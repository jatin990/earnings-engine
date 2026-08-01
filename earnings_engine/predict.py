"""Score upcoming earnings events.

Builds feature rows for earnings announcements in the next N days — price
features as of the latest cached trading day, earnings-history features from
the saved labeled dataset — then trains the chosen model on ALL labeled
events and emits direction + calibrated confidence per upcoming event.
"""

import pandas as pd

from earnings_engine.config import Settings, market_of
from earnings_engine.data.earnings import load_earnings, upcoming_earnings
from earnings_engine.data.prices import load_prices
from earnings_engine.dataset import FEATURE_COLUMNS, load_dataset
from earnings_engine.features.earnings_features import compute_earnings_features
from earnings_engine.features.price_features import compute_price_features
from earnings_engine.models.registry import make_model
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.predict")


def build_upcoming_events(tickers: list[str], settings: Settings, days: int = 14) -> pd.DataFrame:
    """Feature rows for upcoming earnings, mirroring the training schema."""
    calendar = upcoming_earnings(tickers, settings, days=days)
    logger.info("building upcoming events tickers=%s days=%s rows=%s", tickers, days, len(calendar))
    if calendar.empty:
        return pd.DataFrame()

    try:
        dataset = load_dataset()
    except FileNotFoundError:
        dataset = pd.DataFrame()

    rows: list[dict] = []
    for _, ev in calendar.iterrows():
        ticker = ev["ticker"]
        prices = load_prices(ticker, settings)
        if prices.empty:
            continue
        asof = prices.index[-1]
        pf = compute_price_features(prices, asof)
        if pf is None:
            continue
        past = (
            dataset[dataset["ticker"] == ticker].sort_values("earnings_date")
            if not dataset.empty
            else pd.DataFrame(columns=["reaction_return"])
        )
        ef = compute_earnings_features(past, load_earnings(ticker, settings), ev["earnings_date"])
        rows.append({
            "ticker": ticker,
            "market": market_of(ticker),
            "earnings_date": ev["earnings_date"],
            "asof_date": asof,
            **pf,
            **ef,
            "is_in_market": int(market_of(ticker) == "IN"),
        })
    logger.info("built upcoming feature rows rows=%s", len(rows))
    return pd.DataFrame(rows)


def predict_upcoming(
    tickers: list[str],
    settings: Settings,
    model_name: str = "gbm",
    days: int = 14,
) -> pd.DataFrame:
    """Train on all labeled events and score upcoming ones.

    Returns one row per upcoming event with direction ('UP'/'DOWN'),
    p_up, and confidence = max(p_up, 1 - p_up), sorted by confidence.
    """
    upcoming = build_upcoming_events(tickers, settings, days=days)
    if upcoming.empty:
        logger.info("predict_upcoming skipped: no upcoming events")
        return pd.DataFrame()

    train = load_dataset()
    model = make_model(model_name).fit(train)
    p_up = model.predict_proba(upcoming)

    out = upcoming[["ticker", "market", "earnings_date", "asof_date"]].copy()
    out["p_up"] = p_up
    out["direction"] = ["UP" if p >= 0.5 else "DOWN" for p in p_up]
    out["confidence"] = [max(p, 1 - p) for p in p_up]
    out["n_past_events"] = upcoming["n_past_events"].values
    out["model"] = model_name
    out["train_events"] = len(train)
    logger.info("predict_upcoming completed rows=%s train_events=%s", len(out), len(train))
    return out.sort_values("confidence", ascending=False).reset_index(drop=True)
