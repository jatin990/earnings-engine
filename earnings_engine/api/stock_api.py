"""Comprehensive Stock Intelligence Aggregator.

Assembles complete fundamentals, live quotes, technical swing ranges,
quarterly earnings signals, multi-model AI consensus trade setup, and news catalysts.
"""

from __future__ import annotations

import logging
from typing import Any
import pandas as pd
import yfinance as yf

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.prices import fetch_prices
from earnings_engine.data.market_context import _week_high_low_around, detect_swing_range
from earnings_engine.data.swing_ranges import get_swing_range
from earnings_engine.data.catalysts_news import get_short_term_catalysts
from earnings_engine.consensus.storage import get_predictions

logger = logging.getLogger(__name__)


def get_stock_overview(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Compile a full stock intelligence overview for a single ticker."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}

    profile: dict[str, Any] = {
        "ticker": sym,
        "name": sym.replace(".NS", ""),
        "market": "NSE" if sym.endswith(".NS") else "US",
        "market_cap": None,
        "sector": "Equities",
        "industry": "General",
        "currency": "₹" if sym.endswith(".NS") else "$",
    }

    # 1. Fetch metadata from DB ticker master if available
    try:
        conn = get_db_connection(settings)
        row = conn.execute(
            "SELECT name, market_cap, sector, industry, metrics FROM tickers WHERE ticker = ?",
            (sym,),
        ).fetchone()
        if row:
            if row[0]: profile["name"] = row[0]
            if row[1]: profile["market_cap"] = float(row[1])
            if len(row) > 2 and row[2]: profile["sector"] = row[2]
            if len(row) > 3 and row[3]: profile["industry"] = row[3]
    except Exception as e:
        logger.debug("Error querying ticker master for %s: %s", sym, e)

    # 2. Quotes & Price Action
    quote: dict[str, Any] = {
        "current_price": None,
        "day_change": None,
        "day_change_pct": None,
        "previous_close": None,
        "day_high": None,
        "day_low": None,
        "week_52_high": None,
        "week_52_low": None,
        "volume": None,
        "avg_volume": None,
        "pct_from_52w_high": None,
        "pct_from_52w_low": None,
    }

    prices_df = pd.DataFrame()
    try:
        prices_df = fetch_prices(sym, settings, force=False)
    except Exception as e:
        logger.debug("Error fetching cached prices for %s: %s", sym, e)

    # Try live fast_info
    try:
        yf_obj = yf.Ticker(sym)
        fast = yf_obj.fast_info or {}
        last_p = fast.get("last_price")
        prev_c = fast.get("previous_close")
        if last_p is not None and last_p > 0:
            quote["current_price"] = round(float(last_p), 2)
            quote["previous_close"] = round(float(prev_c), 2) if prev_c else None
            if prev_c and prev_c > 0:
                quote["day_change"] = round(float(last_p - prev_c), 2)
                quote["day_change_pct"] = round(float((last_p / prev_c - 1.0) * 100.0), 2)
            quote["day_high"] = round(float(fast.get("day_high")), 2) if fast.get("day_high") else None
            quote["day_low"] = round(float(fast.get("day_low")), 2) if fast.get("day_low") else None
            quote["week_52_high"] = round(float(fast.get("year_high")), 2) if fast.get("year_high") else None
            quote["week_52_low"] = round(float(fast.get("year_low")), 2) if fast.get("year_low") else None
            if fast.get("market_cap") and not profile.get("market_cap"):
                profile["market_cap"] = float(fast.get("market_cap"))
    except Exception as e:
        logger.debug("Error fetching yfinance fast_info for %s: %s", sym, e)

    # Fallback to prices_df if fast_info missing
    if not prices_df.empty and "close" in prices_df.columns:
        closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
        if not closes.empty:
            if quote["current_price"] is None:
                quote["current_price"] = round(float(closes.iloc[-1]), 2)
                if len(closes) >= 2:
                    p_close = float(closes.iloc[-2])
                    quote["previous_close"] = round(p_close, 2)
                    quote["day_change"] = round(float(quote["current_price"] - p_close), 2)
                    quote["day_change_pct"] = round(float((quote["current_price"] / p_close - 1.0) * 100.0), 2)
            if quote["week_52_high"] is None and len(closes) >= 20:
                quote["week_52_high"] = round(float(closes.tail(252).max()), 2)
            if quote["week_52_low"] is None and len(closes) >= 20:
                quote["week_52_low"] = round(float(closes.tail(252).min()), 2)

    # Compute 52W % distances
    if quote["current_price"] and quote["week_52_high"] and quote["week_52_high"] > 0:
        quote["pct_from_52w_high"] = round((quote["current_price"] / quote["week_52_high"] - 1.0) * 100.0, 2)
    if quote["current_price"] and quote["week_52_low"] and quote["week_52_low"] > 0:
        quote["pct_from_52w_low"] = round((quote["current_price"] / quote["week_52_low"] - 1.0) * 100.0, 2)

    # 3. Technical Swing Structure & Momentum
    technical: dict[str, Any] = {
        "swing_range_20d": None,
        "swing_range_3m": None,
        "support_level": None,
        "resistance_level": None,
        "cycles": 0,
        "avg_cycle_days": 0,
        "momentum_3d": None,
        "momentum_7d": None,
        "momentum_30d": None,
    }

    if not prices_df.empty and "close" in prices_df.columns:
        closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
        if not closes.empty:
            auto_rng = detect_swing_range(closes)
            technical["swing_range_20d"] = {
                "lower": auto_rng.get("lower"),
                "upper": auto_rng.get("upper"),
            }
            technical["swing_range_3m"] = {
                "lower": auto_rng.get("three_month_lower"),
                "upper": auto_rng.get("three_month_upper"),
            }
            technical["support_level"] = auto_rng.get("lower")
            technical["resistance_level"] = auto_rng.get("upper")
            technical["cycles"] = auto_rng.get("cycles", 0)
            technical["avg_cycle_days"] = auto_rng.get("avg_days", 0)

            latest_c = float(closes.iloc[-1])
            if len(closes) >= 4:
                p3 = float(closes.iloc[-4])
                technical["momentum_3d"] = round((latest_c / p3 - 1.0) * 100.0, 2) if p3 else None
            if len(closes) >= 8:
                p7 = float(closes.iloc[-8])
                technical["momentum_7d"] = round((latest_c / p7 - 1.0) * 100.0, 2) if p7 else None
            if len(closes) >= 22:
                p30 = float(closes.iloc[-22])
                technical["momentum_30d"] = round((latest_c / p30 - 1.0) * 100.0, 2) if p30 else None

    # Stored swing range override if present
    stored_sr = get_swing_range("ALL", sym, settings)
    if stored_sr:
        technical["stored_swing_range"] = stored_sr
        if stored_sr.get("lower_bound"): technical["support_level"] = stored_sr["lower_bound"]
        if stored_sr.get("upper_bound"): technical["resistance_level"] = stored_sr["upper_bound"]

    # 4. Quarterly Earnings Track Record
    earnings_history: list[dict[str, Any]] = []
    try:
        conn = get_db_connection(settings)
        e_rows = conn.execute(
            "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 8",
            (sym,),
        ).fetchall()
        for r in e_rows:
            ed_str = r[0]
            eps_est = float(r[1]) if r[1] is not None else None
            eps_rep = float(r[2]) if r[2] is not None else None
            surp = float(r[3]) if r[3] is not None else None

            # Calculate post-earnings week high/low move
            week_hl = None
            if not prices_df.empty:
                week_hl = _week_high_low_around(
                    prices_df,
                    ed_str,
                    current_price=quote.get("current_price"),
                    day_high=quote.get("day_high"),
                    day_low=quote.get("day_low"),
                )

            earnings_history.append({
                "earnings_date": ed_str,
                "eps_estimate": eps_est,
                "eps_reported": eps_rep,
                "surprise_pct": round(surp, 2) if surp is not None else None,
                "week_high_pct": round(week_hl[0], 2) if week_hl else None,
                "week_low_pct": round(week_hl[1], 2) if week_hl else None,
                "week_high_price": round(week_hl[2], 2) if week_hl else None,
                "week_low_price": round(week_hl[3], 2) if week_hl else None,
                "high_date": pd.Timestamp(week_hl[4]).strftime("%b %d") if week_hl and week_hl[4] is not None else None,
                "low_date": pd.Timestamp(week_hl[5]).strftime("%b %d") if week_hl and week_hl[5] is not None else None,
            })
    except Exception as e:
        logger.debug("Error fetching earnings history for %s: %s", sym, e)

    # 5. Multi-Model AI Consensus Prediction & Trade Setup
    preds = get_predictions(settings, ticker=sym, limit=1)
    consensus_data = preds[0] if preds else None

    # 6. Live Short-Term News Catalysts
    catalysts_data = get_short_term_catalysts(watchlist_or_universe="ALL", search_query=sym, limit=15, settings=settings)

    # 7. Check Watchlist status
    is_in_watchlist = False
    try:
        from earnings_engine.data.watchlists import get_watchlist
        wl = get_watchlist("DEFAULT", settings) or []
        is_in_watchlist = sym in wl
    except Exception:
        pass

    return {
        "success": True,
        "ticker": sym,
        "profile": profile,
        "quote": quote,
        "technical": technical,
        "earnings_history": earnings_history,
        "consensus": consensus_data,
        "catalysts": catalysts_data,
        "is_in_watchlist": is_in_watchlist,
    }
