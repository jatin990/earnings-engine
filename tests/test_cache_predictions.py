"""Tests for the cache-aware prediction runners and the cache-predictions CLI.

Covers:
- run_gbm_with_cache: cache hit returns cached map, miss computes + persists
- run_kronos_with_cache: cache hit returns cached forecasts, miss computes +
  persists + writes audit rows
- cache-predictions CLI command: flags, progress, cache file, audit writes
- upcoming-results --cache-only: renders from cache without recompute
"""

import json
from datetime import datetime

import pandas as pd
import pytest
from click.testing import CliRunner

import earnings_engine.cli as cli_mod
import earnings_engine.data.predictions as predictions_db_mod
import earnings_engine.kronos_predictor as kronos_mod
import earnings_engine.prediction_cache as cache_mod
import earnings_engine.predict as predict_mod
from earnings_engine.config import EmailSettings, Settings


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_gbm_map(tickers):
    return {
        t: {
            "p_up": 0.62,
            "direction": "UP",
            "confidence": 0.62,
            "earnings_date": "2026-08-10",
            "train_events": 300,
            "model": "gbm",
        }
        for t in tickers
    }


def make_kronos_forecast(ticker):
    return {
        "symbol": ticker,
        "name": f"{ticker} Corp",
        "current_price": 100.0,
        "projected_close": 105.0,
        "support": 95.0,
        "resistance": 110.0,
        "return_pct": 5.0,
        "trend": "Bullish",
        "results_date": None,
        "last_week_change_pct": None,
        "pred_len": 14,
        "forecast_series": [],
        "explanation": "Test explanation.",
    }


def make_kronos_forecasts(tickers):
    return [make_kronos_forecast(t) for t in tickers]


def write_cache_file(tmp_path, kronos_map, gbm_map, date_str=None):
    """Write a predictions cache JSON file under tmp_path/data/cache/predictions."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    cache_dir = tmp_path / "data" / "cache" / "predictions"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"predictions-{date_str}.json"
    path.write_text(
        json.dumps(
            {
                "generated_date": date_str,
                "kronos": kronos_map,
                "gbm": gbm_map,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# run_gbm_with_cache
# ---------------------------------------------------------------------------

def test_run_gbm_with_cache_hit_returns_cached(monkeypatch, tmp_path):
    """On a full cache hit, the cached GBM map is returned without recompute."""
    tickers = ["AAA", "BBB.NS"]
    gbm_map = make_gbm_map(tickers)
    write_cache_file(tmp_path, {}, gbm_map)

    # run_gbm_with_cache imports prediction-cache helpers inside its body, so
    # patch the source module (earnings_engine.prediction_cache), not predict_mod.
    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": {},
        "gbm": gbm_map,
    })
    monkeypatch.setattr(cache_mod, "save_prediction_cache", lambda k, g, date_str=None: tmp_path)
    monkeypatch.setattr(
        predict_mod, "get_gbm_predictions_by_ticker",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not recompute on cache hit")),
    )

    result = predict_mod.run_gbm_with_cache(tickers, Settings(), force=False)
    assert result == gbm_map


def test_run_gbm_with_cache_miss_computes_and_saves(monkeypatch, tmp_path):
    """On a cache miss, the model runs and the result is persisted."""
    tickers = ["AAA", "BBB.NS"]
    gbm_map = make_gbm_map(tickers)
    saved = {}

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": {}, "gbm": {}
    })
    monkeypatch.setattr(
        cache_mod, "save_prediction_cache",
        lambda k, g, date_str=None: saved.update({"kronos": k, "gbm": g}) or tmp_path,
    )

    # The runner forwards progress_callback into get_gbm_predictions_by_ticker;
    # simulate the underlying implementation invoking it per event.
    def fake_gbm(tickers, settings, days=14, progress_callback=None):
        for i, t in enumerate(tickers, start=1):
            if progress_callback:
                progress_callback(i, len(tickers), t)
        return make_gbm_map(tickers)

    monkeypatch.setattr(predict_mod, "get_gbm_predictions_by_ticker", fake_gbm)

    progress = []
    result = predict_mod.run_gbm_with_cache(
        tickers, Settings(), progress_callback=lambda c, t, s, status="ok": progress.append((c, t, s, status))
    )

    assert result == make_gbm_map(tickers)
    assert saved["gbm"] == make_gbm_map(tickers)
    assert len(progress) == 2


def test_run_gbm_with_cache_force_recomputes(monkeypatch, tmp_path):
    """force=True ignores the cache and recomputes."""
    tickers = ["AAA"]
    gbm_map = make_gbm_map(tickers)
    calls = {"n": 0}

    monkeypatch.setattr(
        cache_mod, "load_prediction_cache_partial",
        lambda tickers, date_str=None: (_ for _ in ()).throw(AssertionError("force must skip cache")),
    )
    monkeypatch.setattr(cache_mod, "save_prediction_cache", lambda k, g, date_str=None: tmp_path)
    monkeypatch.setattr(
        predict_mod, "get_gbm_predictions_by_ticker",
        lambda *a, **kw: (calls.__setitem__("n", calls["n"] + 1) or gbm_map),
    )

    result = predict_mod.run_gbm_with_cache(tickers, Settings(), force=True)
    assert result == gbm_map
    assert calls["n"] == 1


def test_run_gbm_with_cache_partial_reuse_only_missing(monkeypatch, tmp_path):
    """Partial cache: reuse covered tickers, compute only the missing one."""
    tickers = ["AAA", "BBB.NS", "CCC.NS"]
    cached_gbm = make_gbm_map(["AAA", "BBB.NS"])
    computed = make_gbm_map(["CCC.NS"])  # only the missing ticker

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": {}, "gbm": cached_gbm,
    })
    monkeypatch.setattr(cache_mod, "save_prediction_cache", lambda k, g, date_str=None: tmp_path)
    called_with = {}
    def fake_gbm(tickers, settings, days=14, progress_callback=None):
        called_with["tickers"] = list(tickers)
        return make_gbm_map(tickers)
    monkeypatch.setattr(predict_mod, "get_gbm_predictions_by_ticker", fake_gbm)

    result = predict_mod.run_gbm_with_cache(tickers, Settings(), force=False)

    # Only the missing ticker was computed.
    assert called_with["tickers"] == ["CCC.NS"]
    # Result contains all three tickers.
    assert set(result.keys()) == set(tickers)


# ---------------------------------------------------------------------------
# run_kronos_with_cache
# ---------------------------------------------------------------------------

def test_run_kronos_with_cache_hit_returns_cached(monkeypatch, tmp_path):
    """On a full cache hit, cached forecasts are returned without recompute."""
    tickers = ["AAA", "BBB.NS"]
    forecasts = make_kronos_forecasts(tickers)
    kronos_map = {fc["symbol"]: fc for fc in forecasts}

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": kronos_map,
        "gbm": {},
    })
    monkeypatch.setattr(cache_mod, "save_prediction_cache", lambda k, g, date_str=None: tmp_path)
    monkeypatch.setattr(
        kronos_mod, "predict_portfolio",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not recompute on cache hit")),
    )
    monkeypatch.setattr(
        predictions_db_mod, "store_prediction",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("audit should not run on cache hit")),
    )

    result = kronos_mod.run_kronos_with_cache(tickers, force=False, audit=True)
    assert len(result) == 2
    assert {fc["symbol"] for fc in result} == set(tickers)


def test_run_kronos_with_cache_audit_reuse_skips_model(monkeypatch, tmp_path):
    """When today's predictions already exist in the audit trail, reuse them."""
    tickers = ["AAA", "BBB.NS"]
    forecasts = make_kronos_forecasts(tickers)
    # Audit rows keyed by ticker, each with a "prediction" dict.
    existing = {
        t: {"ticker": t, "run_at": "2026-08-04 09:00:00", "prediction": dict(fc)}
        for t, fc in zip(tickers, forecasts)
    }

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": {}, "gbm": {}
    })
    monkeypatch.setattr(
        predictions_db_mod, "load_predictions_by_date",
        lambda tickers, date_str, settings=None: existing,
    )
    monkeypatch.setattr(
        kronos_mod, "predict_portfolio",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("audit reuse must not run the model")),
    )
    monkeypatch.setattr(
        predictions_db_mod, "store_prediction",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("audit reuse must not store again")),
    )

    result = kronos_mod.run_kronos_with_cache(tickers, force=False, audit=True)
    assert len(result) == 2
    assert {fc["symbol"] for fc in result} == set(tickers)


def test_run_kronos_with_cache_miss_computes_saves_and_audits(monkeypatch, tmp_path):
    """On a cache miss, forecasts are computed, persisted, and audited."""
    tickers = ["AAA", "BBB.NS"]
    forecasts = make_kronos_forecasts(tickers)
    saved = {}
    audited = []

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": {}, "gbm": {}
    })
    monkeypatch.setattr(
        cache_mod, "save_prediction_cache",
        lambda k, g, date_str=None: saved.update({"kronos": k, "gbm": g}) or tmp_path,
    )
    # No existing predictions in today's audit trail -> proceed to model.
    monkeypatch.setattr(predictions_db_mod, "load_predictions_by_date", lambda tickers, date_str, settings=None: {})

    # The runner forwards progress_callback into predict_portfolio; simulate
    # the underlying implementation invoking it per symbol.
    def fake_portfolio(tickers, lookback=120, pred_len=14, progress_callback=None, on_forecast=None, **kw):
        for i, t in enumerate(tickers, start=1):
            if progress_callback:
                progress_callback(i, len(tickers), t)
        for fc in make_kronos_forecasts(tickers):
            if on_forecast:
                on_forecast(fc)
        return make_kronos_forecasts(tickers)

    monkeypatch.setattr(kronos_mod, "predict_portfolio", fake_portfolio)
    # run_kronos_with_cache imports store_prediction from
    # earnings_engine.data.predictions inside its body, so patch that module.
    monkeypatch.setattr(
        predictions_db_mod, "store_prediction",
        lambda ticker, settings, payload: audited.append((ticker, payload)),
    )

    progress = []
    result = kronos_mod.run_kronos_with_cache(
        tickers, progress_callback=lambda c, t, s: progress.append((c, t, s)), audit=True
    )

    assert [fc["symbol"] for fc in result] == tickers
    assert set(saved["kronos"].keys()) == set(tickers)
    assert len(audited) == 2
    assert {t for t, _ in audited} == set(tickers)
    assert len(progress) == 2


def test_run_kronos_with_cache_audit_false_skips_store(monkeypatch, tmp_path):
    """audit=False skips the SQLite audit write (used by dashboard_api)."""
    tickers = ["AAA"]
    forecasts = make_kronos_forecasts(tickers)

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": {}, "gbm": {}
    })
    monkeypatch.setattr(cache_mod, "save_prediction_cache", lambda k, g, date_str=None: tmp_path)
    def fake_portfolio(symbols, lookback=120, pred_len=14, progress_callback=None, on_forecast=None, **kw):
        for fc in forecasts:
            if on_forecast:
                on_forecast(fc)
        return forecasts
    monkeypatch.setattr(kronos_mod, "predict_portfolio", fake_portfolio)
    monkeypatch.setattr(
        predictions_db_mod, "store_prediction",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("audit=False must not store")),
    )

    result = kronos_mod.run_kronos_with_cache(tickers, audit=False)
    assert result == forecasts


def test_run_kronos_with_cache_partial_reuse_only_missing(monkeypatch, tmp_path):
    """Partial cache/audit: reuse covered tickers, compute only the missing one."""
    tickers = ["AAA", "BBB.NS", "CCC.NS"]
    cached_kronos = {fc["symbol"]: fc for fc in make_kronos_forecasts(["AAA", "BBB.NS"])}

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": cached_kronos, "gbm": {}
    })
    monkeypatch.setattr(predictions_db_mod, "load_predictions_by_date", lambda tickers, date_str, settings=None: {})
    monkeypatch.setattr(cache_mod, "save_prediction_cache", lambda k, g, date_str=None: tmp_path)
    monkeypatch.setattr(
        predictions_db_mod, "store_prediction",
        lambda ticker, settings, payload: None,
    )
    called_with = {}
    def fake_portfolio(tickers, lookback=120, pred_len=14, progress_callback=None, on_forecast=None, **kw):
        called_with["tickers"] = list(tickers)
        for fc in make_kronos_forecasts(tickers):
            if on_forecast:
                on_forecast(fc)
        return make_kronos_forecasts(tickers)
    monkeypatch.setattr(kronos_mod, "predict_portfolio", fake_portfolio)

    result = kronos_mod.run_kronos_with_cache(tickers, force=False, audit=True)

    # Only the missing ticker was computed.
    assert called_with["tickers"] == ["CCC.NS"]
    # Result contains all three tickers in order.
    assert [fc["symbol"] for fc in result] == tickers


# ---------------------------------------------------------------------------
# cache-predictions CLI
# ---------------------------------------------------------------------------

def test_cache_predictions_cli_runs_both_engines(tmp_path, monkeypatch):
    """cache-predictions runs GBM + Kronos with progress and saves to cache."""
    tickers = ["AAA"]
    gbm_map = make_gbm_map(tickers)
    forecasts = make_kronos_forecasts(tickers)

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: tickers)
    monkeypatch.setattr(cli_mod, "run_gbm_with_cache", lambda *a, **kw: gbm_map)
    monkeypatch.setattr(cli_mod, "run_kronos_with_cache", lambda *a, **kw: forecasts)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["cache-predictions", "--market", "IN"])

    assert result.exit_code == 0
    assert "Pre-computing predictions for 1 tickers" in result.output
    assert "Running GBM" in result.output
    assert "Running Kronos" in result.output
    assert "GBM: 1 predictions cached" in result.output
    assert "Kronos: 1 predictions cached" in result.output
    assert "upcoming-results --cache-only" in result.output


def test_cache_predictions_cli_no_kronos(tmp_path, monkeypatch):
    """--no-kronos skips the Kronos engine entirely."""
    tickers = ["AAA"]
    gbm_map = make_gbm_map(tickers)

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: tickers)
    monkeypatch.setattr(cli_mod, "run_gbm_with_cache", lambda *a, **kw: gbm_map)
    monkeypatch.setattr(
        cli_mod, "run_kronos_with_cache",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("--no-kronos must not run Kronos")),
    )

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["cache-predictions", "--market", "IN", "--no-kronos"])

    assert result.exit_code == 0
    assert "Running GBM" in result.output
    assert "Running Kronos" not in result.output


def test_cache_predictions_cli_no_gbm(tmp_path, monkeypatch):
    """--no-gbm skips the GBM engine entirely."""
    tickers = ["AAA"]
    forecasts = make_kronos_forecasts(tickers)

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: tickers)
    monkeypatch.setattr(
        cli_mod, "run_gbm_with_cache",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("--no-gbm must not run GBM")),
    )
    monkeypatch.setattr(cli_mod, "run_kronos_with_cache", lambda *a, **kw: forecasts)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["cache-predictions", "--market", "IN", "--no-gbm"])

    assert result.exit_code == 0
    assert "Running GBM" not in result.output
    assert "Running Kronos" in result.output


def test_cache_predictions_cli_both_disabled(tmp_path, monkeypatch):
    """Both --no-kronos and --no-gbm is a no-op with a friendly message."""
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["cache-predictions", "--market", "IN", "--no-kronos", "--no-gbm"])

    assert result.exit_code == 0
    assert "Nothing to do" in result.output


# ---------------------------------------------------------------------------
# upcoming-results --cache-only
# ---------------------------------------------------------------------------

def test_upcoming_results_cache_only_uses_cache_without_recompute(tmp_path, monkeypatch):
    """--cache-only renders from the daily cache and never runs the models."""
    tickers = ["AAA"]
    gbm_map = make_gbm_map(tickers)
    kronos_map = {fc["symbol"]: fc for fc in make_kronos_forecasts(tickers)}

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: tickers)
    monkeypatch.setattr(
        cli_mod.earnings_mod,
        "upcoming_earnings",
        lambda tickers, settings, days=14, source=None, start_date=None: pd.DataFrame([
            {"ticker": "AAA", "earnings_date": pd.Timestamp("2026-08-01")}
        ]),
    )
    monkeypatch.setattr(cli_mod, "enrich_upcoming_results", lambda df: df.assign(
        market_cap=1_000_000_000,
        current_price=100.0,
        week_change=0.05,
        pct_from_52w_high=10.0,
        pct_from_52w_low=5.0,
    ))
    monkeypatch.setattr(cli_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_ENABLED", "false")
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: EmailSettings(enabled=False))

    # The upcoming-results command imports prediction-cache helpers inside its
    # body, so patch the source module (earnings_engine.prediction_cache).
    monkeypatch.setattr(
        cache_mod, "load_prediction_cache",
        lambda tickers, date_str=None: {"kronos": kronos_map, "gbm": gbm_map},
    )
    # The cache-aware runners must NOT run under --cache-only. They are imported
    # at module top of cli.py, so patch cli_mod directly.
    monkeypatch.setattr(
        cli_mod, "run_kronos_with_cache",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("--cache-only must not run Kronos")),
    )
    monkeypatch.setattr(
        cli_mod, "run_gbm_with_cache",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("--cache-only must not run GBM")),
    )

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14", "--cache-only"])

    assert result.exit_code == 0
    assert "Saved CSV" in result.output


# ---------------------------------------------------------------------------
# Report sorting (momentum primary, Kronos/GBM tie-breakers)
# ---------------------------------------------------------------------------

def test_sort_per_day_momentum_primary_kronos_tiebreaks():
    """Same-day rows sort by momentum first, then Kronos 14D return."""
    from earnings_engine.reports.render import _sort_per_day

    df = pd.DataFrame([
        {"ticker": "A.NS", "earnings_date": pd.Timestamp("2026-08-05"),
         "thirty_day_return_pct": 2.0, "earnings_week_move_pct": 1.0,
         "prev_3q_earnings_score": 6, "market_cap": 1e11,
         "kronos_14d": {"return_pct": 5.0},
         "gbm_prediction": {"direction": "UP", "confidence": 0.7}},
        {"ticker": "B.NS", "earnings_date": pd.Timestamp("2026-08-05"),
         "thirty_day_return_pct": 3.0, "earnings_week_move_pct": 1.0,
         "prev_3q_earnings_score": 6, "market_cap": 1e11,
         "kronos_14d": {"return_pct": -2.0},
         "gbm_prediction": {"direction": "DOWN", "confidence": 0.6}},
        {"ticker": "C.NS", "earnings_date": pd.Timestamp("2026-08-05"),
         "thirty_day_return_pct": 3.0, "earnings_week_move_pct": 1.0,
         "prev_3q_earnings_score": 6, "market_cap": 1e11,
         "kronos_14d": {"return_pct": 4.0},
         "gbm_prediction": {"direction": "UP", "confidence": 0.8}},
    ])

    out = _sort_per_day(df)

    # B and C tie on momentum (4.0); C (Kronos +4) beats B (Kronos -2).
    # A has the lowest momentum (3.0) and ranks last despite Kronos +5.
    assert out["ticker"].tolist() == ["C.NS", "B.NS", "A.NS"]


def test_sort_per_day_gbm_tiebreak_after_kronos():
    """GBM direction x confidence breaks ties when momentum and Kronos match."""
    from earnings_engine.reports.render import _sort_per_day

    df = pd.DataFrame([
        {"ticker": "X.NS", "earnings_date": pd.Timestamp("2026-08-05"),
         "thirty_day_return_pct": 1.0, "earnings_week_move_pct": 1.0,
         "prev_3q_earnings_score": 6, "market_cap": 1e11,
         "kronos_14d": {"return_pct": 2.0},
         "gbm_prediction": {"direction": "UP", "confidence": 0.9}},
        {"ticker": "Y.NS", "earnings_date": pd.Timestamp("2026-08-05"),
         "thirty_day_return_pct": 1.0, "earnings_week_move_pct": 1.0,
         "prev_3q_earnings_score": 6, "market_cap": 1e11,
         "kronos_14d": {"return_pct": 2.0},
         "gbm_prediction": {"direction": "DOWN", "confidence": 0.8}},
    ])

    out = _sort_per_day(df)

    # Momentum + Kronos tie; GBM UP(+0.9) beats DOWN(-0.8).
    assert out["ticker"].tolist() == ["X.NS", "Y.NS"]


def test_quarter_week_hl_includes_earnings_date(monkeypatch):
    """_fmt_quarter_week_hl appends the quarter's earnings date when available."""
    from earnings_engine.reports.render import render_upcoming_results_report

    df = pd.DataFrame([
        {
            "ticker": "AAA.NS",
            "earnings_date": pd.Timestamp("2026-08-05"),
            "source": "yfinance",
            "company_name": "AAA Corp",
            "market_cap": 1.5e11,
            "current_price": 100.0,
            "thirty_day_return_pct": 3.0,
            "earnings_week_move_pct": 1.0,
            "prev_3q_earnings_score": 6,
            "q1_earnings_score": 7,
            "q2_earnings_score": 6,
            "q3_earnings_score": 5,
            "q1_week_high_pct": 8.7,
            "q1_week_low_pct": 2.3,
            "q1_week_high_price": 8500.0,
            "q1_week_low_price": 7800.0,
            "q1_week_high_date": "2026-05-16",
            "q1_week_low_date": "2026-05-14",
            "q1_earnings_date": "2026-05-15",
            "q2_week_high_pct": 5.0,
            "q2_week_low_pct": 1.0,
            "q2_week_high_price": 8200.0,
            "q2_week_low_price": 7900.0,
            "q2_week_high_date": "2026-02-13",
            "q2_week_low_date": "2026-02-11",
            "q2_earnings_date": "2026-02-12",
            "kronos_14d": None,
            "gbm_prediction": None,
        }
    ])

    html_path = render_upcoming_results_report(df, csv_path=None, html_path=None)
    html = html_path.read_text(encoding="utf-8")

    # The quarter's earnings date is surfaced in the Q1 + Q2 week H/L cells.
    assert "earn May 15" in html
    assert "earn Feb 12" in html


# ---------------------------------------------------------------------------
# cache-predictions --earnings-only
# ---------------------------------------------------------------------------

def test_cache_predictions_cli_earnings_only_filters_tickers(tmp_path, monkeypatch):
    """--earnings-only filters the ticker list to only stocks with upcoming earnings."""
    all_tickers = ["AAA", "BBB.NS", "CCC.NS", "DDD.NS"]
    earnings_tickers = ["AAA", "CCC.NS"]  # only 2 have upcoming earnings

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: all_tickers)
    monkeypatch.setattr(
        cli_mod.earnings_mod,
        "upcoming_earnings",
        lambda tickers, settings, days=14, source=None, start_date=None: pd.DataFrame([
            {"ticker": "AAA", "earnings_date": pd.Timestamp("2026-08-10")},
            {"ticker": "CCC.NS", "earnings_date": pd.Timestamp("2026-08-12")},
        ]),
    )

    called_with = {}
    def fake_gbm(tickers, settings, days=14, progress_callback=None, force=False):
        called_with["gbm_tickers"] = list(tickers)
        return make_gbm_map(tickers)
    def fake_kronos(tickers, lookback=120, pred_len=14, progress_callback=None, force=False, audit=True, **kw):
        called_with["kronos_tickers"] = list(tickers)
        return make_kronos_forecasts(tickers)

    monkeypatch.setattr(cli_mod, "run_gbm_with_cache", fake_gbm)
    monkeypatch.setattr(cli_mod, "run_kronos_with_cache", fake_kronos)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["cache-predictions", "--market", "NSE_ALL", "--earnings-only", "--days", "14"])

    assert result.exit_code == 0
    # Only the 2 earnings tickers were passed to the engines, not all 4.
    assert called_with["gbm_tickers"] == earnings_tickers
    assert called_with["kronos_tickers"] == earnings_tickers


def test_cache_predictions_cli_earnings_only_no_events(tmp_path, monkeypatch):
    """--earnings-only with no upcoming earnings is a no-op."""
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
    monkeypatch.setattr(
        cli_mod.earnings_mod,
        "upcoming_earnings",
        lambda tickers, settings, days=14, source=None, start_date=None: pd.DataFrame(),
    )

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["cache-predictions", "--market", "NSE_ALL", "--earnings-only"])

    assert result.exit_code == 0
    assert "Nothing to do" in result.output


# ---------------------------------------------------------------------------
# Incremental cache saving (on_forecast callback)
# ---------------------------------------------------------------------------

def test_run_kronos_with_cache_saves_incrementally(monkeypatch, tmp_path):
    """run_kronos_with_cache passes on_forecast to predict_portfolio for incremental saves."""
    tickers = ["AAA", "BBB.NS", "CCC.NS"]
    forecasts = make_kronos_forecasts(tickers)
    saved = {}
    audited = []

    monkeypatch.setattr(cache_mod, "load_prediction_cache_partial", lambda tickers, date_str=None: {
        "kronos": {}, "gbm": {}
    })
    monkeypatch.setattr(
        cache_mod, "save_prediction_cache",
        lambda k, g, date_str=None: saved.update({"kronos": k, "gbm": g}) or tmp_path,
    )
    monkeypatch.setattr(predictions_db_mod, "load_predictions_by_date", lambda tickers, date_str, settings=None: {})

    # Track that on_forecast is called for each forecast.
    on_forecast_calls = []
    def fake_portfolio(symbols, lookback=120, pred_len=14, progress_callback=None, on_forecast=None, **kw):
        for fc in forecasts:
            if on_forecast:
                on_forecast(fc)
                on_forecast_calls.append(fc["symbol"])
        return forecasts

    monkeypatch.setattr(kronos_mod, "predict_portfolio", fake_portfolio)
    monkeypatch.setattr(
        predictions_db_mod, "store_prediction",
        lambda ticker, settings, payload: audited.append((ticker, payload)),
    )

    result = kronos_mod.run_kronos_with_cache(tickers, audit=True)

    # on_forecast was called for each forecast.
    assert on_forecast_calls == tickers
    # All forecasts were audited.
    assert len(audited) == 3
    # Cache was saved (final save).
    assert "kronos" in saved
    assert set(saved["kronos"].keys()) == set(tickers)
    # Result contains all 3 tickers.
    assert [fc["symbol"] for fc in result] == tickers


# ---------------------------------------------------------------------------
# upcoming-results routes through cache-aware runners
# ---------------------------------------------------------------------------

def test_upcoming_results_routes_through_cache_aware_runners(tmp_path, monkeypatch):
    """Without --cache-only, upcoming-results reuses via the cache-aware runners."""
    tickers = ["AAA"]
    gbm_map = make_gbm_map(tickers)
    kronos_map = {fc["symbol"]: fc for fc in make_kronos_forecasts(tickers)}

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: tickers)
    monkeypatch.setattr(
        cli_mod.earnings_mod,
        "upcoming_earnings",
        lambda tickers, settings, days=14, source=None, start_date=None: pd.DataFrame([
            {"ticker": "AAA", "earnings_date": pd.Timestamp("2026-08-01")}
        ]),
    )
    monkeypatch.setattr(cli_mod, "enrich_upcoming_results", lambda df: df.assign(
        market_cap=1_000_000_000,
        current_price=100.0,
        week_change=0.05,
        pct_from_52w_high=10.0,
        pct_from_52w_low=5.0,
    ))
    monkeypatch.setattr(cli_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_ENABLED", "false")
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: EmailSettings(enabled=False))

    # The runners are imported at module top of cli.py; patch them to return
    # cached/audited results without running the models.
    monkeypatch.setattr(cli_mod, "run_kronos_with_cache", lambda *a, **kw: list(kronos_map.values()))
    monkeypatch.setattr(cli_mod, "run_gbm_with_cache", lambda *a, **kw: gbm_map)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    assert "Saved CSV" in result.output
    output_dir = tmp_path / "reports" / "output"
    csv_files = list(output_dir.glob("upcoming-results-*.csv"))
    assert len(csv_files) == 1
    data = pd.read_csv(csv_files[0])
    assert data.iloc[0]["ticker"] == "AAA"
    # The report CSV should contain the Kronos + GBM prediction columns.
    assert "kronos_14d" in data.columns
    assert "gbm_prediction" in data.columns


def test_upcoming_results_cache_only_no_cache_leaves_empty(tmp_path, monkeypatch):
    """--cache-only with no cache leaves predictions empty without error."""
    tickers = ["AAA"]

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: tickers)
    monkeypatch.setattr(
        cli_mod.earnings_mod,
        "upcoming_earnings",
        lambda tickers, settings, days=14, source=None, start_date=None: pd.DataFrame([
            {"ticker": "AAA", "earnings_date": pd.Timestamp("2026-08-01")}
        ]),
    )
    monkeypatch.setattr(cli_mod, "enrich_upcoming_results", lambda df: df.assign(
        market_cap=1_000_000_000,
        current_price=100.0,
        week_change=0.05,
        pct_from_52w_high=10.0,
        pct_from_52w_low=5.0,
    ))
    monkeypatch.setattr(cli_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_ENABLED", "false")
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: EmailSettings(enabled=False))

    # No cache file exists.
    monkeypatch.setattr(cache_mod, "load_prediction_cache", lambda tickers, date_str=None: None)
    # The cache-aware runners must NOT run under --cache-only. They are imported
    # at module top of cli.py, so patch cli_mod directly.
    monkeypatch.setattr(
        cli_mod, "run_kronos_with_cache",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("--cache-only must not run Kronos")),
    )
    monkeypatch.setattr(
        cli_mod, "run_gbm_with_cache",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("--cache-only must not run GBM")),
    )

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14", "--cache-only"])

    assert result.exit_code == 0
    assert "Saved CSV" in result.output
