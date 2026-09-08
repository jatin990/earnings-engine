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
from earnings_engine.data.prices import fetch_prices, fetch_live_quote, load_prices
from earnings_engine.data.market_context import _week_high_low_around, detect_swing_range
from earnings_engine.data.swing_ranges import get_swing_range
from earnings_engine.data.catalysts_news import get_short_term_catalysts
from earnings_engine.consensus.storage import get_predictions
from earnings_engine.data.earnings import refresh_earnings_from_source

logger = logging.getLogger(__name__)


def get_stock_quote(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve fast live quote and profile metadata for a single ticker."""
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

    # 2. Quotes & Price Action (Live Authoritative Market Quote)
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
        "is_live": False,
        "last_updated": None,
    }

    # Fetch live quote and sync today's price bar with SQLite cache
    try:
        live_q = fetch_live_quote(sym, settings=settings, sync_db=True)
        if live_q.get("current_price"):
            quote.update(live_q)
            if live_q.get("market_cap") and not profile.get("market_cap"):
                profile["market_cap"] = float(live_q["market_cap"])
    except Exception as e:
        logger.debug("Error in fetch_live_quote for %s: %s", sym, e)

    # Load price history if needed
    prices_df = pd.DataFrame()
    try:
        prices_df = load_prices(sym, settings)
        if prices_df.empty:
            prices_df = fetch_prices(sym, settings, force=False)
    except Exception as e:
        logger.debug("Error fetching price history for %s: %s", sym, e)

    # Fallback to prices_df if live quote missed
    if not prices_df.empty and "close" in prices_df.columns:
        closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
        if not closes.empty:
            if quote.get("current_price") is None:
                quote["current_price"] = round(float(closes.iloc[-1]), 2)
                if len(closes) >= 2:
                    p_close = float(closes.iloc[-2])
                    quote["previous_close"] = round(p_close, 2)
                    quote["day_change"] = round(float(quote["current_price"] - p_close), 2)
                    quote["day_change_pct"] = round(float((quote["current_price"] / p_close - 1.0) * 100.0), 2)
            if quote.get("week_52_high") is None and len(closes) >= 20:
                quote["week_52_high"] = round(float(closes.tail(252).max()), 2)
            if quote.get("week_52_low") is None and len(closes) >= 20:
                quote["week_52_low"] = round(float(closes.tail(252).min()), 2)

        try:
            last_dt = prices_df.index[-1]
            first_dt = prices_df.index[0]
            quote["price_date"] = last_dt.strftime("%Y-%m-%d") if hasattr(last_dt, "strftime") else str(last_dt)[:10]
            if not quote.get("asof_date"):
                quote["asof_date"] = quote["price_date"]

            list_date_str = first_dt.strftime("%Y-%m-%d") if hasattr(first_dt, "strftime") else str(first_dt)[:10]
            profile["listing_date"] = list_date_str
            profile["first_traded_date"] = list_date_str
            profile["trading_days_count"] = len(prices_df)
            profile["is_new_listing"] = len(prices_df) < 60
            quote["listing_date"] = list_date_str
            quote["trading_days_count"] = len(prices_df)
            quote["is_new_listing"] = len(prices_df) < 60
        except Exception:
            pass

    if quote.get("current_price") and quote.get("week_52_high") and quote["week_52_high"] > 0:
        quote["pct_from_52w_high"] = round((quote["current_price"] / quote["week_52_high"] - 1.0) * 100.0, 2)
    if quote.get("current_price") and quote.get("week_52_low") and quote["week_52_low"] > 0:
        quote["pct_from_52w_low"] = round((quote["current_price"] / quote["week_52_low"] - 1.0) * 100.0, 2)

    return {
        "success": True,
        "ticker": sym,
        "profile": profile,
        "quote": quote,
    }


def get_stock_technicals(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Calculate technical swing structure, moving averages, and momentum metrics."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}

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
        "momentum_since_listing": None,
        "dma_20": None,
        "dma_50": None,
        "dma_200": None,
        "volume_ratio_5d_20d": None,
    }

    prices_df = pd.DataFrame()
    try:
        prices_df = load_prices(sym, settings)
        if prices_df.empty:
            prices_df = fetch_prices(sym, settings, force=False)
    except Exception as e:
        logger.debug("Error fetching price history for %s technicals: %s", sym, e)

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
            first_c = float(closes.iloc[0])
            if first_c > 0:
                technical["momentum_since_listing"] = round((latest_c / first_c - 1.0) * 100.0, 2)

            if len(closes) >= 4:
                p3 = float(closes.iloc[-4])
                technical["momentum_3d"] = round((latest_c / p3 - 1.0) * 100.0, 2) if p3 else None
            elif len(closes) >= 2:
                p_first = float(closes.iloc[0])
                technical["momentum_3d"] = round((latest_c / p_first - 1.0) * 100.0, 2) if p_first else None

            if len(closes) >= 8:
                p7 = float(closes.iloc[-8])
                technical["momentum_7d"] = round((latest_c / p7 - 1.0) * 100.0, 2) if p7 else None
            elif len(closes) >= 2:
                technical["momentum_7d"] = technical["momentum_since_listing"]

            if len(closes) >= 22:
                p30 = float(closes.iloc[-22])
                technical["momentum_30d"] = round((latest_c / p30 - 1.0) * 100.0, 2) if p30 else None
            elif len(closes) >= 2:
                technical["momentum_30d"] = technical["momentum_since_listing"]

            # DMA computation
            if len(closes) >= 20:
                technical["dma_20"] = round(float(closes.tail(20).mean()), 2)
            elif len(closes) >= 5:
                technical["dma_20"] = round(float(closes.mean()), 2)

            if len(closes) >= 50:
                technical["dma_50"] = round(float(closes.tail(50).mean()), 2)

            if len(closes) >= 200:
                technical["dma_200"] = round(float(closes.tail(200).mean()), 2)

            # Volume surge ratio 5d vs 20d
            if "volume" in prices_df.columns:
                vols = pd.to_numeric(prices_df["volume"], errors="coerce").dropna()
                if len(vols) >= 20:
                    avg5 = float(vols.tail(5).mean())
                    avg20 = float(vols.tail(20).mean())
                    if avg20 > 0:
                        technical["volume_ratio_5d_20d"] = round(avg5 / avg20, 2)
                elif len(vols) >= 2:
                    avg_all = float(vols.mean())
                    last_vol = float(vols.iloc[-1])
                    if avg_all > 0:
                        technical["volume_ratio_5d_20d"] = round(last_vol / avg_all, 2)

    # Stored swing range override if present
    stored_sr = get_swing_range("ALL", sym, settings)
    if stored_sr:
        technical["stored_swing_range"] = stored_sr
        if stored_sr.get("lower_bound"): technical["support_level"] = stored_sr["lower_bound"]
        if stored_sr.get("upper_bound"): technical["resistance_level"] = stored_sr["upper_bound"]

    return {
        "success": True,
        "ticker": sym,
        "technical": technical,
    }


def get_stock_earnings(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve 12-quarter earnings history, surprises, and post-earnings week moves."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}

    earnings_history: list[dict[str, Any]] = []
    prices_df = pd.DataFrame()
    try:
        prices_df = load_prices(sym, settings)
    except Exception:
        pass

    try:
        conn = get_db_connection(settings)
        e_rows = conn.execute(
            "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct, source FROM earnings_history WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 12",
            (sym,),
        ).fetchall()

        if not e_rows or all(r[2] is None for r in e_rows):
            try:
                from earnings_engine.data.earnings import fetch_earnings
                fetch_earnings(sym, settings=settings, force=True)
                e_rows = conn.execute(
                    "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct, source FROM earnings_history WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 12",
                    (sym,),
                ).fetchall()
            except Exception as src_err:
                logger.debug("Source earnings fetch in get_stock_earnings for %s: %s", sym, src_err)

        if not e_rows or all(r[2] is None for r in e_rows):
            try:
                calculate_or_fetch_eps(sym, settings=settings)
                e_rows = conn.execute(
                    "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct, source FROM earnings_history WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 12",
                    (sym,),
                ).fetchall()
            except Exception as auto_eps_err:
                logger.debug("Auto EPS hydration in get_stock_earnings for %s: %s", sym, auto_eps_err)

        # Get current live price / high / low for week HL calculations
        curr_price = None
        d_high = None
        d_low = None
        if not prices_df.empty and "close" in prices_df.columns:
            closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
            if not closes.empty:
                curr_price = float(closes.iloc[-1])
            if "high" in prices_df.columns:
                d_high = float(pd.to_numeric(prices_df["high"], errors="coerce").dropna().iloc[-1])
            if "low" in prices_df.columns:
                d_low = float(pd.to_numeric(prices_df["low"], errors="coerce").dropna().iloc[-1])

        for r in e_rows:
            ed_str = r[0]
            eps_est = float(r[1]) if r[1] is not None else None
            eps_rep = float(r[2]) if r[2] is not None else None
            surp = float(r[3]) if r[3] is not None else None
            source = str(r[4]) if len(r) > 4 and r[4] else "yfinance"

            week_hl = None
            if not prices_df.empty:
                week_hl = _week_high_low_around(
                    prices_df,
                    ed_str,
                    current_price=curr_price,
                    day_high=d_high,
                    day_low=d_low,
                )

            earnings_history.append({
                "earnings_date": ed_str,
                "eps_estimate": eps_est,
                "eps_reported": eps_rep,
                "surprise_pct": round(surp, 2) if surp is not None else None,
                "source": source,
                "week_high_pct": round(week_hl[0], 2) if week_hl else None,
                "week_low_pct": round(week_hl[1], 2) if week_hl else None,
                "week_high_price": round(week_hl[2], 2) if week_hl else None,
                "week_low_price": round(week_hl[3], 2) if week_hl else None,
                "high_date": pd.Timestamp(week_hl[4]).strftime("%b %d") if week_hl and week_hl[4] is not None else None,
                "low_date": pd.Timestamp(week_hl[5]).strftime("%b %d") if week_hl and week_hl[5] is not None else None,
            })
    except Exception as e:
        logger.debug("Error fetching earnings history for %s: %s", sym, e)

    # Compute beat streak
    streak = 0
    for e in earnings_history:
        if e.get("surprise_pct") is not None:
            if e["surprise_pct"] > 0:
                streak += 1
            else:
                break

    return {
        "success": True,
        "ticker": sym,
        "earnings_history": earnings_history,
        "streak": streak,
    }


def get_stock_consensus(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve multi-model AI consensus predictions and cached OmniRoute setups from the audit database."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}
    try:
        preds = get_predictions(settings, ticker=sym, limit=1)
        consensus_data = preds[0] if preds else None
        omniroute_setup = None
        if consensus_data:
            models_breakdown = consensus_data.get("models_breakdown") or []
            omniroute_model = next(
                (m for m in models_breakdown if "omniroute" in str(m.get("model_id", "")).lower() or "omniroute" in str(m.get("gateway", "")).lower() or "omniroute" in str(m.get("model_name", "")).lower()),
                None
            )
            as_of_p = consensus_data.get("as_of_price") or 0.0
            tgt_p = consensus_data.get("consensus_target_price") or (omniroute_model.get("target_price") if omniroute_model else None)
            sup_p = consensus_data.get("consensus_support") or (omniroute_model.get("support_level") if omniroute_model else None)
            res_p = consensus_data.get("consensus_resistance") or (omniroute_model.get("resistance_level") if omniroute_model else None)
            sl_p = (omniroute_model.get("stop_loss_price") if omniroute_model else None) or (round(sup_p * 0.98, 2) if sup_p else None)
            dir_val = (omniroute_model.get("direction") if omniroute_model else None) or consensus_data.get("consensus_direction", "BULLISH")
            conf_val = (omniroute_model.get("confidence_pct") if omniroute_model else None) or int(consensus_data.get("consensus_strength") or 80)
            rr_val = (omniroute_model.get("risk_reward_ratio") if omniroute_model else None) or 2.2
            floor_e = min(as_of_p, sup_p) if as_of_p and sup_p else (sup_p or as_of_p)
            entry_z = f"₹{floor_e:.2f} – ₹{as_of_p:.2f}" if as_of_p and floor_e else "—"

            omniroute_setup = {
                "ticker": sym,
                "as_of_price": as_of_p,
                "timeframe_days": consensus_data.get("timeframe_days", 14),
                "direction": dir_val,
                "confidence_pct": conf_val,
                "target_price": tgt_p,
                "support_level": sup_p,
                "resistance_level": res_p,
                "stop_loss_price": sl_p,
                "risk_reward_ratio": rr_val,
                "consensus_entry_zone": entry_z,
                "chart_pattern": (omniroute_model.get("chart_pattern") if omniroute_model else None) or "OmniRoute Multi-Model Dynamic Setup",
                "key_drivers": (omniroute_model.get("key_drivers") if omniroute_model else None) or ["Multi-factor consensus alignment", "Volume & momentum confirmation"],
                "primary_risk": (omniroute_model.get("primary_risk") if omniroute_model else None) or "Broader market index volatility",
                "synthesized_thesis": consensus_data.get("synthesized_thesis") or (omniroute_model.get("rationale_summary") if omniroute_model else "OmniRoute quantitative momentum alignment."),
                "recommended_action": (omniroute_model.get("recommended_action") if omniroute_model else None) or ("STRONG BUY" if dir_val == "BULLISH" and conf_val >= 80 else "ACCUMULATE ON DIPS"),
                "ai_model": (omniroute_model.get("model_id") if omniroute_model else "omniroute/deepseek-r1"),
                "ai_model_name": (omniroute_model.get("model_name") if omniroute_model else "OmniRoute-AI"),
                "gateway": (omniroute_model.get("gateway") if omniroute_model else "diegosouzapw/OmniRoute"),
                "created_at": consensus_data.get("created_at"),
                "is_cached": True,
            }

        return {
            "success": True,
            "ticker": sym,
            "consensus": consensus_data,
            "omniroute_setup": omniroute_setup,
        }
    except Exception as e:
        logger.debug("Error fetching consensus prediction for %s: %s", sym, e)
        return {"success": False, "ticker": sym, "error": str(e), "consensus": None, "omniroute_setup": None}


def get_stock_kronos(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve latest Kronos AI 14-day sequence price prediction."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}
    try:
        from earnings_engine.data.predictions import load_latest_predictions
        preds = load_latest_predictions(tickers=[sym], settings=settings)
        latest_kronos = preds[0] if preds else None
        return {
            "success": True,
            "ticker": sym,
            "kronos": latest_kronos,
        }
    except Exception as e:
        logger.debug("Error fetching Kronos prediction for %s: %s", sym, e)
        return {"success": False, "ticker": sym, "error": str(e), "kronos": None}


def get_stock_institutional(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve institutional accumulation flows, top fund holdings, and block deals."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}

    institutional_data: dict[str, Any] = {}
    try:
        from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
        inst = get_stock_institutional_activity(sym, settings)
        if inst.get("success"):
            institutional_data = {
                "accumulation_score": inst.get("accumulation_score"),
                "verdict": inst.get("verdict"),
                "verdict_badge": inst.get("verdict_badge"),
                "funds_accumulating_count": inst.get("funds_accumulating_count", 0),
                "funds_selling_count": inst.get("funds_selling_count", 0),
                "new_funds_bought_count": inst.get("new_funds_bought_count", 0),
                "gross_inflow_cr": inst.get("gross_inflow_cr", 0),
                "gross_outflow_cr": inst.get("gross_outflow_cr", 0),
                "net_flow_cr": inst.get("net_flow_cr", 0),
                "total_institutional_stake_pct": inst.get("total_institutional_stake_pct"),
                "return_7d_pct": inst.get("return_7d_pct"),
                "return_30d_pct": inst.get("return_30d_pct"),
                "shareholding_patterns": (inst.get("shareholding_patterns") or [])[-4:],
                "block_deals": (inst.get("block_deals") or [])[:5],
                "top_holdings": sorted(
                    (inst.get("holdings") or []),
                    key=lambda h: h.get("holding_value_cr", 0),
                    reverse=True,
                )[:8],
            }
    except Exception as e:
        logger.debug("Error fetching institutional data for %s: %s", sym, e)

    return {
        "success": True,
        "ticker": sym,
        "institutional": institutional_data,
    }


def get_stock_catalysts(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve news catalysts and sentiment impact scores."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}

    # 1. Check SQLite DB cache first
    cached_catalysts = get_short_term_catalysts(watchlist_or_universe="ALL", search_query=sym, limit=15, settings=settings)
    if cached_catalysts:
        return {
            "success": True,
            "ticker": sym,
            "catalysts": cached_catalysts,
        }

    # 2. If completely empty, perform instant heuristic background fetch (run_ai=False to keep modal fast and on-demand)
    try:
        import threading
        from earnings_engine.data.catalysts_news import fetch_ticker_catalysts
        threading.Thread(target=fetch_ticker_catalysts, args=(sym, 15, False, False, settings), daemon=True).start()
    except Exception as e:
        logger.debug("Async catalysts fetch spawn error for %s: %s", sym, e)

    return {
        "success": True,
        "ticker": sym,
        "catalysts": [],
    }


def get_stock_overview(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Compile a full stock intelligence overview (composed from individual modules)."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}

    quote_res = get_stock_quote(sym, settings)
    tech_res = get_stock_technicals(sym, settings)
    earn_res = get_stock_earnings(sym, settings)
    cons_res = get_stock_consensus(sym, settings)
    cat_res = get_stock_catalysts(sym, settings)
    inst_res = get_stock_institutional(sym, settings)

    factor_eval = {}
    try:
        from earnings_engine.consensus.standard_inputs import evaluate_stock_standard_pillars
        factor_eval = evaluate_stock_standard_pillars(sym, settings=settings)
    except Exception as e:
        logger.debug("Error computing standard factor evaluation for %s: %s", sym, e)

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
        "profile": quote_res.get("profile", {}),
        "quote": quote_res.get("quote", {}),
        "technical": tech_res.get("technical", {}),
        "earnings_history": earn_res.get("earnings_history", []),
        "consensus": cons_res.get("consensus"),
        "catalysts": cat_res.get("catalysts", []),
        "factor_evaluation": factor_eval,
        "institutional": inst_res.get("institutional", {}),
        "is_in_watchlist": is_in_watchlist,
    }


def get_stock_factor_evaluation(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve dedicated 6-Pillar factor evaluation matrix and composite rating for a ticker."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}
    try:
        from earnings_engine.consensus.standard_inputs import evaluate_stock_standard_pillars
        eval_data = evaluate_stock_standard_pillars(sym, settings=settings)
        return {"success": True, "data": eval_data}
    except Exception as e:
        logger.error("Failed evaluating standard factors for %s: %s", sym, e)
        return {"success": False, "error": str(e)}


def calculate_stock_rating(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Calculate industry benchmark relative valuation multiples and technical strength rating."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker is required"}
    try:
        from earnings_engine.data.stock_rating import recalculate_stock_rating
        return recalculate_stock_rating(sym, settings, source="api_rating")
    except Exception as e:
        logger.error("Error calculating stock rating for %s: %s", sym, e, exc_info=True)
        return {"success": False, "error": str(e)}


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


def calculate_or_fetch_eps(
    ticker: str,
    earnings_date: str | None = None,
    override_estimate: float | None = None,
    override_reported: float | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Calculate, derive, or fetch missing EPS and surprise % for past earnings dates.
    
    Multi-Tier Strategy:
    1. If manual override is provided, use it directly.
    2. Force re-fetch fresh earnings dates from Yahoo Finance / NSE (consensus Reported EPS / EPS Estimate).
    3. Query quarterly income statement & financials to extract all historical Diluted/Basic EPS values.
    4. Synthesize missing EPS estimates from preceding quarterly averages so surprise % is always computed.
    5. Save resolved values to `earnings_history` database across all available quarters.
    6. Force recalculate ticker metrics, 3Q quality scores, price reactions, and record an audit log entry.
    """
    from earnings_engine.api.recalculate_api import recalculate_ticker_metrics

    if not isinstance(earnings_date, str):
        if isinstance(earnings_date, Settings) and settings is None:
            settings = earnings_date
        earnings_date = None

    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym.endswith(".NS") and not "." in sym:
        sym += ".NS"

    now_date_str = pd.Timestamp.now().strftime("%Y-%m-%d")

    target_ed = earnings_date
    conn = get_db_connection(settings)

    eps_est = override_estimate
    eps_rep = override_reported
    method = "manual_override" if (override_reported is not None or override_estimate is not None) else None

    # Track multi-quarter statements
    quarterly_eps_records: list[dict[str, Any]] = []

    # Multi-Tier Automated Calculation
    # Tier 1: Fresh yfinance get_earnings_dates
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("yfinance")
        except Exception:
            pass
        yf_ticker = yf.Ticker(sym)
        raw_dates = yf_ticker.get_earnings_dates(limit=60)
        if raw_dates is not None and not raw_dates.empty:
            raw_dates.index = pd.to_datetime(raw_dates.index, utc=True).tz_convert(None).normalize()
            
            # Record all available historical dates from consensus
            for dt, row in raw_dates.iterrows():
                dt_str = dt.strftime("%Y-%m-%d")
                r_rep = row.get("Reported EPS") or row.get("reported eps") or row.get("eps_reported")
                r_est = row.get("EPS Estimate") or row.get("eps estimate") or row.get("eps_estimate")
                rep_val = float(r_rep) if (r_rep is not None and not pd.isna(r_rep)) else None
                est_val = float(r_est) if (r_est is not None and not pd.isna(r_est)) else None
                if rep_val is not None or est_val is not None:
                    quarterly_eps_records.append({
                        "date": dt_str,
                        "eps_reported": rep_val,
                        "eps_estimate": est_val,
                        "source": "yfinance_consensus",
                    })

            # Check if target date matched
            if target_ed:
                target_ts = pd.Timestamp(target_ed).normalize()
                matched_row = None
                for dt, row in raw_dates.iterrows():
                    diff_days = abs((dt - target_ts).days)
                    if diff_days <= 7:
                        matched_row = row
                        break
                
                if matched_row is not None:
                    r_rep = matched_row.get("Reported EPS") or matched_row.get("reported eps") or matched_row.get("eps_reported")
                    r_est = matched_row.get("EPS Estimate") or matched_row.get("eps estimate") or matched_row.get("eps_estimate")
                    if eps_rep is None and r_rep is not None and not pd.isna(r_rep):
                        eps_rep = float(r_rep)
                        method = "yfinance_consensus"
                    if eps_est is None and r_est is not None and not pd.isna(r_est):
                        eps_est = float(r_est)
    except Exception as e:
        logger.debug("Tier 1 earnings dates fetch failed for %s: %s", sym, e)

    # Tier 2: Quarterly Income Statement (Extract Diluted EPS across all available quarters)
    inc_stmt_cols_data: list[tuple[pd.Timestamp, float]] = []
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("yfinance")
        except Exception:
            pass
        yf_ticker = yf.Ticker(sym)
        inc_stmt = yf_ticker.quarterly_income_stmt
        if inc_stmt is not None and not inc_stmt.empty:
            # Sort columns from newest to oldest
            sorted_cols = sorted(inc_stmt.columns, key=lambda c: pd.Timestamp(c).normalize(), reverse=True)
            
            for col in sorted_cols:
                col_ts = pd.Timestamp(col).normalize()
                col_eps = None
                if "Diluted EPS" in inc_stmt.index and not pd.isna(inc_stmt.loc["Diluted EPS", col]):
                    col_eps = float(inc_stmt.loc["Diluted EPS", col])
                elif "Basic EPS" in inc_stmt.index and not pd.isna(inc_stmt.loc["Basic EPS", col]):
                    col_eps = float(inc_stmt.loc["Basic EPS", col])
                elif "Net Income" in inc_stmt.index and "Diluted Average Shares" in inc_stmt.index:
                    net_inc = inc_stmt.loc["Net Income", col]
                    shares = inc_stmt.loc["Diluted Average Shares", col]
                    if not pd.isna(net_inc) and not pd.isna(shares) and shares > 0:
                        col_eps = round(float(net_inc / shares), 2)
                
                if col_eps is not None:
                    inc_stmt_cols_data.append((col_ts, col_eps))

            # Match for target_ed if specified
            if target_ed and inc_stmt_cols_data:
                target_ts = pd.Timestamp(target_ed).normalize()
                best_match = None
                min_diff = 9999
                for col_ts, col_eps in inc_stmt_cols_data:
                    diff_days = abs((col_ts - target_ts).days)
                    if diff_days < min_diff and (col_ts <= target_ts + pd.Timedelta(days=20)):
                        min_diff = diff_days
                        best_match = (col_ts, col_eps)
                
                if eps_rep is None and best_match:
                    eps_rep = best_match[1]
                    method = "quarterly_income_stmt_diluted"
    except Exception as e:
        logger.debug("Tier 2 quarterly income stmt calculation failed for %s: %s", sym, e)

    # If target_ed is specified, derive its EPS Estimate if missing
    surprise_pct: float | None = None
    if target_ed:
        if eps_est is None:
            preceding_eps = [eps for col_ts, eps in inc_stmt_cols_data if (col_ts < pd.Timestamp(target_ed).normalize())]
            if not preceding_eps and len(inc_stmt_cols_data) > 1:
                preceding_eps = [eps for _, eps in inc_stmt_cols_data[1:]]
            
            if preceding_eps:
                eps_est = round(sum(preceding_eps[:4]) / len(preceding_eps[:4]), 2)
                if method is None or method == "quarterly_income_stmt_diluted":
                    method = "quarterly_income_stmt_diluted"
            else:
                try:
                    prior_rows = conn.execute(
                        "SELECT eps_reported FROM earnings_history WHERE ticker = ? AND earnings_date < ? AND eps_reported IS NOT NULL ORDER BY earnings_date DESC LIMIT 4",
                        (sym, target_ed),
                    ).fetchall()
                    if prior_rows:
                        prior_vals = [float(r[0]) for r in prior_rows if r[0] is not None]
                        if prior_vals:
                            eps_est = round(sum(prior_vals) / len(prior_vals), 2)
                            if method is None:
                                method = "derived_historical_average"
                except Exception:
                    pass

        # Fallback from fast_info if still missing
        if eps_rep is None:
            try:
                from earnings_engine.rate_limits import record_request
                try:
                    record_request("yfinance")
                except Exception:
                    pass
                yf_ticker = yf.Ticker(sym)
                info = yf_ticker.fast_info
                trailing_pe = getattr(info, "trailing_pe", None)
                last_price = getattr(info, "last_price", None)
                if trailing_pe and last_price and trailing_pe > 0:
                    annual_eps = last_price / trailing_pe
                    eps_rep = round(annual_eps / 4.0, 2)
                    method = "derived_pe_quarterly_eps"
                    if eps_est is None:
                        eps_est = round(eps_rep * 0.96, 2)
            except Exception:
                pass

        if eps_rep is not None and eps_est is None:
            eps_est = round(eps_rep * 0.95, 2)

        # Calculate surprise percentage
        if eps_rep is not None and eps_est is not None and abs(eps_est) > 0.0001:
            surprise_pct = round(((eps_rep - eps_est) / abs(eps_est)) * 100.0, 2)

        # Guard Rail 1: Do not overwrite authentic yfinance/nse source data with calculated heuristics unless it is an explicit user override
        is_manual_override = (override_estimate is not None or override_reported is not None)
        existing_auth = None
        try:
            existing_auth = conn.execute(
                "SELECT source, eps_reported, eps_estimate FROM earnings_history WHERE ticker = ? AND earnings_date = ?",
                (sym, target_ed),
            ).fetchone()
        except Exception:
            pass

        if existing_auth and existing_auth[0] in ("yfinance", "nse") and not is_manual_override:
            logger.info("[CALC-EPS] Preserving authentic %s record for %s (%s)", existing_auth[0], sym, target_ed)
        elif eps_rep is not None or eps_est is not None or target_ed:
            save_source = "manual_override" if is_manual_override else (method or "corporate_announcement")
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                            eps_estimate = COALESCE(excluded.eps_estimate, earnings_history.eps_estimate),
                            eps_reported = COALESCE(excluded.eps_reported, earnings_history.eps_reported),
                            surprise_pct = COALESCE(excluded.surprise_pct, earnings_history.surprise_pct),
                            source = excluded.source
                    """, (sym, target_ed, eps_est, eps_rep, surprise_pct, save_source))
                    conn.commit()
                logger.info("[CALC-EPS] Successfully saved EPS for %s (%s): est=%s, rep=%s, surp=%s (source=%s)", sym, target_ed, eps_est, eps_rep, surprise_pct, save_source)
            except Exception as e:
                logger.warning("[CALC-EPS] Error saving target EPS to DB for %s: %s", sym, e)

    # Guard Rail 2: Save discovered quarterly income statements ONLY when NO authentic yfinance/nse row exists within 60 days
    if inc_stmt_cols_data:
        try:
            auth_dates = []
            try:
                auth_dates = [r[0] for r in conn.execute(
                    "SELECT earnings_date FROM earnings_history WHERE ticker = ? AND source IN ('yfinance', 'nse')",
                    (sym,),
                ).fetchall()]
            except Exception:
                pass

            with conn:
                for i, (col_ts, col_eps) in enumerate(inc_stmt_cols_data):
                    col_dt_str = col_ts.strftime("%Y-%m-%d")
                    # Check if an authentic source date exists within 60 days
                    has_auth_near = any(abs((pd.Timestamp(a_ed) - col_ts).days) <= 60 for a_ed in auth_dates)
                    if has_auth_near:
                        logger.debug("[CALC-EPS] Skipping quarterly_income_stmt for %s (%s) - authentic source date exists nearby", sym, col_dt_str)
                        continue

                    if not target_ed or col_dt_str != target_ed:
                        prior_subset = [e for _, e in inc_stmt_cols_data[i+1:]]
                        q_est = round(sum(prior_subset[:4]) / len(prior_subset[:4]), 2) if prior_subset else round(col_eps * 0.95, 2)
                        q_surp = round(((col_eps - q_est) / abs(q_est)) * 100.0, 2) if abs(q_est) > 0.0001 else 0.0
                        conn.execute("""
                            INSERT INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
                            VALUES (?, ?, ?, ?, ?, 'quarterly_income_stmt')
                            ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                                eps_estimate = COALESCE(earnings_history.eps_estimate, excluded.eps_estimate),
                                eps_reported = COALESCE(earnings_history.eps_reported, excluded.eps_reported),
                                surprise_pct = COALESCE(earnings_history.surprise_pct, excluded.surprise_pct)
                        """, (sym, col_dt_str, q_est, col_eps, q_surp))
                conn.commit()
        except Exception as e:
            logger.warning("[CALC-EPS] Error saving quarterly income statements for %s: %s", sym, e)

    # Save discovered consensus dates
    if quarterly_eps_records:
        try:
            with conn:
                for rec in quarterly_eps_records:
                    r_dt = rec["date"]
                    r_rep = rec["eps_reported"]
                    r_est = rec["eps_estimate"]
                    r_surp = round(((r_rep - r_est) / abs(r_est)) * 100.0, 2) if (r_rep is not None and r_est is not None and abs(r_est) > 0.0001) else None
                    conn.execute("""
                        INSERT INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
                        VALUES (?, ?, ?, ?, ?, 'yfinance_consensus')
                        ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                            eps_estimate = COALESCE(excluded.eps_estimate, earnings_history.eps_estimate),
                            eps_reported = COALESCE(excluded.eps_reported, earnings_history.eps_reported),
                            surprise_pct = COALESCE(excluded.surprise_pct, earnings_history.surprise_pct)
                    """, (sym, r_dt, r_est, r_rep, r_surp))
                conn.commit()
        except Exception as e:
            logger.warning("[CALC-EPS] Error saving consensus dates for %s: %s", sym, e)

    # If target_ed was not provided, set reporting date to newest statement date for response summary
    resolved_ed = target_ed
    if not resolved_ed and inc_stmt_cols_data:
        resolved_ed = inc_stmt_cols_data[0][0].strftime("%Y-%m-%d")
        eps_rep = inc_stmt_cols_data[0][1]
        prior_subset = [e for _, e in inc_stmt_cols_data[1:]]
        eps_est = round(sum(prior_subset[:4]) / len(prior_subset[:4]), 2) if prior_subset else round(eps_rep * 0.95, 2)
        surprise_pct = round(((eps_rep - eps_est) / abs(eps_est)) * 100.0, 2) if abs(eps_est) > 0.0001 else 0.0
        method = "quarterly_income_stmt"

    # Trigger full metric recalculation and audit trail diff logging
    recalc_result: dict[str, Any] = {}
    try:
        recalc_result = recalculate_ticker_metrics(sym, settings=settings)
    except Exception as e:
        logger.warning("[CALC-EPS] Metric recalculation after EPS update for %s failed: %s", sym, e)

    return {
        "success": True,
        "ticker": sym,
        "earnings_date": resolved_ed,
        "eps_estimate": eps_est,
        "eps_reported": eps_rep,
        "surprise_pct": surprise_pct,
        "method": method or "not_found",
        "message": f"Successfully resolved EPS for {resolved_ed or sym}: Reported ₹{eps_rep if eps_rep is not None else '—'} vs Est ₹{eps_est if eps_est is not None else '—'} ({f'{surprise_pct:+.2f}% surprise' if surprise_pct is not None else 'in line'})",
        "has_changes": recalc_result.get("has_changes", False),
        "changes_count": recalc_result.get("changes_count", 0),
        "audit_id": recalc_result.get("audit_id"),
        "recalculate": recalc_result,
    }


def get_stock_intelligence_note(
    ticker: str,
    model_name: str | None = None,
    provider: str = "auto",
    settings: Settings | None = None,
    include_ai: bool = True,
) -> dict[str, Any]:
    """Aggregate a comprehensive, transparent intelligence note for any stock.
    
    Includes:
    - Fundamental Earnings Reaction Mechanics (EPS surprise, week peak high %, net week move %, 30D return %, pullback reasoning)
    - Technical Swing Boundaries (Support, Resistance, Channel Pivot, Cycle Durations)
    - Multi-Model AI Forward Thesis, Growth Drivers, and Risk Factors
    - Recent Corporate Filings & News Catalysts with Sentiment Badges
    - 3-Quarter Beat Streak Track Record
    """
    from earnings_engine.data.quarter_repeaters import generate_ai_repeater_forecast
    from earnings_engine.data.prices import load_price_metrics

    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker is required"}

    # 1. Base overview & metrics
    overview = get_stock_overview(sym, settings)
    profile = overview.get("profile", {})
    quote = overview.get("quote", {})
    tech = overview.get("technical", {})
    e_hist = overview.get("earnings_history", [])

    ticker_metrics = load_price_metrics(sym, settings) or {}

    # 2. Extract Price Action Mechanics
    cmp = quote.get("current_price") or ticker_metrics.get("current_price")
    wk_high_52 = quote.get("week_52_high") or ticker_metrics.get("week_52_high")
    pct_from_52w_high = quote.get("pct_from_52w_high") if quote.get("pct_from_52w_high") is not None else ticker_metrics.get("pct_from_52w_high")
    ret_30d = tech.get("momentum_30d") if tech.get("momentum_30d") is not None else ticker_metrics.get("thirty_day_return_pct")

    # Latest quarter move data
    last_e = e_hist[0] if e_hist else {}
    last_surp = last_e.get("surprise_pct") if last_e.get("surprise_pct") is not None else ticker_metrics.get("last_eps_surprise")
    last_wk_high = last_e.get("week_high_pct") if last_e.get("week_high_pct") is not None else ticker_metrics.get("q1_week_high_pct")
    last_wk_low = last_e.get("week_low_pct") if last_e.get("week_low_pct") is not None else ticker_metrics.get("q1_week_low_pct")
    last_wk_move = ticker_metrics.get("earnings_week_move_pct") if ticker_metrics.get("earnings_week_move_pct") is not None else ticker_metrics.get("week_change")
    last_score = ticker_metrics.get("quality_score") or 6

    # 3. Technical Swing Structure
    supp = tech.get("support_level")
    ress = tech.get("resistance_level")
    pivot = round((supp + ress) / 2.0, 2) if (supp and ress) else None
    pct_from_supp = round(((cmp - supp) / supp) * 100.0, 2) if (cmp and supp and supp > 0) else None
    pct_to_ress = round(((ress - cmp) / cmp) * 100.0, 2) if (cmp and ress and cmp > 0) else None

    # 4. Forward AI Thesis & Multi-Model Execution
    # Lazy-loaded: expensive LLM inference exercises by default so the core note
    # renders fast. Callers opt-in via include_ai=True (the /notes?include_ai=true
    # and /intelligence-note paths) to pull the full AI thesis in the background.
    ai_forecast = {}
    if include_ai:
        try:
            ai_forecast = generate_ai_repeater_forecast(sym, settings=settings, model_name=model_name, provider=provider)
        except Exception as ex:
            logger.warning("[NOTE-API] Error generating AI forecast for %s: %s", sym, ex)

    # Reaction explanation
    price_action_explanation = ai_forecast.get("price_action_assessment")
    if not price_action_explanation:
        if last_wk_move is not None and last_wk_move < 0 and last_wk_high is not None and last_wk_high >= 2.5:
            price_action_explanation = f"Stock rallied +{last_wk_high:.1f}% peak intra-week following strong delivery before post-earnings profit booking pulled the close to {last_wk_move:+.1f}%. Medium-term momentum remained strong with {f'{ret_30d:+.1f}%' if ret_30d is not None else 'positive'} 30-day continuation."
        elif last_wk_high is not None and last_wk_high >= 2.5:
            price_action_explanation = f"Stock demonstrated strong post-earnings demand with a +{last_wk_high:.1f}% peak rally and sustained momentum."
        else:
            price_action_explanation = "Stock established a stable accumulation base following earnings release."

    return {
        "success": True,
        "ticker": sym,
        "company_name": profile.get("name") or sym,
        "sector": profile.get("sector") or "Equities",
        "industry": profile.get("industry") or "General",
        "industry_buzz_tag": ai_forecast.get("industry_buzz_tag") or profile.get("industry") or "Growth",
        "current_price": cmp,
        "day_change_pct": quote.get("day_change_pct"),
        "week_52_high": wk_high_52,
        "pct_from_52w_high": pct_from_52w_high,
        "thirty_day_return_pct": ret_30d,
        "price_reaction": {
            "last_eps_surprise": last_surp,
            "last_quality_score": last_score,
            "last_week_high_pct": last_wk_high,
            "last_week_low_pct": last_wk_low,
            "earnings_week_move_pct": last_wk_move,
            "thirty_day_return_pct": ret_30d,
            "price_action_explanation": price_action_explanation,
        },
        "swing_structure": {
            "support_level": supp,
            "resistance_level": ress,
            "channel_pivot": pivot,
            "pct_from_support": pct_from_supp,
            "pct_to_resistance": pct_to_ress,
            "cycles": tech.get("cycles", 0),
            "avg_cycle_days": tech.get("avg_cycle_days", 0),
        },
        "ai_thesis": {
            "verdict": ai_forecast.get("ai_repeat_verdict") or "MODERATE_BEAT",
            "confidence_pct": ai_forecast.get("repeat_probability_pct") or ai_forecast.get("confidence_pct") or 75,
            "expected_price_bias": ai_forecast.get("expected_price_bias") or "BULLISH",
            "suggested_action": ai_forecast.get("suggested_action") or "ACCUMULATE_PRE_EARNINGS",
            "thesis": ai_forecast.get("thesis") or "Constructive fundamental and momentum continuation expected.",
            "growth_drivers": ai_forecast.get("primary_growth_drivers") or [],
            "risk_factors": ai_forecast.get("key_risk_factors") or [],
            "model_used": ai_forecast.get("model_used") or "Institutional Rules",
        },
        "beat_history": ai_forecast.get("streak_history") or [],
        "beat_streak": ai_forecast.get("beat_streak") or len(e_hist),
        "news_catalysts": ai_forecast.get("news_articles") or [],
        "ai_loaded": bool(ai_forecast),
    }


def get_recent_market_additions(
    days: int = 180,
    limit: int = 100,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve recent IPOs and market additions listed on the NSE."""
    from earnings_engine.data.new_listings import get_recent_nse_additions
    settings = settings or Settings()
    items = get_recent_nse_additions(days=days, limit=limit, settings=settings)
    return {
        "success": True,
        "count": len(items),
        "lookback_days": days,
        "items": items,
    }


def sync_recent_additions_to_watchlist(
    ticker: str,
    watchlist_name: str = "my_watchlist",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """One-click addition of a newly listed stock to a watchlist."""
    from earnings_engine.data.watchlists import add_to_watchlist
    settings = settings or Settings()
    sym = ticker.strip().upper()
    success = add_to_watchlist(watchlist_name, sym, settings=settings)
    return {
        "success": success,
        "ticker": sym,
        "watchlist": watchlist_name,
        "message": f"Successfully added {sym} to {watchlist_name}" if success else f"Failed adding {sym} to {watchlist_name}",
    }


def refresh_stock_news(
    ticker: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Fetch live incremental news delta for a specific ticker and return fresh catalysts."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}
    try:
        from earnings_engine.data.catalysts_news import fetch_ticker_catalysts, get_short_term_catalysts
        fetched = []
        try:
            fetched = fetch_ticker_catalysts(sym, limit=20, force=True, settings=settings)
        except Exception as fe:
            logger.debug("Incremental news fetch partial warning for %s: %s", sym, fe)

        catalysts = get_short_term_catalysts(watchlist_or_universe="ALL", search_query=sym, limit=25, settings=settings)
        return {
            "success": True,
            "ticker": sym,
            "fetched_count": len(fetched),
            "catalysts": catalysts,
        }
    except Exception as e:
        logger.error("Failed refreshing news delta for %s: %s", sym, e)
        return {"success": False, "error": str(e)}



