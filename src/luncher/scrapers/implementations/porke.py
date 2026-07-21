I need to analyze the HTML to understand the new structure. The HTML is cut off, but I can see the page no longer uses tabs with `tabid_238_1`. The navigation shows `#menu` as the anchor for "Polední Menu". I need to look for the lunch menu section and find what structure it uses now.

Since the HTML is truncated, I'll write a robust scraper that:
1. Tries to find the menu section by `id="menu"` anchor
2. Falls back to searching for Elementor price list widgets anywhere on the page
3. Handles the case where no tab click is needed (the menu might be directly visible)

```python
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
        # Strategy 1: find element with id="menu" directly
        panel = soup.find(id=self.MENU_ANCHOR)
        if panel and panel.find('li', class_='elementor-price-list-item'):
            return panel

        # Strategy 2: find a section that contains an anchor tag with name/id "menu"
        anchor = soup.find('a', attrs={'name': self.MENU_ANCHOR})
        if anchor:
            section = anchor.find_parent('section')
            if section and section.find('li', class_='elementor-price-list-item'):
                return section

        # Strategy 3: look for a heading containing "polední menu" text
        # and return its parent section
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']):
            text = heading.get_text(strip=True).lower()
            if 'polední' in text and 'menu' in text:
                section = heading.find_parent('section')
                if section and section.find('li', class_='elementor-price-list-item'):
                    return section

        # Strategy 4: find the first section containing price list items
        # that is most likely to be the lunch menu (check for lunch keywords nearby)
        lunch_keywords = ['polední', 'lunch', 'poledni', 'denní menu', 'denni menu']
        for section in soup.find_all('section'):
            section_text = section.get_text(strip=True).lower()
            has_price_items = bool(section.find('li', class_='elementor-price-list-item'))
            has_keyword = any(kw in section_text for kw in lunch_keywords)
            if has_price_items and has_keyword:
                return section

        # Strategy 5: fallback — return the first container with price list items
        for container in soup.find_all(['section', 'div']):
            if container.find('li', class_='elementor-price-list-item'):
                return container

        # Strategy 6: search entire document
        if soup.find('li', class_='elementor-price-list-item'):
            return soup

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
            if price == 49.0 or any(w in nl for w in ['polévka', 'vývar', 'krém', 'bramborová', 'soup']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek', 'desert']):
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
```