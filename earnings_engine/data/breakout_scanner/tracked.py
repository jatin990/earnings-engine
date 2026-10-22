"""Tracked breakout setups, outcome confirmation, and historical trade evaluation."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db_helpers import row_to_dict
from earnings_engine.data.breakout_scanner.constants import BREAKOUT_STRATEGIES
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)


def _extract_strategy_id_from_setup(item: dict[str, Any]) -> str:
    """Classify a setup into one of the 5 registered breakout strategy keys."""
    strat = str(item.get("strategy_id") or item.get("strategy") or "").upper().strip()
    if "DELIVERY" in strat or "ABSORPTION" in strat:
        return "NSE_DELIVERY_ABSORPTION"
    if "CALL" in strat or "FO_" in strat or "WALL" in strat or "OPTION" in strat:
        return "NSE_FO_CALL_WALL"
    if "VOLUME_PROFILE" in strat or "VAH" in strat:
        return "VOLUME_PROFILE_VAH"
    if "DONCHIAN" in strat or "SQUEEZE" in strat or "TTM" in strat:
        return "DONCHIAN_TTM_SQUEEZE"
    if "CLASSIC" in strat or "TECHNICAL" in strat:
        return "CLASSIC_TECHNICAL"

    arch = str(item.get("setup_archetype") or "").upper()
    if "DELIVERY" in arch or "ABSORPTION" in arch:
        return "NSE_DELIVERY_ABSORPTION"
    if "CALL" in arch or "F&O" in arch or "WALL" in arch or "OPTION" in arch:
        return "NSE_FO_CALL_WALL"
    if "VOLUME PROFILE" in arch or "VAH" in arch:
        return "VOLUME_PROFILE_VAH"
    if "DONCHIAN" in arch or "SQUEEZE" in arch or "TTM" in arch:
        return "DONCHIAN_TTM_SQUEEZE"

    return "CLASSIC_TECHNICAL"


def get_tracked_breakouts(
    days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    tier: str | None = None,
    outcome: str | None = None,
    strategy: str | None = None,
    sort_by: str = "signal_date",
    limit: int = 200,
    live: bool = False,
    capital: float = 1000000.0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Query permanently tracked breakout signals from breakout_tracked_signals with filtering and summary metrics."""
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)

        query_clauses = [
            "1=1",
            "signal_date >= '2026-08-26'",
            "(breakout_happened = 1 OR signal_price >= breakout_trigger OR current_price >= breakout_trigger OR outcome NOT IN ('PENDING', 'ACTIVE', ''))",
        ]
        params: list[Any] = []

        # 1. Date Filtering
        preset_days_int = None
        if days is not None and str(days).strip().lower() not in ("all", "all_time", "none", "", "0"):
            try:
                preset_days_int = int(days)
            except (ValueError, TypeError):
                preset_days_int = None

        if start_date and end_date:
            query_clauses.append("signal_date BETWEEN ? AND ?")
            params.extend([start_date, end_date])
        elif start_date:
            query_clauses.append("signal_date >= ?")
            params.append(start_date)
        elif end_date:
            query_clauses.append("signal_date <= ?")
            params.append(end_date)
        elif preset_days_int is not None and preset_days_int > 0:
            query_clauses.append("signal_date >= DATE('now', ?)")
            params.append(f"-{preset_days_int} days")

        # 2. Tier Filtering
        if tier and tier.upper() not in ("ALL", ""):
            query_clauses.append("UPPER(tier) = ?")
            params.append(tier.upper())

        # 3. Outcome Filtering
        filter_outcome = bool(outcome and outcome.upper() not in ("ALL", ""))
        if filter_outcome:
            out_up = outcome.upper()
            if out_up in ("STOP_HIT", "STOP_LOSS_HIT"):
                query_clauses.append("UPPER(outcome) IN ('STOP_HIT', 'STOP_LOSS_HIT', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up in ("SETUP_FAILED", "BREAKOUT_FAILED"):
                query_clauses.append("UPPER(outcome) IN ('SETUP_FAILED', 'BREAKOUT_FAILED', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up in ("TRIGGERED", "BREAKOUT_SUCCEEDED"):
                query_clauses.append("UPPER(outcome) IN ('TRIGGERED', 'BREAKOUT_SUCCEEDED', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up == "TARGET_HIT":
                query_clauses.append("UPPER(outcome) IN ('TARGET_HIT', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE"):
                query_clauses.append("UPPER(outcome) IN ('ACTIVE', 'COILING_IN_PROFIT', 'COILING_IN_RANGE', 'PENDING')")
            else:
                query_clauses.append("(UPPER(outcome) = ? OR UPPER(outcome) IN ('ACTIVE', 'PENDING'))")
                params.append(out_up)

        # 4. Strategy Filtering
        if strategy and strategy.upper() not in ("ALL", ""):
            strat_up = strategy.upper().strip()
            query_clauses.append("(data_json LIKE ? OR setup_archetype LIKE ?)")
            params.extend([f"%{strat_up}%", f"%{strat_up}%"])

        where_clause = " AND ".join(query_clauses)

        # 4. Sorting
        order_by = "signal_date DESC, composite_score DESC"
        if sort_by == "return_pct":
            order_by = "realized_return_pct DESC"
        elif sort_by == "max_gain":
            order_by = "max_gain_pct DESC"
        elif sort_by in ("score", "composite_score"):
            order_by = "composite_score DESC"
        elif sort_by == "days_elapsed":
            order_by = "days_elapsed ASC"
        elif sort_by == "signal_date_asc":
            order_by = "signal_date ASC"

        sql = f"""
            SELECT id, ticker, company_name, industry, tier, signal_date,
                   signal_price, predicted_value, breakout_trigger, ideal_entry_price,
                   is_late, entry_delay_pct, target_price, stop_loss,
                   risk_reward_ratio, composite_score, resistance_score, volume_score, compression_score,
                   momentum_score, fundamental_score, volume_ratio, atr_pct, pct_from_high,
                   setup_archetype, current_price, current_date, realized_return_pct, max_gain_pct,
                   breakout_happened, outcome, outcome_label, outcome_badge, days_elapsed,
                   scanned_at, data_json, created_at, updated_at
            FROM breakout_tracked_signals
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ?
        """
        params.append(limit)

        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()

        items: list[dict[str, Any]] = []
        for r_raw in rows:
            r = row_to_dict(cur, r_raw)
            raw_json = r.get("data_json")
            parsed_data = {}
            if raw_json:
                try:
                    parsed_data = json.loads(raw_json)
                except Exception:
                    pass

            ticker_val = r.get("ticker", "")
            item = {
                "id": r.get("id"),
                "ticker": ticker_val,
                "company_name": r.get("company_name") or ticker_val.replace(".NS", ""),
                "industry": r.get("industry") or "—",
                "tier": r.get("tier"),
                "signal_date": r.get("signal_date"),
                "signal_price": r.get("signal_price"),
                "predicted_value": r.get("predicted_value"),
                "breakout_trigger": r.get("breakout_trigger"),
                "ideal_entry_price": r.get("ideal_entry_price"),
                "is_late": bool(r.get("is_late")) if r.get("is_late") is not None else False,
                "entry_delay_pct": float(r.get("entry_delay_pct")) if r.get("entry_delay_pct") is not None else 0.0,
                "target_price": r.get("target_price"),
                "stop_loss": r.get("stop_loss"),
                "risk_reward_ratio": r.get("risk_reward_ratio") or 2.0,
                "composite_score": r.get("composite_score"),
                "resistance_score": r.get("resistance_score"),
                "volume_score": r.get("volume_score"),
                "compression_score": r.get("compression_score"),
                "momentum_score": r.get("momentum_score"),
                "fundamental_score": r.get("fundamental_score"),
                "volume_ratio": r.get("volume_ratio"),
                "atr_pct": r.get("atr_pct"),
                "pct_from_high": r.get("pct_from_high"),
                "setup_archetype": r.get("setup_archetype") or "Breakout Setup",
                "current_price": r.get("current_price") or r.get("signal_price"),
                "current_date": r.get("current_date") or r.get("signal_date"),
                "realized_return_pct": r.get("realized_return_pct") or 0.0,
                "max_gain_pct": r.get("max_gain_pct") or 0.0,
                "breakout_happened": bool(r.get("breakout_happened")),
                "outcome": r.get("outcome") or "ACTIVE",
                "outcome_label": r.get("outcome_label") or "Active Setup",
                "outcome_badge": r.get("outcome_badge") or "ACTIVE",
                "days_elapsed": r.get("days_elapsed") or 0,
                "scanned_at": r.get("scanned_at"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            if parsed_data:
                for k, v in parsed_data.items():
                    if k not in item and v is not None:
                        item[k] = v
            items.append(item)

        # 5. Always process 14-day outcome vs live recent breakout data
        if items:
            from concurrent.futures import ThreadPoolExecutor
            from earnings_engine.data.prices import fetch_prices, fetch_batch_live_quotes

            tracked_syms = [it.get("ticker") for it in items if it.get("ticker")]
            live_quotes_map: dict[str, dict[str, Any]] = {}
            try:
                live_quotes_map = fetch_batch_live_quotes(tracked_syms, settings=settings, sync_db=True)
            except Exception as lq_err:
                logger.debug("[TRACKED-BREAKOUTS] Batch live quote fetch error: %s", lq_err)

            def _process_tracked_item(item_d: dict[str, Any]) -> None:
                t = item_d.get("ticker")
                sig_p = item_d.get("signal_price")
                trig_p = item_d.get("breakout_trigger")
                target_p = item_d.get("target_price")
                stop_p = item_d.get("stop_loss")
                sig_date = item_d.get("signal_date")

                # Ensure timestamps and staleness attributes are initialized
                item_d["signal_time"] = item_d.get("signal_time") or item_d.get("created_at") or (f"{sig_date} 15:30" if sig_date else None)
                item_d["signal_datetime"] = item_d.get("signal_datetime") or item_d.get("created_at") or sig_date

                lq = live_quotes_map.get(t) if live_quotes_map else None
                if lq:
                    item_d["quote_timestamp"] = lq.get("quote_timestamp") or lq.get("last_updated")
                    item_d["current_price_time"] = item_d["quote_timestamp"]
                    item_d["price_delay_status"] = lq.get("price_delay_status") or ("LIVE" if lq.get("is_live") else "DELAYED")
                    item_d["is_price_stale"] = bool(lq.get("is_price_stale", False))
                else:
                    item_d["quote_timestamp"] = item_d.get("current_date") or item_d.get("updated_at")
                    item_d["current_price_time"] = item_d["quote_timestamp"]
                    item_d["price_delay_status"] = "DELAYED"
                    item_d["is_price_stale"] = False

                if not t or "TEST" in t.upper() or "MOCK" in t.upper() or "DUMMY" in t.upper():
                    return
                try:
                    df = fetch_prices(t, settings, force=live)
                    if not df.empty and "close" in df.columns:
                        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
                        if not closes.empty:
                            latest_hist_close = round(float(closes.iloc[-1]), 2)
                            latest_hist_date = str(df.index[-1])[:10]

                            cur_p = latest_hist_close
                            if lq and lq.get("current_price") and float(lq.get("current_price") or 0) > 0:
                                cur_p = float(lq["current_price"])

                            # Slicing strictly Point-in-Time starting at signal date
                            post_df = pd.DataFrame()
                            if sig_date:
                                try:
                                    sig_dt = pd.to_datetime(str(sig_date)[:10]).tz_localize(None)
                                    df_norm_idx = pd.to_datetime(df.index).tz_localize(None)
                                    post_mask = df_norm_idx >= sig_dt
                                    post_df = df.loc[post_mask]
                                except Exception:
                                    post_df = pd.DataFrame()

                            if post_df.empty:
                                # When signal is newer than price history or created today/weekend:
                                days_elapsed = 1
                                item_d["days_elapsed"] = days_elapsed

                                # Validate if live quote is fresh and on/after signal date
                                valid_lq_price = False
                                if lq and lq.get("current_price") and float(lq.get("current_price") or 0) > 0:
                                    lq_ts = str(lq.get("quote_timestamp") or lq.get("last_updated") or "")[:10]
                                    sig_d_str = str(sig_date)[:10] if sig_date else ""
                                    if not sig_d_str or not lq_ts or lq_ts >= sig_d_str:
                                        cur_p = float(lq["current_price"])
                                        valid_lq_price = True

                                if not valid_lq_price and sig_p:
                                    cur_p = sig_p

                                item_d["current_price"] = cur_p
                                item_d["current_date"] = str(sig_date)[:10] if sig_date else latest_hist_date
                                item_d["post_high"] = max(cur_p, sig_p or cur_p)
                                item_d["peak_price"] = item_d["post_high"]
                                if sig_p and sig_p > 0:
                                    item_d["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                                    item_d["max_gain_pct"] = round(((item_d["post_high"] - sig_p) / sig_p) * 100, 2)
                                else:
                                    item_d["realized_return_pct"] = 0.0
                                    item_d["max_gain_pct"] = 0.0

                                item_d["is_live_recent"] = True
                                item_d["settled_14d"] = False

                                item_d["days_to_target"] = None
                                item_d["strategy_id"] = _extract_strategy_id_from_setup(item_d)

                                if target_p and (cur_p >= target_p or item_d["post_high"] >= target_p):
                                    item_d["outcome"] = "TARGET_HIT"
                                    item_d["outcome_label"] = "Target Hit 🎯 (Live D1)"
                                    item_d["outcome_badge"] = "TARGET_HIT"
                                    item_d["breakout_happened"] = True
                                    item_d["days_to_target"] = 1
                                    item_d["what_happened_summary"] = f"🎯 Hit target ₹{target_p:,.2f} on Day 1 (+{item_d.get('max_gain_pct',0):.1f}% peak)."
                                elif stop_p and cur_p <= stop_p:
                                    item_d["outcome"] = "STOP_HIT"
                                    item_d["outcome_label"] = "Stop Hit 🛑 (Live D1)"
                                    item_d["outcome_badge"] = "STOP_HIT"
                                    item_d["breakout_happened"] = False
                                    item_d["what_happened_summary"] = f"🛑 Hit stop loss ₹{stop_p:,.2f} on Day 1."
                                elif sig_p and cur_p >= sig_p:
                                    item_d["outcome"] = "TRIGGERED"
                                    item_d["outcome_label"] = f"Live Active 🟢 (+{item_d.get('realized_return_pct',0):.1f}% D1)"
                                    item_d["outcome_badge"] = "TRIGGERED"
                                    item_d["breakout_happened"] = True
                                    item_d["what_happened_summary"] = f"🟢 Holding breakout gains at ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return on Day 1/14)."
                                else:
                                    item_d["outcome"] = "BREAKOUT_RETRACED"
                                    item_d["outcome_label"] = f"Breakout Retraced ⚠️ ({item_d.get('realized_return_pct',0):+.1f}% Live D1)"
                                    item_d["outcome_badge"] = "BREAKOUT_RETRACED"
                                    item_d["breakout_happened"] = False
                                    item_d["what_happened_summary"] = f"⚠️ Pulled back to ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return on Day 1)."
                            else:
                                days_elapsed = max(1, len(post_df))
                                item_d["days_elapsed"] = days_elapsed
                                item_d["current_price"] = cur_p
                                item_d["current_date"] = latest_hist_date
                                item_d["strategy_id"] = _extract_strategy_id_from_setup(item_d)

                                if days_elapsed >= 14:
                                    # 14-day post-signal settled trajectory
                                    w14_df = post_df.head(14)
                                    w14_subsequent = w14_df.iloc[1:] if len(w14_df) > 1 else pd.DataFrame()
                                    w14_high = float(pd.to_numeric(w14_df["high"], errors="coerce").dropna().max()) if "high" in w14_df and not w14_df.empty else cur_p
                                    w14_sub_low = float(pd.to_numeric(w14_subsequent["low"], errors="coerce").dropna().min()) if not w14_subsequent.empty and "low" in w14_subsequent else None
                                    w14_close = float(pd.to_numeric(w14_df["close"], errors="coerce").dropna().iloc[-1]) if "close" in w14_df and not w14_df.empty else cur_p

                                    item_d["post_high"] = w14_high
                                    item_d["peak_price"] = w14_high
                                    if sig_p and sig_p > 0:
                                        item_d["realized_return_pct"] = round(((w14_close - sig_p) / sig_p) * 100, 2)
                                        item_d["max_gain_pct"] = round(((w14_high - sig_p) / sig_p) * 100, 2)

                                    item_d["is_live_recent"] = False
                                    item_d["settled_14d"] = True
                                    item_d["days_to_target"] = None

                                    if target_p and w14_high >= target_p:
                                        target_day = 14
                                        if "high" in w14_df:
                                            highs = pd.to_numeric(w14_df["high"], errors="coerce").fillna(0).tolist()
                                            for idx, h_val in enumerate(highs, start=1):
                                                if h_val >= target_p:
                                                    target_day = idx
                                                    break
                                        item_d["days_to_target"] = target_day
                                        item_d["outcome"] = "TARGET_HIT"
                                        item_d["outcome_label"] = f"Target Hit 🎯 (Day {target_day})"
                                        item_d["outcome_badge"] = "TARGET_HIT"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🎯 Reached upside target ₹{target_p:,.2f} on Day {target_day}/14 (+{item_d.get('max_gain_pct',0):.1f}% peak)."
                                    elif stop_p and ((w14_sub_low is not None and w14_sub_low <= stop_p) or w14_close <= stop_p):
                                        item_d["outcome"] = "STOP_HIT"
                                        item_d["outcome_label"] = "Stop Hit 🛑 (14D)"
                                        item_d["outcome_badge"] = "STOP_HIT"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"🛑 Breached protective stop at ₹{stop_p:,.2f} within 14-day window."
                                    elif sig_p and w14_close >= sig_p:
                                        item_d["outcome"] = "TRIGGERED"
                                        item_d["outcome_label"] = f"Breakout Succeeded 🚀 (+{item_d.get('realized_return_pct',0):.1f}% 14D)"
                                        item_d["outcome_badge"] = "TRIGGERED"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🚀 Settled +{item_d.get('realized_return_pct',0):.1f}% in profit over 14-day post-breakout period."
                                    else:
                                        item_d["outcome"] = "BREAKOUT_RETRACED"
                                        item_d["outcome_label"] = "Breakout Retraced ⚠️ (14D)"
                                        item_d["outcome_badge"] = "BREAKOUT_RETRACED"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"⚠️ Breakout pulled back to ₹{w14_close:,.2f} by day 14."
                                else:
                                    # Recently broken out (< 14 days) -> LIVE tracking!
                                    post_subsequent = post_df.iloc[1:] if len(post_df) > 1 else pd.DataFrame()
                                    post_high = float(pd.to_numeric(post_df["high"], errors="coerce").dropna().max()) if "high" in post_df and not post_df.empty else cur_p
                                    post_sub_low = float(pd.to_numeric(post_subsequent["low"], errors="coerce").dropna().min()) if not post_subsequent.empty and "low" in post_subsequent else None
                                    post_high = max(post_high, cur_p)

                                    item_d["post_high"] = post_high
                                    item_d["peak_price"] = post_high
                                    if sig_p and sig_p > 0:
                                        item_d["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                                        item_d["max_gain_pct"] = round(((post_high - sig_p) / sig_p) * 100, 2)

                                    item_d["is_live_recent"] = True
                                    item_d["settled_14d"] = False
                                    item_d["days_to_target"] = None

                                    if target_p and (cur_p >= target_p or post_high >= target_p):
                                        target_day = days_elapsed
                                        if not post_df.empty and "high" in post_df:
                                            highs = pd.to_numeric(post_df["high"], errors="coerce").fillna(0).tolist()
                                            for idx, h_val in enumerate(highs, start=1):
                                                if h_val >= target_p:
                                                    target_day = idx
                                                    break
                                        item_d["days_to_target"] = target_day
                                        item_d["outcome"] = "TARGET_HIT"
                                        item_d["outcome_label"] = f"Target Hit 🎯 (Live D{target_day})"
                                        item_d["outcome_badge"] = "TARGET_HIT"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🎯 Hit target ₹{target_p:,.2f} on Day {target_day}/14 (+{item_d.get('max_gain_pct',0):.1f}% peak)."
                                    elif stop_p and (cur_p <= stop_p or (post_sub_low is not None and post_sub_low <= stop_p)):
                                        item_d["outcome"] = "STOP_HIT"
                                        item_d["outcome_label"] = f"Stop Hit 🛑 (Live D{days_elapsed})"
                                        item_d["outcome_badge"] = "STOP_HIT"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"🛑 Hit stop loss ₹{stop_p:,.2f} on Day {days_elapsed}/14."
                                    elif sig_p and cur_p >= sig_p:
                                        item_d["outcome"] = "TRIGGERED"
                                        item_d["outcome_label"] = f"Live Active 🟢 (+{item_d.get('realized_return_pct',0):.1f}% D{days_elapsed})"
                                        item_d["outcome_badge"] = "TRIGGERED"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🟢 Holding breakout gains at ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return on Day {days_elapsed}/14)."
                                    else:
                                        item_d["outcome"] = "BREAKOUT_RETRACED"
                                        item_d["outcome_label"] = f"Breakout Retraced ⚠️ ({item_d.get('realized_return_pct',0):+.1f}% Live D{days_elapsed})"
                                        item_d["outcome_badge"] = "BREAKOUT_RETRACED"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"⚠️ Breached trigger to peak ₹{post_high:,.2f} (+{item_d.get('max_gain_pct',0):.1f}%) but retraced to ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return)."
                except Exception as ex:
                    logger.debug("Failed processing tracked breakout for %s: %s", t, ex)

            with ThreadPoolExecutor(max_workers=min(10, len(items))) as pool:
                list(pool.map(_process_tracked_item, items))

            # Batch persist updated live tracking data back to breakout_tracked_signals
            try:
                update_params = []
                now_iso = datetime.now(timezone.utc).isoformat()
                for it in items:
                    item_id = it.get("id")
                    if not item_id:
                        continue
                    update_params.append((
                        it.get("current_price"),
                        it.get("current_date"),
                        it.get("realized_return_pct", 0.0),
                        it.get("max_gain_pct", 0.0),
                        1 if it.get("breakout_happened") else 0,
                        it.get("outcome"),
                        it.get("outcome_label"),
                        it.get("outcome_badge"),
                        it.get("days_elapsed", 0),
                        now_iso,
                        item_id,
                    ))
                if update_params:
                    update_sql = """
                        UPDATE breakout_tracked_signals
                        SET current_price = ?,
                            current_date = ?,
                            realized_return_pct = ?,
                            max_gain_pct = ?,
                            breakout_happened = ?,
                            outcome = ?,
                            outcome_label = ?,
                            outcome_badge = ?,
                            days_elapsed = ?,
                            updated_at = ?
                        WHERE id = ?
                    """
                    conn.executemany(update_sql, update_params)
                    if hasattr(conn, "commit"):
                        conn.commit()
            except Exception as e:
                logger.debug("[TRACKED-BREAKOUTS] Batch update error: %s", e)

        # Post-filter items by outcome if requested
        if filter_outcome:
            out_up = outcome.upper()
            filtered_items = []
            for it in items:
                it_out = str(it.get("outcome") or "").upper()
                if out_up in ("STOP_HIT", "STOP_LOSS_HIT") and it_out in ("STOP_HIT", "STOP_LOSS_HIT"):
                    filtered_items.append(it)
                elif out_up in ("SETUP_FAILED", "BREAKOUT_FAILED") and it_out in ("SETUP_FAILED", "BREAKOUT_FAILED"):
                    filtered_items.append(it)
                elif out_up in ("TRIGGERED", "BREAKOUT_SUCCEEDED") and it_out in ("TRIGGERED", "BREAKOUT_SUCCEEDED"):
                    filtered_items.append(it)
                elif out_up == "TARGET_HIT" and it_out == "TARGET_HIT":
                    filtered_items.append(it)
                elif out_up in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE") and it_out in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE", "PENDING"):
                    filtered_items.append(it)
                elif out_up == it_out:
                    filtered_items.append(it)
            items = filtered_items

        # 6. Summary metrics calculation & 10L Portfolio Capital Simulation
        total_tracked = len(items)
        initial_capital = float(capital) if capital and capital > 0 else 1000000.0
        alloc_per_trade = (initial_capital / total_tracked) if total_tracked > 0 else 0.0

        for it in items:
            out_str = str(it.get("outcome") or "").upper()
            sig_p = it.get("signal_price") or it.get("breakout_trigger")
            target_p = it.get("target_price")
            stop_p = it.get("stop_loss")
            max_g = float(it.get("max_gain_pct") or 0.0)

            if out_str == "TARGET_HIT":
                target_ret = round(((target_p - sig_p) / sig_p * 100.0), 2) if (sig_p and target_p and sig_p > 0) else float(it.get("realized_return_pct") or 0.0)
                peak_ret = max(target_ret, max_g)
                # 70% booked at target, 30% booked at peak
                sim_ret = round(0.70 * target_ret + 0.30 * peak_ret, 2)
                book_note = f"70% @ Target (+{target_ret:.1f}%), 30% @ Peak (+{peak_ret:.1f}%)"
            elif out_str in ("STOP_HIT", "STOP_LOSS_HIT"):
                stop_ret = round(((stop_p - sig_p) / sig_p * 100.0), 2) if (sig_p and stop_p and sig_p > 0) else float(it.get("realized_return_pct") or -5.0)
                if stop_ret > 0:
                    stop_ret = -abs(stop_ret)
                sim_ret = round(stop_ret, 2)
                book_note = f"100% Stop Loss Hit ({stop_ret:.1f}%)"
            elif out_str in ("ACTIVE", "PENDING", "COILING_IN_PROFIT", "COILING_IN_RANGE"):
                sim_ret = round(float(it.get("realized_return_pct") or 0.0), 2)
                book_note = f"MTM Live ({sim_ret:+.1f}%)"
            else:
                sim_ret = round(float(it.get("realized_return_pct") or 0.0), 2)
                book_note = f"14D Settled ({sim_ret:+.1f}%)"

            sim_pnl = round(alloc_per_trade * (sim_ret / 100.0), 2)
            it["simulated_return_pct"] = sim_ret
            it["simulated_allocation"] = round(alloc_per_trade, 2)
            it["simulated_pnl"] = sim_pnl
            it["simulated_booking_note"] = book_note

        positive_count = sum(1 for it in items if (it.get("realized_return_pct") or 0) > 0 or it.get("outcome") in ("TARGET_HIT", "BREAKOUT_SUCCEEDED"))
        loss_count = sum(1 for it in items if (it.get("realized_return_pct") or 0) < 0 or it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT", "SETUP_FAILED", "BREAKOUT_FAILED"))
        win_rate_pct = round((positive_count / total_tracked) * 100, 1) if total_tracked > 0 else 0.0

        all_rets = [it.get("realized_return_pct") or 0.0 for it in items]
        avg_return_pct = round(sum(all_rets) / len(all_rets), 2) if all_rets else 0.0

        all_peaks = [it.get("max_gain_pct") or 0.0 for it in items]
        avg_peak_gain_pct = round(sum(all_peaks) / len(all_peaks), 2) if all_peaks else 0.0

        best_item = max(items, key=lambda x: x.get("realized_return_pct") or -999) if items else None
        max_return_pct = best_item.get("realized_return_pct", 0.0) if best_item else 0.0
        max_return_ticker = best_item.get("ticker", "—") if best_item else "—"

        target_hit_count = sum(1 for it in items if it.get("outcome") == "TARGET_HIT")
        target_hit_rate_pct = round((target_hit_count / total_tracked) * 100, 1) if total_tracked > 0 else 0.0
        triggered_count = sum(1 for it in items if it.get("outcome") in ("TRIGGERED", "BREAKOUT_SUCCEEDED", "TARGET_HIT", "BREAKOUT_RETRACED"))
        stop_hit_count = sum(1 for it in items if it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT"))
        stop_hit_rate_pct = round((stop_hit_count / total_tracked) * 100, 1) if total_tracked > 0 else 0.0
        setup_failed_count = sum(1 for it in items if it.get("outcome") in ("SETUP_FAILED", "BREAKOUT_FAILED"))
        active_count = sum(1 for it in items if not it.get("settled_14d", False) and (it.get("days_elapsed") or 0) < 14)

        all_days_to_target = [it["days_to_target"] for it in items if it.get("days_to_target") is not None and it.get("outcome") == "TARGET_HIT"]
        avg_days_to_target = round(sum(all_days_to_target) / len(all_days_to_target), 1) if all_days_to_target else None

        # Per-Strategy breakdown matrix
        per_strategy_stats: dict[str, dict[str, Any]] = {}
        for s_key, s_meta in BREAKOUT_STRATEGIES.items():
            s_items = [it for it in items if _extract_strategy_id_from_setup(it) == s_key]
            s_total = len(s_items)
            if s_total == 0:
                per_strategy_stats[s_key] = {
                    "strategy_id": s_key,
                    "strategy_name": s_meta.get("name", s_key),
                    "short_name": s_meta.get("short_name", s_key),
                    "icon": s_meta.get("icon", "⚡"),
                    "badge": s_meta.get("badge", s_key),
                    "total_tracked": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "win_rate_pct": 0.0,
                    "target_hit_count": 0,
                    "target_hit_rate_pct": 0.0,
                    "stop_hit_count": 0,
                    "stop_hit_rate_pct": 0.0,
                    "avg_days_to_target": None,
                    "avg_return_pct": 0.0,
                    "avg_peak_gain_pct": 0.0,
                    "active_count": 0,
                    "triggered_count": 0,
                    "best_ticker": "—",
                    "best_return_pct": 0.0,
                }
            else:
                s_wins = sum(1 for it in s_items if (it.get("realized_return_pct") or 0) > 0 or it.get("outcome") in ("TARGET_HIT", "BREAKOUT_SUCCEEDED"))
                s_losses = sum(1 for it in s_items if (it.get("realized_return_pct") or 0) < 0 or it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT", "SETUP_FAILED", "BREAKOUT_FAILED"))
                s_targets = sum(1 for it in s_items if it.get("outcome") == "TARGET_HIT")
                s_stops = sum(1 for it in s_items if it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT"))
                s_active = sum(1 for it in s_items if not it.get("settled_14d", False) and (it.get("days_elapsed") or 0) < 14)
                s_triggered = sum(1 for it in s_items if it.get("outcome") in ("TRIGGERED", "BREAKOUT_SUCCEEDED", "TARGET_HIT", "BREAKOUT_RETRACED"))
                s_rets = [it.get("realized_return_pct") or 0.0 for it in s_items]
                s_peaks = [it.get("max_gain_pct") or 0.0 for it in s_items]
                s_target_days = [it["days_to_target"] for it in s_items if it.get("days_to_target") is not None and it.get("outcome") == "TARGET_HIT"]
                s_best = max(s_items, key=lambda x: x.get("realized_return_pct") or -999) if s_items else None

                per_strategy_stats[s_key] = {
                    "strategy_id": s_key,
                    "strategy_name": s_meta.get("name", s_key),
                    "short_name": s_meta.get("short_name", s_key),
                    "icon": s_meta.get("icon", "⚡"),
                    "badge": s_meta.get("badge", s_key),
                    "total_tracked": s_total,
                    "win_count": s_wins,
                    "loss_count": s_losses,
                    "win_rate_pct": round((s_wins / s_total) * 100, 1),
                    "target_hit_count": s_targets,
                    "target_hit_rate_pct": round((s_targets / s_total) * 100, 1),
                    "stop_hit_count": s_stops,
                    "stop_hit_rate_pct": round((s_stops / s_total) * 100, 1),
                    "avg_days_to_target": round(sum(s_target_days) / len(s_target_days), 1) if s_target_days else None,
                    "avg_return_pct": round(sum(s_rets) / len(s_rets), 2) if s_rets else 0.0,
                    "avg_peak_gain_pct": round(sum(s_peaks) / len(s_peaks), 2) if s_peaks else 0.0,
                    "active_count": s_active,
                    "triggered_count": s_triggered,
                    "best_ticker": s_best.get("ticker", "—") if s_best else "—",
                    "best_return_pct": s_best.get("realized_return_pct", 0.0) if s_best else 0.0,
                }

        # Portfolio simulation aggregation
        total_sim_profit = round(sum(it.get("simulated_pnl", 0.0) for it in items if (it.get("simulated_pnl") or 0.0) > 0), 2)
        total_sim_loss = round(sum(abs(it.get("simulated_pnl", 0.0)) for it in items if (it.get("simulated_pnl") or 0.0) < 0), 2)
        net_sim_pnl = round(sum(it.get("simulated_pnl", 0.0) for it in items), 2)
        final_sim_capital = round(initial_capital + net_sim_pnl, 2)
        sim_return_pct = round((net_sim_pnl / initial_capital) * 100.0, 2) if initial_capital > 0 else 0.0
        profit_factor = round(total_sim_profit / total_sim_loss, 2) if total_sim_loss > 0 else (99.0 if total_sim_profit > 0 else 0.0)

        portfolio_sim = {
            "initial_capital": initial_capital,
            "final_capital": final_sim_capital,
            "net_pnl": net_sim_pnl,
            "return_pct": sim_return_pct,
            "total_profit": total_sim_profit,
            "total_loss": total_sim_loss,
            "profit_factor": profit_factor,
            "allocation_per_trade": round(alloc_per_trade, 2),
            "winning_trades": sum(1 for it in items if (it.get("simulated_return_pct") or 0) > 0),
            "losing_trades": sum(1 for it in items if (it.get("simulated_return_pct") or 0) < 0),
            "breakeven_trades": sum(1 for it in items if (it.get("simulated_return_pct") or 0) == 0),
        }

        return {
            "success": True,
            "total_count": total_tracked,
            "timeframe": {
                "preset_days": days,
                "start_date": start_date,
                "end_date": end_date,
                "as_of": datetime.now(timezone.utc).isoformat(),
            },
            "summary": {
                "total_tracked": total_tracked,
                "win_rate_pct": win_rate_pct,
                "win_count": positive_count,
                "loss_count": loss_count,
                "target_hit_count": target_hit_count,
                "target_hit_rate_pct": target_hit_rate_pct,
                "stop_hit_count": stop_hit_count,
                "stop_hit_rate_pct": stop_hit_rate_pct,
                "avg_days_to_target": avg_days_to_target,
                "avg_return_pct": avg_return_pct,
                "avg_peak_gain_pct": avg_peak_gain_pct,
                "max_return_pct": max_return_pct,
                "max_return_ticker": max_return_ticker,
                "active_count": active_count,
                "triggered_count": triggered_count,
                "setup_failed_count": setup_failed_count,
                "per_strategy_stats": per_strategy_stats,
                "portfolio_simulation": portfolio_sim,
            },
            "items": items,
        }
    except Exception as e:
        logger.exception("[BREAKOUT-TRACKED] Failed fetching tracked breakouts: %s", e)
        return {
            "success": False,
            "error": str(e),
            "total_count": 0,
            "summary": {},
            "items": [],
        }


def delete_tracked_breakout(setup_id: int, settings: Settings | None = None) -> bool:
    """Delete a single tracked breakout setup by its primary key ID."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    try:
        cur = conn.execute("DELETE FROM breakout_tracked_signals WHERE id = ?", (setup_id,))
        conn.commit()
        deleted = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount > 0 else False
        logger.info("[BREAKOUT-TRACKED] Deleted tracked setup ID=%s (deleted=%s)", setup_id, bool(deleted))
        return bool(deleted)
    except Exception as e:
        logger.exception("[BREAKOUT-TRACKED] Failed deleting tracked setup ID=%s: %s", setup_id, e)
        return False
    finally:
        conn.close()


def delete_tracked_breakouts_by_ticker(ticker: str, settings: Settings | None = None) -> int:
    """Delete all tracked breakout setups for a given ticker symbol."""
    settings = settings or Settings()
    sym = ticker.upper().strip()
    conn = get_db_connection(settings)
    try:
        cur = conn.execute(
            "DELETE FROM breakout_tracked_signals WHERE UPPER(ticker) = ? OR UPPER(ticker) = ?",
            (sym, sym.replace(".NS", "")),
        )
        conn.commit()
        deleted = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount >= 0 else 0
        logger.info("[BREAKOUT-TRACKED] Deleted %d tracked setups for ticker=%s", deleted, sym)
        return deleted
    except Exception as e:
        logger.exception("[BREAKOUT-TRACKED] Failed deleting tracked setups for ticker=%s: %s", sym, e)
        return 0
    finally:
        conn.close()


def get_tracked_ticker_set(settings: Settings | None = None) -> set[str]:
    """Return set of ticker symbols permanently persisted and tracked in breakout_tracked_signals / breakout_radar database."""
    settings = settings or Settings()
    conn = None
    try:
        conn = get_db_connection(settings)
        cur = conn.execute("SELECT DISTINCT UPPER(ticker) FROM breakout_tracked_signals WHERE ticker IS NOT NULL")
        tracked = {str(r[0]) for r in cur.fetchall() if r and r[0]}
        cur2 = conn.execute("SELECT DISTINCT UPPER(ticker) FROM breakout_radar WHERE ticker IS NOT NULL")
        for r in cur2.fetchall():
            if r and r[0]:
                tracked.add(str(r[0]))
        return tracked
    except Exception as e:
        logger.debug("[BREAKOUT] Error querying tracked ticker set: %s", e)
        return set()
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def confirm_breakout_outcomes(settings: Settings | None = None) -> dict[str, Any]:
    """Reconcile and confirm real-world outcomes for all tracked breakout setups against latest price history.

    Audits pending/active setups, evaluates post-signal candles against breakout_trigger,
    target_price, and stop_loss with a 0.15% confirmation buffer, and updates database records.
    """
    settings = settings or Settings()
    t_start = time.perf_counter()
    from earnings_engine.data.prices import load_prices, _connect
    from earnings_engine.data.breakout_scanner.storage import _init_breakout_db

    updated_count = 0
    resolved_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with _connect(settings) as conn:
            _init_breakout_db(conn)
            rows = conn.execute(
                """
                SELECT ticker, strategy, signal_date, signal_price, breakout_trigger,
                       target_price, stop_loss, outcome, created_at
                FROM breakout_radar
                WHERE outcome IN ('ACTIVE', 'PENDING', 'COILING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')
                   OR outcome IS NULL
                """
            ).fetchall()

            if not rows:
                return {"success": True, "audited_count": 0, "resolved_count": 0, "duration_s": 0.0}

            updates = []
            for row in rows:
                ticker, strat, sig_date, sig_price, trigger, target, stop, prev_outcome, _ = row
                if not ticker or not sig_date or not trigger:
                    continue

                prices_df = load_prices(ticker, settings)
                if prices_df is None or prices_df.empty:
                    continue

                sig_clean = str(sig_date).strip()[:10]
                future_df = prices_df.loc[prices_df.index > sig_clean]
                if future_df.empty:
                    continue

                all_closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
                cur_price = float(all_closes.iloc[-1])
                cur_date = str(prices_df.index[-1])[:10]

                f_highs = pd.to_numeric(future_df["high"], errors="coerce") if "high" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
                f_lows = pd.to_numeric(future_df["low"], errors="coerce") if "low" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
                post_high = float(f_highs.max()) if not f_highs.empty else sig_price
                post_low = float(f_lows.min()) if not f_lows.empty else sig_price

                realized_ret = round(((cur_price - sig_price) / sig_price) * 100, 2)
                max_gain = round(((post_high - sig_price) / sig_price) * 100, 2)
                days_el = len(future_df)

                # 0.15% trigger confirmation buffer
                breakout_fired = bool(post_high >= trigger * 1.0015 or cur_price >= trigger * 1.0015)

                # Keep today's freshly-signaled breakouts in the active pool — do NOT resolve
                # them on day-0. They should stay live so traders can still track/enter them.
                is_today_signal = sig_clean == cur_date

                if target and post_high >= target:
                    outcome = "TARGET_HIT"
                    outcome_label = f"Target Hit 🎯 (+{max_gain}%)"
                    outcome_badge = "emerald"
                    broke_happened = 1
                elif breakout_fired and not is_today_signal:
                    if stop and (post_low <= stop or cur_price <= stop):
                        outcome = "STOP_LOSS_HIT"
                        outcome_label = f"Stop Hit 🛑 ({realized_ret:+0.1f}%)"
                        outcome_badge = "rose"
                        broke_happened = 0
                    elif cur_price >= sig_price:
                        outcome = "BREAKOUT_SUCCEEDED"
                        outcome_label = f"Breakout Succeeded ✅ ({realized_ret:+0.1f}%)"
                        outcome_badge = "emerald"
                        broke_happened = 1
                    else:
                        outcome = "BREAKOUT_RETRACED"
                        outcome_label = f"Breakout Retraced ⚠️ ({realized_ret:+0.1f}%)"
                        outcome_badge = "amber"
                        broke_happened = 0
                elif stop and (post_low <= stop or cur_price <= stop):
                    outcome = "SETUP_FAILED"
                    outcome_label = f"Setup Failed ❌ ({realized_ret:+0.1f}%)"
                    outcome_badge = "rose"
                    broke_happened = 0
                elif cur_price >= sig_price:
                    outcome = "COILING_IN_PROFIT"
                    outcome_label = f"Coiling In Green 🟢 ({realized_ret:+0.1f}%)"
                    outcome_badge = "emerald"
                    broke_happened = 0
                else:
                    outcome = "COILING_IN_RANGE"
                    outcome_label = f"Coiling In Range 🗜️ ({realized_ret:+0.1f}%)"
                    outcome_badge = "slate"
                    broke_happened = 0

                if outcome in ("TARGET_HIT", "BREAKOUT_SUCCEEDED", "STOP_LOSS_HIT", "SETUP_FAILED", "BREAKOUT_RETRACED"):
                    resolved_count += 1

                updates.append((
                    cur_price, cur_date, realized_ret, max_gain, broke_happened,
                    outcome, outcome_label, outcome_badge, days_el, now_iso,
                    ticker, strat
                ))

            if updates:
                conn.executemany(
                    """
                    UPDATE breakout_radar
                    SET current_price = ?, current_date = ?, realized_return_pct = ?,
                        max_gain_pct = ?, breakout_happened = ?, outcome = ?,
                        outcome_label = ?, outcome_badge = ?, days_elapsed = ?,
                        updated_at = ?
                    WHERE ticker = ? AND strategy = ?
                    """,
                    updates
                )
                conn.commit()
                updated_count = len(updates)

    except Exception as e:
        logger.error("[BREAKOUT-OUTCOMES] Failed confirming breakout outcomes: %s", e)
        return {"success": False, "error": str(e), "audited_count": 0, "resolved_count": 0}

    return {
        "success": True,
        "audited_count": updated_count,
        "resolved_count": resolved_count,
        "duration_s": round(time.perf_counter() - t_start, 2),
        "run_at": now_iso,
    }
