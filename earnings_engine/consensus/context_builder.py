"""Context Assembler for AI Consensus Engine.

Collects technical metrics, swing channels, earnings history, and recent
news catalysts into a structured payload for multi-model LLM prompts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger("earnings_engine.consensus.context_builder")


def build_context(ticker: str, timeframe_days: int = 14, settings: Settings | None = None, fetch_live: bool = True) -> dict[str, Any]:
    """Assemble a full standardized context payload for a single ticker on live market data.

    Utilizes the canonical 6-pillar factor standardization engine including
    market sentiment, macro VIX regimes, institutional flows, and fundamentals.
    """
    from earnings_engine.consensus.standard_inputs import build_standardized_model_context

    settings = settings or Settings()
    sym = ticker.strip().upper()

    # Build canonical standardized context
    ctx = build_standardized_model_context(sym, timeframe_days=timeframe_days, settings=settings, fetch_live=fetch_live)

    # Attach backward-compatible keys for existing consumers
    ctx["price_action"] = ctx.get("technical_momentum", {})
    ctx["swing_channel"] = ctx.get("swing_structure", {})
    ctx["earnings"] = ctx.get("earnings_track_record", {})
    ctx["catalysts"] = ctx.get("corporate_catalysts", [])

    return ctx


def context_to_prompt(ctx: dict[str, Any]) -> str:
    """Render a context dict into a standardized markdown prompt string for LLMs."""
    from earnings_engine.consensus.standard_inputs import format_standardized_llm_prompt
    return format_standardized_llm_prompt(ctx)


def build_customized_prompt(
    ticker: str,
    timeframe_days: int = 14,
    include_technicals: bool = True,
    include_news: bool = True,
    include_institutional: bool = True,
    custom_directives: str | None = None,
    settings: Settings | None = None,
    fetch_live: bool = True,
) -> tuple[str, str, dict[str, Any]]:
    """Build a customized system and user prompt for OmniRoute analysis with selective toggles.

    Returns:
        (system_prompt, user_prompt, context_dict)
    """
    from earnings_engine.consensus.model_runner import get_horizon_system_prompt

    settings = settings or Settings()
    sym = ticker.strip().upper()

    ctx = build_context(sym, timeframe_days=timeframe_days, settings=settings, fetch_live=fetch_live)

    # Clean custom directives if blank
    clean_directives = custom_directives.strip() if (custom_directives and custom_directives.strip()) else None

    # 1. System Prompt tailored for horizon & optional directives
    system_prompt = get_horizon_system_prompt(timeframe_days=timeframe_days, custom_directives=clean_directives)

    # 2. Extract context elements
    profile = ctx.get("profile", {})
    company_name = profile.get("company_name", sym.replace(".NS", ""))
    sector = profile.get("sector", "General")
    industry = profile.get("industry", "General")
    timestamp = ctx.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_live = ctx.get("is_live", False)
    live_q = ctx.get("live_quote") or {}

    pa = ctx.get("technical_momentum") or ctx.get("price_action") or {}
    sw = ctx.get("swing_structure") or ctx.get("swing_channel") or {}
    inst = ctx.get("institutional_flows") or {}
    cats = ctx.get("corporate_catalysts") or ctx.get("catalysts") or []

    cmp_val = live_q.get("current_price") or pa.get("current_price") or "N/A"
    curr_prefix = "₹" if sym.endswith(".NS") else "$"

    # 3. Assemble User Prompt Markdown
    lines: list[str] = [
        f"# OmniRoute Market Analysis Context: {sym} ({company_name})",
        f"- **Sector / Industry:** {sector} | {industry}",
        f"- **Timeframe / Horizon:** {timeframe_days} Trading Days",
        f"- **Analysis Timestamp:** {timestamp}",
        f"- **Market Feed Status:** {'🟢 Live Real-Time authoritative Quote' if is_live else '📊 Daily Historical Snapshot'}",
        f"- **Current Price (CMP):** {curr_prefix}{cmp_val}",
        "",
    ]

    # --- Section: Technical Momentum & Price Structure ---
    if include_technicals:
        lines.extend([
            "---",
            "## ⚡ Technical Momentum & Price Structure",
        ])
        # 52W High / Low
        h52 = pa.get("high_52w")
        l52 = pa.get("low_52w")
        p52w_high = pa.get("pct_from_52w_high")
        lines.append(f"- **52-Week Range (52W):** Low {curr_prefix}{l52 or 'N/A'} — High {curr_prefix}{h52 or 'N/A'} (Distance to 52W High: {_fmt_pct(p52w_high)})")

        # Returns
        r7 = pa.get("return_7d")
        r30 = pa.get("return_30d")
        r90 = pa.get("return_90d")
        lines.append(f"- **Multi-Timeframe Returns:** 7D {_fmt_pct(r7)} | 30D {_fmt_pct(r30)} | 90D {_fmt_pct(r90)}")

        # EMAs
        ema20 = pa.get("ema_20")
        ema50 = pa.get("ema_50")
        ema200 = pa.get("ema_200")
        ema_state = pa.get("ema_alignment", "Neutral")
        lines.append(f"- **Moving Averages (EMA):** 20 EMA: {ema20 or 'N/A'}, 50 EMA: {ema50 or 'N/A'}, 200 EMA: {ema200 or 'N/A'} (Alignment: {ema_state})")

        # Volume & ATR
        vol_surge = pa.get("volume_surge_ratio")
        atr_val = pa.get("atr_14") or pa.get("atr")
        lines.append(f"- **Volume Surge Ratio:** {f'{vol_surge:.2f}x' if vol_surge is not None else 'N/A'} vs 20-day average")
        lines.append(f"- **Volatility (ATR):** {curr_prefix}{atr_val or 'N/A'} (14-day Average True Range)")

        # Swing channel support / resistance
        sup = sw.get("support") or sw.get("lower_bound")
        res = sw.get("resistance") or sw.get("upper_bound")
        lines.append(f"- **Swing Range Support / Resistance:** Support {curr_prefix}{sup or 'N/A'} | Resistance {curr_prefix}{res or 'N/A'}")
        lines.append("")

    # --- Section: Institutional & Smart Money Flows ---
    if include_institutional:
        lines.extend([
            "---",
            "## 🏛️ Institutional & Smart Money Flows",
        ])
        mf_delta = inst.get("mf_holding_delta_qoq") or inst.get("dii_change_qoq")
        fii_delta = inst.get("fii_holding_delta_qoq") or inst.get("fii_change_qoq")
        promoter_pct = inst.get("promoter_holding_pct")
        mf_schemes = inst.get("mf_scheme_count")
        lines.append(f"- **Mutual Fund (DII) QoQ Delta:** {_fmt_pct(mf_delta)} (Schemes holding: {mf_schemes or 'N/A'})")
        lines.append(f"- **Foreign Institutional (FII) QoQ Delta:** {_fmt_pct(fii_delta)}")
        lines.append(f"- **Promoter Shareholding:** {f'{promoter_pct:.2f}%' if promoter_pct is not None else 'N/A'}")
        lines.append("")

    # --- Section: Corporate Catalysts & Breaking News ---
    if include_news:
        lines.extend([
            "---",
            "## 📰 Corporate Catalysts & Breaking News",
        ])
        if cats:
            for idx, c in enumerate(cats[:5], start=1):
                title = c.get("title", "Untitled")
                pub = c.get("published_at") or c.get("date") or "Recent"
                impact = c.get("impact_level") or c.get("impact_score") or "Neutral"
                summary = c.get("summary") or ""
                lines.append(f"{idx}. **[{impact}] {title}** ({pub})")
                if summary:
                    lines.append(f"   _{summary[:200]}_")
        else:
            lines.append("No active breaking news catalysts recorded for this symbol.")
        lines.append("")

    # --- Section: Custom Directives ---
    if clean_directives:
        lines.extend([
            "---",
            "## 🎯 Custom Focus & Analysis Directives",
            clean_directives,
            "",
        ])

    # --- Section: Required Output Schema ---
    lines.extend([
        "---",
        "## 📋 Required Prediction Schema",
        "Provide your structured evaluation as a STRICT JSON object in your response:",
        "```json",
        "{",
        '  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",',
        '  "conviction_score": <integer from 0 to 100>,',
        '  "target_price": <expected target price as float>,',
        '  "stop_loss": <invalidation stop loss price as float>,',
        '  "risk_reward_ratio": <calculated risk-to-reward ratio as float, e.g. 2.5>,',
        '  "catalyst_summary": "<concise 1-2 sentence core driver>",',
        '  "thesis": "<detailed 2-3 paragraph trade rationale and technical thesis>",',
        '  "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"]',
        "}",
        "```",
    ])

    user_prompt = "\n".join(lines)
    return system_prompt, user_prompt, ctx


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:+.2f}%"


# ---------------------------------------------------------------------------
# Private data-fetching helpers
# ---------------------------------------------------------------------------

def _build_price_action(ticker: str, settings: Settings, live_quote: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch current price, returns, RSI, EMAs from price history."""
    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM price_history "
            "WHERE ticker = ? ORDER BY date DESC LIMIT 300",
            (ticker,),
        ).fetchall()
        conn.close()

        if not rows:
            if live_quote and live_quote.get("current_price"):
                return {"current_price": live_quote["current_price"]}
            return {}

        # Build DataFrame (rows come newest-first, reverse for chronological)
        data = [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in reversed(rows)]
        df = pd.DataFrame(data)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

        closes = df["close"].dropna()
        if closes.empty:
            if live_quote and live_quote.get("current_price"):
                return {"current_price": live_quote["current_price"]}
            return {}

        # Prioritize live price if provided
        current = float(live_quote.get("current_price")) if (live_quote and live_quote.get("current_price")) else float(closes.iloc[-1])
        result: dict[str, Any] = {"current_price": round(current, 2)}

        # Returns
        if len(closes) >= 5:
            result["return_7d"] = round((current / float(closes.iloc[-min(5, len(closes))]) - 1) * 100, 2)
        if len(closes) >= 22:
            result["return_30d"] = round((current / float(closes.iloc[-min(22, len(closes))]) - 1) * 100, 2)

        # 52W high/low
        year_closes = closes.tail(252)
        high_52w = float(year_closes.max())
        low_52w = float(year_closes.min())
        result["high_52w"] = round(high_52w, 2)
        result["low_52w"] = round(low_52w, 2)
        result["pct_from_52w_high"] = round((current / high_52w - 1) * 100, 2) if high_52w > 0 else None
        result["pct_from_52w_low"] = round((current / low_52w - 1) * 100, 2) if low_52w > 0 else None

        # RSI-14
        if len(closes) >= 15:
            deltas = closes.diff().dropna()
            gains = deltas.clip(lower=0)
            losses = (-deltas.clip(upper=0))
            avg_gain = gains.tail(14).mean()
            avg_loss = losses.tail(14).mean()
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                result["rsi_14"] = round(100 - (100 / (1 + rs)), 1)
            else:
                result["rsi_14"] = 100.0

        # EMAs
        if len(closes) >= 20:
            result["ema_20"] = round(float(closes.ewm(span=20, adjust=False).mean().iloc[-1]), 2)
        if len(closes) >= 50:
            result["ema_50"] = round(float(closes.ewm(span=50, adjust=False).mean().iloc[-1]), 2)
        if len(closes) >= 200:
            result["ema_200"] = round(float(closes.ewm(span=200, adjust=False).mean().iloc[-1]), 2)

        # Average volume
        volumes = df["volume"].dropna().tail(20)
        if not volumes.empty:
            result["avg_volume_20d"] = int(volumes.mean())

        return result

    except Exception as e:
        logger.warning("Failed to build price action for %s: %s", ticker, e)
        return {}


def _build_swing_channel(ticker: str, settings: Settings) -> dict[str, Any]:
    """Get swing channel data from price history."""
    try:
        from earnings_engine.data.market_context import detect_swing_range

        conn = get_db_connection(settings)
        rows = conn.execute(
            "SELECT date, close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 80",
            (ticker,),
        ).fetchall()
        conn.close()

        if not rows:
            return {}

        # Filter out rows where close is None/NULL
        valid_rows = [(r[0], r[1]) for r in reversed(rows) if r[1] is not None]
        if not valid_rows:
            return {}

        closes = pd.Series(
            [float(r[1]) for r in valid_rows],
            index=pd.to_datetime([r[0] for r in valid_rows]),
        )
        swing = detect_swing_range(closes)

        # Compute position in channel (0% = at support, 100% = at resistance)
        if swing.get("lower") and swing.get("upper") and swing["upper"] > swing["lower"]:
            current = float(closes.iloc[-1])
            position = (current - swing["lower"]) / (swing["upper"] - swing["lower"]) * 100
            swing["position_in_channel"] = round(min(max(position, 0), 100), 1)

        return swing

    except Exception as e:
        logger.warning("Failed to build swing channel for %s: %s", ticker, e)
        return {}


def _build_earnings_context(
    ticker: str,
    settings: Settings,
    preloaded_prices: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Get earnings history, days to next, and post-earnings moves."""
    result: dict[str, Any] = {}
    try:
        conn = get_db_connection(settings)

        # Past earnings with surprises
        rows = conn.execute(
            "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct "
            "FROM earnings_history WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 6",
            (ticker,),
        ).fetchall()

        if rows:
            past_surprises = []
            for i, r in enumerate(rows[:3]):
                past_surprises.append({
                    "quarter": i + 1,
                    "date": r[0],
                    "eps_estimate": r[1],
                    "eps_reported": r[2],
                    "surprise_pct": r[3],
                })
            result["past_surprises"] = past_surprises

            # Days to next earnings (find the nearest future earnings date)
            today = datetime.now().date()
            for r in rows:
                try:
                    ed = datetime.strptime(r[0][:10], "%Y-%m-%d").date()
                    if ed >= today:
                        result["days_to_next"] = (ed - today).days
                        result["next_earnings_date"] = r[0][:10]
                        break
                except (ValueError, TypeError):
                    continue

            # Post-earnings 7D moves from price history (using in-memory slice where available)
            post_moves = []
            earliest_date = min((r[0][:10] for r in rows[:3]), default=None)
            pdf = preloaded_prices
            if pdf is None and earliest_date:
                try:
                    from earnings_engine.data.prices import load_prices
                    pdf = load_prices(ticker, settings, since_date=earliest_date)
                except Exception:
                    pdf = None

            for r in rows[:3]:
                try:
                    ed = r[0][:10]
                    if pdf is not None and not pdf.empty:
                        ed_ts = pd.Timestamp(ed)
                        sub = pdf.loc[pdf.index >= ed_ts]
                        if len(sub) >= 2:
                            base = float(sub.iloc[0]["close"])
                            end_slice = sub.head(8)
                            end = float(end_slice.iloc[-1]["close"])
                            if base > 0:
                                move = (end / base - 1) * 100
                                post_moves.append({"date": ed, "move_pct": round(move, 2)})
                    else:
                        price_rows = conn.execute(
                            "SELECT close FROM price_history WHERE ticker = ? AND date >= ? ORDER BY date LIMIT 8",
                            (ticker, ed),
                        ).fetchall()
                        if len(price_rows) >= 2:
                            base = float(price_rows[0][0])
                            end = float(price_rows[-1][0])
                            if base > 0:
                                move = (end / base - 1) * 100
                                post_moves.append({"date": ed, "move_pct": round(move, 2)})
                except Exception:
                    continue
            if post_moves:
                result["post_earnings_moves"] = post_moves

        conn.close()
    except Exception as e:
        logger.warning("Failed to build earnings context for %s: %s", ticker, e)

    return result


def _build_catalysts(ticker: str, settings: Settings) -> list[dict[str, Any]]:
    """Get top 5 recent news catalysts from the database."""
    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            "SELECT title, category, direction, impact_score, impact_level, published_at, summary "
            "FROM news_catalysts WHERE ticker = ? ORDER BY published_at DESC, impact_score DESC LIMIT 5",
            (ticker,),
        ).fetchall()
        conn.close()

        return [
            {
                "title": r[0],
                "category": r[1],
                "direction": r[2],
                "impact_score": r[3],
                "impact_level": r[4],
                "published_at": r[5],
                "summary": r[6],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Failed to build catalysts for %s: %s", ticker, e)
        return []
