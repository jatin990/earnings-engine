"""Institutional Accumulation, Fund Holdings, and Distribution Tracker Routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import institutional_accumulation as inst_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.institutional")

router = APIRouter(tags=["Institutional Accumulation & Funds"])


class InstitutionalVerifyRequest(BaseModel):
    scope: str = "ALL"
    ticker: str | None = None
    purge_synthetic: bool = False
    auto_repair: bool = False


@router.get("/api/v1/institutional/integrity")
async def get_institutional_integrity_health(
    scope: str = Query("ALL", description="Audit scope: 'ALL', 'FRESHNESS', 'MATHEMATICAL', 'PROVENANCE', 'ANOMALY'"),
    include_findings: bool = Query(True, description="Include recent audit findings"),
    limit: int = Query(25, ge=1, le=100, description="Max recent findings to return"),
):
    """Retrieve system-wide institutional data health score, cadence freshness statuses, and audit ledger telemetry."""
    try:
        def _get_summary() -> dict[str, Any]:
            from earnings_engine.data.institutional_verifier import InstitutionalVerifier
            verifier = InstitutionalVerifier(_settings)
            summary = verifier.get_integrity_status_summary()

            conn = verifier._get_connection()
            q_row = conn.execute("SELECT COUNT(*) FROM institutional_quarantine").fetchone()
            summary["quarantined_records_count"] = q_row[0] if q_row else 0

            if include_findings:
                findings_rows = conn.execute(
                    """
                    SELECT id, audit_run_id, audit_timestamp, audit_scope, ticker,
                           check_category, check_name, severity, status,
                           expected_value, actual_value, deviation_pct, details
                    FROM institutional_audit_log
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                summary["recent_findings"] = [
                    {
                        "id": r[0],
                        "audit_run_id": r[1],
                        "audit_timestamp": r[2],
                        "audit_scope": r[3],
                        "ticker": r[4],
                        "check_category": r[5],
                        "check_name": r[6],
                        "severity": r[7],
                        "status": r[8],
                        "expected_value": r[9],
                        "actual_value": r[10],
                        "deviation_pct": r[11],
                        "details": r[12],
                    }
                    for r in findings_rows
                ]
            return summary

        data = await asyncio.to_thread(_get_summary)
        return {"success": True, **data}
    except Exception as e:
        logger.exception("Error in get_institutional_integrity_health: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve integrity health: {str(e)}")


@router.post("/api/v1/institutional/verify-and-repair")
async def trigger_institutional_verify_and_repair(
    request: InstitutionalVerifyRequest | None = None,
    scope: str | None = Query(None),
    ticker: str | None = Query(None),
    purge_synthetic: bool | None = Query(None),
    auto_repair: bool | None = Query(None),
):
    """Trigger on-demand institutional verification, invariant audit, and auto-repair/quarantine."""
    req = request or InstitutionalVerifyRequest()
    req_scope = scope or req.scope
    req_ticker = ticker or req.ticker
    req_purge = purge_synthetic if purge_synthetic is not None else req.purge_synthetic
    req_repair = auto_repair if auto_repair is not None else req.auto_repair

    try:
        def _run_audit() -> dict[str, Any]:
            from earnings_engine.data.institutional_verifier import InstitutionalVerifier
            verifier = InstitutionalVerifier(_settings)
            tickers = [req_ticker] if req_ticker else None
            report = verifier.run_comprehensive_audit(
                tickers=tickers,
                scope=req_scope,
                purge_synthetic=req_purge,
                auto_repair=req_repair,
                persist_log=True,
            )
            return report.to_dict()

        result = await asyncio.to_thread(_run_audit)
        return {"success": True, "report": result}
    except Exception as e:
        logger.exception("Error in trigger_institutional_verify_and_repair: %s", e)
        raise HTTPException(status_code=500, detail=f"Institutional verify & repair failed: {str(e)}")


@router.get("/api/v1/institutional/integrity/{ticker:path}")
async def get_stock_institutional_integrity(ticker: str):
    """Retrieve stock-specific data provenance, audit trail, cryptographic payload hashes, and mathematical checks."""
    try:
        def _get_ticker_integrity() -> dict[str, Any]:
            from earnings_engine.data.institutional_verifier import InstitutionalVerifier, MathematicalInvariantChecker
            verifier = InstitutionalVerifier(_settings)
            trail = verifier.get_ticker_provenance_trail(ticker)

            conn = verifier._get_connection()
            sym = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
            base_sym = ticker.replace(".NS", "")

            # Fetch latest shareholding pattern for mathematical validation
            shp_row = conn.execute(
                """
                SELECT quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at
                FROM shareholding_patterns
                WHERE ticker = ? OR ticker = ?
                ORDER BY quarter DESC
                LIMIT 1
                """,
                (sym, base_sym),
            ).fetchone()

            shp_math_findings = []
            shp_info = None
            if shp_row:
                q, p_pct, f_pct, d_pct, pub_pct, oth_pct, upd_at = shp_row
                shp_info = {
                    "quarter": q,
                    "promoter_pct": float(p_pct or 0.0),
                    "fii_pct": float(f_pct or 0.0),
                    "dii_pct": float(d_pct or 0.0),
                    "public_pct": float(pub_pct or 0.0),
                    "others_pct": float(oth_pct or 0.0),
                    "pledged_pct": 0.0,
                    "updated_at": upd_at,
                    "sum_pct": round(
                        float(p_pct or 0.0)
                        + float(f_pct or 0.0)
                        + float(d_pct or 0.0)
                        + float(pub_pct or 0.0)
                        + float(oth_pct or 0.0),
                        2,
                    ),
                }
                findings = MathematicalInvariantChecker.verify_shareholding_pattern(
                    ticker=sym,
                    quarter=q,
                    promoter_pct=float(p_pct or 0.0),
                    fii_pct=float(f_pct or 0.0),
                    dii_pct=float(d_pct or 0.0),
                    public_pct=float(pub_pct or 0.0),
                    others_pct=float(oth_pct or 0.0),
                    pledged_pct=0.0,
                )
                shp_math_findings = [f.to_dict() for f in findings]

            # Fetch recent audit logs for this ticker
            audit_rows = conn.execute(
                """
                SELECT id, audit_run_id, audit_timestamp, check_category, check_name,
                       severity, status, expected_value, actual_value, deviation_pct, details
                FROM institutional_audit_log
                WHERE ticker = ? OR ticker = ?
                ORDER BY id DESC
                LIMIT 20
                """,
                (sym, base_sym),
            ).fetchall()
            audit_logs = [
                {
                    "id": r[0],
                    "audit_run_id": r[1],
                    "audit_timestamp": r[2],
                    "check_category": r[3],
                    "check_name": r[4],
                    "severity": r[5],
                    "status": r[6],
                    "expected_value": r[7],
                    "actual_value": r[8],
                    "deviation_pct": r[9],
                    "details": r[10],
                }
                for r in audit_rows
            ]

            # Fetch quarantine records if any
            quar_rows = conn.execute(
                """
                SELECT id, record_type, entity_key, source_name, rejection_reason, quarantined_at
                FROM institutional_quarantine
                WHERE entity_key LIKE ? OR entity_key LIKE ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (f"{sym}%", f"{base_sym}%"),
            ).fetchall()
            quarantine_records = [
                {
                    "id": r[0],
                    "record_type": r[1],
                    "entity_key": r[2],
                    "source_name": r[3],
                    "rejection_reason": r[4],
                    "quarantined_at": r[5],
                }
                for r in quar_rows
            ]

            # Stock health score calculation
            crit_count = sum(1 for a in audit_logs if a["severity"] in ("CRITICAL", "CRITICAL_ERROR"))
            warn_count = sum(1 for a in audit_logs if a["severity"] == "WARNING")
            stock_health = max(0.0, min(100.0, 100.0 - (crit_count * 20.0) - (warn_count * 5.0)))

            return {
                "ticker": sym,
                "health_score": stock_health,
                "status": "OPTIMAL" if stock_health >= 90.0 else ("WARNING" if stock_health >= 70.0 else "CRITICAL"),
                "provenance_trail": trail,
                "provenance_count": len(trail),
                "latest_shareholding": shp_info,
                "mathematical_findings": shp_math_findings,
                "audit_logs": audit_logs,
                "quarantine_records": quarantine_records,
            }

        data = await asyncio.to_thread(_get_ticker_integrity)
        return {"success": True, **data}
    except Exception as e:
        logger.exception("Error in get_stock_institutional_integrity for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stock integrity: {str(e)}")


@router.get("/api/v1/institutional/summary")
async def get_institutional_summary():
    """Retrieve macro institutional accumulation & distribution metrics."""
    try:
        accumulated = await asyncio.to_thread(inst_mod.get_top_accumulated_stocks, limit=10, settings=_settings)
        distributed = await asyncio.to_thread(inst_mod.get_top_distributed_stocks, limit=10, settings=_settings)
        return {
            "success": True,
            "top_accumulated": accumulated[:5] if accumulated else [],
            "top_distributed": distributed[:5] if distributed else [],
            "total_accumulated": len(accumulated),
            "total_distributed": len(distributed),
        }
    except Exception as e:
        logger.exception("Error in get_institutional_summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching institutional summary: {str(e)}")


@router.get("/api/v1/institutional/accumulating")
async def get_institutional_accumulating(
    universe: str | None = Query(None, description="Universe filter"),
    min_score: float = Query(60.0, ge=0.0, le=100.0),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve top stocks being heavily accumulated by institutions."""
    try:
        stocks = await asyncio.to_thread(
            inst_mod.get_top_accumulated_stocks,
            universe=universe,
            min_score=min_score,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "count": len(stocks), "items": stocks, "stocks": stocks}
    except Exception as e:
        logger.exception("Error in get_institutional_accumulating: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching accumulating stocks: {str(e)}")


@router.get("/api/v1/institutional/distributing")
async def get_institutional_distributing(
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve stocks experiencing institutional distribution or stakeholder exits."""
    try:
        stocks = await asyncio.to_thread(inst_mod.get_top_distributed_stocks, limit=limit, settings=_settings)
        return {"success": True, "count": len(stocks), "items": stocks, "stocks": stocks}
    except Exception as e:
        logger.exception("Error in get_institutional_distributing: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching distributing stocks: {str(e)}")


@router.get("/api/v1/institutional/top-additions")
async def get_top_stake_additions(
    min_delta: float = Query(3.0, ge=0.5, le=50.0),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve top stocks with >= min_delta% institutional additions (latest quarter & historical surges)."""
    try:
        data = await asyncio.to_thread(inst_mod.get_top_stake_additions, min_delta=min_delta, limit=limit, settings=_settings)
        return data
    except Exception as e:
        logger.exception("Error in get_top_stake_additions: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching top additions: {str(e)}")


@router.get("/api/v1/institutional/recent-accumulation")
async def get_institutional_recent_accumulation(
    window: str = Query("90d", description="Lookback window: '30d', '90d', '180d', '365d'"),
    entity_focus: str = Query("smart_money", description="Entity focus: 'smart_money', 'all', 'fii_only', 'super_investor', 'block_deals'"),
    min_cr: float = Query(5.0, ge=0.0, description="Minimum capital deployed in ₹ Cr"),
    sort_by: str = Query("score", description="Sort by: 'score', 'capital', 'dominance', 'return_30d', 'signal_date', 'return_since_signal', 'eps_growth'"),
    limit: int = Query(50, ge=1, le=200),
    emerging_only: bool = Query(False, description="Filter Small/Micro cap equities (< ₹15,000 Cr)"),
    min_eps_growth: float | None = Query(None, description="Minimum quarterly YoY EPS growth %"),
    new_entrants_only: bool = Query(False, description="Filter stocks added to radar within last 14 days"),
):
    """Retrieve equities under aggressive smart money accumulation across rolling lookback windows."""
    try:
        data = await asyncio.to_thread(
            inst_mod.get_stocks_under_institutional_accumulation,
            window=window,
            entity_focus=entity_focus,
            min_cr=min_cr,
            sort_by=sort_by,
            limit=limit,
            emerging_only=emerging_only,
            min_eps_growth=min_eps_growth,
            new_entrants_only=new_entrants_only,
            settings=_settings,
        )
        return data
    except Exception as e:
        logger.exception("Error in get_institutional_recent_accumulation: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching recent accumulation: {str(e)}")


@router.get("/api/v1/institutional/signals", summary="Smart Money Radar Tracked Signals")
async def get_smart_money_signals(
    strategy: str = Query("ALL_STRATEGIES", description="Strategy key: ALL_STRATEGIES, WHALE_CONVICTION, BLOCK_DEAL_MOMENTUM, DUAL_ACCELERATION, DOMESTIC_ABSORPTION"),
    status: str = Query("active", description="Signal lifecycle status: active, target_hit, distribution_exit, cooling_off, all"),
    sort_by: str = Query("score", description="Sort key: score, return, gain, capital, date, days"),
    limit: int = Query(60, ge=1, le=200, description="Max signals to return"),
):
    """Retrieve tracked smart money signals filtered by strategy, lifecycle status, and sort key."""
    try:
        data = await asyncio.to_thread(
            inst_mod.get_tracked_smart_money_signals,
            strategy=strategy,
            status=status,
            sort_by=sort_by,
            limit=limit,
            settings=_settings,
        )
        return data
    except Exception as e:
        logger.exception("Error in get_smart_money_signals: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching smart money signals: {str(e)}")


@router.get("/api/v1/institutional/funds")
async def get_top_institutional_funds(
    limit: int = Query(25, ge=1, le=100),
):
    """Retrieve top mutual funds and institutional entities with their active positions."""
    try:
        funds = await asyncio.to_thread(inst_mod.get_all_funds_activity, limit=limit, settings=_settings)
        return {"success": True, "count": len(funds), "funds": funds}
    except Exception as e:
        logger.exception("Error in get_top_institutional_funds: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching funds: {str(e)}")


@router.get("/api/v1/institutional/fund/{fund_name:path}")
async def get_fund_portfolio(fund_name: str):
    """Reverse lookup: retrieve all equities held and recent actions for a specific mutual fund or super investor."""
    try:
        items = await asyncio.to_thread(inst_mod.get_fund_portfolio_activity, fund_name=fund_name, settings=_settings)
        total_aum = round(sum(float(h.get("holding_value_cr") or 0.0) for h in items), 1)
        fund_type = items[0].get("fund_type") if items and items[0].get("fund_type") else "Mutual Fund (DII)"
        return {
            "success": True,
            "fund_name": fund_name,
            "fund_type": fund_type,
            "count": len(items),
            "total_aum_tracked_cr": total_aum,
            "holdings": items,
        }
    except Exception as e:
        logger.exception("Error in get_fund_portfolio for %s: %s", fund_name, e)
        raise HTTPException(status_code=500, detail=f"Error fetching fund portfolio: {str(e)}")


@router.get("/api/v1/institutional/stock/{ticker}/buyers")
@router.get("/api/v1/institutional/buyers/{ticker:path}")
async def get_stock_buyers(
    ticker: str,
    from_date: str | None = Query(None, description="Start date (e.g. '2026-02-01', 'FEB 2026', '90d')"),
    to_date: str | None = Query(None, description="End date (e.g. '2026-08-31')"),
    quarter: str | None = Query(None, description="Quarter filter (e.g. 'Q4 FY26', 'Q1 FY27')"),
    entity_type: str | None = Query(None, description="Entity filter (e.g. 'FII', 'DII', 'Super Investor')"),
    min_value_cr: float = Query(0.0, ge=0.0, description="Minimum capital deployed in ₹ Cr"),
):
    """Retrieve all institutional, fund, and super investor buyers who accumulated the stock in a given period."""
    try:
        data = await asyncio.to_thread(
            inst_mod.get_stock_buyers_in_period,
            ticker=ticker,
            from_date=from_date,
            to_date=to_date,
            quarter=quarter,
            entity_type=entity_type,
            min_value_cr=min_value_cr,
            settings=_settings,
        )
        return data
    except Exception as e:
        logger.exception("Error in get_stock_buyers for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock buyers: {str(e)}")


@router.get("/api/v1/institutional/stock/{ticker}/forensics", summary="Stock Forensic Dossier")
async def get_stock_forensics(ticker: str):
    """Retrieve complete stock forensic dossier (metadata, signal timeline, institutional buyers, quarterly income trajectory, block deals, macro profile)."""
    try:
        data = await asyncio.to_thread(
            inst_mod.get_stock_forensic_dossier,
            ticker=ticker,
            settings=_settings,
        )
        if not data or not data.get("ticker"):
            raise HTTPException(status_code=404, detail=f"No forensic dossier found for {ticker}")
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_stock_forensics for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock forensic dossier: {str(e)}")


@router.get("/api/v1/institutional/stock/{ticker}")
async def get_stock_institutional_details(ticker: str):
    """Retrieve detailed institutional shareholding breakdown for a specific stock."""
    try:
        details = await asyncio.to_thread(inst_mod.get_stock_institutional_activity, ticker=ticker, settings=_settings)
        return {"success": True, "ticker": ticker, **(details or {})}
    except Exception as e:
        logger.exception("Error in get_stock_institutional_details for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock institutional data: {str(e)}")


@router.get("/api/v1/institutional/freshness")
async def get_institutional_data_freshness():
    """Inspect and return last refresh timestamps, cadences, and counts across institutional data types."""
    try:
        data = await asyncio.to_thread(inst_mod.check_institutional_data_freshness, settings=_settings)
        return data
    except Exception as e:
        logger.exception("Error in get_institutional_data_freshness: %s", e)
        raise HTTPException(status_code=500, detail=f"Error checking freshness: {str(e)}")


@router.get("/api/v1/institutional/divergence-data")
async def get_institutional_divergence_data():
    """Retrieve full structured dataset for institutional flow divergence visualization."""
    from pathlib import Path
    import json
    data_path = Path("institutional_divergence_data.json")
    if data_path.exists():
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"success": True, **data}
        except Exception as e:
            logger.error("Failed to read divergence json: %s", e)
    return {"success": False, "detail": "Divergence data not generated yet."}


@router.get("/institutional-divergence", tags=["UI"])
async def serve_institutional_divergence_radar():
    """Serve standalone interactive HTML Institutional Flow Divergence Radar."""
    from fastapi.responses import HTMLResponse
    from pathlib import Path
    html_path = Path("institutional_flow_divergence.html")
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="Institutional Flow Divergence Radar page not found.")


@router.post("/api/v1/institutional/recalculate")
async def trigger_institutional_recalculation(force: bool = Query(False)):
    """Trigger complete batch recalculation and cache population for all stocks in the database."""
    try:
        res = await asyncio.to_thread(inst_mod.recalculate_all_institutional_metrics, settings=_settings, force=force)
        return res
    except Exception as e:
        logger.exception("Error in trigger_institutional_recalculation: %s", e)
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {str(e)}")


@router.post("/api/v1/institutional/scan")
async def run_institutional_scan(request: dict | None = None):
    """Trigger background computation of institutional flows via live corporate ownership fetch."""
    ticker = (request or {}).get("ticker")
    try:
        if ticker:
            res = await asyncio.to_thread(inst_mod.fetch_live_corporate_ownership, ticker=ticker, settings=_settings)
        else:
            res = await asyncio.to_thread(inst_mod.recalculate_all_institutional_metrics, settings=_settings, force=True)
        return {"success": True, "result": res}
    except Exception as e:
        logger.exception("Error in run_institutional_scan: %s", e)
        raise HTTPException(status_code=500, detail=f"Institutional scan failed: {str(e)}")

