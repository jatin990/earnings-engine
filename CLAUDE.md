# CLAUDE.md — Nexus Intelligence Platform
> Single source of truth for architectural invariants, data contracts, and operational standards.

## 1. Non-Negotiable Engineering Invariants

### 1.1 Strict Point-in-Time (PIT) Guarantee (features/, dataset.py, backtest/)
- Zero future leakage. For any event on date $T$, filter historical price bars strictly up to $T-1$:
  `prices_pit = prices.loc[prices.index <= asof_date]`
- **Reaction Return**: $\text{reaction} = \left(\frac{\text{close}(T+1)}{\text{close}(T-1)}\right) - 1$.
- **Label**: `1` if $\text{reaction} > 0$ else `0`. Return `None` if either $T-1$ or $T+1$ bar is missing or gap $> 10\text{d}$.

### 1.2 Database & Turso Sync Contract (earnings_engine/data/)
Whenever a new SQLite table is created:
1. Register table name in `SYNC_TABLES` (`earnings_engine/data/turso_sync.py`).
2. Add timestamp/date column to `WATERMARK_CANDIDATE_COLUMNS` (and `DATE_ONLY_COLUMNS` if formatted `YYYY-MM-DD`).
3. Use `INSERT OR IGNORE` for replication compatibility. Always wrap Turso network calls with local SQLite fallback.

### 1.3 Anti-Fabrication & Honest Empty States
- Zero dummy/mock data. Never generate synthetic numbers (`hashlib.md5(...) % N`) in production routes or cards.
- If data is unavailable, return `None`, `0.0`, or `[]` with an honest status tag (`status: "market_closed"`, `No Filings On Record`).

### 1.4 Explicit Timeframe & Baseline Badging
- Every metric, delta, surge, and prediction rendered in API responses and UI cards MUST state its baseline:
  - Return: `7D: +4.2%`, `52W High / Low` (never bare `+X%`)
  - Volume: `Surge: 2.4x (5D vs 63D avg)`
  - Freshness: Explicit badge (`Live Quote`, `EOD Snapshot`, timestamp)

### 1.5 FastAPI Precedence & Route Contracts (earnings_engine/api/)
- Always define literal/static routes before parameterized routes (e.g. `/quotes` before `/{symbol}`).
- Equities: Indian equities require `.NS` (`TCS.NS`), US equities have no suffix (`AAPL`). Resolve via `market_of(ticker)`.
- On-Demand AI: Default 0 tokens. Zero automated LLM inference on page load, modal open, or table render.

### 1.6 Frontend & Template Architecture (reports/, ui/)
- Canonical dashboard templates live under `reports/templates/hubs/dashboard/<name>.html`.
- Keep UI JS modular under `earnings_engine/ui/js/modules/*.js`.

## 2. Delivery & Operations Protocol
- **Git Branch**: Work directly on `new_report`. Always commit and push directly to `origin/new_report` upon task completion. Follow conventional commits (`feat:`, `fix:`) + co-authorship.
- **Error Ledger**: Check `scripts/error_ledger.py open` before starting; run `scripts/error_ledger.py scan` upon completion.
- **Python Interpreter**: Always execute Python tools via `./.venv/Scripts/python.exe` (forward slashes in Git Bash).
- **Targeted Testing**: Run targeted tests only (`./.venv/Scripts/python.exe -m pytest tests/<file>.py -k "<test>"`). Never run full/E2E suites during iteration.
