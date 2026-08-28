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
) -> list[dict[str, Any]]:
    """Pass raw news items through NewsVerifier and return verified, enriched records."""
    settings = settings or Settings()
    verifier = NewsVerifier(settings)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    verified_records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for item in raw_items:
        v_res = verifier.verify_news_item(item)
        if v_res.get("verification_status") != "VERIFIED":
            logger.debug("[NEWS-PIPELINE] Rejected news item '%s': %s", item.get("title"), v_res.get("rejection_reason"))
            continue

        c_hash = v_res.get("canonical_hash")
        if c_hash and c_hash in seen_hashes:
            continue
        if c_hash:
            seen_hashes.add(c_hash)

        title = item.get("title", "").strip()
        summary = item.get("summary", "").strip()
        scored = score_catalyst_headline(title, summary)

        record = {
            "ticker": v_res["resolved_ticker"],
            "stock_name": v_res["official_name"],
            "title": title,
            "publisher": item.get("publisher", "Financial Feed"),
            "link": item.get("link", f"/stock/{v_res['resolved_ticker']}"),
            "published_at": v_res["published_at_utc"],
            "published_at_ist": v_res["published_at_ist"],
            "summary": summary,
            "impact_score": scored["impact_score"],
            "impact_level": scored["impact_level"],
            "category": scored["category"],
            "direction": v_res["verified_direction"],
            "expected_horizon": scored["expected_horizon"],
            "volatility_est": scored["volatility_est"],
            "why_it_matters": scored["why_it_matters"],
            "source": item.get("source", "verified_pipeline"),
            "created_at": now_str,
            "verification_status": "VERIFIED",
            "verification_flags": json.dumps(v_res.get("verification_flags", [])),
            "verified_numbers": json.dumps(v_res.get("verified_numbers", {})),
            "entity_confidence": v_res.get("confidence_score", 0.85),
            "canonical_hash": c_hash,
        }
        verified_records.append(record)

    return verified_records


def save_verified_news_records(
    records: list[dict[str, Any]],
    settings: Settings | None = None,
) -> int:
    """Save verified news records into the database with atomic upsert."""
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
                        entity_confidence, canonical_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        canonical_hash = excluded.canonical_hash
                    """,
                    (
                        r["ticker"], r["stock_name"], r["title"], r["publisher"],
                        r["link"], r["published_at"], r["summary"], r["impact_score"],
                        r["impact_level"], r["category"], r["direction"],
                        r["expected_horizon"], r["volatility_est"], r["why_it_matters"],
                        r["source"], r["created_at"], r["verification_status"],
                        r["verification_flags"], r["verified_numbers"],
                        r["entity_confidence"], r["canonical_hash"],
                    ),
                )
                inserted_count += 1
            except Exception as e:
                logger.debug("Failed inserting verified record %s: %s", r.get("title"), e)

        conn.commit()

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
