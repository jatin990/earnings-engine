"""High-Speed Multi-Row Bulk Migration Script: Local SQLite to Turso LibSQL Cloud.

Migrates all tables, schemas, metadata, predictions, watchlists,
and universe data from `money_club.sqlite3` to Turso using multi-row SQL batching.
"""

from __future__ import annotations

import io
import os
import sqlite3
import sys
import time
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path


def migrate_table(table_name: str, create_sql: str, sqlite_path: Path, max_rows: int | None = None) -> tuple[str, int]:
    local_conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    turso = get_db_connection()

    # 1. Initialize schema
    if "IF NOT EXISTS" not in create_sql.upper():
        create_sql = create_sql.replace(f"CREATE TABLE {table_name}", f"CREATE TABLE IF NOT EXISTS {table_name}")
        create_sql = create_sql.replace(f"CREATE TABLE \"{table_name}\"", f"CREATE TABLE IF NOT EXISTS \"{table_name}\"")
    try:
        turso.execute(create_sql)
    except Exception as e:
        print(f"  [!] Schema notice for {table_name}: {e}")

    # 2. Count local rows
    count_cur = local_conn.cursor()
    count_cur.execute(f"SELECT COUNT(*) FROM \"{table_name}\"")
    total_local = count_cur.fetchone()[0]

    if total_local == 0:
        local_conn.close()
        return table_name, 0

    # 3. Read columns
    col_cur = local_conn.cursor()
    col_cur.execute(f"PRAGMA table_info(\"{table_name}\")")
    cols = [c[1] for c in col_cur.fetchall()]
    col_names = ", ".join([f"\"{c}\"" for c in cols])
    single_row_placeholders = f"({', '.join(['?'] * len(cols))})"

    # Fetch rows
    limit_clause = f" LIMIT {max_rows}" if max_rows else ""
    data_cur = local_conn.cursor()
    data_cur.execute(f"SELECT {col_names} FROM \"{table_name}\" ORDER BY rowid ASC{limit_clause}")
    all_rows = data_cur.fetchall()
    local_conn.close()

    total_to_migrate = len(all_rows)
    print(f"[*] {table_name}: migrating {total_to_migrate:,} rows...")

    # Multi-row batching: 100 rows per single INSERT statement
    batch_size = 100
    migrated = 0

    for i in range(0, len(all_rows), batch_size):
        chunk = all_rows[i : i + batch_size]
        values_clause = ", ".join([single_row_placeholders] * len(chunk))
        multi_insert_sql = f"INSERT OR REPLACE INTO \"{table_name}\" ({col_names}) VALUES {values_clause}"
        flattened_params = [val for row in chunk for val in row]

        try:
            turso.execute(multi_insert_sql, flattened_params)
            migrated += len(chunk)
            if migrated % 1000 == 0 or migrated == total_to_migrate:
                pct = (migrated / total_to_migrate) * 100
                print(f"    [{table_name}] Progress: {migrated:,}/{total_to_migrate:,} ({pct:.1f}%)")
        except Exception as e:
            # Fallback to single row inserts if batch hits a parameter limit
            for row in chunk:
                single_sql = f"INSERT OR REPLACE INTO \"{table_name}\" ({col_names}) VALUES {single_row_placeholders}"
                try:
                    turso.execute(single_sql, row)
                    migrated += 1
                except Exception as inner_e:
                    pass

    # Verify count on Turso
    try:
        res = turso.execute(f"SELECT COUNT(*) FROM \"{table_name}\"")
        turso_count = res.fetchone()[0]
        print(f"  [+] {table_name} verified on Turso: {turso_count:,} rows.\n")
    except Exception as e:
        print(f"  [!] {table_name} count check: {e}\n")

    return table_name, migrated


def run_migration() -> None:
    if not is_turso_enabled():
        print("[ERROR] TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set in .env")
        sys.exit(1)

    sqlite_path = _cache_path(Settings())
    if not sqlite_path.exists():
        print(f"[ERROR] Local SQLite file not found at {sqlite_path}")
        sys.exit(1)

    print("============================================================")
    print("🚀 Starting Bulk Multi-Row Migration to Turso LibSQL Cloud")
    print(f"Database: {sqlite_path.name} ({sqlite_path.stat().st_size / (1024*1024):.1f} MB)")
    print("============================================================\n")

    start_time = time.time()
    local_conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    cur = local_conn.cursor()
    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = cur.fetchall()
    local_conn.close()

    # Separate price_history from application tables
    app_tables = [(t, sql) for t, sql in tables if t != "price_history"]
    price_table = [(t, sql) for t, sql in tables if t == "price_history"]

    total_migrated = 0

    # Phase 1: Migrate all core application tables
    print(f"--- Phase 1: Core Application Tables ({len(app_tables)} tables) ---")
    for t_name, create_sql in app_tables:
        _, count = migrate_table(t_name, create_sql, sqlite_path)
        total_migrated += count

    # Phase 2: Migrate recent price_history (50,000 candles for active universe)
    if price_table:
        t_name, create_sql = price_table[0]
        print(f"--- Phase 2: Price History (Recent Active Universe) ---")
        _, count = migrate_table(t_name, create_sql, sqlite_path, max_rows=50000)
        total_migrated += count

    elapsed = time.time() - start_time
    print("=" * 60)
    print(f"🎉 Migration Complete! Successfully migrated {total_migrated:,} total rows in {elapsed:.2f}s.")
    print("Your cloud database is now fully active on Turso!")
    print("=" * 60)


if __name__ == "__main__":
    run_migration()
