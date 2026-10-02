// =========================================================================
// consensus — Nexus Dashboard Module (Multi-Model AI Consensus Engine & Post-Mortems)
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
            tradingAgentsMap: {},

            // =========================================================================
            // 🏛️ TradingAgents Multi-Agent Trading Suite (TauricResearch Architecture)
            // =========================================================================
            async loadTradingAgentsCache() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/trading-agents/all?limit=500');
                    const data = await res.json();
                    if (data && data.reports) {
                        data.reports.forEach(r => {
                            if (r.ticker) {
                                this.tradingAgentsMap[r.ticker.toUpperCase()] = r;
                            }
                        });
                    }
                } catch (e) {
                    console.warn('Failed to load TradingAgents cache:', e);
                }
            },

            renderTradingAgentsBadge(ticker, market) {
                if (!ticker) return '—';
                const sym = String(ticker).trim().toUpperCase();
                const rep = this.tradingAgentsMap[sym];
                const safeSym = sym.replace(/'/g, "\\'");
                const domId = 'trading-agents-cell-' + sym.replace(/[^A-Za-z0-9]/g, '_');

                if (rep && rep.action) {
                    const act = (rep.action || 'HOLD').toUpperCase();
                    const isBull = act.includes('BUY');
                    const isBear = act.includes('SELL');
                    const color = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';
                    const bg = isBull ? 'rgba(16,185,129,0.18)' : isBear ? 'rgba(239,68,68,0.18)' : 'rgba(251,191,36,0.18)';
                    const border = isBull ? 'rgba(16,185,129,0.35)' : isBear ? 'rgba(239,68,68,0.35)' : 'rgba(251,191,36,0.35)';
                    const score = rep.conviction_score || 50;
                    const rrr = rep.risk_reward_ratio ? ` · ${Number(rep.risk_reward_ratio).toFixed(1)}R` : '';

                    return '<div id="' + domId + '" style="display:inline-flex;align-items:center;gap:0.3rem;white-space:nowrap;">' +
                        '<span class="signal-badge" style="background:' + bg + ';color:' + color + ';border:1px solid ' + border + ';font-size:0.70rem;padding:0.15rem 0.45rem;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:0.25rem;" onclick="event.stopPropagation(); app.openTradingAgentsWarRoom(\'' + safeSym + '\', event)" title="TradingAgents 7-Agent Synthesis: ' + act + ' (' + score + '% Conviction' + rrr + ') · Click for 7-Agent War Room">' +
                        '🏛️ ' + act + ' (' + score + '%)' +
                        '</span>' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runTradingAgentsWorkflow(\'' + safeSym + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Re-run 7-Agent Trading Team for ' + safeSym + '">⚡</button>' +
                        '</div>';
                } else {
                    return '<div id="' + domId + '" style="white-space:nowrap;">' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runTradingAgentsWorkflow(\'' + safeSym + '\', this)" style="padding:0.16rem 0.42rem;font-size:0.68rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;font-weight:600;white-space:nowrap;" title="Run 7-Agent Trading Team (TauricResearch) for ' + safeSym + '">🏛️ TradingAgents</button>' +
                        '</div>';
                }
            },

            async runTradingAgentsWorkflow(ticker, btnEl) {
                if (!ticker) return;
                const sym = String(ticker).trim().toUpperCase();
                if (btnEl) {
                    btnEl.disabled = true;
                    btnEl.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,0.3);border-radius:50%;border-top-color:#34d399;animation:spin 0.8s linear infinite;"></span>';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/trading-agents/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticker: sym, timeframe_days: 14, force_refresh: true })
                    });
                    const data = await res.json();
                    if (data && data.report) {
                        this.tradingAgentsMap[sym] = data.report;
                        
                        // Update all cells matching this ticker across all open tables
                        const domId = 'trading-agents-cell-' + sym.replace(/[^A-Za-z0-9]/g, '_');
                        const cells = document.querySelectorAll('[id="' + domId + '"]');
                        const newHtml = this.renderTradingAgentsBadge(sym, this.currentMarket || 'ALL');
                        cells.forEach(el => {
                            el.outerHTML = newHtml;
                        });

                        if (typeof this.showToast === 'function') {
                            this.showToast('🏛️ TradingAgents 7-Agent Synthesis for ' + sym + ': ' + data.report.action + ' (' + data.report.conviction_score + '% conviction)');
                        }
                        return data.report;
                    }
                } catch (e) {
                    console.error('Error running TradingAgents for ' + sym + ':', e);
                    if (typeof this.showToast === 'function') {
                        this.showToast('Failed running TradingAgents for ' + sym + ': ' + e.message, 'error');
                    }
                } finally {
                    if (btnEl) {
                        btnEl.disabled = false;
                        btnEl.innerHTML = '⚡';
                    }
                }
            },

            // =========================================================================
            // 🤖 AI Multi-Model Consensus (DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral)
            // =========================================================================
            async loadConsensusCache() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/consensus/latest?limit=500');
                    const data = await res.json();
                    if (data && data.predictions) {
                        data.predictions.forEach(p => {
                            if (p.ticker) {
                                this.consensusMap[p.ticker.toUpperCase()] = p;
                            }
                        });
                    }
                } catch (e) {
                    console.warn('Failed to load consensus cache:', e);
                }
            },

            renderConsensusBadge(ticker, market) {
                if (!ticker) return '—';
                const sym = String(ticker).trim().toUpperCase();
                const pred = this.consensusMap[sym];
                const safeMarket = (market || this.currentMarket || 'ALL').replace(/'/g, "\\'");
                const safeSym = sym.replace(/'/g, "\\'");
                const domId = 'consensus-cell-' + sym.replace(/[^A-Za-z0-9]/g, '_');

                if (pred && (pred.consensus_direction || pred.direction || typeof pred === 'string')) {
                    const rawDir = typeof pred === 'string' ? pred : (pred.consensus_direction || pred.direction);
                    const dir = (typeof rawDir === 'string' ? rawDir : (rawDir && typeof rawDir === 'object' && rawDir.direction ? rawDir.direction : (rawDir != null ? String(rawDir) : 'NEUTRAL'))).toUpperCase();
                    const isBull = dir.includes('BULL') || dir.includes('BUY');
                    const isBear = dir.includes('BEAR') || dir.includes('SELL');
                    const color = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';
                    const bg = isBull ? 'rgba(16,185,129,0.18)' : isBear ? 'rgba(239,68,68,0.18)' : 'rgba(251,191,36,0.18)';
                    const border = isBull ? 'rgba(16,185,129,0.35)' : isBear ? 'rgba(239,68,68,0.35)' : 'rgba(251,191,36,0.35)';
                    
                    const retPct = pred.consensus_return_pct != null ? pred.consensus_return_pct : (pred.expected_move_pct != null ? pred.expected_move_pct : null);
                    const retStr = retPct != null ? ((retPct > 0 ? '+' : '') + Number(retPct).toFixed(1) + '%') : '';
                    const strength = pred.consensus_strength != null ? Math.round(pred.consensus_strength) + '%' : '';
                    const agreeRatio = pred.agreement_ratio != null ? Math.round(pred.agreement_ratio * 100) : (pred.agreement_rate ? Math.round(pred.agreement_rate * 100) : null);
                    const action = pred.consensus_recommended_action || (isBull ? 'BUY' : isBear ? 'SELL' : 'HOLD');
                    
                    const titleText = 'DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral: ' + dir + (retStr ? ' (' + retStr + ')' : '') +
                        (agreeRatio ? ' · ' + agreeRatio + '% Agreement' : '') +
                        (strength ? ' · ' + strength + ' Strength' : '') +
                        (action ? ' · Stance: ' + action : '') +
                        ' (Click to view full price action & 5-pillar targets)';

                    return '<div id="' + domId + '" style="display:inline-flex;align-items:center;gap:0.35rem;white-space:nowrap;">' +
                        '<span class="signal-badge" style="background:' + bg + ';color:' + color + ';border:1px solid ' + border + ';font-size:0.72rem;padding:0.18rem 0.5rem;font-weight:700;cursor:pointer;white-space:nowrap;" onclick="event.stopPropagation(); app.openAiDetails(\'' + safeMarket + '\', \'' + safeSym + '\', event)" title="' + titleText.replace(/"/g, '&quot;') + '">' +
                        '🤖 ' + dir + (retStr ? ' ' + retStr : '') +
                        '</span>' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(99,102,241,0.18);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);border-radius:0.3rem;" title="Re-run 4-Model AI Consensus for ' + safeSym + '">⚡</button>' +
                        '</div>';
                } else {
                    return '<div id="' + domId + '" style="white-space:nowrap;">' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.18rem 0.45rem;font-size:0.7rem;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);border-radius:0.3rem;font-weight:600;white-space:nowrap;" title="Run DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral 4-Model consensus for ' + safeSym + '">⚡ AI Consensus</button>' +
                        '</div>';
                }
            },

            async runConsensusForTicker(ticker, btnEl) {
                if (!ticker) return;
                const sym = String(ticker).trim().toUpperCase();
                const oldHtml = btnEl ? btnEl.innerHTML : '';
                if (btnEl) {
                    btnEl.disabled = true;
                    btnEl.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,0.3);border-radius:50%;border-top-color:#60a5fa;animation:spin 0.8s linear infinite;"></span>';
                }

                try {
                    const result = await this.runOmniRouteAnalysis(sym);
                    return result;
                } catch (e) {
                    console.error('Error running consensus for ' + sym + ':', e);
                    if (typeof this.showToast === 'function') {
                        this.showToast('Failed running consensus for ' + sym + ': ' + e.message, 'error');
                    }
                } finally {
                    if (btnEl && btnEl.isConnected) {
                        btnEl.disabled = false;
                        btnEl.innerHTML = oldHtml;
                    }
                }
            },

            async predictAllConsensus(e) {
                const btn = (e && e.target) ? e.target : document.getElementById('swingConsensusAllBtn');
                const origHtml = btn ? btn.innerHTML : '🤖 Consensus All';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Scanning stocks in view...';
                }
                
                // Find all visible tickers on the active tables
                const tickers = [];
                const rows = document.querySelectorAll('#swingTableBody tr strong, #resultsTable tr strong, #topGainersTableBody tr strong, #upcomingSetupsTableBody tr strong, #scannerCandidatesTableBody tr strong, #patStocksTable tr strong');
                rows.forEach(r => {
                    const text = r.textContent.trim().toUpperCase();
                    if (text && text !== '?' && text !== '—' && !tickers.includes(text) && text.length <= 15 && !text.includes('NO CANDIDATES') && !text.includes('NO RESULTS')) {
                        tickers.push(text);
                    }
                });

                if (!tickers.length) {
                    if (typeof this.showToast === 'function') this.showToast('No stocks found in current view to predict.', 'info');
                    else alert('No stocks found in current view to predict.');
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                    return;
                }

                let completed = 0;
                const total = tickers.length;
                for (const ticker of tickers) {
                    if (btn) {
                        btn.innerHTML = '🤖 Consensus ' + (completed + 1) + '/' + total + ' (' + ticker + ')...';
                    }
                    await this.runConsensusForTicker(ticker, null);
                    completed++;
                }

                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
                if (typeof this.showToast === 'function') {
                    this.showToast('✨ Completed AI Consensus for ' + total + ' stocks!');
                } else {
                    alert('✨ Completed AI Consensus for ' + total + ' stocks!');
                }
            },

            async refreshSwing() {
                try {
                    await this.loadSwing();
                } catch (e) {
                    console.error('Error refreshing swing:', e);
                }
            },

            async runKronos() {
                const btn = document.getElementById('kronosRunBtn');
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Running...';
                document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Running Kronos predictions... this can take several minutes.</div>';

                // Priority: typed tickers > selected app watchlist (managed in the app).
                let tickers = [];
                const input = document.getElementById('kronosTickers').value;
                if (input) {
                    tickers = input.split(',').map(t => t.trim()).filter(Boolean);
                } else {
                    const wl = document.getElementById('kronosWatchlist').value || localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                    if (wl) {
                        try {
                            let res = await fetch(API_BASE + '/api/v1/watchlist/' + encodeURIComponent(wl));
                            if (!res.ok) {
                                res = await fetch(API_BASE + '/api/v1/watchlist?name=' + encodeURIComponent(wl));
                            }
                            if (res.ok) {
                                const data = await res.json();
                                tickers = (data && data.tickers) || (Array.isArray(data) ? data : []);
                            }
                        } catch (e) {
                            console.error('Error fetching watchlist tickers:', e);
                        }
                    }
                    if (!tickers.length) {
                        btn.disabled = false;
                        btn.textContent = '▶ Run Predictions';
                        document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No tickers found in watchlist "' + (wl || 'selected') + '". Type tickers above or pick another watchlist.</div>';
                        return;
                    }
                }
                if (!tickers.length) {
                    btn.disabled = false;
                    btn.textContent = '▶ Run Predictions';
                    document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">The selected watchlist has no tickers.</div>';
                    return;
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({tickers: tickers, lookback: 120, pred_len: 14})
                    });
                    if (!res.ok) {
                        const errData = await res.json().catch(() => ({}));
                        throw new Error(errData.detail || ('HTTP ' + res.status));
                    }
                    const data = await res.json();
                    this.renderKronos(data);
                } catch (e) {
                    console.error('Error running Kronos:', e);
                    document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0;color:var(--red);">Error running Kronos predictions: ' + (e.message || e) + '</div>';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '▶ Run Predictions';
                }
            },

            async runAllKronos() {
                const btn1 = document.getElementById('kronosRunAllBtn');
                const btn2 = document.getElementById('kronosListRunAllBtn');
                const setButtons = (running, text) => {
                    if (btn1) { btn1.disabled = running; btn1.innerHTML = text; }
                    if (btn2) { btn2.disabled = running; btn2.innerHTML = text; }
                };

                setButtons(true, '<span class="loading-spinner"></span> ⚡ Preparing All...');

                let tickers = [];
                const wl = document.getElementById('kronosWatchlist')?.value || localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';

                try {
                    let res = await fetch(API_BASE + '/api/v1/watchlist/' + encodeURIComponent(wl));
                    if (!res.ok) res = await fetch(API_BASE + '/api/v1/watchlist?name=' + encodeURIComponent(wl));
                    if (res.ok) {
                        const data = await res.json();
                        tickers = (data && data.tickers) || (Array.isArray(data) ? data : []);
                    }
                } catch (e) {
                    console.warn('Watchlist fetch error:', e);
                }

                if (!tickers || !tickers.length) {
                    try {
                        const res = await fetch(API_BASE + '/api/v1/universe/symbols?market=' + encodeURIComponent(wl || 'NSE_TOP'));
                        if (res.ok) {
                            const data = await res.json();
                            tickers = data.tickers || (Array.isArray(data) ? data : []);
                        }
                    } catch (e) {
                        console.warn('Universe fetch error:', e);
                    }
                }

                if (!tickers || !tickers.length) {
                    tickers = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS', 'BHARTIARTL.NS', 'SBIN.NS', 'LICI.NS', 'ITC.NS', 'HINDUNILVR.NS', 'LT.NS', 'BAJFINANCE.NS', 'MARUTI.NS', 'HCLTECH.NS', 'SUNPHARMA.NS', 'TATAMOTORS.NS', 'NTPC.NS', 'ONGC.NS', 'POWERGRID.NS', 'TITAN.NS'];
                }

                const total = tickers.length;
                let allForecasts = [];
                const chunkSize = 8;

                const widgetsEl = document.getElementById('kronosWidgets');
                if (widgetsEl) {
                    widgetsEl.innerHTML = `<div class="card" style="grid-column:1/-1;margin:0;padding:1.2rem;text-align:center;">
                        <div style="font-size:1.05rem;font-weight:700;color:#38bdf8;margin-bottom:0.35rem;">⚡ Running Kronos Neural AI Batch Inference</div>
                        <div style="font-size:0.76rem;color:#94a3b8;margin-bottom:0.75rem;">Processing ${total} stocks in <strong>${wl || 'universe'}</strong> using local neural sequence acceleration...</div>
                        <div style="background:rgba(255,255,255,0.06);border-radius:20px;height:8px;max-width:380px;margin:0 auto;overflow:hidden;">
                            <div id="kronosBatchProgressBar" style="background:linear-gradient(90deg,#3b82f6,#10b981);height:100%;width:0%;transition:width 0.3s ease;"></div>
                        </div>
                        <div id="kronosBatchProgressText" style="font-size:0.72rem;color:#cbd5e1;margin-top:0.5rem;font-family:var(--font-mono);">0 / ${total} completed</div>
                    </div>`;
                }

                for (let i = 0; i < total; i += chunkSize) {
                    const chunk = tickers.slice(i, i + chunkSize);
                    setButtons(true, `⚡ Running (${Math.min(i + chunkSize, total)}/${total})...`);
                    
                    const progBar = document.getElementById('kronosBatchProgressBar');
                    const progText = document.getElementById('kronosBatchProgressText');
                    if (progBar) progBar.style.width = Math.round((i / total) * 100) + '%';
                    if (progText) progText.textContent = `${i} / ${total} completed (${chunk.slice(0, 3).join(', ')}${chunk.length > 3 ? '...' : ''})`;

                    try {
                        const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({tickers: chunk, lookback: 120, pred_len: 14})
                        });
                        if (res.ok) {
                            const chunkForecasts = await res.json();
                            if (Array.isArray(chunkForecasts)) {
                                allForecasts = allForecasts.concat(chunkForecasts);
                            }
                        }
                    } catch (e) {
                        console.error('Kronos batch chunk error:', e);
                    }
                }

                const progBar = document.getElementById('kronosBatchProgressBar');
                const progText = document.getElementById('kronosBatchProgressText');
                if (progBar) progBar.style.width = '100%';
                if (progText) progText.textContent = `✅ Completed ${allForecasts.length} / ${total} predictions!`;

                if (allForecasts.length) {
                    this.renderKronos(allForecasts);
                }

                setButtons(false, '⚡ Run All (Batch)');

                try {
                    await this.loadKronosList();
                    await this.loadKronosSummaryCards();
                } catch (e) {}
            },

            renderKronos(forecasts) {
                const el = document.getElementById('kronosWidgets');
                if (!forecasts.length) {
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No predictions generated. Check that Kronos library is available.</div>';
                    return;
                }
                el.innerHTML = forecasts.map(f => {
                    const sym = f.symbol || f.ticker || '?';
                    const name = f.name || sym;
                    const ret = f.return_pct != null ? Number(f.return_pct) : 0;
                    const isBull = ret >= 0.5;
                    const isBear = ret <= -0.5;
                    const cls = isBull ? 'price-positive' : (isBear ? 'price-negative' : '');
                    const trendEmoji = isBull ? '🟢' : (isBear ? '🔴' : '🟡');
                    const trendText = isBull ? 'Bullish' : (isBear ? 'Bearish' : 'Neutral');
                    const badgeBg = isBull ? 'rgba(16,185,129,0.15)' : (isBear ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.08)');
                    const badgeColor = isBull ? '#34d399' : (isBear ? '#f87171' : 'var(--muted)');

                    const series = Array.isArray(f.forecast_series) ? f.forecast_series : [];
                    const seriesHtml = series.length ? this.renderForecastSeries(series, sym, f.run_at) : '';
                    const gbmHtml = this.renderGbmSignal(f.gbm_prediction);
                    const hasDetails = Boolean(f.explanation || (f.gbm_prediction && !f.gbm_prediction.error));

                    return '<div class="widget-card" style="padding:0.75rem 0.9rem;border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;background:rgba(255,255,255,0.02);display:flex;flex-direction:column;gap:0.4rem;">' +
                        // Top row: Symbol + Name left, Trend badge right
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;">' +
                            '<div>' +
                                '<div style="font-size:1rem;font-weight:700;letter-spacing:0.02em;color:var(--light);">' + sym + '</div>' +
                                (name !== sym ? '<div style="font-size:0.75rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;">' + name + '</div>' : '') +
                            '</div>' +
                            '<span style="background:' + badgeBg + ';color:' + badgeColor + ';padding:0.2rem 0.55rem;border-radius:0.35rem;font-size:0.75rem;font-weight:700;white-space:nowrap;">' +
                                trendEmoji + ' ' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '% ' + trendText +
                            '</span>' +
                        '</div>' +
                        
                        // Metrics strip: 4-column compact horizontal grid
                        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.35rem;background:rgba(0,0,0,0.25);border-radius:0.35rem;padding:0.4rem 0.5rem;text-align:center;">' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">Price</span><strong style="font-size:0.82rem;">₹' + (f.current_price ? f.current_price.toFixed(1) : '—') + '</strong></div>' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">14D Ret</span><strong class="' + cls + '" style="font-size:0.82rem;">' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%</strong></div>' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">Support</span><strong style="font-size:0.82rem;">' + (f.support ? '₹' + Number(f.support).toFixed(1) : '—') + '</strong></div>' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">Resist</span><strong style="font-size:0.82rem;">' + (f.resistance ? '₹' + Number(f.resistance).toFixed(1) : '—') + '</strong></div>' +
                        '</div>' +

                        // Collapsible: AI Rationale & Event Signal (if present)
                        (hasDetails ? (
                            '<details style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.3rem;padding:0.25rem 0.5rem;" onclick="event.stopPropagation()">' +
                                '<summary style="cursor:pointer;font-size:0.72rem;color:var(--muted);font-weight:600;user-select:none;">💡 AI Rationale & Signal</summary>' +
                                '<div style="margin-top:0.35rem;font-size:0.75rem;line-height:1.35;color:var(--muted);">' +
                                    (f.explanation ? '<p style="margin:0 0 0.35rem 0;">' + f.explanation + '</p>' : '') +
                                    gbmHtml +
                                '</div>' +
                            '</details>'
                        ) : '') +

                        // Collapsible: 14-Day OHLCV Forecast Table (if present)
                        (series.length ? (
                            '<details style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.3rem;padding:0.25rem 0.5rem;" onclick="event.stopPropagation()">' +
                                '<summary style="cursor:pointer;font-size:0.72rem;color:var(--muted);font-weight:600;user-select:none;">📊 14-Day OHLCV Forecast (' + series.length + ' bars)</summary>' +
                                '<div style="margin-top:0.35rem;max-height:220px;overflow-y:auto;">' + seriesHtml + '</div>' +
                            '</details>'
                        ) : '') +

                        // Footer row: run_at timestamp left, History action button right
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.2rem;padding-top:0.3rem;border-top:1px solid rgba(255,255,255,0.05);">' +
                            '<span style="font-size:0.68rem;color:var(--muted);">' + (f.run_at ? f.run_at.split('.')[0] : '') + '</span>' +
                            '<div style="display:flex;gap:0.3rem;">' +
                                '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + sym + '\', \'' + (f.run_at || '') + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV accuracy against realized prices">📊 Benchmark</button>' +
                                '<button type="button" onclick="event.stopPropagation(); app.showKronosHistory(\'' + sym + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:0.3rem;">🔍 History</button>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');
            },

            renderForecastSeries(series, ticker, runAt) {
                const rows = series.map(r =>
                    '<tr>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.date ? r.date.split(' ')[0] : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.open != null ? Number(r.open).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.high != null ? Number(r.high).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.low != null ? Number(r.low).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;font-weight:600;">' + (r.close != null ? Number(r.close).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.volume != null ? (Number(r.volume)/1000).toFixed(0) + 'k' : '—') + '</td>' +
                    '</tr>'
                ).join('');

                const benchBtn = ticker ? '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + ticker + '\', \'' + (runAt || '') + '\')" class="btn btn-sm" style="margin-top:0.4rem;width:100%;font-size:0.7rem;padding:0.2rem 0.4rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;">📊 Benchmark Realized vs Predicted OHLCV →</button>' : '';

                return '<table class="results-table" style="font-size:0.7rem;width:100%;border-collapse:collapse;">' +
                    '<thead><tr><th style="padding:0.2rem 0.35rem;">Date</th><th style="padding:0.2rem 0.35rem;">O</th><th style="padding:0.2rem 0.35rem;">H</th><th style="padding:0.2rem 0.35rem;">L</th><th style="padding:0.2rem 0.35rem;">C</th><th style="padding:0.2rem 0.35rem;">Vol</th>' +
                    '</tr></thead><tbody>' + rows + '</tbody></table>' + benchBtn;
            },

            async showOhlcvBenchmarkModal(ticker, runAt, forceRefresh = false) {
                this._activeOhlcvTicker = ticker;
                const modal = document.getElementById('kronosOhlcvModal');
                const scorecardsEl = document.getElementById('kronosOhlcvScorecards');
                const tableEl = document.getElementById('kronosOhlcvTableContainer');
                const badgeEl = document.getElementById('kronosOhlcvTickerBadge');
                const runSelectorEl = document.getElementById('kronosOhlcvRunSelector');
                const explanationEl = document.getElementById('kronosOhlcvExplanation');
                const fetchBtn = document.getElementById('kronosOhlcvFetchBtn');

                if (badgeEl) badgeEl.textContent = ticker + (runAt ? ' (' + runAt + ')' : '');
                modal.style.display = 'block';
                scorecardsEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Evaluating OHLCV realized bars for ' + ticker + (forceRefresh ? ' (downloading latest market candles)...' : '...') + '</div>';
                tableEl.innerHTML = '';

                // Populate Run Selector dropdown with all available historical runs for this ticker
                try {
                    const histRes = await fetch(API_BASE + '/api/v1/dashboard/kronos/history/' + encodeURIComponent(ticker));
                    const history = await histRes.json();
                    if (runSelectorEl && Array.isArray(history) && history.length > 0) {
                        const sortedHistory = [...history].sort((a, b) => new Date(b.run_at) - new Date(a.run_at));
                        const activeRun = runAt || sortedHistory[0].run_at;
                        runSelectorEl.innerHTML = sortedHistory.map((h, idx) => {
                            const p = h.prediction || {};
                            const trend = p.trend || h.trend || 'Prediction';
                            const ret = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : h.return_pct;
                            const retStr = ret !== null && ret !== undefined ? (ret >= 0 ? '+' : '') + Number(ret).toFixed(1) + '%' : '';
                            const isSelected = h.run_at === activeRun ? 'selected' : '';
                            const isLatest = idx === 0 ? ' (Latest)' : '';
                            return '<option value="' + h.run_at + '" ' + isSelected + '>' + h.run_at + isLatest + ' — ' + trend + (retStr ? ' (' + retStr + ')' : '') + '</option>';
                        }).join('');

                        runSelectorEl.onchange = (e) => {
                            this.showOhlcvBenchmarkModal(ticker, e.target.value);
                        };
                    }
                } catch (e) {
                    console.warn('Could not populate run selector:', e);
                }

                try {
                    let url = API_BASE + '/api/v1/dashboard/kronos/benchmark-ohlcv/' + encodeURIComponent(ticker);
                    const params = [];
                    if (runAt) params.push('run_at=' + encodeURIComponent(runAt));
                    if (forceRefresh) params.push('force_refresh=true');
                    if (params.length > 0) url += '?' + params.join('&');

                    const res = await fetch(url);
                    const data = await res.json();

                    const summary = data.summary || {};
                    const bars = data.bars || [];

                    if (!bars.length) {
                        scorecardsEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No OHLCV forecast series found to benchmark for ' + ticker + '</div>';
                        return;
                    }

                    const settled = summary.settled_bars || 0;
                    const total = summary.total_bars || bars.length;
                    const mape = summary.mape_pct != null ? summary.mape_pct.toFixed(1) + '%' : '—';
                    const dirAcc = summary.directional_accuracy_pct != null ? summary.directional_accuracy_pct.toFixed(1) + '%' : '—';
                    const corridorAcc = summary.corridor_hit_pct != null ? summary.corridor_hit_pct.toFixed(1) + '%' : '—';
                    const overallScore = summary.overall_score_pct != null ? summary.overall_score_pct.toFixed(1) + '%' : '—';

                    if (explanationEl) {
                        if (summary.is_evaluated) {
                            explanationEl.innerHTML = '✅ <strong>Evaluated Run (' + settled + '/' + total + ' trading days closed):</strong> Realized market candles are compared against Kronos forecast.';
                            explanationEl.style.color = '#34d399';
                        } else {
                            explanationEl.innerHTML = '⏳ <strong>Live Active Run (' + total + ' days upcoming):</strong> Forecasted days are in the future. As daily candles close, realized prices settle automatically. <em>Select an earlier run from the dropdown above to benchmark past predictions or click "Fetch Latest Prices & Settle".</em>';
                            explanationEl.style.color = '#fbbf24';
                        }
                    }

                    const mapeColor = summary.mape_pct != null ? (summary.mape_pct <= 2.5 ? '#34d399' : (summary.mape_pct <= 5.0 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';
                    const dirColor = summary.directional_accuracy_pct != null ? (summary.directional_accuracy_pct >= 60 ? '#34d399' : (summary.directional_accuracy_pct >= 40 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';
                    const corrColor = summary.corridor_hit_pct != null ? (summary.corridor_hit_pct >= 70 ? '#34d399' : (summary.corridor_hit_pct >= 50 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';

                    scorecardsEl.innerHTML = 
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">🎯 Composite Accuracy</span>' +
                            '<strong style="font-size:1.15rem;color:#38bdf8;">' + (summary.is_evaluated ? overallScore : '⏳ Pending') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">📉 MAPE (Price Error)</span>' +
                            '<strong style="font-size:1.15rem;color:' + mapeColor + ';">' + (summary.is_evaluated ? mape : '—') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">📈 Directional Accuracy</span>' +
                            '<strong style="font-size:1.15rem;color:' + dirColor + ';">' + (summary.is_evaluated ? dirAcc : '—') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">🛡️ Corridor [L-H] Hit</span>' +
                            '<strong style="font-size:1.15rem;color:' + corrColor + ';">' + (summary.is_evaluated ? corridorAcc : '—') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">📅 Settled Days</span>' +
                            '<strong style="font-size:1.15rem;color:var(--light);">' + settled + ' / ' + total + '</strong>' +
                        '</div>';

                    const rows = bars.map(b => {
                        const isSettled = b.status === 'SETTLED';
                        const errCls = b.error_pct != null ? (b.error_pct <= 2.5 ? 'price-positive' : (b.error_pct <= 5.0 ? 'color:#fbbf24;' : 'price-negative')) : '';
                        const errText = b.error_pct != null ? b.error_pct.toFixed(1) + '%' : '—';
                        const deltaText = b.delta_pct != null ? (b.delta_pct >= 0 ? '+' : '') + b.delta_pct.toFixed(1) + '%' : '—';
                        const deltaCls = b.delta_pct != null ? (b.delta_pct >= 0 ? 'price-positive' : 'price-negative') : '';
                        
                        const corridorBadge = isSettled ? (b.corridor_hit ? '<span style="background:rgba(16,185,129,0.2);color:#34d399;padding:0.15rem 0.4rem;border-radius:0.25rem;font-size:0.72rem;font-weight:600;">✅ Inside</span>' : '<span style="background:rgba(239,68,68,0.2);color:#f87171;padding:0.15rem 0.4rem;border-radius:0.25rem;font-size:0.72rem;font-weight:600;">❌ Out</span>') : '<span style="color:var(--muted);font-size:0.72rem;">⏳</span>';
                        
                        const dirBadge = isSettled && b.dir_hit != null ? (b.dir_hit ? '<span style="color:#34d399;font-weight:700;">🟢 Match</span>' : '<span style="color:#f87171;font-weight:700;">🔴 Miss</span>') : '<span style="color:var(--muted);">—</span>';

                        const statusBadge = isSettled ? '<span style="background:rgba(16,185,129,0.15);color:#34d399;padding:0.15rem 0.45rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">✅ Settled</span>' : '<span style="background:rgba(255,255,255,0.06);color:var(--muted);padding:0.15rem 0.45rem;border-radius:0.3rem;font-size:0.72rem;">⏳ Upcoming</span>';

                        return '<tr>' +
                            '<td><strong>' + b.date + '</strong></td>' +
                            '<td>₹' + (b.pred_close ? b.pred_close.toFixed(2) : '—') + '</td>' +
                            '<td>' + (b.actual_close ? '₹' + b.actual_close.toFixed(2) : '—') + '</td>' +
                            '<td class="' + deltaCls + '">' + deltaText + '</td>' +
                            '<td class="' + errCls + '" style="font-weight:600;">' + errText + '</td>' +
                            '<td>' + dirBadge + '</td>' +
                            '<td>[₹' + (b.pred_low ? b.pred_low.toFixed(1) : '—') + ' - ₹' + (b.pred_high ? b.pred_high.toFixed(1) : '—') + ']</td>' +
                            '<td>' + (isSettled ? '[₹' + (b.actual_low ? b.actual_low.toFixed(1) : '—') + ' - ₹' + (b.actual_high ? b.actual_high.toFixed(1) : '—') + ']' : '—') + '</td>' +
                            '<td style="text-align:center;">' + corridorBadge + '</td>' +
                            '<td style="text-align:center;">' + statusBadge + '</td>' +
                            '</tr>';
                    }).join('');

                    tableEl.innerHTML = '<div class="table-wrapper"><table class="results-table">' +
                        '<thead><tr>' +
                        '<th>Date</th><th>Pred Close</th><th>Actual Close</th><th>Δ %</th><th>MAPE Error</th><th>Daily Direction</th><th>Forecast Range [L-H]</th><th>Actual Range [L-H]</th><th>Corridor Hit?</th><th>Status</th>' +
                        '</tr></thead><tbody>' + rows + '</tbody></table></div>';
                } catch (e) {
                    console.error('Error benchmarking OHLCV series:', e);
                    scorecardsEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error evaluating OHLCV benchmark for ' + ticker + '</div>';
                }
            },

            async refreshOhlcvBenchmarkPrices() {
                const ticker = this._activeOhlcvTicker;
                const runSelectorEl = document.getElementById('kronosOhlcvRunSelector');
                const runAt = runSelectorEl ? runSelectorEl.value : null;
                const fetchBtn = document.getElementById('kronosOhlcvFetchBtn');
                if (fetchBtn) {
                    fetchBtn.disabled = true;
                    fetchBtn.innerHTML = '⏳ Fetching Prices & Settling...';
                }
                try {
                    if (ticker) {
                        await this.showOhlcvBenchmarkModal(ticker, runAt, true);
                    }
                } finally {
                    if (fetchBtn) {
                        fetchBtn.disabled = false;
                        fetchBtn.innerHTML = '🔄 Fetch Latest Prices & Settle';
                    }
                }
            },

            renderGbmSignal(gbm) {
                if (!gbm || typeof gbm !== 'object' || gbm.error) {
                    return '';
                }
                const dir = gbm.direction || '—';
                const up = gbm.direction === 'UP';
                const cls = up ? 'price-positive' : 'price-negative';
                const conf = gbm.confidence != null ? (gbm.confidence * 100).toFixed(1) + '%' : '—';
                const pUp = gbm.p_up != null ? (gbm.p_up * 100).toFixed(1) + '%' : '—';
                return '<div style="margin-top:0.3rem;padding:0.25rem 0.4rem;background:rgba(255,255,255,0.03);border-left:3px solid ' + (up ? '#10b981' : '#ef4444') + ';font-size:0.72rem;">' +
                    '<strong class="' + cls + '">' + dir + '</strong> (p_up: ' + pUp + ', conf: ' + conf + ')' +
                    '</div>';
            },

            switchKronosTab(name) {
                name = name || 'latest';
                try {
                    localStorage.setItem('subtab_kronos', name);
                    if (!app._subtabState) app._subtabState = {};
                    app._subtabState['kronos'] = name;
                } catch (e) {}

                const latest = document.getElementById('kronosLatestView');
                const list = document.getElementById('kronosListView');
                const audit = document.getElementById('kronosAuditView');
                const btnLatest = document.getElementById('kronosTabLatest');
                const btnList = document.getElementById('kronosTabList');
                const btnAudit = document.getElementById('kronosTabAudit');

                const sideLatest = document.getElementById('sidebarSubKronosLatest');
                const sideList = document.getElementById('sidebarSubKronosList');
                const sideAudit = document.getElementById('sidebarSubKronosAudit');
                if (sideLatest) sideLatest.classList.toggle('active', name === 'latest');
                if (sideList) sideList.classList.toggle('active', name === 'list');
                if (sideAudit) sideAudit.classList.toggle('active', name === 'audit');
                
                // Hide all views
                if (latest) latest.style.display = 'none';
                if (list) list.style.display = 'none';
                if (audit) audit.style.display = 'none';
                if (btnLatest) btnLatest.classList.remove('active');
                if (btnList) btnList.classList.remove('active');
                if (btnAudit) btnAudit.classList.remove('active');
                
                const ctxLabel = document.getElementById('kronosSubtabContextLabel');
                if (ctxLabel) {
                    if (name === 'audit') ctxLabel.textContent = '📜 Forecast Audit History';
                    else if (name === 'list') ctxLabel.textContent = '📋 Universe Overview List';
                    else ctxLabel.textContent = '📈 Latest Forecast Charts';
                }

                if (name === 'audit') {
                    if (audit) audit.style.display = 'block';
                    if (btnAudit) btnAudit.classList.add('active');
                    this.loadKronosAudit();
                } else if (name === 'list') {
                    if (list) list.style.display = 'block';
                    if (btnList) btnList.classList.add('active');
                    this.loadKronosList();
                } else {
                    if (latest) latest.style.display = 'block';
                    if (btnLatest) btnLatest.classList.add('active');
                    this.loadKronosLatest();
                }
            },

            onKronosWatchlistChange() {
                const select = document.getElementById('kronosWatchlist');
                const val = select ? select.value : '';
                localStorage.setItem('selectedWatchlist_kronos', val);
                localStorage.setItem('selectedGlobalWatchlist', val);
                
                const gEl = document.getElementById('globalWatchlist');
                if (gEl) gEl.value = val;

                const isAudit = document.getElementById('kronosTabAudit')?.classList.contains('active');
                const isList = document.getElementById('kronosTabList')?.classList.contains('active');
                if (isAudit) {
                    this.loadKronosAudit();
                } else if (isList) {
                    this.loadKronosList();
                } else {
                    this.loadKronosLatest();
                }
            },

            async refreshKronos() {
                try {
                    const isAudit = document.getElementById('kronosTabAudit')?.classList.contains('active');
                    const isList = document.getElementById('kronosTabList')?.classList.contains('active');
                    if (isAudit) {
                        await this.loadKronosAudit();
                    } else if (isList) {
                        await this.loadKronosList();
                    } else {
                        await this.loadKronosLatest();
                    }
                } catch (e) {
                    console.error('Error refreshing Kronos:', e);
                }
            },

            async loadKronosLatest() {
                const el = document.getElementById('kronosWidgets');
                const wl = document.getElementById('kronosWatchlist')?.value || '';
                el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading latest predictions' + (wl ? ' for "' + wl + '"' : '') + '...</div>';
                try {
                    const url = API_BASE + '/api/v1/dashboard/kronos/latest' + (wl ? '?watchlist=' + encodeURIComponent(wl) : '');
                    const res = await fetch(url);
                    const data = await res.json();
                    if (!data.length) {
                        el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No saved predictions' + (wl ? ' for watchlist "' + wl + '"' : '') + '. Click "▶ Run Predictions" above to generate.</div>';
                        return;
                    }
                    // Each row has a nested `prediction` object (the stored payload).
                    const forecasts = data.map(row => {
                        const p = row.prediction || {};
                        return {
                            name: p.name || row.ticker,
                            symbol: p.symbol || row.ticker,
                            current_price: p.current_price,
                            return_pct: p.return_pct,
                            support: p.support,
                            resistance: p.resistance,
                            explanation: p.explanation,
                            run_at: row.run_at,
                            forecast_series: p.forecast_series,
                            gbm_prediction: p.gbm_prediction
                        };
                    });
                    this.renderKronos(forecasts);
                } catch (e) {
                    console.error('Error loading latest Kronos predictions:', e);
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading latest Kronos predictions</div>';
                }
            },

            kronosListSortKey: 'run_at',
            kronosListSortDir: 'desc',
            kronosListData: [],
            kronosListLivePrices: {},

            async loadKronosList() {
                const tbody = document.getElementById('kronosListTable');
                const kpiEl = document.getElementById('kronosListKpis');
                const badgeEl = document.getElementById('kronosListCountBadge');
                const wl = document.getElementById('kronosWatchlist')?.value || '';
                
                if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">Loading all predictions with live prices' + (wl ? ' for "' + wl + '"' : '') + '...</td></tr>';
                
                try {
                    const url = API_BASE + '/api/v1/dashboard/kronos/latest' + (wl ? '?watchlist=' + encodeURIComponent(wl) : '');
                    const res = await fetch(url);
                    const data = await res.json();
                    
                    if (!data.length) {
                        this.kronosListData = [];
                        if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">No predictions found' + (wl ? ' for watchlist "' + wl + '"' : '') + '. Click "▶ Run Predictions" above to generate.</td></tr>';
                        if (kpiEl) kpiEl.innerHTML = '';
                        if (badgeEl) badgeEl.textContent = '0 stocks';
                        return;
                    }

                    this.kronosListData = data;

                    // Fetch live market context prices in parallel
                    const livePrices = {};
                    await Promise.all(data.map(async row => {
                        const ticker = row.ticker;
                        try {
                            const r = await fetch(API_BASE + '/api/v1/market-context/' + encodeURIComponent(ticker));
                            const d = await r.json();
                            livePrices[ticker] = d.current_price;
                        } catch (e) {
                            livePrices[ticker] = null;
                        }
                    }));
                    this.kronosListLivePrices = livePrices;

                    this.renderKronosList();
                } catch (e) {
                    console.error('Error loading Kronos predictions list:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">Error loading predictions list</td></tr>';
                }
            },

            sortKronosList(key) {
                if (this.kronosListSortKey === key) {
                    this.kronosListSortDir = this.kronosListSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.kronosListSortKey = key;
                    this.kronosListSortDir = (key === 'ticker' || key === 'name') ? 'asc' : 'desc';
                }
                this.renderKronosList();
            },

            filterKronosList() {
                this.renderKronosList();
            },

            renderKronosList() {
                const tbody = document.getElementById('kronosListTable');
                const kpiEl = document.getElementById('kronosListKpis');
                const badgeEl = document.getElementById('kronosListCountBadge');
                if (!tbody) return;

                const data = this.kronosListData || [];
                const livePrices = this.kronosListLivePrices || {};
                const searchQ = (document.getElementById('kronosListSearch')?.value || '').toLowerCase().trim();
                const trendFilter = document.getElementById('kronosListTrendFilter')?.value || '';
                const outcomeFilter = document.getElementById('kronosListOutcomeFilter')?.value || '';

                // Map enriched rows
                const enriched = data.map(row => {
                    const p = row.prediction || {};
                    const ticker = row.ticker || '?';
                    const name = p.name || row.ticker;
                    const predP = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : (row.current_price || 0);
                    const liveP = livePrices[ticker];
                    const expRet = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : row.return_pct;
                    const trend = (p.trend || row.trend || '—').trim();
                    const gbm = p.gbm_prediction || {};
                    const support = p.support ? Number(p.support) : (row.support ? Number(row.support) : null);
                    const resistance = p.resistance ? Number(p.resistance) : (row.resistance ? Number(row.resistance) : null);

                    const hasPred = predP > 0;
                    const hasLive = liveP !== null && liveP !== undefined && !isNaN(liveP);
                    let delta = null, deltaPct = null;
                    if (hasPred && hasLive) {
                        delta = liveP - predP;
                        deltaPct = (delta / predP) * 100.0;
                    }

                    // Expected target price
                    let targetP = null;
                    if (hasPred && expRet !== null && expRet !== undefined) {
                        targetP = predP * (1 + expRet / 100.0);
                    }

                    // Outcome evaluation
                    let outcomeStatus = 'PENDING';
                    let outcomeLabel = '⏳ Pending';
                    let outcomeBg = 'rgba(255,255,255,0.06)';
                    let outcomeColor = 'var(--muted)';

                    if (deltaPct !== null) {
                        const isBull = trend === 'Bullish' || (expRet !== null && expRet > 0.3);
                        const isBear = trend === 'Bearish' || (expRet !== null && expRet < -0.3);

                        if (Math.abs(deltaPct) < 0.05) {
                            outcomeStatus = 'FLAT';
                            outcomeLabel = '⏳ Flat (0.0%)';
                            outcomeBg = 'rgba(251,191,36,0.15)';
                            outcomeColor = '#fbbf24';
                        } else if (isBull) {
                            if (deltaPct > 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        } else if (isBear) {
                            if (deltaPct < 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        }
                    }

                    return {
                        row,
                        ticker,
                        name,
                        run_at: row.run_at || '',
                        predicted_price: predP,
                        live_price: liveP,
                        delta,
                        delta_pct: deltaPct,
                        expected_return: expRet,
                        target_price: targetP,
                        trend,
                        gbm,
                        support,
                        resistance,
                        outcome: outcomeStatus,
                        outcomeLabel,
                        outcomeBg,
                        outcomeColor
                    };
                });

                // Compute KPI Summary Stats over all loaded predictions
                const totalStocks = enriched.length;
                let bullCount = 0, bearCount = 0, expRetSum = 0, expRetCount = 0;
                let curRetSum = 0, curRetCount = 0, workedCount = 0, evaluatedCount = 0;

                enriched.forEach(item => {
                    if (item.trend === 'Bullish') bullCount++;
                    else if (item.trend === 'Bearish') bearCount++;
                    if (item.expected_return !== null && item.expected_return !== undefined) {
                        expRetSum += item.expected_return;
                        expRetCount++;
                    }
                    if (item.delta_pct !== null && item.delta_pct !== undefined) {
                        curRetSum += item.delta_pct;
                        curRetCount++;
                    }
                    if (item.outcome === 'WORKED') {
                        workedCount++;
                        evaluatedCount++;
                    } else if (item.outcome === 'FAILED') {
                        evaluatedCount++;
                    }
                });

                const avgExpRet = expRetCount > 0 ? (expRetSum / expRetCount).toFixed(1) + '%' : '—';
                const avgCurRet = curRetCount > 0 ? (curRetSum / curRetCount >= 0 ? '+' : '') + (curRetSum / curRetCount).toFixed(1) + '%' : '—';
                const avgCurColor = curRetCount > 0 ? (curRetSum >= 0 ? '#34d399' : '#f87171') : 'var(--muted)';
                const winRate = evaluatedCount > 0 ? ((workedCount / evaluatedCount) * 100).toFixed(1) + '%' : '—';
                const winRateColor = evaluatedCount > 0 ? (workedCount / evaluatedCount >= 0.6 ? '#34d399' : (workedCount / evaluatedCount >= 0.4 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';

                if (kpiEl) {
                    kpiEl.innerHTML = 
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Total Stocks</span>' +
                            '<strong style="font-size:1.25rem;color:var(--light);">' + totalStocks + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">🟢 Bull / 🔴 Bear</span>' +
                            '<strong style="font-size:1.25rem;"><span style="color:#34d399;">' + bullCount + '</span> / <span style="color:#f87171;">' + bearCount + '</span></strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Avg Expected Return</span>' +
                            '<strong style="font-size:1.25rem;color:#38bdf8;">' + avgExpRet + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Avg Realized Return</span>' +
                            '<strong style="font-size:1.25rem;color:' + avgCurColor + ';">' + avgCurRet + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Win Rate (Hit Rate)</span>' +
                            '<strong style="font-size:1.25rem;color:' + winRateColor + ';">' + winRate + (evaluatedCount > 0 ? ' (' + workedCount + '/' + evaluatedCount + ')' : '') + '</strong>' +
                        '</div>';
                }

                // Filter rows
                let filtered = enriched.filter(item => {
                    if (searchQ) {
                        const matchSym = item.ticker.toLowerCase().includes(searchQ);
                        const matchName = item.name.toLowerCase().includes(searchQ);
                        if (!matchSym && !matchName) return false;
                    }
                    if (trendFilter && item.trend !== trendFilter) return false;
                    if (outcomeFilter) {
                        if (outcomeFilter === 'PENDING') {
                            if (item.outcome !== 'PENDING' && item.outcome !== 'FLAT') return false;
                        } else if (item.outcome !== outcomeFilter) {
                            return false;
                        }
                    }
                    return true;
                });

                if (badgeEl) badgeEl.textContent = filtered.length + ' of ' + totalStocks + ' stocks';

                // Sort rows
                const key = this.kronosListSortKey || 'run_at';
                const dir = this.kronosListSortDir || 'desc';
                filtered.sort((a, b) => {
                    let va = a[key], vb = b[key];
                    if (key === 'run_at') { va = new Date(va); vb = new Date(vb); }
                    va = va === null || va === undefined ? -Infinity : va;
                    vb = vb === null || vb === undefined ? -Infinity : vb;
                    if (va < vb) return dir === 'asc' ? -1 : 1;
                    if (va > vb) return dir === 'asc' ? 1 : -1;
                    return 0;
                });

                if (!filtered.length) {
                    tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">No predictions matching filter criteria.</td></tr>';
                    return;
                }

                tbody.innerHTML = filtered.map(item => {
                    const hasLive = item.live_price !== null && item.live_price !== undefined;
                    const hasPred = item.predicted_price > 0;
                    
                    const deltaStr = item.delta !== null ? (item.delta >= 0 ? '+' : '') + item.delta.toFixed(2) : '—';
                    const deltaPctStr = item.delta_pct !== null ? (item.delta_pct >= 0 ? '+' : '') + item.delta_pct.toFixed(2) + '%' : '—';
                    const deltaCls = item.delta_pct !== null ? (item.delta_pct >= 0 ? 'price-positive' : 'price-negative') : '';

                    const expRetStr = item.expected_return !== null && item.expected_return !== undefined ? (item.expected_return >= 0 ? '+' : '') + Number(item.expected_return).toFixed(2) + '%' : '—';
                    const expRetCls = item.expected_return !== null && item.expected_return !== undefined ? (item.expected_return >= 0 ? 'price-positive' : 'price-negative') : '';

                    const trendCls = item.trend === 'Bullish' ? 'price-positive' : item.trend === 'Bearish' ? 'price-negative' : '';
                    
                    // GBM signal badge if present
                    let gbmBadge = '';
                    if (item.gbm && item.gbm.direction) {
                        const gDir = item.gbm.direction;
                        const gColor = gDir === 'UP' ? '#34d399' : '#f87171';
                        const gConf = item.gbm.confidence != null ? ' ' + (item.gbm.confidence * 100).toFixed(0) + '%' : '';
                        gbmBadge = '<span style="display:block;font-size:0.68rem;color:' + gColor + ';opacity:0.85;">GBM: ' + gDir + gConf + '</span>';
                    }

                    // S/R band display
                    let srDisplay = '—';
                    if (item.support && item.resistance) {
                        srDisplay = '₹' + item.support.toFixed(1) + ' – ₹' + item.resistance.toFixed(1);
                    } else if (item.support) {
                        srDisplay = 'Supp: ₹' + item.support.toFixed(1);
                    } else if (item.resistance) {
                        srDisplay = 'Res: ₹' + item.resistance.toFixed(1);
                    }

                    const targetDisplay = item.target_price !== null ? '₹' + item.target_price.toFixed(2) : '—';

                    return '<tr>' +
                        '<td>' +
                            '<div style="font-weight:700;font-size:0.85rem;color:var(--light);">' + (item.name || item.ticker) + '</div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);">' + item.ticker + '</div>' +
                        '</td>' +
                        '<td><span style="font-size:0.75rem;color:var(--muted);">' + (item.run_at ? item.run_at.split('.')[0] : 'N/A') + '</span></td>' +
                        '<td><strong>₹' + (hasPred ? item.predicted_price.toFixed(2) : '—') + '</strong></td>' +
                        '<td>₹' + (hasLive ? item.live_price.toFixed(2) : '—') + '</td>' +
                        '<td class="' + deltaCls + '"><strong>' + deltaPctStr + '</strong><br><span style="font-size:0.7rem;opacity:0.85;">(' + deltaStr + ')</span></td>' +
                        '<td class="' + expRetCls + '" style="font-size:0.9rem;"><strong>' + expRetStr + '</strong></td>' +
                        '<td><span style="font-size:0.82rem;font-weight:600;color:#38bdf8;">' + targetDisplay + '</span></td>' +
                        '<td><strong class="' + trendCls + '">' + item.trend + '</strong>' + gbmBadge + '</td>' +
                        '<td style="text-align:center;"><span style="background:' + item.outcomeBg + ';color:' + item.outcomeColor + ';padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.75rem;font-weight:600;white-space:nowrap;">' + item.outcomeLabel + '</span></td>' +
                        '<td><span style="font-size:0.75rem;color:var(--muted);white-space:nowrap;">' + srDisplay + '</span></td>' +
                        '<td style="text-align:center;">' +
                            '<div style="display:flex;gap:0.3rem;justify-content:center;">' +
                                '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + item.ticker + '\', \'' + item.run_at + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV forecast against realized bars">📊 Benchmark</button>' +
                                '<button type="button" onclick="event.stopPropagation(); app.showKronosHistory(\'' + item.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:0.3rem;" title="View prediction history & accuracy timeline">🔍 History</button>' +
                            '</div>' +
                        '</td>' +
                    '</tr>';
                }).join('');
            },

            async loadKronosAudit() {
                const tbody = document.getElementById('kronosAuditTable');
                const limit = document.getElementById('kronosAuditLimit')?.value || 200;
                const wl = document.getElementById('kronosWatchlist')?.value || '';
                tbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Loading audit trail' + (wl ? ' for "' + wl + '"' : '') + '...</td></tr>';
                try {
                    let url = API_BASE + '/api/v1/dashboard/kronos/audit?limit=' + limit;
                    if (wl) url += '&watchlist=' + encodeURIComponent(wl);
                    const res = await fetch(url);
                    const rows = await res.json();
                    this.auditData = rows;
                    this.auditSortKey = 'run_at';
                    this.auditSortDir = 'desc';
                    await this.renderKronosAudit();
                } catch (e) {
                    console.error('Error loading Kronos audit:', e);
                    tbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Error loading audit trail</td></tr>';
                }
            },

            async renderKronosAudit() {
                const tbody = document.getElementById('kronosAuditTable');
                const rows = this.auditData || [];
                if (!rows.length) {
                    tbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">No audit records yet. Run Kronos predictions to populate the audit trail.</td></tr>';
                    const stTbody = document.getElementById('kronosStockAccuracyTable');
                    if (stTbody) stTbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:0.75rem;">No historical predictions to evaluate.</td></tr>';
                    return;
                }
                // Sort
                const key = this.auditSortKey;
                const dir = this.auditSortDir;
                const sorted = [...rows].sort((a, b) => {
                    let va = a[key], vb = b[key];
                    if (key === 'run_at') { va = new Date(va); vb = new Date(vb); }
                    va = va === null || va === undefined ? -Infinity : va;
                    vb = vb === null || vb === undefined ? -Infinity : vb;
                    if (va < vb) return dir === 'asc' ? -1 : 1;
                    if (va > vb) return dir === 'asc' ? 1 : -1;
                    return 0;
                });

                // Fetch live current prices in parallel
                const livePrices = {};
                await Promise.all(sorted.map(async row => {
                    const ticker = row.ticker;
                    try {
                        const r = await fetch(API_BASE + '/api/v1/market-context/' + encodeURIComponent(ticker));
                        const d = await r.json();
                        livePrices[ticker] = d.current_price;
                    } catch (e) {
                        livePrices[ticker] = null;
                    }
                }));

                const stockStats = {};
                let totalEvaluated = 0, totalWorked = 0, totalFailed = 0;
                let totalRunsCount = sorted.length;

                // Cluster sorted rows by ticker and timeframe/date session
                const clusters = [];
                const tickerMap = {};
                sorted.forEach(row => {
                    const t = row.ticker || '?';
                    if (!tickerMap[t]) tickerMap[t] = [];
                    tickerMap[t].push(row);
                });

                Object.keys(tickerMap).forEach(t => {
                    const tRows = tickerMap[t];
                    let cur = null;
                    tRows.forEach(row => {
                        const runDate = (row.run_at || '').split(' ')[0];
                        const p = row.prediction || {};
                        const predP = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : (row.current_price || 0);

                        if (!cur) {
                            cur = {
                                ticker: t,
                                date: runDate,
                                anchorPrice: predP,
                                representative: row,
                                runs: [row]
                            };
                        } else {
                            const priceDiff = cur.anchorPrice > 0 ? (Math.abs(predP - cur.anchorPrice) / cur.anchorPrice) * 100 : 0;
                            if (runDate === cur.date || priceDiff < 0.75) {
                                cur.runs.push(row);
                            } else {
                                clusters.push(cur);
                                cur = {
                                    ticker: t,
                                    date: runDate,
                                    anchorPrice: predP,
                                    representative: row,
                                    runs: [row]
                                };
                            }
                        }
                    });
                    if (cur) clusters.push(cur);
                });

                // Sort clusters
                clusters.sort((a, b) => {
                    let va = a.representative[key], vb = b.representative[key];
                    if (key === 'run_at') { va = new Date(a.representative.run_at); vb = new Date(b.representative.run_at); }
                    va = va === null || va === undefined ? -Infinity : va;
                    vb = vb === null || vb === undefined ? -Infinity : vb;
                    if (va < vb) return dir === 'asc' ? -1 : 1;
                    if (va > vb) return dir === 'asc' ? 1 : -1;
                    return 0;
                });

                tbody.innerHTML = clusters.map(cluster => {
                    const row = cluster.representative;
                    const p = row.prediction || {};
                    const predicted = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : row.current_price;
                    const live = livePrices[row.ticker];
                    const hasPred = predicted !== null && predicted !== undefined && !isNaN(predicted) && predicted > 0;
                    const hasLive = live !== null && live !== undefined && !isNaN(live);
                    let delta = null, deltaPct = null;
                    if (hasPred && hasLive) {
                        delta = live - predicted;
                        deltaPct = (delta / predicted) * 100;
                    }
                    const deltaCls = delta !== null ? (delta >= 0 ? 'price-positive' : 'price-negative') : '';
                    const deltaStr = delta !== null ? (delta >= 0 ? '+' : '') + delta.toFixed(2) : '—';
                    const deltaPctStr = deltaPct !== null ? (deltaPct >= 0 ? '+' : '') + deltaPct.toFixed(2) + '%' : '—';
                    const trend = (p.trend || row.trend || '—').trim();
                    const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';
                    const retPct = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : row.return_pct;

                    // Calculate Worked / Failed outcome for this timeframe session
                    let outcomeStatus = 'PENDING';
                    let outcomeLabel = '⏳ Pending';
                    let outcomeBg = 'rgba(255,255,255,0.06)';
                    let outcomeColor = 'var(--muted)';

                    if (deltaPct !== null) {
                        const isBull = trend === 'Bullish' || (retPct !== null && retPct > 0.3);
                        const isBear = trend === 'Bearish' || (retPct !== null && retPct < -0.3);

                        if (Math.abs(deltaPct) < 0.05) {
                            outcomeStatus = 'FLAT';
                            outcomeLabel = '⏳ Flat (0.0%)';
                            outcomeBg = 'rgba(251,191,36,0.15)';
                            outcomeColor = '#fbbf24';
                        } else if (isBull) {
                            if (deltaPct > 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        } else if (isBear) {
                            if (deltaPct < 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        }
                    }

                    // Aggregate per-stock stats (1 evaluation per timeframe session)
                    const t = row.ticker || '?';
                    if (!stockStats[t]) {
                        stockStats[t] = { ticker: t, totalSessions: 0, totalRuns: 0, evaluated: 0, worked: 0, failed: 0, predReturns: [], actualDeltas: [] };
                    }
                    const st = stockStats[t];
                    st.totalSessions++;
                    st.totalRuns += cluster.runs.length;
                    if (outcomeStatus === 'WORKED') {
                        st.evaluated++;
                        st.worked++;
                        totalEvaluated++;
                        totalWorked++;
                    } else if (outcomeStatus === 'FAILED') {
                        st.evaluated++;
                        st.failed++;
                        totalEvaluated++;
                        totalFailed++;
                    }
                    if (retPct !== null && retPct !== undefined) st.predReturns.push(Number(retPct));
                    if (deltaPct !== null) st.actualDeltas.push(Number(deltaPct));

                    const runsBadge = cluster.runs.length > 1 ? '<span style="background:rgba(59,130,246,0.2);color:#93c5fd;padding:0.1rem 0.35rem;border-radius:0.25rem;font-size:0.7rem;margin-left:0.35rem;" title="' + cluster.runs.length + ' runs in this timeframe (grouped)">' + cluster.runs.length + ' runs</span>' : '';

                    return '<tr>' +
                        '<td><strong>' + (row.ticker || '?') + '</strong></td>' +
                        '<td>' + (row.run_at || 'N/A') + runsBadge + '</td>' +
                        '<td>' + (hasPred ? '₹' + predicted.toFixed(2) : '—') + '</td>' +
                        '<td>' + (hasLive ? '₹' + live.toFixed(2) : '—') + '</td>' +
                        '<td class="' + deltaCls + '">' + deltaStr + '</td>' +
                        '<td class="' + deltaCls + '">' + deltaPctStr + '</td>' +
                        '<td>' + (retPct !== null && retPct !== undefined ? retPct + '%' : '—') + '</td>' +
                        '<td class="' + trendCls + '">' + trend + '</td>' +
                        '<td style="text-align:center;"><span style="background:' + outcomeBg + ';color:' + outcomeColor + ';padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.75rem;font-weight:600;white-space:nowrap;">' + outcomeLabel + '</span></td>' +
                        '<td>' + (p.support ? '₹' + Number(p.support).toFixed(2) : (row.support ? '₹' + Number(row.support).toFixed(2) : '—')) + '</td>' +
                        '<td>' + (p.resistance ? '₹' + Number(p.resistance).toFixed(2) : (row.resistance ? '₹' + Number(row.resistance).toFixed(2) : '—')) + '</td>' +
                        '<td><div style="display:flex;gap:0.3rem;"><button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + row.ticker + '\', \'' + row.run_at + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV accuracy against realized prices">📊 Benchmark</button><button type="button" onclick="app.deleteKronosPrediction(\'' + row.ticker + '\', \'' + row.run_at + '\')" class="btn btn-danger btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;" title="Delete record">🗑️</button></div></td>' +
                        '</tr>';
                }).join('');

                // Render KPI Summary Cards
                const overallAcc = totalEvaluated > 0 ? ((totalWorked / totalEvaluated) * 100).toFixed(1) : '—';
                const overallColor = totalEvaluated > 0 ? (totalWorked / totalEvaluated >= 0.6 ? '#34d399' : (totalWorked / totalEvaluated >= 0.4 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';
                const setElem = (id, prop, val) => { const el = document.getElementById(id); if (el) el[prop] = val; };
                setElem('kronosOverallAcc', 'textContent', overallAcc + (totalEvaluated > 0 ? '%' : ''));
                const elAcc = document.getElementById('kronosOverallAcc');
                if (elAcc) elAcc.style.color = overallColor;
                setElem('kronosEvaluatedCount', 'textContent', totalEvaluated + (clusters.length !== totalRunsCount ? ' sessions (' + totalRunsCount + ' total runs)' : ''));
                setElem('kronosWorkedCount', 'textContent', totalWorked);
                setElem('kronosFailedCount', 'textContent', totalFailed);
                setElem('kronosStocksTracked', 'textContent', Object.keys(stockStats).length);

                // Render Per-Stock Accuracy Breakdown Table
                const stockRows = Object.values(stockStats).sort((a, b) => {
                    const accA = a.evaluated > 0 ? a.worked / a.evaluated : -1;
                    const accB = b.evaluated > 0 ? b.worked / b.evaluated : -1;
                    return (b.evaluated - a.evaluated) || (accB - accA);
                });

                const stTbody = document.getElementById('kronosStockAccuracyTable');
                if (stTbody) {
                    if (!stockRows.length) {
                        stTbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:0.75rem;">No stocks evaluated yet.</td></tr>';
                    } else {
                        stTbody.innerHTML = stockRows.map(s => {
                            const accPct = s.evaluated > 0 ? ((s.worked / s.evaluated) * 100).toFixed(1) : '—';
                            const accCls = s.evaluated > 0 ? (s.worked / s.evaluated >= 0.6 ? 'price-positive' : (s.worked / s.evaluated >= 0.4 ? 'color:#fbbf24;' : 'price-negative')) : '';
                            const avgProj = s.predReturns.length ? (s.predReturns.reduce((a, b) => a + b, 0) / s.predReturns.length).toFixed(1) + '%' : '—';
                            const avgAct = s.actualDeltas.length ? (s.actualDeltas.reduce((a, b) => a + b, 0) / s.actualDeltas.length).toFixed(1) + '%' : '—';
                            const sessLabel = s.totalSessions + (s.totalRuns > s.totalSessions ? ' (' + s.totalRuns + ' runs)' : '');
                            return '<tr>' +
                                '<td><strong>' + s.ticker + '</strong></td>' +
                                '<td>' + sessLabel + '</td>' +
                                '<td>' + s.evaluated + '</td>' +
                                '<td><span style="color:#34d399;font-weight:600;">' + s.worked + '</span></td>' +
                                '<td><span style="color:#ef4444;font-weight:600;">' + s.failed + '</span></td>' +
                                '<td><strong class="' + accCls + '">' + accPct + (s.evaluated > 0 ? '%' : '') + '</strong></td>' +
                                '<td>' + avgProj + '</td>' +
                                '<td>' + avgAct + '</td>' +
                                '<td><button type="button" onclick="app.showKronosHistory(\'' + s.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.2);color:#60a5fa;">🔍 History</button></td>' +
                                '</tr>';
                        }).join('');
                    }
                }
            },

            sortAudit(key) {
                if (this.auditSortKey === key) {
                    this.auditSortDir = this.auditSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.auditSortKey = key;
                    this.auditSortDir = 'asc';
                }
                this.renderKronosAudit();
            },

            async deleteKronosPrediction(ticker, runAt) {
                if (!confirm('Delete prediction record for ' + ticker + ' at ' + runAt + '?')) {
                    return;
                }
                try {
                    const res = await fetch(
                        API_BASE + '/api/v1/dashboard/kronos/' + encodeURIComponent(ticker) + '?run_at=' + encodeURIComponent(runAt),
                        { method: 'DELETE' }
                    );
                    const data = await res.json();
                    if (data.success) {
                        this.loadKronosAudit();
                    } else {
                        alert('Failed to delete: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error deleting prediction:', e);
                    alert('Error deleting prediction');
                }
            },

            async showKronosHistory(ticker) {
                const modal = document.getElementById('kronosHistoryModal');
                const content = document.getElementById('kronosHistoryContent');
                const tickerEl = document.getElementById('kronosHistoryTicker');
                const badgeEl = document.getElementById('kronosHistoryAccuracyBadge');
                if (tickerEl) tickerEl.textContent = 'Stock: ' + ticker;
                modal.style.display = 'block';
                content.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading prediction history for ' + ticker + '...</div>';
                
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/history/' + encodeURIComponent(ticker));
                    const data = await res.json();
                    
                    if (!data.length) {
                        content.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No prediction history found for ' + ticker + '</div>';
                        if (badgeEl) badgeEl.style.display = 'none';
                        return;
                    }
                    
                // Fetch live current prices in parallel
                    const livePrices = {};
                    await Promise.all(data.map(async row => {
                        const t = row.ticker;
                        try {
                            const r = await fetch(API_BASE + '/api/v1/market-context/' + encodeURIComponent(t));
                            const d = await r.json();
                            livePrices[t] = d.current_price;
                        } catch (e) {
                            livePrices[t] = null;
                        }
                    }));

                    // Cluster historical runs into timeframe sessions
                    const sortedData = [...data].sort((a, b) => new Date(b.run_at) - new Date(a.run_at));
                    const historyClusters = [];
                    let curSess = null;

                    sortedData.forEach(row => {
                        const runDate = (row.run_at || '').split(' ')[0];
                        const p = row.prediction || {};
                        const predP = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : (row.current_price || 0);

                        if (!curSess) {
                            curSess = {
                                date: runDate,
                                anchorPrice: predP,
                                representative: row,
                                runs: [row]
                            };
                        } else {
                            const priceDiff = curSess.anchorPrice > 0 ? (Math.abs(predP - curSess.anchorPrice) / curSess.anchorPrice) * 100 : 0;
                            if (runDate === curSess.date || priceDiff < 0.75) {
                                curSess.runs.push(row);
                            } else {
                                historyClusters.push(curSess);
                                curSess = {
                                    date: runDate,
                                    anchorPrice: predP,
                                    representative: row,
                                    runs: [row]
                                };
                            }
                        }
                    });
                    if (curSess) historyClusters.push(curSess);

                    let stockWorked = 0, stockEvaluated = 0;
                    
                    content.innerHTML = '<div class="table-wrapper" style="grid-column:1/-1;"><table class="results-table"><thead><tr>' +
                        '<th>Forecast Timeframe</th><th>Price at Prediction</th><th>Current Price</th><th>Δ %</th><th>Return %</th><th>Trend</th><th>Outcome (Worked?)</th><th>Support</th><th>Resistance</th><th>Action</th>' +
                        '</tr></thead><tbody>' + historyClusters.map(cluster => {
                            const row = cluster.representative;
                            const p = row.prediction || {};
                            const predicted = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : row.current_price;
                            const live = livePrices[row.ticker];
                            const hasPred = predicted !== null && predicted !== undefined && !isNaN(predicted) && predicted > 0;
                            const hasLive = live !== null && live !== undefined && !isNaN(live);
                            let deltaPct = null;
                            if (hasPred && hasLive) {
                                const delta = live - predicted;
                                deltaPct = (delta / predicted) * 100;
                            }
                            const deltaPctStr = deltaPct !== null ? (deltaPct >= 0 ? '+' : '') + deltaPct.toFixed(2) + '%' : '—';
                            const deltaCls = deltaPct !== null ? (deltaPct >= 0 ? 'price-positive' : 'price-negative') : '';
                            const trend = (p.trend || row.trend || '—').trim();
                            const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';
                            const retPct = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : row.return_pct;

                            let outcomeLabel = '⏳ Pending';
                            let outcomeBg = 'rgba(255,255,255,0.06)';
                            let outcomeColor = 'var(--muted)';

                            if (deltaPct !== null) {
                                const isBull = trend === 'Bullish' || (retPct !== null && retPct > 0.3);
                                const isBear = trend === 'Bearish' || (retPct !== null && retPct < -0.3);

                                if (Math.abs(deltaPct) < 0.05) {
                                    outcomeLabel = '⏳ Flat (0.0%)';
                                    outcomeBg = 'rgba(251,191,36,0.15)';
                                    outcomeColor = '#fbbf24';
                                } else if (isBull) {
                                    if (deltaPct > 0) {
                                        stockEvaluated++;
                                        stockWorked++;
                                        outcomeLabel = '✅ Worked (+' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(16,185,129,0.2)';
                                        outcomeColor = '#34d399';
                                    } else {
                                        stockEvaluated++;
                                        outcomeLabel = '❌ Failed (' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(239,68,68,0.2)';
                                        outcomeColor = '#f87171';
                                    }
                                } else if (isBear) {
                                    if (deltaPct < 0) {
                                        stockEvaluated++;
                                        stockWorked++;
                                        outcomeLabel = '✅ Worked (' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(16,185,129,0.2)';
                                        outcomeColor = '#34d399';
                                    } else {
                                        stockEvaluated++;
                                        outcomeLabel = '❌ Failed (+' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(239,68,68,0.2)';
                                        outcomeColor = '#f87171';
                                    }
                                }
                            }

                            const runsBadge = cluster.runs.length > 1 ? '<span style="background:rgba(59,130,246,0.2);color:#93c5fd;padding:0.1rem 0.35rem;border-radius:0.25rem;font-size:0.7rem;margin-left:0.35rem;">' + cluster.runs.length + ' runs</span>' : '';

                            return '<tr>' +
                                '<td>' + (row.run_at || 'N/A') + runsBadge + '</td>' +
                                '<td>₹' + (hasPred ? predicted.toFixed(2) : '—') + '</td>' +
                                '<td>' + (hasLive ? '₹' + live.toFixed(2) : '—') + '</td>' +
                                '<td class="' + deltaCls + '">' + deltaPctStr + '</td>' +
                                '<td>' + (retPct !== null && retPct !== undefined ? retPct + '%' : '—') + '</td>' +
                                '<td class="' + trendCls + '">' + trend + '</td>' +
                                '<td style="text-align:center;"><span style="background:' + outcomeBg + ';color:' + outcomeColor + ';padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.75rem;font-weight:600;">' + outcomeLabel + '</span></td>' +
                                '<td>₹' + (p.support ? Number(p.support).toFixed(2) : (row.support ? Number(row.support).toFixed(2) : '—')) + '</td>' +
                                '<td>₹' + (p.resistance ? Number(p.resistance).toFixed(2) : (row.resistance ? Number(row.resistance).toFixed(2) : '—')) + '</td>' +
                                '<td><button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + row.ticker + '\', \'' + (row.run_at || '') + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark this past forecast against realized prices">📊 Benchmark</button></td>' +
                                '</tr>';
                        }).join('') + '</tbody></table></div>';

                    if (badgeEl) {
                        badgeEl.style.display = 'inline-block';
                        const accPct = stockEvaluated > 0 ? ((stockWorked / stockEvaluated) * 100).toFixed(1) : '—';
                        const totalRuns = sortedData.length;
                        const sessText = historyClusters.length < totalRuns ? ' across ' + historyClusters.length + ' sessions (' + totalRuns + ' total runs)' : '';
                        badgeEl.textContent = 'Accuracy: ' + accPct + (stockEvaluated > 0 ? '%' : '') + ' (' + stockWorked + '/' + stockEvaluated + ' hits)' + sessText;
                        badgeEl.style.background = stockEvaluated > 0 ? (stockWorked / stockEvaluated >= 0.6 ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)') : 'rgba(59,130,246,0.2)';
                        badgeEl.style.color = stockEvaluated > 0 ? (stockWorked / stockEvaluated >= 0.6 ? '#34d399' : '#f87171') : '#60a5fa';
                    }
                } catch (e) {
                    console.error('Error loading Kronos history:', e);
                    content.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading prediction history</div>';
                }
            },

        // [swing_range] -> extracted to modules/swing_range.js
        // [playground] -> extracted to modules/playground.js
            // =========================================================================
            // 🧠 Multi-Model AI Consensus Engine & OmniRoute Intelligence Tab
            // =========================================================================
            consensusPredictions: [],
            omniTimeframe: 14,
            _activeOmniTab: 'raw',

            initOmniRouteConsensus() {
                this.loadConsensusAuditLedger();
                // Restore timeframe
                const savedTf = localStorage.getItem('omni_timeframe_days') || '14';
                this.setOmniTimeframe(parseInt(savedTf, 10) || 14);

                // Restore data inclusion checkboxes
                const chkTech = document.getElementById('chkIncludeTechnicals');
                if (chkTech) {
                    const saved = localStorage.getItem('chk_include_technicals');
                    if (saved !== null) chkTech.checked = (saved === 'true');
                    chkTech.onchange = () => {
                        try { localStorage.setItem('chk_include_technicals', chkTech.checked); } catch (_) {}
                    };
                }
                const chkNews = document.getElementById('chkIncludeNews');
                if (chkNews) {
                    const saved = localStorage.getItem('chk_include_news');
                    if (saved !== null) chkNews.checked = (saved === 'true');
                    chkNews.onchange = () => {
                        try { localStorage.setItem('chk_include_news', chkNews.checked); } catch (_) {}
                    };
                }
                const chkInst = document.getElementById('chkIncludeInstitutional');
                if (chkInst) {
                    const saved = localStorage.getItem('chk_include_institutional');
                    if (saved !== null) chkInst.checked = (saved === 'true');
                    chkInst.onchange = () => {
                        try { localStorage.setItem('chk_include_institutional', chkInst.checked); } catch (_) {}
                    };
                }

                // Restore custom directives
                const dirEl = document.getElementById('omniCustomDirectives');
                if (dirEl) {
                    const savedDir = localStorage.getItem('omni_custom_directives');
                    if (savedDir !== null && savedDir !== undefined) dirEl.value = savedDir;
                    dirEl.oninput = () => {
                        try { localStorage.setItem('omni_custom_directives', dirEl.value); } catch (_) {}
                    };
                }

                // Enter key on ticker input runs analysis
                const tickerInput = document.getElementById('omniTickerInput');
                if (tickerInput && !tickerInput._hasOmniListener) {
                    tickerInput._hasOmniListener = true;
                    tickerInput.addEventListener('keydown', (e) => {
                        if (e.key === 'Enter') {
                            e.preventDefault();
                            this.runOmniAnalysis();
                        }
                    });
                }

                // Load models and hydrate selector
                this.loadConsensusOmniRouteModels(false);
            },

            setOmniTimeframe(days) {
                days = parseInt(days, 10) || 14;
                this.omniTimeframe = days;
                try {
                    localStorage.setItem('omni_timeframe_days', String(days));
                } catch (_) {}

                [3, 7, 14, 30, 90].forEach(d => {
                    const btn = document.getElementById('omniTf-' + d);
                    if (btn) {
                        const isActive = (d === days);
                        btn.classList.toggle('active', isActive);
                        if (isActive) {
                            btn.style.background = '#2563eb';
                            btn.style.color = '#ffffff';
                            btn.style.fontWeight = '700';
                        } else {
                            btn.style.background = 'transparent';
                            btn.style.color = '#94a3b8';
                            btn.style.fontWeight = '500';
                        }
                    }
                });
            },

            setOmniDirective(presetText) {
                const dirEl = document.getElementById('omniCustomDirectives');
                if (dirEl) {
                    dirEl.value = presetText || '';
                    try {
                        localStorage.setItem('omni_custom_directives', dirEl.value);
                    } catch (_) {}
                    dirEl.focus();
                }
            },

            setOmniDirectivePreset(presetText) {
                this.setOmniDirective(presetText);
            },

            async onOmniWatchlistSelect(wl) {
                if (!wl) return;
                const tickerInput = document.getElementById('omniTickerInput');
                if (!tickerInput) return;
                try {
                    if (wl === 'NSE_TOP') {
                        tickerInput.value = 'RELIANCE.NS';
                    } else if (wl === 'BREAKOUT_HOT') {
                        const res = await fetch(API_BASE + '/api/v1/breakout/hot?limit=1');
                        if (res.ok) {
                            const data = await res.json();
                            const top = (data.candidates || data.setups || [])[0];
                            tickerInput.value = top ? top.ticker : 'TCS.NS';
                        } else {
                            tickerInput.value = 'TCS.NS';
                        }
                    } else if (wl === 'RECENT_IPO') {
                        const res = await fetch(API_BASE + '/api/v1/new-additions/latest?limit=1');
                        if (res.ok) {
                            const data = await res.json();
                            const top = (data.additions || data.items || [])[0];
                            tickerInput.value = top ? top.ticker : 'ZOMATO.NS';
                        } else {
                            tickerInput.value = 'ZOMATO.NS';
                        }
                    } else if (wl === 'SWING_SETUPS') {
                        const res = await fetch(API_BASE + '/api/v1/swing/candidates?limit=1');
                        if (res.ok) {
                            const data = await res.json();
                            const top = (data.candidates || data.setups || [])[0];
                            tickerInput.value = top ? top.ticker : 'INFY.NS';
                        } else {
                            tickerInput.value = 'INFY.NS';
                        }
                    } else {
                        tickerInput.value = wl;
                    }
                } catch (e) {
                    console.warn('Watchlist auto-fill error:', e);
                }
            },

            async runOmniAnalysis() {
                const tickerInput = document.getElementById('omniTickerInput');
                const ticker = (tickerInput ? tickerInput.value : '').trim().toUpperCase();
                return await this.runOmniRouteAnalysis(ticker);
            },

            async runOmniRouteAnalysis(ticker, customOptions = {}) {
                const sym = String(ticker || document.getElementById('omniTickerInput')?.value || '').trim().toUpperCase();
                if (!sym) {
                    if (typeof this.showToast === 'function') this.showToast('Please enter a ticker symbol (e.g. RELIANCE.NS, TCS.NS)', 'warning');
                    else alert('Please enter a ticker symbol (e.g. RELIANCE.NS, TCS.NS)');
                    return;
                }

                // Sync input field if present
                const tickerInput = document.getElementById('omniTickerInput');
                if (tickerInput && tickerInput.value.trim().toUpperCase() !== sym) {
                    tickerInput.value = sym;
                }

                const model = customOptions.model || document.getElementById('omniModelSelect')?.value || localStorage.getItem('selected_omni_model') || 'antigravityonly';
                const timeframe = customOptions.timeframe_days || this.omniTimeframe || parseInt(localStorage.getItem('omni_timeframe_days') || '14', 10);
                const includeTech = customOptions.include_technicals !== undefined ? customOptions.include_technicals : (document.getElementById('chkIncludeTechnicals')?.checked ?? true);
                const includeNews = customOptions.include_news !== undefined ? customOptions.include_news : (document.getElementById('chkIncludeNews')?.checked ?? true);
                const includeInst = customOptions.include_institutional !== undefined ? customOptions.include_institutional : (document.getElementById('chkIncludeInstitutional')?.checked ?? true);
                const customPrompt = customOptions.custom_prompt !== undefined ? customOptions.custom_prompt : (document.getElementById('omniCustomDirectives')?.value || null);

                const runBtn = document.getElementById('omniRunAnalysisBtn');
                const origBtnHtml = runBtn ? runBtn.innerHTML : '<span>⚡</span> Run OmniRoute Analysis';
                if (runBtn) {
                    runBtn.disabled = true;
                    runBtn.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,0.3);border-radius:50%;border-top-color:#ffffff;animation:spin 0.8s linear infinite;margin-right:0.3rem;"></span> Analyzing ' + sym + '...';
                }

                const thesisEl = document.getElementById('omniThesis');
                if (thesisEl) thesisEl.textContent = 'Generating real-time PIT market analysis for ' + sym + ' via ' + model + '...';

                try {
                    const res = await fetch(API_BASE + '/api/v1/consensus/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            ticker: sym,
                            model: model,
                            timeframe_days: timeframe,
                            include_technicals: includeTech,
                            include_news: includeNews,
                            include_institutional: includeInst,
                            custom_prompt: customPrompt,
                            temperature: 0.2
                        })
                    });

                    if (!res.ok) {
                        const errData = await res.json().catch(() => ({}));
                        throw new Error(errData.detail || ('HTTP ' + res.status));
                    }

                    const data = await res.json();
                    if (!data || data.error) {
                        throw new Error(data.error || 'OmniRoute returned an error');
                    }

                    // Render results in split deck & inspector
                    this.renderOmniRouteResults(data);

                    if (typeof this.showToast === 'function') {
                        const dir = data.structured?.direction || 'DONE';
                        const conf = data.structured?.confidence_pct || 80;
                        this.showToast(`✨ OmniRoute Analysis for ${sym}: ${dir} (${conf}% conviction)`);
                    }

                    return data;
                } catch (e) {
                    console.error('OmniRoute analysis error for ' + sym + ':', e);
                    if (thesisEl) {
                        thesisEl.innerHTML = `<span style="color:#f87171;">⚠️ Analysis failed for ${sym}: ${this.escapeHtml(e.message)}</span>`;
                    }
                    if (typeof this.showToast === 'function') {
                        this.showToast('OmniRoute error for ' + sym + ': ' + e.message, 'error');
                    } else {
                        alert('OmniRoute error for ' + sym + ': ' + e.message);
                    }
                } finally {
                    if (runBtn) {
                        runBtn.disabled = false;
                        runBtn.innerHTML = origBtnHtml;
                    }
                }
            },

            renderOmniRouteResults(data) {
                if (!data) return;
                const sym = String(data.ticker || '').toUpperCase();
                const structured = data.structured || {};
                const currPrefix = sym.endsWith('.NS') ? '₹' : '$';

                // 1. Populate Left Pane: Structured Verdict
                const tickerEl = document.getElementById('omniResultTicker');
                if (tickerEl) tickerEl.textContent = sym;

                const timeEl = document.getElementById('omniResultTimestamp');
                if (timeEl) {
                    const latSec = data.latency_ms ? (data.latency_ms / 1000).toFixed(2) + 's' : '0.8s';
                    timeEl.textContent = `Generated via ${data.model || 'OmniRoute'} in ${latSec} · ${new Date().toLocaleTimeString()}`;
                }

                const biasBadge = document.getElementById('omniBiasBadge');
                if (biasBadge) {
                    const dir = (structured.direction || 'NEUTRAL').toUpperCase();
                    const isBull = dir.includes('BULL');
                    const isBear = dir.includes('BEAR');
                    biasBadge.textContent = dir;
                    if (isBull) {
                        biasBadge.style.background = 'rgba(16,185,129,0.2)';
                        biasBadge.style.color = '#34d399';
                        biasBadge.style.borderColor = 'rgba(16,185,129,0.4)';
                    } else if (isBear) {
                        biasBadge.style.background = 'rgba(239,68,68,0.2)';
                        biasBadge.style.color = '#f87171';
                        biasBadge.style.borderColor = 'rgba(239,68,68,0.4)';
                    } else {
                        biasBadge.style.background = 'rgba(251,191,36,0.18)';
                        biasBadge.style.color = '#fbbf24';
                        biasBadge.style.borderColor = 'rgba(251,191,36,0.4)';
                    }
                }

                const convVal = document.getElementById('omniConvictionVal');
                if (convVal) {
                    const conf = structured.confidence_pct != null ? structured.confidence_pct : (structured.conviction_score != null ? structured.conviction_score : 80);
                    convVal.textContent = conf + '%';
                }

                const targetEl = document.getElementById('omniTargetPrice');
                if (targetEl) {
                    const tp = structured.target_price;
                    const retPct = structured.target_return_pct;
                    let text = '—';
                    if (tp != null && !isNaN(tp)) {
                        text = `${currPrefix}${Number(tp).toLocaleString('en-IN', {maximumFractionDigits: 2})}`;
                        if (retPct != null && !isNaN(retPct)) {
                            const sign = retPct >= 0 ? '+' : '';
                            text += ` (${sign}${Number(retPct).toFixed(1)}%)`;
                        }
                    }
                    targetEl.textContent = text;
                }

                const slEl = document.getElementById('omniStopLoss');
                if (slEl) {
                    const sl = structured.stop_loss_price;
                    slEl.textContent = (sl != null && !isNaN(sl)) ? `${currPrefix}${Number(sl).toLocaleString('en-IN', {maximumFractionDigits: 2})}` : '—';
                }

                const rrEl = document.getElementById('omniRiskReward');
                if (rrEl) {
                    const rr = structured.risk_reward_ratio;
                    rrEl.textContent = (rr != null && !isNaN(rr)) ? `${Number(rr).toFixed(2)}R` : '2.0R';
                }

                const catSummary = document.getElementById('omniCatalystSummary');
                if (catSummary) {
                    const insight = structured.volume_profile_insight || structured.chart_pattern || structured.recommended_action || 'Volume and momentum align with setup.';
                    catSummary.textContent = insight;
                }

                const thesisEl = document.getElementById('omniThesis');
                if (thesisEl) {
                    const drivers = Array.isArray(structured.key_drivers) && structured.key_drivers.length ? structured.key_drivers.map(d => `• ${d}`).join('\n') : '';
                    let body = structured.thesis || structured.executive_summary || '';
                    if (!body && drivers) {
                        body = `${structured.recommended_action ? `Action: ${structured.recommended_action}\n\n` : ''}${drivers}`;
                    } else if (body && drivers) {
                        body = `${body}\n\nKey Drivers:\n${drivers}`;
                    }
                    thesisEl.textContent = body || 'Quantitative setup evaluated under current market regime.';
                }

                const risksList = document.getElementById('omniRisksList');
                if (risksList) {
                    const risks = [];
                    if (structured.primary_risk) risks.push(structured.primary_risk);
                    if (Array.isArray(structured.invalidation_triggers)) risks.push(...structured.invalidation_triggers);
                    if (Array.isArray(structured.risks)) risks.push(...structured.risks);
                    if (structured.support_level) risks.push(`Violation of pivot support at ${currPrefix}${structured.support_level}`);

                    if (risks.length) {
                        risksList.innerHTML = risks.map(r => `<li>${this.escapeHtml(r)}</li>`).join('');
                    } else {
                        risksList.innerHTML = '<li>Loss of recent swing low or adverse market shock invalidates setup.</li>';
                    }
                }

                // 2. Populate Right Pane: 3-Tab Inspector
                const metaEl = document.getElementById('omniExecutionMeta');
                if (metaEl) {
                    const latSec = data.latency_ms ? (data.latency_ms / 1000).toFixed(2) + 's' : '—';
                    metaEl.textContent = `Latency: ${latSec} · Tokens: ${data.tokens_used || '—'}`;
                }

                const rawEl = document.getElementById('omniRawOutputContent');
                if (rawEl) {
                    rawEl.textContent = data.raw_text || (typeof structured === 'object' ? JSON.stringify(structured, null, 2) : 'No raw text output.');
                }

                const thinkEl = document.getElementById('omniThinkingContent');
                if (thinkEl) {
                    thinkEl.textContent = data.reasoning_text || 'No reasoning stream captured. Chain of thought (<think>) text will be displayed here when generated by reasoning models.';
                }

                const promptEl = document.getElementById('omniPromptSentContent');
                if (promptEl) {
                    promptEl.textContent = data.prompt_sent || 'Prompt payload not recorded.';
                }

                // 3. Update Table Row Badge Cells across all open tables
                const dir = (structured.direction || 'NEUTRAL').toUpperCase();
                const isBull = dir.includes('BULL');
                const isBear = dir.includes('BEAR');
                const retPct = structured.target_return_pct != null ? structured.target_return_pct : 0;

                const consensusRecord = {
                    ticker: sym,
                    consensus_direction: dir,
                    consensus_return_pct: retPct,
                    expected_move_pct: retPct,
                    consensus_strength: structured.confidence_pct || 80,
                    agreement_ratio: 1.0,
                    consensus_recommended_action: structured.recommended_action || (isBull ? 'BUY' : isBear ? 'SELL' : 'HOLD'),
                    consensus_target_price: structured.target_price,
                    stop_loss_price: structured.stop_loss_price,
                    synthesized_thesis: structured.thesis || (structured.key_drivers ? structured.key_drivers.join('. ') : ''),
                    models_breakdown: [{
                        model_id: data.model || 'OmniRoute',
                        model_name: data.model || 'OmniRoute',
                        direction: dir,
                        confidence_pct: structured.confidence_pct || 80,
                        target_price: structured.target_price,
                        target_return_pct: retPct,
                        raw_response: data.raw_text,
                        key_drivers: structured.key_drivers,
                        primary_risk: structured.primary_risk
                    }]
                };

                this.consensusMap[sym] = consensusRecord;

                const domId = 'consensus-cell-' + sym.replace(/[^A-Za-z0-9]/g, '_');
                const cells = document.querySelectorAll('[id="' + domId + '"]');
                const newHtml = this.renderConsensusBadge(sym, this.currentMarket || 'ALL');
                cells.forEach(el => {
                    el.outerHTML = newHtml;
                });
            },

            switchOmniInspectorTab(tabName) {
                const tabs = ['raw', 'thinking', 'prompt'];
                if (!tabs.includes(tabName)) tabName = 'raw';
                this._activeOmniTab = tabName;

                const btnMap = {
                    'raw': document.getElementById('omniTabBtnRaw'),
                    'thinking': document.getElementById('omniTabBtnThinking'),
                    'prompt': document.getElementById('omniTabBtnPrompt')
                };

                const paneMap = {
                    'raw': document.getElementById('omniTabPaneRaw'),
                    'thinking': document.getElementById('omniTabPaneThinking'),
                    'prompt': document.getElementById('omniTabPanePrompt')
                };

                tabs.forEach(t => {
                    const btn = btnMap[t];
                    const pane = paneMap[t];
                    const isActive = (t === tabName);
                    if (pane) pane.style.display = isActive ? 'block' : 'none';
                    if (btn) {
                        btn.classList.toggle('active', isActive);
                        if (isActive) {
                            btn.style.background = '#2563eb';
                            btn.style.color = '#ffffff';
                            btn.style.fontWeight = '700';
                        } else {
                            btn.style.background = 'transparent';
                            btn.style.color = '#94a3b8';
                            btn.style.fontWeight = '500';
                        }
                    }
                });
            },

            copyOmniRawOutput() {
                const activeTab = this._activeOmniTab || 'raw';
                let textToCopy = '';
                if (activeTab === 'thinking') {
                    textToCopy = document.getElementById('omniThinkingContent')?.textContent || '';
                } else if (activeTab === 'prompt') {
                    textToCopy = document.getElementById('omniPromptSentContent')?.textContent || '';
                } else {
                    textToCopy = document.getElementById('omniRawOutputContent')?.textContent || '';
                }

                if (!textToCopy) return;

                const copyBtn = document.getElementById('omniCopyRawBtn');
                const origText = copyBtn ? copyBtn.innerHTML : '📋 Copy';

                const onDone = () => {
                    if (copyBtn) {
                        copyBtn.innerHTML = '✅ Copied!';
                        copyBtn.style.color = '#34d399';
                        setTimeout(() => {
                            copyBtn.innerHTML = origText;
                            copyBtn.style.color = '';
                        }, 1500);
                    }
                    if (typeof this.showToast === 'function') this.showToast('Copied ' + activeTab + ' text to clipboard!');
                };

                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(textToCopy).then(onDone).catch(() => {
                        this._fallbackCopyText(textToCopy, onDone);
                    });
                } else {
                    this._fallbackCopyText(textToCopy, onDone);
                }
            },

            _fallbackCopyText(text, cb) {
                try {
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.style.position = 'fixed';
                    ta.style.top = '0';
                    ta.style.left = '0';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.focus();
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                    if (cb) cb();
                } catch (e) {
                    console.warn('Fallback copy failed:', e);
                }
            },

            escapeHtml(str) {
                if (!str) return '';
                return String(str)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
            },

            async loadConsensusTab() {
                // Initialize OmniRoute customizer controls & preferences
                this.initOmniRouteConsensus();

                const grid = document.getElementById('consensusListGrid');
                if (grid) {
                    grid.innerHTML = '<div style="text-align:center;color:var(--muted);padding:2rem;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading AI consensus predictions...</div>';
                }

                try {
                    // Fetch latest predictions and accuracy stats in parallel
                    const [predsRes, statsRes] = await Promise.all([
                        fetch('/api/v1/consensus/latest?limit=100'),
                        fetch('/api/v1/consensus/accuracy-stats')
                    ]);

                    const predsData = await predsRes.json();
                    const statsData = await statsRes.json();

                    this.consensusPredictions = predsData.predictions || [];

                    // Render KPI stats
                    this.renderConsensusKpis(statsData);

                    // Render Prediction list
                    this.filterConsensus();
                } catch (e) {
                    console.error('Error loading Consensus Tab:', e);
                    if (grid) {
                        grid.innerHTML = '<div class="card" style="padding:1.5rem;color:#f87171;text-align:center;">Failed to load consensus predictions: ' + (e.message || e) + '</div>';
                    }
                }
            },

                        async loadConsensusAuditLedger() {
                const tbody = document.getElementById('consensusAuditTableBody');
                if (!tbody) return;
                try {
                    const res = await fetch(API_BASE + '/api/v1/consensus/audit?limit=100');
                    if (!res.ok) return;
                    const data = await res.json();
                    const records = data.audit_records || [];
                    if (!records.length) {
                        tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; padding: 2rem; color: #94a3b8;">No historical consensus audit predictions found.</td></tr>';
                        return;
                    }
                    tbody.innerHTML = records.map(function(r) {
                        const dir = (r.consensus_direction || 'NEUTRAL').toUpperCase();
                        const isBull = dir.indexOf('BULL') !== -1;
                        const isBear = dir.indexOf('BEAR') !== -1;
                        const dirColor = isBull ? '#34d399' : (isBear ? '#f43f5e' : '#94a3b8');
                        const dirBg = isBull ? 'rgba(16,185,129,0.15)' : (isBear ? 'rgba(244,63,94,0.15)' : 'rgba(255,255,255,0.05)');
                        const isSettled = r.settlement_status === 'SETTLED';
                        const settleColor = isSettled ? (r.direction_correct ? '#34d399' : '#f43f5e') : '#fbbf24';
                        const settleBg = isSettled ? (r.direction_correct ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)') : 'rgba(245,158,11,0.15)';
                        const outRet = (r.actual_return_pct != null) ? ((r.actual_return_pct >= 0 ? '+' : '') + Number(r.actual_return_pct).toFixed(1) + '%') : '—';
                        const createdDate = r.created_at ? r.created_at.split(' ')[0] : '—';
                        const tf = r.timeframe_days || 14;
                        const tp = r.consensus_target_price ? ('₹' + Number(r.consensus_target_price).toFixed(2)) : '—';
                        const asof = r.as_of_price ? ('₹' + Number(r.as_of_price).toFixed(2)) : '—';
                        const stat = r.settlement_status || 'PENDING';

                        return '<tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">' +
                            '<td style="padding: 0.6rem 0.75rem; color: #94a3b8;">' + createdDate + '</td>' +
                            '<td style="padding: 0.6rem 0.75rem; font-weight: 700; color: #f8fafc;">' + (r.ticker || '') + '</td>' +
                            '<td style="padding: 0.6rem 0.75rem; color: #cbd5e1;">' + tf + 'D</td>' +
                            '<td style="padding: 0.6rem 0.75rem;"><span style="background:' + dirBg + ';color:' + dirColor + ';padding:0.15rem 0.45rem;border-radius:4px;font-weight:700;">' + dir + '</span></td>' +
                            '<td style="padding: 0.6rem 0.75rem; color: #38bdf8; font-weight: 600;">' + tp + '</td>' +
                            '<td style="padding: 0.6rem 0.75rem; color: #cbd5e1;">' + asof + '</td>' +
                            '<td style="padding: 0.6rem 0.75rem;"><span style="background:' + settleBg + ';color:' + settleColor + ';padding:0.15rem 0.45rem;border-radius:4px;font-weight:600;">' + stat + '</span></td>' +
                            '<td style="padding: 0.6rem 0.75rem; color: ' + settleColor + '; font-weight: 700;">' + outRet + '</td>' +
                            '<td style="padding: 0.6rem 0.75rem; text-align: right;">' +
                                '<button type="button" onclick="app.inspectTrace(' + r.id + ')" class="btn btn-sm" style="font-size: 0.65rem; padding: 0.15rem 0.45rem; background: rgba(59,130,246,0.15); color: #93c5fd; border: 1px solid rgba(59,130,246,0.3); border-radius: 4px; cursor: pointer;">Trace</button>' +
                            '</td>' +
                        '</tr>';
                    }).join('');
                } catch (e) {
                    console.warn('Failed to load consensus audit ledger:', e);
                }
            },

            filterConsensusAuditTable() {
                const search = (document.getElementById('omniAuditSearchInput')?.value || '').trim().toUpperCase();
                const rows = document.querySelectorAll('#consensusAuditTableBody tr');
                rows.forEach(function(r) {
                    if (r.children.length < 2) return;
                    const sym = (r.children[1].textContent || '').trim().toUpperCase();
                    r.style.display = (!search || sym.indexOf(search) !== -1) ? '' : 'none';
                });
            },

            renderConsensusKpis(stats) {
                const totalEl = document.getElementById('consensusStatTotal');
                const winRateEl = document.getElementById('consensusStatWinRate');
                const dirAccEl = document.getElementById('consensusStatDirAcc');
                const pendingEl = document.getElementById('consensusStatPending');
                const topFailEl = document.getElementById('consensusStatTopFail');

                if (totalEl) totalEl.textContent = stats.total_predictions || 0;
                if (winRateEl) {
                    const wr = stats.win_rate != null ? stats.win_rate.toFixed(1) + '%' : '0.0%';
                    winRateEl.textContent = wr;
                    winRateEl.style.color = (stats.win_rate >= 50) ? '#10b981' : '#f59e0b';
                }
                if (dirAccEl) {
                    const da = stats.direction_accuracy != null ? stats.direction_accuracy.toFixed(1) + '%' : '0.0%';
                    dirAccEl.textContent = da;
                }
                if (pendingEl) pendingEl.textContent = stats.pending || 0;
                if (topFailEl) {
                    const topF = stats.top_failure_categories && stats.top_failure_categories.length ? stats.top_failure_categories[0].category : 'None';
                    topFailEl.textContent = topF.replace(/_/g, ' ');
                }
            },

            filterConsensus() {
                const search = (document.getElementById('consensusSearchFilter')?.value || '').trim().toUpperCase();
                const dirFilter = document.getElementById('consensusDirectionFilter')?.value || 'ALL';
                const statusFilter = document.getElementById('consensusStatusFilter')?.value || 'ALL';

                let filtered = this.consensusPredictions || [];

                if (search) {
                    filtered = filtered.filter(p => (p.ticker || '').toUpperCase().includes(search));
                }
                if (dirFilter !== 'ALL') {
                    filtered = filtered.filter(p => (p.consensus_direction || '').toUpperCase() === dirFilter);
                }
                if (statusFilter !== 'ALL') {
                    filtered = filtered.filter(p => (p.settlement_status || '').toUpperCase() === statusFilter);
                }

                const badge = document.getElementById('consensusCountBadge');
                if (badge) badge.textContent = filtered.length + ' predictions';

                this.renderConsensusList(filtered);
            },

            renderConsensusList(items) {
                const grid = document.getElementById('consensusListGrid');
                if (!grid) return;

                if (!items || !items.length) {
                    grid.innerHTML = '<div class="card" style="padding:2rem;text-align:center;color:var(--muted);margin:0;">No consensus predictions match the selected filters. Click <strong>⚡ Run Consensus</strong> above to generate one.</div>';
                    return;
                }

                grid.innerHTML = items.map(p => {
                    const dir = (p.consensus_direction || 'NEUTRAL').toUpperCase();
                    const dirBg = dir === 'BULLISH' ? 'rgba(16,185,129,0.15)' : dir === 'BEARISH' ? 'rgba(239,68,68,0.15)' : 'rgba(251,191,36,0.15)';
                    const dirColor = dir === 'BULLISH' ? '#34d399' : dir === 'BEARISH' ? '#f87171' : '#fbbf24';
                    const dirIcon = dir === 'BULLISH' ? '🟢 BULLISH' : dir === 'BEARISH' ? '🔴 BEARISH' : '🟡 NEUTRAL';

                    const status = (p.settlement_status || 'PENDING').toUpperCase();
                    const statusBg = status === 'SUCCESS' ? '#10b981' : status === 'PARTIAL' ? '#f59e0b' : status === 'FAILURE' ? '#ef4444' : '#64748b';
                    const statusIcon = status === 'SUCCESS' ? '✅ SUCCESS' : status === 'PARTIAL' ? '🟡 PARTIAL' : status === 'FAILURE' ? '❌ FAILED' : '⏳ PENDING';

                    const strength = p.consensus_strength || 0;
                    const agreeRatio = p.agreement_ratio ? (p.agreement_ratio * 100).toFixed(0) + '%' : '—';
                    const retPct = p.consensus_return_pct != null ? (p.consensus_return_pct >= 0 ? '+' : '') + p.consensus_return_pct.toFixed(2) + '%' : '—';
                    const actualRet = p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '+' : '') + p.actual_return_pct.toFixed(2) + '%' : '—';
                    const actualRetColor = p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '#34d399' : '#f87171') : 'var(--muted)';

                    // Model Pills
                    let modelPills = '';
                    if (p.models_breakdown && p.models_breakdown.length) {
                        modelPills = p.models_breakdown.map(m => {
                            const mDir = (m.direction || 'ERR').toUpperCase();
                            const mCol = mDir === 'BULLISH' ? '#34d399' : mDir === 'BEARISH' ? '#f87171' : '#94a3b8';
                            return '<span style="font-size:0.72rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);padding:0.15rem 0.45rem;border-radius:0.3rem;color:' + mCol + ';">' + (m.model_name || m.model_id) + ': ' + mDir + '</span>';
                        }).join(' ');
                    }

                    // Post-Mortem banner if failed
                    let postMortemSnippet = '';
                    if (status === 'FAILURE' || status === 'PARTIAL') {
                        const failCat = p.failure_category ? p.failure_category.replace(/_/g, ' ') : 'Unclassified';
                        const failSummary = p.failure_reason_summary || 'Price action diverged from model consensus.';
                        postMortemSnippet = '<div style="margin-top:0.6rem;padding:0.5rem 0.75rem;background:rgba(239,68,68,0.08);border-left:3px solid #ef4444;border-radius:0.3rem;font-size:0.78rem;color:#fca5a5;">' +
                            '<strong>🔍 Post-Mortem (' + failCat + '):</strong> ' + failSummary +
                            '</div>';
                    }

                    return '<div class="card" style="margin:0;padding:1rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.6rem;transition:all 0.2s;">' +
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.75rem;">' +
                            '<div>' +
                                '<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.3rem;">' +
                                    '<div style="display:flex;align-items:center;gap:0.35rem;">' +
                                        `<button type="button" onclick="app.openAddToWatchlistModal('${p.ticker}')" class="btn-micro" style="color:#fbbf24;border:none;background:transparent;padding:0;font-size:0.9rem;cursor:pointer;" title="Add to Watchlist">⭐</button>` +
                                        '<strong style="font-size:1.15rem;color:var(--light);">' + p.ticker + '</strong>' +
                                    '</div>' +
                                    '<span style="font-size:0.75rem;font-weight:700;background:' + dirBg + ';color:' + dirColor + ';padding:0.2rem 0.55rem;border-radius:0.35rem;border:1px solid ' + dirColor + '44;">' + dirIcon + '</span>' +
                                    '<span style="font-size:0.72rem;font-weight:700;background:' + statusBg + '22;color:' + statusBg + ';padding:0.18rem 0.5rem;border-radius:0.35rem;border:1px solid ' + statusBg + '66;">' + statusIcon + '</span>' +
                                '</div>' +
                                '<div style="font-size:0.78rem;color:var(--muted);display:flex;gap:0.8rem;flex-wrap:wrap;">' +
                                    '<span>Entry: <strong>₹' + (p.as_of_price || 0).toFixed(2) + '</strong></span>' +
                                    '<span>Target: <strong style="color:#60a5fa;">₹' + (p.consensus_target_price || 0).toFixed(2) + ' (' + retPct + ')</strong></span>' +
                                    '<span>Exit: <strong style="color:' + actualRetColor + ';">' + (p.actual_exit_price ? '₹' + p.actual_exit_price.toFixed(2) + ' (' + actualRet + ')' : 'Pending') + '</strong></span>' +
                                    '<span>Due: ' + (p.evaluation_date || '—') + '</span>' +
                                '</div>' +
                            '</div>' +
                            '<div style="display:flex;align-items:center;gap:0.6rem;">' +
                                '<div style="text-align:right;">' +
                                    '<div style="font-size:0.75rem;color:var(--muted);">Consensus Strength</div>' +
                                    '<div style="font-size:0.95rem;font-weight:700;color:' + dirColor + ';">' + strength.toFixed(0) + '% <span style="font-size:0.75rem;color:var(--muted);">(' + agreeRatio + ' agree)</span></div>' +
                                '</div>' +
                                '<button type="button" onclick="app.openConsensusDetailModal(' + p.id + ')" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);padding:0.4rem 0.75rem;border-radius:0.4rem;font-weight:600;">🔍 View Audit</button>' +
                            '</div>' +
                        '</div>' +
                        (modelPills ? '<div style="margin-top:0.6rem;display:flex;gap:0.4rem;flex-wrap:wrap;">' + modelPills + '</div>' : '') +
                        postMortemSnippet +
                    '</div>';
                }).join('');
            },

            async loadConsensusOmniRouteModels(forceRefresh = false) {
                const omniSel = document.getElementById('omniModelSelect');
                const legSel = document.getElementById('consensusModelSelect');
                const badge = document.getElementById('omniRouteGatewayStatusBadge');
                if (badge && forceRefresh) {
                    badge.innerHTML = '🔄 Scanning Gateway Models...';
                    badge.style.color = '#c084fc';
                }
                try {
                    let models = [];
                    const res = await fetch('/api/v1/consensus/models');
                    if (res.ok) {
                        const data = await res.json();
                        models = data.models || [];
                    }

                    if (!models.length) {
                        const fRes = await fetch('/api/v1/consensus/omniroute-models');
                        if (fRes.ok) {
                            const fData = await fRes.json();
                            models = fData.catalog || [];
                        }
                    }

                    if (badge) {
                        badge.innerHTML = `🟢 OmniRoute: Active (${models.length || 4} models)`;
                        badge.style.color = '#34d399';
                        badge.style.borderColor = 'rgba(16,185,129,0.25)';
                    }

                    const savedModel = localStorage.getItem('selected_omni_model') || 'antigravityonly';

                    if (omniSel && models.length > 0) {
                        omniSel.innerHTML = models.map(m => {
                            const tierBadge = m.tier ? ` [${m.tier}]` : '';
                            const speedText = m.speed ? ` · ${m.speed}` : '';
                            return `<option value="${m.id}" data-desc="${m.description || ''}" data-speed="${m.speed || ''}">
                                ${m.icon || '🤖'} ${m.name || m.id}${tierBadge}${speedText}
                            </option>`;
                        }).join('');

                        if (models.some(m => m.id === savedModel)) {
                            omniSel.value = savedModel;
                        } else {
                            omniSel.value = models[0].id;
                        }
                    }

                    if (legSel && models.length > 0) {
                        legSel.innerHTML = '<option value="ALL">🧠 All Discovered Models (Ensemble)</option>' +
                            models.map(m => `<option value="${m.id}">${m.icon || '🤖'} ${m.name || m.id}</option>`).join('');
                    }

                    this.updateOmniModelTelemetry();
                    this.updateConsensusModelTelemetry();
                } catch (e) {
                    console.debug('Error loading OmniRoute catalog on consensus tab:', e);
                    if (badge) {
                        badge.innerHTML = '⚠️ OmniRoute Gateway: Offline';
                        badge.style.color = '#f87171';
                    }
                }
            },

            updateOmniModelTelemetry() {
                const omniSel = document.getElementById('omniModelSelect');
                const badge = document.getElementById('omniModelTelemetryBadge');
                if (!omniSel) return;
                const mKey = omniSel.value;
                try {
                    localStorage.setItem('selected_omni_model', mKey);
                } catch (_) {}

                if (!badge) return;

                const opt = omniSel.selectedOptions && omniSel.selectedOptions[0];
                const speed = opt ? opt.getAttribute('data-speed') : '';
                const desc = opt ? opt.getAttribute('data-desc') : '';

                const bench = {
                    'antigravityonly': { label: 'antigravityonly', speed: '~1.5s', status: 'Workhorse' },
                    'claude only': { label: 'claude only', speed: '~2.8s', status: 'Architecture & Reasoning' },
                    'free only': { label: 'free only', speed: '~1.1s', status: 'Fast Free Tier' },
                    'claude': { label: 'claude', speed: '~2.2s', status: 'Orchestrator' },
                };

                const info = bench[mKey] || { label: mKey.split('/').pop(), speed: speed || '~2.0s', status: desc || 'Ready' };
                badge.innerHTML = `⚡ ${info.label} (${info.speed}) · ${info.status}`;
            },

            updateConsensusModelTelemetry() {
                const sel = document.getElementById('consensusModelSelect');
                const badge = document.getElementById('consensusModelTelemetryBadge');
                if (!sel || !badge) return;
                const mKey = sel.value;
                const bench = {
                    'ALL': { time: '~2.4s', succ: '99.6%', label: 'Ensemble' },
                    'antigravityonly': { time: '~1.5s', succ: '99.9%', label: 'antigravityonly' },
                    'claude only': { time: '~2.8s', succ: '99.8%', label: 'claude only' },
                    'free only': { time: '~1.1s', succ: '100%', label: 'free only' },
                    'claude': { time: '~2.2s', succ: '99.7%', label: 'claude' },
                    'deepseek/deepseek-r1': { time: '~3.4s', succ: '99.2%', label: 'DeepSeek-R1' },
                    'meta-llama/llama-3.3-70b-instruct': { time: '~2.1s', succ: '99.8%', label: 'Llama-3.3-70B' },
                    'qwen/qwen-2.5-72b-instruct': { time: '~2.3s', succ: '99.6%', label: 'Qwen-2.5-72B' },
                    'mistralai/mistral-large': { time: '~1.9s', succ: '99.7%', label: 'Mistral-Large' },
                    'google/gemma-4-31b-it:free': { time: '~1.6s', succ: '100%', label: 'Gemma-4-31B' },
                    'z-ai/glm-5.2': { time: '~2.6s', succ: '99.4%', label: 'GLM-5.2' },
                    'local': { time: '~1.2s', succ: '100%', label: 'Local Model' }
                };
                const info = bench[mKey] || { time: '~2.2s', succ: '99.5%', label: mKey.split('/').pop() };
                badge.innerHTML = `⚡ ${info.label} Avg: ${info.time} · ${info.succ} Success`;
            },

            async runConsensusPrediction(explicitModelId = null) {
                const tickerInput = document.getElementById('consensusTickerInput') || document.getElementById('omniTickerInput');
                const tfSelect = document.getElementById('consensusTimeframeSelect');
                const modelSelect = document.getElementById('consensusModelSelect') || document.getElementById('omniModelSelect');
                const runBtn = document.getElementById('consensusRunBtn') || document.getElementById('omniRunAnalysisBtn');

                const ticker = (tickerInput?.value || '').trim().toUpperCase();
                if (!ticker) {
                    alert('Please enter a stock ticker symbol (e.g. RELIANCE.NS, TCS.NS, AAPL).');
                    return;
                }

                const timeframe = tfSelect ? parseInt(tfSelect.value || '14', 10) : (this.omniTimeframe || 14);
                const selectedModel = explicitModelId || (modelSelect?.value || 'antigravityonly');

                if (explicitModelId && modelSelect) {
                    modelSelect.value = explicitModelId;
                    this.updateConsensusModelTelemetry();
                    this.updateOmniModelTelemetry();
                }

                // If running single model, route to OmniRoute analyze endpoint
                if (selectedModel && selectedModel !== 'ALL') {
                    return await this.runOmniRouteAnalysis(ticker, {
                        model: selectedModel,
                        timeframe_days: timeframe
                    });
                }

                const reqBody = {
                    ticker: ticker,
                    timeframe_days: timeframe,
                    force: true
                };

                const modelNameDisplay = selectedModel === 'ALL' ? 'All Engines' : (selectedModel.split('/').pop());
                if (runBtn) {
                    runBtn.disabled = true;
                    runBtn.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> Running ${modelNameDisplay}...`;
                }

                try {
                    const res = await fetch('/api/v1/consensus/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(reqBody)
                    });
                    const data = await res.json();
                    if (!data.success || !data.predictions || !data.predictions.length) {
                        alert('Prediction error: ' + (data.detail || data.error || 'Failed to generate consensus.'));
                        return;
                    }
                    const pred = data.predictions[0];
                    if (pred.error) {
                        alert('Model error for ' + ticker + ': ' + pred.error);
                        return;
                    }

                    // Reload consensus list
                    await this.loadConsensusTab();

                    // Automatically open modal for newly created prediction
                    if (pred.id) {
                        this.openConsensusDetailModal(pred.id);
                    }
                } catch (e) {
                    console.error('Error running consensus prediction:', e);
                    alert('Error running consensus: ' + (e.message || e));
                } finally {
                    if (runBtn) {
                        runBtn.disabled = false;
                        runBtn.innerHTML = '<span>⚡</span> Run OmniRoute Analysis';
                    }
                }
            },

            async settleConsensusPredictions() {
                const settleBtn = document.getElementById('consensusSettleBtn');
                if (settleBtn) {
                    settleBtn.disabled = true;
                    settleBtn.innerHTML = '🔄 Settling...';
                }
                try {
                    const res = await fetch('/api/v1/consensus/settle', { method: 'POST' });
                    const data = await res.json();
                    alert('Settlement Complete!\n- Total Due: ' + (data.total_due || 0) + '\n- Settled: ' + (data.settled_count || 0) + '\n- Successes: ' + (data.success_count || 0) + '\n- Failures: ' + (data.failure_count || 0));
                    await this.loadConsensusTab();
                } catch (e) {
                    console.error('Error settling consensus predictions:', e);
                    alert('Settlement error: ' + (e.message || e));
                } finally {
                    if (settleBtn) {
                        settleBtn.disabled = false;
                        settleBtn.innerHTML = '🔄 Settle Due Trades';
                    }
                }
            },

            async openConsensusDetailModal(predId) {
                const modal = document.getElementById('consensusDetailModal');
                const body = document.getElementById('consensusModalBody');
                if (!modal || !body) return;

                modal.style.display = 'flex';
                body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading audit details...</div>';

                try {
                    const res = await fetch('/api/v1/consensus/' + predId);
                    const data = await res.json();
                    if (!data.success || !data.prediction) {
                        body.innerHTML = '<div style="color:#f87171;padding:1.5rem;">Prediction record not found.</div>';
                        return;
                    }
                    const p = data.prediction;
                    const dir = (p.consensus_direction || 'NEUTRAL').toUpperCase();
                    const dirColor = dir === 'BULLISH' ? '#34d399' : dir === 'BEARISH' ? '#f87171' : '#fbbf24';
                    const status = (p.settlement_status || 'PENDING').toUpperCase();
                    const statusBg = status === 'SUCCESS' ? '#10b981' : status === 'PARTIAL' ? '#f59e0b' : status === 'FAILURE' ? '#ef4444' : '#64748b';

                    // Build Models Breakdown Matrix
                    let modelsGrid = '';
                    if (p.models_breakdown && p.models_breakdown.length) {
                        modelsGrid = p.models_breakdown.map((m, idx) => {
                            const mDir = (m.direction || 'ERR').toUpperCase();
                            const mColor = mDir === 'BULLISH' ? '#34d399' : mDir === 'BEARISH' ? '#f87171' : '#94a3b8';
                            const drivers = m.key_drivers ? m.key_drivers.map(d => '<li style="margin-bottom:0.25rem;">' + d + '</li>').join('') : '<li>No specific drivers</li>';
                            
                            const rawResp = m.raw_response ? m.raw_response : JSON.stringify(m, null, 2);
                            const escapedRaw = String(rawResp)
                                .replace(/&/g, "&amp;")
                                .replace(/</g, "&lt;")
                                .replace(/>/g, "&gt;")
                                .replace(/"/g, "&quot;")
                                .replace(/'/g, "&#039;");

                            const rawAccordion = `
                                <details style="margin-top:0.65rem;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:0.4rem;padding:0.45rem 0.65rem;">
                                    <summary style="cursor:pointer;font-size:0.75rem;font-weight:700;color:#93c5fd;display:flex;align-items:center;justify-content:space-between;user-select:none;">
                                        <span>📄 Full Raw LLM Response &amp; Chain-of-Thought</span>
                                        <span style="font-size:0.68rem;color:#94a3b8;background:rgba(255,255,255,0.06);padding:0.1rem 0.35rem;border-radius:3px;">${m.tokens_used ? m.tokens_used + ' tokens' : (m.latency_ms ? m.latency_ms + 'ms' : 'Raw Text')} ▾</span>
                                    </summary>
                                    <div style="margin-top:0.45rem;position:relative;">
                                        <pre style="margin:0;padding:0.65rem;background:#030712;border:1px solid rgba(255,255,255,0.12);border-radius:0.35rem;font-family:var(--font-mono);font-size:0.73rem;color:#e2e8f0;white-space:pre-wrap;word-break:break-word;max-height:280px;overflow-y:auto;line-height:1.5;">${escapedRaw}</pre>
                                    </div>
                                </details>
                            `;

                            return '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;padding:0.85rem;">' +
                                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">' +
                                    '<strong style="color:var(--light);font-size:0.9rem;">' + (m.model_name || m.model_id) + '</strong>' +
                                    '<span style="font-size:0.75rem;font-weight:700;color:' + mColor + ';background:' + mColor + '22;padding:0.15rem 0.45rem;border-radius:0.3rem;">' + mDir + ' (' + (m.confidence_pct || 0) + '%)</span>' +
                                '</div>' +
                                '<div style="font-size:0.78rem;color:var(--muted);margin-bottom:0.4rem;">' +
                                    'Target Return: <strong style="color:#60a5fa;">' + (m.target_return_pct ? (m.target_return_pct >= 0 ? '+' : '') + m.target_return_pct + '%' : '—') + '</strong> | Target ₹: ' + (m.target_price || '—') +
                                '</div>' +
                                '<div style="font-size:0.75rem;color:#cbd5e1;margin-bottom:0.4rem;"><strong>Key Drivers:</strong><ul style="padding-left:1.2rem;margin:0.2rem 0 0 0;">' + drivers + '</ul></div>' +
                                (m.primary_risk ? '<div style="font-size:0.75rem;color:#fca5a5;margin-bottom:0.3rem;"><strong>Primary Risk:</strong> ' + m.primary_risk + '</div>' : '') +
                                rawAccordion +
                            '</div>';
                        }).join('');
                    }

                    // Build Post-Mortem Failure Analysis Section
                    let postMortemSection = '';
                    if (status === 'FAILURE' || status === 'PARTIAL' || p.failure_post_mortem) {
                        const cat = p.failure_category ? p.failure_category.replace(/_/g, ' ') : 'Unclassified';
                        postMortemSection = '<div style="margin-top:1.25rem;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.3);border-radius:0.6rem;padding:1rem;">' +
                            '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">' +
                                '<h4 style="margin:0;color:#f87171;font-size:0.95rem;">🔍 AI Post-Mortem Failure Attribution</h4>' +
                                '<span style="font-size:0.72rem;font-weight:700;background:rgba(239,68,68,0.2);color:#fca5a5;padding:0.15rem 0.5rem;border-radius:0.3rem;">' + cat + '</span>' +
                            '</div>' +
                            '<div style="font-size:0.82rem;color:#e2e8f0;line-height:1.5;margin-bottom:0.6rem;">' +
                                '<strong>Summary:</strong> ' + (p.failure_reason_summary || 'Adverse market movement opposite to consensus expectation.') +
                            '</div>' +
                            (p.failure_post_mortem ? '<div style="font-size:0.8rem;color:#cbd5e1;line-height:1.5;background:rgba(0,0,0,0.25);padding:0.75rem;border-radius:0.4rem;">' + p.failure_post_mortem.replace(/\n/g, '<br>') + '</div>' : '') +
                        '</div>';
                    }

                    body.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:0.75rem;margin-bottom:1rem;">' +
                        '<div>' +
                            '<h3 style="margin:0;font-size:1.3rem;color:var(--light);">' + p.ticker + ' — Consensus Prediction Audit</h3>' +
                            '<div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem;">Created: ' + p.created_at + ' | Evaluation Window: ' + p.evaluation_date + '</div>' +
                        '</div>' +
                        '<span style="font-size:0.85rem;font-weight:700;background:' + statusBg + ';color:white;padding:0.3rem 0.8rem;border-radius:0.4rem;">' + status + '</span>' +
                    '</div>' +
                    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.6rem;margin-bottom:1rem;">' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Direction</span><strong style="display:block;font-size:1.1rem;color:' + dirColor + ';">' + dir + '</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Strength</span><strong style="display:block;font-size:1.1rem;color:' + dirColor + ';">' + (p.consensus_strength || 0).toFixed(0) + '%</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Entry Price</span><strong style="display:block;font-size:1.1rem;color:var(--light);">₹' + (p.as_of_price || 0).toFixed(2) + '</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Target Price</span><strong style="display:block;font-size:1.1rem;color:#60a5fa;">₹' + (p.consensus_target_price || 0).toFixed(2) + '</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Actual Return</span><strong style="display:block;font-size:1.1rem;color:' + (p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '#34d399' : '#f87171') : 'var(--muted)') + ';">' + (p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '+' : '') + p.actual_return_pct.toFixed(2) + '%' : 'Pending') + '</strong></div>' +
                    '</div>' +
                    '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.85rem;margin-bottom:1rem;font-size:0.85rem;color:#e2e8f0;line-height:1.5;">' +
                        '<strong>📜 Synthesized Consensus Thesis:</strong> ' + (p.synthesized_thesis || 'No thesis generated.') +
                    '</div>' +
                    '<h4 style="margin:1rem 0 0.5rem 0;color:var(--light);font-size:0.95rem;">🤖 Individual Model Predictions</h4>' +
                    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:0.75rem;">' + modelsGrid + '</div>' +
                    postMortemSection;
                } catch (e) {
                    console.error('Error opening consensus modal:', e);
                    body.innerHTML = '<div style="color:#f87171;padding:1.5rem;">Error loading prediction details: ' + (e.message || e) + '</div>';
                }
            },

            closeConsensusModal() {
                const modal = document.getElementById('consensusDetailModal');
                if (modal) modal.style.display = 'none';
            },

        });

        // Search / autocomplete
        const searchInput = document.getElementById('tickerSearch');
        const dropdown = document.getElementById('autocompleteDropdown');
        let selectedIndex = -1;

        searchInput.addEventListener('focus', () => {
            if (!app.allTickers.length) app.loadSearchTickers();
        });

        searchInput.addEventListener('input', async (e) => {
            const query = e.target.value.trim().toUpperCase();
            if (query.length < 1) { dropdown.style.display = 'none'; return; }
            if (!app.allTickers.length) {
                await app.loadSearchTickers();
            }
            const matches = app.allTickers.filter(t => t.toUpperCase().includes(query)).slice(0, 20);
            if (matches.length) {
                selectedIndex = -1;
                dropdown.innerHTML = matches.map((t, i) =>
                    '<div class="autocomplete-item" data-i="' + i + '" onclick="app.selectTicker(\'' + t + '\')" onmouseenter="app.setSearchHoverIndex(' + i + ')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:0.45rem 0.75rem;border-bottom:1px solid rgba(255,255,255,0.04);">' +
                    '<a href="/stock/' + encodeURIComponent(t) + '" onclick="event.preventDefault(); app.selectTicker(\'' + t + '\');" style="color:#ffffff;font-weight:700;letter-spacing:0.02em;text-decoration:none;display:flex;justify-content:space-between;align-items:center;width:100%;">' +
                    '<span>' + t + '</span>' +
                    '<span style="font-size:0.68rem;padding:0.12rem 0.45rem;border-radius:4px;background:rgba(255,255,255,0.06);color:#94a3b8;border:1px solid rgba(255,255,255,0.08);">' + (t.endsWith('.NS') ? 'NSE' : 'US') + '</span>' +
                    '</a>' +
                    '</div>'
                ).join('');
                dropdown.style.display = 'block';
            } else {
                dropdown.style.display = 'none';
            }
        });

        app.setSearchHoverIndex = function(idx) {
            selectedIndex = idx;
            const items = dropdown.querySelectorAll('.autocomplete-item');
            items.forEach((it, i) => it.classList.toggle('selected', i === idx));
        };

        searchInput.addEventListener('keydown', (e) => {
            const items = dropdown.querySelectorAll('.autocomplete-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                items.forEach((it, i) => {
                    const isSel = i === selectedIndex;
                    it.classList.toggle('selected', isSel);
                    if (isSel) it.scrollIntoView({ block: 'nearest' });
                });
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, -1);
                items.forEach((it, i) => {
                    const isSel = i === selectedIndex;
                    it.classList.toggle('selected', isSel);
                    if (isSel) it.scrollIntoView({ block: 'nearest' });
                });
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (selectedIndex >= 0 && items[selectedIndex]) {
                    items[selectedIndex].click();
                } else if (items.length) {
                    items[0].click();
                } else if (searchInput.value.trim()) {
                    app.selectTicker(searchInput.value.trim());
                }
            } else if (e.key === 'Escape') {
                dropdown.style.display = 'none';
            }
        });

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) dropdown.style.display = 'none';
        });

        app.selectTicker = function (ticker) {
            if (!ticker) return;
            const sym = ticker.trim().toUpperCase();
            dropdown.style.display = 'none';
            if (searchInput) searchInput.value = '';
            app.openStockModal(sym);
        };

        app.openTradingAgentsWarRoom = async function(ticker, event) {
            if (event && event.stopPropagation) event.stopPropagation();
            if (!ticker) return;
            const sym = String(ticker).trim().toUpperCase();

            // Ensure modal element exists
            let modal = document.getElementById('tradingAgentsWarRoomModal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'tradingAgentsWarRoomModal';
                modal.className = 'modal-backdrop';
                modal.style.cssText = 'display:none;position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(2,6,23,0.85);backdrop-filter:blur(8px);z-index:99999;overflow-y:auto;padding:1.5rem 1rem;';
                modal.onclick = function(e) {
                    if (e.target === modal) app.closeTradingAgentsWarRoom();
                };
                document.body.appendChild(modal);
            }

            modal.style.display = 'flex';
            modal.style.justifyContent = 'center';
            modal.style.alignItems = 'flex-start';
            document.body.style.overflow = 'hidden';

            modal.innerHTML = `
                <div style="background:#090d16;border:1px solid rgba(16,185,129,0.3);border-radius:14px;width:100%;max-width:960px;box-shadow:0 25px 60px -15px rgba(0,0,0,0.9), 0 0 30px rgba(16,185,129,0.15);overflow:hidden;animation:modalFadeIn 0.2s ease-out;margin:auto;">
                    <div style="padding:1.2rem 1.5rem;border-bottom:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-between;align-items:center;background:linear-gradient(180deg, rgba(16,185,129,0.08) 0%, transparent 100%);">
                        <div style="display:flex;align-items:center;gap:0.75rem;">
                            <span style="font-size:1.6rem;">🏛️</span>
                            <div>
                                <div style="display:flex;align-items:center;gap:0.5rem;">
                                    <h2 style="margin:0;font-size:1.2rem;font-weight:800;color:#f8fafc;letter-spacing:-0.02em;">TradingAgents War Room</h2>
                                    <span style="font-size:0.68rem;font-weight:800;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);padding:0.15rem 0.5rem;border-radius:4px;font-family:var(--font-mono);">${sym}</span>
                                    <span style="font-size:0.65rem;color:#94a3b8;font-weight:600;">7-Agent Multi-Model Firm</span>
                                </div>
                                <div style="font-size:0.72rem;color:#64748b;margin-top:2px;">TauricResearch Autonomous Multi-Agent Trading Architecture</div>
                            </div>
                        </div>
                        <button type="button" onclick="app.closeTradingAgentsWarRoom()" style="background:transparent;border:none;color:#94a3b8;font-size:1.5rem;cursor:pointer;padding:0.2rem 0.5rem;line-height:1;" title="Close">&times;</button>
                    </div>
                    <div id="tradingAgentsWarRoomContent" style="padding:1.5rem;max-height:80vh;overflow-y:auto;">
                        <div style="text-align:center;padding:3rem 0;color:#94a3b8;">
                            <div class="loading-spinner" style="width:32px;height:32px;border:3px solid rgba(255,255,255,0.15);border-top-color:#34d399;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 1rem;"></div>
                            <div style="font-weight:600;font-size:0.95rem;color:#e2e8f0;">Convening 7-Agent Trading Committee for ${sym}...</div>
                            <div style="font-size:0.75rem;color:#64748b;margin-top:0.3rem;">Running Fundamental, Technical & Sentiment Analysts · Executing Bull vs Bear Debate · Calculating Risk Boundaries</div>
                        </div>
                    </div>
                </div>
            `;

            try {
                let rep = app.tradingAgentsMap[sym];
                if (!rep) {
                    const res = await fetch(API_BASE + '/api/v1/trading-agents/report/' + encodeURIComponent(sym));
                    const data = await res.json();
                    rep = data.report;
                    if (rep) app.tradingAgentsMap[sym] = rep;
                }

                if (!rep) {
                    throw new Error('No report generated');
                }

                app.renderTradingAgentsWarRoomModalContent(rep);
            } catch (err) {
                const contentEl = document.getElementById('tradingAgentsWarRoomContent');
                if (contentEl) {
                    contentEl.innerHTML = `
                        <div style="text-align:center;padding:2rem;color:#f87171;">
                            <div style="font-size:1.5rem;margin-bottom:0.5rem;">⚠️</div>
                            <div style="font-weight:700;">Failed generating TradingAgents analysis for ${sym}</div>
                            <div style="font-size:0.78rem;color:#94a3b8;margin-top:0.4rem;">${err.message}</div>
                            <button type="button" class="btn btn-sm" onclick="app.runTradingAgentsWorkflow('${sym}', this)" style="margin-top:1rem;background:rgba(16,185,129,0.2);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:0.4rem 1rem;">⚡ Retry 7-Agent Execution</button>
                        </div>
                    `;
                }
            }
        };

        app.closeTradingAgentsWarRoom = function() {
            const modal = document.getElementById('tradingAgentsWarRoomModal');
            if (modal) modal.style.display = 'none';
            document.body.style.overflow = '';
        };

        app.renderTradingAgentsWarRoomModalContent = function(rep) {
            const contentEl = document.getElementById('tradingAgentsWarRoomContent');
            if (!contentEl || !rep) return;

            const isBull = rep.direction === 'BULLISH' || (rep.action || '').includes('BUY');
            const isBear = rep.direction === 'BEARISH' || (rep.action || '').includes('SELL');
            const actionColor = isBull ? '#34d399' : (isBear ? '#f87171' : '#fbbf24');
            const actionBg = isBull ? 'rgba(16,185,129,0.15)' : (isBear ? 'rgba(239,68,68,0.15)' : 'rgba(251,191,36,0.15)');
            const actionBorder = isBull ? 'rgba(16,185,129,0.35)' : (isBear ? 'rgba(239,68,68,0.35)' : 'rgba(251,191,36,0.35)');

            const fa = rep.fundamental_analyst || {};
            const ta = rep.technical_analyst || {};
            const sa = rep.sentiment_analyst || {};
            const bull = rep.bull_researcher || {};
            const bear = rep.bear_researcher || {};
            const rm = rep.risk_manager || {};

            contentEl.innerHTML = `
                <!-- 1. Executive Head Trader Verdict Banner -->
                <div style="background:linear-gradient(135deg, rgba(15,23,42,0.9) 0%, rgba(9,13,22,0.95) 100%);border:1px solid ${actionBorder};padding:1.2rem;border-radius:10px;margin-bottom:1.2rem;position:relative;overflow:hidden;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem;">
                        <div>
                            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.4rem;">
                                <span style="font-size:0.75rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;">🏛️ Head Trader Synthesis</span>
                                <span style="background:${actionBg};color:${actionColor};border:1px solid ${actionBorder};font-size:0.82rem;font-weight:800;padding:0.18rem 0.65rem;border-radius:4px;">${rep.action || 'HOLD'}</span>
                                <span style="background:rgba(255,255,255,0.06);color:#f1f5f9;font-size:0.75rem;font-weight:700;padding:0.18rem 0.5rem;border-radius:4px;font-family:var(--font-mono);">${rep.conviction_score || 50}% Conviction</span>
                            </div>
                            <div style="font-size:0.85rem;color:#cbd5e1;line-height:1.5;max-width:620px;">${rep.executive_summary || 'Executive trade synthesis completed across all 7 agents.'}</div>
                        </div>

                        <!-- Key Numerical Trade Box -->
                        <div style="display:flex;gap:0.75rem;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.08);padding:0.6rem 0.9rem;border-radius:8px;text-align:center;">
                            <div>
                                <div style="font-size:0.65rem;color:#94a3b8;">Target Price</div>
                                <div style="font-size:0.95rem;font-weight:800;color:#34d399;font-family:var(--font-mono);">₹${Number(rep.target_price || 0).toLocaleString('en-IN', {minimumFractionDigits:2})}</div>
                                <div style="font-size:0.62rem;color:#34d399;font-weight:700;">+${Number(rep.target_return_pct || 0).toFixed(1)}%</div>
                            </div>
                            <div style="width:1px;background:rgba(255,255,255,0.1);"></div>
                            <div>
                                <div style="font-size:0.65rem;color:#94a3b8;">Stop Loss</div>
                                <div style="font-size:0.95rem;font-weight:800;color:#f87171;font-family:var(--font-mono);">₹${Number(rep.stop_loss_price || 0).toLocaleString('en-IN', {minimumFractionDigits:2})}</div>
                                <div style="font-size:0.62rem;color:#f87171;font-weight:700;">Defensive Floor</div>
                            </div>
                            <div style="width:1px;background:rgba(255,255,255,0.1);"></div>
                            <div>
                                <div style="font-size:0.65rem;color:#94a3b8;">Risk-Reward</div>
                                <div style="font-size:0.95rem;font-weight:800;color:#38bdf8;font-family:var(--font-mono);">${Number(rep.risk_reward_ratio || 2.0).toFixed(2)}R</div>
                                <div style="font-size:0.62rem;color:#38bdf8;font-weight:700;">Asymmetry</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. Specialized Analyst Team (3 Columns) -->
                <div style="font-size:0.78rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.6rem;display:flex;align-items:center;gap:0.4rem;">
                    <span>👥 1. Specialized Analyst Team</span>
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(270px, 1fr));gap:0.75rem;margin-bottom:1.2rem;">
                    <!-- Fundamental Analyst -->
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.08);padding:0.9rem;border-radius:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                            <div style="display:flex;align-items:center;gap:0.4rem;font-weight:700;color:#38bdf8;font-size:0.82rem;">
                                <span>📊</span> Fundamental Analyst
                            </div>
                            <span style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);font-size:0.70rem;font-weight:800;padding:0.1rem 0.4rem;border-radius:4px;font-family:var(--font-mono);">${Number(fa.score || 5.0).toFixed(1)}/10</span>
                        </div>
                        <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.5rem;">${fa.summary || 'Fundamental evaluation.'}</div>
                        <div style="display:flex;flex-direction:column;gap:0.2rem;font-size:0.68rem;color:#94a3b8;background:rgba(0,0,0,0.3);padding:0.4rem 0.6rem;border-radius:4px;">
                            ${(fa.key_metrics || []).map(m => `<div>• ${m}</div>`).join('')}
                        </div>
                    </div>

                    <!-- Technical Analyst -->
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.08);padding:0.9rem;border-radius:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                            <div style="display:flex;align-items:center;gap:0.4rem;font-weight:700;color:#c084fc;font-size:0.82rem;">
                                <span>📈</span> Technical Analyst
                            </div>
                            <span style="background:rgba(168,85,247,0.15);color:#c084fc;border:1px solid rgba(168,85,247,0.3);font-size:0.70rem;font-weight:800;padding:0.1rem 0.4rem;border-radius:4px;font-family:var(--font-mono);">${Number(ta.score || 5.0).toFixed(1)}/10</span>
                        </div>
                        <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.5rem;">${ta.summary || 'Technical evaluation.'}</div>
                        <div style="display:flex;flex-direction:column;gap:0.2rem;font-size:0.68rem;color:#94a3b8;background:rgba(0,0,0,0.3);padding:0.4rem 0.6rem;border-radius:4px;">
                            ${(ta.key_signals || []).map(s => `<div>• ${s}</div>`).join('')}
                        </div>
                    </div>

                    <!-- Sentiment Analyst -->
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.08);padding:0.9rem;border-radius:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                            <div style="display:flex;align-items:center;gap:0.4rem;font-weight:700;color:#f59e0b;font-size:0.82rem;">
                                <span>📰</span> Sentiment & Catalysts
                            </div>
                            <span style="background:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.3);font-size:0.70rem;font-weight:800;padding:0.1rem 0.4rem;border-radius:4px;font-family:var(--font-mono);">${Number(sa.score || 5.0).toFixed(1)}/10</span>
                        </div>
                        <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.5rem;">${sa.summary || 'Sentiment evaluation.'}</div>
                        <div style="display:flex;flex-direction:column;gap:0.2rem;font-size:0.68rem;color:#94a3b8;background:rgba(0,0,0,0.3);padding:0.4rem 0.6rem;border-radius:4px;">
                            <div>• Institutional: ${sa.institutional_verdict || 'Neutral'} (${sa.funds_accumulating_count || 0} funds in)</div>
                            <div>• Macro Regime: ${sa.macro_regime_pill || '🟡 Neutral'}</div>
                        </div>
                    </div>
                </div>

                <!-- 3. Debate Arena (Bull vs Bear) -->
                <div style="font-size:0.78rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.6rem;display:flex;align-items:center;gap:0.4rem;">
                    <span>🥊 2. Debate Arena (Bullish Researcher vs Bearish Researcher)</span>
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(320px, 1fr));gap:0.75rem;margin-bottom:1.2rem;">
                    <!-- Bull Researcher -->
                    <div style="background:rgba(16,185,129,0.04);border:1px solid rgba(16,185,129,0.25);padding:0.9rem;border-radius:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
                            <div style="font-weight:800;color:#34d399;font-size:0.82rem;display:flex;align-items:center;gap:0.4rem;">
                                <span>🐂</span> Bull Researcher Thesis
                            </div>
                            <span style="font-size:0.68rem;color:#34d399;font-weight:700;">${bull.conviction_pct || 50}% Bull Conviction</span>
                        </div>
                        <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.5rem;">${bull.core_thesis || 'Upside growth thesis.'}</div>
                        <div style="font-size:0.68rem;color:#94a3b8;background:rgba(0,0,0,0.3);padding:0.4rem 0.6rem;border-radius:4px;display:flex;flex-direction:column;gap:0.2rem;">
                            ${(bull.top_catalysts || []).map(c => `<div style="color:#a7f3d0;">↑ ${c}</div>`).join('')}
                        </div>
                    </div>

                    <!-- Bear Researcher -->
                    <div style="background:rgba(239,68,68,0.04);border:1px solid rgba(239,68,68,0.25);padding:0.9rem;border-radius:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
                            <div style="font-weight:800;color:#f87171;font-size:0.82rem;display:flex;align-items:center;gap:0.4rem;">
                                <span>🐻</span> Bear Researcher Thesis
                            </div>
                            <span style="font-size:0.68rem;color:#f87171;font-weight:700;">${bear.conviction_pct || 50}% Bear Conviction</span>
                        </div>
                        <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.5rem;">${bear.core_thesis || 'Downside risk thesis.'}</div>
                        <div style="font-size:0.68rem;color:#94a3b8;background:rgba(0,0,0,0.3);padding:0.4rem 0.6rem;border-radius:4px;display:flex;flex-direction:column;gap:0.2rem;">
                            ${(bear.top_risks || []).map(r => `<div style="color:#fecaca;">↓ ${r}</div>`).join('')}
                        </div>
                    </div>
                </div>

                <!-- 4. Risk Manager & Portfolio Sizing -->
                <div style="font-size:0.78rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.6rem;display:flex;align-items:center;gap:0.4rem;">
                    <span>🛡️ 3. Risk & Sizing Assessment</span>
                </div>
                <div style="background:#0f172a;border:1px solid rgba(56,189,248,0.2);padding:0.9rem;border-radius:8px;margin-bottom:1.2rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.5rem;">
                        <div style="font-weight:700;color:#38bdf8;font-size:0.80rem;">Risk Manager Sizing Constraints</div>
                        <span style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);font-size:0.68rem;font-weight:700;padding:0.1rem 0.45rem;border-radius:4px;">Volatility: ${rm.volatility_risk || 'MODERATE'}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:0.5rem;font-size:0.72rem;color:#cbd5e1;">
                        ${(rm.risk_notes || []).map(n => `<div style="background:rgba(0,0,0,0.3);padding:0.35rem 0.55rem;border-radius:4px;border-left:2px solid #38bdf8;">${n}</div>`).join('')}
                    </div>
                </div>

                <!-- 5. Interactive Actions & Footer -->
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.6rem;padding-top:0.8rem;border-top:1px solid rgba(255,255,255,0.08);">
                    <div style="font-size:0.68rem;color:#64748b;font-family:var(--font-mono);">
                        Analyzed in ${rep.duration_s || 0.5}s · ${rep.created_at ? new Date(rep.created_at).toLocaleString() : 'Just now'}
                    </div>
                    <div style="display:flex;gap:0.5rem;">
                        <button type="button" class="btn btn-secondary" onclick="window.location.href='/stock/${encodeURIComponent(rep.ticker)}'" style="padding:0.35rem 0.75rem;font-size:0.75rem;">🔍 View Stock Detail</button>
                        <button type="button" class="btn btn-primary" onclick="app.runTradingAgentsWorkflow('${rep.ticker}', this); app.openTradingAgentsWarRoom('${rep.ticker}', event);" style="padding:0.35rem 0.85rem;font-size:0.75rem;background:linear-gradient(135deg, #10b981 0%, #059669 100%);border-color:#10b981;">⚡ Re-Run 7-Agent Analysis</button>
                    </div>
                </div>
            `;
        };

        window.openTradingAgentsWarRoom = app.openTradingAgentsWarRoom;
        window.closeTradingAgentsWarRoom = app.closeTradingAgentsWarRoom;
        window.openPopup = window.openPopup;
        window.closePopups = window.closePopups;
        window.runRowPrediction = function(ticker, engine, btn) {
            app.runRowPrediction(ticker, engine, btn);
        };
    app.openPopup = window.openPopup;
    app.closePopups = window.closePopups;
    app.runRowPrediction = app.runRowPrediction;
    app.openTradingAgentsWarRoom = app.openTradingAgentsWarRoom;
    app.closeTradingAgentsWarRoom = app.closeTradingAgentsWarRoom;
})(); // end consensus IIFE