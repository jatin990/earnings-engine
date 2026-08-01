"""Command-line interface.

Phase 1 commands: ingest, calendar. Later phases add train, backtest,
predict, report.
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import click
import pandas as pd

from earnings_engine.config import PROJECT_ROOT, Settings, load_email_settings
from earnings_engine.data import earnings as earnings_mod
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.market_context import enrich_upcoming_results
from earnings_engine.data.universe import load_all, load_universe, load_universe_from_file
from earnings_engine.emailing import send_report_email
from earnings_engine.logging_utils import get_logger
from earnings_engine.reports.render import render_upcoming_results_report


def _get_cli_logger():
    return get_logger("earnings_engine.cli", base_dir=PROJECT_ROOT)


def _cleanup_previous_artifacts(root: Path | None = None) -> None:
    """Archive generated reports and clear stale logs before a new run."""
    root_path = root or PROJECT_ROOT
    reports_dir = root_path / "reports"
    output_dir = reports_dir / "output"
    archive_dir = reports_dir / "archive"
    logs_dir = root_path / "logs"

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    for artifact in sorted(output_dir.iterdir()):
        if not artifact.is_file():
            continue
        target = archive_dir / artifact.name
        if target.exists():
            target.unlink()
        shutil.move(str(artifact), str(target))

    cutoff = datetime.now() - timedelta(days=3)
    for log_file in sorted(logs_dir.glob("earnings_engine-*.log")):
        if log_file.is_file() and log_file.stat().st_mtime < cutoff.timestamp():
            log_file.unlink(missing_ok=True)


def _resolve_tickers(market: str | None, ticker: tuple[str, ...], universe_file: str | Path | None = None) -> list[str]:
    if ticker:
        return list(ticker)
    if universe_file:
        return load_universe_from_file(universe_file)
    if market:
        return load_universe(market.upper())
    return load_all()


@click.group()
@click.pass_context
def cli(ctx) -> None:
    """Earnings prediction engine."""
    _cleanup_previous_artifacts(PROJECT_ROOT)
    if ctx.invoked_subcommand is None:
        click.echo("Choose a subcommand. Run `earnings-engine --help` for details.")


@cli.command()
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None,
              help="Choose a market (defaults to the Indian universe when omitted).")
@click.option("--ticker", "-t", multiple=True, help="Specific ticker(s) instead of the universe.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--force", is_flag=True, help="Ignore cache freshness and re-download.")
@click.option("--prices/--no-prices", default=True, help="Ingest daily OHLCV.")
@click.option("--earnings/--no-earnings", "earnings_flag", default=True, help="Ingest earnings dates.")
def ingest(market, ticker, force, prices, earnings_flag, universe_file) -> None:
    """Download prices and earnings dates into the local cache."""
    settings = Settings()
    tickers = _resolve_tickers(market, ticker, universe_file)
    logger = _get_cli_logger()
    click.echo(f"Ingesting {len(tickers)} tickers...")
    logger.info("ingest started market=%s tickers=%s force=%s", market, tickers, force)
    click.echo(f"Tickers: {', '.join(tickers)}")

    if prices:
        results = prices_mod.ingest_prices(tickers, settings, force=force)
        logger.info("ingest prices completed results=%s", results)
        ok = sum(1 for n in results.values() if n > 0)
        empty = [t for t, n in results.items() if n == 0]
        click.echo(f"Prices: {ok}/{len(tickers)} tickers with data.")
        if empty:
            click.echo(f"  No price data: {', '.join(empty)}")

    if earnings_flag:
        results = earnings_mod.ingest_earnings(tickers, settings, force=force)
        logger.info("ingest earnings completed results=%s", results)
        ok = sum(1 for n in results.values() if n > 0)
        empty = [t for t, n in results.items() if n == 0]
        click.echo(f"Earnings: {ok}/{len(tickers)} tickers with events.")
        if empty:
            click.echo(f"  No earnings data: {', '.join(empty)}")


@cli.command()
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None)
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--days", default=14, show_default=True, help="Look-ahead window in days.")
def calendar(market, days, universe_file) -> None:
    """Show upcoming earnings events from the local cache."""
    settings = Settings()
    tickers = _resolve_tickers(market, (), universe_file)
    logger = _get_cli_logger()
    click.echo(f"Calendar for {len(tickers)} tickers")
    logger.info("calendar requested market=%s days=%s tickers=%s", market, days, tickers)
    click.echo(f"Tickers: {', '.join(tickers)}")
    df = earnings_mod.upcoming_earnings(tickers, settings, days=days)
    logger.info("calendar returned rows=%s", len(df))
    if df.empty:
        click.echo("No upcoming earnings in cache. Run `earnings-engine ingest` first.")
        return
    click.echo(df.to_string(index=False))


@cli.command("upcoming-results")
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None)
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--days", default=14, show_default=True, help="Look-ahead window in days.")
def upcoming_results(market, days, universe_file) -> None:
    """List all stocks with earnings results in the next N days."""
    settings = Settings()
    tickers = _resolve_tickers(market, (), universe_file)
    logger = _get_cli_logger()
    click.echo(f"Upcoming results for {len(tickers)} tickers")
    logger.info("upcoming-results requested market=%s days=%s tickers=%s", market, days, tickers)
    click.echo(f"Tickers: {', '.join(tickers)}")
    df = earnings_mod.upcoming_earnings(tickers, settings, days=days)
    logger.info("upcoming-results raw rows=%s", len(df))
    if df.empty:
        click.echo("No upcoming results in cache. Run `earnings-engine ingest` first.")
        return
    enriched = enrich_upcoming_results(df)
    logger.info("upcoming-results enrichment complete rows=%s", len(enriched))
    for col in ["market_cap", "current_price", "week_change", "pct_from_52w_high", "pct_from_52w_low", "thirty_day_return_pct", "earnings_week_move_pct", "prev_quarter_earnings_score"]:
        if col not in enriched.columns:
            enriched[col] = pd.NA
    enriched["market_cap_crore"] = enriched["market_cap"].map(lambda v: f"{v/1e7:.1f} Cr" if pd.notna(v) else "")
    enriched["current_price"] = enriched["current_price"].map(lambda v: f"{v:.2f}" if pd.notna(v) else "")
    enriched["week_change"] = enriched["week_change"].map(lambda v: f"{v:.1%}" if pd.notna(v) else "")
    enriched["pct_from_52w_high"] = enriched["pct_from_52w_high"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "")
    enriched["pct_from_52w_low"] = enriched["pct_from_52w_low"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "")
    enriched["thirty_day_return_pct"] = enriched["thirty_day_return_pct"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "")
    enriched["earnings_week_move_pct"] = enriched["earnings_week_move_pct"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "")
    enriched["prev_quarter_earnings_score"] = enriched["prev_quarter_earnings_score"].map(lambda v: f"{v:.0f}/9" if pd.notna(v) else "")

    output_dir = PROJECT_ROOT / "reports" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    csv_path = output_dir / f"upcoming-results-{stamp}.csv"
    enriched.to_csv(csv_path, index=False)
    logger.info("upcoming-results exported csv=%s", csv_path)

    html_path = output_dir / f"upcoming-results-{stamp}.html"
    report_html = render_upcoming_results_report(enriched, csv_path=csv_path, html_path=html_path)
    logger.info("upcoming-results rendered html=%s", html_path)

    click.echo(enriched[["ticker", "earnings_date", "market_cap_crore", "current_price", "week_change", "thirty_day_return_pct", "earnings_week_move_pct", "prev_quarter_earnings_score", "pct_from_52w_high", "pct_from_52w_low"]].to_string(index=False))
    click.echo(f"\nSaved CSV: {csv_path}")
    click.echo(f"Saved HTML report: {html_path}")
    logger.info("saved csv path=%s", csv_path)

    email_settings = load_email_settings()
    should_email = bool(email_settings.to_addresses and (email_settings.enabled or email_settings.smtp_host))
    if should_email:
        logger.info("sending email recipients=%s enabled=%s", email_settings.to_addresses, email_settings.enabled)
        click.echo(f"Emailing report to: {', '.join(email_settings.to_addresses)}")
        send_report_email(csv_path, email_settings, body="Attached are the CSV and HTML earnings report.", html_path=html_path)
        logger.info("email sent successfully csv=%s html=%s", csv_path, html_path)
        click.echo(f"Email sent successfully: {csv_path}")
    else:
        logger.info("email not triggered because no recipients or smtp host were configured")


@cli.command("build-dataset")
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None)
@click.option("--ticker", "-t", multiple=True, help="Specific ticker(s) instead of the universe.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
def build_dataset_cmd(market, ticker, universe_file) -> None:
    """Build the event dataset (features + labels) from cached data."""
    from earnings_engine.dataset import DATASET_PATH, build_dataset

    settings = Settings()
    tickers = _resolve_tickers(market, ticker, universe_file)
    logger = _get_cli_logger()
    logger.info("build-dataset requested market=%s tickers=%s", market, tickers)
    df = build_dataset(tickers, settings)
    logger.info("build-dataset complete rows=%s", len(df))
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
@click.option("--model", "model_name", default="gbm",
              help="Model to backtest (always_up, past_up_rate, gbm).")
@click.option("--threshold", default=0.5, show_default=True,
              help="Min P(up) confidence to take a trade (0.5 trades everything).")
@click.option("--cost", default=0.001, show_default=True, help="Round-trip cost per trade.")
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None,
              help="Choose a market for backtesting.")
def backtest(model_name, threshold, cost, market) -> None:
    """Walk-forward backtest of a model on the event dataset."""
    from earnings_engine.backtest.engine import BacktestConfig, run_backtest
    from earnings_engine.dataset import load_dataset
    from earnings_engine.models.registry import make_model

    try:
        model = make_model(model_name)
    except ValueError as e:
        raise click.BadParameter(str(e))
    df = load_dataset()
    if market:
        df = df[df["market"] == market.upper()]
    cfg = BacktestConfig(threshold=threshold, cost_per_trade=cost)
    result = run_backtest(df, model, cfg)
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


@cli.command()
@click.option("--model", "model_name", default="gbm", show_default=True)
@click.option("--days", default=14, show_default=True, help="Look-ahead window for upcoming earnings.")
@click.option("--market", type=click.Choice(["IN", "US"], case_sensitive=False), default=None)
@click.option("--ticker", "-t", multiple=True)
@click.option("--report/--no-report", "write_report", default=True, show_default=True,
              help="Also write CSV + HTML to reports/output/.")
def predict(model_name, days, market, ticker, write_report) -> None:
    """Predict direction + confidence for upcoming earnings events."""
    from earnings_engine.predict import predict_upcoming
    from earnings_engine.reports.render import render_predictions

    settings = Settings()
    tickers = _resolve_tickers(market, ticker)
    logger = _get_cli_logger()
    logger.info("predict requested market=%s days=%s model=%s tickers=%s", market, days, model_name, tickers)
    preds = predict_upcoming(tickers, settings, model_name=model_name, days=days)
    logger.info("predict complete rows=%s", len(preds))
    if preds.empty:
        click.echo("No upcoming earnings with sufficient data. "
                   "Run `earnings-engine ingest` to refresh the calendar.")
        return
    show = preds[["ticker", "market", "earnings_date", "direction", "confidence", "p_up", "n_past_events"]].copy()
    show["earnings_date"] = show["earnings_date"].dt.date
    show["confidence"] = show["confidence"].map("{:.1%}".format)
    show["p_up"] = show["p_up"].map("{:.1%}".format)
    click.echo(show.to_string(index=False))
    if write_report:
        csv_path, html_path = render_predictions(preds)
        click.echo(f"\nReport: {html_path}\nCSV   : {csv_path}")


@cli.command("test-email")
def test_email() -> None:
    """Send the latest generated report artifact to the configured recipient."""
    logger = _get_cli_logger()
    output_dir = PROJECT_ROOT / "reports" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_candidates = sorted(output_dir.glob("upcoming-results-*.csv"))
    html_candidates = sorted(output_dir.glob("upcoming-results-*.html"))

    if not csv_candidates:
        click.echo("No generated report found. Run `earnings-engine upcoming-results` first.")
        logger.info("test-email aborted because no csv report exists")
        return

    csv_path = csv_candidates[-1]
    html_path = html_candidates[-1] if html_candidates else None
    email_settings = load_email_settings()

    if not (email_settings.to_addresses and (email_settings.enabled or email_settings.smtp_host)):
        click.echo("Email not configured. Set SMTP/recipient settings in .env first.")
        logger.info("test-email aborted because mail settings are incomplete")
        return

    logger.info("test-email sending latest report csv=%s html=%s", csv_path, html_path)
    click.echo(f"Sending latest report: {csv_path}")
    if html_path is not None:
        click.echo(f"HTML report: {html_path}")

    send_report_email(csv_path, email_settings, body="Test email from earnings-engine.", html_path=html_path)
    click.echo("Email send attempt completed.")


if __name__ == "__main__":
    cli()
