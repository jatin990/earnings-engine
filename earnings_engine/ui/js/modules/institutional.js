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
                    const kpiInflow = document.getElementById('kpiTopAdditionInflowLeader') || document.getElementById('kpiTopAdditionInflow');
                    const kpiInflowSub = document.getElementById('kpiTopAdditionInflowLeaderSub');
                    const kpiMegaCount = document.getElementById('kpiHistoricalSurgesCount') || document.getElementById('kpiHistoricalMegaCount');

                    if (kpiCount) {
                        kpiCount.innerText = `${data.latest_count || (data.latest_additions ? data.latest_additions.length : 0)} Setups`;
                    }
                    if (kpiLeader && data.latest_additions && data.latest_additions.length > 0) {
                        const top = data.latest_additions[0];
                        kpiLeader.innerText = `+${top.increase_pct}% (${top.ticker.replace('.NS', '')})`;
                        if (kpiLeaderSub) {
                            kpiLeaderSub.innerText = `FII +${top.fii_delta_pct || 0}% · DII +${top.dii_delta_pct || 0}% · +₹${top.increase_amount_cr || 0} Cr`;
                        }
                    }
                    if (kpiInflow) {
                        const totalInflow = data.total_inflow_cr || (data.latest_additions ? data.latest_additions.reduce((acc, x) => acc + (x.increase_amount_cr || 0), 0) : 0);
                        kpiInflow.innerText = `+₹${Number(Number(totalInflow).toFixed(0)).toLocaleString()} Cr`;
                        if (kpiInflowSub && data.latest_additions && data.latest_additions.length > 0) {
                            const topStock = data.latest_additions[0];
                            kpiInflowSub.innerText = `Led by ${topStock.ticker.replace('.NS', '')}`;
                        }
                    }
                    if (kpiMegaCount) {
                        const count = data.historical_count || (data.historical_surges ? data.historical_surges.length : (data.historical_additions ? data.historical_additions.length : 0));
                        kpiMegaCount.innerText = `${count} Surges`;
                    }

                    this.renderTopAdditionsTable(data.latest_additions || []);
                    this.renderHistoricalAdditionsTable(data.historical_surges || data.historical_additions || []);
                }
            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading top additions:', e);
            }
        },

        renderTopAdditionsTable(items) {
            const tbody = document.getElementById('instTopAdditionsTableBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="8" style="padding:2rem;text-align:center;color:#71717a;">No high-conviction stake additions exceeding threshold.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const fundsInStr = `<span style="color:#ffffff;font-weight:700;">+${it.funds_accumulating_count || 0}</span> / <span style="color:#71717a;">-${it.funds_selling_count || 0}</span>`;
                const ret7d = it.return_7d_pct != null ? it.return_7d_pct : 0;
                const ret30d = it.return_30d_pct != null ? it.return_30d_pct : 0;
                const ret7dCol = ret7d >= 0 ? '#34d399' : '#f87171';
                const ret30dCol = ret30d >= 0 ? '#34d399' : '#f87171';

                const increaseAmount = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);
                const totalAmount = it.total_amount_cr != null ? it.total_amount_cr : (it.total_institutional_amount_cr || 0);
                const incPct = it.increase_pct != null ? it.increase_pct : (it.inst_addition_pct != null ? it.inst_addition_pct : 0);

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.55rem 0.65rem;font-family:var(--font-mono);font-weight:700;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}', false)">
                            <span style="color:#ffffff;font-size:0.82rem;">${it.ticker.replace('.NS', '')}</span>
                            <div style="font-size:0.68rem;color:#71717a;font-weight:400;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${it.company_name || ''}</div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:800;color:#ffffff;font-size:0.82rem;">
                            +${incPct}%
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;">
                            +₹${Number(increaseAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#a1a1aa;">
                            ₹${Number(totalAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-size:0.68rem;color:#a1a1aa;font-family:var(--font-mono);line-height:1.35;">
                            <div>FII: <span style="color:#ffffff;font-weight:700;">${it.fii_stake_pct || 0}%</span> (+${it.fii_delta_pct || 0}%)</div>
                            <div>DII: <span style="color:#ffffff;font-weight:700;">${it.dii_stake_pct || 0}%</span> (+${it.dii_delta_pct || 0}%)</div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${fundsInStr}</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">
                            <div style="color:${ret7dCol};">7D: ${ret7d >= 0 ? '+' : ''}${ret7d}%</div>
                            <div style="color:${ret30dCol};">30D: ${ret30d >= 0 ? '+' : ''}${ret30d}%</div>
                        </td>
                        <td style="padding:0.55rem 0.4rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}', false)" class="btn btn-sm" style="font-size:0.65rem;padding:0.2rem 0.5rem;background:#18181b;color:#ffffff;border:1px solid rgba(255,255,255,0.25);border-radius:4px;cursor:pointer;">Inspect</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        renderHistoricalAdditionsTable(items) {
            const tbody = document.getElementById('instHistoricalAdditionsTableBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="8" style="padding:2rem;text-align:center;color:#71717a;">No historical surges on record.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const increaseAmount = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);
                const totalAmount = it.total_amount_cr != null ? it.total_amount_cr : (it.total_institutional_amount_cr || 0);
                const comparisonStr = it.quarter_comparison || ((it.target_quarter && it.baseline_quarter) ? `${it.target_quarter} vs ${it.baseline_quarter}` : (it.quarter && it.prev_quarter ? `${it.quarter} vs ${it.prev_quarter}` : 'Prior Filings'));
                const incPct = it.increase_pct != null ? it.increase_pct : (it.inst_addition_pct != null ? it.inst_addition_pct : 0);
                const fiiDelta = it.fii_delta_pct != null ? it.fii_delta_pct : (it.fii_surge_pct != null ? it.fii_surge_pct : 0);
                const diiDelta = it.dii_delta_pct != null ? it.dii_delta_pct : (it.dii_surge_pct != null ? it.dii_surge_pct : 0);
                const histStake = it.historical_stake_pct != null ? `${it.historical_stake_pct}%` : '—';
                const currStake = (it.current_total_stake_pct != null ? it.current_total_stake_pct : (it.current_stake_pct != null ? it.current_stake_pct : null));
                const stakeFlowStr = currStake != null ? `<span style="color:#71717a;">${histStake}</span> &rarr; <span style="color:#ffffff;font-weight:700;">${currStake}%</span>` : `<span style="color:#ffffff;font-weight:700;">${histStake}</span>`;

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.55rem 0.65rem;font-family:var(--font-mono);font-weight:700;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}', false)">
                            <span style="color:#ffffff;font-size:0.82rem;">${it.ticker.replace('.NS', '')}</span>
                            <div style="font-size:0.68rem;color:#71717a;font-weight:400;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${it.company_name || ''}</div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;color:#a1a1aa;">${comparisonStr}</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:800;color:#ffffff;font-size:0.82rem;">
                            +${incPct}%
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;">
                            +₹${Number(increaseAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#a1a1aa;">
                            ₹${Number(totalAmount).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-size:0.68rem;color:#a1a1aa;font-family:var(--font-mono);line-height:1.35;">
                            <div>FII: <span style="color:#ffffff;font-weight:700;">+${fiiDelta}%</span></div>
                            <div>DII: <span style="color:#ffffff;font-weight:700;">+${diiDelta}%</span></div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">
                            ${stakeFlowStr}
                        </td>
                        <td style="padding:0.55rem 0.4rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}', false)" class="btn btn-sm" style="font-size:0.65rem;padding:0.2rem 0.5rem;background:#18181b;color:#ffffff;border:1px solid rgba(255,255,255,0.25);border-radius:4px;cursor:pointer;">Inspect</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        toggleSurgeSort(type) {
            const btnPct = document.getElementById('btnSurgeSort-pct');
            const btnAmt = document.getElementById('btnSurgeSort-amt');
            const topAdditions = this.institutionalData.topAdditions;
            const surges = topAdditions ? (topAdditions.historical_surges || topAdditions.historical_additions || []) : [];

            if (type === 'pct') {
                if (btnPct) {
                    btnPct.style.background = '#ffffff';
                    btnPct.style.color = '#09090b';
                    btnPct.style.borderColor = '#ffffff';
                    btnPct.style.fontWeight = '700';
                }
                if (btnAmt) {
                    btnAmt.style.background = 'transparent';
                    btnAmt.style.color = '#a1a1aa';
                    btnAmt.style.borderColor = 'transparent';
                    btnAmt.style.fontWeight = '500';
                }
                const sorted = [...surges].sort((a, b) => {
                    const pctB = b.increase_pct != null ? b.increase_pct : (b.inst_addition_pct || 0);
                    const pctA = a.increase_pct != null ? a.increase_pct : (a.inst_addition_pct || 0);
                    return pctB - pctA;
                });
                this.renderHistoricalAdditionsTable(sorted);
            } else {
                if (btnAmt) {
                    btnAmt.style.background = '#ffffff';
                    btnAmt.style.color = '#09090b';
                    btnAmt.style.borderColor = '#ffffff';
                    btnAmt.style.fontWeight = '700';
                }
                if (btnPct) {
                    btnPct.style.background = 'transparent';
                    btnPct.style.color = '#a1a1aa';
                    btnPct.style.borderColor = 'transparent';
                    btnPct.style.fontWeight = '500';
                }
                const sorted = [...surges].sort((a, b) => {
                    const amtB = b.increase_amount_cr != null ? b.increase_amount_cr : (b.net_flow_cr || 0);
                    const amtA = a.increase_amount_cr != null ? a.increase_amount_cr : (a.net_flow_cr || 0);
                    return amtB - amtA;
                });
                this.renderHistoricalAdditionsTable(sorted);
            }
        },

        async searchInstitutionalStock(ticker, autoSwitch = true) {
            if (!ticker) return;
            const cleanTicker = ticker.trim().toUpperCase().endsWith('.NS') ? ticker.trim().toUpperCase() : ticker.trim().toUpperCase() + '.NS';
            this._selectedTicker = cleanTicker;
            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.institutionalData.currentStock = data;
                    this.renderStockInstitutionalDetails(data);
                    if (autoSwitch && this.institutionalSubPage === 'investors') {
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

            // Page 1 Elements
            const tickerEl = document.getElementById('instSelectedTicker');
            const nameEl = document.getElementById('instSelectedCompanyName');
            const badgeEl = document.getElementById('instSelectedVerdictBadge');
            const scoreTextEl = document.getElementById('instSelectedScoreText');
            const linkEl = document.getElementById('instSelectedStockLink');

            // Page 3 Elements
            const topTickerEl = document.getElementById('instTopSelectedTicker');
            const topNameEl = document.getElementById('instTopSelectedCompanyName') || document.getElementById('instTopSelectedCompany');
            const topBadgeEl = document.getElementById('instTopSelectedVerdictBadge');
            const topSubtitleEl = document.getElementById('instTopSelectedStockSubtitle');
            const topScoreTextEl = document.getElementById('instTopSelectedScoreText');
            const topLinkEl = document.getElementById('instTopSelectedStockLink') || document.getElementById('instTopSelectedStockDeepLink');

            // Populate Page 1 Header
            if (tickerEl) tickerEl.textContent = data.ticker;
            if (nameEl) nameEl.textContent = data.company_name || '';
            if (badgeEl) {
                badgeEl.textContent = data.verdict || 'Institutional Activity';
                badgeEl.style.background = data.verdict_badge === 'emerald' ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                badgeEl.style.color = data.verdict_badge === 'emerald' ? '#34d399' : '#60a5fa';
            }
            if (scoreTextEl) {
                scoreTextEl.innerHTML = `Accumulation Score: <strong style="color:#ffffff;">${data.accumulation_score} / 100</strong> · Inflow: <strong style="color:#ffffff;">+₹${Number(data.gross_inflow_cr || 0).toLocaleString()} Cr</strong> · Outflow: <strong style="color:#f87171;">-₹${Number(data.gross_outflow_cr || 0).toLocaleString()} Cr</strong> · Net: <strong style="color:#ffffff;">+₹${Number(data.net_flow_cr || 0).toLocaleString()} Cr</strong>`;
            }
            if (linkEl) linkEl.href = `/stock/${data.ticker}`;

            // Populate Page 3 Header (Crisp Monochrome)
            if (topTickerEl) topTickerEl.textContent = data.ticker;
            if (topNameEl) topNameEl.textContent = data.company_name || '';
            if (topBadgeEl) {
                topBadgeEl.textContent = data.verdict || 'Top Institutional Addition';
                topBadgeEl.style.background = '#18181b';
                topBadgeEl.style.color = '#f4f4f5';
                topBadgeEl.style.border = '1px solid rgba(255,255,255,0.25)';
            }
            const incPctStr = data.increase_pct != null ? `${data.increase_pct >= 0 ? '+' : ''}${data.increase_pct}%` : `${data.total_institutional_stake_pct || 0}%`;
            const incAmtStr = data.increase_amount_cr != null ? `+₹${Number(data.increase_amount_cr).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr` : `+₹${data.net_flow_cr || 0} Cr`;
            const totAmtStr = data.total_amount_cr != null ? `₹${Number(data.total_amount_cr).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr` : '—';

            const subtitleHtml = `Inflow: <b style="color:#ffffff;">${incAmtStr}</b> · Current Stake: <b style="color:#ffffff;">${data.total_institutional_stake_pct || '—'}%</b> · FII Surge: <b style="color:#ffffff;">+${data.fii_delta_pct || 0}%</b>`;
            if (topSubtitleEl) topSubtitleEl.innerHTML = subtitleHtml;
            if (topScoreTextEl) topScoreTextEl.innerHTML = `Inflow: <strong style="color:#ffffff;">${incAmtStr}</strong> · Stake: <strong style="color:#ffffff;">${incPctStr}</strong> · Total: <strong style="color:#ffffff;">${totAmtStr}</strong>`;
            if (topLinkEl) topLinkEl.href = `/stock/${data.ticker}`;

            // 1. Shareholding Pattern History (Rendered to both Page 1 and Page 3)
            const pats = data.shareholding_patterns || [];
            let patTableHtml = '';
            if (!pats.length) {
                patTableHtml = '<div style="color:#71717a;font-size:0.72rem;padding:0.75rem;text-align:center;">No historical shareholding filings found.</div>';
            } else {
                patTableHtml = `
                    <table style="width:100%;font-size:0.72rem;text-align:left;border-collapse:collapse;">
                        <thead>
                            <tr style="color:#a1a1aa;border-bottom:1px solid rgba(255,255,255,0.12);font-family:var(--font-mono);font-size:0.68rem;">
                                <th style="padding:0.35rem 0.5rem;">QUARTER</th>
                                <th style="padding:0.35rem 0.5rem;text-align:right;">STOCK PRICE</th>
                                <th style="padding:0.35rem 0.5rem;text-align:right;">PROMOTER</th>
                                <th style="padding:0.35rem 0.5rem;text-align:right;">FII / FPI</th>
                                <th style="padding:0.35rem 0.5rem;text-align:right;">DII / MUTUAL FUNDS</th>
                                <th style="padding:0.35rem 0.5rem;text-align:right;">PUBLIC / RETAIL</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${pats.map((p, idx) => {
                                const fiiDelta = p.fii_delta_pct != null ? p.fii_delta_pct : (idx < pats.length - 1 ? (p.fii_pct - pats[idx+1].fii_pct) : 0);
                                const diiDelta = p.dii_delta_pct != null ? p.dii_delta_pct : (idx < pats.length - 1 ? (p.dii_mf_pct - pats[idx+1].dii_mf_pct) : 0);
                                const fiiDeltaStr = fiiDelta !== 0 ? `<span style="color:${fiiDelta > 0 ? '#34d399' : '#f87171'};font-size:0.62rem;">(${fiiDelta > 0 ? '+' : ''}${fiiDelta.toFixed(2)}%)</span>` : '';
                                const diiDeltaStr = diiDelta !== 0 ? `<span style="color:${diiDelta > 0 ? '#34d399' : '#f87171'};font-size:0.62rem;">(${diiDelta > 0 ? '+' : ''}${diiDelta.toFixed(2)}%)</span>` : '';

                                const isCurrentQ = p.is_current_quarter || idx === 0;
                                let priceHtml = '—';
                                if (isCurrentQ) {
                                    const curP = p.current_price != null ? p.current_price : p.stock_price;
                                    const startP = p.quarter_start_price;
                                    const retQ = (curP && startP) ? (((curP - startP) / startP) * 100) : null;
                                    const retStr = retQ != null ? `<span style="color:${retQ >= 0 ? '#34d399' : '#f87171'};font-size:0.60rem;font-weight:700;">(${retQ >= 0 ? '+' : ''}${retQ.toFixed(1)}%)</span>` : '';
                                    priceHtml = `
                                        <div style="font-weight:800;color:#f8fafc;">₹${curP != null ? Number(curP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}) : '—'} <span style="font-size:0.58rem;color:#ffffff;background:#27272a;padding:0.02rem 0.25rem;border-radius:3px;font-weight:700;">Live</span></div>
                                        ${startP ? `<div style="font-size:0.60rem;color:#71717a;">Start: ₹${Number(startP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})} ${retStr}</div>` : ''}
                                    `;
                                } else {
                                    const startP = p.quarter_start_price != null ? p.quarter_start_price : p.stock_price;
                                    priceHtml = `
                                        <div style="font-weight:700;color:#ffffff;">₹${startP != null ? Number(startP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}) : '—'}</div>
                                    `;
                                }

                                return `
                                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                        <td style="padding:0.4rem 0.5rem;font-weight:700;color:#ffffff;font-family:var(--font-mono);">${p.quarter}</td>
                                        <td style="padding:0.4rem 0.5rem;text-align:right;font-family:var(--font-mono);">${priceHtml}</td>
                                        <td style="padding:0.4rem 0.5rem;text-align:right;color:#a1a1aa;font-family:var(--font-mono);">${p.promoter_pct}%</td>
                                        <td style="padding:0.4rem 0.5rem;text-align:right;color:#ffffff;font-weight:700;font-family:var(--font-mono);">${p.fii_pct}% ${fiiDeltaStr}</td>
                                        <td style="padding:0.4rem 0.5rem;text-align:right;color:#ffffff;font-weight:700;font-family:var(--font-mono);">${p.dii_mf_pct}% ${diiDeltaStr}</td>
                                        <td style="padding:0.4rem 0.5rem;text-align:right;color:#71717a;font-family:var(--font-mono);">${p.public_retail_pct}%</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                `;
            }
            const patContainer = document.getElementById('instShareholdingPatternContainer');
            if (patContainer) patContainer.innerHTML = patTableHtml;
            const patContainerTop = document.getElementById('instTopStockQuarterlyTrendContainer');
            if (patContainerTop) patContainerTop.innerHTML = patTableHtml;

            // 2. Block Deals (Rendered to both Page 1 and Page 3)
            const deals = data.block_deals || [];
            let dealsHtml = '';
            if (!deals.length) {
                dealsHtml = '<div style="color:#71717a;font-size:0.72rem;padding:0.75rem;text-align:center;">No recent block/bulk deals recorded.</div>';
            } else {
                dealsHtml = deals.map(d => {
                    const isBuy = d.deal_type === 'BUY';
                    const bg = isBuy ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
                    const col = isBuy ? '#34d399' : '#f87171';
                    return `
                        <div style="background:${bg};border:1px solid ${isBuy ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:4px;padding:0.35rem 0.55rem;margin-bottom:0.35rem;display:flex;justify-content:space-between;align-items:center;font-size:0.72rem;">
                            <div>
                                <span style="font-weight:700;color:${col};font-family:var(--font-mono);margin-right:0.35rem;">[${d.deal_type}]</span>
                                <strong style="color:#ffffff;">${d.client_name}</strong>
                            </div>
                            <div style="font-family:var(--font-mono);color:#a1a1aa;text-align:right;">
                                ${d.quantity.toLocaleString()} shares @ ₹${d.price} (₹${d.value_cr} Cr) | <span style="color:#71717a;">${d.deal_date}</span>
                            </div>
                        </div>
                    `;
                }).join('');
            }
            const dealsContainer = document.getElementById('instBlockDealsContainer');
            if (dealsContainer) dealsContainer.innerHTML = dealsHtml;
            const dealsContainerTop = document.getElementById('instTopBlockDealsContainer') || document.getElementById('instTopStockBlockDealsBody');
            if (dealsContainerTop) dealsContainerTop.innerHTML = dealsHtml;

            // 3. Fund-by-Fund Table (Rendered to both Page 1 and Page 3)
            const holdings = data.holdings || [];
            const fundBadge = document.getElementById('instStockFundCountBadge');
            if (fundBadge) fundBadge.textContent = `${holdings.length} Funds Tracked`;
            const fundBadgeTop = document.getElementById('instTopStockFundCountBadge');
            if (fundBadgeTop) fundBadgeTop.textContent = `${holdings.length} Funds Tracked`;

            const tbody = document.getElementById('instStockHoldingsTableBody');
            const tbodyTop = document.getElementById('instTopStockHoldingsTableBody');

            let holdingsRowsHtml = '';
            if (!holdings.length) {
                holdingsRowsHtml = '<tr><td colspan="10" style="padding:1.5rem;text-align:center;color:#71717a;">No fund positions recorded for this ticker yet.</td></tr>';
            } else {
                holdingsRowsHtml = holdings.map(h => {
                    const act = h.action;
                    const isBuy = act === 'NEW BUY';
                    const isAcc = act === 'ACCUMULATED';
                    const isTrim = act === 'TRIMMED';
                    const actBg = '#18181b';
                    const actCol = isBuy ? '#38bdf8' : isAcc ? '#34d399' : isTrim ? '#fbbf24' : '#f87171';

                    const changePct = h.change_pct != null ? h.change_pct : 0;
                    const changeStr = changePct > 0 ? `+${changePct}%` : `${changePct}%`;

                    const incAmountCr = h.increase_amount_cr != null ? h.increase_amount_cr : 0;
                    const incAmountCol = incAmountCr >= 0 ? '#34d399' : '#f87171';
                    const incAmountStr = `${incAmountCr >= 0 ? '+' : ''}₹${Number(incAmountCr).toFixed(2)} Cr`;
                    const totAmountCr = h.total_amount_cr != null ? h.total_amount_cr : (h.holding_value_cr || 0);

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.5rem 0.6rem;font-weight:700;color:#ffffff;cursor:pointer;" onclick="app.inspectFundPortfolio('${h.fund_name}')">
                                <span style="color:#ffffff;">${h.fund_name}</span>
                            </td>
                            <td style="padding:0.5rem 0.5rem;color:#a1a1aa;font-size:0.68rem;">${h.fund_type}</td>
                            <td style="padding:0.5rem 0.5rem;">
                                <span class="signal-badge" style="background:${actBg};color:${actCol};border:1px solid rgba(255,255,255,0.15);font-size:0.65rem;padding:0.1rem 0.35rem;">${h.action}</span>
                            </td>
                            <td style="padding:0.5rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;">${h.stake_pct}%</td>
                            <td style="padding:0.5rem 0.5rem;font-family:var(--font-mono);color:#a1a1aa;font-size:0.68rem;">₹${h.avg_price != null ? Number(h.avg_price).toFixed(2) : '—'}</td>
                            <td style="padding:0.5rem 0.5rem;font-family:var(--font-mono);color:#71717a;font-size:0.65rem;">${h.recent_buy_price ? `₹${Number(h.recent_buy_price).toFixed(2)}` : '—'}</td>
                            <td style="padding:0.5rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:${actCol};">${changeStr}</td>
                            <td style="padding:0.5rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:${incAmountCol};">${incAmountStr}</td>
                            <td style="padding:0.5rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;">₹${Number(totAmountCr).toFixed(2)} Cr</td>
                            <td style="padding:0.5rem 0.5rem;font-family:var(--font-mono);color:#71717a;font-size:0.68rem;">${h.reported_date || '—'}</td>
                        </tr>
                    `;
                }).join('');
            }
            if (tbody) tbody.innerHTML = holdingsRowsHtml;
            if (tbodyTop) tbodyTop.innerHTML = holdingsRowsHtml;
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
                        titleEl.innerText = data.fund_name || fundName;
                    }
                    if (subEl) {
                        subEl.innerText = `${data.fund_type || 'Fund'} Portfolio · ${holdings.length} Positions Tracked · Total Tracked Value: ₹${Number(data.total_aum_tracked_cr || 0).toLocaleString()} Cr`;
                    }

                    if (tbody) {
                        if (!holdings.length) {
                            tbody.innerHTML = '<tr><td colspan="10" style="padding:2rem;text-align:center;color:#71717a;">No portfolio positions recorded for this fund.</td></tr>';
                        } else {
                            tbody.innerHTML = holdings.map(h => {
                                const act = h.action;
                                const isBuy = act === 'NEW BUY';
                                const isAcc = act === 'ACCUMULATED';
                                const isTrim = act === 'TRIMMED';
                                const actBg = '#18181b';
                                const actCol = isBuy ? '#38bdf8' : isAcc ? '#34d399' : isTrim ? '#fbbf24' : '#f87171';

                                const ret30 = h.return_30d_pct != null ? h.return_30d_pct : 0;
                                const ret1y = h.return_1y_pct != null ? h.return_1y_pct : 0;
                                const ret30Col = ret30 >= 0 ? '#34d399' : '#f87171';
                                const ret1yCol = ret1y >= 0 ? '#34d399' : '#f87171';

                                const changePct = h.change_pct != null ? h.change_pct : 0;
                                const changeStr = changePct > 0 ? `+${changePct}%` : `${changePct}%`;
                                const incAmountCr = h.increase_amount_cr != null ? h.increase_amount_cr : 0;
                                const incAmountCol = incAmountCr >= 0 ? '#34d399' : '#f87171';
                                const incAmountStr = `${incAmountCr >= 0 ? '+' : ''}₹${Number(incAmountCr).toFixed(2)} Cr`;
                                const totAmountCr = h.total_amount_cr != null ? h.total_amount_cr : (h.holding_value_cr || 0);

                                return `
                                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                                        <td style="padding:0.5rem 0.65rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;cursor:pointer;" onclick="app.closeFundModal(); app.searchInstitutionalStock('${h.ticker}', false);">
                                            ${h.ticker.replace('.NS', '')}
                                        </td>
                                        <td style="padding:0.5rem 0.6rem;color:#a1a1aa;font-size:0.72rem;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${h.company_name || ''}</td>
                                        <td style="padding:0.5rem 0.6rem;color:#71717a;font-size:0.68rem;">${h.sector || '—'}</td>
                                        <td style="padding:0.5rem 0.6rem;">
                                            <span class="signal-badge" style="background:${actBg};color:${actCol};border:1px solid rgba(255,255,255,0.15);font-size:0.65rem;padding:0.1rem 0.35rem;">${h.action}</span>
                                        </td>
                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;">₹${Number(totAmountCr).toFixed(2)} Cr</td>
                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);color:#a1a1aa;font-size:0.7rem;">${Number(h.shares || 0).toLocaleString()}</td>
                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;">${h.stake_pct}%</td>
                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:${ret30Col};">${ret30 >= 0 ? '+' : ''}${ret30}%</td>
                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:${ret1yCol};">${ret1y >= 0 ? '+' : ''}${ret1y}%</td>
                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);color:#71717a;font-size:0.68rem;">${h.reported_date || '—'}</td>
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
