// =========================================================================
// catalysts — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[catalysts] window.app not initialized'); return; }

    Object.assign(app, {
            // =========================================================================
            // 📰 Short-Term Catalysts & High-Impact News Tab
            // =========================================================================
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
                
                try {
                    // Fetch stats and items in parallel
                    const [itemsRes, statsRes] = await Promise.all([
                        fetch(API_BASE + '/api/v1/news/catalysts' + wlParam),
                        fetch(API_BASE + '/api/v1/news/catalyst-stats' + statsParam)
                    ]);
                    const itemsData = await itemsRes.json();
                    const statsData = await statsRes.json();

                    this.catalystsData = itemsData.catalysts || [];
                    this.renderCatalystsStats(statsData.stats || {});
                    this.renderCatalysts();
                } catch (e) {
                    console.error('Error loading catalysts:', e);
                    if (feedGrid) feedGrid.innerHTML = '<div class="card" style="padding:1rem;color:var(--red);">Failed loading catalysts feed. Click "⚡ Scan Feeds" to refresh.</div>';
                }
            },

            async loadNewsOutcomes() {
                const tableBody = document.getElementById('outcomesTableBody');
                if (tableBody) tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading historical verified news outcomes & performance metrics...</td></tr>';
                
                try {
                    const [metricsRes, outcomesRes] = await Promise.all([
                        fetch(API_BASE + '/api/v1/news/trade-metrics'),
                        fetch(API_BASE + '/api/v1/news/outcomes?limit=100')
                    ]);
                    const metricsData = await metricsRes.json();
                    const outcomesData = await outcomesRes.json();

                    this.outcomesMetrics = metricsData.metrics || {};
                    this.outcomesData = outcomesData.outcomes || [];

                    this.renderNewsTradeMetrics(this.outcomesMetrics);
                    this.renderNewsOutcomes();
                } catch (e) {
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

                    return '<div class="card" style="margin:0;padding:1rem;background:rgba(255,255,255,0.03);' + cardBorder + 'transition:transform 0.15s ease;">' +
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.45rem;">' +
                            '<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">' +
                                ((c.stock_name && c.stock_name.trim().toUpperCase() !== c.ticker.trim().toUpperCase())
                                    ? '<strong style="font-size:1.05rem;color:#f8fafc;">' + c.stock_name + '</strong><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" class="signal-badge" style="background:rgba(59,130,246,0.2);color:#60a5fa;font-size:0.72rem;text-decoration:none;" title="Open stock intelligence">' + c.ticker + ' ↗</a>'
                                    : '<a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="font-size:1.05rem;font-weight:700;color:#60a5fa;text-decoration:none;">' + c.ticker + ' ↗</a>') +
                                priceBadge +
                                '<span style="background:' + impactBadgeBg + ';color:' + impactBadgeColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + impactLabel + '</span>' +
                                '<span style="background:' + dirBadgeBg + ';color:' + dirColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + dirIcon + '</span>' +
                                '<span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;">' + c.category + '</span>' +
                            '</div>' +
                            '<div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">' +
                                '<span class="timestamp" style="font-size:0.72rem;background:rgba(255,255,255,0.05);padding:0.15rem 0.45rem;border-radius:0.25rem;">' + (c.publisher || 'News') + ' &middot; ⏱️ ' + dateDisplay + '</span>' +
                                `<button type="button" onclick="app.runConsensusForStock('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.45);border-radius:0.3rem;font-weight:700;" title="Run AI Multi-Model Consensus for Target, Resistance, Support & Buy Zone">🧠 Consensus</button>` +
                                `<button type="button" onclick="app.openAddToWatchlistModal('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);border-radius:0.3rem;" title="Add to Watchlist">⭐ Watchlist</button>` +
                                `<button type="button" onclick="app.runPredictionForTickerSingle('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run Kronos Forecast">🔮 Predict</button>` +
                            '</div>' +
                        '</div>' +
                        '<div style="margin-bottom:0.5rem;">' + headlineLink + '</div>' +
                        (c.summary ? '<p style="margin:0 0 0.5rem 0;font-size:0.82rem;color:#cbd5e1;line-height:1.45;">' + c.summary + '</p>' : '') +
                        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;background:rgba(0,0,0,0.2);padding:0.45rem 0.65rem;border-radius:0.4rem;border:1px solid rgba(255,255,255,0.06);font-size:0.75rem;">' +
                            '<div style="color:#38bdf8;font-weight:600;"><span style="color:var(--muted);">💡 Why this matters: </span>' + (c.why_it_matters || '') + '</div>' +
                            '<div style="display:flex;gap:0.6rem;color:var(--muted);white-space:nowrap;">' +
                                '<span>Expected Horizon: <strong style="color:var(--light);">' + (c.expected_horizon || '1-3 Days') + '</strong></span>' +
                                '<span>Move Est: <strong style="color:#fbbf24;">' + (c.volatility_est || '±3%') + '</strong></span>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');
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
