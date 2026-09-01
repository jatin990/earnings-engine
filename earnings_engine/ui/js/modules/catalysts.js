// =========================================================================
// catalysts — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
            catalystsData: [],
            catalystsActiveView: 'feed',
            outcomesData: [],
            outcomesMetrics: {},

            switchCatalystsView(view) {
                this.catalystsActiveView = view;
                const feedView = document.getElementById('catalystsFeedView');
                const outcomesView = document.getElementById('catalystsOutcomesView');
                const feedBtn = document.getElementById('catViewFeedBtn');
                const outcomesBtn = document.getElementById('catViewOutcomesBtn');
                const scanBtn = document.getElementById('catScanBtn');
                const evalBtn = document.getElementById('catEvalOutcomesBtn');

                if (feedView) feedView.style.display = (view === 'feed') ? 'block' : 'none';
                if (outcomesView) outcomesView.style.display = (view === 'outcomes') ? 'block' : 'none';

                if (feedBtn) {
                    feedBtn.style.background = (view === 'feed') ? 'rgba(59, 130, 246, 0.2)' : 'transparent';
                    feedBtn.style.color = (view === 'feed') ? '#60a5fa' : '#a1a1aa';
                    feedBtn.style.borderColor = (view === 'feed') ? 'rgba(59, 130, 246, 0.35)' : 'transparent';
                    feedBtn.style.fontWeight = (view === 'feed') ? '700' : '600';
                }
                if (outcomesBtn) {
                    outcomesBtn.style.background = (view === 'outcomes') ? 'rgba(59, 130, 246, 0.2)' : 'transparent';
                    outcomesBtn.style.color = (view === 'outcomes') ? '#60a5fa' : '#a1a1aa';
                    outcomesBtn.style.borderColor = (view === 'outcomes') ? 'rgba(59, 130, 246, 0.35)' : 'transparent';
                    outcomesBtn.style.fontWeight = (view === 'outcomes') ? '700' : '600';
                }

                if (scanBtn) scanBtn.style.display = (view === 'feed') ? 'inline-flex' : 'none';
                if (evalBtn) evalBtn.style.display = (view === 'outcomes') ? 'inline-flex' : 'none';

                if (view === 'outcomes') {
                    this.loadNewsOutcomes();
                }
            },

            filterCatalystsHighImpact70() {
                const impactSelect = document.getElementById('catImpactFilter');
                const btn = document.getElementById('catViewHighImpactBtn');
                if (!this._highImpact70Only) {
                    this._highImpact70Only = true;
                    if (impactSelect) impactSelect.value = 'HIGH';
                    if (btn) {
                        btn.style.background = 'rgba(251, 191, 36, 0.2)';
                        btn.style.color = '#fbbf24';
                        btn.style.borderColor = 'rgba(251, 191, 36, 0.4)';
                        btn.style.fontWeight = '700';
                    }
                } else {
                    this._highImpact70Only = false;
                    if (impactSelect) impactSelect.value = 'ALL';
                    if (btn) {
                        btn.style.background = 'transparent';
                        btn.style.color = '#fbbf24';
                        btn.style.borderColor = 'transparent';
                        btn.style.fontWeight = '600';
                    }
                }
                this.renderCatalysts();
            },

            async loadCatalysts(watchlist, days) {
                const feedGrid = document.getElementById('catalystsFeedGrid');
                if (!feedGrid) return;
                const wlSelect = document.getElementById('catWatchlistSelect');
                const daysSelect = document.getElementById('catDaysFilter');
                const wl = watchlist || (wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL'));
                const d = (days !== undefined && days !== null) ? days : (daysSelect ? daysSelect.value : '14');
                const wlParam = (wl && wl !== 'GLOBAL') ? '?watchlist=' + encodeURIComponent(wl) + '&limit=200&days=' + encodeURIComponent(d) : '?limit=200&days=' + encodeURIComponent(d);
                const statsParam = (wl && wl !== 'GLOBAL') ? '?watchlist=' + encodeURIComponent(wl) + '&days=' + encodeURIComponent(d) : '?days=' + encodeURIComponent(d);
                feedGrid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading short-term market moving catalysts' + (wl ? ' for "' + wl + '"' : '') + '...</div>';
                
                const fetchFn = (this.apiFetch ? this.apiFetch.bind(this) : fetch);
                try {
                    const [itemsRes, statsRes] = await Promise.all([
                        fetchFn(API_BASE + '/api/v1/news/catalysts' + wlParam, {}, 'catalysts'),
                        fetchFn(API_BASE + '/api/v1/news/catalyst-stats' + statsParam, {}, 'catalysts')
                    ]);
                    const itemsData = await itemsRes.json();
                    const statsData = await statsRes.json();

                    if (itemsData && itemsData.aborted) return;

                    this.catalystsData = itemsData.catalysts || [];
                    this.renderCatalystsStats(statsData.stats || {});
                    this.renderCatalysts();
                    if (typeof this.updateHarvesterScheduleDisplay === 'function') {
                        this.updateHarvesterScheduleDisplay();
                    } else if (typeof this.renderAutomationSchedules === 'function') {
                        this.renderAutomationSchedules();
                    }
                    this.probeOmniRouteGateway(false);
                } catch (e) {
                    console.error('Error loading catalysts:', e);
                    feedGrid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:#f87171;">Failed to load catalysts feed.</div>';
                }
            },

            updateHarvesterScheduleDisplay() {
                if (typeof this.renderAutomationSchedules === 'function') {
                    this.renderAutomationSchedules();
                } else if (typeof this.loadAutomationSchedules === 'function') {
                    this.loadAutomationSchedules();
                }
            },

            async probeOmniRouteGateway(showToast = false) {
                const dot = document.getElementById('omnirouteStatusDot');
                const text = document.getElementById('omnirouteStatusText');
                const pill = document.getElementById('omnirouteGatewayStatusPill');
                if (text && showToast) {
                    text.textContent = 'Probing OmniRoute...';
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/omniroute/status');
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'online') {
                            if (dot) dot.style.background = '#34d399';
                            if (text) text.textContent = `OmniRoute: ${data.endpoint || 'localhost:20128'} (${data.models_count || '350+'} models)`;
                            if (pill) {
                                pill.style.borderColor = 'rgba(52,211,153,0.4)';
                                pill.style.background = 'rgba(52,211,153,0.12)';
                                pill.style.color = '#34d399';
                                pill.title = 'OmniRoute Gateway Connected';
                            }
                        } else if (data.status === 'auth_required') {
                            if (dot) dot.style.background = '#fbbf24';
                            if (text) text.textContent = `OmniRoute: localhost:20128 (Key Required)`;
                            if (pill) {
                                pill.style.borderColor = 'rgba(251,191,36,0.5)';
                                pill.style.background = 'rgba(251,191,36,0.15)';
                                pill.style.color = '#fbbf24';
                                pill.title = data.message || 'OmniRoute is running on http://localhost:20128/. Generate an API Key in the OmniRoute dashboard and add OMNIROUTE_API_KEY to your .env file.';
                            }
                        } else if (data.status === 'auth_invalid') {
                            if (dot) dot.style.background = '#f87171';
                            if (text) text.textContent = `OmniRoute: Invalid API Key`;
                            if (pill) {
                                pill.style.borderColor = 'rgba(248,113,113,0.5)';
                                pill.style.background = 'rgba(248,113,113,0.15)';
                                pill.style.color = '#f87171';
                                pill.title = 'Configured OMNIROUTE_API_KEY was rejected by OmniRoute.';
                            }
                        } else if (data.status === 'fallback_online') {
                            if (dot) dot.style.background = '#38bdf8';
                            if (text) text.textContent = `OmniRoute: Fallback Gateway Active`;
                            if (pill) {
                                pill.style.borderColor = 'rgba(56,189,248,0.4)';
                                pill.style.background = 'rgba(56,189,248,0.12)';
                                pill.style.color = '#38bdf8';
                            }
                        } else {
                            if (dot) dot.style.background = '#f87171';
                            if (text) text.textContent = `OmniRoute: Offline (Port 20128)`;
                            if (pill) {
                                pill.style.borderColor = 'rgba(248,113,113,0.4)';
                                pill.style.background = 'rgba(248,113,113,0.12)';
                                pill.style.color = '#f87171';
                            }
                        }
                    }
                } catch (e) {
                    if (dot) dot.style.background = '#f87171';
                    if (text) text.textContent = `OmniRoute: Offline (Port 20128)`;
                }
            },

            async loadNewsOutcomes() {
                const tableBody = document.getElementById('outcomesTableBody');
                if (tableBody) tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading historical verified news outcomes & performance metrics...</td></tr>';
                
                const fetchFn = (this.apiFetch ? this.apiFetch.bind(this) : fetch);
                try {
                    const [metricsRes, outcomesRes] = await Promise.all([
                        fetchFn(API_BASE + '/api/v1/news/trade-metrics', {}, 'catalysts'),
                        fetchFn(API_BASE + '/api/v1/news/outcomes?limit=100', {}, 'catalysts')
                    ]);
                    const metricsData = await metricsRes.json();
                    const outcomesData = await outcomesRes.json();

                    if (outcomesData && outcomesData.aborted) return;

                    this.outcomesMetrics = metricsData.metrics || {};
                    this.outcomesData = outcomesData.outcomes || [];

                    this.renderNewsTradeMetrics(this.outcomesMetrics);
                    this.renderNewsOutcomes();
                } catch (e) {
                    if (e.name === 'AbortError') return;
                    console.error('Error loading news outcomes:', e);
                    if (tableBody) tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:1.5rem;color:var(--red);">Failed loading outcomes track record. Click "🎯 Re-Verify Outcomes" to calculate.</td></tr>';
                }
            },

            renderNewsTradeMetrics(m) {
                if (!m) return;
                const winRateEl = document.getElementById('outcomeWinRate');
                const dirWinEl = document.getElementById('outcomeDirWinRates');
                const expEl = document.getElementById('outcomeExpectancy');
                const avgRetEl = document.getElementById('outcomeAvgReturn');
                const pfEl = document.getElementById('outcomeProfitFactor');
                const payoffEl = document.getElementById('outcomePayoff');
                const topGValEl = document.getElementById('outcomeTopGainerVal');
                const topGTickEl = document.getElementById('outcomeTopGainerTicker');
                const totalEl = document.getElementById('outcomeTotalCount');
                const verEl = document.getElementById('outcomeVerifiedCount');
                const actEl = document.getElementById('outcomeActiveCount');

                const h1dEl = document.getElementById('horizon1d');
                const h3dEl = document.getElementById('horizon3d');
                const h5dEl = document.getElementById('horizon5d');

                if (winRateEl) winRateEl.textContent = (m.win_rate_pct != null ? m.win_rate_pct.toFixed(1) : '0.0') + '%';
                if (dirWinEl) dirWinEl.textContent = `Bull: ${(m.bullish_win_rate_pct || 0).toFixed(1)}% | Bear: ${(m.bearish_win_rate_pct || 0).toFixed(1)}%`;
                
                if (expEl) {
                    const expVal = m.trade_expectancy_pct || 0;
                    expEl.textContent = (expVal > 0 ? '+' : '') + expVal.toFixed(2) + '%';
                    expEl.style.color = expVal >= 0 ? '#34d399' : '#f87171';
                }
                if (avgRetEl) {
                    const rVal = m.avg_return_pct || 0;
                    avgRetEl.textContent = (rVal > 0 ? '+' : '') + rVal.toFixed(2) + '%';
                    avgRetEl.style.color = rVal >= 0 ? '#34d399' : '#f87171';
                }
                if (pfEl) pfEl.textContent = (m.profit_factor != null ? m.profit_factor.toFixed(2) : '0.00');
                if (payoffEl) payoffEl.textContent = (m.payoff_ratio != null ? m.payoff_ratio.toFixed(2) : '0.0') + 'x';

                if (m.max_gainers && m.max_gainers.length) {
                    const topG = m.max_gainers[0];
                    if (topGValEl) topGValEl.textContent = '+' + Number(topG.max_gain_pct).toFixed(1) + '%';
                    if (topGTickEl) topGTickEl.textContent = `${topG.ticker}: ${topG.title}`;
                }
                if (totalEl) totalEl.textContent = m.total_evaluated || 0;
                if (verEl) verEl.textContent = m.verified_count || 0;
                if (actEl) actEl.textContent = (m.total_evaluated || 0) - (m.verified_count || 0);

                if (m.horizon_performance) {
                    const h1 = m.horizon_performance.avg_1d_pct || 0;
                    const h3 = m.horizon_performance.avg_3d_pct || 0;
                    const h5 = m.horizon_performance.avg_5d_pct || 0;
                    if (h1dEl) { h1dEl.textContent = (h1 > 0 ? '+' : '') + h1.toFixed(2) + '%'; h1dEl.style.color = h1 >= 0 ? '#60a5fa' : '#f87171'; }
                    if (h3dEl) { h3dEl.textContent = (h3 > 0 ? '+' : '') + h3.toFixed(2) + '%'; h3dEl.style.color = h3 >= 0 ? '#34d399' : '#f87171'; }
                    if (h5dEl) { h5dEl.textContent = (h5 > 0 ? '+' : '') + h5.toFixed(2) + '%'; h5dEl.style.color = h5 >= 0 ? '#38bdf8' : '#f87171'; }
                }

                // Render Category Performance Table
                const catTableBody = document.getElementById('outcomeCategoryTableBody');
                if (catTableBody && m.category_performance) {
                    if (!m.category_performance.length) {
                        catTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1rem;color:var(--muted);">No category data available.</td></tr>';
                    } else {
                        catTableBody.innerHTML = m.category_performance.map(c => {
                            const wrColor = c.win_rate_pct >= 65 ? '#34d399' : (c.win_rate_pct >= 50 ? '#60a5fa' : '#f87171');
                            const retColor = c.avg_return_pct >= 0 ? '#34d399' : '#f87171';
                            const edgeBadge = c.win_rate_pct >= 70 && c.profit_factor >= 2.0
                                ? '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-size:0.68rem;">🔥 High Edge</span>'
                                : (c.win_rate_pct >= 55 ? '<span class="signal-badge" style="background:rgba(59,130,246,0.15);color:#60a5fa;font-size:0.68rem;">⚡ Solid</span>' : '<span class="signal-badge" style="background:rgba(148,163,184,0.1);color:#94a3b8;font-size:0.68rem;">Neutral</span>');

                            return `
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                    <td style="padding: 0.4rem 0.5rem; font-weight: 600; color: #f8fafc;">${c.category}</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; color: #a1a1aa; font-family: var(--font-mono);">${c.total_events}</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; font-weight: 700; color: ${wrColor}; font-family: var(--font-mono);">${c.win_rate_pct.toFixed(1)}%</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; font-weight: 600; color: ${retColor}; font-family: var(--font-mono);">${(c.avg_return_pct > 0 ? '+' : '') + c.avg_return_pct.toFixed(2)}%</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; color: #38bdf8; font-family: var(--font-mono);">+${c.avg_max_gain_pct.toFixed(2)}%</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; font-weight: 600; color: #e2e8f0; font-family: var(--font-mono);">${c.profit_factor.toFixed(2)}</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: center;">${edgeBadge}</td>
                                </tr>
                            `;
                        }).join('');
                    }
                }
            },

            filterOutcomes() {
                this.renderNewsOutcomes();
            },

            renderNewsOutcomes() {
                const tableBody = document.getElementById('outcomesTableBody');
                const countBadge = document.getElementById('outcomesCountBadge');
                if (!tableBody) return;

                const searchQ = (document.getElementById('outcomesSearchInput')?.value || '').toLowerCase().trim();
                const catFilter = document.getElementById('outcomesCategoryFilter')?.value || 'ALL';
                const dirFilter = document.getElementById('outcomesDirectionFilter')?.value || 'ALL';
                const statusFilter = document.getElementById('outcomesStatusFilter')?.value || 'ALL';
                const sortBy = document.getElementById('outcomesSortBy')?.value || 'max_gain';

                let filtered = (this.outcomesData || []).filter(item => {
                    if (searchQ) {
                        const mTicker = (item.ticker || '').toLowerCase().includes(searchQ);
                        const mName = (item.stock_name || '').toLowerCase().includes(searchQ);
                        const mTitle = (item.title || '').toLowerCase().includes(searchQ);
                        if (!mTicker && !mName && !mTitle) return false;
                    }
                    if (catFilter !== 'ALL' && item.category !== catFilter) return false;
                    if (dirFilter !== 'ALL' && item.direction !== dirFilter) return false;
                    if (statusFilter !== 'ALL' && item.status !== statusFilter) return false;
                    return true;
                });

                if (sortBy === 'max_gain') {
                    filtered.sort((a, b) => (b.max_gain_pct || 0) - (a.max_gain_pct || 0));
                } else if (sortBy === 'net_return') {
                    filtered.sort((a, b) => (b.net_return_pct || 0) - (a.net_return_pct || 0));
                } else if (sortBy === 'impact') {
                    filtered.sort((a, b) => (b.impact_score || 0) - (a.impact_score || 0));
                } else {
                    filtered.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''));
                }

                if (countBadge) countBadge.textContent = filtered.length + ' evaluated';

                if (!filtered.length) {
                    tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--muted);">No news outcomes matching selected filters.</td></tr>';
                    return;
                }

                tableBody.innerHTML = filtered.map(o => {
                    const isBull = o.direction === 'BULLISH';
                    const isMet = Boolean(o.predicted_met);
                    const isVerified = o.status === 'VERIFIED';

                    const dirColor = isBull ? '#34d399' : '#f87171';
                    const dirIcon = isBull ? '🟢 Bull' : '🔴 Bear';

                    let outcomeBadge = '';
                    if (isVerified) {
                        if (isMet) {
                            const retStr = o.net_return_pct != null ? (o.net_return_pct > 0 ? '+' : '') + o.net_return_pct.toFixed(1) + '%' : 'MET';
                            outcomeBadge = `<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-weight:700;border:1px solid rgba(16,185,129,0.3);">✅ MET (${retStr})</span>`;
                        } else {
                            const retStr = o.net_return_pct != null ? o.net_return_pct.toFixed(1) + '%' : 'FAILED';
                            outcomeBadge = `<span class="signal-badge" style="background:rgba(239,68,68,0.15);color:#f87171;font-weight:700;border:1px solid rgba(239,68,68,0.3);">❌ MISSED (${retStr})</span>`;
                        }
                    } else {
                        outcomeBadge = `<span class="signal-badge" style="background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);">⏳ ACTIVE</span>`;
                    }

                    const fmtRet = (val) => {
                        if (val == null || isNaN(val)) return '—';
                        const sign = val > 0 ? '+' : '';
                        const col = val > 0 ? '#34d399' : (val < 0 ? '#f87171' : '#94a3b8');
                        return `<span style="color:${col};font-weight:600;font-family:var(--font-mono);">${sign}${Number(val).toFixed(2)}%</span>`;
                    };

                    const entryPx = o.entry_price ? `₹${Number(o.entry_price).toLocaleString('en-IN', {minimumFractionDigits:1, maximumFractionDigits:2})}` : '—';
                    const maxGain = o.max_gain_pct != null ? `<span style="color:#38bdf8;font-weight:700;font-family:var(--font-mono);">+${Number(o.max_gain_pct).toFixed(2)}%</span>` : '—';
                    const maxDD = o.max_drawdown_pct != null ? `<span style="color:#f87171;font-weight:600;font-family:var(--font-mono);">${Number(o.max_drawdown_pct).toFixed(2)}%</span>` : '—';

                    const pubDate = o.published_at ? o.published_at.slice(0, 10) : '—';

                    return `
                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.12s ease;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                            <td style="padding: 0.45rem 0.5rem; white-space: nowrap;">
                                <a href="/stock/${encodeURIComponent(o.ticker)}" target="_blank" style="font-weight:700;color:#60a5fa;text-decoration:none;font-family:var(--font-mono);" title="Open stock intelligence page">
                                    ${o.ticker} ↗
                                </a>
                                <div style="font-size:0.68rem;color:#71717a;">${o.stock_name || ''}</div>
                            </td>
                            <td style="padding: 0.45rem 0.5rem; white-space: nowrap; color: #a1a1aa; font-family: var(--font-mono); font-size: 0.72rem;">
                                ${pubDate}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; max-width: 320px;">
                                <div style="font-weight: 600; color: #f8fafc; font-size: 0.78rem; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${(o.title || '').replace(/"/g, '&quot;')}">
                                    ${o.title}
                                </div>
                                <div style="display: flex; gap: 0.35rem; align-items: center; margin-top: 0.15rem;">
                                    <span style="font-size: 0.65rem; color: ${dirColor}; font-weight: 700;">${dirIcon}</span>
                                    <span style="font-size: 0.65rem; background: rgba(255,255,255,0.06); color: #94a3b8; padding: 0.05rem 0.3rem; border-radius: 3px;">${o.category}</span>
                                    <span style="font-size: 0.65rem; color: #fbbf24;">⚡ ${o.impact_score}%</span>
                                </div>
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; font-family: var(--font-mono); color: #e2e8f0; font-weight: 600; white-space: nowrap;">
                                ${entryPx}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${fmtRet(o.return_1d_pct)}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${fmtRet(o.return_3d_pct)}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${fmtRet(o.return_5d_pct)}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${maxGain}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${maxDD}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: center; white-space: nowrap;">
                                ${outcomeBadge}
                            </td>
                        </tr>
                    `;
                }).join('');
            },

            async evaluateNewsOutcomesNow() {
                const btn = document.getElementById('catEvalOutcomesBtn');
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Evaluating Outcomes...';
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/news/outcomes/evaluate', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({force: true})
                    });
                    const data = await res.json();
                    await this.loadNewsOutcomes();
                } catch (e) {
                    console.error('Error evaluating news outcomes:', e);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<span>🎯</span> Re-Verify Outcomes';
                    }
                }
            },

            onCatWatchlistChange(val) {
                const daysSelect = document.getElementById('catDaysFilter');
                const d = daysSelect ? daysSelect.value : '14';
                this.loadCatalysts(val, d);
            },

            onCatDaysFilterChange(val) {
                const wlSelect = document.getElementById('catWatchlistSelect');
                const wl = wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL');
                this.loadCatalysts(wl, val);
            },

            renderCatalystsStats(stats) {
                const totalEl = document.getElementById('catStatTotal');
                const highEl = document.getElementById('catStatHigh');
                const biasEl = document.getElementById('catStatBias');
                const topCatEl = document.getElementById('catStatTopCat');

                if (totalEl) totalEl.textContent = stats.total_catalysts || this.catalystsData.length;
                if (highEl) highEl.textContent = stats.high_impact_count || this.catalystsData.filter(c => c.impact_level === 'HIGH').length;
                if (biasEl) {
                    const bull = stats.bullish_count || this.catalystsData.filter(c => c.direction === 'BULLISH').length;
                    const bear = stats.bearish_count || this.catalystsData.filter(c => c.direction === 'BEARISH').length;
                    biasEl.innerHTML = '<span style="color:#34d399;">' + bull + '</span> / <span style="color:#f87171;">' + bear + '</span>';
                }
                if (topCatEl) {
                    const topC = (stats.top_categories && stats.top_categories.length) ? stats.top_categories[0].category : 'Order Wins & Contracts';
                    topCatEl.textContent = topC;
                }
            },

            formatNewsDate(dateStr) {
                if (!dateStr) return '';
                try {
                    const cleanStr = dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T') + 'Z';
                    const d = new Date(cleanStr);
                    if (isNaN(d.getTime())) return dateStr.split(' ')[0] || dateStr;
                    const now = new Date();
                    const diffMs = now.getTime() - d.getTime();
                    const diffMins = Math.floor(diffMs / 60000);
                    const diffHours = Math.floor(diffMins / 60);
                    const diffDays = Math.floor(diffHours / 24);

                    if (diffMins >= 0 && diffMins < 60) {
                        return (diffMins <= 1 ? 'Just now' : diffMins + 'm ago');
                    } else if (diffHours > 0 && diffHours < 24) {
                        return diffHours + 'h ago';
                    } else if (diffDays === 1) {
                        return 'Yesterday';
                    } else if (diffDays > 1 && diffDays < 7) {
                        return diffDays + 'd ago';
                    } else {
                        return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
                    }
                } catch (e) {
                    return dateStr;
                }
            },

            filterCatalysts() {
                this.renderCatalysts();
            },

            renderCatalysts() {
                const feedGrid = document.getElementById('catalystsFeedGrid');
                const countBadge = document.getElementById('catFeedCountBadge');
                if (!feedGrid) return;

                const searchQ = (document.getElementById('catSearchInput')?.value || '').toLowerCase().trim();
                const daysFilter = parseInt(document.getElementById('catDaysFilter')?.value || '14', 10);
                const impactFilter = document.getElementById('catImpactFilter')?.value || 'ALL';
                const dirFilter = document.getElementById('catDirectionFilter')?.value || 'ALL';
                const catFilter = document.getElementById('catCategoryFilter')?.value || 'ALL';

                // STRICT CHRONOLOGICAL SORT: Newest news always on top
                const _toTime = (dStr) => {
                    if (!dStr) return 0;
                    const clean = dStr.includes('T') ? dStr : dStr.replace(' ', 'T') + 'Z';
                    const t = new Date(clean).getTime();
                    return isNaN(t) ? new Date(dStr).getTime() || 0 : t;
                };

                const nowMs = Date.now();
                const cutoffMs = (daysFilter > 0) ? (nowMs - (daysFilter * 24 * 60 * 60 * 1000)) : 0;

                let filtered = (this.catalystsData || []).filter(item => {
                    if (daysFilter > 0) {
                        const itemTime = _toTime(item.published_at || item.created_at);
                        if (itemTime > 0 && itemTime < cutoffMs) return false;
                    }
                    if (searchQ) {
                        const mTicker = (item.ticker || '').toLowerCase().includes(searchQ);
                        const mName = (item.stock_name || '').toLowerCase().includes(searchQ);
                        const mTitle = (item.title || '').toLowerCase().includes(searchQ);
                        if (!mTicker && !mName && !mTitle) return false;
                    }
                    if (impactFilter === 'HIGH' && item.impact_level !== 'HIGH') return false;
                    if (impactFilter === 'MEDIUM+' && item.impact_level !== 'HIGH' && item.impact_level !== 'MEDIUM') return false;
                    if (dirFilter !== 'ALL' && item.direction !== dirFilter) return false;
                    if (catFilter !== 'ALL' && item.category !== catFilter) return false;
                    return true;
                });

                filtered.sort((a, b) => {
                    const ta = _toTime(a.published_at || a.created_at);
                    const tb = _toTime(b.published_at || b.created_at);
                    if (tb !== ta) return tb - ta;
                    return (b.impact_score || 0) - (a.impact_score || 0);
                });

                if (countBadge) countBadge.textContent = filtered.length + ' headlines';

                // Synchronously update top KPI summary cards based on the filtered dataset
                const totalCount = filtered.length;
                const highCount = filtered.filter(c => c.impact_level === 'HIGH').length;
                const bullCount = filtered.filter(c => c.direction === 'BULLISH').length;
                const bearCount = filtered.filter(c => c.direction === 'BEARISH').length;

                const catCounts = {};
                filtered.forEach(c => {
                    const cat = c.category || 'Order Wins & Contracts';
                    catCounts[cat] = (catCounts[cat] || 0) + 1;
                });
                let topCat = '—';
                let maxCnt = 0;
                for (const [cat, cnt] of Object.entries(catCounts)) {
                    if (cnt > maxCnt) {
                        maxCnt = cnt;
                        topCat = cat;
                    }
                }

                const totalEl = document.getElementById('catStatTotal');
                const highEl = document.getElementById('catStatHigh');
                const biasEl = document.getElementById('catStatBias');
                const topCatEl = document.getElementById('catStatTopCat');

                if (totalEl) totalEl.textContent = totalCount;
                if (highEl) highEl.textContent = highCount;
                if (biasEl) biasEl.innerHTML = '<span style="color:#34d399;">' + bullCount + '</span> / <span style="color:#f87171;">' + bearCount + '</span>';
                if (topCatEl) topCatEl.textContent = topCat;

                this._lastFilteredCatalysts = filtered;

                if (!filtered.length) {
                    feedGrid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);">No catalysts matching selected filter criteria. Click "⚡ Scan Feeds" to discover live headlines.</div>';
                    return;
                }

                feedGrid.innerHTML = filtered.map(c => {
                    const isHigh = c.impact_level === 'HIGH';
                    const isBull = c.direction === 'BULLISH';
                    const isBear = c.direction === 'BEARISH';

                    const impactBadgeBg = isHigh ? 'rgba(239,68,68,0.2)' : 'rgba(251,191,36,0.2)';
                    const impactBadgeColor = isHigh ? '#f87171' : '#fbbf24';
                    const impactLabel = isHigh ? '🔥 HIGH IMPACT (' + c.impact_score + '%)' : '⚡ MEDIUM (' + c.impact_score + '%)';

                    const dirBadgeBg = isBull ? 'rgba(16,185,129,0.2)' : isBear ? 'rgba(239,68,68,0.2)' : 'rgba(148,163,184,0.2)';
                    const dirColor = isBull ? '#34d399' : isBear ? '#f87171' : '#94a3b8';
                    const dirIcon = isBull ? '🟢 BULLISH CATALYST' : isBear ? '🔴 BEARISH THREAT' : '⚪ NEUTRAL';

                    const cardBorder = isHigh ? 'border-left: 4px solid #ef4444;' : (isBull ? 'border-left: 4px solid #10b981;' : 'border-left: 4px solid #60a5fa;');

                    const headlineLink = c.link ? '<a href="' + c.link + '" target="_blank" rel="noopener noreferrer" style="color:var(--light);text-decoration:none;font-weight:700;font-size:0.95rem;line-height:1.4;" onmouseover="this.style.color=\'#60a5fa\'" onmouseout="this.style.color=\'var(--light)\'">' + c.title + ' ↗</a>' : '<span style="font-weight:700;font-size:0.95rem;color:var(--light);">' + c.title + '</span>';

                    const dateDisplay = this.formatNewsDate(c.published_at);

                    const sigPrice = (c.signal_price != null && c.signal_price > 0) ? '₹' + Number(c.signal_price).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : null;
                    const curPrice = (c.current_price != null && c.current_price > 0) ? '₹' + Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : null;
                    const chgPct = c.price_change_pct || 0;
                    const chgColor = chgPct > 0 ? '#34d399' : (chgPct < 0 ? '#f87171' : '#94a3b8');
                    const chgSign = chgPct > 0 ? '+' : '';
                    const priceBadge = (sigPrice && curPrice) ? `
                        <div style="display:inline-flex;align-items:center;gap:0.4rem;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.12);border-radius:5px;padding:0.12rem 0.5rem;font-size:0.72rem;" title="Price at time of news disclosure vs latest quote">
                            <span style="color:#94a3b8;">Signal Price: <strong style="color:#f8fafc;font-family:var(--font-mono);">${sigPrice}</strong></span>
                            <span style="color:#64748b;">→</span>
                            <span style="color:#94a3b8;">Now: <strong style="color:#38bdf8;font-family:var(--font-mono);">${curPrice}</strong></span>
                            <span style="color:${chgColor};font-weight:700;font-family:var(--font-mono);margin-left:0.2rem;">(${chgSign}${chgPct.toFixed(2)}%)</span>
                        </div>
                    ` : (curPrice ? `
                        <div style="display:inline-flex;align-items:center;gap:0.35rem;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.08);border-radius:5px;padding:0.12rem 0.45rem;font-size:0.72rem;">
                            <span style="color:#94a3b8;">Live Price: <strong style="color:#38bdf8;font-family:var(--font-mono);">${curPrice}</strong></span>
                        </div>
                    ` : '');

                    const aiTargetBadge = (c.ai_target != null && c.ai_target > 0) ? `
                        <div style="display:inline-flex;align-items:center;gap:0.35rem;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);border-radius:5px;padding:0.12rem 0.45rem;font-size:0.70rem;" title="OmniRouter AI Target Price & Defensive Invalidation Stop">
                            <span style="color:#34d399;font-weight:700;font-family:var(--font-mono);">🎯 Target: ₹${Number(c.ai_target).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2})}</span>
                            ${(c.ai_stop_loss != null && c.ai_stop_loss > 0) ? `<span style="color:#64748b;">|</span><span style="color:#f87171;font-weight:600;font-family:var(--font-mono);">🛡️ Stop: ₹${Number(c.ai_stop_loss).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2})}</span>` : ''}
                        </div>
                    ` : '';

                    const aiModelBadge = c.ai_model ? `
                        <span style="background:rgba(168,85,247,0.15);color:#c084fc;border:1px solid rgba(168,85,247,0.3);padding:0.12rem 0.45rem;border-radius:0.3rem;font-size:0.68rem;font-weight:700;font-family:var(--font-mono);" title="Analyzed by OmniRouter AI Engine">🤖 ${c.ai_model.replace('omnirouter/', '')}</span>
                    ` : '';

                    let parsedAi = null;
                    if (c.ai_analysis) {
                        try {
                            parsedAi = (typeof c.ai_analysis === 'string') ? JSON.parse(c.ai_analysis) : c.ai_analysis;
                        } catch (e) {
                            parsedAi = null;
                        }
                    }
                    const latVal = c.latency_ms || (parsedAi && parsedAi.latency_ms);
                    const latBadge = latVal ? `
                        <span style="background:rgba(251,191,36,0.12);color:#fbbf24;border:1px solid rgba(251,191,36,0.25);padding:0.12rem 0.45rem;border-radius:0.3rem;font-size:0.68rem;font-family:var(--font-mono);" title="Inference response round-trip latency">⏱️ ${latVal > 100 ? (latVal / 1000).toFixed(2) + 's' : latVal + 'ms'}</span>
                    ` : '';

                    const tokVal = c.tokens_used || (parsedAi && parsedAi.tokens_used);
                    const tokBadge = tokVal ? `
                        <span style="background:rgba(148,163,184,0.1);color:#94a3b8;border:1px solid rgba(148,163,184,0.2);padding:0.12rem 0.45rem;border-radius:0.3rem;font-size:0.68rem;font-family:var(--font-mono);" title="Token usage (Prompt + Completion)">🔢 ${tokVal} tok</span>
                    ` : '';

                    const displayTakeaway = c.ai_takeaway || (parsedAi && parsedAi.trading_takeaway) || c.why_it_matters || '';

                    const isRePub = c.is_republication === 1 || c.is_republication === true || c.temporal_originality === 'REPUBLICATION';
                    const origType = c.temporal_originality || (isRePub ? 'REPUBLICATION' : 'NEW_PUBLICATION');
                    const origRationale = c.originality_rationale || (isRePub ? 'Repetitive or historical recap of past event.' : 'Novel primary news disclosure.');
                    
                    const origBadge = isRePub ? `
                        <span style="background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);padding:0.12rem 0.45rem;border-radius:0.3rem;font-size:0.68rem;font-weight:700;" title="${origRationale}">🔄 Republication</span>
                    ` : (origType === 'BREAKING' ? `
                        <span style="background:rgba(16,185,129,0.2);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:0.12rem 0.45rem;border-radius:0.3rem;font-size:0.68rem;font-weight:700;" title="${origRationale}">⚡ Fresh Breaking</span>
                    ` : `
                        <span style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:0.12rem 0.45rem;border-radius:0.3rem;font-size:0.68rem;font-weight:600;" title="${origRationale}">📰 New Publication</span>
                    `);

                    let parsedProj = null;
                    if (c.financial_projections) {
                        try {
                            parsedProj = (typeof c.financial_projections === 'string') ? JSON.parse(c.financial_projections) : c.financial_projections;
                        } catch (e) {
                            parsedProj = null;
                        }
                    }
                    const projBadge = (parsedProj && (parsedProj.order_value_cr || parsedProj.revenue_projection_cr || parsedProj.ebitda_margin_pct || parsedProj.growth_rate_pct)) ? `
                        <div style="display:inline-flex;align-items:center;gap:0.3rem;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.25);border-radius:5px;padding:0.12rem 0.45rem;font-size:0.70rem;color:#fcd34d;" title="Extracted Financial Projections">
                            ${parsedProj.order_value_cr ? `<span>💼 Order: <strong>₹${parsedProj.order_value_cr} Cr</strong></span>` : ''}
                            ${parsedProj.revenue_projection_cr ? `<span>📊 Rev: <strong>₹${parsedProj.revenue_projection_cr} Cr</strong></span>` : ''}
                            ${parsedProj.ebitda_margin_pct ? `<span>📈 Margin: <strong>${parsedProj.ebitda_margin_pct}%</strong></span>` : ''}
                            ${parsedProj.growth_rate_pct ? `<span>🚀 Growth: <strong>+${parsedProj.growth_rate_pct}%</strong></span>` : ''}
                        </div>
                    ` : '';

                    let affTickers = [];
                    if (c.affected_tickers) {
                        try {
                            affTickers = typeof c.affected_tickers === 'string' ? JSON.parse(c.affected_tickers) : c.affected_tickers;
                        } catch(_) {
                            affTickers = [];
                        }
                    }
                    const otherPeers = Array.isArray(affTickers) ? affTickers.filter(t => String(t).toUpperCase() !== String(c.ticker).toUpperCase()) : [];
                    const multiStockBadge = otherPeers.length > 0
                        ? `<span class="signal-badge" style="background:rgba(236,72,153,0.15);color:#f472b6;border:1px solid rgba(236,72,153,0.35);font-size:0.7rem;padding:0.12rem 0.45rem;border-radius:0.3rem;" title="Multi-stock impact: ${otherPeers.join(', ')}">⚡ Also Impacts: ${otherPeers.slice(0, 3).map(t => `<a href="/stock/${encodeURIComponent(t)}" target="_blank" style="color:#f472b6;text-decoration:none;font-weight:700;">${String(t).replace('.NS','')}</a>`).join(', ')}${otherPeers.length > 3 ? ` +${otherPeers.length - 3}` : ''}</span>`
                        : '';

                    const isSel = (this.selectedCatalysts && this.selectedCatalysts.has(c.ticker + '|||' + c.title)) ? 'checked' : '';

                    return '<div class="card" style="margin:0;padding:1rem;background:rgba(255,255,255,0.03);' + cardBorder + 'transition:transform 0.15s ease;">' +
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.45rem;">' +
                            '<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">' +
                                `<input type="checkbox" class="cat-select-checkbox" data-ticker="${c.ticker}" data-title="${encodeURIComponent(c.title)}" ${isSel} onchange="app.onCatalystCheckboxChange(this)" style="cursor:pointer;width:15px;height:15px;accent-color:#3b82f6;margin-right:0.1rem;" title="Select for on-demand AI analysis">` +
                                ((c.stock_name && c.stock_name.trim().toUpperCase() !== c.ticker.trim().toUpperCase())
                                    ? '<strong style="font-size:1.05rem;color:#f8fafc;">' + c.stock_name + '</strong><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" class="signal-badge" style="background:rgba(59,130,246,0.2);color:#60a5fa;font-size:0.72rem;text-decoration:none;" title="Open stock intelligence">' + c.ticker + ' ↗</a>'
                                    : '<a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="font-size:1.05rem;font-weight:700;color:#60a5fa;text-decoration:none;">' + c.ticker + ' ↗</a>') +
                                multiStockBadge +
                                priceBadge +
                                aiTargetBadge +
                                projBadge +
                                origBadge +
                                '<span style="background:' + impactBadgeBg + ';color:' + impactBadgeColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + impactLabel + '</span>' +
                                '<span style="background:' + dirBadgeBg + ';color:' + dirColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + dirIcon + '</span>' +
                                '<span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;">' + c.category + '</span>' +
                                aiModelBadge +
                                latBadge +
                                tokBadge +
                            '</div>' +
                            '<div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">' +
                                '<span class="timestamp" style="font-size:0.72rem;background:rgba(255,255,255,0.05);padding:0.15rem 0.45rem;border-radius:0.25rem;">' + (c.publisher || 'News') + ' &middot; ⏱️ ' + dateDisplay + '</span>' +
                                `<button type="button" onclick="app.analyzeSingleCatalyst('${encodeURIComponent(c.ticker)}', '${encodeURIComponent(c.title)}', this)" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(168,85,247,0.2);color:#c084fc;border:1px solid rgba(168,85,247,0.45);border-radius:0.3rem;font-weight:700;" title="Run on-demand AI re-evaluation using selected model">⚡ Re-evaluate</button>` +
                                `<button type="button" onclick="app.showNewsRawOutput(${filtered.indexOf(c)})" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(168,85,247,0.15);color:#c084fc;border:1px solid rgba(168,85,247,0.35);border-radius:0.3rem;" title="Inspect raw OmniRouter AI JSON telemetry">📄 Raw AI</button>` +
                                `<button type="button" onclick="app.runConsensusForStock('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.45);border-radius:0.3rem;font-weight:700;" title="Run AI Multi-Model Consensus for Target, Resistance, Support & Buy Zone">🧠 Consensus</button>` +
                                `<button type="button" onclick="app.openAddToWatchlistModal('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);border-radius:0.3rem;" title="Add to Watchlist">⭐ Watchlist</button>` +
                                `<button type="button" onclick="app.runPredictionForTickerSingle('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run Kronos Forecast">🔮 Predict</button>` +
                            '</div>' +
                        '</div>' +
                        '<div style="margin-bottom:0.5rem;">' + headlineLink + '</div>' +
                        (c.summary ? '<p style="margin:0 0 0.5rem 0;font-size:0.82rem;color:#cbd5e1;line-height:1.45;">' + c.summary + '</p>' : '') +
                        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;background:rgba(0,0,0,0.2);padding:0.45rem 0.65rem;border-radius:0.4rem;border:1px solid rgba(255,255,255,0.06);font-size:0.75rem;">' +
                            '<div style="color:#38bdf8;font-weight:600;"><span style="color:#c084fc;font-weight:700;">💡 AI Takeaway: </span>' + displayTakeaway + '</div>' +
                            '<div style="display:flex;gap:0.6rem;color:var(--muted);white-space:nowrap;">' +
                                '<span>Expected Horizon: <strong style="color:var(--light);">' + (c.expected_horizon || '1-3 Days') + '</strong></span>' +
                                '<span>Move Est: <strong style="color:#fbbf24;">' + (c.volatility_est || '±3%') + '</strong></span>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');

                this.updateCatalystSelectionState();
            },

            onCatalystCheckboxChange(checkboxEl) {
                if (!this.selectedCatalysts) this.selectedCatalysts = new Set();
                const ticker = checkboxEl.getAttribute('data-ticker');
                const title = decodeURIComponent(checkboxEl.getAttribute('data-title') || '');
                const key = ticker + '|||' + title;
                if (checkboxEl.checked) {
                    this.selectedCatalysts.add(key);
                } else {
                    this.selectedCatalysts.delete(key);
                }
                this.updateCatalystSelectionState();
            },

            toggleSelectAllCatalysts(checked) {
                if (!this.selectedCatalysts) this.selectedCatalysts = new Set();
                const checkboxes = document.querySelectorAll('.cat-select-checkbox');
                checkboxes.forEach(cb => {
                    cb.checked = checked;
                    const ticker = cb.getAttribute('data-ticker');
                    const title = decodeURIComponent(cb.getAttribute('data-title') || '');
                    const key = ticker + '|||' + title;
                    if (checked) {
                        this.selectedCatalysts.add(key);
                    } else {
                        this.selectedCatalysts.delete(key);
                    }
                });
                this.updateCatalystSelectionState();
            },

            updateCatalystSelectionState() {
                const count = (this.selectedCatalysts ? this.selectedCatalysts.size : 0);
                const batchBtn = document.getElementById('catAnalyzeBatchBtn');
                const countSpan = document.getElementById('catSelectedCount');
                const selectAllCb = document.getElementById('catSelectAllCheckbox');

                if (countSpan) countSpan.textContent = count;
                if (batchBtn) {
                    batchBtn.style.display = count > 0 ? 'inline-flex' : 'none';
                }
                if (selectAllCb) {
                    const allCbs = document.querySelectorAll('.cat-select-checkbox');
                    if (allCbs.length > 0) {
                        selectAllCb.checked = (count === allCbs.length);
                        selectAllCb.indeterminate = (count > 0 && count < allCbs.length);
                    } else {
                        selectAllCb.checked = false;
                        selectAllCb.indeterminate = false;
                    }
                }
            },

            async analyzeSingleCatalyst(encodedTicker, encodedTitle, btnEl, specificModel = null) {
                const ticker = decodeURIComponent(encodedTicker);
                const title = decodeURIComponent(encodedTitle);
                const model = specificModel || document.getElementById('catModelSelect')?.value || 'google/gemini-2.5-flash';
                const origHtml = btnEl ? btnEl.innerHTML : '';
                if (btnEl) {
                    btnEl.disabled = true;
                    btnEl.innerHTML = '⏳ Analyzing...';
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/news/analyze-ondemand', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ticker, title, model})
                    });
                    const data = await res.json();
                    if (data.success && (data.catalyst || data.id)) {
                        const updated = data.catalyst || data;
                        const idx = (this.catalystsData || []).findIndex(x => x.ticker === ticker && x.title === title);
                        if (idx !== -1) {
                            this.catalystsData[idx] = { ...this.catalystsData[idx], ...updated };
                        }
                        this.renderCatalysts();
                        if (typeof this.showToast === 'function') {
                            this.showToast(`Re-evaluated ${ticker} using ${model.split('/').pop()}`, 'success');
                        }
                    } else {
                        if (typeof this.showToast === 'function') {
                            this.showToast(data.detail || 'Analysis failed', 'error');
                        }
                    }
                } catch (e) {
                    console.error('Error analyzing catalyst:', e);
                    if (typeof this.showToast === 'function') {
                        this.showToast('AI analysis request failed', 'error');
                    }
                } finally {
                    if (btnEl) {
                        btnEl.disabled = false;
                        btnEl.innerHTML = origHtml || '⚡ Re-evaluate';
                    }
                }
            },

            async analyzeSelectedCatalysts() {
                if (!this.selectedCatalysts || this.selectedCatalysts.size === 0) return;
                const items = [];
                this.selectedCatalysts.forEach(key => {
                    const parts = key.split('|||');
                    if (parts.length >= 2) {
                        items.push({ticker: parts[0], title: parts.slice(1).join('|||')});
                    }
                });
                if (!items.length) return;

                const model = document.getElementById('catModelSelect')?.value || 'google/gemini-2.5-flash';
                const batchBtn = document.getElementById('catAnalyzeBatchBtn');
                const iconSpan = document.getElementById('catBatchBtnIcon');
                if (batchBtn) batchBtn.disabled = true;
                if (iconSpan) iconSpan.textContent = '⏳';

                try {
                    const res = await fetch(API_BASE + '/api/v1/news/analyze-batch', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items, model})
                    });
                    const data = await res.json();
                    if (data.success && data.catalysts) {
                        data.catalysts.forEach(updated => {
                            const idx = (this.catalystsData || []).findIndex(x => x.ticker === updated.ticker && x.title === updated.title);
                            if (idx !== -1) {
                                this.catalystsData[idx] = { ...this.catalystsData[idx], ...updated };
                            }
                        });
                        this.selectedCatalysts.clear();
                        this.renderCatalysts();
                        this.updateCatalystSelectionState();
                        if (typeof this.showToast === 'function') {
                            this.showToast(`Successfully analyzed ${data.count} items with ${model.split('/').pop()}!`, 'success');
                        }
                    } else {
                        if (typeof this.showToast === 'function') {
                            this.showToast(data.detail || 'Batch analysis failed', 'error');
                        }
                    }
                } catch (e) {
                    console.error('Error running batch analysis:', e);
                    if (typeof this.showToast === 'function') {
                        this.showToast('Batch AI analysis request failed', 'error');
                    }
                } finally {
                    if (batchBtn) batchBtn.disabled = false;
                    if (iconSpan) iconSpan.textContent = '⚡';
                }
            },

            showNewsRawOutput(idxOrObj, directObj) {
                let c = directObj;
                if (!c && typeof idxOrObj === 'object' && idxOrObj !== null) {
                    c = idxOrObj;
                }
                if (!c && typeof idxOrObj === 'number') {
                    c = (this._lastFilteredCatalysts && this._lastFilteredCatalysts[idxOrObj]) || 
                        (this.catalystsData && this.catalystsData[idxOrObj]) ||
                        (window.app && window.app.catalystsData && window.app.catalystsData[idxOrObj]);
                }
                if (!c && typeof idxOrObj === 'string') {
                    c = (this.catalystsData || []).find(x => x.id === idxOrObj || (x.ticker && x.ticker.trim().toUpperCase() === idxOrObj.trim().toUpperCase())) ||
                        (this._lastFilteredCatalysts || []).find(x => x.id === idxOrObj || (x.ticker && x.ticker.trim().toUpperCase() === idxOrObj.trim().toUpperCase()));
                }
                if (!c) return;

                const modal = document.getElementById('modalNewsRawOutput');
                if (!modal) return;

                const tickerEl = document.getElementById('newsRawModalTicker');
                const nameEl = document.getElementById('newsRawModalStockName');
                const modelBadge = document.getElementById('newsRawModalModelBadge');
                const headlineEl = document.getElementById('newsRawModalHeadline');
                const impactBadge = document.getElementById('newsRawModalImpactBadge');
                const sigPriceEl = document.getElementById('newsRawModalSignalPrice');
                const curPriceEl = document.getElementById('newsRawModalCurrentPrice');
                const priceDeltaEl = document.getElementById('newsRawModalPriceDelta');
                const targetEl = document.getElementById('newsRawModalTargetPrice');
                const stopEl = document.getElementById('newsRawModalStopLoss');
                const latEl = document.getElementById('newsRawModalLatency');
                const tokEl = document.getElementById('newsRawModalTokens');
                const takeawayEl = document.getElementById('newsRawModalTakeaway');
                const horizonEl = document.getElementById('newsRawModalHorizon');
                const volEl = document.getElementById('newsRawModalVolatility');
                const riskEl = document.getElementById('newsRawModalRisk');
                const preEl = document.getElementById('newsRawModalContent');
                const timeEl = document.getElementById('newsRawModalTimestamp');

                let parsedAi = null;
                if (c.ai_analysis) {
                    try {
                        parsedAi = (typeof c.ai_analysis === 'string') ? JSON.parse(c.ai_analysis) : c.ai_analysis;
                    } catch (e) {
                        parsedAi = null;
                    }
                }

                if (tickerEl) tickerEl.textContent = c.ticker;
                if (nameEl) nameEl.textContent = c.stock_name || c.ticker;
                if (modelBadge) modelBadge.textContent = '🤖 ' + (c.ai_model || (parsedAi && parsedAi.ai_model) || 'omniroute/deepseek-r1');
                if (headlineEl) headlineEl.textContent = c.title || '';
                if (impactBadge) {
                    impactBadge.textContent = `⚡ ${c.impact_level || 'MEDIUM'} (${c.impact_score || 75}%)`;
                    impactBadge.style.color = (c.impact_level === 'HIGH') ? '#f87171' : '#fbbf24';
                    impactBadge.style.background = (c.impact_level === 'HIGH') ? 'rgba(239,68,68,0.2)' : 'rgba(251,191,36,0.2)';
                }

                const sigP = c.signal_price ? '₹' + Number(c.signal_price).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : '—';
                const curP = c.current_price ? '₹' + Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : '—';
                const dPct = c.price_change_pct || 0;
                const dColor = dPct > 0 ? '#34d399' : (dPct < 0 ? '#f87171' : '#94a3b8');
                const dSign = dPct > 0 ? '+' : '';

                if (sigPriceEl) sigPriceEl.textContent = sigP;
                if (curPriceEl) curPriceEl.textContent = curP;
                if (priceDeltaEl) {
                    priceDeltaEl.textContent = `${dSign}${Number(dPct).toFixed(2)}%`;
                    priceDeltaEl.style.color = dColor;
                }

                const targP = c.ai_target || (parsedAi && parsedAi.target_price);
                const slP = c.ai_stop_loss || (parsedAi && parsedAi.stop_loss);
                if (targetEl) targetEl.textContent = targP ? '₹' + Number(targP).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : '—';
                if (stopEl) stopEl.textContent = slP ? '₹' + Number(slP).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : '—';

                const latVal = c.latency_ms || (parsedAi && parsedAi.latency_ms) || 1200;
                const tokVal = c.tokens_used || (parsedAi && parsedAi.tokens_used) || 450;
                if (latEl) latEl.textContent = latVal > 100 ? (latVal / 1000).toFixed(2) + 's' : latVal + 'ms';
                if (tokEl) tokEl.textContent = tokVal + ' tokens';

                if (takeawayEl) takeawayEl.textContent = c.ai_takeaway || (parsedAi && parsedAi.trading_takeaway) || c.why_it_matters || 'No takeaway generated';
                if (horizonEl) horizonEl.textContent = c.expected_horizon || (parsedAi && parsedAi.expected_horizon) || '1-3 Days';
                if (volEl) volEl.textContent = c.volatility_est || (parsedAi && parsedAi.volatility_est) || '±3%';
                if (riskEl) riskEl.textContent = (parsedAi && parsedAi.primary_risk) || 'Broader market benchmark volatility';

                if (timeEl) timeEl.textContent = c.ai_analyzed_at || c.published_at || new Date().toISOString();

                // Format Full JSON Output
                const rawPayload = parsedAi || {
                    ticker: c.ticker,
                    title: c.title,
                    direction: c.direction,
                    impact_score: c.impact_score,
                    impact_level: c.impact_level,
                    expected_horizon: c.expected_horizon,
                    volatility_est: c.volatility_est,
                    signal_price: c.signal_price,
                    current_price: c.current_price,
                    target_price: c.ai_target,
                    stop_loss: c.ai_stop_loss,
                    trading_takeaway: c.ai_takeaway || c.why_it_matters,
                    ai_model: c.ai_model,
                    latency_ms: latVal,
                    tokens_used: tokVal,
                };
                if (preEl) preEl.textContent = JSON.stringify(rawPayload, null, 2);

                modal.style.zIndex = '999999';
                modal.style.display = 'flex';
            },

            closeNewsRawModal() {
                const modal = document.getElementById('modalNewsRawOutput');
                if (modal) modal.style.display = 'none';
            },

            copyNewsRawOutput() {
                const pre = document.getElementById('newsRawModalContent');
                const btn = document.getElementById('btnNewsCopyRaw');
                if (!pre) return;
                navigator.clipboard.writeText(pre.textContent).then(() => {
                    if (btn) {
                        const orig = btn.innerHTML;
                        btn.innerHTML = '✅ Copied!';
                        setTimeout(() => { btn.innerHTML = orig; }, 1800);
                    }
                }).catch(e => {
                    console.error('Clipboard copy failed:', e);
                });
            },

            async scanCatalystsNow() {
                const btn = document.getElementById('catScanBtn');
                const wlSelect = document.getElementById('catWatchlistSelect');
                const wl = wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL');
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Scanning Feeds...';
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/news/scan', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({watchlist: wl, limit_per_stock: 3})
                    });
                    const data = await res.json();
                    await this.loadCatalysts(wl);
                } catch (e) {
                    console.error('Error scanning catalysts:', e);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '⚡ Scan Feeds';
                    }
                }
            },
    });
})(); // end catalysts IIFE
