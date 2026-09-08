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
        _isOiHistoryView: false,
        _lastFlowsData: null,
        _lastOiData: null,
        _glossaryData: null,
        _currentGlossaryCategory: 'all',
        _currentGlossarySearch: '',

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
                if (data.metric_glossary) {
                    this._glossaryData = data.metric_glossary;
                }
                if (window.app) {
                    window.app.pulseData = data;
                    window.app._pulseLoaded = true;
                    if (data.metric_glossary) {
                        window.app._glossaryData = data.metric_glossary;
                    }
                }

                if (timeEl) {
                    const now = new Date();
                    timeEl.textContent = 'Updated: ' + now.toLocaleTimeString();
                }
                if (badgeEl) badgeEl.textContent = '● LIVE TICK';

                this.renderIndices(data.indices || []);
                this.renderNextDayPlaybook(data.next_day_playbook || {});
                this.renderFearAndGreed(data.fear_and_greed || {});
                this.renderVolatility(data.volatility || {});
                this.renderPrediction(data.prediction || {});
                this.renderBreadth(data.breadth || {});
                this.renderInstitutionalFlows(data.institutional_flows || {});
                this.renderParticipantOI(data.participant_oi || {});
                this.renderSectors(data.sectors || []);
                this.renderMacroCharts(data.macro_charts || {}, data.participant_oi || {});
                // Note: Confluence setups are loaded on-demand via user trigger

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
                                    ${(idx.current_price || 0).toLocaleString()}
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

        // =====================================================================
        // 🎯 1.5. Next-Day Actionable Strategy Playbook Renderer
        // =====================================================================
        renderNextDayPlaybook(pb) {
            if (!pb || Object.keys(pb).length === 0) return;

            const biasBadge = document.getElementById('pulsePlaybookBiasBadge');
            const headlineEl = document.getElementById('pulsePlaybookHeadline');
            const confPill = document.getElementById('pulsePlaybookConfluencePill');
            const vixTag = document.getElementById('pulsePlaybookVixTag');
            const spotEl = document.getElementById('pulsePlaybookNiftySpot');
            const expMoveEl = document.getElementById('pulsePlaybookExpectedMove');
            const sigma1El = document.getElementById('pulsePlaybook1SigmaRange');
            const sigma2El = document.getElementById('pulsePlaybook2SigmaRange');
            const thetaEnvEl = document.getElementById('pulsePlaybookThetaEnv');
            const divBadge = document.getElementById('pulsePlaybookDivergenceBadge');
            const fiiLsEl = document.getElementById('pulsePlaybookFiiLs');
            const clientLsEl = document.getElementById('pulsePlaybookClientLs');
            const trapWarnEl = document.getElementById('pulsePlaybookTrapWarning');
            const trapScoreEl = document.getElementById('pulsePlaybookTrapScore');
            const divDeltaEl = document.getElementById('pulsePlaybookDivDelta');
            const rulesContainer = document.getElementById('pulsePlaybookRulesContainer');
            const focusSectorsEl = document.getElementById('pulsePlaybookFocusSectors');

            // Bias Badge & Colors
            if (biasBadge) {
                const label = pb.bias_label || (pb.bias ? pb.bias.replace(/_/g, ' ') : 'Neutral Stance');
                biasBadge.textContent = label;
                const bias = (pb.bias || '').toUpperCase();
                if (bias.includes('BULLISH') || bias.includes('ACCUMULATION')) {
                    biasBadge.style.background = 'rgba(52,211,153,0.18)';
                    biasBadge.style.color = '#34d399';
                    biasBadge.style.borderColor = 'rgba(52,211,153,0.35)';
                } else if (bias.includes('BEARISH') || bias.includes('DEFENSIVE') || bias.includes('SELL')) {
                    biasBadge.style.background = 'rgba(239,68,68,0.18)';
                    biasBadge.style.color = '#f87171';
                    biasBadge.style.borderColor = 'rgba(239,68,68,0.35)';
                } else {
                    biasBadge.style.background = 'rgba(251,191,36,0.18)';
                    biasBadge.style.color = '#fbbf24';
                    biasBadge.style.borderColor = 'rgba(251,191,36,0.35)';
                }
            }

            if (headlineEl && pb.headline) {
                headlineEl.textContent = pb.headline;
            }

            if (confPill && pb.confluence_score !== undefined) {
                const s = pb.confluence_score >= 0 ? '+' : '';
                confPill.textContent = `Confluence: ${s}${pb.confluence_score}/100`;
                if (pb.confluence_score >= 20) {
                    confPill.style.color = '#34d399';
                    confPill.style.background = 'rgba(52,211,153,0.15)';
                    confPill.style.borderColor = 'rgba(52,211,153,0.3)';
                } else if (pb.confluence_score <= -20) {
                    confPill.style.color = '#f87171';
                    confPill.style.background = 'rgba(239,68,68,0.15)';
                    confPill.style.borderColor = 'rgba(239,68,68,0.3)';
                }
            }

            // Column 1: Volatility & Corridor
            if (vixTag && pb.vix_level != null) {
                vixTag.textContent = `VIX: ${pb.vix_level}`;
            }
            if (spotEl && pb.nifty_spot) {
                spotEl.textContent = Number(pb.nifty_spot).toLocaleString();
            }
            if (expMoveEl) {
                const pts = pb.expected_1d_move_pts ?? pb.expected_1d_range_pts ?? pb.corridor?.expected_1d_move_pts ?? pb.corridor?.expected_1d_range_pts ?? 0;
                const pct = pb.expected_1d_move_pct ?? pb.expected_1d_range_pct ?? pb.corridor?.expected_1d_move_pct ?? pb.corridor?.expected_1d_range_pct ?? 0;
                expMoveEl.textContent = `±${pct}% (±${pts} Pts)`;
            }
            if (sigma1El) {
                const low = pb.corridor?.lower_band_1sigma ?? pb.corridor?.lower_1sigma ?? pb.lower_band_1sigma ?? 0;
                const high = pb.corridor?.upper_band_1sigma ?? pb.corridor?.upper_1sigma ?? pb.upper_band_1sigma ?? 0;
                sigma1El.textContent = `${Number(low).toLocaleString()} – ${Number(high).toLocaleString()}`;
            }
            if (sigma2El) {
                const low = pb.corridor?.lower_band_2sigma ?? pb.corridor?.lower_2sigma ?? pb.lower_band_2sigma ?? 0;
                const high = pb.corridor?.upper_band_2sigma ?? pb.corridor?.upper_2sigma ?? pb.upper_band_2sigma ?? 0;
                sigma2El.textContent = `${Number(low).toLocaleString()} – ${Number(high).toLocaleString()}`;
            }
            if (thetaEnvEl) {
                const env = pb.theta_env_label || pb.theta_environment || pb.theta_decay_environment || '';
                if (env) {
                    thetaEnvEl.textContent = env.replace(/_/g, ' ');
                    if (env.includes('Selling') || env.includes('Decay') || env.includes('SELLING')) {
                        thetaEnvEl.style.background = 'rgba(16,185,129,0.12)';
                        thetaEnvEl.style.color = '#34d399';
                        thetaEnvEl.style.borderColor = 'rgba(16,185,129,0.25)';
                    } else if (env.includes('Buying') || env.includes('Expansion') || env.includes('BUYING')) {
                        thetaEnvEl.style.background = 'rgba(56,189,248,0.12)';
                        thetaEnvEl.style.color = '#38bdf8';
                        thetaEnvEl.style.borderColor = 'rgba(56,189,248,0.25)';
                    } else {
                        thetaEnvEl.style.background = 'rgba(251,191,36,0.12)';
                        thetaEnvEl.style.color = '#fbbf24';
                        thetaEnvEl.style.borderColor = 'rgba(251,191,36,0.25)';
                    }
                }
            }

            // Column 2: Divergence
            const sm = pb.smart_money_vs_retail || pb.divergence || {};
            if (divBadge) {
                divBadge.textContent = sm.badge || sm.status || 'Balanced';
                const st = (sm.status || sm.badge || '').toUpperCase();
                if (st.includes('BULLISH')) {
                    divBadge.style.color = '#34d399';
                } else if (st.includes('BEARISH')) {
                    divBadge.style.color = '#f87171';
                } else {
                    divBadge.style.color = '#38bdf8';
                }
            }
            const fiiRatio = sm.fii_ls_ratio ?? sm.fii_ls ?? 1.0;
            const clientRatio = sm.client_ls_ratio ?? sm.client_ls ?? 1.0;
            if (fiiLsEl) {
                fiiLsEl.textContent = `${Number(fiiRatio).toFixed(2)}x`;
                fiiLsEl.style.color = fiiRatio >= 1.0 ? '#34d399' : '#f87171';
            }
            if (clientLsEl) {
                clientLsEl.textContent = `${Number(clientRatio).toFixed(2)}x`;
                clientLsEl.style.color = clientRatio >= 1.0 ? '#fb923c' : '#94a3b8';
            }
            const trapWarning = sm.trap_warning || sm.warning;
            if (trapWarnEl && trapWarning) {
                trapWarnEl.textContent = trapWarning;
            }
            if (trapScoreEl) {
                const score = sm.trap_risk_score !== undefined ? sm.trap_risk_score : 35;
                const label = sm.trap_risk_label || (score > 60 ? 'High' : score > 35 ? 'Moderate' : 'Low');
                trapScoreEl.textContent = `${score}/100 (${label})`;
                trapScoreEl.style.color = score > 60 ? '#f87171' : score > 35 ? '#fbbf24' : '#34d399';
            }
            const divDelta = sm.divergence_delta !== undefined ? sm.divergence_delta : (fiiRatio - clientRatio);
            if (divDeltaEl && divDelta !== undefined && divDelta !== null) {
                const s = divDelta >= 0 ? '+' : '';
                divDeltaEl.textContent = `${s}${Number(divDelta).toFixed(2)}`;
                divDeltaEl.style.color = divDelta >= 0 ? '#34d399' : '#f87171';
            }

            // Column 3: Rules
            if (rulesContainer && pb.actionable_rules && pb.actionable_rules.length) {
                rulesContainer.innerHTML = pb.actionable_rules.map(rule => {
                    let icon = '📌';
                    if (rule.startsWith('Primary') || rule.startsWith('1.')) icon = '🎯';
                    else if (rule.startsWith('Option') || rule.startsWith('2.')) icon = '⚡';
                    else if (rule.startsWith('Invalidation') || rule.startsWith('3.')) icon = '🛑';
                    return `<div>${icon} ${rule}</div>`;
                }).join('');
            }

            // Focus Sectors
            if (focusSectorsEl && pb.focus_sectors) {
                if (Array.isArray(pb.focus_sectors) && pb.focus_sectors.length) {
                    focusSectorsEl.textContent = pb.focus_sectors.join(', ');
                } else if (typeof pb.focus_sectors === 'string') {
                    focusSectorsEl.textContent = pb.focus_sectors;
                }
            }
        },

        renderFearAndGreed(fg) {
            const scoreEl = document.getElementById('pulseFgScore');
            const badgeEl = document.getElementById('pulseFgBadge');
            const barEl = document.getElementById('pulseFgBar');
            const descEl = document.getElementById('pulseFgDesc');
            const momEl = document.getElementById('pulseFgMom');
            const vixEl = document.getElementById('pulseFgVix');
            const breadthEl = document.getElementById('pulseFgBreadth');
            const deltaEl = document.getElementById('pulseFgDelta');

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
            if (deltaEl && fg.change_7d != null) {
                const s = fg.change_7d >= 0 ? '+' : '';
                deltaEl.textContent = `${s}${fg.change_7d} (7D)`;
                deltaEl.style.color = fg.change_7d >= 0 ? '#34d399' : '#f87171';
            }
        },

        renderVolatility(vix) {
            const levelEl = document.getElementById('pulseVixLevel');
            const changeEl = document.getElementById('pulseVixChange');
            const badgeEl = document.getElementById('pulseVixRegimeBadge');
            const descEl = document.getElementById('pulseVixDesc');
            const stanceEl = document.getElementById('pulseVixStance');

            if (levelEl) levelEl.textContent = vix.vix_level != null ? vix.vix_level : '13.8';
            if (changeEl && vix.change_1d != null) {
                const s = vix.change_1d >= 0 ? '+' : '';
                changeEl.textContent = `${s}${vix.change_1d}% 1D`;
                changeEl.style.color = vix.change_1d <= 0 ? '#34d399' : '#f87171';
            }
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
            const niftyLvl = document.getElementById('pulseNiftyLevel');
            const niftyChg = document.getElementById('pulseNiftyChange');

            if (regimeEl && pred.regime) regimeEl.textContent = pred.regime;
            if (commEl && pred.commentary) commEl.textContent = pred.commentary;
            if (convPill && pred.conviction_pct) convPill.textContent = `${pred.conviction_pct}% CONVICTION`;
            if (supEl && pred.nifty_support) supEl.textContent = pred.nifty_support;
            if (resEl && pred.nifty_resistance) resEl.textContent = pred.nifty_resistance;
            if (niftyLvl && pred.nifty_spot) niftyLvl.textContent = (pred.nifty_spot).toLocaleString();
            if (niftyChg && pred.nifty_change_1d != null) {
                const s = pred.nifty_change_1d >= 0 ? '+' : '';
                niftyChg.textContent = `${s}${pred.nifty_change_1d}% 1D`;
                niftyChg.style.color = pred.nifty_change_1d >= 0 ? '#34d399' : '#f87171';
            }
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

        // =====================================================================
        // 🏛️ Enhanced Participant Derivatives OI & Long/Short Matrix
        // =====================================================================
        renderParticipantOI(oiData) {
            this._lastOiData = oiData;
            const tableBody = document.getElementById('pulseParticipantOiTableBody');
            const historyBody = document.getElementById('pulseParticipantOiHistoryTableBody');
            const badgeEl = document.getElementById('pulseOiRegimeBadge');
            const sessionSub = document.getElementById('pulseOiSessionSub');
            const commentaryEl = document.getElementById('pulseOiCommentary');

            if (!oiData || (!oiData.participants && !oiData.history_10d && !oiData.history_7d)) {
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

                    const deltaVal = p.delta_net_contracts !== undefined ? p.delta_net_contracts : null;
                    let deltaStr = '';
                    if (deltaVal !== null) {
                        const dSign = deltaVal >= 0 ? '+' : '';
                        const dCol = deltaVal >= 0 ? '#34d399' : '#f87171';
                        deltaStr = `<div style="font-size:0.62rem;color:${dCol};font-weight:600;">Δ ${dSign}${deltaVal.toLocaleString()}</div>`;
                    }

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
                    const shiftRegime = p.shift_regime || stance;
                    let stanceBg = 'rgba(255,255,255,0.04)';
                    let stanceCol = '#cbd5e1';
                    if (shiftRegime.includes('🟢') || shiftRegime.includes('Long') || shiftRegime.includes('Covering')) {
                        stanceBg = 'rgba(16,185,129,0.1)';
                        stanceCol = '#34d399';
                    } else if (shiftRegime.includes('🔴') || shiftRegime.includes('Short') || shiftRegime.includes('Unwinding')) {
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
                                <div>${netSign}${netVal.toLocaleString()}</div>
                                ${deltaStr}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:center;">
                                <span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:${lsBg};color:${lsCol};font-weight:800;font-family:var(--font-mono);border:1px solid ${lsCol}33;">
                                    ${lsRatio.toFixed(2)}x (${(p.long_pct || 50).toFixed(0)}% L)
                                </span>
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:left;">
                                <span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:${stanceBg};color:${stanceCol};font-weight:600;font-family:var(--font-mono);">
                                    ${shiftRegime}
                                </span>
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            // Render 10-Day History Matrix Table
            const history = oiData.history_10d || oiData.history_7d || [];
            if (historyBody && history.length) {
                historyBody.innerHTML = history.map((row, idx) => {
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

                    const shiftRegime = row.fii_shift_regime || row.shift_regime || (fNet >= 0 ? '🟢 FII Long Bias' : '🔴 FII Short Hedge');
                    let biasBg = 'rgba(52,211,153,0.12)';
                    let biasCol = '#34d399';
                    if (shiftRegime.includes('🔴') || shiftRegime.includes('Short') || shiftRegime.includes('Unwinding')) {
                        biasBg = 'rgba(248,113,113,0.12)';
                        biasCol = '#f87171';
                    } else if (shiftRegime.includes('🚀') || shiftRegime.includes('Covering')) {
                        biasBg = 'rgba(56,189,248,0.12)';
                        biasCol = '#38bdf8';
                    }

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
                                    ${shiftRegime}
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
                    if (btn) btn.innerHTML = '📅 Past 10 Days Matrix';
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

        // =====================================================================
        // 📈 Macro Charts Rendering (5-Chart Grid)
        // =====================================================================
        renderMacroCharts(charts, participantOi = {}) {
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

            // 4. Participant OI 10D Net Contracts Trajectory (Multi-Line)
            const oiHistory = (participantOi && (participantOi.history_10d || participantOi.history_7d))
                || charts.participant_oi_history
                || [];

            if (oiHistory.length >= 2) {
                const chronological = [...oiHistory].reverse();
                const fiiSeries = chronological.map(x => x.fii_net_contracts || 0);
                const proSeries = chronological.map(x => x.pro_net_contracts || 0);
                const clientSeries = chronological.map(x => x.client_net_contracts || 0);

                this.drawMultiLineChart('chartParticipantOi', [
                    { name: 'FII', values: fiiSeries, color: '#34d399' },
                    { name: 'PRO', values: proSeries, color: '#818cf8' },
                    { name: 'CLIENT', values: clientSeries, color: '#fb923c' }
                ], { showZeroLine: true });

                const latestFii = oiHistory[0]?.fii_net_contracts ?? 0;
                const fiiBadge = document.getElementById('pulseParticipantOiChartBadge');
                const fiiPill = document.getElementById('pulseFiiNetContractsPill');
                if (fiiBadge) {
                    fiiBadge.textContent = latestFii >= 0 ? 'FII Net Long' : 'FII Net Short';
                    fiiBadge.style.color = latestFii >= 0 ? '#34d399' : '#f87171';
                    fiiBadge.style.background = latestFii >= 0 ? 'rgba(52,211,153,0.15)' : 'rgba(248,113,113,0.15)';
                }
                if (fiiPill) {
                    const s = latestFii >= 0 ? '+' : '';
                    fiiPill.textContent = `${s}${latestFii.toLocaleString()}`;
                    fiiPill.style.color = latestFii >= 0 ? '#34d399' : '#f87171';
                }
            }

            // 5. FII Long/Short Ratio Oscillator
            if (oiHistory.length >= 2) {
                const chronological = [...oiHistory].reverse();
                const fiiLsSeries = chronological.map(x => x.fii_long_short_ratio || 1.0);
                this.drawSparklineChart('chartFiiLsRatio', fiiLsSeries, {
                    color: '#38bdf8',
                    gradientFrom: 'rgba(56, 189, 248, 0.25)',
                    gradientTo: 'rgba(56, 189, 248, 0.0)',
                    referenceLines: [0.85, 1.0, 1.25],
                    refLineColors: ['rgba(244,63,94,0.4)', 'rgba(251,191,36,0.3)', 'rgba(16,185,129,0.4)'],
                });

                const latestLs = oiHistory[0]?.fii_long_short_ratio ?? 1.15;
                const oscBadge = document.getElementById('pulseFiiLsOscBadge');
                const oscPill = document.getElementById('pulseFiiLsRatioPill');
                if (oscBadge) {
                    if (latestLs >= 1.25) {
                        oscBadge.textContent = 'Overbought (>1.25)';
                        oscBadge.style.color = '#34d399';
                        oscBadge.style.background = 'rgba(52,211,153,0.15)';
                    } else if (latestLs <= 0.85) {
                        oscBadge.textContent = 'Oversold Squeeze (<0.85)';
                        oscBadge.style.color = '#f87171';
                        oscBadge.style.background = 'rgba(239,68,68,0.15)';
                    } else {
                        oscBadge.textContent = latestLs >= 1.0 ? 'Normal Bullish' : 'Mild Bearish';
                        oscBadge.style.color = latestLs >= 1.0 ? '#38bdf8' : '#fbbf24';
                        oscBadge.style.background = latestLs >= 1.0 ? 'rgba(56,189,248,0.15)' : 'rgba(251,191,36,0.15)';
                    }
                }
                if (oscPill) {
                    oscPill.textContent = `${latestLs.toFixed(2)}x`;
                    oscPill.style.color = latestLs >= 1.0 ? '#38bdf8' : '#fb923c';
                }
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

        drawMultiLineChart(canvasId, datasets, options = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas || !datasets || !datasets.length) return;

            const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: 300, height: 100 };
            const dpr = window.devicePixelRatio || 1;
            const w = rect.width || 300;
            const h = rect.height || 100;

            canvas.width = w * dpr;
            canvas.height = h * dpr;
            const ctx = canvas.getContext('2d');
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, w, h);

            let allVals = [];
            datasets.forEach(ds => { allVals = allVals.concat(ds.values || []); });
            if (allVals.length === 0) return;

            const minVal = Math.min(...allVals);
            const maxVal = Math.max(...allVals);
            const valRange = (maxVal - minVal) || 1.0;

            const padding = 6;
            const drawW = w - padding * 2;
            const drawH = h - padding * 2;

            // Zero line
            if (options.showZeroLine && minVal <= 0 && maxVal >= 0) {
                const zeroY = padding + drawH - ((0 - minVal) / valRange) * drawH;
                ctx.beginPath();
                ctx.strokeStyle = 'rgba(255,255,255,0.15)';
                ctx.lineWidth = 1;
                ctx.setLineDash([2, 2]);
                ctx.moveTo(padding, zeroY);
                ctx.lineTo(w - padding, zeroY);
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Draw each dataset curve
            datasets.forEach(ds => {
                const vals = ds.values || [];
                if (vals.length < 2) return;

                const points = vals.map((v, i) => {
                    const x = padding + (i / (vals.length - 1)) * drawW;
                    const y = padding + drawH - ((v - minVal) / valRange) * drawH;
                    return { x, y, v };
                });

                ctx.beginPath();
                ctx.moveTo(points[0].x, points[0].y);
                for (let i = 1; i < points.length; i++) {
                    const prev = points[i - 1];
                    const curr = points[i];
                    const cpX = (prev.x + curr.x) / 2;
                    ctx.bezierCurveTo(cpX, prev.y, cpX, curr.y, curr.x, curr.y);
                }
                ctx.strokeStyle = ds.color || '#38bdf8';
                ctx.lineWidth = 1.8;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                ctx.stroke();

                // Terminal dot
                const last = points[points.length - 1];
                ctx.beginPath();
                ctx.arc(last.x, last.y, 3, 0, Math.PI * 2);
                ctx.fillStyle = ds.color || '#38bdf8';
                ctx.fill();
            });
        },

        // =====================================================================
        // 📖 Metric Glossary & Educational Trading Guide Controller
        // =====================================================================
        async openMetricGlossary(targetCategoryOrKey = 'all') {
            const modal = document.getElementById('modalPulseGlossary');
            if (!modal) return;
            modal.style.display = 'flex';

            if (!this._glossaryData) {
                try {
                    const res = await fetch(API_BASE + '/api/v1/market-pulse/glossary');
                    if (res.ok) {
                        const data = await res.json();
                        this._glossaryData = data.categories || data;
                    }
                } catch (e) {
                    console.error('[GLOSSARY] Error fetching metric glossary:', e);
                }
            }

            let catFilter = 'all';
            let scrollTarget = null;
            if (targetCategoryOrKey && targetCategoryOrKey !== 'all') {
                const knownCats = ['participant_oi', 'volatility_vix', 'institutional_liquidity', 'market_breadth', 'fear_greed'];
                if (knownCats.includes(targetCategoryOrKey)) {
                    catFilter = targetCategoryOrKey;
                } else {
                    scrollTarget = targetCategoryOrKey;
                }
            }

            this._currentGlossaryCategory = catFilter;
            this.filterGlossaryCategory(catFilter);

            if (scrollTarget) {
                setTimeout(() => {
                    const targetEl = document.getElementById(`glossary-card-${scrollTarget}`);
                    if (targetEl) {
                        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        targetEl.style.boxShadow = '0 0 15px rgba(168,85,247,0.5)';
                        setTimeout(() => { targetEl.style.boxShadow = ''; }, 2000);
                    }
                }, 100);
            }
        },

        closeMetricGlossary() {
            const modal = document.getElementById('modalPulseGlossary');
            if (modal) modal.style.display = 'none';
        },

        filterGlossaryCategory(category) {
            this._currentGlossaryCategory = category;
            const tabs = document.querySelectorAll('.pulse-glossary-tab');
            tabs.forEach(tab => {
                if (tab.getAttribute('data-cat') === category) {
                    tab.style.background = 'rgba(56,189,248,0.15)';
                    tab.style.color = '#38bdf8';
                    tab.style.borderColor = 'rgba(56,189,248,0.3)';
                } else {
                    tab.style.background = 'transparent';
                    tab.style.color = '#94a3b8';
                    tab.style.borderColor = 'rgba(255,255,255,0.08)';
                }
            });

            this.renderGlossaryCards();
        },

        searchGlossary(query) {
            this._currentGlossarySearch = (query || '').toLowerCase().trim();
            this.renderGlossaryCards();
        },

        renderGlossaryCards() {
            const body = document.getElementById('pulseGlossaryBody');
            if (!body) return;

            let categories = this._glossaryData;
            if (!categories) {
                body.innerHTML = '<div style="color:#64748b;text-align:center;padding:2rem;">Glossary data loading...</div>';
                return;
            }

            if (!Array.isArray(categories) && typeof categories === 'object') {
                categories = categories.categories || Object.values(categories);
            }

            const catFilter = this._currentGlossaryCategory;
            const search = this._currentGlossarySearch;

            let matchingCards = [];
            categories.forEach(cat => {
                if (catFilter !== 'all' && cat.category_id !== catFilter) return;

                (cat.metrics || []).forEach(m => {
                    if (search) {
                        const str = `${m.title} ${m.metric_id} ${m.summary} ${m.formula} ${m.bullish_benchmark} ${m.bearish_benchmark} ${m.next_day_playbook} ${m.trap_warning}`.toLowerCase();
                        if (!str.includes(search)) return;
                    }
                    matchingCards.push({ ...m, catTitle: cat.title, catId: cat.category_id });
                });
            });

            if (!matchingCards.length) {
                body.innerHTML = `
                    <div style="text-align:center;padding:3rem 1rem;color:#64748b;">
                        <div style="font-size:1.5rem;margin-bottom:0.5rem;">🔍</div>
                        <div>No glossary metrics found matching your filter or search query.</div>
                    </div>
                `;
                return;
            }

            body.innerHTML = matchingCards.map(m => {
                return `
                    <div id="glossary-card-${m.metric_id}" class="card" style="padding:1.15rem;background:#0b1329;border:1px solid rgba(255,255,255,0.08);border-radius:8px;display:flex;flex-direction:column;gap:0.75rem;">
                        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.5rem;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:0.6rem;">
                            <div>
                                <div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.2rem;">
                                    <span style="font-size:0.65rem;padding:0.1rem 0.4rem;border-radius:3px;background:rgba(168,85,247,0.15);color:#c084fc;font-weight:700;">
                                        ${m.catTitle}
                                    </span>
                                    <span style="font-size:0.62rem;color:#64748b;font-family:var(--font-mono);">
                                        #${m.metric_id}
                                    </span>
                                </div>
                                <div style="font-size:0.95rem;font-weight:800;color:#f8fafc;">
                                    ${m.title}
                                </div>
                            </div>
                        </div>

                        <!-- Summary -->
                        <div style="font-size:0.75rem;color:#cbd5e1;line-height:1.45;">
                            ${m.summary}
                        </div>

                        <!-- Formula Box -->
                        ${m.formula ? `
                            <div style="background:#060a16;padding:0.5rem 0.75rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                                <div style="font-size:0.65rem;color:#94a3b8;font-weight:700;margin-bottom:0.2rem;">📐 Formula &amp; Mathematical Definition:</div>
                                <div style="font-family:var(--font-mono);font-size:0.72rem;color:#38bdf8;line-height:1.4;">
                                    ${m.formula}
                                </div>
                            </div>
                        ` : ''}

                        <!-- Bullish vs Bearish Benchmarks Grid -->
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;font-size:0.70rem;">
                            <div style="background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);padding:0.5rem 0.65rem;border-radius:6px;">
                                <div style="color:#34d399;font-weight:800;margin-bottom:0.15rem;">🟢 Bullish Benchmark</div>
                                <div style="color:#cbd5e1;line-height:1.35;">${m.bullish_benchmark}</div>
                            </div>
                            <div style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);padding:0.5rem 0.65rem;border-radius:6px;">
                                <div style="color:#f87171;font-weight:800;margin-bottom:0.15rem;">🔴 Bearish Benchmark</div>
                                <div style="color:#cbd5e1;line-height:1.35;">${m.bearish_benchmark}</div>
                            </div>
                        </div>

                        <!-- Next-Day Playbook Directive -->
                        <div style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);padding:0.6rem 0.75rem;border-radius:6px;font-size:0.72rem;">
                            <div style="color:#60a5fa;font-weight:800;margin-bottom:0.2rem;display:flex;align-items:center;gap:0.3rem;">
                                <span>🎯</span> Next-Day Market Application &amp; Trading Strategy:
                            </div>
                            <div style="color:#e2e8f0;line-height:1.4;">
                                ${m.next_day_playbook}
                            </div>
                        </div>

                        <!-- Trap Warning Alert -->
                        <div style="background:rgba(244,63,94,0.06);border:1px solid rgba(244,63,94,0.2);padding:0.5rem 0.75rem;border-radius:6px;font-size:0.70rem;">
                            <div style="color:#fb7185;font-weight:800;margin-bottom:0.15rem;display:flex;align-items:center;gap:0.3rem;">
                                <span>⚠️</span> Trap Warning &amp; Pitfalls:
                            </div>
                            <div style="color:#cbd5e1;line-height:1.35;">
                                ${m.trap_warning}
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        },

        async loadConfluenceSetups(forceRefresh = false) {
            const tbody = document.getElementById('pulseConfluenceTableBody');
            const btn = document.getElementById('btnSyncPulseConfluence');
            if (!tbody) return;

            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:10px;height:10px;margin-right:4px;vertical-align:middle;"></span> Scanning...';
            }

            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align:center;padding:1.5rem;color:#94a3b8;">
                        <div class="loading-spinner" style="margin:0 auto 0.4rem auto;"></div>
                        <div>Evaluating multi-strategy confluences across Breakout, Swing, AI &amp; News...</div>
                    </td>
                </tr>
            `;

            try {
                const res = await fetch(API_BASE + '/api/v1/dashboard/confluence?min_level=1&limit=20');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const setups = data.setups || [];

                if (!setups.length) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="7" style="text-align:center;padding:1.5rem;color:#94a3b8;">
                                🛡️ No multi-strategy confluence setups currently active. All scanner engines operating normally.
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
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '🔄 Re-scan Confluences';
                }
            }
        }
    };

    window.marketPulseModule = marketPulseModule;
    window.app.marketPulse = marketPulseModule;
    Object.assign(window.app, marketPulseModule);
})();
