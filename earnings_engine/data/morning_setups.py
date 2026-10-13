"""Data ingestion, synchronization, and radar scoring engine for Morning Setups.

Features:
1. Block & Bulk Deals Ingestion (NSE daily archives + live API endpoints).
2. Upcoming Board Meetings Radar (NSE event calendar scraper + price-sensitive catalyst categorization).
3. Database retrieval, multi-attribute filtering, and summary metrics.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

import requests

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.nse_api import _get_session, fetch_event_calendar
from earnings_engine.data.prices import fetch_batch_live_quotes, load_prices_batch

logger = logging.getLogger("earnings_engine.data.morning_setups")

NSE_BULK_CSV_URL = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
NSE_BLOCK_CSV_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"
NSE_LIVE_BLOCK_API = "https://www.nseindia.com/api/block-deal"
NSE_LIVE_BULK_API = "https://www.nseindia.com/api/live-analysis-variations?index=bulk-deals"

# Catalyst Impact Classification rules
CATALYST_HIGH_KEYWORDS = [
    "FINANCIAL RESULT",
    "FINANCIAL RESULTS",
    "QUARTERLY RESULTS",
    "AUDITED RESULTS",
    "UNAUDITED RESULTS",
    "BONUS",
    "SPLIT",
    "SUB-DIVISION",
    "SUB DIVISION",
    "BUYBACK",
    "BUY-BACK",
    "MERGER",
    "AMALGAMATION",
    "DEMERGER",
    "ACQUISITION",
    "DELISTING",
]

CATALYST_MEDIUM_KEYWORDS = [
    "SPECIAL DIVIDEND",
    "INTERIM DIVIDEND",
    "DIVIDEND",
    "FUND RAISING",
    "QIP",
    "RIGHTS ISSUE",
    "PREFERENTIAL ALLOTMENT",
    "EXPANSION",
    "CAPEX",
    "STRATEGIC INVESTMENT",
    "JOINT VENTURE",
    "NEW BUSINESS",
    "CHANGE IN DIRECTOR",
    "APPOINTMENT",
    "CEO",
    "MD",
    "MANAGEMENT",
    "BORROWING",
]


def classify_board_meeting_impact(purpose: str) -> str:
    """Classify the corporate meeting purpose into HIGH, MEDIUM, or ROUTINE impact tier."""
    if not purpose:
        return "ROUTINE"
    p_upper = purpose.upper()
    for kw in CATALYST_HIGH_KEYWORDS:
        if kw in p_upper:
            return "HIGH"
    for kw in CATALYST_MEDIUM_KEYWORDS:
        if kw in p_upper:
            return "MEDIUM"
    return "ROUTINE"


def clean_nse_deal_symbol(sym: str) -> str:
    """Normalize NSE symbol to standard .NS equity ticker format."""
    s = (sym or "").strip().upper()
    if not s:
        return ""
    if not s.endswith(".NS"):
        return f"{s}.NS"
    return s


def enrich_tickers_with_technicals(
    tickers: list[str],
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Batch-calculate 1D, 7D, 30D returns and 20 / 50 DMA positioning from historical prices.

    Follows Point-in-Time and strict anti-fabrication standards:
    - If price history is unavailable or insufficient, returns None rather than synthetic defaults.
    - Uses load_prices_batch to retrieve OHLCV frames efficiently.
    """
    settings = settings or Settings()
    if not tickers:
        return {}

    clean_tickers = list(dict.fromkeys([clean_nse_deal_symbol(t) for t in tickers if t]))
    if not clean_tickers:
        return {}

    try:
        price_dfs = load_prices_batch(clean_tickers, settings)
    except Exception as e:
        logger.error("[MORNING-SETUPS] Failed to load batch prices for technical indicators: %s", e)
        price_dfs = {}

    results: dict[str, dict[str, Any]] = {}
    for t in clean_tickers:
        df = price_dfs.get(t)
        base_record = {
            "latest_close": None,
            "return_1d": None,
            "return_7d": None,
            "return_30d": None,
            "dma_20": None,
            "dma_50": None,
            "price_vs_dma20_pct": None,
            "price_vs_dma50_pct": None,
        }
        if df is None or df.empty or "close" not in df.columns:
            results[t] = base_record
            continue

        try:
            closes = df["close"].dropna()
            if closes.empty:
                results[t] = base_record
                continue

            latest_c = float(closes.iloc[-1])
            p1 = float(closes.iloc[-2]) if len(closes) >= 2 else None
            p7 = float(closes.iloc[-8]) if len(closes) >= 8 else (float(closes.iloc[0]) if len(closes) >= 2 else None)
            p30 = float(closes.iloc[-22]) if len(closes) >= 22 else (float(closes.iloc[0]) if len(closes) >= 2 else None)

            dma20 = round(float(closes.tail(20).mean()), 2) if len(closes) >= 20 else None
            dma50 = round(float(closes.tail(50).mean()), 2) if len(closes) >= 50 else None

            r1 = round(((latest_c / p1) - 1.0) * 100.0, 2) if p1 and p1 > 0 else None
            r7 = round(((latest_c / p7) - 1.0) * 100.0, 2) if p7 and p7 > 0 else None
            r30 = round(((latest_c / p30) - 1.0) * 100.0, 2) if p30 and p30 > 0 else None

            pct_dma20 = round(((latest_c / dma20) - 1.0) * 100.0, 2) if dma20 and dma20 > 0 else None
            pct_dma50 = round(((latest_c / dma50) - 1.0) * 100.0, 2) if dma50 and dma50 > 0 else None

            results[t] = {
                "latest_close": round(latest_c, 2),
                "return_1d": r1,
                "return_7d": r7,
                "return_30d": r30,
                "dma_20": dma20,
                "dma_50": dma50,
                "price_vs_dma20_pct": pct_dma20,
                "price_vs_dma50_pct": pct_dma50,
            }
        except Exception as err:
            logger.debug("[MORNING-SETUPS] Error computing technicals for %s: %s", t, err)
            results[t] = base_record

    return results


def enrich_grouped_deals_with_live_quotes(
    grouped_deals: list[dict[str, Any]],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Merge current/live market quotes into already-grouped deal records.

    For each group, attach the live quote fields (current_price, day_change_pct,
    is_live) and a `vs_deal_vwap_pct` that expresses where the live price sits
    relative to the group's executed VWAP. Uses the batched live-quote path with
    DB-first TTL caching, slowing to the cached/settled close on non-market hours
    rather than fabricating data.

    Anti-fabrication: if no quote could be resolved, fields are left as None /
    is_live False and the group's existing technicals still stand.
    """
    settings = settings or Settings()
    if not grouped_deals:
        return []

    tickers = list(dict.fromkeys([g.get("ticker") for g in grouped_deals if g.get("ticker")]))
    if not tickers:
        return grouped_deals

    try:
        quotes = fetch_batch_live_quotes(tickers, settings=settings)
    except Exception as e:
        logger.error("[MORNING-SETUPS] Failed to fetch live quotes for grouped deals: %s", e)
        quotes = {}

    enriched: list[dict[str, Any]] = []
    for g in grouped_deals:
        g_out = dict(g)
        t = g.get("ticker")
        quote = quotes.get(t) if t else None

        live_price = None
        if quote:
            try:
                live_price = float(quote.get("current_price") or 0) or None
            except (TypeError, ValueError):
                live_price = None

        vs_vwap = None
        vwap = float(g.get("vwap") or 0)
        if live_price is not None and live_price > 0 and vwap > 0:
            vs_vwap = round(((live_price / vwap) - 1.0) * 100.0, 2)

        g_out["live_price"] = live_price
        g_out["live_day_change_pct"] = quote.get("day_change_pct") if quote else None
        g_out["live_is_live"] = bool(quote.get("is_live")) if quote else False
        g_out["live_last_updated"] = quote.get("last_updated") if quote else None
        g_out["vs_deal_vwap_pct"] = vs_vwap
        enriched.append(g_out)

    return enriched


def parse_date_to_iso(dt_str: str | None) -> str:
    """Parse various date formats (DD-MMM-YYYY, DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY) into YYYY-MM-DD."""
    if not dt_str:
        return datetime.now().strftime("%Y-%m-%d")
    dt_str = str(dt_str).strip()

    # Check if already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dt_str):
        return dt_str

    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d-%b-%y"):
        try:
            return datetime.strptime(dt_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try regex matching day-month-year
    match = re.search(r"(\d{1,2})[-/]([A-Za-z]{3}|\d{1,2})[-/](\d{2,4})", dt_str)
    if match:
        d, m, y = match.groups()
        if len(y) == 2:
            y = f"20{y}"
        if m.isalpha():
            try:
                return datetime.strptime(f"{d}-{m}-{y}", "%d-%b-%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        else:
            try:
                return datetime.strptime(f"{d}-{m}-{y}", "%d-%m-%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

    return datetime.now().strftime("%Y-%m-%d")


def fetch_and_parse_deals_csv(url: str, deal_type: str, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Download and parse NSE Block / Bulk deals official CSV file."""
    sess = session or _get_session()
    deals: list[dict[str, Any]] = []
    try:
        resp = sess.get(url, timeout=15)
        if resp.status_code != 200 or not resp.text.strip():
            logger.warning("[MORNING-SETUPS] Failed to fetch %s CSV (HTTP %d)", deal_type, resp.status_code)
            return deals

        csv_text = resp.text
        # Clean potential BOM or leading whitespace
        csv_text = csv_text.lstrip("﻿")
        reader = csv.reader(io.StringIO(csv_text))

        headers = [h.strip().upper() for h in next(reader, [])]
        if not headers:
            return deals

        # Identify column indices flexibly
        # Format: Date, Symbol, Security Name, Client Name, Buy/Sell, Quantity Traded, Trade Price / Wght. Avg. Price
        date_idx = next((i for i, h in enumerate(headers) if "DATE" in h), 0)
        sym_idx = next((i for i, h in enumerate(headers) if "SYMBOL" in h), 1)
        sec_idx = next((i for i, h in enumerate(headers) if "SECURITY" in h), 2)
        client_idx = next((i for i, h in enumerate(headers) if "CLIENT" in h), 3)
        bs_idx = next((i for i, h in enumerate(headers) if "BUY" in h or "SELL" in h or "ACTION" in h), 4)
        qty_idx = next((i for i, h in enumerate(headers) if "QUANTITY" in h or "QTY" in h or "VOLUME" in h), 5)
        price_idx = next((i for i, h in enumerate(headers) if "PRICE" in h or "AVG" in h), 6)

        for row in reader:
            if not row or len(row) < 5:
                continue
            try:
                raw_date = row[date_idx].strip() if len(row) > date_idx else ""
                sym = row[sym_idx].strip().upper() if len(row) > sym_idx else ""
                if not sym or sym in ("SYMBOL", "DATE"):
                    continue
                sec_name = row[sec_idx].strip() if len(row) > sec_idx else ""
                client = row[client_idx].strip() if len(row) > client_idx else "Market Participant"
                bs = row[bs_idx].strip().upper() if len(row) > bs_idx else "BUY"
                tx_type = "SELL" if "SELL" in bs or bs == "S" else "BUY"

                qty_raw = row[qty_idx].replace(",", "").strip() if len(row) > qty_idx else "0"
                qty = int(float(qty_raw)) if qty_raw else 0

                price_raw = row[price_idx].replace(",", "").strip() if len(row) > price_idx else "0"
                price = float(price_raw) if price_raw else 0.0

                if qty <= 0 or price <= 0:
                    continue

                val_cr = round((qty * price) / 10000000.0, 2)
                ticker = f"{sym}.NS" if not sym.endswith(".NS") else sym
                iso_date = parse_date_to_iso(raw_date)

                deals.append({
                    "deal_date": iso_date,
                    "ticker": ticker,
                    "security_name": sec_name or sym,
                    "client_name": client,
                    "deal_type": deal_type,
                    "transaction_type": tx_type,
                    "quantity": qty,
                    "trade_price": round(price, 2),
                    "value_cr": val_cr,
                    "source": "NSE_CSV",
                })
            except Exception as row_err:
                logger.debug("[MORNING-SETUPS] Skipping malformed deal row: %s (err: %s)", row, row_err)
                continue

    except Exception as e:
        logger.warning("[MORNING-SETUPS] Exception parsing %s CSV: %s", deal_type, e)

    return deals


def fetch_live_block_deals_api(session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Fetch live morning/afternoon block deals from official NSE block-deal JSON endpoint."""
    sess = session or _get_session()
    deals: list[dict[str, Any]] = []
    try:
        resp = sess.get(NSE_LIVE_BLOCK_API, timeout=12)
        if resp.status_code != 200:
            return deals

        data = resp.json()
        if not isinstance(data, dict):
            return deals

        mkt_status = data.get("marketStatus", {})
        raw_trade_dt = mkt_status.get("tradeDate") or data.get("timestamp")
        deal_date = parse_date_to_iso(raw_trade_dt)

        items = data.get("data", [])
        for it in items:
            sym = (it.get("symbol") or "").strip().upper()
            if not sym:
                continue
            qty = int(it.get("totalTradedVolume") or it.get("quantity") or 0)
            val_raw = float(it.get("totalTradedValue") or it.get("value") or 0.0)
            price = float(it.get("lastPrice") or it.get("price") or (val_raw / qty if qty > 0 else 0.0))
            if qty <= 0 or price <= 0:
                continue

            val_cr = round(val_raw / 10000000.0, 2) if val_raw > 0 else round((qty * price) / 10000000.0, 2)
            session_label = it.get("session") or "Window 1"
            ticker = f"{sym}.NS" if not sym.endswith(".NS") else sym

            deals.append({
                "deal_date": deal_date,
                "ticker": ticker,
                "security_name": sym,
                "client_name": f"NSE Block Window ({session_label})",
                "deal_type": "BLOCK",
                "transaction_type": "BUY",
                "quantity": qty,
                "trade_price": round(price, 2),
                "value_cr": val_cr,
                "source": "NSE_LIVE",
            })
    except Exception as e:
        logger.debug("[MORNING-SETUPS] Live block deals fetch error: %s", e)

    return deals


def fetch_live_bulk_deals_api(session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Fetch live bulk deals from official NSE live-analysis variations endpoint."""
    sess = session or _get_session()
    deals: list[dict[str, Any]] = []
    try:
        resp = sess.get(NSE_LIVE_BULK_API, timeout=12)
        if resp.status_code != 200:
            return deals

        data = resp.json()
        if not isinstance(data, dict):
            return deals

        items = data.get("data", [])
        for it in items:
            sym = (it.get("symbol") or "").strip().upper()
            if not sym:
                continue
            qty = int(it.get("qty") or it.get("quantity") or it.get("totalTradedVolume") or 0)
            price = float(it.get("price") or it.get("trade_price") or it.get("lastPrice") or 0.0)
            if qty <= 0 or price <= 0:
                continue

            val_cr = round((qty * price) / 10000000.0, 2)
            cname = it.get("client") or it.get("clientName") or "Exchange Bulk Client"
            dtype = (it.get("buySell") or it.get("deal_type") or "BUY").upper()
            tx_type = "SELL" if "SELL" in dtype or dtype == "S" else "BUY"
            raw_dt = it.get("date")
            deal_date = parse_date_to_iso(raw_dt)
            ticker = f"{sym}.NS" if not sym.endswith(".NS") else sym

            deals.append({
                "deal_date": deal_date,
                "ticker": ticker,
                "security_name": sym,
                "client_name": cname,
                "deal_type": "BULK",
                "transaction_type": tx_type,
                "quantity": qty,
                "trade_price": round(price, 2),
                "value_cr": val_cr,
                "source": "NSE_LIVE",
            })
    except Exception as e:
        logger.debug("[MORNING-SETUPS] Live bulk deals fetch error: %s", e)

    return deals


def sync_all_morning_deals(settings: Settings | None = None) -> dict[str, Any]:
    """Ingest Bulk & Block deals from CSV archives and Live APIs into morning_block_deals."""
    settings = settings or Settings()
    sess = _get_session()

    # 1. Fetch from CSV archives
    bulk_csv = fetch_and_parse_deals_csv(NSE_BULK_CSV_URL, "BULK", session=sess)
    block_csv = fetch_and_parse_deals_csv(NSE_BLOCK_CSV_URL, "BLOCK", session=sess)

    # 2. Fetch from Live APIs
    block_live = fetch_live_block_deals_api(session=sess)
    bulk_live = fetch_live_bulk_deals_api(session=sess)

    all_deals = bulk_csv + block_csv + block_live + bulk_live
    if not all_deals:
        logger.info("[MORNING-SETUPS] No block/bulk deals retrieved from NSE endpoints.")
        return {"status": "ok", "inserted": 0, "total_scanned": 0, "source": "NSE"}

    conn = get_db_connection(settings)
    now_iso = datetime.now().isoformat(timespec="seconds")
    inserted_count = 0

    try:
        with conn:
            for d in all_deals:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO morning_block_deals (
                        deal_date, ticker, security_name, client_name, deal_type,
                        transaction_type, quantity, trade_price, value_cr, source,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        d["deal_date"],
                        d["ticker"],
                        d.get("security_name"),
                        d["client_name"],
                        d["deal_type"],
                        d["transaction_type"],
                        d["quantity"],
                        d["trade_price"],
                        d["value_cr"],
                        d.get("source", "NSE"),
                        now_iso,
                        now_iso,
                    ),
                )
                if cur.rowcount > 0:
                    inserted_count += 1
            conn.commit()
    except Exception as e:
        logger.error("[MORNING-SETUPS] Database error inserting block deals: %s", e)
        return {"status": "error", "error": str(e), "inserted": inserted_count}

    logger.info(
        "[MORNING-SETUPS] Ingested %d new block/bulk deals (out of %d fetched).",
        inserted_count,
        len(all_deals),
    )
    return {
        "status": "ok",
        "inserted": inserted_count,
        "total_scanned": len(all_deals),
        "updated_at": now_iso,
    }


def sync_upcoming_board_meetings(
    settings: Settings | None = None,
    days_forward: int = 45,
) -> dict[str, Any]:
    """Ingest corporate board meetings from NSE Event Calendar into upcoming_board_meetings."""
    settings = settings or Settings()
    today = date.today()
    from_date = today - timedelta(days=2) # Keep slight backward buffer for today/yesterday verification
    to_date = today + timedelta(days=days_forward)

    raw_calendar = fetch_event_calendar(from_date=from_date, to_date=to_date)
    if not raw_calendar or "error" in raw_calendar:
        err = raw_calendar.get("error") if isinstance(raw_calendar, dict) else "Unknown fetch error"
        logger.warning("[MORNING-SETUPS] Event calendar fetch returned: %s", err)
        return {"status": "error", "error": str(err), "inserted": 0}

    items: list[dict[str, Any]] = []
    if isinstance(raw_calendar, list):
        items = raw_calendar
    elif isinstance(raw_calendar, dict):
        items = raw_calendar.get("data") or raw_calendar.get("result") or []

    if not items:
        return {"status": "ok", "inserted": 0, "total_scanned": 0}

    conn = get_db_connection(settings)
    now_iso = datetime.now().isoformat(timespec="seconds")
    inserted_count = 0
    updated_count = 0

    try:
        with conn:
            for it in items:
                if not isinstance(it, dict):
                    continue

                sym = (it.get("symbol") or it.get("Symbol") or "").strip().upper()
                if not sym:
                    continue
                ticker = f"{sym}.NS" if not sym.endswith(".NS") else sym

                company_name = it.get("companyName") or it.get("sm_name") or sym
                raw_meeting_dt = it.get("date") or it.get("bm_date") or it.get("eventDate") or it.get("meetingDate")
                meeting_date = parse_date_to_iso(raw_meeting_dt)

                purpose = (it.get("purpose") or it.get("bm_purpose") or it.get("details") or "Corporate Action / Board Meeting").strip()
                details = it.get("bm_desc") or it.get("remarks") or purpose

                impact_tier = classify_board_meeting_impact(purpose + " " + (details or ""))

                # Insert or update
                cur = conn.execute(
                    """
                    INSERT INTO upcoming_board_meetings (
                        ticker, company_name, meeting_date, purpose, impact_tier, details, source, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'NSE', ?, ?)
                    ON CONFLICT(ticker, meeting_date, purpose) DO UPDATE SET
                        company_name = excluded.company_name,
                        impact_tier = excluded.impact_tier,
                        details = excluded.details,
                        updated_at = excluded.updated_at
                    """,
                    (
                        ticker,
                        company_name,
                        meeting_date,
                        purpose,
                        impact_tier,
                        details,
                        now_iso,
                        now_iso,
                    ),
                )
                if cur.rowcount == 1:
                    inserted_count += 1
                else:
                    updated_count += 1
            conn.commit()
    except Exception as e:
        logger.error("[MORNING-SETUPS] Database error inserting board meetings: %s", e)
        return {"status": "error", "error": str(e), "inserted": inserted_count}

    logger.info(
        "[MORNING-SETUPS] Board meetings sync: %d inserted/updated out of %d items.",
        inserted_count + updated_count,
        len(items),
    )
    return {
        "status": "ok",
        "inserted": inserted_count,
        "updated": updated_count,
        "total_scanned": len(items),
        "updated_at": now_iso,
    }


def store_morning_block_deals(settings: Settings | None, deals: list[dict[str, Any]]) -> int:
    """Insert or ignore block/bulk deals into SQLite database. Returns count of inserted rows."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    now_iso = datetime.now().isoformat(timespec="seconds")
    inserted = 0

    with conn:
        for d in deals:
            ticker = clean_nse_deal_symbol(d.get("ticker") or d.get("symbol") or "")
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO morning_block_deals (
                    deal_date, ticker, security_name, client_name, deal_type,
                    transaction_type, quantity, trade_price, value_cr, source,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.get("deal_date"),
                    ticker,
                    d.get("security_name") or ticker,
                    d.get("client_name") or "Market Participant",
                    (d.get("deal_type") or "BLOCK").upper(),
                    (d.get("transaction_type") or "BUY").upper(),
                    int(d.get("quantity") or 0),
                    float(d.get("trade_price") or 0.0),
                    float(d.get("value_cr") or 0.0),
                    d.get("source") or "MANUAL",
                    now_iso,
                    now_iso,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()

    return inserted


def store_upcoming_board_meetings(settings: Settings | None, meetings: list[dict[str, Any]]) -> int:
    """Insert or replace upcoming board meetings into SQLite database. Returns count of affected rows."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    now_iso = datetime.now().isoformat(timespec="seconds")
    inserted = 0

    with conn:
        for m in meetings:
            ticker = clean_nse_deal_symbol(m.get("ticker") or m.get("symbol") or "")
            cur = conn.execute(
                """
                INSERT OR REPLACE INTO upcoming_board_meetings (
                    ticker, company_name, meeting_date, purpose,
                    impact_tier, details, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    m.get("company_name") or ticker,
                    m.get("meeting_date"),
                    m.get("purpose") or "",
                    (m.get("impact_tier") or classify_board_meeting_impact(m.get("purpose") or "")).upper(),
                    m.get("details") or "",
                    m.get("source") or "MANUAL",
                    now_iso,
                    now_iso,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()

    return inserted


def get_morning_block_deals(
    settings: Settings | None = None,
    deal_type: str | None = None,
    transaction_type: str | None = None,
    min_value_cr: float | None = 0.0,
    ticker: str | None = None,
    client_name: str | None = None,
    search: str | None = None,
    date_preset: str = "ALL",
    deal_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 250,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Retrieve filtered block and bulk deals from database."""
    settings = settings or Settings()
    conn = get_db_connection(settings)

    where_clauses = ["1=1"]
    params: list[Any] = []

    if deal_type and deal_type.upper() in ("BLOCK", "BULK"):
        where_clauses.append("deal_type = ?")
        params.append(deal_type.upper())

    if transaction_type and transaction_type.upper() in ("BUY", "SELL"):
        where_clauses.append("transaction_type = ?")
        params.append(transaction_type.upper())

    if min_value_cr is not None and min_value_cr > 0:
        where_clauses.append("value_cr >= ?")
        params.append(min_value_cr)

    if ticker:
        t_clean = f"%{ticker.strip().upper()}%"
        where_clauses.append("ticker LIKE ?")
        params.append(t_clean)

    if client_name:
        c_clean = f"%{client_name.strip().upper()}%"
        where_clauses.append("client_name LIKE ?")
        params.append(c_clean)

    if search:
        s_clean = f"%{search.strip().upper()}%"
        where_clauses.append("(ticker LIKE ? OR client_name LIKE ? OR security_name LIKE ?)")
        params.extend([s_clean, s_clean, s_clean])

    today = date.today()
    if deal_date:
        where_clauses.append("deal_date = ?")
        params.append(deal_date)
    elif start_date and end_date:
        where_clauses.append("deal_date BETWEEN ? AND ?")
        params.extend([start_date, end_date])
    elif date_preset == "TODAY":
        where_clauses.append("deal_date = ?")
        params.append(today.strftime("%Y-%m-%d"))
    elif date_preset == "YESTERDAY":
        yest = today - timedelta(days=1)
        where_clauses.append("deal_date = ?")
        params.append(yest.strftime("%Y-%m-%d"))
    elif date_preset == "7D":
        d7 = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        where_clauses.append("deal_date >= ?")
        params.append(d7)
    elif date_preset == "30D":
        d30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        where_clauses.append("deal_date >= ?")
        params.append(d30)
    elif from_date and to_date:
        where_clauses.append("deal_date BETWEEN ? AND ?")
        params.extend([from_date, to_date])

    query = f"""
        SELECT id, deal_date, ticker, security_name, client_name, deal_type,
               transaction_type, quantity, trade_price, value_cr, source, created_at, updated_at
        FROM morning_block_deals
        WHERE {' AND '.join(where_clauses)}
        ORDER BY deal_date DESC, value_cr DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    deals: list[dict[str, Any]] = []
    try:
        cur = conn.execute(query, params)
        rows = cur.fetchall()
        for r in rows:
            deals.append({
                "id": r[0],
                "deal_date": r[1],
                "ticker": r[2],
                "symbol": r[2].replace(".NS", "") if r[2] else "",
                "security_name": r[3] or r[2],
                "client_name": r[4],
                "deal_type": r[5],
                "transaction_type": r[6],
                "quantity": r[7],
                "trade_price": round(float(r[8]), 2),
                "value_cr": round(float(r[9]), 2),
                "source": r[10],
                "created_at": r[11],
                "updated_at": r[12],
            })
    except Exception as e:
        logger.error("[MORNING-SETUPS] Query deals error: %s", e)

    return deals


def group_deals_by_symbol(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate individual block and bulk deals prints by ticker symbol.

    Calculates:
    - total_deals: count of deals prints for this symbol
    - gross_buy_cr, gross_sell_cr: total buys and sells in ₹ Cr
    - net_value_cr: gross_buy_cr - gross_sell_cr
    - total_quantity: sum of shares traded
    - vwap: volume-weighted average price across all prints
    - prints: list of original deal records
    """
    if not deals:
        return []

    grouped_dict: dict[str, dict[str, Any]] = {}

    for d in deals:
        sym = d.get("ticker") or "UNKNOWN.NS"
        if sym not in grouped_dict:
            grouped_dict[sym] = {
                "ticker": sym,
                "symbol": d.get("symbol") or sym.replace(".NS", ""),
                "security_name": d.get("security_name") or sym,
                "total_deals": 0,
                "block_count": 0,
                "bulk_count": 0,
                "total_quantity": 0,
                "gross_buy_cr": 0.0,
                "gross_sell_cr": 0.0,
                "net_value_cr": 0.0,
                "total_turnover_rs": 0.0,
                "vwap": 0.0,
                "latest_deal_date": d.get("deal_date"),
                "prints": [],
            }

        g = grouped_dict[sym]
        g["total_deals"] += 1
        dtype = (d.get("deal_type") or "").upper()
        if dtype == "BLOCK":
            g["block_count"] += 1
        elif dtype == "BULK":
            g["bulk_count"] += 1

        qty = int(d.get("quantity") or 0)
        price = float(d.get("trade_price") or 0.0)
        val_cr = float(d.get("value_cr") or 0.0)
        tx_type = (d.get("transaction_type") or "").upper()

        g["total_quantity"] += qty
        g["total_turnover_rs"] += (qty * price)

        if tx_type == "BUY":
            g["gross_buy_cr"] += val_cr
        elif tx_type == "SELL":
            g["gross_sell_cr"] += val_cr

        d_date = d.get("deal_date") or ""
        if d_date and (not g["latest_deal_date"] or d_date > g["latest_deal_date"]):
            g["latest_deal_date"] = d_date

        g["prints"].append(d)

    result_list = []
    for g in grouped_dict.values():
        total_qty = g["total_quantity"]
        turnover = g["total_turnover_rs"]
        vwap = round(turnover / total_qty, 2) if total_qty > 0 else 0.0
        g["vwap"] = vwap
        g["gross_buy_cr"] = round(g["gross_buy_cr"], 2)
        g["gross_sell_cr"] = round(g["gross_sell_cr"], 2)
        g["net_value_cr"] = round(g["gross_buy_cr"] - g["gross_sell_cr"], 2)
        g["total_value_cr"] = round(g["gross_buy_cr"] + g["gross_sell_cr"], 2)
        del g["total_turnover_rs"]
        result_list.append(g)

    # Sort descending by cumulative total value in Cr
    result_list.sort(key=lambda x: x["total_value_cr"], reverse=True)
    return result_list


def get_morning_deals_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Calculate overview statistics for Block & Bulk Deals."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    summary = {
        "total_deals": 0,
        "total_value_cr": 0.0,
        "block_deals_count": 0,
        "block_value_cr": 0.0,
        "bulk_deals_count": 0,
        "bulk_value_cr": 0.0,
        "buy_deals_count": 0,
        "buy_value_cr": 0.0,
        "gross_buy_cr": 0.0,
        "sell_deals_count": 0,
        "sell_value_cr": 0.0,
        "gross_sell_cr": 0.0,
        "top_tickers": [],
        "latest_deal_date": None,
    }
    try:
        cur = conn.execute("""
            SELECT
                COUNT(*) as total_count,
                COALESCE(SUM(value_cr), 0.0) as total_val,
                COALESCE(SUM(CASE WHEN deal_type = 'BLOCK' THEN 1 ELSE 0 END), 0) as blk_count,
                COALESCE(SUM(CASE WHEN deal_type = 'BLOCK' THEN value_cr ELSE 0 END), 0.0) as blk_val,
                COALESCE(SUM(CASE WHEN deal_type = 'BULK' THEN 1 ELSE 0 END), 0) as bulk_count,
                COALESCE(SUM(CASE WHEN deal_type = 'BULK' THEN value_cr ELSE 0 END), 0.0) as bulk_val,
                COALESCE(SUM(CASE WHEN transaction_type = 'BUY' THEN 1 ELSE 0 END), 0) as buy_count,
                COALESCE(SUM(CASE WHEN transaction_type = 'BUY' THEN value_cr ELSE 0 END), 0.0) as buy_val,
                COALESCE(SUM(CASE WHEN transaction_type = 'SELL' THEN 1 ELSE 0 END), 0) as sell_count,
                COALESCE(SUM(CASE WHEN transaction_type = 'SELL' THEN value_cr ELSE 0 END), 0.0) as sell_val,
                MAX(deal_date) as max_date
            FROM morning_block_deals
        """)
        row = cur.fetchone()
        if row and row[0] > 0:
            summary["total_deals"] = int(row[0])
            summary["total_value_cr"] = round(float(row[1]), 2)
            summary["block_deals_count"] = int(row[2])
            summary["block_value_cr"] = round(float(row[3]), 2)
            summary["bulk_deals_count"] = int(row[4])
            summary["bulk_value_cr"] = round(float(row[5]), 2)
            summary["buy_deals_count"] = int(row[6])
            summary["buy_value_cr"] = round(float(row[7]), 2)
            summary["gross_buy_cr"] = round(float(row[7]), 2)
            summary["sell_deals_count"] = int(row[8])
            summary["sell_value_cr"] = round(float(row[9]), 2)
            summary["gross_sell_cr"] = round(float(row[9]), 2)
            summary["latest_deal_date"] = row[10]

        # Top 5 tickers by cumulative deal value
        top_cur = conn.execute("""
            SELECT ticker, COUNT(*) as count, SUM(value_cr) as val_cr
            FROM morning_block_deals
            GROUP BY ticker
            ORDER BY val_cr DESC
            LIMIT 5
        """)
        summary["top_tickers"] = [
            {"ticker": r[0], "symbol": r[0].replace(".NS", ""), "count": r[1], "value_cr": round(float(r[2]), 2)}
            for r in top_cur.fetchall()
        ]
    except Exception as e:
        logger.error("[MORNING-SETUPS] Deals summary calculation error: %s", e)

    return summary


def get_upcoming_board_meetings(
    settings: Settings | None = None,
    ticker: str | None = None,
    impact_tier: str | None = None,
    days_ahead: int | None = 30,
    from_date: str | None = None,
    to_date: str | None = None,
    purpose_contains: str | None = None,
    search: str | None = None,
    limit: int = 250,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Retrieve upcoming board meetings categorized by catalyst impact and proximity."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    today = date.today()

    where_clauses = []
    params: list[Any] = []

    if from_date and to_date:
        where_clauses.append("meeting_date BETWEEN ? AND ?")
        params.extend([from_date, to_date])
    elif from_date:
        where_clauses.append("meeting_date >= ?")
        params.append(from_date)
    elif to_date:
        where_clauses.append("meeting_date <= ?")
        params.append(to_date)
    else:
        min_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")  # Include today
        where_clauses.append("meeting_date >= ?")
        params.append(min_date)
        if days_ahead is not None and days_ahead > 0:
            max_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            where_clauses.append("meeting_date <= ?")
            params.append(max_date)

    if ticker:
        t_clean = f"%{ticker.strip().upper()}%"
        where_clauses.append("ticker LIKE ?")
        params.append(t_clean)

    if impact_tier and impact_tier.upper() in ("HIGH", "MEDIUM", "ROUTINE"):
        where_clauses.append("impact_tier = ?")
        params.append(impact_tier.upper())

    if purpose_contains:
        p_clean = f"%{purpose_contains.strip().upper()}%"
        where_clauses.append("UPPER(purpose) LIKE ?")
        params.append(p_clean)

    if search:
        s_clean = f"%{search.strip().upper()}%"
        where_clauses.append("(ticker LIKE ? OR company_name LIKE ? OR purpose LIKE ?)")
        params.extend([s_clean, s_clean, s_clean])

    if not where_clauses:
        where_clauses.append("1=1")

    query = f"""
        SELECT id, ticker, company_name, meeting_date, purpose, impact_tier, details, source, updated_at
        FROM upcoming_board_meetings
        WHERE {' AND '.join(where_clauses)}
        ORDER BY meeting_date ASC, CASE impact_tier WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    meetings: list[dict[str, Any]] = []
    try:
        cur = conn.execute(query, params)
        rows = cur.fetchall()
        for r in rows:
            m_date_str = r[3]
            days_until = 0
            try:
                m_dt = datetime.strptime(m_date_str, "%Y-%m-%d").date()
                days_until = (m_dt - today).days
            except Exception:
                pass

            meetings.append({
                "id": r[0],
                "ticker": r[1],
                "symbol": r[1].replace(".NS", "") if r[1] else "",
                "company_name": r[2] or r[1],
                "meeting_date": m_date_str,
                "days_until": days_until,
                "purpose": r[4],
                "impact_tier": r[5],
                "details": r[6],
                "source": r[7],
                "updated_at": r[8],
            })
    except Exception as e:
        logger.error("[MORNING-SETUPS] Query board meetings error: %s", e)

    return meetings


def get_board_meetings_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Calculate summary statistics for upcoming board meetings."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    today = date.today()
    min_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    summary = {
        "total_upcoming": 0,
        "high_impact_count": 0,
        "medium_impact_count": 0,
        "routine_count": 0,
        "next_7d_count": 0,
        "next_14d_count": 0,
        "next_30d_count": 0,
        "marquee_stocks": [],
    }
    try:
        d7 = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        d14 = (today + timedelta(days=14)).strftime("%Y-%m-%d")
        d30 = (today + timedelta(days=30)).strftime("%Y-%m-%d")

        cur = conn.execute("""
            SELECT
                COUNT(*) as total_cnt,
                COALESCE(SUM(CASE WHEN impact_tier = 'HIGH' THEN 1 ELSE 0 END), 0) as high_cnt,
                COALESCE(SUM(CASE WHEN impact_tier = 'MEDIUM' THEN 1 ELSE 0 END), 0) as med_cnt,
                COALESCE(SUM(CASE WHEN impact_tier = 'ROUTINE' THEN 1 ELSE 0 END), 0) as routine_cnt,
                COALESCE(SUM(CASE WHEN meeting_date <= ? THEN 1 ELSE 0 END), 0) as d7_cnt,
                COALESCE(SUM(CASE WHEN meeting_date <= ? THEN 1 ELSE 0 END), 0) as d14_cnt,
                COALESCE(SUM(CASE WHEN meeting_date <= ? THEN 1 ELSE 0 END), 0) as d30_cnt
            FROM upcoming_board_meetings
            WHERE meeting_date >= ?
        """, (d7, d14, d30, min_date))

        row = cur.fetchone()
        if row and row[0] > 0:
            summary["total_upcoming"] = int(row[0])
            summary["high_impact_count"] = int(row[1])
            summary["medium_impact_count"] = int(row[2])
            summary["routine_count"] = int(row[3])
            summary["next_7d_count"] = int(row[4])
            summary["next_14d_count"] = int(row[5])
            summary["next_30d_count"] = int(row[6])

        # Top upcoming high-impact marquee stocks
        m_cur = conn.execute("""
            SELECT ticker, company_name, meeting_date, purpose, impact_tier
            FROM upcoming_board_meetings
            WHERE meeting_date >= ? AND impact_tier = 'HIGH'
            ORDER BY meeting_date ASC
            LIMIT 6
        """, (min_date,))
        summary["marquee_stocks"] = [
            {
                "ticker": r[0],
                "symbol": r[0].replace(".NS", ""),
                "company_name": r[1],
                "meeting_date": r[2],
                "purpose": r[3],
                "impact_tier": r[4],
            }
            for r in m_cur.fetchall()
        ]
    except Exception as e:
        logger.error("[MORNING-SETUPS] Board meetings summary error: %s", e)

    return summary
