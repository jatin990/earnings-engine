"""Central configuration: paths, markets, and data settings."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
PRICES_DIR = CACHE_DIR / "prices"
EARNINGS_DIR = CACHE_DIR / "earnings"

# Markets are identified by ticker suffix conventions used by yfinance.
MARKETS = {
    "IN": {"suffix": ".NS", "name": "NSE India"},
    "US": {"suffix": "", "name": "United States"},
}


@dataclass
class Settings:
    """Runtime settings for data ingestion."""

    history_start: str = "2015-01-01"
    # Refresh cached data if older than this many days.
    cache_max_age_days: int = 1
    # Pause between yfinance requests to stay under rate limits.
    request_pause_secs: float = 0.5
    markets: tuple[str, ...] = ("IN", "US")
    data_dirs: dict = field(
        default_factory=lambda: {
            "prices": PRICES_DIR,
            "earnings": EARNINGS_DIR,
        }
    )

    def ensure_dirs(self) -> None:
        for d in self.data_dirs.values():
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class EmailSettings:
    """SMTP settings for emailing generated reports."""

    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587 
    smtp_username: str = "jatin990.service@gmail.com"
    smtp_password: str = "yptc iqes rcud nngu"
    from_address: str = "jatin990.service@gmail.com"
    to_addresses: tuple[str, ...] = ("jatinabrol4@gmail.com",)


def _parse_env_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.replace(";", ",").split(",") if part.strip())


def load_email_settings() -> EmailSettings:
    """Load email settings from environment variables."""
    enabled = os.getenv("EARNINGS_ENGINE_EMAIL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    smtp_host = os.getenv("EARNINGS_ENGINE_SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("EARNINGS_ENGINE_SMTP_PORT", "587"))
    smtp_username = os.getenv("EARNINGS_ENGINE_SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("EARNINGS_ENGINE_SMTP_PASSWORD", "").strip()
    from_address = os.getenv("EARNINGS_ENGINE_EMAIL_FROM", "").strip()
    to_addresses = _parse_env_list(os.getenv("EARNINGS_ENGINE_EMAIL_TO", ""))
    return EmailSettings(
        enabled=enabled,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        from_address=from_address,
        to_addresses=to_addresses,
    )


def market_of(ticker: str) -> str:
    """Infer market code from a yfinance ticker symbol."""
    return "IN" if ticker.endswith(".NS") else "US"
