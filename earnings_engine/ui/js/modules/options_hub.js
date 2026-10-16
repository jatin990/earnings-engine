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
    app._optionsChartMode = 'gex'; // Default: Mode 1 - Dealer Gamma GEX Profile
    app._optionsChainData = null;  // Cached latest option chain analysis
    app._optionsSetupsHistory = [];
    app._optionsSetupsFilter = 'ALL';
    app._optionsLayers = {
        vwap: true,
        ob: true,
        derivatives: true,
        orb: true,
        trendlines: true,
    };

    app._optionsChart = null; // Chart.js instance for multi-mode derivatives visualizer
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
    app._avgVolume = 1;
    app._crosshairBound = false;

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
    app.formatIST = formatIST;

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
                    statusBanner.innerHTML = `⚠️ <strong>${symbol} is not eligible for NSE/BSE Derivatives (F&amp;O)</strong>. Only official NSE and BSE index &amp; stock derivatives are supported.`;
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

            // Cache option chain data
            app._optionsChainData = data;

            // Render KPI cards & Radar HUD
            app.renderOptionKpiCards(data);

            // Render Tactical GEX Market Briefing & Action Directive Header Bar
            app.renderGexMarketBriefing(data);

            // Render Multi-Mode Open Interest / GEX / Delta / IV Chart
            app.renderOiDistributionChart(data);

            // Render Strike Tree Table with Greek & GEX metrics
            app.renderStrikeTreeTable(data);

            // Also load tracked setups and multi-day positioning history asynchronously
            app.fetchOptionHistory(symbol);
            app.fetchOptionSetupsHistory(symbol);

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
            height: 560,
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
                scaleMargins: { top: 0.08, bottom: 0.15 },
            },
            localization: {
                locale: 'en-IN',
                dateFormat: 'dd MMM yyyy',
                timeFormatter: (time) => formatIST(time, { includeTime: true, includeYear: true, suffix: true }),
                dateFormatter: (time) => formatIST(time, { includeTime: false, includeYear: true, suffix: true }),
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
                timeVisible: true,
                secondsVisible: false,
                tickMarkFormatter: (time, tickMarkType) => {
                    return formatIST(time, { includeTime: true, includeYear: false, suffix: true });
                },
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

        // Subscribe to crosshair movement for Sticky Hover Inspector HUD
        chart.subscribeCrosshairMove(app.handleOptionsCrosshairMove);

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
     * Crosshair move handler for Sticky Real-time Hover Inspector HUD bar
     */
    app.handleOptionsCrosshairMove = function (param) {
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

        if (param && param.time && app._candleSeries && param.seriesData) {
            candle = param.seriesData.get(app._candleSeries);
            timeSec = typeof param.time === 'number' ? param.time : (param.time.year ? new Date(Date.UTC(param.time.year, param.time.month - 1, param.time.day)).getTime() / 1000 : null);
        }

        // Fallback to latest candle if cursor left canvas
        if (!candle && app._smartChartData && app._smartChartData.candles && app._smartChartData.candles.length > 0) {
            const candles = app._smartChartData.candles;
            candle = candles[candles.length - 1];
            timeSec = candle.time;
        }

        if (!candle) {
            if (inspectTime) inspectTime.textContent = 'Cursor: --';
            return;
        }

        const timeStr = formatIST(timeSec || param.time || Date.now() / 1000, { includeTime: true, suffix: true });

        if (inspectTime) inspectTime.textContent = timeStr;
        if (inspectOpen) inspectOpen.textContent = `₹${candle.open !== undefined ? Number(candle.open).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (inspectHigh) inspectHigh.textContent = `₹${candle.high !== undefined ? Number(candle.high).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (inspectLow) inspectLow.textContent = `₹${candle.low !== undefined ? Number(candle.low).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;
        if (inspectClose) inspectClose.textContent = `₹${candle.close !== undefined ? Number(candle.close).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}`;

        const tr = Math.max((candle.high || 0) - (candle.low || 0), 0);
        if (inspectTr) inspectTr.textContent = `₹${tr.toFixed(2)}`;

        // Volume surge multiple
        const volItem = app._volumeSeries && param.seriesData ? param.seriesData.get(app._volumeSeries) : null;
        const v = volItem ? Number(volItem.value || 0) : Number(candle.volume || 0);
        const avgVol = app._avgVolume || 1;
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
        if (inspectZoneDetails && app._smartChartData) {
            const data = app._smartChartData;
            const deriv = data.derivatives_levels || {};
            const smartMoney = data.smart_money || {};
            const ind = data.indicators || {};
            let matchedZone = null;
            let zoneColor = '#eab308';

            let hoverPrice = candle.close;
            if (param.point && param.point.y !== undefined && app._candleSeries.coordinateToPrice) {
                const p = app._candleSeries.coordinateToPrice(param.point.y);
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
    };

    /**
     * Load full candlestick & quant intelligence from backend API
     */
    app.loadOptionsChartIntelligence = async function (forceRefresh = false, isBackground = false) {
        const symbol = app._optionsSymbol || 'NIFTY';
        const tf = app._optionsTimeframe || '5m';
        const loadingEl = document.getElementById('optionsSmartChartLoading');
        const dot = document.getElementById('optLivePulseDot');
        const timeEl = document.getElementById('optChartTimestamp');

        if (loadingEl && !isBackground) {
            loadingEl.style.display = 'flex';
            loadingEl.style.pointerEvents = 'auto';
        }

        try {
            const url = `/api/v1/options/chart-intelligence?symbol=${encodeURIComponent(symbol)}&interval=${tf}&force_refresh=${forceRefresh}`;
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();
            app._smartChartData = data;

            // Compute 20-period moving average volume for surge ratios
            if (data.candles && data.candles.length > 0) {
                const vols = data.candles.map(c => c.volume || 0);
                const recent = vols.slice(-20);
                const sum = recent.reduce((a, b) => a + b, 0);
                app._avgVolume = Math.max(Math.round(sum / Math.max(recent.length, 1)), 1);
            }

            // Update timestamp badge in IST
            if (timeEl) {
                const ts = data.timestamp ? formatIST(data.timestamp, { includeTime: true, suffix: true }) : formatIST(Date.now() / 1000, { includeTime: true, suffix: true });
                timeEl.textContent = `As of ${ts}`;
            }

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
                loadingEl.style.pointerEvents = 'none';
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
     * Switch Option Chart Visualization Mode (GEX, OI, NET_DELTA, IV)
     */
    app.setOptionChartMode = function (mode) {
        const cleanMode = (mode || 'gex').toLowerCase();
        app._optionsChartMode = cleanMode;

        const modeMap = {
            'gex': 'btnOptModeGex',
            'oi': 'btnOptModeOi',
            'net_delta': 'btnOptModeNetDelta',
            'iv': 'btnOptModeIv'
        };

        ['btnOptModeGex', 'btnOptModeOi', 'btnOptModeNetDelta', 'btnOptModeIv'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.classList.remove('active');
                btn.style.background = 'transparent';
                btn.style.color = '#94a3b8';
            }
        });

        const activeBtnId = modeMap[cleanMode] || 'btnOptModeGex';
        const activeBtn = document.getElementById(activeBtnId);
        if (activeBtn) {
            activeBtn.classList.add('active');
            activeBtn.style.background = cleanMode === 'gex' ? '#a855f7' : '#38bdf8';
            activeBtn.style.color = cleanMode === 'gex' ? '#ffffff' : '#000000';
        }

        const descEl = document.getElementById('optionsChartModeDescription');
        if (descEl) {
            if (cleanMode === 'gex') {
                descEl.textContent = 'Dealer Gamma Exposure (GEX) profile per strike in ₹ Lakhs. Green (Call GEX) = Positive Gamma (vol dampening), Red (Put GEX) = Negative Gamma (vol acceleration). Blue dashed line = Cumulative Net Gamma.';
            } else if (cleanMode === 'oi') {
                descEl.textContent = 'Total Open Interest & intraday OI change (solid = total OI, semi-transparent = change in OI) across Call and Put strikes.';
            } else if (cleanMode === 'net_delta') {
                descEl.textContent = 'Net OI Delta (PE ΔOI - CE ΔOI). Green bars indicate net Put writer accumulation (support building), Red bars indicate net Call writer accumulation (resistance building).';
            } else if (cleanMode === 'iv') {
                descEl.textContent = 'Implied Volatility (IV) Smile & Skew curve for CE and PE across the option ladder with ATM marker.';
            }
        }

        if (app._optionsChainData) {
            app.renderOiDistributionChart(app._optionsChainData);
        }
    };

    /**
     * Render the 7 KPI Summary Cards + Gamma Radar HUD
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

        // Gamma Regime Badge
        const gammaRegimeEl = document.getElementById('optKpiGammaRegimeBadge');
        if (gammaRegimeEl) {
            const regime = data.gamma_regime || 'NEUTRAL';
            if (regime === 'POSITIVE_GAMMA') {
                gammaRegimeEl.textContent = '🛡️ POSITIVE GAMMA (Vol Dampening / Pin)';
                gammaRegimeEl.style.background = 'rgba(16,185,129,0.15)';
                gammaRegimeEl.style.color = '#34d399';
                gammaRegimeEl.style.border = '1px solid rgba(16,185,129,0.3)';
            } else if (regime === 'NEGATIVE_GAMMA') {
                gammaRegimeEl.textContent = '⚡ NEGATIVE GAMMA (Vol Acceleration / Squeeze)';
                gammaRegimeEl.style.background = 'rgba(239,68,68,0.15)';
                gammaRegimeEl.style.color = '#f87171';
                gammaRegimeEl.style.border = '1px solid rgba(239,68,68,0.3)';
            } else {
                gammaRegimeEl.textContent = '⚖️ NEUTRAL GAMMA';
                gammaRegimeEl.style.background = 'rgba(245,158,11,0.15)';
                gammaRegimeEl.style.color = '#fbbf24';
                gammaRegimeEl.style.border = '1px solid rgba(245,158,11,0.3)';
            }
        }

        // Gamma Flip & Net GEX
        const gammaFlipEl = document.getElementById('optKpiGammaFlip');
        if (gammaFlipEl) {
            gammaFlipEl.textContent = data.gamma_flip_strike ? `Flip Strike: ${formatNum(data.gamma_flip_strike, 0)}` : 'Flip Strike: --';
        }

        const netGexEl = document.getElementById('optKpiNetGex');
        if (netGexEl) {
            const netGex = data.total_net_gex || 0;
            const sign = netGex >= 0 ? '+' : '';
            netGexEl.textContent = `Net GEX: ${sign}₹${netGex.toFixed(1)}L`;
            netGexEl.style.color = netGex >= 0 ? '#34d399' : '#f87171';
        }

        // India VIX Badge
        const vixBadge = document.getElementById('optKpiVixBadge');
        if (vixBadge) {
            vixBadge.textContent = data.vix != null ? `INDIA VIX: ${Number(data.vix).toFixed(2)}` : 'INDIA VIX: --';
        }

        // Expected Move (±1σ) Badge
        const expMoveBadge = document.getElementById('optKpiExpectedMoveBadge');
        const expMove = data.expected_move || {};
        if (expMoveBadge) {
            if (expMove.range_1sigma != null && expMove.upper_1sigma != null && expMove.lower_1sigma != null) {
                expMoveBadge.textContent = `Exp Move (±1σ): ±${Number(expMove.range_1sigma).toFixed(1)} (${Number(expMove.lower_1sigma).toFixed(0)} - ${Number(expMove.upper_1sigma).toFixed(0)})`;
            } else {
                expMoveBadge.textContent = 'Exp Move: --';
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

        // Render Algorithmic Setups
        app.renderOptionMarketSetups(data);
    };

    /**
     * Render Algorithmic Derivatives Setups in Options Hub
     */
    app.renderOptionMarketSetups = function (data) {
        const container = document.getElementById('optAlgorithmicSetupsContainer');
        const countBadge = document.getElementById('optSetupsCountBadge');
        if (!container) return;

        const setups = data.setups || [];
        if (countBadge) {
            countBadge.textContent = `${setups.length} ACTIVE`;
            countBadge.style.background = setups.length > 0 ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255, 255, 255, 0.05)';
            countBadge.style.color = setups.length > 0 ? '#38bdf8' : 'var(--text-secondary)';
        }

        if (setups.length === 0) {
            container.innerHTML = `
                <div style="grid-column: 1 / -1; padding: 1.5rem; text-align: center; color: var(--text-secondary); background: rgba(255,255,255,0.02); border-radius: 8px; border: 1px dashed rgba(255,255,255,0.08);">
                    No high-probability derivative trigger conditions detected for current strike matrix.
                </div>
            `;
            return;
        }

        let html = '';
        setups.forEach(s => {
            const isBullish = s.direction === 'BULLISH';
            const isBearish = s.direction === 'BEARISH';
            const dirColor = isBullish ? '#34d399' : (isBearish ? '#f87171' : '#fbbf24');
            const dirBg = isBullish ? 'rgba(16, 185, 129, 0.15)' : (isBearish ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)');
            const confBadge = s.confidence === 'HIGH' ? 'background:rgba(16,185,129,0.2);color:#34d399;' : 'background:rgba(245,158,11,0.2);color:#fbbf24;';

            html += `
                <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 1rem; display: flex; flex-direction: column; gap: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 700; font-size: 0.85rem; color: #fff;">${s.title}</span>
                        <div style="display: flex; gap: 0.35rem;">
                            <span style="font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.4rem; border-radius: 4px; ${confBadge}">${s.confidence} CONFIDENCE</span>
                            <span style="font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.4rem; border-radius: 4px; background:${dirBg}; color:${dirColor};">${s.direction}</span>
                        </div>
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary); line-height: 1.4;">
                        ${s.description}
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; margin-top: 0.35rem; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05); font-family: var(--font-mono); font-size: 0.72rem;">
                        <div><span style="color:var(--text-secondary);font-size:0.65rem;display:block;">ENTRY</span><span style="font-weight:700;color:#fff;">${s.trigger_spot != null ? s.trigger_spot.toFixed(1) : '--'}</span></div>
                        <div><span style="color:var(--text-secondary);font-size:0.65rem;display:block;">TARGET 1</span><span style="font-weight:700;color:#34d399;">${s.target_1 != null ? s.target_1.toFixed(1) : '--'}</span></div>
                        <div><span style="color:var(--text-secondary);font-size:0.65rem;display:block;">TARGET 2</span><span style="font-weight:700;color:#34d399;">${s.target_2 != null ? s.target_2.toFixed(1) : '--'}</span></div>
                        <div><span style="color:var(--text-secondary);font-size:0.65rem;display:block;">STOP LOSS</span><span style="font-weight:700;color:#f87171;">${s.stop_loss != null ? s.stop_loss.toFixed(1) : '--'}</span></div>
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    };

    /**
     * Render the Tactical GEX Market Briefing & Action Directive Header Bar
     */
    app.renderGexMarketBriefing = function (data) {
        const briefingEl = document.getElementById('optGexMarketBriefing');
        if (!briefingEl) return;

        const gexSummary = data && data.gex_summary ? data.gex_summary : null;
        if (!gexSummary || gexSummary.action_type === 'UNAVAILABLE') {
            briefingEl.style.display = 'none';
            return;
        }

        briefingEl.style.display = 'block';

        const regimeBadge = document.getElementById('optGexRegimeBadge');
        const textureHeadline = document.getElementById('optGexTextureHeadline');
        const narrative = document.getElementById('optGexNarrative');
        const rangeSpread = document.getElementById('optGexRangeSpread');
        const rangeSupport = document.getElementById('optGexRangeSupport');
        const rangeResistance = document.getElementById('optGexRangeResistance');
        const straddleBounds = document.getElementById('optGexStraddleBounds');
        const flipLevel = document.getElementById('optGexFlipLevel');
        const actionBadge = document.getElementById('optGexActionBadge');
        const actionHeadline = document.getElementById('optGexActionHeadline');
        const actionDetails = document.getElementById('optGexActionDetails');

        // 1. Market Texture & Regime
        if (regimeBadge) {
            regimeBadge.textContent = gexSummary.texture_badge || gexSummary.gamma_regime || 'NEUTRAL';
            if (gexSummary.gamma_regime === 'POSITIVE_GAMMA') {
                regimeBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                regimeBadge.style.color = '#34d399';
                regimeBadge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
            } else if (gexSummary.gamma_regime === 'NEGATIVE_GAMMA') {
                regimeBadge.style.background = 'rgba(239, 68, 68, 0.15)';
                regimeBadge.style.color = '#f87171';
                regimeBadge.style.borderColor = 'rgba(239, 68, 68, 0.35)';
            } else {
                regimeBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                regimeBadge.style.color = '#fbbf24';
                regimeBadge.style.borderColor = 'rgba(245, 158, 11, 0.35)';
            }
        }

        if (textureHeadline) {
            textureHeadline.textContent = gexSummary.market_texture || 'Market Consolidation';
        }
        if (narrative) {
            narrative.textContent = gexSummary.narrative || '--';
        }

        // 2. Expected Daily Range
        const expRange = gexSummary.expected_range || {};
        if (rangeSpread) {
            const pts = expRange.spread_points !== undefined && expRange.spread_points !== null ? Number(expRange.spread_points).toFixed(1) : '--';
            const pct = expRange.spread_pct !== undefined && expRange.spread_pct !== null ? Number(expRange.spread_pct).toFixed(2) : '--';
            rangeSpread.textContent = `${pts} pts (${pct}%)`;
        }
        if (rangeSupport) {
            rangeSupport.textContent = expRange.support ? `₹${Number(expRange.support).toLocaleString('en-IN')}` : '--';
        }
        if (rangeResistance) {
            rangeResistance.textContent = expRange.resistance ? `₹${Number(expRange.resistance).toLocaleString('en-IN')}` : '--';
        }
        if (straddleBounds) {
            const low = expRange.lower_1sigma ? `₹${Number(expRange.lower_1sigma).toLocaleString('en-IN')}` : '--';
            const high = expRange.upper_1sigma ? `₹${Number(expRange.upper_1sigma).toLocaleString('en-IN')}` : '--';
            straddleBounds.textContent = `${low} – ${high}`;
        }
        if (flipLevel) {
            flipLevel.textContent = gexSummary.gamma_flip_strike ? `₹${Number(gexSummary.gamma_flip_strike).toLocaleString('en-IN')}` : '--';
        }

        // 3. Action Directive
        if (actionBadge) {
            actionBadge.textContent = gexSummary.action_badge || 'TACTICAL PLAN';
            const theme = gexSummary.action_theme || 'indigo';
            if (theme === 'emerald') {
                actionBadge.style.background = 'rgba(16, 185, 129, 0.2)';
                actionBadge.style.color = '#34d399';
                actionBadge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            } else if (theme === 'rose') {
                actionBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                actionBadge.style.color = '#f87171';
                actionBadge.style.borderColor = 'rgba(239, 68, 68, 0.4)';
            } else {
                actionBadge.style.background = 'rgba(99, 102, 241, 0.2)';
                actionBadge.style.color = '#a5b4fc';
                actionBadge.style.borderColor = 'rgba(99, 102, 241, 0.4)';
            }
        }
        if (actionHeadline) {
            actionHeadline.textContent = gexSummary.action_headline || '--';
            const theme = gexSummary.action_theme || 'indigo';
            if (theme === 'emerald') {
                actionHeadline.style.color = '#34d399';
            } else if (theme === 'rose') {
                actionHeadline.style.color = '#f87171';
            } else {
                actionHeadline.style.color = '#c7d2fe';
            }
        }
        if (actionDetails) {
            actionDetails.textContent = gexSummary.action_details || '--';
        }
    };

    /**
     * Render Open Interest / Gamma / Net Delta / IV Distribution Chart using Chart.js
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

        if (app._optionsChart) {
            app._optionsChart.destroy();
            app._optionsChart = null;
        }

        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded on page.');
            return;
        }

        const mode = (app._optionsChartMode || 'gex').toLowerCase();
        const labels = strikes.map(s => s.strike);

        let chartConfig = null;

        if (mode === 'gex') {
            // Mode 1: Dealer Gamma Exposure (GEX) Profile (₹ Lakhs)
            const callGexData = strikes.map(s => s.ce_gex || 0);
            const putGexData = strikes.map(s => s.pe_gex || 0);
            const cumGexData = strikes.map(s => s.cum_net_gex || 0);

            chartConfig = {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            type: 'line',
                            label: 'Cumulative Net GEX (₹ Lakhs)',
                            data: cumGexData,
                            borderColor: '#38bdf8',
                            borderWidth: 2,
                            borderDash: [4, 4],
                            fill: false,
                            pointRadius: 2,
                            pointHoverRadius: 5,
                            yAxisID: 'yGex'
                        },
                        {
                            type: 'bar',
                            label: 'Call GEX (+Gamma / Vol Dampening)',
                            data: callGexData,
                            backgroundColor: 'rgba(16, 185, 129, 0.8)',
                            borderColor: '#10b981',
                            borderWidth: 1,
                            borderRadius: 3,
                            yAxisID: 'yGex'
                        },
                        {
                            type: 'bar',
                            label: 'Put GEX (-Gamma / Vol Acceleration)',
                            data: putGexData,
                            backgroundColor: 'rgba(239, 68, 68, 0.8)',
                            borderColor: '#ef4444',
                            borderWidth: 1,
                            borderRadius: 3,
                            yAxisID: 'yGex'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: { color: '#e2e8f0', font: { size: 10 } }
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
                                    const formatted = '₹' + (Math.abs(val)).toFixed(2) + ' Lakhs';
                                    const sign = val >= 0 ? '+' : '-';
                                    return `${context.dataset.label}: ${sign}${formatted}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#a1a1aa', font: { size: 10, family: 'var(--font-mono)' } }
                        },
                        yGex: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: {
                                color: '#a1a1aa',
                                font: { size: 10, family: 'var(--font-mono)' },
                                callback: function (val) {
                                    return '₹' + val.toFixed(0) + 'L';
                                }
                            }
                        }
                    }
                }
            };
        } else if (mode === 'oi') {
            // Mode 2: Total OI & ΔOI
            const callOiData = strikes.map(s => s.ce_oi || 0);
            const callOiChgData = strikes.map(s => s.ce_change_oi || 0);
            const putOiData = strikes.map(s => s.pe_oi || 0);
            const putOiChgData = strikes.map(s => s.pe_change_oi || 0);

            chartConfig = {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Call OI (Total)',
                            data: callOiData,
                            backgroundColor: 'rgba(239, 68, 68, 0.75)',
                            borderColor: '#ef4444',
                            borderWidth: 1,
                            borderRadius: 3
                        },
                        {
                            label: 'Call ΔOI',
                            data: callOiChgData,
                            backgroundColor: 'rgba(239, 68, 68, 0.35)',
                            borderColor: '#f87171',
                            borderWidth: 1,
                            borderRadius: 3
                        },
                        {
                            label: 'Put OI (Total)',
                            data: putOiData,
                            backgroundColor: 'rgba(16, 185, 129, 0.75)',
                            borderColor: '#10b981',
                            borderWidth: 1,
                            borderRadius: 3
                        },
                        {
                            label: 'Put ΔOI',
                            data: putOiChgData,
                            backgroundColor: 'rgba(16, 185, 129, 0.35)',
                            borderColor: '#34d399',
                            borderWidth: 1,
                            borderRadius: 3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: { color: '#e2e8f0', font: { size: 10 } }
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
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#a1a1aa', font: { size: 10, family: 'var(--font-mono)' } }
                        },
                        y: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
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
            };
        } else if (mode === 'net_delta') {
            // Mode 3: Net OI Delta (PE ΔOI - CE ΔOI)
            const netDeltaData = strikes.map(s => (s.pe_change_oi || 0) - (s.ce_change_oi || 0));
            const bgColors = netDeltaData.map(v => v >= 0 ? 'rgba(16, 185, 129, 0.75)' : 'rgba(239, 68, 68, 0.75)');
            const borderColors = netDeltaData.map(v => v >= 0 ? '#10b981' : '#ef4444');

            chartConfig = {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Net OI Delta (PE ΔOI - CE ΔOI)',
                            data: netDeltaData,
                            backgroundColor: bgColors,
                            borderColor: borderColors,
                            borderWidth: 1,
                            borderRadius: 3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(10, 10, 10, 0.9)',
                            titleColor: '#fbbf24',
                            titleFont: { weight: 'bold' },
                            borderColor: 'rgba(255, 255, 255, 0.1)',
                            borderWidth: 1,
                            callbacks: {
                                label: function (context) {
                                    const val = context.parsed.y || 0;
                                    const bias = val >= 0 ? 'Bullish (Net Put Writing)' : 'Bearish (Net Call Writing)';
                                    const formatted = val >= 100000 ? (val / 100000).toFixed(2) + ' L' : val.toLocaleString();
                                    return `Net ΔOI: ${formatted} contracts · ${bias}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#a1a1aa', font: { size: 10, family: 'var(--font-mono)' } }
                        },
                        y: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
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
            };
        } else if (mode === 'iv') {
            // Mode 4: IV Skew & Smile
            const ceIvData = strikes.map(s => s.ce_iv || null);
            const peIvData = strikes.map(s => s.pe_iv || null);

            chartConfig = {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Call IV (%)',
                            data: ceIvData,
                            borderColor: '#f87171',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            borderWidth: 2,
                            pointRadius: 3,
                            tension: 0.3
                        },
                        {
                            label: 'Put IV (%)',
                            data: peIvData,
                            borderColor: '#34d399',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            borderWidth: 2,
                            pointRadius: 3,
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: { color: '#e2e8f0', font: { size: 10 } }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(10, 10, 10, 0.9)',
                            titleColor: '#fbbf24',
                            titleFont: { weight: 'bold' },
                            borderColor: 'rgba(255, 255, 255, 0.1)',
                            borderWidth: 1,
                            callbacks: {
                                label: function (context) {
                                    const val = context.parsed.y;
                                    return val != null ? `${context.dataset.label}: ${val.toFixed(1)}%` : `${context.dataset.label}: N/A`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#a1a1aa', font: { size: 10, family: 'var(--font-mono)' } }
                        },
                        y: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: {
                                color: '#a1a1aa',
                                font: { size: 10, family: 'var(--font-mono)' },
                                callback: function (val) {
                                    return val.toFixed(1) + '%';
                                }
                            }
                        }
                    }
                }
            };
        }

        if (chartConfig) {
            app._optionsChart = new Chart(ctx, chartConfig);
        }
    };

    /**
     * Render the comprehensive Strike Tree Table (13 Columns including Greeks & GEX)
     */
    app.renderStrikeTreeTable = function (data) {
        const tbody = document.getElementById('optionsStrikeTreeBody');
        if (!tbody) return;

        const strikes = data.strikes || [];
        if (strikes.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="13" style="text-align:center;padding:2.5rem;color:var(--text-secondary);">
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

        const formatGreek = (val) => {
            if (val === null || val === undefined || isNaN(val)) return '-';
            return Number(val).toFixed(2);
        };

        const formatGex = (val) => {
            if (val === null || val === undefined || isNaN(val)) return '-';
            const num = Number(val);
            if (num > 0) return `<span style="color:#34d399;">+${num.toFixed(1)}</span>`;
            if (num < 0) return `<span style="color:#f87171;">${num.toFixed(1)}</span>`;
            return `<span style="color:#71717a;">0.0</span>`;
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

            // Net GEX display
            const netGex = s.net_gex_lakhs != null ? Number(s.net_gex_lakhs) : null;
            const netGexBadge = netGex !== null ?
                `<div style="font-size:0.65rem;font-weight:600;color:${netGex >= 0 ? '#38bdf8' : '#f87171'};margin-top:2px;">${netGex >= 0 ? '+' : ''}${netGex.toFixed(1)}L</div>` : '';

            html += `
                <tr style="background:${rowBg}; border-bottom: 1px solid rgba(255,255,255,0.04);" ${isAtm ? 'id="optionsAtmRow"' : ''}>
                    <!-- CE: Delta -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:#c084fc;${ceBg}">${formatGreek(s.ce_delta)}</td>
                    <!-- CE: GEX -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${ceBg}">${formatGex(s.ce_gex_lakhs)}</td>
                    <!-- CE: OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${ceBg}">${formatQty(s.ce_oi)}</td>
                    <!-- CE: Chg OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${ceBg}">${formatDelta(s.ce_change_oi)}</td>
                    <!-- CE: IV -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${ceBg}">${formatIv(s.ce_iv)}</td>
                    <!-- CE: LTP -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f87171;border-right:1px solid rgba(255,255,255,0.08);${ceBg}">${formatPrice(s.ce_ltp)}</td>

                    <!-- STRIKE -->
                    <td style="padding:0.35rem 0.5rem;text-align:center;font-family:var(--font-mono);background:#121316;${strikeStyle}">
                        <div>${s.strike} ${isAtm ? '<span style="font-size:0.65rem;background:#fbbf24;color:#000;padding:0.1rem 0.3rem;border-radius:4px;margin-left:0.2rem;font-weight:bold;">ATM</span>' : ''}</div>
                        ${netGexBadge}
                    </td>

                    <!-- PE: LTP -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#34d399;border-left:1px solid rgba(255,255,255,0.08);${peBg}">${formatPrice(s.pe_ltp)}</td>
                    <!-- PE: IV -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${peBg}">${formatIv(s.pe_iv)}</td>
                    <!-- PE: Chg OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${peBg}">${formatDelta(s.pe_change_oi)}</td>
                    <!-- PE: OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${peBg}">${formatQty(s.pe_oi)}</td>
                    <!-- PE: GEX -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${peBg}">${formatGex(s.pe_gex_lakhs)}</td>
                    <!-- PE: Delta -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:#c084fc;${peBg}">${formatGreek(s.pe_delta)}</td>
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
     * Fetch tracked algorithmic option setups ledger
     */
    app.fetchOptionSetupsHistory = async function (symbol = null) {
        const sym = (symbol || app._optionsSymbol || 'NIFTY').trim().toUpperCase().replace('.NS', '');
        const tbody = document.getElementById('optionsSetupsHistoryBody');
        const badge = document.getElementById('optSetupHistoryCountBadge');
        if (!tbody) return;

        try {
            const res = await fetch(`/api/v1/options/setups/history?symbol=${encodeURIComponent(sym)}&limit=100`);
            if (!res.ok) throw new Error('Failed to fetch setups history');

            const payload = await res.json();
            const setups = payload.setups || [];
            app._optionsSetupsHistory = setups;

            if (badge) {
                badge.innerText = `${setups.length} Setups`;
            }

            app.renderOptionSetupsHistory(setups);

        } catch (e) {
            console.error('Error fetching options setups history:', e);
            tbody.innerHTML = `
                <tr>
                    <td colspan="13" style="text-align:center;padding:1.5rem;color:#f87171;">
                        Could not load tracked setups: ${e.message}
                    </td>
                </tr>
            `;
        }
    };

    /**
     * Filter tracked setups by outcome state
     */
    app.filterOptionsSetups = function (filter) {
        app._optionsSetupsFilter = filter || 'ALL';

        // Update active filter button styling
        const buttons = document.querySelectorAll('.opt-setup-filter-btn');
        buttons.forEach(btn => {
            if (btn.getAttribute('data-filter') === filter) {
                btn.style.background = '#38bdf8';
                btn.style.color = '#000000';
            } else {
                btn.style.background = 'transparent';
                btn.style.color = '#94a3b8';
            }
        });

        const allSetups = app._optionsSetupsHistory || [];
        let filtered = allSetups;
        if (filter === 'ACTIVE') {
            filtered = allSetups.filter(s => s.outcome === 'ACTIVE');
        } else if (filter === 'TARGET1_HIT') {
            filtered = allSetups.filter(s => s.outcome === 'TARGET1_HIT' || s.outcome === 'TARGET2_HIT');
        } else if (filter === 'STOPPED_OUT') {
            filtered = allSetups.filter(s => s.outcome === 'STOPPED_OUT');
        }

        app.renderOptionSetupsHistory(filtered);
    };

    /**
     * Render tracked setups into table
     */
    app.renderOptionSetupsHistory = function (setups) {
        const tbody = document.getElementById('optionsSetupsHistoryBody');
        if (!tbody) return;

        if (!setups || setups.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="13" style="text-align:center;padding:1.5rem;color:var(--text-secondary);">
                        No tracked setups found for this filter.
                    </td>
                </tr>
            `;
            return;
        }

        const formatPrice = (p) => (p != null ? Number(p).toFixed(1) : '--');

        let html = '';
        setups.forEach(s => {
            const isBull = (s.direction || '').toUpperCase() === 'BULLISH';
            const isBear = (s.direction || '').toUpperCase() === 'BEARISH';
            const biasBg = isBull ? 'rgba(16,185,129,0.15)' : isBear ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)';
            const biasColor = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';

            // Outcome badge
            let outcomeBg = 'rgba(56,189,248,0.15)';
            let outcomeColor = '#38bdf8';
            let outcomeLabel = s.outcome || 'ACTIVE';

            if (s.outcome === 'TARGET2_HIT') {
                outcomeBg = 'rgba(16,185,129,0.2)';
                outcomeColor = '#34d399';
                outcomeLabel = '🎯 Target 2 Hit';
            } else if (s.outcome === 'TARGET1_HIT') {
                outcomeBg = 'rgba(16,185,129,0.15)';
                outcomeColor = '#34d399';
                outcomeLabel = '🎯 Target 1 Hit';
            } else if (s.outcome === 'STOPPED_OUT') {
                outcomeBg = 'rgba(239,68,68,0.2)';
                outcomeColor = '#f87171';
                outcomeLabel = '🛑 Stopped Out';
            } else if (s.outcome === 'ACTIVE') {
                outcomeBg = 'rgba(56,189,248,0.15)';
                outcomeColor = '#38bdf8';
                outcomeLabel = '⚡ Active';
            }

            // Calculate Spot PnL %
            const trigger = s.trigger_spot != null ? Number(s.trigger_spot) : null;
            const currentSpot = app._optionsChainData?.spot_price || (s.outcome === 'STOPPED_OUT' ? s.stop_loss : trigger);
            let pnlStr = '--';
            let pnlColor = 'var(--text-secondary)';

            if (trigger && currentSpot) {
                let diffPct = 0;
                if (isBull) {
                    diffPct = ((currentSpot - trigger) / trigger) * 100;
                } else if (isBear) {
                    diffPct = ((trigger - currentSpot) / trigger) * 100;
                }
                const sign = diffPct >= 0 ? '+' : '';
                pnlStr = `${sign}${diffPct.toFixed(2)}%`;
                pnlColor = diffPct >= 0 ? '#34d399' : '#f87171';
            }

            // Entry timestamp formatting
            const dateStr = s.entry_time || s.created_at || '--';

            html += `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <td style="font-family:var(--font-mono);font-size:0.75rem;color:var(--text-secondary);white-space:nowrap;">${dateStr}</td>
                    <td style="font-family:var(--font-mono);font-weight:700;color:var(--text-primary);">${s.symbol || '--'}</td>
                    <td style="font-weight:600;color:#f1f5f9;">${s.setup_type || '--'}</td>
                    <td>
                        <span style="background:${biasBg};color:${biasColor};padding:0.15rem 0.45rem;border-radius:4px;font-weight:700;font-size:0.72rem;">
                            ${s.direction || '--'}
                        </span>
                    </td>
                    <td style="font-family:var(--font-mono);color:var(--text-primary);">${formatPrice(s.trigger_spot)}</td>
                    <td style="font-family:var(--font-mono);color:#f87171;">${formatPrice(s.stop_loss)}</td>
                    <td style="font-family:var(--font-mono);color:#34d399;">${formatPrice(s.target_1)}</td>
                    <td style="font-family:var(--font-mono);color:#34d399;font-weight:700;">${formatPrice(s.target_2)}</td>
                    <td style="font-family:var(--font-mono);color:#38bdf8;">1:2.0</td>
                    <td style="font-family:var(--font-mono);color:var(--text-secondary);">${formatPrice(s.trigger_spot)}</td>
                    <td style="font-family:var(--font-mono);">${formatPrice(currentSpot)}</td>
                    <td style="font-family:var(--font-mono);font-weight:700;color:${pnlColor};">${pnlStr}</td>
                    <td style="text-align:center;">
                        <span style="background:${outcomeBg};color:${outcomeColor};padding:0.18rem 0.5rem;border-radius:4px;font-weight:700;font-size:0.72rem;display:inline-block;white-space:nowrap;">
                            ${outcomeLabel}
                        </span>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    };

    /**
     * Trigger live evaluation of active setups against current spot price
     */
    app.evaluateOptionSetups = async function () {
        const sym = (app._optionsSymbol || 'NIFTY').trim().toUpperCase().replace('.NS', '');
        const currentSpot = app._optionsChainData?.spot_price;
        try {
            let url = `/api/v1/options/setups/evaluate?symbol=${encodeURIComponent(sym)}`;
            if (currentSpot) url += `&current_spot=${currentSpot}`;

            const res = await fetch(url, { method: 'POST' });
            if (!res.ok) throw new Error('Evaluation request failed');

            const payload = await res.json();
            const count = payload.evaluated_count || 0;

            // Refresh table
            await app.fetchOptionSetupsHistory(sym);

            if (typeof app.showToast === 'function') {
                app.showToast(`Evaluated ${count} active setups for ${sym}`, 'success');
            }
        } catch (e) {
            console.error('Error evaluating options setups:', e);
            if (typeof app.showToast === 'function') {
                app.showToast(`Evaluation failed: ${e.message}`, 'error');
            }
        }
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

    /**
     * Interactive 6-Slide Options Guide Carousel Modal Controllers
     */
    app._optionsGuideSlide = 0;

    app.openOptionsGuideModal = function () {
        const modal = document.getElementById('optionsGuideModal');
        if (!modal) return;
        modal.style.display = 'flex';
        app.goToOptionsGuideSlide(app._optionsGuideSlide || 0);
    };

    app.closeOptionsGuideModal = function () {
        const modal = document.getElementById('optionsGuideModal');
        if (modal) modal.style.display = 'none';
    };

    app.goToOptionsGuideSlide = function (slideIndex) {
        const idx = Math.max(0, Math.min(5, parseInt(slideIndex, 10) || 0));
        app._optionsGuideSlide = idx;

        const slides = document.querySelectorAll('#optionsGuideModal .opt-guide-slide');
        slides.forEach((slide) => {
            const sIdx = parseInt(slide.getAttribute('data-slide'), 10);
            slide.style.display = sIdx === idx ? 'block' : 'none';
        });

        const dots = document.querySelectorAll('#optionsGuideModal .opt-guide-dot');
        dots.forEach((dot, dIdx) => {
            if (dIdx === idx) {
                dot.classList.add('active');
                dot.style.width = '10px';
                dot.style.height = '10px';
                dot.style.background = '#c084fc';
            } else {
                dot.classList.remove('active');
                dot.style.width = '8px';
                dot.style.height = '8px';
                dot.style.background = 'rgba(255,255,255,0.2)';
            }
        });

        const prevBtn = document.getElementById('optGuidePrevBtn');
        if (prevBtn) {
            if (idx === 0) {
                prevBtn.style.opacity = '0.35';
                prevBtn.style.pointerEvents = 'none';
            } else {
                prevBtn.style.opacity = '1';
                prevBtn.style.pointerEvents = 'auto';
            }
        }

        const nextBtn = document.getElementById('optGuideNextBtn');
        if (nextBtn) {
            if (idx === 5) {
                nextBtn.innerHTML = 'Got it! 🚀';
                nextBtn.style.background = '#34d399';
                nextBtn.style.borderColor = '#34d399';
                nextBtn.style.color = '#000000';
            } else {
                nextBtn.innerHTML = 'Next &rarr;';
                nextBtn.style.background = '#c084fc';
                nextBtn.style.borderColor = '#c084fc';
                nextBtn.style.color = '#000000';
            }
        }

        const container = document.getElementById('optionsGuideSlideContainer');
        if (container) container.scrollTop = 0;
    };

    app.prevOptionsGuideSlide = function () {
        if (app._optionsGuideSlide > 0) {
            app.goToOptionsGuideSlide(app._optionsGuideSlide - 1);
        }
    };

    app.nextOptionsGuideSlide = function () {
        if (app._optionsGuideSlide < 5) {
            app.goToOptionsGuideSlide(app._optionsGuideSlide + 1);
        } else {
            app.closeOptionsGuideModal();
        }
    };

    // Close options guide modal when clicking outside dialog container or pressing Esc
    const guideModalEl = document.getElementById('optionsGuideModal');
    if (guideModalEl) {
        guideModalEl.addEventListener('click', function (e) {
            if (e.target === guideModalEl) {
                app.closeOptionsGuideModal();
            }
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('optionsGuideModal');
            if (modal && modal.style.display !== 'none') {
                app.closeOptionsGuideModal();
            }
        }
    });

    /**
     * Entry point for tab activation from dashboard.js
     */
    app.initOptionsHub = function () {
        app.loadOptionChain(false);
        app.loadOptionsChartIntelligence(false);
        setTimeout(() => {
            if (app._smartChart) {
                const container = document.getElementById('optionsSmartChartCanvas');
                if (container && container.clientWidth > 0) {
                    app._smartChart.applyOptions({
                        width: container.clientWidth,
                        height: 560
                    });
                    app._smartChart.timeScale().fitContent();
                }
            }
        }, 100);
    };

    // Auto-initialize when loaded
    if (document.getElementById('tab-options')) {
        app.initOptionsHub();

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
