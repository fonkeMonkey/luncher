"""Scraper for Spravovna restaurant."""

import re
from datetime import date, datetime
from typing import Optional, List, Tuple
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('spravovna')
class SpravovnaScraper(BaseScraper):
    """Scraper for Spravovna restaurant (https://www.spravovna.cz/).

    The website embeds a menicka.cz iframe for the daily menu.
    We fetch the iframe directly:
      https://www.menicka.cz/api/iframe/?id=9733&datum=dnes

    Structure: table.menu with rows:
      tr.soup  — soup row:  td.food (name), td.prize (price)
      tr.main  — main row:  td.no (number), td.food (name), td.prize (price)
    Item type inferred from row class and name keywords.
    """

    MENICKA_URL = "https://www.menicka.cz/api/iframe/?id=9733&datum=dnes"

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            response = requests.get(self.MENICKA_URL, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            table = soup.find('table', class_='menu')
            if not table:
                return self.create_error_menu(target_date, "Tabulka menu nebyla nalezena na menicka.cz")

            items, raw_text = self._extract_items(table)

            if not items:
                return self.create_error_menu(target_date, "Menu pro dnešní den nebylo nalezeno")

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

    def _extract_items(self, table) -> Tuple[List[MenuItem], str]:
        """Extract menu items from the menicka.cz table."""
        items = []
        raw_parts = []

        for tr in table.find_all('tr'):
            row_classes = tr.get('class', [])
            food_el = tr.find('td', class_='food')
            prize_el = tr.find('td', class_='prize')

            if not food_el:
                continue

            name = food_el.get_text(strip=True)
            price_text = prize_el.get_text(strip=True) if prize_el else ''

            if not name:
                continue

            price = None
            m = re.search(r'(\d+)', price_text)
            if m:
                price = float(m.group(1))

            raw_parts.append(f"{name} - {price_text}")

            nl = name.lower()
            if 'soup' in row_classes:
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek', 'lívance', 'palačinka']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            items.append(MenuItem(
                name=name,
                price=price,
                type=item_type
            ))

        return items, "\n".join(raw_parts)
