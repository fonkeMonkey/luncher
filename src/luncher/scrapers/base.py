"""Base scraper abstract class."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional
import re
from luncher.core.models import DailyMenu, RestaurantConfig


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
