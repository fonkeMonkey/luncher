I need to analyze the HTML to understand the new structure. The HTML is truncated, but I can see the page no longer uses tabs with `tabid_238_1`. The navigation shows `#menu` as the anchor for "Polední Menu". I need to adapt the scraper to find the lunch menu section by the `#menu` anchor/section and look for price list items there, or fall back to searching the entire page.

Since the tab structure is gone and the content appears to be in a section anchored at `#menu`, I'll update the scraper to navigate to the section by ID or look for Elementor price list widgets in the relevant section, with fallbacks.

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

    The lunch menu is in a section reachable via the '#menu' anchor.
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
            await page.wait_for_timeout(1000)
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
                await page.wait_for_timeout(1000)

                content = await page.content()
                await browser.close()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'lxml')

            panel = self._find_menu_panel(soup)
            if not panel:
                return self.create_error_menu(target_date, "Panel poledního menu nebyl nalezen")

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

    def _find_menu_panel(self, soup):
        """Find the lunch menu panel using multiple strategies."""

        # Strategy 1: Look for element with id="menu" (anchor target)
        panel = soup.find(id=self.MENU_ANCHOR)
        if panel and panel.find('li', class_='elementor-price-list-item'):
            return panel

        # Strategy 2: Find a section that contains heading text about lunch menu
        lunch_keywords = ['polední menu', 'poledni menu', 'lunch menu', 'denní menu']
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']):
            text = heading.get_text(strip=True).lower()
            if any(kw in text for kw in lunch_keywords):
                # Walk up to find a section/div container that has price list items
                for parent in heading.parents:
                    if parent.name in ('section', 'div', 'article'):
                        if parent.find('li', class_='elementor-price-list-item'):
                            return parent

        # Strategy 3: Find the first section containing price list items
        # that also appears to be a lunch/daily menu (look for typical lunch prices)
        for section in soup.find_all('section', class_='elementor-section'):
            items = section.find_all('li', class_='elementor-price-list-item')
            if items:
                # Check if prices look like lunch prices (typically 49-299 Kč range)
                prices = []
                for li in items:
                    price_el = li.find('span', class_='elementor-price-list-price')
                    if price_el:
                        m = re.search(r'(\d+)', price_el.get_text())
                        if m:
                            prices.append(int(m.group(1)))
                if prices and any(p <= 300 for p in prices):
                    return section

        # Strategy 4: Return the container of all price list items if any exist
        all_items = soup.find_all('li', class_='elementor-price-list-item')
        if all_items:
            # Return the common ancestor
            return all_items[0].find_parent('ul', class_='elementor-price-list') or \
                   all_items[0].find_parent('section') or \
                   soup.body

        # Strategy 5: Old tab panel fallback
        for tab_id in ['tabid_238_1', 'tabid_238_0', 'tabid_238_2']:
            panel = soup.find(id=tab_id)
            if panel and panel.find('li', class_='elementor-price-list-item'):
                return panel

        return None

    def _extract_items(self, panel) -> Tuple[List[MenuItem], str]:
        """Extract items from Elementor price list widgets in the panel."""
        items = []
        raw_parts = []

        price_list_items = panel.find_all('li', class_='elementor-price-list-item')

        for li in price_list_items:
            title_el = li.find('span', class_='elementor-price-list-title')
            price_el = li.find('span', class_='elementor-price-list-price')
            desc_el = li.find('p', class_='elementor-price-list-description')

            # Also try div for description in case structure changed
            if not desc_el:
                desc_el = li.find('div', class_='elementor-price-list-description')

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