// =========================================================================
// gainers — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[gainers] window.app not initialized'); return; }
    Object.assign(app, {
// =========================================================================
            // 🚀 Top Gainers, "Why It Rose" Attribution & Pattern Discovery Tab
            // =========================================================================
            gainersSubTab: 'gainers',
            gainersData: [],
            patternMatrixData: [],
            upcomingSetupsData: [],

            switchGainersSubTab(subTab) {
                this.gainersSubTab = subTab;
                ['gainers', 'patterns', 'setups'].forEach(t => {
                    const view = document.getElementById('gainersSubView_' + t);
                    const btn = document.getElementById('gainersSubTabBtn_' + t);
                    if (view) view.style.display = (t === subTab) ? 'block' : 'none';
                    if (btn) btn.classList.toggle('active', t === subTab);
                });

                if (subTab === 'patterns' && !this.patternMatrixData.length) {
                    this.loadPatternMatrix();
                } else if (subTab === 'setups' && !this.upcomingSetupsData.length) {
                    this.loadUpcomingSetups();
                }
            },

            async loadGainersTab() {
                await this.loadDailyTopGainers();
            },

            async refreshGainersTab() {
                if (this.gainersSubTab === 'patterns') {
                    await this.loadPatternMatrix();
                } else if (this.gainersSubTab === 'setups') {
                    await this.loadUpcomingSetups();
                } else {
                    await this.loadDailyTopGainers();
                }
            },

            onGainersMarketChange(val) {
                this.loadDailyTopGainers(val);
            },

            async loadDailyTopGainers(market) {
                const tbody = document.getElementById('topGainersTableBody');
                if (!tbody) return;
                const mktSelect = document.getElementById('gainersMarketSelect');
                const wl = market || (mktSelect ? mktSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP'));
                tbody.innerHTML = '<tr><td colspan="10" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Analyzing daily top gainers & drivers for ' + wl + '...</td></tr>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/daily?universe=' + encodeURIComponent(wl) + '&top_n=10');
                    const data = await res.json();
                    this.gainersData = data.gainers || [];
                    this.renderGainersLeaderboard();
                } catch (e) {
                    console.error('Error loading top gainers:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="10" style="padding:1rem;text-align:center;color:var(--red);">Failed loading daily top gainers.</td></tr>';
                }
            },

            renderGainersLeaderboard() {
                const tbody = document.getElementById('topGainersTableBody');
                if (!tbody) return;
                const items = this.gainersData || [];
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="10" style="padding:1.5rem;text-align:center;color:var(--muted);">No top gainers found for selected universe.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map((g, idx) => {
                    const rank = idx + 1;
                    const rankBadgeBg = rank === 1 ? 'gold' : (rank === 2 ? 'silver' : (rank === 3 ? '#cd7f32' : 'rgba(255,255,255,0.1)'));
                    const rankColor = rank <= 3 ? '#000' : 'var(--light)';

                    const is52w = g.is_52w_high === 1;
                    const status52w = is52w ? '<span style="background:rgba(52,211,153,0.2);color:#34d399;padding:0.15rem 0.45rem;border-radius:0.3rem;font-weight:700;font-size:0.7rem;">🛡️ 52W HIGH</span>' : '<span style="color:var(--muted);font-size:0.72rem;">' + (g.dist_from_52w_high_pct ? g.dist_from_52w_high_pct.toFixed(1) + '%' : '—') + '</span>';

                    const volMult = g.volume_multiple ? Number(g.volume_multiple).toFixed(1) : '—';
                    const volColor = g.volume_multiple >= 3.0 ? '#f87171' : (g.volume_multiple >= 2.0 ? '#fbbf24' : '#34d399');
                    const currSym = (g.ticker.endsWith('.NS') || g.ticker.endsWith('.BO')) ? '₹' : '$';

                    return '<tr>' +
                        '<td style="text-align:center;"><span style="background:' + rankBadgeBg + ';color:' + rankColor + ';width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:0.75rem;">' + rank + '</span></td>' +
                        '<td>' +
                            '<div><a href="/stock/' + encodeURIComponent(g.ticker) + '" target="_blank" style="font-weight:700;font-size:0.85rem;color:var(--light);text-decoration:none;">' + (g.stock_name || g.ticker) + '</a></div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);"><a href="/stock/' + encodeURIComponent(g.ticker) + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-family:var(--font-mono);">' + g.ticker + '</a><a href="/stock/' + encodeURIComponent(g.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></div>' +
                        '</td>' +
                        '<td><strong>' + currSym + (g.close_price ? Number(g.close_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td><strong class="price-positive" style="font-size:0.95rem;">+' + Number(g.return_pct).toFixed(2) + '%</strong></td>' +
                        '<td><strong style="color:' + volColor + ';">' + volMult + 'x</strong> <span style="font-size:0.7rem;color:var(--muted);">20D Avg</span></td>' +
                        '<td>' + status52w + '</td>' +
                        '<td style="max-width:320px;">' +
                            '<div style="font-weight:600;color:#38bdf8;font-size:0.78rem;margin-bottom:0.15rem;">' + (g.primary_driver || '').replace(/_/g, ' ') + '</div>' +
                            '<div style="font-size:0.73rem;color:#cbd5e1;line-height:1.35;">' + (g.driver_explanation || '') + '</div>' +
                        '</td>' +
                        '<td><span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;white-space:nowrap;">' + (g.pattern_name || 'Breakout') + '</span></td>' +
                        '<td>' + this.renderConsensusBadge(g.ticker, 'ALL') + '</td>' +
                        '<td style="text-align:center;">' +
                            '<div style="display:flex;gap:0.3rem;justify-content:center;">' +
                                '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + g.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="14D OHLCV Forecast Benchmark">📊 Benchmark</button>' +
                                '<button type="button" onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + g.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run AI Prediction">🔮 Predict</button>' +
                            '</div>' +
                        '</td>' +
                    '</tr>';
                }).join('');
            },

            async loadPatternMatrix() {
                const grid = document.getElementById('patternArchetypesGrid');
                if (!grid) return;
                grid.innerHTML = '<div class="card" style="grid-column:1/-1;padding:1.5rem;text-align:center;color:var(--muted);">Loading recurring pattern archetypes...</div>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/patterns');
                    const data = await res.json();
                    this.patternMatrixData = data.patterns || [];
                    this.renderPatternMatrix();
                } catch (e) {
                    console.error('Error loading pattern matrix:', e);
                }
            },

            renderPatternMatrix() {
                const grid = document.getElementById('patternArchetypesGrid');
                if (!grid) return;
                const items = this.patternMatrixData || [];

                grid.innerHTML = items.map(p => {
                    const winRate = p.win_rate_3d ? p.win_rate_3d.toFixed(1) + '%' : '—';
                    const avgGain = p.avg_follow_through_pct ? '+' + p.avg_follow_through_pct.toFixed(1) + '%' : '—';

                    const rulesHtml = (p.technical_rules || []).map(r => '<li style="margin-bottom:0.25rem;">' + r + '</li>').join('');

                    return '<div class="card" style="margin:0;padding:1.1rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.1);display:flex;flex-direction:column;justify-content:space-between;">' +
                        '<div>' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;flex-wrap:wrap;gap:0.3rem;">' +
                                '<h4 style="margin:0;font-size:1.05rem;color:#f8fafc;">' + p.name + '</h4>' +
                                '<span class="signal-badge" style="background:rgba(16,185,129,0.2);color:#34d399;font-size:0.75rem;">' + winRate + ' 3-Day Win Rate</span>' +
                            '</div>' +
                            '<p style="margin:0 0 0.75rem 0;font-size:0.82rem;color:#cbd5e1;line-height:1.45;">' + p.description + '</p>' +
                            '<div style="background:rgba(0,0,0,0.25);padding:0.6rem;border-radius:0.4rem;margin-bottom:0.75rem;">' +
                                '<span style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;display:block;margin-bottom:0.3rem;font-weight:700;">📐 Key Trigger Conditions:</span>' +
                                '<ul style="margin:0;padding-left:1.1rem;font-size:0.78rem;color:#93c5fd;">' + rulesHtml + '</ul>' +
                            '</div>' +
                        '</div>' +
                        '<div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.6rem;border-top:1px solid rgba(255,255,255,0.08);font-size:0.75rem;">' +
                            '<span>Avg 3D Move: <strong style="color:#34d399;font-size:0.88rem;">' + avgGain + '</strong></span>' +
                            '<span style="color:var(--muted);">Risk: <strong style="color:#fbbf24;">' + (p.risk_level || 'Medium') + '</strong></span>' +
                        '</div>' +
                    '</div>';
                }).join('');
            },

            async loadUpcomingSetups() {
                const tbody = document.getElementById('upcomingSetupsTableBody');
                if (!tbody) return;
                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                tbody.innerHTML = '<tr><td colspan="9" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Scanning watchlist for pre-breakout patterns...</td></tr>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/upcoming-setups?universe=' + encodeURIComponent(wl));
                    const data = await res.json();
                    this.upcomingSetupsData = data.setups || [];
                    this.renderUpcomingSetups();
                } catch (e) {
                    console.error('Error scanning setups:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="9" style="padding:1rem;text-align:center;color:var(--red);">Failed scanning watchlist setups.</td></tr>';
                }
            },

            renderUpcomingSetups() {
                const tbody = document.getElementById('upcomingSetupsTableBody');
                if (!tbody) return;
                const items = this.upcomingSetupsData || [];
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="9" style="padding:1.5rem;text-align:center;color:var(--muted);">No stocks currently in tight pre-breakout coils in this universe. Try selecting another universe above.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(s => {
                    const currSym = (s.ticker.endsWith('.NS') || s.ticker.endsWith('.BO')) ? '₹' : '$';
                    return '<tr>' +
                        '<td>' +
                            '<div><a href="/stock/' + encodeURIComponent(s.ticker) + '" target="_blank" style="font-weight:700;font-size:0.85rem;color:var(--light);text-decoration:none;">' + (s.stock_name || s.ticker) + '</a></div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);"><a href="/stock/' + encodeURIComponent(s.ticker) + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-family:var(--font-mono);">' + s.ticker + '</a><a href="/stock/' + encodeURIComponent(s.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></div>' +
                        '</td>' +
                        '<td><strong>' + currSym + (s.current_price ? Number(s.current_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td><span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">' + s.matching_pattern + '</span></td>' +
                        '<td><span style="background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">' + s.setup_stage + '</span></td>' +
                        '<td><strong style="color:#fbbf24;font-size:0.85rem;">' + currSym + Number(s.trigger_level).toFixed(2) + '</strong></td>' +
                        '<td><span style="color:#34d399;font-weight:700;">' + s.confidence_score + '%</span></td>' +
                        '<td style="max-width:320px;font-size:0.75rem;color:#cbd5e1;line-height:1.35;">' + s.why_it_matches + '</td>' +
                        '<td>' + this.renderConsensusBadge(s.ticker, 'ALL') + '</td>' +
                        '<td style="text-align:center;">' +
                            '<button type="button" onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + s.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run AI Prediction">🔮 Predict</button>' +
                        '</td>' +
                    '</tr>';
                }).join('');
            },

            maybeShowKronosPrompt() {
                const el = document.getElementById('kronosWidgets');
                if (!el) return;
                if (!el.innerHTML.trim()) {
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">' +
                        '<p style="margin:0 0 0.5rem 0;">Select a watchlist below, then click ▶ Run Predictions to load forecasts.</p>' +
                        '<p style="margin:0;color:var(--muted);font-size:0.8rem;">Kronos does not fetch anything by default — pick one of your managed watchlists to get started.</p>' +
                        '</div>';
                }
            },

            async loadOverview() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/overview');
                    const data = await res.json();
                    this.renderDatasetSummary(data.dataset);
                    this.renderRefreshStatus(data.refresh_status);
                } catch (e) {
                    console.error('Error loading overview:', e);
                }
            },

            renderDatasetSummary(ds) {
                const el = document.getElementById('resultsDatasetSummary');
                if (!el) return;
                if (!ds || !ds.available) {
                    el.innerHTML = '<div class="card" style="margin:0">⚠️ Event dataset not available. Run <code>earnings-engine build-dataset</code> first.</div>';
                    return;
                }
                el.innerHTML = [
                    '<div class="metric"><span>Dataset Rows</span><strong>' + ds.rows + '</strong></div>',
                    '<div class="metric"><span>Tickers</span><strong>' + ds.tickers + '</strong></div>',
                    '<div class="metric"><span>Up-Label Rate</span><strong>' + (ds.up_label_rate !== null ? (ds.up_label_rate * 100).toFixed(1) + '%' : 'N/A') + '</strong></div>',
                    '<div class="metric"><span>Date Range</span><strong>' + (ds.date_range ? ds.date_range.min + ' → ' + ds.date_range.max : 'N/A') + '</strong></div>'
                ].join('');
            },

            renderRefreshStatus(status) {
                const el = document.getElementById('lastRefreshed');
                if (!el) return;
                if (!status || Object.keys(status).length === 0) {
                    el.textContent = 'Last refreshed: Never';
                    return;
                }
                let parts = Object.entries(status).map(([k, v]) => {
                    const time = v.last_refresh ? v.last_refresh.split(' ')[1] : '?';
                    return k + ': ' + time + ' (' + v.rows + ')';
                });
                el.textContent = 'Last refreshed — ' + parts.join(' · ');
            
    
        }
});
})(); // end gainers IIFE
