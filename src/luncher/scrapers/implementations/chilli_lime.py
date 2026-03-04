"""Scraper for Chilli & Lime restaurant."""

from datetime import date, datetime
from typing import Optional, List, Tuple
import json
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('chilli_lime')
class ChilliLimeScraper(BaseScraper):
    """Scraper for Chilli & Lime restaurant (https://chilliandlime.choiceqr.com/online-menu).

    Structure: Next.js page with JSON in <script id="__NEXT_DATA__">.
      props.app.categories  — list of menu categories
      props.app.menu        — list of all menu items

    The lunch category has hurl='poledni-nabidka' (or name contains 'POLEDNÍ').
    Each item has: name, description, price (in halíře, divide by 100 for Kč), category (id).
    """

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            script = soup.find('script', id='__NEXT_DATA__')
            if not script:
                return self.create_error_menu(target_date, "Nepodařilo se najít data menu (chybí __NEXT_DATA__)")

            data = json.loads(script.string)
            app = data.get('props', {}).get('app', {})

            cat_id = self._find_lunch_category_id(app)
            if not cat_id:
                return self.create_error_menu(target_date, "Nepodařilo se najít kategorii poledního menu")

            items, raw_text = self._extract_items(app, cat_id)

            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text=raw_text,
                scraped_at=datetime.now(),
                url=self.config.url
            )

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Chyba načítání: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            return self.create_error_menu(target_date, f"Chyba parsování JSON: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    def _find_lunch_category_id(self, app: dict) -> Optional[str]:
        """Find the lunch menu category ID."""
        for cat in app.get('categories', []):
            hurl = cat.get('hurl', '').lower()
            name = cat.get('name', '').lower()
            if 'poledni' in hurl or 'polední' in name or 'obed' in hurl:
                return cat['_id']
        # Fallback: first category
        cats = app.get('categories', [])
        return cats[0]['_id'] if cats else None

    def _extract_items(self, app: dict, cat_id: str) -> Tuple[List[MenuItem], str]:
        """Extract items belonging to the lunch category."""
        items = []
        raw_parts = []

        for item in app.get('menu', []):
            if item.get('category') != cat_id:
                continue

            name = item.get('name', '').strip()
            description = (item.get('description') or '').strip()
            # Price is stored in halíře (1/100 Kč)
            price_raw = item.get('price', 0)
            price = float(price_raw) / 100 if price_raw else None

            if not name:
                continue

            raw_parts.append(f"{name}{' - ' + description if description else ''} - {price} Kč")

            nl = name.lower()
            if any(w in nl for w in ['polévka', 'soup', 'vývar']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'dessert']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            # For the generic soup label, show the actual soup name from description
            if item_type == MenuItemType.SOUP and description and 'polední' in nl:
                name = description
                description = None

            items.append(MenuItem(
                name=name,
                description=description or None,
                price=price,
                type=item_type
            ))

        return items, "\n".join(raw_parts)
