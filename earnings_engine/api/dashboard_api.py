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
from earnings_engine.data import coverage as coverage_mod
from earnings_engine.data import industry as industry_mod
from earnings_engine.data import sector_moves as sector_moves_mod
from earnings_engine.data import recent_results as recent_results_mod
from earnings_engine.data import swing_ranges as swing_ranges_mod
from earnings_engine.data.market_context import detect_swing_range, enrich_upcoming_results
from earnings_engine.data.universe import load_all, load_universe, load_universe_from_file
from earnings_engine.data.predictions import (
    benchmark_ohlcv_forecast,
    delete_prediction,
    get_kronos_accuracy_summary,
    load_latest_predictions,
    load_prediction_history,
    store_prediction,
)
from earnings_engine.data import watchlists as watchlists_mod
from earnings_engine.data.buy_the_dip import get_buydip_today, get_buydip_yesterday
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.dashboard_api")

UNIVERSES_DIR = Path(__file__).resolve().parent.parent / "data" / "universes"

_REFRESH_STATUS: dict[str, dict[str, Any]] = {}


def _settings() -> Settings:
    return Settings()


def _resolve_tickers(market: str | None) -> list[str]:
    """Resolve the ticker list for a given universe selector.

    Matches the CLI ``upcoming-results`` semantics:
    - ``None`` / ``"ALL"``  -> ``load_all()`` (IN + US, same as CLI default)
    - ``"WATCHLIST"``       -> the server-side DB watchlist ``my_watchlist``
    - ``"IN"``/``"US"``/``"NSE_ALL"``/``"NSE_LARGE_CAP"`` -> ``load_universe(market)``
    - anything else         -> treated as a DB watchlist name (so per-tab
      watchlists are usable directly), then as a universe file name

    Watchlist names are stored in the DB with their original casing — the
    exact string is tried first, followed by an all-uppercase fallback so
    legacy universe files (typically UPPERCASE.txt) still resolve correctly.
    """
    tickers_raw: list[Any] = []
    if market:
        mu = market.upper()
        if mu == "WATCHLIST":
            tickers_raw = watchlists_mod.get_watchlist("my_watchlist", _settings())
        elif mu == "ALL":
            tickers_raw = load_all()
        elif mu in {"IN", "US", "NSE_ALL", "NSE_LARGE_CAP"}:
            tickers_raw = load_universe(mu)
        else:
            db_list = watchlists_mod.get_watchlist(market, _settings())
            if not db_list and mu != market:
                db_list = watchlists_mod.get_watchlist(mu, _settings())
            if db_list:
                tickers_raw = db_list
            else:
                f = UNIVERSES_DIR / f"{market}.txt"
                if f.exists():
                    tickers_raw = load_universe_from_file(f)
                elif mu != market:
                    f_mu = UNIVERSES_DIR / f"{mu}.txt"
                    if f_mu.exists():
                        tickers_raw = load_universe_from_file(f_mu)
    else:
        tickers_raw = load_all()

    clean_tickers: list[str] = []
    for item in tickers_raw or []:
        if isinstance(item, dict):
            sym = item.get("ticker") or item.get("symbol") or ""
            if sym:
                clean_tickers.append(str(sym).strip().upper())
        elif item:
            clean_tickers.append(str(item).strip().upper())
    return clean_tickers


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

def get_upcoming_results(
    days: int = 60,
    market: str | None = None,
    past_days: int = 0,
    start_date: str | None = None,
) -> list[dict[str, Any]]:
    """Get earnings results with market context enrichment.

    ``market`` follows the same semantics as the ``upcoming-results`` CLI:
    None/"ALL" -> IN+US (load_all), "WATCHLIST" -> watchlist file, an
    "IN"/"US"/"NSE_ALL"/"NSE_LARGE_CAP" code, or a user-created universe name.
    """
    settings = _settings()
    tickers = _resolve_tickers(market)
    logger.info(
        "get_upcoming_results: market=%s, days=%d, past_days=%d, start_date=%s (resolved %d tickers)",
        market,
        days,
        past_days,
        start_date,
        len(tickers),
    )
    if not tickers:
        return []

    if past_days > 0 and not start_date:
        start_ts = pd.Timestamp.today().normalize() - pd.Timedelta(days=past_days)
        start_date = start_ts.strftime("%Y-%m-%d")
        total_days = past_days + days
    else:
        total_days = days

    df = earnings_mod.upcoming_earnings(tickers, settings, days=total_days, start_date=start_date)
    if df.empty:
        return []

    enriched = enrich_upcoming_results(df)
    mark_refreshed("results", rows=len(enriched))
    logger.info("get_upcoming_results: returning %d enriched upcoming results", len(enriched))

    ticker_list = [str(t) for t in enriched["ticker"].dropna().unique()]

    # Merge latest Kronos predictions for the same tickers (read-only, from the
    # SQLite audit trail — never runs the model).
    try:
        latest_kronos = {row["ticker"]: row for row in get_kronos_latest_predictions(tickers=ticker_list)}
    except Exception:
        latest_kronos = {}

    # Merge GBM predictions from today's daily prediction cache (read-only —
    # never trains/runs the model).  The cache is populated by
    # `cache-predictions` / `predict` / `upcoming-results`.
    try:
        from earnings_engine.prediction_cache import load_prediction_cache_partial
        cached = load_prediction_cache_partial(ticker_list)
        gbm_map = cached.get("gbm", {})
    except Exception:
        gbm_map = {}

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
        item["gbm_prediction"] = gbm_map.get(ticker_str)
        results.append(item)
    return results


def get_results_report_components(
    days: int = 60,
    market: str | None = None,
    past_days: int = 0,
    start_date: str | None = None,
) -> dict[str, Any]:
    """Build report-style HTML fragments for the dashboard Results tab.

    Reuses ``build_upcoming_results_fragments`` from the reports module so the
    dashboard renders the exact same day-grouped ledger + popups layout as the
    standalone HTML report.  Kronos/GBM predictions are attached via the
    cache-aware runners (reuse today's cached predictions, never re-train).
    """
    import importlib
    import earnings_engine.reports.render as _render_mod
    importlib.reload(_render_mod)
    build_upcoming_results_fragments = _render_mod.build_upcoming_results_fragments

    settings = _settings()
    tickers = _resolve_tickers(market)
    if not tickers:
        return {"success": False, "error": "No tickers", "day_legend": "", "day_sections": "", "popups": ""}

    if past_days > 0 and not start_date:
        start_ts = pd.Timestamp.today().normalize() - pd.Timedelta(days=past_days)
        start_date = start_ts.strftime("%Y-%m-%d")
        total_days = past_days + days
    else:
        total_days = days

    df = earnings_mod.upcoming_earnings(tickers, settings, days=total_days, start_date=start_date)
    if df.empty:
        return {"success": False, "error": "No results found for the selected date window", "day_legend": "", "day_sections": "", "popups": ""}

    enriched = enrich_upcoming_results(df)
    if enriched.empty:
        return {"success": False, "error": "Enrichment empty", "day_legend": "", "day_sections": "", "popups": ""}

    enriched["kronos_14d"] = None
    enriched["gbm_prediction"] = None

    fragments = build_upcoming_results_fragments(enriched, on_demand=True)
    fragments["success"] = True
    fragments["fetch_record"] = earnings_mod.get_fetch_record_status(settings)
    return fragments


def get_month_filter_report_components(
    days: int = 60,
    market: str | None = None,
    past_days: int = 60,
    force_sync: bool = False,
) -> dict[str, Any]:
    """Get precalculated Month Filter report components with present-day delta sync."""
    settings = _settings()
    
    # Always ensure present-day earnings calendar is synced
    fetch_rec = earnings_mod.sync_present_day_earnings_delta(settings, force=force_sync)

    cache_key = f"month_filter_{market or 'ALL'}_{past_days}_{days}"
    if not force_sync:
        cached = earnings_mod.get_cached_month_filter(settings, cache_key)
        if cached:
            cached["fetch_record"] = fetch_rec
            return cached

    fragments = get_results_report_components(days=days, market=market, past_days=past_days)
    if fragments.get("success"):
        fragments["fetch_record"] = fetch_rec
        earnings_mod.set_cached_month_filter(settings, cache_key, fragments)
    return fragments


def run_prediction_for_ticker(
    ticker: str,
    engine: str = "kronos",
    days: int = 14,
    lookback: int = 120,
    pred_len: int = 14,
    device: str | None = None,
) -> dict[str, Any]:
    """Compute a Kronos/GBM prediction for a SINGLE ticker on demand.

    Used by the per-row "Run" buttons in the Results report so the dashboard
    only does model work for the rows the user actually inspects.
    """
    settings = _settings()
    ticker = str(ticker).strip().upper()
    if not ticker:
        return {"success": False, "error": "Ticker is required"}
    try:
        if engine == "gbm":
            from earnings_engine.predict import run_gbm_with_cache

            gbm_map = run_gbm_with_cache([ticker], settings, days=days)
            pred = (gbm_map or {}).get(ticker)
            if not pred:
                return {"success": False, "error": "No GBM prediction returned for this ticker"}
            return {"success": True, "engine": "gbm", "ticker": ticker, "prediction": pred}
        # default: kronos
        from earnings_engine.kronos_predictor import run_kronos_with_cache

        forecasts = run_kronos_with_cache([ticker], lookback=lookback, pred_len=pred_len, device=device, audit=True)
        pred = None
        for fc in forecasts or []:
            if fc and fc.get("symbol") == ticker:
                pred = fc
                break
        if not pred:
            pred = next(iter(forecasts or []), None)
        if not pred:
            return {"success": False, "error": "No Kronos prediction returned for this ticker"}
        return {"success": True, "engine": "kronos", "ticker": ticker, "prediction": pred}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_event_dataset_summary() -> dict[str, Any]:
    """Get summary stats from event_dataset table."""
    from earnings_engine.data.db import get_db_connection

    try:
        conn = get_db_connection(Settings())
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
            "source": "database",
        }
    except Exception as exc:
        return {"available": False, "rows": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Swing tab
# ---------------------------------------------------------------------------

def get_swing_setups(market: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Get swing setups with support/resistance and momentum data."""
    settings = _settings()
    tickers = _resolve_tickers(market)

    # Pre-fetch upcoming earnings for the whole batch so each swing card can
    # show a real "Next Earnings" date (enrich_upcoming_results() alone does
    # not populate it for a single-ticker frame).
    upcoming_map: dict[str, str] = {}
    try:
        upcoming_df = earnings_mod.upcoming_earnings(tickers[:limit], settings, days=90)
        if not upcoming_df.empty:
            for _, ev in upcoming_df.iterrows():
                t = str(ev["ticker"])
                if t not in upcoming_map:
                    upcoming_map[t] = (
                        ev["earnings_date"].strftime("%Y-%m-%d")
                        if isinstance(ev["earnings_date"], pd.Timestamp)
                        else str(ev["earnings_date"])
                    )
    except Exception:
        upcoming_map = {}

    results = []
    wl_name = market or "ALL"

    # 1. Batch enrich all tickers at once instead of individual per-ticker calls
    try:
        batch_df = pd.DataFrame({"ticker": tickers[:limit]})
        enriched_all = enrich_upcoming_results(batch_df, settings)
    except Exception as e:
        logger.warning("Failed batch enrich in get_swing_setups: %s", e)
        enriched_all = pd.DataFrame()

    if enriched_all.empty:
        return results

    # 2. Batch load all stored swing ranges in 1 query
    try:
        stored_ranges_wl = {r["ticker"]: r for r in swing_ranges_mod.list_ranges(wl_name, settings)}
        stored_ranges_all = (
            {r["ticker"]: r for r in swing_ranges_mod.list_ranges("ALL", settings)}
            if wl_name != "ALL"
            else stored_ranges_wl
        )
    except Exception:
        stored_ranges_wl = {}
        stored_ranges_all = {}

    for _, row_series in enriched_all.iterrows():
        try:
            row = row_series.to_dict()
            ticker = str(row.get("ticker", "")).strip()
            if not ticker:
                continue

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

            # Populate "Next Earnings" from the cached upcoming calendar
            if not item.get("earnings_date"):
                item["earnings_date"] = upcoming_map.get(ticker)

            # Attach swing range for this watchlist (or ALL fallback) from memory map
            sr = stored_ranges_wl.get(ticker) or stored_ranges_all.get(ticker)
            if not sr and item.get("current_support") is not None and item.get("next_resistance") is not None:
                try:
                    swing_ranges_mod.record_auto_range(
                        wl_name,
                        ticker,
                        float(item["current_support"]),
                        float(item["next_resistance"]),
                        settings=settings,
                    )
                    sr = swing_ranges_mod.get_swing_range(wl_name, ticker, settings)
                    if sr:
                        stored_ranges_wl[ticker] = sr
                except Exception:
                    pass

            item["swing_range"] = sr
            if sr:
                if sr.get("lower_bound") is not None:
                    item["current_support"] = sr["lower_bound"]
                if sr.get("upper_bound") is not None:
                    item["next_resistance"] = sr["upper_bound"]

            price = item.get("current_price")
            support = item.get("current_support")
            resistance = item.get("next_resistance")
            momentum = item.get("thirty_day_return_pct") or 0

            if price is not None and support is not None and resistance is not None and resistance > support:
                channel_width = resistance - support
                # Position in channel: 0.0 = support, 1.0 = resistance
                pos = (price - support) / channel_width

                if pos < -0.02:
                    # Broken below support
                    item["swing_signal"] = "Breakdown"
                    item["swing_zone"] = "Below Support"
                elif pos <= 0.25:
                    # In bottom 25% of channel -> BUY ZONE
                    if momentum >= 0 or pos <= 0.10:
                        item["swing_signal"] = "Strong Buy"
                    else:
                        item["swing_signal"] = "Buy"
                    item["swing_zone"] = "Buy Zone"
                elif pos <= 0.70:
                    # Middle of range
                    item["swing_signal"] = "Neutral"
                    item["swing_zone"] = "Mid Channel"
                elif pos <= 1.00:
                    # Top 30% of channel approaching resistance
                    item["swing_signal"] = "Sell Zone"
                    item["swing_zone"] = "Near Resistance"
                else:
                    # Above resistance -> Overbought / Breakout
                    item["swing_signal"] = "Overbought"
                    item["swing_zone"] = "Above Resistance"
            else:
                if momentum > 5:
                    item["swing_signal"] = "Momentum"
                elif momentum < -5:
                        item["swing_signal"] = "Cautious"
                else:
                    item["swing_signal"] = "Neutral"
                item["swing_zone"] = "Unknown"

            results.append(item)
        except Exception:
            continue

    # Enrich each swing setup with the latest multi-modal AI synthesis & news sentiment
    try:
        from earnings_engine.predict_multimodal import get_latest_ai_predictions_all
        all_ai_preds = {p["ticker"].upper(): p for p in get_latest_ai_predictions_all(settings)}
        for r in results:
            sym = (r.get("ticker") or "").upper()
            if sym in all_ai_preds:
                r["ai_synthesis"] = all_ai_preds[sym]
    except Exception as e:
        logger.debug("Failed to attach AI synthesis to swing setups: %s", e)

    mark_refreshed("swing", rows=len(results))
    return results


def get_swing_range_api(watchlist: str = "ALL", ticker: str = "") -> dict[str, Any]:
    """Get the current swing range, auto-detected trading channel, and cycle history for a ticker in a watchlist."""
    settings = _settings()
    ticker = ticker.strip().upper()
    if not ticker:
        return {"error": "Ticker is required"}

    wl_name = watchlist or "ALL"
    rng = swing_ranges_mod.get_swing_range(wl_name, ticker, settings)
    if not rng and wl_name != "ALL":
        rng = swing_ranges_mod.get_swing_range("ALL", ticker, settings)

    prices = prices_mod.load_prices(ticker, settings)
    if prices.empty:
        prices = prices_mod.fetch_prices(ticker, settings, force=False)

    current_price = None
    auto_rng = None
    if not prices.empty and "close" in prices.columns:
        df_p = prices.copy()
        if "date" in df_p.columns:
            df_p["date"] = pd.to_datetime(df_p["date"], errors="coerce")
            df_p = df_p.dropna(subset=["date"]).sort_values("date").set_index("date")
        closes = pd.to_numeric(df_p["close"], errors="coerce").dropna()
        if not closes.empty:
            current_price = float(closes.iloc[-1])
            auto_rng = detect_swing_range(closes)

    if not rng and auto_rng:
        if auto_rng.get("lower") is not None and auto_rng.get("upper") is not None:
            swing_ranges_mod.record_auto_range(
                wl_name,
                ticker,
                auto_rng["lower"],
                auto_rng["upper"],
                cycles=auto_rng.get("cycles"),
                avg_days=auto_rng.get("avg_days"),
                cycles_data=auto_rng.get("cycles_data"),
                settings=settings,
            )
            rng = swing_ranges_mod.get_swing_range(wl_name, ticker, settings)

    history = swing_ranges_mod.get_cycle_history(wl_name, ticker, settings)
    if not history and wl_name != "ALL":
        history = swing_ranges_mod.get_cycle_history("ALL", ticker, settings)
    if not history and auto_rng and auto_rng.get("cycles_data"):
        history = auto_rng.get("cycles_data")

    return {
        "success": True,
        "watchlist": wl_name,
        "ticker": ticker,
        "current_price": current_price,
        "range": rng,
        "auto_range": auto_rng,
        "history": history,
    }


def set_swing_range_api(
    watchlist: str,
    ticker: str,
    lower: float,
    upper: float,
    cycles: int | None = None,
) -> dict[str, Any]:
    """Set a user override for swing range."""
    settings = _settings()
    ticker = ticker.strip().upper()
    wl_name = watchlist or "ALL"
    res = swing_ranges_mod.set_user_range(
        watchlist=wl_name,
        ticker=ticker,
        lower=lower,
        upper=upper,
        cycles=cycles,
        settings=settings,
    )
    return res


def clear_swing_range_api(watchlist: str = "ALL", ticker: str = "") -> dict[str, Any]:
    """Clear custom swing range and revert to auto-detection."""
    settings = _settings()
    ticker = ticker.strip().upper()
    wl_name = watchlist or "ALL"
    swing_ranges_mod.clear_user_range(wl_name, ticker, settings)

    # Re-detect auto range if prices are available
    prices = prices_mod.load_prices(ticker, settings)
    if prices.empty:
        prices = prices_mod.fetch_prices(ticker, settings, force=False)
    if not prices.empty and "close" in prices.columns:
        closes = pd.to_numeric(prices["close"], errors="coerce").dropna()
        auto_rng = detect_swing_range(closes)
        if auto_rng.get("lower") is not None and auto_rng.get("upper") is not None:
            swing_ranges_mod.record_auto_range(
                wl_name,
                ticker,
                auto_rng["lower"],
                auto_rng["upper"],
                cycles=auto_rng.get("cycles"),
                avg_days=auto_rng.get("avg_days"),
                cycles_data=auto_rng.get("cycles_data"),
                settings=settings,
            )

    return get_swing_range_api(watchlist=wl_name, ticker=ticker)


def get_swing_cycle_history_api(watchlist: str = "ALL", ticker: str = "") -> list[dict[str, Any]]:
    """Return cycle history for a ticker."""
    settings = _settings()
    ticker = ticker.strip().upper()
    wl_name = watchlist or "ALL"
    hist = swing_ranges_mod.get_cycle_history(wl_name, ticker, settings)
    if not hist and wl_name != "ALL":
        hist = swing_ranges_mod.get_cycle_history("ALL", ticker, settings)
    return hist


def list_swing_ranges_api(watchlist: str = "ALL") -> list[dict[str, Any]]:
    """Return all swing ranges for a watchlist."""
    settings = _settings()
    wl_name = watchlist or "ALL"
    return swing_ranges_mod.list_ranges(wl_name, settings)



# ---------------------------------------------------------------------------
# Kronos tab
# ---------------------------------------------------------------------------

def get_kronos_predictions(
    tickers: list[str] | None = None,
    lookback: int = 120,
    pred_len: int = 14,
    device: str | None = None,
    progress_callback: callable | None = None,
) -> list[dict[str, Any]]:
    from earnings_engine.kronos_predictor import run_kronos_with_cache

    if not tickers:
        tickers = watchlists_mod.get_watchlist("my_watchlist", _settings()) or load_universe("IN")[:10]
    if not tickers:
        return []

    # Cache-aware runner: reuses today's cached Kronos results when available.
    # audit=False because this function persists the audit rows itself below
    # (avoids double-writing to the SQLite audit trail).
    forecasts = run_kronos_with_cache(
        tickers,
        lookback=lookback,
        pred_len=pred_len,
        device=device,
        progress_callback=progress_callback,
        force=False,
        audit=False,
    )
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


def get_system_device_info() -> dict[str, Any]:
    """Get system hardware and CUDA device diagnostics for the dashboard."""
    from earnings_engine.kronos_predictor import get_cuda_status

    return get_cuda_status()


def _resolve_kronos_tickers(watchlist: str | None, tickers: list[str] | None, settings: Settings) -> list[str] | None:
    """Resolve list of tickers from explicit tickers or a named watchlist."""
    if tickers:
        return tickers
    if watchlist and watchlist.strip() and watchlist.strip().upper() not in ("ALL", "GLOBAL"):
        wl = watchlist.strip()
        # Try custom app watchlists first
        saved_tickers = watchlists_mod.get_watchlist(wl, settings)
        if saved_tickers:
            return saved_tickers
        # Try universe files next
        loaded = load_universe_from_file(wl, settings=settings)
        if loaded:
            return [item["ticker"] for item in loaded]
    return None


def get_kronos_predictions_audit(
    tickers: list[str] | None = None,
    watchlist: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the full audit history of Kronos predictions (optionally filtered by ticker/watchlist)."""
    settings = _settings()
    resolved = _resolve_kronos_tickers(watchlist, tickers, settings)
    return load_prediction_history(tickers=resolved, limit=limit, settings=settings)


def get_kronos_latest_predictions(
    tickers: list[str] | None = None,
    watchlist: str | None = None,
) -> list[dict[str, Any]]:
    """Return the most-recent Kronos prediction per ticker (optionally filtered by ticker/watchlist)."""
    settings = _settings()
    resolved = _resolve_kronos_tickers(watchlist, tickers, settings)
    logger.info(
        "get_kronos_latest_predictions: watchlist=%s, tickers_count=%s",
        watchlist or "ALL",
        len(resolved) if resolved else "ALL",
    )
    return load_latest_predictions(tickers=resolved, settings=settings)


def get_kronos_predictions_for_ticker(ticker: str) -> list[dict[str, Any]]:
    """Return all historical predictions for a specific ticker."""
    settings = _settings()
    logger.info("get_kronos_predictions_for_ticker: ticker=%s", ticker)
    return load_prediction_history(tickers=[ticker], settings=settings)


def get_kronos_accuracy_api(
    tickers: list[str] | None = None,
    watchlist: str | None = None,
) -> dict[str, Any]:
    """Return overall and per-stock accuracy statistics for all Kronos predictions (optionally filtered)."""
    settings = _settings()
    resolved = _resolve_kronos_tickers(watchlist, tickers, settings)
    logger.info(
        "get_kronos_accuracy_api: watchlist=%s, tickers_count=%s",
        watchlist or "ALL",
        len(resolved) if resolved else "ALL",
    )
    return get_kronos_accuracy_summary(tickers=resolved, settings=settings)


def get_kronos_ohlcv_benchmark_api(
    ticker: str,
    run_at: str | None = None,
) -> dict[str, Any]:
    """Return the OHLCV benchmark comparison for a ticker's latest or specific forecast."""
    settings = _settings()
    history = load_prediction_history(tickers=[ticker], settings=settings)
    if not history:
        return {"bars": [], "summary": {"total_bars": 0, "settled_bars": 0, "is_evaluated": False}}

    selected = None
    if run_at:
        for r in history:
            if r.get("run_at") == run_at:
                selected = r
                break
    if not selected:
        selected = history[0]

    pred = selected.get("prediction") or {}
    series = pred.get("forecast_series") or selected.get("forecast_series") or []
    if not series:
        return {"bars": [], "summary": {"total_bars": 0, "settled_bars": 0, "is_evaluated": False}}

    return benchmark_ohlcv_forecast(series, ticker=ticker, settings=settings)


def create_universe_file(name: str, tickers: list[str] | None = None) -> dict[str, Any]:
    """Create a new named watchlist in the SQLite DB (kept for API compat).

    Names are sanitized to a safe ``[A-Za-z0-9_-]+`` form.  An empty watchlist
    is still created (``watchlist_meta`` row) so the user can populate it later
    via the add/remove endpoints.
    """
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-")).strip()
    if not safe_name or safe_name.startswith("."):
        return {"success": False, "error": "Invalid watchlist name"}

    settings = _settings()
    created = watchlists_mod.create_watchlist(safe_name, settings)
    if not created.get("success"):
        return created

    results = []
    for t in [t.strip().upper() for t in (tickers or []) if t and t.strip()]:
        results.append(watchlists_mod.add_to_watchlist(safe_name, t, settings))
    added = sum(1 for r in results if r.get("success"))
    return {
        "success": True,
        "name": safe_name,
        "tickers": added,
        "watchlist": watchlists_mod.get_watchlist(safe_name, settings),
    }


def _next_watchlist_name(settings: Settings) -> str:
    """Return the next available auto-name for a new watchlist."""
    existing = {w["name"] for w in watchlists_mod.list_watchlists(settings)}
    i = 1
    while f"Watchlist {i}" in existing:
        i += 1
    return f"Watchlist {i}"


def create_watchlist_api(name: str | None = None, tickers: list[str] | None = None) -> dict[str, Any]:
    """Create a watchlist, auto-naming it (Watchlist 1, 2, …) when no name given."""
    settings = _settings()
    safe = name if (name and name.strip()) else _next_watchlist_name(settings)
    return create_universe_file(safe, tickers=tickers)


def get_all_watchlists(include_universes: bool = False) -> list[dict[str, Any]]:
    """Return every watchlist with its full ticker list (for the Watchlist tab)."""
    settings = _settings()
    custom_lists = watchlists_mod.all_watchlists(settings)
    for c in custom_lists:
        c["type"] = "custom"
        c["is_builtin"] = False
        c["is_under_100"] = len(c.get("tickers", [])) <= 100
        c["display_name"] = c.get("name", "")
        c["summary"] = "Custom user-defined watchlist."
        c["explanation"] = "Custom watchlist created and managed by the user for tracking swing trading ranges, price moves, and earnings."
    return custom_lists


def get_all_watchlists_and_universes() -> dict[str, Any]:
    """Return custom watchlists and built-in universes with full metadata and explanations."""
    settings = _settings()
    custom_lists = get_all_watchlists(include_universes=False)
    from earnings_engine.data.universe import get_universe_details
    universes = get_universe_details(settings)
    return {
        "watchlists": custom_lists,
        "universes": universes,
        "all_lists": custom_lists + universes,
    }


def rename_watchlist_api(name: str, new_name: str) -> dict[str, Any]:
    return watchlists_mod.rename_watchlist(name, new_name, _settings())


def delete_watchlist_api(name: str) -> dict[str, Any]:
    return watchlists_mod.delete_watchlist(name, _settings())


# ---------------------------------------------------------------------------
# Watchlist (DB-backed, named lists per dashboard tab)
# ---------------------------------------------------------------------------

def get_watchlist(name: str = "my_watchlist") -> list[str]:
    return watchlists_mod.get_watchlist(name, _settings())


def add_to_watchlist(ticker: str, name: str = "my_watchlist") -> dict[str, Any]:
    result = watchlists_mod.add_to_watchlist(name, ticker, _settings())
    if result.get("success"):
        mark_refreshed(name, rows=len(result.get("watchlist", [])))
    return result


def remove_from_watchlist(ticker: str, name: str = "my_watchlist") -> dict[str, Any]:
    result = watchlists_mod.remove_from_watchlist(name, ticker, _settings())
    if result.get("success"):
        mark_refreshed(name, rows=len(result.get("watchlist", [])))
    return result


# ---------------------------------------------------------------------------
# Watchlist browser
# ---------------------------------------------------------------------------

def get_universe_files() -> list[dict[str, Any]]:
    return watchlists_mod.list_watchlists(_settings())


# ---------------------------------------------------------------------------
# Data coverage
# ---------------------------------------------------------------------------

def get_data_coverage(market: str | None = None, tickers: list[str] | None = None) -> dict[str, Any]:
    """Return per-ticker data coverage for the requested universe.

    ``market`` follows the same semantics as the other dashboard endpoints
    (None/"ALL" -> IN+US, "WATCHLIST" -> watchlist file, universe name/code).
    ``tickers``, when provided, overrides the market resolution.
    """
    settings = _settings()
    ticker_list = tickers or _resolve_tickers(market)
    result = coverage_mod.get_data_coverage(ticker_list, settings)
    mark_refreshed(
        "coverage",
        rows=result.get("total", 0),
        message=f"{result.get('with_prices', 0)}/{result.get('total', 0)} prices, {result.get('with_earnings', 0)}/{result.get('total', 0)} earnings",
    )
    return result


def ingest_earnings_incremental_api(market: str | None = None, tickers: list[str] | None = None) -> dict[str, Any]:
    """Fetch earnings only for tickers that are missing earnings data.

    ``market`` follows the same semantics as the other dashboard endpoints
    (None/"ALL" -> IN+US, "WATCHLIST" -> watchlist file, universe name/code).
    ``tickers``, when provided, overrides the market resolution.
    """
    settings = _settings()
    ticker_list = tickers or _resolve_tickers(market)
    if not ticker_list:
        return {"success": False, "error": "No tickers to process"}

    try:
        result = earnings_mod.ingest_earnings_incremental(ticker_list, settings)
        mark_refreshed("earnings", rows=result.get("fetched", 0),
                       message=f"{result.get('fetched', 0)} fetched, {result.get('already_cached', 0)} cached")
        return {"success": True, **result}
    except Exception as e:
        mark_refreshed("earnings", status="error", message=str(e))
        return {"success": False, "error": str(e)}


def get_industry_moves(market: str | None = None, lookback_days: int = 60) -> dict[str, Any]:
    """Return recent-earnings moves grouped by industry for the Industries tab.

    Resolves the universe via ``_resolve_tickers``, computes each past result's
    +7-day high/low move from cached prices, and groups by industry using only
    the CACHED industry classifications (NO live yfinance fetch).  Tickers
    without a cached industry fall back to "Other" and are counted as
    ``unclassified``.  Live classification only happens on-demand via
    ``POST /api/v1/dashboard/industries/classify``.
    """
    settings = _settings()
    tickers = _resolve_tickers(market)
    if not tickers:
        return {"industries": [], "best_industry": None, "total_results": 0, "unclassified": 0}

    moves = sector_moves_mod.get_recent_earnings_moves(tickers, settings, lookback_days=lookback_days)
    move_tickers = [r["ticker"] for r in moves]
    # Cache-only lookup — never fires a bulk yfinance call on tab load.
    industry_map = industry_mod.load_industry_map(move_tickers, settings)
    groups = sector_moves_mod.group_by_industry(moves, industry_map)
    # Sort industries so the strongest (most positive) is at the top.
    groups.sort(key=lambda g: (g["positive_count"], round(g["avg_high_pct"], 6)), reverse=True)
    best = sector_moves_mod.pick_best_industry(groups)
    unclassified = sum(1 for r in moves if not industry_map.get(r["ticker"]))
    return {
        "industries": groups,
        "best_industry": best["industry"] if best else None,
        "total_results": len(moves),
        "unclassified": unclassified,
    }


def classify_industries_api(market: str | None = None, tickers: list[str] | None = None, force: bool = False) -> dict[str, Any]:
    """Backfill/cache industry classifications for a universe from yfinance."""
    settings = _settings()
    ticker_list = tickers or _resolve_tickers(market)
    if not ticker_list:
        return {"success": False, "error": "No tickers to classify"}
    try:
        res = industry_mod.ingest_industries(ticker_list, settings, force=force)
        ok = sum(1 for v in res.values() if v > 0)
        return {"success": True, "classified": ok, "total": len(ticker_list)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_recent_results_api(
    market: str | None = None,
    correction_pct: float = 5.0,
    drop_pct: float = 3.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Return recent results with momentum + buy-the-dip / dip-recovery signals.

    Resolves the universe via ``_resolve_tickers`` and delegates to
    ``recent_results_mod.get_recent_results`` for the per-ticker scan.  An optional
    ``start_date``/``end_date`` (ISO) enables historical validation over a range.
    """
    settings = _settings()
    tickers = _resolve_tickers(market)
    if not tickers:
        return {"rows": [], "buy_dip_count": 0, "dip_recovery_count": 0, "today_count": 0, "yesterday_count": 0, "total": 0}
    return recent_results_mod.get_recent_results(
        tickers, settings,
        correction_pct=correction_pct,
        drop_pct=drop_pct,
        start_date=start_date,
        end_date=end_date,
    )


def get_recent_results_verdict_api(
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Opt-in earnings-quality verdict (surprise when present, else vs sector peers).

    Runs only when the user explicitly asks, so the always-on Buy-the-Dip scan
    pays no cost for it.
    """
    settings = _settings()
    tickers = _resolve_tickers(market)
    if not tickers:
        return {"verdicts": {}, "total": 0}
    events = recent_results_mod.load_recent_results(tickers, settings, start_date=start_date, end_date=end_date)
    price_map: dict[str, Any] = {}
    for t in sorted({t for t, _ in events}):
        try:
            price_map[t] = prices_mod.fetch_prices(t, settings)
        except Exception:
            price_map[t] = pd.DataFrame()
    verdicts = recent_results_mod.compute_earnings_verdicts(events, price_map, settings)
    return {"verdicts": verdicts, "total": len(verdicts)}


def get_patterns_api(
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Aggregate buy-the-dip / industry patterns over a result timeframe."""
    settings = _settings()
    tickers = _resolve_tickers(market)
    if not tickers:
        return {
            "total": 0, "positive": 0, "negative": 0, "neutral": 0,
            "best_positive_industry": None, "best_ratio_industry": None,
            "positive_dipped_total": 0, "comeback_50_total": 0, "kept_dipping_total": 0,
            "industries": [], "rows": [],
        }
    return recent_results_mod.compute_patterns(tickers, settings, start_date=start_date, end_date=end_date)


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
        "coverage": _REFRESH_STATUS.get("coverage", {}),
        "earnings": _REFRESH_STATUS.get("earnings", {}),
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
        from earnings_engine.kronos_predictor import run_kronos_with_cache
    except Exception as e:
        return {"success": False, "error": f"Kronos predictor unavailable: {str(e)}"}

    # Only use watchlist or explicit tickers - do NOT fall back to IN universe
    # None means "use watchlist", [] means "no tickers"
    if tickers is None:
        target_tickers = watchlists_mod.get_watchlist("my_watchlist", _settings())
    else:
        target_tickers = tickers
    
    if not target_tickers:
        return {"success": False, "error": "No tickers provided and watchlist is empty"}

    settings = _settings()
    try:
        # Cache-aware runner: reuses today's cached Kronos results when available.
        # audit=False because this function persists the audit rows itself below
        # (avoids double-writing to the SQLite audit trail).
        forecasts = run_kronos_with_cache(
            target_tickers,
            lookback=lookback,
            pred_len=pred_len,
            force=False,
            audit=False,
        )
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

def get_buydip_today_api(market: str | None = None) -> dict[str, Any]:
    settings = _settings()
    return get_buydip_today(settings)


def get_buydip_yesterday_api(market: str | None = None) -> dict[str, Any]:
    settings = _settings()
    return get_buydip_yesterday(settings)


# =========================================================================
# Multi-Modal AI Stock Forecast & News Sentiment APIs
# =========================================================================

def run_ai_forecast_api(
    ticker: str,
    swing_support: float | None = None,
    swing_resistance: float | None = None,
) -> dict[str, Any]:
    """Run on-demand multi-modal AI prediction synthesizing news, price action, volume, and swing levels."""
    from earnings_engine.predict_multimodal import run_multimodal_prediction
    settings = _settings()
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {"success": False, "error": "Ticker is required"}
    try:
        prediction = run_multimodal_prediction(
            ticker,
            swing_support=swing_support,
            swing_resistance=swing_resistance,
            settings=settings,
        )
        return {"success": True, "prediction": prediction}
    except Exception as e:
        logger.exception("Error running AI multi-modal forecast for %s: %s", ticker, e)
        return {"success": False, "error": str(e)}


def run_ai_forecasts_batch_api(
    tickers: list[str],
    watchlist: str = "ALL",
) -> list[dict[str, Any]]:
    """Run batch multi-modal AI predictions for a list of tickers."""
    from earnings_engine.predict_multimodal import run_multimodal_prediction
    settings = _settings()
    results: list[dict[str, Any]] = []
    
    for sym in tickers:
        sym = (sym or "").strip().upper()
        if not sym:
            continue
        try:
            pred = run_multimodal_prediction(sym, settings=settings)
            results.append(pred)
        except Exception as e:
            logger.warning("Batch AI forecast failed for %s: %s", sym, e)
            continue

    return results


def get_ticker_news_api(ticker: str, limit: int = 10) -> dict[str, Any]:
    """Fetch real-time news headlines, event topics, and sentiment scores for a ticker."""
    from earnings_engine.data.news_sentiment import get_ticker_news_and_sentiment
    settings = _settings()
    return get_ticker_news_and_sentiment(ticker, limit=limit, settings=settings)


def get_latest_ai_forecasts_api() -> list[dict[str, Any]]:
    """Get the most recent AI multi-modal prediction for every tracked ticker."""
    from earnings_engine.predict_multimodal import get_latest_ai_predictions_all
    settings = _settings()
    return get_latest_ai_predictions_all(settings)


# =========================================================================
# Short-Term Impact News & Catalyst Scanner APIs
# =========================================================================

def get_catalysts_api(
    watchlist: str | None = None,
    impact_level: str | None = None,
    category: str | None = None,
    direction: str | None = None,
    search: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch short-term market impact catalysts with filtering."""
    from earnings_engine.data.catalysts_news import get_short_term_catalysts, fetch_ticker_catalysts
    settings = _settings()
    items = get_short_term_catalysts(
        watchlist_or_universe=watchlist,
        impact_filter=impact_level,
        category_filter=category,
        direction_filter=direction,
        search_query=search,
        limit=limit,
        settings=settings,
    )
    if not items:
        # If cache is empty, seed with active watchlist items
        from earnings_engine.data.catalysts_news import scan_watchlist_catalysts
        scan_watchlist_catalysts(watchlist_name=watchlist, settings=settings)
        items = get_short_term_catalysts(
            watchlist_or_universe=watchlist,
            impact_filter=impact_level,
            category_filter=category,
            direction_filter=direction,
            search_query=search,
            limit=limit,
            settings=settings,
        )
    return items


def get_catalyst_stats_api() -> dict[str, Any]:
    """Get high-impact catalyst KPI statistics."""
    from earnings_engine.data.catalysts_news import get_catalyst_summary_stats
    settings = _settings()
    return get_catalyst_summary_stats(settings)


def scan_catalysts_api(watchlist: str | None = None) -> dict[str, Any]:
    """Trigger real-time catalyst scan across watchlist/universe."""
    from earnings_engine.data.catalysts_news import scan_watchlist_catalysts
    settings = _settings()
    return scan_watchlist_catalysts(watchlist_name=watchlist, settings=settings)


# =========================================================================
# Daily Top 10 Gainers, Driver Attribution & Pattern Discovery APIs
# =========================================================================

def get_daily_top_gainers_api(
    universe: str = "NSE_ALL",
    date: str | None = None,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Get Top 10 Gainers for a date with driver attribution and pattern classification."""
    from earnings_engine.data.gainers_patterns import get_daily_top_gainers
    settings = _settings()
    return get_daily_top_gainers(universe_or_watchlist=universe, date=date, top_n=top_n, settings=settings)


def get_pattern_matrix_api() -> list[dict[str, Any]]:
    """Get discovered pattern archetypes and historical continuation metrics."""
    from earnings_engine.data.gainers_patterns import get_pattern_matrix_summary
    return get_pattern_matrix_summary()


def scan_upcoming_setups_api(universe: str = "NSE_TOP") -> list[dict[str, Any]]:
    """Scan stocks currently coiling or forming high-probability pre-breakout setups."""
    from earnings_engine.data.gainers_patterns import scan_upcoming_breakout_setups
    settings = _settings()
    return scan_upcoming_breakout_setups(universe_or_watchlist=universe, settings=settings)


# =========================================================================
# Active Multi-Category Stock Scanner APIs
# =========================================================================

def get_scanner_categories_api(universe: str = "NSE_TOP") -> list[dict[str, Any]]:
    """Get all scanner categories with live candidate counts."""
    from earnings_engine.data.category_scanner import get_categories_overview
    settings = _settings()
    return get_categories_overview(universe_or_watchlist=universe, settings=settings)


def scan_category_api(
    category_id: str,
    universe: str = "NSE_TOP",
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Get ranked candidate stocks for a specific category."""
    from earnings_engine.data.category_scanner import scan_category
    settings = _settings()
    return scan_category(category_id=category_id, universe_or_watchlist=universe, limit=limit, settings=settings)


def deep_sweep_api(universe: str = "NSE_TOP") -> dict[str, Any]:
    """Trigger a deep multi-category universe sweep."""
    from earnings_engine.data.category_scanner import deep_universe_sweep
    settings = _settings()
    return deep_universe_sweep(universe_or_watchlist=universe, settings=settings)


