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
    "BHEL.NS", "RECLTD.NS", "PFC.NS", "IRFC.NS", "SOLARINDS.NS",
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
    "CLEAN.NS", "FLUOROCHEM.NS", "EXIDEIND.NS", "ARE&M.NS", "APOLLOTYRE.NS",
    "BALKRISIND.NS", "MRF.NS", "VOLTAS.NS", "BLUESTARCO.NS", "CROMPTON.NS",
    "KEI.NS", "FINCABLES.NS", "CDSL.NS", "BSE.NS", "ANGELONE.NS",
    "KFINTECH.NS", "MCX.NS", "NAM-INDIA.NS", "HDFCAMC.NS", "UTIAMC.NS",
    "ABCAPITAL.NS", "LTF.NS", "SUNDARMFIN.NS", "POONAWALLA.NS", "CREDITACC.NS",
    "FORTIS.NS", "NH.NS", "ASTERDM.NS", "SYNGENE.NS", "GLAND.NS",
    "LAURUSLABS.NS", "NATCOPHARM.NS", "JBMA.NS", "MSUMI.NS", "CRAFTSMAN.NS",
    "SONACOMS.NS", "ESCORTS.NS", "ACE.NS", "ELECON.NS", "KIRLOSENG.NS",
    "THERMAX.NS", "TRIVENI.NS", "AIAENG.NS", "CARBORUNIV.NS", "GRINDWELL.NS",
    "TIMKEN.NS", "SCHAEFFLER.NS", "SKFINDIA.NS", "CENTURYPLY.NS", "GREENPANEL.NS",
    "KAJARIACER.NS", "CERA.NS", "CASTROLIND.NS", "AEGISLOG.NS", "MGL.NS",
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
    "STAR.NS", "GRANULES.NS", "JBCHEPHARM.NS", "ERIS.NS", "AJANTPHARM.NS"
]

_SEED_NSE_TOP = _SEED_NIFTY_50

_SEED_US_TOP = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B", "LLY",
    "AVGO", "AMD", "COST", "PEP", "ADBE", "NFLX", "CRM", "INTC", "QCOM",
    "TXN", "AMGN", "WMT", "DIS", "ISRG", "INTU", "PYPL", "MRNA", "SPGI",
    "CSCO", "CMCSA", "NOW", "CAT", "ADP", "CSX", "GE", "SHOP", "PLTR",
    "CME", "VRTX", "ON", "ROKU", "PANW", "SBUX", "SQ", "UBER", "MELI",
]

_SEED_NSE_FNO = [
    # Major Indices
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI", "SENSEX",
    # Official Underlying Equities
    "360ONE", "ABB", "ABCAPITAL", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS",
    "ADANIPOWER", "ALKEM", "AMBER", "AMBUJACEM", "ANGELONE", "APLAPOLLO", "APOLLOHOSP",
    "ASHOKLEY", "ASIANPAINT", "ASTRAL", "ATHERENERG", "AUBANK", "AUROPHARMA", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJAJHLDNG", "BAJFINANCE", "BANDHANBNK", "BANKBARODA",
    "BANKINDIA", "BDL", "BEL", "BHARATFORG", "BHARTIARTL", "BHEL", "BIOCON", "BLUESTARCO",
    "BOSCHLTD", "BPCL", "BRITANNIA", "BSE", "CAMS", "CANBK", "CANFINHOME", "CDSL", "CGPOWER",
    "CHAMBLFERT", "CHOLAFIN", "CIPLA", "COALINDIA", "COCHINSHIP", "COFORGE", "COLPAL",
    "CONCOR", "COROMANDEL", "CROMPTON", "CUMMINSIND", "DABUR", "DEEPAKNTR", "DELHIVERY",
    "DIVISLAB", "DIXON", "DLF", "DMART", "DRREDDY", "EICHERMOT", "ESCORTS", "ETERNAL",
    "EXIDEIND", "FEDERALBNK", "FORCEMOT", "FORTIS", "GAIL", "GLENMARK", "GMRAIRPORT",
    "GNFC", "GODFRYPHLP", "GODREJCP", "GODREJPROP", "GRANULES", "GRASIM", "GUJGASLTD",
    "GVT&D", "HAL", "HAVELLS", "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO",
    "HINDALCO", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "HINDZINC", "HYUNDAI", "ICICIBANK",
    "ICICIGI", "ICICIPRULI", "IDEA", "IDFCFIRSTB", "IEX", "INDHOTEL", "INDIANB", "INDIGO",
    "INDUSINDBK", "INDUSTOWER", "INFY", "INOXWIND", "IOC", "IREDA", "IRFC", "ITC",
    "JINDALSTEL", "JIOFIN", "JSWENERGY", "JSWSTEEL", "JUBLFOOD", "KALYANKJIL", "KAYNES",
    "KEI", "KFINTECH", "KOTAKBANK", "KPITTECH", "LAURUSLABS", "LICHSGFIN", "LICI", "LODHA",
    "LT", "LTF", "LTIM", "LTM", "LUPIN", "M&M", "M&MFIN", "MAHABANK", "MANAPPURAM",
    "MANKIND", "MARICO", "MARUTI", "MAXHEALTH", "MAZDOCK", "MCX", "METROPOLIS", "MFSL",
    "MOTHERSON", "MOTILALOFS", "MPHASIS", "MUTHOOTFIN", "NAM-INDIA", "NATIONALUM", "NAUKRI",
    "NBCC", "NESTLEIND", "NHPC", "NMDC", "NTPC", "NYKAA", "OBEROIRLTY", "OFSS", "OIL",
    "ONGC", "PAGEIND", "PATANJALI", "PAYTM", "PEL", "PERSISTENT", "PETRONET", "PFC",
    "PGEL", "PHOENIXLTD", "PIDILITIND", "PIIND", "PNB", "PNBHOUSING", "POLICYBZR",
    "POLYCAB", "POWERGRID", "POWERINDIA", "PREMIERENE", "PRESTIGE", "PVRINOX", "RADICO",
    "RBLBANK", "REC", "RECLTD", "RELIANCE", "RVNL", "SAGILITY", "SAIL", "SBICARD",
    "SBILIFE", "SBIN", "SHREECEM", "SHRIRAMFIN", "SIEMENS", "SOLARINDS", "SONACOMS",
    "SRF", "SUNPHARMA", "SUNTV", "SUPREMEIND", "SUZLON", "SWIGGY", "SYNGENE", "TATACHEM",
    "TATACOMM", "TATACONSUM", "TATAELXSI", "TATAMOTORS", "TATAPOWER", "TATASTEEL", "TCS",
    "TECHM", "TIINDIA", "TITAN", "TMPV", "TORNTPHARM", "TRENT", "TVSMOTOR", "UBL",
    "ULTRACEMCO", "UNIONBANK", "UNITDSPR", "UNOMINDA", "UPL", "VBL", "VEDL", "VMM",
    "VOLTAS", "WAAREEENER", "WIPRO", "YESBANK", "ZEEL", "ZYDUSLIFE"
]

FNO_INDEX_ALIASES: dict[str, str] = {
    "^NSEI": "NIFTY",
    "NIFTY": "NIFTY",
    "NIFTY50": "NIFTY",
    "NIFTY 50": "NIFTY",
    "NIFTY_50": "NIFTY",
    "^NSEBANK": "BANKNIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "NIFTYBANK": "BANKNIFTY",
    "NIFTY BANK": "BANKNIFTY",
    "NIFTY_BANK": "BANKNIFTY",
    "^CNXFIN": "FINNIFTY",
    "FINNIFTY": "FINNIFTY",
    "NIFTY FIN SERVICE": "FINNIFTY",
    "NIFTY FINANCIAL SERVICES": "FINNIFTY",
    "MIDCPNIFTY": "MIDCPNIFTY",
    "NIFTY MIDCAP SELECT": "MIDCPNIFTY",
    "NIFTY_MID_SELECT": "MIDCPNIFTY",
    "NIFTYNXT50": "NIFTYNXT50",
    "NIFTY NEXT 50": "NIFTYNXT50",
    "NIFTY_NEXT_50": "NIFTYNXT50",
    "^BSESN": "SENSEX",
    "SENSEX": "SENSEX",
    "BSESENSEX": "SENSEX",
    "BSE:SENSEX": "SENSEX",
    "SENSEX.BO": "SENSEX",
    "BSE SENSEX": "SENSEX",
    "BSE_SENSEX": "SENSEX",
}


def resolve_fno_symbol(ticker: str) -> str:
    """Normalize index names, aliases, and ticker suffixes to canonical NSE F&O underlying symbol."""
    if not ticker:
        return ""
    clean = str(ticker).upper().strip()
    if clean in FNO_INDEX_ALIASES:
        return FNO_INDEX_ALIASES[clean]
    clean_no_ns = clean.replace(".NS", "").strip()
    if clean_no_ns in FNO_INDEX_ALIASES:
        return FNO_INDEX_ALIASES[clean_no_ns]
    return clean_no_ns


_FNO_NORMALIZED_SET: set[str] = set()


def is_fno_eligible(ticker: str) -> bool:
    """Check if a ticker or symbol is eligible for NSE Derivatives (F&O).

    Fast in-memory lookup (<0.01ms). Normalizes ticker symbol (removes .NS suffix,
    resolves index aliases, converts to uppercase, trims whitespace).
    """
    if not ticker:
        return False
    clean = resolve_fno_symbol(ticker)
    global _FNO_NORMALIZED_SET
    if not _FNO_NORMALIZED_SET:
        _FNO_NORMALIZED_SET = {s.upper().replace(".NS", "").strip() for s in _SEED_NSE_FNO}
    return clean in _FNO_NORMALIZED_SET


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
    elif clean_name in ("nse_fno", "fno", "nifty_fno"):
        indices = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI", "SENSEX"}
        return [f"{s}.NS" if s not in indices else s for s in _SEED_NSE_FNO]
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
    "nse_top": {
        "name": "nse_top",
        "display_name": "🇮🇳 NSE Top 50 (Nifty 50 Blue-Chips)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "India's flagship 50 mega-cap blue-chip index constituents on the NSE.",
        "explanation": "Includes benchmark NIFTY 50 blue-chip market leaders across banking, IT, energy, consumer, auto, and pharma.",
        "selection_criteria": "Official 50 constituents of the Nifty 50 Index.",
    },
    "nse_fno": {
        "name": "nse_fno",
        "display_name": "⚡ NSE F&O (Derivatives Universe)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": False,
        "summary": "Eligible underlying equities and major indices traded on the NSE Futures & Options (F&O) segment.",
        "explanation": "Deeply liquid derivatives universe with live option chains, open interest, PCR, and strike walls.",
        "selection_criteria": "Official underlying securities in NSE F&O segment.",
    },
}


def get_universe_details(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return all built-in universes with their full ticker lists, metadata, and explanations."""
    universe_names = [
        "nse_top", "nifty_50", "nifty_next_50", "nifty_100", "nifty_200", "nifty_500",
        "nse_mid_cap", "nse_small_cap", "nse_large_cap", "nse_fno", "nse_all", "us_top"
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


_LOAD_UNIVERSE_CACHE: dict[str, tuple[float, list[str]]] = {}
_UNIVERSE_CACHE_TTL_SECS: float = 300.0  # 5-minute fast in-memory cache


def load_nse_large_cap(force_refresh: bool = False, settings: Settings | None = None) -> list[str]:
    """Load NSE stocks with market cap > 1000cr from SQLite, with sub-millisecond fallback."""
    settings = settings or Settings()
    if not force_refresh:
        # 1. Check existing universe in SQLite
        if is_universe_fresh("NSE_LARGE_CAP", NSE_ALL_MAX_AGE_DAYS, settings):
            tickers = get_universe("NSE_LARGE_CAP", settings)
            if tickers:
                return tickers

        # 2. Fast query from indexed tickers table
        try:
            min_market_cap = NSE_LARGE_CAP_MIN_CR * 1e7
            with _connect(settings) as connection:
                rows = connection.execute(
                    "SELECT ticker FROM tickers WHERE market_cap >= ? ORDER BY market_cap DESC",
                    (min_market_cap,)
                ).fetchall()
                if rows and len(rows) >= 30:
                    tickers = [r[0] for r in rows if r[0]]
                    store_universe("NSE_LARGE_CAP", tickers, settings)
                    return tickers
        except Exception:
            pass

        # 3. Fallback immediately to broad index (Nifty 500 / 200) without blocking on yfinance
        fallback = get_universe("nifty_500", settings) or get_universe("nifty_200", settings) or list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50 + _SEED_NIFTY_MIDCAP_100))
        if fallback:
            store_universe("NSE_LARGE_CAP", fallback, settings)
            return fallback

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


def load_nse_fno(force_refresh: bool = False, settings: Settings | None = None) -> list[str]:
    """Load official NSE F&O underlying universe with .NS ticker suffixes for equities."""
    global _FNO_NORMALIZED_SET
    settings = settings or Settings()
    if not force_refresh and is_universe_fresh("NSE_FNO", NSE_ALL_MAX_AGE_DAYS, settings):
        tickers = get_universe("NSE_FNO", settings)
        if tickers:
            if not _FNO_NORMALIZED_SET:
                _FNO_NORMALIZED_SET = {s.upper().replace(".NS", "").strip() for s in _SEED_NSE_FNO}
            _FNO_NORMALIZED_SET.update(t.upper().replace(".NS", "").strip() for t in tickers)
            _FNO_NORMALIZED_SET.add("SENSEX")
            if "SENSEX" not in tickers:
                tickers.append("SENSEX")
            return tickers

    logger.info("refreshing NSE_FNO derivatives universe")
    try:
        from nselib import derivatives
        df = derivatives.live_most_active_underlying()
        if df is not None and not df.empty and "symbol" in df.columns:
            raw_syms = df["symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
            if raw_syms:
                if not _FNO_NORMALIZED_SET:
                    _FNO_NORMALIZED_SET = {s.upper().replace(".NS", "").strip() for s in _SEED_NSE_FNO}
                _FNO_NORMALIZED_SET.update(raw_syms)
                _FNO_NORMALIZED_SET.add("SENSEX")
                indices = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI", "SENSEX"}
                for idx in indices:
                    if idx not in raw_syms:
                        raw_syms.append(idx)
                fno_tickers = [f"{s}.NS" if s not in indices else s for s in raw_syms]
                store_universe("NSE_FNO", fno_tickers, settings)
                logger.info("NSE_FNO refreshed with %d symbols", len(fno_tickers))
                return fno_tickers
    except Exception as e:
        logger.warning("Dynamic NSE F&O underlying fetch failed: %s; falling back to seed universe", e)

    indices = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI", "SENSEX"}
    seed_formatted = [f"{s}.NS" if s not in indices else s for s in _SEED_NSE_FNO]
    store_universe("NSE_FNO", seed_formatted, settings)
    return seed_formatted


# ---------------------------------------------------------------------------
# Public Load APIs
# ---------------------------------------------------------------------------

def load_universe(market: str, settings: Settings | None = None) -> list[str]:
    """Load the configured ticker universe for one market with fast in-memory caching."""
    import time
    settings = settings or Settings()
    market_key = str(market or "IN").upper().strip()

    # Fast in-memory cache check (<0.01ms)
    now = time.monotonic()
    if market_key in _LOAD_UNIVERSE_CACHE:
        cached_time, cached_tickers = _LOAD_UNIVERSE_CACHE[market_key]
        if (now - cached_time) < _UNIVERSE_CACHE_TTL_SECS and cached_tickers:
            return cached_tickers

    res: list[str] = []
    if market_key in {"IN", "NSE_TOP", "NIFTY_50", "NSE_50"}:
        res = get_universe("nifty_50", settings) or get_universe("IN", settings) or get_universe("nse_top", settings) or list(_SEED_NIFTY_50)
    elif market_key in {"NIFTY_NEXT_50", "NEXT_50"}:
        res = get_universe("nifty_next_50", settings) or list(_SEED_NIFTY_NEXT_50)
    elif market_key in {"NIFTY_100", "NSE_100"}:
        res = get_universe("nifty_100", settings) or list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50))
    elif market_key in {"NIFTY_MIDCAP_100", "NSE_MID_CAP", "NSE_MIDCAP", "MID_CAP"}:
        res = get_universe("nse_mid_cap", settings) or list(_SEED_NIFTY_MIDCAP_100)
    elif market_key in {"NIFTY_SMALLCAP_100", "NSE_SMALL_CAP", "NSE_SMALLCAP", "SMALL_CAP"}:
        res = get_universe("nse_small_cap", settings) or list(_SEED_NIFTY_SMALLCAP_100)
    elif market_key in {"NIFTY_200", "NSE_200"}:
        res = get_universe("nifty_200", settings) or list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50 + _SEED_NIFTY_MIDCAP_100))
    elif market_key in {"NIFTY_500", "NSE_500"}:
        res = get_universe("nifty_500", settings) or list(dict.fromkeys(_SEED_NIFTY_50 + _SEED_NIFTY_NEXT_50 + _SEED_NIFTY_MIDCAP_100 + _SEED_NIFTY_SMALLCAP_100))
    elif market_key in {"NSE_FNO", "FNO", "NIFTY_FNO"}:
        res = load_nse_fno(settings=settings)
    elif market_key in {"US", "US_TOP", "US_50"}:
        res = get_universe("US", settings) or get_universe("us_top", settings) or list(_SEED_US_TOP)
    elif market_key == "NSE_ALL":
        res = load_nse_all(settings=settings)
    elif market_key == "NSE_LARGE_CAP":
        res = load_nse_large_cap(settings=settings)
    else:
        res = get_universe(market, settings) or get_universe(market_key, settings)
        if not res:
            raise ValueError(f"Unsupported market: {market}")

    if res:
        _LOAD_UNIVERSE_CACHE[market_key] = (now, res)
    return res


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
