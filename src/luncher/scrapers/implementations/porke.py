Looking at the HTML, I can see the page no longer uses tabs with `tabid_238_1`. The navigation now links to `#menu` anchor. I need to analyze the HTML structure more carefully to find where the lunch menu content is. The HTML is truncated, but based on what's visible, the site now uses anchor-based navigation (`#menu`) instead of tab panels. I'll update the scraper to look for the menu section by the `#menu` anchor, and make it more resilient by trying multiple strategies to find price list items anywhere on the page.

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

    The lunch menu is in a section reachable via the #menu anchor.
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

                # Try clicking any lunch menu tab/link if present
                for selector in [
                    'a[href="#menu"]',
                    'a[href="#tabid_238_1"]',
                    'a:has-text("Polední")',
                    'a:has-text("POLEDNÍ")',
                ]:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            await elem.click()
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        pass

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
        """Try multiple strategies to locate the lunch menu section."""
        # Strategy 1: old tab panel by id
        panel = soup.find(id='tabid_238_1')
        if panel and panel.find('li', class_='elementor-price-list-item'):
            return panel

        # Strategy 2: section with id="menu" anchor
        panel = soup.find(id=self.MENU_ANCHOR)
        if panel and panel.find('li', class_='elementor-price-list-item'):
            return panel

        # Strategy 3: look for a heading containing "Polední" and return its parent section
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']):
            text = heading.get_text(strip=True).lower()
            if 'polední' in text or 'poledni' in text or 'lunch' in text:
                # Walk up to find a section/div that contains price list items
                parent = heading.parent
                for _ in range(8):
                    if parent is None:
                        break
                    if parent.find('li', class_='elementor-price-list-item'):
                        return parent
                    parent = parent.parent

        # Strategy 4: find the first elementor section that contains price list items
        # and is closest to a "Polední menu" heading in document order
        all_price_sections = []
        for section in soup.find_all(['section', 'div'], class_=re.compile(r'elementor-(section|widget)')):
            items = section.find_all('li', class_='elementor-price-list-item')
            if items:
                all_price_sections.append(section)

        if all_price_sections:
            # Prefer sections that contain soup-priced items (49 Kč) or lunch keywords
            for section in all_price_sections:
                text = section.get_text(separator=' ', strip=True).lower()
                if any(w in text for w in ['polévka', 'vývar', 'polední', '49']):
                    return section
            # Fall back to first section with price list items
            return all_price_sections[0]

        # Strategy 5: return whole body if price list items exist anywhere
        if soup.find('li', class_='elementor-price-list-item'):
            return soup

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

            # Classify item type
            nl = name.lower()
            if price == 49.0 or any(w in nl for w in ['polévka', 'vývar', 'krém', 'bramborová', 'consommé', 'bisque', 'minestrone']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'moučník', 'zákusek', 'dort', 'zmrzlina', 'panna cotta', 'tiramisu']):
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