"""Central configuration: paths, markets, and data settings."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

if os.getenv("VERCEL") == "1" and not os.getenv("EARNINGS_ENGINE_DATA_DIR"):
    DATA_DIR = Path("/tmp/data")
else:
    DATA_DIR = Path(os.getenv("EARNINGS_ENGINE_DATA_DIR", str(PROJECT_ROOT / "data")))

CACHE_DIR = DATA_DIR / "cache"
PRICES_DIR = CACHE_DIR / "prices"
EARNINGS_DIR = CACHE_DIR / "earnings"

# Markets are identified by ticker suffix conventions used by yfinance.
MARKETS = {
    "IN": {"suffix": ".NS", "name": "NSE India"},
    "US": {"suffix": "", "name": "United States"},
}


def _env_int(name: str, default: int) -> int:
    """Read an integer from the environment with a fallback default."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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
    # Concurrency: price/earnings ingestion workers.
    price_fetch_workers: int = field(
        default_factory=lambda: _env_int("EARNINGS_ENGINE_PRICE_FETCH_WORKERS", 10)
    )
    # Concurrency: GBM feature-building loop (per upcoming-earnings event).
    gbm_feature_workers: int = field(
        default_factory=lambda: _env_int("EARNINGS_ENGINE_GBM_FEATURE_WORKERS", 8)
    )
    # Concurrency: Kronos historical-data fetch (I/O-bound, parallel).
    kronos_fetch_workers: int = field(
        default_factory=lambda: _env_int("EARNINGS_ENGINE_KRONOS_FETCH_WORKERS", 8)
    )
    # Kronos GPU batch size: number of ticker sequences per forward pass.
    # Batching sequences into one tensor is far more efficient (and safer on a
    # 6GB 3060) than spawning concurrent threads that hammer the same model.
    kronos_gpu_batch_size: int = field(
        default_factory=lambda: _env_int("EARNINGS_ENGINE_KRONOS_GPU_BATCH_SIZE", 2)
    )
    # Concurrency: Ollama explanation calls (local network, parallel).
    kronos_explain_workers: int = field(
        default_factory=lambda: _env_int("EARNINGS_ENGINE_KRONOS_EXPLAIN_WORKERS", 4)
    )
    # Inference device for Kronos model: "cuda", "cuda:0", "cpu", or "" (auto-detect).
    kronos_device: str = field(
        default_factory=lambda: os.getenv("EARNINGS_ENGINE_KRONOS_DEVICE", "").strip()
    )

    def resolve_device(self, preferred: str | None = None) -> str:
        """Resolve the model inference device for Kronos."""
        return get_default_device(preferred or self.kronos_device)

    def ensure_dirs(self) -> None:
        for d in self.data_dirs.values():
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class EmailSettings:
    """SMTP settings for emailing generated reports."""

    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: tuple[str, ...] = ()


def _parse_env_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.replace(";", ",").split(",") if part.strip())


def load_email_settings() -> EmailSettings:
    return EmailSettings(
        enabled=os.getenv("EARNINGS_ENGINE_EMAIL_ENABLED", "false").strip().lower() == "true",
        smtp_host=os.getenv("EARNINGS_ENGINE_SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_env_int("EARNINGS_ENGINE_SMTP_PORT", 587),
        smtp_username=os.getenv("EARNINGS_ENGINE_SMTP_USERNAME", ""),
        smtp_password=os.getenv("EARNINGS_ENGINE_SMTP_PASSWORD", ""),
        from_address=os.getenv("EARNINGS_ENGINE_EMAIL_FROM", ""),
        to_addresses=_parse_env_list(os.getenv("EARNINGS_ENGINE_EMAIL_TO")),
    )


def market_of(ticker: str) -> str:
    """Infer market code from a yfinance ticker symbol."""
    return "IN" if ticker.endswith(".NS") else "US"


def get_default_device(preferred: str | None = None) -> str:
    """Return the resolved PyTorch device for Kronos inference.

    Checks preferred argument, then EARNINGS_ENGINE_KRONOS_DEVICE, then auto-detects CUDA.
    """
    if preferred and preferred.strip():
        pref = preferred.strip().lower()
        if pref == "cuda":
            return "cuda:0"
        return pref
    env_dev = os.getenv("EARNINGS_ENGINE_KRONOS_DEVICE", "").strip().lower()
    if env_dev:
        if env_dev == "cuda":
            return "cuda:0"
        return env_dev
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"

