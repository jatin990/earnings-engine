"""Common database, query building, and data normalization utilities.

Designed to eliminate repetitive SQL upsert statements, tuple unpacking,
and redundant symbol normalization across scanners and data engines.
"""

from typing import Any, Sequence


def normalize_nse_ticker(ticker: str) -> str:
    """Ensure standard Indian equity ticker format with .NS suffix.

    If the ticker ends with .BO, keeps it intact. Otherwise strips any
    existing .NS and ensures uppercase .NS ending.
    """
    if not ticker:
        return ""
    t = ticker.strip().upper()
    if t.endswith(".BO"):
        return t
    if t.endswith(".NS"):
        return t
    return f"{t}.NS"


def strip_nse_suffix(ticker: str) -> str:
    """Remove .NS or .BO suffix from ticker symbol."""
    if not ticker:
        return ""
    t = ticker.strip().upper()
    if t.endswith(".NS"):
        return t[:-3]
    if t.endswith(".BO"):
        return t[:-3]
    return t


def get_ticker_variants(ticker: str) -> list[str]:
    """Return deduplicated list of ticker symbol variants (with .NS, without suffix)."""
    if not ticker:
        return []
    base = strip_nse_suffix(ticker)
    nse = normalize_nse_ticker(ticker)
    return list(dict.fromkeys([ticker.strip().upper(), nse, base]))


def build_upsert_sql(
    table_name: str,
    columns: Sequence[str],
    conflict_columns: Sequence[str],
    update_columns: Sequence[str] | None = None,
    custom_update_clauses: dict[str, str] | None = None,
) -> str:
    """Construct a clean, parameterized SQLite ON CONFLICT DO UPDATE upsert statement.

    Args:
        table_name: Name of target SQLite table.
        columns: Sequence of column names to insert.
        conflict_columns: Sequence of column names defining the UNIQUE or PRIMARY KEY conflict target.
        update_columns: Columns to update with excluded.<col>. If None, all columns except conflict_columns.
        custom_update_clauses: Optional dict mapping column name -> custom SQL expression (e.g. CASE statement).
    """
    cols_joined = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    conflict_joined = ", ".join(conflict_columns)

    if update_columns is None:
        conflict_set = set(conflict_columns)
        update_columns = [c for c in columns if c not in conflict_set]

    update_clauses = []
    custom_clauses = custom_update_clauses or {}

    for c in update_columns:
        if c in custom_clauses:
            update_clauses.append(f"{c} = {custom_clauses[c]}")
        else:
            update_clauses.append(f"{c} = excluded.{c}")

    updates_joined = ",\n        ".join(update_clauses)

    return f"""INSERT INTO {table_name} (
        {cols_joined}
    ) VALUES (
        {placeholders}
    )
    ON CONFLICT({conflict_joined}) DO UPDATE SET
        {updates_joined}"""


def row_to_dict(cursor_or_desc: Any, row: Any) -> dict[str, Any]:
    """Convert an SQLite row tuple, sqlite3.Row, or dict-like object to a standard dict."""
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return dict(row)
    if hasattr(row, "get"):
        return dict(row)

    col_names = None
    if hasattr(cursor_or_desc, "description"):
        desc = cursor_or_desc.description
        if desc:
            col_names = [d[0] for d in desc]
    elif isinstance(cursor_or_desc, (list, tuple)):
        col_names = cursor_or_desc

    if col_names and isinstance(row, (tuple, list)):
        return dict(zip(col_names, row))

    return {}
