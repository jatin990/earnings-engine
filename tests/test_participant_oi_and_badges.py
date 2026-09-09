"""Tests for Participant Open Interest (OI) positioning, harmonized indices, and accurate sidebar badges."""

from __future__ import annotations

import pytest
from earnings_engine.config import Settings
from earnings_engine.data.market_pulse import (
    compute_participant_oi_matrix,
    compute_indices_quotes,
    compute_sector_heatmap,
    get_market_pulse_data,
)
from earnings_engine.api.routers.system import (
    get_badge_counters,
    set_badge_counter,
    _hydrate_badge_counters_from_db,
)


def test_compute_participant_oi_matrix():
    """Verify participant OI matrix returns all 4 participant classes with valid mathematical structures."""
    settings = Settings()
    oi_data = compute_participant_oi_matrix(settings=settings, force_refresh=True)

    assert isinstance(oi_data, dict)
    assert "as_of_date" in oi_data
    assert "session_label" in oi_data
    assert "participants" in oi_data
    assert "regime_verdict" in oi_data
    assert "regime_sentiment" in oi_data
    assert "commentary" in oi_data

    participants = oi_data["participants"]
    assert len(participants) == 4

    p_names = {p["participant"] for p in participants}
    assert p_names == {"FII", "DII", "PRO", "CLIENT"}

    for p in participants:
        assert "futures_long" in p
        assert "futures_short" in p
        assert "calls_long" in p
        assert "calls_short" in p
        assert "puts_long" in p
        assert "puts_short" in p
        assert "total_long" in p
        assert "total_short" in p
        assert "net_contracts" in p
        assert "long_short_ratio" in p
        assert "long_pct" in p
        assert "short_pct" in p
        assert "stance" in p
        assert "future_index_long" in p
        assert "future_index_short" in p
        assert "future_index_net" in p
        assert "future_index_long_pct" in p
        assert p["long_pct"] + p["short_pct"] == pytest.approx(100.0, rel=1e-1)

        # 1D Day Delta keys & regime classifications
        assert "delta_future_index_net" in p
        assert "future_index_delta" in p
        assert "delta_future_index_long" in p
        assert "delta_future_index_short" in p
        assert "delta_future_index_long_pct" in p
        assert "delta_future_stock_net" in p
        assert "delta_net_contracts" in p
        assert "delta_ls_ratio" in p
        assert "shift_regime" in p
        assert "oi_regime_badge" in p

    # Check contrarian prediction & smart money divergence metadata
    assert "smart_vs_retail_divergence" in oi_data
    assert "divergence_status" in oi_data
    assert "divergence_badge" in oi_data
    assert "market_maker_stance" in oi_data
    assert "retail_stance" in oi_data
    assert "contrarian_prediction" in oi_data
    assert "verdict" in oi_data["contrarian_prediction"]
    assert "trap_score" in oi_data["contrarian_prediction"]


def test_participant_oi_day_deltas_and_historical_matrix():
    """Verify pairwise day-over-day deltas across history_10d and history_30d."""
    settings = Settings()
    oi_data = compute_participant_oi_matrix(settings=settings, force_refresh=True)

    assert "history_10d" in oi_data
    assert "history_30d" in oi_data
    hist_10d = oi_data["history_10d"]
    assert isinstance(hist_10d, list)
    assert len(hist_10d) >= 1

    # Check historical delta computations
    for i, row in enumerate(hist_10d):
        assert "date" in row
        assert "fii_future_index_net" in row
        assert "dii_future_index_net" in row
        assert "pro_future_index_net" in row
        assert "client_future_index_net" in row
        assert "fii_delta_index_net" in row
        assert "dii_delta_index_net" in row
        assert "pro_delta_index_net" in row
        assert "client_delta_index_net" in row
        assert "fii_shift_regime" in row

        if i < len(hist_10d) - 1:
            next_row = hist_10d[i + 1]
            expected_fii_delta = row["fii_future_index_net"] - next_row["fii_future_index_net"]
            assert row["fii_delta_index_net"] == expected_fii_delta
            expected_dii_delta = row["dii_future_index_net"] - next_row["dii_future_index_net"]
            assert row["dii_delta_index_net"] == expected_dii_delta

    # The oldest baseline day in history_30d has 0 delta and Baseline regime
    hist_30d = oi_data["history_30d"]
    assert isinstance(hist_30d, list)
    assert len(hist_30d) >= 1
    oldest_row = hist_30d[-1]
    assert oldest_row["fii_delta_index_net"] == 0
    assert oldest_row["fii_shift_regime"] == "Baseline"


def test_master_market_pulse_includes_participant_oi():
    """Verify master get_market_pulse_data includes the participant_oi block."""
    settings = Settings()
    pulse = get_market_pulse_data(settings=settings, force_refresh=True)

    assert "participant_oi" in pulse
    assert "participants" in pulse["participant_oi"]
    assert len(pulse["participant_oi"]["participants"]) == 4


def test_harmonized_indices_and_sector_returns():
    """Verify sectoral indices in compute_indices_quotes harmonize with compute_sector_heatmap."""
    settings = Settings()
    sectors = compute_sector_heatmap(settings=settings, force_refresh=True)
    indices = compute_indices_quotes(settings=settings, force_refresh=True)

    sec_map = {s["symbol"]: s for s in sectors if s.get("symbol")}
    for idx in indices:
        sym = idx["symbol"]
        if sym in sec_map:
            sec = sec_map[sym]
            if sec.get("change_1d") is not None:
                assert idx["change_pct"] == pytest.approx(sec["change_1d"], abs=0.01)


def test_sidebar_badges_real_counts():
    """Verify sidebar badges endpoint returns realistic, accurate counts."""
    settings = Settings()
    _hydrate_badge_counters_from_db(settings)
    counters = get_badge_counters(settings)

    assert "breaking_out_stocks" in counters
    assert "high_impact_news_70" in counters
    assert "premarket_high_impact_70" in counters
    assert "active_gainers" in counters

    # Verify numbers are integers and not string 99+
    assert isinstance(counters["breaking_out_stocks"], int)
    assert isinstance(counters["high_impact_news_70"], int)
    assert isinstance(counters["premarket_high_impact_70"], int)
