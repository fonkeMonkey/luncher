I need to analyze the HTML to understand the new structure. The HTML is truncated, but I can see the page no longer uses tabs with `a[href="#tabid_238_1"]` - instead it uses anchor links like `#menu`. Let me write a robust scraper that handles the new structure.

Looking at the HTML:
- No tab panel with `tabid_238_1` exists
- The menu section is anchored at `#menu`
- The page still uses Elementor widgets
- Need to find the lunch menu section by looking for the `#menu` section or nearby Elementor price list widgets

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

    The lunch menu is in a section with id="menu" or nearby anchor.
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

        # Strategy 1: Find element with id="menu"
        panel = soup.find(id=self.MENU_ANCHOR)
        if panel and panel.find('li', class_='elementor-price-list-item'):
            return panel

        # Strategy 2: Find a section containing an anchor tag with name/id "menu"
        anchor = soup.find('a', attrs={'name': self.MENU_ANCHOR})
        if anchor:
            section = anchor.find_parent('section')
            if section and section.find('li', class_='elementor-price-list-item'):
                return section

        # Strategy 3: Look for headings containing "polední menu" text
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']):
            text = heading.get_text(strip=True).lower()
            if 'polední menu' in text or 'poledni menu' in text or 'lunch' in text:
                # Walk up to find a section containing price list items
                parent = heading
                for _ in range(10):
                    parent = parent.find_parent()
                    if parent is None:
                        break
                    if parent.find('li', class_='elementor-price-list-item'):
                        return parent

        # Strategy 4: Find the first section/div that contains price list items
        # and appears to be a lunch menu (has soup-priced items or lunch keywords)
        all_price_list_sections = []
        for container in soup.find_all(['section', 'div']):
            items = container.find_all('li', class_='elementor-price-list-item')
            if len(items) >= 2:
                # Check if this looks like a lunch menu
                all_text = container.get_text(strip=True).lower()
                if any(w in all_text for w in ['polévka', 'polední', 'lunch', 'hlavní chod', 'soup']):
                    return container
                # Check price points typical of lunch menus (49, 159, 169, 179 Kč)
                prices = re.findall(r'\b(49|99|129|139|149|159|169|179|189)\b', all_text)
                if prices:
                    all_price_list_sections.append((len(items), container))

        if all_price_list_sections:
            # Return the section with the most price list items
            all_price_list_sections.sort(key=lambda x: x[0], reverse=True)
            return all_price_list_sections[0][1]

        # Strategy 5: Return the entire body and let _extract_items handle it
        return soup.find('body')

    def _extract_items(self, panel) -> Tuple[List[MenuItem], str]:
        """Extract items from Elementor price list widgets in the panel."""
        items = []
        raw_parts = []

        # Deduplicate: track already seen (name, price) pairs
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

            # Parse price
            price = None
            m = re.search(r'(\d+)', price_text)
            if m:
                price = float(m.group(1))

            # Deduplicate entries
            key = (name.lower(), price)
            if key in seen:
                continue
            seen.add(key)

            raw_parts.append(f"{name}{' - ' + description if description else ''} - {price_text}")

            # Soups have 49 Kč price or soup keywords
            nl = name.lower()
            if price == 49.0 or any(w in nl for w in ['polévka', 'vývar', 'krém', 'bramborová', 'soup']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek', 'dort', 'zmrzlin']):
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