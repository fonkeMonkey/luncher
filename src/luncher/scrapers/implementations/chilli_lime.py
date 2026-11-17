"""Scraper for Chilli & Lime restaurant."""

from datetime import date, datetime
from typing import Optional, List, Tuple
import json
import re
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('chilli_lime')
class ChilliLimeScraper(BaseScraper):
    """Scraper for Chilli & Lime restaurant (https://chilliandlime.choiceqr.com/online-menu).

    The page is a Next.js app. The __NEXT_DATA__ script tag no longer contains
    the full menu in props.app. Instead the menu data is loaded client-side via
    the choiceqr API. We fetch it directly from the API endpoint.

    API base: https://api.choiceqr.com/v1/
    Place slug: chilliandlime

    Endpoints used:
      GET /eat/{slug}/menu  ->  { categories: [...], menu: [...] }

    Category fields: _id, name, hurl
    Item fields:     _id, name, description, price (halíře), category (_id ref)
    """

    _API_BASE = "https://api.choiceqr.com/v1"
    _SLUG = "chilliandlime"

    # Fallback: section id visible in the HTML as id="section-60b3d79b809c3bf0560e534f"
    _KNOWN_LUNCH_SECTION_ID = "60b3d79b809c3bf0560e534f"

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            # First attempt: use the JSON API directly
            menu_data = self._fetch_api_menu()
            if menu_data:
                cat_id = self._find_lunch_category_id(menu_data)
                if cat_id:
                    items, raw_text = self._extract_items(menu_data, cat_id)
                    if items:
                        return DailyMenu(
                            restaurant_id=self.config.id,
                            restaurant_name=self.config.name,
                            date=target_date,
                            items=items,
                            raw_text=raw_text,
                            scraped_at=datetime.now(),
                            url=self.config.url,
                        )

            # Second attempt: parse __NEXT_DATA__ from the HTML page (legacy path)
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            script = soup.find('script', id='__NEXT_DATA__')
            if script and script.string:
                data = json.loads(script.string)
                # Try several known paths where choiceqr has stored menu data
                app_data = self._locate_app_data(data)
                if app_data:
                    cat_id = self._find_lunch_category_id(app_data)
                    if cat_id:
                        items, raw_text = self._extract_items(app_data, cat_id)
                        if items:
                            return DailyMenu(
                                restaurant_id=self.config.id,
                                restaurant_name=self.config.name,
                                date=target_date,
                                items=items,
                                raw_text=raw_text,
                                scraped_at=datetime.now(),
                                url=self.config.url,
                            )

            # Third attempt: scrape the rendered HTML directly (SSR skeleton is present)
            items, raw_text = self._scrape_html(soup)
            if items:
                return DailyMenu(
                    restaurant_id=self.config.id,
                    restaurant_name=self.config.name,
                    date=target_date,
                    items=items,
                    raw_text=raw_text,
                    scraped_at=datetime.now(),
                    url=self.config.url,
                )

            return self.create_error_menu(
                target_date,
                "Nepodařilo se najít položky poledního menu (všechny metody selhaly)",
            )

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Chyba načítání: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            return self.create_error_menu(target_date, f"Chyba parsování JSON: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    # ------------------------------------------------------------------
    # API fetch (primary path)
    # ------------------------------------------------------------------

    def _fetch_api_menu(self) -> Optional[dict]:
        """Try to fetch menu data from the choiceqr REST API."""
        # Known API endpoints for choiceqr; try the most likely ones.
        candidates = [
            f"{self._API_BASE}/eat/{self._SLUG}/menu",
            f"{self._API_BASE}/eat/{self._SLUG}",
            f"https://api.choiceqr.com/eat/{self._SLUG}/menu",
        ]
        headers = {
            "Accept": "application/json",
            "Referer": self.config.url,
            "User-Agent": (
                "Mozilla/5.0 (compatible; LuncherBot/1.0)"
            ),
        }
        for url in candidates:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    payload = resp.json()
                    # Accept if it looks like a menu payload
                    if isinstance(payload, dict) and (
                        'categories' in payload or 'menu' in payload
                    ):
                        return payload
                    # Sometimes wrapped
                    for key in ('data', 'result', 'payload'):
                        inner = payload.get(key)
                        if isinstance(inner, dict) and (
                            'categories' in inner or 'menu' in inner
                        ):
                            return inner
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # __NEXT_DATA__ path (secondary)
    # ------------------------------------------------------------------

    def _locate_app_data(self, next_data: dict) -> Optional[dict]:
        """Walk known paths inside __NEXT_DATA__ to find menu/categories."""
        props = next_data.get('props', {})

        # Path 1 (old): props.app
        app = props.get('app')
        if isinstance(app, dict) and ('menu' in app or 'categories' in app):
            return app

        # Path 2: props.pageProps (common Next.js pattern)
        page_props = props.get('pageProps', {})
        for key in ('app', 'menu', 'data', 'initialData', 'initialState'):
            candidate = page_props.get(key)
            if isinstance(candidate, dict) and (
                'menu' in candidate or 'categories' in candidate
            ):
                return candidate

        # Path 3: props.pageProps itself
        if isinstance(page_props, dict) and (
            'menu' in page_props or 'categories' in page_props
        ):
            return page_props

        # Path 4: search one more level deep via BFS
        def _bfs(node, depth=0):
            if depth > 4 or not isinstance(node, dict):
                return None
            if 'menu' in node and 'categories' in node:
                return node
            for v in node.values():
                result = _bfs(v, depth + 1)
                if result:
                    return result
            return None

        return _bfs(next_data)

    # ------------------------------------------------------------------
    # HTML scraping path (tertiary – uses rendered skeleton / SSR content)
    # ------------------------------------------------------------------

    def _scrape_html(self, soup: BeautifulSoup) -> Tuple[List['MenuItem'], str]:
        """Extract menu items directly from rendered HTML."""
        items = []
        raw_parts = []

        # The lunch section is identified by id="section-{KNOWN_ID}" or by
        # heading text "POLEDNÍ MENU".
        section = soup.find(
            'div',
            id=f"section-{self._KNOWN_LUNCH_SECTION_ID}",
        )
        if not section:
            # Fallback: find by heading text
            for heading in soup.find_all(
                class_=re.compile(r'sectionTitle|sectionHeading|categoryTitle', re.I)
            ):
                if 'polední' in heading.get_text(strip=True).lower() or \
                   'poledni' in heading.get_text(strip=True).lower():
                    section = heading.find_parent(
                        class_=re.compile(r'section|wrapper', re.I)
                    )
                    break

        if not section:
            return items, ""

        # Collect item cards within the section
        item_cards = section.find_all(
            class_=re.compile(r'menuItem(?!.*heading|.*Category|.*Button|.*Image|.*Action|.*Info|.*Price|.*Title|.*Desc|.*Text|.*Icon|.*Fav)', re.I)
        )

        # Broaden search if nothing found with the strict pattern
        if not item_cards:
            item_cards = section.find_all(
                class_=re.compile(r'styles_menuItem__', re.I)
            )

        for card in item_cards:
            name_el = card.find(class_=re.compile(r'menuItemTitle|itemTitle', re.I))
            price_el = card.find(class_=re.compile(r'menuItemPrice|itemPrice', re.I))
            desc_el = card.find(class_=re.compile(r'menuItemDescription|itemDescription|menuItemText', re.I))

            name = name_el.get_text(strip=True) if name_el else ''
            if not name:
                continue

            price_text = price_el.get_text(strip=True) if price_el else ''
            price = self._parse_price(price_text)

            description = desc_el.get_text(' ', strip=True) if desc_el else ''
            description = description or None

            raw_parts.append(
                f"{name}{' - ' + description if description else ''}"
                f"{' - ' + str(price) + ' Kč' if price is not None else ''}"
            )

            nl = name.lower()
            if any(w in nl for w in ['polévka', 'soup', 'vývar']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'dessert']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            items.append(MenuItem(
                name=name,
                description=description,
                price=price,
                type=item_type,
            ))

        return items, "\n".join(raw_parts)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _find_lunch_category_id(self, app: dict) -> Optional[str]:
        """Find the lunch menu category ID from an app/menu dict."""
        for cat in app.get('categories', []):
            hurl = cat.get('hurl', '').lower()
            name = cat.get('name', '').lower()
            if (
                'poledni' in hurl
                or 'polední' in name
                or 'poledni' in name
                or 'obed' in hurl
                or 'lunch' in hurl
                or 'lunch' in name
            ):
                return cat.get('_id') or cat.get('id')

        # Fallback: use the known section id directly
        for cat in app.get('categories', []):
            cid = cat.get('_id') or cat.get('id') or ''
            if self._KNOWN_LUNCH_SECTION_ID in cid:
                return cid

        # Last resort: first category
        cats = app.get('categories', [])
        if cats:
            return cats[0].get('_id') or cats[0].get('id')
        return None

    def _extract_items(self, app: dict, cat_id: str) -> Tuple[List['MenuItem'], str]:
        """Extract items belonging to the lunch category from API/JSON data."""
        items: List[MenuItem] = []
        raw_parts: List[str] = []

        menu_list = app.get('menu', app.get('items', app.get('products', [])))

        for item in menu_list:
            # category field may be an id string or a dict with _id
            item_cat = item.get('category', item.get('categoryId', ''))
            if isinstance(item_cat, dict):
                item_cat = item_cat.get('_id', item_cat.get('id', ''))

            if item_cat != cat_id:
                continue

            name = item.get('name', '').strip()
            description = (item.get('description') or '').strip() or None

            # Price stored in halíře (1/100 Kč)
            price_raw = item.get('price', item.get('priceValue', 0))
            if isinstance(price_raw, dict):
                # Sometimes: { "value": 18900, "currency": "CZK" }
                price_raw = price_raw.get('value', 0)
            price = float(price_raw) / 100 if price_raw else None

            if not name:
                continue

            raw_parts.append(
                f"{name}{' - ' + description if description else ''}"
                f"{' - ' + str(price) + ' Kč' if price is not None else ''}"
            )

            nl = name.lower()
            if any(w in nl for w in ['polévka', 'soup', 'vývar']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'dessert']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            # For a generic soup label carry the actual soup from description
            if item_type == MenuItemType.SOUP and description and 'polední' in nl:
                name = description
                description = None

            items.append(MenuItem(
                name=name,
                description=description,
                price=price,
                type=item_type,
            ))

        return items, "\n".join(raw_parts)

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        """Extract a numeric price from a string like '189 Kč' or '189,00'."""
        if not text:
            return None
        match = re.search(r'(\d[\d\s]*[,.]?\d*)', text.replace('\xa0', ' '))
        if match:
            raw = match.group(1).replace(' ', '').replace(',', '.')
            try:
                return float(raw)
            except ValueError:
                pass
        return None