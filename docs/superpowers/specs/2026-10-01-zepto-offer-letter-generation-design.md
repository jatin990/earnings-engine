# Technical Design Specification: Zepto Hub Offer Letter Generation Subsystem

> **Date**: 2026-10-01  
> **Target Subsystem**: `earnings_engine/data/zepto_db.py`, `earnings_engine/api/routers/zepto.py`, `earnings_engine/reports/templates/hubs/zepto/`, `earnings_engine/ui/js/modules/zepto.js`  
> **Source Sample**: `C:\Users\91700\Downloads\Offer Letter - Akash Kumar.pdf`

---

## 1. Overview & Objectives

The Zepto Hub operates the franchise dark store at Sector F Sainik Colony Jammu under **Rakeshparmeshwar & Sons Co.** partnered with Zepto. Recruiting and hiring staff (Pickpackers, Store Associates, Shift Incharges, Security Guards, Housekeeping) requires rapid, professional offer letter generation with precise compensation slabs, KPI incentives, and legal terms.

This subsystem provides:
1. A **dedicated workspace tab (`📄 Offer Letters`)** within Zepto Hub.
2. A **Dual-Mode Editor**:
   - Structured Form Controls for candidate attributes, dates, compensation slabs, and signatory.
   - Live A4 Document Preview with direct `contenteditable` editing on every element, cell, and paragraph.
3. High-fidelity **PDF Download & Print** styled to exact A4 print specifications matching the sample `Offer Letter - Akash Kumar.pdf`.
4. Persistence of offer letters in SQLite (`zepto_offer_letters`), with cloud Turso sync.
5. Direct candidate pipeline integration from the Candidates tab to prefill and issue offer letters seamlessly.

---

## 2. Template Specification (Akash Kumar Structure)

The generated document replicates the single-page A4 layout of `Offer Letter - Akash Kumar.pdf`:

### 2.1 Header & Branding
- **Company / Entity**:
  - `RAKESHPARMESHWAR & SONS CO.` (Bold Display)
  - `PARTNERED WITH ZEPTO (FRANCHISE STORE)`
- **Header Right**:
  - `OFFER LETTER` (Bold, uppercase)
  - `Strictly Confidential` badge / italic subtext
- **Metadata Bar**:
  - `Date: DD/MM/YYYY`
  - `To: Mr./Ms. [Candidate Name]`
  - `Location: Jammu, J&K`

### 2.2 Salutation & Body
- **Subject**: `Offer of Employment – [Position] / Store Associates`
- **Salutation**: `Dear [Candidate Name],`
- **Introductory Statement**:
  > "We are pleased to offer you employment with Rakeshparmeshwar & Sons Co., partnered with Zepto as a franchise, for the position of [Position]/Store Associates. We believe your skills and enthusiasm will be a valuable addition to our operational team."

### 2.3 Position & Deployment Matrix (3x2 Grid)
- `POSITION`: [Position] (e.g. Pickpackers)
- `DEPARTMENT`: Operations
- `EMPLOYMENT TYPE`: Full - Time
- `WORK LOCATION`: Sector F Sainik Colony Jammu
- `DATE OF JOINING`: [DD/MM/YYYY]

### 2.4 Compensation & KPI Slab Table (Jammu – Sainik Colony Zepto Store)
Structured table with columns: `KPI`, `SLAB 1 (KPI / AMOUNT)`, `SLAB 2 (KPI / AMOUNT)`, `SLAB 3 (KPI / AMOUNT)`:
- **BASIC PAY**: `Attendance Basis` | `₹12,000` | `₹12,000` | `₹12,000`
- **ATTENDANCE BONUS**: `26 or 27 Attendance (₹1,000)` | `1 Leave with Info (₹700)` | `2 Leave with Info (₹500)`
- **BEHAVIOUR**: `DHM Feedback (₹1,000)` | `DHM Feedback (₹700)` | `DHM Feedback (₹500)`
- **IPP**: `160+ (₹1,000)` | `140+ (₹700)` | `120+ (₹500)`
- **SLA**: `SLA 3 (₹2,000)` | `SLA 2 (₹1,500)` | `SLA 1 (₹700)`
- **TOTAL POTENTIAL**: `₹17,000` | `₹15,600` | `₹14,200`
- **Achievers Bonus Box**:
  - `★ Achievers Bonus (Additional Monthly Top Performer Incentive):`
  - `1st Best Performer: ₹1,500` | `2nd Best Performer: ₹1,000` | `3rd Best Performer: ₹700`

### 2.5 Key Responsibilities
7 operational bullet points:
1. Picking items accurately as per order from the store inventory.
2. Packing orders securely and ensuring high packing accuracy.
3. Ensuring timely order processing and quick store dispatch.
4. Maintaining strict cleanliness and organization in work area.
5. Following all safety, hygiene, and daily operational guidelines.
6. Assisting in regular inventory management and cycle stock checks.
7. Performing any other operational duties assigned by the supervisor or management.

### 2.6 Probation & General Terms
- **Probation Period**: 3 months from joining date.
- **General Terms & Notice**: Compliance with company rules; termination on misconduct; 1-month prior notice required for resignation, failing which 1 month salary may be deducted as per management decision.

### 2.7 Signatures & Footer
- **Signatory**: `For Rakeshparmeshwar & Sons Co.`
- **Signatory Signature Block**: `Jatin` (Script/Bold) + `Authorized Signatory (Jatin)`
- **Footer**:
  - Left: `Delivering Excellence, Every Time. | Partnered with Zepto`
  - Right: `Document Ref: RPS-ZEP-YYYY/MM-XX | Page 1 of 1`

---

## 3. Database Architecture & Turso Sync

### 3.1 SQLite Schema: `zepto_offer_letters`
```sql
CREATE TABLE IF NOT EXISTS zepto_offer_letters (
    id TEXT PRIMARY KEY,
    cand_id TEXT,
    candidate_name TEXT NOT NULL,
    title TEXT DEFAULT 'Mr.',
    role TEXT NOT NULL,
    department TEXT DEFAULT 'Operations',
    work_location TEXT DEFAULT 'Sector F Sainik Colony Jammu',
    date_of_joining TEXT NOT NULL,
    employment_type TEXT DEFAULT 'Full - Time',
    doc_ref TEXT,
    basic_pay REAL DEFAULT 12000.0,
    total_potential REAL DEFAULT 17000.0,
    signatory_name TEXT DEFAULT 'Jatin',
    signatory_title TEXT DEFAULT 'Authorized Signatory',
    data_json TEXT, -- Full serialized state (slabs, bullets, notes)
    html_snapshot TEXT, -- Cached HTML snapshot for exact reproduction
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 3.2 Remote DB Sync Integration
- Registered in `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`.
- Watermark candidates: `updated_at`, `created_at`.

---

## 4. REST API Contract

Mounted on `earnings_engine/api/routers/zepto.py`:
- `GET /api/v1/zepto/offer-letters`: List all generated offer letters (sorted by `created_at` desc).
- `GET /api/v1/zepto/offer-letters/{letter_id}`: Retrieve a specific offer letter and its full configuration.
- `POST /api/v1/zepto/offer-letters`: Create or update an offer letter record.
- `DELETE /api/v1/zepto/offer-letters/{letter_id}`: Delete an offer letter.

---

## 5. UI & Frontend Architecture

### 5.1 Subtab Placement
- File: `earnings_engine/reports/templates/hubs/zepto/_offers.html`.
- Included in `index.html` under `<main id="tabContent-offers">` and sidebar item `tabBtn-offers`.

### 5.2 Responsive 2-Column Split Workspace
- Left Column (`w-full xl:w-[380px]`):
  - Saved letter selector & quick load.
  - Candidate quick-fill picker.
  - Form fields: Name, Title, Date, Joining Date, Role, Department, Location, Slabs, Signatory.
  - Action buttons: "💾 Save Letter", "🔄 Reset to Default Template", "📥 Download PDF / Print".
- Right Column (`flex-1`):
  - A4 Document Canvas with realistic paper shadow and white background styling.
  - All content editable (`contenteditable="true"`), with seamless bi-directional synchronization to the form.
  - `@media print` CSS block that strips all navigation, sidebars, and hub borders, and formats the document perfectly into A4 dimensions (`210mm x 297mm`).

---

## 6. Verification & Test Plan
1. `tests/test_zepto_offer_letters.py`:
   - Test table creation in test SQLite database.
   - Test CRUD functions in `zepto_db.py`.
   - Test FastAPI router endpoints (`/api/v1/zepto/offer-letters`).
2. Browser validation:
   - Live editing in form updates A4 preview.
   - In-place editing in preview preserves clean markup.
   - Print preview renders exactly on 1 page without spillover.
