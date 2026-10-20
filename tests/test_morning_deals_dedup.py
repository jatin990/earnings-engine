"""Unit tests for Morning Setups deals deduplication, normalization, and trade pairing."""

from unittest.mock import patch, MagicMock
from earnings_engine.data.morning_setups import (
    clean_client_name,
    pair_bilateral_deals,
    group_deals_by_symbol,
    build_institutional_tags,
    sync_all_morning_deals,
)
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import _migration_046_morning_setups_deals_and_board_meetings


def test_clean_client_name_normalization():
    # Verify standard legal entity and punctuation normalization
    raw_1 = "BOFA SECURITIES EUROPE SA."
    raw_2 = "BOFA SECURITIES EUROPE SA"
    raw_3 = "  MORGAN STANLEY ASIA (SINGAPORE) PTE.  "
    raw_4 = "MORGAN STANLEY ASIA SINGAPORE PTE"

    assert clean_client_name(raw_1) == "BOFA SECURITIES EUROPE SA"
    assert clean_client_name(raw_2) == "BOFA SECURITIES EUROPE SA"
    assert clean_client_name(raw_3) == "MORGAN STANLEY ASIA SINGAPORE PTE"
    assert clean_client_name(raw_4) == "MORGAN STANLEY ASIA SINGAPORE PTE"


def test_bilateral_trade_pairing():
    # Two complementary legs: one BUY and one SELL for same stock, date, qty, and price
    deals = [
        {
            "id": 1,
            "deal_date": "2026-10-15",
            "ticker": "ETERNAL.NS",
            "client_name": "BOFA SECURITIES EUROPE SA",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 5337584,
            "trade_price": 316.0,
            "value_cr": 168.67,
        },
        {
            "id": 2,
            "deal_date": "2026-10-15",
            "ticker": "ETERNAL.NS",
            "client_name": "GOLDMAN SACHS BANK EUROPE SE ODI",
            "deal_type": "BLOCK",
            "transaction_type": "SELL",
            "quantity": 5337584,
            "trade_price": 316.0,
            "value_cr": 168.67,
        },
        {
            "id": 3,
            "deal_date": "2026-10-15",
            "ticker": "RELIANCE.NS",
            "client_name": "RELIANCE MUTUAL FUND",
            "deal_type": "BULK",
            "transaction_type": "BUY",
            "quantity": 100000,
            "trade_price": 1200.0,
            "value_cr": 12.0,
        },
    ]

    paired = pair_bilateral_deals(deals)
    assert len(paired) == 3

    # Check that legs 1 and 2 are matched to each other
    leg_1 = next(d for d in paired if d["id"] == 1)
    leg_2 = next(d for d in paired if d["id"] == 2)
    leg_3 = next(d for d in paired if d["id"] == 3)

    assert leg_1["is_matched_cross"] is True
    assert leg_1["counterparty_name"] == "GOLDMAN SACHS BANK EUROPE SE ODI"
    assert leg_1["deal_nature"] == "MATCHED_CROSS"

    assert leg_2["is_matched_cross"] is True
    assert leg_2["counterparty_name"] == "BOFA SECURITIES EUROPE SA"
    assert leg_2["deal_nature"] == "MATCHED_CROSS"

    assert leg_3["is_matched_cross"] is False
    assert leg_3["counterparty_name"] is None
    assert leg_3["deal_nature"] == "OPEN_MARKET_ACCUMULATION"


def test_group_deals_by_symbol_cross_detection():
    # Deals where Fund A buys and Fund B sells identical value -> pure cross trade
    deals = [
        {
            "id": 1,
            "deal_date": "2026-10-15",
            "ticker": "ETERNAL.NS",
            "symbol": "ETERNAL",
            "security_name": "ETERNAL LIMITED",
            "client_name": "BOFA SECURITIES EUROPE SA",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 5000000,
            "trade_price": 300.0,
            "value_cr": 150.0,
            "is_matched_cross": True,
            "counterparty_name": "GOLDMAN SACHS",
            "deal_nature": "MATCHED_CROSS",
        },
        {
            "id": 2,
            "deal_date": "2026-10-15",
            "ticker": "ETERNAL.NS",
            "symbol": "ETERNAL",
            "security_name": "ETERNAL LIMITED",
            "client_name": "GOLDMAN SACHS",
            "deal_type": "BLOCK",
            "transaction_type": "SELL",
            "quantity": 5000000,
            "trade_price": 300.0,
            "value_cr": 150.0,
            "is_matched_cross": True,
            "counterparty_name": "BOFA SECURITIES EUROPE SA",
            "deal_nature": "MATCHED_CROSS",
        },
    ]

    grouped = group_deals_by_symbol(deals)
    assert len(grouped) == 1
    g = grouped[0]
    assert g["ticker"] == "ETERNAL.NS"
    assert g["gross_buy_cr"] == 150.0
    assert g["gross_sell_cr"] == 150.0
    assert g["net_value_cr"] == 0.0
    assert g["is_pure_cross"] is True
    assert g["flow_posture"] == "MATCHED_CROSS"


def test_placeholder_deshadowing_and_client_normalization(tmp_path):
    settings = Settings()
    settings.data_dirs["prices"] = tmp_path
    settings.ensure_dirs()

    conn = get_db_connection(settings)
    _migration_046_morning_setups_deals_and_board_meetings(conn)

    # Insert provisional live placeholder
    conn.execute("""
        INSERT INTO morning_block_deals (
            deal_date, ticker, security_name, client_name, deal_type,
            transaction_type, quantity, trade_price, value_cr, source,
            created_at, updated_at
        ) VALUES (
            '2026-10-15', 'TRENT.NS', 'TRENT LIMITED', 'NSE Block Window (Window 1)', 'BLOCK',
            'BUY', 50000, 5000.0, 25.0, 'NSE_LIVE',
            '2026-10-15T09:15:00', '2026-10-15T09:15:00'
        )
    """)
    conn.commit()

    # Official settled CSV record
    mock_official = [
        {
            "deal_date": "2026-10-15",
            "ticker": "TRENT.NS",
            "security_name": "TRENT LIMITED",
            "client_name": "MORGAN STANLEY ASIA (SINGAPORE) PTE.",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 50000,
            "trade_price": 5000.0,
            "value_cr": 25.0,
            "source": "NSE",
        }
    ]
    # Live provisional record arriving concurrently
    mock_live = [
        {
            "deal_date": "2026-10-15",
            "ticker": "TRENT.NS",
            "security_name": "TRENT LIMITED",
            "client_name": "NSE Block Window (Window 1)",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 50000,
            "trade_price": 5000.0,
            "value_cr": 25.0,
            "source": "NSE_LIVE",
        }
    ]

    with patch("earnings_engine.data.morning_setups.fetch_and_parse_deals_csv", side_effect=[[], mock_official]), \
         patch("earnings_engine.data.morning_setups.fetch_live_block_deals_api", return_value=mock_live), \
         patch("earnings_engine.data.morning_setups.fetch_live_bulk_deals_api", return_value=[]):
        res = sync_all_morning_deals(settings)

    rows = conn.execute("SELECT client_name FROM morning_block_deals WHERE ticker = 'TRENT.NS'").fetchall()
    client_names = [r[0] for r in rows]

    # Official settled client should be normalized and present
    assert "MORGAN STANLEY ASIA SINGAPORE PTE" in client_names
    # Generic provisional placeholder should be purged/de-shadowed
    assert "NSE Block Window (Window 1)" not in client_names
    assert len(client_names) == 1


def test_morning_setups_institutional_tags():
    # 1. Matched cross deal
    tags_cross = build_institutional_tags(
        ticker="TRENT.NS",
        deal={"is_matched_cross": True, "deal_nature": "MATCHED_CROSS"},
        technical_info={"drawdown_52w_pct": -1.2, "breakout": {"is_breakout_active": True}},
    )
    tag_ids = [t["id"] for t in tags_cross]
    assert "MATCHED_CROSS" in tag_ids
    assert "BREAKOUT_ACTIVE" in tag_ids
    assert "TESTING_52W_HIGH" in tag_ids

    # 2. Upcoming result
    tags_res = build_institutional_tags(
        ticker="RELIANCE.NS",
        deal={"is_matched_cross": False, "deal_nature": "OPEN_MARKET_ACCUMULATION"},
        technical_info={
            "drawdown_52w_pct": -15.0,
            "upcoming_result": {"has_upcoming_result": True, "days_until": 4},
        },
    )
    tag_ids_res = [t["id"] for t in tags_res]
    assert "UPCOMING_RESULT" in tag_ids_res
    assert "MATCHED_CROSS" not in tag_ids_res
    res_tag = next(t for t in tags_res if t["id"] == "UPCOMING_RESULT")
    assert "4D" in res_tag["label"]

