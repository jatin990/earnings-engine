# Phase 1 — Scaffold & Data Layer

**Status: Complete** (2026-06-10)

## Goal

Stand up the project skeleton and a reliable, cached data layer that everything
downstream (features, labels, models, backtests) builds on. After this phase the
engine can ingest daily prices and earnings dates for Indian (NSE) and US stocks
and show an upcoming-earnings calendar — no modeling yet.

## What was built

```
earnings-engine/
├── earnings_engine/
│   ├── config.py              # Settings, paths, market suffix conventions
│   ├── cli.py                 # `earnings-engine ingest | calendar`
│   └── data/
│       ├── universe.py        # ticker lists from plain-text files
│       ├── universes/         # nse_top.txt (50 NSE), us_top.txt (50 US)
│       ├── prices.py          # yfinance OHLCV → parquet cache
│       └── earnings.py        # yfinance earnings dates → parquet cache
├── data/cache/                # parquet cache (gitignored)
├── tests/                     # 8 tests, all offline (yfinance mocked)
└── docs/                      # this file + future phase docs
```

## Design decisions

- **Market-agnostic core.** A ticker's market is inferred from its yfinance
  suffix (`.NS` → India, none → US). No per-market code paths downstream.
- **One parquet file per ticker** under `data/cache/{prices,earnings}/`.
  Files fresher than `Settings.cache_max_age_days` (default 1 day) are reused;
  `--force` re-downloads. Empty earnings results are cached too, so tickers
  with no coverage don't get re-queried every run.
- **Full-history refresh, not incremental appends.** Daily bars for ~100
  tickers are tiny; re-downloading is simpler and avoids append-edge bugs.
- **Earnings source is swappable.** `data/earnings.py` is the single source of
  earnings dates. yfinance NSE coverage is patchy — when that becomes a
  problem, plug NSE corporate-announcement scraping into this module without
  touching anything downstream.
- **Rate limiting:** 0.5 s pause between yfinance requests
  (`Settings.request_pause_secs`).

## Data schemas

**Prices** (per ticker): index `date` (naive datetime), columns
`open, high, low, close, volume`. Prices are dividend/split adjusted
(`auto_adjust=True`), history from 2015-01-01.

**Earnings** (per ticker): columns `earnings_date` (naive, normalized to
midnight UTC), `eps_estimate`, `eps_reported`, `surprise_pct`. Past and
upcoming events together; EPS fields are mostly populated for US tickers only.

## Gotchas found during the build

1. **yfinance needs `lxml`** for `get_earnings_dates()` — it's now a declared
   dependency. Without it the call raises ImportError and you silently get
   no earnings data.
2. **Mixed timezone offsets break naive parsing.** US earnings timestamps mix
   EDT (−04:00) and EST (−05:00) within one frame; `pd.to_datetime` then
   returns object dtype and `.dt` access fails. Fixed by parsing with
   `utc=True` before stripping the timezone. Regression test covers it.
3. **NSE earnings via yfinance have dates but no EPS estimates** for most
   tickers, and history depth varies. Direction labels (Phase 2) only need
   the date + prices, so this is acceptable for now.

## Usage

```bash
# install
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# ingest both universes (prices + earnings)
.venv/bin/earnings-engine ingest                 # full ~100-ticker run
.venv/bin/earnings-engine ingest --market IN     # NSE only
.venv/bin/earnings-engine ingest -t AAPL -t TCS.NS

# upcoming earnings from cache
.venv/bin/earnings-engine calendar --days 30

# tests (offline, yfinance mocked)
.venv/bin/pytest
```

## Verification

- 8/8 tests pass (universe loading, cache roundtrip, freshness, empty-result
  caching, mixed-timezone normalization).
- Live smoke test: RELIANCE.NS → 2,825 daily bars (2015→today) + earnings
  events incl. upcoming 2026-07-17; AAPL → 2,876 bars + 100 earnings events
  incl. upcoming 2026-07-30.

## Next: Phase 2 — Event dataset, features & labels

Build the point-in-time event table (one row per ticker × earnings event):
pre-earnings price/volume features computed strictly from data before the
announcement, and the 1-day post-earnings direction label. Deliverable doc:
feature dictionary.
