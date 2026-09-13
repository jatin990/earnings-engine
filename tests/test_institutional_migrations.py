from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.turso_sync import SYNC_TABLES, WATERMARK_CANDIDATE_COLUMNS

def test_migration_smart_money_signals_and_financials(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    # Verify institutional_radar_signals columns
    sig_cols = [r[1] for r in conn.execute("PRAGMA table_info(institutional_radar_signals)").fetchall()]
    assert "strategy" in sig_cols
    assert "outcome_return_pct" in sig_cols
    assert "lifecycle_status" in sig_cols
    assert "ideal_entry_price" in sig_cols
    assert "target_price" in sig_cols
    assert "stop_loss" in sig_cols

    # Verify quarterly_financials table
    qfin_cols = [r[1] for r in conn.execute("PRAGMA table_info(quarterly_financials)").fetchall()]
    assert "ticker" in qfin_cols
    assert "quarter" in qfin_cols
    assert "revenue_cr" in qfin_cols
    assert "net_profit_cr" in qfin_cols
    assert "operating_margin_pct" in qfin_cols
    assert "eps" in qfin_cols

    # Verify SYNC_TABLES
    assert "institutional_radar_signals" in SYNC_TABLES
    assert "quarterly_financials" in SYNC_TABLES
    assert "period_end_date" in WATERMARK_CANDIDATE_COLUMNS
