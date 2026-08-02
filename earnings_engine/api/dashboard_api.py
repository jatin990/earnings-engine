"""Dashboard data aggregation for the earnings-engine UI.

Provides aggregate data access for the interactive dashboard:
- Results data from the SQLite event_dataset
- Swing setups from market context enrichment
- Kronos predictions from the Kronos predictor
- Watchlist management via NSE universe files
- Refresh status tracking
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data import earnings as earnings_mod
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.market_context import enrich_upcoming_results
from earnings_engine.data.universe import load_all, load_universe, load_universe_from_file
from earnings_engine.data.predictions import (
    delete_prediction,
    load_latest_predictions,
    load_prediction_history,
    store_prediction,
)

UNIVERSES_DIR = Path(__file__).resolve().parent.parent / "data" / "universes"
WATCHLIST_FILE = UNIVERSES_DIR / "my_watchlist.txt"

_REFRESH_STATUS: dict[str, dict[str, Any]] = {}


def _settings() -> Settings:
    return Settings()


def _load_list(file: Path) -> list[str]:
    try:
        return load_universe_from_file(file)
    except Exception:
        return []


def _resolve_tickers(market: str | None) -> list[str]:
    """Resolve the ticker list for a given universe selector.

    Matches the CLI ``upcoming-results`` semantics:
    - ``None`` / ``"ALL"``  -> ``load_all()`` (IN + US, same as CLI default)
    - ``"WATCHLIST"``       -> the server-side watchlist file
    - ``"IN"``/``"US"``/``"NSE_ALL"``/``"NSE_LARGE_CAP"`` -> ``load_universe(market)``
    - anything else         -> treated as a universe file name (so user-created
      watchlists are usable directly)
    """
    if market:
        mu = market.upper()
        if mu == "WATCHLIST":
            return _load_list(WATCHLIST_FILE)
        if mu == "ALL":
            return load_all()
        if mu in {"IN", "US", "NSE_ALL", "NSE_LARGE_CAP"}:
            return load_universe(mu)
        f = UNIVERSES_DIR / f"{mu}.txt"
        if f.exists():
            return _load_list(f)
        return []
    return load_all()


def _write_list(file: Path, items: list[str]) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "w", encoding="utf-8") as f:
        f.write(f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for item in sorted(items):
            f.write(f"{item}\n")


# ---------------------------------------------------------------------------
# Refresh status
# ---------------------------------------------------------------------------

def mark_refreshed(source: str, rows: int = 0, status: str = "ok", message: str = "") -> None:
    _REFRESH_STATUS[source] = {
        "last_refresh": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rows": rows,
        "status": status,
        "message": message,
    }


def get_refresh_status() -> dict[str, Any]:
    return {k: dict(v) for k, v in _REFRESH_STATUS.items()}


# ---------------------------------------------------------------------------
# Results tab
# ---------------------------------------------------------------------------

def get_upcoming_results(days: int = 14, market: str | None = None) -> list[dict[str, Any]]:
    """Get upcoming earnings results with market context enrichment.

    ``market`` follows the same semantics as the ``upcoming-results`` CLI:
    None/"ALL" -> IN+US (load_all), "WATCHLIST" -> watchlist file, an
    "IN"/"US"/"NSE_ALL"/"NSE_LARGE_CAP" code, or a user-created universe name.
    """
    settings = _settings()
    tickers = _resolve_tickers(market)
    if not tickers:
        return []

    df = earnings_mod.upcoming_earnings(tickers, settings, days=days)
    if df.empty:
        return []

    enriched = enrich_upcoming_results(df)
    mark_refreshed("results", rows=len(enriched))

    # Merge latest Kronos predictions for the same tickers
    try:
        latest_kronos = {row["ticker"]: row for row in get_kronos_latest_predictions(tickers=[str(t) for t in enriched["ticker"].dropna().unique()])}
    except Exception:
        latest_kronos = {}

    results = []
    for _, row in enriched.iterrows():
        item: dict[str, Any] = {}
        for col in enriched.columns:
            val = row[col]
            if pd.isna(val):
                item[col] = None
            elif isinstance(val, pd.Timestamp):
                item[col] = val.strftime("%Y-%m-%d")
            elif hasattr(val, "item"):
                item[col] = val.item()
            else:
                item[col] = val
        ticker_str = str(row.get("ticker", ""))
        kp = latest_kronos.get(ticker_str)
        if kp:
            pred = kp.get("prediction", kp)
            item["kronos_prediction"] = {
                "return_pct": pred.get("return_pct"),
                "support": pred.get("support"),
                "resistance": pred.get("resistance"),
                "trend": pred.get("trend"),
                "confidence": pred.get("confidence"),
                "run_at": kp.get("run_at"),
            }
        else:
            item["kronos_prediction"] = None
        results.append(item)
    return results


def get_event_dataset_summary() -> dict[str, Any]:
    """Get summary stats from SQLite event_dataset table."""
    db = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "prices" / "prices.sqlite3"
    if not db.exists():
        return {"available": False, "rows": 0}

    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker), AVG(label) FROM event_dataset")
        rows, tickers, up_rate = cur.fetchone()
        cur.execute("SELECT MIN(earnings_date), MAX(earnings_date) FROM event_dataset")
        min_d, max_d = cur.fetchone()
        conn.close()
        return {
            "available": True,
            "rows": rows,
            "tickers": tickers,
            "up_label_rate": round(float(up_rate), 4) if up_rate is not None else None,
            "date_range": {"min": min_d, "max": max_d},
        }
    except sqlite3.Error:
        return {"available": False, "rows": 0}


# ---------------------------------------------------------------------------
# Swing tab
# ---------------------------------------------------------------------------

def get_swing_setups(market: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Get swing setups with support/resistance and momentum data."""
    settings = _settings()
    tickers = _resolve_tickers(market)

    results = []
    for ticker in tickers[:limit]:
        try:
            enriched = enrich_upcoming_results(pd.DataFrame({"ticker": [ticker]}), settings)
            if enriched.empty:
                continue
            row = enriched.iloc[0].to_dict()
            item: dict[str, Any] = {}
            for col, val in row.items():
                if pd.isna(val):
                    item[col] = None
                elif isinstance(val, pd.Timestamp):
                    item[col] = val.strftime("%Y-%m-%d")
                elif hasattr(val, "item"):
                    item[col] = val.item()
                else:
                    item[col] = val

            momentum = item.get("thirty_day_return_pct") or 0
            support = item.get("current_support")
            resistance = item.get("next_resistance")
            if momentum > 3 and support and resistance:
                item["swing_signal"] = "Strong Buy"
            elif momentum > 0 and support and resistance:
                item["swing_signal"] = "Buy"
            elif momentum < -3:
                item["swing_signal"] = "Cautious"
            else:
                item["swing_signal"] = "Neutral"
            results.append(item)
        except Exception:
            continue

    mark_refreshed("swing", rows=len(results))
    return results


# ---------------------------------------------------------------------------
# Kronos tab
# ---------------------------------------------------------------------------

def get_kronos_predictions(
    tickers: list[str] | None = None,
    lookback: int = 120,
    pred_len: int = 14,
    progress_callback: callable | None = None,
) -> list[dict[str, Any]]:
    from earnings_engine.kronos_predictor import predict_portfolio

    if not tickers:
        tickers = _load_list(WATCHLIST_FILE) or load_universe("IN")[:10]
    if not tickers:
        return []

    forecasts = predict_portfolio(tickers, lookback=lookback, pred_len=pred_len, progress_callback=progress_callback)
    mark_refreshed("kronos", rows=len(forecasts))

    # Persist every forecast as an immutable audit row so the dashboard can
    # show historical predictions and track accuracy over time.
    settings = _settings()
    for fc in forecasts:
        payload = dict(fc)
        payload["lookback"] = lookback
        payload["pred_len"] = pred_len
        store_prediction(fc.get("symbol", fc.get("ticker", "")), settings, payload)
    return forecasts


def get_kronos_predictions_audit(
    tickers: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the full audit history of Kronos predictions (optionally filtered by ticker)."""
    settings = _settings()
    return load_prediction_history(tickers=tickers, limit=limit, settings=settings)


def get_kronos_latest_predictions(
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the most-recent Kronos prediction per ticker."""
    settings = _settings()
    return load_latest_predictions(tickers=tickers, settings=settings)


def get_kronos_predictions_for_ticker(ticker: str) -> list[dict[str, Any]]:
    """Return all historical predictions for a specific ticker."""
    settings = _settings()
    return load_prediction_history(tickers=[ticker], settings=settings)


def create_universe_file(name: str, tickers: list[str] | None = None) -> dict[str, Any]:
    """Create a new watchlist/universe file under the universes directory.

    The file is created even when ``tickers`` is empty so the user can populate
    it later via the existing add/remove endpoints.  Names are sanitized to a
    safe ``[A-Za-z0-9_-]+`` form and ``.txt`` appended automatically.
    """
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-")).strip()
    if not safe_name or safe_name.startswith("."):
        return {"success": False, "error": "Invalid universe name"}

    file_path = UNIVERSES_DIR / f"{safe_name}.txt"
    if file_path.exists():
        return {"success": False, "error": f"Universe '{safe_name}' already exists"}

    items = [t.strip().upper() for t in (tickers or []) if t and t.strip()]
    _write_list(file_path, items)
    return {
        "success": True,
        "name": safe_name,
        "file": file_path.name,
        "tickers": len(items),
        "path": str(file_path),
    }


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

def get_watchlist() -> list[str]:
    return _load_list(WATCHLIST_FILE)


def add_to_watchlist(ticker: str) -> dict[str, Any]:
    ticker = ticker.strip().upper()
    if not ticker:
        return {"success": False, "error": "Ticker is required"}
    current = get_watchlist()
    if ticker in current:
        return {"success": False, "error": f"{ticker} already in watchlist"}
    current.append(ticker)
    _write_list(WATCHLIST_FILE, current)
    mark_refreshed("watchlist", rows=len(current))
    return {"success": True, "ticker": ticker, "watchlist": current}


def remove_from_watchlist(ticker: str) -> dict[str, Any]:
    ticker = ticker.strip().upper()
    if not ticker:
        return {"success": False, "error": "Ticker is required"}
    current = get_watchlist()
    if ticker not in current:
        return {"success": False, "error": f"{ticker} not in watchlist"}
    current = [t for t in current if t != ticker]
    _write_list(WATCHLIST_FILE, current)
    mark_refreshed("watchlist", rows=len(current))
    return {"success": True, "ticker": ticker, "watchlist": current}


# ---------------------------------------------------------------------------
# Universe browser
# ---------------------------------------------------------------------------

def get_universe_files() -> list[dict[str, Any]]:
    files = []
    for f in sorted(UNIVERSES_DIR.glob("*.txt")):
        stat = f.stat()
        items = _load_list(f)
        files.append({
            "name": f.stem,
            "path": str(f),
            "tickers": len(items),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return files


# ---------------------------------------------------------------------------
# Refresh / Ingest
# ---------------------------------------------------------------------------

def get_tab_refresh_status() -> dict[str, Any]:
    """Return per-tab last-refresh metadata."""
    return {
        "results": _REFRESH_STATUS.get("results", {}),
        "swing": _REFRESH_STATUS.get("swing", {}),
        "kronos": _REFRESH_STATUS.get("kronos", {}),
        "watchlist": _REFRESH_STATUS.get("watchlist", {}),
    }


def summarize_results_with_llm(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a short LLM summary for the provided results rows.

    Uses the local Ollama endpoint configured in the environment.
    """
    try:
        import requests as req
        import os
    except Exception as e:
        return {"success": False, "error": f"requests not available: {str(e)}"}

    base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    generate_url = base_url.rstrip("/") + "/api/generate"

    # Build a compact prompt
    top = items[:8]
    lines = []
    for r in top:
        ticker = r.get("ticker", "?")
        price = r.get("current_price")
        r30 = r.get("thirty_day_return_pct")
        r7 = r.get("seven_day_return_pct")
        score = r.get("prev_3q_earnings_score")
        kp = r.get("kronos_prediction") or {}
        trend = kp.get("trend") or "N/A"
        line = (
            f"{ticker}: price={price}, 30D={None if r30 is None else f'{r30:.2f}%'}, "
            f"7D={None if r7 is None else f'{r7:.2f}%'}, quality={score}, kronos_trend={trend}"
        )
        lines.append(line)
    prompt = (
        "You are a concise financial markets assistant. "
        "Given the following upcoming earnings results with market metrics, "
        "produce 3-5 bullet points summarizing actionable insights. "
        "Focus on momentum shifts, quality, and consistency. Be brief.\n\n" + "\n".join(lines)
    )

    try:
        resp = req.post(generate_url, json={"model": model, "prompt": prompt, "stream": False}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        return {"success": True, "summary": text, "model": model}
    except Exception as e:
        return {"success": False, "error": str(e)}


def refresh_data(market: str | None = None, tickers: list[str] | None = None, force: bool = True) -> dict[str, Any]:
    settings = _settings()
    results: dict[str, Any] = {}

    ticker_list = tickers or _resolve_tickers(market)
    if not ticker_list:
        return {"success": False, "error": "No tickers to refresh"}

    for name, func in [
        ("prices", lambda: prices_mod.ingest_prices(ticker_list, settings, force=force)),
        ("earnings", lambda: earnings_mod.ingest_earnings(ticker_list, settings, force=force)),
    ]:
        try:
            res = func()
            ok = sum(1 for n in res.values() if n > 0)
            mark_refreshed(name, rows=ok, message=f"{ok}/{len(ticker_list)}")
            results[name] = {"ok": ok, "total": len(ticker_list)}
        except Exception as e:
            mark_refreshed(name, status="error", message=str(e))
            results[name] = {"error": str(e)}

    try:
        from earnings_engine.data.universe import ingest_market_caps
        mc = ingest_market_caps(ticker_list, force=force)
        ok = sum(1 for v in mc.values() if v > 0)
        mark_refreshed("market_caps", rows=ok, message=f"{ok}/{len(ticker_list)}")
        results["market_caps"] = {"ok": ok, "total": len(ticker_list)}
    except Exception as e:
        mark_refreshed("market_caps", status="error", message=str(e))
        results["market_caps"] = {"error": str(e)}

    return {"success": True, "results": results}


def generate_watchlist_kronos(
    tickers: list[str] | None = None,
    lookback: int = 120,
    pred_len: int = 14,
) -> dict[str, Any]:
    """Generate Kronos predictions for watchlist tickers.

    If ``tickers`` is None, falls back to the server-side watchlist file.
    Returns a dict with ``success`` and a list of generated forecasts.
    """
    try:
        from earnings_engine.kronos_predictor import predict_portfolio
    except Exception as e:
        return {"success": False, "error": f"Kronos predictor unavailable: {str(e)}"}

    # Only use watchlist or explicit tickers - do NOT fall back to IN universe
    # None means "use watchlist", [] means "no tickers"
    if tickers is None:
        target_tickers = _load_list(WATCHLIST_FILE)
    else:
        target_tickers = tickers
    
    if not target_tickers:
        return {"success": False, "error": "No tickers provided and watchlist is empty"}

    settings = _settings()
    try:
        forecasts = predict_portfolio(target_tickers, lookback=lookback, pred_len=pred_len)
    except Exception as e:
        return {"success": False, "error": f"Prediction failed: {str(e)}"}

    mark_refreshed("kronos", rows=len(forecasts))

    # Persist each forecast to the audit trail.
    for fc in forecasts:
        payload = dict(fc)
        payload["lookback"] = lookback
        payload["pred_len"] = pred_len
        store_prediction(fc.get("symbol", fc.get("ticker", "")), settings, payload)

    return {"success": True, "generated": len(forecasts), "forecasts": forecasts}


def delete_kronos_prediction(ticker: str, run_at: str) -> dict[str, Any]:
    """Delete a specific Kronos prediction from the audit trail.
    
    Parameters
    ----------
    ticker:
        The stock ticker.
    run_at:
        The ISO timestamp of the prediction run to delete.
    
    Returns
    -------
    dict
        Success status and message.
    """
    settings = _settings()
    try:
        deleted = delete_prediction(ticker, run_at, settings)
        if deleted:
            return {"success": True, "message": f"Deleted prediction for {ticker} at {run_at}"}
        else:
            return {"success": False, "error": f"No prediction found for {ticker} at {run_at}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
