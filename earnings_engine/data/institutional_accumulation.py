"""Institutional Accumulation, Mutual Fund Portfolio Activity & Block Deals Engine.

Tracks institutional funds (Nippon India, Quant, HDFC, SBI, ICICI Pru, Parag Parikh, GQG,
Vanguard, BlackRock, Norway GPFG) and Super Investors (Ashish Kacholia, Mukul Agrawal, Vijay Kedia,
Dolly Khanna, Radhakishan Damani) accumulating, investing, trimming, or exiting equities.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)

# Curated institutional baseline dataset for key equities (seeded on initial launch)
SEEDED_INSTITUTIONAL_DATA: list[dict[str, Any]] = [
    # 1. ALLCARGO.NS (User Requested Highlight)
    {
        "ticker": "ALLCARGO.NS",
        "fund_name": "Nippon India Small Cap Fund",
        "fund_type": "Mutual Fund (DII)",
        "quarter": "Q3 FY25",
        "shares_held": 28450000,
        "stake_pct": 2.89,
        "prev_stake_pct": 1.44,
        "holding_value_cr": 223.3,
        "action": "ACCUMULATED",
        "change_shares": 14250000,
        "change_pct": 1.45,
        "reported_date": "2026-08-15",
    },
    {
        "ticker": "ALLCARGO.NS",
        "fund_name": "Quant Small Cap Fund",
        "fund_type": "Mutual Fund (DII)",
        "quarter": "Q3 FY25",
        "shares_held": 17800000,
        "stake_pct": 1.81,
        "prev_stake_pct": 0.0,
        "holding_value_cr": 139.7,
        "action": "NEW BUY",
        "change_shares": 17800000,
        "change_pct": 1.81,
        "reported_date": "2026-08-18",
    },
    {
        "ticker": "ALLCARGO.NS",
        "fund_name": "Ashish Kacholia",
        "fund_type": "Super Investor",
        "quarter": "Q3 FY25",
        "shares_held": 14200000,
        "stake_pct": 1.44,
        "prev_stake_pct": 0.69,
        "holding_value_cr": 111.5,
        "action": "ACCUMULATED",
        "change_shares": 7400000,
        "change_pct": 0.75,
        "reported_date": "2026-08-10",
    },
    {
        "ticker": "ALLCARGO.NS",
        "fund_name": "HDFC Flexi Cap Fund",
        "fund_type": "Mutual Fund (DII)",
        "quarter": "Q3 FY25",
        "shares_held": 8500000,
        "stake_pct": 0.86,
        "prev_stake_pct": 1.46,
        "holding_value_cr": 66.7,
        "action": "TRIMMED",
        "change_shares": -5900000,
        "change_pct": -0.60,
        "reported_date": "2026-08-12",
    },
    {
        "ticker": "ALLCARGO.NS",
        "fund_name": "Vanguard Emerging Markets Fund",
        "fund_type": "Foreign Institutional (FII)",
        "quarter": "Q3 FY25",
        "shares_held": 0,
        "stake_pct": 0.0,
        "prev_stake_pct": 1.15,
        "holding_value_cr": 0.0,
        "action": "SOLD OUT",
        "change_shares": -11300000,
        "change_pct": -1.15,
        "reported_date": "2026-08-05",
    },
    {
        "ticker": "ALLCARGO.NS",
        "fund_name": "Government Pension Fund Global (Norway)",
        "fund_type": "Foreign Sovereign / FII",
        "quarter": "Q3 FY25",
        "shares_held": 11500000,
        "stake_pct": 1.17,
        "prev_stake_pct": 0.77,
        "holding_value_cr": 90.3,
        "action": "ACCUMULATED",
        "change_shares": 3900000,
        "change_pct": 0.40,
        "reported_date": "2026-08-20",
    },

    # 2. TCS.NS
    {
        "ticker": "TCS.NS",
        "fund_name": "SBI Bluechip Fund",
        "fund_type": "Mutual Fund (DII)",
        "quarter": "Q3 FY25",
        "shares_held": 12500000,
        "stake_pct": 0.35,
        "prev_stake_pct": 0.28,
        "holding_value_cr": 5250.0,
        "action": "ACCUMULATED",
        "change_shares": 2500000,
        "change_pct": 0.07,
        "reported_date": "2026-08-14",
    },
    {
        "ticker": "TCS.NS",
        "fund_name": "GQG Partners Emerging Markets",
        "fund_type": "Foreign Institutional (FII)",
        "quarter": "Q3 FY25",
        "shares_held": 18200000,
        "stake_pct": 0.50,
        "prev_stake_pct": 0.0,
        "holding_value_cr": 7644.0,
        "action": "NEW BUY",
        "change_shares": 18200000,
        "change_pct": 0.50,
        "reported_date": "2026-08-16",
    },

    # 3. FORCEMOT.NS
    {
        "ticker": "FORCEMOT.NS",
        "fund_name": "Mukul Agrawal",
        "fund_type": "Super Investor",
        "quarter": "Q3 FY25",
        "shares_held": 580000,
        "stake_pct": 4.40,
        "prev_stake_pct": 3.20,
        "holding_value_cr": 493.0,
        "action": "ACCUMULATED",
        "change_shares": 158000,
        "change_pct": 1.20,
        "reported_date": "2026-08-11",
    },
    {
        "ticker": "FORCEMOT.NS",
        "fund_name": "DSP Midcap Fund",
        "fund_type": "Mutual Fund (DII)",
        "quarter": "Q3 FY25",
        "shares_held": 320000,
        "stake_pct": 2.43,
        "prev_stake_pct": 0.0,
        "holding_value_cr": 272.0,
        "action": "NEW BUY",
        "change_shares": 320000,
        "change_pct": 2.43,
        "reported_date": "2026-08-19",
    },

    # 4. PCJEWELLER.NS
    {
        "ticker": "PCJEWELLER.NS",
        "fund_name": "Quant Active Fund",
        "fund_type": "Mutual Fund (DII)",
        "quarter": "Q3 FY25",
        "shares_held": 11200000,
        "stake_pct": 2.41,
        "prev_stake_pct": 0.0,
        "holding_value_cr": 196.0,
        "action": "NEW BUY",
        "change_shares": 11200000,
        "change_pct": 2.41,
        "reported_date": "2026-08-22",
    },
    {
        "ticker": "PCJEWELLER.NS",
        "fund_name": "Dolly Khanna",
        "fund_type": "Super Investor",
        "quarter": "Q3 FY25",
        "shares_held": 5800000,
        "stake_pct": 1.25,
        "prev_stake_pct": 0.60,
        "holding_value_cr": 101.5,
        "action": "ACCUMULATED",
        "change_shares": 3010000,
        "change_pct": 0.65,
        "reported_date": "2026-08-17",
    },
]

SEEDED_BLOCK_DEALS: list[dict[str, Any]] = [
    {
        "deal_date": "2026-08-22",
        "ticker": "ALLCARGO.NS",
        "client_name": "NIPPON INDIA MUTUAL FUND",
        "deal_type": "BUY",
        "quantity": 2500000,
        "price": 78.50,
        "value_cr": 19.63,
        "pct_equity": 0.25,
        "exchange": "NSE",
    },
    {
        "deal_date": "2026-08-20",
        "ticker": "ALLCARGO.NS",
        "client_name": "NORGES BANK (NORWAY PENSION FUND)",
        "deal_type": "BUY",
        "quantity": 3900000,
        "price": 77.20,
        "value_cr": 30.11,
        "pct_equity": 0.40,
        "exchange": "NSE",
    },
    {
        "deal_date": "2026-08-18",
        "ticker": "ALLCARGO.NS",
        "client_name": "VANGUARD TOTAL INTL STOCK INDEX",
        "deal_type": "SELL",
        "quantity": 4200000,
        "price": 76.80,
        "value_cr": 32.26,
        "pct_equity": 0.43,
        "exchange": "NSE",
    },
    {
        "deal_date": "2026-08-21",
        "ticker": "TCS.NS",
        "client_name": "GQG PARTNERS EMERGING MARKETS EQUITY",
        "deal_type": "BUY",
        "quantity": 1200000,
        "price": 4210.00,
        "value_cr": 505.20,
        "pct_equity": 0.03,
        "exchange": "NSE",
    },
    {
        "deal_date": "2026-08-19",
        "ticker": "FORCEMOT.NS",
        "client_name": "MUKUL MAHAVIR AGRAWAL",
        "deal_type": "BUY",
        "quantity": 85000,
        "price": 8450.00,
        "value_cr": 71.83,
        "pct_equity": 0.65,
        "exchange": "NSE",
    },
    {
        "deal_date": "2026-08-24",
        "ticker": "PCJEWELLER.NS",
        "client_name": "QUANT MUTUAL FUND",
        "deal_type": "BUY",
        "quantity": 4500000,
        "price": 174.50,
        "value_cr": 78.53,
        "pct_equity": 0.97,
        "exchange": "NSE",
    },
]

SEEDED_SHAREHOLDING_PATTERNS: list[dict[str, Any]] = [
    {
        "ticker": "ALLCARGO.NS",
        "quarter": "Q3 FY25",
        "promoter_pct": 45.45,
        "fii_pct": 12.30,
        "dii_mf_pct": 16.85,
        "public_retail_pct": 25.40,
        "other_pct": 0.0,
    },
    {
        "ticker": "ALLCARGO.NS",
        "quarter": "Q2 FY25",
        "promoter_pct": 45.45,
        "fii_pct": 11.85,
        "dii_mf_pct": 14.60,
        "public_retail_pct": 28.10,
        "other_pct": 0.0,
    },
    {
        "ticker": "ALLCARGO.NS",
        "quarter": "Q1 FY25",
        "promoter_pct": 45.45,
        "fii_pct": 10.90,
        "dii_mf_pct": 13.20,
        "public_retail_pct": 30.45,
        "other_pct": 0.0,
    },
    {
        "ticker": "TCS.NS",
        "quarter": "Q3 FY25",
        "promoter_pct": 71.77,
        "fii_pct": 12.80,
        "dii_mf_pct": 10.45,
        "public_retail_pct": 4.98,
        "other_pct": 0.0,
    },
    {
        "ticker": "FORCEMOT.NS",
        "quarter": "Q3 FY25",
        "promoter_pct": 61.63,
        "fii_pct": 6.80,
        "dii_mf_pct": 9.45,
        "public_retail_pct": 22.12,
        "other_pct": 0.0,
    },
    {
        "ticker": "PCJEWELLER.NS",
        "quarter": "Q3 FY25",
        "promoter_pct": 54.54,
        "fii_pct": 4.20,
        "dii_mf_pct": 6.80,
        "public_retail_pct": 34.46,
        "other_pct": 0.0,
    },
]


def init_institutional_db(settings: Settings | None = None) -> None:
    """Seed sample institutional holdings, block deals, and shareholding patterns if empty."""
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        count = conn.execute("SELECT COUNT(*) FROM institutional_holdings").fetchone()[0]
        if count == 0:
            now_iso = datetime.now(timezone.utc).isoformat()
            # 1. Seed holdings
            for h in SEEDED_INSTITUTIONAL_DATA:
                conn.execute(
                    """
                    INSERT INTO institutional_holdings (
                        ticker, fund_name, fund_type, quarter,
                        shares_held, stake_pct, holding_value_cr,
                        prev_stake_pct, action, change_shares,
                        change_pct, reported_date, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        h["ticker"], h["fund_name"], h["fund_type"], h["quarter"],
                        h["shares_held"], h["stake_pct"], h["holding_value_cr"],
                        h["prev_stake_pct"], h["action"], h["change_shares"],
                        h["change_pct"], h["reported_date"], now_iso,
                    ),
                )

            # 2. Seed block deals
            for b in SEEDED_BLOCK_DEALS:
                conn.execute(
                    """
                    INSERT INTO institutional_block_deals (
                        deal_date, ticker, client_name, deal_type,
                        quantity, price, value_cr, pct_equity, exchange, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        b["deal_date"], b["ticker"], b["client_name"], b["deal_type"],
                        b["quantity"], b["price"], b["value_cr"], b["pct_equity"],
                        b["exchange"], now_iso,
                    ),
                )

            # 3. Seed shareholding patterns
            for p in SEEDED_SHAREHOLDING_PATTERNS:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO shareholding_patterns (
                        ticker, quarter, promoter_pct, fii_pct, dii_mf_pct,
                        public_retail_pct, other_pct, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p["ticker"], p["quarter"], p["promoter_pct"], p["fii_pct"],
                        p["dii_mf_pct"], p["public_retail_pct"], p["other_pct"], now_iso,
                    ),
                )

            if hasattr(conn, "commit"):
                conn.commit()
            logger.info("[INSTITUTIONAL] Seeded baseline institutional holding & block deal dataset.")
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Seeding error: %s", e)


def get_stock_institutional_activity(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve complete institutional accumulation breakdown for a specific equity."""
    settings = settings or Settings()
    init_institutional_db(settings)

    sym = (ticker or "").strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"

    try:
        conn = get_db_connection(settings)
        # 1. Fund holdings
        h_rows = conn.execute(
            """
            SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                   holding_value_cr, prev_stake_pct, action, change_shares, change_pct, reported_date
            FROM institutional_holdings
            WHERE ticker = ?
            ORDER BY stake_pct DESC, holding_value_cr DESC
            """,
            (sym,),
        ).fetchall()

        holdings: list[dict[str, Any]] = []
        accumulating_count = 0
        selling_count = 0
        new_buys_count = 0
        net_inflow_cr = 0.0

        for r in h_rows:
            d = {
                "id": r[0],
                "ticker": r[1],
                "fund_name": r[2],
                "fund_type": r[3],
                "quarter": r[4],
                "shares_held": r[5],
                "stake_pct": round(float(r[6] or 0.0), 2),
                "holding_value_cr": round(float(r[7] or 0.0), 1),
                "prev_stake_pct": round(float(r[8] or 0.0), 2),
                "action": (r[9] or "HOLD").upper(),
                "change_shares": r[10] or 0,
                "change_pct": round(float(r[11] or 0.0), 2),
                "reported_date": r[12],
            }
            act = d["action"]
            if act in ("NEW BUY", "ACCUMULATED"):
                accumulating_count += 1
                if act == "NEW BUY":
                    new_buys_count += 1
                net_inflow_cr += max(0, d["holding_value_cr"] * (d["change_pct"] / max(0.01, d["stake_pct"])))
            elif act in ("TRIMMED", "SOLD OUT"):
                selling_count += 1
                net_inflow_cr -= max(0, abs(d["change_pct"]) * 50.0)

            holdings.append(d)

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

        # 3. Shareholding pattern history
        p_rows = conn.execute(
            """
            SELECT quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct
            FROM shareholding_patterns
            WHERE ticker = ?
            ORDER BY quarter DESC LIMIT 4
            """,
            (sym,),
        ).fetchall()

        patterns: list[dict[str, Any]] = []
        for p in p_rows:
            patterns.append({
                "quarter": p[0],
                "promoter_pct": round(float(p[1]), 2),
                "fii_pct": round(float(p[2]), 2),
                "dii_mf_pct": round(float(p[3]), 2),
                "public_retail_pct": round(float(p[4]), 2),
                "other_pct": round(float(p[5]), 2),
            })

        # Derive institutional accumulation conviction score (0-100)
        score = 50.0
        if accumulating_count > selling_count:
            score += min(35.0, (accumulating_count - selling_count) * 12.0 + new_buys_count * 5.0)
        elif selling_count > accumulating_count:
            score -= min(35.0, (selling_count - accumulating_count) * 12.0)

        # Delta from shareholding pattern
        if len(patterns) >= 2:
            fii_delta = patterns[0]["fii_pct"] - patterns[1]["fii_pct"]
            dii_delta = patterns[0]["dii_mf_pct"] - patterns[1]["dii_mf_pct"]
            score += min(15.0, max(-15.0, (fii_delta + dii_delta) * 5.0))

        score = max(5.0, min(98.0, round(score, 1)))

        if score >= 75.0:
            verdict = "🔥 Aggressive Institutional Accumulation"
            verdict_badge = "emerald"
        elif score >= 58.0:
            verdict = "🟢 Moderate Institutional Buying"
            verdict_badge = "green"
        elif score >= 42.0:
            verdict = "⚖️ Stable Institutional Allocation"
            verdict_badge = "amber"
        else:
            verdict = "🔴 Institutional Distribution / Trimming"
            verdict_badge = "rose"

        # Company name lookup
        from earnings_engine.data.names import get_name
        company_name = get_name(sym) or sym.replace(".NS", "")

        return {
            "success": True,
            "ticker": sym,
            "company_name": company_name,
            "accumulation_score": score,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "funds_accumulating_count": accumulating_count,
            "funds_selling_count": selling_count,
            "new_funds_bought_count": new_buys_count,
            "net_flow_cr": round(net_inflow_cr, 1),
            "holdings": holdings,
            "block_deals": deals,
            "shareholding_patterns": patterns,
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


def get_top_accumulated_stocks(
    universe: str | None = None,
    min_score: float = 60.0,
    limit: int = 25,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve high-conviction equities experiencing active institutional fund accumulation."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        # Find distinct tickers in holdings
        t_rows = conn.execute("SELECT DISTINCT ticker FROM institutional_holdings").fetchall()
        tickers = [r[0] for r in t_rows if r[0]]

        results: list[dict[str, Any]] = []
        for t in tickers:
            act = get_stock_institutional_activity(t, settings=settings)
            if act.get("success") and act.get("accumulation_score", 0) >= min_score:
                results.append({
                    "ticker": act["ticker"],
                    "company_name": act["company_name"],
                    "accumulation_score": act["accumulation_score"],
                    "verdict": act["verdict"],
                    "verdict_badge": act["verdict_badge"],
                    "funds_accumulating_count": act["funds_accumulating_count"],
                    "funds_selling_count": act["funds_selling_count"],
                    "new_funds_bought_count": act["new_funds_bought_count"],
                    "net_flow_cr": act["net_flow_cr"],
                    "top_funds": [h["fund_name"] for h in act["holdings"] if h["action"] in ("NEW BUY", "ACCUMULATED")][:3],
                    "total_institutional_stake": round(sum(h["stake_pct"] for h in act["holdings"]), 2),
                })

        results.sort(key=lambda x: x["accumulation_score"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Top accumulated error: %s", e)
        return []


def get_top_distributed_stocks(
    limit: int = 20,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve equities where institutional funds are actively trimming or liquidating positions."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        t_rows = conn.execute("SELECT DISTINCT ticker FROM institutional_holdings").fetchall()
        tickers = [r[0] for r in t_rows if r[0]]

        results: list[dict[str, Any]] = []
        for t in tickers:
            act = get_stock_institutional_activity(t, settings=settings)
            if act.get("success") and act.get("funds_selling_count", 0) > 0:
                results.append({
                    "ticker": act["ticker"],
                    "company_name": act["company_name"],
                    "accumulation_score": act["accumulation_score"],
                    "verdict": act["verdict"],
                    "verdict_badge": act["verdict_badge"],
                    "funds_selling_count": act["funds_selling_count"],
                    "exiting_funds": [h["fund_name"] for h in act["holdings"] if h["action"] in ("TRIMMED", "SOLD OUT")],
                    "net_flow_cr": act["net_flow_cr"],
                })

        results.sort(key=lambda x: x["funds_selling_count"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Top distributed error: %s", e)
        return []


def get_all_funds_activity(limit: int = 50, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve distinct list of active institutional funds with their latest actions."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            """
            SELECT fund_name, fund_type, COUNT(DISTINCT ticker) as total_positions,
                   SUM(CASE WHEN action IN ('NEW BUY', 'ACCUMULATED') THEN 1 ELSE 0 END) as buying_actions,
                   SUM(CASE WHEN action IN ('TRIMMED', 'SOLD OUT') THEN 1 ELSE 0 END) as selling_actions,
                   SUM(holding_value_cr) as total_aum_tracked_cr
            FROM institutional_holdings
            GROUP BY fund_name, fund_type
            ORDER BY total_positions DESC, buying_actions DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        funds: list[dict[str, Any]] = []
        for r in rows:
            funds.append({
                "fund_name": r[0],
                "fund_type": r[1],
                "total_positions": r[2],
                "buying_actions": r[3],
                "selling_actions": r[4],
                "total_aum_tracked_cr": round(float(r[5] or 0.0), 1),
            })
        return funds
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Funds list error: %s", e)
        return []


def get_fund_portfolio_activity(fund_name: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Reverse lookup: retrieve all equities held and recent actions for a specific fund."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            """
            SELECT ticker, quarter, shares_held, stake_pct, holding_value_cr,
                   action, change_pct, reported_date
            FROM institutional_holdings
            WHERE LOWER(fund_name) = LOWER(?)
            ORDER BY stake_pct DESC
            """,
            (fund_name.strip(),),
        ).fetchall()

        holdings: list[dict[str, Any]] = []
        for r in rows:
            holdings.append({
                "ticker": r[0],
                "quarter": r[1],
                "shares_held": r[2],
                "stake_pct": round(float(r[3] or 0.0), 2),
                "holding_value_cr": round(float(r[4] or 0.0), 1),
                "action": r[5],
                "change_pct": round(float(r[6] or 0.0), 2),
                "reported_date": r[7],
            })
        return holdings
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Fund portfolio error for %s: %s", fund_name, e)
        return []
