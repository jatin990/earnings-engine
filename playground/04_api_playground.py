"""Playground #4 — FastAPI dashboard endpoint sandbox.

Exercises the dashboard API endpoints that back the bulk Kronos actions
(requires the FastAPI server running via ``python run_api.py``):

- ``POST /api/v1/dashboard/kronos/run`` — run + persist Kronos predictions
- ``GET /api/v1/dashboard/kronos/latest`` — latest prediction per ticker
- ``GET /api/v1/dashboard/kronos/audit``  — full audit trail
- ``POST /api/v1/dashboard/watchlist/kronos`` — bulk watchlist generation
- ``DELETE /api/v1/dashboard/kronos/audit/{ticker}/{run_at}`` — delete a row
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root:  python playground/04_api_playground.py
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playground.playground_utils import C, err, heading, info, ok, warn

DEFAULT_BASE = "http://localhost:8000"


def _get_base() -> str:
    return sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE


def _client():
    try:
        import httpx
        return httpx.Client(base_url=_get_base(), timeout=120.0)
    except ImportError:
        try:
            import requests
            class _ReqClient:
                def __init__(self, base):
                    self.base = base.rstrip("/")
                def post(self, path, **kw):
                    return requests.post(self.base + path, **kw)
                def get(self, path, **kw):
                    return requests.get(self.base + path, **kw)
                def delete(self, path):
                    return requests.delete(self.base + path)
            return _ReqClient(_get_base())
        except ImportError:
            err("Neither httpx nor requests is installed. Run: pip install httpx")
            sys.exit(1)


def run_kronos(symbols: list[str]) -> None:
    subheading("POST /api/v1/dashboard/kronos/run")
    payload = {"tickers": symbols, "lookback": 120, "pred_len": 14}
    resp = client.post("/api/v1/dashboard/kronos/run", json=payload)
    if resp.status_code == 200:
        data = resp.json()
        ok(f"status={resp.status_code} — {len(data)} forecasts persisted to audit")
        for item in data:
            trend = item.get("trend", "?")
            print(f"  {item.get('symbol', '?')}: ₹{item.get('current_price')} → {trend} {item.get('return_pct', 0):+.2f}%")
    else:
        err(f"status={resp.status_code}: {resp.text[:300]}")


def latest(symbols: list[str]) -> None:
    subheading("GET /api/v1/dashboard/kronos/latest")
    query = "&".join(f"tickers={t}" for t in symbols)
    resp = client.get(f"/api/v1/dashboard/kronos/latest?{query}")
    if resp.status_code == 200:
        data = resp.json()
        ok(f"status={resp.status_code} — {len(data)} latest predictions")
        for row in data:
            print(
                f"  {row.get('ticker')} run_at={row.get('run_at')} "
                f"return_pct={row.get('return_pct')} trend={row.get('trend')}"
            )
    else:
        err(f"status={resp.status_code}: {resp.text[:300]}")


def audit(limit: int = 10) -> None:
    subheading("GET /api/v1/dashboard/kronos/audit")
    resp = client.get(f"/api/v1/dashboard/kronos/audit?limit={limit}")
    if resp.status_code == 200:
        data = resp.json()
        ok(f"status={resp.status_code} — {len(data)} audit rows")
        for row in data:
            print(
                f"  {row.get('ticker')} run_at={row.get('run_at')} "
                f"trend={row.get('trend')} return_pct={row.get('return_pct')}"
            )
    else:
        err(f"status={resp.status_code}: {resp.text[:300]}")


def watchlist_batch() -> None:
    subheading("POST /api/v1/dashboard/watchlist/kronos")
    resp = client.post("/api/v1/dashboard/watchlist/kronos", json={})
    if resp.status_code == 200:
        data = resp.json()
        if data.get("success"):
            ok(f"status={resp.status_code} — generated {data.get('generated')} forecasts")
        else:
            warn(f"watchlist generation: {data.get('error')}")
    else:
        err(f"status={resp.status_code}: {resp.text[:300]}")


def delete_example() -> None:
    subheading("DELETE /api/v1/dashboard/kronos/audit/{ticker}/{run_at}")
    # Fetch the most recent audit row and delete it to demonstrate the endpoint.
    resp = client.get("/api/v1/dashboard/kronos/audit?limit=1")
    if resp.status_code != 200 or not resp.json():
        warn("No audit rows to demonstrate deletion.")
        return
    row = resp.json()[0]
    ticker = row["ticker"]
    run_at = row["run_at"].replace(" ", "%20")
    d_resp = client.delete(f"/api/v1/dashboard/kronos/audit/{ticker}/{run_at}")
    if d_resp.status_code == 200:
        ok(f"deleted: {ticker} @ {row['run_at']}")
    else:
        warn(f"delete failed: {d_resp.status_code} {d_resp.text[:200]}")


def main() -> None:
    heading(f"API Playground ({_get_base()})")

    health = client.get("/health")
    ok(f"health: {health.json()}")

    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    run_kronos(symbols)
    latest(symbols)
    audit(limit=10)
    watchlist_batch()
    delete_example()

    heading("Done")


if __name__ == "__main__":
    client = _client()
    main()