"""Constants and identifier classifications for Institutional Accumulation Forensics."""

from __future__ import annotations

import re

from earnings_engine.data.institutional_catalog import SUPER_INVESTORS_CATALOG

DEFAULT_LOOKBACK_DAYS: int = 90
MIN_HOLDING_VALUE_CR: float = 1.0
SUPER_INVESTORS: list[str] = SUPER_INVESTORS_CATALOG
SECTORS_MAP: dict[str, str] = {}

_MARQUEE_AMC_KEYWORDS: tuple[str, ...] = (
    "hdfc", "sbi", "icici pru", "icici prudential", "nippon", "kotak", "axis", "mirae",
    "parag parikh", "ppfas", "quant", "dsp", "tata", "uti", "bandhan", "motilal oswal",
    "whiteoak", "vanguard", "blackrock", "gqg", "fidelity", "capital group", "temasek",
    "gic", "norway", "adia", "cppib", "franklin", "invesco", "schroder", "morgan stanley",
    "goldman", "jpmorgan", "nomura", "clsa", "macquarie",
)

MARQUEE_AMCS: tuple[str, ...] = _MARQUEE_AMC_KEYWORDS


def _get_quarter_start_date(q_str: str) -> str:
    """Parse quarter name like 'Q1 FY26' into ISO start date string for accurate chronological sorting."""
    m = re.search(r'Q([1-4])\s*FY(\d{2,4})', str(q_str), re.IGNORECASE)
    if not m:
        return "2000-01-01"
    q_num = int(m.group(1))
    fy_num = int(m.group(2))
    if fy_num < 100:
        fy_num += 2000
    if q_num == 1:
        return f"{fy_num - 1}-04-01"
    elif q_num == 2:
        return f"{fy_num - 1}-07-01"
    elif q_num == 3:
        return f"{fy_num - 1}-10-01"
    elif q_num == 4:
        return f"{fy_num}-01-01"
    return f"{fy_num}-01-01"


def _is_super_investor_name(name: str) -> bool:
    """Check if the given investor or fund entity name matches known Super Investors."""
    if not name:
        return False
    from earnings_engine.data.institutional_catalog import SUPER_INVESTORS_CATALOG
    name_clean = name.strip().lower()
    for s in SUPER_INVESTORS_CATALOG:
        s_clean = s.strip().lower()
        if s_clean in name_clean or name_clean in s_clean:
            return True
    return False


def _is_marquee_amc_name(name: str) -> bool:
    """Check if the given entity name matches marquee flagship asset management companies."""
    if not name:
        return False
    name_clean = name.strip().lower()
    return any(k in name_clean for k in _MARQUEE_AMC_KEYWORDS)
