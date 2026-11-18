"""SQLite-backed rate limiter, action deduplication, and safety circuit breaker."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict


class QuotaExceededError(Exception):
    """Raised when a daily safety quota has been reached."""


class CheckpointDetectedError(Exception):
    """Raised when LinkedIn presents a CAPTCHA, 429, or security checkpoint."""


class RateLimiter:
    """Persists action history to enforce daily quotas and prevent duplicate outreach."""

    def __init__(self, db_path: Path, quotas: Dict[str, int]) -> None:
        self.db_path = db_path
        self.quotas = quotas
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    profile_url TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    headline TEXT,
                    company TEXT,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def actions_in_last_24h(self, action_type: str) -> int:
        """Count successful actions of a given type in the past 24 hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM action_log
                WHERE action_type = ? AND status = 'success' AND created_at >= ?
                """,
                (action_type, cutoff),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def remaining_quota(self, action_type: str) -> int:
        limit = self.quotas.get(action_type, 0)
        used = self.actions_in_last_24h(action_type)
        return max(0, limit - used)

    def check_quota(self, action_type: str) -> None:
        """Raise QuotaExceededError if daily cap is reached."""
        if self.remaining_quota(action_type) <= 0:
            limit = self.quotas.get(action_type, 0)
            raise QuotaExceededError(
                f"Daily safety limit reached for '{action_type}' ({limit}/24h). Stopping to protect account."
            )

    def already_processed(self, profile_url: str, statuses: tuple[str, ...] = ("connected", "messaged")) -> bool:
        """Return True if this lead has already been contacted."""
        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT status FROM leads WHERE profile_url = ? AND status IN ({placeholders})",
                (profile_url, *statuses),
            ).fetchone()
        return row is not None

    def record_action(
        self,
        action_type: str,
        target_url: str,
        status: str = "success",
        note: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO action_log (action_type, target_url, status, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_type, target_url, status, note, now),
            )

    def upsert_lead(
        self,
        profile_url: str,
        name: str,
        headline: str,
        company: str,
        status: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO leads (profile_url, name, headline, company, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_url) DO UPDATE SET
                    name = excluded.name,
                    headline = excluded.headline,
                    company = excluded.company,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (profile_url, name, headline, company, status, now),
            )

    def summary(self) -> Dict[str, Dict[str, int]]:
        """Return used and limit counts for all tracked action types."""
        return {
            action: {
                "used_24h": self.actions_in_last_24h(action),
                "limit_24h": limit,
            }
            for action, limit in self.quotas.items()
        }

