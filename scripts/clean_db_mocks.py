"""Clean test artifact dummy prices and re-sync authoritative live quotes."""
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.prices import fetch_live_quote
from earnings_engine.data.breakout_scanner import run_hot_rescore, run_warm_rescore, run_cold_scan

conn = get_db_connection(Settings())

# 1. Clean corrupt 100.0 dummy rows from tests
cur = conn.execute("DELETE FROM price_history WHERE close = 100.0 AND volume = 0.0 AND date >= '2026-08-01'")
deleted_count = cur.rowcount
if hasattr(conn, 'commit'):
    conn.commit()
print(f"Deleted {deleted_count} corrupt dummy price rows from price_history.")

# 2. Fetch true live quote for SUNPHARMA.NS
real_q = fetch_live_quote("SUNPHARMA.NS", sync_db=True)
print("SUNPHARMA.NS true live quote:", real_q.get("current_price"), real_q.get("previous_close"))

# 3. Clean and rescore breakout radar
conn.execute("DELETE FROM breakout_radar WHERE ticker = 'SUNPHARMA.NS'")
if hasattr(conn, 'commit'):
    conn.commit()

# Rescore
s = Settings()
run_warm_rescore(s)
run_hot_rescore(s)
print("Breakout Radar refreshed successfully.")
