"""Historical News Catalyst Outcome Verification and Trade Performance Analytics.

Evaluates post-event forward returns (1D, 3D, 5D, max gain, max drawdown) for
ingested financial news & catalysts against historical daily price candles,
verifies whether the predicted directional outcome succeeded, and calculates
quantitative trade-readiness KPIs (Win Rate, Profit Factor, Expectancy, Max Gainers).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled
from earnings_engine.data import prices as prices_mod

logger = logging.getLogger("earnings_engine.data.news_outcomes")

def _ensure_outcomes_table(conn: Any) -> None:
    """Create news_catalyst_outcomes table and indices if they do not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_catalyst_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalyst_id INTEGER,
            ticker TEXT NOT NULL,
            stock_name TEXT,
            title TEXT NOT NULL,
            publisher TEXT,
            published_at TEXT NOT NULL,
            category TEXT NOT NULL,
            direction TEXT NOT NULL,
            impact_score INTEGER NOT NULL,
            impact_level TEXT NOT NULL,
            entry_date TEXT,
            entry_price REAL,
            price_1d REAL,
            return_1d_pct REAL,
            price_3d REAL,
            return_3d_pct REAL,
            price_5d REAL,
            return_5d_pct REAL,
            max_high_price REAL,
            max_gain_pct REAL,
            max_low_price REAL,
            max_drawdown_pct REAL,
            exit_price REAL,
            net_return_pct REAL,
            predicted_met INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            why_it_matters TEXT,
            verified_at TEXT NOT NULL,
            UNIQUE(catalyst_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON news_catalyst_outcomes(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_status ON news_catalyst_outcomes(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_category ON news_catalyst_outcomes(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_pub_at ON news_catalyst_outcomes(published_at)")
    conn.commit()
    _TABLE_CREATED = True


from earnings_engine.data.catalysts_news import _connect as _connect_catalysts

def _connect(settings: Settings) -> Any:
    settings.ensure_dirs()
    conn = _connect_catalysts(settings)
    _ensure_outcomes_table(conn)
    return conn


def evaluate_all_catalyst_outcomes(
    settings: Settings | None = None,
    force: bool = False,
    min_days_history: int = 1,
) -> dict[str, Any]:
    """Scan all news_catalysts, fetch forward price action, compute returns, and verify trade outcomes.

    Returns:
        Summary dict containing evaluated count, verified count, and elapsed time.
    """
    import time
    t0 = time.perf_counter()
    settings = settings or Settings()

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        # Fetch all catalysts
        query = "SELECT * FROM news_catalysts ORDER BY published_at ASC"
        catalysts = [dict(r) for r in conn.execute(query).fetchall()]

        if not catalysts:
            return {
                "total_catalysts": 0,
                "evaluated": 0,
                "verified": 0,
                "active": 0,
                "elapsed_seconds": 0.0,
            }

        # Batch load/fetch price histories using parallel price loader
        price_map = prices_mod.ensure_prices_batch(tickers, settings, max_workers=10)

        now_str = datetime.now(timezone.utc).isoformat()
        evaluated_count = 0
        verified_count = 0
        active_count = 0

        for cat in catalysts:
            cat_id = cat["id"]
            ticker = cat["ticker"]
            published_at = cat["published_at"]
            direction = (cat.get("direction") or "BULLISH").upper()
            impact_score = int(cat.get("impact_score") or 50)
            impact_level = cat.get("impact_level") or "MEDIUM"
            category = cat.get("category") or "Uncategorized"

            # Parse publish date
            try:
                # Handle standard ISO strings or substring YYYY-MM-DD
                pub_date_str = published_at[:10]
                pub_dt = pd.to_datetime(pub_date_str)
            except Exception:
                continue

            df_p = price_map.get(ticker)
            if df_p is None or df_p.empty or "close" not in df_p.columns:
                continue

            # Ensure date column exists (reset index if date is index)
            if "date" not in df_p.columns:
                df_p = df_p.reset_index()

            if "date" not in df_p.columns:
                continue

            # Ensure date column is datetime
            if not pd.api.types.is_datetime64_any_dtype(df_p["date"]):
                df_p = df_p.copy()
                df_p["date"] = pd.to_datetime(df_p["date"])

            df_sorted = df_p.sort_values("date").reset_index(drop=True)

            # Find candles on or after publish date
            forward_candles = df_sorted[df_sorted["date"] >= pub_dt]
            if forward_candles.empty:
                # If no candle on or after publish date, use latest available candle for entry
                continue

            # Entry candle (Day 0)
            entry_row = forward_candles.iloc[0]
            entry_date = entry_row["date"].strftime("%Y-%m-%d")
            entry_price = float(entry_row.get("open") if "open" in entry_row and not pd.isna(entry_row["open"]) else entry_row["close"])
            if entry_price <= 0:
                continue

            # Subsequent forward candles (excluding entry day for forward horizon)
            post_candles = forward_candles.iloc[1:6]  # Up to next 5 trading days

            price_1d = None
            return_1d_pct = None
            price_3d = None
            return_3d_pct = None
            price_5d = None
            return_5d_pct = None

            if len(post_candles) >= 1:
                price_1d = float(post_candles.iloc[0]["close"])
                return_1d_pct = round(((price_1d - entry_price) / entry_price) * 100.0, 2)

            if len(post_candles) >= 3:
                price_3d = float(post_candles.iloc[2]["close"])
                return_3d_pct = round(((price_3d - entry_price) / entry_price) * 100.0, 2)
            elif len(post_candles) > 0:
                price_3d = float(post_candles.iloc[-1]["close"])
                return_3d_pct = round(((price_3d - entry_price) / entry_price) * 100.0, 2)

            if len(post_candles) >= 5:
                price_5d = float(post_candles.iloc[4]["close"])
                return_5d_pct = round(((price_5d - entry_price) / entry_price) * 100.0, 2)
            elif len(post_candles) > 0:
                price_5d = float(post_candles.iloc[-1]["close"])
                return_5d_pct = round(((price_5d - entry_price) / entry_price) * 100.0, 2)

            # Highs and Lows excursion in forward window
            eval_window = forward_candles.iloc[0:6]  # Day 0 to Day 5
            max_high = float(eval_window["high"].max()) if "high" in eval_window.columns else float(eval_window["close"].max())
            min_low = float(eval_window["low"].min()) if "low" in eval_window.columns else float(eval_window["close"].min())

            max_gain_pct = round(((max_high - entry_price) / entry_price) * 100.0, 2)
            max_drawdown_pct = round(((min_low - entry_price) / entry_price) * 100.0, 2)

            # Exit / net return (always anchored to latest market price if still active)
            latest_close = float(df_sorted.iloc[-1]["close"]) if not df_sorted.empty and "close" in df_sorted.columns else entry_price
            exit_price = price_5d if price_5d is not None else latest_close
            net_return_pct = round(((exit_price - entry_price) / entry_price) * 100.0, 2)

            # Outcome verification logic
            # Bullish success: Peak move >= +2.0% OR 3D/5D net return > 0%
            # Bearish success: Max drop <= -2.0% OR 3D/5D net return < 0%
            if direction == "BULLISH":
                predicted_met = 1 if (max_gain_pct >= 2.0 or net_return_pct > 0.0) else 0
            elif direction == "BEARISH":
                predicted_met = 1 if (max_drawdown_pct <= -2.0 or net_return_pct < 0.0) else 0
            else:
                predicted_met = 1 if abs(net_return_pct) < 3.0 else 0

            status = "VERIFIED" if len(post_candles) >= 3 else "ACTIVE"

            if status == "VERIFIED":
                verified_count += 1
            else:
                active_count += 1

            evaluated_count += 1

            conn.execute(
                """
                INSERT OR REPLACE INTO news_catalyst_outcomes (
                    catalyst_id, ticker, stock_name, title, publisher, published_at,
                    category, direction, impact_score, impact_level, entry_date,
                    entry_price, price_1d, return_1d_pct, price_3d, return_3d_pct,
                    price_5d, return_5d_pct, max_high_price, max_gain_pct,
                    max_low_price, max_drawdown_pct, exit_price, net_return_pct,
                    predicted_met, status, why_it_matters, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cat_id, ticker, cat.get("stock_name"), cat["title"], cat.get("publisher"),
                    published_at, category, direction, impact_score, impact_level,
                    entry_date, entry_price, price_1d, return_1d_pct, price_3d, return_3d_pct,
                    price_5d, return_5d_pct, max_high, max_gain_pct, min_low, max_drawdown_pct,
                    exit_price, net_return_pct, predicted_met, status, cat.get("why_it_matters"),
                    now_str,
                )
            )

        conn.commit()

    elapsed = time.perf_counter() - t0
    logger.info(
        "[NEWS-OUTCOMES] Evaluated %d catalysts in %.2fs (%d verified, %d active)",
        evaluated_count, elapsed, verified_count, active_count
    )

    return {
        "total_catalysts": len(catalysts),
        "evaluated": evaluated_count,
        "verified": verified_count,
        "active": active_count,
        "elapsed_seconds": round(elapsed, 2),
    }


def get_verified_catalyst_outcomes(
    category: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    predicted_met: bool | None = None,
    sort_by: str = "published_at",
    limit: int = 50,
    search_query: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Query evaluated news outcomes with rich filtering and sorting."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        _ensure_outcomes_table(conn)
        conn.row_factory = sqlite3.Row

        # If table is empty, trigger initial evaluation
        count = conn.execute("SELECT COUNT(*) FROM news_catalyst_outcomes").fetchone()[0]
        if count == 0:
            try:
                evaluate_all_catalyst_outcomes(settings=settings)
            except Exception as e:
                logger.debug("[NEWS-OUTCOMES] Initial evaluation error: %s", e)

        query = "SELECT * FROM news_catalyst_outcomes WHERE 1=1"
        params: list[Any] = []

        if category and category.upper() != "ALL":
            query += " AND category = ?"
            params.append(category)

        if direction and direction.upper() != "ALL":
            query += " AND direction = ?"
            params.append(direction.upper())

        if status and status.upper() != "ALL":
            query += " AND status = ?"
            params.append(status.upper())

        if predicted_met is not None:
            query += " AND predicted_met = ?"
            params.append(1 if predicted_met else 0)

        if search_query:
            sq = f"%{search_query.strip().lower()}%"
            query += " AND (LOWER(title) LIKE ? OR LOWER(ticker) LIKE ? OR LOWER(stock_name) LIKE ?)"
            params.extend([sq, sq, sq])

        order_clause = "published_at DESC"
        if sort_by == "max_gain":
            order_clause = "max_gain_pct DESC"
        elif sort_by == "net_return":
            order_clause = "net_return_pct DESC"
        elif sort_by == "impact":
            order_clause = "impact_score DESC, published_at DESC"
        elif sort_by == "drawdown":
            order_clause = "max_drawdown_pct ASC"

        query += f" ORDER BY {order_clause} LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def compute_news_trade_metrics(
    settings: Settings | None = None,
    category: str | None = None,
    min_impact: int = 0,
) -> dict[str, Any]:
    """Compute institutional quantitative backtest and trade-readiness KPIs across news catalysts.

    Calculates:
    - Overall Win Rate (%) & Directional Win Rates
    - Profit Factor & Payoff Ratio
    - Trade Expectancy (%)
    - Max Gainer catalysts
    - Category Alpha performance breakdown
    - Horizon returns decay (1D, 3D, 5D)
    """
    settings = settings or Settings()
    with _connect(settings) as conn:
        _ensure_outcomes_table(conn)
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM news_catalyst_outcomes WHERE entry_price IS NOT NULL AND entry_price > 0"
        params: list[Any] = []

        if category and category.upper() != "ALL":
            query += " AND category = ?"
            params.append(category)

        if min_impact > 0:
            query += " AND impact_score >= ?"
            params.append(min_impact)

        rows = conn.execute(query, params).fetchall()
        if not rows:
            return {
                "total_evaluated": 0,
                "verified_count": 0,
                "win_rate_pct": 0.0,
                "bullish_win_rate_pct": 0.0,
                "bearish_win_rate_pct": 0.0,
                "avg_return_pct": 0.0,
                "avg_max_gain_pct": 0.0,
                "avg_max_drawdown_pct": 0.0,
                "profit_factor": 0.0,
                "payoff_ratio": 0.0,
                "trade_expectancy_pct": 0.0,
                "max_gainers": [],
                "category_performance": [],
                "horizon_performance": {
                    "avg_1d_pct": 0.0,
                    "avg_3d_pct": 0.0,
                    "avg_5d_pct": 0.0,
                },
            }

        df = pd.DataFrame([dict(r) for r in rows])

        total = len(df)
        verified_df = df[df["status"] == "VERIFIED"]
        eval_set = verified_df if not verified_df.empty else df

        met_count = int(eval_set["predicted_met"].sum())
        win_rate = round((met_count / len(eval_set)) * 100.0, 1) if len(eval_set) > 0 else 0.0

        bull_df = eval_set[eval_set["direction"] == "BULLISH"]
        bull_win_rate = round((bull_df["predicted_met"].sum() / len(bull_df)) * 100.0, 1) if len(bull_df) > 0 else 0.0

        bear_df = eval_set[eval_set["direction"] == "BEARISH"]
        bear_win_rate = round((bear_df["predicted_met"].sum() / len(bear_df)) * 100.0, 1) if len(bear_df) > 0 else 0.0

        # Directional strategy returns analytics (long for bullish, short for bearish)
        eval_set = eval_set.copy()
        eval_set["trade_return_pct"] = eval_set.apply(
            lambda r: -float(r["net_return_pct"]) if str(r.get("direction", "")).upper() == "BEARISH" and r["net_return_pct"] is not None else float(r["net_return_pct"] or 0.0),
            axis=1,
        )

        returns = eval_set["trade_return_pct"].dropna()
        avg_ret = round(float(returns.mean()), 2) if not returns.empty else 0.0
        avg_max_gain = round(float(eval_set["max_gain_pct"].dropna().mean()), 2) if not eval_set["max_gain_pct"].empty else 0.0
        avg_max_dd = round(float(eval_set["max_drawdown_pct"].dropna().mean()), 2) if not eval_set["max_drawdown_pct"].empty else 0.0

        # Profit Factor & Expectancy
        gains = returns[returns > 0]
        losses = returns[returns < 0]
        sum_gains = float(gains.sum()) if not gains.empty else 0.0
        sum_losses = abs(float(losses.sum())) if not losses.empty else 0.0

        profit_factor = round(sum_gains / sum_losses, 2) if sum_losses > 0 else (round(sum_gains, 2) if sum_gains > 0 else 1.0)
        avg_win = float(gains.mean()) if not gains.empty else 0.0
        avg_loss = abs(float(losses.mean())) if not losses.empty else 0.0
        payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

        p_win = (len(gains) / len(returns)) if len(returns) > 0 else 0.0
        p_loss = (len(losses) / len(returns)) if len(returns) > 0 else 0.0
        expectancy = round((p_win * avg_win) - (p_loss * avg_loss), 2)

        # Top Max Gainers
        top_gainers_df = df.sort_values("max_gain_pct", ascending=False).head(10)
        max_gainers = [
            {
                "ticker": r["ticker"],
                "stock_name": r.get("stock_name") or r["ticker"],
                "title": r["title"],
                "published_at": r["published_at"][:10],
                "category": r["category"],
                "entry_price": r["entry_price"],
                "max_high_price": r["max_high_price"],
                "max_gain_pct": r["max_gain_pct"],
                "net_return_pct": r["net_return_pct"],
                "predicted_met": bool(r["predicted_met"]),
                "status": r["status"],
            }
            for _, r in top_gainers_df.iterrows()
        ]

        # Category Performance Breakdown
        cat_perf: list[dict[str, Any]] = []
        for cat_name, grp in df.groupby("category"):
            c_tot = len(grp)
            c_met = int(grp["predicted_met"].sum())
            c_win_rate = round((c_met / c_tot) * 100.0, 1)
            grp_strat = grp.apply(
                lambda r: -float(r["net_return_pct"]) if str(r.get("direction", "")).upper() == "BEARISH" and r["net_return_pct"] is not None else float(r["net_return_pct"] or 0.0),
                axis=1,
            )
            c_ret = round(float(grp_strat.mean()), 2) if not grp_strat.empty else 0.0
            c_gain = round(float(grp["max_gain_pct"].mean()), 2) if not grp["max_gain_pct"].empty else 0.0
            c_gains = grp_strat[grp_strat > 0].sum()
            c_losses = abs(grp_strat[grp_strat < 0].sum())
            c_pf = round(float(c_gains / c_losses), 2) if c_losses > 0 else (round(float(c_gains), 2) if c_gains > 0 else 1.0)

            cat_perf.append({
                "category": cat_name,
                "total_events": c_tot,
                "win_rate_pct": c_win_rate,
                "avg_return_pct": c_ret,
                "avg_max_gain_pct": c_gain,
                "profit_factor": c_pf,
            })

        cat_perf.sort(key=lambda x: (x["win_rate_pct"], x["avg_max_gain_pct"]), reverse=True)

        # Horizon Breakdown
        avg_1d = round(float(df["return_1d_pct"].dropna().mean()), 2) if not df["return_1d_pct"].dropna().empty else 0.0
        avg_3d = round(float(df["return_3d_pct"].dropna().mean()), 2) if not df["return_3d_pct"].dropna().empty else 0.0
        avg_5d = round(float(df["return_5d_pct"].dropna().mean()), 2) if not df["return_5d_pct"].dropna().empty else 0.0

        return {
            "total_evaluated": total,
            "verified_count": len(verified_df),
            "win_rate_pct": win_rate,
            "bullish_win_rate_pct": bull_win_rate,
            "bearish_win_rate_pct": bear_win_rate,
            "avg_return_pct": avg_ret,
            "avg_max_gain_pct": avg_max_gain,
            "avg_max_drawdown_pct": avg_max_dd,
            "profit_factor": profit_factor,
            "payoff_ratio": payoff_ratio,
            "trade_expectancy_pct": expectancy,
            "max_gainers": max_gainers,
            "category_performance": cat_perf,
            "horizon_performance": {
                "avg_1d_pct": avg_1d,
                "avg_3d_pct": avg_3d,
                "avg_5d_pct": avg_5d,
            },
        }
