"""Detailed institutional activity breakdown and lookups for individual stocks."""

from __future__ import annotations

import json
import logging
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.db_helpers import normalize_nse_ticker
from earnings_engine.data.institutional_accumulation.constants import (
    _get_quarter_start_date,
    _is_marquee_amc_name,
    _is_super_investor_name,
)
from earnings_engine.data.institutional_accumulation.db import (
    _ensure_institutional_data_for_ticker,
    init_institutional_db,
)
from earnings_engine.data.institutional_accumulation.returns import (
    _fetch_price_history,
    _get_ticker_returns,
)
from earnings_engine.data.institutional_accumulation.scoring import calculate_institutional_score
from earnings_engine.data.nse_shareholding import get_stock_fetch_status

logger = logging.getLogger(__name__)

_NAME_CACHE: dict[str, str] = {}


def get_stock_institutional_activity(
    ticker: str,
    settings: Settings | None = None,
    force_refresh: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Retrieve complete institutional accumulation breakdown for a specific equity."""
    force_refresh = force_refresh or force
    settings = settings or Settings()
    init_institutional_db(settings)

    sym = normalize_nse_ticker(ticker)

    try:
        conn = get_db_connection(settings)
        if not force_refresh:
            row = conn.execute(
                """
                SELECT ticker, company_name, market_cap_cr, accumulation_score, verdict, verdict_badge,
                       funds_accumulating_count, funds_selling_count, new_funds_bought_count,
                       gross_inflow_cr, gross_outflow_cr, net_flow_cr,
                       inst_addition_pct, increase_amount_cr, total_amount_cr, total_institutional_amount_cr,
                       total_institutional_stake_pct, fii_stake_pct, dii_stake_pct,
                       is_new_fii_entry, is_new_dii_entry, fii_always_held, fii_interest_summary,
                       return_7d_pct, return_30d_pct, return_1y_pct,
                       holdings_json, block_deals_json, shareholding_patterns_json, updated_at
                FROM institutional_accumulation_cache
                WHERE ticker = ?
                """,
                (sym,),
            ).fetchone()
            if row:
                pats = json.loads(row[28] or "[]")
                # Enrich with price if missing
                if pats and (pats[0].get("current_price") is None or pats[0].get("quarter_start_price") is None):
                    p_series = _fetch_price_history(conn, sym)
                    lat_cp = round(float(p_series[0][1]), 2) if p_series and p_series[0][1] else None
                    lat_cd = str(p_series[0][0]) if p_series and p_series[0][0] else None

                    for idx, pat in enumerate(pats):
                        q_name = pat.get("quarter", "")
                        q_sdate = _get_quarter_start_date(q_name) if q_name else "2026-01-01"

                        q_sprice = None
                        q_act_date = None
                        for d_val, c_val in reversed(p_series):
                            if d_val >= q_sdate:
                                q_sprice = round(float(c_val), 2)
                                q_act_date = str(d_val)
                                break
                        if q_sprice is None and p_series:
                            q_sprice = round(float(p_series[-1][1]), 2)
                            q_act_date = str(p_series[-1][0])

                        is_present_q = (idx == 0)
                        pat["quarter_start_date"] = q_sdate
                        pat["quarter_start_price"] = q_sprice
                        pat["quarter_price_date"] = q_act_date
                        pat["current_price"] = lat_cp
                        pat["latest_price_date"] = lat_cd
                        sp_disp = lat_cp if (is_present_q and lat_cp is not None) else q_sprice
                        pat["stock_price"] = sp_disp
                        pat["is_current_quarter"] = is_present_q

                return {
                    "success": True,
                    "ticker": row[0],
                    "company_name": row[1],
                    "market_cap_cr": row[2],
                    "accumulation_score": row[3],
                    "verdict": row[4],
                    "verdict_badge": row[5],
                    "funds_accumulating_count": row[6],
                    "funds_selling_count": row[7],
                    "new_funds_bought_count": row[8],
                    "gross_inflow_cr": row[9],
                    "gross_outflow_cr": row[10],
                    "net_flow_cr": row[11],
                    "increase_pct": row[12],
                    "inst_addition_pct": row[12],
                    "increase_amount_cr": row[13],
                    "total_amount_cr": row[14],
                    "total_institutional_amount_cr": row[15],
                    "total_institutional_stake_pct": row[16],
                    "total_institutional_stake": row[16],
                    "fii_stake_pct": row[17],
                    "dii_stake_pct": row[18],
                    "is_new_fii_entry": bool(row[19]),
                    "is_new_dii_entry": bool(row[20]),
                    "fii_always_held": bool(row[21]),
                    "fii_interest_summary": row[22],
                    "return_7d_pct": row[23],
                    "return_30d_pct": row[24],
                    "return_1y_pct": row[25],
                    "holdings": json.loads(row[26] or "[]"),
                    "block_deals": json.loads(row[27] or "[]"),
                    "shareholding_patterns": pats,
                    "updated_at": row[29],
                    "last_fetch": get_stock_fetch_status(sym, settings=settings, conn=conn),
                }

        h_rows = conn.execute(
            """
            SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                   holding_value_cr, prev_stake_pct, action, change_shares, change_pct,
                   avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type,
                   reported_date
            FROM institutional_holdings
            WHERE ticker = ?
            ORDER BY stake_pct DESC, holding_value_cr DESC
            """,
            (sym,),
        ).fetchall()

        # If completely empty, seed initial data
        if not h_rows:
            _ensure_institutional_data_for_ticker(sym, conn)
            h_rows = conn.execute(
                """
                SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                       holding_value_cr, prev_stake_pct, action, change_shares, change_pct,
                       avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type,
                       reported_date
                FROM institutional_holdings
                WHERE ticker = ?
                ORDER BY stake_pct DESC, holding_value_cr DESC
                """,
                (sym,),
            ).fetchall()

        # Determine latest reporting quarter from shareholding pattern
        p_latest_row = conn.execute(
            "SELECT quarter FROM shareholding_patterns WHERE ticker = ? ORDER BY rowid ASC",
            (sym,),
        ).fetchall()
        p_latest_sorted = sorted(p_latest_row, key=lambda x: _get_quarter_start_date(x[0]), reverse=True)
        latest_quarter = p_latest_sorted[0][0] if p_latest_sorted else None

        # Deduplicate to latest reported quarter position per fund
        latest_holdings_by_fund: dict[str, Any] = {}
        for r in h_rows:
            fname = r[2]
            qtr = r[4]
            if fname not in latest_holdings_by_fund:
                latest_holdings_by_fund[fname] = r
            else:
                existing_qtr = latest_holdings_by_fund[fname][4]
                if _get_quarter_start_date(qtr) > _get_quarter_start_date(existing_qtr):
                    latest_holdings_by_fund[fname] = r

        holdings_deduped = list(latest_holdings_by_fund.values())

        # If latest quarter is known, filter to only that quarter
        if latest_quarter:
            quarter_holdings = [r for r in holdings_deduped if r[4] == latest_quarter]
            if len(quarter_holdings) >= 1:
                holdings_deduped = quarter_holdings

        holdings_deduped.sort(key=lambda x: (float(x[6] or 0.0), float(x[7] or 0.0)), reverse=True)

        # Pre-retrieve market cap for this symbol
        mcap_cr = None
        try:
            mcap_row = conn.execute("SELECT market_cap FROM tickers WHERE ticker = ?", (sym,)).fetchone()
            if mcap_row and mcap_row[0]:
                mcap_cr = round(float(mcap_row[0]) / 1e7, 1)
        except Exception:
            pass

        if not mcap_cr:
            try:
                from earnings_engine.data.universe import load_market_cap
                raw_cap = load_market_cap(sym, settings)
                if raw_cap and raw_cap > 0:
                    mcap_cr = round(float(raw_cap) / 1e7, 1)
            except Exception:
                pass

        holdings: list[dict[str, Any]] = []
        accumulating_count = 0
        selling_count = 0
        new_buys_count = 0
        gross_inflow_cr = 0.0
        gross_outflow_cr = 0.0

        for r in holdings_deduped:
            act = (r[9] or "HELD").upper()
            val_cr = round(float(r[7] or 0.0), 2)
            stk = round(float(r[6] or 0.0), 2)
            prev_stk = round(float(r[8] or 0.0), 2) if r[8] is not None else None
            chg_pct = round(float(r[11] or 0.0), 2) if r[11] is not None else 0.0

            is_buy = act in ("NEW BUY", "ACCUMULATED")
            is_trim = act in ("TRIMMED", "SOLD OUT", "PROFIT TAKING", "SOLD", "REDUCED")

            inc_amt_cr = 0.0
            if is_buy:
                accumulating_count += 1
                if act == "NEW BUY":
                    new_buys_count += 1
                    inc_amt_cr = val_cr
                else:
                    if prev_stk is not None and prev_stk >= 0 and stk > 0:
                        delta_stk = max(0.0, stk - prev_stk)
                        inc_amt_cr = round((delta_stk / stk) * val_cr, 2) if delta_stk > 0 else round((min(stk, max(0.05, chg_pct)) / max(0.01, stk)) * val_cr, 2)
                    else:
                        inc_amt_cr = round(val_cr * 0.35, 2)
                gross_inflow_cr += max(inc_amt_cr, 5.0)
            elif is_trim:
                selling_count += 1
                if prev_stk and prev_stk > 0 and stk > 0:
                    delta_stk = abs(prev_stk - stk)
                    inc_amt_cr = -round((delta_stk / stk) * val_cr, 2)
                elif prev_stk and prev_stk > 0:
                    inc_amt_cr = -round((prev_stk / 100.0) * (mcap_cr or 1000.0), 2)
                else:
                    inc_amt_cr = -round(max(0.1, abs(chg_pct)) * 15.0, 2)
                gross_outflow_cr += abs(inc_amt_cr)

            raw_avg = r[12]
            raw_buy = r[13] if is_buy else None
            raw_txn_p = r[14]
            raw_txn_d = r[15]
            raw_txn_t = r[16] or ("BUY" if is_buy else ("SELL" if is_trim else "HOLD"))

            d = {
                "id": r[0],
                "ticker": r[1],
                "fund_name": r[2],
                "fund_type": r[3],
                "quarter": r[4],
                "shares_held": r[5],
                "stake_pct": stk,
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
            }

            holdings.append(d)

        gross_inflow_cr = round(gross_inflow_cr, 1)
        gross_outflow_cr = round(gross_outflow_cr, 1)
        net_flow_cr = round(gross_inflow_cr - gross_outflow_cr, 1)

        # 2. Block deals
        b_rows = conn.execute(
            """
            SELECT id, deal_date, ticker, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange
            FROM institutional_block_deals
            WHERE ticker = ?
            ORDER BY deal_date DESC LIMIT 20
            """,
            (sym,),
        ).fetchall()

        deals: list[dict[str, Any]] = []
        for b in b_rows:
            deals.append({
                "id": b[0],
                "deal_date": b[1],
                "ticker": b[2],
                "client_name": b[3],
                "deal_type": b[4].upper(),
                "quantity": b[5],
                "price": round(float(b[6]), 2),
                "value_cr": round(float(b[7]), 2),
                "pct_equity": round(float(b[8] or 0.0), 2),
                "exchange": b[9],
            })

        # 3. Shareholding pattern history in strict chronological order
        p_rows = conn.execute(
            """
            SELECT quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct
            FROM shareholding_patterns
            WHERE ticker = ?
            ORDER BY rowid ASC
            """,
            (sym,),
        ).fetchall()

        # Retrieve live / latest close price from price history
        latest_p_row = conn.execute(
            "SELECT close, date FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (sym,),
        ).fetchone()
        latest_close_price = round(float(latest_p_row[0]), 2) if latest_p_row and latest_p_row[0] else None
        latest_price_date = str(latest_p_row[1]) if latest_p_row and latest_p_row[1] else None

        def _get_quarter_start_price(q_date: str) -> tuple[float | None, str | None]:
            row = conn.execute(
                "SELECT close, date FROM price_history WHERE ticker = ? AND date >= ? ORDER BY date ASC LIMIT 1",
                (sym, q_date),
            ).fetchone()
            if not row or not row[0]:
                row = conn.execute(
                    "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                    (sym, q_date),
                ).fetchone()
            if row and row[0]:
                return round(float(row[0]), 2), str(row[1])
            return None, None

        # Sort raw quarter rows strictly descending by calendar start date
        sorted_p_rows = sorted(p_rows, key=lambda r: _get_quarter_start_date(r[0]), reverse=True)

        patterns: list[dict[str, Any]] = []
        for idx, p in enumerate(sorted_p_rows):
            q_name = p[0]
            dii_val = round(float(p[3]), 2)
            pub_val = round(float(p[4]), 2)
            q_sdate = _get_quarter_start_date(q_name)
            q_sprice, q_act_date = _get_quarter_start_price(q_sdate)
            is_present_q = (idx == 0)

            # Price to display: live current price for present quarter, start price for historical quarters
            stock_price_display = latest_close_price if (is_present_q and latest_close_price is not None) else q_sprice

            patterns.append({
                "quarter": q_name,
                "promoter_pct": round(float(p[1]), 2),
                "fii_pct": round(float(p[2]), 2),
                "dii_mf_pct": dii_val,
                "dii_pct": dii_val,
                "public_retail_pct": pub_val,
                "public_pct": pub_val,
                "other_pct": round(float(p[5]), 2),
                "quarter_start_date": q_sdate,
                "quarter_start_price": q_sprice,
                "quarter_price_date": q_act_date,
                "current_price": latest_close_price,
                "latest_price_date": latest_price_date,
                "stock_price": stock_price_display,
                "is_current_quarter": is_present_q,
            })

        # Compute total institutional stake (FII + DII)
        if patterns:
            total_inst_stake_pct = round(patterns[0]["fii_pct"] + patterns[0]["dii_mf_pct"], 2)
        else:
            total_inst_stake_pct = round(sum(h["stake_pct"] for h in holdings), 2)

        # 4. FII Interest & New Entry Calculation (8-month lookback window ~ since Dec 2025)
        WINDOW_CUTOFF_DATE = "2025-12-28"
        quarter_dates_map = {
            "Q1 FY27": "2026-07-18",
            "Q4 FY26": "2026-04-16",
            "Q3 FY26": "2026-01-15",
            "Q2 FY26": "2025-10-18",
            "Q1 FY26": "2025-07-18",
        }
        window_patterns = [
            p for p in patterns
            if quarter_dates_map.get(p["quarter"], "2026-01-01") >= WINDOW_CUTOFF_DATE
        ]

        # New entry flags (checking latest quarter Q1 FY27 vs previous quarter Q4 FY26)
        is_new_fii_entry = False
        is_new_dii_entry = False
        if len(patterns) >= 2:
            latest_fii = patterns[0].get("fii_pct", 0.0)
            prev_fii = patterns[1].get("fii_pct", 0.0)
            latest_dii = patterns[0].get("dii_mf_pct", 0.0)
            prev_dii = patterns[1].get("dii_mf_pct", 0.0)
            if prev_fii == 0.0 and latest_fii > 0.0:
                is_new_fii_entry = True
            if prev_dii == 0.0 and latest_dii > 0.0:
                is_new_dii_entry = True

        # FII Interest Signal & Always-Held Fallback
        fii_always_held = True
        baseline_fii_pct = 0.0
        fii_interest_quarter = None
        fii_interest_date = None
        fii_signal_price = None
        fii_current_price = None
        fii_interest_return_pct = None
        fii_interest_summary = ""

        # Find latest current price
        curr_price_val = None
        try:
            latest_p_row = conn.execute(
                "SELECT close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                (sym,),
            ).fetchone()
            if latest_p_row and latest_p_row[0]:
                curr_price_val = round(float(latest_p_row[0]), 2)
        except Exception:
            pass

        if window_patterns:
            had_zero_fii = any(p.get("fii_pct", 0.0) == 0.0 for p in window_patterns)
            oldest_window_pat = window_patterns[-1]
            baseline_fii_pct = round(float(oldest_window_pat.get("fii_pct", 0.0)), 2)

            if not had_zero_fii and baseline_fii_pct > 0.0:
                # Stock had constant positive FII holding in the last 8 months
                fii_always_held = True
                fii_interest_summary = f"Had {baseline_fii_pct:.1f}% on Dec 2025"
            else:
                fii_always_held = False
                # Find the earliest quarter in the 8-month window where FII holding became positive
                chrono_window = list(reversed(window_patterns))
                for pat in chrono_window:
                    if pat.get("fii_pct", 0.0) > 0.0:
                        fii_interest_quarter = pat["quarter"]
                        fii_interest_date = quarter_dates_map.get(fii_interest_quarter, "2026-04-16")
                        break

                if fii_interest_date:
                    try:
                        sig_row = conn.execute(
                            "SELECT close FROM price_history WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                            (sym, fii_interest_date),
                        ).fetchone()
                        if sig_row and sig_row[0]:
                            fii_signal_price = round(float(sig_row[0]), 2)
                    except Exception:
                        pass

                    if not fii_signal_price and curr_price_val:
                        fii_signal_price = curr_price_val

                    fii_current_price = curr_price_val

                    if fii_signal_price and fii_current_price and fii_signal_price > 0:
                        fii_interest_return_pct = round(((fii_current_price - fii_signal_price) / fii_signal_price) * 100.0, 2)

                    ret_str = f"{fii_interest_return_pct:+0.1f}%" if fii_interest_return_pct is not None else "0.0%"
                    sig_p_str = f"₹{fii_signal_price:,.2f}" if fii_signal_price else "—"
                    cur_p_str = f"₹{fii_current_price:,.2f}" if fii_current_price else "—"
                    fii_interest_summary = f"Interest: {fii_interest_quarter} ({fii_interest_date}) · Signal: {sig_p_str} · Current: {cur_p_str} · Return: {ret_str}"
                else:
                    fii_interest_summary = "No FII Entry in 8M"
        else:
            fii_interest_summary = "—"

        # 5. Returns (7d, 30d, 1y)
        ret_7d, ret_30d, ret_1y = _get_ticker_returns(sym, conn)

        # Company name lookup — resolve real name from local database, never return raw ticker
        raw_name = _NAME_CACHE.get(sym)
        if not raw_name:
            try:
                row_n = conn.execute("SELECT name FROM tickers WHERE ticker = ?", (sym,)).fetchone()
                if row_n and row_n[0]:
                    raw_name = row_n[0]
                    _NAME_CACHE[sym] = raw_name
            except Exception:
                pass
        if raw_name and raw_name != sym and not raw_name.endswith(".NS") and not raw_name.endswith(".BO"):
            company_name = raw_name
        else:
            company_name = sym.replace(".NS", "").replace(".BO", "")

        # Calculate 3 Distinct Financial Metrics at the stock level
        if mcap_cr and mcap_cr > 0:
            total_inst_amount_cr = round((total_inst_stake_pct / 100.0) * mcap_cr, 1)
        else:
            total_inst_amount_cr = round(sum(h.get("total_amount_cr", 0.0) for h in holdings), 1)

        # QoQ stake addition percentage
        inst_addition_pct = 0.0
        if len(patterns) >= 2:
            lat_inst = patterns[0].get("fii_pct", 0.0) + patterns[0].get("dii_mf_pct", 0.0)
            prev_inst = patterns[1].get("fii_pct", 0.0) + patterns[1].get("dii_mf_pct", 0.0)
            inst_addition_pct = round(lat_inst - prev_inst, 2)

        stock_increase_amount_cr = round((inst_addition_pct / 100.0) * mcap_cr, 1) if (mcap_cr and inst_addition_pct != 0) else net_flow_cr

        # Compute block deal metrics & whale conviction for multi-tier scoring
        block_buy_cr = sum(float(d.get("value_cr") or 0.0) for d in deals if d.get("deal_type") == "BUY")
        block_sell_cr = sum(float(d.get("value_cr") or 0.0) for d in deals if d.get("deal_type") == "SELL")
        block_net_cr = round(block_buy_cr - block_sell_cr, 2)
        block_cnt = len(deals)

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

        # Derive institutional accumulation conviction score (0-100) using 3-tier composite:
        # Tier 1 (Macro Supply Absorption), Tier 2 (Breadth + Block Deals), Tier 3 (Whale/Marquee Conviction)
        score, verdict, verdict_badge = calculate_institutional_score(
            accumulating_count=accumulating_count,
            selling_count=selling_count,
            new_buys_count=new_buys_count,
            net_flow_cr=net_flow_cr,
            gross_inflow_cr=gross_inflow_cr,
            gross_outflow_cr=gross_outflow_cr,
            inst_addition_pct=inst_addition_pct,
            increase_amount_cr=stock_increase_amount_cr,
            total_inst_amount_cr=total_inst_amount_cr,
            block_deals_net_cr=block_net_cr,
            block_deals_count=block_cnt,
            super_investor_count=len(super_investor_names),
            marquee_amc_count=len(marquee_amc_names),
            whale_capital_cr=round(whale_cap_cr, 2),
        )

        return {
            "success": True,
            "ticker": sym,
            "company_name": company_name,
            "market_cap_cr": mcap_cr,
            "accumulation_score": score,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "funds_accumulating_count": accumulating_count,
            "funds_selling_count": selling_count,
            "new_funds_bought_count": new_buys_count,
            "gross_inflow_cr": gross_inflow_cr,
            "gross_outflow_cr": gross_outflow_cr,
            "net_flow_cr": net_flow_cr,
            # 3 Distinct Financial Metrics:
            "increase_pct": inst_addition_pct,
            "inst_addition_pct": inst_addition_pct,
            "increase_amount_cr": stock_increase_amount_cr,
            "total_amount_cr": total_inst_amount_cr,
            "total_institutional_amount_cr": total_inst_amount_cr,
            "total_institutional_stake_pct": total_inst_stake_pct,
            "total_institutional_stake": total_inst_stake_pct,
            "fii_stake_pct": patterns[0]["fii_pct"] if patterns else None,
            "dii_stake_pct": patterns[0]["dii_mf_pct"] if patterns else None,
            "is_new_fii_entry": is_new_fii_entry,
            "is_new_dii_entry": is_new_dii_entry,
            "fii_always_held": fii_always_held,
            "baseline_fii_pct": baseline_fii_pct,
            "fii_interest_quarter": fii_interest_quarter,
            "fii_interest_date": fii_interest_date,
            "fii_signal_price": fii_signal_price,
            "fii_current_price": fii_current_price,
            "fii_interest_return_pct": fii_interest_return_pct,
            "fii_interest_summary": fii_interest_summary,
            "return_7d_pct": ret_7d,
            "return_30d_pct": ret_30d,
            "return_1y_pct": ret_1y,
            "holdings": holdings,
            "block_deals": deals,
            "shareholding_patterns": patterns,
            "last_fetch": get_stock_fetch_status(sym, settings=settings, conn=conn),
        }

    except Exception as e:
        logger.error("[INSTITUTIONAL] Failed fetching activity for %s: %s", sym, e)
        return {
            "success": False,
            "ticker": sym,
            "error": str(e),
            "holdings": [],
            "block_deals": [],
            "shareholding_patterns": [],
        }
