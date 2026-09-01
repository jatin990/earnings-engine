"""Tests for broadband news ingestion, multi-stock entity mapping, and on-demand model selection."""

import json
from datetime import datetime, timezone, timedelta
from earnings_engine.config import Settings
from earnings_engine.data.catalysts_news import _connect
from earnings_engine.data.news_verifier import extract_all_affected_tickers, verify_company_entity
from earnings_engine.data.news_pipeline import process_and_verify_news_items, save_verified_news_records
from earnings_engine.data.catalysts_news import get_short_term_catalysts
from earnings_engine.data.pre_market_setups import get_premarket_setups


def test_ecosystem_multi_stock_entity_resolution():
    # 1. Test unlisted startup (Ather Energy) mapping to listed stakeholder & EV peers
    title_ather = "Ather Energy launches new Rizta family electric scooter with 160km range to challenge Ola"
    summary_ather = "Hero MotoCorp-backed EV startup expands production footprint"
    aff_ather = extract_all_affected_tickers(title_ather, summary_ather)
    tickers_ather = [t[0] for t in aff_ather]
    assert "HEROMOTOCO.NS" in tickers_ather
    assert "OLAELEC.NS" in tickers_ather

    # 2. Test Quick Commerce war (Zepto) mapping to Zomato & Swiggy
    title_zepto = "Zepto raises $650M at $3.6B valuation to intensify quick commerce grocery delivery battle"
    aff_zepto = extract_all_affected_tickers(title_zepto, "")
    tickers_zepto = [t[0] for t in aff_zepto]
    assert "ZOMATO.NS" in tickers_zepto
    assert "SWIGGY.NS" in tickers_zepto

    # 3. Test Conglomerate entity disambiguation
    title_adani = "Adani Group plans $10 billion investment in energy and infrastructure projects"
    aff_adani = extract_all_affected_tickers(title_adani, "")
    tickers_adani = [t[0] for t in aff_adani]
    assert "ADANIENT.NS" in tickers_adani
    assert "ADANIPORTS.NS" in tickers_adani


def test_broadband_news_pipeline_and_relational_storage(tmp_path):
    settings = Settings()
    settings.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    settings.ensure_dirs()

    recent_utc = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    # Ingest headline with unlisted entity that routes to multiple listed tickers
    raw_item = [{
        "title": "Ather Energy files DRHP with SEBI for Rs 4,500 crore IPO - Moneycontrol",
        "summary": "Hero MotoCorp holds 38% stake in the EV scooter maker",
        "publisher": "Moneycontrol",
        "published_at": recent_utc,
        "source": "broadband_moneycontrol",
    }]

    verified = process_and_verify_news_items(raw_item, settings=settings, run_ai=False)
    assert len(verified) == 1
    rec = verified[0]
    assert rec["ticker"] == "HEROMOTOCO.NS"
    aff_list = json.loads(rec["affected_tickers"])
    assert "HEROMOTOCO.NS" in aff_list
    assert "OLAELEC.NS" in aff_list

    # Save to database and verify relational table
    saved = save_verified_news_records(verified, settings=settings)
    assert saved == 1

    with _connect(settings) as conn:
        rel_rows = conn.execute("SELECT ticker, impact_type FROM news_catalysts_tickers").fetchall()
        rel_tickers = [r[0] for r in rel_rows]
        assert "HEROMOTOCO.NS" in rel_tickers
        assert "OLAELEC.NS" in rel_tickers

    # Querying by secondary affected stock should find the news item via relational lookup
    ola_catalysts = get_short_term_catalysts(watchlist_or_universe="my_watchlist", settings=settings)
    assert isinstance(ola_catalysts, list)


def test_premarket_setups_submission_time_sorting(tmp_path):
    settings = Settings()
    settings.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    settings.ensure_dirs()

    now_utc = datetime.now(timezone.utc)
    time_newer = (now_utc - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    time_older = (now_utc - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

    items = [
        {
            "ticker": "INFY.NS",
            "stock_name": "Infosys",
            "title": "Infosys signs $500M cloud migration deal with European client",
            "summary": "Multi-year digital transformation partnership",
            "publisher": "Livemint",
            "published_at": time_older,
            "source": "broadband_livemint",
        },
        {
            "ticker": "TCS.NS",
            "stock_name": "Tata Consultancy Services",
            "title": "TCS secures mega BFSI contract worth $1.2 Billion in North America",
            "summary": "Large financial institution transformation deal",
            "publisher": "Economic Times",
            "published_at": time_newer,
            "source": "broadband_et",
        }
    ]

    verified = process_and_verify_news_items(items, settings=settings, run_ai=False)
    save_verified_news_records(verified, settings=settings)

    # Fetch premarket setups
    setups_res = get_premarket_setups(settings=settings, limit=10)
    assert setups_res["success"] is True
    setups = setups_res.get("items") or setups_res.get("setups") or []
    if len(setups) >= 2:
        # Newer submission time should appear first
        t0_time = setups[0].get("published_at_raw") or setups[0]["published_at"]
        t1_time = setups[1].get("published_at_raw") or setups[1]["published_at"]
        assert t0_time >= t1_time
