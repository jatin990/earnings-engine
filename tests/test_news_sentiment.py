"""Unit tests for the news and world events sentiment analysis module."""

import unittest
from unittest.mock import MagicMock, patch

from earnings_engine.data.news_sentiment import (
    calculate_headline_sentiment,
    classify_topics,
    get_ticker_news_and_sentiment,
)


class TestNewsSentiment(unittest.TestCase):
    def test_calculate_headline_sentiment_bullish(self):
        title = "Company surges 15% after record profit beat and strong revenue expansion"
        score, label = calculate_headline_sentiment(title)
        self.assertGreater(score, 0.20)
        self.assertEqual(label, "Bullish")

    def test_calculate_headline_sentiment_bearish(self):
        title = "Stock plunges amid earnings miss, debt warning and legal probe"
        score, label = calculate_headline_sentiment(title)
        self.assertLess(score, -0.20)
        self.assertEqual(label, "Bearish")

    def test_calculate_headline_sentiment_neutral(self):
        title = "Company scheduled to meet investors next Tuesday in Mumbai"
        score, label = calculate_headline_sentiment(title)
        self.assertEqual(score, 0.0)
        self.assertEqual(label, "Neutral")

    def test_classify_topics(self):
        earnings_text = "Q3 financial results show strong EBITDA growth and EPS surprise"
        topics = classify_topics(earnings_text)
        self.assertIn("Earnings & Guidance", topics)

        deal_text = "Firm announces strategic partnership and joint venture buyout agreement"
        topics = classify_topics(deal_text)
        self.assertIn("Expansion & Deals", topics)

        regulatory_text = "Central bank announces new compliance policy and tariff probe"
        topics = classify_topics(regulatory_text)
        self.assertIn("Regulatory & Macro", topics)

    @patch("earnings_engine.data.news_sentiment.fetch_yfinance_news")
    @patch("earnings_engine.data.news_sentiment.fetch_yahoo_rss_news")
    @patch("earnings_engine.data.news_sentiment.fetch_google_news_rss")
    def test_get_ticker_news_and_sentiment_aggregation(
        self, mock_google, mock_yahoo, mock_yf
    ):
        mock_yf.return_value = [
            {
                "title": "TCS beats quarterly profit estimates with record deal wins",
                "publisher": "Reuters",
                "link": "https://example.com/1",
                "published_at": "2026-08-15 10:00",
                "summary": "Revenue grew 8% year on year.",
                "sentiment_score": 0.8,
                "sentiment_label": "Bullish",
                "topics": ["Earnings & Guidance", "Expansion & Deals"],
                "source": "yfinance",
            }
        ]
        mock_yahoo.return_value = []
        mock_google.return_value = []

        res = get_ticker_news_and_sentiment("TCS.NS")
        self.assertEqual(res["ticker"], "TCS.NS")
        self.assertEqual(res["articles_count"], 1)
        self.assertEqual(res["sentiment_label"], "Bullish")
        self.assertGreater(res["sentiment_score"], 0.5)
        self.assertIn("Earnings & Guidance", res["top_topics"])


if __name__ == "__main__":
    unittest.main()
