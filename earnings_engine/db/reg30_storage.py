"""
Database schema & storage operations for SEBI Reg 30 High-Impact Disclosures.
"""

import sqlite3
import os
from typing import List, Dict, Any, Optional
from earnings_engine.config import Settings
from earnings_engine.data.db import _cache_path


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or str(_cache_path(Settings()))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_reg30_db(conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None):
    """Initializes the reg30_disclosures table and indexes."""
    close_on_exit = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_on_exit = True

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reg30_disclosures (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            bse_code TEXT,
            company_name TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            category TEXT NOT NULL,
            category_name TEXT NOT NULL,
            sentiment TEXT NOT NULL,
            impact_level TEXT NOT NULL,
            headline TEXT NOT NULL,
            description TEXT,
            order_value_cr REAL,
            pdf_url TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'BSE',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg30_timestamp ON reg30_disclosures(timestamp DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg30_symbol ON reg30_disclosures(symbol);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg30_category ON reg30_disclosures(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reg30_sentiment ON reg30_disclosures(sentiment);")
    conn.commit()

    if close_on_exit:
        conn.close()


def insert_reg30_disclosure(
    disclosure: Dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Inserts a single disclosure ignoring duplicates based on primary key id."""
    return store_reg30_disclosures([disclosure], conn=conn, db_path=db_path) > 0


def store_reg30_disclosures(
    disclosures: List[Dict[str, Any]],
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str] = None,
) -> int:
    """Inserts disclosures ignoring duplicates based on primary key id."""
    if not disclosures:
        return 0

    close_on_exit = False
    if conn is None:
        init_reg30_db(db_path=db_path)
        conn = get_db_connection(db_path)
        close_on_exit = True
    else:
        init_reg30_db(conn=conn)

    cursor = conn.cursor()

    query = """
        INSERT OR IGNORE INTO reg30_disclosures (
            id, symbol, bse_code, company_name, timestamp, category, category_name,
            sentiment, impact_level, headline, description, order_value_cr, pdf_url, source
        ) VALUES (
            :id, :symbol, :bse_code, :company_name, :timestamp, :category, :category_name,
            :sentiment, :impact_level, :headline, :description, :order_value_cr, :pdf_url, :source
        )
    """

    cursor.executemany(query, disclosures)
    conn.commit()
    inserted_count = cursor.rowcount

    if close_on_exit:
        conn.close()

    return inserted_count


def fetch_reg30_stream(
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    impact_level: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieves paginated, filtered Reg 30 disclosures sorted by timestamp descending."""
    close_on_exit = False
    if conn is None:
        init_reg30_db(db_path=db_path)
        conn = get_db_connection(db_path)
        close_on_exit = True
    else:
        init_reg30_db(conn=conn)

    cursor = conn.cursor()

    query = "SELECT * FROM reg30_disclosures WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if sentiment:
        query += " AND sentiment = ?"
        params.append(sentiment)
    if impact_level:
        query += " AND impact_level = ?"
        params.append(impact_level)
    if symbol:
        query += " AND (symbol = ? OR symbol LIKE ? OR company_name LIKE ?)"
        params.extend([symbol, f"%{symbol}%", f"%{symbol}%"])

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    results = [dict(row) for row in rows]

    if close_on_exit:
        conn.close()

    return results


def fetch_reg30_stats(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns aggregate metrics for category and sentiment breakdown."""
    close_on_exit = False
    if conn is None:
        init_reg30_db(db_path=db_path)
        conn = get_db_connection(db_path)
        close_on_exit = True
    else:
        init_reg30_db(conn=conn)

    cursor = conn.cursor()

    cursor.execute("SELECT sentiment, COUNT(*) as count FROM reg30_disclosures GROUP BY sentiment")
    sentiment_counts = {row["sentiment"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("SELECT category, category_name, COUNT(*) as count FROM reg30_disclosures GROUP BY category")
    category_counts = [{ "category": row["category"], "name": row["category_name"], "count": row["count"] } for row in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) as total FROM reg30_disclosures")
    total = cursor.fetchone()["total"]

    if close_on_exit:
        conn.close()

    return {
        "total_disclosures": total,
        "by_sentiment": sentiment_counts,
        "by_category": category_counts,
    }
