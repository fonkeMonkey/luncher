"""Scraper for PORKE restaurant."""

from datetime import date, datetime
from typing import Optional, List
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('porke')
class PorkeScraper(BaseScraper):
    """Scraper for PORKE restaurant (https://www.porke.cz/)."""

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        """
        Scrape PORKE menu for the specified date.

        This requires Playwright as the menu is loaded dynamically via JavaScript.
        """
        if target_date is None:
            target_date = date.today()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return self.create_error_menu(
                target_date,
                "Playwright not installed. Run: playwright install chromium"
            )

        try:
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                # Navigate to the page
                await page.goto(self.config.url, timeout=30000)

                # Wait for page to load
                await page.wait_for_load_state('networkidle')

                # Look for and click the "poledni menu" button
                try:
                    # Try different selectors for the lunch menu button
                    button_selectors = [
                        'text="poledni menu"',
                        'text="polední menu"',
                        'text="Polední menu"',
                        'button:has-text("poledni")',
                        'button:has-text("polední")',
                        'a:has-text("poledni")',
                        'a:has-text("polední")',
                        '[href*="poledni"]',
                        '[href*="lunch"]'
                    ]

                    button_clicked = False
                    for selector in button_selectors:
                        try:
                            button = page.locator(selector).first
                            if await button.count() > 0:
                                await button.click()
                                button_clicked = True
                                # Wait for content to load after click
                                await page.wait_for_timeout(2000)
                                break
                        except:
                            continue

                except Exception as e:
                    # If button click fails, continue anyway - menu might be visible
                    pass

                # Extract menu content
                content = await page.content()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, 'lxml')

                # Get the Czech day name
                day_name = self.get_czech_weekday_name(target_date)

                items = []
                raw_text_parts = []

                # Look for menu sections
                menu_sections = soup.find_all(['div', 'section'], class_=lambda x: x and any(
                    keyword in str(x).lower() for keyword in ['menu', 'lunch', 'obed', 'poledni']
                ))

                for section in menu_sections:
                    section_items, section_text = self._extract_menu_items(section, day_name)
                    items.extend(section_items)
                    if section_text:
                        raw_text_parts.append(section_text)

                # If no items found in specific sections, try broader search
                if not items:
                    # Look for any text containing day name
                    all_text = soup.get_text()
                    if day_name in all_text.lower():
                        items, raw_text = self._extract_menu_items(soup.body, day_name)
                        raw_text_parts.append(raw_text)

                await browser.close()

                return DailyMenu(
                    restaurant_id=self.config.id,
                    restaurant_name=self.config.name,
                    date=target_date,
                    items=items,
                    raw_text="\n".join(raw_text_parts) if raw_text_parts else content[:500],
                    scraped_at=datetime.now(),
                    url=self.config.url
                )

        except Exception as e:
            return self.create_error_menu(target_date, f"Scraping error: {e}")

    def _extract_menu_items(self, container, day_name: str) -> tuple[List[MenuItem], str]:
        """Extract menu items from a container."""
        items = []
        raw_text_parts = []

        # Find all potential menu item elements
        elements = container.find_all(['li', 'p', 'div', 'span'])

        for elem in elements:
            text = elem.get_text(strip=True)
            if not text or len(text) < 5:
                continue

            # Skip navigation and non-menu content
            if any(skip in text.lower() for skip in [
                'kontakt', 'otevírací', 'galerie', 'o nás', 'copyright',
                'facebook', 'instagram', 'menu', 'hlavní strana'
            ]):
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
        elif any(word in text_lower for word in ['dezert', 'moučník']):
            item_type = MenuItemType.DESSERT
        elif any(word in text_lower for word in ['příloha', 'priloha']):
            item_type = MenuItemType.SIDE

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
