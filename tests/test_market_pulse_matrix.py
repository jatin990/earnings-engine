import pytest
from earnings_engine.data.market_pulse import compute_participant_oi_matrix, compute_net_cash_liquidity, get_market_pulse_data
from earnings_engine.config import Settings


def test_compute_participant_oi_matrix():
    settings = Settings()
    oi_data = compute_participant_oi_matrix(settings)
    
    assert isinstance(oi_data, dict)
    assert "participants" in oi_data
    assert "history_7d" in oi_data
    assert "regime_verdict" in oi_data
    assert "regime_sentiment" in oi_data
    
    # Participants should have FII, DII, PRO, CLIENT
    participants = oi_data["participants"]
    assert len(participants) == 4
    categories = {p["participant"] for p in participants}
    assert categories == {"FII", "DII", "PRO", "CLIENT"}
    
    for p in participants:
        assert "long_short_ratio" in p
        assert "long_pct" in p
        assert "short_pct" in p
        assert "stance" in p
        assert "net_contracts" in p

    # 7-day history matrix
    history = oi_data["history_7d"]
    assert isinstance(history, list)
    assert len(history) >= 1
    for h in history:
        assert "date" in h
        assert "fii_net_contracts" in h
        assert "dii_net_contracts" in h
        assert "pro_net_contracts" in h
        assert "client_net_contracts" in h
        assert "fii_long_short_ratio" in h
        assert "fii_delta_index_net" in h
        assert "fii_shift_regime" in h


def test_compute_net_cash_liquidity():
    settings = Settings()
    liquidity = compute_net_cash_liquidity(settings)
    
    assert isinstance(liquidity, dict)
    assert "history_7d" in liquidity
    assert "history_30d" in liquidity
    assert "fii_net_cr" in liquidity
    assert "dii_net_cr" in liquidity
    assert "total_net_cr" in liquidity
    assert "fii_7d_total" in liquidity
    assert "combined_7d_total" in liquidity
    assert "bias" in liquidity
    assert "regime_badge" in liquidity
    
    # Check 7D history records
    hist_7d = liquidity["history_7d"]
    assert isinstance(hist_7d, list)
    assert len(hist_7d) >= 1
    for row in hist_7d:
        assert "date" in row
        assert "fii_net_cr" in row
        assert "dii_net_cr" in row
        assert "total_net_cr" in row


def test_get_market_pulse_data_includes_institutional_flows():
    settings = Settings()
    pulse = get_market_pulse_data(settings)
    
    assert isinstance(pulse, dict)
    assert "institutional_flows" in pulse
    flows = pulse["institutional_flows"]
    assert "history_7d" in flows
    assert "history_30d" in flows
    assert "participant_oi" in pulse
    assert "history_7d" in pulse["participant_oi"]
