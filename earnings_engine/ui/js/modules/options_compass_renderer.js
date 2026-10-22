/**
 * options_compass_renderer.js - Institutional F&O Confluence & Market Compass Renderer
 * Modular frontend controller for:
 * 1. Multi-Timeframe Call vs Put Open Interest Velocity Meters
 * 2. Market Compass Confluence SVG Speedometer & 8-Factor Breakdown
 * 3. Dual Strike Distribution Charts (Total OI vs Intraday OI Change)
 * 4. Algorithmic Real-Time Institutional Alerts Feed
 */

(function () {
    'use strict';

    window.app = window.app || {};
    const app = window.app;

    // Chart instances cache
    let dualOiChartInstance = null;
    let dualOiChgChartInstance = null;

    /**
     * Render Multi-Timeframe Call vs Put OI Meters (Today, 15m, 5m)
     */
    app.renderOiTimeframeMeters = function (timeframesData, pcrOi) {
        if (!timeframesData) return;

        // 1. Overall Flow Sentiment Header Badge
        const flowBadge = document.getElementById('optFlowSentimentBadge');
        const pcrVal = document.getElementById('optFlowPcrVal');
        const pcrBias = document.getElementById('optFlowPcrBias');

        const todaySentiment = timeframesData.today?.sentiment || 'NEUTRAL';
        if (flowBadge) {
            flowBadge.textContent = todaySentiment;
            if (todaySentiment.includes('PUT WRITING') || todaySentiment.includes('SHORT COVERING')) {
                flowBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                flowBadge.style.color = '#34d399';
                flowBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
            } else if (todaySentiment.includes('CALL WRITING') || todaySentiment.includes('LONG UNWINDING')) {
                flowBadge.style.background = 'rgba(239, 68, 68, 0.15)';
                flowBadge.style.color = '#f87171';
                flowBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            } else {
                flowBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                flowBadge.style.color = '#fbbf24';
                flowBadge.style.borderColor = 'rgba(245, 158, 11, 0.3)';
            }
        }

        if (pcrVal && pcrOi !== undefined) {
            pcrVal.textContent = Number(pcrOi).toFixed(2);
        }

        if (pcrBias && pcrOi !== undefined) {
            if (pcrOi >= 1.2) {
                pcrBias.textContent = 'Bullish Support Dominated';
                pcrBias.style.color = '#34d399';
            } else if (pcrOi <= 0.75) {
                pcrBias.textContent = 'Bearish Resistance Dominated';
                pcrBias.style.color = '#f87171';
            } else {
                pcrBias.textContent = 'Balanced Equilibrium';
                pcrBias.style.color = '#fbbf24';
            }
        }

        // Helper to format number in Indian Lakhs/Crores
        const fmtOi = (num) => {
            const n = Math.abs(num || 0);
            const sign = (num || 0) >= 0 ? '+' : '-';
            if (n >= 10000000) return `${sign}${(n / 10000000).toFixed(2)}Cr`;
            if (n >= 100000) return `${sign}${(n / 100000).toFixed(1)}L`;
            if (n >= 1000) return `${sign}${(n / 1000).toFixed(0)}k`;
            return `${sign}${n}`;
        };

        // 2. Card 1: Today
        const td = timeframesData.today;
        if (td) {
            const badge = document.getElementById('optTfTodayBadge');
            const callBar = document.getElementById('optTfTodayCallBar');
            const putBar = document.getElementById('optTfTodayPutBar');
            const callPct = document.getElementById('optTfTodayCallPct');
            const putPct = document.getElementById('optTfTodayPutPct');
            const callChg = document.getElementById('optTfTodayCallChg');
            const putChg = document.getElementById('optTfTodayPutChg');

            if (badge) badge.textContent = td.sentiment || 'NEUTRAL';
            if (callBar) callBar.style.width = `${td.call_pct || 50}%`;
            if (putBar) putBar.style.width = `${td.put_pct || 50}%`;
            if (callPct) callPct.textContent = `${td.call_pct || 50}%`;
            if (putPct) putPct.textContent = `${td.put_pct || 50}%`;
            if (callChg) callChg.textContent = fmtOi(td.call_chg);
            if (putChg) putChg.textContent = fmtOi(td.put_chg);
        }

        // 3. Card 2: 15m Velocity
        const m15 = timeframesData.tf_15m;
        if (m15) {
            const badge = document.getElementById('optTf15mBadge');
            const callBar = document.getElementById('optTf15mCallBar');
            const putBar = document.getElementById('optTf15mPutBar');
            const callPct = document.getElementById('optTf15mCallPct');
            const putPct = document.getElementById('optTf15mPutPct');
            const callChg = document.getElementById('optTf15mCallChg');
            const putChg = document.getElementById('optTf15mPutChg');

            if (badge) badge.textContent = m15.sentiment || 'NEUTRAL';
            if (callBar) callBar.style.width = `${m15.call_pct || 50}%`;
            if (putBar) putBar.style.width = `${m15.put_pct || 50}%`;
            if (callPct) callPct.textContent = `${m15.call_pct || 50}%`;
            if (putPct) putPct.textContent = `${m15.put_pct || 50}%`;
            if (callChg) callChg.textContent = fmtOi(m15.call_chg);
            if (putChg) putChg.textContent = fmtOi(m15.put_chg);
        }

        // 4. Card 3: 5m Burst
        const m5 = timeframesData.tf_5m;
        if (m5) {
            const badge = document.getElementById('optTf5mBadge');
            const callBar = document.getElementById('optTf5mCallBar');
            const putBar = document.getElementById('optTf5mPutBar');
            const callPct = document.getElementById('optTf5mCallPct');
            const putPct = document.getElementById('optTf5mPutPct');
            const callChg = document.getElementById('optTf5mCallChg');
            const putChg = document.getElementById('optTf5mPutChg');

            if (badge) badge.textContent = m5.sentiment || 'NEUTRAL';
            if (callBar) callBar.style.width = `${m5.call_pct || 50}%`;
            if (putBar) putBar.style.width = `${m5.put_pct || 50}%`;
            if (callPct) callPct.textContent = `${m5.call_pct || 50}%`;
            if (putPct) putPct.textContent = `${m5.put_pct || 50}%`;
            if (callChg) callChg.textContent = fmtOi(m5.call_chg);
            if (putChg) putChg.textContent = fmtOi(m5.put_chg);
        }
    };

    /**
     * Render Market Compass Speedometer and 8-Factor Breakdown
     */
    app.renderMarketCompass = function (compassData) {
        if (!compassData) return;

        const score = typeof compassData.score === 'number' ? compassData.score : 0;
        const confidence = compassData.confidence_pct || 75;
        const sentiment = compassData.sentiment || 'NEUTRAL';
        const verdict = compassData.verdict || 'Neutral Consolidation';
        const factors = compassData.factors || [];

        // 1. Verdict & Confidence Badges
        const verdictBadge = document.getElementById('optCompassVerdictBadge');
        const confPill = document.getElementById('optCompassConfidencePill');
        const scoreVal = document.getElementById('optCompassScoreVal');
        const verdictText = document.getElementById('optCompassVerdictText');
        const needleGroup = document.getElementById('optCompassNeedleGroup');

        if (verdictBadge) {
            verdictBadge.textContent = sentiment + ' CONFLUENCE';
            if (score > 15) {
                verdictBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                verdictBadge.style.color = '#34d399';
                verdictBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
            } else if (score < -15) {
                verdictBadge.style.background = 'rgba(239, 68, 68, 0.15)';
                verdictBadge.style.color = '#f87171';
                verdictBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            } else {
                verdictBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                verdictBadge.style.color = '#fbbf24';
                verdictBadge.style.borderColor = 'rgba(245, 158, 11, 0.3)';
            }
        }

        if (confPill) {
            confPill.textContent = `${confidence}% Confidence`;
        }

        if (scoreVal) {
            const sign = score > 0 ? '+' : '';
            scoreVal.textContent = `${sign}${score.toFixed(1)}`;
            scoreVal.style.color = score > 15 ? '#34d399' : (score < -15 ? '#f87171' : '#fbbf24');
        }

        if (verdictText) {
            verdictText.textContent = verdict;
        }

        // 2. Needle Angle Transform (-90 deg to +90 deg)
        // Score: -100 => -90 deg, 0 => 0 deg, +100 => +90 deg
        if (needleGroup) {
            const clampedScore = Math.max(-100, Math.min(100, score));
            const angle = -90 + ((clampedScore + 100) / 200) * 180;
            needleGroup.setAttribute('transform', `rotate(${angle.toFixed(1)} 100 100)`);
        }

        // 3. Render 8 Factors Breakdown Deck
        app.renderFactorBreakdown(factors);
    };

    /**
     * Render the 8-Factor Confluence Deck
     */
    app.renderFactorBreakdown = function (factors) {
        const container = document.getElementById('optCompassFactorsContainer');
        if (!container) return;

        if (!factors || factors.length === 0) {
            container.innerHTML = '<div style="color:var(--text-secondary);font-size:0.75rem;">No factor breakdown data available.</div>';
            return;
        }

        let html = '';
        for (const factor of factors) {
            const weight = factor.weight || 0;
            const factorScore = factor.score !== undefined ? factor.score : 0;
            const bias = factor.bias || 'NEUTRAL';
            const detail = factor.detail || '';

            // Color coding based on bias
            let biasColor = '#fbbf24';
            let barBg = '#fbbf24';
            if (bias === 'BULLISH') {
                biasColor = '#34d399';
                barBg = '#10b981';
            } else if (bias === 'BEARISH') {
                biasColor = '#f87171';
                barBg = '#ef4444';
            }

            // Normalise score from [-100, 100] to [0, 100]% bar fill
            const fillPct = Math.max(0, Math.min(100, ((factorScore + 100) / 2)));

            html += `
            <div style="background:#0d0e12;border:1px solid rgba(255,255,255,0.05);border-radius:6px;padding:0.45rem 0.65rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
                    <span style="font-size:0.72rem;font-weight:700;color:var(--text-primary);display:flex;align-items:center;gap:0.3rem;">
                        ${factor.name}
                        <span style="font-size:0.62rem;color:var(--text-secondary);font-family:var(--font-mono);font-weight:400;">(${weight}%)</span>
                    </span>
                    <span style="font-size:0.68rem;font-weight:800;color:${biasColor};font-family:var(--font-mono);">
                        ${bias} (${factorScore > 0 ? '+' : ''}${Math.round(factorScore)})
                    </span>
                </div>
                <div style="display:flex;height:4px;border-radius:2px;overflow:hidden;background:rgba(255,255,255,0.06);margin-bottom:0.3rem;">
                    <div style="width:${fillPct}%;background:${barBg};transition:width 0.4s ease;"></div>
                </div>
                <div style="font-size:0.68rem;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                    ${detail}
                </div>
            </div>`;
        }

        container.innerHTML = html;
    };

    /**
     * Render Real-Time Institutional Alerts Feed
     */
    app.renderDerivativesAlerts = function (alerts) {
        const container = document.getElementById('optDerivativesAlertsList');
        if (!container) return;

        if (!alerts || alerts.length === 0) {
            container.innerHTML = `
                <div style="grid-column:1/-1;text-align:center;padding:0.75rem;color:var(--text-secondary);font-size:0.75rem;background:#0d0e12;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    No abnormal flow surges detected at this timestamp. Order flow distribution is within standard baseline.
                </div>`;
            return;
        }

        let html = '';
        for (const alert of alerts) {
            let badgeBg = 'rgba(56,189,248,0.12)';
            let badgeColor = '#38bdf8';
            let borderCol = 'rgba(56,189,248,0.25)';

            if (alert.level === 'SUCCESS' || alert.type.includes('PUT_WRITING')) {
                badgeBg = 'rgba(16,185,129,0.12)';
                badgeColor = '#34d399';
                borderCol = 'rgba(16,185,129,0.3)';
            } else if (alert.level === 'WARNING' || alert.type.includes('CALL_WRITING')) {
                badgeBg = 'rgba(239,68,68,0.12)';
                badgeColor = '#f87171';
                borderCol = 'rgba(239,68,68,0.3)';
            }

            html += `
            <div style="background:#0d0e12;border:1px solid ${borderCol};border-radius:8px;padding:0.6rem 0.8rem;display:flex;align-items:flex-start;gap:0.6rem;">
                <span class="badge" style="background:${badgeBg};color:${badgeColor};font-size:0.65rem;font-weight:700;padding:0.15rem 0.4rem;border-radius:4px;white-space:nowrap;margin-top:0.1rem;">
                    ${alert.type}
                </span>
                <div style="flex:1;">
                    <div style="font-size:0.75rem;font-weight:600;color:var(--text-primary);line-height:1.3;">
                        ${alert.text}
                    </div>
                    <div style="font-size:0.65rem;color:var(--text-secondary);font-family:var(--font-mono);margin-top:0.2rem;">
                        ${alert.time || 'Live'}
                    </div>
                </div>
            </div>`;
        }

        container.innerHTML = html;
    };

    /**
     * Render Dual Strike Distribution Charts (Chart.js)
     * Left: Total OI (Calls vs Puts)
     * Right: Intraday OI Change (Writing Flow)
     */
    app.renderDualStrikeCharts = function (strikes, spotPrice) {
        if (!strikes || !strikes.length || !window.Chart) return;

        const oiCanvas = document.getElementById('optDualOiChart');
        const oiChgCanvas = document.getElementById('optDualOiChgChart');
        if (!oiCanvas || !oiChgCanvas) return;

        // Sort strikes ascending
        const sortedStrikes = [...strikes].sort((a, b) => a.strike - b.strike);

        // Filter to reasonable strike window around spot (e.g. 15 strikes above/below)
        let displayStrikes = sortedStrikes;
        if (spotPrice && sortedStrikes.length > 30) {
            const atmIdx = sortedStrikes.findIndex(s => s.strike >= spotPrice);
            const start = Math.max(0, atmIdx - 15);
            const end = Math.min(sortedStrikes.length, atmIdx + 16);
            displayStrikes = sortedStrikes.slice(start, end);
        }

        const labels = displayStrikes.map(s => String(s.strike));
        const callOiData = displayStrikes.map(s => s.ce_oi || 0);
        const putOiData = displayStrikes.map(s => s.pe_oi || 0);
        const callOiChgData = displayStrikes.map(s => s.ce_chg_oi || 0);
        const putOiChgData = displayStrikes.map(s => s.pe_chg_oi || 0);

        // Common Chart.js options
        const baseOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#18181b',
                    titleColor: '#ffffff',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 8,
                    callbacks: {
                        label: function (ctx) {
                            const val = ctx.raw || 0;
                            return `${ctx.dataset.label}: ${val.toLocaleString('en-IN')}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    ticks: {
                        color: '#64748b',
                        font: { size: 10, family: 'monospace' },
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#64748b',
                        font: { size: 10, family: 'monospace' },
                        callback: function (val) {
                            if (Math.abs(val) >= 10000000) return (val / 10000000).toFixed(1) + 'Cr';
                            if (Math.abs(val) >= 100000) return (val / 100000).toFixed(0) + 'L';
                            return val;
                        }
                    }
                }
            }
        };

        // 1. Destroy existing instances
        if (dualOiChartInstance) {
            try { dualOiChartInstance.destroy(); } catch (e) {}
            dualOiChartInstance = null;
        }
        if (dualOiChgChartInstance) {
            try { dualOiChgChartInstance.destroy(); } catch (e) {}
            dualOiChgChartInstance = null;
        }

        // 2. Render Left Chart: Total OI
        const ctxOi = oiCanvas.getContext('2d');
        dualOiChartInstance = new window.Chart(ctxOi, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Call OI (CE)',
                        data: callOiData,
                        backgroundColor: 'rgba(248, 113, 113, 0.8)',
                        borderColor: '#f87171',
                        borderWidth: 1,
                        borderRadius: 3
                    },
                    {
                        label: 'Put OI (PE)',
                        data: putOiData,
                        backgroundColor: 'rgba(52, 211, 153, 0.8)',
                        borderColor: '#34d399',
                        borderWidth: 1,
                        borderRadius: 3
                    }
                ]
            },
            options: baseOptions
        });

        // 3. Render Right Chart: Intraday OI Change
        const ctxOiChg = oiChgCanvas.getContext('2d');
        dualOiChgChartInstance = new window.Chart(ctxOiChg, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Call ΔOI (CE)',
                        data: callOiChgData,
                        backgroundColor: callOiChgData.map(v => v >= 0 ? 'rgba(248, 113, 113, 0.85)' : 'rgba(248, 113, 113, 0.35)'),
                        borderColor: '#f87171',
                        borderWidth: 1,
                        borderRadius: 3
                    },
                    {
                        label: 'Put ΔOI (PE)',
                        data: putOiChgData,
                        backgroundColor: putOiChgData.map(v => v >= 0 ? 'rgba(52, 211, 153, 0.85)' : 'rgba(52, 211, 153, 0.35)'),
                        borderColor: '#34d399',
                        borderWidth: 1,
                        borderRadius: 3
                    }
                ]
            },
            options: baseOptions
        });
    };

})();
