"""Pre-Market Setups and Overnight SEBI / Exchange Filings Radar.

Captures, categorizes, and scores corporate filings and high-impact news published
in the overnight after-hours window (6:00 PM on T-1 to 09:15 AM on T) before market open.
Computes estimated opening gap momentum, pre-market trigger levels, targets, and invalidations.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.catalysts_news import (
    _connect,
    get_short_term_catalysts,
    score_catalyst_headline,
    is_headline_current,
    CATALYST_RULES,
)
from earnings_engine.data.names import get_name

logger = logging.getLogger(__name__)

# Indian Standard Time (IST) Offset: UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)


def to_ist(dt_utc: datetime) -> datetime:
    """Convert UTC datetime to Indian Standard Time (IST)."""
    return dt_utc + IST_OFFSET


def parse_to_ist(published_at_str: str) -> tuple[datetime | None, str]:
    """Parse published_at timestamp into IST datetime and formatted label."""
    if not published_at_str:
        return None, "—"
    try:
        clean_str = str(published_at_str).strip()
        if "T" in clean_str:
            clean_str = clean_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
        else:
            dt = datetime.strptime(clean_str[:19], "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
        
        ist_dt = dt.astimezone(timezone(IST_OFFSET)) if dt.tzinfo else dt + IST_OFFSET
        time_label = ist_dt.strftime("%Y-%m-%d %H:%M IST")
        return ist_dt, time_label
    except Exception:
        return None, published_at_str


def is_in_overnight_window(
    published_at_str: str,
    window_mode: str = "standard_6pm",
    target_date: str | None = None,
) -> tuple[bool, str, str]:
    """Determine if publication timestamp falls in the after-hours / overnight pre-market window.

    Window modes:
    - 'standard_6pm' (Default): Post-18:00 (6:00 PM) on T-1 to 09:15 AM on T.
    - 'full_post_market': Post-15:30 (3:30 PM) on T-1 to 09:15 AM on T.
    - 'early_morning': 05:00 AM to 09:15 AM on T.
    - 'all_recent': Any publication in last 7 days falling in after-hours (>=18:00 or <=09:15).

    Returns:
        (is_match, session_tag, timing_description)
    """
    ist_dt, time_label = parse_to_ist(published_at_str)
    if not ist_dt:
        return False, "UNKNOWN", time_label

    hour = ist_dt.hour
    minute = ist_dt.minute
    time_float = hour + (minute / 60.0)

    # Classification by time of day
    if time_float >= 18.0:
        timing_desc = f"{ist_dt.strftime('%b %d')} {ist_dt.strftime('%H:%M')} IST (🌙 After 6 PM)"
        session_phase = "EVENING_FILING"
    elif time_float >= 15.5 and time_float < 18.0:
        timing_desc = f"{ist_dt.strftime('%b %d')} {ist_dt.strftime('%H:%M')} IST (🌆 Post-Close 3:30–6 PM)"
        session_phase = "POST_CLOSE"
    elif time_float <= 9.25:  # <= 09:15 AM
        timing_desc = f"{ist_dt.strftime('%b %d')} {ist_dt.strftime('%H:%M')} IST (🌅 Pre-Market Open)"
        session_phase = "PRE_OPEN"
    else:
        timing_desc = f"{ist_dt.strftime('%b %d')} {ist_dt.strftime('%H:%M')} IST (☀️ Intraday Market Session)"
        session_phase = "INTRADAY"

    if window_mode == "all_recent":
        is_match = (time_float >= 18.0 or time_float <= 9.25 or time_float >= 15.5)
        return is_match, session_phase, timing_desc

    if window_mode == "early_morning":
        is_match = (time_float >= 5.0 and time_float <= 9.25)
        return is_match, session_phase, timing_desc

    if window_mode == "full_post_market":
        is_match = (time_float >= 15.5 or time_float <= 9.25)
        return is_match, session_phase, timing_desc

    # Default 'standard_6pm': >= 18.0 (6:00 PM) or <= 09:15 AM
    is_match = (time_float >= 18.0 or time_float <= 9.25)
    return is_match, session_phase, timing_desc


def score_premarket_setup(
    item: dict[str, Any],
    prev_close: float | None = None,
    current_price: float | None = None,
) -> dict[str, Any]:
    """Compute opening gap estimates, trigger, target and stop levels for pre-market setups."""
    title = item.get("title", "")
    summary = item.get("summary", "")
    category = item.get("category", "General Financial News")
    direction = (item.get("direction") or "BULLISH").upper()
    impact_score = float(item.get("impact_score") or 60.0)

    base_price = prev_close or current_price or 100.0

    # Determine catalyst source badge
    full_text = f"{title} {summary}".lower()
    if any(w in full_text for w in ["sebi", "lodr", "disclosure", "intimation", "exchange filing", "bse filing", "nse filing"]):
        source_badge = "🏛️ SEBI / Exchange Disclosure"
        source_code = "SEBI_FILING"
    elif any(w in full_text for w in ["order win", "bags order", "secures order", "contract", "pact", "deal", "l1"]):
        source_badge = "📦 Order Win & Contract"
        source_code = "ORDER_WIN"
    elif any(w in full_text for w in ["fda", "usfda", "approval", "clearance", "eir"]):
        source_badge = "💊 USFDA / Regulatory Nod"
        source_code = "REGULATORY_NOD"
    elif any(w in full_text for w in ["profit surges", "net profit up", "beats", "earnings beat", "revenue surges"]):
        source_badge = "📊 Earnings Surprise Beat"
        source_code = "EARNINGS_BEAT"
    elif any(w in full_text for w in ["acquisition", "merger", "stake", "buys stake", "joint venture"]):
        source_badge = "🤝 M&A / Strategic Stake"
        source_code = "MA_EXPANSION"
    elif any(w in full_text for w in ["bonus", "split", "dividend", "buyback"]):
        source_badge = "⚡ Board / Corporate Action"
        source_code = "CORP_ACTION"
    else:
        source_badge = f"📰 {category}"
        source_code = "NEWS"

    # Gap and Volatility Estimation
    if direction == "BULLISH":
        if impact_score >= 85:
            gap_min = 4.0
            gap_max = 8.5
            action_badge = "🔥 Strong Gap Up Expected"
            action_code = "STRONG_GAP_UP"
            action_color = "#34d399"
        elif impact_score >= 70:
            gap_min = 2.0
            gap_max = 4.5
            action_badge = "🟢 Moderate Gap Up"
            action_code = "MILD_GAP_UP"
            action_color = "#38bdf8"
        else:
            gap_min = 0.8
            gap_max = 2.2
            action_badge = "⚖️ Mild Bullish Bias"
            action_code = "MILD_BULLISH"
            action_color = "#a78bfa"
        
        avg_gap_pct = round((gap_min + gap_max) / 2.0, 2)
        est_open_price = round(base_price * (1.0 + avg_gap_pct / 100.0), 2)
        premarket_trigger = round(base_price * (1.0 + gap_min / 100.0), 2)
        target_1 = round(est_open_price * 1.035, 2)
        target_2 = round(est_open_price * 1.075, 2)
        stop_loss = round(base_price * 0.985, 2)
    elif direction == "BEARISH":
        if impact_score >= 75:
            gap_min = -7.5
            gap_max = -3.5
            action_badge = "⚠️ High Risk / Gap Down"
            action_code = "RISK_GAP_DOWN"
            action_color = "#f87171"
        else:
            gap_min = -3.5
            gap_max = -1.2
            action_badge = "⚠️ Mild Bearish Gap"
            action_code = "MILD_BEARISH"
            action_color = "#fb923c"

        avg_gap_pct = round((gap_min + gap_max) / 2.0, 2)
        est_open_price = round(base_price * (1.0 + avg_gap_pct / 100.0), 2)
        premarket_trigger = round(base_price * (1.0 + gap_max / 100.0), 2)
        target_1 = round(est_open_price * 0.965, 2)
        target_2 = round(est_open_price * 0.925, 2)
        stop_loss = round(base_price * 1.02, 2)
    else:
        gap_min = -1.0
        gap_max = 1.5
        avg_gap_pct = 0.5
        action_badge = "⚖️ Neutral / Watchlist"
        action_code = "NEUTRAL"
        action_color = "#94a3b8"
        est_open_price = base_price
        premarket_trigger = round(base_price * 1.01, 2)
        target_1 = round(base_price * 1.03, 2)
        target_2 = round(base_price * 1.05, 2)
        stop_loss = round(base_price * 0.98, 2)

    return {
        "source_badge": source_badge,
        "source_code": source_code,
        "action_badge": action_badge,
        "action_code": action_code,
        "action_color": action_color,
        "est_gap_min_pct": gap_min,
        "est_gap_max_pct": gap_max,
        "avg_gap_pct": avg_gap_pct,
        "est_open_price": est_open_price,
        "premarket_trigger": premarket_trigger,
        "target_1": target_1,
        "target_2": target_2,
        "stop_loss": stop_loss,
        "base_price": base_price,
    }


def get_premarket_setups(
    window_mode: str = "standard_6pm",
    days_lookback: int = 7,
    category_filter: str = "ALL",
    direction_filter: str = "ALL",
    min_impact: float = 0.0,
    search_query: str = "",
    limit: int = 100,
    live_quotes: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Query, filter, score, and rank pre-market setups from overnight filings and news."""
    settings = settings or Settings()
    
    # 1. Fetch recent raw catalysts
    raw_catalysts = get_short_term_catalysts(
        days=days_lookback,
        impact_filter="ALL",
        category_filter="ALL",
        direction_filter="ALL",
        search_query="",
        limit=500,
        settings=settings,
    )

    setups: list[dict[str, Any]] = []

    for c in raw_catalysts:
        pub_at = c.get("published_at") or ""
        is_match, session_phase, timing_desc = is_in_overnight_window(pub_at, window_mode=window_mode)
        if not is_match and window_mode != "all_recent":
            continue

        impact_score = float(c.get("impact_score") or 50.0)
        if impact_score < min_impact:
            continue

        direction = (c.get("direction") or "NEUTRAL").upper()
        if direction_filter != "ALL" and direction != direction_filter.upper():
            continue

        category = c.get("category") or "General Financial News"
        if category_filter != "ALL" and category != category_filter:
            continue

        title = c.get("title") or ""
        summary = c.get("summary") or ""
        ticker = c.get("ticker") or ""
        stock_name = c.get("stock_name") or get_name(ticker) or ticker.replace(".NS", "")

        if search_query:
            sq = search_query.strip().lower()
            if sq not in title.lower() and sq not in summary.lower() and sq not in ticker.lower() and sq not in stock_name.lower():
                continue

        prev_close = c.get("signal_price")
        cur_price = c.get("current_price") or prev_close

        scored = score_premarket_setup(c, prev_close=prev_close, current_price=cur_price)

        setup_item = {
            "id": c.get("id"),
            "ticker": ticker,
            "stock_name": stock_name,
            "title": title,
            "summary": summary,
            "publisher": c.get("publisher") or "Exchange Filing",
            "link": c.get("link") or f"/stock/{ticker}",
            "published_at": pub_at,
            "timing_desc": timing_desc,
            "session_phase": session_phase,
            "category": category,
            "direction": direction,
            "impact_score": impact_score,
            "prev_close": prev_close or cur_price,
            "current_price": cur_price,
            "price_change_pct": c.get("price_change_pct") or 0.0,
            **scored,
        }
        setups.append(setup_item)

    # Sort setups by impact_score DESC, published_at DESC
    setups.sort(key=lambda x: (x["impact_score"], x["published_at"]), reverse=True)
    items = setups[:limit]

    # Compute KPI Summary Cards
    total_count = len(setups)
    strong_gappers = [s for s in setups if s.get("action_code") == "STRONG_GAP_UP" or s.get("impact_score", 0) >= 80]
    bullish_count = len([s for s in setups if s.get("direction") == "BULLISH"])
    bearish_count = len([s for s in setups if s.get("direction") == "BEARISH"])
    avg_impact = round(sum(s.get("impact_score", 0) for s in setups) / len(setups), 1) if setups else 0.0
    sebi_filings_count = len([s for s in setups if "SEBI" in s.get("source_code", "") or "ORDER" in s.get("source_code", "")])

    return {
        "success": True,
        "window_mode": window_mode,
        "total_setups": total_count,
        "as_of": datetime.now(timezone(IST_OFFSET)).strftime("%Y-%m-%d %H:%M:%S IST"),
        "summary": {
            "total_overnight_setups": total_count,
            "high_conviction_gappers": len(strong_gappers),
            "bullish_setups_count": bullish_count,
            "bearish_risk_count": bearish_count,
            "sebi_filings_count": sebi_filings_count,
            "avg_impact_score": avg_impact,
        },
        "items": items,
    }


def scan_premarket_filings(settings: Settings | None = None) -> dict[str, Any]:
    """Trigger background sweep of overnight corporate filings and news feeds."""
    settings = settings or Settings()
    from earnings_engine.data.catalysts_news import scan_watchlist_catalysts
    res = scan_watchlist_catalysts(watchlist_name="my_watchlist", limit_per_stock=3, force=True, settings=settings)
    return {
        "success": True,
        "scanned_summary": res,
        "timestamp": datetime.now(timezone(IST_OFFSET)).strftime("%Y-%m-%d %H:%M:%S IST"),
    }
