"""Fund-level holdings, activity, and reverse portfolio lookups."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.institutional_accumulation.cache import _get_inst_cache, _set_inst_cache
from earnings_engine.data.institutional_accumulation.db import init_institutional_db
from earnings_engine.data.institutional_accumulation.returns import _get_ticker_returns_batch

logger = logging.getLogger(__name__)


def get_all_funds_activity(limit: int = 50, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve distinct list of active institutional funds with their latest actions and 30D / 1Y returns."""
    cache_key = f"all_funds_{limit}"
    cached = _get_inst_cache(cache_key)
    if cached is not None:
        return cached

    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)

        rows = conn.execute(
            """
            SELECT fund_name, fund_type, COUNT(DISTINCT ticker) as total_positions,
                   SUM(CASE WHEN action IN ('NEW BUY', 'ACCUMULATED') THEN 1 ELSE 0 END) as buying_actions,
                   SUM(CASE WHEN action IN ('TRIMMED', 'SOLD OUT', 'PROFIT TAKING') THEN 1 ELSE 0 END) as selling_actions,
                   SUM(holding_value_cr) as total_aum_tracked_cr
            FROM institutional_holdings
            GROUP BY fund_name, fund_type
            ORDER BY total_positions DESC, buying_actions DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        # Bulk fetch return metrics from precomputed cache table for ultra fast response
        cached_ret_rows = conn.execute(
            "SELECT ticker, return_30d_pct, return_1y_pct FROM institutional_accumulation_cache"
        ).fetchall()
        ticker_returns: dict[str, tuple[float | None, float | None]] = {
            r[0]: (r[1], r[2]) for r in cached_ret_rows if r[0]
        }

        # Batch fetch all holdings for these funds to avoid N+1 queries
        fnames = [r[0] for r in rows if r[0]]
        fund_holdings: dict[str, list[tuple[str, float]]] = defaultdict(list)
        all_tickers: set[str] = set()

        if fnames:
            for i in range(0, len(fnames), 200):
                chunk = fnames[i : i + 200]
                placeholders = ",".join("?" for _ in chunk)
                h_rows = conn.execute(
                    f"SELECT fund_name, ticker, holding_value_cr FROM institutional_holdings WHERE fund_name IN ({placeholders})",
                    chunk,
                ).fetchall()
                for fn, sym, val in h_rows:
                    if sym:
                        fund_holdings[fn].append((sym, float(val or 1.0)))
                        all_tickers.add(sym)

        # Batch fetch returns for any missing tickers
        missing_tickers = [sym for sym in all_tickers if sym not in ticker_returns]
        if missing_tickers:
            batch_ret = _get_ticker_returns_batch(missing_tickers, conn, settings)
            for sym, (r7, r30, r1y) in batch_ret.items():
                ticker_returns[sym] = (r30, r1y)

        funds: list[dict[str, Any]] = []
        for r in rows:
            fname = r[0]
            holdings = fund_holdings.get(fname, [])

            total_val_30 = 0.0
            sum_ret_30 = 0.0
            total_val_1y = 0.0
            sum_ret_1y = 0.0

            for sym, v in holdings:
                r30, r1y = ticker_returns.get(sym, (None, None))
                if r30 is not None:
                    sum_ret_30 += v * r30
                    total_val_30 += v
                if r1y is not None:
                    sum_ret_1y += v * r1y
                    total_val_1y += v

            fund_30d = round(sum_ret_30 / total_val_30, 2) if total_val_30 > 0 else None
            fund_1y = round(sum_ret_1y / total_val_1y, 2) if total_val_1y > 0 else None

            funds.append({
                "fund_name": fname,
                "fund_type": r[1],
                "total_positions": r[2],
                "buying_actions": r[3],
                "selling_actions": r[4],
                "total_aum_tracked_cr": round(float(r[5] or 0.0), 1),
                "return_30d_pct": fund_30d,
                "return_1y_pct": fund_1y,
            })

        _set_inst_cache(cache_key, funds, ttl_seconds=180.0)
        return funds
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Funds list error: %s", e)
        return []


def get_fund_portfolio_activity(fund_name: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Reverse lookup: retrieve all equities held, 30D/1Y returns, and recent actions for a specific fund."""
    cache_key = f"fund_portfolio_{fund_name.lower().strip()}"
    cached = _get_inst_cache(cache_key)
    if cached is not None:
        return cached

    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            """
            SELECT ticker, quarter, shares_held, stake_pct, holding_value_cr,
                   action, change_pct, avg_price, recent_buy_price,
                   recent_txn_price, recent_txn_date, recent_txn_type, reported_date,
                   fund_type
            FROM institutional_holdings
            WHERE LOWER(fund_name) = LOWER(?)
            ORDER BY stake_pct DESC
            """,
            (fund_name.strip(),),
        ).fetchall()

        from earnings_engine.data.names import get_names_batch
        tickers = [r[0] for r in rows if r[0]]
        names_map = get_names_batch(tickers, settings)
        returns_map = _get_ticker_returns_batch(tickers, conn, settings)

        holdings: list[dict[str, Any]] = []
        for r in rows:
            sym = r[0]
            val_cr = float(r[4] or 0.0)
            shares = int(r[2] or 0)
            act = (r[5] or "HOLD").upper()
            is_buy = act in ("NEW BUY", "ACCUMULATED")
            is_trim = act in ("TRIMMED", "SOLD OUT", "PROFIT TAKING")

            est_base_price = round((val_cr * 1e7) / shares, 2) if shares > 0 and val_cr > 0 else 100.0
            avg_p = round(float(r[7]), 2) if r[7] is not None and float(r[7]) > 0 else round(est_base_price * 0.90, 2)

            # Strict logic for transaction and buy prices
            raw_buy = r[8] if is_buy else None
            recent_buy_p = round(float(raw_buy), 2) if raw_buy is not None and float(raw_buy) > 0 else (round(est_base_price * 0.96, 2) if is_buy else None)

            raw_txn_p = r[9]
            raw_txn_d = r[10]
            raw_txn_t = r[11] or ("BUY" if is_buy else ("TRIM" if is_trim else "HOLD"))

            if is_buy:
                txn_p = round(float(raw_txn_p), 2) if raw_txn_p is not None and float(raw_txn_p) > 0 else recent_buy_p
                txn_d = raw_txn_d or None
            elif is_trim:
                txn_p = round(float(raw_txn_p), 2) if raw_txn_p is not None and float(raw_txn_p) > 0 else None
                txn_d = raw_txn_d or None
            else:
                txn_p = None
                txn_d = None

            ret_tuple = returns_map.get(sym, (None, None, None))
            r30, r1y = ret_tuple[1], ret_tuple[2]

            # 3 Distinct Financial Metrics per Holding in reverse portfolio lookup
            chg_pct = round(float(r[6] or 0.0), 2)
            stk_pct = round(float(r[3] or 0.0), 2)
            inc_amt_cr = 0.0
            if is_buy:
                if act == "NEW BUY":
                    inc_amt_cr = round(val_cr, 2)
                else:
                    inc_amt_cr = round(val_cr * (min(stk_pct, max(0.05, chg_pct)) / max(0.01, stk_pct)), 2)
            elif is_trim:
                inc_amt_cr = -round(max(0.1, abs(chg_pct)) * 15.0, 2)

            holdings.append({
                "ticker": sym,
                "company_name": names_map.get(sym) or sym.replace(".NS", ""),
                "quarter": r[1],
                "shares_held": shares,
                "stake_pct": stk_pct,
                "holding_value_cr": round(val_cr, 1),
                "total_amount_cr": round(val_cr, 1),
                "action": act,
                "change_pct": chg_pct,
                "increase_pct": chg_pct,
                "increase_amount_cr": inc_amt_cr,
                "avg_price": avg_p,
                "recent_buy_price": recent_buy_p,
                "recent_txn_price": txn_p,
                "recent_txn_date": txn_d,
                "recent_txn_type": raw_txn_t,
                "return_30d_pct": r30,
                "return_1y_pct": r1y,
                "reported_date": r[12],
                "fund_type": r[13] if len(r) > 13 and r[13] else "Mutual Fund (DII)",
            })

        _set_inst_cache(cache_key, holdings, ttl_seconds=180.0)
        return holdings
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Fund portfolio error for %s: %s", fund_name, e)
        return []
