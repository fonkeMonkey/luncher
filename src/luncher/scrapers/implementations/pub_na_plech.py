"""Scraper for Pub Na Plech restaurant."""

from datetime import date, datetime
from typing import Optional, List
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('pub_na_plech')
class PubNaPlechScraper(BaseScraper):
    """Scraper for Pub Na Plech restaurant (http://www.pubnaplech.cz/)."""

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        """Scrape Pub Na Plech menu for the specified date."""
        if target_date is None:
            target_date = date.today()

        try:
            # Fetch the page
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            # Set encoding to handle Czech characters
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'lxml')

            # Get the Czech day name
            day_name = self.get_czech_weekday_name(target_date)

            items = []
            raw_text_parts = []

            # Look for day-specific sections
            # Pub Na Plech typically organizes menu by weekdays
            day_section = self._find_day_section(soup, day_name)

            if day_section:
                items, raw_text = self._extract_menu_items(day_section)
                raw_text_parts.append(raw_text)
            else:
                # Try to find any menu content
                menu_section = soup.find(['div', 'section', 'article'], class_=lambda x: x and 'menu' in str(x).lower())
                if menu_section:
                    items, raw_text = self._extract_menu_items(menu_section)
                    raw_text_parts.append(raw_text)

            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text="\n".join(raw_text_parts) if raw_text_parts else response.text[:500],
                scraped_at=datetime.now(),
                url=self.config.url
            )

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Failed to fetch page: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Scraping error: {e}")

    def _find_day_section(self, soup: BeautifulSoup, day_name: str):
        """Find the section for a specific day."""
        # Look for headings containing the day name
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'strong', 'b'])
        for heading in headings:
            heading_text = heading.get_text(strip=True).lower()
            if day_name in heading_text:
                # Return the parent container or next siblings
                parent = heading.find_parent(['div', 'section', 'article'])
                if parent:
                    return parent
                return heading
        return None

    def _extract_menu_items(self, container) -> tuple[List[MenuItem], str]:
        """Extract menu items from a container."""
        items = []
        raw_text_parts = []

        # Find all list items or paragraphs
        elements = container.find_all(['li', 'p', 'div'])

        for elem in elements:
            text = elem.get_text(strip=True)
            if not text or len(text) < 5:
                continue

            # Skip non-menu content
            if any(skip in text.lower() for skip in ['kontakt', 'otevírací', 'rezervace', 'copyright', 'o nás']):
                continue

            raw_text_parts.append(text)

            # Parse menu item
            menu_item = self._parse_menu_item(text)
            if menu_item:
                items.append(menu_item)

        # Also check for table structures (common for menus)
        tables = container.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                text = row.get_text(strip=True)
                if text and len(text) >= 5:
                    raw_text_parts.append(text)
                    menu_item = self._parse_menu_item(text)
                    if menu_item:
                        items.append(menu_item)

        return items, "\n".join(raw_text_parts)

    def _parse_menu_item(self, text: str) -> Optional[MenuItem]:
        """Parse a single menu item from text."""
        if not text:
            return None

        # Detect item type
        item_type = MenuItemType.MAIN
        text_lower = text.lower()

        if any(word in text_lower for word in ['polévka', 'polievka']):
            item_type = MenuItemType.SOUP
        elif any(word in text_lower for word in ['příloha', 'priloha']):
            item_type = MenuItemType.SIDE
        elif any(word in text_lower for word in ['dezert', 'moučník']):
            item_type = MenuItemType.DESSERT

        # Extract price
        price = self.normalize_price(text)

        # Clean up the name
        name = text
        if price:
            import re
            name = re.sub(r'\d+\s*[,.-]?\s*(?:kč|czk)?', '', name, flags=re.IGNORECASE)
            name = name.strip(' ,-.')

        return MenuItem(
            name=name,
            description=None,
            price=price,
            type=item_type
        )
