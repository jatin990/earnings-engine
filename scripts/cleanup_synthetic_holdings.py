#!/usr/bin/env python3
"""Cleanup synthetic / fabricated rows from shareholding_patterns and
institutional_accumulation_cache.

Detection heuristics
--------------------
1. Sum-to-100 rows not from the known legitimate 2026-09-13 NSE bulk batch.
2. Tickers matching known test / placeholder names.
3. The 0.45 / 0.55 FII-DII split signature (fii/dii ratio between 0.72-0.92).
4. Rows updated before 2026-09-13 (pre-filing fallback seeds).
5. yfinance cross-check on ALL flagged rows — parallel (4 threads),
   exponential-backoff retry (3 attempts), 0.3s per-thread stagger.

Usage:
    python scripts/cleanup_synthetic_holdings.py              # dry-run (default)
    python scripts/cleanup_synthetic_holdings.py --apply      # actually delete
    python scripts/cleanup_synthetic_holdings.py --verbose     # extra logging
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from earnings_engine.data.db import get_db_connection  # noqa: E402

logger = logging.getLogger("cleanup_synthetic_holdings")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEGITIMATE_BATCH_PREFIX = "2026-09-13T06:49"  # known legitimate NSE bulk batch

TEST_TICKERS = {
    "AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA",
    "CHECK", "COIL", "FLAT", "NONEXISTENT", "SUM",
}

FII_DII_RATIO_LOW = 0.72
FII_DII_RATIO_HIGH = 0.92

YFINANCE_MAX_CHECKS = 50
YFINANCE_SLEEP = 0.3  # seconds between yfinance calls per-thread
YF_WORKERS = 4        # parallel yfinance threads
YF_RETRIES = 3        # retry attempts per ticker
YF_RETRY_DELAY = 2.0  # seconds base delay between retries

PRE_CUTOFF = "2026-09-13"  # anything updated before this date

# Percentage-point tolerance for yfinance cross-check
YF_INSIDER_TOLERANCE = 25.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_test_ticker(ticker: str) -> bool:
    """Return True if ticker is a known test/placeholder name."""
    base = ticker.replace(".NS", "").replace(".BO", "")
    return base.upper() in TEST_TICKERS


def _has_sum_to_100(row: Any) -> bool:
    """Check if holding percentages sum to exactly 100."""
    total = (row["promoter_pct"] or 0) + (row["fii_pct"] or 0) + \
            (row["dii_mf_pct"] or 0) + (row["public_retail_pct"] or 0)
    return abs(total - 100.0) < 0.01


def _is_legitimate_batch(updated_at: str) -> bool:
    """Check if the row belongs to the known legitimate bulk NSE API batch."""
    if not updated_at:
        return False
    return updated_at.startswith(LEGITIMATE_BATCH_PREFIX)


def _has_fii_dii_split_signature(row: Any) -> bool:
    """Check the 0.45/0.55 split ratio signature, but NOT for the legitimate batch."""
    if _is_legitimate_batch(row["updated_at"] or ""):
        return False
    fii = row["fii_pct"] or 0
    dii = row["dii_mf_pct"] or 0
    if fii <= 0 or dii <= 0:
        return False
    ratio = fii / max(dii, 0.01)
    return FII_DII_RATIO_LOW <= ratio <= FII_DII_RATIO_HIGH


def _is_pre_cutoff(updated_at: str) -> bool:
    """Check if updated_at is before the cutoff date."""
    if not updated_at:
        return True
    return updated_at < PRE_CUTOFF


def classify_row(row: Any) -> list[str]:
    """Return a list of reasons why a row is flagged as synthetic."""
    reasons: list[str] = []
    ticker = row["ticker"]
    updated_at = row["updated_at"] or ""

    if _is_test_ticker(ticker):
        reasons.append("test_ticker")

    if _has_sum_to_100(row) and not _is_legitimate_batch(updated_at):
        reasons.append("sum_100_not_legit_batch")

    if _has_fii_dii_split_signature(row):
        reasons.append("fii_dii_split_signature")

    if _is_pre_cutoff(updated_at):
        reasons.append("pre_cutoff_seed")

    return reasons


def yfinance_cross_check(ticker: str, row: Any) -> tuple[list[str], str | None]:
    """Cross-check a row against yfinance data with retry.

    Returns:
        (extra_reasons, verification_status)
        verification_status is one of:
          "confirmed_synthetic" — yfinance contradicts the data
          "confirmed_real"      — yfinance matches within tolerance
          "yfinance_failed"     — all retries exhausted / no data
          "test_ticker"         — known placeholder name
    """
    reasons: list[str] = []
    last_exc: Exception | None = None

    # Test tickers are always synthetic — skip network call
    if _is_test_ticker(ticker):
        reasons.append("test_ticker")
        return reasons, "test_ticker"

    for attempt in range(YF_RETRIES):
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info or {}

            insiders = info.get("heldPercentInsiders")  # should approximate promoter_pct
            institutions = info.get("heldPercentInstitutions")  # should approximate fii+dii

            promoter = row["promoter_pct"] or 0
            fii = row["fii_pct"] or 0

            # Check: promoter differs from yfinance insiders by >25pp
            if insiders is not None and insiders != 0 and abs(promoter - insiders * 100) > YF_INSIDER_TOLERANCE:
                reasons.append(f"yf_insider_mismatch(promoter={promoter:.1f}, yf_insiders={insiders * 100:.1f})")

            # Check: fii_pct > 0 but yfinance shows 0 institutions
            if fii > 0 and institutions is not None and institutions == 0:
                reasons.append(f"yf_zero_institutions_but_fii={fii:.1f}")

            # Determine verification status
            if reasons:
                return reasons, "confirmed_synthetic"

            # yfinance data present and matches within tolerance — this is real data
            if insiders is not None and institutions is not None:
                return reasons, "confirmed_real"

            # yfinance returned but insiders/institutions are None — can't verify
            if info:
                return reasons, None  # partial data, keep flagged from heuristic

            # Empty ticker (e.g., delisted)
            return reasons, "confirmed_real"  # no info to contradict, trust heuristic

        except ImportError:
            logger.warning("yfinance not installed — skipping cross-check for %s", ticker)
            return reasons, "yfinance_failed"

        except Exception as exc:
            last_exc = exc
            delay = YF_RETRY_DELAY * (2 ** attempt)  # exponential backoff
            logger.warning(
                "yfinance attempt %d/%d failed for %s: %s — retrying in %.1fs",
                attempt + 1, YF_RETRIES, ticker, exc, delay
            )
            time.sleep(delay)

    # All retries exhausted
    logger.error("yfinance cross-check permanently failed for %s after %d attempts: %s",
                 ticker, YF_RETRIES, last_exc)
    return reasons, "yfinance_failed"


def run_yfinance_checks(flagged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run yfinance cross-checks on ALL flagged rows in parallel with retries.

    Removes rows from the flagged list if yfinance confirms they are real data.
    """
    if not flagged:
        return flagged

    logger.info("Running yfinance cross-check on %d rows with %d parallel threads...",
                len(flagged), YF_WORKERS)

    confirmed_real: list[dict[str, Any]] = []
    confirmed_synthetic: list[dict[str, Any]] = []
    yf_failed: list[dict[str, Any]] = []
    errors: int = 0

    with ThreadPoolExecutor(max_workers=YF_WORKERS) as pool:
        futures = {
            pool.submit(yfinance_cross_check, row["ticker"], row): row
            for row in flagged
        }

        for future in as_completed(futures):
            row = futures[future]
            ticker = row["ticker"]
            try:
                extra, status = future.result()
                if extra:
                    row["reasons"].extend(extra)
                    logger.debug("  [yfinance] %s — extra reasons: %s", ticker, extra)

                if status == "confirmed_real":
                    confirmed_real.append(row)
                    logger.info("  [yfinance] %s — VERIFIED REAL, removing from delete list", ticker)
                elif status == "confirmed_synthetic":
                    confirmed_synthetic.append(row)
                elif status == "yfinance_failed":
                    yf_failed.append(row)
            except Exception as exc:
                errors += 1
                logger.error("  [yfinance] %s — unexpected exception in future: %s", ticker, exc)

            # Small stagger per thread to avoid hammering yfinance
            time.sleep(YFINANCE_SLEEP)

    logger.info(
        "yfinance cross-check complete: %d confirmed_real, %d confirmed_synthetic, "
        "%d yf_failed, %d errors",
        len(confirmed_real), len(confirmed_synthetic),
        len(yf_failed), errors
    )

    # Remove yfinance-confirmed-real rows from the flagged delete list
    verified_real_tickers = {r["ticker"] for r in confirmed_real}
    filtered = [row for row in flagged if row["ticker"] not in verified_real_tickers]

    if confirmed_real:
        logger.info(
            "yfinance verified %d row(s) as real — removed from delete list: %s",
            len(confirmed_real),
            sorted(verified_real_tickers)
        )

    return filtered


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def find_suspicious_rows(conn: Any) -> list[dict[str, Any]]:
    """Query shareholding_patterns and return all rows flagged by heuristics."""
    cur = conn.execute(
        "SELECT ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, "
        "public_retail_pct, other_pct, updated_at "
        "FROM shareholding_patterns ORDER BY ticker, quarter"
    )
    columns = [d[0] for d in cur.description]
    rows = [dict(zip(columns, r)) for r in cur.fetchall()]

    flagged: list[dict[str, Any]] = []
    for row in rows:
        reasons = classify_row(row)
        if reasons:
            row["reasons"] = reasons
            flagged.append(row)

    return flagged


def _extract_date(updated_at: str | None) -> str:
    """Extract YYYY-MM-DD (or date-time prefix) from updated_at."""
    if not updated_at:
        return "unknown"
    return updated_at[:10]


def print_summary_table(flagged: list[dict[str, Any]]) -> None:
    """Print a formatted summary table of all flagged rows, grouped by date."""
    if not flagged:
        print("\n  No suspicious rows found. Database is clean.\n")
        return

    # Group by date
    from collections import defaultdict
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in flagged:
        by_date[_extract_date(row["updated_at"])].append(row)

    row_line = (
        f"  {'Ticker':<18} {'Quarter':<14} {'Prom%':>7} {'FII%':>7} "
        f"{'DII%':>7} {'Pub%':>7} {'Updated At':<22} {'Reasons'}"
    )
    sep = "-" * len(row_line)

    print()

    for date_key in sorted(by_date.keys()):
        group = by_date[date_key]
        print(f"  === {date_key}  ({len(group)} rows) ===")
        print(f"  {sep}")
        print(f"  {row_line}")
        print(f"  {sep}")

        for row in group:
            print(
                f"  {row['ticker']:<18} {row['quarter']:<14} "
                f"{row['promoter_pct']:>7.1f} {row['fii_pct']:>7.1f} "
                f"{row['dii_mf_pct']:>7.1f} {row['public_retail_pct']:>7.1f} "
                f"{(row['updated_at'] or 'N/A'):<22} {', '.join(row['reasons'])}"
            )

        print(f"  {sep}")
        print()

    print(f"  Grand total flagged: {len(flagged)} rows across {len(by_date)} date group(s)\n")


def delete_flagged(conn: Any, flagged: list[dict[str, Any]]) -> dict[str, int]:
    """Delete flagged rows from shareholding_patterns and
    institutional_accumulation_cache. Returns deletion counts."""
    stats = {"shareholding_patterns_deleted": 0, "accumulation_cache_deleted": 0}

    # Collect unique tickers that need cache cleanup
    affected_tickers: set[str] = set()

    for row in flagged:
        ticker = row["ticker"]
        quarter = row["quarter"]

        try:
            cur = conn.execute(
                "DELETE FROM shareholding_patterns WHERE ticker = ? AND quarter = ?",
                (ticker, quarter),
            )
            stats["shareholding_patterns_deleted"] += cur.rowcount
            affected_tickers.add(ticker)
        except Exception as exc:
            logger.error("Failed to delete shareholding_patterns row %s/%s: %s", ticker, quarter, exc)

    # Delete institutional_accumulation_cache for affected tickers
    for ticker in affected_tickers:
        try:
            cur = conn.execute(
                "DELETE FROM institutional_accumulation_cache WHERE ticker = ?",
                (ticker,),
            )
            stats["accumulation_cache_deleted"] += cur.rowcount
        except Exception as exc:
            logger.error("Failed to delete accumulation_cache for %s: %s", ticker, exc)

    conn.commit()
    return stats


def print_final_stats(conn: Any, delete_stats: dict[str, int], flagged: list[dict[str, Any]]) -> None:
    """Print post-deletion statistics."""
    try:
        shp_total = conn.execute("SELECT COUNT(*) FROM shareholding_patterns").fetchone()[0]
    except Exception:
        shp_total = "N/A"
    try:
        acc_total = conn.execute("SELECT COUNT(*) FROM institutional_accumulation_cache").fetchone()[0]
    except Exception:
        acc_total = "N/A"

    print("=" * 60)
    print("  CLEANUP SUMMARY")
    print("=" * 60)
    print(f"  Rows flagged for deletion:                {len(flagged)}")
    print(f"  shareholding_patterns rows deleted:       {delete_stats['shareholding_patterns_deleted']}")
    print(f"  institutional_accumulation_cache deleted: {delete_stats['accumulation_cache_deleted']}")
    print(f"  shareholding_patterns rows remaining:     {shp_total}")
    print(f"  institutional_accumulation_cache remaining: {acc_total}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identify and optionally delete synthetic shareholding rows.",
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Actually delete flagged rows (default is dry-run).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Only report, do not delete (this is the default).",
    )
    parser.add_argument(
        "--verbose", action="store_true", default=False,
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    # If --apply is passed, override dry-run
    dry_run = not args.apply

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 60)
    if dry_run:
        print("  MODE: DRY RUN (no rows will be deleted)")
    else:
        print("  MODE: APPLY (flagged rows WILL be deleted)")
    print("=" * 60)

    conn = get_db_connection()
    try:
        # 1. Find suspicious rows by pattern matching
        flagged = find_suspicious_rows(conn)
        logger.info("Found %d suspicious rows by heuristic matching.", len(flagged))

        # 2. Cross-check against yfinance
        if flagged:
            flagged = run_yfinance_checks(flagged)

            # Remove rows from flagged list if yfinance cross-check added no
            # reasons AND the only heuristic was pre_cutoff_seed — these are
            # borderline; keep them flagged (the heuristic alone is sufficient).

        # 3. Print summary table
        print_summary_table(flagged)

        # 4. Delete if not dry-run
        if dry_run:
            print("  Run with --apply to delete these rows.\n")
        else:
            if flagged:
                delete_stats = delete_flagged(conn, flagged)
                print_final_stats(conn, delete_stats, flagged)
            else:
                print("  Nothing to delete.\n")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
