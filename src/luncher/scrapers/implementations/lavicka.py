"""Scraper for Restaurace Lavička."""

import re
from datetime import date, datetime
from typing import Optional, List, Tuple
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('lavicka')
class LavickaScraper(BaseScraper):
    """Scraper for Restaurace Lavička (https://www.restaurace-lavicka.cz/menu/).

    Structure: Elementor-built page with a section whose h2 heading contains
    'Denní nabídka'. Each daily item is an elementor-inner-section inside that
    section with two columns: name/description on the left and price on the right.
    """

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            items, raw_text = self._extract_daily_items(soup, target_date)

            if not items:
                return self.create_error_menu(target_date, "Denní menu nebylo nalezeno")

            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text=raw_text,
                scraped_at=datetime.now(),
                url=self.config.url,
            )

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Chyba načítání: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    def _extract_daily_items(self, soup: BeautifulSoup, target_date: date) -> Tuple[List[MenuItem], str]:
        """Find the daily menu section and extract items from it."""
        daily_section = self._find_daily_section(soup)
        if daily_section is None:
            return [], ""

        items = []
        raw_parts = []

        for inner in daily_section.find_all('section', class_='elementor-inner-section'):
            columns = inner.find_all('div', class_='elementor-column', recursive=False)
            if not columns:
                # columns may be inside elementor-container
                container = inner.find('div', class_='elementor-container')
                columns = container.find_all('div', class_='elementor-column', recursive=False) if container else []

            if len(columns) < 2:
                continue

            name_col, price_col = columns[0], columns[1]

            # Name is the first heading or text-editor widget in the name column
            name = self._extract_text_from_column(name_col)
            price_text = self._extract_text_from_column(price_col)

            if not name:
                continue

            raw_parts.append(f"{name} | {price_text}")
            price = self._parse_price(price_text)

            name_lower = name.lower()
            if any(w in name_lower for w in ['polévka', 'vývar', 'polívka', 'krém', 'česnečka', 'bujón']):
                item_type = MenuItemType.SOUP
            elif any(w in name_lower for w in ['dezert', 'moučník', 'zákusek', 'dort', 'palačink']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            items.append(MenuItem(name=name, price=price, type=item_type))

        return items, "\n".join(raw_parts)

    def _find_daily_section(self, soup: BeautifulSoup):
        """Find the outer section containing the daily menu heading."""
        for h2 in soup.find_all('h2'):
            if 'Denní nabídka' in h2.get_text():
                return h2.find_parent('section')
        return None

    def _extract_text_from_column(self, column) -> str:
        """Get the main text content from an elementor column."""
        # Try heading widget first, then text-editor
        for widget_type in ['elementor-widget-heading', 'elementor-widget-text-editor']:
            widget = column.find('div', class_=widget_type)
            if widget:
                text = self.clean_text(widget)
                if text:
                    return text
        return self.clean_text(column)

    def _parse_price(self, text: str) -> Optional[float]:
        """Parse price from text like '188 Kč'."""
        if not text:
            return None
        m = re.search(r'(\d+)', text)
        return float(m.group(1)) if m else None
