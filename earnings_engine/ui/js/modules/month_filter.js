// =========================================================================
// month_filter — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
// =========================================================================
            // 🗓️ Month Filter & Earnings Calendar Dedicated Tab
            // =========================================================================
            async loadMonthFilterTab(forceSync = false) {
                const statusEl = document.getElementById('mfReportStatus');
                const sectionsEl = document.getElementById('mfReportSections');
                const countBadge = document.getElementById('mfCount');
                const market = document.getElementById('mfMarket')?.value || 'ALL';
                const cancelBtn = document.getElementById('mfCancelBtn');
                if (cancelBtn) cancelBtn.style.display = 'inline-block';

                if (statusEl) statusEl.textContent = forceSync ? 'Syncing present day delta...' : 'Loading precalculated Month Filter data...';

                try {
                    const url = '/api/v1/dashboard/month-filter?market=' + encodeURIComponent(market) + (forceSync ? '&force_sync=true' : '');
                    const res = await this.fetchWithAbort('monthfilter', url);
                    const data = await res.json();

                    if (!data || data.error) {
                        if (sectionsEl) sectionsEl.innerHTML = '<div class="card" style="padding:1.5rem;color:var(--muted);text-align:center;">' + (data.error || 'Failed to load month filter') + '</div>';
                        return;
                    }

                    // Render Fetch Record Banner
                    const rec = data.fetch_record || {};
                    const syncBannerText = document.getElementById('mfSyncText');
                    const statusBadge = document.getElementById('mfStatusBadge');
                    const lastSyncedEl = document.getElementById('mfLastSynced');
                    const totalEventsEl = document.getElementById('mfTotalEvents');
                    const insertedCountEl = document.getElementById('mfInsertedCount');

                    if (rec) {
                        if (statusBadge) {
                            statusBadge.textContent = rec.synced_today ? '🟢 UP TO DATE' : '🟡 STALE';
                            statusBadge.style.background = rec.synced_today ? '#10b981' : '#f59e0b';
                        }
                        if (syncBannerText) {
                            syncBannerText.textContent = rec.synced_today
                                ? 'Present day earnings calendar is up-to-date for ' + rec.today + '.'
                                : 'Earnings data not synced for today (' + rec.today + '). Delta fetch recommended.';
                        }
                        if (lastSyncedEl) lastSyncedEl.textContent = rec.last_fetched_at || rec.today || '--';
                        if (totalEventsEl) totalEventsEl.textContent = rec.events_count || data.total_stocks || 0;
                        if (insertedCountEl) insertedCountEl.textContent = rec.inserted_count || 0;
                    }

                    if (data.popups) {
                        let wrap = document.getElementById('resultsReportPopups');
                        if (!wrap) {
                            wrap = document.createElement('div');
                            wrap.id = 'resultsReportPopups';
                            document.body.appendChild(wrap);
                        }
                        wrap.innerHTML += data.popups;
                    }

                    this.mfDaySections = data.day_sections_list || [];
                    this.mfDaySectionsMeta = data.day_sections_meta || [];
                    this.mfMonths = data.months || [];
                    this.mfTotalStocks = data.total_stocks || 0;
                    this.mfActiveMonth = 'ALL';

                    this.renderMfMonthTabs();
                    this.renderMfSections();
                    this.populateMfIndustryFilter();

                    if (countBadge) {
                        countBadge.textContent = this.mfTotalStocks + ' results (' + this.mfDaySectionsMeta.length + ' dates)';
                    }
                    if (statusEl) statusEl.textContent = 'Month Filter loaded: ' + this.mfTotalStocks + ' results across ' + this.mfDaySectionsMeta.length + ' dates (' + new Date().toLocaleTimeString() + ')';
                } catch (e) {
                    if (e.name === 'AbortError') {
                        console.log('Month Filter fetch aborted:', e.message);
                        if (statusEl) statusEl.textContent = '⚠️ Request cancelled (' + (e.message || 'aborted') + ').';
                        return;
                    }
                    console.error('Error loading Month Filter tab:', e);
                    if (statusEl) statusEl.textContent = 'Error loading Month Filter: ' + (e.message || e);
                } finally {
                    this.resetTaskLoadingUI('monthfilter');
                }
            },

            async syncMonthFilter() {
                if (this.isMaster === false) {
                    alert('⚠️ Access Restricted: Syncing dataset delta is restricted to Master role.');
                    return;
                }
                const syncBtn = document.getElementById('mfSyncBtn');
                if (syncBtn) {
                    syncBtn.disabled = true;
                    syncBtn.innerHTML = '🔄 Syncing...';
                }
                try {
                    await this.loadMonthFilterTab(true);
                } finally {
                    if (syncBtn) {
                        syncBtn.disabled = false;
                        syncBtn.innerHTML = '🔄 Sync Delta';
                    }
                }
            },

            renderMfMonthTabs() {
                const el = document.getElementById('mfMonthTabs');
                if (!el || !this.mfMonths || !this.mfMonths.length) return;

                let html = '<span style="font-size:0.75rem;font-weight:700;color:var(--muted);text-transform:uppercase;margin-right:0.25rem;">🗓️ Month Filter:</span>';
                const allActive = (this.mfActiveMonth === 'ALL');
                const allBtnStyle = allActive
                    ? 'background:var(--accent);color:#fff;font-weight:700;border:1px solid var(--accent);'
                    : 'background:rgba(255,255,255,0.06);color:var(--light);border:1px solid rgba(255,255,255,0.15);';

                html += '<button type="button" onclick="app.filterMfByMonth(\'ALL\')" class="btn btn-sm" style="' + allBtnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                    '🌐 All (±2M) <span style="background:rgba(0,0,0,0.25);padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;margin-left:0.2rem;">' + this.mfTotalStocks + '</span>' +
                    '</button>';

                this.mfMonths.forEach(m => {
                    const isActive = (this.mfActiveMonth === m.month_key);
                    const tag = m.is_current ? '⭐ ' : (m.is_past ? '◀ ' : '▶ ');
                    let btnStyle = isActive
                        ? 'background:#2563eb;color:#fff;font-weight:700;border:1px solid #3b82f6;'
                        : (m.is_current ? 'background:rgba(16,185,129,0.15);color:#6ee7b7;border:1px solid rgba(16,185,129,0.35);'
                        : 'background:rgba(255,255,255,0.06);color:var(--light);border:1px solid rgba(255,255,255,0.15);');

                    html += '<button type="button" onclick="app.filterMfByMonth(\'' + m.month_key + '\')" class="btn btn-sm" style="' + btnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                        tag + m.month_label + ' ' +
                        '<span style="background:rgba(0,0,0,0.25);padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;font-weight:700;margin-left:0.2rem;">' + (m.stocks_count || 0) + '</span>' +
                        '</button>';
                });

                el.innerHTML = html;
            },

            filterMfByMonth(monthKey) {
                this.mfActiveMonth = monthKey;
                this.renderMfMonthTabs();
                this.renderMfSections();
            },

            renderMfSections() {
                const el = document.getElementById('mfReportSections');
                if (!el) return;

                let items = this.mfDaySectionsMeta || [];
                if (this.mfActiveMonth !== 'ALL') {
                    items = items.filter(m => m.month_key === this.mfActiveMonth);
                }

                const htmls = items.map(m => m.html);
                el.innerHTML = htmls.length ? htmls.join('\n') : '<p class="timestamp">No earnings data for this month selection.</p>';
            },

            populateMfIndustryFilter() {
                const select = document.getElementById('mfIndustryFilter');
                if (!select) return;
                const industries = new Set();

                (this.mfDaySectionsMeta || []).forEach(m => {
                    const matches = m.html.match(/Industry:\s*([^<]+)/g) || [];
                    matches.forEach(str => {
                        const ind = str.replace('Industry:', '').trim();
                        if (ind) industries.add(ind);
                    });
                });

                let options = '<option value="ALL">All Industries (' + industries.size + ')</option>';
                Array.from(industries).sort().forEach(ind => {
                    options += '<option value="' + ind.replace(/"/g, '&quot;') + '">' + ind + '</option>';
                });
                select.innerHTML = options;
            },

            filterMonthFilterRows() {
                const query = (document.getElementById('mfSearchInput')?.value || '').toLowerCase().trim();
                const selectedInd = document.getElementById('mfIndustryFilter')?.value || 'ALL';
                const el = document.getElementById('mfReportSections');
                if (!el) return;

                let items = this.mfDaySectionsMeta || [];
                if (this.mfActiveMonth !== 'ALL') {
                    items = items.filter(m => m.month_key === this.mfActiveMonth);
                }

                const filteredHtml = [];
                items.forEach(m => {
                    if (selectedInd !== 'ALL' && !m.html.includes(selectedInd)) return;
                    if (query && !m.html.toLowerCase().includes(query)) return;
                    filteredHtml.push(m.html);
                });

                el.innerHTML = filteredHtml.length ? filteredHtml.join('\n') : '<p class="timestamp">No matching results for your query/industry filter.</p>';
            },

            renderResultsWidgets() {
                const el = document.getElementById('resultsWidgets');
                if (!el) return;
                if (!this.resultsData.length) {
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No upcoming results found. Try a different market or refresh data.</div>';
                    return;
                }
                el.innerHTML = this.resultsData.slice(0, 6).map(r => {
                    const mom = r.thirty_day_return_pct !== null ? r.thirty_day_return_pct : 0;
                    const mom7 = r.seven_day_return_pct !== null ? r.seven_day_return_pct : 0;
                    const cls = mom >= 0 ? 'price-positive' : 'price-negative';
                    const cls7 = mom7 >= 0 ? 'price-positive' : 'price-negative';
                    const signal = mom > 3 ? 'Bullish' : mom < -3 ? 'Bearish' : 'Neutral';
                    const badgeStyle = mom > 3 ? 'background:rgba(16,185,129,0.2);color:#10b981' : mom < -3 ? 'background:rgba(239,68,68,0.2);color:#ef4444' : 'background:rgba(148,163,184,0.2);color:#94a3b8';
                    const kp = r.kronos_prediction || {};
                    const trend = kp.trend || 'N/A';
                    const trendStyle = trend === 'Bullish' ? 'color:#10b981' : trend === 'Bearish' ? 'color:#ef4444' : 'color:#94a3b8';
                    return '<div class="widget-card">' +
                        '<h4>' + (r.ticker || '?') + '<a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></h4>' +
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">' +
                        '<span class="timestamp">' + (r.earnings_date || 'N/A') + '</span>' +
                        '<span class="signal-badge" style="' + badgeStyle + '">' + signal + '</span></div>' +
                        '<div class="metric" style="margin-bottom:0.4rem"><span>Current Price</span><strong>' + (r.current_price ? '$' + r.current_price.toFixed(2) : 'N/A') + '</strong></div>' +
                        '<div class="metric" style="margin-bottom:0.4rem"><span>7D Return</span><strong class="' + cls7 + '">' + (r.seven_day_return_pct !== null ? r.seven_day_return_pct.toFixed(2) + '%' : 'N/A') + '</strong></div>' +
                        '<div class="metric" style="margin-bottom:0.4rem"><span>30D Return</span><strong class="' + cls + '">' + (r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A') + '</strong></div>' +
                        '<div class="metric"><span>Market Cap</span><strong>' + (r.market_cap ? this.formatMarketCap(r.market_cap) : 'N/A') + '</strong></div>' +
                        '<div class="metric" style="margin-top:0.4rem"><span>Kronos Trend</span><strong style="' + trendStyle + '">' + trend + '</strong></div>' +
                        '</div>';
                }).join('');
            },

            renderResultsTable() {
                const tbody = document.getElementById('resultsTable');
                const sorted = [...this.resultsData].sort((a, b) => {
                    let va = a[this.sortKey], vb = b[this.sortKey];
                    va = va === null ? -Infinity : (this.sortKey === 'earnings_date' ? new Date(va) : va);
                    vb = vb === null ? -Infinity : (this.sortKey === 'earnings_date' ? new Date(vb) : vb);
                    if (va < vb) return this.sortDir === 'asc' ? -1 : 1;
                    if (va > vb) return this.sortDir === 'asc' ? 1 : -1;
                    return 0;
                });

                if (!sorted.length) {
                    tbody.innerHTML = '<tr><td colspan="11" style="padding:1rem;text-align:center;color:var(--muted)">No results</td></tr>';
                    return;
                }
                tbody.innerHTML = sorted.map(r => {
                    const mom = r.thirty_day_return_pct !== null ? r.thirty_day_return_pct : 0;
                    const mom7 = r.seven_day_return_pct !== null ? r.seven_day_return_pct : 0;
                    const cls = mom >= 0 ? 'price-positive' : 'price-negative';
                    const cls7 = mom7 >= 0 ? 'price-positive' : 'price-negative';
                    const signal = mom > 3 ? 'Bullish' : mom < -3 ? 'Bearish' : 'Neutral';
                    const kp = r.kronos_prediction || {};
                    const trend = kp.trend || '—';
                    const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';
                    return '<tr>' +
                        '<td><strong>' + (r.ticker || '?') + '</strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></td>' +
                        '<td>' + (r.earnings_date || 'N/A') + '</td>' +
                        '<td>' + (r.current_price ? r.current_price.toFixed(2) : 'N/A') + '</td>' +
                        '<td>' + (r.market_cap ? this.formatMarketCap(r.market_cap) : 'N/A') + '</td>' +
                        '<td class="' + cls7 + '">' + (r.seven_day_return_pct !== null ? r.seven_day_return_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td class="' + cls + '">' + (r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td>' + (r.earnings_week_move_pct !== null ? r.earnings_week_move_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td>' + (r.prev_quarter_earnings_score !== null ? r.prev_quarter_earnings_score + '/9' : 'N/A') + '</td>' +
                        '<td class="' + trendCls + '">' + trend + '</td>' +
                        '<td><div style="display:flex;flex-direction:column;gap:0.3rem;">' + this.renderConsensusBadge(r.ticker, this.currentMarket) + (typeof this.renderTradingAgentsBadge === 'function' ? this.renderTradingAgentsBadge(r.ticker, this.currentMarket) : '') + '</div></td>' +
                        '<td><span class="signal-badge ' + (mom > 3 ? 'price-positive' : mom < -3 ? 'price-negative' : '') + '">' + signal + '</span></td>' +
                        '</tr>';
                }).join('');
            },

            sortResults(key) {
                if (this.sortKey === key) this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
                else { this.sortKey = key; this.sortDir = 'asc'; }
                this.renderResultsTable();
            },

            swingData: [],
            swingView: 'table',
            swingFilter: 'all',
            swingSortKey: 'ticker',
            swingSortDir: 'asc',

            setSwingView(view) {
                this.swingView = view;
                const tbl = document.getElementById('swingTableContainer');
                const crd = document.getElementById('swingWidgets');
                const btnTbl = document.getElementById('swingViewBtn-table');
                const btnCrd = document.getElementById('swingViewBtn-cards');

                if (view === 'table') {
                    if (tbl) tbl.style.display = 'block';
                    if (crd) crd.style.display = 'none';
                    if (btnTbl) { btnTbl.style.background = 'var(--accent)'; btnTbl.style.color = 'white'; }
                    if (btnCrd) { btnCrd.style.background = 'rgba(255,255,255,0.06)'; btnCrd.style.color = 'var(--muted)'; }
                } else {
                    if (tbl) tbl.style.display = 'none';
                    if (crd) crd.style.display = 'grid';
                    if (btnTbl) { btnTbl.style.background = 'rgba(255,255,255,0.06)'; btnTbl.style.color = 'var(--muted)'; }
                    if (btnCrd) { btnCrd.style.background = 'var(--accent)'; btnCrd.style.color = 'white'; }
                }
                this.renderSwing();
            },

            filterSwing(filter) {
                this.swingFilter = filter;
                const pills = ['all', 'buyzone', 'strongbuy', 'custom'];
                pills.forEach(p => {
                    const btn = document.getElementById('swingFilter-' + p);
                    if (!btn) return;
                    if (p === filter) {
                        btn.style.background = p === 'buyzone' ? 'rgba(16,185,129,0.35)' : 'var(--accent)';
                        btn.style.color = 'white';
                        btn.style.borderColor = p === 'buyzone' ? '#10b981' : 'transparent';
                    } else {
                        btn.style.background = p === 'buyzone' ? 'rgba(16,185,129,0.12)' : (p === 'strongbuy' ? 'rgba(16,185,129,0.1)' : (p === 'custom' ? 'rgba(59,130,246,0.15)' : 'rgba(255,255,255,0.06)'));
                        btn.style.color = p === 'buyzone' ? '#34d399' : (p === 'strongbuy' ? '#10b981' : (p === 'custom' ? '#60a5fa' : 'var(--muted)'));
                        btn.style.borderColor = p === 'buyzone' ? 'rgba(16,185,129,0.4)' : 'transparent';
                    }
                });
                this.renderSwing();
            },

            sortSwing(key) {
                if (this.swingSortKey === key) {
                    this.swingSortDir = this.swingSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.swingSortKey = key;
                    this.swingSortDir = 'asc';
                }
                this.renderSwing();
            },

            isSwingInBuyZone(r) {
                if (!r) return false;
                const cur = r.current_price;
                const supp = r.current_support;
                const res = r.next_resistance;
                const sig = r.swing_signal;

                // Never mark as Buy Zone if price is above resistance or broken below support
                if (cur != null && res != null && cur > res) return false;
                if (cur != null && supp != null && cur < supp * 0.97) return false;
                if (sig === 'Overbought' || sig === 'Sell Zone' || sig === 'Breakdown') return false;

                if (r.swing_zone === 'Buy Zone') return true;
                if (sig === 'Strong Buy' || sig === 'Buy') return true;
                if (cur != null && supp != null && res != null && res > supp) {
                    const channelPos = (cur - supp) / (res - supp);
                    if (channelPos >= 0 && channelPos <= 0.25) return true;
                }
                return false;
            },

            async loadSwing(e) {
                const marketEl = document.getElementById('swingMarket');
                const market = marketEl ? marketEl.value : 'ALL';
                const url = API_BASE + '/api/v1/dashboard/swing?limit=50' + (market ? '&market=' + encodeURIComponent(market) : '');
                const btn = (e && e.target) ? e.target : (typeof window !== 'undefined' && window.event ? window.event.target : null);
                if (btn && btn.tagName === 'BUTTON') { btn.disabled = true; btn.innerHTML = '<span class="loading-spinner"></span> Loading...'; }
                try {
                    const res = await fetch(url);
                    const data = await res.json();
                    this.swingData = Array.isArray(data) ? data : [];

                    // Update summary counts
                    const countAll = this.swingData.length;
                    const countBuyZone = this.swingData.filter(r => this.isSwingInBuyZone(r) || r.tier === 'HOT').length;
                    const countStrongBuy = this.swingData.filter(r => r.swing_signal === 'Strong Buy').length;
                    const countCustom = this.swingData.filter(r => (r.swing_range && r.swing_range.source === 'user') || r.source === 'user').length;

                    const elAll = document.getElementById('count-all'); if (elAll) elAll.textContent = countAll;
                    const elBz = document.getElementById('count-buyzone'); if (elBz) elBz.textContent = countBuyZone;
                    const elSb = document.getElementById('count-strongbuy'); if (elSb) elSb.textContent = countStrongBuy;
                    const elCust = document.getElementById('count-custom'); if (elCust) elCust.textContent = countCustom;

                    const pAll = document.getElementById('count-all-pill'); if (pAll) pAll.textContent = countAll;
                    const pBz = document.getElementById('count-buyzone-pill'); if (pBz) pBz.textContent = countBuyZone;
                    const pSb = document.getElementById('count-strongbuy-pill'); if (pSb) pSb.textContent = countStrongBuy;
                    const pCust = document.getElementById('count-custom-pill'); if (pCust) pCust.textContent = countCustom;

                    this.renderSwing();
                } catch (e) {
                    console.error('Error loading swing setups:', e);
                    const tbody = document.getElementById('swingTableBody');
                    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--red);">Error loading swing setups. Check server logs.</td></tr>';
                    const el = document.getElementById('swingWidgets');
                    if (el) el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0;color:var(--red)">Error loading swing setups</div>';
                } finally {
                    if (btn && btn.tagName === 'BUTTON') { btn.disabled = false; btn.textContent = '🔄 Refresh Setups'; }
                }
            },

            toggleSwingBuyZoneFilter() {
                if (this.swingFilter === 'buyzone') {
                    this.clearSwingFilter();
                } else {
                    this.filterSwing('buyzone');
                }
            },

            clearSwingFilter() {
                this.filterSwing('all');
            },

            filterSwing(filterType) {
                this.swingFilter = filterType || 'all';

                // Update filter pills UI
                ['all', 'buyzone', 'strongbuy', 'custom'].forEach(t => {
                    const btn = document.getElementById(`swingFilter-${t}`);
                    if (btn) {
                        if (t === this.swingFilter) {
                            btn.className = 'btn btn-primary btn-xs';
                            btn.style.fontWeight = '700';
                        } else {
                            btn.className = 'btn btn-xs';
                            btn.style.fontWeight = '500';
                        }
                    }
                });

                // Update KPI Cards UI (Glow & Indicators)
                const cardBz = document.getElementById('swingCardBuyZone');
                const badgeBz = document.getElementById('swingFilterIndicatorBz');
                const subBz = document.getElementById('swingStatBzSub');
                const noticeEl = document.getElementById('swingFilterNotice');

                if (this.swingFilter === 'buyzone') {
                    if (cardBz) {
                        cardBz.style.outline = '2px solid #10b981';
                        cardBz.style.boxShadow = '0 0 20px rgba(16,185,129,0.45)';
                    }
                    if (badgeBz) badgeBz.style.display = 'inline-block';
                    if (subBz) subBz.textContent = 'Filtered 🔍';
                    if (noticeEl) {
                        const count = (this.swingData || []).filter(r => this.isSwingInBuyZone(r) || r.tier === 'HOT').length;
                        noticeEl.style.display = 'inline-flex';
                        noticeEl.innerHTML = `🟢 Filtering: In Buy Zone (${count} setups) <button type="button" onclick="app.clearSwingFilter()" style="background:none;border:none;color:#6ee7b7;cursor:pointer;font-weight:800;margin-left:0.35rem;">✕ Show All</button>`;
                    }
                } else {
                    if (cardBz) {
                        cardBz.style.outline = 'none';
                        cardBz.style.boxShadow = 'none';
                    }
                    if (badgeBz) badgeBz.style.display = 'none';
                    if (subBz) subBz.textContent = 'Support Floor';

                    if (this.swingFilter === 'strongbuy') {
                        if (noticeEl) {
                            const count = (this.swingData || []).filter(r => r.swing_signal === 'Strong Buy').length;
                            noticeEl.style.display = 'inline-flex';
                            noticeEl.innerHTML = `⭐ Filtering: Strong Buy Grade A+ (${count} stocks) <button type="button" onclick="app.clearSwingFilter()" style="background:none;border:none;color:#38bdf8;cursor:pointer;font-weight:800;margin-left:0.35rem;">✕ Show All</button>`;
                        }
                    } else if (this.swingFilter === 'custom') {
                        if (noticeEl) {
                            const count = (this.swingData || []).filter(r => (r.swing_range && r.swing_range.source === 'user') || r.source === 'user').length;
                            noticeEl.style.display = 'inline-flex';
                            noticeEl.innerHTML = `🔒 Filtering: Custom User Ranges (${count} stocks) <button type="button" onclick="app.clearSwingFilter()" style="background:none;border:none;color:#fbbf24;cursor:pointer;font-weight:800;margin-left:0.35rem;">✕ Show All</button>`;
                        }
                    } else {
                        if (noticeEl) noticeEl.style.display = 'none';
                    }
                }

                this.renderSwing();
            },

            renderSwing() {
                const marketEl = document.getElementById('swingMarket');
                const currentMarket = marketEl ? marketEl.value : 'ALL';
                const tbody = document.getElementById('swingTableBody');
                const widgetEl = document.getElementById('swingWidgets');

                if (!this.swingData || !this.swingData.length) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--muted)">No swing setups found. Try a different market or click Refresh.</td></tr>';
                    if (widgetEl) widgetEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No swing setups found.</div>';
                    return;
                }

                // Filter
                let list = [...this.swingData];
                if (this.swingFilter === 'buyzone') {
                    list = list.filter(r => this.isSwingInBuyZone(r) || r.tier === 'HOT');
                } else if (this.swingFilter === 'strongbuy') {
                    list = list.filter(r => r.swing_signal === 'Strong Buy');
                } else if (this.swingFilter === 'custom') {
                    list = list.filter(r => (r.swing_range && r.swing_range.source === 'user') || r.source === 'user');
                }

                // Text search filter
                const searchInp = document.getElementById('swingSearchInput');
                if (searchInp && searchInp.value.trim()) {
                    const q = searchInp.value.trim().toUpperCase();
                    list = list.filter(r => (r.ticker || '').toUpperCase().includes(q) || (r.swing_signal || '').toUpperCase().includes(q) || (r.industry || '').toUpperCase().includes(q));
                }

                // Sort
                list.sort((a, b) => {
                    let va = a[this.swingSortKey], vb = b[this.swingSortKey];
                    if (this.swingSortKey === 'ticker') {
                        va = (a.ticker || '').toUpperCase();
                        vb = (b.ticker || '').toUpperCase();
                    } else if (this.swingSortKey === 'current_price') {
                        va = a.current_price != null ? a.current_price : -Infinity;
                        vb = b.current_price != null ? b.current_price : -Infinity;
                    } else if (this.swingSortKey === 'current_support') {
                        va = a.current_support != null ? a.current_support : -Infinity;
                        vb = b.current_support != null ? b.current_support : -Infinity;
                    } else if (this.swingSortKey === 'thirty_day_return_pct') {
                        va = a.thirty_day_return_pct != null ? a.thirty_day_return_pct : -Infinity;
                        vb = b.thirty_day_return_pct != null ? b.thirty_day_return_pct : -Infinity;
                    } else if (this.swingSortKey === 'prev_quarter_earnings_score') {
                        va = a.prev_quarter_earnings_score != null ? a.prev_quarter_earnings_score : -Infinity;
                        vb = b.prev_quarter_earnings_score != null ? b.prev_quarter_earnings_score : -Infinity;
                    } else if (this.swingSortKey === 'consensus_strength') {
                        const pA = this.consensusMap[(a.ticker || '').toUpperCase()] || a.consensus || {};
                        const pB = this.consensusMap[(b.ticker || '').toUpperCase()] || b.consensus || {};
                        va = pA.consensus_strength != null ? pA.consensus_strength : -Infinity;
                        vb = pB.consensus_strength != null ? pB.consensus_strength : -Infinity;
                    } else {
                        va = va === null || va === undefined ? -Infinity : va;
                        vb = vb === null || vb === undefined ? -Infinity : vb;
                    }
                    if (va < vb) return this.swingSortDir === 'asc' ? -1 : 1;
                    if (va > vb) return this.swingSortDir === 'asc' ? 1 : -1;
                    return 0;
                });

                if (!list.length) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--muted)">No stocks match the selected filter.</td></tr>';
                    if (widgetEl) widgetEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No stocks match the selected filter.</div>';
                    return;
                }

                // Render Streamlined 7-Column Rows
                if (tbody) {
                    tbody.innerHTML = list.map(r => {
                        const isBz = this.isSwingInBuyZone(r) || r.tier === 'HOT';
                        const curPrice = r.current_price;
                        const curPriceStr = curPrice !== null && curPrice !== undefined ? ('₹' + Number(curPrice).toFixed(2)) : '—';
                        const supp = r.current_support;
                        const resis = r.next_resistance;
                        const suppStr = supp !== null && supp !== undefined ? ('₹' + Number(supp).toFixed(2)) : '—';
                        const resisStr = resis !== null && resis !== undefined ? ('₹' + Number(resis).toFixed(2)) : '—';

                        // Distance to support & channel position %
                        let distToSupp = '—';
                        let distCls = 'timestamp';
                        let posPct = r.channel_position_pct != null ? r.channel_position_pct : 50;
                        if (curPrice != null && supp != null && supp > 0) {
                            const diffPct = ((curPrice - supp) / supp) * 100;
                            if (Math.abs(diffPct) < 0.5) {
                                distToSupp = '🎯 At Support';
                                distCls = 'price-positive';
                            } else if (diffPct > 0) {
                                distToSupp = '+' + diffPct.toFixed(1) + '% to Floor';
                                distCls = isBz ? 'price-positive' : 'timestamp';
                            } else {
                                distToSupp = diffPct.toFixed(1) + '% Below Floor';
                                distCls = 'price-negative';
                            }
                            if (resis != null && resis > supp) {
                                posPct = Math.max(0, Math.min(100, ((curPrice - supp) / (resis - supp)) * 100));
                            }
                        }
                        const posColor = posPct <= 25 ? '#10b981' : (posPct >= 80 ? '#f87171' : '#38bdf8');

                        // Swing Range bounds
                        const sr = r.swing_range || {};
                        const hasSr = sr.lower_bound != null && sr.upper_bound != null;
                        const srLower = hasSr ? Number(sr.lower_bound).toFixed(2) : (supp ? Number(supp).toFixed(2) : '—');
                        const srUpper = hasSr ? Number(sr.upper_bound).toFixed(2) : (resis ? Number(resis).toFixed(2) : '—');
                        const isUser = (sr.source === 'user') || (r.source === 'user');
                        const srSource = isUser ? 'Custom 🔒' : 'Auto';
                        const srSourceCls = isUser ? 'background:rgba(245,158,11,0.2);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);' : 'background:rgba(148,163,184,0.15);color:#94a3b8;';
                        const spreadStr = r.spread_pct ? `${r.spread_pct}% spread` : (hasSr && sr.lower_bound > 0 ? `${(((sr.upper_bound - sr.lower_bound)/sr.lower_bound)*100).toFixed(1)}% spread` : '');

                        // Tier Pill
                        const tier = r.tier || (isBz ? 'HOT' : 'WARM');
                        const tierBadge = tier === 'HOT'
                            ? '<span class="signal-badge" style="background:rgba(249,115,22,0.2);color:#fdba74;border:1px solid rgba(249,115,22,0.4);font-size:0.65rem;font-weight:800;padding:0.1rem 0.35rem;">🔥 HOT</span>'
                            : '<span class="signal-badge" style="background:rgba(148,163,184,0.15);color:#cbd5e1;font-size:0.65rem;padding:0.1rem 0.35rem;">🟡 WARM</span>';

                        // Signal Badge
                        let signalBadge = '';
                        if (r.swing_signal === 'Strong Buy') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid #38bdf8;padding:0.15rem 0.5rem;font-size:0.72rem;font-weight:800;">⭐ STRONG BUY</span>';
                        } else if (isBz || r.swing_signal === 'Buy Zone') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#34d399;border:1px solid #10b981;padding:0.15rem 0.5rem;font-size:0.72rem;font-weight:700;">🟢 BUY ZONE</span>';
                        } else if (r.swing_signal === 'Overbought' || r.swing_signal === 'Sell Zone') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(251,146,60,0.2);color:#fb923c;border:1px solid rgba(251,146,60,0.4);padding:0.15rem 0.5rem;font-size:0.72rem;font-weight:600;">🟠 SELL ZONE</span>';
                        } else if (r.swing_signal === 'Breakdown') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(239,68,68,0.25);color:#ef4444;border:1px solid #ef4444;padding:0.15rem 0.5rem;font-size:0.72rem;font-weight:700;">🔴 BREAKDOWN</span>';
                        } else {
                            signalBadge = '<span class="signal-badge" style="background:rgba(148,163,184,0.15);color:#94a3b8;padding:0.15rem 0.5rem;font-size:0.72rem;">Neutral</span>';
                        }

                        // 30D Return
                        const mom = r.thirty_day_return_pct;
                        const momCls = mom !== null && mom !== undefined ? (mom >= 0 ? 'price-positive' : 'price-negative') : '';
                        const momStr = mom !== null && mom !== undefined ? ((mom >= 0 ? '+' : '') + Number(mom).toFixed(1) + '%') : '—';

                        // AI Intelligence Cell (Consolidated 4-Model + Kronos + News)
                        const kp = r.kronos_prediction || {};
                        const kpTrend = kp.trend || '—';
                        const kpRet = (kp.return_pct != null) ? `${kp.return_pct >= 0 ? '+' : ''}${kp.return_pct.toFixed(1)}%` : '';
                        const pConsensus = this.consensusMap[(r.ticker || '').toUpperCase()] || r.consensus || {};
                        const cDir = pConsensus.consensus_direction || 'NEUTRAL';
                        const isCBull = cDir.includes('BUY') || cDir.includes('BULL');
                        const isCBear = cDir.includes('SELL') || cDir.includes('BEAR');
                        const cColor = isCBull ? '#34d399' : isCBear ? '#f87171' : '#fbbf24';

                        const aiColHtml = `
                            <div onclick="event.stopPropagation(); app.openSwingAiModal('${(r.ticker || '').replace(/'/g, "\\'")}')" style="cursor:pointer;display:flex;flex-direction:column;gap:0.15rem;" title="Click to view full AI Thesis & Intelligence">
                                <div style="display:flex;align-items:center;gap:0.35rem;">
                                    <span class="signal-badge" style="background:rgba(255,255,255,0.06);color:${cColor};font-size:0.68rem;font-weight:700;padding:0.1rem 0.4rem;border:1px solid rgba(255,255,255,0.1);">
                                        🤖 ${cDir}
                                    </span>
                                    ${kpRet ? `<span style="font-size:0.68rem;color:#38bdf8;font-family:var(--font-mono);font-weight:600;">🔮 ${kpRet}</span>` : ''}
                                </div>
                                <div style="font-size:0.65rem;color:#94a3b8;">
                                    Kronos: ${kpTrend} · <span style="color:#60a5fa;text-decoration:underline;">Thesis ↗</span>
                                </div>
                            </div>
                        `;

                        // Row styling
                        const rowStyle = isBz ? 'background:rgba(16,185,129,0.06);border-left:3px solid #10b981;' : '';
                        const hoverBg = isBz ? 'rgba(16,185,129,0.12)' : 'rgba(255,255,255,0.04)';
                        const origBg = isBz ? 'rgba(16,185,129,0.06)' : '';

                        return `
                            <tr style="${rowStyle}cursor:pointer;" data-ticker="${r.ticker || ''}" onmouseenter="this.style.background='${hoverBg}'" onmouseleave="this.style.background='${origBg}'" onclick="app.openSwingRangeModal('${currentMarket.replace(/'/g, "\\'")}', '${(r.ticker || '').replace(/'/g, "\\'")}')" title="Click to open Support/Resistance Channel Editor">
                                <!-- Col 1: Ticker -->
                                <td style="padding:0.55rem 0.65rem;">
                                    <div style="display:flex;align-items:center;gap:0.3rem;">
                                        <strong style="color:#ffffff;font-size:0.92rem;font-family:var(--font-heading);">${r.ticker || '?'}</strong>
                                        <button type="button" class="btn-ticker-refresh" onclick="event.stopPropagation(); app.refreshSingleStockPrice('${r.ticker}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.75rem;padding:0 0.15rem;opacity:0.75;line-height:1;transition:all 0.15s;" onmouseenter="this.style.opacity='1';this.style.color='#7dd3fc';" onmouseleave="this.style.opacity='0.75';this.style.color='#38bdf8';" title="Refresh live price & technical metrics for ${r.ticker}">↻</button>
                                        <a href="/stock/${encodeURIComponent(r.ticker)}" target="_blank" onclick="event.stopPropagation();" style="color:#38bdf8;font-size:0.75rem;text-decoration:none;" title="Open profile">↗</a>
                                    </div>
                                    <div style="font-size:0.65rem;color:#64748b;margin-top:0.1rem;">${r.industry || 'NSE Equity'}</div>
                                </td>

                                <!-- Col 2: Price & 30D Move -->
                                <td class="cell-current-price" style="padding:0.55rem 0.65rem;">
                                    <div style="font-weight:800;font-size:0.92rem;${isBz ? 'color:#34d399;' : 'color:#f8fafc;'}font-family:var(--font-mono);">${curPriceStr}</div>
                                    <div class="${momCls} cell-thirty-day-return" style="font-size:0.68rem;font-weight:600;margin-top:0.1rem;">30D: ${momStr}</div>
                                </td>

                                <!-- Col 3: Tier & Signal -->
                                <td style="padding:0.55rem 0.65rem;">
                                    <div style="display:flex;align-items:center;gap:0.35rem;margin-bottom:0.2rem;">
                                        ${tierBadge}
                                    </div>
                                    <div>${signalBadge}</div>
                                </td>

                                <!-- Col 4: Consolidated Trading Channel (S/R) -->
                                <td class="cell-sr-structure" style="padding:0.55rem 0.65rem;">
                                    <div style="display:flex;justify-content:space-between;align-items:center;">
                                        <span style="font-weight:700;color:#f8fafc;font-family:var(--font-mono);">₹${srLower} – ₹${srUpper}</span>
                                        <span class="signal-badge" style="${srSourceCls}font-size:0.60rem;padding:0.05rem 0.3rem;">${srSource}</span>
                                    </div>
                                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.15rem;">
                                        <span class="${distCls}" style="font-size:0.68rem;font-weight:600;">${distToSupp}</span>
                                        <span style="font-size:0.65rem;color:#64748b;">${spreadStr}</span>
                                    </div>
                                    <div style="width:100%;height:3px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden;margin-top:0.25rem;">
                                        <div style="width:${posPct}%;height:100%;background:${posColor};border-radius:2px;"></div>
                                    </div>
                                </td>

                                <!-- Col 5: Earnings & Quality -->
                                <td style="padding:0.55rem 0.65rem;">
                                    <div style="font-weight:600;color:#f1f5f9;font-size:0.75rem;">${r.earnings_date || '—'}</div>
                                    <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.1rem;">
                                        Quality: <strong style="color:#fbbf24;">${r.prev_quarter_earnings_score != null ? r.prev_quarter_earnings_score + '/9' : '—'}</strong>
                                    </div>
                                </td>

                                <!-- Col 6: AI Intelligence & Thesis -->
                                <td style="padding:0.55rem 0.65rem;">
                                    ${aiColHtml}
                                </td>

                                <!-- Col 7: Actions -->
                                <td style="padding:0.55rem 0.65rem;text-align:right;">
                                    <div style="display:flex;justify-content:flex-end;gap:0.3rem;align-items:center;">
                                        <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingRangeModal('${currentMarket.replace(/'/g, "\\'")}', '${(r.ticker || '').replace(/'/g, "\\'")}')" style="padding:0.2rem 0.45rem;font-size:0.70rem;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);" title="Edit Support & Resistance bounds">✎ Range</button>
                                        <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingAiModal('${(r.ticker || '').replace(/'/g, "\\'")}')" style="padding:0.2rem 0.45rem;font-size:0.70rem;background:rgba(59,130,246,0.2);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);" title="View unified AI Thesis">🧠 AI</button>
                                        <a href="/stock/${encodeURIComponent(r.ticker)}" target="_blank" onclick="event.stopPropagation();" class="btn btn-sm" style="padding:0.2rem 0.45rem;font-size:0.70rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);text-decoration:none;">📊 Chart</a>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join('');
                }

                // Render Cards (if user switches to card view)
                if (widgetEl) {
                    widgetEl.innerHTML = list.map(r => {
                        const isBz = this.isSwingInBuyZone(r);
                        const mom = r.thirty_day_return_pct !== null ? r.thirty_day_return_pct : 0;
                        const cls = mom >= 0 ? 'price-positive' : 'price-negative';
                        const badgeStyle = isBz ? 'background:rgba(16,185,129,0.25);color:#34d399;border:1px solid #10b981;' :
                            r.swing_signal === 'Overbought' ? 'background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);' :
                            r.swing_signal === 'Sell Zone' ? 'background:rgba(251,146,60,0.2);color:#fb923c;border:1px solid rgba(251,146,60,0.4);' :
                            r.swing_signal === 'Breakdown' ? 'background:rgba(239,68,68,0.25);color:#ef4444;border:1px solid #ef4444;' :
                            r.swing_signal === 'Buy' ? 'background:rgba(16,185,129,0.15);color:#6ee7b7;' :
                            r.swing_signal === 'Cautious' ? 'background:rgba(239,68,68,0.2);color:#ef4444;' :
                            'background:rgba(148,163,184,0.2);color:#94a3b8;';
                        const badgeText = isBz ? '🟢 BUY ZONE' : (r.swing_signal === 'Overbought' ? '⚠️ Above Resistance' : (r.swing_signal === 'Sell Zone' ? '🟠 Sell Zone' : (r.swing_signal === 'Breakdown' ? '🔴 Below Support' : r.swing_signal)));
                        const earningsDate = r.earnings_date || 'N/A';
                        const kp = r.kronos_prediction || {};
                        const hasKp = kp && kp.trend && kp.trend !== '—' && kp.trend !== 'N/A';
                        const trend = kp.trend || 'N/A';
                        const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';

                        const ai = r.ai_synthesis || {};
                        const hasAi = ai && ai.ai_signal;

                        const sr = r.swing_range || {};
                        const hasSr = sr.lower_bound != null && sr.upper_bound != null;
                        const srLower = hasSr ? Number(sr.lower_bound).toFixed(2) : (r.current_support ? Number(r.current_support).toFixed(2) : '—');
                        const srUpper = hasSr ? Number(sr.upper_bound).toFixed(2) : (r.next_resistance ? Number(r.next_resistance).toFixed(2) : '—');
                        const isUser = sr.source === 'user';
                        const srSource = isUser ? 'Custom' : 'Auto';
                        const srSourceCls = isUser ? 'background:rgba(59,130,246,0.25);color:#60a5fa;' : 'background:rgba(148,163,184,0.15);color:#94a3b8;';
                        const srCycles = (sr.cycles != null && sr.cycles > 0) ? (sr.cycles + ' cyc' + (sr.avg_cycle_days ? ' · ~' + Math.round(sr.avg_cycle_days) + 'd' : '')) : '';
                        const curPriceStr = r.current_price !== null && r.current_price !== undefined ? ('₹' + Number(r.current_price).toFixed(2)) : 'N/A';

                        const cardBorder = isBz ? 'border-color:#10b981;background:rgba(16,185,129,0.05);' : '';

                        return '<div class="widget-card" onclick="app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" style="' + cardBorder + 'cursor:pointer;transition:transform 0.15s ease, border-color 0.15s ease;" onmouseenter="this.style.borderColor=\'rgba(59,130,246,0.8)\'" onmouseleave="this.style.borderColor=\'' + (isBz ? '#10b981' : '') + '\'" title="Click anywhere to view 3-month range history & customize swing range">' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                            '<h4>' + (r.ticker || '?') + '</h4>' +
                            '<span class="signal-badge" style="' + badgeStyle + '">' + badgeText + '</span></div>' +
                            '<div style="display:flex;justify-content:space-between;align-items:baseline;margin:0.25rem 0 0.45rem 0;">' +
                            '<span style="font-size:0.8rem;color:var(--muted);">Current Price</span>' +
                            '<strong style="font-size:1.1rem;' + (isBz ? 'color:#34d399;' : 'color:var(--light);') + '">' + curPriceStr + '</strong>' +
                            '</div>' +
                            '<div class="metric" style="margin-bottom:0.4rem"><span>Next Earnings</span><strong>' + earningsDate + '</strong></div>' +
                            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">' +
                            '<div class="metric"><span>Support (Buy Zone)</span><strong style="' + (isBz ? 'color:#34d399;' : '') + '">' + (r.current_support ? '₹' + Number(r.current_support).toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>Resistance (Sell Zone)</span><strong>' + (r.next_resistance ? '₹' + Number(r.next_resistance).toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>30D Return</span><strong class="' + cls + '">' + (r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>Quality (LQ)</span><strong>' + (r.prev_quarter_earnings_score !== null ? r.prev_quarter_earnings_score + '/9' : 'N/A') + '</strong></div>' +
                            '</div>' +
                            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.45rem 0.6rem;margin-top:0.5rem;">' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">' +
                            '<span style="font-size:0.72rem;color:var(--muted);font-weight:600;">SWING RANGE</span>' +
                            '<span class="signal-badge" style="' + srSourceCls + 'font-size:0.68rem;padding:0.08rem 0.35rem;">' + srSource + '</span>' +
                            '</div>' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                            '<div><strong style="font-size:0.92rem;">₹' + srLower + ' – ₹' + srUpper + '</strong>' +
                            (srCycles ? '<span class="timestamp" style="display:block;font-size:0.72rem;">' + srCycles + '</span>' : '') +
                            '</div>' +
                            '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" style="padding:0.2rem 0.5rem;font-size:0.75rem;">✎ Range</button>' +
                            '</div>' +
                            '</div>' +
                            (hasAi ? ('<div class="metric" style="margin-top:0.4rem;cursor:pointer;" onclick="event.stopPropagation(); app.openAiDetails(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\', event)"><span>AI Synthesis</span><strong style="color:#60a5fa;">' + ai.ai_signal + ' (' + (ai.sentiment_score >= 0 ? '+' : '') + Number(ai.sentiment_score).toFixed(2) + ') 🔍</strong></div>') : '') +
                            (hasKp ? ('<div class="metric" style="margin-top:0.2rem"><span>Kronos 14D Return</span><strong class="' + trendCls + '">' + (kp.return_pct != null ? kp.return_pct.toFixed(2) + '%' : '—') + ' (' + trend + ')</strong></div>') : '') +
                            (kp.explanation ? '<p class="timestamp" style="margin-top:0.5rem;font-size:0.75rem;">' + kp.explanation + '</p>' : '') +
                            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">' +
                            '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.35rem 0.4rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);">' + (hasKp ? '🔄 Kronos' : '⚡ Kronos AI') + '</button>' +
                            '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openAiDetails(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\', event)" style="padding:0.35rem 0.4rem;font-size:0.72rem;background:rgba(59,130,246,0.22);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);">' + (hasAi ? '🔍 Reasons & News' : '🧠 AI Thesis') + '</button>' +
                            '</div>';
                    }).join('');
                }
            },

            async runPredictionForTickerSingle(ticker, eventOrBtn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;

                let btn = null;
                if (eventOrBtn && eventOrBtn.tagName) {
                    btn = eventOrBtn;
                } else if (window.event && window.event.target) {
                    btn = window.event.target.closest('button');
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> 🔮...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: [ticker], lookback: 120, pred_len: 14 })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || ('HTTP ' + res.status));
                    }
                    const data = await res.json();
                    const list = Array.isArray(data) ? data : (data.predictions || (data.prediction ? [data.prediction] : []));
                    const pred = list[0];

                    if (pred && (pred.trend || pred.return_pct != null)) {
                        const ret = Number(pred.return_pct || 0);
                        const isBull = ret >= 0.5;
                        const isBear = ret <= -0.5;
                        const emoji = isBull ? '🟢' : (isBear ? '🔴' : '🟡');
                        const color = isBull ? '#34d399' : (isBear ? '#f87171' : '#fbbf24');

                        if (btn) {
                            btn.style.borderColor = color;
                            btn.style.color = color;
                            btn.innerHTML = emoji + ' ' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%';
                            btn.title = (pred.trend || 'Trend') + ': ' + (pred.explanation || '');
                        }

                        // Also update row in swingData if present
                        const sItem = (this.swingData || []).find(x => x.ticker === ticker);
                        if (sItem) {
                            sItem.kronos_prediction = pred;
                        }

                        // Open OHLCV Benchmark modal with the generated forecast
                        this.showOhlcvBenchmarkModal(ticker, pred.run_at);
                    } else {
                        alert('Kronos prediction for ' + ticker + ' completed with no signals.');
                        if (btn) btn.innerHTML = origHtml;
                    }
                } catch (err) {
                    console.error('Error running single Kronos prediction for ' + ticker + ':', err);
                    alert('Error running Kronos prediction for ' + ticker + ': ' + (err.message || err));
                    if (btn) btn.innerHTML = origHtml;
                } finally {
                    if (btn) btn.disabled = false;
                }
            },

            async runSwingKronos(ticker, btn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Predicting...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/predict/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticker: ticker, engine: 'kronos', days: 14, lookback: 120, pred_len: 14 })
                    });
                    const data = await res.json();
                    if (data.success && data.prediction) {
                        const item = (this.swingData || []).find(x => x.ticker === ticker);
                        if (item) {
                            item.kronos_prediction = data.prediction;
                        }
                        this.renderSwing();

                        // If modal is open for this ticker, update its Kronos section
                        const modalTicker = document.getElementById('srModalTicker')?.value;
                        if (modalTicker === ticker) {
                            this._renderModalKronos(data.prediction);
                        }
                    } else {
                        alert('Kronos prediction failed: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error running Kronos prediction for ' + ticker + ':', e);
                    alert('Network error running Kronos prediction');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async runRowPrediction(ticker, engine, btn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;
                engine = (engine || 'kronos').toLowerCase();

                if (!btn && window.event) {
                    btn = window.event.target ? window.event.target.closest('button') : null;
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span>...';
                }

                try {
                    const apiBase = (typeof API_BASE !== 'undefined') ? API_BASE : '';
                    const res = await fetch(apiBase + '/api/v1/dashboard/predict/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticker: ticker, engine: engine, lookback: 120, pred_len: 14 })
                    });

                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || err.error || ('HTTP ' + res.status));
                    }

                    const data = await res.json();
                    if (!data || !data.success) {
                        throw new Error(data.error || 'Prediction failed');
                    }

                    const pred = data.prediction || {};
                    if (engine === 'kronos') {
                        const ret = Number(pred.return_pct || 0);
                        const trend = pred.trend || 'Neutral';
                        const cls = trend === 'Bullish' ? 'pred-bullish' : (trend === 'Bearish' ? 'pred-bearish' : 'pred-neutral');
                        const sign = ret >= 0 ? '+' : '';
                        if (btn) {
                            btn.outerHTML = '<span class="' + cls + '">' + sign + ret.toFixed(1) + '%</span>';
                        }
                    } else if (engine === 'gbm') {
                        const direction = pred.direction || '?';
                        const conf = pred.confidence;
                        const confStr = conf != null ? Math.round(conf * 100) + '%' : '—';
                        const cls = direction === 'UP' ? 'pred-bullish' : 'pred-bearish';
                        if (btn) {
                            btn.outerHTML = '<span class="' + cls + '">' + direction + ' ' + confStr + '</span>';
                        }
                    }
                } catch (e) {
                    console.error('Error running ' + engine + ' row prediction:', e);
                    if (btn) {
                        btn.disabled = false;
                        btn.style.borderColor = '#f87171';
                        btn.style.color = '#f87171';
                        btn.title = 'Error: ' + (e.message || e);
                        btn.innerHTML = '⚠️ Error';
                    }
                }
            },

            async runModalKronos() {
                const ticker = document.getElementById('srModalTicker')?.value;
                const btn = document.getElementById('srModalKronosRunBtn');
                if (!ticker) return;
                await this.runSwingKronos(ticker, btn);
            },

            _renderModalKronos(kp) {
                const badge = document.getElementById('srModalKronosBadge');
                const content = document.getElementById('srModalKronosContent');
                if (!badge || !content) return;

                if (kp && (kp.trend || kp.return_pct != null)) {
                    const trend = kp.trend || 'Neutral';
                    const isBull = trend === 'Bullish';
                    const isBear = trend === 'Bearish';
                    const ret = kp.return_pct != null ? Number(kp.return_pct).toFixed(2) : '—';
                    const retCls = isBull ? 'price-positive' : isBear ? 'price-negative' : '';

                    badge.style.display = 'inline-block';
                    badge.textContent = trend + ' (' + (ret >= 0 ? '+' : '') + ret + '%)';
                    badge.style.background = isBull ? 'rgba(16,185,129,0.25)' : isBear ? 'rgba(239,68,68,0.25)' : 'rgba(251,191,36,0.25)';
                    badge.style.color = isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24';

                    content.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.4rem;margin:0.5rem 0;">' +
                        '<div class="metric"><span>14D Forecast Return</span><strong class="' + retCls + '">' + (ret >= 0 ? '+' : '') + ret + '%</strong></div>' +
                        '<div class="metric"><span>Kronos Support</span><strong>₹' + (kp.support ? Number(kp.support).toFixed(2) : '—') + '</strong></div>' +
                        '<div class="metric"><span>Kronos Resistance</span><strong>₹' + (kp.resistance ? Number(kp.resistance).toFixed(2) : '—') + '</strong></div>' +
                        '<div class="metric"><span>Target Price</span><strong>₹' + (kp.target_price ? Number(kp.target_price).toFixed(2) : (kp.current_price && kp.return_pct ? (kp.current_price * (1 + kp.return_pct/100)).toFixed(2) : '—')) + '</strong></div>' +
                        '</div>' +
                        (kp.explanation ? '<p class="timestamp" style="margin:0.25rem 0 0 0;font-size:0.78rem;">' + kp.explanation + '</p>' : '');
                } else {
                    badge.style.display = 'none';
                    content.innerHTML = '<p class="timestamp" style="margin:0;font-size:0.8rem;">No forecast generated yet. Click <strong>"⚡ Run Kronos AI"</strong> to compute 14-day predictions on demand.</p>';
                }
            },

            async runSingleAiForecast(ticker, btn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Synthesizing...';
                }

                try {
                    const item = (this.swingData || []).find(x => x.ticker === ticker) || {};
                    const res = await fetch(API_BASE + '/api/v1/dashboard/ai-forecast/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            ticker: ticker,
                            swing_support: item.current_support || null,
                            swing_resistance: item.next_resistance || null,
                        })
                    });
                    const data = await res.json();
                    if (data.success && data.prediction) {
                        const target = (this.swingData || []).find(x => x.ticker === ticker);
                        if (target) {
                            target.ai_synthesis = data.prediction;
                        }
                        this.renderSwing();

                        // If modal is open for this ticker, update its AI section
                        const modalTicker = document.getElementById('srModalTicker')?.value;
                        if (modalTicker === ticker) {
                            this._renderModalAi(data.prediction, ticker);
                        }
                    } else {
                        alert('AI News Synthesis failed: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error running AI News synthesis for ' + ticker + ':', e);
                    alert('Network error running AI News synthesis');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async runModalAiForecast() {
                const ticker = document.getElementById('srModalTicker')?.value;
                const btn = document.getElementById('srModalAiRunBtn');
                if (!ticker) return;
                await this.runSingleAiForecast(ticker, btn);
            },

            async _renderModalAi(ai, ticker) {
                const badge = document.getElementById('srModalAiSignalBadge');
                const content = document.getElementById('srModalAiContent');
                if (!badge || !content) return;

                if (!ai || !ai.ai_signal) {
                    badge.style.display = 'none';
                    content.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin:0.25rem 0;">' +
                        '<p class="timestamp" style="margin:0;font-size:0.8rem;">Click <strong>"⚡ Run AI Synthesis"</strong> to analyze real-time news headlines, volume surge, and price action.</p>' +
                        '<button type="button" class="btn btn-sm" onclick="app.runModalAiForecast()" style="font-size:0.75rem;background:rgba(59,130,246,0.25);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);">⚡ Run Now</button>' +
                        '</div>';
                    
                    // Also try to load raw news preview in background if available
                    if (ticker) {
                        try {
                            const nRes = await fetch(API_BASE + '/api/v1/dashboard/ai-forecast/news/' + encodeURIComponent(ticker) + '?limit=4');
                            const nData = await nRes.json();
                            if (nData.articles && nData.articles.length) {
                                content.innerHTML += '<div style="margin-top:0.6rem;border-top:1px dashed rgba(255,255,255,0.08);padding-top:0.5rem;">' +
                                    '<h5 style="margin:0 0 0.35rem 0;font-size:0.78rem;color:var(--muted);">📰 Live Headlines Feed (' + nData.articles.length + ' articles)</h5>' +
                                    '<div style="display:flex;flex-direction:column;gap:0.35rem;">' +
                                    nData.articles.map(a =>
                                        '<div style="font-size:0.75rem;display:flex;justify-content:space-between;align-items:baseline;background:rgba(255,255,255,0.02);padding:0.25rem 0.4rem;border-radius:0.3rem;">' +
                                        '<a href="' + (a.link || '#') + '" target="_blank" rel="noopener noreferrer" style="color:#93c5fd;text-decoration:none;flex:1;margin-right:0.5rem;">' + (a.title || 'Headline') + '</a>' +
                                        '<span class="timestamp" style="font-size:0.68rem;white-space:nowrap;">' + (a.publisher || '') + '</span>' +
                                        '</div>'
                                    ).join('') +
                                    '</div></div>';
                            }
                        } catch (e) {}
                    }
                    return;
                }

                const sig = ai.ai_signal || 'Neutral';
                const isBull = sig.includes('Bullish');
                const isBear = sig.includes('Bearish');
                const score = ai.sentiment_score != null ? Number(ai.sentiment_score).toFixed(2) : '0.00';
                const scoreStr = (ai.sentiment_score >= 0 ? '+' : '') + score;
                const conf = ai.confidence ? Math.round(ai.confidence * 100) + '%' : '75%';

                badge.style.display = 'inline-block';
                badge.textContent = sig + ' (' + scoreStr + ' · ' + conf + ' conf)';
                badge.style.background = isBull ? 'rgba(16,185,129,0.25)' : isBear ? 'rgba(239,68,68,0.25)' : 'rgba(251,191,36,0.25)';
                badge.style.color = isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24';

                const catalystsHtml = (ai.catalysts && ai.catalysts.length)
                    ? ('<div style="background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);border-radius:0.4rem;padding:0.5rem;margin-top:0.4rem;">' +
                       '<strong style="color:#34d399;font-size:0.8rem;display:flex;align-items:center;gap:0.3rem;">🚀 Positive Catalysts & Reasons:</strong>' +
                       '<ul style="margin:0.25rem 0 0 1.1rem;padding:0;font-size:0.75rem;color:var(--light);line-height:1.45;">' +
                       ai.catalysts.map(c => '<li style="margin-bottom:0.2rem;">' + c + '</li>').join('') + '</ul></div>')
                    : '';

                const risksHtml = (ai.risk_factors && ai.risk_factors.length)
                    ? ('<div style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);border-radius:0.4rem;padding:0.5rem;margin-top:0.4rem;">' +
                       '<strong style="color:#f87171;font-size:0.8rem;display:flex;align-items:center;gap:0.3rem;">⚠️ Downside Risks & Headwinds:</strong>' +
                       '<ul style="margin:0.25rem 0 0 1.1rem;padding:0;font-size:0.75rem;color:var(--light);line-height:1.45;">' +
                       ai.risk_factors.map(r => '<li style="margin-bottom:0.2rem;">' + r + '</li>').join('') + '</ul></div>')
                    : '';

                const articlesHtml = (ai.articles && ai.articles.length)
                    ? ('<div style="margin-top:0.75rem;border-top:1px solid rgba(255,255,255,0.1);padding-top:0.6rem;">' +
                       '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">' +
                       '<h5 style="margin:0;font-size:0.82rem;display:flex;align-items:center;gap:0.3rem;">📰 Big News & World Events Stream <span class="timestamp" style="font-size:0.72rem;">(' + ai.articles.length + ' stories)</span></h5>' +
                       '<span class="signal-badge" style="font-size:0.68rem;background:' + (ai.news_sentiment_score >= 0.15 ? 'rgba(16,185,129,0.2);color:#34d399;' : ai.news_sentiment_score <= -0.15 ? 'rgba(239,68,68,0.2);color:#f87171;' : 'rgba(251,191,36,0.2);color:#fbbf24;') + '">' +
                       'News Sentiment: ' + (ai.news_sentiment_label || 'Neutral') + ' (' + (ai.news_sentiment_score >= 0 ? '+' : '') + Number(ai.news_sentiment_score || 0).toFixed(2) + ')' +
                       '</span></div>' +
                       '<div style="display:flex;flex-direction:column;gap:0.45rem;max-height:220px;overflow-y:auto;padding-right:0.2rem;">' +
                       ai.articles.map(a => {
                           const aScore = a.sentiment_score != null ? a.sentiment_score : 0;
                           const aLabel = a.sentiment_label || (aScore >= 0.2 ? 'Bullish' : aScore <= -0.2 ? 'Bearish' : 'Neutral');
                           const aBadgeStyle = aLabel === 'Bullish' ? 'background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.3);' :
                               aLabel === 'Bearish' ? 'background:rgba(239,68,68,0.18);color:#f87171;border:1px solid rgba(239,68,68,0.3);' :
                               'background:rgba(255,255,255,0.06);color:var(--muted);';
                           const topicBadge = (a.topics && a.topics[0])
                               ? '<span class="signal-badge" style="font-size:0.62rem;background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);">' + a.topics[0] + '</span>'
                               : '';

                           return '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.4rem;padding:0.45rem 0.6rem;">' +
                               '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;">' +
                               '<a href="' + (a.link || '#') + '" target="_blank" rel="noopener noreferrer" style="color:#60a5fa;text-decoration:none;font-weight:600;font-size:0.78rem;line-height:1.35;flex:1;">' +
                               (a.title || 'Headline') + ' ↗' +
                               '</a>' +
                               '<div style="display:flex;gap:0.3rem;align-items:center;white-space:nowrap;">' +
                               topicBadge +
                               '<span class="signal-badge" style="font-size:0.62rem;' + aBadgeStyle + '">' + aLabel + '</span>' +
                               '</div></div>' +
                               (a.summary ? '<p style="margin:0.25rem 0 0.15rem 0;font-size:0.72rem;color:var(--muted);line-height:1.35;">' + a.summary + '</p>' : '') +
                               '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.2rem;font-size:0.68rem;color:var(--muted);">' +
                               '<span>Source: <strong>' + (a.publisher || 'Financial Media') + '</strong></span>' +
                               '<span>' + (a.published_at || '') + '</span>' +
                               '</div></div>';
                       }).join('') +
                       '</div></div>')
                    : '';

                content.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.4rem;margin:0.5rem 0;">' +
                    '<div class="metric"><span>Multi-Factor AI Score</span><strong style="color:' + (isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24') + ';">' + scoreStr + ' (' + sig + ')</strong></div>' +
                    '<div class="metric"><span>Volume Accumulation</span><strong>' + (ai.volume_status || 'Average Flow') + ' (' + (ai.volume_ratio || 1.0) + 'x)</strong></div>' +
                    '<div class="metric"><span>7D / 30D Return</span><strong>' + (ai.return_7d >= 0 ? '+' : '') + (ai.return_7d || 0) + '% / ' + (ai.return_30d >= 0 ? '+' : '') + (ai.return_30d || 0) + '%</strong></div>' +
                    '<div class="metric"><span>News Coverage</span><strong>' + (ai.news_count || 0) + ' articles (' + (ai.news_sentiment_label || 'Neutral') + ')</strong></div>' +
                    '</div>' +
                    (ai.thesis ? '<div style="background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.25);border-radius:0.4rem;padding:0.5rem 0.65rem;margin-top:0.4rem;"><strong style="color:#60a5fa;font-size:0.8rem;display:block;margin-bottom:0.2rem;">💡 AI Synthesis Thesis & Reasoning:</strong><p style="margin:0;font-size:0.8rem;line-height:1.45;color:var(--light);">' + ai.thesis + '</p></div>' : '') +
                    '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:0.5rem;">' + catalystsHtml + risksHtml + '</div>' +
                    articlesHtml;
            },

            async runModalConsensus() {
                const ticker = document.getElementById('srModalTicker')?.value;
                const btn = document.getElementById('srModalConsensusRunBtn');
                if (!ticker) return;

                const origHtml = btn ? btn.innerHTML : '⚡ Run AI Consensus';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Synthesizing Models...';
                }

                try {
                    const res = await fetch('/api/v1/consensus/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: [ticker] })
                    });
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Consensus generation failed');
                    }
                    await this._renderModalConsensus(ticker);
                } catch (e) {
                    alert('Error running AI Consensus: ' + e.message);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async _renderModalConsensus(ticker) {
                const badge = document.getElementById('srModalConsensusBadge');
                const content = document.getElementById('srModalConsensusContent');
                if (!content) return;

                if (!ticker) {
                    if (badge) badge.style.display = 'none';
                    content.innerHTML = '<p class="timestamp" style="margin:0;font-size:0.8rem;">No ticker specified for consensus.</p>';
                    return;
                }

                try {
                    content.innerHTML = '<div style="display:flex;align-items:center;gap:0.5rem;color:var(--muted);font-size:0.82rem;"><span class="loading-spinner"></span> Checking multi-model consensus status for ' + ticker + '...</div>';
                    
                    const res = await fetch('/api/v1/consensus/latest?ticker=' + encodeURIComponent(ticker) + '&limit=1');
                    const data = await res.json();
                    const pred = (data.predictions && data.predictions.length) ? data.predictions[0] : null;

                    if (!pred || !pred.consensus_direction) {
                        if (badge) badge.style.display = 'none';
                        content.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.5rem;padding:0.75rem;">' +
                            '<div>' +
                            '<strong style="display:block;font-size:0.85rem;color:var(--light);">No Multi-Model Consensus on Record</strong>' +
                            '<span style="font-size:0.78rem;color:var(--muted);">Trigger an ensemble run to gather calibrated votes, support/resistance targets, and chart patterns from DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, and Mistral Large.</span>' +
                            '</div>' +
                            '<button type="button" class="btn btn-sm" onclick="app.runModalConsensus()" style="background:linear-gradient(135deg, #2563eb, #1d4ed8);color:#fff;border:none;font-size:0.78rem;font-weight:700;padding:0.4rem 0.85rem;border-radius:0.4rem;box-shadow:0 2px 8px rgba(37,99,235,0.3);">⚡ Run Consensus Now</button>' +
                            '</div>';
                        return;
                    }

                    // Extract Consensus Metrics
                    const dir = (pred.consensus_direction || 'NEUTRAL').toUpperCase();
                    const isBull = dir.includes('BULL');
                    const isBear = dir.includes('BEAR');
                    const dirColor = isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24';
                    const dirBg = isBull ? 'rgba(16,185,129,0.2)' : isBear ? 'rgba(239,68,68,0.2)' : 'rgba(251,191,36,0.2)';
                    
                    const strengthPct = pred.consensus_strength != null ? Math.round(pred.consensus_strength) : 80;
                    const agreeRatio = pred.agreement_ratio != null ? Math.round(pred.agreement_ratio * 100) : (pred.agreement_rate ? Math.round(pred.agreement_rate * 100) : 75);
                    const retPct = pred.consensus_return_pct != null ? pred.consensus_return_pct : (pred.expected_move_pct != null ? pred.expected_move_pct : null);
                    const expRetStr = retPct != null ? ((retPct > 0 ? '+' : '') + Number(retPct).toFixed(2) + '%') : '—';
                    
                    const curPrice = pred.as_of_price != null ? ('₹' + Number(pred.as_of_price).toFixed(2)) : '—';
                    const tgtPrice = pred.consensus_target_price != null ? ('₹' + Number(pred.consensus_target_price).toFixed(2)) : '—';
                    const supPrice = pred.consensus_support != null ? ('₹' + Number(pred.consensus_support).toFixed(2)) : '—';
                    const resPrice = pred.consensus_resistance != null ? ('₹' + Number(pred.consensus_resistance).toFixed(2)) : '—';
                    const stopPrice = pred.consensus_stop_loss != null ? ('₹' + Number(pred.consensus_stop_loss).toFixed(2)) : '—';
                    const rrRatio = pred.consensus_risk_reward != null ? ('1 : ' + Number(pred.consensus_risk_reward).toFixed(1)) : '—';
                    const recAction = pred.consensus_recommended_action || (isBull ? (strengthPct >= 80 ? 'STRONG BUY' : 'ACCUMULATE ON DIPS') : isBear ? 'AVOID / TAKE PROFITS' : 'HOLD / WAIT FOR BREAKOUT');
                    const actColor = recAction.includes('BUY') || recAction.includes('ACCUMULATE') ? '#34d399' : recAction.includes('AVOID') || recAction.includes('TAKE PROFIT') ? '#f87171' : '#fbbf24';

                    if (badge) {
                        badge.style.display = 'inline-block';
                        badge.style.background = dirBg;
                        badge.style.color = dirColor;
                        badge.textContent = dir + ' (' + expRetStr + ' · ' + agreeRatio + '% Agreement · ' + strengthPct + '% Strength)';
                    }

                    // 1. Five-Pillar Price Action Matrix
                    const priceMatrixHtml = '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;margin:0.6rem 0;">' +
                        '<div class="metric" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:var(--muted);">Entry / As-Of Price</span>' +
                        '<strong style="font-size:1.05rem;color:var(--light);">' + curPrice + '</strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(52,211,153,0.08);border:1px solid rgba(52,211,153,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#6ee7b7;">Consensus Target</span>' +
                        '<strong style="font-size:1.05rem;color:#34d399;">' + tgtPrice + ' <small style="font-size:0.75rem;">(' + expRetStr + ')</small></strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#93c5fd;">Support Floor</span>' +
                        '<strong style="font-size:1.05rem;color:#60a5fa;">' + supPrice + '</strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(244,63,94,0.08);border:1px solid rgba(244,63,94,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#fda4af;">Resistance Ceiling</span>' +
                        '<strong style="font-size:1.05rem;color:#fb7185;">' + resPrice + '</strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(234,179,8,0.08);border:1px solid rgba(234,179,8,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#fde047;">Stop-Loss & R:R</span>' +
                        '<strong style="font-size:1.05rem;color:#facc15;">' + stopPrice + (rrRatio !== '—' ? (' <small style="font-size:0.72rem;color:var(--muted);">(' + rrRatio + ')</small>') : '') + '</strong>' +
                        '</div>' +
                        '</div>';

                    // 2. Verdict & Action Ribbon
                    const actionRibbonHtml = '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.6rem;background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.6rem 0.85rem;margin-bottom:0.6rem;">' +
                        '<div style="display:flex;align-items:center;gap:0.5rem;">' +
                        '<span style="font-size:0.78rem;color:var(--muted);">Ensemble Action:</span>' +
                        '<span class="signal-badge" style="font-size:0.8rem;font-weight:700;background:rgba(255,255,255,0.08);color:' + actColor + ';border:1px solid ' + actColor + '44;padding:0.2rem 0.6rem;">🎯 ' + recAction + '</span>' +
                        '</div>' +
                        '<div style="display:flex;align-items:center;gap:0.8rem;font-size:0.75rem;color:var(--muted);">' +
                        '<span>Consensus Strength: <strong style="color:' + dirColor + ';">' + strengthPct + '%</strong></span>' +
                        '<span>Model Agreement: <strong style="color:var(--light);">' + agreeRatio + '% (' + (pred.valid_count || pred.model_count || 4) + ' Models)</strong></span>' +
                        '</div>' +
                        '</div>';

                    // 3. Synthesis Thesis Callout
                    const thesisText = pred.synthesized_thesis || pred.synthesis_reasoning || pred.synthesis_summary;
                    const thesisHtml = thesisText ? ('<div style="background:linear-gradient(135deg, rgba(59,130,246,0.1), rgba(37,99,235,0.1));border:1px solid rgba(59,130,246,0.35);border-radius:0.5rem;padding:0.75rem 0.95rem;margin-bottom:0.75rem;">' +
                        '<strong style="color:#93c5fd;font-size:0.82rem;display:flex;align-items:center;gap:0.35rem;margin-bottom:0.3rem;">✨ Ensemble Quantitative Thesis:</strong>' +
                        '<p style="margin:0;font-size:0.82rem;line-height:1.55;color:var(--light);">' + thesisText + '</p>' +
                        '</div>') : '';

                    // 4. Individual Model Detail Cards
                    let modelCardsHtml = '';
                    const rawModels = pred.models_breakdown || pred.model_outputs || pred.model_votes || [];
                    const modelsList = Array.isArray(rawModels) ? rawModels : Object.entries(rawModels).map(([k, v]) => ({ model_name: k, ...(typeof v === 'object' ? v : { direction: v }) }));

                    if (modelsList.length) {
                        const cards = modelsList.map(m => {
                            const mName = m.model_name || m.model_id || 'Unknown Model';
                            const mDir = (m.direction || 'NEUTRAL').toUpperCase();
                            const mBull = mDir.includes('BULL');
                            const mBear = mDir.includes('BEAR');
                            const mColor = mBull ? '#34d399' : mBear ? '#f87171' : '#fbbf24';
                            const mBg = mBull ? 'rgba(52,211,153,0.15)' : mBear ? 'rgba(248,113,113,0.15)' : 'rgba(251,191,36,0.15)';
                            
                            const mConf = m.confidence_pct != null ? (m.confidence_pct + '% Conf') : '';
                            const mTgt = m.target_price != null ? ('₹' + Number(m.target_price).toFixed(2)) : '—';
                            const mRet = m.target_return_pct != null ? ((m.target_return_pct > 0 ? '+' : '') + Number(m.target_return_pct).toFixed(2) + '%') : '—';
                            const mSup = m.support_level != null ? ('₹' + Number(m.support_level).toFixed(2)) : '—';
                            const mRes = m.resistance_level != null ? ('₹' + Number(m.resistance_level).toFixed(2)) : '—';
                            const mStop = m.stop_loss_price != null ? ('₹' + Number(m.stop_loss_price).toFixed(2)) : '—';
                            const mRr = m.risk_reward_ratio != null ? ('1 : ' + Number(m.risk_reward_ratio).toFixed(1)) : '—';
                            const mPattern = m.chart_pattern || '';
                            const mVolume = m.volume_profile_insight || '';
                            const mAction = m.recommended_action || '';
                            const mDrivers = Array.isArray(m.key_drivers) ? m.key_drivers : [];
                            const mRisk = m.primary_risk || '';
                            const mLatency = m.latency_ms ? (m.latency_ms + 'ms') : '';

                            return '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.75rem;display:flex;flex-direction:column;gap:0.45rem;">' +
                                '<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:0.4rem;">' +
                                '<div style="display:flex;align-items:center;gap:0.4rem;">' +
                                '<strong style="font-size:0.82rem;color:#93c5fd;">🤖 ' + mName + '</strong>' +
                                (mLatency ? '<span style="font-size:0.68rem;color:var(--muted);font-family:monospace;">⚡ ' + mLatency + '</span>' : '') +
                                '</div>' +
                                '<div style="display:flex;align-items:center;gap:0.35rem;">' +
                                '<span class="signal-badge" style="font-size:0.7rem;font-weight:700;background:' + mBg + ';color:' + mColor + ';padding:0.15rem 0.45rem;">' + mDir + (mConf ? (' · ' + mConf) : '') + '</span>' +
                                '</div>' +
                                '</div>' +

                                // Model Price Levels Row
                                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.35rem;font-size:0.75rem;background:rgba(0,0,0,0.2);padding:0.45rem 0.6rem;border-radius:0.35rem;">' +
                                '<div><span style="color:var(--muted);">Target:</span> <strong style="color:#34d399;">' + mTgt + ' (' + mRet + ')</strong></div>' +
                                '<div><span style="color:var(--muted);">Support:</span> <strong style="color:#60a5fa;">' + mSup + '</strong></div>' +
                                '<div><span style="color:var(--muted);">Resistance:</span> <strong style="color:#fb7185;">' + mRes + '</strong></div>' +
                                '<div><span style="color:var(--muted);">Stop / R:R:</span> <strong style="color:#facc15;">' + mStop + (mRr !== '—' ? (' (' + mRr + ')') : '') + '</strong></div>' +
                                '</div>' +

                                // Pattern & Order Flow
                                (mPattern ? ('<div style="font-size:0.73rem;color:#38bdf8;">📐 <strong>Pattern:</strong> ' + mPattern + '</div>') : '') +
                                (mVolume ? ('<div style="font-size:0.73rem;color:#38bdf8;">📊 <strong>Order Flow:</strong> ' + mVolume + '</div>') : '') +
                                (mAction ? ('<div style="font-size:0.73rem;color:#fcd34d;">🎯 <strong>Recommended:</strong> ' + mAction + '</div>') : '') +

                                // Drivers & Risk
                                (mDrivers.length ? ('<div style="font-size:0.72rem;color:var(--light);line-height:1.35;margin-top:0.15rem;">' +
                                mDrivers.map(d => '<div>🎯 ' + d + '</div>').join('') +
                                '</div>') : '') +
                                (mRisk ? ('<div style="font-size:0.72rem;color:#fca5a5;margin-top:0.1rem;">⚠️ <strong>Risk:</strong> ' + mRisk + '</div>') : '') +
                                '</div>';
                        }).join('');

                        modelCardsHtml = '<div>' +
                            '<strong style="font-size:0.8rem;color:var(--light);display:block;margin:0.75rem 0 0.4rem 0;">🗳️ Individual Model Predictions & Price Action Insights:</strong>' +
                            '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:0.6rem;">' + cards + '</div>' +
                            '</div>';
                    }

                    // Assemble Complete Content
                    content.innerHTML = actionRibbonHtml + priceMatrixHtml + thesisHtml + modelCardsHtml;

                } catch (err) {
                    console.error('Error rendering modal consensus:', err);
                    if (content) content.innerHTML = '<p class="timestamp" style="margin:0;font-size:0.8rem;color:var(--red);">Failed to load consensus data: ' + err.message + '</p>';
                }
            },

            async openAiDetails(market, ticker, e) {
                if (e) e.stopPropagation();
                market = market || this.currentSwingMarket || 'ALL';
                await this.openSwingRangeModal(market, ticker);
                
                // If not already predicted, run it automatically
                const item = (this.swingData || []).find(x => x.ticker === ticker);
                if (!item || !item.ai_synthesis) {
                    await this.runModalAiForecast();
                }
                
                // Scroll directly to the AI section inside modal
                const aiSec = document.getElementById('srModalAiSection');
                if (aiSec) {
                    aiSec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            },

            async predictAllAiSynthesis(e) {
                const btn = (e && e.target) ? e.target : document.getElementById('swingAiThesisAllBtn');
                
                // If swing data isn't loaded yet, load it first
                if (!this.swingData || !this.swingData.length) {
                    await this.loadSwing();
                }

                const tickers = (this.swingData || []).map(r => r.ticker).filter(Boolean);
                if (!tickers.length) {
                    alert('No stocks found in the current watchlist/universe to synthesize.');
                    return;
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Synthesizing ' + tickers.length + ' stocks...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/ai-forecast/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: tickers, watchlist: this.currentSwingMarket || 'ALL' })
                    });
                    const forecasts = await res.json();
                    if (Array.isArray(forecasts)) {
                        const forecastMap = {};
                        forecasts.forEach(f => {
                            const sym = f.symbol || f.ticker;
                            if (sym) forecastMap[sym.toUpperCase()] = f;
                        });

                        this.swingData.forEach(r => {
                            const sym = (r.ticker || '').toUpperCase();
                            if (forecastMap[sym]) {
                                r.ai_synthesis = forecastMap[sym];
                            }
                        });

                        this.renderSwing();
                    } else {
                        alert('Failed to generate AI news synthesis: ' + (forecasts.detail || forecasts.error || 'Server error'));
                    }
                } catch (err) {
                    console.error('Error in predictAllAiSynthesis:', err);
                    alert('Error running batch AI synthesis. Check server logs.');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async predictAllSwing(e) {
                const btn = (e && e.target) ? e.target : document.getElementById('swingPredictAllBtn');
                
                // If swing data isn't loaded yet, load it first
                if (!this.swingData || !this.swingData.length) {
                    await this.loadSwing();
                }

                const tickers = (this.swingData || []).map(r => r.ticker).filter(Boolean);
                if (!tickers.length) {
                    alert('No stocks found in the current watchlist/universe to predict.');
                    return;
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Predicting ' + tickers.length + ' stocks...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: tickers, lookback: 120, pred_len: 14 })
                    });
                    const forecasts = await res.json();
                    if (Array.isArray(forecasts)) {
                        const forecastMap = {};
                        forecasts.forEach(f => {
                            const sym = f.symbol || f.ticker;
                            if (sym) forecastMap[sym.toUpperCase()] = f;
                        });

                        this.swingData.forEach(r => {
                            const sym = (r.ticker || '').toUpperCase();
                            if (forecastMap[sym]) {
                                r.kronos_prediction = forecastMap[sym];
                            }
                        });

                        this.renderSwing();
                    } else {
                        alert('Failed to generate predictions: ' + (forecasts.detail || forecasts.error || 'Server error'));
                    }
                } catch (err) {
                    console.error('Error in predictAllSwing:', err);
                    alert('Error running batch Kronos predictions. Check server logs.');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            
    
        }
});
})(); // end month_filter IIFE
