"""Institutional-Grade News Verification & Section-by-Section Sanity Pipeline.

Independently validates and sanity-checks every section of incoming financial news:
1. Date & Temporal Horizon Verification (ISO/IST timestamps, stale/future date detection, quarter extraction).
2. Company Entity & Ticker Resolution (Universe lookup, trade alias matching, dictionary collision protection, conglomerate disambiguation).
3. Financial Numbers & Currency Sanity (Order values in ₹ Cr / $ M, % profit jumps/drops, dividend amounts, scale bounds).
4. Content Authenticity & Noise Filter (Rejects sports, generic clickbait listicles, foreign stocks, spam).
5. Category & Sentiment Cross-Validation (Ensures direction matches polarity; prevents false beat on profit plunge).
6. Canonical Event Fingerprinting (Deterministic SHA-256 hash to collapse multi-feed duplicate reporting).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.names import get_name
from earnings_engine.data.news_sentiment import calculate_headline_sentiment, _clean_text

logger = logging.getLogger(__name__)

# Indian Standard Time (IST) Offset: UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)

# Months mapping for in-text date extraction
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
}

# High-risk single-word tickers prone to generic dictionary false-positives
DICTIONARY_TICKERS = {
    "CREST": ["crest ventures", "crest venture", "crest holdings"],
    "SUN": ["sun pharma", "sun pharmaceutical", "sun tv", "sunflag"],
    "GOD": ["godrej", "godfrey"],
    "FORCE": ["force motors", "force motor"],
    "POWER": ["tata power", "power grid", "powergrid", "adani power", "torrent power", "reliance power"],
    "WIND": ["suzlon", "inox wind", "wind energy"],
    "GOLD": ["manappuram", "muthoot", "titan", "kalyan jewel"],
    "BEST": ["best agrolife"],
    "STAR": ["star health", "star cement"],
    "IDEA": ["vodafone idea", "vi "],
    "CARE": ["care ratings", "healthcare global"],
    "TIME": ["time technoplast"],
    "TRUE": ["truecaller"],
    "GLOBAL": ["global health", "medanta"],
}

# Non-corporate / noise exclusion keywords (sports, gossip, low-fidelity recycled scrapers, crypto spam)
NOISE_PATTERNS = [
    r"\b(barcelona|real madrid|manchester united|arsenal|chelsea|liverpool|world cup|fifa|la liga|premier league|champions league)\b",
    r"\b(boeing|airbus|f-15|f-35|pentagon|us air force|lockheed)\b",
    r"\b(coca-cola europacific|fair oaks income|prudential declares|ccep)\b",
    r"\b(cryptocurrency|bitcoin|ethereum|solana|memecoin|dogecoin|shiba inu)\b",
    r"\b(top 10 stocks for 2030|how to get rich|multibagger penny stocks to buy today|astrology prediction)\b",
    r"\b(scanx\.trade|simplywall\.st|whalesbook|equitypandit|investorgain)\b",
]

# Curated Conglomerate Entity Mappings
CONGLOMERATE_MAP: dict[str, list[tuple[str, str]]] = {
    "APOLLO": [
        (r"\b(apollo\s+tyres?|tyres?)\b", "APOLLOTYRE.NS"),
        (r"\b(apollo\s+hospitals?|hospital|healthcare|pharmacy)\b", "APOLLOHOSP.NS"),
        (r"\b(apollo\s+pipes?|pipes?)\b", "APOLLOPIPE.NS"),
        (r"\b(apollo\s+micro|micro\s+systems?|defence\s+avionics)\b", "APOLLO.NS"),
    ],
    "TATA": [
        (r"\b(tata\s+motors?|jlr|ev\s+curvv|harrier|safari|commercial\s+vehicles)\b", "TATAMOTORS.NS"),
        (r"\b(tata\s+steel|steel\s+plant|kalinganagar)\b", "TATASTEEL.NS"),
        (r"\b(tata\s+power|solar\s+roof|ev\s+charging|renewable)\b", "TATAPOWER.NS"),
        (r"\b(tata\s+consumer|tata\s+tea|sampann|tetley|starbucks)\b", "TATACONSUM.NS"),
        (r"\b(tata\s+elxsi|design\s+tech|embedded\s+ai)\b", "TATAELXSI.NS"),
        (r"\b(tata\s+comm|tata\s+communications?|data\s+center)\b", "TATACOMM.NS"),
        (r"\b(tata\s+chem|tata\s+chemicals?|soda\s+ash)\b", "TATACHEM.NS"),
        (r"\b(tcs|tata\s+consultancy)\b", "TCS.NS"),
        (r"\b(trent|zudio|westside)\b", "TRENT.NS"),
    ],
    "BAJAJ": [
        (r"\b(bajaj\s+finance|bajfinance|consumer\s+lending)\b", "BAJFINANCE.NS"),
        (r"\b(bajaj\s+finserv|finserv|insurance\s+arm)\b", "BAJAJFINSV.NS"),
        (r"\b(bajaj\s+auto|pulsar|chetak|two-wheeler|three-wheeler)\b", "BAJAJ-AUTO.NS"),
        (r"\b(bajaj\s+housing|bhfl)\b", "BAJAJHLDNG.NS"),
    ],
    "ADANI": [
        (r"\b(adani\s+enterprises|ael)\b", "ADANIENT.NS"),
        (r"\b(adani\s+ports|apsez|mundra\s+port)\b", "ADANIPORTS.NS"),
        (r"\b(adani\s+power)\b", "ADANIPOWER.NS"),
        (r"\b(adani\s+green|renewable)\b", "ADANIGREEN.NS"),
        (r"\b(adani\s+energy|transmission)\b", "ADANIENSOL.NS"),
        (r"\b(adani\s+total\s+gas|atgl)\b", "ATGL.NS"),
        (r"\b(adani\s+wilmar|fortune\s+oil)\b", "AWL.NS"),
    ],
    "RELIANCE": [
        (r"\b(reliance\s+industries|ril|jio|reliance\s+retail|oil\s+to\s+chemicals|o2c)\b", "RELIANCE.NS"),
        (r"\b(reliance\s+power|rpower)\b", "RPOWER.NS"),
        (r"\b(reliance\s+infra|rinfra)\b", "RINFRA.NS"),
    ],
}


def parse_and_verify_date(
    published_at_str: str | None,
    title: str = "",
    summary: str = "",
    max_stale_days: int = 14,
) -> dict[str, Any]:
    """Section 1: Date & Temporal Horizon Verification.

    Validates publication timestamp freshness, converts to standardized UTC and IST,
    identifies explicit historical date mentions in the headline, and extracts reporting periods (e.g. Q1 FY27).
    """
    now_utc = datetime.now(timezone.utc)
    now_ist = datetime.now(timezone(IST_OFFSET))
    flags: list[str] = []

    dt_utc: datetime | None = None
    if published_at_str:
        clean_str = str(published_at_str).strip()
        try:
            if "T" in clean_str:
                clean_str = clean_str.replace("Z", "+00:00")
                dt_utc = datetime.fromisoformat(clean_str)
            elif "," in clean_str:
                from email.utils import parsedate_to_datetime
                dt_utc = parsedate_to_datetime(clean_str)
            else:
                dt_utc = datetime.strptime(clean_str[:19], "%Y-%m-%d %H:%M:%S")
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            else:
                dt_utc = dt_utc.astimezone(timezone.utc)
        except Exception:
            dt_utc = None
            flags.append("DATE_PARSE_FAILED")

    if dt_utc is None:
        dt_utc = now_utc
        flags.append("DATE_DEFAULTED_NOW")

    dt_ist = dt_utc.astimezone(timezone(IST_OFFSET))
    published_at_utc = dt_utc.strftime("%Y-%m-%d %H:%M:%S")
    published_at_ist = dt_ist.strftime("%Y-%m-%d %H:%M IST")

    age_hours = (now_utc - dt_utc).total_seconds() / 3600.0
    age_days = age_hours / 24.0

    is_future = age_hours < -1.0  # More than 1h in future (allow small clock drift)
    if is_future:
        flags.append("DATE_FUTURE_INVALID")

    is_stale = age_days > max_stale_days
    if is_stale:
        flags.append("DATE_STALE")

    # In-text historical date mention scan (e.g. "2nd July", "July 2", "during June 2026", "in 2024")
    full_text = (title + " " + summary).lower()
    in_text_historical = False
    in_text_date_desc = None

    # 1. Day Month (e.g. "2nd july", "2 july", "15th june 2026")
    day_month_matches = re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:\s+(\d{4}))?\b", full_text)
    for d_str, m_name, y_str in day_month_matches:
        m_num = MONTH_MAP.get(m_name)
        if m_num:
            day = int(d_str)
            year = int(y_str) if y_str else dt_ist.year
            if year < dt_ist.year or (year == dt_ist.year and (m_num < dt_ist.month or (m_num == dt_ist.month and day < (dt_ist.day - 7)))):
                in_text_historical = True
                in_text_date_desc = f"{day} {m_name.capitalize()} {year}"
                flags.append(f"IN_TEXT_HISTORICAL_DATE_{m_name.upper()}_{day}")
                break

    # 2. Month Day (e.g. "july 2", "july 2nd", "july 02, 2026")
    if not in_text_historical:
        month_day_matches = re.findall(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b", full_text)
        for m_name, d_str, y_str in month_day_matches:
            m_num = MONTH_MAP.get(m_name)
            if m_num:
                day = int(d_str)
                year = int(y_str) if y_str else dt_ist.year
                if year < dt_ist.year or (year == dt_ist.year and (m_num < dt_ist.month or (m_num == dt_ist.month and day < (dt_ist.day - 7)))):
                    in_text_historical = True
                    in_text_date_desc = f"{m_name.capitalize()} {day} {year}"
                    flags.append(f"IN_TEXT_HISTORICAL_DATE_{m_name.upper()}_{day}")
                    break

    # 3. In/During Month (e.g. "in july 2026", "during june")
    if not in_text_historical:
        in_month_matches = re.findall(r"\b(?:in|during|of|as of|since)\s+([a-z]+)(?:\s+(\d{4}))?\b", full_text)
        for m_name, y_str in in_month_matches:
            m_num = MONTH_MAP.get(m_name)
            if m_num:
                year = int(y_str) if y_str else dt_ist.year
                if year < dt_ist.year or (year == dt_ist.year and m_num < dt_ist.month):
                    in_text_historical = True
                    in_text_date_desc = f"{m_name.capitalize()} {year}"
                    flags.append(f"IN_TEXT_HISTORICAL_MONTH_{m_name.upper()}")
                    break

    # 4. Explicit past years (e.g. "in 2024", "during 2025", "fy24", "fy25" when running in 2026)
    if not in_text_historical:
        past_year_match = re.search(r"\b(202[0-5]|fy2[0-5])\b", full_text)
        if past_year_match:
            in_text_historical = True
            in_text_date_desc = f"Past Year {past_year_match.group(1).upper()}"
            flags.append(f"IN_TEXT_HISTORICAL_YEAR_{past_year_match.group(1).upper()}")

    # Extract reporting quarter / fiscal period
    reporting_quarter = None
    q_match = re.search(r"\b(q[1-4]\s*(?:fy\s*\d{2,4})?|fy\s*\d{2,4})\b", full_text)
    if q_match:
        reporting_quarter = q_match.group(1).upper().replace(" ", "")

    is_valid_date = not is_future and not is_stale and not in_text_historical

    return {
        "is_valid": is_valid_date,
        "published_at_utc": published_at_utc,
        "published_at_ist": published_at_ist,
        "dt_ist": dt_ist,
        "age_hours": round(age_hours, 1),
        "age_days": round(age_days, 1),
        "is_future": is_future,
        "is_stale": is_stale,
        "in_text_historical": in_text_historical,
        "in_text_date_desc": in_text_date_desc,
        "reporting_quarter": reporting_quarter,
        "flags": flags,
    }


def verify_company_entity(
    ticker: str,
    title: str,
    summary: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Section 2: Company Entity & Ticker Verification.

    Validates ticker legitimacy, matches corporate entity names and known trading aliases,
    protects against single-word dictionary collisions (e.g. CREST, SUN), and disambiguates conglomerate families.
    """
    settings = settings or Settings()
    raw_sym = str(ticker).strip().upper()
    clean_sym = raw_sym.replace(".NS", "").replace(".BO", "").strip()
    official_name = get_name(raw_sym, settings) or clean_sym

    full_text = f"{title} {summary}".lower()
    flags: list[str] = []
    resolved_ticker = raw_sym
    confidence_score = 0.50

    # 1. Conglomerate Disambiguation Check
    for prefix, mappings in CONGLOMERATE_MAP.items():
        if clean_sym.startswith(prefix) or clean_sym == prefix:
            for pattern, target_ticker in mappings:
                if re.search(pattern, full_text):
                    if target_ticker != raw_sym:
                        flags.append(f"CONGLOMERATE_REASSIGNED_{clean_sym}_TO_{target_ticker}")
                        resolved_ticker = target_ticker
                        official_name = get_name(resolved_ticker, settings) or target_ticker
                        confidence_score = 0.90
                    else:
                        flags.append("CONGLOMERATE_VERIFIED_EXACT")
                        confidence_score = 0.88
                    break

    # 2. Single-Word Dictionary Collision Protection (e.g. "crest" in "wave crest" vs "Crest Ventures")
    if clean_sym in DICTIONARY_TICKERS:
        required_aliases = DICTIONARY_TICKERS[clean_sym]
        has_alias_match = any(alias in full_text for alias in required_aliases)
        if not has_alias_match:
            flags.append(f"DICTIONARY_WORD_COLLISION_REJECTED_{clean_sym}")
            return {
                "is_verified": False,
                "confidence_score": 0.10,
                "resolved_ticker": resolved_ticker,
                "official_name": official_name,
                "rejection_reason": f"Headline contains dictionary word '{clean_sym}' without matching corporate entity alias ({required_aliases[0]}).",
                "flags": flags,
            }
        else:
            confidence_score = max(confidence_score, 0.85)
            flags.append("DICTIONARY_TICKER_ALIAS_VERIFIED")

    # 3. Foreign Exchange Ticker Collision Protection (e.g. "SFL (NYSE:SFL)" mapped to Indian "SFL.NS")
    is_indian = raw_sym.endswith(".NS") or raw_sym.endswith(".BO")
    if is_indian:
        foreign_exchanges = [
            r"\b(?:nyse|nasdaq|tsx|asx|lse|hkg|sgx|fra|etr|cboe)\s*[:/]\s*([a-z0-9\.\-]+)",
            r"\((?:nyse|nasdaq|tsx|asx|lse|hkg|sgx|fra|etr|cboe)\s*:\s*([a-z0-9\.\-]+)\)",
        ]
        has_foreign_ticker = any(re.search(pat, full_text) for pat in foreign_exchanges)
        if has_foreign_ticker and not any(ind in full_text for ind in ["(nse:", "(bse:", "nse:", "bse:", "sebi", "lodr", "india"]):
            # Check if official corporate name (e.g. Sheela Foam) is explicitly present (excluding the bare ticker symbol)
            name_clean = re.sub(r"\b(ltd|limited|corp|corporation|industries|india|co)\b", "", official_name.lower()).strip()
            name_tokens = [w for w in name_clean.split() if len(w) >= 3 and w != clean_sym.lower()]
            if not name_tokens or not any(t in full_text for t in name_tokens):
                flags.append("FOREIGN_EXCHANGE_TICKER_COLLISION_REJECTED")
                return {
                    "is_verified": False,
                    "confidence_score": 0.05,
                    "resolved_ticker": resolved_ticker,
                    "official_name": official_name,
                    "rejection_reason": f"Headline refers to foreign exchange listing (NYSE/NASDAQ/LSE) rather than Indian equity {raw_sym}.",
                    "flags": flags,
                }

    # 4. Direct Entity Name Mention Check
    name_clean = re.sub(r"\b(ltd|limited|corp|corporation|industries|india|co)\b", "", official_name.lower()).strip()
    name_tokens = [w for w in name_clean.split() if len(w) >= 3]
    if name_tokens and any(t in full_text for t in name_tokens):
        confidence_score = max(confidence_score, 0.85)
        flags.append("ENTITY_NAME_TOKEN_MATCH")
    elif clean_sym.lower() in full_text:
        confidence_score = max(confidence_score, 0.70)
        flags.append("EXACT_SYMBOL_TOKEN_MATCH")

    is_verified = confidence_score >= 0.60

    return {
        "is_verified": is_verified,
        "confidence_score": round(confidence_score, 2),
        "resolved_ticker": resolved_ticker,
        "official_name": official_name,
        "rejection_reason": None if is_verified else f"Low entity association confidence ({confidence_score:.2f})",
        "flags": flags,
    }


def verify_financial_numbers(title: str, summary: str = "") -> dict[str, Any]:
    """Section 3: Financial Numbers & Currency Sanity Check.

    Extracts all quantitative metrics from headline and summary:
    - Order / Contract values: ₹X Cr, ₹X Lakh, $X Million, $X Billion.
    - Percentage changes: surges 56%, profit drops 12%.
    - Dividend / Corporate actions: ₹8.50 per share, bonus 1:1, split 1:10.
    Validates mathematical sanity and detects currency scale mismatches.
    """
    full_text = f"{title} {summary}"
    flags: list[str] = []
    extracted: dict[str, Any] = {
        "order_value_cr": None,
        "order_value_usd_m": None,
        "pct_change": None,
        "dividend_amount": None,
        "ratio_action": None,
        "currency": "INR",
    }

    # 1. Order / Deal Value Extraction (INR Crore & Lakh)
    cr_match = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(?:cr|crore|crores)\b", full_text, re.IGNORECASE)
    if not cr_match:
        cr_match = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:crore|cr)\s*(?:order|deal|contract|pact|project)\b", full_text, re.IGNORECASE)
    if cr_match:
        try:
            val = float(cr_match.group(1).replace(",", ""))
            # Sanity bound: Order value must be > 0 and <= 500,000 Cr
            if 0 < val <= 500000:
                extracted["order_value_cr"] = val
                flags.append(f"ORDER_VALUE_INR_{val}CR")
            else:
                flags.append("ORDER_VALUE_OUT_OF_BOUNDS")
        except ValueError:
            pass

    # USD / Foreign Value Extraction
    usd_match = re.search(r"(?:\$|usd)\s*([\d,]+(?:\.\d+)?)\s*(m|million|b|billion|k)?\b", full_text, re.IGNORECASE)
    if usd_match:
        try:
            raw_num = float(usd_match.group(1).replace(",", ""))
            unit = (usd_match.group(2) or "").lower()
            if unit.startswith("b"):
                val_m = raw_num * 1000.0
            elif unit.startswith("k"):
                val_m = raw_num / 1000.0
            else:
                val_m = raw_num
            extracted["order_value_usd_m"] = val_m
            extracted["currency"] = "USD"
            flags.append(f"FOREIGN_VALUE_USD_{val_m}M")
        except ValueError:
            pass

    # 2. Percentage Surge / Drop Extraction
    pct_match = re.search(r"(?:surges|jumps|soars|rises|up|gains|plunges|drops|falls|down|slumps|by)\s*([\d,]+(?:\.\d+)?)\s*%", full_text, re.IGNORECASE)
    if not pct_match:
        pct_match = re.search(r"([\d,]+(?:\.\d+)?)\s*%\s*(?:jump|surge|rise|drop|fall|plunge|decline|growth|beat)", full_text, re.IGNORECASE)
    if pct_match:
        try:
            pct_val = float(pct_match.group(1).replace(",", ""))
            # Sanity bound: percentage move must be <= 50,000%
            if 0 <= pct_val <= 50000:
                extracted["pct_change"] = pct_val
                flags.append(f"PCT_CHANGE_{pct_val}%")
            else:
                flags.append("PCT_CHANGE_EXTREME_ANOMALY")
        except ValueError:
            pass

    # 3. Dividend Payout Extraction (₹X per share)
    div_match = re.search(r"(?:dividend(?:\s+of)?|payout(?:\s+of)?)\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+share|rs\.?|inr|₹)?\b", full_text, re.IGNORECASE)
    if div_match:
        try:
            div_val = float(div_match.group(1).replace(",", ""))
            if 0 < div_val <= 5000:
                extracted["dividend_amount"] = div_val
                flags.append(f"DIVIDEND_PER_SHARE_INR_{div_val}")
        except ValueError:
            pass

    # 4. Stock Split / Bonus Ratio Extraction (e.g. 1:1, 1:2, 1:10)
    ratio_match = re.search(r"\b(bonus|split|ratio|rights)\s*(?:issue)?\s*(?:of)?\s*(\d+:\d+)\b", full_text, re.IGNORECASE)
    if ratio_match:
        ratio_str = ratio_match.group(2)
        extracted["ratio_action"] = ratio_str
        flags.append(f"CORPORATE_RATIO_{ratio_str}")

    has_numbers = any(v is not None for k, v in extracted.items() if k != "currency")
    return {
        "has_numbers": has_numbers,
        "metrics": extracted,
        "flags": flags,
    }


def verify_authenticity_and_relevance(title: str, summary: str = "") -> dict[str, Any]:
    """Section 4: Content Authenticity & Noise/Spam Filter.

    Filters out sports results, foreign defense tenders unrelated to Indian listings,
    clickbait generic listicles, and crypto spam.
    """
    full_text = f"{title} {summary}".lower()
    flags: list[str] = []

    for pattern in NOISE_PATTERNS:
        if re.search(pattern, full_text):
            flags.append("NOISE_FILTER_TRIGGERED")
            return {
                "is_authentic": False,
                "rejection_reason": f"Headline matched non-corporate / noise pattern: {pattern}",
                "flags": flags,
            }

    # Verify corporate relevance keyword presence
    corporate_triggers = [
        "order", "contract", "profit", "revenue", "quarter", "pat", "ebitda", "dividend",
        "acquisition", "merger", "stake", "approval", "fda", "usfda", "sebi", "lodr",
        "disclosure", "intimation", "rating", "target", "upgrade", "downgrade", "pledge",
        "plant", "expansion", "commercial", "board meeting", "results", "guidance",
        "tender", "secures", "wins", "bags", "deal", "pact", "agreement", "solar", "project"
    ]
    has_trigger = any(t in full_text for t in corporate_triggers)
    if not has_trigger:
        flags.append("LOW_CORPORATE_RELEVANCE")

    return {
        "is_authentic": True,
        "has_corporate_trigger": has_trigger,
        "flags": flags,
    }


def verify_category_and_sentiment(
    title: str,
    summary: str = "",
    base_category: str | None = None,
) -> dict[str, Any]:
    """Section 5: Category & Sentiment Cross-Validation.

    Cross-verifies topic classification against sentiment and financial figures.
    Prevents contradictions (e.g. classifying profit plunges as BULLISH).
    """
    full_text = f"{title} {summary}".lower()
    score, label = calculate_headline_sentiment(title, summary)
    flags: list[str] = []

    direction = "NEUTRAL"
    if label == "Bullish" or score >= 0.20:
        direction = "BULLISH"
    elif label == "Bearish" or score <= -0.20:
        direction = "BEARISH"

    # Strict Sentiment Sanity Overrides for negative corporate catalysts
    if any(w in full_text for w in ["plunges", "plunged", "crashes", "crashed", "loss", "warning", "probe", "fraud", "scam", "default", "downgraded", "margin compression", "slumps", "slumped", "drops 4", "drops 5", "drops 6", "drops 7", "drops 8", "drops 9", "down 4", "down 5"]):
        if direction != "BEARISH":
            flags.append("DIRECTION_CONTRADICTION_CORRECTED_TO_BEARISH")
            direction = "BEARISH"

    # Strict Sentiment Sanity Overrides for positive corporate catalysts
    if any(w in full_text for w in ["surges", "surged", "bags order", "secures order", "profit jumps", "net profit up", "profit surges", "upgrade", "approved"]):
        if "loss" not in full_text and "probe" not in full_text and "warning" not in full_text and "fraud" not in full_text:
            if direction != "BULLISH":
                flags.append("DIRECTION_CONTRADICTION_CORRECTED_TO_BULLISH")
                direction = "BULLISH"

    return {
        "direction": direction,
        "sentiment_score": score,
        "sentiment_label": label,
        "flags": flags,
    }


def compute_canonical_hash(
    ticker: str,
    title: str,
    verified_numbers: dict[str, Any] | None = None,
) -> str:
    """Section 6: Canonical Event Fingerprinting.

    Computes deterministic SHA-256 fingerprint on cleaned ticker, normalized core tokens,
    and key financial values to collapse duplicate reports across feeds.
    """
    clean_sym = ticker.replace(".NS", "").replace(".BO", "").strip().upper()
    # Normalize title: lowercase, remove punctuation, strip publisher signatures
    norm_title = re.sub(r"-(?:\s*[a-z0-9\.\s]+)$", "", title, flags=re.IGNORECASE)
    norm_title = re.sub(r"[^\w\s]", "", norm_title.lower())
    tokens = sorted(list(set(w for w in norm_title.split() if len(w) >= 4)))
    core_str = f"{clean_sym}:{' '.join(tokens)}"

    if verified_numbers:
        if verified_numbers.get("order_value_cr"):
            core_str += f":val_cr_{verified_numbers['order_value_cr']}"
        if verified_numbers.get("pct_change"):
            core_str += f":pct_{verified_numbers['pct_change']}"

    return hashlib.sha256(core_str.encode("utf-8")).hexdigest()[:24]


class NewsVerifier:
    """Master Verification Engine coordinating all multi-section news validators."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def verify_news_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Execute the end-to-end 6-stage verification funnel for an incoming news item."""
        title = _clean_text(item.get("title", ""))
        summary = _clean_text(item.get("summary", ""))
        ticker = item.get("ticker", "").strip().upper()
        raw_pub = item.get("published_at")

        all_flags: list[str] = []

        # Stage 1: Authenticity & Noise Filter
        auth_res = verify_authenticity_and_relevance(title, summary)
        all_flags.extend(auth_res["flags"])
        if not auth_res["is_authentic"]:
            return {
                "verification_status": "REJECTED",
                "rejection_reason": auth_res["rejection_reason"],
                "verification_flags": all_flags,
                "confidence_score": 0.0,
            }

        # Stage 2: Date & Temporal Verification
        date_res = parse_and_verify_date(raw_pub, title, summary)
        all_flags.extend(date_res["flags"])
        if not date_res["is_valid"]:
            return {
                "verification_status": "REJECTED",
                "rejection_reason": f"Date verification failed: {', '.join(date_res['flags'])}",
                "verification_flags": all_flags,
                "confidence_score": 0.0,
            }

        # Stage 3: Entity Resolution & Ticker Verification
        entity_res = verify_company_entity(ticker, title, summary, self.settings)
        all_flags.extend(entity_res["flags"])
        if not entity_res["is_verified"]:
            return {
                "verification_status": "REJECTED",
                "rejection_reason": entity_res["rejection_reason"],
                "verification_flags": all_flags,
                "confidence_score": entity_res["confidence_score"],
            }

        # Stage 4: Financial Numbers Extraction
        num_res = verify_financial_numbers(title, summary)
        all_flags.extend(num_res["flags"])

        # Stage 5: Category & Sentiment Cross-Validation
        cat_res = verify_category_and_sentiment(title, summary, item.get("category"))
        all_flags.extend(cat_res["flags"])

        # Stage 6: Canonical Event Fingerprint
        canonical_hash = compute_canonical_hash(
            entity_res["resolved_ticker"],
            title,
            num_res["metrics"],
        )

        confidence = round((entity_res["confidence_score"] * 0.7) + (0.3 if num_res["has_numbers"] else 0.2), 2)
        confidence = min(0.99, max(0.50, confidence))

        return {
            "verification_status": "VERIFIED",
            "confidence_score": confidence,
            "resolved_ticker": entity_res["resolved_ticker"],
            "official_name": entity_res["official_name"],
            "published_at_utc": date_res["published_at_utc"],
            "published_at_ist": date_res["published_at_ist"],
            "reporting_quarter": date_res["reporting_quarter"],
            "verified_numbers": num_res["metrics"],
            "verified_direction": cat_res["direction"],
            "sentiment_score": cat_res["sentiment_score"],
            "sentiment_label": cat_res["sentiment_label"],
            "canonical_hash": canonical_hash,
            "verification_flags": all_flags,
            "rejection_reason": None,
        }
