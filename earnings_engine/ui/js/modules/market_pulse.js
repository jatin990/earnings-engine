// =========================================================================
// 🌐 Market Pulse & Macro Command Center Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || (window.location && window.location.origin) || '';
    window.app = window.app || {};
    const app = window.app;

    const marketPulseModule = {
        pulseData: null,
        _pulseLoaded: false,
        _isFlowHistoryExpanded: false,
        _lastFlowsData: null,

        async loadMarketPulseData(forceRefresh = false) {
            const timeEl = document.getElementById('pulseAsOfTime');
            const badgeEl = document.getElementById('pulseLiveBadge');
            if (badgeEl) badgeEl.textContent = '● REFRESHING...';

            try {
                const url = API_BASE + '/api/v1/market/pulse' + (forceRefresh ? '?force_refresh=true' : '');
                const res = await fetch(url);
                if (!res.ok) throw new Error('HTTP ' + res.status);
                
                const data = await res.json();
                this.pulseData = data;
                this._pulseLoaded = true;
                if (window.app) {
                    window.app.pulseData = data;
                    window.app._pulseLoaded = true;
                }

                if (timeEl) {
                    const now = new Date();
                    timeEl.textContent = 'Updated: ' + now.toLocaleTimeString();
                }
                if (badgeEl) badgeEl.textContent = '● LIVE TICK';

                this.renderIndices(data.indices || []);
                this.renderFearAndGreed(data.fear_and_greed || {});
                this.renderVolatility(data.volatility || {});
                this.renderPrediction(data.prediction || {});
                this.renderBreadth(data.breadth || {});
                this.renderInstitutionalFlows(data.institutional_flows || {});
                this.renderParticipantOI(data.participant_oi || {});
                this.renderSectors(data.sectors || []);
                this.renderMacroCharts(data.macro_charts || {});
                this.loadConfluenceSetups();

            } catch (e) {
                console.error('[MARKET_PULSE] Error loading market pulse:', e);
                if (badgeEl) badgeEl.textContent = '⚠️ SYNC DELAY';
            }
        },

        renderIndices(indices) {
            const grid = document.getElementById('pulseIndicesGrid');
            if (!grid) return;

            if (!indices || !indices.length) {
                grid.innerHTML = '<div style="color:#64748b;font-size:0.75rem;">Indices data loading...</div>';
                return;
            }

            grid.innerHTML = indices.map(idx => {
                const isPositive = idx.change_pct >= 0;
                const isVix = idx.symbol === '^INDIAVIX';
                
                // For VIX, down is good (green), up is volatility risk (red)
                const col = isVix ? (idx.change_pct <= 0 ? '#34d399' : '#f87171') : (isPositive ? '#34d399' : '#f87171');
                const sign = idx.change_pct >= 0 ? '+' : '';
                const ptsSign = idx.change_pts >= 0 ? '+' : '';

                // Simple SVG sparkline
                const points = idx.sparkline || [];
                let sparkSvg = '';
                if (points.length >= 2) {
                    const minP = Math.min(...points);
                    const maxP = Math.max(...points);
                    const range = (maxP - minP) || 1.0;
                    const w = 70;
                    const h = 22;
                    const coords = points.map((p, i) => {
                        const x = (i / (points.length - 1)) * w;
                        const y = h - ((p - minP) / range) * (h - 4) - 2;
                        return `${x.toFixed(1)},${y.toFixed(1)}`;
                    }).join(' ');
                    sparkSvg = `
                        <svg width="${w}" height="${h}" style="overflow:visible;">
                            <polyline fill="none" stroke="${col}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" points="${coords}" />
                        </svg>
                    `;
                }

                return `
                    <div class="card" style="padding:0.75rem 0.85rem;background:#0b1329;border:1px solid rgba(255,255,255,0.08);display:flex;flex-direction:column;justify-content:space-between;">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.35rem;">
                            <div>
                                <div style="font-size:0.68rem;color:#94a3b8;font-weight:700;letter-spacing:0.04em;">${idx.name}</div>
                                <div style="font-size:1.05rem;font-weight:900;color:#f8fafc;font-family:var(--font-mono);margin-top:0.15rem;">
                                    ${idx.current_price.toLocaleString()}
                                </div>
                            </div>
                            <div style="text-align:right;">
                                ${sparkSvg}
                            </div>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.68rem;font-family:var(--font-mono);">
                            <span style="color:#64748b;">${ptsSign}${idx.change_pts}</span>
                            <span style="font-weight:800;color:${col};background:${col}15;padding:0.1rem 0.35rem;border-radius:3px;">
                                ${sign}${idx.change_pct}%
                            </span>
                        </div>
                    </div>
                `;
            }).join('');
        },

        renderFearAndGreed(fg) {
            const scoreEl = document.getElementById('pulseFgScore');
            const badgeEl = document.getElementById('pulseFgBadge');
            const barEl = document.getElementById('pulseFgBar');
            const descEl = document.getElementById('pulseFgDesc');
            const momEl = document.getElementById('pulseFgMom');
            const vixEl = document.getElementById('pulseFgVix');
            const breadthEl = document.getElementById('pulseFgBreadth');

            if (scoreEl) {
                scoreEl.textContent = fg.score != null ? fg.score : '—';
                scoreEl.style.color = fg.color || '#34d399';
            }
            if (badgeEl) {
                badgeEl.textContent = fg.label || 'Greed';
                badgeEl.style.color = fg.color || '#34d399';
                badgeEl.style.background = (fg.color || '#34d399') + '22';
            }
            if (barEl && fg.score != null) {
                barEl.style.width = Math.min(100, Math.max(5, fg.score)) + '%';
            }
            if (descEl && fg.description) descEl.textContent = fg.description;
            if (momEl) momEl.textContent = fg.momentum_factor != null ? fg.momentum_factor : '—';
            if (vixEl) vixEl.textContent = fg.vix_factor != null ? fg.vix_factor : '—';
            if (breadthEl) breadthEl.textContent = fg.breadth_factor != null ? fg.breadth_factor : '—';
        },

        renderVolatility(vix) {
            const levelEl = document.getElementById('pulseVixLevel');
            const changeEl = document.getElementById('pulseVixChange');
            const badgeEl = document.getElementById('pulseVixRegimeBadge');
            const descEl = document.getElementById('pulseVixDesc');
            const stanceEl = document.getElementById('pulseVixStance');

            if (levelEl) levelEl.textContent = vix.vix_level != null ? vix.vix_level : '13.8';
            if (badgeEl && vix.regime) badgeEl.textContent = vix.regime;
            if (descEl && vix.description) descEl.textContent = vix.description;
            if (stanceEl && vix.stance) {
                stanceEl.textContent = vix.stance.replace(/_/g, ' ');
                stanceEl.style.color = vix.stance.includes('BULLISH') ? '#34d399' : vix.stance.includes('BEARISH') ? '#f87171' : '#fbbf24';
            }
        },

        renderPrediction(pred) {
            const regimeEl = document.getElementById('pulsePredictionRegime');
            const commEl = document.getElementById('pulsePredictionCommentary');
            const convPill = document.getElementById('pulseConvictionPill');
            const supEl = document.getElementById('pulseNiftySupport');
            const resEl = document.getElementById('pulseNiftyResistance');

            if (regimeEl && pred.regime) regimeEl.textContent = pred.regime;
            if (commEl && pred.commentary) commEl.textContent = pred.commentary;
            if (convPill && pred.conviction_pct) convPill.textContent = `${pred.conviction_pct}% CONVICTION`;
            if (supEl && pred.nifty_support) supEl.textContent = pred.nifty_support;
            if (resEl && pred.nifty_resistance) resEl.textContent = pred.nifty_resistance;
        },

        renderBreadth(b) {
            const advEl = document.getElementById('pulseAdvancesCount');
            const decEl = document.getElementById('pulseDeclinesCount');
            const unchEl = document.getElementById('pulseUnchangedCount');
            const advBar = document.getElementById('pulseAdvBar');
            const unchBar = document.getElementById('pulseUnchBar');
            const decBar = document.getElementById('pulseDecBar');
            const p20El = document.getElementById('pulsePct20dma');
            const p50El = document.getElementById('pulsePct50dma');

            if (advEl) advEl.textContent = (b.advances || 0).toLocaleString();
            if (decEl) decEl.textContent = (b.declines || 0).toLocaleString();
            if (unchEl) unchEl.textContent = (b.unchanged || 0).toLocaleString();

            const tot = (b.advances || 0) + (b.declines || 0) + (b.unchanged || 0) || 1;
            if (advBar) advBar.style.width = ((b.advances / tot) * 100).toFixed(1) + '%';
            if (unchBar) unchBar.style.width = ((b.unchanged / tot) * 100).toFixed(1) + '%';
            if (decBar) decBar.style.width = ((b.declines / tot) * 100).toFixed(1) + '%';

            if (p20El) p20El.textContent = (b.pct_above_20dma != null ? b.pct_above_20dma + '%' : '—');
            if (p50El) p50El.textContent = (b.pct_above_50dma != null ? b.pct_above_50dma + '%' : '—');
        },

        renderInstitutionalFlows(flows) {
            const fiiEl = document.getElementById('pulseFiiNet');
            const diiEl = document.getElementById('pulseDiiNet');
            const totEl = document.getElementById('pulseTotalNet');
            const biasEl = document.getElementById('pulseInstBias');
            const badge7d = document.getElementById('pulse7dTotalBadge');
            const summary7d = document.getElementById('pulse7dFiiDiiSummary');
            const tbody7d = document.getElementById('pulse7dFlowsTableBody');
            const titleEl = document.getElementById('pulseFlowHistoryTitle');
            const countBadge = document.getElementById('pulseFlowHistoryCountBadge');
            const toggleBtn = document.getElementById('pulseToggleFlowHistoryBtn');
            const containerEl = document.getElementById('pulseFlowsTableContainer');

            // Resolve robust flows data from whatever source is available
            if (!flows || Object.keys(flows).length === 0) {
                flows = this._lastFlowsData
                    || (window.app && window.app._lastFlowsData)
                    || (this.pulseData && this.pulseData.institutional_flows)
                    || (window.app && window.app.pulseData && window.app.pulseData.institutional_flows)
                    || {};
            }

            this._lastFlowsData = flows;
            if (window.app) window.app._lastFlowsData = flows;

            const sessionLabel = flows.session_label || flows.as_of_date || 'Latest Session';
            const fiiLbl = document.getElementById('pulseSessionFiiLabel');
            const diiLbl = document.getElementById('pulseSessionDiiLabel');
            const totLbl = document.getElementById('pulseSessionTotLabel');
            if (fiiLbl) fiiLbl.textContent = `${sessionLabel} FII`;
            if (diiLbl) diiLbl.textContent = `${sessionLabel} DII`;
            if (totLbl) totLbl.textContent = `${sessionLabel} Total`;

            if (fiiEl && flows.fii_net_cr !== undefined && flows.fii_net_cr !== null) {
                const s = flows.fii_net_cr >= 0 ? '+' : '';
                fiiEl.textContent = `${s}₹${flows.fii_net_cr.toLocaleString()} Cr`;
                fiiEl.style.color = flows.fii_net_cr >= 0 ? '#34d399' : '#f87171';
            }
            if (diiEl && flows.dii_net_cr !== undefined && flows.dii_net_cr !== null) {
                const s = flows.dii_net_cr >= 0 ? '+' : '';
                diiEl.textContent = `${s}₹${flows.dii_net_cr.toLocaleString()} Cr`;
                diiEl.style.color = flows.dii_net_cr >= 0 ? '#34d399' : '#f87171';
            }
            if (totEl && flows.total_net_cr !== undefined && flows.total_net_cr !== null) {
                const s = flows.total_net_cr >= 0 ? '+' : '';
                totEl.textContent = `${s}₹${flows.total_net_cr.toLocaleString()} Cr`;
                totEl.style.color = flows.total_net_cr >= 0 ? '#38bdf8' : '#f87171';
            }
            const biasText = flows.bias || flows.regime_badge;
            if (biasEl && biasText) {
                biasEl.textContent = biasText;
                biasEl.style.color = biasText.includes('BULLISH') || biasText.includes('Accumulation') ? '#34d399' : (biasText.includes('Distribution') || biasText.includes('DEFENSIVE') ? '#f87171' : '#94a3b8');
            }

            const isExpanded = !!(this._isFlowHistoryExpanded || (window.app && window.app._isFlowHistoryExpanded));
            const history = isExpanded
                ? (flows.history_extended || flows.history_30d || flows.history_7d || [])
                : (flows.history_7d || flows.past_7_days || []);

            // Dynamic Timeframe Total Badge (7D vs 30D)
            if (badge7d) {
                const totalVal = isExpanded
                    ? (flows.total_30d_total_cr ?? flows.total_7d_total_cr ?? 0)
                    : (flows.total_7d_total_cr ?? 0);
                const label = isExpanded ? '30D Net' : '7D Net';
                const s = totalVal >= 0 ? '+' : '';
                badge7d.textContent = `${label}: ${s}₹${Math.abs(totalVal).toLocaleString()} Cr`;
                badge7d.style.color = totalVal >= 0 ? '#38bdf8' : '#f87171';
                badge7d.style.background = totalVal >= 0 ? 'rgba(56,189,248,0.12)' : 'rgba(248,113,113,0.12)';
                badge7d.style.borderColor = totalVal >= 0 ? 'rgba(56,189,248,0.25)' : 'rgba(248,113,113,0.25)';
            }

            // Sub-Summary Breakdown
            if (summary7d) {
                const fVal = isExpanded ? (flows.fii_30d_total_cr ?? flows.fii_7d_total_cr ?? 0) : (flows.fii_7d_total_cr ?? 0);
                const dVal = isExpanded ? (flows.dii_30d_total_cr ?? flows.dii_7d_total_cr ?? 0) : (flows.dii_7d_total_cr ?? 0);
                const fSign = fVal >= 0 ? '+' : '';
                const dSign = dVal >= 0 ? '+' : '';
                summary7d.textContent = `FII: ${fSign}₹${fVal.toLocaleString()} Cr | DII: ${dSign}₹${dVal.toLocaleString()} Cr`;
            }

            // Update Header & Controls
            if (titleEl) {
                titleEl.textContent = isExpanded ? 'Past 30 Days Activity' : 'Past 7 Days Activity';
            }
            if (countBadge) {
                countBadge.textContent = `${history.length} Sessions`;
                countBadge.style.color = isExpanded ? '#38bdf8' : '#94a3b8';
                countBadge.style.background = isExpanded ? 'rgba(56,189,248,0.12)' : 'rgba(255,255,255,0.06)';
            }
            if (toggleBtn) {
                toggleBtn.innerHTML = isExpanded ? '🔼 Show Less (7D)' : '🔽 Show More (30D)';
            }
            if (containerEl) {
                containerEl.style.maxHeight = isExpanded ? '380px' : '180px';
            }

            // Flow History Table Rows
            if (tbody7d) {
                if (!history.length) {
                    tbody7d.innerHTML = '<tr><td colspan="5" style="padding:1rem;text-align:center;color:#64748b;">No recent institutional flow history found.</td></tr>';
                    return;
                }

                tbody7d.innerHTML = history.map((row, idx) => {
                    const isToday = idx === 0;
                    const rowBg = isToday ? 'rgba(56,189,248,0.06)' : 'transparent';
                    const fiiVal = row.fii_net_cr ?? 0;
                    const diiVal = row.dii_net_cr ?? 0;
                    const totVal = row.total_net_cr ?? (fiiVal + diiVal);
                    const fiiSign = fiiVal >= 0 ? '+' : '';
                    const diiSign = diiVal >= 0 ? '+' : '';
                    const totSign = totVal >= 0 ? '+' : '';
                    const fiiCol = fiiVal >= 0 ? '#34d399' : '#f87171';
                    const diiCol = diiVal >= 0 ? '#34d399' : '#f87171';
                    const totCol = totVal >= 0 ? '#38bdf8' : '#f87171';
                    const isBull = totVal >= 0;
                    const badgeCol = isBull ? '#34d399' : '#f87171';
                    const badgeBg = isBull ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)';
                    const badgeText = isBull ? '🟢 Inflow' : '🔴 Outflow';

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);background:${rowBg};">
                            <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);font-weight:${isToday ? '700' : '500'};color:${isToday ? '#f8fafc' : '#cbd5e1'};">
                                ${row.day_label || row.date}
                            </td>
                            <td style="padding:0.35rem 0.5rem;text-align:right;font-family:var(--font-mono);color:${fiiCol};font-weight:600;">
                                ${fiiSign}₹${fiiVal.toLocaleString()}
                            </td>
                            <td style="padding:0.35rem 0.5rem;text-align:right;font-family:var(--font-mono);color:${diiCol};font-weight:600;">
                                ${diiSign}₹${diiVal.toLocaleString()}
                            </td>
                            <td style="padding:0.35rem 0.5rem;text-align:right;font-family:var(--font-mono);color:${totCol};font-weight:700;">
                                ${totSign}₹${totVal.toLocaleString()}
                            </td>
                            <td style="padding:0.35rem 0.5rem;text-align:center;">
                                <span style="font-size:0.6rem;padding:0.1rem 0.35rem;border-radius:3px;background:${badgeBg};color:${badgeCol};font-weight:700;font-family:var(--font-mono);">
                                    ${badgeText}
                                </span>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        },

        toggleFlowHistory() {
            this._isFlowHistoryExpanded = !this._isFlowHistoryExpanded;
            if (window.app) window.app._isFlowHistoryExpanded = this._isFlowHistoryExpanded;
            const flows = this._lastFlowsData
                || (window.app && window.app._lastFlowsData)
                || this.pulseData?.institutional_flows
                || (window.app && window.app.pulseData?.institutional_flows)
                || {};
            this.renderInstitutionalFlows(flows);
        },

        renderParticipantOI(oiData) {
            this._lastOiData = oiData;
            const tableBody = document.getElementById('pulseParticipantOiTableBody');
            const historyBody = document.getElementById('pulseParticipantOiHistoryTableBody');
            const badgeEl = document.getElementById('pulseOiRegimeBadge');
            const sessionSub = document.getElementById('pulseOiSessionSub');
            const commentaryEl = document.getElementById('pulseOiCommentary');

            if (!oiData || (!oiData.participants && !oiData.history_7d)) {
                if (tableBody) {
                    tableBody.innerHTML = `
                        <tr>
                            <td colspan="7" style="padding:1rem;text-align:center;color:#64748b;font-size:0.75rem;">
                                Participant derivatives positioning data loading...
                            </td>
                        </tr>
                    `;
                }
                return;
            }

            if (sessionSub && oiData.session_label) {
                sessionSub.textContent = `As of ${oiData.session_label} · Multi-Participant Derivatives Breakdown (FII vs DII vs Pro vs Retail)`;
            }

            if (badgeEl && oiData.regime_verdict) {
                badgeEl.textContent = oiData.regime_verdict;
                if (oiData.regime_sentiment === 'BULLISH_CONVERGENCE') {
                    badgeEl.style.background = 'rgba(16,185,129,0.15)';
                    badgeEl.style.color = '#34d399';
                    badgeEl.style.borderColor = 'rgba(16,185,129,0.3)';
                } else if (oiData.regime_sentiment === 'BEARISH_DIVERGENCE') {
                    badgeEl.style.background = 'rgba(239,68,68,0.15)';
                    badgeEl.style.color = '#f87171';
                    badgeEl.style.borderColor = 'rgba(239,68,68,0.3)';
                } else {
                    badgeEl.style.background = 'rgba(249,115,22,0.15)';
                    badgeEl.style.color = '#fb923c';
                    badgeEl.style.borderColor = 'rgba(249,115,22,0.3)';
                }
            }

            if (commentaryEl && oiData.commentary) {
                commentaryEl.textContent = oiData.commentary;
            }

            // Render 1D Snapshot Table
            if (tableBody && oiData.participants && oiData.participants.length) {
                tableBody.innerHTML = oiData.participants.map(p => {
                    const netVal = p.net_contracts || 0;
                    const netCol = netVal > 0 ? '#34d399' : (netVal < 0 ? '#f87171' : '#94a3b8');
                    const netSign = netVal > 0 ? '+' : '';
                    
                    const lsRatio = p.long_short_ratio || 1.0;
                    let lsCol = '#94a3b8';
                    let lsBg = 'rgba(255,255,255,0.05)';
                    if (lsRatio >= 1.25) {
                        lsCol = '#34d399';
                        lsBg = 'rgba(16,185,129,0.12)';
                    } else if (lsRatio <= 0.85) {
                        lsCol = '#f87171';
                        lsBg = 'rgba(239,68,68,0.12)';
                    }

                    const stance = p.stance || 'Balanced';
                    let stanceBg = 'rgba(255,255,255,0.04)';
                    let stanceCol = '#cbd5e1';
                    if (stance.includes('🟢') || stance.includes('Long')) {
                        stanceBg = 'rgba(16,185,129,0.1)';
                        stanceCol = '#34d399';
                    } else if (stance.includes('🔴') || stance.includes('Short')) {
                        stanceBg = 'rgba(239,68,68,0.1)';
                        stanceCol = '#f87171';
                    }

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:0.45rem 0.6rem;text-align:left;font-weight:700;color:#f8fafc;">
                                ${p.category_label || p.participant}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#cbd5e1;">
                                <span style="color:#34d399;">${(p.futures_long || 0).toLocaleString()}</span> / <span style="color:#f87171;">${(p.futures_short || 0).toLocaleString()}</span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#cbd5e1;">
                                <span style="color:#34d399;">${(p.calls_long || 0).toLocaleString()}</span> / <span style="color:#f87171;">${(p.calls_short || 0).toLocaleString()}</span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#cbd5e1;">
                                <span style="color:#34d399;">${(p.puts_long || 0).toLocaleString()}</span> / <span style="color:#f87171;">${(p.puts_short || 0).toLocaleString()}</span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:${netCol};">
                                ${netSign}${netVal.toLocaleString()}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:center;">
                                <span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:${lsBg};color:${lsCol};font-weight:800;font-family:var(--font-mono);border:1px solid ${lsCol}33;">
                                    ${lsRatio.toFixed(2)}x (${(p.long_pct || 50).toFixed(0)}% L)
                                </span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:left;">
                                <span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:${stanceBg};color:${stanceCol};font-weight:600;font-family:var(--font-mono);">
                                    ${stance}
                                </span>
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            // Render 7-Day History Matrix Table
            if (historyBody && oiData.history_7d && oiData.history_7d.length) {
                historyBody.innerHTML = oiData.history_7d.map((row, idx) => {
                    const isToday = idx === 0;
                    const rowBg = isToday ? 'rgba(56,189,248,0.06)' : 'transparent';
                    
                    const fNet = row.fii_net_contracts || 0;
                    const fSign = fNet >= 0 ? '+' : '';
                    const fCol = fNet >= 0 ? '#34d399' : '#f87171';
                    const fRatio = row.fii_long_short_ratio || 1.0;

                    const dNet = row.dii_net_contracts || 0;
                    const dSign = dNet >= 0 ? '+' : '';
                    const dCol = dNet >= 0 ? '#34d399' : '#f87171';
                    const dRatio = row.dii_long_short_ratio || 1.0;

                    const pNet = row.pro_net_contracts || 0;
                    const pSign = pNet >= 0 ? '+' : '';
                    const pCol = pNet >= 0 ? '#34d399' : '#f87171';
                    const pRatio = row.pro_long_short_ratio || 1.0;

                    const cNet = row.client_net_contracts || 0;
                    const cSign = cNet >= 0 ? '+' : '';
                    const cCol = cNet >= 0 ? '#34d399' : '#f87171';
                    const cRatio = row.client_long_short_ratio || 1.0;

                    const isFiiLong = fNet >= 0;
                    const biasText = isFiiLong ? '🟢 FII Long Bias' : '🔴 FII Short Hedge';
                    const biasBg = isFiiLong ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)';
                    const biasCol = isFiiLong ? '#34d399' : '#f87171';

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);background:${rowBg};">
                            <td style="padding:0.45rem 0.6rem;font-family:var(--font-mono);font-weight:${isToday ? '700' : '500'};color:${isToday ? '#f8fafc' : '#cbd5e1'};">
                                ${row.session_label || row.date}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${fCol};font-weight:600;">
                                ${fSign}${fNet.toLocaleString()} <span style="font-size:0.62rem;color:#94a3b8;">(${fRatio.toFixed(2)}x)</span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${dCol};font-weight:600;">
                                ${dSign}${dNet.toLocaleString()} <span style="font-size:0.62rem;color:#94a3b8;">(${dRatio.toFixed(2)}x)</span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${pCol};font-weight:600;">
                                ${pSign}${pNet.toLocaleString()} <span style="font-size:0.62rem;color:#94a3b8;">(${pRatio.toFixed(2)}x)</span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${cCol};font-weight:600;">
                                ${cSign}${cNet.toLocaleString()} <span style="font-size:0.62rem;color:#94a3b8;">(${cRatio.toFixed(2)}x)</span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:center;">
                                <span style="font-size:0.62rem;padding:0.12rem 0.4rem;border-radius:3px;background:${biasBg};color:${biasCol};font-weight:700;font-family:var(--font-mono);">
                                    ${biasText}
                                </span>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        },

        toggleParticipantOiView() {
            this._isOiHistoryView = !this._isOiHistoryView;
            const snapContainer = document.getElementById('pulseOiSnapshotContainer');
            const histContainer = document.getElementById('pulseOiHistoryContainer');
            const btn = document.getElementById('btnToggleOiView');

            if (snapContainer && histContainer) {
                if (this._isOiHistoryView) {
                    snapContainer.style.display = 'none';
                    histContainer.style.display = 'block';
                    if (btn) btn.innerHTML = '📊 1D Snapshot View';
                } else {
                    snapContainer.style.display = 'block';
                    histContainer.style.display = 'none';
                    if (btn) btn.innerHTML = '📅 Past 7 Days Matrix';
                }
            }
        },

        renderSectors(sectors) {
            const grid = document.getElementById('pulseSectorsGrid');
            if (!grid) return;

            if (!sectors || !sectors.length) {
                grid.innerHTML = '<div style="color:#64748b;font-size:0.75rem;">Sector data loading...</div>';
                return;
            }

            grid.innerHTML = sectors.map(s => {
                const isPos = s.change_1d >= 0;
                const col = isPos ? '#34d399' : '#f87171';
                const sign1d = s.change_1d >= 0 ? '+' : '';
                const sign7d = s.change_7d >= 0 ? '+' : '';
                const sign30d = s.change_30d >= 0 ? '+' : '';

                return `
                    <div style="background:#060a16;border:1px solid rgba(255,255,255,0.06);border-left:3px solid ${col};border-radius:6px;padding:0.55rem 0.75rem;display:flex;flex-direction:column;gap:0.25rem;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:0.75rem;font-weight:700;color:#f8fafc;">${s.name}</span>
                            <span style="font-size:0.75rem;font-weight:800;color:${col};font-family:var(--font-mono);">${sign1d}${s.change_1d}%</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:#94a3b8;font-family:var(--font-mono);">
                            <span>7D: <strong style="color:${s.change_7d >= 0 ? '#34d399' : '#f87171'};">${sign7d}${s.change_7d}%</strong></span>
                            <span>30D: <strong style="color:${s.change_30d >= 0 ? '#34d399' : '#f87171'};">${sign30d}${s.change_30d}%</strong></span>
                        </div>
                    </div>
                `;
            }).join('');
        },

        renderMacroCharts(charts) {
            if (!charts) return;

            // 1. Fear & Greed 30D Trend Wave Chart
            const fgSeries = charts.fear_greed || [];
            if (fgSeries.length) {
                this.drawSparklineChart('chartFearGreed', fgSeries.map(x => x.score), {
                    color: '#34d399',
                    gradientFrom: 'rgba(52, 211, 153, 0.25)',
                    gradientTo: 'rgba(52, 211, 153, 0.0)',
                    minVal: 0,
                    maxVal: 100,
                    referenceLines: [25, 50, 75],
                    refLineColors: ['rgba(244,63,94,0.3)', 'rgba(251,191,36,0.3)', 'rgba(16,185,129,0.3)'],
                });
            }

            // 2. India VIX Volatility Corridor Chart
            const vixSeries = charts.vix || [];
            if (vixSeries.length) {
                this.drawSparklineChart('chartVix', vixSeries.map(x => x.value), {
                    color: '#38bdf8',
                    gradientFrom: 'rgba(56, 189, 248, 0.25)',
                    gradientTo: 'rgba(56, 189, 248, 0.0)',
                    referenceLines: [15, 20],
                    refLineColors: ['rgba(52,211,153,0.3)', 'rgba(248,113,113,0.3)'],
                });
            }

            // 3. NIFTY 50 Benchmark Trajectory Chart
            const niftySeries = charts.nifty || [];
            if (niftySeries.length) {
                this.drawSparklineChart('chartNifty', niftySeries.map(x => x.value), {
                    color: '#818cf8',
                    gradientFrom: 'rgba(129, 140, 248, 0.25)',
                    gradientTo: 'rgba(129, 140, 248, 0.0)',
                });
            }
        },

        drawSparklineChart(canvasId, values, options = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas || !values || values.length < 2) return;

            const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: 300, height: 100 };
            const dpr = window.devicePixelRatio || 1;
            const w = rect.width || 300;
            const h = rect.height || 100;

            canvas.width = w * dpr;
            canvas.height = h * dpr;
            const ctx = canvas.getContext('2d');
            ctx.scale(dpr, dpr);

            ctx.clearRect(0, 0, w, h);

            const minVal = options.minVal !== undefined ? options.minVal : Math.min(...values) * 0.98;
            const maxVal = options.maxVal !== undefined ? options.maxVal : Math.max(...values) * 1.02;
            const valRange = maxVal - minVal || 1.0;

            const padding = 6;
            const drawW = w - padding * 2;
            const drawH = h - padding * 2;

            // Draw Reference Lines
            if (options.referenceLines) {
                options.referenceLines.forEach((ref, idx) => {
                    if (ref >= minVal && ref <= maxVal) {
                        const y = padding + drawH - ((ref - minVal) / valRange) * drawH;
                        ctx.beginPath();
                        ctx.strokeStyle = (options.refLineColors && options.refLineColors[idx]) || 'rgba(255,255,255,0.1)';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([3, 3]);
                        ctx.moveTo(padding, y);
                        ctx.lineTo(w - padding, y);
                        ctx.stroke();
                        ctx.setLineDash([]);
                    }
                });
            }

            // Calculate points
            const points = values.map((v, i) => {
                const x = padding + (i / (values.length - 1)) * drawW;
                const y = padding + drawH - ((v - minVal) / valRange) * drawH;
                return { x, y, v };
            });

            // Fill Area Gradient
            const gradient = ctx.createLinearGradient(0, padding, 0, h - padding);
            gradient.addColorStop(0, options.gradientFrom || 'rgba(56,189,248,0.25)');
            gradient.addColorStop(1, options.gradientTo || 'rgba(56,189,248,0.0)');

            ctx.beginPath();
            ctx.moveTo(points[0].x, points[0].y);
            for (let i = 1; i < points.length; i++) {
                const prev = points[i - 1];
                const curr = points[i];
                const cpX = (prev.x + curr.x) / 2;
                ctx.bezierCurveTo(cpX, prev.y, cpX, curr.y, curr.x, curr.y);
            }
            ctx.lineTo(points[points.length - 1].x, h - padding);
            ctx.lineTo(points[0].x, h - padding);
            ctx.closePath();
            ctx.fillStyle = gradient;
            ctx.fill();

            // Stroke Line
            ctx.beginPath();
            ctx.moveTo(points[0].x, points[0].y);
            for (let i = 1; i < points.length; i++) {
                const prev = points[i - 1];
                const curr = points[i];
                const cpX = (prev.x + curr.x) / 2;
                ctx.bezierCurveTo(cpX, prev.y, cpX, curr.y, curr.x, curr.y);
            }
            ctx.strokeStyle = options.color || '#38bdf8';
            ctx.lineWidth = 2.0;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.stroke();

            // Glowing Last Point
            const last = points[points.length - 1];
            ctx.beginPath();
            ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
            ctx.fillStyle = options.color || '#38bdf8';
            ctx.shadowColor = options.color || '#38bdf8';
            ctx.shadowBlur = 8;
            ctx.fill();
            ctx.shadowBlur = 0;
        },

        async loadConfluenceSetups(forceRefresh = false) {
            const tbody = document.getElementById('pulseConfluenceTableBody');
            if (!tbody) return;

            try {
                const res = await fetch(API_BASE + '/api/v1/dashboard/confluence?min_level=1&limit=20');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const setups = data.setups || [];

                if (!setups.length) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="7" style="text-align:center;padding:1.25rem;color:#94a3b8;">
                                🛡️ No multi-strategy confluence setups currently active. All engines operating normally.
                            </td>
                        </tr>
                    `;
                    return;
                }

                tbody.innerHTML = setups.map(s => {
                    const sym = s.ticker || '';
                    const cleanSym = sym.replace('.NS', '');
                    const badgeBg = s.confluence_level >= 3 ? 'rgba(244,63,94,0.2)' : (s.confluence_level >= 2 ? 'rgba(56,189,248,0.2)' : 'rgba(16,185,129,0.15)');
                    const badgeColor = s.badge_color || '#38bdf8';

                    const breakoutCell = s.breakout_tier === 'HOT' 
                        ? `<span class="signal-badge" style="background:rgba(244,63,94,0.15);color:#fb7185;font-size:0.65rem;">🔥 HOT Breakout</span>`
                        : (s.breakout_tier === 'WARM' ? `<span class="signal-badge" style="background:rgba(251,191,36,0.15);color:#fbbf24;font-size:0.65rem;">⚡ Coiling (Warm)</span>` : `<span style="color:#64748b;">—</span>`);

                    const swingCell = s.is_swing_buy 
                        ? `<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-size:0.65rem;">🎯 Buy Zone Floor</span>`
                        : (s.swing_tier === 'WARM' ? `<span style="color:#fbbf24;font-size:0.68rem;">Channel Compression</span>` : `<span style="color:#64748b;">—</span>`);

                    const aiCell = s.is_ai_buy
                        ? `<span class="signal-badge" style="background:rgba(168,85,247,0.15);color:#c084fc;font-size:0.65rem;">🤖 ${s.ai_direction} (${s.ai_strength}%)</span>`
                        : `<span style="color:#94a3b8;font-size:0.68rem;">${s.ai_direction || 'Neutral'}</span>`;

                    const news = s.news || {};
                    const newsCell = news.has_news
                        ? `<span style="color:${news.badge_color || '#34d399'};font-size:0.68rem;font-weight:600;">${news.badge_text}</span>`
                        : `<span style="color:#64748b;font-size:0.68rem;">No Filings (7D)</span>`;

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.45rem 0.6rem;">
                                <a href="/stock/${encodeURIComponent(sym)}" style="font-weight:800;color:#f8fafc;text-decoration:none;font-family:var(--font-mono);font-size:0.80rem;">
                                    ${cleanSym}
                                </a>
                            </td>
                            <td style="padding:0.45rem 0.6rem;">
                                <span class="signal-badge" style="background:${badgeBg};color:${badgeColor};font-size:0.68rem;border:1px solid ${badgeColor}40;">
                                    ${s.confluence_badge}
                                </span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;">${breakoutCell}</td>
                            <td style="padding:0.45rem 0.6rem;">${swingCell}</td>
                            <td style="padding:0.45rem 0.6rem;">${aiCell}</td>
                            <td style="padding:0.45rem 0.6rem;">${newsCell}</td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;">
                                <button type="button" onclick="window.location.href='/stock/${encodeURIComponent(sym)}'" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.2rem 0.45rem;">
                                    Deep Dive ➔
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (e) {
                console.error('[CONFLUENCE] Error loading confluence setups:', e);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align:center;padding:1rem;color:#f87171;">
                            ⚠️ Error syncing cross-strategy confluence setups: ${e.message}
                        </td>
                    </tr>
                `;
            }
        }
    };

    window.marketPulseModule = marketPulseModule;
    window.app.marketPulse = marketPulseModule;
    Object.assign(window.app, marketPulseModule);
})();
