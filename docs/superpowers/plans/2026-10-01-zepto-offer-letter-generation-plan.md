# Zepto Offer Letter Generation Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete Offer Letter generation subsystem in Zepto Hub with database persistence, Turso sync, dual-mode structured form + live in-place `contenteditable` A4 preview matching the Akash Kumar template (`C:\Users\91700\Downloads\Offer Letter - Akash Kumar.pdf`), candidate pipeline pre-fill, and high-fidelity 1-click A4 PDF export.

**Architecture:** A new SQLite table `zepto_offer_letters` registered with Turso cloud sync stores generated letters; FastAPI REST endpoints expose CRUD operations; a dedicated `#offers` tab in Zepto Hub provides a 2-column split view (left: reactive form controls & candidate loader; right: exact A4 paper simulation with direct click-to-edit on all text/tables/signatures); and `@media print` CSS formats the document cleanly into single-page A4 PDF output.

**Tech Stack:** Python 3.14, FastAPI, SQLite (libSQL / Turso sync), Jinja2, Tailwind CSS, Vanilla JS, HTML5 contenteditable, CSS Paged Media (`@page { size: A4 portrait; margin: 0; }`).

**Spec:** `docs/superpowers/specs/2026-10-01-zepto-offer-letter-generation-design.md`

## Global Constraints

- **Python Path Format**: Always use `./.venv/Scripts/python.exe` with forward slashes in all commands.
- **Turso Sync Rule**: `zepto_offer_letters` must be listed in `SYNC_TABLES` in `earnings_engine/data/turso_sync.py` and timestamps registered in `WATERMARK_CANDIDATE_COLUMNS`.
- **Zero Mock / Anti-Fabrication**: Do not inject synthetic/dummy placeholder candidate letters; initialize with clean Akash Kumar default structure if no candidate selected.
- **Exact Layout Match**: Replicate all elements of `Offer Letter - Akash Kumar.pdf`: company header, strictly confidential badge, metadata strip, salutation, 3x2 position matrix, 3-slab KPI compensation table with ₹17,000 / ₹15,600 / ₹14,200 total potentials, achievers bonus box, 7 key responsibilities, probation terms, notice period, and authorized signatory Jatin.
- **Git Commit Rule**: Follow conventional commits and include co-authorship attribution.

## Review Focus

- **Print / PDF single page invariant**: Ensure CSS media print styling fits cleanly on exactly one A4 page without spillover onto page 2.
- **Bidirectional editing sync**: Updating a form field (e.g. candidate name, joining date) updates the preview; editing in-place in the preview updates internal state for saving.
- **Turso sync schema compatibility**: Ensure table creation SQL in `zepto_db.py` uses SQLite syntax that mirrors cleanly to Turso libSQL.
- **Candidate pipeline linkage**: Clicking "📄 Offer" on a candidate in `_candidates.html` pre-fills their name, role, expected salary, and switches tab to `#offers`.
- **Special character encoding**: Rupee symbol `₹`, dashes `–`, and bullet points must render properly without character encoding corruption.

---

### Task 1: SQLite Schema & CRUD in `zepto_db.py` and Turso Sync Registration

**Files:**
- Modify: `earnings_engine/data/zepto_db.py`
- Modify: `earnings_engine/data/turso_sync.py`
- Test: `tests/test_zepto_offer_letters.py`

**Interfaces:**
- Consumes: `zepto_db._get_conn()`, `zepto_db._utc_now_iso()`
- Produces:
  - `zepto_db.init_zepto_db(settings=None)`: includes `zepto_offer_letters`
  - `zepto_db.save_offer_letter(data: dict, settings=None) -> dict`
  - `zepto_db.get_offer_letters(search: str = None, settings=None) -> list[dict]`
  - `zepto_db.get_offer_letter(letter_id: str, settings=None) -> dict | None`
  - `zepto_db.delete_offer_letter(letter_id: str, settings=None) -> bool`

- [ ] **Step 1: Write the failing unit tests for `zepto_offer_letters` schema and CRUD**

Create `tests/test_zepto_offer_letters.py` testing creation, saving, listing, fetching, and deleting offer letters.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_zepto_offer_letters.py -v`
Expected: FAIL (functions not yet implemented).

- [ ] **Step 3: Implement database schema and CRUD in `earnings_engine/data/zepto_db.py`**

Add table `zepto_offer_letters` to `init_zepto_db` and implement `save_offer_letter`, `get_offer_letters`, `get_offer_letter`, and `delete_offer_letter`.

- [ ] **Step 4: Register `zepto_offer_letters` in `earnings_engine/data/turso_sync.py`**

Add `"zepto_offer_letters"` to `SYNC_TABLES` list and ensure `updated_at`, `created_at` are tracked.

- [ ] **Step 5: Run tests and verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_zepto_offer_letters.py -v`
Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add earnings_engine/data/zepto_db.py earnings_engine/data/turso_sync.py tests/test_zepto_offer_letters.py
git commit -m "feat(zepto): add zepto_offer_letters schema, CRUD helpers, and Turso sync"
```

---

### Task 2: REST API Endpoints in `earnings_engine/api/routers/zepto.py`

**Files:**
- Modify: `earnings_engine/api/routers/zepto.py`
- Test: `tests/test_zepto_offer_letters.py`

**Interfaces:**
- Consumes: `zepto_db.get_offer_letters`, `zepto_db.get_offer_letter`, `zepto_db.save_offer_letter`, `zepto_db.delete_offer_letter`
- Produces:
  - `GET /api/v1/zepto/offer-letters` -> `{"success": True, "count": N, "items": [...]}`
  - `GET /api/v1/zepto/offer-letters/{letter_id}` -> `{"success": True, "letter": {...}}`
  - `POST /api/v1/zepto/offer-letters` -> `{"success": True, "letter": {...}}`
  - `DELETE /api/v1/zepto/offer-letters/{letter_id}` -> `{"success": True, "deleted": True}`

- [ ] **Step 1: Write failing API route tests in `tests/test_zepto_offer_letters.py`**

Add test cases using `httpx.AsyncClient` or FastAPI `TestClient` verifying all 4 endpoints.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_zepto_offer_letters.py -k "endpoint" -v`
Expected: FAIL (404 Not Found).

- [ ] **Step 3: Implement endpoints in `earnings_engine/api/routers/zepto.py`**

Add the 4 endpoints with proper validation, exception handling, and logging.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_zepto_offer_letters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add earnings_engine/api/routers/zepto.py tests/test_zepto_offer_letters.py
git commit -m "feat(zepto): implement offer letter REST endpoints in zepto router"
```

---

### Task 3: Jinja2 Templates (`_offers.html`, `index.html`, `_candidates.html`)

**Files:**
- Create: `earnings_engine/reports/templates/hubs/zepto/_offers.html`
- Modify: `earnings_engine/reports/templates/hubs/zepto/index.html`
- Modify: `earnings_engine/reports/templates/hubs/zepto/_candidates.html`

**Interfaces:**
- Consumes: Tailwind classes, dark glass styling, `@media print` rules
- Produces:
  - Nav button `#tabBtn-offers` in `index.html`
  - Main container `<main id="tabContent-offers">` in `index.html`
  - Full template in `_offers.html` with form panel (left) and A4 preview (right)
  - Quick action button `zeptoApp.createOfferForCandidate(candId)` in `_candidates.html`

- [ ] **Step 1: Create `earnings_engine/reports/templates/hubs/zepto/_offers.html`**

Build the high-fidelity A4 sheet matching `Offer Letter - Akash Kumar.pdf`:
- Dark glass toolbar: Saved Letters dropdown, "💾 Save", "📄 New", "📥 Download PDF / Print", "🔄 Reset".
- Form Panel on left with inputs for candidate title, name, joining date, role, location, salary, signatory name.
- Paper preview container on right (`w-[210mm] min-h-[297mm]` or responsive scaled container) styled like clean white bond paper with crisp dark slate/black typography, official headers, 3x2 details grid, KPI slab table, achievers bonus block, 7 bullet responsibilities, probation terms, signature block, and footer.
- Set `contenteditable="true"` on editable sections with subtle hover outlines.
- Include specialized `@media print` style block so `window.print()` isolates only the `#offerLetterDoc` and formats for 0-margin A4 printing.

- [ ] **Step 2: Update `index.html`**

Add `#tabBtn-offers` to the navigation sidebar and `{% include "hubs/zepto/_offers.html" %}` under `#tabContent-offers`.

- [ ] **Step 3: Update `_candidates.html`**

Add a `📄 Offer` action button to each candidate row calling `zeptoApp.prepareOfferFromCandidate(candId)`.

- [ ] **Step 4: Commit Task 3**

```bash
git add earnings_engine/reports/templates/hubs/zepto/_offers.html earnings_engine/reports/templates/hubs/zepto/index.html earnings_engine/reports/templates/hubs/zepto/_candidates.html
git commit -m "feat(zepto): add offer letter template, sidebar tab, and candidate action button"
```

---

### Task 4: Frontend Controller Logic in `zepto.js`

**Files:**
- Modify: `earnings_engine/ui/js/modules/zepto.js`

**Interfaces:**
- Consumes: REST endpoints `/api/v1/zepto/offer-letters`, `/api/v1/zepto/candidates`
- Produces:
  - `zeptoApp.switchTab('offers')` handling
  - `zeptoApp.initOfferLetterModule()`
  - `zeptoApp.loadOfferLetters()`
  - `zeptoApp.saveCurrentOfferLetter()`
  - `zeptoApp.loadOfferLetterById(id)`
  - `zeptoApp.prepareOfferFromCandidate(candId)`
  - `zeptoApp.syncFormToPreview()`
  - `zeptoApp.syncPreviewToForm()`
  - `zeptoApp.printOrDownloadOfferLetter()`
  - `zeptoApp.resetOfferLetterToDefault()`

- [ ] **Step 1: Add tab registration for `offers` in `zepto.js`**

Include `'offers'` in `this.switchTab` list and initialize offer letter module when tab opens.

- [ ] **Step 2: Implement state management and bidirectional synchronization**

Store `this.currentOfferLetter` state. When form inputs change, update preview elements. When user edits text directly inside preview (`input` event on `contenteditable`), sync internal state.

- [ ] **Step 3: Implement candidate prefill**

Fetch candidate details or find in `this.candidatesCache`, populate form, generate unique document reference (`RPS-ZEP-YYYY/MM-XX`), and switch tab to `#offers`.

- [ ] **Step 4: Implement API save, load, and delete**

POST to `/api/v1/zepto/offer-letters` with state and HTML snapshot. Populate the saved letters dropdown.

- [ ] **Step 5: Implement print & download trigger**

Trigger browser print with target styles (`window.print()`), ensuring clean single-page PDF generation.

- [ ] **Step 6: Commit Task 4**

```bash
git add earnings_engine/ui/js/modules/zepto.js
git commit -m "feat(zepto): add offer letter interactive controller, bidirectional sync, and print export"
```

---

### Task 5: End-to-End Verification & Hygiene Checks

**Files:**
- Test: `tests/test_zepto_offer_letters.py`
- Test: `tests/test_zepto_hub.py`
- Script: `scripts/error_ledger.py`

- [ ] **Step 1: Run complete test suite for Zepto Hub**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_zepto_offer_letters.py tests/test_zepto_hub.py -v`
Expected: All tests PASS.

- [ ] **Step 2: Verify error ledger hygiene**

Run: `./.venv/Scripts/python.exe scripts/error_ledger.py scan`
Expected: Clean scan with zero errors.

- [ ] **Step 3: Commit Task 5**

```bash
git add -A
git commit -m "test(zepto): complete offer letter verification and error ledger scan"
```
