"""FII and DII cash flow ingestion, synchronization, and net cash liquidity analysis."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import earnings_engine.data.market_pulse as mp
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.institutional_verifier import (
    MathematicalInvariantChecker,
    record_provenance,
)
from earnings_engine.data.market_pulse.constants import (
    _INSTITUTIONAL_FLOWS_SYNC_LOCK,
    _LAST_FII_DII_SYNC_ATTEMPT,
    _LIQUIDITY_CACHE,
    _LIQUIDITY_LOCK,
    _PULSE_CACHE_TTL,
)
from earnings_engine.data.market_pulse.timing import (
    compute_fii_dii_release_schedule,
    format_iso_to_ist,
    get_expected_latest_trading_date,
    is_market_open,
)
from earnings_engine.data.turso_sync import sync_single_table

logger = logging.getLogger(__name__)

def sync_real_fii_dii_cash_flows(
    settings: Settings | None = None,
    days: int = 30,
    force: bool = False,
) -> int:
    """Sync authentic daily FII / DII cash market net flows from official NSE endpoints
    and 30-day historical exchange records into SQLite institutional_net_flows.
    """
    if not _INSTITUTIONAL_FLOWS_SYNC_LOCK.acquire(blocking=False):
        logger.debug("[FII-DII-SYNC] Sync already in progress by another thread, skipping redundant sync.")
        return 0

    conn = None
    try:
        settings = settings or Settings()
        conn = get_db_connection(settings)

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS institutional_net_flows (
                    date TEXT PRIMARY KEY,
                    day_label TEXT NOT NULL,
                    fii_buy_cr REAL NOT NULL DEFAULT 0.0,
                    fii_sell_cr REAL NOT NULL DEFAULT 0.0,
                    fii_net_cr REAL NOT NULL DEFAULT 0.0,
                    dii_buy_cr REAL NOT NULL DEFAULT 0.0,
                    dii_sell_cr REAL NOT NULL DEFAULT 0.0,
                    dii_net_cr REAL NOT NULL DEFAULT 0.0,
                    total_net_cr REAL NOT NULL DEFAULT 0.0,
                    stance TEXT NOT NULL DEFAULT 'Neutral',
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_flows_date ON institutional_net_flows(date DESC)")
            conn.commit()
        except Exception as e:
            logger.debug("[FII-DII-SYNC] Table setup notice: %s", e)

        global _LAST_FII_DII_SYNC_ATTEMPT
        _LAST_FII_DII_SYNC_ATTEMPT = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        inserted_count = 0

        # 1. Fetch 30-day authentic historical time series with real buy/sell/net amounts
        try:
            hist_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get("https://www.moneycontrol.com/markets/fii-dii-data/cash/", headers=hist_headers, timeout=6)
            if resp.status_code == 200 and "__NEXT_DATA__" in resp.text:
                m = re.search(r'<script id="__NEXT_DATA__"[^>]*>({.*?})</script>', resp.text)
                if m:
                    payload = json.loads(m.group(1))
                    page_props = payload.get("props", {}).get("pageProps", {})
                    data_list = page_props.get("FiiDiiData", {}).get("fiiDiiData", [])
                    if isinstance(data_list, list) and data_list:
                        def _clean_num(val: Any) -> float:
                            if val is None:
                                return 0.0
                            s = str(val).replace(",", "").strip()
                            try:
                                return float(s)
                            except Exception:
                                return 0.0

                        db_inserts = []
                        for item in data_list:
                            iso_date = item.get("date")
                            if not iso_date:
                                continue
                            fii_buy = _clean_num(item.get("fiiPurchase") or item.get("fii_buy"))
                            fii_sell = _clean_num(item.get("fiiSales") or item.get("fii_sell"))
                            fii_net = _clean_num(item.get("fiiNet") or item.get("fii_net") or item.get("fiiCM"))

                            dii_buy = _clean_num(item.get("diiPurchase") or item.get("dii_buy"))
                            dii_sell = _clean_num(item.get("diiSale") or item.get("dii_sell"))
                            dii_net = _clean_num(item.get("diiNet") or item.get("dii_net") or item.get("diiCM"))

                            tot_net = round(fii_net + dii_net, 2)

                            try:
                                d_obj = datetime.strptime(iso_date, "%Y-%m-%d").date()
                                day_label = d_obj.strftime("%d %b (%a)")
                            except Exception:
                                day_label = item.get("graphToolTipRecordDate") or item.get("fDate") or iso_date

                            stance = "NET INFLOW (BULLISH)" if tot_net > 0 else ("NET OUTFLOW (DEFENSIVE)" if tot_net < 0 else "BALANCED FLOWS")

                            db_inserts.append((
                                iso_date, day_label, fii_buy, fii_sell, fii_net,
                                dii_buy, dii_sell, dii_net, tot_net, stance, now_iso
                            ))

                        if db_inserts:
                            conn.executemany("""
                                INSERT OR REPLACE INTO institutional_net_flows (
                                    date, day_label, fii_buy_cr, fii_sell_cr, fii_net_cr,
                                    dii_buy_cr, dii_sell_cr, dii_net_cr, total_net_cr,
                                    stance, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, db_inserts)
                            conn.commit()
                            inserted_count += len(db_inserts)
                            logger.info("[FII-DII-SYNC] Ingested %d authentic daily records from 30-day feed", len(db_inserts))
        except Exception as e:
            logger.debug("[FII-DII-SYNC] 30-day feed notice: %s", e)

        # 2. Fetch live latest day settlement from official NSE India API
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.nseindia.com/",
            })
            # Prime cookies
            session.get("https://www.nseindia.com", timeout=5)
            live_resp = session.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=6)
            if live_resp.status_code == 200:
                live_data = live_resp.json()
                if isinstance(live_data, list) and len(live_data) >= 2:
                    fii_row = next((x for x in live_data if "FII" in str(x.get("category", "")).upper() or "FPI" in str(x.get("category", "")).upper()), None)
                    dii_row = next((x for x in live_data if "DII" in str(x.get("category", "")).upper()), None)

                    if fii_row and dii_row:
                        raw_date_str = str(fii_row.get("date", "")).strip()
                        # e.g., "06-Mar-2025" or "06-Mar-2026"
                        iso_date = ""
                        day_label = raw_date_str
                        try:
                            d_obj = datetime.strptime(raw_date_str, "%d-%b-%Y").date()
                            iso_date = d_obj.strftime("%Y-%m-%d")
                            day_label = d_obj.strftime("%d %b (%a)")
                        except Exception:
                            iso_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                        fii_buy = float(fii_row.get("buyValue") or 0.0)
                        fii_sell = float(fii_row.get("sellValue") or 0.0)
                        fii_net = float(fii_row.get("netValue") or 0.0)

                        dii_buy = float(dii_row.get("buyValue") or 0.0)
                        dii_sell = float(dii_row.get("sellValue") or 0.0)
                        dii_net = float(dii_row.get("netValue") or 0.0)

                        tot_net = round(fii_net + dii_net, 2)
                        stance = "NET INFLOW (BULLISH)" if tot_net > 0 else ("NET OUTFLOW (DEFENSIVE)" if tot_net < 0 else "BALANCED FLOWS")

                        # Validate mathematical invariants before persisting
                        inv_findings = MathematicalInvariantChecker.validate_daily_cash_flow({
                            "date": iso_date,
                            "fii_buy_cr": fii_buy,
                            "fii_sell_cr": fii_sell,
                            "fii_net_cr": fii_net,
                            "dii_buy_cr": dii_buy,
                            "dii_sell_cr": dii_sell,
                            "dii_net_cr": dii_net,
                            "total_net_cr": tot_net,
                        })
                        has_critical = any(f.severity in ("CRITICAL", "CRITICAL_ERROR") for f in inv_findings)

                        record_provenance(
                            record_type="fii_dii_cash_flow",
                            entity_key=f"FII_DII:{iso_date}",
                            source_name="NSE_DAILY_FII_DII",
                            source_url="https://www.nseindia.com/api/fiidiiTradeReact",
                            payload=live_data,
                            is_authentic=not has_critical,
                            quarantine_reason=inv_findings[0].details if has_critical and inv_findings else None,
                            conn=conn,
                        )

                        conn.execute("""
                            INSERT OR REPLACE INTO institutional_net_flows (
                                date, day_label, fii_buy_cr, fii_sell_cr, fii_net_cr,
                                dii_buy_cr, dii_sell_cr, dii_net_cr, total_net_cr,
                                stance, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            iso_date, day_label, fii_buy, fii_sell, fii_net,
                            dii_buy, dii_sell, dii_net, tot_net, stance, now_iso
                        ))
                        conn.commit()
                        inserted_count += 1
                        logger.info("[FII-DII-SYNC] Ingested live NSE settlement for %s: FII Net = %.2f Cr, DII Net = %.2f Cr", iso_date, fii_net, dii_net)
        except Exception as e:
            logger.warning("[FII-DII-SYNC] Live NSE endpoint sync error: %s", e, exc_info=True)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        _INSTITUTIONAL_FLOWS_SYNC_LOCK.release()

    return inserted_count


def compute_net_cash_liquidity(settings: Settings | None = None, force_refresh: bool = False) -> dict[str, Any]:
    """Compute Net Cash Liquidity, FII vs DII breakdown, 7D/30D cumulative flows, and flow regime from authentic data."""
    now_ts = time.time()
    # Resolve live cache dictionary from package facade if available
    cache = getattr(mp, "_LIQUIDITY_CACHE", _LIQUIDITY_CACHE)
    if not force_refresh and "data" in cache:
        if (now_ts - cache.get("ts", 0)) < _PULSE_CACHE_TTL:
            return cache["data"]

    settings = settings or Settings()

    # Proactively check if the latest expected trading session's settlement is missing or if forced
    needs_sync = force_refresh
    if not needs_sync:
        check_conn = get_db_connection(settings)
        try:
            latest_row = check_conn.execute("SELECT date FROM institutional_net_flows ORDER BY date DESC LIMIT 1").fetchone()
            if not latest_row:
                needs_sync = True
            else:
                latest_date_in_db = str(latest_row[0])
                expected_date = get_expected_latest_trading_date()
                if latest_date_in_db < expected_date:
                    # Apply cooldown (3 min) to prevent repeated hammering if exchange holiday or delay
                    last_attempt = getattr(mp, "_LAST_FII_DII_SYNC_ATTEMPT", _LAST_FII_DII_SYNC_ATTEMPT)
                    if (now_ts - last_attempt) > 180.0:
                        needs_sync = True
        except Exception:
            needs_sync = True
        finally:
            try:
                check_conn.close()
            except Exception:
                pass

    if needs_sync:
        try:
            sync_fn = getattr(mp, "sync_real_fii_dii_cash_flows", sync_real_fii_dii_cash_flows)
            sync_fn(settings, days=30, force=force_refresh)
        except Exception as e:
            logger.debug("[LIQUIDITY] Auto-sync attempt error: %s", e)

    today_dt = datetime.now(timezone.utc).date()
    today_str = today_dt.strftime("%Y-%m-%d")

    history_full: list[dict[str, Any]] = []
    read_conn = get_db_connection(settings)
    try:
        rows = read_conn.execute("SELECT * FROM institutional_net_flows ORDER BY date DESC LIMIT 45").fetchall()
        for r in rows:
            raw_updated_at = r[10] if (hasattr(r, "__len__") and len(r) > 10) else (r["updated_at"] if hasattr(r, "keys") else None)
            fii_b = float(r[2] or 0.0) if hasattr(r, "__len__") else float(r.get("fii_buy_cr", 0.0))
            fii_s = float(r[3] or 0.0) if hasattr(r, "__len__") else float(r.get("fii_sell_cr", 0.0))
            fii_n = float(r[4] or 0.0) if hasattr(r, "__len__") else float(r.get("fii_net_cr", 0.0))
            dii_b = float(r[5] or 0.0) if hasattr(r, "__len__") else float(r.get("dii_buy_cr", 0.0))
            dii_s = float(r[6] or 0.0) if hasattr(r, "__len__") else float(r.get("dii_sell_cr", 0.0))
            dii_n = float(r[7] or 0.0) if hasattr(r, "__len__") else float(r.get("dii_net_cr", 0.0))
            tot_n = float(r[8] or 0.0) if hasattr(r, "__len__") else float(r.get("total_net_cr", 0.0))
            st = str(r[9] if hasattr(r, "__len__") else r.get("stance", "Neutral"))
            d_label = str(r[1] if hasattr(r, "__len__") else r.get("day_label", ""))
            iso_d = str(r[0] if hasattr(r, "__len__") else r.get("date", ""))

            gross_turn = round(fii_b + fii_s + dii_b + dii_s, 2)
            f_bs = round(fii_b / max(1.0, fii_s), 2) if fii_s > 0 else 1.0
            d_bs = round(dii_b / max(1.0, dii_s), 2) if dii_s > 0 else 1.0
            tot_bs = round((fii_b + dii_b) / max(1.0, fii_s + dii_s), 2) if (fii_s + dii_s) > 0 else 1.0

            r_dict = {
                "date": iso_d,
                "day_label": d_label,
                "fii_buy_cr": fii_b,
                "fii_sell_cr": fii_s,
                "fii_net_cr": fii_n,
                "dii_buy_cr": dii_b,
                "dii_sell_cr": dii_s,
                "dii_net_cr": dii_n,
                "total_net_cr": tot_n,
                "gross_turnover_cr": gross_turn,
                "fii_bs_ratio": f_bs,
                "dii_bs_ratio": d_bs,
                "total_bs_ratio": tot_bs,
                "stance": st,
                "updated_at": raw_updated_at,
            }
            r_dict["arrived_at_ist"] = format_iso_to_ist(r_dict.get("updated_at"))
            history_full.append(r_dict)
    except Exception as e:
        logger.warning("[LIQUIDITY] Error loading institutional flows: %s", e)
    finally:
        try:
            read_conn.close()
        except Exception:
            pass

    # If DB still has no rows (e.g. offline test), gracefully fallback to neutral structure without synthetic randoms
    if not history_full:
        for i in range(7):
            cur_d = today_dt - timedelta(days=i)
            iso_d = cur_d.strftime("%Y-%m-%d")
            history_full.append({
                "date": iso_d,
                "day_label": cur_d.strftime("%d %b (%a)"),
                "fii_buy_cr": 0.0,
                "fii_sell_cr": 0.0,
                "fii_net_cr": 0.0,
                "dii_buy_cr": 0.0,
                "dii_sell_cr": 0.0,
                "dii_net_cr": 0.0,
                "total_net_cr": 0.0,
                "stance": "BALANCED FLOWS",
                "updated_at": None,
                "arrived_at_ist": "—",
            })

    history_7d = history_full[:7]
    history_30d = history_full[:30]

    latest_rec = history_7d[0] if history_7d else {}
    fii_net_cr = float(latest_rec.get("fii_net_cr", 0.0))
    dii_net_cr = float(latest_rec.get("dii_net_cr", 0.0))
    total_net_cr = round(fii_net_cr + dii_net_cr, 2)

    fii_buy_cr = float(latest_rec.get("fii_buy_cr", 0.0))
    fii_sell_cr = float(latest_rec.get("fii_sell_cr", 0.0))
    dii_buy_cr = float(latest_rec.get("dii_buy_cr", 0.0))
    dii_sell_cr = float(latest_rec.get("dii_sell_cr", 0.0))
    total_buy_cr = round(fii_buy_cr + dii_buy_cr, 2)
    total_sell_cr = round(fii_sell_cr + dii_sell_cr, 2)
    gross_turnover_cr = round(fii_buy_cr + fii_sell_cr + dii_buy_cr + dii_sell_cr, 2)
    fii_bs_ratio = round(fii_buy_cr / max(1.0, fii_sell_cr), 2) if fii_sell_cr > 0 else 1.0
    dii_bs_ratio = round(dii_buy_cr / max(1.0, dii_sell_cr), 2) if dii_sell_cr > 0 else 1.0
    total_bs_ratio = round(total_buy_cr / max(1.0, total_sell_cr), 2) if total_sell_cr > 0 else 1.0

    # Classify granular flow regime
    if fii_net_cr < -500 and dii_net_cr > 500:
        flow_regime = "🏢 DII Absorption Wall (Counter-Cyclical)"
    elif fii_net_cr > 500 and dii_net_cr > 500:
        flow_regime = "🟢 Dual Institutional Surge (Coordinated Inflow)"
    elif fii_net_cr < -500 and dii_net_cr < -500:
        flow_regime = "🔴 Dual Institutional Exit (Coordinated Outflow)"
    elif fii_net_cr > 500 and dii_net_cr < -500:
        flow_regime = "🏛️ FII Momentum Surge (DII Profit Taking)"
    elif total_net_cr > 300:
        flow_regime = "🟢 Moderate Institutional Inflow"
    elif total_net_cr < -300:
        flow_regime = "🔴 Moderate Institutional Outflow"
    else:
        flow_regime = "⚪ Balanced Institutional Flow"

    fii_7d_total = round(sum(h.get("fii_net_cr", 0.0) for h in history_7d), 2)
    dii_7d_total = round(sum(h.get("dii_net_cr", 0.0) for h in history_7d), 2)
    combined_7d_total = round(sum(h.get("total_net_cr", 0.0) for h in history_7d), 2)

    fii_30d_total = round(sum(h.get("fii_net_cr", 0.0) for h in history_30d), 2)
    dii_30d_total = round(sum(h.get("dii_net_cr", 0.0) for h in history_30d), 2)
    combined_30d_total = round(sum(h.get("total_net_cr", 0.0) for h in history_30d), 2)

    if combined_7d_total > 500:
        regime_badge = "🟢 Institutional Accumulation"
        bias_str = "NET INFLOW (BULLISH)"
    elif combined_7d_total < -500:
        regime_badge = "🔴 Institutional Distribution"
        bias_str = "NET OUTFLOW (DEFENSIVE)"
    else:
        regime_badge = "⚪ Neutral / Balanced Flow"
        bias_str = "BALANCED FLOWS"

    session_label = history_full[0]["day_label"] if history_full else today_str
    latest_settled_date = history_full[0]["date"] if history_full else today_str
    latest_updated_at = history_full[0].get("updated_at") if history_full else None
    latest_arrived_at_ist = format_iso_to_ist(latest_updated_at)
    release_schedule = compute_fii_dii_release_schedule(latest_date_in_db=latest_settled_date)

    liquidity_data = {
        "as_of_date": latest_settled_date,
        "session_label": session_label,
        "latest_updated_at": latest_updated_at,
        "latest_arrived_at_ist": latest_arrived_at_ist,
        "arrived_at_ist": latest_arrived_at_ist,
        "next_release_schedule": release_schedule,
        "next_release_label": release_schedule["release_label"],
        "next_release_countdown": release_schedule["countdown_text"],
        "next_release_eta_seconds": release_schedule["eta_seconds"],
        "next_release_status": release_schedule["status"],
        "is_today_settled": release_schedule["is_today_settled"],
        "fii_net_cr": fii_net_cr,
        "dii_net_cr": dii_net_cr,
        "total_net_cr": total_net_cr,
        "fii_buy_cr": fii_buy_cr,
        "fii_sell_cr": fii_sell_cr,
        "dii_buy_cr": dii_buy_cr,
        "dii_sell_cr": dii_sell_cr,
        "total_buy_cr": total_buy_cr,
        "total_sell_cr": total_sell_cr,
        "gross_turnover_cr": gross_turnover_cr,
        "fii_bs_ratio": fii_bs_ratio,
        "dii_bs_ratio": dii_bs_ratio,
        "total_bs_ratio": total_bs_ratio,
        "flow_regime": flow_regime,
        "bias": bias_str,
        "fii_7d_total": fii_7d_total,
        "dii_7d_total": dii_7d_total,
        "combined_7d_total": combined_7d_total,
        "fii_7d_total_cr": fii_7d_total,
        "dii_7d_total_cr": dii_7d_total,
        "total_7d_total_cr": combined_7d_total,
        "fii_30d_total": fii_30d_total,
        "dii_30d_total": dii_30d_total,
        "combined_30d_total": combined_30d_total,
        "fii_30d_total_cr": fii_30d_total,
        "dii_30d_total_cr": dii_30d_total,
        "total_30d_total_cr": combined_30d_total,
        "regime_badge": regime_badge,
        "history_7d": history_7d,
        "history_30d": history_30d,
        "history_extended": history_30d,
        "past_7_days": history_7d,
    }

    cache.clear()
    cache.update({"ts": now_ts, "data": liquidity_data})
    return liquidity_data


# ---------------------------------------------------------------------------
# 4. Participant Derivatives Open Interest (OI) & Long/Short Positioning
# ---------------------------------------------------------------------------

_PARTICIPANT_OI_CACHE: dict[str, Any] = {}


