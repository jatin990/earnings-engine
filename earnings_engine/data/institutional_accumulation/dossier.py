"""Forensic dossiers and historical quarterly financials for equities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.db_helpers import get_ticker_variants
from earnings_engine.data.institutional_accumulation.buyers import (
    _map_buyer_macro_category,
    _resolve_ticker_symbol,
    get_stock_buyers_in_period,
)
from earnings_engine.data.institutional_accumulation.db import init_institutional_db
from earnings_engine.data.nse_shareholding import get_stock_fetch_status

logger = logging.getLogger(__name__)


def get_stock_quarterly_financials(
    ticker: str,
    limit: int = 8,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve historical quarterly financial statements for a specific equity.

    Returns structured financial metrics per quarter including Revenue, PAT, Operating Margin,
    EPS, and YoY Revenue & PAT growth rates.
    """
    settings = settings or Settings()
    init_institutional_db(settings)
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)

    conn = get_db_connection(settings)
    try:
        raw_sym = (ticker or "").strip().upper()
        if not raw_sym:
            return []

        sym, _ = _resolve_ticker_symbol(raw_sym, conn=conn, settings=settings)
        if not sym:
            sym = raw_sym

        sym_variants = get_ticker_variants(sym)

        placeholders = ",".join("?" for _ in sym_variants)
        rows = conn.execute(
            f"""
            SELECT id, ticker, quarter, period_end_date, revenue_cr, net_profit_cr,
                   operating_profit_cr, operating_margin_pct, net_margin_pct, eps,
                   yoy_revenue_growth_pct, yoy_pat_growth_pct, sales_growth_yoy_pct, profit_growth_yoy_pct,
                   raw_payload_json, created_at, updated_at,
                   interest_expense_cr, total_debt_cr, debt_to_equity, interest_coverage_ratio, net_debt_cr
            FROM quarterly_financials
            WHERE ticker IN ({placeholders})
            ORDER BY period_end_date DESC, quarter DESC
            LIMIT ?
            """,
            (*sym_variants, max(1, min(40, int(limit)))),
        ).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            rev_cr = float(r[4]) if r[4] is not None else None
            np_cr = float(r[5]) if r[5] is not None else None
            op_cr = float(r[6]) if r[6] is not None else None
            op_margin = float(r[7]) if r[7] is not None else None
            net_margin = float(r[8]) if r[8] is not None else None
            eps_val = float(r[9]) if r[9] is not None else None
            yoy_rev = float(r[10]) if r[10] is not None else (float(r[12]) if r[12] is not None else None)
            yoy_pat = float(r[11]) if r[11] is not None else (float(r[13]) if r[13] is not None else None)
            int_exp_cr = float(r[17]) if len(r) > 17 and r[17] is not None else None
            tot_debt_cr = float(r[18]) if len(r) > 18 and r[18] is not None else None
            de_ratio = float(r[19]) if len(r) > 19 and r[19] is not None else None
            int_cov = float(r[20]) if len(r) > 20 and r[20] is not None else None
            net_debt_cr = float(r[21]) if len(r) > 21 and r[21] is not None else None

            results.append({
                "id": r[0],
                "ticker": r[1],
                "quarter": r[2],
                "period_end_date": r[3],
                "revenue_cr": rev_cr,
                "net_profit_cr": np_cr,
                "operating_profit_cr": op_cr,
                "operating_margin_pct": op_margin,
                "net_margin_pct": net_margin,
                "eps": eps_val,
                "yoy_revenue_growth_pct": yoy_rev,
                "yoy_pat_growth_pct": yoy_pat,
                "sales_growth_yoy_pct": yoy_rev,
                "profit_growth_yoy_pct": yoy_pat,
                "raw_payload_json": r[14],
                "created_at": r[15],
                "updated_at": r[16],
                "interest_expense_cr": int_exp_cr,
                "total_debt_cr": tot_debt_cr,
                "debt_to_equity": de_ratio,
                "interest_coverage_ratio": int_cov,
                "net_debt_cr": net_debt_cr,
            })

        # Compute dynamic QoQ and EBITDA metrics across descending quarters
        for i, q in enumerate(results):
            rev = q.get("revenue_cr")
            op = q.get("operating_profit_cr")
            pat = q.get("net_profit_cr")

            q["ebitda_cr"] = op
            q["ebitda_margin_pct"] = q.get("operating_margin_pct")

            qoq_rev = None
            qoq_op = None
            qoq_pat = None
            if i + 1 < len(results):
                prev_rev = results[i + 1].get("revenue_cr")
                prev_op = results[i + 1].get("operating_profit_cr")
                prev_pat = results[i + 1].get("net_profit_cr")
                if prev_rev and prev_rev > 0 and rev is not None:
                    qoq_rev = round(((rev - prev_rev) / prev_rev) * 100, 2)
                if prev_op and prev_op != 0 and op is not None:
                    qoq_op = round(((op - prev_op) / abs(prev_op)) * 100, 2)
                if prev_pat and prev_pat != 0 and pat is not None:
                    qoq_pat = round(((pat - prev_pat) / abs(prev_pat)) * 100, 2)

            q["qoq_revenue_growth_pct"] = qoq_rev
            q["qoq_operating_profit_growth_pct"] = qoq_op
            q["qoq_ebitda_growth_pct"] = qoq_op
            q["qoq_pat_growth_pct"] = qoq_pat

            yoy_op = None
            if i + 4 < len(results):
                prev_y_op = results[i + 4].get("operating_profit_cr")
                if prev_y_op and prev_y_op != 0 and op is not None:
                    yoy_op = round(((op - prev_y_op) / abs(prev_y_op)) * 100, 2)
            q["yoy_operating_profit_growth_pct"] = yoy_op
            q["yoy_ebitda_growth_pct"] = yoy_op

        return results
    except Exception as e:
        logger.exception("[INSTITUTIONAL] Error fetching quarterly financials for %s: %s", ticker, e)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_stock_forensic_dossier(
    ticker: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Synthesize complete 360-degree forensic institutional and fundamental dossier for an equity.

    Aggregates:
      1. Company metadata & live quote from tickers and price_history
      2. Longitudinal signal timeline & strategy triggers from institutional_radar_signals
      3. Complete institutional buyers list from filings and block deals
      4. Historical quarterly financial trajectory from quarterly_financials
      5. Real-time exchange block deals from institutional_block_deals
      6. Macro shareholding profile breakdown (Promoter, FII, DII, Public)
    """
    settings = settings or Settings()
    init_institutional_db(settings)
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)

    from earnings_engine.data.nse_shareholding import classify_institutional_entity

    conn = get_db_connection(settings)
    try:
        raw_sym = (ticker or "").strip().upper()
        sym, comp_name = _resolve_ticker_symbol(raw_sym, conn=conn, settings=settings)
        if not sym:
            sym = raw_sym
            comp_name = raw_sym

        sym_variants = get_ticker_variants(sym)

        placeholders = ",".join("?" for _ in sym_variants)

        # 1. Company metadata & market cap
        t_row = conn.execute(
            f"SELECT name, sector, industry, market_cap FROM tickers WHERE ticker IN ({placeholders}) LIMIT 1",
            sym_variants,
        ).fetchone()

        if t_row:
            if t_row[0]:
                comp_name = t_row[0]
            sector = t_row[1] or "Diversified"
            industry = t_row[2] or "General"
            raw_mcap = float(t_row[3] or 0.0)
            mcap_cr = round(raw_mcap / 1e7, 1) if raw_mcap > 0 else None
        else:
            sector = "Diversified"
            industry = "General"
            mcap_cr = None

        # 2. Latest market price and date
        ltp_row = conn.execute(
            f"SELECT close, date FROM price_history WHERE ticker IN ({placeholders}) ORDER BY date DESC LIMIT 1",
            sym_variants,
        ).fetchone()
        curr_price = round(float(ltp_row[0]), 2) if (ltp_row and ltp_row[0]) else None
        curr_price_date = str(ltp_row[1]) if (ltp_row and ltp_row[1]) else None

        # 3. Longitudinal Signal Timeline from institutional_radar_signals
        sig_rows = conn.execute(
            f"""
            SELECT id, ticker, strategy, company_name, industry, signal_date, signal_price,
                   ideal_entry_price, target_price, stop_loss, risk_reward_ratio, current_price,
                   current_date, outcome_return_pct, peak_price, max_gain_pct, days_elapsed,
                   lifecycle_status, initial_score, initial_dominance, initial_smart_money_cr,
                   whale_count, trigger_reason, entry_delay_pct, is_late, created_at, updated_at
            FROM institutional_radar_signals
            WHERE ticker IN ({placeholders})
            ORDER BY signal_date DESC, created_at DESC
            """,
            sym_variants,
        ).fetchall()

        signal_timeline: list[dict[str, Any]] = []
        for r in sig_rows:
            signal_timeline.append({
                "id": r[0],
                "ticker": r[1],
                "strategy": r[2],
                "company_name": r[3] or comp_name,
                "industry": r[4] or industry,
                "signal_date": r[5],
                "signal_price": float(r[6] or 0.0),
                "ideal_entry_price": float(r[7] or r[6] or 0.0),
                "target_price": float(r[8] or 0.0),
                "stop_loss": float(r[9] or 0.0),
                "risk_reward_ratio": float(r[10] or 2.5),
                "current_price": float(r[11] or curr_price or r[6] or 0.0),
                "current_date": r[12] or curr_price_date or r[5],
                "outcome_return_pct": float(r[13] or 0.0) if r[13] is not None else 0.0,
                "peak_price": float(r[14] or r[11] or r[6] or 0.0),
                "max_gain_pct": float(r[15] or 0.0) if r[15] is not None else 0.0,
                "days_elapsed": int(r[16] or 0),
                "lifecycle_status": r[17] or "ACTIVE",
                "initial_score": float(r[18] or 50.0),
                "initial_dominance": float(r[19] or 0.0),
                "initial_smart_money_cr": float(r[20] or 0.0),
                "whale_count": int(r[21] or 0),
                "trigger_reason": r[22] or "",
                "entry_delay_pct": float(r[23] or 0.0),
                "is_late": bool(r[24]),
                "created_at": r[25],
                "updated_at": r[26],
            })

        # 4. Institutional buyers from period inspection and filings
        buyers_data = get_stock_buyers_in_period(sym, settings=settings)
        buyers = buyers_data.get("buyers", []) if buyers_data.get("success") else []

        # If buyers is empty from get_stock_buyers_in_period, query institutional_holdings directly
        if not buyers:
            h_rows = conn.execute(
                f"""
                SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                       holding_value_cr, prev_stake_pct, action, change_shares, change_pct,
                       avg_price, recent_buy_price, recent_txn_date, reported_date
                FROM institutional_holdings
                WHERE ticker IN ({placeholders})
                ORDER BY reported_date DESC, stake_pct DESC
                """,
                sym_variants,
            ).fetchall()

            for hr in h_rows:
                fname = hr[2]
                ftype = hr[3]
                hq = hr[4]
                shs = int(hr[5] or 0)
                stk = round(float(hr[6] or 0.0), 2)
                hval = round(float(hr[7] or 0.0), 2)
                act = hr[9] or "HOLD"
                chg_shs = int(hr[10] or 0)
                chg_p = round(float(hr[11] or 0.0), 2)
                bp = round(float(hr[13] or hr[12] or 0.0), 2)
                tx_date = hr[14] or hr[15]

                e_class = classify_institutional_entity(fname)
                if "MUTUAL FUND" in (ftype or "").upper() and "MUTUAL FUND" not in e_class.upper():
                    e_class = "Mutual Fund (DII)"
                elif ftype:
                    e_class = ftype
                category = _map_buyer_macro_category(e_class)

                cap_cr = hval
                if chg_shs > 0 and bp > 0:
                    cap_cr = round((chg_shs * bp) / 1e7, 2)
                elif stk > 0 and chg_p > 0:
                    cap_cr = round((chg_p / stk) * hval, 2)

                buyers.append({
                    "investor_name": fname,
                    "buyer_name": fname,
                    "entity_type": e_class,
                    "entity_class": e_class,
                    "category": category,
                    "action": act,
                    "source": "Filing",
                    "source_label": "Quarterly / AMFI Filing",
                    "date": tx_date,
                    "quarter": hq,
                    "capital_deployed_cr": cap_cr,
                    "holding_value_cr": hval,
                    "stake_pct": stk,
                    "change_pct": chg_p,
                    "shares_added": chg_shs if chg_shs > 0 else None,
                    "shares_held": shs,
                    "price": bp if bp > 0 else None,
                    "avg_price": bp if bp > 0 else None,
                    "latest_market_price": curr_price,
                    "latest_price_date": curr_price_date,
                    "exchange": "AMFI / Disclosures",
                })

        # 5. Historical Quarterly Financials
        quarterly_income = get_stock_quarterly_financials(sym, limit=12, settings=settings)

        # 6. Real-time Block & Bulk Deals
        b_rows = conn.execute(
            f"""
            SELECT id, deal_date, ticker, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange
            FROM institutional_block_deals
            WHERE ticker IN ({placeholders})
            ORDER BY deal_date DESC, value_cr DESC
            """,
            sym_variants,
        ).fetchall()

        block_deals: list[dict[str, Any]] = []
        for br in b_rows:
            dtype = (br[4] or "").upper()
            val_cr = round(float(br[7] or 0.0), 2)
            bp = round(float(br[6] or 0.0), 2)
            block_deals.append({
                "id": br[0],
                "deal_date": br[1],
                "ticker": br[2],
                "client_name": br[3],
                "deal_type": dtype,
                "quantity": int(br[5] or 0),
                "price": bp,
                "value_cr": val_cr,
                "pct_equity": round(float(br[8] or 0.0), 2),
                "exchange": br[9] or "NSE",
            })

        # 7. Shareholding Patterns & Macro Profile
        p_rows = conn.execute(
            f"""
            SELECT quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at
            FROM shareholding_patterns
            WHERE ticker IN ({placeholders})
            ORDER BY quarter DESC
            """,
            sym_variants,
        ).fetchall()

        shareholding_patterns: list[dict[str, Any]] = []
        for pr in p_rows:
            shareholding_patterns.append({
                "quarter": pr[0],
                "promoter_pct": round(float(pr[1] or 0.0), 2),
                "fii_pct": round(float(pr[2] or 0.0), 2),
                "dii_pct": round(float(pr[3] or 0.0), 2),
                "public_pct": round(float(pr[4] or 0.0), 2),
                "other_pct": round(float(pr[5] or 0.0), 2),
                "updated_at": pr[6],
            })

        if shareholding_patterns:
            lat_p = shareholding_patterns[0]
            macro_profile = {
                "quarter": lat_p["quarter"],
                "promoter_pct": lat_p["promoter_pct"],
                "fii_pct": lat_p["fii_pct"],
                "dii_pct": lat_p["dii_pct"],
                "public_pct": lat_p["public_pct"],
                "other_pct": lat_p["other_pct"],
            }
        else:
            macro_profile = {
                "quarter": "Latest",
                "promoter_pct": 0.0,
                "fii_pct": 0.0,
                "dii_pct": 0.0,
                "public_pct": 0.0,
                "other_pct": 0.0,
            }

        # 8. Score & Verdict from cache or computation
        cache_row = conn.execute(
            f"""
            SELECT accumulation_score, verdict, verdict_badge, net_flow_cr, inst_addition_pct,
                   funds_accumulating_count, funds_selling_count
            FROM institutional_accumulation_cache
            WHERE ticker IN ({placeholders}) LIMIT 1
            """,
            sym_variants,
        ).fetchone()

        if cache_row:
            accumulation_summary = {
                "score": float(cache_row[0] or 50.0),
                "verdict": cache_row[1] or "NEUTRAL",
                "verdict_badge": cache_row[2] or "⚪ Neutral",
                "net_flow_cr": float(cache_row[3] or 0.0),
                "inst_addition_pct": float(cache_row[4] or 0.0),
                "funds_accumulating_count": int(cache_row[5] or 0),
                "funds_selling_count": int(cache_row[6] or 0),
            }
        else:
            accumulation_summary = {
                "score": 50.0,
                "verdict": "NEUTRAL",
                "verdict_badge": "⚪ Neutral",
                "net_flow_cr": 0.0,
                "inst_addition_pct": 0.0,
                "funds_accumulating_count": len([b for b in buyers if b.get("action") in ("NEW BUY", "ACCUMULATED")]),
                "funds_selling_count": 0,
            }

        return {
            "success": True,
            "ticker": sym,
            "company_name": comp_name,
            "sector": sector,
            "industry": industry,
            "market_cap_cr": mcap_cr,
            "current_price": curr_price,
            "current_price_date": curr_price_date,
            "signal_timeline": signal_timeline,
            "buyers": buyers,
            "quarterly_income": quarterly_income,
            "quarterly_financials": quarterly_income,
            "block_deals": block_deals,
            "macro_profile": macro_profile,
            "shareholding_patterns": shareholding_patterns,
            "accumulation_summary": accumulation_summary,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "last_fetch": get_stock_fetch_status(sym, settings=settings, conn=conn),
        }
    except Exception as e:
        logger.exception("[INSTITUTIONAL] Error generating forensic dossier for %s: %s", ticker, e)
        return {
            "success": False,
            "ticker": ticker,
            "error": str(e),
            "signal_timeline": [],
            "buyers": [],
            "quarterly_income": [],
            "block_deals": [],
            "macro_profile": {},
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
