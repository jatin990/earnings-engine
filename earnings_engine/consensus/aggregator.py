"""Consensus Aggregator for AI Consensus Engine.

Takes individual model predictions and computes consensus direction,
confidence-weighted target prices, agreement ratios, and a synthesized thesis.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("earnings_engine.consensus.aggregator")


def aggregate_predictions(
    model_results: list[dict[str, Any]],
    ticker: str,
    as_of_price: float,
    timeframe_days: int = 14,
) -> dict[str, Any]:
    """Aggregate individual model predictions into a consensus result.

    Args:
        model_results: List of prediction dicts from model_runner.
        ticker: The ticker symbol.
        as_of_price: Current price at prediction time.
        timeframe_days: Evaluation window in days.

    Returns:
        A ConsensusResult dict ready for DB insertion.
    """
    # Separate successful vs errored predictions
    valid = [r for r in model_results if "error" not in r and r.get("direction")]
    errored = [r for r in model_results if "error" in r]

    if not valid:
        return {
            "ticker": ticker,
            "as_of_price": as_of_price,
            "consensus_direction": "NEUTRAL",
            "consensus_strength": 0.0,
            "consensus_return_pct": 0.0,
            "consensus_target_price": as_of_price,
            "consensus_support": None,
            "consensus_resistance": None,
            "model_count": len(model_results),
            "agreement_ratio": 0.0,
            "models_breakdown": model_results,
            "synthesized_thesis": "All models failed to respond. No consensus available.",
            "valid_count": 0,
            "error_count": len(errored),
        }

    # --- Directional Consensus (confidence-weighted) ---
    bullish_confidence = 0.0
    bearish_confidence = 0.0
    neutral_confidence = 0.0
    total_confidence = 0.0

    for p in valid:
        conf = float(p.get("confidence_pct", 50))
        direction = p.get("direction", "NEUTRAL").upper()
        total_confidence += conf

        if direction == "BULLISH":
            bullish_confidence += conf
        elif direction == "BEARISH":
            bearish_confidence += conf
        else:
            neutral_confidence += conf

    # Consensus direction = whichever side has the most confidence-weighted votes
    if total_confidence > 0:
        bull_pct = bullish_confidence / total_confidence * 100
        bear_pct = bearish_confidence / total_confidence * 100
    else:
        bull_pct = bear_pct = 0.0

    if bull_pct >= 60:
        consensus_direction = "BULLISH"
        consensus_strength = bull_pct
    elif bear_pct >= 60:
        consensus_direction = "BEARISH"
        consensus_strength = bear_pct
    else:
        consensus_direction = "NEUTRAL"
        consensus_strength = max(bull_pct, bear_pct)

    # --- Agreement Ratio (simple majority count) ---
    direction_counts: dict[str, int] = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
    for p in valid:
        d = p.get("direction", "NEUTRAL").upper()
        direction_counts[d] = direction_counts.get(d, 0) + 1

    majority_direction = max(direction_counts, key=direction_counts.get)  # type: ignore[arg-type]
    agreement_ratio = direction_counts[majority_direction] / len(valid) if valid else 0.0

    # --- Confidence-Weighted Price Action Metrics ---
    weighted_target = 0.0
    weighted_return = 0.0
    weighted_support = 0.0
    weighted_resistance = 0.0
    weighted_stop_loss = 0.0
    support_weight = 0.0
    resistance_weight = 0.0
    stop_weight = 0.0
    rr_ratios: list[float] = []
    actions: list[str] = []

    for p in valid:
        conf = float(p.get("confidence_pct", 50))

        target_price = p.get("target_price")
        if target_price and float(target_price) > 0:
            weighted_target += float(target_price) * conf

        target_ret = p.get("target_return_pct")
        if target_ret is not None:
            weighted_return += float(target_ret) * conf

        support = p.get("support_level")
        if support and float(support) > 0:
            weighted_support += float(support) * conf
            support_weight += conf

        resistance = p.get("resistance_level")
        if resistance and float(resistance) > 0:
            weighted_resistance += float(resistance) * conf
            resistance_weight += conf

        stop_loss = p.get("stop_loss_price")
        if stop_loss and float(stop_loss) > 0:
            weighted_stop_loss += float(stop_loss) * conf
            stop_weight += conf

        rr = p.get("risk_reward_ratio")
        if rr and float(rr) > 0:
            rr_ratios.append(float(rr))

        act = p.get("recommended_action")
        if act:
            actions.append(str(act).strip().upper())

    consensus_target_price = weighted_target / total_confidence if total_confidence > 0 else as_of_price
    consensus_return_pct = weighted_return / total_confidence if total_confidence > 0 else 0.0
    consensus_support = weighted_support / support_weight if support_weight > 0 else None
    consensus_resistance = weighted_resistance / resistance_weight if resistance_weight > 0 else None
    consensus_stop_loss = weighted_stop_loss / stop_weight if stop_weight > 0 else None
    consensus_rr = (sum(rr_ratios) / len(rr_ratios)) if rr_ratios else None

    # Determine recommended action
    if actions:
        from collections import Counter
        consensus_action = Counter(actions).most_common(1)[0][0]
    elif consensus_direction == "BULLISH":
        consensus_action = "ACCUMULATE ON DIPS" if consensus_strength < 80 else "STRONG BUY"
    elif consensus_direction == "BEARISH":
        consensus_action = "AVOID / TAKE PROFITS"
    else:
        consensus_action = "HOLD / WAIT FOR BREAKOUT"

    # --- Synthesized Thesis ---
    thesis = _synthesize_thesis(valid, errored, consensus_direction, consensus_strength, agreement_ratio)

    return {
        "ticker": ticker,
        "as_of_price": round(as_of_price, 2),
        "consensus_direction": consensus_direction,
        "consensus_strength": round(consensus_strength, 1),
        "consensus_return_pct": round(consensus_return_pct, 2),
        "consensus_target_price": round(consensus_target_price, 2),
        "consensus_support": round(consensus_support, 2) if consensus_support else None,
        "consensus_resistance": round(consensus_resistance, 2) if consensus_resistance else None,
        "consensus_stop_loss": round(consensus_stop_loss, 2) if consensus_stop_loss else None,
        "consensus_risk_reward": round(consensus_rr, 1) if consensus_rr else None,
        "consensus_recommended_action": consensus_action,
        "model_count": len(model_results),
        "agreement_ratio": round(agreement_ratio, 2),
        "models_breakdown": model_results,
        "synthesized_thesis": thesis,
        "valid_count": len(valid),
        "error_count": len(errored),
    }


def _synthesize_thesis(
    valid: list[dict[str, Any]],
    errored: list[dict[str, Any]],
    direction: str,
    strength: float,
    agreement: float,
) -> str:
    """Generate a human-readable thesis from model predictions."""
    parts: list[str] = []

    # Strength label
    if strength >= 80:
        parts.append(f"Strong {direction.lower()} consensus ({strength:.0f}%)")
    elif strength >= 60:
        parts.append(f"Moderate {direction.lower()} consensus ({strength:.0f}%)")
    else:
        parts.append(f"Divergent views — no clear consensus ({strength:.0f}%)")

    parts.append(f"with {agreement:.0%} model agreement ({len(valid)}/{len(valid) + len(errored)} responded).")

    # Key drivers from the majority
    all_drivers: list[str] = []
    dissenting_drivers: list[str] = []
    for p in valid:
        model_dir = p.get("direction", "NEUTRAL").upper()
        drivers = p.get("key_drivers", [])
        model_name = p.get("model_name", "Unknown")

        if model_dir == direction:
            all_drivers.extend(drivers[:2])
        else:
            for d in drivers[:1]:
                dissenting_drivers.append(f"{model_name}: {d}")

    if all_drivers:
        unique_drivers = list(dict.fromkeys(all_drivers))[:3]
        parts.append("Key drivers: " + "; ".join(unique_drivers) + ".")

    if dissenting_drivers:
        parts.append("Dissent: " + "; ".join(dissenting_drivers[:2]) + ".")

    # Primary risks
    risks = [p.get("primary_risk") for p in valid if p.get("primary_risk")]
    if risks:
        parts.append(f"Primary risk: {risks[0]}")

    return " ".join(parts)
