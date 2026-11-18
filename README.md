# LinkedIn Lead & Outreach Automation (Python + Playwright)

A production-structured browser automation framework built with **Python** and **Playwright** featuring anti-detection hardening, persistent sessions, SQLite-backed daily rate limiting, lead deduplication, and a safe local **Demo Sandbox Mode** for testing and walkthroughs.

## Key Features

- **Anti-Detection & Stealth (`core/stealth.py`)**
  - Persistent Chromium context (`launch_persistent_context`) to reuse cookies/sessions naturally.
  - Fingerprint hardening (`navigator.webdriver` masking, consistent locale/timezone/viewport).
  - Humanized interaction: triangular-distribution delays, variable-speed keystroke typing, curved/stepped mouse movement, and incremental scrolling.
- **Rate Limiting & Safety Guardrails (`core/rate_limiter.py`)**
  - Rolling 24-hour quota enforcement persisted in SQLite (`data/state.db`).
  - Automatic lead deduplication so no profile is contacted twice.
  - Checkpoint / CAPTCHA circuit breaker that halts execution immediately if a security challenge is detected.
- **Safe Demo Sandbox (`mock_site/server.py`)**
  - Embedded local HTTP server mimicking a LinkedIn-style people search, profile detail view, and connection modal—allowing full end-to-end visual runs without risking a live account.
- **Structured Exports (`output/`)**
  - Automatically generates `output/leads.csv` and `output/report.json` after every run.

## Quickstart

```bash
# 1. Create virtual environment & install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 2. Run in safe Demo Mode (great for testing or Loom walkthroughs)
python main.py --mode demo --query "SaaS Founder" --limit 4 --reset-db

# 3. Run in Live Mode (uses persistent browser_profile/ session)
python main.py --mode live --query "SaaS Founder" --limit 5
```

## Project Structure

```text
├── config.py              # Pydantic settings & rate-limit defaults
├── main.py                # CLI entrypoint & Rich terminal reporting
├── core/
│   ├── stealth.py         # Browser hardening & human-behavior simulation
│   ├── rate_limiter.py    # SQLite 24h quotas, deduplication & circuit breaker
│   └── linkedin_bot.py    # Search, enrichment, outreach & CSV/JSON export
└── mock_site/
    └── server.py          # Local interactive sandbox for safe demos
```

