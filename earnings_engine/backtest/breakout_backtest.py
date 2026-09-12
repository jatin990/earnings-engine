"""Breakout Radar multi-strategy walk-forward backtesting engine.

Simulates and evaluates all 5 quantitative Breakout Radar strategies on historical OHLCV data:
  1. CLASSIC_TECHNICAL
  2. NSE_DELIVERY_ABSORPTION
  3. NSE_FO_CALL_WALL
  4. VOLUME_PROFILE_VAH
  5. DONCHIAN_TTM_SQUEEZE

Evaluates entry at confirmed breakout_trigger breaches, exit at target_price, stop_loss,
or maximum holding window (20 bars) with realistic transaction costs (slippage + commission).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner import (
    BREAKOUT_STRATEGIES,
    score_breakout,
    _resolve_universe_tickers,
)
from earnings_engine.data.prices import load_prices, load_prices_batch
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.backtest.breakout_backtest")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class BreakoutBacktestConfig:
    """Configuration knobs for Breakout Radar strategy backtest."""

    strategy: str = "CLASSIC_TECHNICAL"
    universe: str = "nifty_50"
    min_score: float = 40.0
    initial_capital: float = 100_000.0
    risk_per_trade_pct: float = 0.02          # 2.0% capital risk per trade
    commission_bps: float = 10.0               # 10 bps (0.10%) per side
    slippage_bps: float = 5.0                  # 5 bps (0.05%) execution slippage
    max_hold_days: int = 20                    # 20 trading days max holding period
    max_open_positions: int = 6                # Maximum simultaneous open trades
    max_position_pct: float = 0.20             # Max 20% equity per position
    scan_interval_days: int = 1                # Step interval (daily)
    lookback_days: int = 180                   # Historical test window


# ---------------------------------------------------------------------------
# Trade & Result Data-classes
# ---------------------------------------------------------------------------

@dataclass
class BreakoutTrade:
    """One completed or open breakout trade."""

    ticker: str
    strategy: str
    signal_date: str
    entry_date: str
    signal_price: float
    trigger_price: float
    entry_price: float
    size: int
    target_price: float
    stop_loss: float
    exit_date: str | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = "OPEN"
    hold_days: int = 0
    max_gain_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "strategy": self.strategy,
            "signal_date": self.signal_date,
            "entry_date": self.entry_date,
            "signal_price": round(self.signal_price, 2),
            "trigger_price": round(self.trigger_price, 2),
            "entry_price": round(self.entry_price, 2),
            "size": self.size,
            "target_price": round(self.target_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "exit_date": self.exit_date,
            "exit_price": round(self.exit_price, 2) if self.exit_price else None,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 2),
            "exit_reason": self.exit_reason,
            "hold_days": self.hold_days,
            "max_gain_pct": round(self.max_gain_pct, 2),
        }


@dataclass
class BreakoutBacktestResult:
    """Aggregated output from a Breakout Radar backtest run."""

    strategy: str
    strategy_name: str
    universe: str
    initial_capital: float = 0.0
    final_capital: float = 0.0
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    avg_hold_days: float = 0.0
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    run_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "strategy_name": self.strategy_name,
            "universe": self.universe,
            "initial_capital": round(self.initial_capital, 2),
            "final_capital": round(self.final_capital, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "annualized_return_pct": round(self.annualized_return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "win_rate_pct": round(self.win_rate_pct, 1),
            "profit_factor": round(self.profit_factor, 2),
            "expectancy_pct": round(self.expectancy_pct, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win_pct": round(self.avg_win_pct, 2),
            "avg_loss_pct": round(self.avg_loss_pct, 2),
            "avg_hold_days": round(self.avg_hold_days, 1),
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "run_at": self.run_at,
        }


# ---------------------------------------------------------------------------
# Backtesting Engine
# ---------------------------------------------------------------------------

def run_breakout_backtest(
    config: BreakoutBacktestConfig | None = None,
    settings: Settings | None = None,
    tickers: list[str] | None = None,
) -> BreakoutBacktestResult:
    """Execute a realistic walk-forward backtest for a Breakout Radar strategy."""
    cfg = config or BreakoutBacktestConfig()
    settings = settings or Settings()
    strat_key = (cfg.strategy or "CLASSIC_TECHNICAL").upper().strip()
    strat_meta = BREAKOUT_STRATEGIES.get(strat_key, BREAKOUT_STRATEGIES["CLASSIC_TECHNICAL"])

    ticker_list = tickers or _resolve_universe_tickers(settings, cfg.universe)
    if not ticker_list:
        logger.warning("[BREAKOUT-BT] No tickers found for universe %s", cfg.universe)
        return BreakoutBacktestResult(
            strategy=strat_key,
            strategy_name=strat_meta["name"],
            universe=cfg.universe,
        )

    # 1. Preload Price History in batch
    all_prices: dict[str, pd.DataFrame] = {}
    all_dates: set[str] = set()

    batch_prices = load_prices_batch(ticker_list, settings)
    for sym in ticker_list:
        df = batch_prices.get(sym)
        if df is None or df.empty:
            df = load_prices(sym, settings)
        if df is not None and not df.empty and len(df) >= 40:
            df = df.sort_index()
            all_prices[sym] = df
            all_dates.update([str(d)[:10] for d in df.index])

    if not all_prices:
        return BreakoutBacktestResult(
            strategy=strat_key,
            strategy_name=strat_meta["name"],
            universe=cfg.universe,
        )

    sorted_dates = sorted(all_dates)
    if len(sorted_dates) > cfg.lookback_days:
        test_dates = sorted_dates[-cfg.lookback_days:]
    else:
        test_dates = sorted_dates[40:]  # Need warmup bars

    # Portfolio State
    cash = cfg.initial_capital
    open_trades: list[BreakoutTrade] = []
    completed_trades: list[BreakoutTrade] = []
    equity_series: list[dict[str, Any]] = []

    cost_mult = (cfg.commission_bps + cfg.slippage_bps) / 10_000.0

    # 2. Daily Walk-Forward Simulation
    for date_str in test_dates:
        # A. Evaluate Open Positions against current day's OHLCV
        for trade in list(open_trades):
            sym = trade.ticker
            df = all_prices.get(sym)
            if df is None or date_str not in df.index:
                trade.hold_days += 1
                continue

            row = df.loc[date_str]
            day_high = float(row["high"]) if "high" in row else float(row["close"])
            day_low = float(row["low"]) if "low" in row else float(row["close"])
            day_close = float(row["close"])

            trade.hold_days += 1
            gain_pct = ((day_high - trade.entry_price) / trade.entry_price) * 100.0
            trade.max_gain_pct = max(trade.max_gain_pct, gain_pct)

            # Check Exit Conditions
            exited = False
            exit_price = 0.0
            reason = ""

            # Stop-loss priority (gap down protection)
            if day_low <= trade.stop_loss:
                exit_price = min(trade.stop_loss, float(row.get("open", day_low))) * (1.0 - cost_mult)
                reason = "STOP_LOSS"
                exited = True
            elif day_high >= trade.target_price:
                exit_price = trade.target_price * (1.0 - cost_mult)
                reason = "TARGET_HIT"
                exited = True
            elif trade.hold_days >= cfg.max_hold_days:
                exit_price = day_close * (1.0 - cost_mult)
                reason = "TIME_STOP"
                exited = True

            if exited:
                trade.exit_date = date_str
                trade.exit_price = exit_price
                trade.exit_reason = reason
                trade.pnl = (exit_price - trade.entry_price) * trade.size
                trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100.0

                cash += trade.size * exit_price
                open_trades.remove(trade)
                completed_trades.append(trade)

        # B. Scan for New Breakout Entries if capacity allows
        if len(open_trades) < cfg.max_open_positions:
            for sym, df in all_prices.items():
                if len(open_trades) >= cfg.max_open_positions:
                    break
                if any(t.ticker == sym for t in open_trades):
                    continue
                if date_str not in df.index:
                    continue

                # Point-in-time scoring as of date_str
                res = score_breakout(
                    ticker=sym,
                    prices_df=df,
                    asof_date=date_str,
                    strategy=strat_key,
                    settings=settings,
                )

                if res and (res.get("composite_score") or 0) >= cfg.min_score:
                    sig_price = float(res.get("signal_price") or 0)
                    trig_price = float(res.get("breakout_trigger") or 0)
                    target = float(res.get("target_price") or 0)
                    stop = float(res.get("stop_loss") or 0)

                    if sig_price > 0 and trig_price > sig_price and stop < sig_price:
                        # Entry occurs when price breaches trigger with execution slippage
                        entry_price = trig_price * (1.0 + cost_mult)
                        risk_per_share = max(1.0, entry_price - stop)
                        portfolio_equity = cash + sum(t.size * entry_price for t in open_trades)
                        risk_amount = portfolio_equity * cfg.risk_per_trade_pct

                        size = int(risk_amount / risk_per_share)
                        max_allowed_size = int((portfolio_equity * cfg.max_position_pct) / entry_price)
                        size = max(1, min(size, max_allowed_size))

                        trade_cost = size * entry_price
                        if cash >= trade_cost:
                            cash -= trade_cost
                            new_trade = BreakoutTrade(
                                ticker=sym,
                                strategy=strat_key,
                                signal_date=date_str,
                                entry_date=date_str,
                                signal_price=sig_price,
                                trigger_price=trig_price,
                                entry_price=entry_price,
                                size=size,
                                target_price=target,
                                stop_loss=stop,
                            )
                            open_trades.append(new_trade)

        # Record daily equity point
        open_val = 0.0
        for t in open_trades:
            df = all_prices.get(t.ticker)
            if df is not None and date_str in df.index:
                open_val += t.size * float(df.loc[date_str, "close"])
            else:
                open_val += t.size * t.entry_price

        total_equity = cash + open_val
        equity_series.append({
            "date": date_str,
            "equity": round(total_equity, 2),
            "cash": round(cash, 2),
            "open_positions": len(open_trades),
        })

    # Close remaining open positions at final close price
    final_date = test_dates[-1] if test_dates else "Latest"
    for trade in list(open_trades):
        sym = trade.ticker
        df = all_prices.get(sym)
        last_p = float(df.iloc[-1]["close"]) if df is not None and not df.empty else trade.entry_price
        exit_p = last_p * (1.0 - cost_mult)

        trade.exit_date = final_date
        trade.exit_price = exit_p
        trade.exit_reason = "FORCE_CLOSE"
        trade.pnl = (exit_p - trade.entry_price) * trade.size
        trade.pnl_pct = ((exit_p - trade.entry_price) / trade.entry_price) * 100.0
        cash += trade.size * exit_p
        completed_trades.append(trade)

    final_capital = cash
    total_ret_pct = ((final_capital - cfg.initial_capital) / cfg.initial_capital) * 100.0

    # Performance Metrics
    total_trades_count = len(completed_trades)
    winning_trades = [t for t in completed_trades if t.pnl > 0]
    losing_trades = [t for t in completed_trades if t.pnl <= 0]

    win_rate = (len(winning_trades) / total_trades_count * 100.0) if total_trades_count > 0 else 0.0
    gross_profit = sum(t.pnl for t in winning_trades)
    gross_loss = abs(sum(t.pnl for t in losing_trades))
    profit_factor = (gross_profit / max(1.0, gross_loss)) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

    avg_win = float(np.mean([t.pnl_pct for t in winning_trades])) if winning_trades else 0.0
    avg_loss = float(np.mean([t.pnl_pct for t in losing_trades])) if losing_trades else 0.0
    avg_hold = float(np.mean([t.hold_days for t in completed_trades])) if completed_trades else 0.0

    expectancy = (win_rate / 100.0 * avg_win) + ((100.0 - win_rate) / 100.0 * avg_loss)

    # Calculate Drawdowns & Sharpe
    if equity_series:
        eq_df = pd.DataFrame(equity_series)
        eq_df["peak"] = eq_df["equity"].cummax()
        eq_df["dd_pct"] = (eq_df["equity"] - eq_df["peak"]) / eq_df["peak"] * 100.0
        max_dd = abs(float(eq_df["dd_pct"].min()))

        eq_df["daily_ret"] = eq_df["equity"].pct_change().fillna(0)
        daily_std = float(eq_df["daily_ret"].std())
        daily_mean = float(eq_df["daily_ret"].mean())
        sharpe = (daily_mean / max(1e-6, daily_std)) * np.sqrt(252) if daily_std > 0 else 0.0

        # Canonical Sortino: Root-Mean-Square Downside Deviation against 0 threshold
        neg_rets = np.minimum(0.0, eq_df["daily_ret"].to_numpy())
        downside_std = float(np.sqrt(np.mean(neg_rets ** 2)))
        sortino = (daily_mean / max(1e-6, downside_std)) * np.sqrt(252) if downside_std > 0 else 0.0
    else:
        max_dd = 0.0
        sharpe = 0.0
        sortino = 0.0

    ann_ret = total_ret_pct * (252.0 / max(1, len(test_dates)))

    return BreakoutBacktestResult(
        strategy=strat_key,
        strategy_name=strat_meta["name"],
        universe=cfg.universe,
        initial_capital=cfg.initial_capital,
        final_capital=final_capital,
        total_return_pct=total_ret_pct,
        annualized_return_pct=ann_ret,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_pct=max_dd,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        expectancy_pct=expectancy,
        total_trades=total_trades_count,
        winning_trades=len(winning_trades),
        losing_trades=len(losing_trades),
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        avg_hold_days=avg_hold,
        trades=[t.to_dict() for t in completed_trades],
        equity_curve=equity_series,
    )
