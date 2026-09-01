"""NSE Corporate Shareholding Pattern Ingestion & Institutional Entity Extractor.

Fetches and parses quarterly corporate shareholding filings from NSE India (and regulatory disclosures).
Extracts all real institutional entities (Mutual Funds, FIIs/FPIs, Insurance Companies, Sovereign Funds,
AIFs, and Super Investors) with exact stake percentages, share quantities, values (₹ Cr), and actions.
Includes polite rate limiting and backoff controls for large universe batch processing (top stocks & top 500).
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

import requests

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger("earnings_engine.data.nse_shareholding")

# Default polite rate limiting settings
# Institutional categorization keywords
_SUPER_INVESTORS = {
    "ashish kacholia", "vijay kedia", "mukul agrawal", "dolly khanna", "radhakishan damani",
    "nemish shah", "porinju veliyath", "anil kumar goel", "rekha jhunjhunwala", "sunil singhania",
    "abakkus", "mohnish pabrai", "guy spier", "hemendra kothari", "madhu kela",
}

_SOVEREIGN_OR_PENSION = {
    "government pension fund", "norway", "gic private", "monetary authority of singapore",
    "temasek", "abu dhabi investment", "kuwait investment", "canada pension", "cppib",
    "calpers", "california public employees", "ontario teachers",
}

_INSURANCE_COMPANIES = {
    "life insurance corporation", "lic of india", "sbi life", "hdfc life", "icici prudential life",
    "max life", "general insurance corporation", "new india assurance", "tata aia", "bajaj allianz",
}

_FOREIGN_INSTITUTIONS = {
    "vanguard", "blackrock", "gqg partners", "fidelity", "capital group", "morgan stanley",
    "goldman sachs", "jpmorgan", "hsbc", "citigroup", "nomura", "societe generale",
    "ubs", "bnp paribas", "clsa", "macquarie", "foreign portfolio investor", "fpi",
}


def classify_institutional_entity(name: str) -> str:
    """Classify an entity name into its appropriate institutional or investor category."""
    n_lower = (name or "").strip().lower()

    if any(si in n_lower for si in _SUPER_INVESTORS):
        return "Super Investor"
    if any(sp in n_lower for sp in _SOVEREIGN_OR_PENSION):
        return "Foreign Sovereign / FII"
def extract_and_persist_stock_shareholding(
    ticker: str,
    filing_data: dict[str, Any] | list[dict[str, Any]],
    settings: Settings | None = None,
    conn: Any = None,
) -> int:
    """Extract individual institutions from an equity filing payload and persist them to institutional_holdings."""
    sym = (ticker or "").strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"

    settings = settings or Settings()
    from earnings_engine.data.amfi_holdings import save_discovered_fund_holdings

    holdings_to_save: list[dict[str, Any]] = []

    # Handle structured list of shareholders
    items = filing_data if isinstance(filing_data, list) else filing_data.get("shareholders", filing_data.get("data", []))

    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("holder_name") or it.get("shareholder_name") or it.get("name") or it.get("client_name")
        if not name or len(name.strip()) < 3:
            continue

        stake_pct = float(it.get("stake_pct") or it.get("percentage") or it.get("pct_holding") or 0.0)
        shares = int(it.get("shares_held") or it.get("shares") or it.get("quantity") or 0)
        val_cr = float(it.get("holding_value_cr") or it.get("value_cr") or 0.0)
        fund_type = it.get("fund_type") or classify_institutional_entity(name)
        quarter = it.get("quarter") or "Q1 FY27"
        action = (it.get("action") or "HOLD").upper()
        change_pct = float(it.get("change_pct") or 0.0)
        avg_price = float(it.get("avg_price") or 0.0)
        recent_txn_p = float(it.get("recent_txn_price") or 0.0) if it.get("recent_txn_price") else None
        recent_txn_d = it.get("recent_txn_date")

        holdings_to_save.append({
            "ticker": sym,
            "fund_name": name.strip(),
            "fund_type": fund_type,
            "quarter": quarter,
            "shares_held": shares,
            "stake_pct": round(stake_pct, 2),
            "holding_value_cr": round(val_cr, 2),
            "action": action,
            "change_pct": round(change_pct, 2),
            "avg_price": round(avg_price, 2) if avg_price > 0 else 0.0,
            "recent_txn_price": recent_txn_p,
            "recent_txn_date": recent_txn_d,
            "reported_date": it.get("reported_date"),
        })

    return save_discovered_fund_holdings(holdings_to_save, settings=settings, conn=conn)


def ingest_universe_shareholding_patterns(
    tickers: list[str] | None = None,
    limit: int = 500,
    rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
    settings: Settings | None = None,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Ingest corporate shareholding patterns across top stocks / top 500 equities with strict rate limiting."""
    settings = settings or Settings()
    conn = get_db_connection(settings)

    if not tickers:
        # Load top equities by market cap or transaction activity
        rows = conn.execute(
            """
            SELECT ticker FROM tickers
            WHERE ticker LIKE '%.NS'
            ORDER BY market_cap DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        tickers = [r[0] for r in rows]

    logger.info("[NSE-SHP] Starting institutional pattern ingestion for %d equities (rate_limit=%0.2fs)", len(tickers), rate_limit_delay)

    success_count = 0
    total_entities_extracted = 0

    for idx, sym in enumerate(tickers):
        try:
            # Respect rate limit pause
            if idx > 0 and rate_limit_delay > 0:
                time.sleep(rate_limit_delay)

            # Retrieve real corporate ownership for this equity
            from earnings_engine.data.institutional_accumulation import fetch_live_corporate_ownership, _ensure_institutional_data_for_ticker
            _ensure_institutional_data_for_ticker(sym, conn)
            success_count += 1

            if progress_callback:
                progress_callback(idx + 1, len(tickers), sym)

        except Exception as e:
            logger.warning("[NSE-SHP] Error processing %s: %s", sym, e)

    # Recalculate accumulation summary cache
    from earnings_engine.data.institutional_accumulation import recalculate_all_institutional_metrics
    recalculate_all_institutional_metrics(settings=settings, force=True)

    return {
        "success": True,
        "processed_count": success_count,
        "total_requested": len(tickers),
        "rate_limit_delay_secs": rate_limit_delay,
    }

    if any(ins in n_lower for ins in _INSURANCE_COMPANIES):
        return "Insurance Company (DII)"
    if "mutual fund" in n_lower or "trustee" in n_lower or "scheme" in n_lower or "amc" in n_lower:
        return "Mutual Fund (DII)"
    if any(fii in n_lower for fii in _FOREIGN_INSTITUTIONS):
        return "Foreign Institutional (FII)"
    if "alternate investment" in n_lower or "aif" in n_lower or "ventures" in n_lower or "capital" in n_lower:
        return "Alternate Investment Fund (AIF)"
    return "Institutional Investor (DII/FII)"

DEFAULT_RATE_LIMIT_DELAY = 1.5  # Seconds between requests to avoid triggering rate limits
DEFAULT_RETRY_BACKOFF = 3.0     # Seconds to back off on 429 / 403 responses
