"""Report checker subworkflow.

After a report is generated, this module verifies each field in the report
against the database.  For each field:

1. Compare the report value against the cached database value (or a
   recomputation from the raw data source).
2. If the report value is empty (None/NaN/blank), re-run the original
   calculation from the raw data source to confirm it is genuinely empty
   (not a bug that dropped data).
3. If the report value differs from the expected value, log an inconsistency.

Field sources are split by their true origin:

- **Cache-verified fields** come from live yfinance data (cached once per day
  in ``ticker_metrics`` / ``ticker_market_cap``): ``current_price``,
  ``week_change``, ``pct_from_52w_high/low``, ``week_high``, ``week_low``,
  ``market_cap``.  These are compared against the cache only — recomputing
  them from the cached OHLC ``price_history`` would compare against stale or
  different data and produce false inconsistencies.
- **Price-history-recomputed fields** genuinely come from the cached OHLC
  closes in production: ``thirty_day_return_pct``, ``earnings_week_move_pct``,
  ``next_resistance``, ``current_support``.  These are recomputed from
  ``price_history``.
- **Earnings-derived fields** come from the cached ``earnings_history``:
  ``prev_quarter_earnings_score``, ``prev_3q_earnings_score``,
  ``q1/q2/q3_earnings_score``, ``eps_estimate``, ``eps_reported``,
  ``surprise_pct``.  These are recomputed from ``earnings_history``.

The checker is opt-in (``--check`` on ``upcoming-results`` or the standalone
``check-report`` command) so normal report generation is not slowed down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.earnings import load_earnings
from earnings_engine.data.market_context import _score_surprise
from earnings_engine.data.prices import load_prices
from earnings_engine.data.universe import load_market_cap
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.reports.checker")

# Fields that come from live yfinance data, cached once per day in
# ticker_metrics / ticker_market_cap.  These are compared against the cache
# only — never recomputed from price_history (which would be stale/different).
_CACHED_FIELD_SOURCES: dict[str, str] = {
    "market_cap": "market_cap",
    "current_price": "current_price",
    "week_change": "week_change",
    "pct_from_52w_high": "pct_from_52w_high",
    "pct_from_52w_low": "pct_from_52w_low",
    "week_high": "week_high",
    "week_low": "week_low",
}

# Fields that genuinely come from the cached OHLC closes in production.
# These are recomputed from price_history.
_PRICE_HISTORY_FIELDS = [
    "thirty_day_return_pct",
    "earnings_week_move_pct",
    "next_resistance",
    "current_support",
]

# Fields that come from the cached earnings_history.
_EARNINGS_DERIVED_FIELDS = [
    "prev_quarter_earnings_score",
    "prev_3q_earnings_score",
    "q1_earnings_score",
    "q2_earnings_score",
    "q3_earnings_score",
    "eps_estimate",
    "eps_reported",
    "surprise_pct",
]

# Week high/low date fields (stored as strings in cache)
_WEEK_DATE_FIELDS = [
    "q1_week_high_date", "q1_week_low_date",
    "q2_week_high_date", "q2_week_low_date",
    "q3_week_high_date", "q3_week_low_date",
    "last_week_high_date", "last_week_low_date",
]

# 7-day post-earnings price fields
_PRICE_7D_FIELDS = [
    "q1_price_7d", "q2_price_7d", "q3_price_7d",
]


@dataclass
class Inconsistency:
    """A single field that did not match the expected value."""

    ticker: str
    field: str
    report_value: object
    expected_value: object
    reason: str


@dataclass
class CheckResult:
    """Aggregated result of a report check."""

    verified: int = 0
    verified_empty: int = 0
    unverified: int = 0
    inconsistencies: list[Inconsistency] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"verified={self.verified} verified_empty={self.verified_empty} "
            f"unverified={self.unverified} inconsistencies={len(self.inconsistencies)}"
        )


def _is_empty(value: object) -> bool:
    """Return True if a value is None, NaN, or a blank string."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _to_float(value: object) -> float | None:
    """Safely convert a value to float, handling strings like '4.2%'."""
    if _is_empty(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().rstrip("%").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _close(a: object, b: object, rel_tol: float = 1e-6) -> bool:
    """Compare two numeric values with a relative tolerance."""
    fa = _to_float(a)
    fb = _to_float(b)
    if fa is None or fb is None:
        return fa is None and fb is None
    return abs(fa - fb) <= rel_tol * max(1.0, abs(fa), abs(fb))


def _recompute_price_history_fields(ticker: str, settings: Settings) -> dict[str, object]:
    """Recompute price-history-derived fields from raw cached prices.

    Only the fields that genuinely come from the cached OHLC closes in
    production are recomputed here (thirty_day_return_pct,
    earnings_week_move_pct, next_resistance, current_support).
    """
    prices = load_prices(ticker, settings)
    out: dict[str, object] = {}
    if prices.empty or "close" not in prices.columns:
        return out

    closes = pd.to_numeric(prices["close"], errors="coerce").dropna()
    if closes.empty:
        return out

    latest = float(closes.iloc[-1])

    if len(closes) >= 2:
        prior_week = float(closes.iloc[-5]) if len(closes) >= 5 else float(closes.iloc[0])
        out["earnings_week_move_pct"] = ((latest - prior_week) / prior_week) * 100 if prior_week else None

    if len(closes) >= 30:
        prior_30 = float(closes.iloc[-30])
        out["thirty_day_return_pct"] = ((latest - prior_30) / prior_30) * 100 if prior_30 else None
    elif len(closes) >= 2:
        prior_30 = float(closes.iloc[0])
        out["thirty_day_return_pct"] = ((latest - prior_30) / prior_30) * 100 if prior_30 else None

    recent_high = float(closes.tail(20).max()) if len(closes) >= 20 else float(closes.max())
    recent_low = float(closes.tail(20).min()) if len(closes) >= 20 else float(closes.min())
    out["next_resistance"] = recent_high
    out["current_support"] = recent_low
    return out


def _recompute_earnings_fields(ticker: str, settings: Settings) -> dict[str, object]:
    """Recompute earnings-derived fields from raw cached earnings.

    Replicates the production formulas in ``enrich_upcoming_results()``:
    - q1/q2/q3_earnings_score = per-quarter _score_surprise on the last 3
      quarters (oldest -> newest), excluding upcoming events with null surprise.
    - prev_quarter_earnings_score = most recent quarter's score (default 5
      when there is no historical data).
    - prev_3q_earnings_score = average of individual quarter scores, capped
      at the max individual score.
    - eps_estimate / eps_reported / surprise_pct = from the most recent
      historical earnings event.
    - week high/low dates and 7-day post-earnings prices from price_history.
    """
    from earnings_engine.data.prices import load_prices
    
    earnings = load_earnings(ticker, settings)
    out: dict[str, object] = {}

    if earnings.empty:
        out["prev_quarter_earnings_score"] = 5
        return out

    # Use ALL earnings (including upcoming with null surprise), matching
    # the production code in enrich_upcoming_results() which does:
    #   recent_earnings = earnings.sort_values("earnings_date").tail(3)
    # The null surprises are handled gracefully (score becomes None).
    recent_earnings = earnings.sort_values("earnings_date").tail(3)
    quarter_scores: list[int] = []
    n_quarters = len(recent_earnings)
    for i, (_, qrow) in enumerate(recent_earnings.iterrows()):
        surprise = pd.to_numeric(qrow.get("surprise_pct", 0), errors="coerce")
        score = _score_surprise(float(surprise)) if pd.notna(surprise) else None
        if score is not None:
            quarter_scores.append(score)

        # q1 = oldest of the 3, q2 = middle, q3 = most recent
        if i == 0:
            out["q1_earnings_score"] = score
        elif i == 1:
            out["q2_earnings_score"] = score
        elif i == 2:
            out["q3_earnings_score"] = score

        if i == n_quarters - 1:
            out["prev_quarter_earnings_score"] = score if score is not None else 5

    if quarter_scores:
        avg = round(sum(quarter_scores) / len(quarter_scores))
        out["prev_3q_earnings_score"] = min(avg, max(quarter_scores))

    # EPS fields come from the most recent **historical** earnings event
    # (exclude upcoming/future events where these values are naturally null).
    # This matches the production logic in enrich_upcoming_results().
    today = pd.Timestamp.today().normalize()
    historical = earnings[earnings["earnings_date"] < today]
    if not historical.empty:
        latest_earnings = historical.sort_values("earnings_date").iloc[-1]
        out["eps_estimate"] = latest_earnings.get("eps_estimate")
        out["eps_reported"] = latest_earnings.get("eps_reported")
        out["surprise_pct"] = latest_earnings.get("surprise_pct")
    else:
        out["eps_estimate"] = None
        out["eps_reported"] = None
        out["surprise_pct"] = None

    # Recompute week high/low dates and 7-day prices from price_history
    prices = load_prices(ticker, settings)
    if not prices.empty:
        for i, (_, qrow) in enumerate(recent_earnings.iterrows()):
            earnings_date = qrow["earnings_date"]
            
            # Week high/low dates
            from earnings_engine.data.market_context import _week_high_low_around
            week_data = _week_high_low_around(prices, earnings_date)
            if week_data is not None:
                high_pct, low_pct, high_price, low_price, high_date, low_date = week_data
                if i == 0:
                    out["q1_week_high_date"] = high_date.strftime("%Y-%m-%d") if high_date is not None else None
                    out["q1_week_low_date"] = low_date.strftime("%Y-%m-%d") if low_date is not None else None
                elif i == 1:
                    out["q2_week_high_date"] = high_date.strftime("%Y-%m-%d") if high_date is not None else None
                    out["q2_week_low_date"] = low_date.strftime("%Y-%m-%d") if low_date is not None else None
                elif i == 2:
                    out["q3_week_high_date"] = high_date.strftime("%Y-%m-%d") if high_date is not None else None
                    out["q3_week_low_date"] = low_date.strftime("%Y-%m-%d") if low_date is not None else None
            
            # 7-day post-earnings price
            from earnings_engine.data.market_context import _price_after_earnings
            price_7d = _price_after_earnings(prices, earnings_date, days=7)
            if i == 0:
                out["q1_price_7d"] = price_7d
            elif i == 1:
                out["q2_price_7d"] = price_7d
            elif i == 2:
                out["q3_price_7d"] = price_7d

    return out


def _check_field(
    ticker: str,
    field: str,
    report_value: object,
    expected_value: object,
    result: CheckResult,
) -> None:
    """Check a single field and record the outcome."""
    if _is_empty(report_value):
        # Report value is empty.  Re-run the original calculation to confirm
        # it is genuinely empty (not a bug that dropped data).
        if _is_empty(expected_value):
            result.verified_empty += 1
        else:
            result.inconsistencies.append(
                Inconsistency(
                    ticker=ticker,
                    field=field,
                    report_value=report_value,
                    expected_value=expected_value,
                    reason="report field is empty but the original source has a value",
                )
            )
    elif _is_empty(expected_value):
        result.inconsistencies.append(
            Inconsistency(
                ticker=ticker,
                field=field,
                report_value=report_value,
                expected_value=expected_value,
                reason="report field has a value but the original source is empty",
            )
        )
    elif _close(report_value, expected_value):
        result.verified += 1
    else:
        result.inconsistencies.append(
            Inconsistency(
                ticker=ticker,
                field=field,
                report_value=report_value,
                expected_value=expected_value,
                reason="report value differs from the original source",
            )
        )


def check_report_frame(df: pd.DataFrame, settings: Settings | None = None) -> CheckResult:
    """Verify every field in an enriched report DataFrame against the database.

    For each row, each known field is checked against the cached database value
    (or a recomputation from the raw data source).  Empty report fields are
    re-verified against the original source to confirm they are genuinely empty.
    """
    settings = settings or Settings()
    result = CheckResult()

    if df.empty:
        return result

    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        if not ticker:
            continue

        # 1) Cache-verified fields (live-yfinance-derived, cached once per day).
        #    These are compared against the cache only.  If the cache has no
        #    value (e.g. never computed, or a new day), the field is marked
        #    unverified rather than falsely flagged as an inconsistency.
        from earnings_engine.data.prices import load_price_metrics

        cached = load_price_metrics(ticker, settings) or {}
        for field, cache_key in _CACHED_FIELD_SOURCES.items():
            if field not in row.index:
                continue
            expected = cached.get(cache_key)
            if field == "market_cap" and expected is None:
                expected = load_market_cap(ticker, settings)
            if _is_empty(expected):
                result.unverified += 1
                continue
            _check_field(ticker, field, row.get(field), expected, result)

        # 2) Price-history-recomputed fields (genuinely from cached OHLC closes).
        recomputed_prices = _recompute_price_history_fields(ticker, settings)
        for field in _PRICE_HISTORY_FIELDS:
            if field not in row.index:
                continue
            expected = recomputed_prices.get(field)
            _check_field(ticker, field, row.get(field), expected, result)

        # 3) Earnings-derived fields (from cached earnings_history).
        recomputed_earnings = _recompute_earnings_fields(ticker, settings)
        for field in _EARNINGS_DERIVED_FIELDS:
            if field not in row.index:
                continue
            expected = recomputed_earnings.get(field)
            _check_field(ticker, field, row.get(field), expected, result)

        # 4) Week high/low date fields (stored as strings).
        for field in _WEEK_DATE_FIELDS:
            if field not in row.index:
                continue
            expected = recomputed_earnings.get(field)
            _check_field(ticker, field, row.get(field), expected, result)

        # 5) 7-day post-earnings price fields.
        for field in _PRICE_7D_FIELDS:
            if field not in row.index:
                continue
            expected = recomputed_earnings.get(field)
            _check_field(ticker, field, row.get(field), expected, result)

    return result


def check_report_csv(csv_path: Path, settings: Settings | None = None) -> CheckResult:
    """Load a report CSV and run the checker on it.
    
    Also checks for a .cache.json sidecar to detect if the underlying
    cache changed between report generation and checking.
    """
    df = pd.read_csv(csv_path)
    result = check_report_frame(df, settings)
    
    # Check for cache-versioning sidecar
    snapshot_path = csv_path.with_suffix(".cache.json")
    if snapshot_path.exists():
        try:
            import json
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            _check_cache_freshness(df, snapshot, result)
        except Exception:
            pass
    
    return result


def _check_cache_freshness(df: pd.DataFrame, snapshot: dict, result: CheckResult) -> None:
    """Compare current cache state against the snapshot to detect stale reports."""
    from earnings_engine.data.earnings import load_earnings
    from earnings_engine.data.prices import load_price_metrics
    from earnings_engine.data.universe import load_market_cap
    from earnings_engine.config import Settings

    settings = Settings()
    tickers = df["ticker"].dropna().unique().tolist() if "ticker" in df.columns else []
    
    for ticker in tickers:
        # Check if earnings cache changed
        snapshot_max_date = snapshot.get("earnings_freshness", {}).get(ticker)
        if snapshot_max_date:
            try:
                earnings = load_earnings(ticker, settings)
                if not earnings.empty:
                    current_max_date = earnings["earnings_date"].max().isoformat()
                    if current_max_date != snapshot_max_date:
                        result.inconsistencies.append(Inconsistency(
                            ticker=ticker,
                            field="earnings_cache",
                            report_value=snapshot_max_date,
                            expected_value=current_max_date,
                            reason="earnings cache changed since report was generated (stale report)",
                        ))
            except Exception:
                pass
        
        # Check if price metrics cache changed
        snapshot_price_date = snapshot.get("price_metrics_dates", {}).get(ticker)
        if snapshot_price_date:
            try:
                metrics = load_price_metrics(ticker, settings)
                if metrics:
                    current_date = str(metrics.get("as_of_date", ""))
                    if current_date != snapshot_price_date:
                        result.inconsistencies.append(Inconsistency(
                            ticker=ticker,
                            field="price_metrics_cache",
                            report_value=snapshot_price_date,
                            expected_value=current_date,
                            reason="price metrics cache changed since report was generated (stale report)",
                        ))
            except Exception:
                pass
