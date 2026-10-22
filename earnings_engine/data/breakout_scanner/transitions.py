"""Tier transitions and promotion/demotion lifecycle for Breakout Radar pools."""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.universe import is_fno_eligible
from earnings_engine.data.breakout_scanner.constants import (
    HOT_THRESHOLD,
    WARM_THRESHOLD,
    HOT_DEMOTION_THRESHOLD,
    WARM_DEMOTION_THRESHOLD,
)
from earnings_engine.data.breakout_scanner.state import (
    _pool,
    _pool_key,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.breakout_scanner.scoring import _should_be_hot
from earnings_engine.data.breakout_scanner.audit_log import record_breakout_transition

logger = logging.getLogger(__name__)


def _promote(ticker: str, result: dict, settings: Settings | None = None) -> None:
    """Place a ticker into the correct tier based on its score and audit the transition."""
    settings = settings or Settings()
    strat = (result.get("strategy") or "CLASSIC_TECHNICAL").upper().strip()
    if strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(ticker):
        logger.debug("[BREAKOUT:FNO_BYPASS] Skipping promotion of %s for NSE_FO_CALL_WALL; not F&O eligible", ticker)
        return
    result["strategy"] = strat
    key = _pool_key(ticker, strat)
    new_score = result.get("composite_score", 0)
    cur_p = result.get("current_price") or result.get("signal_price")
    trig_p = result.get("breakout_trigger")
    vol_r = result.get("volume_ratio", 1.0)
    cat_headline = (result.get("catalyst_headlines") or [None])[0]

    tier = str(result.get("tier") or ("HOT" if _should_be_hot(result) else ("WARM" if new_score >= WARM_THRESHOLD else "WARM"))).upper()
    result["tier"] = tier

    if tier == "HOT":
        was_warm = key in _pool["warm"]
        was_hot = key in _pool["hot"]
        _pool["hot"][key] = {"result": result, "consecutive_low": 0}
        _pool["warm"].pop(key, None)

        if not was_hot:
            from_t = "WARM" if was_warm else "COLD"
            reason_str = f"Promoted to HOT ({strat}): Score {new_score:.1f} (>= {HOT_THRESHOLD}) with volume ratio {vol_r:.2f}x approaching resistance/trigger ₹{trig_p}"
            if cat_headline:
                reason_str += f" + News: {cat_headline}"
            record_breakout_transition(
                ticker=ticker,
                event_type="PROMOTED_HOT",
                from_tier=from_t,
                to_tier="HOT",
                score_before=None,
                score_after=new_score,
                price=cur_p,
                trigger_price=trig_p,
                target_price=result.get("target_price"),
                stop_loss=result.get("stop_loss"),
                risk_reward_ratio=result.get("risk_reward_ratio"),
                volume_ratio=vol_r,
                reason=reason_str,
                catalyst_impact=cat_headline,
                company_name=result.get("company_name"),
                strategy=strat,
                settings=settings,
            )

    elif new_score >= WARM_THRESHOLD or tier == "WARM":
        if key not in _pool["hot"]:
            was_warm = key in _pool["warm"]
            _pool["warm"][key] = {"result": result, "consecutive_low": 0}
            if not was_warm:
                reason_str = f"Added to WARM ({strat}): Coiling compression setup with score {new_score:.1f} (>= {WARM_THRESHOLD})"
                record_breakout_transition(
                    ticker=ticker,
                    event_type="ADDED_WARM",
                    from_tier="COLD",
                    to_tier="WARM",
                    score_before=None,
                    score_after=new_score,
                    price=cur_p,
                    trigger_price=trig_p,
                    target_price=result.get("target_price"),
                    stop_loss=result.get("stop_loss"),
                    risk_reward_ratio=result.get("risk_reward_ratio"),
                    volume_ratio=vol_r,
                    reason=reason_str,
                    catalyst_impact=cat_headline,
                    company_name=result.get("company_name"),
                    strategy=strat,
                    settings=settings,
                )


def _demote_hot(ticker: str, settings: Settings | None = None) -> None:
    """Demote a Hot ticker: increment consecutive_low, remove after 2 strikes with audit log."""
    settings = settings or Settings()
    key = ticker if "::" in ticker else _pool_key(ticker)
    entry = _pool["hot"].get(key)
    if not entry:
        for k, v in _pool["hot"].items():
            if k.startswith(f"{ticker}::"):
                key = k
                entry = v
                break
    if not entry:
        return
    entry["consecutive_low"] += 1
    result = entry.get("result", {})
    parts = key.split("::")
    t_clean = result.get("ticker", parts[0])
    strat = result.get("strategy") or (parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL")
    is_invalid_fno = strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(t_clean)

    if entry["consecutive_low"] >= 2 or is_invalid_fno:
        score = result.get("composite_score", 0)
        cur_p = result.get("current_price") or result.get("signal_price")
        trig_p = result.get("breakout_trigger")
        del _pool["hot"][key]

        if score >= WARM_THRESHOLD and not is_invalid_fno:
            _pool["warm"][key] = {"result": result, "consecutive_low": 0}
            record_breakout_transition(
                ticker=t_clean,
                event_type="DEMOTED_WARM",
                from_tier="HOT",
                to_tier="WARM",
                score_before=score,
                score_after=score,
                price=cur_p,
                trigger_price=trig_p,
                reason=f"Demoted HOT ➔ WARM: Score dropped to {score:.1f} (< {HOT_DEMOTION_THRESHOLD}) for 2 consecutive scan cycles",
                strategy=strat,
                settings=settings,
            )
            logger.debug("[BREAKOUT] %s demoted Hot → Warm (score %.1f)", key, score)
        else:
            reason = (
                f"Removed non-F&O ticker {t_clean} from NSE_FO_CALL_WALL strategy"
                if is_invalid_fno
                else f"Removed from Breakout Radar: Score fell to {score:.1f} below minimum setup criteria"
            )
            record_breakout_transition(
                ticker=t_clean,
                event_type="REMOVED_COLD",
                from_tier="HOT",
                to_tier="COLD",
                score_before=score,
                score_after=score,
                price=cur_p,
                trigger_price=trig_p,
                reason=reason,
                strategy=strat,
                settings=settings,
            )
            logger.debug("[BREAKOUT] %s demoted Hot → Cold (score %.1f)", key, score)
            try:
                conn = get_db_connection(settings)
                conn.execute("DELETE FROM breakout_radar WHERE ticker = ? AND (strategy = ? OR strategy IS NULL)", (t_clean, strat))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.debug("[BREAKOUT-DB] Error removing cold ticker %s from breakout_radar: %s", t_clean, e)


def _demote_warm(ticker: str, settings: Settings | None = None) -> None:
    """Demote a Warm ticker: increment consecutive_low, remove after 2 strikes (or immediate if non-F&O)."""
    settings = settings or Settings()
    key = ticker if "::" in ticker else _pool_key(ticker)
    entry = _pool["warm"].get(key)
    if not entry:
        for k, v in _pool["warm"].items():
            if k.startswith(f"{ticker}::"):
                key = k
                entry = v
                break
    if not entry:
        return
    entry["consecutive_low"] += 1
    result = entry.get("result", {})
    parts = key.split("::")
    t_clean = result.get("ticker", parts[0])
    strat = result.get("strategy") or (parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL")
    is_invalid_fno = strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(t_clean)

    if entry["consecutive_low"] >= 2 or is_invalid_fno:
        score = result.get("composite_score", 0)
        cur_p = result.get("current_price") or result.get("signal_price")
        trig_p = result.get("breakout_trigger")
        reason = (
            f"Removed non-F&O ticker {t_clean} from NSE_FO_CALL_WALL strategy"
            if is_invalid_fno
            else f"Removed from Warm Pool: Score dropped to {score:.1f} (< {WARM_DEMOTION_THRESHOLD}) for 2 consecutive cycles"
        )
        record_breakout_transition(
            ticker=t_clean,
            event_type="REMOVED_COLD",
            from_tier="WARM",
            to_tier="COLD",
            score_before=score,
            score_after=score,
            price=cur_p,
            trigger_price=trig_p,
            reason=reason,
            strategy=strat,
            settings=settings,
        )
        logger.debug("[BREAKOUT] %s demoted Warm → Cold (score %.1f)", key, score)
        del _pool["warm"][key]
        try:
            conn = get_db_connection(settings)
            conn.execute("DELETE FROM breakout_radar WHERE ticker = ? AND (strategy = ? OR strategy IS NULL)", (t_clean, strat))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("[BREAKOUT-DB] Error removing cold ticker %s from breakout_radar: %s", t_clean, e)
