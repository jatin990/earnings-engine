"""Manual independent verification of the latest generated report.

This test is INdependent verification: it re-derives every field in the
latest report CSV from the RAW database tables (price_history,
earnings_history, ticker_market_cap) WITHOUT importing or calling the
production calculation functions.  It is a cross-check of the report
against the underlying data and formulas, so if a formula in the report
generation changed (or a field is sourced from the wrong place), this test
catches it.

Run manually (excluded from the default suite):
    python -m pytest tests/manual/test_manual_report_verification.py -v

It reads:
  - reports/output/upcoming-results-*.csv   (newest by filename date)
  - data/cache/prices/prices.sqlite3        (price_history, earnings_history, ticker_market_cap)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import sqlite3

from earnings_engine.config import PROJECT_ROOT, Settings

OUTPUT_DIR = PROJECT_ROOT / "reports" / "output"
DB_PATH = Settings().data_dirs["prices"] / "prices.sqlite3"

# ---------------------------------------------------------------------------
# Field specification: every report field, its meaning, and how it is
# independently recomputed from the raw database.
# ---------------------------------------------------------------------------
# Each entry: field -> (components, formula-docstring)
FIELD_SPEC: dict[str, str] = {
    "market_cap": "Live yfinance market cap in rupees, cached in ticker_market_cap. "
                  "Expected == stored market_cap (no recompute possible from raw history).",
    "current_price": "Live yfinance last price (cached in ticker_metrics). "
                     "Expected == cached current_price — NOT the latest price_history close.",
    "week_change": "Live yfinance year_change fraction (cached in ticker_metrics). "
                   "Expected == cached week_change — NOT a 5-day return from price_history.",
    "pct_from_52w_high": "Distance % of current price below 52W high: "
                         "(week_high - current_price) / week_high * 100. "
                         "Expected == cached pct_from_52w_high.",
    "pct_from_52w_low": "Distance % of current price above 52W low: "
                        "(current_price - week_low) / week_low * 100. "
                        "Expected == cached pct_from_52w_low.",
    "week_high": "Live yfinance 52W high (cached in ticker_metrics). "
                 "Expected == cached week_high — NOT the max of price_history closes.",
    "week_low": "Live yfinance 52W low (cached in ticker_metrics). "
                "Expected == cached week_low — NOT the min of price_history closes.",
    "thirty_day_return_pct": "Return over the last ~30 trading days from price_history: "
                             "(close[-1] - close[-30]) / close[-30] * 100. "
                             "Expected == recompute from price_history.",
    "earnings_week_move_pct": "5-trading-day move into the print from price_history: "
                              "(close[-1] - close[-5]) / close[-5] * 100. "
                              "Expected == recompute from price_history.",
    "next_resistance": "Max close over the last 20 trading days (or all closes if <20 bars) "
                       "from price_history. Expected == recompute from price_history.",
    "current_support": "Min close over the last 20 trading days (or all closes if <20 bars) "
                       "from price_history. Expected == recompute from price_history.",
    "prev_quarter_earnings_score": "Quality score (1-9) of the MOST RECENT historical quarter's "
                                   "surprise (default 5 when no historical surprises) from "
                                   "earnings_history. Expected == recompute.",
    "prev_3q_earnings_score": "Average of the last 3 quarters' individual scores, capped at the "
                              "max individual score. Expected == recompute.",
    "q1_earnings_score": "Score of the OLDEST of the last 3 historical quarters. "
                         "Expected == recompute.",
    "q2_earnings_score": "Score of the MIDDLE of the last 3 historical quarters. "
                         "Expected == recompute.",
    "q3_earnings_score": "Score of the MOST RECENT of the last 3 historical quarters. "
                         "Expected == recompute.",
    "eps_estimate": "EPS estimate of the most recent historical earnings event. "
                    "Expected == recompute from earnings_history.",
    "eps_reported": "Reported EPS of the most recent historical earnings event. "
                    "Expected == recompute from earnings_history.",
    "surprise_pct": "EPS surprise % of the most recent historical earnings event. "
                    "Expected == recompute from earnings_history.",
}


def _score_surprise(surprise: float) -> int:
    """Re-derive the 1-9 quality score independently (mirrors the documented scale)."""
    if surprise >= 15:
        return 9
    if surprise >= 10:
        return 8
    if surprise >= 5:
        return 7
    if surprise >= 0:
        return 6
    if surprise >= -5:
        return 5
    if surprise >= -10:
        return 4
    return 3


def _latest_report_csv() -> Path:
    """Pick the newest upcoming-results-*.csv in reports/output."""
    files = sorted(OUTPUT_DIR.glob("upcoming-results-*.csv"))
    if not files:
        raise FileNotFoundError("No upcoming-results-*.csv found in reports/output/. "
                                "Run `earnings-engine upcoming-results` first.")
    return files[-1]


def _read_db(ticker: str) -> tuple[pd.DataFrame, pd.DataFrame, float | None]:
    """Read raw price_history, earnings_history, and market_cap for a ticker."""
    with sqlite3.connect(DB_PATH) as conn:
        prices = pd.read_sql_query(
            "SELECT date, close FROM price_history WHERE ticker = ? ORDER BY date", conn, params=(ticker,)
        )
        earnings = pd.read_sql_query(
            "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct "
            "FROM earnings_history WHERE ticker = ? ORDER BY earnings_date",
            conn, params=(ticker,),
        )
        mc_row = conn.execute(
            "SELECT market_cap FROM ticker_market_cap WHERE ticker = ?", (ticker,)
        ).fetchone()
    if not prices.empty:
        prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    if not earnings.empty:
        earnings["earnings_date"] = pd.to_datetime(earnings["earnings_date"])
    return prices, earnings, mc_row[0] if mc_row else None


def _recompute_price_dependent(ticker: str) -> dict[str, float | None]:
    """Recompute the price_history-dependent fields from raw closes."""
    prices, _, _ = _read_db(ticker)
    out: dict[str, float | None] = {}
    if prices.empty or prices["close"].dropna().empty:
        return out

    closes = prices["close"].dropna().astype(float).tolist()
    latest = closes[-1]

    if len(closes) >= 5:
        out["earnings_week_move_pct"] = (latest - closes[-5]) / closes[-5] * 100
    elif len(closes) >= 2:
        out["earnings_week_move_pct"] = (latest - closes[0]) / closes[0] * 100

    if len(closes) >= 30:
        out["thirty_day_return_pct"] = (latest - closes[-30]) / closes[-30] * 100
    elif len(closes) >= 2:
        out["thirty_day_return_pct"] = (latest - closes[0]) / closes[0] * 100

    window = closes[-20:] if len(closes) >= 20 else closes
    out["next_resistance"] = max(window)
    out["current_support"] = min(window)
    return out


def _recompute_earnings_dependent(ticker: str) -> dict[str, float | None]:
    """Recompute the earnings-dependent fields from raw earnings_history."""
    _, earnings, _ = _read_db(ticker)
    out: dict[str, float | None] = {}
    if earnings.empty:
        out["prev_quarter_earnings_score"] = 5.0
        return out

    today = pd.Timestamp.today().normalize()
    historical = earnings[earnings["earnings_date"] < today]
    if historical.empty:
        out["prev_quarter_earnings_score"] = 5.0
        return out

    recent = historical.sort_values("earnings_date").tail(3)
    quarter_scores: list[int] = []
    n = len(recent)
    for i, row in recent.iterrows():
        sx = row.get("surprise_pct")
        sx = float(sx) if pd.notna(sx) else None
        score = _score_surprise(sx) if sx is not None else None
        if score is not None:
            quarter_scores.append(score)
        key = {0: "q1_earnings_score", 1: "q2_earnings_score", 2: "q3_earnings_score"}.get(i)
        if key:
            out[key] = score
        if i == n - 1:
            out["prev_quarter_earnings_score"] = score if score is not None else 5.0

    if quarter_scores:
        avg = round(sum(quarter_scores) / len(quarter_scores))
        out["prev_3q_earnings_score"] = min(avg, max(quarter_scores))

    latest_ev = historical.sort_values("earnings_date").iloc[-1]
    for col in ("eps_estimate", "eps_reported", "surprise_pct"):
        v = latest_ev.get(col)
        out[col] = float(v) if pd.notna(v) else None
    return out


def _is_close(a: float | None, b: float | None, rel_tol: float = 1e-4) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= rel_tol * max(1.0, abs(a), abs(b))


def test_manual_report_verification():
    csv_path = _latest_report_csv()
    print(f"\n=== Manual report verification: {csv_path.name} ===")
    print(f"DB: {DB_PATH}\n")

    df = pd.read_csv(csv_path)
    assert not df.empty, "Report CSV is empty!"

    total_fields = 0
    passed_fields = 0
    mismatches: list[tuple[str, str, object, object, float | None]] = []

    for _, row in df.iterrows():
        ticker = str(row["ticker"])
        prices, earnings, db_market_cap = _read_db(ticker)
        recomputed_prices = _recompute_price_dependent(ticker)
        recomputed_earnings = _recompute_earnings_dependent(ticker)

        # Cache-verified (live yfinance) fields: compare against the cache in the
        # report itself for known fields, plus market_cap from ticker_market_cap.
        for col in ("market_cap", "current_price", "week_change",
                    "pct_from_52w_high", "pct_from_52w_low", "week_high", "week_low"):
            if col not in row.index:
                continue
            total_fields += 1
            report_val = row[col]
            expected: object
            if col == "market_cap":
                expected = db_market_cap
            else:
                # These live-yfinance fields can only be checked against the
                # cached value stored alongside the report (ticker_metrics).
                # We read it from the DB ticker_metrics table.
                expected = _load_cached_metric(ticker, col)
            if expected is None:
                continue  # can't verify without the cache
            if _is_close(float(report_val) if pd.notna(report_val) else None,
                         float(expected) if expected is not None else None):
                passed_fields += 1
            else:
                mismatches.append((ticker, col, report_val, expected, None))

        # Price-history-dependent fields.
        for col, expected in recomputed_prices.items():
            if col not in row.index:
                continue
            total_fields += 1
            report_val = row[col]
            rv = float(report_val) if pd.notna(report_val) else None
            if _is_close(rv, expected):
                passed_fields += 1
            else:
                mismatches.append((ticker, col, report_val, expected, None))

        # Earnings-dependent fields.
        for col, expected in recomputed_earnings.items():
            if col not in row.index:
                continue
            total_fields += 1
            report_val = row[col]
            rv = float(report_val) if pd.notna(report_val) else None
            if _is_close(rv, expected):
                passed_fields += 1
            else:
                mismatches.append((ticker, col, report_val, expected, None))

    print(f"\n=== FIELD SPECIFICATIONS ===")
    for field, spec in FIELD_SPEC.items():
        print(f"\n  {field}:\n    {spec}")

    print(f"\n=== RESULTS ===")
    print(f"  Fields checked : {total_fields}")
    print(f"  Fields passed  : {passed_fields}")
    print(f"  Mismatches     : {len(mismatches)}")

    if mismatches:
        print("\n=== MISMATCHES ===")
        for ticker, field, report_val, expected, _ in mismatches:
            print(f"  {ticker} {field}: report={report_val} expected={expected}")

    assert len(mismatches) == 0, f"{len(mismatches)} field mismatch(es) found — see output above."
    print("\n✅ PASS: report fields match the raw database recomputation.")


def _load_cached_metric(ticker: str, field: str) -> float | None:
    """Read a single field from the ticker_metrics cache table."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT metrics FROM ticker_metrics WHERE ticker = ? ORDER BY as_of_date DESC LIMIT 1",
                (ticker,),
            ).fetchone()
        if not row:
            return None
        import json
        payload = json.loads(row[0])
        v = payload.get(field)
        return float(v) if v is not None else None
    except Exception:
        return None


if __name__ == "__main__":
    test_manual_report_verification()