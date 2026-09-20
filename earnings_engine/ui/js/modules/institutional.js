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

        // ── Accumulation Table Sort State ──
        _accSortColumn: null,
        _accSortAsc: true,

        // ── Distribution Table Sort State ──
        _distSortColumn: null,
        _distSortAsc: true,

        // ── Funds Table Sort State ──
        _fundsSortColumn: null,
        _fundsSortAsc: true,

        switchInstitutionalView(view) {

            this.institutionalActiveView = view || 'accumulating';

            ['accumulating', 'stock', 'distributing', 'funds'].forEach(v => {

                const el = document.getElementById('instView-' + v);

                const btn = document.getElementById('btnInstTab-' + v);

                if (el) el.style.display = (v === this.institutionalActiveView) ? 'block' : 'none';

                if (btn) {

                    if (v === this.institutionalActiveView) {

                        btn.style.background = '#18181b';

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

                btnAcc.style.background = isAcc ? '#18181b' : 'transparent';

                btnAcc.style.color = isAcc ? '#34d399' : '#94a3b8';

                btnAcc.style.borderColor = isAcc ? 'rgba(16,185,129,0.4)' : 'transparent';

                btnAcc.style.fontWeight = isAcc ? '700' : '500';

            }

            if (btnDist) {

                btnDist.style.background = !isAcc ? '#18181b' : 'transparent';

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

            const pages = ['equities', 'top-additions', 'investors', 'smart-money'];

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

                        btn.style.background = '#18181b';

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

            const sideSmartMoney = document.getElementById('sidebarSubInstSmartMoney');

            if (sideEquities) sideEquities.classList.toggle('active', p === 'equities');

            if (sideAdditions) sideAdditions.classList.toggle('active', p === 'top-additions');

            if (sideInvestors) sideInvestors.classList.toggle('active', p === 'investors');

            if (sideSmartMoney) sideSmartMoney.classList.toggle('active', p === 'smart-money');

            const ctxLabel = document.getElementById('instSubtabContextLabel');
            if (ctxLabel) {
                if (p === 'investors') ctxLabel.textContent = '💼 Smart Portfolios (AMFI)';
                else if (p === 'top-additions') ctxLabel.textContent = '🚀 Top Additions & Unwinds';
                else if (p === 'smart-money') ctxLabel.textContent = '🎯 Smart Money Radar';
                else ctxLabel.textContent = '🏛️ Equities & Stake Radar';
            }



            if (p === 'investors') {

                this.loadSuperInvestors();

            } else if (p === 'top-additions') {

                this.loadTopAdditions();

            } else if (p === 'smart-money') {

                this.loadSmartMoneyRadar();

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



                // Non-blocking load of institutional data integrity health & provenance status

                this.loadInstitutionalIntegrityStatus();



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

                const ret7dStr = it.return_7d_pct != null ? `<span style="color:${it.return_7d_pct >= 0 ? '#34d399' : '#f87171'};font-weight:600;">${it.return_7d_pct >= 0 ? '+' : ''}${it.return_7d_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;

                const ret30dStr = it.return_30d_pct != null ? `<span style="color:${it.return_30d_pct >= 0 ? '#34d399' : '#f87171'};font-weight:600;">${it.return_30d_pct >= 0 ? '+' : ''}${it.return_30d_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;

                const netFlow = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);



                return `

                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">

                        <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">

                            <span style="color:#38bdf8;">${it.ticker.replace('.NS', '')}</span>
                            <button type="button" class="btn-ticker-refresh" onclick="event.stopPropagation(); app.refreshSingleStockPrice('${it.ticker}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.75rem;padding:0 0.15rem;margin-left:0.15rem;opacity:0.75;line-height:1;transition:all 0.15s;" title="Refresh live price for ${it.ticker}">↻</button>

                            <div style="font-size:0.65rem;color:#94a3b8;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px;">${it.company_name || ''}</div>

                        </td>

                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">${it.accumulation_score}</td>

                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);">${ret7dStr}</td>

                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);">${ret30dStr}</td>

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

                const ret7dStr = it.return_7d_pct != null ? `<span style="color:${it.return_7d_pct >= 0 ? '#34d399' : '#f87171'};font-weight:600;">${it.return_7d_pct >= 0 ? '+' : ''}${it.return_7d_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;

                const ret30dStr = it.return_30d_pct != null ? `<span style="color:${it.return_30d_pct >= 0 ? '#34d399' : '#f87171'};font-weight:600;">${it.return_30d_pct >= 0 ? '+' : ''}${it.return_30d_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;

                const netFlow = it.increase_amount_cr != null ? it.increase_amount_cr : (it.net_flow_cr || 0);



                return `

                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">

                        <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;color:#f87171;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">

                            <span>${it.ticker.replace('.NS', '')}</span>
                            <button type="button" class="btn-ticker-refresh" onclick="event.stopPropagation(); app.refreshSingleStockPrice('${it.ticker}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.75rem;padding:0 0.15rem;margin-left:0.15rem;opacity:0.75;line-height:1;transition:all 0.15s;" title="Refresh live price for ${it.ticker}">↻</button>

                            <div style="font-size:0.65rem;color:#94a3b8;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px;">${it.company_name || ''}</div>

                        </td>

                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f87171;">${it.accumulation_score}</td>

                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);">${ret7dStr}</td>

                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);">${ret30dStr}</td>

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

        // ── Sort Accumulating / Distributing Tables (shared column set) ──

        _sortInstitutionalEquities(col, which) {
            const dataKey = which === 'acc' ? 'accumulating' : 'distributing';
            const items = this.institutionalData[dataKey];
            if (!items || !items.length) return;

            const sortKey = which === 'acc' ? '_accSortColumn' : '_distSortColumn';
            const ascKey  = which === 'acc' ? '_accSortAsc'    : '_distSortAsc';

            if (this[sortKey] === col) {
                this[ascKey] = !this[ascKey];
            } else {
                this[sortKey] = col;
                this[ascKey]  = (col === 'ticker');
            }

            const asc = this[ascKey];
            const factor = asc ? 1 : -1;

            // Stable sort: remember original position for tie-breaking
            items.forEach((item, idx) => { item._origIdx = idx; });

            items.sort((a, b) => {
                let vA, vB, cmp;
                switch (col) {
                    case 'ticker':
                        cmp = (a.ticker || '').localeCompare(b.ticker || '');
                        break;
                    case 'score':
                        vA = Number(a.accumulation_score || 0);
                        vB = Number(b.accumulation_score || 0);
                        cmp = vA - vB;
                        break;
                    case 'ret7d':
                        vA = a.return_7d_pct != null ? Number(a.return_7d_pct) : -9999;
                        vB = b.return_7d_pct != null ? Number(b.return_7d_pct) : -9999;
                        cmp = vA - vB;
                        break;
                    case 'ret30d':
                        vA = a.return_30d_pct != null ? Number(a.return_30d_pct) : -9999;
                        vB = b.return_30d_pct != null ? Number(b.return_30d_pct) : -9999;
                        cmp = vA - vB;
                        break;
                    case 'funds':
                        vA = (Number(a.funds_accumulating_count || 0)) - (Number(a.funds_selling_count || 0));
                        vB = (Number(b.funds_accumulating_count || 0)) - (Number(b.funds_selling_count || 0));
                        cmp = vA - vB;
                        break;
                    case 'flow':
                        vA = Number(a.increase_amount_cr != null ? a.increase_amount_cr : (a.net_flow_cr || 0));
                        vB = Number(b.increase_amount_cr != null ? b.increase_amount_cr : (b.net_flow_cr || 0));
                        cmp = vA - vB;
                        break;
                    case 'stake':
                        vA = Number(a.total_institutional_stake || 0);
                        vB = Number(b.total_institutional_stake || 0);
                        cmp = vA - vB;
                        break;
                    default:
                        cmp = 0;
                }
                if (cmp !== 0) return factor * cmp;
                return a._origIdx - b._origIdx; // stable tie-break
            });

            const prefix = which === 'acc' ? 'acc' : 'dist';
            ['ticker', 'score', 'ret7d', 'ret30d', 'funds', 'flow', 'stake'].forEach(c => {
                const icon = document.getElementById(prefix + 'SortIcon-' + c);
                if (icon) {
                    if (c === col) {
                        icon.textContent = asc ? '▲' : '▼';
                        icon.style.color = '#38bdf8';
                    } else {
                        icon.textContent = '↕';
                        icon.style.color = '#71717a';
                    }
                }
            });

            if (which === 'acc') {
                this.renderInstitutionalAccumulatingTable(items);
            } else {
                this.renderInstitutionalDistributingTable(items);
            }
        },

        sortAccumulatingTable(col) {
            this._sortInstitutionalEquities(col, 'acc');
        },

        sortDistributingTable(col) {
            this._sortInstitutionalEquities(col, 'dist');
        },

        // ── Sort Funds Table ──

        sortFundsTable(col) {
            const funds = this.institutionalData.funds;
            if (!funds || !funds.length) return;

            if (this._fundsSortColumn === col) {
                this._fundsSortAsc = !this._fundsSortAsc;
            } else {
                this._fundsSortColumn = col;
                this._fundsSortAsc = (col === 'name' || col === 'category');
            }

            const asc = this._fundsSortAsc;
            const factor = asc ? 1 : -1;

            // Stable sort: remember original position for tie-breaking
            funds.forEach((f, idx) => { f._origIdx = idx; });

            funds.sort((a, b) => {
                let vA, vB, cmp;
                switch (col) {
                    case 'name':
                        cmp = (a.fund_name || '').localeCompare(b.fund_name || '');
                        break;
                    case 'category':
                        cmp = (a.fund_type || '').localeCompare(b.fund_type || '');
                        break;
                    case 'holdings':
                        vA = Number(a.total_positions || 0);
                        vB = Number(b.total_positions || 0);
                        cmp = vA - vB;
                        break;
                    case 'buying':
                        vA = Number(a.buying_actions || 0);
                        vB = Number(b.buying_actions || 0);
                        cmp = vA - vB;
                        break;
                    case 'selling':
                        vA = Number(a.selling_actions || 0);
                        vB = Number(b.selling_actions || 0);
                        cmp = vA - vB;
                        break;
                    case 'ret30d':
                        vA = a.return_30d_pct != null ? Number(a.return_30d_pct) : -9999;
                        vB = b.return_30d_pct != null ? Number(b.return_30d_pct) : -9999;
                        cmp = vA - vB;
                        break;
                    case 'ret1y':
                        vA = a.return_1y_pct != null ? Number(a.return_1y_pct) : -9999;
                        vB = b.return_1y_pct != null ? Number(b.return_1y_pct) : -9999;
                        cmp = vA - vB;
                        break;
                    case 'aum':
                        vA = Number(a.total_aum_tracked_cr || 0);
                        vB = Number(b.total_aum_tracked_cr || 0);
                        cmp = vA - vB;
                        break;
                    default:
                        cmp = 0;
                }
                if (cmp !== 0) return factor * cmp;
                return a._origIdx - b._origIdx; // stable tie-break
            });

            ['name', 'category', 'holdings', 'buying', 'selling', 'ret30d', 'ret1y', 'aum'].forEach(c => {
                const icon = document.getElementById('fundSortIcon-' + c);
                if (icon) {
                    if (c === col) {
                        icon.textContent = asc ? '▲' : '▼';
                        icon.style.color = '#38bdf8';
                    } else {
                        icon.textContent = '↕';
                        icon.style.color = '#71717a';
                    }
                }
            });

            // Re-apply current investor filter after sorting
            this.filterInvestors(this._currentInvestorFilter || 'ALL');
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

                const ret30Str = f.return_30d_pct != null ? `<span style="color:${f.return_30d_pct >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${f.return_30d_pct >= 0 ? '+' : ''}${f.return_30d_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;

                const ret1yStr = f.return_1y_pct != null ? `<span style="color:${f.return_1y_pct >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${f.return_1y_pct >= 0 ? '+' : ''}${f.return_1y_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;



                return `

                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">

                        <td style="padding:0.65rem 0.8rem;font-weight:700;color:#f8fafc;">${f.fund_name}</td>

                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${f.fund_type}</td>

                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;">${f.total_positions} Stocks</td>

                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${f.buying_actions}</td>

                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${f.selling_actions}</td>

                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);">${ret30Str}</td>

                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);">${ret1yStr}</td>

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

                        btn.style.background = '#18181b';

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

                const ret7dStr = it.return_7d_pct != null ? `<div style="color:${it.return_7d_pct >= 0 ? '#34d399' : '#f87171'};">7D: ${it.return_7d_pct >= 0 ? '+' : ''}${it.return_7d_pct}%</div>` : `<div style="color:#71717a;">7D: N/A</div>`;

                const ret30dStr = it.return_30d_pct != null ? `<div style="color:${it.return_30d_pct >= 0 ? '#34d399' : '#f87171'};">30D: ${it.return_30d_pct >= 0 ? '+' : ''}${it.return_30d_pct}%</div>` : `<div style="color:#71717a;">30D: N/A</div>`;



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

                            ${ret7dStr}

                            ${ret30dStr}

                        </td>

                        <td style="padding:0.55rem 0.4rem;text-align:center;">

                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}', false)" class="btn btn-sm" style="font-size:0.65rem;padding:0.2rem 0.5rem;background:#18181b;color:#ffffff;border:1px solid rgba(255,255,255,0.25);border-radius:4px;cursor:pointer;">Inspect</button>

                        </td>

                    </tr>

                `;

            }).join('');

        },



        renderHistoricalAdditionsTable(items) {

            const tbody = document.getElementById('instHistoricalSurgesTableBody') || document.getElementById('instHistoricalAdditionsTableBody');

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



                renderFetchStatusBadge(badgeEl, fetchObj) {
            if (!badgeEl) return;
            if (!fetchObj || fetchObj.status === 'UNTRACKED') {
                badgeEl.textContent = '⚪ Ingestion: Untracked';
                badgeEl.style.background = 'rgba(255,255,255,0.05)';
                badgeEl.style.color = '#a1a1aa';
                badgeEl.style.border = '1px solid rgba(255,255,255,0.15)';
                badgeEl.title = 'No live filing fetch recorded for this stock yet.';
                return;
            }

            const isSuccess = (fetchObj.status || '').toUpperCase() === 'SUCCESS';
            const timeAgo = fetchObj.time_ago || 'Recently';
            if (isSuccess) {
                const src = fetchObj.source === 'EXCHANGE_REGULATORY_FILINGS' ? 'Filings' : (fetchObj.source === 'nse_api' ? 'NSE API' : fetchObj.source || 'Live');
                const entCount = fetchObj.entities_count != null ? `${fetchObj.entities_count} entities` : 'Verified';
                badgeEl.innerHTML = `<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#34d399;margin-right:0.25rem;"></span>Ingestion: Success · ${timeAgo} (${src}, ${entCount})`;
                badgeEl.style.background = 'rgba(16,185,129,0.12)';
                badgeEl.style.color = '#34d399';
                badgeEl.style.border = '1px solid rgba(16,185,129,0.35)';
                badgeEl.title = `Last verified fetch: ${fetchObj.fetched_at || ''} via ${fetchObj.source || ''}`;
            } else {
                const err = fetchObj.error_message || 'Fetch failed';
                badgeEl.innerHTML = `<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#f87171;margin-right:0.25rem;"></span>Ingestion: Failed · ${timeAgo}`;
                badgeEl.style.background = 'rgba(239,68,68,0.12)';
                badgeEl.style.color = '#f87171';
                badgeEl.style.border = '1px solid rgba(239,68,68,0.35)';
                badgeEl.title = `Error: ${err}`;
            }
        },

        async triggerStockShareholdingFetch(ticker) {
            if (!ticker) return;
            const cleanTicker = (ticker || '').trim().toUpperCase();
            const btnP1 = document.getElementById('btnInstRefreshFetchP1');
            const btnP3 = document.getElementById('btnInstRefreshFetchP3');
            const btnForensic = document.getElementById('btnForensicRefreshFetch');

            const p1Err = document.getElementById('instP1IngestErrorBanner');
            const p3Err = document.getElementById('instP3IngestErrorBanner');
            const fErr = document.getElementById('instForensicIngestErrorBanner');

            if (p1Err) p1Err.style.display = 'none';
            if (p3Err) p3Err.style.display = 'none';
            if (fErr) fErr.style.display = 'none';

            [btnP1, btnP3, btnForensic].forEach(b => {
                if (b) {
                    b.disabled = true;
                    b.textContent = '⏳ Ingesting...';
                    b.style.opacity = '0.6';
                }
            });

            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}/fetch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                });

                const data = await res.json();
                if (res.ok && data.success) {
                    await this.loadStockInstitutionalDetails(cleanTicker, false);
                    if (this._smartMoneyForensicDossier && this._smartMoneyForensicDossier.ticker === cleanTicker) {
                        const fRes = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}/forensics`);
                        if (fRes.ok) {
                            this._smartMoneyForensicDossier = await fRes.json();
                            this.renderForensicsTab(this._smartMoneyForensicTab || 'buyers');
                        }
                    }
                } else {
                    const errMsg = data.detail || data.error || 'Ingestion failed across all exchange & regulatory endpoints.';
                    const errHtml = `<strong>⚠️ Ingestion Halted:</strong> ${errMsg}`;
                    if (p1Err) { p1Err.innerHTML = errHtml; p1Err.style.display = 'block'; }
                    if (p3Err) { p3Err.innerHTML = errHtml; p3Err.style.display = 'block'; }
                    if (fErr) { fErr.innerHTML = errHtml; fErr.style.display = 'block'; }
                    const p1FetchStatus = document.getElementById('instSelectedStockFetchStatus');
                    const p3FetchStatus = document.getElementById('instTopSelectedStockFetchStatus');
                    const fBadge = document.getElementById('instForensicFetchStatusBadge');
                    this.renderFetchStatusBadge(p1FetchStatus, { status: 'FAILED', error_message: errMsg, time_ago: 'Just now' });
                    this.renderFetchStatusBadge(p3FetchStatus, { status: 'FAILED', error_message: errMsg, time_ago: 'Just now' });
                    this.renderFetchStatusBadge(fBadge, { status: 'FAILED', error_message: errMsg, time_ago: 'Just now' });
                }
            } catch (err) {
                console.error('[INST] Ingestion error:', err);
                const errMsg = `Network exception during ingestion: ${err.message || err}`;
                const errHtml = `<strong>⚠️ Ingestion Halted:</strong> ${errMsg}`;
                if (p1Err) { p1Err.innerHTML = errHtml; p1Err.style.display = 'block'; }
                if (p3Err) { p3Err.innerHTML = errHtml; p3Err.style.display = 'block'; }
                if (fErr) { fErr.innerHTML = errHtml; fErr.style.display = 'block'; }
            } finally {
                [btnP1, btnP3, btnForensic].forEach(b => {
                    if (b) {
                        b.disabled = false;
                        b.textContent = b.id === 'btnForensicRefreshFetch' ? '🔄 Ingest Filings' : '🔄 Ingest';
                        b.style.opacity = '1';
                    }
                });
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



            // Clean verdict title without raw emojis if present

            const verdictClean = (data.verdict || 'Institutional Activity').replace(/^[^\w\s]+\s*/, '');



            // Populate Page 1 Header

            if (tickerEl) tickerEl.textContent = data.ticker;
            const p1FetchStatus = document.getElementById('instSelectedStockFetchStatus');
            const p3FetchStatus = document.getElementById('instTopSelectedStockFetchStatus');
            this.renderFetchStatusBadge(p1FetchStatus, data.last_fetch);
            this.renderFetchStatusBadge(p3FetchStatus, data.last_fetch);

            if (nameEl) nameEl.textContent = data.company_name || '';

            if (badgeEl) {

                badgeEl.textContent = verdictClean;

                badgeEl.style.background = '#18181b';

                badgeEl.style.color = '#f4f4f5';

                badgeEl.style.border = '1px solid rgba(255,255,255,0.25)';

            }

            if (linkEl) linkEl.href = `/stock/${data.ticker}`;



            // Populate Page 3 Header (Crisp Monochrome)

            if (topTickerEl) topTickerEl.textContent = data.ticker;

            if (topNameEl) topNameEl.textContent = data.company_name || '';

            if (topBadgeEl) {

                topBadgeEl.textContent = verdictClean;

                topBadgeEl.style.background = '#18181b';

                topBadgeEl.style.color = '#f4f4f5';

                topBadgeEl.style.border = '1px solid rgba(255,255,255,0.25)';

            }

            if (topLinkEl) topLinkEl.href = `/stock/${data.ticker}`;



            // Extract price, returns, and market cap

            const curP = (data.shareholding_patterns && data.shareholding_patterns.length > 0)

                ? (data.shareholding_patterns[0].current_price != null ? data.shareholding_patterns[0].current_price : data.shareholding_patterns[0].stock_price)

                : null;

            const priceStr = curP != null ? `₹${Number(curP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';



            const ret7d = data.return_7d_pct != null ? data.return_7d_pct : null;

            const ret30d = data.return_30d_pct != null ? data.return_30d_pct : null;

            const ret1y = data.return_1y_pct != null ? data.return_1y_pct : null;



            const ret7dStr = ret7d != null ? `${ret7d >= 0 ? '+' : ''}${ret7d}%` : '—';

            const ret30dStr = ret30d != null ? `${ret30d >= 0 ? '+' : ''}${ret30d}%` : '—';

            const ret1yStr = ret1y != null ? `${ret1y >= 0 ? '+' : ''}${ret1y}%` : '—';



            const ret7dCol = ret7d != null ? (ret7d >= 0 ? '#34d399' : '#f87171') : '#a1a1aa';

            const ret30dCol = ret30d != null ? (ret30d >= 0 ? '#34d399' : '#f87171') : '#a1a1aa';

            const ret1yCol = ret1y != null ? (ret1y >= 0 ? '#34d399' : '#f87171') : '#a1a1aa';



            const mcapStr = data.market_cap_cr ? `₹${Number(Math.round(data.market_cap_cr)).toLocaleString()} Cr` : '—';



            // Populate trend metrics bar on Page 1

            const p1Price = document.getElementById('instPriceVal');

            const p1Ret7d = document.getElementById('instRet7dVal');

            const p1Ret30d = document.getElementById('instRet30dVal');

            const p1Ret1y = document.getElementById('instRet1yVal');

            const p1Mcap = document.getElementById('instMcapVal');



            if (p1Price) p1Price.textContent = priceStr;

            if (p1Ret7d) { p1Ret7d.textContent = ret7dStr; p1Ret7d.style.color = ret7dCol; }

            if (p1Ret30d) { p1Ret30d.textContent = ret30dStr; p1Ret30d.style.color = ret30dCol; }

            if (p1Ret1y) { p1Ret1y.textContent = ret1yStr; p1Ret1y.style.color = ret1yCol; }

            if (p1Mcap) p1Mcap.textContent = mcapStr;



            // Populate trend metrics bar on Page 3

            const p3Price = document.getElementById('instTopPriceVal');

            const p3Ret7d = document.getElementById('instTopRet7dVal');

            const p3Ret30d = document.getElementById('instTopRet30dVal');

            const p3Ret1y = document.getElementById('instTopRet1yVal');

            const p3Mcap = document.getElementById('instTopMcapVal');



            if (p3Price) p3Price.textContent = priceStr;

            if (p3Ret7d) { p3Ret7d.textContent = ret7dStr; p3Ret7d.style.color = ret7dCol; }

            if (p3Ret30d) { p3Ret30d.textContent = ret30dStr; p3Ret30d.style.color = ret30dCol; }

            if (p3Ret1y) { p3Ret1y.textContent = ret1yStr; p3Ret1y.style.color = ret1yCol; }

            if (p3Mcap) p3Mcap.textContent = mcapStr;



            // Formatted institutional flow lines

            const incPct = data.increase_pct != null ? data.increase_pct : (data.inst_addition_pct != null ? data.inst_addition_pct : 0);

            const incPctStr = `${incPct >= 0 ? '+' : ''}${incPct}%`;

            const incAmtStr = data.increase_amount_cr != null ? `+₹${Number(data.increase_amount_cr).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr` : `+₹${data.net_flow_cr || 0} Cr`;

            const fiiStakeStr = `${data.fii_stake_pct || 0}%${data.fii_delta_pct ? ` (+${data.fii_delta_pct}%)` : ''}`;

            const diiStakeStr = `${data.dii_stake_pct || 0}%${data.dii_delta_pct ? ` (+${data.dii_delta_pct}%)` : ''}`;



            const subtitleHtml = `Inflow (QoQ): <b style="color:#ffffff;">${incAmtStr} (${incPctStr})</b> · Inst Stake: <b style="color:#ffffff;">${data.total_institutional_stake_pct || '—'}%</b> · FII: <b style="color:#ffffff;">${fiiStakeStr}</b> · DII: <b style="color:#ffffff;">${diiStakeStr}</b>`;

            if (topSubtitleEl) topSubtitleEl.innerHTML = subtitleHtml;

            if (scoreTextEl) scoreTextEl.innerHTML = `Score: <strong style="color:#ffffff;">${data.accumulation_score || 50} / 100</strong> · Inflow: <strong style="color:#ffffff;">${incAmtStr}</strong> · Outflow: <strong style="color:#f87171;">-₹${Number(data.gross_outflow_cr || 0).toLocaleString()} Cr</strong> · Inst Stake: <strong style="color:#ffffff;">${data.total_institutional_stake_pct || '—'}%</b>`;



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



        // =========================================================================
        // 🏛️ NEXUS PERSISTENT DRAWER — INSTITUTIONAL HALF RENDERER
        // Merged into the breakout inspector drawer as the persistent institutional
        // bottom half. Mirrors renderStockInstitutionalDetails against nexusInst* IDs.
        // =========================================================================

        _nexusInstLoading: false,

        async loadNexusInstitutional(ticker) {
            if (!ticker || this._nexusInstLoading) return;
            const clean = String(ticker).trim().toUpperCase();
            const cleanTicker = (clean.endsWith('.NS') || clean.endsWith('.BO')) ? clean : clean + '.NS';
            this._nexusInstLoading = true;

            // Show loading skeleton, hide other states
            const loadEl = document.getElementById('nexusInstLoading');
            const emptyEl = document.getElementById('nexusInstEmpty');
            const headerEl = document.getElementById('nexusInstHeader');
            if (loadEl) loadEl.style.display = 'block';
            if (emptyEl) emptyEl.style.display = 'none';
            if (headerEl) headerEl.style.display = 'none';

            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.renderNexusInstitutionalPanel(data);
                } else if (emptyEl) {
                    emptyEl.style.display = 'block';
                    if (loadEl) loadEl.style.display = 'none';
                }
            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading nexus panel data:', e);
                if (emptyEl) emptyEl.style.display = 'block';
                if (loadEl) loadEl.style.display = 'none';
            } finally {
                this._nexusInstLoading = false;
            }
        },

        // Unified entry point: opens the persistent drawer (breakout + institutional
        // halves) for a ticker. Works standalone (institutional tab) or via breakout.
        async openStockIntelligencePanel(ticker) {
            if (!ticker) return;
            const clean = String(ticker).trim().toUpperCase();
            const cleanTicker = (clean.endsWith('.NS') || clean.endsWith('.BO')) ? clean : clean + '.NS';
            this._selectedTicker = cleanTicker;

            // Open the drawer shell (reparent to body + slide in)
            const drawer = document.getElementById('breakoutInspectorDrawer');
            const backdrop = document.getElementById('breakoutInspectorBackdrop');
            if (drawer && drawer.parentElement !== document.body) document.body.appendChild(drawer);
            if (backdrop && backdrop.parentElement !== document.body) document.body.appendChild(backdrop);
            if (drawer) {
                try {
                    drawer.style.width = localStorage.getItem('breakout_inspector_drawer_width') || '720px';
                } catch (e) {}
                drawer.style.right = '0px';
            }
            if (backdrop) {
                backdrop.style.display = 'block';
                setTimeout(() => { backdrop.style.opacity = '1'; }, 10);
            }

            // Load tech side if breakout module is available
            if (app.selectBreakoutCandidate) {
                app.selectBreakoutCandidate(cleanTicker, false, false);
            } else {
                // Show the drawer content, ensure institutional empty state visible
                const emptyState = document.getElementById('breakoutInspectorEmptyState');
                const content = document.getElementById('breakoutInspectorContent');
                if (emptyState) emptyState.style.display = 'none';
                if (content) content.style.display = 'block';
            }

            // Load institutional half
            await this.loadNexusInstitutional(cleanTicker);
        },

        renderNexusInstitutionalPanel(data) {
            if (!data) return;
            const emptyEl = document.getElementById('nexusInstEmpty');
            const headerEl = document.getElementById('nexusInstHeader');
            const stripEl = document.getElementById('nexusInstReturnsStrip');
            const tickerEl = document.getElementById('nexusInstTicker');
            const companyEl = document.getElementById('nexusInstCompany');
            const verdictEl = document.getElementById('nexusInstVerdict');
            const priceEl = document.getElementById('nexusInstPrice');
            const ret7dEl = document.getElementById('nexusInst7dVal');
            const ret30dEl = document.getElementById('nexusInst30dVal');
            const ret1yEl = document.getElementById('nexusInst1yVal');
            const mcapEl = document.getElementById('nexusInstMcapVal');
            // Returns strip uses distinct IDs so getElementById finds the right element
            const ret7dStripEl = document.getElementById('nexusInstReturns7dVal');
            const ret30dStripEl = document.getElementById('nexusInstReturns30dVal');
            const ret1yStripEl = document.getElementById('nexusInstReturns1yVal');
            const mcapStripEl = document.getElementById('nexusInstReturnsMcapVal');
            const scoreLineEl = document.getElementById('nexusInstScoreLine');
            const shContainer = document.getElementById('nexusInstShareholdingContainer');
            const shWrap = document.getElementById('nexusInstShareholdingWrap');
            const bdContainer = document.getElementById('nexusInstBlockDealsContainer');
            const bdWrap = document.getElementById('nexusInstBlockDealsWrap');
            const holdingsBody = document.getElementById('nexusInstHoldingsTableBody');
            const holdingsWrap = document.getElementById('nexusInstHoldingsWrap');
            const fundCountEl = document.getElementById('nexusInstFundCount');

            // Show populated state, hide empty
            if (emptyEl) emptyEl.style.display = 'none';
            if (headerEl) headerEl.style.display = 'block';
            if (stripEl) stripEl.style.display = 'grid';

            // Identity
            const cleanVerdict = (data.verdict || 'Accumulating').replace(/^[^\w\s]+\s*/, '');
            if (tickerEl) tickerEl.textContent = data.ticker;
            const p1FetchStatus = document.getElementById('instSelectedStockFetchStatus');
            const p3FetchStatus = document.getElementById('instTopSelectedStockFetchStatus');
            this.renderFetchStatusBadge(p1FetchStatus, data.last_fetch);
            this.renderFetchStatusBadge(p3FetchStatus, data.last_fetch);
            if (companyEl) companyEl.textContent = data.company_name || '';
            if (verdictEl) { verdictEl.textContent = cleanVerdict; verdictEl.style.background = '#18181b'; verdictEl.style.color = '#f4f4f5'; }

            // Price
            const curP = (data.shareholding_patterns && data.shareholding_patterns.length > 0)
                ? (data.shareholding_patterns[0].current_price != null ? data.shareholding_patterns[0].current_price : data.shareholding_patterns[0].stock_price) : null;
            const priceStr = curP != null ? `₹${Number(curP).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
            if (priceEl) priceEl.textContent = priceStr;

            // Returns
            const ret7d = data.return_7d_pct, ret30d = data.return_30d_pct, ret1y = data.return_1y_pct;
            const fmt = (v) => v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '—';
            const col = (v) => v != null ? (v >= 0 ? '#34d399' : '#f87171') : '#a1a1aa';
            if (ret7dEl) { ret7dEl.textContent = fmt(ret7d); ret7dEl.style.color = col(ret7d); }
            if (ret7dStripEl) { ret7dStripEl.textContent = fmt(ret7d); ret7dStripEl.style.color = col(ret7d); }
            if (ret30dEl) { ret30dEl.textContent = fmt(ret30d); ret30dEl.style.color = col(ret30d); }
            if (ret30dStripEl) { ret30dStripEl.textContent = fmt(ret30d); ret30dStripEl.style.color = col(ret30d); }
            if (ret1yEl) { ret1yEl.textContent = fmt(ret1y); ret1yEl.style.color = col(ret1y); }
            if (ret1yStripEl) { ret1yStripEl.textContent = fmt(ret1y); ret1yStripEl.style.color = col(ret1y); }
            if (mcapEl) mcapEl.textContent = data.market_cap_cr ? `₹${Number(Math.round(data.market_cap_cr)).toLocaleString()} Cr` : '—';
            if (mcapStripEl) mcapStripEl.textContent = data.market_cap_cr ? `₹${Number(Math.round(data.market_cap_cr)).toLocaleString()} Cr` : '—';

            // Score line
            const incAmtStr = data.increase_amount_cr != null
                ? `+₹${Number(data.increase_amount_cr).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} Cr`
                : `+₹${data.net_flow_cr || 0} Cr`;
            if (scoreLineEl) scoreLineEl.innerHTML = `Score: <strong style="color:#fff;">${data.accumulation_score || 50}/100</strong> · Inflow: <strong style="color:#34d399;">${incAmtStr}</strong> · Inst Stake: <strong style="color:#fff;">${data.total_institutional_stake_pct || '—'}%</strong>`;

            // ── Shareholding Pattern Table ──
            const pats = data.shareholding_patterns || [];
            if (shContainer) {
                if (!pats.length) {
                    shContainer.innerHTML = '<div style="color:#52525b;font-size:0.68rem;text-align:center;padding:0.5rem;">No filing data.</div>';
                    if (shWrap) shWrap.style.display = 'block';
                } else {
                    shContainer.innerHTML = `
                        <table style="width:100%;font-size:0.68rem;text-align:left;border-collapse:collapse;">
                            <thead>
                                <tr style="color:#71717a;border-bottom:1px solid rgba(255,255,255,0.1);font-family:var(--font-mono);">
                                    <th style="padding:0.25rem 0.35rem;">QTR</th>
                                    <th style="padding:0.25rem 0.35rem;text-align:right;">PRICE</th>
                                    <th style="padding:0.25rem 0.35rem;text-align:right;">PROM</th>
                                    <th style="padding:0.25rem 0.35rem;text-align:right;">FII</th>
                                    <th style="padding:0.25rem 0.35rem;text-align:right;">DII/MF</th>
                                    <th style="padding:0.25rem 0.35rem;text-align:right;">RETAIL</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${pats.slice(0, 6).map((p, idx) => {
                                    const fiiDelta = p.fii_delta_pct != null ? p.fii_delta_pct : (idx < pats.length - 1 ? (p.fii_pct - pats[idx + 1].fii_pct) : 0);
                                    const diiDelta = p.dii_delta_pct != null ? p.dii_delta_pct : (idx < pats.length - 1 ? (p.dii_mf_pct - pats[idx + 1].dii_mf_pct) : 0);
                                    const fiiD = fiiDelta !== 0 ? `<span style="color:${fiiDelta > 0 ? '#34d399' : '#f87171'};font-size:0.58rem;">(${fiiDelta > 0 ? '+' : ''}${fiiDelta.toFixed(2)}%)</span>` : '';
                                    const diiD = diiDelta !== 0 ? `<span style="color:${diiDelta > 0 ? '#34d399' : '#f87171'};font-size:0.58rem;">(${diiDelta > 0 ? '+' : ''}${diiDelta.toFixed(2)}%)</span>` : '';
                                    const price = p.current_price != null ? p.current_price : p.stock_price;
                                    const priceStr2 = price != null ? `₹${Number(price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
                                    return `
                                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                            <td style="padding:0.25rem 0.35rem;font-weight:700;color:#fff;font-family:var(--font-mono);">${p.quarter}</td>
                                            <td style="padding:0.25rem 0.35rem;text-align:right;font-family:var(--font-mono);color:#fff;">${priceStr2}</td>
                                            <td style="padding:0.25rem 0.35rem;text-align:right;font-family:var(--font-mono);color:#a1a1aa;">${p.promoter_pct}%</td>
                                            <td style="padding:0.25rem 0.35rem;text-align:right;font-family:var(--font-mono);color:#fff;font-weight:700;">${p.fii_pct}% ${fiiD}</td>
                                            <td style="padding:0.25rem 0.35rem;text-align:right;font-family:var(--font-mono);color:#fff;font-weight:700;">${p.dii_mf_pct}% ${diiD}</td>
                                            <td style="padding:0.25rem 0.35rem;text-align:right;font-family:var(--font-mono);color:#71717a;">${p.public_retail_pct}%</td>
                                        </tr>`;
                                }).join('')}
                            </tbody>
                        </table>`;
                    if (shWrap) shWrap.style.display = 'block';
                }
            }

            // ── Block Deals ──
            const deals = data.block_deals || [];
            if (bdContainer) {
                if (!deals.length) {
                    bdContainer.innerHTML = '<div style="color:#52525b;font-size:0.68rem;">No block deals on record.</div>';
                    if (bdWrap) bdWrap.style.display = 'block';
                } else {
                    bdContainer.innerHTML = deals.map(d => {
                        const isBuy = d.deal_type === 'BUY';
                        const bg = isBuy ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
                        const col = isBuy ? '#34d399' : '#f87171';
                        return `
                            <div style="background:${bg};border:1px solid ${isBuy ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:4px;padding:0.3rem 0.45rem;margin-bottom:0.25rem;font-size:0.66rem;font-family:var(--font-mono);">
                                <span style="color:${col};font-weight:700;">[${d.deal_type}]</span>
                                <strong style="color:#fff;">${d.client_name}</strong>
                                <span style="color:#71717a;"> · ${d.quantity.toLocaleString()} @ ₹${d.price} (₹${d.value_cr} Cr) · ${d.deal_date}</span>
                            </div>`;
                    }).join('');
                    if (bdWrap) bdWrap.style.display = 'block';
                }
            }

            // ── Fund Holdings ──
            const holdings = data.holdings || [];
            if (fundCountEl) fundCountEl.textContent = `${holdings.length} Funds`;
            if (holdingsBody) {
                if (!holdings.length) {
                    holdingsBody.innerHTML = '<tr><td colspan="6" style="padding:1rem;text-align:center;color:#52525b;font-size:0.68rem;">No fund positions recorded.</td></tr>';
                    if (holdingsWrap) holdingsWrap.style.display = 'block';
                } else {
                    holdingsBody.innerHTML = holdings.slice(0, 15).map(h => {
                        const act = h.action;
                        const isBuy = act === 'NEW BUY', isAcc = act === 'ACCUMULATED', isTrim = act === 'TRIMMED';
                        const actCol = isBuy ? '#38bdf8' : isAcc ? '#34d399' : isTrim ? '#fbbf24' : '#f87171';
                        const chgPct = h.change_pct != null ? h.change_pct : 0;
                        const incCr = h.increase_amount_cr != null ? h.increase_amount_cr : 0;
                        const incCol = incCr >= 0 ? '#34d399' : '#f87171';
                        const totCr = h.total_amount_cr != null ? h.total_amount_cr : (h.holding_value_cr || 0);
                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                                <td style="padding:0.28rem 0.4rem;font-family:var(--font-mono);font-weight:700;color:#fff;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${h.fund_name}</td>
                                <td style="padding:0.28rem 0.35rem;"><span style="font-size:0.58rem;background:#18181b;color:${actCol};border:1px solid rgba(255,255,255,0.1);padding:0.05rem 0.25rem;border-radius:3px;">${h.action}</span></td>
                                <td style="padding:0.28rem 0.35rem;text-align:right;font-family:var(--font-mono);color:#fff;font-weight:700;">${h.stake_pct}%</td>
                                <td style="padding:0.28rem 0.35rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:${chgPct >= 0 ? '#34d399' : '#f87171'};">${chgPct > 0 ? '+' : ''}${chgPct}%</td>
                                <td style="padding:0.28rem 0.35rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:${incCol};">${incCr >= 0 ? '+' : ''}₹${Number(incCr).toFixed(1)} Cr</td>
                                <td style="padding:0.28rem 0.35rem;text-align:right;font-family:var(--font-mono);color:#a1a1aa;font-size:0.62rem;">₹${Number(totCr).toFixed(1)} Cr</td>
                            </tr>`;
                    }).join('');
                    if (holdingsWrap) holdingsWrap.style.display = 'block';
                }
            }

            // ── Institutional Flow Metrics (Crore summary row) ──
            const flowMetricsEl = document.getElementById('nexusInstFlowMetrics');
            if (flowMetricsEl) {
                const netFlow = data.net_flow_cr != null ? Number(data.net_flow_cr) : (data.increase_amount_cr != null ? Number(data.increase_amount_cr) : null);
                const grossIn = data.gross_inflow_cr != null ? Number(data.gross_inflow_cr) : null;
                const grossOut = data.gross_outflow_cr != null ? Number(data.gross_outflow_cr) : null;
                const totalAmt = data.total_amount_cr != null ? Number(data.total_amount_cr) : null;
                const fundsAcc = data.funds_accumulating_count != null ? Number(data.funds_accumulating_count) : null;
                const fundsSell = data.funds_selling_count != null ? Number(data.funds_selling_count) : null;

                const fmtCr = (v, showSign) => {
                    if (v == null) return '—';
                    const prefix = showSign && v > 0 ? '+' : '';
                    return `${prefix}₹${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 1 })} Cr`;
                };
                const crCol = (v) => v != null ? (v > 0 ? '#34d399' : v < 0 ? '#f87171' : '#a1a1aa') : '#52525b';

                const netFlowEl = document.getElementById('nexusInstNetFlow');
                const grossInEl = document.getElementById('nexusInstGrossIn');
                const grossOutEl = document.getElementById('nexusInstGrossOut');
                const totalAmtEl = document.getElementById('nexusInstTotalAmt');
                const fundsAccEl = document.getElementById('nexusInstFundsAcc');

                if (netFlowEl) {
                    netFlowEl.innerHTML = `<div style="color:#71717a;font-size:0.56rem;">NET FLOW</div><div style="font-weight:700;color:${crCol(netFlow)};font-size:0.78rem;">${fmtCr(netFlow, true)}</div>`;
                }
                if (grossInEl) {
                    grossInEl.innerHTML = `<div style="color:#71717a;font-size:0.56rem;">GROSS INFLOW</div><div style="font-weight:700;color:#34d399;font-size:0.78rem;">${fmtCr(grossIn, false)}</div>`;
                }
                if (grossOutEl) {
                    grossOutEl.innerHTML = `<div style="color:#71717a;font-size:0.56rem;">GROSS OUTFLOW</div><div style="font-weight:700;color:#f87171;font-size:0.78rem;">${fmtCr(grossOut, false)}</div>`;
                }
                if (totalAmtEl) {
                    totalAmtEl.innerHTML = `<div style="color:#71717a;font-size:0.56rem;">TOTAL HOLDINGS</div><div style="font-weight:700;color:#fff;font-size:0.78rem;">${fmtCr(totalAmt, false)}</div>`;
                }
                if (fundsAccEl) {
                    const fundsAccStr = fundsAcc != null ? `${fundsAcc}` : '—';
                    const fundsSellStr = fundsSell != null ? `${fundsSell}` : '—';
                    fundsAccEl.innerHTML = `<div style="color:#71717a;font-size:0.56rem;">FUNDS IN / OUT</div><div style="font-size:0.78rem;"><span style="font-weight:700;color:#34d399;">${fundsAccStr}</span><span style="color:#52525b;"> / </span><span style="font-weight:700;color:#f87171;">${fundsSellStr}</span></div>`;
                }
                flowMetricsEl.style.display = 'grid';
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

                        titleEl.innerText = data.fund_name || fundName;

                    }

                    if (subEl) {

                        const computedAum = data.total_aum_tracked_cr != null ? data.total_aum_tracked_cr : holdings.reduce((sum, h) => sum + Number(h.holding_value_cr || h.total_amount_cr || 0), 0);
                        subEl.innerText = `${data.fund_type || 'Fund'} Portfolio · ${holdings.length} Positions Tracked · Total Tracked Value: ₹${Number(computedAum).toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr`;

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



                                const ret30Str = h.return_30d_pct != null ? `<span style="color:${h.return_30d_pct >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${h.return_30d_pct >= 0 ? '+' : ''}${h.return_30d_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;

                                const ret1yStr = h.return_1y_pct != null ? `<span style="color:${h.return_1y_pct >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${h.return_1y_pct >= 0 ? '+' : ''}${h.return_1y_pct}%</span>` : `<span style="color:#71717a;">N/A</span>`;



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

                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);">${ret30Str}</td>

                                        <td style="padding:0.5rem 0.6rem;font-family:var(--font-mono);">${ret1yStr}</td>

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

        },



        // =========================================================================

        // 🎯 SMART MONEY ACCUMULATION RADAR CONTROLLER

        // =========================================================================

        _smartMoneyWindow: '90d',
        _smartMoneyEntityFocus: 'smart_money',
        _smartMoneyMinCr: 5,
        _smartMoneySortBy: 'score',
        _smartMoneySortColumn: 'score',
        _smartMoneySortAsc: false,
        _smartMoneyNewEntrantsOnly: false,
        _smartMoneyEmergingOnly: false,
        _smartMoneyGoodEpsOnly: false,
        _smartMoneyStrategy: 'ALL_STRATEGIES',
        _smartMoneyStatus: 'active',
        _smartMoneyForensicDossier: null,
        _smartMoneyForensicTab: 'buyers',
        _smartMoneyStocks: [],
        _smartMoneySelectedStock: null,
        _smartMoneyRawData: null,



        selectSmartMoneyStrategy(strategy) {

            this._smartMoneyStrategy = strategy;

            ['ALL_STRATEGIES', 'WHALE_CONVICTION', 'BLOCK_DEAL_MOMENTUM', 'DUAL_ACCELERATION', 'DOMESTIC_ABSORPTION'].forEach(s => {

                const btn = document.getElementById('btnSmStrat-' + s);

                if (btn) {

                    btn.style.background = s === strategy ? '#ffffff' : 'transparent';

                    btn.style.color = s === strategy ? '#09090b' : '#a1a1aa';

                    btn.style.borderColor = s === strategy ? '#ffffff' : 'transparent';

                }

            });

            this._smartMoneySortColumn = 'score';

            this._smartMoneySortAsc = false;

            this.loadSmartMoneyRadar(true);

        },



        switchForensicsTab(tab) {

            this._smartMoneyForensicTab = tab;

            ['buyers', 'quarterly', 'blocks', 'signals'].forEach(t => {

                const btn = document.getElementById('btnForensicTab-' + t);

                const pane = document.getElementById('instForensicPane-' + t);

                if (btn) {

                    btn.style.background = t === tab ? '#ffffff' : 'transparent';

                    btn.style.color = t === tab ? '#09090b' : '#a1a1aa';

                    btn.style.borderColor = t === tab ? '#ffffff' : 'transparent';

                }

                if (pane) pane.style.display = t === tab ? 'block' : 'none';

            });

            if (this._smartMoneySelectedStock) {

                this.renderForensicsTab(tab);

            }

        },



        renderForensicsTab(tab) {
            const dossier = this._smartMoneyForensicDossier;
            if (!dossier) return;
            const container = document.getElementById('instForensicPane-' + tab);
            const fBadge = document.getElementById('instForensicFetchStatusBadge');
            if (fBadge) this.renderFetchStatusBadge(fBadge, dossier.last_fetch);
            if (!container) return;
            if (tab === 'quarters') tab = 'quarterly';

            if (tab === 'buyers') {
                const buyers = dossier.buyers || [];
                const badge = document.getElementById('instSmBuyerCountBadge');
                if (badge) badge.textContent = `${buyers.length} Buyers Logged`;
                const tbody = document.getElementById('instSmBuyersTableBody');
                if (!tbody) return;

                if (!buyers.length) {
                    tbody.innerHTML = '<tr><td colspan="6" style="padding:2rem;text-align:center;color:#71717a;">No institutional buyers on record.</td></tr>';
                    return;
                }

                tbody.innerHTML = buyers.map(b => {
                    const buyerName = b.investor_name || b.buyer_name || b.fund_name || b.name || b.client_name || 'Institution';
                    const cls = b.entity_class || b.entity_type || b.fund_type || 'Institution';
                    const stakePct = b.stake_pct != null ? `${Number(b.stake_pct).toFixed(2)}%` : '—';
                    const capCr = b.capital_deployed_cr != null ? `₹${Number(b.capital_deployed_cr).toLocaleString(undefined, {maximumFractionDigits:1})} Cr` : (b.capital_cr != null ? `₹${Number(b.capital_cr).toLocaleString(undefined, {maximumFractionDigits:1})} Cr` : (b.holding_value_cr != null ? `₹${Number(b.holding_value_cr).toLocaleString(undefined, {maximumFractionDigits:1})} Cr` : '—'));
                    const qty = b.shares_held != null ? Number(b.shares_held).toLocaleString('en-IN') : (b.quantity != null ? Number(b.quantity).toLocaleString('en-IN') : (b.shares != null ? Number(b.shares).toLocaleString('en-IN') : (b.change_shares != null ? Number(b.change_shares).toLocaleString('en-IN') : '—')));
                    const price = b.price != null ? `₹${Number(b.price).toFixed(2)}` : (b.avg_price != null ? `₹${Number(b.avg_price).toFixed(2)}` : (b.buy_price != null ? `₹${Number(b.buy_price).toFixed(2)}` : '—'));
                    const filingDate = b.quarter || b.date || b.deal_date || b.reported_date || '—';

                    return `<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                        <td style="padding:0.4rem 0.6rem;font-weight:700;color:#f4f4f5;">${buyerName}</td>
                        <td style="padding:0.4rem 0.5rem;color:#a1a1aa;">${cls}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#10b981;font-weight:700;">${capCr}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${stakePct}${qty !== '—' ? ` <span style="color:#71717a;font-size:0.65rem;">(${qty} sh)</span>` : ''}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${price}</td>
                        <td style="padding:0.4rem 0.5rem;color:#71717a;font-size:0.65rem;font-family:var(--font-mono);">${filingDate}</td>
                    </tr>`;
                }).join('');
                return;
            }

            if (tab === 'quarterly') {
                const fin = dossier.quarterly_income || dossier.quarterly_financials || [];
                const badge = document.getElementById('instSmQuarterlyCountBadge');
                if (badge) badge.textContent = `${fin.length} Quarters Logged`;
                const tbody = document.getElementById('instSmQuarterlyTableBody');
                if (!tbody) return;

                if (!fin.length) {
                    tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#71717a;">No quarterly financial filings on record.</td></tr>';
                    return;
                }

                tbody.innerHTML = fin.map(f => {
                    const revCr = f.revenue_cr != null ? `₹${Number(f.revenue_cr).toLocaleString(undefined, {maximumFractionDigits:0})} Cr` : '—';
                    const patCr = f.net_profit_cr != null ? `₹${Number(f.net_profit_cr).toLocaleString(undefined, {maximumFractionDigits:0})} Cr` : '—';
                    const opm = f.operating_margin_pct != null ? `${Number(f.operating_margin_pct).toFixed(1)}%` : '—';
                    const epsVal = f.eps != null ? `₹${Number(f.eps).toFixed(2)}` : '—';
                    const yoyRev = f.yoy_revenue_growth_pct;
                    const yoyRevStr = yoyRev != null ? `${yoyRev >= 0 ? '+' : ''}${Number(yoyRev).toFixed(1)}%` : '—';
                    const yoyRevCol = yoyRev != null ? (yoyRev >= 0 ? '#34d399' : '#f87171') : '#a1a1aa';
                    const yoyPat = f.yoy_pat_growth_pct;
                    const yoyPatStr = yoyPat != null ? `${yoyPat >= 0 ? '+' : ''}${Number(yoyPat).toFixed(1)}%` : '—';
                    const yoyPatCol = yoyPat != null ? (yoyPat >= 0 ? '#34d399' : '#f87171') : '#a1a1aa';

                    return `<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                        <td style="padding:0.4rem 0.5rem;font-weight:700;color:#f4f4f5;">${f.quarter || '—'}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${revCr}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#ffffff;">${patCr}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${opm}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${epsVal}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:${yoyRevCol};">${yoyRevStr}</td>
                        <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:${yoyPatCol};">${yoyPatStr}</td>
                    </tr>`;
                }).join('');
                return;
            }

            if (tab === 'blocks') {
                const deals = dossier.block_deals || [];
                const badge = document.getElementById('instSmBlockCountBadge');
                if (badge) badge.textContent = `${deals.length} Deals`;
                const container = document.getElementById('instSmBlockDealsContainer');
                if (!container) return;

                if (!deals.length) {
                    container.innerHTML = '<div style="color:#71717a;font-size:0.72rem;text-align:center;padding:2rem;">No major exchange block deals on record.</div>';
                    return;
                }

                container.innerHTML = deals.map(d => {
                    const isBuy = (d.deal_type || 'BUY').toUpperCase() === 'BUY';
                    const col = isBuy ? '#34d399' : '#f87171';
                    const bg = isBuy ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)';
                    const border = isBuy ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)';
                    const valCr = d.value_cr != null ? `₹${Number(d.value_cr).toLocaleString(undefined, {maximumFractionDigits:2})} Cr` : '—';
                    const pctEq = d.pct_equity != null ? ` · ${Number(d.pct_equity).toFixed(2)}%` : '';

                    return `<div style="background:${bg};border:1px solid ${border};border-radius:4px;padding:0.45rem 0.65rem;margin-bottom:0.4rem;display:flex;justify-content:space-between;align-items:center;font-size:0.72rem;">
                        <div>
                            <span style="font-weight:700;color:${col};font-family:var(--font-mono);margin-right:0.35rem;">[${d.deal_type || 'DEAL'}]</span>
                            <strong style="color:#ffffff;">${d.client_name || d.name || '—'}</strong>
                            <span style="color:#71717a;margin-left:0.35rem;font-size:0.65rem;font-family:var(--font-mono);">${d.deal_date || d.date || ''}</span>
                        </div>
                        <div style="font-family:var(--font-mono);color:#a1a1aa;text-align:right;">
                            ${d.quantity ? Number(d.quantity).toLocaleString('en-IN') + ' sh @ ' : ''}₹${d.price != null ? Number(d.price).toFixed(2) : '—'}
                            <div style="color:#10b981;font-weight:700;">${valCr}${pctEq}</div>
                        </div>
                    </div>`;
                }).join('');
                return;
            }

            if (tab === 'signals') {
                const signal = dossier.signal_timeline || [];
                const container = document.getElementById('instSmSignalTimelineContainer');
                const badge = document.getElementById('instSmTimelineCountBadge');
                if (badge) badge.textContent = `${signal.length} Signals`;
                if (!container) return;

                const timelineSrc = Array.isArray(signal) ? signal : [];
                if (!timelineSrc.length) {
                    container.innerHTML = '<div style="color:#71717a;font-size:0.72rem;text-align:center;padding:2rem;">No discovery signal history on record.</div>';
                    return;
                }

                container.innerHTML = `
                    <table style="width:100%;border-collapse:collapse;font-size:0.72rem;text-align:left;">
                        <thead style="position:sticky;top:0;z-index:2;background:#121215;color:#a1a1aa;border-bottom:1px solid rgba(255,255,255,0.15);font-family:var(--font-mono);font-size:0.65rem;">
                            <tr>
                                <th style="padding:0.4rem 0.5rem;">STRATEGY</th>
                                <th style="padding:0.4rem 0.5rem;">SIGNAL DATE</th>
                                <th style="padding:0.4rem 0.5rem;">ENTRY (₹)</th>
                                <th style="padding:0.4rem 0.5rem;">CURRENT (₹)</th>
                                <th style="padding:0.4rem 0.5rem;">OUTCOME RET</th>
                                <th style="padding:0.4rem 0.5rem;">TARGET (₹)</th>
                                <th style="padding:0.4rem 0.5rem;">STOP LOSS</th>
                                <th style="padding:0.4rem 0.5rem;">DAYS</th>
                                <th style="padding:0.4rem 0.5rem;">STATUS</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${timelineSrc.map(sg => {
                                const sigRet = sg.outcome_return_pct != null ? sg.outcome_return_pct : sg.return_since_signal_pct;
                                const retStr = sigRet != null ? `${sigRet >= 0 ? '+' : ''}${Number(sigRet).toFixed(2)}%` : '—';
                                const retCol = sigRet != null && sigRet >= 0 ? '#34d399' : '#f87171';
                                const status = sg.lifecycle_status || 'ACTIVE';
                                const stBadge = status === 'TARGET_HIT' ? ['rgba(16,185,129,0.18)','#34d399','rgba(16,185,129,0.35)'] : (status === 'DISTRIBUTION_EXIT' ? ['rgba(239,68,68,0.18)','#f87171','rgba(239,68,68,0.35)'] : (status === 'COOLING_OFF' ? ['rgba(245,158,11,0.18)','#fbbf24','rgba(245,158,11,0.35)'] : ['rgba(56,189,248,0.18)','#38bdf8','rgba(56,189,248,0.35)']));
                                return `<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                                    <td style="padding:0.4rem 0.5rem;font-weight:700;color:#f4f4f5;">${sg.strategy || '—'}</td>
                                    <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#a1a1aa;">${sg.signal_date || '—'}</td>
                                    <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">₹${sg.signal_price != null ? Number(sg.signal_price).toFixed(2) : '—'}</td>
                                    <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${sg.current_price != null ? `₹${Number(sg.current_price).toFixed(2)}` : '—'}</td>
                                    <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:${retCol};">${retStr}</td>
                                    <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">₹${sg.target_price != null ? Number(sg.target_price).toFixed(2) : '—'}</td>
                                    <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">₹${sg.stop_loss != null ? Number(sg.stop_loss).toFixed(2) : '—'}</td>
                                    <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${sg.days_elapsed != null ? `${sg.days_elapsed}d` : '—'}</td>
                                    <td style="padding:0.4rem 0.5rem;"><span style="font-size:0.62rem;font-weight:700;padding:0.12rem 0.35rem;border-radius:3px;background:${stBadge[0]};color:${stBadge[1]};border:1px solid ${stBadge[2]};">${status}</span></td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>`;
                return;
            }
        },

        sortSmartMoneyTable(col) {
            if (!this._smartMoneyStocks || !this._smartMoneyStocks.length) return;

            if (this._smartMoneySortColumn === col) {
                this._smartMoneySortAsc = !this._smartMoneySortAsc;
            } else {
                this._smartMoneySortColumn = col;
                this._smartMoneySortAsc = (col === 'ticker' || col === 'strategy' || col === 'status');
            }

            const asc = this._smartMoneySortAsc;
            const factor = asc ? 1 : -1;

            this._smartMoneyStocks.sort((a, b) => {
                let vA, vB;
                switch (col) {
                    case 'ticker':
                        return factor * (a.ticker || '').localeCompare(b.ticker || '');
                    case 'strategy':
                        return factor * (a.strategy || a.strategy_archetype || '').localeCompare(b.strategy || b.strategy_archetype || '');
                    case 'signal_date':
                        return factor * (a.signal_date || '').localeCompare(b.signal_date || '');
                    case 'price':
                        vA = a.current_price != null ? Number(a.current_price) : 0;
                        vB = b.current_price != null ? Number(b.current_price) : 0;
                        return factor * (vA - vB);
                    case 'return':
                    case 'signal':
                        vA = a.outcome_return_pct != null ? Number(a.outcome_return_pct) : (a.return_since_signal_pct != null ? Number(a.return_since_signal_pct) : -9999);
                        vB = b.outcome_return_pct != null ? Number(b.outcome_return_pct) : (b.return_since_signal_pct != null ? Number(b.return_since_signal_pct) : -9999);
                        return factor * (vA - vB);
                    case 'eps':
                        vA = a.eps_growth_yoy != null ? Number(a.eps_growth_yoy) : -9999;
                        vB = b.eps_growth_yoy != null ? Number(b.eps_growth_yoy) : -9999;
                        return factor * (vA - vB);
                    case 'capital':
                        vA = Number(a.smart_money_inflow_cr || a.initial_smart_money_cr || a.capital_cr || 0);
                        vB = Number(b.smart_money_inflow_cr || b.initial_smart_money_cr || b.capital_cr || 0);
                        return factor * (vA - vB);
                    case 'dominance':
                        vA = Number(a.smart_money_dominance_pct != null ? a.smart_money_dominance_pct : (a.dominance_pct || 0));
                        vB = Number(b.smart_money_dominance_pct != null ? b.smart_money_dominance_pct : (b.dominance_pct || 0));
                        return factor * (vA - vB);
                    case 'whales':
                        vA = a.whale_count != null ? Number(a.whale_count) : (a.whale_buyers_summary || a.whale_buyers || []).length;
                        vB = b.whale_count != null ? Number(b.whale_count) : (b.whale_buyers_summary || b.whale_buyers || []).length;
                        return factor * (vA - vB);
                    case 'status':
                        return factor * (a.lifecycle_status || '').localeCompare(b.lifecycle_status || '');
                    case 'classification':
                        return factor * (a.accumulation_signal_badge || a.badge || '').localeCompare(b.accumulation_signal_badge || b.badge || '');
                    case 'score':
                    default:
                        vA = Number(a.conviction_score != null ? a.conviction_score : (a.initial_score != null ? a.initial_score : (a.smart_money_conviction_score || 0)));
                        vB = Number(b.conviction_score != null ? b.conviction_score : (b.initial_score != null ? b.initial_score : (b.smart_money_conviction_score || 0)));
                        return factor * (vA - vB);
                }
            });

            // Update UI sort arrow indicators
            ['ticker', 'strategy', 'signal_date', 'price', 'return', 'capital', 'whales', 'score', 'status', 'signal', 'eps', 'dominance', 'classification'].forEach(c => {
                const icon = document.getElementById('smSortIcon-' + c);
                if (icon) {
                    if (c === col) {
                        icon.textContent = asc ? '▲' : '▼';
                        icon.style.color = '#38bdf8';
                    } else {
                        icon.textContent = '↕';
                        icon.style.color = '#71717a';
                    }
                }
            });

            const searchInput = document.getElementById('instSmSearchInput');
            if (searchInput && searchInput.value.trim()) {
                this.filterSmartMoneyLocal(searchInput.value.trim());
            } else {
                this.renderSmartMoneyTable(this._smartMoneyStocks);
            }
        },

        setSmartMoneyWindow(win) {
            this._smartMoneyWindow = win || '90d';
            ['30d', '90d', '180d', '365d'].forEach(w => {
                const btn = document.getElementById('btnSmWin-' + w);
                if (btn) {
                    if (w === this._smartMoneyWindow) {
                        btn.style.background = '#ffffff';
                        btn.style.color = '#09090b';
                        btn.style.borderColor = '#ffffff';
                        btn.style.fontWeight = '700';
                    } else {
                        btn.style.background = 'transparent';
                        btn.style.color = '#a1a1aa';
                        btn.style.borderColor = 'transparent';
                        btn.style.fontWeight = '600';
                    }
                }
            });
            this.loadSmartMoneyRadar();
        },

        changeSmartMoneyFilter() {
            const statusEl = document.getElementById('instSmStatus');
            const sortByEl = document.getElementById('instSmSortBy');
            const entityEl = document.getElementById('instSmEntityFocus');
            const minCrEl = document.getElementById('instSmMinCrInput');
            if (statusEl) this._smartMoneyStatus = statusEl.value;
            if (sortByEl) this._smartMoneySortBy = sortByEl.value;
            if (entityEl) this._smartMoneyEntityFocus = entityEl.value;
            if (minCrEl) this._smartMoneyMinCr = parseFloat(minCrEl.value) || 0;
            this.loadSmartMoneyRadar(true);
        },

        toggleSmartMoneyNewEntrants() {
            this._smartMoneyNewEntrantsOnly = !this._smartMoneyNewEntrantsOnly;
            const btn = document.getElementById('instSmNewEntrantsBtn');
            if (btn) {
                if (this._smartMoneyNewEntrantsOnly) {
                    btn.style.background = 'rgba(56,189,248,0.25)';
                    btn.style.color = '#38bdf8';
                    btn.style.borderColor = '#38bdf8';
                    btn.style.fontWeight = '700';
                } else {
                    btn.style.background = '#18181b';
                    btn.style.color = '#a1a1aa';
                    btn.style.borderColor = 'rgba(255,255,255,0.15)';
                    btn.style.fontWeight = '500';
                }
            }
            this.loadSmartMoneyRadar(true);
        },

        toggleSmartMoneyEmerging() {
            this._smartMoneyEmergingOnly = !this._smartMoneyEmergingOnly;
            const btn = document.getElementById('instSmEmergingBtn');
            if (btn) {
                if (this._smartMoneyEmergingOnly) {
                    btn.style.background = 'rgba(52,211,153,0.25)';
                    btn.style.color = '#34d399';
                    btn.style.borderColor = '#34d399';
                    btn.style.fontWeight = '700';
                } else {
                    btn.style.background = '#18181b';
                    btn.style.color = '#a1a1aa';
                    btn.style.borderColor = 'rgba(255,255,255,0.15)';
                    btn.style.fontWeight = '500';
                }
            }
            this.loadSmartMoneyRadar(true);
        },

        toggleSmartMoneyGoodEps() {
            this._smartMoneyGoodEpsOnly = !this._smartMoneyGoodEpsOnly;
            const btn = document.getElementById('instSmGoodEpsBtn');
            if (btn) {
                if (this._smartMoneyGoodEpsOnly) {
                    btn.style.background = 'rgba(244,63,94,0.25)';
                    btn.style.color = '#fb7185';
                    btn.style.borderColor = '#fb7185';
                    btn.style.fontWeight = '700';
                } else {
                    btn.style.background = '#18181b';
                    btn.style.color = '#a1a1aa';
                    btn.style.borderColor = 'rgba(255,255,255,0.15)';
                    btn.style.fontWeight = '500';
                }
            }
            this.loadSmartMoneyRadar(true);
        },

        filterSmartMoneyLocal(query) {
            if (!this._smartMoneyStocks || !this._smartMoneyStocks.length) return;
            const q = (query || '').trim().toLowerCase();
            if (!q) {
                this.renderSmartMoneyTable(this._smartMoneyStocks);
                return;
            }

            const filtered = this._smartMoneyStocks.filter(s => {
                const ticker = (s.ticker || '').toLowerCase();
                const name = (s.company_name || '').toLowerCase();
                const sector = (s.sector || '').toLowerCase();
                const strat = (s.strategy || s.strategy_archetype || '').toLowerCase();
                const whales = (s.whale_buyers_summary || []).join(' ').toLowerCase();
                return ticker.includes(q) || name.includes(q) || sector.includes(q) || strat.includes(q) || whales.includes(q);
            });

            this.renderSmartMoneyTable(filtered);
        },

        async loadSmartMoneyRadar(force = false) {
            const tbody = document.getElementById('instSmTableBody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="10" style="padding:2.5rem;text-align:center;color:#71717a;"><span class="spinner-border spinner-border-sm" style="margin-right:0.4rem;"></span>Scanning institutional flow databases for smart money accumulation...</td></tr>';
            }

            try {
                let url = API_BASE + `/api/v1/institutional/signals?strategy=${encodeURIComponent(this._smartMoneyStrategy)}&status=${encodeURIComponent(this._smartMoneyStatus)}&sort_by=${encodeURIComponent(this._smartMoneySortBy)}&limit=60`;
                if (this._smartMoneyNewEntrantsOnly) {
                    url += '&new_entrants_only=true';
                }
                if (this._smartMoneyEmergingOnly) {
                    url += '&emerging_only=true';
                }
                if (this._smartMoneyGoodEpsOnly) {
                    url += '&min_eps_growth=20.0';
                }

                const res = await fetch(url);
                if (!res.ok) {
                    throw new Error(`API returned HTTP ${res.status}`);
                }
                const data = await res.json();
                this._smartMoneyRawData = data;
                this._smartMoneyStocks = data.signals || [];
                this._smartMoneySortColumn = 'score';
                this._smartMoneySortAsc = false;

                ['ticker', 'strategy', 'signal_date', 'price', 'return', 'capital', 'whales', 'score', 'status', 'signal', 'eps', 'dominance', 'classification'].forEach(c => {
                    const icon = document.getElementById('smSortIcon-' + c);
                    if (icon) {
                        if (c === 'score') {
                            icon.textContent = '▼';
                            icon.style.color = '#38bdf8';
                        } else {
                            icon.textContent = '↕';
                            icon.style.color = '#71717a';
                        }
                    }
                });

                // Update Macro KPI Cards
                const summary = data.macro_summary || {};
                const kpiStocks = document.getElementById('kpiSmTotalStocks');
                const kpiStocksSub = document.getElementById('kpiSmTotalStocksSub');
                const kpiCap = document.getElementById('kpiSmTotalCapital');
                const kpiCapSub = document.getElementById('kpiSmTotalCapitalSub');
                const kpiDom = document.getElementById('kpiSmAvgDominance');
                const kpiDomSub = document.getElementById('kpiSmAvgDominanceSub');
                const kpiLead = document.getElementById('kpiSmTopLeader');
                const kpiLeadSub = document.getElementById('kpiSmTopLeaderSub');

                if (kpiStocks) kpiStocks.textContent = `${data.count || this._smartMoneyStocks.length} Setups`;
                if (kpiStocksSub) kpiStocksSub.textContent = `Strategy: ${this._smartMoneyStrategy.replace('_', ' ')}`;
                if (kpiCap) kpiCap.textContent = `₹${Number(summary.total_smart_money_cr || 0).toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr`;
                if (kpiCapSub) kpiCapSub.textContent = `Total Capital: ₹${Number(summary.total_capital_deployed_cr || 0).toLocaleString(undefined, {maximumFractionDigits:0})} Cr`;
                if (kpiDom) kpiDom.textContent = `${summary.avg_smart_money_dominance_pct || 0}%`;
                if (kpiDomSub) kpiDomSub.textContent = `Smart Money vs Domestic Ratio`;
                if (kpiLead) kpiLead.textContent = summary.top_conviction_ticker ? summary.top_conviction_ticker.replace('.NS', '') : 'None';
                if (kpiLeadSub) kpiLeadSub.textContent = summary.top_conviction_name ? `${summary.top_conviction_name} (Score ${summary.top_conviction_score || 0})` : 'Awaiting data';

                this.renderSmartMoneyTable(this._smartMoneyStocks);

                // Auto-inspect the top stock if available
                if (this._smartMoneyStocks.length > 0) {
                    const targetStock = this._smartMoneyStocks.find(s => s.ticker === this._selectedTicker) || this._smartMoneyStocks[0];
                    this.inspectSmartMoneyStock(targetStock);
                }
            } catch (err) {
                console.error('Error loading smart money radar:', err);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="10" style="padding:2rem;text-align:center;color:#ef4444;">Failed to load Smart Money Radar: ${err.message}. Please retry.</td></tr>`;
                }
            }
        },

        renderSmartMoneyTable(stocks) {
            const tbody = document.getElementById('instSmTableBody');
            const countBadge = document.getElementById('instSmCountBadge');
            if (countBadge) countBadge.textContent = `${stocks.length} signals`;
            if (!tbody) return;

            if (!stocks.length) {
                tbody.innerHTML = '<tr><td colspan="10" style="padding:2.5rem;text-align:center;color:#71717a;">No tracked smart money signals found matching the selected strategy and status filters.</td></tr>';
                return;
            }

            tbody.innerHTML = stocks.map((s, idx) => {
                const isSelected = this._smartMoneySelectedStock && (this._smartMoneySelectedStock.ticker === s.ticker);
                const cleanTicker = (s.ticker || '').replace('.NS', '');

                // 1. Ticker / Co
                const compName = s.company_name || s.ticker;
                const capCat = s.cap_category || s.sector || '';

                // 2. Strategy Archetype
                const strat = s.strategy || s.strategy_archetype || s.accumulation_signal_badge || 'WHALE_CONVICTION';
                let stratBg = 'rgba(56,189,248,0.15)', stratCol = '#38bdf8', stratBorder = 'rgba(56,189,248,0.35)';
                if (strat === 'WHALE_CONVICTION') {
                    stratBg = 'rgba(99,102,241,0.18)'; stratCol = '#818cf8'; stratBorder = 'rgba(99,102,241,0.35)';
                } else if (strat === 'BLOCK_DEAL_MOMENTUM') {
                    stratBg = 'rgba(168,85,247,0.18)'; stratCol = '#c084fc'; stratBorder = 'rgba(168,85,247,0.35)';
                } else if (strat === 'DUAL_ACCELERATION') {
                    stratBg = 'rgba(16,185,129,0.18)'; stratCol = '#34d399'; stratBorder = 'rgba(16,185,129,0.35)';
                } else if (strat === 'DOMESTIC_ABSORPTION') {
                    stratBg = 'rgba(239,68,68,0.18)'; stratCol = '#f87171'; stratBorder = 'rgba(239,68,68,0.35)';
                }

                // 3. Signal Date & Days Elapsed
                const sigDate = s.signal_date || '—';
                const daysElapsed = s.days_elapsed != null ? `${s.days_elapsed}d` : (s.days_on_radar != null ? `${s.days_on_radar}d` : '—');

                // 4. Price (Current & Signal Entry)
                const priceStr = s.current_price != null ? `₹${Number(s.current_price).toLocaleString('en-IN', {minimumFractionDigits:1, maximumFractionDigits:2})}` : '—';
                const sigPriceStr = s.signal_price != null ? `₹${Number(s.signal_price).toFixed(1)}` : '—';

                // 5. Outcome Return %
                const retSig = s.outcome_return_pct != null ? s.outcome_return_pct : (s.return_since_signal_pct != null ? s.return_since_signal_pct : 0);
                const retSigStr = (s.outcome_return_pct != null || s.return_since_signal_pct != null) ? `${retSig >= 0 ? '+' : ''}${Number(retSig).toFixed(2)}%` : '—';
                const retSigCol = retSig >= 0 ? '#34d399' : '#f87171';

                // 6. Smart Money Capital
                const smCrVal = Number(s.smart_money_inflow_cr || s.initial_smart_money_cr || s.capital_cr || 0);
                const smCrStr = `₹${smCrVal.toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr`;

                // 7. Whales Count & Summary
                const whaleCnt = s.whale_count != null ? s.whale_count : (s.whale_buyers_summary || s.whale_buyers || []).length;
                const whales = (s.whale_buyers_summary || []).slice(0, 1);
                const whalesHtml = whales.length ? `<div style="font-size:0.62rem;color:#a1a1aa;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${whales[0]}</div>` : '';

                // 8. Conviction Score
                const scoreVal = Number(s.conviction_score != null ? s.conviction_score : (s.initial_score != null ? s.initial_score : (s.smart_money_conviction_score || 0)));
                const scoreStr = scoreVal.toFixed(1);
                let scoreCol = '#38bdf8';
                if (scoreVal >= 80) scoreCol = '#10b981';
                else if (scoreVal >= 60) scoreCol = '#38bdf8';
                else if (scoreVal < 40) scoreCol = '#f59e0b';

                // 9. Lifecycle Status Badge
                const status = (s.lifecycle_status || 'ACTIVE').toUpperCase();
                let stBg = 'rgba(16,185,129,0.18)', stCol = '#34d399', stBorder = 'rgba(16,185,129,0.35)', stIcon = '🟢';
                if (status === 'TARGET_HIT') {
                    stBg = 'rgba(56,189,248,0.18)'; stCol = '#38bdf8'; stBorder = 'rgba(56,189,248,0.35)'; stIcon = '🎯';
                } else if (status === 'COOLING_OFF') {
                    stBg = 'rgba(245,158,11,0.18)'; stCol = '#fbbf24'; stBorder = 'rgba(245,158,11,0.35)'; stIcon = '❄️';
                } else if (status === 'DISTRIBUTION_EXIT') {
                    stBg = 'rgba(239,68,68,0.18)'; stCol = '#f87171'; stBorder = 'rgba(239,68,68,0.35)'; stIcon = '🛑';
                }

                return `
                    <tr id="smRow-${cleanTicker}" onclick="app.inspectSmartMoneyStock('${s.ticker}')" style="border-bottom:1px solid rgba(255,255,255,0.06);cursor:pointer;background:${isSelected ? 'rgba(56,189,248,0.08)' : 'transparent'};transition:background 0.15s;" onmouseover="if(!this.dataset.selected) this.style.background='rgba(255,255,255,0.03)'" onmouseout="if(!this.dataset.selected) this.style.background='transparent'">
                        <td style="padding:0.45rem 0.6rem;">
                            <div style="font-weight:800;color:#ffffff;font-family:var(--font-mono);font-size:0.8rem;display:flex;align-items:center;gap:0.3rem;">
                                <span>${cleanTicker}</span>
                                <button type="button" class="btn-ticker-refresh" onclick="event.stopPropagation(); app.refreshSingleStockPrice('${s.ticker}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.75rem;padding:0 0.15rem;opacity:0.75;line-height:1;transition:all 0.15s;" title="Refresh live price for ${s.ticker}">↻</button>
                                <span style="font-size:0.6rem;color:#71717a;font-weight:600;">${capCat}</span>
                            </div>
                            <div style="font-size:0.65rem;color:#a1a1aa;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                                ${compName}
                            </div>
                        </td>
                        <td style="padding:0.45rem 0.5rem;">
                            <span class="badge" style="background:${stratBg};color:${stratCol};border:1px solid ${stratBorder};font-size:0.62rem;padding:0.12rem 0.35rem;white-space:nowrap;font-weight:700;">
                                ${strat}
                            </span>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);">
                            <div style="font-weight:700;color:#f4f4f5;font-size:0.72rem;">${sigDate}</div>
                            <div style="font-size:0.62rem;color:#71717a;">${daysElapsed}</div>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);">
                            <div style="font-weight:700;color:#f4f4f5;font-size:0.75rem;">${priceStr}</div>
                            <div style="font-size:0.62rem;color:#71717a;">Entry: ${sigPriceStr}</div>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);">
                            <div style="font-weight:800;color:${retSigCol};font-size:0.78rem;">${retSigStr}</div>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);">
                            <div style="font-weight:800;color:#10b981;font-size:0.78rem;">${smCrStr}</div>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);">
                            <div style="font-weight:700;color:#d4d4d8;font-size:0.72rem;">${whaleCnt} Whales</div>
                            ${whalesHtml}
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);">
                            <div style="font-weight:800;color:${scoreCol};font-size:0.8rem;">${scoreStr}</div>
                            <div style="font-size:0.6rem;color:#71717a;">/ 100</div>
                        </td>
                        <td style="padding:0.45rem 0.5rem;">
                            <span class="badge" style="background:${stBg};color:${stCol};border:1px solid ${stBorder};font-size:0.62rem;padding:0.12rem 0.35rem;white-space:nowrap;font-weight:700;">
                                ${stIcon} ${status}
                            </span>
                        </td>
                        <td style="padding:0.45rem 0.4rem;text-align:center;">
                            <a href="/stock/${encodeURIComponent(s.ticker)}" target="_blank" onclick="event.stopPropagation();" title="Open Ticker Intel" class="btn btn-sm" style="background:#18181b;color:#a1a1aa;border:1px solid rgba(255,255,255,0.15);padding:0.15rem 0.35rem;font-size:0.65rem;border-radius:4px;text-decoration:none;">
                                ↗
                            </a>
                        </td>
                    </tr>
                `;
            }).join('');
        },



        async inspectSmartMoneyStock(stockOrTicker) {

            let stock = typeof stockOrTicker === 'object' ? stockOrTicker : (this._smartMoneyStocks || []).find(s => s.ticker === stockOrTicker);

            if (!stock) {

                if (typeof stockOrTicker === 'string') {

                    stock = { ticker: stockOrTicker };

                } else {

                    return;

                }

            }

            this._smartMoneySelectedStock = stock;

            this._selectedTicker = stock.ticker;



            // Highlight selected row in table

            const cleanTicker = stock.ticker.replace('.NS', '');

            (this._smartMoneyStocks || []).forEach(s => {

                const row = document.getElementById('smRow-' + s.ticker.replace('.NS', ''));

                if (row) {

                    const isMatch = s.ticker === stock.ticker;

                    row.style.background = isMatch ? 'rgba(56,189,248,0.12)' : 'transparent';

                    row.dataset.selected = isMatch ? 'true' : '';

                }

            });



            // Update Header & Ticker

            const tEl = document.getElementById('instSmSelectedTicker');

            const nEl = document.getElementById('instSmSelectedCompanyName');

            const bEl = document.getElementById('instSmSelectedBadge');

            const tfEl = document.getElementById('instSmSelectedTimeframe');

            const linkEl = document.getElementById('instSmSelectedStockLink');



            if (tEl) tEl.textContent = stock.ticker;

            if (nEl) nEl.textContent = stock.company_name ? `${stock.company_name} · ${stock.sector || ''}` : stock.sector || '';

            if (bEl) {

                bEl.textContent = stock.accumulation_signal_badge || '⭐ Smart Money Flow';

                if (stock.classification_category === 'domestic_absorption') {

                    bEl.style.background = 'rgba(239,68,68,0.15)';

                    bEl.style.color = '#f87171';

                    bEl.style.borderColor = 'rgba(239,68,68,0.35)';

                } else {

                    bEl.style.background = 'rgba(16,185,129,0.15)';

                    bEl.style.color = '#34d399';

                    bEl.style.borderColor = 'rgba(16,185,129,0.35)';

                }

            }

            if (tfEl) tfEl.textContent = `Horizon: ${this._smartMoneyWindow.toUpperCase()} (${this._smartMoneyRawData ? this._smartMoneyRawData.period_description : 'Rolling Lookback'})`;

            if (linkEl) linkEl.href = `/stock/${encodeURIComponent(stock.ticker)}`;



            // Update Price & Returns Strip

            const pVal = document.getElementById('instSmPriceVal');

            const r7Val = document.getElementById('instSmRet7dVal');

            const r30Val = document.getElementById('instSmRet30dVal');

            const r1yVal = document.getElementById('instSmRet1yVal');

            const mcVal = document.getElementById('instSmMcapVal');



            if (pVal) pVal.textContent = stock.current_price != null ? `₹${Number(stock.current_price).toLocaleString('en-IN', {minimumFractionDigits:1, maximumFractionDigits:2})}` : '—';

            if (r7Val) {

                const v = stock.return_7d_pct != null ? stock.return_7d_pct : 0;

                r7Val.textContent = `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;

                r7Val.style.color = v >= 0 ? '#34d399' : '#f87171';

            }

            if (r30Val) {

                const v = stock.return_30d_pct != null ? stock.return_30d_pct : 0;

                r30Val.textContent = `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;

                r30Val.style.color = v >= 0 ? '#34d399' : '#f87171';

            }

            if (r1yVal) {

                const v = stock.return_1y_pct != null ? stock.return_1y_pct : 0;

                r1yVal.textContent = `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;

                r1yVal.style.color = v >= 0 ? '#34d399' : '#f87171';

            }

            if (mcVal) mcVal.textContent = stock.market_cap_cr ? `₹${Number(stock.market_cap_cr).toLocaleString(undefined, {maximumFractionDigits:0})} Cr` : '—';

            // Populate Signal Tracking & Historical Entry Ledger Card
            const newEntrantBadge = document.getElementById('instSmNewEntrantBadge');
            const sigDateVal = document.getElementById('instSmSignalDateVal');
            const daysOnRadarVal = document.getElementById('instSmDaysOnRadarVal');
            const sigPriceVal = document.getElementById('instSmSignalPriceVal');
            const retSigVal = document.getElementById('instSmReturnSinceSignalVal');
            const peakGainVal = document.getElementById('instSmPeakGainVal');

            if (newEntrantBadge) {
                if (stock.is_new_entrant) {
                    newEntrantBadge.textContent = '🆕 New Entrant (≤14d)';
                    newEntrantBadge.style.background = 'rgba(16,185,129,0.18)';
                    newEntrantBadge.style.color = '#34d399';
                    newEntrantBadge.style.borderColor = 'rgba(16,185,129,0.4)';
                } else {
                    newEntrantBadge.textContent = 'Veteran Signal';
                    newEntrantBadge.style.background = '#18181b';
                    newEntrantBadge.style.color = '#a1a1aa';
                    newEntrantBadge.style.borderColor = 'rgba(255,255,255,0.15)';
                }
            }
            if (sigDateVal) sigDateVal.textContent = stock.signal_date || '—';
            if (daysOnRadarVal) daysOnRadarVal.textContent = stock.days_on_radar != null ? `${stock.days_on_radar} days on radar` : '-- days on radar';
            if (sigPriceVal) sigPriceVal.textContent = stock.signal_price != null ? `₹${Number(stock.signal_price).toFixed(2)}` : '₹--';
            if (retSigVal) {
                const r = stock.return_since_signal_pct != null ? stock.return_since_signal_pct : 0;
                retSigVal.textContent = stock.return_since_signal_pct != null ? `${r >= 0 ? '+' : ''}${r.toFixed(1)}%` : '--';
                retSigVal.style.color = r >= 0 ? '#34d399' : '#f87171';
            }
            if (peakGainVal) {
                const maxG = stock.max_gain_pct != null ? stock.max_gain_pct : (stock.return_since_signal_pct != null ? stock.return_since_signal_pct : 0);
                const peakP = stock.peak_price != null ? stock.peak_price : stock.current_price;
                peakGainVal.textContent = peakP != null ? `Peak: +${Number(maxG).toFixed(1)}% (₹${Number(peakP).toFixed(1)})` : 'Peak: --';
            }

            // Populate Emerging Fundamentals & EPS Growth Card
            const emergingBadge = document.getElementById('instSmEmergingBadge');
            const epsYoYVal = document.getElementById('instSmEpsYoYVal');
            const epsActualVal = document.getElementById('instSmEpsActualVal');
            const peVal = document.getElementById('instSmPeVal');
            const beatStreakVal = document.getElementById('instSmBeatStreakVal');
            const emergingSummary = document.getElementById('instSmEmergingSummaryText');

            if (emergingBadge) {
                if (stock.is_emerging && stock.has_good_eps) {
                    emergingBadge.textContent = '🌟 Emerging EPS Rocket';
                    emergingBadge.style.background = 'rgba(245,158,11,0.18)';
                    emergingBadge.style.color = '#fbbf24';
                    emergingBadge.style.borderColor = 'rgba(245,158,11,0.45)';
                } else if (stock.is_emerging) {
                    emergingBadge.textContent = '🌱 Small/Micro Cap';
                    emergingBadge.style.background = 'rgba(56,189,248,0.15)';
                    emergingBadge.style.color = '#38bdf8';
                    emergingBadge.style.borderColor = 'rgba(56,189,248,0.35)';
                } else {
                    emergingBadge.textContent = stock.cap_category || 'Mid/Large Cap';
                    emergingBadge.style.background = '#18181b';
                    emergingBadge.style.color = '#a1a1aa';
                    emergingBadge.style.borderColor = 'rgba(255,255,255,0.15)';
                }
            }

            if (epsYoYVal) {
                const y = stock.eps_growth_yoy;
                epsYoYVal.textContent = y != null ? `${y >= 0 ? '+' : ''}${y.toFixed(1)}%` : 'N/A';
                if (y != null && y >= 20) epsYoYVal.style.color = '#34d399';
                else if (y != null && y > 0) epsYoYVal.style.color = '#38bdf8';
                else if (y != null && y < 0) epsYoYVal.style.color = '#f87171';
                else epsYoYVal.style.color = '#a1a1aa';
            }

            if (epsActualVal) {
                epsActualVal.textContent = stock.eps_actual != null ? `Latest EPS: ₹${Number(stock.eps_actual).toFixed(2)}` : 'Latest EPS: —';
            }
            if (peVal) {
                peVal.textContent = stock.pe_ratio != null ? `${Number(stock.pe_ratio).toFixed(1)}x` : '—';
            }
            if (beatStreakVal) {
                beatStreakVal.textContent = stock.beat_streak != null ? `${stock.beat_streak}Q Consecutive` : '—';
            }
            if (emergingSummary) {
                const capStr = stock.market_cap_cr ? `₹${Number(stock.market_cap_cr).toLocaleString(undefined, {maximumFractionDigits:0})} Cr` : 'N/A';
                const isEmerg = stock.is_emerging;
                const hasGood = stock.has_good_eps;
                if (isEmerg && hasGood) {
                    emergingSummary.innerHTML = `<span style="color:#fbbf24;font-weight:700;">🌟 High-Conviction Emerging Growth:</span> Small/Micro Cap (${capStr}) experiencing smart money accumulation with robust +${Number(stock.eps_growth_yoy).toFixed(1)}% YoY EPS expansion.`;
                } else if (isEmerg) {
                    emergingSummary.innerHTML = `<span style="color:#38bdf8;font-weight:700;">🌱 Emerging Equities:</span> Small/Micro Cap (${capStr}) institutional accumulation target. Watch upcoming quarterly earnings for fundamental confirmation.`;
                } else if (hasGood) {
                    emergingSummary.innerHTML = `<span style="color:#34d399;font-weight:700;">🚀 Strong EPS Growth:</span> Delivering +${Number(stock.eps_growth_yoy).toFixed(1)}% YoY EPS expansion across ${stock.cap_category || 'established'} scale (${capStr}).`;
                } else {
                    emergingSummary.innerHTML = `Standard institutional accumulation profile across ${stock.cap_category || 'equity'} tier (${capStr}).`;
                }
            }

            // Update Inflow Decomposition & Dominance

            const domRatio = Number(stock.smart_money_dominance_pct || 0);

            const smCr = Number(stock.smart_money_inflow_cr || 0);

            const domCr = Number(stock.domestic_absorption_cr || 0);

            const totCr = Number(stock.total_capital_deployed_cr || 0);

            const score = Number(stock.smart_money_conviction_score || 0).toFixed(1);



            const dBadge = document.getElementById('instSmDominanceRatioBadge');

            const barSm = document.getElementById('instSmDominanceBarSm');

            const barDom = document.getElementById('instSmDominanceBarDom');

            const depCrEl = document.getElementById('instSmDeployedCr');

            const domCrEl = document.getElementById('instSmDomesticCr');

            const convVal = document.getElementById('instSmConvictionVal');

            const insightBox = document.getElementById('instSmInsightBox');



            if (dBadge) dBadge.textContent = `${domRatio.toFixed(1)}% Dominance`;

            if (barSm) barSm.style.width = `${Math.min(100, Math.max(0, domRatio))}%`;

            if (barDom) barDom.style.width = `${Math.min(100, Math.max(0, 100 - domRatio))}%`;

            if (depCrEl) depCrEl.textContent = `₹${smCr.toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr`;

            if (domCrEl) domCrEl.textContent = `₹${domCr.toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:1})} Cr`;

            if (convVal) convVal.textContent = `${score} / 100`;

            // Update Conviction Score 4-Factor Breakdown
            const sb = stock.score_breakdown || {};
            const sbTotal = document.getElementById('instSmScoreBreakdownTotal');
            const sbCap = document.getElementById('instSmScorePartCap');
            const sbDom = document.getElementById('instSmScorePartDom');
            const sbWhale = document.getElementById('instSmScorePartWhale');
            const sbMom = document.getElementById('instSmScorePartMom');
            const sbPenalty = document.getElementById('instSmScoreAbsorptionPenalty');

            if (sbTotal) sbTotal.textContent = `${score} / 100`;
            if (sbCap) sbCap.textContent = `${sb.capital_score != null ? sb.capital_score.toFixed(1) : '--'}/35`;
            if (sbDom) sbDom.textContent = `${sb.dominance_score != null ? sb.dominance_score.toFixed(1) : '--'}/30`;
            if (sbWhale) sbWhale.textContent = `${sb.whale_quality_score != null ? sb.whale_quality_score.toFixed(1) : '--'}/20`;
            if (sbMom) sbMom.textContent = `${sb.momentum_score != null ? sb.momentum_score.toFixed(1) : '--'}/15`;

            if (sbPenalty) {
                if (sb.absorption_penalty || stock.classification === 'domestic_absorption' || stock.classification_category === 'domestic_absorption') {
                    sbPenalty.style.display = 'block';
                    sbPenalty.innerHTML = '⚠️ <b>Absorption Penalty Applied:</b> Domestic Absorption detected. Conviction Score capped at &le; 40.0 pts.';
                } else {
                    sbPenalty.style.display = 'none';
                }
            }



            if (insightBox) {

                if (stock.classification_category === 'domestic_absorption') {

                    insightBox.style.borderLeftColor = '#f59e0b';

                    insightBox.innerHTML = `⚠️ <b style="color:#fbbf24;">Passive Domestic Absorption Alert:</b> Domestic Mutual Funds have absorbed ₹${domCr.toFixed(1)} Cr while Smart Money (FIIs, Sovereign Wealth, Super Investors) represents only ${domRatio.toFixed(1)}% of flow. This setup indicates passive liquidity absorption rather than catalyst-driven re-rating.`;

                } else if (stock.classification_category === 'high_conviction_smart_money') {

                    insightBox.style.borderLeftColor = '#10b981';

                    insightBox.innerHTML = `⭐ <b style="color:#34d399;">High-Conviction Smart Money Accumulation:</b> Smart Money accounts for <b>${domRatio.toFixed(1)}%</b> of all capital deployed (₹${smCr.toFixed(1)} Cr). Supported by ${stock.smart_money_buyers_count || 0} distinct whale entities with catalytic fundamental conviction.`;

                } else if (stock.classification_category === 'fii_whale_inflow') {

                    insightBox.style.borderLeftColor = '#818cf8';

                    insightBox.innerHTML = `🚀 <b style="color:#818cf8;">Foreign Institutional Inflow:</b> Sustained FII & Sovereign Wealth accumulation of ₹${smCr.toFixed(1)} Cr, representing dominant foreign accumulation over domestic retail churn.`;

                } else {

                    insightBox.style.borderLeftColor = '#38bdf8';

                    insightBox.innerHTML = `🎯 <b style="color:#38bdf8;">Institutional Accumulation:</b> ₹${smCr.toFixed(1)} Cr smart money deployed with a conviction score of <b>${score}/100</b> across the ${this._smartMoneyWindow.toUpperCase()} window.`;

                }

            }



            // Render Whale Buyers Table

            const buyersTbody = document.getElementById('instSmBuyersTableBody');

            const buyersBadge = document.getElementById('instSmBuyerCountBadge');

            const buyers = stock.whale_buyers || [];

            if (buyersBadge) buyersBadge.textContent = `${buyers.length} Buyers Logged`;



            if (buyersTbody) {

                if (!buyers.length) {

                    buyersTbody.innerHTML = '<tr><td colspan="6" style="padding:1.5rem;text-align:center;color:#71717a;">No named whale filings logged in this specific window. Inflow inferred from exchange bulk totals.</td></tr>';

                } else {

                    buyersTbody.innerHTML = buyers.map(b => {

                        const isFII = (b.entity_type || '').includes('FII') || (b.entity_type || '').includes('Foreign');

                        const isSuper = (b.entity_type || '').includes('Super');

                        const isBlock = (b.entity_type || '').includes('Block');

                        let entCol = '#38bdf8';

                        let entBg = 'rgba(56,189,248,0.12)';

                        if (isSuper) { entCol = '#fbbf24'; entBg = 'rgba(245,158,11,0.12)'; }

                        else if (isBlock) { entCol = '#c084fc'; entBg = 'rgba(168,85,247,0.12)'; }

                        else if (isFII) { entCol = '#818cf8'; entBg = 'rgba(99,102,241,0.12)'; }



                        const buyerName = b.buyer_name || b.name || b.client_name || 'Anonymous Institution';
                        const depCr = Number(b.deployed_cr != null ? b.deployed_cr : (b.capital_cr != null ? b.capital_cr : (b.value_cr || 0)));

                        return `

                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">

                                <td style="padding:0.4rem 0.6rem;font-weight:700;color:#ffffff;">${buyerName}</td>

                                <td style="padding:0.4rem 0.5rem;">

                                    <span class="badge" style="background:${entBg};color:${entCol};font-size:0.62rem;padding:0.1rem 0.35rem;border:1px solid rgba(255,255,255,0.1);">${b.entity_type || 'Institution'}</span>

                                </td>

                                <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#10b981;">₹${depCr.toFixed(2)} Cr</td>

                                <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#d4d4d8;">${b.stake_pct ? b.stake_pct + '%' : (b.quantity ? Number(b.quantity).toLocaleString() + ' sh' : '—')}</td>

                                <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#a1a1aa;">${b.avg_price ? '₹' + Number(b.avg_price).toFixed(2) : (b.price ? '₹' + Number(b.price).toFixed(2) : '—')}</td>

                                <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#71717a;font-size:0.65rem;">${b.date || b.deal_date || b.filing_date || '—'}</td>

                            </tr>

                        `;

                    }).join('');

                }

            }



            // Render Block / Bulk Deals section

            const blocksContainer = document.getElementById('instSmBlockDealsContainer');

            if (blocksContainer) {

                const blockDeals = (stock.whale_buyers || []).filter(b => (b.entity_type || '').includes('Block') || b.deal_type);

                if (!blockDeals.length) {

                    blocksContainer.innerHTML = '<div style="color:#71717a;font-size:0.72rem;text-align:center;padding:1rem;">No major exchange block deals logged in this lookback window.</div>';

                } else {

                    blocksContainer.innerHTML = blockDeals.map(d => {
                        const dealBuyer = d.buyer_name || d.name || d.client_name || 'Block Deal Buyer';
                        const dealCr = Number(d.deployed_cr != null ? d.deployed_cr : (d.capital_cr != null ? d.capital_cr : (d.value_cr || 0)));

                        return `

                        <div style="background:#18181b;border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:0.35rem 0.55rem;margin-bottom:0.35rem;display:flex;justify-content:space-between;align-items:center;font-size:0.72rem;">

                            <div>

                                <span style="font-weight:700;color:#34d399;font-family:var(--font-mono);margin-right:0.35rem;">[BUY]</span>

                                <strong style="color:#ffffff;">${dealBuyer}</strong>

                            </div>

                            <div style="font-family:var(--font-mono);color:#a1a1aa;text-align:right;">

                                ${d.quantity ? Number(d.quantity).toLocaleString() + ' shares' : ''} ${d.avg_price ? '@ ₹' + Number(d.avg_price).toFixed(2) : ''} (₹${dealCr.toFixed(2)} Cr) | <span style="color:#71717a;">${d.date || d.deal_date || ''}</span>

                            </div>

                        </div>

                    `;
                    }).join('');
                }
            }


            // Fetch 360° Forensic Dossier and populate 4-tab drawer
            const badge = document.getElementById('instSmBuyerCountBadge');
            if (badge) badge.textContent = '⏳ Loading forensics...';
            const finBadge = document.getElementById('instSmFinCountBadge');
            if (finBadge) finBadge.textContent = '⏳';
            const dealsBadge = document.getElementById('instSmDealsCountBadge');
            if (dealsBadge) dealsBadge.textContent = '⏳';
            const sigBadge = document.getElementById('instSmSignalCountBadge');
            if (sigBadge) sigBadge.textContent = '⏳';

            this._smartMoneyForensicDossier = null;
            try {
                const fRes = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(stock.ticker)}/forensics`);
                if (fRes.ok) {
                    const dossier = await fRes.json();
                    this._smartMoneyForensicDossier = dossier;
                    this.renderForensicsTab(this._smartMoneyForensicTab);
                }
            } catch (err) {
                console.warn('[INST] Forensic dossier fetch failed:', err);
            }
        },

        // =========================================================================
        // 🛡️ Institutional Data Integrity & Verification Subsystem
        // =========================================================================
        institutionalIntegrityData: null,

        async loadInstitutionalIntegrityStatus() {
            try {
                const res = await fetch(API_BASE + '/api/v1/institutional/integrity');
                if (!res.ok) return;
                const data = await res.json();
                this.institutionalIntegrityData = data;
                this.renderInstitutionalIntegrityBadge(data);
                this.renderInstitutionalIntegrityModal(data);
            } catch (err) {
                console.warn('[INSTITUTIONAL:INTEGRITY] Failed to fetch integrity status:', err);
            }
        },

        renderInstitutionalIntegrityBadge(data) {
            const badgeBtn = document.getElementById('btnInstIntegrityModal');
            const badgeText = document.getElementById('instIntegrityBadgeText');
            const icon = document.getElementById('instIntegrityIcon');
            if (!badgeBtn || !badgeText) return;

            const score = data.health_score != null ? data.health_score : 100;

            if (score >= 95) {
                badgeBtn.style.borderColor = 'rgba(16,185,129,0.35)';
                badgeBtn.style.color = '#10b981';
                if (icon) icon.textContent = '🛡️';
                badgeText.textContent = `Data Integrity: Optimal (${score}%)`;
            } else if (score >= 80) {
                badgeBtn.style.borderColor = 'rgba(245,158,11,0.35)';
                badgeBtn.style.color = '#f59e0b';
                if (icon) icon.textContent = '⚠️';
                badgeText.textContent = `Data Integrity: Warnings (${score}%)`;
            } else {
                badgeBtn.style.borderColor = 'rgba(239,68,68,0.35)';
                badgeBtn.style.color = '#ef4444';
                if (icon) icon.textContent = '🚨';
                badgeText.textContent = `Data Integrity: Degraded (${score}%)`;
            }
        },

        openInstitutionalIntegrityModal() {
            const modal = document.getElementById('instIntegrityModal');
            if (modal) {
                modal.style.display = 'flex';
                this.loadInstitutionalIntegrityStatus();
            }
        },

        closeInstitutionalIntegrityModal() {
            const modal = document.getElementById('instIntegrityModal');
            if (modal) modal.style.display = 'none';
        },

        switchIntegrityModalTab(tab) {
            const tabs = ['findings', 'provenance', 'stock'];
            tabs.forEach(t => {
                const btn = document.getElementById('btnInstModalTab-' + t);
                const view = document.getElementById('instModalView-' + t);
                const isActive = (t === tab);
                if (view) view.style.display = isActive ? 'block' : 'none';
                if (btn) {
                    if (isActive) {
                        btn.style.background = '#18181b';
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

            const searchBox = document.getElementById('instModalStockSearchBox');
            if (searchBox) {
                searchBox.style.display = (tab === 'stock') ? 'flex' : 'none';
            }
        },

        renderInstitutionalIntegrityModal(data) {
            if (!data) return;

            // KPI 1: Health Score
            const kpiScore = document.getElementById('instKpiHealthScore');
            const kpiScoreLbl = document.getElementById('instKpiHealthLabel');
            const statusBadge = document.getElementById('instModalHealthStatusBadge');
            const score = data.health_score != null ? data.health_score : 100;
            const status = data.status || 'OPTIMAL';

            if (kpiScore) {
                kpiScore.textContent = `${score}%`;
                kpiScore.style.color = score >= 95 ? '#10b981' : (score >= 80 ? '#f59e0b' : '#ef4444');
            }
            if (kpiScoreLbl) {
                kpiScoreLbl.textContent = score >= 95 ? 'Zero Faults' : `${status} status`;
                kpiScoreLbl.style.color = score >= 95 ? '#34d399' : (score >= 80 ? '#fbbf24' : '#f87171');
            }
            if (statusBadge) {
                statusBadge.textContent = `SYSTEM: ${status} (${score}%)`;
                statusBadge.style.color = score >= 95 ? '#10b981' : (score >= 80 ? '#f59e0b' : '#ef4444');
                statusBadge.style.borderColor = score >= 95 ? 'rgba(16,185,129,0.4)' : (score >= 80 ? 'rgba(245,158,11,0.4)' : 'rgba(239,68,68,0.4)');
            }

            // KPI 2: Total Audited Records
            const kpiAudited = document.getElementById('instKpiAuditedCount');
            if (kpiAudited) {
                kpiAudited.textContent = Number(data.total_audited_records || 0).toLocaleString();
            }

            // KPI 3: Quarantined
            const kpiQuarantined = document.getElementById('instKpiQuarantinedCount');
            if (kpiQuarantined) {
                kpiQuarantined.textContent = Number(data.quarantined_records || 0).toLocaleString();
            }

            // KPI 4: Warnings
            const kpiWarnings = document.getElementById('instKpiWarningsCount');
            if (kpiWarnings) {
                const totalWarn = (data.open_issues_count || 0) + (data.anomalies_detected || 0);
                kpiWarnings.textContent = totalWarn.toString();
            }

            // Cadence Statuses
            const cadences = data.cadences || {};

            // Daily Cadence
            const daily = cadences.daily_fii_dii || {};
            const dailyBadge = document.getElementById('instCadenceBadgeDaily');
            const dailyDetails = document.getElementById('instCadenceDetailsDaily');
            const dailyDate = document.getElementById('instCadenceDateDaily');
            if (dailyBadge) {
                dailyBadge.textContent = daily.status || 'HEALTHY';
                dailyBadge.style.color = (daily.status === 'HEALTHY' || daily.status === 'PASS') ? '#10b981' : '#f59e0b';
            }
            if (dailyDetails) {
                dailyDetails.textContent = daily.message || (daily.missing_trading_days && daily.missing_trading_days.length ? `Missing dates: ${daily.missing_trading_days.join(', ')}` : 'All recent trading sessions verified.');
            }
            if (dailyDate) {
                dailyDate.textContent = daily.latest_trading_date_on_record || '--';
            }

            // Monthly Cadence
            const monthly = cadences.monthly_amfi_portfolios || {};
            const monthlyBadge = document.getElementById('instCadenceBadgeMonthly');
            const monthlyDetails = document.getElementById('instCadenceDetailsMonthly');
            const monthlyDate = document.getElementById('instCadenceDateMonthly');
            if (monthlyBadge) {
                monthlyBadge.textContent = monthly.status || 'HEALTHY';
                monthlyBadge.style.color = (monthly.status === 'HEALTHY' || monthly.status === 'PASS') ? '#10b981' : '#f59e0b';
            }
            if (monthlyDetails) {
                monthlyDetails.textContent = monthly.message || `Disclosures fresh within ${monthly.days_since_latest || 0} days.`;
            }
            if (monthlyDate) {
                monthlyDate.textContent = monthly.latest_portfolio_date || '--';
            }

            // Quarterly Cadence
            const quarterly = cadences.quarterly_nse_shareholding || {};
            const quarterlyBadge = document.getElementById('instCadenceBadgeQuarterly');
            const quarterlyDetails = document.getElementById('instCadenceDetailsQuarterly');
            const quarterlyTarget = document.getElementById('instCadenceQuarterTarget');
            const quarterlyDeadline = document.getElementById('instCadenceDeadline');
            if (quarterlyBadge) {
                quarterlyBadge.textContent = quarterly.status || 'HEALTHY';
                quarterlyBadge.style.color = (quarterly.status === 'HEALTHY' || quarterly.status === 'PASS') ? '#10b981' : '#f59e0b';
            }
            if (quarterlyDetails) {
                quarterlyDetails.textContent = quarterly.is_filing_season ? 'Active SEBI Reg 31 filing season underway.' : 'Statutory filing season closed.';
            }
            if (quarterlyTarget) {
                quarterlyTarget.textContent = quarterly.current_filing_quarter || '--';
            }
            if (quarterlyDeadline) {
                quarterlyDeadline.textContent = quarterly.statutory_deadline || '--';
            }

            // Render Findings Table
            this.renderIntegrityFindingsTable(data.recent_findings || []);

            // Render Provenance Table
            this.renderIntegrityProvenanceTable(data.provenance_ledger || []);
        },

        renderIntegrityFindingsTable(findings) {
            const tbody = document.getElementById('instModalFindingsTableBody');
            if (!tbody) return;

            if (!findings || !findings.length) {
                tbody.innerHTML = '<tr><td colspan="6" style="padding:2rem;text-align:center;color:#10b981;font-weight:600;">✓ Zero invariant violations or integrity warnings found. All checks passed.</td></tr>';
                return;
            }

            tbody.innerHTML = findings.map(f => {
                let sevBg = 'rgba(16,185,129,0.15)';
                let sevCol = '#10b981';
                if (f.severity === 'WARNING') {
                    sevBg = 'rgba(245,158,11,0.15)';
                    sevCol = '#f59e0b';
                } else if (f.severity === 'CRITICAL_ERROR' || f.severity === 'ERROR') {
                    sevBg = 'rgba(239,68,68,0.15)';
                    sevCol = '#ef4444';
                } else if (f.severity === 'INFO') {
                    sevBg = 'rgba(56,189,248,0.15)';
                    sevCol = '#38bdf8';
                }

                const ticker = f.ticker ? `<span style="font-weight:700;color:#ffffff;cursor:pointer;" onclick="app.inspectStockIntegrity('${f.ticker}')">${f.ticker.replace('.NS','')}</span>` : '<span style="color:#71717a;">SYSTEM</span>';
                const period = f.period_or_date || '—';
                const details = f.details || f.message || JSON.stringify(f.details_json || {});

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                        <td style="padding:0.45rem 0.65rem;font-family:var(--font-mono);color:#94a3b8;font-size:0.68rem;">${f.check_category}</td>
                        <td style="padding:0.45rem 0.5rem;font-weight:700;color:#f8fafc;">${f.check_name}</td>
                        <td style="padding:0.45rem 0.5rem;">
                            <span class="badge" style="background:${sevBg};color:${sevCol};border:1px solid ${sevCol}40;font-size:0.62rem;padding:0.1rem 0.35rem;font-weight:700;">${f.severity}</span>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);">${ticker}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#d4d4d8;">${period}</td>
                        <td style="padding:0.45rem 0.65rem;color:#cbd5e1;font-size:0.7rem;line-height:1.35;">${details}</td>
                    </tr>
                `;
            }).join('');
        },

        renderIntegrityProvenanceTable(records) {
            const tbody = document.getElementById('instModalProvenanceTableBody');
            if (!tbody) return;

            if (!records || !records.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#71717a;">No cryptographic provenance entries logged yet. Provenance hashes are recorded on real-source ingestion.</td></tr>';
                return;
            }

            tbody.innerHTML = records.map(r => {
                const shortHash = (r.response_hash || '').substring(0, 16) + '...';
                const shortUrl = (r.source_url || '').length > 35 ? (r.source_url.substring(0, 32) + '...') : (r.source_url || '—');
                const sizeStr = r.payload_size_bytes ? `${(r.payload_size_bytes / 1024).toFixed(1)} KB` : '—';
                const timeStr = r.ingested_at ? r.ingested_at.substring(0, 19).replace('T', ' ') : '—';
                const statusCol = r.status === 'AUTHENTIC' ? '#10b981' : (r.status === 'VERIFIED' ? '#38bdf8' : '#f59e0b');

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                        <td style="padding:0.45rem 0.65rem;font-weight:700;color:#ffffff;font-size:0.68rem;">${r.source_name}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#f4f4f5;font-size:0.7rem;">${r.entity_key}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#38bdf8;font-size:0.65rem;" title="${r.response_hash}">${shortHash}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#71717a;font-size:0.65rem;" title="${r.source_url}">${shortUrl}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#a1a1aa;font-size:0.68rem;">${sizeStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#94a3b8;font-size:0.65rem;">${timeStr}</td>
                        <td style="padding:0.45rem 0.5rem;">
                            <span class="badge" style="background:${statusCol}20;color:${statusCol};border:1px solid ${statusCol}50;font-size:0.6rem;padding:0.1rem 0.35rem;font-weight:700;">${r.status}</span>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async inspectStockIntegrity(tickerInput) {
            const ticker = (tickerInput || '').trim().toUpperCase();
            if (!ticker) return;

            this.switchIntegrityModalTab('stock');
            const searchInput = document.getElementById('instModalStockSearchInput');
            if (searchInput) searchInput.value = ticker;

            const container = document.getElementById('instModalStockAuditContainer');
            if (!container) return;

            container.innerHTML = '<div style="text-align:center;padding:2.5rem;color:#38bdf8;font-size:0.8rem;">Running cryptographic provenance inspection and pre-commit invariant audit for <b>' + ticker + '</b>...</div>';

            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/integrity/${encodeURIComponent(ticker)}`);
                if (!res.ok) {
                    container.innerHTML = `<div style="text-align:center;padding:2rem;color:#ef4444;font-size:0.8rem;">Failed to fetch audit data for ${ticker}: HTTP ${res.status}</div>`;
                    return;
                }
                const data = await res.json();
                this.renderStockIntegrityInspector(data, container);
            } catch (err) {
                container.innerHTML = `<div style="text-align:center;padding:2rem;color:#ef4444;font-size:0.8rem;">Inspection error: ${err.message}</div>`;
            }
        },

        renderStockIntegrityInspector(data, container) {
            const sh = data.latest_shareholding || {};
            const inv = data.invariant_verification || {};
            const prov = data.provenance_records || [];
            const findings = data.audit_findings || [];
            const score = data.health_score != null ? data.health_score : 100;
            const scoreCol = score >= 95 ? '#10b981' : (score >= 80 ? '#f59e0b' : '#ef4444');

            container.innerHTML = `
                <div style="display:flex;flex-direction:column;gap:1rem;">
                    <!-- Stock Summary Banner -->
                    <div class="card" style="padding:1rem;background:#121215;border:1px solid rgba(255,255,255,0.12);border-radius:8px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem;">
                        <div>
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span style="font-size:1.2rem;font-weight:800;color:#ffffff;font-family:var(--font-mono);">${data.ticker}</span>
                                <span class="badge" style="background:${scoreCol}20;color:${scoreCol};border:1px solid ${scoreCol}50;font-size:0.7rem;padding:0.15rem 0.5rem;font-weight:700;">
                                    INTEGRITY SCORE: ${score}% (${data.status})
                                </span>
                            </div>
                            <div style="font-size:0.72rem;color:#a1a1aa;margin-top:0.2rem;">
                                Latest Quarter on Record: <b style="color:#ffffff;">${sh.quarter || 'N/A'}</b> · Total Invariant Checks Passed: <b style="color:${inv.valid_invariants ? '#10b981' : '#ef4444'};">${inv.valid_invariants ? 'YES' : 'NO'}</b>
                            </div>
                        </div>
                        <div style="display:flex;gap:1.5rem;font-family:var(--font-mono);font-size:0.72rem;text-align:right;">
                            <div><span style="color:#71717a;">Promoter:</span> <b style="color:#ffffff;">${sh.promoter_pct || 0}%</b></div>
                            <div><span style="color:#71717a;">FII:</span> <b style="color:#ffffff;">${sh.fii_pct || 0}%</b></div>
                            <div><span style="color:#71717a;">DII:</span> <b style="color:#ffffff;">${sh.dii_mf_pct || 0}%</b></div>
                            <div><span style="color:#71717a;">Public:</span> <b style="color:#ffffff;">${sh.public_retail_pct || 0}%</b></div>
                            <div><span style="color:#71717a;">Sum:</span> <b style="color:${inv.valid_invariants ? '#10b981' : '#ef4444'};">${inv.sum_pct != null ? inv.sum_pct.toFixed(2) : '--'}%</b></div>
                        </div>
                    </div>

                    <!-- Provenance Ledger for Stock -->
                    <div class="card" style="padding:0.85rem;background:#121215;border:1px solid rgba(255,255,255,0.1);border-radius:8px;">
                        <div style="font-size:0.78rem;font-weight:700;color:#ffffff;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.4rem;">
                            <span>🔐 Cryptographic Provenance Chain for ${data.ticker}</span>
                            <span class="badge" style="background:#18181b;color:#38bdf8;font-size:0.65rem;">${prov.length} hashes</span>
                        </div>
                        <div style="overflow-x:auto;">
                            <table style="width:100%;border-collapse:collapse;font-size:0.7rem;text-align:left;">
                                <thead style="background:#18181b;color:#a1a1aa;font-family:var(--font-mono);">
                                    <tr>
                                        <th style="padding:0.4rem 0.5rem;">SOURCE</th>
                                        <th style="padding:0.4rem 0.5rem;">ENTITY KEY</th>
                                        <th style="padding:0.4rem 0.5rem;">SHA-256 HASH</th>
                                        <th style="padding:0.4rem 0.5rem;">ENDPOINT</th>
                                        <th style="padding:0.4rem 0.5rem;">INGESTED AT</th>
                                        <th style="padding:0.4rem 0.5rem;">STATUS</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${!prov.length ? '<tr><td colspan="6" style="padding:1.5rem;text-align:center;color:#71717a;">No cryptographic provenance records found for this ticker.</td></tr>' :
                                    prov.map(p => `
                                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                                            <td style="padding:0.35rem 0.5rem;color:#ffffff;font-weight:700;">${p.source_name}</td>
                                            <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);">${p.entity_key}</td>
                                            <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:#38bdf8;" title="${p.response_hash}">${(p.response_hash || '').substring(0, 18)}...</td>
                                            <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:#71717a;">${p.source_url || '—'}</td>
                                            <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:#94a3b8;">${(p.ingested_at || '').substring(0, 19).replace('T', ' ')}</td>
                                            <td style="padding:0.35rem 0.5rem;"><span class="badge" style="background:#10b98120;color:#10b981;font-size:0.6rem;padding:0.1rem 0.35rem;">${p.status}</span></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `;
        },

        async triggerIntegrityVerifyAndRepair() {
            const btn = document.getElementById('btnInstTriggerAudit');
            const spinner = document.getElementById('instAuditBtnSpinner');
            const text = document.getElementById('instAuditBtnText');

            if (btn) btn.disabled = true;
            if (spinner) spinner.style.display = 'inline-block';
            if (text) text.textContent = 'Auditing & Auto-Repairing...';

            try {
                const res = await fetch(API_BASE + '/api/v1/institutional/verify-and-repair', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ repair: true })
                });
                if (res.ok) {
                    await this.loadInstitutionalIntegrityStatus();
                }
            } catch (err) {
                console.error('[INSTITUTIONAL:INTEGRITY] Auto-repair failed:', err);
            } finally {
                if (btn) btn.disabled = false;
                if (spinner) spinner.style.display = 'none';
                if (text) text.textContent = '⚡ Run Audit & Auto-Repair';
            }
        },

    });



})(); // end institutional IIFE

