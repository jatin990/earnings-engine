"""Pre-earnings price/volume features.

All features are computed from price data up to and including `asof_date`
(the last trading day strictly before the announcement). Nothing after that
date may be touched — this is the point-in-time guarantee the backtest and
live prediction both rely on.
"""

import math

import numpy as np
import pandas as pd

MIN_HISTORY_DAYS = 70  # need ~3 months of bars for the longest lookback

PRICE_FEATURES = [
    "ret_5d",
    "ret_21d",
    "ret_63d",
    "vol_21d",
    "vol_ratio_5d_63d",
    "volume_ratio_5d_63d",
    "abs_ret_mean_21d",
    "dist_52w_high",
    "dist_52w_low",
]


def _trailing_return(close: pd.Series, days: int) -> float:
    if len(close) <= days:
        return np.nan
    return float(close.iloc[-1] / close.iloc[-1 - days] - 1.0)


def compute_price_features(prices: pd.DataFrame, asof_date: pd.Timestamp) -> dict | None:
    """Return the price-feature dict as of `asof_date`, or None if history is thin."""
    hist = prices.loc[prices.index <= asof_date]
    if len(hist) < MIN_HISTORY_DAYS:
        return None

    close = hist["close"]
    volume = hist["volume"].astype(float)
    daily_ret = close.pct_change().dropna()

    vol_5d = float(daily_ret.tail(5).std())
    vol_21d = float(daily_ret.tail(21).std())
    vol_63d = float(daily_ret.tail(63).std())

    vol_avg_5d = float(volume.tail(5).mean())
    vol_avg_63d = float(volume.tail(63).mean())

    high_52w = float(close.tail(252).max())
    low_52w = float(close.tail(252).min())
    last = float(close.iloc[-1])

    feats = {
        "ret_5d": _trailing_return(close, 5),
        "ret_21d": _trailing_return(close, 21),
        "ret_63d": _trailing_return(close, 63),
        "vol_21d": vol_21d,
        "vol_ratio_5d_63d": vol_5d / vol_63d if vol_63d > 0 else np.nan,
        "volume_ratio_5d_63d": vol_avg_5d / vol_avg_63d if vol_avg_63d > 0 else np.nan,
        "abs_ret_mean_21d": float(daily_ret.tail(21).abs().mean()),
        "dist_52w_high": last / high_52w - 1.0 if high_52w > 0 else np.nan,
        "dist_52w_low": last / low_52w - 1.0 if low_52w > 0 else np.nan,
    }
    if any(isinstance(v, float) and math.isnan(v) for v in (feats["ret_63d"],)):
        return None  # not enough usable history for the longest lookback
    return feats
