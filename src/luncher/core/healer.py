"""Self-healing scraper: generates code fixes and opens GitHub PRs."""

import inspect
import logging
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ScraperHealer:
    """Uses Claude to fix broken scrapers and open a PR with the fix."""

    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)

    def get_scraper_path(self, restaurant_id: str) -> Optional[Path]:
        """Resolve the source file for a registered scraper."""
        from luncher.scrapers.registry import ScraperRegistry
        scraper_class = ScraperRegistry.get(restaurant_id)
        if not scraper_class:
            return None
        return Path(inspect.getfile(scraper_class))

    def get_fallback_html(self, restaurant_id: str) -> Optional[str]:
        """Read the HTML saved during AI fallback scraping."""
        html_path = Path(f"/tmp/luncher_fallback_{restaurant_id}.html")
        if not html_path.exists():
            return None
        return html_path.read_text(encoding="utf-8")

    def generate_fix(self, scraper_path: Path, html: str) -> str:
        """Ask Claude Sonnet to fix the scraper given the new HTML structure."""
        current_code = scraper_path.read_text(encoding="utf-8")

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "meta", "link"]):
            tag.decompose()
        clean_html = str(soup)[:15000]

        prompt = f"""This Python web scraper stopped working because the restaurant website changed its HTML structure.

Current scraper code:
```python
{current_code}
```

Current HTML of the page (scripts/styles removed):
```html
{clean_html}
```

Analyse the HTML and fix the scraper so it correctly extracts the lunch menu items again.
Return ONLY the complete fixed Python file with no explanation, no markdown fences."""

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()

    def open_pr(self, restaurant_id: str, scraper_path: Path, fixed_code: str) -> Optional[str]:
        """
        Commit the fixed scraper to a new branch and open a GitHub PR.
        Returns the PR URL, or None if it failed.
        """
        branch = f"fix/scraper-{restaurant_id}-{date.today().isoformat()}"

        try:
            # Configure git identity for the Actions runner
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)

            subprocess.run(["git", "checkout", "-b", branch], check=True)

            scraper_path.write_text(fixed_code, encoding="utf-8")
            subprocess.run(["git", "add", str(scraper_path)], check=True)
            subprocess.run(
                ["git", "commit", "-m", f"fix: auto-heal {restaurant_id} scraper\n\nWebsite structure changed; selectors updated by self-healing AI."],
                check=True
            )
            subprocess.run(["git", "push", "--force", "origin", branch], check=True)

            gh_cmd = [
                "gh", "pr", "create",
                "--title", f"fix: auto-heal {restaurant_id} scraper",
                "--body", (
                    f"The **{restaurant_id}** scraper broke today because the restaurant website changed its HTML structure.\n\n"
                    "The self-healing mechanism fetched the live page, analysed the new structure, and generated this fix automatically.\n\n"
                    "**Please review the diff before merging.**"
                ),
                "--base", "master",
                "--head", branch,
            ]
            repo = os.environ.get("GITHUB_REPOSITORY")
            if repo:
                gh_cmd += ["--repo", repo]

            result = subprocess.run(gh_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("gh pr create failed for %s: %s", restaurant_id, result.stderr.strip())
                return None

            pr_url = result.stdout.strip()
            logger.info("Opened healing PR for %s: %s", restaurant_id, pr_url)
            return pr_url

        except subprocess.CalledProcessError as e:
            logger.error("Failed to open PR for %s: %s", restaurant_id, e)
            return None
        finally:
            # Return to master so the rest of the workflow continues normally
            subprocess.run(["git", "checkout", "master"], check=False)

    def heal(self, restaurant_id: str) -> Optional[str]:
        """
        Full heal cycle: generate fix + open PR.
        Returns PR URL or None.
        """
        scraper_path = self.get_scraper_path(restaurant_id)
        if not scraper_path:
            logger.warning("No scraper file found for %s, skipping heal", restaurant_id)
            return None

        html = self.get_fallback_html(restaurant_id)
        if not html:
            logger.warning("No fallback HTML saved for %s, skipping heal", restaurant_id)
            return None

        try:
            logger.info("Generating fix for %s scraper...", restaurant_id)
            fixed_code = self.generate_fix(scraper_path, html)
            return self.open_pr(restaurant_id, scraper_path, fixed_code)
        except Exception as e:
            logger.error("Heal failed for %s: %s", restaurant_id, e)
            return None
