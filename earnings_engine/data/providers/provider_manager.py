"""Central Provider Manager and Market Data Router.

Automatically selects the optimal provider based on:
- Asset market (Indian NSE vs US)
- Provider availability (NSE Direct / nselib / jugaad-data vs yfinance)
- Request type (single OHLCV, bulk daily Bhavcopy, live quotes, or Option Chain)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from earnings_engine.config import Settings, market_of
from earnings_engine.data.providers.base import DataProvider
from earnings_engine.data.providers.nse_provider import NSEDirectProvider
from earnings_engine.data.providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger("earnings_engine.data.providers.manager")


class DataProviderManager:
    """Manages active market data providers and routes data requests."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._providers: dict[str, DataProvider] = {
            "nse_direct": NSEDirectProvider(),
            "yfinance": YFinanceProvider(),
        }

    def get_provider(self, name: str) -> DataProvider | None:
        return self._providers.get(name)

    def fetch_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
        preferred_provider: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data with automatic provider fallback."""
        mkt = market_of(ticker)

        # 1. Preferred provider if specified
        if preferred_provider and preferred_provider in self._providers:
            prov = self._providers[preferred_provider]
            if prov.is_available:
                logger.info("[PROVIDER-ROUTE] Querying preferred provider '%s' for ticker=%s...", preferred_provider, ticker)
                df = prov.fetch_ohlcv(ticker, start_date, end_date, interval)
                if not df.empty:
                    logger.info("[PROVIDER-SUCCESS] Fetched %d rows from '%s' for %s", len(df), preferred_provider, ticker)
                    return df

        # 2. For Indian equities: try NSE Direct first
        if mkt == "IN":
            nse_prov = self._providers["nse_direct"]
            if nse_prov.is_available:
                logger.info("[PROVIDER-ROUTE] [NSE-Direct] Querying official NSE archives (nselib / jugaad-data) for %s...", ticker)
                df = nse_prov.fetch_ohlcv(ticker, start_date, end_date, interval)
                if not df.empty:
                    logger.info("[PROVIDER-SUCCESS] [NSE-Direct] Retrieved %d bars for %s", len(df), ticker)
                    return df
                else:
                    logger.info("[PROVIDER-FALLBACK] [NSE-Direct] returned empty for %s; falling back to yfinance", ticker)

        # 3. Fallback to yfinance
        yf_prov = self._providers["yfinance"]
        if yf_prov.is_available:
            logger.info("[PROVIDER-ROUTE] [yfinance] Querying Yahoo Finance for %s (%s to %s)...", ticker, start_date, end_date or "now")
            df = yf_prov.fetch_ohlcv(ticker, start_date, end_date, interval)
            if not df.empty:
                logger.info("[PROVIDER-SUCCESS] [yfinance] Retrieved %d bars for %s", len(df), ticker)
            return df

        logger.warning("[PROVIDER-ERROR] No available provider succeeded for ticker=%s", ticker)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch latest price snapshot with fallback."""
        mkt = market_of(ticker)
        if mkt == "IN":
            nse_prov = self._providers["nse_direct"]
            if nse_prov.is_available:
                logger.info("[PROVIDER-QUOTE] [NSE-Direct] Fetching real-time quote for %s...", ticker)
                res = nse_prov.fetch_quote(ticker)
                if res.get("price") is not None:
                    return res
                logger.info("[PROVIDER-QUOTE] [NSE-Direct] Quote empty for %s, falling back to yfinance", ticker)

        yf_prov = self._providers["yfinance"]
        logger.info("[PROVIDER-QUOTE] [yfinance] Fetching quote for %s...", ticker)
        return yf_prov.fetch_quote(ticker)

    def fetch_bhavcopy(self, date_str: str) -> pd.DataFrame:
        """Fetch bulk daily bhavcopy for all NSE equities."""
        nse_prov = self._providers["nse_direct"]
        if nse_prov.is_available:
            logger.info("[PROVIDER-BHAVCOPY] [NSE-Direct] Fetching bulk daily bhavcopy for %s...", date_str)
            return nse_prov.fetch_bhavcopy(date_str)
        logger.warning("[PROVIDER-BHAVCOPY] NSE Direct provider not available for bhavcopy on %s", date_str)
        return pd.DataFrame(columns=["ticker", "open", "high", "low", "close", "volume"])

    def fetch_bse_option_chain(self, symbol: str = "SENSEX", expiry_date: str | None = None) -> dict[str, Any]:
        """Fetch Option Chain data for BSE SENSEX derivatives from official BSE Bhavcopy."""
        import io
        import urllib.request
        from datetime import datetime, timedelta

        clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "").replace("BSE:", "").replace("^BSESN", "SENSEX").strip()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        now = datetime.now()
        df = None

        # Look back up to 7 calendar days to find the latest published BSE FO Bhavcopy
        for days_back in range(0, 7):
            target_dt = now - timedelta(days=days_back)
            if target_dt.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
                continue
            d_str = target_dt.strftime("%Y%m%d")
            url = f"https://www.bseindia.com/download/BhavCopy/Derivative/BhavCopy_BSE_FO_0_0_0_{d_str}_F_0000.CSV"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw_csv = resp.read().decode("utf-8", errors="ignore")
                    if raw_csv and len(raw_csv) > 200:
                        parsed_df = pd.read_csv(io.StringIO(raw_csv))
                        if not parsed_df.empty:
                            df = parsed_df
                            logger.info("[PROVIDER-OPTIONS] [BSE-Direct] Successfully downloaded BhavCopy for %s (%d rows)", d_str, len(df))
                            break
            except Exception as e:
                logger.debug("[PROVIDER-OPTIONS] [BSE-Direct] BhavCopy fetch attempt for %s failed: %s", d_str, e)
                continue

        if df is None or df.empty:
            logger.warning("[PROVIDER-OPTIONS] [BSE-Direct] No BSE FO Bhavcopy available for symbol %s in last 7 days", clean_sym)
            return {"symbol": clean_sym, "records_count": 0, "data": [], "expiries": [], "selected_expiry": None}

        # Filter for SENSEX index options (IDO)
        sub = df[(df["TckrSymb"].astype(str).str.upper() == clean_sym) & (df["FinInstrmTp"].astype(str).str.upper() == "IDO")]
        if sub.empty:
            logger.warning("[PROVIDER-OPTIONS] [BSE-Direct] No IDO options found for symbol %s in BSE Bhavcopy", clean_sym)
            return {"symbol": clean_sym, "records_count": 0, "data": [], "expiries": [], "selected_expiry": None}

        expiries = sorted(sub["XpryDt"].dropna().astype(str).unique().tolist())
        selected_expiry = expiry_date if (expiry_date and expiry_date in expiries) else (expiries[0] if expiries else None)

        active_df = sub[sub["XpryDt"] == selected_expiry] if selected_expiry else sub
        underlying_val = None
        if not active_df["UndrlygPric"].dropna().empty:
            try:
                underlying_val = float(active_df["UndrlygPric"].dropna().iloc[0])
            except Exception:
                underlying_val = None

        strikes_map: dict[float, dict[str, Any]] = {}
        for _, row in active_df.iterrows():
            try:
                strike = float(row.get("StrkPric") or 0)
            except Exception:
                continue
            if strike <= 0:
                continue

            if strike not in strikes_map:
                strikes_map[strike] = {
                    "strikePrice": strike,
                    "expiryDate": selected_expiry,
                    "CE": {},
                    "PE": {},
                }

            opt_type = str(row.get("OptnTp") or "").upper().strip()
            close_p = float(row.get("ClsPric") or 0.0)
            prev_p = float(row.get("PrvsClsgPric") or 0.0)
            change = close_p - prev_p
            p_change = ((change / prev_p) * 100.0) if prev_p > 0 else 0.0

            opt_data = {
                "strikePrice": strike,
                "expiryDate": selected_expiry,
                "underlying": clean_sym,
                "openInterest": int(row.get("OpnIntrst") or 0),
                "changeinOpenInterest": int(row.get("ChngInOpnIntrst") or 0),
                "totalTradedVolume": int(row.get("TtlTradgVol") or 0),
                "lastPrice": float(row.get("LastPric") or close_p),
                "change": round(change, 2),
                "pChange": round(p_change, 2),
                "totalTradedValue": float(row.get("TtlTrfVal") or 0.0),
                "underlyingValue": underlying_val,
            }
            if opt_type == "CE":
                strikes_map[strike]["CE"] = opt_data
            elif opt_type == "PE":
                strikes_map[strike]["PE"] = opt_data

        sorted_strikes = [strikes_map[k] for k in sorted(strikes_map.keys())]
        return {
            "symbol": clean_sym,
            "records_count": len(sorted_strikes),
            "data": sorted_strikes,
            "expiries": expiries,
            "selected_expiry": selected_expiry,
            "underlying_value": underlying_val,
            "timestamp": datetime.now().isoformat(),
            "provider": "bse_derivatives_bhavcopy",
        }

    def fetch_option_chain(self, symbol: str, expiry_date: str | None = None) -> dict[str, Any]:
        """Fetch Option Chain data for an NSE or BSE symbol/index."""
        clean_symbol = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
        if clean_symbol in ("SENSEX", "BSESENSEX", "^BSESN", "BSE:SENSEX"):
            logger.info("[PROVIDER-OPTIONS] [BSE-Direct] Querying Option Chain for %s (expiry=%s)...", clean_symbol, expiry_date)
            return self.fetch_bse_option_chain("SENSEX", expiry_date=expiry_date)

        nse_prov = self._providers["nse_direct"]
        if nse_prov.is_available:
            logger.info("[PROVIDER-OPTIONS] [NSE-Direct] Querying live Option Chain for %s (expiry=%s)...", symbol, expiry_date)
            return nse_prov.fetch_option_chain(symbol, expiry_date=expiry_date)
        logger.warning("[PROVIDER-OPTIONS] NSE Direct provider (nselib / jugaad-data) unavailable for Option Chain on %s", symbol)
        return {"symbol": symbol, "records_count": 0, "data": [], "expiries": [], "selected_expiry": None}

    def fetch_index_data(self, index_name: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
        """Fetch index history (NIFTY 50, NIFTY BANK, etc.)."""
        nse_prov = self._providers["nse_direct"]
        if nse_prov.is_available:
            df = nse_prov.fetch_index_data(index_name, start_date, end_date)
            if not df.empty:
                return df

        # Fallback to yfinance with ^ prefix (e.g. ^NSEI)
        sym_map = {
            "NIFTY 50": "^NSEI",
            "NIFTY BANK": "^NSEBANK",
            "NIFTY IT": "^CNXIT",
        }
        yf_sym = sym_map.get(index_name.upper(), index_name)
        return self._providers["yfinance"].fetch_ohlcv(yf_sym, start_date, end_date)


# Singleton accessor
_manager_instance: DataProviderManager | None = None


def get_data_manager(settings: Settings | None = None) -> DataProviderManager:
    """Get or create singleton DataProviderManager instance."""
    global _manager_instance
    if _manager_instance is None or settings is not None:
        _manager_instance = DataProviderManager(settings)
    return _manager_instance
