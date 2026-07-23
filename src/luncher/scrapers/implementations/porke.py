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
    The page no longer uses a tab panel with tabid_238_1.
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

            panel = self._find_menu_section(soup)
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

    def _find_menu_section(self, soup):
        """Find the lunch menu section in the page.

        Tries multiple strategies to locate the section containing
        the Elementor price list items for the lunch menu:
        1. Look for an element with id="menu" (the anchor used in the nav).
        2. Look for a section that contains price list items and a heading
           with polední/lunch keywords.
        3. Fall back to the first container that has any price list items.
        """
        # Strategy 1: direct id="menu" anchor element or nearby section
        menu_anchor = soup.find(id=self.MENU_ANCHOR)
        if menu_anchor:
            # Check if the anchor itself or its parent section has price list items
            candidate = menu_anchor
            for _ in range(5):
                if candidate.find('li', class_='elementor-price-list-item'):
                    return candidate
                parent = candidate.parent
                if parent is None:
                    break
                candidate = parent
            # If not found by walking up, search siblings and descendants of the anchor's section
            section = menu_anchor.find_parent('section')
            if section and section.find('li', class_='elementor-price-list-item'):
                return section

        # Strategy 2: find a section/div that contains a heading with lunch keywords
        # and also contains price list items
        lunch_keywords = ['polední', 'lunch', 'poledni', 'denní menu', 'denni menu']
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']):
            text = heading.get_text(strip=True).lower()
            if any(kw in text for kw in lunch_keywords):
                # Walk up to find a container with price list items
                candidate = heading
                for _ in range(8):
                    if candidate.find('li', class_='elementor-price-list-item'):
                        return candidate
                    parent = candidate.parent
                    if parent is None:
                        break
                    candidate = parent

        # Strategy 3: find the elementor section that appears earliest after #menu anchor
        # by looking at all sections with price list items
        sections_with_items = []
        for section in soup.find_all(['section', 'div'], class_=re.compile(r'elementor-section|elementor-widget')):
            items = section.find_all('li', class_='elementor-price-list-item')
            if items:
                sections_with_items.append((section, len(items)))

        if sections_with_items:
            # Prefer the section with the most items (likely the full menu)
            sections_with_items.sort(key=lambda x: x[1], reverse=True)
            return sections_with_items[0][0]

        # Strategy 4: absolute fallback — return entire body if there are any price list items
        body = soup.find('body')
        if body and body.find('li', class_='elementor-price-list-item'):
            return body

        return None

    def _extract_items(self, panel) -> Tuple[List[MenuItem], str]:
        """Extract items from Elementor price list widgets in the panel."""
        items = []
        raw_parts = []

        seen = set()

        for li in panel.find_all('li', class_='elementor-price-list-item'):
            title_el = li.find('span', class_='elementor-price-list-title')
            price_el = li.find('span', class_='elementor-price-list-price')
            desc_el = li.find('p', class_='elementor-price-list-description')

            name = self.clean_text(title_el) if title_el else ''
            price_text = self.clean_text(price_el) if price_el else ''
            description = self.clean_text(desc_el) if desc_el else None

            if not name:
                continue

            # Deduplicate
            key = (name, price_text)
            if key in seen:
                continue
            seen.add(key)

            # Parse price
            price = None
            m = re.search(r'(\d+)', price_text)
            if m:
                price = float(m.group(1))

            raw_parts.append(f"{name}{' - ' + description if description else ''} - {price_text}")

            # Soups have 49 Kč price or soup keywords
            nl = name.lower()
            if price == 49.0 or any(w in nl for w in ['polévka', 'vývar', 'krém', 'bramborová', 'gulášová', 'česnečka']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek', 'dort', 'tiramisu']):
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