"""Recent-results scan: today/yesterday earnings + momentum + buy-the-dip.

Surfaces the earnings that just printed (previous calendar day, or today once
the NSE market has closed) alongside their post-result momentum and how far
they have corrected from the post-result high, so the user can spot
buy-the-dip setups.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.earnings import _connect as _earnings_connect
from earnings_engine.data.industry import get_industry_map
from earnings_engine.data.market_context import _close_n_calendar_days_ago, _week_high_low_around

# NSE closes ~15:30 IST; use 16:00 local as a safe "market has closed" cutoff.
MARKET_CLOSE_HOUR = 16

# How many recent calendar days of results to scan so the Buy-the-Dip / recent
# results tab actually surfaces data. Scanning just "yesterday (+ today after
# close)" is too narrow — on most days very few (often zero) stocks in a selected
# universe print earnings, so the tab appeared empty.
RECENT_WINDOW_DAYS = 7


def _is_after_market(now: datetime | None = None) -> bool:
    """Return True once the market has closed for the day (safe 16:00 local cutoff)."""
    if now is None:
        now = datetime.now()
    return now.hour >= MARKET_CLOSE_HOUR


def _eligible_dates(now: datetime | None = None) -> list[str]:
    """Return the earnings dates to scan: the last ``RECENT_WINDOW_DAYS`` calendar
    days (always) plus today once the market closes.

    This keeps the tab useful even on days when nothing printed "yesterday".
    """
    if now is None:
        now = datetime.now()
    today = now.date()
    # Prior calendar days within the window (RECENT_WINDOW_DAYS-1 .. 1 days ago).
    dates = [(today - timedelta(days=i)).isoformat() for i in range(RECENT_WINDOW_DAYS - 1, 0, -1)]
    # Today's results only appear once the market has closed.
    if _is_after_market(now):
        dates.append(today.isoformat())
    return dates


def load_recent_results(
    tickers: list[str],
    settings: Settings,
    now: datetime | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, pd.Timestamp]]:
    """Return (ticker, earnings_date) pairs for eligible recent results.

    When neither ``start_date`` nor ``end_date`` is given, uses ``_eligible_dates``
    (the last few calendar days, plus today after market close) for a quick default
    scan.  When a range is supplied (historical validation), filters earnings to
    that inclusive date range.  Rows are deduplicated by (ticker, date).
    """
    if not tickers:
        return []
    placeholders = ",".join("?" for _ in tickers)

    if start_date or end_date:
        conds = [f"ticker IN ({placeholders})"]
        params: list[Any] = list(tickers)
        if start_date:
            conds.append("earnings_date >= ?")
            params.append(start_date)
        if end_date:
            conds.append("earnings_date <= ?")
            params.append(end_date)
        where = " AND ".join(conds)
        query = (
            "SELECT DISTINCT ticker, earnings_date FROM earnings_history "
            f"WHERE {where}"
        )
    else:
        dates = _eligible_dates(now)
        date_placeholders = ",".join("?" for _ in dates)
        query = (
            "SELECT DISTINCT ticker, earnings_date FROM earnings_history "
            f"WHERE ticker IN ({placeholders}) AND earnings_date IN ({date_placeholders})"
        )
        params = tickers + dates

    with _earnings_connect(settings) as connection:
        rows = connection.execute(query, params).fetchall()
    return [(t, pd.Timestamp(d)) for t, d in rows]



def get_recent_results(
    tickers: list[str],
    settings: Settings,
    correction_pct: float = 5.0,
    drop_pct: float = 3.0,
    now: datetime | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Return per-result momentum + correction rows for the recent-results tab.

    `now` is defaulted to the current time/date for gating; pass an explicit
    value in tests.  `start_date`/`end_date` enable historical validation over an
    arbitrary range (default = last few days).  Each row carries:

    - ticker, earnings_date, day_label (Today/Yesterday/Nd ago), industry
    - close_before: close of the last trading day before the result (pre-result close)
    - open_after: open of the first trading day after the result (next-day open)
    - result_ohlc: dict {open, high, low, close} + _pct fields vs pre-result close
    - next_day_ohlc: dict {open, close} + _pct fields vs result-day close
    - drop_at_open_pct: reaction-day open vs pre-result close (negative = gapped down)
    - closed_above_open: the reaction day closed back above its open (recovery)
    - intraday_recovery_pct: reaction-day close vs its low
    - is_dip_recovery: dropped at the open by >= ``drop_pct`` then recovered (closed up)
    - high_pct / low_pct: post-result 7-day high/low move vs pre-result close
    - current_pct: latest close vs pre-result close
    - pullback_from_high: % below the post-result 7-day high
    - momentum_3d / momentum_7d / momentum_30d: 3/7/30-calendar-day returns
    - is_buy_dip: high_pct > 0 AND pullback_from_high <= -correction_pct

    Rows are sorted best-to-worst (highest post-result return first).
    """
    if now is None:
        now = datetime.now()
    events = load_recent_results(tickers, settings, now=now, start_date=start_date, end_date=end_date)

    # Load prices once per unique ticker.  ``fetch_prices`` falls back to
    # yfinance / NSE when a ticker has no (or stale) cached price rows, so
    # stocks missing from the SQLite cache still get real OHLC data.
    price_map: dict[str, pd.DataFrame] = {}
    for ticker in sorted({t for t, _ in events}):
        try:
            price_map[ticker] = prices_mod.fetch_prices(ticker, settings)
        except Exception:
            price_map[ticker] = pd.DataFrame()

    rows: list[dict[str, Any]] = []
    industry_map = get_industry_map([t for t, _ in events], settings)
    for ticker, edate in events:
        prices = price_map.get(ticker)
        base = None
        high_pct = low_pct = high_price = low_price = None
        current_price = None
        current_pct = pullback_from_high = momentum_3d = None
        result_ohlc = None
        next_day_ohlc = None
        momentum_7d = None
        momentum_30d = None
        open_after = None
        drop_at_open_pct = closed_above_open = intraday_recovery_pct = None

        if prices is not None and not prices.empty and "close" in prices.columns:
            closes = pd.to_numeric(prices["close"], errors="coerce").dropna()
            highs = pd.to_numeric(prices["high"], errors="coerce").dropna() if "high" in prices.columns else pd.Series(dtype=float)
            lows = pd.to_numeric(prices["low"], errors="coerce").dropna() if "low" in prices.columns else pd.Series(dtype=float)
            opens = pd.to_numeric(prices["open"], errors="coerce").dropna() if "open" in prices.columns else pd.Series(dtype=float)
            if not closes.empty:
                before = closes[closes.index < edate]
                if not before.empty and float(before.iloc[-1]) > 0:
                    base = float(before.iloc[-1])
                after_opens = opens[opens.index > edate]
                if not after_opens.empty:
                    open_after = float(after_opens.iloc[0])
                current_price = float(closes.iloc[-1])

                # Result-day OHLC (the trading day of the earnings result itself).
                result_day = closes[closes.index >= edate]
                if not result_day.empty:
                    rd = result_day.index[0]
                    rd_open = float(opens[opens.index == rd].iloc[0]) if not opens[opens.index == rd].empty else None
                    rd_high = float(highs[highs.index == rd].iloc[0]) if not highs[highs.index == rd].empty else None
                    rd_low = float(lows[lows.index == rd].iloc[0]) if not lows[lows.index == rd].empty else None
                    rd_close = float(result_day.iloc[0])

                    def _vs_base(v: float | None) -> float | None:
                        # % move of result-day price vs pre-result close.
                        return (v / base - 1.0) * 100 if v is not None and base else None

                    result_ohlc = {
                        "open": rd_open, "high": rd_high, "low": rd_low, "close": rd_close,
                        "open_pct": _vs_base(rd_open), "high_pct": _vs_base(rd_high),
                        "low_pct": _vs_base(rd_low), "close_pct": _vs_base(rd_close),
                    }
                else:
                    result_ohlc = None

                # Next-trading-day open/close (if any), % vs the result-day close.
                next_day = closes[closes.index > edate]
                if not next_day.empty:
                    nd = next_day.index[0]
                    nd_open = float(opens[opens.index == nd].iloc[0]) if not opens[opens.index == nd].empty else None
                    nd_close = float(next_day.iloc[0])
                    next_day_ohlc = {
                        "open": nd_open, "close": nd_close,
                        "open_pct": (nd_open / rd_close - 1.0) * 100 if nd_open is not None and rd_close else None,
                        "close_pct": (nd_close / rd_close - 1.0) * 100 if rd_close else None,
                    }
                else:
                    next_day_ohlc = None

                # Dip-then-recovery: did the stock gap DOWN at the reaction-day open
                # and then recover (close back above/open or off its intraday low)?
                if result_ohlc is not None:
                    drop_at_open_pct = result_ohlc.get("open_pct")  # negative = gap down
                    closed_above_open = (
                        result_ohlc.get("open") is not None
                        and result_ohlc.get("close") is not None
                        and float(result_ohlc["close"]) >= float(result_ohlc["open"])
                    )
                    if result_ohlc.get("low") and float(result_ohlc["low"]) > 0:
                        intraday_recovery_pct = (
                            float(result_ohlc["close"]) / float(result_ohlc["low"]) - 1.0
                        ) * 100

                week_data = _week_high_low_around(prices, edate)
                if week_data is not None:
                    high_pct, low_pct, high_price, low_price, _, _ = week_data
                if base:
                    current_pct = (current_price / base - 1.0) * 100
                if high_price and high_price > 0 and current_price is not None:
                    pullback_from_high = (current_price / high_price - 1.0) * 100
                # Momentum uses CALENDAR-day windows (3D/7D/30D = 3/7/30 calendar days)
                # so it matches external sources, not trading days (which overstate).
                _last_close = float(closes.iloc[-1])
                _last_date = closes.index[-1]
                _p3 = _close_n_calendar_days_ago(closes, _last_date, 3)
                _p7 = _close_n_calendar_days_ago(closes, _last_date, 7)
                _p30 = _close_n_calendar_days_ago(closes, _last_date, 30)
                if _p3:
                    momentum_3d = (_last_close / _p3 - 1.0) * 100
                if _p7:
                    momentum_7d = (_last_close / _p7 - 1.0) * 100
                if _p30:
                    momentum_30d = (_last_close / _p30 - 1.0) * 100

        is_buy_dip = bool(
            high_pct is not None and high_pct > 0
            and pullback_from_high is not None
            and pullback_from_high <= -correction_pct
        )
        is_dip_recovery = bool(
            drop_at_open_pct is not None
            and drop_at_open_pct <= -drop_pct
            and closed_above_open
        )
        # Label the day relative to now (the window can span several days).
        _delta = (now.date() - edate.date()).days
        day_label = "Today" if _delta == 0 else ("Yesterday" if _delta == 1 else f"{_delta}d ago")
        rows.append({
            "ticker": ticker,
            "earnings_date": edate.strftime("%Y-%m-%d"),
            "day_label": day_label,
            "industry": industry_map.get(ticker),
            "close_before": base,
            "open_after": open_after,
            "current_price": current_price,
            "result_ohlc": result_ohlc,
            "next_day_ohlc": next_day_ohlc,
            "drop_at_open_pct": drop_at_open_pct,
            "closed_above_open": closed_above_open,
            "intraday_recovery_pct": intraday_recovery_pct,
            "is_dip_recovery": is_dip_recovery,
            "high_pct": high_pct,
            "low_pct": low_pct,
            "current_pct": current_pct,
            "pullback_from_high": pullback_from_high,
            "momentum_3d": momentum_3d,
            "momentum_7d": momentum_7d,
            "momentum_30d": momentum_30d,
            "is_buy_dip": is_buy_dip,
        })

    # Sort best-to-worst: highest post-result return (current_pct) first.
    rows.sort(key=lambda r: r["current_pct"] if r["current_pct"] is not None else float("-inf"), reverse=True)

    return {
        "rows": rows,
        "buy_dip_count": sum(1 for r in rows if r["is_buy_dip"]),
        "dip_recovery_count": sum(1 for r in rows if r["is_dip_recovery"]),
        "today_count": sum(1 for r in rows if r["day_label"] == "Today"),
        "yesterday_count": sum(1 for r in rows if r["day_label"] == "Yesterday"),
        "total": len(rows),
    }


def compute_patterns(
    tickers: list[str],
    settings: Settings,
    now: datetime | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    drop_pct: float = 3.0,
    comeback_fraction: float = 0.5,
    lookahead_days: int = 5,
) -> dict[str, Any]:
    """Aggregate buy-the-dip / industry patterns over a result timeframe.

    Classifies each result by price reaction (close of the first full session
    after the result vs the pre-result close) and rolls the metrics up by
    industry:
      1. total results declared in the timeframe
      2. positive / negative / neutral result counts
      3. industry with the most positive results
      4. industry with the best positive-results : stocks-with-results ratio
      5. positive results that dipped on the result/next day, plus how many of
         those recovered >= ``comeback_fraction`` of the initial drop
      6. positive results that kept dipping afterwards (no recovery)
    """
    if now is None:
        now = datetime.now()
    events = load_recent_results(tickers, settings, now=now, start_date=start_date, end_date=end_date)

    price_map: dict[str, pd.DataFrame] = {}
    for t in sorted({t for t, _ in events}):
        try:
            price_map[t] = prices_mod.fetch_prices(t, settings)
        except Exception:
            price_map[t] = pd.DataFrame()
    industry_map = get_industry_map([t for t, _ in events], settings)

    def _series(prices, col) -> pd.Series:
        if prices is None or prices.empty or col not in prices.columns:
            return pd.Series([], dtype=float)
        return pd.to_numeric(prices[col], errors="coerce").dropna()

    rows = []
    for ticker, edate in events:
        prices = price_map.get(ticker)
        closes = _series(prices, "close")
        if closes.empty:
            continue
        before = closes[closes.index < edate]
        if before.empty or float(before.iloc[-1]) <= 0:
            continue
        base = float(before.iloc[-1])
        on_or_after = closes[closes.index >= edate]
        strictly = closes[closes.index > edate]
        if on_or_after.empty:
            continue
        reaction_close = float(strictly.iloc[0]) if not strictly.empty else float(on_or_after.iloc[0])

        if reaction_close > base:
            result_class = "positive"
        elif reaction_close < base:
            result_class = "negative"
        else:
            result_class = "neutral"

        # Post-result window (from the result date onward).
        post_closes = on_or_after.iloc[:lookahead_days]
        post_lows = _series(prices, "low")
        post_lows = post_lows[post_lows.index >= edate].iloc[:lookahead_days]
        post_opens = _series(prices, "open")
        post_opens = post_opens[post_opens.index >= edate].iloc[:lookahead_days]
        post_highs = _series(prices, "high")
        post_highs = post_highs[post_highs.index >= edate].iloc[:lookahead_days]

        # Result-day OHLC (the first session on/after the earnings date).
        day_open = float(post_opens.iloc[0]) if not post_opens.empty else None
        day_high = float(post_highs.iloc[0]) if not post_highs.empty else None
        day_low = float(post_lows.iloc[0]) if not post_lows.empty else None
        day_close = float(on_or_after.iloc[0]) if not on_or_after.empty else None

        dipped = bool(not post_lows.empty and float(post_lows.min()) < base)
        if not dipped and not post_opens.empty:
            dipped = float(post_opens.iloc[0]) < base

        trough = float(post_lows.min()) if not post_lows.empty else base
        drop_value = max(0.0, base - trough)
        comeback_50 = False
        if drop_value > 0 and not post_closes.empty:
            target = trough + comeback_fraction * drop_value
            comeback_50 = bool(post_closes.max() >= target)

        kept_dipping = bool(not post_closes.empty and float(post_closes.iloc[-1]) < base)

        rows.append({
            "ticker": ticker,
            "earnings_date": edate.strftime("%Y-%m-%d"),
            "is_today": (edate.strftime("%Y-%m-%d") == now.date().isoformat()),
            "industry": industry_map.get(ticker),
            "result_class": result_class,
            "reaction_return_pct": (reaction_close / base - 1.0) * 100,
            "day_open": day_open,
            "day_high": day_high,
            "day_low": day_low,
            "day_close": day_close,
            "dipped": dipped,
            "drop_value_pct": (drop_value / base * 100) if base else 0.0,
            "comeback_50": comeback_50,
            "kept_dipping": kept_dipping,
        })

    # ---- industry aggregation + return for compute_patterns ----
    industries: dict[str, dict[str, Any]] = {}
    for r in rows:
        ind = r["industry"]
        if not ind:
            continue
        d = industries.setdefault(ind, {"total": 0, "positive": 0, "negative": 0, "stocks": set(), "positive_dipped": 0, "comeback_50": 0, "kept_dipping": 0})
        d["total"] += 1
        d["stocks"].add(r["ticker"])
        if r["result_class"] == "positive":
            d["positive"] += 1
            if r["dipped"]:
                d["positive_dipped"] += 1
            if r["comeback_50"]:
                d["comeback_50"] += 1
            if r["kept_dipping"]:
                d["kept_dipping"] += 1
        elif r["result_class"] == "negative":
            d["negative"] += 1

    breakdown = []
    for ind, d in industries.items():
        stocks = len(d["stocks"])
        breakdown.append({
            "industry": ind,
            "total": d["total"],
            "positive": d["positive"],
            "negative": d["negative"],
            "stocks": stocks,
            "ratio": (round(d["positive"] / stocks, 3) if stocks else 0.0),
            "positive_dipped": d["positive_dipped"],
            "comeback_50": d["comeback_50"],
            "kept_dipping": d["kept_dipping"],
        })
    breakdown.sort(key=lambda x: x["positive"], reverse=True)

    best_positive = max(breakdown, key=lambda x: x["positive"]) if breakdown else None
    ratio_eligible = [x for x in breakdown if x["stocks"] > 0]
    best_ratio = max(ratio_eligible, key=lambda x: x["ratio"]) if ratio_eligible else None

    positive_rows = [r for r in rows if r["result_class"] == "positive"]
    return {
        "total": len(rows),
        "positive": sum(1 for r in rows if r["result_class"] == "positive"),
        "negative": sum(1 for r in rows if r["result_class"] == "negative"),
        "neutral": sum(1 for r in rows if r["result_class"] == "neutral"),
        "best_positive_industry": best_positive,
        "best_ratio_industry": best_ratio,
        "positive_dipped_total": sum(1 for r in positive_rows if r["dipped"]),
        "comeback_50_total": sum(1 for r in positive_rows if r["comeback_50"]),
        "kept_dipping_total": sum(1 for r in positive_rows if r["kept_dipping"]),
        "today_count": sum(1 for r in rows if r["is_today"]),
        "today_positive": sum(1 for r in rows if r["is_today"] and r["result_class"] == "positive"),
        "today_came_back": sum(1 for r in rows if r["is_today"] and r["comeback_50"]),
        "today_no_recovery": sum(1 for r in rows if r["is_today"] and r["kept_dipping"]),
        "industries": breakdown,
        "rows": rows,
    }


def compute_earnings_verdicts(events: list[tuple[str, pd.Timestamp]], price_map: dict[str, pd.DataFrame], settings: Settings) -> dict[str, dict[str, Any]]:
    """Opt-in "how were the results?" verdict per ticker (no upfront cost as a rule).

    Uses the EPS surprise when present (mostly US tickers); otherwise (the common
    NSE case) compares each stock's post-result 3-day move to the median move of
    its industry peers in the same scan, labelling it Strong / Neutral / Weak.

    Returns ``{ticker: {"verdict", "metric", "industry"}}``.
    """
    if not events:
        return {}

    # Load surprise / EPS fields for each (ticker, date) from the earnings table.
    surprise_map: dict[tuple[str, str], dict[str, Any]] = {}
    with _earnings_connect(settings) as con:
        for ticker, edate in events:
            row = con.execute(
                "SELECT surprise_pct, eps_reported, eps_estimate FROM earnings_history "
                "WHERE ticker = ? AND earnings_date = ? LIMIT 1",
                (ticker, edate.strftime("%Y-%m-%d")),
            ).fetchone()
            surprise_map[(ticker, edate.strftime("%Y-%m-%d"))] = (
                {"surprise_pct": row[0], "eps_reported": row[1], "eps_estimate": row[2]}
                if row else {"surprise_pct": None, "eps_reported": None, "eps_estimate": None}
            )

    industry_map = get_industry_map([t for t, _ in events], settings)

    # Per-ticker post-result 3-day return (vs pre-result close) for peer comparison.
    ret3: dict[str, float] = {}
    for ticker, edate in events:
        prices = price_map.get(ticker)
        if prices is None or prices.empty or "close" not in prices.columns:
            continue
        closes = pd.to_numeric(prices["close"], errors="coerce").dropna()
        before = closes[closes.index < edate]
        after = closes[closes.index >= edate]
        if before.empty or len(after) < 3:
            continue
        base = float(before.iloc[-1])
        if base <= 0:
            continue
        ret3[ticker] = (float(after.iloc[2]) / base - 1.0) * 100

    # Median post-result 3-day move per industry.
    peers: dict[str, list[float]] = {}
    for ticker, ind in industry_map.items():
        if ticker in ret3:
            peers.setdefault(ind, []).append(ret3[ticker])
    medians = {ind: float(median(vals)) for ind, vals in peers.items() if vals}

    out: dict[str, dict[str, Any]] = {}
    for ticker, edate in events:
        ekey = (ticker, edate.strftime("%Y-%m-%d"))
        info = surprise_map.get(ekey, {})
        sur = info.get("surprise_pct")
        ind = industry_map.get(ticker)
        if sur is not None:
            verdict = "Beat" if sur >= 5 else ("Miss" if sur <= -5 else "In-line")
            metric = f"surprise {sur:+.1f}%"
        elif ticker in ret3 and ind in medians:
            r, m = ret3[ticker], medians[ind]
            if r >= m + 1.0:
                verdict = "Strong"
            elif r <= m - 1.0:
                verdict = "Weak"
            else:
                verdict = "Neutral"
            metric = f"{r:+.1f}% vs sector med {m:+.1f}%"
        else:
            verdict = "n/a"
            metric = "insufficient data"
        out[ticker] = {"verdict": verdict, "metric": metric, "industry": ind}
    return out
