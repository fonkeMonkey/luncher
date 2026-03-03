"""Scraper for Spravovna restaurant."""

from datetime import date, datetime
from typing import Optional, List, Tuple
import requests
from bs4 import BeautifulSoup
from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('spravovna')
class SpravovnaScraper(BaseScraper):
    """Scraper for Spravovna restaurant (https://www.spravovna.cz/).

    Note: Spravovna does not publish their daily lunch menu on the website.
    The menu is distributed via email newsletter and Instagram.
    This scraper extracts any available drink recommendations from the page,
    and provides the Instagram link for the daily menu.
    """

    INSTAGRAM_URL = "https://www.instagram.com/restauracespravovna/"

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            items, raw_text = self._extract_available_items(soup)

            # If no items, indicate that the menu is on Instagram
            if not items:
                return self.create_error_menu(
                    target_date,
                    f"Menu zveřejněno na Instagramu: {self.INSTAGRAM_URL}"
                )

            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text=raw_text,
                scraped_at=datetime.now(),
                url=self.config.url
            )

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Chyba načítání: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    def _extract_available_items(self, soup: BeautifulSoup) -> Tuple[List[MenuItem], str]:
        """Extract any available items (e.g. drink recommendations)."""
        items = []
        raw_parts = []

        # Look for the "K POLEDNÍMU MENU DOPORUČUJEME" section
        for heading in soup.find_all(['h2', 'h3', 'h4', 'strong', 'p']):
            text = heading.get_text(strip=True).lower()
            if 'doporučujeme' in text or 'k polednímu' in text:
                # Extract items from the following section
                parent = heading.find_parent(['div', 'section'])
                if parent:
                    for item_div in parent.find_all('div', recursive=False):
                        name_el = item_div.find(['p', 'span', 'strong'])
                        price_els = item_div.find_all(['p', 'span'], string=lambda t: t and 'Kč' in str(t))
                        if name_el:
                            name = name_el.get_text(strip=True)
                            price_text = price_els[0].get_text(strip=True) if price_els else ''
                            if name and len(name) > 3 and 'Kč' not in name:
                                price = self.normalize_price(price_text)
                                raw_parts.append(f"{name} - {price_text}")
                                items.append(MenuItem(
                                    name=name,
                                    price=price,
                                    type=MenuItemType.OTHER
                                ))
                break

        return items, "\n".join(raw_parts)
