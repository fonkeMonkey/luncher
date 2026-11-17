"""Scraper for Chilli & Lime restaurant."""

from datetime import date, datetime
from typing import Optional, List, Tuple
import json
import re
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('chilli_lime')
class ChilliLimeScraper(BaseScraper):
    """Scraper for Chilli & Lime restaurant (https://chilliandlime.choiceqr.com/online-menu).

    The page is a Next.js app. The __NEXT_DATA__ script tag no longer contains
    the full menu in props.app. Instead the menu data is loaded client-side via
    the choiceqr API. We therefore fall back to:

      1. Try the __NEXT_DATA__ path (props.pageProps or props.app) in case it
         ever comes back.
      2. Call the choiceqr REST API directly:
           GET https://api.choiceqr.com/v2/app/<place_hurl>
         which returns JSON with categories and menu arrays identical to the
         old __NEXT_DATA__ shape.
      3. As a last resort, parse the rendered HTML for the section whose
         heading is "POLEDNÍ MENU" and read item titles/prices from the DOM.

    Structure returned by the API:
      {
        "categories": [{"_id": "...", "name": "...", "hurl": "..."}, ...],
        "menu": [{"_id": "...", "name": "...", "description": "...",
                  "price": <int halíře>, "category": "<cat_id>"}, ...]
      }
    """

    # Public choiceqr REST API – place slug is the subdomain of the site URL.
    _API_URL_TEMPLATE = "https://api.choiceqr.com/v2/app/{place}"
    # Fallback: extract place slug from config url automatically.

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, 'lxml')

            # --- Strategy 1: __NEXT_DATA__ JSON blob ---
            app = self._try_next_data(soup)
            if app and app.get('menu'):
                return self._build_menu(app, target_date)

            # --- Strategy 2: direct choiceqr API call ---
            app = self._try_api(self.config.url)
            if app and app.get('menu'):
                return self._build_menu(app, target_date)

            # --- Strategy 3: parse rendered HTML ---
            items, raw_text = self._parse_html(soup)
            if items:
                return DailyMenu(
                    restaurant_id=self.config.id,
                    restaurant_name=self.config.name,
                    date=target_date,
                    items=items,
                    raw_text=raw_text,
                    scraped_at=datetime.now(),
                    url=self.config.url,
                )

            return self.create_error_menu(target_date, "Nepodařilo se najít data menu")

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Chyba načítání: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            return self.create_error_menu(target_date, f"Chyba parsování JSON: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    # ------------------------------------------------------------------
    # Strategy helpers
    # ------------------------------------------------------------------

    def _try_next_data(self, soup: BeautifulSoup) -> Optional[dict]:
        """Try to extract app data from the __NEXT_DATA__ script tag."""
        script = soup.find('script', id='__NEXT_DATA__')
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None

        props = data.get('props', {})
        # Old shape: props.app
        if props.get('app', {}).get('menu'):
            return props['app']
        # Alternative shape: props.pageProps.app
        if props.get('pageProps', {}).get('app', {}).get('menu'):
            return props['pageProps']['app']
        # Another alternative: props.pageProps directly
        if props.get('pageProps', {}).get('menu'):
            return props['pageProps']
        return None

    def _try_api(self, page_url: str) -> Optional[dict]:
        """Call the choiceqr v2 API to get the full app/menu JSON."""
        place = self._extract_place_slug(page_url)
        if not place:
            return None
        api_url = self._API_URL_TEMPLATE.format(place=place)
        try:
            resp = requests.get(api_url, timeout=20, headers={
                'Accept': 'application/json',
                'Referer': page_url,
            })
            if resp.status_code != 200:
                return None
            data = resp.json()
            # The API may return the app object directly or wrapped
            if isinstance(data, dict):
                if data.get('menu'):
                    return data
                if data.get('app', {}).get('menu'):
                    return data['app']
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_place_slug(url: str) -> Optional[str]:
        """Extract the place slug (subdomain) from a choiceqr URL.

        e.g. https://chilliandlime.choiceqr.com/... -> 'chilliandlime'
        """
        m = re.search(r'https?://([^.]+)\.choiceqr\.com', url)
        if m:
            return m.group(1)
        return None

    # ------------------------------------------------------------------
    # Building DailyMenu from app dict (categories + menu arrays)
    # ------------------------------------------------------------------

    def _build_menu(self, app: dict, target_date: date) -> DailyMenu:
        cat_id = self._find_lunch_category_id(app)
        items, raw_text = self._extract_items(app, cat_id) if cat_id else ([], "")
        return DailyMenu(
            restaurant_id=self.config.id,
            restaurant_name=self.config.name,
            date=target_date,
            items=items,
            raw_text=raw_text,
            scraped_at=datetime.now(),
            url=self.config.url,
        )

    def _find_lunch_category_id(self, app: dict) -> Optional[str]:
        """Find the lunch menu category ID."""
        for cat in app.get('categories', []):
            hurl = cat.get('hurl', '').lower()
            name = cat.get('name', '').upper()
            if ('poledni' in hurl or 'obed' in hurl
                    or 'POLEDNÍ' in name.upper() or 'POLEDNI' in hurl
                    or 'LUNCH' in name):
                return cat['_id']
        # Fallback: first category
        cats = app.get('categories', [])
        return cats[0]['_id'] if cats else None

    def _extract_items(self, app: dict, cat_id: str) -> Tuple[List[MenuItem], str]:
        """Extract items belonging to the lunch category."""
        items: List[MenuItem] = []
        raw_parts: List[str] = []

        for item in app.get('menu', []):
            if item.get('category') != cat_id:
                continue

            name = item.get('name', '').strip()
            description = (item.get('description') or '').strip()
            price_raw = item.get('price', 0)
            price = float(price_raw) / 100 if price_raw else None

            if not name:
                continue

            raw_parts.append(
                f"{name}{' - ' + description if description else ''}"
                f"{' - ' + str(price) + ' Kč' if price else ''}"
            )

            nl = name.lower()
            if any(w in nl for w in ['polévka', 'soup', 'vývar']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'dessert']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            # For the generic soup label, use description as the actual name
            if item_type == MenuItemType.SOUP and description and 'polední' in nl:
                name = description
                description = ''

            items.append(MenuItem(
                name=name,
                description=description or None,
                price=price,
                type=item_type,
            ))

        return items, "\n".join(raw_parts)

    # ------------------------------------------------------------------
    # Strategy 3: parse rendered HTML
    # ------------------------------------------------------------------

    def _parse_html(self, soup: BeautifulSoup) -> Tuple[List[MenuItem], str]:
        """Parse the server-rendered HTML for POLEDNÍ MENU items.

        The page renders a section with id="section-<cat_id>" whose heading
        contains "POLEDNÍ MENU". Within it each menu item lives in a div with
        class containing 'menuItem' and has child elements for title and price.
        """
        items: List[MenuItem] = []
        raw_parts: List[str] = []

        # Find the section div whose title is "POLEDNÍ MENU"
        section_div = None
        for div in soup.find_all('div', class_=re.compile(r'sectionTitle|DefaultView_sectionTitle')):
            if 'polední menu' in div.get_text(strip=True).lower():
                # Walk up to the section container
                section_div = div.find_parent('div', id=re.compile(r'^section-'))
                break

        if section_div is None:
            # Broader fallback: look for any div whose id starts with 'section-'
            for div in soup.find_all('div', id=re.compile(r'^section-')):
                heading = div.find(class_=re.compile(r'sectionTitle'))
                if heading and 'polední menu' in heading.get_text(strip=True).lower():
                    section_div = div
                    break

        if section_div is None:
            return items, ""

        # Iterate over menu item containers
        for item_div in section_div.find_all('div', class_=re.compile(r'menuItem__')):
            # Title
            title_el = item_div.find(class_=re.compile(r'menuItemTitle'))
            name = title_el.get_text(strip=True) if title_el else ''
            if not name:
                continue

            # Description
            desc_el = item_div.find(class_=re.compile(r'menuItemDescription'))
            description = desc_el.get_text(separator=' ', strip=True) if desc_el else ''

            # Price – look for text matching digits + optional space + Kč
            price: Optional[float] = None
            price_el = item_div.find(class_=re.compile(r'menuItemPrice'))
            if price_el:
                price_text = price_el.get_text(strip=True)
                m = re.search(r'(\d[\d\s]*(?:[.,]\d+)?)\s*Kč', price_text)
                if m:
                    price = float(m.group(1).replace('\xa0', '').replace(' ', '').replace(',', '.'))

            raw_parts.append(
                f"{name}{' - ' + description if description else ''}"
                f"{' - ' + str(price) + ' Kč' if price else ''}"
            )

            nl = name.lower()
            if any(w in nl for w in ['polévka', 'soup', 'vývar']):
                item_type = MenuItemType.SOUP
            elif any(w in nl for w in ['dezert', 'dessert']):
                item_type = MenuItemType.DESSERT
            else:
                item_type = MenuItemType.MAIN

            if item_type == MenuItemType.SOUP and description and 'polední' in nl:
                name = description
                description = ''

            items.append(MenuItem(
                name=name,
                description=description or None,
                price=price,
                type=item_type,
            ))

        return items, "\n".join(raw_parts)