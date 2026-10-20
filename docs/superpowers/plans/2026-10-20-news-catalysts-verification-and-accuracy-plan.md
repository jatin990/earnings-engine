# News Catalysts Verification, Corroboration & Accuracy Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate false positives, market noise, and speculative clickbait from the news intelligence system by building a deterministic verification and multi-source corroboration engine for corporate news catalysts.

**Architecture:**
1. **Source Tiering & Credibility Scoring**:
   - Tier 1 (Official / Primary): NSE/BSE corporate filings, exchange disclosure announcements, press releases filed on NEAPS/BSE Online.
   - Tier 2 (Major Financial Press): Economic Times, Business Standard, LiveMint, Reuters India, Bloomberg.
   - Tier 3 (Aggregators / Syndication): Google News RSS, MoneyControl syndicates (require secondary corroboration).
2. **Deterministic Exchange Disclosure Corroboration**:
   - Cross-reference news claiming "Order Win", "Capex", or "Regulatory Approval" against the official `corporate_disclosures` or `exchange_filings` table.
   - Assign verification status: `EXCHANGE_VERIFIED` (100% confidence), `CORROBORATED` (multiple independent Tier-2 sources), or `UNVERIFIED_SINGLE_SOURCE`.
3. **Semantic Staleness & Noise Filter**:
   - Enforce strict detection of re-circulated news (e.g., articles summarizing an old Q1 event being published in Q3).
   - Filter out speculative retail articles, trading blogs, and sponsored promotional content.

**Tech Stack:** Python 3.14, SQLite (WAL mode), Regex/NLP pattern matching, Feedparser, HTTPX.

---

## Global Constraints

- **Anti-Hallucination**: News catalysts must cite an exact headline, publication timestamp, source domain, and direct URL. Never infer or invent catalysts.
- **Strict Verification Filter**: In high-conviction tabs (like Results Ledger or Breakout Radar), only display news tagged as `EXCHANGE_VERIFIED` or `CORROBORATED`.
- **Deduplication Contract**: Multiple articles covering the identical event within a 48-hour window must be collapsed into a single parent event with multi-source attribution links.

---

## Review Focus

1. **Opinion & Analyst Commentary vs Corporate Actions**: Ensure an analyst's opinion (e.g. "Stock XYZ could win large order") is never tagged as an actual corporate order win.
2. **Re-cycled / Stale Wire Reports**: Aggregators often republish disclosures from weeks ago; timestamps must be checked against original filing timestamps.
3. **Entity Disambiguation**: Avoid matching tickers like `IDEA.NS` with general generic uses of the word "idea" in headlines.
4. **Impact Misattribution**: Downward regulatory actions (e.g., USFDA warning letter or Form 483 with 10 observations) must strictly be flagged as `BEARISH`, never `BULLISH`.
5. **No Token Bloat**: Corroboration and deduplication must run via deterministic hashing (`title_simhash`, entity matching) without expensive LLM loops.

---

## Tasks

### Task 1: Source Tiering & Exchange Disclosure Cross-Referencing

**Files:**
- Modify: `earnings_engine/data/catalysts_news.py:200-350`
- Modify: `earnings_engine/data/news_sources.py`
- Test: `tests/test_news_source_tiering.py`

- [ ] **Step 1: Write test for source credibility ranking and exchange filing match**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement Tier 1/2/3 classification and exchange cross-reference**
- [ ] **Step 4: Run test to verify pass**
- [ ] **Step 5: Commit source tiering**

---

### Task 2: Multi-Source Deduplication & Semantic Event Clustering

**Files:**
- Modify: `earnings_engine/data/catalysts_news.py:500-650`
- Test: `tests/test_news_event_clustering.py`

- [ ] **Step 1: Write test verifying that 3 articles for the same order win collapse into one event**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement Jaccard/SimHash title clustering with 48h temporal window**
- [ ] **Step 4: Run test to verify pass**
- [ ] **Step 5: Commit deduplication engine**

---

### Task 3: Analyst Commentary vs Real Catalyst Disambiguation

**Files:**
- Modify: `earnings_engine/data/catalysts_news.py:700-820`
- Test: `tests/test_catalyst_disambiguation.py`

- [ ] **Step 1: Write test verifying that "Analyst predicts order win" is NOT classified as `ORDER_WIN`**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Refine keyword dictionaries with negative regex guards (e.g., `(?!could|may|likely|seen winning)`)**
- [ ] **Step 4: Run test to verify pass**
- [ ] **Step 5: Commit disambiguation guards**
