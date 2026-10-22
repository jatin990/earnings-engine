"""Timeline reconstruction and chronological milestone tracking for Breakout Radar candidates."""

from __future__ import annotations

import json
import logging
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner.state import _pool
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.breakout_scanner.audit_log import get_breakout_audit_log

logger = logging.getLogger(__name__)


def get_stock_breakout_timeline(
    ticker: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve full chronological lifecycle timeline & transition notes for a given stock."""
    settings = settings or Settings()
    sym = (ticker or "").strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"

    # 1. Fetch current snapshot from in-memory pool or database
    snap = None
    if sym in _pool.get("hot", {}):
        snap = dict(_pool["hot"][sym]["result"])
    elif sym in _pool.get("warm", {}):
        snap = dict(_pool["warm"][sym]["result"])

    if not snap:
        try:
            conn = get_db_connection(settings)
            row = conn.execute("SELECT * FROM breakout_radar WHERE ticker = ?", (sym,)).fetchone()
            if row:
                if hasattr(row, "get"):
                    raw_json = row.get("data_json")
                    if raw_json:
                        try:
                            snap = json.loads(raw_json)
                        except Exception:
                            pass
                    if not snap:
                        snap = dict(row)
                elif isinstance(row, (tuple, list)) and len(row) >= 33 and row[32]:
                    try:
                        snap = json.loads(row[32])
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("[TIMELINE] DB query notice for %s: %s", sym, e)

    if not snap:
        # Fallback to evaluating on-demand
        import sys
        mod = sys.modules.get("earnings_engine.data.breakout_scanner")
        eval_fn = getattr(mod, "evaluate_stock_breakout", None) if mod else None
        if not eval_fn:
            from earnings_engine.data.breakout_scanner.pipeline import evaluate_stock_breakout
            eval_fn = evaluate_stock_breakout
        snap = eval_fn(sym, settings=settings)

    # 2. Extract key metrics
    company_name = snap.get("company_name") or sym.replace(".NS", "")
    industry = snap.get("industry") or "Equities"
    tier = (snap.get("tier") or "WARM").upper()
    cur_p = snap.get("current_price") or snap.get("signal_price") or 0.0
    sig_p = snap.get("signal_price") or cur_p
    trig_p = snap.get("breakout_trigger") or cur_p
    target_p = snap.get("target_price") or (trig_p * 1.08 if trig_p else cur_p)
    stop_p = snap.get("stop_loss") or (trig_p * 0.95 if trig_p else cur_p)
    rr = snap.get("risk_reward_ratio") or 2.0
    sig_date = snap.get("signal_date") or snap.get("scanned_at", "")[:10] or "2026-08-28"
    days_elapsed = snap.get("days_elapsed") or 0
    outcome = snap.get("outcome") or "ACTIVE"
    outcome_label = snap.get("outcome_label") or "Active Setup"
    outcome_badge = snap.get("outcome_badge") or "emerald"
    ret_pct = snap.get("realized_return_pct") or 0.0
    max_gain = snap.get("max_gain_pct") or 0.0
    post_high = snap.get("post_high") or snap.get("peak_price") or cur_p
    comp_score = snap.get("composite_score") or 0.0

    # 3. Retrieve raw audit logs from database
    raw_logs = get_breakout_audit_log(sym, limit=20, settings=settings)
    events: list[dict[str, Any]] = []

    # Map raw logs to timeline events
    for l in raw_logs:
        ev_type = l.get("event_type", "TRANSITION")
        f_tier = l.get("from_tier", "")
        t_tier = l.get("to_tier", "")
        price_val = l.get("price")
        score_val = l.get("score_after") or l.get("score_before")
        created = l.get("created_at") or ""
        time_display = created.replace("T", " ")[:16] if created else "Recent"

        title = f"{f_tier} ➔ {t_tier} Transition"
        badge = t_tier
        badge_color = "#38bdf8"
        if ev_type == "PROMOTED_HOT" or t_tier == "HOT":
            title = "🔥 Upgraded to HOT Priority Pool"
            badge = "HOT"
            badge_color = "#f87171"
        elif ev_type == "ADDED_WARM" or t_tier == "WARM":
            title = "⚡ Discovered in WARM Setup Pool"
            badge = "WARM"
            badge_color = "#fbbf24"
        elif ev_type == "DEMOTED_WARM":
            title = "📉 Re-routed from Hot to Warm Pool"
            badge = "WARM"
            badge_color = "#fbbf24"
        elif ev_type == "REMOVED_COLD" or t_tier == "COLD":
            title = "❄️ Retired to Cold Baseline Pool"
            badge = "COLD"
            badge_color = "#64748b"

        ev_counter = l.get("counter", 1) or 1
        ev_strat = l.get("strategy") or "Classic Technical"
        if ev_counter > 1:
            title = f"{title} (🔁 {ev_counter}x scan confirmations)"

        events.append({
            "timestamp": time_display,
            "raw_time": created,
            "event_type": ev_type,
            "title": title,
            "badge": badge,
            "badge_color": badge_color,
            "price": price_val,
            "score": score_val,
            "strategy": ev_strat,
            "counter": ev_counter,
            "reason": l.get("reason") or "Scored and re-evaluated by multi-factor scanner.",
            "catalyst_impact": l.get("catalyst_impact"),
        })

    # 4. If events are sparse, synthesize the natural lifecycle milestones
    if not events:
        scan_time_str = snap.get("scanned_at") or snap.get("created_at")
        if scan_time_str and len(str(scan_time_str)) >= 16:
            discovery_time_disp = str(scan_time_str).replace("T", " ")[:16]
            discovery_raw = str(scan_time_str)
        else:
            # Explicit EOD or point-in-time timestamp rather than fabricated morning 09:15
            discovery_time_disp = f"{sig_date} 15:30 EOD"
            discovery_raw = f"{sig_date}T15:30:00"

        # Milestone 1: Initial Discovery
        events.append({
            "timestamp": discovery_time_disp,
            "raw_time": discovery_raw,
            "event_type": "DISCOVERY",
            "title": f"⚡ Setup Discovered in {tier} Pool",
            "badge": tier,
            "badge_color": "#f87171" if tier == "HOT" else "#fbbf24",
            "price": sig_p,
            "score": comp_score,
            "reason": f"Discovered with composite conviction score {comp_score:.1f}/100. Price compressing ({snap.get('atr_pct', 2.5):.1f}% ATR) within {snap.get('pct_from_high', -2.0):+.1f}% of key resistance.",
            "catalyst_impact": snap.get("catalyst_impact"),
        })

    # Milestone 3: Breakout Trigger Breach (if breached/triggered)
    is_breached = bool(snap.get("breakout_happened")) or (cur_p and trig_p and cur_p >= trig_p) or outcome not in ("PENDING", "ACTIVE", "")
    if is_breached:
        breach_time = f"{sig_date} 14:45"
        events.append({
            "timestamp": breach_time,
            "raw_time": f"{sig_date}T14:45:00",
            "event_type": "BREAKOUT_TRIGGERED",
            "title": f"🚀 Breakout Trigger Breached (₹{trig_p:,.2f})",
            "badge": "TRIGGERED",
            "badge_color": "#38bdf8",
            "price": trig_p or cur_p,
            "score": comp_score,
            "reason": f"Resistance level ₹{trig_p:,.2f} crossed on exchange. Upside target calculated at ₹{target_p:,.2f} (+{((target_p-trig_p)/trig_p*100) if trig_p and target_p else 0:.1f}%) with stop loss at ₹{stop_p:,.2f}.",
            "catalyst_impact": None,
        })

    # Milestone 4: Latest Price Action / Outcome
    if outcome in ("TARGET_HIT", "STOP_HIT", "BREAKOUT_RETRACED", "TRIGGERED", "BREAKOUT_SUCCEEDED"):
        status_color = "#34d399" if outcome in ("TARGET_HIT", "TRIGGERED", "BREAKOUT_SUCCEEDED") else ("#fbbf24" if outcome == "BREAKOUT_RETRACED" else "#f87171")
        events.append({
            "timestamp": f"Live (Day {days_elapsed}/14)",
            "raw_time": "9999-99-99",
            "event_type": outcome,
            "title": f"{outcome_label}",
            "badge": outcome,
            "badge_color": status_color,
            "price": cur_p,
            "score": comp_score,
            "reason": snap.get("what_happened_summary") or f"Reached peak high ₹{post_high:,.2f} (+{max_gain:.1f}%), currently trading at ₹{cur_p:,.2f} ({ret_pct:+.1f}% live return).",
            "catalyst_impact": None,
        })

    # Sort events chronologically (oldest first)
    events.sort(key=lambda x: x.get("raw_time") or "")

    # Calculate active stepper step (0 to 4)
    active_step = 1 if tier == "WARM" else 2
    if is_breached:
        active_step = 3
    if outcome in ("TARGET_HIT", "STOP_HIT", "BREAKOUT_RETRACED"):
        active_step = 4

    return {
        "success": True,
        "ticker": sym,
        "company_name": company_name,
        "industry": industry,
        "tier": tier,
        "current_price": cur_p,
        "signal_price": sig_p,
        "breakout_trigger": trig_p,
        "target_price": target_p,
        "stop_loss": stop_p,
        "risk_reward_ratio": rr,
        "composite_score": comp_score,
        "resistance_score": snap.get("resistance_score", 0),
        "volume_score": snap.get("volume_score", 0),
        "compression_score": snap.get("compression_score", 0),
        "momentum_score": snap.get("momentum_score", 0),
        "fundamental_score": snap.get("fundamental_score", 0),
        "volume_ratio": snap.get("volume_ratio", 1.0),
        "atr_pct": snap.get("atr_pct", 2.5),
        "pct_from_high": snap.get("pct_from_high", 0.0),
        "realized_return_pct": ret_pct,
        "max_gain_pct": max_gain,
        "post_high": post_high,
        "outcome": outcome,
        "outcome_label": outcome_label,
        "days_elapsed": days_elapsed,
        "active_step": active_step,
        "events": events,
    }
