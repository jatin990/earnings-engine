"""Recent Market Additions & IPOs Tracker for Indian Equities (NSE).

Tracks newly listed companies on the National Stock Exchange of India (NSE),
identifies listing dates, calculates market debut age, cross-references watchlists,
and flags 1st and 2nd post-IPO earnings releases.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger("earnings_engine.data.new_listings")

# In-memory cache for official NSE equity list to prevent repetitive downloads
_EQUITY_LIST_CACHE: dict[str, Any] = {"timestamp": None, "data": None}
CACHE_TTL_SECONDS = 3600  # 1 hour TTL


def fetch_all_nse_equities_cached() -> pd.DataFrame:
    """Fetch all listed equities from official NSE directory with in-memory caching."""
    now = datetime.now()
    if (
        _EQUITY_LIST_CACHE["timestamp"] is not None
        and _EQUITY_LIST_CACHE["data"] is not None
        and (now - _EQUITY_LIST_CACHE["timestamp"]).total_seconds() < CACHE_TTL_SECONDS
    ):
        return _EQUITY_LIST_CACHE["data"].copy()

    # 1. Try nselib if installed
    logger.info("[NSELIB:REQ] capital_market.equity_list()")
    t0 = time.perf_counter()
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("nse")
        except Exception:
            pass
        from nselib import capital_market
        df = capital_market.equity_list()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        df.columns = [c.strip() for c in df.columns]

        # Clean columns: SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, FACE VALUE
        if "DATE OF LISTING" in df.columns:
            df["LISTING_DATE"] = pd.to_datetime(df["DATE OF LISTING"], format="%d-%b-%Y", errors="coerce")
        else:
            df["LISTING_DATE"] = pd.NaT

        _EQUITY_LIST_CACHE["timestamp"] = now
        _EQUITY_LIST_CACHE["data"] = df
        logger.info("[NSELIB:RESP] capital_market.equity_list() -> %d equities (%.1fms)", len(df), elapsed_ms)
        return df.copy()
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning("[NSELIB:FAIL] capital_market.equity_list() failed after %.1fms: %s", elapsed_ms, e)

    # 2. Direct fallback to official NSE archives CSV (zero binary dependency)
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    logger.info("[NSE:REQ] GET %s", url)
    t0_nse = time.perf_counter()
    try:
        import io
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        elapsed_ms = (time.perf_counter() - t0_nse) * 1000
        try:
            from earnings_engine.rate_limits import record_request
            record_request("nse", status_code=resp.status_code)
        except Exception:
            pass

        if resp.status_code == 200 and len(resp.content) > 0:
            df = pd.read_csv(io.BytesIO(resp.content))
            df.columns = [c.strip() for c in df.columns]
            if "DATE OF LISTING" in df.columns:
                df["LISTING_DATE"] = pd.to_datetime(df["DATE OF LISTING"], format="%d-%b-%Y", errors="coerce")
            else:
                df["LISTING_DATE"] = pd.NaT

            _EQUITY_LIST_CACHE["timestamp"] = now
            _EQUITY_LIST_CACHE["data"] = df
            logger.info("[NSE:RESP] GET %s -> %d equities (%.1fms, HTTP %d)", url, len(df), elapsed_ms, resp.status_code)
            return df.copy()
        else:
            logger.warning("[NSE:FAIL] GET %s returned status %d after %.1fms", url, resp.status_code, elapsed_ms)
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0_nse) * 1000
        logger.warning("[NSE:FAIL] Failed to fetch equity list from direct NSE archives after %.1fms: %s", elapsed_ms, e)

    if _EQUITY_LIST_CACHE["data"] is not None:
        return _EQUITY_LIST_CACHE["data"].copy()
    return pd.DataFrame(columns=["SYMBOL", "NAME OF COMPANY", "SERIES", "DATE OF LISTING", "LISTING_DATE"])


def get_recent_nse_additions(
    days: int = 180,
    limit: int = 100,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve recent market additions / IPOs listed within the last `days` days.

    Enriches each company with:
    - Days since listing
    - Formatted ticker with .NS suffix
    - Series (EQ, BE, SM for SME)
    - Watchlist presence status
    - Next earnings date (if available)
    - Result sequence (1st Result / 2nd Result / 3rd Result)
    """
    settings = settings or Settings()
    df = fetch_all_nse_equities_cached()
    if df.empty or "LISTING_DATE" not in df.columns:
        return []

    cutoff_date = datetime.now() - timedelta(days=days)
    recent_df = df[df["LISTING_DATE"] >= cutoff_date].copy()
    if recent_df.empty:
        return []

    recent_df = recent_df.sort_values(by="LISTING_DATE", ascending=False).head(limit)

    # Load existing watchlist tickers for cross-referencing
    from earnings_engine.data.watchlists import get_all_watchlist_tickers
    try:
        existing_watchlist_tickers = set(get_all_watchlist_tickers(settings))
    except Exception:
        existing_watchlist_tickers = set()

    # Load earnings dates from SQLite
    earnings_map: dict[str, dict[str, Any]] = {}
    try:
        conn = get_db_connection(settings)
        rows = conn.execute("""
            SELECT ticker, COUNT(earnings_date) as past_count, MAX(earnings_date) as last_date
            FROM earnings_history
            GROUP BY ticker
        """).fetchall()
        for r in rows:
            earnings_map[r[0]] = {"past_count": r[1], "last_date": r[2]}
    except Exception as e:
        logger.debug("[NEW-LISTINGS] Failed querying earnings_history: %s", e)

    today = datetime.now().date()
    items: list[dict[str, Any]] = []

    for _, row in recent_df.iterrows():
        raw_symbol = str(row.get("SYMBOL", "")).strip().upper()
        ticker = f"{raw_symbol}.NS"
        company_name = str(row.get("NAME OF COMPANY", raw_symbol)).strip()
        series = str(row.get("SERIES", "EQ")).strip()
        face_value = row.get("FACE VALUE", None)

        listing_dt = row.get("LISTING_DATE")
        listing_date_str = listing_dt.strftime("%Y-%m-%d") if pd.notna(listing_dt) else "Unknown"
        days_on_market = (today - listing_dt.date()).days if pd.notna(listing_dt) else 0

        ea_info = earnings_map.get(ticker, {"past_count": 0, "last_date": None})
        past_events = ea_info["past_count"]

        if past_events == 0:
            seq_num = 1
            seq_label = "🌟 1st Result (Post-IPO Debut)"
            seq_badge = "amber"
        elif past_events == 1:
            seq_num = 2
            seq_label = "🌱 2nd Public Result"
            seq_badge = "emerald"
        elif past_events == 2:
            seq_num = 3
            seq_label = "🌿 3rd Public Result"
            seq_badge = "cyan"
        else:
            seq_num = past_events + 1
            seq_label = f"Q{seq_num} Result"
            seq_badge = "slate"

        items.append({
            "ticker": ticker,
            "raw_symbol": raw_symbol,
            "company_name": company_name,
            "series": series,
            "is_sme": series in ("SM", "ST"),
            "face_value": face_value,
            "listing_date": listing_date_str,
            "days_on_market": max(0, days_on_market),
            "in_watchlist": ticker in existing_watchlist_tickers,
            "past_earnings_count": past_events,
            "result_sequence_number": seq_num,
            "result_sequence_label": seq_label,
            "result_sequence_badge": seq_badge,
        })

    return items


def compute_ticker_result_sequence(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Compute whether an upcoming earnings announcement is a company's 1st, 2nd, or 3rd public result."""
    settings = settings or Settings()
    sym = ticker.strip().upper()

    try:
        conn = get_db_connection(settings)
        row = conn.execute(
            "SELECT COUNT(earnings_date) FROM earnings_history WHERE ticker = ?",
            (sym,),
        ).fetchone()
        past_events = row[0] if row else 0
    except Exception:
        past_events = 0

    if past_events == 0:
        return {
            "result_sequence_number": 1,
            "result_sequence_label": "🌟 1st Result (Post-IPO Debut)",
            "result_sequence_badge": "amber",
            "is_debut": True,
        }
    elif past_events == 1:
        return {
            "result_sequence_number": 2,
            "result_sequence_label": "🌱 2nd Public Result",
            "result_sequence_badge": "emerald",
            "is_debut": False,
        }
    elif past_events == 2:
        return {
            "result_sequence_number": 3,
            "result_sequence_label": "🌿 3rd Public Result",
            "result_sequence_badge": "cyan",
            "is_debut": False,
        }
    else:
        return {
            "result_sequence_number": past_events + 1,
            "result_sequence_label": f"Established ({past_events} past quarters)",
            "result_sequence_badge": "slate",
            "is_debut": False,
        }
