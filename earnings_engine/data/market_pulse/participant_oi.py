"""Participant Open Interest (OI) positioning, sync, and contrarian divergence analytics."""

from __future__ import annotations

import concurrent.futures
import io
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.market_pulse.constants import (
    IST_OFFSET,
    _FAILED_NSE_OI_DATES,
    _FAILED_NSE_OI_TTL,
    _PARTICIPANT_OI_CACHE,
    _PARTICIPANT_OI_LOCK,
    _PARTICIPANT_OI_SYNC_LOCK,
    _PULSE_CACHE_TTL,
    labels_map,
)
from earnings_engine.data.market_pulse.timing import (
    format_iso_to_ist,
    get_latest_completed_trading_day,
    is_trading_day,
)
from earnings_engine.data.turso_sync import sync_single_table

logger = logging.getLogger(__name__)

def sync_nse_participant_oi_data(
    settings: Settings | None = None,
    days: int = 30,
    force: bool = False,
) -> int:
    """Sync authentic daily participant derivatives open interest from official NSE clearing archives.

    Downloads https://archives.nseindia.com/content/nsccl/fao_participant_oi_{DDMMYYYY}.csv
    and persists granular Index Futures, Stock Futures, and Options into SQLite table `participant_oi_positioning`.
    """
    if not _PARTICIPANT_OI_SYNC_LOCK.acquire(blocking=False):
        logger.debug("[PARTICIPANT-OI] Sync already in progress by another thread, skipping redundant sync.")
        return 0

    try:
        settings = settings or Settings()
        conn = get_db_connection(settings)

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS participant_oi_positioning (
                    date TEXT NOT NULL,
                    participant TEXT NOT NULL,
                    category_label TEXT NOT NULL,
                    future_index_long INTEGER NOT NULL DEFAULT 0,
                    future_index_short INTEGER NOT NULL DEFAULT 0,
                    future_index_net INTEGER NOT NULL DEFAULT 0,
                    future_index_long_pct REAL NOT NULL DEFAULT 50.0,
                    future_stock_long INTEGER NOT NULL DEFAULT 0,
                    future_stock_short INTEGER NOT NULL DEFAULT 0,
                    future_stock_net INTEGER NOT NULL DEFAULT 0,
                    opt_index_call_long INTEGER NOT NULL DEFAULT 0,
                    opt_index_call_short INTEGER NOT NULL DEFAULT 0,
                    opt_index_put_long INTEGER NOT NULL DEFAULT 0,
                    opt_index_put_short INTEGER NOT NULL DEFAULT 0,
                    opt_stock_call_long INTEGER NOT NULL DEFAULT 0,
                    opt_stock_call_short INTEGER NOT NULL DEFAULT 0,
                    opt_stock_put_long INTEGER NOT NULL DEFAULT 0,
                    opt_stock_put_short INTEGER NOT NULL DEFAULT 0,
                    futures_long INTEGER NOT NULL DEFAULT 0,
                    futures_short INTEGER NOT NULL DEFAULT 0,
                    calls_long INTEGER NOT NULL DEFAULT 0,
                    calls_short INTEGER NOT NULL DEFAULT 0,
                    puts_long INTEGER NOT NULL DEFAULT 0,
                    puts_short INTEGER NOT NULL DEFAULT 0,
                    total_long INTEGER NOT NULL DEFAULT 0,
                    total_short INTEGER NOT NULL DEFAULT 0,
                    net_contracts INTEGER NOT NULL DEFAULT 0,
                    long_short_ratio REAL NOT NULL DEFAULT 1.0,
                    long_pct REAL NOT NULL DEFAULT 50.0,
                    short_pct REAL NOT NULL DEFAULT 50.0,
                    stance TEXT NOT NULL DEFAULT 'Neutral',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (date, participant)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_participant_oi_date ON participant_oi_positioning(date DESC)")

            # Ensure all columns exist for schema migrations
            cols_needed = [
                ("future_index_long", "INTEGER NOT NULL DEFAULT 0"),
                ("future_index_short", "INTEGER NOT NULL DEFAULT 0"),
                ("future_index_net", "INTEGER NOT NULL DEFAULT 0"),
                ("future_index_long_pct", "REAL NOT NULL DEFAULT 50.0"),
                ("future_stock_long", "INTEGER NOT NULL DEFAULT 0"),
                ("future_stock_short", "INTEGER NOT NULL DEFAULT 0"),
                ("future_stock_net", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_index_call_long", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_index_call_short", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_index_put_long", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_index_put_short", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_stock_call_long", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_stock_call_short", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_stock_put_long", "INTEGER NOT NULL DEFAULT 0"),
                ("opt_stock_put_short", "INTEGER NOT NULL DEFAULT 0"),
            ]
            for col_name, col_type in cols_needed:
                try:
                    conn.execute(f"ALTER TABLE participant_oi_positioning ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
            conn.commit()
        except Exception as e:
            logger.debug("[PARTICIPANT-OI] Table setup notice: %s", e)

        # Check which dates already exist in SQLite
        existing_counts = {}
        if not force:
            try:
                existing_counts = dict(conn.execute(
                    "SELECT date, COUNT(*) FROM participant_oi_positioning WHERE future_index_long > 0 GROUP BY date"
                ).fetchall())
            except Exception:
                existing_counts = {}
        try:
            conn.close()
        except Exception:
            pass

        # Determine candidate valid trading dates up to the latest completed trading session
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc + IST_OFFSET
        now_ts = time.time()

        latest_completed = get_latest_completed_trading_day(now_ist.date())
        # If today is an active trading day but before standard settlement release time (~18:30 IST),
        # today's clearing archive has not been published yet -> anchor target to yesterday's completed session
        if latest_completed == now_ist.date():
            time_val = now_ist.hour + now_ist.minute / 60.0
            if time_val < 18.5:
                latest_completed = get_latest_completed_trading_day(now_ist.date() - timedelta(days=1))

        target_dates: list[tuple[str, str]] = []  # (YYYY-MM-DD, DDMMYYYY)
        cur = latest_completed
        while len(target_dates) < days:
            if is_trading_day(cur):
                target_dates.append((cur.strftime("%Y-%m-%d"), cur.strftime("%d%m%Y")))
            cur -= timedelta(days=1)

        # Check which dates already exist in SQLite or are currently in negative-cache cooldown
        missing_dates: list[tuple[str, str]] = []
        if not force:
            for iso_d, ddmmyyyy in target_dates:
                # Check negative cache cooldown (don't re-attempt failed/unreleased dates within 30 min)
                last_failed_ts = _FAILED_NSE_OI_DATES.get(iso_d, 0.0)
                if (now_ts - last_failed_ts) < _FAILED_NSE_OI_TTL:
                    continue

                if existing_counts.get(iso_d, 0) < 4:
                    missing_dates.append((iso_d, ddmmyyyy))
        else:
            missing_dates = target_dates

        if not missing_dates:
            return 0

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        labels_map = {
            "FII": "🏛️ Foreign Institutions (FII / FPI)",
            "DII": "🏢 Domestic Institutions (DII / MF)",
            "PRO": "⚡ Proprietary Desks (Algo / MM)",
            "CLIENT": "👤 Retail Investors & HNIs",
        }

        def _fetch_and_parse_day(date_info: tuple[str, str]) -> list[tuple] | None:
            iso_date, ddmmyyyy = date_info
            url = f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{ddmmyyyy}.csv"
            try:
                resp = requests.get(url, headers=headers, timeout=8)
                if resp.status_code != 200 or len(resp.content) < 50:
                    _FAILED_NSE_OI_DATES[iso_date] = time.time()
                    return None

                raw_bytes = resp.content
                # NSE clearing CSVs often have a title row at line 0 (e.g. "Participant wise Open Interest...")
                df = pd.read_csv(io.BytesIO(raw_bytes))
                df.columns = [c.strip() for c in df.columns]

                p_col = None
                for candidate in ["Client Type", "CLIENT TYPE", "Participant", "PARTICIPANT"]:
                    if candidate in df.columns:
                        p_col = candidate
                        break

                if not p_col:
                    # Try with skiprows=1
                    df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=1)
                    df.columns = [c.strip() for c in df.columns]
                    for candidate in ["Client Type", "CLIENT TYPE", "Participant", "PARTICIPANT"]:
                        if candidate in df.columns:
                            p_col = candidate
                            break

                if not p_col:
                    return None

                now_iso = datetime.now(timezone.utc).isoformat()
                day_records: list[tuple] = []

                for _, row in df.iterrows():
                    raw_type = str(row.get(p_col, "")).strip().upper()
                    p_key = None
                    if "FII" in raw_type or "FOREIGN" in raw_type:
                        p_key = "FII"
                    elif "DII" in raw_type or "DOMESTIC" in raw_type:
                        p_key = "DII"
                    elif "PRO" in raw_type or "PROPRIETARY" in raw_type:
                        p_key = "PRO"
                    elif "CLIENT" in raw_type or "RETAIL" in raw_type or "INDIVIDUAL" in raw_type:
                        p_key = "CLIENT"

                    if not p_key:
                        continue

                    def _safe_int(k: str) -> int:
                        val = row.get(k, 0)
                        try:
                            return int(float(str(val).replace(",", "").strip()))
                        except Exception:
                            return 0

                    fi_long = _safe_int("Future Index Long")
                    fi_short = _safe_int("Future Index Short")
                    fi_net = fi_long - fi_short
                    fi_total = fi_long + fi_short
                    fi_long_pct = round((fi_long / max(1, fi_total)) * 100.0, 1)

                    fs_long = _safe_int("Future Stock Long")
                    fs_short = _safe_int("Future Stock Short")
                    fs_net = fs_long - fs_short

                    oic_long = _safe_int("Option Index Call Long")
                    oic_short = _safe_int("Option Index Call Short")
                    oip_long = _safe_int("Option Index Put Long")
                    oip_short = _safe_int("Option Index Put Short")

                    osc_long = _safe_int("Option Stock Call Long")
                    osc_short = _safe_int("Option Stock Call Short")
                    osp_long = _safe_int("Option Stock Put Long")
                    osp_short = _safe_int("Option Stock Put Short")

                    fut_long = fi_long + fs_long
                    fut_short = fi_short + fs_short

                    calls_long = oic_long + osc_long
                    calls_short = oic_short + osc_short

                    puts_long = oip_long + osp_long
                    puts_short = oip_short + osp_short

                    tot_long = _safe_int("Total Long Contracts") or (fut_long + calls_long + puts_long)
                    tot_short = _safe_int("Total Short Contracts") or (fut_short + calls_short + puts_short)
                    net_contracts = tot_long - tot_short
                    ls_ratio = round(tot_long / max(1, tot_short), 2)
                    sum_tot = tot_long + tot_short
                    long_pct = round((tot_long / max(1, sum_tot)) * 100.0, 1)
                    short_pct = round(100.0 - long_pct, 1)

                    # Classify qualitative stance
                    if p_key == "FII":
                        if fi_long_pct >= 55.0 or (ls_ratio >= 1.15 and fi_net > 0):
                            stance = "🟢 Net Long · Index Futures Momentum"
                        elif fi_long_pct <= 40.0 or (ls_ratio <= 0.85 and fi_net < 0):
                            stance = "🔴 Net Short · Index Futures Hedging"
                        else:
                            stance = "⚪ Neutral Delta · Hedged Positioning"
                    elif p_key == "PRO":
                        if oic_short > oic_long and oip_short > oip_long:
                            stance = "⚪ Delta Neutral · Straddle Writing"
                        elif fi_long_pct >= 55.0:
                            stance = "🟢 Long Delta · Directional Algos"
                        elif fi_long_pct <= 40.0:
                            stance = "🔴 Short Delta · Resistance Writing"
                        else:
                            stance = "⚪ Neutral Delta · Options Writing / Arbitrage"
                    elif p_key == "CLIENT":
                        if fi_long_pct >= 60.0 or calls_long > (calls_short * 1.3):
                            stance = "🟢 Net Long · Retail Call Momentum"
                        elif fi_long_pct <= 40.0:
                            stance = "🔴 Net Short · Retail Protective Puts"
                        else:
                            stance = "🟢 Net Long · Retail Float"
                    else:  # DII
                        if ls_ratio >= 1.15:
                            stance = "🟢 Net Long · Equity Float Accumulation"
                        else:
                            stance = "🟢 Net Long · Systematic SIP Inflows"

                    day_records.append((
                        iso_date, p_key, labels_map.get(p_key, p_key),
                        fi_long, fi_short, fi_net, fi_long_pct,
                        fs_long, fs_short, fs_net,
                        oic_long, oic_short, oip_long, oip_short,
                        osc_long, osc_short, osp_long, osp_short,
                        fut_long, fut_short,
                        calls_long, calls_short,
                        puts_long, puts_short,
                        tot_long, tot_short,
                        net_contracts, ls_ratio, long_pct, short_pct,
                        stance, now_iso
                    ))

                return day_records if len(day_records) >= 4 else None
            except Exception as e:
                logger.debug("[PARTICIPANT-OI] Failed scraping archive %s: %s", url, e)
                return None

        all_inserts: list[tuple] = []
        # Scrape concurrently across candidate dates
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(missing_dates))) as executor:
            results = executor.map(_fetch_and_parse_day, missing_dates)
            for res in results:
                if res:
                    all_inserts.extend(res)

        if all_inserts:
            write_conn = get_db_connection(settings)
            try:
                for attempt in range(3):
                    try:
                        with write_conn:
                            write_conn.executemany("""
                                INSERT OR REPLACE INTO participant_oi_positioning (
                                    date, participant, category_label,
                                    future_index_long, future_index_short, future_index_net, future_index_long_pct,
                                    future_stock_long, future_stock_short, future_stock_net,
                                    opt_index_call_long, opt_index_call_short, opt_index_put_long, opt_index_put_short,
                                    opt_stock_call_long, opt_stock_call_short, opt_stock_put_long, opt_stock_put_short,
                                    futures_long, futures_short,
                                    calls_long, calls_short,
                                    puts_long, puts_short,
                                    total_long, total_short,
                                    net_contracts, long_short_ratio, long_pct, short_pct,
                                    stance, updated_at
                                ) VALUES (
                                    ?, ?, ?,
                                    ?, ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?, ?, ?,
                                    ?, ?, ?, ?,
                                    ?, ?,
                                    ?, ?,
                                    ?, ?,
                                    ?, ?,
                                    ?, ?, ?, ?,
                                    ?, ?
                                )
                            """, all_inserts)
                        logger.info("[PARTICIPANT-OI] Successfully synced %d participant records from official NSE archives", len(all_inserts))
                        break
                    except Exception as e:
                        if "locked" in str(e).lower() and attempt < 2:
                            time.sleep(0.25 * (2 ** attempt))
                            continue
                        logger.warning("[PARTICIPANT-OI] Error persisting synced records: %s", e)
                        break
            finally:
                try:
                    write_conn.close()
                except Exception:
                    pass

        return len(all_inserts)
    finally:
        _PARTICIPANT_OI_SYNC_LOCK.release()


def _classify_oi_regime(d_fi_net: int, d_fi_long: int, d_fi_short: int) -> tuple[str, str, str]:
    """Classify derivatives positioning shift regime based on index futures day-over-day delta.

    Follows standard 4-quadrant derivatives mechanics:
    1. Long Build-up: Fresh long accumulation (ΔLong > 0 and ΔLong >= ΔShort, ΔNet > 0).
    2. Short Build-up: Fresh short creation (ΔShort > 0 and ΔShort >= ΔLong, ΔNet < 0).
    3. Short Covering: Shorts closing/covering (ΔShort < 0 and ΔNet > 0, or both dropping with ΔNet > 0).
    4. Long Unwinding: Longs closing/unwinding (ΔLong < 0 and ΔNet < 0, or both dropping with ΔNet < 0).
    5. Expiry Rollover: Both legs dropping symmetrically (ΔLong < 0 and ΔShort < 0 with ΔNet == 0).
    """
    # Case 1: Both legs dropping (Expiry Rollover / Gross OI contraction)
    if d_fi_long < 0 and d_fi_short < 0:
        if d_fi_net > 0:
            # Shorts closed faster than longs
            return ("Short Covering", "⚡ Short Covering", "Shorts squaring off / expiry unwinding; short covering momentum.")
        elif d_fi_net < 0:
            # Longs closed faster than shorts
            return ("Long Unwinding", "⚠️ Long Unwinding", "Longs squaring off / expiry unwinding; profit taking / risk trimming.")
        else:
            return ("Expiry Rollover", "⚪ Expiry Rollover", "Symmetric expiry rollover / position closure across long and short contracts.")

    # Case 2: Fresh long accumulation dominates
    if d_fi_long > 0 and d_fi_net > 0 and d_fi_long >= d_fi_short:
        return ("Long Build-up", "🟢 Long Build-up", "Aggressive fresh long accumulation in index futures; bullish continuation bias.")

    # Case 3: Fresh short accumulation dominates
    if d_fi_short > 0 and d_fi_net < 0 and d_fi_short >= d_fi_long:
        return ("Short Build-up", "🔴 Short Build-up", "Fresh institutional short hedges added in index futures; overhead resistance.")

    # Case 4: Shorts closing while longs flat or adding
    if d_fi_short < 0 and d_fi_net > 0:
        return ("Short Covering", "⚡ Short Covering", "Bear capitulation / shorts exiting; short squeeze momentum.")

    # Case 5: Longs closing while shorts flat or adding
    if d_fi_long < 0 and d_fi_net < 0:
        return ("Long Unwinding", "⚠️ Long Unwinding", "Longs taking profit / trimming risk; lack of aggressive buying.")

    # Case 6: Delta is non-zero but one leg neutral
    if d_fi_net > 0:
        return ("Net Long Shift", "🟢 Long Add", "Moderate net long expansion in index futures.")
    elif d_fi_net < 0:
        return ("Net Short Shift", "🔴 Short Add", "Moderate net short expansion in index futures.")
    else:
        return ("Neutral / Balanced", "⚪ Neutral", "Balanced positioning shifts with minimal directional skew.")


def compute_participant_oi_matrix(settings: Settings | None = None, force_refresh: bool = False) -> dict[str, Any]:
    """Compute authentic Participant Derivatives Open Interest (OI), Index Futures Long/Short positioning,
    Day-over-Day shifts, and quantitative Market Maker vs Retail Contrarian Predictions for Tomorrow.
    """
    global _PARTICIPANT_OI_CACHE
    now_ts = time.time()
    if not force_refresh and "data" in _PARTICIPANT_OI_CACHE:
        if (now_ts - _PARTICIPANT_OI_CACHE.get("ts", 0)) < _PULSE_CACHE_TTL:
            return _PARTICIPANT_OI_CACHE["data"]

    settings = settings or Settings()

    # Automatically sync latest authentic participant OI files from official NSE clearing archives BEFORE opening query connection
    try:
        sync_nse_participant_oi_data(settings, days=30, force=force_refresh)
    except Exception as e:
        logger.debug("[PARTICIPANT-OI] Auto-sync notice: %s", e)

    # Retrieve all recorded distinct dates from SQLite
    trading_dates_raw: list[str] = []
    target_dates_subset: list[str] = []
    date_grouped: dict[str, dict[str, Any]] = {}

    conn = get_db_connection(settings)
    try:
        dt_rows = conn.execute("""
            SELECT DISTINCT date
            FROM participant_oi_positioning
            ORDER BY date DESC
            LIMIT 40
        """).fetchall()
        for r in dt_rows:
            if r[0]:
                trading_dates_raw.append(str(r[0]))

        target_dates_subset = trading_dates_raw[:30]
        if target_dates_subset:
            placeholders = ", ".join(["?"] * len(target_dates_subset))
            batch_sql = f"""
                SELECT * FROM participant_oi_positioning
                WHERE date IN ({placeholders})
                ORDER BY date DESC,
                         CASE participant
                             WHEN 'FII' THEN 1
                             WHEN 'DII' THEN 2
                             WHEN 'PRO' THEN 3
                             WHEN 'CLIENT' THEN 4
                             ELSE 5
                         END
            """
            cur = conn.execute(batch_sql, target_dates_subset)
            cols = [d[0] for d in cur.description] if cur.description else []
            all_rows = cur.fetchall()
            for r in all_rows:
                row_map = dict(zip(cols, r)) if cols else {}
                d_val = str(row_map.get("date", ""))
                p_code = str(row_map.get("participant", ""))
                if d_val not in date_grouped:
                    date_grouped[d_val] = {}
                if p_code:
                    date_grouped[d_val][p_code] = row_map
    except Exception as e:
        logger.warning("[PARTICIPANT-OI] Batch history query error: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    latest_date_str = trading_dates_raw[0] if trading_dates_raw else today_str
    try:
        dt_obj = datetime.strptime(latest_date_str, "%Y-%m-%d").date()
        session_label = dt_obj.strftime("%d %b (%a)")
    except Exception:
        session_label = latest_date_str

    # Build 30-day, 10-day, and 7-day Participant OI History Matrix
    history_30d: list[dict[str, Any]] = []

    for d_str in target_dates_subset:
        try:
            dt_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
            d_fmt = dt_obj.strftime("%d %b (%a)")
        except Exception:
            d_fmt = d_str

        p_dict = date_grouped.get(d_str, {})
        fii_stat = p_dict.get("FII", {})
        dii_stat = p_dict.get("DII", {})
        pro_stat = p_dict.get("PRO", {})
        client_stat = p_dict.get("CLIENT", {})

        # Compute stock futures long % for each participant
        fii_fs_tot = fii_stat.get("future_stock_long", 0) + fii_stat.get("future_stock_short", 0)
        fii_fs_long_pct = round((fii_stat.get("future_stock_long", 0) / max(1, fii_fs_tot)) * 100.0, 1)

        client_fs_tot = client_stat.get("future_stock_long", 0) + client_stat.get("future_stock_short", 0)
        client_fs_long_pct = round((client_stat.get("future_stock_long", 0) / max(1, client_fs_tot)) * 100.0, 1)

        pro_fs_tot = pro_stat.get("future_stock_long", 0) + pro_stat.get("future_stock_short", 0)
        pro_fs_long_pct = round((pro_stat.get("future_stock_long", 0) / max(1, pro_fs_tot)) * 100.0, 1)

        dii_fs_tot = dii_stat.get("future_stock_long", 0) + dii_stat.get("future_stock_short", 0)
        dii_fs_long_pct = round((dii_stat.get("future_stock_long", 0) / max(1, dii_fs_tot)) * 100.0, 1)

        # Compute net call and put options (Long - Short)
        fii_c_net = fii_stat.get("calls_long", 0) - fii_stat.get("calls_short", 0)
        fii_p_net = fii_stat.get("puts_long", 0) - fii_stat.get("puts_short", 0)
        pro_c_net = pro_stat.get("calls_long", 0) - pro_stat.get("calls_short", 0)
        pro_p_net = pro_stat.get("puts_long", 0) - pro_stat.get("puts_short", 0)
        client_c_net = client_stat.get("calls_long", 0) - client_stat.get("calls_short", 0)
        client_p_net = client_stat.get("puts_long", 0) - client_stat.get("puts_short", 0)

        history_30d.append({
            "date": d_str,
            "session_label": d_fmt,
            # Index Futures Positioning
            "fii_future_index_long": fii_stat.get("future_index_long", 0),
            "fii_future_index_short": fii_stat.get("future_index_short", 0),
            "fii_future_index_net": fii_stat.get("future_index_net", 0),
            "fii_future_index_long_pct": fii_stat.get("future_index_long_pct", 50.0),
            "client_future_index_long": client_stat.get("future_index_long", 0),
            "client_future_index_short": client_stat.get("future_index_short", 0),
            "client_future_index_net": client_stat.get("future_index_net", 0),
            "client_future_index_long_pct": client_stat.get("future_index_long_pct", 50.0),
            "pro_future_index_net": pro_stat.get("future_index_net", 0),
            "pro_future_index_long_pct": pro_stat.get("future_index_long_pct", 50.0),
            "dii_future_index_net": dii_stat.get("future_index_net", 0),
            "dii_future_index_long_pct": dii_stat.get("future_index_long_pct", 50.0),
            # Stock Futures (Single Stock Alpha) Positioning
            "fii_future_stock_long": fii_stat.get("future_stock_long", 0),
            "fii_future_stock_short": fii_stat.get("future_stock_short", 0),
            "fii_future_stock_net": fii_stat.get("future_stock_net", 0),
            "fii_future_stock_long_pct": fii_fs_long_pct,
            "dii_future_stock_net": dii_stat.get("future_stock_net", 0),
            "dii_future_stock_long_pct": dii_fs_long_pct,
            "pro_future_stock_net": pro_stat.get("future_stock_net", 0),
            "pro_future_stock_long_pct": pro_fs_long_pct,
            "client_future_stock_net": client_stat.get("future_stock_net", 0),
            "client_future_stock_long_pct": client_fs_long_pct,
            # Options Net Open Interest (Calls Net vs Puts Net)
            "fii_calls_net": fii_c_net,
            "fii_puts_net": fii_p_net,
            "pro_calls_net": pro_c_net,
            "pro_puts_net": pro_p_net,
            "client_calls_net": client_c_net,
            "client_puts_net": client_p_net,
            # Consolidated F&O Positioning
            "fii_net_contracts": fii_stat.get("net_contracts", 0),
            "fii_long_short_ratio": fii_stat.get("long_short_ratio", 1.0),
            "fii_long_pct": fii_stat.get("long_pct", 50.0),
            "dii_net_contracts": dii_stat.get("net_contracts", 0),
            "dii_long_short_ratio": dii_stat.get("long_short_ratio", 1.0),
            "dii_long_pct": dii_stat.get("long_pct", 50.0),
            "pro_net_contracts": pro_stat.get("net_contracts", 0),
            "pro_long_short_ratio": pro_stat.get("long_short_ratio", 1.0),
            "pro_long_pct": pro_stat.get("long_pct", 50.0),
            "client_net_contracts": client_stat.get("net_contracts", 0),
            "client_long_short_ratio": client_stat.get("long_short_ratio", 1.0),
            "client_long_pct": client_stat.get("long_pct", 50.0),
            "participants": p_dict,
        })

    # Calculate Day-over-Day Delta OI metrics for each participant (T vs T-1)
    delta_metrics: dict[str, dict[str, Any]] = {}
    if len(history_30d) >= 2:
        today_p = history_30d[0].get("participants", {})
        prev_p = history_30d[1].get("participants", {})
        for p_code in ["FII", "DII", "PRO", "CLIENT"]:
            t_stat = today_p.get(p_code, {})
            y_stat = prev_p.get(p_code, {})

            d_fi_net = t_stat.get("future_index_net", 0) - y_stat.get("future_index_net", 0)
            d_fi_long = t_stat.get("future_index_long", 0) - y_stat.get("future_index_long", 0)
            d_fi_short = t_stat.get("future_index_short", 0) - y_stat.get("future_index_short", 0)
            d_fi_long_pct = round(t_stat.get("future_index_long_pct", 50.0) - y_stat.get("future_index_long_pct", 50.0), 1)

            d_fs_net = t_stat.get("future_stock_net", 0) - y_stat.get("future_stock_net", 0)
            d_fs_long = t_stat.get("future_stock_long", 0) - y_stat.get("future_stock_long", 0)
            d_fs_short = t_stat.get("future_stock_short", 0) - y_stat.get("future_stock_short", 0)
            t_fs_tot = t_stat.get("future_stock_long", 0) + t_stat.get("future_stock_short", 0)
            y_fs_tot = y_stat.get("future_stock_long", 0) + y_stat.get("future_stock_short", 0)
            t_fs_long_pct = round((t_stat.get("future_stock_long", 0) / max(1, t_fs_tot)) * 100.0, 1)
            y_fs_long_pct = round((y_stat.get("future_stock_long", 0) / max(1, y_fs_tot)) * 100.0, 1)
            d_fs_long_pct = round(t_fs_long_pct - y_fs_long_pct, 1)

            stock_regime, stock_badge, stock_desc = _classify_oi_regime(d_fs_net, d_fs_long, d_fs_short)

            t_calls_long = t_stat.get("calls_long", 0)
            t_calls_short = t_stat.get("calls_short", 0)
            t_puts_long = t_stat.get("puts_long", 0)
            t_puts_short = t_stat.get("puts_short", 0)

            y_calls_long = y_stat.get("calls_long", 0)
            y_calls_short = y_stat.get("calls_short", 0)
            y_puts_long = y_stat.get("puts_long", 0)
            y_puts_short = y_stat.get("puts_short", 0)

            d_call_long = t_calls_long - y_calls_long
            d_call_short = t_calls_short - y_calls_short
            d_call_net = (t_calls_long - t_calls_short) - (y_calls_long - y_calls_short)

            d_put_long = t_puts_long - y_puts_long
            d_put_short = t_puts_short - y_puts_short
            d_put_net = (t_puts_long - t_puts_short) - (y_puts_long - y_puts_short)

            t_opt_pcr = round((t_puts_long + t_puts_short) / max(1, t_calls_long + t_calls_short), 2)
            y_opt_pcr = round((y_puts_long + y_puts_short) / max(1, y_calls_long + y_calls_short), 2)
            d_opt_pcr = round(t_opt_pcr - y_opt_pcr, 2)

            # Option posture classification
            if p_code == "PRO":
                if t_puts_short > t_puts_long and t_calls_short > t_calls_long:
                    opt_stance = "⚡ Strangle Writing (MM Corridor)"
                    opt_badge = "⚡ Strangle Writing"
                elif t_puts_short > t_puts_long:
                    opt_stance = "🟢 Support Writing (Floor Defense)"
                    opt_badge = "🟢 Support Writing"
                elif t_calls_short > t_calls_long:
                    opt_stance = "🔴 Resistance Writing (Overhead Cap)"
                    opt_badge = "🔴 Resistance Writing"
                else:
                    opt_stance = "⚪ Balanced Options"
                    opt_badge = "⚪ Balanced Options"
            elif p_code == "FII":
                if t_puts_long > t_puts_short and t_opt_pcr >= 1.2:
                    opt_stance = "🛡️ Put Tail-Risk Hedging"
                    opt_badge = "🛡️ Put Hedge"
                elif t_calls_long > t_calls_short and t_opt_pcr <= 0.85:
                    opt_stance = "🟢 Long Call Momentum Speculation"
                    opt_badge = "🟢 Long Calls"
                else:
                    opt_stance = "⚪ Hedged Options Book"
                    opt_badge = "⚪ Hedged Options"
            elif p_code == "CLIENT":
                if t_calls_long > t_calls_short * 1.3:
                    opt_stance = "🟢 Retail Long Call Bias"
                    opt_badge = "🟢 Long Calls"
                elif t_puts_long > t_puts_short * 1.3:
                    opt_stance = "🔴 Retail Long Put Bias"
                    opt_badge = "🔴 Long Puts"
                else:
                    opt_stance = "⚪ Retail Balanced"
                    opt_badge = "⚪ Retail Balanced"
            else:
                opt_stance = "⚪ Passive Derivatives Float"
                opt_badge = "⚪ Passive"

            d_net = t_stat.get("net_contracts", 0) - y_stat.get("net_contracts", 0)
            d_long = t_stat.get("total_long", 0) - y_stat.get("total_long", 0)
            d_short = t_stat.get("total_short", 0) - y_stat.get("total_short", 0)
            d_ls = round(t_stat.get("long_short_ratio", 1.0) - y_stat.get("long_short_ratio", 1.0), 3)

            regime, badge, desc = _classify_oi_regime(d_fi_net, d_fi_long, d_fi_short)

            delta_metrics[p_code] = {
                # Canonical standard keys
                "delta_future_index_net": d_fi_net,
                "delta_future_index_long": d_fi_long,
                "delta_future_index_short": d_fi_short,
                "delta_future_index_long_pct": d_fi_long_pct,
                # Stock Futures
                "future_stock_long_pct": t_fs_long_pct,
                "delta_future_stock_net": d_fs_net,
                "delta_future_stock_long": d_fs_long,
                "delta_future_stock_short": d_fs_short,
                "delta_future_stock_long_pct": d_fs_long_pct,
                "stock_shift_regime": stock_regime,
                "stock_shift_badge": stock_badge,
                "stock_shift_desc": stock_desc,
                # Options Anatomy
                "calls_net": t_calls_long - t_calls_short,
                "puts_net": t_puts_long - t_puts_short,
                "delta_call_long": d_call_long,
                "delta_call_short": d_call_short,
                "delta_call_net": d_call_net,
                "delta_put_long": d_put_long,
                "delta_put_short": d_put_short,
                "delta_put_net": d_put_net,
                "option_pcr": t_opt_pcr,
                "delta_option_pcr": d_opt_pcr,
                "option_stance": opt_stance,
                "option_stance_badge": opt_badge,
                # Consolidated Totals
                "delta_net_contracts": d_net,
                "delta_long_contracts": d_long,
                "delta_short_contracts": d_short,
                "delta_ls_ratio": d_ls,
                "shift_regime": regime,
                "shift_badge": badge,
                "shift_desc": desc,
                # Compatibility aliases
                "future_index_delta": d_fi_net,
                "future_index_long_delta": d_fi_long,
                "future_index_short_delta": d_fi_short,
                "future_index_long_pct_delta": d_fi_long_pct,
                "future_stock_delta": d_fs_net,
                "delta_net_contracts_1d": d_net,
                "delta_long_contracts_1d": d_long,
                "delta_short_contracts_1d": d_short,
                "delta_ls_ratio_1d": d_ls,
                "oi_regime": regime,
                "oi_regime_badge": badge,
                "oi_regime_desc": desc,
            }
    else:
        for p_code in ["FII", "DII", "PRO", "CLIENT"]:
            delta_metrics[p_code] = {
                "delta_future_index_net": 0,
                "delta_future_index_long": 0,
                "delta_future_index_short": 0,
                "delta_future_index_long_pct": 0.0,
                "future_stock_long_pct": 50.0,
                "delta_future_stock_net": 0,
                "delta_future_stock_long": 0,
                "delta_future_stock_short": 0,
                "delta_future_stock_long_pct": 0.0,
                "stock_shift_regime": "Baseline",
                "stock_shift_badge": "⚪ Baseline",
                "stock_shift_desc": "Baseline",
                "calls_net": 0,
                "puts_net": 0,
                "delta_call_long": 0,
                "delta_call_short": 0,
                "delta_call_net": 0,
                "delta_put_long": 0,
                "delta_put_short": 0,
                "delta_put_net": 0,
                "option_pcr": 1.0,
                "delta_option_pcr": 0.0,
                "option_stance": "⚪ Baseline",
                "option_stance_badge": "⚪ Baseline",
                "delta_net_contracts": 0,
                "delta_long_contracts": 0,
                "delta_short_contracts": 0,
                "delta_ls_ratio": 0.0,
                "shift_regime": "Neutral / Balanced",
                "shift_badge": "⚪ Neutral",
                "shift_desc": "Balanced positioning baseline.",
                "future_index_delta": 0,
                "future_index_long_delta": 0,
                "future_index_short_delta": 0,
                "future_index_long_pct_delta": 0.0,
                "future_stock_delta": 0,
                "delta_net_contracts_1d": 0,
                "delta_long_contracts_1d": 0,
                "delta_short_contracts_1d": 0,
                "delta_ls_ratio_1d": 0.0,
                "oi_regime": "Neutral / Balanced",
                "oi_regime_badge": "⚪ Neutral",
                "oi_regime_desc": "Balanced positioning baseline.",
            }

    # Compute Day-over-Day Deltas (T_i vs T_{i+1}) across all historical matrix rows
    num_hist = len(history_30d)
    for i in range(num_hist):
        curr_row = history_30d[i]
        curr_p = curr_row.get("participants", {})
        has_next = (i + 1 < num_hist)
        next_p = history_30d[i + 1].get("participants", {}) if has_next else {}

        row_deltas: dict[str, Any] = {}
        for p_code in ["FII", "DII", "PRO", "CLIENT"]:
            c_stat = curr_p.get(p_code, {})
            n_stat = next_p.get(p_code, {}) if has_next else {}

            if has_next and n_stat:
                d_fi_net = c_stat.get("future_index_net", 0) - n_stat.get("future_index_net", 0)
                d_fi_long = c_stat.get("future_index_long", 0) - n_stat.get("future_index_long", 0)
                d_fi_short = c_stat.get("future_index_short", 0) - n_stat.get("future_index_short", 0)
                d_fi_long_pct = round(c_stat.get("future_index_long_pct", 50.0) - n_stat.get("future_index_long_pct", 50.0), 1)

                d_fs_net = c_stat.get("future_stock_net", 0) - n_stat.get("future_stock_net", 0)
                d_fs_long = c_stat.get("future_stock_long", 0) - n_stat.get("future_stock_long", 0)
                d_fs_short = c_stat.get("future_stock_short", 0) - n_stat.get("future_stock_short", 0)

                d_net = c_stat.get("net_contracts", 0) - n_stat.get("net_contracts", 0)
                d_long = c_stat.get("total_long", 0) - n_stat.get("total_long", 0)
                d_short = c_stat.get("total_short", 0) - n_stat.get("total_short", 0)
                d_ls = round(c_stat.get("long_short_ratio", 1.0) - n_stat.get("long_short_ratio", 1.0), 3)

                regime, badge, desc = _classify_oi_regime(d_fi_net, d_fi_long, d_fi_short)
                s_regime, s_badge, _ = _classify_oi_regime(d_fs_net, d_fs_long, d_fs_short)
            else:
                d_fi_net = 0
                d_fi_long = 0
                d_fi_short = 0
                d_fi_long_pct = 0.0
                d_fs_net = 0
                d_net = 0
                d_long = 0
                d_short = 0
                d_ls = 0.0
                regime = "Baseline"
                badge = "⚪ Baseline"
                desc = "Initial observation baseline"
                s_regime = "Baseline"
                s_badge = "⚪ Baseline"

            p_delta_bundle = {
                "delta_future_index_net": d_fi_net,
                "future_index_delta": d_fi_net,
                "delta_future_index_long": d_fi_long,
                "delta_future_index_short": d_fi_short,
                "delta_future_index_long_pct": d_fi_long_pct,
                "delta_future_stock_net": d_fs_net,
                "future_stock_delta": d_fs_net,
                "stock_shift_regime": s_regime,
                "stock_shift_badge": s_badge,
                "delta_net_contracts": d_net,
                "delta_long_contracts": d_long,
                "delta_short_contracts": d_short,
                "delta_ls_ratio": d_ls,
                "shift_regime": regime,
                "shift_badge": badge,
                "shift_desc": desc,
                "oi_regime_badge": badge,
            }
            if p_code in curr_p:
                curr_p[p_code].update(p_delta_bundle)
            row_deltas[p_code.lower()] = p_delta_bundle

        # Top-level row convenience properties for easy consumption in templates and JS
        curr_row["fii_delta_index_net"] = row_deltas["fii"]["delta_future_index_net"]
        curr_row["fii_future_index_delta"] = row_deltas["fii"]["delta_future_index_net"]
        curr_row["fii_delta_index_long_pct"] = row_deltas["fii"]["delta_future_index_long_pct"]
        curr_row["fii_delta_stock_net"] = row_deltas["fii"]["delta_future_stock_net"]
        curr_row["fii_delta_net_contracts"] = row_deltas["fii"]["delta_net_contracts"]
        curr_row["fii_shift_regime"] = row_deltas["fii"]["shift_regime"]
        curr_row["fii_shift_badge"] = row_deltas["fii"]["shift_badge"]
        curr_row["fii_stock_shift_badge"] = row_deltas["fii"]["stock_shift_badge"]

        curr_row["dii_delta_index_net"] = row_deltas["dii"]["delta_future_index_net"]
        curr_row["dii_future_index_delta"] = row_deltas["dii"]["delta_future_index_net"]
        curr_row["dii_delta_stock_net"] = row_deltas["dii"]["delta_future_stock_net"]
        curr_row["dii_shift_badge"] = row_deltas["dii"]["shift_badge"]

        curr_row["pro_delta_index_net"] = row_deltas["pro"]["delta_future_index_net"]
        curr_row["pro_future_index_delta"] = row_deltas["pro"]["delta_future_index_net"]
        curr_row["pro_delta_stock_net"] = row_deltas["pro"]["delta_future_stock_net"]
        curr_row["pro_shift_badge"] = row_deltas["pro"]["shift_badge"]

        curr_row["client_delta_index_net"] = row_deltas["client"]["delta_future_index_net"]
        curr_row["client_future_index_delta"] = row_deltas["client"]["delta_future_index_net"]
        curr_row["client_delta_stock_net"] = row_deltas["client"]["delta_future_stock_net"]
        curr_row["client_shift_badge"] = row_deltas["client"]["shift_badge"]

    history_7d = history_30d[:7]
    history_10d = history_30d[:10]

    # Build latest snapshot from in-memory date_grouped and merge delta metrics
    participants_list: list[dict[str, Any]] = []
    latest_day_map = date_grouped.get(latest_date_str, {})
    seen_participants = set()
    for p_code in ["FII", "DII", "PRO", "CLIENT"]:
        if p_code in latest_day_map:
            p_dict = dict(latest_day_map[p_code])
            d_info = delta_metrics.get(p_code, {})
            p_dict.update(d_info)
            participants_list.append(p_dict)
            seen_participants.add(p_code)
    for p_code, p_dict_raw in latest_day_map.items():
        if p_code not in seen_participants:
            p_dict = dict(p_dict_raw)
            d_info = delta_metrics.get(p_code, {})
            p_dict.update(d_info)
            participants_list.append(p_dict)

    # Extract participant stats for contrarian prediction engine
    fii_p = next((p for p in participants_list if p.get("participant") == "FII"), {})
    dii_p = next((p for p in participants_list if p.get("participant") == "DII"), {})
    pro_p = next((p for p in participants_list if p.get("participant") == "PRO"), {})
    client_p = next((p for p in participants_list if p.get("participant") == "CLIENT"), {})

    fii_net = int(fii_p.get("net_contracts", 0))
    dii_net = int(dii_p.get("net_contracts", 0))
    pro_net = int(pro_p.get("net_contracts", 0))
    client_net = int(client_p.get("net_contracts", 0))

    fii_ls = float(fii_p.get("long_short_ratio", 1.0))
    dii_ls = float(dii_p.get("long_short_ratio", 1.0))
    pro_ls = float(pro_p.get("long_short_ratio", 1.0))
    client_ls = float(client_p.get("long_short_ratio", 1.0))

    fii_fi_net = int(fii_p.get("future_index_net", 0))
    fii_fi_long_pct = float(fii_p.get("future_index_long_pct", 50.0))
    client_fi_net = int(client_p.get("future_index_net", 0))
    client_fi_long_pct = float(client_p.get("future_index_long_pct", 50.0))
    pro_fi_net = int(pro_p.get("future_index_net", 0))
    dii_fi_net = int(dii_p.get("future_index_net", 0))

    smart_money_net = fii_fi_net + pro_fi_net
    retail_net = client_fi_net
    smart_vs_retail_delta = smart_money_net - retail_net

    # -----------------------------------------------------------------------
    # Quantitative Market Maker vs Retail Contrarian Prediction Engine
    # -----------------------------------------------------------------------
    # Core Principle: Market makers & institutional desks consistently trade
    # against retail crowds when positioning reaches extreme polar divergence.
    # When Retail is aggressively long (e.g. > 70% long) & FII is heavily short (< 25% long),
    # morning gap-ups face high probability of being sold off (Bull-Trap).
    if (fii_fi_long_pct <= 25.0 or fii_fi_net < -15000) and (client_fi_long_pct >= 65.0 or client_fi_net > 20000):
        regime_verdict = "⚠️ Extreme Smart Money Hedging vs Retail Euphoria (High Bull-Trap Risk)"
        regime_sentiment = "BEARISH_DIVERGENCE"
        divergence_status = "BEAR_TRAP_RISK"
        divergence_badge = "🚨 Extreme Bull-Trap Risk (Smart Money Short vs Retail Long)"
        divergence_trap_score = 88
        divergence_warning = "FIIs hold heavy Index Futures short inventory (~{:.1f}% Long) while Retail is aggressively long ({:.1f}% Long). Market makers are positioned to fade morning rallies into resistance.".format(
            fii_fi_long_pct, client_fi_long_pct
        )
        market_maker_stance = "Net Short Index Futures & Writing Resistance Calls (Trap Formation)"
        retail_stance = "Aggressively Long Index Futures & Buying Out-of-the-Money Calls"
        contrarian_prediction = {
            "verdict": "BEARISH_FADE_GAP_UPS",
            "trap_score": 88,
            "headline": "🚨 High Bull-Trap Risk: Market Makers Poised to Fade Morning Rallies",
            "expected_behavior": "Morning gap-ups will struggle to sustain and are likely to face aggressive institutional supply near VWAP and key call strikes.",
            "actionable_playbook": "Avoid chasing morning breakouts. Look for short / mean-reversion setups on failed tests of overhead resistance.",
            "fii_long_pct": fii_fi_long_pct,
            "client_long_pct": client_fi_long_pct,
        }
        commentary = (
            f"Foreign institutions hold only {fii_fi_long_pct:.1f}% Long in Index Futures with a net short position of {abs(fii_fi_net):,} contracts. "
            f"In contrast, Retail Clients hold {client_fi_long_pct:.1f}% Long (+{client_fi_net:,} net long contracts). "
            "This severe divergence creates high vulnerability to gap-and-crap bull traps where opening momentum is absorbed by institutional sell orders."
        )
    elif (fii_fi_long_pct >= 60.0 or fii_fi_net > 15000) and (client_fi_long_pct <= 40.0 or client_fi_net < -10000):
        regime_verdict = "🟢 Institutional Squeeze on Retail Shorts (High Conviction Bullish Continuation)"
        regime_sentiment = "BULLISH_CONVERGENCE"
        divergence_status = "SHORT_SQUEEZE_EXPANSION"
        divergence_badge = "⚡ Short Squeeze Expansion (Smart Money Long vs Retail Short)"
        divergence_trap_score = 15
        divergence_warning = "FIIs are heavily long Index Futures ({:.1f}% Long) against trapped retail short positions ({:.1f}% Long). Pullbacks into VWAP are high-probability buy zones.".format(
            fii_fi_long_pct, client_fi_long_pct
        )
        market_maker_stance = "Dominant Index Futures Longs & Writing Protective Puts"
        retail_stance = "Trapped in Index Short Hedges & Buying Puts"
        contrarian_prediction = {
            "verdict": "BULLISH_SHORT_SQUEEZE",
            "trap_score": 15,
            "headline": "⚡ Short-Squeeze Alert: Institutions Driving Upward Momentum",
            "expected_behavior": "Morning pullbacks are rapidly absorbed by institutional buy orders, forcing retail shorts to capitulate and buy to cover.",
            "actionable_playbook": "Buy intraday pullbacks near VWAP and 1-Sigma lower bands. Trend continuation favored over reversals.",
            "fii_long_pct": fii_fi_long_pct,
            "client_long_pct": client_fi_long_pct,
        }
        commentary = (
            f"FIIs hold {fii_fi_long_pct:.1f}% Long in Index Futures with +{fii_fi_net:,} net contracts while Retail is net short ({client_fi_long_pct:.1f}% Long). "
            "Historically, this setup fuels powerful short squeezes where dips are aggressively defended and bears are forced to cover."
        )
    elif abs(fii_fi_net) < 10000 and pro_p.get("opt_index_call_short", 0) > pro_p.get("opt_index_call_long", 0):
        regime_verdict = "⚖️ Rangebound / Theta Capture Regime (Market Makers Short Volatility)"
        regime_sentiment = "NEUTRAL_RANGEBOUND"
        divergence_status = "RANGEBOUND_THETA"
        divergence_badge = "⚖️ Rangebound / Theta Capture (Option Sellers Dominant)"
        divergence_trap_score = 38
        divergence_warning = "Proprietary desks and market makers hold heavy short straddles/strangles. Benchmark index likely pinned within the 1-Sigma corridor."
        market_maker_stance = "Delta-Neutral Straddle Writing & Premium Decay Arbitrage"
        retail_stance = "Directional Option Premium Buyers"
        contrarian_prediction = {
            "verdict": "RANGEBOUND_THETA_DECAY",
            "trap_score": 38,
            "headline": "⚖️ Rangebound Pinning: Market Makers Harvesting Premium",
            "expected_behavior": "Index is expected to oscillate within established support/resistance bounds without clean multi-hour breakout extensions.",
            "actionable_playbook": "Deploy non-directional option selling or mean-reversion strategies from range extremes. Avoid breakout chasing.",
            "fii_long_pct": fii_fi_long_pct,
            "client_long_pct": client_fi_long_pct,
        }
        commentary = (
            "Proprietary desks hold delta-neutral option writing positions across major index strikes. "
            "Directional momentum is constrained, favoring mean-reversion and premium decay strategies."
        )
    else:
        regime_verdict = "⚪ Balanced Institutional Positioning (Sector & Stock Rotation)"
        regime_sentiment = "NEUTRAL"
        divergence_status = "BALANCED"
        divergence_badge = "⚖️ Balanced Positioning"
        divergence_trap_score = 45
        divergence_warning = "Positioning is balanced. Benchmark price action will follow sectoral earnings releases and technical pivots."
        market_maker_stance = "Balanced Hedging & Systematic Arbitrage"
        retail_stance = "Stock Specific & Mild Long Bias"
        contrarian_prediction = {
            "verdict": "BALANCED_ROTATION",
            "trap_score": 45,
            "headline": "🔄 Balanced Positioning: Stock & Sector Catalyst Focus",
            "expected_behavior": "Index moves within normal volatility parameters. High divergence between strong and weak sectors.",
            "actionable_playbook": "Focus on high-quality breakout setups and earnings surprise candidates. Trade benchmark indices strictly by technical levels.",
            "fii_long_pct": fii_fi_long_pct,
            "client_long_pct": client_fi_long_pct,
        }
        commentary = (
            f"FII Index Futures Long % stands at {fii_fi_long_pct:.1f}% with Retail at {client_fi_long_pct:.1f}%. "
            "No extreme contrarian trap conditions are present. Stock-specific catalysts and earnings momentum will drive alpha."
        )

    # Build 10D and 30D Time Series for Charting (Chronological order)
    chart_10d_reversed = list(reversed(history_10d))
    chart_series_10d = {
        "dates": [h["date"] for h in chart_10d_reversed],
        "session_labels": [h["session_label"] for h in chart_10d_reversed],
        "fii_future_index_long_pct": [h.get("fii_future_index_long_pct", 50.0) for h in chart_10d_reversed],
        "client_future_index_long_pct": [h.get("client_future_index_long_pct", 50.0) for h in chart_10d_reversed],
        "fii_future_index_net": [h.get("fii_future_index_net", 0) for h in chart_10d_reversed],
        "client_future_index_net": [h.get("client_future_index_net", 0) for h in chart_10d_reversed],
        "fii_net": [h["fii_net_contracts"] for h in chart_10d_reversed],
        "dii_net": [h["dii_net_contracts"] for h in chart_10d_reversed],
        "pro_net": [h["pro_net_contracts"] for h in chart_10d_reversed],
        "client_net": [h["client_net_contracts"] for h in chart_10d_reversed],
        "fii_ls_ratio": [h["fii_long_short_ratio"] for h in chart_10d_reversed],
        "client_ls_ratio": [h["client_long_short_ratio"] for h in chart_10d_reversed],
    }

    chart_30d_reversed = list(reversed(history_30d))
    chart_series_30d = {
        "dates": [h["date"] for h in chart_30d_reversed],
        "session_labels": [h["session_label"] for h in chart_30d_reversed],
        "fii_future_index_long_pct": [h.get("fii_future_index_long_pct", 50.0) for h in chart_30d_reversed],
        "client_future_index_long_pct": [h.get("client_future_index_long_pct", 50.0) for h in chart_30d_reversed],
        "fii_future_index_net": [h.get("fii_future_index_net", 0) for h in chart_30d_reversed],
        "client_future_index_net": [h.get("client_future_index_net", 0) for h in chart_30d_reversed],
        "fii_net": [h["fii_net_contracts"] for h in chart_30d_reversed],
        "dii_net": [h["dii_net_contracts"] for h in chart_30d_reversed],
        "pro_net": [h["pro_net_contracts"] for h in chart_30d_reversed],
        "client_net": [h["client_net_contracts"] for h in chart_30d_reversed],
        "fii_ls_ratio": [h["fii_long_short_ratio"] for h in chart_30d_reversed],
        "client_ls_ratio": [h["client_long_short_ratio"] for h in chart_30d_reversed],
    }

    oi_payload = {
        "as_of_date": latest_date_str,
        "session_label": session_label,
        "participants": participants_list,
        "index_futures_summary": {
            "fii_index_long_pct": fii_fi_long_pct,
            "client_index_long_pct": client_fi_long_pct,
            "pro_index_long_pct": float(pro_p.get("future_index_long_pct", 50.0)),
            "dii_index_long_pct": float(dii_p.get("future_index_long_pct", 50.0)),
            "fii_index_net": fii_fi_net,
            "client_index_net": client_fi_net,
            "pro_index_net": pro_fi_net,
            "dii_index_net": dii_fi_net,
            "fii_index_net_delta": delta_metrics.get("FII", {}).get("future_index_delta", 0),
            "client_index_net_delta": delta_metrics.get("CLIENT", {}).get("future_index_delta", 0),
            "pro_index_net_delta": delta_metrics.get("PRO", {}).get("future_index_delta", 0),
            "dii_index_net_delta": delta_metrics.get("DII", {}).get("future_index_delta", 0),
            "fii_index_long_pct_delta": delta_metrics.get("FII", {}).get("future_index_long_pct_delta", 0.0),
            "client_index_long_pct_delta": delta_metrics.get("CLIENT", {}).get("future_index_long_pct_delta", 0.0),
            "pro_index_long_pct_delta": delta_metrics.get("PRO", {}).get("future_index_long_pct_delta", 0.0),
            "dii_index_long_pct_delta": delta_metrics.get("DII", {}).get("future_index_long_pct_delta", 0.0),
        },
        "stock_futures_summary": {
            "fii_stock_net": int(fii_p.get("future_stock_net", 0)),
            "dii_stock_net": int(dii_p.get("future_stock_net", 0)),
            "pro_stock_net": int(pro_p.get("future_stock_net", 0)),
            "client_stock_net": int(client_p.get("future_stock_net", 0)),
            "fii_stock_long_pct": delta_metrics.get("FII", {}).get("future_stock_long_pct", 50.0),
            "client_stock_long_pct": delta_metrics.get("CLIENT", {}).get("future_stock_long_pct", 50.0),
            "fii_stock_delta": delta_metrics.get("FII", {}).get("delta_future_stock_net", 0),
            "client_stock_delta": delta_metrics.get("CLIENT", {}).get("delta_future_stock_net", 0),
            "fii_stock_regime": delta_metrics.get("FII", {}).get("stock_shift_regime", "Baseline"),
        },
        "options_summary": {
            "pro_stance": delta_metrics.get("PRO", {}).get("option_stance", "Balanced"),
            "fii_stance": delta_metrics.get("FII", {}).get("option_stance", "Balanced"),
            "client_stance": delta_metrics.get("CLIENT", {}).get("option_stance", "Balanced"),
            "fii_pcr": delta_metrics.get("FII", {}).get("option_pcr", 1.0),
            "pro_pcr": delta_metrics.get("PRO", {}).get("option_pcr", 1.0),
            "client_pcr": delta_metrics.get("CLIENT", {}).get("option_pcr", 1.0),
        },
        "history_7d": history_7d,
        "history_10d": history_10d,
        "history_30d": history_30d,
        "fii_net_contracts": fii_net,
        "dii_net_contracts": dii_net,
        "pro_net_contracts": pro_net,
        "client_net_contracts": client_net,
        "fii_long_short_ratio": fii_ls,
        "dii_long_short_ratio": dii_ls,
        "pro_long_short_ratio": pro_ls,
        "client_long_short_ratio": client_ls,
        "smart_money_net": smart_money_net,
        "retail_net": retail_net,
        "smart_vs_retail_delta": smart_vs_retail_delta,
        "smart_vs_retail_divergence": smart_vs_retail_delta,
        "divergence_status": divergence_status,
        "divergence_badge": divergence_badge,
        "divergence_trap_score": divergence_trap_score,
        "divergence_warning": divergence_warning,
        "market_maker_stance": market_maker_stance,
        "retail_stance": retail_stance,
        "contrarian_prediction": contrarian_prediction,
        "regime_verdict": regime_verdict,
        "regime_sentiment": regime_sentiment,
        "commentary": commentary,
        "chart_series_10d": chart_series_10d,
        "chart_series_30d": chart_series_30d,
        "as_of": latest_date_str,
        "as_of_ist": format_iso_to_ist(next((p.get("updated_at") for p in participants_list if p.get("updated_at")), None)) or f"{session_label} (EOD)",
        "updated_at": next((p.get("updated_at") for p in participants_list if p.get("updated_at")), None) or datetime.now(timezone.utc).isoformat(),
        "data_freshness": "EOD_SETTLED",
    }

    _PARTICIPANT_OI_CACHE = {"ts": now_ts, "data": oi_payload}
    return oi_payload


# ---------------------------------------------------------------------------
# 5. Market Sentiment, Fear & Greed, Volatility Regime, Macro Charts
# ---------------------------------------------------------------------------

def compute_market_sentiment_matrix(
    settings: Settings | None = None,
    indices_data: list[dict[str, Any]] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Compute Fear & Greed score, Market Breadth, Volatility Matrix, and 30D macro time-series."""
    settings = settings or Settings()
    conn = get_db_connection(settings)

    if indices_data is None:
        indices_data = compute_indices_quotes(settings=settings, force_refresh=force_refresh)

    vix_level = 13.8
    vix_1d_pct = 0.0
    for idx in indices_data:
        if idx["symbol"] == "^INDIAVIX":
            vix_level = float(idx["current_price"])
            vix_1d_pct = float(idx.get("change_pct", 0.0))

    vix_regime = get_volatility_regime(vix_level)
    nifty_1d = indices_data[0]["change_pct"] if indices_data else 0.5
    vix_factor = max(10.0, min(95.0, 100.0 - (vix_level - 10.0) * 4.5))
    momentum_factor = max(15.0, min(90.0, 50.0 + nifty_1d * 12.0))
    breadth_factor = 62.0
    safe_haven_factor = 58.0

    fear_greed_score = round(
        (vix_factor * 0.35) + (momentum_factor * 0.35) + (breadth_factor * 0.15) + (safe_haven_factor * 0.15), 1
    )
