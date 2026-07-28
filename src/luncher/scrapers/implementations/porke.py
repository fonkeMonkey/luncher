I need to analyze the HTML to understand the new structure. The HTML is truncated, but I can see key structural differences:

1. The navigation links show `#menu` for "Polední Menu" instead of a tab-based system
2. The old tab selector `a[href="#tabid_238_1"]` no longer exists
3. The page uses anchor-based navigation (`#menu` section) instead of tabs

Since the HTML is truncated and doesn't show the actual menu content, I need to write a scraper that:
1. Navigates to the `#menu` section instead of clicking a tab
2. Still looks for Elementor price list widgets (the structure likely remains similar)
3. Falls back gracefully if the structure has changed further

"""Scraper for PORKE restaurant."""

import re
from datetime import date, datetime
from typing import Optional, List, Tuple
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('porke')
class PorkeScraper(BaseScraper):
    """Scraper for PORKE restaurant (https://www.porke.cz/).

    The lunch menu is in the section with id 'menu' (anchor #menu).
    Items use Elementor price list widgets:
      ul.elementor-price-list > li.elementor-price-list-item
        span.elementor-price-list-title   — item name
        span.elementor-price-list-price   — price (e.g. "179 Kč")
        p.elementor-price-list-description — optional description
    Soups are identified by price 49 Kč or keywords in the name.
    """

    MENU_ANCHOR = '#menu'
    MENU_SECTION_ID = 'menu'

    async def get_html_for_fallback(self) -> str:
        """Fetch rendered HTML via Playwright for AI fallback."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(self.config.url, timeout=30000)
            await page.wait_for_load_state('networkidle')
            content = await page.content()
            await browser.close()
        return content

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return self.create_error_menu(
                target_date, "Playwright není nainstalován. Spusť: playwright install chromium"
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(self.config.url, timeout=30000)
                await page.wait_for_load_state('networkidle')
                content = await page.content()
                await browser.close()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'lxml')

            # Try to find the lunch menu section by anchor id 'menu'
            panel = soup.find(id=self.MENU_SECTION_ID)

            # If not found by id, look for a section containing 'Polední Menu' heading
            if not panel:
                for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    text = heading.get_text(strip=True).lower()
                    if 'polední menu' in text or 'poledni menu' in text or 'lunch' in text:
                        # Walk up to a reasonable container
                        panel = heading.find_parent('section') or heading.find_parent('div')
                        break

            # If still not found, search the whole page for price list items
            if not panel:
                panel = soup

            items, raw_text = self._extract_items(panel)

            if not items:
                return self.create_error_menu(target_date, "Žádné položky menu nebyly nalezeny")

            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text=raw_text,
                scraped_at=datetime.now(),
                url=self.config.url
            )

        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    def _extract_items(self, panel) -> Tuple[List[MenuItem], str]:
        """Extract items from Elementor price list widgets in the panel."""
        items = []
        raw_parts = []

        for li in panel.find_all('li', class_='elementor-price-list-item'):
            title_el = li.find('span', class_='elementor-price-list-title')
            price_el = li.find('span', class_='elementor-price-list-price')
            desc_el = li.find('p', class_='elementor-price-list-description')

            name = self.clean_text(title_el) if title_el else ''
            price_text = self.clean_text(price_el) if price_el else ''
            description = self.clean_text(desc_el) if desc_el else None

            if not name:
                continue

            # Parse price
            price = None
            m = re.search(r'(\d+)', price_text)
            if m:
                price = float(m.group(1))

            raw_parts.append(f"{name}{' - ' + description if description else ''} - {price_text}")

            # Soups have 49 Kč price or soup keywords
            nl = name.lower()
            if price == 49.0 or any(w in nl for w in ['polévka', 'vývar', 'krém', 'bramborová']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            items.append(MenuItem(
                name=name,
                description=description,
                price=price,
                type=item_type
            ))

        return items, "\n".join(raw_parts)