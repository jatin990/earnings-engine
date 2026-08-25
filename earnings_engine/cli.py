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
from earnings_engine.data.earnings import ingest_nse_result_calendar
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.market_context import enrich_upcoming_results
from earnings_engine.data.universe import ingest_market_caps, load_all, load_universe, load_universe_from_file
from earnings_engine.emailing import send_report_email
from earnings_engine.kronos_predictor import (
    generate_html_report,
    generate_markdown_report,
    predict_portfolio,
    run_kronos_with_cache,
)
from earnings_engine.predict import run_gbm_with_cache
from earnings_engine.logging_utils import get_logger
from earnings_engine.reports.render import render_dashboard, render_upcoming_results_report


def _get_cli_logger():
    return get_logger("earnings_engine.cli", base_dir=PROJECT_ROOT)


def _extract_report_date(name: str) -> str | None:
    """Extract the YYYY-MM-DD date from a report filename.

    Handles both ``upcoming-results-2026-08-03-201504.html`` (timestamped)
    and ``upcoming-results-2026-08-03.html`` (date-only) formats.
    """
    import re

    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else None


def _write_report_cache_snapshot(csv_path: Path, enriched: pd.DataFrame, settings: Settings) -> None:
    """Write a JSON sidecar capturing the cache state when the report was generated.

    This lets the checker detect if the underlying cache (earnings, prices,
    market cap) changed between report generation and checking.
    """
    import json
    from earnings_engine.data.earnings import load_earnings
    from earnings_engine.data.prices import load_price_metrics
    from earnings_engine.data.universe import load_market_cap

    snapshot_path = csv_path.with_suffix(".cache.json")
    tickers = enriched["ticker"].dropna().unique().tolist() if "ticker" in enriched.columns else []

    snapshot = {
        "generated_at": datetime.now().isoformat(),
        "tickers": tickers,
        "earnings_freshness": {},
        "price_metrics_dates": {},
        "market_cap_dates": {},
    }

    for ticker in tickers:
        try:
            earnings = load_earnings(ticker, settings)
            if not earnings.empty:
                snapshot["earnings_freshness"][ticker] = earnings["earnings_date"].max().isoformat()
        except Exception:
            pass

        try:
            metrics = load_price_metrics(ticker, settings)
            if metrics and "as_of_date" in metrics:
                snapshot["price_metrics_dates"][ticker] = str(metrics["as_of_date"])
        except Exception:
            pass

        try:
            mc = load_market_cap(ticker, settings)
            if mc is not None:
                snapshot["market_cap_dates"][ticker] = datetime.now().isoformat()
        except Exception:
            pass

    try:
        snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except OSError:
        pass


def _cleanup_previous_artifacts(root: Path | None = None) -> None:
    """Archive previous-day reports, keep last 3 same-day files, and dedupe archive.

    - Files in ``reports/output/`` from a previous day are moved to ``archive/``.
    - Files in ``reports/output/`` from today: keep the latest 3, delete older ones.
    - ``archive/`` is deduped to keep only the latest file per (report type, day).
    """
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

    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1) Move previous-day files from output/ to archive/; keep last 3 same-day files.
    try:
        today_files = []
        for artifact in sorted(output_dir.iterdir()):
            if not artifact.is_file():
                continue
            date_str = _extract_report_date(artifact.name)
            if date_str is None:
                # Unknown format — keep it in output/ untouched.
                continue
            if date_str == today_str:
                today_files.append(artifact)
            else:
                # Previous-day file: move to archive/.
                target = archive_dir / artifact.name
                try:
                    if target.exists():
                        target.unlink()
                    shutil.move(str(artifact), str(target))
                except (OSError, shutil.Error):
                    continue
        
        # Keep only the latest 3 same-day files, delete older ones
        if len(today_files) > 3:
            for artifact in today_files[:-3]:
                try:
                    artifact.unlink(missing_ok=True)
                except OSError:
                    continue
    except OSError:
        pass

    # 2) Dedupe archive/: keep only the latest file per (report type, day, extension).
    try:
        by_key: dict[tuple[str, str, str], Path] = {}
        for artifact in sorted(archive_dir.iterdir()):
            if not artifact.is_file():
                continue
            date_str = _extract_report_date(artifact.name)
            if date_str is None:
                continue
            # Report type = everything before the date in the filename.
            prefix = artifact.name.split(date_str)[0].rstrip("-")
            ext = artifact.suffix.lower()
            key = (prefix, date_str, ext)
            existing = by_key.get(key)
            if existing is None or artifact.name > existing.name:
                by_key[key] = artifact
        for artifact in sorted(archive_dir.iterdir()):
            if not artifact.is_file():
                continue
            date_str = _extract_report_date(artifact.name)
            if date_str is None:
                continue
            prefix = artifact.name.split(date_str)[0].rstrip("-")
            ext = artifact.suffix.lower()
            key = (prefix, date_str, ext)
            if by_key.get(key) != artifact:
                try:
                    artifact.unlink(missing_ok=True)
                except OSError:
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
    from earnings_engine.data.migrations import apply_migrations
    from earnings_engine.logging_utils import log_startup_diagnostics
    try:
        apply_migrations(Settings())
    except Exception:
        pass
    log_startup_diagnostics(_get_cli_logger())
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
@click.option("--nse-calendar/--no-nse-calendar", "nse_calendar", default=True,
              help="Also ingest upcoming result dates from the official NSE result-calendar API (NSE markets only).")
@click.option("--incremental/--full", "incremental", default=False,
              help="Only fetch earnings for tickers missing earnings data (faster).")
def ingest(market, ticker, force, prices, earnings_flag, universe_file, nse_calendar, incremental) -> None:
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
        if incremental:
            results = earnings_mod.ingest_earnings_incremental(tickers, settings)
            logger.info("ingest earnings incremental completed results=%s", results)
            click.echo(f"Earnings incremental: {results['fetched']} fetched, "
                       f"{results['already_cached']} cached, "
                       f"{results['skipped_no_listing']} skipped (no listing/too new).")
        else:
            results = earnings_mod.ingest_earnings(tickers, settings, force=force)
            logger.info("ingest earnings completed results=%s", results)
            ok = sum(1 for n in results.values() if n > 0)
            empty = [t for t, n in results.items() if n == 0]
            click.echo(f"Earnings: {ok}/{len(tickers)} tickers with events.")
            if empty:
                click.echo(f"  No earnings data: {', '.join(empty)}")

    # Ingest official NSE result-calendar dates (one API call covers all NSE stocks)
    if nse_calendar and (market is None or market.upper() in ("IN", "NSE_ALL", "NSE_LARGE_CAP")):
        click.echo("Fetching official NSE result calendar...")
        nse_result = ingest_nse_result_calendar(settings)
        logger.info("ingest nse result-calendar completed result=%s", nse_result)
        click.echo(f"NSE result calendar: {nse_result['total']} events, {nse_result['inserted']} new.")

    # Fetch and cache market cap for all tickers
    click.echo(f"Fetching market cap for {len(tickers)} tickers...")
    mc_results = ingest_market_caps(tickers, force=force)
    logger.info("ingest market cap completed results=%s", mc_results)
    mc_ok = sum(1 for v in mc_results.values() if v > 0)
    click.echo(f"Market cap: {mc_ok}/{len(tickers)} tickers with data.")


@cli.command("ingest-industries")
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
@click.option("--ticker", "-t", multiple=True, help="Specific ticker(s) instead of the universe.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--force", is_flag=True, default=False,
              help="Ignore the industry cache and re-fetch every ticker.")
def ingest_industries(market, ticker, universe_file, force) -> None:
    """Fetch and cache industry classifications from yfinance for a universe.

    Classifications (industry, with sector fallback) are stored in the shared
    SQLite database so the Industries dashboard tab can group recent earnings
    moves by industry without hitting yfinance on every view.

    Examples:
        earnings-engine ingest-industries --market NSE_ALL
        earnings-engine ingest-industries --ticker RELIANCE.NS TCS.NS
    """
    from earnings_engine.data.industry import ingest_industries as _ingest

    settings = Settings()
    tickers = _resolve_tickers(market, ticker, universe_file)
    logger = _get_cli_logger()
    click.echo(f"Fetching industry for {len(tickers)} tickers...")
    logger.info("ingest-industries started market=%s tickers=%s force=%s", market, tickers, force)
    results = _ingest(tickers, settings, force=force)
    ok = sum(1 for v in results.values() if v > 0)
    click.echo(f"Industry classification: {ok}/{len(tickers)} tickers classified.")
    logger.info("ingest-industries complete ok=%s total=%s", ok, len(tickers))

@cli.command("recent-results")
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--correction-pct", default=5.0, show_default=True,
              help="Pullback % from the post-result high that flags a buy-the-dip candidate.")
def recent_results(market, universe_file, correction_pct) -> None:
    """Show today/yesterday results with momentum + buy-the-dip corrections.

    For each recent result this prints the post-result 7-day high/low, the
    current pullback from the high, and flags buy-the-dip candidates (positive
    results that corrected by at least --correction-pct).
    """
    from earnings_engine.data.recent_results import get_recent_results as _grr

    settings = Settings()
    tickers = _resolve_tickers(market, (), universe_file)
    logger = _get_cli_logger()
    click.echo(f"Recent results for {len(tickers)} tickers (correction >= {correction_pct}%)")
    result = _grr(tickers, settings, correction_pct=correction_pct)
    rows = result["rows"]
    if not rows:
        click.echo("No results from yesterday/today in cache.")
        return
    click.echo(f"  Total: {result['total']}  Buy-the-dip: {result['buy_dip_count']}  "
               f"Today: {result['today_count']}  Yesterday: {result['yesterday_count']}\n")

    def _fmt(v):
        return f"{v:.1f}% " if v is not None else "—    "

    def _fmt_price(v):
        return f"{v:.2f}" if v is not None else "—"

    header = f"{'Ticker':<16}{'Date':<12}{'Day':<10}{'Price':>9}{'7dHigh':>9}{'7dLow':>9}{'Curr':>10}{'Pull':>10}  BuyDip"
    click.echo(header)
    click.echo("-" * len(header))
    for r in rows:
        flag = "✅" if r["is_buy_dip"] else ""
        click.echo(
            f"{r['ticker']:<16}{r['earnings_date']:<12}{r['day_label']:<10}"
            f"{_fmt_price(r['current_price']):>9}{_fmt(r['high_pct']):>9}{_fmt(r['low_pct']):>9}"
            f"{_fmt(r['current_pct']):>10}{_fmt(r['pullback_from_high']):>10}  {flag}"
        )




@cli.command()
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--days", default=14, show_default=True, help="Look-ahead window in days.")
@click.option("--start-date", "--from", "start_date", default=None,
              help="Start date (YYYY-MM-DD) for the look-ahead window. Defaults to today.")
def calendar(market, days, universe_file, start_date) -> None:
    """Show upcoming earnings events from the local cache."""
    settings = Settings()
    tickers = _resolve_tickers(market, (), universe_file)
    logger = _get_cli_logger()
    click.echo(f"Calendar for {len(tickers)} tickers")
    logger.info("calendar requested market=%s days=%s start_date=%s tickers=%s", market, days, start_date, tickers)
    click.echo(f"Tickers: {', '.join(tickers)}")
    df = earnings_mod.upcoming_earnings(tickers, settings, days=days, start_date=start_date)
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
@click.option("--start-date", "--from", "start_date", default=None,
              help="Start date (YYYY-MM-DD) for the look-ahead window. Defaults to today.")
@click.option("--source", type=click.Choice(["yfinance", "nse", "all"], case_sensitive=False), default="all",
              help="Calendar source: yfinance (per-ticker), nse (official NSE event-calendar), or all (default).")
@click.option("--check", is_flag=True, default=False,
              help="Run the report checker subworkflow to verify each field against the database.")
@click.option("--cache-only", is_flag=True, default=False,
              help="Render purely from today's cached predictions; do not run Kronos/GBM.")
def upcoming_results(market, days, universe_file, source, start_date, check, cache_only) -> None:
    """List all stocks with earnings results in the next N days."""
    settings = Settings()
    tickers = _resolve_tickers(market, (), universe_file)
    logger = _get_cli_logger()
    click.echo(f"Upcoming results for {len(tickers)} tickers (source={source})")
    logger.info("upcoming-results requested market=%s days=%s start_date=%s tickers=%s source=%s",
                market, days, start_date, len(tickers), source)
    src = None if source == "all" else source
    df = earnings_mod.upcoming_earnings(tickers, settings, days=days, source=src, start_date=start_date)
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

    # Attach Kronos 14-day price predictions and GBM earnings predictions.
    # These are best-effort: if the Kronos library or dataset is unavailable,
    # the columns are left empty and the ledger shows "—".
    #
    # Both engines route through the cache-aware runners so the report reuses
    # today's results instead of re-running the models / re-downloading yfinance:
    #   1. Daily JSON prediction cache hit  -> reuse (no model, no yfinance).
    #   2. JSON miss but Kronos audit has today's rows -> reuse from SQLite audit.
    #   3. Only on a genuine miss -> run the model once, save to JSON cache, and
    #      (Kronos) write audit rows.
    enriched["kronos_14d"] = None
    enriched["gbm_prediction"] = None
    try:
        from earnings_engine.kronos_predictor import run_kronos_with_cache
        from earnings_engine.predict import run_gbm_with_cache
        from earnings_engine.prediction_cache import load_prediction_cache

        ticker_list = enriched["ticker"].dropna().unique().tolist()
        logger.info("upcoming-results attaching Kronos + GBM predictions for %s tickers", len(ticker_list))

        if cache_only:
            # --cache-only: never run the models; only use what's already cached.
            # Use partial read so we get whatever coverage exists (not all-or-nothing),
            # and filter out failed-ticker markers so the renderer doesn't choke.
            from earnings_engine.prediction_cache import load_prediction_cache_partial
            cached = load_prediction_cache_partial(ticker_list)
            kronos_map = {t: v for t, v in (cached.get("kronos") or {}).items() if not v.get("failed")}
            gbm_map = {t: v for t, v in (cached.get("gbm") or {}).items() if not v.get("failed")}
            logger.info("upcoming-results --cache-only: using cached predictions for %s kronos + %s gbm tickers",
                        len(kronos_map), len(gbm_map))
        else:
            # Cache-aware runners: reuse JSON cache -> audit trail -> run only on miss.
            kronos_map = {}
            try:
                forecasts = run_kronos_with_cache(
                    ticker_list,
                    lookback=120,
                    pred_len=14,
                    audit=True,
                )
                kronos_map = {fc["symbol"]: fc for fc in forecasts if fc}
            except Exception as e:
                logger.warning("upcoming-results Kronos prediction failed: %s", e)

            gbm_map = {}
            try:
                gbm = run_gbm_with_cache(ticker_list, settings, days=days)
                if isinstance(gbm, dict) and "error" not in gbm:
                    gbm_map = gbm
            except Exception as e:
                logger.warning("upcoming-results GBM prediction failed: %s", e)

        for idx, row in enriched.iterrows():
            t = row["ticker"]
            if t in gbm_map:
                enriched.at[idx, "gbm_prediction"] = gbm_map[t]
            if t in kronos_map:
                enriched.at[idx, "kronos_14d"] = kronos_map[t]
    except Exception as e:
        logger.warning("upcoming-results prediction attachment failed: %s", e)

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
    stamp = datetime.now().strftime("%Y-%m-%d")
    market_str = market.upper() if market else "ALL"
    filename_base = f"upcoming-results-{market_str}-{days}d-{stamp}"
    csv_path = output_dir / f"{filename_base}.csv"
    enriched.to_csv(csv_path, index=False)
    logger.info("upcoming-results exported csv=%s", csv_path)

    # Write a cache-version sidecar so the checker can detect stale reports.
    _write_report_cache_snapshot(csv_path, enriched, settings)

    html_path = output_dir / f"{filename_base}.html"
    report_html = render_upcoming_results_report(enriched, csv_path=csv_path, html_path=html_path)
    logger.info("upcoming-results rendered html=%s", html_path)

    click.echo(f"\nSaved CSV: {csv_path}")
    click.echo(f"Saved HTML report: {html_path}")
    logger.info("saved csv path=%s", csv_path)

    if check:
        from earnings_engine.reports.checker import check_report_frame
        result = check_report_frame(enriched, settings)
        click.echo(f"\nReport checker: {result.summary()}")
        for inc in result.inconsistencies:
            click.echo(f"  INCONSISTENCY {inc.ticker} {inc.field}: report={inc.report_value} expected={inc.expected_value} ({inc.reason})")
        logger.info("report checker complete verified=%s verified_empty=%s inconsistencies=%s",
                    result.verified, result.verified_empty, len(result.inconsistencies))

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


@cli.command("check-report")
@click.option("--csv", "csv_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True,
              help="Path to an upcoming-results CSV report to verify.")
def check_report(csv_path: Path) -> None:
    """Verify every field in an existing report CSV against the database.

    For each row, each field is checked against the cached database value.
    If a field is empty in the report, the original calculation is re-run
    from the raw data source to confirm it is genuinely empty (not a bug).
    Any inconsistencies are logged.
    """
    from earnings_engine.reports.checker import check_report_csv

    settings = Settings()
    logger = _get_cli_logger()
    click.echo(f"Checking report: {csv_path}")
    logger.info("check-report started csv=%s", csv_path)
    result = check_report_csv(csv_path, settings)
    click.echo(f"\nReport checker: {result.summary()}")
    for inc in result.inconsistencies:
        click.echo(f"  INCONSISTENCY {inc.ticker} {inc.field}: report={inc.report_value} expected={inc.expected_value} ({inc.reason})")
    logger.info("check-report complete verified=%s verified_empty=%s inconsistencies=%s",
                result.verified, result.verified_empty, len(result.inconsistencies))


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


@cli.command("swing-backtest")
@click.option("--watchlist", "-w", default="my_watchlist", show_default=True,
              help="Watchlist name to backtest across.")
@click.option("--ticker", "-t", "tickers", multiple=True,
              help="Specific ticker(s) to backtest (overrides watchlist).")
@click.option("--capital", default=100000.0, show_default=True, help="Initial portfolio capital.")
@click.option("--risk-pct", default=0.015, show_default=True, help="Risk fraction per trade (e.g. 0.015 = 1.5%).")
@click.option("--stop-pct", default=0.02, show_default=True, help="Stop loss buffer below support.")
@click.option("--max-hold", default=21, show_default=True, help="Max holding days (time stop).")
@click.option("--lookback", default=20, show_default=True, help="Channel lookback in bars.")
@click.option("--months", default=6, show_default=True, help="Months of historical price data.")
@click.option("--export-csv", type=click.Path(dir_okay=False, writable=True), default=None,
              help="Optional file path to export trade log as CSV.")
def swing_backtest_cmd(watchlist, tickers, capital, risk_pct, stop_pct, max_hold, lookback, months, export_csv) -> None:
    """Run swing-channel backtesting on watchlist or specific tickers."""
    from earnings_engine.backtest.swing_backtest import SwingBacktestConfig, run_swing_backtest
    from earnings_engine.data.universe import load_universe_from_file

    settings = Settings()
    symbols = list(tickers)
    if not symbols and watchlist:
        loaded = load_universe_from_file(watchlist, settings=settings)
        symbols = [item["ticker"] for item in loaded] if loaded else []

    if not symbols:
        click.echo(f"No tickers found for watchlist '{watchlist}'. Provide -t tickers or check watchlist.")
        return

    cfg = SwingBacktestConfig(
        initial_capital=capital,
        risk_per_trade_pct=risk_pct,
        stop_loss_buffer_pct=stop_pct,
        max_hold_days=max_hold,
        channel_lookback=lookback,
        lookback_months=months,
    )

    click.echo(f"Running swing channel backtest across {len(symbols)} tickers...")
    res = run_swing_backtest(symbols, cfg=cfg, settings=settings)

    click.echo("=" * 60)
    click.echo("SWING CHANNEL BACKTEST RESULTS")
    click.echo("=" * 60)
    click.echo(f"  Initial Capital  : ₹{res.initial_capital:,.2f}")
    click.echo(f"  Final Capital    : ₹{res.final_capital:,.2f}")
    click.echo(f"  Total Return     : {res.total_return_pct:+.2f}%")
    click.echo(f"  Annualized Return: {res.annualized_return_pct:+.2f}%")
    click.echo(f"  Sharpe Ratio     : {res.sharpe_ratio:.3f}")
    click.echo(f"  Max Drawdown     : -{res.max_drawdown_pct:.2f}%")
    click.echo(f"  Total Trades     : {res.total_trades}")
    click.echo(f"  Win Rate         : {res.win_rate_pct:.1f}%")
    click.echo(f"  Profit Factor    : {res.profit_factor:.2f}")
    click.echo(f"  Avg Trade PnL    : {res.avg_trade_pnl_pct:+.2f}%")
    click.echo(f"  Avg Hold Days    : {res.avg_hold_days:.1f} days")
    click.echo("=" * 60)

    if export_csv and res.trades:
        df_trades = pd.DataFrame([t.to_dict() for t in res.trades])
        df_trades.to_csv(export_csv, index=False)
        click.echo(f"Exported {len(df_trades)} trades to {export_csv}")


@cli.command()
@click.option("--model", "model_name", default="gbm", show_default=True)
@click.option("--days", default=14, show_default=True, help="Look-ahead window for upcoming earnings.")
@click.option("--start-date", "--from", "start_date", default=None,
              help="Start date (YYYY-MM-DD) for the look-ahead window. Defaults to today.")
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
@click.option("--ticker", "-t", multiple=True)
@click.option("--report/--no-report", "write_report", default=True, show_default=True,
              help="Also write CSV + HTML to reports/output/.")
@click.option("--force", is_flag=True, default=False,
              help="Ignore today's cached predictions and re-run the model.")
def predict(model_name, days, market, ticker, write_report, start_date, force) -> None:
    """Predict direction + confidence for upcoming earnings events."""
    from earnings_engine.reports.render import render_predictions

    settings = Settings()
    tickers = _resolve_tickers(market, ticker)
    logger = _get_cli_logger()
    logger.info("predict requested market=%s days=%s start_date=%s model=%s tickers=%s force=%s",
                market, days, start_date, model_name, tickers, force)

    # Progress callback for CLI output
    def progress_callback(current: int, total: int, symbol: str, status: str = "ok"):
        if status == "skip":
            click.echo(f"  [{current}/{total}] Skipping (no event): {symbol}")
        else:
            click.echo(f"  [{current}/{total}] Scoring: {symbol}")

    # Cache-aware runner: reuses today's cached GBM predictions unless --force
    # is given; on a miss it trains the model, scores upcoming events, and
    # persists the per-ticker map to the daily prediction cache.
    gbm_map = run_gbm_with_cache(
        tickers,
        settings,
        days=days,
        progress_callback=progress_callback,
        force=force,
    )
    if not isinstance(gbm_map, dict) or "error" in gbm_map:
        click.echo("GBM prediction unavailable: %s", gbm_map.get("error", "unknown"))
        return
    # Build a render_predictions-compatible frame from the per-ticker GBM map.
    # The map lacks market/n_past_events/asof_date and stores earnings_date as a
    # string, so we reconstruct those columns here for the report renderer.
    from earnings_engine.config import market_of

    preds = pd.DataFrame(gbm_map).T.reset_index().rename(columns={"index": "ticker"})
    preds["market"] = preds["ticker"].map(market_of)
    preds["n_past_events"] = 0
    preds["asof_date"] = pd.Timestamp.today().normalize()
    preds["earnings_date"] = pd.to_datetime(preds["earnings_date"], errors="coerce")
    logger.info("predict complete rows=%s", len(preds))
    if preds.empty:
        click.echo("No upcoming earnings with sufficient data. "
                   "Run `earnings-engine ingest` to refresh the calendar.")
        return
    show = preds[["ticker", "earnings_date", "direction", "confidence", "p_up", "train_events", "model"]].copy()
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
@click.option("--gpu-batch", "gpu_batch", type=int, default=None,
              help="Number of ticker sequences per GPU forward pass (default: settings.kronos_gpu_batch_size, e.g. 2).")
@click.option("--fetch-workers", "fetch_workers", type=int, default=None,
              help="Parallel yfinance data-fetch workers (default: settings.kronos_fetch_workers).")
@click.option("--device", default=None,
              help="Device for model inference: cuda, cuda:0, cpu (default: auto-detected CUDA if available).")
@click.option("--force", is_flag=True, default=False,
              help="Ignore today's cached predictions and re-run the model.")
def kronos_predict(market, ticker, universe_file, lookback, pred_len, gpu_batch, fetch_workers, device, force) -> None:
    """Generate 14-day price predictions using Kronos AI model.
    
    This command uses the Kronos foundation model to predict price movements
    for the next N days, including support/resistance levels and AI-generated
    trading explanations.
    
    Examples:
        earnings-engine kronos-predict --market IN
        earnings-engine kronos-predict --ticker TCS.NS INFY.NS RELIANCE.NS --device cuda:0
        earnings-engine kronos-predict --universe-file my_stocks.txt
    """
    settings = Settings()
    tickers = _resolve_tickers(market, ticker, universe_file)
    logger = _get_cli_logger()
    
    if not tickers:
        click.echo("No tickers specified. Use --market, --ticker, or --universe-file.")
        return
    
    # Apply per-run concurrency overrides (fall back to settings defaults).
    if gpu_batch is not None:
        settings.kronos_gpu_batch_size = gpu_batch
    if fetch_workers is not None:
        settings.kronos_fetch_workers = fetch_workers
    
    active_device = settings.resolve_device(device)
    click.echo(f"🔮 Kronos AI Price Prediction for {len(tickers)} stocks")
    click.echo(f"   Lookback: {lookback} days | Prediction horizon: {pred_len} days | Device: {active_device}")
    click.echo(f"   GPU batch: {settings.kronos_gpu_batch_size} | Fetch workers: {settings.kronos_fetch_workers}")
    click.echo(f"   Tickers: {', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''}")
    logger.info("kronos-predict started market=%s tickers=%s lookback=%s pred_len=%s device=%s gpu_batch=%s fetch_workers=%s", 
                market, tickers, lookback, pred_len, active_device, settings.kronos_gpu_batch_size, settings.kronos_fetch_workers)
    
    # Progress callback for CLI output
    def progress_callback(current: int, total: int, symbol: str):
        click.echo(f"  [{current}/{total}] Predicting: {symbol}")
    
    # Generate predictions (cache-aware: reuses today's cached Kronos results
    # unless --force is given; on a miss it runs the model, saves to the daily
    # cache, and writes each forecast to the SQLite audit trail so it appears
    # in the dashboard's Kronos Audit/Latest tabs).
    forecasts = run_kronos_with_cache(
        tickers,
        lookback=lookback,
        pred_len=pred_len,
        device=active_device,
        progress_callback=progress_callback,
        force=force,
        audit=True,
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


@cli.command("cache-predictions")
@click.option("--market", type=click.Choice(["IN", "US", "NSE_ALL", "NSE_LARGE_CAP"], case_sensitive=False), default=None,
              help="Choose a market. NSE_ALL fetches all NSE stocks. NSE_LARGE_CAP fetches NSE stocks with market cap > 1000cr.")
@click.option("--ticker", "-t", multiple=True, help="Specific ticker(s) instead of the universe.")
@click.option("--universe-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Load tickers from a plain-text file instead of the built-in universe.")
@click.option("--days", default=14, show_default=True, help="Look-ahead window in days (GBM).")
@click.option("--kronos/--no-kronos", "run_kronos", default=True,
              help="Run Kronos 14-day price predictions (writes to daily cache + SQLite audit).")
@click.option("--gbm/--no-gbm", "run_gbm", default=True,
              help="Run GBM earnings-direction predictions (writes to daily cache).")
@click.option("--earnings-only", is_flag=True, default=False,
              help="Only predict stocks with earnings results in the next --days days (much faster).")
@click.option("--gpu-batch", "gpu_batch", type=int, default=None,
              help="Kronos: number of ticker sequences per GPU forward pass (default: settings.kronos_gpu_batch_size, e.g. 2).")
@click.option("--fetch-workers", "fetch_workers", type=int, default=None,
              help="Kronos: parallel yfinance data-fetch workers (default: settings.kronos_fetch_workers).")
@click.option("--device", default=None,
              help="Device for Kronos model inference: cuda, cuda:0, cpu (default: auto-detected CUDA if available).")
@click.option("--force", is_flag=True, default=False,
              help="Ignore today's cached predictions and re-run the models.")
def cache_predictions(market, ticker, universe_file, days, run_kronos, run_gbm, earnings_only, gpu_batch, fetch_workers, device, force) -> None:
    """Pre-compute Kronos + GBM predictions and persist them to the daily cache.

    This is the "cache data first, then run reports" workflow. It runs each
    selected engine standalone with live progress, saves the results to today's
    prediction cache, and (for Kronos) writes each forecast to the SQLite audit
    trail so it appears in the dashboard's Kronos Audit/Latest tabs.

    After this completes, ``upcoming-results --cache-only`` (or a plain
    ``upcoming-results`` run) renders the report instantly from the cache.

    Examples:
        earnings-engine cache-predictions --market NSE_ALL
        earnings-engine cache-predictions --ticker TCS.NS INFY.NS --no-gbm --device cuda:0
        earnings-engine cache-predictions --market IN --force
    """
    settings = Settings()
    tickers = _resolve_tickers(market, ticker, universe_file)
    logger = _get_cli_logger()

    if not tickers:
        click.echo("No tickers specified. Use --market, --ticker, or --universe-file.")
        return

    if not run_kronos and not run_gbm:
        click.echo("Nothing to do: both --no-kronos and --no-gbm were given.")
        return

    # Apply per-run Kronos concurrency overrides (fall back to settings defaults).
    if gpu_batch is not None:
        settings.kronos_gpu_batch_size = gpu_batch
    if fetch_workers is not None:
        settings.kronos_fetch_workers = fetch_workers

    active_device = settings.resolve_device(device)

    # Filter to only stocks with upcoming earnings if --earnings-only is set.
    if earnings_only:
        click.echo(f"Filtering to stocks with earnings in the next {days} days...")
        earnings_df = earnings_mod.upcoming_earnings(tickers, settings, days=days)
        if earnings_df.empty:
            click.echo("No stocks with upcoming earnings in the given window. Nothing to do.")
            return
        tickers = earnings_df["ticker"].dropna().unique().tolist()
        click.echo(f"   {len(tickers)} stocks with upcoming earnings")

    click.echo(f"📦 Pre-computing predictions for {len(tickers)} tickers")
    click.echo(f"   Kronos: {'ON' if run_kronos else 'OFF'} | GBM: {'ON' if run_gbm else 'OFF'} | force: {force}")
    if run_kronos:
        click.echo(f"   Kronos Device: {active_device} | GPU batch: {settings.kronos_gpu_batch_size} | Fetch workers: {settings.kronos_fetch_workers}")
    logger.info("cache-predictions started market=%s tickers=%s days=%s kronos=%s gbm=%s earnings_only=%s force=%s device=%s gpu_batch=%s fetch_workers=%s",
                market, tickers, days, run_kronos, run_gbm, earnings_only, force, active_device,
                settings.kronos_gpu_batch_size, settings.kronos_fetch_workers)

    if run_gbm:
        click.echo("\n[1/2] Running GBM earnings-direction predictions...")
        def gbm_progress(current: int, total: int, symbol: str, status: str = "ok"):
            if status == "skip":
                click.echo(f"  [{current}/{total}] Skipping (no event): {symbol}")
            else:
                click.echo(f"  [{current}/{total}] Scoring: {symbol}")
        gbm_map = run_gbm_with_cache(
            tickers,
            settings,
            days=days,
            progress_callback=gbm_progress,
            force=force,
        )
        if isinstance(gbm_map, dict) and "error" not in gbm_map:
            click.echo(f"  ✅ GBM: {len(gbm_map)} predictions cached.")
        else:
            click.echo(f"  ⚠️  GBM unavailable: {gbm_map.get('error', 'unknown')}")
        logger.info("cache-predictions gbm complete count=%s", len(gbm_map) if isinstance(gbm_map, dict) else 0)

    if run_kronos:
        click.echo("\n[2/2] Running Kronos 14-day price predictions...")
        def kronos_progress(current: int, total: int, symbol: str):
            click.echo(f"  [{current}/{total}] Predicting: {symbol}")
        forecasts = run_kronos_with_cache(
            tickers,
            lookback=120,
            pred_len=14,
            device=active_device,
            progress_callback=kronos_progress,
            force=force,
            audit=True,
        )
        click.echo(f"  ✅ Kronos: {len(forecasts)} predictions cached + written to audit trail.")
        logger.info("cache-predictions kronos complete count=%s", len(forecasts))

    click.echo("\n✅ Done. Run `earnings-engine upcoming-results --cache-only` to render the report from cache.")


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


@cli.group("audit-strategy")
def audit_strategy() -> None:
    """Track & audit news-derived stock predictions per strategy."""
    pass


@audit_strategy.command("log")
@click.option("--ticker", "-t", required=False, help="Stock ticker (e.g., RELIANCE.NS, AAPL).")
@click.option("--strategy", "-s", required=False, help="Strategy name (e.g., News_Breakout, Earnings_Drift).")
@click.option("--signal", type=click.Choice(["BULLISH", "BEARISH", "NEUTRAL"], case_sensitive=False),
              required=False, help="Predicted direction.")
@click.option("--confidence", type=float, default=None, help="Confidence level (0-100).")
@click.option("--entry-price", type=float, default=None, help="Entry price (auto-resolved from cache if omitted).")
@click.option("--expected-return", type=float, default=None, help="Expected return percentage.")
@click.option("--horizon", type=click.Choice(["1D", "5D", "14D", "POST_EARNINGS"], case_sensitive=False),
              default="1D", show_default=True, help="Holding horizon.")
@click.option("--target-date", default=None, help="Target evaluation date (YYYY-MM-DD). Auto-set from horizon if omitted.")
@click.option("--news-source", default=None, help="News source (e.g., MoneyControl, Reuters).")
@click.option("--headline", default=None, help="News headline or catalyst.")
@click.option("--notes", default=None, help="Additional notes.")
@click.option("--file", "json_file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Bulk-log predictions from a JSON file (array of prediction objects).")
def audit_log(ticker, strategy, signal, confidence, entry_price, expected_return,
              horizon, target_date, news_source, headline, notes, json_file) -> None:
    """Log a daily news-derived stock prediction (or bulk-log from a JSON file)."""
    import json as json_mod
    from earnings_engine.data.strategy_auditor import log_prediction, log_predictions_bulk

    logger = _get_cli_logger()

    if json_file:
        data = json_mod.loads(Path(json_file).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = [data]
        ids = log_predictions_bulk(data)
        click.echo(f"[OK] Bulk-logged {len(ids)} predictions from {json_file}")
        logger.info("audit-strategy log bulk file=%s count=%d", json_file, len(ids))
        return

    if not ticker or not strategy or not signal:
        click.echo("[ERROR] --ticker, --strategy, and --signal are required (or use --file for bulk).")
        return

    row_id = log_prediction(
        ticker=ticker,
        strategy_name=strategy,
        signal=signal.upper(),
        confidence_pct=confidence,
        entry_price=entry_price,
        expected_return_pct=expected_return,
        holding_horizon=horizon,
        target_date=target_date,
        news_source=news_source,
        news_headline=headline,
        notes=notes,
    )
    click.echo(f"[OK] Logged prediction #{row_id}: {ticker} / {strategy} / {signal.upper()}")
    logger.info("audit-strategy log id=%d ticker=%s strategy=%s signal=%s", row_id, ticker, strategy, signal)


@audit_strategy.command("run")
@click.option("--force", is_flag=True, default=False, help="Re-evaluate already-audited predictions.")
def audit_run(force) -> None:
    """Run the automated auditor — evaluate pending predictions against actual prices."""
    from earnings_engine.data.strategy_auditor import audit_predictions

    logger = _get_cli_logger()
    click.echo("[RUN] Running strategy prediction audit...")
    result = audit_predictions(force=force)
    click.echo(f"[OK] Audit complete: {result['evaluated']} evaluated, {result['pending']} pending, {result['skipped']} skipped")
    logger.info("audit-strategy run result=%s", result)


@audit_strategy.command("metrics")
@click.option("--strategy", "-s", default=None, help="Filter to a specific strategy.")
def audit_metrics(strategy) -> None:
    """Display performance metrics for each strategy."""
    from earnings_engine.data.strategy_auditor import calculate_strategy_metrics, list_strategies

    logger = _get_cli_logger()
    metrics = calculate_strategy_metrics(strategy_name=strategy)

    # Overall summary
    ov = metrics["overall"]
    click.echo("\n" + "=" * 80)
    click.echo("STRATEGY PERFORMANCE METRICS")
    click.echo("=" * 80)

    if ov["total_predictions"] == 0:
        click.echo("\nNo audited predictions found. Log predictions with `audit-strategy log` and run `audit-strategy run`.")
        return

    click.echo(f"\n{'OVERALL':>20}  |  Predictions: {ov['total_predictions']}  |  "
               f"Win Rate: {ov['win_rate_pct']}%  |  Profit Factor: {ov['profit_factor']}  |  "
               f"Avg Return: {ov['avg_return_pct']}%  |  Sharpe: {ov['sharpe_ratio']}")

    # Per-strategy breakdown
    if metrics["by_strategy"]:
        click.echo("\n" + "-" * 80)
        click.echo(f"{'Strategy':<25} {'Preds':>6} {'Wins':>5} {'WR%':>6} {'PF':>7} "
                   f"{'AvgR%':>7} {'CumR%':>8} {'Sharpe':>7} {'Brier':>7}")
        click.echo("-" * 80)
        for sn, sm in sorted(metrics["by_strategy"].items()):
            brier_str = f"{sm['brier_score']:.3f}" if sm["brier_score"] is not None else "  —"
            click.echo(
                f"{sn:<25} {sm['total_predictions']:>6} {sm['wins']:>5} "
                f"{sm['win_rate_pct']:>5.1f}% {str(sm['profit_factor']):>7} "
                f"{sm['avg_return_pct']:>6.2f}% {sm['cumulative_return_pct']:>7.2f}% "
                f"{sm['sharpe_ratio']:>7.2f} {brier_str:>7}"
            )

    # Per-market breakdown
    if metrics["by_market"]:
        click.echo("\n" + "-" * 80)
        click.echo(f"{'Market':<25} {'Preds':>6} {'Wins':>5} {'WR%':>6} {'AvgR%':>7}")
        click.echo("-" * 80)
        for mkt, mm in sorted(metrics["by_market"].items()):
            click.echo(
                f"{mkt:<25} {mm['total_predictions']:>6} {mm['wins']:>5} "
                f"{mm['win_rate_pct']:>5.1f}% {mm['avg_return_pct']:>6.2f}%"
            )

    click.echo()
    logger.info("audit-strategy metrics displayed strategy=%s", strategy)


@audit_strategy.command("import-kronos")
@click.option("--force", is_flag=True, default=False, help="Re-import and re-audit existing predictions.")
def audit_import_kronos(force) -> None:
    """Import historical Kronos predictions into strategy audit ledger and audit outcomes."""
    from earnings_engine.data.strategy_auditor import import_kronos_predictions

    logger = _get_cli_logger()
    click.echo("[IMPORT] Importing historical Kronos predictions into strategy audit ledger...")
    res = import_kronos_predictions(force=force)
    click.echo(f"[OK] Imported {res['imported']} predictions ({res['skipped']} skipped). Audited {res['audited']} outcomes against actual prices.")
    logger.info("audit-strategy import-kronos res=%s", res)


@audit_strategy.command("backtest")
@click.option("--strategy", "-s", default="ALL", help="Strategy to backtest (ALL, Kronos_1Y_Backtest, News_Momentum_Breakout, Earnings_Drift_GBM, Mean_Reversion_52W).")
@click.option("--days", "-d", type=int, default=365, show_default=True, help="Lookback window in days (default: 365 = 1 year).")
@click.option("--universe", "-u", default=None, help="Universe name (e.g. NSE_TOP, US_TOP, IN, US).")
def audit_backtest(strategy, days, universe) -> None:
    """Run 1-year historical strategy backtesting simulation and audit all decisions."""
    from earnings_engine.data.strategy_auditor import backtest_strategy_history

    logger = _get_cli_logger()
    click.echo(f"[BACKTEST] Running {days}-day historical backtest simulation for strategy: {strategy}...")
    res = backtest_strategy_history(strategy_name=strategy, days=days, universe=universe)
    click.echo(f"[OK] Backtest completed! Generated {res['predictions_generated']} decisions ({res['predictions_inserted']} new inserted). Audited {res['audited_count']} outcomes.")
    ov = res.get("overall_metrics", {})
    if ov and ov.get("total_predictions", 0) > 0:
        click.echo(f"[METRICS] Overall Win Rate: {ov.get('win_rate_pct', 0)}% | Profit Factor: {ov.get('profit_factor', 0)} | Sharpe: {ov.get('sharpe_ratio', 0)}")
    logger.info("audit-strategy backtest res=%s", res)


# ---------------------------------------------------------------------------
# Broker & 2FA TOTP CLI Group (pyotp, kiteconnect, smartapi, dhanhq, fyers)
# ---------------------------------------------------------------------------

@cli.group("broker")
def broker_group() -> None:
    """Manage Indian stock brokers, 2FA TOTP logins, and order execution."""
    pass


@broker_group.command("status")
def broker_status_cmd() -> None:
    """Display connection status for Zerodha, Angel One, Dhan, and Fyers."""
    from earnings_engine.brokers.broker_manager import get_broker_manager

    mgr = get_broker_manager()
    st = mgr.get_status()

    click.echo("\n" + "=" * 70)
    click.echo(f"BROKER & TRADING INTEGRATION STATUS [MODE: {st['trading_mode']}]")
    click.echo("=" * 70)
    click.echo(f"Default Broker: {st['default_broker'].upper()}\n")

    for name, info in sorted(st["brokers"].items()):
        conn_str = "[CONNECTED]" if info["connected"] else "[DISCONNECTED]"
        click.echo(f"  {name.upper():<15} {conn_str}")
    click.echo()


@broker_group.command("totp")
@click.option("--secret", "-k", required=True, help="Base32 TOTP secret key provided by broker during 2FA setup.")
def broker_totp_cmd(secret: str) -> None:
    """Generate current 6-digit TOTP code for automated broker login."""
    from earnings_engine.brokers.totp import generate_totp

    try:
        code = generate_totp(secret)
        click.echo(f"[TOTP] Current 6-digit 2FA Code: {code}")
    except Exception as e:
        click.echo(f"[ERROR] Failed to generate TOTP: {e}")


@broker_group.command("quote")
@click.option("--symbol", "-s", required=True, help="Ticker symbol (e.g. RELIANCE, TCS, INFY).")
@click.option("--broker", "-b", default=None, help="Broker name (zerodha, angel_one, dhan, fyers).")
def broker_quote_cmd(symbol: str, broker: str | None) -> None:
    """Fetch live quote for a symbol from connected broker or data providers."""
    from earnings_engine.brokers.broker_manager import get_broker_manager

    mgr = get_broker_manager()
    q = mgr.get_quote(symbol, broker_name=broker)
    click.echo(f"[QUOTE] {symbol.upper()}: Price = {q.get('price')} | High = {q.get('high')} | Low = {q.get('low')} | Provider = {q.get('provider') or q.get('broker')}")


@broker_group.command("trade")
@click.option("--symbol", "-s", required=True, help="Ticker symbol.")
@click.option("--signal", required=True, type=click.Choice(["BULLISH", "BEARISH", "BUY", "SELL"], case_sensitive=False))
@click.option("--qty", "-q", type=int, default=1, show_default=True, help="Order quantity.")
@click.option("--strategy", default="Manual_CLI", help="Strategy name tag.")
@click.option("--broker", "-b", default=None, help="Broker to execute with.")
def broker_trade_cmd(symbol: str, signal: str, qty: int, strategy: str, broker: str | None) -> None:
    """Route a strategy signal to broker or paper execution."""
    from earnings_engine.brokers.broker_manager import get_broker_manager

    sig = "BULLISH" if signal.upper() in ("BULLISH", "BUY") else "BEARISH"
    mgr = get_broker_manager()
    res = mgr.execute_signal(symbol=symbol, signal=sig, quantity=qty, strategy_name=strategy, broker_name=broker)
    if res.get("success"):
        click.echo(f"[OK] Order Placed [{res.get('mode')}]: ID = {res.get('order_id')} | {res.get('side')} {qty} {symbol.upper()}")
    else:
        click.echo(f"[ERROR] Order failed: {res.get('error')}")


# ---------------------------------------------------------------------------
# Options & Option Chain Analytics CLI Group (nselib & jugaad-data)
# ---------------------------------------------------------------------------

@cli.group("options")
def options_group() -> None:
    """Option Chain analytics, PCR (Put-Call Ratio), and Max Pain calculations."""
    pass


@options_group.command("chain")
@click.option("--symbol", "-s", required=True, help="NSE Symbol or Index (e.g. NIFTY, BANKNIFTY, RELIANCE).")
def options_chain_cmd(symbol: str) -> None:
    """Analyze Option Chain data, PCR, Max Pain, and Sentiment."""
    from earnings_engine.data.option_chain import analyze_option_chain

    res = analyze_option_chain(symbol)
    click.echo("\n" + "=" * 70)
    click.echo(f"OPTION CHAIN ANALYTICS: {symbol.upper()} [{res.get('status')}]")
    click.echo("=" * 70)
    click.echo(f"  Sentiment:          {res.get('sentiment')}")
    click.echo(f"  Put-Call Ratio(OI): {res.get('pcr_oi')}")
    click.echo(f"  Put-Call Ratio(Vol):{res.get('pcr_volume')}")
    click.echo(f"  Max Pain Strike:    {res.get('max_pain_strike')}")
    click.echo(f"  Key Support Strike: {res.get('support_strike')}")
    click.echo(f"  Key Resist Strike:  {res.get('resistance_strike')}")
    click.echo(f"  Total Call OI:      {res.get('call_oi_total'):,}")
    click.echo(f"  Total Put OI:       {res.get('put_oi_total'):,}")
    click.echo()


# ---------------------------------------------------------------------------
# Multi-Model AI Consensus CLI Group
# ---------------------------------------------------------------------------

@cli.group("consensus")
def consensus_group() -> None:
    """Multi-Model AI Consensus Predictions, Settlement Tracking & Post-Mortem Diagnostics."""
    pass


@consensus_group.command("predict")
@click.option("--ticker", "-t", required=True, help="Stock ticker (e.g. RELIANCE.NS, INFY.NS, AAPL).")
@click.option("--timeframe", "-d", default=14, type=int, show_default=True, help="Evaluation window in days.")
@click.option("--models", "-m", default=None, help="Comma-separated model IDs (optional).")
def consensus_predict_cmd(ticker: str, timeframe: int, models: str | None) -> None:
    """Run multi-model AI consensus prediction for a stock."""
    from datetime import datetime, timedelta
    from earnings_engine.consensus import context_builder, model_runner, aggregator, storage

    t = ticker.strip().upper()
    click.echo(f"\n[CONSENSUS] Gathering context for {t} ({timeframe}D timeframe)...")
    settings = Settings()
    ctx = context_builder.build_context(t, timeframe_days=timeframe, settings=settings)
    as_of_price = ctx.get("price_action", {}).get("current_price") or 0.0

    if as_of_price <= 0:
        try:
            import yfinance as yf
            as_of_price = float(yf.Ticker(t).fast_info.last_price or 0.0)
        except Exception:
            pass

    click.echo(f"[CONSENSUS] Current Price: ₹{as_of_price:.2f}")

    model_list = [m.strip() for m in models.split(",") if m.strip()] if models else None
    click.echo(f"[CONSENSUS] Dispatching to open-source models via OpenRouter...")
    model_outputs = model_runner.run_consensus_models(context=ctx, models=model_list)

    consensus = aggregator.aggregate_predictions(
        model_results=model_outputs,
        ticker=t,
        as_of_price=as_of_price,
        timeframe_days=timeframe,
    )

    eval_date = (datetime.now() + timedelta(days=timeframe)).strftime("%Y-%m-%d")
    pred_id = storage.save_prediction(consensus, evaluation_date=eval_date, settings=settings)

    dir_color = "green" if consensus["consensus_direction"] == "BULLISH" else ("red" if consensus["consensus_direction"] == "BEARISH" else "yellow")
    click.echo("\n" + "=" * 70)
    click.echo(f"AI CONSENSUS RESULT: {t} (ID: {pred_id})")
    click.echo("=" * 70)
    click.secho(f"  Direction:          {consensus['consensus_direction']}", fg=dir_color, bold=True)
    click.echo(f"  Consensus Strength: {consensus['consensus_strength']:.1f}%")
    click.echo(f"  Agreement Ratio:    {consensus['agreement_ratio']:.0%} ({consensus['valid_count']}/{consensus['model_count']} models)")
    click.echo(f"  Expected Return:    {consensus['consensus_return_pct']:+.2f}%")
    click.echo(f"  Target Price:       ₹{consensus['consensus_target_price']:.2f}")
    if consensus.get("consensus_support"):
        click.echo(f"  Consensus Support:  ₹{consensus['consensus_support']:.2f}")
    if consensus.get("consensus_resistance"):
        click.echo(f"  Consensus Resist:   ₹{consensus['consensus_resistance']:.2f}")
    click.echo(f"  Evaluation Date:    {eval_date}")
    click.echo(f"\n  Synthesized Thesis:\n  {consensus.get('synthesized_thesis')}")
    click.echo("\n  Individual Model Breakdown:")
    for m in consensus.get("models_breakdown", []):
        m_name = m.get("model_name", "Unknown")
        if "error" in m:
            click.echo(f"    - {m_name:<16}: [ERROR] {m.get('error')}")
        else:
            m_dir = m.get("direction", "NEUTRAL")
            m_conf = m.get("confidence_pct", 0)
            m_ret = m.get("target_return_pct", 0.0)
            click.echo(f"    - {m_name:<16}: {m_dir:<8} (Conf: {m_conf}%, Ret: {m_ret:+.1f}%)")
    click.echo()


@consensus_group.command("settle")
@click.option("--date", "-d", default=None, help="Evaluation as-of date (YYYY-MM-DD). Defaults to today.")
def consensus_settle_cmd(date: str | None) -> None:
    """Run settlement worker to grade pending consensus predictions and trigger post-mortems."""
    from earnings_engine.consensus import settlement

    click.echo("\n[SETTLEMENT] Checking mature consensus predictions...")
    res = settlement.settle_pending_predictions(as_of_date=date)
    click.echo(f"  Total Due:    {res['total_due']}")
    click.echo(f"  Settled:      {res['settled_count']}")
    click.secho(f"  Success:      {res['success_count']}", fg="green")
    click.secho(f"  Partial:      {res['partial_count']}", fg="yellow")
    click.secho(f"  Failure:      {res['failure_count']}", fg="red")
    click.echo(f"  Invalidated:  {res['invalidated_count']}")
    click.echo()


@consensus_group.command("stats")
def consensus_stats_cmd() -> None:
    """Display consensus performance metrics, win rates, and model accuracy breakdown."""
    from earnings_engine.consensus import storage

    stats = storage.get_accuracy_stats()
    click.echo("\n" + "=" * 70)
    click.echo("AI CONSENSUS ACCURACY & PERFORMANCE AUDIT")
    click.echo("=" * 70)
    click.echo(f"  Total Predictions:  {stats['total_predictions']}")
    click.echo(f"  Pending:            {stats['pending']}")
    click.echo(f"  Settled:            {stats['settled']}")
    click.secho(f"  Win Rate:           {stats['win_rate']:.1f}%", fg="green" if stats['win_rate'] >= 50 else "yellow", bold=True)
    click.echo(f"  Direction Accuracy: {stats['direction_accuracy']:.1f}%")
    if stats.get("avg_strength_wins"):
        click.echo(f"  Avg Strength (Wins):{stats['avg_strength_wins']:.1f}%")
    if stats.get("avg_strength_losses"):
        click.echo(f"  Avg Strength (Loss):{stats['avg_strength_losses']:.1f}%")

    click.echo("\n  Per-Model Accuracy:")
    for ms in stats.get("model_stats", []):
        click.echo(f"    - {ms['model_name']:<18}: {ms['accuracy']:.1f}% ({ms['correct']}/{ms['predictions']})")

    click.echo("\n  Top Failure Categories:")
    for fc in stats.get("top_failure_categories", []):
        click.echo(f"    - {fc['category']:<28}: {fc['count']} occurrences")
    click.echo()


@cli.command("sync")
def sync_cmd() -> None:
    """Synchronize state between local SQLite database and Upstream Turso Cloud."""
    from earnings_engine.data.turso_sync import sync_local_to_upstream
    click.echo("\n[TURSO-SYNC] Synchronizing local SQLite with upstream Turso Cloud...")
    res = sync_local_to_upstream(Settings())
    if res.get("status") == "success":
        click.secho(f"[SUCCESS] Upstream Sync Complete! Pushed {res['total_pushed']} records, pulled {res['total_pulled']} records in {res['elapsed_seconds']}s.", fg="green", bold=True)
    elif res.get("status") == "skipped":
        click.secho(f"[SKIPPED] {res.get('reason')}", fg="yellow")
    else:
        click.secho(f"[ERROR] Sync failed: {res.get('error')}", fg="red")
    click.echo()


if __name__ == "__main__":
    cli()




