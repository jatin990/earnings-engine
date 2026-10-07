import pytest
from earnings_engine.config import Settings
from earnings_engine.data.option_chain import (
    analyze_option_chain,
    _calculate_max_pain,
    _calculate_option_metrics_from_records,
    calculate_bs_greeks,
    calculate_gamma_profile,
)


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


def test_calculate_bs_greeks_atm_call():
    # Spot 25000, Strike 25000, DTE 7 days, IV 15%, r=6.5%
    greeks = calculate_bs_greeks(spot=25000.0, strike=25000.0, dte_days=7.0, iv_pct=15.0, is_call=True)
    assert 0.48 <= greeks["delta"] <= 0.55
    assert greeks["gamma"] > 0.0
    assert greeks["theta"] < 0.0
    assert greeks["vega"] > 0.0


def test_calculate_bs_greeks_atm_put():
    # Spot 25000, Strike 25000, DTE 7 days, IV 15%, r=6.5%
    greeks = calculate_bs_greeks(spot=25000.0, strike=25000.0, dte_days=7.0, iv_pct=15.0, is_call=False)
    assert -0.55 <= greeks["delta"] <= -0.45
    assert greeks["gamma"] > 0.0
    assert greeks["theta"] < 0.0
    assert greeks["vega"] > 0.0


def test_calculate_bs_greeks_zero_dte_and_invalid_iv():
    # Edge case: DTE = 0
    greeks_0dte = calculate_bs_greeks(spot=25000.0, strike=24900.0, dte_days=0.0, iv_pct=15.0, is_call=True)
    assert greeks_0dte["delta"] == 1.0  # Deep ITM Call at expiry
    assert greeks_0dte["gamma"] == 0.0

    # Edge case: IV = 0
    greeks_0iv = calculate_bs_greeks(spot=25000.0, strike=25100.0, dte_days=5.0, iv_pct=0.0, is_call=True)
    assert greeks_0iv["delta"] == 0.0
    assert greeks_0iv["gamma"] == 0.0


def test_calculate_gamma_profile_and_flip():
    # Sample records around ATM 25000
    records = [
        {"strike": 24800.0, "ce_oi": 20000, "ce_change_oi": -2000, "ce_ltp": 250.0, "ce_iv": 14.0, "pe_oi": 100000, "pe_change_oi": 15000, "pe_ltp": 30.0, "pe_iv": 15.0},
        {"strike": 24900.0, "ce_oi": 40000, "ce_change_oi": 1000, "ce_ltp": 160.0, "ce_iv": 13.5, "pe_oi": 80000, "pe_change_oi": 8000, "pe_ltp": 60.0, "pe_iv": 14.0},
        {"strike": 25000.0, "ce_oi": 120000, "ce_change_oi": 5000, "ce_ltp": 90.0, "ce_iv": 13.0, "pe_oi": 110000, "pe_change_oi": 7000, "pe_ltp": 85.0, "pe_iv": 13.2},
        {"strike": 25100.0, "ce_oi": 90000, "ce_change_oi": 12000, "ce_ltp": 45.0, "ce_iv": 12.8, "pe_oi": 30000, "pe_change_oi": -2000, "pe_ltp": 140.0, "pe_iv": 13.5},
        {"strike": 25200.0, "ce_oi": 150000, "ce_change_oi": 20000, "ce_ltp": 18.0, "ce_iv": 13.0, "pe_oi": 10000, "pe_change_oi": -1000, "pe_ltp": 220.0, "pe_iv": 14.0},
    ]
    profile, enriched = calculate_gamma_profile(records, spot_price=25000.0, dte_days=4.0)

    assert "net_gex" in profile
    assert profile["gamma_regime"] in ("POSITIVE_GAMMA", "NEGATIVE_GAMMA")
    assert profile["gamma_flip_strike"] > 0
    assert profile["atm_straddle_price"] == 175.0  # 90.0 + 85.0
    assert profile["expected_move_upper"] == 25175.0
    assert profile["expected_move_lower"] == 24825.0
    assert len(enriched) == 5
    assert "ce_gex" in enriched[0]
    assert "pe_gex" in enriched[0]
    assert "net_gex" in enriched[0]


def test_derive_market_setups_dealer_pin():
    from earnings_engine.data.option_chain import derive_market_setups
    gamma_profile = {
        "net_gex": 50000.0,
        "gamma_regime": "POSITIVE_GAMMA",
        "gamma_flip_strike": 24800.0,
        "atm_straddle_price": 150.0,
        "expected_move_upper": 25150.0,
        "expected_move_lower": 24850.0,
    }
    records = [
        {"strike": 25000.0, "ce_oi": 150000, "pe_oi": 140000, "ce_change_oi": 5000, "pe_change_oi": 5000}
    ]
    vix_data = {"vix_value": 12.8, "vix_change_pct": -1.5, "vix_regime": "LOW_VOL"}

    setups = derive_market_setups("NIFTY", spot_price=25010.0, records=records, gamma_profile=gamma_profile, vix_data=vix_data, max_pain=25000.0)
    assert len(setups) > 0
    setup = setups[0]
    assert "pin" in setup["id"].lower() or setup["type"] == "MEAN_REVERSION"
    assert setup["target_1"] == 25000.0
    assert setup["stop_loss"] > 0


def test_derive_market_setups_gamma_squeeze():
    from earnings_engine.data.option_chain import derive_market_setups
    gamma_profile = {
        "net_gex": -65000.0,
        "gamma_regime": "NEGATIVE_GAMMA",
        "gamma_flip_strike": 25100.0,
        "atm_straddle_price": 200.0,
        "expected_move_upper": 25400.0,
        "expected_move_lower": 25000.0,
    }
    records = [
        {"strike": 25200.0, "ce_oi": 200000, "pe_oi": 40000, "ce_change_oi": -25000, "pe_change_oi": 10000}
    ]
    vix_data = {"vix_value": 15.5, "vix_change_pct": 4.2, "vix_regime": "HIGH_VOL"}

    setups = derive_market_setups("NIFTY", spot_price=25220.0, records=records, gamma_profile=gamma_profile, vix_data=vix_data, max_pain=25000.0, call_wall=25200.0)
    assert any(s["type"] == "BREAKOUT" or "squeeze" in s["id"].lower() for s in setups)





