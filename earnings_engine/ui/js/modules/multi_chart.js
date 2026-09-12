// =========================================================================
// 📈 Interactive Multi-Chart Studio (TradingView Lightweight Charts v4.1.3)
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app.multiChart = {
        layout: '1x1',
        syncCrosshair: true,
        instances: [null, null, null, null],
        candleSeries: [null, null, null, null],
        volumeSeries: [null, null, null, null],
        sma20Series: [null, null, null, null],
        sma50Series: [null, null, null, null],
        sma200Series: [null, null, null, null],
        tickers: ['TCS.NS', 'RELIANCE.NS', 'INFY.NS', 'HDFCBANK.NS'],
        timeframes: ['1D', '1D', '1D', '1D'],
        isSyncing: false,
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
            },
            rightPriceScale: {
                borderColor: colors.border,
                scaleMargins: { top: 0.1, bottom: 0.2 },
            },
            timeScale: {
                borderColor: colors.border,
                timeVisible: true,
                secondsVisible: false,
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

        app.multiChart.instances[idx] = chart;
        app.multiChart.candleSeries[idx] = candleSeries;
        app.multiChart.volumeSeries[idx] = volumeSeries;
        app.multiChart.sma20Series[idx] = sma20;
        app.multiChart.sma50Series[idx] = sma50;
        app.multiChart.sma200Series[idx] = sma200;

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

    async function loadPaneData(idx) {
        const ticker = app.multiChart.tickers[idx] || 'TCS.NS';
        const tf = app.multiChart.timeframes[idx] || '1D';

        try {
            const resp = await fetch(`${API_BASE}/api/v1/price-history/${encodeURIComponent(ticker)}`);
            if (!resp.ok) return;
            const records = await resp.json();
            if (!records || records.length === 0) return;

            const colors = getThemeColors();
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
                volumes.push({
                    time: itemTime,
                    value: r.volume,
                    color: r.close >= r.open ? colors.volumeUp : colors.volumeDown,
                });
            });

            const candleSeries = app.multiChart.candleSeries[idx];
            const volumeSeries = app.multiChart.volumeSeries[idx];
            const sma20 = app.multiChart.sma20Series[idx];
            const sma50 = app.multiChart.sma50Series[idx];
            const sma200 = app.multiChart.sma200Series[idx];

            if (candleSeries) candleSeries.setData(candles);
            if (volumeSeries) volumeSeries.setData(volumes);
            if (sma20) sma20.setData(calculateSMA(records, 20));
            if (sma50) sma50.setData(calculateSMA(records, 50));
            if (sma200) sma200.setData(calculateSMA(records, 200));

            // Update LTP and change % badge
            const lastBar = records[records.length - 1];
            const prevBar = records.length > 1 ? records[records.length - 2] : lastBar;
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

            if (app.multiChart.instances[idx]) {
                app.multiChart.instances[idx].timeScale().fitContent();
            }
        } catch (err) {
            console.warn(`Error loading chart data for pane ${idx} (${ticker}):`, err);
        }
    }

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
    };

    app.closeMultiChartModal = function() {
        const modal = document.getElementById('multiChartModal');
        if (modal) modal.style.display = 'none';
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
