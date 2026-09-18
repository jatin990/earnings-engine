"""
earnings_engine/services/deals_service.py
Service layer for Point-in-Time (PIT) block/bulk deals and windowed institutional inflows.
"""
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from earnings_engine.common.symbols import normalize_symbol
from earnings_engine.config import Settings
from earnings_engine.data.db import _cache_path


def _get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = db_path or str(_cache_path(Settings()))
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_candidate_symbols(symbol: str) -> List[str]:
    clean = normalize_symbol(symbol)
    if not clean:
        return []
    return list(dict.fromkeys([clean, f"{clean}.NS", f"{clean}.BO", symbol.strip().upper()]))


def get_stock_block_deals(
    db_path: Optional[str] = None,
    symbol: str = "",
    asof_date: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Retrieves normalized bulk and block deals for a given symbol adhering strictly
    to Point-in-Time (PIT) boundaries (deal_date <= asof_date).
    """
    candidate_symbols = _get_candidate_symbols(symbol)
    if not candidate_symbols:
        return []

    clean_symbol = candidate_symbols[0]

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        # Check which deal table is present
        table_name = None
        symbol_col = "symbol"
        bs_col = "buy_sell"
        price_col = "trade_price"
        qty_col = "quantity"
        client_col = "client_name"
        deal_type_col = "deal_type"
        exchange_col = "exchange"

        if "bulk_block_deals" in tables:
            table_name = "bulk_block_deals"
            cols = [col[1] for col in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
            symbol_col = "symbol" if "symbol" in cols else "ticker"
            bs_col = "buy_sell" if "buy_sell" in cols else "deal_type"
            price_col = "trade_price" if "trade_price" in cols else "price"
        elif "institutional_block_deals" in tables:
            table_name = "institutional_block_deals"
            cols = [col[1] for col in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
            symbol_col = "ticker" if "ticker" in cols else "symbol"
            bs_col = "deal_type" if "deal_type" in cols else "buy_sell"
            price_col = "price" if "price" in cols else "trade_price"
        else:
            return []

        placeholders = ",".join(["?"] * len(candidate_symbols))
        query = f"""
            SELECT
                deal_date,
                {symbol_col} AS sym,
                {client_col} AS client,
                {bs_col} AS bs,
                {qty_col} AS qty,
                {price_col} AS prc,
                {deal_type_col} AS dtype,
                {exchange_col} AS exch
            FROM {table_name}
            WHERE {symbol_col} IN ({placeholders})
        """
        params: list = list(candidate_symbols)

        if asof_date:
            query += " AND deal_date <= ?"
            params.append(asof_date)

        query += " ORDER BY deal_date DESC, rowid DESC LIMIT ?"
        params.append(limit)

        rows = cursor.execute(query, params).fetchall()

    normalized_deals: List[Dict[str, Any]] = []
    for r in rows:
        bs_raw = str(r["bs"]).strip().upper() if r["bs"] else ""
        direction = "BUY" if bs_raw in ("BUY", "B", "1") else "SELL"

        qty = int(r["qty"] or 0)
        price = float(r["prc"] or 0.0)
        value_cr = round((qty * price) / 1e7, 2)
        client = (r["client"] or "Unknown Participant").strip()

        normalized_deals.append({
            "deal_date": str(r["deal_date"]),
            "symbol": clean_symbol,
            "ticker": clean_symbol,
            "client_name": client,
            "direction": direction,
            "buy_sell": direction,
            "buyer_name": client if direction == "BUY" else None,
            "seller_name": client if direction == "SELL" else None,
            "quantity": qty,
            "trade_price": price,
            "price": price,
            "value_cr": value_cr,
            "deal_type": str(r["dtype"] or "BLOCK").upper(),
            "exchange": str(r["exch"] or "NSE").upper(),
        })

    return normalized_deals


def get_institutional_inflow_metrics(
    db_path: Optional[str] = None,
    symbol: str = "",
    asof_date: Optional[str] = None,
    horizon_days: int = 30,
) -> Dict[str, Any]:
    """
    Computes Point-in-Time institutional inflow metrics with explicit horizon window.
    Window: [asof_date - horizon_days, asof_date]
    """
    candidate_symbols = _get_candidate_symbols(symbol)
    if not candidate_symbols:
        return {
            "symbol": symbol,
            "asof_date": asof_date or datetime.utcnow().strftime("%Y-%m-%d"),
            "horizon_days": horizon_days,
            "total_buy_cr": 0.0,
            "total_sell_cr": 0.0,
            "net_inflow_cr": 0.0,
            "total_deals": 0,
            "sentiment": "NEUTRAL",
        }

    clean_symbol = candidate_symbols[0]

    if asof_date is None:
        target_date = datetime.utcnow().date()
    else:
        target_date = datetime.strptime(asof_date, "%Y-%m-%d").date()

    start_date = (target_date - timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    asof_str = target_date.strftime("%Y-%m-%d")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        table_name = None
        symbol_col = "symbol"
        bs_col = "buy_sell"
        price_col = "trade_price"
        qty_col = "quantity"

        if "bulk_block_deals" in tables:
            table_name = "bulk_block_deals"
            cols = [col[1] for col in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
            symbol_col = "symbol" if "symbol" in cols else "ticker"
            bs_col = "buy_sell" if "buy_sell" in cols else "deal_type"
            price_col = "trade_price" if "trade_price" in cols else "price"
        elif "institutional_block_deals" in tables:
            table_name = "institutional_block_deals"
            cols = [col[1] for col in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
            symbol_col = "ticker" if "ticker" in cols else "symbol"
            bs_col = "deal_type" if "deal_type" in cols else "buy_sell"
            price_col = "price" if "price" in cols else "trade_price"
        else:
            return {
                "symbol": clean_symbol,
                "asof_date": asof_str,
                "horizon_days": horizon_days,
                "window_start": start_date,
                "total_buy_cr": 0.0,
                "total_sell_cr": 0.0,
                "net_inflow_cr": 0.0,
                "total_deals": 0,
                "sentiment": "NEUTRAL",
            }

        placeholders = ",".join(["?"] * len(candidate_symbols))
        query = f"""
            SELECT
                deal_date,
                {bs_col} AS bs,
                {qty_col} AS qty,
                {price_col} AS prc
            FROM {table_name}
            WHERE {symbol_col} IN ({placeholders})
              AND deal_date >= ?
              AND deal_date <= ?
        """
        params = list(candidate_symbols) + [start_date, asof_str]
        rows = cursor.execute(query, params).fetchall()

    total_buy_cr = 0.0
    total_sell_cr = 0.0

    for r in rows:
        bs_raw = str(r["bs"]).strip().upper() if r["bs"] else ""
        qty = float(r["qty"] or 0)
        price = float(r["prc"] or 0.0)
        val_cr = (qty * price) / 1e7

        if bs_raw in ("BUY", "B", "1"):
            total_buy_cr += val_cr
        else:
            total_sell_cr += val_cr

    net_inflow_cr = round(total_buy_cr - total_sell_cr, 2)
    sentiment = "ACCUMULATION" if net_inflow_cr > 0 else ("DISTRIBUTION" if net_inflow_cr < 0 else "NEUTRAL")

    return {
        "symbol": clean_symbol,
        "asof_date": asof_str,
        "horizon_days": horizon_days,
        "window_start": start_date,
        "total_buy_cr": round(total_buy_cr, 2),
        "total_sell_cr": round(total_sell_cr, 2),
        "net_inflow_cr": net_inflow_cr,
        "total_deals": len(rows),
        "sentiment": sentiment,
    }
