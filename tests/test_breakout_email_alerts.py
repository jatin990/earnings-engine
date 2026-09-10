import pytest
import sqlite3
import pandas as pd
from unittest.mock import MagicMock, patch
from earnings_engine.config import Settings, EmailSettings, load_email_settings
from earnings_engine.emailing import send_breakout_alert_email, send_hourly_breakout_digest_email
from earnings_engine.data.breakout_scanner import (
    record_breakout_transition,
    set_ticker_tier,
    compute_technical_decision_metrics,
    _pool,
)
from earnings_engine.data.migrations import apply_migrations


def test_load_email_settings_aliases(monkeypatch):
    for key in (
        "EARNINGS_ENGINE_EMAIL_ENABLED",
        "EARNINGS_ENGINE_SMTP_HOST",
        "EARNINGS_ENGINE_SMTP_PORT",
        "EARNINGS_ENGINE_SMTP_USERNAME",
        "EARNINGS_ENGINE_SMTP_PASSWORD",
        "EARNINGS_ENGINE_EMAIL_FROM",
        "EARNINGS_ENGINE_EMAIL_TO",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("BREAKOUT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.office365.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "trader@nexusquant.com")
    monkeypatch.setenv("SMTP_PASS", "secure_secret_pass")
    monkeypatch.setenv("DEFAULT_FROM_EMAIL", "alerts@nexusquant.com")
    monkeypatch.setenv("BREAKOUT_ALERT_EMAILS", "desk1@nexus.com, desk2@nexus.com; risk@nexus.com")

    settings = load_email_settings()
    assert settings.enabled is True
    assert settings.smtp_host == "smtp.office365.com"
    assert settings.smtp_port == 587
    assert settings.smtp_username == "trader@nexusquant.com"
    assert settings.smtp_password == "secure_secret_pass"
    assert settings.from_address == "alerts@nexusquant.com"
    assert len(settings.to_addresses) == 3
    assert "desk1@nexus.com" in settings.to_addresses
    assert "desk2@nexus.com" in settings.to_addresses
    assert "risk@nexus.com" in settings.to_addresses


def test_send_breakout_alert_email_disabled():
    settings = EmailSettings(
        enabled=False,
        smtp_host="smtp.gmail.com",
        smtp_username="user@gmail.com",
        from_address="user@gmail.com",
        to_addresses=("recipient@gmail.com",),
    )
    result = send_breakout_alert_email(
        ticker="TCS.NS",
        company_name="Tata Consultancy Services",
        settings=settings,
        sync=True,
    )
    assert result is False


def test_send_breakout_alert_email_sync_delivery(monkeypatch):
    settings = EmailSettings(
        enabled=True,
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_username="bot@test.com",
        smtp_password="test_password",
        from_address="bot@test.com",
        to_addresses=("portfolio-manager@test.com", "analyst@test.com"),
    )

    sent_messages = []

    class MockSMTP:
        def __init__(self, host, port, timeout=15):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            sent_messages.append(msg)

    monkeypatch.setattr("smtplib.SMTP", MockSMTP)

    res = send_breakout_alert_email(
        ticker="TATAMOTORS.NS",
        company_name="Tata Motors Ltd",
        strategy="NSE Delivery",
        tier="HOT",
        event_type="PROMOTED_HOT",
        composite_score=88.5,
        current_price=980.0,
        trigger_price=995.0,
        target_price=1080.0,
        stop_loss=940.0,
        risk_reward_ratio=2.5,
        volume_ratio=3.4,
        reason="Institutional accumulation with 3.4x delivery surge clearing 52W resistance",
        catalyst_impact="Q2 Earnings Beat + Commercial Vehicle Expansion",
        settings=settings,
        sync=True,
    )

    assert res is True
    assert len(sent_messages) == 1
    msg = sent_messages[0]

    # Verify headers and recipients
    assert msg["From"] == "bot@test.com"
    assert "portfolio-manager@test.com" in msg["To"]
    assert "analyst@test.com" in msg["To"]
    assert "TATAMOTORS.NS" in msg["Subject"]
    assert "HOT" in msg["Subject"]
    assert "88.5" in msg["Subject"]

    # Verify body contents
    body_text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "TATAMOTORS.NS (Tata Motors Ltd)" in body_text
    assert "NSE Delivery" in body_text
    assert "₹980.00" in body_text
    assert "₹995.00" in body_text
    assert "₹1,080.00" in body_text
    assert "₹940.00" in body_text
    assert "2.50 : 1" in body_text
    assert "3.40x" in body_text
    assert "Institutional accumulation" in body_text
    assert "Commercial Vehicle Expansion" in body_text

    # Verify HTML alternative
    html_part = msg.get_body(preferencelist=("html",)).get_content()
    assert "#07090e" in html_part
    assert "HIGH CONVICTION HOT BREAKOUT" in html_part
    assert "Tata Motors Ltd" in html_part
    assert "TATAMOTORS.NS" in html_part
    assert "Inspect Stock Intelligence Hub" in html_part


def test_record_breakout_transition_email_integration(tmp_path, monkeypatch):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "test.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.migrations.get_db_connection", db_conn_fn)
    apply_migrations(settings)

    dispatched_emails = []

    def mock_send_email(**kwargs):
        dispatched_emails.append(kwargs)
        return True

    monkeypatch.setattr("earnings_engine.emailing.send_breakout_alert_email", mock_send_email)

    ticker = "RELIANCE.NS"

    # Event 1: First promotion to HOT -> Should trigger email alert!
    record_breakout_transition(
        ticker=ticker,
        event_type="PROMOTED_HOT",
        from_tier="WARM",
        to_tier="HOT",
        score_before=68.0,
        score_after=86.0,
        price=3000.0,
        trigger_price=3020.0,
        target_price=3250.0,
        stop_loss=2900.0,
        risk_reward_ratio=2.5,
        volume_ratio=2.2,
        reason="Heavy compression breakout above resistance",
        strategy="Classic Technical",
        company_name="Reliance Industries Ltd",
        settings=settings,
        send_email=True,
        sync_email=True,
    )

    assert len(dispatched_emails) == 1
    assert dispatched_emails[0]["ticker"] == "RELIANCE.NS"
    assert dispatched_emails[0]["tier"] == "HOT"
    assert dispatched_emails[0]["composite_score"] == 86.0
    assert dispatched_emails[0]["current_price"] == 3000.0

    # Event 2: Consecutive duplicate scan -> Increments counter, does NOT send duplicate spam email
    record_breakout_transition(
        ticker=ticker,
        event_type="PROMOTED_HOT",
        from_tier="WARM",
        to_tier="HOT",
        score_after=87.0,
        price=3005.0,
        strategy="Classic Technical",
        settings=settings,
        send_email=True,
        sync_email=True,
    )

    # Count of dispatched emails should still be 1!
    assert len(dispatched_emails) == 1


def test_set_ticker_tier_triggers_email(tmp_path, monkeypatch):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "test.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.migrations.get_db_connection", db_conn_fn)
    apply_migrations(settings)

    _pool["hot"].clear()
    _pool["warm"].clear()

    dispatched_emails = []

    def mock_send_email(**kwargs):
        dispatched_emails.append(kwargs)
        return True

    monkeypatch.setattr("earnings_engine.emailing.send_breakout_alert_email", mock_send_email)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.evaluate_stock_breakout", lambda t, **kw: {
        "success": True,
        "ticker": t,
        "company_name": "Infosys Limited",
        "current_price": 1800.0,
        "breakout_trigger": 1820.0,
        "target_price": 1980.0,
        "stop_loss": 1720.0,
        "risk_reward_ratio": 2.25,
        "volume_ratio": 1.8,
        "composite_score": 84.0,
        "strategy": "Classic Technical",
    })

    # Manually promote INFY.NS to hot
    res = set_ticker_tier("INFY.NS", "hot", settings=settings)
    assert res["success"] is True

    # Check that alert was recorded and email dispatched
    assert len(dispatched_emails) == 1
    assert dispatched_emails[0]["ticker"] == "INFY.NS"
    assert dispatched_emails[0]["tier"] == "HOT"
    assert dispatched_emails[0]["composite_score"] == 84.0


def test_compute_technical_decision_metrics():
    # Construct synthetic OHLCV dataframe (60 bars)
    dates = pd.date_range("2026-01-01", periods=60, freq="B")
    # Base uptrend price from 100 to 160
    closes = [100.0 + i * 1.0 for i in range(60)]
    highs = [c + 2.0 for c in closes]
    lows = [c - 2.0 for c in closes]
    volumes = [100000 + (1000000 if i == 59 else 0) for i in range(60)]

    df = pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
    }, index=dates)

    metrics = compute_technical_decision_metrics("SYNTHETIC.NS", prices_df=df)
    assert metrics["sma_20"] is not None
    assert metrics["sma_50"] is not None
    assert metrics["dist_sma_20_pct"] is not None
    assert metrics["dist_sma_20_pct"] > 0
    assert "Bullish" in metrics["trend_alignment"]
    assert metrics["high_52w"] == highs[-1]
    assert metrics["dist_52w_high_pct"] <= 0
    assert metrics["rsi_14"] is not None
    assert metrics["volume_surge_ratio"] is not None
    assert metrics["volume_surge_ratio"] > 1.0
    assert metrics["ret_30d_pct"] is not None


def test_send_breakout_alert_email_with_technical_data(monkeypatch):
    settings = EmailSettings(
        enabled=True,
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_username="bot@test.com",
        smtp_password="test_password",
        from_address="bot@test.com",
        to_addresses=("trader@test.com",),
    )

    sent_messages = []

    class MockSMTP:
        def __init__(self, host, port, timeout=15):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            sent_messages.append(msg)

    monkeypatch.setattr("smtplib.SMTP", MockSMTP)

    tech_data = {
        "sma_20": 950.0,
        "sma_50": 920.0,
        "sma_200": 850.0,
        "dist_sma_20_pct": 3.16,
        "dist_sma_50_pct": 6.52,
        "dist_sma_200_pct": 15.29,
        "trend_alignment": "Bullish Golden Stack (P > 20 > 50 > 200)",
        "high_52w": 1000.0,
        "low_52w": 750.0,
        "dist_52w_high_pct": -2.0,
        "dist_52w_low_pct": 30.67,
        "range_20d_pct": 4.5,
        "atr_14": 18.5,
        "atr_14_pct": 1.89,
        "squeeze_on": True,
        "rsi_14": 68.5,
        "volume_surge_ratio": 3.4,
        "ret_30d_pct": 12.4,
    }

    res = send_breakout_alert_email(
        ticker="TATAMOTORS.NS",
        company_name="Tata Motors Ltd",
        strategy="NSE Delivery",
        tier="HOT",
        event_type="PROMOTED_HOT",
        composite_score=91.0,
        current_price=980.0,
        trigger_price=995.0,
        target_price=1080.0,
        stop_loss=940.0,
        risk_reward_ratio=2.5,
        volume_ratio=3.4,
        reason="Institutional accumulation with 3.4x delivery surge clearing 52W resistance",
        catalyst_impact="Q2 Earnings Beat",
        technical_data=tech_data,
        settings=settings,
        sync=True,
    )

    assert res is True
    assert len(sent_messages) == 1
    msg = sent_messages[0]

    body_text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "TECHNICAL DECISION CONTEXT & STRUCTURE" in body_text
    assert "Bullish Golden Stack" in body_text
    assert "TTM Squeeze:" in body_text
    assert "ACTIVE SQUEEZE" in body_text
    assert "RSI(14) Momentum:" in body_text
    assert "68.5" in body_text

    html_part = msg.get_body(preferencelist=("html",)).get_content()
    assert "Technical Decision Context" in html_part
    assert "Bullish Golden Stack" in html_part
    assert "ACTIVE SQUEEZE" in html_part
    assert "68.5" in html_part
    assert "3.40x" in html_part


def test_send_hourly_breakout_digest_email(tmp_path, monkeypatch):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    app_settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "test.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.migrations.get_db_connection", db_conn_fn)
    apply_migrations(app_settings)

    email_settings = EmailSettings(
        enabled=True,
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_username="bot@test.com",
        smtp_password="test_password",
        from_address="bot@test.com",
        to_addresses=("desk@test.com",),
    )

    # Insert sample audit log rows for digest
    conn = db_conn_fn()
    conn.execute(
        """
        INSERT INTO breakout_audit_log (
            ticker, company_name, event_type, from_tier, to_tier,
            score_before, score_after, price, trigger_price,
            reason, catalyst_impact, strategy, counter, created_at, updated_at
        ) VALUES
        ('TCS.NS', 'Tata Consultancy Services', 'PROMOTED_HOT', 'WARM', 'HOT', 72.0, 88.0, 4200.0, 4250.0, 'Volume surge breaking out', 'Major Cloud Deal', 'NSE Delivery', 1, datetime('now'), datetime('now')),
        ('INFY.NS', 'Infosys Ltd', 'ADDED_WARM', 'COLD', 'WARM', 50.0, 75.0, 1800.0, 1820.0, 'Coiling in Bollinger Band squeeze', NULL, 'Donchian Squeeze', 2, datetime('now'), datetime('now'))
        """
    )
    conn.commit()

    sent_messages = []

    class MockSMTP:
        def __init__(self, host, port, timeout=15):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            sent_messages.append(msg)

    monkeypatch.setattr("smtplib.SMTP", MockSMTP)

    res = send_hourly_breakout_digest_email(
        hours_lookback=2.0,
        settings=email_settings,
        app_settings=app_settings,
        sync=True,
        base_url="https://nexusquant.test",
    )

    assert res is True
    assert len(sent_messages) == 1
    msg = sent_messages[0]

    assert "HOURLY DIGEST" in msg["Subject"]
    assert "2 Breakout Setups" in msg["Subject"]

    body_text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "TCS.NS" in body_text
    assert "INFY.NS" in body_text
    assert "NSE Delivery" in body_text
    assert "Donchian Squeeze" in body_text
    assert "Major Cloud Deal" in body_text

    html_part = msg.get_body(preferencelist=("html",)).get_content()
    assert "TCS.NS" in html_part
    assert "INFY.NS" in html_part
    assert "Tata Consultancy Services" in html_part
    assert "#07090e" in html_part


def test_scheduler_engine_breakout_hourly_digest_handler(monkeypatch):
    from earnings_engine.data.scheduler_engine import SchedulerEngine
    engine = SchedulerEngine.get_instance()

    digest_called = []

    def mock_digest(**kwargs):
        digest_called.append(kwargs)
        return True

    monkeypatch.setattr("earnings_engine.emailing.send_hourly_breakout_digest_email", mock_digest)

    handler = engine._job_handlers.get("breakout_hourly_digest")
    assert handler is not None

    summary = handler(Settings(), {"hours_lookback": 1.5, "sync": True})
    assert len(digest_called) == 1
    assert digest_called[0]["hours_lookback"] == 1.5
    assert digest_called[0]["sync"] is True
    assert "Hourly breakout digest" in summary

