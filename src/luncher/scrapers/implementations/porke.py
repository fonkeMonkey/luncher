I need to analyze the HTML to understand the new structure. The HTML is truncated, but I can see:

1. The navigation links to `#menu` for "Polední Menu" (not a tab with `tabid_238_1`)
2. The old tab system (`tabid_238_1`) is gone
3. The page uses anchor-based navigation with `id="menu"` section

I need to find the lunch menu section by looking for the `#menu` anchor section and then find price list items within it. Since the HTML is truncated, I'll update the scraper to:
1. Navigate to the `#menu` anchor section instead of clicking a tab
2. Look for the section with `id="menu"` 
3. Keep the Elementor price list widget selectors as they likely remain the same
4. Add fallback strategies if the panel isn't found by id

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

    The lunch menu is in a section anchored at #menu.
    Items use Elementor price list widgets:
      ul.elementor-price-list > li.elementor-price-list-item
        span.elementor-price-list-title   — item name
        span.elementor-price-list-price   — price (e.g. "179 Kč")
        p.elementor-price-list-description — optional description
    Soups are identified by price 49 Kč or keywords in the name.
    """

    MENU_ANCHOR = '#menu'

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
        # Strategy 1: Look for section with id="menu"
        panel = soup.find(id='menu')
        if panel and panel.find('li', class_='elementor-price-list-item'):
            return panel

        # Strategy 2: Look for old tab panel id
        panel = soup.find(id='tabid_238_1')
        if panel and panel.find('li', class_='elementor-price-list-item'):
            return panel

        # Strategy 3: Find a section containing "polední menu" heading text
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']):
            text = heading.get_text(strip=True).lower()
            if 'polední menu' in text or 'poledni menu' in text:
                # Walk up to find a section/div ancestor that contains price list items
                for ancestor in heading.parents:
                    if ancestor.name in ('section', 'div', 'article'):
                        if ancestor.find('li', class_='elementor-price-list-item'):
                            return ancestor

        # Strategy 4: Find any elementor section containing price list items
        # that also contains lunch-related keywords nearby
        for section in soup.find_all('section', class_='elementor-section'):
            price_items = section.find_all('li', class_='elementor-price-list-item')
            if not price_items:
                continue
            section_text = section.get_text(strip=True).lower()
            if any(kw in section_text for kw in ['polévka', 'soup', 'polední', 'lunch', 'menu']):
                return section

        # Strategy 5: Return the first container that has price list items
        for container in soup.find_all(['section', 'div']):
            if container.find('li', class_='elementor-price-list-item'):
                return container

        return None

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
            if price == 49.0 or any(w in nl for w in ['polévka', 'vývar', 'krém', 'bramborová', 'gulášová', 'hovězí', 'zeleninová', 'čočková', 'česnečka']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek', 'dort', 'zmrzlina']):
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