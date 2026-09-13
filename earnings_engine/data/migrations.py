"""Automated database migration framework for Earnings Engine.

Applies versioned, idempotent schema updates on startup and tracks applied
versions in the `schema_migrations` table.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, NamedTuple

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.migrations")


class Migration(NamedTuple):
    version: int
    name: str
    up: Callable[[Any], None]


def _get_table_columns(conn: Any, table_name: str) -> set[str]:
    """Safely inspect existing column names for a table using PRAGMA table_info."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        cols = set()
        for r in rows:
            if hasattr(r, "get"):
                c = r.get("name")
            elif isinstance(r, (tuple, list)) and len(r) > 1:
                c = r[1]
            elif hasattr(r, "keys") and "name" in r.keys():
                c = r["name"]
            else:
                c = None
            if c:
                cols.add(c)
        return cols
    except Exception:
        return set()


def _add_column_if_missing(conn: Any, table_name: str, col_name: str, col_type: str) -> bool:
    """Idempotently add a column to a table only if it does not already exist."""
    existing = _get_table_columns(conn, table_name)
    if not existing or col_name not in existing:
        try:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
            return True
        except Exception:
            return False
    return False


# ---------------------------------------------------------------------------
# Individual Migrations
# ---------------------------------------------------------------------------

def _migration_001_core_schema(conn: Any) -> None:
    """Core tables: earnings_history, price_history, universes, caches."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_history (
            ticker TEXT NOT NULL,
            earnings_date TEXT NOT NULL,
            eps_estimate REAL,
            eps_reported REAL,
            surprise_pct REAL,
            source TEXT NOT NULL DEFAULT 'yfinance',
            PRIMARY KEY (ticker, earnings_date, source)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_history_ticker ON earnings_history (ticker)")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            PRIMARY KEY (ticker, date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS universes (
            universe_name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (universe_name, ticker)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS universe_stocks (
            universe_name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT,
            added_at TEXT NOT NULL,
            PRIMARY KEY (universe_name, ticker)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS universe_freshness (
            universe_name TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            stock_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_freshness (
            market TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_fetch_log (
            fetch_date TEXT NOT NULL PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            events_count INTEGER DEFAULT 0,
            inserted_count INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_month_cache (
            cache_key TEXT NOT NULL PRIMARY KEY,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_fetch_log (
            ticker TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_month_cache (
            cache_key TEXT PRIMARY KEY,
            cached_at TEXT NOT NULL,
            data_json TEXT NOT NULL
        )
    """)


def _migration_002_swing_ranges(conn: Any) -> None:
    """Swing trading ranges and cycle detection tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swing_ranges (
            watchlist TEXT NOT NULL,
            ticker TEXT NOT NULL,
            lower_bound REAL NOT NULL,
            upper_bound REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'auto',
            cycles INTEGER,
            avg_cycle_days REAL,
            last_updated TEXT NOT NULL,
            PRIMARY KEY (watchlist, ticker)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_ranges_lookup ON swing_ranges (watchlist, ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_ranges_ticker ON swing_ranges (ticker)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS swing_cycle_history (
            watchlist TEXT NOT NULL,
            ticker TEXT NOT NULL,
            cycle_idx INTEGER NOT NULL,
            cycle_start TEXT NOT NULL,
            cycle_end TEXT NOT NULL,
            duration_days INTEGER NOT NULL,
            lower_bound REAL,
            upper_bound REAL,
            PRIMARY KEY (watchlist, ticker, cycle_idx)
        )
    """)


def _migration_003_multimodal_ai(conn: Any) -> None:
    """Multi-modal AI synthesis and news sentiment tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_news_predictions (
            ticker TEXT NOT NULL,
            run_at TEXT NOT NULL,
            current_price REAL,
            ai_signal TEXT,
            sentiment_score REAL,
            confidence REAL,
            volume_status TEXT,
            volume_ratio REAL,
            catalysts TEXT,
            risk_factors TEXT,
            thesis TEXT,
            news_count INTEGER,
            payload TEXT,
            PRIMARY KEY (ticker, run_at)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_news_ticker ON ai_news_predictions (ticker)")


def _migration_004_ticker_audit(conn: Any) -> None:
    """Audit logging table for on-demand ticker recalculations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            refreshed_at TEXT NOT NULL,
            has_changes INTEGER NOT NULL DEFAULT 0,
            changes_summary TEXT NOT NULL,
            previous_values TEXT,
            updated_values TEXT,
            diff_json TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ticker_time ON ticker_audit_log (ticker, refreshed_at DESC)")


def _migration_005_unified_tickers(conn: Any) -> None:
    """Unified master table consolidating ticker_names, ticker_industry, ticker_market_cap, ticker_metrics."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            sector TEXT,
            market_cap REAL,
            market_cap_updated_at TEXT,
            metrics TEXT,
            metrics_as_of_date TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickers_industry ON tickers (industry)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickers_market_cap ON tickers (market_cap)")

    # Migrate data from legacy ticker_names if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, name, last_updated)
            SELECT ticker, name, DATETIME('now') FROM ticker_names
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                name = COALESCE(excluded.name, tickers.name)
        """)
    except Exception:
        pass

    # Migrate data from legacy ticker_industry if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, industry, sector, last_updated)
            SELECT ticker, industry, sector, DATETIME('now') FROM ticker_industry
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                industry = COALESCE(excluded.industry, tickers.industry),
                sector = COALESCE(excluded.sector, tickers.sector)
        """)
    except Exception:
        pass

    # Migrate data from legacy ticker_market_cap if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, market_cap, market_cap_updated_at, last_updated)
            SELECT ticker, market_cap, fetched_at, DATETIME('now') FROM ticker_market_cap
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                market_cap = COALESCE(excluded.market_cap, tickers.market_cap),
                market_cap_updated_at = COALESCE(excluded.market_cap_updated_at, tickers.market_cap_updated_at)
        """)
    except Exception:
        pass

    # Migrate data from legacy ticker_metrics if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, metrics, metrics_as_of_date, last_updated)
            SELECT ticker, metrics, as_of_date, DATETIME('now') FROM ticker_metrics
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                metrics = COALESCE(excluded.metrics, tickers.metrics),
                metrics_as_of_date = COALESCE(excluded.metrics_as_of_date, tickers.metrics_as_of_date)
        """)
    except Exception:
        pass


def _migration_006_drop_legacy_ticker_tables(conn: Any) -> None:
    """Drop legacy ticker tables consolidated into unified tickers master table."""
    legacy_tables = [
        "ticker_names",
        "market_caps",
        "ticker_market_cap",
        "ticker_metrics",
        "ticker_industries",
        "ticker_industry",
    ]
    for tbl in legacy_tables:
        try:
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass


def _migration_007_consolidate_earnings_and_freshness(conn: Any) -> None:
    """Deduplicate earnings_history to (ticker, earnings_date) and consolidate freshness into tickers."""
    # 1. Add freshness columns to master tickers table
    for col in ("earnings_fetched_at", "prices_fetched_at"):
        _add_column_if_missing(conn, "tickers", col, "TEXT")

    # 2. Migrate existing freshness records into tickers
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, earnings_fetched_at, last_updated)
            SELECT ticker, fetched_at, DATETIME('now') FROM earnings_freshness
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                earnings_fetched_at = COALESCE(excluded.earnings_fetched_at, tickers.earnings_fetched_at)
        """)
    except Exception:
        pass

    try:
        conn.execute("""
            INSERT INTO tickers (ticker, prices_fetched_at, last_updated)
            SELECT ticker, fetched_at, DATETIME('now') FROM price_fetch_log
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                prices_fetched_at = COALESCE(excluded.prices_fetched_at, tickers.prices_fetched_at)
        """)
    except Exception:
        pass

    # 3. Deduplicate and rebuild earnings_history with PK (ticker, earnings_date)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_history_new (
            ticker TEXT NOT NULL,
            earnings_date TEXT NOT NULL,
            eps_estimate REAL,
            eps_reported REAL,
            surprise_pct REAL,
            source TEXT NOT NULL DEFAULT 'yfinance',
            PRIMARY KEY (ticker, earnings_date)
        )
    """)

    try:
        conn.execute("""
            INSERT INTO earnings_history_new (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            SELECT 
                ticker,
                earnings_date,
                MAX(eps_estimate) as eps_estimate,
                MAX(eps_reported) as eps_reported,
                MAX(surprise_pct) as surprise_pct,
                MAX(source) as source
            FROM earnings_history
            GROUP BY ticker, earnings_date
            ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                eps_estimate = COALESCE(excluded.eps_estimate, earnings_history_new.eps_estimate),
                eps_reported = COALESCE(excluded.eps_reported, earnings_history_new.eps_reported),
                surprise_pct = COALESCE(excluded.surprise_pct, earnings_history_new.surprise_pct)
        """)
        conn.execute("DROP TABLE earnings_history")
        conn.execute("ALTER TABLE earnings_history_new RENAME TO earnings_history")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_history_date ON earnings_history (earnings_date)")
    except Exception:
        pass

    # 4. Drop obsolete tables
    for tbl in ("earnings_freshness", "price_fetch_log", "universe_stocks"):
        try:
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass


def _migration_008_passcodes(conn: Any) -> None:
    """Passcodes table for role-based friend portal & routing gate."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS passcodes (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            allowed_routes TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            max_uses INTEGER,
            use_count INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)


def _migration_009_rbac_and_scoped_access(conn: Any) -> None:
    """Fine-grained RBAC, Email OTP onboarding, friend access, and scoped data entities."""
    now_str = datetime.now().isoformat(timespec="seconds")
    
    # 1. Users
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner', 'friend')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")

    # 2. Invite Codes
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invite_codes (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            allowed_email TEXT,
            scopes TEXT NOT NULL,
            max_uses INTEGER DEFAULT 1,
            uses_count INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_invite_codes_active ON invite_codes (is_active)")

    # 3. Friend Access (1:1 with Friend Users)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS friend_access (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            can_view_trips INTEGER NOT NULL DEFAULT 0,
            can_view_cards INTEGER NOT NULL DEFAULT 0,
            can_view_net_worth INTEGER NOT NULL DEFAULT 0,
            granted_via_code TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_friend_access_user ON friend_access (user_id)")

    # 4. OTP Verifications
    conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_verifications (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            invite_code TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL,
            verified_at TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_otp_email_code ON otp_verifications (email, invite_code)")

    # 5. Trips & Plans
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            destination TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            status TEXT NOT NULL CHECK(status IN ('planning', 'confirmed', 'completed')),
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # 6. Credit Cards (Non-sensitive benefits & rewards)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS credit_cards (
            id TEXT PRIMARY KEY,
            card_name TEXT NOT NULL,
            issuer TEXT NOT NULL,
            network TEXT NOT NULL,
            category_perks TEXT NOT NULL,
            lounge_access_summary TEXT,
            annual_fee_status TEXT,
            display_order INTEGER DEFAULT 0
        )
    """)

    # 7. High-level Net Worth Summary
    conn.execute("""
        CREATE TABLE IF NOT EXISTS net_worth_snapshots (
            id TEXT PRIMARY KEY,
            as_of_date TEXT NOT NULL,
            total_net_worth_band TEXT NOT NULL,
            allocation_pct TEXT NOT NULL,
            yoy_growth_pct REAL,
            updated_at TEXT NOT NULL
        )
    """)

    # Seed Default Owner and Initial Demo Records
    try:
        # Seed Owner
        conn.execute("""
            INSERT OR IGNORE INTO users (id, email, name, role, is_active, created_at)
            VALUES ('usr_owner_001', 'owner@earnings-engine.local', 'Owner Account', 'owner', 1, ?)
        """, (now_str,))

        # Seed Sample Invite Codes
        demo_codes = [
            ("VIP-ALL-ACCESS", "VIP Friend (All Scopes)", None, '["can_view_trips", "can_view_cards", "can_view_net_worth"]', 10, 0, None, 1, "usr_owner_001", now_str),
            ("TRIP-EXPLORER", "Travel Buddy (Trips Only)", None, '["can_view_trips"]', 5, 0, None, 1, "usr_owner_001", now_str),
            ("CARDS-REWARDS", "Credit Card Enthusiast", None, '["can_view_cards"]', 5, 0, None, 1, "usr_owner_001", now_str),
        ]
        conn.executemany("""
            INSERT OR IGNORE INTO invite_codes (code, label, allowed_email, scopes, max_uses, uses_count, expires_at, is_active, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, demo_codes)

        # Seed Trips
        sample_trips = [
            ("trip_001", "Kyoto & Tokyo Cherry Blossom Expedition", "Japan (Kyoto / Tokyo)", "2026-10-10", "2026-10-22", "confirmed", "Shinkansen pass booked; stay in Gion & Shinjuku.", now_str),
            ("trip_002", "Swiss Alps High-Altitude Trekking", "Switzerland (Zermatt / Grindelwald)", "2027-01-15", "2027-01-25", "planning", "Matterhorn glacier trail & mountain rail passes.", now_str),
        ]
        conn.executemany("""
            INSERT OR IGNORE INTO trips (id, title, destination, start_date, end_date, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_trips)

        # Seed Credit Cards
        sample_cards = [
            ("card_001", "Infinia Metal Edition", "HDFC Bank", "Visa Infinite", '{"flights_hotels": "10x SmartBuy (33.3% reward rate)", "dining": "5x Dineout", "general": "3.3% baseline"}', "Unlimited International & Domestic Lounge Access (Priority Pass)", "Waived (Spend Milestone)", 1),
            ("card_002", "Platinum Reserve Card", "American Express", "Amex", '{"travel": "3x Membership Rewards", "weekend_dining": "5x", "concierge": "24/7 Global Travel Assistant"}', "Domestic Lounge Access + Centurion Lounges", "Annual Renewal Active", 2),
            ("card_003", "Magnus for Burgundy", "Axis Bank", "Mastercard World Elite", '{"travel": "12x TravelEdge Boost", "international": "2x Forex Rewards", "forex_markup": "2.0% Low Fee"}', "Unlimited Domestic + 8 Guest Visits per year", "Waived on Burgundy Criteria", 3),
        ]
        conn.executemany("""
            INSERT OR IGNORE INTO credit_cards (id, card_name, issuer, network, category_perks, lounge_access_summary, annual_fee_status, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_cards)

        # Seed Net Worth Snapshot
        conn.execute("""
            INSERT OR IGNORE INTO net_worth_snapshots (id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at)
            VALUES ('nw_001', '2026-08-01', '₹1.5Cr - ₹2.5Cr Band', '{"Indian Equities": 58, "US Tech": 18, "Debt & Liquid Funds": 14, "Gold & Sovereign Bonds": 7, "Crypto & Sandbox": 3}', 24.8, ?)
        """, (now_str,))
    except Exception:
        pass


def _migration_010_credit_cards_and_otp_requests(conn: Any) -> None:
    """Enhanced Credit Card fields (last4, limits, theme, sharing) & OTP requests table."""
    now_str = datetime.now().isoformat(timespec="seconds")
    
    # 1. Enhance credit_cards table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS credit_cards (
            id TEXT PRIMARY KEY,
            card_name TEXT NOT NULL,
            issuer TEXT NOT NULL,
            network TEXT NOT NULL,
            category_perks TEXT NOT NULL,
            lounge_access_summary TEXT,
            annual_fee_status TEXT,
            display_order INTEGER DEFAULT 0
        )
    """)
    
    # Add new columns if missing
    new_cols = [
        ("last4", "TEXT DEFAULT '8842'"),
        ("card_holder", "TEXT DEFAULT 'VIP Member'"),
        ("color_theme", "TEXT DEFAULT 'obsidian'"),
        ("credit_limit", "REAL DEFAULT 500000.0"),
        ("available_limit", "REAL DEFAULT 428760.0"),
        ("billing_cycle_day", "INTEGER DEFAULT 15"),
        ("is_shared_with_friends", "INTEGER DEFAULT 1"),
        ("created_at", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        _add_column_if_missing(conn, "credit_cards", col_name, col_type)

    # 2. OTP Requests Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS credit_card_otp_requests (
            id TEXT PRIMARY KEY,
            card_id TEXT NOT NULL,
            requested_by_name TEXT NOT NULL,
            requested_by_role TEXT DEFAULT 'friend',
            amount REAL NOT NULL,
            merchant TEXT NOT NULL,
            purpose TEXT,
            urgency TEXT DEFAULT 'normal',
            status TEXT NOT NULL DEFAULT 'pending',
            otp_code TEXT,
            otp_expires_at TEXT,
            response_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cc_otp_card ON credit_card_otp_requests(card_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cc_otp_status ON credit_card_otp_requests(status)")

    # 3. Seed / Update sample cards with themes and limits
    sample_cards = [
        ("card_001", "Infinia Metal Edition", "HDFC Bank", "Visa Infinite", '{"flights_hotels": "10x SmartBuy (33.3% reward rate)", "dining": "5x Dineout", "general": "3.3% baseline", "forex": "2.0% Low Markup"}', "Unlimited Priority Pass (Self + Guest)", "Waived (Spend Milestone)", 1, "8842", "Jatin", "obsidian", 1000000.0, 850000.0, 15, 1, now_str),
        ("card_002", "Platinum Reserve Card", "American Express", "Amex", '{"travel": "3x Membership Rewards", "weekend_dining": "5x", "concierge": "24/7 Global Travel Assistant", "hotel": "Fine Hotels & Resorts perks"}', "Domestic Lounges + Centurion Lounges Access", "Annual Renewal Active", 2, "3004", "Jatin", "platinum-frost", 750000.0, 680000.0, 18, 1, now_str),
        ("card_003", "Magnus for Burgundy", "Axis Bank", "Mastercard World Elite", '{"travel": "12x TravelEdge Boost", "international": "2x Forex Rewards", "forex_markup": "2.0% Low Fee", "dining": "Extra 40% on EazyDiner"}', "Unlimited Domestic + 8 Guest Visits/yr", "Waived on Burgundy Tier", 3, "6190", "Jatin", "burgundy-rose", 600000.0, 520000.0, 25, 1, now_str),
        ("card_004", "Emeralde Private Metal", "ICICI Bank", "Mastercard World Elite", '{"flights": "6 Reward Points per ₹100", "golf": "Unlimited Golf Rounds", "cancellation": "Zero Flight Cancellation Fee"}', "Unlimited DreamFolks Lounge Access Global", "Lifetime Free / Burgundy Linked", 4, "4419", "Jatin", "emerald-gold", 800000.0, 745000.0, 10, 1, now_str),
    ]
    for c in sample_cards:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO credit_cards 
                (id, card_name, issuer, network, category_perks, lounge_access_summary, annual_fee_status, display_order, last4, card_holder, color_theme, credit_limit, available_limit, billing_cycle_day, is_shared_with_friends, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, c)
        except Exception:
            pass

    # 4. Seed demo OTP request for immediate testing
    demo_otp_reqs = [
        ("req_cc_demo_01", "card_001", "Rohan (Friend)", "friend", 4250.0, "MakeMyTrip Flight Booking", "Flight to Mumbai conference", "high", "approved", "849201", (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds"), "Approved for travel", now_str, now_str),
        ("req_cc_demo_02", "card_003", "Amit K.", "friend", 1899.0, "Amazon India", "Apple MagSafe charger", "normal", "pending", None, None, None, now_str, now_str),
    ]
    for r in demo_otp_reqs:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO credit_card_otp_requests
                (id, card_id, requested_by_name, requested_by_role, amount, merchant, purpose, urgency, status, otp_code, otp_expires_at, response_notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, r)
        except Exception:
            pass


def _migration_011_trips_and_net_worth_expansion(conn: Any) -> None:
    """Enhance trips with rich itinerary fields, activities, and net worth history snapshots."""
    now_str = datetime.now().isoformat(timespec="seconds")

    # 1. Enhance trips table
    new_trip_cols = [
        ("cover_image", "TEXT DEFAULT 'japan'"),
        ("estimated_budget", "REAL DEFAULT 150000.0"),
        ("is_shared_with_friends", "INTEGER DEFAULT 1"),
        ("flight_details", "TEXT"),
        ("hotel_details", "TEXT"),
        ("packing_list", "TEXT"),
    ]
    for col_name, col_type in new_trip_cols:
        _add_column_if_missing(conn, "trips", col_name, col_type)

    # 2. Trip Activities & Suggestions Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trip_activities (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL,
            suggested_by_name TEXT NOT NULL,
            suggested_by_role TEXT DEFAULT 'friend',
            activity_title TEXT NOT NULL,
            location TEXT,
            approx_cost REAL DEFAULT 0.0,
            votes_count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'suggested',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trip_act_trip ON trip_activities(trip_id)")

    # 3. Seed / Update sample trips with rich details
    sample_trips = [
        ("trip_001", "Kyoto & Tokyo Cherry Blossom Expedition", "Japan (Kyoto / Tokyo)", "2026-10-10", "2026-10-22", "confirmed", "Shinkansen bullet pass booked; stay in Gion Ryokan & Shinjuku tower.", now_str, "japan", 320000.0, 1, "ANA All Nippon NH-830 (BOM -> HND)", "Hyatt Regency Kyoto & Cerulean Tower Shibuya", '["Passport & Visa", "Universal Adapter", "JR Rail Pass Exchange", "Pocket Wi-Fi eSIM", "Cash Yen (20,000¥)"]'),
        ("trip_002", "Swiss Alps High-Altitude Trekking", "Switzerland (Zermatt / Grindelwald)", "2027-01-15", "2027-01-25", "planning", "Matterhorn glacier trail & mountain rail passes.", now_str, "swiss", 450000.0, 1, "Swiss Int Air LX-155 (BOM -> ZRH)", "The Omnia Zermatt & Romantik Hotel Grindelwald", '["Gore-Tex Shell", "Thermal Base Layers", "Hiking Poles", "Swiss Travel Pass", "Action Camera"]'),
        ("trip_003", "Amalfi Coast & Capri Yacht Charter", "Italy (Positano / Capri)", "2027-05-20", "2027-05-30", "planning", "Private catamaran charter along Amalfi cliffside.", now_str, "amalfi", 580000.0, 1, "Emirates (BOM -> DXB -> FCO)", "Le Sirenuse Positano & Hotel Caesar Augustus Capri", '["Linen Shirts", "Polarized Sunglasses", "Boat Shoes", "International Driving Permit"]'),
    ]
    for t in sample_trips:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO trips
                (id, title, destination, start_date, end_date, status, notes, created_at, cover_image, estimated_budget, is_shared_with_friends, flight_details, hotel_details, packing_list)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, t)
        except Exception:
            pass

    # 4. Seed sample activities for trips
    sample_activities = [
        ("act_001", "trip_001", "Rohan (Friend)", "friend", "Fushimi Inari Sunrise Hike & Matcha Tasting", "Kyoto, Japan", 2500.0, 4, "accepted", now_str),
        ("act_002", "trip_001", "Amit K.", "friend", "TeamLab Planets Digital Art Immersion", "Tokyo, Japan", 3800.0, 3, "accepted", now_str),
        ("act_003", "trip_001", "Jatin (Owner)", "owner", "Sukiyabashi Jiro Sushi Tasting Course", "Ginza, Tokyo", 25000.0, 5, "accepted", now_str),
        ("act_004", "trip_002", "Sarah M.", "friend", "Gornergrat Bahn Panoramic Train Ride", "Zermatt, Switzerland", 8500.0, 2, "suggested", now_str),
    ]
    for a in sample_activities:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO trip_activities
                (id, trip_id, suggested_by_name, suggested_by_role, activity_title, location, approx_cost, votes_count, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, a)
        except Exception:
            pass

    # 5. Seed historical Net Worth Snapshots
    history_snapshots = [
        ("nw_001", "2026-08-01", "₹1.5Cr - ₹2.5Cr Band", '{"Indian Equities": 58, "US Tech": 18, "Debt & Liquid Funds": 14, "Gold & Sovereign Bonds": 7, "Crypto & Sandbox": 3}', 24.8, now_str),
        ("nw_002", "2026-05-01", "₹1.2Cr - ₹1.8Cr Band", '{"Indian Equities": 55, "US Tech": 19, "Debt & Liquid Funds": 16, "Gold & Sovereign Bonds": 7, "Crypto & Sandbox": 3}', 21.2, now_str),
        ("nw_003", "2026-01-01", "₹1.0Cr - ₹1.5Cr Band", '{"Indian Equities": 52, "US Tech": 20, "Debt & Liquid Funds": 18, "Gold & Sovereign Bonds": 7, "Crypto & Sandbox": 3}', 18.5, now_str),
        ("nw_004", "2025-08-01", "₹80L - ₹1.2Cr Band", '{"Indian Equities": 50, "US Tech": 20, "Debt & Liquid Funds": 20, "Gold & Sovereign Bonds": 7, "Crypto & Sandbox": 3}', 15.0, now_str),
    ]
    for s in history_snapshots:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO net_worth_snapshots
                (id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, s)
        except Exception:
            pass


def _migration_012_quarter_repeaters(conn: Any) -> None:
    """Create table for Quarter Repeaters & AI Forward Earnings Radar predictions."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quarter_repeater_predictions (
            ticker TEXT NOT NULL,
            run_at TEXT NOT NULL,
            as_of_quarter TEXT,
            last_eps_surprise REAL,
            last_week_high_pct REAL,
            last_quality_score INTEGER,
            beat_streak INTEGER,
            industry_buzz_tag TEXT,
            ai_repeat_verdict TEXT,
            repeat_probability_pct REAL,
            confidence_pct REAL,
            expected_price_bias TEXT,
            growth_drivers_json TEXT,
            risk_factors_json TEXT,
            thesis TEXT,
            news_summary TEXT,
            days_to_next_earnings INTEGER,
            next_earnings_date TEXT,
            payload_json TEXT,
            PRIMARY KEY (ticker, run_at)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_repeater_ticker ON quarter_repeater_predictions (ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_repeater_verdict ON quarter_repeater_predictions (ai_repeat_verdict)")


def _migration_013_automation_and_institutional(conn: Any) -> None:
    """Automation schedules, breakout movement audit log, and institutional holdings/block deals."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automation_schedules (
            job_id TEXT PRIMARY KEY,
            job_name TEXT NOT NULL,
            category TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            last_run_at TEXT,
            next_run_at TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_duration_s REAL DEFAULT 0,
            total_runs INTEGER NOT NULL DEFAULT 0,
            last_summary TEXT,
            error_message TEXT,
            updated_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS breakout_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            company_name TEXT,
            event_type TEXT NOT NULL,
            from_tier TEXT,
            to_tier TEXT,
            score_before REAL,
            score_after REAL,
            price REAL,
            trigger_price REAL,
            reason TEXT,
            catalyst_impact TEXT,
            created_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_audit_ticker ON breakout_audit_log (ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_audit_time ON breakout_audit_log (created_at DESC)")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            fund_name TEXT NOT NULL,
            fund_type TEXT NOT NULL DEFAULT 'Mutual Fund',
            quarter TEXT NOT NULL,
            shares_held INTEGER NOT NULL DEFAULT 0,
            stake_pct REAL NOT NULL DEFAULT 0.0,
            holding_value_cr REAL DEFAULT 0.0,
            prev_stake_pct REAL,
            action TEXT NOT NULL DEFAULT 'HOLD',
            change_shares INTEGER DEFAULT 0,
            change_pct REAL DEFAULT 0.0,
            avg_price REAL DEFAULT 0.0,
            recent_buy_price REAL DEFAULT 0.0,
            reported_date TEXT,
            created_at TEXT NOT NULL
        )
    """)
    _add_column_if_missing(conn, "institutional_holdings", "avg_price", "REAL DEFAULT 0.0")
    _add_column_if_missing(conn, "institutional_holdings", "recent_buy_price", "REAL DEFAULT 0.0")
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_holdings_ticker ON institutional_holdings (ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_holdings_fund ON institutional_holdings (fund_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_holdings_action ON institutional_holdings (action)")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_block_deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            client_name TEXT NOT NULL,
            deal_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            value_cr REAL NOT NULL,
            pct_equity REAL,
            exchange TEXT NOT NULL DEFAULT 'NSE',
            created_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_deals_ticker ON institutional_block_deals (ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_deals_date ON institutional_block_deals (deal_date DESC)")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS shareholding_patterns (
            ticker TEXT NOT NULL,
            quarter TEXT NOT NULL,
            promoter_pct REAL NOT NULL DEFAULT 0.0,
            fii_pct REAL NOT NULL DEFAULT 0.0,
            dii_mf_pct REAL NOT NULL DEFAULT 0.0,
            public_retail_pct REAL NOT NULL DEFAULT 0.0,
            other_pct REAL NOT NULL DEFAULT 0.0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (ticker, quarter)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shareholding_ticker ON shareholding_patterns (ticker)")
    except Exception:
        pass


def _migration_014_institutional_avg_and_recent_price(conn: Any) -> None:
    """Add avg_price and recent_buy_price columns to institutional_holdings."""
    _add_column_if_missing(conn, "institutional_holdings", "avg_price", "REAL DEFAULT 0.0")
    _add_column_if_missing(conn, "institutional_holdings", "recent_buy_price", "REAL DEFAULT 0.0")


def _migration_015_scanner_candidates_schema(conn: Any) -> None:
    """Ensure scanner_candidates table and all required signal/outcome columns exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scanner_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            universe TEXT NOT NULL,
            category_id TEXT NOT NULL,
            category_name TEXT,
            category_badge TEXT,
            ticker TEXT NOT NULL,
            stock_name TEXT,
            signal_date TEXT,
            signal_price REAL,
            current_price REAL,
            return_pct REAL,
            volume_multiple REAL,
            trigger_level REAL,
            target_price REAL,
            stop_loss REAL,
            confidence_score INTEGER,
            severity TEXT,
            outcome TEXT,
            outcome_label TEXT,
            outcome_badge TEXT,
            expected_horizon TEXT,
            volatility_est TEXT,
            headline TEXT,
            catalyst_summary TEXT,
            why_it_matches TEXT,
            published_at TEXT,
            link TEXT,
            scanned_at TEXT NOT NULL,
            UNIQUE(universe, category_id, ticker)
        )
    """)
    for col, col_type in [
        ("signal_date", "TEXT"),
        ("signal_price", "REAL"),
        ("target_price", "REAL"),
        ("stop_loss", "REAL"),
        ("severity", "TEXT"),
        ("outcome", "TEXT"),
        ("outcome_label", "TEXT"),
        ("outcome_badge", "TEXT"),
    ]:
        _add_column_if_missing(conn, "scanner_candidates", col, col_type)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scanner_univ_cat ON scanner_candidates(universe, category_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scanner_scanned_at ON scanner_candidates(scanned_at DESC)")
    except Exception:
        pass


def _migration_016_automation_schedule_logs_and_flow_controls(conn: Any) -> None:
    """Add execution logs table and dynamic configuration columns to automation_schedules."""
    # Ensure automation_schedules has is_enabled and params_json columns
    for col_def in [
        ("is_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("params_json", "TEXT"),
        ("cron_expression", "TEXT"),
    ]:
        _add_column_if_missing(conn, "automation_schedules", col_def[0], col_def[1])

    # Create persistent execution logs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automation_schedule_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            job_name TEXT,
            category TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_s REAL DEFAULT 0,
            status TEXT NOT NULL,
            summary TEXT,
            error_details TEXT,
            created_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_logs_job_time ON automation_schedule_logs (job_id, started_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_logs_created ON automation_schedule_logs (created_at DESC)")
    except Exception:
        pass


def _migration_017_clean_fabricated_earnings_and_guard_rails(conn: Any) -> None:
    """Clean up synthetic, duplicate, and fabricated earnings records to restore pure source provenance."""
    # 1. Delete derived/synthetic test rows
    try:
        conn.execute("DELETE FROM earnings_history WHERE source IN ('derived_historical_average', 'quarterly_income_stmt_diluted+yfinance')")
    except Exception:
        pass

    # 2. Delete known synthetic date entries
    try:
        conn.execute("DELETE FROM earnings_history WHERE ticker = 'JIOFIN.NS' AND earnings_date IN ('2025-11-10', '2026-02-15', '2026-05-20')")
        conn.execute("DELETE FROM earnings_history WHERE ticker = 'RELIANCE.NS' AND earnings_date = '2026-10-16'")
        conn.execute("DELETE FROM earnings_history WHERE ticker IN ('TCS.NS', 'INFY.NS') AND earnings_date = '2026-08-07'")
    except Exception:
        pass

    # 3. Clean up quarterly_income_stmt duplicates where an authentic yfinance/nse row already exists
    try:
        stmt_rows = conn.execute("SELECT ticker, earnings_date FROM earnings_history WHERE source = 'quarterly_income_stmt'").fetchall()
        for sym, s_ed in stmt_rows:
            # Check if there is an authentic row within 60 days
            auth_row = conn.execute("""
                SELECT earnings_date FROM earnings_history
                WHERE ticker = ? AND source IN ('yfinance', 'nse')
                AND abs(julianday(earnings_date) - julianday(?)) <= 60
            """, (sym, s_ed)).fetchone()
            if auth_row:
                conn.execute("DELETE FROM earnings_history WHERE ticker = ? AND earnings_date = ? AND source = 'quarterly_income_stmt'", (sym, s_ed))
    except Exception:
        pass


def _migration_018_breakout_tracked_signals(conn: Any) -> None:
    """Create permanent breakout_tracked_signals archive table and backfill existing setups."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS breakout_tracked_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            company_name TEXT,
            industry TEXT,
            tier TEXT NOT NULL DEFAULT 'HOT',
            signal_date TEXT NOT NULL,
            signal_price REAL,
            predicted_value REAL,
            breakout_trigger REAL,
            target_price REAL,
            stop_loss REAL,
            risk_reward_ratio REAL,
            composite_score REAL,
            resistance_score REAL,
            volume_score REAL,
            compression_score REAL,
            momentum_score REAL,
            fundamental_score REAL,
            volume_ratio REAL,
            atr_pct REAL,
            pct_from_high REAL,
            avg_quality_score REAL,
            setup_archetype TEXT,
            current_price REAL,
            current_date TEXT,
            realized_return_pct REAL DEFAULT 0.0,
            max_gain_pct REAL DEFAULT 0.0,
            breakout_happened INTEGER DEFAULT 0,
            outcome TEXT DEFAULT 'ACTIVE',
            outcome_label TEXT,
            outcome_badge TEXT,
            days_elapsed INTEGER DEFAULT 0,
            scanned_at TEXT NOT NULL,
            data_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(ticker, signal_date)
        )
    """)
    _add_column_if_missing(conn, "breakout_tracked_signals", "avg_quality_score", "REAL")

    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bk_tracked_date ON breakout_tracked_signals (signal_date DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bk_tracked_ticker ON breakout_tracked_signals (ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bk_tracked_tier ON breakout_tracked_signals (tier)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bk_tracked_score ON breakout_tracked_signals (composite_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bk_tracked_scanned ON breakout_tracked_signals (scanned_at DESC)")
    except Exception:
        pass

    # Backfill from existing breakout_radar if rows exist
    try:
        conn.execute("""
            INSERT OR IGNORE INTO breakout_tracked_signals (
                ticker, company_name, industry, tier, signal_date,
                signal_price, predicted_value, breakout_trigger, target_price, stop_loss,
                risk_reward_ratio, composite_score, resistance_score, volume_score, compression_score,
                momentum_score, fundamental_score, volume_ratio, atr_pct, pct_from_high,
                setup_archetype, current_price, current_date, realized_return_pct, max_gain_pct,
                breakout_happened, outcome, outcome_label, outcome_badge, days_elapsed,
                scanned_at, data_json, created_at, updated_at
            )
            SELECT 
                ticker, company_name, industry, tier, 
                COALESCE(NULLIF(signal_date, ''), SUBSTR(scanned_at, 1, 10), DATE('now')) AS signal_date,
                signal_price, predicted_value, breakout_trigger, target_price, stop_loss,
                risk_reward_ratio, composite_score, resistance_score, volume_score, compression_score,
                momentum_score, fundamental_score, volume_ratio, atr_pct, pct_from_high,
                setup_archetype, current_price, current_date, realized_return_pct, max_gain_pct,
                breakout_happened, outcome, outcome_label, outcome_badge, days_elapsed,
                scanned_at, data_json, created_at, updated_at
            FROM breakout_radar
            WHERE ticker IS NOT NULL 
              AND signal_date >= '2026-08-26'
              AND (breakout_happened = 1 OR signal_price >= breakout_trigger OR current_price >= breakout_trigger OR outcome != 'PENDING')
        """)
    except Exception as e:
        logger.debug("[MIGRATION-018] Backfill from breakout_radar notice: %s", e)


def _migration_019_automation_schedules_market_hours(conn: Any) -> None:
    """Add run_after_hours and market_session controls to automation_schedules table."""
    for col_name, col_type in [
        ("run_after_hours", "INTEGER NOT NULL DEFAULT 1"),
        ("market_session", "TEXT NOT NULL DEFAULT 'all'"),
    ]:
        _add_column_if_missing(conn, "automation_schedules", col_name, col_type)


def _migration_020_breakout_strategy_tracking(conn: Any) -> None:
    """Add strategy column to breakout_radar and breakout_tracked_signals and purge test data."""
    for tbl in ["breakout_radar", "breakout_tracked_signals"]:
        _add_column_if_missing(conn, tbl, "strategy", "TEXT NOT NULL DEFAULT 'CLASSIC_TECHNICAL'")

    # Purge any test/dummy/mock records across tables
    for tbl in ["breakout_radar", "breakout_tracked_signals", "breakout_audit_log", "consensus_predictions", "tickers"]:
        try:
            conn.execute(f"DELETE FROM {tbl} WHERE UPPER(ticker) LIKE '%TEST%' OR UPPER(ticker) LIKE '%MOCK%' OR UPPER(ticker) LIKE '%DUMMY%'")
        except Exception:
            pass

    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_breakout_ticker_strat ON breakout_radar(ticker, strategy)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_breakout_tracked_uniq ON breakout_tracked_signals(ticker, strategy, signal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_strategy ON breakout_radar(strategy)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_tracked_strat ON breakout_tracked_signals(strategy)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_tracked_date ON breakout_tracked_signals(signal_date DESC)")
    except Exception as e:
        logger.debug("[MIGRATION-020] Index creation notice: %s", e)


def _migration_021_sidebar_badge_counters(conn: sqlite3.Connection | TursoConnection) -> None:
    """Create dedicated sidebar_badge_counters table for instant sub-millisecond badge counters."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sidebar_badge_counters (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    try:
        conn.execute("INSERT OR IGNORE INTO sidebar_badge_counters (key, value, updated_at) VALUES ('breaking_out_stocks', 0, datetime('now'))")
        conn.execute("INSERT OR IGNORE INTO sidebar_badge_counters (key, value, updated_at) VALUES ('high_impact_news_70', 0, datetime('now'))")
    except Exception:
        pass


def _migration_022_institutional_amount_metrics(conn: sqlite3.Connection | TursoConnection) -> None:
    """Add increase_amount_cr, total_amount_cr, and recent transaction columns to institutional_holdings."""
    cols = [
        ("increase_amount_cr", "REAL DEFAULT 0.0"),
        ("total_amount_cr", "REAL DEFAULT 0.0"),
        ("recent_txn_price", "REAL DEFAULT 0.0"),
        ("recent_txn_date", "TEXT"),
        ("recent_txn_type", "TEXT"),
    ]
    for c_name, c_type in cols:
        _add_column_if_missing(conn, "institutional_holdings", c_name, c_type)


def _migration_023_news_structured_extraction(conn: sqlite3.Connection | TursoConnection) -> None:
    """Add structured extraction fields (projections, sentiment, temporal originality) to news_catalysts."""
    cols = [
        ("financial_projections", "TEXT DEFAULT '{}'"),
        ("sentiment", "TEXT DEFAULT 'NEUTRAL'"),
        ("temporal_originality", "TEXT DEFAULT 'NEW_PUBLICATION'"),
        ("is_republication", "INTEGER DEFAULT 0"),
        ("originality_rationale", "TEXT DEFAULT ''"),
    ]
    for c_name, c_type in cols:
        _add_column_if_missing(conn, "news_catalysts", c_name, c_type)


def _migration_024_breakout_audit_counter_and_strategy(conn: sqlite3.Connection | TursoConnection) -> None:
    """Add strategy, counter and updated_at to breakout_audit_log and backpopulate historical records."""
    cols = [
        ("strategy", "TEXT NOT NULL DEFAULT 'Classic Technical'"),
        ("counter", "INTEGER NOT NULL DEFAULT 1"),
        ("updated_at", "TEXT"),
    ]
    for c_name, c_type in cols:
        _add_column_if_missing(conn, "breakout_audit_log", c_name, c_type)

    try:
        conn.execute("UPDATE breakout_audit_log SET strategy = 'Classic Technical' WHERE strategy IS NULL OR strategy = '' OR strategy = 'CLASSIC_TECHNICAL'")
        conn.execute("UPDATE breakout_audit_log SET counter = 1 WHERE counter IS NULL OR counter < 1")
        conn.execute("UPDATE breakout_audit_log SET updated_at = created_at WHERE updated_at IS NULL")
    except Exception as e:
        logger.debug("[MIGRATION-024] Backpopulate notice: %s", e)

    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_audit_strat ON breakout_audit_log (strategy)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_audit_ticker_time ON breakout_audit_log (ticker, created_at DESC)")
    except Exception:
        pass


def _migration_025_option_chain_history(conn: Any) -> None:
    """Create option_chain_history table for persisting daily/intraday derivatives snapshots."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_chain_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            spot_price REAL,
            pcr_oi REAL,
            pcr_volume REAL,
            max_pain_strike REAL,
            sentiment TEXT,
            call_oi_total INTEGER,
            put_oi_total INTEGER,
            resistance_strike REAL,
            support_strike REAL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, as_of_date)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_option_chain_sym_date ON option_chain_history (symbol, as_of_date DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_option_chain_date ON option_chain_history (as_of_date DESC)")
    except Exception:
        pass


def _migration_026_institutional_accumulation_cache(conn: Any) -> None:
    """Precomputed summary cache table and composite indexes for ultra fast institutional intelligence queries."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_accumulation_cache (
            ticker TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            market_cap_cr REAL,
            accumulation_score REAL NOT NULL DEFAULT 50.0,
            verdict TEXT NOT NULL,
            verdict_badge TEXT NOT NULL,
            funds_accumulating_count INTEGER NOT NULL DEFAULT 0,
            funds_selling_count INTEGER NOT NULL DEFAULT 0,
            new_funds_bought_count INTEGER NOT NULL DEFAULT 0,
            gross_inflow_cr REAL NOT NULL DEFAULT 0.0,
            gross_outflow_cr REAL NOT NULL DEFAULT 0.0,
            net_flow_cr REAL NOT NULL DEFAULT 0.0,
            inst_addition_pct REAL NOT NULL DEFAULT 0.0,
            increase_amount_cr REAL NOT NULL DEFAULT 0.0,
            total_amount_cr REAL NOT NULL DEFAULT 0.0,
            total_institutional_amount_cr REAL NOT NULL DEFAULT 0.0,
            total_institutional_stake_pct REAL NOT NULL DEFAULT 0.0,
            fii_stake_pct REAL NOT NULL DEFAULT 0.0,
            dii_stake_pct REAL NOT NULL DEFAULT 0.0,
            is_new_fii_entry INTEGER NOT NULL DEFAULT 0,
            is_new_dii_entry INTEGER NOT NULL DEFAULT 0,
            fii_always_held INTEGER NOT NULL DEFAULT 1,
            fii_interest_summary TEXT,
            return_7d_pct REAL,
            return_30d_pct REAL,
            return_1y_pct REAL,
            holdings_json TEXT,
            block_deals_json TEXT,
            shareholding_patterns_json TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_cache_score ON institutional_accumulation_cache (accumulation_score DESC, net_flow_cr DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_cache_selling ON institutional_accumulation_cache (funds_selling_count DESC, gross_outflow_cr DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_cache_addition ON institutional_accumulation_cache (inst_addition_pct DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_cache_net_flow ON institutional_accumulation_cache (net_flow_cr DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_cache_updated ON institutional_accumulation_cache (updated_at DESC)")
        
        # Raw tables composite indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_holdings_action_ticker ON institutional_holdings (action, ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_holdings_ticker_stake ON institutional_holdings (ticker, stake_pct DESC, holding_value_cr DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shareholding_ticker_quarter ON shareholding_patterns (ticker, quarter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_deals_ticker_date ON institutional_block_deals (ticker, deal_date DESC)")
    except Exception:
        pass


def _migration_027_nse_shareholding_freshness(conn: Any) -> None:
    """Create nse_shareholding_freshness table for tracking last fetch timestamp and dynamic discovery of institutional holdings."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nse_shareholding_freshness (
            ticker TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            source TEXT DEFAULT 'nse_api',
            entities_count INTEGER DEFAULT 0
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nse_shp_fresh_fetched ON nse_shareholding_freshness (fetched_at DESC)")
    except Exception:
        pass


def _migration_028_tri_confluence_metrics_cache(conn: Any) -> None:
    """Create tri_confluence_metrics table for persistent SQLite caching of Tri-Factor synergy metrics."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tri_confluence_metrics (
            ticker TEXT PRIMARY KEY,
            clean_ticker TEXT,
            company_name TEXT,
            sector TEXT,
            industry TEXT,
            market TEXT DEFAULT 'IN',
            market_cap REAL DEFAULT 0,
            market_cap_cr REAL DEFAULT 0,
            current_price REAL DEFAULT 0,
            synergy_score REAL DEFAULT 50.0,
            grade TEXT DEFAULT 'B',
            rating_label TEXT,
            rating_badge TEXT,
            status_desc TEXT,
            hit_rate_pct REAL DEFAULT 50.0,
            confluent_quarters INTEGER DEFAULT 0,
            total_quarters INTEGER DEFAULT 0,
            corr_inst_return REAL DEFAULT 0.0,
            corr_surprise_return REAL DEFAULT 0.0,
            corr_inst_surprise REAL DEFAULT 0.0,
            latest_quarter TEXT,
            latest_inst_pct REAL DEFAULT 0.0,
            latest_inst_delta REAL DEFAULT 0.0,
            latest_surprise_pct REAL DEFAULT 0.0,
            latest_return_pct REAL DEFAULT 0.0,
            latest_confluence_aligned INTEGER DEFAULT 0,
            quarters_json TEXT DEFAULT '[]',
            top_holders_json TEXT DEFAULT '[]',
            insights_json TEXT DEFAULT '[]',
            calculated_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tri_conf_score ON tri_confluence_metrics (synergy_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tri_conf_grade ON tri_confluence_metrics (grade)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tri_conf_market ON tri_confluence_metrics (market)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tri_conf_updated ON tri_confluence_metrics (updated_at DESC)")
    except Exception:
        pass


def _migration_029_earnings_fetch_log_schema_alignment(conn: Any) -> None:
    """Align earnings_fetch_log and earnings_month_cache schema with current queries."""
    try:
        cols = _get_table_columns(conn, "earnings_fetch_log")
        if cols and "fetch_date" not in cols:
            conn.execute("DROP TABLE IF EXISTS earnings_fetch_log")
    except Exception:
        pass

    try:
        cols_mc = _get_table_columns(conn, "earnings_month_cache")
        if cols_mc and "payload_json" not in cols_mc:
            conn.execute("DROP TABLE IF EXISTS earnings_month_cache")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_fetch_log (
            fetch_date TEXT NOT NULL PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            events_count INTEGER DEFAULT 0,
            inserted_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_month_cache (
            cache_key TEXT NOT NULL PRIMARY KEY,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
    """)


def _migration_030_ai_model_telemetry_and_api_calls(conn: sqlite3.Connection) -> None:
    """Create AI model telemetry & downstream API calls tracking tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_model_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL,
            model_name TEXT,
            created_at TEXT NOT NULL,
            timestamp REAL NOT NULL,
            latency_ms REAL NOT NULL,
            tokens INTEGER,
            is_local INTEGER DEFAULT 0,
            success INTEGER DEFAULT 1,
            error_message TEXT,
            ticker TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_model ON ai_model_telemetry(model_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON ai_model_telemetry(timestamp)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS downstream_api_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,
            created_at TEXT NOT NULL,
            timestamp REAL NOT NULL,
            status_code INTEGER DEFAULT 200
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_calls_service ON downstream_api_calls(service)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_calls_ts ON downstream_api_calls(timestamp)")


def _migration_031_institutional_verification_and_provenance(conn: Any) -> None:
    """Create data provenance, audit log, and quarantine tables for institutional intelligence integrity."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_provenance_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_url TEXT,
            payload_sha256 TEXT NOT NULL,
            payload_size_bytes INTEGER NOT NULL DEFAULT 0,
            fetch_timestamp TEXT NOT NULL,
            verified_timestamp TEXT,
            is_authentic INTEGER NOT NULL DEFAULT 1,
            quarantine_reason TEXT,
            created_at TEXT NOT NULL DEFAULT (DATETIME('now'))
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_type_key ON data_provenance_meta(record_type, entity_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_sha256 ON data_provenance_meta(payload_sha256)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_fetch ON data_provenance_meta(fetch_timestamp DESC)")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_run_id TEXT NOT NULL,
            audit_timestamp TEXT NOT NULL,
            audit_scope TEXT NOT NULL,
            ticker TEXT,
            check_category TEXT NOT NULL,
            check_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            expected_value TEXT,
            actual_value TEXT,
            deviation_pct REAL,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT (DATETIME('now'))
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_audit_run ON institutional_audit_log(audit_run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_audit_ticker ON institutional_audit_log(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_audit_category ON institutional_audit_log(check_category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_audit_severity ON institutional_audit_log(severity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_audit_ts ON institutional_audit_log(audit_timestamp DESC)")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_quarantine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            source_name TEXT NOT NULL,
            rejection_reason TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            quarantined_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            resolved_at TEXT,
            resolution_status TEXT DEFAULT 'OPEN'
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_quarantine_key ON institutional_quarantine(record_type, entity_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_quarantine_ts ON institutional_quarantine(quarantined_at DESC)")
    except Exception:
        pass


def _migration_032_institutional_radar_signals(conn: Any) -> None:
    """Create table for tracking institutional accumulation radar signal dates, entry prices, and performance."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_radar_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
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
            UNIQUE (ticker, signal_date)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_ticker ON institutional_radar_signals(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_date ON institutional_radar_signals(signal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_active ON institutional_radar_signals(is_active)")
    except Exception:
        pass


def _migration_033_consolidate_breakout_audit_log(conn: Any) -> None:
    """Consolidate duplicate breakout audit log records and prune entries older than 30 days.

    Groups duplicates by (ticker, strategy, event_type, from_tier, to_tier), summing their counter
    values, preserving the earliest created_at and the latest updated_at/price/score, and deletes
    stale redundant transitions caused by multi-strategy scan oscillation.
    """
    # 1. Prune records older than 30 days
    try:
        conn.execute(
            "DELETE FROM breakout_audit_log "
            "WHERE replace(created_at, 'T', ' ') < datetime('now', '-30 days')"
        )
    except Exception as e:
        logger.debug("[MIGRATION-033] Prune old records notice: %s", e)

    # 2. Consolidate duplicate groups into a temporary staging table
    try:
        conn.execute(
            "CREATE TEMP TABLE _breakout_audit_consolidate AS "
            "SELECT "
            "    MAX(id) AS keep_id, "
            "    MIN(created_at) AS earliest_created, "
            "    MAX(COALESCE(updated_at, created_at)) AS latest_updated, "
            "    SUM(COALESCE(counter, 1)) AS total_counter "
            "FROM breakout_audit_log "
            "GROUP BY ticker, COALESCE(strategy, 'Classic Technical'), event_type, "
            "         COALESCE(from_tier, ''), COALESCE(to_tier, '') "
            "HAVING COUNT(*) > 1"
        )

        # Delete older duplicate rows (keeping only MAX(id) per group)
        conn.execute(
            "DELETE FROM breakout_audit_log "
            "WHERE id NOT IN ("
            "    SELECT MAX(id) "
            "    FROM breakout_audit_log "
            "    GROUP BY ticker, COALESCE(strategy, 'Classic Technical'), event_type, "
            "             COALESCE(from_tier, ''), COALESCE(to_tier, '')"
            ")"
        )

        # Update the kept rows with consolidated counter, created_at, updated_at
        conn.execute(
            "UPDATE breakout_audit_log "
            "SET counter = c.total_counter, "
            "    created_at = c.earliest_created, "
            "    updated_at = c.latest_updated "
            "FROM _breakout_audit_consolidate c "
            "WHERE breakout_audit_log.id = c.keep_id"
        )
        conn.execute("DROP TABLE IF EXISTS _breakout_audit_consolidate")
    except Exception as e:
        logger.debug("[MIGRATION-033] Consolidation notice: %s", e)

    # 3. Create high performance composite index for ticker and strategy lookups
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_breakout_audit_ticker_strat "
            "ON breakout_audit_log (ticker, strategy, id DESC)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-033] Index creation notice: %s", e)


def _migration_034_institutional_query_indexes(conn: Any) -> None:
    """Create composite indexes for high-throughput institutional accumulation radar queries."""
    # 1. Institutional block deals composite indexes
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_block_deals_td "
            "ON institutional_block_deals (ticker, deal_date DESC)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_block_deals_td notice: %s", e)

    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inst_block_deals_perf "
            "ON institutional_block_deals (deal_type, value_cr, deal_date)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_inst_block_deals_perf notice: %s", e)

    # 2. Institutional holdings composite indexes
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inst_holdings_tq "
            "ON institutional_holdings (ticker, quarter)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_inst_holdings_tq notice: %s", e)

    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inst_holdings_qr "
            "ON institutional_holdings (quarter, reported_date)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_inst_holdings_qr notice: %s", e)

    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inst_holdings_perf "
            "ON institutional_holdings (action, holding_value_cr)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_inst_holdings_perf notice: %s", e)

    # 3. Shareholding patterns composite indexes
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_shareholding_tq "
            "ON shareholding_patterns (ticker, quarter)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_shareholding_tq notice: %s", e)

    # 4. Institutional radar signals composite indexes
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_signals_ts "
            "ON institutional_radar_signals (ticker, signal_date)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_radar_signals_ts notice: %s", e)

    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inst_radar_signals_perf "
            "ON institutional_radar_signals (ticker, signal_date)"
        )
    except Exception as e:
        logger.debug("[MIGRATION-034] Index idx_inst_radar_signals_perf notice: %s", e)


def _migration_035_purge_non_fno_fo_call_wall(conn: Any) -> None:
    """Purge invalid non-F&O entries from breakout_radar and breakout_tracked_signals for NSE_FO_CALL_WALL strategy."""
    from earnings_engine.data.universe import is_fno_eligible

    for tbl in ["breakout_radar", "breakout_tracked_signals"]:
        try:
            cur = conn.execute(f"SELECT DISTINCT ticker FROM {tbl} WHERE strategy = 'NSE_FO_CALL_WALL'")
            tickers = [r[0] for r in cur.fetchall() if r and r[0]]
            for t in tickers:
                if not is_fno_eligible(t):
                    conn.execute(f"DELETE FROM {tbl} WHERE ticker = ? AND strategy = 'NSE_FO_CALL_WALL'", (t,))
        except Exception as e:
            logger.debug("[MIGRATION-035] Notice for table %s: %s", tbl, e)


def _migration_036_sync_breakout_radar_signal_columns(conn: Any) -> None:
    """Sync stale breakout_radar signal columns (signal_date, signal_price, etc.) from candidate data_json payload."""
    try:
        cur = conn.execute("SELECT ticker, strategy, data_json FROM breakout_radar WHERE data_json IS NOT NULL AND data_json != ''")
        rows = cur.fetchall()
        for ticker, strategy, data_json_str in rows:
            try:
                import json
                d = json.loads(data_json_str)
                if not isinstance(d, dict):
                    continue
                s_date = d.get("signal_date")
                s_price = d.get("signal_price")
                pred_val = d.get("predicted_value")
                trigger = d.get("breakout_trigger")
                target = d.get("target_price")
                sl = d.get("stop_loss")

                if s_date:
                    conn.execute("""
                        UPDATE breakout_radar
                        SET signal_date = ?,
                            signal_price = COALESCE(?, signal_price),
                            predicted_value = COALESCE(?, predicted_value),
                            breakout_trigger = COALESCE(?, breakout_trigger),
                            target_price = COALESCE(?, target_price),
                            stop_loss = COALESCE(?, stop_loss)
                        WHERE ticker = ? AND strategy = ?
                    """, (s_date, s_price, pred_val, trigger, target, sl, ticker, strategy))
            except Exception as row_err:
                logger.debug("[MIGRATION-036] Row update notice for %s %s: %s", ticker, strategy, row_err)
    except Exception as e:
        logger.debug("[MIGRATION-036] Execution notice: %s", e)


def _migration_037_breakout_late_detection_fields(conn: Any) -> None:
    """Add ideal_entry_price, is_late, and entry_delay_pct fields to breakout_radar and breakout_tracked_signals."""
    for tbl in ["breakout_radar", "breakout_tracked_signals"]:
        _add_column_if_missing(conn, tbl, "ideal_entry_price", "REAL")
        _add_column_if_missing(conn, tbl, "is_late", "INTEGER DEFAULT 0")
        _add_column_if_missing(conn, tbl, "entry_delay_pct", "REAL DEFAULT 0.0")

    # Backfill late detection metrics from existing data_json payloads where available
    # Note: breakout_radar has composite primary key (ticker, strategy), while breakout_tracked_signals has integer primary key (id).
    # 1. Backfill breakout_radar
    try:
        cur = conn.execute("SELECT ticker, strategy, signal_price, breakout_trigger, data_json FROM breakout_radar WHERE data_json IS NOT NULL AND data_json != ''")
        rows = cur.fetchall()
        for ticker, strat, sig_p, trig_p, d_json in rows:
            try:
                import json
                d = json.loads(d_json)
                if not isinstance(d, dict):
                    continue
                notes = d.get("calculation_notes") or {}
                ideal_p = d.get("ideal_entry_price") or notes.get("ideal_entry_price")
                if ideal_p is None:
                    ideal_p = trig_p

                if ideal_p is not None:
                    ideal_p = round(float(ideal_p), 2)
                    s_price = float(sig_p) if sig_p is not None else float(d.get("signal_price", 0) or 0)
                    t_trigger = float(trig_p) if trig_p is not None else float(d.get("breakout_trigger", 0) or 0)

                    is_late_val = 1 if (
                        (t_trigger > 0 and s_price >= t_trigger)
                        or (ideal_p > 0 and s_price > ideal_p * 1.002)
                    ) else 0

                    delay_pct = round(((s_price - ideal_p) / ideal_p) * 100, 2) if (is_late_val and ideal_p > 0) else 0.0

                    conn.execute(
                        "UPDATE breakout_radar SET ideal_entry_price = ?, is_late = ?, entry_delay_pct = ? WHERE ticker = ? AND strategy = ?",
                        (ideal_p, is_late_val, delay_pct, ticker, strat),
                    )
            except Exception:
                continue
    except Exception as e:
        logger.debug("[MIGRATION-037] Backfill notice for breakout_radar: %s", e)

    # 2. Backfill breakout_tracked_signals
    try:
        cur = conn.execute("SELECT id, ticker, signal_price, breakout_trigger, data_json FROM breakout_tracked_signals WHERE data_json IS NOT NULL AND data_json != ''")
        rows = cur.fetchall()
        for r_id, ticker, sig_p, trig_p, d_json in rows:
            try:
                import json
                d = json.loads(d_json)
                if not isinstance(d, dict):
                    continue
                notes = d.get("calculation_notes") or {}
                ideal_p = d.get("ideal_entry_price") or notes.get("ideal_entry_price")
                if ideal_p is None:
                    ideal_p = trig_p

                if ideal_p is not None:
                    ideal_p = round(float(ideal_p), 2)
                    s_price = float(sig_p) if sig_p is not None else float(d.get("signal_price", 0) or 0)
                    t_trigger = float(trig_p) if trig_p is not None else float(d.get("breakout_trigger", 0) or 0)

                    is_late_val = 1 if (
                        (t_trigger > 0 and s_price >= t_trigger)
                        or (ideal_p > 0 and s_price > ideal_p * 1.002)
                    ) else 0

                    delay_pct = round(((s_price - ideal_p) / ideal_p) * 100, 2) if (is_late_val and ideal_p > 0) else 0.0

                    conn.execute(
                        "UPDATE breakout_tracked_signals SET ideal_entry_price = ?, is_late = ?, entry_delay_pct = ? WHERE id = ?",
                        (ideal_p, is_late_val, delay_pct, r_id),
                    )
            except Exception:
                continue
    except Exception as e:
        logger.debug("[MIGRATION-037] Backfill notice for breakout_tracked_signals: %s", e)



def _migration_038_alert_rules_engine(conn: Any) -> None:
    """Create alert_rules and alert_rule_logs tables for custom multi-channel notifications."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            strategy TEXT DEFAULT 'ALL',
            min_score REAL DEFAULT 70.0,
            min_volume_surge REAL DEFAULT 1.5,
            tier TEXT DEFAULT 'ALL',
            target_universe TEXT DEFAULT 'ALL',
            max_entry_delay_pct REAL DEFAULT 3.0,
            actions_json TEXT NOT NULL DEFAULT '["browser"]',
            webhook_url TEXT,
            email_recipients TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_triggered_at TEXT,
            trigger_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_rule_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            strategy TEXT,
            score REAL,
            volume_surge REAL,
            channels_dispatched TEXT,
            status TEXT NOT NULL,
            details TEXT,
            triggered_at TEXT NOT NULL,
            FOREIGN KEY(rule_id) REFERENCES alert_rules(id) ON DELETE CASCADE
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_active ON alert_rules(is_active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_rule_logs_rule ON alert_rule_logs(rule_id, triggered_at)")
    except Exception:
        pass


def _migration_039_strategy_tier_audit_and_swing_radar(conn: Any) -> None:
    """Create universal strategy_tier_audit_log and swing_radar tables for graduated tier pooling."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_tier_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            ticker TEXT NOT NULL,
            company_name TEXT,
            strategy TEXT NOT NULL DEFAULT 'DEFAULT',
            event_type TEXT NOT NULL,
            from_tier TEXT,
            to_tier TEXT,
            score_before REAL,
            score_after REAL,
            price REAL,
            trigger_price REAL,
            target_price REAL,
            stop_loss REAL,
            risk_reward_ratio REAL,
            volume_ratio REAL,
            reason TEXT,
            catalyst_impact TEXT,
            counter INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strat_tier_audit_dt ON strategy_tier_audit_log (domain, ticker, strategy, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strat_tier_audit_ds ON strategy_tier_audit_log (domain, strategy, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strat_tier_audit_created ON strategy_tier_audit_log (created_at DESC)")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS swing_radar (
            ticker TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'WARM',
            composite_score REAL NOT NULL DEFAULT 0.0,
            swing_signal TEXT,
            channel_lower REAL,
            channel_upper REAL,
            dist_to_support_pct REAL,
            dist_to_resistance_pct REAL,
            risk_reward_ratio REAL,
            current_price REAL,
            data_json TEXT,
            scanned_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (ticker)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_radar_tier ON swing_radar (tier)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_radar_score ON swing_radar (composite_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_radar_scanned ON swing_radar (scanned_at DESC)")
    except Exception:
        pass


def _migration_040_purge_invalid_price_history_nan_records(conn: Any) -> None:
    """Purge corrupt, null, and non-positive close records from price_history table."""
    try:
        conn.execute("DELETE FROM price_history WHERE close IS NULL OR close <= 0")
        conn.execute("DELETE FROM price_history WHERE open IS NULL AND high IS NULL AND low IS NULL AND close IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date_close ON price_history(ticker, date, close)")
    except Exception as e:
        logger.debug("[MIGRATION-040] Price history purge notice: %s", e)


# Migration Registry (ordered by version)
MIGRATIONS: list[Migration] = [
    Migration(1, "001_core_schema", _migration_001_core_schema),
    Migration(2, "002_swing_ranges", _migration_002_swing_ranges),
    Migration(3, "003_multimodal_ai", _migration_003_multimodal_ai),
    Migration(4, "004_ticker_audit", _migration_004_ticker_audit),
    Migration(5, "005_unified_tickers", _migration_005_unified_tickers),
    Migration(6, "006_drop_legacy_ticker_tables", _migration_006_drop_legacy_ticker_tables),
    Migration(7, "007_consolidate_earnings_and_freshness", _migration_007_consolidate_earnings_and_freshness),
    Migration(8, "008_passcodes", _migration_008_passcodes),
    Migration(9, "009_rbac_and_scoped_access", _migration_009_rbac_and_scoped_access),
    Migration(10, "010_credit_cards_and_otp_requests", _migration_010_credit_cards_and_otp_requests),
    Migration(11, "011_trips_and_net_worth_expansion", _migration_011_trips_and_net_worth_expansion),
    Migration(12, "012_quarter_repeater_predictions", _migration_012_quarter_repeaters),
    Migration(13, "013_automation_schedules_and_institutional_hub", _migration_013_automation_and_institutional),
    Migration(14, "014_institutional_avg_and_recent_price", _migration_014_institutional_avg_and_recent_price),
    Migration(15, "015_scanner_candidates_schema", _migration_015_scanner_candidates_schema),
    Migration(16, "016_automation_schedule_logs_and_flow_controls", _migration_016_automation_schedule_logs_and_flow_controls),
    Migration(17, "017_clean_fabricated_earnings_and_guard_rails", _migration_017_clean_fabricated_earnings_and_guard_rails),
    Migration(18, "018_breakout_tracked_signals", _migration_018_breakout_tracked_signals),
    Migration(19, "019_automation_schedules_market_hours", _migration_019_automation_schedules_market_hours),
    Migration(20, "020_breakout_strategy_tracking", _migration_020_breakout_strategy_tracking),
    Migration(21, "021_sidebar_badge_counters", _migration_021_sidebar_badge_counters),
    Migration(22, "022_institutional_amount_metrics", _migration_022_institutional_amount_metrics),
    Migration(23, "023_news_structured_extraction", _migration_023_news_structured_extraction),
    Migration(24, "024_breakout_audit_counter_and_strategy", _migration_024_breakout_audit_counter_and_strategy),
    Migration(25, "025_option_chain_history", _migration_025_option_chain_history),
    Migration(26, "026_institutional_accumulation_cache", _migration_026_institutional_accumulation_cache),
    Migration(27, "027_nse_shareholding_freshness", _migration_027_nse_shareholding_freshness),
    Migration(28, "028_tri_confluence_metrics_cache", _migration_028_tri_confluence_metrics_cache),
    Migration(29, "029_earnings_fetch_log_schema_alignment", _migration_029_earnings_fetch_log_schema_alignment),
    Migration(30, "030_ai_model_telemetry_and_api_calls", _migration_030_ai_model_telemetry_and_api_calls),
    Migration(31, "031_institutional_verification_and_provenance", _migration_031_institutional_verification_and_provenance),
    Migration(32, "032_institutional_radar_signals", _migration_032_institutional_radar_signals),
    Migration(33, "033_consolidate_breakout_audit_log", _migration_033_consolidate_breakout_audit_log),
    Migration(34, "034_institutional_query_indexes", _migration_034_institutional_query_indexes),
    Migration(35, "035_purge_non_fno_fo_call_wall", _migration_035_purge_non_fno_fo_call_wall),
    Migration(36, "036_sync_breakout_radar_signal_columns", _migration_036_sync_breakout_radar_signal_columns),
    Migration(37, "037_breakout_late_detection_fields", _migration_037_breakout_late_detection_fields),
    Migration(38, "038_alert_rules_engine", _migration_038_alert_rules_engine),
    Migration(39, "039_strategy_tier_audit_and_swing_radar", _migration_039_strategy_tier_audit_and_swing_radar),
    Migration(40, "040_purge_invalid_price_history_nan_records", _migration_040_purge_invalid_price_history_nan_records),
]


_APPLIED_DBS: set[str] = set()


def reset_migration_cache() -> None:
    """Clear in-memory migration tracking cache."""
    _APPLIED_DBS.clear()


def apply_migrations(settings: Settings | None = None, force: bool = False) -> list[str]:
    """Execute all pending database migrations in order."""
    settings = settings or Settings()
    db_key = str(getattr(settings, "db_path", ""))
    if not force and db_key and db_key in _APPLIED_DBS:
        return []

    conn = get_db_connection(settings)
    applied_names: list[str] = []

    try:
        # 1. Ensure migrations ledger exists
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            conn.commit()

        # 2. Get set of already applied migration versions
        with conn:
            applied_rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
            applied_versions = {r[0] for r in applied_rows}

            # Auto-baseline: if schema_migrations was just created on an existing database
            # that already contains core tables (price_history), baseline migrations 1-4
            if not applied_versions:
                try:
                    check_row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'").fetchone()
                    if check_row:
                        now_str = datetime.now().isoformat(timespec="seconds")
                        for v, n in [(1, "001_core_schema"), (2, "002_swing_ranges"), (3, "003_multimodal_ai"), (4, "004_ticker_audit")]:
                            conn.execute("INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)", (v, n, now_str))
                        conn.commit()
                        applied_versions.update({1, 2, 3, 4})
                except Exception:
                    pass

        for migration in MIGRATIONS:
            if migration.version in applied_versions:
                continue

            logger.info("Applying database migration %d: %s...", migration.version, migration.name)
            now_str = datetime.now().isoformat(timespec="seconds")
            try:
                with conn:
                    migration.up(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (migration.version, migration.name, now_str),
                    )
                    conn.commit()
                applied_names.append(migration.name)
                logger.info("✅ Migration %s applied successfully.", migration.name)
            except Exception as e:
                logger.warning("Migration %s encountered error: %s (recording as baseline)", migration.name, e)
                try:
                    with conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                            (migration.version, migration.name, now_str),
                        )
                        conn.commit()
                except Exception:
                    pass

        if db_key:
            _APPLIED_DBS.add(db_key)

        return applied_names
    finally:
        try:
            conn.close()
        except Exception:
            pass
