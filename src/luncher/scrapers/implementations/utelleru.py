"""Scraper for U Telleru restaurant."""

import re
from datetime import date, datetime
from typing import Optional, List, Tuple
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('utelleru')
class UtelleruScraper(BaseScraper):
    """Scraper for U Telleru restaurant (https://www.utelleru.cz/obedy/).

    Structure: days alternate between div.bezova and div.modra sections.
    Each section has div.polozka4 items containing:
      div.nazev5 > p  (item name)
      div.alergeny    (allergen codes)
      div.cena        (price, e.g. "59 Kč")
    """

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            day_name = self.get_czech_weekday_name(target_date)
            section = self._find_day_section(soup, day_name)

            if section is None:
                return self.create_error_menu(target_date, f"Menu pro {day_name} nebylo nalezeno")

            items, raw_text = self._extract_items(section)

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

    def _find_day_section(self, soup: BeautifulSoup, day_name: str):
        """Find the day section div (bezova or modra) for the given day."""
        for div in soup.find_all('div', class_=['bezova', 'modra']):
            h2 = div.find('h2')
            if h2 and day_name in h2.get_text(strip=True).lower():
                return div
        return None

    def _extract_items(self, section) -> Tuple[List[MenuItem], str]:
        """Extract menu items from a day section."""
        items = []
        raw_parts = []

        for p4 in section.find_all('div', class_='polozka4'):
            name_div = p4.find('div', class_='nazev5')
            price_div = p4.find('div', class_='cena')

            if not name_div:
                continue

            # Name is in a <p> inside nazev5, or directly
            p_tag = name_div.find('p')
            raw_name = (p_tag or name_div).get_text(strip=True)
            if not raw_name:
                continue

            raw_parts.append(raw_name)

            # Price
            price_text = price_div.get_text(strip=True) if price_div else ''
            price = self._parse_price(price_text)

            # Clean name: remove leading number prefix ("1.", "2.", "Náš tip:")
            name = re.sub(r'^\d+\.\s*', '', raw_name).strip()
            name = re.sub(r'^náš tip:\s*', '', name, flags=re.IGNORECASE).strip()

            # Item type
            nl = raw_name.lower()
            if any(w in nl for w in ['polévka', 'vývar', 'polívka']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            items.append(MenuItem(name=name, price=price, type=item_type))

        return items, "\n".join(raw_parts)

    def _parse_price(self, text: str) -> Optional[float]:
        """Parse price from '59 Kč' format."""
        if not text:
            return None
        m = re.search(r'(\d+)', text)
        return float(m.group(1)) if m else None
