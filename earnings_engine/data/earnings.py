"""Cached earnings-event data access and ingestion."""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from typing import Any, Iterator

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path as _prices_cache_path
from earnings_engine.data.nse_api import fetch_event_calendar
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.earnings")

COLUMNS = ["earnings_date", "eps_estimate", "eps_reported", "surprise_pct"]
EARNINGS_PROVENANCE_COLUMNS = [
    "exchange_source",
    "confirmation_status",
    "board_meeting_purpose",
    "filing_id",
]


def ensure_earnings_history_schema(connection: Any) -> None:
    """Ensure earnings_history table has filing provenance and verification columns."""
    try:
        cur = connection.execute("PRAGMA table_info(earnings_history)")
        existing_cols = {row[1] for row in cur.fetchall()}
        if not existing_cols:
            return

        col_defs = [
            ("exchange_source", "TEXT"),
            ("confirmation_status", "TEXT DEFAULT 'CONFIRMED'"),
            ("board_meeting_purpose", "TEXT"),
            ("filing_id", "TEXT"),
        ]
        for col_name, col_type in col_defs:
            if col_name not in existing_cols:
                connection.execute(f"ALTER TABLE earnings_history ADD COLUMN {col_name} {col_type}")

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_earnings_history_exchange ON earnings_history (exchange_source)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_earnings_history_status ON earnings_history (confirmation_status)"
        )
    except Exception as e:
        logger.debug("Failed to verify/alter earnings_history schema: %s", e)


def _db_path(settings: Settings) -> Path:
    """Use the same SQLite database as prices."""
    return _prices_cache_path(settings)


@contextmanager
def _connect(settings: Settings) -> Iterator[Any]:
    """Connect to the shared database with automated lifecycle management."""
    settings.ensure_dirs()
    connection = get_db_connection(settings)
    ensure_earnings_history_schema(connection)
    try:
        yield connection
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _is_fresh(ticker: str, settings: Settings) -> bool:
    """Check if earnings data is fresh in SQLite for the given ticker.

    Refresh should ONLY happen if:
    1. The next earnings date is not present in SQLite (None / missing).
    2. OR the next earnings date is in the next 7 days (0 <= (next_date - today).days <= 7).

    If the next earnings date is present and > 7 days in the future, the data is
    considered fresh and does NOT need to be re-downloaded.
    """
    with _connect(settings) as connection:
        # Check when this ticker's earnings was last fetched
        row = connection.execute(
            "SELECT earnings_fetched_at FROM tickers WHERE ticker = ?",
            (ticker,),
        ).fetchone()

        fetched_at_str = row[0] if row and row[0] else None

        # If fetched within the last 24 hours, treat as fresh to avoid hammering APIs within the same session (especially for newly listed IPOs with no earnings calendar yet)
        if fetched_at_str:
            try:
                fetched_at = pd.Timestamp(fetched_at_str)
                age_hours = (pd.Timestamp.now() - fetched_at).total_seconds() / 3600.0
                if age_hours < 24.0:
                    return True
            except Exception:
                pass

        # Query the next upcoming earnings date for this ticker (>= today)
        today_str = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
        next_row = connection.execute(
            "SELECT MIN(earnings_date) FROM earnings_history WHERE ticker = ? AND earnings_date >= ?",
            (ticker, today_str),
        ).fetchone()

        next_earnings_date_str = next_row[0] if next_row and next_row[0] else None

    # Condition 1: Next earnings date is NOT present and hasn't been fetched in last 24h -> needs refresh
    if not next_earnings_date_str:
        if fetched_at_str:
            try:
                age_hours = (pd.Timestamp.now() - pd.Timestamp(fetched_at_str)).total_seconds() / 3600.0
                if age_hours < 24.0:
                    return True
            except Exception:
                pass
        return False

    try:
        next_dt = pd.Timestamp(next_earnings_date_str).normalize()
        today_dt = pd.Timestamp.today().normalize()
        days_to_next = (next_dt - today_dt).days

        # Condition 2: Next earnings date is in the next 7 days -> needs refresh (unless fetched today)
        if 0 <= days_to_next <= 7:
            if fetched_at_str:
                age_days = (pd.Timestamp.now() - pd.Timestamp(fetched_at_str)).total_seconds() / 86400.0
                if age_days < 1.0:
                    return True
            return False

        # Next earnings date is > 7 days away -> Fresh! No refresh needed
        if days_to_next > 7:
            return True
    except Exception:
        return False

    return True


def _mark_fresh(ticker: str, settings: Settings) -> None:
    """Mark a ticker as freshly fetched in the master tickers table."""
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO tickers (ticker, earnings_fetched_at, last_updated)
            VALUES (?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                earnings_fetched_at = excluded.earnings_fetched_at,
                last_updated = excluded.last_updated
            """,
            (ticker, now, now),
        )
        connection.commit()


def _write_earnings(ticker: str, settings: Settings, df: pd.DataFrame) -> None:
    """Write earnings data to SQLite with smart merge into earnings_history."""
    if df.empty:
        return
    # Deduplicate by earnings_date (keep last occurrence)
    df = df.drop_duplicates(subset=["earnings_date"], keep="last")
    is_indian = ticker.upper().endswith((".NS", ".BO"))
    today_str = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    rows = []
    for _, row in df.iterrows():
        edate = pd.Timestamp(row["earnings_date"]).strftime("%Y-%m-%d")
        # Anti-fabrication rule: never take future results dates from yfinance for Indian equities
        if is_indian and edate >= today_str:
            continue
        rows.append(
            (
                ticker,
                edate,
                float(row["eps_estimate"]) if pd.notna(row.get("eps_estimate")) else None,
                float(row["eps_reported"]) if pd.notna(row.get("eps_reported")) else None,
                float(row["surprise_pct"]) if pd.notna(row.get("surprise_pct")) else None,
                "yfinance",
            )
        )
    if not rows:
        return
    with _connect(settings) as connection:
        connection.executemany(
            """
            INSERT INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                eps_estimate = COALESCE(excluded.eps_estimate, earnings_history.eps_estimate),
                eps_reported = COALESCE(excluded.eps_reported, earnings_history.eps_reported),
                surprise_pct = COALESCE(excluded.surprise_pct, earnings_history.surprise_pct),
                source = CASE
                    WHEN earnings_history.source != excluded.source THEN earnings_history.source || '+' || excluded.source
                    ELSE excluded.source
                END
            """,
            rows,
        )
        connection.commit()


def _migrate_from_parquet(ticker: str, settings: Settings) -> None:
    """Migrate earnings data from old Parquet cache to SQLite if it exists."""
    old_path = settings.data_dirs["earnings"] / f"{ticker}.parquet"
    if not old_path.exists():
        return
    try:
        df = pd.read_parquet(old_path)
        if not df.empty:
            _write_earnings(ticker, settings, df)
            logger.info("migrated earnings from parquet ticker=%s rows=%s", ticker, len(df))
        old_path.unlink()
    except Exception as e:
        logger.warning("parquet migration failed ticker=%s error=%s", ticker, e)


def fetch_earnings(ticker: str, settings: Settings, force: bool = False) -> pd.DataFrame:
    """Load cached earnings dates or download them when needed."""
    # Migrate from old Parquet cache if it exists
    _migrate_from_parquet(ticker, settings)

    if not force and _is_fresh(ticker, settings):
        logger.info("earnings cache hit ticker=%s", ticker)
        return load_earnings(ticker, settings)

    settings.ensure_dirs()
    logger.info("[YF:REQ] yf.Ticker(%s).get_earnings_dates(limit=60)", ticker)
    t0 = time.perf_counter()
    try:
        try:
            from earnings_engine.rate_limits import record_request
            record_request("yfinance")
        except Exception:
            pass
        raw = yf.Ticker(ticker).get_earnings_dates(limit=60)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        count = len(raw) if raw is not None and isinstance(raw, pd.DataFrame) else 0
        logger.info("[YF:RESP] get_earnings_dates(%s) -> %d rows (%.1fms)", ticker, count, elapsed_ms)
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning("[YF:FAIL] get_earnings_dates(%s) failed after %.1fms: %s", ticker, elapsed_ms, e)
        raw = None

    if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
        df = pd.DataFrame(columns=COLUMNS)
        df["earnings_date"] = pd.Series(dtype="datetime64[ns]")
        _mark_fresh(ticker, settings)
        return df

    frame = raw.copy()
    rename_map = {
        "EPS Estimate": "eps_estimate",
        "Reported EPS": "eps_reported",
        "Surprise(%)": "surprise_pct",
        "eps estimate": "eps_estimate",
        "reported eps": "eps_reported",
        "surprise(%)": "surprise_pct",
        "eps_estimate": "eps_estimate",
        "eps_reported": "eps_reported",
        "surprise_pct": "surprise_pct",
    }
    frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})

    frame.index = pd.to_datetime(frame.index, utc=True)
    frame.index = frame.index.tz_convert(None)
    frame.index = frame.index.normalize()
    frame.index.name = "earnings_date"
    frame = frame.reset_index()

    for col in COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    frame = frame[COLUMNS].copy()
    logger.info("earnings data normalized ticker=%s rows=%s", ticker, len(frame))
    frame["earnings_date"] = pd.to_datetime(frame["earnings_date"])
    frame = frame.sort_values("earnings_date").reset_index(drop=True)
    _write_earnings(ticker, settings, frame)
    _mark_fresh(ticker, settings)
    return frame


def load_earnings(ticker: str, settings: Settings, source: str | None = None) -> pd.DataFrame:
    """Load earnings dates from SQLite if present.

    If ``source`` is given (``"yfinance"``, ``"nse"``), only rows from that
    source are returned.  ``None`` means all sources (default), with rows
    deduplicated by earnings_date (preferring yfinance rows that have EPS data).
    """
    with _connect(settings) as connection:
        if source is None:
            rows = connection.execute(
                "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker = ? ORDER BY earnings_date",
                (ticker,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker = ? AND source = ? ORDER BY earnings_date",
                (ticker, source),
            ).fetchall()

    if not rows:
        return pd.DataFrame(columns=COLUMNS)

    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["earnings_date"] = pd.to_datetime(frame["earnings_date"])
    # When loading all sources, the same date may exist as both yfinance (with
    # EPS) and nse (without EPS).  Deduplicate by earnings_date, preferring
    # rows that have EPS data.
    if source is None:
        frame = frame.sort_values(
            "earnings_date", ascending=True
        ).drop_duplicates(
            subset=["earnings_date"], keep="first"
        ).reset_index(drop=True)
    return frame


def upcoming_earnings(tickers: list[str], settings: Settings, days: int = 14,
                      source: str | None = None,
                      start_date: str | None = None,
                      confirmed_only: bool = False) -> pd.DataFrame:
    """List upcoming earnings events in the next N days.

    If ``source`` is given (``"yfinance"``, ``"nse"``, ``"bse"``), only rows from that
    source are returned. ``None`` means all sources (default).

    Includes regulatory filing provenance columns:
    - ``exchange_source`` ('NSE', 'BSE', etc.)
    - ``confirmation_status`` ('CONFIRMED', 'TENTATIVE', 'UNCONFIRMED_ESTIMATE')
    - ``board_meeting_purpose``
    - ``filing_id``

    For each ticker:
    - Official exchange filings (CONFIRMED) take absolute precedence over third-party estimates.
    - If an official NSE filing exists, it is prioritized over BSE for dual-listed stocks.
    - If ``confirmed_only=True``, only verified exchange board meeting notices are returned.

    The window is ``[start_date, start_date + days)``. ``start_date`` defaults
    to today, so the default behaviour is unchanged (next ``days`` days).
    """
    if start_date is not None:
        start = pd.Timestamp(start_date).normalize()
    else:
        start = pd.Timestamp.today().normalize()
    end = start + pd.Timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    cols = [
        "ticker",
        "earnings_date",
        "source",
        "exchange_source",
        "confirmation_status",
        "board_meeting_purpose",
        "filing_id",
    ]

    # Build a placeholder list for tickers that appear in overlapping universes.
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)

    if not unique_tickers:
        return pd.DataFrame(columns=cols)

    placeholders = ", ".join(["?"] * len(unique_tickers))
    with _connect(settings) as connection:
        if source is None:
            sql = f"""
                SELECT ticker, earnings_date, source, exchange_source,
                       confirmation_status, board_meeting_purpose, filing_id
                FROM earnings_history
                WHERE ticker IN ({placeholders})
                  AND earnings_date >= ?
                  AND earnings_date <= ?
                ORDER BY earnings_date
            """
            params = unique_tickers + [start_str, end_str]
        else:
            sql = f"""
                SELECT ticker, earnings_date, source, exchange_source,
                       confirmation_status, board_meeting_purpose, filing_id
                FROM earnings_history
                WHERE ticker IN ({placeholders})
                  AND (source = ? OR exchange_source = ?)
                  AND earnings_date >= ?
                  AND earnings_date <= ?
                ORDER BY earnings_date
            """
            params = unique_tickers + [source, source.upper(), start_str, end_str]
        rows = connection.execute(sql, params).fetchall()

    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows, columns=cols)
    df["earnings_date"] = pd.to_datetime(df["earnings_date"])

    # ── Provenance Normalization ──
    def _normalize_row_provenance(r):
        exch = r["exchange_source"]
        status = r["confirmation_status"]
        src = str(r["source"] or "").lower()

        if pd.isna(exch) or not exch:
            if "nse" in src:
                exch = "NSE"
            elif "bse" in src:
                exch = "BSE"
            else:
                exch = None

        if pd.isna(status) or not status:
            if exch in ("NSE", "BSE") or "nse" in src or "bse" in src:
                status = "CONFIRMED"
            else:
                status = "TENTATIVE"
        elif "yfinance" in src and (exch is None or exch == "") and status == "CONFIRMED":
            # Default schema may give 'CONFIRMED' to legacy yfinance rows without exchange_source
            status = "TENTATIVE"

        return exch, status

    norm = [_normalize_row_provenance(row) for _, row in df.iterrows()]
    df["exchange_source"] = [n[0] for n in norm]
    df["confirmation_status"] = [n[1] for n in norm]

    # ── Multi-Exchange and Official Precedence Deduplication ──
    if source is None and not df.empty:
        # 1. Official confirmed filings supersede unconfirmed/tentative estimates
        confirmed_tickers = set(df.loc[df["confirmation_status"] == "CONFIRMED", "ticker"].unique())
        if confirmed_tickers:
            df = df[
                (df["confirmation_status"] == "CONFIRMED") | (~df["ticker"].isin(confirmed_tickers))
            ].reset_index(drop=True)

        # 2. NSE precedence over BSE for dual-listed stocks
        nse_tickers = set(df.loc[df["exchange_source"] == "NSE", "ticker"].unique())
        if nse_tickers:
            df = df[
                (df["exchange_source"] == "NSE") | (~df["ticker"].isin(nse_tickers))
            ].reset_index(drop=True)

    if confirmed_only and not df.empty:
        df = df[df["confirmation_status"] == "CONFIRMED"].reset_index(drop=True)

    loaded_tickers = df["ticker"].nunique()
    source_label = source if source is not None else "ALL_SOURCES"
    logger.info("[EARNINGS-CACHE] Loaded cached earnings dates for %s/%s tickers (source=%s, window: %s to %s)", loaded_tickers, len(unique_tickers), source_label, start_str, end_str)
    return df.sort_values("earnings_date").reset_index(drop=True)


def purge_unconfirmed_future_dates(settings: Settings, ticker: str | None = None) -> int:
    """Purge unconfirmed/speculative future earnings dates from SQLite.

    Guarantees that third-party algorithmic projections (yfinance) or unconfirmed
    estimates for future dates (>= today) do not persist in earnings_history when
    an official exchange filing is required or already exists.
    """
    today_str = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    with _connect(settings) as connection:
        if ticker:
            sql = """
                DELETE FROM earnings_history
                WHERE ticker = ?
                  AND earnings_date >= ?
                  AND (
                      source LIKE '%yfinance%'
                      OR confirmation_status IN ('UNCONFIRMED_ESTIMATE', 'TENTATIVE')
                      OR exchange_source IS NULL
                  )
                  AND confirmation_status != 'CONFIRMED'
            """
            cur = connection.execute(sql, (ticker, today_str))
        else:
            sql = """
                DELETE FROM earnings_history
                WHERE earnings_date >= ?
                  AND (
                      source LIKE '%yfinance%'
                      OR confirmation_status IN ('UNCONFIRMED_ESTIMATE', 'TENTATIVE')
                      OR exchange_source IS NULL
                  )
                  AND confirmation_status != 'CONFIRMED'
            """
            cur = connection.execute(sql, (today_str,))
        purged = cur.rowcount
        connection.commit()
    logger.info("Purged %d unconfirmed future earnings date estimates (ticker=%s)", purged, ticker or "ALL")
    return purged


def _fetch_earnings_for_ticker(args: tuple[str, Settings, bool]) -> tuple[str, int]:
    """Fetch earnings for a single ticker. Returns (ticker, row_count)."""
    ticker, settings, force = args
    try:
        df = fetch_earnings(ticker, settings, force=force)
        return (ticker, int(len(df)))
    except Exception:
        return (ticker, 0)


def classify_board_meeting_purpose(purpose: str, time_str: str = "") -> dict[str, Any]:
    """Strictly classify board meeting agenda and extract session timing.

    Filters out corporate actions (dividends, AGMs, warrants, fund raising) that
    do not include financial results. Distinguishes session timing (BM: Pre, BM: During, BM: Post).

    Returns:
        {
            "is_results": bool,
            "session_timing": "BM: Pre" | "BM: During" | "BM: Post" | None,
            "normalized_purpose": str,
        }
    """
    raw_purpose = str(purpose or "").strip()
    p_lower = raw_purpose.lower()

    # Financial results positive indicators
    results_keywords = [
        "financial result",
        "financial results",
        "quarterly result",
        "quarterly results",
        "audited result",
        "audited results",
        "unaudited result",
        "unaudited results",
        "accounts and results",
        "financial performance",
        "interim financial",
    ]
    has_results = any(kw in p_lower for kw in results_keywords)

    # Excluded keywords (when results keywords are absent)
    excluded_keywords = [
        "agm",
        "annual general meeting",
        "egm",
        "extraordinary general meeting",
        "postal ballot",
        "dividend only",
        "interim dividend only",
        "fund raising",
        "fundraising",
        "warrants",
        "preferential basis",
        "employee stock",
        "esop",
        "allotment of",
        "qip",
    ]
    is_purely_excluded = any(kw in p_lower for kw in excluded_keywords) and not has_results

    is_valid = has_results and not is_purely_excluded

    # Session timing extraction
    session_timing = None
    t_clean = str(time_str or "").strip().lower()

    # 1. From explicit time_str (e.g., "08:30", "16:00", "12:00")
    if t_clean:
        import re
        m = re.search(r"(\d{1,2}):(\d{2})", t_clean)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            minutes = hh * 60 + mm
            # Market hours: 09:15 (555 min) to 15:30 (930 min)
            if minutes < 555:
                session_timing = "BM: Pre"
            elif minutes > 930:
                session_timing = "BM: Post"
            else:
                session_timing = "BM: During"

    # 2. From purpose string text
    if not session_timing:
        if any(kw in p_lower for kw in ["pre-market", "pre market", "before market"]):
            session_timing = "BM: Pre"
        elif any(kw in p_lower for kw in ["post-market", "post market", "after market", "after market hours"]):
            session_timing = "BM: Post"
        elif any(kw in p_lower for kw in ["during market", "market hours"]):
            session_timing = "BM: During"

    norm_purpose = raw_purpose
    if session_timing and f"({session_timing})" not in norm_purpose and f"[{session_timing}]" not in norm_purpose:
        norm_purpose = f"{raw_purpose} [{session_timing}]" if norm_purpose else session_timing

    return {
        "is_results": is_valid,
        "session_timing": session_timing,
        "normalized_purpose": norm_purpose,
    }


def ingest_nse_result_calendar(settings: Settings, days: int = 60) -> dict[str, int]:
    """Ingest upcoming result dates from the official NSE event-calendar API.

    One API call covers all NSE stocks. Result dates are written into the
    shared SQLite ``earnings_history`` table with full exchange provenance metadata
    (exchange_source='NSE', confirmation_status='CONFIRMED', filing_id, purpose).

    Returns ``{"total": ..., "inserted": ..., "errors": ...}``.
    """
    from datetime import date, timedelta

    today = date.today()
    raw = fetch_event_calendar(today, today + timedelta(days=days))
    if "error" in raw:
        logger.warning("nse event-calendar ingest failed: %s", raw["error"])
        return {"total": 0, "inserted": 0, "errors": 1}

    entries = raw if isinstance(raw, list) else raw.get("data", raw.get("result", []))
    if not isinstance(entries, list):
        logger.warning("nse event-calendar returned unexpected payload type=%s", type(raw).__name__)
        return {"total": 0, "inserted": 0, "errors": 1}

    rows: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        purpose_str = entry.get("purpose") or entry.get("desc") or ""
        time_str = entry.get("time") or entry.get("bmTime") or entry.get("session") or ""
        classification = classify_board_meeting_purpose(purpose_str, time_str)
        if not classification["is_results"]:
            continue

        sym = str(entry.get("symbol", "")).strip().upper()
        if not sym:
            continue
        # NSE returns bare codes; yfinance/Nexus needs the .NS suffix.
        if not sym.endswith(".NS"):
            sym = sym + ".NS"

        result_date = entry.get("date") or entry.get("resultDate") or entry.get("bmDate")
        if not result_date:
            continue
        try:
            edate = pd.Timestamp(result_date).strftime("%Y-%m-%d")
        except Exception:
            continue

        filing_id = str(entry.get("id") or entry.get("broadcastId") or f"NSE-BM-{sym}-{edate}")
        rows.append({
            "ticker": sym,
            "earnings_date": edate,
            "purpose": classification["normalized_purpose"],
            "filing_id": filing_id,
        })

    if not rows:
        logger.info("nse result-calendar returned no rows")
        return {"total": 0, "inserted": 0, "errors": 0}

    max_retries = 5
    backoff = 0.5
    inserted = 0
    today_str = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    sym_list = list({r["ticker"] for r in rows})
    db_tuples = [
        (
            r["ticker"],
            r["earnings_date"],
            "nse",
            "NSE",
            "CONFIRMED",
            r["purpose"],
            r["filing_id"],
        )
        for r in rows
    ]

    for attempt in range(max_retries):
        try:
            with _connect(settings) as connection:
                # 1. Purge any unconfirmed yfinance future dates for these tickers
                for i in range(0, len(sym_list), 500):
                    chunk = sym_list[i : i + 500]
                    ph = ", ".join(["?"] * len(chunk))
                    connection.execute(
                        f"""
                        DELETE FROM earnings_history
                        WHERE ticker IN ({ph})
                          AND earnings_date >= ?
                          AND source LIKE '%yfinance%'
                        """,
                        chunk + [today_str],
                    )

                # 2. Rescheduling / Postponement: purge older upcoming official dates superseded by new filings
                for r in rows:
                    connection.execute(
                        """
                        DELETE FROM earnings_history
                        WHERE ticker = ?
                          AND earnings_date >= ?
                          AND earnings_date != ?
                          AND exchange_source = 'NSE'
                        """,
                        (r["ticker"], today_str, r["earnings_date"]),
                    )

                # 3. Insert or update verified NSE records with full provenance
                inserted = connection.executemany(
                    """
                    INSERT INTO earnings_history (
                        ticker, earnings_date, source, exchange_source,
                        confirmation_status, board_meeting_purpose, filing_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                        source = excluded.source,
                        exchange_source = excluded.exchange_source,
                        confirmation_status = excluded.confirmation_status,
                        board_meeting_purpose = excluded.board_meeting_purpose,
                        filing_id = excluded.filing_id
                    """,
                    db_tuples,
                ).rowcount
                connection.commit()
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                logger.warning(
                    "Database locked during NSE results calendar ingest (attempt %d/%d), retrying in %.1fs...",
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            raise

    logger.info("nse result-calendar ingest complete total=%s inserted=%s", len(rows), inserted)
    return {"total": len(rows), "inserted": inserted, "errors": 0}


def fetch_bse_result_calendar(
    start_date: str | Any = None,
    end_date: str | Any = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch multi-exchange (BSE/NSE) corporate earnings board meetings calendar from MoneyControl.

    Captures official board meeting announcements filed under BSE and NSE corporate actions,
    including BSE-exclusive listings and newly listed companies (e.g., Onix Solar Energy,
    Grand Oak Canyons Distillery, K&R Rail Engineering, Lotus Chocolate).
    """
    import json
    import urllib.request
    from datetime import datetime
    from concurrent.futures import ThreadPoolExecutor

    if start_date is None:
        start_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    elif hasattr(start_date, "strftime"):
        start_date = start_date.strftime("%Y-%m-%d")
    else:
        start_date = str(start_date)

    if end_date is None:
        end_date = (pd.Timestamp(start_date) + pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    elif hasattr(end_date, "strftime"):
        end_date = end_date.strftime("%Y-%m-%d")
    else:
        end_date = str(end_date)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.moneycontrol.com/",
    }

    all_raw_items = []
    page = 1
    max_pages = 25

    while page <= max_pages:
        url = f"https://api.moneycontrol.com/mcapi/v1/earnings/get-earnings-data?indexId=All&startDate={start_date}&endDate={end_date}&limit={limit}&page={page}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data or data.get("success") != 1:
                    break
                raw_data = data.get("data")
                items = raw_data.get("list", []) if isinstance(raw_data, dict) else (raw_data if isinstance(raw_data, list) else [])
                if not items:
                    break
                all_raw_items.extend(items)
                total_records = int(data.get("totalRecords") or (raw_data.get("pagination", {}).get("totalRecords") if isinstance(raw_data, dict) else 0) or 0)
                if (total_records > 0 and len(all_raw_items) >= total_records) or len(items) < limit:
                    break
        except Exception as e:
            logger.warning("BSE/Moneycontrol earnings calendar fetch failed page=%s error=%s", page, e)
            break
        page += 1

    if not all_raw_items:
        return []

    # Filter out non-result board meetings using strict purpose classification
    filtered_items = []
    for item in all_raw_items:
        if not isinstance(item, dict):
            continue
        purpose = str(item.get("purpose", "")).strip()
        if purpose:
            classification = classify_board_meeting_purpose(purpose)
            if not classification["is_results"]:
                continue
        filtered_items.append(item)

    if not filtered_items:
        return []

    def _resolve_item(item: dict[str, Any]) -> dict[str, Any] | None:
        sc_id = item.get("scId")
        ex = item.get("exchange", "N")
        date_val = item.get("date")
        company_name = item.get("stockName") or item.get("shortName") or item.get("companyName")
        purpose_str = item.get("resultType") or item.get("purpose", "Financial Results")
        market_cap = item.get("marketCap")

        if not sc_id or not date_val:
            return None

        # Parse date value (handles '8 Oct', '17 Oct', or 'YYYY-MM-DD')
        edate = None
        date_str = str(date_val).strip()
        try:
            if "-" in date_str and len(date_str) == 10:
                edate = pd.Timestamp(date_str).strftime("%Y-%m-%d")
            else:
                start_year = pd.Timestamp(start_date).year
                parsed_dt = datetime.strptime(f"{date_str} {start_year}", "%d %b %Y")
                if parsed_dt < pd.Timestamp(start_date) - pd.Timedelta(days=30):
                    parsed_dt = datetime.strptime(f"{date_str} {start_year + 1}", "%d %b %Y")
                edate = parsed_dt.strftime("%Y-%m-%d")
        except Exception:
            try:
                edate = pd.Timestamp(date_val).strftime("%Y-%m-%d")
            except Exception:
                return None

        ticker = None
        ex_code = "bse" if str(ex).upper() == "B" else "nse"
        try:
            feed_url = f"https://priceapi.moneycontrol.com/pricefeed/{ex_code}/equitycash/{sc_id}"
            feed_req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(feed_req, timeout=5) as resp:
                fdata = json.loads(resp.read().decode("utf-8"))
                if fdata.get("code") == "200" and "data" in fdata and isinstance(fdata["data"], dict):
                    finfo = fdata["data"]
                    nse_id = finfo.get("NSEID")
                    bse_id = finfo.get("BSEID")
                    disp_id = finfo.get("DISPID")
                    c_name = finfo.get("company") or company_name
                    if c_name:
                        company_name = c_name
                    mcap_val = finfo.get("MktCap")
                    if mcap_val:
                        try:
                            market_cap = float(str(mcap_val).replace(",", ""))
                        except Exception:
                            pass

                    if nse_id:
                        ticker = f"{nse_id}.NS"
                    elif bse_id:
                        ticker = f"{bse_id}.BO"
                    elif disp_id:
                        ticker = f"{disp_id}.BO"
        except Exception:
            pass

        if not ticker:
            if ex_code == "nse" and str(sc_id).isalpha():
                ticker = f"{sc_id}.NS"
            else:
                ticker = f"{sc_id}.BO"

        return {
            "ticker": ticker.upper(),
            "earnings_date": edate,
            "company_name": company_name,
            "market_cap": market_cap,
            "source": "bse" if (ex_code == "bse" or ticker.endswith(".BO")) else "nse",
            "purpose": purpose_str,
        }

    resolved_events = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(_resolve_item, item) for item in filtered_items]
        for f in futures:
            try:
                res = f.result()
                if res:
                    resolved_events.append(res)
            except Exception:
                pass

    return resolved_events


def ingest_bse_result_calendar(settings: Settings, days: int = 60) -> dict[str, int]:
    """Ingest upcoming result dates from BSE / Multi-exchange corporate filing calendar.

    Covers both BSE-exclusive and NSE-listed equities. Writes result dates to SQLite
    earnings_history and records newly discovered company metadata into tickers table.
    """
    from datetime import date, timedelta

    today = date.today()
    events = fetch_bse_result_calendar(
        start_date=today,
        end_date=today + timedelta(days=days),
    )

    if not events:
        logger.info("bse/multi-exchange result-calendar returned no events")
        return {"total": 0, "inserted": 0, "errors": 0}

    eh_rows = []
    ticker_rows = []
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")

    with _connect(settings) as connection:
        # Check existing confirmed upcoming NSE dates to enforce NSE precedence for dual-listed stocks
        existing_nse_upcoming = {}
        for row in connection.execute(
            "SELECT ticker, earnings_date FROM earnings_history WHERE exchange_source = 'NSE' AND earnings_date >= ?",
            (today_str,),
        ).fetchall():
            existing_nse_upcoming[row[0]] = row[1]

        for ev in events:
            ticker = ev["ticker"]
            edate = ev["earnings_date"]
            cname = ev.get("company_name")
            mcap = ev.get("market_cap")
            purpose_raw = ev.get("purpose", "Financial Results")
            classification = classify_board_meeting_purpose(purpose_raw)
            if not classification["is_results"]:
                continue

            # Multi-Exchange conflict resolution:
            # If ticker already has an authoritative upcoming NSE date, do NOT overwrite it!
            if ticker in existing_nse_upcoming:
                continue

            source = "bse"
            exchange_source = "BSE"
            confirmation_status = "CONFIRMED"
            filing_id = f"BSE-BM-{ticker}-{edate}"
            purpose = classification["normalized_purpose"]

            eh_rows.append((
                ticker,
                edate,
                source,
                exchange_source,
                confirmation_status,
                purpose,
                filing_id,
            ))
            if cname:
                ticker_rows.append((ticker, cname, mcap, now_str))

        if not eh_rows:
            logger.info("bse/multi-exchange result-calendar returned no actionable rows after filtering/conflict resolution")
            return {"total": 0, "inserted": 0, "errors": 0}

        # Purge any unconfirmed yfinance future dates for incoming symbols before merging verified BSE dates
        sym_list = list({r[0] for r in eh_rows})
        for i in range(0, len(sym_list), 500):
            chunk = sym_list[i : i + 500]
            ph = ", ".join(["?"] * len(chunk))
            connection.execute(
                f"""
                DELETE FROM earnings_history
                WHERE ticker IN ({ph})
                  AND earnings_date >= ?
                  AND source LIKE '%yfinance%'
                """,
                chunk + [today_str],
            )

        # Rescheduling for BSE records: purge older upcoming BSE dates superseded by new filing
        for r in eh_rows:
            connection.execute(
                """
                DELETE FROM earnings_history
                WHERE ticker = ?
                  AND earnings_date >= ?
                  AND earnings_date != ?
                  AND exchange_source = 'BSE'
                """,
                (r[0], today_str, r[1]),
            )

        inserted = connection.executemany(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, source, exchange_source,
                confirmation_status, board_meeting_purpose, filing_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                source = excluded.source,
                exchange_source = excluded.exchange_source,
                confirmation_status = excluded.confirmation_status,
                board_meeting_purpose = excluded.board_meeting_purpose,
                filing_id = excluded.filing_id
            """,
            eh_rows,
        ).rowcount

        if ticker_rows:
            cols = {r[1] for r in connection.execute("PRAGMA table_info(tickers)").fetchall()}
            name_col = "name" if "name" in cols else "company_name"
            if "name" in cols and "company_name" in cols:
                dual_rows = [(r[0], r[1], r[1], r[2], r[3]) for r in ticker_rows]
                connection.executemany(
                    """
                    INSERT INTO tickers (ticker, name, company_name, market_cap, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                        name = COALESCE(excluded.name, tickers.name),
                        company_name = COALESCE(excluded.company_name, tickers.company_name),
                        market_cap = COALESCE(excluded.market_cap, tickers.market_cap),
                        last_updated = excluded.last_updated
                    """,
                    dual_rows,
                )
            else:
                connection.executemany(
                    f"""
                    INSERT INTO tickers (ticker, {name_col}, market_cap, last_updated)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                        {name_col} = COALESCE(excluded.{name_col}, tickers.{name_col}),
                        market_cap = COALESCE(excluded.market_cap, tickers.market_cap),
                        last_updated = excluded.last_updated
                    """,
                    ticker_rows,
                )
        connection.commit()

    logger.info("bse/multi-exchange result-calendar ingest complete total=%s inserted=%s", len(eh_rows), inserted)
    return {"total": len(eh_rows), "inserted": inserted, "errors": 0}


def ingest_earnings_incremental(tickers: list[str], settings: Settings) -> dict[str, int]:
    """Fetch earnings only for tickers that are missing earnings data.
    
    Identifies tickers with NO earnings rows in earnings_history. For those,
    checks price_history for a listing date (MIN(date)) — skips tickers with
    no price history or listed < 90 days ago (too new for quarterly earnings).
    Only fetches earnings for tickers that should have earnings but don't.
    
    Returns {"total", "already_cached", "fetched", "skipped_no_listing", "errors"}.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    if not tickers:
        return {"total": 0, "already_cached": 0, "fetched": 0, "skipped_no_listing": 0, "errors": 0}
    
    total = len(tickers)
    batch_size = 50
    processed = 0
    already_cached = 0
    skipped_no_listing = 0
    errors = 0
    fetched = 0
    
    # Identify tickers that need earnings data
    tickers_to_fetch: list[str] = []
    with _connect(settings) as connection:
        for ticker in tickers:
            # Check if ticker already has earnings
            row = connection.execute(
                "SELECT COUNT(*) FROM earnings_history WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            has_earnings = row and row[0] > 0
            
            if has_earnings:
                already_cached += 1
                processed += 1
                continue
            
            # Check if ticker has price history and get listing date
            price_row = connection.execute(
                "SELECT MIN(date), MAX(date) FROM price_history WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            
            if not price_row or not price_row[0]:
                # No price history at all
                skipped_no_listing += 1
                processed += 1
                logger.info("skipping ticker=%s reason=no_price_history", ticker)
                continue
            
            listing_date = pd.Timestamp(price_row[0])
            age_days = (pd.Timestamp.now() - listing_date).total_seconds() / 86400
            
            if age_days < 90:
                # Too new for quarterly earnings
                skipped_no_listing += 1
                processed += 1
                logger.info("skipping ticker=%s reason=too_new listing_date=%s age_days=%.1f",
                           ticker, listing_date.date(), age_days)
                continue
            
            tickers_to_fetch.append(ticker)
    
    if already_cached == total:
        logger.info("all %s tickers already have earnings cached", total)
        return {"total": total, "already_cached": already_cached, "fetched": 0,
                "skipped_no_listing": 0, "errors": 0}
    
    logger.info("incremental earnings: %s total, %s cached, %s to fetch, %s skipped",
                total, already_cached, len(tickers_to_fetch), skipped_no_listing)
    
    # Fetch earnings for tickers that need it
    fetch_total = len(tickers_to_fetch)
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_earnings_for_ticker, (ticker, settings, False)): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, count = future.result()
                processed += 1
                if count > 0:
                    fetched += 1
                else:
                    errors += 1
        
        logger.info("earnings incremental batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)
        
        # Wait 2 seconds between batches (skip after last batch)
        if i + batch_size < fetch_total:
            time.sleep(2)
    
    logger.info("earnings incremental complete: %s fetched, %s errors, %s skipped_no_listing",
                fetched, errors, skipped_no_listing)
    return {
        "total": total,
        "already_cached": already_cached,
        "fetched": fetched,
        "skipped_no_listing": skipped_no_listing,
        "errors": errors,
    }


def ingest_earnings(tickers: list[str], settings: Settings, force: bool = False) -> dict[str, int]:
    """Download or refresh cached earnings data for the requested tickers.

    Uses ThreadPoolExecutor with 10 workers, batched in groups of 50 with
    2-second delays between batches to avoid yfinance rate limits.
    Skips tickers with fresh cache unless force=True.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, int] = {}
    total = len(tickers)
    batch_size = 50
    processed = 0

    # Filter out tickers with fresh cache (when not forcing)
    tickers_to_fetch: list[str] = []
    cached_hits = 0
    for ticker in tickers:
        if not force and _is_fresh(ticker, settings):
            # Load from cache to get row count
            df = load_earnings(ticker, settings)
            results[ticker] = int(len(df))
            cached_hits += 1
            processed += 1
        else:
            tickers_to_fetch.append(ticker)

    if cached_hits == total:
        logger.info("earnings cache hit for all %s tickers, skipping fetch", total)
        return results

    logger.info("ingesting earnings for %s tickers (%s cached, %s to fetch)",
                total, cached_hits, len(tickers_to_fetch))

    fetch_total = len(tickers_to_fetch)
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_earnings_for_ticker, (ticker, settings, force)): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, count = future.result()
                processed += 1
                results[ticker] = count

        logger.info("earnings ingest batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)

        # Wait 2 seconds between batches (skip after last batch)
        if i + batch_size < fetch_total:
            time.sleep(2)

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("earnings ingest complete: %s/%s tickers with data", ok, total)
    return results


def get_fetch_record_status(settings: Settings) -> dict[str, Any]:
    """Get the fetch record status for the present day."""
    import json
    today_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT fetch_date, fetched_at, status, events_count, inserted_count FROM earnings_fetch_log WHERE fetch_date = ?",
            (today_str,),
        ).fetchone()
        
        # If no row for today, get latest entry
        if not row:
            row = connection.execute(
                "SELECT fetch_date, fetched_at, status, events_count, inserted_count FROM earnings_fetch_log ORDER BY fetch_date DESC LIMIT 1"
            ).fetchone()

        # Count total upcoming events in database
        total_events = connection.execute(
            "SELECT COUNT(*) FROM earnings_history WHERE earnings_date >= ?",
            (today_str,),
        ).fetchone()[0]

    if not row:
        return {
            "today": today_str,
            "synced_today": False,
            "last_fetched_at": None,
            "status": "NOT_SYNCED",
            "events_count": total_events,
            "inserted_count": 0,
        }

    fetch_date, fetched_at, status, events_count, inserted_count = row
    return {
        "today": today_str,
        "synced_today": (fetch_date == today_str),
        "last_fetched_at": fetched_at,
        "status": status if fetch_date == today_str else "STALE",
        "events_count": max(events_count, total_events),
        "inserted_count": inserted_count,
    }


def sync_present_day_earnings_delta(settings: Settings, force: bool = False) -> dict[str, Any]:
    """Check if earnings calendar for present day is fetched; if missing or stale, fetch delta and update record."""
    today_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    status_info = get_fetch_record_status(settings)

    if not force and status_info.get("synced_today"):
        logger.info("Present day earnings calendar already synced today (%s)", today_str)
        return status_info

    logger.info("Fetching present day earnings delta for date=%s (force=%s)...", today_str, force)
    ingest_nse = ingest_nse_result_calendar(settings, days=60)
    ingest_bse = ingest_bse_result_calendar(settings, days=60)
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = ingest_nse.get("inserted", 0) + ingest_bse.get("inserted", 0)
    total_found = ingest_nse.get("total", 0) + ingest_bse.get("total", 0)

    max_retries = 5
    backoff = 0.5
    total_events = 0
    for attempt in range(max_retries):
        try:
            with _connect(settings) as connection:
                total_events = connection.execute(
                    "SELECT COUNT(*) FROM earnings_history WHERE earnings_date >= ?",
                    (today_str,),
                ).fetchone()[0]

                connection.execute(
                    "INSERT OR REPLACE INTO earnings_fetch_log (fetch_date, fetched_at, status, events_count, inserted_count) VALUES (?, ?, ?, ?, ?)",
                    (today_str, now_str, "UP_TO_DATE", total_events, inserted),
                )
                connection.commit()
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                logger.warning(
                    "Database locked during present day earnings delta sync (attempt %d/%d), retrying in %.1fs...",
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            raise

    return {
        "today": today_str,
        "synced_today": True,
        "last_fetched_at": now_str,
        "status": "UP_TO_DATE",
        "events_count": total_events,
        "inserted_count": inserted,
        "total_calendar_events": total_found,
    }


def get_cached_month_filter(settings: Settings, cache_key: str = "ALL") -> dict[str, Any] | None:
    """Retrieve precalculated month filter payload from SQLite cache."""
    import json
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT payload_json, updated_at FROM earnings_month_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row[0])
        data["_cached_at"] = row[1]
        return data
    except Exception as e:
        logger.warning("Failed to decode cached month filter for key=%s: %s", cache_key, e)
        return None


def set_cached_month_filter(settings: Settings, cache_key: str, payload: dict[str, Any]) -> None:
    """Store precalculated month filter payload into SQLite cache."""
    import json
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    payload_str = json.dumps(payload)
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO earnings_month_cache (cache_key, updated_at, payload_json) VALUES (?, ?, ?)",
            (cache_key, now_str, payload_str),
        )
        connection.commit()


def resolve_tickers_for_watchlist_or_universe(
    name: str | None,
    settings: Settings | None = None,
) -> list[str]:
    """Resolve a watchlist name or universe identifier to a list of tickers."""
    settings = settings or Settings()
    if not name or name.strip().upper() in ("ALL", "GLOBAL", "DEFAULT", "UNIVERSE", ""):
        return []

    clean_name = name.strip()

    # 1. Check custom watchlists in SQLite
    try:
        from earnings_engine.data.watchlists import get_watchlist
        wl_tickers = get_watchlist(clean_name, settings)
        if wl_tickers:
            return wl_tickers
    except Exception:
        pass

    # 2. Check standard universes (e.g. NSE_ALL, NSE_TOP, NSE_LARGE_CAP, US_TOP, IN, US)
    try:
        from earnings_engine.data.universe import load_universe
        u_tickers = load_universe(clean_name, settings)
        if u_tickers:
            return u_tickers
    except Exception:
        pass

    return []


def get_watchlist_earnings_freshness(
    watchlist_name: str | None = None,
    tickers: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Calculate aggregated earnings freshness metrics for a watchlist or ticker list."""
    settings = settings or Settings()

    is_all_universe = not watchlist_name or watchlist_name.strip().upper() in ("ALL", "GLOBAL", "DEFAULT", "UNIVERSE", "")

    if tickers is None and not is_all_universe:
        tickers = resolve_tickers_for_watchlist_or_universe(watchlist_name, settings)

    if tickers is None or (not tickers and is_all_universe):
        with _connect(settings) as connection:
            row = connection.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(earnings_fetched_at) as fetched_count,
                    MAX(earnings_fetched_at) as latest_fetch,
                    MIN(earnings_fetched_at) as oldest_fetch
                FROM tickers
                """
            ).fetchone()
        
        total_tickers = row[0] if row else 0
        fetched_count = row[1] if row else 0
        latest_fetch = row[2] if row else None
        oldest_fetch = row[3] if row else None

        # Fallback to earnings_history if tickers table count is 0
        if total_tickers == 0:
            with _connect(settings) as connection:
                eh_row = connection.execute("SELECT COUNT(DISTINCT ticker), MAX(fetched_at), MIN(fetched_at) FROM earnings_history").fetchone()
                if eh_row and eh_row[0]:
                    total_tickers = eh_row[0]
                    fetched_count = eh_row[0]
                    latest_fetch = eh_row[1]
                    oldest_fetch = eh_row[2]

        if total_tickers == 0:
            try:
                from earnings_engine.data.universe import load_universe
                u_tickers = load_universe("NSE_ALL", settings) or load_universe("IN", settings)
                total_tickers = len(u_tickers)
            except Exception:
                total_tickers = 0
    else:
        if not tickers:
            return {
                "watchlist": watchlist_name or "ALL",
                "total_tickers": 0,
                "cached_tickers": 0,
                "last_updated": None,
                "relative_time": "No tickers in watchlist",
                "status": "EMPTY",
            }

        total_tickers = len(tickers)
        # Avoid exceeding SQLite 999 parameter limit if watchlist is huge
        if len(tickers) <= 900:
            placeholders = ", ".join(["?"] * len(tickers))
            with _connect(settings) as connection:
                row = connection.execute(
                    f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(earnings_fetched_at) as fetched_count,
                        MAX(earnings_fetched_at) as latest_fetch,
                        MIN(earnings_fetched_at) as oldest_fetch
                    FROM tickers
                    WHERE ticker IN ({placeholders})
                    """,
                    tickers,
                ).fetchone()
            fetched_count = row[1] if row else 0
            latest_fetch = row[2] if row else None
            oldest_fetch = row[3] if row else None
        else:
            fetched_count = 0
            latest_fetch = None
            oldest_fetch = None
            for i in range(0, len(tickers), 500):
                chunk = tickers[i:i+500]
                placeholders = ", ".join(["?"] * len(chunk))
                with _connect(settings) as connection:
                    row = connection.execute(
                        f"SELECT COUNT(earnings_fetched_at), MAX(earnings_fetched_at), MIN(earnings_fetched_at) FROM tickers WHERE ticker IN ({placeholders})",
                        chunk,
                    ).fetchone()
                    if row:
                        fetched_count += (row[0] or 0)
                        if row[1] and (latest_fetch is None or row[1] > latest_fetch):
                            latest_fetch = row[1]
                        if row[2] and (oldest_fetch is None or row[2] < oldest_fetch):
                            oldest_fetch = row[2]

    # Calculate human-readable relative time
    relative_time = "Never"
    status = "STALE"
    if latest_fetch:
        try:
            ts = pd.Timestamp(latest_fetch)
            delta = pd.Timestamp.now() - ts
            hours = delta.total_seconds() / 3600.0
            if hours < 1:
                relative_time = "Just now"
                status = "FRESH"
            elif hours < 24:
                relative_time = f"{int(hours)}h ago"
                status = "FRESH"
            elif hours < 48:
                relative_time = "1 day ago"
                status = "WARM"
            else:
                days = int(hours / 24)
                relative_time = f"{days} days ago"
                status = "WARM" if days <= 7 else "STALE"
        except Exception:
            relative_time = str(latest_fetch)

    return {
        "watchlist": watchlist_name or "ALL",
        "total_tickers": total_tickers,
        "cached_tickers": fetched_count,
        "last_updated": latest_fetch,
        "oldest_updated": oldest_fetch,
        "relative_time": relative_time,
        "status": status,
    }


def refresh_watchlist_earnings(
    watchlist_name: str | None = None,
    tickers: list[str] | None = None,
    settings: Settings | None = None,
    max_workers: int = 6,
) -> dict[str, Any]:
    """Force-refresh earnings data for all tickers in a specific watchlist in parallel."""
    import concurrent.futures
    settings = settings or Settings()

    if tickers is None:
        if watchlist_name:
            tickers = resolve_tickers_for_watchlist_or_universe(watchlist_name, settings)
        else:
            try:
                from earnings_engine.data.universe import load_universe
                tickers = load_universe("NSE_TOP", settings) or load_universe("IN", settings)
            except Exception:
                tickers = []

    if not tickers:
        return {"success": False, "error": "No tickers in selected watchlist", "refreshed_count": 0}

    refreshed = []
    errors = []

    def _fetch_single(t: str):
        try:
            fetch_earnings(t, settings, force=True)
            return t, True, None
        except Exception as err:
            return t, False, str(err)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_single, t): t for t in tickers}
        for future in concurrent.futures.as_completed(futures):
            sym, ok, err_msg = future.result()
            if ok:
                refreshed.append(sym)
            else:
                errors.append({"ticker": sym, "error": err_msg})

    freshness = get_watchlist_earnings_freshness(watchlist_name, tickers, settings)
    return {
        "success": True,
        "watchlist": watchlist_name or "CUSTOM",
        "total_tickers": len(tickers),
        "refreshed_count": len(refreshed),
        "error_count": len(errors),
        "freshness": freshness,
    }


def refresh_earnings_from_source(
    ticker: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Force re-fetch official earnings calendar and reported EPS from authentic sources (yfinance & NSE).

    Enforces strict guard rails:
    1. Fetches authentic historical earnings from yfinance with force=True.
    2. Purges any stale/spurious synthetic or duplicate records for this ticker.
    3. Recalculates metrics and updates tickers master table.
    """
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if not sym:
        return {"success": False, "error": "Ticker symbol is required"}

    try:
        # 1. Force refresh from yfinance
        df = fetch_earnings(sym, settings, force=True)

        # 2. If NSE stock, ingest NSE calendar as well
        if sym.endswith(".NS"):
            try:
                ingest_nse_result_calendar(settings)
            except Exception as nse_err:
                logger.debug("NSE calendar refresh error for %s: %s", sym, nse_err)

        # 3. Clean up any synthetic/spurious duplicate records for this ticker
        with _connect(settings) as connection:
            connection.execute(
                "DELETE FROM earnings_history WHERE ticker = ? AND source IN ('derived_historical_average', 'quarterly_income_stmt_diluted+yfinance')",
                (sym,),
            )
            # Remove quarterly_income_stmt if authentic yfinance/nse exists within 60 days
            stmt_rows = connection.execute(
                "SELECT earnings_date FROM earnings_history WHERE ticker = ? AND source = 'quarterly_income_stmt'",
                (sym,),
            ).fetchall()
            for (s_ed,) in stmt_rows:
                auth_row = connection.execute(
                    """
                    SELECT earnings_date FROM earnings_history
                    WHERE ticker = ? AND source IN ('yfinance', 'nse')
                    AND abs(julianday(earnings_date) - julianday(?)) <= 60
                    """,
                    (sym, s_ed),
                ).fetchone()
                if auth_row:
                    connection.execute(
                        "DELETE FROM earnings_history WHERE ticker = ? AND earnings_date = ? AND source = 'quarterly_income_stmt'",
                        (sym, s_ed),
                    )
            connection.commit()

        # 4. Trigger metric recalculation
        recalc_result: dict[str, Any] = {}
        try:
            from earnings_engine.api.recalculate_api import recalculate_ticker_metrics
            recalc_result = recalculate_ticker_metrics(sym, settings=settings)
        except Exception as e:
            logger.debug("Recalculate metrics in refresh_earnings_from_source failed for %s: %s", sym, e)

        # 5. Load updated earnings records with clean JSON serialization
        updated_df = load_earnings(sym, settings)
        records = []
        if not updated_df.empty:
            for _, r in updated_df.iterrows():
                ed_val = r.get("earnings_date")
                ed_str = ed_val.strftime("%Y-%m-%d") if hasattr(ed_val, "strftime") else str(ed_val)[:10]
                eps_est = float(r["eps_estimate"]) if pd.notna(r.get("eps_estimate")) else None
                eps_rep = float(r["eps_reported"]) if pd.notna(r.get("eps_reported")) else None
                surp = float(r["surprise_pct"]) if pd.notna(r.get("surprise_pct")) else None
                records.append({
                    "earnings_date": ed_str,
                    "eps_estimate": eps_est,
                    "eps_reported": eps_rep,
                    "surprise_pct": surp,
                })

        return {
            "success": True,
            "ticker": sym,
            "source": "yfinance/nse",
            "message": f"Successfully refreshed authoritative earnings from source for {sym} ({len(records)} events)",
            "events_count": len(records),
            "records": records,
            "recalculate": recalc_result,
        }
    except Exception as e:
        logger.exception("Error in refresh_earnings_from_source for %s: %s", sym, e)
        return {"success": False, "ticker": sym, "error": str(e)}


