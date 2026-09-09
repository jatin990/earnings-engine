"""NSE India official API client — financial calendar & result dates.

NSE India exposes JSON APIs under ``https://www.nseindia.com/api/`` that require
a browser-like session (cookies set on the homepage + headers).  This module
provides:

- ``fetch_result_calendar(from_date, to_date)`` — raw result-calendar payload
  (companies + their result dates).
- ``fetch_event_calendar(from_date, to_date)`` — raw event-calendar payload
  (board meetings, results, dividends, etc.).
- ``get_financial_calendar(symbol, from_date, to_date)`` — normalized result
  dates for one symbol (raw payload kept separate).

All calls are wrapped in try/except and return ``{"error": ...}`` on failure so
the dashboard can surface a friendly message instead of crashing.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

import requests

logger = logging.getLogger("earnings_engine.data.nse_api")

NSE_BASE = "https://www.nseindia.com"
NSE_RESULT_CALENDAR = NSE_BASE + "/api/result-calendar"
NSE_EVENT_CALENDAR = NSE_BASE + "/api/event-calendar"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_BASE + "/",
}

_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return a shared session, priming NSE cookies on first use."""
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(_HEADERS)
        try:
            # NSE sets cookies on the homepage; hitting it first avoids 401s.
            s.get(NSE_BASE + "/", timeout=10)
        except Exception as e:
            logger.warning("nse_api: homepage cookie priming failed: %s", e)
        _session = s
    return _session


def _fmt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _default_range(days: int = 30) -> tuple[date, date]:
    today = date.today()
    return today, today + timedelta(days=days)


def fetch_result_calendar(
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    """Fetch the raw NSE result-calendar payload for a date range.

    Returns the raw JSON dict, or ``{"error": ...}`` on failure.
    """
    f, t = _default_range() if from_date is None else (from_date, to_date)
    url_params = {"from": _fmt(f), "to": _fmt(t), "index": "equities"}
    logger.info("[NSE:REQ] GET %s (from=%s, to=%s)", NSE_RESULT_CALENDAR, _fmt(f), _fmt(t))
    t0 = time.perf_counter()
    try:
        resp = _get_session().get(
            NSE_RESULT_CALENDAR,
            params=url_params,
            timeout=15,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        try:
            from earnings_engine.rate_limits import record_request
            record_request("nse", status_code=resp.status_code)
        except Exception:
            pass
        resp.raise_for_status()
        data = resp.json()
        item_count = len(data) if isinstance(data, list) else len(data.get("data", data.get("result", [])))
        logger.info("[NSE:RESP] Result calendar -> %d items (%.1fms, HTTP %d)", item_count, elapsed_ms, resp.status_code)
        return data
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning("[NSE:RESP] Result calendar request failed after %.1fms: %s", elapsed_ms, e)
        return {"error": str(e)}


def fetch_event_calendar(
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    """Fetch the raw NSE event-calendar payload for a date range.

    Returns the raw JSON dict, or ``{"error": ...}`` on failure.
    """
    f, t = _default_range() if from_date is None else (from_date, to_date)
    url_params = {"from": _fmt(f), "to": _fmt(t), "index": "equities"}
    logger.info("[NSE:REQ] GET %s (from=%s, to=%s)", NSE_EVENT_CALENDAR, _fmt(f), _fmt(t))
    t0 = time.perf_counter()
    try:
        resp = _get_session().get(
            NSE_EVENT_CALENDAR,
            params=url_params,
            timeout=15,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        try:
            from earnings_engine.rate_limits import record_request
            record_request("nse", status_code=resp.status_code)
        except Exception:
            pass
        resp.raise_for_status()
        data = resp.json()
        item_count = len(data) if isinstance(data, list) else len(data.get("data", data.get("result", [])))
        logger.info("[NSE:RESP] Event calendar -> %d items (%.1fms, HTTP %d)", item_count, elapsed_ms, resp.status_code)
        return data
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning("[NSE:RESP] Event calendar request failed after %.1fms: %s", elapsed_ms, e)
        return {"error": str(e)}


def get_financial_calendar(
    symbol: str,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    """Return normalized result dates for one symbol from the NSE result calendar.

    Returns ``{"symbol", "result_dates": [...], "raw": {...}}``.  On failure
    returns ``{"symbol", "error": "..."}``.  The raw payload is kept separate
    from the normalized ``result_dates`` list.
    """
    raw = fetch_result_calendar(from_date, to_date)
    if "error" in raw:
        return {"symbol": symbol, "error": raw["error"]}

    # The result-calendar payload is typically a list of {symbol, companyName,
    # ...} entries, each with a result date field.  Normalize defensively.
    result_dates: list[dict[str, Any]] = []
    entries = raw if isinstance(raw, list) else raw.get("data", raw.get("result", []))
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sym = str(entry.get("symbol", "")).upper()
            if sym and (sym == symbol.upper() or sym == symbol.upper().replace(".NS", "")):
                result_dates.append({
                    "symbol": sym,
                    "company": entry.get("companyName") or entry.get("company") or sym,
                    "result_date": entry.get("resultDate") or entry.get("date") or entry.get("bmDate"),
                })

    return {
        "symbol": symbol,
        "result_dates": result_dates,
        "raw": raw,
    }