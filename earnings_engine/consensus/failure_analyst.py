"""AI Failure Attribution & Post-Mortem Diagnostic Engine.

Analyzes settled predictions that resulted in FAILURE or PARTIAL success,
diagnosing why the multi-model consensus failed using price trajectories,
earnings results, and breaking news catalysts during the evaluation window.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger("earnings_engine.consensus.failure_analyst")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
POST_MORTEM_MODEL = "deepseek/deepseek-r1"

VALID_FAILURE_CATEGORIES = [
    "EARNINGS_MISS_GUIDANCE_DOWN",
    "MACRO_MARKET_CORRECTION",
    "SECTOR_ROTATION",
    "FALSE_TECHNICAL_BREAKOUT",
    "UNEXPECTED_CATALYST_EVENT",
    "OVERESTIMATED_MOMENTUM",
]

POST_MORTEM_SYSTEM_PROMPT = """You are a senior quantitative risk manager and post-mortem trading analyst.
A multi-model consensus prediction failed or underperformed its target.
Analyze the provided trade context, actual price trajectory, and post-prediction news/events.

Diagnose the root cause of failure and return STRICT JSON with exactly:
{
  "failure_category": "<ONE OF: EARNINGS_MISS_GUIDANCE_DOWN | MACRO_MARKET_CORRECTION | SECTOR_ROTATION | FALSE_TECHNICAL_BREAKOUT | UNEXPECTED_CATALYST_EVENT | OVERESTIMATED_MOMENTUM>",
  "summary": "<1-line concise summary of why the prediction failed>",
  "detailed_analysis": "<Detailed multi-paragraph diagnostic explaining what the models missed and what drove the price>",
  "learning_lesson": "<Concrete takeaway for future model prompt weighting and risk filters>"
}

Rules:
- Output ONLY valid JSON. No markdown code blocks, no preamble.
- Pick exactly one failure_category from the allowed list.
- Be objective and specific to the stock and events provided."""


def diagnose_failure(
    prediction: dict[str, Any],
    actual_exit_price: float,
    actual_return_pct: float,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run an AI post-mortem diagnostic on a failed or partial prediction.

    Args:
        prediction: Full prediction record from consensus_predictions.
        actual_exit_price: Final settlement price.
        actual_return_pct: Actual return achieved.
        settings: Optional Settings instance.

    Returns:
        Dict with failure_category, summary, detailed_analysis, learning_lesson.
    """
    settings = settings or Settings()
    ticker = prediction.get("ticker", "UNKNOWN")
    created_at = str(prediction.get("created_at", ""))[:10]
    eval_date = str(prediction.get("evaluation_date", ""))[:10]

    # Gather window context (news catalysts & price history during trade)
    window_news = _get_news_during_window(ticker, created_at, eval_date, settings)
    trajectory = _get_price_trajectory(ticker, created_at, eval_date, settings)

    prompt = _build_post_mortem_prompt(
        prediction=prediction,
        actual_exit_price=actual_exit_price,
        actual_return_pct=actual_return_pct,
        trajectory=trajectory,
        news=window_news,
    )

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        logger.warning("[POST-MORTEM] OPENROUTER_API_KEY not found. Using heuristic failure classification.")
        return _heuristic_failure_analysis(prediction, actual_return_pct)

    try:
        resp = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://earnings-engine.local",
                "X-Title": "Earnings Engine Post-Mortem",
            },
            json={
                "model": POST_MORTEM_MODEL,
                "messages": [
                    {"role": "system", "content": POST_MORTEM_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1200,
            },
            timeout=60,
        )

        if resp.status_code == 200:
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = _parse_post_mortem_json(content)
            if parsed and parsed.get("failure_category"):
                # Validate failure category
                cat = parsed["failure_category"].strip().upper()
                if cat not in VALID_FAILURE_CATEGORIES:
                    cat = "FALSE_TECHNICAL_BREAKOUT"
                parsed["failure_category"] = cat
                return parsed
        else:
            logger.warning("[POST-MORTEM] LLM HTTP error %d: %s", resp.status_code, resp.text[:200])

    except Exception as e:
        logger.error("[POST-MORTEM] Error during post-mortem diagnosis for %s: %s", ticker, e)

    return _heuristic_failure_analysis(prediction, actual_return_pct)


def _build_post_mortem_prompt(
    prediction: dict[str, Any],
    actual_exit_price: float,
    actual_return_pct: float,
    trajectory: dict[str, Any],
    news: list[dict[str, Any]],
) -> str:
    """Format the post-mortem diagnostic prompt."""
    ticker = prediction.get("ticker", "UNKNOWN")
    as_of = prediction.get("as_of_price", 0.0)
    target = prediction.get("consensus_target_price", 0.0)
    exp_return = prediction.get("consensus_return_pct", 0.0)
    direction = prediction.get("consensus_direction", "NEUTRAL")
    strength = prediction.get("consensus_strength", 0.0)
    thesis = prediction.get("synthesized_thesis", "N/A")

    lines = [
        f"# Post-Mortem Trade Failure Analysis: {ticker}",
        f"- **Consensus Prediction:** {direction} (Strength: {strength:.0f}%, Target Return: {exp_return:+.2f}%)",
        f"- **Entry Price:** ₹{as_of:.2f} | **Target Price:** ₹{target:.2f}",
        f"- **Actual Exit Price:** ₹{actual_exit_price:.2f} | **Actual Return:** {actual_return_pct:+.2f}%",
        f"- **Original Thesis:** {thesis}",
        "",
        "## Price Trajectory During Evaluation Window",
        f"- **Max Drawdown in Window:** {trajectory.get('max_drawdown_pct', 'N/A')}%",
        f"- **Peak Move in Window:** {trajectory.get('peak_move_pct', 'N/A')}%",
        f"- **Volatility / Spread:** {trajectory.get('spread_pct', 'N/A')}%",
        "",
        "## News & Catalysts Published During Evaluation Window",
    ]

    if news:
        for i, n in enumerate(news[:6], 1):
            lines.append(f"{i}. [{n.get('published_at', '')}] ({n.get('direction', 'NEUTRAL')}) {n.get('title', '')}")
            if n.get("summary"):
                lines.append(f"   Summary: {n.get('summary')}")
    else:
        lines.append("- No significant news headlines captured during this window.")

    lines.append("\nDiagnose why this consensus trade failed or underperformed.")
    return "\n".join(lines)


def _get_news_during_window(ticker: str, start_date: str, end_date: str, settings: Settings) -> list[dict[str, Any]]:
    """Fetch news published between prediction creation and evaluation."""
    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            """
            SELECT title, category, direction, impact_score, published_at, summary
            FROM news_catalysts
            WHERE ticker = ? AND published_at >= ? AND published_at <= ?
            ORDER BY published_at DESC, impact_score DESC LIMIT 10
            """,
            (ticker, start_date, end_date),
        ).fetchall()
        conn.close()
        return [
            {
                "title": r[0],
                "category": r[1],
                "direction": r[2],
                "impact_score": r[3],
                "published_at": r[4],
                "summary": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug("Failed to query news during window: %s", e)
        return []


def _get_price_trajectory(ticker: str, start_date: str, end_date: str, settings: Settings) -> dict[str, Any]:
    """Calculate trajectory metrics (max drawdown, peak move) during window."""
    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            "SELECT date, close, high, low FROM price_history WHERE ticker = ? AND date >= ? AND date <= ? ORDER BY date",
            (ticker, start_date, end_date),
        ).fetchall()
        conn.close()

        if not rows:
            return {}

        closes = [float(r[1]) for r in rows if r[1] is not None]
        highs = [float(r[2]) for r in rows if r[2] is not None]
        lows = [float(r[3]) for r in rows if r[3] is not None]

        if not closes:
            return {}

        base = closes[0]
        if base <= 0:
            return {}

        max_high = max(highs) if highs else max(closes)
        min_low = min(lows) if lows else min(closes)

        peak_pct = round((max_high / base - 1) * 100, 2)
        drawdown_pct = round((min_low / base - 1) * 100, 2)
        spread_pct = round((max_high - min_low) / base * 100, 2)

        return {
            "peak_move_pct": peak_pct,
            "max_drawdown_pct": drawdown_pct,
            "spread_pct": spread_pct,
        }
    except Exception as e:
        logger.debug("Failed to calculate price trajectory: %s", e)
        return {}


def _parse_post_mortem_json(content: str) -> dict[str, Any] | None:
    """Parse JSON output from post-mortem LLM."""
    if not content:
        return None

    # Strip thinking tags
    clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    for pattern in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"\{[^{}]*\}"]:
        match = re.search(pattern, clean, re.DOTALL)
        if match:
            try:
                candidate = match.group(1) if "```" in pattern else match.group(0)
                return json.loads(candidate)
            except Exception:
                continue

    return None


def _heuristic_failure_analysis(prediction: dict[str, Any], actual_return_pct: float) -> dict[str, Any]:
    """Fallback rule-based attribution when LLM is unavailable."""
    direction = prediction.get("consensus_direction", "BULLISH").upper()
    exp_return = prediction.get("consensus_return_pct", 0.0)

    if direction == "BULLISH" and actual_return_pct < -3.0:
        cat = "FALSE_TECHNICAL_BREAKOUT"
        summary = f"Stock broke below key support, dropping {actual_return_pct:+.1f}% vs expected {exp_return:+.1f}%."
    elif direction == "BEARISH" and actual_return_pct > 3.0:
        cat = "OVERESTIMATED_MOMENTUM"
        summary = f"Stock sustained unexpected upward momentum (+{actual_return_pct:.1f}%) contrary to bearish consensus."
    else:
        cat = "MACRO_MARKET_CORRECTION"
        summary = f"Actual return of {actual_return_pct:+.1f}% diverged from predicted {exp_return:+.1f}% target."

    return {
        "failure_category": cat,
        "summary": summary,
        "detailed_analysis": f"The trade experienced adverse price divergence where {direction} models predicted {exp_return:+.1f}%, but the market realized {actual_return_pct:+.1f}%.",
        "learning_lesson": "Incorporate tighter stop-loss thresholds and check broader index momentum prior to trade confirmation.",
    }
