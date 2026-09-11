"""Test automatic last-close calculation and dynamic price delta fetch upon news injection."""

import pytest
import sqlite3
from datetime import datetime, timezone, timedelta

from earnings_engine.config import Settings
from earnings_engine.data.news_pipeline import process_and_verify_news_items, save_verified_news_records
from earnings_engine.data.catalysts_news import _connect


def test_news_injection_calculates_on_last_close(tmp_path, monkeypatch):
    settings = Settings()
    settings.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    settings.ensure_dirs()

    now_utc = datetime.now(timezone.utc)
    d_prev = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
    d_curr = now_utc.strftime("%Y-%m-%d")
    recent_utc = (now_utc - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

    # Initialize tables and seed price history for RELIANCE.NS in isolated test tmp_path
    with _connect(settings) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (ticker, date)
            )
        """)
        # Seed price for d_prev and d_curr
        conn.execute(f"INSERT OR REPLACE INTO price_history VALUES ('RELIANCE.NS', '{d_prev}', 2980.0, 3010.0, 2975.0, 3000.0, 500000)")
        conn.execute(f"INSERT OR REPLACE INTO price_history VALUES ('RELIANCE.NS', '{d_curr}', 3010.0, 3060.0, 3005.0, 3045.0, 750000)")
        conn.commit()

    raw_item = [{
        "ticker": "RELIANCE.NS",
        "title": "Reliance Industries bags Rs 5,000 crore solar project contract - Economic Times",
        "summary": "Renewable energy division secures massive commercial order",
        "published_at": recent_utc,
        "publisher": "The Economic Times",
    }]

    verified = process_and_verify_news_items(raw_item, settings=settings)
    assert len(verified) == 1
    rec = verified[0]

    # Ground truth: on recent_utc morning/afternoon, last close was d_prev at ₹3000.00
    assert rec["signal_price"] == 3000.0
    assert rec["signal_date"] == d_prev
    assert rec["current_price"] == 3045.0
    assert rec["price_change_pct"] == round(((3045.0 - 3000.0) / 3000.0) * 100.0, 2)

    # Save to database
    saved_cnt = save_verified_news_records(verified, settings=settings)
    assert saved_cnt == 1

    # Verify saved row in SQLite
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM news_catalysts WHERE ticker = 'RELIANCE.NS' AND title LIKE '%solar project%'").fetchone()
        assert row is not None
        assert row["signal_price"] == 3000.0
        assert row["signal_date"] == d_prev
        assert row["current_price"] == 3045.0
        assert row["price_change_pct"] == 1.5
