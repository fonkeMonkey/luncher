# Quick Start Guide

## 🚀 Get Started in 5 Minutes

### 1. Install Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Install Playwright browser (for PORKE restaurant)
playwright install chromium
```

### 2. Configure API Key (Optional for AI features)

```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your Anthropic API key
# ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Get your API key from: https://console.anthropic.com/

### 3. Try It Out!

#### View All Restaurants
```bash
luncher list
```

#### Get Today's Menus (No API key needed)
```bash
luncher today
```

This will fetch and display menus from all 5 restaurants!

#### View Specific Restaurant
```bash
luncher show utelleru
```

#### Compare with AI (Requires API key)
```bash
luncher compare
```

### 4. Start Web Interface

```bash
# Start the web server
uvicorn luncher.web.app:app --reload

# Open browser to http://localhost:8000
```

## 📝 Common Commands

| Command | Description |
|---------|-------------|
| `luncher list` | Show all available restaurants |
| `luncher today` | Display all today's menus |
| `luncher show <id>` | Show specific restaurant menu |
| `luncher compare` | AI-powered menu comparison |
| `luncher clear-cache` | Clear cached menus |
| `luncher today --no-cache` | Force fresh data fetch |

## 🏪 Available Restaurants

1. **U Telleru** (`utelleru`) - Czech traditional cuisine
2. **Spravovna** (`spravovna`) - Modern Czech food
3. **Pub Na Plech** (`pub_na_plech`) - Pub food
4. **Chilli & Lime** (`chilli_lime`) - Asian fusion
5. **PORKE** (`porke`) - BBQ and grilled

## 🎨 Features Overview

### CLI Output
- Beautiful terminal tables with Rich
- Color-coded soups and prices
- Error handling with clear messages
- 4-hour intelligent caching

### Web Interface
- Responsive design
- All menus on one page
- AI comparison button
- Smooth animations

### AI Features (Requires API Key)
- Menu summaries in Czech
- Price/value recommendations
- Health-conscious options
- Vegetarian suggestions
- Interactive Q&A

## 🔧 Troubleshooting

### "Playwright not installed"
```bash
playwright install chromium
```

### "API key not found" (for AI features)
Add your key to `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Empty Menus
- Try `--no-cache` to force fresh scraping
- Check if restaurant websites are accessible
- Some restaurants may not have daily menus on weekends

### Cache Issues
```bash
luncher clear-cache
```

## 📚 Next Steps

1. **Add Your Favorite Restaurant**
   - See `README.md` for detailed instructions
   - Only requires creating a new scraper class

2. **Customize Settings**
   - Edit `src/luncher/config/restaurants.yaml`
   - Enable/disable restaurants
   - Adjust cache TTL in `.env`

3. **Integrate with Your Workflow**
   - Add `luncher today` to your shell startup
   - Create aliases for favorite commands
   - Schedule cron jobs for daily emails

---

Made with ❤️ using Claude Code
