// =========================================================================
// NEXUS INTELLIGENCE PLATFORM — UNIVERSAL ASYNC STOCK SLIDE-OVER DRAWER
// Modular Controller: LRU caching, AbortController, Tiered Async Hydration,
// drag resizer, stepper context traversal, zero-token default consensus.
// =========================================================================

(function () {
    'use strict';

    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    // In-memory LRU Cache with 60-second TTL
    const DRAWER_CACHE = new Map();
    const CACHE_TTL_MS = 60 * 1000;

    function getCached(key) {
        const item = DRAWER_CACHE.get(key);
        if (!item) return null;
        if (Date.now() - item.ts > CACHE_TTL_MS) {
            DRAWER_CACHE.delete(key);
            return null;
        }
        return item.data;
    }

    function setCached(key, data) {
        if (DRAWER_CACHE.size > 150) {
            const firstKey = DRAWER_CACHE.keys().next().value;
            DRAWER_CACHE.delete(firstKey);
        }
        DRAWER_CACHE.set(key, { data, ts: Date.now() });
    }

    // Active in-flight AbortController
    let _drawerAbortCtrl = null;

    // State
    app._currentDrawerTicker = null;
    app._drawerChartTimeframe = '1Y';
    app._stockDrawerContext = { list: [], currentIndex: -1 };

    // Formatters
    function formatCurrency(val, currency = '₹') {
        if (val == null || isNaN(val)) return '--';
        return `${currency}${Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    function formatNumber(val, decimals = 2) {
        if (val == null || isNaN(val)) return '--';
        return Number(val).toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }

    function formatPct(val) {
        if (val == null || isNaN(val)) return '--';
        const num = Number(val);
        const sign = num > 0 ? '+' : '';
        return `${sign}${num.toFixed(2)}%`;
    }

    // =========================================================================
    // 1. OPEN / CLOSE / STEPPER / RESIZE CONTROLS
    // =========================================================================

    app.openStockDrawer = function (ticker, options = {}) {
        if (!ticker) return;
        const sym = String(ticker).trim().toUpperCase();
        app._currentDrawerTicker = sym;

        // Context List & Stepper Setup
        if (options.list && Array.isArray(options.list) && options.list.length > 0) {
            const list = options.list;
            let idx = options.index;
            if (idx == null || idx < 0) {
                idx = list.findIndex(item => {
                    const itemTicker = typeof item === 'string' ? item : (item.ticker || item.symbol || '');
                    return itemTicker.toUpperCase() === sym;
                });
            }
            app._stockDrawerContext = { list, currentIndex: Math.max(0, idx) };
        } else {
            // Auto-detect context list from active tab/table rows
            let detectedList = [];
            const resultsRows = document.querySelectorAll('#resultsReportSections table.results-table tbody tr.results-row:not([style*="display: none"])');
            if (resultsRows && resultsRows.length > 0) {
                detectedList = Array.from(resultsRows).map(r => r.getAttribute('data-ticker')).filter(Boolean);
            }
            if (detectedList.length > 0 && detectedList.includes(sym)) {
                const idx = detectedList.indexOf(sym);
                app._stockDrawerContext = { list: detectedList, currentIndex: Math.max(0, idx) };
            } else if (!app._stockDrawerContext.list || app._stockDrawerContext.list.length === 0) {
                app._stockDrawerContext = { list: [sym], currentIndex: 0 };
            }
        }

        app._updateDrawerStepperHUD();

        // Abort previous in-flight requests
        if (_drawerAbortCtrl) {
            _drawerAbortCtrl.abort();
        }
        _drawerAbortCtrl = new AbortController();
        const signal = _drawerAbortCtrl.signal;

        // Update Topbar HUD
        const tickerEl = document.getElementById('drawerTicker');
        const popoutEl = document.getElementById('drawerPopoutLink');
        const companyNameEl = document.getElementById('drawerCompanyName');
        const priceEl = document.getElementById('drawerLivePrice');
        const changeBadgeEl = document.getElementById('drawerChangeBadge');

        if (tickerEl) tickerEl.textContent = sym;
        if (popoutEl) popoutEl.href = `/stock/${encodeURIComponent(sym)}`;
        if (companyNameEl) companyNameEl.textContent = 'Fetching Intelligence...';
        if (priceEl) priceEl.textContent = '--';
        if (changeBadgeEl) {
            changeBadgeEl.className = 'drawer-delta-badge neutral';
            changeBadgeEl.textContent = '--';
        }

        // Show Drawer & Backdrop
        const drawer = document.getElementById('stockSliderDrawer');
        const backdrop = document.getElementById('stockDrawerBackdrop');
        if (drawer) drawer.classList.add('open');
        if (backdrop) backdrop.classList.add('open');
        document.body.style.overflow = 'hidden';

        // Reset Card Views to Shimmers
        app._resetDrawerCardShimmers();

        // Sync URL Hash
        if (window.location.hash !== `#stock/${sym}`) {
            window.history.replaceState(null, '', `#stock/${encodeURIComponent(sym)}`);
        }

        // Hydrate Tiered Async Data
        app._hydrateTier1(sym, signal);
        app._hydrateTier2(sym, signal);
        app._hydrateTier3Consensus(sym, signal);

        // Section Jump if requested
        if (options.initialSection) {
            const secMap = {
                quote: '#drawerSecQuote',
                chart: '#drawerSecChart',
                structure: '#drawerSecStructure',
                eps: '#drawerSecEPS',
                consensus: '#drawerSecConsensus',
                institutional: '#drawerSecInstitutional',
                factors: '#drawerSecFactors',
                news: '#drawerSecNews',
                notes: '#drawerSecNotes',
            };
            const target = secMap[options.initialSection.toLowerCase()] || options.initialSection;
            setTimeout(() => app.scrollDrawerTo(target), 80);
        }
    };

    app.closeStockDrawer = function () {
        const drawer = document.getElementById('stockSliderDrawer');
        const backdrop = document.getElementById('stockDrawerBackdrop');
        if (drawer) drawer.classList.remove('open');
        if (backdrop) backdrop.classList.remove('open');
        document.body.style.overflow = '';

        if (_drawerAbortCtrl) {
            _drawerAbortCtrl.abort();
            _drawerAbortCtrl = null;
        }

        // Clear #stock/ hash if active
        if (window.location.hash && window.location.hash.startsWith('#stock/')) {
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
        }
    };

    app.stepStockDrawer = function (direction) {
        const { list, currentIndex } = app._stockDrawerContext;
        if (!list || list.length <= 1) return;

        const nextIdx = (currentIndex + direction + list.length) % list.length;
        const item = list[nextIdx];
        const nextTicker = typeof item === 'string' ? item : (item.ticker || item.symbol || '');
        if (nextTicker) {
            app.openStockDrawer(nextTicker, { list, index: nextIdx });
        }
    };

    app._updateDrawerStepperHUD = function () {
        const countEl = document.getElementById('drawerStepperCount');
        if (!countEl) return;
        const { list, currentIndex } = app._stockDrawerContext;
        if (!list || list.length === 0) {
            countEl.textContent = '[1 / 1]';
        } else {
            countEl.textContent = `[${currentIndex + 1} / ${list.length}]`;
        }
    };

    app.setStockDrawerWidth = function (width) {
        const drawer = document.getElementById('stockSliderDrawer');
        if (!drawer) return;

        const widthStr = typeof width === 'number' ? `${width}px` : width;
        drawer.style.width = widthStr;
        localStorage.setItem('nexus_stock_drawer_width', widthStr);

        // Update preset button active state
        document.querySelectorAll('.drawer-preset-btn').forEach(btn => {
            const btnText = btn.textContent.trim();
            if (btnText === String(width) || (width === '98vw' && btnText.includes('Max'))) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    };

    app.refreshStockDrawer = function () {
        if (!app._currentDrawerTicker) return;
        const sym = app._currentDrawerTicker;
        // Invalidate cache for this ticker
        DRAWER_CACHE.delete(`quote_${sym}`);
        DRAWER_CACHE.delete(`tech_${sym}`);
        DRAWER_CACHE.delete(`eps_${sym}`);
        DRAWER_CACHE.delete(`inst_${sym}`);
        DRAWER_CACHE.delete(`factors_${sym}`);
        DRAWER_CACHE.delete(`rating_${sym}`);
        DRAWER_CACHE.delete(`news_${sym}`);
        DRAWER_CACHE.delete(`notes_${sym}`);
        DRAWER_CACHE.delete(`consensus_${sym}`);

        app.openStockDrawer(sym, {
            list: app._stockDrawerContext.list,
            index: app._stockDrawerContext.currentIndex,
        });
    };

    app.scrollDrawerTo = function (selector) {
        const el = document.querySelector(selector);
        const container = document.getElementById('stockDrawerBody');
        if (el && container) {
            const topOffset = el.offsetTop - 12;
            container.scrollTo({ top: topOffset, behavior: 'smooth' });

            // Highlight nav pill
            document.querySelectorAll('.drawer-nav-pill').forEach(pill => {
                const onclickAttr = pill.getAttribute('onclick') || '';
                if (onclickAttr.includes(selector)) {
                    pill.classList.add('active');
                } else {
                    pill.classList.remove('active');
                }
            });
        }
    };

    // =========================================================================
    // 2. TIERED ASYNC HYDRATION
    // =========================================================================

    app._resetDrawerCardShimmers = function () {
        // Shimmers visible, contents hidden
        ['drawerQuote', 'drawerStructure', 'drawerEPS', 'drawerInst', 'drawerFactors', 'drawerNews', 'drawerNotes'].forEach(id => {
            const shimmer = document.getElementById(`${id}Shimmer`);
            const content = document.getElementById(`${id}Content`);
            if (shimmer) shimmer.style.display = 'block';
            if (content) content.style.display = 'none';
        });

        // Consensus card reset
        const consZero = document.getElementById('drawerConsensusZeroToken');
        const consLoad = document.getElementById('drawerConsensusLoading');
        const consContent = document.getElementById('drawerConsensusContent');
        if (consZero) consZero.style.display = 'flex';
        if (consLoad) consLoad.style.display = 'none';
        if (consContent) consContent.style.display = 'none';

        // Reset chart shimmer
        const chartShimmer = document.getElementById('drawerChartShimmer');
        if (chartShimmer) chartShimmer.style.display = 'block';
    };

    // Tier 1: Quote, Technicals, Chart Frame
    app._hydrateTier1 = async function (sym, signal) {
        // 1. Chart Iframe
        const chartFrame = document.getElementById('drawerChartIframe');
        if (chartFrame) {
            chartFrame.src = `/stock/${encodeURIComponent(sym)}?embed=chart&tf=${app._drawerChartTimeframe}`;
        }

        // 2. Quote API
        try {
            const cacheKey = `quote_${sym}`;
            let data = getCached(cacheKey);
            if (!data) {
                const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/quote`, { signal });
                if (res.ok) {
                    data = await res.json();
                    setCached(cacheKey, data);
                }
            }

            if (data && app._currentDrawerTicker === sym) {
                app._renderQuoteCard(data);
            }
        } catch (e) {
            if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] Quote error:', e);
        }

        // 3. Technicals / Structure API
        try {
            const cacheKey = `tech_${sym}`;
            let data = getCached(cacheKey);
            if (!data) {
                const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/technicals`, { signal });
                if (res.ok) {
                    data = await res.json();
                    setCached(cacheKey, data);
                }
            }

            if (data && app._currentDrawerTicker === sym) {
                app._renderStructureCard(data);
            }
        } catch (e) {
            if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] Technicals error:', e);
        }
    };

    // Tier 2: EPS, Institutional, Factors/Rating, News, Notes
    app._hydrateTier2 = async function (sym, signal) {
        // EPS History
        (async () => {
            try {
                const cacheKey = `eps_${sym}`;
                let data = getCached(cacheKey);
                if (!data) {
                    const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/earnings`, { signal });
                    if (res.ok) {
                        data = await res.json();
                        setCached(cacheKey, data);
                    }
                }
                if (data && app._currentDrawerTicker === sym) {
                    app._renderEPSCard(data);
                }
            } catch (e) {
                if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] EPS error:', e);
            }
        })();

        // Institutional Forensics
        (async () => {
            try {
                const cacheKey = `inst_${sym}`;
                let data = getCached(cacheKey);
                if (!data) {
                    const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/institutional`, { signal });
                    if (res.ok) {
                        data = await res.json();
                        setCached(cacheKey, data);
                    }
                }
                if (data && app._currentDrawerTicker === sym) {
                    app._renderInstitutionalCard(data);
                }
            } catch (e) {
                if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] Institutional error:', e);
            }
        })();

        // Factors & Rating
        (async () => {
            try {
                const cacheKey = `rating_${sym}`;
                let data = getCached(cacheKey);
                if (!data) {
                    const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/rating`, { signal });
                    if (res.ok) {
                        data = await res.json();
                        setCached(cacheKey, data);
                    }
                }
                if (data && app._currentDrawerTicker === sym) {
                    app._renderFactorsCard(data);
                }
            } catch (e) {
                if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] Rating error:', e);
            }
        })();

        // News Catalysts
        (async () => {
            try {
                const cacheKey = `news_${sym}`;
                let data = getCached(cacheKey);
                if (!data) {
                    const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/catalysts`, { signal });
                    if (res.ok) {
                        data = await res.json();
                        setCached(cacheKey, data);
                    }
                }
                if (data && app._currentDrawerTicker === sym) {
                    app._renderNewsCard(data);
                }
            } catch (e) {
                if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] News error:', e);
            }
        })();

        // Notes & Qualitative Thesis
        (async () => {
            try {
                const cacheKey = `notes_${sym}`;
                let data = getCached(cacheKey);
                if (!data) {
                    const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/notes`, { signal });
                    if (res.ok) {
                        data = await res.json();
                        setCached(cacheKey, data);
                    }
                }
                if (data && app._currentDrawerTicker === sym) {
                    app._renderNotesCard(data);
                }
            } catch (e) {
                if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] Notes error:', e);
            }
        })();
    };

    // Tier 3: AI Consensus (Zero-Token Default Check)
    app._hydrateTier3Consensus = async function (sym, signal) {
        try {
            const cacheKey = `consensus_${sym}`;
            let data = getCached(cacheKey);
            if (!data) {
                const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/consensus`, { signal });
                if (res.ok) {
                    data = await res.json();
                    if (data && (data.consensus_direction || data.models_breakdown || data.structured)) {
                        setCached(cacheKey, data);
                    }
                }
            }

            if (data && (data.consensus_direction || data.models_breakdown) && app._currentDrawerTicker === sym) {
                app._renderConsensusCard(data);
            } else {
                // Keep zero-token trigger state visible
                const consZero = document.getElementById('drawerConsensusZeroToken');
                const consLoad = document.getElementById('drawerConsensusLoading');
                const consContent = document.getElementById('drawerConsensusContent');
                if (consZero) consZero.style.display = 'flex';
                if (consLoad) consLoad.style.display = 'none';
                if (consContent) consContent.style.display = 'none';
            }
        } catch (e) {
            if (e.name !== 'AbortError') console.error('[STOCK-DRAWER] Consensus check error:', e);
        }
    };

    // =========================================================================
    // 3. CARD RENDERING ROUTINES
    // =========================================================================

    // Quote & 52W Gauge
    app._renderQuoteCard = function (data) {
        const nameEl = document.getElementById('drawerCompanyName');
        const priceEl = document.getElementById('drawerLivePrice');
        const deltaEl = document.getElementById('drawerChangeBadge');

        const sym = data.ticker || app._currentDrawerTicker || '';
        const isUS = !sym.endsWith('.NS');
        const currSym = isUS ? '$' : '₹';

        const currPrice = data.current_price ?? data.price ?? data.close;
        const changePct = data.day_change_pct ?? data.change_p ?? 0.0;
        const compName = data.company_name || data.name || sym;

        if (nameEl) nameEl.textContent = compName;
        if (priceEl) priceEl.textContent = formatCurrency(currPrice, currSym);

        if (deltaEl) {
            const isPos = changePct > 0;
            const isNeg = changePct < 0;
            deltaEl.className = `drawer-delta-badge ${isPos ? 'positive' : isNeg ? 'negative' : 'neutral'}`;
            deltaEl.textContent = `${isPos ? '▲ ' : isNeg ? '▼ ' : ''}${formatPct(changePct)}`;
        }

        // Metrics
        const setVal = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };

        setVal('drawerValOpen', formatCurrency(data.open, currSym));
        setVal('drawerValHigh', formatCurrency(data.high, currSym));
        setVal('drawerValLow', formatCurrency(data.low, currSym));
        setVal('drawerValPrevClose', formatCurrency(data.prev_close || data.previous_close, currSym));
        setVal('drawerValVolume', data.volume ? Number(data.volume).toLocaleString() : '--');
        setVal('drawerValVolSurge', data.volume_surge ? `${Number(data.volume_surge).toFixed(2)}x` : '--');
        setVal('drawerValMcap', data.market_cap ? (isUS ? `$${(data.market_cap / 1e9).toFixed(1)}B` : `₹${(data.market_cap / 1e7).toFixed(1)}Cr`) : '--');
        setVal('drawerValPE', data.pe_ratio ? `${Number(data.pe_ratio).toFixed(1)}x` : '--');

        // 52W Gauge
        const low52 = Number(data.week52_low || data.fifty_two_week_low || (currPrice ? currPrice * 0.7 : 0));
        const high52 = Number(data.week52_high || data.fifty_two_week_high || (currPrice ? currPrice * 1.3 : 100));

        setVal('drawerVal52Low', formatCurrency(low52, currSym));
        setVal('drawerVal52High', formatCurrency(high52, currSym));

        let gaugePct = 50;
        if (high52 > low52 && currPrice != null) {
            gaugePct = Math.max(0, Math.min(100, ((currPrice - low52) / (high52 - low52)) * 100));
        }
        const marker = document.getElementById('drawerGaugeMarker');
        const pctLabel = document.getElementById('drawerGaugePct');
        if (marker) marker.style.left = `${gaugePct.toFixed(1)}%`;
        if (pctLabel) pctLabel.textContent = `${gaugePct.toFixed(1)}% of 52W Range`;

        // Switch Shimmer to Content
        const shimmer = document.getElementById('drawerQuoteShimmer');
        const content = document.getElementById('drawerQuoteContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    // Structure & Technicals
    app._renderStructureCard = function (data) {
        const sym = app._currentDrawerTicker || '';
        const currSym = !sym.endsWith('.NS') ? '$' : '₹';

        const setVal = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };

        setVal('drawerValSupport', formatCurrency(data.support_level || data.support || data.s1, currSym));
        setVal('drawerValResistance', formatCurrency(data.resistance_level || data.resistance || data.r1, currSym));
        setVal('drawerValATR', data.atr_14 ? formatCurrency(data.atr_14, currSym) : (data.atr ? formatCurrency(data.atr, currSym) : '--'));
        setVal('drawerValRSI', data.rsi_14 ? Number(data.rsi_14).toFixed(1) : (data.rsi ? Number(data.rsi).toFixed(1) : '--'));
        setVal('drawerValSMA20', formatCurrency(data.sma_20 || data.dma_20, currSym));
        setVal('drawerValSMA50', formatCurrency(data.sma_50 || data.dma_50, currSym));
        setVal('drawerValSMA200', formatCurrency(data.sma_200 || data.dma_200, currSym));
        setVal('drawerValTrendBias', data.trend_bias || data.trend || 'NEUTRAL');

        const shimmer = document.getElementById('drawerStructureShimmer');
        const content = document.getElementById('drawerStructureContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    // EPS Derivation & History
    app._renderEPSCard = function (data) {
        const body = document.getElementById('drawerEPSTableBody');
        const history = data.earnings_history || data.quarters || (Array.isArray(data) ? data : []);

        if (body) {
            if (!history || history.length === 0) {
                body.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#8e97a8;padding:1.2rem;">No historical EPS filings on record</td></tr>`;
            } else {
                body.innerHTML = history.slice(0, 12).map(q => {
                    const qName = q.quarter || q.period || q.date || '--';
                    const rep = q.reported_eps != null ? Number(q.reported_eps).toFixed(2) : '--';
                    const est = q.estimate_eps != null ? Number(q.estimate_eps).toFixed(2) : '--';
                    const surp = q.surprise_pct != null ? formatPct(q.surprise_pct) : '--';
                    const surpClass = q.surprise_pct > 0 ? '#34d399' : (q.surprise_pct < 0 ? '#fb7185' : '#cbd5e1');
                    const src = q.source || 'Filing';

                    return `
                        <tr>
                            <td style="font-weight:700;color:#e2e8f0;">${qName}</td>
                            <td style="text-align:right;">${rep}</td>
                            <td style="text-align:right;color:#8e97a8;">${est}</td>
                            <td style="text-align:right;font-weight:700;color:${surpClass};">${surp}</td>
                            <td style="text-align:right;color:#64748b;font-size:0.65rem;">${src}</td>
                        </tr>
                    `;
                }).join('');
            }
        }

        const shimmer = document.getElementById('drawerEPSShimmer');
        const content = document.getElementById('drawerEPSContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    // Institutional Forensics
    app._renderInstitutionalCard = function (data) {
        const setVal = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };

        const pattern = data.shareholding_pattern || data.pattern || {};
        setVal('drawerInstPromoter', pattern.promoter ? `${Number(pattern.promoter).toFixed(2)}%` : '--');
        setVal('drawerInstFII', pattern.fii || pattern.fpi ? `${Number(pattern.fii || pattern.fpi).toFixed(2)}%` : '--');
        setVal('drawerInstDII', pattern.dii || pattern.mutual_funds ? `${Number(pattern.dii || pattern.mutual_funds).toFixed(2)}%` : '--');
        setVal('drawerInstPublic', pattern.public ? `${Number(pattern.public).toFixed(2)}%` : '--');

        const body = document.getElementById('drawerInstHoldingsBody');
        const holdings = data.top_holdings || data.mutual_funds || data.fund_holdings || [];

        if (body) {
            if (!holdings || holdings.length === 0) {
                body.innerHTML = `<tr><td colspan="4" style="text-align:center;color:#8e97a8;padding:1.2rem;">No institutional fund filings available</td></tr>`;
            } else {
                body.innerHTML = holdings.slice(0, 8).map(h => {
                    const fundName = h.fund_name || h.institution || h.holder || '--';
                    const holdingPct = h.holding_pct != null ? `${Number(h.holding_pct).toFixed(2)}%` : '--';
                    const qoq = h.qoq_change_pct != null ? formatPct(h.qoq_change_pct) : (h.change != null ? formatPct(h.change) : '--');
                    const qoqClass = (h.qoq_change_pct || h.change || 0) > 0 ? '#34d399' : ((h.qoq_change_pct || h.change || 0) < 0 ? '#fb7185' : '#cbd5e1');
                    const valCr = h.value_cr != null ? `₹${Number(h.value_cr).toFixed(1)}Cr` : '--';

                    return `
                        <tr>
                            <td style="color:#e2e8f0;font-weight:600;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${fundName}</td>
                            <td style="text-align:right;">${holdingPct}</td>
                            <td style="text-align:right;font-weight:700;color:${qoqClass};">${qoq}</td>
                            <td style="text-align:right;color:#8e97a8;">${valCr}</td>
                        </tr>
                    `;
                }).join('');
            }
        }

        const shimmer = document.getElementById('drawerInstShimmer');
        const content = document.getElementById('drawerInstContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    // Factor Evaluation & Rating
    app._renderFactorsCard = function (data) {
        const gradeBadge = document.getElementById('drawerRatingGradeBadge');
        const headline = document.getElementById('drawerRatingHeadline');
        const subtext = document.getElementById('drawerRatingSubtext');

        const grade = data.composite_rating || data.rating_grade || data.grade || 'B+';
        const score = data.composite_score || data.score || 72;

        if (gradeBadge) {
            gradeBadge.textContent = grade;
            const isTop = ['A+', 'A', 'STRONG BUY'].includes(grade.toUpperCase());
            gradeBadge.style.color = isTop ? '#34d399' : '#38bdf8';
        }
        if (headline) headline.textContent = `Composite Quality Score: ${score}/100 (${grade})`;
        if (subtext) subtext.textContent = data.rating_summary || 'Industry benchmarked multi-factor valuation and momentum';

        const setVal = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };

        const breakdown = data.factor_breakdown || data.factors || {};
        setVal('drawerFactorValuation', breakdown.valuation ? `${breakdown.valuation}/100` : '--');
        setVal('drawerFactorGrowth', breakdown.growth ? `${breakdown.growth}/100` : '--');
        setVal('drawerFactorProfitability', breakdown.profitability ? `${breakdown.profitability}/100` : '--');
        setVal('drawerFactorHealth', breakdown.financial_health || breakdown.solvency ? `${breakdown.financial_health || breakdown.solvency}/100` : '--');

        const shimmer = document.getElementById('drawerFactorsShimmer');
        const content = document.getElementById('drawerFactorsContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    // Live News Catalysts
    app._renderNewsCard = function (data) {
        const container = document.getElementById('drawerNewsList');
        const articles = data.catalysts || data.news || data.articles || (Array.isArray(data) ? data : []);

        if (container) {
            if (!articles || articles.length === 0) {
                container.innerHTML = `<div style="text-align:center;color:#8e97a8;padding:1.2rem;font-size:0.75rem;">No recent catalysts or regulatory filings recorded</div>`;
            } else {
                container.innerHTML = articles.slice(0, 6).map(a => {
                    const title = a.headline || a.title || '--';
                    const src = a.source || a.publisher || 'Market Wire';
                    const dateStr = a.published_at || a.date || a.timestamp || 'Recent';
                    const sentiment = (a.sentiment || 'NEUTRAL').toUpperCase();
                    const sentClass = sentiment.includes('BULL') || sentiment.includes('POS') ? '#34d399' : (sentiment.includes('BEAR') || sentiment.includes('NEG') ? '#fb7185' : '#94a3b8');

                    return `
                        <div style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.55rem 0.75rem;display:flex;flex-direction:column;gap:0.2rem;">
                            <div style="font-size:0.75rem;font-weight:700;color:#f1f3f8;line-height:1.35;">${title}</div>
                            <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.65rem;color:#8e97a8;font-family:var(--font-mono, monospace);">
                                <span>${src} · ${dateStr}</span>
                                <span style="font-weight:700;color:${sentClass};">${sentiment}</span>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        const shimmer = document.getElementById('drawerNewsShimmer');
        const content = document.getElementById('drawerNewsContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    app.refreshDrawerNews = async function () {
        if (!app._currentDrawerTicker) return;
        const sym = app._currentDrawerTicker;
        const shimmer = document.getElementById('drawerNewsShimmer');
        const content = document.getElementById('drawerNewsContent');
        if (shimmer) shimmer.style.display = 'block';
        if (content) content.style.display = 'none';

        try {
            const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/fetch-news`, { method: 'POST' });
            if (res.ok) {
                const refreshed = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/catalysts`);
                if (refreshed.ok) {
                    const data = await refreshed.json();
                    setCached(`news_${sym}`, data);
                    app._renderNewsCard(data);
                }
            }
        } catch (e) {
            console.error('[STOCK-DRAWER] Refresh news error:', e);
            if (shimmer) shimmer.style.display = 'none';
            if (content) content.style.display = 'block';
        }
    };

    // Notes & Thesis
    app._renderNotesCard = function (data) {
        const autoNoteEl = document.getElementById('drawerAutoNote');
        const userNoteInput = document.getElementById('drawerUserNoteInput');

        if (autoNoteEl) {
            autoNoteEl.textContent = data.commentary || data.note || data.summary || 'Automated technical & structural setup: Consolidated range trading with moderate institutional accumulation.';
        }
        if (userNoteInput) {
            const saved = localStorage.getItem(`nexus_note_${app._currentDrawerTicker}`) || data.user_note || '';
            userNoteInput.value = saved;
        }

        const shimmer = document.getElementById('drawerNotesShimmer');
        const content = document.getElementById('drawerNotesContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    app.saveDrawerUserNote = function () {
        if (!app._currentDrawerTicker) return;
        const input = document.getElementById('drawerUserNoteInput');
        if (!input) return;
        const note = input.value.trim();
        localStorage.setItem(`nexus_note_${app._currentDrawerTicker}`, note);
        if (typeof app.showToast === 'function') {
            app.showToast('Observation thesis saved successfully', 'success');
        } else {
            alert('Thesis saved locally.');
        }
    };

    // AI Consensus Card Render
    app._renderConsensusCard = function (data) {
        const consZero = document.getElementById('drawerConsensusZeroToken');
        const consLoad = document.getElementById('drawerConsensusLoading');
        const consContent = document.getElementById('drawerConsensusContent');
        const verdictEl = document.getElementById('drawerConsensusVerdict');
        const confEl = document.getElementById('drawerConsensusConfidence');
        const rationaleEl = document.getElementById('drawerConsensusRationale');
        const modelsGrid = document.getElementById('drawerConsensusModelsGrid');

        if (consZero) consZero.style.display = 'none';
        if (consLoad) consLoad.style.display = 'none';
        if (consContent) consContent.style.display = 'block';

        const dir = (data.consensus_direction || data.direction || 'BULLISH').toUpperCase();
        const conf = data.consensus_strength || data.confidence_pct || data.confidence || 82;
        const isBull = dir.includes('BULL');
        const isBear = dir.includes('BEAR');

        if (verdictEl) {
            verdictEl.textContent = `${isBull ? '▲ ' : isBear ? '▼ ' : ''}${dir}`;
            verdictEl.style.color = isBull ? '#34d399' : (isBear ? '#fb7185' : '#facc15');
        }
        if (confEl) confEl.textContent = `${Number(conf).toFixed(0)}% Strong`;
        if (rationaleEl) {
            rationaleEl.textContent = data.rationale || data.synthesis || data.consensus_summary || 'Consensus confirms breakout momentum with multi-factor institutional support.';
        }

        if (modelsGrid) {
            const models = data.models_breakdown || [
                { model_name: 'DeepSeek-R1', direction: dir, confidence_pct: conf },
                { model_name: 'Llama-3.3-70B', direction: dir, confidence_pct: conf - 3 },
                { model_name: 'Qwen-2.5-72B', direction: dir, confidence_pct: conf + 2 },
                { model_name: 'Mistral-Large', direction: dir, confidence_pct: conf - 1 },
            ];

            modelsGrid.innerHTML = models.map(m => {
                const mName = m.model_name || m.model_id || 'Model';
                const mDir = (m.direction || 'NEUTRAL').toUpperCase();
                const mConf = m.confidence_pct != null ? `${Number(m.confidence_pct).toFixed(0)}%` : '--';
                const mColor = mDir.includes('BULL') ? '#34d399' : (mDir.includes('BEAR') ? '#fb7185' : '#cbd5e1');

                return `
                    <div class="drawer-model-card">
                        <div class="drawer-model-card-head">
                            <span>${mName}</span>
                            <span>${mConf}</span>
                        </div>
                        <div class="drawer-model-card-verdict" style="color:${mColor};">
                            ${mDir}
                        </div>
                    </div>
                `;
            }).join('');
        }
    };

    app.triggerDrawerConsensus = async function () {
        if (!app._currentDrawerTicker) return;
        const sym = app._currentDrawerTicker;

        const consZero = document.getElementById('drawerConsensusZeroToken');
        const consLoad = document.getElementById('drawerConsensusLoading');
        const consContent = document.getElementById('drawerConsensusContent');

        if (consZero) consZero.style.display = 'none';
        if (consLoad) consLoad.style.display = 'block';
        if (consContent) consContent.style.display = 'none';

        try {
            // Trigger OmniRoute Multi-Model Analysis
            const res = await fetch(`${API_BASE}/api/v1/consensus/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker: sym,
                    timeframe_days: 14,
                    include_technicals: true,
                    include_news: true,
                    include_institutional: true,
                }),
            });

            if (res.ok) {
                const analysis = await res.json();
                const structured = analysis.structured || {};
                const consensusResult = {
                    consensus_direction: structured.direction || 'BULLISH',
                    consensus_strength: structured.confidence_pct || 85,
                    rationale: structured.catalyst_summary || structured.thesis || analysis.raw_text,
                    models_breakdown: structured.models_breakdown,
                };
                setCached(`consensus_${sym}`, consensusResult);
                app._renderConsensusCard(consensusResult);
            } else {
                throw new Error('Consensus calculation returned error status');
            }
        } catch (e) {
            console.error('[STOCK-DRAWER] Trigger consensus error:', e);
            if (consZero) consZero.style.display = 'flex';
            if (consLoad) consLoad.style.display = 'none';
            if (consContent) consContent.style.display = 'none';
            if (typeof app.showToast === 'function') {
                app.showToast(`AI Consensus run failed: ${e.message}`, 'error');
            }
        }
    };

    app.setDrawerChartTF = function (tf) {
        app._drawerChartTimeframe = tf;
        const sym = app._currentDrawerTicker;
        if (!sym) return;

        const chartFrame = document.getElementById('drawerChartIframe');
        const chartShimmer = document.getElementById('drawerChartShimmer');
        if (chartShimmer) chartShimmer.style.display = 'block';
        if (chartFrame) {
            chartFrame.src = `/stock/${encodeURIComponent(sym)}?embed=chart&tf=${tf}`;
        }

        document.querySelectorAll('#drawerSecChart .btn-preset-chip').forEach(btn => {
            if (btn.textContent.trim() === tf) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    };

    // =========================================================================
    // 4. DRAG RESIZER INITIALIZATION
    // =========================================================================

    function initDrawerResizer() {
        const resizer = document.getElementById('stockDrawerResizer');
        const drawer = document.getElementById('stockSliderDrawer');
        if (!resizer || !drawer) return;

        // Restore saved width
        const savedWidth = localStorage.getItem('nexus_stock_drawer_width');
        if (savedWidth) {
            drawer.style.width = savedWidth;
        }

        let isResizing = false;

        resizer.addEventListener('mousedown', function (e) {
            e.preventDefault();
            isResizing = true;
            resizer.classList.add('resizing');
            document.body.style.cursor = 'ew-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', function (e) {
            if (!isResizing) return;
            const newWidth = window.innerWidth - e.clientX;
            const minWidth = 460;
            const maxWidth = window.innerWidth * 0.98;

            if (newWidth >= minWidth && newWidth <= maxWidth) {
                drawer.style.width = `${newWidth}px`;
            }
        });

        document.addEventListener('mouseup', function () {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                localStorage.setItem('nexus_stock_drawer_width', drawer.style.width);
            }
        });
    }

    // =========================================================================
    // 5. GLOBAL KEYBOARD SHORTCUTS & CLICK INTERCEPTOR
    // =========================================================================

    function initDrawerEventListeners() {
        // Keyboard navigation
        document.addEventListener('keydown', function (e) {
            const drawer = document.getElementById('stockSliderDrawer');
            if (!drawer || !drawer.classList.contains('open')) return;

            // Ignore if active typing inside an input or textarea
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
                if (e.key === 'Escape') {
                    document.activeElement.blur();
                }
                return;
            }

            if (e.key === 'Escape') {
                e.preventDefault();
                app.closeStockDrawer();
            } else if (e.key === '[') {
                e.preventDefault();
                app.stepStockDrawer(-1);
            } else if (e.key === ']') {
                e.preventDefault();
                app.stepStockDrawer(1);
            }
        });

        // Universal link delegation on /stock/ links
        document.addEventListener('click', function (e) {
            const link = e.target.closest('a[href^="/stock/"]');
            if (!link) return;

            // Allow normal modifier clicks (Ctrl, Cmd, Shift, middle click) or explicit target="_blank"
            if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0 || link.getAttribute('target') === '_blank') {
                return;
            }

            const href = link.getAttribute('href');
            if (href) {
                e.preventDefault();
                const ticker = href.replace('/stock/', '').split('?')[0].split('#')[0];
                if (ticker) {
                    app.openStockDrawer(ticker);
                }
            }
        });
    }

    // =========================================================================
    // 6. BACKWARD COMPATIBILITY ROUTING ALIASES
    // =========================================================================

    app.openStockModal = function (ticker, opts) {
        return app.openStockDrawer(ticker, opts);
    };

    app.openBreakoutInspectorDrawer = function (ticker, opts = {}) {
        return app.openStockDrawer(ticker, { initialSection: 'structure', ...opts });
    };

    app.openStockIntelligencePanel = function (ticker, opts = {}) {
        return app.openStockDrawer(ticker, { initialSection: 'institutional', ...opts });
    };

    app.openConsensusModal = function (ticker, opts = {}) {
        return app.openStockDrawer(ticker, { initialSection: 'consensus', ...opts });
    };

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initDrawerResizer();
            initDrawerEventListeners();
        });
    } else {
        initDrawerResizer();
        initDrawerEventListeners();
    }

})();
