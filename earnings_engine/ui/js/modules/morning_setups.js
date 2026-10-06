// =========================================================================
// 🌅 Morning Setups: Block Deals & Board Meetings Radar Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const morningSetupsModule = {
        dealsData: [],
        dealsSummary: null,
        meetingsData: [],
        meetingsSummary: null,
        activeSubtab: 'deals',
        dealsLoading: false,
        meetingsLoading: false,

        init() {
            // Check persisted or default subtab
            const savedSubtab = localStorage.getItem('morning_setups_subtab') || 'deals';
            this.switchSubtab(savedSubtab, false);
            this.loadDealsSummary();
            this.loadDeals();
            this.loadMeetingsSummary();
            this.loadMeetings();
        },

        switchSubtab(subtab, reload = true) {
            subtab = subtab || 'deals';
            this.activeSubtab = subtab;
            try {
                localStorage.setItem('morning_setups_subtab', subtab);
            } catch (e) {}

            const dealsDiv = document.getElementById('morningSubtab-deals');
            const meetingsDiv = document.getElementById('morningSubtab-meetings');
            const btnDeals = document.getElementById('btnMorningSubDeals');
            const btnMeetings = document.getElementById('btnMorningSubMeetings');

            if (subtab === 'deals') {
                if (dealsDiv) dealsDiv.style.display = 'block';
                if (meetingsDiv) meetingsDiv.style.display = 'none';

                if (btnDeals) {
                    btnDeals.style.background = '#18181b';
                    btnDeals.style.color = '#ffffff';
                    btnDeals.style.border = '1px solid rgba(255,255,255,0.3)';
                    btnDeals.style.fontWeight = '700';
                }
                if (btnMeetings) {
                    btnMeetings.style.background = 'transparent';
                    btnMeetings.style.color = '#94a3b8';
                    btnMeetings.style.border = '1px solid transparent';
                    btnMeetings.style.fontWeight = '500';
                }
                if (reload && (!this.dealsData || this.dealsData.length === 0)) {
                    this.loadDeals();
                }
            } else {
                if (dealsDiv) dealsDiv.style.display = 'none';
                if (meetingsDiv) meetingsDiv.style.display = 'block';

                if (btnDeals) {
                    btnDeals.style.background = 'transparent';
                    btnDeals.style.color = '#94a3b8';
                    btnDeals.style.border = '1px solid transparent';
                    btnDeals.style.fontWeight = '500';
                }
                if (btnMeetings) {
                    btnMeetings.style.background = '#18181b';
                    btnMeetings.style.color = '#ffffff';
                    btnMeetings.style.border = '1px solid rgba(255,255,255,0.3)';
                    btnMeetings.style.fontWeight = '700';
                }
                if (reload && (!this.meetingsData || this.meetingsData.length === 0)) {
                    this.loadMeetings();
                }
            }
        },

        // ---------------------------------------------------------------------
        // Block & Bulk Deals Handlers
        // ---------------------------------------------------------------------
        onDealsDateChange(val) {
            this.loadDeals(true);
        },

        getDateRangeFromPreset(preset) {
            const today = new Date();
            const format = (d) => d.toISOString().split('T')[0];

            if (preset === 'today') {
                return { deal_date: format(today) };
            } else if (preset === 'yesterday') {
                const y = new Date(today);
                y.setDate(y.getDate() - 1);
                return { deal_date: format(y) };
            } else if (preset === '7d') {
                const s = new Date(today);
                s.setDate(s.getDate() - 7);
                return { start_date: format(s), end_date: format(today) };
            } else if (preset === '30d') {
                const s = new Date(today);
                s.setDate(s.getDate() - 30);
                return { start_date: format(s), end_date: format(today) };
            }
            return {}; // 'all'
        },

        async loadDealsSummary() {
            try {
                const res = await fetch(`${API_BASE}/api/v1/morning-setups/deals/summary`);
                if (!res.ok) return;
                const data = await res.json();
                this.dealsSummary = data;
                this.renderDealsSummary(data);
            } catch (err) {
                console.error('Error fetching morning deals summary:', err);
            }
        },

        renderDealsSummary(summary) {
            if (!summary) return;
            const totalEl = document.getElementById('metricDealsTotalCount');
            const blockEl = document.getElementById('metricDealsBlockCount');
            const buyEl = document.getElementById('metricDealsBuyValue');
            const sellEl = document.getElementById('metricDealsSellValue');

            if (totalEl) totalEl.textContent = Number(summary.total_deals || 0).toLocaleString();
            if (blockEl) blockEl.textContent = `${Number(summary.block_deals_count || 0).toLocaleString()} (${Number(summary.bulk_deals_count || 0).toLocaleString()} Bulk)`;
            if (buyEl) buyEl.textContent = `₹${Number(summary.gross_buy_cr || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} Cr`;
            if (sellEl) sellEl.textContent = `₹${Number(summary.gross_sell_cr || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} Cr`;
        },

        async loadDeals(forceRefresh = false) {
            if (this.dealsLoading) return;
            this.dealsLoading = true;

            const tbody = document.getElementById('morningDealsTableBody');
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: #94a3b8;"><div class="spinner" style="margin: 0 auto 0.5rem auto;"></div>Loading executed block &amp; bulk deals...</td></tr>`;
            }

            try {
                const search = (document.getElementById('morningDealsSearchInput')?.value || '').trim();
                const datePreset = document.getElementById('morningDealsDateSelect')?.value || '7d';
                const dealType = document.getElementById('morningDealsTypeSelect')?.value || '';
                const side = document.getElementById('morningDealsSideSelect')?.value || '';
                const minVal = document.getElementById('morningDealsMinValSelect')?.value || '10';

                const params = new URLSearchParams();
                const dateRange = this.getDateRangeFromPreset(datePreset);
                if (dateRange.deal_date) params.append('deal_date', dateRange.deal_date);
                if (dateRange.start_date) params.append('start_date', dateRange.start_date);
                if (dateRange.end_date) params.append('end_date', dateRange.end_date);
                if (dealType) params.append('deal_type', dealType);
                if (side) params.append('transaction_type', side);
                if (minVal && parseFloat(minVal) > 0) params.append('min_value_cr', minVal);
                if (search) {
                    if (search.length <= 10 && !search.includes(' ')) {
                        params.append('ticker', search);
                    } else {
                        params.append('client_name', search);
                    }
                }
                params.append('limit', '300');

                const res = await fetch(`${API_BASE}/api/v1/morning-setups/deals?${params.toString()}`);
                if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                const data = await res.json();
                this.dealsData = data.deals || [];
                this.renderDealsTable(this.dealsData);
            } catch (err) {
                console.error('Error loading morning deals:', err);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: #f87171;">Failed to load deals data. Error: ${this.escapeHtml(err.message)}</td></tr>`;
                }
            } finally {
                this.dealsLoading = false;
            }
        },

        renderDealsTable(deals) {
            const tbody = document.getElementById('morningDealsTableBody');
            if (!tbody) return;

            if (!deals || deals.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 3rem 1rem; color: #64748b;"><div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📦</div><div>No executed block or bulk deals found matching the selected filters.</div><div style="font-size: 0.72rem; color: #475569; margin-top: 0.35rem;">Try relaxing minimum deal value (₹ Cr) or expanding the date range.</div></td></tr>`;
                return;
            }

            tbody.innerHTML = deals.map((d) => {
                const isBuy = (d.transaction_type || '').toUpperCase() === 'BUY';
                const sideColor = isBuy ? '#34d399' : '#f87171';
                const sideBg = isBuy ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
                const sideBorder = isBuy ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)';

                const isBlock = (d.deal_type || '').toUpperCase() === 'BLOCK';
                const typeColor = isBlock ? '#38bdf8' : '#fbbf24';
                const typeBg = isBlock ? 'rgba(56,189,248,0.15)' : 'rgba(245,158,11,0.15)';

                const qtyFmt = Number(d.quantity || 0).toLocaleString();
                const priceFmt = Number(d.trade_price || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                const valueCrFmt = Number(d.value_cr || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

                const rawSym = (d.ticker || '').toUpperCase().replace('.NS', '');
                const cleanSym = this.escapeHtml(rawSym);
                const clientName = this.escapeHtml(d.client_name || '—');

                return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s ease;" onmouseenter="this.style.background='rgba(255,255,255,0.02)'" onmouseleave="this.style.background='transparent'">
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-size: 0.72rem; color: #cbd5e1; white-space: nowrap;">
                        ${this.escapeHtml(d.deal_date || '—')}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-weight: 700;">
                        <a href="javascript:void(0)" onclick="app.openStockDetail ? app.openStockDetail('${cleanSym}.NS') : (window.stockDrawer ? window.stockDrawer.open('${cleanSym}.NS') : null)" style="color: #60a5fa; text-decoration: none; display: inline-flex; align-items: center; gap: 0.25rem;">
                            <span>${cleanSym}</span>
                        </a>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #e2e8f0;" title="${clientName}">
                        ${clientName}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        <span style="background: ${typeBg}; color: ${typeColor}; border: 1px solid ${typeColor}40; padding: 0.12rem 0.45rem; border-radius: 4px; font-size: 0.65rem; font-family: var(--font-mono); font-weight: 700;">
                            ${this.escapeHtml(d.deal_type || 'DEAL')}
                        </span>
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        <span style="background: ${sideBg}; color: ${sideColor}; border: 1px solid ${sideBorder}; padding: 0.12rem 0.45rem; border-radius: 4px; font-size: 0.65rem; font-family: var(--font-mono); font-weight: 800;">
                            ${this.escapeHtml(d.transaction_type || '—')}
                        </span>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); color: #94a3b8;">
                        ${qtyFmt}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); color: #f8fafc; font-weight: 600;">
                        ₹${priceFmt}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); font-weight: 800; color: ${isBuy ? '#34d399' : '#f87171'};">
                        ₹${valueCrFmt} Cr
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: center;">
                        <button type="button" onclick="app.openStockDetail ? app.openStockDetail('${cleanSym}.NS') : (window.stockDrawer ? window.stockDrawer.open('${cleanSym}.NS') : null)" class="btn btn-secondary btn-sm" style="font-size: 0.65rem; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.15);" title="Open Stock Forensics">
                            📊 Inspect
                        </button>
                    </td>
                </tr>`;
            }).join('');
        },

        async triggerDealsSync() {
            const btn = document.getElementById('btnMorningDealsSync');
            const origText = btn ? btn.innerHTML : '';
            if (btn) {
                btn.innerHTML = `<span class="spinner" style="display:inline-block;width:12px;height:12px;vertical-align:middle;margin-right:4px;"></span> Syncing NSE...`;
                btn.disabled = true;
            }

            try {
                const res = await fetch(`${API_BASE}/api/v1/morning-setups/deals/sync`, { method: 'POST' });
                const json = await res.json();
                if (!res.ok) throw new Error(json.detail || 'Sync failed');

                this.showLiveSyncBadge('DEALS SYNCED');
                await this.loadDealsSummary();
                await this.loadDeals(true);
            } catch (err) {
                alert(`Deals Sync Notice: ${err.message}`);
            } finally {
                if (btn) {
                    btn.innerHTML = origText;
                    btn.disabled = false;
                }
            }
        },

        // ---------------------------------------------------------------------
        // Board Meetings Radar Handlers
        // ---------------------------------------------------------------------
        filterMeetingsPreset(sym) {
            const input = document.getElementById('morningMeetingsSearchInput');
            if (input) input.value = sym;
            this.loadMeetings(true);
        },

        async loadMeetingsSummary() {
            try {
                const res = await fetch(`${API_BASE}/api/v1/morning-setups/board-meetings/summary`);
                if (!res.ok) return;
                const data = await res.json();
                this.meetingsSummary = data;
                this.renderMeetingsSummary(data);
            } catch (err) {
                console.error('Error fetching board meetings summary:', err);
            }
        },

        renderMeetingsSummary(summary) {
            if (!summary) return;
            const totalEl = document.getElementById('metricMeetingsTotalCount');
            const highEl = document.getElementById('metricMeetingsHighCount');
            const medEl = document.getElementById('metricMeetingsMediumCount');
            const next7El = document.getElementById('metricMeetingsNext7DCount');

            if (totalEl) totalEl.textContent = Number(summary.total_upcoming || 0).toLocaleString();
            if (highEl) highEl.textContent = Number(summary.high_impact_count || 0).toLocaleString();
            if (medEl) medEl.textContent = Number(summary.medium_impact_count || 0).toLocaleString();
            if (next7El) next7El.textContent = Number(summary.next_7_days_count || 0).toLocaleString();
        },

        async loadMeetings(forceRefresh = false) {
            if (this.meetingsLoading) return;
            this.meetingsLoading = true;

            const tbody = document.getElementById('morningMeetingsTableBody');
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 2rem; color: #94a3b8;"><div class="spinner" style="margin: 0 auto 0.5rem auto;"></div>Loading upcoming corporate board meetings...</td></tr>`;
            }

            try {
                const search = (document.getElementById('morningMeetingsSearchInput')?.value || '').trim();
                const impact = document.getElementById('morningMeetingsImpactSelect')?.value || '';
                const horizon = document.getElementById('morningMeetingsHorizonSelect')?.value || '30';

                const params = new URLSearchParams();
                if (search) params.append('ticker', search);
                if (impact) params.append('impact_tier', impact);
                if (horizon) params.append('days_ahead', horizon);
                params.append('limit', '300');

                const res = await fetch(`${API_BASE}/api/v1/morning-setups/board-meetings?${params.toString()}`);
                if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                const data = await res.json();
                this.meetingsData = data.meetings || [];
                this.renderMeetingsTable(this.meetingsData);
            } catch (err) {
                console.error('Error loading board meetings:', err);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 2rem; color: #f87171;">Failed to load board meetings. Error: ${this.escapeHtml(err.message)}</td></tr>`;
                }
            } finally {
                this.meetingsLoading = false;
            }
        },

        renderMeetingsTable(meetings) {
            const tbody = document.getElementById('morningMeetingsTableBody');
            if (!tbody) return;

            if (!meetings || meetings.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 3rem 1rem; color: #64748b;"><div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📅</div><div>No scheduled board meetings found for the selected impact tier and horizon.</div><div style="font-size: 0.72rem; color: #475569; margin-top: 0.35rem;">Try selecting "All Impact Tiers" or expanding the horizon to 45D / 90D.</div></td></tr>`;
                return;
            }

            const today = new Date();
            today.setHours(0, 0, 0, 0);

            tbody.innerHTML = meetings.map((m) => {
                const impact = (m.impact_tier || 'ROUTINE').toUpperCase();
                let impactColor = '#94a3b8';
                let impactBg = 'rgba(148,163,184,0.12)';
                let impactLabel = 'ROUTINE';

                if (impact === 'HIGH') {
                    impactColor = '#f87171';
                    impactBg = 'rgba(239,68,68,0.18)';
                    impactLabel = '🔥 HIGH IMPACT';
                } else if (impact === 'MEDIUM') {
                    impactColor = '#fbbf24';
                    impactBg = 'rgba(245,158,11,0.18)';
                    impactLabel = '⚡ MEDIUM IMPACT';
                }

                let daysLeftStr = '—';
                let daysLeftNum = null;
                if (m.meeting_date) {
                    const mDate = new Date(m.meeting_date);
                    mDate.setHours(0, 0, 0, 0);
                    const diffTime = mDate.getTime() - today.getTime();
                    daysLeftNum = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                    if (daysLeftNum === 0) {
                        daysLeftStr = `<span style="color:#fbbf24;font-weight:800;">TODAY</span>`;
                    } else if (daysLeftNum === 1) {
                        daysLeftStr = `<span style="color:#38bdf8;font-weight:700;">Tomorrow</span>`;
                    } else if (daysLeftNum > 1) {
                        daysLeftStr = `In ${daysLeftNum} days`;
                    } else {
                        daysLeftStr = `${Math.abs(daysLeftNum)}d ago`;
                    }
                }

                const rawSym = (m.ticker || '').toUpperCase().replace('.NS', '');
                const cleanSym = this.escapeHtml(rawSym);
                const coName = this.escapeHtml(m.company_name || rawSym);
                const purpose = this.escapeHtml(m.purpose || 'General / Other Business');

                return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s ease;" onmouseenter="this.style.background='rgba(255,255,255,0.02)'" onmouseleave="this.style.background='transparent'">
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-size: 0.74rem; color: #f8fafc; font-weight: 700; white-space: nowrap;">
                        ${this.escapeHtml(m.meeting_date || '—')}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-size: 0.72rem; color: #94a3b8; white-space: nowrap;">
                        ${daysLeftStr}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-weight: 700;">
                        <a href="javascript:void(0)" onclick="app.openStockDetail ? app.openStockDetail('${cleanSym}.NS') : (window.stockDrawer ? window.stockDrawer.open('${cleanSym}.NS') : null)" style="color: #60a5fa; text-decoration: none; display: inline-flex; align-items: center; gap: 0.25rem;">
                            <span>${cleanSym}</span>
                        </a>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #cbd5e1;" title="${coName}">
                        ${coName}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        <span style="background: ${impactBg}; color: ${impactColor}; border: 1px solid ${impactColor}40; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.65rem; font-family: var(--font-mono); font-weight: 800;">
                            ${impactLabel}
                        </span>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; max-width: 320px; color: #e2e8f0;" title="${purpose}">
                        <div style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.35; font-size: 0.73rem;">
                            ${purpose}
                        </div>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: center; white-space: nowrap;">
                        <button type="button" onclick="app.openStockDetail ? app.openStockDetail('${cleanSym}.NS') : (window.stockDrawer ? window.stockDrawer.open('${cleanSym}.NS') : null)" class="btn btn-secondary btn-sm" style="font-size: 0.65rem; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.15);" title="Open Stock Forensics">
                            📊 Inspect
                        </button>
                    </td>
                </tr>`;
            }).join('');
        },

        async triggerMeetingsSync() {
            const btn = document.getElementById('btnMorningMeetingsSync');
            const origText = btn ? btn.innerHTML : '';
            if (btn) {
                btn.innerHTML = `<span class="spinner" style="display:inline-block;width:12px;height:12px;vertical-align:middle;margin-right:4px;"></span> Syncing Calendar...`;
                btn.disabled = true;
            }

            try {
                const res = await fetch(`${API_BASE}/api/v1/morning-setups/board-meetings/sync?days_forward=60`, { method: 'POST' });
                const json = await res.json();
                if (!res.ok) throw new Error(json.detail || 'Sync failed');

                this.showLiveSyncBadge('CALENDAR SYNCED');
                await this.loadMeetingsSummary();
                await this.loadMeetings(true);
            } catch (err) {
                alert(`Board Meetings Sync Notice: ${err.message}`);
            } finally {
                if (btn) {
                    btn.innerHTML = origText;
                    btn.disabled = false;
                }
            }
        },

        showLiveSyncBadge(txt) {
            const badge = document.getElementById('morningSetupsSyncStatus');
            if (badge) {
                badge.textContent = txt || 'SYNCED';
                badge.style.display = 'inline-block';
                setTimeout(() => {
                    badge.style.display = 'none';
                }, 4000);
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
        }
    };

    window.morningSetupsModule = morningSetupsModule;

    // Hook subtab switcher into global app namespace
    if (window.app) {
        window.app.switchMorningSubtab = function(subtab) {
            morningSetupsModule.switchSubtab(subtab);
        };
    }
})();
