/**
 * Commodities & Precious Metals Smart Chart Module
 *
 * Provides institutional TradingView Lightweight Charts canvas with:
 * - Real-time / intraday candlesticks for Gold, Silver, Crude Oil, Natural Gas, Copper
 * - Dynamic Session VWAP (±1.5σ dispersion bands)
 * - 15-minute Opening Range Breakout (ORB-15) and expansion targets
 * - Smart Money Concepts (SMC): Bullish (D-OB) and Bearish (S-OB) Order Blocks, Fair Value Gaps, and Liquidity Sweeps
 * - Algorithmic Support & Resistance Trendlines
 * - Interactive SMC Playbook educational drawer
 * - Sticky Crosshair Hover Inspector Bar (#commHoverInspectorCard)
 * - Microstructure Depth & Imbalance Widget
 * - Fast Real-Time Incremental Tick Engine (3000ms poller)
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
        fvg: true,
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
     * Universal IST (Indian Standard Time / Asia/Kolkata) Timestamp Formatter
     */
    function formatIST(timeVal, opts = {}) {
        if (timeVal === null || timeVal === undefined || timeVal === '') return '--';
        let ms;
        if (typeof timeVal === 'number') {
            ms = timeVal < 1e11 ? timeVal * 1000 : timeVal;
        } else if (typeof timeVal === 'string') {
            if (/^\d{4}-\d{2}-\d{2}$/.test(timeVal)) {
                const parts = timeVal.split('-').map(Number);
                const dt = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2], 10, 0, 0));
                return new Intl.DateTimeFormat('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    day: '2-digit',
                    month: 'short',
                    year: opts.includeYear ? 'numeric' : (opts.hideYear ? undefined : 'numeric'),
                }).format(dt);
            }
            ms = Date.parse(timeVal.includes('Z') || timeVal.includes('+') ? timeVal : timeVal + 'T00:00:00+05:30');
        } else if (timeVal instanceof Date) {
            ms = timeVal.getTime();
        } else if (typeof timeVal === 'object' && timeVal.year) {
            const dt = new Date(Date.UTC(timeVal.year, timeVal.month - 1, timeVal.day, 10, 0, 0));
            return new Intl.DateTimeFormat('en-IN', {
                timeZone: 'Asia/Kolkata',
                day: '2-digit',
                month: 'short',
                year: opts.includeYear ? 'numeric' : undefined,
            }).format(dt);
        } else {
            ms = Date.now();
        }

        if (isNaN(ms)) return String(timeVal);

        const d = new Date(ms);
        const formatConfig = {
            timeZone: 'Asia/Kolkata',
            day: '2-digit',
            month: 'short',
            hour12: false,
        };
        if (opts.includeYear) formatConfig.year = 'numeric';
        if (opts.includeTime !== false) {
            formatConfig.hour = '2-digit';
            formatConfig.minute = '2-digit';
            if (opts.includeSeconds) formatConfig.second = '2-digit';
        }

        const formatted = new Intl.DateTimeFormat('en-IN', formatConfig).format(d);
        return opts.suffix !== false ? `${formatted} IST` : formatted;
    }
    mod.formatIST = formatIST;

    /**
     * Check if commodities tab is active / visible in viewport
     */
    mod.isTabActive = function () {
        const tab = document.getElementById('tab-commodities');
        if (!tab) return false;
        return tab.style.display !== 'none' || tab.classList.contains('active') || window.location.hash === '#commodities';
    };

    /**
     * Initialize the module
     */
    mod.init = function () {
        mod.loadChart(false);

        // 1. 60s background structural intelligence refresh timer
        if (!mod._pollTimer) {
            mod._pollTimer = setInterval(() => {
                if (mod.isTabActive()) {
                    mod.loadChart(false, true); // preserve zoom on background refresh
                }
            }, 60000);
        }

        // 2. 3s lightweight incremental tick poller
        if (!mod._tickTimer) {
            mod._tickTimer = setInterval(() => {
                if (mod.isTabActive() && mod._chart && mod._candleSeries) {
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

        // Update pill UI
        document.querySelectorAll('.comm-asset-pill').forEach(pill => {
            if (pill.getAttribute('data-asset') === clean) {
                pill.classList.add('active');
                pill.style.background = 'var(--primary, #3b82f6)';
                pill.style.color = '#fff';
            } else {
                pill.classList.remove('active');
                pill.style.background = 'transparent';
                pill.style.color = 'var(--text-secondary, #94a3b8)';
            }
        });

        // Also sync dropdown if available
        const select = document.getElementById('commSymbolSelect');
        if (select) select.value = clean;

        mod.loadChart(true);
    };

    /**
     * Set chart timeframe interval (1m, 5m, 15m, 1h, 1d)
     */
    mod.setTimeframe = function (tf) {
        if (!tf || tf === mod._timeframe) return;
        mod._timeframe = tf;
        mod._hasFitted = false;

        document.querySelectorAll('.comm-tf-btn').forEach(btn => {
            if (btn.getAttribute('data-tf') === tf) {
                btn.classList.add('active');
                btn.style.background = 'var(--primary, #3b82f6)';
                btn.style.color = '#fff';
            } else {
                btn.classList.remove('active');
                btn.style.background = 'transparent';
                btn.style.color = 'var(--text-secondary, #94a3b8)';
            }
        });

        mod.loadChart(true);
    };

    /**
     * Set chart lookback period (1d, 5d, 1mo, 3mo, 1y)
     */
    mod.setPeriod = function (period) {
        if (!period || period === mod._period) return;
        mod._period = period;
        mod._hasFitted = false;

        document.querySelectorAll('.comm-period-btn').forEach(btn => {
            if (btn.getAttribute('data-period') === period) {
                btn.classList.add('active');
                btn.style.background = 'var(--primary, #3b82f6)';
                btn.style.color = '#fff';
            } else {
                btn.classList.remove('active');
                btn.style.background = 'transparent';
                btn.style.color = 'var(--text-secondary, #94a3b8)';
            }
        });

        mod.loadChart(true);
    };

    /**
     * Toggle layer visibility (vwap, orb, ob, fvg, pivots, trendlines)
     */
    mod.toggleLayer = function (layerName, isChecked) {
        mod._layers[layerName] = isChecked;
        if (mod._chartData) {
            mod.renderChartLayers(mod._chartData);
        }
    };

    /**
     * Load chart intelligence payload from backend
     */
    mod.loadChart = async function (forceRefresh = false, preserveZoom = false) {
        const loadingEl = document.getElementById('commChartLoading');
        const refreshBtn = document.getElementById('commRefreshBtn');

        if (!preserveZoom && loadingEl) loadingEl.style.display = 'flex';
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<span style="animation:spin 1s linear infinite;">⏳</span> Loading...';
        }

        try {
            const url = `/api/v1/commodities/chart-intelligence?symbol=${encodeURIComponent(mod._symbol)}&interval=${encodeURIComponent(mod._timeframe)}&period=${encodeURIComponent(mod._period)}${forceRefresh ? '&force_refresh=true' : ''}`;
            const res = await fetch(url);
            if (!res.ok) {
                throw new Error(`Failed to load commodities intelligence: ${res.statusText}`);
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

            // Render KPI cards, Microstructure widget & Tactical Trade HUD
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
     * Fast incremental tick poller (3s)
     */
    mod.pollLatestTick = async function () {
        if (!mod._candleSeries || !mod._chart) return;
        try {
            const url = `/api/v1/commodities/latest-tick?symbol=${encodeURIComponent(mod._symbol)}&interval=${encodeURIComponent(mod._timeframe)}`;
            const res = await fetch(url);
            if (!res.ok) return;

            const data = await res.json();
            if (data && data.success && data.latest_candle && mod._candleSeries) {
                const c = data.latest_candle;
                mod._candleSeries.update(c);

                if (mod._volumeSeries && c.volume !== undefined) {
                    mod._volumeSeries.update({
                        time: c.time,
                        value: c.volume,
                        color: c.close >= c.open ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)',
                    });
                }

                // Update real-time spot price & change HUD
                const curr = data.currency_symbol || '$';
                const spotEl = document.getElementById('commKpiSpotPrice');
                const spotChangeEl = document.getElementById('commKpiSpotChange');
                const timeEl = document.getElementById('commChartTimestamp');

                if (spotEl && data.spot_price !== undefined) {
                    spotEl.textContent = `${curr}${data.spot_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                }
                if (spotChangeEl && data.change_24h !== undefined) {
                    const chg = data.change_24h;
                    const sign = chg >= 0 ? '+' : '';
                    spotChangeEl.textContent = `24h: ${sign}${chg}%`;
                    spotChangeEl.style.color = chg >= 0 ? '#10b981' : '#f43f5e';
                }
                if (timeEl && data.timestamp) {
                    timeEl.textContent = `As of ${formatIST(data.timestamp, { includeTime: true, suffix: true })}`;
                }
            }
        } catch (e) {
            // Silently suppress background tick polling errors
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
                localization: {
                    locale: 'en-IN',
                    dateFormat: 'dd MMM yyyy',
                    timeFormatter: (time) => formatIST(time, { includeTime: true, suffix: true }),
                    dateFormatter: (time) => formatIST(time, { includeTime: false, includeYear: true, suffix: true }),
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    timeVisible: true,
                    secondsVisible: false,
                    tickMarkFormatter: (time, tickMarkType) => {
                        return formatIST(time, { includeTime: tickMarkType >= 3, includeYear: tickMarkType === 0, suffix: false });
                    },
                },
            });

            // Crosshair Movement Subscription for Sticky Hover Inspector
            if (!mod._crosshairBound) {
                mod._chart.subscribeCrosshairMove((param) => {
                    mod.handleCrosshairMove(param);
                });
                mod._crosshairBound = true;
            }

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
        }
    };

    /**
     * Crosshair move handler for Sticky Hover Inspector Bar
     */
    mod.handleCrosshairMove = function (param) {
        const inspectTime = document.getElementById('commInspectTime');
        const inspectOpen = document.getElementById('commInspectOpen');
        const inspectHigh = document.getElementById('commInspectHigh');
        const inspectLow = document.getElementById('commInspectLow');
        const inspectClose = document.getElementById('commInspectClose');
        const inspectTr = document.getElementById('commInspectTr');
        const inspectVol = document.getElementById('commInspectVol');
        const inspectDelta = document.getElementById('commInspectDelta');
        const inspectZoneDetails = document.getElementById('commInspectZoneDetails');
        const inspectZone = document.getElementById('commInspectZone');

        if (!param || !mod._candleSeries) return;

        let candle = null;
        let timeSec = param.time;

        if (param.seriesData) {
            candle = param.seriesData.get(mod._candleSeries);
        }

        // Fallback: If cursor is on Y-axis scale or hover point without time param
        if (!candle && mod._chartData && mod._chartData.candles && mod._chartData.candles.length > 0) {
            if (param.point && param.point.y !== undefined && mod._candleSeries.coordinateToPrice) {
                const hoverPrice = mod._candleSeries.coordinateToPrice(param.point.y);
                if (hoverPrice) {
                    candle = mod._chartData.candles.reduce((prev, curr) => {
                        return Math.abs(curr.close - hoverPrice) < Math.abs(prev.close - hoverPrice) ? curr : prev;
                    }, mod._chartData.candles[mod._chartData.candles.length - 1]);
                    timeSec = candle.time;
                }
            } else {
                candle = mod._chartData.candles[mod._chartData.candles.length - 1];
                timeSec = candle.time;
            }
        }

        if (!candle) return;

        const curr = mod._chartData?.currency_symbol || '$';
        const timeStr = formatIST(timeSec || param.time || Date.now() / 1000, { includeTime: true, suffix: true });

        if (inspectTime) inspectTime.textContent = timeStr;
        if (inspectOpen) inspectOpen.textContent = `${curr}${candle.open !== undefined ? candle.open.toFixed(2) : '--'}`;
        if (inspectHigh) inspectHigh.textContent = `${curr}${candle.high !== undefined ? candle.high.toFixed(2) : '--'}`;
        if (inspectLow) inspectLow.textContent = `${curr}${candle.low !== undefined ? candle.low.toFixed(2) : '--'}`;
        if (inspectClose) inspectClose.textContent = `${curr}${candle.close !== undefined ? candle.close.toFixed(2) : '--'}`;

        const tr = Math.max((candle.high || 0) - (candle.low || 0), 0);
        if (inspectTr) inspectTr.textContent = `${curr}${tr.toFixed(2)}`;

        // Volume surge multiple
        const volItem = mod._volumeSeries && param.seriesData ? param.seriesData.get(mod._volumeSeries) : null;
        const v = volItem ? Number(volItem.value || 0) : Number(candle.volume || 0);
        const avgVol = mod._avgVolume || 1;
        const volRatio = (v / avgVol).toFixed(1);

        if (inspectVol) {
            inspectVol.textContent = `Vol: ${v ? (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v) : '--'} (${volRatio}x avg)`;
            if (Number(volRatio) >= 2.0) {
                inspectVol.style.background = 'rgba(16, 185, 129, 0.25)';
                inspectVol.style.color = '#10b981';
            } else if (Number(volRatio) >= 1.2) {
                inspectVol.style.background = 'rgba(56, 189, 248, 0.2)';
                inspectVol.style.color = '#38bdf8';
            } else {
                inspectVol.style.background = 'rgba(255, 255, 255, 0.08)';
                inspectVol.style.color = '#ededed';
            }
        }

        // Wick Delta (Buyer Absorption vs Seller Rejection Pressure)
        if (inspectDelta && candle.high !== undefined && candle.low !== undefined) {
            const rng = Math.max(candle.high - candle.low, 0.001);
            const buyRatio = Math.round(((candle.close - candle.low) / rng) * 100);
            const sellRatio = 100 - buyRatio;
            inspectDelta.textContent = `Delta: ${buyRatio}% B / ${sellRatio}% S`;
            inspectDelta.style.color = buyRatio >= 50 ? '#10b981' : '#f43f5e';
            inspectDelta.style.background = buyRatio >= 50 ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)';
        }

        // Zone intersection check
        if (inspectZoneDetails && mod._chartData && mod._chartData.indicators) {
            const ind = mod._chartData.indicators;
            let matchedZone = null;
            let zoneColor = '#a855f7';

            let hoverPrice = candle.close;
            if (param.point && param.point.y !== undefined && mod._candleSeries.coordinateToPrice) {
                const p = mod._candleSeries.coordinateToPrice(param.point.y);
                if (p) hoverPrice = p;
            }

            // 1. Check Order Blocks
            const obs = ind.order_blocks || [];
            for (const ob of obs) {
                const bMin = Math.min(ob.bottom, ob.top);
                const bMax = Math.max(ob.bottom, ob.top);
                if ((hoverPrice >= bMin && hoverPrice <= bMax) || param.time === ob.time) {
                    matchedZone = `${ob.short_label || (ob.type === 'BULLISH_OB' ? 'D-OB' : 'S-OB')} @ ${curr}${ob.bottom}–${ob.top} (${ob.status || 'ACTIVE'} · ${ob.volume_surge || 1.0}x Vol · ${ob.distance_pts || 0} pts away)`;
                    zoneColor = ob.type === 'BULLISH_OB' ? '#10b981' : '#f43f5e';
                    break;
                }
            }

            // 2. Check FVGs
            if (!matchedZone) {
                const fvgs = ind.fvgs || [];
                for (const fvg of fvgs) {
                    const fMin = Math.min(fvg.bottom, fvg.top);
                    const fMax = Math.max(fvg.bottom, fvg.top);
                    if ((hoverPrice >= fMin && hoverPrice <= fMax) || param.time === fvg.time) {
                        matchedZone = `${fvg.type?.replace('_', ' ') || 'FVG'} @ ${curr}${fvg.bottom}–${fvg.top} (${fvg.status || 'UNFILLED'} · Mid: ${curr}${fvg.midpoint})`;
                        zoneColor = '#38bdf8';
                        break;
                    }
                }
            }

            // 3. Check Volume Profile POC & Value Area
            if (!matchedZone && ind.poc) {
                const poc = ind.poc;
                const vah = ind.vah;
                const val = ind.val;
                if (Math.abs(hoverPrice - poc) <= (poc * 0.002)) {
                    matchedZone = `Volume Profile POC @ ${curr}${poc.toFixed(2)}`;
                    zoneColor = '#eab308';
                } else if (vah && Math.abs(hoverPrice - vah) <= (vah * 0.002)) {
                    matchedZone = `Value Area High (VAH 70%) @ ${curr}${vah.toFixed(2)}`;
                    zoneColor = '#f59e0b';
                } else if (val && Math.abs(hoverPrice - val) <= (val * 0.002)) {
                    matchedZone = `Value Area Low (VAL 70%) @ ${curr}${val.toFixed(2)}`;
                    zoneColor = '#f59e0b';
                }
            }

            // 4. Check Liquidity Sweeps
            if (!matchedZone && ind.liquidity_sweeps && ind.liquidity_sweeps.length > 0) {
                for (const sw of ind.liquidity_sweeps) {
                    if (param.time === sw.time || Math.abs(hoverPrice - sw.level) <= (sw.level * 0.001)) {
                        matchedZone = `${sw.label || sw.type} @ ${curr}${sw.level} (Extreme: ${curr}${sw.sweep_extreme})`;
                        zoneColor = '#f43f5e';
                        break;
                    }
                }
            }

            if (matchedZone) {
                inspectZoneDetails.textContent = matchedZone;
                if (inspectZone) {
                    inspectZone.style.color = zoneColor;
                    inspectZone.style.borderColor = zoneColor;
                }
            } else {
                inspectZoneDetails.textContent = 'Free Flow / Fair Value Zone';
                if (inspectZone) {
                    inspectZone.style.color = '#eab308';
                    inspectZone.style.borderColor = 'rgba(234,179,8,0.25)';
                }
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

        // Only fitContent on first load or explicit asset/timeframe switch, NOT on background tick/price refreshes
        if (!mod._hasFitted) {
            try {
                mod._chart.priceScale('right').applyOptions({ autoScale: true });
            } catch (e) {}
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

        // 1. Clear existing price lines & trendlines and reset secondary indicator data
        mod._priceLines.forEach(line => {
            try { mod._candleSeries.removePriceLine(line); } catch (e) {}
        });
        mod._priceLines = [];

        mod._trendlineSeries.forEach(ts => {
            try { mod._chart.removeSeries(ts); } catch (e) {}
        });
        mod._trendlineSeries = [];

        if (mod._vwapSeries) mod._vwapSeries.setData([]);
        if (mod._vwapUpperSeries) mod._vwapUpperSeries.setData([]);
        if (mod._vwapLowerSeries) mod._vwapLowerSeries.setData([]);
        if (mod._candleSeries) mod._candleSeries.setMarkers([]);

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

        // 5. Order Blocks (D-OB / S-OB) & Fair Value Gaps (FVG)
        const markers = [];
        if (mod._layers.ob && ind.order_blocks && ind.order_blocks.length > 0) {
            ind.order_blocks.forEach(ob => {
                markers.push({
                    time: ob.time,
                    position: ob.type === 'BULLISH_OB' ? 'belowBar' : 'aboveBar',
                    color: ob.type === 'BULLISH_OB' ? '#10b981' : '#f43f5e',
                    shape: ob.type === 'BULLISH_OB' ? 'arrowUp' : 'arrowDown',
                    text: `${ob.short_label || (ob.type === 'BULLISH_OB' ? 'D-OB' : 'S-OB')} (${ob.status || 'UNMIT'})`,
                });
            });
        }
        if (mod._layers.fvg && ind.fvgs && ind.fvgs.length > 0) {
            ind.fvgs.forEach(fvg => {
                const isBull = fvg.type === 'BULLISH_FVG';
                markers.push({
                    time: fvg.time,
                    position: isBull ? 'belowBar' : 'aboveBar',
                    color: isBull ? '#38bdf8' : '#fb7185',
                    shape: 'circle',
                    text: isBull ? 'B-FVG' : 'S-FVG',
                });
            });
        }
        markers.sort((a, b) => a.time - b.time);
        mod._candleSeries.setMarkers(markers);

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
     * Render KPI cards, Microstructure widget, and 3-column Tactical Trade HUD Deck
     */
    mod.renderTacticalHUD = function (data) {
        if (!data) return;

        const curr = data.currency_symbol || '$';

        // 1. Header & Title
        const timelineBadge = document.getElementById('commTimelineBadge');
        if (timelineBadge) {
            const candleCount = (data.candles || []).length;
            timelineBadge.textContent = '📅 5D SMC Window (' + candleCount + ' bars)';
        }
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

        // 3. Microstructure Imbalance Widget
        const micro = ind.microstructure || data.microstructure || {};
        const buyDepthEl = document.getElementById('commKpiBuyDepth');
        const sellDepthEl = document.getElementById('commKpiSellDepth');
        const buyDepthBar = document.getElementById('commKpiBuyDepthBar');
        const cvdBadge = document.getElementById('commKpiCvdBadge');
        const spreadProxyEl = document.getElementById('commKpiSpreadProxy');

        const buyPct = micro.buy_depth_pct !== undefined ? micro.buy_depth_pct : (micro.resting_buy_depth_pct !== undefined ? micro.resting_buy_depth_pct : 50.0);
        const sellPct = micro.sell_depth_pct !== undefined ? micro.sell_depth_pct : (micro.resting_sell_depth_pct !== undefined ? micro.resting_sell_depth_pct : 50.0);

        if (buyDepthEl) buyDepthEl.textContent = `${buyPct}%`;
        if (sellDepthEl) sellDepthEl.textContent = `${sellPct}%`;
        if (buyDepthBar) buyDepthBar.style.width = `${buyPct}%`;

        if (cvdBadge) {
            const bias = micro.cvd_bias || 'NEUTRAL';
            cvdBadge.textContent = bias.replace(/_/g, ' ');
            if (bias.includes('BULLISH')) {
                cvdBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                cvdBadge.style.color = '#10b981';
            } else if (bias.includes('BEARISH')) {
                cvdBadge.style.background = 'rgba(244, 63, 94, 0.15)';
                cvdBadge.style.color = '#f43f5e';
            } else {
                cvdBadge.style.background = 'rgba(234, 179, 8, 0.15)';
                cvdBadge.style.color = '#eab308';
            }
        }

        if (spreadProxyEl) {
            const spreadText = micro.spread_bps !== undefined ? `${micro.spread_bps} bps` : (micro.spread_proxy !== undefined ? `~$${micro.spread_proxy}` : '~$0.05');
            spreadProxyEl.textContent = `Spread: ${spreadText}`;
        }

        // 4. 3-Column Tactical Trade HUD Deck
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
        const regimeSummary = document.getElementById('commRegimeSummary');
        const structureStatus = document.getElementById('commStructureStatus');

        if (regimeTag) regimeTag.textContent = hud.regime || 'NEUTRAL';
        if (momentumBias) momentumBias.textContent = hud.momentum_bias?.replace(/_/g, ' ') || 'NEUTRAL';
        if (regimeSummary) {
            const sym = data.name || data.symbol || 'Asset';
            const regText = (hud.regime || 'NEUTRAL').replace(/_/g, ' ');
            const momText = (hud.momentum_bias || 'CONSOLIDATION').replace(/_/g, ' ');
            regimeSummary.textContent = `${sym} trading in ${regText} with ${momText} momentum bias across VWAP slope and structural key levels.`;
        }
        if (structureStatus) {
            const indSweeps = (ind.liquidity_sweeps || []).length;
            const indObs = (ind.order_blocks || []).length;
            if (indSweeps > 0) {
                structureStatus.textContent = `Sweep Active (${indSweeps})`;
                structureStatus.style.color = '#f43f5e';
            } else if (indObs > 0) {
                structureStatus.textContent = `OB Defended (${indObs})`;
                structureStatus.style.color = '#10b981';
            } else {
                structureStatus.textContent = 'SMC Intact';
                structureStatus.style.color = '#a855f7';
            }
        }
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
