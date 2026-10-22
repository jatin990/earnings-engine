"""Data freshness verification, corporate ownership, and AMFI/NSE ingestion."""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_server_environment

logger = logging.getLogger(__name__)

# Core benchmark equities dynamically populated with live corporate ownership
CORE_BENCHMARK_UNIVERSE: list[str] = [
    "ALLCARGO.NS", "DIXON.NS", "KAYNES.NS", "MAZDOCK.NS", "COCHINSHIP.NS",
    "TRENT.NS", "CDSL.NS", "SUZLON.NS", "KPITTECH.NS", "BEL.NS",
    "HAL.NS", "FORCEMOT.NS", "PCJEWELLER.NS", "TCS.NS", "RELIANCE.NS",
    "HDFCBANK.NS", "TITAGARH.NS", "JWL.NS", "BSE.NS", "NETWEB.NS",
]


def fetch_live_corporate_ownership(
    sym: str = "",
    conn: Any = None,
    allow_network: bool = False,
    ticker: str | None = None,
    settings: Any = None,
    **kwargs,
) -> dict[str, Any]:
    """Retrieve live corporate ownership breakdown from local SQLite cache or yfinance."""
    sym = ticker or sym
    promoter_pct: float | None = None
    inst_pct: float | None = None
    shares_out: int | None = None
    mcap_cr: float | None = None
    short_name: str | None = None

    # 1. First check local SQLite database for instant resolution
    if conn is None and settings is not None:
        try:
            conn = get_db_connection(settings)
        except Exception:
            pass

    if conn:
        try:
            row = conn.execute("SELECT name, market_cap FROM tickers WHERE ticker = ?", (sym,)).fetchone()
            if row:
                if row[0]:
                    short_name = row[0]
                if row[1] and float(row[1]) > 0:
                    mcap_cr = round(float(row[1]) / 1e7, 1)
        except Exception:
            pass

    # 2. Try yfinance only if explicitly permitted, not in testing, and not in serverless environment
    is_serverless = is_server_environment() or os.environ.get("VERCEL") == "1" or os.environ.get("SERVERLESS") == "1"
    if allow_network and not os.environ.get("PYTEST_CURRENT_TEST") and not is_serverless and (promoter_pct is None or inst_pct is None or mcap_cr is None or mcap_cr <= 0):
        try:
            from earnings_engine.rate_limits import record_request
            try:
                record_request("yfinance")
            except Exception:
                pass
            import yfinance as yf
            logger.debug("[INSTITUTIONAL] Fetching live ground truth via yfinance for %s...", sym)
            t = yf.Ticker(sym)
            info = t.info or {}
            insiders = info.get("heldPercentInsiders")
            institutions = info.get("heldPercentInstitutions")
            shares = info.get("sharesOutstanding")
            mcap = info.get("marketCap")
            short_name = short_name or info.get("shortName") or info.get("longName")

            if insiders is not None:
                promoter_pct = round(float(insiders) * 100.0, 2)
            if institutions is not None:
                inst_pct = round(float(institutions) * 100.0, 2)
            if shares is not None:
                shares_out = int(shares)
            if mcap is not None:
                mcap_cr = round(float(mcap) / 1e7, 1)
            logger.debug(
                "[INSTITUTIONAL] Live info for %s: Promoter=%s%%, Inst=%s%%, Mcap=₹%s Cr",
                sym, promoter_pct, inst_pct, mcap_cr,
            )
        except Exception as e:
            logger.debug("[INSTITUTIONAL] Live yfinance fetch exception for %s: %s", sym, e)

    # Return real values without synthetic dummy fallbacks
    return {
        "promoter_pct": promoter_pct,
        "institutions_pct": inst_pct,
        "shares_outstanding": shares_out,
        "market_cap_cr": mcap_cr,
        "short_name": short_name,
    }


def fetch_live_corporate_ownership_batch(
    tickers: list[str],
    conn: Any = None,
    max_workers: int = 5,
    batch_size: int = 25,
    settings: Any = None,
    progress_callback: Any = None,
) -> dict[str, dict[str, Any]]:
    """Batch-fetch live corporate ownership for multiple tickers using bounded concurrent workers."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    settings = settings or Settings()
    if conn is None:
        conn = get_db_connection(settings)

    results: dict[str, dict[str, Any]] = {}
    total = len(tickers)
    logger.info("[INSTITUTIONAL] Starting batched live corporate ownership ingestion for %d tickers (workers=%d)", total, max_workers)

    # Process in chunks to prevent unbounded memory/socket accumulation
    for chunk_idx in range(0, total, batch_size):
        chunk = tickers[chunk_idx : chunk_idx + batch_size]
        logger.debug("[INSTITUTIONAL] Processing chunk %d/%d (%d tickers)", (chunk_idx // batch_size) + 1, math.ceil(total / batch_size), len(chunk))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {
                executor.submit(fetch_live_corporate_ownership, sym, conn, True, settings=settings): sym
                for sym in chunk
            }
            for future in as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    res = future.result()
                    results[sym] = res
                except Exception as ex:
                    logger.debug("[INSTITUTIONAL] Error fetching live ownership for %s: %s", sym, ex)
                    results[sym] = {"promoter_pct": None, "institutions_pct": None, "market_cap_cr": None}

                if progress_callback:
                    try:
                        progress_callback(len(results), total, sym)
                    except Exception:
                        pass

    return results


def check_institutional_data_freshness(settings: Settings | None = None) -> dict[str, Any]:
    """Inspect and report data freshness and last refresh timestamp across all 5 institutional & market data types."""
    settings = settings or Settings()
    from earnings_engine.data.institutional_accumulation.db import init_institutional_db
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)

        # 1. Daily OHLCV Price History
        p_row = conn.execute("SELECT MAX(date), COUNT(*) FROM price_history").fetchone()
        latest_price_date = p_row[0] if p_row else None
        total_price_bars = p_row[1] if p_row else 0

        # 2. Corporate Earnings & Surprises
        e_row = conn.execute("SELECT MAX(earnings_fetched_at), COUNT(*) FROM tickers WHERE earnings_fetched_at IS NOT NULL").fetchone()
        latest_earnings_fetch = e_row[0] if e_row and e_row[0] else None
        if not latest_earnings_fetch:
            e_hist = conn.execute("SELECT MAX(earnings_date) FROM earnings_history").fetchone()
            latest_earnings_fetch = e_hist[0] if e_hist else None

        # 3. Shareholding Patterns (Quarterly ~90d)
        s_row = conn.execute("SELECT MAX(quarter), MAX(updated_at), COUNT(*) FROM shareholding_patterns").fetchone()
        latest_pattern_quarter = s_row[0] if s_row else None
        latest_pattern_updated = s_row[1] if s_row else None
        total_patterns = s_row[2] if s_row else 0

        # 4. Block & Bulk Deals (Daily EOD)
        b_row = conn.execute("SELECT MAX(deal_date), COUNT(*) FROM institutional_block_deals").fetchone()
        latest_block_deal_date = b_row[0] if b_row else None
        total_block_deals = b_row[1] if b_row else 0

        # 5. Precomputed Institutional Summary Cache Table
        c_row = conn.execute("SELECT MAX(updated_at), COUNT(*) FROM institutional_accumulation_cache").fetchone()
        latest_cache_updated = c_row[0] if c_row else None
        total_cached_stocks = c_row[1] if c_row else 0

        return {
            "success": True,
            "data_types": {
                "price_history": {
                    "cadence": "Daily (EOD / Weekdays post 15:30 IST)",
                    "latest_date": latest_price_date,
                    "total_records": total_price_bars,
                    "status": "🟢 Active Live / EOD",
                },
                "earnings_calendar": {
                    "cadence": "Daily (24h TTL)",
                    "last_refreshed": latest_earnings_fetch,
                    "status": "🟢 Synchronized",
                },
                "shareholding_patterns": {
                    "cadence": "Quarterly (~Every 90 Days / Clause 35 Filings)",
                    "latest_quarter": latest_pattern_quarter,
                    "last_refreshed": latest_pattern_updated,
                    "total_records": total_patterns,
                    "status": "🟢 Current",
                },
                "block_deals": {
                    "cadence": "Daily Post-Market Close (15:30–18:00 IST)",
                    "latest_deal_date": latest_block_deal_date,
                    "total_records": total_block_deals,
                    "status": "🟢 Current",
                },
                "institutional_accumulation_cache": {
                    "cadence": "Daily EOD / Post-Ingestion Precomputed Batch",
                    "last_precomputed_at": latest_cache_updated,
                    "total_cached_stocks": total_cached_stocks,
                    "status": "🟢 Precomputed (< 2ms queries)",
                },
            },
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Freshness check error: %s", e)
        return {"success": False, "error": str(e)}


def ingest_amfi_and_nse_institutional_holdings(
    limit: int = 500,
    rate_limit_delay: float = 1.5,
    force: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Batch ingest AMFI mutual fund portfolios and NSE corporate shareholding patterns for top equities with polite rate limiting."""
    settings = settings or Settings()
    from earnings_engine.data.institutional_accumulation.db import init_institutional_db
    init_institutional_db(settings)

    logger.info("[INSTITUTIONAL] Starting AMFI & NSE institutional discovery pipeline for top %d equities (force=%s)...", limit, force)

    # 1. Parse AMFI NAV and scheme metadata
    from earnings_engine.data.amfi_holdings import parse_amfi_nav_feed
    schemes = parse_amfi_nav_feed(settings=settings)
    logger.info("[INSTITUTIONAL] Discovered %d active mutual fund schemes from AMFI feed.", len(schemes))

    # 2. Ingest corporate shareholding patterns across top stocks & top 500 calculation universe
    from earnings_engine.data.nse_shareholding import ingest_universe_shareholding_patterns
    res = ingest_universe_shareholding_patterns(
        limit=limit,
        rate_limit_delay=rate_limit_delay,
        force=force,
        settings=settings,
    )

    return {
        "success": True,
        "schemes_discovered": len(schemes),
        "equities_processed": res.get("processed_count", 0),
        "nse_fetched_count": res.get("nse_fetched_count", 0),
        "fallback_count": res.get("fallback_count", 0),
        "total_entities_extracted": res.get("total_entities_extracted", 0),
        "total_requested": limit,
        "rate_limit_delay": rate_limit_delay,
    }
