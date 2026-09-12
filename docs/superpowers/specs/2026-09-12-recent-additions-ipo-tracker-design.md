# Specification: Recent Market Additions & IPO Tracker (Two-Window Split View)

**Date**: 2026-09-12  
**Status**: Approved  
**Topic**: Two-Window Layout for Recent Market Additions & IPO Tracker with Hybrid Stock Insights

---

## 1. Overview & Objectives

Upgrade the **Recent Market Additions & IPO Tracker** tab (`#tab-new-additions`) on the dashboard to match the responsive 50-50 / master-detail split-window paradigm established by Institutional Intelligence (`#tab-institutional`).

Key capabilities:
1. **Left Window (Master Table)**: Displays rich, point-in-time NSE listing data with Mainboard (`EQ`) as the default view and an optional toggle for SME equities (`SM`/`ST`), enriched with CMP, return since listing debut, 7D/30D returns, ATH distance (% from All-Time High), volume ratio, and public earnings sequence.
2. **Right Window (Sticky Stock Intelligence Pane)**: A dedicated live drilldown card displaying balanced hybrid insights:
   - Valuation & Debut Return Bar (Price, Debut Return %, 7D/30D %, ATH, 52W Range, Market Cap).
   - IPO Technical & Base Structure (IPO Base classification, breakout proximity, key reference levels, volume dry-up).
   - Debut Earnings & Reporting Lifecycle (Board meeting schedule, debut results pending vs. filed, past reported prints, SEBI reporting rule guidance).
   - Institutional & Smart Money Backing (AMFI Mutual Fund holdings, shareholding breakdown from exchange filings, block/bulk deal volume footprints).
3. **Earnings Availability Architecture**: Explicitly handles the post-IPO earnings lifecycle where fresh listings begin with 0 past quarterly results, schedules populate via NSE Event Calendar scraping, and reported figures file within SEBI's 45-day post-quarter window.

---

## 2. Backend & Data Architecture

### 2.1 Enriched Listing Ingestion (`earnings_engine/data/new_listings.py`)
Enhance `get_recent_nse_additions()` to join SQLite `price_history` and `market_caps`:
- Extract listing-day baseline price (earliest available open/close in `price_history`).
- Calculate current market price (CMP) and cumulative `return_since_listing_pct`.
- Calculate `ath_price` and `ath_distance_pct` (`((CMP - ATH) / ATH) * 100`).
- Calculate `return_7d_pct` and `return_30d_pct`.
- Calculate 5-day vs. 20-day volume ratio.
- Cross-reference `earnings_history` for debut sequence (`1st Result Debut`, `2nd Public Result`, etc.) and upcoming scheduled board meetings.

### 2.2 IPO Detail Endpoint (`/api/v1/market/ipo-detail/{ticker}`)
Create a consolidated endpoint in `earnings_engine/api/routers/watchlists.py` (and corresponding implementation in `stock_api.py`):
- Accepts clean ticker symbol (e.g. `SWIGGY.NS`).
- Queries:
  - Technicals & IPO Base analysis (stage classification: *IPO Base Formation*, *Breaking Out of Listing High*, *Testing Debut Support*, *Sub-IPO Drawdown*).
  - Earnings lifecycle & board meeting records from `earnings_history`.
  - Shareholding pattern (Promoter, FII, DII, Public) from `nse_shareholding` / `institutional_accumulation_cache`.
  - AMFI Mutual Fund holdings from `amfi_holdings` table.
  - Recent block/bulk deals from SQLite.
- Fast execution (<50ms) using indexed SQLite lookups without external network blocking.

---

## 3. Frontend Architecture & UI Components

### 3.1 Template Update (`_new_additions.html`)
Update both `earnings_engine/reports/templates/dashboard/_new_additions.html` and `earnings_engine/reports/templates/hubs/dashboard/_new_additions.html`:
- **Top Toolbar**:
  - Segment filter buttons: **Mainboard (EQ)** (Default active), **SME Segment (SM/ST)**, and **All Series**.
  - Lookback dropdown: 30D, 90D, 180D (Default), 365D.
  - Search bar + quick ticker select.
  - Split toggle button (`btnToggleNewAdditionsSplit`) allowing full-width vs. 50-50 split.
- **Split Container (`newAdditionsSplitGrid`)**:
  - Responsive CSS grid (`grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); gap: 0.85rem;`).
  - **Left Pane (`newAdditionsSplitLeft`)**:
    - Compact table containing: Ticker & Series badge, Company Name, Listing Date & Days on Market, CMP & Debut Return %, 7D/30D %, ATH Proximity, Earnings Sequence, Watchlist button, and Inspect button.
  - **Right Pane (`newAdditionsSplitRight`)**:
    - Sticky positioning (`position: sticky; top: 0.75rem; max-height: calc(100vh - 120px); overflow-y: auto`).
    - **Header & Metric Strip**: Ticker, Company Name, Series, Listing Date, Watchlist button, Link to `/stock/{ticker}`, Price, Debut Return %, 7D %, 30D %, ATH Distance %, Market Cap.
    - **IPO Base & Technical Card**: Setup diagnosis badge, Listing High, All-Time High, All-Time Low, volume trend.
    - **Debut Earnings & Board Meeting Card**: Sequence label, Next board meeting date, reported quarterly prints table, SEBI guidance banner.
    - **Smart Money & Fund Holdings Card**: Shareholding breakdown bar (Promoter / FII / DII / Public), table of top mutual funds holding the stock, and recent block/bulk deals.

### 3.2 JavaScript Module (`earnings_engine/ui/js/modules/new_additions.js`)
- `loadRecentAdditions()`: Fetches data, populates metrics, renders table, and auto-inspects the first mainboard ticker.
- `setSeriesFilter(mode)`: Filters between Mainboard (EQ), SME (SM/ST), and ALL.
- `inspectStock(ticker)`: Calls `/api/v1/market/ipo-detail/{ticker}`, updates right pane with animated load state and fills all 4 insight cards.
- `toggleSplitLayout()`: Toggles full-width vs split view with state persistence in `localStorage`.
- `addRecentAdditionToWatchlist(ticker)`: Seamless inline watchlist synchronization.

---

## 4. Error Handling & Invariants

1. **Anti-Fabrication**: If a fresh IPO has no mutual fund filings or no price history yet, display honest status indicators ("No Mutual Fund Filings on Record Yet", "Awaiting 1st Public Results") rather than placeholder numbers.
2. **Zero-Token Default**: Purely algorithmic and database-driven; no LLM tokens invoked automatically.
3. **Graceful Fallback**: If `price_history` is missing for a newly listed ticker, fallback to listing date metadata cleanly without crashing the table.
4. **Responsive Breakdown**: Below 1024px width, the grid stacks cleanly into a single column.
