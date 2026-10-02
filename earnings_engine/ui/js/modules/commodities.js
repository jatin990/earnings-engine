/**
 * Commodities & Precious Metals Smart Chart Module
 *
 * Provides institutional TradingView Lightweight Charts canvas with:
 * - Real-time / intraday candlesticks for Gold, Silver, Crude Oil, Natural Gas, Copper
 * - Dynamic Session VWAP (±1.5σ dispersion bands)
 * - 15-minute Opening Range Breakout (ORB-15) and expansion targets
 * - Smart Money Concepts (SMC): Bullish (D-OB) and Bearish (S-OB) Order Blocks and Fair Value Gaps
 * - Algorithmic Support & Resistance Trendlines
 * - Interactive SMC Playbook educational drawer
 * - Interactive Crosshair Hover Inspector Bar (#commHoverInspectorCard)
 * - Real-Time Incremental Tick Engine (3000ms poller)
 * - Actionable 3-Column Tactical Trade HUD Deck (Where to Buy / Where to Sell)
 */
(function (window) {
    'use strict';

    window.commoditiesModule = window.commoditiesModule || {};
    const mod = window.commoditiesModule;

    mod._symbol = 'GOLD';
    mod._timeframe = '5m';
    mod._period = '5d';
    mod._layers = {
        vwap: true,
        orb: true,
        ob: true,
        pivots: true,
        trendlines: true,
    };

    mod._chart = null;
    mod._candleSeries = null;
    mod._volumeSeries = null;
    mod._vwapSeries = null;
    mod._vwapUpperSeries = null;
    mod._vwapLowerSeries = null;
    mod._trendlineSeries = [];
    mod._priceLines = [];
    mod._chartData = null;
    mod._pollTimer = null;
    mod._tickTimer = null;
    mod._avgVolume = 1;
    mod._hasFitted = false;
    mod._isFullscreen = false;
    mod._escListenerBound = false;
    mod._crosshairBound = false;

    /**
     * Initialize the module
     */
    mod.init = function () {
        mod.loadChart(false);

        // Full dataset reload timer (60s)
        if (!mod._pollTimer) {
            mod._pollTimer = setInterval(() => {
                const tab = document.getElementById('tab-commodities');
                if (tab && (tab.style.display !== 'none' || tab.classList.contains('active'))) {
                    mod.loadChart(false);
                }
            }, 60000);
        }

        // Fast Incremental Tick Poller (3000ms)
        if (!mod._tickTimer) {
            mod._tickTimer = setInterval(() => {
                const tab = document.getElementById('tab-commodities');
                if (tab && (tab.style.display !== 'none' || tab.classList.contains('active'))) {
                    mod.pollLatestTick();
                }
            }, 3000);
        }
    };

    /**
     * Toggle educational SMC Playbook drawer
     */
    mod.togglePlaybook = function () {
        const content = document.getElementById('commPlaybookContent');
        const chevron = document.getElementById('commPlaybookChevron');
        if (!content) return;
        const isHidden = content.style.display === 'none' || !content.style.display;
        content.style.display = isHidden ? 'block' : 'none';
        if (chevron) {
            chevron.textContent = isHidden ? '▲' : '▼';
        }
    };

    /**
     * Switch active commodity symbol
     */
    mod.switchCommodity = function (symbol) {
        if (!symbol) return;
        const clean = symbol.trim().toUpperCase();
        mod._symbol = clean;
        mod._hasFitted = false;

        // Update pills
        document.querySelectorAll('.comm-asset-pill').forEach(pill => {
            const isActive = pill.getAttribute('data-asset') === clean;
            pill.classList.toggle('active', isActive);
            pill.style.background = isActive ? 'rgba(234, 179, 8, 0.25)' : 'transparent';
            pill.style.color = isActive ? '#eab308' : 'var(--text-secondary)';
            pill.style.borderColor = isActive ? 'rgba(234, 179, 8, 0.5)' : 'rgba(255, 255, 255, 0.1)';
        });

        const select = document.getElementById('commAssetSelect');
        if (select) select.value = clean;

        mod.loadChart(false);
    };

    /**
     * Set timeframe interval
     */
    mod.setTimeframe = function (tf) {
        if (!tf) return;
        mod._timeframe = tf;
        mod._period = (tf === '1d' || tf === '1D') ? '6mo' : '5d';
        mod._hasFitted = false;

        document.querySelectorAll('.comm-tf-btn').forEach(btn => {
            const isActive = btn.getAttribute('data-tf') === tf;
            btn.classList.toggle('active', isActive);
            btn.style.background = isActive ? 'rgba(255, 255, 255, 0.18)' : 'transparent';
            btn.style.color = isActive ? '#ffffff' : 'var(--text-secondary)';
            btn.style.fontWeight = isActive ? '700' : '400';
            btn.style.borderRadius = '4px';
        });

        mod.loadChart(false);
    };

    /**
     * Toggle layer overlay
     */
    mod.toggleLayer = function (layer, isChecked) {
        if (layer in mod._layers) {
            mod._layers[layer] = isChecked;
            if (mod._chartData) {
                mod.renderChartLayers(mod._chartData);
            }
        }
    };

    /**
     * Fetch full chart intelligence from REST API
     */
    mod.loadChart = async function (forceRefresh = false) {
        const loadingEl = document.getElementById('commChartLoading');
        const refreshBtn = document.getElementById('commRefreshBtn');

        if (loadingEl && !mod._chartData) loadingEl.style.display = 'flex';
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<span>⏳</span> Loading...';
        }

        try {
            const url = `/api/v1/commodities/chart-intelligence?symbol=${encodeURIComponent(mod._symbol)}&interval=${encodeURIComponent(mod._timeframe)}&period=${encodeURIComponent(mod._period)}${forceRefresh ? '&force_refresh=true' : ''}`;
            const res = await fetch(url);
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }

            const data = await res.json();
            mod._chartData = data;

            // Compute average volume for hover surge metrics
            if (data.candles && data.candles.length > 0) {
                const vols = data.candles.map(c => c.volume || 0);
                const recent = vols.slice(-20);
                const sum = recent.reduce((a, b) => a + b, 0);
                mod._avgVolume = Math.max(Math.round(sum / Math.max(recent.length, 1)), 1);
            }

            // Render KPI cards & Tactical Trade HUD
            mod.renderTacticalHUD(data);

            // Render Lightweight Chart
            mod.initChartCanvas();
            mod.renderChart(data);

        } catch (err) {
            console.error('[COMMODITIES-MODULE] Error loading chart intelligence:', err);
        } finally {
            if (loadingEl) loadingEl.style.display = 'none';
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<span>🔄</span> Refresh';
            }
        }
    };

    /**
     * Fast Real-Time Incremental Tick Poller (3000ms)
     */
    mod.pollLatestTick = async function () {
        if (!mod._candleSeries || !mod._chart) return;
        try {
            const url = `/api/v1/commodities/latest-tick?symbol=${encodeURIComponent(mod._symbol)}&interval=${encodeURIComponent(mod._timeframe)}`;
            const res = await fetch(url);
            if (!res.ok) return;

            const data = await res.json();
            if (!data.success || !data.latest_candle) return;

            const candle = data.latest_candle;
            const curr = data.currency_symbol || '$';

            // Incremental Candle & Volume Update
            mod._candleSeries.update(candle);
            if (mod._volumeSeries) {
                mod._volumeSeries.update({
                    time: candle.time,
                    value: candle.volume,
                    color: candle.close >= candle.open ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)',
                });
            }

            // Update Spot price and change HUD
            const spotEl = document.getElementById('commKpiSpotPrice');
            const spotChangeEl = document.getElementById('commKpiSpotChange');
            const timeEl = document.getElementById('commChartTimestamp');

            if (spotEl) spotEl.textContent = `${curr}${candle.close.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (spotChangeEl) {
                const chg = data.change_24h || 0;
                const sign = chg >= 0 ? '+' : '';
                spotChangeEl.textContent = `24h: ${sign}${chg}%`;
                spotChangeEl.style.color = chg >= 0 ? '#10b981' : '#f43f5e';
            }
            if (timeEl && data.timestamp) {
                timeEl.textContent = `As of ${data.timestamp}`;
            }

        } catch (e) {
            // Quiet tick error
        }
    };

    /**
     * Initialize Lightweight Charts instance
     */
    mod.initChartCanvas = function () {
        const container = document.getElementById('commoditiesChartCanvas');
        if (!container || !window.LightweightCharts) return;

        if (!mod._chart) {
            mod._chart = window.LightweightCharts.createChart(container, {
                width: container.clientWidth || 800,
                height: 640,
                layout: {
                    background: { type: 'solid', color: '#050505' },
                    textColor: '#94a3b8',
                    fontSize: 11,
                    fontFamily: "var(--font-mono, monospace)",
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
                },
                crosshair: {
                    mode: window.LightweightCharts.CrosshairMode.Normal,
                    vertLine: { color: 'rgba(234, 179, 8, 0.4)', width: 1, style: 2 },
                    horzLine: { color: 'rgba(234, 179, 8, 0.4)', width: 1, style: 2 },
                },
                rightPriceScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    autoScale: true,
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    timeVisible: true,
                    secondsVisible: false,
                },
            });

            window.addEventListener('resize', () => {
                if (mod._chart && container) {
                    const h = mod._isFullscreen ? Math.max(window.innerHeight - 120, 400) : 640;
                    mod._chart.applyOptions({ width: container.clientWidth, height: h });
                }
            });

            if (!mod._escListenerBound) {
                document.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape' && mod._isFullscreen) {
                        mod.toggleFullscreen();
                    }
                });
                mod._escListenerBound = true;
            }

            // Crosshair Hover Inspector Hook
            if (!mod._crosshairBound) {
                mod._chart.subscribeCrosshairMove(mod.handleCrosshairMove);
                mod._crosshairBound = true;
            }
        }
    };

    /**
     * Crosshair move handler for Sticky Hover Inspector Bar
     */
    mod.handleCrosshairMove = function (param) {
        const timeEl = document.getElementById('commInspTime');
        const oEl = document.getElementById('commInspO');
        const hEl = document.getElementById('commInspH');
        const lEl = document.getElementById('commInspL');
        const cEl = document.getElementById('commInspC');
        const trEl = document.getElementById('commInspTr');
        const volSurgeEl = document.getElementById('commInspVolSurge');
        const wickDeltaEl = document.getElementById('commInspWickDelta');
        const smcDetailsEl = document.getElementById('commInspSmcDetails');
        const smcZoneEl = document.getElementById('commInspSmcZone');

        if (!param || !param.time || !param.seriesData || !mod._candleSeries) {
            return;
        }

        const candle = param.seriesData.get(mod._candleSeries);
        if (!candle) return;

        const curr = mod._chartData?.currency_symbol || '$';
        const o = Number(candle.open || 0);
        const h = Number(candle.high || 0);
        const l = Number(candle.low || 0);
        const c = Number(candle.close || 0);
        const tr = Math.max(h - l, 0.01);

        if (timeEl) {
            const d = new Date(param.time * 1000);
            timeEl.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
        }
        if (oEl) oEl.textContent = `${curr}${o.toFixed(2)}`;
        if (hEl) hEl.textContent = `${curr}${h.toFixed(2)}`;
        if (lEl) lEl.textContent = `${curr}${l.toFixed(2)}`;
        if (cEl) cEl.textContent = `${curr}${c.toFixed(2)}`;
        if (trEl) trEl.textContent = `${curr}${tr.toFixed(2)}`;

        // Volume surge multiple
        const volData = param.seriesData.get(mod._volumeSeries);
        const v = volData ? Number(volData.value || 0) : Number(candle.volume || 0);
        const avgVol = mod._avgVolume || 1;
        const volRatio = (v / avgVol).toFixed(1);

        if (volSurgeEl) {
            volSurgeEl.textContent = `Vol: ${v ? v.toLocaleString() : '--'} (${volRatio}x avg)`;
            if (Number(volRatio) >= 2.0) {
                volSurgeEl.style.background = 'rgba(16, 185, 129, 0.25)';
                volSurgeEl.style.color = '#10b981';
            } else if (Number(volRatio) >= 1.2) {
                volSurgeEl.style.background = 'rgba(56, 189, 248, 0.2)';
                volSurgeEl.style.color = '#38bdf8';
            } else {
                volSurgeEl.style.background = 'rgba(255, 255, 255, 0.08)';
                volSurgeEl.style.color = '#ededed';
            }
        }

        // Wick Delta (Buyer Absorb vs Seller Reject)
        const upperWick = Math.max(0, h - Math.max(o, c));
        const lowerWick = Math.max(0, Math.min(o, c) - l);
        const wickDelta = (lowerWick - upperWick).toFixed(2);
        if (wickDeltaEl) {
            if (lowerWick > upperWick) {
                wickDeltaEl.innerHTML = `Delta: <span style="color:#10b981;font-weight:700;">+${curr}${wickDelta} (Buyer)</span>`;
            } else if (upperWick > lowerWick) {
                wickDeltaEl.innerHTML = `Delta: <span style="color:#f43f5e;font-weight:700;">-${curr}${Math.abs(Number(wickDelta)).toFixed(2)} (Seller)</span>`;
            } else {
                wickDeltaEl.innerHTML = `Delta: <span style="color:var(--text-secondary);">Balanced</span>`;
            }
        }

        // Check if cursor price is inside any Order Block or FVG
        const pPrice = c;
        let activeZone = null;
        const obs = mod._chartData?.indicators?.order_blocks || [];
        const fvgs = mod._chartData?.indicators?.fvgs || [];

        for (const ob of obs) {
            const minB = Math.min(ob.bottom, ob.top);
            const maxB = Math.max(ob.bottom, ob.top);
            if (pPrice >= minB && pPrice <= maxB) {
                activeZone = {
                    type: ob.type === 'BULLISH_OB' ? 'Demand OB (D-OB)' : 'Supply OB (S-OB)',
                    color: ob.type === 'BULLISH_OB' ? '#10b981' : '#f43f5e',
                    status: ob.status || (ob.mitigated ? 'MITIGATED' : 'UNMITIGATED'),
                    distPts: ob.distance_pts !== undefined ? ob.distance_pts : Math.abs(pPrice - ob.midpoint).toFixed(2),
                    top: ob.top,
                    bottom: ob.bottom,
                };
                break;
            }
        }

        if (!activeZone) {
            for (const fvg of fvgs) {
                const minF = Math.min(fvg.bottom, fvg.top);
                const maxF = Math.max(fvg.bottom, fvg.top);
                if (pPrice >= minF && pPrice <= maxF) {
                    activeZone = {
                        type: fvg.type === 'BULLISH_FVG' ? 'Bullish FVG' : 'Bearish FVG',
                        color: fvg.type === 'BULLISH_FVG' ? '#38bdf8' : '#f43f5e',
                        status: fvg.status || (fvg.mitigated ? 'MITIGATED' : 'UNFILLED'),
                        distPts: fvg.distance_pts !== undefined ? fvg.distance_pts : Math.abs(pPrice - fvg.midpoint).toFixed(2),
                        top: fvg.top,
                        bottom: fvg.bottom,
                    };
                    break;
                }
            }
        }

        if (smcDetailsEl && smcZoneEl) {
            if (activeZone) {
                smcZoneEl.style.borderColor = activeZone.color;
                smcZoneEl.style.background = activeZone.color === '#10b981' ? 'rgba(16, 185, 129, 0.15)' : (activeZone.color === '#38bdf8' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(244, 63, 94, 0.15)');
                smcZoneEl.style.color = activeZone.color;
                smcDetailsEl.innerHTML = `<strong>${activeZone.type}</strong> · [${curr}${activeZone.bottom} – ${curr}${activeZone.top}] · <span style="font-weight:700;">${activeZone.status}</span>`;
            } else {
                smcZoneEl.style.borderColor = 'rgba(234,179,8,0.25)';
                smcZoneEl.style.background = 'rgba(234,179,8,0.12)';
                smcZoneEl.style.color = '#eab308';
                smcDetailsEl.textContent = 'Cursor Active · Outside SMC Zones';
            }
        }
    };

    /**
     * Toggle chart card fullscreen mode
     */
    mod.toggleFullscreen = function () {
        const card = document.getElementById('commoditiesChartCard');
        const container = document.getElementById('commoditiesChartCanvas');
        const fsText = document.getElementById('commFsText');
        if (!card || !container) return;

        mod._isFullscreen = !mod._isFullscreen;

        if (mod._isFullscreen) {
            card.style.cssText = 'position: fixed; inset: 0; z-index: 99999; background: #09090b; width: 100vw; height: 100vh; padding: 1.25rem; box-sizing: border-box; overflow-y: auto; display: flex; flex-direction: column;';
            const fsHeight = Math.max(window.innerHeight - 120, 400);
            container.style.height = `${fsHeight}px`;
            container.style.minHeight = `${fsHeight}px`;
            if (fsText) fsText.textContent = 'Exit Fullscreen';
            if (mod._chart) {
                mod._chart.applyOptions({ width: container.clientWidth, height: fsHeight });
                mod._chart.timeScale().fitContent();
            }
        } else {
            card.style.cssText = '';
            container.style.height = '640px';
            container.style.minHeight = '640px';
            if (fsText) fsText.textContent = 'Fullscreen';
            if (mod._chart) {
                mod._chart.applyOptions({ width: container.clientWidth, height: 640 });
                mod._chart.timeScale().fitContent();
            }
        }
    };

    /**
     * Render Candlesticks and indicators onto chart
     */
    mod.renderChart = function (data) {
        if (!mod._chart || !data) return;

        const candles = data.candles || [];
        if (candles.length === 0) return;

        // 1. Candlestick Series
        if (!mod._candleSeries) {
            mod._candleSeries = mod._chart.addCandlestickSeries({
                upColor: '#10b981',
                downColor: '#f43f5e',
                borderUpColor: '#10b981',
                borderDownColor: '#f43f5e',
                wickUpColor: '#10b981',
                wickDownColor: '#f43f5e',
            });
        }
        mod._candleSeries.setData(candles);

        // 2. Volume Series
        if (!mod._volumeSeries) {
            mod._volumeSeries = mod._chart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: '',
                scaleMargins: { top: 0.82, bottom: 0 },
            });
        }
        const volData = candles.map(c => ({
            time: c.time,
            value: c.volume,
            color: c.close >= c.open ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)',
        }));
        mod._volumeSeries.setData(volData);

        // 3. Render Indicator Layers
        mod.renderChartLayers(data);

        // Fit Content on initial render or symbol switch
        if (!mod._hasFitted) {
            mod._chart.timeScale().fitContent();
            mod._hasFitted = true;
        }
    };

    /**
     * Render / Update Overlays (VWAP, ORB, Order Blocks, Pivots, Trendlines)
     */
    mod.renderChartLayers = function (data) {
        if (!mod._chart || !mod._candleSeries) return;

        const ind = data.indicators || {};

        // 1. Clear existing price lines & trendlines
        mod._priceLines.forEach(line => {
            try { mod._candleSeries.removePriceLine(line); } catch (e) {}
        });
        mod._priceLines = [];

        mod._trendlineSeries.forEach(ts => {
            try { mod._chart.removeSeries(ts); } catch (e) {}
        });
        mod._trendlineSeries = [];

        // 2. VWAP Series
        if (mod._layers.vwap && ind.vwap && ind.vwap.length > 0) {
            if (!mod._vwapSeries) {
                mod._vwapSeries = mod._chart.addLineSeries({
                    color: '#38bdf8',
                    lineWidth: 2,
                    title: 'VWAP',
                    priceLineVisible: false,
                });
            }
            mod._vwapSeries.setData(ind.vwap);

            if (!mod._vwapUpperSeries) {
                mod._vwapUpperSeries = mod._chart.addLineSeries({
                    color: 'rgba(56, 189, 248, 0.4)',
                    lineWidth: 1,
                    lineStyle: 2,
                    priceLineVisible: false,
                });
            }
            mod._vwapUpperSeries.setData(ind.vwap_upper || []);

            if (!mod._vwapLowerSeries) {
                mod._vwapLowerSeries = mod._chart.addLineSeries({
                    color: 'rgba(56, 189, 248, 0.4)',
                    lineWidth: 1,
                    lineStyle: 2,
                    priceLineVisible: false,
                });
            }
            mod._vwapLowerSeries.setData(ind.vwap_lower || []);
        } else {
            if (mod._vwapSeries) mod._vwapSeries.setData([]);
            if (mod._vwapUpperSeries) mod._vwapUpperSeries.setData([]);
            if (mod._vwapLowerSeries) mod._vwapLowerSeries.setData([]);
        }

        // 3. ORB-15 Price Lines
        if (mod._layers.orb && ind.orb && ind.orb.active) {
            const orbHigh = mod._candleSeries.createPriceLine({
                price: ind.orb.high,
                color: '#a855f7',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'ORB High',
            });
            const orbLow = mod._candleSeries.createPriceLine({
                price: ind.orb.low,
                color: '#a855f7',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'ORB Low',
            });
            mod._priceLines.push(orbHigh, orbLow);
        }

        // 4. Classical Floor Pivots
        if (mod._layers.pivots && ind.pivots && ind.pivots.p > 0) {
            const pLine = mod._candleSeries.createPriceLine({
                price: ind.pivots.p,
                color: '#fbbf24',
                lineWidth: 1,
                lineStyle: 1,
                axisLabelVisible: true,
                title: 'Pivot (P)',
            });
            const r1Line = mod._candleSeries.createPriceLine({
                price: ind.pivots.r1,
                color: '#f43f5e',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'R1',
            });
            const s1Line = mod._candleSeries.createPriceLine({
                price: ind.pivots.s1,
                color: '#10b981',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'S1',
            });
            mod._priceLines.push(pLine, r1Line, s1Line);
        }

        // 5. Order Blocks (Markers on Candlesticks)
        if (mod._layers.ob && ind.order_blocks && ind.order_blocks.length > 0) {
            const markers = ind.order_blocks.map(ob => ({
                time: ob.time,
                position: ob.type === 'BULLISH_OB' ? 'belowBar' : 'aboveBar',
                color: ob.type === 'BULLISH_OB' ? '#10b981' : '#f43f5e',
                shape: ob.type === 'BULLISH_OB' ? 'arrowUp' : 'arrowDown',
                text: `${ob.short_label || (ob.type === 'BULLISH_OB' ? 'D-OB' : 'S-OB')} (${ob.status || 'UNMIT'})`,
            }));
            mod._candleSeries.setMarkers(markers);
        } else {
            mod._candleSeries.setMarkers([]);
        }

        // 6. Trendlines
        if (mod._layers.trendlines && ind.trendlines && ind.trendlines.length > 0) {
            ind.trendlines.forEach(tl => {
                const ts = mod._chart.addLineSeries({
                    color: tl.type === 'SUPPORT' ? '#10b981' : '#f43f5e',
                    lineWidth: 1,
                    lineStyle: 2,
                    priceLineVisible: false,
                    lastValueVisible: false,
                });
                ts.setData([
                    { time: tl.point1.time, value: tl.point1.price },
                    { time: tl.point2.time, value: tl.point2.price },
                ]);
                mod._trendlineSeries.push(ts);
            });
        }
    };

    /**
     * Render KPI cards and 3-column Tactical Trade HUD Deck
     */
    mod.renderTacticalHUD = function (data) {
        if (!data) return;

        const curr = data.currency_symbol || '$';

        // 1. Header & Title
        const titleEl = document.getElementById('commChartSymbolTitle');
        const timeEl = document.getElementById('commChartTimestamp');
        if (titleEl) titleEl.textContent = `${data.icon || '🥇'} ${data.name || data.symbol}`;
        if (timeEl) timeEl.textContent = `As of ${data.timestamp || 'Live'}`;

        // 2. KPI Cards
        const spotEl = document.getElementById('commKpiSpotPrice');
        const spotChangeEl = document.getElementById('commKpiSpotChange');
        const gsrEl = document.getElementById('commKpiGsr');
        const vwapEl = document.getElementById('commKpiVwap');
        const vwapBandsEl = document.getElementById('commKpiVwapBands');
        const orbRangeEl = document.getElementById('commKpiOrbRange');
        const orbTargetsEl = document.getElementById('commKpiOrbTargets');
        const atrEl = document.getElementById('commKpiAtr');
        const pivotFloorEl = document.getElementById('commKpiPivotFloor');

        if (spotEl) spotEl.textContent = `${curr}${data.spot_price !== undefined && data.spot_price !== null ? data.spot_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (spotChangeEl) {
            const chg = data.change_24h || 0;
            const sign = chg >= 0 ? '+' : '';
            spotChangeEl.textContent = `24h: ${sign}${chg}%`;
            spotChangeEl.style.color = chg >= 0 ? '#10b981' : '#f43f5e';
        }

        if (gsrEl) gsrEl.textContent = data.gsr?.toFixed(1) || '84.5';

        const ind = data.indicators || {};
        if (vwapEl && ind.vwap && ind.vwap.length > 0) {
            const lastVwap = ind.vwap[ind.vwap.length - 1]?.value;
            vwapEl.textContent = `${curr}${lastVwap !== undefined && lastVwap !== null ? lastVwap.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        }
        if (vwapBandsEl && ind.vwap_upper && ind.vwap_lower) {
            const u = ind.vwap_upper[ind.vwap_upper.length - 1]?.value;
            const l = ind.vwap_lower[ind.vwap_lower.length - 1]?.value;
            if (u !== undefined && l !== undefined) {
                vwapBandsEl.textContent = `Bands: ${curr}${l.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} – ${curr}${u.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            }
        }

        if (orbRangeEl && ind.orb && ind.orb.active) {
            orbRangeEl.textContent = `${curr}${ind.orb.range !== undefined && ind.orb.range !== null ? ind.orb.range.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        }
        if (orbTargetsEl && ind.orb && ind.orb.active) {
            orbTargetsEl.textContent = `T1: ${curr}${ind.orb.target_long_1?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} | T2: ${curr}${ind.orb.target_long_2?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }

        if (atrEl && ind.pivots) {
            atrEl.textContent = `${curr}${ind.pivots.atr !== undefined && ind.pivots.atr !== null ? ind.pivots.atr.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        }
        if (pivotFloorEl && ind.pivots) {
            pivotFloorEl.textContent = `Pivot: ${curr}${ind.pivots.p !== undefined && ind.pivots.p !== null ? ind.pivots.p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        }

        // Microstructure depth
        const micro = data.microstructure || {};
        const buyDepthEl = document.getElementById('commKpiBuyDepth');
        const sellDepthEl = document.getElementById('commKpiSellDepth');
        const cvdBiasEl = document.getElementById('commKpiCvdBias');

        if (buyDepthEl && micro.buy_depth_pct !== undefined) {
            buyDepthEl.textContent = `${micro.buy_depth_pct}%`;
        }
        if (sellDepthEl && micro.sell_depth_pct !== undefined) {
            sellDepthEl.textContent = `${micro.sell_depth_pct}%`;
        }
        if (cvdBiasEl) {
            const biasLabel = micro.cvd_bias ? micro.cvd_bias.replace(/_/g, ' ') : 'Balanced';
            const spread = micro.spread_bps !== undefined ? `${micro.spread_bps} bps` : '--';
            cvdBiasEl.textContent = `CVD: ${biasLabel} · Spread: ${spread}`;
        }

        // 3. 3-Column Tactical Trade HUD Deck
        const hud = data.tactical_hud || {};
        const buy = hud.where_to_buy || {};
        const sell = hud.where_to_sell || {};

        const buyEntryEl = document.getElementById('commBuyEntry');
        const buySlEl = document.getElementById('commBuySl');
        const buyT1El = document.getElementById('commBuyT1');
        const buyT2El = document.getElementById('commBuyT2');
        const buyRrBadge = document.getElementById('commBuyRrBadge');
        const buyRationaleEl = document.getElementById('commBuyRationale');

        if (buyEntryEl) buyEntryEl.textContent = buy.entry_zone || '--';
        if (buySlEl) buySlEl.textContent = `${curr}${buy.stop_loss !== undefined && buy.stop_loss !== null ? buy.stop_loss.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (buyT1El) buyT1El.textContent = `${curr}${buy.target_1 !== undefined && buy.target_1 !== null ? buy.target_1.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (buyT2El) buyT2El.textContent = `${curr}${buy.target_2 !== undefined && buy.target_2 !== null ? buy.target_2.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (buyRrBadge) buyRrBadge.textContent = `R:R ${buy.rr_ratio || 2.0}`;
        if (buyRationaleEl && buy.rationale) buyRationaleEl.textContent = buy.rationale;

        const sellEntryEl = document.getElementById('commSellEntry');
        const sellSlEl = document.getElementById('commSellSl');
        const sellT1El = document.getElementById('commSellT1');
        const sellT2El = document.getElementById('commSellT2');
        const sellRrBadge = document.getElementById('commSellRrBadge');
        const sellRationaleEl = document.getElementById('commSellRationale');

        if (sellEntryEl) sellEntryEl.textContent = sell.entry_zone || '--';
        if (sellSlEl) sellSlEl.textContent = `${curr}${sell.stop_loss !== undefined && sell.stop_loss !== null ? sell.stop_loss.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (sellT1El) sellT1El.textContent = `${curr}${sell.target_1 !== undefined && sell.target_1 !== null ? sell.target_1.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (sellT2El) sellT2El.textContent = `${curr}${sell.target_2 !== undefined && sell.target_2 !== null ? sell.target_2.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (sellRrBadge) sellRrBadge.textContent = `R:R ${sell.rr_ratio || 2.0}`;
        if (sellRationaleEl && sell.rationale) sellRationaleEl.textContent = sell.rationale;

        // Market Regime & Momentum
        const regimeTag = document.getElementById('commRegimeTag');
        const momentumBias = document.getElementById('commMomentumBias');
        const regimeBadge = document.getElementById('commRegimeBadge');

        if (regimeTag) regimeTag.textContent = hud.regime || 'NEUTRAL';
        if (momentumBias) momentumBias.textContent = hud.momentum_bias?.replace(/_/g, ' ') || 'NEUTRAL';
        if (regimeBadge) {
            regimeBadge.style.display = 'inline-block';
            regimeBadge.textContent = hud.regime || 'ACTIVE';
            if (hud.regime?.includes('BULLISH')) {
                regimeBadge.style.background = 'rgba(16, 185, 129, 0.2)';
                regimeBadge.style.color = '#10b981';
                regimeBadge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
            } else if (hud.regime?.includes('BEARISH')) {
                regimeBadge.style.background = 'rgba(244, 63, 94, 0.2)';
                regimeBadge.style.color = '#f43f5e';
                regimeBadge.style.borderColor = 'rgba(244, 63, 94, 0.35)';
            } else {
                regimeBadge.style.background = 'rgba(234, 179, 8, 0.2)';
                regimeBadge.style.color = '#eab308';
                regimeBadge.style.borderColor = 'rgba(234, 179, 8, 0.35)';
            }
        }
    };

})(window);
