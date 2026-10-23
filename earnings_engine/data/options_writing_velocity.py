"""Institutional Option Writing Velocity & Rolling OI Snapshot Cache.

Tracks rolling multi-timeframe Open Interest (5m, 15m, 30m, 1h, 4h, and Today)
and classifies institutional writing flow (Put Writing vs Call Writing) with
actionable trading directives ('what is happening' and 'what to do').
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger("earnings_engine.data.options_writing_velocity")

# Rolling Open Interest & Writing Velocity Cache: symbol -> list of dict snapshots
# Each snapshot: {"timestamp": float, "call_oi": int, "put_oi": int, "strikes": dict}
_OI_SNAPSHOT_CACHE: dict[str, list[dict[str, Any]]] = {}
_MAX_OI_SNAPSHOTS = 1200  # Keep up to 5 hours of 15s snapshots


def _hydrate_cache_from_db(clean_sym: str) -> None:
    """Prepopulate rolling in-memory snapshot cache from persistent SQLite option_chain_intraday_snapshots."""
    if clean_sym in _OI_SNAPSHOT_CACHE and len(_OI_SNAPSHOT_CACHE[clean_sym]) >= 10:
        return

    try:
        from earnings_engine.data.db import get_db_connection
        conn = get_db_connection()
        now_ts = time.time()
        cutoff_ts = now_ts - 86400.0  # Last 24 hours of intraday snapshots
        cur = conn.execute(
            """
            SELECT timestamp, call_oi_total, put_oi_total, spot_price
            FROM option_chain_intraday_snapshots
            WHERE symbol = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT 1200
            """,
            (clean_sym, cutoff_ts),
        )
        rows = cur.fetchall()
        if not rows:
            return

        db_snapshots: list[dict[str, Any]] = []
        for r in rows:
            ts = float(r[0] if isinstance(r, (tuple, list)) else r["timestamp"])
            c_oi = int(r[1] if isinstance(r, (tuple, list)) else r["call_oi_total"])
            p_oi = int(r[2] if isinstance(r, (tuple, list)) else r["put_oi_total"])
            db_snapshots.append({
                "timestamp": ts,
                "call_oi": c_oi,
                "put_oi": p_oi,
                "strikes": {},
            })

        if clean_sym not in _OI_SNAPSHOT_CACHE or not _OI_SNAPSHOT_CACHE[clean_sym]:
            _OI_SNAPSHOT_CACHE[clean_sym] = db_snapshots
        else:
            existing = {s["timestamp"]: s for s in _OI_SNAPSHOT_CACHE[clean_sym]}
            for s in db_snapshots:
                if s["timestamp"] not in existing:
                    existing[s["timestamp"]] = s
            _OI_SNAPSHOT_CACHE[clean_sym] = sorted(existing.values(), key=lambda x: x["timestamp"])[-_MAX_OI_SNAPSHOTS:]
    except Exception as e:
        logger.debug("[OI-CACHE-HYDRATE] Failed to hydrate cache for %s: %s", clean_sym, e)


def _persist_intraday_snapshot_to_db(
    clean_sym: str,
    timestamp: float,
    call_oi: int,
    put_oi: int,
    spot_price: float | None = None,
    pcr_oi: float | None = None,
) -> None:
    """Save an intraday snapshot to option_chain_intraday_snapshots table with throttling."""
    try:
        from earnings_engine.data.db import get_db_connection
        conn = get_db_connection()
        now_iso = datetime.now().isoformat()
        recorded_at = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        # Check last snapshot timestamp to throttle writes to >= 10s intervals
        cur = conn.execute(
            "SELECT timestamp FROM option_chain_intraday_snapshots WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
            (clean_sym,),
        )
        row = cur.fetchone()
        if row:
            last_ts = float(row[0] if isinstance(row, (tuple, list)) else row["timestamp"])
            if (timestamp - last_ts) < 10.0:
                return

        conn.execute(
            """
            INSERT INTO option_chain_intraday_snapshots (
                symbol, timestamp, recorded_at, spot_price,
                call_oi_total, put_oi_total, pcr_oi, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_sym,
                timestamp,
                recorded_at,
                spot_price,
                int(call_oi),
                int(put_oi),
                pcr_oi,
                now_iso,
            ),
        )
        conn.commit()
    except Exception as e:
        logger.debug("[OI-INTRADAY-PERSIST] Failed to persist snapshot for %s: %s", clean_sym, e)


def track_oi_snapshot(
    symbol: str,
    total_call_oi: int,
    total_put_oi: int,
    strikes: list[dict[str, Any]],
    spot_price: float | None = None,
) -> None:
    """Store timestamped snapshot into the in-memory rolling ring buffer and persist to SQLite."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    now = time.time()

    # Hydrate if empty
    if clean_sym not in _OI_SNAPSHOT_CACHE or not _OI_SNAPSHOT_CACHE[clean_sym]:
        _hydrate_cache_from_db(clean_sym)

    strike_map = {}
    for s in strikes or []:
        stk = float(s.get("strike", 0.0))
        if stk > 0:
            strike_map[stk] = {
                "ce_oi": int(s.get("ce_oi") or 0),
                "pe_oi": int(s.get("pe_oi") or 0),
                "ce_chg": int(s.get("ce_change_oi") or 0),
                "pe_chg": int(s.get("pe_change_oi") or 0),
            }

    if clean_sym not in _OI_SNAPSHOT_CACHE:
        _OI_SNAPSHOT_CACHE[clean_sym] = []

    history = _OI_SNAPSHOT_CACHE[clean_sym]
    # Deduplicate if called within 5 seconds
    if history and (now - history[-1]["timestamp"]) < 5.0:
        history[-1] = {
            "timestamp": now,
            "call_oi": total_call_oi,
            "put_oi": total_put_oi,
            "strikes": strike_map,
        }
    else:
        history.append({
            "timestamp": now,
            "call_oi": total_call_oi,
            "put_oi": total_put_oi,
            "strikes": strike_map,
        })

    # Trim to max window
    if len(history) > _MAX_OI_SNAPSHOTS:
        _OI_SNAPSHOT_CACHE[clean_sym] = history[-_MAX_OI_SNAPSHOTS:]

    # Persist to persistent SQLite table
    pcr = round(total_put_oi / max(total_call_oi, 1), 2)
    _persist_intraday_snapshot_to_db(clean_sym, now, total_call_oi, total_put_oi, spot_price=spot_price, pcr_oi=pcr)


def _classify_writing_sentiment(call_delta: int, put_delta: int) -> tuple[str, str, str]:
    """Classify writing flow into institutional sentiment, status badge, and theme color."""
    tot_abs = abs(call_delta) + abs(put_delta)
    if tot_abs == 0:
        return "NEUTRAL", "BALANCED", "amber"

    # Put Writing Dominance (Bullish floor defense)
    if put_delta > 0 and (call_delta <= 0 or put_delta >= call_delta * 1.25):
        ratio = round(put_delta / max(call_delta, 1), 1) if call_delta > 0 else 2.5
        return "PUT WRITING", f"PUT WRITING ({ratio}x)", "emerald"

    # Call Writing Dominance (Bearish ceiling cap)
    if call_delta > 0 and (put_delta <= 0 or call_delta >= put_delta * 1.25):
        ratio = round(call_delta / max(put_delta, 1), 1) if put_delta > 0 else 2.5
        return "CALL WRITING", f"CALL WRITING ({ratio}x)", "rose"

    # Both unwinding (Short covering or long liquidation)
    if call_delta < 0 and put_delta < 0:
        if abs(call_delta) > abs(put_delta):
            return "SHORT COVERING", "CE UNWINDING", "sky"
        else:
            return "LONG UNWINDING", "PE UNWINDING", "rose"

    # Balanced two-way positioning
    return "BALANCED", "TWO-WAY FLOW", "amber"


def _fmt_indian_qty(num: int | float) -> str:
    """Format quantity into Indian Cr, L, or k."""
    n = abs(num)
    sign = "+" if num > 0 else ("-" if num < 0 else "")
    if n >= 10000000:
        return f"{sign}{n / 10000000:.2f} Cr"
    if n >= 100000:
        return f"{sign}{n / 100000:.2f} L"
    if n >= 1000:
        return f"{sign}{n / 1000:.1f} k"
    return f"{sign}{int(n)}"


def classify_strike_activity(
    price_change: float,
    oi_change: int,
    option_type: str = "CE",
) -> dict[str, Any]:
    """Classify strike activity into 4 categories and addition vs unwinding.

    Categories:
      - CALL_BUY: Long Buildup (Addition: ΔPrice >= 0, ΔOI > 0) OR Long Liquidation (Unwinding: ΔPrice < 0, ΔOI < 0)
      - CALL_SELL: Short Buildup/Writing (Addition: ΔPrice <= 0, ΔOI > 0) OR Short Covering (Unwinding: ΔPrice > 0, ΔOI < 0)
      - PUT_BUY: Long Buildup (Addition: ΔPrice >= 0, ΔOI > 0) OR Long Liquidation (Unwinding: ΔPrice < 0, ΔOI < 0)
      - PUT_SELL: Short Buildup/Writing (Addition: ΔPrice <= 0, ΔOI > 0) OR Short Covering (Unwinding: ΔPrice > 0, ΔOI < 0)
    """
    is_addition = oi_change > 0
    is_unwinding = oi_change < 0
    abs_oi = abs(oi_change)

    if option_type == "CE":
        if is_addition:
            category = "CALL_BUY" if price_change >= 0 else "CALL_SELL"
            flow_type = "Long Buildup" if price_change >= 0 else "Short Buildup (Writing)"
        elif is_unwinding:
            category = "CALL_SELL" if price_change >= 0 else "CALL_BUY"
            flow_type = "Short Covering" if price_change >= 0 else "Long Liquidation"
        else:
            category = "NEUTRAL"
            flow_type = "Neutral"
    else:
        if is_addition:
            category = "PUT_BUY" if price_change >= 0 else "PUT_SELL"
            flow_type = "Long Buildup" if price_change >= 0 else "Short Buildup (Writing)"
        elif is_unwinding:
            category = "PUT_SELL" if price_change >= 0 else "PUT_BUY"
            flow_type = "Short Covering" if price_change >= 0 else "Long Liquidation"
        else:
            category = "NEUTRAL"
            flow_type = "Neutral"

    return {
        "category": category,
        "flow_type": flow_type,
        "is_addition": is_addition,
        "is_unwinding": is_unwinding,
        "contracts": abs_oi,
    }


def derive_4category_flow(strikes: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate contracts into Call Buy, Call Sell, Put Buy, Put Sell (Added vs Unwound)."""
    call_buy_added = call_buy_unwound = 0
    call_sell_added = call_sell_unwound = 0
    put_buy_added = put_buy_unwound = 0
    put_sell_added = put_sell_unwound = 0

    for s in strikes or []:
        ce_chg = int(s.get("ce_change_oi") or 0)
        pe_chg = int(s.get("pe_change_oi") or 0)
        ce_p_chg = float(s.get("ce_pchange_oi") or 0.0)
        pe_p_chg = float(s.get("pe_pchange_oi") or 0.0)

        ce_res = classify_strike_activity(ce_p_chg, ce_chg, option_type="CE")
        if ce_res["category"] == "CALL_BUY":
            if ce_res["is_addition"]:
                call_buy_added += ce_res["contracts"]
            else:
                call_buy_unwound += ce_res["contracts"]
        elif ce_res["category"] == "CALL_SELL":
            if ce_res["is_addition"]:
                call_sell_added += ce_res["contracts"]
            else:
                call_sell_unwound += ce_res["contracts"]

        pe_res = classify_strike_activity(pe_p_chg, pe_chg, option_type="PE")
        if pe_res["category"] == "PUT_BUY":
            if pe_res["is_addition"]:
                put_buy_added += pe_res["contracts"]
            else:
                put_buy_unwound += pe_res["contracts"]
        elif pe_res["category"] == "PUT_SELL":
            if pe_res["is_addition"]:
                put_sell_added += pe_res["contracts"]
            else:
                put_sell_unwound += pe_res["contracts"]

    tot_flow = (
        call_buy_added + call_buy_unwound +
        call_sell_added + call_sell_unwound +
        put_buy_added + put_buy_unwound +
        put_sell_added + put_sell_unwound
    )
    safe_tot = max(tot_flow, 1)

    cb_tot = call_buy_added + call_buy_unwound
    cs_tot = call_sell_added + call_sell_unwound
    pb_tot = put_buy_added + put_buy_unwound
    ps_tot = put_sell_added + put_sell_unwound

    return {
        "call_buy": {
            "name": "Call Buy",
            "added": call_buy_added,
            "unwound": call_buy_unwound,
            "total": cb_tot,
            "pct": round((cb_tot / safe_tot) * 100, 1),
            "added_pct": round((call_buy_added / max(cb_tot, 1)) * 100, 1) if cb_tot > 0 else 0.0,
            "unwound_pct": round((call_buy_unwound / max(cb_tot, 1)) * 100, 1) if cb_tot > 0 else 0.0,
            "added_fmt": _fmt_indian_qty(call_buy_added).lstrip("+"),
            "unwound_fmt": _fmt_indian_qty(call_buy_unwound).lstrip("+"),
            "total_fmt": _fmt_indian_qty(cb_tot).lstrip("+"),
            "bias": "BULLISH",
            "theme": "emerald",
            "desc": "Long Buildup (+Added) vs Long Liquidation (-Unwound)",
        },
        "call_sell": {
            "name": "Call Sell",
            "added": call_sell_added,
            "unwound": call_sell_unwound,
            "total": cs_tot,
            "pct": round((cs_tot / safe_tot) * 100, 1),
            "added_pct": round((call_sell_added / max(cs_tot, 1)) * 100, 1) if cs_tot > 0 else 0.0,
            "unwound_pct": round((call_sell_unwound / max(cs_tot, 1)) * 100, 1) if cs_tot > 0 else 0.0,
            "added_fmt": _fmt_indian_qty(call_sell_added).lstrip("+"),
            "unwound_fmt": _fmt_indian_qty(call_sell_unwound).lstrip("+"),
            "total_fmt": _fmt_indian_qty(cs_tot).lstrip("+"),
            "bias": "BEARISH",
            "theme": "rose",
            "desc": "Short Buildup/Writing (+Added) vs Short Covering (-Unwound)",
        },
        "put_buy": {
            "name": "Put Buy",
            "added": put_buy_added,
            "unwound": put_buy_unwound,
            "total": pb_tot,
            "pct": round((pb_tot / safe_tot) * 100, 1),
            "added_pct": round((put_buy_added / max(pb_tot, 1)) * 100, 1) if pb_tot > 0 else 0.0,
            "unwound_pct": round((put_buy_unwound / max(pb_tot, 1)) * 100, 1) if pb_tot > 0 else 0.0,
            "added_fmt": _fmt_indian_qty(put_buy_added).lstrip("+"),
            "unwound_fmt": _fmt_indian_qty(put_buy_unwound).lstrip("+"),
            "total_fmt": _fmt_indian_qty(pb_tot).lstrip("+"),
            "bias": "BEARISH",
            "theme": "rose",
            "desc": "Put Buying (+Added) vs Put Liquidation (-Unwound)",
        },
        "put_sell": {
            "name": "Put Sell",
            "added": put_sell_added,
            "unwound": put_sell_unwound,
            "total": ps_tot,
            "pct": round((ps_tot / safe_tot) * 100, 1),
            "added_pct": round((put_sell_added / max(ps_tot, 1)) * 100, 1) if ps_tot > 0 else 0.0,
            "unwound_pct": round((put_sell_unwound / max(ps_tot, 1)) * 100, 1) if ps_tot > 0 else 0.0,
            "added_fmt": _fmt_indian_qty(put_sell_added).lstrip("+"),
            "unwound_fmt": _fmt_indian_qty(put_sell_unwound).lstrip("+"),
            "total_fmt": _fmt_indian_qty(ps_tot).lstrip("+"),
            "bias": "BULLISH",
            "theme": "emerald",
            "desc": "Put Underwriting/Floor (+Added) vs Put Short Covering (-Unwound)",
        },
        "total_contracts": tot_flow,
        "total_contracts_fmt": _fmt_indian_qty(tot_flow).lstrip("+"),
    }


def _derive_timeframe_guidance(
    tf_key: str,
    sentiment: str,
    call_delta: int,
    put_delta: int,
    pcr_oi: float = 1.0,
) -> tuple[str, str, str]:
    """Derive bias, institutional diagnosis ('what is happening'), and actionable trading directive ('what should I do').

    Returns:
        (bias, what_is_happening, what_to_do)
        where bias is 'BULLISH' | 'BEARISH' | 'NEUTRAL'
    """
    # 1. Determine Bias
    if sentiment in ("BALANCED", "NEUTRAL"):
        bias = "NEUTRAL"
    elif sentiment == "PUT WRITING":
        bias = "BULLISH"
    elif sentiment == "CALL WRITING":
        bias = "BEARISH"
    elif sentiment == "SHORT COVERING":
        bias = "BULLISH"
    elif sentiment == "LONG UNWINDING":
        bias = "BEARISH"
    elif put_delta >= call_delta * 1.25 and put_delta > 0:
        bias = "BULLISH"
    elif call_delta >= put_delta * 1.25 and call_delta > 0:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # 2. Timeframe-specific diagnoses and trade playbooks
    # Microstructure burst: 5m
    if tf_key == "5m":
        if sentiment == "SHORT COVERING":
            happening = "Microstructure Short Squeeze: Call writers panic-covering positions on rapid upward momentum burst."
            todo = "RIDE MOMENTUM: Scalp long momentum breakouts above immediate strike; trail stops very tightly."
        elif sentiment == "LONG UNWINDING":
            happening = "Microstructure PE Unwinding: Put sellers liquidating downside contracts; temporary slip hazard."
            todo = "TIGHTEN LONG STOPS: Avoid aggressive dip-buying; wait for fresh put writing to materialize."
        elif bias == "BULLISH":
            happening = "Microstructure Put Writing Surge: Smart money rapidly underwriting immediate floor strikes; aggressive short put bids."
            todo = "BUY DIPS: Scalp longs on minor pullbacks toward VWAP or nearest strike support; avoid chasing tops."
        elif bias == "BEARISH":
            happening = "Microstructure Call Writing Block: Aggressive ask-side liquidity building overhead; quick capping of upside."
            todo = "FADE RALLIES: Scalp short or lock profits on spikes into resistance; do not chase intraday highs."
        else:
            happening = "Scalper Equilibrium: Balanced two-way order flow; tight range-bound scalping between immediate strikes."
            todo = "SCALP BOUNDARIES: Trade only at extreme edges; avoid entering trades in the middle of the range."

    # Primary intraday velocity: 15m
    elif tf_key == "15m":
        if sentiment == "SHORT COVERING":
            happening = "Intraday Short Squeeze: Sustained CE unwinding forcing trapped bears to buy back contracts."
            todo = "FAVOR UPSIDE: Ride the squeeze toward upper Call Wall; watch for volume exhaustion before exiting."
        elif sentiment == "LONG UNWINDING":
            happening = "Intraday Support Erosion: PE unwinding indicates waning floor confidence and tactical risk-off."
            todo = "DEFEND LONGS: Tighten stop-losses; avoid adding longs until put sellers re-enter."
        elif bias == "BULLISH":
            happening = "Intraday Put Defense: Institutions aggressively underwriting downside puts, reinforcing session demand zone."
            todo = "LONG BIAS: Enter long pullbacks near Put Wall; deploy Bull Put Spreads or ATM Calls with defined stops."
        elif bias == "BEARISH":
            happening = "Intraday Ceiling Build: Heavy institutional call writing pinning price below key resistance strikes."
            todo = "SHORT BIAS: Sell rallies into Call Wall resistance; deploy Bear Call Spreads or ATM Put options."
        else:
            happening = "Two-Way Consolidation: Neither bulls nor bears possess decisive writing velocity; price coiling for breakout."
            todo = "WAIT & OBSERVE: Look for volume surge or wait for an OI expansion trigger before taking directional risk."

    # Session continuation & momentum: 30m
    elif tf_key == "30m":
        if sentiment == "SHORT COVERING":
            happening = "Structural Short Covering: Major overhead calls being liquidated, clearing the way for higher price discovery."
            todo = "BUY BREAKOUTS: Enter continuation trades on breaks above intraday highs; trail stop under prior 30m candle."
        elif sentiment == "LONG UNWINDING":
            happening = "Floor Abandonment: Key put strikes losing open interest, leaving the market vulnerable to sharp downward dips."
            todo = "REDUCE EXPOSURE: Hedge existing long deltas; look for tactical short opportunities on failed bounces."
        elif bias == "BULLISH":
            happening = "Sustained Put Writing Momentum: Strong accumulation of short put inventory, establishing durable floor."
            todo = "FAVOR LONGS: Hold long delta; trail stop-loss under 30m session low; target Call Wall resistance."
        elif bias == "BEARISH":
            happening = "Sustained Overhead Supply: Call OI expanding across upper strikes, locking the market below resistance."
            todo = "DEFEND / SHORT: Protect existing longs with put hedges; initiate tactical short plays on bounces."
        else:
            happening = "Range-Bound Equilibrium: Symmetric call and put writing pinning spot price between nearest walls."
            todo = "RANGE STRATEGIES: Deploy non-directional strategies (Iron Condor / Short Straddle) to harvest theta."

    # Institutional block positioning: 1h
    elif tf_key == "1h":
        if sentiment == "SHORT COVERING":
            happening = "Higher-Timeframe Short Unwinding: Trapped call sellers capitulating; significant delta rebalancing to upside."
            todo = "SWING LONG: Hold long positions with trailing stop; institutional sellers are abandoning resistance."
        elif sentiment == "LONG UNWINDING":
            happening = "Institutional Put De-risking: Sustained unwinding of downside buffers; caution warranted for bulls."
            todo = "RAISE CASH: Trim long equity/options exposure; institutional put writers are pulling their bids."
        elif bias == "BULLISH":
            happening = "Institutional Floor Solidification: Major liquidity providers establishing high-conviction structural floor."
            todo = "TREND ACCUMULATION: Build swing long exposure via Bull Call Ladders or Put Credit Spreads."
        elif bias == "BEARISH":
            happening = "Institutional Distribution Ceiling: Large-scale call sales pinning market under overhead Gamma Flip."
            todo = "REDUCE LONG RISK: Exit weak long positions; initiate Bear Put Spreads targeting lower Put Wall."
        else:
            happening = "Structural Congestion: Multi-strike straddle/strangle writing creating non-directional range containment."
            todo = "WAIT FOR EXPANSION: Range-bound chop; wait for clear OI volume breakout before directional entry."

    # Multi-session institutional swing horizon: 4h
    elif tf_key == "4h":
        if sentiment == "SHORT COVERING":
            happening = "Multi-Hour Bear Capitulation: Broad-based short call liquidation across key resistance strikes."
            todo = "HOLD SWING LONGS: Major overhead supply cleared; trend continuation favored on multi-session horizon."
        elif sentiment == "LONG UNWINDING":
            happening = "Macro Support Liquidation: Multi-hour erosion of put contracts pointing toward prolonged drift."
            todo = "AVOID AGGRESSIVE LONGS: Lack of institutional put absorption indicates vulnerable downside trajectory."
        elif bias == "BULLISH":
            happening = "Macro Swing Bullish Cushion: Large institutional participants heavily short puts, providing multi-session trend ballast."
            todo = "HOLD BULLISH SWINGS: Macro floor intact; buy dips with wider stops; avoid shorting rallies."
        elif bias == "BEARISH":
            happening = "Macro Resistance Fortification: Strong swing-level call writing establishes durable multi-hour resistance wall."
            todo = "SWING SHORT LEAN: Macro resistance holding firm; sell call spreads or hold delta-hedged shorts."
        else:
            happening = "Macro Indecision / Theta Regime: Balanced positioning across horizons awaiting external catalyst."
            todo = "HARVEST THETA: Sell wide out-of-the-money strangle/straddles; let time decay work in your favor."

    # Macro Weekly Horizon: 1w (5 Trading Days)
    elif tf_key == "1w":
        if sentiment == "SHORT COVERING":
            happening = "Weekly Short Squeeze: Persistent call liquidation over the past 5 sessions; institutional bears being systematically squeezed out."
            todo = "RIDE WEEKLY SWING: Trailing stops below 5-day VWAP; upside momentum dominant into weekly expiry."
        elif sentiment == "LONG UNWINDING":
            happening = "Weekly Support Capitulation: Sustained 5-day unwinding of downside put buffers; institutional floor being dismantled."
            todo = "EXIT WEAK SWINGS: Avoid bottom-fishing until fresh weekly put bases form; reduce net long delta."
        elif bias == "BULLISH":
            happening = "Structural Weekly Put Writing: Institutions aggressively building a multi-day floor across key strikes."
            todo = "BUY WEEKLY DIP BASES: Initiate swing longs on pullbacks to key weekly support; target upper Call Wall."
        elif bias == "BEARISH":
            happening = "Heavy Weekly Call Accumulation: Institutional sellers maintaining an unyielding ceiling over the past 5 sessions."
            todo = "SELL CEILING RESISTANCE: Deploy Bear Call Spreads or sell rallies near weekly Call Wall; hedge long portfolios."
        else:
            happening = "Weekly Range Containment: Call and put writing balanced across the weekly cycle, locking spot inside expiry channel."
            todo = "HARVEST WEEKLY THETA: Sell weekly Iron Condors or credit spreads near outer strikes; capture rapid time decay."

    # Macro Monthly Horizon: 1mo (21 Trading Days)
    elif tf_key == "1mo":
        if sentiment == "SHORT COVERING":
            happening = "Monthly Cycle Short Unwinding: Structural short covering across monthly series; institutional regime shift toward bullish expansion."
            todo = "POSITIONAL LONG: Ride monthly trend continuation; trail stop loss under 20-day moving average."
        elif sentiment == "LONG UNWINDING":
            happening = "Macro Put Liquidation: Monthly put open interest decaying rapidly without replacement; structural risk-off across sectors."
            todo = "TACTICAL SHORT / CASH: Maintain high cash or purchase protective monthly index puts; hedge equity beta."
        elif bias == "BULLISH":
            happening = "Institutional Monthly Accumulation: Multi-week put writing dominance establishing high-conviction macro floor."
            todo = "ACCUMULATE POSITIONS: Buy dip pullbacks in leading sector equities; deploy multi-week Bull Put Spreads."
        elif bias == "BEARISH":
            happening = "Macro Monthly Supply Overhang: Large institutional call writing block capping broad market upside for the series."
            todo = "DEFENSIVE CYCLE PLAY: Cap portfolio delta; deploy monthly Bear Spreads or delta-hedged collar strategies."
        else:
            happening = "Monthly Expiry Channel: Open interest distributed symmetrically across monthly strikes, defining wide trading boundaries."
            todo = "MONTHLY STRANGLE / CONDOR: Deploy wide monthly delta-neutral structures to capitalize on volatility crush."

    # Macro Quarterly Horizon: 3mo (63 Trading Days)
    elif tf_key == "3mo":
        if sentiment == "SHORT COVERING":
            happening = "Quarterly Capitulation Squeeze: Large-scale unwinding of long-term call hedges indicating strong institutional risk-on regime."
            todo = "LONG-TERM BULLISH TREND: Build core long positions; let winners run across quarterly earnings cycles."
        elif sentiment == "LONG UNWINDING":
            happening = "Long-Term Hedge Liquidation: Multi-month put decay reflecting exhaustion of structural institutional floor."
            todo = "PORTFOLIO RISK CONTROL: Reduce leveraged exposures; implement systemic downside risk buffers."
        elif bias == "BULLISH":
            happening = "Strategic Institutional Put Inflow: Multi-month put writing dominance providing strong underlying foundation for secular trend."
            todo = "STRATEGIC ACCUMULATION: Systematically buy structural dips; hold quarterly index bull spreads."
        elif bias == "BEARISH":
            happening = "Strategic Institutional Distribution: Heavy quarterly call writing indicating prolonged institutional hedging and upside capping."
            todo = "LONG-TERM HEDGE: Implement portfolio-level collars; avoid buying into multi-week rallies without volume confirmation."
        else:
            happening = "Long-Term Structural Congestion: Symmetrical quarterly institutional positioning preserving broad multi-month range boundaries."
            todo = "RANGE REBALANCING: Buy near lower quarterly boundary, trim at upper quarterly boundary; maintain disciplined risk limits."

    # Full session cumulative: today
    else:
        if sentiment == "SHORT COVERING":
            happening = "Session-Wide Short Squeeze: Trapped call writers steadily abandoning positions, propelling bullish run."
            todo = "TREND FOLLOWING: Ride the strong intraday trend; let profits run with trailing stop at VWAP."
        elif sentiment == "LONG UNWINDING":
            happening = "Session Support Drainage: Institutional put sellers stepping away, removing downside floor cushion."
            todo = "DEFENSIVE POSTURE: Move to cash or hedge; session support has failed to attract fresh institutional writing."
        elif bias == "BULLISH":
            happening = "Full-Day Put Accumulation: Session-wide put delta dominance creating an expanding institutional safety buffer."
            todo = "BUY WITH CONFIDENCE: Favor long strategies; buy at VWAP/support floors; trail stops systematically."
        elif bias == "BEARISH":
            happening = "Full-Day Supply Dominance: Sustained call additions suppressing spot rallies throughout the session."
            todo = "DEFENSIVE / SHORT: Institutional ceiling active; sell rallies, tighten trailing stops on longs."
        else:
            happening = "Neutral Session Balance: Net writing delta near parity; market operating in theta-decay equilibrium."
            todo = "DELTA-NEUTRAL: Market in consolidation balance; scalp channel extremes or collect premium."

    return bias, happening, todo


def derive_multi_timeframe_oi(
    symbol: str,
    current_call_oi: int,
    current_put_oi: int,
    strikes: list[dict[str, Any]],
    spot_price: float | None = None,
    current_call_vol: int = 0,
    current_put_vol: int = 0,
) -> dict[str, Any]:
    """Compute multi-timeframe Call vs Put Open Interest metrics across 5m, 15m, 30m, 1h, 4h, and Today."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    now = time.time()
    now_time = datetime.now().strftime("%H:%M")

    # Hydrate cache from SQLite if needed
    _hydrate_cache_from_db(clean_sym)

    # Track current snapshot and persist to SQLite
    track_oi_snapshot(clean_sym, current_call_oi, current_put_oi, strikes, spot_price=spot_price)
    history = _OI_SNAPSHOT_CACHE.get(clean_sym, [])

    # Current PCR
    curr_pcr = round(current_put_oi / max(current_call_oi, 1), 2)

    # Volume and Gross Added contracts
    tot_vol = max(current_call_vol + current_put_vol, 0)
    today_ce_chg = sum(int(s.get("ce_change_oi") or 0) for s in strikes)
    today_pe_chg = sum(int(s.get("pe_change_oi") or 0) for s in strikes)
    today_total_added = abs(today_ce_chg) + abs(today_pe_chg)

    # 1. Total Positions (Two Bars: Calls vs Puts)
    tot_oi = max(current_call_oi + current_put_oi, 1)
    tot_call_pct = round((current_call_oi / tot_oi) * 100, 1)
    tot_put_pct = round((current_put_oi / tot_oi) * 100, 1)

    total_positions = {
        "call_oi": current_call_oi,
        "put_oi": current_put_oi,
        "call_pct": tot_call_pct,
        "put_pct": tot_put_pct,
        "call_oi_formatted": _fmt_indian_qty(current_call_oi).lstrip("+"),
        "put_oi_formatted": _fmt_indian_qty(current_put_oi).lstrip("+"),
        "call_vol": current_call_vol,
        "put_vol": current_put_vol,
        "total_vol": tot_vol,
        "total_traded": tot_vol,
        "total_added": today_total_added,
        "call_vol_fmt": _fmt_indian_qty(current_call_vol).lstrip("+"),
        "put_vol_fmt": _fmt_indian_qty(current_put_vol).lstrip("+"),
        "total_traded_fmt": _fmt_indian_qty(tot_vol).lstrip("+"),
        "total_added_fmt": _fmt_indian_qty(today_total_added).lstrip("+"),
    }

    # 2. Today (Full Session) Intraday Aggregation
    call_base_today = max(current_call_oi - today_ce_chg, 1)
    put_base_today = max(current_put_oi - today_pe_chg, 1)
    call_today_pct_chg = round((today_ce_chg / call_base_today) * 100, 1)
    put_today_pct_chg = round((today_pe_chg / put_base_today) * 100, 1)

    today_sent, today_badge, today_theme = _classify_writing_sentiment(today_ce_chg, today_pe_chg)
    today_bias, today_happening, today_todo = _derive_timeframe_guidance(
        "today", today_sent, today_ce_chg, today_pe_chg, curr_pcr
    )

    today_metric = {
        "key": "today",
        "timeframe": "Today",
        "scope": "Full Session",
        "call_oi": current_call_oi,
        "put_oi": current_put_oi,
        "call_pct": tot_call_pct,
        "put_pct": tot_put_pct,
        "call_chg": today_ce_chg,
        "put_chg": today_pe_chg,
        "net_delta": today_pe_chg - today_ce_chg,
        "call_traded": current_call_vol,
        "put_traded": current_put_vol,
        "total_traded": tot_vol,
        "call_added": abs(today_ce_chg),
        "put_added": abs(today_pe_chg),
        "total_added": today_total_added,
        "call_pct_chg": call_today_pct_chg,
        "put_pct_chg": put_today_pct_chg,
        "call_chg_fmt": _fmt_indian_qty(today_ce_chg),
        "put_chg_fmt": _fmt_indian_qty(today_pe_chg),
        "net_delta_fmt": _fmt_indian_qty(today_pe_chg - today_ce_chg),
        "total_traded_fmt": _fmt_indian_qty(tot_vol).lstrip("+"),
        "total_added_fmt": _fmt_indian_qty(today_total_added).lstrip("+"),
        "sentiment": today_sent,
        "badge": today_badge,
        "theme": today_theme,
        "bias": today_bias,
        "what_is_happening": today_happening,
        "what_to_do": today_todo,
        "is_extended": False,
    }

    # Helper to calculate delta from target seconds ago and extract base snapshot
    def _get_rolling_snapshot(target_sec_ago: float) -> tuple[int, int, dict[str, Any] | None]:
        duration_fraction = min(target_sec_ago / 22500.0, 1.0)
        c_session_proj = int(today_ce_chg * duration_fraction)
        p_session_proj = int(today_pe_chg * duration_fraction)

        if len(history) < 2:
            return c_session_proj, p_session_proj, None

        target_time = now - target_sec_ago
        base_snap = history[0]
        for snap in history:
            if snap["timestamp"] <= target_time:
                base_snap = snap
            else:
                break

        curr_snap = history[-1]
        c_delta = curr_snap["call_oi"] - base_snap["call_oi"]
        p_delta = curr_snap["put_oi"] - base_snap["put_oi"]

        total_cache_elapsed = curr_snap["timestamp"] - history[0]["timestamp"]

        # If cache history does not reach back to target_sec_ago (base_snap was clamped to history[0])
        if total_cache_elapsed < (target_sec_ago * 0.85):
            if total_cache_elapsed >= 30.0 and (c_delta != 0 or p_delta != 0):
                # Rate per second from observed history, scaled strictly to the target horizon
                rate_c = c_delta / max(total_cache_elapsed, 1.0)
                rate_p = p_delta / max(total_cache_elapsed, 1.0)
                c_rate_proj = int(rate_c * target_sec_ago)
                p_rate_proj = int(rate_p * target_sec_ago)

                # Cap rate projection so extreme early micro-swings don't exceed session envelope
                max_c = max(abs(today_ce_chg), abs(c_session_proj) * 2)
                max_p = max(abs(today_pe_chg), abs(p_session_proj) * 2)

                c_clamped = int(max(min(c_rate_proj, max_c), -max_c))
                p_clamped = int(max(min(p_rate_proj, max_p), -max_p))

                # Blend 60% observed rate projection with 40% session progress
                c_delta = int(0.6 * c_clamped + 0.4 * c_session_proj)
                p_delta = int(0.6 * p_clamped + 0.4 * p_session_proj)
            else:
                # Early cold cache: strictly use session progress based on timeframe duration
                c_delta = c_session_proj
                p_delta = p_session_proj

        return c_delta, p_delta, base_snap

    # Builder for individual timeframe metrics
    def _build_tf_metric(tf_key: str, tf_label: str, tf_scope: str, seconds: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
        c_chg, p_chg, snap = _get_rolling_snapshot(seconds)
        abs_tot = max(abs(c_chg) + abs(p_chg), 1)
        sent, badge, theme = _classify_writing_sentiment(c_chg, p_chg)

        call_base = max(current_call_oi - c_chg, 1)
        put_base = max(current_put_oi - p_chg, 1)
        c_pct_chg = round((c_chg / call_base) * 100, 1)
        p_pct_chg = round((p_chg / put_base) * 100, 1)

        duration_fraction = min(seconds / 22500.0, 1.0)
        c_vol = int(current_call_vol * duration_fraction)
        p_vol = int(current_put_vol * duration_fraction)
        tf_traded = c_vol + p_vol
        tf_added = abs(c_chg) + abs(p_chg)

        bias, happening, todo = _derive_timeframe_guidance(tf_key, sent, c_chg, p_chg, curr_pcr)

        metric = {
            "key": tf_key,
            "timeframe": tf_label,
            "scope": tf_scope,
            "call_chg": c_chg,
            "put_chg": p_chg,
            "net_delta": p_chg - c_chg,
            "call_traded": c_vol,
            "put_traded": p_vol,
            "total_traded": tf_traded,
            "call_added": abs(c_chg),
            "put_added": abs(p_chg),
            "total_added": tf_added,
            "call_pct_chg": c_pct_chg,
            "put_pct_chg": p_pct_chg,
            "call_pct": round((abs(c_chg) / abs_tot) * 100, 1) if abs_tot > 0 else 50.0,
            "put_pct": round((abs(p_chg) / abs_tot) * 100, 1) if abs_tot > 0 else 50.0,
            "call_chg_fmt": _fmt_indian_qty(c_chg),
            "put_chg_fmt": _fmt_indian_qty(p_chg),
            "net_delta_fmt": _fmt_indian_qty(p_chg - c_chg),
            "total_traded_fmt": _fmt_indian_qty(tf_traded).lstrip("+"),
            "total_added_fmt": _fmt_indian_qty(tf_added).lstrip("+"),
            "sentiment": sent,
            "badge": badge,
            "theme": theme,
            "bias": bias,
            "what_is_happening": happening,
            "what_to_do": todo,
            "is_extended": False,
        }
        return metric, snap

    # 3. 5-Minute Burst (300 seconds)
    tf_5m, snap_5m = _build_tf_metric("5m", "5 min", "Scalp Burst", 300.0)

    # 4. 15-Minute Velocity (900 seconds)
    tf_15m, snap_15m = _build_tf_metric("15m", "15 min", "Intraday Velocity", 900.0)

    # 5. 30-Minute Structure (1800 seconds)
    tf_30m, snap_30m = _build_tf_metric("30m", "30 min", "Session Trend", 1800.0)

    # 6. 1-Hour Positioning Block (3600 seconds)
    tf_1h, snap_1h = _build_tf_metric("1h", "1 hour", "Institutional Block", 3600.0)

    # 7. 4-Hour Swing Horizon (14400 seconds)
    tf_4h, snap_4h = _build_tf_metric("4h", "4 hours", "Swing Horizon", 14400.0)

    # 8. Macro Horizons: Weekly (5D), Monthly (21D), Quarterly (63D) from DB snapshots
    def _get_historical_snapshots() -> list[dict[str, Any]]:
        try:
            from earnings_engine.data.option_chain import get_option_chain_history
            return get_option_chain_history(clean_sym, limit=70)
        except Exception:
            return []

    history_snapshots = _get_historical_snapshots()

    def _build_macro_tf_metric(
        tf_key: str,
        tf_label: str,
        tf_scope: str,
        target_days: int,
    ) -> dict[str, Any]:
        c_chg = 0
        p_chg = 0
        scope_label = tf_scope

        if len(history_snapshots) > 1:
            idx = min(target_days, len(history_snapshots) - 1)
            base_row = history_snapshots[idx]
            base_call = int(base_row.get("call_oi_total") or 0)
            base_put = int(base_row.get("put_oi_total") or 0)
            if idx < target_days:
                scope_label = f"{tf_scope} ({idx}D historical)"
            if base_call > 0 and base_put > 0:
                c_chg = current_call_oi - base_call
                p_chg = current_put_oi - base_put
            else:
                mult = 3.5 if tf_key == "1w" else (10.0 if tf_key == "1mo" else 25.0)
                c_chg = int(today_ce_chg * mult)
                p_chg = int(today_pe_chg * mult)
        else:
            mult = 3.5 if tf_key == "1w" else (10.0 if tf_key == "1mo" else 25.0)
            c_chg = int(today_ce_chg * mult)
            p_chg = int(today_pe_chg * mult)

        abs_tot = max(abs(c_chg) + abs(p_chg), 1)
        sent, badge, theme = _classify_writing_sentiment(c_chg, p_chg)

        call_base = max(current_call_oi - c_chg, 1)
        put_base = max(current_put_oi - p_chg, 1)
        c_pct_chg = round((c_chg / call_base) * 100, 1)
        p_pct_chg = round((p_chg / put_base) * 100, 1)

        macro_added = abs(c_chg) + abs(p_chg)
        macro_traded = int(tot_vol * target_days)
        macro_c_traded = int(current_call_vol * target_days)
        macro_p_traded = int(current_put_vol * target_days)

        bias, happening, todo = _derive_timeframe_guidance(tf_key, sent, c_chg, p_chg, curr_pcr)

        return {
            "key": tf_key,
            "timeframe": tf_label,
            "scope": scope_label,
            "call_chg": c_chg,
            "put_chg": p_chg,
            "net_delta": p_chg - c_chg,
            "call_traded": macro_c_traded,
            "put_traded": macro_p_traded,
            "total_traded": macro_traded,
            "call_added": abs(c_chg),
            "put_added": abs(p_chg),
            "total_added": macro_added,
            "call_pct_chg": c_pct_chg,
            "put_pct_chg": p_pct_chg,
            "call_pct": round((abs(c_chg) / abs_tot) * 100, 1) if abs_tot > 0 else 50.0,
            "put_pct": round((abs(p_chg) / abs_tot) * 100, 1) if abs_tot > 0 else 50.0,
            "call_chg_fmt": _fmt_indian_qty(c_chg),
            "put_chg_fmt": _fmt_indian_qty(p_chg),
            "net_delta_fmt": _fmt_indian_qty(p_chg - c_chg),
            "total_traded_fmt": _fmt_indian_qty(macro_traded).lstrip("+"),
            "total_added_fmt": _fmt_indian_qty(macro_added).lstrip("+"),
            "sentiment": sent,
            "badge": badge,
            "theme": theme,
            "bias": bias,
            "what_is_happening": happening,
            "what_to_do": todo,
            "is_extended": True,
        }

    tf_1w = _build_macro_tf_metric("1w", "Weekly (5D)", "Swing Horizon", 5)
    tf_1mo = _build_macro_tf_metric("1mo", "Monthly (21D)", "Macro Cycle", 21)
    tf_3mo = _build_macro_tf_metric("3mo", "Quarterly (63D)", "Institutional Horizon", 63)

    # 9. Enrich strikes with strike-level 15m change
    base_strikes_15m = snap_15m.get("strikes", {}) if snap_15m else {}
    for s in strikes:
        stk = float(s.get("strike", 0.0))
        if stk in base_strikes_15m:
            s["ce_change_15m"] = int(s.get("ce_oi", 0) or 0) - int(base_strikes_15m[stk].get("ce_oi", 0) or 0)
            s["pe_change_15m"] = int(s.get("pe_oi", 0) or 0) - int(base_strikes_15m[stk].get("pe_oi", 0) or 0)
        else:
            # Fallback: ~4% (15m/375m) of session change
            s["ce_change_15m"] = int((int(s.get("ce_change_oi", 0) or 0)) * (15.0 / 375.0))
            s["pe_change_15m"] = int((int(s.get("pe_change_oi", 0) or 0)) * (15.0 / 375.0))

    # 10. PCR (OI) & 15m Delta
    if snap_15m and snap_15m.get("call_oi", 0) > 0:
        base_pcr = round(snap_15m["put_oi"] / max(snap_15m["call_oi"], 1), 2)
        pcr_15m_delta = round(curr_pcr - base_pcr, 2)
    else:
        pcr_15m_delta = 0.0

    # 11. Multi-Timeframe Tabular Matrix (Standard Intraday + Macro Horizons)
    core_timeframes = [
        tf_5m,
        tf_15m,
        tf_30m,
        tf_1h,
        tf_4h,
        today_metric,
    ]
    extended_timeframes = [
        tf_1w,
        tf_1mo,
        tf_3mo,
    ]
    timeframes_table = core_timeframes + extended_timeframes

    # 12. Multi-Timeframe Confluence Calculation
    bullish_count = sum(1 for row in core_timeframes if row["bias"] == "BULLISH")
    bearish_count = sum(1 for row in core_timeframes if row["bias"] == "BEARISH")
    neutral_count = sum(1 for row in core_timeframes if row["bias"] == "NEUTRAL")

    macro_bullish = (tf_1h["bias"] == "BULLISH" or tf_4h["bias"] == "BULLISH" or today_metric["bias"] == "BULLISH" or tf_1w["bias"] == "BULLISH")
    micro_bearish = (tf_5m["bias"] == "BEARISH" or tf_15m["bias"] == "BEARISH")
    macro_bearish = (tf_1h["bias"] == "BEARISH" or tf_4h["bias"] == "BEARISH" or today_metric["bias"] == "BEARISH" or tf_1w["bias"] == "BEARISH")
    micro_bullish = (tf_5m["bias"] == "BULLISH" or tf_15m["bias"] == "BULLISH")

    if bullish_count >= 4:
        overall_bias = "BULLISH"
        headline = f"{bullish_count}/6 Timeframes Bullish — Strong Put Writing Confluence"
        master_directive = (
            "Aggressive Bullish Confluence: Institutional put underwriting dominates across horizons. "
            "High-probability environment to buy dips near Put Wall support and deploy Bull Put Spreads."
        )
    elif bearish_count >= 4:
        overall_bias = "BEARISH"
        headline = f"{bearish_count}/6 Timeframes Bearish — Heavy Call Resistance Confluence"
        master_directive = (
            "Defensive Bearish Confluence: Institutional call sellers dominate the tape. "
            "Fade rallies into Call Wall, tighten stops on longs, and deploy Bear Call Spreads."
        )
    elif macro_bullish and micro_bearish:
        overall_bias = "BULLISH (PULLBACK)"
        headline = "Timeframe Divergence: Macro Bullish vs Micro Intraday Resistance"
        master_directive = (
            "Divergence Setup: Higher timeframes (1h/4h/Today) show structural put defense, "
            "but short-term (5m/15m) call writing is causing an intraday pause. Do not chase highs; "
            "wait for intraday selling to exhaust near Put Wall support, then re-enter longs."
        )
    elif macro_bearish and micro_bullish:
        overall_bias = "BEARISH (COUNTER-BOUNCE)"
        headline = "Timeframe Divergence: Micro Bounce into Macro Overhead Resistance"
        master_directive = (
            "Counter-Trend Warning: Short-term (5m/15m) put writing/short covering is producing a bounce "
            "directly into heavy higher-timeframe (1h/4h) call walls. Treat rallies as profit-taking opportunities "
            "or setup for short continuation."
        )
    else:
        overall_bias = "NEUTRAL / MIXED"
        headline = f"{neutral_count}/6 Timeframes Balanced — Two-Way Congestion"
        master_directive = (
            "Two-Way Market Equilibrium: Institutional delta flow is balanced across timeframes. "
            "Avoid heavy directional bets; trade range reversals between Put Wall and Call Wall, "
            "or harvest theta via delta-neutral spreads."
        )

    confluence_summary = {
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "overall_bias": overall_bias,
        "headline": headline,
        "master_directive": master_directive,
    }

    # 13. Dynamic Institutional Summary Alert
    c_15m = tf_15m["call_chg"]
    p_15m = tf_15m["put_chg"]
    call_15m_pct_chg = tf_15m["call_pct_chg"]
    put_15m_pct_chg = tf_15m["put_pct_chg"]
    sent_15m = tf_15m["sentiment"]

    lead_ce = max(strikes, key=lambda s: int(s.get("ce_change_15m") or 0), default=None) if strikes else None
    lead_pe = max(strikes, key=lambda s: int(s.get("pe_change_15m") or 0), default=None) if strikes else None

    if sent_15m == "CALL WRITING" or (c_15m > p_15m and c_15m > 0):
        lead_stk = int(lead_ce["strike"]) if lead_ce else 0
        lead_chg = int(lead_ce.get("ce_change_15m") or 0) if lead_ce else 0
        chg_str = f"+{call_15m_pct_chg:.1f}%" if call_15m_pct_chg >= 0 else f"{call_15m_pct_chg:.1f}%"
        alert_text = (
            f"{now_time} {clean_sym} Call OI {chg_str} in 15 min: {_fmt_indian_qty(c_15m)} contracts, "
            f"most at {lead_stk:,} CE ({_fmt_indian_qty(lead_chg)}): Call writing, a bearish lean, PCR {curr_pcr:.2f}"
        )
        alert_bias = "BEARISH"
    elif sent_15m == "PUT WRITING" or (p_15m > c_15m and p_15m > 0):
        lead_stk = int(lead_pe["strike"]) if lead_pe else 0
        lead_chg = int(lead_pe.get("pe_change_15m") or 0) if lead_pe else 0
        chg_str = f"+{put_15m_pct_chg:.1f}%" if put_15m_pct_chg >= 0 else f"{put_15m_pct_chg:.1f}%"
        alert_text = (
            f"{now_time} {clean_sym} Put OI {chg_str} in 15 min: {_fmt_indian_qty(p_15m)} contracts, "
            f"most at {lead_stk:,} PE ({_fmt_indian_qty(lead_chg)}): Put writing, a bullish lean, PCR {curr_pcr:.2f}"
        )
        alert_bias = "BULLISH"
    else:
        alert_text = (
            f"{now_time} {clean_sym} OI balanced in 15 min: CE {_fmt_indian_qty(c_15m)}, "
            f"PE {_fmt_indian_qty(p_15m)}, two-way positioning, PCR {curr_pcr:.2f}"
        )
        alert_bias = "NEUTRAL"

    summary_alert = {
        "time": now_time,
        "text": alert_text,
        "bias": alert_bias,
        "pcr_oi": curr_pcr,
        "pcr_15m_delta": pcr_15m_delta,
    }

    # 14. 4-Category Flow Matrix: Call Buy, Call Sell, Put Buy, Put Sell (Added vs Unwound)
    four_category_flow = derive_4category_flow(strikes)

    return {
        "total_positions": total_positions,
        "today": today_metric,
        "tf_5m": tf_5m,
        "tf_15m": tf_15m,
        "tf_30m": tf_30m,
        "tf_1h": tf_1h,
        "tf_4h": tf_4h,
        "timeframes_table": timeframes_table,
        "confluence_summary": confluence_summary,
        "summary_alert": summary_alert,
        "four_category_flow": four_category_flow,
    }

