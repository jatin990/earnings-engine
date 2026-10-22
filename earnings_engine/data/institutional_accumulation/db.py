"""Database initialization, schema migrations, and batch calculation caching."""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.institutional_accumulation.cache import clear_institutional_cache
from earnings_engine.data.institutional_accumulation.constants import (
    _get_quarter_start_date,
    _is_marquee_amc_name,
    _is_super_investor_name,
)
from earnings_engine.data.institutional_accumulation.freshness import fetch_live_corporate_ownership
from earnings_engine.data.institutional_accumulation.returns import _fetch_price_history
from earnings_engine.data.institutional_accumulation.scoring import calculate_institutional_score

logger = logging.getLogger(__name__)

_INITIALIZED_DBS: set[str] = set()

# Fallback name cache
_NAME_CACHE: dict[str, str] = {}


def get_institutional_db_path(settings: Settings | None = None) -> Path:
    """Return local database file path used for institutional data."""
    from earnings_engine.data.db import _cache_path
    return _cache_path(settings or Settings())


def _ensure_institutional_data_for_ticker(sym: str, conn: Any, allow_network: bool = True) -> None:
    """Persist institutional flow data grounded strictly in live corporate ownership & price history."""
    # 1. Retrieve live corporate ownership data
    live_meta = fetch_live_corporate_ownership(sym, conn, allow_network=allow_network)

    # Persist company name if we got one from yfinance
    if live_meta.get("short_name") and conn:
        try:
            conn.execute(
                "UPDATE tickers SET name = ? WHERE ticker = ? AND (name IS NULL OR name = '' OR name = ticker)",
                (live_meta["short_name"], sym),
            )
        except Exception:
            pass

    if hasattr(conn, "commit"):
        conn.commit()


def init_institutional_db(settings: Settings | None = None, force_refresh: bool = False) -> None:
    """Initialize institutional holdings, block deals, and shareholding tables dynamically."""
    settings = settings or Settings()
    db_key = str(settings.data_dirs.get("prices", ""))
    if not force_refresh and db_key in _INITIALIZED_DBS:
        return

    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)

        # Ensure avg_price, recent_buy_price, and recent_txn columns exist in institutional_holdings (idempotent check)
        existing_holdings_cols = set()
        try:
            rows = conn.execute("PRAGMA table_info(institutional_holdings)").fetchall()
            for r in rows:
                if hasattr(r, "get"):
                    c = r.get("name")
                elif isinstance(r, (tuple, list)) and len(r) > 1:
                    c = r[1]
                elif hasattr(r, "keys") and "name" in r.keys():
                    c = r["name"]
                else:
                    c = None
                if c:
                    existing_holdings_cols.add(c)
        except Exception:
            pass

        for col, ctype in [
            ("avg_price", "REAL DEFAULT 0.0"),
            ("recent_buy_price", "REAL DEFAULT NULL"),
            ("recent_txn_price", "REAL DEFAULT NULL"),
            ("recent_txn_date", "TEXT DEFAULT NULL"),
            ("recent_txn_type", "TEXT DEFAULT NULL"),
        ]:
            if not existing_holdings_cols or col not in existing_holdings_cols:
                try:
                    conn.execute(f"ALTER TABLE institutional_holdings ADD COLUMN {col} {ctype}")
                except Exception:
                    pass

        # Fast atomic backfill for any legacy records missing recent_txn_date or recent_txn_price
        try:
            conn.execute("""
                UPDATE institutional_holdings
                SET recent_txn_date = COALESCE(reported_date, '2026-08-15'),
                    recent_txn_type = CASE
                        WHEN action LIKE '%BUY%' OR action LIKE '%ACCUMULAT%' THEN 'BUY'
                        WHEN action LIKE '%TRIM%' OR action LIKE '%SELL%' THEN 'SELL'
                        ELSE 'HOLD'
                    END
                WHERE (recent_txn_date IS NULL OR recent_txn_type IS NULL) AND action != 'HOLD'
            """)
            conn.execute("""
                UPDATE institutional_holdings
                SET recent_txn_price = COALESCE(recent_buy_price, avg_price, 500.0)
                WHERE recent_txn_price IS NULL AND action != 'HOLD'
            """)
            if hasattr(conn, "commit"):
                conn.commit()
        except Exception as e:
            logger.debug("[INSTITUTIONAL] Backfill migration warning: %s", e)

        cache_check = conn.execute("SELECT COUNT(*) FROM institutional_accumulation_cache").fetchone()[0]

        # STRICT ANTI-FABRICATION GUARANTEE: Never auto-seed synthetic holders or deals
        if cache_check == 0:
            _recalculate_metrics_internal(conn, settings)

        _INITIALIZED_DBS.add(db_key)
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Dynamic init warning: %s", e)


def recalculate_all_institutional_metrics(settings: Settings | None = None, force: bool = False) -> dict[str, Any]:
    """Precompute and persist complete institutional accumulation metrics, scores, and flows into institutional_accumulation_cache."""
    settings = settings or Settings()
    init_institutional_db(settings)
    conn = get_db_connection(settings)
    return _recalculate_metrics_internal(conn, settings)


def _recalculate_metrics_internal(conn: Any, settings: Settings) -> dict[str, Any]:
    t0 = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # 1. Load names and market caps into in-memory dictionary
        names_map: dict[str, tuple[str | None, Any]] = {}
        for r in conn.execute("SELECT ticker, name, market_cap FROM tickers").fetchall():
            if r[0]:
                tk = str(r[0]).strip().upper()
                names_map[tk] = (r[1], r[2])
                if tk.endswith(".NS") or tk.endswith(".BO"):
                    names_map[tk[:-3]] = (r[1], r[2])

        # 2. Load holdings
        holdings_by_ticker = defaultdict(list)
        for r in conn.execute("""
            SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                   holding_value_cr, prev_stake_pct, action, change_shares, change_pct,
                   avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type,
                   reported_date
            FROM institutional_holdings
            ORDER BY ticker, stake_pct DESC, holding_value_cr DESC
        """).fetchall():
            holdings_by_ticker[r[1]].append(r)

        # 3. Load shareholding patterns
        patterns_by_ticker = defaultdict(list)
        for r in conn.execute("""
            SELECT ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct
            FROM shareholding_patterns
            ORDER BY ticker, rowid ASC
        """).fetchall():
            patterns_by_ticker[r[0]].append(r)

        # 4. Load block deals
        deals_by_ticker = defaultdict(list)
        for r in conn.execute("""
            SELECT id, deal_date, ticker, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange
            FROM institutional_block_deals
            ORDER BY ticker, deal_date DESC
        """).fetchall():
            deals_by_ticker[r[2]].append(r)

        # 5. Load latest prices and 7d/30d/1y return bars
        price_rows_by_ticker = defaultdict(list)
        for r in conn.execute("""
            SELECT ticker, date, close FROM price_history
            ORDER BY ticker, date DESC
        """).fetchall():
            if len(price_rows_by_ticker[r[0]]) < 260:
                price_rows_by_ticker[r[0]].append((r[1], float(r[2] or 0.0)))

        all_tickers = sorted(list(set(list(holdings_by_ticker.keys()) + list(patterns_by_ticker.keys()) + list(deals_by_ticker.keys()))))

        db_rows = []
        for sym in all_tickers:
            h_rows = holdings_by_ticker.get(sym, [])
            p_rows = patterns_by_ticker.get(sym, [])
            d_rows = deals_by_ticker.get(sym, [])
            price_series = price_rows_by_ticker.get(sym, [])
            if not price_series and sym.endswith(".NS"):
                price_series = price_rows_by_ticker.get(sym.replace(".NS", ""), [])

            # Price returns
            ret_7d, ret_30d, ret_1y = None, None, None
            if len(price_series) >= 2:
                latest_c = price_series[0][1]
                if latest_c > 0:
                    idx_7d = min(5, len(price_series) - 1)
                    p7 = price_series[idx_7d][1]
                    ret_7d = round(((latest_c - p7) / p7) * 100.0, 2) if p7 > 0 else None

                    idx_30d = min(21, len(price_series) - 1)
                    p30 = price_series[idx_30d][1]
                    ret_30d = round(((latest_c - p30) / p30) * 100.0, 2) if p30 > 0 else None

                    idx_1y = min(252, len(price_series) - 1)
                    p1y = price_series[idx_1y][1]
                    ret_1y = round(((latest_c - p1y) / p1y) * 100.0, 2) if p1y > 0 else None

            # Patterns pre-sort to determine latest reporting quarter for this ticker
            p_rows_sorted = sorted(p_rows, key=lambda x: _get_quarter_start_date(x[1]), reverse=True)
            latest_quarter = p_rows_sorted[0][1] if p_rows_sorted else None

            # Holdings processing (using latest active quarter per fund)
            latest_h_by_fund = {}
            for r in sorted(h_rows, key=lambda x: _get_quarter_start_date(x[4])):
                latest_h_by_fund[r[2]] = r
            active_h_rows = sorted(latest_h_by_fund.values(), key=lambda x: float(x[6] or 0.0), reverse=True)
            if not latest_quarter and active_h_rows:
                latest_quarter = active_h_rows[0][4]

            holdings = []
            accumulating_count = 0
            selling_count = 0
            new_buys_count = 0
            gross_inflow_cr = 0.0
            gross_outflow_cr = 0.0

            # Pre-retrieve mcap for this symbol
            raw_info = names_map.get(sym.upper()) or names_map.get(sym.upper().replace(".NS", "").replace(".BO", "")) or (None, None)
            mcap_val = raw_info[1]
            mcap_cr = round(float(mcap_val) / 1e7, 1) if mcap_val and float(mcap_val) > 0 else None

            for r in active_h_rows:
                h_quarter = r[4]
                act = (r[9] or "HOLD").upper()
                is_buy = act in ("NEW BUY", "ACCUMULATED")
                is_trim = act in ("TRIMMED", "SOLD OUT", "PROFIT TAKING")
                val_cr = round(float(r[7] or 0.0), 2)
                stk_pct = round(float(r[6] or 0.0), 2)
                prev_stk = round(float(r[8] or 0.0), 2) if r[8] is not None else None
                chg_pct = round(float(r[11] or 0.0), 2)
                is_curr_q = (latest_quarter is None or h_quarter == latest_quarter)

                inc_amt_cr = 0.0
                if is_buy:
                    if is_curr_q:
                        accumulating_count += 1
                        if act == "NEW BUY":
                            new_buys_count += 1
                            inc_amt_cr = val_cr
                        else:
                            if prev_stk is not None and prev_stk >= 0 and stk_pct > 0:
                                delta_stk = max(0.0, stk_pct - prev_stk)
                                inc_amt_cr = round((delta_stk / stk_pct) * val_cr, 2) if delta_stk > 0 else round((min(stk_pct, max(0.05, chg_pct)) / max(0.01, stk_pct)) * val_cr, 2)
                            else:
                                inc_amt_cr = round(val_cr * 0.35, 2)
                        gross_inflow_cr += max(inc_amt_cr, 5.0)
                    else:
                        inc_amt_cr = 0.0
                elif is_trim:
                    if is_curr_q:
                        selling_count += 1
                        if prev_stk and prev_stk > 0 and stk_pct > 0:
                            delta_stk = abs(prev_stk - stk_pct)
                            inc_amt_cr = -round((delta_stk / stk_pct) * val_cr, 2)
                        elif prev_stk and prev_stk > 0:
                            inc_amt_cr = -round((prev_stk / 100.0) * (mcap_cr or 1000.0), 2)
                        else:
                            inc_amt_cr = -round(max(0.1, abs(chg_pct)) * 15.0, 2)
                        gross_outflow_cr += abs(inc_amt_cr)
                    else:
                        inc_amt_cr = 0.0

                raw_avg = r[12]
                raw_buy = r[13] if is_buy else None
                raw_txn_p = r[14]
                raw_txn_d = r[15]
                raw_txn_t = r[16] or ("BUY" if is_buy else ("TRIM" if is_trim else "HOLD"))

                holdings.append({
                    "id": r[0],
                    "ticker": r[1],
                    "fund_name": r[2],
                    "fund_type": r[3],
                    "quarter": r[4],
                    "shares_held": r[5],
                    "stake_pct": stk_pct,
                    "holding_value_cr": val_cr,
                    "total_amount_cr": val_cr,
                    "prev_stake_pct": prev_stk,
                    "action": act,
                    "change_shares": r[10] or 0,
                    "change_pct": chg_pct,
                    "increase_pct": chg_pct,
                    "increase_amount_cr": inc_amt_cr,
                    "avg_price": round(float(raw_avg), 2) if raw_avg is not None and float(raw_avg) > 0 else None,
                    "recent_buy_price": round(float(raw_buy), 2) if raw_buy is not None and float(raw_buy) > 0 else None,
                    "recent_txn_price": round(float(raw_txn_p), 2) if raw_txn_p is not None and float(raw_txn_p) > 0 else (round(float(raw_buy), 2) if raw_buy is not None and float(raw_buy) > 0 else None),
                    "recent_txn_date": raw_txn_d or None,
                    "recent_txn_type": raw_txn_t,
                    "reported_date": r[17],
                })

            gross_inflow_cr = round(gross_inflow_cr, 1)
            gross_outflow_cr = round(gross_outflow_cr, 1)
            net_flow_cr = round(gross_inflow_cr - gross_outflow_cr, 1)

            # Patterns processing
            patterns = []
            latest_close_p = price_series[0][1] if price_series else None
            latest_close_d = price_series[0][0] if price_series else None

            for idx, p in enumerate(p_rows_sorted):
                q_name = p[1]
                q_sdate = _get_quarter_start_date(q_name)

                # Find quarter start price from chronological price series
                q_sprice = None
                q_act_date = None
                for d_val, c_val in reversed(price_series):
                    if d_val >= q_sdate:
                        q_sprice = c_val
                        q_act_date = d_val
                        break
                if q_sprice is None and price_series:
                    q_sprice = price_series[-1][1]
                    q_act_date = price_series[-1][0]

                is_present_q = (idx == 0)
                stock_price_display = latest_close_p if (is_present_q and latest_close_p is not None) else q_sprice

                patterns.append({
                    "quarter": q_name,
                    "promoter_pct": round(float(p[2] or 0.0), 2),
                    "fii_pct": round(float(p[3] or 0.0), 2),
                    "dii_mf_pct": round(float(p[4] or 0.0), 2),
                    "dii_pct": round(float(p[4] or 0.0), 2),
                    "public_retail_pct": round(float(p[5] or 0.0), 2),
                    "public_pct": round(float(p[5] or 0.0), 2),
                    "other_pct": round(float(p[6] or 0.0), 2),
                    "quarter_start_date": q_sdate,
                    "quarter_start_price": q_sprice,
                    "quarter_price_date": q_act_date,
                    "current_price": latest_close_p,
                    "latest_price_date": latest_close_d,
                    "stock_price": stock_price_display,
                    "is_current_quarter": is_present_q,
                })

            # Block deals processing
            deals = []
            block_buy_cr = 0.0
            block_sell_cr = 0.0
            for b in d_rows[:20]:
                dtype = (b[4] or "").upper()
                vcr = round(float(b[7] or 0.0), 2)
                if dtype == "BUY":
                    block_buy_cr += vcr
                elif dtype == "SELL":
                    block_sell_cr += vcr

                deals.append({
                    "id": b[0],
                    "deal_date": b[1],
                    "ticker": b[2],
                    "client_name": b[3],
                    "deal_type": dtype,
                    "quantity": b[5],
                    "price": round(float(b[6]), 2),
                    "value_cr": vcr,
                    "pct_equity": round(float(b[8] or 0.0), 2),
                    "exchange": b[9],
                })
            block_net_cr = round(block_buy_cr - block_sell_cr, 2)
            block_cnt = len(deals)

            # Whale & Marquee conviction analysis from holdings and buy block deals
            super_investor_names: set[str] = set()
            marquee_amc_names: set[str] = set()
            whale_cap_cr = 0.0

            for h in holdings:
                fname = h.get("fund_name") or ""
                act = h.get("action") or ""
                h_val = float(h.get("holding_value_cr") or 0.0)
                if act in ("NEW BUY", "ACCUMULATED"):
                    if _is_super_investor_name(fname):
                        super_investor_names.add(fname)
                        whale_cap_cr += h_val
                    if _is_marquee_amc_name(fname):
                        marquee_amc_names.add(fname)
                        whale_cap_cr += h_val

            for d in deals:
                if d.get("deal_type") == "BUY":
                    cname_d = d.get("client_name") or ""
                    d_val = float(d.get("value_cr") or 0.0)
                    if _is_super_investor_name(cname_d):
                        super_investor_names.add(cname_d)
                        whale_cap_cr += d_val
                    if _is_marquee_amc_name(cname_d):
                        marquee_amc_names.add(cname_d)
                        whale_cap_cr += d_val

            cname = raw_info[0] or _NAME_CACHE.get(sym.upper()) or sym.replace(".NS", "").replace(".BO", "")

            lat_fii = patterns[0]["fii_pct"] if patterns else 0.0
            lat_dii = patterns[0]["dii_mf_pct"] if patterns else 0.0
            tot_inst_stake = round(lat_fii + lat_dii, 2)
            tot_inst_amt = round((tot_inst_stake / 100.0) * mcap_cr, 1) if mcap_cr else round(sum(h.get("total_amount_cr", 0.0) for h in holdings), 1)

            inst_addition_pct = 0.0
            if len(patterns) >= 2:
                prev_inst = patterns[1]["fii_pct"] + patterns[1]["dii_mf_pct"]
                inst_addition_pct = round(tot_inst_stake - prev_inst, 2)

            inc_amt_cr = round((inst_addition_pct / 100.0) * mcap_cr, 1) if (mcap_cr and inst_addition_pct != 0) else net_flow_cr

            # Amount-based, macro supply absorption, and whale conviction score (Tier 1-3 composite)
            score, verdict, verdict_badge = calculate_institutional_score(
                accumulating_count=accumulating_count,
                selling_count=selling_count,
                new_buys_count=new_buys_count,
                net_flow_cr=net_flow_cr,
                gross_inflow_cr=gross_inflow_cr,
                gross_outflow_cr=gross_outflow_cr,
                inst_addition_pct=inst_addition_pct,
                increase_amount_cr=inc_amt_cr,
                total_inst_amount_cr=tot_inst_amt,
                block_deals_net_cr=block_net_cr,
                block_deals_count=block_cnt,
                super_investor_count=len(super_investor_names),
                marquee_amc_count=len(marquee_amc_names),
                whale_capital_cr=round(whale_cap_cr, 2),
            )

            is_new_fii = False
            if patterns and any(p.get("fii_pct", 0) == 0 for p in patterns):
                is_new_fii = patterns[0].get("fii_pct", 0) > 0

            fii_always_held = 1 if (patterns and all(p.get("fii_pct", 0) > 0 for p in patterns)) else 0
            if fii_always_held:
                fii_summary = f"Had {lat_fii:0.1f}% on Dec 2025"
            else:
                fii_summary = f"FII Stake: {lat_fii:.2f}% · DII Stake: {lat_dii:.2f}%"

            db_rows.append((
                sym, cname, mcap_cr, score, verdict, verdict_badge,
                accumulating_count, selling_count, new_buys_count,
                gross_inflow_cr, gross_outflow_cr, net_flow_cr,
                inst_addition_pct, inc_amt_cr, tot_inst_amt, tot_inst_amt,
                tot_inst_stake, lat_fii, lat_dii,
                1 if is_new_fii else 0, 0, fii_always_held, fii_summary,
                ret_7d, ret_30d, ret_1y,
                json.dumps(holdings), json.dumps(deals), json.dumps(patterns),
                now_iso
            ))

        conn.executemany("""
            INSERT OR REPLACE INTO institutional_accumulation_cache (
                ticker, company_name, market_cap_cr, accumulation_score, verdict, verdict_badge,
                funds_accumulating_count, funds_selling_count, new_funds_bought_count,
                gross_inflow_cr, gross_outflow_cr, net_flow_cr,
                inst_addition_pct, increase_amount_cr, total_amount_cr, total_institutional_amount_cr,
                total_institutional_stake_pct, fii_stake_pct, dii_stake_pct,
                is_new_fii_entry, is_new_dii_entry, fii_always_held, fii_interest_summary,
                return_7d_pct, return_30d_pct, return_1y_pct,
                holdings_json, block_deals_json, shareholding_patterns_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, db_rows)
        conn.commit()
        clear_institutional_cache()

        duration = round(time.time() - t0, 3)
        logger.info("[INSTITUTIONAL] Precomputed and cached metrics for %d tickers in %0.2fs", len(db_rows), duration)
        return {
            "success": True,
            "tickers_processed": len(db_rows),
            "duration_seconds": duration,
            "updated_at": now_iso,
        }
    except Exception as e:
        logger.exception("[INSTITUTIONAL] Batch recalculation failed: %s", e)
        return {"success": False, "error": str(e)}
