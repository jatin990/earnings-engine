"""Central configuration: paths, markets, and data settings."""

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def market_of(ticker: str) -> str:
    """Infer market code from a yfinance ticker symbol."""
    return "IN" if ticker.endswith(".NS") else "US"
