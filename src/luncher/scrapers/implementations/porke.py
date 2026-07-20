I need to analyze the HTML to understand the new structure. The HTML provided is truncated, but I can see:

1. The navigation links to `#menu` (not a tab with `#tabid_238_1`)
2. The old tab-based system seems to be gone
3. The page uses `#menu` anchor for the lunch menu section

Since the HTML is truncated and doesn't show the actual menu items, I need to write a more robust scraper that:
1. Tries the new structure (navigating to `#menu` section, looking for elementor price list widgets anywhere on the page)
2. Falls back gracefully

The key changes: the tab system with `tabid_238_1` is gone. The menu is now at `#menu` anchor. I'll search for elementor price list items across the whole page, and also try other common patterns.

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

    The lunch menu is under the #menu anchor section.
    Items use Elementor price list widgets:
      ul.elementor-price-list > li.elementor-price-list-item
        span.elementor-price-list-title   — item name
        span.elementor-price-list-price   — price (e.g. "179 Kč")
        p.elementor-price-list-description — optional description
    Soups are identified by price 49 Kč or keywords in the name.
    """

    MENU_ANCHOR = 'menu'

    async def get_html_for_fallback(self) -> str:
        """Fetch rendered HTML via Playwright for AI fallback."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(self.config.url, timeout=30000)
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(2000)
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
                await page.wait_for_timeout(2000)

                content = await page.content()
                await browser.close()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'lxml')

            items, raw_text = self._extract_items(soup)

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

    def _find_menu_section(self, soup):
        """Try to find the lunch menu section by various strategies."""
        # Strategy 1: find section/div with id="menu"
        section = soup.find(id=self.MENU_ANCHOR)
        if section and section.find('li', class_='elementor-price-list-item'):
            return section

        # Strategy 2: find anchor tag with name="menu" and get parent section
        anchor = soup.find('a', attrs={'name': self.MENU_ANCHOR})
        if anchor:
            parent = anchor.find_parent('section')
            if parent and parent.find('li', class_='elementor-price-list-item'):
                return parent

        # Strategy 3: find heading containing "polední menu" text and get its section
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span']):
            text = heading.get_text(strip=True).lower()
            if 'polední menu' in text or 'poledni menu' in text or 'lunch' in text:
                section = heading.find_parent('section')
                if section and section.find('li', class_='elementor-price-list-item'):
                    return section

        # Strategy 4: find the first section that contains price list items
        for section in soup.find_all('section', class_='elementor-section'):
            if section.find('li', class_='elementor-price-list-item'):
                return section

        # Strategy 5: return whole soup as fallback (search everywhere)
        return soup

    def _extract_items(self, soup) -> Tuple[List[MenuItem], str]:
        """Extract items from Elementor price list widgets."""
        items = []
        raw_parts = []

        panel = self._find_menu_section(soup)

        all_lis = panel.find_all('li', class_='elementor-price-list-item')

        if not all_lis:
            # Broader search across whole document
            all_lis = soup.find_all('li', class_='elementor-price-list-item')

        for li in all_lis:
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
            if price == 49.0 or any(w in nl for w in ['polévka', 'vývar', 'krém', 'bramborová', 'soup']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek', 'dort']):
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