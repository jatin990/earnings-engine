"""SQLite-backed watchlist storage.

Watchlists live in the shared ``prices.sqlite3`` database (a ``watchlists``
table) instead of flat files, so they persist across restarts and support
multiple named lists (one per dashboard tab plus the global ``my_watchlist``).
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            name     TEXT NOT NULL,
            ticker   TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (name, ticker)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_meta (
            name       TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """
    )
    # Auto-migrate rebranded/renamed symbols (e.g. ZOMATO.NS -> ETERNAL.NS)
    try:
        conn.execute("UPDATE watchlists SET ticker = 'ETERNAL.NS' WHERE ticker = 'ZOMATO.NS'")
    except Exception:
        pass
    conn.commit()
    return conn


def _sanitize(name: str) -> str:
    """Sanitize a watchlist name to a safe ``[A-Za-z0-9_-]+`` form."""
    return "".join(c for c in name if c.isalnum() or c in ("_", "-")).strip()


def _ensure_meta(conn: sqlite3.Connection, name: str) -> None:
    """Ensure a watchlist_meta row exists so empty lists stay visible."""
    conn.execute(
        "INSERT OR IGNORE INTO watchlist_meta (name, created_at) VALUES (?, ?)",
        (name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def get_watchlist(name: str, settings: Settings | None = None) -> list[str]:
    """Return the tickers in a named watchlist, in insertion order."""
    settings = settings or Settings()
    if not _cache_path(settings).exists():
        return []
    with _connect(settings) as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlists WHERE name = ? ORDER BY added_at, rowid",
            (name,),
        ).fetchall()
    return [r[0] for r in rows]


def add_to_watchlist(name: str, ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Add a ticker to a named watchlist. Rejects duplicates."""
    settings = settings or Settings()
    ticker = ticker.strip().upper()
    if not ticker:
        return {"success": False, "error": "Ticker is required"}
    with _connect(settings) as conn:
        _ensure_meta(conn, name)
        try:
            conn.execute(
                "INSERT INTO watchlists (name, ticker, added_at) VALUES (?, ?, ?)",
                (name, ticker, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return {"success": False, "error": f"{ticker} already in {name} watchlist"}
    return {"success": True, "name": name, "ticker": ticker, "watchlist": get_watchlist(name, settings)}


def remove_from_watchlist(name: str, ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Remove a ticker from a named watchlist."""
    settings = settings or Settings()
    ticker = ticker.strip().upper()
    if not ticker:
        return {"success": False, "error": "Ticker is required"}
    with _connect(settings) as conn:
        cur = conn.execute("DELETE FROM watchlists WHERE name = ? AND ticker = ?", (name, ticker))
        conn.commit()
        if cur.rowcount == 0:
            return {"success": False, "error": f"{ticker} not in {name} watchlist"}
    return {"success": True, "name": name, "ticker": ticker, "watchlist": get_watchlist(name, settings)}


def create_watchlist(name: str, settings: Settings | None = None) -> dict[str, Any]:
    """Create a new (possibly empty) named watchlist. Rejects duplicates."""
    settings = settings or Settings()
    safe = _sanitize(name)
    if not safe or safe.startswith("."):
        return {"success": False, "error": "Invalid watchlist name"}
    try:
        with _connect(settings) as conn:
            conn.execute(
                "INSERT INTO watchlist_meta (name, created_at) VALUES (?, ?)",
                (safe, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return {"success": False, "error": f"Watchlist '{safe}' already exists"}
    return {"success": True, "name": safe, "tickers": [], "watchlist": []}


def rename_watchlist(name: str, new_name: str, settings: Settings | None = None) -> dict[str, Any]:
    """Rename a watchlist (both the meta row and its ticker rows)."""
    settings = settings or Settings()
    safe_new = _sanitize(new_name)
    name = name.strip()
    if not safe_new or safe_new.startswith("."):
        return {"success": False, "error": "Invalid watchlist name"}
    if name == safe_new:
        return {"success": False, "error": "New name is the same as the old name"}
    with _connect(settings) as conn:
        exists = conn.execute("SELECT 1 FROM watchlist_meta WHERE name = ?", (safe_new,)).fetchone()
        if exists:
            return {"success": False, "error": f"Watchlist '{safe_new}' already exists"}
        cur_meta = conn.execute(
            "UPDATE watchlist_meta SET name = ? WHERE name = ?", (safe_new, name)
        )
        cur_rows = conn.execute(
            "UPDATE watchlists SET name = ? WHERE name = ?", (safe_new, name)
        )
        conn.commit()
    if cur_meta.rowcount == 0 and cur_rows.rowcount == 0:
        return {"success": False, "error": f"Watchlist '{name}' not found"}
    return {
        "success": True,
        "name": safe_new,
        "old_name": name,
        "watchlist": get_watchlist(safe_new, settings),
    }


def delete_watchlist(name: str, settings: Settings | None = None) -> dict[str, Any]:
    """Delete a watchlist and all of its tickers."""
    settings = settings or Settings()
    name = name.strip()
    with _connect(settings) as conn:
        cur_meta = conn.execute("DELETE FROM watchlist_meta WHERE name = ?", (name,))
        cur_rows = conn.execute("DELETE FROM watchlists WHERE name = ?", (name,))
        conn.commit()
    if cur_meta.rowcount == 0 and cur_rows.rowcount == 0:
        return {"success": False, "error": f"Watchlist '{name}' not found"}
    return {"success": True, "name": name}


def list_watchlists(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return all watchlists with their ticker counts and last-modified time.

    Includes empty lists (backed by ``watchlist_meta``) and legacy lists that
    only have ticker rows.
    """
    settings = settings or Settings()
    if not _cache_path(settings).exists():
        return []
    with _connect(settings) as conn:
        rows = conn.execute(
            """
            SELECT name, MAX(cnt) AS cnt, MAX(modified) AS modified FROM (
                SELECT name, COUNT(*) AS cnt, MAX(added_at) AS modified
                FROM watchlists GROUP BY name
                UNION ALL
                SELECT name, 0 AS cnt, created_at AS modified
                FROM watchlist_meta
            )
            GROUP BY name
            ORDER BY name
            """
        ).fetchall()
    return [
        {"name": name, "tickers": cnt, "modified": modified or ""}
        for name, cnt, modified in rows
    ]


def all_watchlists(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return every watchlist with its full ordered ticker list."""
    settings = settings or Settings()
    if not _cache_path(settings).exists():
        return []
    with _connect(settings) as conn:
        rows = conn.execute(
            "SELECT name, ticker FROM watchlists ORDER BY name, added_at, rowid"
        ).fetchall()
    by_name: dict[str, list[str]] = {}
    for n, t in rows:
        by_name.setdefault(n, []).append(t)

    out: list[dict[str, Any]] = []
    for info in list_watchlists(settings):
        n = info["name"]
        tl = by_name.get(n, [])
        out.append({"name": n, "tickers": tl, "count": len(tl), "modified": info["modified"]})
    return out