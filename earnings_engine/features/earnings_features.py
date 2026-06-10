"""Features from a ticker's own earnings history.

Computed strictly from events that occurred BEFORE the current event's
announcement date, using their already-realized reaction returns.
"""

import numpy as np
import pandas as pd

EARNINGS_FEATURES = [
    "n_past_events",
    "past_reaction_mean",
    "past_reaction_std",
    "past_up_rate",
    "last_reaction_return",
    "last_surprise_pct",
]


def compute_earnings_features(
    past_events: pd.DataFrame,
    earnings: pd.DataFrame,
    earnings_date: pd.Timestamp,
) -> dict:
    """Return earnings-history features for one event.

    `past_events` holds this ticker's earlier events with a
    'reaction_return' column (chronological). `earnings` is the raw cached
    earnings frame, used for the previous event's EPS surprise.
    """
    feats: dict = {
        "n_past_events": len(past_events),
        "past_reaction_mean": np.nan,
        "past_reaction_std": np.nan,
        "past_up_rate": np.nan,
        "last_reaction_return": np.nan,
        "last_surprise_pct": np.nan,
    }
    if len(past_events) > 0:
        r = past_events["reaction_return"]
        feats["past_reaction_mean"] = float(r.mean())
        feats["past_reaction_std"] = float(r.std()) if len(r) > 1 else np.nan
        feats["past_up_rate"] = float((r > 0).mean())
        feats["last_reaction_return"] = float(r.iloc[-1])

    prior = earnings.loc[earnings["earnings_date"] < earnings_date]
    if not prior.empty:
        s = prior.iloc[-1].get("surprise_pct")
        if pd.notna(s):
            feats["last_surprise_pct"] = float(s)
    return feats
