"""Scraper for U Telleru restaurant."""

from datetime import date, datetime
from typing import Optional, List
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('utelleru')
class UtelleruScraper(BaseScraper):
    """Scraper for U Telleru restaurant (https://www.utelleru.cz/obedy/)."""

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        """Scrape U Telleru menu for the specified date."""
        if target_date is None:
            target_date = date.today()

        try:
            # Fetch the page
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            # Get the Czech day name
            day_name = self.get_czech_weekday_name(target_date)

            # Find today's menu section
            items = []
            raw_text_parts = []

            # Look for the day header (e.g., "Pondělí")
            # The structure typically has a heading or strong tag with the day name
            day_headers = soup.find_all(['h2', 'h3', 'strong', 'b'])

            for header in day_headers:
                header_text = header.get_text(strip=True).lower()
                if day_name in header_text:
                    # Found the right day, extract menu items from following siblings
                    items, raw_text = self._extract_menu_items(header)
                    raw_text_parts.append(raw_text)
                    break

            # If we didn't find items by day name, try to get all menu items
            if not items:
                # Try alternative: look for menu items in a specific section
                menu_section = soup.find('div', class_=['menu', 'daily-menu', 'obedy'])
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

    def _extract_menu_items(self, element) -> tuple[List[MenuItem], str]:
        """
        Extract menu items from an element and its siblings.

        Returns:
            Tuple of (items list, raw text)
        """
        items = []
        raw_text_parts = []

        # Try to find items in list elements
        parent = element.find_parent(['div', 'section', 'article'])
        if not parent:
            parent = element

        # Look for lists (ul, ol) or paragraphs
        for list_elem in parent.find_all(['ul', 'ol', 'p']):
            list_items = list_elem.find_all('li') if list_elem.name in ['ul', 'ol'] else [list_elem]

            for item_elem in list_items:
                text = item_elem.get_text(strip=True)
                if not text or len(text) < 3:
                    continue

                raw_text_parts.append(text)

                # Try to parse item
                menu_item = self._parse_menu_item(text)
                if menu_item:
                    items.append(menu_item)

        return items, "\n".join(raw_text_parts)

    def _parse_menu_item(self, text: str) -> Optional[MenuItem]:
        """Parse a single menu item from text."""
        if not text:
            return None

        # Detect item type
        item_type = MenuItemType.OTHER
        text_lower = text.lower()

        if any(word in text_lower for word in ['polévka', 'polievka', 'soup']):
            item_type = MenuItemType.SOUP
        elif any(word in text_lower for word in ['hlavní', 'jídlo', 'main']):
            item_type = MenuItemType.MAIN
        elif any(word in text_lower for word in ['příloha', 'priloha', 'side']):
            item_type = MenuItemType.SIDE
        elif any(word in text_lower for word in ['dezert', 'moučník', 'dessert']):
            item_type = MenuItemType.DESSERT
        else:
            # If no type keyword, assume it's a main dish
            item_type = MenuItemType.MAIN

        # Extract price
        price = self.normalize_price(text)

        # Clean up the name by removing price info
        name = text
        if price:
            # Remove price patterns from name
            import re
            name = re.sub(r'\d+\s*[,.-]?\s*(?:kč|czk)?', '', name, flags=re.IGNORECASE)
            name = name.strip(' ,-.')

        return MenuItem(
            name=name,
            description=None,
            price=price,
            type=item_type
        )
