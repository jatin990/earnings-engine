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


if __name__ == "__main__":
    cli()
