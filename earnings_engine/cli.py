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
from earnings_engine.data.universe import ingest_market_caps, load_all, load_universe, load_universe_from_file
from earnings_engine.emailing import send_report_email
from earnings_engine.kronos_predictor import generate_html_report, generate_markdown_report, predict_portfolio
from earnings_engine.logging_utils import get_logger
from earnings_engine.reports.render import render_dashboard, render_upcoming_results_report


def _get_cli_logger():
    return get_logger("earnings_engine.cli", base_dir=PROJECT_ROOT)


def _cleanup_previous_artifacts(root: Path | None = None) -> None:
    """Archive generated reports and clear stale logs before a new run."""
    root_path = root or PROJECT_ROOT
    reports_dir = root_path / "reports"
    output_dir = reports_dir / "output"
    archive_dir = reports_dir / "archive"
    logs_dir = root_path / "logs"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    try:
        for artifact in sorted(output_dir.iterdir()):
            if not artifact.is_file():
                continue
            target = archive_dir / artifact.name
            try:
                if target.exists():
                    target.unlink()
                shutil.move(str(artifact), str(target))
            except (OSError, shutil.Error):
                continue
    except OSError:
        pass

    cutoff = datetime.now() - timedelta(days=3)
    try:
        for log_file in sorted(logs_dir.glob("earnings_engine-*.log")):
            if not log_file.is_file():
                continue
            try:
                if log_file.stat().st_mtime < cutoff.timestamp():
                    log_file.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        pass


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
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
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

    # Fetch and cache market cap for all tickers
    click.echo(f"Fetching market cap for {len(tickers)} tickers...")
    mc_results = ingest_market_caps(tickers, force=force)
    logger.info("ingest market cap completed results=%s", mc_results)
    mc_ok = sum(1 for v in mc_results.values() if v > 0)
    click.echo(f"Market cap: {mc_ok}/{len(tickers)} tickers with data.")


@cli.command()
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
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
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--days", default=14, show_default=True, help="Look-ahead window in days.")
def upcoming_results(market, days, universe_file) -> None:
    """List all stocks with earnings results in the next N days."""
    settings = Settings()
    tickers = _resolve_tickers(market, (), universe_file)
    logger = _get_cli_logger()
    click.echo(f"Upcoming results for {len(tickers)} tickers")
    logger.info("upcoming-results requested market=%s days=%s tickers=%s", market, days, len(tickers))
    df = earnings_mod.upcoming_earnings(tickers, settings, days=days)
    logger.info("upcoming-results raw rows=%s", len(df))
    if df.empty:
        click.echo("No upcoming results in cache. Run `earnings-engine ingest` first.")
        return
    enriched = enrich_upcoming_results(df)
    logger.info("upcoming-results enrichment complete rows=%s", len(enriched))
    for col in ["market_cap", "current_price", "week_change", "pct_from_52w_high", "pct_from_52w_low",
                "thirty_day_return_pct", "earnings_week_move_pct", "earnings_week_high_pct",
                "earnings_week_low_pct", "week_high", "week_low",
                "prev_quarter_earnings_score", "prev_3q_earnings_score",
                "q1_earnings_score", "q2_earnings_score", "q3_earnings_score"]:
        if col not in enriched.columns:
            enriched[col] = pd.NA

    # Build a separate display copy for the CLI table — the raw enriched frame
    # is passed to the renderer/CSV so it keeps numeric values (no double-formatting).
    display = enriched.copy()
    display["market_cap_crore"] = display["market_cap"].map(lambda v: f"{v/1e7:.1f} Cr" if pd.notna(v) else "")
    display["current_price"] = display["current_price"].map(lambda v: f"{v:.2f}" if pd.notna(v) else "")
    display["week_change"] = display["week_change"].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "")
    display["thirty_day_return_pct"] = display["thirty_day_return_pct"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "")
    display["earnings_week_move_pct"] = display["earnings_week_move_pct"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "")
    display["earnings_week_high_pct"] = display["earnings_week_high_pct"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "")
    display["earnings_week_low_pct"] = display["earnings_week_low_pct"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "")

    def _fmt_52w(row: pd.Series, col: str, price_col: str) -> str:
        v = row.get(col)
        price = row.get(price_col)
        if pd.isna(v):
            return ""
        value = float(v)
        if pd.isna(price):
            return f"{value:+.1f}%"
        return f"{value:+.1f}% ({price:,.0f})"

    display["pct_from_52w_high"] = display.apply(lambda r: _fmt_52w(r, "pct_from_52w_high", "week_high"), axis=1)
    display["pct_from_52w_low"] = display.apply(lambda r: _fmt_52w(r, "pct_from_52w_low", "week_low"), axis=1)
    display["prev_quarter_earnings_score"] = display["prev_quarter_earnings_score"].map(lambda v: f"{v:.0f}/9" if pd.notna(v) else "")
    display["prev_3q_earnings_score"] = display["prev_3q_earnings_score"].map(lambda v: f"{v:.0f}/9" if pd.notna(v) else "")
    display["q1_earnings_score"] = display["q1_earnings_score"].map(lambda v: f"{v:.0f}/9" if pd.notna(v) else "")
    display["q2_earnings_score"] = display["q2_earnings_score"].map(lambda v: f"{v:.0f}/9" if pd.notna(v) else "")
    display["q3_earnings_score"] = display["q3_earnings_score"].map(lambda v: f"{v:.0f}/9" if pd.notna(v) else "")

    # Collapse related columns into combined display columns
    display["52w_gap"] = display.apply(
        lambda r: f"{r['pct_from_52w_high']} / {r['pct_from_52w_low']}", axis=1
    )
    display["quality"] = display.apply(
        lambda r: f"Q1={r['q1_earnings_score']} Q2={r['q2_earnings_score']} Q3={r['q3_earnings_score']} (3Q={r['prev_3q_earnings_score']})", axis=1
    )

    output_dir = PROJECT_ROOT / "reports" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    csv_path = output_dir / f"upcoming-results-{stamp}.csv"
    enriched.to_csv(csv_path, index=False)
    logger.info("upcoming-results exported csv=%s", csv_path)

    html_path = output_dir / f"upcoming-results-{stamp}.html"
    report_html = render_upcoming_results_report(enriched, csv_path=csv_path, html_path=html_path)
    logger.info("upcoming-results rendered html=%s", html_path)

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
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
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
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market for backtesting. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
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
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
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


@cli.command("kronos-predict")
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
@click.option("--ticker", "-t", multiple=True, help="Specific ticker(s) to predict.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--lookback", default=120, show_default=True, help="Number of historical days to use for prediction.")
@click.option("--pred-len", default=14, show_default=True, help="Number of days to predict forward.")
def kronos_predict(market, ticker, universe_file, lookback, pred_len) -> None:
    """Generate 14-day price predictions using Kronos AI model.
    
    This command uses the Kronos foundation model to predict price movements
    for the next N days, including support/resistance levels and AI-generated
    trading explanations.
    
    Examples:
        earnings-engine kronos-predict --market IN
        earnings-engine kronos-predict --ticker TCS.NS INFY.NS RELIANCE.NS
        earnings-engine kronos-predict --universe-file my_stocks.txt
    """
    settings = Settings()
    tickers = _resolve_tickers(market, ticker, universe_file)
    logger = _get_cli_logger()
    
    if not tickers:
        click.echo("No tickers specified. Use --market, --ticker, or --universe-file.")
        return
    
    click.echo(f"🔮 Kronos AI Price Prediction for {len(tickers)} stocks")
    click.echo(f"   Lookback: {lookback} days | Prediction horizon: {pred_len} days")
    click.echo(f"   Tickers: {', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''}")
    logger.info("kronos-predict started market=%s tickers=%s lookback=%s pred_len=%s", 
                market, tickers, lookback, pred_len)
    
    # Progress callback for CLI output
    def progress_callback(current: int, total: int, symbol: str):
        click.echo(f"  [{current}/{total}] Predicting: {symbol}")
    
    # Generate predictions
    forecasts = predict_portfolio(
        tickers,
        lookback=lookback,
        pred_len=pred_len,
        progress_callback=progress_callback
    )
    
    if not forecasts:
        click.echo("\n❌ No predictions generated. Check logs for errors.")
        logger.warning("kronos-predict completed with no forecasts")
        return
    
    # Sort by return percentage
    forecasts.sort(key=lambda x: x["return_pct"], reverse=True)
    
    # Generate reports
    output_dir = PROJECT_ROOT / "reports" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    
    md_path = output_dir / f"kronos-predictions-{stamp}.md"
    html_path = output_dir / f"kronos-predictions-{stamp}.html"
    
    generate_markdown_report(forecasts, md_path)
    generate_html_report(forecasts, html_path)
    
    logger.info("kronos-predict completed rows=%s md=%s html=%s", len(forecasts), md_path, html_path)
    
    # Display summary
    click.echo(f"\n✅ Generated {len(forecasts)} predictions")
    click.echo(f"\n📊 Top Performers (14-day outlook):")
    for item in forecasts[:5]:
        trend_emoji = "🟢" if item["return_pct"] > 0.5 else ("🔴" if item["return_pct"] < -0.5 else "🟡")
        click.echo(f"  {trend_emoji} {item['name']} ({item['symbol']}): {item['return_pct']:+.2f}% | "
                   f"Support: ₹{item['support']:,.2f} | Resistance: ₹{item['resistance']:,.2f}")
    
    click.echo(f"\n📁 Reports saved:")
    click.echo(f"   Markdown: {md_path}")
    click.echo(f"   HTML: {html_path}")
    click.echo(f"\n💡 Open {html_path} in your browser to view the interactive report")


@cli.command("dashboard")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host for the API server.")
@click.option("--port", default=8000, show_default=True, help="Port for the API server.")
def dashboard(host: str, port: int) -> None:
    """Start the API server and open the interactive dashboard in your browser.
    
    The dashboard is served through the FastAPI server so all embedded
    JavaScript can call the REST endpoints (market-context, price-history,
    earnings-history, universe, etc.) from the same origin. This makes every
    feature fully interactive:
    
    - Ticker search with autocomplete
    - Interactive price charts (line/candlestick with SMA/EMA/volume)
    - Watchlist management
    - Multi-ticker comparison
    - CSV export
    - Earnings table filtering/sorting
    - Dark/light theme toggle
    - Auto-refresh
    
    Example:
        earnings-engine dashboard
        earnings-engine dashboard --port 8080
    """
    import threading
    import time
    import webbrowser
    import uvicorn
    from earnings_engine.api.server import app as api_app
    
    logger = _get_cli_logger()
    
    click.echo(f"🌐 Starting API server on http://{host}:{port} ...")
    logger.info("dashboard command started host=%s port=%s", host, port)
    
    # Start the API server in a background thread
    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": api_app, "host": host, "port": port, "log_level": "warning"},
        daemon=True,
    )
    server_thread.start()
    
    # Wait for the server to be ready
    import urllib.request
    dashboard_url = f"http://{host}:{port}/dashboard"
    for attempt in range(30):
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=1):
                break
        except Exception:
            time.sleep(0.5)
    else:
        click.echo("❌ API server failed to start. Check logs for errors.")
        logger.error("dashboard command failed to start API server")
        return
    
    click.echo(f"✅ Dashboard available at: {dashboard_url}")
    click.echo(f"🌐 Opening in browser...")
    
    # Open the dashboard in the default browser
    webbrowser.open(dashboard_url)
    
    click.echo("Press Ctrl+C to stop the server.")
    logger.info("dashboard opened url=%s", dashboard_url)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\n👋 Dashboard server stopped.")
        logger.info("dashboard server stopped")


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
