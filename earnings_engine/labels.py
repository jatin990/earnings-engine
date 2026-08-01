"""Post-earnings reaction labels.

yfinance does not reliably tell us whether an announcement was before market
open or after close (and NSE results often land mid-day or after hours), so
the reaction window is defined conservatively as:

    reaction_return = close(T+1) / close(T-1) - 1

where T is the announcement date and T-1 / T+1 are the nearest trading days
before/after. This captures the earnings move regardless of intraday timing.
The direction label is 1 if reaction_return > 0, else 0.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class Reaction:
    asof_date: pd.Timestamp      # last trading day strictly before the event (T-1)
    reaction_date: pd.Timestamp  # first trading day strictly after the event (T+1)
    reaction_return: float
    label: int


def compute_reaction(prices: pd.DataFrame, earnings_date: pd.Timestamp) -> Reaction | None:
    """Compute the reaction window around one earnings date.

    `prices` is the per-ticker OHLCV frame (date index, 'close' column).
    Returns None if there is no trading day on either side of the event.
    """
    if prices.empty:
        return None
    idx = prices.index
    before = idx[idx < earnings_date]
    after = idx[idx > earnings_date]
    if len(before) == 0 or len(after) == 0:
        return None
    t_minus = before[-1]
    t_plus = after[0]
    # Guard against stale events with huge gaps (delisted/halted tickers).
    if (t_plus - t_minus).days > 10:
        return None
    try:
        c0 = float(prices.loc[t_minus, "close"])
        c1 = float(prices.loc[t_plus, "close"])
    except (KeyError, TypeError, ValueError):
        return None
    if pd.isna(c0) or pd.isna(c1) or c0 <= 0:
        return None
    ret = c1 / c0 - 1.0
    return Reaction(
        asof_date=t_minus,
        reaction_date=t_plus,
        reaction_return=ret,
        label=int(ret > 0),
    )
