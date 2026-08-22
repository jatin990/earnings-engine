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


def build_upcoming_events(tickers: list[str], settings: Settings, days: int = 14,
                          start_date: str | None = None,
                          progress_callback: callable | None = None) -> pd.DataFrame:
    """Feature rows for upcoming earnings, mirroring the training schema.

    ``progress_callback(current, total, ticker)`` is invoked once per calendar
    event processed so long-running standalone runs can surface progress.

    The per-event feature work (SQLite price load + feature math) is
    I/O-bound and embarrassingly parallel, so it runs on a thread pool sized
    by ``settings.gbm_feature_workers`` (default 8).
    """
    calendar = upcoming_earnings(tickers, settings, days=days, start_date=start_date)
    logger.info("building upcoming events tickers=%s days=%s start_date=%s rows=%s",
                tickers, days, start_date, len(calendar))
    if calendar.empty:
        return pd.DataFrame()

    try:
        dataset = load_dataset()
    except FileNotFoundError:
        dataset = pd.DataFrame()

    events = [ev for _, ev in calendar.iterrows()]

    def _build_one(event: pd.Series) -> dict | None:
        """Build the feature row for one event. Returns None when skipped."""
        ticker = event["ticker"]
        prices = load_prices(ticker, settings)
        if prices.empty:
            logger.warning("[GBM] Skipping %s: no cached prices", ticker)
            return None
        asof = prices.index[-1]
        pf = compute_price_features(prices, asof)
        if pf is None:
            logger.warning("[GBM] Skipping %s: price features unavailable", ticker)
            return None
        past = (
            dataset[dataset["ticker"] == ticker].sort_values("earnings_date")
            if not dataset.empty
            else pd.DataFrame(columns=["reaction_return"])
        )
        ef = compute_earnings_features(past, load_earnings(ticker, settings), event["earnings_date"])
        return {
            "ticker": ticker,
            "market": market_of(ticker),
            "earnings_date": event["earnings_date"],
            "asof_date": asof,
            **pf,
            **ef,
            "is_in_market": int(market_of(ticker) == "IN"),
        }

    total = len(events)
    completed = 0
    rows: list[dict] = []
    max_workers = max(1, getattr(settings, "gbm_feature_workers", 8))

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_build_one, ev) for ev in events]
        for future in as_completed(futures):
            completed += 1
            row = future.result()
            if row is not None:
                rows.append(row)
            if progress_callback:
                progress_callback(completed, total, row["ticker"] if row else events[completed - 1]["ticker"])

    # Preserve calendar order for deterministic output.
    by_ticker = {row["ticker"]: row for row in rows}
    rows = [by_ticker[ev["ticker"]] for ev in events if ev["ticker"] in by_ticker]
    logger.info("built upcoming feature rows rows=%s", len(rows))
    return pd.DataFrame(rows)


def predict_upcoming(
    tickers: list[str],
    settings: Settings,
    model_name: str = "gbm",
    days: int = 14,
    start_date: str | None = None,
    progress_callback: callable | None = None,
) -> pd.DataFrame:
    """Train on all labeled events and score upcoming ones.

    Returns one row per upcoming event with direction ('UP'/'DOWN'),
    p_up, and confidence = max(p_up, 1 - p_up), sorted by confidence.
    """
    upcoming = build_upcoming_events(tickers, settings, days=days, start_date=start_date,
                                     progress_callback=progress_callback)
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


def get_gbm_predictions_by_ticker(
    tickers: list[str],
    settings: Settings,
    days: int = 14,
    progress_callback: callable | None = None,
) -> dict[str, dict]:
    """Train the GBM model once and return per-ticker predictions for upcoming events.

    Follows the build-dataset chain: the model trains on ``event_dataset`` (built
    by ``dataset.build_dataset`` -> ``build_ticker_events`` -> features), then
    scores the next ``days`` earnings events for ``tickers`` via ``predict_upcoming``.

    Returns a dict ``{ticker: {p_up, direction, confidence, earnings_date,
    train_events}}``.  If the event dataset is missing (FileNotFoundError) the
    return value is ``{"error": "..."}`` so callers can surface a friendly message.
    """
    try:
        df = predict_upcoming(tickers, settings, days=days, progress_callback=progress_callback)
    except FileNotFoundError as e:
        logger.warning("get_gbm_predictions_by_ticker: dataset missing: %s", e)
        return {"error": str(e)}
    except Exception as e:
        logger.warning("get_gbm_predictions_by_ticker failed: %s", e)
        return {"error": str(e)}

    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        t = row["ticker"]
        if t in out:
            continue  # keep the highest-confidence row (sorted desc)
        out[t] = {
            "p_up": round(float(row["p_up"]), 4),
            "direction": str(row["direction"]),
            "confidence": round(float(row["confidence"]), 4),
            "earnings_date": (
                row["earnings_date"].strftime("%Y-%m-%d")
                if hasattr(row["earnings_date"], "strftime")
                else str(row["earnings_date"])
            ),
            "train_events": int(row["train_events"]),
            "model": str(row["model"]),
        }
    return out


def run_gbm_with_cache(
    tickers: list[str],
    settings: Settings,
    days: int = 14,
    progress_callback: callable | None = None,
    force: bool = False,
) -> dict[str, dict]:
    """Run the GBM prediction standalone, persisted to the daily prediction cache.

    This is the GBM half of the "cache data, then run reports" workflow: it uses
    the same ``prediction_cache`` JSON file that ``upcoming-results`` reads, so a
    report rendered later with ``--cache-only`` (or next run of ``upcoming-results``)
    can reuse today's GBM signals without re-training.

    Cache semantics (per-ticker, not all-or-nothing):
        * When ``force=False``, whatever GBM predictions already exist in today's
          cache are reused; only the genuinely missing tickers are scored via
          ``get_gbm_predictions_by_ticker``.
        * On a miss (or ``force=True``), the model is trained on the cached
          labeled dataset, event features are built for the upcoming calendar, and
          the resulting per-ticker GBM map is persisted to today's cache file
          (merged with any existing Kronos entries).

    ``progress_callback(current, total, ticker, status=None)`` is invoked once per
    calendar event while features are being built.
    """
    from earnings_engine.prediction_cache import load_prediction_cache_partial, save_prediction_cache

    gbm_map: dict[str, dict] = {}

    if not force:
        try:
            cached = load_prediction_cache_partial(tickers)
            gbm_map.update(cached.get("gbm") or {})
        except Exception as e:
            logger.warning("[GBM-CACHE] Partial cache read failed; continuing: %s", e)

    missing = [t for t in tickers if t not in gbm_map]
    if not missing:
        logger.info("[GBM-CACHE] Reusing %d GBM predictions from cache (no model run)", len(gbm_map))
        return {t: v for t, v in gbm_map.items() if not v.get("failed")}

    logger.info("[GBM-CACHE] Reusing %d GBM predictions from cache; computing %d new",
                len(gbm_map), len(missing))
    gbm = get_gbm_predictions_by_ticker(missing, settings, days=days, progress_callback=progress_callback)
    if isinstance(gbm, dict) and "error" not in gbm:
        gbm_map.update(gbm)
        # Cache failed tickers (missing from the GBM result — no upcoming
        # events, no prices, etc.) so they're NOT retried on the next run.
        for t in missing:
            if t not in gbm:
                gbm_map[t] = {"failed": True, "ticker": t}
    else:
        logger.warning("[GBM-CACHE] GBM prediction unavailable: %s", gbm.get("error", "unknown"))

    # Return only successful predictions (exclude failed markers).
    result_map = {t: v for t, v in gbm_map.items() if not v.get("failed")}

    try:
        save_prediction_cache({}, gbm_map)
        logger.info("[GBM-CACHE] Saved %d GBM predictions to daily cache", len(result_map))
    except Exception as e:
        logger.warning("[GBM-CACHE] Failed to save GBM cache: %s", e)
    return result_map
