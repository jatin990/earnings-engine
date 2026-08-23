"""Playground API — raw API console catalog + search for the dashboard Playground tab.

This module powers a Postman-style API console inside the dashboard:
- ``get_endpoint_catalog()`` — the list of real API endpoints grouped by source
  (Market Data / NSE / yfinance / Kronos).  The console calls these endpoints
  directly and shows the raw JSON response.
- ``search_symbols(q)`` — autocomplete across the NSE_ALL + US universes.

The existing raw endpoints (market-cap, market-context, price-history,
earnings-history, universe, playground/ticker, dashboard/kronos/*) are NOT
modified — the console just calls them same-origin.
"""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.config import market_of

logger = logging.getLogger("earnings_engine.api.playground_api")


# ---------------------------------------------------------------------------
# Endpoint catalog (drives the API console dropdown)
# ---------------------------------------------------------------------------

def get_endpoint_catalog() -> list[dict[str, Any]]:
    """Return the catalog of raw API endpoints grouped by source.

    Each entry: {id, group, method, path, params, description}.
    ``path`` uses ``{ticker}`` / ``{market}`` placeholders that the console
    fills from the selected symbol / params.
    """
    return [
        # --- Market Data ---
        {
            "id": "market_cap",
            "group": "Market Data",
            "method": "GET",
            "path": "/api/v1/market-cap/{ticker}",
            "params": [],
            "description": "Raw market cap for a ticker (cache-first, yfinance fallback).",
        },
        {
            "id": "market_context",
            "group": "Market Data",
            "method": "GET",
            "path": "/api/v1/market-context/{ticker}",
            "params": [],
            "description": "Enriched market context: price, 52w, 30D, earnings scores, support/resistance.",
        },
        {
            "id": "price_history",
            "group": "Market Data",
            "method": "GET",
            "path": "/api/v1/price-history/{ticker}",
            "params": [
                {"name": "start_date", "type": "date", "optional": True},
                {"name": "end_date", "type": "date", "optional": True},
                {"name": "force_refresh", "type": "bool", "optional": True},
            ],
            "description": "Raw OHLCV price history from the SQLite cache.",
        },
        {
            "id": "earnings_history",
            "group": "Market Data",
            "method": "GET",
            "path": "/api/v1/earnings-history/{ticker}",
            "params": [
                {"name": "force_refresh", "type": "bool", "optional": True},
            ],
            "description": "Raw earnings history (dates, EPS estimate/reported, surprise %).",
        },
        # --- NSE ---
        {
            "id": "universe",
            "group": "NSE",
            "method": "GET",
            "path": "/api/v1/universe/{market}",
            "params": [
                {"name": "market", "type": "select", "options": ["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], "optional": False},
            ],
            "description": "Raw ticker universe for a market (IN, US, NSE_ALL, NSE_LARGE_CAP).",
        },
        {
            "id": "universe_files",
            "group": "NSE",
            "method": "GET",
            "path": "/api/v1/universe/files",
            "params": [],
            "description": "List available universe files.",
        },
        {
            "id": "market_caps",
            "group": "NSE",
            "method": "GET",
            "path": "/api/v1/market-caps",
            "params": [],
            "description": "All cached market caps as {ticker: market_cap}.",
        },
        {
            "id": "nse_universe_info",
            "group": "NSE",
            "method": "GET",
            "path": "/api/v1/playground/nse",
            "params": [
                {"name": "force_refresh", "type": "bool", "optional": True},
            ],
            "description": "NSE universe sizes + samples (nse_all, nse_large_cap, IN, US, combined).",
        },
        {
            "id": "nse_result_calendar",
            "group": "NSE",
            "method": "GET",
            "path": "/api/v1/playground/nse/result-calendar",
            "params": [
                {"name": "from_date", "type": "date", "optional": True},
                {"name": "to_date", "type": "date", "optional": True},
            ],
            "description": "Raw NSE result-calendar payload (companies + result dates) from nseindia.com.",
        },
        {
            "id": "nse_event_calendar",
            "group": "NSE",
            "method": "GET",
            "path": "/api/v1/playground/nse/event-calendar",
            "params": [
                {"name": "from_date", "type": "date", "optional": True},
                {"name": "to_date", "type": "date", "optional": True},
            ],
            "description": "Raw NSE event-calendar payload (board meetings, results, dividends) from nseindia.com.",
        },
        {
            "id": "nse_financial_calendar",
            "group": "NSE",
            "method": "GET",
            "path": "/api/v1/playground/nse/financial-calendar/{symbol}",
            "params": [
                {"name": "from_date", "type": "date", "optional": True},
                {"name": "to_date", "type": "date", "optional": True},
            ],
            "description": "Normalized NSE result dates for the selected symbol (raw payload kept separate).",
        },
        # --- yfinance ---
        {
            "id": "yf_overview",
            "group": "yfinance",
            "method": "GET",
            "path": "/api/v1/playground/ticker/{ticker}",
            "params": [],
            "description": "Raw yfinance snapshot: fast_info/.info, price, market cap, earnings dates.",
        },
        {
            "id": "yf_history",
            "group": "yfinance",
            "method": "GET",
            "path": "/api/v1/playground/ticker/{ticker}/history",
            "params": [
                {"name": "period", "type": "select", "options": ["1mo", "3mo", "6mo", "1y", "5y"], "optional": True},
                {"name": "interval", "type": "select", "options": ["1d", "1wk", "1mo"], "optional": True},
            ],
            "description": "Raw yfinance OHLCV history (live, capped at 120 rows).",
        },
        # --- Kronos ---
        {
            "id": "kronos_run",
            "group": "Kronos",
            "method": "POST",
            "path": "/api/v1/dashboard/kronos/run",
            "params": [
                {"name": "tickers", "type": "text", "optional": True},
                {"name": "lookback", "type": "number", "optional": True},
                {"name": "pred_len", "type": "number", "optional": True},
            ],
            "description": "Run Kronos predictions — raw forecast payload (forecast_series, gbm_prediction, projected_close).",
        },
        {
            "id": "kronos_latest",
            "group": "Kronos",
            "method": "GET",
            "path": "/api/v1/dashboard/kronos/latest",
            "params": [
                {"name": "tickers", "type": "text", "optional": True},
            ],
            "description": "Latest Kronos prediction per ticker (raw audit rows).",
        },
        {
            "id": "kronos_audit",
            "group": "Kronos",
            "method": "GET",
            "path": "/api/v1/dashboard/kronos/audit",
            "params": [
                {"name": "tickers", "type": "text", "optional": True},
                {"name": "limit", "type": "number", "optional": True},
            ],
            "description": "Full Kronos prediction audit trail (raw rows).",
        },
        {
            "id": "kronos_history",
            "group": "Kronos",
            "method": "GET",
            "path": "/api/v1/dashboard/kronos/history/{ticker}",
            "params": [],
            "description": "All historical Kronos predictions for one ticker (raw rows).",
        },
    ]


# ---------------------------------------------------------------------------
# Symbol search (autocomplete)
# ---------------------------------------------------------------------------

_SEARCH_UNIVERSE_CACHE: tuple[list[str], list[str]] | None = None
_SEARCH_SEEDED: bool = False


def search_symbols(q: str, limit: int = 20) -> list[dict[str, str]]:
    """Search stocks by NAME or SYMBOL across NSE_ALL + US universes with in-memory fast indexing."""
    from earnings_engine.data import names as names_mod
    from earnings_engine.data.universe import load_nse_all, load_universe

    query = (q or "").strip().upper()
    if not query:
        return []

    global _SEARCH_UNIVERSE_CACHE, _SEARCH_SEEDED
    if _SEARCH_UNIVERSE_CACHE is None:
        try:
            nse = load_nse_all()
        except Exception as e:
            logger.warning("search_symbols: nse_all failed: %s", e)
            nse = []
        try:
            us = load_universe("US")
        except Exception as e:
            logger.warning("search_symbols: us_top failed: %s", e)
            us = []
        _SEARCH_UNIVERSE_CACHE = (nse, us)

    nse, us = _SEARCH_UNIVERSE_CACHE

    if not _SEARCH_SEEDED:
        try:
            names_mod.ensure_names([*nse, *us])
            _SEARCH_SEEDED = True
        except Exception as e:
            logger.warning("search_symbols: name index seeding failed: %s", e)

    seen: set[str] = set()
    results: list[dict[str, str]] = []

    def _add(symbol: str, name: str | None = None, market: str | None = None) -> None:
        symbol = symbol.strip()
        if not symbol or symbol in seen:
            return
        seen.add(symbol)
        results.append(
            {
                "symbol": symbol,
                "name": name or symbol,
                "market": market or ("NSE" if market_of(symbol) == "IN" else "US"),
            }
        )

    # 1) DB-backed name + symbol match (name ranked first).
    _db_results = []
    try:
        _db_results = names_mod.search(query, limit=limit)
    except Exception as e:
        logger.warning("search_symbols: name search failed: %s", e)
    for r in _db_results:
        _add(r["symbol"], r.get("name"), r.get("market"))
        if len(results) >= limit:
            return results

    # 2) Symbol-substring fallback over the universe lists (catches unseeded).
    for symbol in nse + us:
        if query in symbol.upper():
            _add(symbol)
            if len(results) >= limit:
                return results

    # 3) Stale-NSE fallback: refresh from nsetools live.
    if not results:
        try:
            for symbol in load_nse_all(force_refresh=True):
                if query in symbol.upper():
                    _add(symbol)
                    if len(results) >= limit:
                        return results
        except Exception as e:
            logger.warning("search_symbols: live nse refresh failed: %s", e)

    # 4) Final fallback: let the user select exactly what they typed.  If the
    #    query has no exchange suffix, also suggest the NSE (``.NS``) variant.
    if not results:
        if query.endswith(".NS"):
            _add(query, market="NSE")
        else:
            _add(query, market="US")
            _add(f"{query}.NS", market="NSE")

    return results


# ---------------------------------------------------------------------------
# Raw yfinance / NSE exploration (used by the existing playground endpoints)
# ---------------------------------------------------------------------------

def get_ticker_overview(ticker: str) -> dict[str, Any]:
    """Fetch a compact exploration snapshot for one ticker.

    Returns market inference, last price, market cap, 1-week/1-month change,
    and the next few earnings dates.
    """
    import yfinance as yf

    overview: dict[str, Any] = {
        "ticker": ticker,
        "market": market_of(ticker),
        "name": None,
        "last_price": None,
        "currency": None,
        "market_cap": None,
        "week_change_pct": None,
        "month_change_pct": None,
        "earnings_dates": [],
        "error": None,
    }

    yt = yf.Ticker(ticker)

    # --- name / currency / market cap via fast_info then .info fallback ---
    try:
        fi = yt.fast_info or {}
        market_cap = fi.get("market_cap")
        last_price = fi.get("last_price")
        currency = fi.get("currency")
        if isinstance(fi, dict) and fi:
            logger.info("playground fast_info keys: %s", sorted(fi.keys()))
    except Exception as e:
        logger.warning("fast_info failed for %s: %s", ticker, e)
        market_cap, last_price, currency = None, None, None

    name = None
    if market_cap is None or last_price is None:
        try:
            info = yt.info or {}
            name = info.get("shortName") or info.get("longName")
            market_cap = info.get("marketCap", market_cap)
            last_price = info.get("currentPrice", info.get("regularMarketPrice", last_price))
            currency = info.get("currency", currency)
        except Exception as e:
            logger.warning(".info fallback failed for %s: %s", ticker, e)

    overview["market_cap"] = market_cap
    overview["last_price"] = last_price
    overview["currency"] = currency
    overview["name"] = name

    # --- price history for % moves ---
    try:
        hist = yt.history(period="3mo", interval="1d")
        if not hist.empty and "Close" in hist.columns:
            close = hist["Close"].dropna()
            if len(close) >= 6:
                overview["week_change_pct"] = round(
                    (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100, 2
                )
            if len(close) >= 22:
                overview["month_change_pct"] = round(
                    (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100, 2
                )
    except Exception as e:
        logger.warning("history failed for %s: %s", ticker, e)

    # --- earnings dates (limit=60 quirk; may return None/empty) ---
    try:
        ed = getattr(yt, "earnings_dates", None)
        if isinstance(ed, pd.DataFrame) and not ed.empty:
            raw_dates: list[str] = []
            if "Earnings Date" in ed.columns:
                parsed = pd.to_datetime(ed["Earnings Date"], errors="coerce")
            else:
                parsed = pd.to_datetime(ed.index, errors="coerce")
            for dt in parsed.dropna():
                if dt.tzinfo is not None:
                    dt = dt.tz_convert(None)
                raw_dates.append(dt.strftime("%Y-%m-%d"))

            now = pd.Timestamp.now().tz_localize(None)
            future = [d for d in raw_dates if pd.Timestamp(d) >= now - pd.Timedelta(days=1)]
            overview["earnings_dates"] = future[:10] or raw_dates[:5]
    except Exception as e:
        logger.warning("earnings_dates failed for %s: %s", ticker, e)

    return overview


def get_ticker_history(ticker: str, period: str = "1mo", interval: str = "1d") -> list[dict[str, Any]]:
    """Fetch OHLCV history for one ticker as a list of row dicts."""
    import yfinance as yf

    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
    except Exception as e:
        logger.warning("history failed for %s: %s", ticker, e)
        return []

    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        rows.append({
            "date": idx.strftime("%Y-%m-%d") if isinstance(idx, pd.Timestamp) else str(idx),
            "open": float(row["Open"]) if pd.notna(row.get("Open")) else None,
            "high": float(row["High"]) if pd.notna(row.get("High")) else None,
            "low": float(row["Low"]) if pd.notna(row.get("Low")) else None,
            "close": float(row["Close"]) if pd.notna(row.get("Close")) else None,
            "volume": int(row["Volume"]) if pd.notna(row.get("Volume")) else None,
        })
    return rows[-120:]  # cap at 120 rows for the UI table


def get_nse_universe_info(force_refresh: bool = False) -> dict[str, Any]:
    """Return NSE universe sizes + samples (nse_all, nse_large_cap, configured tops)."""
    from earnings_engine.data.universe import load_all, load_nse_all, load_nse_large_cap, load_universe

    result: dict[str, Any] = {}

    for key, loader in [
        ("NSE_ALL", lambda: load_nse_all(force_refresh=force_refresh)),
        ("NSE_LARGE_CAP", lambda: load_nse_large_cap(force_refresh=force_refresh)),
        ("IN", lambda: load_universe("IN")),
        ("US", lambda: load_universe("US")),
        ("COMBINED", load_all),
    ]:
        try:
            tickers = loader()
            result[key] = {
                "count": len(tickers),
                "sample": tickers[:10],
            }
        except Exception as e:
            logger.warning("universe %s failed: %s", key, e)
            result[key] = {"count": 0, "sample": [], "error": str(e)}

    return result
