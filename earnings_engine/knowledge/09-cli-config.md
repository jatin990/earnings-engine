# 09 — CLI, Config, Logging, Emailing

> Related: [07-reports](07-reports.md) → [08-api-dashboard](08-api-dashboard.md) → [13-config-env](13-config-env.md)

## `config.py`
**Constants:**
- `PROJECT_ROOT = Path(__file__).resolve().parent.parent`
- `DATA_DIR = PROJECT_ROOT / "data"`
- `CACHE_DIR = DATA_DIR / "cache"`
- `PRICES_DIR = CACHE_DIR / "prices"`
- `EARNINGS_DIR = CACHE_DIR / "earnings"`
- `MARKETS = {"IN": {"suffix": ".NS", "name": "NSE India"}, "US": {"suffix": "", "name": "United States"}}`

**Classes:**
- `Settings` (dataclass):
  - `history_start: str = "2015-01-01"`
  - `cache_max_age_days: int = 1`
  - `request_pause_secs: float = 0.5`
  - `markets: tuple[str, ...] = ("IN", "US")`
  - `data_dirs: dict = {"prices": PRICES_DIR, "earnings": EARNINGS_DIR}`
  - `ensure_dirs() -> None`
- `EmailSettings` (dataclass):
  - `enabled: bool = False`
  - `smtp_host: str = "smtp.gmail.com"`
  - `smtp_port: int = 587`
  - `smtp_username: str`
  - `smtp_password: str`
  - `from_address: str`
  - `to_addresses: tuple[str, ...]`

**Functions:**
- `load_email_settings() -> EmailSettings` — reads from env vars
- `market_of(ticker: str) -> str` — returns "IN" if `.NS` suffix, else "US"

## `cli.py`
**Commands:**
- `ingest` — download prices + earnings + market cap for tickers
- `calendar` — show upcoming earnings from cache
- `upcoming-results` — enrich + render HTML/CSV report
- `build-dataset` — build full event dataset
- `backtest` — walk-forward backtest
- `predict` — score upcoming events
- `test-email` — send latest report via email

**Key options:**
- `--market`: IN, US, NSE_ALL (all NSE stocks via nsetools), or NSE_LARGE_CAP (NSE stocks with market cap > 1000cr)
- `ingest` now also fetches and caches market cap for all tickers (with ticker-level freshness check)
- `--ticker / -t`: specific tickers
- `--universe-file`: plain-text ticker list
- `--force`: ignore cache freshness
- `--days`: look-ahead window (default 14)
- `--incremental`: `ingest` only fetches earnings for tickers that are missing earnings data (skips already-cached and too-new/na-listed tickers) — faster than a full earnings fetch
- `--start-date` / `--from`: start date (YYYY-MM-DD) for the look-ahead window on `calendar`, `upcoming-results`, and `predict` (defaults to today; window = `[start_date, start_date + days)`)
- `--check`: run the report checker subworkflow after generating an `upcoming-results` report
- `check-report --csv <path>`: standalone command that verifies every field in an existing report CSV against the database
- `audit-strategy` command group:
  - `audit-strategy log`: log single or bulk prediction (`--ticker`, `--strategy`, `--signal`, `--confidence`, `--file`)
  - `audit-strategy run`: evaluate pending predictions against actual closing prices (`--force`)
  - `audit-strategy metrics`: display terminal performance table with Win Rate %, Profit Factor, Sharpe, Brier Score (`-s <strategy>`)
  - `audit-strategy import-kronos`: import existing Kronos predictions from `kronos_predictions` into the audit ledger
  - `audit-strategy backtest`: run 1-year historical simulation across all strategies (`--strategy`, `--days`, `--universe`)


## `logging_utils.py`
**Functions:**
- `get_logger(name="earnings_engine", base_dir=None) -> logging.Logger`
- Creates per-run log file: `logs/earnings_engine-{YYYY-MM-DD-HHMMSS}.log`
- All loggers share the same file handler; stream to console too

## `emailing.py`
**Function:**
- `send_report_email(csv_path, settings, body=None, html_path=None) -> None`
- Attaches CSV + optional HTML, sends via SMTP with STARTTLS