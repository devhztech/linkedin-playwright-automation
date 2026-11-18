"""CLI entrypoint for the Playwright LinkedIn Automation showcase."""

from __future__ import annotations

import argparse
from contextlib import nullcontext

from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import settings
from core.linkedin_bot import LinkedInAutomationBot, export_results
from core.rate_limiter import RateLimiter
from core.stealth import human_delay, launch_stealth_context
from mock_site.server import MockLinkedInServer

console = Console()

DEFAULT_NOTE_TEMPLATE = (
    "Hi {first_name}, came across your work at {company} and would love to connect "
    "and exchange notes on scaling B2B automation."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Playwright LinkedIn Lead & Outreach Automation")
    parser.add_argument("--mode", choices=["demo", "live"], default=settings.app_mode, help="Run against local sandbox or live LinkedIn")
    parser.add_argument("--query", default=settings.search_query, help="Search keyword (e.g., 'SaaS Founder')")
    parser.add_argument("--limit", type=int, default=settings.max_leads_per_run, help="Max leads to process in this run")
    parser.add_argument("--headless", action="store_true", default=settings.headless, help="Run Chromium headless")
    parser.add_argument("--reset-db", action="store_true", help="Clear local SQLite rate-limit/dedup history before running")
    parser.add_argument("--record-video", action="store_true", help="Record browser session video to output/videos/")
    return parser.parse_args()


def render_summary(leads, limiter: RateLimiter, csv_path, json_path) -> None:
    lead_table = Table(title="Processed Leads Summary", show_lines=True)
    lead_table.add_column("Name", style="bold cyan")
    lead_table.add_column("Company", style="white")
    lead_table.add_column("Status", style="green")

    for lead in leads:
        lead_table.add_row(lead.name, lead.company, lead.status)

    quota_table = Table(title="24h Safety Rate-Limit Budget")
    quota_table.add_column("Action", style="magenta")
    quota_table.add_column("Used (24h)", justify="right")
    quota_table.add_column("Daily Cap", justify="right")

    for action, stats in limiter.summary().items():
        quota_table.add_row(action, str(stats["used_24h"]), str(stats["limit_24h"]))

    console.print()
    console.print(lead_table)
    console.print(quota_table)
    console.print(f"\n[bold]Exports:[/bold] {csv_path} | {json_path}\n")


def main() -> None:
    args = parse_args()

    if args.reset_db and settings.db_path.exists():
        settings.db_path.unlink()
        console.log("[yellow]Cleared previous SQLite state database.[/yellow]")

    console.print(
        Panel.fit(
            f"[bold cyan]Playwright LinkedIn Automation[/bold cyan]\n"
            f"Mode: [bold]{args.mode.upper()}[/bold] | Query: [bold]{args.query}[/bold] | Limit: [bold]{args.limit}[/bold]",
            border_style="cyan",
        )
    )

    limiter = RateLimiter(
        db_path=settings.db_path,
        quotas={
            "connection": settings.max_connections_per_day,
            "message": settings.max_messages_per_day,
            "profile_view": settings.max_profile_views_per_day,
        },
    )

    server_ctx = MockLinkedInServer(port=settings.demo_port) if args.mode == "demo" else nullcontext()

    with server_ctx as server:
        base_url = server.url if args.mode == "demo" else "https://www.linkedin.com/feed/"

        with sync_playwright() as p:
            video_dir = settings.output_dir / "videos" if args.record_video else None
            context = launch_stealth_context(
                playwright=p,
                user_data_dir=settings.user_data_dir,
                headless=args.headless,
                slow_mo_ms=settings.slow_mo_ms,
                record_video_dir=video_dir,
            )
            page = context.pages[0] if context.pages else context.new_page()

            bot = LinkedInAutomationBot(
                page=page,
                rate_limiter=limiter,
                base_url=base_url,
                mode=args.mode,
                min_delay=settings.min_action_delay,
                max_delay=settings.max_action_delay,
            )

            bot.ensure_session()
            leads = bot.search_leads(query=args.query, max_leads=args.limit)
            processed = bot.process_leads(leads, note_template=DEFAULT_NOTE_TEMPLATE)

            if args.mode == "demo" and not args.headless:
                console.log("[dim]Pausing 2s so final UI state is visible for recording...[/dim]")
                human_delay(2.0, 2.5)

            video_path = page.video.path() if (args.record_video and page.video) else None
            context.close()

    csv_path, json_path = export_results(processed, settings.output_dir)
    render_summary(processed, limiter, csv_path, json_path)
    if video_path:
        console.print(f"[bold green]Recorded Demo Video:[/bold green] {video_path}\n")


if __name__ == "__main__":
    main()

