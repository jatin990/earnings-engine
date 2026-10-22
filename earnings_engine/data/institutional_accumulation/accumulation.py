"""Cross-sectional screening for equities experiencing aggressive institutional smart money accumulation."""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.institutional_accumulation.buyers import (
    _map_buyer_macro_category,
    _normalize_query_dates,
    _parse_fiscal_quarter,
)
from earnings_engine.data.institutional_accumulation.cache import _get_inst_cache, _set_inst_cache
from earnings_engine.data.institutional_accumulation.strategies import _get_or_create_radar_signals
from earnings_engine.data.names import get_name

logger = logging.getLogger(__name__)


def _attach_fundamentals_and_eps(
    screened_stocks: list[dict[str, Any]],
    conn: Any,
    min_eps_growth_threshold: float = 20.0,
) -> None:
    """Extract quarterly EPS results, compute YoY growth, and identify Emerging Multi-Bagger equities.

    Features:
    - Analyzes earnings_history to extract reported quarterly EPS.
    - Computes YoY quarterly EPS growth (Q0 vs Q-4) with fallbacks to QoQ if fewer quarters exist.
    - Tracks beat streak and P/E valuation.
    - Classifies Small Cap / Micro Cap equities (< ₹15,000 Cr market cap) as Emerging.
    - Awards '🌟 Emerging EPS Rocket' or '🌱 Emerging Smart Money' badges.
    """
    if not screened_stocks:
        return

    tickers = [s["ticker"] for s in screened_stocks]
    placeholders = ",".join("?" * len(tickers))

    # 1. Fetch reported quarterly EPS history
    eps_map: dict[str, list[tuple[str, float, float | None, float | None]]] = defaultdict(list)
    try:
        e_rows = conn.execute(
            f"""
            SELECT ticker, earnings_date, eps_reported, eps_estimate, surprise_pct
            FROM earnings_history
            WHERE ticker IN ({placeholders}) AND eps_reported IS NOT NULL
            ORDER BY ticker, earnings_date DESC
            """,
            tickers,
        ).fetchall()
        for r in e_rows:
            sym, edate, rep, est, sur = r
            eps_map[sym].append((edate, float(rep), float(est) if est is not None else None, float(sur) if sur is not None else None))
    except Exception as e:
        logger.debug("[INSTITUTIONAL] EPS history fetch error: %s", e)

    # 2. Calculate and attach for each stock
    for s in screened_stocks:
        sym = s["ticker"]
        hist = eps_map.get(sym, [])

        latest_eps = None
        latest_quarter = None
        eps_estimate = None
        eps_surprise_pct = None
        eps_growth_yoy = None
        beat_streak = 0
        pe_ratio = None

        if hist:
            latest_quarter = hist[0][0]
            latest_eps = round(hist[0][1], 2)
            eps_estimate = round(hist[0][2], 2) if hist[0][2] is not None else None
            eps_surprise_pct = round(hist[0][3], 2) if hist[0][3] is not None else None

            # Calculate YoY EPS growth (compare Q0 with Q-4)
            if len(hist) >= 5:
                q0_eps = hist[0][1]
                q4_eps = hist[4][1]
                if abs(q4_eps) > 0.001:
                    eps_growth_yoy = round(((q0_eps - q4_eps) / abs(q4_eps)) * 100.0, 1)
            elif len(hist) >= 2:
                q0_eps = hist[0][1]
                q_prev_eps = hist[1][1]
                if abs(q_prev_eps) > 0.001:
                    eps_growth_yoy = round(((q0_eps - q_prev_eps) / abs(q_prev_eps)) * 100.0, 1)

            # Compute beat streak
            for _q_date, rep_val, est_val, sur_val in hist:
                if sur_val is not None and sur_val >= 0:
                    beat_streak += 1
                elif est_val is not None and rep_val >= est_val:
                    beat_streak += 1
                elif est_val is None:
                    if rep_val > 0:
                        beat_streak += 1
                    else:
                        break
                else:
                    break

            # Estimate P/E ratio if current price and TTM EPS available
            curr_p = s.get("current_price") or 0.0
            ttm_eps = sum(h[1] for h in hist[:4])
            if ttm_eps > 0.1 and curr_p > 0:
                pe_ratio = round(curr_p / ttm_eps, 1)

        # Emerging stock definition: Small Cap / Micro Cap (< ₹15,000 Cr)
        mcap_cr = float(s.get("market_cap_cr") or 0.0)
        cap_cat = s.get("cap_category") or ""
        is_emerging = (cap_cat in ("Small Cap", "Micro Cap")) or (0 < mcap_cr < 15000.0)
        has_good_eps = bool(eps_growth_yoy is not None and eps_growth_yoy >= min_eps_growth_threshold)

        # Upgrade badges for high-conviction emerging stocks
        dom_pct = float(s.get("dominance_pct") or 0.0)
        if is_emerging and has_good_eps and dom_pct >= 50.0:
            s["signal_badge"] = "🌟 Emerging EPS Rocket"
            s["badge"] = "🌟 Emerging EPS Rocket"
            s["accumulation_signal_badge"] = "🌟 Emerging EPS Rocket"
            s["signal_color"] = "emerald"
        elif is_emerging and dom_pct >= 60.0 and s.get("classification") != "domestic_absorption":
            s["signal_badge"] = "🌱 Emerging Smart Money"
            s["badge"] = "🌱 Emerging Smart Money"
            s["accumulation_signal_badge"] = "🌱 Emerging Smart Money"
            s["signal_color"] = "teal"

        s["latest_eps"] = latest_eps
        s["latest_quarter"] = latest_quarter
        s["eps_estimate"] = eps_estimate
        s["eps_surprise_pct"] = eps_surprise_pct
        s["eps_growth_yoy"] = eps_growth_yoy
        s["beat_streak"] = beat_streak
        s["pe_ratio"] = pe_ratio
        s["is_emerging"] = is_emerging
        s["has_good_eps"] = has_good_eps
        s["fundamentals"] = {
            "latest_eps": latest_eps,
            "latest_quarter": latest_quarter,
            "eps_estimate": eps_estimate,
            "eps_surprise_pct": eps_surprise_pct,
            "eps_growth_yoy": eps_growth_yoy,
            "beat_streak": beat_streak,
            "pe_ratio": pe_ratio,
            "is_emerging": is_emerging,
            "has_good_eps": has_good_eps,
        }


def get_stocks_under_institutional_accumulation(
    window: str = "90d",
    entity_focus: str = "smart_money",
    min_cr: float = 5.0,
    sort_by: str = "score",
    limit: int = 50,
    emerging_only: bool = False,
    min_eps_growth: float | None = None,
    new_entrants_only: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve equities experiencing aggressive smart money institutional accumulation across rolling time windows.

    Separates catalytic Smart Money (FIIs, Foreign Sovereign Funds, Super Investors, AIFs, and Block Deals)
    from passive Domestic Absorption (routine retail SIP inflows into mature large-caps).

    Args:
        window: Lookback horizon ('30d', '90d', '180d', '365d', '1y'). Default '90d'.
        entity_focus: 'smart_money', 'all', 'fii_only', 'super_investor', 'block_deals'.
        min_cr: Minimum capital deployed threshold in ₹ Cr. Default 5.0 Cr.
        sort_by: Ranking key ('score', 'capital', 'dominance', 'return_30d'). Default 'score'.
        limit: Max stocks to return (1-200). Default 50.
        emerging_only: Filter for small/micro cap emerging companies.
        min_eps_growth: Filter for minimum YoY EPS growth %.
        new_entrants_only: Filter for new entrants in institutional filings.
        settings: Settings instance.
    """
    settings = settings or Settings()
    db_ctx = str(getattr(settings, "database_url", "") or getattr(settings, "db_path", "") or str(settings.data_dirs.get("prices", "")))
    cache_key = (
        f"smart_money_acc:{db_ctx}:{window}:{entity_focus}:{min_cr}:{sort_by}:{limit}:"
        f"{emerging_only}:{min_eps_growth}:{new_entrants_only}"
    )
    cached = _get_inst_cache(cache_key)
    if cached is not None:
        return cached

    # Normalize dates
    start_date, end_date, canonical_q = _normalize_query_dates(from_date=window)
    desc_parts = []
    if start_date:
        desc_parts.append(f"From {start_date}")
    if end_date:
        desc_parts.append(f"To {end_date}")
    if canonical_q:
        desc_parts.append(f"Quarter {canonical_q}")
    period_description = " - ".join(desc_parts) if desc_parts else f"Window: {window}"

    window_labels = {
        "30d": "Last 30 Days (Fast Flow & Breakouts)",
        "90d": "Last 90 Days (Quarterly Accumulation)",
        "180d": "Last 180 Days (Deep Structural Accumulation)",
        "365d": "Last 1 Year (Whale Position Building)",
        "1y": "Last 1 Year (Whale Position Building)",
    }
    window_label = window_labels.get(window.lower(), f"Lookback: {window}")

    conn = get_db_connection(settings)
    try:
        from earnings_engine.data.nse_shareholding import classify_institutional_entity

        # 1. Fetch all institutional holdings additions / new buys
        h_rows = conn.execute(
            """
            SELECT h.ticker, h.fund_name, h.fund_type, h.action, h.quarter,
                   h.holding_value_cr, h.stake_pct, h.change_pct, h.change_shares,
                   COALESCE(h.recent_buy_price, h.recent_txn_price, h.avg_price, 0.0) AS buy_price,
                   h.recent_txn_date, h.reported_date
            FROM institutional_holdings h
            WHERE (h.action IN ('NEW BUY', 'INCREASE', 'ACCUMULATED') OR h.change_pct > 0 OR h.change_shares > 0)
              AND h.holding_value_cr > 0
            """
        ).fetchall()

        # Aggregation buckets per ticker
        stocks_acc: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "fii_cr": 0.0,
            "fii_count": 0,
            "super_inv_cr": 0.0,
            "super_inv_count": 0,
            "aif_cr": 0.0,
            "aif_count": 0,
            "dii_cr": 0.0,
            "dii_count": 0,
            "block_deals_cr": 0.0,
            "block_deals_count": 0,
            "other_cr": 0.0,
            "other_count": 0,
            "buyers": [],
        })

        for r in h_rows:
            (
                sym, fund_name, raw_fund_type, action, h_quarter,
                holding_val_cr, stake_pct, change_pct, change_shares,
                buy_price, txn_date, reported_date
            ) = r

            holding_val_cr = float(holding_val_cr or 0.0)
            stake_pct = float(stake_pct or 0.0)
            change_pct = float(change_pct or 0.0)
            change_shares = int(change_shares or 0)
            buy_price = float(buy_price or 0.0)

            # Date / quarter matching
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

            # Classify entity
            classified_type = classify_institutional_entity(fund_name)
            if "MUTUAL FUND" in (raw_fund_type or "").upper() and "MUTUAL FUND" not in classified_type.upper():
                entity_class = "Mutual Fund (DII)"
            elif classified_type in ("Institutional Investor (DII/FII)", "Domestic Institutional (DII)") and raw_fund_type:
                entity_class = raw_fund_type
            else:
                entity_class = classified_type

            category = _map_buyer_macro_category(entity_class)

            # Estimate capital deployed (₹ Cr)
            if change_shares > 0 and buy_price > 0:
                capital_cr = round((change_shares * buy_price) / 1e7, 2)
            elif action == "NEW BUY" and (change_pct >= stake_pct or change_pct == 0.0):
                capital_cr = holding_val_cr
            elif stake_pct > 0 and change_pct > 0:
                capital_cr = round((change_pct / stake_pct) * holding_val_cr, 2)
            else:
                capital_cr = round(holding_val_cr * 0.2, 2)

            if capital_cr <= 0:
                continue

            target = stocks_acc[sym]
            if category == "FII":
                target["fii_cr"] += capital_cr
                target["fii_count"] += 1
            elif category == "Super Investor":
                target["super_inv_cr"] += capital_cr
                target["super_inv_count"] += 1
            elif category == "AIF":
                target["aif_cr"] += capital_cr
                target["aif_count"] += 1
            elif category == "DII":
                target["dii_cr"] += capital_cr
                target["dii_count"] += 1
            else:
                target["other_cr"] += capital_cr
                target["other_count"] += 1

            target["buyers"].append({
                "name": fund_name,
                "buyer_name": fund_name,
                "client_name": fund_name,
                "entity_type": entity_class,
                "category": category,
                "capital_cr": capital_cr,
                "deployed_cr": capital_cr,
                "value_cr": capital_cr,
                "source": "Filing",
                "date": txn_date or reported_date,
                "deal_date": txn_date or reported_date,
                "filing_date": reported_date or txn_date,
                "stake_pct": round(float(stake_pct), 2) if stake_pct else None,
                "change_pct": round(float(change_pct), 2) if change_pct else None,
                "quantity": int(change_shares) if change_shares else None,
                "shares": int(change_shares) if change_shares else None,
                "avg_price": round(float(buy_price), 2) if buy_price else None,
                "price": round(float(buy_price), 2) if buy_price else None,
            })

        # 2. Fetch block deal buys within window
        b_rows = conn.execute(
            """
            SELECT ticker, deal_date, client_name, quantity, price, value_cr, pct_equity, exchange
            FROM institutional_block_deals
            WHERE deal_type = 'BUY' AND value_cr > 0
            """
        ).fetchall()

        for r in b_rows:
            sym, deal_date, client_name, qty, price, val_cr, pct_eq, exchange = r
            val_cr = float(val_cr or 0.0)

            # Date matching
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

            classified_type = classify_institutional_entity(client_name)
            category = _map_buyer_macro_category(classified_type)

            target = stocks_acc[sym]
            target["block_deals_cr"] += val_cr
            target["block_deals_count"] += 1

            if category == "FII":
                target["fii_cr"] += val_cr
                target["fii_count"] += 1
            elif category == "Super Investor":
                target["super_inv_cr"] += val_cr
                target["super_inv_count"] += 1
            elif category == "AIF":
                target["aif_cr"] += val_cr
                target["aif_count"] += 1

            target["buyers"].append({
                "name": client_name,
                "buyer_name": client_name,
                "client_name": client_name,
                "entity_type": classified_type if classified_type != "Other / Entity" else f"Block Buy ({exchange})",
                "category": category if category != "Other" else "Block Deal",
                "capital_cr": val_cr,
                "deployed_cr": val_cr,
                "value_cr": val_cr,
                "source": "Block Deal",
                "date": deal_date,
                "deal_date": deal_date,
                "filing_date": deal_date,
                "stake_pct": round(float(pct_eq), 2) if pct_eq else None,
                "change_pct": None,
                "quantity": int(qty) if qty else None,
                "shares": int(qty) if qty else None,
                "avg_price": round(float(price), 2) if price else None,
                "price": round(float(price), 2) if price else None,
            })

        # 2.5 Synthesize authentic quarterly shareholding accumulation from precomputed cache
        pat_cache_rows = conn.execute(
            """
            SELECT ticker, company_name, market_cap_cr, accumulation_score, verdict, verdict_badge,
                   inst_addition_pct, increase_amount_cr, fii_stake_pct, dii_stake_pct,
                   shareholding_patterns_json, updated_at
            FROM institutional_accumulation_cache
            WHERE inst_addition_pct > 0
            """
        ).fetchall()

        for pr in pat_cache_rows:
            p_sym, p_cname, p_mcap, p_score, p_verd, p_badge, p_add_pct, p_inc_amt, p_fii, p_dii, p_json, p_upd = pr
            if not p_sym:
                continue

            p_mcap = float(p_mcap or 0.0)
            p_add_pct = float(p_add_pct or 0.0)
            p_inc_amt = float(p_inc_amt or 0.0)

            # If symbol already has granular filing buyers or block buyers, skip augmenting
            if p_sym in stocks_acc and stocks_acc[p_sym]["buyers"]:
                continue

            p_pats = json.loads(p_json or "[]")
            fii_delta = 0.0
            dii_delta = 0.0
            lat_q = "Q1 FY27"
            prev_q = "Q4 FY26"
            if len(p_pats) >= 2:
                lat_q = p_pats[0].get("quarter", "Q1 FY27")
                prev_q = p_pats[1].get("quarter", "Q4 FY26")
                fii_delta = round(float(p_pats[0].get("fii_pct", 0.0)) - float(p_pats[1].get("fii_pct", 0.0)), 2)
                dii_delta = round(float(p_pats[0].get("dii_mf_pct", 0.0)) - float(p_pats[1].get("dii_mf_pct", 0.0)), 2)
            elif len(p_pats) == 1:
                lat_q = p_pats[0].get("quarter", "Q1 FY27")
                fii_delta = round(float(p_pats[0].get("fii_pct", 0.0)), 2)
                dii_delta = round(float(p_pats[0].get("dii_mf_pct", 0.0)), 2)

            fii_amt = round((fii_delta / 100.0) * p_mcap, 2) if (p_mcap > 0 and fii_delta > 0) else round(fii_delta * 100.0, 2)
            dii_amt = round((dii_delta / 100.0) * p_mcap, 2) if (p_mcap > 0 and dii_delta > 0) else round(dii_delta * 100.0, 2)

            pat_date = "2026-08-30"
            if p_pats and isinstance(p_pats, list) and len(p_pats) > 0:
                pat_date = p_pats[0].get("quarter_price_date") or p_pats[0].get("quarter_start_date") or (p_upd[:10] if p_upd else "2026-08-30")

            target = stocks_acc[p_sym]
            if fii_delta > 0 and fii_amt > 0:
                target["fii_cr"] += fii_amt
                target["fii_count"] += 1
                target["buyers"].append({
                    "name": "Foreign Portfolio Investors",
                    "buyer_name": f"Foreign Portfolio Investors ({lat_q} vs {prev_q})",
                    "client_name": f"Foreign Portfolio Investors ({lat_q} vs {prev_q})",
                    "entity_type": "Foreign Institutional (FII)",
                    "category": "FII",
                    "capital_cr": fii_amt,
                    "deployed_cr": fii_amt,
                    "value_cr": fii_amt,
                    "source": "Filing",
                    "date": pat_date,
                    "deal_date": pat_date,
                    "filing_date": pat_date,
                    "stake_pct": round(float(p_fii or 0.0), 2),
                    "change_pct": fii_delta,
                    "quantity": None,
                    "shares": None,
                    "avg_price": None,
                    "price": None,
                })

            if dii_delta > 0 and dii_amt > 0:
                target["dii_cr"] += dii_amt
                target["dii_count"] += 1
                target["buyers"].append({
                    "name": "Domestic Mutual Funds & Inst",
                    "buyer_name": f"Domestic Mutual Funds & Inst ({lat_q} vs {prev_q})",
                    "client_name": f"Domestic Mutual Funds & Inst ({lat_q} vs {prev_q})",
                    "entity_type": "Mutual Fund (DII)",
                    "category": "DII",
                    "capital_cr": dii_amt,
                    "deployed_cr": dii_amt,
                    "value_cr": dii_amt,
                    "source": "Filing",
                    "date": pat_date,
                    "deal_date": pat_date,
                    "filing_date": pat_date,
                    "stake_pct": round(float(p_dii or 0.0), 2),
                    "change_pct": dii_delta,
                    "quantity": None,
                    "shares": None,
                    "avg_price": None,
                    "price": None,
                })

        # 3. Load metadata from tickers and institutional_accumulation_cache
        meta_dict: dict[str, dict[str, Any]] = {}
        t_rows = conn.execute(
            """
            SELECT ticker, name, sector, industry, market_cap
            FROM tickers
            """
        ).fetchall()
        for tr in t_rows:
            sym, tname, sec, ind, mcap = tr
            mcap_cr = round(float(mcap or 0.0) / 1e7, 1) if mcap else 0.0
            meta_dict[sym] = {
                "company_name": tname,
                "sector": sec or "Diversified",
                "industry": ind or "General",
                "market_cap_cr": mcap_cr,
                "cap_category": None,
                "current_price": None,
                "change_pct": 0.0,
                "return_7d_pct": None,
                "return_30d_pct": None,
                "return_1y_pct": None,
            }

        cache_rows = conn.execute(
            """
            SELECT ticker, company_name, market_cap_cr, return_7d_pct, return_30d_pct, return_1y_pct
            FROM institutional_accumulation_cache
            """
        ).fetchall()
        for cr in cache_rows:
            sym, cname, mcap_cr, r7, r30, r1y = cr
            if sym not in meta_dict:
                meta_dict[sym] = {
                    "company_name": cname,
                    "sector": "Diversified",
                    "industry": "General",
                    "market_cap_cr": float(mcap_cr or 0.0),
                    "cap_category": None,
                    "current_price": None,
                    "change_pct": 0.0,
                    "return_7d_pct": r7,
                    "return_30d_pct": r30,
                    "return_1y_pct": r1y,
                }
            else:
                if cname:
                    meta_dict[sym]["company_name"] = cname
                if mcap_cr:
                    meta_dict[sym]["market_cap_cr"] = float(mcap_cr)
                meta_dict[sym]["return_7d_pct"] = r7
                meta_dict[sym]["return_30d_pct"] = r30
                meta_dict[sym]["return_1y_pct"] = r1y

        # 4. Synthesize, score, classify and filter stocks
        screened_stocks: list[dict[str, Any]] = []

        for sym, data in stocks_acc.items():
            fii_cr = round(data["fii_cr"], 2)
            super_inv_cr = round(data["super_inv_cr"], 2)
            aif_cr = round(data["aif_cr"], 2)
            block_deals_cr = round(data["block_deals_cr"], 2)
            dii_cr = round(data["dii_cr"], 2)

            buyers_list = data["buyers"]
            if not buyers_list:
                continue

            sm_cr = 0.0
            dom_cr = 0.0
            for b in buyers_list:
                cat = b.get("category")
                b_val = float(b.get("capital_cr") or 0.0)
                if cat in ("FII", "Super Investor", "AIF", "Block Deal"):
                    sm_cr += b_val
                elif cat == "DII":
                    dom_cr += b_val
                else:
                    if b.get("source") == "Block Deal":
                        sm_cr += b_val
                    else:
                        dom_cr += b_val

            smart_money_cr = round(sm_cr, 2)
            domestic_cr = round(dom_cr, 2)
            total_capital_cr = round(smart_money_cr + domestic_cr, 2)

            if total_capital_cr <= 0:
                continue

            dominance_pct = round((smart_money_cr / max(total_capital_cr, 0.01)) * 100.0, 1)

            # Filter by entity_focus & min_cr
            focus_lower = entity_focus.lower()
            if focus_lower == "smart_money":
                if smart_money_cr < min_cr:
                    continue
            elif focus_lower == "fii_only":
                if fii_cr < min_cr:
                    continue
            elif focus_lower == "super_investor":
                if super_inv_cr < min_cr:
                    continue
            elif focus_lower == "block_deals":
                if block_deals_cr < min_cr:
                    continue
            else:  # "all"
                if total_capital_cr < min_cr:
                    continue

            # Metadata enrichment
            m = meta_dict.get(sym, {})
            company_name = m.get("company_name") or get_name(sym) or sym
            sector = m.get("sector") or "Diversified"
            industry = m.get("industry") or "General"
            mcap_cr = round(float(m.get("market_cap_cr") or 0.0), 1)

            cap_cat = m.get("cap_category")
            if not cap_cat or cap_cat == "Unknown":
                if mcap_cr >= 20000:
                    cap_cat = "Large Cap"
                elif mcap_cr >= 5000:
                    cap_cat = "Mid Cap"
                elif mcap_cr >= 1000:
                    cap_cat = "Small Cap"
                else:
                    cap_cat = "Micro Cap"

            curr_price = m.get("current_price")
            ret_7d = m.get("return_7d_pct")
            ret_30d = m.get("return_30d_pct")
            ret_1y = m.get("return_1y_pct")
            chg_pct = m.get("change_pct") or 0.0

            # Signal classification
            fii_cnt = data["fii_count"]
            super_cnt = data["super_inv_count"]
            block_cnt = data["block_deals_count"]
            aif_cnt = data["aif_count"]

            if dominance_pct >= 60.0 and smart_money_cr >= 15.0:
                signal_badge = "⭐ High Smart Money Conviction"
                signal_type = "high_conviction"
                signal_color = "emerald"
            elif fii_cr >= 15.0 and (fii_cr >= (0.5 * total_capital_cr)):
                signal_badge = "🚀 FII Whale Inflow"
                signal_type = "fii_whale"
                signal_color = "blue"
            elif super_inv_cr >= 5.0 or super_cnt >= 1:
                signal_badge = "👑 Super Investor Entry"
                signal_type = "super_investor"
                signal_color = "purple"
            elif block_deals_cr >= 20.0 or block_cnt >= 2:
                signal_badge = "⚡ Block Deal Frenzy"
                signal_type = "block_deals"
                signal_color = "amber"
            elif domestic_cr >= 10.0 and dominance_pct < 30.0:
                signal_badge = "⚠️ Domestic Absorption"
                signal_type = "domestic_absorption"
                signal_color = "rose"
            else:
                signal_badge = "🟢 Steady Accumulation"
                signal_type = "steady"
                signal_color = "green"

            # Quantitative Conviction Score (0-100)
            score_cap = min(35.0, math.log10(max(1.0, smart_money_cr)) * 12.0) if smart_money_cr > 0 else 0.0
            score_dom = min(30.0, (dominance_pct / 100.0) * 30.0)
            score_whale = min(20.0, (fii_cnt * 4.0) + (super_cnt * 6.0) + (block_cnt * 2.5) + (aif_cnt * 3.0))

            mom_30 = max(-10.0, min(30.0, ret_30d or 0.0))
            mom_7 = max(-5.0, min(15.0, ret_7d or 0.0))
            score_mom = max(0.0, min(15.0, (mom_30 * 0.3) + (mom_7 * 0.4) + 5.0))

            raw_score = round(score_cap + score_dom + score_whale + score_mom, 1)
            conviction_score = raw_score
            is_absorption_capped = False
            if signal_type == "domestic_absorption":
                if conviction_score > 40.0:
                    conviction_score = 40.0
                    is_absorption_capped = True
            conviction_score = max(0.0, min(100.0, conviction_score))

            score_breakdown = {
                "capital_score": round(score_cap, 1),
                "capital_max": 35.0,
                "dominance_score": round(score_dom, 1),
                "dominance_max": 30.0,
                "whale_quality_score": round(score_whale, 1),
                "whale_quality_max": 20.0,
                "momentum_score": round(score_mom, 1),
                "momentum_max": 15.0,
                "absorption_penalty": is_absorption_capped,
                "raw_total": raw_score,
                "final_score": conviction_score,
            }

            # Top distinct buyers sorted by capital
            grouped_buyers: dict[str, dict[str, Any]] = {}
            for b in buyers_list:
                bname = b.get("name") or b.get("buyer_name") or b.get("client_name") or "Anonymous Institution"
                if bname not in grouped_buyers:
                    grouped_buyers[bname] = {
                        "name": bname,
                        "buyer_name": bname,
                        "client_name": bname,
                        "entity_type": b.get("entity_type") or "Institution",
                        "category": b.get("category") or "Smart Money",
                        "capital_cr": 0.0,
                        "deployed_cr": 0.0,
                        "value_cr": 0.0,
                        "source": b.get("source") or "Filing",
                        "date": b.get("date") or b.get("deal_date") or b.get("filing_date"),
                        "deal_date": b.get("deal_date") or b.get("date"),
                        "filing_date": b.get("filing_date") or b.get("date"),
                        "stake_pct": b.get("stake_pct"),
                        "change_pct": b.get("change_pct"),
                        "quantity": b.get("quantity") or b.get("shares"),
                        "shares": b.get("shares") or b.get("quantity"),
                        "avg_price": b.get("avg_price") or b.get("price"),
                        "price": b.get("price") or b.get("avg_price"),
                    }
                val = float(b.get("capital_cr") or b.get("deployed_cr") or b.get("value_cr") or 0.0)
                grouped_buyers[bname]["capital_cr"] += val
                grouped_buyers[bname]["deployed_cr"] += val
                grouped_buyers[bname]["value_cr"] += val

                if b.get("stake_pct") is not None and not grouped_buyers[bname].get("stake_pct"):
                    grouped_buyers[bname]["stake_pct"] = b.get("stake_pct")
                if b.get("avg_price") is not None and not grouped_buyers[bname].get("avg_price"):
                    grouped_buyers[bname]["avg_price"] = b.get("avg_price")
                    grouped_buyers[bname]["price"] = b.get("avg_price")
                if b.get("quantity") is not None:
                    grouped_buyers[bname]["quantity"] = (grouped_buyers[bname].get("quantity") or 0) + (b.get("quantity") or 0)
                    grouped_buyers[bname]["shares"] = grouped_buyers[bname]["quantity"]

            for gb in grouped_buyers.values():
                gb["capital_cr"] = round(gb["capital_cr"], 2)
                gb["deployed_cr"] = gb["capital_cr"]
                gb["value_cr"] = gb["capital_cr"]

            sorted_buyers = sorted(grouped_buyers.values(), key=lambda x: x["capital_cr"], reverse=True)
            top_buyers = [
                {
                    "name": sb["name"],
                    "buyer_name": sb["name"],
                    "client_name": sb["name"],
                    "entity_type": sb["entity_type"],
                    "category": sb["category"],
                    "capital_cr": sb["capital_cr"],
                    "deployed_cr": sb["deployed_cr"],
                    "value_cr": sb["value_cr"],
                    "source": sb["source"],
                    "date": sb["date"],
                    "deal_date": sb["deal_date"],
                    "filing_date": sb["filing_date"],
                    "stake_pct": sb.get("stake_pct"),
                    "quantity": sb.get("quantity"),
                    "shares": sb.get("shares"),
                    "avg_price": sb.get("avg_price"),
                    "price": sb.get("price"),
                }
                for sb in sorted_buyers[:4]
            ]

            top_buyer_names = [b["name"] for b in top_buyers]
            whale_buyers_summary = [f"{b['name']} ({b['entity_type']})" for b in top_buyers[:3]]

            screened_stocks.append({
                "ticker": sym,
                "company_name": company_name,
                "sector": sector,
                "industry": industry,
                "market_cap_cr": mcap_cr,
                "cap_category": cap_cat,
                "current_price": curr_price,
                "change_pct": chg_pct,
                "return_7d_pct": ret_7d,
                "return_30d_pct": ret_30d,
                "return_1y_pct": ret_1y,
                "smart_money_cr": smart_money_cr,
                "smart_money_inflow_cr": smart_money_cr,
                "domestic_cr": domestic_cr,
                "domestic_inflow_cr": domestic_cr,
                "domestic_absorption_cr": domestic_cr,
                "total_capital_cr": total_capital_cr,
                "total_inflow_cr": total_capital_cr,
                "smart_money_dominance_pct": dominance_pct,
                "dominance_pct": dominance_pct,
                "fii_cr": fii_cr,
                "fii_count": fii_cnt,
                "super_inv_cr": super_inv_cr,
                "super_inv_count": super_cnt,
                "aif_cr": aif_cr,
                "aif_count": aif_cnt,
                "block_deals_cr": block_deals_cr,
                "block_deals_count": block_cnt,
                "smart_money_buyers_count": fii_cnt + super_cnt + aif_cnt + block_cnt,
                "buyers_count": len(grouped_buyers),
                "top_buyers": top_buyers,
                "top_buyer_names": top_buyer_names,
                "whale_buyers_summary": whale_buyers_summary,
                "whale_buyers": sorted_buyers,
                "signal_badge": signal_badge,
                "badge": signal_badge,
                "accumulation_signal_badge": signal_badge,
                "signal_type": signal_type,
                "classification": signal_type,
                "classification_category": signal_type,
                "signal_color": signal_color,
                "conviction_score": conviction_score,
                "score": conviction_score,
                "accumulation_score": conviction_score,
                "smart_money_conviction_score": conviction_score,
                "score_breakdown": score_breakdown,
                "buyers": buyers_list,
                "breakdown": {
                    "fii_cr": fii_cr,
                    "super_investor_cr": super_inv_cr,
                    "aif_cr": aif_cr,
                    "block_deals_cr": block_deals_cr,
                    "dii_cr": dii_cr,
                },
            })

        # 5. Fill missing current prices for screened_stocks from price_history
        tickers_needing_price = [s["ticker"] for s in screened_stocks if not s.get("current_price")]
        if tickers_needing_price:
            placeholders = ",".join("?" * len(tickers_needing_price))
            p_rows = conn.execute(
                f"""
                SELECT ticker, close FROM (
                    SELECT ticker, close, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                    FROM price_history
                    WHERE ticker IN ({placeholders})
                ) WHERE rn = 1
                """,
                tickers_needing_price,
            ).fetchall()
            price_map = {pr[0]: round(float(pr[1]), 2) for pr in p_rows if pr[1] is not None}
            for s in screened_stocks:
                if not s.get("current_price") and s["ticker"] in price_map:
                    s["current_price"] = price_map[s["ticker"]]

        # 6. Signal Tracking & Historical Entry Ledger
        _get_or_create_radar_signals(
            screened_stocks,
            conn,
            as_of_date=end_date or "2026-09-10",
            default_window=window,
        )

        # 7. Fundamental EPS & Emerging Multi-Bagger Synthesis
        _attach_fundamentals_and_eps(
            screened_stocks,
            conn,
            min_eps_growth_threshold=min_eps_growth if min_eps_growth is not None else 20.0,
        )

        # Commit signal ledger updates to SQLite
        try:
            conn.commit()
        except Exception:
            pass

        # 8. User-triggered Filters (Emerging, Good EPS Growth, New Entrants)
        if emerging_only:
            screened_stocks = [s for s in screened_stocks if s.get("is_emerging")]
        if min_eps_growth is not None:
            screened_stocks = [
                s for s in screened_stocks
                if s.get("eps_growth_yoy") is not None and s.get("eps_growth_yoy") >= min_eps_growth
            ]
        if new_entrants_only:
            screened_stocks = [s for s in screened_stocks if s.get("is_new_entrant")]

        # 9. Sorting
        sort_key = sort_by.lower()
        if sort_key == "capital":
            screened_stocks.sort(key=lambda s: (s["smart_money_cr"], s["conviction_score"]), reverse=True)
        elif sort_key == "dominance":
            screened_stocks.sort(key=lambda s: (s["smart_money_dominance_pct"], s["smart_money_cr"]), reverse=True)
        elif sort_key == "return_30d":
            screened_stocks.sort(key=lambda s: (s["return_30d_pct"] if s["return_30d_pct"] is not None else -999.0, s["conviction_score"]), reverse=True)
        elif sort_key == "signal_date":
            screened_stocks.sort(key=lambda s: (s.get("signal_date") or "1970-01-01", s["conviction_score"]), reverse=True)
        elif sort_key in ("return_since_signal", "return_signal", "signal_return"):
            screened_stocks.sort(key=lambda s: (s.get("return_since_signal_pct") if s.get("return_since_signal_pct") is not None else -999.0, s["conviction_score"]), reverse=True)
        elif sort_key in ("eps_growth", "eps_growth_yoy"):
            screened_stocks.sort(key=lambda s: (s.get("eps_growth_yoy") if s.get("eps_growth_yoy") is not None else -999.0, s["conviction_score"]), reverse=True)
        else:  # "score"
            screened_stocks.sort(key=lambda s: (s["conviction_score"], s["smart_money_cr"]), reverse=True)

        final_stocks = screened_stocks[:limit]

        # 10. Compute Macro Summary
        total_sm = round(sum(s["smart_money_cr"] for s in screened_stocks), 2)
        total_dom = round(sum(s["domestic_cr"] for s in screened_stocks), 2)
        avg_dom = round(sum(s["smart_money_dominance_pct"] for s in screened_stocks) / len(screened_stocks), 1) if screened_stocks else 0.0

        sector_sm: dict[str, float] = defaultdict(float)
        for s in screened_stocks:
            sector_sm[s["sector"]] += s["smart_money_cr"]
        top_sec = max(sector_sm.items(), key=lambda x: x[1])[0] if sector_sm else "Diversified"

        highest_inflow_ticker = screened_stocks[0]["ticker"] if screened_stocks else None

        result = {
            "success": True,
            "window": window,
            "window_label": window_label,
            "entity_focus": entity_focus,
            "min_cr": min_cr,
            "sort_by": sort_by,
            "emerging_only": emerging_only,
            "min_eps_growth": min_eps_growth,
            "new_entrants_only": new_entrants_only,
            "count": len(final_stocks),
            "total_screened": len(screened_stocks),
            "period_description": period_description,
            "time_period": {
                "from_date": start_date,
                "to_date": end_date,
                "quarter": canonical_q,
                "description": period_description,
            },
            "macro_summary": {
                "total_stocks": len(screened_stocks),
                "total_stocks_tracked": len(screened_stocks),
                "total_smart_money_cr": total_sm,
                "total_domestic_cr": total_dom,
                "total_domestic_absorption_cr": total_dom,
                "avg_dominance_pct": avg_dom,
                "avg_smart_money_dominance_pct": avg_dom,
                "top_sector": top_sec,
                "highest_inflow_ticker": highest_inflow_ticker,
                "total_fii_cr": round(sum(s["fii_cr"] for s in screened_stocks), 2),
                "total_super_inv_cr": round(sum(s["super_inv_cr"] for s in screened_stocks), 2),
                "total_block_deals_cr": round(sum(s["block_deals_cr"] for s in screened_stocks), 2),
                "total_emerging_stocks": sum(1 for s in screened_stocks if s.get("is_emerging")),
                "total_new_entrants": sum(1 for s in screened_stocks if s.get("is_new_entrant")),
                "total_high_eps_growth": sum(1 for s in screened_stocks if s.get("has_good_eps")),
            },
            "stocks": final_stocks,
        }

        _set_inst_cache(cache_key, result, ttl_seconds=120.0)
        return result

    except Exception as e:
        logger.exception("Error in get_stocks_under_institutional_accumulation: %s", e)
        return {
            "success": False,
            "detail": f"Error calculating accumulation: {str(e)}",
            "stocks": [],
            "macro_summary": {},
        }
