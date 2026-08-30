import sqlite3
from earnings_engine.config import Settings
from earnings_engine.data.turso_sync import (
    _get_watermark_column,
    _init_sync_state_tables,
    _get_last_sync_timestamp,
    _save_last_sync_timestamp,
    WATERMARK_CANDIDATE_COLUMNS,
)


def test_get_watermark_column_priority():
    cols_1 = ["id", "ticker", "created_at", "updated_at"]
    assert _get_watermark_column(cols_1) == "updated_at"

    cols_2 = ["ticker", "signal_date", "scanned_at"]
    assert _get_watermark_column(cols_2) == "scanned_at"

    cols_3 = ["ticker", "company", "date"]
    assert _get_watermark_column(cols_3) == "date"

    cols_4 = ["ticker", "score"]
    assert _get_watermark_column(cols_4) is None


def test_sync_state_lifecycle(tmp_path):
    db_file = tmp_path / "test_delta.sqlite3"
    conn = sqlite3.connect(str(db_file))

    # Mock class for remote connection
    class MockRemote:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, params=None):
            if params:
                return self.conn.execute(sql, params)
            return self.conn.execute(sql)

    remote = MockRemote(conn)

    _init_sync_state_tables(conn, remote)

    # Initially None
    ts = _get_last_sync_timestamp(conn, "breakout_radar")
    assert ts is None

    # Save timestamp
    _save_last_sync_timestamp(conn, remote, "breakout_radar", "2026-08-30T14:00:00Z", 15, 0)

    # Retrieve timestamp
    ts2 = _get_last_sync_timestamp(conn, "breakout_radar")
    assert ts2 == "2026-08-30T14:00:00Z"

    conn.close()
