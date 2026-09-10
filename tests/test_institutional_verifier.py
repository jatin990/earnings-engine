"""Tests for Institutional Data Integrity, Provenance & Mathematical Verification Engine."""
from __future__ import annotations

import json
import sqlite3
import pytest
from datetime import datetime, date, timezone
from fastapi.testclient import TestClient
from click.testing import CliRunner

from earnings_engine.config import Settings
from earnings_engine.api.server import app
from earnings_engine.cli import cli
from earnings_engine.data.institutional_verifier import (
    InstitutionalVerifier,
    MathematicalInvariantChecker,
    FreshnessCadenceTracker,
    AntiFabricationDetector,
    AuditFinding,
    ProvenanceRecord,
    record_provenance,
    hash_payload,
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    return TestClient(app)


# =========================================================================
# 1. Mathematical Invariance Verification Tests
# =========================================================================

def test_shareholding_100_percent_sum_invariant_pass():
    """Verify standard shareholding exactly summing to 100.0% passes invariant."""
    findings = MathematicalInvariantChecker.verify_shareholding_pattern(
        ticker="RELIANCE.NS",
        quarter="Q4 FY26",
        promoter_pct=50.30,
        fii_pct=21.50,
        dii_pct=16.20,
        public_pct=11.50,
        others_pct=0.50,
    )
    assert len(findings) >= 1
    sum_finding = next(f for f in findings if f.check_name == "SHAREHOLDING_100_PCT_SUM_INVARIANT")
    assert sum_finding.severity == "PASS"
    assert sum_finding.status == "OK"


def test_shareholding_100_percent_sum_invariant_fail():
    """Verify shareholding with incorrect sum is flagged with CRITICAL_ERROR."""
    # Sum = 50 + 20 + 20 + 15 = 105.0% (> 100.5%)
    findings = MathematicalInvariantChecker.verify_shareholding_pattern(
        ticker="BADSTOCK.NS",
        quarter="Q4 FY26",
        promoter_pct=50.0,
        fii_pct=20.0,
        dii_pct=20.0,
        public_pct=15.0,
        others_pct=0.0,
    )
    assert len(findings) >= 1
    sum_finding = next(f for f in findings if f.check_name == "SHAREHOLDING_100_PCT_SUM_INVARIANT")
    assert sum_finding.severity == "CRITICAL_ERROR"
    assert sum_finding.status == "FAILED"
    assert sum_finding.actual_value == "105.00%"


def test_shareholding_negative_percentage_fail():
    """Verify negative percentage is rejected with COMPONENT_BOUNDS_CHECK."""
    findings = MathematicalInvariantChecker.verify_shareholding_pattern(
        ticker="NEGSTOCK.NS",
        quarter="Q4 FY26",
        promoter_pct=60.0,
        fii_pct=-5.0,
        dii_pct=25.0,
        public_pct=20.0,
        others_pct=0.0,
    )
    assert len(findings) >= 1
    bounds_finding = next((f for f in findings if f.check_name == "COMPONENT_BOUNDS_CHECK"), None)
    assert bounds_finding is not None
    assert bounds_finding.severity == "CRITICAL_ERROR"


def test_promoter_pledge_bound_pass():
    """Verify valid promoter pledge percentage (<= promoter_pct) passes."""
    findings = MathematicalInvariantChecker.verify_shareholding_pattern(
        ticker="TCS.NS",
        quarter="Q4 FY26",
        promoter_pct=72.0,
        fii_pct=12.0,
        dii_pct=10.0,
        public_pct=6.0,
        others_pct=0.0,
        pledged_pct=5.5,
    )
    assert not any(f.check_name == "PROMOTER_PLEDGE_BOUND_CHECK" for f in findings)


def test_promoter_pledge_bound_fail():
    """Verify promoter pledge exceeding promoter total is flagged."""
    findings = MathematicalInvariantChecker.verify_shareholding_pattern(
        ticker="TCS.NS",
        quarter="Q4 FY26",
        promoter_pct=50.0,
        fii_pct=20.0,
        dii_pct=20.0,
        public_pct=10.0,
        others_pct=0.0,
        pledged_pct=55.0,  # Impossible: cannot pledge more than total owned
    )
    pledge_finding = next((f for f in findings if f.check_name == "PROMOTER_PLEDGE_BOUND_CHECK"), None)
    assert pledge_finding is not None
    assert pledge_finding.severity == "CRITICAL_ERROR"
    assert pledge_finding.status == "FAILED"


def test_category_breakdown_reconciliation():
    """Verify individual shareholders sum cannot exceed category aggregate."""
    # FII aggregate is 15.0%, but sum of listed FIIs is 18.0%
    sub_holders = [
        {"fund_name": "FII A", "stake_pct": 10.0},
        {"fund_name": "FII B", "stake_pct": 8.0},
    ]
    findings = MathematicalInvariantChecker.reconcile_individual_holders(
        ticker="TEST.NS",
        quarter="Q4 FY26",
        category_name="FII",
        category_total_pct=15.0,
        individual_holdings=sub_holders,
    )
    assert len(findings) >= 1
    recon_finding = next(f for f in findings if f.check_name == "CATEGORY_BREAKDOWN_RECONCILIATION")
    assert recon_finding.severity == "CRITICAL_ERROR"
    assert recon_finding.status == "FAILED"


def test_daily_cash_flow_balance_pass():
    """Verify valid gross-net daily flows pass."""
    findings = MathematicalInvariantChecker.verify_daily_flow_consistency(
        trade_date="2026-03-31",
        fii_buy_cr=10000.0,
        fii_sell_cr=8000.0,
        fii_net_cr=2000.0,
        dii_buy_cr=7000.0,
        dii_sell_cr=7500.0,
        dii_net_cr=-500.0,
        total_net_cr=1500.0,
    )
    assert len(findings) == 1
    assert findings[0].severity == "PASS"
    assert findings[0].status == "OK"


def test_daily_cash_flow_balance_fail():
    """Verify arithmetic mismatch in daily cash flows is flagged."""
    findings = MathematicalInvariantChecker.verify_daily_flow_consistency(
        trade_date="2026-03-31",
        fii_buy_cr=10000.0,
        fii_sell_cr=8000.0,
        fii_net_cr=3000.0,  # Math error: 10000 - 8000 != 3000
        dii_buy_cr=7000.0,
        dii_sell_cr=7000.0,
        dii_net_cr=0.0,
        total_net_cr=3000.0,
    )
    fii_math = next((f for f in findings if f.check_name == "DAILY_FII_FLOW_ARITHMETIC"), None)
    assert fii_math is not None
    assert fii_math.severity == "CRITICAL_ERROR"


def test_deal_trade_bounds():
    """Verify deal quantity and price bounds."""
    # Negative price
    bad_deal = MathematicalInvariantChecker.verify_bulk_block_deal(
        ticker="INFY.NS",
        deal_date="2026-03-31",
        deal_type="BUY",
        quantity=100000,
        price=-10.0,
        value_cr=15.0,
    )
    assert len(bad_deal) >= 1
    assert any("PRICE_BOUNDS" in f.check_name for f in bad_deal)

    # Valid deal
    good_deal = MathematicalInvariantChecker.verify_bulk_block_deal(
        ticker="INFY.NS",
        deal_date="2026-03-31",
        deal_type="BUY",
        quantity=100000,
        price=1500.0,
        value_cr=15.0,
    )
    assert len(good_deal) == 0


# =========================================================================
# 2. Multi-Cadence Freshness Tracking Tests
# =========================================================================

def test_statutory_filing_deadline():
    """Verify statutory filing deadlines under SEBI Reg 31 (21 days post quarter end)."""
    # In month 4 (April 2026), latest completed quarter is Q4 ended Mar 31 -> Apr 21
    ref = datetime(2026, 4, 10, tzinfo=timezone.utc)
    info = FreshnessCadenceTracker.get_sebi_filing_window(ref)
    assert info.quarter_code == "Q4 FY26"
    assert info.quarter_end_date == "2026-03-31"
    assert info.filing_deadline == "2026-04-21"
    assert info.is_filing_window_active is True
    assert info.is_past_filing_deadline is False


def test_amfi_portfolio_freshness(tmp_path):
    """Test AMFI monthly portfolio freshness detection on SQLite database."""
    db_path = tmp_path / "test_freshness.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE institutional_holdings (
            id INTEGER PRIMARY KEY,
            ticker TEXT,
            fund_name TEXT,
            fund_type TEXT,
            quarter TEXT,
            reported_date TEXT,
            stake_pct REAL
        )
    """)
    # Insert recent holding (10 days ago)
    conn.execute(
        "INSERT INTO institutional_holdings VALUES (1, 'TCS.NS', 'SBI Bluechip Fund', 'Mutual Fund', 'Q4 FY26', '2026-03-25', 2.5)"
    )
    conn.commit()

    findings = FreshnessCadenceTracker.audit_amfi_portfolio_freshness(conn, max_age_days=45)
    conn.close()
    assert len(findings) >= 1
    assert any(f.check_category == "FRESHNESS" for f in findings)


# =========================================================================
# 3. Anti-Fabrication & Anomaly Auditing Tests
# =========================================================================

def test_detect_synthetic_mock_records(tmp_path):
    """Test detection of fake/synthetic/dummy records in database."""
    db_path = tmp_path / "test_anti_fab.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE institutional_holdings (
            id INTEGER PRIMARY KEY,
            ticker TEXT,
            fund_name TEXT,
            quarter TEXT,
            stake_pct REAL
        )
    """)
    conn.execute(
        "INSERT INTO institutional_holdings VALUES (1, 'MOCK_STOCK.NS', 'Synthetic Mock Fund XYZ', 'Q4 FY26', 1.5)"
    )
    conn.commit()

    findings = AntiFabricationDetector.detect_synthetic_records(conn)
    conn.close()
    assert len(findings) >= 1
    assert any("SYNTHETIC" in f.check_name for f in findings)
    assert findings[0].severity == "CRITICAL_ERROR"


def test_detect_static_stuck_shareholding(tmp_path):
    """Test detection of identically frozen shareholding patterns over >=4 quarters."""
    db_path = tmp_path / "test_stuck.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE shareholding_patterns (
            ticker TEXT,
            quarter TEXT,
            promoter_pct REAL,
            fii_pct REAL,
            dii_mf_pct REAL,
            public_retail_pct REAL,
            PRIMARY KEY (ticker, quarter)
        )
    """)
    for q in ["Q1 FY25", "Q2 FY25", "Q3 FY25", "Q4 FY25"]:
        conn.execute(
            "INSERT INTO shareholding_patterns VALUES ('STUCK.NS', ?, 50.0, 20.0, 15.0, 15.0)",
            (q,),
        )
    conn.commit()

    findings = AntiFabricationDetector.detect_stuck_or_static_patterns(conn, min_consecutive_quarters=4)
    conn.close()
    assert len(findings) >= 1
    assert any("STATIC" in f.check_name for f in findings)


def test_detect_unexplained_jump(tmp_path):
    """Test detection of large unexplained institutional stake shift (>20%)."""
    db_path = tmp_path / "test_jump.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE shareholding_patterns (
            ticker TEXT,
            quarter TEXT,
            promoter_pct REAL,
            fii_pct REAL,
            dii_mf_pct REAL,
            PRIMARY KEY (ticker, quarter)
        )
    """)
    conn.execute("INSERT INTO shareholding_patterns VALUES ('VOLATILE.NS', 'Q3 FY26', 50.0, 10.0, 15.0)")
    conn.execute("INSERT INTO shareholding_patterns VALUES ('VOLATILE.NS', 'Q4 FY26', 50.0, 35.0, 15.0)")  # FII +25%
    conn.commit()

    findings = AntiFabricationDetector.detect_unexplained_stake_jumps(conn, fii_dii_threshold_pct=20.0)
    conn.close()
    assert len(findings) >= 1
    jump_finding = next((f for f in findings if f.check_name == "UNEXPLAINED_STAKE_JUMP"), None)
    assert jump_finding is not None
    assert jump_finding.severity == "WARNING"


# =========================================================================
# 4. Cryptographic Provenance Ledger Tests
# =========================================================================

def test_cryptographic_provenance_recording(tmp_path):
    """Test SHA-256 payload provenance calculation and persistent storage."""
    db_path = tmp_path / "test_prov.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE data_provenance_meta (
            id INTEGER PRIMARY KEY,
            record_type TEXT,
            entity_key TEXT,
            source_name TEXT,
            source_url TEXT,
            payload_sha256 TEXT,
            payload_size_bytes INTEGER,
            fetch_timestamp TEXT,
            verified_timestamp TEXT,
            is_authentic INTEGER,
            quarantine_reason TEXT,
            created_at TEXT
        )
    """)

    payload = {"source": "NSE_XBRL", "data": [1, 2, 3], "status": "active"}
    rec = record_provenance(
        record_type="SHAREHOLDING",
        entity_key="RELIANCE.NS:Q4_FY26",
        source_name="NSE_XBRL_SHAREHOLDING",
        payload=payload,
        source_url="https://www.nseindia.com/api/corporates-shareholding",
        is_authentic=True,
        conn=conn,
    )
    conn.close()

    assert rec.payload_sha256 is not None
    assert len(rec.payload_sha256) == 64  # SHA-256 is 64 hex chars
    assert rec.source_name == "NSE_XBRL_SHAREHOLDING"
    assert rec.entity_key == "RELIANCE.NS:Q4_FY26"
    assert rec.is_authentic is True


# =========================================================================
# 5. Full Verifier Audit Engine & Quarantine Tests
# =========================================================================

def test_institutional_verifier_full_audit(tmp_path):
    """Test comprehensive audit run on sample database."""
    db_path = tmp_path / "test_full_audit.sqlite3"
    conn = sqlite3.connect(db_path)

    # Setup necessary tables
    conn.execute("""
        CREATE TABLE shareholding_patterns (
            ticker TEXT, quarter TEXT, promoter_pct REAL, fii_pct REAL, dii_mf_pct REAL, public_retail_pct REAL, other_pct REAL, updated_at TEXT,
            PRIMARY KEY (ticker, quarter)
        )
    """)
    conn.execute("""
        CREATE TABLE institutional_net_flows (
            date TEXT PRIMARY KEY, fii_buy_cr REAL, fii_sell_cr REAL, fii_net_cr REAL, dii_buy_cr REAL, dii_sell_cr REAL, dii_net_cr REAL, total_net_cr REAL, updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE institutional_holdings (
            id INTEGER PRIMARY KEY, fund_name TEXT, fund_type TEXT, ticker TEXT, stake_pct REAL, quarter TEXT, reported_date TEXT, action TEXT, updated_at TEXT
        )
    """)

    # Insert 1 valid stock and 1 invalid stock
    conn.execute("INSERT INTO shareholding_patterns VALUES ('GOOD.NS', 'Q4 FY26', 50.0, 20.0, 20.0, 10.0, 0.0, '2026-03-31')")
    conn.execute("INSERT INTO shareholding_patterns VALUES ('BAD.NS', 'Q4 FY26', 60.0, 30.0, 20.0, 10.0, 0.0, '2026-03-31')")  # Sum = 120%
    conn.commit()

    verifier = InstitutionalVerifier(conn=conn)
    report = verifier.run_comprehensive_audit(scope="MATHEMATICAL", persist_log=False)
    conn.close()

    assert report is not None
    assert report.total_checks >= 1
    bad_findings = [f for f in report.findings if f.ticker == "BAD.NS"]
    assert len(bad_findings) >= 1
    assert any("SUM_INVARIANT" in f.check_name for f in bad_findings)


# =========================================================================
# 6. REST API Endpoints Integration Tests
# =========================================================================

def test_api_institutional_integrity(client):
    """Test GET /api/v1/institutional/integrity endpoint."""
    res = client.get("/api/v1/institutional/integrity")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "health_score" in data
    assert "status" in data
    assert "cadences" in data
    assert "daily_fii_dii" in data["cadences"]
    assert "monthly_amfi_portfolios" in data["cadences"]
    assert "quarterly_nse_shareholding" in data["cadences"]


def test_api_stock_integrity(client):
    """Test GET /api/v1/institutional/integrity/{ticker} endpoint."""
    res = client.get("/api/v1/institutional/integrity/RELIANCE.NS")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["ticker"] == "RELIANCE.NS"
    assert "health_score" in data
    assert "status" in data
    assert "provenance_trail" in data
    assert "mathematical_findings" in data


def test_api_verify_and_repair(client):
    """Test POST /api/v1/institutional/verify-and-repair endpoint."""
    res = client.post("/api/v1/institutional/verify-and-repair", json={"scope": "MATHEMATICAL", "auto_repair": False})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "report" in data
    assert "health_score" in data["report"]


# =========================================================================
# 7. CLI Command Integration Tests
# =========================================================================

def test_cli_verify_institutional():
    """Test earnings-engine verify-institutional command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-institutional", "--ticker", "RELIANCE.NS", "--json"])
    assert result.exit_code == 0
    json_start = result.output.find("{")
    assert json_start != -1
    parsed = json.loads(result.output[json_start:])
    assert "health_score" in parsed
    assert "status" in parsed
