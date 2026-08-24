"""Helpers for enriching upcoming earnings results with market context."""

from __future__ import annotations

import time
import pandas as pd
import yfinance as yf

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
    if current_price is not None and float(current_price) > 0 and today >= ed:
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
    if closes.empty:
        return {
            "lower": None, "upper": None, "cycles": 0, "avg_days": 0, "cycles_data": [],
            "three_month_lower": None, "three_month_upper": None, "monthly_ranges": [],
        }

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

    try:
        from earnings_engine.data.db import get_db_connection
        from collections import defaultdict
        conn = get_db_connection(settings)
        placeholders = ", ".join(["?"] * len(tickers))
        
        # 1. Unified Ticker Master (Names, Market Caps, Metrics in 1 query)
        import json
        try:
            ticker_master_rows = conn.execute(
                f"SELECT ticker, name, market_cap, metrics FROM tickers WHERE ticker IN ({placeholders})",
                tickers,
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

                    
        # 3. Earnings History (last 2 years)
        cutoff_e_date = (pd.Timestamp.now() - pd.Timedelta(days=730)).strftime("%Y-%m-%d")
        e_rows = conn.execute(
            f"SELECT ticker, earnings_date, eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker IN ({placeholders}) AND earnings_date >= ? ORDER BY ticker, earnings_date",
            tickers + [cutoff_e_date],
        ).fetchall()
        e_by_ticker = defaultdict(list)
        for r in e_rows:
            e_by_ticker[r[0]].append((r[1], r[2], r[3], r[4]))
        for t, r_list in e_by_ticker.items():
            f = pd.DataFrame(r_list, columns=["earnings_date", "eps_estimate", "eps_reported", "surprise_pct"])
            f["earnings_date"] = pd.to_datetime(f["earnings_date"])
            earnings_map[t] = f

        # 4. Price History (last ~450 days)
        cutoff_p_date = (pd.Timestamp.now() - pd.Timedelta(days=450)).strftime("%Y-%m-%d")
        p_rows = conn.execute(
            f"SELECT ticker, date, open, high, low, close, volume FROM price_history WHERE ticker IN ({placeholders}) AND date >= ? ORDER BY ticker, date",
            tickers + [cutoff_p_date],
        ).fetchall()
        p_by_ticker = defaultdict(list)
        for r in p_rows:
            p_by_ticker[r[0]].append((r[1], r[2], r[3], r[4], r[5], r[6]))
        for t, r_list in p_by_ticker.items():
            f = pd.DataFrame(r_list, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
            f.index = pd.to_datetime(f.index)
            prices_map[t] = f

        # 5. Stored Swing Ranges
        sr_rows = conn.execute(
            f"SELECT ticker, lower_bound, upper_bound, source FROM swing_ranges WHERE ticker IN ({placeholders})",
            tickers,
        ).fetchall()
        sr_map = {r[0]: {"lower_bound": r[1], "upper_bound": r[2], "source": r[3]} for r in sr_rows}
    except Exception:
        sr_map = {}

    t1_bulk = time.perf_counter()

    rows: list[dict] = []
    metrics_to_store: dict[str, dict[str, Any]] = {}
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

            # Load prices from preloaded cache or fallback to load_prices/fetch_prices
            if fetch_prices is not _ORIGINAL_FETCH_PRICES:
                prices = fetch_prices(ticker, settings, force=False)
            elif load_prices is not _ORIGINAL_LOAD_PRICES:
                prices = load_prices(ticker, settings)
                if prices is None or prices.empty:
                    prices = fetch_prices(ticker, settings, force=False)
            else:
                prices = prices_map.get(ticker)
                if (prices is None or prices.empty) and force:
                    try:
                        prices = fetch_prices(ticker, settings, force=True)
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

            # Only query fast_info over network when force=True
            if force and (market_cap is None or current_price is None):
                try:
                    info = yf.Ticker(ticker).fast_info or {}
                    if market_cap is None:
                        market_cap = info.get("market_cap")
                    if current_price is None:
                        current_price = info.get("last_price")
                    if week_high is None:
                        week_high = info.get("year_high")
                    if week_low is None:
                        week_low = info.get("year_low")
                except Exception:
                    pass

            # Store market cap in cache only when force-fetching
            if market_cap is not None and force:
                store_market_cap(ticker, market_cap, settings)
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

            if not earnings.empty:
                today = pd.Timestamp.today().normalize()
                # Only PAST earnings events contribute to the Q1/Q2/Q3 breakdown.
                # The upcoming event (e.g. +4d) must NOT leak into the quarter
                # scores, week-high/low, or price-after-earnings — otherwise the
                # "result week" would be the upcoming print's pre-move instead of
                # a historical result week.
                historical_earnings = earnings[earnings["earnings_date"] < today]
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

                    if offset == 0:  # most recent quarter -> Q1
                        q1_earnings_score = score
                        q1_price_7d = price_7d
                        q1_earnings_date = qrow["earnings_date"]
                        if week_data is not None:
                            q1_week_high_pct, q1_week_low_pct, q1_week_high_price, q1_week_low_price, q1_week_high_date, q1_week_low_date = week_data
                    elif offset == 1:  # 2nd most recent quarter -> Q2
                        q2_earnings_score = score
                        q2_price_7d = price_7d
                        q2_earnings_date = qrow["earnings_date"]
                        if week_data is not None:
                            q2_week_high_pct, q2_week_low_pct, q2_week_high_price, q2_week_low_price, q2_week_high_date, q2_week_low_date = week_data
                    elif offset == 2:  # 3rd most recent quarter -> Q3
                        q3_earnings_score = score
                        q3_price_7d = price_7d
                        q3_earnings_date = qrow["earnings_date"]
                        if week_data is not None:
                            q3_week_high_pct, q3_week_low_pct, q3_week_high_price, q3_week_low_price, q3_week_high_date, q3_week_low_date = week_data

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
            # (exclude upcoming/future events where these values are naturally null)
            if not earnings.empty:
                today = pd.Timestamp.today().normalize()
                historical = earnings[earnings["earnings_date"] < today]
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
            }
            metrics_to_store[ticker] = metrics_payload

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
                "swing_range": get_swing_range("ALL", ticker, settings),
                "eps_estimate": eps_estimate,
                "eps_reported": eps_reported,
                "surprise_pct": surprise_pct,
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
