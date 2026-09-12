"""Custom Alert Rules Engine and Notification Dispatch Router."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.alerts")

router = APIRouter(tags=["Alert Rules & Notifications"])


class AlertRulePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    strategy: str = Field(default="ALL")
    min_score: float = Field(default=70.0, ge=0.0, le=100.0)
    min_volume_surge: float = Field(default=1.5, ge=0.0, le=50.0)
    tier: str = Field(default="ALL")
    target_universe: str = Field(default="ALL")
    max_entry_delay_pct: float = Field(default=3.0, ge=0.0, le=20.0)
    actions_json: list[str] | str = Field(default=["browser"])
    webhook_url: str | None = None
    email_recipients: str | None = None
    is_active: bool = True


class TestDispatchPayload(BaseModel):
    channel: str = Field(..., description="browser, webhook, or email")
    webhook_url: str | None = None
    email_recipients: str | None = None
    sample_ticker: str = Field(default="TCS.NS")
    sample_strategy: str = Field(default="Breakout Momentum")
    sample_score: float = Field(default=86.5)
    sample_surge: float = Field(default=2.8)


def _seed_default_rules_if_empty(conn: Any) -> None:
    """Seed initial high-conviction quantitative alert templates if table is empty."""
    try:
        cur = conn.execute("SELECT COUNT(*) as count FROM alert_rules")
        row = cur.fetchone()
        count = row["count"] if hasattr(row, "keys") else (row[0] if row else 0)
        if count > 0:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        seeds = [
            (
                "rule_default_momentum",
                "🚀 High-Volume Breakout Surge",
                "MOMENTUM",
                75.0,
                2.0,
                "TIER_1",
                "NSE_TOP",
                2.5,
                json.dumps(["browser"]),
                None,
                None,
                1,
                now_iso,
                now_iso,
            ),
            (
                "rule_default_52w",
                "🛡️ 52W High Institutional Squeeze",
                "52W_HIGH",
                80.0,
                1.5,
                "ALL",
                "NSE_LARGE_CAP",
                2.0,
                json.dumps(["browser"]),
                None,
                None,
                1,
                now_iso,
                now_iso,
            ),
            (
                "rule_default_confluence",
                "⚡ Tri-Confluence Power Coil",
                "TRI_CONFLUENCE",
                70.0,
                1.8,
                "ALL",
                "ALL",
                3.0,
                json.dumps(["browser"]),
                None,
                None,
                1,
                now_iso,
                now_iso,
            ),
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO alert_rules (
                id, name, strategy, min_score, min_volume_surge, tier,
                target_universe, max_entry_delay_pct, actions_json,
                webhook_url, email_recipients, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seeds,
        )
        conn.commit()
    except Exception as e:
        logger.debug("Failed seeding initial alert rules: %s", e)


# ---------------------------------------------------------------------------
# LITERAL ROUTES (Defined BEFORE Parameterized Routes for Strict Precedence)
# ---------------------------------------------------------------------------

@router.get("/api/v1/alerts/rules")
async def get_alert_rules():
    """List all custom alert rules with trigger stats and active states."""
    def _fetch():
        with get_db_connection() as conn:
            _seed_default_rules_if_empty(conn)
            cur = conn.execute(
                """
                SELECT id, name, strategy, min_score, min_volume_surge, tier,
                       target_universe, max_entry_delay_pct, actions_json,
                       webhook_url, email_recipients, is_active, last_triggered_at,
                       trigger_count, created_at, updated_at
                FROM alert_rules
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = dict(r) if hasattr(r, "keys") else {
                    "id": r[0], "name": r[1], "strategy": r[2], "min_score": r[3],
                    "min_volume_surge": r[4], "tier": r[5], "target_universe": r[6],
                    "max_entry_delay_pct": r[7], "actions_json": r[8],
                    "webhook_url": r[9], "email_recipients": r[10], "is_active": r[11],
                    "last_triggered_at": r[12], "trigger_count": r[13],
                    "created_at": r[14], "updated_at": r[15],
                }
                # Parse actions_json
                if isinstance(item.get("actions_json"), str):
                    try:
                        item["actions"] = json.loads(item["actions_json"])
                    except Exception:
                        item["actions"] = ["browser"]
                else:
                    item["actions"] = item.get("actions_json") or ["browser"]
                item["is_active"] = bool(item.get("is_active", 1))
                results.append(item)
            return {"status": "ok", "rules": results, "total": len(results)}

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.exception("Error loading alert rules: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/alerts/rules")
async def create_alert_rule(payload: AlertRulePayload):
    """Create a new custom alert rule."""
    def _create():
        now_iso = datetime.now(timezone.utc).isoformat()
        rule_id = f"rule_{uuid.uuid4().hex[:10]}"
        actions_str = json.dumps(payload.actions_json) if isinstance(payload.actions_json, list) else str(payload.actions_json)

        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO alert_rules (
                    id, name, strategy, min_score, min_volume_surge, tier,
                    target_universe, max_entry_delay_pct, actions_json,
                    webhook_url, email_recipients, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    payload.name,
                    payload.strategy,
                    payload.min_score,
                    payload.min_volume_surge,
                    payload.tier,
                    payload.target_universe,
                    payload.max_entry_delay_pct,
                    actions_str,
                    payload.webhook_url,
                    payload.email_recipients,
                    1 if payload.is_active else 0,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            return {"status": "ok", "message": "Alert rule created", "id": rule_id}

    try:
        return await asyncio.to_thread(_create)
    except Exception as e:
        logger.exception("Error creating alert rule: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/alerts/test-dispatch")
async def test_dispatch_alert(payload: TestDispatchPayload):
    """Dispatch a test alert notification to verify browser, webhook, or email channels."""
    now_iso = datetime.now(timezone.utc).isoformat()
    channel = payload.channel.lower()

    details = {
        "channel": channel,
        "ticker": payload.sample_ticker,
        "strategy": payload.sample_strategy,
        "score": payload.sample_score,
        "volume_surge": f"{payload.sample_surge:.1f}x",
        "timestamp": now_iso,
    }

    if channel == "webhook":
        if not payload.webhook_url:
            raise HTTPException(status_code=400, detail="Webhook URL is required for webhook test dispatch")
        import urllib.request
        try:
            req_data = json.dumps({
                "event": "nexus_alert_test",
                "title": f"⚡ Nexus Test Alert: {payload.sample_ticker}",
                "message": f"Rule triggered for {payload.sample_ticker} ({payload.sample_strategy}) with Score {payload.sample_score} and Volume Surge {payload.sample_surge:.1f}x",
                "data": details,
            }).encode("utf-8")
            req = urllib.request.Request(
                payload.webhook_url,
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "Nexus-Alerts/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp_code = resp.getcode()
            return {"status": "ok", "channel": "webhook", "http_status": resp_code, "message": f"Webhook test delivered to {payload.webhook_url}"}
        except Exception as e:
            logger.warning("Webhook test dispatch failed: %s", e)
            return {"status": "error", "channel": "webhook", "error": str(e), "message": "Webhook request failed or timed out"}

    elif channel == "email":
        recipients = payload.email_recipients or "configured admin"
        # Log simulated test dispatch
        logger.info("[ALERT TEST] Email dispatch simulated for %s -> %s", payload.sample_ticker, recipients)
        return {
            "status": "ok",
            "channel": "email",
            "recipients": recipients,
            "message": f"Simulated test alert email dispatched to {recipients}",
        }

    # Browser HTML5 notification payload
    return {
        "status": "ok",
        "channel": "browser",
        "notification": {
            "title": f"⚡ Nexus Signal: {payload.sample_ticker}",
            "body": f"Breakout score {payload.sample_score} | Vol {payload.sample_surge:.1f}x | Strategy: {payload.sample_strategy}",
            "tag": f"alert-{payload.sample_ticker}",
            "icon": "/static/favicon.ico",
        },
    }


@router.get("/api/v1/alerts/logs")
async def get_alert_logs(
    rule_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Retrieve execution history and dispatch status logs."""
    def _fetch():
        with get_db_connection() as conn:
            if rule_id:
                cur = conn.execute(
                    """
                    SELECT id, rule_id, ticker, strategy, score, volume_surge,
                           channels_dispatched, status, details, triggered_at
                    FROM alert_rule_logs
                    WHERE rule_id = ?
                    ORDER BY triggered_at DESC
                    LIMIT ?
                    """,
                    (rule_id, limit),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, rule_id, ticker, strategy, score, volume_surge,
                           channels_dispatched, status, details, triggered_at
                    FROM alert_rule_logs
                    ORDER BY triggered_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = dict(r) if hasattr(r, "keys") else {
                    "id": r[0], "rule_id": r[1], "ticker": r[2], "strategy": r[3],
                    "score": r[4], "volume_surge": r[5], "channels_dispatched": r[6],
                    "status": r[7], "details": r[8], "triggered_at": r[9],
                }
                results.append(item)
            return {"status": "ok", "logs": results, "total": len(results)}

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.exception("Error loading alert logs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# PARAMETERIZED ROUTES (Defined AFTER Literal Routes)
# ---------------------------------------------------------------------------

@router.put("/api/v1/alerts/rules/{rule_id}")
async def update_alert_rule(rule_id: str, payload: AlertRulePayload):
    """Update an existing alert rule or toggle active state."""
    def _update():
        now_iso = datetime.now(timezone.utc).isoformat()
        actions_str = json.dumps(payload.actions_json) if isinstance(payload.actions_json, list) else str(payload.actions_json)

        with get_db_connection() as conn:
            cur = conn.execute(
                """
                UPDATE alert_rules
                SET name = ?, strategy = ?, min_score = ?, min_volume_surge = ?,
                    tier = ?, target_universe = ?, max_entry_delay_pct = ?,
                    actions_json = ?, webhook_url = ?, email_recipients = ?,
                    is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name,
                    payload.strategy,
                    payload.min_score,
                    payload.min_volume_surge,
                    payload.tier,
                    payload.target_universe,
                    payload.max_entry_delay_pct,
                    actions_str,
                    payload.webhook_url,
                    payload.email_recipients,
                    1 if payload.is_active else 0,
                    now_iso,
                    rule_id,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Alert rule not found")
            return {"status": "ok", "message": "Alert rule updated", "id": rule_id}

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating alert rule: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete a custom alert rule and its associated execution logs."""
    def _delete():
        with get_db_connection() as conn:
            conn.execute("DELETE FROM alert_rule_logs WHERE rule_id = ?", (rule_id,))
            cur = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Alert rule not found")
            return {"status": "ok", "message": "Alert rule deleted", "id": rule_id}

    try:
        return await asyncio.to_thread(_delete)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting alert rule: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
