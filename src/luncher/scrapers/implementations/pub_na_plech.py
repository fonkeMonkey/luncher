"""Scraper for Pub Na Plech restaurant."""

import re
from datetime import date, datetime
from typing import Optional, List, Tuple
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('pub_na_plech')
class PubNaPlechScraper(BaseScraper):
    """Scraper for Pub Na Plech restaurant (http://www.pubnaplech.cz/).

    Structure inside div.ez-c[1]:
      Each day is a pair of direct children:
        div.b.b-text.cf  — contains h2 with day name (e.g. "Úterý")
        div.mt.mt-pricelist.b-s.cf  — contains menu items

      Inside mt-pricelist → div.mt-c → div.mt-i × N → div.mt-i-c:
        div.b-c  — item name (may include section label like "Polévka")
        h3       — price text (e.g. "49 Kč / 29 Kč")
    """

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'lxml')

            day_name = self.get_czech_weekday_name(target_date)
            # Capitalise first letter to match site format (e.g. "Úterý")
            day_cap = day_name.capitalize()

            pricelist = self._find_day_pricelist(soup, day_cap)
            if pricelist is None:
                return self.create_error_menu(target_date, f"Menu pro {day_name} nebylo nalezeno")

            items, raw_text = self._extract_items(pricelist, day_name)

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
        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    def _find_day_pricelist(self, soup: BeautifulSoup, day_cap: str):
        """
        Find the mt-pricelist div that follows the b-text div with today's h2 heading.
        Both are direct children of the same div.ez-c container.
        """
        for ez in soup.find_all('div', class_='ez-c'):
            children = [c for c in ez.children if hasattr(c, 'name') and c.name]
            for i, child in enumerate(children):
                if 'b-text' in child.get('class', []):
                    h2 = child.find('h2')
                    if h2 and h2.get_text(strip=True) == day_cap:
                        # The very next sibling should be the mt-pricelist
                        if i + 1 < len(children):
                            nxt = children[i + 1]
                            if 'mt-pricelist' in ' '.join(nxt.get('class', [])):
                                return nxt
        return None

    def _extract_items(self, pricelist, day_name: str) -> Tuple[List[MenuItem], str]:
        """Extract menu items from a mt-pricelist div."""
        items = []
        raw_parts = []

        # Skip section headers and drink items
        skip_keywords = [
            'polévka', 'hlavní jídlo', 'specialita', 'dezert', 'nápoj',
            'ledový čaj', 'tankové pivo', 'k hlavnímu', 'k polednímu',
            'přijímáme', 'zabalit'
        ]

        for mi_c in pricelist.find_all('div', class_='mt-i-c'):
            name_div = mi_c.find('div', class_='b-c')
            price_el = mi_c.find('h3')

            if not name_div:
                continue

            name = self.clean_text(name_div)
            price_text = self.clean_text(price_el) if price_el else ''

            # Skip section labels and drink items
            name_lower = name.lower()
            if not name or len(name) < 4:
                continue
            if any(kw in name_lower for kw in skip_keywords) and 'Kč' not in price_text:
                continue
            if any(kw in name_lower for kw in ['ledový čaj', 'tankové pivo', 'k hlavnímu', 'k polednímu']):
                continue

            raw_parts.append(f"{name} - {price_text}")

            # Parse first price from "49 Kč / 29 Kč" → 49
            price = None
            m = re.search(r'(\d+)', price_text)
            if m:
                price = float(m.group(1))

            # Item type
            nl = name_lower
            if any(w in nl for w in ['polévka', 'vývar', 'gulášová', 'cibulačka',
                                     'frankfurtská', 'hovězí vývar', 'dýňová',
                                     'středeční', 'úterní', 'pondělní', 'čtvrteční', 'páteční']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'roláda', 'moučník', 'zákusek']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            # Clean name: remove leading bullet "·"
            name = name.lstrip('·').strip()

            items.append(MenuItem(name=name, price=price, type=item_type))

        return items, "\n".join(raw_parts)
