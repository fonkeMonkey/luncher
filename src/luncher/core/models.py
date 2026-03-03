"""Data models for lunch menus and restaurants."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional
from enum import Enum


class MenuItemType(str, Enum):
    """Types of menu items."""
    SOUP = "soup"
    MAIN = "main"
    SIDE = "side"
    DESSERT = "dessert"
    OTHER = "other"


@dataclass
class MenuItem:
    """Represents a single item on a menu."""
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    type: MenuItemType = MenuItemType.OTHER

    def __str__(self) -> str:
        parts = [self.name]
        if self.description:
            parts.append(f"({self.description})")
        if self.price:
            parts.append(f"- {self.price} Kč")
        return " ".join(parts)


@dataclass
class DailyMenu:
    """Represents a complete daily menu from a restaurant."""
    restaurant_id: str
    restaurant_name: str
    date: date
    items: List[MenuItem]
    raw_text: str
    scraped_at: datetime
    url: str
    error: Optional[str] = None

    def __post_init__(self):
        """Ensure items is a list."""
        if not isinstance(self.items, list):
            self.items = []

    @property
    def is_valid(self) -> bool:
        """Check if menu was successfully scraped."""
        return self.error is None and len(self.items) > 0

    def get_items_by_type(self, item_type: MenuItemType) -> List[MenuItem]:
        """Get all items of a specific type."""
        return [item for item in self.items if item.type == item_type]


@dataclass
class RestaurantConfig:
    """Configuration for a restaurant."""
    id: str
    name: str
    url: str
    scraper_class: str
    enabled: bool = True

    def __post_init__(self):
        """Validate configuration."""
        if not self.id or not self.name or not self.url:
            raise ValueError("Restaurant config requires id, name, and url")
