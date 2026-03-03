"""Application settings and configuration loading."""

import os
from pathlib import Path
from typing import List, Optional
import yaml
from dotenv import load_dotenv
from luncher.core.models import RestaurantConfig

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings."""

    def __init__(self):
        # API Keys
        self.anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")

        # Cache settings
        self.cache_ttl_hours: int = int(os.getenv("CACHE_TTL_HOURS", "4"))
        cache_dir = os.getenv("CACHE_DIR", "~/.luncher/cache")
        self.cache_dir: Path = Path(cache_dir).expanduser()

        # Web server settings
        self.web_host: str = os.getenv("WEB_HOST", "0.0.0.0")
        self.web_port: int = int(os.getenv("WEB_PORT", "8000"))

        # Project paths
        self.project_root: Path = Path(__file__).parent.parent
        self.config_dir: Path = Path(__file__).parent

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_restaurants(self) -> List[RestaurantConfig]:
        """Load restaurant configurations from YAML file."""
        config_file = self.config_dir / "restaurants.yaml"

        if not config_file.exists():
            raise FileNotFoundError(f"Restaurant config not found: {config_file}")

        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        restaurants = []
        for resto_data in data.get("restaurants", []):
            restaurants.append(RestaurantConfig(**resto_data))

        return restaurants

    def get_enabled_restaurants(self) -> List[RestaurantConfig]:
        """Get only enabled restaurants."""
        return [r for r in self.load_restaurants() if r.enabled]


# Global settings instance
settings = Settings()
