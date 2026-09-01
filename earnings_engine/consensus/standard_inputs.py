"""Standardized Model Input & Factor Evaluation Engine.

Provides a unified, canonical Point-in-Time (PIT) context payload and LLM prompt
generator for all predictive models (Multi-Model AI Consensus, LightGBM, Kronos AI,
and Stock Intelligence Notes).

Includes:
1. Standardized 6-Pillar Factor Weight Model (Total: 100%)
2. Detailed Relevance & Scope of Improvement Review per factor
3. Automated Real-Time Market Sentiment & Macro Regime Data Injection
4. Strict Point-in-Time (PIT) data compliance
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.prices import fetch_live_quote, load_prices
from earnings_engine.data.market_context import detect_swing_range
from earnings_engine.data.catalysts_news import get_short_term_catalysts, fetch_ticker_catalysts, is_headline_current
from earnings_engine.features.market_sentiment import get_market_sentiment
from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity

logger = logging.getLogger(__name__)

# =============================================================================
# ⚖️ STANDARDIZED 6-PILLAR FACTOR WEIGHT MODEL & RELEVANCE MATRIX (100% TOTAL)
# =============================================================================
STANDARDIZED_FACTORS_WEIGHT_MODEL: dict[str, Any] = {
    "version": "2.0.0",
    "last_reviewed": "2026-08-26",
    "total_weight": 100.0,
    "pillars": {
        "pillar_1_institutional_flows": {
            "name": "🏛️ Institutional & Smart Money Flows",
            "weight_pct": 22.0,
            "description": "Quarterly mutual fund (DII), FII/FPI, Super Investor stake deltas, and block deal conviction.",
            "sub_factors": [
                {
                    "name": "Mutual Fund (DII) Net Stake Delta (QoQ)",
                    "weight_pct": 7.0,
                    "relevance": "CRITICAL",
                    "relevance_explanation": "Mutual funds deploy long-term domestic capital. Sustained buying indicates high fundamental conviction.",
                    "scope_of_improvement": "Integrate monthly scheme-level holding reports instead of waiting for quarterly SEBI filings.",
                },
                {
                    "name": "FII / FPI Institutional Inflows & Exits",
                    "weight_pct": 6.0,
                    "relevance": "HIGH",
                    "relevance_explanation": "Foreign institutional flows dictate major liquidity waves and large-cap valuation expansion.",
                    "scope_of_improvement": "Track FII sector-level allocation trends alongside single-stock filings.",
                },
                {
                    "name": "Super Investor & Whale Buying (Ashish Kacholia, Dolly Khanna, etc.)",
                    "weight_pct": 4.5,
                    "relevance": "HIGH",
                    "relevance_explanation": "Ace investors have proven track records of discovering high-alpha mid/small-caps before broad market discovery.",
                    "scope_of_improvement": "Monitor exchange disclosure dates to separate initial signal from retail crowd-chasing lag.",
                },
                {
                    "name": "Large Exchange Block / Bulk Deals Net Flow",
                    "weight_pct": 4.5,
                    "relevance": "MEDIUM_HIGH",
                    "relevance_explanation": "Block deals show immediate institutional transfer of hands at market prices without open-market slippage.",
                    "scope_of_improvement": "Filter promoter block sales (e.g. debt reduction vs stake dilution) from strategic fund entries.",
                },
            ],
        },
        "pillar_2_technical_momentum": {
            "name": "⚡ Technical Momentum & Price Structure",
            "weight_pct": 20.0,
            "description": "Multi-timeframe price momentum, volume expansion, EMA alignment, and compression channels.",
            "sub_factors": [
                {
                    "name": "Volume Surge Ratio (5D vs 63D / Deliverable Spike)",
                    "weight_pct": 5.5,
                    "relevance": "CRITICAL",
                    "relevance_explanation": "Price moves accompanied by 2x-5x deliverable volume surges confirm genuine accumulation vs retail noise.",
                    "scope_of_improvement": "Isolate high-deliverable % days from intraday scalping churn.",
                },
                {
                    "name": "52-Week High / Resistance Distance & Compression Coiling",
                    "weight_pct": 5.0,
                    "relevance": "HIGH",
                    "relevance_explanation": "Stocks within 0–5% of 52W Highs have zero overhead resistance and strong upward drift potential.",
                    "scope_of_improvement": "Compute multi-month Bollinger Band Width (BBW) compression percentiles.",
                },
                {
                    "name": "Moving Average Alignment (EMA 20 > 50 > 200 Stack)",
                    "weight_pct": 4.5,
                    "relevance": "HIGH",
                    "relevance_explanation": "Confirms established multi-timeframe trend alignment and institutional support zones.",
                    "scope_of_improvement": "Check slope angle of 20 EMA and 50 EMA for trend velocity.",
                },
                {
                    "name": "RSI-14 Momentum & Mean Reversion Bound",
                    "weight_pct": 3.0,
                    "relevance": "MEDIUM",
                    "relevance_explanation": "Identifies overbought exhaustion (> 75) vs bullish momentum sweet spot (55–70).",
                    "scope_of_improvement": "Use Smoothed RSI or MACD Histogram divergence alongside RSI.",
                },
                {
                    "name": "Swing Range Position (Support vs Resistance)",
                    "weight_pct": 2.0,
                    "relevance": "MEDIUM",
                    "relevance_explanation": "Defines entry risk-reward ratio near lower support channel bounds.",
                    "scope_of_improvement": "Auto-adjust swing channels dynamically as volatility expands.",
                },
            ],
        },
        "pillar_3_earnings_surprises": {
            "name": "📊 Corporate Earnings Surprises & Track Record",
            "weight_pct": 18.0,
            "description": "Quarterly EPS beats, surprise streaks, historical post-earnings reaction returns, and guidance.",
            "sub_factors": [
                {
                    "name": "EPS & Revenue Surprise % (vs Consensus Estimates)",
                    "weight_pct": 6.5,
                    "relevance": "CRITICAL",
                    "relevance_explanation": "Surprises force Wall Street/Dalal Street analysts to revise discounted cash flow models upward immediately.",
                    "scope_of_improvement": "Distinguish core operating profit surprises from one-off other income windfalls.",
                },
                {
                    "name": "Historical Post-Earnings Reaction Returns (1D & 7D Drift)",
                    "weight_pct": 4.5,
                    "relevance": "HIGH",
                    "relevance_explanation": "Measures post-earnings announcement drift (PEAD) persistence across recent quarters.",
                    "scope_of_improvement": "Compute intraday gap vs full-day reaction return differential.",
                },
                {
                    "name": "Earnings Surprise Streak & Beat Frequency",
                    "weight_pct": 4.0,
                    "relevance": "MEDIUM_HIGH",
                    "relevance_explanation": "Companies with 3+ consecutive quarter beats exhibit compounding operational momentum and conservative guidance.",
                    "scope_of_improvement": "Factor in management earnings call sentiment and transcript NLP scoring.",
                },
                {
                    "name": "Days to Next Earnings Announcement Window",
                    "weight_pct": 3.0,
                    "relevance": "MEDIUM",
                    "relevance_explanation": "Volatility and implied move expand as earnings date approaches (< 14 days).",
                    "scope_of_improvement": "Integrate options implied earnings move for liquid F&O equities.",
                },
            ],
        },
        "pillar_4_corporate_catalysts": {
            "name": "📰 Corporate Filings, Catalysts & News Sentiment",
            "weight_pct": 16.0,
            "description": "Material events: large order wins, capacity expansions, FDA approvals, M&A, and regulatory actions.",
            "sub_factors": [
                {
                    "name": "Commercial Order Wins & Multi-Year Contract Awards",
                    "weight_pct": 6.0,
                    "relevance": "CRITICAL",
                    "relevance_explanation": "Order book visibility directly enhances future 4-8 quarter revenue predictability and forward EPS.",
                    "scope_of_improvement": "Normalize order value as % of company trailing 12-month revenue.",
                },
                {
                    "name": "Regulatory Clearances, FDA Approvals & Patent Grants",
                    "weight_pct": 4.0,
                    "relevance": "HIGH",
                    "relevance_explanation": "Removes major binary overhangs and opens immediate high-margin revenue streams.",
                    "scope_of_improvement": "Track Warning Letters and Form 483 resolution speed in pharma.",
                },
                {
                    "name": "CapEx Expansion, Mergers & Strategic Joint Ventures",
                    "weight_pct": 3.5,
                    "relevance": "MEDIUM_HIGH",
                    "relevance_explanation": "Demonstrates management capital deployment conviction and sector market share capture.",
                    "scope_of_improvement": "Evaluate Return on Capital Employed (ROCE) history of past CapEx cycles.",
                },
                {
                    "name": "Management Guidance & Structural Restructuring",
                    "weight_pct": 2.5,
                    "relevance": "MEDIUM",
                    "relevance_explanation": "Positive management commentary drives upward target price consensus revisions.",
                    "scope_of_improvement": "Cross-reference management guidance against historical track record of delivery.",
                },
            ],
        },
        "pillar_5_market_sentiment": {
            "name": "🌐 Market Sentiment, Macro Regime & Volatility",
            "weight_pct": 14.0,
            "description": "India VIX regime, benchmark index momentum (Nifty 50 / S&P 500), and institutional liquidity breadth.",
            "sub_factors": [
                {
                    "name": "India VIX / CBOE VIX Volatility Regime",
                    "weight_pct": 5.0,
                    "relevance": "CRITICAL",
                    "relevance_explanation": "VIX > 20 elevates market-wide risk-off selling; VIX < 14 creates favorable breakout tailwinds.",
                    "scope_of_improvement": "Track 5-day rate of change in VIX to detect volatility spikes before index breakdowns.",
                },
                {
                    "name": "Benchmark Index 5D & 20D Trend (Nifty 50 / S&P 500)",
                    "weight_pct": 4.5,
                    "relevance": "HIGH",
                    "relevance_explanation": "70% of individual equities follow the direction of the primary market trend.",
                    "scope_of_improvement": "Monitor market advance-decline ratio across the NSE 500 universe.",
                },
                {
                    "name": "Sector Relative Strength Index (RS vs Benchmark)",
                    "weight_pct": 4.5,
                    "relevance": "HIGH",
                    "relevance_explanation": "Leaders in outperforming sectors experience institutional sector-rotation inflows.",
                    "scope_of_improvement": "Compute rolling 21-day Mansfied Relative Strength (MRS) vs benchmark index.",
                },
            ],
        },
        "pillar_6_valuation_fundamentals": {
            "name": "💰 Valuation Multiples & Balance Sheet Health",
            "weight_pct": 10.0,
            "description": "Relative valuation (P/E vs Sector P/E, PEG), return ratios (ROE, ROCE), and financial leverage (Debt/Equity).",
            "sub_factors": [
                {
                    "name": "Relative P/E Multiple vs Sector Benchmark P/E",
                    "weight_pct": 3.5,
                    "relevance": "HIGH",
                    "relevance_explanation": "Establishes margin of safety and whether the market is pricing in excessive optimism or undervaluation.",
                    "scope_of_improvement": "Use Forward 1Y P/E instead of Trailing 12M P/E where forward consensus is available.",
                },
                {
                    "name": "Return on Equity (ROE) & Operating Profit Margins",
                    "weight_pct": 3.5,
                    "relevance": "HIGH",
                    "relevance_explanation": "High ROE (> 18%) with stable operating margins (> 15%) proves competitive moat and pricing power.",
                    "scope_of_improvement": "Decompose ROE via DuPont Analysis (Net Margin × Asset Turnover × Financial Leverage).",
                },
                {
                    "name": "Financial Leverage & Solvency (Debt-to-Equity Ratio)",
                    "weight_pct": 3.0,
                    "relevance": "MEDIUM_HIGH",
                    "relevance_explanation": "Low D/E (< 0.5) protects against interest rate shocks and enables counter-cyclical investment.",
                    "scope_of_improvement": "Track Interest Coverage Ratio (EBIT / Interest Expense) for debt-heavy sectors.",
                },
            ],
        },
    },
}


# =============================================================================
# 🧩 CANONICAL STANDARDIZED CONTEXT BUILDER
# =============================================================================
def build_standardized_model_context(
    ticker: str,
    timeframe_days: int = 14,
    settings: Settings | None = None,
    fetch_live: bool = True,
) -> dict[str, Any]:
    """Assemble a complete, standardized Point-in-Time context dictionary for any model.

    Standardizes inputs across all 6 core pillars:
    - Pillar 1: Institutional & Smart Money Flows
    - Pillar 2: Technical Momentum & Price Structure
    - Pillar 3: Earnings Surprises & Track Record
    - Pillar 4: Corporate Catalysts, News & Order Wins
    - Pillar 5: Market Sentiment & Macro Regime
    - Pillar 6: Valuation Multiples & Fundamental Quality
    """
    settings = settings or Settings()
    sym = ticker.strip().upper()
    now_dt = datetime.now(timezone.utc)

    ctx: dict[str, Any] = {
        "ticker": sym,
        "timeframe_days": timeframe_days,
        "generated_at": now_dt.isoformat(),
        "is_live": False,
        "factor_model_version": STANDARDIZED_FACTORS_WEIGHT_MODEL["version"],
    }

    # 1. Base Metadata & Live Quote
    live_q: dict[str, Any] = {}
    if fetch_live:
        try:
            live_q = fetch_live_quote(sym, settings=settings, sync_db=True)
            if live_q.get("current_price"):
                ctx["is_live"] = True
                ctx["live_quote"] = live_q
        except Exception as e:
            logger.debug("[STD-CTX] Live quote fetch error for %s: %s", sym, e)

    # 2. Market Cap & Metadata from DB
    profile: dict[str, Any] = {
        "ticker": sym,
        "company_name": sym.replace(".NS", ""),
        "sector": "Equities",
        "industry": "General",
        "market_cap": None,
    }
    db_metrics: dict[str, Any] = {}
    try:
        conn = get_db_connection(settings)
        row = conn.execute(
            "SELECT name, market_cap, sector, industry, metrics FROM tickers WHERE ticker = ?",
            (sym,),
        ).fetchone()
        if row:
            if row[0]: profile["company_name"] = row[0]
            if row[1]: profile["market_cap"] = float(row[1])
            if len(row) > 2 and row[2]: profile["sector"] = row[2]
            if len(row) > 3 and row[3]: profile["industry"] = row[3]
            if len(row) > 4 and row[4]:
                db_metrics = json.loads(row[4]) if isinstance(row[4], str) else row[4]
    except Exception as e:
        logger.debug("[STD-CTX] Metadata lookup error for %s: %s", sym, e)
    ctx["profile"] = profile

    # 3. Pillar 5: Market Sentiment & Macro Regime Data
    market_sentiment = get_market_sentiment(sym, settings=settings, fetch_live=fetch_live)
    try:
        from earnings_engine.data.cross_strategy import compute_market_regime_multiplier
        macro_mult_data = compute_market_regime_multiplier(settings)
        market_sentiment["macro_multiplier_info"] = macro_mult_data
        market_sentiment["fear_greed_score"] = macro_mult_data.get("fear_greed_score", 50.0)
        market_sentiment["macro_bias"] = macro_mult_data.get("macro_bias", "RANGEBOUND_NEUTRAL")
        market_sentiment["macro_pill"] = macro_mult_data.get("macro_pill", "🟡 Neutral")
        market_sentiment["macro_tag"] = macro_mult_data.get("macro_tag", "")
    except Exception as e:
        logger.debug("[STD-CTX] Macro multiplier enrichment error: %s", e)
    ctx["market_sentiment"] = market_sentiment

    # 4. Pillar 1: Institutional & Smart Money Flows
    try:
        inst_activity = get_stock_institutional_activity(sym, settings=settings)
        ctx["institutional_flows"] = {
            "accumulation_score": inst_activity.get("accumulation_score", 50.0),
            "verdict": inst_activity.get("verdict", "Neutral"),
            "funds_in_count": inst_activity.get("funds_accumulating_count", 0),
            "funds_out_count": inst_activity.get("funds_selling_count", 0),
            "net_flow_cr": inst_activity.get("net_flow_cr", 0.0),
            "holdings": inst_activity.get("holdings", []),
            "shareholding_patterns": inst_activity.get("shareholding_patterns", []),
            "block_deals": inst_activity.get("block_deals", []),
        }
    except Exception as e:
        logger.debug("[STD-CTX] Institutional flows error for %s: %s", sym, e)
        ctx["institutional_flows"] = {
            "accumulation_score": 50.0,
            "verdict": "Neutral",
            "holdings": [],
            "shareholding_patterns": [],
            "block_deals": [],
        }

    # 5. Pillar 2: Technical Momentum & Price Structure
    prices_df = load_prices(sym, settings)
    pa: dict[str, Any] = {}
    cmp = live_q.get("current_price")
    if cmp is None and not prices_df.empty and "close" in prices_df.columns:
        cmp = float(prices_df["close"].dropna().iloc[-1])

    if not prices_df.empty and "close" in prices_df.columns:
        closes = prices_df["close"].dropna()
        highs = prices_df["high"].dropna() if "high" in prices_df.columns else closes
        lows = prices_df["low"].dropna() if "low" in prices_df.columns else closes
        vols = prices_df["volume"].dropna() if "volume" in prices_df.columns else pd.Series(dtype=float)

        pa["current_price"] = round(float(cmp), 2) if cmp else None
        if len(closes) >= 7:
            p_7d = float(closes.iloc[-7])
            pa["return_7d"] = round(((cmp - p_7d) / p_7d) * 100, 2)
        if len(closes) >= 30:
            p_30d = float(closes.iloc[-30])
            pa["return_30d"] = round(((cmp - p_30d) / p_30d) * 100, 2)

        # 52-Week extremes
        w52_high = float(highs.tail(252).max()) if len(highs) >= 10 else float(highs.max())
        w52_low = float(lows.tail(252).min()) if len(lows) >= 10 else float(lows.min())
        pa["high_52w"] = round(w52_high, 2)
        pa["low_52w"] = round(w52_low, 2)
        if cmp and w52_high > 0:
            pa["pct_from_52w_high"] = round(((cmp - w52_high) / w52_high) * 100, 2)
        if cmp and w52_low > 0:
            pa["pct_from_52w_low"] = round(((cmp - w52_low) / w52_low) * 100, 2)

        # Technical Indicators
        if len(closes) >= 14:
            delta = closes.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, 0.001)
            rsi = 100 - (100 / (1 + rs))
            pa["rsi_14"] = round(float(rsi.dropna().iloc[-1]), 1) if not rsi.dropna().empty else None

        if len(closes) >= 20: pa["ema_20"] = round(float(closes.ewm(span=20, adjust=False).mean().iloc[-1]), 2)
        if len(closes) >= 50: pa["ema_50"] = round(float(closes.ewm(span=50, adjust=False).mean().iloc[-1]), 2)
        if len(closes) >= 200: pa["ema_200"] = round(float(closes.ewm(span=200, adjust=False).mean().iloc[-1]), 2)

        # Volume Ratio (5D vs 63D)
        if len(vols) >= 63:
            v_5d = vols.tail(5).mean()
            v_63d = vols.tail(63).mean()
            pa["volume_ratio_5d_63d"] = round(float(v_5d / v_63d), 2) if v_63d > 0 else 1.0
            pa["avg_volume_20d"] = int(vols.tail(20).mean())

    ctx["technical_momentum"] = pa

    # Swing channel bounds
    closes_series = prices_df["close"] if (not prices_df.empty and "close" in prices_df.columns) else None
    swing = detect_swing_range(closes_series) if closes_series is not None else {}
    ctx["swing_structure"] = swing

    # 6. Pillar 3: Corporate Earnings Surprises & Track Record
    ea: dict[str, Any] = {}
    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            """
            SELECT earnings_date, eps_estimate, eps_reported, surprise_pct
            FROM earnings_history
            WHERE ticker = ?
            ORDER BY earnings_date DESC
            LIMIT 6
            """,
            (sym,),
        ).fetchall()

        past_surprises = []
        for r in rows:
            if r[3] is not None:
                past_surprises.append({
                    "date": str(r[0]),
                    "eps_estimate": r[1],
                    "eps_reported": r[2],
                    "surprise_pct": round(float(r[3]), 2),
                })
        ea["past_surprises"] = past_surprises
        if past_surprises:
            ea["mean_surprise_pct"] = round(sum(s["surprise_pct"] for s in past_surprises) / len(past_surprises), 2)
            ea["beat_rate_pct"] = round(len([s for s in past_surprises if s["surprise_pct"] > 0]) / len(past_surprises) * 100, 1)

        # Check upcoming earnings date
        up_row = conn.execute(
            "SELECT earnings_date FROM earnings_history WHERE ticker = ? AND earnings_date >= date('now') ORDER BY earnings_date ASC LIMIT 1",
            (sym,),
        ).fetchone()
        if up_row and up_row[0]:
            next_date = datetime.strptime(str(up_row[0])[:10], "%Y-%m-%d")
            ea["next_earnings_date"] = str(up_row[0])[:10]
            ea["days_to_next_earnings"] = max(0, (next_date - datetime.now()).days)
    except Exception as e:
        logger.debug("[STD-CTX] Earnings history error for %s: %s", sym, e)
    ctx["earnings_track_record"] = ea

    # 7. Pillar 4: Corporate Catalysts, News & Order Wins
    try:
        # Check SQLite DB first for instant resolution without triggering live scraping/LLM during modal load
        conn = get_db_connection(settings)
        rows = conn.execute(
            "SELECT * FROM news_catalysts WHERE ticker = ? ORDER BY published_at DESC, impact_score DESC LIMIT 8",
            (sym,),
        ).fetchall()
        col_names = [d[0] for d in conn.execute("SELECT * FROM news_catalysts LIMIT 0").description] if rows else []
        db_cats = [dict(zip(col_names, r)) for r in rows]
        raw_cats = [c for c in db_cats if is_headline_current(c.get("title", ""), c.get("summary") or "", c.get("published_at", ""))]

        # If completely empty and fetch_live is enabled, fetch without heavy AI parsing (run_ai=False)
        if not raw_cats and fetch_live:
            raw_cats = fetch_ticker_catalysts(sym, limit=8, force=False, run_ai=False, settings=settings)

        ctx["corporate_catalysts"] = raw_cats[:6] if raw_cats else []
    except Exception as e:
        logger.debug("[STD-CTX] Catalysts error for %s: %s", sym, e)
        ctx["corporate_catalysts"] = []

    # 8. Pillar 6: Valuation Multiples & Fundamental Quality
    pe = db_metrics.get("pe") or db_metrics.get("trailing_pe") or live_q.get("pe")
    pb = db_metrics.get("pb") or db_metrics.get("price_to_book")
    roe = db_metrics.get("roe") or db_metrics.get("return_on_equity")
    de = db_metrics.get("debt_to_equity") or db_metrics.get("de_ratio")
    op_margin = db_metrics.get("operating_margin") or db_metrics.get("ebitda_margin")

    ctx["valuation_fundamentals"] = {
        "pe": round(float(pe), 1) if pe is not None else None,
        "pb": round(float(pb), 2) if pb is not None else None,
        "roe_pct": round(float(roe), 1) if roe is not None else None,
        "debt_to_equity": round(float(de), 2) if de is not None else None,
        "operating_margin_pct": round(float(op_margin), 1) if op_margin is not None else None,
    }

    return ctx


# =============================================================================
# 📝 CANONICAL STANDARDIZED LLM PROMPT FORMATTER
# =============================================================================
def format_standardized_llm_prompt(ctx: dict[str, Any]) -> str:
    """Format the standardized multi-pillar context into a structured LLM prompt."""
    ticker = ctx.get("ticker", "UNKNOWN")
    timeframe = ctx.get("timeframe_days", 14)
    profile = ctx.get("profile", {})
    pa = ctx.get("technical_momentum", {})
    sw = ctx.get("swing_structure", {})
    ea = ctx.get("earnings_track_record", {})
    cat = ctx.get("corporate_catalysts", [])
    mkt = ctx.get("market_sentiment", {})
    inst = ctx.get("institutional_flows", {})
    val = ctx.get("valuation_fundamentals", {})
    is_live = ctx.get("is_live", False)
    curr_sym = "$" if not ticker.endswith(".NS") else "₹"

    lines = [
        f"# Point-in-Time Quantitative Analysis Context: {ticker} ({profile.get('company_name', ticker)})",
        f"**Sector / Industry:** {profile.get('sector', 'General')} | {profile.get('industry', 'General')}",
        f"**Forecast Timeframe:** {timeframe} Trading Days",
        f"**Analysis Timestamp:** {ctx.get('generated_at', 'N/A')}",
        f"**Market Feed Status:** {'🟢 Live Real-Time authoritative Quote' if is_live else '📊 Daily Historical Snapshot'}",
        "",
        "---",
        "## ⚖️ Quantitative Factor Weight Rubric (Total: 100%)",
        "Your predictive synthesis MUST rigorously weigh the 6 fundamental pillars according to these empirical weights:",
        "1. **🏛️ Institutional & Smart Money Flows (22%)** — Mutual fund accumulation, FII net flows, whale holdings.",
        "2. **⚡ Technical Momentum & Price Structure (20%)** — Volume surge ratio, 52W resistance proximity, EMA alignment.",
        "3. **📊 Earnings Surprises & Fundamental Track Record (18%)** — Beat streaks, surprise magnitude, reaction drift.",
        "4. **📰 Corporate Filings, Catalysts & Order Wins (16%)** — Confirmed orders, regulatory clearances, CapEx expansion.",
        "5. **🌐 Market Sentiment & Macro Volatility Regime (14%)** — India VIX regime, benchmark index trend, market breadth.",
        "6. **💰 Valuation Multiples & Balance Sheet Health (10%)** — P/E relative to sector, ROE %, Debt-to-Equity ratio.",
        "",
        "---",
        "## 🌐 Pillar 5: Market Sentiment & Macro Regime (Weight: 14%)",
        f"- **Macro Market Stance:** {mkt.get('macro_pill', '🟡 Neutral')} — *{mkt.get('macro_tag', 'Normal Regime')}*",
        f"- **Fear & Greed Index:** {mkt.get('fear_greed_score', 50):.1f}/100 (`{mkt.get('macro_bias', 'RANGEBOUND_NEUTRAL')}`)",
        f"- **Benchmark Index ({mkt.get('benchmark_name', 'Nifty 50')}):** {mkt.get('benchmark_symbol')} @ {mkt.get('benchmark_cmp', 'N/A')} "
        f"| 5D: {mkt.get('benchmark_return_5d_pct', 0):+.2f}% | 20D: {mkt.get('benchmark_return_20d_pct', 0):+.2f}%",
        f"- **Index Trend:** `{mkt.get('benchmark_trend', 'NEUTRAL')}`",
        f"- **Volatility Metric ({mkt.get('vix_name', 'India VIX')}):** {mkt.get('vix_level', 'N/A')} (5D Change: {mkt.get('vix_change_5d_pct', 0):+.1f}%)",
        f"- **Volatility Regime:** {mkt.get('vix_regime_label', 'Normal')} — *{mkt.get('vix_description', '')}*",
        f"- **Institutional Market Net Bias:** `{mkt.get('institutional_net_bias', 'BALANCED')}` (Net: ₹{mkt.get('institutional_net_cr', 0)} Cr)",
        f"- **Overall Market Climate:** {mkt.get('market_climate', 'Supportive')} (Score: {mkt.get('market_sentiment_score', 50)}/100)",
        "",
        "## 🏛️ Pillar 1: Institutional & Smart Money Flows (Weight: 22%)",
        f"- **Institutional Accumulation Score:** {inst.get('accumulation_score', 50)} / 100 (`{inst.get('verdict', 'Neutral')}`)",
        f"- **Tracked Fund Actions:** +{inst.get('funds_in_count', 0)} Buying / -{inst.get('funds_out_count', 0)} Selling",
    ]

    holdings = inst.get("holdings", [])
    if holdings:
        lines.append("- **Top Institutional & Mutual Fund Holders:**")
        for h in holdings[:5]:
            lines.append(f"  • {h.get('fund_name')} ({h.get('fund_type')}): **{h.get('stake_pct')}%** stake | Action: `{h.get('action')}` ({h.get('change_pct', 0):+}% change)")
    else:
        lines.append("- No individual fund holding filings found.")

    pats = inst.get("shareholding_patterns", [])
    if pats:
        latest_pat = pats[0]
        lines.append(f"- **Latest Shareholding ({latest_pat.get('quarter', 'Recent')}):** Promoter: {latest_pat.get('promoter_pct')}% | FII/FPI: **{latest_pat.get('fii_pct')}%** | DII/Mutual Funds: **{latest_pat.get('dii_mf_pct')}%** | Retail: {latest_pat.get('public_retail_pct')}%")

    lines.extend([
        "",
        "## ⚡ Pillar 2: Technical Momentum & Price Structure (Weight: 20%)",
    ])

    if pa:
        lines.extend([
            f"- **Current Authoritative Price:** {curr_sym}{pa.get('current_price', 'N/A')}",
            f"- **Trailing Momentum:** 7-Day: {pa.get('return_7d', 0):+.2f}% | 30-Day: {pa.get('return_30d', 0):+.2f}%",
            f"- **52-Week Range:** Low: {curr_sym}{pa.get('low_52w', 'N/A')} ({pa.get('pct_from_52w_low', 0):+.1f}%) ➔ High: {curr_sym}{pa.get('high_52w', 'N/A')} ({pa.get('pct_from_52w_high', 0):+.1f}% from peak)",
            f"- **Volume Multiple:** {pa.get('volume_ratio_5d_63d', 1.0)}x (5D average volume vs 63D baseline)",
            f"- **RSI-14:** {pa.get('rsi_14', 'N/A')}",
            f"- **Key Moving Averages:** EMA-20: {curr_sym}{pa.get('ema_20', 'N/A')} | EMA-50: {curr_sym}{pa.get('ema_50', 'N/A')} | EMA-200: {curr_sym}{pa.get('ema_200', 'N/A')}",
        ])
    else:
        lines.append("- No detailed price action metrics available.")

    if sw and sw.get("lower") is not None:
        lines.extend([
            f"- **Support / Resistance Channel:** Support: {curr_sym}{sw.get('lower')} | Resistance: {curr_sym}{sw.get('upper')}",
            f"- **Position in Channel:** {sw.get('position_in_channel', 50):.0f}% (0%=at support floor, 100%=at resistance ceiling)",
        ])

    lines.extend([
        "",
        "## 📊 Pillar 3: Earnings Surprises & Track Record (Weight: 18%)",
    ])
    if ea:
        if ea.get("days_to_next_earnings") is not None:
            lines.append(f"- **Days to Next Earnings Announcement:** **{ea['days_to_next_earnings']} days** ({ea.get('next_earnings_date')})")
        if ea.get("beat_rate_pct") is not None:
            lines.append(f"- **Historical Beat Rate:** {ea['beat_rate_pct']}% of past releases | Mean Surprise: {ea.get('mean_surprise_pct', 0):+.2f}%")
        surprises = ea.get("past_surprises", [])
        if surprises:
            lines.append("- **Recent Surprise History:**")
            for s in surprises[:4]:
                lines.append(f"  • {s.get('date')}: Reported EPS {s.get('eps_reported')} vs Est {s.get('eps_estimate')} (**{s.get('surprise_pct'):+.1f}% surprise**)")
    else:
        lines.append("- No earnings track record data available.")

    lines.extend([
        "",
        "## 📰 Pillar 4: Corporate Catalysts & News Sentiment (Weight: 16%)",
    ])
    if cat:
        for i, c in enumerate(cat[:6], 1):
            direction = c.get("direction", "NEUTRAL")
            icon = "🟢" if direction == "BULLISH" else ("🔴" if direction == "BEARISH" else "⚪")
            pub_date = (c.get("published_at") or "")[:10]
            horizon = c.get("expected_horizon") or "⚡ 1–3 Days"
            lines.append(f"{i}. {icon} [{c.get('impact_score', 50)}/100 {direction}] **{c.get('title', 'N/A')}** ({pub_date})")
            if c.get("category"):
                lines.append(f"   *Category:* {c['category']} | *Impact Level:* {c.get('impact_level', 'MODERATE')} | *Horizon:* {horizon}")
            if c.get("why_it_matters") or c.get("summary"):
                summary_text = (c.get("why_it_matters") or c.get("summary") or "").strip()
                if summary_text:
                    lines.append(f"   *Context:* {summary_text[:180]}")
    else:
        lines.append("- No recent material news catalysts found within the last 30 days.")

    lines.extend([
        "",
        "## 💰 Pillar 6: Valuation Multiples & Financial Health (Weight: 10%)",
        f"- **Valuation Multiples:** P/E Ratio: {val.get('pe', 'N/A')} | P/B Ratio: {val.get('pb', 'N/A')}",
        f"- **Profitability & Moat:** Return on Equity (ROE): {val.get('roe_pct', 'N/A')}% | Operating Margin: {val.get('operating_margin_pct', 'N/A')}%",
        f"- **Balance Sheet Solvency:** Debt-to-Equity: {val.get('debt_to_equity', 'N/A')}",
        "",
        "---",
        "## 🎯 Inference Directive",
        f"Based on the rigorous weighting of these 6 pillars for the **{timeframe}-day forecast window**:",
        "1. Synthesize whether the composite forces indicate **BULLISH**, **BEARISH**, or **NEUTRAL** price discovery.",
        "2. Provide high-conviction **Target Price**, **Stop Loss**, and **Confidence Level (0–100%)**.",
        "3. Explicitly state the primary driver from the factor rubric (e.g. Institutional Accumulation vs Macro VIX Headwind).",
    ])

    return "\n".join(lines)


# =============================================================================
# ⚖️ MASTER 6-PILLAR FACTOR EVALUATION ENGINE
# =============================================================================
def evaluate_stock_standard_pillars(
    ticker: str,
    settings: Settings | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute normalized 0–100 scores for each of the 6 standardized pillars and synthesize the master weighted factor score.

    Weights (Total: 100%):
    - Pillar 1: Institutional & Smart Money Flows (22%)
    - Pillar 2: Technical Momentum & Price Structure (20%)
    - Pillar 3: Earnings Surprises & Track Record (18%)
    - Pillar 4: Corporate Filings & News Catalysts (16%)
    - Pillar 5: Market Sentiment & Macro Volatility Regime (14%)
    - Pillar 6: Valuation Multiples & Financial Health (10%)
    """
    settings = settings or Settings()
    sym = ticker.strip().upper()
    if ctx is None:
        ctx = build_standardized_model_context(sym, settings=settings)

    # 1. Pillar 1: Institutional & Smart Money (22%)
    inst = ctx.get("institutional_flows", {})
    p1_score = float(inst.get("accumulation_score", 50.0))
    funds_in = inst.get("funds_in_count", 0)
    funds_out = inst.get("funds_out_count", 0)
    net_flow_cr = inst.get("net_flow_cr", 0.0)
    p1_badge = f"+{funds_in} Funds Buying" if funds_in > 0 else (f"-{funds_out} Funds Selling" if funds_out > 0 else "Neutral")
    p1_detail = f"Score {p1_score:.0f}/100 | +{funds_in} in / -{funds_out} out | Net: ₹{net_flow_cr:+.1f} Cr ({inst.get('verdict', 'Neutral')})"

    # 2. Pillar 2: Technical Momentum & Structure (20%)
    pa = ctx.get("technical_momentum", {})
    p2_base = 50.0
    vol_ratio = pa.get("volume_ratio_5d_63d", 1.0) or 1.0
    pct_52h = pa.get("pct_from_52w_high", -20.0) or -20.0
    ret_30d = pa.get("return_30d", 0.0) or 0.0
    cmp = pa.get("current_price")
    e20 = pa.get("ema_20")
    e50 = pa.get("ema_50")
    e200 = pa.get("ema_200")

    if vol_ratio >= 2.0: p2_base += 20.0
    elif vol_ratio >= 1.3: p2_base += 10.0
    elif vol_ratio < 0.7: p2_base -= 10.0

    if pct_52h >= -5.0: p2_base += 20.0
    elif pct_52h >= -12.0: p2_base += 10.0
    elif pct_52h < -30.0: p2_base -= 15.0

    if ret_30d >= 8.0: p2_base += 15.0
    elif ret_30d >= 0.0: p2_base += 5.0
    elif ret_30d < -8.0: p2_base -= 15.0

    if cmp and e20 and e50 and e200 and (cmp > e20 > e50 > e200):
        p2_base += 15.0

    p2_score = max(10.0, min(98.0, p2_base))
    p2_badge = f"{vol_ratio:.1f}x Vol Surge" if vol_ratio >= 1.3 else f"{pct_52h:+.1f}% from 52W High"
    p2_detail = f"Vol Multiple: {vol_ratio:.2f}x | 30D Ret: {ret_30d:+.1f}% | 52W High Gap: {pct_52h:+.1f}%"

    # 3. Pillar 3: Earnings Surprises & Track Record (18%)
    ea = ctx.get("earnings_track_record", {})
    p3_base = 50.0
    beat_rate = ea.get("beat_rate_pct")
    mean_surp = ea.get("mean_surprise_pct", 0.0) or 0.0
    if beat_rate is not None:
        if beat_rate >= 75.0: p3_base += 25.0
        elif beat_rate >= 50.0: p3_base += 10.0
        elif beat_rate < 30.0: p3_base -= 20.0
    if mean_surp > 10.0: p3_base += 15.0
    elif mean_surp > 0.0: p3_base += 5.0
    elif mean_surp < -5.0: p3_base -= 15.0

    p3_score = max(10.0, min(98.0, p3_base))
    p3_badge = f"{beat_rate:.0f}% Beat Rate" if beat_rate is not None else f"{mean_surp:+.1f}% Mean Surprise"
    p3_detail = f"Historical Beat Rate: {beat_rate or 50:.0f}% | Avg Surprise: {mean_surp:+.1f}%"

    # 4. Pillar 4: Corporate Catalysts & Filings (16%)
    cat = ctx.get("corporate_catalysts", [])
    p4_base = 50.0
    pos_count = 0
    neg_count = 0
    if cat:
        for c in cat[:6]:
            d = c.get("direction", "NEUTRAL")
            imp = c.get("impact_score", 50)
            if d == "BULLISH" or imp >= 70:
                p4_base += 10.0
                pos_count += 1
            elif d == "BEARISH" or imp <= 30:
                p4_base -= 15.0
                neg_count += 1
    p4_score = max(10.0, min(98.0, p4_base))
    p4_badge = f"+{pos_count} Positive Catalysts" if pos_count > 0 else (f"{neg_count} Headwinds" if neg_count > 0 else "Neutral News")
    p4_detail = f"{len(cat)} Catalysts Tracked ({pos_count} positive, {neg_count} negative in last 30d)"

    # 5. Pillar 5: Market Sentiment & Macro Volatility (14%)
    mkt = ctx.get("market_sentiment", {})
    p5_score = float(mkt.get("market_sentiment_score", 50.0))
    vix_val = mkt.get("vix_level", 14.0)
    vix_reg = mkt.get("vix_regime_label", "Normal Volatility")
    p5_badge = f"VIX {vix_val} ({vix_reg})"
    p5_detail = f"Climate: {mkt.get('market_climate', 'Supportive')} | Index: {mkt.get('benchmark_trend', 'NEUTRAL')} | VIX: {vix_val}"

    # 6. Pillar 6: Valuation & Financial Health (10%)
    val = ctx.get("valuation_fundamentals", {})
    p6_base = 50.0
    pe = val.get("pe")
    de = val.get("debt_to_equity")
    roe = val.get("roe_pct")
    if pe is not None:
        if 10.0 <= pe <= 35.0: p6_base += 15.0
        elif pe > 75.0: p6_base -= 15.0
    if de is not None:
        if de <= 0.4: p6_base += 15.0
        elif de > 1.5: p6_base -= 15.0
    if roe is not None:
        if roe >= 15.0: p6_base += 15.0
        elif roe < 6.0: p6_base -= 10.0

    p6_score = max(10.0, min(98.0, p6_base))
    p6_badge = f"P/E {pe:.1f}" if pe else (f"ROE {roe:.1f}%" if roe else "Fair Valuation")
    p6_detail = f"P/E: {pe or '—'} | D/E: {de or '—'} | ROE: {roe or '—'}%"

    # Composite Synthesis (Weights: 22%, 20%, 18%, 16%, 14%, 10%)
    composite = (
        0.22 * p1_score +
        0.20 * p2_score +
        0.18 * p3_score +
        0.16 * p4_score +
        0.14 * p5_score +
        0.10 * p6_score
    )
    composite = round(composite, 1)

    if composite >= 75.0:
        verdict = "STRONG BUY / HIGH CONVICTION"
        verdict_badge = "emerald"
        verdict_icon = "🟢"
    elif composite >= 60.0:
        verdict = "MODERATE BUY / BULLISH TAILWIND"
        verdict_badge = "emerald"
        verdict_icon = "🌱"
    elif composite >= 45.0:
        verdict = "NEUTRAL / RANGE-BOUND"
        verdict_badge = "amber"
        verdict_icon = "🟡"
    elif composite >= 32.0:
        verdict = "CAUTION / DISTRIBUTION PRESSURE"
        verdict_badge = "rose"
        verdict_icon = "🟠"
    else:
        verdict = "BEARISH / ELEVATED RISK"
        verdict_badge = "rose"
        verdict_icon = "🔴"

    return {
        "ticker": sym,
        "composite_score": composite,
        "verdict": verdict,
        "verdict_badge": verdict_badge,
        "verdict_icon": verdict_icon,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "pillars": {
            "institutional_flows": {
                "name": "🏛️ Institutional & Smart Money Flows",
                "weight_pct": 22.0,
                "score": round(p1_score, 1),
                "badge": p1_badge,
                "detail": p1_detail,
                "weighted_points": round(0.22 * p1_score, 1),
            },
            "technical_momentum": {
                "name": "⚡ Technical Momentum & Price Structure",
                "weight_pct": 20.0,
                "score": round(p2_score, 1),
                "badge": p2_badge,
                "detail": p2_detail,
                "weighted_points": round(0.20 * p2_score, 1),
            },
            "earnings_track_record": {
                "name": "📊 Earnings Surprises & Track Record",
                "weight_pct": 18.0,
                "score": round(p3_score, 1),
                "badge": p3_badge,
                "detail": p3_detail,
                "weighted_points": round(0.18 * p3_score, 1),
            },
            "corporate_catalysts": {
                "name": "📰 Corporate Filings & News Catalysts",
                "weight_pct": 16.0,
                "score": round(p4_score, 1),
                "badge": p4_badge,
                "detail": p4_detail,
                "weighted_points": round(0.16 * p4_score, 1),
            },
            "market_sentiment": {
                "name": "🌐 Market Sentiment & Macro Volatility",
                "weight_pct": 14.0,
                "score": round(p5_score, 1),
                "badge": p5_badge,
                "detail": p5_detail,
                "weighted_points": round(0.14 * p5_score, 1),
            },
            "valuation_fundamentals": {
                "name": "💰 Valuation Multiples & Financial Health",
                "weight_pct": 10.0,
                "score": round(p6_score, 1),
                "badge": p6_badge,
                "detail": p6_detail,
                "weighted_points": round(0.10 * p6_score, 1),
            },
        },
    }


# Convenient alias
build_standardized_stock_context = build_standardized_model_context


