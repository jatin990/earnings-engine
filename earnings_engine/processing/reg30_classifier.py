"""
Reg 30 High-Impact Filing Classifier & Noise Filter.
Categorizes SEBI (LODR) Regulation 30 corporate announcements from BSE/NSE
into actionable trading catalysts and critical risk vetoes.
"""

import re
from typing import Dict, Optional, Any

# High-Impact Rule definitions
HIGH_IMPACT_RULES = {
    "AUDITOR_RESIGN": {
        "patterns": [
            r"resignation.*(?:statutory\s+auditor|auditor)",
            r"auditor.*resigned",
            r"cessation.*statutory\s+auditor",
            r"auditor.*resignation",
        ],
        "sentiment": "BEARISH",
        "impact": "CRITICAL",
        "display_name": "Auditor Resignation",
    },
    "KMP_RESIGN": {
        "patterns": [
            r"resignation.*(?:cfo|chief\s+financial\s+officer|managing\s+director|md\s+and\s+ceo|ceo|whole\s+time\s+director)",
            r"cessation.*(?:kmp|chief\s+financial\s+officer|cfo)",
        ],
        "sentiment": "BEARISH",
        "impact": "HIGH",
        "display_name": "Key Management Exit",
    },
    "DEFAULT_LEGAL": {
        "patterns": [
            r"(?:default.*payment.*debt|insolvency.*nclt|ibc.*petition|cbi.*search|ed.*raid|search\s+and\s+seizure|nclt.*admit|forensic\s+audit)",
        ],
        "sentiment": "BEARISH",
        "impact": "CRITICAL",
        "display_name": "Default / Legal / Forensic",
    },
    "RATING_DOWNGRADE": {
        "patterns": [
            r"credit\s+rating.*(?:downgrade|revised\s+downward|negative\s+outlook|credit\s+watch.*negative)",
            r"(?:downgraded|revised\s+down).*(?:rating|outlook)",
        ],
        "sentiment": "BEARISH",
        "impact": "HIGH",
        "display_name": "Rating Downgrade / Watch",
    },
    "ORDER_WIN": {
        "patterns": [
            r"(?:bagged|awarded|received|won|secures?|receipt\s+of).*(?:order|contract|project|letter\s+of\s+award|loa|commercial\s+order)",
            r"(?:major\s+order|export\s+order|supply\s+agreement|turnkey\s+project)",
        ],
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "display_name": "Order Win / Contract",
    },
    "CAPEX_COD": {
        "patterns": [
            r"(?:commissioning|commercial\s+production|commencement\s+of\s+commercial\s+operations|capacity\s+expansion|new\s+plant|trial\s+production|capacity\s+addition)",
        ],
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "display_name": "Capex / Commercial Ops (COD)",
    },
    "RATING_UPGRADE": {
        "patterns": [
            r"credit\s+rating.*(?:upgrade|revised\s+upward|positive\s+outlook)",
            r"(?:upgraded|revised\s+upward).*(?:rating|outlook)",
        ],
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "display_name": "Rating Upgrade",
    },
    "M_AND_A": {
        "patterns": [
            r"(?:acquisition|acquires|takeover|joint\s+venture|slump\s+sale|strategic\s+partnership|merger\s+with|amalgamation)",
        ],
        "sentiment": "NEUTRAL",
        "impact": "MEDIUM",
        "display_name": "M&A / Joint Venture",
    },
    "PROMOTER_PLEDGE": {
        "patterns": [
            r"(?:revocation.*pledge|release.*pledge|pledge.*released|creation\s+of\s+pledge|encumbrance)",
        ],
        "sentiment": "DYNAMIC",
        "impact": "MEDIUM",
        "display_name": "Promoter Pledge Shift",
    },
}

# Substring filters for routine noise that should be rejected immediately
EXCLUDED_KEYWORDS = [
    "trading window closure",
    "closure of trading window",
    "newspaper publication",
    "newspaper advertisement",
    "audio recording",
    "transcript of conference call",
    "transcript of earnings call",
    "analyst meet - audio",
    "loss of share certificate",
    "duplicate share certificate",
    "issue of duplicate",
    "investor presentation",
    "voting results",
    "scrutinizer report",
    "postal ballot notice",
    "shareholding pattern",
    "re-affirmation",
    "reaffirms rating",
    "reaffirmed rating",
]


def extract_order_value_cr(text: str) -> Optional[float]:
    """Extracts disclosed order/deal value in Crores INR if mentioned."""
    patterns = [
        r"(?:rs\.?|inr|₹)\s*([\d,.]+)\s*(?:cr(?:ore)?s?|lakhs?|mn|million|billion)",
        r"(?:worth|value\s+of)\s*(?:rs\.?|inr|₹)?\s*([\d,.]+)\s*(?:cr(?:ore)?s?)",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            val_str = match.group(1).replace(",", "").strip()
            try:
                val = float(val_str)
                if "lakh" in match.group(0).lower():
                    return round(val / 100.0, 2)
                return round(val, 2)
            except ValueError:
                continue
    return None


def classify_reg30_filing(headline: str, description: str = "") -> Optional[Dict[str, Any]]:
    """
    Classifies a Reg 30 disclosure into high-impact category or returns None if noise.
    """
    combined_text = f"{headline} {description}".strip()
    combined_lower = combined_text.lower()

    # 1. Quick noise rejection
    for noise in EXCLUDED_KEYWORDS:
        if noise in combined_lower:
            return None

    # 2. Rule matching
    for cat, rule in HIGH_IMPACT_RULES.items():
        for pattern in rule["patterns"]:
            if re.search(pattern, combined_lower, re.IGNORECASE):
                sentiment = rule["sentiment"]
                if cat == "PROMOTER_PLEDGE":
                    sentiment = "BULLISH" if ("release" in combined_lower or "revocation" in combined_lower) else "BEARISH"

                order_val = extract_order_value_cr(combined_text) if cat == "ORDER_WIN" else None

                return {
                    "category": cat,
                    "category_name": rule["display_name"],
                    "sentiment": sentiment,
                    "impact_level": rule["impact"],
                    "order_value_cr": order_val,
                }

    return None
