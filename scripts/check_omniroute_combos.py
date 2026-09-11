import sqlite3
import json
import uuid
from datetime import datetime

DB_PATH = r"C:\Users\91700\.omniroute\storage.sqlite"

def check_combos():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    rows = cur.execute("SELECT id, name, data, sort_order, created_at, updated_at, system_message, tool_filter_regex, context_cache_protection FROM combos").fetchall()
    for r in rows:
        print(f"ID: {r[0]}, Name: {r[1]}, SortOrder: {r[3]}")
        data = json.loads(r[2])
        print("Data:", json.dumps(data, indent=2))
    con.close()

if __name__ == "__main__":
    check_combos()
