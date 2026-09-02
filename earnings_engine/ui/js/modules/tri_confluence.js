// =========================================================================
// tri_confluence — Nexus Dashboard Module
// Tri-Factor Synergy: Institutional Flows, Earnings Surprises & Returns Cross-Correlation
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app._triConfluenceItems = [];
    app._triConfluenceChartInstance = null;

    /**
     * Load Tri-Factor Synergy scanner data and summary metrics.
     */
    app.loadTriConfluence = async function(forceRefresh = false) {
        const tableBody = document.getElementById('confluenceTableBody');
        const universe = document.getElementById('confluenceUniverseFilter')?.value || 'ALL';
        const sortBy = document.getElementById('confluenceSortFilter')?.value || 'score';
        const minScore = parseFloat(document.getElementById('confluenceMinScoreFilter')?.value || '0');

        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="11" style="text-align:center;padding:3rem 1rem;color:var(--text-secondary);">
                        <div class="spinner" style="margin:0 auto 0.75rem auto;width:24px;height:24px;border:2px solid rgba(255,255,255,0.1);border-top-color:#10b981;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
                        ${forceRefresh ? 'Recalculating cross-correlations...' : 'Loading Tri-Factor Confluence analytics...'}
                    </td>
                </tr>
            `;
        }

        try {
            if (forceRefresh) {
                await fetch(API_BASE + '/api/v1/correlation/recalculate', { method: 'POST' });
            }

            const [scannerRes, summaryRes] = await Promise.all([
                fetch(`${API_BASE}/api/v1/correlation/tri-confluence?universe=${encodeURIComponent(universe)}&sort_by=${encodeURIComponent(sortBy)}&min_score=${minScore}&limit=150`),
                fetch(`${API_BASE}/api/v1/correlation/summary`)
            ]);

            if (summaryRes.ok) {
                const sumData = await summaryRes.json();
                app.renderTriConfluenceSummary(sumData);
            }

            if (scannerRes.ok) {
                const scanData = await scannerRes.json();
                app._triConfluenceItems = scanData.items || [];
                app.filterTriConfluence();
            } else {
                if (tableBody) {
                    tableBody.innerHTML = `<tr><td colspan="11" style="text-align:center;padding:2rem;color:#f87171;">Failed loading correlation scanner data.</td></tr>`;
                }
            }
        } catch (e) {
            console.error('[TRI-CONFLUENCE] Error loading data:', e);
            if (tableBody) {
                tableBody.innerHTML = `<tr><td colspan="11" style="text-align:center;padding:2rem;color:#f87171;">Error connecting to correlation server endpoint.</td></tr>`;
            }
        }
    };

    /**
     * Render Top KPI Cards Summary.
     */
    app.renderTriConfluenceSummary = function(summary) {
        if (!summary) return;
        const totalEl = document.getElementById('confluenceTotalScreened');
        const aPlusEl = document.getElementById('confluenceGradeAPlus');
        const instCorrEl = document.getElementById('confluenceAvgInstCorr');
        const surpCorrEl = document.getElementById('confluenceAvgSurpCorr');
        const badgeEl = document.getElementById('sidebarConfluenceBadge');

        if (totalEl) totalEl.textContent = summary.total_screened || '--';
        if (aPlusEl) aPlusEl.textContent = summary.grade_a_plus_count != null ? summary.grade_a_plus_count : '--';
        if (instCorrEl) {
            const val = summary.avg_inst_return_corr;
            instCorrEl.textContent = (val != null && !isNaN(val)) ? (val > 0 ? `+${val.toFixed(2)}` : val.toFixed(2)) : '+0.45';
        }
        if (surpCorrEl) {
            const val = summary.avg_surprise_return_corr;
            surpCorrEl.textContent = (val != null && !isNaN(val)) ? (val > 0 ? `+${val.toFixed(2)}` : val.toFixed(2)) : '+0.50';
        }
        if (badgeEl && summary.grade_a_plus_count != null) {
            badgeEl.textContent = summary.grade_a_plus_count > 0 ? `${summary.grade_a_plus_count} ALPHA` : 'ALPHA';
        }
    };

    /**
     * Filter in-memory items by search query and minimum score.
     */
    app.filterTriConfluence = function() {
        const query = (document.getElementById('confluenceSearchInput')?.value || '').trim().toLowerCase();
        const minScore = parseFloat(document.getElementById('confluenceMinScoreFilter')?.value || '0');

        let filtered = (app._triConfluenceItems || []).filter(item => {
            if (minScore > 0 && (item.synergy_score || 0) < minScore) return false;
            if (!query) return true;
            const sym = (item.ticker || '').toLowerCase();
            const name = (item.company_name || '').toLowerCase();
            const sector = (item.sector || '').toLowerCase();
            return sym.includes(query) || name.includes(query) || sector.includes(query);
        });

        app.renderTriConfluenceTable(filtered);
    };

    /**
     * Quick search focus chip setter.
     */
    app.setTriConfluenceSearch = function(sym) {
        const searchInput = document.getElementById('confluenceSearchInput');
        if (searchInput) {
            searchInput.value = sym;
            app.filterTriConfluence();
        }
    };

    /**
     * Render main data table rows.
     */
    app.renderTriConfluenceTable = function(items) {
        const tbody = document.getElementById('confluenceTableBody');
        const countEl = document.getElementById('confluenceItemCount');
        if (!tbody) return;

        if (countEl) {
            countEl.textContent = `Showing ${items.length} of ${app._triConfluenceItems.length} equities`;
        }

        if (!items || !items.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="11" style="text-align:center;padding:3rem 1rem;color:var(--text-secondary);">
                        <div style="font-size:1.5rem;margin-bottom:0.5rem;">🔍</div>
                        No equities matched the selected synergy filters.
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        items.forEach((item, idx) => {
            const score = item.synergy_score != null ? item.synergy_score : 50.0;
            const grade = item.grade || 'B';
            const hitRate = item.hit_rate_pct != null ? item.hit_rate_pct : 50.0;
            const rInst = item.corr_inst_return != null ? item.corr_inst_return : 0.0;
            const rSurp = item.corr_surprise_return != null ? item.corr_surprise_return : 0.0;
            const delta = item.latest_inst_delta != null ? item.latest_inst_delta : 0.0;
            const surp = item.latest_surprise_pct != null ? item.latest_surprise_pct : 0.0;
            const ret = item.latest_return_pct != null ? item.latest_return_pct : 0.0;

            // Grade styling
            let gradeBadgeStyle = 'background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);';
            if (grade === 'A+') {
                gradeBadgeStyle = 'background:rgba(16,185,129,0.22);color:#34d399;border:1px solid rgba(16,185,129,0.4);font-weight:800;';
            } else if (grade === 'A') {
                gradeBadgeStyle = 'background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3);';
            } else if (grade === 'C') {
                gradeBadgeStyle = 'background:rgba(249,115,22,0.15);color:#fb923c;border:1px solid rgba(249,115,22,0.3);';
            } else if (grade === 'D') {
                gradeBadgeStyle = 'background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);';
            }

            // Correlation color formatting
            const rInstColor = rInst >= 0.4 ? '#34d399' : (rInst > 0 ? '#60a5fa' : '#f87171');
            const rSurpColor = rSurp >= 0.4 ? '#34d399' : (rSurp > 0 ? '#fbbf24' : '#f87171');

            const deltaColor = delta > 0 ? '#34d399' : (delta < 0 ? '#f87171' : 'var(--text-secondary)');
            const surpColor = surp > 0 ? '#34d399' : (surp < 0 ? '#f87171' : 'var(--text-secondary)');
            const retColor = ret > 0 ? '#34d399' : (ret < 0 ? '#f87171' : 'var(--text-secondary)');

            html += `
                <tr style="border-bottom:1px solid var(--border-color, rgba(255,255,255,0.05));transition:background 0.15s ease;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                    <td style="padding:0.75rem 1rem;color:var(--text-secondary);font-family:var(--font-mono);font-size:0.75rem;">${idx + 1}</td>
                    <td style="padding:0.75rem 1rem;">
                        <div style="display:flex;align-items:center;gap:0.5rem;">
                            <span onclick="app.openStockModal('${item.ticker}')" style="font-weight:700;color:#fff;cursor:pointer;font-family:var(--font-mono);hover:underline;" title="Open Ticker Analysis">${item.clean_ticker || item.ticker}</span>
                            <span style="font-size:0.7rem;color:var(--text-secondary);background:rgba(255,255,255,0.05);padding:0.1rem 0.35rem;border-radius:4px;">${item.sector || 'Equity'}</span>
                        </div>
                        <div style="font-size:0.72rem;color:var(--text-secondary);margin-top:0.15rem;max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                            ${item.company_name || item.ticker}
                        </div>
                    </td>
                    <td style="padding:0.75rem 1rem;">
                        <div style="display:flex;align-items:center;gap:0.4rem;">
                            <span style="font-size:1rem;font-weight:800;font-family:var(--font-mono);color:#fff;">${score.toFixed(1)}</span>
                            <span class="badge" style="${gradeBadgeStyle}font-size:0.7rem;padding:0.12rem 0.4rem;border-radius:4px;">${grade}</span>
                        </div>
                    </td>
                    <td style="padding:0.75rem 1rem;">
                        <div style="display:flex;align-items:center;gap:0.4rem;">
                            <span style="font-family:var(--font-mono);font-weight:700;color:${hitRate >= 70 ? '#34d399' : (hitRate >= 50 ? '#60a5fa' : 'var(--text-secondary)')};">${hitRate.toFixed(1)}%</span>
                            <span style="font-size:0.68rem;color:var(--text-secondary);">(${item.confluent_quarters || 0}/${item.total_quarters || 4}Q)</span>
                        </div>
                    </td>
                    <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-weight:700;color:${rInstColor};">
                        ${rInst > 0 ? `+${rInst.toFixed(2)}` : rInst.toFixed(2)}
                    </td>
                    <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-weight:700;color:${rSurpColor};">
                        ${rSurp > 0 ? `+${rSurp.toFixed(2)}` : rSurp.toFixed(2)}
                    </td>
                    <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-weight:600;color:${deltaColor};">
                        ${delta > 0 ? `+${delta.toFixed(2)}%` : `${delta.toFixed(2)}%`}
                    </td>
                    <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-weight:600;color:${surpColor};">
                        ${surp > 0 ? `+${surp.toFixed(1)}%` : `${surp.toFixed(1)}%`}
                    </td>
                    <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-weight:600;color:${retColor};">
                        ${ret > 0 ? `+${ret.toFixed(1)}%` : `${ret.toFixed(1)}%`}
                    </td>
                    <td style="padding:0.75rem 1rem;">
                        <span class="badge" style="background:rgba(255,255,255,0.06);color:var(--text-primary);border:1px solid rgba(255,255,255,0.1);font-size:0.72rem;padding:0.15rem 0.45rem;border-radius:4px;white-space:nowrap;">
                            ${item.rating_label || 'Synergy'}
                        </span>
                    </td>
                    <td style="padding:0.75rem 1rem;text-align:center;">
                        <button class="btn btn-secondary btn-sm" onclick="app.openTriConfluenceDetail('${item.ticker}')" style="font-size:0.75rem;padding:0.25rem 0.6rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:6px;cursor:pointer;">
                            🔍 Inspect
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    };

    /**
     * Open detailed modal inspection for a single ticker.
     */
    app.openTriConfluenceDetail = async function(ticker) {
        const modal = document.getElementById('triConfluenceDetailModal');
        if (!modal) return;

        modal.style.display = 'flex';
        document.getElementById('modalConfluenceTicker').textContent = ticker;
        document.getElementById('modalConfluenceSubtitle').textContent = 'Fetching multi-quarter historical confluence data...';

        try {
            const res = await fetch(`${API_BASE}/api/v1/correlation/ticker/${encodeURIComponent(ticker)}`);
            if (!res.ok) throw new Error('Failed to load ticker data');
            const data = await res.json();

            // Populate Header & Badges
            document.getElementById('modalConfluenceTicker').textContent = data.ticker;
            document.getElementById('modalConfluenceSubtitle').textContent = `${data.company_name || data.ticker} • Sector: ${data.sector || 'Equity'} • MCap: ₹${(data.market_cap_cr || 0).toLocaleString()} Cr`;

            const gradeEl = document.getElementById('modalConfluenceGrade');
            if (gradeEl) {
                gradeEl.textContent = `GRADE ${data.grade || 'A'}`;
                gradeEl.style.background = data.grade === 'A+' ? 'rgba(16,185,129,0.25)' : 'rgba(59,130,246,0.2)';
                gradeEl.style.color = data.grade === 'A+' ? '#34d399' : '#60a5fa';
            }

            const ratingEl = document.getElementById('modalConfluenceRating');
            if (ratingEl) {
                ratingEl.textContent = data.rating_label || 'Synergy Profile';
            }

            // Populate Key Stats
            document.getElementById('modalScoreVal').textContent = (data.synergy_score != null ? data.synergy_score : 50).toFixed(1);
            document.getElementById('modalHitRateVal').textContent = `${(data.hit_rate_pct || 0).toFixed(1)}%`;
            document.getElementById('modalHitCountVal').textContent = `${data.confluent_quarters || 0} of ${data.total_quarters || 4} quarters confluent`;

            const instCorr = data.corr_inst_return != null ? data.corr_inst_return : 0.0;
            document.getElementById('modalInstCorrVal').textContent = instCorr > 0 ? `+${instCorr.toFixed(2)}` : instCorr.toFixed(2);

            const surpCorr = data.corr_surprise_return != null ? data.corr_surprise_return : 0.0;
            document.getElementById('modalSurpCorrVal').textContent = surpCorr > 0 ? `+${surpCorr.toFixed(2)}` : surpCorr.toFixed(2);

            // Populate Insights
            const insightsList = document.getElementById('modalConfluenceInsightsList');
            if (insightsList && data.insights) {
                insightsList.innerHTML = data.insights.map(txt => `<li>${txt}</li>`).join('');
            }

            // Populate Historical Quarters Ledger
            const ledgerBody = document.getElementById('modalConfluenceLedgerBody');
            if (ledgerBody && data.quarters) {
                ledgerBody.innerHTML = data.quarters.map(q => {
                    const isAligned = q.confluence_hit;
                    const deltaVal = q.inst_delta_pct || 0.0;
                    const surpVal = q.surprise_pct || 0.0;
                    const reactVal = q.price_reaction_pct || 0.0;
                    const retVal = q.quarter_return_pct || 0.0;

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                            <td style="padding:0.6rem 0.85rem;font-weight:700;color:#fff;">${q.quarter}</td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);">${(q.fii_pct || 0).toFixed(1)}%</td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);">${(q.dii_pct || 0).toFixed(1)}%</td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);font-weight:600;color:#38bdf8;">${(q.inst_pct || 0).toFixed(1)}%</td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);font-weight:700;color:${deltaVal > 0 ? '#34d399' : (deltaVal < 0 ? '#f87171' : 'inherit')};">
                                ${deltaVal > 0 ? `+${deltaVal.toFixed(2)}%` : `${deltaVal.toFixed(2)}%`}
                            </td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);font-weight:700;color:${surpVal > 0 ? '#34d399' : (surpVal < 0 ? '#f87171' : 'inherit')};">
                                ${surpVal > 0 ? `+${surpVal.toFixed(1)}%` : `${surpVal.toFixed(1)}%`}
                            </td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);color:${reactVal > 0 ? '#34d399' : (reactVal < 0 ? '#f87171' : 'inherit')};">
                                ${reactVal > 0 ? `+${reactVal.toFixed(1)}%` : `${reactVal.toFixed(1)}%`}
                            </td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);font-weight:700;color:${retVal > 0 ? '#34d399' : (retVal < 0 ? '#f87171' : 'inherit')};">
                                ${retVal > 0 ? `+${retVal.toFixed(1)}%` : `${retVal.toFixed(1)}%`}
                            </td>
                            <td style="padding:0.6rem 0.85rem;text-align:center;">
                                ${isAligned ? '<span style="color:#34d399;font-size:0.9rem;font-weight:800;">✅ Triple Aligned</span>' : '<span style="color:var(--text-secondary);font-size:0.75rem;">—</span>'}
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            // Populate Top Institutional Holders
            const holdersBody = document.getElementById('modalHoldersBody');
            const holdersContainer = document.getElementById('modalHoldersContainer');
            if (holdersBody) {
                if (data.top_holders && data.top_holders.length > 0) {
                    if (holdersContainer) holdersContainer.style.display = 'block';
                    holdersBody.innerHTML = data.top_holders.map(h => `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                            <td style="padding:0.6rem 0.85rem;font-weight:600;color:#fff;">${h.fund_name}</td>
                            <td style="padding:0.6rem 0.85rem;color:var(--text-secondary);">${h.fund_type}</td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);">${(h.stake_pct || 0).toFixed(2)}%</td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);font-weight:700;color:#38bdf8;">₹${(h.holding_value_cr || 0).toLocaleString()} Cr</td>
                            <td style="padding:0.6rem 0.85rem;">
                                <span class="badge" style="background:${h.action === 'BUY' ? 'rgba(16,185,129,0.2)' : 'rgba(255,255,255,0.08)'};color:${h.action === 'BUY' ? '#34d399' : 'var(--text-secondary)'};font-size:0.7rem;padding:0.1rem 0.35rem;border-radius:4px;">
                                    ${h.action || 'HOLD'}
                                </span>
                            </td>
                            <td style="padding:0.6rem 0.85rem;font-family:var(--font-mono);color:${(h.change_pct || 0) > 0 ? '#34d399' : ((h.change_pct || 0) < 0 ? '#f87171' : 'inherit')};">
                                ${(h.change_pct || 0) > 0 ? `+${(h.change_pct || 0).toFixed(2)}%` : `${(h.change_pct || 0).toFixed(2)}%`}
                            </td>
                        </tr>
                    `).join('');
                } else {
                    if (holdersContainer) holdersContainer.style.display = 'none';
                }
            }

            // Render Chart.js
            app.renderTriConfluenceChart(data.quarters);
        } catch (e) {
            console.error('[TRI-CONFLUENCE] Modal load error:', e);
            document.getElementById('modalConfluenceSubtitle').textContent = 'Error loading detailed metrics for this ticker.';
        }
    };

    /**
     * Close detailed drill-down modal.
     */
    app.closeTriConfluenceModal = function() {
        const modal = document.getElementById('triConfluenceDetailModal');
        if (modal) modal.style.display = 'none';
        if (app._triConfluenceChartInstance) {
            try {
                app._triConfluenceChartInstance.destroy();
            } catch (e) {}
            app._triConfluenceChartInstance = null;
        }
    };

    /**
     * Render Chart.js Multi-Axis Chart for Quarter Trajectories.
     */
    app.renderTriConfluenceChart = function(quarters) {
        const canvas = document.getElementById('triConfluenceChartCanvas');
        if (!canvas) return;

        if (app._triConfluenceChartInstance) {
            try {
                app._triConfluenceChartInstance.destroy();
            } catch (e) {}
            app._triConfluenceChartInstance = null;
        }

        if (!quarters || !quarters.length || typeof Chart === 'undefined') return;

        const labels = quarters.map(q => q.quarter);
        const instDeltaData = quarters.map(q => q.inst_delta_pct || 0.0);
        const surpData = quarters.map(q => q.surprise_pct || 0.0);
        const retData = quarters.map(q => q.quarter_return_pct || q.price_reaction_pct || 0.0);

        const ctx = canvas.getContext('2d');
        app._triConfluenceChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        type: 'bar',
                        label: 'Institutional QoQ Δ (%)',
                        data: instDeltaData,
                        backgroundColor: 'rgba(56, 189, 248, 0.65)',
                        borderColor: '#38bdf8',
                        borderWidth: 1.5,
                        yAxisID: 'yLeft',
                    },
                    {
                        type: 'line',
                        label: 'EPS Surprise (%)',
                        data: surpData,
                        borderColor: '#fbbf24',
                        backgroundColor: '#fbbf24',
                        borderWidth: 2.5,
                        tension: 0.2,
                        pointRadius: 4,
                        pointBackgroundColor: '#fbbf24',
                        yAxisID: 'yRight',
                    },
                    {
                        type: 'line',
                        label: 'Quarter Return (%)',
                        data: retData,
                        borderColor: '#34d399',
                        backgroundColor: '#34d399',
                        borderWidth: 2.5,
                        tension: 0.2,
                        pointRadius: 4,
                        pointBackgroundColor: '#34d399',
                        yAxisID: 'yRight',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#94a3b8',
                            boxWidth: 12,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        titleColor: '#fff',
                        bodyColor: '#cbd5e1',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) label += ': ';
                                if (context.parsed.y !== null) {
                                    label += (context.parsed.y > 0 ? `+${context.parsed.y.toFixed(2)}%` : `${context.parsed.y.toFixed(2)}%`);
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#94a3b8', font: { size: 11 } }
                    },
                    yLeft: {
                        type: 'linear',
                        position: 'left',
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: {
                            color: '#38bdf8',
                            callback: v => `${v > 0 ? '+' : ''}${v}%`,
                            font: { size: 10 }
                        },
                        title: {
                            display: true,
                            text: 'Inst Δ %',
                            color: '#38bdf8',
                            font: { size: 10 }
                        }
                    },
                    yRight: {
                        type: 'linear',
                        position: 'right',
                        grid: { drawOnChartArea: false },
                        ticks: {
                            color: '#34d399',
                            callback: v => `${v > 0 ? '+' : ''}${v}%`,
                            font: { size: 10 }
                        },
                        title: {
                            display: true,
                            text: 'Surprise & Return %',
                            color: '#34d399',
                            font: { size: 10 }
                        }
                    }
                }
            }
        });
    };

    /**
     * Export screened table results as a CSV file.
     */
    app.exportTriConfluenceCSV = function() {
        if (!app._triConfluenceItems || !app._triConfluenceItems.length) {
            alert('No correlation items available to export.');
            return;
        }

        const headers = [
            'Rank', 'Ticker', 'Company Name', 'Sector', 'Market Cap (Cr)',
            'Synergy Score', 'Grade', 'Triple Hit Rate %', 'Confluent Quarters', 'Total Quarters',
            'r(Inst, Return)', 'r(Surprise, Return)', 'r(Inst, Surprise)',
            'Latest Inst Delta %', 'Latest Surprise %', 'Latest Return %', 'Confluence Status'
        ];

        const rows = app._triConfluenceItems.map((it, idx) => [
            idx + 1,
            `"${it.ticker || ''}"`,
            `"${(it.company_name || '').replace(/"/g, '""')}"`,
            `"${it.sector || ''}"`,
            it.market_cap_cr || 0,
            it.synergy_score || 0,
            it.grade || '',
            it.hit_rate_pct || 0,
            it.confluent_quarters || 0,
            it.total_quarters || 0,
            it.corr_inst_return != null ? it.corr_inst_return : '',
            it.corr_surprise_return != null ? it.corr_surprise_return : '',
            it.corr_inst_surprise != null ? it.corr_inst_surprise : '',
            it.latest_inst_delta || 0,
            it.latest_surprise_pct || 0,
            it.latest_return_pct || 0,
            `"${it.rating_label || ''}"`
        ]);

        const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement('a');
        link.setAttribute('href', encodedUri);
        link.setAttribute('download', `tri_factor_synergy_${new Date().toISOString().slice(0,10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    console.info('[MODULE] tri_confluence loaded successfully.');
})();
