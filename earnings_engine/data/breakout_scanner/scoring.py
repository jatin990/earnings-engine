"""Composite Breakout Scoring and Multi-Model AI Reasoning."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner.constants import (
    BREAKOUT_STRATEGIES,
    HOT_THRESHOLD,
    WARM_THRESHOLD,
)
from earnings_engine.data.breakout_scanner.indicators import _calc_atr_pct
from earnings_engine.data.breakout_scanner.state import _AI_REASONING_CACHE
from earnings_engine.data.breakout_scanner.strategies import (
    _score_classic_technical,
    _score_donchian_squeeze,
    _score_fo_call_wall,
    _score_nse_delivery_absorption,
    _score_volume_profile_vah,
)
from earnings_engine.data.universe import is_fno_eligible

logger = logging.getLogger(__name__)


def _should_be_hot(result: dict[str, Any]) -> bool:
    """Evaluate whether candidate meets elite HOT momentum thresholds."""
    if not result:
        return False
    score = result.get("composite_score", 0)
    if score >= HOT_THRESHOLD:
        return True
    mom_signal = str(result.get("momentum_signal") or "")
    mom_score = result.get("momentum_score", 0)
    pct_from_high = result.get("pct_from_high", -99.0)
    vol_ratio = result.get("volume_ratio", 0.0)
    vol_score = result.get("volume_score", 0.0)
    breakout_fired = bool(result.get("breakout_fired", False))

    if score >= 50 and breakout_fired:
        return True
    if score >= 52 and (mom_signal == "Strong" or mom_score >= 14) and pct_from_high >= -3.0:
        return True
    if score >= 50 and vol_ratio >= 1.5 and vol_score >= 12 and pct_from_high >= -4.0:
        return True
    return False


def score_breakout(
    ticker: str,
    prices_df: pd.DataFrame,
    quality_scores: list[float | None] | None = None,
    asof_date: str | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Score a single ticker point-in-time using any of the 5 specialized Breakout Strategies."""
    if prices_df is None or prices_df.empty:
        return None

    df = prices_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass

    df = df.sort_index()

    # Strict Point-in-time slicing
    if asof_date:
        asof_clean = str(asof_date).strip()[:10]
        hist_df = df.loc[df.index <= asof_clean]
        future_df = df.loc[df.index > asof_clean]
    else:
        hist_df = df
        future_df = pd.DataFrame()

    if hist_df.empty:
        return None

    closes = pd.to_numeric(hist_df["close"], errors="coerce").dropna()
    if len(closes) < 10:
        return None

    signal_date = str(hist_df.index[-1])[:10]
    signal_price = float(closes.iloc[-1])

    high_series = pd.to_numeric(hist_df["high"], errors="coerce") if "high" in hist_df.columns else closes
    low_series = pd.to_numeric(hist_df["low"], errors="coerce") if "low" in hist_df.columns else closes
    volumes = pd.to_numeric(hist_df["volume"], errors="coerce") if "volume" in hist_df.columns else pd.Series(1.0, index=closes.index)
    volumes.fillna(0, inplace=True)
    volumes = volumes.reindex(closes.index, fill_value=0)

    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    if strategy_clean not in BREAKOUT_STRATEGIES:
        strategy_clean = "CLASSIC_TECHNICAL"

    if strategy_clean == "NSE_FO_CALL_WALL" and not is_fno_eligible(ticker):
        logger.debug("[BREAKOUT:FNO_BYPASS] Skipping %s for NSE_FO_CALL_WALL; not F&O eligible", ticker)
        return None

    strat_meta = BREAKOUT_STRATEGIES[strategy_clean]

    # Execute Strategy-Specific Engine
    if strategy_clean == "NSE_DELIVERY_ABSORPTION":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_nse_delivery_absorption(
            ticker, closes, volumes, high_series, low_series, quality_scores or [], settings=settings
        )
    elif strategy_clean == "NSE_FO_CALL_WALL":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_fo_call_wall(
            ticker, closes, volumes, high_series, low_series, settings=settings
        )
    elif strategy_clean == "VOLUME_PROFILE_VAH":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_volume_profile_vah(
            closes, volumes, high_series, low_series, hist_df
        )
    elif strategy_clean == "DONCHIAN_TTM_SQUEEZE":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_donchian_squeeze(
            closes, volumes, high_series, low_series
        )
    else:  # CLASSIC_TECHNICAL
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_classic_technical(
            closes, volumes, high_series, quality_scores or []
        )

    # Current / Latest Market Data
    all_closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    current_price = float(all_closes.iloc[-1])
    current_date = str(df.index[-1])[:10]

    # Outcome Calculation (Did Breakout Happen?)
    if not future_df.empty and signal_date != current_date:
        f_highs = pd.to_numeric(future_df["high"], errors="coerce") if "high" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        f_lows = pd.to_numeric(future_df["low"], errors="coerce") if "low" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        post_high = float(f_highs.max()) if not f_highs.empty else signal_price
        post_low = float(f_lows.min()) if not f_lows.empty else signal_price

        realized_return_pct = round(((current_price - signal_price) / signal_price) * 100, 2)
        max_gain_pct = round(((post_high - signal_price) / signal_price) * 100, 2)
        days_elapsed = len(future_df)

        # Require a 0.15% confirmation buffer above trigger to confirm a real breach vs tick noise
        breakout_fired = bool(post_high >= breakout_trigger * 1.0015 or current_price >= breakout_trigger * 1.0015)

        if post_high >= target_price:
            breakout_happened = True
            outcome = "TARGET_HIT"
            outcome_label = f"Target Hit 🎯 (+{max_gain_pct}%)"
            outcome_badge = "emerald"
        elif breakout_fired:
            if post_low <= stop_loss or current_price <= stop_loss:
                breakout_happened = False
                outcome = "STOP_LOSS_HIT"
                outcome_label = f"Stop Hit 🛑 ({realized_return_pct:+0.1f}%)"
                outcome_badge = "rose"
            elif current_price >= signal_price:
                breakout_happened = True
                outcome = "BREAKOUT_SUCCEEDED"
                outcome_label = f"Breakout Succeeded ✅ ({realized_return_pct:+0.1f}%)"
                outcome_badge = "emerald"
            else:
                breakout_happened = False
                outcome = "BREAKOUT_RETRACED"
                outcome_label = f"Breakout Retraced ⚠️ ({realized_return_pct:+0.1f}%)"
                outcome_badge = "amber"
        elif post_low <= stop_loss or current_price <= stop_loss:
            breakout_happened = False
            outcome = "SETUP_FAILED"
            outcome_label = f"Setup Failed ❌ ({realized_return_pct:+0.1f}%)"
            outcome_badge = "rose"
        elif current_price >= signal_price:
            breakout_happened = False
            outcome = "COILING_IN_PROFIT"
            outcome_label = f"Coiling In Green 🟢 ({realized_return_pct:+0.1f}%)"
            outcome_badge = "emerald"
        else:
            breakout_happened = False
            outcome = "COILING_IN_RANGE"
            outcome_label = f"Coiling In Range 🗜️ ({realized_return_pct:+0.1f}%)"
            outcome_badge = "slate"
    else:
        breakout_fired = False
        breakout_happened = None
        outcome = "PENDING"
        realized_return_pct = None
        max_gain_pct = None
        days_elapsed = None
        post_high = None
        outcome_label = "Pending ⏳"
        outcome_badge = "slate"

    # One-liner narrative
    if outcome == "TARGET_HIT":
        one_liner = f"🎯 Target Hit: Reached peak ₹{post_high:,.2f} (+{max_gain_pct}%) in {days_elapsed}d; crossed trigger ₹{breakout_trigger:,.2f}."
    elif outcome == "BREAKOUT_SUCCEEDED":
        one_liner = f"🚀 Breakout Succeeded: Breached trigger ₹{breakout_trigger:,.2f}, currently holding gains at ₹{current_price:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "BREAKOUT_RETRACED":
        one_liner = f"⚠️ Breakout Retraced: Triggered breakout to peak ₹{post_high:,.2f} (+{max_gain_pct}%) but retraced to ₹{current_price:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "STOP_LOSS_HIT":
        one_liner = f"🛑 Stop Hit: Breached trigger but slipped below SL ₹{stop_loss:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "SETUP_FAILED":
        one_liner = f"❌ Setup Failed: Never crossed breakout trigger ₹{breakout_trigger:,.2f}; broke below SL ₹{stop_loss:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "COILING_IN_PROFIT":
        one_liner = f"🟢 Coiling Green: Trading above signal price at ₹{current_price:,.2f} ({realized_return_pct:+.1f}%), awaiting trigger breach at ₹{breakout_trigger:,.2f}."
    elif outcome == "COILING_IN_RANGE":
        one_liner = f"🗜️ Coiling In Range: Consolidating near ₹{current_price:,.2f} ({realized_return_pct:+.1f}%), holding above SL ₹{stop_loss:,.2f}."
    else:
        one_liner = f"⏳ Active Setup: Monitoring for resistance breach at ₹{breakout_trigger:,.2f} with SL at ₹{stop_loss:,.2f}."

    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0
    vol_expansion_str = f"{vol_ratio:.1f}x Vol" if not np.isnan(vol_ratio) else "1.0x Vol"
    is_vol_confirmed = bool(vol_ratio >= 1.5)
    is_fakeout_risk = bool(vol_ratio < 1.2 and (breakout_fired or current_price >= breakout_trigger * 0.98))

    if is_vol_confirmed:
        confirmation_badge = f"⭐ High-Conviction Vol ({vol_expansion_str})"
        confirmation_color = "#34d399"
    elif is_fakeout_risk:
        confirmation_badge = f"⚠️ Low Vol Warning ({vol_expansion_str})"
        confirmation_color = "#fbbf24"
    elif vol_ratio >= 1.2:
        confirmation_badge = f"🔊 {vol_expansion_str} Expansion"
        confirmation_color = "#38bdf8"
    else:
        confirmation_badge = f"📊 Normal Vol ({vol_expansion_str})"
        confirmation_color = "#94a3b8"

    # Enforce minimum 1.5 Risk-Reward Ratio
    downside_risk = max(0.01, signal_price - stop_loss)
    if (target_price - signal_price) < 1.5 * downside_risk:
        target_price = round(max(target_price, signal_price + 1.5 * downside_risk), 2)

    risk_reward_ratio = round((target_price - signal_price) / downside_risk, 2)
    notes["risk_reward_ratio"] = risk_reward_ratio

    # Institutional Flow
    inst_flow = {}
    try:
        from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
        act = get_stock_institutional_activity(ticker)
        if act:
            inst_flow = {
                "accumulation_score": act.get("accumulation_score"),
                "verdict": act.get("verdict"),
                "funds_in": act.get("funds_accumulating_count", 0),
                "funds_out": act.get("funds_selling_count", 0),
                "net_flow_cr": act.get("net_flow_cr", 0.0),
            }
    except Exception:
        pass

    pct_from_high = ((signal_price - breakout_trigger) / breakout_trigger) * 100 if breakout_trigger else 0.0
    atr_pct = _calc_atr_pct(closes, default=2.0)

    ideal_entry_price = notes.get("ideal_entry_price") or breakout_trigger
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(notes.get("is_late") if notes.get("is_late") is not None else (ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002)))
    entry_delay_pct = notes.get("entry_delay_pct") if notes.get("entry_delay_pct") is not None else (round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0)

    return {
        "ticker": ticker,
        "signal_date": signal_date,
        "signal_price": round(signal_price, 2),
        "predicted_value": round(signal_price, 2),
        "breakout_trigger": breakout_trigger,
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "risk_reward_ratio": risk_reward_ratio,
        "setup_archetype": archetype,
        "strategy": strategy_clean,
        "strategy_name": strat_meta["name"],
        "strategy_short_name": strat_meta["short_name"],
        "strategy_badge": strat_meta["badge"],
        "strategy_icon": strat_meta["icon"],
        "calculation_notes": notes,
        "institutional_flow": inst_flow,
        "current_price": round(current_price, 2),
        "current_date": current_date,
        "post_high": round(post_high, 2) if post_high is not None else round(signal_price, 2),
        "peak_price": round(post_high, 2) if post_high is not None else round(signal_price, 2),
        "peak_gain_pct": max_gain_pct,
        "realized_return_pct": realized_return_pct,
        "max_gain_pct": max_gain_pct,
        "breakout_happened": breakout_happened,
        "breakout_fired": breakout_fired,
        "outcome": outcome,
        "outcome_label": outcome_label,
        "outcome_badge": outcome_badge,
        "explanation_one_liner": one_liner,
        "what_happened_summary": one_liner,
        "confirmation_badge": confirmation_badge,
        "confirmation_color": confirmation_color,
        "vol_expansion_str": vol_expansion_str,
        "is_fakeout_risk": is_fakeout_risk,
        "is_vol_confirmed": is_vol_confirmed,
        "days_elapsed": days_elapsed,
        "composite_score": composite,
        "resistance_score": subscores["resistance_score"],
        "volume_score": subscores["volume_score"],
        "compression_score": subscores["compression_score"],
        "momentum_score": subscores["momentum_score"],
        "fundamental_score": subscores["fundamental_score"],
        "pct_from_high": round(pct_from_high, 2),
        "volume_ratio": round(vol_ratio, 2),
        "atr_pct": round(atr_pct, 2),
        "momentum_signal": "Strong" if subscores["momentum_score"] >= 15 else "Moderate",
        "tier": "HOT" if _should_be_hot({
            "composite_score": composite,
            "momentum_score": subscores["momentum_score"],
            "momentum_signal": "Strong" if subscores["momentum_score"] >= 15 else "Moderate",
            "pct_from_high": round(pct_from_high, 2),
            "volume_ratio": round(vol_ratio, 2),
            "volume_score": subscores["volume_score"],
            "breakout_fired": breakout_fired,
        }) else ("WARM" if composite >= WARM_THRESHOLD else "COLD"),
        "avg_quality_score": 8.0,
        "data_points": len(closes),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_breakout_ai_reasoning(
    ticker: str,
    model_name: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Generate multi-model AI reasoning for a breakout candidate using local Ollama models."""
    from earnings_engine.data.db import get_db_connection
    from earnings_engine.data.breakout_scanner.storage import _init_breakout_db

    sym = ticker.strip().upper()
    settings = settings or Settings()

    # Check in-memory cache
    cache_key = f"{sym}_{model_name or 'default'}"
    if cache_key in _AI_REASONING_CACHE:
        return _AI_REASONING_CACHE[cache_key]

    # Persistent DB Cache Check
    try:
        conn = get_db_connection(settings)
        try:
            cur = conn.execute(
                "SELECT data_json FROM breakout_radar WHERE ticker = ? ORDER BY composite_score DESC LIMIT 1",
                (sym,),
            )
            row = cur.fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                if "ai_reasoning" in data:
                    ai_data = data["ai_reasoning"]
                    gen_at = ai_data.get("generated_at")
                    if gen_at:
                        gen_dt = datetime.fromisoformat(gen_at)
                        if gen_dt.tzinfo is None:
                            gen_dt = gen_dt.replace(tzinfo=timezone.utc)
                        now_dt = datetime.now(timezone.utc)
                        if (now_dt - gen_dt).total_seconds() < 12 * 3600:
                            _AI_REASONING_CACHE[cache_key] = ai_data
                            return ai_data
        finally:
            conn.close()
    except Exception as e:
        logger.debug("[BREAKOUT-AI] DB cache read failed for %s: %s", sym, e)

    # Get scored candidate details
    from earnings_engine.data.prices import load_prices, load_price_metrics
    prices_df = load_prices(sym, settings)
    metrics = load_price_metrics(sym, settings) or {}
    company_name = metrics.get("company_name") or sym
    industry = metrics.get("industry") or metrics.get("sector") or "—"

    quality_scores = [
        float(metrics.get(k)) if metrics.get(k) is not None else None
        for k in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score")
    ]
    scored = score_breakout(sym, prices_df, quality_scores) or {}

    notes = scored.get("calculation_notes", {})
    target = scored.get("target_price", 0)
    stop = scored.get("stop_loss", 0)
    trigger = scored.get("breakout_trigger", 0)
    cur_p = scored.get("current_price", 0)
    score = scored.get("composite_score", 0)
    archetype = scored.get("setup_archetype", "Breakout Coil")

    prompt = f"""You are an elite quantitative trading analyst specializing in breakout pattern recognition and price action momentum.
Evaluate the following breakout setup for {sym} ({company_name}) and provide an institutional opinion.

### Setup Metrics:
- Ticker: {sym} | Industry: {industry}
- Setup Archetype: {archetype}
- Composite Breakout Score: {score}/100
- Current Price: ₹{cur_p}
- Breakout Trigger (Resistance): ₹{trigger} ({scored.get('pct_from_high', 0):+.1f}% from high)
- Upside Target Price: ₹{target}
- Invalidation Stop Loss: ₹{stop}
- Risk/Reward Ratio: {scored.get('risk_reward_ratio', 2.0)} : 1
- Volume Surge: {scored.get('volume_ratio', 1.0)}x of 20D average
- Price Compression (ATR %): {scored.get('atr_pct', 2.0)}%
- Momentum Signal: {scored.get('momentum_signal', 'Moderate')}
- Earnings Quality (1-9): {scored.get('avg_quality_score', 'N/A')}

### Instructions:
1. Explain whether this breakout has genuine institutional volume accumulation or fakeout/exhaustion risk.
2. Outline key execution game plan (Entry confirmation, trailing stop, target scaling).
3. Output strict JSON adhering to this schema:
{{
  "verdict": "HIGH_CONVICTION_BREAKOUT",
  "confidence_pct": 82,
  "model_used": "{model_name or 'Ollama'}",
  "accumulation_analysis": "2-3 sentences evaluating the volume surge and price coiling.",
  "fakeout_risk_assessment": "Key vulnerability or fakeout warning signs to monitor.",
  "execution_plan": "Specific entry trigger, stop loss discipline, and target level.",
  "key_reasons": ["Reason 1", "Reason 2", "Reason 3"]
}}
"""

    model_to_use = model_name or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    output_dict: dict[str, Any] | None = None

    # 1. Try Local Ollama
    try:
        import urllib.request
        data_payload = json.dumps({
            "model": model_to_use,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": 4096,
                "temperature": 0.3,
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ollama_host}/api/generate",
            data=data_payload,
            headers={"Content-Type": "application/json"},
        )
        timeout = 45 if "8b" in model_to_use.lower() or "deepseek" in model_to_use.lower() else 18
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_res = json.loads(resp.read().decode("utf-8"))
            resp_text = raw_res.get("response", "")
            m = re.search(r"\{[\s\S]*\}", resp_text)
            if m:
                output_dict = json.loads(m.group(0))
                output_dict["source"] = f"Local Ollama ({model_to_use})"
    except Exception as e:
        logger.debug("[BREAKOUT-AI] Local Ollama call (%s) failed/timed out: %s", model_to_use, e)

    # 2. Rule-based Institutional Fallback if local model unavailable
    if not output_dict:
        vol_r = scored.get("volume_ratio") or 1.0
        pct_h = scored.get("pct_from_high") or -3.0
        is_high_conviction = score >= 60 and vol_r >= 1.3 and pct_h >= -3.0

        verdict = "HIGH_CONVICTION_BREAKOUT" if is_high_conviction else ("POTENTIAL_BREAKOUT_COIL" if score >= 40 else "WATCHLIST_SETUP")
        conf = min(92, max(60, int(score * 0.9 + (vol_r * 5))))

        output_dict = {
            "verdict": verdict,
            "confidence_pct": conf,
            "model_used": "Institutional Quantitative Rule Engine",
            "source": "Quantitative Synthesis",
            "accumulation_analysis": (
                f"{sym} displays {vol_r:.2f}× volume surge alongside an ATR compression of {scored.get('atr_pct', 1.5):.2f}%, "
                f"indicating tight price energy coiled directly under key resistance at ₹{trigger:,.2f}."
            ),
            "fakeout_risk_assessment": (
                f"Watch for rejection at ₹{trigger:,.2f} on declining volume. Stop loss is strictly placed at ₹{stop:,.2f} "
                f"to protect capital against false breakouts."
            ),
            "execution_plan": (
                f"Enter on confirmed hourly close above ₹{trigger:,.2f}. Scale out 50% at initial target ₹{target:,.2f}, "
                f"and trail remaining position using 20D SMA."
            ),
            "key_reasons": [
                notes.get("resistance_reasoning", f"Within {pct_h:+.1f}% of key resistance high"),
                notes.get("volume_reasoning", f"{vol_r:.2f}x volume surge confirming buyer interest"),
                notes.get("compression_reasoning", "ATR squeeze signaling high potential energy release"),
            ],
        }

    output_dict["ticker"] = sym
    output_dict["company_name"] = company_name
    output_dict["score"] = score
    output_dict["archetype"] = archetype
    output_dict["trigger"] = trigger
    output_dict["target"] = target
    output_dict["stop_loss"] = stop
    output_dict["risk_reward_ratio"] = scored.get("risk_reward_ratio", 2.0)
    output_dict["calculation_notes"] = notes
    output_dict["generated_at"] = datetime.now(timezone.utc).isoformat()

    _AI_REASONING_CACHE[cache_key] = output_dict

    # Store in DB to prevent token/compute waste on restart
    try:
        conn = get_db_connection(settings)
        try:
            _init_breakout_db(conn)
            cur = conn.execute(
                "SELECT data_json FROM breakout_radar WHERE ticker = ? ORDER BY composite_score DESC LIMIT 1",
                (sym,),
            )
            row = cur.fetchone()
            if row is not None:
                data = json.loads(row[0]) if row[0] else {}
                data["ai_reasoning"] = output_dict
                new_json = json.dumps(data)
                conn.execute("UPDATE breakout_radar SET data_json = ? WHERE ticker = ?", (new_json, sym))
                conn.commit()
            else:
                new_json = json.dumps({"ai_reasoning": output_dict})
                conn.execute(
                    "INSERT INTO breakout_radar (ticker, strategy, tier, data_json) VALUES (?, 'CLASSIC_TECHNICAL', 'WARM', ?)",
                    (sym, new_json),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug("[BREAKOUT-AI] DB cache write failed for %s: %s", sym, e)

    return output_dict


def _score_single_ticker(
    ticker: str,
    settings: Settings,
    asof_date: str | None = None,
    use_live_quote: bool = False,
    strategy: str = "CLASSIC_TECHNICAL",
    prices_df: pd.DataFrame | None = None,
    metrics: dict[str, Any] | None = None,
    catalysts: list[dict[str, Any]] | None = None,
    macro_info: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Load prices, metrics, news catalysts, and score a single ticker. Returns result dict or None."""
    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    if strategy_clean == "NSE_FO_CALL_WALL" and not is_fno_eligible(ticker):
        return None

    try:
        from earnings_engine.data.prices import load_prices, load_price_metrics, fetch_live_quote

        if prices_df is None:
            prices_df = load_prices(ticker, settings)
        if prices_df is None or prices_df.empty:
            return None

        # 1. Live Price integration for Hot stocks / on-demand re-eval
        if use_live_quote and not asof_date:
            try:
                prices_df = prices_df.copy()
                live_q = fetch_live_quote(ticker, settings, sync_db=True)
                if live_q and live_q.get("current_price"):
                    live_price = float(live_q["current_price"])
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    if not prices_df.empty:
                        last_idx_str = str(prices_df.index[-1])[:10]
                        if last_idx_str == today_str:
                            prices_df.loc[prices_df.index[-1], "close"] = live_price
                            if live_q.get("volume"):
                                prices_df.loc[prices_df.index[-1], "volume"] = float(live_q["volume"])
                        else:
                            new_row = pd.DataFrame(
                                {
                                    "open": [float(live_q.get("open") or live_price)],
                                    "high": [max(live_price, float(live_q.get("high") or live_price))],
                                    "low": [min(live_price, float(live_q.get("low") or live_price))],
                                    "close": [live_price],
                                    "volume": [float(live_q.get("volume") or 0)],
                                },
                                index=pd.to_datetime([today_str]),
                            )
                            prices_df = pd.concat([prices_df, new_row])
            except Exception as e:
                logger.debug("[BREAKOUT-LIVE] Live quote fetch skipped for %s: %s", ticker, e)

        if metrics is None:
            metrics = load_price_metrics(ticker, settings) or {}
        quality_scores: list[float | None] = []
        for key in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score"):
            v = metrics.get(key)
            if v is not None:
                try:
                    quality_scores.append(float(v))
                except (TypeError, ValueError):
                    quality_scores.append(None)
            else:
                quality_scores.append(None)

        result = score_breakout(ticker, prices_df, quality_scores, asof_date=asof_date, strategy=strategy, settings=settings)
        if result:
            result["company_name"] = metrics.get("company_name") or ticker
            result["market_cap_cr"] = metrics.get("market_cap_cr") or metrics.get("market_cap")
            result["industry"] = metrics.get("industry") or metrics.get("sector") or "—"

            # 2. News Catalyst Integration from pooled news database
            if not asof_date:
                try:
                    if catalysts is None:
                        from earnings_engine.data.catalysts_news import get_recent_catalysts
                        cats = get_recent_catalysts(ticker, limit=3, settings=settings)
                    else:
                        cats = catalysts
                    if cats:
                        top_cat = cats[0]
                        direction = str(top_cat.get("direction") or "NEUTRAL").upper()
                        impact = float(top_cat.get("impact_score") or 50)
                        title = str(top_cat.get("title") or "")
                        result["latest_news"] = {
                            "title": title,
                            "direction": direction,
                            "impact_score": impact,
                            "impact_level": top_cat.get("impact_level", "MEDIUM"),
                            "published_at": top_cat.get("published_at"),
                            "category": top_cat.get("category", "General"),
                        }
                        news_bonus = 0.0
                        if direction == "BULLISH" and impact >= 60:
                            news_bonus = min(10.0, round((impact - 50) / 50 * 10, 1))
                        elif direction == "BEARISH" and impact >= 65:
                            news_bonus = -min(15.0, round((impact - 50) / 50 * 15, 1))

                        if news_bonus != 0.0:
                            result["news_bonus"] = news_bonus
                            result["composite_score"] = max(0.0, min(100.0, round(result["composite_score"] + news_bonus, 1)))
                            cat_tag = "🚀 Bullish" if news_bonus > 0 else "⚠️ Bearish"
                            result.setdefault("reasoning", []).append(
                                f"{cat_tag} News Catalyst ({impact:.0f}% impact, {news_bonus:+.1f} pts): {title[:75]}..."
                            )
                except Exception as e:
                    logger.debug("[BREAKOUT-NEWS] Catalyst integration error for %s: %s", ticker, e)

            # 3. Macro Market Conditions & Volatility Regime Weighting
            if not asof_date:
                try:
                    if macro_info is None:
                        from earnings_engine.data.cross_strategy import compute_market_regime_multiplier
                        macro_data = compute_market_regime_multiplier(settings)
                    else:
                        macro_data = macro_info
                    b_mult = float(macro_data.get("breakout_multiplier", 1.0))
                    m_score = float(macro_data.get("macro_score", 8.0))
                    m_pill = str(macro_data.get("macro_pill", "🟡 Neutral"))
                    m_bias = str(macro_data.get("macro_bias", "RANGEBOUND_NEUTRAL"))

                    raw_score = float(result.get("composite_score", 0.0))
                    adjusted_score = max(0.0, min(100.0, round(raw_score * b_mult, 1)))
                    macro_delta = round(adjusted_score - raw_score, 1)

                    result["composite_score"] = adjusted_score
                    result["macro_regime"] = {
                        "bias": m_bias,
                        "multiplier": b_mult,
                        "score": m_score,
                        "delta": macro_delta,
                        "pill": m_pill,
                        "fear_greed_score": macro_data.get("fear_greed_score"),
                        "vix_level": macro_data.get("vix_level"),
                    }
                    if macro_delta != 0.0:
                        tag = "Tailwind" if macro_delta > 0 else "Headwind"
                        result.setdefault("reasoning", []).append(
                            f"🌐 Macro Market {tag} ({b_mult:.2f}x mult, {macro_delta:+.1f} pts): {m_pill}"
                        )
                except Exception as e:
                    logger.debug("[BREAKOUT-MACRO] Macro weighting error for %s: %s", ticker, e)

        return result
    except Exception as e:
        logger.debug("[BREAKOUT] Error scoring %s: %s", ticker, e)
    return None
