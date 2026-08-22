"""Tests for the Strategy Auditor module.

Covers:
- Table creation & prediction logging
- Outcome evaluation logic (bullish/bearish/neutral)
- Multi-strategy metric calculation (Win Rate, Profit Factor, Sharpe, Brier)
- Bulk logging
- Audit engine execution
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.strategy_auditor import (
    _connect,
    _evaluate_single,
    _compute_brier_score,
    _compute_group_metrics,
    audit_predictions,
    backtest_strategy_history,
    calculate_strategy_metrics,
    delete_prediction,
    import_kronos_predictions,
    list_strategies,
    load_audit_history,
    load_predictions,
    log_prediction,
    log_predictions_bulk,
)


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    """Create a Settings instance with temporary data directories."""
    prices_dir = tmp_path / "cache" / "prices"
    earnings_dir = tmp_path / "cache" / "earnings"
    prices_dir.mkdir(parents=True)
    earnings_dir.mkdir(parents=True)
    return Settings(
        data_dirs={"prices": prices_dir, "earnings": earnings_dir},
    )


# ---------------------------------------------------------------------------
# 1. Table creation & prediction logging
# ---------------------------------------------------------------------------


class TestTableCreation:
    def test_connect_creates_tables(self, tmp_settings: Settings) -> None:
        """Verify that _connect creates both audit tables."""
        conn = _connect(tmp_settings)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "strategy_predictions" in tables
        assert "strategy_audit_logs" in tables

    def test_connect_creates_indexes(self, tmp_settings: Settings) -> None:
        """Verify that the indexes are created."""
        conn = _connect(tmp_settings)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_strat_pred_ticker_strat" in indexes
        assert "idx_strat_audit_pred" in indexes


class TestLogPrediction:
    def test_log_basic(self, tmp_settings: Settings) -> None:
        row_id = log_prediction(
            ticker="RELIANCE.NS",
            strategy_name="News_Breakout",
            signal="BULLISH",
            settings=tmp_settings,
            entry_price=2500.0,
            confidence_pct=75.0,
        )
        assert row_id > 0

        preds = load_predictions(settings=tmp_settings)
        assert len(preds) == 1
        assert preds[0]["ticker"] == "RELIANCE.NS"
        assert preds[0]["strategy_name"] == "News_Breakout"
        assert preds[0]["signal"] == "BULLISH"
        assert preds[0]["entry_price"] == 2500.0
        assert preds[0]["confidence_pct"] == 75.0

    def test_log_invalid_signal(self, tmp_settings: Settings) -> None:
        with pytest.raises(ValueError, match="Invalid signal"):
            log_prediction(
                ticker="AAPL",
                strategy_name="Test",
                signal="MAYBE",
                settings=tmp_settings,
            )

    def test_log_auto_sets_market(self, tmp_settings: Settings) -> None:
        log_prediction("TCS.NS", "Test", "BULLISH", settings=tmp_settings, entry_price=100.0)
        log_prediction("AAPL", "Test", "BEARISH", settings=tmp_settings, entry_price=200.0)

        preds = load_predictions(settings=tmp_settings)
        markets = {p["ticker"]: p["market"] for p in preds}
        assert markets["TCS.NS"] == "IN"
        assert markets["AAPL"] == "US"

    def test_log_auto_sets_target_date(self, tmp_settings: Settings) -> None:
        log_prediction("AAPL", "Test", "BULLISH", settings=tmp_settings,
                       entry_price=150.0, holding_horizon="5D")

        preds = load_predictions(settings=tmp_settings)
        assert preds[0]["target_date"] is not None
        expected = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        assert preds[0]["target_date"] == expected

    def test_bulk_log(self, tmp_settings: Settings) -> None:
        batch = [
            {"ticker": "AAPL", "strategy_name": "S1", "signal": "BULLISH", "entry_price": 150.0},
            {"ticker": "MSFT", "strategy_name": "S1", "signal": "BEARISH", "entry_price": 400.0},
            {"ticker": "TSLA", "strategy_name": "S2", "signal": "NEUTRAL", "entry_price": 250.0},
        ]
        ids = log_predictions_bulk(batch, settings=tmp_settings)
        assert len(ids) == 3
        assert all(i > 0 for i in ids)

        preds = load_predictions(settings=tmp_settings)
        assert len(preds) == 3


# ---------------------------------------------------------------------------
# 2. Outcome evaluation logic
# ---------------------------------------------------------------------------


class TestEvaluateSingle:
    def test_bullish_correct(self) -> None:
        pred = {"entry_price": 100.0, "signal": "BULLISH", "expected_return_pct": 5.0}
        result = _evaluate_single(pred, 110.0)
        assert result["outcome_status"] == "WORKED"
        assert result["direction_correct"] == 1
        assert result["actual_return_pct"] == 10.0

    def test_bullish_wrong(self) -> None:
        pred = {"entry_price": 100.0, "signal": "BULLISH", "expected_return_pct": 5.0}
        result = _evaluate_single(pred, 90.0)
        assert result["outcome_status"] == "FAILED"
        assert result["direction_correct"] == 0

    def test_bearish_correct(self) -> None:
        pred = {"entry_price": 200.0, "signal": "BEARISH", "expected_return_pct": -3.0}
        result = _evaluate_single(pred, 190.0)
        assert result["outcome_status"] == "WORKED"
        assert result["direction_correct"] == 1

    def test_bearish_wrong(self) -> None:
        pred = {"entry_price": 200.0, "signal": "BEARISH"}
        result = _evaluate_single(pred, 210.0)
        assert result["outcome_status"] == "FAILED"
        assert result["direction_correct"] == 0

    def test_neutral_within_range(self) -> None:
        pred = {"entry_price": 100.0, "signal": "NEUTRAL"}
        result = _evaluate_single(pred, 100.5)
        assert result["outcome_status"] == "WORKED"
        assert result["direction_correct"] == 1

    def test_neutral_outside_range(self) -> None:
        pred = {"entry_price": 100.0, "signal": "NEUTRAL"}
        result = _evaluate_single(pred, 105.0)
        assert result["outcome_status"] == "FAILED"
        assert result["direction_correct"] == 0

    def test_pending_no_actual_price(self) -> None:
        pred = {"entry_price": 100.0, "signal": "BULLISH"}
        result = _evaluate_single(pred, None)
        assert result["outcome_status"] == "PENDING"

    def test_pending_no_entry_price(self) -> None:
        pred = {"entry_price": None, "signal": "BULLISH"}
        result = _evaluate_single(pred, 110.0)
        assert result["outcome_status"] == "PENDING"


# ---------------------------------------------------------------------------
# 3. Metric calculation
# ---------------------------------------------------------------------------


class TestMetricCalculation:
    def _make_records(self, wins: int, losses: int, returns: list[float]) -> list[dict]:
        records = []
        for i in range(wins):
            records.append({
                "signal": "BULLISH",
                "audit_status": "WORKED",
                "direction_correct": 1,
                "actual_return_pct": returns[i] if i < len(returns) else 2.0,
                "error_pct": 1.0,
                "confidence_pct": 70.0,
            })
        for i in range(losses):
            idx = wins + i
            records.append({
                "signal": "BULLISH",
                "audit_status": "FAILED",
                "direction_correct": 0,
                "actual_return_pct": returns[idx] if idx < len(returns) else -1.5,
                "error_pct": 3.0,
                "confidence_pct": 60.0,
            })
        return records

    def test_win_rate(self) -> None:
        records = self._make_records(7, 3, [2.0]*7 + [-1.0]*3)
        metrics = _compute_group_metrics(records)
        assert metrics["win_rate_pct"] == 70.0
        assert metrics["wins"] == 7
        assert metrics["losses"] == 3

    def test_profit_factor(self) -> None:
        records = self._make_records(2, 2, [10.0, 5.0, -3.0, -2.0])
        metrics = _compute_group_metrics(records)
        # PF = sum_wins / abs(sum_losses) = 15.0 / 5.0 = 3.0
        assert metrics["profit_factor"] == 3.0

    def test_sharpe_ratio_positive(self) -> None:
        records = self._make_records(5, 0, [2.0, 3.0, 1.5, 2.5, 4.0])
        metrics = _compute_group_metrics(records)
        assert metrics["sharpe_ratio"] > 0

    def test_brier_score(self) -> None:
        records = self._make_records(4, 1, [2.0]*4 + [-1.0])
        brier = _compute_brier_score(records)
        assert brier is not None
        assert 0.0 <= brier <= 1.0

    def test_empty_metrics(self) -> None:
        metrics = _compute_group_metrics([])
        assert metrics["total_predictions"] == 0
        assert metrics["win_rate_pct"] == 0.0

    def test_cumulative_return(self) -> None:
        records = self._make_records(3, 0, [10.0, 5.0, -2.0])
        metrics = _compute_group_metrics(records)
        # (1.10 * 1.05 * 0.98 - 1) * 100 ≈ 13.19
        assert metrics["cumulative_return_pct"] > 0


class TestCalculateStrategyMetrics:
    def test_no_data_returns_empty(self, tmp_settings: Settings) -> None:
        metrics = calculate_strategy_metrics(settings=tmp_settings)
        assert metrics["overall"]["total_predictions"] == 0

    def test_with_audited_data(self, tmp_settings: Settings) -> None:
        # Log a prediction
        past_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        row_id = log_prediction(
            "AAPL", "Test_Strategy", "BULLISH",
            settings=tmp_settings,
            entry_price=150.0,
            target_date=past_date,
            confidence_pct=80.0,
        )

        # Manually insert an audit log
        conn = _connect(tmp_settings)
        conn.execute(
            """
            INSERT INTO strategy_audit_logs
                (prediction_id, actual_exit_price, actual_return_pct,
                 outcome_status, direction_correct, error_pct, audited_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (row_id, 160.0, 6.67, "WORKED", 1, 1.67, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()

        metrics = calculate_strategy_metrics(settings=tmp_settings)
        assert metrics["overall"]["total_predictions"] == 1
        assert metrics["overall"]["wins"] == 1
        assert metrics["overall"]["win_rate_pct"] == 100.0
        assert "Test_Strategy" in metrics["by_strategy"]


# ---------------------------------------------------------------------------
# 4. Additional helpers
# ---------------------------------------------------------------------------


class TestListStrategies:
    def test_list_empty(self, tmp_settings: Settings) -> None:
        strategies = list_strategies(settings=tmp_settings)
        assert strategies == []

    def test_list_with_data(self, tmp_settings: Settings) -> None:
        log_prediction("AAPL", "S1", "BULLISH", settings=tmp_settings, entry_price=100.0)
        log_prediction("MSFT", "S1", "BEARISH", settings=tmp_settings, entry_price=200.0)
        log_prediction("TSLA", "S2", "BULLISH", settings=tmp_settings, entry_price=300.0)

        strategies = list_strategies(settings=tmp_settings)
        names = {s["strategy_name"] for s in strategies}
        assert names == {"S1", "S2"}

        s1 = next(s for s in strategies if s["strategy_name"] == "S1")
        assert s1["total_predictions"] == 2
        assert s1["unique_tickers"] == 2


class TestDeletePrediction:
    def test_delete_existing(self, tmp_settings: Settings) -> None:
        row_id = log_prediction("AAPL", "Test", "BULLISH", settings=tmp_settings, entry_price=100.0)
        assert delete_prediction(row_id, settings=tmp_settings) is True
        assert load_predictions(settings=tmp_settings) == []

    def test_delete_nonexistent(self, tmp_settings: Settings) -> None:
        assert delete_prediction(9999, settings=tmp_settings) is False


class TestAuditHistory:
    def test_empty_history(self, tmp_settings: Settings) -> None:
        result = load_audit_history(settings=tmp_settings)
        assert result["items"] == []
        assert result["total"] == 0

    def test_history_with_predictions(self, tmp_settings: Settings) -> None:
        log_prediction("AAPL", "S1", "BULLISH", settings=tmp_settings, entry_price=100.0)
        log_prediction("MSFT", "S1", "BEARISH", settings=tmp_settings, entry_price=200.0)

        result = load_audit_history(settings=tmp_settings)
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_filter_by_strategy(self, tmp_settings: Settings) -> None:
        log_prediction("AAPL", "S1", "BULLISH", settings=tmp_settings, entry_price=100.0)
        log_prediction("MSFT", "S2", "BEARISH", settings=tmp_settings, entry_price=200.0)

        result = load_audit_history(strategy_name="S1", settings=tmp_settings)
        assert result["total"] == 1
        assert result["items"][0]["strategy_name"] == "S1"


# ---------------------------------------------------------------------------
# 5. Kronos historical import & 1-Year backtesting tests
# ---------------------------------------------------------------------------


class TestKronosImport:
    def test_import_empty_db(self, tmp_settings: Settings) -> None:
        """When no kronos_predictions table exists, handles gracefully."""
        res = import_kronos_predictions(settings=tmp_settings)
        assert res["imported"] == 0

    def test_import_kronos_predictions_roundtrip(self, tmp_settings: Settings) -> None:
        """Verify importing existing Kronos forecasts into strategy audit ledger."""
        conn = _connect(tmp_settings)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kronos_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                run_at TEXT NOT NULL,
                predicted_at TEXT NOT NULL,
                lookback INTEGER,
                pred_len INTEGER,
                prediction_json TEXT NOT NULL,
                current_price REAL,
                support REAL,
                resistance REAL,
                return_pct REAL,
                trend TEXT,
                explanation TEXT
            )
        """)
        past_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        conn.execute(
            """
            INSERT INTO kronos_predictions
                (ticker, run_at, predicted_at, lookback, pred_len, prediction_json,
                 current_price, support, resistance, return_pct, trend, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("RELIANCE.NS", f"{past_date} 10:00:00", past_date, 60, 14, "{}",
             2500.0, 2400.0, 2650.0, 5.2, "Bullish", "Breakout setup"),
        )
        conn.commit()
        conn.close()

        res = import_kronos_predictions(settings=tmp_settings)
        assert res["imported"] == 1

        preds = load_predictions(strategy_name="Kronos_AI", settings=tmp_settings)
        assert len(preds) == 1
        assert preds[0]["ticker"] == "RELIANCE.NS"
        assert preds[0]["strategy_name"] == "Kronos_AI"
        assert preds[0]["signal"] == "BULLISH"
        assert preds[0]["entry_price"] == 2500.0


class TestBacktestStrategyHistory:
    def test_backtest_with_mock_data(self, tmp_settings: Settings) -> None:
        """Verify that backtest_strategy_history runs and generates predictions."""
        # Seed some price history
        conn = _connect(tmp_settings)
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
        base_date = datetime.now() - timedelta(days=120)
        for i in range(80):
            d_str = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            p = 100.0 + i * 0.5
            conn.execute(
                "INSERT OR REPLACE INTO price_history VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("AAPL", d_str, p, p + 1.0, p - 1.0, p, 1000000.0),
            )
        conn.commit()
        conn.close()

        res = backtest_strategy_history(
            strategy_name="Kronos_1Y_Backtest",
            days=90,
            universe=None,
            settings=tmp_settings,
        )
        assert res["success"] is True
        assert res["predictions_generated"] > 0

        # Confirm visible in calculate_strategy_metrics
        metrics = calculate_strategy_metrics(settings=tmp_settings)
        assert "Kronos_1Y_Backtest" in metrics["by_strategy"]
        strat_m = metrics["by_strategy"]["Kronos_1Y_Backtest"]
        assert strat_m["total_predictions"] > 0

