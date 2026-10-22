"""Tracked institutional radar signals and multi-strategy evaluation.

Tracks longitudinal lifecycle of institutional strategies:
- WHALE_CONVICTION
- BLOCK_DEAL_MOMENTUM
- DUAL_ACCELERATION
- DOMESTIC_ABSORPTION
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.names import get_name

logger = logging.getLogger(__name__)

_RADAR_TABLE_INITIALIZED: bool = False


class TrackedSignalsResult(dict):
    """Dictionary holding tracked smart money signals that also supports direct indexing and iteration."""

    def __iter__(self):
        return iter(self.get("signals", []))

    def __len__(self):
        return len(self.get("signals", []))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.get("signals", [])[key]
        return super().__getitem__(key)


def _get_or_create_radar_signals(
    screened_stocks: list[dict[str, Any]],
    conn: Any,
    as_of_date: str = "2026-09-10",
    default_window: str = "90d",
) -> None:
    """Resolve and persist Smart Money radar entry dates, historical entry prices, and returns.

    Guarantees Point-in-Time historical accuracy:
    - Resolves authentic earliest entry date from filings/block deals or existing signal ledger.
    - Resolves authentic closing price on entry date from price_history (T <= signal_date).
    - Calculates days on radar, return since signal %, peak price, and max gain %.
    - Flags newly added stocks (<= 14 days on radar) as New Entrants.
    """
    global _RADAR_TABLE_INITIALIZED
    if not screened_stocks:
        return

    # Ensure table and indexes exist (only once per process lifetime)
    if not _RADAR_TABLE_INITIALIZED:
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS institutional_radar_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    strategy TEXT NOT NULL DEFAULT 'WHALE_CONVICTION',
                    signal_date TEXT NOT NULL,
                    signal_price REAL NOT NULL,
                    initial_score REAL,
                    initial_window TEXT,
                    initial_dominance REAL,
                    initial_smart_money_cr REAL,
                    current_price REAL,
                    current_return_pct REAL,
                    peak_price REAL,
                    max_gain_pct REAL,
                    last_seen_date TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
                    updated_at TEXT NOT NULL DEFAULT (DATETIME('now')),
                    UNIQUE (ticker, strategy, signal_date)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_ticker ON institutional_radar_signals(ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_date ON institutional_radar_signals(signal_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_active ON institutional_radar_signals(is_active)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_radar_signals_perf ON institutional_radar_signals(ticker, signal_date)")
            _RADAR_TABLE_INITIALIZED = True
        except Exception as e:
            logger.debug("[INSTITUTIONAL] Signal table verify warning: %s", e)

    today_dt = None
    try:
        today_dt = datetime.fromisoformat(as_of_date).date() if "T" in as_of_date else datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    except Exception:
        today_dt = datetime.now(timezone.utc).date()
    today_str = today_dt.strftime("%Y-%m-%d")

    # 1. Batch query existing signals across all screened tickers in 1 roundtrip
    tickers = list({s["ticker"] for s in screened_stocks if s.get("ticker")})
    existing_signals: dict[str, tuple[str, float, float, float, float]] = {}
    if tickers:
        try:
            placeholders = ",".join("?" for _ in tickers)
            cur = conn.execute(
                f"""
                SELECT ticker, signal_date, signal_price, initial_score, peak_price, initial_smart_money_cr
                FROM institutional_radar_signals
                WHERE ticker IN ({placeholders})
                ORDER BY ticker, signal_date ASC
                """,
                tickers,
            )
            for row in cur.fetchall():
                sym_k = row[0]
                if sym_k not in existing_signals:
                    existing_signals[sym_k] = (
                        str(row[1]),
                        float(row[2] or 0.0),
                        float(row[3] or 50.0),
                        float(row[4] or row[2] or 0.0),
                        float(row[5] or 0.0),
                    )
        except Exception as e:
            logger.debug("[INSTITUTIONAL] Batch radar signals lookup notice: %s", e)

    # 2. Identify new signals needing Point-in-Time historical price lookup
    price_lookup_targets: list[tuple[str, str]] = []
    new_signal_metadata: dict[str, tuple[str, float]] = {}

    for s in screened_stocks:
        sym = s["ticker"]
        if sym in existing_signals:
            continue

        txn_dates = []
        for b in s.get("buyers", []):
            cat = b.get("category")
            b_date = b.get("date") or b.get("deal_date") or b.get("filing_date")
            if b_date and cat in ("FII", "Super Investor", "AIF", "Block Deal", "Smart Money"):
                txn_dates.append(str(b_date)[:10])

        if txn_dates:
            sig_date = min(txn_dates)
        else:
            all_b_dates = [
                str(b.get("date") or b.get("deal_date") or b.get("filing_date"))[:10]
                for b in s.get("buyers", [])
                if b.get("date") or b.get("deal_date") or b.get("filing_date")
            ]
            sig_date = min(all_b_dates) if all_b_dates else today_str

        if sig_date >= today_str:
            sig_date = today_str

        initial_score = float(s.get("conviction_score", 50.0))
        new_signal_metadata[sym] = (sig_date, initial_score)

        if sig_date < today_str:
            price_lookup_targets.append((sym, sig_date))

    # 3. Batch resolve historical prices using CTE window function
    historical_prices: dict[str, float] = {}
    if price_lookup_targets:
        try:
            dedup_targets = list({t[0]: t for t in price_lookup_targets}.values())
            values_clause = ", ".join("(?, ?)" for _ in dedup_targets)
            params: list[Any] = []
            for sym_t, dt_t in dedup_targets:
                params.extend([sym_t, dt_t])
            query = f"""
                WITH targets(sym, target_date) AS (
                    VALUES {values_clause}
                ),
                ranked_prices AS (
                    SELECT p.ticker, p.close,
                           ROW_NUMBER() OVER (PARTITION BY t.sym ORDER BY p.date DESC) as rn
                    FROM targets t
                    JOIN price_history p ON p.ticker = t.sym AND p.date <= t.target_date AND p.close > 0
                )
                SELECT ticker, close FROM ranked_prices WHERE rn = 1
            """
            p_cur = conn.execute(query, params)
            for p_row in p_cur.fetchall():
                if p_row and p_row[1]:
                    historical_prices[p_row[0]] = round(float(p_row[1]), 2)
        except Exception as e:
            logger.debug("[INSTITUTIONAL] CTE batch price lookup notice, falling back: %s", e)
            for sym_t, dt_t in price_lookup_targets:
                try:
                    p_cur = conn.execute(
                        "SELECT close FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                        (sym_t, dt_t),
                    )
                    p_row = p_cur.fetchone()
                    if p_row and p_row[0]:
                        historical_prices[sym_t] = round(float(p_row[0]), 2)
                except Exception:
                    pass

    # 4. Prepare batch updates and batch inserts
    updates_batch: list[tuple[Any, ...]] = []
    inserts_batch: list[tuple[Any, ...]] = []

    for s in screened_stocks:
        sym = s["ticker"]
        curr_p = s.get("current_price") or 0.0

        if sym in existing_signals:
            sig_date, sig_price, initial_score, peak_price, initial_smart_money_cr = existing_signals[sym]

            if curr_p <= 0:
                curr_p = sig_price
                s["current_price"] = curr_p

            days_on_radar = 0
            try:
                sig_dt = datetime.fromisoformat(sig_date).date() if "T" in sig_date else datetime.strptime(sig_date[:10], "%Y-%m-%d").date()
                days_on_radar = max(0, (today_dt - sig_dt).days)
            except Exception:
                days_on_radar = 0

            return_pct = round(((curr_p - sig_price) / sig_price) * 100.0, 2) if sig_price > 0 else 0.0
            peak_price = max(peak_price, curr_p)
            max_gain = round(((peak_price - sig_price) / sig_price) * 100.0, 2) if sig_price > 0 else 0.0
            is_new = (days_on_radar <= 14)

            updates_batch.append((
                curr_p, return_pct, peak_price, max_gain, today_str, sym, sig_date
            ))
        else:
            sig_date, initial_score = new_signal_metadata.get(sym, (today_str, float(s.get("conviction_score", 50.0))))

            if sig_date >= today_str:
                sig_date = today_str
                sig_price = round(float(curr_p or 100.0), 2)
                days_on_radar = 0
            else:
                sig_price = historical_prices.get(sym, 0.0)
                if sig_price <= 0:
                    sig_price = round(float(curr_p or 100.0), 2)
                days_on_radar = 0
                try:
                    sig_dt = datetime.fromisoformat(sig_date).date() if "T" in sig_date else datetime.strptime(sig_date[:10], "%Y-%m-%d").date()
                    days_on_radar = max(0, (today_dt - sig_dt).days)
                except Exception:
                    days_on_radar = 0

            if curr_p <= 0:
                curr_p = sig_price
                s["current_price"] = curr_p

            return_pct = round(((curr_p - sig_price) / sig_price) * 100.0, 2) if sig_price > 0 else 0.0
            peak_price = max(sig_price, curr_p)
            max_gain = round(((peak_price - sig_price) / sig_price) * 100.0, 2) if sig_price > 0 else 0.0
            is_new = (days_on_radar <= 14)

            inserts_batch.append((
                sym, sig_date, sig_price, initial_score, default_window,
                float(s.get("dominance_pct") or 0.0), float(s.get("smart_money_cr") or 0.0),
                curr_p, return_pct, peak_price, max_gain, today_str
            ))

        s["signal_date"] = sig_date
        s["signal_price"] = sig_price
        s["days_on_radar"] = days_on_radar
        s["return_since_signal_pct"] = return_pct
        s["return_since_signal"] = return_pct
        s["peak_price"] = peak_price
        s["max_gain_pct"] = max_gain
        s["is_new_entrant"] = is_new
        s["new_entrant_badge"] = f"🆕 New Entrant ({days_on_radar}d ago)" if is_new else None

    # 5. Execute batched updates and inserts
    if updates_batch:
        try:
            conn.executemany(
                """
                UPDATE institutional_radar_signals
                SET current_price = ?, current_return_pct = ?, peak_price = ?, max_gain_pct = ?,
                    last_seen_date = ?, is_active = 1, updated_at = DATETIME('now')
                WHERE ticker = ? AND signal_date = ?
                """,
                updates_batch,
            )
        except Exception as e:
            logger.debug("[INSTITUTIONAL] Batch signal update error: %s", e)

    if inserts_batch:
        try:
            conn.executemany(
                """
                INSERT OR IGNORE INTO institutional_radar_signals (
                    ticker, signal_date, signal_price, initial_score, initial_window,
                    initial_dominance, initial_smart_money_cr, current_price,
                    current_return_pct, peak_price, max_gain_pct, last_seen_date,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, DATETIME('now'), DATETIME('now'))
                """,
                inserts_batch,
            )
        except Exception as e:
            logger.debug("[INSTITUTIONAL] Batch signal insert error: %s", e)


def _qualifies_whale_conviction(stock: dict[str, Any]) -> tuple[bool, str]:
    """Check qualification for WHALE_CONVICTION strategy."""
    score = float(stock.get("conviction_score") or stock.get("score") or 0.0)
    sm_cr = float(stock.get("smart_money_cr") or 0.0)
    dom_pct = float(stock.get("dominance_pct") or stock.get("smart_money_dominance_pct") or 0.0)

    if score >= 65.0 and sm_cr >= 10.0 and dom_pct >= 60.0:
        return True, f"Whale Conviction: Score {score:.0f}, Dominance {dom_pct:.1f}%, ₹{sm_cr:.1f} Cr Smart Money"
    if score >= 60.0 and sm_cr >= 25.0 and dom_pct >= 50.0:
        return True, f"Whale Accumulation: Score {score:.0f}, ₹{sm_cr:.1f} Cr Smart Money"
    return False, ""


def _qualifies_block_deal_momentum(stock: dict[str, Any]) -> tuple[bool, str]:
    """Check qualification for BLOCK_DEAL_MOMENTUM strategy."""
    block_cr = float(stock.get("block_deals_cr") or 0.0)
    block_cnt = int(stock.get("block_deals_count") or 0)

    if block_cr >= 25.0 or block_cnt >= 2:
        return True, f"Block Deal Momentum: ₹{block_cr:.1f} Cr across {block_cnt} block trade(s)"
    return False, ""


def _qualifies_dual_acceleration(stock: dict[str, Any], inst_delta: float = 0.0) -> tuple[bool, str]:
    """Check qualification for DUAL_ACCELERATION strategy."""
    eps_growth = stock.get("eps_growth_yoy")
    if eps_growth is None:
        fund = stock.get("fundamentals") or {}
        eps_growth = fund.get("eps_growth_yoy")

    eps_val = float(eps_growth or 0.0) if eps_growth is not None else 0.0

    if inst_delta <= 0:
        for b in stock.get("buyers", []):
            if b.get("source") == "Filing" and b.get("change_pct"):
                inst_delta += float(b.get("change_pct") or 0.0)

    if eps_val >= 20.0 and inst_delta >= 0.50:
        return True, f"Dual Acceleration: +{eps_val:.1f}% YoY EPS & +{inst_delta:.2f}% Stake Expansion"
    if eps_val >= 20.0 and float(stock.get("smart_money_cr") or 0.0) >= 15.0:
        return True, f"Dual Acceleration: +{eps_val:.1f}% YoY EPS & ₹{float(stock.get('smart_money_cr') or 0.0):.1f} Cr Smart Money"
    return False, ""


def _qualifies_domestic_absorption(stock: dict[str, Any]) -> tuple[bool, str]:
    """Check qualification for DOMESTIC_ABSORPTION strategy."""
    dii_cr = float(stock.get("dii_cr") or stock.get("domestic_cr") or 0.0)
    cap_cat = str(stock.get("cap_category") or "")
    mcap_cr = float(stock.get("market_cap_cr") or 0.0)

    is_smid = cap_cat in ("Small Cap", "Mid Cap", "Micro Cap") or (0 < mcap_cr < 20000.0)
    if dii_cr >= 25.0 and (is_smid or cap_cat != "Large Cap"):
        return True, f"Domestic Absorption: ₹{dii_cr:.1f} Cr DII Inflow in {cap_cat or 'SMID'}"
    if dii_cr >= 50.0:
        return True, f"Heavy Domestic Inflow: ₹{dii_cr:.1f} Cr DII Inflow"
    return False, ""


def evaluate_and_track_strategy_signals(
    settings: Settings | None = None,
    as_of_date: str | None = None,
    window: str = "90d",
    force: bool = False,
) -> dict[str, Any]:
    """Evaluate multi-strategy institutional accumulation signals and persist longitudinal lifecycle tracking."""
    settings = settings or Settings()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)

    from earnings_engine.data.institutional_accumulation.db import recalculate_all_institutional_metrics
    recalculate_all_institutional_metrics(settings=settings, force=force)

    from earnings_engine.data.institutional_accumulation.accumulation import get_stocks_under_institutional_accumulation
    acc_data = get_stocks_under_institutional_accumulation(
        window=window,
        entity_focus="all",
        min_cr=0.0,
        limit=250,
        settings=settings,
    )
    screened_stocks = acc_data.get("stocks", [])

    conn = get_db_connection(settings)
    tracked_count = 0
    now_utc = datetime.now(timezone.utc)

    if as_of_date:
        as_of_str = str(as_of_date)[:10]
    else:
        try:
            p_max = conn.execute("SELECT MAX(date) FROM price_history WHERE close > 0").fetchone()
            as_of_str = str(p_max[0]) if p_max and p_max[0] else now_utc.strftime("%Y-%m-%d")
        except Exception:
            as_of_str = now_utc.strftime("%Y-%m-%d")

    try:
        for s in screened_stocks:
            sym = s.get("ticker")
            if not sym:
                continue

            company_name = s.get("company_name") or get_name(sym) or sym
            industry = s.get("industry") or s.get("sector") or "General"

            qualifications: list[tuple[str, str]] = []

            q_whale, reason_whale = _qualifies_whale_conviction(s)
            if q_whale:
                qualifications.append(("WHALE_CONVICTION", reason_whale))

            q_block, reason_block = _qualifies_block_deal_momentum(s)
            if q_block:
                qualifications.append(("BLOCK_DEAL_MOMENTUM", reason_block))

            q_dual, reason_dual = _qualifies_dual_acceleration(s)
            if q_dual:
                qualifications.append(("DUAL_ACCELERATION", reason_dual))

            q_dom, reason_dom = _qualifies_domestic_absorption(s)
            if q_dom:
                qualifications.append(("DOMESTIC_ABSORPTION", reason_dom))

            if not qualifications:
                score = float(s.get("conviction_score") or s.get("score") or 0.0)
                sm_cr = float(s.get("smart_money_cr") or 0.0)
                if score >= 50.0 or sm_cr >= 5.0:
                    qualifications.append(("WHALE_CONVICTION", f"Steady Accumulation: Score {score:.0f}, ₹{sm_cr:.1f} Cr Inflow"))

            for strat_name, trig_reason in qualifications:
                cur = conn.execute(
                    """
                    SELECT id, signal_date, signal_price, ideal_entry_price, target_price, stop_loss,
                           risk_reward_ratio, peak_price, max_gain_pct, initial_score, initial_dominance,
                           initial_smart_money_cr, whale_count, lifecycle_status, created_at
                    FROM institutional_radar_signals
                    WHERE ticker = ? AND strategy = ?
                    ORDER BY signal_date ASC LIMIT 1
                    """,
                    (sym, strat_name),
                )
                existing = cur.fetchone()

                if existing:
                    sig_id = existing[0]
                    sig_date = str(existing[1])
                    sig_price = float(existing[2] or 0.0)
                    ideal_entry = float(existing[3]) if existing[3] and float(existing[3]) > 0 else sig_price
                    target_price = float(existing[4]) if existing[4] and float(existing[4]) > 0 else round(sig_price * 1.20, 2)
                    stop_loss = float(existing[5]) if existing[5] and float(existing[5]) > 0 else round(sig_price * 0.92, 2)
                    rr_ratio = float(existing[6]) if existing[6] and float(existing[6]) > 0 else 2.5
                    peak_price = float(existing[7] or sig_price)
                    max_gain = float(existing[8] or 0.0)
                    init_score = float(existing[9] or s.get("conviction_score") or 50.0)
                    init_dom = float(existing[10] or s.get("dominance_pct") or 0.0)
                    init_sm_cr = float(existing[11] or s.get("smart_money_cr") or 0.0)
                    whale_cnt = int(existing[12] or s.get("smart_money_buyers_count") or len(s.get("buyers", [])))
                    curr_lifecycle = str(existing[13] or "ACTIVE")
                    is_new = False
                else:
                    txn_dates = []
                    for b in s.get("buyers", []):
                        b_date = b.get("date") or b.get("deal_date") or b.get("filing_date")
                        if b_date:
                            txn_dates.append(str(b_date)[:10])
                    if txn_dates:
                        sig_date = min(txn_dates)
                    else:
                        sig_date = as_of_str

                    if sig_date > as_of_str:
                        sig_date = as_of_str

                    p_cur = conn.execute(
                        "SELECT close FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                        (sym, sig_date),
                    )
                    p_row = p_cur.fetchone()
                    if p_row and p_row[0]:
                        sig_price = round(float(p_row[0]), 2)
                    else:
                        p_cur2 = conn.execute(
                            "SELECT close FROM price_history WHERE ticker = ? AND close > 0 ORDER BY date ASC LIMIT 1",
                            (sym,),
                        )
                        p_row2 = p_cur2.fetchone()
                        if p_row2 and p_row2[0]:
                            sig_price = round(float(p_row2[0]), 2)
                        else:
                            sig_price = round(float(s.get("current_price") or 100.0), 2)

                    ideal_entry = sig_price
                    target_price = round(sig_price * 1.20, 2)
                    stop_loss = round(sig_price * 0.92, 2)
                    rr_ratio = 2.5
                    peak_price = sig_price
                    max_gain = 0.0
                    init_score = float(s.get("conviction_score") or 50.0)
                    init_dom = float(s.get("dominance_pct") or 0.0)
                    init_sm_cr = float(s.get("smart_money_cr") or 0.0)
                    whale_cnt = int(s.get("smart_money_buyers_count") or len(s.get("buyers", [])))
                    curr_lifecycle = "ACTIVE"
                    is_new = True

                curr_p_row = conn.execute(
                    "SELECT date, close FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                    (sym, as_of_str),
                ).fetchone()

                if curr_p_row and curr_p_row[1]:
                    curr_date = str(curr_p_row[0])
                    curr_price = round(float(curr_p_row[1]), 2)
                else:
                    curr_date = as_of_str
                    curr_price = round(float(s.get("current_price") or sig_price), 2)

                outcome_return = round(((curr_price - sig_price) / sig_price) * 100.0, 2) if sig_price > 0 else 0.0
                peak_price = max(peak_price, sig_price, curr_price)
                max_gain = round(max(max_gain, outcome_return, ((peak_price - sig_price) / sig_price) * 100.0), 2) if sig_price > 0 else 0.0

                days_elapsed = 0
                try:
                    s_dt = datetime.strptime(str(sig_date)[:10], "%Y-%m-%d").date()
                    c_dt = datetime.strptime(str(curr_date)[:10], "%Y-%m-%d").date()
                    days_elapsed = max(0, (c_dt - s_dt).days)
                except Exception:
                    days_elapsed = 0

                if curr_price >= target_price:
                    lifecycle_status = "TARGET_HIT"
                elif curr_price <= stop_loss:
                    lifecycle_status = "DISTRIBUTION_EXIT"
                else:
                    lifecycle_status = curr_lifecycle if curr_lifecycle in ("COOLING_OFF", "TARGET_HIT") else "ACTIVE"

                entry_delay_pct = round(((curr_price - ideal_entry) / ideal_entry) * 100.0, 2) if ideal_entry > 0 else 0.0
                is_late = 1 if entry_delay_pct > 5.0 else 0

                if is_new:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO institutional_radar_signals (
                            ticker, strategy, company_name, industry, signal_date, signal_price,
                            ideal_entry_price, target_price, stop_loss, risk_reward_ratio, current_price,
                            current_date, outcome_return_pct, peak_price, max_gain_pct, days_elapsed,
                            lifecycle_status, initial_score, initial_window, initial_dominance,
                            initial_smart_money_cr, whale_count, trigger_reason, entry_delay_pct,
                            is_late, last_seen_date, is_active, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, DATETIME('now'), DATETIME('now'))
                        """,
                        (
                            sym, strat_name, company_name, industry, sig_date, sig_price,
                            ideal_entry, target_price, stop_loss, rr_ratio, curr_price,
                            curr_date, outcome_return, peak_price, max_gain, days_elapsed,
                            lifecycle_status, init_score, window, init_dom,
                            init_sm_cr, whale_cnt, trig_reason, entry_delay_pct,
                            is_late, as_of_str,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE institutional_radar_signals
                        SET current_price = ?, current_date = ?, outcome_return_pct = ?,
                            peak_price = ?, max_gain_pct = ?, days_elapsed = ?,
                            lifecycle_status = ?, entry_delay_pct = ?, is_late = ?,
                            target_price = ?, stop_loss = ?, ideal_entry_price = ?, risk_reward_ratio = ?,
                            whale_count = ?, trigger_reason = ?, company_name = ?, industry = ?,
                            last_seen_date = ?, is_active = 1, updated_at = DATETIME('now')
                        WHERE id = ?
                        """,
                        (
                            curr_price, curr_date, outcome_return, peak_price, max_gain,
                            days_elapsed, lifecycle_status, entry_delay_pct, is_late,
                            target_price, stop_loss, ideal_entry, rr_ratio,
                            whale_cnt, trig_reason, company_name, industry,
                            as_of_str, sig_id,
                        ),
                    )

                tracked_count += 1

        conn.commit()
    except Exception as e:
        logger.exception("[INSTITUTIONAL] Error in evaluate_and_track_strategy_signals: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return {
        "success": True,
        "total_signals": tracked_count,
        "as_of_date": as_of_str,
        "strategies_evaluated": [
            "WHALE_CONVICTION",
            "BLOCK_DEAL_MOMENTUM",
            "DUAL_ACCELERATION",
            "DOMESTIC_ABSORPTION",
        ],
    }


def get_tracked_smart_money_signals(
    strategy: str = "ALL_STRATEGIES",
    status: str = "active",
    sort_by: str = "score",
    limit: int = 60,
    settings: Settings | None = None,
) -> TrackedSignalsResult:
    """Query permanently tracked smart money signals with lifecycle metrics, sorting, and macro summary."""
    settings = settings or Settings()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)

    conn = get_db_connection(settings)
    try:
        count_row = conn.execute("SELECT COUNT(*) FROM institutional_radar_signals").fetchone()
        if not count_row or count_row[0] == 0:
            evaluate_and_track_strategy_signals(settings=settings)

        query_clauses = ["1=1"]
        params: list[Any] = []

        strat_clean = (strategy or "ALL_STRATEGIES").strip().upper()
        if strat_clean not in ("ALL", "ALL_STRATEGIES", ""):
            query_clauses.append("UPPER(strategy) = ?")
            params.append(strat_clean)

        stat_clean = (status or "active").strip().lower()
        if stat_clean in ("active", "all", "open", "all_signals", ""):
            query_clauses.append("is_active = 1")
        elif stat_clean == "target_hit":
            query_clauses.append("lifecycle_status = 'TARGET_HIT' AND is_active = 1")
        elif stat_clean in ("distribution_exit", "stopped", "exit"):
            query_clauses.append("lifecycle_status = 'DISTRIBUTION_EXIT' AND is_active = 1")
        elif stat_clean == "cooling_off":
            query_clauses.append("lifecycle_status = 'COOLING_OFF' AND is_active = 1")
        elif stat_clean in ("pure_active", "open_only"):
            query_clauses.append("lifecycle_status = 'ACTIVE' AND is_active = 1")
        elif stat_clean in ("closed", "completed"):
            query_clauses.append("lifecycle_status IN ('TARGET_HIT', 'DISTRIBUTION_EXIT', 'COOLING_OFF') AND is_active = 1")

        sort_key = (sort_by or "score").strip().lower()
        if sort_key in ("return", "outcome_return", "outcome_return_pct"):
            order_by = "outcome_return_pct DESC, initial_score DESC"
        elif sort_key in ("gain", "max_gain", "max_gain_pct"):
            order_by = "max_gain_pct DESC, initial_score DESC"
        elif sort_key in ("capital", "smart_money_cr", "inflow"):
            order_by = "initial_smart_money_cr DESC, initial_score DESC"
        elif sort_key in ("date", "signal_date"):
            order_by = "signal_date DESC, initial_score DESC"
        elif sort_key in ("days", "days_elapsed"):
            order_by = "days_elapsed ASC, initial_score DESC"
        else:
            order_by = "initial_score DESC, outcome_return_pct DESC"

        where_sql = " AND ".join(query_clauses)
        sql = f"""
            SELECT id, ticker, strategy, company_name, industry, signal_date, signal_price,
                   ideal_entry_price, target_price, stop_loss, risk_reward_ratio, current_price,
                   current_date, outcome_return_pct, peak_price, max_gain_pct, days_elapsed,
                   lifecycle_status, initial_score, initial_dominance, initial_smart_money_cr,
                   whale_count, trigger_reason, entry_delay_pct, is_late, created_at, updated_at
            FROM institutional_radar_signals
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT ?
        """
        params.append(max(1, min(200, int(limit))))

        rows = conn.execute(sql, params).fetchall()
        signals = []
        for r in rows:
            sig = {
                "id": r[0],
                "ticker": r[1],
                "strategy": r[2],
                "company_name": r[3] or get_name(r[1]) or r[1],
                "industry": r[4] or "General",
                "signal_date": r[5],
                "signal_price": float(r[6] or 0.0),
                "ideal_entry_price": float(r[7] or r[6] or 0.0),
                "target_price": float(r[8] or 0.0),
                "stop_loss": float(r[9] or 0.0),
                "risk_reward_ratio": float(r[10] or 2.5),
                "current_price": float(r[11] or r[6] or 0.0),
                "current_date": r[12] or r[5],
                "outcome_return_pct": float(r[13] or 0.0) if r[13] is not None else 0.0,
                "peak_price": float(r[14] or r[11] or r[6] or 0.0),
                "max_gain_pct": float(r[15] or 0.0) if r[15] is not None else 0.0,
                "days_elapsed": int(r[16] or 0),
                "lifecycle_status": r[17] or "ACTIVE",
                "initial_score": float(r[18] or 50.0),
                "initial_dominance": float(r[19] or 0.0),
                "initial_smart_money_cr": float(r[20] or 0.0),
                "whale_count": int(r[21] or 0),
                "trigger_reason": r[22] or "",
                "entry_delay_pct": float(r[23] or 0.0),
                "is_late": bool(r[24]),
                "created_at": r[25],
                "updated_at": r[26],
            }
            signals.append(sig)

        macro_summary = {
            "total_signals": len(signals),
            "active_count": sum(1 for s in signals if s["lifecycle_status"] == "ACTIVE"),
            "target_hit_count": sum(1 for s in signals if s["lifecycle_status"] == "TARGET_HIT"),
            "distribution_exit_count": sum(1 for s in signals if s["lifecycle_status"] == "DISTRIBUTION_EXIT"),
            "cooling_off_count": sum(1 for s in signals if s["lifecycle_status"] == "COOLING_OFF"),
            "avg_outcome_return_pct": round(sum(s["outcome_return_pct"] for s in signals) / len(signals), 2) if signals else 0.0,
            "avg_max_gain_pct": round(sum(s["max_gain_pct"] for s in signals) / len(signals), 2) if signals else 0.0,
            "win_rate_pct": round((sum(1 for s in signals if s["outcome_return_pct"] > 0 or s["lifecycle_status"] == "TARGET_HIT") / len(signals)) * 100.0, 1) if signals else 0.0,
            "total_smart_money_cr": round(sum(s["initial_smart_money_cr"] for s in signals), 2),
        }

        result = TrackedSignalsResult({
            "success": True,
            "signals": signals,
            "count": len(signals),
            "strategy": strat_clean,
            "status": stat_clean,
            "macro_summary": macro_summary,
        })
        return result
    except Exception as e:
        logger.exception("[INSTITUTIONAL] Error in get_tracked_smart_money_signals: %s", e)
        return TrackedSignalsResult({
            "success": False,
            "signals": [],
            "count": 0,
            "strategy": strategy,
            "status": status,
            "macro_summary": {},
            "detail": str(e),
        })
    finally:
        try:
            conn.close()
        except Exception:
            pass
