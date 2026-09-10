"""Yahoo Finance data provider adapter (yfinance).

Primary provider for US equities, and reliable fallback for Indian equities.
"""

from __future__ import annotations

import logging
import time
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
        try:
            from earnings_engine.rate_limits import record_request
            record_request("yfinance")
        except Exception:
            pass

        sym = self._normalize_symbol(ticker)
        logger.info("[YF:REQ] yf.download(symbol=%s, start=%s, end=%s, interval=%s)", sym, start_date, end_date, interval)
        t0 = time.perf_counter()
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False, auto_adjust=False)
            if df is None or df.empty:
                stock = yf.Ticker(sym)
                kwargs: dict[str, Any] = {"interval": interval, "auto_adjust": False}
                if start_date:
                    kwargs["start"] = start_date
                if end_date:
                    kwargs["end"] = end_date
                df = stock.history(**{k: v for k, v in kwargs.items() if v is not None})

            elapsed_ms = (time.perf_counter() - t0) * 1000

            if df is None or df.empty:
                logger.info("[YF:RESP] yf.download(%s) -> 0 rows (%.1fms)", sym, elapsed_ms)
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0].lower() if isinstance(col, tuple) else str(col).lower() for col in df.columns]
            else:
                df.columns = df.columns.str.lower()

            cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
            res_df = df[cols].copy()
            res_df.index = pd.to_datetime(res_df.index).astype(str).str[:10]
            res_df.index.name = "date"
            logger.info("[YF:RESP] yf.download(%s) -> %d rows (%.1fms)", sym, len(res_df), elapsed_ms)
            return res_df
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning("[YF:FAIL] yfinance fetch_ohlcv failed for %s after %.1fms: %s", ticker, elapsed_ms, e)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        import yfinance as yf
        try:
            from earnings_engine.rate_limits import record_request
            record_request("yfinance")
        except Exception:
            pass

        sym = self._normalize_symbol(ticker)
        logger.info("[YF:REQ] yf.Ticker(%s) quote", sym)
        t0 = time.perf_counter()
        try:
            t = yf.Ticker(sym)
            price = None
            if hasattr(t, "fast_info"):
                price = getattr(t.fast_info, "last_price", None) or getattr(t.fast_info, "previous_close", None)
            if price is None:
                hist = t.history(period="5d")
                if not hist.empty and "Close" in hist.columns:
                    price = float(hist["Close"].iloc[-1])

            elapsed_ms = (time.perf_counter() - t0) * 1000
            p_val = float(price) if price is not None else None
            logger.info("[YF:RESP] yf.Ticker(%s) price=%s (%.1fms)", sym, f"{p_val:.2f}" if p_val is not None else "None", elapsed_ms)

            return {
                "symbol": sym,
                "price": p_val,
                "provider": "yfinance",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning("[YF:FAIL] yfinance fetch_quote failed for %s after %.1fms: %s", ticker, elapsed_ms, e)
            return {"symbol": sym, "price": None, "provider": "yfinance", "error": str(e)}
