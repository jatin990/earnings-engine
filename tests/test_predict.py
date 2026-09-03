import os
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner

import earnings_engine.cli as cli_mod
import earnings_engine.predict as predict_mod
from earnings_engine.config import EmailSettings, Settings, load_email_settings
from earnings_engine.data import market_context as market_context_mod
from earnings_engine.logging_utils import get_logger
from earnings_engine.dataset import FEATURE_COLUMNS
from earnings_engine.predict import build_upcoming_events, predict_upcoming
from earnings_engine.reports.render import render_dashboard, render_predictions


def make_prices(days=400, seed=5):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, days)))
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": rng.integers(1e5, 1e6, days).astype(float)},
        index=pd.DatetimeIndex(dates, name="date"),
    )


def make_labeled_dataset(n=300, seed=9):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(0, 1, n) for c in FEATURE_COLUMNS})
    df["n_past_events"] = rng.integers(0, 10, n)
    df["is_in_market"] = rng.integers(0, 2, n)
    ret = rng.normal(0, 0.04, n)
    df["reaction_return"] = ret
    df["label"] = (ret > 0).astype(int)
    df["ticker"] = rng.choice(["AAA", "BBB.NS"], n)
    df["market"] = np.where(df["ticker"].str.endswith(".NS"), "IN", "US")
    df["earnings_date"] = pd.date_range("2019-01-01", periods=n, freq="5D")
    return df


@pytest.fixture
def wired(monkeypatch, tmp_path):
    prices = make_prices()
    future = pd.Timestamp.today().normalize() + pd.Timedelta(days=4)
    earnings = pd.DataFrame({
        "earnings_date": [pd.Timestamp("2024-02-01"), future],
        "eps_estimate": [1.0, 1.2], "eps_reported": [1.1, None], "surprise_pct": [10.0, None],
    })
    dataset = make_labeled_dataset()

    monkeypatch.setattr(predict_mod, "load_prices", lambda t, s: prices)
    monkeypatch.setattr(predict_mod, "load_earnings", lambda t, s: earnings)
    monkeypatch.setattr(
        predict_mod, "upcoming_earnings",
        lambda tickers, s, days=14, start_date=None: pd.DataFrame(
            [{"ticker": t, "earnings_date": future} for t in tickers]
        ),
    )
    monkeypatch.setattr(predict_mod, "load_dataset", lambda: dataset)
    return dataset


def test_build_upcoming_events_schema(wired):
    df = build_upcoming_events(["AAA", "BBB.NS"], Settings())
    assert len(df) == 2
    assert set(FEATURE_COLUMNS).issubset(df.columns)
    assert "label" not in df.columns


def test_predict_upcoming(wired):
    preds = predict_upcoming(["AAA", "BBB.NS"], Settings(), model_name="gbm")
    assert len(preds) == 2
    assert preds["direction"].isin(["UP", "DOWN"]).all()
    assert ((preds["confidence"] >= 0.5) & (preds["confidence"] <= 1.0)).all()
    # Sorted by confidence descending.
    assert preds["confidence"].is_monotonic_decreasing
    # Direction consistent with p_up.
    assert ((preds["p_up"] >= 0.5) == (preds["direction"] == "UP")).all()


def test_render_predictions(wired, tmp_path, monkeypatch):
    import earnings_engine.reports.render as render_mod
    monkeypatch.setattr(render_mod, "OUTPUT_DIR", tmp_path)
    preds = predict_upcoming(["AAA", "BBB.NS"], Settings(), model_name="gbm")
    csv_path, html_path = render_predictions(preds)
    assert csv_path.exists() and html_path.exists()
    html = html_path.read_text()
    assert "AAA" in html and "Direction" in html or "direction" in html
    assert len(pd.read_csv(csv_path)) == 2


def test_render_dashboard(tmp_path, monkeypatch):
    """Test that render_dashboard creates a valid HTML dashboard file."""
    import earnings_engine.reports.render as render_mod
    monkeypatch.setattr(render_mod, "OUTPUT_DIR", tmp_path)
    
    html_path = render_dashboard()
    
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")
    
    # Verify it's valid HTML with key dashboard elements
    assert "<!DOCTYPE html>" in content
    assert "<title>Earnings Engine" in content
    assert "tickerSearch" in content
    assert "autocompleteDropdown" in content
    
    # Verify tab-based layout (Results, Swing, Kronos, Data Coverage, Industries, Buy the Dip, Playground)
    assert "tab-results" in content
    assert "tab-swing" in content
    assert "tab-kronos" in content
    assert "tab-coverage" in content
    assert "tab-industries" in content
    assert "tab-patterns" in content
    assert "tab-buydip" in content
    assert "tab-playground" in content
    
    # Verify widget containers & key table containers
    assert "resultsDatasetSummary" in content or "resultsWidgets" in content
    assert "swingTable" in content or "swingWidgets" in content
    assert "kronosTable" in content or "kronosWidgets" in content

    # Verify the global-only watchlist model (no per-tab watchlist strips) +
    # the Data Coverage / Industries / Buy-the-Dip / Patterns tables
    assert "resultsWatchlistItems" not in content
    assert "tabWatchlists" not in content
    assert "coverageTable" in content
    assert "indGroups" in content
    assert "bdTodayTable" in content
    assert "bdYesterdayTable" in content
    assert "patIndustries" in content
    assert "/api/v1/dashboard/patterns" in content
    
    # Verify results table container
    assert "resultsReportSections" in content or "resultsTable" in content

    # Verify modular architecture and API endpoints
    assert "modules/swing.js" in content or "dashboard/swing" in content
    assert "modules/coverage.js" in content or "coverageTable" in content
    assert "watchlist" in content.lower()
    assert "dashboard.js" in content


def test_cleanup_previous_artifacts_archives_reports_and_prunes_logs(tmp_path):
    output_dir = tmp_path / "reports" / "output"
    archive_dir = tmp_path / "reports" / "archive"
    logs_dir = tmp_path / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Previous-day report (date-stamped) should be moved to archive/.
    (output_dir / "upcoming-results-2026-08-01.csv").write_text("old", encoding="utf-8")
    (output_dir / "upcoming-results-2026-08-01.html").write_text("old", encoding="utf-8")
    # Same-day report should be deleted (the new run regenerates it).
    today = datetime.now().strftime("%Y-%m-%d")
    (output_dir / f"upcoming-results-{today}.csv").write_text("today", encoding="utf-8")
    old_log = logs_dir / "earnings_engine-old.log"
    old_log.write_text("old", encoding="utf-8")
    recent_log = logs_dir / "earnings_engine-recent.log"
    recent_log.write_text("recent", encoding="utf-8")

    old_log_time = old_log.stat().st_mtime - 4 * 24 * 60 * 60
    os.utime(old_log, (old_log_time, old_log_time))

    cli_mod._cleanup_previous_artifacts(tmp_path)

    assert not (output_dir / "upcoming-results-2026-08-01.csv").exists()
    assert not (output_dir / "upcoming-results-2026-08-01.html").exists()
    assert (archive_dir / "upcoming-results-2026-08-01.csv").exists()
    assert (archive_dir / "upcoming-results-2026-08-01.html").exists()
    # Same-day files are kept (keep-last-3 policy) rather than deleted.
    assert (output_dir / f"upcoming-results-{today}.csv").exists()
    assert not old_log.exists()
    assert recent_log.exists()


def test_enrich_upcoming_results_computes_momentum_and_support_levels(monkeypatch):
    # Bypass the once-per-day price-metrics cache so the test always recomputes.
    monkeypatch.setattr(market_context_mod, "load_price_metrics", lambda ticker, settings: None)

    class DummyTicker:
        def __init__(self, ticker):
            self.fast_info = {"market_cap": 1_000_000_000, "last_price": 100.0, "year_high": 110.0, "year_low": 90.0, "year_change": 0.05}
            self.info = {"marketCap": 1_000_000_000, "currentPrice": 100.0, "fiftyTwoWeekHigh": 110.0, "fiftyTwoWeekLow": 90.0}

    prices = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100, 101, 102, 103, 104],
            "volume": [1_000, 1_000, 1_000, 1_000, 1_000],
        },
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )
    earnings = pd.DataFrame(
        {
            "earnings_date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01"), pd.Timestamp("2024-07-01")],
            "surprise_pct": [12.0, 8.0, -3.0],
        }
    )

    monkeypatch.setattr(market_context_mod, "fetch_prices", lambda ticker, settings, force=False: prices)
    monkeypatch.setattr(market_context_mod, "load_earnings", lambda ticker, settings: earnings)
    monkeypatch.setattr(market_context_mod.yf, "Ticker", lambda ticker: DummyTicker(ticker))

    df = pd.DataFrame([{"ticker": "AAA", "earnings_date": pd.Timestamp("2024-08-01")}])
    enriched = market_context_mod.enrich_upcoming_results(df, Settings())

    assert enriched["thirty_day_return_pct"].iloc[0] == pytest.approx(4.0)
    assert enriched["earnings_week_move_pct"].iloc[0] == pytest.approx(4.0)
    # Most recent quarter (Q3) score = 5 (from surprise -3% maps to score 5)
    assert enriched["prev_quarter_earnings_score"].iloc[0] == 5
    assert enriched["next_resistance"].iloc[0] == 104.0
    assert enriched["current_support"].iloc[0] == 100.0


def test_enrich_upcoming_results_handles_empty_prices(monkeypatch):
    """Regression: a ticker with no price data must not crash enrichment.

    ``seven_day_return_pct`` is computed inside the ``len(closes) >= 2`` branch
    and previously had no ``None`` default, so an empty/too-short price history
    (e.g. a delisted ticker whose download failed) left it unbound
    (UnboundLocalError), which dropped the whole row from the upcoming-results
    report.
    """
    monkeypatch.setattr(market_context_mod, "load_price_metrics", lambda ticker, settings: None)
    empty_prices = pd.DataFrame(columns=["close"])
    monkeypatch.setattr(market_context_mod, "fetch_prices", lambda ticker, settings, force=False: empty_prices)
    monkeypatch.setattr(market_context_mod, "load_prices", lambda ticker, settings: empty_prices)

    class DummyTicker:
        def __init__(self, ticker):
            self.fast_info = {"market_cap": 1_000_000_000, "last_price": 100.0,
                              "year_high": 110.0, "year_low": 90.0, "year_change": 0.05}
            self.info = {"marketCap": 1_000_000_000, "currentPrice": 100.0,
                         "fiftyTwoWeekHigh": 110.0, "fiftyTwoWeekLow": 90.0}

    earnings = pd.DataFrame({
        "earnings_date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01"),
                          pd.Timestamp("2024-07-01")],
        "surprise_pct": [12.0, 8.0, -3.0],
    })
    monkeypatch.setattr(market_context_mod, "load_earnings", lambda ticker, settings: earnings)
    monkeypatch.setattr(market_context_mod.yf, "Ticker", lambda ticker: DummyTicker(ticker))

    df = pd.DataFrame([{"ticker": "AAA", "earnings_date": pd.Timestamp("2024-08-01")}])
    enriched = market_context_mod.enrich_upcoming_results(df, Settings())

    assert len(enriched) == 1
    assert enriched["ticker"].iloc[0] == "AAA"
    assert enriched["seven_day_return_pct"].iloc[0] is None
    assert enriched["thirty_day_return_pct"].iloc[0] is None
    assert "earnings_week_move_pct" in enriched.columns


def test_day_color_assignment():
    """Per-day color classes are assigned correctly to distinct earnings dates."""
    from earnings_engine.reports.render import _assign_day_classes, _DAY_COLORS

    df = pd.DataFrame([
        {"ticker": "AAA", "earnings_date": pd.Timestamp("2026-08-04")},
        {"ticker": "BBB", "earnings_date": pd.Timestamp("2026-08-05")},
        {"ticker": "CCC", "earnings_date": pd.Timestamp("2026-08-04")},
    ])
    classes = _assign_day_classes(df)
    assert classes["2026-08-04"] == f"day-0"
    assert classes["2026-08-05"] == f"day-1"
    # Same date gets the same class
    assert classes["2026-08-04"] == classes["2026-08-04"]


def test_per_day_ranking():
    """Per-day ranking sorts each day's sublist best→worst by momentum."""
    from earnings_engine.reports.render import _sort_per_day

    df = pd.DataFrame([
        {"ticker": "WORST", "earnings_date": pd.Timestamp("2026-08-04"),
         "thirty_day_return_pct": -5.0, "earnings_week_move_pct": -2.0,
         "prev_3q_earnings_score": 3, "market_cap": 1e9},
        {"ticker": "BEST", "earnings_date": pd.Timestamp("2026-08-04"),
         "thirty_day_return_pct": 10.0, "earnings_week_move_pct": 5.0,
         "prev_3q_earnings_score": 8, "market_cap": 5e9},
        {"ticker": "MID", "earnings_date": pd.Timestamp("2026-08-04"),
         "thirty_day_return_pct": 2.0, "earnings_week_move_pct": 1.0,
         "prev_3q_earnings_score": 6, "market_cap": 2e9},
        {"ticker": "OTHER_DAY", "earnings_date": pd.Timestamp("2026-08-05"),
         "thirty_day_return_pct": 0.0, "earnings_week_move_pct": 0.0,
         "prev_3q_earnings_score": 5, "market_cap": 1e9},
    ])
    sorted_df = _sort_per_day(df)
    # Day 2026-08-04: BEST (15) > MID (3) > WORST (-7)
    day1 = sorted_df[sorted_df["earnings_date"] == pd.Timestamp("2026-08-04")]
    assert list(day1["ticker"]) == ["BEST", "MID", "WORST"]
    # Day 2026-08-05: only one row
    day2 = sorted_df[sorted_df["earnings_date"] == pd.Timestamp("2026-08-05")]
    assert list(day2["ticker"]) == ["OTHER_DAY"]
    # Days are in chronological order
    assert sorted_df.iloc[0]["earnings_date"] == pd.Timestamp("2026-08-04")
    assert sorted_df.iloc[-1]["earnings_date"] == pd.Timestamp("2026-08-05")


def test_upcoming_results_check_flag_runs_checker(tmp_path, monkeypatch):
    """The --check flag runs the report checker after rendering."""
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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

    # Use a fake checker that returns a known result to avoid DB access.
    from earnings_engine.reports import checker as checker_mod
    from earnings_engine.reports.checker import CheckResult, Inconsistency

    def fake_check(df, settings=None):
        return CheckResult(verified=3, verified_empty=1, inconsistencies=[
            Inconsistency(
                ticker="AAA", field="current_price", report_value=100.0,
                expected_value=110.0, reason="report value differs from the original source",
            )
        ])

    monkeypatch.setattr(checker_mod, "check_report_frame", fake_check)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14", "--check"])

    assert result.exit_code == 0
    assert "Report checker" in result.output
    assert "INCONSISTENCY AAA current_price" in result.output


def test_upcoming_results_start_date_passed_through(tmp_path, monkeypatch):
    """The --start-date option is passed to upcoming_earnings."""
    captured = {}

    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
    monkeypatch.setattr(
        cli_mod.earnings_mod,
        "upcoming_earnings",
        lambda tickers, settings, days=14, source=None, start_date=None: (
            captured.update({"start_date": start_date, "days": days}) or
            pd.DataFrame([{"ticker": "AAA", "earnings_date": pd.Timestamp("2026-08-01")}])
        ),
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

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--start-date", "2026-09-01", "--days", "5"])

    assert result.exit_code == 0
    assert captured["start_date"] == "2026-09-01"
    assert captured["days"] == 5


def test_upcoming_results_renders_ledger_section(tmp_path, monkeypatch):
    import earnings_engine.reports.render as render_mod
    from earnings_engine.reports.render import render_upcoming_results_report

    enriched = pd.DataFrame([
        {
            "ticker": "AAA",
            "company_name": "Alpha Corp",
            "earnings_date": pd.Timestamp("2026-08-01"),
            "market_cap": 1_000_000_000,
            "current_price": 100.0,
            "week_change": 0.05,
            "pct_from_52w_high": 10.0,
            "pct_from_52w_low": 5.0,
            "thirty_day_return_pct": 4.2,
            "earnings_week_move_pct": 3.1,
            "prev_quarter_earnings_score": 7,
            "kronos_14d": {
                "symbol": "AAA",
                "name": "Alpha Corp",
                "current_price": 100.0,
                "projected_close": 105.0,
                "support": 95.0,
                "resistance": 110.0,
                "return_pct": 5.0,
                "trend": "Bullish",
                "explanation": "Alpha Corp shows a constructive 14-day setup with support near 95.",
            },
            "gbm_prediction": {
                "direction": "UP",
                "confidence": 0.62,
                "p_up": 0.62,
                "earnings_date": "2026-08-01",
                "train_events": 300,
            },
        }
    ])
    monkeypatch.setattr(render_mod, "OUTPUT_DIR", tmp_path)

    html_path = render_upcoming_results_report(enriched)
    html = html_path.read_text(encoding="utf-8")
    # New layout: day-wise collapsible sections with cap categorization
    assert "day-section" in html
    assert "2026-08-01" in html
    assert "Large Cap" in html or "Small Cap" in html
    assert "AAA" in html
    assert "Kronos 14D" in html
    assert "GBM" in html

    # Ledger stock cell shows company name
    assert "Alpha Corp" in html

    # Popup modal with Kronos + GBM + Ollama sections
    assert "popup-modal" in html
    assert "Kronos 14-Day Forecast" in html
    assert "GBM Earnings Prediction" in html
    assert "Ollama Analysis" in html
    assert "Setup, Quality & Momentum" in html
    assert "Alpha Corp shows a constructive 14-day setup" in html
    assert "UP 62%" in html


def test_upcoming_results_dedupes_same_stock(tmp_path, monkeypatch):
    """The same stock appearing on multiple earnings dates is merged (earliest kept)."""
    import earnings_engine.reports.render as render_mod
    from earnings_engine.reports.render import render_upcoming_results_report

    enriched = pd.DataFrame([
        {
            "ticker": "AAA",
            "company_name": "Alpha Corp",
            "earnings_date": pd.Timestamp("2026-08-01"),
            "source": "nse",
            "market_cap": 1_000_000_000,
            "current_price": 100.0,
            "week_change": 0.05,
            "pct_from_52w_high": 10.0,
            "pct_from_52w_low": 5.0,
            "thirty_day_return_pct": 4.2,
            "earnings_week_move_pct": 3.1,
            "prev_quarter_earnings_score": 7,
        },
        {
            "ticker": "AAA",
            "company_name": "Alpha Corp",
            "earnings_date": pd.Timestamp("2026-08-05"),
            "source": "yfinance",
            "market_cap": 1_000_000_000,
            "current_price": 102.0,
            "week_change": 0.06,
            "pct_from_52w_high": 11.0,
            "pct_from_52w_low": 6.0,
            "thirty_day_return_pct": 5.0,
            "earnings_week_move_pct": 4.0,
            "prev_quarter_earnings_score": 8,
        },
    ])
    monkeypatch.setattr(render_mod, "OUTPUT_DIR", tmp_path)

    html_path = render_upcoming_results_report(enriched)
    html = html_path.read_text(encoding="utf-8")

    # Only one day section should exist (earliest date kept), one popup, one row
    assert html.count("class=\"day-section\"") == 1
    assert html.count("class=\"popup-modal\"") == 1
    assert "2026-08-01" in html
    assert "2026-08-05" in html  # both dates shown
    assert "2026-08-01 (nse)" in html
    assert "2026-08-05 (yfinance)" in html
    assert html.count("Alpha Corp") >= 2  # appears in ledger row and popup header


def test_upcoming_results_formats_market_cap_quality_and_52w_gaps(tmp_path, monkeypatch):
    """Regression: market cap in Cr, quality as /9, 52W gaps with price, signed percents."""
    import earnings_engine.reports.render as render_mod
    from earnings_engine.reports.render import render_upcoming_results_report

    enriched = pd.DataFrame([
        {
            "ticker": "DIVISLAB.NS",
            "earnings_date": pd.Timestamp("2026-08-01"),
            "market_cap": 2138614792192,          # rupees
            "current_price": 8056.0,
            "week_change": 0.192,
            "pct_from_52w_high": 0.4,             # already ×100
            "pct_from_52w_low": 42.9,
            "thirty_day_return_pct": 19.2,
            "earnings_week_move_pct": 8.7,
            "earnings_week_high_pct": 8.7,
            "earnings_week_low_pct": 0.0,
            "earnings_week_high_price": 8500.0,
            "earnings_week_low_price": 7800.0,
            "week_high": 8090.0,
            "week_low": 5636.5,
            "prev_quarter_earnings_score": 6,
            "prev_3q_earnings_score": 6,
            "q1_earnings_score": 9,
            "q2_earnings_score": 9,
            "q3_earnings_score": 6,
            "q1_week_high_pct": 5.0,
            "q1_week_low_pct": -2.0,
            "q1_week_high_price": 8200.0,
            "q1_week_low_price": 7600.0,
            "q2_week_high_pct": 6.5,
            "q2_week_low_pct": -1.5,
            "q2_week_high_price": 8300.0,
            "q2_week_low_price": 7700.0,
            "q3_week_high_pct": 8.7,
            "q3_week_low_pct": 0.0,
            "q3_week_high_price": 8500.0,
            "q3_week_low_price": 7800.0,
            "next_resistance": 8056.0,
            "current_support": 6727.26,
        }
    ])
    monkeypatch.setattr(render_mod, "OUTPUT_DIR", tmp_path)

    html_path = render_upcoming_results_report(enriched)
    html = html_path.read_text(encoding="utf-8")

    # Market cap in crores (not "k Cr")
    assert "213,861.5 Cr" in html
    assert "k Cr" not in html

    # Quality scores as /9 (not bare numbers)
    assert "6/9" in html

    # 52W gaps with percentages on one line, prices on second line
    assert "+0.4%/+42.9%" in html  # 52W high/low percentages
    assert "(8,090/5,636)" in html  # 52W prices on separate line

    # Week high/low with percentages on one line, prices on second line
    assert "+8.7%/+0.0%" in html  # Q3 week high/low percentages
    assert "(8,500/7,800)" in html  # Q3 prices on separate line
    assert "+6.5%/-1.5%" in html  # Q2 week high/low percentages
    assert "(8,300/7,700)" in html  # Q2 prices on separate line

    # Signed percents
    assert "+19.20%" in html
    assert "+8.70%" in html

    # Quality scores in format "Q1 | Q2 | Q3" (just scores, no prefix)
    assert "9/9 | 9/9 | 6/9" in html

    # 3Q average in separate column
    assert "6/9" in html  # prev_3q_score


def test_upcoming_results_exports_timestamped_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    output_dir = tmp_path / "reports" / "output"
    csv_files = list(output_dir.glob("upcoming-results-*.csv"))
    assert len(csv_files) == 1
    data = pd.read_csv(csv_files[0])
    assert list(data.columns[:2]) == ["ticker", "earnings_date"]
    assert data.iloc[0]["ticker"] == "AAA"


def test_upcoming_results_sends_email_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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
    email_settings = EmailSettings(enabled=True, smtp_host="smtp.test", from_address="from@example.com", to_addresses=("to@example.com",))
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: email_settings)

    sent = {}
    def fake_send(path, settings, body=None, html_path=None):
        sent["path"] = path
        sent["settings"] = settings
        sent["body"] = body
        sent["html_path"] = html_path

    monkeypatch.setattr(cli_mod, "send_report_email", fake_send)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    assert sent["settings"] == email_settings
    assert sent["path"].exists()
    assert sent["body"] == "Attached are the CSV and HTML earnings report."


def test_upcoming_results_writes_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    log_files = list((tmp_path / "logs").glob("earnings_engine-*.log"))
    assert log_files
    assert any("upcoming-results" in path.read_text(encoding="utf-8") for path in log_files)


def test_upcoming_results_generates_html_report_for_email(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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
    email_settings = EmailSettings(enabled=True, smtp_host="smtp.test", from_address="from@example.com", to_addresses=("to@example.com",))
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: email_settings)

    captured = {}
    def fake_send(path, settings, body=None, html_path=None):
        captured["path"] = path
        captured["settings"] = settings
        captured["body"] = body
        captured["html_path"] = html_path

    monkeypatch.setattr(cli_mod, "send_report_email", fake_send)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    assert captured["html_path"] is not None
    assert captured["html_path"].exists()


def test_upcoming_results_sends_email_when_smtp_config_present(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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
    email_settings = EmailSettings(enabled=False, smtp_host="smtp.test", from_address="from@example.com", to_addresses=("to@example.com",))
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: email_settings)

    called = {}
    def fake_send(path, settings, body=None, html_path=None):
        called["path"] = path
        called["settings"] = settings

    monkeypatch.setattr(cli_mod, "send_report_email", fake_send)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    assert called["path"].exists()
    assert called["settings"] == email_settings


def test_load_email_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_PORT", "2525")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_USERNAME", "demo")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_TO", "first@example.com; second@example.com")

    settings = load_email_settings()

    assert settings.enabled is True
    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 2525
    assert settings.smtp_username == "demo"
    assert settings.smtp_password == "secret"
    assert settings.from_address == "sender@example.com"
    assert settings.to_addresses == ("first@example.com", "second@example.com")


def test_quality_score_last_quarter_is_last_element():
    """Regression: last quarter score must be the most recent quarter's score,
    not an average across multiple quarters."""
    from earnings_engine.data.market_context import _score_surprise

    # Last quarter weak (2% → 6), prior quarters strong (20% → 9, 18% → 9)
    earnings = pd.DataFrame({
        "earnings_date": pd.to_datetime(["2026-01-01", "2026-04-01", "2026-07-01"]),
        "surprise_pct": [20.0, 18.0, 2.0],
    })

    # Individual quarter scores: [20%→9, 18%→9, 2%→6]
    # Last quarter (most recent) = 6
    recent = earnings.sort_values("earnings_date").tail(1)
    surprises = pd.to_numeric(recent.get("surprise_pct", pd.Series([0])), errors="coerce").fillna(0)
    scores = [_score_surprise(float(s)) for s in surprises]
    assert scores[-1] == 6

    # Verify individual scoring function
    assert _score_surprise(20.0) == 9
    assert _score_surprise(18.0) == 9
    assert _score_surprise(2.0) == 6


def test_upcoming_results_writes_log_file(tmp_path, monkeypatch):
    monkeypatch.delenv("EARNINGS_ENGINE_DISABLE_FILE_LOGGING", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    log_files = list((tmp_path / "logs").glob("earnings_engine-*.log"))
    assert log_files
    assert any("upcoming-results" in path.read_text(encoding="utf-8") for path in log_files)


def test_upcoming_results_generates_html_report_for_email(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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
    email_settings = EmailSettings(enabled=True, smtp_host="smtp.test", from_address="from@example.com", to_addresses=("to@example.com",))
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: email_settings)

    captured = {}
    def fake_send(path, settings, body=None, html_path=None):
        captured["path"] = path
        captured["settings"] = settings
        captured["body"] = body
        captured["html_path"] = html_path

    monkeypatch.setattr(cli_mod, "send_report_email", fake_send)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    assert captured["html_path"] is not None
    assert captured["html_path"].exists()


def test_upcoming_results_sends_email_when_smtp_config_present(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "Settings", lambda: Settings())
    monkeypatch.setattr(cli_mod, "_resolve_tickers", lambda market, ticker, universe_file=None: ["AAA"])
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
    email_settings = EmailSettings(enabled=False, smtp_host="smtp.test", from_address="from@example.com", to_addresses=("to@example.com",))
    monkeypatch.setattr(cli_mod, "load_email_settings", lambda: email_settings)

    called = {}
    def fake_send(path, settings, body=None, html_path=None):
        called["path"] = path
        called["settings"] = settings

    monkeypatch.setattr(cli_mod, "send_report_email", fake_send)

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["upcoming-results", "--market", "IN", "--days", "14"])

    assert result.exit_code == 0
    assert called["path"].exists()
    assert called["settings"] == email_settings


def test_load_email_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_PORT", "2525")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_USERNAME", "demo")
    monkeypatch.setenv("EARNINGS_ENGINE_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("EARNINGS_ENGINE_EMAIL_TO", "first@example.com; second@example.com")

    settings = load_email_settings()

    assert settings.enabled is True
    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 2525
    assert settings.smtp_username == "demo"
    assert settings.smtp_password == "secret"
    assert settings.from_address == "sender@example.com"
    assert settings.to_addresses == ("first@example.com", "second@example.com")


def test_quality_score_last_quarter_is_last_element():
    """Regression: last quarter score must be the most recent quarter's score,
    not an average across multiple quarters."""
    from earnings_engine.data.market_context import _score_surprise

    # Last quarter weak (2% → 6), prior quarters strong (20% → 9, 18% → 9)
    earnings = pd.DataFrame({
        "earnings_date": pd.to_datetime(["2026-01-01", "2026-04-01", "2026-07-01"]),
        "surprise_pct": [20.0, 18.0, 2.0],
    })

    # Individual quarter scores: [20%→9, 18%→9, 2%→6]
    # Last quarter (most recent) = 6
    recent = earnings.sort_values("earnings_date").tail(1)
    surprises = pd.to_numeric(recent.get("surprise_pct", pd.Series([0])), errors="coerce").fillna(0)
    scores = [_score_surprise(float(s)) for s in surprises]
    assert scores[-1] == 6

    # Verify individual scoring function
    assert _score_surprise(20.0) == 9
    assert _score_surprise(18.0) == 9
    assert _score_surprise(2.0) == 6


def test_enrich_upcoming_results_adds_last_quarter_score_and_week_hl(monkeypatch):
    """Regression: last quarter score and week high/low from last earnings date."""
    # Bypass the once-per-day price-metrics cache so the test always recomputes.
    monkeypatch.setattr(market_context_mod, "load_price_metrics", lambda ticker, settings: None)

    class DummyTicker:
        def __init__(self, ticker):
            self.fast_info = {"market_cap": 1_000_000_000, "last_price": 100.0, "year_high": 110.0, "year_low": 90.0, "year_change": 0.05}
            self.info = {"marketCap": 1_000_000_000, "currentPrice": 100.0, "fiftyTwoWeekHigh": 110.0, "fiftyTwoWeekLow": 90.0}

    # Prices spanning the earnings dates with a clear high/low around each
    dates = pd.bdate_range("2024-01-01", periods=200)
    closes = [100.0] * len(dates)
    # Add a spike around 2024-07-01 (last quarter earnings)
    for i, d in enumerate(dates):
        if pd.Timestamp("2024-06-27") <= d <= pd.Timestamp("2024-07-05"):
            closes[i] = 120.0
    prices = pd.DataFrame(
        {"open": closes, "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
         "close": closes, "volume": [1_000] * len(dates)},
        index=pd.DatetimeIndex(dates, name="date"),
    )
    earnings = pd.DataFrame(
        {
            "earnings_date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01"), pd.Timestamp("2024-07-01")],
            "surprise_pct": [20.0, 18.0, 2.0],
        }
    )

    monkeypatch.setattr(market_context_mod, "fetch_prices", lambda ticker, settings, force=False: prices)
    monkeypatch.setattr(market_context_mod, "load_earnings", lambda ticker, settings: earnings)
    monkeypatch.setattr(market_context_mod.yf, "Ticker", lambda ticker: DummyTicker(ticker))

    df = pd.DataFrame([{"ticker": "AAA", "earnings_date": pd.Timestamp("2024-08-01")}])
    enriched = market_context_mod.enrich_upcoming_results(df, Settings())

    # Last quarter score = most recent quarter (2% → 6)
    assert enriched["prev_quarter_earnings_score"].iloc[0] == 6
    # Last quarter week high/low computed from last earnings date (±4 business days)
    # Last earnings (2024-07-01) has spike to 120, so should have positive high_pct
    assert enriched["last_week_high_pct"].iloc[0] is not None
    assert enriched["last_week_high_price"].iloc[0] == pytest.approx(121.2, rel=1e-2)


def test_enrich_upcoming_results_adds_individual_quarter_scores_and_week_hl(monkeypatch):
    """Regression: per-quarter scores + week high/low are restored for Q1/Q2/Q3."""
    # Bypass the once-per-day price-metrics cache so the test always recomputes.
    monkeypatch.setattr(market_context_mod, "load_price_metrics", lambda ticker, settings: None)

    class DummyTicker:
        def __init__(self, ticker):
            self.fast_info = {"market_cap": 1_000_000_000, "last_price": 100.0, "year_high": 110.0, "year_low": 90.0, "year_change": 0.05}
            self.info = {"marketCap": 1_000_000_000, "currentPrice": 100.0, "fiftyTwoWeekHigh": 110.0, "fiftyTwoWeekLow": 90.0}

    # Prices spanning the earnings dates with a clear high/low around each.
    # Start before Q1's earnings so _week_high_low_around has a base close.
    dates = pd.bdate_range("2023-12-01", periods=200)
    closes = [100.0] * len(dates)
    # Add spikes around each quarter's earnings date
    for i, d in enumerate(dates):
        if pd.Timestamp("2024-01-01") <= d <= pd.Timestamp("2024-01-09"):
            closes[i] = 110.0
        elif pd.Timestamp("2024-04-01") <= d <= pd.Timestamp("2024-04-09"):
            closes[i] = 120.0
        elif pd.Timestamp("2024-07-01") <= d <= pd.Timestamp("2024-07-09"):
            closes[i] = 130.0
    prices = pd.DataFrame(
        {"open": closes, "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
         "close": closes, "volume": [1_000] * len(dates)},
        index=pd.DatetimeIndex(dates, name="date"),
    )
    earnings = pd.DataFrame(
        {
            "earnings_date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01"), pd.Timestamp("2024-07-01")],
            "surprise_pct": [20.0, 18.0, 2.0],
        }
    )

    monkeypatch.setattr(market_context_mod, "fetch_prices", lambda ticker, settings, force=False: prices)
    monkeypatch.setattr(market_context_mod, "load_earnings", lambda ticker, settings: earnings)
    monkeypatch.setattr(market_context_mod.yf, "Ticker", lambda ticker: DummyTicker(ticker))

    df = pd.DataFrame([{"ticker": "AAA", "earnings_date": pd.Timestamp("2024-08-01")}])
    enriched = market_context_mod.enrich_upcoming_results(df, Settings())

    # Individual quarter scores with Q1 = MOST recent quarter:
    #   Q1 (2024-07-01) has 2% → 6
    #   Q2 (2024-04-01) has 18% → 9
    #   Q3 (2024-01-01) has 20% → 9
    assert enriched["q1_earnings_score"].iloc[0] == 6
    assert enriched["q2_earnings_score"].iloc[0] == 9
    assert enriched["q3_earnings_score"].iloc[0] == 9
    # 3Q average = round((6+9+9)/3) = 8, capped at max individual (9)
    assert enriched["prev_3q_earnings_score"].iloc[0] == 8
    # Last quarter score = most recent quarter (2% → 6)
    assert enriched["prev_quarter_earnings_score"].iloc[0] == 6

    # Per-quarter week high/low computed from each quarter's earnings date (±4 business days)
    # Q1 (2024-07-01) has spike to 130 * 1.01 = 131.3
    assert enriched["q1_week_high_pct"].iloc[0] is not None
    assert enriched["q1_week_high_price"].iloc[0] == pytest.approx(131.3, rel=1e-2)
    # Q2 (2024-04-01) has spike to 120 * 1.01 = 121.2
    assert enriched["q2_week_high_pct"].iloc[0] is not None
    assert enriched["q2_week_high_price"].iloc[0] == pytest.approx(121.2, rel=1e-2)
    # Q3 (2024-01-01) has spike to 110 * 1.01 = 111.1
    assert enriched["q3_week_high_pct"].iloc[0] is not None
    assert enriched["q3_week_high_price"].iloc[0] == pytest.approx(111.1, rel=1e-2)
    # Last week high/low mirrors Q1 (most recent)
    assert enriched["last_week_high_price"].iloc[0] == pytest.approx(131.3, rel=1e-2)


def test_enrich_upcoming_results_excludes_upcoming_event_from_quarters(monkeypatch):
    """Regression: the upcoming earnings event (e.g. +4d) must NOT leak into the
    Q1/Q2/Q3 quarter breakdown — only PAST earnings events contribute to the
    quarter scores, week-high/low, and price-after-earnings."""
    # Bypass the once-per-day price-metrics cache so the test always recomputes.
    monkeypatch.setattr(market_context_mod, "load_price_metrics", lambda ticker, settings: None)

    class DummyTicker:
        def __init__(self, ticker):
            self.fast_info = {"market_cap": 1_000_000_000, "last_price": 100.0, "year_high": 110.0, "year_low": 90.0, "year_change": 0.05}
            self.info = {"marketCap": 1_000_000_000, "currentPrice": 100.0, "fiftyTwoWeekHigh": 110.0, "fiftyTwoWeekLow": 90.0}

    # Prices spanning the earnings dates with a clear high/low around each.
    dates = pd.bdate_range("2023-12-01", periods=200)
    closes = [100.0] * len(dates)
    for i, d in enumerate(dates):
        if pd.Timestamp("2024-01-01") <= d <= pd.Timestamp("2024-01-09"):
            closes[i] = 110.0
        elif pd.Timestamp("2024-04-01") <= d <= pd.Timestamp("2024-04-09"):
            closes[i] = 120.0
        elif pd.Timestamp("2024-07-01") <= d <= pd.Timestamp("2024-07-09"):
            closes[i] = 130.0
    prices = pd.DataFrame(
        {"open": closes, "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
         "close": closes, "volume": [1_000] * len(dates)},
        index=pd.DatetimeIndex(dates, name="date"),
    )

    # Earnings include 3 PAST quarters + 1 UPCOMING event (+4d from today).
    # The upcoming event has surprise_pct=None (no result yet).
    upcoming = pd.Timestamp.today().normalize() + pd.Timedelta(days=4)
    earnings = pd.DataFrame(
        {
            "earnings_date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01"),
                              pd.Timestamp("2024-07-01"), upcoming],
            "surprise_pct": [20.0, 18.0, 2.0, None],
        }
    )

    monkeypatch.setattr(market_context_mod, "fetch_prices", lambda ticker, settings, force=False: prices)
    monkeypatch.setattr(market_context_mod, "load_earnings", lambda ticker, settings: earnings)
    monkeypatch.setattr(market_context_mod.yf, "Ticker", lambda ticker: DummyTicker(ticker))

    df = pd.DataFrame([{"ticker": "AAA", "earnings_date": upcoming}])
    enriched = market_context_mod.enrich_upcoming_results(df, Settings())

    # Q1 = most recent PAST quarter (2024-07-01, surprise 2% → score 6).
    # The upcoming event must NOT be Q1 — if it leaked, Q1 would be None
    # (no surprise yet) and the week-high/low would reflect the pre-earnings move.
    assert enriched["q1_earnings_score"].iloc[0] == 6
    assert enriched["q1_earnings_date"].iloc[0] == pd.Timestamp("2024-07-01")
    assert enriched["q1_week_high_price"].iloc[0] == pytest.approx(131.3, rel=1e-2)  # spike around 2024-07-01
    # Q2 = middle past quarter (2024-04-01, surprise 18% → score 9)
    assert enriched["q2_earnings_score"].iloc[0] == 9
    assert enriched["q2_earnings_date"].iloc[0] == pd.Timestamp("2024-04-01")
    # Q3 = oldest past quarter (2024-01-01, surprise 20% → score 9)
    assert enriched["q3_earnings_score"].iloc[0] == 9
    assert enriched["q3_earnings_date"].iloc[0] == pd.Timestamp("2024-01-01")
    # Last quarter = most recent PAST quarter (2% → 6), NOT the upcoming event
    assert enriched["prev_quarter_earnings_score"].iloc[0] == 6


def test_enrich_upcoming_results_adds_earnings_context(monkeypatch):
    # Bypass the once-per-day price-metrics cache so the test always recomputes.
    monkeypatch.setattr(market_context_mod, "load_price_metrics", lambda ticker, settings: None)

    df = pd.DataFrame([{"ticker": "AAA", "earnings_date": pd.Timestamp("2026-08-01")}])
    prices = pd.DataFrame(
        {"close": [100.0, 105.0, 110.0]},
        index=pd.to_datetime(["2026-07-01", "2026-07-15", "2026-07-31"]),
    )
    earnings = pd.DataFrame(
        [{"earnings_date": pd.Timestamp("2026-07-15"), "surprise_pct": 20.0}]
    )

    monkeypatch.setattr(market_context_mod, "load_prices", lambda ticker, settings: prices)
    monkeypatch.setattr(market_context_mod, "load_earnings", lambda ticker, settings: earnings)

    class DummyTicker:
        fast_info = {"market_cap": 1_000_000_000, "last_price": 110.0, "year_high": 120.0, "year_low": 90.0, "year_change": 0.05}

    monkeypatch.setattr(market_context_mod.yf, "Ticker", lambda ticker: DummyTicker())

    enriched = market_context_mod.enrich_upcoming_results(df, settings=Settings())

    assert enriched["thirty_day_return_pct"].iloc[0] > 0
    assert enriched["earnings_week_move_pct"].iloc[0] > 0
    assert enriched["prev_quarter_earnings_score"].iloc[0] == 9


def test_email_logging_writes_to_run_log(tmp_path, monkeypatch):
    monkeypatch.delenv("EARNINGS_ENGINE_DISABLE_FILE_LOGGING", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    from earnings_engine import emailing

    logger = get_logger("earnings_engine.emailing", base_dir=tmp_path)
    monkeypatch.setattr(emailing, "get_logger", lambda name: logger)

    class DummySettings:
        enabled = True
        smtp_host = "smtp.test"
        smtp_port = 25
        smtp_username = ""
        smtp_password = ""
        from_address = "from@example.com"
        to_addresses = ("to@example.com",)

    monkeypatch.setattr(emailing.smtplib, "SMTP", lambda *args, **kwargs: DummySMTP())

    class DummySMTP:
        def __init__(self, *args, **kwargs):
            self.sent = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            return None

        def login(self, *args, **kwargs):
            return None

        def send_message(self, message):
            self.sent = True

    dummy_report = tmp_path / "report.csv"
    dummy_report.write_text("header1,header2\n1,2", encoding="utf-8")
    emailing.send_report_email(dummy_report, DummySettings())

    log_files = list((tmp_path / "logs").glob("earnings_engine-*.log"))
    assert log_files
    assert any("Email delivery is disabled" not in path.read_text(encoding="utf-8") for path in log_files)
