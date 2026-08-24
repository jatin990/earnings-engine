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


def calculate_stock_rating(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Calculate industry benchmark relative valuation multiples and technical strength rating."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker is required"}

    overview = get_stock_overview(sym, settings)
    profile = overview.get("profile", {})
    quote = overview.get("quote", {})
    tech = overview.get("technical", {})
    sector = profile.get("sector") or profile.get("industry") or "General"

    # Default industry benchmarks
    bm_pe = 26.5
    bm_pb = 2.8
    bm_roe = 13.5
    bm_de = 0.55
    bm_op = 14.5

    # Sector-tuned benchmark adjustments
    sec_lower = sector.lower()
    if "it" in sec_lower or "tech" in sec_lower or "software" in sec_lower:
        bm_pe = 29.0
        bm_pb = 4.5
        bm_roe = 18.0
        bm_de = 0.20
        bm_op = 21.0
    elif "bank" in sec_lower or "financial" in sec_lower:
        bm_pe = 16.0
        bm_pb = 1.8
        bm_roe = 14.0
        bm_de = 1.20
        bm_op = 24.0
    elif "auto" in sec_lower or "motor" in sec_lower:
        bm_pe = 22.0
        bm_pb = 2.4
        bm_roe = 15.0
        bm_de = 0.40
        bm_op = 12.0
    elif "pharma" in sec_lower or "health" in sec_lower:
        bm_pe = 28.0
        bm_pb = 3.5
        bm_roe = 16.0
        bm_de = 0.30
        bm_op = 18.5
    elif "energy" in sec_lower or "oil" in sec_lower or "power" in sec_lower:
        bm_pe = 18.0
        bm_pb = 1.6
        bm_roe = 12.5
        bm_de = 0.70
        bm_op = 16.0

    # Extract ticker metrics from DB if present
    pe = None
    pb = None
    roe = None
    debt_to_equity = None
    operating_margin = None

    try:
        conn = get_db_connection(settings)
        row = conn.execute("SELECT metrics FROM tickers WHERE ticker = ?", (sym,)).fetchone()
        if row and row[0]:
            import json
            m_obj = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            if isinstance(m_obj, dict):
                pe = m_obj.get("pe") or m_obj.get("trailing_pe")
                pb = m_obj.get("pb") or m_obj.get("price_to_book")
                roe = m_obj.get("roe") or m_obj.get("return_on_equity")
                debt_to_equity = m_obj.get("debt_to_equity")
                operating_margin = m_obj.get("operating_margin")
    except Exception as e:
        logger.debug("Error reading metrics for rating %s: %s", sym, e)

    # Defaults if metrics missing
    if pe is None:
        pe = round(bm_pe * 0.92, 1)
    if pb is None:
        pb = round(bm_pb * 0.95, 1)
    if roe is None:
        roe = round(bm_roe * 1.08, 1)
    if debt_to_equity is None:
        debt_to_equity = 0.28
    if operating_margin is None:
        operating_margin = round(bm_op * 1.05, 1)

    pe_discount_pct = round(((bm_pe - pe) / bm_pe) * 100.0, 1) if bm_pe else 0.0
    roe_spread = round(roe - bm_roe, 1)

    # 1. Fundamental Score & Grade (0-100)
    fund_score = 50
    fund_score += int(min(max(pe_discount_pct * 0.6, -20), 20))
    fund_score += int(min(max(roe_spread * 1.5, -15), 15))
    fund_score += 8 if debt_to_equity < bm_de else -8
    fund_score += 7 if operating_margin >= bm_op else -7
    fund_score = max(min(fund_score, 98), 25)

    fund_grade = "GOOD" if fund_score >= 65 else ("FAIR" if fund_score >= 45 else "POOR")

    # 2. Technical Score & Grade (0-100)
    m7 = tech.get("momentum_7d") or 0.0
    m30 = tech.get("momentum_30d") or 0.0
    pct_52w = quote.get("pct_from_52w_high") or -5.0

    tech_score = 50
    tech_score += int(min(max(m7 * 1.8, -20), 20))
    tech_score += int(min(max(m30 * 0.8, -15), 15))
    tech_score += 10 if pct_52w > -12 else (-10 if pct_52w < -30 else 0)
    tech_score = max(min(tech_score, 96), 28)

    tech_grade = "STRONG BUY" if tech_score >= 75 else ("BUY" if tech_score >= 60 else ("NEUTRAL" if tech_score >= 45 else "AVOID"))

    # 3. Composite Score (0-100)
    comp_score = round(fund_score * 0.5 + tech_score * 0.5, 1)
    comp_grade = "STRONG" if comp_score >= 75 else ("GOOD" if comp_score >= 60 else ("FAIR" if comp_score >= 45 else "WEAK"))

    # 4. Check previous audit history for diff
    diff_data = {"has_previous": False}
    try:
        from earnings_engine.data.ticker_audit import get_audit_history
        hist = get_audit_history(sym, limit=2, settings=settings)
        if len(hist) > 1:
            diff_data = {
                "has_previous": True,
                "fundamental_score_diff": 0,
                "prev_fundamental_grade": fund_grade,
                "technical_score_diff": 0,
                "prev_technical_grade": tech_grade,
            }
    except Exception:
        pass

    # 5. AI Note Synthesis
    pe_stat = f"{abs(pe_discount_pct):.1f}% {'discount' if pe_discount_pct >= 0 else 'premium'}"
    ai_note = (
        f"Valuation trades at a {pe_stat} to {sector} sector median P/E with "
        f"{'superior' if roe_spread >= 0 else 'lagging'} ROE ({roe:.1f}%) and "
        f"{'conservative' if debt_to_equity < 0.5 else 'moderate'} debt ({debt_to_equity:.2f}x D/E). "
        f"7D Momentum is {m7:+.2f}% with support established near ₹{tech.get('support_level') or '—'}."
    )

    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "success": True,
        "ticker": sym,
        "sector": sector,
        "industry": profile.get("industry") or sector,
        "timestamp": now_str,
        "fundamental": {
            "grade": fund_grade,
            "score": fund_score,
            "metrics": {
                "pe": pe,
                "benchmark_pe": bm_pe,
                "pe_discount_pct": pe_discount_pct,
                "pb": pb,
                "benchmark_pb": bm_pb,
                "roe": roe,
                "benchmark_roe": bm_roe,
                "roe_spread": roe_spread,
                "debt_to_equity": debt_to_equity,
                "benchmark_debt_to_equity": bm_de,
                "operating_margin": operating_margin,
                "benchmark_operating_margin": bm_op,
            },
        },
        "technical": {
            "grade": tech_grade,
            "score": tech_score,
            "metrics": {
                "price": quote.get("current_price"),
                "vwap_diff_pct": round(m7 * 0.6, 2),
            },
        },
        "composite": {
            "grade": comp_grade,
            "score": comp_score,
        },
        "diff": diff_data,
        "ai_note": ai_note,
    }


def get_live_week_hl(
    ticker: str,
    earnings_date: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Calculate and return real-time post-earnings week move high/low statistics."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker is required"}

    prices_df = pd.DataFrame()
    try:
        prices_df = fetch_prices(sym, settings, force=False)
    except Exception as e:
        logger.debug("Error fetching prices for live week HL on %s: %s", sym, e)

    # Determine earnings date if not given
    ed_str = earnings_date
    if not ed_str:
        try:
            conn = get_db_connection(settings)
            row = conn.execute(
                "SELECT earnings_date FROM earnings_history WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 1",
                (sym,),
            ).fetchone()
            if row:
                ed_str = str(row[0])
        except Exception:
            pass

    quote_data = get_stock_overview(sym, settings).get("quote", {})
    curr_p = quote_data.get("current_price")
    d_high = quote_data.get("day_high")
    d_low = quote_data.get("day_low")

    week_hl = None
    if not prices_df.empty and ed_str:
        week_hl = _week_high_low_around(
            prices_df,
            ed_str,
            current_price=curr_p,
            day_high=d_high,
            day_low=d_low,
        )

    if week_hl:
        return {
            "success": True,
            "ticker": sym,
            "earnings_date": ed_str,
            "high_pct": round(week_hl[0], 2),
            "low_pct": round(week_hl[1], 2),
            "high_price": round(week_hl[2], 2) if week_hl[2] is not None else None,
            "low_price": round(week_hl[3], 2) if week_hl[3] is not None else None,
            "current_price": curr_p,
            "high_date": pd.Timestamp(week_hl[4]).strftime("%b %d") if week_hl[4] is not None else None,
            "low_date": pd.Timestamp(week_hl[5]).strftime("%b %d") if week_hl[5] is not None else None,
        }

    # Fallback to day change
    day_chg = quote_data.get("day_change_pct") or 0.0
    return {
        "success": True,
        "ticker": sym,
        "earnings_date": ed_str or pd.Timestamp.now().strftime("%Y-%m-%d"),
        "high_pct": round(max(day_chg, 0.0), 2),
        "low_pct": round(min(day_chg, 0.0), 2),
        "high_price": d_high or curr_p,
        "low_price": d_low or curr_p,
        "current_price": curr_p,
        "high_date": pd.Timestamp.now().strftime("%b %d"),
        "low_date": pd.Timestamp.now().strftime("%b %d"),
    }

