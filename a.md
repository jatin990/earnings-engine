# Complete Screen-by-Screen Price & Metric Audit, Global Live Tick Sync, and Bug Resolution Plan

## 1. Context & Objectives
1. **Screen-by-Screen Verification**: Complete catalog across every platform screen defining each price, momentum metric, technical indicator, and financial calculation, their exact mathematical formula, expected behavior, and edge cases.
2. **Unified Global Live Ticks Refresh**: Ensure all real-time pricing and screen views synchronize dynamically with the central global live refresh interval configuration (`LIVE_REFRESH_INTERVAL_SEC` / `window.APP_CONFIG`).
3. **M&M Results Bug Resolution**: Fix why M&M (`M&M.NS`) appeared in the Results section when its actual quarterly results were not yet declared (distinguishing scheduled board meetings from actual declared financial filings).
4. **Mindspace 0% Returns Bug Resolution**: Fix why Mindspace REIT (`MINDSPACE.NS`) and other special instruments displayed `0%` returns in the Institutional Top Stake Additions table.

---

## 2. Screen-by-Screen Price & Metric Catalog

### A. Dashboard (`/dashboard`)
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **LTP (Last Traded Price)** | Most recent traded market price | $\text{LTP} = P_{\text{last}}$ (NSE real-time / SQLite close) | If market closed, show last official closing price. No synthetic data. |
| **Day Change & %** | Price change from previous trading day's close | $\Delta P = \text{LTP} - P_{\text{prev\_close}}$, $\%\Delta = \frac{\Delta P}{P_{\text{prev\_close}}} \times 100$ | If $P_{\text{prev\_close}} \le 0$ or missing, return `None` (UI: `—`), not `0%`. |
| **52-Week High / Low & Distance** | 1-year rolling price extremes and proximity | $\text{Dist}_{\text{52WH}} = \frac{\text{LTP} - \text{52WH}}{\text{52WH}} \times 100$, $\text{Dist}_{\text{52WL}} = \frac{\text{LTP} - \text{52WL}}{\text{52WL}} \times 100$ | Calculated strictly over 252 trading days. If history < 50 days (IPOs), use available window and badge as `N/A (<1Y)`. |
| **7D / 30D Price Drift** | Short-to-medium term momentum | $\text{Return}_{N\text{D}} = \frac{P_{T} - P_{T-N}}{P_{T-N}} \times 100$ ($N \in \{7, 30\}$ calendar/trading adjusted) | Point-in-Time clean: matches closest trading date on/before $T-N$. |
| **Volume Surge Ratio** | Relative volume spike vs baseline | $\text{Surge} = \frac{V_{\text{today}}}{\text{SMA}_{20}(V)}$ or $\frac{\text{SMA}_5(V)}{\text{SMA}_{63}(V)}$ | If volume is 0 (pre-market), display `0.0x` or `Market Closed`. |
| **Expected Reaction Confidence (GBM)** | Calibrated probability of positive post-earnings move | $P(\text{Up}) = \text{PlattScale}(\text{GBM}(X))$ ($X \in \text{PIT Features}$) | Probabilities strictly bounded in $[0.0, 1.0]$. |

### B. Stock Detail Page & Intelligence Modal (`/stock/{ticker}`)
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **SMA / EMA (20, 50, 200)** | Simple & Exponential Moving Averages | $\text{SMA}_k = \frac{1}{k}\sum_{i=0}^{k-1} P_{t-i}$, $\text{EMA}_k = \alpha P_t + (1-\alpha)\text{EMA}_{t-1}, \alpha = \frac{2}{k+1}$ | Requires at least $k$ price points. If history < 200, return `null` for EMA-200. |
| **RSI (14)** | Relative Strength Index | $\text{RSI} = 100 - \frac{100}{1 + RS}$, $RS = \frac{\text{EMA}_{14}(\text{Gain})}{\text{EMA}_{14}(\text{Loss})}$ | Values bounded $[0, 100]$. Neutral = 50. |
| **MACD & Signal** | Moving Average Convergence Divergence | $\text{MACD} = \text{EMA}_{12}(P) - \text{EMA}_{26}(P)$, $\text{Signal} = \text{EMA}_9(\text{MACD})$ | Displays histogram $\text{MACD} - \text{Signal}$. |
| **Historical Reaction Return (PIT)** | 1-day reaction to past earnings announcements | $\text{Reaction} = \frac{P_{\text{ann}+1} - P_{\text{ann}-1}}{P_{\text{ann}-1}} \times 100$ | Strict PIT: never uses same-day intraday or leaks future post-announcement data. |
| **Kronos 14-Day Neural Trajectory** | Deep sequence price forecast | $\hat{P}_{t+1\dots t+14} = \text{Kronos}(\mathbf{X}_{t-60:t})$ | Only runs on user demand or background pre-cache; zero automatic LLM cost. |
| **Support & Resistance (Pivot Points)** | Swing reaction levels | $PP = \frac{H+L+C}{3}, R_1 = 2PP - L, S_1 = 2PP - H$ | Computed on rolling 20-day swing channel or daily pivots. |

### C. Institutional Intelligence Hub (`/institutional`)
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **Institutional Stakeholder Delta (QoQ)** | Net change in FII / DII / MF percentage stake | $\Delta \text{Stake} = \text{Stake}_{Q_t} - \text{Stake}_{Q_{t-1}}$ (% points) | Must indicate quarter horizon (e.g. `Q3 FY25 vs Q2 FY25`). |
| **Top Stake Additions (7D/30D/1Y Return)** | Equity returns over short/long windows for stocks with $>+3\%$ stake additions | $\text{Return}_{K} = \frac{P_{\text{current}} - P_{\text{current}-K}}{P_{\text{current}-K}} \times 100$ | If price history is missing or symbol is a REIT/InvIT, must fetch fallback quote or show `N/A`, **never** false `0%`. |
| **Accumulation Score (0-100)** | Multi-factor institutional pressure metric | Weighted composite: FII $\Delta$ (35%) + DII $\Delta$ (35%) + Delivery Vol Surge (20%) + Block Deals (10%) | Bounded $[0, 100]$. $\ge 70$ Heavy Accumulation, $\le 30$ Heavy Distribution. |
| **Fund Holding Value (Cr)** | Aggregate value of shares held by specific fund | $\text{Value (Cr)} = \frac{\text{Shares Held} \times \text{LTP}}{10^7}$ | Uses latest LTP synced from `price_history`. |

### D. Breakout Radar & Real-Time Scanner
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **52W High Breakout Condition** | Stock trading within $\le 2\%$ of 52WH or hitting fresh high | $\text{Dist}_{\text{52WH}} \ge -2.0\%$ and $\text{Volume} > 1.5 \times \text{SMA}_{20}(V)$ | Flags breakout stage: `Imminent`, `Fresh Breakout`, `Extended`. |
| **Consolidation Range Compression** | Tight trading band prior to volatility expansion | $\text{Band Width} = \frac{\text{Max}(P_{20}) - \text{Min}(P_{20})}{\text{SMA}_{20}(P)} \times 100 \le 6.0\%$ | Quantifies volatility squeeze (Bollinger / Keltner channel pinch). |
| **200 EMA Golden Cross** | 50 EMA crossing above 200 EMA | $\text{EMA}_{50}(t-1) \le \text{EMA}_{200}(t-1)$ and $\text{EMA}_{50}(t) > \text{EMA}_{200}(t)$ | Point-in-time cross detection over daily bars. |

### E. Swing Range Detector & S/R Engine
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **Swing Channel High/Low** | Local extremum over rolling $N=20$ bars | $\text{SwingHigh} = \max(H_{t-20:t}), \text{SwingLow} = \min(L_{t-20:t})$ | Identifies swing boundaries for risk/reward. |
| **Distance to Support / Resistance** | Proximity to key bounce or rejection level | $\text{Dist}_R = \frac{R_1 - \text{LTP}}{\text{LTP}} \times 100$, $\text{Dist}_S = \frac{\text{LTP} - S_1}{\text{LTP}} \times 100$ | Visualized as risk-reward ratio $\text{RR} = \frac{\text{Dist}_R}{\text{Dist}_S}$. |

### F. Point-in-Time Tri-Factor Confluence Hub
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **Tri-Factor Synergy Score (0-100)** | Unified confluence of Technical + Institutional + Earnings Momentum | $S = 0.40 \cdot S_{\text{Technical}} + 0.35 \cdot S_{\text{Institutional}} + 0.25 \cdot S_{\text{Earnings}}$ | Strictly point-in-time; highlights 3-way aligned equities. |
| **Synergy Classification** | High conviction breakout / swing setup | $\text{Score} \ge 75 \implies \text{High Confluence Bullish}$; $\le 30 \implies \text{Bearish/Distribution}$ | Rendered in UI badge with breakdown tooltip. |

### G. Results & Earnings Calendar / Month Filter
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **Declared vs Scheduled Result Status** | Distinguishes announced financials from tentative board meetings | $\text{Status} \in \{\text{"Declared"}, \text{"Scheduled"}\}$ based on presence of audited/unaudited filings & reported EPS/Net Profit | Prevents unconfirmed calendar events from polluting the Results report. |
| **Reported EPS Surprise %** | Outperformance relative to consensus estimate | $\text{Surprise} = \frac{\text{EPS}_{\text{reported}} - \text{EPS}_{\text{estimate}}}{|\text{EPS}_{\text{estimate}}|} \times 100$ | If estimate missing, display reported EPS and YoY growth instead. |
| **Post-Earnings Reaction (PIT)** | Day +1 close vs Day -1 close | $\frac{P_{T+1} - P_{T-1}}{P_{T-1}} \times 100$ | If $T+1$ has not traded yet, display `Pending Session`. |

### H. Buy The Dip Radar
| Metric / Component | Meaning & Purpose | Exact Mathematical Formula | Expected Behavior & Edge-Cases |
| :--- | :--- | :--- | :--- |
| **Dip from 52W High** | Correction depth from peak | $\text{Dip} = \frac{\text{LTP} - \text{52WH}}{\text{52WH}} \times 100$ (typically $-10\%$ to $-30\%$) | Filters quality stocks (Market Cap > ₹5,000 Cr, Inst > 15%). |
| **Oversold Bounce Signal** | Daily RSI $\le 40$ + reversal candle or support touch | $\text{RSI}_{14} \le 40$ and $\text{LTP} \ge S_1 \cdot 0.98$ and $\Delta P > 0$ | Combines technical oversold state with institutional backing. |

---

## 3. Global Live Ticks Refresh Sync Architecture

1. **Centralized Configuration**:
   - Backend exposes `LIVE_REFRESH_INTERVAL_SEC` via `/api/v1/config` (default: 30s).
   - Frontend stores this in `window.APP_CONFIG.live_refresh_interval_sec`.
2. **Master Polling Dispatcher (`LiveTickDispatcher`)**:
   - Create a single global dispatcher in `earnings_engine/ui/js/dashboard.js`.
   - Replaces fragmented per-component `setInterval` timers across all modules.
   - Respects document visibility (`document.visibilityState === 'visible'`) and market hours.
   - Dynamic rebind without full page reload.

---

## 4. Root Cause Analysis & Concrete Fixes for Specific Bugs

### Bug 1: M&M (`M&M.NS`) in Results Section Without Declared Results
- **Root Cause**:
  In `earnings_engine/data/earnings.py` (`ingest_nse_result_calendar`), NSE corporate announcements were ingested with keyword checks for board meetings (e.g. "to consider financial results"). These were saved directly into `earnings_history` with `earnings_date = meeting_date`.
  When `/api/v1/dashboard/results/report` was called, it queried all records in `earnings_history` for the selected date window without checking whether financial results were actually declared (`eps_reported is not NULL` or `financials_reported == 1`) or if it was merely an upcoming/tentative board meeting.
- **Fix**:
  1. Add an `is_declared` boolean column / computed property in `earnings_history` and `recent_results.py`.
  2. In `earnings.py` / `recent_results.py`, mark events as `declared` only when filing data, EPS, or revenue statements are present.
  3. In `dashboard_api.py` (`/api/v1/dashboard/results/report`), filter strictly to `is_declared == True` for the "Declared Results" section, and route tentative future dates to "Upcoming Earnings Calendar" with explicit badge `Scheduled (Board Meeting: DD Mon)`.

### Bug 2: Mindspace (`MINDSPACE.NS`) Showing 0% Returns in Top Stake Additions
- **Root Cause**:
  In `earnings_engine/data/institutional_accumulation.py`:
  1. `_get_ticker_returns(ticker)` queried SQLite `price_history` for `MINDSPACE.NS`. Because REITs / InvITs were not part of the standard equity universe daily price scraper, `price_history` had 0 or 1 row.
  2. `_get_ticker_returns()` returned `(None, None, None)`.
  3. In `earnings_engine/ui/js/modules/institutional.js` (`renderTopAdditionsTable`), the return formatting was written as:
     `const ret7d = it.return_7d_pct != null ? it.return_7d_pct : 0;`
     This coerced `null` / `None` into `0%`, misleadingly showing `+0%` returns.
- **Fix**:
  1. **Backend**: Update `_get_ticker_returns()` to trigger on-demand price fallback via `fetch_prices(ticker, force=False)` when SQLite cache is empty.
  2. **Universe Ingestion**: Ensure REITs/InvITs (`MINDSPACE.NS`, `EMBASSY.NS`, `BIRET.NS`, `PGINVIT.NS`) are ingested in price sync pipelines.
  3. **Frontend**: In `institutional.js`, format `null` returns as `<span class="text-muted">N/A</span>` instead of `0%`.

---

## 5. Implementation Roadmap & Critical Files to Modify

1. **`earnings_engine/data/earnings.py` & `earnings_engine/data/recent_results.py`**:
   - Implement `is_declared` / `result_status` differentiation.
   - Refine NSE corporate announcement scraper so scheduled meetings do not masquerade as declared results.
2. **`earnings_engine/data/institutional_accumulation.py` & `earnings_engine/data/prices.py`**:
   - Fix `_get_ticker_returns()` with live fallback quote lookup for missing tickers/REITs.
   - Add safe error/missing-data return signatures.
3. **`earnings_engine/ui/js/modules/institutional.js`**:
   - Fix `renderTopAdditionsTable` and related renderers to output `N/A` for missing return series.
4. **`earnings_engine/ui/js/dashboard.js`**:
   - Implement centralized `LiveTickDispatcher` linked to `window.APP_CONFIG.live_refresh_interval_sec`.
   - Wire all view listeners to use the central dispatcher.
5. **`tests/test_institutional.py` & `tests/test_recent_results.py`**:
   - Add unit tests for REIT returns calculation, N/A handling, and declared vs scheduled results separation.

---

## 6. Verification & Validation Plan

1. **Bug 1 Verification (M&M Results)**:
   - Query `/api/v1/dashboard/results/report` and verify `M&M.NS` only appears in "Upcoming / Scheduled" until official results are declared.
2. **Bug 2 Verification (Mindspace 0% Returns)**:
   - Query `/api/v1/institutional/top-additions` and verify `MINDSPACE.NS` displays actual calculated returns or `N/A`, never false `0%`.
3. **Global Live Ticks Sync Verification**:
   - Change `LIVE_REFRESH_INTERVAL_SEC` in configuration, load the UI, and verify in DevTools Network tab that all tabs poll at the configured cadence.
4. **Automated Test Suite**:
   - Run `pytest tests/test_institutional_accumulation.py tests/test_recent_results.py -v`.
