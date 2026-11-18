"""Stealth browser configuration and human-behavior simulation utilities."""

from __future__ import annotations

import random
import time
from pathlib import Path
from playwright.sync_api import BrowserContext, Locator, Page, Playwright


STEALTH_INIT_SCRIPT = """
// Mask automation indicators
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
"""


def launch_stealth_context(
    playwright: Playwright,
    user_data_dir: Path,
    headless: bool = False,
    slow_mo_ms: int = 40,
    record_video_dir: Path | None = None,
) -> BrowserContext:
    """Launch a persistent Chromium context with anti-detection hardening."""
    user_data_dir.mkdir(parents=True, exist_ok=True)
    if record_video_dir:
        record_video_dir.mkdir(parents=True, exist_ok=True)

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        headless=headless,
        slow_mo=slow_mo_ms,
        viewport={"width": 1366, "height": 840},
        locale="en-US",
        timezone_id="America/New_York",
        record_video_dir=str(record_video_dir) if record_video_dir else None,
        record_video_size={"width": 1366, "height": 840} if record_video_dir else None,
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    context.add_init_script(STEALTH_INIT_SCRIPT)
    return context


def human_delay(min_seconds: float = 1.5, max_seconds: float = 4.0) -> float:
    """Sleep for a randomized, human-like duration using triangular distribution."""
    midpoint = (min_seconds + max_seconds) / 2.0
    duration = random.triangular(min_seconds, max_seconds, midpoint)
    time.sleep(duration)
    return duration


def human_type(page: Page, selector: str, text: str) -> None:
    """Click an input and type text with randomized per-keystroke delays."""
    locator = page.locator(selector).first
    human_click(page, locator)
    locator.fill("")
    for char in text:
        locator.type(char, delay=random.randint(35, 115))
        if random.random() < 0.08:
            time.sleep(random.uniform(0.12, 0.30))


def human_click(page: Page, locator: Locator) -> None:
    """Move cursor toward the element with slight randomness before clicking."""
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box:
        target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        page.mouse.move(target_x, target_y, steps=random.randint(6, 14))
        time.sleep(random.uniform(0.08, 0.25))
    locator.click()


def human_scroll(page: Page, distance_px: int = 600) -> None:
    """Scroll down in variable increments to mimic natural reading."""
    scrolled = 0
    while scrolled < distance_px:
        step = random.randint(120, 260)
        page.mouse.wheel(0, step)
        scrolled += step
        time.sleep(random.uniform(0.15, 0.45))

