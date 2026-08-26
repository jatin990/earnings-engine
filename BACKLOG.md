# Earnings Engine — Backlog & Roadmap

## 1. Hub Decoupling & Modularization
- [ ] **Decouple Ancillary Hubs**: Extract `trips` (`/trips`), `net_worth` (`/net-worth`), and `credit_cards` (`/credit-cards`) into standalone modular packages or separate micro-repos to keep `earnings-engine` purely focused on institutional market intelligence and predictive AI.
- [ ] **Nexus Gateway Route Isolation**: Update router mounting in `server.py` so decoupled modules can run as optional plugins or standalone services.

## 2. Institutional Flows & Data Feeds
- [ ] **Automated Exchange Bulk/Block Feed**: Connect scheduled ingestion pipeline to live NSE/BSE bulk and block deal API feeds.
- [ ] **NSE Corporate Filing Scraper**: Automate quarterly shareholding pattern ingestion directly from NSE India corporate announcement filings.
- [ ] **Historical Holding Comparisons**: Add multi-year YoY and QoQ institutional trend charts for all FII/DII funds.

## 3. Consensus Engine & Forecasting
- [ ] **Kronos AI Sequence Visualizer**: Add interactive sequence playback for 14-day Kronos neural price trajectory forecasts.
- [ ] **Consensus Performance Auto-Settlement**: Automated cron settlement evaluating AI target prices and stop losses against realized post-earnings reaction returns.

## 4. UI/UX & Performance Polish
- [ ] **Client-side IndexedDB Caching**: Cache heavy quote and pattern responses for instant offline tab switching.
- [ ] **Virtualized Table Rendering**: Implement windowed virtual scrolling for tables exceeding 500 rows.
