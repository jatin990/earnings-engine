import pytest
from earnings_engine.config import Settings
from earnings_engine.data.option_chain import analyze_option_chain, _calculate_max_pain, _calculate_option_metrics_from_records


@pytest.fixture
def test_settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def test_non_fno_ticker_fast_bypass(monkeypatch, test_settings):
    """Ensure cash-only / non-F&O equities immediately return NOT_FNO status with zero network requests."""
    # If any network provider or fetcher is called, raise an error
    from earnings_engine.data.providers import provider_manager

    def _unexpected_provider(*args, **kwargs):
        raise AssertionError("Network provider should NEVER be queried for non-F&O tickers!")

    monkeypatch.setattr(provider_manager, "get_data_manager", _unexpected_provider)

    res = analyze_option_chain("SOUTHWEST.NS", spot_price=150.0, settings=test_settings)
    assert res["status"] == "NOT_FNO"
    assert res["symbol"] == "SOUTHWEST"
    assert res["pcr_oi"] is None
    assert res["pcr_volume"] is None
    assert res["max_pain_strike"] is None
    assert res["call_oi_total"] == 0
    assert res["put_oi_total"] == 0
    assert "NOT_FNO_ELIGIBLE" in res["signals"]


def test_calculate_max_pain():
    """Verify max pain calculation algorithm."""
    strikes_data = [
        {"strike": 100.0, "call_oi": 1000, "put_oi": 100},
        {"strike": 105.0, "call_oi": 500, "put_oi": 500},
        {"strike": 110.0, "call_oi": 100, "put_oi": 1000},
    ]
    max_pain = _calculate_max_pain(strikes_data)
    assert max_pain == 105.0


def test_calculate_option_metrics_from_records():
    """Verify metrics calculation and sentiment classification from real records."""
    records = [
        {"strikePrice": 2400.0, "CE_openInterest": 10000, "PE_openInterest": 5000, "CE_totalTradedVolume": 2000, "PE_totalTradedVolume": 1000},
        {"strikePrice": 2500.0, "CE_openInterest": 20000, "PE_openInterest": 25000, "CE_totalTradedVolume": 5000, "PE_totalTradedVolume": 6000},
        {"strikePrice": 2600.0, "CE_openInterest": 5000, "PE_openInterest": 20000, "CE_totalTradedVolume": 1000, "PE_totalTradedVolume": 4000},
    ]
    res = _calculate_option_metrics_from_records("RELIANCE", records, spot_price=2500.0)
    assert res["status"] == "LIVE"
    assert res["call_oi_total"] == 35000
    assert res["put_oi_total"] == 50000
    # PCR(OI) = 50000 / 35000 = 1.43 >= 1.2 -> BULLISH
    assert res["pcr_oi"] == 1.43
    assert res["sentiment"] == "BULLISH"
    assert res["resistance_strike"] == 2500.0
    assert res["support_strike"] == 2500.0


def test_calculate_option_metrics_from_nested_records():
    """Verify metrics calculation when records contain nested CE/PE dicts (from jugaad-data / official NSE)."""
    nested_records = [
        {
            "strikePrice": 1200.0,
            "CE": {"openInterest": 1000, "totalTradedVolume": 200},
            "PE": {"openInterest": 500, "totalTradedVolume": 100},
        },
        {
            "strikePrice": 1250.0,
            "CE": {"openInterest": 3000, "totalTradedVolume": 800},
            "PE": {"openInterest": 4000, "totalTradedVolume": 1200},
        },
        {
            "strikePrice": 1300.0,
            "CE": {"openInterest": 5000, "totalTradedVolume": 1500},
            "PE": {"openInterest": 1000, "totalTradedVolume": 300},
        },
    ]
    res = _calculate_option_metrics_from_records("INFY", nested_records, spot_price=1250.0)
    assert res["status"] == "LIVE"
    assert res["call_oi_total"] == 9000
    assert res["put_oi_total"] == 5500
    # PCR(OI) = 5500 / 9000 = 0.61 <= 0.8 -> BEARISH
    assert res["pcr_oi"] == 0.61
    assert res["sentiment"] == "BEARISH"
    assert res["resistance_strike"] == 1300.0
    assert res["support_strike"] == 1250.0


def test_calculate_option_metrics_straddle_pin_and_direction_aware():
    """Verify that when peak Call OI and peak Put OI occur at the same strike (short straddle),
    resistance is selected from overhead (>= spot) strikes, support from underfoot (<= spot),
    and pin_strike is explicitly flagged."""
    records = [
        {"strikePrice": 1700, "CE_openInterest": 500, "PE_openInterest": 1200},
        {"strikePrice": 1800, "CE_openInterest": 3000, "PE_openInterest": 3000},  # Straddle peak
        {"strikePrice": 1900, "CE_openInterest": 2500, "PE_openInterest": 400},
        {"strikePrice": 2000, "CE_openInterest": 1500, "PE_openInterest": 100},
    ]
    # Spot is 1820 -> Spot > 1800
    res = _calculate_option_metrics_from_records("COFORGE", records, spot_price=1820.0)
    assert res["pin_strike"] == 1800.0
    # Resistance should pick from strikes >= 1820 -> 1900 (2500 OI), not collapse to 1800
    assert res["resistance_strike"] == 1900.0
    # Support should pick from strikes <= 1820 -> 1800 (3000 OI)
    assert res["support_strike"] == 1800.0


