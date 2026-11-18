"""Playwright LinkedIn automation engine supporting both safe Demo and Live modes."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

from playwright.sync_api import Page
from rich.console import Console

from core.rate_limiter import CheckpointDetectedError, QuotaExceededError, RateLimiter
from core.stealth import human_click, human_delay, human_scroll, human_type

console = Console()


@dataclass
class Lead:
    profile_url: str
    name: str
    headline: str
    company: str
    bio: str = ""
    status: str = "discovered"


class LinkedInAutomationBot:
    """Automates LinkedIn lead search, profile enrichment, and personalized outreach."""

    CHECKPOINT_MARKERS = ("checkpoint/challenge", "authwall", "security verification", "captcha")

    def __init__(
        self,
        page: Page,
        rate_limiter: RateLimiter,
        base_url: str,
        mode: str = "demo",
        min_delay: float = 2.0,
        max_delay: float = 5.0,
    ) -> None:
        self.page = page
        self.limiter = rate_limiter
        self.base_url = base_url.rstrip("/")
        self.mode = mode
        self.min_delay = min_delay
        self.max_delay = max_delay

    def _check_for_challenges(self) -> None:
        """Circuit breaker: abort immediately if a security checkpoint or CAPTCHA appears."""
        current_url = self.page.url.lower()
        content_lower = self.page.content()[:4000].lower()
        for marker in self.CHECKPOINT_MARKERS:
            if marker in current_url or marker in content_lower:
                raise CheckpointDetectedError(
                    f"Security checkpoint detected ('{marker}'). Halting automation safely."
                )

    def ensure_session(self) -> None:
        """Open target site and verify session readiness."""
        console.log(f"[cyan]Navigating to[/cyan] {self.base_url} (mode={self.mode})")
        self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
        human_delay(1.0, 2.0)
        self._check_for_challenges()

        if self.mode == "live" and ("login" in self.page.url.lower() or "uas/login" in self.page.url.lower()):
            console.print(
                "[yellow]LinkedIn login required.[/yellow] Please log in manually in the open browser window.\n"
                "Your session will be saved in `browser_profile/` for future runs."
            )
            self.page.wait_for_url("**/feed/**", timeout=180000)
            console.log("[green]Login detected and session persisted.[/green]")

    def search_leads(self, query: str, max_leads: int = 5) -> List[Lead]:
        """Search for people matching `query` and extract lead metadata."""
        console.log(f"[cyan]Searching leads for:[/cyan] '{query}' (limit={max_leads})")

        if self.mode == "demo":
            human_type(self.page, '[data-testid="search-input"]', query)
            human_click(self.page, self.page.locator('[data-testid="search-btn"]'))
            human_delay(0.8, 1.6)
            human_scroll(self.page, distance_px=450)
            return self._extract_demo_leads(max_leads)

        search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}"
        self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        human_delay(self.min_delay, self.max_delay)
        self._check_for_challenges()
        human_scroll(self.page, distance_px=700)
        return self._extract_live_leads(max_leads)

    def _extract_demo_leads(self, max_leads: int) -> List[Lead]:
        cards = self.page.locator('[data-testid="lead-card"]')
        count = min(cards.count(), max_leads)
        leads: List[Lead] = []

        for idx in range(count):
            card = cards.nth(idx)
            lead_id = card.get_attribute("data-lead-id") or f"lead-{idx}"
            name = card.locator('[data-testid="lead-name"]').inner_text().strip()
            headline = card.locator('[data-testid="lead-headline"]').inner_text().strip()
            company_raw = card.locator('[data-testid="lead-company"]').inner_text().strip()
            company = company_raw.split("·")[0].strip()

            leads.append(
                Lead(
                    profile_url=f"{self.base_url}/in/{lead_id}",
                    name=name,
                    headline=headline,
                    company=company,
                )
            )
        console.log(f"[green]Extracted {len(leads)} leads from search results.[/green]")
        return leads

    def _extract_live_leads(self, max_leads: int) -> List[Lead]:
        cards = self.page.locator("li.reusable-search__result-container")
        count = min(cards.count(), max_leads)
        leads: List[Lead] = []

        for idx in range(count):
            card = cards.nth(idx)
            link = card.locator("a.app-aware-link").first
            href = link.get_attribute("href") or ""
            profile_url = href.split("?")[0]
            name = card.locator("span[aria-hidden='true']").first.inner_text().strip()
            headline = card.locator(".entity-result__primary-subtitle").inner_text().strip()
            company = headline.split(" at ")[-1].strip() if " at " in headline else "your team"

            if profile_url:
                leads.append(
                    Lead(
                        profile_url=profile_url,
                        name=name,
                        headline=headline,
                        company=company,
                    )
                )
        console.log(f"[green]Extracted {len(leads)} live leads.[/green]")
        return leads

    def process_leads(self, leads: List[Lead], note_template: str) -> List[Lead]:
        """Enrich each lead profile and send a rate-limited personalized connection request."""
        processed: List[Lead] = []

        for lead in leads:
            if self.limiter.already_processed(lead.profile_url):
                console.log(f"[yellow]Skipping already-contacted lead:[/yellow] {lead.name}")
                lead.status = "skipped_duplicate"
                processed.append(lead)
                continue

            try:
                self.limiter.check_quota("profile_view")
                self._enrich_lead(lead)
                self.limiter.record_action("profile_view", lead.profile_url)

                self.limiter.check_quota("connection")
                self._send_connection_request(lead, note_template)
                self.limiter.record_action("connection", lead.profile_url, note=f"Connected with {lead.name}")
                lead.status = "connected"
                self.limiter.upsert_lead(
                    lead.profile_url, lead.name, lead.headline, lead.company, lead.status
                )
                console.log(f"[bold green]✓ Connected:[/bold green] {lead.name} ({lead.company})")

            except QuotaExceededError as exc:
                console.log(f"[bold red]{exc}[/bold red]")
                lead.status = "quota_paused"
                processed.append(lead)
                break
            except CheckpointDetectedError as exc:
                console.log(f"[bold red]{exc}[/bold red]")
                lead.status = "checkpoint_halted"
                processed.append(lead)
                break

            processed.append(lead)
            delay = human_delay(self.min_delay, self.max_delay)
            console.log(f"[dim]Cooldown sleep: {delay:.2f}s[/dim]")

        return processed

    def _enrich_lead(self, lead: Lead) -> None:
        if self.mode == "demo":
            lead_id = lead.profile_url.rsplit("/", 1)[-1]
            card = self.page.locator(f'[data-lead-id="{lead_id}"]')
            human_click(self.page, card.locator('[data-testid="view-profile-btn"]'))
            human_delay(0.8, 1.5)
            lead.bio = self.page.locator("#detail-bio").inner_text().strip()
            human_click(self.page, self.page.locator('#profile-detail button:has-text("Back")'))
            human_delay(0.5, 1.0)
            return

        self.page.goto(lead.profile_url, wait_until="domcontentloaded", timeout=30000)
        human_delay(self.min_delay, self.max_delay)
        self._check_for_challenges()
        human_scroll(self.page, distance_px=500)
        about = self.page.locator("#about ~ div").first
        lead.bio = about.inner_text().strip()[:300] if about.count() else ""

    def _send_connection_request(self, lead: Lead, note_template: str) -> None:
        first_name = lead.name.split()[0] if lead.name else "there"
        personalized_note = note_template.format(first_name=first_name, company=lead.company)

        if self.mode == "demo":
            lead_id = lead.profile_url.rsplit("/", 1)[-1]
            card = self.page.locator(f'[data-lead-id="{lead_id}"]')
            human_click(self.page, card.locator('[data-testid="connect-btn"]'))
            human_delay(0.5, 1.0)
            human_type(self.page, '[data-testid="connect-note"]', personalized_note)
            human_delay(0.5, 1.0)
            human_click(self.page, self.page.locator('[data-testid="send-invite-btn"]'))
            return

        connect_btn = self.page.locator('button:has-text("Connect")').first
        if connect_btn.count() == 0:
            raise RuntimeError(f"Connect button not available for {lead.name}")
        human_click(self.page, connect_btn)
        human_delay(0.8, 1.5)

        add_note_btn = self.page.locator('button:has-text("Add a note")')
        if add_note_btn.count() > 0:
            human_click(self.page, add_note_btn.first)
            human_type(self.page, 'textarea[name="message"]', personalized_note)
            human_delay(0.6, 1.2)
            human_click(self.page, self.page.locator('button:has-text("Send")').first)


def export_results(leads: List[Lead], output_dir: Path) -> tuple[Path, Path]:
    """Save extracted and contacted leads to CSV and JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "leads.csv"
    json_path = output_dir / "report.json"

    rows = [asdict(lead) for lead in leads]
    fieldnames = ["name", "headline", "company", "profile_url", "status", "bio"]

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_leads": len(rows),
        "leads": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return csv_path, json_path

