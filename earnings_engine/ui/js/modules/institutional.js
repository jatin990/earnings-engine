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
        _institutionalLoaded: false,

        switchInstitutionalView(view) {
            const views = ['accumulating', 'distributing', 'funds', 'stock'];
            views.forEach(v => {
                const el = document.getElementById('instView-' + v);
                if (el) el.style.display = (v === view) ? 'block' : 'none';

                const btn = document.getElementById('instBtn-' + v);
                if (btn) {
                    if (v === view) {
                        btn.style.background = 'rgba(59,130,246,0.2)';
                        btn.style.color = '#60a5fa';
                        btn.style.borderColor = 'rgba(59,130,246,0.4)';
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

        async loadInstitutionalData() {
            try {
                const [resAcc, resDist, resFunds] = await Promise.all([
                    fetch(API_BASE + '/api/v1/institutional/accumulating?limit=30'),
                    fetch(API_BASE + '/api/v1/institutional/distributing?limit=20'),
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
                this.searchInstitutionalStock('ALLCARGO.NS', false);

            } catch (e) {
                console.error('[INSTITUTIONAL] Failed loading institutional flows:', e);
            }
        },

        renderInstitutionalAccumulatingTable(items) {
            const tbody = document.getElementById('instAccumulatingTableBody');
            const countEl = document.getElementById('instAccumulatingCount');
            if (countEl) countEl.textContent = items ? items.length : '0';
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No high-accumulation stocks found.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const fundsList = it.funds_accumulating || [];
                const fundsStr = fundsList.slice(0, 2).map(f => f.fund_name).join(', ') + (fundsList.length > 2 ? ` +${fundsList.length - 2} more` : '');
                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;">
                            <a href="javascript:void(0)" onclick="app.searchInstitutionalStock('${it.ticker}')" style="color:#38bdf8;text-decoration:none;">${it.ticker}</a>
                        </td>
                        <td style="padding:0.65rem 0.8rem;color:#f8fafc;font-weight:600;">${it.company_name}</td>
                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${it.sector}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#34d399;">${it.accumulation_score} / 100</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${it.funds_accumulating_count} Funds</td>
                        <td style="padding:0.65rem 0.8rem;color:#cbd5e1;font-size:0.72rem;">${fundsStr}</td>
                        <td style="padding:0.65rem 0.8rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">Inspect</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        renderInstitutionalDistributingTable(items) {
            const tbody = document.getElementById('instDistributingTableBody');
            const countEl = document.getElementById('instDistributingCount');
            if (countEl) countEl.textContent = items ? items.length : '0';
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No high-distribution stocks found.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(it => {
                const exitingList = it.funds_selling || [];
                const exitingStr = exitingList.slice(0, 2).map(f => f.fund_name).join(', ') + (exitingList.length > 2 ? ` +${exitingList.length - 2} more` : '');
                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;">
                            <a href="javascript:void(0)" onclick="app.searchInstitutionalStock('${it.ticker}')" style="color:#f87171;text-decoration:none;">${it.ticker}</a>
                        </td>
                        <td style="padding:0.65rem 0.8rem;color:#f8fafc;font-weight:600;">${it.company_name}</td>
                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${it.sector}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f87171;">${it.accumulation_score} / 100</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${it.funds_selling_count} Funds</td>
                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${exitingStr}</td>
                        <td style="padding:0.65rem 0.8rem;text-align:center;">
                            <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">Inspect</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        renderInstitutionalFundsTable(funds) {
            const tbody = document.getElementById('instFundsTableBody');
            const countEl = document.getElementById('instFundsTrackedCount');
            if (countEl) countEl.textContent = funds ? funds.length + '+' : '50+';
            if (!tbody) return;

            if (!funds || !funds.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No fund profiles loaded.</td></tr>';
                return;
            }

            tbody.innerHTML = funds.map(f => {
                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.8rem;font-weight:700;color:#f8fafc;">${f.fund_name}</td>
                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${f.fund_type}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;">${f.total_positions} Stocks</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${f.buying_actions}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${f.selling_actions}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">₹${f.total_aum_tracked_cr.toLocaleString()} Cr</td>
                        <td style="padding:0.65rem 0.8rem;text-align:center;">
                            <button type="button" onclick="app.inspectFundPortfolio('${f.fund_name.replace(/'/g, "\\'")}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">View Holdings</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async searchInstitutionalStock(ticker, autoSwitch = true) {
            if (!ticker) return;
            const cleanTicker = ticker.trim().toUpperCase();
            try {
                const res = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.renderStockInstitutionalDetails(data);
                    if (autoSwitch) {
                        this.switchInstitutionalView('stock');
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
                scoreTextEl.innerHTML = `Accumulation Score: <strong style="color:#38bdf8;">${data.accumulation_score} / 100</strong> | Net Tracked Flow: <strong style="color:#34d399;">+₹${data.net_flow_cr} Cr</strong> | Funds In/Out: <strong style="color:#34d399;">+${data.funds_accumulating_count}</strong> / <strong style="color:#f87171;">-${data.funds_selling_count}</strong>`;
            }

            // 1. Shareholding pattern history
            const patContainer = document.getElementById('instShareholdingPatternContainer');
            if (patContainer) {
                const pats = data.shareholding_patterns || [];
                if (!pats.length) {
                    patContainer.innerHTML = '<div style="color:#64748b;font-size:0.72rem;">No historical shareholding filings found.</div>';
                } else {
                    patContainer.innerHTML = `
                        <table style="width:100%;font-size:0.72rem;text-align:left;border-collapse:collapse;">
                            <thead>
                                <tr style="color:#94a3b8;border-bottom:1px solid rgba(255,255,255,0.06);font-family:var(--font-mono);">
                                    <th style="padding:0.35rem 0.5rem;">QUARTER</th>
                                    <th style="padding:0.35rem 0.5rem;">PROMOTER</th>
                                    <th style="padding:0.35rem 0.5rem;">FII / FPI</th>
                                    <th style="padding:0.35rem 0.5rem;">DII / MUTUAL FUNDS</th>
                                    <th style="padding:0.35rem 0.5rem;">RETAIL / PUBLIC</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${pats.map(p => `
                                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                        <td style="padding:0.4rem 0.5rem;font-weight:700;color:#f8fafc;font-family:var(--font-mono);">${p.quarter}</td>
                                        <td style="padding:0.4rem 0.5rem;color:#cbd5e1;font-family:var(--font-mono);">${p.promoter_pct}%</td>
                                        <td style="padding:0.4rem 0.5rem;color:#38bdf8;font-weight:700;font-family:var(--font-mono);">${p.fii_pct}%</td>
                                        <td style="padding:0.4rem 0.5rem;color:#34d399;font-weight:700;font-family:var(--font-mono);">${p.dii_mf_pct}%</td>
                                        <td style="padding:0.4rem 0.5rem;color:#94a3b8;font-family:var(--font-mono);">${p.public_retail_pct}%</td>
                                    </tr>
                                `).join('')}
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

            // 3. Fund-by-Fund Table
            const tbody = document.getElementById('instStockHoldingsTableBody');
            if (tbody) {
                const holdings = data.holdings || [];
                if (!holdings.length) {
                    tbody.innerHTML = '<tr><td colspan="8" style="padding:2rem;text-align:center;color:#64748b;">No fund positions recorded for this ticker yet.</td></tr>';
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
                    const changeStr = h.change_pct > 0 ? `+${h.change_pct}%` : `${h.change_pct}%`;

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.6rem 0.8rem;font-weight:700;color:#f8fafc;">${h.fund_name}</td>
                            <td style="padding:0.6rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${h.fund_type}</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">${h.quarter}</td>
                            <td style="padding:0.6rem 0.8rem;">
                                <span class="signal-badge" style="background:${actBg};color:${actCol};font-size:0.68rem;padding:0.12rem 0.4rem;">${h.action}</span>
                            </td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${h.stake_pct}%</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${actCol};">${changeStr}</td>
                            <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;">₹${h.holding_value_cr} Cr</td>
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
                    const summary = holdings.map(h => `${h.ticker} (${h.stake_pct}% stake, Action: ${h.action})`).join('\n• ');
                    alert(`💼 Holdings for ${fundName}:\n\n• ${summary || 'No positions recorded.'}`);
                }
            } catch (e) {
                console.error('Error fetching fund portfolio:', e);
            }
        }
    };

    // Export module
    window.InstitutionalModule = institutionalModule;
    if (window.app) {
        Object.assign(window.app, institutionalModule);
    }
})();
