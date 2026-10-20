# Earnings Data Integrity & Official Exchange Filings (NSE/BSE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish 100% authoritative earnings calendar and financial metrics provenance by sourcing directly from official NSE/BSE regulatory disclosures, eliminating speculative/unconfirmed third-party dates, and storing verifiable filing metadata.

**Architecture:**
1. Upgrade `earnings_engine/data/earnings.py` to enforce a strict **Exchange-First Ingestion Pipeline**:
   - Primary: NSE Event Calendar API (`https://www.nseindia.com/api/event-calendar`)
   - Secondary: BSE Board Meetings Announcements API & Corporate Actions feed
   - Quarantine/Filter: Third-party algorithmic date projections (e.g., yfinance estimated earnings dates) are flagged as `UNCONFIRMED_ESTIMATE` and never masquerade as confirmed corporate announcements.
2. Extend `earnings_history` schema with verification metadata: `exchange_source` (`NSE`, `BSE`, `SEC`), `filing_url`, `board_meeting_purpose`, `confirmation_status` (`CONFIRMED`, `TENTATIVE`).
3. Build an automated reconciliation job to audit and cross-verify reported EPS, Net Profit, and Revenue against official exchange XML/PDF filing attachments.

**Tech Stack:** Python 3.14, SQLite (WAL mode), Requests/HTTPX with NSE/BSE session rotators, Pandas.

---

## Global Constraints

- **Official Source Mandate**: For all Indian equities (`.NS`), upcoming earnings dates must originate from an official exchange regulatory disclosure (NSE or BSE).
- **Anti-Fabrication**: If neither NSE nor BSE has an official board meeting filing on record, display `Date Unconfirmed (Projected: YYYY-MM-DD)` with a warning badge. Never fabricate a confirmed status.
- **Zero-Token Verification**: Validation pipelines must use deterministic regex, exchange filing numbers, and status codes. No probabilistic LLM calls in core ingestion loops.

---

## Review Focus

1. **Board Meeting Purpose Filtering**: Corporate board meetings for dividends, fund raising, or warrants must not be misclassified as earnings announcements unless financial results are explicitly in the agenda.
2. **Postponements & Rescheduling**: When a company files a revised board meeting date to NSE/BSE, the older date must be superseded atomically.
3. **Session Timing Distinction**: Accurately capture whether results are scheduled for Pre-Market (`BM: Pre`), During Market, or Post-Market (`BM: Post`).
4. **Standalone vs Consolidated Confusion**: Financial metrics must specify whether they reflect Standalone or Consolidated statements.
5. **Purge of Stale Projections**: Ensure legacy rows with `source='yfinance'` having dates in the future are purged whenever an official NSE/BSE schedule is synced.

---

## Tasks

### Task 1: Extend `earnings_history` Schema for Filing Provenance

**Files:**
- Modify: `earnings_engine/data/earnings.py:20-65`
- Modify: `earnings_engine/data/turso_sync.py:35-60`
- Test: `tests/test_earnings_provenance_schema.py`

- [ ] **Step 1: Write test for new provenance columns**
  - Verify `exchange_source`, `confirmation_status`, `board_meeting_purpose`, `filing_id` columns exist and default properly.
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Add schema migration and table alter logic**
- [ ] **Step 4: Run test to verify pass**
- [ ] **Step 5: Commit schema extension**

---

### Task 2: Official NSE Financial Results Ingestion Overhaul

**Files:**
- Modify: `earnings_engine/data/earnings.py:378-485`
- Test: `tests/test_nse_calendar_ingest.py`

- [ ] **Step 1: Write test validating strict purpose keywords and rejection of non-results board meetings**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement strict purpose classification and session timing extraction (Pre/Post market)**
- [ ] **Step 4: Run test to verify pass**
- [ ] **Step 5: Commit NSE calendar overhaul**

---

### Task 3: Multi-Exchange BSE Corporate Filings Reconciliation

**Files:**
- Modify: `earnings_engine/data/earnings.py:487-680`
- Test: `tests/test_bse_calendar_ingest.py`

- [ ] **Step 1: Write test verifying BSE board meeting ingestion for exclusive and dual-listed stocks**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement BSE board meeting parser with conflict resolution (NSE precedence for dual-listed)**
- [ ] **Step 4: Run test to verify pass**
- [ ] **Step 5: Commit BSE calendar reconciliation**

---

### Task 4: Invalidation and Purge of Unconfirmed Algorithmic Dates

**Files:**
- Modify: `earnings_engine/data/earnings.py:298-370`
- Test: `tests/test_unconfirmed_dates_purge.py`

- [ ] **Step 1: Write test verifying that `upcoming_earnings` marks unconfirmed yfinance dates as `TENTATIVE` and prioritizes official filings**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement filtering and badge attribution**
- [ ] **Step 4: Run test to verify pass**
- [ ] **Step 5: Commit date validation gates**
