"""FastAPI web application for luncher."""

import asyncio
from datetime import date
from pathlib import Path
from typing import List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from luncher.config.settings import settings
from luncher.core.cache import MenuCache
from luncher.core.ai import MenuAIProcessor
from luncher.core.models import DailyMenu
from luncher.scrapers.registry import ScraperRegistry

app = FastAPI(
    title="Luncher",
    description="Daily lunch menu aggregator for Czech restaurants",
    version="0.1.0"
)

# Setup templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


async def fetch_menu(restaurant_config, use_cache: bool = True) -> DailyMenu:
    """Fetch menu for a single restaurant."""
    cache = MenuCache()

    # Try cache first
    if use_cache:
        cached_menu = cache.get(restaurant_config.id, date.today())
        if cached_menu:
            return cached_menu

    # Scrape fresh data
    try:
        scraper = ScraperRegistry.create(restaurant_config)
        menu = await scraper.scrape()

        # Cache the result
        if use_cache:
            cache.set(menu)

        return menu
    except Exception as e:
        # Return error menu
        from luncher.scrapers.base import BaseScraper
        base_scraper = BaseScraper(restaurant_config)
        import logging
        logging.getLogger(__name__).error("Failed to fetch menu for %s: %s", restaurant_config.id, e)
        return base_scraper.create_error_menu(date.today(), "Nepodařilo se načíst menu")


async def fetch_all_menus(use_cache: bool = True) -> List[DailyMenu]:
    """Fetch menus from all enabled restaurants."""
    restaurants = settings.get_enabled_restaurants()

    # Fetch all menus concurrently
    tasks = [fetch_menu(resto, use_cache) for resto in restaurants]
    menus = await asyncio.gather(*tasks)

    return list(menus)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page showing all menus."""
    menus = await fetch_all_menus()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "menus": menus,
            "today": date.today(),
        }
    )


@app.get("/api/menus/today")
async def get_today_menus(no_cache: bool = False):
    """API endpoint to get today's menus as JSON."""
    menus = await fetch_all_menus(use_cache=not no_cache)

    return JSONResponse([
        {
            "restaurant_id": menu.restaurant_id,
            "restaurant_name": menu.restaurant_name,
            "date": menu.date.isoformat(),
            "url": menu.url,
            "is_valid": menu.is_valid,
            "error": menu.error,
            "items": [
                {
                    "name": item.name,
                    "description": item.description,
                    "price": item.price,
                    "type": item.type.value
                }
                for item in menu.items
            ]
        }
        for menu in menus
    ])


@app.get("/api/compare")
async def compare_menus():
    """API endpoint to get AI comparison of menus."""
    menus = await fetch_all_menus()

    try:
        ai = MenuAIProcessor()
        comparison = await ai.compare_menus(menus)
        return {"comparison": comparison}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("AI comparison failed: %s", e)
        return JSONResponse(
            {"error": "AI analýza není momentálně dostupná"},
            status_code=503
        )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.web_host, port=settings.web_port)
