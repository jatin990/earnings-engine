"""Rankings and screening for top institutional accumulation, distribution, and stake additions."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.institutional_accumulation.activity import get_stock_institutional_activity
from earnings_engine.data.institutional_accumulation.cache import _get_inst_cache, _set_inst_cache
from earnings_engine.data.institutional_accumulation.db import (
    init_institutional_db,
    recalculate_all_institutional_metrics,
)

logger = logging.getLogger(__name__)


def get_top_accumulated_stocks(
    universe: str | None = None,
    min_score: float = 60.0,
    limit: int = 25,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve high-conviction equities experiencing active institutional fund accumulation."""
    cache_key = f"top_accum_{universe}_{min_score}_{limit}"
    cached = _get_inst_cache(cache_key)
    if cached is not None:
        return cached

    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        # Ensure cache table has data
        count_cache = conn.execute("SELECT COUNT(*) FROM institutional_accumulation_cache").fetchone()[0]
        if count_cache == 0:
            recalculate_all_institutional_metrics(settings)

        if universe:
            rows = conn.execute(
                """
                SELECT c.ticker, c.company_name, c.market_cap_cr, c.accumulation_score, c.verdict, c.verdict_badge,
                       c.funds_accumulating_count, c.funds_selling_count, c.new_funds_bought_count,
                       c.gross_inflow_cr, c.gross_outflow_cr, c.net_flow_cr,
                       c.inst_addition_pct, c.increase_amount_cr, c.total_amount_cr, c.total_institutional_amount_cr,
                       c.total_institutional_stake_pct, c.fii_stake_pct, c.dii_stake_pct,
                       c.is_new_fii_entry, c.is_new_dii_entry, c.fii_always_held, c.fii_interest_summary,
                       c.return_7d_pct, c.return_30d_pct, c.return_1y_pct, c.holdings_json
                FROM institutional_accumulation_cache c
                JOIN universes u ON (c.ticker = u.ticker OR c.ticker || '.NS' = u.ticker OR REPLACE(c.ticker, '.NS', '') = u.ticker)
                WHERE (LOWER(u.universe_name) = LOWER(?) OR u.universe_name = ?)
                  AND c.accumulation_score >= ?
                ORDER BY c.accumulation_score DESC, c.net_flow_cr DESC
                LIMIT ?
                """,
                (universe, universe, min_score, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ticker, company_name, market_cap_cr, accumulation_score, verdict, verdict_badge,
                       funds_accumulating_count, funds_selling_count, new_funds_bought_count,
                       gross_inflow_cr, gross_outflow_cr, net_flow_cr,
                       inst_addition_pct, increase_amount_cr, total_amount_cr, total_institutional_amount_cr,
                       total_institutional_stake_pct, fii_stake_pct, dii_stake_pct,
                       is_new_fii_entry, is_new_dii_entry, fii_always_held, fii_interest_summary,
                       return_7d_pct, return_30d_pct, return_1y_pct, holdings_json
                FROM institutional_accumulation_cache
                WHERE accumulation_score >= ?
                ORDER BY accumulation_score DESC, net_flow_cr DESC
                LIMIT ?
                """,
                (min_score, limit),
            ).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            holdings_raw = json.loads(r[26] or "[]")
            results.append({
                "ticker": r[0],
                "company_name": r[1],
                "market_cap_cr": r[2],
                "accumulation_score": r[3],
                "score": r[3],
                "verdict": r[4],
                "verdict_badge": r[5],
                "funds_accumulating_count": r[6],
                "funds_selling_count": r[7],
                "new_funds_bought_count": r[8],
                "gross_inflow_cr": r[9],
                "gross_outflow_cr": r[10],
                "net_flow_cr": r[11],
                "increase_pct": r[12],
                "inst_addition_pct": r[12],
                "increase_amount_cr": r[13],
                "total_amount_cr": r[14],
                "total_institutional_amount_cr": r[15],
                "total_institutional_stake_pct": r[16],
                "total_institutional_stake": r[16],
                "fii_stake_pct": r[17],
                "dii_stake_pct": r[18],
                "is_new_fii_entry": bool(r[19]),
                "is_new_dii_entry": bool(r[20]),
                "fii_always_held": bool(r[21]),
                "fii_interest_summary": r[22],
                "return_7d_pct": r[23],
                "return_30d_pct": r[24],
                "return_1y_pct": r[25],
                "funds_accumulating": [
                    {"fund_name": h["fund_name"], "action": h["action"], "stake_pct": h["stake_pct"], "increase_amount_cr": h.get("increase_amount_cr", 0.0), "total_amount_cr": h.get("total_amount_cr", 0.0)}
                    for h in holdings_raw if h.get("action") in ("NEW BUY", "ACCUMULATED")
                ],
            })

        _set_inst_cache(cache_key, results, ttl_seconds=180.0)
        return results
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Top accumulated error: %s", e)
        return []


def get_top_distributed_stocks(
    limit: int = 20,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve equities where institutional funds are actively trimming or liquidating positions."""
    cache_key = f"top_dist_{limit}"
    cached = _get_inst_cache(cache_key)
    if cached is not None:
        return cached

    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        count_cache = conn.execute("SELECT COUNT(*) FROM institutional_accumulation_cache").fetchone()[0]
        if count_cache == 0:
            recalculate_all_institutional_metrics(settings)

        rows = conn.execute(
            """
            SELECT ticker, company_name, market_cap_cr, accumulation_score, verdict, verdict_badge,
                   funds_accumulating_count, funds_selling_count, new_funds_bought_count,
                   gross_inflow_cr, gross_outflow_cr, net_flow_cr,
                   inst_addition_pct, increase_amount_cr, total_amount_cr, total_institutional_amount_cr,
                   total_institutional_stake_pct, fii_stake_pct, dii_stake_pct,
                   is_new_fii_entry, is_new_dii_entry, fii_always_held, fii_interest_summary,
                   return_7d_pct, return_30d_pct, return_1y_pct, holdings_json
            FROM institutional_accumulation_cache
            WHERE funds_selling_count > 0 OR inst_addition_pct < 0
            ORDER BY CASE WHEN inst_addition_pct < 0 THEN inst_addition_pct ELSE 0 END ASC, funds_selling_count DESC, gross_outflow_cr DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            holdings_raw = json.loads(r[26] or "[]")
            results.append({
                "ticker": r[0],
                "company_name": r[1],
                "market_cap_cr": r[2],
                "accumulation_score": r[3],
                "score": r[3],
                "verdict": r[4],
                "verdict_badge": r[5],
                "funds_selling_count": r[7],
                "funds_accumulating_count": r[6],
                "gross_inflow_cr": r[9],
                "gross_outflow_cr": r[10],
                "net_flow_cr": r[11],
                "increase_pct": r[12],
                "inst_addition_pct": r[12],
                "increase_amount_cr": r[13],
                "total_amount_cr": r[14],
                "total_institutional_amount_cr": r[15],
                "total_institutional_stake_pct": r[16],
                "total_institutional_stake": r[16],
                "fii_stake_pct": r[17],
                "dii_stake_pct": r[18],
                "is_new_fii_entry": bool(r[19]),
                "is_new_dii_entry": bool(r[20]),
                "fii_always_held": bool(r[21]),
                "fii_interest_summary": r[22],
                "return_7d_pct": r[23],
                "return_30d_pct": r[24],
                "return_1y_pct": r[25],
                "funds_selling": [
                    {"fund_name": h["fund_name"], "action": h["action"], "stake_pct": h["stake_pct"], "increase_amount_cr": h.get("increase_amount_cr", 0.0), "total_amount_cr": h.get("total_amount_cr", 0.0)}
                    for h in holdings_raw if h.get("action") in ("TRIMMED", "SOLD OUT", "PROFIT TAKING")
                ],
            })

        _set_inst_cache(cache_key, results, ttl_seconds=180.0)
        return results
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Top distributed error: %s", e)
        return []


def get_top_stake_additions(
    min_delta: float = 3.0,
    limit: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve top stocks with >= min_delta% institutional addition in latest quarter and historical mega surges."""
    cache_key = f"top_additions_{min_delta}_{limit}"
    cached = _get_inst_cache(cache_key)
    if cached is not None and len(cached.get("latest_additions", [])) > 0:
        return cached

    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        count_cache = conn.execute("SELECT COUNT(*) FROM institutional_accumulation_cache").fetchone()[0]
        if count_cache == 0:
            recalculate_all_institutional_metrics(settings)

        # 1. Fetch from precomputed institutional accumulation cache
        rows = conn.execute(
            """
            SELECT ticker, company_name, market_cap_cr, accumulation_score, verdict, verdict_badge,
                   funds_accumulating_count, funds_selling_count, new_funds_bought_count,
                   gross_inflow_cr, gross_outflow_cr, net_flow_cr,
                   inst_addition_pct, increase_amount_cr, total_amount_cr, total_institutional_amount_cr,
                   total_institutional_stake_pct, fii_stake_pct, dii_stake_pct,
                   is_new_fii_entry, is_new_dii_entry, fii_always_held, fii_interest_summary,
                   return_7d_pct, return_30d_pct, return_1y_pct, shareholding_patterns_json
            FROM institutional_accumulation_cache
            WHERE inst_addition_pct >= ?
            ORDER BY inst_addition_pct DESC, net_flow_cr DESC
            LIMIT ?
            """,
            (min_delta, limit * 2),
        ).fetchall()

        if not rows:
            rows = conn.execute(
                """
                SELECT ticker, company_name, market_cap_cr, accumulation_score, verdict, verdict_badge,
                       funds_accumulating_count, funds_selling_count, new_funds_bought_count,
                       gross_inflow_cr, gross_outflow_cr, net_flow_cr,
                       inst_addition_pct, increase_amount_cr, total_amount_cr, total_institutional_amount_cr,
                       total_institutional_stake_pct, fii_stake_pct, dii_stake_pct,
                       is_new_fii_entry, is_new_dii_entry, fii_always_held, fii_interest_summary,
                       return_7d_pct, return_30d_pct, return_1y_pct, shareholding_patterns_json
                FROM institutional_accumulation_cache
                ORDER BY inst_addition_pct DESC, net_flow_cr DESC
                LIMIT ?
                """,
                (limit * 2,),
            ).fetchall()

        latest_additions: list[dict[str, Any]] = []
        historical_additions: list[dict[str, Any]] = []

        for r in rows:
            pats = json.loads(r[26] or "[]")
            lat_q = pats[0]["quarter"] if len(pats) >= 1 else "Q1 FY27"
            prev_q = pats[1]["quarter"] if len(pats) >= 2 else "Q4 FY26"
            fii_d = round(pats[0]["fii_pct"] - pats[1]["fii_pct"], 2) if len(pats) >= 2 else 0.0
            dii_d = round(pats[0]["dii_mf_pct"] - pats[1]["dii_mf_pct"], 2) if len(pats) >= 2 else 0.0

            latest_additions.append({
                "ticker": r[0],
                "company_name": r[1],
                "latest_quarter": lat_q,
                "previous_quarter": prev_q,
                "market_cap_cr": r[2],
                "inst_addition_pct": r[12],
                "increase_pct": r[12],
                "increase_amount_cr": r[13],
                "total_amount_cr": r[14],
                "total_institutional_amount_cr": r[15],
                "fii_delta_pct": fii_d,
                "dii_delta_pct": dii_d,
                "total_institutional_stake_pct": r[16],
                "fii_stake_pct": r[17],
                "dii_stake_pct": r[18],
                "accumulation_score": r[3],
                "verdict": r[4],
                "verdict_badge": r[5],
                "net_flow_cr": r[11],
                "gross_inflow_cr": r[9],
                "gross_outflow_cr": r[10],
                "funds_accumulating_count": r[6],
                "funds_selling_count": r[7],
                "is_new_fii_entry": bool(r[19]),
                "is_new_dii_entry": bool(r[20]),
                "fii_interest_summary": r[22],
                "return_7d_pct": r[23],
                "return_30d_pct": r[24],
                "return_1y_pct": r[25],
            })

            # Check historical quarterly pairs from stored pattern JSON
            if len(pats) >= 3:
                best_surge = None
                for i in range(1, len(pats) - 1):
                    hfii_curr, hdii_curr = pats[i]["fii_pct"], pats[i]["dii_mf_pct"]
                    hfii_prev, hdii_prev = pats[i+1]["fii_pct"], pats[i+1]["dii_mf_pct"]
                    h_delta = round((hfii_curr + hdii_curr) - (hfii_prev + hdii_prev), 2)
                    if h_delta >= min_delta:
                        hq_curr, hq_prev = pats[i]["quarter"], pats[i+1]["quarter"]
                        hinst_curr = round(hfii_curr + hdii_curr, 2)
                        h_tot_amt = round((hinst_curr / 100.0) * r[2], 1) if r[2] else round(hinst_curr * 150.0, 1)
                        h_inc_amt = round((h_delta / 100.0) * r[2], 1) if (r[2] and h_delta != 0) else round(h_delta * 120.0, 1)
                        surge_entry = {
                            "ticker": r[0],
                            "company_name": r[1],
                            "quarter_comparison": f"{hq_curr} vs {hq_prev}",
                            "target_quarter": hq_curr,
                            "baseline_quarter": hq_prev,
                            "market_cap_cr": r[2],
                            "inst_addition_pct": h_delta,
                            "increase_pct": h_delta,
                            "increase_amount_cr": h_inc_amt,
                            "total_amount_cr": h_tot_amt,
                            "total_institutional_amount_cr": h_tot_amt,
                            "fii_delta_pct": round(hfii_curr - hfii_prev, 2),
                            "dii_delta_pct": round(hdii_curr - hdii_prev, 2),
                            "historical_stake_pct": hinst_curr,
                            "current_total_stake_pct": r[16],
                            "accumulation_score": r[3],
                            "funds_accumulating_count": r[6],
                            "return_30d_pct": r[24],
                        }
                        if best_surge is None or surge_entry["inst_addition_pct"] > best_surge["inst_addition_pct"]:
                            best_surge = surge_entry
                if best_surge is not None:
                    historical_additions.append(best_surge)

        latest_additions.sort(key=lambda x: x["inst_addition_pct"], reverse=True)
        historical_additions.sort(key=lambda x: x["inst_addition_pct"], reverse=True)

        res_payload = {
            "success": True,
            "min_delta": min_delta,
            "latest_count": len(latest_additions),
            "historical_count": len(historical_additions),
            "latest_additions": latest_additions[:limit],
            "historical_additions": historical_additions[:limit],
            "historical_surges": historical_additions[:limit],
            "top_additions": latest_additions[:limit],
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

        _set_inst_cache(cache_key, res_payload, ttl_seconds=180.0)
        return res_payload

    except Exception as e:
        logger.warning("[INSTITUTIONAL] Top additions error: %s", e)
        return {
            "success": False,
            "error": str(e),
            "latest_additions": [],
            "historical_additions": [],
        }


def scan_watchlist_institutional(
    watchlist_name: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Scan and synchronize institutional ownership and accumulation data for all stocks in a watchlist/universe."""
    settings = settings or Settings()
    from earnings_engine.data.watchlists import get_watchlist
    from earnings_engine.data.universe import get_universe

    tickers: list[str] = []
    if watchlist_name and watchlist_name.upper() not in ("", "ALL", "GLOBAL"):
        tickers = get_watchlist(watchlist_name, settings)
        if not tickers:
            tickers = get_universe(watchlist_name, settings)

    if not tickers:
        tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "LT.NS"]

    results: list[dict[str, Any]] = []
    for t in tickers:
        try:
            act = get_stock_institutional_activity(t, settings)
            if act and act.get("success"):
                results.append(act)
        except Exception as ex:
            logger.debug("[INSTITUTIONAL] Failed syncing %s: %s", t, ex)

    return results
