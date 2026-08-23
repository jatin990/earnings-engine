import time
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.telemetry import (
    clear_telemetry_records,
    get_telemetry_records,
    record_telemetry_async,
)


def test_telemetry_direct_recording(temp_settings: Settings):
    # Record telemetry asynchronously
    record_telemetry_async(
        client_host="127.0.0.1",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        endpoint="/dashboard",
        headers={"sec-ch-ua-platform": '"Windows"'},
        settings=temp_settings,
    )
    # Wait for background thread
    records = []
    for _ in range(15):
        records = get_telemetry_records(limit=10, settings=temp_settings)
        if records:
            break
        time.sleep(0.1)

    assert len(records) >= 1
    rec = records[0]
    assert "localhost" in rec["ip_address"] or "127.0.0.1" in rec["ip_address"] or any(c.isdigit() for c in rec["ip_address"])
    assert "Windows" in rec["device_info"] or "Chrome" in rec["device_info"]
    assert rec["endpoint"] == "/dashboard"
    assert rec["country"] != "Unknown"

    # Clear records
    res = clear_telemetry_records(settings=temp_settings)
    assert res["success"] is True
    assert len(get_telemetry_records(limit=10, settings=temp_settings)) == 0


def test_telemetry_api_endpoints(temp_settings: Settings, monkeypatch):
    monkeypatch.setattr("earnings_engine.api.server._settings", temp_settings)
    client = TestClient(app)

    # Trigger dashboard request with passcode header to invoke middleware telemetry
    res = client.get("/dashboard", headers={"X-Passcode": "NEXUS-MASTER"})
    assert res.status_code == 200

    data = {}
    for _ in range(20):
        api_res = client.get("/api/v1/system/telemetry", headers={"X-Passcode": "NEXUS-MASTER"})
        if api_res.status_code == 200:
            data = api_res.json()
            if data.get("total", 0) >= 1:
                break
        time.sleep(0.1)

    assert data.get("has_key") is True
    assert "records" in data
    assert data["total"] >= 1

    # Clear via API
    del_res = client.delete("/api/v1/system/telemetry", headers={"X-Passcode": "NEXUS-MASTER"})
    assert del_res.status_code == 200

    api_res2 = client.get("/api/v1/system/telemetry", headers={"X-Passcode": "NEXUS-MASTER"})
    assert api_res2.json()["total"] == 0

    # Without private key, API returns has_key: False and records: []
    import earnings_engine.data.crypto as crypto_mod
    from pathlib import Path
    monkeypatch.setattr(crypto_mod, "_CACHED_PRIV_KEY", None)
    monkeypatch.setattr(crypto_mod, "_PRIVATE_KEY_FILE", Path("non_existent_key.pem"))

    locked_res = client.get("/api/v1/system/telemetry", headers={"X-Passcode": "NEXUS-MASTER"})
    assert locked_res.status_code == 200
    locked_data = locked_res.json()
    assert locked_data.get("has_key") is False
    assert locked_data["total"] == 0
    assert locked_data["records"] == []


def test_telemetry_encrypted_in_db(temp_settings: Settings):
    from earnings_engine.data.db import get_db_connection

    # Record telemetry asynchronously
    record_telemetry_async(
        client_host="127.0.0.1",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        endpoint="/dashboard",
        headers={},
        settings=temp_settings,
    )
    time.sleep(0.3)

    # Inspect raw database columns directly
    conn = get_db_connection(temp_settings)
    with conn:
        row = conn.execute("SELECT id, payload, created_at FROM meta_data ORDER BY id DESC LIMIT 1").fetchone()
        assert row is not None
        # Must be single encrypted ciphertext payload in innocuous meta_data table
        assert str(row[1]).startswith("enc::")
        # Ensure plaintext fields are not leaked in column values
        assert "127.0.0.1" not in str(row[1])
        assert "Mozilla" not in str(row[1])


def test_telemetry_undecryptable_without_private_key(temp_settings: Settings, monkeypatch):
    import earnings_engine.data.crypto as crypto_mod
    from pathlib import Path

    # Clear cached keys
    monkeypatch.setattr(crypto_mod, "_CACHED_PRIV_KEY", None)
    monkeypatch.setattr(crypto_mod, "_PRIVATE_KEY_FILE", Path("non_existent_key.pem"))

    # Encrypt a test dictionary using the public key
    test_dict = {"ip": "203.0.113.195", "country": "TestCountry", "machine": "SecretLaptop"}
    encrypted = crypto_mod.encrypt_field(str(test_dict))
    assert encrypted.startswith("enc::")

    # Without private key, decrypt_field should gracefully fail to decrypt
    decrypted = crypto_mod.decrypt_field(encrypted)
    assert "[ENCRYPTED: LOCKED WITH LOCAL KEY]" in decrypted
    assert "SecretLaptop" not in decrypted


def test_grouped_telemetry_records(temp_settings: Settings):
    from earnings_engine.data.telemetry import get_grouped_telemetry_records

    # Clear old records
    clear_telemetry_records(settings=temp_settings)

    # Record 3 events from same machine + IP combo
    for ep in ["/dashboard", "/api/v1/overview", "/dashboard"]:
        record_telemetry_async(
            client_host="192.168.1.100",
            user_agent="Mozilla/5.0 Chrome/120.0.0.0",
            endpoint=ep,
            headers={},
            settings=temp_settings,
        )

    grouped = []
    for _ in range(25):
        grouped = get_grouped_telemetry_records(limit=10, settings=temp_settings)
        if grouped and grouped[0]["count"] >= 3:
            break
        time.sleep(0.1)

    assert len(grouped) == 1
    assert grouped[0]["count"] == 3
    assert any(c.isdigit() for c in grouped[0]["ip_address"])
    assert "/dashboard" in grouped[0]["endpoints"]
    assert grouped[0]["endpoints"]["/dashboard"] == 2
    assert grouped[0]["endpoints"]["/api/v1/overview"] == 1

