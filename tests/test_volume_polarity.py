"""Unit tests for Volume Polarity and F&O Open Interest classification engine."""

import pytest
from earnings_engine.analysis.volume_polarity import (
    OI_LONG_BUILDUP,
    OI_SHORT_BUILDUP,
    OI_SHORT_COVERING,
    OI_LONG_UNWINDING,
    classify_volume_polarity,
)


class TestVolumePolarity:
    def test_fno_long_buildup(self):
        # Price Up (+2.5%) and OI Up (+5.0%) on an F&O stock
        res = classify_volume_polarity(
            ticker="RELIANCE",
            price_change_pct=2.5,
            volume_ratio=2.1,
            oi_change_pct=5.0,
            is_fno=True,
        )
        assert res["volume_polarity"] == "BULLISH"
        assert res["oi_buildup"] == OI_LONG_BUILDUP
        assert res["volume_character"] == "Long Buildup"
        assert "Long Buildup" in res["badge_label"]
        assert res["confidence"] == "HIGH"

    def test_fno_short_buildup(self):
        # Price Down (-3.2%) and OI Up (+6.5%)
        res = classify_volume_polarity(
            ticker="TATASTEEL",
            price_change_pct=-3.2,
            volume_ratio=1.8,
            oi_change_pct=6.5,
            is_fno=True,
        )
        assert res["volume_polarity"] == "BEARISH"
        assert res["oi_buildup"] == OI_SHORT_BUILDUP
        assert res["volume_character"] == "Short Buildup"
        assert "Short Buildup" in res["badge_label"]
        assert res["confidence"] == "HIGH"

    def test_fno_short_covering(self):
        # Price Up (+1.8%) and OI Down (-4.2%)
        res = classify_volume_polarity(
            ticker="INFY",
            price_change_pct=1.8,
            volume_ratio=1.2,
            oi_change_pct=-4.2,
            is_fno=True,
        )
        assert res["volume_polarity"] == "BULLISH"
        assert res["oi_buildup"] == OI_SHORT_COVERING
        assert res["volume_character"] == "Short Covering"
        assert "Short Covering" in res["badge_label"]

    def test_fno_long_unwinding(self):
        # Price Down (-2.0%) and OI Down (-5.1%)
        res = classify_volume_polarity(
            ticker="HDFCBANK",
            price_change_pct=-2.0,
            volume_ratio=1.3,
            oi_change_pct=-5.1,
            is_fno=True,
        )
        assert res["volume_polarity"] == "BEARISH"
        assert res["oi_buildup"] == OI_LONG_UNWINDING
        assert res["volume_character"] == "Long Unwinding"
        assert "Long Unwinding" in res["badge_label"]

    def test_cash_bullish_accumulation(self):
        # Non-F&O cash stock with strong price close near highs and solid delivery
        res = classify_volume_polarity(
            ticker="ZOMATO",
            price_change_pct=3.5,
            volume_ratio=2.4,
            close=250.0,
            high=252.0,
            low=240.0,
            delivery_pct=55.0,
            is_fno=False,
        )
        assert res["volume_polarity"] == "BULLISH"
        assert res["oi_buildup"] is None
        assert "Bullish" in res["badge_label"]

    def test_cash_bearish_distribution(self):
        # Non-F&O cash stock closing near lows with negative return
        res = classify_volume_polarity(
            ticker="PAYTM",
            price_change_pct=-4.0,
            volume_ratio=2.8,
            close=380.0,
            high=410.0,
            low=378.0,
            is_fno=False,
        )
        assert res["volume_polarity"] == "BEARISH"
        assert res["oi_buildup"] is None
        assert "Bearish" in res["badge_label"]

    def test_neutral_churn(self):
        # Flat price and mid-range candle
        res = classify_volume_polarity(
            ticker="ABC",
            price_change_pct=0.0,
            volume_ratio=1.0,
            close=100.0,
            high=102.0,
            low=98.0,
            is_fno=False,
        )
        assert res["volume_polarity"] == "NEUTRAL"
        assert "Neutral" in res["badge_label"]
