"""Generate a static HTML page with today's lunch menus for GitHub Pages."""

import asyncio
import sys
from datetime import date
from pathlib import Path

# Ensure the src directory is on the path when running directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jinja2 import Environment, FileSystemLoader

from luncher.core.ai import MenuAIProcessor
from luncher.web.app import fetch_all_menus


async def main() -> None:
    print("Fetching menus...")
    menus = await fetch_all_menus(use_cache=False)
    print(f"Fetched {len(menus)} menus")

    ai_comparison = None
    try:
        print("Generating AI comparison...")
        ai = MenuAIProcessor()
        ai_comparison = await ai.compare_menus(menus)
        print("AI comparison done")
    except Exception as e:
        print(f"AI comparison skipped: {e}")

    templates_dir = Path(__file__).parent.parent / "src" / "luncher" / "web" / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template("index.html")

    html = template.render(
        menus=menus,
        today=date.today(),
        ai_comparison=ai_comparison,
    )

    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    output_path = docs_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
