import sqlite3
import pytest
from earnings_engine.data.option_chain import (
    save_tracked_option_setups,
    get_tracked_option_setups,
    evaluate_tracked_option_setups,
)


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS options_tracked_setups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            setup_id TEXT NOT NULL,
            setup_title TEXT NOT NULL,
            setup_type TEXT NOT NULL,
            bias TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            signal_date TEXT NOT NULL,
            spot_at_signal REAL NOT NULL,
            entry_zone TEXT NOT NULL,
            stop_loss REAL NOT NULL,
            target_1 REAL NOT NULL,
            target_2 REAL,
            risk_reward TEXT,
            catalyst TEXT,
            gamma_regime TEXT,
            vix_value REAL,
            current_spot REAL,
            realized_pnl_pct REAL DEFAULT 0.0,
            outcome TEXT NOT NULL DEFAULT 'ACTIVE',
            outcome_label TEXT,
            outcome_badge TEXT,
            scanned_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(symbol, setup_id, signal_date)
        )
    """)
    return conn


def test_save_and_retrieve_tracked_setups(db_conn):
    setups = [
        {
            "id": "gamma-squeeze-25200",
            "title": "Gamma Squeeze Breakout above 25200",
            "type": "BREAKOUT",
            "bias": "BULLISH",
            "confidence": 88,
            "entry_zone": "25180 - 25220",
            "stop_loss": 25050.0,
            "target_1": 25400.0,
            "target_2": 25500.0,
            "risk_reward": "1 : 3.2",
            "catalyst": "High gamma squeeze",
        }
    ]
    gamma_profile = {"gamma_regime": "NEGATIVE_GAMMA"}
    vix_profile = {"vix_value": 15.2}

    saved_count = save_tracked_option_setups(
        db_conn, setups, "NIFTY", spot_price=25210.0, gamma_profile=gamma_profile, vix_profile=vix_profile
    )
    assert saved_count == 1

    history = get_tracked_option_setups(db_conn, symbol="NIFTY")
    assert len(history) == 1
    assert history[0]["setup_id"] == "gamma-squeeze-25200"
    assert history[0]["outcome"] == "ACTIVE"


def test_evaluate_tracked_setups_target_hit(db_conn):
    setups = [
        {
            "id": "gamma-squeeze-25200",
            "title": "Gamma Squeeze Breakout above 25200",
            "type": "BREAKOUT",
            "bias": "BULLISH",
            "confidence": 88,
            "entry_zone": "25180 - 25220",
            "stop_loss": 25050.0,
            "target_1": 25400.0,
            "target_2": 25500.0,
            "risk_reward": "1 : 3.2",
            "catalyst": "High gamma squeeze",
        }
    ]
    save_tracked_option_setups(
        db_conn, setups, "NIFTY", spot_price=25210.0, gamma_profile={"gamma_regime": "NEGATIVE_GAMMA"}, vix_profile={"vix_value": 15.2}
    )

    # Evaluate with spot at 25420 (Target 1 achieved)
    updates = evaluate_tracked_option_setups(db_conn, "NIFTY", current_spot=25420.0)
    assert len(updates) == 1
    assert updates[0]["outcome"] == "TARGET1_HIT"
    assert updates[0]["realized_pnl_pct"] > 0
