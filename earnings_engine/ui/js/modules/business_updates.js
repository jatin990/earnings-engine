// =========================================================================
// business_updates — Pure Operational Disclosures & Anticipated Radar
// Nexus Dashboard Module (2026-10-09)
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    function escapeHtml(str) {
        if (!str && str !== 0) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function sanitizeUrl(url) {
        if (!url) return '#';
        const clean = String(url).trim();
        if (clean.startsWith('http://') || clean.startsWith('https://') || clean.startsWith('/')) {
            return clean.replace(/"/g, '%22').replace(/'/g, '%27').replace(/</g, '%3C').replace(/>/g, '%3E');
        }
        return '#';
    }

    function sanitizeTicker(ticker) {
        if (!ticker) return '';
        return String(ticker).replace(/[^a-zA-Z0-9._-]/g, '').toUpperCase();
    }

    Object.assign(app, {
        bizUpdatesData: [],
        bizUpdatesStats: {},
        bizUpdateSchedulesData: [],
        isBizUpdatesLoading: false,
        isSchedulesLoading: false,

        async loadBusinessUpdates(watchlist, days) {
            const grid = document.getElementById('bizUpdatesGrid');
            if (!grid) return;
            const wlSelect = document.getElementById('catWatchlistSelect');
            const daysSelect = document.getElementById('bizUpdatesDaysFilter');
            const wl = watchlist || (wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL'));
            const d = (days !== undefined && days !== null) ? days : (daysSelect ? daysSelect.value : '30');

            grid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading corporate operational updates & disclosures...</div>';
            this.isBizUpdatesLoading = true;

            const fetchFn = (this.apiFetch ? this.apiFetch.bind(this) : fetch);
            try {
                const res = await fetchFn(API_BASE + `/api/v1/news/business-updates?days=${encodeURIComponent(d)}&limit=200`, {}, 'catalysts');
                if (res.ok) {
                    const json = await res.json();
                    this.bizUpdatesData = json.updates || [];
                    this.bizUpdatesStats = json.stats || {};
                    this.renderBusinessUpdates();
                    this.updateBusinessUpdatesKpis();
                } else {
                    grid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:#f87171;">Failed to load business updates.</div>';
                }
            } catch (err) {
                console.error('Error loading business updates:', err);
                grid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:#f87171;">Network error loading business updates.</div>';
            } finally {
                this.isBizUpdatesLoading = false;
            }
        },

        updateBusinessUpdatesKpis() {
            const stats = this.bizUpdatesStats || {};
            const totalEl = document.getElementById('bizUpdatesStatTotal');
            const highEl = document.getElementById('bizUpdatesStatHigh');
            const biasEl = document.getElementById('bizUpdatesStatBias');
            const sectorsEl = document.getElementById('bizUpdatesStatSectors');

            if (totalEl) totalEl.textContent = stats.total_business_updates || this.bizUpdatesData.length || '0';
            if (highEl) highEl.textContent = stats.high_impact_count || '0';
            if (biasEl) {
                const bull = stats.bullish_count || 0;
                const bear = stats.bearish_count || 0;
                biasEl.innerHTML = `<span style="color:#34d399;">${bull}▲</span> / <span style="color:#f87171;">${bear}▼</span>`;
            }
            if (sectorsEl) {
                const quarters = stats.quarterly_updates_count || 0;
                const autos = stats.monthly_sales_count || 0;
                const realty = stats.realty_bookings_count || 0;
                const banks = stats.banking_advances_count || 0;
                sectorsEl.textContent = `Qtr:${quarters} · Auto:${autos} · RE:${realty} · Bank:${banks}`;
            }
        },

        filterBusinessUpdates() {
            this.renderBusinessUpdates();
        },

        renderBusinessUpdates() {
            const grid = document.getElementById('bizUpdatesGrid');
            const countBadge = document.getElementById('bizUpdatesCountBadge');
            if (!grid) return;

            const searchQ = (document.getElementById('bizUpdatesSearchInput')?.value || '').toLowerCase().trim();
            const catFilter = document.getElementById('bizUpdatesCategoryFilter')?.value || 'ALL';
            const dirFilter = document.getElementById('bizUpdatesDirectionFilter')?.value || 'ALL';
            const sortBy = document.getElementById('bizUpdatesSortBy')?.value || 'recency';

            let items = [...(this.bizUpdatesData || [])];

            if (searchQ) {
                items = items.filter(item =>
                    (item.ticker || '').toLowerCase().includes(searchQ) ||
                    (item.company_name || '').toLowerCase().includes(searchQ) ||
                    (item.stock_name || '').toLowerCase().includes(searchQ) ||
                    (item.title || '').toLowerCase().includes(searchQ) ||
                    (item.summary || '').toLowerCase().includes(searchQ)
                );
            }

            if (catFilter !== 'ALL') {
                items = items.filter(item => {
                    const cat = (item.business_update_type || item.category || '').toUpperCase();
                    if (catFilter === 'QUARTERLY') return cat.includes('QUARTER') || cat.includes('BUSINESS');
                    if (catFilter === 'MONTHLY') return cat.includes('MONTH') || cat.includes('AUTO') || cat.includes('SALES');
                    if (catFilter === 'REALTY') return cat.includes('REALTY') || cat.includes('BOOKING') || cat.includes('PRE-SALE');
                    if (catFilter === 'BANKING') return cat.includes('BANK') || cat.includes('ADVANCE') || cat.includes('DEPOSIT');
                    return true;
                });
            }

            if (dirFilter !== 'ALL') {
                items = items.filter(item => item.direction === dirFilter);
            }

            if (sortBy === 'impact') {
                items.sort((a, b) => (b.impact_score || 0) - (a.impact_score || 0));
            } else if (sortBy === 'reaction') {
                items.sort((a, b) => (b.reaction_1d || 0) - (a.reaction_1d || 0));
            } else {
                items.sort((a, b) => (b.published_at || b.date || '').localeCompare(a.published_at || a.date || ''));
            }

            if (countBadge) {
                countBadge.textContent = `${items.length} updates found`;
            }

            if (!items.length) {
                grid.innerHTML = `
                    <div class="card" style="padding:2.5rem;text-align:center;color:var(--muted);grid-column: 1 / -1;">
                        <div style="font-size:1.5rem;margin-bottom:0.5rem;">📋</div>
                        <div style="font-size:0.85rem;font-weight:600;color:#f8fafc;margin-bottom:0.25rem;">No Corporate Business Updates Matching Criteria</div>
                        <div style="font-size:0.72rem;color:#94a3b8;">Try clearing search filters or changing the lookback timeframe.</div>
                    </div>
                `;
                return;
            }

            const getCategoryPill = (item) => {
                const title = (item.title || '').toLowerCase();
                const type = item.business_update_type || '';
                if (type === 'REALTY_BOOKINGS' || title.includes('booking') || title.includes('pre-sales')) {
                    return `<span style="font-size:0.65rem;background:rgba(168,85,247,0.18);color:#c084fc;border:1px solid rgba(168,85,247,0.35);padding:0.1rem 0.35rem;border-radius:4px;font-weight:700;">🏢 Realty Bookings</span>`;
                }
                if (type === 'MONTHLY_SALES' || title.includes('monthly sales') || title.includes('dispatch') || title.includes('sales volume')) {
                    return `<span style="font-size:0.65rem;background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);padding:0.1rem 0.35rem;border-radius:4px;font-weight:700;">🚗 Monthly Sales</span>`;
                }
                if (type === 'BANKING_ADVANCES' || title.includes('advances') || title.includes('deposits') || title.includes('casa')) {
                    return `<span style="font-size:0.65rem;background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);padding:0.1rem 0.35rem;border-radius:4px;font-weight:700;">🏦 Banking Advances</span>`;
                }
                return `<span style="font-size:0.65rem;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.35);padding:0.1rem 0.35rem;border-radius:4px;font-weight:700;">📊 Quarterly Business Update</span>`;
            };

            grid.innerHTML = items.map(u => {
                const ticker = sanitizeTicker(u.ticker || '');
                const rawStockName = u.company_name || u.stock_name || ticker;
                const stockName = escapeHtml(rawStockName);
                const isBull = (u.direction || 'BULLISH') === 'BULLISH';
                const dirColor = isBull ? '#34d399' : '#f87171';
                const dirBg = isBull ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)';
                const dirBorder = isBull ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)';
                const dirText = isBull ? '▲ BULLISH' : '▼ BEARISH';
                const impactScore = Number(u.impact_score) || 84;
                const pubDate = escapeHtml((u.published_at || u.date || '').slice(0, 16).replace('T', ' '));
                const rawTitle = u.title || 'Operational Business Update';
                const title = escapeHtml(rawTitle);
                const summary = escapeHtml(u.summary || u.description || 'Pre-earnings operational metrics, sales volume and capacity utilization update.');
                const link = sanitizeUrl(u.url || u.link || '#');
                const encodedTitle = encodeURIComponent(rawTitle);
                const encodedSummary = encodeURIComponent(u.summary || u.description || '');
                const updateId = encodeURIComponent(String(u.id || ''));

                return `
                    <div class="card" style="padding:0.75rem 0.95rem;background:#050505;border:1px solid rgba(255,255,255,0.08);border-radius:8px;display:flex;flex-direction:column;justify-content:space-between;gap:0.5rem;transition:border-color 0.15s ease;" onmouseover="this.style.borderColor='rgba(59,130,246,0.4)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'">
                        <div>
                            <!-- Header Row: Stock + Pill + Impact -->
                            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.4rem;gap:0.4rem;flex-wrap:wrap;">
                                <div style="display:flex;align-items:center;gap:0.4rem;">
                                    <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="font-size:0.88rem;font-weight:800;color:#60a5fa;text-decoration:none;font-family:var(--font-mono);" title="Open ${escapeHtml(ticker)} intelligence page">
                                        ${escapeHtml(ticker)} ↗
                                    </a>
                                    <span style="font-size:0.72rem;color:#94a3b8;font-weight:500;">${stockName}</span>
                                </div>
                                <div style="display:flex;align-items:center;gap:0.35rem;">
                                    ${getCategoryPill(u)}
                                    <span style="font-size:0.65rem;background:${dirBg};color:${dirColor};border:1px solid ${dirBorder};padding:0.1rem 0.35rem;border-radius:4px;font-weight:700;font-family:var(--font-mono);">${dirText}</span>
                                    <span style="font-size:0.65rem;background:rgba(251,191,36,0.15);color:#fbbf24;border:1px solid rgba(251,191,36,0.3);padding:0.1rem 0.35rem;border-radius:4px;font-weight:700;font-family:var(--font-mono);">⚡ ${impactScore}%</span>
                                </div>
                            </div>

                            <!-- Headline & Link -->
                            <div style="margin-bottom:0.4rem;">
                                <a href="${link}" target="_blank" rel="noopener noreferrer" style="font-size:0.82rem;font-weight:700;color:#f8fafc;line-height:1.4;text-decoration:none;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#f8fafc'">
                                    ${title}
                                </a>
                            </div>

                            <!-- Extracted Summary / Key Operational Disclosures -->
                            <div style="font-size:0.72rem;color:#a1a1aa;line-height:1.45;background:rgba(255,255,255,0.02);padding:0.45rem 0.6rem;border-radius:5px;border-left:2px solid #38bdf8;margin-bottom:0.4rem;">
                                ${summary}
                            </div>
                        </div>

                        <!-- Footer Meta + Action Buttons -->
                        <div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.35rem;border-top:1px solid rgba(255,255,255,0.06);flex-wrap:wrap;gap:0.35rem;">
                            <span style="font-size:0.65rem;color:#64748b;font-family:var(--font-mono);">
                                🕒 Disclosed: ${pubDate}
                            </span>
                            <div style="display:flex;gap:0.25rem;align-items:center;">
                                <button type="button" onclick="app.analyzeNewsWithAI('${encodedTitle}', '${encodedSummary}', '${ticker}', '${updateId}')" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.45rem;background:rgba(168,85,247,0.15);color:#c084fc;border:1px solid rgba(168,85,247,0.35);font-weight:600;" title="Run Instant LLM Analysis on this disclosure">
                                    <span>🧠</span> Analyze
                                </button>
                                <button type="button" onclick="app.openStockDrawer('${ticker}')" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.45rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);font-weight:600;" title="Open Stock Forensics Drawer">
                                    <span>🎯</span> Forensics
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        },

        async loadBusinessUpdateSchedules(status, daysAhead) {
            const container = document.getElementById('bizUpdateSchedulesContainer');
            if (!container) return;

            const statusSelect = document.getElementById('schedulesStatusFilter');
            const daysSelect = document.getElementById('schedulesDaysFilter');
            const st = status || (statusSelect ? statusSelect.value : '');
            const da = (daysAhead !== undefined && daysAhead !== null) ? daysAhead : (daysSelect ? daysSelect.value : '60');

            container.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading anticipated reporting cadences and radar schedules...</div>';
            this.isSchedulesLoading = true;

            const fetchFn = (this.apiFetch ? this.apiFetch.bind(this) : fetch);
            try {
                let url = API_BASE + `/api/v1/news/business-updates/schedules?days_ahead=${encodeURIComponent(da)}`;
                if (st && st !== 'ALL') url += `&status=${encodeURIComponent(st)}`;

                const res = await fetchFn(url, {}, 'catalysts');
                if (res.ok) {
                    const json = await res.json();
                    this.bizUpdateSchedulesData = json.schedules || [];
                    this.renderBusinessUpdateSchedules();
                    this.updateSchedulesKpis();
                } else {
                    container.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:#f87171;">Failed to load business update schedules.</div>';
                }
            } catch (err) {
                console.error('Error loading schedules:', err);
                container.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:#f87171;">Network error loading schedules.</div>';
            } finally {
                this.isSchedulesLoading = false;
            }
        },

        updateSchedulesKpis() {
            const list = this.bizUpdateSchedulesData || [];
            const dueNowCount = list.filter(s => s.status === 'DUE_NOW').length;
            const anticipatedCount = list.filter(s => s.status === 'ANTICIPATED').length;
            const overdueCount = list.filter(s => s.status === 'OVERDUE').length;

            const dueEl = document.getElementById('schedulesStatDueNow');
            const antEl = document.getElementById('schedulesStatAnticipated');
            const trackedEl = document.getElementById('schedulesStatTracked');
            const avgReactEl = document.getElementById('schedulesStatAvgReact');

            if (dueEl) dueEl.textContent = dueNowCount;
            if (antEl) antEl.textContent = anticipatedCount;
            if (trackedEl) trackedEl.textContent = list.length;
            if (avgReactEl) {
                avgReactEl.textContent = `${dueNowCount + anticipatedCount} Active`;
            }
        },

        filterBusinessUpdateSchedules() {
            this.renderBusinessUpdateSchedules();
        },

        async syncBusinessUpdateSchedulesNow() {
            const btn = document.getElementById('catSyncSchedulesBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '⏳ Recalculating Cadences...';
            }
            try {
                const res = await fetch(API_BASE + '/api/v1/news/business-updates/sync-schedules', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });
                if (res.ok) {
                    const data = await res.json();
                    await this.loadBusinessUpdateSchedules();
                }
            } catch (e) {
                console.error('Error syncing schedules:', e);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>🔄</span> Recalculate Cadences';
                }
            }
        },

        renderBusinessUpdateSchedules() {
            const container = document.getElementById('bizUpdateSchedulesContainer');
            const countBadge = document.getElementById('schedulesCountBadge');
            if (!container) return;

            const searchQ = (document.getElementById('schedulesSearchInput')?.value || '').toLowerCase().trim();
            const typeFilter = document.getElementById('schedulesTypeFilter')?.value || 'ALL';
            const statusFilter = document.getElementById('schedulesStatusFilter')?.value || 'ALL';

            let items = [...(this.bizUpdateSchedulesData || [])];

            if (searchQ) {
                items = items.filter(s =>
                    (s.ticker || '').toLowerCase().includes(searchQ) ||
                    (s.company_name || '').toLowerCase().includes(searchQ) ||
                    (s.update_type || '').toLowerCase().includes(searchQ)
                );
            }

            if (typeFilter !== 'ALL') {
                items = items.filter(s => (s.update_type || '') === typeFilter);
            }

            if (statusFilter !== 'ALL') {
                items = items.filter(s => (s.status || '') === statusFilter);
            }

            if (countBadge) {
                countBadge.textContent = `${items.length} cadences active`;
            }

            if (!items.length) {
                container.innerHTML = `
                    <div class="card" style="padding:2.5rem;text-align:center;color:var(--muted);">
                        <div style="font-size:1.5rem;margin-bottom:0.5rem;">📅</div>
                        <div style="font-size:0.85rem;font-weight:600;color:#f8fafc;margin-bottom:0.25rem;">No Anticipated Reporting Windows Found</div>
                        <div style="font-size:0.72rem;color:#94a3b8;">Try changing status filters or clicking "Recalculate Cadences".</div>
                    </div>
                `;
                return;
            }

            const getStatusBadge = (status) => {
                if (status === 'DUE_NOW') {
                    return `<span style="display:inline-flex;align-items:center;gap:0.25rem;background:rgba(239,68,68,0.18);color:#f87171;border:1px solid rgba(239,68,68,0.4);padding:0.12rem 0.45rem;border-radius:4px;font-weight:800;font-size:0.68rem;font-family:var(--font-mono);"><span style="width:6px;height:6px;border-radius:50%;background:#ef4444;display:inline-block;animation:pulse 1.2s infinite;"></span> 🚨 DUE NOW</span>`;
                }
                if (status === 'OVERDUE') {
                    return `<span style="background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);padding:0.12rem 0.45rem;border-radius:4px;font-weight:700;font-size:0.68rem;font-family:var(--font-mono);">⚠️ OVERDUE</span>`;
                }
                return `<span style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);padding:0.12rem 0.45rem;border-radius:4px;font-weight:700;font-size:0.68rem;font-family:var(--font-mono);">📅 ANTICIPATED</span>`;
            };

            const getTypeBadge = (type) => {
                if (type === 'REALTY_BOOKINGS') return '<span style="color:#c084fc;font-weight:600;">🏢 Realty Bookings</span>';
                if (type === 'MONTHLY_SALES') return '<span style="color:#38bdf8;font-weight:600;">🚗 Auto Monthly Sales</span>';
                if (type === 'BANKING_ADVANCES') return '<span style="color:#fbbf24;font-weight:600;">🏦 Banking Advances</span>';
                return '<span style="color:#34d399;font-weight:600;">📊 Quarterly Business Update</span>';
            };

            container.innerHTML = `
                <div style="overflow-x:auto;">
                    <table style="width:100%;border-collapse:collapse;font-size:0.75rem;text-align:left;">
                        <thead>
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.08);color:#71717a;background:rgba(255,255,255,0.01);">
                                <th style="padding:0.45rem 0.6rem;">Company / Stock</th>
                                <th style="padding:0.45rem 0.6rem;">Update Type</th>
                                <th style="padding:0.45rem 0.6rem;">Frequency</th>
                                <th style="padding:0.45rem 0.6rem;">Reporting Pattern</th>
                                <th style="padding:0.45rem 0.6rem;">Expected Window</th>
                                <th style="padding:0.45rem 0.6rem;text-align:center;">Status</th>
                                <th style="padding:0.45rem 0.6rem;text-align:right;">Confidence</th>
                                <th style="padding:0.45rem 0.6rem;text-align:center;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${items.map(s => {
                                const ticker = sanitizeTicker(s.ticker || '');
                                const company = escapeHtml(s.company_name || ticker);
                                const winStart = escapeHtml(s.next_expected_window_start || '—');
                                const winEnd = escapeHtml(s.next_expected_window_end || '—');
                                const conf = s.confidence_score ? `${Math.round(Number(s.confidence_score) * 100)}%` : '85%';
                                const typicalDays = Number(s.typical_days_after_period) || 5;
                                const frequency = escapeHtml(s.frequency || 'QUARTERLY');

                                return `
                                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);transition:background 0.12s ease;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                                        <td style="padding:0.45rem 0.6rem;white-space:nowrap;">
                                            <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="font-weight:700;color:#60a5fa;text-decoration:none;font-family:var(--font-mono);" title="Open ${escapeHtml(ticker)} intelligence page">
                                                ${escapeHtml(ticker)} ↗
                                            </a>
                                            <div style="font-size:0.68rem;color:#94a3b8;">${company}</div>
                                        </td>
                                        <td style="padding:0.45rem 0.6rem;white-space:nowrap;">
                                            ${getTypeBadge(s.update_type)}
                                        </td>
                                        <td style="padding:0.45rem 0.6rem;white-space:nowrap;color:#a1a1aa;font-family:var(--font-mono);font-size:0.7rem;">
                                            ${frequency}
                                        </td>
                                        <td style="padding:0.45rem 0.6rem;color:#cbd5e1;font-size:0.72rem;">
                                            Day ${typicalDays} after period end
                                        </td>
                                        <td style="padding:0.45rem 0.6rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.72rem;color:#38bdf8;font-weight:600;">
                                            ${winStart} &rarr; ${winEnd}
                                        </td>
                                        <td style="padding:0.45rem 0.6rem;text-align:center;white-space:nowrap;">
                                            ${getStatusBadge(s.status)}
                                        </td>
                                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#fbbf24;font-weight:700;">
                                            ${conf}
                                        </td>
                                        <td style="padding:0.45rem 0.6rem;text-align:center;white-space:nowrap;">
                                            <button type="button" onclick="app.openStockDrawer('${ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.68rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);" title="Open Forensics Drawer">
                                                <span>🎯</span> Drawer
                                            </button>
                                        </td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }
    });
})();
