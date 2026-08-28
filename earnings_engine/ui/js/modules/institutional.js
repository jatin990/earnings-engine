// =========================================================================
// institutional — Nexus Dashboard Module (Institutional Accumulation & Funds)
// Extracted from dashboard.js — modularization 2026-08-28
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
            institutionalData: {
                accumulating: [],
                distributing: [],
                funds: [],
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
                    const badgeBg = it.verdict_badge === 'emerald' ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                    const badgeCol = it.verdict_badge === 'emerald' ? '#34d399' : '#60a5fa';
                    const fundsInStr = `<span style="color:#34d399;font-weight:700;">+${it.funds_accumulating_count} in</span> / <span style="color:#f87171;">-${it.funds_selling_count} out</span>`;
                    const topFundsStr = it.top_funds && it.top_funds.length ? it.top_funds.join(', ') : '—';

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">
                                <span style="color:#38bdf8;">${it.ticker}</span>
                            </td>
                            <td style="padding:0.65rem 0.8rem;color:#cbd5e1;">${it.company_name}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">${it.accumulation_score} / 100</td>
                            <td style="padding:0.65rem 0.8rem;">
                                <span class="signal-badge" style="background:${badgeBg};color:${badgeCol};font-size:0.68rem;padding:0.15rem 0.45rem;">${it.verdict}</span>
                            </td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-size:0.74rem;">${fundsInStr}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f8fafc;">${it.total_institutional_stake}%</td>
                            <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${topFundsStr}">
                                ${topFundsStr}
                            </td>
                            <td style="padding:0.65rem 0.8rem;text-align:center;">
                                <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">Inspect</button>
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
                    tbody.innerHTML = '<tr><td colspan="6" style="padding:2rem;text-align:center;color:#64748b;">No high-distribution equities detected.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(it => {
                    const exitingStr = it.exiting_funds && it.exiting_funds.length ? it.exiting_funds.join(', ') : '—';
                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f87171;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">${it.ticker}</td>
                            <td style="padding:0.65rem 0.8rem;color:#cbd5e1;">${it.company_name}</td>
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
                const tbody = document.getElementById('instFundsTableBody') || document.getElementById('instInvestorsDirectoryTableBody');
                const countBadge = document.getElementById('instFundsCountBadge');
                if (countBadge) {
                    countBadge.innerText = `Showing ${funds ? funds.length : 0} funds & whales`;
                }
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
                    scoreTextEl.innerHTML = `Accumulation Score: <strong style="color:#38bdf8;">${data.accumulation_score} / 100</strong> | Net Tracked Flow: <strong style="color:#34d399;">+₹${data.net_flow_cr} Cr</strong> | Funds In/Out (QoQ): <strong style="color:#34d399;">+${data.funds_accumulating_count}</strong> / <strong style="color:#f87171;">-${data.funds_selling_count}</strong>`;
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

                // 3. Fund-by-Fund Table
                const tbody = document.getElementById('instStockHoldingsTableBody');
                if (tbody) {
                    const holdings = data.holdings || [];
                    if (!holdings.length) {
                        tbody.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#64748b;">No fund positions recorded for this ticker yet.</td></tr>';
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
                                <td style="padding:0.6rem 0.8rem;">
                                    <span class="signal-badge" style="background:${actBg};color:${actCol};font-size:0.68rem;padding:0.12rem 0.4rem;">${h.action}</span>
                                </td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${h.stake_pct}%</td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;font-weight:600;">₹${h.avg_price != null ? Number(h.avg_price).toFixed(2) : '—'}</td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#a7f3d0;font-weight:600;">₹${h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : '—'}</td>
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
        });

})(); // end institutional IIFE