"""Scraper for Spravovna restaurant."""

from datetime import date, datetime
from typing import Optional, List
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('spravovna')
class SpravovnaScraper(BaseScraper):
    """Scraper for Spravovna restaurant (https://www.spravovna.cz/)."""

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        """Scrape Spravovna menu for the specified date."""
        if target_date is None:
            target_date = date.today()

        try:
            # Fetch the page
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            # Get the Czech day name
            day_name = self.get_czech_weekday_name(target_date)

            items = []
            raw_text_parts = []

            # Spravovna typically has menu in specific sections
            # Look for menu containers or day-specific sections
            menu_containers = soup.find_all(['div', 'section'], class_=lambda x: x and ('menu' in x.lower() or 'obed' in x.lower()))

            if not menu_containers:
                # Try finding by text content
                all_headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'strong'])
                for heading in all_headings:
                    heading_text = heading.get_text(strip=True).lower()
                    if day_name in heading_text or 'menu' in heading_text:
                        menu_containers.append(heading.find_parent())

            # Extract items from containers
            for container in menu_containers:
                if container:
                    container_items, container_text = self._extract_menu_items(container, day_name)
                    items.extend(container_items)
                    if container_text:
                        raw_text_parts.append(container_text)

            # If no items found, try a broader search
            if not items:
                body = soup.find('body')
                if body:
                    items, raw_text = self._extract_menu_items(body, day_name)
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

    def _extract_menu_items(self, container, day_name: str) -> tuple[List[MenuItem], str]:
        """Extract menu items from a container."""
        items = []
        raw_text_parts = []

        # Find all potential menu item elements
        elements = container.find_all(['li', 'p', 'div'])

        for elem in elements:
            text = elem.get_text(strip=True)
            if not text or len(text) < 5:
                continue

            # Skip navigation and non-menu content
            if any(skip in text.lower() for skip in ['kontakt', 'otevírací', 'galerie', 'o nás', 'copyright']):
                continue

            raw_text_parts.append(text)

            # Parse menu item
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
        elif any(word in text_lower for word in ['dezert', 'moučník', 'zákusek']):
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
