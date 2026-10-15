// =========================================================================
// 🌅 Morning Setups: Block Deals & Board Meetings Radar Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const morningSetupsModule = {
        dealsData: [],
        dealsTechnicals: {},
        dealsSummary: null,
        meetingsData: [],
        meetingsTechnicals: {},
        meetingsSummary: null,
        activeSubtab: 'deals',
        groupBySymbol: false,
        dealsLoading: false,
        meetingsLoading: false,

        init() {
            const savedSubtab = localStorage.getItem('morning_setups_subtab') || 'deals';
            this.switchSubtab(savedSubtab, false);
            this.loadDealsSummary();
            this.loadDeals();
            this.loadMeetingsSummary();
            this.loadMeetings();
        },

        openInspect(ticker) {
            if (!ticker) return;
            const sym = ticker.endsWith('.NS') ? ticker : `${ticker}.NS`;
            if (window.app && typeof window.app.openStockDrawer === 'function') {
                window.app.openStockDrawer(sym);
            } else if (window.app && typeof window.app.openStockDetail === 'function') {
                window.app.openStockDetail(sym);
            } else {
                window.location.assign(`/stock/${encodeURIComponent(sym)}`);
            }
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

        toggleGroupBySymbol(checked) {
            this.groupBySymbol = Boolean(checked);
            this.loadDeals(true);
        },

        togglePrintsAccordion(idx) {
            const row = document.getElementById(`prints-accordion-${idx}`);
            const icon = document.getElementById(`prints-icon-${idx}`);
            if (!row) return;
            const isHidden = row.style.display === 'none';
            row.style.display = isHidden ? 'table-row' : 'none';
            if (icon) icon.textContent = isHidden ? '▼' : '▶';
        },

        renderReturnsBadges(tech) {
            if (!tech) return `<span style="color:#64748b;font-family:var(--font-mono);font-size:0.7rem;">--</span>`;
            const fmt = (v) => {
                if (v === null || v === undefined) return `<span style="color:#64748b;">--</span>`;
                const num = Number(v);
                const col = num > 0 ? '#34d399' : (num < 0 ? '#f87171' : '#94a3b8');
                const prefix = num > 0 ? '+' : '';
                return `<span style="color:${col};font-weight:600;">${prefix}${num.toFixed(1)}%</span>`;
            };
            return `
            <div style="display:flex;gap:0.35rem;align-items:center;font-family:var(--font-mono);font-size:0.68rem;white-space:nowrap;">
                <span title="1-Day Return">1D: ${fmt(tech.return_1d)}</span>
                <span style="color:rgba(255,255,255,0.18);">|</span>
                <span title="7-Day Return">7D: ${fmt(tech.return_7d)}</span>
                <span style="color:rgba(255,255,255,0.18);">|</span>
                <span title="30-Day Return">30D: ${fmt(tech.return_30d)}</span>
            </div>`;
        },

        renderTrendBadges(tech) {
            if (!tech) return `<span style="color:#64748b;font-family:var(--font-mono);font-size:0.7rem;">--</span>`;
            const fmtDma = (pct) => {
                if (pct === null || pct === undefined) return `<span style="color:#64748b;">--</span>`;
                const num = Number(pct);
                const col = num >= 0 ? '#34d399' : '#f87171';
                const arrow = num >= 0 ? '▲ +' : '▼ ';
                return `<span style="color:${col};font-weight:600;">${arrow}${num.toFixed(1)}%</span>`;
            };
            return `
            <div style="display:flex;flex-direction:column;gap:0.12rem;font-family:var(--font-mono);font-size:0.67rem;white-space:nowrap;">
                <div style="display:flex;align-items:center;gap:0.3rem;">
                    <span style="color:#94a3b8;font-size:0.62rem;">20 DMA</span>
                    ${fmtDma(tech.price_vs_dma20_pct)}
                </div>
                <div style="display:flex;align-items:center;gap:0.3rem;">
                    <span style="color:#94a3b8;font-size:0.62rem;">50 DMA</span>
                    ${fmtDma(tech.price_vs_dma50_pct)}
                </div>
            </div>`;
        },

        renderLivePriceCell(g) {
            const live = g.live_price;
            const liveFmt = (live !== null && live !== undefined)
                ? Number(live).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                : null;

            const isLive = Boolean(g.live_is_live);
            const dotColor = isLive ? '#34d399' : '#94a3b8';
            const dotTitle = isLive ? 'Live quote' : 'Settled / cached close';

            const vs = g.vs_deal_vwap_pct;
            let vsBadge = `<span style="color:#64748b;font-family:var(--font-mono);font-size:0.68rem;">--</span>`;
            if (vs !== null && vs !== undefined) {
                const v = Number(vs);
                const col = v > 0 ? '#34d399' : (v < 0 ? '#f87171' : '#94a3b8');
                const prefix = v > 0 ? '+' : (v < 0 ? '-' : '');
                vsBadge = `<span style="color:${col};font-weight:700;">${prefix}${Math.abs(v).toFixed(2)}%</span>`;
            }

            if (liveFmt === null) {
                return `<div style="font-family:var(--font-mono);font-size:0.68rem;color:#64748b;">Live --</div>`;
            }

            return `
            <div style="display:flex;flex-direction:column;gap:0.12rem;font-family:var(--font-mono);white-space:nowrap;">
                <div style="display:flex;align-items:center;gap:0.32rem;">
                    <span style="width:7px;height:7px;border-radius:50%;background:${dotColor};display:inline-block;flex-shrink:0;" title="${dotTitle}"></span>
                    <span style="color:#f8fafc;font-weight:700;font-size:0.72rem;">&#8377;${liveFmt}</span>
                </div>
                <div style="font-size:0.65rem;color:#94a3b8;">
                    vs VWAP: ${vsBadge}
                </div>
            </div>`;
        },

        renderUpcomingResultBadge(tech) {
            if (!tech || !tech.upcoming_result || !tech.upcoming_result.has_upcoming_result) {
                return '';
            }
            const info = tech.upcoming_result;
            const days = info.days_until;
            let badgeText = '📅 Result';
            if (days === 0) {
                badgeText = '📅 Result TODAY';
            } else if (days === 1) {
                badgeText = '📅 Result TOMORROW';
            } else if (days !== null && days !== undefined) {
                badgeText = `📅 Result in ${days}d`;
            }
            const meetingDate = info.meeting_date || '';
            const purpose = this.escapeHtml(info.purpose || 'Board meeting for financial results');
            const tooltip = `${purpose} (${meetingDate})`;

            return `
                <span title="${tooltip}" style="background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.62rem; font-family: var(--font-mono); font-weight: 700; white-space: nowrap; cursor: help; display: inline-flex; align-items: center; gap: 0.2rem;">
                    ${badgeText}
                </span>`;
        },

        renderStructureBadge(tech) {
            if (!tech || !tech.structure) {
                return `<span style="color:#64748b;font-family:var(--font-mono);font-size:0.7rem;">--</span>`;
            }
            const s = tech.structure;
            const posture = s.posture || 'CHANNEL';
            let pColor = '#94a3b8';
            let pBg = 'rgba(148, 163, 184, 0.12)';
            let pBorder = 'rgba(148, 163, 184, 0.25)';

            if (posture === 'BREAKOUT') {
                pColor = '#34d399';
                pBg = 'rgba(16, 185, 129, 0.2)';
                pBorder = 'rgba(16, 185, 129, 0.45)';
            } else if (posture === 'BREAKDOWN') {
                pColor = '#f87171';
                pBg = 'rgba(239, 68, 68, 0.2)';
                pBorder = 'rgba(239, 68, 68, 0.45)';
            } else if (posture === 'NEAR RESISTANCE') {
                pColor = '#fbbf24';
                pBg = 'rgba(245, 158, 11, 0.18)';
                pBorder = 'rgba(245, 158, 11, 0.35)';
            } else if (posture === 'NEAR SUPPORT') {
                pColor = '#38bdf8';
                pBg = 'rgba(56, 189, 248, 0.18)';
                pBorder = 'rgba(56, 189, 248, 0.35)';
            } else if (posture === 'CHANNEL UPPER') {
                pColor = '#a78bfa';
                pBg = 'rgba(167, 139, 250, 0.15)';
                pBorder = 'rgba(167, 139, 250, 0.3)';
            } else if (posture === 'CHANNEL LOWER') {
                pColor = '#94a3b8';
                pBg = 'rgba(148, 163, 184, 0.12)';
                pBorder = 'rgba(148, 163, 184, 0.25)';
            }

            const supFmt = s.support !== null ? Number(s.support).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '--';
            const resFmt = s.resistance !== null ? Number(s.resistance).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '--';
            const distSup = s.pct_from_support !== null ? `+${s.pct_from_support.toFixed(1)}%` : '--';
            const distRes = s.pct_to_resistance !== null ? `${s.pct_to_resistance.toFixed(1)}%` : '--';

            return `
            <div style="display:flex;flex-direction:column;gap:0.18rem;font-family:var(--font-mono);font-size:0.67rem;white-space:nowrap;">
                <div style="display:flex;align-items:center;gap:0.3rem;">
                    <span style="background:${pBg};color:${pColor};border:1px solid ${pBorder};padding:0.08rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:800;letter-spacing:0.02em;">
                        ${posture}
                    </span>
                    <span style="color:#64748b;font-size:0.62rem;" title="Channel position (${s.channel_position_pct}% of 20D range)">${s.channel_position_pct}% pos</span>
                </div>
                <div style="display:flex;align-items:center;gap:0.35rem;font-size:0.62rem;color:#94a3b8;">
                    <span title="20D Support: &#8377;${supFmt} (${distSup} away)">S: &#8377;${supFmt}</span>
                    <span style="color:rgba(255,255,255,0.18);">|</span>
                    <span title="20D Resistance: &#8377;${resFmt} (${distRes} away)">R: &#8377;${resFmt}</span>
                </div>
            </div>`;
        },

        // ---------------------------------------------------------------------
        // Block & Bulk Deals Handlers
        // ---------------------------------------------------------------------
        onDealsDateChange() {
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
            return {};
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
                tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; padding: 2rem; color: #94a3b8;"><div class="spinner" style="margin: 0 auto 0.5rem auto;"></div>Loading executed block &amp; bulk deals...</td></tr>`;
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
                if (this.groupBySymbol) {
                    params.append('group_by_symbol', 'true');
                }
                const upcomingOnly = document.getElementById('morningDealsUpcomingResultsCheckbox')?.checked;
                if (upcomingOnly) {
                    params.append('upcoming_results_only', 'true');
                }
                params.append('include_technicals', 'true');
                params.append('limit', '300');

                const res = await fetch(`${API_BASE}/api/v1/morning-setups/deals?${params.toString()}`);
                if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                const data = await res.json();
                this.dealsData = data.deals || [];
                this.dealsTechnicals = data.technicals || {};

                this.updateDealsHeaderRow();
                if (this.groupBySymbol) {
                    this.renderGroupedDealsTable(this.dealsData, this.dealsTechnicals);
                } else {
                    this.renderFlatDealsTable(this.dealsData, this.dealsTechnicals);
                }
            } catch (err) {
                console.error('Error loading morning deals:', err);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; padding: 2rem; color: #f87171;">Failed to load deals data: ${this.escapeHtml(err.message)}</td></tr>`;
                }
            } finally {
                this.dealsLoading = false;
            }
        },

        updateDealsHeaderRow() {
            const headerRow = document.getElementById('morningDealsTableHeaderRow');
            if (!headerRow) return;

            if (this.groupBySymbol) {
                headerRow.innerHTML = `
                    <th style="padding: 0.65rem 0.5rem; color: #94a3b8; font-weight: 700; width: 34px; text-align: center;"></th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Symbol</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Deals Breakdown</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">Net Flow (₹ Cr)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">Gross Buy / Sell</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">Total Qty</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">VWAP</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">Total Turnover</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Live Price vs VWAP</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Returns (1D / 7D / 30D)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Structure (20D)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Trend (20 / 50 DMA)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: center;">Actions</th>
                `;
            } else {
                headerRow.innerHTML = `
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Date</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Symbol</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Client / Fund Name</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Type</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Side</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">Quantity</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">Trade Price</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: right;">Value (₹ Cr)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Returns (1D / 7D / 30D)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Structure (20D)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700;">Trend (20 / 50 DMA)</th>
                    <th style="padding: 0.65rem 0.75rem; color: #94a3b8; font-weight: 700; text-align: center;">Actions</th>
                `;
            }
        },

        renderFlatDealsTable(deals, technicals) {
            const tbody = document.getElementById('morningDealsTableBody');
            if (!tbody) return;

            if (!deals || deals.length === 0) {
                tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; padding: 3rem 1rem; color: #64748b;"><div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📦</div><div>No executed block or bulk deals found matching the selected filters.</div><div style="font-size: 0.72rem; color: #475569; margin-top: 0.35rem;">Try relaxing minimum deal value (₹ Cr) or expanding the date range.</div></td></tr>`;
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

                const ticker = d.ticker || '';
                const rawSym = ticker.toUpperCase().replace('.NS', '');
                const cleanSym = this.escapeHtml(rawSym);
                const clientName = this.escapeHtml(d.client_name || '—');
                const tech = technicals ? (technicals[ticker] || technicals[`${rawSym}.NS`]) : null;

                return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s ease;" onmouseenter="this.style.background='rgba(255,255,255,0.02)'" onmouseleave="this.style.background='transparent'">
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-size: 0.72rem; color: #cbd5e1; white-space: nowrap;">
                        ${this.escapeHtml(d.deal_date || '—')}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-weight: 700;">
                        <div style="display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;">
                            <a href="javascript:void(0)" onclick="morningSetupsModule.openInspect('${cleanSym}.NS')" style="color: #60a5fa; text-decoration: none; display: inline-flex; align-items: center; gap: 0.25rem;">
                                <span>${cleanSym}</span>
                            </a>
                            ${this.renderUpcomingResultBadge(tech)}
                        </div>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #e2e8f0;" title="${clientName}">
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
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderReturnsBadges(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderStructureBadge(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderTrendBadges(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: center;">
                        <button type="button" onclick="morningSetupsModule.openInspect('${cleanSym}.NS')" class="btn btn-secondary btn-sm" style="font-size: 0.65rem; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.15);" title="Open Stock Forensics">
                            📊 Inspect
                        </button>
                    </td>
                </tr>`;
            }).join('');
        },

        renderGroupedDealsTable(groupedDeals, technicals) {
            const tbody = document.getElementById('morningDealsTableBody');
            if (!tbody) return;

            if (!groupedDeals || groupedDeals.length === 0) {
                tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; padding: 3rem 1rem; color: #64748b;"><div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🗂️</div><div>No grouped deal records found for the selected filters.</div></td></tr>`;
                return;
            }

            tbody.innerHTML = groupedDeals.map((g, idx) => {
                const ticker = g.ticker || '';
                const rawSym = ticker.toUpperCase().replace('.NS', '');
                const cleanSym = this.escapeHtml(rawSym);
                const tech = technicals ? (technicals[ticker] || technicals[`${rawSym}.NS`]) : null;

                const netCr = Number(g.net_value_cr || 0);
                const isNetBuy = netCr > 0;
                const netColor = isNetBuy ? '#34d399' : (netCr < 0 ? '#f87171' : '#94a3b8');
                const netPrefix = isNetBuy ? '+₹' : (netCr < 0 ? '-₹' : '₹');
                const netFmt = `${netPrefix}${Math.abs(netCr).toFixed(2)} Cr`;

                const grossBuyFmt = Number(g.gross_buy_cr || 0).toFixed(2);
                const grossSellFmt = Number(g.gross_sell_cr || 0).toFixed(2);
                const totalValFmt = Number(g.total_value_cr || 0).toFixed(2);
                const vwapFmt = Number(g.vwap || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                const totalQtyFmt = Number(g.total_quantity || 0).toLocaleString();

                const prints = g.prints || [];
                const blockCount = Number(g.block_count || 0);
                const bulkCount = Number(g.bulk_count || 0);

                // Nested sub-rows for prints
                const printsSubRows = prints.map((p) => {
                    const isPBuy = (p.transaction_type || '').toUpperCase() === 'BUY';
                    const pSideColor = isPBuy ? '#34d399' : '#f87171';
                    const isPBlock = (p.deal_type || '').toUpperCase() === 'BLOCK';
                    const pTypeColor = isPBlock ? '#38bdf8' : '#fbbf24';

                    return `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.71rem;">
                        <td style="padding: 0.35rem 0.6rem; color: #94a3b8; font-family: var(--font-mono);">${this.escapeHtml(p.deal_date || '—')}</td>
                        <td style="padding: 0.35rem 0.6rem; color: #e2e8f0; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(p.client_name || '—')}</td>
                        <td style="padding: 0.35rem 0.6rem; color: ${pTypeColor}; font-weight: 700; font-family: var(--font-mono);">${this.escapeHtml(p.deal_type || 'DEAL')}</td>
                        <td style="padding: 0.35rem 0.6rem; color: ${pSideColor}; font-weight: 800; font-family: var(--font-mono);">${this.escapeHtml(p.transaction_type || '—')}</td>
                        <td style="padding: 0.35rem 0.6rem; text-align: right; color: #94a3b8; font-family: var(--font-mono);">${Number(p.quantity || 0).toLocaleString()}</td>
                        <td style="padding: 0.35rem 0.6rem; text-align: right; color: #f8fafc; font-family: var(--font-mono);">₹${Number(p.trade_price || 0).toFixed(2)}</td>
                        <td style="padding: 0.35rem 0.6rem; text-align: right; color: ${pSideColor}; font-weight: 700; font-family: var(--font-mono);">₹${Number(p.value_cr || 0).toFixed(2)} Cr</td>
                    </tr>`;
                }).join('');

                return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.06); background: rgba(255,255,255,0.01); transition: background 0.15s ease;" onmouseenter="this.style.background='rgba(255,255,255,0.03)'" onmouseleave="this.style.background='rgba(255,255,255,0.01)'">
                    <td style="padding: 0.55rem 0.5rem; text-align: center;">
                        <button type="button" onclick="morningSetupsModule.togglePrintsAccordion(${idx})" style="background: transparent; border: none; color: #94a3b8; cursor: pointer; font-size: 0.72rem; padding: 2px;" title="Toggle deal prints">
                            <span id="prints-icon-${idx}">▶</span>
                        </button>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-weight: 700;">
                        <div style="display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;">
                            <a href="javascript:void(0)" onclick="morningSetupsModule.openInspect('${cleanSym}.NS')" style="color: #60a5fa; text-decoration: none; display: inline-flex; align-items: center; gap: 0.25rem;">
                                <span>${cleanSym}</span>
                            </a>
                            ${this.renderUpcomingResultBadge(tech)}
                        </div>
                        <div style="font-size: 0.65rem; color: #64748b; font-weight: 400; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${this.escapeHtml(g.security_name || cleanSym)}
                        </div>
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        <div style="font-size: 0.72rem; font-weight: 600; color: #f8fafc;">
                            ${g.total_deals} ${g.total_deals === 1 ? 'Deal' : 'Deals'}
                        </div>
                        <div style="font-size: 0.64rem; color: #94a3b8; font-family: var(--font-mono);">
                            ${blockCount > 0 ? `<span style="color: #38bdf8;">${blockCount} Block</span>` : ''}
                            ${blockCount > 0 && bulkCount > 0 ? ' · ' : ''}
                            ${bulkCount > 0 ? `<span style="color: #fbbf24;">${bulkCount} Bulk</span>` : ''}
                        </div>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); font-weight: 800; color: ${netColor};">
                        ${netFmt}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); font-size: 0.69rem;">
                        <div style="color: #34d399;">+₹${grossBuyFmt} Cr</div>
                        <div style="color: #f87171;">-₹${grossSellFmt} Cr</div>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); color: #94a3b8;">
                        ${totalQtyFmt}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); color: #f8fafc; font-weight: 600;">
                        ₹${vwapFmt}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: right; font-family: var(--font-mono); font-weight: 700; color: #e2e8f0;">
                        ₹${totalValFmt} Cr
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderLivePriceCell(g)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderReturnsBadges(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderStructureBadge(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderTrendBadges(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: center;">
                        <button type="button" onclick="morningSetupsModule.openInspect('${cleanSym}.NS')" class="btn btn-secondary btn-sm" style="font-size: 0.65rem; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.15);" title="Open Stock Forensics">
                            📊 Inspect
                        </button>
                    </td>
                </tr>
                <tr id="prints-accordion-${idx}" style="display: none; background: rgba(6, 6, 10, 0.7);">
                    <td colspan="13" style="padding: 0.6rem 1rem 0.8rem 2.2rem; border-bottom: 1px solid rgba(255,255,255,0.08);">
                        <div style="font-size: 0.67rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; margin-bottom: 0.35rem; font-family: var(--font-mono);">
                            Executed Prints for ${cleanSym} (${prints.length} Transactions)
                        </div>
                        <table style="width: 100%; max-width: 820px; border-collapse: collapse; background: #08080c; border: 1px solid rgba(255,255,255,0.06); border-radius: 4px;">
                            <thead>
                                <tr style="background: #0f1016; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 0.67rem; color: #94a3b8; font-family: var(--font-mono);">
                                    <th style="padding: 0.3rem 0.6rem; text-align: left;">Date</th>
                                    <th style="padding: 0.3rem 0.6rem; text-align: left;">Client Name</th>
                                    <th style="padding: 0.3rem 0.6rem; text-align: left;">Type</th>
                                    <th style="padding: 0.3rem 0.6rem; text-align: left;">Side</th>
                                    <th style="padding: 0.3rem 0.6rem; text-align: right;">Quantity</th>
                                    <th style="padding: 0.3rem 0.6rem; text-align: right;">Price</th>
                                    <th style="padding: 0.3rem 0.6rem; text-align: right;">Value</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${printsSubRows}
                            </tbody>
                        </table>
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
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: #94a3b8;"><div class="spinner" style="margin: 0 auto 0.5rem auto;"></div>Loading upcoming corporate board meetings...</td></tr>`;
            }

            try {
                const search = (document.getElementById('morningMeetingsSearchInput')?.value || '').trim();
                const impact = document.getElementById('morningMeetingsImpactSelect')?.value || '';
                const horizon = document.getElementById('morningMeetingsHorizonSelect')?.value || '30';

                const params = new URLSearchParams();
                if (search) params.append('ticker', search);
                if (impact) params.append('impact_tier', impact);
                if (horizon) params.append('days_ahead', horizon);
                params.append('include_technicals', 'true');
                params.append('limit', '300');

                const res = await fetch(`${API_BASE}/api/v1/morning-setups/board-meetings?${params.toString()}`);
                if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                const data = await res.json();
                this.meetingsData = data.meetings || [];
                this.meetingsTechnicals = data.technicals || {};
                this.renderMeetingsTable(this.meetingsData, this.meetingsTechnicals);
            } catch (err) {
                console.error('Error loading board meetings:', err);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: #f87171;">Failed to load board meetings: ${this.escapeHtml(err.message)}</td></tr>`;
                }
            } finally {
                this.meetingsLoading = false;
            }
        },

        renderMeetingsTable(meetings, technicals) {
            const tbody = document.getElementById('morningMeetingsTableBody');
            if (!tbody) return;

            if (!meetings || meetings.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 3rem 1rem; color: #64748b;"><div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📅</div><div>No scheduled board meetings found for the selected impact tier and horizon.</div><div style="font-size: 0.72rem; color: #475569; margin-top: 0.35rem;">Try selecting "All Impact Tiers" or expanding the horizon to 45D / 90D.</div></td></tr>`;
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
                if (m.meeting_date) {
                    const mDate = new Date(m.meeting_date);
                    mDate.setHours(0, 0, 0, 0);
                    const diffTime = mDate.getTime() - today.getTime();
                    const daysLeftNum = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
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

                const ticker = m.ticker || '';
                const rawSym = ticker.toUpperCase().replace('.NS', '');
                const cleanSym = this.escapeHtml(rawSym);
                const coName = this.escapeHtml(m.company_name || rawSym);
                const purpose = this.escapeHtml(m.purpose || 'General / Other Business');
                const tech = technicals ? technicals[ticker] : null;

                return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s ease;" onmouseenter="this.style.background='rgba(255,255,255,0.02)'" onmouseleave="this.style.background='transparent'">
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-size: 0.74rem; color: #f8fafc; font-weight: 700; white-space: nowrap;">
                        ${this.escapeHtml(m.meeting_date || '—')}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-size: 0.72rem; color: #94a3b8; white-space: nowrap;">
                        ${daysLeftStr}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; font-family: var(--font-mono); font-weight: 700;">
                        <a href="javascript:void(0)" onclick="morningSetupsModule.openInspect('${cleanSym}.NS')" style="color: #60a5fa; text-decoration: none; display: inline-flex; align-items: center; gap: 0.25rem;">
                            <span>${cleanSym}</span>
                        </a>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #cbd5e1;" title="${coName}">
                        ${coName}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        <span style="background: ${impactBg}; color: ${impactColor}; border: 1px solid ${impactColor}40; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.65rem; font-family: var(--font-mono); font-weight: 800;">
                            ${impactLabel}
                        </span>
                    </td>
                    <td style="padding: 0.55rem 0.75rem; max-width: 280px; color: #e2e8f0;" title="${purpose}">
                        <div style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.35; font-size: 0.73rem;">
                            ${purpose}
                        </div>
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderReturnsBadges(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem;">
                        ${this.renderTrendBadges(tech)}
                    </td>
                    <td style="padding: 0.55rem 0.75rem; text-align: center; white-space: nowrap;">
                        <button type="button" onclick="morningSetupsModule.openInspect('${cleanSym}.NS')" class="btn btn-secondary btn-sm" style="font-size: 0.65rem; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.15);" title="Open Stock Forensics">
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
