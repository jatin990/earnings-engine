"""Ticker universes for supported markets, backed by shared SQLite database."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path as _prices_cache_path

UNIVERSE_DIR = Path(__file__).resolve().parent / "universes"
NSE_ALL_MAX_AGE_DAYS = 40
NSE_LARGE_CAP_MIN_CR = 1000  # 1000 crore = 10,000,000,000 rupees
MARKET_CAP_MAX_AGE_DAYS = 15  # same as earnings cache freshness

logger = logging.getLogger("earnings_engine.data.universe")

_SEED_NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "KOTAKBANK.NS", "SBIN.NS", "LT.NS", "AXISBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "NTPC.NS", "ULTRACEMCO.NS", "POWERGRID.NS", "ONGC.NS", "JSWSTEEL.NS",
    "TATASTEEL.NS", "M&M.NS", "WIPRO.NS", "TECHM.NS", "HCLTECH.NS",
    "BAJAJ-AUTO.NS", "TITAN.NS", "ADANIPORTS.NS", "HEROMOTOCO.NS", "INDUSINDBK.NS",
    "EICHERMOT.NS", "DIVISLAB.NS", "DRREDDY.NS", "CIPLA.NS", "NESTLEIND.NS",
    "GRASIM.NS", "BEL.NS", "BPCL.NS", "COALINDIA.NS", "SHREECEM.NS",
    "ETERNAL.NS", "ADANIENT.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "TRENT.NS",
    "APOLLOHOSP.NS", "BRITANNIA.NS", "TATAMOTORS.NS", "SBILIFE.NS", "HDFCLIFE.NS",
    "HINDALCO.NS", "SHRIRAMFIN.NS", "LTIM.NS"
]

_SEED_NIFTY_NEXT_50 = [
    "HAL.NS", "DLF.NS", "SIEMENS.NS", "ABB.NS", "INDIGO.NS",
    "TVSMOTOR.NS", "VEDL.NS", "AMBUJACEM.NS", "GAIL.NS", "TATAPOWER.NS",
    "HAVELLS.NS", "NAUKRI.NS", "CANBK.NS", "BANKBARODA.NS", "PNB.NS",
    "UNIONBANK.NS", "ZYDUSLIFE.NS", "CHOLAFIN.NS", "CUMMINSIND.NS", "PERSISTENT.NS",
    "POLYCAB.NS", "LODHA.NS", "INDHOTEL.NS", "CGPOWER.NS", "BOSCHLTD.NS",
    "PIDILITIND.NS", "DABUR.NS", "MARICO.NS", "GODREJCP.NS", "ICICIGI.NS",
    "ICICIPRULI.NS", "UNITDSPR.NS", "SRF.NS", "TORNTPHARM.NS", "JUBLFOOD.NS",
    "BHEL.NS", "REC.NS", "PFC.NS", "IRFC.NS", "SOLARINDS.NS",
    "SUPREMEIND.NS", "TIINDIA.NS", "COLPAL.NS", "BERGEPAINT.NS", "ASHOKLEY.NS",
    "CONCOR.NS", "BIOCON.NS", "PAGEIND.NS", "ASTRAL.NS", "MAXHEALTH.NS"
]

_SEED_NIFTY_MIDCAP_100 = [
    "DIXON.NS", "KAYNES.NS", "MAZDOCK.NS", "COCHINSHIP.NS", "SUZLON.NS",
    "INOXWIND.NS", "WAAREEENER.NS", "IREDA.NS", "KPITTECH.NS", "COFORGE.NS",
    "MPHASIS.NS", "LTTS.NS", "TATAELXSI.NS", "UNOMINDA.NS", "BHARATFORG.NS",
    "FEDERALBNK.NS", "IDFCFIRSTB.NS", "AUBANK.NS", "BANDHANBNK.NS", "OBEROIRLTY.NS",
    "PRESTIGE.NS", "PHOENIXLTD.NS", "GODREJPROP.NS", "SUNTV.NS", "GLENMARK.NS",
    "ALKEM.NS", "IPCALAB.NS", "AARTIIND.NS", "DEEPAKNTR.NS", "TATACHEM.NS",
    "CLEAN.NS", "FLUOROCHEM.NS", "EXIDEIND.NS", "AMARAJABAT.NS", "APOLLOTYRE.NS",
    "BALKRISIND.NS", "MRF.NS", "VOLTAS.NS", "BLUESTARCO.NS", "CROMPTON.NS",
    "KEI.NS", "FINCABLES.NS", "CDSL.NS", "BSE.NS", "ANGELONE.NS",
    "KFINTECH.NS", "MCX.NS", "NAM-INDIA.NS", "HDFCAMC.NS", "UTIAMC.NS",
    "ABCAPITAL.NS", "L&TFH.NS", "SUNDARMFIN.NS", "POONAWALLA.NS", "CREDITACC.NS",
    "FORTIS.NS", "NH.NS", "ASTERDM.NS", "SYNGENE.NS", "GLAND.NS",
    "LAURUSLABS.NS", "NATCOPHARM.NS", "JBMA.NS", "MSUMI.NS", "CRAFTSMAN.NS",
    "SONACOMS.NS", "ESCORTS.NS", "ACE.NS", "ELECON.NS", "KIRLOSENG.NS",
    "THERMAX.NS", "TRIVENI.NS", "AIAENG.NS", "CARBORUNIV.NS", "GRINDWELL.NS",
    "TIMKEN.NS", "SCHAEFFLER.NS", "SKFINDIA.NS", "CENTURYPLY.NS", "GREENPANEL.NS",
    "KAJARIACER.NS", "CERA.NS", "CASTROLIND.NS", "AEGISCHEM.NS", "MGL.NS",
    "IGL.NS", "GUJGASLTD.NS", "PETRONET.NS", "OIL.NS", "MOTILALOFS.NS"
]

_SEED_NIFTY_SMALLCAP_100 = [
    "TATATECH.NS", "NETWEB.NS", "CYIENT.NS", "BSOFT.NS", "TANLA.NS",
    "HAPPSTMNDS.NS", "RALLIS.NS", "AVANTIFEED.NS", "CENTURYTEX.NS", "RAYMOND.NS",
    "WELSPUNLIV.NS", "TRIDENT.NS", "KNRCON.NS", "PNCINFRA.NS", "GRINFRA.NS",
    "HGINFRA.NS", "ASHOKA.NS", "PRAJIND.NS", "ISGEC.NS", "IONEXCHANG.NS",
    "TECHNOCRAF.NS", "SANGHVIMOV.NS", "JWL.NS", "TITAGARH.NS", "TEXRAIL.NS",
    "RAILTEL.NS", "RITES.NS", "IRCON.NS", "MSTCLTD.NS", "HUDCO.NS",
    "NBCC.NS", "ENGINERSIN.NS", "MOIL.NS", "KIOCL.NS", "SANDUMA.NS",
    "LLOYDSME.NS", "JAIBALAJI.NS", "JINDALSAW.NS", "MAHSEAMLES.NS", "WELCORP.NS",
    "APLAPOLLO.NS", "RATNAMANI.NS", "VENUSPIPES.NS", "PRINCEPIPE.NS", "FINPIPE.NS",
    "CAMPUS.NS", "METROBRAND.NS", "RELAXO.NS", "SAFARI.NS", "VIPIND.NS",
    "VAIBHAVGBL.NS", "ETHOSLTD.NS", "SENCO.NS", "KALYANKJIL.NS", "MEDPLUS.NS",
    "YATHARTH.NS", "JLHL.NS", "SHALBY.NS", "THYROCARE.NS", "METROPOLIS.NS",
    "VIJAYA.NS", "LALPATHLAB.NS", "KIMS.NS", "MARKSANS.NS", "SUPRIYA.NS",
    "SIGACHI.NS", "NEULANDLAB.NS", "FDC.NS", "CAPLIPOINT.NS", "RPGLIFE.NS",
    "STRIDES.NS", "GRANULES.NS", "JBCHEPHARM.NS", "ERIS.NS", "AJANTPHARM.NS"
]

_SEED_NSE_TOP = _SEED_NIFTY_50

_SEED_US_TOP = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B", "LLY",
    "AVGO", "AMD", "COST", "PEP", "ADBE", "NFLX", "CRM", "INTC", "QCOM",
    "TXN", "AMGN", "WMT", "DIS", "ISRG", "INTU", "PYPL", "MRNA", "SPGI",
    "CSCO", "CMCSA", "NOW", "CAT", "ADP", "CSX", "GE", "SHOP", "PLTR",
    "CME", "VRTX", "ON", "ROKU", "PANW", "SBUX", "SQ", "UBER", "MELI",
]


# ---------------------------------------------------------------------------
# SQLite connection & schema
# ---------------------------------------------------------------------------

def _db_path(settings: Settings | None = None) -> Path:
    """Use the same SQLite database as prices."""
    if settings is None:
        settings = Settings()
    return _prices_cache_path(settings)


def _connect(settings: Settings | None = None) -> Any:
    """Connect to database and ensure universe tables and initial seeds exist."""
    if settings is None:
        settings = Settings()
    settings.ensure_dirs()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)
    conn = get_db_connection(settings)

    # Seed IN and US if universes table has no rows
    count = conn.execute("SELECT count(*) FROM universes").fetchone()[0]
    if count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for t in _SEED_NSE_TOP:
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("IN", t, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("nse_top", t, now),
            )
        for t in _SEED_US_TOP:
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("US", t, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("us_top", t, now),
            )

        # Also import any existing text files in universes directory if present
        if UNIVERSE_DIR.exists():
            for f in UNIVERSE_DIR.glob("*.txt"):
                name = f.stem
                if name.startswith("my_watchlist"):
                    continue
                try:
                    lines = [line.strip() for line in f.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
                    for t in lines:
                        conn.execute(
                            "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                            (name, t, now),
                        )
                except Exception:
                    pass
        conn.commit()

    # Auto-migrate rebranded/renamed symbols (e.g. ZOMATO.NS -> ETERNAL.NS)
    try:
        conn.execute("UPDATE universes SET ticker = 'ETERNAL.NS' WHERE ticker = 'ZOMATO.NS'")
        conn.commit()
    except Exception:
        pass

    return conn


# Backward-compatible alias
_connect_market_cap = _connect


# ---------------------------------------------------------------------------
# Market cap caching
# ---------------------------------------------------------------------------

def is_market_cap_fresh(ticker: str, settings: Settings | None = None) -> bool:
    """Check if market cap data is fresh in SQLite for the given ticker."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT market_cap_updated_at FROM tickers WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if not row or not row[0]:
            try:
                row = connection.execute(
                    "SELECT fetched_at FROM ticker_market_cap WHERE ticker = ?",
                    (ticker,),
                ).fetchone()
            except Exception:
                row = None
    if not row or not row[0]:
        return False
    fetched_at = pd.Timestamp(row[0])
    age_days = (pd.Timestamp.now() - fetched_at).total_seconds() / 86400
    return age_days <= MARKET_CAP_MAX_AGE_DAYS


def store_market_caps_bulk(ticker_caps: dict[str, float | None], settings: Settings | None = None) -> None:
    """Store market caps for multiple tickers in SQLite in a single transaction."""
    if not ticker_caps:
        return
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    params = [(ticker, cap, now, now) for ticker, cap in ticker_caps.items() if cap is not None]
    if not params:
        return

    with _connect(settings) as connection:
        connection.executemany(
            """
            INSERT INTO tickers (ticker, market_cap, market_cap_updated_at, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market_cap = excluded.market_cap,
                market_cap_updated_at = excluded.market_cap_updated_at,
                last_updated = excluded.last_updated
            """,
            params,
        )
        try:
            legacy_params = [(ticker, cap, now) for ticker, cap in ticker_caps.items() if cap is not None]
            connection.executemany(
                "INSERT OR REPLACE INTO ticker_market_cap (ticker, market_cap, fetched_at) VALUES (?, ?, ?)",
                legacy_params,
            )
        except Exception:
            pass
        connection.commit()


def store_market_cap(ticker: str, market_cap: float | None, settings: Settings | None = None) -> None:
    """Store market cap for a ticker in SQLite."""
    store_market_caps_bulk({ticker: market_cap}, settings)


def load_market_cap(ticker: str, settings: Settings | None = None) -> float | None:
    """Load cached market cap for a ticker."""
    with _connect(settings) as connection:
        try:
            row = connection.execute(
                "SELECT market_cap FROM tickers WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            if row and row[0] is not None:
                return float(row[0])
        except Exception:
            pass
        return None


def load_all_market_caps(settings: Settings | None = None) -> dict[str, float]:
    """Load all market caps from SQLite cache. Returns {ticker: market_cap}."""
    with _connect(settings) as connection:
        try:
            rows = connection.execute(
                "SELECT ticker, market_cap FROM tickers WHERE market_cap IS NOT NULL"
            ).fetchall()
        except Exception:
            rows = []
    return {row[0]: float(row[1]) for row in rows if row[1] is not None}


# ---------------------------------------------------------------------------
# Universe CRUD (SQLite)
# ---------------------------------------------------------------------------

def is_universe_fresh(name: str, max_age_days: int = NSE_ALL_MAX_AGE_DAYS, settings: Settings | None = None) -> bool:
    """Check if a dynamic universe is fresh in SQLite."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT fetched_at FROM universe_freshness WHERE LOWER(universe_name) = LOWER(?)",
            (name,),
        ).fetchone()
    if not row:
        return False
    fetched_at = pd.Timestamp(row[0])
    age_days = (pd.Timestamp.now() - fetched_at).total_seconds() / 86400
    return age_days <= max_age_days


def store_universe(name: str, tickers: list[str], settings: Settings | None = None) -> None:
    """Store/replace an entire universe in SQLite."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_name = name.strip()
    with _connect(settings) as connection:
        connection.execute("DELETE FROM universes WHERE LOWER(universe_name) = LOWER(?)", (clean_name,))
        for t in tickers:
            t = t.strip().upper()
            if t:
                connection.execute(
                    "INSERT OR REPLACE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                    (clean_name.lower(), t, now),
                )
        connection.execute(
            "INSERT OR REPLACE INTO universe_freshness (universe_name, fetched_at) VALUES (?, ?)",
            (clean_name.lower(), now),
        )
        connection.commit()


def add_to_universe(name: str, ticker: str, settings: Settings | None = None) -> bool:
    """Add a ticker to a universe in SQLite."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
            (name, ticker, now),
        )
        connection.commit()
    return True


def remove_from_universe(name: str, ticker: str, settings: Settings | None = None) -> bool:
    """Remove a ticker from a universe in SQLite."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    with _connect(settings) as connection:
        cursor = connection.execute(
            "DELETE FROM universes WHERE universe_name = ? AND ticker = ?",
            (name, ticker),
        )
        connection.commit()
        return cursor.rowcount > 0


def list_universes(settings: Settings | None = None) -> list[dict[str, Any]]:
    """List all available universes from SQLite."""
    with _connect(settings) as connection:
        rows = connection.execute(
            "SELECT universe_name, count(ticker), max(updated_at) FROM universes GROUP BY universe_name ORDER BY universe_name ASC"
        ).fetchall()
    return [
        {"name": row[0], "tickers_count": row[1], "updated_at": row[2]}
        for row in rows
    ]


def get_universe(name: str, settings: Settings | None = None) -> list[str]:
    """Get tickers in a universe from SQLite with comprehensive Groww-style benchmark fallbacks."""
    clean_name = name.lower().strip()
    with _connect(settings) as connection:
        rows = connection.execute(
            "SELECT ticker FROM universes WHERE LOWER(universe_name) = ? ORDER BY rowid ASC",
            (clean_name,),
        ).fetchall()
        if rows:
            return [row[0] for row in rows]

    # Benchmark index resolutions
    if clean_name in ("nse_top", "nifty_50", "nifty50", "nifty_top_50", "nse_50", "in", "nse"):
        return list(_SEED_NIFTY_50)
    elif clean_name in ("nifty_next_50", "niftynext50", "next_50"):
        return list(_SEED_NIFTY_NEXT_50)
    elif clean_name in ("nifty_100", "nifty100", "nse_100"):
        return list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50))
    elif clean_name in ("nifty_midcap_100", "nse_mid_cap", "nse_midcap", "mid_cap", "midcap"):
        return list(_SEED_NIFTY_MIDCAP_100)
    elif clean_name in ("nifty_smallcap_100", "nse_small_cap", "nse_smallcap", "small_cap", "smallcap"):
        return list(_SEED_NIFTY_SMALLCAP_100)
    elif clean_name in ("nifty_200", "nifty200", "nse_200"):
        return list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50 + _SEED_NIFTY_MIDCAP_100))
    elif clean_name in ("nifty_500", "nifty500", "nse_500"):
        return list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50 + _SEED_NIFTY_MIDCAP_100 + _SEED_NIFTY_SMALLCAP_100))
    elif clean_name in ("us_top", "us", "us_50"):
        return list(_SEED_US_TOP)

    return []


UNIVERSE_METADATA: dict[str, dict[str, Any]] = {
    "nifty_50": {
        "name": "nifty_50",
        "display_name": "🇮🇳 Nifty 50 (Bluechips)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "India's flagship 50 mega-cap blue-chip index constituents on the NSE.",
        "explanation": "Includes benchmark market leaders across banking, IT, energy, consumer, auto, and pharma.",
        "selection_criteria": "Official 50 constituents of the Nifty 50 Index.",
    },
    "nifty_next_50": {
        "name": "nifty_next_50",
        "display_name": "🇮🇳 Nifty Next 50 (Large-Cap Growth)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "The next 50 largest companies by market cap ranked 51–100.",
        "explanation": "High-growth large cap companies poised for future inclusion in Nifty 50.",
        "selection_criteria": "Official constituents of the Nifty Next 50 Index.",
    },
    "nifty_100": {
        "name": "nifty_100",
        "display_name": "🇮🇳 Nifty 100 (Top 100 Large-Cap)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Complete Top 100 large cap companies (Nifty 50 + Nifty Next 50).",
        "explanation": "Represents ~70% of total Indian free float market capitalization with deep liquidity.",
        "selection_criteria": "Top 100 large cap companies on the NSE.",
    },
    "nifty_200": {
        "name": "nifty_200",
        "display_name": "🇮🇳 Nifty 200 (Large & Mid-Cap Leaders)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": False,
        "summary": "Top 200 companies combining Large Cap (Nifty 100) and Mid Cap leaders.",
        "explanation": "Comprehensive exposure to institutional-grade growth and quality compounders.",
        "selection_criteria": "Top 200 companies ranked by market capitalization.",
    },
    "nifty_500": {
        "name": "nifty_500",
        "display_name": "🇮🇳 Nifty 500 (Broad Market Index)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": False,
        "summary": "Top 500 companies representing ~96% of total free-float market capitalization.",
        "explanation": "Full market representation across Large, Mid, and Small Cap segments.",
        "selection_criteria": "Top 500 listed companies on the NSE.",
    },
    "nse_mid_cap": {
        "name": "nse_mid_cap",
        "display_name": "🚀 NSE Mid Cap (Top 100 Mid-Cap Growth)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Ranked 101–250 by market cap; the primary engine of alpha and manufacturing expansion.",
        "explanation": "Fast-growing companies across defense, electronics, renewables, and consumer sectors.",
        "selection_criteria": "Companies ranked 101–250 by market capitalization.",
    },
    "nse_small_cap": {
        "name": "nse_small_cap",
        "display_name": "⚡ NSE Small Cap (Top 100 Small-Cap Compounders)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Ranked 251–500 by market cap; high-beta growth opportunities and emerging leaders.",
        "explanation": "Emerging industry disruptors with high earnings surprise velocity.",
        "selection_criteria": "Companies ranked 251–500 by market capitalization.",
    },
    "nse_large_cap": {
        "name": "nse_large_cap",
        "display_name": "🏛️ NSE Large Cap (>₹1,000 Cr Institutional)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": False,
        "summary": "All Indian companies on the NSE with market capitalization exceeding ₹1,000 Crore.",
        "explanation": "Isolates institutional-grade large and mid-to-large cap companies.",
        "selection_criteria": "Market Cap > ₹1,000 Crore on NSE.",
    },
    "nse_all": {
        "name": "nse_all",
        "display_name": "🌐 NSE All (Complete Listed Equities 2,000+)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": False,
        "summary": "Comprehensive universe of all active equity symbols traded on the National Stock Exchange of India.",
        "explanation": "Over 2,000 active tickers across all sectors and market capitalizations.",
        "selection_criteria": "All active traded equity tickers on NSE.",
    },
    "us_top": {
        "name": "us_top",
        "display_name": "🇺🇸 US Top 50 (Mega-Cap Tech & S&P 500 Leaders)",
        "market": "US",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Curated top 50 mega-cap US equities across NASDAQ & NYSE.",
        "explanation": "Features Magnificent Seven leaders and core S&P 500 blue-chips.",
        "selection_criteria": "Top 50 US mega-cap companies by liquidity and market cap.",
    },
}


def get_universe_details(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return all built-in universes with their full ticker lists, metadata, and explanations."""
    universe_names = [
        "nifty_50", "nifty_next_50", "nifty_100", "nifty_200", "nifty_500",
        "nse_mid_cap", "nse_small_cap", "nse_large_cap", "nse_all", "us_top"
    ]
    # Also inspect any other universes in SQLite
    for u in list_universes(settings):
        uname = u["name"].lower()
        if uname not in universe_names and uname not in ("in", "us"):
            universe_names.append(uname)

    out: list[dict[str, Any]] = []
    for uname in universe_names:
        tickers = get_universe(uname, settings)
        if not tickers and uname in ("nse_top", "in"):
            tickers = list(_SEED_NSE_TOP)
        elif not tickers and uname in ("us_top", "us"):
            tickers = list(_SEED_US_TOP)

        meta = UNIVERSE_METADATA.get(uname, {
            "name": uname,
            "display_name": uname.replace("_", " ").title(),
            "market": "IN" if any(t.endswith(".NS") for t in tickers) else "US",
            "type": "universe",
            "is_builtin": True,
            "is_under_100": len(tickers) <= 100,
            "summary": f"Universe containing {len(tickers)} symbols.",
            "explanation": f"Universe '{uname}' stored in the database.",
            "selection_criteria": "Custom universe.",
        })

        count = len(tickers)
        item = {
            **meta,
            "tickers": tickers,
            "count": count,
            "is_under_100": count <= 100,
        }
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# NSE ALL and NSE Large Cap (SQLite Backed)
# ---------------------------------------------------------------------------

def _fetch_nse_all_from_nsetools() -> list[str]:
    """Fetch all NSE stock codes from nsetools and append .NS suffix for yfinance."""
    from nsetools import Nse

    nse = Nse()
    codes = nse.get_stock_codes()
    if not codes:
        return []
    return [f"{code}.NS" for code in codes if code]


def load_nse_all(force_refresh: bool = False, settings: Settings | None = None) -> list[str]:
    """Load all NSE stocks from SQLite, refreshing from nsetools if stale or forced."""
    if not force_refresh and is_universe_fresh("NSE_ALL", NSE_ALL_MAX_AGE_DAYS, settings):
        tickers = get_universe("NSE_ALL", settings)
        if tickers:
            logger.debug("loaded cached NSE_ALL from SQLite (%s tickers)", len(tickers))
            return tickers

    logger.info("refreshing NSE_ALL from nsetools")
    try:
        tickers = _fetch_nse_all_from_nsetools()
        if not tickers:
            logger.warning("nsetools returned empty list, falling back to SQLite cache")
            return get_universe("NSE_ALL", settings)
        store_universe("NSE_ALL", tickers, settings)
        logger.info("NSE_ALL refreshed with %s tickers in SQLite", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("nsetools fetch failed: %s, falling back to SQLite cache", e)
        return get_universe("NSE_ALL", settings)


def _fetch_market_cap_for_ticker(ticker: str) -> tuple[str, float | None]:
    """Fetch market cap for a single ticker from yfinance."""
    import yfinance as yf

    if is_market_cap_fresh(ticker):
        cached = load_market_cap(ticker)
        return (ticker, cached)

    try:
        try:
            from earnings_engine.rate_limits import record_request
            record_request("yfinance")
        except Exception:
            pass
        info = yf.Ticker(ticker).fast_info or {}
        market_cap = info.get("market_cap")
        if market_cap is None:
            info = yf.Ticker(ticker).info or {}
            market_cap = info.get("marketCap")
        store_market_cap(ticker, market_cap)
        return (ticker, market_cap)
    except Exception:
        return (ticker, None)


def _fetch_nse_large_cap_from_yfinance(settings: Settings | None = None) -> list[str]:
    """Fetch market cap for all NSE tickers and filter to those > 1000cr."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_tickers = load_nse_all(settings=settings)
    if not all_tickers:
        return []

    min_market_cap = NSE_LARGE_CAP_MIN_CR * 1e7
    large_cap_tickers: list[str] = []
    total = len(all_tickers)
    batch_size = 50
    processed = 0

    logger.info("fetching market cap for %s tickers in batches of %s", total, batch_size)

    for i in range(0, total, batch_size):
        batch = all_tickers[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_market_cap_for_ticker, ticker): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, market_cap = future.result()
                processed += 1
                if market_cap and market_cap > min_market_cap:
                    large_cap_tickers.append(ticker)

        logger.info("market cap batch %s/%s complete: %s/%s tickers, %s large cap",
                    batch_num, total_batches, processed, total, len(large_cap_tickers))

        if i + batch_size < total:
            time.sleep(2)

    return large_cap_tickers


def load_nse_large_cap(force_refresh: bool = False, settings: Settings | None = None) -> list[str]:
    """Load NSE stocks with market cap > 1000cr from SQLite, refreshing from yfinance if stale."""
    if not force_refresh and is_universe_fresh("NSE_LARGE_CAP", NSE_ALL_MAX_AGE_DAYS, settings):
        tickers = get_universe("NSE_LARGE_CAP", settings)
        if tickers:
            logger.debug("loaded cached NSE_LARGE_CAP from SQLite (%s tickers)", len(tickers))
            return tickers

    logger.info("refreshing NSE_LARGE_CAP from yfinance")
    try:
        tickers = _fetch_nse_large_cap_from_yfinance(settings)
        if not tickers:
            logger.warning("yfinance returned empty list, falling back to SQLite cache")
            return get_universe("NSE_LARGE_CAP", settings)
        store_universe("NSE_LARGE_CAP", tickers, settings)
        logger.info("NSE_LARGE_CAP refreshed with %s tickers in SQLite", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("yfinance fetch failed: %s, falling back to SQLite cache", e)
        return get_universe("NSE_LARGE_CAP", settings)


# ---------------------------------------------------------------------------
# Public Load APIs
# ---------------------------------------------------------------------------

def load_universe(market: str, settings: Settings | None = None) -> list[str]:
    """Load the configured ticker universe for one market from SQLite."""
    market_key = market.upper()
    if market_key in {"IN", "NSE_TOP", "NIFTY_50", "NSE_50"}:
        res = get_universe("nifty_50", settings) or get_universe("IN", settings) or get_universe("nse_top", settings)
        return res or list(_SEED_NIFTY_50)
    if market_key in {"NIFTY_NEXT_50", "NEXT_50"}:
        return get_universe("nifty_next_50", settings) or list(_SEED_NIFTY_NEXT_50)
    if market_key in {"NIFTY_100", "NSE_100"}:
        return get_universe("nifty_100", settings) or list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50))
    if market_key in {"NIFTY_MIDCAP_100", "NSE_MID_CAP", "NSE_MIDCAP", "MID_CAP"}:
        return get_universe("nse_mid_cap", settings) or list(_SEED_NIFTY_MIDCAP_100)
    if market_key in {"NIFTY_SMALLCAP_100", "NSE_SMALL_CAP", "NSE_SMALLCAP", "SMALL_CAP"}:
        return get_universe("nse_small_cap", settings) or list(_SEED_NIFTY_SMALLCAP_100)
    if market_key in {"NIFTY_200", "NSE_200"}:
        return get_universe("nifty_200", settings) or list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50 + _SEED_NIFTY_MIDCAP_100))
    if market_key in {"NIFTY_500", "NSE_500"}:
        return get_universe("nifty_500", settings) or list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50 + _SEED_NIFTY_MIDCAP_100 + _SEED_NIFTY_SMALLCAP_100))
    if market_key in {"US", "US_TOP", "US_50"}:
        res = get_universe("US", settings) or get_universe("us_top", settings)
        return res or list(_SEED_US_TOP)
    if market_key == "NSE_ALL":
        return load_nse_all(settings=settings)
    if market_key == "NSE_LARGE_CAP":
        return load_nse_large_cap(settings=settings)

    # Custom universe from SQLite
    res = get_universe(market, settings) or get_universe(market_key, settings)
    if res:
        return res

    raise ValueError(f"Unsupported market: {market}")


def load_universe_from_file(path: str | Path) -> list[str]:
    """Load tickers from a plain-text file (legacy helper)."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Universe file not found: {file_path}")
    return [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]


def ingest_market_caps(tickers: list[str], force: bool = False, settings: Settings | None = None) -> dict[str, int]:
    """Fetch and cache market cap for the requested tickers in SQLite."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, int] = {}
    total = len(tickers)
    batch_size = 50
    processed = 0
    cached_hits = 0

    if not force:
        for ticker in tickers:
            if is_market_cap_fresh(ticker, settings):
                cached_hits += 1
        if cached_hits == total:
            logger.info("market cap cache hit for all %s tickers, skipping fetch", total)
            return {t: 1 for t in tickers}

    logger.info("ingesting market cap for %s tickers (%s cached, %s to fetch)",
                total, cached_hits, total - cached_hits)

    tickers_to_fetch: list[str] = []
    for ticker in tickers:
        if not force and is_market_cap_fresh(ticker, settings):
            results[ticker] = 1
            processed += 1
        else:
            tickers_to_fetch.append(ticker)

    fetch_total = len(tickers_to_fetch)
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_market_cap_for_ticker, ticker): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, market_cap = future.result()
                processed += 1
                results[ticker] = 1 if market_cap is not None else 0

        logger.info("market cap ingest batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)

        if i + batch_size < total:
            time.sleep(2)

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("market cap ingest complete: %s/%s tickers with data", ok, total)
    return results


def load_universe_from_file(
    name_or_path: str | Path,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Load tickers from a watchlist, universe, or file path, returning list of dicts with 'ticker' key."""
    settings = settings or Settings()
    clean_name = str(name_or_path).replace(".txt", "").strip()

    from earnings_engine.data.watchlists import get_watchlist
    tickers = get_watchlist(clean_name, settings)
    if not tickers:
        tickers = get_universe(clean_name, settings)

    if not tickers and Path(name_or_path).exists():
        try:
            with open(name_or_path, "r", encoding="utf-8") as f:
                tickers = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
        except Exception:
            pass

    if not tickers:
        tickers = list(_SEED_NSE_TOP)

    return [{"ticker": t} for t in tickers]


def load_all(settings: Settings | None = None) -> list[str]:
    """Return the combined universe across supported markets from SQLite."""
    return load_universe("IN", settings) + load_universe("US", settings)
