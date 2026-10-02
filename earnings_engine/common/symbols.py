"""
earnings_engine/common/symbols.py
Standardized symbol normalization utility.
"""
import re


def normalize_symbol(symbol: str) -> str:
    """
    Standardizes ticker symbol by trimming whitespace, uppercase conversion,
    and stripping exchange/series suffixes (.NS, .BO, .BSE, .NSE, -EQ, -BE).

    Examples:
        'RELIANCE.NS' -> 'RELIANCE'
        'TCS-EQ'      -> 'TCS'
        'INFY.BO'     -> 'INFY'
    """
    if not symbol:
        return ""
    clean = symbol.strip().upper()
    clean = re.sub(r'(\.NS|\.BO|\.BSE|\.NSE|-EQ|-BE)$', '', clean)
    return clean
