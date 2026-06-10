"""Command-line interface.

Phase 1 commands: ingest, calendar. Later phases add train, backtest,
predict, report.
"""

import click

from earnings_engine.config import Settings
from earnings_engine.data import earnings as earnings_mod
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.universe import load_all, load_universe


def _resolve_tickers(market: str | None, ticker: tuple[str, ...]) -> list[str]:
    if ticker:
        return list(ticker)
    if market:
        return load_universe(market.upper())
    return load_all()


@click.group()
def cli() -> None:
    """Earnings prediction engine."""


@cli.command()
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None,
              help="Limit to one market (default: both).")
@click.option("--ticker", "-t", multiple=True, help="Specific ticker(s) instead of the universe.")
@click.option("--force", is_flag=True, help="Ignore cache freshness and re-download.")
@click.option("--prices/--no-prices", default=True, help="Ingest daily OHLCV.")
@click.option("--earnings/--no-earnings", "earnings_flag", default=True, help="Ingest earnings dates.")
def ingest(market, ticker, force, prices, earnings_flag) -> None:
    """Download prices and earnings dates into the local cache."""
    settings = Settings()
    tickers = _resolve_tickers(market, ticker)
    click.echo(f"Ingesting {len(tickers)} tickers...")

    if prices:
        results = prices_mod.ingest_prices(tickers, settings, force=force)
        ok = sum(1 for n in results.values() if n > 0)
        empty = [t for t, n in results.items() if n == 0]
        click.echo(f"Prices: {ok}/{len(tickers)} tickers with data.")
        if empty:
            click.echo(f"  No price data: {', '.join(empty)}")

    if earnings_flag:
        results = earnings_mod.ingest_earnings(tickers, settings, force=force)
        ok = sum(1 for n in results.values() if n > 0)
        empty = [t for t, n in results.items() if n == 0]
        click.echo(f"Earnings: {ok}/{len(tickers)} tickers with events.")
        if empty:
            click.echo(f"  No earnings data: {', '.join(empty)}")


@cli.command()
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None)
@click.option("--days", default=14, show_default=True, help="Look-ahead window in days.")
def calendar(market, days) -> None:
    """Show upcoming earnings events from the local cache."""
    settings = Settings()
    tickers = _resolve_tickers(market, ())
    df = earnings_mod.upcoming_earnings(tickers, settings, days=days)
    if df.empty:
        click.echo("No upcoming earnings in cache. Run `earnings-engine ingest` first.")
        return
    click.echo(df.to_string(index=False))


@cli.command("build-dataset")
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None)
@click.option("--ticker", "-t", multiple=True, help="Specific ticker(s) instead of the universe.")
def build_dataset_cmd(market, ticker) -> None:
    """Build the event dataset (features + labels) from cached data."""
    from earnings_engine.dataset import DATASET_PATH, build_dataset

    settings = Settings()
    tickers = _resolve_tickers(market, ticker)
    df = build_dataset(tickers, settings)
    if df.empty:
        click.echo("No events built. Run `earnings-engine ingest` first.")
        return
    by_market = df["market"].value_counts().to_dict()
    up_rate = df["label"].mean()
    click.echo(f"Built {len(df)} events from {df['ticker'].nunique()} tickers -> {DATASET_PATH}")
    click.echo(f"  By market: {by_market}")
    click.echo(f"  Date range: {df['earnings_date'].min().date()} -> {df['earnings_date'].max().date()}")
    click.echo(f"  Up-label rate: {up_rate:.1%}")


@cli.command()
@click.option("--model", "model_name", default="past_up_rate",
              help="Model to backtest (always_up, past_up_rate).")
@click.option("--threshold", default=0.5, show_default=True,
              help="Min P(up) confidence to take a trade (0.5 trades everything).")
@click.option("--cost", default=0.001, show_default=True, help="Round-trip cost per trade.")
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None,
              help="Backtest one market only.")
def backtest(model_name, threshold, cost, market) -> None:
    """Walk-forward backtest of a model on the event dataset."""
    from earnings_engine.backtest.engine import BacktestConfig, run_backtest
    from earnings_engine.dataset import load_dataset
    from earnings_engine.models.baseline import BASELINES

    if model_name not in BASELINES:
        raise click.BadParameter(f"Unknown model {model_name!r}; choose from {list(BASELINES)}")
    df = load_dataset()
    if market:
        df = df[df["market"] == market.upper()]
    cfg = BacktestConfig(threshold=threshold, cost_per_trade=cost)
    result = run_backtest(df, BASELINES[model_name](), cfg)
    if result.predictions.empty:
        click.echo("Not enough events to backtest. Build a bigger dataset first.")
        return
    m = result.metrics
    click.echo(f"Model: {model_name}  threshold={threshold}  cost={cost}")
    click.echo(f"  Events tested : {m['n_events']}   traded: {m['n_traded']} ({m['coverage']:.0%})")
    click.echo(f"  Hit rate      : {m['hit_rate']:.1%}   (base up-rate: {m['base_up_rate']:.1%})")
    click.echo(f"  Avg trade ret : {m['avg_trade_return']:+.3%}")
    click.echo(f"  Total return  : {m['total_return']:+.1%} (sum of per-event returns)")
    click.echo(f"  Sharpe/event  : {m['sharpe_per_event']:.3f}")


if __name__ == "__main__":
    cli()
