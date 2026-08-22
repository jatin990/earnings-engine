"""Playground #2 — NSE universe sandbox (nsetools + yfinance).

Exercises the NSE universe layer the same way earnings-engine does:
- ``load_nse_all()`` — full NSE stock-code list via ``nsetools`` (``.NS`` suffix appended)
- ``load_nse_large_cap()`` — NSE stocks with market cap > 1000 cr via yfinance ``fast_info``
- ``load_universe("IN")`` / ``load_universe("US")`` — the configured top lists
- Market cap cache / freshness checks (``ticker_market_cap`` table)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root:  python playground/02_nse_playground.py
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from earnings_engine.config import Settings
from earnings_engine.data.universe import (
    NSE_ALL_FILE,
    NSE_LARGE_CAP_FILE,
    load_all,
    load_market_cap,
    load_nse_all,
    load_nse_large_cap,
    load_universe,
)
from playground.playground_utils import C, err, fmt_num, heading, info, ok, subheading, warn


def show_nse_all() -> None:
    subheading("NSE all-stock universe (nsetools)")
    try:
        tickers = load_nse_all(force_refresh=False)
        ok(f"load_nse_all() returned {len(tickers)} tickers")
    except Exception as e:
        err(f"load_nse_all() failed: {e}")
        tickers = []

    if tickers:
        info(f"cache file: {NSE_ALL_FILE} (exists={NSE_ALL_FILE.exists()})")
        info(f"first 10: {', '.join(tickers[:10])}")
        print(f"  … {', '.join(tickers[-5:])}")


def show_nse_large_cap() -> None:
    subheading("NSE large-cap universe (> 1000 cr, via yfinance fast_info)")
    try:
        tickers = load_nse_large_cap(force_refresh=False)
        ok(f"load_nse_large_cap() returned {len(tickers)} tickers")
    except Exception as e:
        err(f"load_nse_large_cap() failed: {e}")
        tickers = []

    if tickers:
        info(f"cache file: {NSE_LARGE_CAP_FILE} (exists={NSE_LARGE_CAP_FILE.exists()})")
        info(f"first 15: {', '.join(tickers[:15])}")


def show_configured_universes() -> None:
    subheading("Configured universes")
    for market in ("IN", "US"):
        try:
            tickers = load_universe(market)
            ok(f"load_universe({market!r}) -> {len(tickers)} tickers")
            info(f"  first 5: {', '.join(tickers[:5])}")
        except Exception as e:
            err(f"load_universe({market!r}) failed: {e}")

    try:
        all_tickers = load_all()
        ok(f"load_all() -> {len(all_tickers)} combined tickers (IN + US)")
    except Exception as e:
        err(f"load_all() failed: {e}")


def show_market_cap_cache() -> None:
    subheading("Market cap cache (SQLite ticker_market_cap table)")
    settings = Settings()
    for ticker in ("RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"):
        mc = load_market_cap(ticker, settings)
        if mc is not None:
            ok(f"{ticker}: ₹{fmt_num(mc)}")
        else:
            warn(f"{ticker}: not cached (call ingest_market_caps to populate)")


def main() -> None:
    heading("NSE Playground (nsetools + yfinance universes)")

    show_nse_all()
    show_nse_large_cap()
    show_configured_universes()
    show_market_cap_cache()

    heading("Done")
    info(
        "Tip: these functions are backed by data/universe.py — "
        "nse_all pulls from nsetools, nse_large_cap from yfinance fast_info, "
        "both with 7-day file freshness."
    )


if __name__ == "__main__":
    main()