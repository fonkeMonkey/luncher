"""Command-line interface for luncher."""

import asyncio
from datetime import date
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from luncher.config.settings import settings
from luncher.core.cache import MenuCache
from luncher.core.ai import MenuAIProcessor
from luncher.scrapers.registry import ScraperRegistry

app = typer.Typer(
    name="luncher",
    help="Daily lunch menu aggregator for Czech restaurants",
    add_completion=False
)
console = Console()


async def fetch_menu(restaurant_config, use_cache: bool = True):
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
        console.print(f"[red]Error scraping {restaurant_config.name}: {e}[/red]")
        return None


async def fetch_all_menus(use_cache: bool = True):
    """Fetch menus from all enabled restaurants."""
    restaurants = settings.get_enabled_restaurants()

    # Fetch all menus concurrently
    tasks = [fetch_menu(resto, use_cache) for resto in restaurants]
    menus = await asyncio.gather(*tasks)

    return [m for m in menus if m is not None]


def display_menu_table(menus):
    """Display menus in a rich table."""
    for menu in menus:
        # Create a table for this restaurant
        table = Table(
            title=f"[bold cyan]{menu.restaurant_name}[/bold cyan]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )

        table.add_column("Jídlo", style="white", no_wrap=False)
        table.add_column("Cena", justify="right", style="green")

        if not menu.is_valid:
            table.add_row(f"[red]{menu.error}[/red]", "")
        else:
            # Group by type
            soups = menu.get_items_by_type("soup")
            mains = menu.get_items_by_type("main")
            others = [item for item in menu.items if item.type not in ["soup", "main"]]

            # Add soups
            if soups:
                for item in soups:
                    price = f"{item.price:.0f} Kč" if item.price else "-"
                    table.add_row(f"[yellow]Polévka:[/yellow] {item.name}", price)

            # Add separator if we have both soups and mains
            if soups and mains:
                table.add_row("", "")

            # Add mains
            for item in mains:
                price = f"{item.price:.0f} Kč" if item.price else "-"
                table.add_row(item.name, price)

            # Add others
            for item in others:
                price = f"{item.price:.0f} Kč" if item.price else "-"
                table.add_row(item.name, price)

        console.print(table)
        console.print()


@app.command()
def today(
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass cache and fetch fresh data")
):
    """Show today's lunch menus from all restaurants."""
    console.print("[bold]Načítám dnešní polední menu...[/bold]\n")

    menus = asyncio.run(fetch_all_menus(use_cache=not no_cache))

    if not menus:
        console.print("[red]Nepodařilo se načíst žádná menu.[/red]")
        raise typer.Exit(1)

    display_menu_table(menus)

    # Show summary
    valid_count = sum(1 for m in menus if m.is_valid)
    console.print(f"[dim]Načteno {valid_count} z {len(menus)} menu[/dim]")


@app.command()
def show(
    restaurant_id: str = typer.Argument(..., help="Restaurant ID (e.g., utelleru)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass cache and fetch fresh data")
):
    """Show menu from a specific restaurant."""
    restaurants = settings.load_restaurants()
    restaurant = next((r for r in restaurants if r.id == restaurant_id), None)

    if not restaurant:
        console.print(f"[red]Restaurant '{restaurant_id}' not found.[/red]")
        console.print("\nAvailable restaurants:")
        for r in restaurants:
            console.print(f"  • {r.id} - {r.name}")
        raise typer.Exit(1)

    console.print(f"[bold]Načítám menu z {restaurant.name}...[/bold]\n")

    menu = asyncio.run(fetch_menu(restaurant, use_cache=not no_cache))

    if menu:
        display_menu_table([menu])
    else:
        console.print("[red]Nepodařilo se načíst menu.[/red]")
        raise typer.Exit(1)


@app.command()
def compare(
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass cache and fetch fresh data")
):
    """Compare all menus with AI-powered analysis."""
    console.print("[bold]Načítám menu pro porovnání...[/bold]\n")

    menus = asyncio.run(fetch_all_menus(use_cache=not no_cache))

    if not menus:
        console.print("[red]Nepodařilo se načíst žádná menu.[/red]")
        raise typer.Exit(1)

    # Display menus
    display_menu_table(menus)

    # AI comparison
    console.print("[bold cyan]Zpracovávám AI analýzu...[/bold cyan]\n")

    try:
        ai = MenuAIProcessor()
        comparison = asyncio.run(ai.compare_menus(menus))

        panel = Panel(
            comparison,
            title="[bold magenta]🤖 AI Doporučení[/bold magenta]",
            border_style="magenta",
            padding=(1, 2)
        )
        console.print(panel)
    except ValueError as e:
        console.print(f"[red]AI nedostupná: {e}[/red]")
        console.print("[yellow]Tip: Nastav ANTHROPIC_API_KEY v .env souboru[/yellow]")


@app.command()
def list():
    """List all available restaurants."""
    restaurants = settings.load_restaurants()

    table = Table(title="[bold]Dostupné restaurace[/bold]", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("Název", style="white")
    table.add_column("URL", style="blue", no_wrap=False)
    table.add_column("Status", justify="center")

    for resto in restaurants:
        status = "[green]✓[/green]" if resto.enabled else "[red]✗[/red]"
        table.add_row(resto.id, resto.name, resto.url, status)

    console.print(table)


@app.command()
def clear_cache(
    restaurant_id: Optional[str] = typer.Argument(None, help="Restaurant ID to clear (clears all if not specified)")
):
    """Clear the menu cache."""
    cache = MenuCache()

    if restaurant_id:
        count = cache.clear(restaurant_id, date.today())
        console.print(f"[green]Vymazáno {count} cache souborů pro {restaurant_id}[/green]")
    else:
        count = cache.clear()
        console.print(f"[green]Vymazáno {count} cache souborů[/green]")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
