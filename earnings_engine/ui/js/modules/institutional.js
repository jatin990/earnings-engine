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
            const pages = ['equities', 'investors'];
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

        async loadInstitutionalData() {
            try {
                const [resAcc, resDist, resFunds] = await Promise.all([
                    fetch(API_BASE + '/api/v1/institutional/accumulating?limit=35'),
                    fetch(API_BASE + '/api/v1/institutional/distributing?limit=25'),
                    fetch(API_BASE + '/api/v1/institutional/funds?limit=50')
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

                // Initial inspect ALLCARGO as default benchmark drilldown
                this.searchInstitutionalStock('ALLCARGO.NS');

            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading institutional flows:', e);
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

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:${rowBg};cursor:pointer;transition:background 0.12s;" onclick="app.searchInstitutionalStock('${it.ticker}')" onmouseover="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='rgba(255,255,255,0.03)'" onmouseout="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='transparent'">
                        <td style="padding:0.45rem 0.6rem;font-family:var(--font-mono);font-weight:700;">
                            <span style="color:#38bdf8;">${it.ticker.replace('.NS', '')}</span>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:${scoreCol};">${it.accumulation_score}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret7dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret30dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${it.funds_accumulating_count}</td>
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

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:${rowBg};cursor:pointer;transition:background 0.12s;" onclick="app.searchInstitutionalStock('${it.ticker}')" onmouseover="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='rgba(255,255,255,0.03)'" onmouseout="if('${this._selectedTicker}' !== '${it.ticker}') this.style.background='transparent'">
                        <td style="padding:0.45rem 0.6rem;font-family:var(--font-mono);font-weight:700;">
                            <span style="color:#f87171;">${it.ticker.replace('.NS', '')}</span>
                        </td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f87171;">${it.accumulation_score}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret7dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;">${ret30dStr}</td>
                        <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${it.funds_selling_count}</td>
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

        async searchInstitutionalStock(ticker) {
            if (!ticker) return;
            const cleanTicker = ticker.trim().toUpperCase();
            this._selectedTicker = cleanTicker;
            
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

            if (tickerEl) tickerEl.textContent = data.ticker;
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

                scoreTextEl.innerHTML = `
                    Score: <strong style="color:#38bdf8;">${data.accumulation_score}</strong>
                    &nbsp;·&nbsp; Inflow: <strong style="color:#34d399;">+₹${(data.gross_inflow_cr || 0).toLocaleString()} Cr</strong>
                    &nbsp;·&nbsp; Outflow: <strong style="color:#f87171;">-₹${(data.gross_outflow_cr || 0).toLocaleString()} Cr</strong>
                    &nbsp;·&nbsp; Net: <strong style="color:${netCol};">${netSign}₹${Math.abs(data.net_flow_cr || 0).toLocaleString()} Cr</strong>
                    &nbsp;·&nbsp; 7D: ${ret7dStr}
                    &nbsp;·&nbsp; 30D: ${ret30dStr}
                    &nbsp;·&nbsp; Funds (QoQ): <strong style="color:#34d399;">+${data.funds_accumulating_count}</strong> / <strong style="color:#f87171;">-${data.funds_selling_count}</strong>
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
                                    <th style="padding:0.3rem 0.4rem;">PROMOTER</th>
                                    <th style="padding:0.3rem 0.4rem;">FII / FPI</th>
                                    <th style="padding:0.3rem 0.4rem;">DII / MUTUAL FUNDS</th>
                                    <th style="padding:0.3rem 0.4rem;">RETAIL</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${pats.map((p, idx) => {
                                    const prevP = pats[idx + 1];
                                    const fiiDelta = prevP ? (p.fii_pct - prevP.fii_pct) : 0;
                                    const diiDelta = prevP ? (p.dii_mf_pct - prevP.dii_mf_pct) : 0;
                                    const fiiDeltaStr = prevP ? (fiiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${fiiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${fiiDelta.toFixed(2)}%)</span>`) : '';
                                    const diiDeltaStr = prevP ? (diiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${diiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${diiDelta.toFixed(2)}%)</span>`) : '';

                                    return `
                                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                             <td style="padding:0.35rem 0.4rem;font-weight:700;color:#f8fafc;font-family:var(--font-mono);">${p.quarter}</td>
                                             <td style="padding:0.35rem 0.4rem;color:#cbd5e1;font-family:var(--font-mono);">${p.promoter_pct}%</td>
                                             <td style="padding:0.35rem 0.4rem;color:#38bdf8;font-weight:700;font-family:var(--font-mono);">${p.fii_pct}% ${fiiDeltaStr}</td>
                                             <td style="padding:0.35rem 0.4rem;color:#34d399;font-weight:700;font-family:var(--font-mono);">${p.dii_mf_pct}% ${diiDeltaStr}</td>
                                             <td style="padding:0.35rem 0.4rem;color:#94a3b8;font-family:var(--font-mono);">${p.public_retail_pct}%</td>
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
                                <td style="padding:0.45rem 0.5rem;font-family:var(--font-mono);color:#a7f3d0;font-weight:600;">₹${h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : '—'}</td>
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
                        const actCol = isBuy ? '#34d399' : h.action === 'TRIMMED' || h.action === 'SOLD OUT' ? '#f87171' : '#cbd5e1';
                        const actBg = isBuy ? 'rgba(16,185,129,0.15)' : h.action === 'TRIMMED' || h.action === 'SOLD OUT' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)';
                        const ret30Str = h.return_30d_pct != null ? (h.return_30d_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${h.return_30d_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${h.return_30d_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                        const ret1yStr = h.return_1y_pct != null ? (h.return_1y_pct >= 0 ? `<span style="color:#34d399;font-weight:700;">+${h.return_1y_pct}%</span>` : `<span style="color:#f87171;font-weight:700;">${h.return_1y_pct}%</span>`) : '<span style="color:#64748b;">—</span>';
                        const compName = h.company_name && h.company_name !== h.ticker ? `<div style="font-size:0.68rem;color:#94a3b8;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px;">${h.company_name}</div>` : '';

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);font-weight:700;">
                                    <a href="javascript:void(0)" onclick="app.closeFundModal(); app.searchInstitutionalStock('${h.ticker}')" style="color:#38bdf8;text-decoration:none;">${h.ticker}</a>
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
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);color:#a7f3d0;font-weight:600;">₹${h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : '—'}</td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">₹${(h.holding_value_cr || 0).toLocaleString()} Cr</td>
                                <td style="padding:0.55rem 0.8rem;font-family:var(--font-mono);color:#94a3b8;font-size:0.72rem;">${h.reported_date || '—'}</td>
                                <td style="padding:0.55rem 0.8rem;text-align:center;">
                                    <button type="button" onclick="app.closeFundModal(); app.searchInstitutionalStock('${h.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.2rem 0.5rem;background:rgba(56,189,248,0.1);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);">🔍 Analyze Stock</button>
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
