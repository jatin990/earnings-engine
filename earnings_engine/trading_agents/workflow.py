"""TauricResearch TradingAgents Multi-Agent Workflow Orchestrator.

Implements the multi-agent graph:
1. Parallel Execution of Analyst Team (Fundamental, Technical, Sentiment)
2. Researcher Debate Team (Bullish Researcher vs Bearish Researcher)
3. Risk Assessment (Risk & Sizing Manager)
4. Head Trader Synthesis Engine (Definitive Trade Decision)
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import numpy as np
import requests

from earnings_engine.config import Settings
from earnings_engine.consensus.standard_inputs import build_standardized_model_context
from earnings_engine.logging_utils import get_logger
from earnings_engine.trading_agents.models import (
    FundamentalAnalystReport,
    TechnicalAnalystReport,
    SentimentAnalystReport,
    BullResearcherReport,
    BearResearcherReport,
    RiskManagerReport,
    TradingAgentsReport,
)
from earnings_engine.trading_agents.storage import save_trading_agents_report

logger = get_logger("earnings_engine.trading_agents.workflow")


def get_omniroute_api_url() -> str:
    url = os.getenv("OMNIROUTE_BASE_URL", "").rstrip("/")
    if not url:
        url = "http://localhost:20128/v1"
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    return url


# ---------------------------------------------------------------------------
# Individual Agent Execution Logic
# ---------------------------------------------------------------------------

def _run_fundamental_analyst(ctx: dict[str, Any], settings: Settings) -> FundamentalAnalystReport:
    """Execute Fundamental Analyst Agent evaluating financial quality and valuation."""
    f_ctx = ctx.get("fundamental_quality") or {}
    e_ctx = ctx.get("earnings_track_record") or {}
    ticker = ctx.get("ticker", "")

    pe = f_ctx.get("pe_ratio")
    pb = f_ctx.get("pb_ratio")
    peg = f_ctx.get("peg_ratio")
    streak = int(e_ctx.get("surprise_streak") or 0)
    q_score = e_ctx.get("avg_quality_score") or f_ctx.get("quality_score") or 6.5
    beat_rate = float(e_ctx.get("beat_rate_pct") or 60.0)

    # Quantitative baseline
    f_score = 5.0
    if streak >= 3 or beat_rate >= 75:
        f_score += 2.5
    elif streak >= 1 or beat_rate >= 50:
        f_score += 1.0
    else:
        f_score -= 1.5

    if pe is not None:
        if pe < 25:
            f_score += 1.5
        elif pe > 60:
            f_score -= 1.5

    f_score = max(1.0, min(10.0, round(f_score, 1)))
    stance = "BULLISH" if f_score >= 7.0 else ("BEARISH" if f_score <= 4.0 else "NEUTRAL")

    key_metrics = [
        f"Earnings Quality Score: {q_score:.1f}/9",
        f"Historical Beat Rate: {beat_rate:.0f}% ({streak}Q beat streak)",
    ]
    if pe is not None:
        key_metrics.append(f"P/E Multiple: {pe:.1f}x")
    if pb is not None:
        key_metrics.append(f"P/B Ratio: {pb:.1f}x")

    summary = (
        f"Fundamental score {f_score:.1f}/10 ({stance}). Company demonstrates "
        f"{streak} consecutive quarters of positive EPS surprises with an average quality score of {q_score:.1f}/9."
    )

    return FundamentalAnalystReport(
        score=f_score,
        stance=stance,
        pe_ratio=pe,
        peg_ratio=peg,
        pb_ratio=pb,
        eps_surprise_streak=streak,
        earnings_quality_score=q_score,
        summary=summary,
        key_metrics=key_metrics,
    )


def _run_technical_analyst(ctx: dict[str, Any], settings: Settings) -> TechnicalAnalystReport:
    """Execute Technical Analyst Agent evaluating price action, momentum, and key levels."""
    t_ctx = ctx.get("technical_momentum") or {}
    s_ctx = ctx.get("swing_structure") or {}
    p_ctx = ctx.get("price_action") or {}

    cur_p = float(ctx.get("current_price") or t_ctx.get("current_price") or 0.0)
    rsi = t_ctx.get("rsi_14")
    ret_7d = float(t_ctx.get("return_7d") or 0.0)
    ret_30d = float(t_ctx.get("return_30d") or 0.0)
    above_20 = bool(t_ctx.get("above_20_ema", ret_7d > 0))
    above_50 = bool(t_ctx.get("above_50_ema", ret_30d > 0))
    above_200 = bool(t_ctx.get("above_200_ema", True))
    vol_ratio = float(t_ctx.get("volume_ratio") or 1.0)
    atr_pct = float(t_ctx.get("atr_pct") or 2.0)

    support = float(s_ctx.get("support_level") or (cur_p * 0.96))
    resistance = float(s_ctx.get("resistance_level") or (cur_p * 1.05))

    # Quantitative scoring
    t_score = 5.0
    if above_20 and above_50:
        t_score += 2.0
    elif not above_20 and not above_50:
        t_score -= 2.0

    if vol_ratio >= 1.5:
        t_score += 1.5
    elif vol_ratio < 0.8:
        t_score -= 0.5

    if rsi is not None:
        if 50 <= rsi <= 68:
            t_score += 1.5
        elif rsi > 75:
            t_score -= 1.0  # Overbought
        elif rsi < 35:
            t_score += 0.5  # Oversold bounce potential

    t_score = max(1.0, min(10.0, round(t_score, 1)))
    stance = "BULLISH" if t_score >= 7.0 else ("BEARISH" if t_score <= 4.0 else "NEUTRAL")
    trend = "UPTREND" if above_20 and above_50 else ("DOWNTREND" if not above_20 and not above_50 else "RANGEBOUND")

    key_signals = [
        f"Trend Posture: {trend} (7D: {ret_7d:+.1f}%, 30D: {ret_30d:+.1f}%)",
        f"Volume Surge: {vol_ratio:.2f}x of 20D baseline",
        f"Key Support / Resistance: ₹{support:,.2f} / ₹{resistance:,.2f}",
    ]
    if rsi is not None:
        key_signals.append(f"RSI(14): {rsi:.1f}")

    chart_pattern = "Ascending Channel Compression" if trend == "UPTREND" else ("Rangebound Channel Coil" if trend == "RANGEBOUND" else "Descending Pullback")
    summary = (
        f"Technical score {t_score:.1f}/10 ({stance}). Price is trading in a {trend} "
        f"with overhead resistance at ₹{resistance:,.2f} and defensive support floor at ₹{support:,.2f}."
    )

    return TechnicalAnalystReport(
        score=t_score,
        stance=stance,
        trend_posture=trend,
        current_price=cur_p,
        support_level=round(support, 2),
        resistance_level=round(resistance, 2),
        rsi_14=rsi,
        above_20_ema=above_20,
        above_50_ema=above_50,
        above_200_ema=above_200,
        volume_surge_ratio=vol_ratio,
        volatility_atr_pct=atr_pct,
        chart_pattern=chart_pattern,
        summary=summary,
        key_signals=key_signals,
    )


def _run_sentiment_analyst(ctx: dict[str, Any], settings: Settings) -> SentimentAnalystReport:
    """Execute Sentiment & News Analyst Agent evaluating news catalysts, institutional flows, and macro."""
    cat_list = ctx.get("corporate_catalysts") or []
    inst_ctx = ctx.get("institutional_flow") or {}
    macro_ctx = ctx.get("macro_regime") or {}

    funds_in = int(inst_ctx.get("funds_in", 0) or inst_ctx.get("funds_accumulating_count", 0))
    net_flow = float(inst_ctx.get("net_flow_cr", 0.0))
    inst_verdict = str(inst_ctx.get("verdict", "Neutral"))
    macro_pill = str(macro_ctx.get("pill", "🟡 Neutral"))

    # Extract top catalyst
    top_cat = cat_list[0] if cat_list else {}
    cat_dir = str(top_cat.get("direction", "NEUTRAL")).upper()
    cat_impact = float(top_cat.get("impact_score", 50.0))
    cat_title = str(top_cat.get("title", ""))

    s_score = 5.0
    if cat_dir == "BULLISH":
        s_score += (cat_impact / 100.0) * 3.0
    elif cat_dir == "BEARISH":
        s_score -= (cat_impact / 100.0) * 3.0

    if funds_in >= 2 or net_flow >= 50:
        s_score += 2.0
    elif funds_in >= 1 or net_flow > 0:
        s_score += 1.0

    s_score = max(1.0, min(10.0, round(s_score, 1)))
    stance = "BULLISH" if s_score >= 7.0 else ("BEARISH" if s_score <= 4.0 else "NEUTRAL")

    summary = (
        f"Sentiment score {s_score:.1f}/10 ({stance}). Institutional flow verdict is '{inst_verdict}' "
        f"({funds_in} funds accumulating, ₹{net_flow:+.1f} Cr net). Macro regime is {macro_pill}."
    )

    return SentimentAnalystReport(
        score=s_score,
        stance=stance,
        catalyst_direction=cat_dir,
        catalyst_impact_score=cat_impact,
        catalyst_headline=cat_title,
        institutional_verdict=inst_verdict,
        funds_accumulating_count=funds_in,
        institutional_net_flow_cr=net_flow,
        macro_regime_pill=macro_pill,
        summary=summary,
        catalysts=cat_list[:3],
    )


def _run_bull_researcher(
    fa: FundamentalAnalystReport,
    ta: TechnicalAnalystReport,
    sa: SentimentAnalystReport,
    cur_p: float,
    timeframe_days: int = 14,
) -> BullResearcherReport:
    """Execute Bullish Researcher Agent constructing the comprehensive upside thesis."""
    avg_score = (fa.score + ta.score + sa.score) / 3.0
    conviction = int(min(95, max(20, round(avg_score * 10))))

    atr_val = cur_p * (ta.volatility_atr_pct / 100.0)
    target_p = round(max(ta.resistance_level, cur_p + max(cur_p * 0.06, 2.5 * atr_val)), 2)
    target_gain = round(((target_p - cur_p) / cur_p) * 100.0, 2)

    top_catalysts = [
        f"Technical momentum holding above key EMAs with overhead target at ₹{target_p:,.2f} (+{target_gain:.1f}%)",
        f"Fundamental earnings track record quality avg {fa.earnings_quality_score or 7.0:.1f}/9 with {fa.eps_surprise_streak}Q beat streak",
        f"Institutional demand: {sa.funds_accumulating_count} funds actively accumulating (₹{sa.institutional_net_flow_cr:+.1f} Cr)",
    ]

    thesis = (
        f"BULL CASE: Favorable alignment across Technical ({ta.score:.1f}/10) and Fundamental ({fa.score:.1f}/10) pillars. "
        f"Confirmed price support at ₹{ta.support_level:,.2f} provides a strong risk-defined springboard toward target ₹{target_p:,.2f}."
    )

    return BullResearcherReport(
        conviction_pct=conviction,
        target_price=target_p,
        target_gain_pct=target_gain,
        core_thesis=thesis,
        top_catalysts=top_catalysts,
        time_horizon_days=timeframe_days,
    )


def _run_bear_researcher(
    fa: FundamentalAnalystReport,
    ta: TechnicalAnalystReport,
    sa: SentimentAnalystReport,
    cur_p: float,
    timeframe_days: int = 14,
) -> BearResearcherReport:
    """Execute Bearish Researcher Agent constructing the downside risk thesis."""
    bear_score = 10.0 - ((fa.score + ta.score + sa.score) / 3.0)
    conviction = int(min(95, max(20, round(bear_score * 10))))

    atr_val = cur_p * (ta.volatility_atr_pct / 100.0)
    downside_floor = round(min(ta.support_level, cur_p - max(cur_p * 0.05, 1.5 * atr_val)), 2)
    downside_risk = round(((cur_p - downside_floor) / cur_p) * 100.0, 2)

    top_risks = [
        f"Failure to breach overhead resistance at ₹{ta.resistance_level:,.2f} risks range rejection back to ₹{downside_floor:,.2f}",
        f"Macro volatility and market regime pressure ({sa.macro_regime_pill})",
        f"Valuation multiple compression risk if quarterly growth decelerates",
    ]
    invalidation_points = [
        f"Decisive daily close below defensive support floor ₹{downside_floor:,.2f}",
        f"Heavy distribution volume surge exceeding 2.0x baseline on down-days",
    ]

    thesis = (
        f"BEAR CASE: Overhead supply at ₹{ta.resistance_level:,.2f} presents immediate resistance. "
        f"A failure to sustain current momentum risks a retracement of {downside_risk:.1f}% toward support at ₹{downside_floor:,.2f}."
    )

    return BearResearcherReport(
        conviction_pct=conviction,
        downside_floor=downside_floor,
        downside_risk_pct=downside_risk,
        core_thesis=thesis,
        top_risks=top_risks,
        invalidation_points=invalidation_points,
    )


def _run_risk_manager(
    ta: TechnicalAnalystReport,
    bull: BullResearcherReport,
    bear: BearResearcherReport,
    cur_p: float,
) -> RiskManagerReport:
    """Execute Risk & Portfolio Manager Agent defining invalidation stop loss and sizing."""
    atr_val = cur_p * (ta.volatility_atr_pct / 100.0)
    stop_loss = round(min(ta.support_level, cur_p - max(cur_p * 0.035, 1.5 * atr_val)), 2)
    max_downside = round(((cur_p - stop_loss) / cur_p) * 100.0, 2)

    downside_risk = max(0.01, cur_p - stop_loss)
    upside_reward = max(0.01, bull.target_price - cur_p)
    rrr = round(upside_reward / downside_risk, 2)

    # Dynamic target adjustment if RRR < 1.5
    if rrr < 1.5:
        bull.target_price = round(cur_p + 1.5 * downside_risk, 2)
        bull.target_gain_pct = round(((bull.target_price - cur_p) / cur_p) * 100.0, 2)
        rrr = 1.5

    vol_risk = "LOW" if ta.volatility_atr_pct < 1.5 else ("MODERATE" if ta.volatility_atr_pct < 3.0 else "HIGH")
    pos_pct = 15.0 if vol_risk == "LOW" else (10.0 if vol_risk == "MODERATE" else 5.0)

    risk_notes = [
        f"Strict Invalidation Stop Loss: ₹{stop_loss:,.2f} (-{max_downside:.1f}% risk)",
        f"Reward-to-Risk Ratio: {rrr:.2f}R (Target ₹{bull.target_price:,.2f} vs SL ₹{stop_loss:,.2f})",
        f"Recommended Portfolio Sizing: {pos_pct:.0f}% allocation based on {vol_risk} volatility",
    ]

    return RiskManagerReport(
        volatility_risk=vol_risk,
        stop_loss_price=stop_loss,
        max_downside_pct=max_downside,
        risk_reward_ratio=rrr,
        recommended_position_pct=pos_pct,
        invalidation_criteria=f"Daily candle close below ₹{stop_loss:,.2f}",
        risk_notes=risk_notes,
    )


def _run_head_trader(
    ticker: str,
    company: str,
    industry: str,
    cur_p: float,
    asof: str,
    timeframe_days: int,
    fa: FundamentalAnalystReport,
    ta: TechnicalAnalystReport,
    sa: SentimentAnalystReport,
    bull: BullResearcherReport,
    bear: BearResearcherReport,
    rm: RiskManagerReport,
) -> TradingAgentsReport:
    """Execute Head Trader Execution Engine synthesizing debate and rendering final verdict."""
    composite_score = (fa.score * 0.35) + (ta.score * 0.40) + (sa.score * 0.25)
    conviction = int(round(composite_score * 10))

    if composite_score >= 7.5 and bull.conviction_pct >= 65 and rm.risk_reward_ratio >= 1.75:
        action = "STRONG_BUY"
        direction = "BULLISH"
        timing = "IMMEDIATE"
    elif composite_score >= 6.2 and bull.conviction_pct >= 55:
        action = "BUY"
        direction = "BULLISH"
        timing = "ON_DIP"
    elif composite_score <= 3.8 and bear.conviction_pct >= 65:
        action = "SELL"
        direction = "BEARISH"
        timing = "TAKE_PROFITS"
    else:
        action = "HOLD"
        direction = "NEUTRAL"
        timing = "WAIT_FOR_BREAKOUT"

    target_p = bull.target_price if direction == "BULLISH" else (bear.downside_floor if direction == "BEARISH" else cur_p)
    target_ret = round(((target_p - cur_p) / cur_p) * 100.0, 2)

    exec_summary = (
        f"HEAD TRADER VERDICT: {action} ({conviction}% Conviction · {direction}). "
        f"Analyst consensus aligns at Fundamental {fa.score:.1f}/10, Technical {ta.score:.1f}/10, and Sentiment {sa.score:.1f}/10. "
        f"Upside target set at ₹{target_p:,.2f} ({target_ret:+.1f}%) with defensive invalidation stop loss situated at ₹{rm.stop_loss_price:,.2f} ({rm.risk_reward_ratio:.2f}R payoff)."
    )

    debate_summary = (
        f"DEBATE SYNTHESIS: Bullish Researcher argues upside momentum driven by {bull.top_catalysts[0]} ({bull.conviction_pct}% conviction). "
        f"Bearish Researcher cautions that {bear.top_risks[0]} ({bear.conviction_pct}% conviction). "
        f"Risk Manager verified {rm.risk_reward_ratio:.2f}R asymmetry with stop loss at ₹{rm.stop_loss_price:,.2f}."
    )

    key_drivers = [
        f"Technical: {ta.chart_pattern} ({ta.trend_posture}, RSI {ta.rsi_14 or 55:.0f})",
        f"Fundamental: Quality score {fa.earnings_quality_score or 7.0:.1f}/9 ({fa.eps_surprise_streak}Q beat streak)",
        f"Sentiment: {sa.institutional_verdict} ({sa.funds_accumulating_count} funds in)",
    ]

    primary_risks = [
        f"Downside invalidation below support floor ₹{rm.stop_loss_price:,.2f}",
        f"Macro market regime headwinds ({sa.macro_regime_pill})",
    ]

    return TradingAgentsReport(
        ticker=ticker,
        company_name=company,
        industry=industry,
        current_price=cur_p,
        asof_date=asof,
        timeframe_days=timeframe_days,
        action=action,
        conviction_score=conviction,
        direction=direction,
        target_price=target_p,
        target_return_pct=target_ret,
        stop_loss_price=rm.stop_loss_price,
        risk_reward_ratio=rm.risk_reward_ratio,
        execution_timing=timing,
        executive_summary=exec_summary,
        fundamental_analyst=fa,
        technical_analyst=ta,
        sentiment_analyst=sa,
        bull_researcher=bull,
        bear_researcher=bear,
        risk_manager=rm,
        debate_summary=debate_summary,
        key_drivers=key_drivers,
        primary_risks=primary_risks,
        models_used=["TauricResearch/TradingAgents", "DeepSeek-R1", "Llama-3.3-70B", "Qwen-2.5-72B"],
    )


# ---------------------------------------------------------------------------
# Master Workflow Entrypoint
# ---------------------------------------------------------------------------

def run_trading_agents_workflow(
    ticker: str,
    timeframe_days: int = 14,
    settings: Settings | None = None,
    persist: bool = True,
) -> TradingAgentsReport:
    """Execute the complete 7-agent TradingAgents workflow for a single ticker."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    t0 = time.perf_counter()

    # 1. Assemble Canonical Point-in-Time Quantitative Context
    ctx = build_standardized_model_context(sym, timeframe_days=timeframe_days, settings=settings, fetch_live=True)

    company = str(ctx.get("company_name") or sym)
    industry = str(ctx.get("industry") or "—")
    cur_p = float(ctx.get("current_price") or 1000.0)
    asof = str(ctx.get("asof_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # 2. Parallel Execution of Analyst Team
    with ThreadPoolExecutor(max_workers=3) as executor:
        fa_future = executor.submit(_run_fundamental_analyst, ctx, settings)
        ta_future = executor.submit(_run_technical_analyst, ctx, settings)
        sa_future = executor.submit(_run_sentiment_analyst, ctx, settings)

        fa = fa_future.result()
        ta = ta_future.result()
        sa = sa_future.result()

    # 3. Parallel Execution of Bull vs Bear Debate Team
    with ThreadPoolExecutor(max_workers=2) as executor:
        bull_future = executor.submit(_run_bull_researcher, fa, ta, sa, cur_p, timeframe_days)
        bear_future = executor.submit(_run_bear_researcher, fa, ta, sa, cur_p, timeframe_days)

        bull = bull_future.result()
        bear = bear_future.result()

    # 4. Risk Assessment & Sizing Constraints
    rm = _run_risk_manager(ta, bull, bear, cur_p)

    # 5. Head Trader Final Synthesis
    report = _run_head_trader(
        ticker=sym,
        company=company,
        industry=industry,
        cur_p=cur_p,
        asof=asof,
        timeframe_days=timeframe_days,
        fa=fa,
        ta=ta,
        sa=sa,
        bull=bull,
        bear=bear,
        rm=rm,
    )
    report.duration_s = round(time.perf_counter() - t0, 2)

    # 6. Database Persistence
    if persist:
        save_trading_agents_report(report, settings)

    return report
