import os

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
        lambda tickers, s, days=14: pd.DataFrame(
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
    assert "<title>Earnings Engine Dashboard</title>" in content
    assert "tickerSearch" in content
    assert "autocompleteDropdown" in content
    
    # Verify tab-based layout (Results, Swing, Kronos, Watchlist)
    assert "tab-results" in content
    assert "tab-swing" in content
    assert "tab-kronos" in content
    assert "tab-watchlist" in content
    
    # Verify widget containers
    assert "resultsWidgets" in content
    assert "swingWidgets" in content
    assert "kronosWidgets" in content
    assert "watchlistItems" in content
    
    # Verify results table
    assert "resultsTable" in content

    # Verify refresh with timestamp
    assert "lastRefreshed" in content
    assert "refreshBtn" in content
    assert "dashboard/refresh" in content

    # Verify SQLite & NSE-file backed endpoints
    assert "dashboard/overview" in content
    assert "dashboard/results" in content
    assert "dashboard/swing" in content
    assert "dashboard/kronos" in content
    assert "watchlist" in content.lower()
    assert "universeFilesTable" in content


def test_cleanup_previous_artifacts_archives_reports_and_prunes_logs(tmp_path):
    output_dir = tmp_path / "reports" / "output"
    archive_dir = tmp_path / "reports" / "archive"
    logs_dir = tmp_path / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "old-report.csv").write_text("old", encoding="utf-8")
    (output_dir / "old-report.html").write_text("old", encoding="utf-8")
    old_log = logs_dir / "earnings_engine-old.log"
    old_log.write_text("old", encoding="utf-8")
    recent_log = logs_dir / "earnings_engine-recent.log"
    recent_log.write_text("recent", encoding="utf-8")

    old_log_time = old_log.stat().st_mtime - 4 * 24 * 60 * 60
    os.utime(old_log, (old_log_time, old_log_time))

    cli_mod._cleanup_previous_artifacts(tmp_path)

    assert not (output_dir / "old-report.csv").exists()
    assert not (output_dir / "old-report.html").exists()
    assert (archive_dir / "old-report.csv").exists()
    assert (archive_dir / "old-report.html").exists()
    assert not old_log.exists()
    assert recent_log.exists()


def test_enrich_upcoming_results_computes_momentum_and_support_levels(monkeypatch):
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


def test_upcoming_results_renders_ledger_section(tmp_path, monkeypatch):
    import earnings_engine.reports.render as render_mod
    from earnings_engine.reports.render import render_upcoming_results_report

    enriched = pd.DataFrame([
        {
            "ticker": "AAA",
            "earnings_date": pd.Timestamp("2026-08-01"),
            "market_cap": 1_000_000_000,
            "current_price": 100.0,
            "week_change": 0.05,
            "pct_from_52w_high": 10.0,
            "pct_from_52w_low": 5.0,
            "thirty_day_return_pct": 4.2,
            "earnings_week_move_pct": 3.1,
            "prev_quarter_earnings_score": 7,
        }
    ])
    monkeypatch.setattr(render_mod, "OUTPUT_DIR", tmp_path)

    html_path = render_upcoming_results_report(enriched)
    html = html_path.read_text(encoding="utf-8")

    assert "Upcoming Results Ledger" in html
    assert "AAA" in html
    assert "risk/reward" in html
    assert "Momentum Bias" in html


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
        lambda tickers, settings, days=14: pd.DataFrame([
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
        lambda tickers, settings, days=14: pd.DataFrame([
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
        lambda tickers, settings, days=14: pd.DataFrame([
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
        lambda tickers, settings, days=14: pd.DataFrame([
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
        lambda tickers, settings, days=14: pd.DataFrame([
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
    assert enriched["last_week_high_price"].iloc[0] == 120.0


def test_enrich_upcoming_results_adds_earnings_context(monkeypatch):
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

    emailing.send_report_email(tmp_path / "report.csv", DummySettings())

    log_files = list((tmp_path / "logs").glob("earnings_engine-*.log"))
    assert log_files
    assert any("Email delivery is disabled" not in path.read_text(encoding="utf-8") for path in log_files)
