"""Direct NSE Market Data Provider utilizing nselib and jugaad-data.

Provides direct access to official NSE archives without requiring API keys:
- Bulk daily Bhavcopy (downloads all ~2,400 NSE equities in one request)
- Historical equity price series directly from NSE
- Real-time and historical Option Chain data (strikes, OI, PCR, IV)
- Official NSE index historical values (NIFTY 50, NIFTY BANK, NIFTY IT)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from earnings_engine.data.providers.base import DataProvider

logger = logging.getLogger("earnings_engine.data.providers.nse")


class NSEDirectProvider(DataProvider):
    """Direct NSE archive adapter via nselib and jugaad-data."""

    @property
    def name(self) -> str:
        return "nse_direct"

    @property
    def is_available(self) -> bool:
        """Check if either nselib or jugaad-data is installed."""
        try:
            import nselib
            return True
        except ImportError:
            pass
        try:
            import jugaad_data
            return True
        except ImportError:
            pass
        return False

    def fetch_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch historical equity data directly from NSE archives."""
        clean_symbol = ticker.upper().replace(".NS", "")
        end_str = end_date or datetime.now().strftime("%Y-%m-%d")

        # 1. Try nselib capital_market
        try:
            import nselib
            from nselib import capital_market
            from earnings_engine.rate_limits import record_request

            # Convert YYYY-MM-DD to DD-MM-YYYY required by nselib
            from_dt = datetime.strptime(start_date[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
            to_dt = datetime.strptime(end_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")

            try:
                record_request("nse")
            except Exception:
                pass

            raw_df = capital_market.price_volume_and_deliverable_position_data(
                symbol=clean_symbol,
                from_date=from_dt,
                to_date=to_dt,
            )

            if raw_df is not None and not raw_df.empty:
                df = raw_df.copy()
                df.columns = df.columns.str.strip().str.lower()
                rename_map = {
                    "openprice": "open",
                    "highprice": "high",
                    "lowprice": "low",
                    "closeprice": "close",
                    "totaltradedquantity": "volume",
                    "date": "date",
                }
                df = df.rename(columns=rename_map)

                if "date" in df.columns:
                    # Convert date to standard YYYY-MM-DD
                    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
                    df = df.set_index("date").sort_index()

                cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
                df = df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
                return df
        except Exception as e:
            logger.debug("nselib fetch_ohlcv failed for %s: %s", clean_symbol, e)

        # 2. Try jugaad-data
        try:
            from jugaad_data.nse import stock_df
            from earnings_engine.rate_limits import record_request
            from_d = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
            to_d = datetime.strptime(end_str[:10], "%Y-%m-%d").date()

            try:
                record_request("jugaad_data")
            except Exception:
                pass

            raw_df = stock_df(symbol=clean_symbol, from_date=from_d, to_date=to_d, series="EQ")
            if raw_df is not None and not raw_df.empty:
                df = raw_df.copy()
                df.columns = df.columns.str.strip().str.lower()
                rename_map = {
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                    "date": "date",
                }
                df = df.rename(columns=rename_map)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                    df = df.set_index("date").sort_index()

                cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
                return df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
        except Exception as e:
            logger.debug("jugaad-data fetch_ohlcv failed for %s: %s", clean_symbol, e)

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch latest live quote for an NSE stock."""
        clean_symbol = ticker.upper().replace(".NS", "")

        # Try nselib
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("nse")
            except Exception:
                pass
            import nselib
            from nselib import capital_market
            data = capital_market.market_watch_all_indices()
            # Try getting price from quote
            df = capital_market.bhav_copy_equities(datetime.now().strftime("%d-%m-%Y"))
            if df is not None and not df.empty:
                match = df[df["SYMBOL"] == clean_symbol]
                if not match.empty:
                    p = float(match["CLOSE"].iloc[0])
                    return {
                        "symbol": f"{clean_symbol}.NS",
                        "price": p,
                        "provider": "nse_direct",
                        "timestamp": datetime.now().isoformat(),
                    }
        except Exception:
            pass

        return {"symbol": f"{clean_symbol}.NS", "price": None, "provider": "nse_direct"}

    def fetch_bhavcopy(self, date_str: str) -> pd.DataFrame:
        """Fetch bulk daily bhavcopy from NSE for all traded equities.

        Parameters
        ----------
        date_str:
            Date in 'YYYY-MM-DD' format.

        Returns
        -------
        DataFrame with columns: ['ticker', 'open', 'high', 'low', 'close', 'volume']
        """
        # Try nselib bhav_copy_equities
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("nse")
            except Exception:
                pass
            import nselib
            from nselib import capital_market

            d_fmt = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
            df = capital_market.bhav_copy_equities(d_fmt)

            if df is not None and not df.empty:
                df = df.copy()
                df.columns = df.columns.str.strip().str.upper()

                # Filter EQ series
                if "SERIES" in df.columns:
                    df = df[df["SERIES"] == "EQ"]

                df["ticker"] = df["SYMBOL"].astype(str) + ".NS"
                df = df.rename(columns={
                    "OPEN": "open",
                    "HIGH": "high",
                    "LOW": "low",
                    "CLOSE": "close",
                    "TOTTRDQTY": "volume",
                })
                cols = ["ticker", "open", "high", "low", "close", "volume"]
                return df[[c for c in cols if c in df.columns]].dropna(subset=["close"])
        except Exception as e:
            logger.debug("nselib bhavcopy failed for date %s: %s", date_str, e)

        # Try jugaad-data bhavcopy
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("jugaad_data")
            except Exception:
                pass
            from jugaad_data.nse import bhavcopy_save, bhavcopy_fo_save
            d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            from jugaad_data.nse.history import bhavcopy_raw
            raw_csv = bhavcopy_raw(d)
            if raw_csv:
                import io
                df = pd.read_csv(io.StringIO(raw_csv))
                df.columns = df.columns.str.strip().str.upper()
                if "SERIES" in df.columns:
                    df = df[df["SERIES"] == "EQ"]
                df["ticker"] = df["SYMBOL"].astype(str) + ".NS"
                df = df.rename(columns={
                    "OPEN": "open",
                    "HIGH": "high",
                    "LOW": "low",
                    "CLOSE": "close",
                    "TOTTRDQTY": "volume",
                })
                cols = ["ticker", "open", "high", "low", "close", "volume"]
                return df[[c for c in cols if c in df.columns]].dropna(subset=["close"])
        except Exception as e:
            logger.debug("jugaad-data bhavcopy failed for %s: %s", date_str, e)

        return pd.DataFrame(columns=["ticker", "open", "high", "low", "close", "volume"])

    def fetch_option_chain(self, symbol: str, expiry_date: str | None = None) -> dict[str, Any]:
        """Fetch real-time / archival Option Chain data for an equity or index."""
        clean_symbol = symbol.upper().replace(".NS", "")
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("nse")
            except Exception:
                pass
            import nselib
            from nselib import capital_market

            # Query nselib derivatives/options if available
            try:
                from nselib import derivatives
                oc = derivatives.nse_live_option_chain(clean_symbol)
                if oc is not None and not oc.empty:
                    return {
                        "symbol": clean_symbol,
                        "records_count": len(oc),
                        "data": oc.to_dict(orient="records"),
                        "provider": "nselib_derivatives",
                    }
            except Exception:
                pass
        except Exception as e:
            logger.debug("Option chain fetch failed for %s: %s", clean_symbol, e)

        return {
            "symbol": clean_symbol,
            "records_count": 0,
            "data": [],
            "provider": "nse_direct",
        }

    def fetch_index_data(self, index_name: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
        """Fetch historical index values (e.g. NIFTY 50, NIFTY BANK)."""
        idx_clean = index_name.upper()
        end_str = end_date or datetime.now().strftime("%Y-%m-%d")

        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("jugaad_data")
            except Exception:
                pass
            from jugaad_data.nse import index_df
            from_d = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
            to_d = datetime.strptime(end_str[:10], "%Y-%m-%d").date()

            raw_df = index_df(symbol=idx_clean, from_date=from_d, to_date=to_d)
            if raw_df is not None and not raw_df.empty:
                df = raw_df.copy()
                df.columns = df.columns.str.strip().str.lower()
                if "historicaldate" in df.columns:
                    df["date"] = pd.to_datetime(df["historicaldate"]).dt.strftime("%Y-%m-%d")
                    df = df.set_index("date").sort_index()
                cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
                return df[cols].apply(pd.to_numeric, errors="coerce")
        except Exception as e:
            logger.debug("jugaad-data index fetch failed for %s: %s", idx_clean, e)

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
