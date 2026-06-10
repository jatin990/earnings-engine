"""Walk-forward event backtester.

Folds are cut by calendar time on earnings_date: train on everything before
the fold start, test on the fold window, step forward. The model is refit
each fold, so every prediction uses only information available at the time —
the temporal analogue of the point-in-time feature guarantee.

Trade simulation per event: go long if P(up) >= threshold, short if
P(up) <= 1 - threshold, otherwise skip. Trade return = ±reaction_return
minus round-trip cost.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from earnings_engine.models.base import DirectionModel


@dataclass
class BacktestConfig:
    initial_train_frac: float = 0.4   # first 40% of events (by time) = first train set
    test_window_days: int = 90        # each fold tests one quarter
    threshold: float = 0.5            # min confidence to trade (0.5 = trade everything)
    cost_per_trade: float = 0.001     # 10 bps round trip (slippage + fees)


@dataclass
class BacktestResult:
    predictions: pd.DataFrame         # per-event: proba, side, trade_return
    metrics: dict = field(default_factory=dict)
    fold_metrics: pd.DataFrame | None = None


def _make_folds(dataset: pd.DataFrame, cfg: BacktestConfig) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    dates = dataset["earnings_date"]
    start = dates.iloc[int(len(dataset) * cfg.initial_train_frac)]
    folds = []
    cur = start
    end = dates.max()
    while cur <= end:
        nxt = cur + pd.Timedelta(days=cfg.test_window_days)
        folds.append((cur, nxt))
        cur = nxt
    return folds


def run_backtest(dataset: pd.DataFrame, model: DirectionModel, cfg: BacktestConfig | None = None) -> BacktestResult:
    cfg = cfg or BacktestConfig()
    df = dataset.sort_values("earnings_date").reset_index(drop=True)

    parts = []
    for fold_start, fold_end in _make_folds(df, cfg):
        train = df[df["earnings_date"] < fold_start]
        test = df[(df["earnings_date"] >= fold_start) & (df["earnings_date"] < fold_end)]
        if train.empty or test.empty:
            continue
        proba = model.fit(train).predict_proba(test)
        part = test[["ticker", "market", "earnings_date", "reaction_return", "label"]].copy()
        part["proba"] = proba
        part["fold_start"] = fold_start
        parts.append(part)

    if not parts:
        return BacktestResult(predictions=pd.DataFrame(), metrics={})

    preds = pd.concat(parts, ignore_index=True)
    # Trade side: +1 long, -1 short, 0 skip.
    preds["side"] = np.where(
        preds["proba"] >= cfg.threshold, 1,
        np.where(preds["proba"] <= 1 - cfg.threshold, -1, 0),
    )
    traded = preds["side"] != 0
    preds["trade_return"] = np.where(
        traded, preds["side"] * preds["reaction_return"] - cfg.cost_per_trade, 0.0
    )

    return BacktestResult(
        predictions=preds,
        metrics=compute_metrics(preds),
        fold_metrics=preds.groupby("fold_start", as_index=False).apply(
            lambda g: pd.Series(compute_metrics(g)), include_groups=False
        ),
    )


def compute_metrics(preds: pd.DataFrame) -> dict:
    """Summary metrics over a set of per-event predictions."""
    traded = preds[preds["side"] != 0]
    n_events = len(preds)
    n_traded = len(traded)
    out = {
        "n_events": n_events,
        "n_traded": n_traded,
        "coverage": n_traded / n_events if n_events else 0.0,
        "hit_rate": np.nan,
        "avg_trade_return": np.nan,
        "total_return": np.nan,
        "sharpe_per_event": np.nan,
        "base_up_rate": float(preds["label"].mean()) if n_events else np.nan,
    }
    if n_traded:
        correct = (traded["side"] == np.where(traded["reaction_return"] > 0, 1, -1))
        r = traded["trade_return"]
        out["hit_rate"] = float(correct.mean())
        out["avg_trade_return"] = float(r.mean())
        out["total_return"] = float(r.sum())
        # Per-event Sharpe (not annualized — events are irregularly spaced).
        out["sharpe_per_event"] = float(r.mean() / r.std()) if r.std() > 0 else np.nan
    return out
