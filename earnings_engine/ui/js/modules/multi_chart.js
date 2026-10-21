// =========================================================================
// 📈 Interactive Multi-Chart Studio (TradingView Lightweight Charts v4.1.3)
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    function formatIST(val, opts = {}) {
        if (!val) return '—';
        try {
            let d;
            if (typeof val === 'number') {
                d = new Date(val > 1e11 ? val : val * 1000);
            } else if (typeof val === 'string') {
                if (val.includes('T')) {
                    d = new Date(val);
                } else if (/^\d{4}-\d{2}-\d{2}$/.test(val)) {
                    const [y, m, day] = val.split('-').map(Number);
                    d = new Date(Date.UTC(y, m - 1, day, 10, 0, 0));
                } else {
                    d = new Date(val);
                }
            } else if (val instanceof Date) {
                d = val;
            } else if (val && typeof val === 'object' && val.year) {
                d = new Date(Date.UTC(val.year, (val.month || 1) - 1, val.day || 1, 10, 0, 0));
            } else {
                return String(val);
            }

            if (isNaN(d.getTime())) return String(val);

            const timeParts = {
                timeZone: 'Asia/Kolkata',
                hour12: false,
            };

            if (opts.includeDate && opts.includeTime) {
                const dateStr = d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric' });
                const timeStr = d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false });
                return `${dateStr} ${timeStr}${opts.suffix ? ' IST' : ''}`;
            } else if (opts.includeTime) {
                const timeStr = d.toLocaleTimeString('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: opts.includeSeconds ? '2-digit' : undefined,
                    hour12: false
                });
                return `${timeStr}${opts.suffix ? ' IST' : ''}`;
            } else {
                return d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric' }) + (opts.suffix ? ' IST' : '');
            }
        } catch (e) {
            return String(val);
        }
    }
    app.formatIST = formatIST;

    app.multiChart = {
        layout: '1x1',
        syncCrosshair: true,
        instances: [null, null, null, null],
        candleSeries: [null, null, null, null],
        volumeSeries: [null, null, null, null],
        sma20Series: [null, null, null, null],
        sma50Series: [null, null, null, null],
        sma200Series: [null, null, null, null],
        vwapSeries: [null, null, null, null],
        vwapUpperSeries: [null, null, null, null],
        vwapLowerSeries: [null, null, null, null],
        tickers: ['TCS.NS', 'RELIANCE.NS', 'INFY.NS', 'HDFCBANK.NS'],
        timeframes: ['1D', '1D', '1D', '1D'],
        isSyncing: false,
        pollTimer: null,
    };

    function calculateSMA(data, period) {
        const result = [];
        for (let i = 0; i < data.length; i++) {
            if (i < period - 1) continue;
            let sum = 0;
            for (let j = 0; j < period; j++) {
                sum += data[i - j].close;
            }
            result.push({
                time: data[i].date || data[i].time,
                value: parseFloat((sum / period).toFixed(2)),
            });
        }
        return result;
    }

    function getThemeColors() {
        const isLight = document.body.classList.contains('light-mode') || document.documentElement.getAttribute('data-theme') === 'light';
        return {
            bg: isLight ? '#ffffff' : '#09090b',
            text: isLight ? '#0f172a' : '#cbd5e1',
            grid: isLight ? 'rgba(15, 23, 42, 0.06)' : 'rgba(255, 255, 255, 0.04)',
            border: isLight ? 'rgba(15, 23, 42, 0.12)' : 'rgba(255, 255, 255, 0.08)',
            upColor: '#10b981',
            downColor: '#ef4444',
            volumeUp: 'rgba(16, 185, 129, 0.35)',
            volumeDown: 'rgba(239, 68, 68, 0.35)',
        };
    }

    function initChartInstance(idx) {
        const container = document.getElementById(`chartContainer-${idx}`);
        if (!container || !window.LightweightCharts) return;

        if (app.multiChart.instances[idx]) {
            try {
                app.multiChart.instances[idx].remove();
            } catch (e) {
                console.debug("Error disposing chart", e);
            }
        }

        const colors = getThemeColors();
        const chart = window.LightweightCharts.createChart(container, {
            width: container.clientWidth || 400,
            height: container.clientHeight || 300,
            layout: {
                background: { type: 'solid', color: colors.bg },
                textColor: colors.text,
                fontSize: 11,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            },
            grid: {
                vertLines: { color: colors.grid },
                horzLines: { color: colors.grid },
            },
            crosshair: {
                mode: window.LightweightCharts.CrosshairMode.Normal,
                vertLine: {
                    color: 'rgba(234, 179, 8, 0.4)',
                    width: 1,
                    style: 1,
                },
                horzLine: {
                    color: 'rgba(234, 179, 8, 0.4)',
                    width: 1,
                    style: 1,
                },
            },
            localization: {
                dateFormat: 'yyyy-MM-dd',
                timeFormatter: (val) => formatIST(val, { includeDate: true, includeTime: true, suffix: true }),
                dateFormatter: (val) => formatIST(val, { includeDate: true, includeTime: false, suffix: true }),
            },
            rightPriceScale: {
                borderColor: colors.border,
                scaleMargins: { top: 0.1, bottom: 0.2 },
            },
            timeScale: {
                borderColor: colors.border,
                timeVisible: true,
                secondsVisible: false,
                tickMarkFormatter: (time, tickMarkType, locale) => {
                    return formatIST(time, { includeTime: false });
                },
            },
        });

        // Candlestick series
        const candleSeries = chart.addCandlestickSeries({
            upColor: colors.upColor,
            downColor: colors.downColor,
            borderVisible: false,
            wickUpColor: colors.upColor,
            wickDownColor: colors.downColor,
        });

        // Volume histogram series
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: '', // overlay
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        // Moving Average Overlays
        const sma20 = chart.addLineSeries({
            color: '#38bdf8',
            lineWidth: 1,
            title: 'SMA 20',
        });
        const sma50 = chart.addLineSeries({
            color: '#fbbf24',
            lineWidth: 1,
            title: 'SMA 50',
        });
        const sma200 = chart.addLineSeries({
            color: '#818cf8',
            lineWidth: 1.5,
            title: 'SMA 200',
        });

        // VWAP and Deviation Bands
        const vwap = chart.addLineSeries({
            color: '#f59e0b',
            lineWidth: 1.5,
            priceLineVisible: false,
            title: 'VWAP',
        });
        const vwapUpper = chart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.45)',
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            title: 'VWAP +1σ',
        });
        const vwapLower = chart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.45)',
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            title: 'VWAP -1σ',
        });

        app.multiChart.instances[idx] = chart;
        app.multiChart.candleSeries[idx] = candleSeries;
        app.multiChart.volumeSeries[idx] = volumeSeries;
        app.multiChart.sma20Series[idx] = sma20;
        app.multiChart.sma50Series[idx] = sma50;
        app.multiChart.sma200Series[idx] = sma200;
        app.multiChart.vwapSeries[idx] = vwap;
        app.multiChart.vwapUpperSeries[idx] = vwapUpper;
        app.multiChart.vwapLowerSeries[idx] = vwapLower;

        // ResizeObserver
        const ro = new ResizeObserver(entries => {
            if (!entries || entries.length === 0) return;
            const { width, height } = entries[0].contentRect;
            if (width > 0 && height > 0) {
                chart.applyOptions({ width, height });
            }
        });
        ro.observe(container);

        // Crosshair Sync Handler
        chart.subscribeCrosshairMove(param => {
            if (!app.multiChart.syncCrosshair || app.multiChart.isSyncing) return;
            if (!param.time) return;

            app.multiChart.isSyncing = true;
            for (let i = 0; i < 4; i++) {
                if (i !== idx && app.multiChart.instances[i]) {
                    // Sync visible range or hover
                    const targetChart = app.multiChart.instances[i];
                    try {
                        const targetSeries = app.multiChart.candleSeries[i];
                        if (targetSeries) {
                            // Sync logical range
                            const logicalRange = chart.timeScale().getVisibleLogicalRange();
                            if (logicalRange) {
                                targetChart.timeScale().setVisibleLogicalRange(logicalRange);
                            }
                        }
                    } catch (e) {
                        // ignore range sync errors
                    }
                }
            }
            app.multiChart.isSyncing = false;
        });

        // Load data
        loadPaneData(idx);
    }

    async function loadPaneData(idx, preserveRange = false) {
        const ticker = app.multiChart.tickers[idx] || 'TCS.NS';
        const tf = (app.multiChart.timeframes[idx] || '1D').toLowerCase();
        const isIntraday = tf === '5m' || tf === '15m' || tf === '1m';

        try {
            const candleSeries = app.multiChart.candleSeries[idx];
            const volumeSeries = app.multiChart.volumeSeries[idx];
            const sma20 = app.multiChart.sma20Series[idx];
            const sma50 = app.multiChart.sma50Series[idx];
            const sma200 = app.multiChart.sma200Series[idx];
            const vwap = app.multiChart.vwapSeries[idx];
            const vwapUpper = app.multiChart.vwapUpperSeries[idx];
            const vwapLower = app.multiChart.vwapLowerSeries[idx];

            let candles = [];
            let volumes = [];
            let lastBar = null;
            let prevBar = null;
            const colors = getThemeColors();

            if (isIntraday) {
                // Fetch intraday chart intelligence with VWAP, Order Blocks, and FVGs
                const url = `${API_BASE}/api/v1/options/chart-intelligence?symbol=${encodeURIComponent(ticker)}&interval=${encodeURIComponent(tf)}&period=5d&allow_non_fno=true`;
                const resp = await fetch(url);
                if (!resp.ok) return;
                const data = await resp.json();
                if (!data || !data.candles || data.candles.length === 0) return;

                candles = data.candles.map(c => ({
                    time: c.time,
                    open: c.open,
                    high: c.high,
                    low: c.low,
                    close: c.close,
                }));

                volumes = data.candles.map(c => ({
                    time: c.time,
                    value: c.volume || 0,
                    color: c.close >= c.open ? colors.volumeUp : colors.volumeDown,
                }));

                if (candleSeries) candleSeries.setData(candles);
                if (volumeSeries) volumeSeries.setData(volumes);

                // Hide SMAs on intraday to reduce visual clutter, show VWAP and bands
                if (sma20) sma20.setData([]);
                if (sma50) sma50.setData([]);
                if (sma200) sma200.setData([]);

                const ind = data.indicators || {};
                if (vwap) vwap.setData(ind.vwap || []);
                if (vwapUpper) vwapUpper.setData(ind.vwap_upper_1 || ind.vwap_upper || []);
                if (vwapLower) vwapLower.setData(ind.vwap_lower_1 || ind.vwap_lower || []);

                // SMC Markers (Order Blocks and Fair Value Gaps)
                const sm = data.smart_money || {};
                const markers = [];
                const obs = sm.order_blocks || [];
                obs.forEach(ob => {
                    const isBull = ob.type === 'BULLISH_OB';
                    markers.push({
                        time: ob.start_time || ob.time,
                        position: isBull ? 'belowBar' : 'aboveBar',
                        color: isBull ? '#10b981' : '#f43f5e',
                        shape: isBull ? 'arrowUp' : 'arrowDown',
                        text: `${ob.short_label || (isBull ? 'D-OB' : 'S-OB')}${ob.mitigated ? ' (TEST)' : ''}`,
                    });
                });

                const fvgs = sm.fvg_gaps || [];
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
                if (candleSeries && candleSeries.setMarkers) {
                    candleSeries.setMarkers(markers);
                }

                lastBar = data.candles[data.candles.length - 1];
                prevBar = data.candles.length > 1 ? data.candles[data.candles.length - 2] : lastBar;

            } else {
                // Fetch daily / weekly / monthly price history
                const resp = await fetch(`${API_BASE}/api/v1/price-history/${encodeURIComponent(ticker)}`);
                if (!resp.ok) return;
                const records = await resp.json();
                if (!records || records.length === 0) return;

                records.forEach(r => {
                    const itemTime = r.date;
                    candles.push({
                        time: itemTime,
                        open: r.open,
                        high: r.high,
                        low: r.low,
                        close: r.close,
                    });
                    volumes.push({
                        time: itemTime,
                        value: r.volume,
                        color: r.close >= r.open ? colors.volumeUp : colors.volumeDown,
                    });
                });

                if (candleSeries) {
                    candleSeries.setData(candles);
                    candleSeries.setMarkers([]); // clear intraday SMC markers
                }
                if (volumeSeries) volumeSeries.setData(volumes);
                if (sma20) sma20.setData(calculateSMA(records, 20));
                if (sma50) sma50.setData(calculateSMA(records, 50));
                if (sma200) sma200.setData(calculateSMA(records, 200));

                // Clear VWAP on daily chart
                if (vwap) vwap.setData([]);
                if (vwapUpper) vwapUpper.setData([]);
                if (vwapLower) vwapLower.setData([]);

                lastBar = records[records.length - 1];
                prevBar = records.length > 1 ? records[records.length - 2] : lastBar;
            }

            // Update LTP and change % badge
            if (lastBar) {
                const diff = lastBar.close - prevBar.close;
                const pct = prevBar.close > 0 ? (diff / prevBar.close) * 100 : 0;
                const sym = ticker.endsWith('.NS') || ticker.endsWith('.BO') ? '₹' : '$';

                const ltpEl = document.getElementById(`chartPaneLtp-${idx}`);
                const chgEl = document.getElementById(`chartPaneChange-${idx}`);
                if (ltpEl) ltpEl.textContent = `${sym}${lastBar.close.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
                if (chgEl) {
                    chgEl.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
                    chgEl.style.color = pct >= 0 ? '#34d399' : '#f87171';
                }
            }

            if (!preserveRange && app.multiChart.instances[idx]) {
                app.multiChart.instances[idx].timeScale().fitContent();
            }
        } catch (err) {
            console.warn(`Error loading chart data for pane ${idx} (${ticker}):`, err);
        }
    }

    app.startMultiChartAutoRefresh = function() {
        if (app.multiChart.pollTimer) return;
        app.multiChart.pollTimer = setInterval(() => {
            const modal = document.getElementById('multiChartModal');
            if (!modal || modal.style.display === 'none') {
                app.stopMultiChartAutoRefresh();
                return;
            }
            const paneCount = app.multiChart.layout === '1x1' ? 1 : (app.multiChart.layout === '1x2' ? 2 : 4);
            for (let i = 0; i < paneCount; i++) {
                loadPaneData(i, true);
            }
        }, 15000);
    };

    app.stopMultiChartAutoRefresh = function() {
        if (app.multiChart.pollTimer) {
            clearInterval(app.multiChart.pollTimer);
            app.multiChart.pollTimer = null;
        }
    };

    app.openMultiChartModal = function(ticker, layout) {
        if (ticker) {
            app.multiChart.tickers[0] = ticker.toUpperCase().trim();
            const input0 = document.getElementById('chartTickerInput-0');
            if (input0) input0.value = app.multiChart.tickers[0];
        }

        const modal = document.getElementById('multiChartModal');
        if (modal) {
            modal.style.display = 'flex';
        }

        app.setMultiChartLayout(layout || app.multiChart.layout || '1x1');
        app.startMultiChartAutoRefresh();
    };

    app.closeMultiChartModal = function() {
        const modal = document.getElementById('multiChartModal');
        if (modal) modal.style.display = 'none';
        app.stopMultiChartAutoRefresh();
    };

    app.setMultiChartLayout = function(layout) {
        app.multiChart.layout = layout;
        const grid = document.getElementById('multiChartGrid');
        if (!grid) return;

        ['1x1', '1x2', '2x2'].forEach(l => {
            const btn = document.getElementById(`chartLayoutBtn-${l}`);
            if (btn) {
                if (l === layout) {
                    btn.classList.add('active');
                    btn.style.background = 'rgba(56,189,248,0.2)';
                    btn.style.color = '#38bdf8';
                } else {
                    btn.classList.remove('active');
                    btn.style.background = 'transparent';
                    btn.style.color = '#94a3b8';
                }
            }
        });

        grid.className = `multi-chart-grid grid-${layout}`;

        const paneCount = layout === '1x1' ? 1 : (layout === '1x2' ? 2 : 4);

        for (let i = 0; i < 4; i++) {
            const wrap = document.getElementById(`chartPaneWrap-${i}`);
            if (wrap) {
                if (i < paneCount) {
                    wrap.style.display = 'flex';
                    setTimeout(() => initChartInstance(i), 50);
                } else {
                    wrap.style.display = 'none';
                }
            }
        }
    };

    app.updateChartPaneTicker = function(paneIdx, ticker) {
        if (!ticker) return;
        app.multiChart.tickers[paneIdx] = ticker.toUpperCase().trim();
        loadPaneData(paneIdx);
    };

    app.setChartPaneTimeframe = function(paneIdx, tf) {
        app.multiChart.timeframes[paneIdx] = tf;
        const wrap = document.getElementById(`chartPaneWrap-${paneIdx}`);
        if (wrap) {
            wrap.querySelectorAll('.btn-tf').forEach(b => {
                if (b.textContent.trim() === tf) {
                    b.classList.add('active');
                } else {
                    b.classList.remove('active');
                }
            });
        }
        loadPaneData(paneIdx);
    };

    app.toggleMultiChartCrosshairSync = function(enabled) {
        app.multiChart.syncCrosshair = !!enabled;
    };

    // Hotkey listener for Escape key to close modal
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('multiChartModal');
            if (modal && modal.style.display === 'flex') {
                app.closeMultiChartModal();
            }
        }
    });

})();
