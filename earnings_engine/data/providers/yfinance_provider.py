"""Yahoo Finance data provider adapter (yfinance).

Primary provider for US equities, and reliable fallback for Indian equities.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from earnings_engine.data.providers.base import DataProvider

logger = logging.getLogger("earnings_engine.data.providers.yfinance")


class YFinanceProvider(DataProvider):
    """Yahoo Finance market data adapter."""

    @property
    def name(self) -> str:
        return "yfinance"

    @property
    def is_available(self) -> bool:
        try:
            import yfinance
            return True
        except ImportError:
            return False

    @staticmethod
    def _normalize_symbol(ticker: str) -> str:
        sym = ticker.strip().upper()
        index_map = {
            "NIFTY": "^NSEI",
            "NIFTY50": "^NSEI",
            "NIFTY 50": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "NIFTY BANK": "^NSEBANK",
            "NIFTYIT": "^CNXIT",
            "NIFTY IT": "^CNXIT",
        }
        if sym in index_map:
            return index_map[sym]
        return sym

    def fetch_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        import yfinance as yf

        sym = self._normalize_symbol(ticker)
        try:
            stock = yf.Ticker(sym)
            kwargs: dict[str, Any] = {"interval": interval, "auto_adjust": False}
            if start_date:
                kwargs["start"] = start_date
            if end_date:
                kwargs["end"] = end_date
            else:
                kwargs["period"] = "max" if not start_date else None

            df = stock.history(**{k: v for k, v in kwargs.items() if v is not None})
            if df.empty:
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            df.columns = df.columns.str.lower()
            cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
            df = df[cols].copy()
            df.index = df.index.astype(str).str[:10]
            df.index.name = "date"
            return df
        except Exception as e:
            logger.warning("yfinance fetch_ohlcv failed for %s: %s", ticker, e)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        import yfinance as yf

        sym = self._normalize_symbol(ticker)
        try:
            t = yf.Ticker(sym)
            price = None
            if hasattr(t, "fast_info"):
                price = getattr(t.fast_info, "last_price", None) or getattr(t.fast_info, "previous_close", None)
            if price is None:
                hist = t.history(period="5d")
                if not hist.empty and "Close" in hist.columns:
                    price = float(hist["Close"].iloc[-1])

            return {
                "symbol": sym,
                "price": float(price) if price is not None else None,
                "provider": "yfinance",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning("yfinance fetch_quote failed for %s: %s", ticker, e)
            return {"symbol": sym, "price": None, "provider": "yfinance", "error": str(e)}
