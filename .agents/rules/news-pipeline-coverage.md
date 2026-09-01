# News Pipeline Coverage & Integrity Rule

## Broadband Source Requirement
The news ingestion pipeline MUST include both:
1. **Ticker-specific sources** (yfinance, Yahoo RSS, Google News RSS) for targeted depth
2. **Market-wide broadband sources** (MoneyControl RSS, ET Markets RSS, LiveMint RSS, NDTV Profit RSS, BSE/NSE filing APIs) for comprehensive coverage

Never rely solely on ticker-specific fetching. A stock not on a watchlist must still have its high-impact news discoverable through broadband feeds.

## Multi-Stock Impact
A single news headline can affect multiple tickers (e.g., "Adani Group eyes steel acquisition" affects ADANIENT, TATASTEEL, JSWSTEEL). The pipeline MUST:
- Extract ALL affected tickers from each headline
- Create fan-out records mapping one catalyst to multiple tickers
- Distinguish PRIMARY vs SECONDARY vs SECTOR_PEER impact

## AI Triage on Ingestion
All newly ingested news items (not cached/existing) MUST be auto-triaged by AI (OmniRoute Gemini Flash) to determine:
- Market impact score (0-100)
- Direction (BULLISH/BEARISH/NEUTRAL)
- Whether it's genuinely new or recycled/republished
- All affected tickers

## New vs Recycled Detection
Every headline must be classified as NEW_PUBLICATION, REPUBLICATION, or SAME_EVENT_DIFFERENT_SOURCE before being scored and displayed.
