/**
 * Nexus Breakout Radar - Order Flow & Terminal Widgets
 * Handles GoCharting interactive canvas terminal, 30-bin TPO Volume Profile,
 * intra-bar Footprint cluster matrix, Cumulative Volume Delta (CVD),
 * and embedded TradingView fallback widget.
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

    function formatGoChartingSymbol(sym) {
        if (!sym) return 'BSE:SENSEX';
        const clean = String(sym).trim().toUpperCase();
        if (clean === '^BSESN' || clean === 'SENSEX') return 'BSE:SENSEX';
        if (clean === '^NSEI' || clean === 'NIFTY') return 'NSE:NIFTY';
        if (clean.includes(':')) return clean;
        if (clean.endsWith('.NS') || clean.endsWith('.BO')) {
            return 'BSE:' + clean.replace(/\.(NS|BO)$/, '');
        }
        const knownUSTickers = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'GOOG', 'META', 'TSLA', 'SPY', 'QQQ', 'AMD', 'INTC', 'NFLX', 'BRK.B', 'JNJ', 'JPM', 'V', 'PG', 'UNH', 'HD', 'MA', 'DIS'];
        if (knownUSTickers.includes(clean)) return clean;
        return 'BSE:' + clean;
    }

    app.initBreakoutGoChartingWidget = function(ticker) {
        const container = document.getElementById('bkInspGoChartingContainer');
        if (!container || !ticker) return;

        const gcSymbol = formatGoChartingSymbol(ticker);
        const badge = document.getElementById('bkInspChartSymbolBadge');
        if (badge) badge.textContent = gcSymbol;

        const gcPopout = document.getElementById('bkInspGoChartingPopoutLink');
        if (gcPopout) gcPopout.href = `https://gocharting.com/terminal?ticker=${encodeURIComponent(gcSymbol)}`;

        const tvSymbol = formatTradingViewSymbol(ticker);
        const tvPopout = document.getElementById('bkInspTvPopoutLink');
        if (tvPopout) tvPopout.href = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;

        // Build self-hosted in-project interactive Order Flow, Footprint & CVD Canvas Terminal
        container.innerHTML = `
            <div style="height: 100%; width: 100%; display: flex; flex-direction: column; background: #050608; border-radius: 4px; overflow: hidden; position: relative; font-family: var(--font-mono);">
                <!-- Terminal Header Bar -->
                <div style="display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.03); border-bottom: 1px solid rgba(255,255,255,0.08); padding: 0.4rem 0.65rem; font-size: 0.68rem; flex-shrink: 0; flex-wrap: wrap; gap: 0.35rem;">
                    <div style="display: flex; align-items: center; gap: 0.45rem;">
                        <span style="background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.4); color: #fbbf24; font-weight: 800; font-size: 0.62rem; padding: 0.12rem 0.4rem; border-radius: 3px;">
                            📊 ORDER FLOW TERMINAL
                        </span>
                        <span style="color: #f8fafc; font-weight: 800; font-size: 0.76rem;">${gcSymbol}</span>
                    </div>

                    <!-- Real-Time Metrics Strip -->
                    <div style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.62rem;">
                        <div style="display: flex; align-items: center; gap: 0.2rem; background: rgba(0,0,0,0.4); padding: 0.12rem 0.35rem; border-radius: 3px; border: 1px solid rgba(255,255,255,0.06);">
                            <span style="color: #94a3b8;">POC:</span>
                            <span id="gcPocVal" style="color: #fbbf24; font-weight: 800;">—</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.2rem; background: rgba(0,0,0,0.4); padding: 0.12rem 0.35rem; border-radius: 3px; border: 1px solid rgba(255,255,255,0.06);">
                            <span style="color: #94a3b8;">VAH:</span>
                            <span id="gcVahVal" style="color: #38bdf8; font-weight: 800;">—</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.2rem; background: rgba(0,0,0,0.4); padding: 0.12rem 0.35rem; border-radius: 3px; border: 1px solid rgba(255,255,255,0.06);">
                            <span style="color: #94a3b8;">VAL:</span>
                            <span id="gcValVal" style="color: #34d399; font-weight: 800;">—</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.2rem; background: rgba(0,0,0,0.4); padding: 0.12rem 0.35rem; border-radius: 3px; border: 1px solid rgba(255,255,255,0.06);">
                            <span style="color: #94a3b8;">BIAS:</span>
                            <span id="gcDeltaBiasVal" style="color: #a78bfa; font-weight: 800;">—</span>
                        </div>
                    </div>
                </div>

                <!-- Main Canvas Container -->
                <div id="gcCanvasWrapper" style="position: relative; flex: 1; min-height: 380px; width: 100%; overflow: hidden; background: #050608;">
                    <canvas id="gcMainCanvas" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: block;"></canvas>

                    <!-- Interactive Crosshair Floating Tooltip -->
                    <div id="gcCanvasTooltip" style="position: absolute; display: none; pointer-events: none; background: rgba(5,6,10,0.92); border: 1px solid rgba(255,255,255,0.18); border-radius: 4px; padding: 0.4rem 0.55rem; font-size: 0.58rem; color: #f8fafc; z-index: 20; box-shadow: 0 4px 14px rgba(0,0,0,0.8); backdrop-filter: blur(6px); max-width: 240px;"></div>

                    <!-- Loading State -->
                    <div id="gcLoadingIndicator" style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; background: rgba(5,6,8,0.85); z-index: 10; gap: 0.4rem;">
                        <div style="width: 28px; height: 28px; border: 2px solid rgba(245,158,11,0.2); border-top-color: #fbbf24; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
                        <span style="color: #fbbf24; font-size: 0.72rem; font-weight: 700;">Loading Order Flow &amp; Footprint...</span>
                    </div>
                </div>

                <!-- Terminal Legend & Footer Bar -->
                <div style="display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.02); border-top: 1px solid rgba(255,255,255,0.06); padding: 0.3rem 0.65rem; font-size: 0.58rem; color: #94a3b8; flex-shrink: 0;">
                    <div style="display: flex; align-items: center; gap: 0.6rem;">
                        <span style="display: flex; align-items: center; gap: 0.2rem;"><span style="display: inline-block; width: 8px; height: 3px; background: #fbbf24;"></span> POC</span>
                        <span style="display: flex; align-items: center; gap: 0.2rem;"><span style="display: inline-block; width: 8px; height: 3px; background: #38bdf8;"></span> VAH</span>
                        <span style="display: flex; align-items: center; gap: 0.2rem;"><span style="display: inline-block; width: 8px; height: 3px; background: #34d399;"></span> VAL</span>
                        <span style="display: flex; align-items: center; gap: 0.2rem;"><span style="display: inline-block; width: 8px; height: 3px; background: #ef4444;"></span> Ask Imbalance</span>
                        <span style="display: flex; align-items: center; gap: 0.2rem;"><span style="display: inline-block; width: 8px; height: 3px; background: #10b981;"></span> Bid Imbalance</span>
                    </div>
                    <div style="color: #64748b;">
                        30-Bin TPO Volume Profile · Intra-Bar Lee-Ready CVD
                    </div>
                </div>
            </div>
        `;

        const canvas = document.getElementById('gcMainCanvas');
        const wrapper = document.getElementById('gcCanvasWrapper');
        const tooltip = document.getElementById('gcCanvasTooltip');
        const loadingIndicator = document.getElementById('gcLoadingIndicator');

        if (!canvas || !wrapper) return;

        fetch(`${API_BASE}/api/v1/breakout-radar/orderflow/${encodeURIComponent(ticker)}`)
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (loadingIndicator) loadingIndicator.style.display = 'none';
                if (!data || !data.success) {
                    wrapper.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#71717a;font-size:0.75rem;">Order flow data unavailable for ${gcSymbol}</div>`;
                    return;
                }

                const pocEl = document.getElementById('gcPocVal');
                const vahEl = document.getElementById('gcVahVal');
                const valEl = document.getElementById('gcValVal');
                const biasEl = document.getElementById('gcDeltaBiasVal');

                const vp = data.volume_profile || {};
                const of = data.order_flow || {};

                if (pocEl && vp.poc) pocEl.textContent = `₹${Number(vp.poc).toFixed(1)}`;
                if (vahEl && vp.vah) vahEl.textContent = `₹${Number(vp.vah).toFixed(1)}`;
                if (valEl && vp.val) valEl.textContent = `₹${Number(vp.val).toFixed(1)}`;
                if (biasEl && of.delta_regime) {
                    biasEl.textContent = of.delta_regime;
                    biasEl.style.color = of.delta_regime === 'ACCUMULATION' ? '#34d399' : (of.delta_regime === 'DISTRIBUTION' ? '#fb7185' : '#fbbf24');
                }

                renderOrderFlowCanvas(canvas, wrapper, tooltip, data);
            })
            .catch(err => {
                if (loadingIndicator) loadingIndicator.style.display = 'none';
                console.warn('[BREAKOUT] Error loading order flow terminal:', err);
            });
    };

    function renderOrderFlowCanvas(canvas, wrapper, tooltip, data) {
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const footprintBars = data.footprint_matrix || [];
        const vpBins = data.volume_profile?.profile_bins || [];
        const vp = data.volume_profile || {};
        const cvdBars = data.cvd_history_bars || [];

        if (footprintBars.length === 0) return;

        let mouseX = -1;
        let mouseY = -1;

        function draw() {
            const rect = wrapper.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            let width = rect.width || wrapper.clientWidth || 600;
            let height = rect.height || wrapper.clientHeight || 420;

            if (width <= 0 || height <= 0) {
                setTimeout(() => requestAnimationFrame(draw), 80);
                return;
            }

            canvas.width = width * dpr;
            canvas.height = height * dpr;
            ctx.resetTransform();
            ctx.scale(dpr, dpr);

            ctx.fillStyle = '#050608';
            ctx.fillRect(0, 0, width, height);

            const rightProfileWidth = Math.min(130, width * 0.22);
            const chartWidth = width - rightProfileWidth - 55;
            const topChartHeight = Math.floor(height * 0.72);
            const cvdTop = topChartHeight + 18;
            const cvdHeight = height - cvdTop - 18;

            let minP = Infinity;
            let maxP = -Infinity;
            footprintBars.forEach(b => {
                if (b.low < minP) minP = b.low;
                if (b.high > maxP) maxP = b.high;
            });
            if (vp.poc) {
                minP = Math.min(minP, vp.val || minP);
                maxP = Math.max(maxP, vp.vah || maxP);
            }
            const pPadding = (maxP - minP) * 0.08 || 1;
            minP -= pPadding;
            maxP += pPadding;

            function priceToY(p) {
                return topChartHeight - ((p - minP) / (maxP - minP)) * (topChartHeight - 20) - 10;
            }

            function yToPrice(y) {
                return maxP - ((y - 10) / (topChartHeight - 20)) * (maxP - minP);
            }

            ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
            ctx.lineWidth = 1;
            const numGridLines = 6;
            for (let i = 0; i <= numGridLines; i++) {
                const gy = 15 + (topChartHeight - 30) * (i / numGridLines);
                const gp = yToPrice(gy);
                ctx.beginPath();
                ctx.moveTo(0, gy);
                ctx.lineTo(width - rightProfileWidth, gy);
                ctx.stroke();

                ctx.fillStyle = '#64748b';
                ctx.font = '9px JetBrains Mono, monospace';
                ctx.textAlign = 'left';
                ctx.fillText('₹' + gp.toFixed(1), chartWidth + 5, gy + 3);
            }

            ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
            ctx.beginPath();
            ctx.moveTo(0, topChartHeight);
            ctx.lineTo(width, topChartHeight);
            ctx.stroke();

            // 2. Horizontal TPO Volume Profile
            if (vpBins.length > 0) {
                const maxBinVol = Math.max(1, ...vpBins.map(b => b.volume || 1));
                const vpLeft = width - rightProfileWidth;

                ctx.fillStyle = 'rgba(255, 255, 255, 0.015)';
                ctx.fillRect(vpLeft, 0, rightProfileWidth, topChartHeight);

                vpBins.forEach(b => {
                    const by = priceToY(b.price);
                    const bHeight = Math.max(2, (topChartHeight / vpBins.length) * 0.85);
                    const bWidth = (b.volume / maxBinVol) * (rightProfileWidth - 10);
                    const isPoc = b.is_poc;

                    const buyFrac = b.volume > 0 ? (b.buy_volume / b.volume) : 0.5;
                    const buyW = bWidth * buyFrac;
                    const sellW = bWidth - buyW;

                    ctx.fillStyle = isPoc ? '#f59e0b' : 'rgba(16, 185, 129, 0.6)';
                    ctx.fillRect(vpLeft, by - bHeight / 2, buyW, bHeight);

                    ctx.fillStyle = isPoc ? '#d97706' : 'rgba(239, 68, 68, 0.6)';
                    ctx.fillRect(vpLeft + buyW, by - bHeight / 2, sellW, bHeight);

                    if (isPoc) {
                        ctx.fillStyle = '#fbbf24';
                        ctx.font = 'bold 8px JetBrains Mono, monospace';
                        ctx.fillText('POC', vpLeft + bWidth + 3, by + 3);
                    }
                });
            }

            // 3. Draw POC, VAH, VAL horizontal lines
            if (vp.poc) {
                const pocY = priceToY(vp.poc);
                ctx.strokeStyle = '#f59e0b';
                ctx.setLineDash([4, 4]);
                ctx.beginPath();
                ctx.moveTo(0, pocY);
                ctx.lineTo(width - rightProfileWidth, pocY);
                ctx.stroke();
                ctx.setLineDash([]);
            }
            if (vp.vah) {
                const vahY = priceToY(vp.vah);
                ctx.strokeStyle = '#38bdf8';
                ctx.setLineDash([2, 3]);
                ctx.beginPath();
                ctx.moveTo(0, vahY);
                ctx.lineTo(width - rightProfileWidth, vahY);
                ctx.stroke();
                ctx.setLineDash([]);
            }
            if (vp.val) {
                const valY = priceToY(vp.val);
                ctx.strokeStyle = '#34d399';
                ctx.setLineDash([2, 3]);
                ctx.beginPath();
                ctx.moveTo(0, valY);
                ctx.lineTo(width - rightProfileWidth, valY);
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // 4. Draw Candlesticks & Footprint
            const barCount = footprintBars.length;
            const barSpacing = chartWidth / Math.max(1, barCount);
            const candleWidth = Math.max(8, barSpacing * 0.82);

            let hoveredBar = null;

            footprintBars.forEach((bar, idx) => {
                const cx = idx * barSpacing + barSpacing / 2;
                const oY = priceToY(bar.open);
                const cY = priceToY(bar.close);
                const hY = priceToY(bar.high);
                const lY = priceToY(bar.low);

                const isBull = bar.close >= bar.open;
                const bodyTop = Math.min(oY, cY);
                const bodyBottom = Math.max(oY, cY);
                const bodyHeight = Math.max(2, bodyBottom - bodyTop);

                if (mouseX >= cx - barSpacing / 2 && mouseX < cx + barSpacing / 2 && mouseY <= topChartHeight) {
                    hoveredBar = { bar, cx, idx };
                    ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
                    ctx.fillRect(cx - barSpacing / 2, 0, barSpacing, height);
                }

                ctx.strokeStyle = isBull ? '#10b981' : '#ef4444';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(cx, hY);
                ctx.lineTo(cx, lY);
                ctx.stroke();

                ctx.fillStyle = isBull ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)';
                ctx.fillRect(cx - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
                ctx.strokeStyle = isBull ? '#10b981' : '#ef4444';
                ctx.strokeRect(cx - candleWidth / 2, bodyTop, candleWidth, bodyHeight);

                if (candleWidth >= 12 && Array.isArray(bar.clusters) && bar.clusters.length > 0) {
                    const clusterH = Math.max(2, bodyHeight / bar.clusters.length);
                    bar.clusters.forEach((cl, cIdx) => {
                        const clY = bodyTop + cIdx * clusterH;
                        const buyV = cl.buy_vol ?? cl.buy ?? 0;
                        const sellV = cl.sell_vol ?? cl.sell ?? 0;
                        const isBuyImb = buyV > sellV * 1.5;
                        const isSellImb = sellV > buyV * 1.5;

                        ctx.fillStyle = isSellImb ? 'rgba(239, 68, 68, 0.65)' : 'rgba(239, 68, 68, 0.2)';
                        ctx.fillRect(cx - candleWidth / 2, clY, candleWidth / 2 - 0.5, clusterH);

                        ctx.fillStyle = isBuyImb ? 'rgba(16, 185, 129, 0.65)' : 'rgba(16, 185, 129, 0.2)';
                        ctx.fillRect(cx + 0.5, clY, candleWidth / 2 - 0.5, clusterH);
                    });
                }
            });

            // 5. Draw Cumulative Volume Delta (CVD)
            if (cvdBars.length > 0) {
                let minCvd = Infinity;
                let maxCvd = -Infinity;
                cvdBars.forEach(cb => {
                    const val = cb.cvd != null ? cb.cvd : (cb.cumulative_delta || 0);
                    if (val < minCvd) minCvd = val;
                    if (val > maxCvd) maxCvd = val;
                });
                const cvdPad = Math.max(10, (maxCvd - minCvd) * 0.1);
                minCvd -= cvdPad;
                maxCvd += cvdPad;

                function cvdToY(val) {
                    return cvdTop + cvdHeight - ((val - minCvd) / (maxCvd - minCvd)) * (cvdHeight - 10) - 5;
                }

                const zeroY = cvdToY(0);
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
                ctx.setLineDash([2, 2]);
                ctx.beginPath();
                ctx.moveTo(0, zeroY);
                ctx.lineTo(chartWidth, zeroY);
                ctx.stroke();
                ctx.setLineDash([]);

                ctx.beginPath();
                ctx.moveTo(0, zeroY);
                cvdBars.forEach((cb, idx) => {
                    const cbX = idx * barSpacing + barSpacing / 2;
                    const val = cb.cvd != null ? cb.cvd : (cb.cumulative_delta || 0);
                    const cbY = cvdToY(val);
                    ctx.lineTo(cbX, cbY);
                });
                ctx.lineTo(cvdBars.length * barSpacing, zeroY);
                ctx.closePath();

                const grad = ctx.createLinearGradient(0, cvdTop, 0, cvdTop + cvdHeight);
                grad.addColorStop(0, 'rgba(56, 189, 248, 0.35)');
                grad.addColorStop(1, 'rgba(56, 189, 248, 0.02)');
                ctx.fillStyle = grad;
                ctx.fill();

                ctx.strokeStyle = '#38bdf8';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                cvdBars.forEach((cb, idx) => {
                    const cbX = idx * barSpacing + barSpacing / 2;
                    const val = cb.cvd != null ? cb.cvd : (cb.cumulative_delta || 0);
                    const cbY = cvdToY(val);
                    if (idx === 0) ctx.moveTo(cbX, cbY);
                    else ctx.lineTo(cbX, cbY);
                });
                ctx.stroke();

                cvdBars.forEach((cb, idx) => {
                    const cbX = idx * barSpacing + barSpacing / 2;
                    const deltaH = Math.min(18, Math.max(2, Math.abs(cb.delta) / 1000));
                    const isPos = cb.delta >= 0;
                    ctx.fillStyle = isPos ? 'rgba(16, 185, 129, 0.7)' : 'rgba(239, 68, 68, 0.7)';
                    ctx.fillRect(cbX - 2, isPos ? (zeroY - deltaH) : zeroY, 4, deltaH);
                });

                ctx.fillStyle = '#38bdf8';
                ctx.font = 'bold 9px JetBrains Mono, monospace';
                ctx.textAlign = 'left';
                ctx.fillText('CVD (Order Flow Delta)', 10, cvdTop + 12);
            }

            // 6. Crosshair & Tooltip
            if (mouseX >= 0 && mouseX < chartWidth && mouseY >= 0 && mouseY < height) {
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
                ctx.setLineDash([2, 2]);

                ctx.beginPath();
                ctx.moveTo(mouseX, 0);
                ctx.lineTo(mouseX, height);
                ctx.stroke();

                if (mouseY <= topChartHeight) {
                    ctx.beginPath();
                    ctx.moveTo(0, mouseY);
                    ctx.lineTo(chartWidth, mouseY);
                    ctx.stroke();

                    const hoverPrice = yToPrice(mouseY);
                    ctx.fillStyle = '#38bdf8';
                    ctx.fillRect(chartWidth + 1, mouseY - 7, 50, 14);
                    ctx.fillStyle = '#000000';
                    ctx.font = 'bold 9px JetBrains Mono, monospace';
                    ctx.textAlign = 'center';
                    ctx.fillText('₹' + hoverPrice.toFixed(1), chartWidth + 26, mouseY + 3);
                }
                ctx.setLineDash([]);

                if (hoveredBar && tooltip) {
                    const b = hoveredBar.bar;
                    const idx = hoveredBar.idx;
                    const cvdItem = cvdBars[idx] || {};

                    tooltip.style.display = 'block';
                    const tipX = Math.min(width - 220, Math.max(10, mouseX + 15));
                    const tipY = Math.min(height - 120, Math.max(10, mouseY - 30));
                    tooltip.style.left = tipX + 'px';
                    tooltip.style.top = tipY + 'px';

                    const cvdDisplay = (cvdItem.cvd != null ? cvdItem.cvd : cvdItem.cumulative_delta);
                    tooltip.innerHTML = `
                        <div style="color: #fbbf24; font-weight: 800; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 2px; margin-bottom: 3px;">
                            ${b.date || 'SESSION'} · ₹${Number(b.close).toFixed(2)}
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 2px;">
                            <span style="color: #94a3b8;">O: <b style="color:#fff;">₹${Number(b.open).toFixed(1)}</b></span>
                            <span style="color: #94a3b8;">H: <b style="color:#fff;">₹${Number(b.high).toFixed(1)}</b></span>
                            <span style="color: #94a3b8;">L: <b style="color:#fff;">₹${Number(b.low).toFixed(1)}</b></span>
                            <span style="color: #94a3b8;">C: <b style="color:${b.close >= b.open ? '#34d399' : '#f87171'};">₹${Number(b.close).toFixed(1)}</b></span>
                        </div>
                        <div style="margin-top: 3px; padding-top: 2px; border-top: 1px solid rgba(255,255,255,0.06);">
                            <div style="display:flex; justify-content:space-between;"><span style="color:#94a3b8;">Bar Delta:</span><b style="color:${b.delta >= 0 ? '#34d399' : '#f87171'};">${b.delta >= 0 ? '+' : ''}${Math.round(b.delta).toLocaleString()}</b></div>
                            <div style="display:flex; justify-content:space-between;"><span style="color:#94a3b8;">CVD:</span><b style="color:#38bdf8;">${cvdDisplay != null ? Math.round(cvdDisplay).toLocaleString() : '—'}</b></div>
                            <div style="display:flex; justify-content:space-between;"><span style="color:#94a3b8;">Volume:</span><b style="color:#e2e8f0;">${(b.volume || 0).toLocaleString()}</b></div>
                        </div>
                    `;
                }
            } else if (tooltip) {
                tooltip.style.display = 'none';
            }
        }

        wrapper.onmousemove = function(e) {
            const rect = wrapper.getBoundingClientRect();
            mouseX = e.clientX - rect.left;
            mouseY = e.clientY - rect.top;
            requestAnimationFrame(draw);
        };

        wrapper.onmouseleave = function() {
            mouseX = -1;
            mouseY = -1;
            if (tooltip) tooltip.style.display = 'none';
            requestAnimationFrame(draw);
        };

        const ro = new ResizeObserver(() => {
            requestAnimationFrame(draw);
        });
        ro.observe(wrapper);

        requestAnimationFrame(draw);
        setTimeout(() => requestAnimationFrame(draw), 50);
        setTimeout(() => requestAnimationFrame(draw), 250);
    }

    app.initBreakoutTradingViewWidget = function(ticker) {
        const container = document.getElementById('bkInspTradingViewContainer');
        if (!container || !ticker) return;
        container.innerHTML = '';

        const tvSymbol = formatTradingViewSymbol(ticker);
        const badge = document.getElementById('bkInspChartSymbolBadge');
        if (badge) badge.textContent = tvSymbol;
        const popout = document.getElementById('bkInspTvPopoutLink');
        const tvUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;
        if (popout) popout.href = tvUrl;

        const gcSymbol = formatGoChartingSymbol(ticker);
        const gcPopout = document.getElementById('bkInspGoChartingPopoutLink');
        if (gcPopout) gcPopout.href = `https://gocharting.com/terminal?ticker=${encodeURIComponent(gcSymbol)}`;

        try {
            const widgetWrap = document.createElement('div');
            widgetWrap.className = 'tradingview-widget-container';
            widgetWrap.style.width = '100%';
            widgetWrap.style.height = '100%';
            widgetWrap.style.position = 'relative';

            const widgetInner = document.createElement('div');
            widgetInner.className = 'tradingview-widget-container__widget';
            widgetInner.style.width = '100%';
            widgetInner.style.height = '100%';
            widgetWrap.appendChild(widgetInner);

            const script = document.createElement('script');
            script.type = 'text/javascript';
            script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
            script.async = true;
            script.innerHTML = JSON.stringify({
                "autosize": true,
                "symbol": tvSymbol,
                "interval": "D",
                "timezone": "Asia/Kolkata",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "allow_symbol_change": true,
                "hide_side_toolbar": true,
                "hide_top_toolbar": false,
                "save_image": false,
                "calendar": false,
                "hide_volume": false,
                "support_host": "https://www.tradingview.com"
            });

            widgetWrap.appendChild(script);
            container.appendChild(widgetWrap);
        } catch (err) {
            console.warn('Error creating Breakout TradingView widget:', err);
            container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-family:var(--font-mono);font-size:0.75rem;">TradingView chart stream ready for ${tvSymbol}</div>`;
        }
    };

})();
