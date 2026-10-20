"""Industry-Benchmarked Fundamental & Technical Stock Rating Engine.

Evaluates stocks on:
1. Industry-Relative Fundamental Multiples: P/E, EV/EBITDA, P/B, ROE, ROCE, Debt/Equity, Margins.
2. Technical Momentum & Structure: VWAP position, Volume Surge, Support/Resistance, News Sentiment.
3. Automated AI Synthesis Notes.
4. On-Demand Recalculation, Snapshot Diffing, and Audit Trail Persistence.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.stock_rating")

# ---------------------------------------------------------------------------
# Industry Benchmark Multiples Repository (Standardized Sector Medians)
# ---------------------------------------------------------------------------
INDUSTRY_BENCHMARKS: dict[str, dict[str, float]] = {
    "IT Services & Tech": {
        "pe": 26.5,
        "ev_ebitda": 17.5,
        "pb": 5.5,
        "roe": 22.0,
        "debt_to_equity": 0.15,
        "operating_margin": 20.0,
    },
    "Banking & Financial Services": {
        "pe": 16.0,
        "ev_ebitda": 12.0,
        "pb": 2.2,
        "roe": 15.0,
        "debt_to_equity": 1.5,
        "operating_margin": 24.0,
    },
    "Automotive & Ancillaries": {
        "pe": 22.0,
        "ev_ebitda": 12.5,
        "pb": 3.8,
        "roe": 16.5,
        "debt_to_equity": 0.45,
        "operating_margin": 12.0,
    },
    "Pharmaceuticals & Healthcare": {
        "pe": 29.0,
        "ev_ebitda": 18.0,
        "pb": 4.5,
        "roe": 15.5,
        "debt_to_equity": 0.35,
        "operating_margin": 18.5,
    },
    "FMCG & Consumer Goods": {
        "pe": 44.0,
        "ev_ebitda": 27.0,
        "pb": 8.5,
        "roe": 25.0,
        "debt_to_equity": 0.20,
        "operating_margin": 16.5,
    },
    "Oil, Gas & Energy": {
        "pe": 12.5,
        "ev_ebitda": 7.5,
        "pb": 1.6,
        "roe": 14.0,
        "debt_to_equity": 0.65,
        "operating_margin": 13.0,
    },
    "Metals & Mining": {
        "pe": 11.0,
        "ev_ebitda": 6.5,
        "pb": 1.5,
        "roe": 14.5,
        "debt_to_equity": 0.55,
        "operating_margin": 15.0,
    },
    "Infrastructure & Capital Goods": {
        "pe": 32.0,
        "ev_ebitda": 18.5,
        "pb": 4.0,
        "roe": 14.0,
        "debt_to_equity": 0.40,
        "operating_margin": 10.5,
    },
    "Chemicals & Materials": {
        "pe": 25.0,
        "ev_ebitda": 14.5,
        "pb": 3.2,
        "roe": 16.0,
        "debt_to_equity": 0.30,
        "operating_margin": 15.0,
    },
    "Telecommunication": {
        "pe": 24.0,
        "ev_ebitda": 8.5,
        "pb": 2.8,
        "roe": 11.0,
        "debt_to_equity": 1.20,
        "operating_margin": 21.0,
    },
    "Real Estate & Construction": {
        "pe": 28.0,
        "ev_ebitda": 16.0,
        "pb": 2.6,
        "roe": 10.5,
        "debt_to_equity": 0.75,
        "operating_margin": 17.0,
    },
    "General / Multi-Sector": {
        "pe": 22.0,
        "ev_ebitda": 14.0,
        "pb": 3.0,
        "roe": 15.0,
        "debt_to_equity": 0.50,
        "operating_margin": 14.0,
    },
}


def match_industry_benchmark(industry_str: str | None) -> tuple[str, dict[str, float]]:
    """Match a raw industry/sector string to the closest benchmark profile."""
    if not industry_str:
        return "General / Multi-Sector", INDUSTRY_BENCHMARKS["General / Multi-Sector"]

    ind_lower = industry_str.lower()
    if any(k in ind_lower for k in ["software", "tech", "information technology", "it services", "internet", "electronics", "semiconductor", "computer", "hardware", "education", "training", "business services"]):
        return "IT Services & Tech", INDUSTRY_BENCHMARKS["IT Services & Tech"]
    if any(k in ind_lower for k in ["bank", "financial", "insurance", "nbfc", "capital market", "fintech", "asset management", "wealth", "broking", "depository", "exchange", "microfinance", "mortgage"]):
        return "Banking & Financial Services", INDUSTRY_BENCHMARKS["Banking & Financial Services"]
    if any(k in ind_lower for k in ["auto", "vehicle", "motor", "tyre", "truck", "ancillaries", "automobile"]):
        return "Automotive & Ancillaries", INDUSTRY_BENCHMARKS["Automotive & Ancillaries"]
    if any(k in ind_lower for k in ["pharma", "health", "biotech", "drug", "hospital", "clinic", "medical", "diagnostic", "laboratory", "lifesciences"]):
        return "Pharmaceuticals & Healthcare", INDUSTRY_BENCHMARKS["Pharmaceuticals & Healthcare"]
    if any(k in ind_lower for k in ["fmcg", "consumer", "food", "beverage", "personal", "tobacco", "retail", "textile", "apparel", "garment", "clothing", "footwear", "lodging", "hotel", "resort", "restaurant", "travel", "entertainment", "media", "broadcasting", "gaming", "confection", "farm product", "luxury", "publishing"]):
        return "FMCG & Consumer Goods", INDUSTRY_BENCHMARKS["FMCG & Consumer Goods"]
    if any(k in ind_lower for k in ["oil", "gas", "energy", "petroleum", "power", "utility", "solar", "renewable", "green", "clean", "thermal", "hydro", "electric"]):
        return "Oil, Gas & Energy", INDUSTRY_BENCHMARKS["Oil, Gas & Energy"]
    if any(k in ind_lower for k in ["metal", "steel", "mining", "aluminum", "copper", "iron", "mineral", "zinc", "gold"]):
        return "Metals & Mining", INDUSTRY_BENCHMARKS["Metals & Mining"]
    if any(k in ind_lower for k in ["infra", "capital good", "engineering", "machinery", "defense", "railway", "electrical equipment", "aerospace", "freight", "logistics", "shipping", "transport", "ports", "tools", "business equipment", "wood", "lumber"]):
        return "Infrastructure & Capital Goods", INDUSTRY_BENCHMARKS["Infrastructure & Capital Goods"]
    if any(k in ind_lower for k in ["chemical", "fertilizer", "specialty chemical", "pesticide", "agricultural input", "agri", "packaging", "paper", "plastic", "container", "rubber"]):
        return "Chemicals & Materials", INDUSTRY_BENCHMARKS["Chemicals & Materials"]
    if any(k in ind_lower for k in ["telecom", "wireless", "broadband", "satellite", "network", "communication equipment"]):
        return "Telecommunication", INDUSTRY_BENCHMARKS["Telecommunication"]
    if any(k in ind_lower for k in ["realty", "real estate", "construction", "housing", "cement", "building", "fixture", "furnishing", "appliance", "tile", "sanitaryware", "paint", "glass", "plywood"]):
        return "Real Estate & Construction", INDUSTRY_BENCHMARKS["Real Estate & Construction"]

    return "General / Multi-Sector", INDUSTRY_BENCHMARKS["General / Multi-Sector"]


# ---------------------------------------------------------------------------
# Database Tables Initialization
# ---------------------------------------------------------------------------
_INITIALIZED_RATING_DBS: set[str] = set()


def ensure_stock_rating_schema(settings: Settings) -> None:
    """Ensure tables exist for stock ratings, snapshots, and recalculation logs."""
    db_key = str(settings.data_dirs.get("prices", ""))
    if db_key in _INITIALIZED_RATING_DBS:
        return
    conn = get_db_connection(settings)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_ratings (
                    ticker TEXT PRIMARY KEY,
                    industry TEXT,
                    matched_benchmark TEXT,
                    fundamental_score REAL,
                    fundamental_grade TEXT,
                    technical_score REAL,
                    technical_grade TEXT,
                    composite_score REAL,
                    composite_grade TEXT,
                    metrics_json TEXT,
                    technical_json TEXT,
                    ai_note TEXT,
                    last_updated TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_rating_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT,
                    fundamental_score REAL,
                    fundamental_grade TEXT,
                    technical_score REAL,
                    technical_grade TEXT,
                    metrics_json TEXT,
                    ai_note TEXT,
                    source TEXT,
                    created_at TEXT
                )
                """
            )
        _INITIALIZED_RATING_DBS.add(db_key)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Fundamental Evaluator
# ---------------------------------------------------------------------------
def evaluate_fundamental_rating(
    ticker: str,
    financials: dict[str, Any],
    industry: str | None = None,
) -> dict[str, Any]:
    """Evaluate fundamental health, valuation, and quality against sector benchmarks."""
    sector_name, benchmark = match_industry_benchmark(industry)

    pe = financials.get("pe") or financials.get("trailingPE") or financials.get("forwardPE")
    pb = financials.get("pb") or financials.get("priceToBook")
    ev_ebitda = financials.get("ev_ebitda") or financials.get("enterpriseToEbitda")
    roe = financials.get("roe") or financials.get("returnOnEquity")
    debt_to_equity = financials.get("debt_to_equity") or financials.get("debtToEquity")
    operating_margin = financials.get("operating_margin") or financials.get("operatingMargins")
    eps_surprise = financials.get("surprise_pct") or 0.0

    # Normalization: yfinance returns ROE & margins as decimals (0.15 = 15%) or whole numbers
    if roe is not None and abs(float(roe)) <= 1.0:
        roe = float(roe) * 100.0
    if operating_margin is not None and abs(float(operating_margin)) <= 1.0:
        operating_margin = float(operating_margin) * 100.0
    if debt_to_equity is not None and float(debt_to_equity) > 10.0:
        debt_to_equity = float(debt_to_equity) / 100.0  # e.g. 85.0 -> 0.85

    score = 50.0  # Base neutral score
    metrics_summary: dict[str, Any] = {
        "sector": sector_name,
        "pe": pe,
        "benchmark_pe": benchmark["pe"],
        "pb": pb,
        "benchmark_pb": benchmark["pb"],
        "ev_ebitda": ev_ebitda,
        "benchmark_ev_ebitda": benchmark["ev_ebitda"],
        "roe": roe,
        "benchmark_roe": benchmark["roe"],
        "debt_to_equity": debt_to_equity,
        "benchmark_debt_to_equity": benchmark["debt_to_equity"],
        "operating_margin": operating_margin,
        "benchmark_operating_margin": benchmark["operating_margin"],
        "eps_surprise": eps_surprise,
    }

    # 1. P/E relative to benchmark (weight: 25)
    if pe is not None and float(pe) > 0:
        pe_val = float(pe)
        b_pe = benchmark["pe"]
        discount_pct = (b_pe - pe_val) / b_pe * 100.0
        metrics_summary["pe_discount_pct"] = round(discount_pct, 1)
        if discount_pct > 25.0:
            score += 15.0
        elif discount_pct > 0.0:
            score += 8.0
        elif discount_pct > -25.0:
            score -= 5.0
        else:
            score -= 12.0

    # 2. ROE relative to benchmark (weight: 25)
    if roe is not None:
        roe_val = float(roe)
        b_roe = benchmark["roe"]
        roe_spread = roe_val - b_roe
        metrics_summary["roe_spread"] = round(roe_spread, 1)
        if roe_spread > 5.0:
            score += 15.0
        elif roe_spread >= 0.0:
            score += 7.0
        elif roe_spread > -5.0:
            score -= 5.0
        else:
            score -= 12.0

    # 3. Debt to Equity (weight: 20)
    if debt_to_equity is not None:
        de_val = float(debt_to_equity)
        metrics_summary["debt_to_equity_val"] = round(de_val, 2)
        if de_val < 0.25:
            score += 12.0  # Virtually debt-free
        elif de_val <= 0.75:
            score += 5.0   # Healthy leverage
        elif de_val <= 1.5:
            score -= 5.0   # Moderate leverage
        else:
            score -= 12.0  # High debt burden

    # 4. Operating Margins (weight: 15)
    if operating_margin is not None:
        m_val = float(operating_margin)
        b_m = benchmark["operating_margin"]
        m_spread = m_val - b_m
        if m_spread > 3.0:
            score += 8.0
        elif m_spread >= 0.0:
            score += 4.0
        else:
            score -= 4.0

    # 5. EPS Surprise / Consistency (weight: 15)
    if eps_surprise is not None:
        s_val = float(eps_surprise)
        if s_val > 5.0:
            score += 8.0
        elif s_val > 0.0:
            score += 4.0
        elif s_val < -5.0:
            score -= 6.0

    score = max(5.0, min(95.0, score))

    if score >= 68.0:
        grade = "GOOD"
    elif score >= 45.0:
        grade = "FAIR"
    else:
        grade = "POOR"

    return {
        "score": round(score, 1),
        "grade": grade,
        "sector": sector_name,
        "metrics": metrics_summary,
    }


# ---------------------------------------------------------------------------
# Technical Evaluator
# ---------------------------------------------------------------------------
def evaluate_technical_rating(
    ticker: str,
    price: float | None,
    vwap: float | None = None,
    volume_surge: float | None = None,
    support: float | None = None,
    resistance: float | None = None,
    thirty_day_return: float | None = None,
    news_sentiment: str | None = None,
) -> dict[str, Any]:
    """Evaluate technical indicators, VWAP position, volume expansion, and catalysts."""
    score = 50.0
    tech_metrics: dict[str, Any] = {
        "price": price,
        "vwap": vwap,
        "volume_surge": volume_surge,
        "support": support,
        "resistance": resistance,
        "thirty_day_return": thirty_day_return,
        "news_sentiment": news_sentiment,
    }

    # 1. VWAP Proximity (Weight: 25)
    if price and vwap and vwap > 0:
        vwap_diff_pct = (price - vwap) / vwap * 100.0
        tech_metrics["vwap_diff_pct"] = round(vwap_diff_pct, 2)
        if 0.0 <= vwap_diff_pct <= 3.5:
            score += 15.0  # Ideal pullback hold above VWAP
        elif vwap_diff_pct > 3.5:
            score += 8.0   # Strong bullish trend
        elif -3.0 <= vwap_diff_pct < 0.0:
            score += 2.0   # Testing VWAP support from below
        else:
            score -= 12.0  # Trapped below VWAP

    # 2. Volume Expansion (Weight: 25)
    if volume_surge is not None:
        v_val = float(volume_surge)
        if v_val >= 2.0:
            score += 15.0  # Institutional volume breakout
        elif v_val >= 1.2:
            score += 8.0   # Above average participation
        elif v_val < 0.6:
            score -= 8.0   # Low liquidity / lack of interest

    # 3. Proximity to Support / Resistance (Weight: 25)
    if price and support and resistance and resistance > support:
        range_span = resistance - support
        pos_in_range = (price - support) / range_span
        tech_metrics["pos_in_range"] = round(pos_in_range, 2)
        if 0.0 <= pos_in_range <= 0.35:
            score += 12.0  # In Buy Zone near support
        elif 0.35 < pos_in_range <= 0.75:
            score += 5.0   # Mid-range momentum
        elif pos_in_range > 0.75:
            score -= 5.0   # Approaching overhead resistance

    # 4. News & Catalyst Sentiment (Weight: 25)
    if news_sentiment:
        s_upper = news_sentiment.upper()
        if "BULL" in s_upper or "POSITIVE" in s_upper:
            score += 10.0
        elif "BEAR" in s_upper or "NEGATIVE" in s_upper:
            score -= 10.0

    score = max(5.0, min(95.0, score))

    if score >= 75.0:
        grade = "STRONG BUY"
    elif score >= 58.0:
        grade = "BUY"
    elif score >= 42.0:
        grade = "NEUTRAL"
    else:
        grade = "AVOID"

    return {
        "score": round(score, 1),
        "grade": grade,
        "metrics": tech_metrics,
    }


# ---------------------------------------------------------------------------
# AI Note Generator
# ---------------------------------------------------------------------------
def generate_stock_ai_note(
    ticker: str,
    fund_res: dict[str, Any],
    tech_res: dict[str, Any],
) -> str:
    """Synthesize a concise, high-signal institutional note for the stock."""
    f_grade = fund_res.get("grade", "NEUTRAL")
    f_score = fund_res.get("score", 50.0)
    t_grade = tech_res.get("grade", "NEUTRAL")
    sector = fund_res.get("sector", "General")
    m = fund_res.get("metrics", {})
    t = tech_res.get("metrics", {})

    parts = []

    # Valuation & Fundamental Clause
    pe = m.get("pe")
    b_pe = m.get("benchmark_pe")
    roe = m.get("roe")
    de = m.get("debt_to_equity")

    if pe and b_pe:
        disc = m.get("pe_discount_pct", 0)
        if disc > 0:
            parts.append(f"Trades at an attractive {pe:.1f}x P/E ({disc:+.1f}% vs {sector} median of {b_pe:.1f}x)")
        else:
            parts.append(f"Valuation at {pe:.1f}x P/E reflects a premium over the {sector} median of {b_pe:.1f}x")
    elif roe:
        parts.append(f"Delivers {roe:.1f}% ROE in the {sector} sector")

    if de is not None and de < 0.3:
        parts.append("bolstered by a pristine debt-free balance sheet")
    elif de is not None and de > 1.2:
        parts.append(f"tempered by elevated leverage (D/E {de:.2f}x)")

    # Technical Clause
    vwap_diff = t.get("vwap_diff_pct")
    vol = t.get("volume_surge")

    tech_clause = ""
    if vwap_diff is not None:
        if vwap_diff > 0:
            tech_clause = f"Technically constructive holding {vwap_diff:+.1f}% above VWAP"
        else:
            tech_clause = f"Technically lagging {vwap_diff:+.1f}% below VWAP"
    
    if vol and vol >= 1.5:
        tech_clause += f" on {vol:.1f}x volume surge"

    if tech_clause:
        parts.append(tech_clause)

    full_note = ". ".join(parts) + "."
    return full_note


# ---------------------------------------------------------------------------
# Recalculation, Snapshot, and Diff Engine
# ---------------------------------------------------------------------------
def recalculate_stock_rating(
    ticker: str,
    settings: Settings,
    source: str = "manual_recalc",
) -> dict[str, Any]:
    """Fetch live data, recalculate fundamental/technical ratings, record snapshot diff, and log audit."""
    ensure_stock_rating_schema(settings)
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Fetch previous snapshot for diffing
    prev_snapshot: dict[str, Any] | None = None
    conn = get_db_connection(settings)
    try:
        row = conn.execute(
            """
            SELECT fundamental_score, fundamental_grade, technical_score, technical_grade, metrics_json, ai_note, last_updated
            FROM stock_ratings WHERE ticker = ?
            """,
            (ticker,),
        ).fetchone()
        if row:
            prev_snapshot = {
                "fundamental_score": row[0],
                "fundamental_grade": row[1],
                "technical_score": row[2],
                "technical_grade": row[3],
                "metrics": json.loads(row[4]) if row[4] else {},
                "ai_note": row[5],
                "last_updated": row[6],
            }
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # 2. Fetch fresh live data from yfinance & DB with local fallback
    info: dict[str, Any] = {}
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("yfinance")
        except Exception:
            pass
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
    except Exception as e:
        logger.warning(f"Error fetching live info for {ticker}: {e}")

    # Fallback to local DB if yfinance was rate-limited or failed
    if not info or not any(k in info for k in ("trailingPE", "priceToBook", "debtToEquity", "operatingMargins")):
        conn_fb = get_db_connection(settings)
        try:
            t_row = conn_fb.execute(
                "SELECT metrics, sector, industry FROM tickers WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            if t_row and t_row[0]:
                try:
                    cached_m = json.loads(t_row[0])
                    if isinstance(cached_m, dict):
                        for k, v in cached_m.items():
                            if k not in info and v is not None:
                                info[k] = v
                except Exception:
                    pass
            if t_row and len(t_row) > 1 and t_row[1] and "sector" not in info:
                info["sector"] = t_row[1]
            if t_row and len(t_row) > 2 and t_row[2] and "industry" not in info:
                info["industry"] = t_row[2]
        except Exception as ex:
            logger.debug(f"DB fallback query failed for {ticker}: {ex}")
        finally:
            try:
                conn_fb.close()
            except Exception:
                pass

    # Load industry
    from earnings_engine.data.industry import load_industry
    ind = load_industry(ticker, settings) or info.get("industry") or info.get("sector")

    # Evaluate Fundamental
    fund_res = evaluate_fundamental_rating(ticker, info, ind)

    # Compute VWAP & Technicals from local price history first, then yfinance
    hist = pd.DataFrame()
    try:
        from earnings_engine.data.prices import load_prices
        hist = load_prices(ticker, settings)
        if hist.empty or len(hist) < 5:
            hist = yf_ticker.history(period="1mo")
    except Exception:
        pass

    vwap = None
    vol_surge = None
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")

    if not hist.empty:
        c_col = "close" if "close" in hist.columns else ("Close" if "Close" in hist.columns else None)
        v_col = "volume" if "volume" in hist.columns else ("Volume" if "Volume" in hist.columns else None)
        if c_col:
            if current_price is None:
                current_price = float(hist[c_col].dropna().iloc[-1])
            if v_col and hist[v_col].sum() > 0:
                vwap = float((hist[c_col] * hist[v_col]).sum() / hist[v_col].sum())
                avg_vol = float(hist[v_col].mean())
                last_vol = float(hist[v_col].dropna().iloc[-1])
                if avg_vol > 0:
                    vol_surge = round(last_vol / avg_vol, 2)

    # If ticker has no market or fundamental data whatsoever, do not persist placeholder ratings
    if not info and hist.empty and current_price is None:
        logger.warning("No market or fundamental data available for %s; skipping rating persistence.", ticker)
        return {
            "success": False,
            "error": f"No market or fundamental data available for {ticker}",
            "ticker": ticker,
        }

    tech_res = evaluate_technical_rating(
        ticker=ticker,
        price=current_price,
        vwap=vwap,
        volume_surge=vol_surge,
        thirty_day_return=info.get("fiftyTwoWeekChange"),
    )

    # Generate AI Note
    ai_note = generate_stock_ai_note(ticker, fund_res, tech_res)
    comp_score = round(fund_res["score"] * 0.5 + tech_res["score"] * 0.5, 1)
    comp_grade = "GOOD" if comp_score >= 65 else ("FAIR" if comp_score >= 45 else "POOR")

    # 3. Compute Delta Diff
    diff: dict[str, Any] = {}
    if prev_snapshot:
        p_f_score = prev_snapshot["fundamental_score"] or 50.0
        p_t_score = prev_snapshot["technical_score"] or 50.0
        diff = {
            "has_previous": True,
            "previous_updated": prev_snapshot["last_updated"],
            "fundamental_score_diff": round(fund_res["score"] - p_f_score, 1),
            "fundamental_grade_changed": prev_snapshot["fundamental_grade"] != fund_res["grade"],
            "prev_fundamental_grade": prev_snapshot["fundamental_grade"],
            "technical_score_diff": round(tech_res["score"] - p_t_score, 1),
            "technical_grade_changed": prev_snapshot["technical_grade"] != tech_res["grade"],
            "prev_technical_grade": prev_snapshot["technical_grade"],
            "previous_note": prev_snapshot["ai_note"],
        }
    else:
        diff = {
            "has_previous": False,
            "fundamental_score_diff": 0.0,
            "technical_score_diff": 0.0,
        }

    # 4. Save to Database with write retry on lock
    max_retries = 5
    backoff = 0.5
    for attempt in range(max_retries):
        conn_w = get_db_connection(settings)
        try:
            with conn_w:
                conn_w.execute(
                    """
                    INSERT INTO stock_ratings (
                        ticker, industry, matched_benchmark, fundamental_score, fundamental_grade,
                        technical_score, technical_grade, composite_score, composite_grade,
                        metrics_json, technical_json, ai_note, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                        industry = excluded.industry,
                        matched_benchmark = excluded.matched_benchmark,
                        fundamental_score = excluded.fundamental_score,
                        fundamental_grade = excluded.fundamental_grade,
                        technical_score = excluded.technical_score,
                        technical_grade = excluded.technical_grade,
                        composite_score = excluded.composite_score,
                        composite_grade = excluded.composite_grade,
                        metrics_json = excluded.metrics_json,
                        technical_json = excluded.technical_json,
                        ai_note = excluded.ai_note,
                        last_updated = excluded.last_updated
                    """,
                    (
                        ticker,
                        ind,
                        fund_res["sector"],
                        fund_res["score"],
                        fund_res["grade"],
                        tech_res["score"],
                        tech_res["grade"],
                        comp_score,
                        comp_grade,
                        json.dumps(fund_res["metrics"]),
                        json.dumps(tech_res["metrics"]),
                        ai_note,
                        now_str,
                    ),
                )
                conn_w.execute(
                    """
                    INSERT INTO stock_rating_snapshots (
                        ticker, fundamental_score, fundamental_grade, technical_score,
                        technical_grade, metrics_json, ai_note, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticker,
                        fund_res["score"],
                        fund_res["grade"],
                        tech_res["score"],
                        tech_res["grade"],
                        json.dumps(fund_res["metrics"]),
                        ai_note,
                        source,
                        now_str,
                    ),
                )
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                logger.warning(
                    "Database locked in recalculate_stock_rating for %s (attempt %d/%d), retrying in %.1fs...",
                    ticker,
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            raise
        finally:
            try:
                conn_w.close()
            except Exception:
                pass

    return {
        "ticker": ticker,
        "fundamental": fund_res,
        "technical": tech_res,
        "composite": {
            "score": comp_score,
            "grade": comp_grade,
        },
        "ai_note": ai_note,
        "diff": diff,
        "timestamp": now_str,
    }


def get_stock_rating(ticker: str, settings: Settings) -> dict[str, Any] | None:
    """Retrieve the cached rating for a ticker, or None if not computed."""
    ensure_stock_rating_schema(settings)
    conn = get_db_connection(settings)
    try:
        row = conn.execute(
            """
            SELECT industry, matched_benchmark, fundamental_score, fundamental_grade,
                   technical_score, technical_grade, composite_score, composite_grade,
                   metrics_json, technical_json, ai_note, last_updated
            FROM stock_ratings WHERE ticker = ?
            """,
            (ticker,),
        ).fetchone()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not row:
        return None

    return {
        "ticker": ticker,
        "industry": row[0],
        "sector": row[1],
        "fundamental": {
            "score": row[2],
            "grade": row[3],
            "metrics": json.loads(row[8]) if row[8] else {},
        },
        "technical": {
            "score": row[4],
            "grade": row[5],
            "metrics": json.loads(row[9]) if row[9] else {},
        },
        "composite": {
            "score": row[6],
            "grade": row[7],
        },
        "ai_note": row[10],
        "last_updated": row[11],
    }
