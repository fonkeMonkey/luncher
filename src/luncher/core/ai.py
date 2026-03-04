"""Claude AI integration for menu analysis and summaries."""

from typing import List, Optional
from luncher.core.models import DailyMenu
from luncher.config.settings import settings


class MenuAIProcessor:
    """Process menus using Claude AI."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AI processor.

        Args:
            api_key: Anthropic API key. If None, uses settings.anthropic_api_key
        """
        self.api_key = api_key or settings.anthropic_api_key

        if not self.api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable."
            )

        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

    async def summarize_menu(self, menu: DailyMenu) -> str:
        """
        Generate a brief, friendly summary of a menu in Czech.

        Args:
            menu: Daily menu to summarize.

        Returns:
            Czech summary text.
        """
        if not menu.is_valid:
            return f"Bohužel se nepodařilo načíst menu z {menu.restaurant_name}."

        # Build menu text
        menu_text = f"Restaurace: {menu.restaurant_name}\n\n"
        for item in menu.items:
            menu_text += str(item) + "\n"

        prompt = f"""Prosím, poskytni krátké, přátelské shrnutí tohoto polední menu v češtině (max 3 věty).
Upozorni na zajímavá nebo populární jídla.

{menu_text}

Odpověz pouze v češtině, bez anglických slov."""

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("summarize_menu failed: %s", e)
            return "Chyba při generování shrnutí."

    async def compare_menus(self, menus: List[DailyMenu]) -> str:
        """
        Compare all menus and provide recommendations in Czech.

        Args:
            menus: List of daily menus to compare.

        Returns:
            Czech comparison and recommendations.
        """
        valid_menus = [m for m in menus if m.is_valid]

        if not valid_menus:
            return "Bohužel se nepodařilo načíst žádná menu."

        # Build comprehensive menu text
        menu_text = "DNEŠNÍ POLEDNÍ MENU:\n\n"
        for menu in valid_menus:
            menu_text += f"=== {menu.restaurant_name} ===\n"
            for item in menu.items:
                menu_text += f"  • {item}\n"
            menu_text += "\n"

        prompt = f"""Analyzuj následující polední menu z různých restaurací a poskytni:

1. Stručné srovnání (co je zajímavé, jaké jsou rozdíly v nabídce)
2. Doporučení podle různých preferencí:
   - Nejlepší poměr cena/výkon
   - Nejvíce zdravé/lehké jídlo
   - Nejzajímavější/netradiční nabídka
   - Doporučení pro vegetariány (pokud je něco dostupné)

{menu_text}

Odpověz pouze v češtině, ve struktuře uvedené výše. Buď konkrétní a praktický."""

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("compare_menus failed: %s", e)
            if "credit balance is too low" in str(e):
                return "AI analýza není dostupná – došly kredity. Dobij je na console.anthropic.com/settings/billing."
            return "Chyba při porovnání menu."

    async def answer_question(self, menus: List[DailyMenu], question: str) -> str:
        """
        Answer a specific question about the menus in Czech.

        Args:
            menus: List of daily menus.
            question: User's question in Czech.

        Returns:
            Answer in Czech.
        """
        valid_menus = [m for m in menus if m.is_valid]

        if not valid_menus:
            return "Bohužel nemám k dispozici žádná menu pro zodpovězení dotazu."

        # Build menu context
        menu_text = ""
        for menu in valid_menus:
            menu_text += f"{menu.restaurant_name}:\n"
            for item in menu.items:
                menu_text += f"  • {item}\n"
            menu_text += "\n"

        prompt = f"""Na základě následujících dnešních poledních menu odpověz na dotaz uživatele.

MENU:
{menu_text}

DOTAZ: {question}

Odpověz v češtině, stručně a konkrétně."""

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("answer_question failed: %s", e)
            return "Chyba při odpovídání na dotaz."
