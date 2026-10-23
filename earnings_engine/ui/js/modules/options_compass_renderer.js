/**
 * options_compass_renderer.js - Institutional F&O Confluence & Market Compass Renderer
 * Modular frontend controller for:
 * 1. Multi-Timeframe Call vs Put Open Interest Velocity Meters & Total Positions Two Bars
 * 2. Market Compass Confluence SVG Speedometer & 8-Factor Breakdown
 * 3. Dual Strike Distribution Charts (Total OI, Today's Change, and 15-Min Velocity)
 * 4. Algorithmic Real-Time Institutional Alerts Feed
 */

(function () {
    'use strict';

    window.app = window.app || {};
    const app = window.app;

    // Chart instances cache
    let dualOiChartInstance = null;
    let dualOiChgChartInstance = null;

    // State for interactive strike chart toggling
    let cachedStrikes = [];
    let cachedSpotPrice = null;
    let activeChartMode = 'oi'; // 'oi' | 'today' | '15m'
    let buttonsInitialized = false;

    // State for extended macro timeframes toggle (Weekly, Monthly, Quarterly)
    let showExtendedTf = false;
    let extendedTfButtonBound = false;

    function _setupExtendedTfToggle() {
        const btn = document.getElementById('optToggleExtendedTfBtn');
        if (!btn || extendedTfButtonBound) return;
        btn.addEventListener('click', () => {
            showExtendedTf = !showExtendedTf;
            _updateExtendedTfDisplay();
        });
        extendedTfButtonBound = true;
    }

    function _updateExtendedTfDisplay() {
        const btn = document.getElementById('optToggleExtendedTfBtn');
        const icon = document.getElementById('optToggleExtendedTfIcon');
        const label = document.getElementById('optToggleExtendedTfLabel');
        if (btn) {
            if (showExtendedTf) {
                btn.style.background = 'rgba(56, 189, 248, 0.15)';
                btn.style.borderColor = 'rgba(56, 189, 248, 0.35)';
                btn.style.color = '#38bdf8';
                if (icon) icon.textContent = '➖';
                if (label) label.textContent = 'Hide Macro (1W / 1M / 3M)';
            } else {
                btn.style.background = 'rgba(255, 255, 255, 0.06)';
                btn.style.borderColor = 'rgba(255, 255, 255, 0.12)';
                btn.style.color = 'var(--text-primary)';
                if (icon) icon.textContent = '➕';
                if (label) label.textContent = 'Weekly / Monthly / Quarterly';
            }
        }
        const extRows = document.querySelectorAll('.opt-extended-tf-row');
        extRows.forEach(row => {
            row.style.display = showExtendedTf ? 'table-row' : 'none';
        });
    }

    // Helper to format number in Indian Lakhs/Crores
    const fmtOi = (num, signed = true) => {
        const n = Math.abs(num || 0);
        const sign = signed ? ((num || 0) >= 0 ? '+' : '-') : '';
        if (n >= 10000000) return `${sign}${(n / 10000000).toFixed(2)}Cr`;
        if (n >= 100000) return `${sign}${(n / 100000).toFixed(2)}L`;
        if (n >= 1000) return `${sign}${(n / 1000).toFixed(1)}k`;
        return `${sign}${n}`;
    };

    /**
     * Render Multi-Timeframe Call vs Put OI Meters & Total Positions
     */
    app.renderOiTimeframeMeters = function (timeframesData, pcrOi) {
        if (!timeframesData) return;

        // 1. Total Positions (Two Bars: Calls vs Puts)
        const tp = timeframesData.total_positions || {};
        const totCallsFmt = document.getElementById('optTotCallsFormatted');
        const totCallsPct = document.getElementById('optTotCallsPct');
        const totCallsBar = document.getElementById('optTotCallsBar');
        const totPutsFmt = document.getElementById('optTotPutsFormatted');
        const totPutsPct = document.getElementById('optTotPutsPct');
        const totPutsBar = document.getElementById('optTotPutsBar');

        if (tp.call_oi !== undefined || timeframesData.today?.call_oi !== undefined) {
            const cOi = tp.call_oi !== undefined ? tp.call_oi : (timeframesData.today?.call_oi || 0);
            const pOi = tp.put_oi !== undefined ? tp.put_oi : (timeframesData.today?.put_oi || 0);
            const cPct = tp.call_pct !== undefined ? tp.call_pct : Math.round((cOi / Math.max(cOi + pOi, 1)) * 100);
            const pPct = tp.put_pct !== undefined ? tp.put_pct : Math.round((pOi / Math.max(cOi + pOi, 1)) * 100);

            if (totCallsFmt) totCallsFmt.textContent = tp.call_oi_formatted || fmtOi(cOi, false);
            if (totCallsPct) totCallsPct.textContent = `${cPct}%`;
            if (totCallsBar) totCallsBar.style.width = `${cPct}%`;

            if (totPutsFmt) totPutsFmt.textContent = tp.put_oi_formatted || fmtOi(pOi, false);
            if (totPutsPct) totPutsPct.textContent = `${pPct}%`;
            if (totPutsBar) totPutsBar.style.width = `${pPct}%`;
        }

        // 2. Card: Today
        const td = timeframesData.today;
        if (td) {
            const badge = document.getElementById('optTfTodayBadge');
            const callBar = document.getElementById('optTfTodayCallBar');
            const putBar = document.getElementById('optTfTodayPutBar');
            const callChg = document.getElementById('optTfTodayCallChg');
            const putChg = document.getElementById('optTfTodayPutChg');
            const callPctChg = document.getElementById('optTfTodayCallPctChg');
            const putPctChg = document.getElementById('optTfTodayPutPctChg');

            if (badge) badge.textContent = td.sentiment || 'NEUTRAL';
            if (callBar) callBar.style.width = `${td.call_pct || 50}%`;
            if (putBar) putBar.style.width = `${td.put_pct || 50}%`;
            if (callChg) callChg.textContent = fmtOi(td.call_chg);
            if (putChg) putChg.textContent = fmtOi(td.put_chg);

            if (callPctChg) {
                const pct = td.call_pct_chg !== undefined ? td.call_pct_chg : 0;
                callPctChg.textContent = `${pct >= 0 ? '+' : ''}${pct}%`;
            }
            if (putPctChg) {
                const pct = td.put_pct_chg !== undefined ? td.put_pct_chg : 0;
                putPctChg.textContent = `${pct >= 0 ? '+' : ''}${pct}%`;
            }
        }

        // 3. Card: 15m Velocity
        const m15 = timeframesData.tf_15m;
        if (m15) {
            const badge = document.getElementById('optTf15mBadge');
            const callBar = document.getElementById('optTf15mCallBar');
            const putBar = document.getElementById('optTf15mPutBar');
            const callChg = document.getElementById('optTf15mCallChg');
            const putChg = document.getElementById('optTf15mPutChg');
            const callPctChg = document.getElementById('optTf15mCallPctChg');
            const putPctChg = document.getElementById('optTf15mPutPctChg');

            if (badge) badge.textContent = m15.sentiment || 'NEUTRAL';
            if (callBar) callBar.style.width = `${m15.call_pct || 50}%`;
            if (putBar) putBar.style.width = `${m15.put_pct || 50}%`;
            if (callChg) callChg.textContent = fmtOi(m15.call_chg);
            if (putChg) putChg.textContent = fmtOi(m15.put_chg);

            if (callPctChg) {
                const pct = m15.call_pct_chg !== undefined ? m15.call_pct_chg : 0;
                callPctChg.textContent = `${pct >= 0 ? '+' : ''}${pct}%`;
            }
            if (putPctChg) {
                const pct = m15.put_pct_chg !== undefined ? m15.put_pct_chg : 0;
                putPctChg.textContent = `${pct >= 0 ? '+' : ''}${pct}%`;
            }
        }

        // 4. Card: 5m Burst
        const m5 = timeframesData.tf_5m;
        if (m5) {
            const badge = document.getElementById('optTf5mBadge');
            const callBar = document.getElementById('optTf5mCallBar');
            const putBar = document.getElementById('optTf5mPutBar');
            const callChg = document.getElementById('optTf5mCallChg');
            const putChg = document.getElementById('optTf5mPutChg');
            const callPctChg = document.getElementById('optTf5mCallPctChg');
            const putPctChg = document.getElementById('optTf5mPutPctChg');

            if (badge) badge.textContent = m5.sentiment || 'NEUTRAL';
            if (callBar) callBar.style.width = `${m5.call_pct || 50}%`;
            if (putBar) putBar.style.width = `${m5.put_pct || 50}%`;
            if (callChg) callChg.textContent = fmtOi(m5.call_chg);
            if (putChg) putChg.textContent = fmtOi(m5.put_chg);

            if (callPctChg) {
                const pct = m5.call_pct_chg !== undefined ? m5.call_pct_chg : 0;
                callPctChg.textContent = `${pct >= 0 ? '+' : ''}${pct}%`;
            }
            if (putPctChg) {
                const pct = m5.put_pct_chg !== undefined ? m5.put_pct_chg : 0;
                putPctChg.textContent = `${pct >= 0 ? '+' : ''}${pct}%`;
            }
        }

        // 5. PCR (OI) & 15m Delta
        const pcrVal = document.getElementById('optFlowPcrVal');
        const pcrBias = document.getElementById('optFlowPcrBias');
        const pcr15m = document.getElementById('optFlowPcr15mChg');

        const activePcr = pcrOi !== undefined ? pcrOi : (timeframesData.summary_alert?.pcr_oi || 1.0);
        if (pcrVal) pcrVal.textContent = Number(activePcr).toFixed(2);

        if (pcrBias) {
            if (activePcr >= 1.2) {
                pcrBias.textContent = 'Put Writing Support';
                pcrBias.style.color = '#34d399';
            } else if (activePcr <= 0.8) {
                pcrBias.textContent = 'Call Writing Resistance';
                pcrBias.style.color = '#f87171';
            } else {
                pcrBias.textContent = 'Balanced Equilibrium';
                pcrBias.style.color = '#fbbf24';
            }
        }

        if (pcr15m) {
            const delta = timeframesData.summary_alert?.pcr_15m_delta;
            if (delta !== undefined && delta !== null) {
                const sign = delta >= 0 ? '+' : '';
                const color = delta > 0 ? '#34d399' : (delta < 0 ? '#f87171' : 'var(--text-secondary)');
                pcr15m.innerHTML = `<span style="color:${color};font-weight:700;">${sign}${delta.toFixed(2)} in 15 min</span>`;
            } else {
                pcr15m.innerHTML = `<span style="color:var(--text-secondary);">-- in 15 min</span>`;
            }
        }

        // 6. Dynamic Flow Alert Banner
        const alertBanner = document.getElementById('optVelocityAlertBanner');
        const alertText = document.getElementById('optVelocityAlertText');
        const alertTag = document.getElementById('optVelocityAlertTag');

        if (timeframesData.summary_alert) {
            const sumAlert = timeframesData.summary_alert;
            if (alertText) alertText.textContent = sumAlert.text || 'Order flow analysis completed.';
            if (alertTag) {
                alertTag.textContent = sumAlert.bias || 'FLOW INTEL';
                if (sumAlert.bias === 'BULLISH') {
                    alertTag.style.background = 'rgba(16, 185, 129, 0.15)';
                    alertTag.style.color = '#34d399';
                    alertTag.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                    if (alertBanner) alertBanner.style.borderLeftColor = '#10b981';
                } else if (sumAlert.bias === 'BEARISH') {
                    alertTag.style.background = 'rgba(239, 68, 68, 0.15)';
                    alertTag.style.color = '#f87171';
                    alertTag.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                    if (alertBanner) alertBanner.style.borderLeftColor = '#ef4444';
                } else {
                    alertTag.style.background = 'rgba(56, 189, 248, 0.15)';
                    alertTag.style.color = '#38bdf8';
                    alertTag.style.borderColor = 'rgba(56, 189, 248, 0.3)';
                    if (alertBanner) alertBanner.style.borderLeftColor = '#38bdf8';
                }
            }
        }

        // 7. Multi-Timeframe Tabular Matrix & Action Directives
        const tableBody = document.getElementById('optMultiTfTableBody');
        const confBadge = document.getElementById('optMultiTfConfluenceBadge');
        const macroPill = document.getElementById('optMultiTfMacroPill');
        const headlineEl = document.getElementById('optMultiTfHeadline');
        const directiveEl = document.getElementById('optMultiTfDirectiveText');
        const directiveBox = document.getElementById('optMultiTfMasterDirectiveBox');

        // Update Confluence Header & Master Directive
        const cs = timeframesData.confluence_summary;
        if (cs) {
            if (confBadge) {
                confBadge.textContent = `${cs.bullish_count}/6 BULLISH | ${cs.bearish_count}/6 BEARISH`;
                if (cs.overall_bias.includes('BULLISH')) {
                    confBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                    confBadge.style.color = '#34d399';
                    confBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                } else if (cs.overall_bias.includes('BEARISH')) {
                    confBadge.style.background = 'rgba(239, 68, 68, 0.15)';
                    confBadge.style.color = '#f87171';
                    confBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                } else {
                    confBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                    confBadge.style.color = '#fbbf24';
                    confBadge.style.borderColor = 'rgba(245, 158, 11, 0.3)';
                }
            }

            if (macroPill) {
                macroPill.textContent = `VERDICT: ${cs.overall_bias}`;
                if (cs.overall_bias.includes('BULLISH')) {
                    macroPill.style.color = '#34d399';
                    macroPill.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                    macroPill.style.background = 'rgba(16, 185, 129, 0.08)';
                } else if (cs.overall_bias.includes('BEARISH')) {
                    macroPill.style.color = '#f87171';
                    macroPill.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                    macroPill.style.background = 'rgba(239, 68, 68, 0.08)';
                } else {
                    macroPill.style.color = '#fbbf24';
                    macroPill.style.borderColor = 'rgba(245, 158, 11, 0.3)';
                    macroPill.style.background = 'rgba(245, 158, 11, 0.08)';
                }
            }

            if (headlineEl) headlineEl.textContent = cs.headline || 'Cross-Timeframe Master Directive';
            if (directiveEl) directiveEl.textContent = cs.master_directive || 'Order flow delta synthesized.';

            if (directiveBox) {
                if (cs.overall_bias.includes('BULLISH')) {
                    directiveBox.style.background = 'rgba(16, 185, 129, 0.06)';
                    directiveBox.style.borderColor = 'rgba(16, 185, 129, 0.25)';
                } else if (cs.overall_bias.includes('BEARISH')) {
                    directiveBox.style.background = 'rgba(239, 68, 68, 0.06)';
                    directiveBox.style.borderColor = 'rgba(239, 68, 68, 0.25)';
                } else {
                    directiveBox.style.background = 'rgba(245, 158, 11, 0.06)';
                    directiveBox.style.borderColor = 'rgba(245, 158, 11, 0.25)';
                }
            }
        }

        // Render Table Rows
        const tfRows = timeframesData.timeframes_table || [];
        if (tableBody && tfRows.length > 0) {
            _setupExtendedTfToggle();
            let rowsHtml = '';
            tfRows.forEach(row => {
                const isExt = Boolean(row.is_extended);
                const displayStyle = isExt ? (showExtendedTf ? 'table-row' : 'none') : 'table-row';
                const rowClass = isExt ? 'opt-extended-tf-row' : '';
                const macroBadge = isExt ? '<span class="badge" style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);border-radius:3px;padding:0.05rem 0.25rem;font-size:0.58rem;font-weight:700;margin-left:0.35rem;">MACRO</span>' : '';

                const callVal = row.call_chg !== undefined ? row.call_chg : 0;
                const putVal = row.put_chg !== undefined ? row.put_chg : 0;
                const netVal = row.net_delta !== undefined ? row.net_delta : (putVal - callVal);
                const bias = row.bias || 'NEUTRAL';

                // Formatting
                const callFmt = row.call_chg_fmt || fmtOi(callVal);
                const putFmt = row.put_chg_fmt || fmtOi(putVal);
                const netFmt = row.net_delta_fmt || fmtOi(netVal);

                // Colors
                const callCol = callVal > 0 ? '#f87171' : (callVal < 0 ? '#38bdf8' : 'var(--text-secondary)');
                const putCol = putVal > 0 ? '#34d399' : (putVal < 0 ? '#f87171' : 'var(--text-secondary)');
                const netCol = netVal > 0 ? '#34d399' : (netVal < 0 ? '#f87171' : 'var(--text-secondary)');

                // Bias Badge Styles
                let biasBg = 'rgba(245, 158, 11, 0.15)';
                let biasCol = '#fbbf24';
                let biasBrd = 'rgba(245, 158, 11, 0.3)';
                let actionBrd = 'rgba(245, 158, 11, 0.2)';
                let actionCol = '#fbbf24';

                if (bias === 'BULLISH') {
                    biasBg = 'rgba(16, 185, 129, 0.15)';
                    biasCol = '#34d399';
                    biasBrd = 'rgba(16, 185, 129, 0.3)';
                    actionBrd = 'rgba(16, 185, 129, 0.25)';
                    actionCol = '#34d399';
                } else if (bias === 'BEARISH') {
                    biasBg = 'rgba(239, 68, 68, 0.15)';
                    biasCol = '#f87171';
                    biasBrd = 'rgba(239, 68, 68, 0.3)';
                    actionBrd = 'rgba(239, 68, 68, 0.25)';
                    actionCol = '#f87171';
                }

                rowsHtml += `
                <tr class="${rowClass}" style="display:${displayStyle};border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.2s ease;">
                    <td style="padding:0.6rem;font-weight:700;color:var(--text-primary);white-space:nowrap;">
                        <div style="display:flex;align-items:center;">
                            <span>${row.timeframe}</span>
                            ${macroBadge}
                        </div>
                        <div style="font-size:0.65rem;color:var(--text-secondary);font-family:var(--font-mono);font-weight:400;">
                            ${row.scope || ''}
                        </div>
                    </td>
                    <td style="padding:0.6rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:${callCol};">
                        ${callFmt}
                    </td>
                    <td style="padding:0.6rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:${putCol};">
                        ${putFmt}
                    </td>
                    <td style="padding:0.6rem;text-align:right;font-family:var(--font-mono);font-weight:800;color:${netCol};">
                        ${netFmt}
                    </td>
                    <td style="padding:0.6rem;text-align:center;">
                        <span class="badge" style="background:${biasBg};color:${biasCol};border:1px solid ${biasBrd};font-size:0.65rem;padding:0.15rem 0.45rem;border-radius:4px;font-weight:800;">
                            ${bias}
                        </span>
                        <div style="font-size:0.62rem;color:var(--text-secondary);font-family:var(--font-mono);margin-top:0.2rem;">
                            ${row.badge || row.sentiment || ''}
                        </div>
                    </td>
                    <td style="padding:0.6rem;color:var(--text-primary);line-height:1.35;font-size:0.72rem;">
                        ${row.what_is_happening || '--'}
                    </td>
                    <td style="padding:0.6rem;line-height:1.35;">
                        <div style="background:rgba(255,255,255,0.02);border:1px solid ${actionBrd};border-left:3px solid ${biasCol};border-radius:4px;padding:0.3rem 0.5rem;font-size:0.72rem;font-weight:600;color:var(--text-primary);">
                            <span style="color:${actionCol};font-weight:800;margin-right:0.3rem;">ACTION:</span>
                            ${row.what_to_do || '--'}
                        </div>
                    </td>
                </tr>`;
            });
            tableBody.innerHTML = rowsHtml;
            _updateExtendedTfDisplay();
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
     * Internal setup of mode buttons [Open interest] [OI change today] [OI change - 15 min]
     */
    function _setupStrikeChartModeButtons() {
        if (buttonsInitialized) return;
        const btnOi = document.getElementById('optBtnViewOi');
        const btnToday = document.getElementById('optBtnViewToday');
        const btn15m = document.getElementById('optBtnView15m');

        if (!btnOi || !btnToday || !btn15m) return;

        const updateBtnStyles = (activeMode) => {
            [btnOi, btnToday, btn15m].forEach(b => {
                if (b.getAttribute('data-mode') === activeMode) {
                    b.style.background = 'rgba(255,255,255,0.15)';
                    b.style.color = '#ffffff';
                } else {
                    b.style.background = 'transparent';
                    b.style.color = 'var(--text-secondary)';
                }
            });
        };

        btnOi.addEventListener('click', () => {
            activeChartMode = 'oi';
            updateBtnStyles('oi');
            if (cachedStrikes.length) app.renderDualStrikeCharts(cachedStrikes, cachedSpotPrice);
        });

        btnToday.addEventListener('click', () => {
            activeChartMode = 'today';
            updateBtnStyles('today');
            if (cachedStrikes.length) app.renderDualStrikeCharts(cachedStrikes, cachedSpotPrice);
        });

        btn15m.addEventListener('click', () => {
            activeChartMode = '15m';
            updateBtnStyles('15m');
            if (cachedStrikes.length) app.renderDualStrikeCharts(cachedStrikes, cachedSpotPrice);
        });

        buttonsInitialized = true;
    }

    /**
     * Render Dual Strike Distribution Charts (Chart.js)
     * Left: Total OI (Calls vs Puts)
     * Right: Intraday / 15m OI Change (Writing Flow)
     */
    app.renderDualStrikeCharts = function (strikes, spotPrice) {
        if (!strikes || !strikes.length || !window.Chart) return;

        cachedStrikes = strikes;
        cachedSpotPrice = spotPrice;
        _setupStrikeChartModeButtons();

        const oiCanvas = document.getElementById('optDualOiChart');
        const oiChgCanvas = document.getElementById('optDualOiChgChart');
        if (!oiCanvas || !oiChgCanvas) return;

        // Dynamic Subtitles and Titles according to mode
        const leftTitle = document.getElementById('optDualOiChartTitle');
        const leftSub = document.getElementById('optDualOiChartSubtitle');
        const rightTitle = document.getElementById('optDualOiChgChartTitle');
        const rightSub = document.getElementById('optDualOiChgChartSubtitle');

        if (leftTitle) leftTitle.textContent = 'OI by Strike (Positioning Depth)';
        if (leftSub) leftSub.textContent = 'Cumulative Contracts';

        if (activeChartMode === '15m') {
            if (rightTitle) rightTitle.textContent = '15-Min OI Change by Strike';
            if (rightSub) rightSub.textContent = '15m Rolling Velocity';
        } else {
            if (rightTitle) rightTitle.textContent = 'Intraday OI Change by Strike';
            if (rightSub) rightSub.textContent = 'Session Delta';
        }

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

        // Right chart data changes based on active mode
        let callOiChgData;
        let putOiChgData;
        let rightCallLabel;
        let rightPutLabel;

        if (activeChartMode === '15m') {
            callOiChgData = displayStrikes.map(s => s.ce_change_15m !== undefined ? s.ce_change_15m : (s.ce_chg_oi || 0));
            putOiChgData = displayStrikes.map(s => s.pe_change_15m !== undefined ? s.pe_change_15m : (s.pe_chg_oi || 0));
            rightCallLabel = 'Call 15m ΔOI (CE)';
            rightPutLabel = 'Put 15m ΔOI (PE)';
        } else {
            callOiChgData = displayStrikes.map(s => s.ce_chg_oi !== undefined ? s.ce_chg_oi : (s.ce_change_oi || 0));
            putOiChgData = displayStrikes.map(s => s.pe_chg_oi !== undefined ? s.pe_chg_oi : (s.pe_change_oi || 0));
            rightCallLabel = 'Call Today ΔOI (CE)';
            rightPutLabel = 'Put Today ΔOI (PE)';
        }

        // Common Chart.js options
        const baseOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 250 },
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

        // 3. Render Right Chart: Intraday or 15m OI Change
        const ctxOiChg = oiChgCanvas.getContext('2d');
        dualOiChgChartInstance = new window.Chart(ctxOiChg, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: rightCallLabel,
                        data: callOiChgData,
                        backgroundColor: callOiChgData.map(v => v >= 0 ? 'rgba(248, 113, 113, 0.85)' : 'rgba(248, 113, 113, 0.35)'),
                        borderColor: '#f87171',
                        borderWidth: 1,
                        borderRadius: 3
                    },
                    {
                        label: rightPutLabel,
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
