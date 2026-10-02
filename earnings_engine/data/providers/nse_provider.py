"""Direct NSE Market Data Provider utilizing nselib and jugaad-data.

Provides direct access to official NSE archives without requiring API keys:
- Bulk daily Bhavcopy (downloads all ~2,400 NSE equities in one request)
- Historical equity price series directly from NSE
- Real-time and historical Option Chain data (strikes, OI, PCR, IV)
- Official NSE index historical values (NIFTY 50, NIFTY BANK, NIFTY IT)
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from earnings_engine.data.providers.base import DataProvider

logger = logging.getLogger("earnings_engine.data.providers.nse")


_nselive_lock = threading.Lock()
_nselive_client: Any | None = None

NSE_INDEX_MAP: dict[str, str] = {
    "^NSEI": "NIFTY 50",
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
    "NIFTY 50": "NIFTY 50",
    "NIFTY_50": "NIFTY 50",
    "^NSEBANK": "NIFTY BANK",
    "BANKNIFTY": "NIFTY BANK",
    "NIFTYBANK": "NIFTY BANK",
    "NIFTY BANK": "NIFTY BANK",
    "NIFTY_BANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
    "NIFTYIT": "NIFTY IT",
    "NIFTY IT": "NIFTY IT",
    "NIFTY_IT": "NIFTY IT",
    "^CNXFIN": "NIFTY FINANCIAL SERVICES",
    "FINNIFTY": "NIFTY FINANCIAL SERVICES",
    "NIFTY FIN SERVICE": "NIFTY FINANCIAL SERVICES",
    "NIFTY FINANCIAL SERVICES": "NIFTY FINANCIAL SERVICES",
    "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
    "NIFTY MIDCAP SELECT": "NIFTY MIDCAP SELECT",
    "^NSEMDCP50": "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 50": "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100": "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150": "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 50": "NIFTY SMALLCAP 50",
    "NIFTY SMALLCAP 100": "NIFTY SMALLCAP 100",
    "NIFTY SMALLCAP 250": "NIFTY SMALLCAP 250",
    "NIFTY NEXT 50": "NIFTY NEXT 50",
    "NIFTYNXT50": "NIFTY NEXT 50",
    "NIFTY AUTO": "NIFTY AUTO",
    "NIFTY PHARMA": "NIFTY PHARMA",
    "NIFTY METAL": "NIFTY METAL",
    "NIFTY FMCG": "NIFTY FMCG",
    "NIFTY ENERGY": "NIFTY ENERGY",
    "NIFTY INFRA": "NIFTY INFRA",
    "NIFTY PSE": "NIFTY PSE",
    "NIFTY PSU BANK": "NIFTY PSU BANK",
    "NIFTY PRIVATE BANK": "NIFTY PRIVATE BANK",
    "NIFTY 100": "NIFTY 100",
    "NIFTY 200": "NIFTY 200",
    "NIFTY 500": "NIFTY 500",
    "^CRSLDX": "NIFTY 500",
    "INDIA VIX": "INDIA VIX",
    "INDIAVIX": "INDIA VIX",
    "^INDIAVIX": "INDIA VIX",
}


def resolve_nse_index_name(symbol: str) -> str | None:
    """Resolve standard ticker, Yahoo symbol, or alias to canonical NSE official index name."""
    if not symbol:
        return None
    raw = symbol.strip().upper()
    clean = raw.replace(".NS", "")
    if raw in NSE_INDEX_MAP:
        return NSE_INDEX_MAP[raw]
    if clean in NSE_INDEX_MAP:
        return NSE_INDEX_MAP[clean]
    if clean.startswith("NIFTY ") or clean.startswith("INDIA "):
        return clean
    return None


def _get_nselive_client() -> Any:
    """Return a shared NSELive instance to reuse session cookies across option chain calls."""
    global _nselive_client
    if _nselive_client is None:
        with _nselive_lock:
            if _nselive_client is None:
                try:
                    from jugaad_data.nse import NSELive
                    _nselive_client = NSELive()
                except Exception as e:
                    logger.warning("[NSE:CLIENT_INIT_FAIL] Failed initializing jugaad_data NSELive: %s", e)
                    return None
    return _nselive_client


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
        """Fetch historical equity or index data directly from NSE archives."""
        # Check if ticker represents an NSE index (e.g. ^NSEBANK, ^NSEI, BANKNIFTY, NIFTY 50)
        resolved_index = resolve_nse_index_name(ticker)
        if resolved_index is not None:
            return self._fetch_index_ohlcv(resolved_index, start_date, end_date)

        clean_symbol = ticker.upper().replace(".NS", "")
        # Guard: symbols with leading caret (^) that are not recognized indices shouldn't be queried as stocks
        if clean_symbol.startswith("^"):
            logger.info("[NSE:EQUITY_BYPASS] Non-equity ticker %s skipped for stock archive query", clean_symbol)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        end_str = end_date or datetime.now().strftime("%Y-%m-%d")

        # 1. Try nselib capital_market
        from_dt = datetime.strptime(start_date[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
        to_dt = datetime.strptime(end_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
        logger.info("[NSELIB:REQ] capital_market.price_volume_and_deliverable_position_data(symbol=%s, from_date=%s, to_date=%s)", clean_symbol, from_dt, to_dt)
        t0 = time.perf_counter()
        try:
            import nselib
            from nselib import capital_market
            from earnings_engine.rate_limits import record_request

            try:
                record_request("nse")
            except Exception:
                pass

            raw_df = capital_market.price_volume_and_deliverable_position_data(
                symbol=clean_symbol,
                from_date=from_dt,
                to_date=to_dt,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000

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
                res_df = df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
                logger.info("[NSELIB:RESP] price_volume_and_deliverable_position_data(%s) -> %d rows (%.1fms)", clean_symbol, len(res_df), elapsed_ms)
                return res_df
            else:
                logger.info("[NSELIB:RESP] price_volume_and_deliverable_position_data(%s) -> 0 rows (%.1fms)", clean_symbol, elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning("[NSELIB:FAIL] price_volume_and_deliverable_position_data(%s) failed after %.1fms: %s", clean_symbol, elapsed_ms, e)

        # 2. Try jugaad-data
        from_d = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        to_d = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
        logger.info("[JUGAAD:REQ] stock_df(symbol=%s, from_date=%s, to_date=%s, series=EQ)", clean_symbol, from_d, to_d)
        t0_j = time.perf_counter()
        try:
            from jugaad_data.nse import stock_df
            from earnings_engine.rate_limits import record_request

            try:
                record_request("jugaad_data")
            except Exception:
                pass

            raw_df = stock_df(symbol=clean_symbol, from_date=from_d, to_date=to_d, series="EQ")
            elapsed_ms = (time.perf_counter() - t0_j) * 1000
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
                res_df = df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
                logger.info("[JUGAAD:RESP] stock_df(%s) -> %d rows (%.1fms)", clean_symbol, len(res_df), elapsed_ms)
                return res_df
            else:
                logger.info("[JUGAAD:RESP] stock_df(%s) -> 0 rows (%.1fms)", clean_symbol, elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0_j) * 1000
            err_msg = str(e)
            if "CH_TIMESTAMP" in err_msg and "are in the [columns]" in err_msg:
                logger.warning("[JUGAAD:FAIL] stock_df(%s) returned no historical data on NSE (symbol may be invalid, delisted, or renamed) after %.1fms", clean_symbol, elapsed_ms)
            else:
                logger.warning("[JUGAAD:FAIL] stock_df(%s) failed after %.1fms: %s", clean_symbol, elapsed_ms, e)

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _fetch_index_ohlcv(
        self,
        index_name: str,
        start_date: str,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical index values directly from NSE archives."""
        idx_clean = index_name.upper()
        end_str = end_date or datetime.now().strftime("%Y-%m-%d")

        # 1. Try nselib capital_market.index_data
        from_dt = datetime.strptime(start_date[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
        to_dt = datetime.strptime(end_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
        logger.info("[NSELIB:REQ] capital_market.index_data(index=%s, from_date=%s, to_date=%s)", idx_clean, from_dt, to_dt)
        t0 = time.perf_counter()
        try:
            import nselib
            from nselib import capital_market
            from earnings_engine.rate_limits import record_request

            try:
                record_request("nse")
            except Exception:
                pass

            raw_df = capital_market.index_data(
                index=idx_clean,
                from_date=from_dt,
                to_date=to_dt,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if raw_df is not None and not raw_df.empty:
                df = raw_df.copy()
                df.columns = df.columns.str.strip().str.lower()
                rename_map = {
                    "open_index_val": "open",
                    "high_index_val": "high",
                    "low_index_val": "low",
                    "close_index_val": "close",
                    "traded_qty": "volume",
                    "timestamp": "date",
                }
                df = df.rename(columns=rename_map)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce").dt.strftime("%Y-%m-%d")
                    df = df.set_index("date").sort_index()

                if "volume" not in df.columns:
                    df["volume"] = 0.0

                cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
                res_df = df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
                logger.info("[NSELIB:RESP] index_data(%s) -> %d rows (%.1fms)", idx_clean, len(res_df), elapsed_ms)
                return res_df
            else:
                logger.info("[NSELIB:RESP] index_data(%s) -> 0 rows (%.1fms)", idx_clean, elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning("[NSELIB:FAIL] index_data(%s) failed after %.1fms: %s", idx_clean, elapsed_ms, e)

        # 2. Try jugaad-data index_df
        from_d = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        to_d = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
        logger.info("[JUGAAD:REQ] index_df(symbol=%s, from_date=%s, to_date=%s)", idx_clean, from_d, to_d)
        t0_j = time.perf_counter()
        try:
            from jugaad_data.nse import index_df
            from earnings_engine.rate_limits import record_request

            try:
                record_request("jugaad_data")
            except Exception:
                pass

            raw_df = index_df(symbol=idx_clean, from_date=from_d, to_date=to_d)
            elapsed_ms = (time.perf_counter() - t0_j) * 1000
            if raw_df is not None and not raw_df.empty:
                df = raw_df.copy()
                df.columns = df.columns.str.strip().str.lower()
                rename_map = {
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                    "historicaldate": "date",
                }
                df = df.rename(columns=rename_map)
                if "volume" not in df.columns:
                    df["volume"] = 0.0
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                    df = df.set_index("date").sort_index()

                cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
                res_df = df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
                logger.info("[JUGAAD:RESP] index_df(%s) -> %d rows (%.1fms)", idx_clean, len(res_df), elapsed_ms)
                return res_df
            else:
                logger.info("[JUGAAD:RESP] index_df(%s) -> 0 rows (%.1fms)", idx_clean, elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0_j) * 1000
            logger.warning("[JUGAAD:FAIL] index_df(%s) failed after %.1fms: %s", idx_clean, elapsed_ms, e)

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch latest live quote for an NSE stock or index."""
        resolved_index = resolve_nse_index_name(ticker)
        if resolved_index is not None:
            # 1. Try jugaad-data live_index
            t0 = time.perf_counter()
            nse = _get_nselive_client()
            if nse is not None:
                try:
                    from earnings_engine.rate_limits import record_request
                    try:
                        record_request("nse")
                    except Exception:
                        pass
                    data = nse.live_index(resolved_index)
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    if data and isinstance(data, dict) and data.get("data"):
                        first_item = data["data"][0]
                        price = float(first_item.get("lastPrice") or 0.0)
                        if price > 0:
                            logger.info("[JUGAAD:RESP] live_index(%s) quote found price=%.2f (%.1fms)", resolved_index, price, elapsed_ms)
                            return {
                                "symbol": ticker,
                                "price": price,
                                "open": first_item.get("open"),
                                "high": first_item.get("dayHigh"),
                                "low": first_item.get("dayLow"),
                                "previous_close": first_item.get("previousClose"),
                                "change": first_item.get("change"),
                                "pChange": first_item.get("pChange"),
                                "provider": "nse_direct",
                                "timestamp": datetime.now().isoformat(),
                            }
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    logger.debug("[JUGAAD:FAIL] live_index(%s) quote failed after %.1fms: %s", resolved_index, elapsed_ms, e)

            # 2. Fallback to nselib market_watch_all_indices
            t0 = time.perf_counter()
            try:
                import nselib
                from nselib import capital_market
                from earnings_engine.rate_limits import record_request
                try:
                    record_request("nse")
                except Exception:
                    pass
                df = capital_market.market_watch_all_indices()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if df is not None and not df.empty and "index" in df.columns:
                    match = df[df["index"].str.upper() == resolved_index.upper()]
                    if match.empty and "indexSymbol" in df.columns:
                        match = df[df["indexSymbol"].str.upper() == resolved_index.upper()]
                    if not match.empty:
                        p = float(match["last"].iloc[0])
                        logger.info("[NSELIB:RESP] market_watch_all_indices(%s) found price=%.2f (%.1fms)", resolved_index, p, elapsed_ms)
                        return {
                            "symbol": ticker,
                            "price": p,
                            "provider": "nse_direct",
                            "timestamp": datetime.now().isoformat(),
                        }
            except Exception as e:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.debug("[NSELIB:FAIL] market_watch_all_indices quote failed for %s after %.1fms: %s", resolved_index, elapsed_ms, e)

            return {"symbol": ticker, "price": None, "provider": "nse_direct"}

        clean_symbol = ticker.upper().replace(".NS", "")
        if clean_symbol.startswith("^"):
            return {"symbol": ticker, "price": None, "provider": "nse_direct"}

        # Try nselib
        today_str = datetime.now().strftime("%d-%m-%Y")
        logger.info("[NSELIB:REQ] capital_market.bhav_copy_equities(date=%s) for quote %s", today_str, clean_symbol)
        t0 = time.perf_counter()
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("nse")
            except Exception:
                pass
            import nselib
            from nselib import capital_market
            df = capital_market.bhav_copy_equities(today_str)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if df is not None and not df.empty:
                match = df[df["SYMBOL"] == clean_symbol]
                if not match.empty:
                    p = float(match["CLOSE"].iloc[0])
                    logger.info("[NSELIB:RESP] bhav_copy_equities(%s) quote found price=%.2f (%.1fms)", clean_symbol, p, elapsed_ms)
                    return {
                        "symbol": f"{clean_symbol}.NS",
                        "price": p,
                        "provider": "nse_direct",
                        "timestamp": datetime.now().isoformat(),
                    }
                else:
                    logger.info("[NSELIB:RESP] bhav_copy_equities symbol %s not found in %d rows (%.1fms)", clean_symbol, len(df), elapsed_ms)
            else:
                logger.info("[NSELIB:RESP] bhav_copy_equities empty response (%.1fms)", elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning("[NSELIB:FAIL] bhav_copy_equities quote failed for %s after %.1fms: %s", clean_symbol, elapsed_ms, e)

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
        d_fmt = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
        logger.info("[NSELIB:REQ] capital_market.bhav_copy_equities(date=%s)", d_fmt)
        t0 = time.perf_counter()
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("nse")
            except Exception:
                pass
            import nselib
            from nselib import capital_market

            df = capital_market.bhav_copy_equities(d_fmt)
            elapsed_ms = (time.perf_counter() - t0) * 1000

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
                res_df = df[[c for c in cols if c in df.columns]].dropna(subset=["close"])
                logger.info("[NSELIB:RESP] bhav_copy_equities(%s) -> %d equities (%.1fms)", d_fmt, len(res_df), elapsed_ms)
                return res_df
            else:
                logger.info("[NSELIB:RESP] bhav_copy_equities(%s) -> 0 rows (%.1fms)", d_fmt, elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning("[NSELIB:FAIL] bhav_copy_equities(%s) failed after %.1fms: %s", d_fmt, elapsed_ms, e)

        # Try jugaad-data bhavcopy
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        logger.info("[JUGAAD:REQ] bhavcopy_raw(date=%s)", d)
        t0_j = time.perf_counter()
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("jugaad_data")
            except Exception:
                pass
            from jugaad_data.nse import bhavcopy_save, bhavcopy_fo_save
            from jugaad_data.nse.history import bhavcopy_raw
            raw_csv = bhavcopy_raw(d)
            elapsed_ms = (time.perf_counter() - t0_j) * 1000
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
                res_df = df[[c for c in cols if c in df.columns]].dropna(subset=["close"])
                logger.info("[JUGAAD:RESP] bhavcopy_raw(%s) -> %d equities (%.1fms)", d, len(res_df), elapsed_ms)
                return res_df
            else:
                logger.info("[JUGAAD:RESP] bhavcopy_raw(%s) -> 0 rows (%.1fms)", d, elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0_j) * 1000
            logger.warning("[JUGAAD:FAIL] bhavcopy_raw(%s) failed after %.1fms: %s", d, elapsed_ms, e)

        return pd.DataFrame(columns=["ticker", "open", "high", "low", "close", "volume"])

    def fetch_option_chain(self, symbol: str, expiry_date: str | None = None) -> dict[str, Any]:
        """Fetch real-time / archival Option Chain data for an equity or index."""
        clean_symbol = symbol.upper().replace(".NS", "")
        from earnings_engine.data.universe import is_fno_eligible
        if not is_fno_eligible(clean_symbol):
            logger.debug("[NSE:FNO_BYPASS] Symbol %s is not F&O eligible; skipping option chain network request", clean_symbol)
            return {
                "symbol": clean_symbol,
                "records_count": 0,
                "data": [],
                "provider": "nse_direct",
            }

        # 1. Primary: Query via jugaad-data NSELive (maintains primed cookies & modern headers)
        t0 = time.perf_counter()
        nse = _get_nselive_client()
        if nse is not None:
            try:
                from earnings_engine.rate_limits import record_request
                try:
                    record_request("nse")
                except Exception:
                    pass

                # Handle indices vs equities
                is_index = clean_symbol in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY") or clean_symbol.startswith("NIFTY")
                if is_index:
                    raw_chain = nse.index_option_chain(clean_symbol)
                else:
                    raw_chain = nse.equities_option_chain(clean_symbol)

                records_dict = raw_chain.get("records", {})
                all_expiries = records_dict.get("expiryDates", [])
                timestamp = records_dict.get("timestamp")
                underlying_value = records_dict.get("underlyingValue") or raw_chain.get("filtered", {}).get("underlyingValue")

                if expiry_date and all_expiries:
                    all_records = records_dict.get("data", [])
                    records = [r for r in all_records if r.get("expiryDate") == expiry_date]
                    selected_expiry = expiry_date
                else:
                    records = raw_chain.get("filtered", {}).get("data") or records_dict.get("data", [])
                    selected_expiry = all_expiries[0] if all_expiries else None

                elapsed_ms = (time.perf_counter() - t0) * 1000
                if records:
                    logger.info("[NSE:RESP] option_chain(%s, expiry=%s) -> %d strikes (%.1fms)", clean_symbol, selected_expiry, len(records), elapsed_ms)
                    return {
                        "symbol": clean_symbol,
                        "records_count": len(records),
                        "data": records,
                        "expiries": all_expiries,
                        "selected_expiry": selected_expiry,
                        "underlying_value": underlying_value,
                        "timestamp": timestamp,
                        "provider": "jugaad_data_live",
                    }
                else:
                    logger.info("[NSE:RESP] option_chain(%s) -> 0 strikes (%.1fms)", clean_symbol, elapsed_ms)
            except Exception as e:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.warning("[JUGAAD:FAIL] option_chain(%s) failed after %.1fms: %s", clean_symbol, elapsed_ms, e)
                # Reset cached client on network / session failure
                global _nselive_client
                with _nselive_lock:
                    _nselive_client = None

        # 2. Secondary fallback: nselib derivatives if available
        logger.debug("[NSELIB:REQ] derivatives.nse_live_option_chain(%s)", clean_symbol)
        t0 = time.perf_counter()
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("nse")
            except Exception:
                pass
            import nselib
            from nselib import derivatives

            oc = derivatives.nse_live_option_chain(clean_symbol)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if oc is not None and not oc.empty:
                logger.info("[NSELIB:RESP] nse_live_option_chain(%s) -> %d strikes (%.1fms)", clean_symbol, len(oc), elapsed_ms)
                return {
                    "symbol": clean_symbol,
                    "records_count": len(oc),
                    "data": oc.to_dict(orient="records"),
                    "provider": "nselib_derivatives",
                }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.debug("[NSELIB:FAIL] nse_live_option_chain(%s) failed after %.1fms: %s", clean_symbol, elapsed_ms, e)

        return {
            "symbol": clean_symbol,
            "records_count": 0,
            "data": [],
            "provider": "nse_direct",
        }

    def fetch_index_data(self, index_name: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
        """Fetch historical index values (e.g. NIFTY 50, NIFTY BANK, ^NSEBANK)."""
        resolved = resolve_nse_index_name(index_name) or index_name
        return self._fetch_index_ohlcv(resolved, start_date, end_date)
