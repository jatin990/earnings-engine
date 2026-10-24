/**
 * Nexus Breakout Radar - Candlestick & Lightweight Charts Engine
 * Manages TradingView Lightweight Charts lifecycle, SMA 20/50 technical overlays,
 * execution price lines (Trigger, Target, SL), infinite candle scrollback,
 * drawer height/width resizers, and crosshair HUD telemetry.
 */
(function() {
    'use strict';

    window.app = window.app || {};
    const app = window.app;
    const API_BASE = window.API_BASE || '';

    function formatTradingViewSymbol(sym) {
        if (!sym) return 'BSE:SENSEX';
        const clean = String(sym).trim().toUpperCase();
        if (clean === '^BSESN' || clean === 'SENSEX' || clean === 'BSE:SENSEX') return 'BSE:SENSEX';
        if (clean === '^NSEI' || clean === 'NIFTY' || clean === 'NIFTY50' || clean === 'NIFTY 50') return 'NSE:NIFTY';
        if (clean === '^NSEBANK' || clean === 'BANKNIFTY' || clean === 'NIFTYBANK') return 'NSE:BANKNIFTY';
        if (clean === '^CNX500' || clean === 'NIFTY500') return 'NSE:NIFTY500';
        if (clean === '^GSPC' || clean === 'SPX' || clean === 'S&P 500' || clean === 'S&P500') return 'SP:SPX';
        if (clean === '^NDX' || clean === 'NDX') return 'NASDAQ:NDX';
        if (clean === '^DJI' || clean === 'DJI') return 'DJ:DJI';
        if (clean.includes(':')) return clean;
        if (clean.endsWith('.BO')) return 'BSE:' + clean.slice(0, -3);
        if (clean.endsWith('.NS')) return 'BSE:' + clean.slice(0, -3);
        const knownUSTickers = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'GOOG', 'META', 'TSLA', 'SPY', 'QQQ', 'AMD', 'INTC', 'NFLX', 'BRK.B', 'JNJ', 'JPM', 'V', 'PG', 'UNH', 'HD', 'MA', 'DIS'];
        if (knownUSTickers.includes(clean)) return clean;
        return 'BSE:' + clean;
    }

    app.setBreakoutDrawerWidth = function(width) {
        const drawer = document.getElementById('breakoutInspectorDrawer');
        if (!drawer) return;
        const wStr = typeof width === 'number' ? `${width}px` : String(width);
        drawer.style.width = wStr;
        try {
            localStorage.setItem('breakout_inspector_drawer_width', wStr);
        } catch (e) {}
        if (app.resizeBreakoutChart) {
            setTimeout(app.resizeBreakoutChart, 50);
        }
    };

    app.setBreakoutChartHeight = function(height) {
        const wrap = document.getElementById('bkInspLightweightChartWrap');
        const tvWrap = document.getElementById('bkInspTradingViewContainer');
        const maxBtn = document.getElementById('bkInspChartMaxBtn');
        const h50Btn = document.getElementById('bkChartH50Btn');
        const h70Btn = document.getElementById('bkChartH70Btn');
        const h85Btn = document.getElementById('bkChartH85Btn');
        const h380Btn = document.getElementById('bkChartH380Btn');
        const h480Btn = document.getElementById('bkChartH480Btn');
        const h620Btn = document.getElementById('bkChartH620Btn');

        const hStr = typeof height === 'number' ? `${height}px` : String(height);
        if (wrap) wrap.style.height = hStr;
        if (tvWrap) tvWrap.style.height = hStr;

        [h50Btn, h70Btn, h85Btn, h380Btn, h480Btn, h620Btn].forEach(b => {
            if (b) {
                b.style.background = 'transparent';
                b.style.color = '#94a3b8';
                b.style.fontWeight = '400';
            }
        });

        if ((hStr.includes('50vh') || hStr === '50%') && h50Btn) {
            h50Btn.style.background = 'rgba(56,189,248,0.18)';
            h50Btn.style.color = '#38bdf8';
            h50Btn.style.fontWeight = '700';
        } else if ((hStr.includes('70vh') || hStr === '70%') && h70Btn) {
            h70Btn.style.background = 'rgba(56,189,248,0.18)';
            h70Btn.style.color = '#38bdf8';
            h70Btn.style.fontWeight = '700';
        } else if ((hStr.includes('85vh') || hStr === '85%') && h85Btn) {
            h85Btn.style.background = 'rgba(56,189,248,0.18)';
            h85Btn.style.color = '#38bdf8';
            h85Btn.style.fontWeight = '700';
        } else {
            const hNum = typeof height === 'number' ? height : parseInt(height, 10);
            if (hNum === 380 && h380Btn) {
                h380Btn.style.background = 'rgba(56,189,248,0.18)';
                h380Btn.style.color = '#38bdf8';
                h380Btn.style.fontWeight = '700';
            } else if (hNum === 480 && h480Btn) {
                h480Btn.style.background = 'rgba(56,189,248,0.18)';
                h480Btn.style.color = '#38bdf8';
                h480Btn.style.fontWeight = '700';
            } else if (hNum === 620 && h620Btn) {
                h620Btn.style.background = 'rgba(56,189,248,0.18)';
                h620Btn.style.color = '#38bdf8';
                h620Btn.style.fontWeight = '700';
            }
        }

        if (maxBtn) {
            maxBtn.textContent = '⤢ Max';
            maxBtn.style.color = '#a78bfa';
        }

        try {
            localStorage.setItem('breakout_chart_height', hStr);
        } catch (e) {}

        if (app.resizeBreakoutChart) {
            setTimeout(app.resizeBreakoutChart, 50);
        }
    };

    app.toggleBreakoutChartMaximize = function() {
        const wrap = document.getElementById('bkInspLightweightChartWrap');
        const maxBtn = document.getElementById('bkInspChartMaxBtn');
        if (!wrap) return;

        const isMax = wrap.getAttribute('data-maximized') === 'true';
        if (isMax) {
            wrap.removeAttribute('data-maximized');
            let prevHeight = '70vh';
            try {
                const stored = localStorage.getItem('breakout_chart_height');
                if (stored) prevHeight = stored;
            } catch (e) {}
            app.setBreakoutChartHeight(prevHeight);
            if (maxBtn) {
                maxBtn.textContent = '⤢ Max';
                maxBtn.style.color = '#a78bfa';
            }
        } else {
            wrap.setAttribute('data-maximized', 'true');
            const maxH = 'calc(100vh - 240px)';
            app.setBreakoutChartHeight(maxH);
            if (maxBtn) {
                maxBtn.textContent = '⤓ Restore';
                maxBtn.style.color = '#34d399';
            }
        }
    };

    app._bkChartRange = app._bkChartRange || '1Y';
    app.setBreakoutChartRange = function(range) {
        app._bkChartRange = range || '1Y';
        const r3M = document.getElementById('bkRange3MBtn');
        const r6M = document.getElementById('bkRange6MBtn');
        const r1Y = document.getElementById('bkRange1YBtn');
        const rAll = document.getElementById('bkRangeAllBtn');

        [r3M, r6M, r1Y, rAll].forEach(btn => {
            if (btn) {
                btn.style.background = 'transparent';
                btn.style.color = '#94a3b8';
                btn.style.fontWeight = '400';
            }
        });

        const activeBtn = range === '3M' ? r3M : (range === '6M' ? r6M : (range === 'ALL' ? rAll : r1Y));
        if (activeBtn) {
            activeBtn.style.background = 'rgba(56,189,248,0.18)';
            activeBtn.style.color = '#38bdf8';
            activeBtn.style.fontWeight = '700';
        }

        if (app._bkRawBars && app._bkRawBars.length > 0 && app._bkCandleSeries && app._bkVolumeSeries) {
            app._renderBreakoutChartBars(app._bkRawBars, app._bkChartRange);
        }
    };

    app.fitBreakoutChartScale = function() {
        if (app._bkLightweightChart) {
            app._bkLightweightChart.timeScale().fitContent();
        }
    };

    app.resizeBreakoutChart = function() {
        const container = document.getElementById('bkInspLightweightChartContainer');
        const wrap = document.getElementById('bkInspLightweightChartWrap');
        if (app._bkLightweightChart && container) {
            const w = container.clientWidth;
            const h = wrap ? (wrap.clientHeight || wrap.offsetHeight) : 480;
            if (w > 0) {
                app._bkLightweightChart.applyOptions({
                    width: w,
                    height: h > 0 ? h : 480,
                });
            }
        }
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
                time: data[i].time,
                value: parseFloat((sum / period).toFixed(2)),
            });
        }
        return result;
    }

    app._renderBreakoutChartBars = function(rawBars, range) {
        if (!rawBars || rawBars.length === 0 || !app._bkCandleSeries || !app._bkVolumeSeries) return;

        let filteredBars = rawBars;
        if (range === '3M') {
            filteredBars = rawBars.slice(-65);
        } else if (range === '6M') {
            filteredBars = rawBars.slice(-130);
        } else if (range === '1Y') {
            filteredBars = rawBars.slice(-252);
        }

        const candles = [];
        const volumes = [];
        filteredBars.forEach(r => {
            const itemTime = r.date || r.time;
            candles.push({
                time: itemTime,
                open: Number(r.open),
                high: Number(r.high),
                low: Number(r.low),
                close: Number(r.close),
            });
            volumes.push({
                time: itemTime,
                value: Number(r.volume || 0),
                color: Number(r.close) >= Number(r.open) ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
            });
        });

        app._bkCandleSeries.setData(candles);
        app._bkVolumeSeries.setData(volumes);
        if (app._bkSma20Series) app._bkSma20Series.setData(calculateSMA(candles, 20));
        if (app._bkSma50Series) app._bkSma50Series.setData(calculateSMA(candles, 50));

        app._bkRenderedCandles = candles;
        app._bkRenderedVolumes = volumes;
        app._bkIsLoadingMore = false;
        app._bkHasMoreHistory = true;

        if (app._bkLightweightChart) {
            app._bkLightweightChart.timeScale().fitContent();
        }
    };

    app.onBreakoutChartVisibleLogicalRangeChange = function(newRange) {
        if (app._bkIsProgrammaticRangeChange || !newRange || app._bkIsLoadingMore || !app._bkHasMoreHistory || !app._bkCandleSeries) return;
        if (newRange.from <= 8) {
            if (app._bkRangeDebounceTimer) clearTimeout(app._bkRangeDebounceTimer);
            app._bkRangeDebounceTimer = setTimeout(() => {
                app.loadMoreBreakoutCandles();
            }, 120);
        }
    };

    app.loadMoreBreakoutCandles = async function() {
        if (app._bkIsLoadingMore || !app._bkHasMoreHistory || !app._bkCandleSeries || !app._bkLightweightChart) return;
        app._bkIsLoadingMore = true;

        try {
            const renderedCandles = app._bkRenderedCandles || [];
            if (renderedCandles.length === 0) {
                app._bkHasMoreHistory = false;
                return;
            }

            const earliestRenderedTime = renderedCandles[0].time;
            let olderRaw = (app._bkRawBars || []).filter(b => (b.date || b.time) < earliestRenderedTime);

            if (olderRaw.length === 0 && app._bkCurrentTicker) {
                const earliestDate = typeof earliestRenderedTime === 'string' ? earliestRenderedTime : new Date(earliestRenderedTime * 1000).toISOString().split('T')[0];
                const earliestDt = new Date(earliestDate);
                earliestDt.setFullYear(earliestDt.getFullYear() - 1);
                const targetStart = earliestDt.toISOString().split('T')[0];

                const res = await fetch(`/api/v1/price-history/${encodeURIComponent(app._bkCurrentTicker)}?start_date=${targetStart}`);
                if (res.ok) {
                    const fetchedBars = await res.json();
                    if (Array.isArray(fetchedBars) && fetchedBars.length > 0) {
                        const newOlder = fetchedBars.filter(b => (b.date || b.time) < earliestRenderedTime);
                        if (newOlder.length > 0) {
                            const existingDates = new Set((app._bkRawBars || []).map(b => b.date || b.time));
                            const toAdd = newOlder.filter(b => !existingDates.has(b.date || b.time));
                            app._bkRawBars = [...toAdd, ...(app._bkRawBars || [])];
                            olderRaw = toAdd;
                        }
                    }
                }
            }

            if (olderRaw.length === 0) {
                app._bkHasMoreHistory = false;
                return;
            }

            const newCandles = olderRaw.map(r => ({
                time: r.date || r.time,
                open: Number(r.open),
                high: Number(r.high),
                low: Number(r.low),
                close: Number(r.close),
            }));
            const newVolumes = olderRaw.map(r => ({
                time: r.date || r.time,
                value: Number(r.volume || 0),
                color: Number(r.close) >= Number(r.open) ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
            }));

            const mergedCandles = [...newCandles, ...renderedCandles];
            const mergedVolumes = [...newVolumes, ...(app._bkRenderedVolumes || [])];

            app._bkRenderedCandles = mergedCandles;
            app._bkRenderedVolumes = mergedVolumes;

            const curRange = app._bkLightweightChart.timeScale().getVisibleLogicalRange();
            const shift = newCandles.length;

            app._bkCandleSeries.setData(mergedCandles);
            if (app._bkVolumeSeries) app._bkVolumeSeries.setData(mergedVolumes);
            if (app._bkSma20Series) app._bkSma20Series.setData(calculateSMA(mergedCandles, 20));
            if (app._bkSma50Series) app._bkSma50Series.setData(calculateSMA(mergedCandles, 50));

            if (curRange) {
                app._bkIsProgrammaticRangeChange = true;
                try {
                    app._bkLightweightChart.timeScale().setVisibleLogicalRange({
                        from: curRange.from + shift,
                        to: curRange.to + shift,
                    });
                } finally {
                    setTimeout(() => {
                        app._bkIsProgrammaticRangeChange = false;
                    }, 50);
                }
            }
        } catch (err) {
            console.warn('[BREAKOUT] Error loading more candles on scrollback:', err);
            app._bkHasMoreHistory = false;
        } finally {
            app._bkIsLoadingMore = false;
        }
    };

    app.initBreakoutQuantumChart = async function(ticker, candidate, wallsData) {
        const container = document.getElementById('bkInspLightweightChartContainer');
        const wrap = document.getElementById('bkInspLightweightChartWrap');
        const loadingOverlay = document.getElementById('bkInspChartLoadingOverlay');
        const badge = document.getElementById('bkInspChartSymbolBadge');
        const popout = document.getElementById('bkInspTvPopoutLink');

        if (!container || !ticker) return;

        const tvSymbol = formatTradingViewSymbol(ticker);
        if (badge) badge.textContent = ticker;
        if (popout) popout.href = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;

        if (loadingOverlay) loadingOverlay.style.display = 'flex';

        if (app._bkLightweightChart) {
            try {
                app._bkLightweightChart.remove();
            } catch (e) {}
            app._bkLightweightChart = null;
        }
        container.innerHTML = '';

        if (!window.LightweightCharts) {
            if (loadingOverlay) loadingOverlay.style.display = 'none';
            container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-family:var(--font-mono);font-size:0.75rem;">Chart engine ready for ${ticker}</div>`;
            return;
        }

        try {
            app._bkCurrentTicker = ticker;
            app._bkIsLoadingMore = false;
            app._bkHasMoreHistory = true;

            const chartWidth = container.clientWidth || 600;
            const chartHeight = wrap ? (wrap.clientHeight || wrap.offsetHeight || 480) : 480;
            const chart = window.LightweightCharts.createChart(container, {
                width: chartWidth,
                height: chartHeight,
                layout: {
                    background: { type: 'solid', color: '#050508' },
                    textColor: '#94a3b8',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 10,
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
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
                    timeFormatter: (val) => (window.app && window.app.formatIST ? window.app.formatIST(val, { includeDate: true, includeTime: true, suffix: true }) : val),
                    dateFormatter: (val) => (window.app && window.app.formatIST ? window.app.formatIST(val, { includeDate: true, includeTime: false, suffix: true }) : val),
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    timeVisible: true,
                    secondsVisible: false,
                    tickMarkFormatter: (time, tickMarkType, locale) => {
                        return (window.app && window.app.formatIST ? window.app.formatIST(time, { includeTime: false }) : time);
                    },
                },
                rightPriceScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    scaleMargins: { top: 0.1, bottom: 0.15 },
                }
            });

            app._bkLightweightChart = chart;

            const candleSeries = chart.addCandlestickSeries({
                upColor: '#10b981',
                downColor: '#ef4444',
                borderUpColor: '#10b981',
                borderDownColor: '#ef4444',
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
            });
            app._bkCandleSeries = candleSeries;

            const volumeSeries = chart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: '',
                scaleMargins: { top: 0.82, bottom: 0 },
            });
            app._bkVolumeSeries = volumeSeries;

            const sma20Series = chart.addLineSeries({
                color: '#38bdf8',
                lineWidth: 1,
                title: 'SMA 20',
            });
            const sma50Series = chart.addLineSeries({
                color: '#fbbf24',
                lineWidth: 1,
                title: 'SMA 50',
            });
            app._bkSma20Series = sma20Series;
            app._bkSma50Series = sma50Series;

            const res = await fetch(`/api/v1/price-history/${encodeURIComponent(ticker)}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const rawBars = await res.json();

            if (!rawBars || rawBars.length === 0) {
                if (loadingOverlay) loadingOverlay.style.display = 'none';
                return;
            }

            app._bkRawBars = rawBars;
            app._bkCurrentCandidate = candidate;
            app._bkCurrentWallsData = wallsData;

            app._renderBreakoutChartBars(rawBars, app._bkChartRange || '1Y');

            const curPrice = candidate?.current_price || (rawBars.length > 0 ? Number(rawBars[rawBars.length - 1].close) : 0);
            const trigger = candidate?.breakout_trigger != null ? Number(candidate.breakout_trigger) : null;
            const target = candidate?.target_price != null ? Number(candidate.target_price) : (trigger ? trigger * 1.08 : null);
            const stopLoss = candidate?.stop_loss != null ? Number(candidate.stop_loss) : (curPrice ? curPrice * 0.95 : null);

            if (trigger) {
                candleSeries.createPriceLine({
                    price: trigger,
                    color: '#38bdf8',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `TRIGGER: ₹${trigger.toFixed(1)}`,
                });
            }

            if (stopLoss) {
                candleSeries.createPriceLine({
                    price: stopLoss,
                    color: '#f87171',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: `SL: ₹${stopLoss.toFixed(1)}`,
                });
            }

            if (target) {
                candleSeries.createPriceLine({
                    price: target,
                    color: '#34d399',
                    lineWidth: 2,
                    lineStyle: window.LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: `TARGET: ₹${target.toFixed(1)}`,
                });
            }

            if (wallsData) {
                if (wallsData.resistance_strike && Math.abs(wallsData.resistance_strike - (trigger || 0)) > 2) {
                    candleSeries.createPriceLine({
                        price: Number(wallsData.resistance_strike),
                        color: '#ef4444',
                        lineWidth: 2,
                        lineStyle: window.LightweightCharts.LineStyle.Dotted,
                        axisLabelVisible: true,
                        title: `SELL WALL: ₹${wallsData.resistance_strike}`,
                    });
                }
                if (wallsData.support_strike) {
                    candleSeries.createPriceLine({
                        price: Number(wallsData.support_strike),
                        color: '#10b981',
                        lineWidth: 2,
                        lineStyle: window.LightweightCharts.LineStyle.Dotted,
                        axisLabelVisible: true,
                        title: `BUY WALL: ₹${wallsData.support_strike}`,
                    });
                }
                if (wallsData.max_pain_strike) {
                    candleSeries.createPriceLine({
                        price: Number(wallsData.max_pain_strike),
                        color: '#a855f7',
                        lineWidth: 1,
                        lineStyle: window.LightweightCharts.LineStyle.LargeDashed,
                        axisLabelVisible: true,
                        title: `MAX PAIN: ₹${wallsData.max_pain_strike}`,
                    });
                }
            }

            fetch(`${API_BASE}/api/v1/breakout-radar/orderflow/${encodeURIComponent(ticker)}`)
                .then(r => r.ok ? r.json() : null)
                .then(ofData => {
                    if (app.renderBreakoutOrderBookSpread) {
                        if (ofData && ofData.success) {
                            app.renderBreakoutOrderBookSpread(ofData, curPrice, wallsData);
                        } else {
                            app.renderBreakoutOrderBookSpread(null, curPrice, wallsData);
                        }
                    }
                })
                .catch(() => {
                    if (app.renderBreakoutOrderBookSpread) {
                        app.renderBreakoutOrderBookSpread(null, curPrice, wallsData);
                    }
                });

            chart.subscribeCrosshairMove((param) => {
                if (!param) return;
                let candle = param.seriesData ? param.seriesData.get(candleSeries) : null;
                let volItem = param.seriesData ? param.seriesData.get(volumeSeries) : null;
                let timeVal = param.time;

                if (!candle && app._bkRawBars && app._bkRawBars.length > 0) {
                    if (param.point && param.point.y !== undefined && candleSeries.coordinateToPrice) {
                        const hoverPrice = candleSeries.coordinateToPrice(param.point.y);
                        if (hoverPrice) {
                            const match = app._bkRawBars.reduce((prev, curr) => {
                                return Math.abs(curr.close - hoverPrice) < Math.abs(prev.close - hoverPrice) ? curr : prev;
                            }, app._bkRawBars[app._bkRawBars.length - 1]);
                            candle = { open: match.open, high: match.high, low: match.low, close: match.close };
                            volItem = { value: match.volume };
                            timeVal = match.date || match.time;
                        }
                    }
                }

                if (candle) {
                    const hudO = document.getElementById('bkInspBarO');
                    const hudH = document.getElementById('bkInspBarH');
                    const hudL = document.getElementById('bkInspBarL');
                    const hudC = document.getElementById('bkInspBarC');
                    const hudTime = document.getElementById('bkInspBarTime');
                    if (hudO) hudO.textContent = '₹' + Number(candle.open).toFixed(2);
                    if (hudH) hudH.textContent = '₹' + Number(candle.high).toFixed(2);
                    if (hudL) hudL.textContent = '₹' + Number(candle.low).toFixed(2);
                    if (hudC) hudC.textContent = '₹' + Number(candle.close).toFixed(2);
                    if (hudTime && timeVal) {
                        hudTime.textContent = (window.app && window.app.formatIST ? window.app.formatIST(timeVal, { includeDate: true, includeTime: typeof timeVal === 'number', suffix: true }) : timeVal);
                    }
                }
            });

            chart.timeScale().subscribeVisibleLogicalRangeChange(app.onBreakoutChartVisibleLogicalRangeChange);
            chart.timeScale().fitContent();
        } catch (err) {
            console.warn('[BREAKOUT] Error initializing quantum chart:', err);
        } finally {
            if (loadingOverlay) loadingOverlay.style.display = 'none';
        }
    };

})();
