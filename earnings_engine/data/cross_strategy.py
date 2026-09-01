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
        from earnings_engine.data.market_pulse import _PULSE_CACHE, _PULSE_CACHE_TTL
        now_ts = time.time()
        if "data" in _PULSE_CACHE and (now_ts - _PULSE_CACHE.get("ts", 0)) < _PULSE_CACHE_TTL:
            pulse = _PULSE_CACHE["data"]
        else:
            from earnings_engine.data.market_pulse import compute_market_sentiment_matrix
            sentiment_data = compute_market_sentiment_matrix(settings=settings)
            pulse = {
                "fear_greed_score": sentiment_data.get("fear_greed_score", 50.0),
                "fear_greed_label": sentiment_data.get("fear_greed_label", "Neutral"),
                "vix_level": sentiment_data.get("vix_level", 14.0),
                "vix_regime": sentiment_data.get("vix_regime", "Calm"),
                "institutional_stance": "NEUTRAL",
            }
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


# ---------------------------------------------------------------------------
# Cross-Strategy Confluence Radar Persistence & Background Job
# ---------------------------------------------------------------------------

_CONFLUENCE_CACHE: dict[str, Any] = {}
_CONFLUENCE_CACHE_TTL: float = 120.0  # 2-minute memory cache


def _init_confluence_db(conn: Any) -> None:
    """Initialize confluence_radar table and composite index."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS confluence_radar (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            industry TEXT,
            confluence_level INTEGER DEFAULT 0,
            confluence_tag TEXT,
            confluence_badge TEXT,
            badge_color TEXT,
            is_swing_buy INTEGER DEFAULT 0,
            is_breakout INTEGER DEFAULT 0,
            is_ai_buy INTEGER DEFAULT 0,
            ai_direction TEXT,
            ai_strength REAL,
            swing_tier TEXT,
            breakout_tier TEXT,
            current_price REAL,
            signal_price REAL,
            target_price REAL,
            stop_loss REAL,
            risk_reward_ratio REAL,
            composite_score REAL DEFAULT 0,
            synthesis TEXT,
            data_json TEXT,
            scanned_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_confluence_level_score ON confluence_radar(confluence_level DESC, composite_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_confluence_scanned_at ON confluence_radar(scanned_at DESC)")
    except Exception:
        pass


def compute_and_save_confluence_radar(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Background scheduled job to evaluate cross-module synergy and persist ranked confluence setups."""
    import json
    import time
    from datetime import datetime, timezone

    settings = settings or Settings()
    conn = None
    try:
        from earnings_engine.data.swing_scanner import _pool as swing_pool, load_swing_pool_from_db
        from earnings_engine.data.breakout_scanner import _pool as breakout_pool, load_breakout_pool_from_db

        # Ensure pools are hydrated
        if not swing_pool.get("hot") and not swing_pool.get("warm"):
            load_swing_pool_from_db(settings)
        if not breakout_pool.get("hot") and not breakout_pool.get("warm") and not breakout_pool.get("candidates"):
            load_breakout_pool_from_db(settings)

        candidates = set()
        candidates.update(swing_pool.get("hot", {}).keys())
        candidates.update(swing_pool.get("warm", {}).keys())

        # Extract tickers from breakout pool keys (sym::strategy)
        for k in breakout_pool.get("hot", {}).keys():
            candidates.add(k.split("::")[0])
        for k in breakout_pool.get("warm", {}).keys():
            candidates.add(k.split("::")[0])
        for r in breakout_pool.get("candidates", []):
            if r.get("ticker"):
                candidates.add(str(r["ticker"]).upper().strip())

        # Also pull top setups from breakout_radar and swing_radar DB
        conn = get_db_connection(settings)
        _init_confluence_db(conn)

        try:
            b_rows = conn.execute("SELECT DISTINCT ticker FROM breakout_radar WHERE tier IN ('HOT', 'WARM')").fetchall()
            for r in b_rows:
                if r and r[0]:
                    candidates.add(str(r[0]).upper().strip())
            s_rows = conn.execute("SELECT DISTINCT ticker FROM swing_radar WHERE tier IN ('HOT', 'WARM')").fetchall()
            for r in s_rows:
                if r and r[0]:
                    candidates.add(str(r[0]).upper().strip())
        except Exception:
            pass

        confluence_list: list[dict[str, Any]] = []
        now_str = datetime.now(timezone.utc).isoformat()

        for ticker in candidates:
            if not ticker or "TEST" in ticker or "MOCK" in ticker:
                continue
            c = get_stock_confluence(ticker, settings=settings)
            
            # Augment with pricing & scoring metadata
            comp_score = 0.0
            cur_p = None
            sig_p = None
            targ_p = None
            stop_l = None
            rrr = None
            co_name = ticker
            ind = "General"

            # Check breakout details
            try:
                b_row = conn.execute(
                    "SELECT company_name, industry, current_price, signal_price, target_price, stop_loss, risk_reward_ratio, composite_score FROM breakout_radar WHERE ticker = ? ORDER BY composite_score DESC LIMIT 1",
                    (ticker,),
                ).fetchone()
                if b_row:
                    co_name = b_row[0] or co_name
                    ind = b_row[1] or ind
                    cur_p = float(b_row[2]) if b_row[2] is not None else None
                    sig_p = float(b_row[3]) if b_row[3] is not None else None
                    targ_p = float(b_row[4]) if b_row[4] is not None else None
                    stop_l = float(b_row[5]) if b_row[5] is not None else None
                    rrr = float(b_row[6]) if b_row[6] is not None else None
                    comp_score = max(comp_score, float(b_row[7] or 0))
            except Exception:
                pass

            # Check swing details
            try:
                s_row = conn.execute(
                    "SELECT company_name, industry, current_price, support_level, resistance_level, composite_score FROM swing_radar WHERE ticker = ? LIMIT 1",
                    (ticker,),
                ).fetchone()
                if s_row:
                    co_name = s_row[0] or co_name
                    ind = s_row[1] or ind
                    if cur_p is None and s_row[2] is not None:
                        cur_p = float(s_row[2])
                    if stop_l is None and s_row[3] is not None:
                        stop_l = float(s_row[3])
                    if targ_p is None and s_row[4] is not None:
                        targ_p = float(s_row[4])
                    comp_score = max(comp_score, float(s_row[5] or 0))
            except Exception:
                pass

            c["company_name"] = co_name
            c["industry"] = ind
            c["current_price"] = cur_p
            c["signal_price"] = sig_p or cur_p
            c["target_price"] = targ_p
            c["stop_loss"] = stop_l
            c["risk_reward_ratio"] = rrr
            c["composite_score"] = comp_score
            c["scanned_at"] = now_str

            confluence_list.append(c)

        confluence_list.sort(
            key=lambda x: (x.get("confluence_level", 0), x.get("composite_score", 0)),
            reverse=True,
        )

        # Batch insert/update into confluence_radar table
        insert_rows = []
        for c in confluence_list:
            insert_rows.append((
                c["ticker"], c.get("company_name"), c.get("industry"),
                int(c.get("confluence_level", 0)), c.get("confluence_tag"), c.get("confluence_badge"), c.get("badge_color"),
                1 if c.get("is_swing_buy") else 0, 1 if c.get("is_breakout") else 0, 1 if c.get("is_ai_buy") else 0,
                c.get("ai_direction"), float(c.get("ai_strength", 50)),
                c.get("swing_tier"), c.get("breakout_tier"),
                c.get("current_price"), c.get("signal_price"), c.get("target_price"), c.get("stop_loss"), c.get("risk_reward_ratio"),
                float(c.get("composite_score", 0)),
                c.get("synthesis"), json.dumps(c), now_str, now_str, now_str,
            ))

        if insert_rows:
            conn.executemany(
                """
                INSERT INTO confluence_radar (
                    ticker, company_name, industry,
                    confluence_level, confluence_tag, confluence_badge, badge_color,
                    is_swing_buy, is_breakout, is_ai_buy, ai_direction, ai_strength,
                    swing_tier, breakout_tier,
                    current_price, signal_price, target_price, stop_loss, risk_reward_ratio,
                    composite_score, synthesis, data_json, scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    company_name = excluded.company_name,
                    industry = excluded.industry,
                    confluence_level = excluded.confluence_level,
                    confluence_tag = excluded.confluence_tag,
                    confluence_badge = excluded.confluence_badge,
                    badge_color = excluded.badge_color,
                    is_swing_buy = excluded.is_swing_buy,
                    is_breakout = excluded.is_breakout,
                    is_ai_buy = excluded.is_ai_buy,
                    ai_direction = excluded.ai_direction,
                    ai_strength = excluded.ai_strength,
                    swing_tier = excluded.swing_tier,
                    breakout_tier = excluded.breakout_tier,
                    current_price = excluded.current_price,
                    signal_price = excluded.signal_price,
                    target_price = excluded.target_price,
                    stop_loss = excluded.stop_loss,
                    risk_reward_ratio = excluded.risk_reward_ratio,
                    composite_score = excluded.composite_score,
                    synthesis = excluded.synthesis,
                    data_json = excluded.data_json,
                    scanned_at = excluded.scanned_at,
                    updated_at = excluded.updated_at
                """,
                insert_rows,
            )
            conn.commit()
            logger.info("[CONFLUENCE] Saved %d cross-strategy setups to confluence_radar table.", len(insert_rows))

        global _CONFLUENCE_CACHE
        _CONFLUENCE_CACHE = {"ts": time.time(), "data": confluence_list}
        return confluence_list
    except Exception as e:
        logger.warning("[CONFLUENCE] Error in compute_and_save_confluence_radar: %s", e)
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def load_confluence_radar_from_db(
    min_level: int | Settings = 1,
    limit: int = 30,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Instant sub-millisecond loader for pre-computed confluence setups."""
    import json
    import time

    if isinstance(min_level, Settings):
        settings = min_level
        min_level = 1

    try:
        min_level = int(min_level)
    except Exception:
        min_level = 1

    global _CONFLUENCE_CACHE
    now_ts = time.time()

    # Fast in-memory cache check
    if "data" in _CONFLUENCE_CACHE:
        if (now_ts - _CONFLUENCE_CACHE.get("ts", 0)) < _CONFLUENCE_CACHE_TTL:
            cached = _CONFLUENCE_CACHE["data"]
            filtered = [c for c in cached if c.get("confluence_level", 0) >= min_level]
            return filtered[:limit]

    settings = settings or Settings()
    conn = None
    try:
        conn = get_db_connection(settings)
        _init_confluence_db(conn)

        cur = conn.execute(
            """
            SELECT data_json FROM confluence_radar
            WHERE confluence_level >= ?
            ORDER BY confluence_level DESC, composite_score DESC
            LIMIT ?
            """,
            (min_level, limit),
        )
        rows = cur.fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            if r and r[0]:
                try:
                    results.append(json.loads(r[0]))
                except Exception:
                    pass

        if results:
            _CONFLUENCE_CACHE = {"ts": now_ts, "data": results}
            return results

        # If DB is empty, trigger on-demand background run
        return compute_and_save_confluence_radar(settings)[:limit]
    except Exception as e:
        logger.warning("[CONFLUENCE] Error loading confluence radar from DB: %s", e)
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
