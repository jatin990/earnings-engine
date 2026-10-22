---
name: fastapi-route-authoring
description: FastAPI route design, route precedence, zero-token AI default, equity market resolution (.NS suffix), and anti-fabrication data envelopes. Use when creating or updating API endpoints.
---

# FastAPI Route Authoring & Contract Protocol

Use this skill whenever adding new routes, designing API payloads, or modifying backend endpoints.

---

## 1. Literal Route Precedence (No Route Shadowing)

FastAPI evaluates routes in the exact order they are registered. Always declare static and literal endpoints before parameterized paths:

```python
# CORRECT: Static routes first
@router.get("/summary")
async def get_summary(): ...

@router.get("/watchlist")
async def get_watchlist(): ...

# Parameterized routes LAST
@router.get("/{ticker}")
async def get_stock_detail(ticker: str): ...
```

---

## 2. Zero-Token AI Contract

- **Default Token Consumption is 0**:
  - GET routes for tables, dashboards, drawers, and cards must NEVER trigger background or immediate LLM inference.
  - LLM calls must be isolated in explicit action routes (`/analyze`, `/synthesize`, `/generate-trade-plan`).
- **Deterministic Caching**:
  - Always check cache before calling LLM providers.
  - Hash prompt inputs and model parameters; store outputs in SQLite with a defined TTL.

---

## 3. Equity Ticker & Market Resolution

Always resolve tickers using `market_of(ticker)`:
- Indian equities require the `.NS` suffix for Yahoo Finance / broker APIs (e.g. `RELIANCE.NS`, `HDFCBANK.NS`).
- US equities have no suffix (e.g. `NVDA`, `AAPL`).
- Indices use explicit symbols (e.g. `^NSEI`, `^NSEBANK`).

---

## 4. Honest Data Envelopes (Anti-Fabrication)

- Never substitute missing data with random or synthetic numbers (`hashlib.md5(...) % N`).
- When data is missing, market is closed, or upstream API fails:
  ```json
  {
    "status": "market_closed",
    "data_available": false,
    "metrics": null,
    "items": []
  }
  ```
- Return structured error responses or honest empty states instead of 500 crashes.

---

## 5. Verification Checklist

1. Static route is placed before parameterized route in router file.
2. New router is registered in `earnings_engine/api/app.py`.
3. Targeted test passes:
   ```bash
   ./.venv/Scripts/python.exe -m pytest tests/test_api_*.py -k "<endpoint_name>"
   ```
