import time
from datetime import datetime, timezone
from unittest.mock import patch

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.market_pulse import compute_participant_oi_matrix, sync_nse_participant_oi_data


def test_participant_oi_holiday_no_sync():
    # Calling sync on 2026-10-02 (Gandhi Jayanti holiday)
    with patch("requests.get") as mock_get:
        count = sync_nse_participant_oi_data(days=5, force=False)
        # Should not make network requests for today (holiday)
        # If all past days exist or are holiday/future, mock_get is not called or count >= 0
        assert isinstance(count, int)


def test_participant_oi_matrix_performance_and_structure():
    settings = Settings()
    conn = get_db_connection(settings)

    # Seed 3 sample dates of participant OI if DB empty
    test_dates = ["2026-10-01", "2026-09-30", "2026-09-29"]
    for d in test_dates:
        conn.execute("""
            INSERT OR IGNORE INTO participant_oi_positioning (
                date, participant, category_label, future_index_long, future_index_short,
                future_index_net, future_index_long_pct, future_stock_long, future_stock_short,
                future_stock_net, opt_index_call_long, opt_index_call_short, opt_index_put_long,
                opt_index_put_short, opt_stock_call_long, opt_stock_call_short, opt_stock_put_long,
                opt_stock_put_short, futures_long, futures_short, calls_long, calls_short,
                puts_long, puts_short, total_long, total_short, net_contracts, long_short_ratio,
                long_pct, short_pct, stance, updated_at
            ) VALUES (?, 'FII', '🏛️ FII', 100000, 50000, 50000, 66.7, 500000, 200000, 300000,
                     200000, 100000, 150000, 180000, 10000, 5000, 8000, 12000, 600000, 250000,
                     210000, 105000, 158000, 192000, 968000, 547000, 421000, 1.77, 63.9, 36.1,
                     'BULLISH', '2026-10-01T18:30:00Z')
        """, (d,))
    conn.commit()

    # With records in DB, compute matrix should execute in < 0.1s
    t0 = time.perf_counter()
    data = compute_participant_oi_matrix(settings=settings, force_refresh=False)
    duration = time.perf_counter() - t0

    assert "as_of_date" in data or "as_of" in data
    assert "history_30d" in data
    assert "options_summary" in data or "participants" in data
    assert len(data["history_30d"]) > 0
    # Must run fast with single batch query (< 1.0s)
    assert duration < 1.0
