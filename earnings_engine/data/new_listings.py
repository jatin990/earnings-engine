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

    # Collect candidate tickers for batch database queries
    tickers = [f"{str(row.get('SYMBOL', '')).strip().upper()}.NS" for _, row in recent_df.iterrows()]
    all_syms = list(set(tickers + [t.replace(".NS", "") for t in tickers if t.endswith(".NS")]))

    # Connect to SQLite database using get_db_connection
    conn = None
    try:
        conn = get_db_connection(settings)
    except Exception as e:
        logger.debug("[NEW-LISTINGS] Failed connecting to DB: %s", e)

    # Load earnings dates from SQLite
    earnings_map: dict[str, dict[str, Any]] = {}
    if conn is not None:
        try:
            rows = conn.execute("""
                SELECT ticker, COUNT(earnings_date) as past_count, MAX(earnings_date) as last_date
                FROM earnings_history
                GROUP BY ticker
            """).fetchall()
            for r in rows:
                earnings_map[r[0]] = {"past_count": r[1], "last_date": r[2]}
        except Exception as e:
            logger.debug("[NEW-LISTINGS] Failed querying earnings_history: %s", e)

    # Query price_history in batch for all recent tickers
    price_map: dict[str, list[dict[str, Any]]] = {}
    if conn is not None and all_syms:
        try:
            placeholders = ",".join("?" for _ in all_syms)
            p_rows = conn.execute(f"""
                SELECT ticker, date, open, high, low, close, volume
                FROM price_history
                WHERE ticker IN ({placeholders})
                ORDER BY ticker, date ASC
            """, all_syms).fetchall()
            for r in p_rows:
                t = str(r[0]).strip().upper()
                norm_t = f"{t}.NS" if not t.endswith(".NS") else t
                if norm_t not in price_map:
                    price_map[norm_t] = []
                price_map[norm_t].append({
                    "date": r[1],
                    "open": float(r[2]) if r[2] is not None else None,
                    "high": float(r[3]) if r[3] is not None else None,
                    "low": float(r[4]) if r[4] is not None else None,
                    "close": float(r[5]) if r[5] is not None else None,
                    "volume": float(r[6]) if r[6] is not None else None,
                })
        except Exception as e:
            logger.debug("[NEW-LISTINGS] Failed querying price_history in batch: %s", e)

    today = datetime.now().date()
    items: list[dict[str, Any]] = []

    for _, row in recent_df.iterrows():
        raw_symbol = str(row.get("SYMBOL", "")).strip().upper()
        ticker = f"{raw_symbol}.NS"
        company_name = str(row.get("NAME OF COMPANY", raw_symbol)).strip()
        series = str(row.get("SERIES", "EQ")).strip()
        raw_fv = row.get("FACE VALUE", None)
        face_value = int(raw_fv) if pd.notna(raw_fv) else None

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

        # Price history calculations
        p_history = price_map.get(ticker, [])
        cmp = None
        listing_price = None
        return_since_listing_pct = 0.0
        ath_price = None
        ath_distance_pct = 0.0
        atl_price = None
        return_7d_pct = None
        return_30d_pct = None
        volume_ratio_5_20 = None

        if p_history:
            first_close = p_history[0].get("close")
            if first_close is not None:
                listing_price = round(first_close, 2)

            latest_close = p_history[-1].get("close")
            if latest_close is not None:
                cmp = round(latest_close, 2)

            valid_highs = [h["high"] for h in p_history if h["high"] is not None]
            if valid_highs:
                ath_price = round(max(valid_highs), 2)
            elif cmp is not None:
                ath_price = cmp

            valid_lows = [h["low"] for h in p_history if h["low"] is not None]
            if valid_lows:
                atl_price = round(min(valid_lows), 2)
            elif cmp is not None:
                atl_price = cmp

            if cmp is not None and listing_price is not None and listing_price > 0:
                return_since_listing_pct = round(((cmp - listing_price) / listing_price) * 100.0, 2)

            if cmp is not None and ath_price is not None and ath_price > 0:
                ath_distance_pct = round(((cmp - ath_price) / ath_price) * 100.0, 2)

            if len(p_history) >= 6:
                idx_7 = min(7, len(p_history) - 1)
                p_7d = p_history[-1 - idx_7].get("close")
                if p_7d is not None and p_7d > 0 and cmp is not None:
                    return_7d_pct = round(((cmp - p_7d) / p_7d) * 100.0, 2)

            if len(p_history) >= 21:
                idx_30 = min(30, len(p_history) - 1)
                p_30d = p_history[-1 - idx_30].get("close")
                if p_30d is not None and p_30d > 0 and cmp is not None:
                    return_30d_pct = round(((cmp - p_30d) / p_30d) * 100.0, 2)

            if len(p_history) >= 5:
                v5 = [h["volume"] for h in p_history[-5:] if h["volume"] is not None]
                v20 = [h["volume"] for h in p_history[-20:] if h["volume"] is not None]
                avg_v5 = sum(v5) / len(v5) if v5 else 0.0
                avg_v20 = sum(v20) / len(v20) if v20 else 0.0
                if avg_v20 > 0:
                    volume_ratio_5_20 = round(avg_v5 / avg_v20, 2)

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
            "cmp": cmp,
            "listing_price": listing_price,
            "return_since_listing_pct": return_since_listing_pct,
            "ath_price": ath_price,
            "ath_distance_pct": ath_distance_pct,
            "atl_price": atl_price,
            "return_7d_pct": return_7d_pct,
            "return_30d_pct": return_30d_pct,
            "volume_ratio_5_20": volume_ratio_5_20,
        })

    return items


def compute_ticker_result_sequence(
    ticker: str,
    settings: Settings | None = None,
    past_events_count: int | None = None,
) -> dict[str, Any]:
    """Compute whether an upcoming earnings announcement is a company's 1st, 2nd, or 3rd public result."""
    sym = ticker.strip().upper()

    if past_events_count is not None:
        past_events = past_events_count
    else:
        settings = settings or Settings()
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


def get_ipo_stock_detail(
    ticker: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve comprehensive technical, earnings lifecycle, and institutional intelligence for an IPO stock.

    Cross-references official NSE equity directory, SQLite price_history, earnings_history,
    earnings_calendar, institutional_holdings / amfi_holdings, shareholding_patterns, and block deals.
    """
    settings = settings or Settings()
    raw = (ticker or "").strip().upper()
    if not raw:
        return {"success": False, "error": "Ticker cannot be empty"}

    if not raw.endswith(".NS") and not raw.endswith(".BO") and "." not in raw:
        clean_ticker = f"{raw}.NS"
    else:
        clean_ticker = raw
    raw_symbol = clean_ticker.split(".")[0]

    # Connect to SQLite database
    conn = None
    try:
        conn = get_db_connection(settings)
    except Exception as e:
        logger.debug("[IPO-DETAIL] Failed connecting to DB: %s", e)

    # 1. Company metadata from official cached NSE equity list
    company_name = raw_symbol
    series = "EQ"
    face_value = None
    listing_date_str = "Unknown"
    days_on_market = 0
    today = datetime.now().date()

    try:
        df = fetch_all_nse_equities_cached()
        if not df.empty and "SYMBOL" in df.columns:
            matched = df[df["SYMBOL"].str.strip().str.upper() == raw_symbol]
            if not matched.empty:
                r_meta = matched.iloc[0]
                company_name = str(r_meta.get("NAME OF COMPANY", raw_symbol)).strip()
                series = str(r_meta.get("SERIES", "EQ")).strip()
                raw_fv = r_meta.get("FACE VALUE", None)
                face_value = int(raw_fv) if pd.notna(raw_fv) else None
                listing_dt = r_meta.get("LISTING_DATE")
                if pd.notna(listing_dt):
                    listing_date_str = listing_dt.strftime("%Y-%m-%d")
                    days_on_market = max(0, (today - listing_dt.date()).days)
                elif "DATE OF LISTING" in r_meta and pd.notna(r_meta["DATE OF LISTING"]):
                    listing_date_str = str(r_meta["DATE OF LISTING"]).strip()
    except Exception as e:
        logger.debug("[IPO-DETAIL] Failed fetching equity list metadata for %s: %s", clean_ticker, e)

    is_sme = series in ("SM", "ST")

    # 2. Query price_history ordered by date ASC
    price_rows: list[Any] = []
    if conn is not None:
        try:
            price_rows = conn.execute("""
                SELECT date, open, high, low, close, volume
                FROM price_history
                WHERE ticker IN (?, ?)
                ORDER BY date ASC
            """, (clean_ticker, raw_symbol)).fetchall()
        except Exception as e:
            logger.debug("[IPO-DETAIL] Failed querying price_history for %s: %s", clean_ticker, e)

    listing_day: dict[str, Any] | None = None
    cmp: float | None = None
    latest_date: str | None = None
    listing_price: float | None = None
    return_since_listing_pct = 0.0
    ath_price: float | None = None
    ath_distance_pct = 0.0
    atl_price: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    return_7d_pct: float | None = None
    return_30d_pct: float | None = None
    sma_20: float | None = None
    volume_ratio_5_20: float | None = None
    stage = "New Debut (Awaiting Market History)"
    stage_badge = "slate"

    if price_rows:
        r0 = price_rows[0]
        listing_day = {
            "date": str(r0[0]),
            "open": round(float(r0[1]), 2) if r0[1] is not None else None,
            "high": round(float(r0[2]), 2) if r0[2] is not None else None,
            "low": round(float(r0[3]), 2) if r0[3] is not None else None,
            "close": round(float(r0[4]), 2) if r0[4] is not None else None,
            "volume": int(r0[5]) if r0[5] is not None else None,
        }
        listing_price = listing_day["close"]
        if listing_date_str == "Unknown" and listing_day["date"]:
            listing_date_str = listing_day["date"]
            try:
                l_date = datetime.strptime(listing_date_str, "%Y-%m-%d").date()
                days_on_market = max(0, (today - l_date).days)
            except Exception:
                pass

        r_last = price_rows[-1]
        latest_date = str(r_last[0])
        cmp = round(float(r_last[4]), 2) if r_last[4] is not None else None

        highs = [float(r[2]) for r in price_rows if r[2] is not None]
        ath_price = round(max(highs), 2) if highs else cmp

        lows = [float(r[3]) for r in price_rows if r[3] is not None]
        atl_price = round(min(lows), 2) if lows else cmp

        rows_52w = price_rows[-252:]
        highs_52w = [float(r[2]) for r in rows_52w if r[2] is not None]
        high_52w = round(max(highs_52w), 2) if highs_52w else ath_price
        lows_52w = [float(r[3]) for r in rows_52w if r[3] is not None]
        low_52w = round(min(lows_52w), 2) if lows_52w else atl_price

        if cmp is not None and listing_price is not None and listing_price > 0:
            return_since_listing_pct = round(((cmp - listing_price) / listing_price) * 100.0, 2)

        if cmp is not None and ath_price is not None and ath_price > 0:
            ath_distance_pct = round(((cmp - ath_price) / ath_price) * 100.0, 2)

        if len(price_rows) >= 6:
            idx_7 = min(7, len(price_rows) - 1)
            p_7d = price_rows[-1 - idx_7][4]
            if p_7d is not None and float(p_7d) > 0 and cmp is not None:
                return_7d_pct = round(((cmp - float(p_7d)) / float(p_7d)) * 100.0, 2)

        if len(price_rows) >= 21:
            idx_30 = min(30, len(price_rows) - 1)
            p_30d = price_rows[-1 - idx_30][4]
            if p_30d is not None and float(p_30d) > 0 and cmp is not None:
                return_30d_pct = round(((cmp - float(p_30d)) / float(p_30d)) * 100.0, 2)

        if len(price_rows) >= 20:
            closes_20 = [float(r[4]) for r in price_rows[-20:] if r[4] is not None]
            if closes_20:
                sma_20 = round(sum(closes_20) / len(closes_20), 2)

        if len(price_rows) >= 5:
            v5 = [float(r[5]) for r in price_rows[-5:] if r[5] is not None]
            v20 = [float(r[5]) for r in price_rows[-20:] if r[5] is not None]
            avg_v5 = sum(v5) / len(v5) if v5 else 0.0
            avg_v20 = sum(v20) / len(v20) if v20 else 0.0
            if avg_v20 > 0:
                volume_ratio_5_20 = round(avg_v5 / avg_v20, 2)

        # Classify IPO Base Stage:
        # - If ath_distance_pct >= -2.5: "🔥 IPO Base Breakout (At ATH)"
        # - Else if ath_distance_pct >= -15.0: "🟡 Forming IPO Base (Consolidating near ATH)"
        # - Else if cmp < listing_price: "❄️ Sub-IPO Drawdown (Trading Below Debut)"
        # - Else: "📈 Post-Listing Consolidation"
        if ath_distance_pct >= -2.5:
            stage = "🔥 IPO Base Breakout (At ATH)"
            stage_badge = "emerald"
        elif ath_distance_pct >= -15.0:
            stage = "🟡 Forming IPO Base (Consolidating near ATH)"
            stage_badge = "amber"
        elif cmp is not None and listing_price is not None and cmp < listing_price:
            stage = "❄️ Sub-IPO Drawdown (Trading Below Debut)"
            stage_badge = "rose"
        else:
            stage = "📈 Post-Listing Consolidation"
            stage_badge = "blue"

    technical = {
        "listing_day": listing_day,
        "cmp": cmp,
        "latest_date": latest_date,
        "listing_price": listing_price,
        "return_since_listing_pct": return_since_listing_pct,
        "ath_price": ath_price,
        "ath_distance_pct": ath_distance_pct,
        "atl_price": atl_price,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "return_7d_pct": return_7d_pct,
        "return_30d_pct": return_30d_pct,
        "sma_20": sma_20,
        "volume_ratio_5_20": volume_ratio_5_20,
        "stage": stage,
        "stage_badge": stage_badge,
    }

    # 3. Query earnings_history & earnings_calendar
    past_count = 0
    last_reported: dict[str, Any] | None = None
    upcoming_result: dict[str, Any] | None = None

    if conn is not None:
        try:
            past_rows = conn.execute("""
                SELECT earnings_date, eps_reported, eps_estimate, surprise_pct, source
                FROM earnings_history
                WHERE ticker IN (?, ?)
                ORDER BY earnings_date DESC
            """, (clean_ticker, raw_symbol)).fetchall()

            past_count = len(past_rows)
            if past_rows:
                lr = past_rows[0]
                last_reported = {
                    "earnings_date": str(lr[0]),
                    "eps_reported": float(lr[1]) if lr[1] is not None else None,
                    "eps_estimate": float(lr[2]) if lr[2] is not None else None,
                    "surprise_pct": float(lr[3]) if lr[3] is not None else None,
                    "source": str(lr[4]) if lr[4] else "unknown",
                }
        except Exception as e:
            logger.debug("[IPO-DETAIL] Failed querying earnings_history for %s: %s", clean_ticker, e)

        today_str = today.strftime("%Y-%m-%d")
        try:
            cal_row = conn.execute("""
                SELECT earnings_date, eps_estimate, source
                FROM earnings_calendar
                WHERE ticker IN (?, ?) AND (earnings_date >= ? OR source = 'nse')
                ORDER BY earnings_date ASC
                LIMIT 1
            """, (clean_ticker, raw_symbol, today_str)).fetchone()
            if cal_row:
                upcoming_result = {
                    "earnings_date": str(cal_row[0]),
                    "eps_estimate": float(cal_row[1]) if cal_row[1] is not None else None,
                    "source": str(cal_row[2]) if cal_row[2] else "nse",
                }
        except Exception:
            pass

        if not upcoming_result:
            try:
                hist_upcoming = conn.execute("""
                    SELECT earnings_date, eps_estimate, source
                    FROM earnings_history
                    WHERE ticker IN (?, ?) AND earnings_date >= ?
                    ORDER BY earnings_date ASC
                    LIMIT 1
                """, (clean_ticker, raw_symbol, today_str)).fetchone()
                if hist_upcoming:
                    upcoming_result = {
                        "earnings_date": str(hist_upcoming[0]),
                        "eps_estimate": float(hist_upcoming[1]) if hist_upcoming[1] is not None else None,
                        "source": str(hist_upcoming[2]) if hist_upcoming[2] else "unknown",
                    }
            except Exception:
                pass

    result_sequence = compute_ticker_result_sequence(clean_ticker, settings=settings, past_events_count=past_count)
    guidance_note = (
        "Under SEBI (LODR) regulations, newly listed entities are granted up to 45 days post-quarter end "
        "to disclose financial results (or 60 days for annual audited statements). Pre-IPO financials are filed "
        "in the Red Herring Prospectus (RHP); exchange disclosure history begins from the debut quarter."
    )

    earnings_lifecycle = {
        "past_earnings_count": past_count,
        "last_reported": last_reported,
        "upcoming_result": upcoming_result,
        "result_sequence": result_sequence,
        "guidance_note": guidance_note,
    }

    # 4. Query institutional_holdings / amfi_holdings
    mutual_funds: list[dict[str, Any]] = []
    if conn is not None:
        try:
            mf_rows = conn.execute("""
                SELECT fund_name, fund_type, shares_held, holding_value_cr, stake_pct, reported_date, action
                FROM institutional_holdings
                WHERE ticker IN (?, ?)
                ORDER BY holding_value_cr DESC, shares_held DESC
            """, (clean_ticker, raw_symbol)).fetchall()
            for r in mf_rows:
                mutual_funds.append({
                    "fund_name": str(r[0]),
                    "fund_type": str(r[1] or "Mutual Fund (DII)"),
                    "shares_held": int(r[2] or 0),
                    "market_value_cr": round(float(r[3] or 0.0), 2),
                    "holding_pct": round(float(r[4] or 0.0), 2),
                    "asof_date": str(r[5]) if r[5] else "Latest Filing",
                    "action": str(r[6]) if len(r) > 6 and r[6] else "HOLD",
                })
        except Exception as e:
            logger.debug("[IPO-DETAIL] Failed querying institutional_holdings for %s: %s", clean_ticker, e)

        if not mutual_funds:
            try:
                amfi_rows = conn.execute("""
                    SELECT fund_name, fund_type, shares_held, market_value_cr, holding_pct, asof_date
                    FROM amfi_holdings
                    WHERE ticker IN (?, ?)
                    ORDER BY market_value_cr DESC
                """, (clean_ticker, raw_symbol)).fetchall()
                for r in amfi_rows:
                    mutual_funds.append({
                        "fund_name": str(r[0]),
                        "fund_type": str(r[1] or "Mutual Fund"),
                        "shares_held": int(r[2] or 0),
                        "market_value_cr": round(float(r[3] or 0.0), 2),
                        "holding_pct": round(float(r[4] or 0.0), 2),
                        "asof_date": str(r[5]) if r[5] else "Latest Filing",
                        "action": "HOLD",
                    })
            except Exception:
                pass

    # 5. Query shareholding_patterns / institutional_accumulation_cache
    shareholding_pattern: dict[str, Any] | None = None
    if conn is not None:
        try:
            shp = conn.execute("""
                SELECT quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct
                FROM shareholding_patterns
                WHERE ticker IN (?, ?)
                ORDER BY quarter DESC
                LIMIT 1
            """, (clean_ticker, raw_symbol)).fetchone()
            if shp:
                shareholding_pattern = {
                    "quarter": str(shp[0]),
                    "promoter_pct": round(float(shp[1] or 0.0), 2),
                    "fii_pct": round(float(shp[2] or 0.0), 2),
                    "dii_pct": round(float(shp[3] or 0.0), 2),
                    "public_retail_pct": round(float(shp[4] or 0.0), 2),
                    "other_pct": round(float(shp[5] or 0.0), 2),
                }
        except Exception as e:
            logger.debug("[IPO-DETAIL] Failed querying shareholding_patterns for %s: %s", clean_ticker, e)

        if not shareholding_pattern:
            try:
                cache_row = conn.execute("""
                    SELECT fii_stake_pct, dii_stake_pct, total_institutional_stake_pct, updated_at
                    FROM institutional_accumulation_cache
                    WHERE ticker IN (?, ?)
                """, (clean_ticker, raw_symbol)).fetchone()
                if cache_row and (cache_row[0] > 0 or cache_row[1] > 0 or cache_row[2] > 0):
                    shareholding_pattern = {
                        "quarter": "Latest Reported",
                        "promoter_pct": 0.0,
                        "fii_pct": round(float(cache_row[0] or 0.0), 2),
                        "dii_pct": round(float(cache_row[1] or 0.0), 2),
                        "public_retail_pct": 0.0,
                        "other_pct": 0.0,
                        "total_institutional_stake_pct": round(float(cache_row[2] or 0.0), 2),
                    }
            except Exception:
                pass

    # 6. Query recent block/bulk deals
    block_deals: list[dict[str, Any]] = []
    if conn is not None:
        try:
            bd_rows = conn.execute("""
                SELECT deal_date, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange
                FROM institutional_block_deals
                WHERE ticker IN (?, ?)
                ORDER BY deal_date DESC
                LIMIT 10
            """, (clean_ticker, raw_symbol)).fetchall()
            for r in bd_rows:
                block_deals.append({
                    "deal_date": str(r[0]),
                    "client_name": str(r[1]),
                    "deal_type": str(r[2]),
                    "quantity": int(r[3] or 0),
                    "price": round(float(r[4] or 0.0), 2),
                    "value_cr": round(float(r[5] or 0.0), 2),
                    "pct_equity": round(float(r[6] or 0.0), 2) if r[6] is not None else None,
                    "exchange": str(r[7]) if len(r) > 7 and r[7] else "NSE",
                })
        except Exception as e:
            logger.debug("[IPO-DETAIL] Failed querying institutional_block_deals for %s: %s", clean_ticker, e)

    institutional = {
        "mutual_funds": mutual_funds,
        "mutual_funds_count": len(mutual_funds),
        "shareholding_pattern": shareholding_pattern,
        "block_deals": block_deals,
    }

    return {
        "success": True,
        "ticker": clean_ticker,
        "raw_symbol": raw_symbol,
        "company_name": company_name,
        "series": series,
        "is_sme": is_sme,
        "face_value": face_value,
        "listing_date": listing_date_str,
        "days_on_market": max(0, days_on_market),
        "technical": technical,
        "earnings_lifecycle": earnings_lifecycle,
        "institutional": institutional,
    }

