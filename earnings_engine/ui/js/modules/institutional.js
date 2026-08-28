// =========================================================================
// 🏛️ Institutional Flows & Smart Money Hub Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const institutionalModule = {
        institutionalData: {
            accumulating: [],
            distributing: [],
            funds: []
        },
        _currentInvestorFilter: 'ALL',
        _selectedTicker: 'ALLCARGO.NS',
        _splitCollapsed: false,
        _institutionalLoaded: false,

        switchInstitutionalPage(page) {
            if (!page || (page !== 'equities' && page !== 'top-additions' && page !== 'investors')) page = 'equities';
            try {
                localStorage.setItem('ee_institutional_subpage', page);
                if (window.location.hash && window.location.hash.includes('institutional')) {
                    const newHash = page === 'investors' ? '#institutional/investors' : (page === 'top-additions' ? '#institutional/top-additions' : '#institutional');
                    if (window.location.hash !== newHash) {
                        try { history.replaceState(null, '', newHash); } catch (e) { window.location.hash = newHash; }
                    }
                }
            } catch (e) {}

            const pages = ['equities', 'top-additions', 'investors'];
            pages.forEach(p => {
                const el = document.getElementById('instPage-' + p);
                if (el) el.style.display = (p === page) ? 'block' : 'none';

                const btn = document.getElementById('btnInstPage-' + p);
                if (btn) {
                    if (p === page) {
                        btn.style.background = '#1e293b';
                        btn.style.color = '#38bdf8';
                        btn.style.borderColor = 'rgba(56,189,248,0.4)';
                        btn.style.fontWeight = '700';
                    } else {
                        btn.style.background = 'transparent';
                        btn.style.color = '#94a3b8';
                        btn.style.borderColor = 'transparent';
                        btn.style.fontWeight = '500';
                    }
                }
            });
        },

        switchEquitiesFlowView(flow) {
            const accEl = document.getElementById('instEquitiesFlow-accumulating');
            const distEl = document.getElementById('instEquitiesFlow-distributing');
            const btnAcc = document.getElementById('btnInstFlowToggle-acc');
            const btnDist = document.getElementById('btnInstFlowToggle-dist');

            if (flow === 'accumulating') {
                if (accEl) accEl.style.display = 'block';
                if (distEl) distEl.style.display = 'none';
                if (btnAcc) {
                    btnAcc.style.background = '#1e293b';
                    btnAcc.style.color = '#34d399';
                    btnAcc.style.borderColor = 'rgba(16,185,129,0.4)';
                    btnAcc.style.fontWeight = '700';
                }
                if (btnDist) {
                    btnDist.style.background = 'transparent';
                    btnDist.style.color = '#94a3b8';
                    btnDist.style.borderColor = 'transparent';
                    btnDist.style.fontWeight = '500';
                }
            } else {
                if (accEl) accEl.style.display = 'none';
                if (distEl) distEl.style.display = 'block';
                if (btnDist) {
                    btnDist.style.background = '#180d14';
                    btnDist.style.color = '#f87171';
                    btnDist.style.borderColor = 'rgba(239,68,68,0.4)';
                    btnDist.style.fontWeight = '700';
                }
                if (btnAcc) {
                    btnAcc.style.background = 'transparent';
                    btnAcc.style.color = '#94a3b8';
                    btnAcc.style.borderColor = 'transparent';
                    btnAcc.style.fontWeight = '500';
                }
            }
        },

        toggleInstitutionalSplitLayout() {
            const grid = document.getElementById('instEquitiesSplitGrid');
            const rightPanel = document.getElementById('instSplitRight');
            const btn = document.getElementById('btnToggleInstSplit');
            if (!grid || !rightPanel) return;

            this._splitCollapsed = !this._splitCollapsed;
            if (this._splitCollapsed) {
                grid.style.gridTemplateColumns = '1fr';
                rightPanel.style.display = 'none';
                if (btn) btn.innerHTML = '▶ Show Drilldown';
            } else {
                grid.style.gridTemplateColumns = 'minmax(0, 1.05fr) minmax(0, 0.95fr)';
                rightPanel.style.display = 'block';
                if (btn) btn.innerHTML = '◫ 50-50 Split';
            }
        },

        _accLimit: 25,
        _distLimit: 20,
        _fundsLimit: 50,
        _loadingMoreAcc: false,
        _loadingMoreDist: false,
        _loadingMoreFunds: false,

        async loadInstitutionalData() {
            // Restore active sub-page state on load / refresh
            const savedSub = localStorage.getItem('ee_institutional_subpage') || 'equities';
            this.switchInstitutionalPage(savedSub);

            this._accLimit = 25;
            this._distLimit = 20;
            this._fundsLimit = 50;

            try {
                const [resAcc, resDist, resFunds, resTop] = await Promise.all([
                    fetch(API_BASE + `/api/v1/institutional/accumulating?limit=${this._accLimit}`),
                    fetch(API_BASE + `/api/v1/institutional/distributing?limit=${this._distLimit}`),
                    fetch(API_BASE + `/api/v1/institutional/funds?limit=${this._fundsLimit}`),
                    fetch(API_BASE + `/api/v1/institutional/top-additions?min_delta=3.0`),
                ]);

                const loadedAt = new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', day: '2-digit', month: 'short', year: 'numeric' });
                this._dataFreshness = loadedAt;

                if (resAcc.ok) {
                    const accData = await resAcc.json();
                    this.institutionalData.accumulating = accData.items || [];
                    this.renderInstitutionalAccumulatingTable(this.institutionalData.accumulating);
                }

                if (resDist.ok) {
                    const distData = await resDist.json();
                    this.institutionalData.distributing = distData.items || [];
                    this.renderInstitutionalDistributingTable(this.institutionalData.distributing);
                }

                if (resFunds.ok) {
                    const fundsData = await resFunds.json();
                    this.institutionalData.funds = fundsData.funds || [];
                    this.renderInstitutionalFundsTable(this.institutionalData.funds);
                }

                if (resTop.ok) {
                    const topData = await resTop.json();
                    this.institutionalData.topAdditions = topData;
                    this.renderInstitutionalTopAdditions(topData);
                }

                // Render freshness badge on all pages
                this._renderFreshnessBadges(loadedAt);

                // Initial inspect ALLCARGO as default benchmark drilldown
                this.searchInstitutionalStock('ALLCARGO.NS');

            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading institutional flows:', e);
            }
        },

        _renderFreshnessBadges(ts) {
            const badgeHtml = `<span style="font-size:0.62rem;color:#64748b;font-family:var(--font-mono);background:rgba(255,255,255,0.03);padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(255,255,255,0.06);">📊 Data as of ${ts} IST</span>`;
            ['instFreshnessBadge-equities', 'instFreshnessBadge-topadditions', 'instFreshnessBadge-investors'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.innerHTML = badgeHtml;
            });
        },

        renderInstitutionalTopAdditions(data) {
            if (!data) return;
            const latest = data.latest_additions || [];
            const hist = data.historical_additions || [];

            // Update KPI cards with dynamic data
            const countEl = document.getElementById('kpiTopAdditionsCount');
            if (countEl) countEl.innerText = `${latest.length} Setups`;

            const leaderEl = document.getElementById('kpiTopAdditionLeader');
            const leaderSubEl = document.getElementById('kpiTopAdditionLeaderSub');
            if (leaderEl && latest.length > 0) {
                const top1 = latest[0];
                leaderEl.innerText = `+${top1.inst_addition_pct}% (${top1.ticker.replace('.NS', '')})`;
                if (leaderSubEl) leaderSubEl.innerText = `FII +${top1.fii_delta_pct}% · DII +${top1.dii_delta_pct}%`;
            }

            const inflowEl = document.getElementById('kpiTopAdditionInflow');
            const inflowSubEl = document.getElementById('kpiTopAdditionInflowSub');
            if (inflowEl) {
                const totalInflow = latest.reduce((acc, curr) => acc + (curr.net_flow_cr > 0 ? curr.net_flow_cr : 0), 0);
                inflowEl.innerText = `+₹${Math.round(totalInflow).toLocaleString('en-IN')} Cr`;
                if (inflowSubEl && latest.length > 0) {
                    const topInflows = latest.filter(x => x.net_flow_cr > 0).sort((a,b) => b.net_flow_cr - a.net_flow_cr).slice(0, 2);
                    inflowSubEl.innerText = topInflows.length ? `Led by ${topInflows.map(x => x.ticker.replace('.NS','')).join(' & ')}` : 'Net institutional inflows';
                }
            }

            const histCountEl = document.getElementById('kpiHistoricalMegaCount');
            const histSubEl = document.getElementById('kpiHistoricalMegaSub');
            if (histCountEl) histCountEl.innerText = `${hist.length} Surges`;
            if (histSubEl && hist.length > 0) {
                const topHist = hist.slice(0, 2);
                histSubEl.innerText = topHist.map(x => `${x.ticker.replace('.NS','')} (+${x.inst_addition_pct}%)`).join(', ');
            }

            // 1. Render Latest Top Additions Table
            const tbodyLatest = document.getElementById('instTopAdditionsTableBody');
            if (tbodyLatest) {
                if (!latest.length) {
                    tbodyLatest.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#64748b;">No stocks with >3% institutional addition found in the latest quarter.</td></tr>';
                } else {
                    tbodyLatest.innerHTML = latest.map(it => {
                        const scoreCol = it.accumulation_score >= 75 ? '#34d399' : (it.accumulation_score >= 50 ? '#38bdf8' : '#fbbf24');
                        const ret7dStr = it.return_7d_pct != null ? (it.return_7d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_7d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_7d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                        const ret30Str = it.return_30d_pct != null ? (it.return_30d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_30d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_30d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                        const ret1yStr = it.return_1y_pct != null ? (it.return_1y_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_1y_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_1y_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                        const netCol = it.net_flow_cr >= 0 ? '#34d399' : '#f87171';
                        const netSign = it.net_flow_cr >= 0 ? '+' : '-';
                        const netStr = `${netSign}₹${Math.abs(Math.round(it.net_flow_cr || 0)).toLocaleString('en-IN')}`;

                        const newFiiBadge = it.is_new_fii_entry ? `<span style="font-size:0.6rem;padding:0.08rem 0.32rem;border-radius:4px;background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-weight:700;margin-left:0.3rem;">New FII</span>` : '';
                        const newDiiBadge = it.is_new_dii_entry ? `<span style="font-size:0.6rem;padding:0.08rem 0.32rem;border-radius:4px;background:rgba(52,211,153,0.2);color:#34d399;border:1px solid rgba(52,211,153,0.35);font-weight:700;margin-left:0.3rem;">New DII</span>` : '';

                        const compName = (it.company_name && it.company_name !== it.ticker && !it.company_name.endsWith('.NS')) ? it.company_name : it.ticker.replace('.NS', '');

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.05);cursor:pointer;transition:background 0.12s;" onclick="app.searchInstitutionalStock('${it.ticker}'); app.switchInstitutionalPage('equities');" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                                <td style="padding:0.55rem 0.75rem;">
                                    <div style="font-family:var(--font-mono);font-weight:700;color:#38bdf8;display:flex;align-items:center;">
                                        ${it.ticker.replace('.NS', '')} ${newFiiBadge}${newDiiBadge}
                                    </div>
                                    <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.1rem;">${compName}</div>
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#34d399;font-size:0.82rem;">
                                    +${it.inst_addition_pct}%
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-size:0.7rem;color:#cbd5e1;">
                                    FII: <strong style="color:#38bdf8;">+${it.fii_delta_pct}%</strong> · DII: <strong style="color:#34d399;">+${it.dii_delta_pct}%</strong>
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">
                                    ${it.total_institutional_stake_pct}%
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);">
                                    <span style="color:${scoreCol};font-weight:700;">${it.accumulation_score}</span>
                                    <span style="font-size:0.65rem;color:#94a3b8;margin-left:0.25rem;">${(it.verdict || '').split(' ')[0] || ''}</span>
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:${netCol};">
                                    ${netStr} Cr
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-size:0.7rem;">
                                    <span style="color:#34d399;font-weight:700;">+${it.funds_accumulating_count}</span> / <span style="color:#f87171;font-weight:700;">-${it.funds_selling_count}</span>
                                </td>
                                <td style="padding:0.55rem 0.4rem;font-family:var(--font-mono);font-size:0.68rem;">
                                    <div>${ret7dStr}</div>
                                    <div style="margin-top:0.1rem;">${ret30Str}</div>
                                    <div style="margin-top:0.1rem;">${ret1yStr}</div>
                                </td>
                                <td style="padding:0.55rem 0.5rem;text-align:center;">
                                    <button type="button" onclick="event.stopPropagation(); app.searchInstitutionalStock('${it.ticker}'); app.switchInstitutionalPage('equities');" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.2rem 0.45rem;background:rgba(56,189,248,0.1);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);" title="Inspect ${it.ticker}">🔍 Drilldown</button>
                                </td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            // 2. Render Historical Mega Additions Table
            const tbodyHist = document.getElementById('instHistoricalAdditionsTableBody');
            if (tbodyHist) {
                if (!hist.length) {
                    tbodyHist.innerHTML = '<tr><td colspan="8" style="padding:2rem;text-align:center;color:#64748b;">No historical surges found.</td></tr>';
                } else {
                    tbodyHist.innerHTML = hist.map(it => {
                        const scoreCol = it.accumulation_score >= 75 ? '#34d399' : (it.accumulation_score >= 50 ? '#38bdf8' : '#fbbf24');
                        const ret30Str = it.return_30d_pct != null ? (it.return_30d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_30d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_30d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.05);cursor:pointer;transition:background 0.12s;" onclick="app.searchInstitutionalStock('${it.ticker}'); app.switchInstitutionalPage('equities');" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                                <td style="padding:0.55rem 0.75rem;">
                                    <div style="font-family:var(--font-mono);font-weight:700;color:#fbbf24;">
                                        ${it.ticker.replace('.NS', '')}
                                    </div>
                                    <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.1rem;">${it.company_name}</div>
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-size:0.72rem;color:#94a3b8;">
                                    ${it.quarter_comparison}
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#34d399;font-size:0.82rem;">
                                    +${it.inst_addition_pct}%
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-size:0.7rem;color:#cbd5e1;">
                                    FII: <strong style="color:#38bdf8;">+${it.fii_delta_pct}%</strong> · DII: <strong style="color:#34d399;">+${it.dii_delta_pct}%</strong>
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-size:0.72rem;color:#f8fafc;">
                                    <span style="color:#94a3b8;">${it.historical_stake_pct}%</span> → <strong style="color:#38bdf8;">${it.current_total_stake_pct}%</strong>
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:${scoreCol};">
                                    ${it.accumulation_score}
                                </td>
                                <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-size:0.72rem;">
                                    ${ret30Str}
                                </td>
                                <td style="padding:0.55rem 0.5rem;text-align:center;">
                                    <button type="button" onclick="event.stopPropagation(); app.searchInstitutionalStock('${it.ticker}'); app.switchInstitutionalPage('equities');" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.2rem 0.45rem;background:rgba(251,191,36,0.1);color:#fbbf24;border:1px solid rgba(251,191,36,0.3);" title="Inspect ${it.ticker}">🔍 Drilldown</button>
                                </td>
                            </tr>
                        `;
                    }).join('');
                }
            }
        },

        async loadMoreInstitutionalEquities(type) {
            const isAcc = type === 'accumulating';
            if (isAcc && this._loadingMoreAcc) return;
            if (!isAcc && this._loadingMoreDist) return;

            const btnId = isAcc ? 'btnInstLoadMoreAcc' : 'btnInstLoadMoreDist';
            const btn = document.getElementById(btnId);
            const originalBtnHtml = isAcc 
                ? '<span>📥</span> Load More Accumulating (+25)'
                : '<span>📥</span> Load More Distributing (+25)';

            if (isAcc) {
                this._loadingMoreAcc = true;
                this._accLimit = (this._accLimit || 25) + 25;
            } else {
                this._loadingMoreDist = true;
                this._distLimit = (this._distLimit || 20) + 25;
            }

            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<div style="display:inline-block;animation:spin 1s linear infinite;margin-right:0.3rem;">⏳</div> Loading...';
            }

            try {
                const targetLimit = isAcc ? this._accLimit : this._distLimit;
                const endpoint = isAcc 
                    ? `/api/v1/institutional/accumulating?limit=${targetLimit}`
                    : `/api/v1/institutional/distributing?limit=${targetLimit}`;
                
                const prevCount = isAcc ? (this.institutionalData.accumulating || []).length : (this.institutionalData.distributing || []).length;
                const res = await fetch(API_BASE + endpoint);
                if (res.ok) {
                    const data = await res.json();
                    const items = data.items || [];
                    if (isAcc) {
                        this.institutionalData.accumulating = items;
                        this.renderInstitutionalAccumulatingTable(items);
                    } else {
                        this.institutionalData.distributing = items;
                        this.renderInstitutionalDistributingTable(items);
                    }

                    if (btn) {
                        if (items.length <= prevCount || items.length < targetLimit) {
                            btn.disabled = true;
                            btn.style.opacity = '0.6';
                            btn.innerHTML = `✓ All Setups Loaded (${items.length})`;
                        } else {
                            btn.disabled = false;
                            btn.innerHTML = originalBtnHtml;
                        }
                    }
                } else {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalBtnHtml;
                    }
                }
            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading more equities:', e);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalBtnHtml;
                }
            } finally {
                if (isAcc) this._loadingMoreAcc = false;
                else this._loadingMoreDist = false;
            }
        },

        async loadMoreInstitutionalFunds() {
            if (this._loadingMoreFunds) return;
            const btn = document.getElementById('btnInstLoadMoreFunds');
            const originalBtnHtml = '<span>📥</span> Load More Funds & Whales (+25)';

            this._loadingMoreFunds = true;
            this._fundsLimit = (this._fundsLimit || 50) + 25;

            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<div style="display:inline-block;animation:spin 1s linear infinite;margin-right:0.3rem;">⏳</div> Loading...';
            }

            try {
                const prevCount = (this.institutionalData.funds || []).length;
                const res = await fetch(API_BASE + `/api/v1/institutional/funds?limit=${this._fundsLimit}`);
                if (res.ok) {
                    const data = await res.json();
                    const allFunds = data.funds || [];
                    this.institutionalData.funds = allFunds;

                    // Apply active category filter
                    if (this._currentInvestorFilter === 'ALL') {
                        this.renderInstitutionalFundsTable(allFunds);
                    } else {
                        const filtered = allFunds.filter(f => (f.fund_type || '').toLowerCase().includes(this._currentInvestorFilter.toLowerCase()));
                        this.renderInstitutionalFundsTable(filtered);
                    }

                    if (btn) {
                        if (allFunds.length <= prevCount || allFunds.length < this._fundsLimit) {
                            btn.disabled = true;
                            btn.style.opacity = '0.6';
                            btn.innerHTML = `✓ All Funds Loaded (${allFunds.length})`;
                        } else {
                            btn.disabled = false;
                            btn.innerHTML = originalBtnHtml;
                        }
                    }
                } else {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalBtnHtml;
                    }
                }
            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading more funds:', e);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalBtnHtml;
                }
            } finally {
                this._loadingMoreFunds = false;
            }
        },

        filterInvestors(category) {
            this._currentInvestorFilter = category;
            const catMap = {
                'ALL': 'btnInvCat-ALL',
                'Mutual Fund': 'btnInvCat-MF',
                'Super Investor': 'btnInvCat-SI',
                'Foreign': 'btnInvCat-FII'
            };

            Object.entries(catMap).forEach(([k, btnId]) => {
                const btn = document.getElementById(btnId);
                if (btn) {
                    if (k === category) {
                        btn.style.background = '#1e293b';
                        btn.style.color = '#38bdf8';
                        btn.style.borderColor = 'rgba(56,189,248,0.4)';
                        btn.style.fontWeight = '700';
                    } else {
                        btn.style.background = 'transparent';
                        btn.style.color = '#94a3b8';
                        btn.style.borderColor = 'rgba(255,255,255,0.1)';
                        btn.style.fontWeight = '500';
                    }
                }
            });

            const allFunds = this.institutionalData.funds || [];
            if (category === 'ALL') {
                this.renderInstitutionalFundsTable(allFunds);
            } else {
                const filtered = allFunds.filter(f => (f.fund_type || '').toLowerCase().includes(category.toLowerCase()));
                this.renderInstitutionalFundsTable(filtered);
            }
        },

        renderInstitutionalAccumulatingTable(items) {
            const tbody = document.getElementById('instAccumulatingTableBody');
            const countBadge = document.getElementById('instAccCountBadge');
            if (countBadge) {
                countBadge.innerText = `Showing ${items ? items.length : 0} setups`;
            }
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No high-accumulation stocks found.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const scoreCol = it.accumulation_score >= 75 ? '#34d399' : '#60a5fa';
                const ret7dStr = it.return_7d_pct != null ? (it.return_7d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_7d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_7d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                const ret30dStr = it.return_30d_pct != null ? (it.return_30d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_30d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_30d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                const instStakeStr = (it.total_institutional_stake_pct != null && it.total_institutional_stake_pct > 0) ? `${it.total_institutional_stake_pct}%` : ((it.total_institutional_stake != null && it.total_institutional_stake > 0) ? `${it.total_institutional_stake}%` : '—');
                const isSelected = this._selectedTicker === it.ticker;
                const rowBg = isSelected ? 'rgba(56,189,248,0.12)' : 'transparent';

                const newFiiBadge = it.is_new_fii_entry ? `<span style="font-size:0.6rem;padding:0.08rem 0.32rem;border-radius:4px;background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-weight:700;margin-left:0.3rem;">New FII</span>` : '';
                const newDiiBadge = it.is_new_dii_entry ? `<span style="font-size:0.6rem;padding:0.08rem 0.32rem;border-radius:4px;background:rgba(52,211,153,0.2);color:#34d399;border:1px solid rgba(52,211,153,0.35);font-weight:700;margin-left:0.3rem;">New DII</span>` : '';

                const compName = (it.company_name && it.company_name !== it.ticker && !it.company_name.endsWith('.NS')) ? it.company_name : '';
                const netFlowCr = it.net_flow_cr || 0;
                const netFlowCol = netFlowCr >= 0 ? '#34d399' : '#f87171';
                const netFlowSign = netFlowCr >= 0 ? '+' : '';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:${rowBg};cursor:pointer;transition:background 0.12s;" onclick="app.searchInstitutionalStock('${it.ticker}')" onmouseover="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='rgba(255,255,255,0.03)'" onmouseout="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='transparent'">
                        <td style="padding:0.45rem 0.6rem;font-family:var(--font-mono);font-weight:700;">
                            <span style="color:#38bdf8;">${it.ticker.replace('.NS', '')}</span>
                            ${newFiiBadge}${newDiiBadge}
                            ${compName ? `<div style="font-size:0.6rem;color:#64748b;font-weight:400;font-family:var(--font-sans);margin-top:0.08rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px;">${compName}</div>` : ''}
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:${scoreCol};">${it.accumulation_score}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret7dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret30dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${it.funds_accumulating_count}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:${netFlowCol};font-weight:700;font-size:0.68rem;">${netFlowSign}₹${Math.abs(Math.round(netFlowCr)).toLocaleString('en-IN')}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#cbd5e1;">${instStakeStr}</td>
                        <td style="padding:0.45rem 0.4rem;text-align:center;">
                            <button type="button" onclick="event.stopPropagation(); app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.15rem 0.4rem;background:rgba(56,189,248,0.1);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);" title="Inspect ${it.ticker}">🔍</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        renderInstitutionalDistributingTable(items) {
            const tbody = document.getElementById('instDistributingTableBody');
            const countBadge = document.getElementById('instDistCountBadge');
            if (countBadge) {
                countBadge.innerText = `Showing ${items ? items.length : 0} setups`;
            }
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No high-distribution stocks found.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const ret7dStr = it.return_7d_pct != null ? (it.return_7d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_7d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_7d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                const ret30dStr = it.return_30d_pct != null ? (it.return_30d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${it.return_30d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${it.return_30d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                const instStakeStr = (it.total_institutional_stake_pct != null && it.total_institutional_stake_pct > 0) ? `${it.total_institutional_stake_pct}%` : ((it.total_institutional_stake != null && it.total_institutional_stake > 0) ? `${it.total_institutional_stake}%` : '—');
                const isSelected = this._selectedTicker === it.ticker;
                const rowBg = isSelected ? 'rgba(239,68,68,0.12)' : 'transparent';

                const newFiiBadge = it.is_new_fii_entry ? `<span style="font-size:0.6rem;padding:0.08rem 0.32rem;border-radius:4px;background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-weight:700;margin-left:0.3rem;">New FII</span>` : '';
                const newDiiBadge = it.is_new_dii_entry ? `<span style="font-size:0.6rem;padding:0.08rem 0.32rem;border-radius:4px;background:rgba(52,211,153,0.2);color:#34d399;border:1px solid rgba(52,211,153,0.35);font-weight:700;margin-left:0.3rem;">New DII</span>` : '';

                const compName = (it.company_name && it.company_name !== it.ticker && !it.company_name.endsWith('.NS')) ? it.company_name : '';
                const netFlowCr = it.net_flow_cr || 0;
                const netFlowCol = netFlowCr >= 0 ? '#34d399' : '#f87171';
                const netFlowSign = netFlowCr >= 0 ? '+' : '';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:${rowBg};cursor:pointer;transition:background 0.12s;" onclick="app.searchInstitutionalStock('${it.ticker}')" onmouseover="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='rgba(255,255,255,0.03)'" onmouseout="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='transparent'">
                        <td style="padding:0.45rem 0.6rem;font-family:var(--font-mono);font-weight:700;">
                            <span style="color:#f87171;">${it.ticker.replace('.NS', '')}</span>
                            ${newFiiBadge}${newDiiBadge}
                            ${compName ? `<div style="font-size:0.6rem;color:#64748b;font-weight:400;font-family:var(--font-sans);margin-top:0.08rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px;">${compName}</div>` : ''}
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f87171;">${it.accumulation_score}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret7dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret30dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${it.funds_selling_count}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:${netFlowCol};font-weight:700;font-size:0.68rem;">${netFlowSign}₹${Math.abs(Math.round(netFlowCr)).toLocaleString('en-IN')}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#cbd5e1;">${instStakeStr}</td>
                        <td style="padding:0.45rem 0.4rem;text-align:center;">
                            <button type="button" onclick="event.stopPropagation(); app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.15rem 0.4rem;background:rgba(239,68,68,0.1);color:#f87171;border:1px solid rgba(239,68,68,0.3);" title="Inspect ${it.ticker}">🔍</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        renderInstitutionalFundsTable(funds) {
            const tbody = document.getElementById('instFundsTableBody') || document.getElementById('instInvestorsDirectoryTableBody');
            const countBadge = document.getElementById('instFundsCountBadge');
            if (countBadge) {
                countBadge.innerText = `Showing ${funds ? funds.length : 0} funds & whales`;
            }
            if (!tbody) return;

            if (!funds || !funds.length) {
                tbody.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#64748b;">No fund profiles match the selected filter.</td></tr>';
                return;
            }

            tbody.innerHTML = funds.map(f => {
                const ret30Str = f.return_30d_pct != null ? (f.return_30d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;font-family:var(--font-mono);">+${f.return_30d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;font-family:var(--font-mono);">${f.return_30d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                const ret1yStr = f.return_1y_pct != null ? (f.return_1y_pct >= 0 ? `<span style="color:#34d399;font-weight:700;font-family:var(--font-mono);">+${f.return_1y_pct}%</span>` : `<span style="color:#f87171;font-weight:700;font-family:var(--font-mono);">${f.return_1y_pct}%</span>`) : '<span style="color:#64748b;">—</span>';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.8rem;font-weight:700;color:#f8fafc;">
                            <a href="javascript:void(0)" onclick="app.inspectFundPortfolio('${f.fund_name.replace(/'/g, "\\'")}')" style="color:#f8fafc;text-decoration:none;border-bottom:1px dashed rgba(255,255,255,0.3);">${f.fund_name}</a>
                        </td>
                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${f.fund_type}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;font-weight:700;">${f.total_positions} Stocks</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${f.buying_actions}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${f.selling_actions}</td>
                        <td style="padding:0.65rem 0.8rem;">${ret30Str}</td>
                        <td style="padding:0.65rem 0.8rem;">${ret1yStr}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">₹${(f.total_aum_tracked_cr || 0).toLocaleString()} Cr</td>
                        <td style="padding:0.65rem 0.8rem;text-align:center;">
                            <button type="button" onclick="app.inspectFundPortfolio('${f.fund_name.replace(/'/g, "\\'")}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;background:rgba(59,130,246,0.1);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);">💼 Portfolio</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        inspectInstitutionalHoldingStock(ticker) {
            if (!ticker) return;
            const cleanTicker = ticker.trim().toUpperCase();
            this.closeFundModal();
            this.switchInstitutionalPage('equities');
            if (this._splitCollapsed) {
                this.toggleInstitutionalSplitLayout();
            }
            this.searchInstitutionalStock(cleanTicker);
            const radarEl = document.getElementById('instEquitiesSplitGrid') || document.getElementById('instPage-equities');
            if (radarEl) {
                radarEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        },

        async searchInstitutionalStock(ticker) {
            if (!ticker) return;
            const cleanTicker = ticker.trim().toUpperCase();
            this._selectedTicker = cleanTicker;

            // Ensure equities page is active and split drilldown is visible
            const invPage = document.getElementById('instPage-investors');
            if (invPage && invPage.style.display !== 'none') {
                this.switchInstitutionalPage('equities');
            }
            if (this._splitCollapsed) {
                this.toggleInstitutionalSplitLayout();
            }
            
            // Re-render compact tables to update selected row highlighting
            if (this.institutionalData.accumulating.length) {
                this.renderInstitutionalAccumulatingTable(this.institutionalData.accumulating);
            }
            if (this.institutionalData.distributing.length) {
                this.renderInstitutionalDistributingTable(this.institutionalData.distributing);
            }

            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.renderStockInstitutionalDetails(data);
                } else {
                    console.warn('Failed finding institutional data for ' + cleanTicker);
                }
            } catch (e) {
                console.error('Error fetching institutional stock:', e);
            }
        },

        renderStockInstitutionalDetails(data) {
            if (!data) return;

            const tickerEl = document.getElementById('instSelectedTicker');
            const nameEl = document.getElementById('instSelectedCompanyName');
            const badgeEl = document.getElementById('instSelectedVerdictBadge');
            const scoreTextEl = document.getElementById('instSelectedScoreText');

            const newFiiBadge = data.is_new_fii_entry ? `<span style="font-size:0.68rem;padding:0.12rem 0.45rem;border-radius:4px;background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);font-weight:700;margin-left:0.4rem;">New FII Entry</span>` : '';
            const newDiiBadge = data.is_new_dii_entry ? `<span style="font-size:0.68rem;padding:0.12rem 0.45rem;border-radius:4px;background:rgba(52,211,153,0.2);color:#34d399;border:1px solid rgba(52,211,153,0.4);font-weight:700;margin-left:0.4rem;">New DII Entry</span>` : '';

            if (tickerEl) {
                tickerEl.innerHTML = `<span>${data.ticker}</span>${newFiiBadge}${newDiiBadge}`;
            }
            if (nameEl) nameEl.textContent = data.company_name || '';
            if (badgeEl) {
                badgeEl.textContent = data.verdict;
                badgeEl.style.background = data.verdict_badge === 'emerald' ? 'rgba(16,185,129,0.15)' : data.verdict_badge === 'green' ? 'rgba(34,197,94,0.15)' : data.verdict_badge === 'rose' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)';
                badgeEl.style.color = data.verdict_badge === 'emerald' ? '#34d399' : data.verdict_badge === 'green' ? '#4ade80' : data.verdict_badge === 'rose' ? '#f87171' : '#fbbf24';
            }
            if (scoreTextEl) {
                const netSign = (data.net_flow_cr || 0) >= 0 ? '+' : '-';
                const netCol = (data.net_flow_cr || 0) >= 0 ? '#34d399' : '#f87171';
                const ret7dStr = data.return_7d_pct != null ? (data.return_7d_pct >= 0 ? `<strong style="color:#34d399;">+${data.return_7d_pct}%</strong>` : `<strong style="color:#f87171;">${data.return_7d_pct}%</strong>`) : '—';
                const ret30dStr = data.return_30d_pct != null ? (data.return_30d_pct >= 0 ? `<strong style="color:#34d399;">+${data.return_30d_pct}%</strong>` : `<strong style="color:#f87171;">${data.return_30d_pct}%</strong>`) : '—';
                const ret1yStr = data.return_1y_pct != null ? (data.return_1y_pct >= 0 ? `<strong style="color:#34d399;">+${data.return_1y_pct}%</strong>` : `<strong style="color:#f87171;">${data.return_1y_pct}%</strong>`) : '—';

                let fiiInterestHtml = '';
                if (data.fii_always_held) {
                    fiiInterestHtml = `
                        <div style="margin-top:0.45rem;padding:0.35rem 0.6rem;border-radius:4px;background:rgba(56,189,248,0.08);border:1px solid rgba(56,189,248,0.25);font-size:0.72rem;color:#93c5fd;display:flex;align-items:center;gap:0.4rem;">
                            <span>🏛️</span> <strong>FII Interest (8M):</strong> Had ${data.baseline_fii_pct || 0}% on Dec 2025 (Long-term allocation)
                        </div>
                    `;
                } else if (data.fii_interest_date) {
                    const sigRetStr = (data.fii_interest_return_pct != null) ? ((data.fii_interest_return_pct >= 0 ? '+' : '') + data.fii_interest_return_pct + '%') : '—';
                    const sigRetCol = (data.fii_interest_return_pct || 0) >= 0 ? '#34d399' : '#f87171';
                    fiiInterestHtml = `
                        <div style="margin-top:0.45rem;padding:0.35rem 0.6rem;border-radius:4px;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);font-size:0.72rem;color:#6ee7b7;">
                            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.3rem;">
                                <span>⚡ <strong>FII Interest Initiated:</strong> ${data.fii_interest_quarter} (${data.fii_interest_date})</span>
                                <span style="font-family:var(--font-mono);font-weight:700;">Returns: <strong style="color:${sigRetCol};">${sigRetStr}</strong></span>
                            </div>
                            <div style="font-size:0.68rem;color:#cbd5e1;margin-top:0.15rem;font-family:var(--font-mono);">
                                Signal Price: ₹${Number(data.fii_signal_price || 0).toLocaleString('en-IN', {minimumFractionDigits:2})} &middot; Current Price: ₹${Number(data.fii_current_price || 0).toLocaleString('en-IN', {minimumFractionDigits:2})}
                            </div>
                        </div>
                    `;
                }

                scoreTextEl.innerHTML = `
                    <div>
                        Score: <strong style="color:#38bdf8;">${data.accumulation_score}</strong>
                        &nbsp;·&nbsp; Inst Stake: <strong style="color:#e2e8f0;">${data.total_institutional_stake_pct || '—'}%</strong>
                        &nbsp;·&nbsp; Inflow: <strong style="color:#34d399;">+₹${(data.gross_inflow_cr || 0).toLocaleString()} Cr</strong>
                        &nbsp;·&nbsp; Outflow: <strong style="color:#f87171;">-₹${(data.gross_outflow_cr || 0).toLocaleString()} Cr</strong>
                        &nbsp;·&nbsp; Net: <strong style="color:${netCol};">${netSign}₹${Math.abs(data.net_flow_cr || 0).toLocaleString()} Cr</strong>
                    </div>
                    <div style="margin-top:0.2rem;">
                        7D: ${ret7dStr}
                        &nbsp;·&nbsp; 30D: ${ret30dStr}
                        &nbsp;·&nbsp; 1Y: ${ret1yStr}
                        &nbsp;·&nbsp; Funds (QoQ): <strong style="color:#34d399;">+${data.funds_accumulating_count}</strong> / <strong style="color:#f87171;">-${data.funds_selling_count}</strong>
                    </div>
                    ${fiiInterestHtml}
                `;
            }

            // 1. Shareholding pattern history with QoQ deltas in chronological descending order
            const patContainer = document.getElementById('instShareholdingPatternContainer');
            if (patContainer) {
                const pats = data.shareholding_patterns || [];
                if (!pats.length) {
                    patContainer.innerHTML = '<div style="color:#64748b;font-size:0.7rem;padding:0.4rem;">No historical shareholding filings found.</div>';
                } else {
                    patContainer.innerHTML = `
                        <table style="width:100%;font-size:0.7rem;text-align:left;border-collapse:collapse;">
                            <thead>
                                <tr style="color:#94a3b8;border-bottom:1px solid rgba(255,255,255,0.06);font-family:var(--font-mono);font-size:0.65rem;">
                                    <th style="padding:0.3rem 0.4rem;">QUARTER</th>
                                    <th style="padding:0.3rem 0.4rem;text-align:right;">STOCK PRICE</th>
                                    <th style="padding:0.3rem 0.4rem;text-align:right;">PROMOTER</th>
                                    <th style="padding:0.3rem 0.4rem;text-align:right;">FII / FPI</th>
                                    <th style="padding:0.3rem 0.4rem;text-align:right;">DII / MUTUAL FUNDS</th>
                                    <th style="padding:0.3rem 0.4rem;text-align:right;">RETAIL</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${pats.map((p, idx) => {
                                    const prevP = pats[idx + 1];
                                    const fiiDelta = prevP ? (p.fii_pct - prevP.fii_pct) : 0;
                                    const diiDelta = prevP ? (p.dii_mf_pct - prevP.dii_mf_pct) : 0;
                                    const fiiDeltaStr = prevP ? (fiiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${fiiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${fiiDelta.toFixed(2)}%)</span>`) : '';
                                    const diiDeltaStr = prevP ? (diiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${diiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${diiDelta.toFixed(2)}%)</span>`) : '';

                                    // Stock Price presentation: Present quarter vs historical quarter start
                                    const isCurrentQ = p.is_current_quarter || idx === 0;
                                    let priceHtml = '—';
                                    if (isCurrentQ) {
                                        const curP = p.current_price != null ? p.current_price : p.stock_price;
                                        const startP = p.quarter_start_price;
                                        const retQ = (curP && startP) ? (((curP - startP) / startP) * 100) : null;
                                        const retStr = retQ != null ? `<span style="color:${retQ >= 0 ? '#34d399' : '#f87171'};font-size:0.60rem;font-weight:700;">(${retQ >= 0 ? '+' : ''}${retQ.toFixed(1)}%)</span>` : '';
                                        
                                        priceHtml = `
                                            <div style="font-weight:800;color:#f8fafc;">₹${curP != null ? Number(curP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}) : '—'} <span style="font-size:0.58rem;color:#38bdf8;background:rgba(56,189,248,0.15);padding:0.02rem 0.25rem;border-radius:3px;font-weight:700;">Live</span></div>
                                            ${startP ? `<div style="font-size:0.60rem;color:#64748b;">Start: ₹${Number(startP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})} ${retStr}</div>` : ''}
                                        `;
                                    } else {
                                        const startP = p.quarter_start_price != null ? p.quarter_start_price : p.stock_price;
                                        priceHtml = `
                                            <div style="font-weight:700;color:#93c5fd;">₹${startP != null ? Number(startP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}) : '—'}</div>
                                            <div style="font-size:0.60rem;color:#64748b;">Quarter Start</div>
                                        `;
                                    }

                                    return `
                                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                             <td style="padding:0.35rem 0.4rem;font-weight:700;color:#f8fafc;font-family:var(--font-mono);">${p.quarter}</td>
                                             <td style="padding:0.35rem 0.4rem;text-align:right;font-family:var(--font-mono);">${priceHtml}</td>
                                             <td style="padding:0.35rem 0.4rem;text-align:right;color:#cbd5e1;font-family:var(--font-mono);">${p.promoter_pct}%</td>
                                             <td style="padding:0.35rem 0.4rem;text-align:right;color:#38bdf8;font-weight:700;font-family:var(--font-mono);">${p.fii_pct}% ${fiiDeltaStr}</td>
                                             <td style="padding:0.35rem 0.4rem;text-align:right;color:#34d399;font-weight:700;font-family:var(--font-mono);">${p.dii_mf_pct}% ${diiDeltaStr}</td>
                                             <td style="padding:0.35rem 0.4rem;text-align:right;color:#94a3b8;font-family:var(--font-mono);">${p.public_retail_pct}%</td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }

            // 2. Block deals
            const dealsContainer = document.getElementById('instBlockDealsContainer');
            if (dealsContainer) {
                const deals = data.block_deals || [];
                if (!deals.length) {
                    dealsContainer.innerHTML = '<div style="color:#64748b;font-size:0.7rem;padding:0.4rem;">No recent block/bulk deals recorded.</div>';
                } else {
                    dealsContainer.innerHTML = deals.map(d => {
                        const isBuy = d.deal_type === 'BUY';
                        const col = isBuy ? '#34d399' : '#f87171';
                        const bg = isBuy ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
                        return `
                            <div style="background:${bg};border:1px solid ${isBuy ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'};border-radius:5px;padding:0.35rem 0.55rem;margin-bottom:0.3rem;display:flex;justify-content:space-between;align-items:center;">
                                <div>
                                    <div style="font-size:0.7rem;font-weight:700;color:#f8fafc;">${d.client_name}</div>
                                    <div style="font-size:0.63rem;color:#94a3b8;font-family:var(--font-mono);">${d.deal_date} · ${(d.quantity || 0).toLocaleString()} @ ₹${d.price}</div>
                                </div>
                                <div style="text-align:right;">
                                    <div style="font-size:0.7rem;font-weight:800;color:${col};font-family:var(--font-mono);">${d.deal_type} ₹${d.value_cr} Cr</div>
                                    <div style="font-size:0.62rem;color:#cbd5e1;">${d.pct_equity}% eq</div>
                                </div>
                            </div>
                        `;
                    }).join('');
                }
            }

            // 3. Fund Holdings Table
            const hBody = document.getElementById('instStockHoldingsTableBody');
            if (hBody) {
                const holdings = data.holdings || [];
                if (!holdings.length) {
                    hBody.innerHTML = '<tr><td colspan="9" style="padding:1.5rem;text-align:center;color:#64748b;">No individual fund positions reported.</td></tr>';
                } else {
                    hBody.innerHTML = holdings.map(h => {
                        const isBuy = h.action === 'ACCUMULATED' || h.action === 'NEW BUY';
                        const actCol = isBuy ? '#34d399' : h.action === 'TRIMMED' || h.action === 'SOLD OUT' ? '#f87171' : '#cbd5e1';
                        const actBg = isBuy ? 'rgba(16,185,129,0.15)' : h.action === 'TRIMMED' || h.action === 'SOLD OUT' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)';
                        const chgSign = (h.change_pct || 0) > 0 ? `+${h.change_pct}%` : (h.change_pct || 0) < 0 ? `${h.change_pct}%` : '0.00%';
                        const isTrim = h.action === 'TRIMMED' || h.action === 'SOLD OUT';
                        const txnPrice = h.recent_txn_price != null ? Number(h.recent_txn_price).toFixed(2) : (isBuy && h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : null);
                        const txnDate = h.recent_txn_date || h.reported_date;
                        
                        let txnCellHtml = `<span style="color:#64748b;font-family:var(--font-mono);font-size:0.68rem;">— <span style="font-size:0.58rem;color:#475569;">(Holding)</span></span>`;
                        if (isBuy && txnPrice) {
                            txnCellHtml = `
                                <div>
                                    <span style="color:#34d399;font-weight:700;font-family:var(--font-mono);font-size:0.68rem;">🟢 Buy ₹${txnPrice}</span>
                                    <div style="font-size:0.58rem;color:#94a3b8;font-family:var(--font-mono);margin-top:0.05rem;">📅 ${txnDate || '—'}</div>
                                </div>
                            `;
                        } else if (isTrim && txnPrice) {
                            txnCellHtml = `
                                <div>
                                    <span style="color:#f87171;font-weight:700;font-family:var(--font-mono);font-size:0.68rem;">🔴 ${h.action === 'TRIMMED' ? 'Trim' : 'Exit'} ₹${txnPrice}</span>
                                    <div style="font-size:0.58rem;color:#94a3b8;font-family:var(--font-mono);margin-top:0.05rem;">📅 ${txnDate || '—'}</div>
                                </div>
                            `;
                        }

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                                <td style="padding:0.45rem 0.6rem;font-weight:700;color:#f8fafc;">
                                    <a href="javascript:void(0)" onclick="app.inspectFundPortfolio('${h.fund_name.replace(/'/g, "\\'")}')" style="color:#f8fafc;text-decoration:none;border-bottom:1px dashed rgba(255,255,255,0.3);">${h.fund_name}</a>
                                </td>
                                <td style="padding:0.45rem 0.5rem;color:#94a3b8;font-size:0.68rem;">${h.fund_type}</td>
                                <td style="padding:0.45rem 0.5rem;">
                                    <span class="signal-badge" style="background:${actBg};color:${actCol};font-size:0.62rem;padding:0.08rem 0.35rem;">${h.action}</span>
                                </td>
                                <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${h.stake_pct}%</td>
                                <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#38bdf8;font-weight:600;">₹${h.avg_price != null ? Number(h.avg_price).toFixed(2) : '—'}</td>
                                <td style="padding:0.45rem 0.5rem;">${txnCellHtml}</td>
                                <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:${actCol};font-weight:700;">${chgSign}</td>
                                <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#cbd5e1;">₹${(h.holding_value_cr || 0).toLocaleString()} Cr</td>
                                <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#94a3b8;font-size:0.68rem;">${h.reported_date || '—'}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }
        },

        async inspectFundPortfolio(fundName) {
            if (!fundName) return;
            const modal = document.getElementById('instFundModal');
            const titleEl = document.getElementById('instFundModalTitle');
            const subEl = document.getElementById('instFundModalSubtitle');
            const tbody = document.getElementById('instFundModalTableBody');

            if (titleEl) titleEl.textContent = fundName;
            if (subEl) subEl.textContent = 'Loading equity portfolio disclosures...';
            if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:2rem;text-align:center;color:#64748b;"><div style="display:inline-block;animation:spin 1s linear infinite;margin-right:0.4rem;">⏳</div> Fetching portfolio holdings & returns...</td></tr>';
            if (modal) modal.style.display = 'flex';

            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/fund/${encodeURIComponent(fundName)}`);
                if (res.ok) {
                    const data = await res.json();
                    const holdings = data.holdings || [];
                    if (subEl) subEl.textContent = `${holdings.length} tracked equity positions · Category: ${holdings[0]?.fund_type || 'Institutional'}`;

                    if (!holdings.length) {
                        tbody.innerHTML = '<tr><td colspan="11" style="padding:2rem;text-align:center;color:#64748b;">No recent holdings filed for this fund.</td></tr>';
                        return;
                    }

                    tbody.innerHTML = holdings.map(h => {
                        const isBuy = h.action === 'ACCUMULATED' || h.action === 'NEW BUY';
                        const isTrim = h.action === 'TRIMMED' || h.action === 'SOLD OUT';
                        const actCol = isBuy ? '#34d399' : isTrim ? '#f87171' : '#cbd5e1';
                        const actBg = isBuy ? 'rgba(16,185,129,0.15)' : isTrim ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)';
                        const compName = h.company_name ? `<div style="font-size:0.68rem;color:#94a3b8;font-weight:normal;">${h.company_name}</div>` : '';
                        const ret30 = h.return_30d_pct != null ? Number(h.return_30d_pct) : null;
                        const ret30Str = ret30 != null ? `<span style="color:${ret30 >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${ret30 >= 0 ? '+' : ''}${ret30.toFixed(1)}%</span>` : '<span style="color:#64748b;">—</span>';
                        const ret1y = h.return_1y_pct != null ? Number(h.return_1y_pct) : null;
                        const ret1yStr = ret1y != null ? `<span style="color:${ret1y >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${ret1y >= 0 ? '+' : ''}${ret1y.toFixed(1)}%</span>` : '<span style="color:#64748b;">—</span>';
                        const txnPrice = h.recent_txn_price != null ? Number(h.recent_txn_price).toFixed(2) : (isBuy && h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : null);
                        const txnDate = h.recent_txn_date || h.reported_date;

                        let txnCellHtml = `<span style="color:#64748b;font-family:var(--font-mono);font-size:0.7rem;">— <span style="font-size:0.6rem;color:#475569;">(Holding)</span></span>`;
                        if (isBuy && txnPrice) {
                            txnCellHtml = `
                                <div>
                                    <span style="color:#34d399;font-weight:700;font-family:var(--font-mono);font-size:0.72rem;">🟢 Buy ₹${txnPrice}</span>
                                    <div style="font-size:0.62rem;color:#94a3b8;font-family:var(--font-mono);margin-top:0.08rem;">📅 ${txnDate || '—'}</div>
                                </div>
                            `;
                        } else if (isTrim && txnPrice) {
                            txnCellHtml = `
                                <div>
                                    <span style="color:#f87171;font-weight:700;font-family:var(--font-mono);font-size:0.72rem;">🔴 ${h.action === 'TRIMMED' ? 'Trim' : 'Exit'} ₹${txnPrice}</span>
                                    <div style="font-size:0.62rem;color:#94a3b8;font-family:var(--font-mono);margin-top:0.08rem;">📅 ${txnDate || '—'}</div>
                                </div>
                            `;
                        }

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);font-weight:700;">
                                    <a href="javascript:void(0)" onclick="app.inspectInstitutionalHoldingStock('${h.ticker}')" style="color:#38bdf8;text-decoration:none;border-bottom:1px dashed rgba(56,189,248,0.4);" title="Inspect ${h.ticker} Institutional Flow">${h.ticker}</a>
                                    ${compName}
                                </td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">${h.quarter}</td>
                                <td style="padding:0.55rem 0.8rem;">
                                    <span class="signal-badge" style="background:${actBg};color:${actCol};font-size:0.65rem;padding:0.1rem 0.4rem;">${h.action}</span>
                                </td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${h.stake_pct}%</td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);">${ret30Str}</td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);">${ret1yStr}</td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;font-weight:600;">₹${h.avg_price != null ? Number(h.avg_price).toFixed(2) : '—'}</td>
                                <td style="padding:0.55rem 0.8rem;">${txnCellHtml}</td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">₹${(h.holding_value_cr || 0).toLocaleString()} Cr</td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);color:#94a3b8;font-size:0.72rem;">${h.reported_date || '—'}</td>
                                <td style="padding:0.55rem 0.8rem;text-align:center;white-space:nowrap;">
                                    <div style="display:flex;gap:0.35rem;justify-content:center;">
                                        <button type="button" onclick="app.inspectInstitutionalHoldingStock('${h.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.2rem 0.45rem;background:rgba(56,189,248,0.1);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);" title="Inspect Institutional Flow & Shareholding">🏛️ Flow</button>
                                        <button type="button" onclick="app.closeFundModal(); if (typeof app.showStockFullScreen === 'function') app.showStockFullScreen('${h.ticker}'); else if (typeof app.openStockDetailModal === 'function') app.openStockDetailModal('${h.ticker}'); else window.open('/stock/${encodeURIComponent(h.ticker)}', '_blank');" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.2rem 0.45rem;background:rgba(168,85,247,0.1);color:#c084fc;border:1px solid rgba(168,85,247,0.3);" title="Open Complete Stock Intelligence Analysis">📊 Detail</button>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join('');
                } else {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:2rem;text-align:center;color:#f87171;">Failed fetching fund details.</td></tr>';
                }
            } catch (e) {
                console.error('Error inspecting fund:', e);
                if (tbody) tbody.innerHTML = `<tr><td colspan="11" style="padding:2rem;text-align:center;color:#f87171;">Error: ${e.message}</td></tr>`;
            }
        },

        closeFundModal() {
            const modal = document.getElementById('instFundModal');
            if (modal) modal.style.display = 'none';
        }
    };

    window.institutionalModule = institutionalModule;

    // Attach methods onto window.app namespace so onclick handlers work seamlessly
    if (window.app) {
        Object.assign(window.app, institutionalModule);
    } else {
        window.addEventListener('DOMContentLoaded', () => {
            if (window.app) Object.assign(window.app, institutionalModule);
        });
    }
})();
