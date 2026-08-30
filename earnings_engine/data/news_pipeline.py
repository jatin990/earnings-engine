"""High-Throughput News Ingestion & Verification Pipeline.

Orchestrates multi-source news fetching, runs every item through the 6-stage NewsVerifier,
persists verified records with structured metadata and canonical hashes, and provides
database sanitization routines to purge legacy misattributions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.catalysts_news import _connect, score_catalyst_headline
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.news_verifier import NewsVerifier

logger = logging.getLogger(__name__)


def ensure_news_verification_schema(settings: Settings | None = None) -> None:
    """Ensure news_catalysts table has all verification columns and indexes."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        # Check existing columns
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(news_catalysts)").fetchall()}
        
        new_columns = [
            ("verification_status", "TEXT DEFAULT 'VERIFIED'"),
            ("verification_flags", "TEXT DEFAULT '[]'"),
            ("verified_numbers", "TEXT DEFAULT '{}'"),
            ("entity_confidence", "REAL DEFAULT 0.85"),
            ("canonical_hash", "TEXT"),
            ("signal_price", "REAL"),
            ("signal_date", "TEXT"),
            ("current_price", "REAL"),
            ("price_change_pct", "REAL"),
            ("ai_analysis", "TEXT"),
            ("ai_takeaway", "TEXT"),
            ("ai_direction", "TEXT"),
            ("ai_target", "REAL"),
            ("ai_stop_loss", "REAL"),
            ("ai_model", "TEXT"),
            ("ai_analyzed_at", "TEXT"),
            ("financial_projections", "TEXT DEFAULT '{}'"),
            ("sentiment", "TEXT DEFAULT 'NEUTRAL'"),
            ("temporal_originality", "TEXT DEFAULT 'NEW_PUBLICATION'"),
            ("is_republication", "INTEGER DEFAULT 0"),
            ("originality_rationale", "TEXT DEFAULT ''"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE news_catalysts ADD COLUMN {col_name} {col_type}")
                    logger.info("[NEWS-PIPELINE] Added column %s to news_catalysts", col_name)
                except Exception as e:
                    logger.debug("Failed adding column %s: %s", col_name, e)

        # Create index on canonical_hash
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_news_catalysts_canonical ON news_catalysts (canonical_hash)")
        except Exception:
            pass

        conn.commit()


def process_and_verify_news_items(
    raw_items: list[dict[str, Any]],
    settings: Settings | None = None,
    force_reanalyze: bool = False,
) -> list[dict[str, Any]]:
    """Pass raw news items through NewsVerifier, run AI catalyst analysis ONLY ONCE per news item, and return verified records."""
    settings = settings or Settings()
    verifier = NewsVerifier(settings)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    from earnings_engine.data.ai_news_analyzer import analyze_news_catalyst_ai

    verified_records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()

    for item in raw_items:
        v_res = verifier.verify_news_item(item)
        if v_res.get("verification_status") != "VERIFIED":
            logger.debug("[NEWS-PIPELINE] Rejected news item '%s': %s", item.get("title"), v_res.get("rejection_reason"))
            continue

        c_hash = v_res.get("canonical_hash")
        title = item.get("title", "").strip()
        ticker = v_res["resolved_ticker"]
        t_key = (ticker, title.lower())

        if c_hash and c_hash in seen_hashes:
            continue
        if t_key in seen_titles:
            continue

        if c_hash:
            seen_hashes.add(c_hash)
        seen_titles.add(t_key)

        summary = item.get("summary", "").strip()
        scored = score_catalyst_headline(title, summary)
        pub_d = (v_res.get("published_at_utc") or "")[:10]

        # Calculate on last close's data; fetch price delta from market if not present or stale
        signal_price: float | None = None
        signal_date: str | None = None
        current_price: float | None = None
        price_change_pct: float = 0.0

        if ticker and pub_d:
            try:
                # Determine whether news broke before market close (< 15:30 IST) or after market close (>= 15:30 IST)
                pub_dt_ist = v_res.get("dt_ist")
                is_post_close = False
                if pub_dt_ist:
                    is_post_close = (pub_dt_ist.hour > 15) or (pub_dt_ist.hour == 15 and pub_dt_ist.minute >= 30)
                date_comp = "<=" if is_post_close else "<"

                with _connect(settings) as p_conn:
                    sig_row = p_conn.execute(
                        f"SELECT close, date FROM price_history WHERE ticker = ? AND date {date_comp} ? AND close > 0 ORDER BY date DESC LIMIT 1",
                        (ticker, pub_d),
                    ).fetchone()
                    
                    if not sig_row and not is_post_close:
                        sig_row = p_conn.execute(
                            "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                            (ticker, pub_d),
                        ).fetchone()

                    needs_fetch = False
                    if not sig_row:
                        needs_fetch = True
                    else:
                        try:
                            d_pub = datetime.strptime(pub_d[:10], "%Y-%m-%d").date()
                            d_sig = datetime.strptime(str(sig_row[1])[:10], "%Y-%m-%d").date()
                            if (d_pub - d_sig).days > 4:
                                needs_fetch = True
                        except Exception:
                            pass

                    if needs_fetch:
                        try:
                            from earnings_engine.data.prices import fetch_prices
                            fetch_prices(ticker, settings, force=True)
                            sig_row = p_conn.execute(
                                f"SELECT close, date FROM price_history WHERE ticker = ? AND date {date_comp} ? AND close > 0 ORDER BY date DESC LIMIT 1",
                                (ticker, pub_d),
                            ).fetchone()
                            if not sig_row and not is_post_close:
                                sig_row = p_conn.execute(
                                    "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                                    (ticker, pub_d),
                                raid_fetch=True).fetchone() if hasattr(p_conn, 'raid_fetch') else p_conn.execute(
                                    "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                                    (ticker, pub_d),
                                ).fetchone()
                        except Exception as e:
                            logger.debug("[NEWS-PIPELINE] Auto-fetch price delta for %s failed: %s", ticker, e)

                    if sig_row and sig_row[0] is not None:
                        signal_price = float(sig_row[0])
                        signal_date = str(sig_row[1])

                    latest_row = p_conn.execute(
                        "SELECT close FROM price_history WHERE ticker = ? AND close > 0 ORDER BY date DESC LIMIT 1",
                        (ticker,),
                    ).fetchone()
                    if latest_row and latest_row[0] is not None:
                        current_price = float(latest_row[0])
                    else:
                        current_price = signal_price

                    if signal_price and current_price and signal_price > 0:
                        price_change_pct = round(((current_price - signal_price) / signal_price) * 100.0, 2)
            except Exception as e:
                logger.debug("[NEWS-PIPELINE] Price enrichment failed for %s: %s", ticker, e)

        # -------------------------------------------------------------------
        # Cache Check: Reuse Existing AI Analysis from Database (ONLY ONCE per news)
        # -------------------------------------------------------------------
        cached_row = None
        if not force_reanalyze:
            try:
                with _connect(settings) as check_conn:
                    check_conn.row_factory = sqlite3.Row
                    if c_hash:
                        cached_row = check_conn.execute(
                            """
                            SELECT * FROM news_catalysts
                            WHERE (canonical_hash = ? AND canonical_hash != '') OR (ticker = ? AND title = ?)
                            LIMIT 1
                            """,
                            (c_hash, ticker, title),
                        ).fetchone()
                    else:
                        cached_row = check_conn.execute(
                            "SELECT * FROM news_catalysts WHERE ticker = ? AND title = ? LIMIT 1",
                            (ticker, title),
                        ).fetchone()
            except Exception as e:
                logger.debug("[NEWS-PIPELINE] Error querying news AI cache for %s: %s", ticker, e)

        if cached_row and (cached_row["ai_analysis"] or cached_row["ai_analyzed_at"]):
            # Reuse existing AI analysis from the database without querying OmniRoute
            try:
                ai_res = json.loads(cached_row["ai_analysis"]) if isinstance(cached_row["ai_analysis"], str) else (cached_row["ai_analysis"] or {})
            except Exception:
                ai_res = {}
            ai_direction = cached_row["ai_direction"] or ai_res.get("direction") or v_res["verified_direction"]
            ai_sentiment = cached_row["sentiment"] or ai_res.get("sentiment") or ai_direction
            ai_takeaway = cached_row["ai_takeaway"] or ai_res.get("trading_takeaway") or scored["why_it_matters"]
            ai_target = cached_row["ai_target"] if cached_row["ai_target"] is not None else ai_res.get("target_price")
            ai_stop = cached_row["ai_stop_loss"] if cached_row["ai_stop_loss"] is not None else ai_res.get("stop_loss")
            ai_proj = cached_row["financial_projections"] or ai_res.get("financial_projections") or {}
            ai_temp_orig = cached_row["temporal_originality"] or ai_res.get("temporal_originality") or "NEW_PUBLICATION"
            ai_is_repub = cached_row["is_republication"] if cached_row["is_republication"] is not None else (1 if ai_res.get("is_republication") else 0)
            ai_orig_rat = cached_row["originality_rationale"] or ai_res.get("originality_rationale") or ""
            ai_model = cached_row["ai_model"] or ai_res.get("ai_model", "omniroute/cached")
            ai_analyzed_at = cached_row["ai_analyzed_at"] or now_str
            logger.info("[NEWS-PIPELINE] Reusing cached AI analysis from DB for %s: '%s'", ticker, title[:45])
        else:
            # -------------------------------------------------------------------
            # Execute Free AI Catalyst Analysis via OmniRoute (Invoked ONLY ONCE)
            # -------------------------------------------------------------------
            ai_ctx = {
                "ticker": ticker,
                "stock_name": v_res["official_name"],
                "title": title,
                "summary": summary,
                "signal_price": signal_price,
                "current_price": current_price,
                "published_at": v_res["published_at_utc"],
                "verified_numbers": v_res.get("verified_numbers", {}),
            }
            ai_res = analyze_news_catalyst_ai(ai_ctx, settings=settings)

            ai_direction = ai_res.get("direction") or v_res["verified_direction"]
            ai_sentiment = ai_res.get("sentiment") or ai_direction
            ai_takeaway = ai_res.get("trading_takeaway") or scored["why_it_matters"]
            ai_target = ai_res.get("target_price")
            ai_stop = ai_res.get("stop_loss")
            ai_proj = ai_res.get("financial_projections") or {}
            ai_temp_orig = ai_res.get("temporal_originality") or "NEW_PUBLICATION"
            ai_is_repub = 1 if ai_res.get("is_republication") else 0
            ai_orig_rat = ai_res.get("originality_rationale") or ""
            ai_model = ai_res.get("ai_model", "free-ai-engine")
            ai_analyzed_at = ai_res.get("ai_analyzed_at", now_str)

        # Merge AI impact score if more granular
        if ai_res.get("impact_score") and ai_res["impact_score"] > 0:
            scored["impact_score"] = int(ai_res["impact_score"])
            scored["impact_level"] = ai_res.get("impact_level", scored["impact_level"])

        record = {
            "ticker": ticker,
            "stock_name": v_res["official_name"],
            "title": title,
            "publisher": item.get("publisher", "Financial Feed"),
            "link": item.get("link", f"/stock/{ticker}"),
            "published_at": v_res["published_at_utc"],
            "published_at_ist": v_res["published_at_ist"],
            "summary": summary,
            "impact_score": scored["impact_score"],
            "impact_level": scored["impact_level"],
            "category": scored["category"],
            "direction": ai_direction,
            "sentiment": ai_sentiment,
            "expected_horizon": ai_res.get("expected_horizon") or scored["expected_horizon"],
            "volatility_est": ai_res.get("volatility_est") or scored["volatility_est"],
            "why_it_matters": ai_takeaway,
            "source": item.get("source", "verified_pipeline"),
            "created_at": now_str,
            "verification_status": "VERIFIED",
            "verification_flags": json.dumps(v_res.get("verification_flags", [])),
            "verified_numbers": json.dumps(v_res.get("verified_numbers", {})),
            "entity_confidence": v_res.get("confidence_score", 0.85),
            "canonical_hash": c_hash,
            "signal_price": signal_price,
            "signal_date": signal_date,
            "current_price": current_price,
            "price_change_pct": price_change_pct,
            "ai_analysis": json.dumps(ai_res) if isinstance(ai_res, dict) else str(ai_res),
            "ai_takeaway": ai_takeaway,
            "ai_direction": ai_direction,
            "ai_target": ai_target,
            "ai_stop_loss": ai_stop,
            "financial_projections": json.dumps(ai_proj) if isinstance(ai_proj, dict) else str(ai_proj),
            "temporal_originality": ai_temp_orig,
            "is_republication": ai_is_repub,
            "originality_rationale": ai_orig_rat,
            "ai_model": ai_model,
            "ai_analyzed_at": ai_analyzed_at,
        }
        verified_records.append(record)

    return verified_records


def save_verified_news_records(
    records: list[dict[str, Any]],
    settings: Settings | None = None,
) -> int:
    """Save verified news records into the database with atomic upsert and AI analysis fields."""
    settings = settings or Settings()
    ensure_news_verification_schema(settings)

    if not records:
        return 0

    inserted_count = 0
    with _connect(settings) as conn:
        for r in records:
            try:
                conn.execute(
                    """
                    INSERT INTO news_catalysts (
                        ticker, stock_name, title, publisher, link, published_at,
                        summary, impact_score, impact_level, category, direction,
                        expected_horizon, volatility_est, why_it_matters, source, created_at,
                        verification_status, verification_flags, verified_numbers,
                        entity_confidence, canonical_hash, signal_price, signal_date,
                        current_price, price_change_pct, ai_analysis, ai_takeaway,
                        ai_direction, ai_target, ai_stop_loss, ai_model, ai_analyzed_at,
                        financial_projections, sentiment, temporal_originality, is_republication, originality_rationale
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, title) DO UPDATE SET
                        stock_name = excluded.stock_name,
                        publisher = excluded.publisher,
                        link = excluded.link,
                        published_at = excluded.published_at,
                        summary = excluded.summary,
                        impact_score = excluded.impact_score,
                        impact_level = excluded.impact_level,
                        category = excluded.category,
                        direction = excluded.direction,
                        expected_horizon = excluded.expected_horizon,
                        volatility_est = excluded.volatility_est,
                        why_it_matters = excluded.why_it_matters,
                        verification_status = excluded.verification_status,
                        verification_flags = excluded.verification_flags,
                        verified_numbers = excluded.verified_numbers,
                        entity_confidence = excluded.entity_confidence,
                        canonical_hash = excluded.canonical_hash,
                        signal_price = COALESCE(excluded.signal_price, news_catalysts.signal_price),
                        signal_date = COALESCE(excluded.signal_date, news_catalysts.signal_date),
                        current_price = COALESCE(excluded.current_price, news_catalysts.current_price),
                        price_change_pct = COALESCE(excluded.price_change_pct, news_catalysts.price_change_pct),
                        ai_analysis = COALESCE(excluded.ai_analysis, news_catalysts.ai_analysis),
                        ai_takeaway = COALESCE(excluded.ai_takeaway, news_catalysts.ai_takeaway),
                        ai_direction = COALESCE(excluded.ai_direction, news_catalysts.ai_direction),
                        ai_target = COALESCE(excluded.ai_target, news_catalysts.ai_target),
                        ai_stop_loss = COALESCE(excluded.ai_stop_loss, news_catalysts.ai_stop_loss),
                        ai_model = COALESCE(excluded.ai_model, news_catalysts.ai_model),
                        ai_analyzed_at = COALESCE(excluded.ai_analyzed_at, news_catalysts.ai_analyzed_at),
                        financial_projections = COALESCE(excluded.financial_projections, news_catalysts.financial_projections),
                        sentiment = COALESCE(excluded.sentiment, news_catalysts.sentiment),
                        temporal_originality = COALESCE(excluded.temporal_originality, news_catalysts.temporal_originality),
                        is_republication = COALESCE(excluded.is_republication, news_catalysts.is_republication),
                        originality_rationale = COALESCE(excluded.originality_rationale, news_catalysts.originality_rationale)
                    """,
                    (
                        r["ticker"], r["stock_name"], r["title"], r["publisher"],
                        r["link"], r["published_at"], r["summary"], r["impact_score"],
                        r["impact_level"], r["category"], r["direction"],
                        r["expected_horizon"], r["volatility_est"], r["why_it_matters"],
                        r["source"], r["created_at"], r["verification_status"],
                        r["verification_flags"], r["verified_numbers"],
                        r["entity_confidence"], r["canonical_hash"],
                        r.get("signal_price"), r.get("signal_date"),
                        r.get("current_price"), r.get("price_change_pct", 0.0),
                        r.get("ai_analysis"), r.get("ai_takeaway"),
                        r.get("ai_direction"), r.get("ai_target"),
                        r.get("ai_stop_loss"), r.get("ai_model"),
                        r.get("ai_analyzed_at"),
                        r.get("financial_projections", "{}"),
                        r.get("sentiment", "NEUTRAL"),
                        r.get("temporal_originality", "NEW_PUBLICATION"),
                        r.get("is_republication", 0),
                        r.get("originality_rationale", ""),
                    ),
                )
                inserted_count += 1
            except Exception as e:
                logger.debug("Failed inserting verified record %s: %s", r.get("title"), e)

        conn.commit()

    if inserted_count > 0:
        try:
            high_70 = sum(1 for r in records if (r.get("impact_score") or 0) >= 70)
            if high_70 > 0:
                from earnings_engine.api.routers.system import increment_badge_counter
                increment_badge_counter("high_impact_news_70", high_70, settings)
        except Exception:
            pass

    return inserted_count


def sanitize_legacy_database_news(settings: Settings | None = None) -> dict[str, int]:
    """Scan and sanitize all existing rows in news_catalysts.

    Removes false dictionary collisions (e.g. sports news, Boeing for CREST.NS),
    re-assigns conglomerate entities, and populates verification metadata.
    """
    settings = settings or Settings()
    ensure_news_verification_schema(settings)
    verifier = NewsVerifier(settings)

    purged_count = 0
    updated_count = 0

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM news_catalysts").fetchall()

        for r in rows:
            row_dict = dict(r)
            row_id = row_dict["id"]
            v_res = verifier.verify_news_item(row_dict)

            if v_res.get("verification_status") != "VERIFIED":
                # Delete invalid / noisy / misattributed row
                conn.execute("DELETE FROM news_catalysts WHERE id = ?", (row_id,))
                purged_count += 1
            else:
                # Update with verified metadata and resolved ticker
                resolved_ticker = v_res["resolved_ticker"]
                official_name = v_res["official_name"]
                c_hash = v_res.get("canonical_hash")
                v_flags = json.dumps(v_res.get("verification_flags", []))
                v_nums = json.dumps(v_res.get("verified_numbers", {}))
                conf = v_res.get("confidence_score", 0.85)

                try:
                    conn.execute(
                        """
                        UPDATE news_catalysts
                        SET ticker = ?, stock_name = ?, direction = ?,
                            verification_status = 'VERIFIED', verification_flags = ?,
                            verified_numbers = ?, entity_confidence = ?, canonical_hash = ?
                        WHERE id = ?
                        """,
                        (
                            resolved_ticker, official_name, v_res["verified_direction"],
                            v_flags, v_nums, conf, c_hash, row_id
                        ),
                    )
                    updated_count += 1
                except sqlite3.IntegrityError:
                    # Row already exists under the resolved ticker; delete the duplicate
                    conn.execute("DELETE FROM news_catalysts WHERE id = ?", (row_id,))
                    purged_count += 1

        conn.commit()

    logger.info("[NEWS-PIPELINE] Sanitized database: %d purged, %d verified and updated", purged_count, updated_count)
    return {"purged": purged_count, "verified": updated_count}
