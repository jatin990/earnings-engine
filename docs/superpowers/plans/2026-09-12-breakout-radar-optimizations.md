# Breakout Radar Optimizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize the Breakout Radar workflow for accuracy (intraday spike tracking), performance (NumPy vectorization), and strictly on-demand AI compute with persistent caching.

**Architecture:** We will modify `earnings_engine/data/breakout_scanner.py` across three independent domains. First, we will adjust `is_late` calculations to use `daily_high`. Second, we replace slow Pandas functions with NumPy representations in tight loops. Lastly, we wrap the AI logic in `generate_breakout_ai_reasoning` to read and write to the existing SQLite `data_json` field.

**Tech Stack:** Python, Pandas, NumPy, SQLite

**Spec:** N/A (Based on brainstormed improvements)

## Global Constraints

- **Strict zero-token default for AI:** No automated background usage unless specifically requested.
- **SQLite Compatibility:** All JSON DB reads/writes must fallback gracefully if raw text parsing fails.
- Do not break existing API contracts or frontend models.

---

### Task 1: Accuracy - Intraday High Late Detection

**Files:**
- Modify: `earnings_engine/data/breakout_scanner.py`

**Interfaces:**
- Consumes: The `high_series` provided to strategy functions (`_score_classic_technical`, `_score_nse_delivery_absorption`, `_score_fo_call_wall`, `_score_volume_profile_vah`, `_score_donchian_squeeze`).
- Produces: More accurate `entry_delay_pct` and `is_late` flags in the candidate dictionary.

- [ ] **Step 1: Update `is_late` in all 5 strategies**

Find the block containing `is_late = bool(ideal_entry_price and signal_price > ideal_entry_price * 1.002)` inside `earnings_engine/data/breakout_scanner.py`.

Update it to calculate `daily_high` and use it to determine maximum excursion:
```python
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if is_late else 0.0
```
*Note: I have already applied this fix locally in the current tree! Your job as the executing agent is just to verify the logic is correctly implemented in `breakout_scanner.py`, run tests, and commit.*

- [ ] **Step 2: Run tests to verify logic**

Run: `pytest tests/test_breakout_scanner.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add earnings_engine/data/breakout_scanner.py
git commit -m "feat(breakout): update late detection to use intraday high"
```

---

### Task 2: Performance - Vectorized Operations

**Files:**
- Modify: `earnings_engine/data/breakout_scanner.py`

**Interfaces:**
- Consumes: `closes` and `volumes` Pandas Series generated dynamically during polling loops.
- Produces: Faster execution of the scanner via `np.ndarray` (values).

- [ ] **Step 1: Vectorize Resistance Proximity**

Inside `_score_resistance_proximity(closes: pd.Series)`:
Replace:
```python
    high = float(closes.tail(window).max())
```
With:
```python
    high = float(closes.values[-window:].max())
```

- [ ] **Step 2: Vectorize Volume Surge**

Inside `_score_volume_surge(volumes: pd.Series)`:
Replace:
```python
    avg_20 = float(volumes.tail(21).iloc[:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
    today = float(volumes.iloc[-1])
```
With:
```python
    vals = volumes.values
    avg_20 = float(vals[-21:-1].mean()) if len(vals) >= 21 else float(vals.mean())
    today = float(vals[-1])
```

- [ ] **Step 3: Vectorize Price Compression**

Inside `_score_price_compression(closes: pd.Series)`:
Replace:
```python
    daily_range = closes.pct_change().abs()
    atr_pct = float(daily_range.tail(14).mean()) * 100   # as % of price
```
With:
```python
    vals = closes.values[-15:]
    daily_range = abs(vals[1:] - vals[:-1]) / vals[:-1]
    atr_pct = float(daily_range.mean()) * 100   # as % of price
```

*Note: These changes were already staged and committed to the tree earlier. Just review `breakout_scanner.py` to ensure it looks correct, run tests, and commit any further refinements you make.*

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_breakout_scanner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/breakout_scanner.py
git commit -m "perf(breakout): vectorize tight scanner loops using numpy arrays"
```

---

### Task 3: AI Compute - Persistent Caching

**Files:**
- Modify: `earnings_engine/data/breakout_scanner.py`

**Interfaces:**
- Consumes: `generate_breakout_ai_reasoning` parameters
- Produces: Zero-token cache hits by reading/writing to `breakout_radar.data_json`.

- [ ] **Step 1: Check Database Cache Before Scoring**

Inside `generate_breakout_ai_reasoning`, right under the in-memory cache check, ensure we check the DB before generating quantitative parameters or prompting the LLM. 
```python
    # Persistent DB Cache Check
    try:
        from earnings_engine.data.db import get_db_connection
        conn = get_db_connection(settings)
        cur = conn.execute("SELECT data_json FROM breakout_radar WHERE ticker = ? ORDER BY composite_score DESC LIMIT 1", (sym,))
        row = cur.fetchone()
        if row and row[0]:
            import json
            data = json.loads(row[0])
            if "ai_reasoning" in data:
                ai_data = data["ai_reasoning"]
                gen_at = ai_data.get("generated_at")
                if gen_at:
                    from datetime import datetime, timezone
                    gen_dt = datetime.fromisoformat(gen_at)
                    now_dt = datetime.now(timezone.utc)
                    if (now_dt - gen_dt).total_seconds() < 12 * 3600:
                        _AI_REASONING_CACHE[cache_key] = ai_data
                        return ai_data
        conn.close()
    except Exception as e:
        logger.debug("[BREAKOUT-AI] DB cache read failed for %s: %s", sym, e)
```

- [ ] **Step 2: Save Result to Database Cache**

At the end of `generate_breakout_ai_reasoning`, right before returning `output_dict`, store it in the SQLite JSON:
```python
    # Store in DB to prevent token/compute waste on restart
    try:
        conn = get_db_connection(settings)
        cur = conn.execute("SELECT data_json FROM breakout_radar WHERE ticker = ? ORDER BY composite_score DESC LIMIT 1", (sym,))
        row = cur.fetchone()
        if row and row[0]:
            import json
            data = json.loads(row[0])
            data["ai_reasoning"] = output_dict
            new_json = json.dumps(data)
            conn.execute("UPDATE breakout_radar SET data_json = ? WHERE ticker = ?", (new_json, sym))
            conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("[BREAKOUT-AI] DB cache write failed for %s: %s", sym, e)
```

*Note: As above, this has already been placed into the file. Conduct standard review, verify it passes tests, and verify it uses `get_db_connection` without error.*

- [ ] **Step 3: Run comprehensive logic test**
Run: `pytest tests/test_breakout_strategies.py -v`

- [ ] **Step 4: Commit**
```bash
git add earnings_engine/data/breakout_scanner.py
git commit -m "feat(breakout): cache AI reasoning deterministically in SQLite to enforce zero-token rule"
```
