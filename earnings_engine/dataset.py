"""Event dataset builder: one row per ticker x past earnings event.

Each row contains identifiers, point-in-time features (price/volume as of the
last trading day before the announcement, plus earnings-history features from
strictly earlier events), and the realized 1-day reaction label.

Output: data/cache/prices/prices.sqlite3 (event_dataset table)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from earnings_engine.config import CACHE_DIR, Settings, market_of
from earnings_engine.data.earnings import load_earnings
from earnings_engine.data.prices import _cache_path as _prices_cache_path, load_prices
from earnings_engine.features.earnings_features import EARNINGS_FEATURES, compute_earnings_features
from earnings_engine.features.price_features import PRICE_FEATURES, compute_price_features
from earnings_engine.labels import compute_reaction
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.dataset")

DATASET_PATH = CACHE_DIR / "dataset.parquet"  # Legacy path, kept for migration

ID_COLUMNS = ["ticker", "market", "earnings_date", "asof_date", "reaction_date"]
LABEL_COLUMNS = ["reaction_return", "label"]
FEATURE_COLUMNS = PRICE_FEATURES + EARNINGS_FEATURES + ["is_in_market"]
ALL_COLUMNS = ID_COLUMNS + FEATURE_COLUMNS + LABEL_COLUMNS


def _db_path(settings: Settings | None = None) -> Path:
    """Use the same SQLite database as prices."""
    if settings is None:
        from earnings_engine.config import Settings as S
        settings = S()
    return _prices_cache_path(settings)


def _connect(settings: Settings | None = None) -> sqlite3.Connection:
    """Connect to the shared SQLite database and create the dataset table if missing."""
    if settings is None:
        from earnings_engine.config import Settings as S
        settings = S()
    settings.ensure_dirs()
    connection = sqlite3.connect(_db_path(settings))
    # Create table with all columns as TEXT/REAL
    col_defs = []
    for col in ID_COLUMNS:
        col_defs.append(f"{col} TEXT")
    for col in FEATURE_COLUMNS:
        col_defs.append(f"{col} REAL")
    for col in LABEL_COLUMNS:
        col_defs.append(f"{col} REAL")
    col_defs_sql = ", ".join(col_defs)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS event_dataset (
            {col_defs_sql},
            PRIMARY KEY (ticker, earnings_date)
        )
        """
    )
    connection.commit()
    return connection


def _write_dataset(df: pd.DataFrame, settings: Settings | None = None) -> None:
    """Write dataset to SQLite, replacing all existing rows."""
    if df.empty:
        return
    if settings is None:
        from earnings_engine.config import Settings as S
        settings = S()
    with _connect(settings) as connection:
        connection.execute("DELETE FROM event_dataset")
        # Convert all columns to strings/floats for SQLite
        rows = []
        for _, row in df.iterrows():
            row_data = []
            for col in ALL_COLUMNS:
                val = row.get(col)
                if pd.isna(val):
                    row_data.append(None)
                elif col in ("earnings_date", "asof_date", "reaction_date"):
                    row_data.append(pd.Timestamp(val).strftime("%Y-%m-%d"))
                elif col in ("ticker", "market"):
                    row_data.append(str(val))
                else:
                    row_data.append(float(val))
            rows.append(tuple(row_data))
        placeholders = ", ".join(["?"] * len(ALL_COLUMNS))
        col_names = ", ".join(ALL_COLUMNS)
        connection.executemany(
            f"INSERT INTO event_dataset ({col_names}) VALUES ({placeholders})",
            rows,
        )
        connection.commit()


def _migrate_from_parquet(settings: Settings | None = None) -> None:
    """Migrate dataset from old Parquet cache to SQLite if it exists."""
    if settings is None:
        from earnings_engine.config import Settings as S
        settings = S()
    if not DATASET_PATH.exists():
        return
    try:
        df = pd.read_parquet(DATASET_PATH)
        if not df.empty:
            _write_dataset(df, settings)
            logger.info("migrated dataset from parquet rows=%s", len(df))
        DATASET_PATH.unlink()
    except Exception as e:
        logger.warning("dataset parquet migration failed error=%s", e)


def build_ticker_events(ticker: str, settings: Settings) -> pd.DataFrame:
    """Build event rows for one ticker from cached data (no network)."""
    prices = load_prices(ticker, settings)
    earnings = load_earnings(ticker, settings)
    if prices.empty or earnings.empty:
        logger.info("dataset build skipped ticker=%s reason=missing-data", ticker)
        return pd.DataFrame()

    today = pd.Timestamp.today().normalize()
    rows: list[dict] = []
    for _, ev in earnings.iterrows():
        edate = ev["earnings_date"]
        if edate >= today:
            continue  # upcoming events have no label; handled in Phase 5
        reaction = compute_reaction(prices, edate)
        if reaction is None:
            continue
        pf = compute_price_features(prices, reaction.asof_date)
        if pf is None:
            continue
        past = pd.DataFrame(rows)  # earlier events only — rows is chronological
        ef = compute_earnings_features(past if not past.empty else pd.DataFrame(columns=["reaction_return"]),
                                       earnings, edate)
        rows.append({
            "ticker": ticker,
            "market": market_of(ticker),
            "earnings_date": edate,
            "asof_date": reaction.asof_date,
            "reaction_date": reaction.reaction_date,
            **pf,
            **ef,
            "is_in_market": int(market_of(ticker) == "IN"),
            "reaction_return": reaction.reaction_return,
            "label": reaction.label,
        })
    logger.info("dataset built ticker=%s rows=%s", ticker, len(rows))
    return pd.DataFrame(rows)


def build_dataset(tickers: list[str], settings: Settings, save: bool = True) -> pd.DataFrame:
    """Build the full event dataset across tickers and optionally save it."""
    # Migrate from old Parquet cache if it exists
    _migrate_from_parquet(settings)

    frames = [df for t in tickers if not (df := build_ticker_events(t, settings)).empty]
    if not frames:
        return pd.DataFrame()
    dataset = pd.concat(frames, ignore_index=True)
    dataset = dataset.sort_values(["earnings_date", "ticker"]).reset_index(drop=True)
    if save:
        _write_dataset(dataset, settings)
        logger.info("dataset saved to sqlite rows=%s", len(dataset))
    return dataset


def load_dataset() -> pd.DataFrame:
    """Load the saved event dataset from SQLite."""
    # Migrate from old Parquet cache if it exists
    _migrate_from_parquet()

    with _connect() as connection:
        rows = connection.execute(
            f"SELECT {', '.join(ALL_COLUMNS)} FROM event_dataset ORDER BY earnings_date, ticker"
        ).fetchall()

    if not rows:
        raise FileNotFoundError(
            f"No dataset in SQLite. Run `earnings-engine build-dataset` first."
        )

    df = pd.DataFrame(rows, columns=ALL_COLUMNS)
    # Convert date columns back to datetime
    for col in ("earnings_date", "asof_date", "reaction_date"):
        df[col] = pd.to_datetime(df[col])
    return df
