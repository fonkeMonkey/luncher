# 🍽️ Luncher

Daily lunch menu aggregator for Czech restaurants. Fetches menus from multiple restaurants, displays them in a beautiful CLI or web interface, and uses Claude AI to provide intelligent recommendations.

## Features

- 📱 **5 Restaurant Support**: Chilli & Lime, U Telleru, Spravovna, Pub Na Plech, PORKE
- 💨 **Smart Caching**: 4-hour cache to avoid repeated scraping
- 🎨 **Beautiful CLI**: Rich terminal output with tables and colors
- 🌐 **Web Interface**: Clean, responsive web UI
- 🤖 **AI-Powered**: Claude AI provides menu summaries and recommendations in Czech
- 🔌 **Extensible**: Easy to add new restaurants

## Installation

### Prerequisites

- Python 3.12 or higher
- pip

### Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd luncher
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers** (needed for PORKE scraper):
   ```bash
   playwright install chromium
   ```

5. **Configure API key**:
   ```bash
   cp .env.example .env
   # Edit .env and add your Anthropic API key
   ```

   Get your API key from: https://console.anthropic.com/

6. **Install the package**:
   ```bash
   pip install -e .
   ```

## Usage

### CLI Commands

#### Show all today's menus
```bash
luncher today
```

#### Show specific restaurant
```bash
luncher show utelleru
```

#### Compare menus with AI
```bash
luncher compare
```

#### List available restaurants
```bash
luncher list
```

#### Clear cache
```bash
luncher clear-cache
# Or clear specific restaurant:
luncher clear-cache utelleru
```

#### Force fresh data (bypass cache)
```bash
luncher today --no-cache
```

### Web Interface

Start the web server:
```bash
uvicorn luncher.web.app:app --reload
```

Then visit: http://localhost:8000

Or run directly:
```bash
python -m luncher.web.app
```

### API Endpoints

- `GET /` - Web interface
- `GET /api/menus/today` - Get today's menus as JSON
- `GET /api/compare` - Get AI comparison
- `GET /health` - Health check

## Supported Restaurants

| Restaurant | ID | Type |
|------------|----|----- |
| U Telleru | `utelleru` | Static HTML |
| Spravovna | `spravovna` | Static HTML |
| Pub Na Plech | `pub_na_plech` | Static HTML |
| Chilli & Lime | `chilli_lime` | Dynamic JSON |
| PORKE | `porke` | Dynamic (Playwright) |

## Project Structure

```
luncher/
├── config/
│   ├── settings.py          # Configuration loader
│   └── restaurants.yaml     # Restaurant definitions
├── src/luncher/
│   ├── core/
│   │   ├── models.py       # Data models
│   │   ├── cache.py        # Caching layer
│   │   └── ai.py           # Claude AI integration
│   ├── scrapers/
│   │   ├── base.py         # Base scraper class
│   │   ├── registry.py     # Scraper registry
│   │   └── implementations/ # Restaurant scrapers
│   ├── cli/
│   │   └── app.py          # CLI application
│   └── web/
│       ├── app.py          # FastAPI app
│       └── templates/
│           └── index.html   # Web UI
└── tests/
```

## Adding a New Restaurant

1. **Add to config/restaurants.yaml**:
   ```yaml
   - id: my_restaurant
     name: "My Restaurant"
     url: "https://example.com/menu"
     scraper_class: "luncher.scrapers.implementations.my_restaurant.MyRestaurantScraper"
     enabled: true
   ```

2. **Create scraper in src/luncher/scrapers/implementations/my_restaurant.py**:
   ```python
   from luncher.scrapers.base import BaseScraper
   from luncher.scrapers.registry import ScraperRegistry
   from luncher.core.models import DailyMenu, MenuItem

   @ScraperRegistry.register('my_restaurant')
   class MyRestaurantScraper(BaseScraper):
       async def scrape(self, target_date=None):
           # Implement scraping logic
           pass
   ```

3. **Test it**:
   ```bash
   luncher show my_restaurant
   ```

## Configuration

### Environment Variables

Set in `.env` file:

- `ANTHROPIC_API_KEY` - Claude API key (required for AI features)
- `CACHE_TTL_HOURS` - Cache expiration in hours (default: 4)
- `CACHE_DIR` - Cache directory (default: ~/.luncher/cache)
- `WEB_HOST` - Web server host (default: 0.0.0.0)
- `WEB_PORT` - Web server port (default: 8000)

### Restaurant Configuration

Edit `config/restaurants.yaml` to enable/disable restaurants or add new ones.

## Development

### Running Tests

```bash
pytest
```

### Code Structure

- **Models** (`core/models.py`): Data structures for menus and items
- **Scrapers** (`scrapers/`): Pluggable scraper system with registry
- **Cache** (`core/cache.py`): File-based caching with TTL
- **AI** (`core/ai.py`): Claude AI integration for summaries
- **CLI** (`cli/app.py`): Typer-based command-line interface
- **Web** (`web/app.py`): FastAPI web application

## Troubleshooting

### "Playwright not installed" error
```bash
playwright install chromium
```

### "Anthropic API key not found" error
Make sure `.env` file exists with `ANTHROPIC_API_KEY=sk-ant-...`

### Empty menus
- Check if the restaurant website is accessible
- Try `--no-cache` to force fresh scraping
- Restaurant websites may have changed structure (scrapers may need updates)

### Cache issues
Clear the cache:
```bash
luncher clear-cache
```

## License

MIT

## Credits

Built with:
- [Anthropic Claude](https://www.anthropic.com/) - AI summaries
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing
- [Playwright](https://playwright.dev/) - Browser automation

---

Made with ❤️ using Claude Code
