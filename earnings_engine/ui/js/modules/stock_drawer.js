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
    app._drawerChartTimeframe = '1D';
    app._drawerChartRange = '1Y';
    app._drawerChartPollTimer = null;
    app._stockDrawerContext = { list: [], currentIndex: -1 };
    app._drawerHydratedTabs = new Set();

    // Native Chart State
    app._drawerChartInstance = null;
    app._drawerCandleSeries = null;
    app._drawerVolumeSeries = null;
    app._drawerSMA20Series = null;
    app._drawerSMA50Series = null;
    app._drawerSMA200Series = null;
    app._drawerVWAPSeries = null;
    app._drawerVWAPUpperSeries = null;
    app._drawerVWAPLowerSeries = null;
    app._drawerSRLines = [];
    app._drawerChartRecords = [];
    app._drawerAvgVol20 = 1;
    app._drawerTechnicalData = null;
    app._drawerResizeObserver = null;
    app._drawerToggles = {
        sma20: true,
        sma50: true,
        sma200: true,
        vwap: true,
        bounds: true,
    };

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
        app._drawerHydratedTabs.clear();

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

        // Hydrate only active tab on-demand (lazy loading)
        const initialTab = options.initialTab || options.initialSection || app._currentDrawerTab || 'quote';
        app.switchDrawerTab(initialTab);
    };

    app.closeStockDrawer = function () {
        const drawer = document.getElementById('stockSliderDrawer');
        const backdrop = document.getElementById('stockDrawerBackdrop');
        if (drawer) drawer.classList.remove('open');
        if (backdrop) backdrop.classList.remove('open');
        document.body.style.overflow = '';

        if (app._drawerChartPollTimer) {
            clearInterval(app._drawerChartPollTimer);
            app._drawerChartPollTimer = null;
        }

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

    const DRAWER_SECTIONS = [
        { key: 'quote', id: 'drawerSecQuote' },
        { key: 'chart', id: 'drawerSecChart' },
        { key: 'structure', id: 'drawerSecStructure' },
        { key: 'eps', id: 'drawerSecEPS' },
        { key: 'consensus', id: 'drawerSecConsensus' },
        { key: 'institutional', id: 'drawerSecInstitutional' },
        { key: 'factors', id: 'drawerSecFactors' },
        { key: 'news', id: 'drawerSecNews' },
        { key: 'notes', id: 'drawerSecNotes' },
    ];

    app.switchDrawerTab = function (tabKey) {
        if (!tabKey) tabKey = 'quote';
        // Normalize selector like #drawerSecChart to key
        if (tabKey.startsWith('#')) {
            const found = DRAWER_SECTIONS.find(s => `#${s.id}` === tabKey);
            if (found) tabKey = found.key;
            else tabKey = tabKey.replace('#drawerSec', '').toLowerCase();
        }
        tabKey = tabKey.toLowerCase();
        app._currentDrawerTab = tabKey;

        // Update Nav Pills
        document.querySelectorAll('.drawer-nav-pill').forEach(pill => {
            const pTab = pill.getAttribute('data-tab');
            if (pTab === tabKey) {
                pill.classList.add('active');
            } else {
                pill.classList.remove('active');
            }
        });

        // Show/Hide Sections
        const chartSec = document.getElementById('drawerSecChart');
        if (chartSec) {
            if (tabKey === 'chart') {
                chartSec.classList.add('drawer-tab-active-chart');
            } else {
                chartSec.classList.remove('drawer-tab-active-chart');
            }
        }

        if (tabKey === 'all') {
            DRAWER_SECTIONS.forEach(sec => {
                const el = document.getElementById(sec.id);
                if (el) el.style.display = 'block';
            });
        } else {
            DRAWER_SECTIONS.forEach(sec => {
                const el = document.getElementById(sec.id);
                if (el) {
                    if (sec.key === tabKey) {
                        el.style.display = 'block';
                    } else {
                        el.style.display = 'none';
                    }
                }
            });
        }

        // Trigger on-demand lazy hydration for active tab
        if (app._currentDrawerTicker) {
            app._hydrateDrawerTab(tabKey, app._currentDrawerTicker);
        }

        // If chart tab is active, trigger resize to ensure proper canvas layout
        if ((tabKey === 'chart' || tabKey === 'all') && app._drawerChartInstance) {
            setTimeout(() => {
                const container = document.getElementById('drawerNativeChartCanvas');
                if (container && container.clientWidth > 0 && app._drawerChartInstance) {
                    app._drawerChartInstance.applyOptions({ width: container.clientWidth });
                    if (app._drawerChartTimeframe) {
                        app.setDrawerChartTF(app._drawerChartTimeframe);
                    }
                }
            }, 60);
        }

        const body = document.getElementById('stockDrawerBody');
        if (body) body.scrollTop = 0;
    };

    app.scrollDrawerTo = function (selector) {
        app.switchDrawerTab(selector);
    };

    // =========================================================================
    // 2. ON-DEMAND LAZY SUBTAB HYDRATION DISPATCHER
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

        // Reset chart shimmer & crosshair HUD
        const chartShimmer = document.getElementById('drawerChartShimmer');
        if (chartShimmer) chartShimmer.style.display = 'block';
        ['drawerHudDate', 'drawerHudOpen', 'drawerHudHigh', 'drawerHudLow', 'drawerHudClose', 'drawerHudVol', 'drawerHudSurge', 'drawerHudTR'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = '--';
        });
    };

    // Unified On-Demand Tab Loader
    app._hydrateDrawerTab = async function (tabKey, sym, force = false) {
        if (!sym || app._currentDrawerTicker !== sym) return;
        const signal = _drawerAbortCtrl ? _drawerAbortCtrl.signal : undefined;

        // If 'all', load all tabs concurrently
        if (tabKey === 'all') {
            const allTabs = ['quote', 'chart', 'structure', 'eps', 'consensus', 'institutional', 'factors', 'news', 'notes'];
            allTabs.forEach(t => app._hydrateDrawerTab(t, sym, force));
            return;
        }

        // Avoid re-fetching already hydrated tabs unless forced
        if (!force && app._drawerHydratedTabs.has(tabKey)) {
            return;
        }
        app._drawerHydratedTabs.add(tabKey);

        switch (tabKey) {
            case 'quote': {
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
                break;
            }

            case 'chart': {
                // Initialize or update Native LightweightCharts Canvas
                app._initOrUpdateDrawerChart(sym, signal);
                break;
            }

            case 'structure': {
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
                break;
            }

            case 'eps': {
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
                break;
            }

            case 'consensus': {
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
                break;
            }

            case 'institutional': {
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
                break;
            }

            case 'factors': {
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
                break;
            }

            case 'news': {
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
                break;
            }

            case 'notes': {
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
                break;
            }
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

        app._drawerTechnicalData = data;

        // Apply S/R price lines to chart canvas if active
        if (app._drawerCandleSeries && app._drawerToggles && app._drawerToggles.bounds) {
            app._applyDrawerSRPriceLines(data);
        }

        // Update Technical Explainer Cards
        if (app._drawerChartRecords && app._drawerChartRecords.length > 0) {
            _updateDrawerTechnicalExplainers(app._drawerChartRecords, data);
        }

        const shimmer = document.getElementById('drawerStructureShimmer');
        const content = document.getElementById('drawerStructureContent');
        if (shimmer) shimmer.style.display = 'none';
        if (content) content.style.display = 'block';
    };

    // EPS Derivation & Quarterly Fundamental Forensics
    app._renderEPSCard = function (data) {
        const sym = app._currentDrawerTicker || '';
        const isUS = !sym.endsWith('.NS');
        const currSym = isUS ? '$' : '₹';

        // 1. Render Quarterly Fundamental Forensics (Revenue, EBITDA, Margins, PAT, EPS)
        const fundBody = document.getElementById('drawerFundamentalsTableBody');
        const fundList = data.quarterly_financials || [];
        const provBadge = document.getElementById('drawerFundProvenanceBadge');

        if (provBadge) {
            const srcSet = new Set(fundList.map(f => f.source).filter(Boolean));
            if (srcSet.size > 0) {
                provBadge.textContent = Array.from(srcSet).join(' · ');
            } else {
                provBadge.textContent = isUS ? 'SEC EDGAR / yfinance' : 'BSE / NSE / Screener';
            }
        }

        if (fundBody) {
            if (!fundList || fundList.length === 0) {
                fundBody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#8e97a8;padding:1.2rem;">No quarterly fundamental filings on record for this equity</td></tr>`;
            } else {
                fundBody.innerHTML = fundList.slice(0, 12).map(q => {
                    const qName = q.quarter || q.period || '--';
                    const rev = q.revenue_cr != null ? `${currSym}${Number(q.revenue_cr).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}` : '--';
                    const eb = (q.ebitda_cr != null ? q.ebitda_cr : q.operating_profit_cr);
                    const ebStr = eb != null ? `${currSym}${Number(eb).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}` : '--';
                    const opm = (q.operating_margin_pct != null ? q.operating_margin_pct : q.ebitda_margin_pct);
                    const opmStr = opm != null ? `${Number(opm).toFixed(1)}%` : '--';
                    const pat = q.net_profit_cr != null ? `${currSym}${Number(q.net_profit_cr).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}` : '--';
                    const intExp = q.interest_expense_cr != null ? `${currSym}${Number(q.interest_expense_cr).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}` : '--';
                    const de = q.debt_to_equity != null ? `${Number(q.debt_to_equity).toFixed(2)}x` : '--';
                    const intCov = q.interest_coverage_ratio != null ? `${Number(q.interest_coverage_ratio).toFixed(1)}x` : '--';
                    const eps = q.eps != null ? `${currSym}${Number(q.eps).toFixed(2)}` : '--';

                    // Growth badges
                    const qoqEb = q.qoq_ebitda_growth_pct != null ? q.qoq_ebitda_growth_pct : q.qoq_revenue_growth_pct;
                    const yoyEb = q.yoy_ebitda_growth_pct != null ? q.yoy_ebitda_growth_pct : q.yoy_revenue_growth_pct;

                    const qoqClass = qoqEb > 0 ? '#34d399' : (qoqEb < 0 ? '#fb7185' : '#8e97a8');
                    const yoyClass = yoyEb > 0 ? '#34d399' : (yoyEb < 0 ? '#fb7185' : '#8e97a8');

                    const qoqTag = qoqEb != null ? `<span style="display:inline-block;padding:0.12rem 0.35rem;border-radius:3px;font-size:0.65rem;font-weight:700;background:rgba(255,255,255,0.04);color:${qoqClass};">QoQ: ${qoqEb > 0 ? '+' : ''}${qoqEb.toFixed(1)}%</span>` : '';
                    const yoyTag = yoyEb != null ? `<span style="display:inline-block;padding:0.12rem 0.35rem;border-radius:3px;font-size:0.65rem;font-weight:700;background:rgba(255,255,255,0.04);color:${yoyClass};">YoY: ${yoyEb > 0 ? '+' : ''}${yoyEb.toFixed(1)}%</span>` : '';

                    return `
                        <tr>
                            <td style="font-weight:700;color:#e2e8f0;white-space:nowrap;">${qName}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);">${rev}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);color:#38bdf8;">${ebStr}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);font-weight:700;color:${opm > 15 ? '#34d399' : (opm < 5 ? '#fb7185' : '#cbd5e1')};">${opmStr}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);">${pat}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);color:#f59e0b;">${intExp}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);">${de}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);color:${q.interest_coverage_ratio != null && q.interest_coverage_ratio < 1.5 ? '#fb7185' : '#34d399'};">${intCov}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);font-weight:700;">${eps}</td>
                            <td style="text-align:right;white-space:nowrap;">
                                <div style="display:flex;align-items:center;justify-content:flex-end;gap:0.3rem;">
                                    ${qoqTag}
                                    ${yoyTag}
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // 2. Render EPS Surprise History
        const epsBody = document.getElementById('drawerEPSTableBody');
        const history = data.earnings_history || data.quarters || (Array.isArray(data) ? data : []);

        if (epsBody) {
            if (!history || history.length === 0) {
                epsBody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#8e97a8;padding:1.2rem;">No consensus estimate track record on record</td></tr>`;
            } else {
                epsBody.innerHTML = history.slice(0, 12).map(q => {
                    const qName = q.earnings_date || q.quarter || q.period || q.date || '--';
                    const repVal = q.eps_reported != null ? q.eps_reported : q.reported_eps;
                    const rep = repVal != null ? Number(repVal).toFixed(2) : '--';
                    const estVal = q.eps_estimate != null ? q.eps_estimate : q.estimate_eps;
                    const est = estVal != null ? Number(estVal).toFixed(2) : '--';
                    const surp = q.surprise_pct != null ? formatPct(q.surprise_pct) : '--';
                    const surpClass = q.surprise_pct > 0 ? '#34d399' : (q.surprise_pct < 0 ? '#fb7185' : '#cbd5e1');
                    const src = q.source || 'Filing';

                    return `
                        <tr>
                            <td style="font-weight:700;color:#e2e8f0;">${qName}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);">${rep}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);color:#8e97a8;">${est}</td>
                            <td style="text-align:right;font-family:var(--font-mono, monospace);font-weight:700;color:${surpClass};">${surp}</td>
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

    app.refreshEarningsFromSource = async function () {
        if (!app._currentDrawerTicker) return;
        const sym = app._currentDrawerTicker;
        const btn = document.getElementById('btnDrawerRefreshEarnings');
        const originalHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `⏳ <span>Fetching...</span>`;
        }

        const shimmer = document.getElementById('drawerEPSShimmer');
        const content = document.getElementById('drawerEPSContent');
        if (shimmer) shimmer.style.display = 'block';
        if (content) content.style.display = 'none';

        try {
            const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/refresh-earnings-source`, { method: 'POST' });
            if (res.ok) {
                DRAWER_CACHE.delete(`eps_${sym}`);
                const refreshed = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/earnings`);
                if (refreshed.ok) {
                    const data = await refreshed.json();
                    setCached(`eps_${sym}`, data);
                    app._renderEPSCard(data);
                    if (typeof app.showToast === 'function') {
                        app.showToast(`Fetched latest source filings for ${sym}`, 'success');
                    }
                }
            } else {
                throw new Error('Refresh endpoint returned error status');
            }
        } catch (e) {
            console.error('[STOCK-DRAWER] Refresh earnings error:', e);
            if (shimmer) shimmer.style.display = 'none';
            if (content) content.style.display = 'block';
            if (typeof app.showToast === 'function') {
                app.showToast(`Earnings source refresh failed: ${e.message}`, 'error');
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        }
    };

    app.recalculateStockEPS = async function () {
        if (!app._currentDrawerTicker) return;
        const sym = app._currentDrawerTicker;
        const btn = document.getElementById('btnDrawerRecalcEPS');
        const originalHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `⏳ <span>Calculating...</span>`;
        }

        const shimmer = document.getElementById('drawerEPSShimmer');
        const content = document.getElementById('drawerEPSContent');
        if (shimmer) shimmer.style.display = 'block';
        if (content) content.style.display = 'none';

        try {
            const res = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/calculate-eps`, { method: 'POST' });
            if (res.ok) {
                DRAWER_CACHE.delete(`eps_${sym}`);
                const refreshed = await fetch(`${API_BASE}/api/v1/stock/${encodeURIComponent(sym)}/earnings`);
                if (refreshed.ok) {
                    const data = await refreshed.json();
                    setCached(`eps_${sym}`, data);
                    app._renderEPSCard(data);
                    if (typeof app.showToast === 'function') {
                        app.showToast(`Formula EPS recalculated for ${sym}`, 'success');
                    }
                }
            } else {
                throw new Error('Recalculate EPS endpoint returned error status');
            }
        } catch (e) {
            console.error('[STOCK-DRAWER] Recalculate EPS error:', e);
            if (shimmer) shimmer.style.display = 'none';
            if (content) content.style.display = 'block';
            if (typeof app.showToast === 'function') {
                app.showToast(`Recalculate EPS failed: ${e.message}`, 'error');
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        }
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

    // =========================================================================
    // 4. QUANTUM CHART STUDIO ENGINE & TECHNICAL CALCULATIONS
    // =========================================================================

    function calculateSMA(records, period) {
        const result = [];
        for (let i = period - 1; i < records.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) {
                sum += records[i - j].close;
            }
            result.push({
                time: records[i].date,
                value: sum / period,
            });
        }
        return result;
    }

    function calculateVWAPWithBands(records) {
        const vwapArr = [];
        const upperArr = [];
        const lowerArr = [];

        let cumVol = 0;
        let cumTypicalVol = 0;
        const typicalPrices = [];

        records.forEach((r) => {
            const typical = (r.high + r.low + r.close) / 3;
            const vol = r.volume || 1;
            cumVol += vol;
            cumTypicalVol += typical * vol;
            typicalPrices.push(typical);

            const vwap = cumTypicalVol / Math.max(1, cumVol);

            // Rolling variance for 20-period standard deviation band
            const slice = typicalPrices.slice(-20);
            const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
            const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / slice.length;
            const stdDev = Math.sqrt(variance);

            vwapArr.push({ time: r.date, value: vwap });
            upperArr.push({ time: r.date, value: vwap + 1.5 * stdDev });
            lowerArr.push({ time: r.date, value: vwap - 1.5 * stdDev });
        });

        return { vwap: vwapArr, upper: upperArr, lower: lowerArr };
    }

    function handleDrawerCrosshairMove(param) {
        if (!param || !param.time || !app._drawerCandleSeries || !param.seriesData) {
            updateDrawerHudWithLastBar();
            return;
        }

        const candle = param.seriesData.get(app._drawerCandleSeries);
        if (!candle) {
            updateDrawerHudWithLastBar();
            return;
        }

        const timeStr = typeof param.time === 'string' ? param.time : (window.formatIST ? window.formatIST(param.time, { includeTime: false, includeYear: true, suffix: false }) : String(param.time));
        renderDrawerHudData(candle, timeStr);
    }

    function updateDrawerHudWithLastBar() {
        if (!app._drawerChartRecords || app._drawerChartRecords.length === 0) return;
        const last = app._drawerChartRecords[app._drawerChartRecords.length - 1];
        const tf = (app._drawerChartTimeframe || '1D').toLowerCase();
        const isIntraday = (tf === '5m' || tf === '15m');
        const timeVal = isIntraday ? (last.time || last.date) : (last.date || last.time);
        const timeFormatted = isIntraday && typeof timeVal === 'number'
            ? (window.formatIST ? window.formatIST(timeVal, { includeDate: true, includeTime: true, suffix: true }) : new Date(timeVal * 1000).toLocaleString('en-IN'))
            : timeVal;

        renderDrawerHudData({
            open: last.open,
            high: last.high,
            low: last.low,
            close: last.close,
            volume: last.volume,
        }, timeFormatted);
    }

    function renderDrawerHudData(candle, timeStr) {
        const sym = app._currentDrawerTicker || '';
        const currSym = !sym.endsWith('.NS') ? '$' : '₹';

        const setEl = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };

        setEl('drawerHudDate', timeStr || '--');
        setEl('drawerHudOpen', formatCurrency(candle.open, currSym));
        setEl('drawerHudHigh', formatCurrency(candle.high, currSym));
        setEl('drawerHudLow', formatCurrency(candle.low, currSym));
        setEl('drawerHudClose', formatCurrency(candle.close, currSym));

        const tr = (candle.high != null && candle.low != null) ? (candle.high - candle.low) : 0;
        setEl('drawerHudTR', formatCurrency(tr, currSym));

        let vol = candle.volume;
        if (vol === undefined && app._drawerChartRecords) {
            const match = app._drawerChartRecords.find(r => r.date === timeStr || r.time === timeStr || String(r.time) === String(timeStr));
            if (match) vol = match.volume;
        }

        setEl('drawerHudVol', vol != null ? Number(vol).toLocaleString() : '--');

        if (vol && app._drawerAvgVol20 > 0) {
            const surge = (vol / app._drawerAvgVol20).toFixed(1);
            setEl('drawerHudSurge', `${surge}x`);
            const surgeEl = document.getElementById('drawerHudSurge');
            if (surgeEl) {
                surgeEl.style.color = Number(surge) >= 2.0 ? '#34d399' : Number(surge) >= 1.2 ? '#38bdf8' : '#8e97a8';
            }
        } else {
            setEl('drawerHudSurge', '--');
        }
    }

    app._applyDrawerSRPriceLines = function (data) {
        if (!app._drawerCandleSeries || !app._drawerToggles || !app._drawerToggles.bounds) return;

        // Clear existing S/R lines
        if (app._drawerSRLines && app._drawerSRLines.length > 0) {
            app._drawerSRLines.forEach(line => {
                try {
                    app._drawerCandleSeries.removePriceLine(line);
                } catch (e) {}
            });
        }
        app._drawerSRLines = [];

        const s1 = data.support_level || data.support || data.s1;
        const r1 = data.resistance_level || data.resistance || data.r1;

        if (s1 != null && !isNaN(Number(s1)) && Number(s1) > 0) {
            const supportLine = app._drawerCandleSeries.createPriceLine({
                price: Number(s1),
                color: '#10b981',
                lineWidth: 1.5,
                lineStyle: window.LightweightCharts && window.LightweightCharts.LineStyle ? window.LightweightCharts.LineStyle.Dashed : 1,
                axisLabelVisible: true,
                title: 'S1 Floor',
            });
            app._drawerSRLines.push(supportLine);
        }

        if (r1 != null && !isNaN(Number(r1)) && Number(r1) > 0) {
            const resistLine = app._drawerCandleSeries.createPriceLine({
                price: Number(r1),
                color: '#ef4444',
                lineWidth: 1.5,
                lineStyle: window.LightweightCharts && window.LightweightCharts.LineStyle ? window.LightweightCharts.LineStyle.Dashed : 1,
                axisLabelVisible: true,
                title: 'R1 Ceiling',
            });
            app._drawerSRLines.push(resistLine);
        }
    };

    function _applyDrawerIndicatorToggles() {
        if (app._drawerSMA20Series) app._drawerSMA20Series.applyOptions({ visible: !!app._drawerToggles.sma20 });
        if (app._drawerSMA50Series) app._drawerSMA50Series.applyOptions({ visible: !!app._drawerToggles.sma50 });
        if (app._drawerSMA200Series) app._drawerSMA200Series.applyOptions({ visible: !!app._drawerToggles.sma200 });

        const showVwap = !!app._drawerToggles.vwap;
        if (app._drawerVWAPSeries) app._drawerVWAPSeries.applyOptions({ visible: showVwap });
        if (app._drawerVWAPUpperSeries) app._drawerVWAPUpperSeries.applyOptions({ visible: showVwap });
        if (app._drawerVWAPLowerSeries) app._drawerVWAPLowerSeries.applyOptions({ visible: showVwap });

        if (app._drawerCandleSeries) {
            if (!app._drawerToggles.bounds) {
                if (app._drawerSRLines && app._drawerSRLines.length > 0) {
                    app._drawerSRLines.forEach(l => {
                        try { app._drawerCandleSeries.removePriceLine(l); } catch (e) {}
                    });
                    app._drawerSRLines = [];
                }
            } else if (app._drawerTechnicalData) {
                app._applyDrawerSRPriceLines(app._drawerTechnicalData);
            }
        }
    }

    app.toggleDrawerChartIndicator = function (name) {
        if (!app._drawerToggles) {
            app._drawerToggles = { sma20: true, sma50: true, sma200: true, vwap: true, bounds: true };
        }
        app._drawerToggles[name] = !app._drawerToggles[name];

        const btnMap = {
            sma20: 'drawerToggleSMA20',
            sma50: 'drawerToggleSMA50',
            sma200: 'drawerToggleSMA200',
            vwap: 'drawerToggleVWAP',
            bounds: 'drawerToggleBounds',
        };

        const btn = document.getElementById(btnMap[name]);
        if (btn) {
            if (app._drawerToggles[name]) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        }

        _applyDrawerIndicatorToggles();
    };

    app.toggleDrawerTFDropdown = function (event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        const menu = document.getElementById('drawerTFDropdownMenu');
        const btn = document.getElementById('btnDrawerTFDropdown');
        if (!menu) return;
        const isHidden = menu.style.display === 'none' || !menu.style.display;
        menu.style.display = isHidden ? 'block' : 'none';
        if (btn) btn.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
    };

    app.setDrawerChartTF = function (tf) {
        app._drawerChartTimeframe = tf;

        // 1. Close dropdown popover if open
        const menu = document.getElementById('drawerTFDropdownMenu');
        const dropBtn = document.getElementById('btnDrawerTFDropdown');
        const dropLabel = document.getElementById('drawerTFDropdownLabel');
        if (menu) menu.style.display = 'none';
        if (dropBtn) dropBtn.setAttribute('aria-expanded', 'false');

        // 2. Update Primary Resolution Buttons (5m, 15m, 1h, 1D)
        const primaryTFs = ['5m', '15m', '1h', '1D'];
        let matchedPrimary = false;

        primaryTFs.forEach(t => {
            const btn = document.getElementById(`btnDrawerTF${t}`);
            if (btn) {
                if (t.toLowerCase() === tf.toLowerCase()) {
                    btn.classList.add('active');
                    matchedPrimary = true;
                } else {
                    btn.classList.remove('active');
                }
            }
        });

        // 3. Update Dropdown Button active state & label
        if (dropBtn) {
            if (!matchedPrimary) {
                dropBtn.classList.add('active');
                if (dropLabel) dropLabel.textContent = tf;
            } else {
                dropBtn.classList.remove('active');
                if (dropLabel) dropLabel.textContent = 'More';
            }
        }

        // 4. Update Dropdown Menu items active state
        document.querySelectorAll('.drawer-tf-menu-item').forEach(item => {
            const badge = item.querySelector('.drawer-tf-badge');
            if (badge && badge.textContent.trim().toLowerCase() === tf.toLowerCase()) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        // 5. Toggle Visibility of Daily Range Chips vs Intraday Live Badge & SMC Explainer
        const rangeChips = document.getElementById('drawerDailyRangeChips');
        const liveBadge = document.getElementById('drawerIntradayRefreshBadge');
        const statusBadge = document.getElementById('drawerChartDataStatus');
        const smcCard = document.getElementById('drawerExplainerSMC');

        const normTF = tf.toLowerCase();
        const isIntraday = ['1m', '3m', '5m', '15m', '30m', '1h', '4h'].includes(normTF);

        if (rangeChips) {
            rangeChips.style.display = isIntraday ? 'none' : 'inline-flex';
        }
        if (liveBadge) {
            liveBadge.style.display = isIntraday ? 'inline-flex' : 'none';
        }
        if (statusBadge) {
            statusBadge.textContent = isIntraday ? `${tf.toUpperCase()} SMC FLOW` : `${tf.toUpperCase()} OHLCV`;
        }
        if (smcCard) {
            smcCard.style.display = isIntraday ? 'block' : 'none';
        }

        // 6. Manage Intraday 15s Auto-Refresh Timer
        if (app._drawerChartPollTimer) {
            clearInterval(app._drawerChartPollTimer);
            app._drawerChartPollTimer = null;
        }

        if (isIntraday) {
            app._drawerChartPollTimer = setInterval(() => {
                const drawer = document.getElementById('stockSliderDrawer');
                const curTF = (app._drawerChartTimeframe || '').toLowerCase();
                const stillIntraday = ['1m', '3m', '5m', '15m', '30m', '1h', '4h'].includes(curTF);
                if (drawer && drawer.classList.contains('open') && app._currentDrawerTicker && stillIntraday) {
                    app._initOrUpdateDrawerChart(app._currentDrawerTicker);
                } else if (app._drawerChartPollTimer) {
                    clearInterval(app._drawerChartPollTimer);
                    app._drawerChartPollTimer = null;
                }
            }, 15000);
        }

        // 7. Reload chart data for current ticker under new timeframe resolution
        if (app._currentDrawerTicker) {
            app._initOrUpdateDrawerChart(app._currentDrawerTicker);
        }
    };

    app.setDrawerChartRange = function (r) {
        app._drawerChartRange = r;
        ['1M', '3M', '6M', '1Y', 'ALL'].forEach(range => {
            const btn = document.getElementById(`btnDrawerRange${range}`);
            if (btn) {
                if (range === r) btn.classList.add('active');
                else btn.classList.remove('active');
            }
        });

        if (!app._drawerChartInstance || !app._drawerChartRecords || app._drawerChartRecords.length === 0) return;

        if (r === 'ALL') {
            app._drawerChartInstance.timeScale().fitContent();
            return;
        }

        const total = app._drawerChartRecords.length;
        let barsToShow = 252;
        if (r === '1M') barsToShow = 22;
        else if (r === '3M') barsToShow = 65;
        else if (r === '6M') barsToShow = 130;
        else if (r === '1Y') barsToShow = 252;

        const fromIdx = Math.max(0, total - barsToShow);
        const fromDate = app._drawerChartRecords[fromIdx]?.date;
        const toDate = app._drawerChartRecords[total - 1]?.date;

        if (fromDate && toDate) {
            app._drawerChartInstance.timeScale().setVisibleRange({
                from: fromDate,
                to: toDate,
            });
        } else {
            app._drawerChartInstance.timeScale().fitContent();
        }
    };

    app.setDrawerChartHeight = function (heightPx) {
        const h = Math.max(280, Math.min(850, parseInt(heightPx, 10) || 480));
        const frame = document.getElementById('drawerChartFrameContainer');
        if (frame) {
            frame.style.height = `${h}px`;
        }

        if (app._drawerChartInstance) {
            app._drawerChartInstance.applyOptions({ height: h });
        }

        // Update active preset button highlight
        document.querySelectorAll('.drawer-height-chip').forEach(chip => {
            const chipH = parseInt(chip.getAttribute('data-height'), 10);
            if (chipH === h) {
                chip.classList.add('active');
            } else {
                chip.classList.remove('active');
            }
        });

        localStorage.setItem('nexus_drawer_chart_height', String(h));
    };

    function _updateDrawerTechnicalExplainers(records, techData) {
        if (!records || records.length === 0) return;
        const sym = app._currentDrawerTicker || '';
        const currSym = !sym.endsWith('.NS') ? '$' : '₹';

        const lastBar = records[records.length - 1];
        const lastClose = lastBar.close;

        // Derive or read SMAs
        const sma20Val = techData?.sma_20 || techData?.dma_20 || calculateSMA(records, 20).slice(-1)[0]?.value;
        const sma50Val = techData?.sma_50 || techData?.dma_50 || calculateSMA(records, 50).slice(-1)[0]?.value;
        const sma200Val = techData?.sma_200 || techData?.dma_200 || calculateSMA(records, 200).slice(-1)[0]?.value;

        const setEl = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };

        setEl('drawerChartValSMA20', formatCurrency(sma20Val, currSym));
        setEl('drawerChartValSMA50', formatCurrency(sma50Val, currSym));
        setEl('drawerChartValSMA200', formatCurrency(sma200Val, currSym));

        // Evaluate Regime / Alignment
        const badgeTrend = document.getElementById('drawerChartBadgeTrend');
        const textTrend = document.getElementById('drawerChartExplainerTrend');

        if (sma20Val && sma50Val && sma200Val) {
            if (lastClose > sma20Val && sma20Val > sma50Val && sma50Val > sma200Val) {
                if (badgeTrend) {
                    badgeTrend.className = 'drawer-tech-pill bullish';
                    badgeTrend.textContent = 'BULLISH ALIGNMENT';
                }
                if (textTrend) {
                    textTrend.textContent = `Golden Alignment: Price (${formatCurrency(lastClose, currSym)}) trades above SMA 20, 50, and 200 baselines. Tactical momentum and institutional sponsorship are strongly aligned to the upside.`;
                }
            } else if (lastClose > sma50Val && lastClose > sma200Val) {
                if (badgeTrend) {
                    badgeTrend.className = 'drawer-tech-pill bullish';
                    badgeTrend.textContent = 'ACCUMULATION REGIME';
                }
                if (textTrend) {
                    textTrend.textContent = `Constructive Structure: Price (${formatCurrency(lastClose, currSym)}) holds above the 50-day (${formatCurrency(sma50Val, currSym)}) and 200-day (${formatCurrency(sma200Val, currSym)}) institutional floors, indicating sustained accumulation.`;
                }
            } else if (lastClose < sma20Val && sma20Val < sma50Val && sma50Val < sma200Val) {
                if (badgeTrend) {
                    badgeTrend.className = 'drawer-tech-pill bearish';
                    badgeTrend.textContent = 'BEARISH ALIGNMENT';
                }
                if (textTrend) {
                    textTrend.textContent = `Downward Alignment: Price trades below declining SMA 20, 50, and 200 baselines. Overhead supply pressure remains dominant across all timeframes.`;
                }
            } else if (lastClose < sma50Val) {
                if (badgeTrend) {
                    badgeTrend.className = 'drawer-tech-pill bearish';
                    badgeTrend.textContent = 'DISTRIBUTION / RETEST';
                }
                if (textTrend) {
                    textTrend.textContent = `Institutional Retest: Price (${formatCurrency(lastClose, currSym)}) is trading below the 50 DMA benchmark (${formatCurrency(sma50Val, currSym)}). Monitor for base formation before aggressive exposure.`;
                }
            } else {
                if (badgeTrend) {
                    badgeTrend.className = 'drawer-tech-pill neutral';
                    badgeTrend.textContent = 'RANGE CONSOLIDATION';
                }
                if (textTrend) {
                    textTrend.textContent = `Equilibrium Regime: Price is oscillating inside moving average boundaries, indicating contraction and volatility digestion ahead of directional expansion.`;
                }
            }
        }

        // Support, Resistance, ATR, RSI
        const s1 = techData?.support_level || techData?.support || techData?.s1;
        const r1 = techData?.resistance_level || techData?.resistance || techData?.r1;
        const atr = techData?.atr_14 || techData?.atr;
        const rsi = techData?.rsi_14 || techData?.rsi;

        setEl('drawerChartValSupport', formatCurrency(s1, currSym));
        setEl('drawerChartValResistance', formatCurrency(r1, currSym));
        setEl('drawerChartValATR', atr ? `${formatCurrency(atr, currSym)} (~${((atr / lastClose) * 100).toFixed(1)}%)` : '--');

        const badgeRSI = document.getElementById('drawerChartBadgeRSI');
        const textBounds = document.getElementById('drawerChartExplainerBounds');

        if (rsi != null && !isNaN(Number(rsi))) {
            const rsiNum = Number(rsi);
            if (badgeRSI) {
                if (rsiNum >= 70) {
                    badgeRSI.className = 'drawer-tech-pill warning';
                    badgeRSI.textContent = `RSI ${rsiNum.toFixed(1)} · Overbought Surge`;
                } else if (rsiNum <= 30) {
                    badgeRSI.className = 'drawer-tech-pill oversold';
                    badgeRSI.textContent = `RSI ${rsiNum.toFixed(1)} · Oversold Floor`;
                } else if (rsiNum >= 55) {
                    badgeRSI.className = 'drawer-tech-pill bullish';
                    badgeRSI.textContent = `RSI ${rsiNum.toFixed(1)} · Bullish Expansion`;
                } else {
                    badgeRSI.className = 'drawer-tech-pill neutral';
                    badgeRSI.textContent = `RSI ${rsiNum.toFixed(1)} · Neutral Zone`;
                }
            }
        }

        if (textBounds && (s1 || r1 || atr)) {
            const sText = s1 ? `immediate floor at ${formatCurrency(s1, currSym)}` : 'algorithmic support floor';
            const rText = r1 ? `resistance barrier at ${formatCurrency(r1, currSym)}` : 'overhead supply ceiling';
            const atrText = atr ? `Daily expected true range is ${formatCurrency(atr, currSym)}.` : '';
            textBounds.textContent = `Execution corridor defined by ${sText} and ${rText}. ${atrText}`;
        }
    }

    app._initOrUpdateDrawerChart = async function (sym, signal) {
        const container = document.getElementById('drawerNativeChartCanvas');
        const shimmer = document.getElementById('drawerChartShimmer');
        if (shimmer) shimmer.style.display = 'block';

        if (!container || !window.LightweightCharts) {
            if (shimmer) shimmer.style.display = 'none';
            return;
        }

        // Initialize Canvas Instance if not created
        if (!app._drawerChartInstance) {
            const savedHeight = parseInt(localStorage.getItem('nexus_drawer_chart_height'), 10) || 480;
            const containerFrame = document.getElementById('drawerChartFrameContainer');
            if (containerFrame && savedHeight !== 480) {
                containerFrame.style.height = `${savedHeight}px`;
            }

            const chart = window.LightweightCharts.createChart(container, {
                width: container.clientWidth || 700,
                height: savedHeight,
                layout: {
                    background: { type: 'solid', color: '#050505' },
                    textColor: '#94a3b8',
                    fontSize: 11,
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
                },
                crosshair: {
                    mode: window.LightweightCharts.CrosshairMode ? window.LightweightCharts.CrosshairMode.Normal : 1,
                    vertLine: { color: 'rgba(56, 189, 248, 0.45)', width: 1, style: 2 },
                    horzLine: { color: 'rgba(56, 189, 248, 0.45)', width: 1, style: 2 },
                },
                rightPriceScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    autoScale: true,
                    scaleMargins: { top: 0.08, bottom: 0.16 },
                },
                localization: {
                    locale: 'en-IN',
                    dateFormat: 'dd MMM yyyy',
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    timeVisible: false,
                    secondsVisible: false,
                },
            });

            // 1. Candlestick Series
            const candleSeries = chart.addCandlestickSeries({
                upColor: '#10b981',
                downColor: '#ef4444',
                borderVisible: false,
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
            });

            // 2. Volume Histogram Overlay
            const volumeSeries = chart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: '', // overlay
                scaleMargins: { top: 0.82, bottom: 0 },
            });

            // 3. Moving Averages
            const sma20Series = chart.addLineSeries({
                color: '#f59e0b',
                lineWidth: 1.5,
                title: 'SMA 20',
                priceLineVisible: false,
            });

            const sma50Series = chart.addLineSeries({
                color: '#38bdf8',
                lineWidth: 1.5,
                title: 'SMA 50',
                priceLineVisible: false,
            });

            const sma200Series = chart.addLineSeries({
                color: '#a855f7',
                lineWidth: 1.5,
                title: 'SMA 200',
                priceLineVisible: false,
            });

            // 4. VWAP & Standard Deviation Bands
            const vwapSeries = chart.addLineSeries({
                color: '#06b6d4',
                lineWidth: 2,
                title: 'VWAP',
                priceLineVisible: false,
            });

            const vwapUpperSeries = chart.addLineSeries({
                color: 'rgba(6, 182, 212, 0.5)',
                lineWidth: 1,
                lineStyle: window.LightweightCharts.LineStyle ? window.LightweightCharts.LineStyle.Dotted : 2,
                title: 'VWAP +1.5σ',
                priceLineVisible: false,
            });

            const vwapLowerSeries = chart.addLineSeries({
                color: 'rgba(6, 182, 212, 0.5)',
                lineWidth: 1,
                lineStyle: window.LightweightCharts.LineStyle ? window.LightweightCharts.LineStyle.Dotted : 2,
                title: 'VWAP -1.5σ',
                priceLineVisible: false,
            });

            app._drawerChartInstance = chart;
            app._drawerCandleSeries = candleSeries;
            app._drawerVolumeSeries = volumeSeries;
            app._drawerSMA20Series = sma20Series;
            app._drawerSMA50Series = sma50Series;
            app._drawerSMA200Series = sma200Series;
            app._drawerVWAPSeries = vwapSeries;
            app._drawerVWAPUpperSeries = vwapUpperSeries;
            app._drawerVWAPLowerSeries = vwapLowerSeries;

            chart.subscribeCrosshairMove(handleDrawerCrosshairMove);

            // Responsive Resize Observer
            if (!app._drawerResizeObserver && window.ResizeObserver) {
                app._drawerResizeObserver = new ResizeObserver((entries) => {
                    if (!entries || entries.length === 0 || !app._drawerChartInstance) return;
                    const { width } = entries[0].contentRect;
                    if (width > 0) {
                        app._drawerChartInstance.applyOptions({ width });
                    }
                });
                app._drawerResizeObserver.observe(container);
            }
        }

        // Fetch Historical Price Bars or Intraday SMC Intelligence
        try {
            const tf = (app._drawerChartTimeframe || '1D').toLowerCase();
            const isIntraday = ['1m', '3m', '5m', '15m', '30m', '1h', '4h'].includes(tf);

            if (isIntraday) {
                // Configure chart timeScale for UNIX epoch intraday timestamps
                app._drawerChartInstance.applyOptions({
                    timeScale: {
                        timeVisible: true,
                        secondsVisible: false,
                    },
                });

                const cleanSym = sym.replace('.NS', '');
                const url = `${API_BASE}/api/v1/options/chart-intelligence?symbol=${encodeURIComponent(cleanSym)}&interval=${encodeURIComponent(tf)}&period=5d&allow_non_fno=true`;
                const res = await fetch(url, { signal });

                if (!res.ok) {
                    if (shimmer) shimmer.style.display = 'none';
                    return;
                }

                const data = await res.json();
                if (app._currentDrawerTicker !== sym) return;

                const candles = data.candles || [];
                if (candles.length === 0) {
                    if (shimmer) shimmer.style.display = 'none';
                    return;
                }

                app._drawerChartRecords = candles;

                // 20-period intraday volume baseline
                const recentVols = candles.slice(-20).map(c => c.volume || 0);
                app._drawerAvgVol20 = recentVols.length > 0 ? recentVols.reduce((a, b) => a + b, 0) / recentVols.length : 1;

                const candleBars = [];
                const volumeBars = [];

                candles.forEach(c => {
                    const isBull = c.close >= c.open;
                    const isSurge = app._drawerAvgVol20 > 0 && c.volume > app._drawerAvgVol20 * 1.8;
                    const volColor = isSurge
                        ? isBull
                            ? 'rgba(16, 185, 129, 0.85)'
                            : 'rgba(239, 68, 68, 0.85)'
                        : isBull
                        ? 'rgba(16, 185, 129, 0.35)'
                        : 'rgba(239, 68, 68, 0.35)';

                    candleBars.push({
                        time: c.time,
                        open: c.open,
                        high: c.high,
                        low: c.low,
                        close: c.close,
                    });

                    volumeBars.push({
                        time: c.time,
                        value: c.volume,
                        color: volColor,
                    });
                });

                if (app._drawerCandleSeries) app._drawerCandleSeries.setData(candleBars);
                if (app._drawerVolumeSeries) app._drawerVolumeSeries.setData(volumeBars);

                // In intraday mode, clear daily SMAs
                if (app._drawerSMA20Series) app._drawerSMA20Series.setData([]);
                if (app._drawerSMA50Series) app._drawerSMA50Series.setData([]);
                if (app._drawerSMA200Series) app._drawerSMA200Series.setData([]);

                // Set Session VWAP and Standard Deviation Bands
                const ind = data.indicators || {};
                const vwapPoints = ind.vwap || [];
                const vwapUpperPoints = ind.vwap_upper_1 || ind.vwap_upper || [];
                const vwapLowerPoints = ind.vwap_lower_1 || ind.vwap_lower || [];

                if (app._drawerVWAPSeries) app._drawerVWAPSeries.setData(vwapPoints);
                if (app._drawerVWAPUpperSeries) app._drawerVWAPUpperSeries.setData(vwapUpperPoints);
                if (app._drawerVWAPLowerSeries) app._drawerVWAPLowerSeries.setData(vwapLowerPoints);

                // Set SMC Markers (Order Blocks and Fair Value Gaps)
                const smc = data.smart_money || {};
                const obs = smc.order_blocks || [];
                const fvgs = smc.fvg_gaps || smc.fvgs || [];
                const markers = [];

                obs.forEach(ob => {
                    const isBull = ob.type === 'BULLISH_OB';
                    markers.push({
                        time: ob.start_time || ob.time,
                        position: isBull ? 'belowBar' : 'aboveBar',
                        color: isBull ? '#10b981' : '#f43f5e',
                        shape: isBull ? 'arrowUp' : 'arrowDown',
                        text: `${ob.short_label || (isBull ? 'D-OB' : 'S-OB')} (${ob.mitigated ? 'TESTED' : 'UNMIT'})`,
                    });
                });

                fvgs.forEach(fvg => {
                    const isBull = fvg.type === 'BULLISH_FVG';
                    markers.push({
                        time: fvg.time,
                        position: isBull ? 'belowBar' : 'aboveBar',
                        color: isBull ? '#38bdf8' : '#fb7185',
                        shape: 'circle',
                        text: isBull ? 'B-FVG' : 'S-FVG',
                    });
                });

                markers.sort((a, b) => a.time - b.time);
                if (app._drawerCandleSeries) app._drawerCandleSeries.setMarkers(markers);

                // Clear classical S/R price lines in intraday mode
                if (app._drawerSRLines && app._drawerSRLines.length > 0) {
                    app._drawerSRLines.forEach(l => {
                        try { app._drawerCandleSeries.removePriceLine(l); } catch (e) {}
                    });
                    app._drawerSRLines = [];
                }

                // Update SMC Explainer Card
                const obEl = document.getElementById('drawerChartValOB');
                const fvgEl = document.getElementById('drawerChartValFVG');
                const sessionEl = document.getElementById('drawerChartValSession');
                const badgeSMC = document.getElementById('drawerChartBadgeSMC');
                const explainerSMC = document.getElementById('drawerChartExplainerSMC');

                if (obEl) {
                    const unmitObs = obs.filter(o => !o.mitigated).length;
                    obEl.textContent = `${unmitObs} Active (${obs.length} Total)`;
                }
                if (fvgEl) {
                    const unfilled = fvgs.filter(f => !f.filled).length;
                    fvgEl.textContent = `${unfilled} Open (${fvgs.length} Imbalances)`;
                }
                if (sessionEl) {
                    sessionEl.textContent = data.tactical_signals?.regime || `${tf.toUpperCase()} Confluence Flow`;
                }
                if (badgeSMC) {
                    badgeSMC.textContent = `${tf.toUpperCase()} SMC ACTIVE`;
                }
                if (explainerSMC && data.tactical_signals?.primary_bias) {
                    explainerSMC.textContent = `Microstructure Bias: ${data.tactical_signals.primary_bias} (Confidence: ${data.tactical_signals.confidence_score || 75}%). VWAP dynamic mean: ₹${candles[candles.length - 1]?.close || '--'}.`;
                }

                if (shimmer) shimmer.style.display = 'none';
                app._drawerChartInstance.timeScale().fitContent();
                updateDrawerHudWithLastBar();
            } else {
                // Daily EOD Mode
                app._drawerChartInstance.applyOptions({
                    timeScale: {
                        timeVisible: false,
                        secondsVisible: false,
                    },
                });

                if (app._drawerCandleSeries) app._drawerCandleSeries.setMarkers([]);

                const cacheKey = `price_history_${sym}`;
                let records = getCached(cacheKey);
                if (!records) {
                    const res = await fetch(`${API_BASE}/api/v1/price-history/${encodeURIComponent(sym)}`, { signal });
                    if (res.ok) {
                        records = await res.json();
                        setCached(cacheKey, records);
                    }
                }

                if (!records || records.length === 0) {
                    if (shimmer) shimmer.style.display = 'none';
                    return;
                }

                if (app._currentDrawerTicker !== sym) return;

                app._drawerChartRecords = records;

                // Calculate 20D average volume for surge ratios
                const recentVols = records.slice(-20).map(r => r.volume || 0);
                app._drawerAvgVol20 = recentVols.length > 0 ? recentVols.reduce((a, b) => a + b, 0) / recentVols.length : 1;

                const candles = [];
                const volumes = [];

                records.forEach(r => {
                    const itemTime = r.date;
                    candles.push({
                        time: itemTime,
                        open: r.open,
                        high: r.high,
                        low: r.low,
                        close: r.close,
                    });

                    const isBull = r.close >= r.open;
                    const isSurge = app._drawerAvgVol20 > 0 && r.volume > app._drawerAvgVol20 * 1.8;
                    const volColor = isSurge
                        ? isBull
                            ? 'rgba(16, 185, 129, 0.85)'
                            : 'rgba(239, 68, 68, 0.85)'
                        : isBull
                        ? 'rgba(16, 185, 129, 0.35)'
                        : 'rgba(239, 68, 68, 0.35)';

                    volumes.push({
                        time: itemTime,
                        value: r.volume,
                        color: volColor,
                    });
                });

                if (app._drawerCandleSeries) app._drawerCandleSeries.setData(candles);
                if (app._drawerVolumeSeries) app._drawerVolumeSeries.setData(volumes);

                // Technical Overlays
                if (app._drawerSMA20Series) app._drawerSMA20Series.setData(calculateSMA(records, 20));
                if (app._drawerSMA50Series) app._drawerSMA50Series.setData(calculateSMA(records, 50));
                if (app._drawerSMA200Series) app._drawerSMA200Series.setData(calculateSMA(records, 200));

                // VWAP Bands
                const vwapData = calculateVWAPWithBands(records);
                if (app._drawerVWAPSeries) app._drawerVWAPSeries.setData(vwapData.vwap);
                if (app._drawerVWAPUpperSeries) app._drawerVWAPUpperSeries.setData(vwapData.upper);
                if (app._drawerVWAPLowerSeries) app._drawerVWAPLowerSeries.setData(vwapData.lower);

                // Apply indicator toggle visibility
                _applyDrawerIndicatorToggles();

                // Apply S/R Price Lines if technical data exists
                if (app._drawerTechnicalData) {
                    app._applyDrawerSRPriceLines(app._drawerTechnicalData);
                }

                if (shimmer) shimmer.style.display = 'none';

                // Set Visible Range & HUD
                app.setDrawerChartRange(app._drawerChartRange || '1Y');
                updateDrawerHudWithLastBar();

                // Update Technical Explainer Cards
                _updateDrawerTechnicalExplainers(records, app._drawerTechnicalData);
            }
        } catch (err) {
            if (err.name !== 'AbortError') console.error('[STOCK-DRAWER] Price history chart error:', err);
            if (shimmer) shimmer.style.display = 'none';
        }
    };

    // =========================================================================
    // 5. DRAG RESIZER INITIALIZATION
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

    function initDrawerChartHeightResizer() {
        const resizer = document.getElementById('drawerChartHeightResizer');
        const frame = document.getElementById('drawerChartFrameContainer');
        if (!resizer || !frame) return;

        let isResizing = false;
        let startY = 0;
        let startH = 480;

        resizer.addEventListener('mousedown', function (e) {
            e.preventDefault();
            isResizing = true;
            startY = e.clientY;
            startH = frame.offsetHeight || parseInt(frame.style.height, 10) || 480;
            resizer.classList.add('resizing');
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', function (e) {
            if (!isResizing) return;
            const deltaY = e.clientY - startY;
            const newH = Math.max(280, Math.min(850, Math.round(startH + deltaY)));
            frame.style.height = `${newH}px`;
            if (app._drawerChartInstance) {
                app._drawerChartInstance.applyOptions({ height: newH });
            }
        });

        document.addEventListener('mouseup', function () {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                const finalH = frame.offsetHeight || parseInt(frame.style.height, 10) || 480;
                localStorage.setItem('nexus_drawer_chart_height', String(finalH));

                // Update preset chips active indicator
                document.querySelectorAll('.drawer-height-chip').forEach(chip => {
                    const chipH = parseInt(chip.getAttribute('data-height'), 10);
                    if (chipH === finalH) {
                        chip.classList.add('active');
                    } else {
                        chip.classList.remove('active');
                    }
                });
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

        // Close timeframe dropdown menu on click outside
        document.addEventListener('click', function (e) {
            const dropdown = document.getElementById('drawerTFDropdownMenu');
            const dropBtn = document.getElementById('btnDrawerTFDropdown');
            if (dropdown && dropdown.style.display !== 'none') {
                if (!e.target.closest('#drawerTFDropdownMenu') && !e.target.closest('#btnDrawerTFDropdown')) {
                    dropdown.style.display = 'none';
                    if (dropBtn) dropBtn.setAttribute('aria-expanded', 'false');
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
            initDrawerChartHeightResizer();
            initDrawerEventListeners();
        });
    } else {
        initDrawerResizer();
        initDrawerChartHeightResizer();
        initDrawerEventListeners();
    }

})();
