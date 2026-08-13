"""Base scraper abstract class."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import re
from luncher.core.models import DailyMenu, MenuItem, MenuItemType, RestaurantConfig


class BaseScraper(ABC):
    """Abstract base class for restaurant scrapers."""

    def __init__(self, config: RestaurantConfig):
        """Initialize scraper with restaurant configuration."""
        self.config = config

    @abstractmethod
    async def scrape(self, target_date: Optional[date] = None) -> DailyMenu:
        """
        Scrape menu for the specified date.

        Args:
            target_date: Date to scrape menu for. Defaults to today.

        Returns:
            DailyMenu object with scraped data.
        """
        pass

    @staticmethod
    def clean_text(el) -> str:
        """Get text from a BeautifulSoup element with spaces between child elements."""
        text = el.get_text(separator=' ', strip=True)
        return re.sub(r'\s+', ' ', text).strip()

    def normalize_price(self, text: str) -> Optional[float]:
        """
        Extract price from text like '120 Kč', '120,-', or '120'.

        Args:
            text: Text containing price information.

        Returns:
            Price as float, or None if not found.
        """
        if not text:
            return None

        # Remove whitespace and convert to lowercase
        text = text.strip().lower()

        # Try to find number patterns
        # Matches: 120, 120,-, 120 kč, 120kč, etc.
        pattern = r'(\d+)(?:[,.-]?(?:\d+)?)?'
        match = re.search(pattern, text)

        if match:
            try:
                # Extract just the integer part
                price_str = match.group(1)
                return float(price_str)
            except ValueError:
                return None

        return None

    def get_czech_weekday_name(self, target_date: date) -> str:
        """
        Get Czech name for day of week.

        Args:
            target_date: Date to get weekday for.

        Returns:
            Czech weekday name in lowercase.
        """
        weekdays = {
            0: "pondělí",    # Monday
            1: "úterý",      # Tuesday
            2: "středa",     # Wednesday
            3: "čtvrtek",    # Thursday
            4: "pátek",      # Friday
            5: "sobota",     # Saturday
            6: "neděle"      # Sunday
        }
        return weekdays[target_date.weekday()]

    def create_error_menu(self, target_date: date, error_message: str) -> DailyMenu:
        """
        Create a DailyMenu object representing an error state.

        Args:
            target_date: Date the menu was requested for.
            error_message: Description of the error.

        Returns:
            DailyMenu with error field set.
        """
        return DailyMenu(
            restaurant_id=self.config.id,
            restaurant_name=self.config.name,
            date=target_date,
            items=[],
            raw_text="",
            scraped_at=datetime.now(),
            url=self.config.url,
            error=error_message
        )

    def create_closed_menu(self, target_date: date, message: str = "Zavřeno") -> DailyMenu:
        """
        Create a DailyMenu representing a day the restaurant has no menu (e.g. weekend).

        Unlike create_error_menu, this does NOT trigger the AI fallback in
        scrape_with_healing, since there's nothing wrong with the scraper.
        """
        return DailyMenu(
            restaurant_id=self.config.id,
            restaurant_name=self.config.name,
            date=target_date,
            items=[],
            raw_text="",
            scraped_at=datetime.now(),
            url=self.config.url,
            error=message,
            closed=True
        )

    async def get_html_for_fallback(self) -> str:
        """
        Fetch raw page HTML for AI fallback extraction.

        Override this in scrapers that require JavaScript rendering (e.g. Playwright).
        """
        response = self.get_with_retry(self.config.url)
        return response.text

    @staticmethod
    def get_with_retry(url: str, timeout: int = 30, retries: int = 3, backoff_seconds: tuple = (5, 15)):
        """
        GET a URL, retrying on connection/timeout errors before giving up.

        Some restaurant sites intermittently refuse/timeout connections from
        CI runners (e.g. rate limiting); a couple of short retries clears
        most of these without resorting to a proxy.
        """
        import time
        import requests

        last_exc = None
        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                last_exc = e
                if attempt < retries - 1:
                    time.sleep(backoff_seconds[min(attempt, len(backoff_seconds) - 1)])
        raise last_exc

    async def _ai_fallback_scrape(self, target_date: date, original_error: str) -> DailyMenu:
        """
        Use Claude AI to extract menu items when the normal scraper fails.

        Fetches the page HTML, strips noise, and asks Claude to return menu
        items as JSON. Falls back to the original error menu if AI also fails.
        """
        import json
        import logging
        logger = logging.getLogger(__name__)

        try:
            from luncher.config.settings import settings
            if not settings.anthropic_api_key:
                return self.create_error_menu(target_date, original_error)

            import anthropic
            from bs4 import BeautifulSoup

            html = await self.get_html_for_fallback()

            # Strip scripts/styles to reduce token count
            soup = BeautifulSoup(html, 'lxml')
            for tag in soup(['script', 'style', 'noscript', 'meta', 'link']):
                tag.decompose()
            clean_html = str(soup)[:15000]

            prompt = f"""Extract all lunch menu items from this Czech restaurant HTML page.
Return ONLY a JSON array. Each element: {{"name": "...", "description": "..." or null, "price": 120.0 or null, "type": "soup" | "main" | "dessert" | "other"}}
Identify soups by keywords: polévka, vývar, krém. Desserts: dezert, moučník, zákusek.

HTML:
{clean_html}

Return ONLY the JSON array, no other text."""

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )

            # Save HTML so the healer can use it later to generate a code fix
            try:
                Path(f"/tmp/luncher_fallback_{self.config.id}.html").write_text(html, encoding="utf-8")
            except Exception:
                pass

            raw_response = message.content[0].text.strip()
            # Strip markdown code fences if Claude wrapped the JSON
            if raw_response.startswith("```"):
                raw_response = re.sub(r'^```(?:json)?\s*', '', raw_response)
                raw_response = re.sub(r'\s*```$', '', raw_response).strip()
            items_data = json.loads(raw_response)

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
                    type=item_type
                ))

            if not items:
                return self.create_error_menu(target_date, original_error)

            logger.info("AI fallback extracted %d items for %s", len(items), self.config.id)
            return DailyMenu(
                restaurant_id=self.config.id,
                restaurant_name=self.config.name,
                date=target_date,
                items=items,
                raw_text=f"[AI fallback] {raw_response[:500]}",
                scraped_at=datetime.now(),
                url=self.config.url
            )

        except Exception as e:
            logger.error("AI fallback failed for %s: %s", self.config.id, e)
            return self.create_error_menu(target_date, original_error)

    async def scrape_with_healing(self, target_date: Optional[date] = None) -> DailyMenu:
        """
        Scrape with AI self-healing fallback.

        Runs the normal scraper first. If it returns an error or zero items,
        automatically retries using Claude AI to extract the menu from raw HTML.
        """
        import logging
        if target_date is None:
            target_date = date.today()

        menu = await self.scrape(target_date)

        if not menu.is_valid and not menu.closed:
            logging.getLogger(__name__).warning(
                "Scraper failed for %s (%s), trying AI fallback",
                self.config.id, menu.error
            )
            menu = await self._ai_fallback_scrape(target_date, menu.error or "No items found")

        return menu
