# Recent Market Additions & IPO Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Recent Market Additions & IPO Tracker into a responsive two-window split screen (master-detail) matching Institutional Intelligence, featuring Mainboard default with an optional SME toggle, rich left-hand market performance metrics, and a balanced hybrid right-hand stock intelligence window.

**Architecture:** Enrich backend listing data with Point-in-Time prices, returns since listing, ATH distances, and volume ratios from SQLite `price_history`. Add a dedicated `/api/v1/market/ipo-detail/{ticker}` endpoint that synthesizes IPO base technicals, debut earnings status, shareholding patterns, and AMFI mutual fund holdings. Upgrade the frontend template and JavaScript module to provide a 50-50 responsive split view with sticky right-hand inspection.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (`price_history`, `earnings_history`, `amfi_holdings`, `market_caps`), Vanilla ES6+ JavaScript, Jinja2 templates, CSS Grid.

**Spec:** `docs/superpowers/specs/2026-09-12-recent-additions-ipo-tracker-design.md`

## Global Constraints
- **Strict Point-in-Time (PIT) Guarantee**: Only use historical prices and reported filings; never assume future dates.
- **Zero-Token Default**: No LLM inference triggered automatically during table or inspection renders.
- **Anti-Fabrication**: Show explicit honest empty states (e.g., "No Mutual Fund Filings on Record", "Awaiting 1st Public Results") when data is missing.
- **Segment Default**: Mainboard (`EQ`) is the default active segment; SME (`SM`, `ST`) is accessible via explicit toggle.
- **Fast Local Execution**: All detail lookups resolve from local SQLite caches without blocking external HTTP calls.

---

### Task 1: Backend Data Enrichment & IPO Detail Engine

**Files:**
- Modify: `earnings_engine/data/new_listings.py`
- Test: `tests/test_new_listings.py`

**Interfaces:**
- Consumes: SQLite tables `price_history`, `earnings_history`, `amfi_holdings`, `market_caps`.
- Produces:
  - `get_recent_nse_additions(days: int, limit: int, settings: Settings)` enriched with: `cmp`, `listing_price`, `return_since_listing_pct`, `ath_price`, `ath_distance_pct`, `return_7d_pct`, `return_30d_pct`, `volume_ratio_5_20`.
  - `get_ipo_stock_detail(ticker: str, settings: Settings) -> dict[str, Any]` returning complete hybrid IPO intelligence (technicals, earnings lifecycle, shareholding, mutual fund holdings).

- [ ] **Step 1: Write failing test for `get_recent_nse_additions` enrichment and `get_ipo_stock_detail`**

Create `tests/test_new_listings.py`:
```python
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from earnings_engine.config import Settings
from earnings_engine.data.new_listings import get_recent_nse_additions, get_ipo_stock_detail


def test_get_recent_nse_additions_enriched(tmp_path, monkeypatch):
    test_db = tmp_path / "test_prices.sqlite3"
    conn = sqlite3.connect(test_db)
    
    # Create price_history and earnings_history
    conn.execute("""
        CREATE TABLE price_history (
            ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.execute("""
        CREATE TABLE earnings_history (
            ticker TEXT, earnings_date TEXT, eps_estimate REAL, eps_reported REAL, surprise_pct REAL, source TEXT,
            PRIMARY KEY (ticker, earnings_date, source)
        )
    """)
    
    # Insert dummy prices for TEST.NS
    today = datetime.now().date()
    d1 = (today - timedelta(days=20)).strftime("%Y-%m-%d")
    d2 = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    d3 = today.strftime("%Y-%m-%d")
    
    conn.execute("INSERT INTO price_history VALUES ('TEST.NS', ?, 100.0, 110.0, 95.0, 105.0, 1000)", (d1,))
    conn.execute("INSERT INTO price_history VALUES ('TEST.NS', ?, 105.0, 130.0, 102.0, 125.0, 2000)", (d2,))
    conn.execute("INSERT INTO price_history VALUES ('TEST.NS', ?, 120.0, 125.0, 118.0, 120.0, 1500)", (d3,))
    conn.commit()
    conn.close()

    settings = Settings(cache_dir=tmp_path)
    monkeypatch.setattr("earnings_engine.data.db._cache_path", lambda s: test_db)

    # Mock official nse equities dataframe
    fake_df = pd.DataFrame([{
        "SYMBOL": "TEST",
        "NAME OF COMPANY": "Test India Ltd",
        "SERIES": "EQ",
        "DATE OF LISTING": (today - timedelta(days=20)).strftime("%d-%b-%Y"),
        "LISTING_DATE": pd.to_datetime(today - timedelta(days=20)),
        "FACE VALUE": 10
    }])
    monkeypatch.setattr("earnings_engine.data.new_listings.fetch_all_nse_equities_cached", lambda: fake_df)

    items = get_recent_nse_additions(days=30, limit=10, settings=settings)
    assert len(items) == 1
    item = items[0]
    assert item["ticker"] == "TEST.NS"
    assert item["cmp"] == 120.0
    assert item["listing_price"] == 105.0
    assert item["ath_price"] == 130.0
    assert round(item["return_since_listing_pct"], 1) == 14.3
    assert item["ath_distance_pct"] < 0


def test_get_ipo_stock_detail(tmp_path, monkeypatch):
    test_db = tmp_path / "test_prices.sqlite3"
    conn = sqlite3.connect(test_db)
    conn.execute("""
        CREATE TABLE price_history (
            ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.execute("""
        CREATE TABLE earnings_history (
            ticker TEXT, earnings_date TEXT, eps_estimate REAL, eps_reported REAL, surprise_pct REAL, source TEXT,
            PRIMARY KEY (ticker, earnings_date, source)
        )
    """)
    conn.execute("""
        CREATE TABLE amfi_holdings (
            fund_name TEXT, fund_type TEXT, ticker TEXT, company_name TEXT,
            shares_held INTEGER, market_value_cr REAL, holding_pct REAL, asof_date TEXT
        )
    """)
    
    today = datetime.now().date()
    d1 = (today - timedelta(days=15)).strftime("%Y-%m-%d")
    d2 = today.strftime("%Y-%m-%d")
    conn.execute("INSERT INTO price_history VALUES ('TEST.NS', ?, 500.0, 550.0, 480.0, 520.0, 50000)", (d1,))
    conn.execute("INSERT INTO price_history VALUES ('TEST.NS', ?, 520.0, 600.0, 515.0, 580.0, 75000)", (d2,))
    
    conn.execute("INSERT INTO amfi_holdings VALUES ('Nippon India Growth Fund', 'Mutual Fund', 'TEST.NS', 'Test India Ltd', 100000, 5.8, 1.2, ?)", (d2,))
    conn.commit()
    conn.close()

    settings = Settings(cache_dir=tmp_path)
    monkeypatch.setattr("earnings_engine.data.db._cache_path", lambda s: test_db)

    detail = get_ipo_stock_detail("TEST.NS", settings=settings)
    assert detail["success"] is True
    assert detail["ticker"] == "TEST.NS"
    assert detail["technical"]["cmp"] == 580.0
    assert detail["technical"]["ath"] == 600.0
    assert "IPO Base" in detail["technical"]["base_stage"]
    assert len(detail["institutional"]["mutual_funds"]) == 1
    assert detail["earnings_lifecycle"]["past_earnings_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_new_listings.py -v`
Expected: FAIL (`ImportError: cannot import name 'get_ipo_stock_detail'` or attribute errors).

- [ ] **Step 3: Implement data enrichment and `get_ipo_stock_detail` in `earnings_engine/data/new_listings.py`**

In `earnings_engine/data/new_listings.py`:
1. In `get_recent_nse_additions`:
   - Batch query `price_history` for the recent tickers to fetch listing day close, latest close (CMP), highest high (ATH), lowest low, 7D past close, 30D past close, and recent volume.
   - Calculate `return_since_listing_pct`, `ath_distance_pct`, `return_7d_pct`, `return_30d_pct`, and `volume_ratio_5_20`.
   - Add these fields to each item dictionary.
2. Implement `get_ipo_stock_detail(ticker: str, settings: Settings | None = None) -> dict[str, Any]`:
   - Normalize ticker to `.NS`.
   - Query `price_history` for full price series:
     - Determine Listing Day Open, Close, High, Low.
     - Determine Current Market Price (CMP), ATH, ATL, 52W range.
     - Classify Base Stage:
       - If `ath_distance_pct >= -2.5`: `🔥 IPO Base Breakout (At ATH)`
       - Else if `ath_distance_pct >= -15.0`: `🟡 Forming IPO Base (Consolidating near ATH)`
       - Else if `cmp < listing_price`: `❄️ Sub-IPO Drawdown (Trading Below Debut)`
       - Else: `📈 Post-Listing Consolidation`
   - Query `earnings_history` for upcoming announcements and historical quarter prints.
     - Generate clear lifecycle note (e.g. "Awaiting 1st Public Results (SEBI LODR 45-day window)" vs scheduled date).
   - Query `amfi_holdings` for mutual fund portfolios holding this stock.
   - Query `nse_shareholding` / `institutional_accumulation_cache` for promoter/FII/DII/public stakes.
   - Return structured dict.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_new_listings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/new_listings.py tests/test_new_listings.py
git commit -m "feat(new-listings): enrich recent additions with prices and add get_ipo_stock_detail"
```

---

### Task 2: API Endpoints & Stock API Integration

**Files:**
- Modify: `earnings_engine/api/stock_api.py`
- Modify: `earnings_engine/api/routers/watchlists.py`
- Test: `tests/test_ipo_api.py`

**Interfaces:**
- Consumes: `earnings_engine.data.new_listings.get_ipo_stock_detail`.
- Produces:
  - `stock_api.get_ipo_stock_detail(ticker, settings)`
  - Endpoint `GET /api/v1/market/ipo-detail/{ticker}` returning the full JSON payload.

- [ ] **Step 1: Write test for `/api/v1/market/ipo-detail/{ticker}`**

Create `tests/test_ipo_api.py`:
```python
from fastapi.testclient import TestClient
from earnings_engine.api.server import app


def test_get_ipo_detail_endpoint(monkeypatch):
    client = TestClient(app)
    
    # Mock stock_api.get_ipo_stock_detail
    monkeypatch.setattr(
        "earnings_engine.api.stock_api.get_ipo_stock_detail",
        lambda ticker, settings=None: {
            "success": True,
            "ticker": ticker.upper(),
            "company_name": "Acme IPO Ltd",
            "series": "EQ",
            "is_sme": False,
            "technical": {
                "cmp": 450.0,
                "listing_price": 400.0,
                "return_since_listing_pct": 12.5,
                "ath": 480.0,
                "ath_distance_pct": -6.25,
                "base_stage": "🟡 Forming IPO Base"
            },
            "earnings_lifecycle": {
                "past_earnings_count": 0,
                "sequence_label": "🌟 1st Result Debut",
                "next_earnings_date": None
            },
            "institutional": {
                "mutual_funds": []
            }
        }
    )

    response = client.get("/api/v1/market/ipo-detail/ACME.NS")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "ACME.NS"
    assert data["technical"]["cmp"] == 450.0
    assert data["technical"]["base_stage"] == "🟡 Forming IPO Base"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ipo_api.py -v`
Expected: FAIL (`404 Not Found`).

- [ ] **Step 3: Implement endpoint in `stock_api.py` and `watchlists.py`**

1. In `earnings_engine/api/stock_api.py`:
```python
def get_ipo_stock_detail(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    from earnings_engine.data.new_listings import get_ipo_stock_detail as _get_ipo_stock_detail
    return _get_ipo_stock_detail(ticker=ticker, settings=settings or Settings())
```
2. In `earnings_engine/api/routers/watchlists.py`:
```python
@router.get("/api/v1/market/ipo-detail/{ticker}")
async def get_ipo_detail_endpoint(ticker: str):
    """Retrieve deep IPO technical, earnings lifecycle, and institutional backing for a newly listed stock."""
    from earnings_engine.api import stock_api as _stock_api
    try:
        data = await asyncio.to_thread(_stock_api.get_ipo_stock_detail, ticker=ticker, settings=_settings)
        return data
    except Exception as e:
        logger.exception("Error fetching IPO detail for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ipo_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/api/stock_api.py earnings_engine/api/routers/watchlists.py tests/test_ipo_api.py
git commit -m "feat(api): add /api/v1/market/ipo-detail endpoint"
```

---

### Task 3: Split-Window HTML Templates Redesign

**Files:**
- Modify: `earnings_engine/reports/templates/dashboard/_new_additions.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_new_additions.html`

**Interfaces:**
- Consumes: UI styling tokens (`card`, `btn`, `badge`, `var(--font-mono)`).
- Produces: Master-detail grid `#newAdditionsSplitGrid` containing `#newAdditionsSplitLeft` (table) and `#newAdditionsSplitRight` (inspector card).

- [ ] **Step 1: Update Toolbar in both `_new_additions.html` files**
Add:
- Segment toggle buttons: `Mainboard (EQ)` (active default), `SME Segment (SM/ST)`, `All Listings`.
- Lookback window dropdown.
- Quick search input for newly listed tickers.
- Split layout toggle button `btnToggleNewAdditionsSplit` ("◫ 50-50 Split").

- [ ] **Step 2: Update Grid Container & Left Pane Table in both files**
- Wrap the main section in `<div id="newAdditionsSplitGrid" style="display:grid;grid-template-columns:minmax(0, 1.05fr) minmax(0, 0.95fr);gap:0.85rem;align-items:start;">`.
- Left pane contains the responsive table with columns: `TICKER & SERIES`, `COMPANY`, `LISTED`, `CMP (RETURN)`, `7D / 30D`, `ATH DIST`, `EARNINGS`, `ACTIONS`.

- [ ] **Step 3: Build Right Pane Sticky Inspector in both files**
In `#newAdditionsSplitRight`:
1. **Header & Trend Bar**: Ticker, Company, Series, Watchlist button, Full Intel link, CMP, Return Since Debut, 7D Return, 30D Return, ATH Distance, Market Cap.
2. **IPO Base & Technical Structure Card**: Setup badge (e.g. `🔥 IPO Base Breakout`), Listing Day Open/Close/High, ATH, Volume dry-up ratio.
3. **Debut Earnings & Reporting Lifecycle Card**: Sequence badge, Scheduled Board Meeting countdown or "Awaiting 1st Result", Past Results table, SEBI 45-day LODR guidance banner.
4. **Smart Money, Mutual Funds & Shareholding Card**: Shareholding percentage bar (Promoter / FII / DII / Public), table of mutual funds holding the stock, recent block/bulk deals.

- [ ] **Step 4: Verify template syntax & HTML validity**

Run: `pytest tests/test_templates.py` (or targeted template render test if present).

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/reports/templates/dashboard/_new_additions.html earnings_engine/reports/templates/hubs/dashboard/_new_additions.html
git commit -m "feat(ui): implement two-window split layout in new additions templates"
```

---

### Task 4: Frontend JavaScript Module Upgrade (`new_additions.js`)

**Files:**
- Modify: `earnings_engine/ui/js/modules/new_additions.js`

**Interfaces:**
- Consumes:
  - `/api/v1/market/recent-additions`
  - `/api/v1/market/ipo-detail/{ticker}`
  - `/api/v1/market/recent-additions/sync-watchlist`
- Produces:
  - `app.loadRecentAdditions()`
  - `app.setNewAdditionsSeriesFilter(series)`
  - `app.inspectNewAdditionStock(ticker, autoScroll)`
  - `app.toggleNewAdditionsSplitLayout()`

- [ ] **Step 1: Implement Segment Filtering & Default State**
- Default `_currentSeriesFilter = 'MAIN'` (Mainboard EQ).
- Support filtering by `MAIN`, `SME`, and `ALL`.
- Update segment button styles dynamically (active border/background).

- [ ] **Step 2: Implement Rich Left Table Rendering**
- Render each listing with:
  - Ticker with click handler: `onclick="app.inspectNewAdditionStock('${it.ticker}')"`.
  - Highlight selected row with active border/glow.
  - Formatted CMP and return since listing (`+24.5%` green, `-8.2%` red).
  - 7D and 30D return badges.
  - Distance from ATH (e.g. `-2.1%` highlighting near-breakout candidates).
  - Sequence badge (`🌟 1st Result Debut`, `🌱 2nd Result`).
  - "Inspect" action button.

- [ ] **Step 3: Implement `inspectNewAdditionStock(ticker)`**
- Set loading spinner in right-hand pane `#newAdditionsSplitRight`.
- Fetch `/api/v1/market/ipo-detail/{ticker}`.
- Populate:
  - Header: Ticker, Company, Series, Watchlist button, Full Intel link.
  - Price & Valuation bar: CMP, Debut Return %, 7D %, 30D %, ATH Distance %, Market Cap.
  - IPO Base & Technical card: Base classification badge, Listing High, All-Time High, All-Time Low, volume ratio.
  - Debut Earnings card: Sequence status, Next board meeting date, past quarter prints table, educational SEBI guidance text.
  - Smart Money card: Shareholding breakdown, mutual fund holders table, block deals.
- On initial load of listings, automatically inspect the first mainboard ticker.

- [ ] **Step 4: Implement Split Layout Toggle**
- `toggleNewAdditionsSplitLayout()` toggles between `grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr)` and `1fr`.
- Stores user preference in `localStorage.getItem('new_additions_split_layout')`.

- [ ] **Step 5: Verify module loads without errors in browser or node test**

- [ ] **Step 6: Commit**

```bash
git add earnings_engine/ui/js/modules/new_additions.js
git commit -m "feat(ui): add master-detail inspection and segment toggling in new_additions.js"
```

---

### Task 5: End-to-End Verification & Documentation

**Files:**
- Test: `tests/test_new_listings.py`
- Test: `tests/test_ipo_api.py`
- Modify: `docs/superpowers/specs/2026-09-12-recent-additions-ipo-tracker-design.md` (if any schema adjustments occur)

- [ ] **Step 1: Run targeted unit and API test suite**

Run: `pytest tests/test_new_listings.py tests/test_ipo_api.py -v`
Expected: ALL PASS.

- [ ] **Step 2: Run error ledger check**

Run: `python scripts/error_ledger.py check`
Expected: All health checks green.

- [ ] **Step 3: Final Commit and Push**

```bash
git commit -m "feat: complete recent market additions and ipo tracker two-window screen"
git push origin new_report
```
