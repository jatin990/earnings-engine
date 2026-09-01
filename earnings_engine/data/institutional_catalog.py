"""Comprehensive Institutional Investors, AMC Flagship Schemes, FIIs, and Super Investors Catalog."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPER_INVESTORS_CATALOG: list[str] = [
    "Ashish Kacholia", "Mukul Agrawal", "Vijay Kedia", "Radhakishan Damani",
    "Dolly Khanna", "Sunil Singhania", "Porinju Veliyath", "Anil Kumar Goel",
    "Nemish Shah", "Rekha Jhunjhunwala", "Mohnish Pabrai", "Guy Spier",
    "Hemendra Kothari", "Madhu Kela", "Sanjay Bakshi", "Ramesh Damani",
    "Shankar Sharma", "Kenneth Andrade", "Samir Arora", "Prashant Jain",
    "S Naren", "Sunil Singhania (Abakkus)",
]

FII_SOVEREIGN_CATALOG: list[str] = [
    "Vanguard Emerging Markets Fund", "GQG Partners Emerging Markets", "BlackRock Global Funds",
    "Capital Group Global Discovery", "Fidelity International", "Morgan Stanley Asia Fund",
    "Government Pension Fund Global (Norway)", "GIC Private Limited", "Monetary Authority of Singapore",
    "Temasek Holdings", "CPPIB (Canada Pension Plan)", "CalPERS (California Public Employees)",
    "Ontario Teachers Pension Plan", "Abu Dhabi Investment Authority (ADIA)", "Kuwait Investment Authority",
    "JPMorgan Emerging Markets Equity", "Goldman Sachs India Equity", "HSBC Global Investment Funds",
    "Citigroup Global Markets", "Nomura India Equity", "Societe Generale Asia", "UBS Principal Capital",
    "BNP Paribas Funds India", "CLSA Global Markets", "Macquarie Emerging Markets",
    "Invesco India Growth Opportunities", "Schroder International Selection", "Franklin Templeton Emerging Growth",
    "Wellington Management India", "T. Rowe Price Emerging Markets",
]

INSURANCE_CATALOG: list[str] = [
    "Life Insurance Corporation of India", "SBI Life Insurance", "HDFC Life Insurance",
    "ICICI Prudential Life Insurance", "General Insurance Corporation of India",
    "Max Life Insurance", "New India Assurance", "Oriental Insurance",
    "Bajaj Allianz Life Insurance", "Tata AIA Life Insurance", "Star Health and Allied Insurance",
]

_DISCOVERED_DII_SCHEMES: dict[str, list[str]] = {}



def get_categorized_dii_schemes() -> dict[str, list[str]]:
    """Dynamically discover and categorize active equity schemes from the AMFI NAV feed."""
    global _DISCOVERED_DII_SCHEMES
    if _DISCOVERED_DII_SCHEMES:
        return _DISCOVERED_DII_SCHEMES

    large_cap: list[str] = []
    mid_cap: list[str] = []
    small_cap: list[str] = []
    flexi_cap: list[str] = []
    seen: set[str] = set()

    try:
        from earnings_engine.data.amfi_holdings import parse_amfi_nav_feed
        schemes = parse_amfi_nav_feed()
        for s in schemes:
            n = s.get("scheme_name", "").strip()
            if not n:
                continue
            n_lower = n.lower()
            if any(k in n_lower for k in [
                "direct", "dividend", "idcw", "daily", "weekly", "monthly", "overnight",
                "liquid", "ultra short", "low duration", "money market", "gilt", "debt",
                "bond", "income", "treasury", "fixed", "savings", "banking & psu",
                "credit risk", "floater", "dynamic bond", "arbitrage", "fof", "fund of fund",
                "index fund", "etf",
            ]):
                continue

            clean_n = (
                n.replace(" - Growth Option", "")
                .replace(" - Growth", "")
                .replace(" - Regular Plan", "")
                .replace(" Regular Plan", "")
                .replace(" Growth Option", "")
                .replace(" Growth", "")
                .strip()
            )
            if clean_n in seen:
                continue
            seen.add(clean_n)

            if any(k in n_lower for k in ["large cap", "bluechip", "top 100", "frontline", "large & mid"]):
                large_cap.append(clean_n)
            elif any(k in n_lower for k in ["mid cap", "midcap", "emerging equity", "growth fund", "select focus"]):
                mid_cap.append(clean_n)
            elif any(k in n_lower for k in ["small cap", "smallcap", "micro cap", "microcap"]):
                small_cap.append(clean_n)
            elif any(k in n_lower for k in ["flexi cap", "flexicap", "multi cap", "multicap", "focused", "value", "contra", "opportunities"]):
                flexi_cap.append(clean_n)
    except Exception as e:
        logger.debug("[CATALOG] AMFI feed dynamic scheme harvest notice: %s", e)

    if not large_cap:
        large_cap = [
            "SBI Bluechip Fund", "ICICI Prudential Bluechip Fund", "Mirae Asset Large Cap Fund",
            "Kotak Bluechip Fund", "Axis Bluechip Fund", "HDFC Top 100 Fund", "Canara Robeco Bluechip Equity",
            "Aditya Birla Sun Life Frontline Equity", "UTI Mastershare Unit Scheme", "Nippon India Large Cap Fund",
        ]
    if not mid_cap:
        mid_cap = [
            "HDFC Mid-Cap Opportunities Fund", "Nippon India Growth Fund", "Motilal Oswal Midcap Fund",
            "Kotak Emerging Equity Fund", "DSP Midcap Fund", "Mirae Asset Midcap Fund",
            "SBI Magnum Midcap Fund", "Quant Active Fund", "Axis Midcap Fund", "Edelweiss Mid Cap Fund",
        ]
    if not small_cap:
        small_cap = [
            "Nippon India Small Cap Fund", "HDFC Small Cap Fund", "SBI Small Cap Fund",
            "Tata Small Cap Fund", "DSP Small Cap Fund", "Bandhan Sterling Value Fund",
            "WhiteOak Capital Flexi Cap Fund", "Quant Small Cap Fund", "Kotak Small Cap Fund",
            "Canara Robeco Small Cap Fund", "Axis Small Cap Fund",
        ]
    if not flexi_cap:
        flexi_cap = [
            "Parag Parikh Flexi Cap Fund", "Quant Active Fund", "HDFC Flexi Cap Fund",
            "ICICI Prudential Value Discovery", "Kotak Flexicap Fund", "SBI Contra Fund",
            "Motilal Oswal Flexi Cap Fund", "UTI Flexi Cap Fund", "DSP Flexi Cap Fund",
        ]

    _DISCOVERED_DII_SCHEMES = {
        "large_cap": large_cap,
        "mid_cap": mid_cap,
        "small_cap": small_cap,
        "flexi_cap": flexi_cap,
    }
    return _DISCOVERED_DII_SCHEMES
