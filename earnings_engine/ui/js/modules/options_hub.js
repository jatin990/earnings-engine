/**
 * Option Chain & Derivatives Hub Module
 *
 * Provides interactive strike trees, ATM call/put walls, Max Pain, PCR metrics,
 * multi-day positioning snapshots, and full-featured TradingView Lightweight Charts
 * with VWAP, 15m ORB, Order Blocks (SMC), and Tactical Buy/Sell Trade Plans.
 */
(function (window) {
    'use strict';

    window.app = window.app || {};
    const app = window.app;

    app._optionsSymbol = 'NIFTY';
    app._optionsExpiry = '';
    app._optionsStrikeRange = 20;
    app._optionsTimeframe = '5m';
    app._optionsLayers = {
        vwap: true,
        ob: true,
        derivatives: true,
        orb: true,
        trendlines: true,
    };

    app._optionsChart = null; // Chart.js instance for OI distribution
    app._smartChart = null;   // TradingView Lightweight Charts instance
    app._candleSeries = null;
    app._volumeSeries = null;
    app._vwapSeries = null;
    app._vwapUpperSeries = null;
    app._vwapLowerSeries = null;
    app._trendlineSeries = [];
    app._chartPriceLines = [];
    app._smartChartData = null;
    app._optionsPollTimer = null;
    app._hasInitialChartFitted = false;

    /**
     * Switch active symbol and refresh both option chain & chart intelligence
     */
    app.switchOptionSymbol = function (symbol) {
        if (!symbol) return;
        const clean = symbol.trim().toUpperCase().replace('.NS', '');
        app._optionsSymbol = clean;
        app._optionsExpiry = ''; // Reset expiry to default to nearest active
        app._hasInitialChartFitted = false;

        // Update active class on quick pills
        document.querySelectorAll('.option-sym-pill').forEach(pill => {
            pill.classList.toggle('active', pill.getAttribute('data-sym') === clean);
        });

        const input = document.getElementById('optionsSymbolInput');
        if (input) input.value = clean;

        app.loadOptionChain(false);
        app.loadOptionsChartIntelligence(false, false);
    };

    /**
     * Handler for expiry date selector
     */
    app.onOptionExpiryChange = function (expiry) {
        app._optionsExpiry = expiry || '';
        app.loadOptionChain(false);
    };

    /**
     * Handler for strike range selector
     */
    app.onOptionStrikeRangeChange = function (range) {
        app._optionsStrikeRange = parseInt(range, 10) || 20;
        app.loadOptionChain(false);
    };

    /**
     * Timeframe switcher for smart chart
     */
    app.setOptionTimeframe = function (tf) {
        if (!tf) return;
        app._optionsTimeframe = tf;
        app._hasInitialChartFitted = false;

        document.querySelectorAll('.opt-tf-btn').forEach(btn => {
            const isActive = btn.getAttribute('data-tf') === tf;
            btn.classList.toggle('active', isActive);
            btn.style.background = isActive ? '#38bdf8' : 'transparent';
            btn.style.color = isActive ? '#000000' : '#94a3b8';
        });

        app.loadOptionsChartIntelligence(false, false);
    };

    /**
     * Layer visibility toggle for smart chart
     */
    app.toggleOptionLayer = function (layer) {
        if (!(layer in app._optionsLayers)) return;
        app._optionsLayers[layer] = !app._optionsLayers[layer];

        const btnIdMap = {
            vwap: 'optToggleVwap',
            ob: 'optToggleOb',
            derivatives: 'optToggleDeriv',
            orb: 'optToggleOrb',
            trendlines: 'optToggleTrendlines',
        };

        const btn = document.getElementById(btnIdMap[layer]);
        if (btn) {
            const active = app._optionsLayers[layer];
            btn.classList.toggle('active', active);
            btn.style.opacity = active ? '1' : '0.4';
        }

        if (app._smartChartData) {
            app.renderSmartChart(app._smartChartData, true);
        }
    };

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
            const container = document.getElementById('optionsSmartChartCanvas');
            if (container && app._smartChart) {
                let range = null;
                try {
                    range = app._smartChart.timeScale().getVisibleLogicalRange();
                } catch (e) {}

                app._smartChart.applyOptions({
                    width: container.clientWidth || 800,
                    height: container.clientHeight || 460,
                });

                if (range) {
                    try {
                        app._smartChart.timeScale().setVisibleLogicalRange(range);
                    } catch (e) {}
                }
            }
        };

        // Resize immediately and after CSS transition completes
        resizeChart();
        setTimeout(resizeChart, 100);
        setTimeout(resizeChart, 300);
    };

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
     * Load Option Chain and calculate key metrics
     */
    app.loadOptionChain = async function (forceRefresh = false) {
        const symbol = app._optionsSymbol || 'NIFTY';
        const expiry = app._optionsExpiry || '';
        const strikeRange = app._optionsStrikeRange || 20;

        const refreshBtn = document.getElementById('optionsRefreshBtn');
        const chartLoading = document.getElementById('optionsChartLoading');
        const statusBanner = document.getElementById('optionsStatusBanner');

        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<span>⏳</span> Loading...';
        }
        if (chartLoading) chartLoading.style.display = 'flex';

        try {
            let url = `/api/v1/options/chain?symbol=${encodeURIComponent(symbol)}&strike_range=${strikeRange}`;
            if (expiry) url += `&expiry=${encodeURIComponent(expiry)}`;
            if (forceRefresh) url += `&force_refresh=true`;

            const res = await fetch(url);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || `Server error: ${res.status}`);
            }

            const payload = await res.json();
            const data = payload.data || {};

            // Handle status banner for offline / archived / not_fno states
            if (statusBanner) {
                if (data.status === 'NOT_FNO') {
                    statusBanner.style.display = 'block';
                    statusBanner.style.background = 'rgba(239, 68, 68, 0.15)';
                    statusBanner.style.border = '1px solid rgba(239, 68, 68, 0.35)';
                    statusBanner.style.color = '#f87171';
                    statusBanner.innerHTML = `⚠️ <strong>${symbol} is not eligible for NSE Derivatives (F&amp;O)</strong>. Only official NSE index &amp; stock derivatives are supported.`;
                } else if (data.status === 'ARCHIVED') {
                    statusBanner.style.display = 'block';
                    statusBanner.style.background = 'rgba(245, 158, 11, 0.15)';
                    statusBanner.style.border = '1px solid rgba(245, 158, 11, 0.35)';
                    statusBanner.style.color = '#fbbf24';
                    statusBanner.innerHTML = `ℹ️ <strong>NSE Live Option Chain is closed / unreachable</strong>. Displaying latest recorded positioning snapshot${data.as_of_date ? ' from ' + data.as_of_date : ''}.`;
                } else if (data.status === 'OFFLINE') {
                    statusBanner.style.display = 'block';
                    statusBanner.style.background = 'rgba(239, 68, 68, 0.15)';
                    statusBanner.style.border = '1px solid rgba(239, 68, 68, 0.35)';
                    statusBanner.style.color = '#f87171';
                    statusBanner.innerHTML = `📡 <strong>Option Chain Unreachable</strong>. NSE data provider did not respond and no local archival snapshot was found.`;
                } else {
                    statusBanner.style.display = 'none';
                }
            }

            // Populate Expiries Dropdown if available
            app.populateOptionExpiries(data.expiries || [], data.selected_expiry || expiry);

            // Render KPI cards
            app.renderOptionKpiCards(data);

            // Render Open Interest Distribution Chart
            app.renderOiDistributionChart(data);

            // Render Strike Tree Table
            app.renderStrikeTreeTable(data);

            // Also load multi-day positioning history asynchronously
            app.fetchOptionHistory(symbol);

        } catch (err) {
            console.error('Failed to load option chain:', err);
            if (statusBanner) {
                statusBanner.style.display = 'block';
                statusBanner.style.background = 'rgba(239, 68, 68, 0.15)';
                statusBanner.style.border = '1px solid rgba(239, 68, 68, 0.35)';
                statusBanner.style.color = '#f87171';
                statusBanner.innerHTML = `❌ <strong>Error loading option chain:</strong> ${err.message}`;
            }
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<span>🔄</span> Refresh';
            }
            if (chartLoading) chartLoading.style.display = 'none';
        }
    };

    /**
     * Initialize the TradingView Lightweight Charts instance
     */
    app.initOptionsSmartChart = function () {
        const container = document.getElementById('optionsSmartChartCanvas');
        if (!container || !window.LightweightCharts) return;

        if (app._smartChart) {
            try {
                app._smartChart.remove();
            } catch (e) {
                console.debug('Error disposing smart chart instance:', e);
            }
            app._smartChart = null;
        }

        const chart = window.LightweightCharts.createChart(container, {
            width: container.clientWidth || 800,
            height: 460,
            layout: {
                background: { type: 'solid', color: '#090a0f' },
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
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
                scaleMargins: { top: 0.08, bottom: 0.15 },
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // Candlestick series
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#10b981',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#10b981',
            wickDownColor: '#ef4444',
        });

        // Volume sub-series
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: '', // overlay
            scaleMargins: { top: 0.82, bottom: 0 },
        });

        // VWAP line series
        const vwapSeries = chart.addLineSeries({
            color: '#38bdf8',
            lineWidth: 2,
            title: 'VWAP',
        });

        // VWAP Upper Band
        const vwapUpperSeries = chart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.5)',
            lineWidth: 1,
            lineStyle: window.LightweightCharts.LineStyle.Dotted,
            title: 'VWAP +1.5σ',
        });

        // VWAP Lower Band
        const vwapLowerSeries = chart.addLineSeries({
            color: 'rgba(56, 189, 248, 0.5)',
            lineWidth: 1,
            lineStyle: window.LightweightCharts.LineStyle.Dotted,
            title: 'VWAP -1.5σ',
        });

        app._smartChart = chart;
        app._candleSeries = candleSeries;
        app._volumeSeries = volumeSeries;
        app._vwapSeries = vwapSeries;
        app._vwapUpperSeries = vwapUpperSeries;
        app._vwapLowerSeries = vwapLowerSeries;

        // Responsive ResizeObserver
        const ro = new ResizeObserver(entries => {
            if (!entries || entries.length === 0 || !app._smartChart) return;
            const { width, height } = entries[0].contentRect;
            if (width > 0 && height > 0) {
                app._smartChart.applyOptions({ width, height });
            }
        });
        ro.observe(container);
    };

    /**
     * Load full candlestick & quant intelligence from backend API
     */
    app.loadOptionsChartIntelligence = async function (forceRefresh = false, isBackground = false) {
        const symbol = app._optionsSymbol || 'NIFTY';
        const tf = app._optionsTimeframe || '5m';
        const loadingEl = document.getElementById('optionsSmartChartLoading');
        const dot = document.getElementById('optLivePulseDot');

        if (loadingEl && !isBackground) {
            loadingEl.style.display = 'flex';
        }

        try {
            const url = `/api/v1/options/chart-intelligence?symbol=${encodeURIComponent(symbol)}&interval=${tf}&force_refresh=${forceRefresh}`;
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();
            app._smartChartData = data;

            // Render chart (preserving user zoom / pan if background update) & Tactical HUD
            app.renderSmartChart(data, isBackground);
            app.updateTacticalHUD(data);

            if (isBackground && dot) {
                dot.style.transform = 'scale(1.4)';
                setTimeout(() => { if (dot) dot.style.transform = 'scale(1)'; }, 350);
            }

        } catch (err) {
            console.error('Failed to load chart intelligence:', err);
        } finally {
            if (loadingEl && !isBackground) {
                loadingEl.style.display = 'none';
            }
        }
    };

    /**
     * Render Candlesticks, Indicators, Order Blocks & Structural Lines on Lightweight Chart
     */
    app.renderSmartChart = function (data, isBackground = false) {
        if (!app._smartChart) {
            app.initOptionsSmartChart();
        }
        if (!app._smartChart || !app._candleSeries) return;

        // Capture user's current zoom / pan viewport range to prevent resets on auto-refresh
        let prevLogicalRange = null;
        try {
            if (app._hasInitialChartFitted) {
                prevLogicalRange = app._smartChart.timeScale().getVisibleLogicalRange();
            }
        } catch (e) {}

        const candles = data.candles || [];
        if (candles.length === 0) {
            app._candleSeries.setData([]);
            if (app._volumeSeries) app._volumeSeries.setData([]);
            return;
        }

        // Set Candlestick data
        app._candleSeries.setData(candles.map(c => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        })));

        // Set Volume data
        if (app._volumeSeries) {
            app._volumeSeries.setData(candles.map(c => ({
                time: c.time,
                value: c.volume,
                color: c.close >= c.open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
            })));
        }

        // Clear existing price lines & trendlines
        app._chartPriceLines.forEach(line => {
            try {
                app._candleSeries.removePriceLine(line);
            } catch (e) {}
        });
        app._chartPriceLines = [];

        app._trendlineSeries.forEach(s => {
            try {
                app._smartChart.removeSeries(s);
            } catch (e) {}
        });
        app._trendlineSeries = [];

        const indicators = data.indicators || {};
        const smartMoney = data.smart_money || {};
        const derivLevels = data.derivatives_levels || {};

        // 1. VWAP & Bands
        if (app._optionsLayers.vwap && indicators.vwap && indicators.vwap.length > 0) {
            app._vwapSeries.setData(indicators.vwap);
            app._vwapUpperSeries.setData(indicators.vwap_upper_1 || []);
            app._vwapLowerSeries.setData(indicators.vwap_lower_1 || []);
        } else {
            app._vwapSeries.setData([]);
            app._vwapUpperSeries.setData([]);
            app._vwapLowerSeries.setData([]);
        }

        // 2. Derivatives Levels (Horizontal Lines)
        if (app._optionsLayers.derivatives && derivLevels) {
            // Max Pain (Amber Dashed)
            if (derivLevels.max_pain) {
                const mpLine = app._candleSeries.createPriceLine({
                    price: parseFloat(derivLevels.max_pain),
                    color: '#fbbf24',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `Max Pain: ₹${derivLevels.max_pain}`,
                });
                app._chartPriceLines.push(mpLine);
            }

            // Call Wall / Major Resistance (Red Solid)
            if (derivLevels.call_wall) {
                const cwLine = app._candleSeries.createPriceLine({
                    price: parseFloat(derivLevels.call_wall),
                    color: '#f87171',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: `Call Wall: ₹${derivLevels.call_wall}`,
                });
                app._chartPriceLines.push(cwLine);
            }

            // Put Wall / Major Support (Green Solid)
            if (derivLevels.put_wall) {
                const pwLine = app._candleSeries.createPriceLine({
                    price: parseFloat(derivLevels.put_wall),
                    color: '#34d399',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: `Put Wall: ₹${derivLevels.put_wall}`,
                });
                app._chartPriceLines.push(pwLine);
            }
        }

        // 3. Opening Range Breakout (ORB-15) Range Lines
        if (app._optionsLayers.orb && indicators.orb && indicators.orb.active) {
            const orbHigh = app._candleSeries.createPriceLine({
                price: parseFloat(indicators.orb.high),
                color: '#c084fc',
                lineWidth: 1,
                lineStyle: window.LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: `ORB High: ₹${indicators.orb.high}`,
            });
            const orbLow = app._candleSeries.createPriceLine({
                price: parseFloat(indicators.orb.low),
                color: '#c084fc',
                lineWidth: 1,
                lineStyle: window.LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: `ORB Low: ₹${indicators.orb.low}`,
            });
            app._chartPriceLines.push(orbHigh, orbLow);
        }

        // 4. Smart Money Order Blocks (OB) & FVGs as Markers
        if (app._optionsLayers.ob) {
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

            // Sort markers chronologically
            markers.sort((a, b) => a.time - b.time);
            app._candleSeries.setMarkers(markers);
        } else {
            app._candleSeries.setMarkers([]);
        }

        // 5. Dynamic Support/Resistance Trendlines
        if (app._optionsLayers.trendlines && smartMoney.trendlines) {
            smartMoney.trendlines.forEach(tl => {
                const s = app._smartChart.addLineSeries({
                    color: tl.type === 'SUPPORT' ? '#34d399' : '#f87171',
                    lineWidth: 1,
                    lineStyle: window.LightweightCharts.LineStyle.Dashed,
                    title: tl.label || tl.type,
                });
                s.setData([
                    { time: tl.p1.time, value: tl.p1.price },
                    { time: tl.p2.time, value: tl.p2.price },
                ]);
                app._trendlineSeries.push(s);
            });
        }

        // Restore viewport zoom & scroll position if already fitted; else fit initial
        if (app._hasInitialChartFitted && prevLogicalRange && isBackground) {
            try {
                app._smartChart.timeScale().setVisibleLogicalRange(prevLogicalRange);
            } catch (e) {
                app._smartChart.timeScale().fitContent();
            }
        } else if (!app._hasInitialChartFitted) {
            app._smartChart.timeScale().fitContent();
            app._hasInitialChartFitted = true;
        }
    };

    /**
     * Update the Tactical "Where to Buy & Where to Sell" HUD Deck
     */
    app.updateTacticalHUD = function (data) {
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

        // 3. Micro-Structure & Market Regime
        const regimeTextEl = document.getElementById('optStructureRegimeText');
        const orbTextEl = document.getElementById('optStructureOrbText');
        const straddleTextEl = document.getElementById('optStructureStraddleText');
        const pivotTextEl = document.getElementById('optStructurePivotText');
        const flowTextEl = document.getElementById('optStructureFlowText');

        if (regimeTextEl) regimeTextEl.textContent = tactical.regime || '--';
        if (orbTextEl) {
            const orbStatus = orb.status === 'BREAKOUT_BULLISH' ? `Bullish > ₹${orb.high}` :
                              orb.status === 'BREAKDOWN_BEARISH' ? `Bearish < ₹${orb.low}` : `Inside [₹${orb.low} - ₹${orb.high}]`;
            orbTextEl.textContent = orbStatus;
        }
        if (straddleTextEl) {
            straddleTextEl.textContent = (deriv.straddle_expected_low && deriv.straddle_expected_high) ?
                `₹${deriv.straddle_expected_low.toLocaleString()} – ₹${deriv.straddle_expected_high.toLocaleString()}` : '--';
        }
        if (pivotTextEl) {
            pivotTextEl.textContent = deriv.max_pain ? `Max Pain: ₹${deriv.max_pain.toLocaleString()}` : '--';
        }
        if (flowTextEl) {
            flowTextEl.textContent = `${tactical.primary_bias || 'NEUTRAL'} (PCR ${deriv.pcr_oi || '--'})`;
        }
    };

    /**
     * Populate the expiry dates dropdown
     */
    app.populateOptionExpiries = function (expiries, selectedExpiry) {
        const select = document.getElementById('optionsExpirySelect');
        if (!select) return;

        const currentVal = selectedExpiry || app._optionsExpiry || '';
        let html = '<option value="">Nearest Active</option>';

        if (expiries && expiries.length > 0) {
            expiries.forEach(exp => {
                const isSelected = (exp === currentVal) ? 'selected' : '';
                html += `<option value="${exp}" ${isSelected}>${exp}</option>`;
            });
        }
        select.innerHTML = html;
        if (currentVal && expiries.includes(currentVal)) {
            select.value = currentVal;
        }
    };

    /**
     * Render the 7 KPI Summary Cards
     */
    app.renderOptionKpiCards = function (data) {
        const formatNum = (num, decimals = 2) => {
            if (num === null || num === undefined || isNaN(num)) return '--';
            return Number(num).toLocaleString('en-IN', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            });
        };

        const formatQty = (qty) => {
            if (qty === null || qty === undefined || isNaN(qty)) return '--';
            const val = Number(qty);
            if (val >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
            if (val >= 100000) return (val / 100000).toFixed(2) + ' L';
            if (val >= 1000) return (val / 1000).toFixed(1) + 'k';
            return val.toLocaleString('en-IN');
        };

        // Spot Price
        const spotEl = document.getElementById('optKpiSpotPrice');
        if (spotEl) spotEl.textContent = formatNum(data.spot_price, 2);

        // Max Pain Strike
        const mpEl = document.getElementById('optKpiMaxPain');
        if (mpEl) mpEl.textContent = formatNum(data.max_pain_strike, 0);

        // PCR (OI)
        const pcrOiEl = document.getElementById('optKpiPcrOi');
        const pcrOiLabel = document.getElementById('optKpiPcrOiLabel');
        if (pcrOiEl) {
            const pcr = data.pcr_oi;
            pcrOiEl.textContent = formatNum(pcr, 2);
            if (pcr !== null && pcr !== undefined) {
                if (pcr > 1.2) {
                    pcrOiEl.style.color = '#34d399'; // Bullish
                    if (pcrOiLabel) pcrOiLabel.textContent = 'Bullish (Put Heavy)';
                } else if (pcr < 0.8) {
                    pcrOiEl.style.color = '#f87171'; // Bearish
                    if (pcrOiLabel) pcrOiLabel.textContent = 'Bearish (Call Heavy)';
                } else {
                    pcrOiEl.style.color = '#38bdf8'; // Neutral
                    if (pcrOiLabel) pcrOiLabel.textContent = 'Neutral (Balanced)';
                }
            }
        }

        // PCR (Volume)
        const pcrVolEl = document.getElementById('optKpiPcrVol');
        if (pcrVolEl) pcrVolEl.textContent = formatNum(data.pcr_volume, 2);

        // Call Wall (Resistance)
        const callWallEl = document.getElementById('optKpiCallWall');
        const callWallOiEl = document.getElementById('optKpiCallWallOi');
        if (callWallEl) callWallEl.textContent = formatNum(data.resistance_strike, 0);
        if (callWallOiEl) callWallOiEl.textContent = `Total Call OI: ${formatQty(data.call_oi_total)}`;

        // Put Wall (Support)
        const putWallEl = document.getElementById('optKpiPutWall');
        const putWallOiEl = document.getElementById('optKpiPutWallOi');
        if (putWallEl) putWallEl.textContent = formatNum(data.support_strike, 0);
        if (putWallOiEl) putWallOiEl.textContent = `Total Put OI: ${formatQty(data.put_oi_total)}`;

        // ATM IV & Sentiment
        const atmIvEl = document.getElementById('optKpiAtmIv');
        const atmStraddleEl = document.getElementById('optKpiAtmStraddle');
        if (atmIvEl) {
            const atmStrike = (data.strikes || []).find(s => s.is_atm);
            if (atmStrike) {
                const avgIv = ((atmStrike.ce_iv || 0) + (atmStrike.pe_iv || 0)) / ((atmStrike.ce_iv && atmStrike.pe_iv) ? 2 : 1);
                atmIvEl.textContent = avgIv > 0 ? `${avgIv.toFixed(1)}%` : '--';
                if (atmStraddleEl) {
                    const straddleCost = (atmStrike.ce_ltp || 0) + (atmStrike.pe_ltp || 0);
                    atmStraddleEl.textContent = `Straddle: ₹${straddleCost.toFixed(1)} (@${atmStrike.strike})`;
                }
            } else {
                atmIvEl.textContent = '--';
                if (atmStraddleEl) atmStraddleEl.textContent = 'CE + PE Premium';
            }
        }

        // Header Sentiment Badge
        const sentimentBadge = document.getElementById('optionsSentimentBadge');
        if (sentimentBadge) {
            if (data.sentiment) {
                sentimentBadge.style.display = 'inline-block';
                sentimentBadge.textContent = data.sentiment;
                if (data.sentiment.includes('BULLISH')) {
                    sentimentBadge.style.background = 'rgba(16,185,129,0.15)';
                    sentimentBadge.style.color = '#34d399';
                    sentimentBadge.style.border = '1px solid rgba(16,185,129,0.3)';
                } else if (data.sentiment.includes('BEARISH')) {
                    sentimentBadge.style.background = 'rgba(239,68,68,0.15)';
                    sentimentBadge.style.color = '#f87171';
                    sentimentBadge.style.border = '1px solid rgba(239,68,68,0.3)';
                } else {
                    sentimentBadge.style.background = 'rgba(245,158,11,0.15)';
                    sentimentBadge.style.color = '#fbbf24';
                    sentimentBadge.style.border = '1px solid rgba(245,158,11,0.3)';
                }
            } else {
                sentimentBadge.style.display = 'none';
            }
        }
    };

    /**
     * Render Open Interest Distribution Bar Chart using Chart.js
     */
    app.renderOiDistributionChart = function (data) {
        const ctx = document.getElementById('optionsOiChart');
        if (!ctx) return;

        const strikes = data.strikes || [];
        if (strikes.length === 0) {
            if (app._optionsChart) {
                app._optionsChart.destroy();
                app._optionsChart = null;
            }
            return;
        }

        const labels = strikes.map(s => s.strike);
        const callOiData = strikes.map(s => s.ce_oi || 0);
        const putOiData = strikes.map(s => s.pe_oi || 0);

        if (app._optionsChart) {
            app._optionsChart.destroy();
        }

        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded on page.');
            return;
        }

        app._optionsChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Call OI (Resistance)',
                        data: callOiData,
                        backgroundColor: 'rgba(239, 68, 68, 0.75)',
                        borderColor: '#ef4444',
                        borderWidth: 1,
                        borderRadius: 3,
                    },
                    {
                        label: 'Put OI (Support)',
                        data: putOiData,
                        backgroundColor: 'rgba(16, 185, 129, 0.75)',
                        borderColor: '#10b981',
                        borderWidth: 1,
                        borderRadius: 3,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(10, 10, 10, 0.9)',
                        titleColor: '#fbbf24',
                        titleFont: { weight: 'bold' },
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        callbacks: {
                            label: function (context) {
                                const val = context.parsed.y || 0;
                                const formatted = val >= 100000 ? (val / 100000).toFixed(2) + ' L' : val.toLocaleString();
                                return `${context.dataset.label}: ${formatted} (${val.toLocaleString()} contracts)`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)'
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: { size: 10, family: 'var(--font-mono)' }
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)'
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: { size: 10, family: 'var(--font-mono)' },
                            callback: function (val) {
                                if (val >= 10000000) return (val / 10000000) + ' Cr';
                                if (val >= 100000) return (val / 100000) + ' L';
                                if (val >= 1000) return (val / 1000) + 'k';
                                return val;
                            }
                        }
                    }
                }
            }
        });
    };

    /**
     * Render the comprehensive Strike Tree Table
     */
    app.renderStrikeTreeTable = function (data) {
        const tbody = document.getElementById('optionsStrikeTreeBody');
        if (!tbody) return;

        const strikes = data.strikes || [];
        if (strikes.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="11" style="text-align:center;padding:2.5rem;color:var(--text-secondary);">
                        No option strikes available for the selected parameters.
                    </td>
                </tr>
            `;
            return;
        }

        const formatQty = (val) => {
            if (!val) return '-';
            const num = Number(val);
            if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
            if (num >= 1000) return (num / 1000).toFixed(1) + 'k';
            return num.toLocaleString('en-IN');
        };

        const formatDelta = (delta) => {
            if (!delta || delta === 0) return '<span style="color:#71717a;">0</span>';
            const num = Number(delta);
            const formatted = formatQty(Math.abs(num));
            if (num > 0) {
                return `<span style="color:#34d399;">+${formatted}</span>`;
            }
            return `<span style="color:#f87171;">-${formatted}</span>`;
        };

        const formatPrice = (val) => {
            if (val === null || val === undefined) return '-';
            return Number(val).toFixed(2);
        };

        const formatIv = (val) => {
            if (!val || val === 0) return '-';
            return Number(val).toFixed(1) + '%';
        };

        let html = '';
        strikes.forEach(s => {
            const isAtm = !!s.is_atm;
            const ceItm = !!s.ce_itm;
            const peItm = !!s.pe_itm;

            // Row styling
            let rowBg = 'transparent';
            let strikeStyle = 'color: #ededed;';

            if (isAtm) {
                rowBg = 'rgba(245, 158, 11, 0.12)';
                strikeStyle = 'color: #fbbf24; font-weight: 800; border-left: 2px solid #fbbf24; border-right: 2px solid #fbbf24;';
            }

            const ceBg = ceItm ? 'background:rgba(239, 68, 68, 0.06);' : '';
            const peBg = peItm ? 'background:rgba(16, 185, 129, 0.06);' : '';

            html += `
                <tr style="background:${rowBg}; border-bottom: 1px solid rgba(255,255,255,0.04);" ${isAtm ? 'id="optionsAtmRow"' : ''}>
                    <!-- CE: OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${ceBg}">${formatQty(s.ce_oi)}</td>
                    <!-- CE: Chg OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${ceBg}">${formatDelta(s.ce_change_oi)}</td>
                    <!-- CE: Volume -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${ceBg}">${formatQty(s.ce_vol)}</td>
                    <!-- CE: IV -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${ceBg}">${formatIv(s.ce_iv)}</td>
                    <!-- CE: LTP -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f87171;border-right:1px solid rgba(255,255,255,0.08);${ceBg}">${formatPrice(s.ce_ltp)}</td>

                    <!-- STRIKE -->
                    <td style="padding:0.35rem 0.5rem;text-align:center;font-family:var(--font-mono);background:#121316;${strikeStyle}">
                        ${s.strike} ${isAtm ? '<span style="font-size:0.65rem;background:#fbbf24;color:#000;padding:0.1rem 0.3rem;border-radius:4px;margin-left:0.2rem;font-weight:bold;">ATM</span>' : ''}
                    </td>

                    <!-- PE: LTP -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#34d399;border-left:1px solid rgba(255,255,255,0.08);${peBg}">${formatPrice(s.pe_ltp)}</td>
                    <!-- PE: IV -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${peBg}">${formatIv(s.pe_iv)}</td>
                    <!-- PE: Volume -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${peBg}">${formatQty(s.pe_vol)}</td>
                    <!-- PE: Chg OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${peBg}">${formatDelta(s.pe_change_oi)}</td>
                    <!-- PE: OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${peBg}">${formatQty(s.pe_oi)}</td>
                </tr>
            `;
        });

        tbody.innerHTML = html;

        // Auto-scroll to ATM row smoothly inside container
        setTimeout(() => {
            const atmRow = document.getElementById('optionsAtmRow');
            if (atmRow) {
                atmRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 150);
    };

    /**
     * Fetch and render multi-day historical snapshots
     */
    app.fetchOptionHistory = async function (symbol = null) {
        const sym = (symbol || app._optionsSymbol || 'NIFTY').trim().toUpperCase().replace('.NS', '');
        const tbody = document.getElementById('optionsHistoryBody');
        if (!tbody) return;

        try {
            const res = await fetch(`/api/v1/options/history?symbol=${encodeURIComponent(sym)}&limit=25`);
            if (!res.ok) throw new Error('Failed to fetch history');

            const payload = await res.json();
            const history = payload.history || [];

            if (history.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="10" style="text-align:center;padding:1.5rem;color:var(--text-secondary);">
                            No historical snapshots recorded yet for ${sym}. Snapshots are saved automatically during market updates.
                        </td>
                    </tr>
                `;
                return;
            }

            const formatQty = (qty) => {
                if (!qty) return '--';
                const val = Number(qty);
                if (val >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
                if (val >= 100000) return (val / 100000).toFixed(2) + ' L';
                return val.toLocaleString('en-IN');
            };

            let html = '';
            history.forEach(h => {
                const sentimentColor = (h.sentiment || '').includes('BULLISH') ? '#34d399' :
                                       (h.sentiment || '').includes('BEARISH') ? '#f87171' : '#fbbf24';
                html += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
                        <td style="font-family:var(--font-mono);font-weight:600;color:var(--text-primary);">${h.as_of_date || '--'}</td>
                        <td style="font-family:var(--font-mono);">${h.spot_price != null ? Number(h.spot_price).toFixed(2) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#fbbf24;font-weight:700;">${h.max_pain_strike != null ? Number(h.max_pain_strike).toFixed(0) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#38bdf8;">${h.pcr_oi != null ? Number(h.pcr_oi).toFixed(2) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#a855f7;">${h.pcr_volume != null ? Number(h.pcr_volume).toFixed(2) : '--'}</td>
                        <td><span style="color:${sentimentColor};font-weight:700;font-size:0.75rem;">${h.sentiment || '--'}</span></td>
                        <td style="font-family:var(--font-mono);color:#f87171;">${h.resistance_strike != null ? Number(h.resistance_strike).toFixed(0) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#34d399;">${h.support_strike != null ? Number(h.support_strike).toFixed(0) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:var(--text-secondary);">${formatQty(h.call_oi_total)}</td>
                        <td style="font-family:var(--font-mono);color:var(--text-secondary);">${formatQty(h.put_oi_total)}</td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;

        } catch (e) {
            console.error('Error fetching options history:', e);
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" style="text-align:center;padding:1.5rem;color:#f87171;">
                        Could not load historical snapshots: ${e.message}
                    </td>
                </tr>
            `;
        }
    };

    // Auto-initialize when loaded
    if (document.getElementById('tab-options')) {
        app.loadOptionChain(false);
        app.loadOptionsChartIntelligence(false);

        // Auto-refresh timer every 15 seconds during active usage
        if (app._optionsPollTimer) clearInterval(app._optionsPollTimer);
        app._optionsPollTimer = setInterval(() => {
            const tab = document.getElementById('tab-options');
            if (tab && !tab.classList.contains('hidden') && tab.style.display !== 'none') {
                app.loadOptionsChartIntelligence(false, true);
            }
        }, 15000);
    }

})(window);
