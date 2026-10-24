"""Tests for canonical_symbol and dead-letter ticker suppression."""

import pytest
from unittest.mock import patch, MagicMock
from earnings_engine.config import Settings
from earnings_engine.data.prices import (
    canonical_symbol,
    is_dead_letter_ticker,
    record_dead_letter_failure,
    fetch_prices,
    fetch_live_quote,
    fetch_batch_live_quotes,
    DEAD_LETTER_TICKERS,
)


def test_canonical_symbol_indices():
    assert canonical_symbol("^NSE") == "^NSEI"
    assert canonical_symbol("BANKNIFTY") == "^NSEBANK"
    assert canonical_symbol("^BANKNIFTY") == "^NSEBANK"
    assert canonical_symbol("NIFTY 50") == "^NSEI"
    assert canonical_symbol("NIFTYMETAL.NS") == "^CNXMETAL"
    assert canonical_symbol("INDIA VIX") == "^INDIAVIX"
    assert canonical_symbol("SENSEX") == "^BSESN"


def test_canonical_symbol_us_ns_stripping():
    # If callers append .NS to US tickers, canonical_symbol strips it
    assert canonical_symbol("AAPL.NS") == "AAPL"
    assert canonical_symbol("MSFT.NS") == "MSFT"
    assert canonical_symbol("NVDA.NS") == "NVDA"
    assert canonical_symbol("TSLA.NS") == "TSLA"


def test_canonical_symbol_indian_equity():
    assert canonical_symbol("RELIANCE.NS") == "RELIANCE.NS"
    assert canonical_symbol("TCS.NS") == "TCS.NS"


def test_dead_letter_ticker_suppression():
    # Known delisted stocks from active_error_stream.jsonl
    assert is_dead_letter_ticker("SIPAPER.NS") is True
    assert is_dead_letter_ticker("LAKSELECON.NS") is True
    assert is_dead_letter_ticker("DEEPAKSPIN.NS") is True
    assert is_dead_letter_ticker("SUPER.NS") is True
    assert is_dead_letter_ticker("ASOCSTONE.NS") is True
    assert is_dead_letter_ticker("RELIANCE.NS") is False


def test_dynamic_dead_letter_recording():
    fake_ticker = "NONEXISTENT_DELISTED_TICKER.NS"
    assert is_dead_letter_ticker(fake_ticker) is False

    record_dead_letter_failure(fake_ticker)
    assert is_dead_letter_ticker(fake_ticker) is True


def test_fetch_live_quote_dead_letter_no_network():
    # Dead letter ticker should return immediately without making any network calls
    with patch("yfinance.Ticker") as mock_ticker:
        res = fetch_live_quote("SIPAPER.NS")
        mock_ticker.assert_not_called()
        assert res["ticker"] == "SIPAPER.NS"
        assert res["current_price"] is None
        assert res["is_live"] is False


def test_fetch_prices_dead_letter_suppression():
    settings = Settings()
    with patch("yfinance.download") as mock_download:
        df = fetch_prices("SUPER.NS", settings=settings)
        mock_download.assert_not_called()
        assert df is not None


def test_fetch_batch_live_quotes_skips_dead_letter_network_calls():
    # Batch live quote should exclude dead-letter tickers from network dispatch
    with patch("earnings_engine.data.prices.fetch_live_quote") as mock_single:
        mock_single.return_value = {"ticker": "RELIANCE.NS", "current_price": 2500.0}
        with patch("earnings_engine.data.prices._fetch_yfinance_batch_quotes", return_value={}):
            results = fetch_batch_live_quotes(["SIPAPER.NS", "RELIANCE.NS"], force=True)
            assert "SIPAPER.NS" in results
            assert "RELIANCE.NS" in results
            assert results["SIPAPER.NS"]["current_price"] is None
            # Only RELIANCE.NS should have reached mock_single worker fallback, SIPAPER was suppressed
            mock_single.assert_called_once()
            call_arg = mock_single.call_args[0][0]
            assert call_arg == "RELIANCE.NS"
