// =========================================================================
// institutional — Nexus Dashboard Module (Institutional Accumulation & Funds)
// Enhanced with 3 Distinct Financial Metrics: Increase %, Increase Amount (₹ Cr), Total Amount (₹ Cr)
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    Object.assign(app, {
        // =========================================================================
        // 🏛️ Institutional Accumulation & Mutual Fund Activity Hub
        // =========================================================================
        institutionalActiveView: 'accumulating',
        institutionalSubPage: 'equities',
        _currentInvestorFilter: 'ALL',
        institutionalData: {
            accumulating: [],
            distributing: [],
            funds: [],
            topAdditions: null,
            currentStock: null,
        },

        switchInstitutionalView(view) {
            this.institutionalActiveView = view || 'accumulating';
            ['accumulating', 'stock', 'distributing', 'funds'].forEach(v => {
                const el = document.getElementById('instView-' + v);
                const btn = document.getElementById('btnInstTab-' + v);
                if (el) el.style.display = (v === this.institutionalActiveView) ? 'block' : 'none';
                if (btn) {
                    if (v === this.institutionalActiveView) {
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
        },

        switchEquitiesFlowView(view) {
            const isAcc = view === 'accumulating';
            const accEl = document.getElementById('instEquitiesFlow-accumulating');
            const distEl = document.getElementById('instEquitiesFlow-distributing');
            const btnAcc = document.getElementById('btnInstFlowToggle-acc');
            const btnDist = document.getElementById('btnInstFlowToggle-dist');

            if (accEl) accEl.style.display = isAcc ? 'block' : 'none';
            if (distEl) distEl.style.display = isAcc ? 'none' : 'block';

            if (btnAcc) {
                btnAcc.style.background = isAcc ? '#1e293b' : 'transparent';
                btnAcc.style.color = isAcc ? '#34d399' : '#94a3b8';
                btnAcc.style.borderColor = isAcc ? 'rgba(16,185,129,0.4)' : 'transparent';
                btnAcc.style.fontWeight = isAcc ? '700' : '500';
            }
            if (btnDist) {
                btnDist.style.background = !isAcc ? '#1e293b' : 'transparent';
                btnDist.style.color = !isAcc ? '#f87171' : '#94a3b8';
                btnDist.style.borderColor = !isAcc ? 'rgba(239,68,68,0.4)' : 'transparent';
                btnDist.style.fontWeight = !isAcc ? '700' : '500';
            }
        },

        toggleInstitutionalSplitLayout() {
            const grid = document.getElementById('instEquitiesSplitGrid');
            const btn = document.getElementById('btnToggleInstSplit');
            if (!grid) return;
            const isCurrentlySplit = grid.style.gridTemplateColumns !== '1fr';
            if (isCurrentlySplit) {
                grid.style.gridTemplateColumns = '1fr';
                if (btn) btn.innerHTML = '◫ Expand Split';
            } else {
                grid.style.gridTemplateColumns = 'minmax(0, 1.05fr) minmax(0, 0.95fr)';
                if (btn) btn.innerHTML = '◫ 50-50 Split';
            }
        },

        switchInstitutionalPage(page) {
            const pages = ['equities', 'top-additions', 'investors'];
            const p = pages.includes(page) ? page : 'equities';
            this.institutionalSubPage = p;
            try {
                localStorage.setItem('subtab_institutional', p);
                localStorage.setItem('ee_institutional_subpage', p);
                if (!app._subtabState) app._subtabState = {};
                app._subtabState['institutional'] = p;
            } catch (e) {}

            pages.forEach(name => {
                const el = document.getElementById('instPage-' + name);
                const btn = document.getElementById('btnInstPage-' + name);
                if (el) el.style.display = (name === p) ? 'block' : 'none';
                if (btn) {
                    if (name === p) {
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

            const sideEquities = document.getElementById('sidebarSubInstEquities');
            const sideAdditions = document.getElementById('sidebarSubInstAdditions');
            const sideInvestors = document.getElementById('sidebarSubInstInvestors');
            if (sideEquities) sideEquities.classList.toggle('active', p === 'equities');
            if (sideAdditions) sideAdditions.classList.toggle('active', p === 'top-additions');
            if (sideInvestors) sideInvestors.classList.toggle('active', p === 'investors');

            if (p === 'investors') {
                this.loadSuperInvestors();
            } else if (p === 'top-additions') {
                this.loadTopAdditions();
            } else {
                this.loadInstitutionalData();
            }
        },

        _accLimit: 25,
        _distLimit: 20,
        _fundsLimit: 50,
        _loadingMoreAcc: false,
        _loadingMoreDist: false,
        _loadingMoreFunds: false,

        async loadInstitutionalData() {
            try {
                this._accLimit = 25;
                this._distLimit = 20;
                this._fundsLimit = 50;

                const [resAcc, resDist, resFunds] = await Promise.all([
                    fetch(API_BASE + `/api/v1/institutional/accumulating?limit=${this._accLimit}`),
                    fetch(API_BASE + `/api/v1/institutional/distributing?limit=${this._distLimit}`),
                    fetch(API_BASE + `/api/v1/institutional/funds?limit=${this._fundsLimit}`)
                ]);

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

                // Default search ALLCARGO.NS
                this.searchInstitutionalStock('ALLCARGO.NS', false);

            } catch (e) {
                console.error('Failed loading institutional data:', e);
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

        renderInstitutionalAccumulatingTable(items) {
            const tbody = document.getElementById('instAccumulatingTableBody');
            const countBadge = document.getElementById('instAccCountBadge');
            if (countBadge) {
                countBadge.innerText = `Showing ${items ? items.length : 0} setups`;
            }
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="8" style="padding:2rem;text-align:center;color:#64748b;">No high-conviction accumulating stocks found.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const fundsInStr = `<span style="color:#34d399;font-weight:700;">+${it.funds_accumulating_count || 0} in</span> / <span style="color:#f87171;">-${it.funds_selling_count || 0} out</span>`;
                const ret7d = it.return_7d_pct != null ? it.return_7d_pct : 0;
                const ret30d = it.return_30d_pct != null ? it.return_30d_pct : 0;
                const ret7dCol = ret7d >= 0 ? '#34d399' : '#f87171';
                const ret30dCol = ret30d >= 0 ? '#34d399' : '#f87171';
                const netFlow = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">
                            <span style="color:#38bdf8;">${it.ticker.replace('.NS', '')}</span>
                            <div style="font-size:0.65rem;color:#94a3b8;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px;">${it.company_name || ''}</div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">${it.accumulation_score}</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:${ret7dCol};font-weight:600;">${ret7d >= 0 ? '+' : ''}${ret7d}%</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:${ret30dCol};font-weight:600;">${ret30d >= 0 ? '+' : ''}${ret30d}%</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${fundsInStr}</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+₹${Number(netFlow).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:#f8fafc;">${it.total_institutional_stake}%</td>
                        <td style="padding:0.55rem 0.4rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.15rem 0.45rem;">Inspect</button>
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
                tbody.innerHTML = '<tr><td colspan="8" style="padding:2rem;text-align:center;color:#64748b;">No high-distribution equities detected.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const fundsInStr = `<span style="color:#34d399;">+${it.funds_accumulating_count || 0}</span> / <span style="color:#f87171;font-weight:700;">-${it.funds_selling_count || 0}</span>`;
                const ret7d = it.return_7d_pct != null ? it.return_7d_pct : 0;
                const ret30d = it.return_30d_pct != null ? it.return_30d_pct : 0;
                const ret7dCol = ret7d >= 0 ? '#34d399' : '#f87171';
                const ret30dCol = ret30d >= 0 ? '#34d399' : '#f87171';
                const netFlow = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:#f87171;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">
                            <span>${it.ticker.replace('.NS', '')}</span>
                            <div style="font-size:0.65rem;color:#94a3b8;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px;">${it.company_name || ''}</div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f87171;">${it.accumulation_score}</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:${ret7dCol};font-weight:600;">${ret7d >= 0 ? '+' : ''}${ret7d}%</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:${ret30dCol};font-weight:600;">${ret30d >= 0 ? '+' : ''}${ret30d}%</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${fundsInStr}</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-₹${Math.abs(Number(netFlow)).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);color:#f8fafc;">${it.total_institutional_stake}%</td>
                        <td style="padding:0.55rem 0.4rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.15rem 0.45rem;">Inspect</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        renderInstitutionalFundsTable(funds) {
            const tbody = document.getElementById('instFundsTableBody');
            const countBadge = document.getElementById('instFundsCountBadge');
            if (countBadge) {
                countBadge.innerText = `Showing ${funds ? funds.length : 0} funds & whales`;
            }
            if (!tbody) return;

            if (!funds || !funds.length) {
                tbody.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#64748b;">No fund profiles loaded.</td></tr>';
                return;
            }

            tbody.innerHTML = funds.map(f => {
                const ret30 = f.return_30d_pct != null ? f.return_30d_pct : 0;
                const ret1y = f.return_1y_pct != null ? f.return_1y_pct : 0;
                const ret30Col = ret30 >= 0 ? '#34d399' : '#f87171';
                const ret1yCol = ret1y >= 0 ? '#34d399' : '#f87171';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.8rem;font-weight:700;color:#f8fafc;">${f.fund_name}</td>
                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${f.fund_type}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;">${f.total_positions} Stocks</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${f.buying_actions}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${f.selling_actions}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:${ret30Col};font-weight:700;">${ret30 >= 0 ? '+' : ''}${ret30}%</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:${ret1yCol};font-weight:700;">${ret1y >= 0 ? '+' : ''}${ret1y}%</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;font-weight:700;">₹${Number(f.total_aum_tracked_cr || 0).toLocaleString()} Cr</td>
                        <td style="padding:0.65rem 0.8rem;text-align:center;">
                            <button type="button" onclick="app.inspectFundPortfolio('${f.fund_name.replace(/'/g, "\\'")}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.25rem 0.6rem;background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);">View Holdings</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async loadSuperInvestors() {
            try {
                this._fundsLimit = 50;
                const res = await fetch(API_BASE + `/api/v1/institutional/funds?limit=${this._fundsLimit}`);
                if (res.ok) {
                    const data = await res.json();
                    this.institutionalData.funds = data.funds || [];
                    this.filterInvestors(this._currentInvestorFilter || 'ALL');
                }
            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading super investors:', e);
            }
        },

        filterInvestors(category) {
            this._currentInvestorFilter = category || 'ALL';
            const pills = ['ALL', 'Mutual Fund', 'Super Investor', 'Foreign'];
            pills.forEach(cat => {
                let id = 'btnInvCat-ALL';
                if (cat === 'Mutual Fund') id = 'btnInvCat-MF';
                else if (cat === 'Super Investor') id = 'btnInvCat-SI';
                else if (cat === 'Foreign') id = 'btnInvCat-FII';

                const btn = document.getElementById(id);
                if (btn) {
                    if (cat === category) {
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

        async loadTopAdditions() {
            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/top-additions?min_delta=1.0`);
                if (res.ok) {
                    const data = await res.json();
                    this.institutionalData.topAdditions = data;

                    // Update KPI counters
                    const kpiCount = document.getElementById('kpiTopAdditionsCount');
                    const kpiLeader = document.getElementById('kpiTopAdditionLeader');
                    const kpiLeaderSub = document.getElementById('kpiTopAdditionLeaderSub');
                    const kpiInflow = document.getElementById('kpiTopAdditionInflow');
                    const kpiMegaCount = document.getElementById('kpiHistoricalMegaCount');

                    if (kpiCount) {
                        kpiCount.innerText = `${data.latest_count || (data.latest_additions ? data.latest_additions.length : 0)} Setups`;
                    }
                    if (kpiLeader && data.latest_additions && data.latest_additions.length > 0) {
                        const top = data.latest_additions[0];
                        kpiLeader.innerText = `+${top.increase_pct}% (${top.ticker.replace('.NS', '')})`;
                        if (kpiLeaderSub) {
                            kpiLeaderSub.innerText = `FII +${top.fii_delta_pct}% · DII +${top.dii_delta_pct}% · +₹${top.increase_amount_cr} Cr`;
                        }
                    }
                    if (kpiInflow && data.total_inflow_cr) {
                        kpiInflow.innerText = `+₹${Number(data.total_inflow_cr).toLocaleString()} Cr`;
                    }
                    if (kpiMegaCount && data.historical_surges) {
                        kpiMegaCount.innerText = `${data.historical_surges.length} Surges`;
                    }

                    this.renderTopAdditionsTable(data.latest_additions || []);
                    this.renderHistoricalAdditionsTable(data.historical_surges || []);
                }
            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading top additions:', e);
            }
        },

        renderTopAdditionsTable(items) {
            const tbody = document.getElementById('instTopAdditionsTableBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="10" style="padding:2rem;text-align:center;color:#64748b;">No high-conviction stake additions exceeding threshold.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const fundsInStr = `<span style="color:#34d399;font-weight:700;">+${it.funds_accumulating_count || 0} in</span> / <span style="color:#f87171;">-${it.funds_selling_count || 0} out</span>`;
                const ret7d = it.return_7d_pct != null ? it.return_7d_pct : 0;
                const ret30d = it.return_30d_pct != null ? it.return_30d_pct : 0;
                const ret7dCol = ret7d >= 0 ? '#34d399' : '#f87171';
                const ret30dCol = ret30d >= 0 ? '#34d399' : '#f87171';

                const increaseAmount = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);
                const totalAmount = it.total_amount_cr != null ? it.total_amount_cr : (it.total_institutional_amount_cr || 0);

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.75rem;font-family:var(--font-mono);font-weight:700;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">
                            <span style="color:#38bdf8;font-size:0.82rem;">${it.ticker.replace('.NS', '')}</span>
                            <div style="font-size:0.68rem;color:#94a3b8;font-weight:400;">${it.company_name || ''}</div>
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#34d399;font-size:0.84rem;">
                            +${it.increase_pct}%
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#34d399;">
                            +₹${Number(increaseAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">
                            ₹${Number(totalAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-size:0.68rem;color:#cbd5e1;font-family:var(--font-mono);line-height:1.35;">
                            <div>FII: <span style="color:#38bdf8;font-weight:700;">${it.fii_stake_pct}%</span> (+${it.fii_delta_pct}%)</div>
                            <div>DII: <span style="color:#34d399;font-weight:700;">${it.dii_stake_pct}%</span> (+${it.dii_delta_pct}%)</div>
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${it.total_institutional_stake_pct}%</td>
                        <td style="padding:0.65rem 0.6rem;">
                            <div style="font-family:var(--font-mono);font-weight:800;color:#38bdf8;font-size:0.75rem;">${it.accumulation_score} / 100</div>
                            <span class="signal-badge" style="background:${it.verdict_badge === 'emerald' ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)'};color:${it.verdict_badge === 'emerald' ? '#34d399' : '#60a5fa'};font-size:0.64rem;padding:0.1rem 0.35rem;margin-top:0.2rem;display:inline-block;">${it.verdict}</span>
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-size:0.7rem;">${fundsInStr}</td>
                        <td style="padding:0.65rem 0.4rem;font-family:var(--font-mono);font-size:0.68rem;">
                            <div style="color:${ret7dCol};">7D: ${ret7d >= 0 ? '+' : ''}${ret7d}%</div>
                            <div style="color:${ret30dCol};">30D: ${ret30d >= 0 ? '+' : ''}${ret30d}%</div>
                        </td>
                        <td style="padding:0.65rem 0.5rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.25rem 0.55rem;background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);">Inspect</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        renderHistoricalAdditionsTable(items) {
            const tbody = document.getElementById('instHistoricalAdditionsTableBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="10" style="padding:2rem;text-align:center;color:#64748b;">No historical surges on record.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const ret30 = it.return_30d_pct != null ? it.return_30d_pct : 0;
                const ret30Col = ret30 >= 0 ? '#34d399' : '#f87171';
                const increaseAmount = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);
                const totalAmount = it.total_amount_cr != null ? it.total_amount_cr : (it.total_institutional_amount_cr || 0);

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.75rem;font-family:var(--font-mono);font-weight:700;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">
                            <span style="color:#fbbf24;font-size:0.82rem;">${it.ticker.replace('.NS', '')}</span>
                            <div style="font-size:0.68rem;color:#94a3b8;font-weight:400;">${it.company_name || ''}</div>
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-size:0.72rem;color:#cbd5e1;">${it.quarter} vs ${it.prev_quarter}</td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#fbbf24;font-size:0.84rem;">
                            +${it.increase_pct || it.inst_addition_pct}%
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#fbbf24;">
                            +₹${Number(increaseAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">
                            ₹${Number(totalAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-size:0.68rem;color:#cbd5e1;font-family:var(--font-mono);line-height:1.35;">
                            <div>FII: <span style="color:#38bdf8;font-weight:700;">+${it.fii_surge_pct}%</span></div>
                            <div>DII: <span style="color:#34d399;font-weight:700;">+${it.dii_surge_pct}%</span></div>
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);color:#cbd5e1;font-size:0.72rem;">
                            <span style="color:#94a3b8;">${it.historical_stake_pct}%</span> → <span style="color:#38bdf8;font-weight:700;">${it.current_stake_pct}%</span>
                        </td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:800;color:#fbbf24;">${it.accumulation_score} / 100</td>
                        <td style="padding:0.65rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:${ret30Col};">${ret30 >= 0 ? '+' : ''}${ret30}%</td>
                        <td style="padding:0.65rem 0.5rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.25rem 0.55rem;background:rgba(251,191,36,0.12);color:#fbbf24;border:1px solid rgba(251,191,36,0.35);">Inspect</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async searchInstitutionalStock(ticker, autoSwitch = true) {
            if (!ticker) return;
            const cleanTicker = ticker.trim().toUpperCase();
            this._selectedTicker = cleanTicker;
            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.institutionalData.currentStock = data;
                    this.renderStockInstitutionalDetails(data);
                    if (autoSwitch && this.institutionalSubPage !== 'equities') {
                        this.switchInstitutionalPage('equities');
                    }
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

            if (tickerEl) tickerEl.textContent = data.ticker;
            if (nameEl) nameEl.textContent = data.company_name || '';
            if (badgeEl) {
                badgeEl.textContent = data.verdict;
                badgeEl.style.background = data.verdict_badge === 'emerald' ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                badgeEl.style.color = data.verdict_badge === 'emerald' ? '#34d399' : '#60a5fa';
            }
            if (scoreTextEl) {
                const incPctStr = data.increase_pct != null ? `${data.increase_pct >= 0 ? '+' : ''}${data.increase_pct}%` : '0.0%';
                const incAmtStr = data.increase_amount_cr != null ? `${data.increase_amount_cr >= 0 ? '+' : ''}₹${Number(data.increase_amount_cr).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr` : `+₹${data.net_flow_cr || 0} Cr`;
                const totAmtStr = data.total_amount_cr != null ? `₹${Number(data.total_amount_cr).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr` : '—';

                scoreTextEl.innerHTML = `Accumulation Score: <strong style="color:#38bdf8;">${data.accumulation_score} / 100</strong> | Net Increase: <strong style="color:#34d399;">${incAmtStr} (${incPctStr})</strong> | Total Inst Value: <strong style="color:#38bdf8;">${totAmtStr}</strong> | Funds In/Out (QoQ): <strong style="color:#34d399;">+${data.funds_accumulating_count}</strong> / <strong style="color:#f87171;">-${data.funds_selling_count}</strong>`;
            }

            // 1. Shareholding pattern history
            const patContainer = document.getElementById('instShareholdingPatternContainer');
            if (patContainer) {
                const pats = data.shareholding_patterns || [];
                if (!pats.length) {
                    patContainer.innerHTML = '<div style="color:#64748b;font-size:0.72rem;padding:0.5rem;">No historical shareholding filings found.</div>';
                } else {
                    patContainer.innerHTML = `
                        <table style="width:100%;font-size:0.72rem;text-align:left;border-collapse:collapse;">
                            <thead>
                                <tr style="color:#94a3b8;border-bottom:1px solid rgba(255,255,255,0.06);font-family:var(--font-mono);">
                                    <th style="padding:0.35rem 0.5rem;">QUARTER</th>
                                    <th style="padding:0.35rem 0.5rem;text-align:right;">STOCK PRICE</th>
                                    <th style="padding:0.35rem 0.5rem;text-align:right;">PROMOTER</th>
                                    <th style="padding:0.35rem 0.5rem;text-align:right;">FII / FPI</th>
                                    <th style="padding:0.35rem 0.5rem;text-align:right;">DII / MUTUAL FUNDS</th>
                                    <th style="padding:0.35rem 0.5rem;text-align:right;">RETAIL / PUBLIC</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${pats.map((p, idx) => {
                                    const prevP = pats[idx + 1];
                                    const fiiDelta = prevP ? (p.fii_pct - prevP.fii_pct) : 0;
                                    const diiDelta = prevP ? (p.dii_mf_pct - prevP.dii_mf_pct) : 0;
                                    const fiiDeltaStr = prevP ? (fiiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${fiiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${fiiDelta.toFixed(2)}%)</span>`) : '';
                                    const diiDeltaStr = prevP ? (diiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${diiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${diiDelta.toFixed(2)}%)</span>`) : '';

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
                                            <td style="padding:0.4rem 0.5rem;font-weight:700;color:#f8fafc;font-family:var(--font-mono);">${p.quarter}</td>
                                            <td style="padding:0.4rem 0.5rem;text-align:right;font-family:var(--font-mono);">${priceHtml}</td>
                                            <td style="padding:0.4rem 0.5rem;text-align:right;color:#cbd5e1;font-family:var(--font-mono);">${p.promoter_pct}%</td>
                                            <td style="padding:0.4rem 0.5rem;text-align:right;color:#38bdf8;font-weight:700;font-family:var(--font-mono);">${p.fii_pct}% ${fiiDeltaStr}</td>
                                            <td style="padding:0.4rem 0.5rem;text-align:right;color:#34d399;font-weight:700;font-family:var(--font-mono);">${p.dii_mf_pct}% ${diiDeltaStr}</td>
                                            <td style="padding:0.4rem 0.5rem;text-align:right;color:#94a3b8;font-family:var(--font-mono);">${p.public_retail_pct}%</td>
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
                    dealsContainer.innerHTML = '<div style="color:#64748b;font-size:0.72rem;padding:0.5rem;">No recent bulk or block deals recorded for this ticker.</div>';
                } else {
                    dealsContainer.innerHTML = deals.map(d => {
                        const isBuy = d.deal_type === 'BUY';
                        const bg = isBuy ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
                        const col = isBuy ? '#34d399' : '#f87171';
                        return `
                            <div style="background:${bg};border:1px solid ${isBuy ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:4px;padding:0.35rem 0.55rem;margin-bottom:0.35rem;display:flex;justify-content:space-between;align-items:center;font-size:0.72rem;">
                                <div>
                                    <span style="font-weight:700;color:${col};font-family:var(--font-mono);margin-right:0.35rem;">[${d.deal_type}]</span>
                                    <strong style="color:#f8fafc;">${d.client_name}</strong>
                                </div>
                                <div style="font-family:var(--font-mono);color:#cbd5e1;text-align:right;">
                                    ${d.quantity.toLocaleString()} shares @ ₹${d.price} (₹${d.value_cr} Cr) | <span style="color:#94a3b8;">${d.deal_date}</span>
                                </div>
                            </div>
                        `;
                    }).join('');
                }
            }

            // 3. Fund-by-Fund Table (Render 3 Distinct Financial Metrics)
            const tbody = document.getElementById('instStockHoldingsTableBody');
            if (tbody) {
                const holdings = data.holdings || [];
                if (!holdings.length) {
                    tbody.innerHTML = '<tr><td colspan="10" style="padding:2rem;text-align:center;color:#64748b;">No fund positions recorded for this ticker yet.</td></tr>';
                    return;
                }

                tbody.innerHTML = holdings.map(h => {
                    const act = h.action;
                    const isBuy = act === 'NEW BUY';
                    const isAcc = act === 'ACCUMULATED';
                    const isTrim = act === 'TRIMMED';
                    const isSold = act === 'SOLD OUT';

                    const actBg = isBuy ? 'rgba(56,189,248,0.15)' : isAcc ? 'rgba(16,185,129,0.15)' : isTrim ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)';
                    const actCol = isBuy ? '#38bdf8' : isAcc ? '#34d399' : isTrim ? '#fbbf24' : '#f87171';
                    
                    // Metric 1: Increase by Percentage
                    const changePct = h.change_pct != null ? h.change_pct : 0;
                    const changeStr = changePct > 0 ? `+${changePct}%` : `${changePct}%`;

                    // Metric 2: Increase by Amount (₹ Cr)
                    const incAmountCr = h.increase_amount_cr != null ? h.increase_amount_cr : 0;
                    const incAmountCol = incAmountCr >= 0 ? '#34d399' : '#f87171';
                    const incAmountStr = `${incAmountCr >= 0 ? '+' : ''}₹${Number(incAmountCr).toFixed(2)} Cr`;

                    // Metric 3: Total Amount (₹ Cr)
                    const totAmountCr = h.total_amount_cr != null ? h.total_amount_cr : (h.holding_value_cr || 0);

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.6rem 0.8rem;font-weight:700;color:#f8fafc;">${h.fund_name}</td>
                            <td style="padding:0.6rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${h.fund_type}</td>
                            <td style="padding:0.6rem 0.8rem;">
                                <span class="signal-badge" style="background:${actBg};color:${actCol};font-size:0.68rem;padding:0.12rem 0.4rem;">${h.action}</span>
                            </td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${h.stake_pct}%</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;font-weight:600;">₹${h.avg_price != null ? Number(h.avg_price).toFixed(2) : '—'}</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#a7f3d0;font-weight:600;">₹${h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : '—'}</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${actCol};">${changeStr}</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${incAmountCol};">${incAmountStr}</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#38bdf8;">₹${Number(totAmountCr).toFixed(2)} Cr</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#64748b;font-size:0.7rem;">${h.reported_date || '—'}</td>
                        </tr>
                    `;
                }).join('');
            }
        },

        async inspectFundPortfolio(fundName) {
            if (!fundName) return;
            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/fund/${encodeURIComponent(fundName)}`);
                if (res.ok) {
                    const data = await res.json();
                    const holdings = data.holdings || [];

                    const modal = document.getElementById('instFundModal');
                    const titleEl = document.getElementById('instFundModalTitle');
                    const subEl = document.getElementById('instFundModalSubtitle');
                    const tbody = document.getElementById('instFundModalTableBody');

                    if (titleEl) {
                        titleEl.innerHTML = `<span>💼</span> ${data.fund_name || fundName}`;
                    }
                    if (subEl) {
                        subEl.innerText = `${data.fund_type || 'Fund'} Portfolio · ${holdings.length} Positions Tracked · Total Tracked Value: ₹${Number(data.total_aum_tracked_cr || 0).toLocaleString()} Cr`;
                    }

                    if (tbody) {
                        if (!holdings.length) {
                            tbody.innerHTML = '<tr><td colspan="13" style="padding:2rem;text-align:center;color:#64748b;">No portfolio positions recorded for this fund.</td></tr>';
                        } else {
                            tbody.innerHTML = holdings.map(h => {
                                const act = h.action;
                                const isBuy = act === 'NEW BUY';
                                const isAcc = act === 'ACCUMULATED';
                                const isTrim = act === 'TRIMMED';
                                const actBg = isBuy ? 'rgba(56,189,248,0.15)' : isAcc ? 'rgba(16,185,129,0.15)' : isTrim ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)';
                                const actCol = isBuy ? '#38bdf8' : isAcc ? '#34d399' : isTrim ? '#fbbf24' : '#f87171';

                                const ret30 = h.return_30d_pct != null ? h.return_30d_pct : 0;
                                const ret1y = h.return_1y_pct != null ? h.return_1y_pct : 0;
                                const ret30Col = ret30 >= 0 ? '#34d399' : '#f87171';
                                const ret1yCol = ret1y >= 0 ? '#34d399' : '#f87171';

                                // 3 Distinct Metrics
                                const changePct = h.change_pct != null ? h.change_pct : 0;
                                const changeStr = changePct > 0 ? `+${changePct}%` : `${changePct}%`;
                                const incAmountCr = h.increase_amount_cr != null ? h.increase_amount_cr : 0;
                                const incAmountCol = incAmountCr >= 0 ? '#34d399' : '#f87171';
                                const incAmountStr = `${incAmountCr >= 0 ? '+' : ''}₹${Number(incAmountCr).toFixed(2)} Cr`;
                                const totAmountCr = h.total_amount_cr != null ? h.total_amount_cr : (h.holding_value_cr || 0);

                                return `
                                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;cursor:pointer;" onclick="app.closeFundModal(); app.searchInstitutionalStock('${h.ticker}');">
                                            <span style="color:#38bdf8;">${h.ticker.replace('.NS', '')}</span>
                                            <div style="font-size:0.66rem;color:#94a3b8;font-weight:400;">${h.company_name || ''}</div>
                                        </td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;font-size:0.72rem;">${h.quarter || 'Q1 FY27'}</td>
                                        <td style="padding:0.6rem 0.8rem;">
                                            <span class="signal-badge" style="background:${actBg};color:${actCol};font-size:0.68rem;padding:0.12rem 0.4rem;">${h.action}</span>
                                        </td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${h.stake_pct}%</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${actCol};">${changeStr}</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${incAmountCol};">${incAmountStr}</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#38bdf8;">₹${Number(totAmountCr).toFixed(2)} Cr</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${ret30Col};">${ret30 >= 0 ? '+' : ''}${ret30}%</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${ret1yCol};">${ret1y >= 0 ? '+' : ''}${ret1y}%</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;">₹${h.avg_price != null ? Number(h.avg_price).toFixed(2) : '—'}</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#a7f3d0;">₹${h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : '—'}</td>
                                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#64748b;font-size:0.7rem;">${h.reported_date || '—'}</td>
                                        <td style="padding:0.6rem 0.8rem;text-align:center;">
                                            <button type="button" onclick="app.closeFundModal(); app.searchInstitutionalStock('${h.ticker}');" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.2rem 0.5rem;">Inspect</button>
                                        </td>
                                    </tr>
                                `;
                            }).join('');
                        }
                    }

                    if (modal) {
                        modal.style.display = 'flex';
                    }
                }
            } catch (e) {
                console.error('Error fetching fund portfolio:', e);
            }
        },

        closeFundModal() {
            const modal = document.getElementById('instFundModal');
            if (modal) {
                modal.style.display = 'none';
            }
        }
    });

})(); // end institutional IIFE