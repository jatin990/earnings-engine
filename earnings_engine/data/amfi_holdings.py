"""AMFI Mutual Fund Portfolio & Holdings Ingestion Engine.

Parses AMFI and AMC monthly/quarterly portfolio disclosures, extracting all mutual fund
scheme equity holdings, share counts, market value (₹ Cr), and portfolio weights (%).
Normalizes scheme names and stock symbols for seamless integration into institutional_holdings.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

import requests

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.institutional_verifier import record_provenance

logger = logging.getLogger("earnings_engine.data.amfi_holdings")

# Standard headers for AMFI / AMC network requests
_AMFI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain, */*",
}

# Flagship mutual fund schemes across major AMCs for dynamic tracking
AMC_FLAGSHIP_SCHEMES: list[dict[str, Any]] = [
    {"fund_house": "Nippon India Mutual Fund", "scheme_name": "Nippon India Small Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Small Cap"},
    {"fund_house": "Nippon India Mutual Fund", "scheme_name": "Nippon India Growth Fund", "fund_type": "Mutual Fund (DII)", "category": "Mid Cap"},
    {"fund_house": "HDFC Mutual Fund", "scheme_name": "HDFC Mid-Cap Opportunities Fund", "fund_type": "Mutual Fund (DII)", "category": "Mid Cap"},
    {"fund_house": "HDFC Mutual Fund", "scheme_name": "HDFC Small Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Small Cap"},
    {"fund_house": "HDFC Mutual Fund", "scheme_name": "HDFC Flexi Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Flexi Cap"},
    {"fund_house": "SBI Mutual Fund", "scheme_name": "SBI Bluechip Fund", "fund_type": "Mutual Fund (DII)", "category": "Large Cap"},
    {"fund_house": "SBI Mutual Fund", "scheme_name": "SBI Small Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Small Cap"},
    {"fund_house": "SBI Mutual Fund", "scheme_name": "SBI Contra Fund", "fund_type": "Mutual Fund (DII)", "category": "Contra"},
    {"fund_house": "ICICI Prudential Mutual Fund", "scheme_name": "ICICI Prudential Value Discovery Fund", "fund_type": "Mutual Fund (DII)", "category": "Value"},
    {"fund_house": "ICICI Prudential Mutual Fund", "scheme_name": "ICICI Prudential Bluechip Fund", "fund_type": "Mutual Fund (DII)", "category": "Large Cap"},
    {"fund_house": "Quant Mutual Fund", "scheme_name": "Quant Active Fund", "fund_type": "Mutual Fund (DII)", "category": "Multi Cap"},
    {"fund_house": "Quant Mutual Fund", "scheme_name": "Quant Small Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Small Cap"},
    {"fund_house": "Quant Mutual Fund", "scheme_name": "Quant Mid Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Mid Cap"},
    {"fund_house": "PPFAS Mutual Fund", "scheme_name": "Parag Parikh Flexi Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Flexi Cap"},
    {"fund_house": "Mirae Asset Mutual Fund", "scheme_name": "Mirae Asset Large Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Large Cap"},
    {"fund_house": "Mirae Asset Mutual Fund", "scheme_name": "Mirae Asset Midcap Fund", "fund_type": "Mutual Fund (DII)", "category": "Mid Cap"},
    {"fund_house": "Kotak Mahindra Mutual Fund", "scheme_name": "Kotak Emerging Equity Fund", "fund_type": "Mutual Fund (DII)", "category": "Mid Cap"},
    {"fund_house": "Kotak Mahindra Mutual Fund", "scheme_name": "Kotak Bluechip Fund", "fund_type": "Mutual Fund (DII)", "category": "Large Cap"},
    {"fund_house": "Motilal Oswal Mutual Fund", "scheme_name": "Motilal Oswal Midcap Fund", "fund_type": "Mutual Fund (DII)", "category": "Mid Cap"},
    {"fund_house": "Bandhan Mutual Fund", "scheme_name": "Bandhan Sterling Value Fund", "fund_type": "Mutual Fund (DII)", "category": "Value"},
    {"fund_house": "UTI Mutual Fund", "scheme_name": "UTI Nifty 50 Index Fund", "fund_type": "Mutual Fund (DII)", "category": "Index"},
    {"fund_house": "DSP Mutual Fund", "scheme_name": "DSP Small Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Small Cap"},
    {"fund_house": "Axis Mutual Fund", "scheme_name": "Axis Bluechip Fund", "fund_type": "Mutual Fund (DII)", "category": "Large Cap"},
    {"fund_house": "Tata Mutual Fund", "scheme_name": "Tata Small Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Small Cap"},
    {"fund_house": "WhiteOak Capital Mutual Fund", "scheme_name": "WhiteOak Capital Flexi Cap Fund", "fund_type": "Mutual Fund (DII)", "category": "Flexi Cap"},
]

def parse_amfi_nav_feed(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Fetch and parse AMFI daily scheme feed to discover active equity schemes and AMCs."""
    url = "https://www.amfiindia.com/spages/NAVAll.txt"
    schemes: list[dict[str, Any]] = []
    try:
        resp = requests.get(url, headers=_AMFI_HEADERS, timeout=15)
        if resp.status_code == 200:
            try:
                conn = get_db_connection(settings or Settings())
                record_provenance(
                    record_type="amfi_nav_feed",
                    entity_key=f"AMFI_NAV:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                    source_name="AMFI_DAILY_NAV",
                    source_url=url,
                    payload=resp.text[:50000],
                    is_authentic=True,
                    conn=conn,
                )
            except Exception as e:
                logger.debug("[AMFI] Provenance record notice: %s", e)

            lines = resp.text.splitlines()
            current_amc = ""
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if ";" not in line and not line.startswith("Open Ended") and not line.startswith("Close Ended"):
                    current_amc = line
                    continue
                parts = line.split(";")
                if len(parts) >= 6 and parts[0].isdigit():
                    schemes.append({
                        "scheme_code": parts[0],
                        "isin": parts[1],
                        "scheme_name": parts[3],
                        "fund_house": current_amc or "Indian Mutual Fund",
                        "nav": float(parts[6]) if len(parts) > 6 and parts[6].replace(".", "", 1).isdigit() else None,
                        "date": parts[7] if len(parts) > 7 else None,
                    })
    except Exception as e:
        logger.warning("[AMFI] NAV feed parse warning: %s", e)
    return schemes


def save_discovered_fund_holdings(
    holdings: list[dict[str, Any]],
    settings: Settings | None = None,
    conn: Any = None,
) -> int:
    """Store all dynamically parsed mutual fund holdings into the institutional_holdings database table."""
    if not holdings:
        return 0

    settings = settings or Settings()
    from earnings_engine.data.institutional_accumulation import init_institutional_db
    init_institutional_db(settings)

    local_conn = conn or get_db_connection(settings)
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = 0

    # Pre-fetch existing record IDs in batch using chunked IN queries
    tickers_in_batch = list({
        (h.get("ticker", "").strip().upper() if (h.get("ticker", "").strip().upper().endswith(".NS") or h.get("ticker", "").strip().upper().endswith(".BO") or "." in h.get("ticker", "").strip().upper()) else f"{h.get('ticker', '').strip().upper()}.NS")
        for h in holdings if h.get("ticker")
    })
    existing_map: dict[tuple[str, str, str], int] = {}
    if tickers_in_batch:
        chunk_size = 200
        for i in range(0, len(tickers_in_batch), chunk_size):
            chunk = tickers_in_batch[i : i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            ex_rows = local_conn.execute(
                f"SELECT id, ticker, fund_name, quarter FROM institutional_holdings WHERE ticker IN ({placeholders})",
                chunk,
            ).fetchall()
            for r in ex_rows:
                existing_map[(r[1], r[2], r[3])] = r[0]

    update_rows: list[tuple[Any, ...]] = []
    insert_rows: list[tuple[Any, ...]] = []

    for h in holdings:
        ticker = h.get("ticker", "").strip().upper()
        if not ticker:
            continue
        if not (ticker.endswith(".NS") or ticker.endswith(".BO") or "." in ticker):
            ticker = f"{ticker}.NS"

        fund_name = h.get("fund_name", "").strip()
        if not fund_name:
            continue

        fund_type = h.get("fund_type", "Mutual Fund (DII)")
        quarter = h.get("quarter", "Q1 FY27")
        shares = int(h.get("shares_held", 0) or 0)
        stake_pct = round(float(h.get("stake_pct", 0.0) or 0.0), 2)
        val_cr = round(float(h.get("holding_value_cr", 0.0) or 0.0), 2)
        prev_stake = float(h.get("prev_stake_pct")) if h.get("prev_stake_pct") is not None else None
        action = (h.get("action") or "HOLD").upper()
        change_shares = int(h.get("change_shares", 0) or 0)
        change_pct = round(float(h.get("change_pct", 0.0) or 0.0), 2)
        avg_price = round(float(h.get("avg_price")), 2) if h.get("avg_price") is not None and float(h.get("avg_price") or 0.0) > 0 else None
        recent_buy = round(float(h.get("recent_buy_price", 0.0) or 0.0), 2) if h.get("recent_buy_price") else None
        recent_txn_p = round(float(h.get("recent_txn_price", 0.0) or 0.0), 2) if h.get("recent_txn_price") else None
        recent_txn_d = h.get("recent_txn_date")
        recent_txn_t = h.get("recent_txn_type")
        rep_date = h.get("reported_date") or now_iso[:10]
        inc_amt_cr = round(float(h.get("increase_amount_cr", 0.0) or 0.0), 2)
        tot_amt_cr = val_cr if val_cr > 0 else round(float(h.get("total_amount_cr", 0.0) or 0.0), 2)

        key = (ticker, fund_name, quarter)
        existing_id = existing_map.get(key)

        if existing_id is not None:
            update_rows.append((
                fund_type, shares, stake_pct, val_cr,
                prev_stake, action, change_shares, change_pct,
                avg_price, recent_buy, recent_txn_p,
                recent_txn_d, recent_txn_t, rep_date,
                inc_amt_cr, tot_amt_cr,
                existing_id,
            ))
        else:
            insert_rows.append((
                ticker, fund_name, fund_type, quarter, shares, stake_pct,
                val_cr, prev_stake, action, change_shares, change_pct,
                avg_price, recent_buy, recent_txn_p, recent_txn_d,
                recent_txn_t, rep_date, now_iso, inc_amt_cr, tot_amt_cr,
            ))
            # Mark a sentinel ID so subsequent identical items in the same batch update or don't duplicate
            existing_map[key] = -1
        inserted += 1

    if update_rows:
        local_conn.executemany(
            """
            UPDATE institutional_holdings SET
                fund_type = ?, shares_held = ?, stake_pct = ?, holding_value_cr = ?,
                prev_stake_pct = ?, action = ?, change_shares = ?, change_pct = ?,
                avg_price = ?, recent_buy_price = ?, recent_txn_price = ?,
                recent_txn_date = ?, recent_txn_type = ?, reported_date = ?,
                increase_amount_cr = ?, total_amount_cr = ?
            WHERE id = ?
            """,
            update_rows,
        )

    if insert_rows:
        local_conn.executemany(
            """
            INSERT INTO institutional_holdings (
                ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                holding_value_cr, prev_stake_pct, action, change_shares, change_pct,
                avg_price, recent_buy_price, recent_txn_price, recent_txn_date,
                recent_txn_type, reported_date, created_at, increase_amount_cr, total_amount_cr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            insert_rows,
        )

    if hasattr(local_conn, "commit"):
        local_conn.commit()

    logger.info("[AMFI] Persisted %d institutional fund holding records.", inserted)
    return inserted

