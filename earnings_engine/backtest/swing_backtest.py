"""Swing-channel backtesting engine.

Simulates the multi-factor swing strategy on historical OHLCV data:
  1. Rolling 20-day support / resistance channel detection
  2. Buy Zone entry (channel position ≤ 0.25)
  3. Volume surge confirmation (vol ≥ 1.25× SMA₂₀)
  4. Optional news-sentiment filter (AI score ≥ 0)
  5. Fixed-fractional position sizing (risk 1.5 % equity per trade)
  6. Exits: stop-loss, take-profit at resistance, time-stop (21 bars)

All timestamps and prices come from the existing prices.sqlite3 store so
results are reproducible and consistent with the rest of the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.prices import load_prices, load_prices_batch
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.backtest.swing_backtest")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SwingBacktestConfig:
    """All tuneable knobs for the swing-channel backtest."""

    initial_capital: float = 100_000.0
    risk_per_trade_pct: float = 0.015          # risk 1.5 % equity per trade
    commission_bps: float = 10.0               # 0.10 % per side
    slippage_bps: float = 5.0                  # 0.05 % estimated slippage
    stop_loss_buffer_pct: float = 0.02         # stop sits 2 % below support
    take_profit_ratio: float = 0.985           # exit at 98.5 % of resistance
    max_hold_days: int = 21                    # time-stop after 21 bars
    max_open_positions: int = 8                # portfolio concentration limit
    max_position_pct: float = 0.15             # max 15 % of equity in one stock
    channel_lookback: int = 20                 # rolling window for S/R
    buy_zone_threshold: float = 0.25           # channel-position entry ceiling
    volume_surge_mult: float = 1.25            # vol ≥ 1.25× SMA₂₀
    use_sentiment_filter: bool = False         # require sentiment ≥ 0
    lookback_months: int = 6                   # how much OHLCV history to use


# ---------------------------------------------------------------------------
# Trade / Result data-classes
# ---------------------------------------------------------------------------

@dataclass
class SwingTrade:
    """One completed (or force-closed) swing trade."""

    ticker: str
    entry_date: str
    entry_price: float
    size: int
    stop_loss: float
    take_profit: float
    exit_date: str | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    hold_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "entry_date": self.entry_date,
            "entry_price": round(self.entry_price, 2),
            "size": self.size,
            "stop_loss": round(self.stop_loss, 2),
            "take_profit": round(self.take_profit, 2),
            "exit_date": self.exit_date,
            "exit_price": round(self.exit_price, 2) if self.exit_price else None,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 2),
            "exit_reason": self.exit_reason,
            "hold_days": self.hold_days,
        }


@dataclass
class SwingBacktestResult:
    """Everything the UI / CLI needs to render the backtest output."""

    initial_capital: float = 0.0
    final_capital: float = 0.0
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl_pct: float = 0.0
    avg_hold_days: float = 0.0
    trades: list[SwingTrade] = field(default_factory=list)
    equity_curve: dict[str, float] = field(default_factory=dict)
    config_used: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_trades": self.total_trades,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "avg_trade_pnl_pct": self.avg_trade_pnl_pct,
            "avg_hold_days": self.avg_hold_days,
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": self.equity_curve,
            "config_used": self.config_used,
        }


# ---------------------------------------------------------------------------
# Channel computation
# ---------------------------------------------------------------------------

def compute_channel(
    df: pd.DataFrame,
    lookback: int = 20,
) -> pd.DataFrame:
    """Add rolling support / resistance / channel-position columns.

    ``df`` must have columns ``[close]`` and optionally ``[high, low]``.
    All indicators are **shifted by 1 bar** to avoid look-ahead bias.
    """
    out = df.copy()

    # Use high/low if available, else fall back to close
    highs = out["high"] if "high" in out.columns else out["close"]
    lows = out["low"] if "low" in out.columns else out["close"]

    out["ch_resistance"] = highs.rolling(lookback, min_periods=lookback).max().shift(1)
    out["ch_support"] = lows.rolling(lookback, min_periods=lookback).min().shift(1)

    spread = out["ch_resistance"] - out["ch_support"]
    spread = spread.replace(0, np.nan)
    out["ch_position"] = (out["close"] - out["ch_support"]) / spread

    return out


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

def run_swing_backtest(
    tickers: list[str],
    cfg: SwingBacktestConfig | None = None,
    settings: Settings | None = None,
) -> SwingBacktestResult:
    """Run the swing-channel backtest across *tickers*.

    1. Loads OHLCV from prices.sqlite3 for each ticker.
    2. Merges into a single date-sorted frame.
    3. Walks bar-by-bar simulating entries, exits, and position sizing.
    4. Returns structured results with equity curve and trade log.
    """
    cfg = cfg or SwingBacktestConfig()
    settings = settings or Settings()

    # --- Load & prepare price data in batch ---------------------------------
    frames: list[pd.DataFrame] = []
    batch_prices = load_prices_batch(tickers, settings)
    for ticker in tickers:
        raw = batch_prices.get(ticker)
        if raw is None or raw.empty:
            raw = load_prices(ticker, settings)
        if raw is None or raw.empty:
            logger.debug("no price data for %s — skipping", ticker)
            continue

        df = raw.copy()
        # Normalise index → column
        if "date" not in df.columns:
            df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date", "close"])
        df = df.sort_values("date")

        # Trim to lookback window
        if cfg.lookback_months:
            cutoff = df["date"].max() - pd.DateOffset(months=cfg.lookback_months)
            df = df[df["date"] >= cutoff]

        if len(df) < cfg.channel_lookback + 5:
            logger.debug("insufficient bars for %s (%d) — skipping", ticker, len(df))
            continue

        # Ensure numeric
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Rolling channel
        df = compute_channel(df, lookback=cfg.channel_lookback)

        # Rolling 20-bar volume SMA
        if "volume" in df.columns:
            df["vol_sma20"] = df["volume"].rolling(20, min_periods=10).mean()
        else:
            df["vol_sma20"] = np.nan

        df["ticker"] = ticker
        frames.append(df)

    if not frames:
        logger.warning("no usable price data for any ticker")
        return SwingBacktestResult(
            initial_capital=cfg.initial_capital,
            final_capital=cfg.initial_capital,
            config_used=_cfg_to_dict(cfg),
        )

    all_bars = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)

    # --- Walk-forward simulation ------------------------------------------
    capital = cfg.initial_capital
    open_positions: dict[str, SwingTrade] = {}   # ticker → active trade
    completed: list[SwingTrade] = []
    equity_records: list[dict[str, Any]] = []

    cost_buy = 1.0 + (cfg.commission_bps + cfg.slippage_bps) / 10_000.0
    cost_sell = 1.0 - (cfg.commission_bps + cfg.slippage_bps) / 10_000.0

    # Group by date so we process all tickers for the same trading day together
    for date_val, day_group in all_bars.groupby("date", sort=True):
        date_str = pd.Timestamp(date_val).strftime("%Y-%m-%d")

        for _, row in day_group.iterrows():
            ticker = row["ticker"]
            close_p = row["close"]
            high_p = row.get("high", close_p)
            low_p = row.get("low", close_p)
            support = row.get("ch_support", np.nan)
            resistance = row.get("ch_resistance", np.nan)
            ch_pos = row.get("ch_position", np.nan)
            vol = row.get("volume", np.nan)
            vol_sma = row.get("vol_sma20", np.nan)

            if pd.isna(close_p):
                continue

            # 1. ---- Manage open positions ----
            if ticker in open_positions:
                t = open_positions[ticker]
                t.hold_days += 1
                exited = False

                # Stop-loss: intrabar check via low
                if not pd.isna(low_p) and low_p <= t.stop_loss:
                    t.exit_date = date_str
                    t.exit_price = t.stop_loss * cost_sell
                    t.exit_reason = "Stop Loss"
                    exited = True

                # Take-profit: intrabar check via high
                elif not pd.isna(high_p) and high_p >= t.take_profit:
                    t.exit_date = date_str
                    t.exit_price = t.take_profit * cost_sell
                    t.exit_reason = "Take Profit"
                    exited = True

                # Time stop
                elif t.hold_days >= cfg.max_hold_days:
                    t.exit_date = date_str
                    t.exit_price = close_p * cost_sell
                    t.exit_reason = "Time Stop"
                    exited = True

                if exited:
                    t.pnl = (t.exit_price - t.entry_price) * t.size
                    t.pnl_pct = ((t.exit_price / t.entry_price) - 1.0) * 100.0
                    capital += t.exit_price * t.size
                    completed.append(t)
                    del open_positions[ticker]

            # 2. ---- Check entry conditions ----
            elif (
                not pd.isna(support)
                and not pd.isna(resistance)
                and resistance > support
                and not pd.isna(ch_pos)
            ):
                in_buy_zone = 0.0 <= ch_pos <= cfg.buy_zone_threshold
                vol_ok = (
                    pd.isna(vol) or pd.isna(vol_sma) or vol_sma <= 0
                    or vol >= cfg.volume_surge_mult * vol_sma
                )
                at_capacity = len(open_positions) >= cfg.max_open_positions

                if in_buy_zone and vol_ok and not at_capacity:
                    stop_price = support * (1.0 - cfg.stop_loss_buffer_pct)
                    risk_per_share = close_p - stop_price

                    if risk_per_share > 0:
                        dollar_risk = capital * cfg.risk_per_trade_pct
                        shares = int(dollar_risk / risk_per_share)

                        # Cap at max_position_pct of current equity
                        total_equity = capital + sum(
                            t.size * close_p for t in open_positions.values()
                        )
                        max_trade_value = total_equity * cfg.max_position_pct
                        max_shares_by_pct = int(max_trade_value / (close_p * cost_buy))
                        shares = min(shares, max_shares_by_pct)

                        trade_cost = shares * close_p * cost_buy

                        if shares > 0 and trade_cost <= capital:
                            capital -= trade_cost
                            open_positions[ticker] = SwingTrade(
                                ticker=ticker,
                                entry_date=date_str,
                                entry_price=close_p * cost_buy,
                                size=shares,
                                stop_loss=stop_price,
                                take_profit=resistance * cfg.take_profit_ratio,
                            )

        # --- End-of-day equity snapshot ---
        # Use close prices from this day's group for open positions
        closes_today = {r["ticker"]: r["close"] for _, r in day_group.iterrows() if not pd.isna(r["close"])}
        open_value = sum(
            t.size * closes_today.get(t.ticker, t.entry_price)
            for t in open_positions.values()
        )
        equity_records.append({"date": date_str, "equity": round(capital + open_value, 2)})

    # Force-close any remaining open positions at last known close
    for ticker, t in list(open_positions.items()):
        last_row = all_bars[all_bars["ticker"] == ticker].iloc[-1]
        t.exit_date = pd.Timestamp(last_row["date"]).strftime("%Y-%m-%d")
        t.exit_price = float(last_row["close"]) * cost_sell
        t.exit_reason = "End of Backtest"
        t.pnl = (t.exit_price - t.entry_price) * t.size
        t.pnl_pct = ((t.exit_price / t.entry_price) - 1.0) * 100.0
        capital += t.exit_price * t.size
        completed.append(t)

    # --- Compute metrics ---------------------------------------------------
    if not equity_records:
        return SwingBacktestResult(
            initial_capital=cfg.initial_capital,
            final_capital=cfg.initial_capital,
            config_used=_cfg_to_dict(cfg),
        )

    eq_series = pd.DataFrame(equity_records).groupby("date")["equity"].last()
    final_eq = float(eq_series.iloc[-1])
    total_ret = ((final_eq / cfg.initial_capital) - 1.0) * 100.0
    n_days = len(eq_series)
    ann_ret = total_ret * (252 / max(n_days, 1))

    # Drawdown
    rolling_max = eq_series.cummax()
    drawdowns = (eq_series - rolling_max) / rolling_max
    max_dd = abs(float(drawdowns.min())) * 100.0 if not drawdowns.empty else 0.0

    # Sharpe
    daily_returns = eq_series.pct_change().dropna()
    sharpe = (
        float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))
        if len(daily_returns) > 1 and daily_returns.std() > 0
        else 0.0
    )

    # Win / loss
    wins = [t for t in completed if t.pnl > 0]
    losses = [t for t in completed if t.pnl <= 0]
    win_rate = (len(wins) / len(completed) * 100.0) if completed else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    )
    avg_pnl = float(np.mean([t.pnl_pct for t in completed])) if completed else 0.0
    avg_hold = float(np.mean([t.hold_days for t in completed])) if completed else 0.0

    equity_dict = {str(d): float(v) for d, v in eq_series.items()}

    return SwingBacktestResult(
        initial_capital=cfg.initial_capital,
        final_capital=round(final_eq, 2),
        total_return_pct=round(total_ret, 2),
        annualized_return_pct=round(ann_ret, 2),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown_pct=round(max_dd, 2),
        total_trades=len(completed),
        win_rate_pct=round(win_rate, 1),
        profit_factor=round(min(profit_factor, 999.0), 2),
        avg_trade_pnl_pct=round(avg_pnl, 2),
        avg_hold_days=round(avg_hold, 1),
        trades=completed,
        equity_curve=equity_dict,
        config_used=_cfg_to_dict(cfg),
    )


def _cfg_to_dict(cfg: SwingBacktestConfig) -> dict[str, Any]:
    return {
        "initial_capital": cfg.initial_capital,
        "risk_per_trade_pct": cfg.risk_per_trade_pct,
        "commission_bps": cfg.commission_bps,
        "slippage_bps": cfg.slippage_bps,
        "stop_loss_buffer_pct": cfg.stop_loss_buffer_pct,
        "take_profit_ratio": cfg.take_profit_ratio,
        "max_hold_days": cfg.max_hold_days,
        "max_open_positions": cfg.max_open_positions,
        "max_position_pct": cfg.max_position_pct,
        "channel_lookback": cfg.channel_lookback,
        "buy_zone_threshold": cfg.buy_zone_threshold,
        "volume_surge_mult": cfg.volume_surge_mult,
        "use_sentiment_filter": cfg.use_sentiment_filter,
        "lookback_months": cfg.lookback_months,
    }
