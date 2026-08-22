"""Playground #1 — yfinance market-data sandbox.

Exercises the ``yfinance`` API the same way earnings-engine does:
- OHLCV price history (``Ticker.history``)
- ``fast_info`` market cap / price (with ``.info`` fallback)
- Earnings dates calendar (``get_earnings_dates``, limit=60)
- Market inference via ``market_of()`` (``.NS`` suffix => IN market)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root:  python playground/01_yfinance_playground.py
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from earnings_engine.config import market_of
from playground.playground_utils import C, err, fmt_num, fmt_pct, heading, info, ok, prompt_ticker, subheading, warn


def show_price_history(symbol: str) -> None:
    subheading(f"OHLCV price history for {symbol}")
    import yfinance as yf

    try:
        df = yf.Ticker(symbol).history(period="1mo", interval="1d")
    except Exception as e:
        err(f"history() failed: {e}")
        return

    if df.empty:
        warn("No price data returned (ticker may not exist or suffix may be wrong).")
        return

    info(f"{len(df)} rows, columns: {list(df.columns)}")
    last = df.iloc[-1]
    ok(
        f"last close: {fmt_num(last.get('Close'))}  "
        f"open: {fmt_num(last.get('Open'))}  "
        f"high: {fmt_num(last.get('High'))}  "
        f"low: {fmt_num(last.get('Low'))}"
    )
    print(df.tail(5)[["Open", "High", "Low", "Close", "Volume"]].to_string())


def show_fast_info(symbol: str) -> None:
    subheading(f"fast_info / .info fallback for {symbol}")
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    try:
        fi = ticker.fast_info or {}
        mc = fi.get("market_cap")
        price = fi.get("last_price")
        info(f"fast_info keys: {sorted(fi.keys()) if isinstance(fi, dict) else 'n/a'}")
    except Exception as e:
        warn(f"fast_info failed ({e}); falling back to .info")
        mc, price = None, None

    if mc is None or price is None:
        try:
            info_dict = ticker.info or {}
            mc = info_dict.get("marketCap", mc)
            price = info_dict.get("currentPrice", info_dict.get("regularMarketPrice", price))
        except Exception as e:
            warn(f".info also failed: {e}")

    ok(f"market_cap: {fmt_num(mc)}  |  last_price: {fmt_num(price)}")


def show_earnings_dates(symbol: str) -> None:
    subheading(f"Earnings calendar for {symbol} (yfinance get_earnings_dates, limit=60)")
    import yfinance as yf

    try:
        ticker = yf.Ticker(symbol)
        ed = getattr(ticker, "earnings_dates", None)
        if ed is None:
            warn("earnings_dates attribute not available for this ticker.")
            return
        if isinstance(ed, pd.DataFrame) and not ed.empty:
            info(f"got {len(ed)} rows (may contain future + past dates)")
            print(ed.head(10).to_string())
        else:
            warn(f"earnings_dates empty/None: {type(ed).__name__}")
    except Exception as e:
        err(f"earnings_dates failed: {e}")


def show_market_inference(symbol: str) -> None:
    subheading("Market inference via market_of()")
    ok(f"{symbol} -> market_of() = {market_of(symbol)}  ('.NS' suffix => IN market)")


def main() -> None:
    heading("yfinance Playground")

    symbol = prompt_ticker("RELIANCE.NS")
    # Make sure the .NS suffix is present for an NSE-style ticker.
    if len(sys.argv) > 1:
        symbol = sys.argv[1]

    info(f"Using ticker: {symbol}  (yfinance version {__import__('yfinance').__version__})")

    show_market_inference(symbol)
    show_price_history(symbol)
    show_fast_info(symbol)
    show_earnings_dates(symbol)

    heading("Done")
    info(
        "Pro tip: many yfinance methods (history, info, fast_info, earnings_dates) are "
        "exercised in earnings-engine/data/ (prices.py, market_context.py, universe.py)."
    )


if __name__ == "__main__":
    main()