import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from earnings_engine.config import Settings, EmailSettings, load_email_settings
from earnings_engine.emailing import send_breakout_alert_email
from earnings_engine.data.breakout_scanner import (
    record_breakout_transition,
    set_ticker_tier,
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
