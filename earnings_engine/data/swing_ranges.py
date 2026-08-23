"""SQLite-backed swing range and cycle history storage.

Ranges are keyed by (watchlist, ticker) so users can have different range
theories for the same stock across different lists.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path


def _connect(settings: Settings) -> Any:
    settings.ensure_dirs()
    conn = get_db_connection(settings)
    if not is_turso_enabled():
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 10000;")
        except Exception:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS swing_ranges (
            watchlist      TEXT NOT NULL,
            ticker         TEXT NOT NULL,
            lower_bound    REAL,
            upper_bound    REAL,
            source         TEXT NOT NULL, -- 'auto' | 'user'
            cycles         INTEGER,
            avg_cycle_days REAL,
            last_updated   TEXT NOT NULL,
            PRIMARY KEY (watchlist, ticker)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS swing_cycle_history (
            watchlist     TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            cycle_idx     INTEGER NOT NULL,
            cycle_start   TEXT NOT NULL,
            cycle_end     TEXT NOT NULL,
            duration_days REAL,
            lower_bound   REAL,
            upper_bound   REAL,
            PRIMARY KEY (watchlist, ticker, cycle_idx)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_ranges_wl ON swing_ranges(watchlist);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_cycle_hist ON swing_cycle_history(watchlist, ticker);")
    conn.commit()
    return conn


def get_swing_range(watchlist: str, ticker: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Return the current swing range for a ticker in a watchlist."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        row = conn.execute(
            "SELECT lower_bound, upper_bound, source, cycles, avg_cycle_days, last_updated "
            "FROM swing_ranges WHERE watchlist = ? AND ticker = ?",
            (watchlist, ticker),
        ).fetchone()

    if not row:
        return None

    return {
        "watchlist": watchlist,
        "ticker": ticker,
        "lower_bound": row[0],
        "upper_bound": row[1],
        "source": row[2],
        "cycles": row[3],
        "avg_cycle_days": row[4],
        "last_updated": row[5],
    }


def set_user_range(
    watchlist: str,
    ticker: str,
    lower: float,
    upper: float,
    cycles: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Manually set a swing range for a ticker (source='user')."""
    settings = settings or Settings()
    now = datetime.now().isoformat(timespec="seconds")
    lower_val = round(float(lower), 2)
    upper_val = round(float(upper), 2)
    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO swing_ranges 
            (watchlist, ticker, lower_bound, upper_bound, source, cycles, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (watchlist, ticker, lower_val, upper_val, "user", cycles, now),
        )
        conn.commit()

    return {
        "success": True,
        "watchlist": watchlist,
        "ticker": ticker,
        "lower_bound": lower_val,
        "upper_bound": upper_val,
        "source": "user",
        "cycles": cycles,
        "last_updated": now,
    }


def record_auto_range(
    watchlist: str,
    ticker: str,
    lower: float,
    upper: float,
    cycles: int | None = None,
    avg_days: float | None = None,
    cycles_data: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> None:
    """Record an auto-detected swing range. Only overwrites if source is already 'auto' or missing."""
    settings = settings or Settings()
    now = datetime.now().isoformat(timespec="seconds")
    lower_val = round(float(lower), 2)
    upper_val = round(float(upper), 2)
    with _connect(settings) as conn:
        # Check if a user override or existing record exists
        existing = conn.execute(
            "SELECT source, lower_bound, upper_bound FROM swing_ranges WHERE watchlist = ? AND ticker = ?",
            (watchlist, ticker),
        ).fetchone()

        if existing:
            if existing[0] == "user":
                return  # Don't overwrite user settings
            # If auto-range values haven't changed, skip redundant write
            if existing[1] == lower_val and existing[2] == upper_val:
                return

        conn.execute(
            """
            INSERT OR REPLACE INTO swing_ranges 
            (watchlist, ticker, lower_bound, upper_bound, source, cycles, avg_cycle_days, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (watchlist, ticker, lower_val, upper_val, "auto", cycles, avg_days, now),
        )

        if cycles_data:
            conn.execute(
                "DELETE FROM swing_cycle_history WHERE watchlist = ? AND ticker = ?",
                (watchlist, ticker),
            )
            cycle_rows = [
                (
                    watchlist,
                    ticker,
                    i,
                    c["start"],
                    c["end"],
                    c["duration"],
                    c.get("lower", lower),
                    c.get("upper", upper),
                )
                for i, c in enumerate(cycles_data)
            ]
            conn.executemany(
                """
                INSERT INTO swing_cycle_history 
                (watchlist, ticker, cycle_idx, cycle_start, cycle_end, duration_days, lower_bound, upper_bound)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                cycle_rows,
            )
        conn.commit()


def clear_user_range(watchlist: str, ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Delete a range entry (useful for reverting to auto)."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute(
            "DELETE FROM swing_ranges WHERE watchlist = ? AND ticker = ?",
            (watchlist, ticker),
        )
        conn.execute(
            "DELETE FROM swing_cycle_history WHERE watchlist = ? AND ticker = ?",
            (watchlist, ticker),
        )
        conn.commit()
    return {"success": True, "watchlist": watchlist, "ticker": ticker}


def list_ranges(watchlist: str | None = None, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return all stored ranges for a watchlist or all watchlists if None/ALL."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        if watchlist and watchlist.upper() != "ALL":
            rows = conn.execute(
                "SELECT watchlist, ticker, lower_bound, upper_bound, source, cycles, avg_cycle_days, last_updated "
                "FROM swing_ranges WHERE watchlist = ?",
                (watchlist,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT watchlist, ticker, lower_bound, upper_bound, source, cycles, avg_cycle_days, last_updated "
                "FROM swing_ranges",
            ).fetchall()

    return [
        {
            "watchlist": r[0],
            "ticker": r[1],
            "lower_bound": r[2],
            "upper_bound": r[3],
            "source": r[4],
            "cycles": r[5],
            "avg_cycle_days": r[6],
            "last_updated": r[7],
        }
        for r in rows
    ]


def get_cycle_history(watchlist: str, ticker: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return the detailed cycle history for a ticker."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        rows = conn.execute(
            "SELECT cycle_idx, cycle_start, cycle_end, duration_days, lower_bound, upper_bound "
            "FROM swing_cycle_history WHERE watchlist = ? AND ticker = ? ORDER BY cycle_idx",
            (watchlist, ticker),
        ).fetchall()

    return [
        {
            "idx": r[0],
            "start": r[1],
            "end": r[2],
            "duration": r[3],
            "lower": r[4],
            "upper": r[5],
        }
        for r in rows
    ]
