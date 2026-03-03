"""Scraper registry for automatic discovery and instantiation."""

from typing import Dict, Type, Optional
import importlib
from luncher.scrapers.base import BaseScraper
from luncher.core.models import RestaurantConfig


class ScraperRegistry:
    """Registry for managing scraper classes."""

    _scrapers: Dict[str, Type[BaseScraper]] = {}

    @classmethod
    def register(cls, name: str):
        """
        Decorator to register a scraper class.

        Usage:
            @ScraperRegistry.register('restaurant_id')
            class RestaurantScraper(BaseScraper):
                ...
        """
        def wrapper(scraper_class: Type[BaseScraper]):
            cls._scrapers[name] = scraper_class
            return scraper_class
        return wrapper

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseScraper]]:
        """Get a scraper class by name."""
        return cls._scrapers.get(name)

    @classmethod
    def create(cls, config: RestaurantConfig) -> BaseScraper:
        """
        Create a scraper instance from configuration.

        Args:
            config: Restaurant configuration.

        Returns:
            Instantiated scraper.

        Raises:
            ValueError: If scraper class not found.
        """
        # Try to get from registry first
        scraper_class = cls.get(config.id)

        if not scraper_class:
            # Try to dynamically import the scraper class
            try:
                module_path, class_name = config.scraper_class.rsplit('.', 1)
                module = importlib.import_module(module_path)
                scraper_class = getattr(module, class_name)
            except (ImportError, AttributeError, ValueError) as e:
                raise ValueError(
                    f"Could not load scraper class '{config.scraper_class}' "
                    f"for restaurant '{config.id}': {e}"
                )

        return scraper_class(config)

    @classmethod
    def list_scrapers(cls) -> Dict[str, Type[BaseScraper]]:
        """Get all registered scrapers."""
        return cls._scrapers.copy()
