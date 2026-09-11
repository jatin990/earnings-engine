import sqlite3
import json
import uuid
import urllib.request
from earnings_engine.config import Settings

DB_PATH = r"C:\Users\91700\.omniroute\storage.sqlite"

def add_antigravity_combo():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Check if antigravity already exists
    existing = cur.execute("SELECT id, name, data FROM combos WHERE name = 'antigravity'").fetchone()
    if existing:
        print("Combo 'antigravity' already exists in DB:", existing[0])
    else:
        # Get anitgravity row
        row = cur.execute("SELECT id, name, data, sort_order, created_at, updated_at, system_message, tool_filter_regex, context_cache_protection FROM combos WHERE name = 'anitgravity'").fetchone()
        if not row:
            print("No 'anitgravity' row found!")
            con.close()
            return

        orig_id, orig_name, orig_data_str, sort_order, created_at, updated_at, sys_msg, tool_regex, cache_prot = row
        orig_data = json.loads(orig_data_str)

        new_id = str(uuid.uuid4())
        new_data = json.loads(orig_data_str)
        new_data["id"] = new_id
        new_data["name"] = "antigravity"
        if "models" in new_data:
            for m in new_data["models"]:
                if "id" in m and "anitgravity" in m["id"]:
                    m["id"] = m["id"].replace("anitgravity", "antigravity")

        new_data_str = json.dumps(new_data)

        cur.execute(
            "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at, system_message, tool_filter_regex, context_cache_protection) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id, "antigravity", new_data_str, sort_order + 1, created_at, updated_at, sys_msg, tool_regex, cache_prot)
        )
        con.commit()
        print("Inserted 'antigravity' combo with ID:", new_id)

    con.close()

def test_api():
    s = Settings()
    req = urllib.request.Request(f"{s.omniroute_base_url}/combos", headers={"Authorization": f"Bearer {s.omniroute_api_key}"})
    try:
        with urllib.request.urlopen(req) as resp:
            print("HTTP Status:", resp.status)
            print("Combos API response:", resp.read().decode())
    except Exception as e:
        print("API Error:", e)

if __name__ == "__main__":
    add_antigravity_combo()
    test_api()
