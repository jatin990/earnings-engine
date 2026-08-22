"""Unit tests for the multi-modal AI stock prediction engine."""

import unittest
from unittest.mock import patch

from earnings_engine.config import Settings
from earnings_engine.predict_multimodal import (
    _compute_price_volume_features,
    _deterministic_synthesis,
    init_multimodal_db,
    run_multimodal_prediction,
    store_ai_prediction,
    get_latest_ai_prediction,
)


class TestMultimodalPrediction(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        init_multimodal_db(self.settings)

    def test_deterministic_synthesis_bullish(self):
        news_data = {
            "sentiment_score": 0.65,
            "sentiment_label": "Bullish",
            "articles_count": 4,
            "top_topics": ["Earnings & Guidance", "Expansion & Deals"],
        }
        pv_data = {
            "current_price": 285.0,
            "return_7d": 4.5,
            "return_30d": 8.0,
            "volume_ratio": 1.65,
            "volume_status": "High Accumulation",
        }
        res = _deterministic_synthesis(
            "TEST.NS",
            news_data,
            pv_data,
            swing_support=280.0,
            swing_resistance=320.0,
        )
        self.assertIn("Bullish", res["ai_signal"])
        self.assertGreater(res["sentiment_score"], 0.20)
        self.assertGreaterEqual(len(res["catalysts"]), 1)
        self.assertIn("TEST.NS", res["thesis"])

    def test_deterministic_synthesis_bearish(self):
        news_data = {
            "sentiment_score": -0.70,
            "sentiment_label": "Bearish",
            "articles_count": 3,
            "top_topics": ["Litigation & Risk"],
        }
        pv_data = {
            "current_price": 318.0,
            "return_7d": -4.2,
            "return_30d": -9.0,
            "volume_ratio": 0.55,
            "volume_status": "Low Volume / Distribution",
        }
        res = _deterministic_synthesis(
            "TEST.NS",
            news_data,
            pv_data,
            swing_support=280.0,
            swing_resistance=315.0,
        )
        self.assertIn("Bearish", res["ai_signal"])
        self.assertLess(res["sentiment_score"], -0.15)
        self.assertGreaterEqual(len(res["risk_factors"]), 1)

    @patch("earnings_engine.predict_multimodal.get_ticker_news_and_sentiment")
    @patch("earnings_engine.predict_multimodal._compute_price_volume_features")
    def test_run_multimodal_prediction_and_sqlite_persistence(
        self, mock_pv, mock_news
    ):
        mock_news.return_value = {
            "ticker": "RELIANCE.NS",
            "sentiment_score": 0.5,
            "sentiment_label": "Bullish",
            "bullish_count": 3,
            "bearish_count": 0,
            "neutral_count": 1,
            "articles_count": 4,
            "top_topics": ["Expansion & Deals"],
            "articles": [
                {
                    "title": "Reliance signs multi-billion green energy deal",
                    "publisher": "Mint",
                    "link": "https://example.com/rel",
                    "published_at": "2026-08-15",
                    "summary": "New capex announced.",
                    "sentiment_score": 0.6,
                    "sentiment_label": "Bullish",
                    "topics": ["Expansion & Deals"],
                    "source": "yfinance",
                }
            ],
        }
        mock_pv.return_value = {
            "current_price": 2950.0,
            "return_7d": 2.5,
            "return_30d": 5.1,
            "volatility_20d": 14.2,
            "volume_ratio": 1.4,
            "volume_status": "High Accumulation",
        }

        res = run_multimodal_prediction(
            "RELIANCE.NS",
            swing_support=2900.0,
            swing_resistance=3100.0,
            settings=self.settings,
        )

        self.assertEqual(res["ticker"], "RELIANCE.NS")
        self.assertIn(res["ai_signal"], ["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"])
        self.assertEqual(res["current_price"], 2950.0)

        # Check SQLite persistence
        cached = get_latest_ai_prediction("RELIANCE.NS", settings=self.settings)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["ticker"], "RELIANCE.NS")
        self.assertEqual(cached["ai_signal"], res["ai_signal"])


if __name__ == "__main__":
    unittest.main()
