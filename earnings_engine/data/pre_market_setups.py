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


def get_dynamic_overnight_max_hours(now_ist: datetime | None = None) -> float:
    """Compute maximum hours lookback for the current post-market overnight window.

    Rules:
    - On Weekends (Saturday / Sunday) & Monday pre-market (up to Monday 15:15 IST):
      The overnight window spans from Friday 15:15 IST (3:15 PM) to Monday 09:15 IST.
      The lookback needs to span up to 76.0 hours to capture all Friday post-close filings.
    - On Regular Weekdays (Tuesday to Friday):
      Standard overnight window from T-1 post-close (15:15/18:00 IST) to today 09:15 IST (~28.0 hours).
    """
    if now_ist is None:
        now_ist = datetime.now(timezone(IST_OFFSET))

    weekday = now_ist.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    time_float = now_ist.hour + (now_ist.minute / 60.0)

    # Saturday (weekday 5): Friday 15:15 IST was 1 day ago (~36h max)
    if weekday == 5:
        friday_close = (now_ist - timedelta(days=1)).replace(hour=15, minute=15, second=0, microsecond=0)
        elapsed = (now_ist - friday_close).total_seconds() / 3600.0
        return max(36.0, elapsed + 4.0)

    # Sunday (weekday 6): Friday 15:15 IST was 2 days ago (~60h max)
    if weekday == 6:
        friday_close = (now_ist - timedelta(days=2)).replace(hour=15, minute=15, second=0, microsecond=0)
        elapsed = (now_ist - friday_close).total_seconds() / 3600.0
        return max(60.0, elapsed + 4.0)

    # Monday (weekday 0): Before Monday 15:15 close, Friday 15:15 IST was 3 days ago (~76h max)
    if weekday == 0 and time_float <= 15.25:
        friday_close = (now_ist - timedelta(days=3)).replace(hour=15, minute=15, second=0, microsecond=0)
        elapsed = (now_ist - friday_close).total_seconds() / 3600.0
        return max(76.0, elapsed + 4.0)

    # Regular weekday default
    return 28.0


def is_in_overnight_window(
    published_at_str: str,
    window_mode: str = "standard_6pm",
    target_date: str | None = None,
    max_hours_ago: float | None = None,
    now_ist: datetime | None = None,
) -> tuple[bool, str, str]:
    """Determine if publication timestamp falls in the after-hours / overnight pre-market window.

    Window modes:
    - 'standard_6pm' (Default): Post-18:00 (6:00 PM) on T-1 to 09:15 AM on T.
      * Note: On weekends (Sat/Sun) & Monday pre-market, automatically expands to Friday 15:15 IST – Monday 09:15 AM.
    - 'full_post_market': Post-15:15 (3:15 PM) on T-1 to 09:15 AM on T.
    - 'early_morning': 05:00 AM to 09:15 AM on T.
    - 'all_recent': Any publication in last 7 days falling in after-hours (>=18:00 or <=09:15).

    Returns:
        (is_match, session_tag, timing_description)
    """
    ist_dt, time_label = parse_to_ist(published_at_str)
    if not ist_dt:
        return False, "UNKNOWN", time_label

    if now_ist is None:
        if target_date:
            parsed_target, _ = parse_to_ist(f"{target_date} 08:30:00 IST")
            if parsed_target:
                now_ist = parsed_target
        if now_ist is None:
            now_ist = datetime.now(timezone(IST_OFFSET))

    hours_ago = (now_ist - ist_dt).total_seconds() / 3600.0

    weekday = now_ist.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    time_float_now = now_ist.hour + (now_ist.minute / 60.0)

    # Dynamic lookback max hours if not explicitly forced
    effective_max_hours = max_hours_ago if max_hours_ago is not None else get_dynamic_overnight_max_hours(now_ist)

    if window_mode != "all_recent" and hours_ago > effective_max_hours:
        return False, "HISTORICAL", time_label

    # Check Weekend / Monday Pre-Market Window: Friday 15:15 IST to Monday 09:15 AM
    is_weekend_or_monday = (weekday in (5, 6)) or (weekday == 0 and time_float_now <= 15.25)
    if is_weekend_or_monday and window_mode in ("standard_6pm", "full_post_market"):
        days_to_friday = 1 if weekday == 5 else (2 if weekday == 6 else 3)
        friday_1515 = (now_ist - timedelta(days=days_to_friday)).replace(
            hour=15, minute=15, second=0, microsecond=0
        )
        
        # End of pre-market window on Monday 09:15 AM
        if weekday == 0:
            monday_0915 = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        else:
            days_to_monday = (7 - weekday)
            monday_0915 = (now_ist + timedelta(days=days_to_monday)).replace(
                hour=9, minute=15, second=0, microsecond=0
            )

        cutoff_end = min(now_ist, monday_0915) if weekday == 0 else now_ist

        if ist_dt >= friday_1515 and ist_dt <= cutoff_end + timedelta(minutes=15):
            timing_desc = f"{ist_dt.strftime('%b %d %H:%M')} IST (🌙 Weekend Post-Close Fri 3:15 PM – Mon 9:15 AM)"
            session_phase = "WEEKEND_OVERNIGHT"
            return True, session_phase, timing_desc

    hour = ist_dt.hour
    minute = ist_dt.minute
    time_float = hour + (minute / 60.0)

    # Standard weekday classification by time of day
    if time_float >= 18.0:
        timing_desc = f"{ist_dt.strftime('%b %d %H:%M')} IST (🌙 After 6 PM)"
        session_phase = "EVENING_FILING"
    elif time_float >= 15.25 and time_float < 18.0:
        timing_desc = f"{ist_dt.strftime('%b %d %H:%M')} IST (🌆 Post-Close 3:15–6 PM)"
        session_phase = "POST_CLOSE"
    elif time_float <= 9.25:  # <= 09:15 AM
        timing_desc = f"{ist_dt.strftime('%b %d %H:%M')} IST (🌅 Pre-Market Open)"
        session_phase = "PRE_OPEN"
    else:
        timing_desc = f"{ist_dt.strftime('%b %d %H:%M')} IST (☀️ Intraday Market Session)"
        session_phase = "INTRADAY"

    if window_mode == "all_recent":
        is_match = (time_float >= 18.0 or time_float <= 9.25 or time_float >= 15.25)
        return is_match, session_phase, timing_desc

    if window_mode == "early_morning":
        is_match = (time_float >= 5.0 and time_float <= 9.25)
        return is_match, session_phase, timing_desc

    if window_mode == "full_post_market":
        is_match = (time_float >= 15.25 or time_float <= 9.25)
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
    base_price = prev_close or current_price or 0.0

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
    
    now_ist = datetime.now(timezone(IST_OFFSET))

    # Active overnight window lookback:
    # If standard_6pm, full_post_market, early_morning: adapt max_hours to weekend/weekday context
    # If all_recent: allow full archive lookback (e.g. 7-14 days)
    if window_mode == "all_recent":
        max_hours = days_lookback * 24.0
    else:
        max_hours = get_dynamic_overnight_max_hours(now_ist)

    # 1. Fetch recent raw catalysts (ensure lookback window is at least 4 days on weekends/Monday)
    fetch_days = max(days_lookback, 4 if now_ist.weekday() in (0, 5, 6) else 2)
    raw_catalysts = get_short_term_catalysts(
        days=fetch_days,
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
        ist_dt, time_label = parse_to_ist(pub_at)
        is_match, session_phase, timing_desc = is_in_overnight_window(
            pub_at,
            window_mode=window_mode,
            max_hours_ago=max_hours,
            now_ist=now_ist,
        )
        if not is_match:
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
            "published_at": time_label,
            "published_at_raw": pub_at,
            "published_at_ist": time_label,
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

    # Group setups by ticker so the same stock has 1 primary row and collapsible other headlines
    grouped_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for s in setups:
        t = s["ticker"]
        if t not in grouped_by_ticker:
            grouped_by_ticker[t] = []
        grouped_by_ticker[t].append(s)

    deduped_setups: list[dict[str, Any]] = []
    for t, group in grouped_by_ticker.items():
        # Sort group by impact_score DESC, published_at DESC
        group.sort(key=lambda x: (x["impact_score"], x.get("published_at_raw") or x["published_at"]), reverse=True)
        primary = dict(group[0])
        primary["headlines_count"] = len(group)
        primary["all_headlines"] = group
        primary["other_headlines"] = group[1:] if len(group) > 1 else []
        deduped_setups.append(primary)

    # Sort deduped setups by impact_score DESC, published_at DESC
    deduped_setups.sort(key=lambda x: (x["impact_score"], x.get("published_at_raw") or x["published_at"]), reverse=True)
    items = deduped_setups[:limit]

    # Compute KPI Summary Cards
    total_count = len(deduped_setups)
    strong_gappers = [s for s in deduped_setups if s.get("action_code") == "STRONG_GAP_UP" or s.get("impact_score", 0) >= 80]
    bullish_count = len([s for s in deduped_setups if s.get("direction") == "BULLISH"])
    bearish_count = len([s for s in deduped_setups if s.get("direction") == "BEARISH"])
    avg_impact = round(sum(s.get("impact_score", 0) for s in deduped_setups) / len(deduped_setups), 1) if deduped_setups else 0.0
    sebi_filings_count = len([s for s in deduped_setups if "SEBI" in s.get("source_code", "") or "ORDER" in s.get("source_code", "")])

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


def get_historical_premarket_outcomes(
    days_lookback: int = 90,
    category_filter: str = "ALL",
    direction_filter: str = "ALL",
    min_impact: float = 0.0,
    search_query: str = "",
    limit: int = 150,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Verify historical pre-market setups against actual market open and day candles, computing accuracy metrics."""
    settings = settings or Settings()

    # 1. Fetch raw catalysts in lookback window
    raw_catalysts = get_short_term_catalysts(
        days=days_lookback,
        impact_filter="ALL",
        category_filter="ALL",
        direction_filter="ALL",
        search_query="",
        limit=600,
        settings=settings,
    )

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        verified_items: list[dict[str, Any]] = []

        for c in raw_catalysts:
            pub_at = c.get("published_at") or ""
            is_match, session_phase, timing_desc = is_in_overnight_window(pub_at, window_mode="all_recent")
            if not is_match:
                continue

            impact_score = float(c.get("impact_score") or 50.0)
            if impact_score < min_impact:
                continue

            direction = (c.get("direction") or "NEUTRAL").upper()
            if direction_filter != "ALL" and direction != direction_filter.upper():
                continue

            category = c.get("category") or "Miscellaneous Corporate Disclosures"
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

            pub_date = pub_at[:10]
            if not pub_date or not ticker:
                continue

            # Query the trade day T candle on or after pub_date
            candle_rows = conn.execute(
                """
                SELECT date, open, high, low, close, volume 
                FROM price_history 
                WHERE ticker = ? AND date >= ? 
                ORDER BY date ASC LIMIT 2
                """,
                (ticker, pub_date),
            ).fetchall()

            if not candle_rows:
                continue

            day_candle = candle_rows[0]
            candle_date = day_candle["date"]
            open_p = float(day_candle["open"]) if day_candle["open"] is not None else None
            high_p = float(day_candle["high"]) if day_candle["high"] is not None else None
            low_p = float(day_candle["low"]) if day_candle["low"] is not None else None
            close_p = float(day_candle["close"]) if day_candle["close"] is not None else None

            # Look up base T-1 close price before candle_date
            prev_row = conn.execute(
                """
                SELECT close, date FROM price_history 
                WHERE ticker = ? AND date < ? AND close > 0
                ORDER BY date DESC LIMIT 1
                """,
                (ticker, candle_date),
            ).fetchone()

            prev_close = float(prev_row[0]) if prev_row and prev_row[0] is not None else (open_p or close_p or 0.0)

            if not prev_close or prev_close <= 0:
                continue

            # Self-healing & outlier protection against corrupted candle bars
            if close_p is None or close_p <= 0:
                close_p = open_p or prev_close

            if open_p is None or open_p <= 0 or (prev_close > 0 and (open_p < 0.3 * prev_close or open_p > 3.0 * prev_close)):
                open_p = close_p or prev_close

            if high_p is None or high_p < max(open_p, close_p):
                high_p = max(open_p, close_p)

            if low_p is None or low_p <= 0 or (prev_close > 0 and low_p < 0.2 * prev_close):
                low_p = min(open_p, close_p)

            # Compute planned levels
            scored = score_premarket_setup(c, prev_close=prev_close, current_price=close_p)
            t1 = scored["target_1"]
            t2 = scored["target_2"]
            sl = scored["stop_loss"]

            # Realized gaps and price action
            actual_gap_pct = round(((open_p - prev_close) / prev_close) * 100.0, 2)
            day_return_pct = round(((close_p - prev_close) / prev_close) * 100.0, 2)
            intraday_run_pct = round(((high_p - open_p) / open_p) * 100.0, 2) if open_p > 0 else 0.0
            max_gain_pct = round(((high_p - prev_close) / prev_close) * 100.0, 2)
            max_drawdown_pct = round(((low_p - prev_close) / prev_close) * 100.0, 2)

            # Outcome verification
            t1_hit = False
            t2_hit = False
            sl_hit = False
            is_win = False

            if direction == "BULLISH":
                if high_p >= t2:
                    t2_hit = True
                    t1_hit = True
                    is_win = True
                    outcome_code = "TARGET_2_HIT"
                    outcome_badge = f"🎯 Target 2 Hit (+{max_gain_pct}%)"
                    outcome_color = "#10b981"
                elif high_p >= t1:
                    t1_hit = True
                    is_win = True
                    outcome_code = "TARGET_1_HIT"
                    outcome_badge = f"✅ Target 1 Hit (+{max_gain_pct}%)"
                    outcome_color = "#34d399"
                elif actual_gap_pct > 0 and day_return_pct > 0:
                    is_win = True
                    outcome_code = "GAP_HELD"
                    outcome_badge = f"🟢 Gap Held Green (+{day_return_pct}%)"
                    outcome_color = "#38bdf8"
                elif low_p <= sl:
                    sl_hit = True
                    outcome_code = "STOP_LOSS_HIT"
                    outcome_badge = f"🛑 Stop Hit ({max_drawdown_pct}%)"
                    outcome_color = "#f43f5e"
                else:
                    outcome_code = "GAP_FADED"
                    outcome_badge = f"⚠️ Gap Faded ({day_return_pct}%)"
                    outcome_color = "#fbbf24"
            elif direction == "BEARISH":
                if low_p <= t2:
                    t2_hit = True
                    t1_hit = True
                    is_win = True
                    outcome_code = "TARGET_2_HIT"
                    outcome_badge = f"🎯 Target 2 Hit ({max_drawdown_pct}%)"
                    outcome_color = "#10b981"
                elif low_p <= t1:
                    t1_hit = True
                    is_win = True
                    outcome_code = "TARGET_1_HIT"
                    outcome_badge = f"✅ Target 1 Hit ({max_drawdown_pct}%)"
                    outcome_color = "#34d399"
                elif actual_gap_pct < 0 and day_return_pct < 0:
                    is_win = True
                    outcome_code = "GAP_HELD"
                    outcome_badge = f"🟢 Gap Down Held ({day_return_pct}%)"
                    outcome_color = "#38bdf8"
                elif high_p >= sl:
                    sl_hit = True
                    outcome_code = "STOP_LOSS_HIT"
                    outcome_badge = f"🛑 Stop Hit (+{max_gain_pct}%)"
                    outcome_color = "#f43f5e"
                else:
                    outcome_code = "GAP_FADED"
                    outcome_badge = f"⚠️ Faded ({day_return_pct}%)"
                    outcome_color = "#fbbf24"
            else:
                is_win = abs(day_return_pct) <= 2.0
                outcome_code = "NEUTRAL"
                outcome_badge = f"⚖️ Neutral ({day_return_pct}%)"
                outcome_color = "#94a3b8"

            verified_items.append({
                "id": c.get("id"),
                "ticker": ticker,
                "stock_name": stock_name,
                "title": title,
                "summary": summary,
                "publisher": c.get("publisher") or "Exchange Feed",
                "published_at": pub_at,
                "session_date": candle_date,
                "timing_desc": timing_desc,
                "session_phase": session_phase,
                "category": category,
                "direction": direction,
                "impact_score": impact_score,
                "prev_close": prev_close,
                "actual_open": open_p,
                "actual_gap_pct": actual_gap_pct,
                "day_high": high_p,
                "day_low": low_p,
                "day_close": close_p,
                "day_return_pct": day_return_pct,
                "max_gain_pct": max_gain_pct,
                "max_drawdown_pct": max_drawdown_pct,
                "intraday_run_pct": intraday_run_pct,
                "target_1": t1,
                "target_2": t2,
                "stop_loss": sl,
                "target_1_hit": t1_hit,
                "target_2_hit": t2_hit,
                "stop_loss_hit": sl_hit,
                "is_win": is_win,
                "outcome_code": outcome_code,
                "outcome_badge": outcome_badge,
                "outcome_color": outcome_color,
                "action_badge": scored["action_badge"],
                "action_code": scored["action_code"],
                "action_color": scored.get("action_color", "#38bdf8"),
                "source_badge": scored["source_badge"],
                "source_code": scored["source_code"],
            })

    # Sort historical verified setups by session_date DESC, impact_score DESC
    verified_items.sort(key=lambda x: (x["session_date"], x["published_at"]), reverse=True)
    items = verified_items[:limit]

    # Compute Aggregated Accuracy Breakdown Matrices
    accuracy_by_category = _compute_accuracy_grouping(verified_items, group_key="category")
    accuracy_by_action = _compute_accuracy_grouping(verified_items, group_key="action_code")

    # Global KPI summary
    total_ver = len(verified_items)
    wins = len([v for v in verified_items if v["is_win"]])
    t1_hits = len([v for v in verified_items if v["target_1_hit"]])
    t2_hits = len([v for v in verified_items if v["target_2_hit"]])
    win_rate = round((wins / total_ver * 100.0), 1) if total_ver else 0.0
    t1_rate = round((t1_hits / total_ver * 100.0), 1) if total_ver else 0.0
    t2_rate = round((t2_hits / total_ver * 100.0), 1) if total_ver else 0.0
    avg_gap = round(sum(v["actual_gap_pct"] for v in verified_items) / total_ver, 2) if total_ver else 0.0
    avg_return = round(sum(v["day_return_pct"] for v in verified_items) / total_ver, 2) if total_ver else 0.0

    return {
        "success": True,
        "total_verified": total_ver,
        "as_of": datetime.now(timezone(IST_OFFSET)).strftime("%Y-%m-%d %H:%M:%S IST"),
        "track_record_summary": {
            "total_verified_setups": total_ver,
            "win_rate_pct": win_rate,
            "target_1_hit_rate_pct": t1_rate,
            "target_2_hit_rate_pct": t2_rate,
            "avg_realized_open_gap_pct": avg_gap,
            "avg_day_return_pct": avg_return,
            "total_wins": wins,
        },
        "accuracy_by_category": accuracy_by_category,
        "accuracy_by_action": accuracy_by_action,
        "items": items,
    }


def _compute_accuracy_grouping(items: list[dict[str, Any]], group_key: str) -> list[dict[str, Any]]:
    """Group verified items by key and compute win rate, target hit rate, and average returns."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        k = item.get(group_key) or "Unknown"
        groups.setdefault(k, []).append(item)

    results: list[dict[str, Any]] = []
    for k, sub_items in groups.items():
        n = len(sub_items)
        wins = len([x for x in sub_items if x.get("is_win")])
        t1_count = len([x for x in sub_items if x.get("target_1_hit")])
        t2_count = len([x for x in sub_items if x.get("target_2_hit")])
        win_rate = round((wins / n * 100.0), 1) if n else 0.0
        t1_rate = round((t1_count / n * 100.0), 1) if n else 0.0
        t2_rate = round((t2_count / n * 100.0), 1) if n else 0.0
        avg_gap = round(sum(x.get("actual_gap_pct", 0.0) for x in sub_items) / n, 2) if n else 0.0
        avg_ret = round(sum(x.get("day_return_pct", 0.0) for x in sub_items) / n, 2) if n else 0.0

        results.append({
            "group_name": k,
            "total_setups": n,
            "wins": wins,
            "win_rate_pct": win_rate,
            "target_1_hit_rate_pct": t1_rate,
            "target_2_hit_rate_pct": t2_rate,
            "avg_open_gap_pct": avg_gap,
            "avg_day_return_pct": avg_ret,
        })

    results.sort(key=lambda x: (x["total_setups"], x["win_rate_pct"]), reverse=True)
    return results


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

