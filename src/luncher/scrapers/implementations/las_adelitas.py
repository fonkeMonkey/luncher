"""Scraper for Las Adelitas restaurant."""

import base64
import json
import re
import requests

from datetime import date, datetime
from typing import Optional, List, Tuple

from bs4 import BeautifulSoup

from luncher.scrapers.base import BaseScraper
from luncher.scrapers.registry import ScraperRegistry
from luncher.core.models import DailyMenu, MenuItem, MenuItemType


@ScraperRegistry.register('las_adelitas')
class LasAdelitasScraper(BaseScraper):
    """Scraper for Las Adelitas Vinohrady (https://www.lasadelitas.cz/denni-menu/).

    The lunch menu is published as a daily PNG image (e.g. /data/files/DM_May3_26.png).
    This scraper:
      1. Fetches the menu page to find the current image URL.
      2. Downloads the image.
      3. Sends it to Claude's vision API to extract menu items as JSON.
    """

    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        if target_date is None:
            target_date = date.today()

        try:
            from luncher.config.settings import settings
            if not settings.anthropic_api_key:
                return self.create_error_menu(target_date, "Chybí ANTHROPIC_API_KEY")

            # Step 1: find image URL
            response = requests.get(self.config.url, timeout=30)
            response.raise_for_status()

            image_url = self._find_menu_image_url(response.text)
            if not image_url:
                return self.create_error_menu(target_date, "Nepodařilo se najít obrázek denního menu na stránce")

            # Step 2: download image
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()

            image_b64 = base64.standard_b64encode(img_response.content).decode("utf-8")
            media_type = "image/jpeg" if image_url.lower().endswith(('.jpg', '.jpeg')) else "image/png"

            # Step 3: extract menu items via Claude vision
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extrahuj všechny položky z tohoto obrázku denního menu českého restaurantu.\n"
                                'Vrať POUZE JSON pole. Každý element: {"name": "...", "description": "..." nebo null, "price": 120.0 nebo null, "type": "soup" | "main" | "dessert" | "other"}\n'
                                "Polévky identifikuj podle slov: polévka, vývar, krém. Dezerty: dezert, moučník, zákusek.\n"
                                "Vrať POUZE JSON pole, bez dalšího textu."
                            ),
                        },
                    ],
                }]
            )

            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r'^```(?:json)?\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw).strip()

            items_data = json.loads(raw)
            items = self._parse_items(items_data)

            if not items:
                return self.create_error_menu(target_date, "Nepodařilo se extrahovat položky menu z obrázku")

            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text=raw[:500],
                scraped_at=datetime.now(),
                url=self.config.url,
            )

        except requests.RequestException as e:
            return self.create_error_menu(target_date, f"Chyba načítání: {e}")
        except (json.JSONDecodeError, ValueError) as e:
            return self.create_error_menu(target_date, f"Chyba parsování odpovědi: {e}")
        except Exception as e:
            return self.create_error_menu(target_date, f"Chyba scrapování: {e}")

    def _find_menu_image_url(self, html: str) -> Optional[str]:
        """Find the daily menu image URL from the page HTML."""
        soup = BeautifulSoup(html, 'lxml')

        # Look for the anchor tag with class 'mfp-img' that wraps the menu image
        for a_tag in soup.find_all('a', class_='mfp-img'):
            href = a_tag.get('href', '')
            if '/data/files/' in href:
                if href.startswith('http'):
                    return href
                return f"https://www.lasadelitas.cz{href}"

        # Fallback: look for img tags whose src contains /data/files/ inside #menu section
        menu_section = soup.find(id='menu')
        if menu_section:
            for img in menu_section.find_all('img'):
                src = img.get('src', '')
                if '/data/files/' in src:
                    if src.startswith('http'):
                        return src
                    return f"https://www.lasadelitas.cz{src}"

        # Final fallback: search all img tags for /data/files/ path,
        # excluding known non-menu images (logos, theme assets)
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if '/data/files/' in src and '/data/themes/' not in src:
                if src.startswith('http'):
                    return src
                return f"https://www.lasadelitas.cz{src}"

        return None

    def _parse_items(self, items_data: list) -> List[MenuItem]:
        """Convert raw JSON dicts from Claude into MenuItem objects."""
        items = []
        for item_data in items_data:
            name = item_data.get('name', '').strip()
            if not name:
                continue
            try:
                item_type = MenuItemType(item_data.get('type', 'other'))
            except ValueError:
                item_type = MenuItemType.OTHER
            items.append(MenuItem(
                name=name,
                description=item_data.get('description') or None,
                price=item_data.get('price'),
                type=item_type,
            ))
        return items