"""Helpers for enriching upcoming earnings results with market context."""

from __future__ import annotations

import time
import pandas as pd
import yfinance as yf
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.earnings import load_earnings
from earnings_engine.data.prices import fetch_prices, load_price_metrics, load_prices, store_price_metrics
from earnings_engine.data.universe import is_market_cap_fresh, load_market_cap, load_all_market_caps, store_market_cap
from earnings_engine.data.swing_ranges import get_swing_range, record_auto_range
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.market_context")

_ORIGINAL_FETCH_PRICES = prices_mod.fetch_prices
_ORIGINAL_LOAD_PRICES = prices_mod.load_prices
_ORIGINAL_LOAD_EARNINGS = load_earnings
_ORIGINAL_LOAD_PRICE_METRICS = prices_mod.load_price_metrics


def _score_surprise(surprise: float) -> int:
    """Map a single EPS surprise % to a 1-9 quality score."""
    if surprise >= 15:
        return 9
    if surprise >= 10:
        return 8
    if surprise >= 5:
        return 7
    if surprise >= 0:
        return 6
    if surprise >= -5:
        return 5
    if surprise >= -10:
        return 4
    return 3


def generate_quarter_result_ai_note(
    quarter_label: str,
    earnings_date: str | pd.Timestamp | None,
    score: int | None,
    surprise_pct: float | None = None,
    eps_reported: float | None = None,
    eps_estimate: float | None = None,
    week_high_pct: float | None = None,
    week_low_pct: float | None = None,
    price_7d: float | None = None,
) -> str:
    """Generate an institutional AI summary of how the quarterly result performed."""
    parts = []
    q_name = quarter_label.upper()
    date_str = ""
    if earnings_date:
        try:
            date_str = f" on {pd.Timestamp(earnings_date).strftime('%b %d, %Y')}"
        except Exception:
            date_str = f" on {earnings_date}"

    # 1. Earnings Surprise & Numbers
    if surprise_pct is not None and not pd.isna(surprise_pct):
        surp_val = float(surprise_pct)
        if surp_val > 15:
            header = f"🔥 {q_name} Blowout Beat{date_str}: EPS crushed estimates by {surp_val:+.1f}%"
        elif surp_val > 5:
            header = f"📈 {q_name} Strong Beat{date_str}: EPS beat consensus by {surp_val:+.1f}%"
        elif surp_val >= 0:
            header = f"✅ {q_name} In-Line/Slight Beat{date_str}: EPS exceeded targets by {surp_val:+.1f}%"
        elif surp_val > -10:
            header = f"⚠️ {q_name} Slight Miss{date_str}: EPS missed estimates by {surp_val:.1f}%"
        else:
            header = f"📉 {q_name} Severe Miss{date_str}: EPS missed consensus by {surp_val:.1f}%"

        if eps_reported is not None and eps_estimate is not None and not pd.isna(eps_reported) and not pd.isna(eps_estimate):
            header += f" (Reported: ₹{float(eps_reported):.2f} vs Est: ₹{float(eps_estimate):.2f})"
        parts.append(header)
    elif score is not None:
        if score >= 8:
            parts.append(f"🔥 {q_name} High Quality Print{date_str}: Solid fundamental delivery (Score {score}/9)")
        elif score >= 6:
            parts.append(f"📈 {q_name} Constructive Result{date_str}: Met expectations with positive bias (Score {score}/9)")
        elif score == 5:
            parts.append(f"⚖️ {q_name} Neutral Result{date_str}: Balanced print (Score {score}/9)")
        else:
            parts.append(f"📉 {q_name} Subdued Result{date_str}: Result showed contraction (Score {score}/9)")
    else:
        parts.append(f"ℹ️ {q_name} Result{date_str}: Historic quarterly print")

    # 2. Market / Price Reaction
    reaction_parts = []
    if week_high_pct is not None and not pd.isna(week_high_pct):
        reaction_parts.append(f"Peak move: {float(week_high_pct):+.1f}% high")
    if week_low_pct is not None and not pd.isna(week_low_pct):
        reaction_parts.append(f"Drawdown: {float(week_low_pct):+.1f}% low")
    if price_7d is not None and not pd.isna(price_7d):
        reaction_parts.append(f"7D Post-Close: ₹{float(price_7d):,.0f}")

    if reaction_parts:
        parts.append("Reaction: " + " | ".join(reaction_parts))

    return " • ".join(parts)


def _close_n_calendar_days_ago(closes: pd.Series, latest_date, days: int) -> float | None:
    """Return the closing price on the last trading day on/before ``days`` calendar
    days before ``latest_date``.

    ``closes`` is a Series indexed by timestamp, sorted ascending.  ``days`` is a
    CALENDAR-day count (e.g. 30 = one month) so returns match how external sources
    report an "N-day" return, rather than N trading days (which spans ~N*1.4 cal
    days and overstates the move).
    """
    target = latest_date - pd.Timedelta(days=days)
    before = closes[closes.index <= target]
    if before.empty:
        return None
    return float(before.iloc[-1])



def _week_high_low_around(
    prices: pd.DataFrame,
    earnings_date: pd.Timestamp | str,
    days: int = 7,
    current_price: float | None = None,
    day_high: float | None = None,
    day_low: float | None = None,
) -> tuple[float, float, float, float, pd.Timestamp, pd.Timestamp] | None:
    """Compute the true highest and lowest price point reached since earnings date vs pre-earnings base close.

    Returns (high_pct, low_pct, high_price, low_price, high_date, low_date).
    Uses high/low intraday levels if available in prices DataFrame, otherwise closes.
    """
    if prices is None or prices.empty:
        return None

    df = prices.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        else:
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                return None

    # Strip timezone to prevent comparison errors with tz-naive timestamps
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)

    ed_raw = pd.to_datetime(earnings_date)
    if getattr(ed_raw, "tz", None) is not None:
        ed_raw = ed_raw.tz_localize(None)
    ed = ed_raw.normalize()

    df.columns = [str(c).lower() for c in df.columns]
    if "close" not in df.columns:
        return None

    closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    if closes.empty:
        return None

    # Base close = last close strictly before the earnings date (or on earnings date if first available)
    before = closes[closes.index < ed]
    if before.empty:
        before = closes[closes.index <= ed]
    if before.empty:
        return None
    base_close = float(before.iloc[-1])
    if base_close <= 0:
        return None

    # Highs and Lows series (use intraday high/low if present and non-empty, otherwise close)
    highs = pd.to_numeric(df["high"], errors="coerce").dropna() if "high" in df.columns else pd.Series(dtype=float)
    if highs.empty:
        highs = closes
    lows = pd.to_numeric(df["low"], errors="coerce").dropna() if "low" in df.columns else pd.Series(dtype=float)
    if lows.empty:
        lows = closes

    # Window of post-earnings price action: trading days strictly AFTER the earnings date
    window_highs = highs[highs.index > ed].iloc[:days].copy()
    window_lows = lows[lows.index > ed].iloc[:days].copy()

    # If recent print and no subsequent trading days closed yet, fallback to earnings_date itself
    if window_highs.empty:
        window_highs = highs[highs.index >= ed].iloc[:days].copy()
        window_lows = lows[lows.index >= ed].iloc[:days].copy()

    today = pd.Timestamp.today().normalize()
    closed_days_after = highs[(highs.index > ed) & (highs.index < today)]
    if current_price is not None and float(current_price) > 0 and today >= ed and (len(closed_days_after) < days or today in window_highs.index):
        curr_p = float(current_price)
        hi_p = float(day_high) if day_high is not None and float(day_high) > 0 else curr_p
        lo_p = float(day_low) if day_low is not None and float(day_low) > 0 else curr_p

        if today in window_highs.index:
            window_highs[today] = max(float(window_highs[today]), hi_p)
        else:
            window_highs[today] = hi_p

        if today in window_lows.index:
            window_lows[today] = min(float(window_lows[today]), lo_p)
        else:
            window_lows[today] = lo_p

    if window_highs.empty or window_lows.empty:
        return None

    week_high = float(window_highs.max())
    week_low = float(window_lows.min())
    high_pct = (week_high / base_close - 1.0) * 100.0
    low_pct = (week_low / base_close - 1.0) * 100.0

    high_date = window_highs.idxmax()
    low_date = window_lows.idxmin()

    return high_pct, low_pct, week_high, week_low, high_date, low_date


def _price_after_earnings(prices: pd.DataFrame, earnings_date: pd.Timestamp, days: int = 7) -> float | None:
    """Get the price N working days after an earnings announcement.

    Returns the closing price on the Nth trading day after the earnings date,
    or None if there isn't enough price data.
    """
    if prices.empty or "close" not in prices.columns:
        return None
    closes = pd.to_numeric(prices["close"], errors="coerce").dropna()
    if closes.empty:
        return None

    # Get all trading days after the earnings date
    after_earnings = closes[closes.index > earnings_date]
    if len(after_earnings) < days:
        return None

    # Get the price on the Nth trading day after earnings
    price_after = float(after_earnings.iloc[days - 1])
    return price_after if price_after > 0 else None


def detect_swing_range(closes: pd.Series) -> dict[str, Any]:
    """Detect current swing range, 3-month range history, cycles, and timing from price history.

    - 20-day range (current swing channel): min/max of last 20 trading days
    - 3-month range (macro channel): min/max of last ~65 trading days
    - Monthly breakdown: 30-day buckets over the past 3 months
    - Cycle oscillations: transitions between lower 25% and upper 75% of channel
    """
    if closes is None or (hasattr(closes, "empty") and closes.empty):
        return {
            "lower": None, "upper": None, "cycles": 0, "avg_days": 0, "cycles_data": [],
            "three_month_lower": None, "three_month_upper": None, "monthly_ranges": [],
        }

    if isinstance(closes, pd.DataFrame):
        closes = closes["close"] if "close" in closes.columns else closes.iloc[:, 0]

    # Ensure clean series sorted by date/index
    clean_closes = pd.to_numeric(closes, errors="coerce").dropna()
    if clean_closes.empty:
        return {
            "lower": None, "upper": None, "cycles": 0, "avg_days": 0, "cycles_data": [],
            "three_month_lower": None, "three_month_upper": None, "monthly_ranges": [],
        }

    # Helper to convert index/date to ISO date string and pd.Timestamp
    def parse_dt(d: Any) -> tuple[str, pd.Timestamp]:
        try:
            ts = pd.to_datetime(d)
            if pd.isna(ts):
                return str(d), pd.Timestamp.now()
            return ts.strftime("%Y-%m-%d"), ts
        except Exception:
            return str(d), pd.Timestamp.now()

    # 1. 20-day Current Channel
    recent_20 = clean_closes.tail(20)
    lower = round(float(recent_20.min()), 2)
    upper = round(float(recent_20.max()), 2)

    # 2. 3-Month (65 trading days) Channel
    recent_65 = clean_closes.tail(65)
    three_month_lower = round(float(recent_65.min()), 2)
    three_month_upper = round(float(recent_65.max()), 2)

    # 3. Monthly Breakdown Ranges (last 3 months)
    monthly_ranges: list[dict[str, Any]] = []
    n_days = len(recent_65)

    segments = [
        ("Current Month (Last ~20D)", recent_65.tail(20)),
        ("Previous Month (20–40D Ago)", recent_65.iloc[-min(40, n_days):-20] if n_days > 20 else pd.Series(dtype=float)),
        ("3 Months Ago (40–65D Ago)", recent_65.iloc[-min(65, n_days):-min(40, n_days)] if n_days > 40 else pd.Series(dtype=float)),
    ]

    for label, seg in segments:
        if not seg.empty:
            s_low = round(float(seg.min()), 2)
            s_high = round(float(seg.max()), 2)
            first_date_str, _ = parse_dt(seg.index[0])
            last_date_str, _ = parse_dt(seg.index[-1])
            spread = ((s_high - s_low) / s_low * 100) if s_low > 0 else 0.0
            monthly_ranges.append({
                "period": label,
                "start": first_date_str,
                "end": last_date_str,
                "lower": s_low,
                "upper": s_high,
                "spread_pct": round(spread, 1),
            })

    # 4. Cycle Oscillations Detection over the 3-Month Window
    cycles_data: list[dict[str, Any]] = []
    if lower < upper:
        threshold_low = lower + (upper - lower) * 0.25
        threshold_high = lower + (upper - lower) * 0.75

        state = "neutral"
        start_date_val = None
        start_ts = None
        min_p = None
        max_p = None

        for date_idx, price in recent_65.items():
            date_str, ts = parse_dt(date_idx)
            price = float(price)

            if state == "neutral":
                if price <= threshold_low:
                    state = "low"
                    start_date_val = date_str
                    start_ts = ts
                    min_p = price
                    max_p = price
                elif price >= threshold_high:
                    state = "high"
                    start_date_val = date_str
                    start_ts = ts
                    min_p = price
                    max_p = price
            elif state == "low":
                min_p = min(min_p, price) if min_p is not None else price
                max_p = max(max_p, price) if max_p is not None else price
                if price >= threshold_high:
                    state = "high"
            elif state == "high":
                min_p = min(min_p, price) if min_p is not None else price
                max_p = max(max_p, price) if max_p is not None else price
                if price <= threshold_low:
                    if start_ts is not None:
                        duration_days = max(1, (ts - start_ts).days)
                        cycles_data.append({
                            "start": start_date_val,
                            "end": date_str,
                            "duration": float(duration_days),
                            "lower": round(float(min_p), 2) if min_p is not None else lower,
                            "upper": round(float(max_p), 2) if max_p is not None else upper,
                        })
                    state = "low"
                    start_date_val = date_str
                    start_ts = ts
                    min_p = price
                    max_p = price

    cycles = len(cycles_data)
    avg_days = sum(c["duration"] for c in cycles_data) / cycles if cycles > 0 else 0.0

    return {
        "lower": lower,
        "upper": upper,
        "cycles": cycles,
        "avg_days": round(avg_days, 1),
        "cycles_data": cycles_data,
        "three_month_lower": three_month_lower,
        "three_month_upper": three_month_upper,
        "monthly_ranges": monthly_ranges,
    }


def calculate_trading_range_by_method(
    prices_df: pd.DataFrame,
    method: str = "20d",
) -> dict[str, Any]:
    """Calculate the support/resistance trading range across various methodologies.

    Supported methods:
      - '20d': 20-Day Swing Channel (min/max of last 20 trading days)
      - '65d_3m': 3-Month Positional Channel (min/max of last 65 trading days)
      - 'atr_14': 14-Day ATR Volatility Envelope (Close +/- 2.0 * ATR14)
      - '52w': 52-Week Range (Min/Max over trailing 252 trading sessions)
      - 'pivot_classic': Floor Pivot Support S1 / Resistance R1
      - 'fibonacci': Fibonacci Retracement Levels (23.6% Support / 78.6% Resistance of 65D move)
    """
    if prices_df is None or prices_df.empty:
        return {
            "success": False,
            "error": "No price history available",
            "lower": None,
            "upper": None,
            "current_price": None,
            "spread_pct": 0.0,
            "method": method,
        }

    df = prices_df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    
    # Standardize column names
    col_map = {c: c.lower() for c in df.columns if isinstance(c, str)}
    df = df.rename(columns=col_map)

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].squeeze(), errors="coerce")
    
    df = df.dropna(subset=["close"])
    if df.empty:
        return {
            "success": False,
            "error": "Clean price series is empty",
            "lower": None,
            "upper": None,
            "current_price": None,
            "spread_pct": 0.0,
            "method": method,
        }

    # Clean extreme bad ticks or corrupted low/high anomalies
    if "low" in df.columns:
        df["low"] = df["low"].where(df["low"] >= 0.5 * df["close"], df["close"])
    if "high" in df.columns:
        df["high"] = df["high"].where(df["high"] <= 2.0 * df["close"], df["close"])

    current_price = round(float(df["close"].iloc[-1]), 2)
    method_key = (method or "20d").lower().strip()

    lower = None
    upper = None
    method_name = "20-Day Swing Channel"
    explanation = ""

    if method_key in ("20d", "20_day", "swing"):
        seg = df.tail(20)
        low_val = seg["low"].min() if "low" in seg.columns else seg["close"].min()
        high_val = seg["high"].max() if "high" in seg.columns else seg["close"].max()
        lower = round(float(low_val), 2)
        upper = round(float(high_val), 2)
        method_name = "20-Day Swing Channel"
        explanation = f"Detected from 20-day price oscillation extreme lows (₹{lower}) to highs (₹{upper})."

    elif method_key in ("65d_3m", "3m", "quarter", "positional"):
        seg = df.tail(65)
        low_val = seg["low"].min() if "low" in seg.columns else seg["close"].min()
        high_val = seg["high"].max() if "high" in seg.columns else seg["close"].max()
        lower = round(float(low_val), 2)
        upper = round(float(high_val), 2)
        method_name = "3-Month Positional Channel"
        explanation = f"Calculated over 65 trading sessions (past 3 months): Support ₹{lower}, Resistance ₹{upper}."

    elif method_key in ("atr_14", "atr", "volatility"):
        if len(df) >= 15 and all(k in df.columns for k in ["high", "low", "close"]):
            high = df["high"]
            low = df["low"]
            close_prev = df["close"].shift(1)
            tr1 = high - low
            tr2 = (high - close_prev).abs()
            tr3 = (low - close_prev).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_14 = float(tr.tail(14).mean())
            lower = round(max(0.01, current_price - (2.0 * atr_14)), 2)
            upper = round(current_price + (2.0 * atr_14), 2)
            method_name = "14-Day ATR Volatility Envelope"
            explanation = f"14-Day ATR is ₹{round(atr_14, 2)}. Range is anchored at +/- 2.0x ATR around CMP (₹{current_price})."
        else:
            seg = df.tail(20)
            lower = round(float(seg["close"].min() * 0.96), 2)
            upper = round(float(seg["close"].max() * 1.04), 2)
            method_name = "14-Day Volatility Envelope"
            explanation = "Calculated using estimated 4% volatility band around recent close prices."

    elif method_key in ("52w", "52_week", "yearly"):
        seg = df.tail(252)
        low_val = seg["low"].min() if "low" in seg.columns else seg["close"].min()
        high_val = seg["high"].max() if "high" in seg.columns else seg["close"].max()
        lower = round(float(low_val), 2)
        upper = round(float(high_val), 2)
        method_name = "52-Week Historical High/Low Range"
        explanation = f"Annual 52-Week floor at ₹{lower} and ceiling at ₹{upper} across {len(seg)} sessions."

    elif method_key in ("pivot_classic", "pivot", "floor_pivot"):
        if len(df) >= 2 and all(k in df.columns for k in ["high", "low", "close"]):
            prev = df.iloc[-2]
            h = float(prev["high"])
            l = float(prev["low"])
            c = float(prev["close"])
            p = (h + l + c) / 3.0
            s1 = (2.0 * p) - h
            r1 = (2.0 * p) - l
            lower = round(max(0.01, s1), 2)
            upper = round(r1, 2)
            method_name = "Classic Floor Pivot Points (S1 / R1)"
            explanation = f"Classic Pivot Floor Support S1 (₹{lower}) and Resistance R1 (₹{upper}) from previous bar."
        else:
            seg = df.tail(20)
            lower = round(float(seg["close"].min()), 2)
            upper = round(float(seg["close"].max()), 2)
            method_name = "Pivot Channel"
            explanation = "Pivot estimate derived from recent extrema."

    elif method_key in ("fibonacci", "fib"):
        seg = df.tail(65)
        h = float(seg["high"].max() if "high" in seg.columns else seg["close"].max())
        l = float(seg["low"].min() if "low" in seg.columns else seg["close"].min())
        diff = h - l
        lower = round(l + (0.236 * diff), 2)
        upper = round(l + (0.786 * diff), 2)
        method_name = "Fibonacci Retracement Range (23.6% - 78.6%)"
        explanation = f"Fibonacci channel based on 65D range (Low: ₹{round(l, 2)}, High: ₹{round(h, 2)})."

    else:
        seg = df.tail(20)
        lower = round(float(seg["close"].min()), 2)
        upper = round(float(seg["close"].max()), 2)
        method_name = "20-Day Range"
        explanation = f"Default 20-day channel: ₹{lower} to ₹{upper}."

    spread_pct = round(((upper - lower) / lower * 100), 2) if lower and lower > 0 else 0.0

    return {
        "success": True,
        "method": method_key,
        "method_name": method_name,
        "current_price": current_price,
        "lower": lower,
        "upper": upper,
        "spread_pct": spread_pct,
        "explanation": explanation,
    }


def enrich_upcoming_results(df: pd.DataFrame, settings: Settings | None = None, force: bool = False) -> pd.DataFrame:
    """Append market-cap, price, and recent earnings context for each ticker.

    When ``force=True`` the once-per-day market-cap and price-metrics caches are
    bypassed so every ticker is re-fetched live from yfinance (used by the
    Playground console's LIVE flag).
    """
    if df.empty:
        return df.copy()

    settings = settings or Settings()
    tickers = df["ticker"].dropna().unique().tolist()
    if not tickers:
        return df.copy()

    t0_enrich = time.perf_counter()
    # Pre-fetch cached market caps, names, metrics, earnings, and prices in bulk
    all_market_caps: dict[str, float] = {}
    names_map: dict[str, str] = {}
    metrics_map: dict[str, dict[str, Any]] = {}
    earnings_map: dict[str, pd.DataFrame] = {}
    prices_map: dict[str, pd.DataFrame] = {}
    earnings_count_map: dict[str, int] = {}
    sr_map: dict[str, dict[str, Any]] = {}

    try:
        from earnings_engine.data.db import get_db_connection
        from collections import defaultdict
        import json
        conn = get_db_connection(settings)
        e_by_ticker = defaultdict(list)
        p_by_ticker = defaultdict(list)
        cutoff_e_date = (pd.Timestamp.now() - pd.Timedelta(days=730)).strftime("%Y-%m-%d")
        cutoff_p_date = (pd.Timestamp.now() - pd.Timedelta(days=450)).strftime("%Y-%m-%d")
        chunk_size = 200

        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            placeholders = ", ".join(["?"] * len(chunk))

            # 1. Unified Ticker Master (Names, Market Caps, Metrics in 1 query)
            try:
                ticker_master_rows = conn.execute(
                    f"SELECT ticker, name, market_cap, metrics FROM tickers WHERE ticker IN ({placeholders})",
                    chunk,
                ).fetchall()
                for r in ticker_master_rows:
                    sym = r[0]
                    if r[1]:
                        names_map[sym] = r[1]
                    if r[2] is not None and not force:
                        all_market_caps[sym] = float(r[2])
                    if r[3] and not force:
                        try:
                            metrics_map[sym] = json.loads(r[3]) if isinstance(r[3], str) else r[3]
                        except Exception:
                            pass
            except Exception:
                pass

            # 2. Earnings Counts (lifetime total for result sequence)
            try:
                cnt_rows = conn.execute(
                    f"SELECT ticker, COUNT(earnings_date) FROM earnings_history WHERE ticker IN ({placeholders}) GROUP BY ticker",
                    chunk,
                ).fetchall()
                for r in cnt_rows:
                    earnings_count_map[r[0]] = r[1]
            except Exception:
                pass

            # 3. Earnings History (last 2 years)
            try:
                e_rows = conn.execute(
                    f"SELECT ticker, earnings_date, eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker IN ({placeholders}) AND earnings_date >= ? ORDER BY ticker, earnings_date",
                    chunk + [cutoff_e_date],
                ).fetchall()
                for r in e_rows:
                    e_by_ticker[r[0]].append((r[1], r[2], r[3], r[4]))
            except Exception:
                pass

            # 4. Price History (last ~450 days)
            try:
                p_rows = conn.execute(
                    f"SELECT ticker, date, open, high, low, close, volume FROM price_history WHERE ticker IN ({placeholders}) AND date >= ? ORDER BY ticker, date",
                    chunk + [cutoff_p_date],
                ).fetchall()
                for r in p_rows:
                    p_by_ticker[r[0]].append((r[1], r[2], r[3], r[4], r[5], r[6]))
            except Exception:
                pass

            # 5. Stored Swing Ranges
            try:
                sr_rows = conn.execute(
                    f"SELECT ticker, lower_bound, upper_bound, source, cycles, avg_cycle_days, last_updated FROM swing_ranges WHERE ticker IN ({placeholders})",
                    chunk,
                ).fetchall()
                for r in sr_rows:
                    sr_map[r[0]] = {
                        "watchlist": "ALL",
                        "ticker": r[0],
                        "lower_bound": r[1],
                        "upper_bound": r[2],
                        "source": r[3],
                        "cycles": r[4],
                        "avg_cycle_days": r[5],
                        "last_updated": r[6],
                    }
            except Exception:
                pass

        for t, r_list in e_by_ticker.items():
            f = pd.DataFrame(r_list, columns=["earnings_date", "eps_estimate", "eps_reported", "surprise_pct"])
            f["earnings_date"] = pd.to_datetime(f["earnings_date"])
            earnings_map[t] = f

        for t, r_list in p_by_ticker.items():
            f = pd.DataFrame(r_list, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
            f.index = pd.to_datetime(f.index)
            prices_map[t] = f
    except Exception:
        pass

    # If force=True or if any tickers have missing prices, batch-fetch live quotes in parallel
    missing_or_forced = [t for t in tickers if force or t not in prices_map or prices_map[t].empty]
    if missing_or_forced:
        try:
            from earnings_engine.data.prices import fetch_batch_live_quotes
            fetch_batch_live_quotes(missing_or_forced, settings=settings, sync_db=True, max_workers=10)
        except Exception as e:
            logger.debug("[RESULTS-BATCH] Batch live quote fetch error: %s", e)

    t1_bulk = time.perf_counter()

    rows: list[dict] = []
    metrics_to_store: dict[str, dict[str, Any]] = {}
    market_caps_to_store: dict[str, float] = {}
    for ticker in tickers:
        try:
            company_name = names_map.get(ticker) or ticker.replace(".NS", "")
            market_cap = all_market_caps.get(ticker)
            current_price = None
            week_high = None
            week_low = None
            week_change = None
            pct_from_52w_high = None
            pct_from_52w_low = None
            thirty_day_return_pct = None
            seven_day_return_pct = None
            three_day_return_pct = None
            channel_position_pct = None
            earnings_week_move_pct = None
            earnings_week_high_pct = None
            earnings_week_low_pct = None
            earnings_week_high_price = None
            earnings_week_low_price = None
            prev_quarter_earnings_score = None
            prev_3q_earnings_score = None
            q1_earnings_score = None
            q2_earnings_score = None
            q3_earnings_score = None
            q1_ai_summary = None
            q2_ai_summary = None
            q3_ai_summary = None
            q1_week_high_pct = None
            q1_week_low_pct = None
            q1_week_high_price = None
            q1_week_low_price = None
            q2_week_high_pct = None
            q2_week_low_pct = None
            q2_week_high_price = None
            q2_week_low_price = None
            q3_week_high_pct = None
            q3_week_low_pct = None
            q3_week_high_price = None
            q3_week_low_price = None
            q1_earnings_date = None
            q2_earnings_date = None
            q3_earnings_date = None
            next_resistance = None
            current_support = None
            eps_estimate = None
            eps_reported = None
            surprise_pct = None

            if load_price_metrics is not _ORIGINAL_LOAD_PRICE_METRICS:
                cached_metrics = None if force else load_price_metrics(ticker, settings)
            else:
                cached_metrics = None if force else metrics_map.get(ticker)

            if cached_metrics is not None:
                current_price = cached_metrics.get("current_price")
                week_high = cached_metrics.get("week_high")
                week_low = cached_metrics.get("week_low")
                week_change = cached_metrics.get("week_change")
                pct_from_52w_high = cached_metrics.get("pct_from_52w_high")
                pct_from_52w_low = cached_metrics.get("pct_from_52w_low")
                thirty_day_return_pct = cached_metrics.get("thirty_day_return_pct")
                seven_day_return_pct = cached_metrics.get("seven_day_return_pct")
                earnings_week_move_pct = cached_metrics.get("earnings_week_move_pct")
                if market_cap is None:
                    market_cap = cached_metrics.get("market_cap")
                if three_day_return_pct is None:
                    three_day_return_pct = cached_metrics.get("three_day_return_pct")

            # Load prices from preloaded cache or fallback to load_prices/fetch_prices
            if fetch_prices is not _ORIGINAL_FETCH_PRICES:
                prices = fetch_prices(ticker, settings, force=False)
            elif load_prices is not _ORIGINAL_LOAD_PRICES:
                prices = load_prices(ticker, settings)
                if prices is None or prices.empty:
                    prices = fetch_prices(ticker, settings, force=False)
            else:
                prices = prices_map.get(ticker)
                if prices is None or prices.empty:
                    try:
                        from earnings_engine.data.prices import load_prices as _lp
                        prices = _lp(ticker, settings)
                        if prices is None or prices.empty:
                            prices = fetch_prices(ticker, settings, force=False)
                    except Exception:
                        prices = pd.DataFrame(columns=["close"])
            if prices is None:
                prices = pd.DataFrame(columns=["close"])

            # Compute current price and 52W high/low from prices cache if missing
            if not prices.empty and "close" in prices.columns:
                closes_s = pd.to_numeric(prices["close"], errors="coerce").dropna()
                if not closes_s.empty:
                    if current_price is None:
                        current_price = float(closes_s.iloc[-1])
                    if week_high is None:
                        week_high = float(closes_s.tail(252).max())
                    if week_low is None:
                        week_low = float(closes_s.tail(252).min())
                    if week_change is None and len(closes_s) >= 2:
                        prev_c = float(closes_s.iloc[-2])
                        if prev_c > 0:
                            week_change = ((current_price - prev_c) / prev_c) * 100

            # Collect market cap in batch for bulk storage when available
            if market_cap is not None and force:
                market_caps_to_store[ticker] = float(market_cap)
            if not prices.empty and "close" in prices.columns:
                closes = pd.to_numeric(prices["close"], errors="coerce").dropna()
                if len(closes) >= 2:
                    latest = float(closes.iloc[-1])
                    _last_date = closes.index[-1]
                    # 30D / 7D returns use CALENDAR days (one month / one week) so
                    # they match external sources — not trading days, which overstate
                    # the move. Only recompute if not already cached today.
                    if thirty_day_return_pct is None:
                        prior_30 = _close_n_calendar_days_ago(closes, _last_date, 30)
                        if prior_30 is None:
                            prior_30 = float(closes.iloc[0])
                        thirty_day_return_pct = ((latest - prior_30) / prior_30) * 100 if prior_30 else None
                    if seven_day_return_pct is None:
                        prior_7 = _close_n_calendar_days_ago(closes, _last_date, 7)
                        if prior_7 is None:
                            prior_7 = float(closes.iloc[0])
                        seven_day_return_pct = ((latest - prior_7) / prior_7) * 100 if prior_7 else None
                    if three_day_return_pct is None:
                        prior_3 = _close_n_calendar_days_ago(closes, _last_date, 3)
                        if prior_3 is None and len(closes) >= 4:
                            prior_3 = float(closes.iloc[-4])
                        elif prior_3 is None:
                            prior_3 = float(closes.iloc[0])
                        three_day_return_pct = ((latest - prior_3) / prior_3) * 100 if prior_3 else None

                    if len(closes) >= 5:
                        prior_week = float(closes.iloc[-5])
                        if earnings_week_move_pct is None:
                            earnings_week_move_pct = ((latest - prior_week) / prior_week) * 100 if prior_week else None
                        week_window = closes.tail(5)
                        window_high = float(week_window.max())
                        window_low = float(week_window.min())
                        earnings_week_high_pct = ((window_high - prior_week) / prior_week) * 100 if prior_week else None
                        earnings_week_low_pct = ((window_low - prior_week) / prior_week) * 100 if prior_week else None
                    elif len(closes) >= 2:
                        prior_week = float(closes.iloc[0])
                        if earnings_week_move_pct is None:
                            earnings_week_move_pct = ((latest - prior_week) / prior_week) * 100 if prior_week else None

                # resistance/support and auto-range detection
                if not closes.empty:
                    recent_high = float(closes.tail(20).max()) if len(closes) >= 20 else float(closes.max())
                    recent_low = float(closes.tail(20).min()) if len(closes) >= 20 else float(closes.min())
                    next_resistance = recent_high
                    current_support = recent_low

                    # Auto-detect swing range
                    auto_rng = detect_swing_range(closes)
                    if current_price is not None and current_support is not None and next_resistance is not None:
                        span = next_resistance - current_support
                        if span > 0:
                            channel_position_pct = round(((current_price - current_support) / span) * 100.0, 1)
                        else:
                            channel_position_pct = 50.0

            # Compute relative volume surge (5D average volume vs 63D baseline average)
            rel_vol_5d_vs_63d = None
            if not prices.empty and "volume" in prices.columns:
                try:
                    vols = pd.to_numeric(prices["volume"], errors="coerce").dropna()
                    if len(vols) >= 5:
                        v_5d = float(vols.tail(5).mean())
                        v_63d = float(vols.tail(63).mean()) if len(vols) >= 63 else float(vols.mean())
                        if v_63d > 0:
                            rel_vol_5d_vs_63d = round(v_5d / v_63d, 2)
                except Exception:
                    rel_vol_5d_vs_63d = None

            if load_earnings is not _ORIGINAL_LOAD_EARNINGS:
                earnings = load_earnings(ticker, settings)
            else:
                earnings = earnings_map.get(ticker)
            if earnings is None:
                earnings = pd.DataFrame(columns=["earnings_date", "eps_estimate", "eps_reported", "surprise_pct"])

            # Last 3 quarters earnings scores + week high/low (per-quarter)
            last_quarter_score = None
            last_week_high_pct = None
            last_week_low_pct = None
            last_week_high_price = None
            last_week_low_price = None
            last_week_high_date = None
            last_week_low_date = None
            q1_price_7d = None
            q2_price_7d = None
            q3_price_7d = None
            q1_week_high_date = None
            q1_week_low_date = None
            q2_week_high_date = None
            q2_week_low_date = None
            q3_week_high_date = None
            q3_week_low_date = None
            beat_rate_pct = None
            beat_count = 0
            total_historical_quarters = 0
            historical_quarters_list: list[dict[str, Any]] = []

            if not earnings.empty:
                today = pd.Timestamp.today().normalize()
                # Only declared PAST earnings events contribute to the Q1/Q2/Q3 breakdown.
                # Unconfirmed/tentative calendar estimates without reported EPS or surprise must NOT leak into quarter
                # scores, week-high/low, or price-after-earnings.
                has_eps = "eps_reported" in earnings.columns
                has_surp = "surprise_pct" in earnings.columns
                if has_eps and has_surp:
                    declared_mask = earnings["eps_reported"].notna() | earnings["surprise_pct"].notna()
                elif has_eps:
                    declared_mask = earnings["eps_reported"].notna()
                elif has_surp:
                    declared_mask = earnings["surprise_pct"].notna()
                else:
                    declared_mask = pd.Series([True] * len(earnings), index=earnings.index)

                declared_historical = earnings[(earnings["earnings_date"] < today) & declared_mask]
                historical_earnings = declared_historical if not declared_historical.empty else earnings[earnings["earnings_date"] < today]

                # Compute historical beat rate and 8-quarter history
                if not historical_earnings.empty:
                    sorted_hist = historical_earnings.sort_values("earnings_date")
                    total_historical_quarters = len(sorted_hist)
                    for _, h_row in sorted_hist.iterrows():
                        surp_v = pd.to_numeric(h_row.get("surprise_pct"), errors="coerce")
                        eps_r = pd.to_numeric(h_row.get("eps_reported"), errors="coerce")
                        eps_e = pd.to_numeric(h_row.get("eps_estimate"), errors="coerce")
                        is_beat = False
                        if pd.notna(surp_v) and float(surp_v) > 0:
                            is_beat = True
                        elif pd.notna(eps_r) and pd.notna(eps_e) and float(eps_r) > float(eps_e):
                            is_beat = True
                        if is_beat:
                            beat_count += 1

                    if total_historical_quarters > 0:
                        beat_rate_pct = round((beat_count / total_historical_quarters) * 100.0, 1)

                    # Build detailed 8-quarter historical array for Inspector drawer
                    for _, h_row in sorted_hist.tail(8).iterrows():
                        h_date = h_row.get("earnings_date")
                        h_date_str = pd.Timestamp(h_date).strftime("%Y-%m-%d") if pd.notna(h_date) else ""
                        surp_v = pd.to_numeric(h_row.get("surprise_pct"), errors="coerce")
                        eps_r = pd.to_numeric(h_row.get("eps_reported"), errors="coerce")
                        eps_e = pd.to_numeric(h_row.get("eps_estimate"), errors="coerce")
                        h_score = _score_surprise(float(surp_v)) if pd.notna(surp_v) else 5
                        h_p7d = _price_after_earnings(prices, h_date, days=7) if not prices.empty and pd.notna(h_date) else None
                        h_wk_data = _week_high_low_around(prices, h_date, current_price=current_price) if not prices.empty and pd.notna(h_date) else None
                        historical_quarters_list.append({
                            "date": h_date_str,
                            "eps_estimate": round(float(eps_e), 2) if pd.notna(eps_e) else None,
                            "eps_reported": round(float(eps_r), 2) if pd.notna(eps_r) else None,
                            "surprise_pct": round(float(surp_v), 2) if pd.notna(surp_v) else None,
                            "score": h_score,
                            "price_7d": round(float(h_p7d), 2) if h_p7d is not None else None,
                            "week_high_pct": round(float(h_wk_data[0]), 1) if h_wk_data and h_wk_data[0] is not None else None,
                            "week_low_pct": round(float(h_wk_data[1]), 1) if h_wk_data and h_wk_data[1] is not None else None,
                        })

                recent_earnings = historical_earnings.sort_values("earnings_date").tail(3)  # last 3 past quarters
                quarter_scores: list[int] = []
                n_quarters = len(recent_earnings)
                for i, (_, qrow) in enumerate(recent_earnings.iterrows()):
                    surprise = pd.to_numeric(qrow.get("surprise_pct", 0), errors="coerce")
                    score = _score_surprise(float(surprise)) if pd.notna(surprise) else None
                    if score is not None:
                        quarter_scores.append(score)

                    # Week high/low for this quarter's result week (±4 business days)
                    week_data = None
                    if not prices.empty:
                        week_data = _week_high_low_around(prices, qrow["earnings_date"], current_price=current_price)

                    # Price 7 working days after earnings
                    price_7d = None
                    if not prices.empty:
                        price_7d = _price_after_earnings(prices, qrow["earnings_date"], days=7)
                    if price_7d is None and current_price is not None and (today - qrow["earnings_date"]).days <= 10:
                        price_7d = current_price  # Dynamic live price for recent prints

                    # Quarter labels are mapped so Q1 = MOST recent quarter,
                    # Q2 = 2nd most recent, Q3 = 3rd most recent.
                    offset = (n_quarters - 1) - i
                    is_last = (offset == 0)

                    eps_rep_raw = qrow.get("eps_reported")
                    eps_est_raw = qrow.get("eps_estimate")
                    eps_rep_val = float(eps_rep_raw) if (eps_rep_raw is not None and not pd.isna(eps_rep_raw)) else None
                    eps_est_val = float(eps_est_raw) if (eps_est_raw is not None and not pd.isna(eps_est_raw)) else None
                    surp_val = float(surprise) if pd.notna(surprise) else None

                    if offset == 0:  # most recent quarter -> Q1
                        q1_earnings_score = score
                        q1_price_7d = price_7d
                        q1_earnings_date = qrow["earnings_date"]
                        if week_data is not None:
                            q1_week_high_pct, q1_week_low_pct, q1_week_high_price, q1_week_low_price, q1_week_high_date, q1_week_low_date = week_data
                        q1_ai_summary = generate_quarter_result_ai_note(
                            "Q1", q1_earnings_date, score, surp_val, eps_rep_val, eps_est_val,
                            q1_week_high_pct, q1_week_low_pct, price_7d
                        )
                    elif offset == 1:  # 2nd most recent quarter -> Q2
                        q2_earnings_score = score
                        q2_price_7d = price_7d
                        q2_earnings_date = qrow["earnings_date"]
                        if week_data is not None:
                            q2_week_high_pct, q2_week_low_pct, q2_week_high_price, q2_week_low_price, q2_week_high_date, q2_week_low_date = week_data
                        q2_ai_summary = generate_quarter_result_ai_note(
                            "Q2", q2_earnings_date, score, surp_val, eps_rep_val, eps_est_val,
                            q2_week_high_pct, q2_week_low_pct, price_7d
                        )
                    elif offset == 2:  # 3rd most recent quarter -> Q3
                        q3_earnings_score = score
                        q3_price_7d = price_7d
                        q3_earnings_date = qrow["earnings_date"]
                        if week_data is not None:
                            q3_week_high_pct, q3_week_low_pct, q3_week_high_price, q3_week_low_price, q3_week_high_date, q3_week_low_date = week_data
                        q3_ai_summary = generate_quarter_result_ai_note(
                            "Q3", q3_earnings_date, score, surp_val, eps_rep_val, eps_est_val,
                            q3_week_high_pct, q3_week_low_pct, price_7d
                        )

                    if is_last:
                        last_quarter_score = score
                        if week_data is not None:
                            last_week_high_pct, last_week_low_pct, last_week_high_price, last_week_low_price, last_week_high_date, last_week_low_date = week_data

                if quarter_scores:
                    # 3Q score = average of individual quarter scores (never exceeds max individual score)
                    prev_3q_earnings_score = round(sum(quarter_scores) / len(quarter_scores))
                    prev_3q_earnings_score = min(prev_3q_earnings_score, max(quarter_scores))

            prev_quarter_earnings_score = last_quarter_score if last_quarter_score is not None else 5

            # Extract EPS estimate, reported, and surprise from the most recent **historical** earnings
            # (exclude upcoming/future events and unconfirmed estimates where these values are naturally null)
            if not earnings.empty:
                today = pd.Timestamp.today().normalize()
                has_eps = "eps_reported" in earnings.columns
                has_surp = "surprise_pct" in earnings.columns
                if has_eps and has_surp:
                    declared_mask = earnings["eps_reported"].notna() | earnings["surprise_pct"].notna()
                elif has_eps:
                    declared_mask = earnings["eps_reported"].notna()
                elif has_surp:
                    declared_mask = earnings["surprise_pct"].notna()
                else:
                    declared_mask = pd.Series([True] * len(earnings), index=earnings.index)

                declared_hist = earnings[(earnings["earnings_date"] < today) & declared_mask]
                historical = declared_hist if not declared_hist.empty else earnings[earnings["earnings_date"] < today]
                if not historical.empty:
                    latest_earnings = historical.sort_values("earnings_date").iloc[-1]
                    eps_estimate = latest_earnings.get("eps_estimate")
                    eps_reported = latest_earnings.get("eps_reported")
                    surprise_pct = latest_earnings.get("surprise_pct")
                else:
                    eps_estimate = None
                    eps_reported = None
                    surprise_pct = None

            # Only recompute 52W gaps if not already cached today (once-per-day refresh)
            if pct_from_52w_high is None:
                if week_high is None or current_price is None:
                    pct_from_high = None
                else:
                    pct_from_high = ((week_high - current_price) / week_high) * 100
            else:
                pct_from_high = pct_from_52w_high

            if pct_from_52w_low is None:
                if week_low is None or current_price is None:
                    pct_from_low = None
                else:
                    pct_from_low = ((current_price - week_low) / week_low) * 100
            else:
                pct_from_low = pct_from_52w_low

            metrics_payload = {
                "company_name": company_name,
                "market_cap": market_cap,
                "current_price": current_price,
                "week_change": week_change,
                "pct_from_52w_high": pct_from_high,
                "pct_from_52w_low": pct_from_low,
                "thirty_day_return_pct": thirty_day_return_pct,
                "seven_day_return_pct": seven_day_return_pct,
                "three_day_return_pct": three_day_return_pct,
                "channel_position_pct": channel_position_pct,
                "earnings_week_move_pct": earnings_week_move_pct,
                "earnings_week_high_pct": earnings_week_high_pct,
                "earnings_week_low_pct": earnings_week_low_pct,
                "earnings_week_high_price": earnings_week_high_price,
                "earnings_week_low_price": earnings_week_low_price,
                "week_high": week_high,
                "week_low": week_low,
                "prev_quarter_earnings_score": prev_quarter_earnings_score,
                "prev_3q_earnings_score": prev_3q_earnings_score,
                "q1_earnings_score": q1_earnings_score,
                "q2_earnings_score": q2_earnings_score,
                "q3_earnings_score": q3_earnings_score,
                "q1_ai_summary": q1_ai_summary,
                "q2_ai_summary": q2_ai_summary,
                "q3_ai_summary": q3_ai_summary,
                "q1_week_high_pct": q1_week_high_pct,
                "q1_week_low_pct": q1_week_low_pct,
                "q1_week_high_price": q1_week_high_price,
                "q1_week_low_price": q1_week_low_price,
                "q1_week_high_date": q1_week_high_date.strftime("%Y-%m-%d") if q1_week_high_date is not None else None,
                "q1_week_low_date": q1_week_low_date.strftime("%Y-%m-%d") if q1_week_low_date is not None else None,
                "q1_earnings_date": q1_earnings_date.strftime("%Y-%m-%d") if q1_earnings_date is not None else None,
                "q2_week_high_pct": q2_week_high_pct,
                "q2_week_low_pct": q2_week_low_pct,
                "q2_week_high_price": q2_week_high_price,
                "q2_week_low_price": q2_week_low_price,
                "q2_week_high_date": q2_week_high_date.strftime("%Y-%m-%d") if q2_week_high_date is not None else None,
                "q2_week_low_date": q2_week_low_date.strftime("%Y-%m-%d") if q2_week_low_date is not None else None,
                "q2_earnings_date": q2_earnings_date.strftime("%Y-%m-%d") if q2_earnings_date is not None else None,
                "q3_week_high_pct": q3_week_high_pct,
                "q3_week_low_pct": q3_week_low_pct,
                "q3_week_high_price": q3_week_high_price,
                "q3_week_low_price": q3_week_low_price,
                "q3_week_high_date": q3_week_high_date.strftime("%Y-%m-%d") if q3_week_high_date is not None else None,
                "q3_week_low_date": q3_week_low_date.strftime("%Y-%m-%d") if q3_week_low_date is not None else None,
                "q3_earnings_date": q3_earnings_date.strftime("%Y-%m-%d") if q3_earnings_date is not None else None,
                "q1_price_7d": q1_price_7d,
                "q2_price_7d": q2_price_7d,
                "q3_price_7d": q3_price_7d,
                "last_week_high_pct": last_week_high_pct,
                "last_week_low_pct": last_week_low_pct,
                "last_week_high_price": last_week_high_price,
                "last_week_low_price": last_week_low_price,
                "last_week_high_date": last_week_high_date.strftime("%Y-%m-%d") if last_week_high_date is not None else None,
                "last_week_low_date": last_week_low_date.strftime("%Y-%m-%d") if last_week_low_date is not None else None,
                "next_resistance": next_resistance,
                "current_support": current_support,
                "swing_range": sr_map.get(ticker),
                "rel_vol_5d_vs_63d": rel_vol_5d_vs_63d,
                "beat_rate_pct": beat_rate_pct,
                "beat_count": beat_count,
                "total_historical_quarters": total_historical_quarters,
                "historical_quarters": historical_quarters_list,
            }
            metrics_to_store[ticker] = metrics_payload

            # Calculate result sequence for new listing / debut earnings tracking
            from earnings_engine.data.new_listings import compute_ticker_result_sequence
            seq_info = compute_ticker_result_sequence(
                ticker,
                settings=settings,
                past_events_count=earnings_count_map.get(ticker, 0),
            )

            rows.append({
                "ticker": ticker,
                "company_name": company_name,
                "market_cap": market_cap,
                "current_price": current_price,
                "week_change": week_change,
                "pct_from_52w_high": pct_from_high,
                "pct_from_52w_low": pct_from_low,
                "thirty_day_return_pct": thirty_day_return_pct,
                "seven_day_return_pct": seven_day_return_pct,
                "three_day_return_pct": three_day_return_pct,
                "rel_vol_5d_vs_63d": rel_vol_5d_vs_63d,
                "beat_rate_pct": beat_rate_pct,
                "beat_count": beat_count,
                "total_historical_quarters": total_historical_quarters,
                "historical_quarters": historical_quarters_list,
                "channel_position_pct": channel_position_pct,
                "earnings_week_move_pct": earnings_week_move_pct,
                "earnings_week_high_pct": earnings_week_high_pct,
                "earnings_week_low_pct": earnings_week_low_pct,
                "earnings_week_high_price": earnings_week_high_price,
                "earnings_week_low_price": earnings_week_low_price,
                "week_high": week_high,
                "week_low": week_low,
                "prev_quarter_earnings_score": prev_quarter_earnings_score,
                "prev_3q_earnings_score": prev_3q_earnings_score,
                "q1_earnings_score": q1_earnings_score,
                "q2_earnings_score": q2_earnings_score,
                "q3_earnings_score": q3_earnings_score,
                "q1_ai_summary": q1_ai_summary,
                "q2_ai_summary": q2_ai_summary,
                "q3_ai_summary": q3_ai_summary,
                "q1_week_high_pct": q1_week_high_pct,
                "q1_week_low_pct": q1_week_low_pct,
                "q1_week_high_price": q1_week_high_price,
                "q1_week_low_price": q1_week_low_price,
                "q1_week_high_date": q1_week_high_date,
                "q1_week_low_date": q1_week_low_date,
                "q1_earnings_date": q1_earnings_date,
                "q2_week_high_pct": q2_week_high_pct,
                "q2_week_low_pct": q2_week_low_pct,
                "q2_week_high_price": q2_week_high_price,
                "q2_week_low_price": q2_week_low_price,
                "q2_week_high_date": q2_week_high_date,
                "q2_week_low_date": q2_week_low_date,
                "q2_earnings_date": q2_earnings_date,
                "q3_week_high_pct": q3_week_high_pct,
                "q3_week_low_pct": q3_week_low_pct,
                "q3_week_high_price": q3_week_high_price,
                "q3_week_low_price": q3_week_low_price,
                "q3_week_high_date": q3_week_high_date,
                "q3_week_low_date": q3_week_low_date,
                "q3_earnings_date": q3_earnings_date,
                "q1_price_7d": q1_price_7d,
                "q2_price_7d": q2_price_7d,
                "q3_price_7d": q3_price_7d,
                "last_week_high_pct": last_week_high_pct,
                "last_week_low_pct": last_week_low_pct,
                "last_week_high_price": last_week_high_price,
                "last_week_low_price": last_week_low_price,
                "next_resistance": next_resistance,
                "current_support": current_support,
                "eps_estimate": eps_estimate,
                "eps_reported": eps_reported,
                "surprise_pct": surprise_pct,
                "result_sequence_number": seq_info["result_sequence_number"],
                "result_sequence_label": seq_info["result_sequence_label"],
                "result_sequence_badge": seq_info["result_sequence_badge"],
                "is_debut_result": seq_info["is_debut"],
            })

        except Exception as e:
            logger.warning("enrich_upcoming_results failed for ticker=%s error=%s", ticker, e)
            rows.append({
                "ticker": ticker,
                "market_cap": None,
                "current_price": None,
                "week_change": None,
                "pct_from_52w_high": None,
                "pct_from_52w_low": None,
                "thirty_day_return_pct": None,
                "seven_day_return_pct": None,
                "earnings_week_move_pct": None,
                "earnings_week_high_pct": None,
                "earnings_week_low_pct": None,
                "earnings_week_high_price": None,
                "earnings_week_low_price": None,
                "week_high": None,
                "week_low": None,
                "prev_quarter_earnings_score": None,
                "prev_3q_earnings_score": None,
                "q1_earnings_score": None,
                "q2_earnings_score": None,
                "q3_earnings_score": None,
                "q1_ai_summary": None,
                "q2_ai_summary": None,
                "q3_ai_summary": None,
                "q1_week_high_pct": None,
                "q1_week_low_pct": None,
                "q1_week_high_price": None,
                "q1_week_low_price": None,
                "q2_week_high_pct": None,
                "q2_week_low_pct": None,
                "q2_week_high_price": None,
                "q2_week_low_price": None,
                "q3_week_high_pct": None,
                "q3_week_low_pct": None,
                "q3_week_high_price": None,
                "q3_week_low_price": None,
                "last_week_high_pct": None,
                "last_week_low_pct": None,
                "last_week_high_price": None,
                "last_week_low_price": None,
                "next_resistance": None,
                "current_support": None,
                "eps_estimate": None,
                "eps_reported": None,
                "surprise_pct": None,
            })
            continue

    if market_caps_to_store:
        try:
            from earnings_engine.data.universe import store_market_caps_bulk
            store_market_caps_bulk(market_caps_to_store, settings)
        except Exception as e:
            logger.debug("Failed bulk storing market caps: %s", e)

    if metrics_to_store:
        try:
            from earnings_engine.data.prices import store_price_metrics_bulk
            store_price_metrics_bulk(metrics_to_store, settings)
        except Exception as e:
            logger.debug("Failed bulk storing price metrics: %s", e)

    context = pd.DataFrame(rows)
    # Deduplicate context by ticker so that if the input df has the same ticker
    # multiple times (e.g. from both yfinance and nse sources), the merge
    # doesn't create a cartesian product.
    context = context.drop_duplicates(subset=["ticker"], keep="first")
    t2_loop = time.perf_counter()
    logger.info(
        "[ENRICH-PROFILER] Total: %.1fms | bulk_db_queries: %.1fms | loop_processing: %.1fms (%d tickers)",
        (t2_loop - t0_enrich) * 1000,
        (t1_bulk - t0_enrich) * 1000,
        (t2_loop - t1_bulk) * 1000,
        len(tickers),
    )
    return df.merge(context, on="ticker", how="left")
