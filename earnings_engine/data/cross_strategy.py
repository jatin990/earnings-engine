"""Cross-Strategy Module Synergy & Shared Intelligence Hub.

Aggregates intelligence across:
1. Macro Market Sentiment & India VIX Volatility Regime (market_pulse)
2. Stock-level News Headlines & Regulatory Filing Catalysts (catalysts_news)
3. Multi-Model AI Consensus Predictions (consensus)
4. Breakout Radar Compression & Momentum Setups (breakout_scanner)
5. Horizontal Channel Swing Trading Bands & Support Floors (swing_scanner)

Enables strategies to communicate and discover high-probability Confluence setups.
"""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)


def get_market_macro_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve high-level market sentiment and volatility regime summary."""
    try:
        from earnings_engine.data.market_pulse import get_market_pulse_data
        pulse = get_market_pulse_data(settings=settings, force_refresh=False)
        fg_score = pulse.get("fear_greed_score", 50.0)
        fg_label = pulse.get("fear_greed_label", "Neutral")
        vix = pulse.get("vix_level", 14.0)
        vix_regime = pulse.get("vix_regime", "Calm")
        macro_stance = pulse.get("institutional_stance", "NEUTRAL")

        # Determine macro bias
        if fg_score >= 60.0 and vix < 16.0:
            macro_bias = "BULLISH_EXPANSION"
            macro_badge = f"🟢 Risk-On ({fg_label} · VIX {vix})"
        elif fg_score <= 40.0 or vix > 20.0:
            macro_bias = "BEARISH_DEFENSIVE"
            macro_badge = f"🔴 Risk-Off ({fg_label} · VIX {vix})"
        else:
            macro_bias = "RANGEBOUND_NEUTRAL"
            macro_badge = f"🟡 Neutral ({fg_label} · VIX {vix})"

        return {
            "fear_greed_score": fg_score,
            "fear_greed_label": fg_label,
            "vix_level": vix,
            "vix_regime": vix_regime,
            "macro_stance": macro_stance,
            "macro_bias": macro_bias,
            "macro_badge": macro_badge,
        }
    except Exception as e:
        logger.debug("[CROSS-STRATEGY] Error fetching market macro summary: %s", e)
        return {
            "fear_greed_score": 50.0,
            "fear_greed_label": "Neutral",
            "vix_level": 14.0,
            "vix_regime": "Normal",
            "macro_stance": "NEUTRAL",
            "macro_bias": "RANGEBOUND_NEUTRAL",
            "macro_badge": "🟡 Neutral (VIX 14.0)",
        }


def compute_market_regime_multiplier(settings: Settings | None = None) -> dict[str, Any]:
    """Compute setup multipliers and macro alignment scores across all strategies.

    Returns
    -------
    dict:
        breakout_multiplier: float (0.75 - 1.20)
        swing_multiplier: float (0.80 - 1.15)
        macro_score: float (0 - 15 pts)
        macro_bias: str
        macro_tag: str
        macro_pill: str
        pill_color: str
        fear_greed_score: float
        vix_level: float
    """
    macro = get_market_macro_summary(settings)
    fg = float(macro.get("fear_greed_score", 50.0))
    vix = float(macro.get("vix_level", 14.0))
    bias = macro.get("macro_bias", "RANGEBOUND_NEUTRAL")

    if bias == "BULLISH_EXPANSION" or (fg >= 60 and vix <= 15.5):
        # Risk-on expansion favors momentum breakouts & support rebounds
        breakout_mult = 1.15
        swing_mult = 1.10
        macro_score = 15.0
        macro_tag = "🌐 Macro Tailwinds (Expansion · High Breakout Win-Rate)"
        macro_pill = f"🟢 Tailwinds (+15 pts · Greed {fg:.0f})"
        pill_color = "#34d399"
    elif bias == "BEARISH_DEFENSIVE" or (fg <= 40 or vix >= 20.0):
        # Risk-off volatile regime: penalize false breakouts, tighten swing requirements
        breakout_mult = 0.75
        swing_mult = 0.80
        macro_score = 0.0
        macro_tag = "⚠️ Macro Headwinds (Volatile · Elevated False Breakout Risk)"
        macro_pill = f"🔴 Headwinds (-15 pts · VIX {vix:.1f})"
        pill_color = "#f87171"
    else:
        # Rangebound / Normal
        breakout_mult = 1.00
        swing_mult = 1.05  # Rangebound is great for horizontal support/resistance swings
        macro_score = 8.0
        macro_tag = "⚖️ Rangebound Consolidation (Optimal for Swing Channels)"
        macro_pill = f"🟡 Neutral ({macro.get('fear_greed_label', 'Neutral')})"
        pill_color = "#fbbf24"

    return {
        "breakout_multiplier": breakout_mult,
        "swing_multiplier": swing_mult,
        "macro_score": macro_score,
        "macro_bias": bias,
        "macro_tag": macro_tag,
        "macro_pill": macro_pill,
        "pill_color": pill_color,
        "fear_greed_score": fg,
        "vix_level": vix,
        "macro_summary": macro,
    }


def get_stock_news_sentiment(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve recent news catalysts and sentiment score for a stock."""
    ticker = (ticker or "").upper().strip()
    settings = settings or Settings()
    conn = get_db_connection(settings)

    try:
        from earnings_engine.data.catalysts_news import _connect
        _connect(settings)

        cursor = conn.execute(
            """
            SELECT title, impact_score, category, direction, published_at
            FROM news_catalysts
            WHERE ticker = ?
            ORDER BY published_at DESC
            LIMIT 3
            """,
            (ticker,),
        )
        rows = cursor.fetchall()
        if rows:
            latest = rows[0]
            title = str(latest[0] or "")
            impact = int(latest[1] or 50)
            cat = str(latest[2] or "News")
            direction = str(latest[3] or "NEUTRAL").upper()

            # Normalized sentiment score: +1.0 for Bullish 100%, -1.0 for Bearish 100%
            if "BULL" in direction:
                score = round(impact / 100.0, 2)
            elif "BEAR" in direction:
                score = round(-impact / 100.0, 2)
            else:
                score = 0.0

            is_pos = score >= 0.2
            is_neg = score <= -0.2

            badge_text = f"📰 {score:+.2f} ({cat})"
            badge_color = "#34d399" if is_pos else ("#f87171" if is_neg else "#fbbf24")

            return {
                "has_news": True,
                "sentiment_score": score,
                "category": cat,
                "latest_headline": title,
                "badge_text": badge_text,
                "badge_color": badge_color,
                "headlines_count": len(rows),
            }
    except Exception as e:
        logger.debug("[CROSS-STRATEGY] Error querying news_catalysts: %s", e)

    return {
        "has_news": False,
        "sentiment_score": 0.0,
        "category": "No Recent News",
        "latest_headline": "No major corporate regulatory filings or news in the last 7 days.",
        "badge_text": "📰 Neutral",
        "badge_color": "#94a3b8",
        "headlines_count": 0,
    }


def get_stock_confluence(
    ticker: str,
    settings: Settings | None = None,
    current_swing_item: dict[str, Any] | None = None,
    current_breakout_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate cross-module confluence across Breakout, Swing, AI Consensus, and News."""
    ticker = (ticker or "").upper().strip()
    settings = settings or Settings()

    # 1. Macro context
    macro = get_market_macro_summary(settings)

    # 2. Stock News
    news = get_stock_news_sentiment(ticker, settings)

    # 3. Check Swing Status
    swing_tier = "COLD"
    is_swing_buy = False
    if current_swing_item:
        swing_tier = current_swing_item.get("tier", "COLD")
        is_swing_buy = current_swing_item.get("swing_signal") in ("Strong Buy", "Buy Zone", "Buy") or (
            0.0 <= float(current_swing_item.get("dist_to_support_pct", 99)) <= 3.5
        )
    else:
        try:
            from earnings_engine.data.swing_scanner import _pool as s_pool
            if ticker in s_pool.get("hot", {}):
                swing_tier = "HOT"
                is_swing_buy = True
            elif ticker in s_pool.get("warm", {}):
                swing_tier = "WARM"
        except Exception:
            pass

    # 4. Check Breakout Status
    breakout_tier = "COLD"
    is_breakout = False
    if current_breakout_item:
        breakout_tier = current_breakout_item.get("tier", "COLD")
        is_breakout = breakout_tier in ("HOT", "WARM")
    else:
        try:
            from earnings_engine.data.breakout_scanner import _pool as b_pool
            if ticker in b_pool.get("hot", {}):
                breakout_tier = "HOT"
                is_breakout = True
            elif ticker in b_pool.get("warm", {}):
                breakout_tier = "WARM"
        except Exception:
            pass

    # 5. Check AI Consensus
    ai_dir = "NEUTRAL"
    ai_score = 50
    try:
        from earnings_engine.consensus.storage import _ensure_table
        conn = get_db_connection(settings)
        _ensure_table(conn)
        c_row = conn.execute(
            "SELECT consensus_direction, consensus_strength FROM consensus_predictions WHERE ticker = ? ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if c_row:
            ai_dir = str(c_row[0] or "NEUTRAL")
            ai_score = int(c_row[1] or 50)
    except Exception:
        pass

    is_ai_buy = "BUY" in ai_dir.upper() or "BULL" in ai_dir.upper()

    # 6. Confluence Synergy Evaluation
    confluence_level = 0
    tags: list[str] = []

    if is_swing_buy and is_breakout and is_ai_buy:
        confluence_level = 3
        confluence_tag = "🔥 Triple Confluence: Swing Floor + Breakout + AI Consensus"
        confluence_badge = "🔥 TRIPLE SETUP"
        badge_color = "#f43f5e"
    elif is_swing_buy and is_breakout:
        confluence_level = 2
        confluence_tag = "🎯 Dual Setup: Support Floor Bounce + Volume Breakout"
        confluence_badge = "🎯 DUAL SETUP"
        badge_color = "#38bdf8"
    elif is_swing_buy and is_ai_buy:
        confluence_level = 2
        confluence_tag = "⭐ AI-Validated Swing: High-Conviction Support Floor"
        confluence_badge = "⭐ AI SWING"
        badge_color = "#34d399"
    elif is_breakout and is_ai_buy:
        confluence_level = 2
        confluence_tag = "⚡ AI Momentum: Breakout Compression + Model Consensus"
        confluence_badge = "⚡ AI BREAKOUT"
        badge_color = "#a855f7"
    elif is_swing_buy:
        confluence_level = 1
        confluence_tag = "🔄 Swing Setup: Channel Support Floor"
        confluence_badge = "🔄 SWING"
        badge_color = "#10b981"
    elif is_breakout:
        confluence_level = 1
        confluence_tag = "⚡ Breakout Setup: Momentum Compression Surge"
        confluence_badge = "⚡ BREAKOUT"
        badge_color = "#f97316"
    else:
        confluence_level = 0
        confluence_tag = "Single Module Scan"
        confluence_badge = "STANDARD"
        badge_color = "#64748b"

    # News catalyst alignment
    news_aligned = (news["sentiment_score"] > 0 and is_swing_buy) or (news["sentiment_score"] > 0 and is_breakout)

    # Synthesis summary
    summary_parts = []
    if confluence_level >= 2:
        summary_parts.append(confluence_tag)
    if news["has_news"] and news["sentiment_score"] != 0:
        summary_parts.append(f"News catalyst: {news['category']} ({news['sentiment_score']:+.2f})")
    summary_parts.append(f"Macro context: {macro['macro_badge']}")

    return {
        "ticker": ticker,
        "confluence_level": confluence_level,
        "confluence_tag": confluence_tag,
        "confluence_badge": confluence_badge,
        "badge_color": badge_color,
        "is_swing_buy": is_swing_buy,
        "is_breakout": is_breakout,
        "is_ai_buy": is_ai_buy,
        "ai_direction": ai_dir,
        "ai_strength": ai_score,
        "swing_tier": swing_tier,
        "breakout_tier": breakout_tier,
        "news": news,
        "macro": macro,
        "news_aligned": news_aligned,
        "synthesis": " • ".join(summary_parts),
    }
