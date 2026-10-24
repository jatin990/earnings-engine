"""Quantitative scanner for earnings results breakout setups.

Evaluates stocks reporting results in a configurable window [-past_days, +future_days]
relative to today, computing Result-Day High (RDH), Result-Day Low (RDL), reaction %,
volume ratios, setup archetypes, and composite conviction scores.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.analysis.volume_polarity import classify_volume_polarity, get_stock_oi_delta
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.earnings import _connect as _earnings_connect
from earnings_engine.data.industry import get_industry_map
from earnings_engine.data.names import get_names_batch
from earnings_engine.data.universe import get_universe

logger = logging.getLogger("earnings_engine.data.earnings_breakout_scanner")

VALID_ARCHETYPES = {
    "ALL",
    "RDH_EXPANSION",
    "PEAD_MOMENTUM",
    "PRE_EARNINGS_COIL",
    "POST_RESULT_RECOVERY",
}

ARCHETYPE_METADATA = {
    "RDH_EXPANSION": {
        "label": "RDH Expansion",
        "badge": "RDH Breakout",
        "desc": "Testing or breaking above the Result-Day High candle on elevated volume.",
    },
    "PEAD_MOMENTUM": {
        "label": "PEAD Drift",
        "badge": "PEAD Momentum",
        "desc": "Post-Earnings Announcement Drift continuation on positive earnings catalyst.",
    },
    "PRE_EARNINGS_COIL": {
        "label": "Pre-Earnings Coil",
        "badge": "Pre-Earnings Coil",
        "desc": "Consolidating within striking distance of resistance directly ahead of earnings.",
    },
    "POST_RESULT_RECOVERY": {
        "label": "Post-Result Recovery",
        "badge": "Dip Absorption",
        "desc": "Knee-jerk dip absorbed, reclaiming the pre-result pivot level.",
    },
}


def _calc_atr(df: pd.DataFrame, period: int = 14) -> float | None:
    """Calculate average true range over given period."""
    if df is None or len(df) < 2 or "high" not in df.columns or "low" not in df.columns or "close" not in df.columns:
        return None
    try:
        high = pd.to_numeric(df["high"], errors="coerce")
        low = pd.to_numeric(df["low"], errors="coerce")
        close = pd.to_numeric(df["close"], errors="coerce")
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        tr = tr.dropna()
        if len(tr) == 0:
            return None
        atr_series = tr.rolling(window=min(period, len(tr)), min_periods=1).mean()
        val = float(atr_series.iloc[-1])
        return val if not math.isnan(val) and val > 0 else None
    except Exception:
        return None


def _calc_composite_score(
    pct_from_trigger: float,
    volume_ratio: float | None,
    surprise_pct: float | None,
    atr_pct: float | None,
    reaction_retention_pct: float | None,
    is_declared: bool,
    is_breaking_out: bool,
) -> int:
    """Compute 0-100 composite score for results breakout setup."""
    score = 0.0

    # 1. Resistance & Trigger Proximity (0-30 pts)
    # 0% to +1% -> 30 pts (ideal breakout window)
    # -1% -> 26 pts, -2% -> 22 pts, -3% -> 18 pts, -5% -> 10 pts, < -8% -> 0 pts
    if is_breaking_out or pct_from_trigger >= 0:
        if pct_from_trigger <= 1.5:
            score += 30.0
        elif pct_from_trigger <= 3.5:
            score += 26.0
        else:
            # Overextended breakout
            score += max(15.0, 25.0 - (pct_from_trigger - 3.5) * 2.0)
    else:
        dist = abs(pct_from_trigger)
        if dist <= 0.75:
            score += 28.0
        elif dist <= 1.5:
            score += 24.0
        elif dist <= 3.0:
            score += 18.0
        elif dist <= 5.0:
            score += 10.0
        elif dist <= 8.0:
            score += 5.0

    # 2. Volume Surge (0-25 pts)
    vr = volume_ratio or 1.0
    if vr >= 2.5:
        score += 25.0
    elif vr >= 2.0:
        score += 21.0
    elif vr >= 1.5:
        score += 17.0
    elif vr >= 1.2:
        score += 12.0
    elif vr >= 1.0:
        score += 6.0

    # 3. Earnings Quality & Surprise (0-20 pts)
    sp = surprise_pct if surprise_pct is not None and not math.isnan(surprise_pct) else None
    if sp is not None:
        if sp >= 10.0:
            score += 20.0
        elif sp >= 5.0:
            score += 16.0
        elif sp > 0.0:
            score += 12.0
        elif sp >= -3.0:
            score += 6.0
    else:
        # Neutral if surprise not reported yet
        score += 10.0 if not is_declared else 7.0

    # 4. Volatility Coiling & ATR Squeeze (0-15 pts)
    # Lower ATR% means tighter coil ready for expansion
    if atr_pct is not None and atr_pct > 0:
        if atr_pct <= 1.5:
            score += 15.0
        elif atr_pct <= 2.2:
            score += 12.0
        elif atr_pct <= 3.2:
            score += 8.0
        elif atr_pct <= 4.5:
            score += 4.0
    else:
        score += 8.0

    # 5. Reaction Day Retention / Trend Alignment (0-10 pts)
    rr = reaction_retention_pct if reaction_retention_pct is not None and not math.isnan(reaction_retention_pct) else 0.0
    if rr >= 3.0:
        score += 10.0
    elif rr >= 1.0:
        score += 7.0
    elif rr >= 0.0:
        score += 5.0
    elif rr >= -2.0:
        score += 2.0

    return int(min(100, max(0, round(score))))


def get_results_breakout_candidates(
    settings: Settings | None = None,
    past_days: int = 3,
    future_days: int = 7,
    archetype: str = "ALL",
    min_score: int = 30,
    universe: str = "all",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Scan and compute dedicated results breakout setups within [-past_days, +future_days]."""
    settings = settings or Settings()
    if now is None:
        now = datetime.now()
    today = now.date()

    past_days = max(0, min(30, int(past_days)))
    future_days = max(0, min(30, int(future_days)))
    min_score = max(0, min(100, int(min_score)))
    archetype_upper = (archetype or "ALL").strip().upper()

    start_date = (today - timedelta(days=past_days)).isoformat()
    end_date = (today + timedelta(days=future_days)).isoformat()

    # 1. Query matching earnings events
    eligible_universe_tickers = set(get_universe(universe, settings)) if universe and universe.lower() != "all" else None

    earnings_events: list[dict[str, Any]] = []
    try:
        with _earnings_connect(settings) as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(earnings_history)").fetchall()}
            has_eps_est = "eps_estimate" in cols
            has_eps_rep = "eps_reported" in cols
            has_surprise = "surprise_pct" in cols
            has_source = "source" in cols

            select_fields = ["ticker", "earnings_date"]
            if has_eps_est:
                select_fields.append("eps_estimate")
            if has_eps_rep:
                select_fields.append("eps_reported")
            if has_surprise:
                select_fields.append("surprise_pct")
            if has_source:
                select_fields.append("source")

            sql = f"SELECT {', '.join(select_fields)} FROM earnings_history WHERE earnings_date >= ? AND earnings_date <= ? ORDER BY earnings_date ASC"
            rows = conn.execute(sql, (start_date, end_date)).fetchall()

            seen: dict[tuple[str, str], dict[str, Any]] = {}
            for r in rows:
                t = r[0]
                d = r[1]
                if eligible_universe_tickers is not None and t not in eligible_universe_tickers:
                    continue

                idx = 2
                eps_est = r[idx] if has_eps_est and len(r) > idx else None
                if has_eps_est:
                    idx += 1
                eps_rep = r[idx] if has_eps_rep and len(r) > idx else None
                if has_eps_rep:
                    idx += 1
                surp = r[idx] if has_surprise and len(r) > idx else None
                if has_surprise:
                    idx += 1
                src = r[idx] if has_source and len(r) > idx else "yfinance"

                key = (t, d)
                # Prioritize entries with reported EPS or from nse
                if key not in seen or (eps_rep is not None and seen[key].get("eps_reported") is None):
                    seen[key] = {
                        "ticker": t,
                        "earnings_date": d,
                        "eps_estimate": eps_est,
                        "eps_reported": eps_rep,
                        "surprise_pct": surp,
                        "source": src,
                    }
            earnings_events = list(seen.values())
    except Exception as e:
        logger.error("Error querying earnings history for results radar: %s", e)
        earnings_events = []

    if not earnings_events:
        return {
            "status": "ok",
            "window": {
                "past_days": past_days,
                "future_days": future_days,
                "start_date": start_date,
                "end_date": end_date,
                "asof_date": today.isoformat(),
            },
            "total_candidates": 0,
            "summary": {
                "declared_count": 0,
                "upcoming_count": 0,
                "breaking_out_count": 0,
                "archetype_counts": {k: 0 for k in ARCHETYPE_METADATA},
            },
            "items": [],
        }

    # 2. Batch load prices and company metadata
    unique_tickers = sorted({e["ticker"] for e in earnings_events})
    price_map: dict[str, pd.DataFrame] = prices_mod.load_prices_batch(unique_tickers, settings)
    industry_map = get_industry_map(unique_tickers, settings)
    names_map = get_names_batch(unique_tickers, settings)

    items: list[dict[str, Any]] = []
    archetype_counts = {k: 0 for k in ARCHETYPE_METADATA}
    declared_count = 0
    upcoming_count = 0
    breaking_out_count = 0

    for ev in earnings_events:
        ticker = ev["ticker"]
        edate_str = ev["earnings_date"]
        try:
            edate_obj = date.fromisoformat(edate_str)
        except Exception:
            continue

        days_rel = (edate_obj - today).days
        is_declared = days_rel <= 0

        if is_declared:
            timing_status = "DECLARED"
            if days_rel == 0:
                relative_days_label = "Declared Today"
            elif days_rel == -1:
                relative_days_label = "Declared Yesterday"
            else:
                relative_days_label = f"Declared {abs(days_rel)}D ago"
        else:
            timing_status = "UPCOMING"
            if days_rel == 1:
                relative_days_label = "Upcoming Tomorrow"
            else:
                relative_days_label = f"Upcoming in {days_rel}D"

        prices = price_map.get(ticker)
        if prices is None or prices.empty or "close" not in prices.columns:
            continue

        closes = pd.to_numeric(prices["close"], errors="coerce").dropna()
        if len(closes) < 2:
            continue

        highs = pd.to_numeric(prices["high"], errors="coerce").dropna() if "high" in prices.columns else closes
        lows = pd.to_numeric(prices["low"], errors="coerce").dropna() if "low" in prices.columns else closes
        opens = pd.to_numeric(prices["open"], errors="coerce").dropna() if "open" in prices.columns else closes
        vols = pd.to_numeric(prices["volume"], errors="coerce").dropna() if "volume" in prices.columns else pd.Series(dtype=float)

        current_price = float(closes.iloc[-1])
        if current_price <= 0:
            continue

        # 20D baseline metrics
        window_20 = closes.tail(20)
        high_20d = float(highs.tail(20).max()) if not highs.empty else current_price
        high_52w = float(highs.tail(252).max()) if not highs.empty else high_20d
        sma_20 = float(window_20.mean()) if not window_20.empty else current_price

        # Volume ratio
        vol_20_avg = float(vols.tail(20).mean()) if not vols.empty and len(vols) >= 5 else None
        current_vol = float(vols.iloc[-1]) if not vols.empty else None
        volume_ratio = round(current_vol / vol_20_avg, 2) if vol_20_avg and vol_20_avg > 0 and current_vol is not None else 1.0

        # ATR
        atr_val = _calc_atr(prices, 14)
        atr_pct = round((atr_val / current_price) * 100, 2) if atr_val and current_price > 0 else 2.0
        if atr_val is None or atr_val <= 0:
            atr_val = round(current_price * 0.02, 2)

        # Result structure calculation
        edate_ts = pd.Timestamp(edate_str)
        before_closes = closes[closes.index < edate_ts]
        pre_result_close = float(before_closes.iloc[-1]) if not before_closes.empty else float(closes.iloc[0])

        result_day_high = None
        result_day_low = None
        reaction_gap_pct = None
        reaction_return_pct = None
        intraday_recovery_pct = None
        post_high_move_pct = None
        pullback_from_high_pct = None

        if is_declared:
            # Result day candle
            result_day_bars = prices[prices.index >= edate_ts]
            if not result_day_bars.empty:
                rd_row = result_day_bars.iloc[0]
                rd_high = float(rd_row.get("high", rd_row.get("close", current_price)))
                rd_low = float(rd_row.get("low", rd_row.get("close", current_price)))
                rd_open = float(rd_row.get("open", rd_row.get("close", current_price)))
                rd_close = float(rd_row.get("close", current_price))

                result_day_high = round(rd_high, 2)
                result_day_low = round(rd_low, 2)

                if pre_result_close > 0:
                    reaction_gap_pct = round(((rd_open - pre_result_close) / pre_result_close) * 100, 2)
                    reaction_return_pct = round(((rd_close - pre_result_close) / pre_result_close) * 100, 2)

                if rd_low > 0:
                    intraday_recovery_pct = round(((rd_close - rd_low) / rd_low) * 100, 2)

                # Subsequent price move post-result
                post_closes = closes[closes.index >= edate_ts]
                if not post_closes.empty:
                    post_max_close = float(post_closes.max())
                    if pre_result_close > 0:
                        post_high_move_pct = round(((post_max_close - pre_result_close) / pre_result_close) * 100, 2)
                    if post_max_close > 0:
                        pullback_from_high_pct = round(((current_price - post_max_close) / post_max_close) * 100, 2)

        # Classify Setup Archetype & Determine Breakout Trigger Level
        selected_archetype = "PRE_EARNINGS_COIL"
        breakout_trigger = high_20d
        trigger_label = "20D High"

        if is_declared:
            rdh = result_day_high or high_20d
            # 1. Post-Result Recovery: Knee-jerk gap down reclaimed
            if reaction_gap_pct is not None and reaction_gap_pct < -1.5 and current_price >= pre_result_close:
                selected_archetype = "POST_RESULT_RECOVERY"
                breakout_trigger = round(pre_result_close, 2)
                trigger_label = f"Pre-Result Close ({pre_result_close:,.2f})"
            # 2. RDH Expansion: Challenging or breaking the Result-Day High candle
            elif current_price >= rdh * 0.975:
                selected_archetype = "RDH_EXPANSION"
                breakout_trigger = round(rdh, 2)
                trigger_label = f"RDH ({rdh:,.2f})"
            # 3. PEAD Momentum: Strong earnings reaction or surprise continuation
            elif (reaction_return_pct is not None and reaction_return_pct > 2.0) or (ev.get("surprise_pct") and ev["surprise_pct"] > 0):
                selected_archetype = "PEAD_MOMENTUM"
                breakout_trigger = round(high_20d, 2)
                trigger_label = f"20D High ({high_20d:,.2f})"
            else:
                selected_archetype = "RDH_EXPANSION"
                breakout_trigger = round(rdh, 2)
                trigger_label = f"RDH ({rdh:,.2f})"
        else:
            selected_archetype = "PRE_EARNINGS_COIL"
            breakout_trigger = round(max(high_20d, high_52w * 0.98 if high_52w else high_20d), 2)
            trigger_label = f"Resistance ({breakout_trigger:,.2f})"

        pct_from_trigger = round(((current_price - breakout_trigger) / breakout_trigger) * 100, 2) if breakout_trigger > 0 else 0.0
        is_breaking_out = current_price >= breakout_trigger

        # Momentum calculations
        mom_3d = round(float((current_price / closes.iloc[-4] - 1.0) * 100), 2) if len(closes) >= 4 else None
        mom_7d = round(float((current_price / closes.iloc[-8] - 1.0) * 100), 2) if len(closes) >= 8 else None

        # Squeeze indicator (Bollinger Band inside Keltner Channel)
        std_20 = float(window_20.std()) if len(window_20) >= 10 else None
        squeeze_on = bool(std_20 is not None and (2.0 * std_20) <= (1.5 * atr_val))

        composite_score = _calc_composite_score(
            pct_from_trigger=pct_from_trigger,
            volume_ratio=volume_ratio,
            surprise_pct=ev.get("surprise_pct"),
            atr_pct=atr_pct,
            reaction_retention_pct=reaction_return_pct if is_declared else mom_3d,
            is_declared=is_declared,
            is_breaking_out=is_breaking_out,
        )

        if composite_score < min_score:
            continue

        if archetype_upper != "ALL" and selected_archetype != archetype_upper:
            continue

        tier = "HOT" if composite_score >= 60 else "WARM"

        # Trade Levels
        ideal_entry = round(float(max(current_price, breakout_trigger * 1.002)), 2)
        target_1 = round(float(ideal_entry + 1.5 * atr_val), 2)
        target_2 = round(float(ideal_entry + 3.0 * atr_val), 2)
        target_price = target_1
        stop_loss = round(float(ideal_entry - 1.2 * atr_val), 2)
        risk = max(0.01, ideal_entry - stop_loss)
        reward = max(0.01, target_price - ideal_entry)
        rrr = round(float(reward / risk), 2)

        meta = ARCHETYPE_METADATA.get(selected_archetype, {
            "label": selected_archetype,
            "badge": selected_archetype,
            "desc": "",
        })

        if is_declared:
            declared_count += 1
        else:
            upcoming_count += 1
        if is_breaking_out:
            breaking_out_count += 1
        archetype_counts[selected_archetype] = archetype_counts.get(selected_archetype, 0) + 1

        company_name = names_map.get(ticker, ticker)
        industry = industry_map.get(ticker, "General")
        symbol = ticker[:-3] if ticker.endswith(".NS") else ticker

        # Directional Volume & F&O OI Polarity
        prev_close_bar = float(closes.iloc[-2]) if len(closes) >= 2 else None
        day_chg_pct = round(((current_price - prev_close_bar) / prev_close_bar) * 100.0, 2) if prev_close_bar and prev_close_bar > 0 else None
        latest_high = float(highs.iloc[-1]) if not highs.empty else current_price
        latest_low = float(lows.iloc[-1]) if not lows.empty else current_price
        latest_open = float(opens.iloc[-1]) if not opens.empty else current_price
        oi_delta_pct = get_stock_oi_delta(ticker)

        vol_polarity_meta = classify_volume_polarity(
            ticker=ticker,
            price_change_pct=day_chg_pct,
            volume_ratio=volume_ratio,
            close=current_price,
            high=latest_high,
            low=latest_low,
            open_price=latest_open,
            oi_change_pct=oi_delta_pct,
        )

        items.append({
            "ticker": ticker,
            "symbol": symbol,
            "company_name": company_name,
            "industry": industry,
            "market": "NSE" if ticker.endswith(".NS") else "US",
            "earnings_date": edate_str,
            "days_relative": int(days_rel),
            "days_since_result": int(days_rel),
            "timing_status": timing_status,
            "relative_days_label": relative_days_label,
            "is_declared": is_declared,
            "current_price": round(float(current_price), 2),
            "breakout_trigger": round(float(breakout_trigger), 2),
            "trigger_label": trigger_label,
            "pct_from_trigger": round(float(pct_from_trigger), 2),
            "dist_to_trigger_pct": round(float(pct_from_trigger), 2),
            "is_breaking_out": is_breaking_out,
            "volume_polarity": vol_polarity_meta["volume_polarity"],
            "volume_character": vol_polarity_meta["volume_character"],
            "oi_buildup": vol_polarity_meta["oi_buildup"],
            "oi_change_pct": vol_polarity_meta["oi_change_pct"],
            "is_fno": vol_polarity_meta["is_fno"],
            "target_1": target_1,
            "target_2": target_2,
            "stop_loss": stop_loss,
            "composite_score": int(composite_score),
            "tier": tier,
            "archetype": selected_archetype,
            "archetype_label": meta["label"],
            "archetype_badge": meta["badge"],
            "archetype_description": meta["desc"],
            "result_structure": {
                "pre_result_close": round(float(pre_result_close), 2) if pre_result_close else None,
                "pre_close": round(float(pre_result_close), 2) if pre_result_close else None,
                "result_day_high": round(float(result_day_high), 2) if result_day_high else None,
                "result_day_low": round(float(result_day_low), 2) if result_day_low else None,
                "reaction_day_gap_pct": round(float(reaction_gap_pct), 2) if reaction_gap_pct is not None else None,
                "reaction_day_return_pct": round(float(reaction_return_pct), 2) if reaction_return_pct is not None else None,
                "reaction_day_ret_pct": round(float(reaction_return_pct), 2) if reaction_return_pct is not None else None,
                "intraday_recovery_pct": round(float(intraday_recovery_pct), 2) if intraday_recovery_pct is not None else None,
                "post_high_move_pct": round(float(post_high_move_pct), 2) if post_high_move_pct is not None else None,
                "pullback_from_high_pct": round(float(pullback_from_high_pct), 2) if pullback_from_high_pct is not None else None,
            },
            "fundamentals": {
                "eps_reported": float(ev.get("eps_reported")) if ev.get("eps_reported") is not None else None,
                "eps_estimate": float(ev.get("eps_estimate")) if ev.get("eps_estimate") is not None else None,
                "surprise_pct": round(float(ev.get("surprise_pct")), 2) if ev.get("surprise_pct") is not None else None,
                "quality_score": 70 if ev.get("surprise_pct") and ev["surprise_pct"] > 0 else 50,
            },
            "technicals": {
                "volume_ratio": round(float(volume_ratio), 2),
                "volume_ratio_20d": round(float(volume_ratio), 2),
                "volume_polarity": vol_polarity_meta["volume_polarity"],
                "volume_character": vol_polarity_meta["volume_character"],
                "oi_buildup": vol_polarity_meta["oi_buildup"],
                "oi_change_pct": vol_polarity_meta["oi_change_pct"],
                "is_fno": vol_polarity_meta["is_fno"],
                "vol_badge_label": vol_polarity_meta["badge_label"],
                "vol_badge_color": vol_polarity_meta["badge_color"],
                "vol_badge_bg": vol_polarity_meta["badge_bg"],
                "vol_badge_border": vol_polarity_meta["badge_border"],
                "vol_tooltip": vol_polarity_meta["tooltip"],
                "atr_val": round(float(atr_val), 2),
                "atr_14d": round(float(atr_val), 2),
                "atr_pct": round(float(atr_pct), 2),
                "sma_20": round(float(sma_20), 2),
                "high_20d": round(float(high_20d), 2),
                "resistance_20d": round(float(high_20d), 2),
                "high_52w": round(float(high_52w), 2),
                "momentum_3d_pct": mom_3d,
                "momentum_7d_pct": mom_7d,
                "squeeze_on": squeeze_on,
            },
            "trade_levels": {
                "ideal_entry": ideal_entry,
                "suggested_entry": ideal_entry,
                "breakout_trigger": round(float(breakout_trigger), 2),
                "dist_to_trigger_pct": round(float(pct_from_trigger), 2),
                "target_price": target_price,
                "target_1": target_1,
                "target_2": target_2,
                "stop_loss": stop_loss,
                "risk_reward_ratio": rrr,
            },
        })

    # Sort descending by composite score, then proximity to trigger
    items.sort(key=lambda x: (x["composite_score"], -abs(x["pct_from_trigger"])), reverse=True)

    return {
        "status": "ok",
        "window": {
            "past_days": past_days,
            "future_days": future_days,
            "start_date": start_date,
            "end_date": end_date,
            "asof_date": today.isoformat(),
        },
        "total_candidates": len(items),
        "summary": {
            "total_candidates": len(items),
            "declared_count": declared_count,
            "declared_results": declared_count,
            "upcoming_count": upcoming_count,
            "upcoming_results": upcoming_count,
            "breaking_out_count": breaking_out_count,
            "hot_setups": sum(1 for x in items if x.get("composite_score", 0) >= 60),
            "top_score": items[0]["composite_score"] if items else None,
            "top_conviction_score": items[0]["composite_score"] if items else None,
            "archetype_counts": archetype_counts,
        },
        "items": items,
    }
