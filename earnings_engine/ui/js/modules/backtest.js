// =========================================================================
// backtest — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
// ---------- Backtest Tab ----------

            initBacktestTab() {
                // Populate watchlist dropdown for backtest tab
                const sel = document.getElementById('btWatchlist');
                if (!sel) return;
                // Copy options from swing market dropdown if available
                const swingSel = document.getElementById('swingMarket');
                if (swingSel && swingSel.options.length > 1) {
                    const current = sel.value;
                    sel.innerHTML = '';
                    for (const opt of swingSel.options) {
                        const o = document.createElement('option');
                        o.value = opt.value;
                        o.textContent = opt.textContent;
                        sel.appendChild(o);
                    }
                    if (current) sel.value = current;
                }
            },

            onBacktestStrategyChange(strat) {
                const badge = document.getElementById('btStrategyBadge');
                const labels = {
                    'swing': '🎯 Swing Channel Strategy',
                    'kronos': '🔮 Kronos AI 14D Horizon',
                    'earnings': '⚡ Earnings Reaction Drift',
                    'news': '📰 News Catalyst Momentum',
                    'auditor_all': '🏆 Multi-Strategy Benchmark',
                };
                if (badge) badge.textContent = labels[strat] || 'Strategy Backtest';
            },

            async runSwingBacktest(e) {
                const btn = document.getElementById('btRunBtn');
                const statusEl = document.getElementById('btStatus');
                const watchlist = document.getElementById('btWatchlist')?.value || 'my_watchlist';
                const strategy = document.getElementById('btStrategy')?.value || 'swing';

                const stratLabels = {
                    'swing': 'Swing Channel',
                    'kronos': 'Kronos AI Forecasts',
                    'earnings': 'Earnings Drift',
                    'news': 'News Momentum',
                    'auditor_all': 'Multi-Strategy Benchmark',
                };

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Running backtest...';
                }
                statusEl.textContent = 'Running ' + (stratLabels[strategy] || strategy) + ' backtest on "' + watchlist + '"...';
                statusEl.style.color = '';

                try {
                    const body = {
                        strategy: strategy,
                        watchlist: watchlist,
                        initial_capital: parseFloat(document.getElementById('btCapital')?.value || 100000),
                        risk_per_trade_pct: parseFloat(document.getElementById('btRiskPct')?.value || 1.5) / 100.0,
                        stop_loss_buffer_pct: parseFloat(document.getElementById('btStopPct')?.value || 2) / 100.0,
                        max_hold_days: parseInt(document.getElementById('btMaxHold')?.value || 21),
                        channel_lookback: parseInt(document.getElementById('btLookback')?.value || 20),
                        buy_zone_threshold: parseFloat(document.getElementById('btBuyZone')?.value || 0.25),
                        volume_surge_mult: parseFloat(document.getElementById('btVolMult')?.value || 1.25),
                        lookback_months: parseInt(document.getElementById('btMonths')?.value || 6),
                    };

                    const res = await fetch(API_BASE + '/api/v1/backtest/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body)
                    });
                    const data = await res.json();

                    if (data.success) {
                        this.renderBacktestResults(data);
                        statusEl.textContent = 'Backtest completed for ' + (data.strategy_name || stratLabels[strategy] || 'Strategy') + ' — ' + (data.total_trades || 0) + ' trades simulated.';
                        statusEl.style.color = 'var(--green)';
                    } else {
                        statusEl.textContent = 'Error: ' + (data.detail || data.error || 'Unknown error');
                        statusEl.style.color = 'var(--red)';
                    }
                } catch (err) {
                    console.error('Backtest error:', err);
                    statusEl.textContent = 'Network error running backtest.';
                    statusEl.style.color = 'var(--red)';
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            renderBacktestResults(data) {
                // KPI Metrics
                const retPct = data.total_return_pct || 0;
                const retColor = retPct >= 0 ? '#34d399' : '#ef4444';
                const annPct = data.annualized_return_pct || 0;
                const annColor = annPct >= 0 ? '#34d399' : '#ef4444';
                const ddPct = data.max_drawdown_pct || 0;
                const sharpe = data.sharpe_ratio || 0;
                const sharpeColor = sharpe >= 1.0 ? '#34d399' : sharpe >= 0.5 ? '#fbbf24' : '#ef4444';

                document.getElementById('btMetricReturn').textContent = (retPct >= 0 ? '+' : '') + retPct + '%';
                document.getElementById('btMetricReturn').style.color = retColor;
                document.getElementById('btMetricAnn').textContent = (annPct >= 0 ? '+' : '') + annPct + '%';
                document.getElementById('btMetricAnn').style.color = annColor;
                document.getElementById('btMetricSharpe').textContent = sharpe.toFixed(3);
                document.getElementById('btMetricSharpe').style.color = sharpeColor;
                document.getElementById('btMetricDD').textContent = '-' + ddPct + '%';
                document.getElementById('btMetricDD').style.color = ddPct > 15 ? '#ef4444' : ddPct > 8 ? '#fbbf24' : '#34d399';
                document.getElementById('btMetricTrades').textContent = data.total_trades || 0;
                document.getElementById('btMetricTrades').style.color = '#60a5fa';
                document.getElementById('btMetricWin').textContent = (data.win_rate_pct || 0) + '%';
                document.getElementById('btMetricWin').style.color = (data.win_rate_pct || 0) >= 50 ? '#34d399' : '#ef4444';
                document.getElementById('btMetricPF').textContent = (data.profit_factor || 0).toFixed(2);
                document.getElementById('btMetricPF').style.color = (data.profit_factor || 0) >= 1.5 ? '#34d399' : (data.profit_factor || 0) >= 1.0 ? '#fbbf24' : '#ef4444';
                document.getElementById('btMetricHold').textContent = (data.avg_hold_days || 0).toFixed(1) + 'd';
                document.getElementById('btMetricHold').style.color = '#94a3b8';

                // Equity Curve
                if (data.equity_curve && Object.keys(data.equity_curve).length > 1) {
                    document.getElementById('btChartPlaceholder').style.display = 'none';
                    this.drawEquityCurve('btEquityCanvas', data.equity_curve, data.initial_capital);
                }

                // Trade Log
                this.renderBacktestTrades(data.trades || []);
            },

            drawEquityCurve(canvasId, equityData, initialCapital) {
                const canvas = document.getElementById(canvasId);
                if (!canvas) return;

                // Set actual pixel dimensions for sharp rendering
                const rect = canvas.parentElement.getBoundingClientRect();
                const dpr = window.devicePixelRatio || 1;
                canvas.width = rect.width * dpr;
                canvas.height = rect.height * dpr;
                canvas.style.width = rect.width + 'px';
                canvas.style.height = rect.height + 'px';

                const ctx = canvas.getContext('2d');
                ctx.scale(dpr, dpr);
                const W = rect.width;
                const H = rect.height;
                const pad = { top: 25, right: 15, bottom: 30, left: 65 };
                const plotW = W - pad.left - pad.right;
                const plotH = H - pad.top - pad.bottom;

                // Parse data
                const dates = Object.keys(equityData).sort();
                const values = dates.map(d => equityData[d]);
                const minVal = Math.min(...values) * 0.995;
                const maxVal = Math.max(...values) * 1.005;
                const valRange = maxVal - minVal || 1;

                // Clear
                ctx.clearRect(0, 0, W, H);

                // Background
                ctx.fillStyle = 'rgba(15, 23, 42, 0.6)';
                ctx.fillRect(0, 0, W, H);

                // Grid lines
                ctx.strokeStyle = 'rgba(255,255,255,0.06)';
                ctx.lineWidth = 0.5;
                const nGridY = 5;
                for (let i = 0; i <= nGridY; i++) {
                    const y = pad.top + (plotH * i / nGridY);
                    ctx.beginPath();
                    ctx.moveTo(pad.left, y);
                    ctx.lineTo(W - pad.right, y);
                    ctx.stroke();

                    // Y-axis labels
                    const val = maxVal - (valRange * i / nGridY);
                    ctx.fillStyle = 'rgba(148,163,184,0.7)';
                    ctx.font = '10px Inter, system-ui, sans-serif';
                    ctx.textAlign = 'right';
                    ctx.fillText('₹' + Math.round(val).toLocaleString(), pad.left - 6, y + 3);
                }

                // Initial capital line
                const icY = pad.top + plotH * (1 - (initialCapital - minVal) / valRange);
                ctx.strokeStyle = 'rgba(251,191,36,0.3)';
                ctx.setLineDash([4, 4]);
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(pad.left, icY);
                ctx.lineTo(W - pad.right, icY);
                ctx.stroke();
                ctx.setLineDash([]);

                // Compute points
                const points = values.map((v, i) => ({
                    x: pad.left + (plotW * i / Math.max(values.length - 1, 1)),
                    y: pad.top + plotH * (1 - (v - minVal) / valRange)
                }));

                // Gradient fill under the curve
                const lastVal = values[values.length - 1];
                const isPositive = lastVal >= initialCapital;
                const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
                if (isPositive) {
                    grad.addColorStop(0, 'rgba(16,185,129,0.35)');
                    grad.addColorStop(1, 'rgba(16,185,129,0.02)');
                } else {
                    grad.addColorStop(0, 'rgba(239,68,68,0.25)');
                    grad.addColorStop(1, 'rgba(239,68,68,0.02)');
                }

                ctx.beginPath();
                ctx.moveTo(points[0].x, pad.top + plotH);
                points.forEach(p => ctx.lineTo(p.x, p.y));
                ctx.lineTo(points[points.length - 1].x, pad.top + plotH);
                ctx.closePath();
                ctx.fillStyle = grad;
                ctx.fill();

                // Equity line
                ctx.beginPath();
                ctx.moveTo(points[0].x, points[0].y);
                for (let i = 1; i < points.length; i++) {
                    ctx.lineTo(points[i].x, points[i].y);
                }
                ctx.strokeStyle = isPositive ? '#34d399' : '#ef4444';
                ctx.lineWidth = 2;
                ctx.stroke();

                // X-axis date labels (show ~6 evenly spaced)
                const nLabels = Math.min(6, dates.length);
                ctx.fillStyle = 'rgba(148,163,184,0.7)';
                ctx.font = '9px Inter, system-ui, sans-serif';
                ctx.textAlign = 'center';
                for (let i = 0; i < nLabels; i++) {
                    const idx = Math.round(i * (dates.length - 1) / Math.max(nLabels - 1, 1));
                    const x = pad.left + (plotW * idx / Math.max(dates.length - 1, 1));
                    const label = dates[idx].substring(5); // MM-DD
                    ctx.fillText(label, x, H - pad.bottom + 15);
                }

                // Legend
                ctx.fillStyle = 'rgba(148,163,184,0.5)';
                ctx.font = '10px Inter, system-ui, sans-serif';
                ctx.textAlign = 'left';
                ctx.fillText('Portfolio Equity', pad.left + 5, pad.top + 12);
                ctx.fillStyle = 'rgba(251,191,36,0.5)';
                ctx.fillText('Initial Capital: ₹' + Math.round(initialCapital).toLocaleString(), pad.left + 110, pad.top + 12);
            },

            renderBacktestTrades(trades) {
                const container = document.getElementById('btTradeLog');
                const countEl = document.getElementById('btTradeCount');
                if (!container) return;

                if (!trades || !trades.length) {
                    container.innerHTML = '<p class="timestamp" style="font-size:0.8rem;">No trades generated by the backtest.</p>';
                    if (countEl) countEl.textContent = '0 trades';
                    return;
                }

                if (countEl) countEl.textContent = trades.length + ' trade' + (trades.length === 1 ? '' : 's');

                const rows = trades.map(t => {
                    const pnlCls = t.pnl_pct > 0 ? 'price-positive' : t.pnl_pct < 0 ? 'price-negative' : '';
                    const reasonBg = t.exit_reason === 'Take Profit' ? 'rgba(16,185,129,0.15)' :
                                     t.exit_reason === 'Stop Loss' ? 'rgba(239,68,68,0.15)' :
                                     'rgba(251,191,36,0.1)';
                    return '<tr>' +
                        '<td><strong>' + t.ticker + '</strong></td>' +
                        '<td>' + (t.entry_date || '') + '</td>' +
                        '<td>₹' + (t.entry_price || 0).toFixed(2) + '</td>' +
                        '<td>' + (t.exit_date || '') + '</td>' +
                        '<td>₹' + (t.exit_price ? t.exit_price.toFixed(2) : '—') + '</td>' +
                        '<td class="' + pnlCls + '" style="font-weight:600;">' + (t.pnl_pct >= 0 ? '+' : '') + t.pnl_pct.toFixed(2) + '%</td>' +
                        '<td>₹' + (t.pnl || 0).toFixed(0) + '</td>' +
                        '<td>' + (t.hold_days || 0) + 'd</td>' +
                        '<td><span style="background:' + reasonBg + ';padding:0.15rem 0.4rem;border-radius:0.25rem;font-size:0.72rem;font-weight:600;">' + (t.exit_reason || '') + '</span></td>' +
                        '</tr>';
                }).join('');

                container.innerHTML = '<table class="results-table" style="font-size:0.78rem;width:100%;">' +
                    '<thead><tr>' +
                    '<th>Ticker</th><th>Entry</th><th>Entry ₹</th><th>Exit</th><th>Exit ₹</th><th>PnL %</th><th>PnL ₹</th><th>Hold</th><th>Reason</th>' +
                    '</tr></thead><tbody>' + rows + '</tbody></table>';
            
    
        }
});
})(); // end backtest IIFE
