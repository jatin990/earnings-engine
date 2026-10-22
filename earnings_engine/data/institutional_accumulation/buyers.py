"""Institutional buyers query parsing, period inspection, and smart money transaction tracking."""

from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_COMMON_NAME_ALIASES: dict[str, str] = {
    "STERLITE TECH": "STLTECH.NS",
    "STERLITE TECHNOLOGIES": "STLTECH.NS",
    "STERLITE": "STLTECH.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "RELIANCE": "RELIANCE.NS",
    "INFOSYS": "INFY.NS",
    "TCS": "TCS.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "ICICI BANK": "ICICIBANK.NS",
    "STATE BANK OF INDIA": "SBIN.NS",
    "SBI": "SBIN.NS",
    "L&T": "LT.NS",
    "LARSEN & TOUBRO": "LT.NS",
    "BHARTI AIRTEL": "BHARTIARTL.NS",
    "AIRTEL": "BHARTIARTL.NS",
}


def _resolve_ticker_symbol(
    ticker_str: str,
    conn: Any = None,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """Resolve user-supplied stock name or symbol to canonical symbol and company name.

    Handles natural company queries like 'STERLITE TECH', raw symbols 'STLTECH',
    and standard tickers 'STLTECH.NS'.
    """
    raw = (ticker_str or "").strip()
    if not raw:
        return "", ""

    settings = settings or Settings()
    close_conn = False
    if conn is None:
        conn = get_db_connection(settings)
        close_conn = True

    try:
        from earnings_engine.data.names import get_name, search as search_names

        clean_upper = raw.upper()
        if clean_upper in _COMMON_NAME_ALIASES:
            canonical_sym = _COMMON_NAME_ALIASES[clean_upper]
            name = get_name(canonical_sym, settings=settings) or raw
            return canonical_sym, name

        row = conn.execute("SELECT ticker, name FROM tickers WHERE UPPER(ticker) = UPPER(?)", (raw,)).fetchone()
        if row:
            return row[0], row[1] or row[0]

        if not raw.upper().endswith((".NS", ".BO")):
            row = conn.execute("SELECT ticker, name FROM tickers WHERE UPPER(ticker) = UPPER(?)", (raw + ".NS",)).fetchone()
            if row:
                return row[0], row[1] or row[0]

        q_tokens = raw.upper().split()
        if q_tokens:
            try:
                candidate_rows = conn.execute("SELECT ticker, name FROM tickers WHERE name IS NOT NULL").fetchall()
                for t_sym, t_name in candidate_rows:
                    n_words = t_name.upper().split()
                    if all(any(nw.startswith(tok) for nw in n_words) for tok in q_tokens):
                        return t_sym, t_name
            except Exception:
                pass

        hits = search_names(raw, limit=10, settings=settings)
        if hits:
            clean_raw = raw.upper().replace(" ", "")
            for h in hits:
                sym_clean = h["symbol"].upper().replace(".NS", "").replace(".BO", "")
                if sym_clean == clean_raw:
                    return h["symbol"], h["name"]
            return hits[0]["symbol"], hits[0]["name"]

        inst_row = conn.execute(
            "SELECT ticker FROM institutional_holdings WHERE UPPER(ticker) LIKE UPPER(?) LIMIT 1",
            (f"%{raw}%",),
        ).fetchone()
        if inst_row:
            sym = inst_row[0]
            name = get_name(sym, settings=settings) or sym
            return sym, name

        fallback = raw.upper() if "." in raw else f"{raw.upper()}.NS"
        name = get_name(fallback, settings=settings) or fallback
        return fallback, name
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass


def _parse_single_query_date(s: str, is_end_date: bool = False) -> str | None:
    """Parse relative intervals, natural months, or calendar date strings into YYYY-MM-DD."""
    if not s or not s.strip():
        return None
    raw = s.strip()
    raw = re.sub(r"^(from|since|to|until)\s+", "", raw, flags=re.IGNORECASE).strip()

    m_rel = re.match(r"^(\d+)\s*([dDmMwWyY])$", raw)
    if m_rel:
        val, unit = int(m_rel.group(1)), m_rel.group(2).lower()
        now = datetime.now()
        if unit == "d":
            dt = now - timedelta(days=val)
        elif unit == "w":
            dt = now - timedelta(weeks=val)
        elif unit == "m":
            dt = now - timedelta(days=val * 30)
        elif unit == "y":
            dt = now - timedelta(days=val * 365)
        else:
            dt = now - timedelta(days=val)
        return dt.strftime("%Y-%m-%d")

    m_iso = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", raw)
    if m_iso:
        return f"{int(m_iso.group(1)):04d}-{int(m_iso.group(2)):02d}-{int(m_iso.group(3)):02d}"

    m_dmy = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", raw)
    if m_dmy:
        return f"{int(m_dmy.group(3)):04d}-{int(m_dmy.group(2)):02d}-{int(m_dmy.group(1)):02d}"

    m_my = re.match(r"^([a-zA-Z]+)[-/\s]+(\d{4})$", raw)
    if m_my:
        mon_str, yr_str = m_my.group(1).lower(), m_my.group(2)
        if mon_str in _MONTH_MAP:
            m_idx = _MONTH_MAP[mon_str]
            yr = int(yr_str)
            if is_end_date:
                last_day = calendar.monthrange(yr, m_idx)[1]
                return f"{yr:04d}-{m_idx:02d}-{last_day:02d}"
            return f"{yr:04d}-{m_idx:02d}-01"

    m_ym = re.match(r"^(\d{4})[-/](\d{1,2})$", raw)
    if m_ym:
        yr = int(m_ym.group(1))
        m_idx = int(m_ym.group(2))
        if 1 <= m_idx <= 12:
            if is_end_date:
                last_day = calendar.monthrange(yr, m_idx)[1]
                return f"{yr:04d}-{m_idx:02d}-{last_day:02d}"
            return f"{yr:04d}-{m_idx:02d}-01"

    return None


def _parse_fiscal_quarter(q: str) -> tuple[str | None, str | None, str | None]:
    """Parse Indian Fiscal Quarter (e.g. 'Q4 FY26', 'Q1 FY27') into canonical string and start/end dates."""
    if not q:
        return None, None, None
    raw = q.strip().upper()
    m = re.match(r"Q([1-4])\s*(?:[-/]?\s*FY)?\s*(20\d\d|\d\d)?", raw)
    if m:
        q_num = int(m.group(1))
        yr_str = m.group(2)
        if not yr_str:
            yr = datetime.now().year
        else:
            yr = int(yr_str) if len(yr_str) == 4 else 2000 + int(yr_str)

        canonical_q = f"Q{q_num} FY{str(yr)[-2:]}"
        if q_num == 1:
            return canonical_q, f"{yr - 1}-04-01", f"{yr - 1}-06-30"
        elif q_num == 2:
            return canonical_q, f"{yr - 1}-07-01", f"{yr - 1}-09-30"
        elif q_num == 3:
            return canonical_q, f"{yr - 1}-10-01", f"{yr - 1}-12-31"
        elif q_num == 4:
            return canonical_q, f"{yr}-01-01", f"{yr}-03-31"

    return None, None, None


def _normalize_query_dates(
    from_date: str | None = None,
    to_date: str | None = None,
    quarter: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Normalize query parameters into (start_date_iso, end_date_iso, canonical_quarter)."""
    canonical_q = None
    q_start, q_end = None, None

    if quarter:
        canonical_q, q_start, q_end = _parse_fiscal_quarter(quarter)

    if from_date and not canonical_q:
        test_q, t_start, t_end = _parse_fiscal_quarter(from_date)
        if test_q:
            canonical_q, q_start, q_end = test_q, t_start, t_end
            from_date = None

    start_date = _parse_single_query_date(from_date, is_end_date=False) if from_date else q_start
    end_date = _parse_single_query_date(to_date, is_end_date=True) if to_date else q_end

    return start_date, end_date, canonical_q


def _map_buyer_macro_category(entity_type: str) -> str:
    """Categorize an institutional entity into FII, DII, Super Investor, AIF, or Other."""
    et = (entity_type or "").upper()
    if "SUPER INVESTOR" in et or "INDIVIDUAL" in et:
        return "Super Investor"
    if "FII" in et or "FOREIGN" in et or "SOVEREIGN" in et:
        return "FII"
    if "MUTUAL FUND" in et or "DII" in et or "INSURANCE" in et or "BANK" in et or "FINANCIAL INSTITUTION" in et:
        return "DII"
    if "AIF" in et or "ALTERNATE INVESTMENT" in et:
        return "AIF"
    return "Institutional"


def get_stock_buyers_in_period(
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
    quarter: str | None = None,
    entity_type: str | None = None,
    min_value_cr: float = 0.0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve all institutions, funds, and super investors who bought or accumulated a stock in a given period.

    Synthesizes periodic regulatory shareholding filings (NEW BUY, ACCUMULATED) with real-time
    exchange bulk/block deals (BUY).
    """
    settings = settings or Settings()
    from earnings_engine.data.institutional_accumulation.db import (
        _ensure_institutional_data_for_ticker,
        init_institutional_db,
    )
    from earnings_engine.data.institutional_accumulation.returns import _fetch_price_history
    from earnings_engine.data.nse_shareholding import classify_institutional_entity

    init_institutional_db(settings)

    conn = get_db_connection(settings)
    try:
        sym, comp_name = _resolve_ticker_symbol(ticker, conn=conn, settings=settings)
        if not sym:
            return {
                "success": False,
                "detail": f"Could not resolve ticker symbol or company name for '{ticker}'.",
                "buyers": [],
            }

        _ensure_institutional_data_for_ticker(sym, conn)

        ltp_rows = _fetch_price_history(conn, sym, limit=1)
        ltp_row = ltp_rows[0] if ltp_rows else None

        latest_market_price = round(float(ltp_row[1]), 2) if (ltp_row and ltp_row[1] is not None) else None
        latest_price_date = str(ltp_row[0]) if (ltp_row and ltp_row[0]) else None

        start_date, end_date, canonical_q = _normalize_query_dates(
            from_date=from_date,
            to_date=to_date,
            quarter=quarter,
        )

        desc_parts = []
        if start_date:
            desc_parts.append(f"From {start_date}")
        if end_date:
            desc_parts.append(f"To {end_date}")
        if canonical_q:
            desc_parts.append(f"Quarter {canonical_q}")
        period_description = " - ".join(desc_parts) if desc_parts else "All Recorded Disclosures & Deals"

        h_rows = conn.execute(
            """
            SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                   holding_value_cr, prev_stake_pct, action, change_shares, change_pct,
                   avg_price, recent_buy_price, recent_txn_date, reported_date
            FROM institutional_holdings
            WHERE ticker = ?
              AND (action IN ('NEW BUY', 'ACCUMULATED') OR change_pct > 0 OR change_shares > 0)
            ORDER BY reported_date DESC, stake_pct DESC
            """,
            (sym,),
        ).fetchall()

        filing_buyers: list[dict[str, Any]] = []
        for r in h_rows:
            (
                _hid, _hticker, fund_name, raw_fund_type, h_quarter, shares_held,
                stake_pct, holding_val_cr, prev_stake, action, change_shares,
                change_pct, avg_price, recent_buy_price, recent_txn_date, reported_date
            ) = r

            stake_pct = round(float(stake_pct or 0.0), 2)
            holding_val_cr = round(float(holding_val_cr or 0.0), 2)
            change_pct = round(float(change_pct or 0.0), 2)
            change_shares = int(change_shares or 0)
            buy_price = round(float(recent_buy_price or avg_price or 0.0), 2)

            txn_date = recent_txn_date or reported_date

            if canonical_q and h_quarter != canonical_q:
                continue

            if start_date:
                if txn_date and txn_date < start_date:
                    continue
                elif not txn_date and canonical_q:
                    _cq, q_s, q_e = _parse_fiscal_quarter(h_quarter)
                    if q_e and q_e < start_date:
                        continue
            if end_date:
                if txn_date and txn_date > end_date:
                    continue
                elif not txn_date and canonical_q:
                    _cq, q_s, q_e = _parse_fiscal_quarter(h_quarter)
                    if q_s and q_s > end_date:
                        continue

            classified_type = classify_institutional_entity(fund_name)
            if "MUTUAL FUND" in (raw_fund_type or "").upper() and "MUTUAL FUND" not in classified_type.upper():
                entity_class = "Mutual Fund (DII)"
            elif classified_type in ("Institutional Investor (DII/FII)", "Domestic Institutional (DII)") and raw_fund_type:
                entity_class = raw_fund_type
            else:
                entity_class = classified_type

            category = _map_buyer_macro_category(entity_class)

            if entity_type:
                et_clean = entity_type.strip().upper()
                if et_clean not in entity_class.upper() and et_clean not in category.upper():
                    continue

            if change_shares > 0 and buy_price > 0:
                capital_cr = round((change_shares * buy_price) / 1e7, 2)
            elif action == "NEW BUY" and (change_pct >= stake_pct or change_pct == 0.0):
                capital_cr = holding_val_cr
            elif stake_pct > 0 and change_pct > 0:
                capital_cr = round((change_pct / stake_pct) * holding_val_cr, 2)
            else:
                capital_cr = round(holding_val_cr * 0.2, 2)

            if min_value_cr > 0 and capital_cr < min_value_cr and holding_val_cr < min_value_cr:
                continue

            resolved_price = buy_price if buy_price > 0 else None
            if not resolved_price:
                if change_shares > 0 and capital_cr > 0:
                    resolved_price = round((capital_cr * 1e7) / change_shares, 2)
                elif shares_held and shares_held > 0 and holding_val_cr > 0:
                    resolved_price = round((holding_val_cr * 1e7) / shares_held, 2)

            unrealized_gain_pct = None
            if latest_market_price and resolved_price and latest_market_price > 0 and resolved_price > 0:
                unrealized_gain_pct = round(((latest_market_price - resolved_price) / resolved_price) * 100.0, 2)

            filing_buyers.append({
                "investor_name": fund_name,
                "buyer_name": fund_name,
                "entity_type": entity_class,
                "entity_class": entity_class,
                "category": category,
                "action": action,
                "source": "Filing",
                "source_label": "Quarterly / AMFI Filing",
                "date": txn_date or reported_date,
                "quarter": h_quarter,
                "capital_deployed_cr": capital_cr,
                "holding_value_cr": holding_val_cr,
                "stake_pct": stake_pct,
                "change_pct": change_pct,
                "shares_added": change_shares if change_shares > 0 else None,
                "price": resolved_price,
                "avg_price": resolved_price,
                "latest_market_price": latest_market_price,
                "latest_price_date": latest_price_date,
                "unrealized_gain_pct": unrealized_gain_pct,
                "exchange": "AMFI / Disclosures",
            })

        b_rows = conn.execute(
            """
            SELECT DISTINCT deal_date, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange
            FROM institutional_block_deals
            WHERE ticker = ? AND deal_type = 'BUY'
            ORDER BY deal_date DESC, value_cr DESC
            """,
            (sym,),
        ).fetchall()

        block_deal_buyers: list[dict[str, Any]] = []
        for r in b_rows:
            deal_date, client_name, deal_type, qty, price, val_cr, pct_eq, exchange = r

            val_cr = round(float(val_cr or 0.0), 2)
            price = round(float(price or 0.0), 2)
            qty = int(qty or 0)
            pct_eq = round(float(pct_eq or 0.0), 2)

            if start_date and deal_date < start_date:
                continue
            if end_date and deal_date > end_date:
                continue
            if canonical_q:
                _cq, q_s, q_e = _parse_fiscal_quarter(canonical_q)
                if q_s and deal_date < q_s:
                    continue
                if q_e and deal_date > q_e:
                    continue

            entity_class = classify_institutional_entity(client_name)
            category = _map_buyer_macro_category(entity_class)

            if entity_type:
                et_clean = entity_type.strip().upper()
                if et_clean not in entity_class.upper() and et_clean not in category.upper():
                    continue

            if min_value_cr > 0 and val_cr < min_value_cr:
                continue

            resolved_block_price = price if price > 0 else None
            unrealized_gain_pct = None
            if latest_market_price and resolved_block_price and latest_market_price > 0 and resolved_block_price > 0:
                unrealized_gain_pct = round(((latest_market_price - resolved_block_price) / resolved_block_price) * 100.0, 2)

            block_deal_buyers.append({
                "investor_name": client_name,
                "buyer_name": client_name,
                "entity_type": entity_class,
                "entity_class": entity_class,
                "category": category,
                "action": "BLOCK BUY",
                "source": "Block Deal",
                "source_label": "Exchange Block / Bulk Deal",
                "date": deal_date,
                "quarter": None,
                "capital_deployed_cr": val_cr,
                "holding_value_cr": val_cr,
                "stake_pct": pct_eq,
                "change_pct": pct_eq,
                "shares_added": qty,
                "price": resolved_block_price,
                "avg_price": resolved_block_price,
                "latest_market_price": latest_market_price,
                "latest_price_date": latest_price_date,
                "unrealized_gain_pct": unrealized_gain_pct,
                "exchange": exchange or "NSE",
            })

        all_buyers = filing_buyers + block_deal_buyers
        all_buyers.sort(key=lambda x: (x.get("date") or "", x.get("capital_deployed_cr") or 0.0), reverse=True)

        total_capital = sum(b["capital_deployed_cr"] for b in all_buyers)
        fii_buyers = [b for b in all_buyers if b["category"] == "FII"]
        dii_buyers = [b for b in all_buyers if b["category"] == "DII"]
        super_inv_buyers = [b for b in all_buyers if b["category"] == "Super Investor"]
        other_buyers = [b for b in all_buyers if b["category"] not in ("FII", "DII", "Super Investor")]

        priced_buyers = [b for b in all_buyers if b.get("unrealized_gain_pct") is not None and (b.get("capital_deployed_cr") or 0.0) > 0]
        priced_cap = sum(b["capital_deployed_cr"] for b in priced_buyers)
        avg_unrealized_gain_pct = (
            round(sum(b["unrealized_gain_pct"] * b["capital_deployed_cr"] for b in priced_buyers) / priced_cap, 2)
            if priced_cap > 0 else None
        )
        profitable_buyers = sum(1 for b in all_buyers if (b.get("unrealized_gain_pct") or 0.0) > 0)
        unprofitable_buyers = sum(1 for b in all_buyers if (b.get("unrealized_gain_pct") or 0.0) < 0)

        return {
            "success": True,
            "ticker": sym,
            "company_name": comp_name,
            "total_buyers_count": len(all_buyers),
            "total_capital_deployed_cr": round(total_capital, 2),
            "latest_market_price": latest_market_price,
            "latest_price_date": latest_price_date,
            "avg_unrealized_gain_pct": avg_unrealized_gain_pct,
            "profitable_buyers_count": profitable_buyers,
            "unprofitable_buyers_count": unprofitable_buyers,
            "time_period": {
                "from_date": start_date,
                "to_date": end_date,
                "quarter": canonical_q,
                "description": period_description,
            },
            "summary": {
                "total_buyers_count": len(all_buyers),
                "total_capital_deployed_cr": round(total_capital, 2),
                "latest_market_price": latest_market_price,
                "latest_price_date": latest_price_date,
                "avg_unrealized_gain_pct": avg_unrealized_gain_pct,
                "profitable_buyers_count": profitable_buyers,
                "unprofitable_buyers_count": unprofitable_buyers,
                "fii_capital_deployed_cr": round(sum(b["capital_deployed_cr"] for b in fii_buyers), 2),
                "fii_buyers_count": len(fii_buyers),
                "dii_capital_deployed_cr": round(sum(b["capital_deployed_cr"] for b in dii_buyers), 2),
                "dii_buyers_count": len(dii_buyers),
                "super_investor_capital_deployed_cr": round(sum(b["capital_deployed_cr"] for b in super_inv_buyers), 2),
                "super_investor_buyers_count": len(super_inv_buyers),
                "other_capital_deployed_cr": round(sum(b["capital_deployed_cr"] for b in other_buyers), 2),
                "other_buyers_count": len(other_buyers),
                "filings_count": len(filing_buyers),
                "block_deals_count": len(block_deal_buyers),
            },
            "buyers": all_buyers,
            "filing_buyers": filing_buyers,
            "block_deal_buyers": block_deal_buyers,
        }
    except Exception as e:
        logger.exception("Error in get_stock_buyers_in_period for %s: %s", ticker, e)
        return {
            "success": False,
            "detail": f"Error inspecting buyers for {ticker}: {str(e)}",
            "buyers": [],
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
