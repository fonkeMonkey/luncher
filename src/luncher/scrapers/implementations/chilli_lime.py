"""Scraper for Chilli & Lime restaurant."""

from datetime import date, datetime
from typing import Optional, List
import json
import re
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('chilli_lime')
class ChilliLimeScraper(BaseScraper):
    """Scraper for Chilli & Lime restaurant (https://chilliandlime.choiceqr.com/online-menu)."""

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        """Scrape Chilli & Lime menu for the specified date."""
        if target_date is None:
            target_date = date.today()

        try:
            # Fetch the page
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            # Extract JSON data from Next.js __NEXT_DATA__ script tag
            next_data_script = soup.find('script', id='__NEXT_DATA__')

            if not next_data_script:
                return self.create_error_menu(target_date, "Could not find menu data")

            try:
                data = json.loads(next_data_script.string)
            except json.JSONDecodeError:
                return self.create_error_menu(target_date, "Failed to parse menu JSON")

            # Navigate through the JSON structure to find menu items
            # The structure is typically: props -> pageProps -> ... -> menu items
            items = []
            raw_text_parts = []

            menu_data = self._extract_menu_from_json(data)

            if menu_data:
                items, raw_text_parts = self._parse_menu_data(menu_data, target_date)

            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text="\n".join(raw_text_parts) if raw_text_parts else json.dumps(menu_data, ensure_ascii=False)[:500],
                scraped_at=datetime.now(),
                url=self.config.url
            )

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Failed to fetch page: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Scraping error: {e}")

    def _extract_menu_from_json(self, data: dict) -> Optional[dict]:
        """Extract menu data from Next.js JSON structure."""
        try:
            # Try different common paths
            if 'props' in data and 'pageProps' in data['props']:
                page_props = data['props']['pageProps']

                # Look for menu-related keys
                for key in ['menu', 'menuData', 'categories', 'items', 'products']:
                    if key in page_props:
                        return page_props[key]

                # If menu is nested deeper
                for key, value in page_props.items():
                    if isinstance(value, dict):
                        for nested_key in ['menu', 'items', 'categories']:
                            if nested_key in value:
                                return value[nested_key]

            return None
        except (KeyError, TypeError):
            return None

    def _parse_menu_data(self, menu_data, target_date: date) -> tuple[List[MenuItem], List[str]]:
        """Parse menu items from JSON data."""
        items = []
        raw_text_parts = []

        # Get day name for filtering
        day_name = self.get_czech_weekday_name(target_date)

        # Handle different JSON structures
        if isinstance(menu_data, list):
            for item_data in menu_data:
                menu_item, raw_text = self._parse_menu_item_json(item_data)
                if menu_item:
                    items.append(menu_item)
                    if raw_text:
                        raw_text_parts.append(raw_text)

        elif isinstance(menu_data, dict):
            # Check if it has categories
            if 'categories' in menu_data:
                for category in menu_data['categories']:
                    if isinstance(category, dict) and 'items' in category:
                        for item_data in category['items']:
                            menu_item, raw_text = self._parse_menu_item_json(item_data)
                            if menu_item:
                                items.append(menu_item)
                                if raw_text:
                                    raw_text_parts.append(raw_text)
            else:
                # Try to find items directly
                for key, value in menu_data.items():
                    if isinstance(value, list):
                        for item_data in value:
                            menu_item, raw_text = self._parse_menu_item_json(item_data)
                            if menu_item:
                                items.append(menu_item)
                                if raw_text:
                                    raw_text_parts.append(raw_text)

        return items, raw_text_parts

    def _parse_menu_item_json(self, item_data: dict) -> tuple[Optional[MenuItem], Optional[str]]:
        """Parse a single menu item from JSON."""
        if not isinstance(item_data, dict):
            return None, None

        # Extract common fields (field names may vary)
        name = item_data.get('name') or item_data.get('title') or item_data.get('label')
        description = item_data.get('description') or item_data.get('desc')
        price_value = item_data.get('price') or item_data.get('cost')

        if not name:
            return None, None

        # Parse price
        price = None
        if price_value:
            if isinstance(price_value, (int, float)):
                price = float(price_value)
            elif isinstance(price_value, str):
                price = self.normalize_price(price_value)

        # Determine item type
        item_type = MenuItemType.MAIN
        category = (item_data.get('category') or item_data.get('type') or '').lower()

        if 'soup' in category or 'polévka' in category:
            item_type = MenuItemType.SOUP
        elif 'dessert' in category or 'dezert' in category:
            item_type = MenuItemType.DESSERT
        elif 'side' in category or 'příloha' in category:
            item_type = MenuItemType.SIDE

        raw_text = f"{name}"
        if description:
            raw_text += f" - {description}"
        if price:
            raw_text += f" ({price} Kč)"

        return MenuItem(
            name=name,
            description=description,
            price=price,
            type=item_type
        ), raw_text
