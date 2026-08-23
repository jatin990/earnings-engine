"""Universal Database Connection Layer supporting Turso (LibSQL Cloud) and Local SQLite.

When `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are configured, queries are
executed against the cloud LibSQL database via the lightweight HTTP Pipeline API.
If unset, it seamlessly falls back to standard local SQLite (`money_club.sqlite3`).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import shutil
import threading
from pathlib import Path
from typing import Any, Iterator, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

from earnings_engine.config import Settings, PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("earnings_engine.data.db")

_THREAD_LOCAL = threading.local()
DB_FILENAME = os.getenv("EARNINGS_ENGINE_DB_NAME", "money_club.sqlite3")


def _get_thread_session() -> requests.Session:
    """Return a thread-local requests.Session with Keep-Alive connection pooling."""
    if not hasattr(_THREAD_LOCAL, "session") or _THREAD_LOCAL.session is None:
        s = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=25,
            pool_maxsize=25,
            max_retries=Retry(total=2, backoff_factor=0.1, status_forcelist=[429, 500, 502, 503, 504]),
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _THREAD_LOCAL.session = s
    return _THREAD_LOCAL.session


def _cache_path(settings: Settings) -> Path:
    """Return local SQLite database path with auto-migration from legacy prices.sqlite3."""
    target_path = settings.data_dirs["prices"] / DB_FILENAME
    if not target_path.exists():
        legacy_path = settings.data_dirs["prices"] / "prices.sqlite3"
        if legacy_path.exists() and legacy_path.stat().st_size > 0:
            try:
                shutil.copy2(legacy_path, target_path)
            except Exception:
                return legacy_path
    return target_path





def _serialize_arg(val: Any) -> dict[str, Any]:
    """Serialize Python primitives into Turso pipeline argument JSON."""
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    if isinstance(val, bytes):
        return {"type": "blob", "base64": base64.b64encode(val).decode("ascii")}
    return {"type": "text", "value": str(val)}


def _deserialize_cell(cell: dict[str, Any]) -> Any:
    """Deserialize Turso cell JSON into Python native types."""
    ctype = cell.get("type")
    if ctype == "null" or ctype is None:
        return None
    val = cell.get("value")
    if ctype == "integer":
        try:
            return int(val)
        except (ValueError, TypeError):
            return val
    if ctype == "float":
        try:
            return float(val)
        except (ValueError, TypeError):
            return val
    if ctype == "text":
        return str(val)
    if ctype == "blob":
        b64 = cell.get("base64", "")
        return base64.b64decode(b64)
    return val


class TursoRow(tuple):
    """Row object supporting both index-based and column-name lookups like sqlite3.Row."""

    def __new__(cls, values: Sequence[Any], columns: Sequence[str] | None = None) -> TursoRow:
        obj = super().__new__(cls, values)
        obj._columns = tuple(columns or [])
        obj._col_map = {name: idx for idx, name in enumerate(obj._columns)}
        return obj

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key in self._col_map:
                return super().__getitem__(self._col_map[key])
            raise IndexError(f"No column named '{key}'")
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._col_map:
            return super().__getitem__(self._col_map[key])
        return default

    def keys(self) -> Sequence[str]:
        return self._columns


class TursoCursor:
    """Cursor-like wrapper for Turso HTTP execution results."""

    def __init__(self, rows: list[Any], description: tuple[Any, ...] | None = None, rowcount: int = -1, lastrowid: int | None = None) -> None:
        self._rows = rows
        self._pos = 0
        self.description = description
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self) -> Any | None:
        if self._pos < len(self._rows):
            row = self._rows[self._pos]
            self._pos += 1
            return row
        return None

    def fetchall(self) -> list[Any]:
        remaining = self._rows[self._pos :]
        self._pos = len(self._rows)
        return remaining

    def fetchmany(self, size: int = 1) -> list[Any]:
        end = min(self._pos + size, len(self._rows))
        chunk = self._rows[self._pos : end]
        self._pos = end
        return chunk

    def __iter__(self) -> Iterator[Any]:
        while self._pos < len(self._rows):
            yield self.fetchone()

    def __enter__(self) -> TursoCursor:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class TursoConnection:
    """DB-API compatible connection wrapper over Turso's HTTP Pipeline API."""

    def __init__(self, url: str, token: str) -> None:
        # Standardize URL to https endpoint
        base = url.replace("libsql://", "https://").replace("http://", "https://").rstrip("/")
        if not base.endswith("/v2/pipeline"):
            self.endpoint = f"{base}/v2/pipeline"
        else:
            self.endpoint = base
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.session = _get_thread_session()
        self.row_factory: Any = None

    def execute(self, sql: str, parameters: Sequence[Any] | None = None) -> TursoCursor:
        """Execute a single SQL statement on Turso."""
        args = [_serialize_arg(p) for p in (parameters or [])]
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": args,
                    },
                }
            ]
        }
        resp = self.session.post(self.endpoint, json=payload, headers=self.headers, timeout=30)
        if resp.status_code != 200:
            raise sqlite3.OperationalError(f"Turso HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        if "error" in data:
            raise sqlite3.OperationalError(f"Turso Error: {data['error']}")

        results = data.get("results", [])
        if not results:
            return TursoCursor([])

        res = results[0]
        if res.get("type") == "error":
            err_msg = str(res.get("error", {}).get("message", res))
            if "UNIQUE constraint" in err_msg or "constraint failed" in err_msg.lower():
                raise sqlite3.IntegrityError(err_msg)
            raise sqlite3.OperationalError(f"Turso Query Error: {err_msg}")

        stmt_res = res.get("response", {}).get("result", {})
        cols = stmt_res.get("cols", [])
        col_names = [c.get("name", "") for c in cols]
        raw_rows = stmt_res.get("rows", [])
        rowcount = stmt_res.get("affected_row_count", len(raw_rows))
        lastrowid = stmt_res.get("last_insert_rowid")

        desc = tuple((c.get("name"), None, None, None, None, None, None) for c in cols) if cols else None
        parsed_rows: list[Any] = []
        for r in raw_rows:
            vals = tuple(_deserialize_cell(cell) for cell in r)
            parsed_rows.append(TursoRow(vals, col_names))

        return TursoCursor(parsed_rows, description=desc, rowcount=rowcount, lastrowid=lastrowid)

    def executemany(self, sql: str, seq_of_parameters: Sequence[Sequence[Any]]) -> TursoCursor:
        """Execute parameterized SQL across multiple rows in batched requests."""
        if not seq_of_parameters:
            return TursoCursor([])

        # Batch in chunks of 50 for HTTP efficiency
        batch_size = 50
        total_affected = 0
        for i in range(0, len(seq_of_parameters), batch_size):
            chunk = seq_of_parameters[i : i + batch_size]
            requests_list = [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": [_serialize_arg(p) for p in params],
                    },
                }
                for params in chunk
            ]
            payload = {"requests": requests_list}
            resp = self.session.post(self.endpoint, json=payload, headers=self.headers, timeout=60)
            if resp.status_code != 200:
                raise sqlite3.OperationalError(f"Turso HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            for res in data.get("results", []):
                if res.get("type") == "error":
                    raise sqlite3.OperationalError(f"Turso Executemany Error: {res.get('error', {}).get('message', res)}")
                total_affected += res.get("response", {}).get("result", {}).get("affected_row_count", 0)

        return TursoCursor([], rowcount=total_affected)

    def executescript(self, sql_script: str) -> None:
        """Execute multiple semicolon-separated DDL/DML statements."""
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
        for stmt in statements:
            self.execute(stmt)

    def commit(self) -> None:
        """No-op for HTTP auto-commit pipelines."""
        pass

    def rollback(self) -> None:
        """No-op for HTTP auto-commit pipelines."""
        pass

    def close(self) -> None:
        pass

    def cursor(self) -> TursoConnection:
        return self

    def __enter__(self) -> TursoConnection:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


def is_turso_enabled() -> bool:
    """Check if Turso cloud database credentials are present in the environment."""
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    return bool(url and token)


def get_db_connection(settings: Settings | None = None) -> sqlite3.Connection | TursoConnection:
    """Return a database connection (Turso Cloud if configured, otherwise local SQLite).

    If an isolated test directory is provided in settings, local SQLite is used for test isolation.
    """
    s = settings or Settings()
    default_dir = Settings().data_dirs.get("prices")
    if settings is not None and str(s.data_dirs.get("prices")) != str(default_dir):
        s.ensure_dirs()
        return sqlite3.connect(str(_cache_path(s)))

    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if url and token:
        return TursoConnection(url, token)

    s.ensure_dirs()
    return sqlite3.connect(str(_cache_path(s)))
