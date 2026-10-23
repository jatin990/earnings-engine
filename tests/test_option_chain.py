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


def test_derive_gex_action_summary_positive_gamma():
    from earnings_engine.data.option_chain import derive_gex_action_summary

    gamma_profile = {
        "gamma_regime": "POSITIVE_GAMMA",
        "net_gex": 142.5,
        "gamma_flip_strike": 24200.0,
    }
    expected_move = {
        "lower_1sigma": 24100.0,
        "upper_1sigma": 24500.0,
    }

    # 1. Spot in middle: range fade
    summary = derive_gex_action_summary(
        spot_price=24300.0,
        gamma_profile=gamma_profile,
        call_wall=24500.0,
        put_wall=24000.0,
        max_pain=24250.0,
        expected_move=expected_move,
    )
    assert summary["gamma_regime"] == "POSITIVE_GAMMA"
    assert "Range-Bound" in summary["market_texture"]
    assert summary["expected_range"]["support"] == 24000.0
    assert summary["expected_range"]["resistance"] == 24500.0
    assert summary["action_type"] == "BUY_SUPPORT_SELL_RESISTANCE"
    assert "BUY ON SUPPORT" in summary["action_headline"]
    assert "SELL AT RESISTANCE" in summary["action_headline"]
    assert summary["buy_level"] == 24000.0
    assert summary["sell_level"] == 24500.0

    # 2. Spot near support: tactical buy zone
    summary_support = derive_gex_action_summary(
        spot_price=24010.0,
        gamma_profile=gamma_profile,
        call_wall=24500.0,
        put_wall=24000.0,
        max_pain=24250.0,
        expected_move=expected_move,
    )
    assert summary_support["action_type"] == "TACTICAL_BUY"
    assert "BUY AT SUPPORT" in summary_support["action_headline"]


def test_derive_gex_action_summary_negative_gamma():
    from earnings_engine.data.option_chain import derive_gex_action_summary

    gamma_profile = {
        "gamma_regime": "NEGATIVE_GAMMA",
        "net_gex": -210.0,
        "gamma_flip_strike": 24200.0,
    }
    expected_move = {
        "lower_1sigma": 23900.0,
        "upper_1sigma": 24600.0,
    }

    # Spot above flip -> breakout buy
    summary_bull = derive_gex_action_summary(
        spot_price=24350.0,
        gamma_profile=gamma_profile,
        call_wall=24500.0,
        put_wall=24000.0,
        max_pain=24200.0,
        expected_move=expected_move,
    )
    assert summary_bull["gamma_regime"] == "NEGATIVE_GAMMA"
    assert "Volatile" in summary_bull["market_texture"]
    assert summary_bull["action_type"] == "BUY_BREAKOUT_MOMENTUM"
    assert "BUY MOMENTUM" in summary_bull["action_headline"]

    # Spot below flip -> breakdown sell
    summary_bear = derive_gex_action_summary(
        spot_price=24100.0,
        gamma_profile=gamma_profile,
        call_wall=24500.0,
        put_wall=24000.0,
        max_pain=24200.0,
        expected_move=expected_move,
    )
    assert summary_bear["action_type"] == "SELL_BREAKDOWN_MOMENTUM"
    assert "SELL RALLIES" in summary_bear["action_headline"]


def test_derive_oi_action_summary():
    from earnings_engine.data.option_chain import derive_oi_action_summary

    # Bullish scenario: PCR >= 1.2
    summary_bull = derive_oi_action_summary(
        spot_price=24050.0,
        call_wall=24500.0,
        put_wall=24000.0,
        max_pain=24200.0,
        pcr_oi=1.35,
        pcr_volume=1.20,
        sentiment="BULLISH",
        call_oi_total=100000,
        put_oi_total=135000,
    )
    assert "BULLISH OI" in summary_bull["texture_badge"]
    assert summary_bull["texture_theme"] == "emerald"
    assert summary_bull["action_type"] in ("BUY_DIPS", "TACTICAL_BUY")
    assert summary_bull["buy_level"] == 24000.0
    assert summary_bull["sell_level"] == 24500.0
    assert summary_bull["pivot_1_label"] == "Max Pain Strike"
    assert "24,200" in summary_bull["pivot_1_val"]

    # Bearish scenario: PCR <= 0.8
    summary_bear = derive_oi_action_summary(
        spot_price=24250.0,
        call_wall=24500.0,
        put_wall=24000.0,
        max_pain=24200.0,
        pcr_oi=0.65,
        pcr_volume=0.70,
        sentiment="BEARISH",
        call_oi_total=150000,
        put_oi_total=97500,
    )
    assert "BEARISH OI" in summary_bear["texture_badge"]
    assert summary_bear["texture_theme"] == "rose"
    assert summary_bear["action_type"] in ("SELL_RALLIES", "TACTICAL_SELL")
    assert "SELL RALLIES" in summary_bear["action_headline"]


def test_derive_net_delta_action_summary():
    from earnings_engine.data.option_chain import derive_net_delta_action_summary

    records = [
        {"strike": 24000.0, "ce_change_oi": -2000, "pe_change_oi": 15000},  # net delta +17000 (support build)
        {"strike": 24200.0, "ce_change_oi": 5000, "pe_change_oi": 6000},    # net delta +1000
        {"strike": 24500.0, "ce_change_oi": 25000, "pe_change_oi": 1000},   # net delta -24000 (resistance build)
    ]
    summary = derive_net_delta_action_summary(
        spot_price=24250.0,
        records=records,
        call_wall=24500.0,
        put_wall=24000.0,
    )
    assert summary["expected_range"]["support"] == 24000.0
    assert summary["expected_range"]["resistance"] == 24500.0
    assert summary["pivot_1_label"] == "Peak Put Build"
    assert summary["pivot_2_label"] == "Peak Call Build"
    assert "24,500" in summary["action_headline"]


def test_derive_iv_action_summary():
    from earnings_engine.data.option_chain import derive_iv_action_summary

    records = [
        {"strike": 24000.0, "pe_iv": 16.5, "ce_iv": 14.0},
        {"strike": 24200.0, "pe_iv": 14.5, "ce_iv": 14.2},
        {"strike": 24500.0, "pe_iv": 13.5, "ce_iv": 13.0},
    ]
    vix_data = {"vix_value": 13.5, "vix_regime": "LOW_VOL"}
    expected_move = {
        "lower_1sigma": 24050.0,
        "upper_1sigma": 24450.0,
        "lower_2sigma": 23850.0,
        "upper_2sigma": 24650.0,
    }
    summary = derive_iv_action_summary(
        spot_price=24250.0,
        records=records,
        vix_data=vix_data,
        expected_move=expected_move,
    )
    assert summary["expected_range"]["support"] == 24050.0
    assert summary["expected_range"]["resistance"] == 24450.0
    assert summary["action_type"] in ("SELL_HIGH_IV_CREDIT_SPREADS", "BUY_SUPPORT_SELL_RESISTANCE")
    assert summary["pivot_1_label"] == "ATM IV"
    assert summary["pivot_2_label"] == "IV Skew (PE-CE)"


def test_calculate_option_metrics_subtab_summaries_attached():
    from earnings_engine.data.option_chain import _calculate_option_metrics_from_records

    records = [
        {"strikePrice": 2400.0, "CE_openInterest": 10000, "PE_openInterest": 5000, "CE_changeinOpenInterest": 1000, "PE_changeinOpenInterest": 2000},
        {"strikePrice": 2500.0, "CE_openInterest": 20000, "PE_openInterest": 25000, "CE_changeinOpenInterest": 3000, "PE_changeinOpenInterest": 4000},
        {"strikePrice": 2600.0, "CE_openInterest": 5000, "PE_openInterest": 20000, "CE_changeinOpenInterest": -500, "PE_changeinOpenInterest": 1500},
    ]
    res = _calculate_option_metrics_from_records("RELIANCE", records, spot_price=2500.0)
    assert "subtab_summaries" in res
    assert "gex" in res["subtab_summaries"]
    assert "oi" in res["subtab_summaries"]
    assert "net_delta" in res["subtab_summaries"]
    assert "iv" in res["subtab_summaries"]
    assert res["subtab_summaries"]["oi"]["expected_range"]["support"] is not None


def test_calculate_market_compass_and_velocity():
    from earnings_engine.data.options_market_compass import calculate_market_compass
    from earnings_engine.data.options_writing_velocity import derive_multi_timeframe_oi
    from earnings_engine.data.options_alerts_engine import generate_derivatives_alerts

    strikes = [
        {"strike": 24000.0, "ce_oi": 50000, "pe_oi": 150000, "ce_chg_oi": 5000, "pe_chg_oi": 25000, "ce_iv": 14.2, "pe_iv": 15.1},
        {"strike": 24200.0, "ce_oi": 80000, "pe_oi": 120000, "ce_chg_oi": 8000, "pe_chg_oi": 18000, "ce_iv": 13.9, "pe_iv": 14.5},
        {"strike": 24400.0, "ce_oi": 160000, "pe_oi": 40000, "ce_chg_oi": 30000, "pe_chg_oi": 2000, "ce_iv": 13.5, "pe_iv": 14.0},
    ]

    tf = derive_multi_timeframe_oi("NIFTY", current_call_oi=290000, current_put_oi=310000, strikes=strikes)
    assert "today" in tf
    assert "tf_15m" in tf
    assert "tf_5m" in tf
    assert tf["today"]["call_pct"] + tf["today"]["put_pct"] == 100

    compass = calculate_market_compass(
        symbol="NIFTY",
        spot_price=24220.0,
        pcr_oi=1.07,
        pcr_volume=1.15,
        call_wall=24400.0,
        put_wall=24000.0,
        max_pain=24200.0,
        gamma_profile={"net_gex": 125000000.0, "regime": "POSITIVE_GAMMA (Low Volatility)"},
        oi_timeframes=tf,
        chart_intel={"vwap_dist_pct": 0.25, "orb_status": "BULLISH_EXPANSION"},
        vix_data={"vix": 13.5, "change_pct": -2.1},
    )

    assert "score" in compass
    assert -100.0 <= compass["score"] <= 100.0
    assert len(compass["factors"]) == 8
    total_weight = sum(f["weight"] for f in compass["factors"])
    assert total_weight == 100
    assert compass["confidence_pct"] >= 50

    alerts = generate_derivatives_alerts(
        symbol="NIFTY",
        spot_price=24220.0,
        call_wall=24400.0,
        put_wall=24000.0,
        max_pain=24200.0,
        pcr_oi=1.07,
        oi_timeframes=tf,
        gamma_profile={"net_gex": 125000000.0, "regime": "POSITIVE_GAMMA (Low Volatility)"},
        strikes=strikes,
    )
    assert isinstance(alerts, list)
    assert len(alerts) > 0


def test_option_chain_15s_cache_and_vix_resolution():
    from earnings_engine.data.option_chain import _CACHE_TTL_SECONDS, _resolve_vix_profile
    from earnings_engine.data.options_chart_engine import _CHART_CACHE_TTL_SECONDS

    # 1. 15-second cache TTL guarantee for rapid background polling
    assert _CACHE_TTL_SECONDS == 15.0
    assert _CHART_CACHE_TTL_SECONDS == 15.0

    # 2. VIX profile resolution returns valid benchmark structure
    vix_profile = _resolve_vix_profile()
    assert isinstance(vix_profile, dict)
    assert "vix_value" in vix_profile
    assert "vix_change_pct" in vix_profile
    assert "vix_regime" in vix_profile
    assert vix_profile["vix_value"] > 0
    assert vix_profile["vix_regime"] in ("LOW_VOL", "NORMAL_VOL", "ELEVATED_VOL", "HIGH_VOL")









