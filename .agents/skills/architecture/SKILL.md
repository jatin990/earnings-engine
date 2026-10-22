---
name: architecture
description: Architectural design, refactoring, and anti-bloat best practices for FastAPI, SQLite/Turso, Point-in-Time quant features, and modular UI. Use whenever designing, redesigning, or refactoring code.
---

# Architecture & Anti-Bloat Engineering Spec

Use this skill whenever designing new components, expanding existing subsystems, or refactoring code.

---

## 1. File Size & Complexity Boundaries (Anti-Bloat Governance)

To keep code maintainable and prevent tool degradation:
- **Maximum File Length**: Keep files under **500 lines** (hard ceiling at 650 lines). If a file approaches 500 lines, extract cohesive sub-modules or helpers.
- **Single Responsibility Principle**:
  - `*_engine.py`: Pure computational / statistical / mathematical operations. No direct DB schema alterations or HTTP routing.
  - `*_router.py`: Route mapping, input validation (Pydantic), dependency injection, and HTTP response serialization only.
  - `*_sync.py`: Data replication, cloud egress, external API client synchronization.
- **Zero Monolithic Scripts**: Never create scripts combining scraping, calculation, database creation, and report formatting in a single 1,000+ line file.

---

## 2. FastAPI & API Layer Architecture

- **Literal Route Precedence**: Always place static endpoints (`/summary`, `/watchlist`, `/scan`) before parameterized endpoints (`/{symbol}`, `/{date}`). FastAPI matches routes sequentially.
- **Zero Automated LLM Execution**:
  - Default token consumption on endpoint invocation is **0**.
  - Never trigger autonomous LLM inference on route fetch, tab switch, or table render. LLM inference must be explicitly requested via dedicated `/analyze` or `/synthesize` actions with cache validation.
- **Consistent Response Envelope**:
  - Prefer flat, type-annotated response models or explicit dict structures.
  - Indian tickers require `.NS` suffix (`RELIANCE.NS`); US tickers have no suffix (`NVDA`). Always route through `market_of(ticker)`.
- **Honest Nulls & Status Codes**:
  - Return `None` / `[]` with metadata (`status: "market_closed"`, `data_available: false`) instead of synthetic defaults or 500 errors when data is legitimately missing.

---

## 3. Database Layer (SQLite & Remote Turso/libSQL)

- **Connection Pragmas**:
  - Every connection must enforce:
    ```sql
    PRAGMA journal_mode = WAL;
    PRAGMA busy_timeout = 5000;
    PRAGMA synchronous = NORMAL;
    ```
- **Sync Registration Contract**:
  - Whenever introducing a new SQLite table:
    1. Register the table in `SYNC_TABLES` inside `earnings_engine/data/turso_sync.py`.
    2. Register its date/timestamp column in `WATERMARK_CANDIDATE_COLUMNS` (and `DATE_ONLY_COLUMNS` if formatted `YYYY-MM-DD`).
    3. Use `INSERT OR IGNORE` or `ON CONFLICT DO UPDATE` for bidirectional replication compatibility.
- **Resilient Fallback**: Always wrap remote Turso calls with local SQLite fallback to guarantee offline/local operability.

---

## 4. Quantitative & Data Contracts (Point-in-Time)

- **Zero Future Leakage**:
  - For any event occurring on date $T$, training/feature data must strictly be filtered to:
    $$\text{bars} \le T-1$$
- **Reaction Return Calculation**:
  $$\text{reaction} = \left(\frac{\text{close}(T+1)}{\text{close}(T-1)}\right) - 1$$
- **Labeling Standard**:
  - Label is `1` if $\text{reaction} > 0$ else `0`.
  - Return `None` if either $T-1$ or $T+1$ bar is missing or the calendar gap exceeds 10 days.

---

## 5. Frontend & UI Architecture (Modular Web Client)

- **Directory-Based Modularity**:
  - JavaScript modules reside in `earnings_engine/ui/js/modules/*.js`.
  - Keep modules scoped to a single drawer, scanner, or hub. Max module size: **400 lines**.
- **Template Alignment**:
  - All shared dashboard components must be kept synchronized between `reports/templates/dashboard/` and `reports/templates/hubs/dashboard/`.
- **No Inline Scripts**:
  - Avoid inline `<script>` blocks inside Jinja2 HTML templates. Wire event listeners and handlers inside modular JS files loaded via standard module imports.
- **Baseline Visibility**:
  - Every metric card or delta badge must display its baseline (`7D: +3.2%`, `Surge: 2.1x (5D vs 63D avg)`). Never display naked percentage changes.
