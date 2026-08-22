"""Playground #3 — Kronos prediction sandbox.

Exercises the Kronos AI prediction pipeline the same way earnings-engine does:
- Single-stock 14-day forecast (``predict_single_stock``)
- Batch portfolio prediction (``predict_portfolio`` — the bulk action, 4 workers)
- Watchlist batch generation (``generate_watchlist_kronos`` — the bulk Watchlist API)
- Audit-trail persistence (``data/predictions.py`` — store / history / latest / delete)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root:  python playground/03_kronos_playground.py
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from earnings_engine.api.dashboard_api import generate_watchlist_kronos
from earnings_engine.data.predictions import load_latest_predictions, load_prediction_history
from earnings_engine.kronos_predictor import predict_portfolio, predict_single_stock
from playground.playground_utils import C, err, heading, info, ok, prompt_yes_no, prompt_ticker, subheading, summarize_predictions, warn


def try_single_stock(symbol: str) -> None:
    subheading(f"Single-stock 14-day Kronos forecast: {symbol}")
    result = predict_single_stock(symbol, lookback=120, pred_len=14)
    if result is None:
        err(f"Prediction failed for {symbol}. Is the Kronos library available?")
        return
    summarize_predictions([result])
    ok(f"full payload keys: {sorted(result.keys())}")


def try_portfolio(symbols: list[str]) -> None:
    subheading("Bulk action: predict_portfolio (ThreadPoolExecutor, 4 workers)")
    info(f"Running on {len(symbols)} symbols: {', '.join(symbols)}")
    forecasts = predict_portfolio(symbols, lookback=120, pred_len=14)
    summarize_predictions(forecasts)
    ok(f"generated {len(forecasts)} forecasts")


def try_watchlist_batch() -> None:
    subheading("Bulk action: generate_watchlist_kronos (Watchlist API)")
    result = generate_watchlist_kronos()
    if result.get("success"):
        ok(f"generated {result['generated']} forecasts from watchlist")
        summarize_predictions(result.get("forecasts", []))
    else:
        warn(f"watchlist generation: {result.get('error', 'unknown error')}")


def show_audit_trail() -> None:
    subheading("Audit trail (kronos_predictions table)")
    history = load_prediction_history(limit=10)
    if not history:
        warn("No stored predictions yet (run one of the prediction above first).")
        return
    info(f"{len(history)} most-recent audit rows:")
    for row in history:
        print(
            f"  {C.BOLD}{row['ticker']}{C.RESET} run_at={row['run_at']} "
            f"return_pct={row.get('return_pct')} trend={row.get('trend')}"
        )

    latest = load_latest_predictions()
    if latest:
        info(f"Latest per ticker: {', '.join(r['ticker'] for r in latest)}")


def main() -> None:
    heading("Kronos Playground (bulk predictions + audit)")

    symbol = sys.argv[1] if len(sys.argv) > 1 else prompt_ticker("RELIANCE.NS")

    try_single_stock(symbol)

    if prompt_yes_no("Also run the bulk predict_portfolio on a small basket?", default=False):
        basket = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
        try_portfolio(basket)

    if prompt_yes_no("Also generate predictions for the whole watchlist? (can be slow)", default=False):
        try_watchlist_batch()

    show_audit_trail()

    heading("Done")
    info(
        "Kronos uses NeoQuasar/Kronos-base + Kronos-Tokenizer-base. "
        "Bulk actions live in kronos_predictor.py (predict_portfolio) and "
        "api/dashboard_api.py (generate_watchlist_kronos)."
    )


if __name__ == "__main__":
    main()