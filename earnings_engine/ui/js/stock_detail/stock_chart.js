/**
 * Nexus Intelligence Platform — Stock Drilldown Technical Chart Engine
 * High-Density Lightweight Charts canvas matching Options Hub / Futures Chart.
 * Includes Multi-Timeframe (1m, 5m, 15m, 1h, 1D), Session VWAP ±1.5σ Bands,
 * Volume Surges, Crosshair HUD, SMC Order Blocks (OB/FVG), Derivatives Rays,
 * and Tactical "Where to Buy & Where to Sell" Operational HUD Deck.
 */

(function () {
    'use strict';

    window.app = window.app || {};
    const app = window.app;
    const State = window.StockDetailState;

    let _smartChart = null;
    let _candleSeries = null;
    let _volumeSeries = null;
    let _vwapSeries = null;
    let _vwapUpperSeries = null;
    let _vwapLowerSeries = null;
    let _chartPriceLines = [];
    let _trendlineSeries = [];
    let _smartChartData = null;
    let _avgVolume = 1;
    let _hasInitialChartFitted = false;
    let _chartTimer = null;
    let _isLoadingMore = false;
    let _hasMoreHistory = true;
    let _rangeDebounceTimer = null;
    let _isProgrammaticRangeChange = false;

    let _optionsTimeframe = '5m';
    let _optionsLayers = {
        vwap: true,
        ob: true,
        derivatives: true,
        orb: true,
        trendlines: true,
    };

    function getCleanSymbol() {
        if (State && State.cleanTicker) return State.cleanTicker;
        if (State && State.ticker) return State.ticker.replace('.NS', '').replace('.BO', '').trim().toUpperCase();
        const pathParts = window.location.pathname.split('/');
        const lastPart = pathParts[pathParts.length - 1] || '';
        return lastPart.replace('.NS', '').replace('.BO', '').trim().toUpperCase() || 'NIFTY';
    }

    /**
     * Switch timeframe interval (1m, 5m, 15m, 1h, 1d)
     */
    app.setOptionTimeframe = function (tf) {
        if (!tf) return;
        _optionsTimeframe = tf;
        _hasInitialChartFitted = false;
        _hasMoreHistory = true;
        _isLoadingMore = false;

        document.querySelectorAll('.opt-tf-btn').forEach(btn => {
            const isActive = btn.getAttribute('data-tf') === tf;
            btn.classList.toggle('active', isActive);
            btn.style.background = isActive ? '#38bdf8' : 'transparent';
            btn.style.color = isActive ? '#000000' : '#94a3b8';
        });

        loadStockChartData(false, false);
    };
    window.setOptionTimeframe = app.setOptionTimeframe;

    /**
     * Layer visibility toggle for smart chart
     */
    app.toggleOptionLayer = function (layer) {
        if (!(layer in _optionsLayers)) return;
        _optionsLayers[layer] = !_optionsLayers[layer];

        const btnIdMap = {
            vwap: 'optToggleVwap',
            ob: 'optToggleOb',
            derivatives: 'optToggleDeriv',
            orb: 'optToggleOrb',
            trendlines: 'optToggleTrendlines',
        };

        const btn = document.getElementById(btnIdMap[layer]);
        if (btn) {
            const active = _optionsLayers[layer];
            btn.classList.toggle('active', active);
            btn.style.opacity = active ? '1' : '0.4';
        }

        if (_smartChartData) {
            renderSmartChart(_smartChartData, true);
        }
    };
    window.toggleOptionLayer = app.toggleOptionLayer;

    /**
     * Toggle Fullscreen Mode for the Tactical Smart Chart & HUD Deck
     */
    app.toggleOptionChartFullscreen = function () {
        const card = document.getElementById('optionsSmartChartCard');
        const btnText = document.getElementById('optFullscreenText');
        const btnIcon = document.getElementById('optFullscreenIcon');
        const btn = document.getElementById('optFullscreenBtn');
        if (!card) return;

        const isFullscreen = card.classList.toggle('opt-chart-fullscreen-mode');
        document.body.style.overflow = isFullscreen ? 'hidden' : '';

        if (btnText) btnText.textContent = isFullscreen ? 'Exit Full Screen' : 'Full Screen';
        if (btnIcon) btnIcon.textContent = isFullscreen ? '✕' : '⛶';
        if (btn) {
            btn.style.background = isFullscreen ? '#ef4444' : 'rgba(255,255,255,0.06)';
            btn.style.color = isFullscreen ? '#ffffff' : '#e2e8f0';
            btn.style.borderColor = isFullscreen ? '#ef4444' : 'rgba(255,255,255,0.15)';
        }

        const resizeChart = () => {
            const container = document.getElementById('optionsSmartChartCanvas') || document.getElementById('stockChartCanvas');
            if (container && _smartChart) {
                let range = null;
                try {
                    range = _smartChart.timeScale().getVisibleLogicalRange();
                } catch (e) {}

                _smartChart.applyOptions({
                    width: container.clientWidth || 800,
                    height: container.clientHeight || 560,
                });

                if (range) {
                    try {
                        _smartChart.timeScale().setVisibleLogicalRange(range);
                    } catch (e) {}
                }
            }
        };

        resizeChart();
        setTimeout(resizeChart, 100);
        setTimeout(resizeChart, 300);
    };
    window.toggleOptionChartFullscreen = app.toggleOptionChartFullscreen;

    // Global listener for Escape key to exit fullscreen
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const card = document.getElementById('optionsSmartChartCard');
            if (card && card.classList.contains('opt-chart-fullscreen-mode')) {
                app.toggleOptionChartFullscreen();
            }
        }
    });

    /**
     * Initialize the Advanced Lightweight Charts Canvas
     */
    window.initStockChart = function () {
        const container = document.getElementById('optionsSmartChartCanvas') || document.getElementById('stockChartCanvas');
        if (!container || !window.LightweightCharts) return;

        if (_smartChart) {
            try {
                _smartChart.remove();
            } catch (e) {
                console.debug('Error disposing previous chart instance:', e);
            }
            _smartChart = null;
        }

        const chart = window.LightweightCharts.createChart(container, {
            width: container.clientWidth || 800,
            height: container.clientHeight || 560,
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
                mode: window.LightweightCharts.CrosshairMode.Normal,
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
                timeFormatter: (time) => window.formatIST(time, { includeTime: true, includeYear: true, suffix: true }),
                dateFormatter: (time) => window.formatIST(time, { includeTime: false, includeYear: true, suffix: true }),
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
                timeVisible: true,
                secondsVisible: false,
                tickMarkFormatter: (time) => {
                    return window.formatIST(time, { includeTime: true, includeYear: false, suffix: true });
                },
            },
        });

        // 1. Candlestick series
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#10b981',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#10b981',
            wickDownColor: '#ef4444',
        });

        // 2. Volume sub-series
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: '', // overlay
            scaleMargins: { top: 0.82, bottom: 0 },
        });

        // 3. VWAP line series
        const vwapSeries = chart.addLineSeries({
            color: '#38bdf8',
            lineWidth: 2,
            title: 'VWAP',
        });

        // 4. VWAP Upper Band
        const vwapUpperSeries = chart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.5)',
            lineWidth: 1,
            lineStyle: window.LightweightCharts.LineStyle.Dotted,
            title: 'VWAP +1.5σ',
        });

        // 5. VWAP Lower Band
        const vwapLowerSeries = chart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.5)',
            lineWidth: 1,
            lineStyle: window.LightweightCharts.LineStyle.Dotted,
            title: 'VWAP -1.5σ',
        });

        _smartChart = chart;
        _candleSeries = candleSeries;
        _volumeSeries = volumeSeries;
        _vwapSeries = vwapSeries;
        _vwapUpperSeries = vwapUpperSeries;
        _vwapLowerSeries = vwapLowerSeries;

        if (State) {
            State.chartInstance = chart;
        }

        // Subscribe to crosshair movement for Sticky Real-time Hover Inspector HUD
        chart.subscribeCrosshairMove(handleCrosshairMove);

        // Infinite scroll / pagination: dynamically load older candles when panning left
        chart.timeScale().subscribeVisibleLogicalRangeChange(onSmartChartVisibleLogicalRangeChange);

        // Responsive ResizeObserver
        const ro = new ResizeObserver(entries => {
            if (!entries || entries.length === 0 || !_smartChart) return;
            const { width, height } = entries[0].contentRect;
            if (width > 0 && height > 0) {
                _smartChart.applyOptions({ width, height });
            }
        });
        ro.observe(container);

        loadStockChartData(false, false);

        // Start auto-refresh interval (every 15s)
        if (_chartTimer) clearInterval(_chartTimer);
        _chartTimer = setInterval(() => {
            loadStockChartData(false, true);
        }, 15000);
    };

    /**
     * Crosshair move handler for Sticky Real-time Hover Inspector HUD bar
     */
    function handleCrosshairMove(param) {
        const inspectTime = document.getElementById('optInspectTime');
        const inspectOpen = document.getElementById('optInspectOpen');
        const inspectHigh = document.getElementById('optInspectHigh');
        const inspectLow = document.getElementById('optInspectLow');
        const inspectClose = document.getElementById('optInspectClose');
        const inspectTr = document.getElementById('optInspectTr');
        const inspectVol = document.getElementById('optInspectVol');
        const inspectDelta = document.getElementById('optInspectDelta');
        const inspectZoneDetails = document.getElementById('optInspectZoneDetails');
        const inspectZone = document.getElementById('optInspectZone');

        if (!inspectTime) return;

        let candle = null;
        let timeSec = null;

        if (param && param.time && _candleSeries && param.seriesData) {
            candle = param.seriesData.get(_candleSeries);
            timeSec = typeof param.time === 'number' ? param.time : (param.time.year ? new Date(Date.UTC(param.time.year, param.time.month - 1, param.time.day)).getTime() / 1000 : null);
        }

        // Fallback to latest candle if cursor left canvas
        if (!candle && _smartChartData && _smartChartData.candles && _smartChartData.candles.length > 0) {
            const candles = _smartChartData.candles;
            candle = candles[candles.length - 1];
            timeSec = candle.time;
        }

        if (!candle) {
            if (inspectTime) inspectTime.textContent = 'Cursor: --';
            return;
        }

        const timeStr = window.formatIST ? window.formatIST(timeSec || param.time || Date.now() / 1000, { includeTime: true, suffix: true }) : new Date((timeSec || Date.now() / 1000) * 1000).toLocaleString('en-IN');

        if (inspectTime) inspectTime.textContent = timeStr;
        if (inspectOpen) inspectOpen.textContent = `₹${candle.open !== undefined ? Number(candle.open).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (inspectHigh) inspectHigh.textContent = `₹${candle.high !== undefined ? Number(candle.high).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (inspectLow) inspectLow.textContent = `₹${candle.low !== undefined ? Number(candle.low).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (inspectClose) inspectClose.textContent = `₹${candle.close !== undefined ? Number(candle.close).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;

        const tr = Math.max((candle.high || 0) - (candle.low || 0), 0);
        if (inspectTr) inspectTr.textContent = `₹${tr.toFixed(2)}`;

        // Volume surge multiple
        const volItem = _volumeSeries && param.seriesData ? param.seriesData.get(_volumeSeries) : null;
        const v = volItem ? Number(volItem.value || 0) : Number(candle.volume || 0);
        const avgVol = _avgVolume || 1;
        const volRatio = (v / avgVol).toFixed(1);

        if (inspectVol) {
            const vFormatted = v >= 10000000 ? (v / 10000000).toFixed(2) + ' Cr' :
                               v >= 100000 ? (v / 100000).toFixed(2) + ' L' :
                               v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v;
            inspectVol.textContent = `Vol: ${v ? vFormatted : '--'} (${volRatio}x avg)`;
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

        // Zone intersection check (Derivatives Max Pain, Call/Put Walls, ORB, Order Blocks, FVGs)
        if (inspectZoneDetails && _smartChartData) {
            const data = _smartChartData;
            const deriv = data.derivatives_levels || {};
            const smartMoney = data.smart_money || {};
            const ind = data.indicators || {};
            let matchedZone = null;
            let zoneColor = '#eab308';

            let hoverPrice = candle.close;
            if (param.point && param.point.y !== undefined && _candleSeries.coordinateToPrice) {
                const p = _candleSeries.coordinateToPrice(param.point.y);
                if (p) hoverPrice = p;
            }

            // 1. Check Max Pain, Call Wall, Put Wall
            if (deriv.call_wall && Math.abs(hoverPrice - deriv.call_wall) <= (deriv.call_wall * 0.003)) {
                matchedZone = `Call Wall (Major Resistance) @ ₹${deriv.call_wall.toLocaleString()}`;
                zoneColor = '#f87171';
            } else if (deriv.put_wall && Math.abs(hoverPrice - deriv.put_wall) <= (deriv.put_wall * 0.003)) {
                matchedZone = `Put Wall (Major Support) @ ₹${deriv.put_wall.toLocaleString()}`;
                zoneColor = '#34d399';
            } else if (deriv.max_pain && Math.abs(hoverPrice - deriv.max_pain) <= (deriv.max_pain * 0.003)) {
                matchedZone = `Max Pain Strike @ ₹${deriv.max_pain.toLocaleString()}`;
                zoneColor = '#fbbf24';
            }

            // 2. Check Order Blocks
            if (!matchedZone && smartMoney.order_blocks) {
                for (const ob of smartMoney.order_blocks) {
                    const bMin = Math.min(ob.price_low || ob.bottom || 0, ob.price_high || ob.top || 0);
                    const bMax = Math.max(ob.price_low || ob.bottom || 0, ob.price_high || ob.top || 0);
                    if ((hoverPrice >= bMin && hoverPrice <= bMax) || param.time === ob.start_time) {
                        const tag = ob.type === 'BULLISH_OB' ? 'Demand Order Block (D-OB)' : 'Supply Order Block (S-OB)';
                        matchedZone = `${tag} @ ₹${bMin}–₹${bMax}`;
                        zoneColor = ob.type === 'BULLISH_OB' ? '#10b981' : '#f87171';
                        break;
                    }
                }
            }

            // 3. Check FVGs
            if (!matchedZone && smartMoney.fvg_gaps) {
                for (const fvg of smartMoney.fvg_gaps) {
                    const fMin = Math.min(fvg.low || fvg.bottom || 0, fvg.high || fvg.top || 0);
                    const fMax = Math.max(fvg.low || fvg.bottom || 0, fvg.high || fvg.top || 0);
                    if ((hoverPrice >= fMin && hoverPrice <= fMax) || param.time === fvg.time) {
                        matchedZone = `Fair Value Gap (${fvg.type || 'FVG'}) @ ₹${fMin}–₹${fMax}`;
                        zoneColor = '#38bdf8';
                        break;
                    }
                }
            }

            // 4. Check ORB-15 High / Low
            if (!matchedZone && ind.orb && ind.orb.active) {
                if (Math.abs(hoverPrice - ind.orb.high) <= (ind.orb.high * 0.002)) {
                    matchedZone = `15m ORB High Resistance @ ₹${ind.orb.high.toLocaleString()}`;
                    zoneColor = '#c084fc';
                } else if (Math.abs(hoverPrice - ind.orb.low) <= (ind.orb.low * 0.002)) {
                    matchedZone = `15m ORB Low Support @ ₹${ind.orb.low.toLocaleString()}`;
                    zoneColor = '#c084fc';
                }
            }

            if (matchedZone) {
                inspectZoneDetails.textContent = matchedZone;
                if (inspectZone) {
                    inspectZone.style.background = `${zoneColor}22`;
                    inspectZone.style.borderColor = `${zoneColor}55`;
                    inspectZone.style.color = zoneColor;
                }
            } else {
                inspectZoneDetails.textContent = `Hover over chart / SMC & Derivatives Key Levels`;
                if (inspectZone) {
                    inspectZone.style.background = 'rgba(234,179,8,0.12)';
                    inspectZone.style.borderColor = 'rgba(234,179,8,0.25)';
                    inspectZone.style.color = '#eab308';
                }
            }
        }
    }

    /**
     * Load full candlestick & quant intelligence from backend API
     */
    async function loadStockChartData(forceRefresh = false, isBackground = false) {
        const symbol = getCleanSymbol();
        const tf = _optionsTimeframe || '5m';
        const loadingEl = document.getElementById('optionsSmartChartLoading');
        const dot = document.getElementById('optLivePulseDot');
        const timeEl = document.getElementById('optChartTimestamp');

        if (loadingEl && !isBackground) {
            loadingEl.style.display = 'flex';
            loadingEl.style.pointerEvents = 'auto';
        }

        try {
            const url = `/api/v1/options/chart-intelligence?symbol=${encodeURIComponent(symbol)}&interval=${tf}&force_refresh=${forceRefresh}&allow_non_fno=true`;
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();

            // Non-destructive merge during 15s background auto-refresh: preserve older prepended candles
            if (isBackground && _smartChartData?.candles?.length > 0 && data.candles?.length > 0) {
                const existing = _smartChartData.candles;
                const firstIncomingTime = data.candles[0].time;
                const older = existing.filter(c => c.time < firstIncomingTime);
                if (older.length > 0) {
                    data.candles = older.concat(data.candles);
                }
            }

            _smartChartData = data;

            // Calculate average volume for surge metric
            if (data.candles && data.candles.length > 0) {
                const totalVol = data.candles.reduce((acc, c) => acc + (c.volume || 0), 0);
                _avgVolume = Math.max(totalVol / data.candles.length, 1);
            }

            if (timeEl) {
                const ts = data.timestamp ? (window.formatIST ? window.formatIST(data.timestamp, { includeTime: true, suffix: true }) : new Date(data.timestamp * 1000).toLocaleTimeString()) : (window.formatIST ? window.formatIST(Date.now() / 1000, { includeTime: true, suffix: true }) : new Date().toLocaleTimeString());
                timeEl.textContent = `As of ${ts}`;
            }

            // Render chart (preserving user zoom / pan if background update) & Tactical HUD
            renderSmartChart(data, isBackground);
            updateTacticalHUD(data);

            if (isBackground && dot) {
                dot.style.transform = 'scale(1.4)';
                setTimeout(() => { if (dot) dot.style.transform = 'scale(1)'; }, 350);
            }

        } catch (err) {
            console.error('Failed to load chart intelligence:', err);
        } finally {
            if (loadingEl && !isBackground) {
                loadingEl.style.display = 'none';
                loadingEl.style.pointerEvents = 'none';
            }
        }
    }
    window.loadStockChartData = loadStockChartData;

    /**
     * Dynamic scrollback handler: detect when user pans left near earliest candles
     */
    function onSmartChartVisibleLogicalRangeChange(newRange) {
        if (_isProgrammaticRangeChange || !newRange || _isLoadingMore || !_hasMoreHistory) return;
        if (newRange.from <= 8) {
            if (_rangeDebounceTimer) clearTimeout(_rangeDebounceTimer);
            _rangeDebounceTimer = setTimeout(() => {
                loadMoreSmartChartCandles();
            }, 120);
        }
    }

    /**
     * Fetch older candles and prepend to series while preserving viewport zoom & scroll position
     */
    async function loadMoreSmartChartCandles() {
        if (_isLoadingMore || !_hasMoreHistory || !_smartChartData || !_smartChartData.candles || _smartChartData.candles.length === 0) return;
        _isLoadingMore = true;

        const curCandles = _smartChartData.candles;
        const earliestCandle = curCandles[0];
        const earliestTime = earliestCandle.time;
        const symbol = getCleanSymbol();
        const tf = _optionsTimeframe || '5m';

        try {
            // For daily/weekly (>1D) timeframes, request up to 2 years (730 days) of history via stock-detail price-history
            const isDailyOrAbove = ['1d', '1w', '1mo'].includes(tf.toLowerCase());
            let olderCandles = [];

            if (isDailyOrAbove) {
                const lookbackMs = 730 * 24 * 60 * 60 * 1000;
                const startDateStr = new Date(Date.now() - lookbackMs).toISOString().split('T')[0];
                const url = `/api/v1/stock-detail/price-history?ticker=${encodeURIComponent(symbol)}&start_date=${startDateStr}`;
                const res = await fetch(url);
                if (res.ok) {
                    const json = await res.json();
                    const rawBars = json.data || [];
                    olderCandles = rawBars
                        .map(b => {
                            const t = typeof b.date === 'string' && b.date.includes('T')
                                ? Math.floor(new Date(b.date).getTime() / 1000)
                                : (typeof b.date === 'string' ? Math.floor(new Date(b.date + 'T00:00:00Z').getTime() / 1000) : b.date);
                            return {
                                time: t,
                                open: Number(b.open),
                                high: Number(b.high),
                                low: Number(b.low),
                                close: Number(b.close),
                                volume: Number(b.volume || 0),
                            };
                        })
                        .filter(c => c.time < earliestTime && !isNaN(c.close));
                }
            } else {
                // Intraday: query chart-intelligence with extended period (e.g. 60d)
                const url = `/api/v1/options/chart-intelligence?symbol=${encodeURIComponent(symbol)}&interval=${tf}&period=60d&allow_non_fno=true`;
                const res = await fetch(url);
                if (res.ok) {
                    const json = await res.json();
                    const rawCandles = json.candles || [];
                    olderCandles = rawCandles.filter(c => c.time < earliestTime);
                }
            }

            if (!olderCandles || olderCandles.length === 0) {
                _hasMoreHistory = false;
                return;
            }

            // Sort ascending by time and ensure uniqueness
            olderCandles.sort((a, b) => a.time - b.time);
            const seenTimes = new Set(curCandles.map(c => c.time));
            const deduplicatedOlder = olderCandles.filter(c => !seenTimes.has(c.time));

            if (deduplicatedOlder.length === 0) {
                _hasMoreHistory = false;
                return;
            }

            const mergedCandles = deduplicatedOlder.concat(curCandles);
            _smartChartData.candles = mergedCandles;

            // Capture current visible range before prepending
            let curRange = null;
            try {
                curRange = _smartChart.timeScale().getVisibleLogicalRange();
            } catch (e) {}

            // Update series data
            _candleSeries.setData(mergedCandles.map(c => ({
                time: c.time,
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close,
            })));

            if (_volumeSeries) {
                _volumeSeries.setData(mergedCandles.map(c => ({
                    time: c.time,
                    value: c.volume,
                    color: c.close >= c.open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
                })));
            }

            // Preserve user viewport zoom and pan position by compensating the logical index
            if (curRange && curRange.from !== null && curRange.to !== null) {
                const shift = deduplicatedOlder.length;
                _isProgrammaticRangeChange = true;
                try {
                    _smartChart.timeScale().setVisibleLogicalRange({
                        from: curRange.from + shift,
                        to: curRange.to + shift,
                    });
                } finally {
                    setTimeout(() => {
                        _isProgrammaticRangeChange = false;
                    }, 50);
                }
            }
        } catch (err) {
            console.error('[StockChart] Failed to load older candles:', err);
            _hasMoreHistory = false;
        } finally {
            _isLoadingMore = false;
        }
    }

    /**
     * Render Candlesticks, Indicators, Order Blocks & Structural Lines on Lightweight Chart
     */
    function renderSmartChart(data, isBackground = false) {
        if (!_smartChart) {
            window.initStockChart();
        }
        if (!_smartChart || !_candleSeries) return;

        // Capture user's current zoom / pan viewport range to prevent resets on auto-refresh
        let prevLogicalRange = null;
        try {
            if (_hasInitialChartFitted) {
                prevLogicalRange = _smartChart.timeScale().getVisibleLogicalRange();
            }
        } catch (e) {}

        const candles = data.candles || [];
        if (candles.length === 0) {
            _candleSeries.setData([]);
            if (_volumeSeries) _volumeSeries.setData([]);
            return;
        }

        // Set Candlestick data
        _candleSeries.setData(candles.map(c => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        })));

        // Set Volume data
        if (_volumeSeries) {
            _volumeSeries.setData(candles.map(c => ({
                time: c.time,
                value: c.volume,
                color: c.close >= c.open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
            })));
        }

        // Clear existing price lines & trendlines
        _chartPriceLines.forEach(line => {
            try {
                _candleSeries.removePriceLine(line);
            } catch (e) {}
        });
        _chartPriceLines = [];

        _trendlineSeries.forEach(s => {
            try {
                _smartChart.removeSeries(s);
            } catch (e) {}
        });
        _trendlineSeries = [];

        const indicators = data.indicators || {};
        const smartMoney = data.smart_money || {};
        const derivLevels = data.derivatives_levels || {};

        // 1. VWAP & Bands
        if (_optionsLayers.vwap && indicators.vwap && indicators.vwap.length > 0) {
            _vwapSeries.setData(indicators.vwap);
            _vwapUpperSeries.setData(indicators.vwap_upper_1 || []);
            _vwapLowerSeries.setData(indicators.vwap_lower_1 || []);
        } else {
            _vwapSeries.setData([]);
            _vwapUpperSeries.setData([]);
            _vwapLowerSeries.setData([]);
        }

        // 2. Derivatives Levels (Horizontal Lines)
        if (_optionsLayers.derivatives && derivLevels) {
            // Max Pain (Amber Dashed)
            if (derivLevels.max_pain) {
                const mpLine = _candleSeries.createPriceLine({
                    price: parseFloat(derivLevels.max_pain),
                    color: '#fbbf24',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `Max Pain: ₹${derivLevels.max_pain}`,
                });
                _chartPriceLines.push(mpLine);
            }

            // Call Wall / Major Resistance (Red Solid)
            if (derivLevels.call_wall) {
                const cwLine = _candleSeries.createPriceLine({
                    price: parseFloat(derivLevels.call_wall),
                    color: '#f87171',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: `Call Wall: ₹${derivLevels.call_wall}`,
                });
                _chartPriceLines.push(cwLine);
            }

            // Put Wall / Major Support (Green Solid)
            if (derivLevels.put_wall) {
                const pwLine = _candleSeries.createPriceLine({
                    price: parseFloat(derivLevels.put_wall),
                    color: '#34d399',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: `Put Wall: ₹${derivLevels.put_wall}`,
                });
                _chartPriceLines.push(pwLine);
            }
        }

        // 3. Opening Range Breakout (ORB-15) Range Lines
        if (_optionsLayers.orb && indicators.orb && indicators.orb.active) {
            const orbHigh = _candleSeries.createPriceLine({
                price: parseFloat(indicators.orb.high),
                color: '#c084fc',
                lineWidth: 1,
                lineStyle: window.LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: `ORB High: ₹${indicators.orb.high}`,
            });
            const orbLow = _candleSeries.createPriceLine({
                price: parseFloat(indicators.orb.low),
                color: '#c084fc',
                lineWidth: 1,
                lineStyle: window.LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: `ORB Low: ₹${indicators.orb.low}`,
            });
            _chartPriceLines.push(orbHigh, orbLow);
        }

        // 4. Smart Money Order Blocks (OB) & FVGs as Markers
        if (_optionsLayers.ob) {
            const markers = [];
            const obs = smartMoney.order_blocks || [];
            const fvgs = smartMoney.fvg_gaps || [];

            obs.forEach(ob => {
                const isBull = ob.type === 'BULLISH_OB';
                const tag = isBull ? 'D-OB' : 'S-OB';
                markers.push({
                    time: ob.start_time,
                    position: isBull ? 'belowBar' : 'aboveBar',
                    color: isBull ? '#10b981' : '#ef4444',
                    shape: isBull ? 'arrowUp' : 'arrowDown',
                    text: tag,
                    size: 1,
                });
            });

            fvgs.forEach(fvg => {
                markers.push({
                    time: fvg.time,
                    position: fvg.type === 'BULLISH_FVG' ? 'belowBar' : 'aboveBar',
                    color: fvg.type === 'BULLISH_FVG' ? '#38bdf8' : '#fb7185',
                    shape: 'circle',
                    text: 'FVG',
                    size: 1,
                });
            });

            markers.sort((a, b) => a.time - b.time);
            _candleSeries.setMarkers(markers);
        } else {
            _candleSeries.setMarkers([]);
        }

        // 5. Dynamic Support/Resistance Trendlines
        if (_optionsLayers.trendlines && smartMoney.trendlines) {
            smartMoney.trendlines.forEach(tl => {
                const s = _smartChart.addLineSeries({
                    color: tl.type === 'SUPPORT' ? '#34d399' : '#f87171',
                    lineWidth: 1,
                    lineStyle: window.LightweightCharts.LineStyle.Dashed,
                    title: tl.label || tl.type,
                });
                s.setData([
                    { time: tl.p1.time, value: tl.p1.price },
                    { time: tl.p2.time, value: tl.p2.price },
                ]);
                _trendlineSeries.push(s);
            });
        }

        // Restore viewport zoom & scroll position if already fitted; else fit initial
        if (_hasInitialChartFitted && prevLogicalRange && isBackground) {
            _isProgrammaticRangeChange = true;
            try {
                _smartChart.timeScale().setVisibleLogicalRange(prevLogicalRange);
            } catch (e) {
                _smartChart.timeScale().fitContent();
            } finally {
                setTimeout(() => {
                    _isProgrammaticRangeChange = false;
                }, 50);
            }
        } else if (!_hasInitialChartFitted) {
            _smartChart.timeScale().fitContent();
            _hasInitialChartFitted = true;
        }
    }

    /**
     * Update the Tactical "Where to Buy & Where to Sell" HUD Deck
     */
    function updateTacticalHUD(data) {
        const tactical = data.tactical_signals || {};
        const deriv = data.derivatives_levels || {};
        const ind = data.indicators || {};
        const orb = ind.orb || {};

        // Top Badges
        const regimeBadge = document.getElementById('optChartRegimeBadge');
        if (regimeBadge && tactical.regime) {
            regimeBadge.textContent = tactical.regime;
        }

        const confBadge = document.getElementById('optChartConfidenceBadge');
        if (confBadge && tactical.confidence_score) {
            confBadge.textContent = `${tactical.confidence_score}% Confluence`;
        }

        // 1. Where to Buy Setup
        const buy = tactical.where_to_buy || {};
        const buyEntryEl = document.getElementById('optBuyEntryZone');
        const buySLEl = document.getElementById('optBuyStopLoss');
        const buyT1El = document.getElementById('optBuyTarget1');
        const buyT2El = document.getElementById('optBuyTarget2');
        const buyRREl = document.getElementById('optBuyRRBadge');
        const buyTrigEl = document.getElementById('optBuyTriggerText');

        if (buyEntryEl) buyEntryEl.textContent = buy.entry_low ? `₹${buy.entry_low.toLocaleString()} – ₹${buy.entry_high.toLocaleString()}` : '--';
        if (buySLEl) buySLEl.textContent = buy.stop_loss ? `₹${buy.stop_loss.toLocaleString()}` : '--';
        if (buyT1El) buyT1El.textContent = buy.target_1 ? `₹${buy.target_1.toLocaleString()}` : '--';
        if (buyT2El) buyT2El.textContent = buy.target_2 ? `₹${buy.target_2.toLocaleString()}` : '--';
        if (buyRREl && buy.risk_reward) buyRREl.textContent = `R:R ${buy.risk_reward}`;
        if (buyTrigEl && buy.trigger) buyTrigEl.textContent = buy.trigger;

        // 2. Where to Sell Setup
        const sell = tactical.where_to_sell || {};
        const sellEntryEl = document.getElementById('optSellEntryZone');
        const sellSLEl = document.getElementById('optSellStopLoss');
        const sellT1El = document.getElementById('optSellTarget1');
        const sellT2El = document.getElementById('optSellTarget2');
        const sellRREl = document.getElementById('optSellRRBadge');
        const sellTrigEl = document.getElementById('optSellTriggerText');

        if (sellEntryEl) sellEntryEl.textContent = sell.entry_low ? `₹${sell.entry_low.toLocaleString()} – ₹${sell.entry_high.toLocaleString()}` : '--';
        if (sellSLEl) sellSLEl.textContent = sell.stop_loss ? `₹${sell.stop_loss.toLocaleString()}` : '--';
        if (sellT1El) sellT1El.textContent = sell.target_1 ? `₹${sell.target_1.toLocaleString()}` : '--';
        if (sellT2El) sellT2El.textContent = sell.target_2 ? `₹${sell.target_2.toLocaleString()}` : '--';
        if (sellRREl && sell.risk_reward) sellRREl.textContent = `R:R ${sell.risk_reward}`;
        if (sellTrigEl && sell.trigger) sellTrigEl.textContent = sell.trigger;
    }

})();
