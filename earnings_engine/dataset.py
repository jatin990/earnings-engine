"""Event dataset builder: one row per ticker x past earnings event.

Each row contains identifiers, point-in-time features (price/volume as of the
last trading day before the announcement, plus earnings-history features from
strictly earlier events), and the realized 1-day reaction label.

Output: data/cache/dataset.parquet
"""

import pandas as pd

from earnings_engine.config import CACHE_DIR, Settings, market_of
from earnings_engine.data.earnings import load_earnings
from earnings_engine.data.prices import load_prices
from earnings_engine.features.earnings_features import EARNINGS_FEATURES, compute_earnings_features
from earnings_engine.features.price_features import PRICE_FEATURES, compute_price_features
from earnings_engine.labels import compute_reaction

DATASET_PATH = CACHE_DIR / "dataset.parquet"

ID_COLUMNS = ["ticker", "market", "earnings_date", "asof_date", "reaction_date"]
LABEL_COLUMNS = ["reaction_return", "label"]
FEATURE_COLUMNS = PRICE_FEATURES + EARNINGS_FEATURES + ["is_in_market"]


def build_ticker_events(ticker: str, settings: Settings) -> pd.DataFrame:
    """Build event rows for one ticker from cached data (no network)."""
    prices = load_prices(ticker, settings)
    earnings = load_earnings(ticker, settings)
    if prices.empty or earnings.empty:
        return pd.DataFrame()

    today = pd.Timestamp.today().normalize()
    rows: list[dict] = []
    for _, ev in earnings.iterrows():
        edate = ev["earnings_date"]
        if edate >= today:
            continue  # upcoming events have no label; handled in Phase 5
        reaction = compute_reaction(prices, edate)
        if reaction is None:
            continue
        pf = compute_price_features(prices, reaction.asof_date)
        if pf is None:
            continue
        past = pd.DataFrame(rows)  # earlier events only — rows is chronological
        ef = compute_earnings_features(past if not past.empty else pd.DataFrame(columns=["reaction_return"]),
                                       earnings, edate)
        rows.append({
            "ticker": ticker,
            "market": market_of(ticker),
            "earnings_date": edate,
            "asof_date": reaction.asof_date,
            "reaction_date": reaction.reaction_date,
            **pf,
            **ef,
            "is_in_market": int(market_of(ticker) == "IN"),
            "reaction_return": reaction.reaction_return,
            "label": reaction.label,
        })
    return pd.DataFrame(rows)


def build_dataset(tickers: list[str], settings: Settings, save: bool = True) -> pd.DataFrame:
    """Build the full event dataset across tickers and optionally save it."""
    frames = [df for t in tickers if not (df := build_ticker_events(t, settings)).empty]
    if not frames:
        return pd.DataFrame()
    dataset = pd.concat(frames, ignore_index=True)
    dataset = dataset.sort_values(["earnings_date", "ticker"]).reset_index(drop=True)
    if save:
        DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        dataset.to_parquet(DATASET_PATH)
    return dataset


def load_dataset() -> pd.DataFrame:
    """Load the saved event dataset."""
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"No dataset at {DATASET_PATH}. Run `earnings-engine build-dataset` first."
        )
    return pd.read_parquet(DATASET_PATH)
