// =========================================================================
// 🌅 Pre-Market Setups & Overnight SEBI Filings Radar Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const premarketModule = {
        premarketData: [],
        premarketSummary: null,
        premarketOutcomesData: [],
        premarketOutcomesSummary: null,
        activePremarketView: 'active',
        premarketLoading: false,

        async initPremarket() {
            await this.loadPremarketSetups();
        },

        switchPremarketView(view) {
            this.activePremarketView = view || 'active';
            const activeView = document.getElementById('premarketActiveView');
            const outcomesView = document.getElementById('premarketOutcomesView');
            const activeBtn = document.getElementById('pmViewActiveBtn');
            const outcomesBtn = document.getElementById('pmViewOutcomesBtn');
            const scanBtn = document.getElementById('pmScanBtn');
            const refreshBtn = document.getElementById('pmRefreshBtn');
            const windowSel = document.getElementById('pmWindowModeSelect');

            if (this.activePremarketView === 'active') {
                if (activeView) activeView.style.display = 'block';
                if (outcomesView) outcomesView.style.display = 'none';
                if (scanBtn) scanBtn.style.display = 'inline-flex';
                if (refreshBtn) refreshBtn.style.display = 'inline-flex';
                if (windowSel) windowSel.style.display = 'inline-block';

                if (activeBtn) {
                    activeBtn.style.background = 'rgba(249, 115, 22, 0.2)';
                    activeBtn.style.color = '#fb923c';
                    activeBtn.style.border = '1px solid rgba(249, 115, 22, 0.35)';
                    activeBtn.style.fontWeight = '700';
                }
                if (outcomesBtn) {
                    outcomesBtn.style.background = 'transparent';
                    outcomesBtn.style.color = '#a1a1aa';
                    outcomesBtn.style.border = '1px solid transparent';
                    outcomesBtn.style.fontWeight = '600';
                }
            } else {
                if (activeView) activeView.style.display = 'none';
                if (outcomesView) outcomesView.style.display = 'block';
                if (scanBtn) scanBtn.style.display = 'none';
                if (refreshBtn) refreshBtn.style.display = 'none';
                if (windowSel) windowSel.style.display = 'none';

                if (outcomesBtn) {
                    outcomesBtn.style.background = 'rgba(249, 115, 22, 0.2)';
                    outcomesBtn.style.color = '#fb923c';
                    outcomesBtn.style.border = '1px solid rgba(249, 115, 22, 0.35)';
                    outcomesBtn.style.fontWeight = '700';
                }
                if (activeBtn) {
                    activeBtn.style.background = 'transparent';
                    activeBtn.style.color = '#a1a1aa';
                    activeBtn.style.border = '1px solid transparent';
                    activeBtn.style.fontWeight = '600';
                }
                this.loadPremarketOutcomes();
            }
        },

        async loadPremarketSetups() {
            const windowMode = (document.getElementById('pmWindowModeSelect')?.value) || 'standard_6pm';
            const category = (document.getElementById('pmCategorySelect')?.value) || 'ALL';
            const direction = (document.getElementById('pmDirectionSelect')?.value) || 'ALL';
            const minImpact = parseFloat(document.getElementById('pmMinImpactSelect')?.value || '0');
            const search = (document.getElementById('pmSearchInput')?.value || '').trim();

            const tbody = document.getElementById('tblPremarketSetupsBody');
            if (tbody && (!this.premarketData || this.premarketData.length === 0)) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align:center;padding:2.5rem;color:#64748b;">
                            <div style="display:flex;flex-direction:column;align-items:center;gap:0.5rem;">
                                <span style="font-size:1.5rem;animation:spin 2s linear infinite;">🌅</span>
                                <span>Scanning overnight SEBI submissions &amp; after-hours filings...</span>
                            </div>
                        </td>
                    </tr>
                `;
            }

            this.premarketLoading = true;
            try {
                const params = new URLSearchParams({
                    window: windowMode,
                    category: category,
                    direction: direction,
                    min_impact: minImpact.toString(),
                    search: search,
                    limit: '150',
                    days: windowMode === 'all_recent' ? '7' : '3'
                });

                const res = await fetch(`${API_BASE}/api/v1/premarket/setups?${params.toString()}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                this.premarketData = data.items || [];
                this.premarketSummary = data.summary || {};

                this.renderPremarketKpis(this.premarketSummary, data.as_of);
                this.renderPremarketTable(this.premarketData);

                // Update sidebar badge
                const sidebarBadge = document.getElementById('sidebarPremarketCountBadge');
                if (sidebarBadge) {
                    const cnt = this.premarketSummary.total_overnight_setups || this.premarketData.length || 0;
                    if (cnt > 0) {
                        sidebarBadge.textContent = cnt;
                        sidebarBadge.style.display = 'inline-block';
                    } else {
                        sidebarBadge.style.display = 'none';
                    }
                }
            } catch (err) {
                console.error('[PREMARKET] Failed loading setups:', err);
                if (tbody) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="8" style="text-align:center;padding:2rem;color:#f87171;">
                                ⚠️ Failed to load pre-market setups: ${err.message}
                            </td>
                        </tr>
                    `;
                }
            } finally {
                this.premarketLoading = false;
            }
        },

        renderPremarketKpis(summary, asOf) {
            if (!summary) return;
            const elTotal = document.getElementById('pmStatTotal');
            const elHigh = document.getElementById('pmStatHighConv');
            const elBullish = document.getElementById('pmStatBullish');
            const elSebi = document.getElementById('pmStatSebi');
            const elBearish = document.getElementById('pmStatBearish');
            const elUpdated = document.getElementById('pmLastUpdated');

            if (elTotal) elTotal.textContent = summary.total_overnight_setups || 0;
            if (elHigh) elHigh.textContent = summary.high_conviction_gappers || 0;
            if (elBullish) elBullish.textContent = summary.bullish_setups_count || 0;
            if (elSebi) elSebi.textContent = summary.sebi_filings_count || 0;
            if (elBearish) elBearish.textContent = summary.bearish_risk_count || 0;
            if (elUpdated && asOf) elUpdated.textContent = asOf;
        },

        renderPremarketTable(items) {
            const tbody = document.getElementById('tblPremarketSetupsBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align:center;padding:2.5rem;color:#64748b;">
                            <div style="display:flex;flex-direction:column;align-items:center;gap:0.4rem;">
                                <span style="font-size:1.4rem;">📭</span>
                                <span style="font-weight:600;color:#94a3b8;">No overnight SEBI filings or pre-market setups found matching current filters.</span>
                                <span style="font-size:0.7rem;color:#64748b;">Try selecting "7-Day After-Hours Archive" or clicking "Scan Filings".</span>
                            </div>
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = items.map(s => {
                const ticker = s.ticker || '—';
                const cleanTicker = ticker.replace('.NS', '').replace('.BO', '');
                const stockName = s.stock_name || cleanTicker;
                const prevClose = s.prev_close ? `₹${Number(s.prev_close).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                
                // Gap representation
                const gapMin = s.est_gap_min_pct;
                const gapMax = s.est_gap_max_pct;
                let gapStr = '±0.0%';
                if (gapMin != null && gapMax != null) {
                    const sign = gapMin >= 0 ? '+' : '';
                    gapStr = `${sign}${gapMin.toFixed(1)}% to ${gapMax >= 0 ? '+' : ''}${gapMax.toFixed(1)}%`;
                }
                const gapCol = (s.direction === 'BULLISH') ? '#34d399' : ((s.direction === 'BEARISH') ? '#f87171' : '#94a3b8');

                // Timing & session phase badge
                let phaseBadge = '<span style="background:rgba(249,115,22,0.18);color:#fb923c;padding:0.08rem 0.35rem;border-radius:4px;font-size:0.60rem;font-weight:700;border:1px solid rgba(249,115,22,0.35);">🌙 After 6 PM</span>';
                if (s.session_phase === 'PRE_OPEN') {
                    phaseBadge = '<span style="background:rgba(56,189,248,0.18);color:#38bdf8;padding:0.08rem 0.35rem;border-radius:4px;font-size:0.60rem;font-weight:700;border:1px solid rgba(56,189,248,0.35);">🌅 Pre-Open</span>';
                } else if (s.session_phase === 'POST_CLOSE') {
                    phaseBadge = '<span style="background:rgba(168,85,247,0.18);color:#c084fc;padding:0.08rem 0.35rem;border-radius:4px;font-size:0.60rem;font-weight:700;border:1px solid rgba(168,85,247,0.35);">🌆 Post-Close</span>';
                }

                // Source badge color
                let srcCol = '#94a3b8';
                if (s.source_code === 'SEBI_FILING') srcCol = '#c084fc';
                else if (s.source_code === 'ORDER_WIN') srcCol = '#38bdf8';
                else if (s.source_code === 'REGULATORY_NOD') srcCol = '#34d399';
                else if (s.source_code === 'EARNINGS_BEAT') srcCol = '#fbbf24';

                // Conviction bar
                const imp = Math.round(s.impact_score || 50);
                const barCol = imp >= 80 ? '#34d399' : (imp >= 65 ? '#38bdf8' : '#a1a1aa');

                // Target levels
                const trg = s.premarket_trigger ? `₹${Number(s.premarket_trigger).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const t1 = s.target_1 ? `₹${Number(s.target_1).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const sl = s.stop_loss ? `₹${Number(s.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.15s ease;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                        <!-- 1. Stock / Ticker -->
                        <td style="padding:0.5rem 0.6rem;white-space:nowrap;">
                            <div style="display:flex;align-items:center;gap:0.4rem;">
                                <a href="/stock/${ticker}" target="_blank" style="font-weight:800;color:#f8fafc;font-family:var(--font-mono);font-size:0.78rem;text-decoration:none;" title="Open stock intelligence">
                                    ${cleanTicker}
                                </a>
                                <span style="font-size:0.60rem;color:#64748b;font-family:var(--font-mono);">.NS</span>
                            </div>
                            <div style="font-size:0.68rem;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;max-width:130px;" title="${stockName}">
                                ${stockName}
                            </div>
                        </td>

                        <!-- 2. Submission Time (IST) -->
                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="color:#ededed;font-size:0.72rem;font-weight:600;">${(s.published_at || '').substring(0, 16)}</div>
                            <div style="margin-top:0.15rem;">${phaseBadge}</div>
                        </td>

                        <!-- 3. Catalyst & Source -->
                        <td style="padding:0.5rem 0.6rem;white-space:nowrap;">
                            <div style="font-weight:700;color:${srcCol};font-size:0.72rem;">${s.source_badge || '📰 Announcement'}</div>
                            <div style="font-size:0.65rem;color:#64748b;margin-top:0.1rem;">${s.publisher || 'Exchange Feed'}</div>
                        </td>

                        <!-- 4. Headline & Summary -->
                        <td style="padding:0.5rem 0.6rem;">
                            <div style="font-weight:700;color:#f8fafc;font-size:0.74rem;line-height:1.25;margin-bottom:0.2rem;">
                                ${s.title}
                            </div>
                            ${s.summary ? `<div style="font-size:0.68rem;color:#94a3b8;line-height:1.2;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;" title="${s.summary}">${s.summary}</div>` : ''}
                        </td>

                        <!-- 5. Prev Close & Est Gap -->
                        <td style="padding:0.5rem 0.6rem;text-align:right;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="color:#cbd5e1;font-weight:700;font-size:0.74rem;">${prevClose}</div>
                            <div style="font-size:0.70rem;font-weight:800;color:${gapCol};margin-top:0.1rem;">
                                ${gapStr}
                            </div>
                        </td>

                        <!-- 6. Trigger & Targets -->
                        <td style="padding:0.5rem 0.6rem;text-align:right;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="font-size:0.70rem;color:#38bdf8;font-weight:700;">Trig: ${trg}</div>
                            <div style="font-size:0.65rem;color:#94a3b8;margin-top:0.05rem;">T1: <span style="color:#34d399;">${t1}</span> | SL: <span style="color:#f87171;">${sl}</span></div>
                        </td>

                        <!-- 7. Action & Conviction -->
                        <td style="padding:0.5rem 0.6rem;text-align:center;white-space:nowrap;">
                            <span style="display:inline-block;padding:0.15rem 0.45rem;border-radius:4px;font-size:0.65rem;font-weight:800;background:rgba(255,255,255,0.05);color:${s.action_color || '#ededed'};border:1px solid ${s.action_color ? s.action_color + '40' : 'rgba(255,255,255,0.1)'};">
                                ${s.action_badge}
                            </span>
                            <div style="display:flex;align-items:center;justify-content:center;gap:0.25rem;margin-top:0.25rem;">
                                <div style="width:40px;height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;">
                                    <div style="width:${imp}%;height:100%;background:${barCol};border-radius:2px;"></div>
                                </div>
                                <span style="font-size:0.62rem;font-weight:700;color:${barCol};font-family:var(--font-mono);">${imp}%</span>
                            </div>
                        </td>

                        <!-- 8. Actions -->
                        <td style="padding:0.5rem 0.6rem;text-align:right;white-space:nowrap;">
                            <div style="display:flex;align-items:center;justify-content:flex-end;gap:0.3rem;">
                                <button type="button" onclick="app.openConsensusModal('${ticker}')" class="btn-micro" style="padding:0.2rem 0.4rem;font-size:0.68rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);border-radius:4px;" title="Run AI Consensus">
                                    🧠 AI
                                </button>
                                <a href="/stock/${ticker}" target="_blank" class="btn-micro" style="padding:0.2rem 0.4rem;font-size:0.68rem;background:rgba(255,255,255,0.06);color:#ededed;border:1px solid rgba(255,255,255,0.15);border-radius:4px;text-decoration:none;" title="Stock Intelligence Details">
                                    📊 Intel
                                </a>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async loadPremarketOutcomes() {
            const tbody = document.getElementById('tblPremarketOutcomesLogBody');
            const matrixBody = document.getElementById('tblPremarketCategoryAccuracyBody');

            if (tbody && (!this.premarketOutcomesData || this.premarketOutcomesData.length === 0)) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:#64748b;">Evaluating historical pre-market setups against Day T market candles...</td></tr>';
            }

            try {
                const res = await fetch(`${API_BASE}/api/v1/premarket/outcomes?days=90&limit=150`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                this.premarketOutcomesData = data.items || [];
                this.premarketOutcomesSummary = data.track_record_summary || {};

                this.renderPremarketOutcomesKpis(this.premarketOutcomesSummary);
                this.renderPremarketAccuracyMatrix(data.accuracy_by_category || []);
                this.renderPremarketOutcomesTable(this.premarketOutcomesData);
            } catch (err) {
                console.error('[PREMARKET] Failed loading outcomes:', err);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2rem;color:#f87171;">⚠️ Failed loading previous setups: ${err.message}</td></tr>`;
                }
            }
        },

        renderPremarketOutcomesKpis(sum) {
            if (!sum) return;
            const elTot = document.getElementById('pmOutStatTotal');
            const elWin = document.getElementById('pmOutStatWinRate');
            const elWins = document.getElementById('pmOutStatWins');
            const elT1 = document.getElementById('pmOutStatT1Rate');
            const elT2 = document.getElementById('pmOutStatT2Rate');
            const elGap = document.getElementById('pmOutStatAvgGap');
            const elRet = document.getElementById('pmOutStatAvgReturn');

            if (elTot) elTot.textContent = sum.total_verified_setups || 0;
            if (elWin) elWin.textContent = `${sum.win_rate_pct || 0}%`;
            if (elWins) elWins.textContent = sum.total_wins || 0;
            if (elT1) elT1.textContent = `${sum.target_1_hit_rate_pct || 0}%`;
            if (elT2) elT2.textContent = `${sum.target_2_hit_rate_pct || 0}%`;
            if (elGap) {
                const g = sum.avg_realized_open_gap_pct || 0;
                elGap.textContent = `${g >= 0 ? '+' : ''}${g.toFixed(1)}%`;
            }
            if (elRet) {
                const r = sum.avg_day_return_pct || 0;
                elRet.textContent = `${r >= 0 ? '+' : ''}${r.toFixed(1)}%`;
                elRet.style.color = r >= 0 ? '#34d399' : '#f87171';
            }
        },

        renderPremarketAccuracyMatrix(categories) {
            const tbody = document.getElementById('tblPremarketCategoryAccuracyBody');
            if (!tbody) return;

            if (!categories || !categories.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:#64748b;">No historical categories recorded yet.</td></tr>';
                return;
            }

            tbody.innerHTML = categories.map(c => {
                const wr = c.win_rate_pct || 0;
                const wrCol = wr >= 70 ? '#34d399' : (wr >= 50 ? '#38bdf8' : '#fb923c');
                const gap = c.avg_open_gap_pct || 0;
                const ret = c.avg_day_return_pct || 0;

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                        <td style="padding:0.45rem 0.6rem;font-weight:700;color:#f8fafc;">${c.group_name}</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);">${c.total_setups}</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);font-weight:800;color:${wrCol};">${wr}% (${c.wins}/${c.total_setups})</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#c084fc;font-weight:700;">${c.target_1_hit_rate_pct}%</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#93c5fd;">${c.target_2_hit_rate_pct}%</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${gap >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${gap >= 0 ? '+' : ''}${gap}%</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${ret >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${ret >= 0 ? '+' : ''}${ret}%</td>
                    </tr>
                `;
            }).join('');
        },

        renderPremarketOutcomesTable(items) {
            const tbody = document.getElementById('tblPremarketOutcomesLogBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2.5rem;color:#64748b;">No verified historical setups in lookback window.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(s => {
                const ticker = s.ticker || '—';
                const cleanTicker = ticker.replace('.NS', '').replace('.BO', '');
                const stockName = s.stock_name || cleanTicker;
                const prevP = s.prev_close ? `₹${Number(s.prev_close).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const openP = s.actual_open ? `₹${Number(s.actual_open).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const highP = s.day_high ? `₹${Number(s.day_high).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                
                const gap = s.actual_gap_pct != null ? s.actual_gap_pct : 0;
                const gapCol = gap >= 0 ? '#34d399' : '#f87171';

                const ret = s.day_return_pct != null ? s.day_return_pct : 0;
                const retCol = ret >= 0 ? '#34d399' : '#f87171';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.15s ease;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                        <!-- 1. Stock / Ticker -->
                        <td style="padding:0.5rem 0.6rem;white-space:nowrap;">
                            <div style="display:flex;align-items:center;gap:0.4rem;">
                                <a href="/stock/${ticker}" target="_blank" style="font-weight:800;color:#f8fafc;font-family:var(--font-mono);font-size:0.78rem;text-decoration:none;">
                                    ${cleanTicker}
                                </a>
                                <span style="font-size:0.60rem;color:#64748b;font-family:var(--font-mono);">.NS</span>
                            </div>
                            <div style="font-size:0.68rem;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;max-width:130px;" title="${stockName}">
                                ${stockName}
                            </div>
                        </td>

                        <!-- 2. Session Date -->
                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="color:#ededed;font-size:0.74rem;font-weight:700;">${s.session_date || '—'}</div>
                            <div style="font-size:0.65rem;color:#94a3b8;">${(s.published_at || '').substring(11, 16)} IST</div>
                        </td>

                        <!-- 3. Catalyst & Source -->
                        <td style="padding:0.5rem 0.6rem;white-space:nowrap;">
                            <div style="font-weight:700;color:#c084fc;font-size:0.72rem;">${s.source_badge || '📰 Announcement'}</div>
                            <div style="font-size:0.65rem;color:#64748b;margin-top:0.1rem;">${s.category || 'General'}</div>
                        </td>

                        <!-- 4. Headline -->
                        <td style="padding:0.5rem 0.6rem;">
                            <div style="font-weight:600;color:#f8fafc;font-size:0.74rem;line-height:1.25;" title="${s.title}">
                                ${s.title}
                            </div>
                        </td>

                        <!-- 5. Prev Close -> Open -->
                        <td style="padding:0.5rem 0.6rem;text-align:right;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="color:#94a3b8;font-size:0.68rem;">Prev: ${prevP}</div>
                            <div style="color:#f8fafc;font-weight:800;font-size:0.74rem;">Open: ${openP}</div>
                        </td>

                        <!-- 6. Realized Open Gap % -->
                        <td style="padding:0.5rem 0.6rem;text-align:right;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="font-weight:800;font-size:0.76rem;color:${gapCol};">
                                ${gap >= 0 ? '+' : ''}${gap.toFixed(2)}%
                            </div>
                        </td>

                        <!-- 7. Day High & Return -->
                        <td style="padding:0.5rem 0.6rem;text-align:right;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="color:#93c5fd;font-size:0.70rem;">High: ${highP}</div>
                            <div style="font-weight:800;font-size:0.72rem;color:${retCol};">
                                Close: ${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%
                            </div>
                        </td>

                        <!-- 8. Outcome Status -->
                        <td style="padding:0.5rem 0.6rem;text-align:center;white-space:nowrap;">
                            <span style="display:inline-block;padding:0.18rem 0.5rem;border-radius:4px;font-size:0.66rem;font-weight:800;background:rgba(255,255,255,0.05);color:${s.outcome_color || '#ededed'};border:1px solid ${s.outcome_color ? s.outcome_color + '40' : 'rgba(255,255,255,0.1)'};">
                                ${s.outcome_badge || 'VERIFIED'}
                            </span>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        onPremarketFilterChange() {
            clearTimeout(this._filterTimer);
            this._filterTimer = setTimeout(() => {
                if (this.activePremarketView === 'active') {
                    this.loadPremarketSetups();
                } else {
                    this.loadPremarketOutcomes();
                }
            }, 250);
        },

        async scanPremarketNow() {
            const btn = document.getElementById('pmScanBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>⚡</span> Scanning...';
            }
            try {
                await fetch(`${API_BASE}/api/v1/premarket/scan`, { method: 'POST' });
                await this.loadPremarketSetups();
            } catch (err) {
                console.error('[PREMARKET] Scan failed:', err);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>⚡</span> Scan Filings';
                }
            }
        },

        async refreshPremarketQuotes() {
            const btn = document.getElementById('pmRefreshBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>🔄</span> Refreshing...';
            }
            try {
                await this.loadPremarketSetups();
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>🔄</span> Refresh';
                }
            }
        },

        exportPremarketCsv() {
            if (!this.premarketData || !this.premarketData.length) {
                alert('No pre-market setups to export.');
                return;
            }

            const headers = ['Ticker', 'Stock Name', 'Submission Time IST', 'Source', 'Category', 'Headline', 'Prev Close', 'Est Gap Min %', 'Est Gap Max %', 'Trigger Price', 'Target 1', 'Stop Loss', 'Conviction %', 'Action Badge'];
            const rows = this.premarketData.map(s => [
                s.ticker,
                `"${(s.stock_name || '').replace(/"/g, '""')}"`,
                `"${s.published_at || ''}"`,
                `"${(s.source_badge || '').replace(/"/g, '""')}"`,
                `"${(s.category || '').replace(/"/g, '""')}"`,
                `"${(s.title || '').replace(/"/g, '""')}"`,
                s.prev_close || '',
                s.est_gap_min_pct || '',
                s.est_gap_max_pct || '',
                s.premarket_trigger || '',
                s.target_1 || '',
                s.stop_loss || '',
                s.impact_score || '',
                `"${(s.action_badge || '').replace(/"/g, '""')}"`
            ]);

            const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `premarket_setups_${new Date().toISOString().substring(0, 10)}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    };

    // Export module
    window.PremarketModule = premarketModule;
    window.premarketModule = premarketModule;
    if (window.app) {
        Object.assign(window.app, premarketModule);
    }
})();
