"""Claude AI integration for menu analysis and summaries."""

import json
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

        prompt = f"""Analyzuj následující polední menu z různých restaurací a poskytni doporučení podle těchto preferencí:
   - Nejvíce zdravé/lehké jídlo
   - Nejzajímavější/netradiční nabídka
   - Doporučení pro vegetariány (pokud je něco dostupné)
   - Nejlepší poměr cena/výkon

{menu_text}

Odpověz pouze v češtině, pouze s doporučeními ve struktuře uvedené výše. Buď konkrétní a praktický. Vynech jakékoliv úvodní srovnání nebo souhrn."""

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

    async def rate_menu_items(self, menus: List[DailyMenu]) -> None:
        """
        Rate each menu item for dietary healthiness (1-5) in place.

        1 = very unhealthy, 5 = very healthy.
        """
        valid_menus = [m for m in menus if m.is_valid]
        if not valid_menus:
            return

        items_list = [
            {"restaurant_id": menu.restaurant_id, "item_name": item.name, "type": item.type.value}
            for menu in valid_menus
            for item in menu.items
        ]
        if not items_list:
            return

        prompt = f"""Rate each food item for dietary healthiness on a scale 1-5:
1 = very unhealthy (fried, heavy, processed)
2 = below average
3 = average / balanced
4 = healthy
5 = very healthy (salads, vegetables, light)

Items (JSON):
{json.dumps(items_list, ensure_ascii=False)}

Reply ONLY with a JSON array, no other text. Include a short reason in Czech (max 8 words):
[{{"restaurant_id": "...", "item_name": "...", "rating": <1-5>, "reason": "..."}}, ...]"""

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip()
            import logging as _logging
            _logging.getLogger(__name__).info("rate_menu_items raw response: %s", raw[:500])
            # Extract JSON array robustly — find first [ and last ]
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1:
                raise ValueError(f"No JSON array found in response: {raw[:200]}")
            ratings = json.loads(raw[start:end + 1])
            rating_map = {(r["restaurant_id"], r["item_name"]): r for r in ratings}
            for menu in valid_menus:
                for item in menu.items:
                    entry = rating_map.get((menu.restaurant_id, item.name))
                    if entry is not None:
                        item.health_rating = int(entry["rating"])
                        item.health_rating_reason = entry.get("reason")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("rate_menu_items failed: %s", e)
