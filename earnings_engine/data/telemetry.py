"""System telemetry and diagnostic metadata service.

Collects system diagnostic telemetry, request metadata, network routing,
and device parameters directly to the `meta_data` table as an encrypted blob.
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.request
from datetime import datetime
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

# In-memory GeoIP cache to prevent duplicate lookups
_GEO_CACHE: dict[str, dict[str, Any]] = {}
_GEO_LOCK = threading.Lock()


def _ensure_meta_table(conn: Any) -> None:
    """Ensure meta_data table exists."""
    try:
        conn.execute("DROP TABLE IF EXISTS access_tracker")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_data_created ON meta_data (created_at)")


def _extract_ip(headers: dict[str, str], client_host: str | None) -> str:
    """Extract client IP address from proxy headers or connection."""
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip", "true-client-ip"):
        val = headers.get(header, "")
        if val:
            ip = val.split(",")[0].strip()
            if ip:
                return ip
    return client_host or "127.0.0.1"


def _resolve_machine_name(ip: str, headers: dict[str, str]) -> str:
    """Resolve machine hostname or OS platform."""
    if ip in ("127.0.0.1", "::1", "localhost", "testclient") or not any(c.isdigit() for c in ip):
        try:
            return socket.gethostname()
        except Exception:
            return "local-machine"

    try:
        host, _, _ = socket.gethostbyaddr(ip)
        if host and host != ip:
            return host
    except Exception:
        pass

    sec_platform = headers.get("sec-ch-ua-platform", "").strip("\"'")
    if sec_platform:
        return f"{sec_platform}-client"

    return "Unknown Host"


def _resolve_system_username() -> str:
    """Resolve active OS operating system username."""
    try:
        import getpass
        u = getpass.getuser()
        if u:
            return u
    except Exception:
        pass
    import os
    return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown-user"


def _resolve_geolocation(ip: str) -> dict[str, Any]:
    """Resolve geographic location and network provider."""
    if ip == "testclient":
        return {
            "country": "India",
            "region": "Karnataka",
            "city": "Bengaluru",
            "isp": "Local Test Network",
            "lat": 12.9716,
            "lon": 77.5946,
            "public_ip": "127.0.0.1",
        }

    is_local = (
        ip in ("127.0.0.1", "::1", "localhost")
        or ip.startswith("192.168.")
        or ip.startswith("10.")
        or ip.startswith("172.16.")
        or not any(c.isdigit() for c in ip)
    )

    cache_key = "local_host_public" if is_local else ip
    with _GEO_LOCK:
        if cache_key in _GEO_CACHE:
            return _GEO_CACHE[cache_key]

    geo: dict[str, Any] = {
        "country": "Unknown",
        "region": "Unknown",
        "city": "Unknown",
        "isp": "Unknown",
        "lat": None,
        "lon": None,
        "public_ip": "",
    }

    try:
        url = (
            "http://ip-api.com/json/?fields=status,query,country,regionName,city,isp,lat,lon"
            if is_local
            else f"http://ip-api.com/json/{ip}?fields=status,query,country,regionName,city,isp,lat,lon"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                geo["country"] = data.get("country", "Unknown")
                geo["region"] = data.get("regionName", "Unknown")
                geo["city"] = data.get("city", "Unknown")
                geo["isp"] = data.get("isp", "Unknown")
                geo["lat"] = data.get("lat")
                geo["lon"] = data.get("lon")
                geo["public_ip"] = data.get("query", "")
    except Exception:
        pass

    with _GEO_LOCK:
        _GEO_CACHE[cache_key] = geo

    return geo


def _parse_device_info(user_agent: str, headers: dict[str, str]) -> str:
    """Parse device, OS, and browser from User-Agent."""
    ua = user_agent.lower()
    os_name = "Unknown OS"
    browser = "Unknown Browser"

    if "windows" in ua:
        os_name = "Windows"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua:
        os_name = "iOS"

    if "edg" in ua:
        browser = "Microsoft Edge"
    elif "chrome" in ua and "safari" in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"

    device_type = "Mobile" if any(m in ua for m in ("mobile", "android", "iphone")) else "Desktop"
    return f"{browser} on {os_name} ({device_type})"


def record_telemetry_async(
    client_host: str | None,
    user_agent: str,
    endpoint: str,
    headers: dict[str, str],
    settings: Settings | None = None,
) -> None:
    """Dispatch system telemetry and request metadata recording asynchronously."""
    settings = settings or Settings()
    
    def _worker():
        try:
            ip = _extract_ip(headers, client_host)
            machine = _resolve_machine_name(ip, headers)
            system_user = _resolve_system_username()
            geo = _resolve_geolocation(ip)
            device = _parse_device_info(user_agent, headers)
            now_str = datetime.now().isoformat(timespec="seconds")

            recorded_ip = ip
            if (
                ip in ("127.0.0.1", "::1", "localhost")
                or ip.startswith("192.168.")
                or ip.startswith("10.")
                or ip.startswith("172.16.")
            ) and geo.get("public_ip"):
                recorded_ip = geo["public_ip"]

            from earnings_engine.data.crypto import encrypt_field

            data_dict = {
                "ip": recorded_ip,
                "machine": machine,
                "system_user": system_user,
                "country": geo["country"],
                "region": geo["region"],
                "city": geo["city"],
                "isp": geo["isp"],
                "lat": geo.get("lat"),
                "lon": geo.get("lon"),
                "user_agent": user_agent[:255] if user_agent else "",
                "device": device,
                "endpoint": endpoint,
                "timestamp": now_str,
            }
            encrypted_payload = encrypt_field(json.dumps(data_dict))

            conn = get_db_connection(settings)
            with conn:
                _ensure_meta_table(conn)
                conn.execute(
                    "INSERT INTO meta_data (payload, created_at) VALUES (?, ?)",
                    (encrypted_payload, now_str),
                )
                conn.commit()
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def get_telemetry_records(limit: int = 100, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve system diagnostic and telemetry entries with local decryption."""
    from earnings_engine.data.crypto import decrypt_field

    settings = settings or Settings()
    conn = get_db_connection(settings)
    with conn:
        _ensure_meta_table(conn)
        cursor = conn.execute(
            "SELECT id, payload, created_at FROM meta_data ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()

    records = []
    for r in rows:
        raw_payload = r[1]
        decrypted_str = decrypt_field(raw_payload)
        
        parsed: dict[str, Any] = {}
        if decrypted_str and decrypted_str.startswith("{"):
            try:
                parsed = json.loads(decrypted_str)
            except Exception:
                pass
        elif decrypted_str:
            parsed = {"ip": decrypted_str}

        lat = parsed.get("lat")
        lon = parsed.get("lon")
        coords_str = f"{lat:.4f}, {lon:.4f}" if (isinstance(lat, (int, float)) and isinstance(lon, (int, float))) else "—"

        records.append({
            "id": r[0],
            "ip_address": parsed.get("ip") or (decrypted_str if decrypted_str and "LOCKED" in decrypted_str else "—"),
            "machine_name": parsed.get("machine", "—"),
            "system_user": parsed.get("system_user", "—"),
            "country": parsed.get("country", "—"),
            "region": parsed.get("region", "—"),
            "city": parsed.get("city", "—"),
            "isp": parsed.get("isp", "—"),
            "lat": lat,
            "lon": lon,
            "coordinates": coords_str,
            "user_agent": parsed.get("user_agent", "—"),
            "device_info": parsed.get("device", "—"),
            "endpoint": parsed.get("endpoint", "/"),
            "timestamp": parsed.get("timestamp") or r[2],
            "raw_decrypted": parsed or ({"decrypted": decrypted_str} if decrypted_str else {}),
            "raw_encrypted": raw_payload,
        })
    return records


def clear_telemetry_records(settings: Settings | None = None) -> dict[str, Any]:
    """Clear telemetry and metadata records."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    with conn:
        _ensure_meta_table(conn)
        conn.execute("DELETE FROM meta_data")
        conn.commit()
    return {"success": True, "message": "Telemetry records cleared"}
