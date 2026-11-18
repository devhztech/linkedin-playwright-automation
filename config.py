"""Application configuration loaded from environment variables or .env."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_mode: str = "demo"  # "demo" | "live"
    headless: bool = False
    slow_mo_ms: int = 40
    user_data_dir: Path = Path("./browser_profile")
    db_path: Path = Path("./data/state.db")
    output_dir: Path = Path("./output")

    # Daily safety quotas
    max_connections_per_day: int = 20
    max_messages_per_day: int = 35
    max_profile_views_per_day: int = 80

    # Humanized delay bounds (seconds)
    min_action_delay: float = 2.0
    max_action_delay: float = 5.0

    # Default run parameters
    search_query: str = "SaaS Founder"
    max_leads_per_run: int = 5
    demo_port: int = 8765


settings = Settings()

