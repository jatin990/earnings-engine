/**
 * Nexus Intelligence Platform — Stock Drilldown Technical Chart Engine
 * High-Density Lightweight Charts canvas matching Options Hub / Futures Chart.
 * Includes VWAP +1.5σ Bands, Volume Surges, Crosshair HUD, Liquidity Walls & POC.
 */

(function () {
    'use strict';

    const State = window.StockDetailState;
    let _avgVolume20 = 1;
    let _toggles = {
        sma20: true,
        sma50: true,
        sma200: true,
        vwap: true,
        walls: true,
    };

    /**
     * Initialize the Advanced Lightweight Charts Canvas
     */
    window.initStockChart = function () {
        const container = document.getElementById('stockChartCanvas');
        if (!container || !window.LightweightCharts) return;

        if (State.chartInstance) {
            try {
                State.chartInstance.remove();
            } catch (e) {
                console.debug('Error disposing previous chart instance:', e);
            }
            State.chartInstance = null;
        }

        const chart = window.LightweightCharts.createChart(container, {
            width: container.clientWidth || 800,
            height: 520,
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
                timeFormatter: (time) => window.formatIST(time, { includeTime: false, includeYear: true, suffix: false }),
                dateFormatter: (time) => window.formatIST(time, { includeTime: false, includeYear: true, suffix: false }),
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

        // 3. Simple Moving Averages
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

        State.chartInstance = chart;
        State.candleSeries = candleSeries;
        State.volumeSeries = volumeSeries;
        State.sma20Series = sma20Series;
        State.sma50Series = sma50Series;
        State.sma200Series = sma200Series;
        State.vwapSeries = vwapSeries;
        State.vwapUpperSeries = vwapUpperSeries;
        State.vwapLowerSeries = vwapLowerSeries;

        // Subscribe to crosshair movement
        chart.subscribeCrosshairMove(handleStockCrosshairMove);

        // Responsive Resize
        const ro = new ResizeObserver((entries) => {
            if (!entries || entries.length === 0 || !State.chartInstance) return;
            const { width, height } = entries[0].contentRect;
            if (width > 0 && height > 0) {
                State.chartInstance.applyOptions({ width, height });
            }
        });
        ro.observe(container);

        loadStockChartData();
    };

    /**
     * Fetch Price History & Populate Series
     */
    window.loadStockChartData = async function () {
        const overlay = document.getElementById('stockChartLoading');
        if (overlay) overlay.style.display = 'flex';

        try {
            const resp = await fetch(`/api/v1/price-history/${encodeURIComponent(State.ticker)}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const records = await resp.json();

            if (!records || records.length === 0) {
                if (overlay) {
                    overlay.innerHTML = `<span style="color:#fb7185;">No historical price bars available for ${State.ticker}</span>`;
                }
                return;
            }

            State.chartRecords = records;

            // Calculate 20D average volume for surge ratios
            const recentVols = records.slice(-20).map((r) => r.volume || 0);
            _avgVolume20 = recentVols.length > 0 ? recentVols.reduce((a, b) => a + b, 0) / recentVols.length : 1;

            const candles = [];
            const volumes = [];

            records.forEach((r) => {
                const itemTime = r.date;
                candles.push({
                    time: itemTime,
                    open: r.open,
                    high: r.high,
                    low: r.low,
                    close: r.close,
                });

                const isBull = r.close >= r.open;
                const isSurge = _avgVolume20 > 0 && r.volume > _avgVolume20 * 1.8;
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

            if (State.candleSeries) State.candleSeries.setData(candles);
            if (State.volumeSeries) State.volumeSeries.setData(volumes);

            // Compute and set Technical Overlays
            if (State.sma20Series) State.sma20Series.setData(calculateSMA(records, 20));
            if (State.sma50Series) State.sma50Series.setData(calculateSMA(records, 50));
            if (State.sma200Series) State.sma200Series.setData(calculateSMA(records, 200));

            // Compute VWAP Bands
            const vwapData = calculateVWAPWithBands(records);
            if (State.vwapSeries) State.vwapSeries.setData(vwapData.vwap);
            if (State.vwapUpperSeries) State.vwapUpperSeries.setData(vwapData.upper);
            if (State.vwapLowerSeries) State.vwapLowerSeries.setData(vwapData.lower);

            if (overlay) overlay.style.display = 'none';

            // Set initial range & trigger Liquidity Walls fetch
            setChartRange(State.activeRange || '1Y');
            updateHudWithLastBar();

            if (window.loadStockLiquidityWalls) {
                window.loadStockLiquidityWalls();
            }
        } catch (err) {
            console.error('Error loading chart data:', err);
            if (overlay) {
                overlay.innerHTML = `<span style="color:#fb7185;">Failed to load price bars (${err.message})</span>`;
            }
        }
    };

    /**
     * Crosshair Movement Handler for Sticky HUD Bar
     */
    function handleStockCrosshairMove(param) {
        if (!param || !param.time || !State.candleSeries || !param.seriesData) {
            updateHudWithLastBar();
            return;
        }

        const candle = param.seriesData.get(State.candleSeries);
        if (!candle) {
            updateHudWithLastBar();
            return;
        }

        const timeStr = typeof param.time === 'string' ? param.time : window.formatIST(param.time);
        renderHudData(candle, timeStr);
    }

    function updateHudWithLastBar() {
        if (!State.chartRecords || State.chartRecords.length === 0) return;
        const last = State.chartRecords[State.chartRecords.length - 1];
        renderHudData({
            open: last.open,
            high: last.high,
            low: last.low,
            close: last.close,
            volume: last.volume,
        }, last.date);
    }

    function renderHudData(candle, timeStr) {
        window.setElText('hudDate', timeStr);
        window.setElText('hudOpen', window.formatPrice(candle.open));
        window.setElText('hudHigh', window.formatPrice(candle.high));
        window.setElText('hudLow', window.formatPrice(candle.low));
        window.setElText('hudClose', window.formatPrice(candle.close));

        const tr = (candle.high !== undefined && candle.low !== undefined) ? (candle.high - candle.low) : 0;
        window.setElText('hudTr', window.formatPrice(tr));

        // Find raw record for volume
        let vol = candle.volume;
        if (vol === undefined && State.chartRecords) {
            const match = State.chartRecords.find((r) => r.date === timeStr);
            if (match) vol = match.volume;
        }

        window.setElText('hudVol', window.formatVolume(vol));

        // Surge Ratio
        if (vol && _avgVolume20 > 0) {
            const surge = (vol / _avgVolume20).toFixed(1);
            window.setElText('hudSurge', `${surge}x`);
            const surgeEl = document.getElementById('hudSurge');
            if (surgeEl) {
                surgeEl.style.color = Number(surge) >= 2.0 ? '#34d399' : Number(surge) >= 1.2 ? '#38bdf8' : '#8e97a8';
            }
        }

        // Wick Pressure Delta
        if (candle.high && candle.low && candle.open && candle.close) {
            const body = Math.abs(candle.close - candle.open);
            const upperWick = candle.high - Math.max(candle.open, candle.close);
            const lowerWick = Math.min(candle.open, candle.close) - candle.low;
            const delta = (lowerWick - upperWick) / (tr || 1);
            const deltaFormatted = (delta > 0 ? '+' : '') + delta.toFixed(2);
            window.setElText('hudWickDelta', deltaFormatted);
            const deltaEl = document.getElementById('hudWickDelta');
            if (deltaEl) {
                deltaEl.style.color = delta > 0.15 ? '#34d399' : delta < -0.15 ? '#fb7185' : '#8e97a8';
            }
        }
    }

    /**
     * Range Switcher (1M, 3M, 6M, 1Y, ALL)
     */
    window.setChartRange = function (range) {
        State.activeRange = range;
        ['1M', '3M', '6M', '1Y', 'ALL'].forEach((r) => {
            const btn = document.getElementById(`btnRange${r}`);
            if (btn) {
                if (r === range) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        });

        if (!State.chartInstance || !State.chartRecords || State.chartRecords.length === 0) return;

        if (range === 'ALL') {
            State.chartInstance.timeScale().fitContent();
            return;
        }

        const total = State.chartRecords.length;
        let barsToShow = 252;
        if (range === '1M') barsToShow = 22;
        else if (range === '3M') barsToShow = 65;
        else if (range === '6M') barsToShow = 130;
        else if (range === '1Y') barsToShow = 252;

        const fromIdx = Math.max(0, total - barsToShow);
        const fromDate = State.chartRecords[fromIdx]?.date;
        const toDate = State.chartRecords[total - 1]?.date;

        if (fromDate && toDate) {
            State.chartInstance.timeScale().setVisibleRange({
                from: fromDate,
                to: toDate,
            });
        } else {
            State.chartInstance.timeScale().fitContent();
        }
    };

    /**
     * Technical Indicator Toggles
     */
    window.toggleIndicator = function (name) {
        _toggles[name] = !_toggles[name];
        const btn = document.getElementById(`toggle${name.toUpperCase()}`);
        if (btn) {
            if (_toggles[name]) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        }

        if (name === 'sma20' && State.sma20Series) State.sma20Series.applyOptions({ visible: _toggles.sma20 });
        if (name === 'sma50' && State.sma50Series) State.sma50Series.applyOptions({ visible: _toggles.sma50 });
        if (name === 'sma200' && State.sma200Series) State.sma200Series.applyOptions({ visible: _toggles.sma200 });
        if (name === 'vwap') {
            if (State.vwapSeries) State.vwapSeries.applyOptions({ visible: _toggles.vwap });
            if (State.vwapUpperSeries) State.vwapUpperSeries.applyOptions({ visible: _toggles.vwap });
            if (State.vwapLowerSeries) State.vwapLowerSeries.applyOptions({ visible: _toggles.vwap });
        }
        if (name === 'walls' && State.liquidityLines) {
            State.liquidityLines.forEach((line) => {
                try {
                    State.candleSeries.removePriceLine(line);
                } catch (e) {}
            });
            State.liquidityLines = [];
            if (_toggles.walls && window.applyLiquidityLinesToChart) {
                window.applyLiquidityLinesToChart();
            }
        }
    };

    /**
     * Helper Calculations: SMA & VWAP + Standard Deviation Bands
     */
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

            const vwap = cumTypicalVol / cumVol;

            // Rolling variance for standard deviation band
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
})();
