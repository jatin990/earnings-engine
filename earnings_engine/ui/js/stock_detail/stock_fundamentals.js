/**
 * Nexus Intelligence Platform — Stock Fundamentals & Forensic Ledger
 * 12-Quarter Earnings Ledger, Scenario Calculator, Shareholding & Catalysts.
 */

(function () {
    'use strict';

    const State = window.StockDetailState;

    /**
     * Initialize Fundamentals, Shareholding & Earnings Ledger
     */
    window.initStockFundamentals = function () {
        loadStockEarnings();
        loadStockInstitutional();
        loadStockCatalysts();
    };

    /**
     * Load 12-Quarter Historical Earnings Table
     */
    async function loadStockEarnings() {
        const tbody = document.getElementById('stockEarningsTableBody');
        if (!tbody) return;

        try {
            const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/earnings`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (data && data.success && data.earnings && data.earnings.length > 0) {
                renderEarningsTable(data.earnings);
            } else {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#8e97a8; padding:1.5rem;">No historical quarterly earnings data on record.</td></tr>';
            }
        } catch (e) {
            console.debug('Error loading stock earnings:', e);
        }
    }

    /**
     * Render Earnings Table Rows
     */
    function renderEarningsTable(earnings) {
        const tbody = document.getElementById('stockEarningsTableBody');
        if (!tbody) return;

        let html = '';
        earnings.forEach((q) => {
            const surprise = q.eps_surprise_pct !== undefined && q.eps_surprise_pct !== null ? q.eps_surprise_pct : null;
            const reaction = q.reaction_1d_pct !== undefined && q.reaction_1d_pct !== null ? q.reaction_1d_pct : null;
            const surpriseClass = surprise !== null ? (surprise >= 0 ? '#34d399' : '#fb7185') : '#8e97a8';
            const reactionClass = reaction !== null ? (reaction >= 0 ? '#34d399' : '#fb7185') : '#8e97a8';

            html += `
                <tr>
                    <td style="font-weight:600; color:#ffffff;">${q.quarter || q.period || '—'}</td>
                    <td>${q.report_date || '—'}</td>
                    <td>${q.reported_eps !== null && q.reported_eps !== undefined ? `₹${Number(q.reported_eps).toFixed(2)}` : '—'}</td>
                    <td>${q.estimated_eps !== null && q.estimated_eps !== undefined ? `₹${Number(q.estimated_eps).toFixed(2)}` : '—'}</td>
                    <td style="color:${surpriseClass}; font-weight:700;">${surprise !== null ? window.formatPercent(surprise) : '—'}</td>
                    <td style="color:${reactionClass}; font-weight:700;">${reaction !== null ? window.formatPercent(reaction) : '—'}</td>
                    <td>${q.reaction_1w_pct !== undefined && q.reaction_1w_pct !== null ? window.formatPercent(q.reaction_1w_pct) : '—'}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    }

    /**
     * Open Scenario / EPS Calculator Modal
     */
    window.openEpsCalculatorModal = function () {
        const modal = document.getElementById('stockEpsCalcModal');
        if (modal) modal.classList.add('active');
    };

    window.closeEpsCalculatorModal = function () {
        const modal = document.getElementById('stockEpsCalcModal');
        if (modal) modal.classList.remove('active');
    };

    /**
     * Run Scenario Calculation
     */
    window.runEpsScenarioCalculation = async function () {
        const epsInput = document.getElementById('calcReportedEps');
        const estInput = document.getElementById('calcEstimatedEps');
        const resBox = document.getElementById('calcResultBox');
        if (!epsInput || !estInput || !resBox) return;

        const reported = parseFloat(epsInput.value);
        const estimated = parseFloat(estInput.value);

        if (isNaN(reported) || isNaN(estimated)) {
            window.showStockToast('Please enter valid numeric EPS values', 'error');
            return;
        }

        resBox.innerHTML = '<div style="color:#38bdf8;"><span class="stock-spinner" style="width:14px;height:14px;border-width:2px;"></span> Running LightGBM Reaction Inference...</div>';

        try {
            const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/calculate-eps`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker: State.ticker,
                    reported_eps: reported,
                    estimated_eps: estimated,
                }),
            });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            if (data && data.success) {
                const prob = data.reaction_prob !== undefined ? (data.reaction_prob * 100).toFixed(1) : '—';
                const predMove = data.predicted_move !== undefined ? window.formatPercent(data.predicted_move) : '—';
                const isBull = data.reaction_prob >= 0.5;

                resBox.innerHTML = `
                    <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); border-radius:6px; padding:0.75rem; font-family:var(--font-mono); font-size:0.82rem;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
                            <span style="color:#8e97a8;">Model Stance:</span>
                            <span style="color:${isBull ? '#34d399' : '#fb7185'}; font-weight:700;">${isBull ? 'BULLISH' : 'BEARISH'}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
                            <span style="color:#8e97a8;">Up-Move Probability:</span>
                            <span style="color:#ffffff; font-weight:700;">${prob}%</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:#8e97a8;">Predicted 1-Day Reaction:</span>
                            <span style="color:${isBull ? '#34d399' : '#fb7185'}; font-weight:700;">${predMove}</span>
                        </div>
                    </div>
                `;
            }
        } catch (err) {
            resBox.innerHTML = `<div style="color:#fb7185;">Calculation failed: ${err.message}</div>`;
        }
    };

    /**
     * Load Shareholding Pattern & Institutional Flows
     */
    async function loadStockInstitutional() {
        const promEl = document.getElementById('instPromoterPct');
        const fiiEl = document.getElementById('instFiiPct');
        const diiEl = document.getElementById('instDiiPct');
        const pubEl = document.getElementById('instPublicPct');
        if (!promEl) return;

        try {
            const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/institutional`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (data && data.success && data.shareholding) {
                const sh = data.shareholding;
                window.setElText('instPromoterPct', `${(sh.promoters || 0).toFixed(1)}%`);
                window.setElText('instFiiPct', `${(sh.fii || 0).toFixed(1)}%`);
                window.setElText('instDiiPct', `${(sh.dii || 0).toFixed(1)}%`);
                window.setElText('instPublicPct', `${(sh.public || 0).toFixed(1)}%`);
            }
        } catch (e) {
            console.debug('Error loading institutional data:', e);
        }
    }

    /**
     * Load News Catalysts & Sentiment Feed
     */
    async function loadStockCatalysts() {
        const container = document.getElementById('stockCatalystsFeed');
        if (!container) return;

        try {
            const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/catalysts`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (data && data.success && data.catalysts && data.catalysts.length > 0) {
                let html = '';
                data.catalysts.slice(0, 5).forEach((c) => {
                    const sentiment = (c.sentiment || 'NEUTRAL').toUpperCase();
                    const tagColor = sentiment === 'POSITIVE' ? '#34d399' : sentiment === 'NEGATIVE' ? '#fb7185' : '#8e97a8';

                    html += `
                        <div style="background:var(--bg-well); border:1px solid var(--border-subtle); border-radius:6px; padding:0.75rem; display:flex; flex-direction:column; gap:0.35rem;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:0.7rem; color:#8e97a8; font-family:var(--font-mono);">${c.published_at || 'Recent'}</span>
                                <span style="font-size:0.68rem; font-weight:700; color:${tagColor}; border:1px solid ${tagColor}; border-radius:3px; padding:1px 4px;">${sentiment}</span>
                            </div>
                            <div style="font-size:0.82rem; font-weight:500; color:#ffffff;">${c.headline || c.title}</div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } else {
                container.innerHTML = '<div style="color:#8e97a8; font-size:0.8rem; padding:0.5rem 0;">No major news catalysts detected in the past 30 days.</div>';
            }
        } catch (e) {
            console.debug('Error loading catalysts:', e);
        }
    }
})();
