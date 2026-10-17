# Design Specification: Global CDMO, Peptide & Biosecure Cascade Radar

- **Date**: 2026-10-17
- **Status**: Draft for Builder Review & Architecture Verification
- **Target Subsystem**:
  - Database: `earnings_engine/data/transmission_schema.py`, `earnings_engine/data/turso_sync.py` (SYNC_TABLES)
  - Core Engine: `earnings_engine/data/transmission_radar.py`
  - REST API: `earnings_engine/api/routers/transmission.py`
  - Jinja2 Template: `earnings_engine/reports/templates/dashboard/_transmission.html`,
    `earnings_engine/reports/templates/hubs/dashboard/_transmission.html` (strictly mirrored)
  - Frontend UI: `earnings_engine/ui/js/modules/transmission_radar.js`
  - Tests: `tests/test_transmission_radar.py`, `tests/test_api_transmission.py`

---

## 1. Executive Summary & Intent (The "Why")

In the global pharmaceutical landscape, an unprecedented structural capital reallocation is underway driven by two massive secular megatrends:
1. **The GLP-1/GIP Peptide Supercycle**: Explosive demand for obesity and diabetes therapeutics (`LLY` - Tirzepatide, `NVO` - Semaglutide) has exhausted global peptide chemical synthesis, custom building blocks, and sterile fill-finish injectable capacity. Innovators are forced to outsource billions of dollars in commercial manufacturing.
2. **The US BIOSECURE Act & Western Geopolitical Decoupling**: US legislative initiatives targeting Chinese contract research and manufacturing organizations (CRDMOs such as WuXi AppTec and WuXi Biologics) are accelerating request-for-proposal (RFP) outflows toward accredited Western and Indian contract manufacturers.
3. **Recovery in Global Biotech R&D Funding**: Upstream bioprocessing bellwethers (`TMO`, `DHR`, `CRL`) dictate the liquidity cycle for early-stage discovery pipelines and commercial batch releases.

Indian CDMOs are the primary global liquidity and capacity sponge for these workflows. However, domestic market participants trade these stocks in naive isolation. Indian CDMOs operate across distinct tiers:
- **Tier 1 (Global Innovator Anchors & Tools Titans)**: Set pricing power, outsourcing budgets, and regulatory timelines.
- **Tier 2 (Frontline Indian CDMO Leaders)**: Directly receive large-scale commercial master service agreements (MSAs) and FDA-inspected capacity block reservations.
- **Tier 3 (Specialized Indian Satellite Proxies & High-Beta Followers)**: Experience extreme operational leverage to peptide building blocks, precision microbial fermentation, contrast media intermediates, and niche fluorination, but carry tight circuit limits (5% or 10%) and sharp multiple elasticity.

The **Global CDMO, Peptide & Biosecure Cascade Radar** formalizes this end-to-end physical and regulatory transmission graph into the existing Transmission Lead-Lag engine. It empowers institutional traders to anticipate downstream liquidity surges, avoid valuation traps, and capitalize on lead-lag dislocations.

---

## 2. Goals, Non-Goals & Anti-Goals

### 2.1 Goals
- Instantiate a second high-conviction thematic basket (`GLOBAL_CDMO_PEPTIDE_CASCADE`) within the Transmission Radar framework without altering underlying schema tables.
- Model 16 critical assets across 3 tiers (5 Global Anchors, 5 Indian Tier-2 Leaders, 6 Indian Tier-3 Proxies) connected via 16 directed physical and regulatory bottleneck edges.
- Hydrate live pricing, volume multiples, delivery percentages, and valuation multiples dynamically from existing market tables (`prices.py` / `prices.sqlite3`), strictly preserving Point-in-Time (PIT) integrity.
- Ingest real corporate filings from `news_catalysts` (US FDA Form 483 inspections, Establishment Inspection Reports [EIR], Reg 30 contract awards in ₹ Crores) and `earnings_history` (YoY revenue and PAT surprises).
- Provide automated microstructure trade recommendations (`STRONG_BUY_DIP`, `ACCUMULATE_BREAKOUT`, `HOLD_MOMENTUM`, `FADE_VALUATION_TRAP`, `TRIM_CIRCUIT_RISK`, `NEUTRAL_WATCH`) evaluating circuit freeze proximity, valuation elasticity vs global anchors, and institutional float backing.
- Implement UI basket selection: Enable single-click toggling between `AI_INFRA_HARDWARE` and `GLOBAL_CDMO_PEPTIDE_CASCADE` on the Transmission Radar dashboard with complete state persistence.

### 2.2 Non-Goals
- Domestic generic drug manufacturers (e.g. standard formulation generics without custom synthesis / CDMO business models like basic generic paracetamol or oral solid dosage manufacturers).
- Molecular chemical simulation or bioinformatics modeling; this is a quantitative equity lead-lag, liquidity flow, and valuation elasticity engine.

### 2.3 Anti-Goals
- **Zero Mock / Synthetic Seeding**: Under no circumstance should dummy prices, fabricated P/E multiples, or simulated news filings be written to SQLite. If data is absent, cleanly return `None`, `0.0`, or `[]`.
- **Zero Regression on Existing Radar**: Existing `AI_INFRA_HARDWARE` endpoints, tests, and UI renderings must remain 100% functional and pass all 33 existing tests.
- **Zero Inline JavaScript**: Strict frontend anti-bloat governance: all UI modifications must live within modular JavaScript files (`transmission_radar.js`) and pass `node -c` syntax validation.

---

## 3. Basket Topology Specification

### 3.1 Basket Metadata
- **Basket ID**: `GLOBAL_CDMO_PEPTIDE_CASCADE`
- **Name**: `Global CDMO, Peptide & Biosecure Cascade`
- **Description**: `US Innovators (GLP-1 / Biosecure) -> Indian Frontline CDMO Leaders -> High-Beta Peptide & Fermentation Proxies`
- **Macro Theme**: `GLP-1 Capacity Deficit & US BIOSECURE Act Decoupling`
- **Gate 3 Cash Conversion Status**: `PENDING`

### 3.2 Node Universe (16 Nodes)

| Node ID | Symbol | Market | Tier | Role | Product Lineage / Bottleneck Specialty | Circuit Band |
|---|---|:---:|:---:|---|---|:---:|
| `LLY` | `LLY` | US | 1 | `GLOBAL_ANCHOR` | Tirzepatide (Mounjaro/Zepbound) GLP-1/GIP Innovator Capex | None |
| `NVO` | `NVO` | US | 1 | `GLOBAL_ANCHOR` | Semaglutide (Ozempic/Wegovy) GLP-1 Innovator & Fill-Finish Outsourcing | None |
| `TMO` | `TMO` | US | 1 | `GLOBAL_ANCHOR` | Global Biopharma R&D Funding & Bioprocessing Services Bellwether | None |
| `DHR` | `DHR` | US | 1 | `GLOBAL_ANCHOR` | Upstream Bioprocess Filtration & Single-Use Chromatography Consumables | None |
| `CRL` | `CRL` | US | 1 | `GLOBAL_ANCHOR` | Early-Stage Drug Discovery & Pre-clinical CRO Pipeline Barometer | None |
| `DIVISLAB.NS` | `DIVISLAB.NS` | NSE | 2 | `PRIMARY_LEADER` | Custom Synthesis Titan & Complex Peptide Building Blocks | None (F&O) |
| `SYNGENE.NS` | `SYNGENE.NS` | NSE | 2 | `PRIMARY_LEADER` | Full-Lifecycle Biologics & Discovery CRDMO (WuXi Decoupling Target) | None (F&O) |
| `SUVENPHAR.NS` | `SUVENPHAR.NS` | NSE | 2 | `PRIMARY_LEADER` | High-Margin Innovator Commercial CDMO & Global PE Platform | 20.0% |
| `LAURUSLABS.NS` | `LAURUSLABS.NS` | NSE | 2 | `PRIMARY_LEADER` | Large-Scale Chemical CDMO & Precision Microbial Fermentation (Laurus Bio) | None (F&O) |
| `PIRAMALPHI.NS` | `PIRAMALPHI.NS` | NSE | 2 | `PRIMARY_LEADER` | Sterile Injectables, ADCs (Antibody-Drug Conjugates) & US/UK Facilities | None (F&O) |
| `NEULANDLAB.NS` | `NEULANDLAB.NS` | NSE | 3 | `HIGH_BETA_FOLLOWER` | Pure-Play Commercial Peptide Custom Manufacturing (CMS) | 5.0% |
| `CONCORDBIO.NS` | `CONCORDBIO.NS` | NSE | 3 | `HIGH_BETA_FOLLOWER` | Precision Microbial Fermentation APIs & Immunosuppressants | 20.0% |
| `BLUEJET.NS` | `BLUEJET.NS` | NSE | 3 | `HIGH_BETA_FOLLOWER` | Contrast Media Intermediates & High-Intensity Sweetener CDMO | 20.0% |
| `AMIORG.NS` | `AMIORG.NS` | NSE | 3 | `HIGH_BETA_FOLLOWER` | Advanced Regulatory Intermediates & Multi-Step Organic Synthesis | 10.0% |
| `JUBLPHARMA.NS` | `JUBLPHARMA.NS` | NSE | 3 | `HIGH_BETA_FOLLOWER` | Radiopharma, Sterile Injectables & Allergy Immunotherapy CDMO | 20.0% |
| `ANUPAM.NS` | `ANUPAM.NS` | NSE | 3 | `HIGH_BETA_FOLLOWER` | Custom Chemical Synthesis & High-Barrier Fluorination Chemistries | 20.0% |

### 3.3 Directed Transmission Bottleneck Edges (16 Edges)

| Edge ID | Source Node | Target Node | Catalyst Event | Physical Bottleneck / Transmission Mechanism | Elasticity | Lag Hours | Impact Level |
|---|---|---|---|---|:---:|:---:|:---:|
| `LLY_DIVIS` | `LLY` | `DIVISLAB.NS` | GLP-1 Commercial Ramp | Peptide Building Blocks & Protected Amino Acids Supply | 1.85 | 0h | `CRITICAL` |
| `NVO_NEULAND` | `NVO` | `NEULANDLAB.NS` | Peptide Outsourcing Surge | Commercial Peptide CMS Production Backlog & Capacity Reservation | 2.40 | 0h | `CRITICAL` |
| `LLY_NEULAND` | `LLY` | `NEULANDLAB.NS` | GLP-1 High-Beta Pass-Through | Innovator Custom Manufacturing Spillovers | 2.10 | 0h | `HIGH` |
| `TMO_SYNGENE` | `TMO` | `SYNGENE.NS` | BIOSECURE Act WuXi Displacement | Western Pharma RFP Rotation into Western-Compliant Discovery CRDMO | 1.75 | 24h | `CRITICAL` |
| `TMO_SUVEN` | `TMO` | `SUVENPHAR.NS` | Western Innovator Outsourcing | Innovator Phase II/III Molecule Synthesis & Dedicated Blocks | 1.65 | 24h | `HIGH` |
| `CRL_SYNGENE` | `CRL` | `SYNGENE.NS` | Early-Stage Biotech R&D Rebound | Pre-clinical Pipeline Expansion & Dedicated R&D Center Capex | 1.40 | 24h | `MODERATE` |
| `DHR_CONCORD` | `DHR` | `CONCORDBIO.NS` | Bioprocess & Fermentation Deficit | Large-Scale Microbial Fermentation & Downstream Purification | 1.55 | 24h | `HIGH` |
| `DHR_LAURUS` | `DHR` | `LAURUSLABS.NS` | Fermentation Capacity Reservation | Precision Microbial Fermentation (Laurus Bio) Scale-up | 1.60 | 24h | `HIGH` |
| `NVO_PIRAMAL` | `NVO` | `PIRAMALPHI.NS` | Sterile Fill-Finish & Injectable Deficit | Sterile Injectable Vials, Prefilled Syringes & ADC Manufacturing | 1.90 | 0h | `CRITICAL` |
| `DIVIS_AMIORG` | `DIVISLAB.NS` | `AMIORG.NS` | Commercial Block Intermediate Sourcing | Advanced Regulatory Intermediates & Multi-Step Chemistry Pass-Through | 1.45 | 24h | `HIGH` |
| `DIVIS_BLUEJET` | `DIVISLAB.NS` | `BLUEJET.NS` | Global Innovator Intermediates | High-Purity Contrast Media Intermediates & Niche Chemical Blocks | 1.35 | 24h | `MODERATE` |
| `SYNGENE_JUBL` | `SYNGENE.NS` | `JUBLPHARMA.NS` | Sterile Facility Spillover | US/EU Injectable & Radiopharma Contract Manufacturing | 1.30 | 24h | `MODERATE` |
| `LAURUS_ANUPAM` | `LAURUSLABS.NS` | `ANUPAM.NS` | Complex Fluorination Reagent Demands | High-Hazard Fluorination & Niche Agro/Pharma Synthesis | 1.40 | 24h | `MODERATE` |
| `SUVEN_AMIORG` | `SUVENPHAR.NS` | `AMIORG.NS` | NCE Intermediate Outsourcing | New Chemical Entity (NCE) Multi-Step Process Chemistry | 1.50 | 24h | `MODERATE` |
| `TMO_PIRAMAL` | `TMO` | `PIRAMALPHI.NS` | Western Biopharma Services Recovery | Sterile Fill-Finish & UK/US Clinical Trial Batch Logistics | 1.50 | 24h | `HIGH` |
| `DIVIS_SYNGENE` | `DIVISLAB.NS` | `SYNGENE.NS` | Indian CDMO Institutional Allocation | FII/DII Peer Flow Rebalancing across Frontline Pharma Leaders | 1.20 | 0h | `MODERATE` |

---

## 4. Algorithmic Formulations & Microstructure Trade Actions

The CDMO basket leverages the exact quantitative engine formalized in `transmission_radar.py`:

1. **Valuation Elasticity Formulation**:
   $$\text{Elasticity Ratio} = \frac{\text{Proxy P/E}}{\text{Anchor P/E}}$$
   - `EXTREME` ($\ge 3.0\times$): High-beta proxies (e.g. Neuland or Suven) expanding beyond justified anchor growth face severe compression if US innovators flag margin compression.
   - `ELEVATED` ($\ge 1.8\times$), `NORMAL` ($1.0 - 1.8\times$), `DISCOUNTED` ($< 1.0\times$).
   - Turnarounds or loss-making bases handled gracefully as `"N/A (Turnaround)"`.

2. **Circuit Proximity Buffer**:
   $$\text{Distance to LC} = \frac{\text{Current Price} - \text{Lower Circuit Limit}}{\text{Current Price}} \times 100\%$$
   - Indian CDMO small-caps (`NEULANDLAB.NS`, `AMIORG.NS`) trade under 5% or 10% daily price bands.
   - If distance $\le 2.0\%$, immediate `TRIM_CIRCUIT_RISK` warning fires.

3. **Corporate Catalysts Engine**:
   - Queries `news_catalysts` for ticker matches: Extracts US FDA inspection clearances (Zero 483 / EIR), patent litigation settlements, and Reg 30 contract disclosures with ₹ Crore values.
   - Queries `earnings_history`: Computes latest quarter EPS and revenue surprise %.

4. **Microstructure Trade Action Matrix**:
   - `TRIM_CIRCUIT_RISK` (`#ef4444`): Distance to lower band $\le 2.0\%$ or `HIGH_FREEZE_RISK`.
   - `FADE_VALUATION_TRAP` (`#f59e0b`): Valuation elasticity $\ge 3.0\times$ or institutional holding $< 10\%$ during an unconfirmed breakout.
   - `STRONG_BUY_DIP` (`#10b981`): 1D dip $\le -2.0\%$ into heavy institutional accumulation ($>20\%$ institutional float) with verified positive catalyst.
   - `ACCUMULATE_BREAKOUT` (`#059669`): 1D expansion $\ge 2.0\%$ with volume velocity $\ge 1.5\times$ or multi-crore supply agreement.
   - `HOLD_MOMENTUM` (`#3b82f6`): Stable positive momentum without circuit or valuation flags.
   - `NEUTRAL_WATCH` (`#6b7280`): Default balanced state.

5. **Re-Entry Gate 1 Dual-Level Anchor Architecture**:
   - **Basket-Level Macro Gate 1**: Parameterized in `transmission_radar.py` by inspecting the basket's primary anchor (`BE` for `AI_INFRA_HARDWARE`, `LLY` for `GLOBAL_CDMO_PEPTIDE_CASCADE`). In addition, a composite Tier-1 health rule requires that a majority ($\ge 3$ of the 5 Tier-1 anchors) have a 20-day return $\ge 0\%$ for Gate 1 to flip to `PASSED`.
   - **Node-Level Trade Matrix**: Evaluates the specific upstream anchor driving the node's directed edge:
     - `DIVISLAB.NS`, `NEULANDLAB.NS` $\rightarrow$ `LLY` / `NVO`
     - `SYNGENE.NS`, `SUVENPHAR.NS` $\rightarrow$ `TMO` / `CRL`
     - `PIRAMALPHI.NS` $\rightarrow$ `NVO`
     - `CONCORDBIO.NS`, `LAURUSLABS.NS` $\rightarrow$ `DHR` / `TMO`

6. **Market Data Hydration Contract**:
   - Automated pre-hydration migration script `sync_transmission_fundamentals` will pre-fetch authentic historical bars and live quotes for all 16 tickers (`LLY`, `NVO`, `TMO`, `DHR`, `CRL`, `DIVISLAB.NS`, etc.) into `prices.sqlite3` and `transmission_snapshots`.
   - Guarantees zero-latency initial load, no serverless timeouts, and zero fake/synthetic fallback data.

---

## 5. Frontend & UI Experience

1. **Dynamic Basket Switcher**:
   - Add a clean, responsive segmented basket toggle or dropdown at the top of the Transmission Lead-Lag tab:
     - `⚡ AI Infra & Power Deficit` (`AI_INFRA_HARDWARE`)
     - `🧬 CDMO, Peptides & Biosecure` (`GLOBAL_CDMO_PEPTIDE_CASCADE`)
   - Switching baskets fetches `/api/transmission/graph?basket_id={selected_id}` and re-renders the Canvas Web, Stats Ribbon, Trade Action Matrix, and Node Detail Drawer instantly.
2. **Multi-Tier Layout Geometry**:
   - 16 nodes arranged cleanly into 3 horizontal/curved columns:
     - Tier 1 (Left): 5 Global Anchors (`LLY`, `NVO`, `TMO`, `DHR`, `CRL`)
     - Tier 2 (Center): 5 Indian Frontline CDMO Leaders
     - Tier 3 (Right): 6 Indian Satellite Proxies & Specialized Pure-Plays
3. **Template Mirroring**:
   - Any markup modifications in `reports/templates/dashboard/_transmission.html` must be perfectly cloned into `reports/templates/hubs/dashboard/_transmission.html`.

---

## 6. What's Left to the Builder

1. **Seeding Script Implementation**:
   - Update `seed_default_transmission_baskets` in `earnings_engine/data/transmission_schema.py` to seed `GLOBAL_CDMO_PEPTIDE_CASCADE` alongside `AI_INFRA_HARDWARE`.
2. **Frontend UI Basket Switcher Integration**:
   - Add the basket switcher selector in `_transmission.html` and wire `onBasketChange` in `transmission_radar.js`.
3. **Unit & Integration Test Extensions**:
   - Expand `tests/test_transmission_radar.py` to assert correct node counts (16 nodes, 16 edges), DAG connectivity, and payload delivery for `GLOBAL_CDMO_PEPTIDE_CASCADE`.
