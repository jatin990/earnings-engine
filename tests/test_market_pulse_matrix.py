import pytest
from earnings_engine.data.market_pulse import (
    compute_participant_oi_matrix,
    compute_net_cash_liquidity,
    compute_market_sentiment_matrix,
    get_market_pulse_data,
)
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


def test_compute_market_sentiment_matrix_and_charts():
    settings = Settings()
    sentiment = compute_market_sentiment_matrix(settings)

    assert isinstance(sentiment, dict)
    assert "fear_greed_score" in sentiment
    assert 5.0 <= sentiment["fear_greed_score"] <= 95.0
    assert "fear_greed_label" in sentiment
    assert "fear_greed_color" in sentiment
    assert "change_7d" in sentiment
    assert "vix_level" in sentiment
    assert "vix_regime" in sentiment
    assert "vix_1d_pct" in sentiment
    assert "sub_factors" in sentiment
    assert "breadth" in sentiment
    assert "prediction" in sentiment
    assert "macro_charts" in sentiment

    charts = sentiment["macro_charts"]
    assert "dates" in charts
    assert "fear_greed" in charts
    assert "vix" in charts
    assert "nifty" in charts
    assert "bank_nifty" in charts

    assert len(charts["dates"]) > 0
    assert len(charts["fear_greed"]) == len(charts["dates"])
    assert len(charts["vix"]) == len(charts["dates"])
    assert len(charts["nifty"]) == len(charts["dates"])

    for fg_item in charts["fear_greed"]:
        assert "date" in fg_item
        assert "value" in fg_item
        assert "score" in fg_item
        assert 5.0 <= fg_item["value"] <= 95.0

    for vix_item in charts["vix"]:
        assert "date" in vix_item
        assert "value" in vix_item
        assert vix_item["value"] > 0

    for nifty_item in charts["nifty"]:
        assert "date" in nifty_item
        assert "value" in nifty_item
        assert nifty_item["value"] > 0


def test_get_market_pulse_data_includes_institutional_flows():
    settings = Settings()
    pulse = get_market_pulse_data(settings)

    assert isinstance(pulse, dict)
    assert "indices" in pulse
    assert "sectors" in pulse
    assert "liquidity" in pulse
    assert "participant_oi" in pulse
    assert "sentiment" in pulse
    assert "playbook" in pulse

    assert "macro_charts" in pulse["sentiment"]
    assert len(pulse["sentiment"]["macro_charts"]["fear_greed"]) > 0
