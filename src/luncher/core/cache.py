"""File-based caching layer for menu data."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from luncher.core.models import DailyMenu, MenuItem, MenuItemType
from luncher.config.settings import settings


class MenuCache:
    """File-based cache for daily menus."""

    def __init__(self, cache_dir: Optional[Path] = None, ttl_hours: Optional[int] = None):
        """Initialize cache with directory and TTL settings."""
        self.cache_dir = cache_dir or settings.cache_dir
        self.ttl_hours = ttl_hours or settings.cache_ttl_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, restaurant_id: str, menu_date: date) -> Path:
        """Generate cache file path for a specific restaurant and date."""
        filename = f"{restaurant_id}_{menu_date.isoformat()}.json"
        return self.cache_dir / filename

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file exists and is within TTL."""
        if not cache_path.exists():
            return False

        file_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        age = datetime.now() - file_mtime
        return age < timedelta(hours=self.ttl_hours)

    def get(self, restaurant_id: str, menu_date: date) -> Optional[DailyMenu]:
        """Retrieve cached menu if valid."""
        cache_path = self._get_cache_path(restaurant_id, menu_date)

        if not self._is_cache_valid(cache_path):
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruct DailyMenu from JSON
            items = [
                MenuItem(
                    name=item["name"],
                    description=item.get("description"),
                    price=item.get("price"),
                    type=MenuItemType(item.get("type", "other"))
                )
                for item in data["items"]
            ]

            return DailyMenu(
                restaurant_id=data["restaurant_id"],
                restaurant_name=data["restaurant_name"],
                date=date.fromisoformat(data["date"]),
                items=items,
                raw_text=data["raw_text"],
                scraped_at=datetime.fromisoformat(data["scraped_at"]),
                url=data["url"],
                error=data.get("error")
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Cache corrupted, ignore it
            return None

    def set(self, menu: DailyMenu) -> None:
        """Save menu to cache."""
        cache_path = self._get_cache_path(menu.restaurant_id, menu.date)

        # Convert DailyMenu to JSON-serializable dict
        data = {
            "restaurant_id": menu.restaurant_id,
            "restaurant_name": menu.restaurant_name,
            "date": menu.date.isoformat(),
            "items": [
                {
                    "name": item.name,
                    "description": item.description,
                    "price": item.price,
                    "type": item.type.value
                }
                for item in menu.items
            ],
            "raw_text": menu.raw_text,
            "scraped_at": menu.scraped_at.isoformat(),
            "url": menu.url,
            "error": menu.error
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear(self, restaurant_id: Optional[str] = None, menu_date: Optional[date] = None) -> int:
        """Clear cache. Returns number of files deleted."""
        if restaurant_id and menu_date:
            # Clear specific cache file
            cache_path = self._get_cache_path(restaurant_id, menu_date)
            if cache_path.exists():
                cache_path.unlink()
                return 1
            return 0

        # Clear all cache files
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        return count
