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
        _currentOiView: 'index_futures',
        _currentSectorTimeframe: '1d',
        _lastSectorsData: null,
        _lastFlowsData: null,
        _lastOiData: null,
        _glossaryData: null,
        _currentGlossaryCategory: 'all',
        _currentGlossarySearch: '',

        async loadMarketPulseData(forceRefresh = false) {
            const timeEl = document.getElementById('pulseAsOfTime');
            const badgeEl = document.getElementById('pulseLiveBadge');
            if (badgeEl) badgeEl.textContent = '● REFRESHING...';

            const queryParam = forceRefresh ? '?force_refresh=true' : '';

            // Progressive parallel hydration tasks
            const tasks = [
                // 1. Indices Quotes
                fetch(API_BASE + '/api/v1/market-pulse/indices' + queryParam)
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const indices = data.indices || [];
                        this.renderIndices(indices);
                        return { key: 'indices', val: indices };
                    })
                    .catch(err => {
                        console.warn('[MARKET_PULSE] Error fetching modular indices:', err);
                        return null;
                    }),

                // 2. Sectoral Heatmap
                fetch(API_BASE + '/api/v1/market-pulse/sectors' + queryParam)
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const sectors = data.sectors || [];
                        this.renderSectors(sectors);
                        return { key: 'sectors', val: sectors };
                    })
                    .catch(err => {
                        console.warn('[MARKET_PULSE] Error fetching modular sectors:', err);
                        return null;
                    }),

                // 3. Cash Institutional Liquidity & History
                fetch(API_BASE + '/api/v1/market-pulse/liquidity' + queryParam)
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const liq = data.liquidity || {};
                        this.renderInstitutionalFlows(liq);
                        return { key: 'institutional_flows', val: liq };
                    })
                    .catch(err => {
                        console.warn('[MARKET_PULSE] Error fetching modular liquidity:', err);
                        return null;
                    }),

                // 4. Macro Sentiment, Breadth & 30D Trend Charts
                fetch(API_BASE + '/api/v1/market-pulse/sentiment')
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const sent = data.sentiment || {};
                        const fg = {
                            score: sent.fear_greed_score,
                            label: sent.fear_greed_label,
                            color: sent.fear_greed_color,
                            description: sent.fear_greed_desc,
                            momentum_factor: sent.sub_factors?.momentum_factor,
                            vix_factor: sent.sub_factors?.vix_factor,
                            breadth_factor: sent.sub_factors?.breadth_factor,
                            change_7d: sent.change_7d || null,
                        };
                        this.renderFearAndGreed(fg);
                        this.renderVolatility({
                            vix_level: sent.vix_level,
                            regime: sent.vix_regime?.regime || sent.vix_regime,
                            description: sent.vix_regime?.description,
                            stance: sent.vix_regime?.stance,
                        });
                        this.renderBreadth(sent.breadth || {});
                        if (sent.prediction) {
                            this.renderPrediction({
                                regime: sent.prediction.regime,
                                commentary: sent.prediction.commentary,
                                conviction_pct: sent.prediction.conviction_pct,
                                nifty_support: sent.prediction.support_level,
                                nifty_resistance: sent.prediction.resistance_level,
                            });
                        }
                        this.renderMacroCharts(sent.macro_charts || {}, this._lastOiData || {});
                        return { key: 'sentiment', val: sent };
                    })
                    .catch(err => {
                        console.warn('[MARKET_PULSE] Error fetching modular sentiment:', err);
                        return null;
                    }),

                // 5. Official Participant Derivatives Open Interest Matrix & Contrarian Engine
                fetch(API_BASE + '/api/v1/market-pulse/participant-oi' + queryParam)
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const oi = data.participant_oi || {};
                        this.renderParticipantOI(oi);
                        if (this.pulseData?.sentiment?.macro_charts) {
                            this.renderMacroCharts(this.pulseData.sentiment.macro_charts, oi);
                        }
                        return { key: 'participant_oi', val: oi };
                    })
                    .catch(err => {
                        console.warn('[MARKET_PULSE] Error fetching modular participant OI:', err);
                        return null;
                    }),

                // 6. Actionable Next-Day Playbook & Trading Corridors
                fetch(API_BASE + '/api/v1/market-pulse/playbook' + queryParam)
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const pb = data.playbook || {};
                        this.renderNextDayPlaybook(pb);
                        return { key: 'next_day_playbook', val: pb };
                    })
                    .catch(err => {
                        console.warn('[MARKET_PULSE] Error fetching modular playbook:', err);
                        return null;
                    }),
            ];

            try {
                const results = await Promise.allSettled(tasks);
                const combined = {};
                for (const r of results) {
                    if (r.status === 'fulfilled' && r.value) {
                        combined[r.value.key] = r.value.val;
                    }
                }
                this.pulseData = { ...(this.pulseData || {}), ...combined };
                this._pulseLoaded = true;
                if (window.app) {
                    window.app.pulseData = this.pulseData;
                    window.app._pulseLoaded = true;
                }

                if (timeEl) {
                    const now = new Date();
                    timeEl.textContent = 'Updated: ' + now.toLocaleTimeString();
                }
                if (badgeEl) badgeEl.textContent = '● LIVE TICK';
            } catch (e) {
                console.error('[MARKET_PULSE] Error in progressive hydration:', e);
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
        setParticipantOiView(viewMode) {
            this._currentOiView = viewMode;
            if (window.app) window.app._currentOiView = viewMode;

            // Update tab button styles
            const btnIndex = document.getElementById('btnOiViewIndex');
            const btnConsolidated = document.getElementById('btnOiViewConsolidated');
            const btnHistory = document.getElementById('btnOiViewHistory');

            [btnIndex, btnConsolidated, btnHistory].forEach(btn => {
                if (btn) {
                    btn.classList.remove('active');
                    btn.style.background = 'transparent';
                    btn.style.color = '#94a3b8';
                }
            });

            if (viewMode === 'index_futures' && btnIndex) {
                btnIndex.classList.add('active');
                btnIndex.style.background = 'rgba(56,189,248,0.18)';
                btnIndex.style.color = '#38bdf8';
            } else if (viewMode === 'consolidated_fo' && btnConsolidated) {
                btnConsolidated.classList.add('active');
                btnConsolidated.style.background = 'rgba(56,189,248,0.18)';
                btnConsolidated.style.color = '#38bdf8';
            } else if (viewMode === 'history_matrix' && btnHistory) {
                btnHistory.classList.add('active');
                btnHistory.style.background = 'rgba(56,189,248,0.18)';
                btnHistory.style.color = '#38bdf8';
            }

            const snapContainer = document.getElementById('pulseOiSnapshotContainer');
            const histContainer = document.getElementById('pulseOiHistoryContainer');

            if (snapContainer && histContainer) {
                if (viewMode === 'history_matrix') {
                    snapContainer.style.display = 'none';
                    histContainer.style.display = 'block';
                } else {
                    snapContainer.style.display = 'block';
                    histContainer.style.display = 'none';
                }
            }

            const oiData = this._lastOiData || (window.app && window.app._lastOiData) || this.pulseData?.participant_oi || {};
            this.renderParticipantOI(oiData);
        },

        toggleParticipantOiView() {
            const nextView = this._currentOiView === 'history_matrix' ? 'index_futures' : 'history_matrix';
            this.setParticipantOiView(nextView);
        },

        renderParticipantOI(oiData) {
            this._lastOiData = oiData;
            if (window.app) window.app._lastOiData = oiData;

            const tableHead = document.getElementById('pulseParticipantOiTableHead');
            const tableBody = document.getElementById('pulseParticipantOiTableBody');
            const historyBody = document.getElementById('pulseParticipantOiHistoryTableBody');
            const badgeEl = document.getElementById('pulseOiRegimeBadge');
            const sessionSub = document.getElementById('pulseOiSessionSub');
            const commentaryEl = document.getElementById('pulseOiCommentary');
            const contrarianCard = document.getElementById('pulseOiContrarianCard');

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

            // Render Market Maker Contrarian Trap Score & Tomorrow's Prediction
            if (contrarianCard && oiData.contrarian_prediction) {
                const pred = oiData.contrarian_prediction;
                const trapScore = pred.trap_score ?? 50;
                let trapCol = '#38bdf8';
                let trapBg = 'rgba(56,189,248,0.1)';
                let trapBorder = 'rgba(56,189,248,0.25)';

                if (trapScore >= 70) {
                    trapCol = '#f87171';
                    trapBg = 'rgba(248,113,113,0.1)';
                    trapBorder = 'rgba(248,113,113,0.25)';
                } else if (trapScore <= 30) {
                    trapCol = '#34d399';
                    trapBg = 'rgba(52,211,153,0.1)';
                    trapBorder = 'rgba(52,211,153,0.25)';
                } else {
                    trapCol = '#fb923c';
                    trapBg = 'rgba(251,146,60,0.1)';
                    trapBorder = 'rgba(251,146,60,0.25)';
                }

                contrarianCard.style.display = 'block';
                contrarianCard.innerHTML = `
                    <div style="background:${trapBg};border:1px solid ${trapBorder};border-radius:6px;padding:0.6rem 0.8rem;margin-bottom:0.75rem;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;flex-wrap:wrap;gap:0.4rem;">
                            <div style="display:flex;align-items:center;gap:0.4rem;">
                                <span style="font-size:0.78rem;font-weight:800;color:${trapCol};">${pred.headline || 'Institutional Contrarian Prediction'}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span style="font-size:0.65rem;color:#94a3b8;font-family:var(--font-mono);">
                                    FII Long: <strong style="color:#f87171;">${(pred.fii_long_pct ?? 0).toFixed(1)}%</strong> | Client Long: <strong style="color:#34d399;">${(pred.client_long_pct ?? 0).toFixed(1)}%</strong>
                                </span>
                                <span style="font-size:0.68rem;padding:0.1rem 0.45rem;border-radius:4px;background:${trapCol}22;color:${trapCol};font-weight:800;font-family:var(--font-mono);border:1px solid ${trapCol}44;">
                                    Trap Risk: ${trapScore}/100
                                </span>
                            </div>
                        </div>
                        <div style="font-size:0.72rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.3rem;">
                            <strong style="color:#f8fafc;">Expected Market Action:</strong> ${pred.expected_behavior || ''}
                        </div>
                        <div style="font-size:0.7rem;color:#94a3b8;line-height:1.35;">
                            <strong style="color:#38bdf8;">Actionable Playbook:</strong> ${pred.actionable_playbook || ''}
                        </div>
                    </div>
                `;
            }

            const currentView = this._currentOiView || 'index_futures';

            // Dynamic Table Headers based on View
            if (tableHead) {
                if (currentView === 'index_futures') {
                    tableHead.innerHTML = `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.08);color:#94a3b8;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.04em;">
                            <th style="padding:0.4rem 0.6rem;text-align:left;">Participant</th>
                            <th style="padding:0.4rem 0.6rem;text-align:right;">Index Fut Long</th>
                            <th style="padding:0.4rem 0.6rem;text-align:right;">Index Fut Short</th>
                            <th style="padding:0.4rem 0.6rem;text-align:right;">Net Index Contracts</th>
                            <th style="padding:0.4rem 0.6rem;text-align:center;">Index Long %</th>
                            <th style="padding:0.4rem 0.6rem;text-align:center;">1D Shift (Δ)</th>
                            <th style="padding:0.4rem 0.6rem;text-align:left;">Shift &amp; Regime</th>
                        </tr>
                    `;
                } else {
                    tableHead.innerHTML = `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.08);color:#94a3b8;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.04em;">
                            <th style="padding:0.4rem 0.6rem;text-align:left;">Participant</th>
                            <th style="padding:0.4rem 0.6rem;text-align:right;">Total Futures (L/S)</th>
                            <th style="padding:0.4rem 0.6rem;text-align:right;">Call Options (L/S)</th>
                            <th style="padding:0.4rem 0.6rem;text-align:right;">Put Options (L/S)</th>
                            <th style="padding:0.4rem 0.6rem;text-align:right;">Consolidated Net F&amp;O (Δ)</th>
                            <th style="padding:0.4rem 0.6rem;text-align:center;">Long / Short Ratio (Δ)</th>
                            <th style="padding:0.4rem 0.6rem;text-align:left;">Shift &amp; Regime</th>
                        </tr>
                    `;
                }
            }

            // Render Snapshot Table Body
            if (tableBody && oiData.participants && oiData.participants.length) {
                tableBody.innerHTML = oiData.participants.map(p => {
                    const participantName = p.category_label || p.participant;

                    if (currentView === 'index_futures') {
                        const fiLong = p.future_index_long ?? p.futures_long ?? 0;
                        const fiShort = p.future_index_short ?? p.futures_short ?? 0;
                        const fiNet = p.future_index_net ?? (fiLong - fiShort);
                        const fiLongPct = p.future_index_long_pct ?? ((fiLong + fiShort) > 0 ? (fiLong / (fiLong + fiShort)) * 100 : 50);

                        const netCol = fiNet > 0 ? '#34d399' : (fiNet < 0 ? '#f87171' : '#94a3b8');
                        const netSign = fiNet > 0 ? '+' : '';

                        const deltaVal = p.delta_future_index_net ?? p.future_index_delta ?? p.delta_net_contracts ?? null;
                        let deltaStr = '<span style="color:#64748b;">—</span>';
                        if (deltaVal !== null && deltaVal !== undefined) {
                            const dSign = deltaVal >= 0 ? '+' : '';
                            const dCol = deltaVal >= 0 ? '#34d399' : '#f87171';
                            const dArr = deltaVal >= 0 ? '▲' : '▼';
                            deltaStr = `<span style="font-size:0.68rem;padding:0.12rem 0.45rem;border-radius:4px;background:${dCol}18;color:${dCol};font-weight:800;font-family:var(--font-mono);border:1px solid ${dCol}33;">Δ ${dSign}${deltaVal.toLocaleString()} ${dArr}</span>`;
                        }

                        const deltaLongPct = p.delta_future_index_long_pct ?? p.future_index_long_pct_delta ?? null;
                        let deltaPctStr = '';
                        if (deltaLongPct !== null && deltaLongPct !== undefined) {
                            const dPctSign = deltaLongPct >= 0 ? '+' : '';
                            const dPctCol = deltaLongPct >= 0 ? '#34d399' : '#f87171';
                            deltaPctStr = `<div style="font-size:0.58rem;color:${dPctCol};font-weight:700;font-family:var(--font-mono);margin-top:0.12rem;">Δ ${dPctSign}${deltaLongPct.toFixed(1)}%</div>`;
                        }

                        let pctCol = '#94a3b8';
                        let pctBg = 'rgba(255,255,255,0.05)';
                        if (fiLongPct >= 65) {
                            pctCol = '#34d399';
                            pctBg = 'rgba(16,185,129,0.12)';
                        } else if (fiLongPct <= 35) {
                            pctCol = '#f87171';
                            pctBg = 'rgba(239,68,68,0.12)';
                        }

                        const stance = p.stance || 'Balanced';
                        const shiftRegime = p.shift_regime || p.oi_regime_badge || stance;
                        let stanceBg = 'rgba(255,255,255,0.04)';
                        let stanceCol = '#cbd5e1';
                        let stanceBorder = 'rgba(255,255,255,0.08)';
                        if (shiftRegime.includes('🟢') || shiftRegime.includes('Long Build') || shiftRegime.includes('Long Add')) {
                            stanceBg = 'rgba(16,185,129,0.12)';
                            stanceCol = '#34d399';
                            stanceBorder = 'rgba(16,185,129,0.25)';
                        } else if (shiftRegime.includes('⚡') || shiftRegime.includes('Covering')) {
                            stanceBg = 'rgba(56,189,248,0.12)';
                            stanceCol = '#38bdf8';
                            stanceBorder = 'rgba(56,189,248,0.25)';
                        } else if (shiftRegime.includes('🔴') || shiftRegime.includes('Short Build') || shiftRegime.includes('Short Add')) {
                            stanceBg = 'rgba(239,68,68,0.12)';
                            stanceCol = '#f87171';
                            stanceBorder = 'rgba(239,68,68,0.25)';
                        } else if (shiftRegime.includes('⚠️') || shiftRegime.includes('Unwinding')) {
                            stanceBg = 'rgba(251,146,60,0.12)';
                            stanceCol = '#fb923c';
                            stanceBorder = 'rgba(251,146,60,0.25)';
                        }

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                <td style="padding:0.45rem 0.6rem;text-align:left;font-weight:700;color:#f8fafc;">
                                    ${participantName}
                                </td>
                                <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#34d399;font-weight:600;">
                                    ${fiLong.toLocaleString()}
                                </td>
                                <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:#f87171;font-weight:600;">
                                    ${fiShort.toLocaleString()}
                                </td>
                                <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:${netCol};">
                                    ${netSign}${fiNet.toLocaleString()}
                                </td>
                                <td style="padding:0.45rem 0.6rem;text-align:center;">
                                    <span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:${pctBg};color:${pctCol};font-weight:800;font-family:var(--font-mono);border:1px solid ${pctCol}33;">
                                        ${fiLongPct.toFixed(1)}% Long
                                    </span>
                                    ${deltaPctStr}
                                </td>
                                <td style="padding:0.45rem 0.6rem;text-align:center;">
                                    ${deltaStr}
                                </td>
                                <td style="padding:0.45rem 0.6rem;text-align:left;">
                                    <span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:${stanceBg};color:${stanceCol};font-weight:700;font-family:var(--font-mono);border:1px solid ${stanceBorder};">
                                        ${shiftRegime}
                                    </span>
                                </td>
                            </tr>
                        `;
                    } else {
                        // Consolidated F&O View
                        const netVal = p.net_contracts || 0;
                        const netCol = netVal > 0 ? '#34d399' : (netVal < 0 ? '#f87171' : '#94a3b8');
                        const netSign = netVal > 0 ? '+' : '';

                        const deltaVal = p.delta_net_contracts !== undefined ? p.delta_net_contracts : (p.delta_net_contracts_1d !== undefined ? p.delta_net_contracts_1d : null);
                        let deltaStr = '';
                        if (deltaVal !== null && deltaVal !== undefined) {
                            const dSign = deltaVal >= 0 ? '+' : '';
                            const dCol = deltaVal >= 0 ? '#34d399' : '#f87171';
                            const dArr = deltaVal >= 0 ? '▲' : '▼';
                            deltaStr = `<div style="font-size:0.60rem;color:${dCol};font-weight:700;font-family:var(--font-mono);margin-top:0.12rem;">Δ ${dSign}${deltaVal.toLocaleString()} ${dArr}</div>`;
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

                        const deltaLs = p.delta_ls_ratio !== undefined ? p.delta_ls_ratio : null;
                        let deltaLsStr = '';
                        if (deltaLs !== null && deltaLs !== undefined) {
                            const lsSign = deltaLs >= 0 ? '+' : '';
                            const lsColVal = deltaLs >= 0 ? '#34d399' : '#f87171';
                            deltaLsStr = `<div style="font-size:0.58rem;color:${lsColVal};font-weight:700;font-family:var(--font-mono);margin-top:0.12rem;">Δ ${lsSign}${deltaLs.toFixed(2)}x</div>`;
                        }

                        const stance = p.stance || 'Balanced';
                        const shiftRegime = p.shift_regime || p.oi_regime_badge || stance;
                        let stanceBg = 'rgba(255,255,255,0.04)';
                        let stanceCol = '#cbd5e1';
                        let stanceBorder = 'rgba(255,255,255,0.08)';
                        if (shiftRegime.includes('🟢') || shiftRegime.includes('Long Build') || shiftRegime.includes('Long Add')) {
                            stanceBg = 'rgba(16,185,129,0.12)';
                            stanceCol = '#34d399';
                            stanceBorder = 'rgba(16,185,129,0.25)';
                        } else if (shiftRegime.includes('⚡') || shiftRegime.includes('Covering')) {
                            stanceBg = 'rgba(56,189,248,0.12)';
                            stanceCol = '#38bdf8';
                            stanceBorder = 'rgba(56,189,248,0.25)';
                        } else if (shiftRegime.includes('🔴') || shiftRegime.includes('Short Build') || shiftRegime.includes('Short Add')) {
                            stanceBg = 'rgba(239,68,68,0.12)';
                            stanceCol = '#f87171';
                            stanceBorder = 'rgba(239,68,68,0.25)';
                        } else if (shiftRegime.includes('⚠️') || shiftRegime.includes('Unwinding')) {
                            stanceBg = 'rgba(251,146,60,0.12)';
                            stanceCol = '#fb923c';
                            stanceBorder = 'rgba(251,146,60,0.25)';
                        }

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                <td style="padding:0.45rem 0.6rem;text-align:left;font-weight:700;color:#f8fafc;">
                                    ${participantName}
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
                                    ${deltaLsStr}
                                </td>
                                <td style="padding:0.45rem 0.6rem;text-align:left;">
                                    <span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:${stanceBg};color:${stanceCol};font-weight:700;font-family:var(--font-mono);border:1px solid ${stanceBorder};">
                                        ${shiftRegime}
                                    </span>
                                </td>
                            </tr>
                        `;
                    }
                }).join('');
            }

            // Render 10-Day History Matrix Table
            const history = oiData.history_10d || oiData.history_7d || [];
            if (historyBody && history.length) {
                historyBody.innerHTML = history.map((row, idx) => {
                    const isToday = idx === 0;
                    const rowBg = isToday ? 'rgba(56,189,248,0.06)' : 'transparent';

                    const fNet = row.fii_future_index_net ?? row.fii_net_contracts ?? 0;
                    const fSign = fNet >= 0 ? '+' : '';
                    const fCol = fNet >= 0 ? '#34d399' : '#f87171';
                    const fPct = row.fii_future_index_long_pct ?? ((row.fii_long_short_ratio ?? 1) / (1 + (row.fii_long_short_ratio ?? 1)) * 100);

                    const dNet = row.dii_future_index_net ?? row.dii_net_contracts ?? 0;
                    const dSign = dNet >= 0 ? '+' : '';
                    const dCol = dNet >= 0 ? '#34d399' : '#f87171';

                    const pNet = row.pro_future_index_net ?? row.pro_net_contracts ?? 0;
                    const pSign = pNet >= 0 ? '+' : '';
                    const pCol = pNet >= 0 ? '#34d399' : '#f87171';

                    const cNet = row.client_future_index_net ?? row.client_net_contracts ?? 0;
                    const cSign = cNet >= 0 ? '+' : '';
                    const cCol = cNet >= 0 ? '#34d399' : '#f87171';

                    const fmtDelta = (val) => {
                        if (val === null || val === undefined) return '';
                        const s = val >= 0 ? '+' : '';
                        const c = val >= 0 ? '#34d399' : '#f87171';
                        const arr = val >= 0 ? '▲' : '▼';
                        return `<div style="font-size:0.58rem;color:${c};font-weight:700;font-family:var(--font-mono);line-height:1.2;">Δ ${s}${val.toLocaleString()} ${arr}</div>`;
                    };

                    const fDeltaStr = fmtDelta(row.fii_delta_index_net);
                    const dDeltaStr = fmtDelta(row.dii_delta_index_net);
                    const pDeltaStr = fmtDelta(row.pro_delta_index_net);
                    const cDeltaStr = fmtDelta(row.client_delta_index_net);

                    const shiftRegime = row.fii_shift_regime || row.shift_regime || (fNet >= 0 ? '🟢 Long Build-up' : '🔴 Short Build-up');
                    let biasBg = 'rgba(52,211,153,0.12)';
                    let biasCol = '#34d399';
                    let biasBorder = 'rgba(52,211,153,0.25)';
                    if (shiftRegime.includes('🔴') || shiftRegime.includes('Short Build') || shiftRegime.includes('Short Add')) {
                        biasBg = 'rgba(248,113,113,0.12)';
                        biasCol = '#f87171';
                        biasBorder = 'rgba(248,113,113,0.25)';
                    } else if (shiftRegime.includes('⚡') || shiftRegime.includes('Covering')) {
                        biasBg = 'rgba(56,189,248,0.12)';
                        biasCol = '#38bdf8';
                        biasBorder = 'rgba(56,189,248,0.25)';
                    } else if (shiftRegime.includes('⚠️') || shiftRegime.includes('Unwinding')) {
                        biasBg = 'rgba(251,146,60,0.12)';
                        biasCol = '#fb923c';
                        biasBorder = 'rgba(251,146,60,0.25)';
                    } else if (shiftRegime.includes('⚪') || shiftRegime.includes('Neutral') || shiftRegime.includes('Baseline')) {
                        biasBg = 'rgba(148,163,184,0.12)';
                        biasCol = '#94a3b8';
                        biasBorder = 'rgba(148,163,184,0.25)';
                    }

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);background:${rowBg};">
                            <td style="padding:0.45rem 0.6rem;font-family:var(--font-mono);font-weight:${isToday ? '700' : '500'};color:${isToday ? '#f8fafc' : '#cbd5e1'};">
                                ${row.session_label || row.date}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${fCol};font-weight:600;">
                                <div>${fSign}${fNet.toLocaleString()} <span style="font-size:0.58rem;color:#94a3b8;">(${fPct.toFixed(0)}% L)</span></div>
                                ${fDeltaStr}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${dCol};font-weight:600;">
                                <div>${dSign}${dNet.toLocaleString()}</div>
                                ${dDeltaStr}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${pCol};font-weight:600;">
                                <div>${pSign}${pNet.toLocaleString()}</div>
                                ${pDeltaStr}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${cCol};font-weight:600;">
                                <div>${cSign}${cNet.toLocaleString()}</div>
                                ${cDeltaStr}
                            </td>
                            <td style="padding:0.45rem 0.6rem;text-align:center;">
                                <span style="font-size:0.62rem;padding:0.15rem 0.45rem;border-radius:4px;background:${biasBg};color:${biasCol};font-weight:700;font-family:var(--font-mono);border:1px solid ${biasBorder};">
                                    ${shiftRegime}
                                </span>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        },

        renderSectors(sectors) {
            const grid = document.getElementById('pulseSectorsGrid');
            if (!grid) return;

            if (sectors && sectors.length) {
                this._lastSectorsData = sectors;
            }
            const currentTf = this._currentSectorTimeframe || '1d';

            if (!sectors || !sectors.length) {
                grid.innerHTML = '<div style="color:#64748b;font-size:0.75rem;padding:1rem;text-align:center;grid-column:1/-1;">Sector heatmap data loading...</div>';
                return;
            }

            grid.innerHTML = sectors.map(s => {
                let returnVal = 0;
                if (currentTf === '30d') {
                    returnVal = s.change_30d ?? 0;
                } else if (currentTf === '7d') {
                    returnVal = s.change_7d ?? 0;
                } else {
                    returnVal = s.change_1d ?? 0;
                }

                // Magnitude Saturation Color Matrix
                let bg = 'rgba(255,255,255,0.02)';
                let border = 'rgba(255,255,255,0.08)';
                let textCol = '#94a3b8';
                let badgeBg = 'rgba(255,255,255,0.06)';
                let badgeBorder = 'rgba(255,255,255,0.1)';

                if (returnVal >= 2.5) {
                    bg = 'rgba(16, 185, 129, 0.22)';
                    border = 'rgba(16, 185, 129, 0.60)';
                    textCol = '#34d399';
                    badgeBg = 'rgba(16, 185, 129, 0.35)';
                    badgeBorder = 'rgba(16, 185, 129, 0.50)';
                } else if (returnVal >= 1.0) {
                    bg = 'rgba(16, 185, 129, 0.14)';
                    border = 'rgba(16, 185, 129, 0.40)';
                    textCol = '#34d399';
                    badgeBg = 'rgba(16, 185, 129, 0.25)';
                    badgeBorder = 'rgba(16, 185, 129, 0.40)';
                } else if (returnVal > 0) {
                    bg = 'rgba(16, 185, 129, 0.07)';
                    border = 'rgba(16, 185, 129, 0.22)';
                    textCol = '#6ee7b7';
                    badgeBg = 'rgba(16, 185, 129, 0.15)';
                    badgeBorder = 'rgba(16, 185, 129, 0.30)';
                } else if (returnVal <= -2.5) {
                    bg = 'rgba(239, 68, 68, 0.22)';
                    border = 'rgba(239, 68, 68, 0.60)';
                    textCol = '#f87171';
                    badgeBg = 'rgba(239, 68, 68, 0.35)';
                    badgeBorder = 'rgba(239, 68, 68, 0.50)';
                } else if (returnVal <= -1.0) {
                    bg = 'rgba(239, 68, 68, 0.14)';
                    border = 'rgba(239, 68, 68, 0.40)';
                    textCol = '#f87171';
                    badgeBg = 'rgba(239, 68, 68, 0.25)';
                    badgeBorder = 'rgba(239, 68, 68, 0.40)';
                } else if (returnVal < 0) {
                    bg = 'rgba(239, 68, 68, 0.07)';
                    border = 'rgba(239, 68, 68, 0.22)';
                    textCol = '#fca5a5';
                    badgeBg = 'rgba(239, 68, 68, 0.15)';
                    badgeBorder = 'rgba(239, 68, 68, 0.30)';
                }

                const signActive = returnVal >= 0 ? '+' : '';
                const arrow = returnVal >= 0 ? '▲' : '▼';

                const advances = s.advances ?? 0;
                const declines = s.declines ?? 0;
                const total = (advances + declines) || s.total_constituents || 10;
                const advPct = total > 0 ? Math.round((advances / total) * 100) : 50;
                const decPct = 100 - advPct;

                const s1d = s.change_1d ?? 0;
                const s7d = s.change_7d ?? 0;
                const s30d = s.change_30d ?? 0;

                const gainerHtml = s.top_gainer ? `
                    <span style="font-size:0.60rem;padding:0.1rem 0.3rem;border-radius:3px;background:rgba(16,185,129,0.12);color:#34d399;font-family:var(--font-mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:48%;">
                        ▲ ${s.top_gainer}
                    </span>` : '';
                const loserHtml = s.top_loser ? `
                    <span style="font-size:0.60rem;padding:0.1rem 0.3rem;border-radius:3px;background:rgba(239,68,68,0.12);color:#f87171;font-family:var(--font-mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:48%;">
                        ▼ ${s.top_loser}
                    </span>` : '';

                return `
                    <div style="background:${bg};border:1px solid ${border};border-radius:7px;padding:0.65rem 0.75rem;display:flex;flex-direction:column;gap:0.35rem;transition:all 0.2s ease;box-shadow:0 2px 8px rgba(0,0,0,0.2);">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.4rem;">
                            <div>
                                <div style="font-size:0.78rem;font-weight:800;color:#f8fafc;letter-spacing:0.01em;">${s.name}</div>
                                <div style="font-size:0.62rem;color:#94a3b8;font-family:var(--font-mono);">${s.symbol || ''}</div>
                            </div>
                            <span style="font-size:0.80rem;font-weight:900;color:${textCol};font-family:var(--font-mono);padding:0.18rem 0.45rem;border-radius:4px;background:${badgeBg};border:1px solid ${badgeBorder};white-space:nowrap;">
                                ${signActive}${returnVal.toFixed(1)}% ${arrow}
                            </span>
                        </div>

                        <!-- Breadth Progress Bar -->
                        <div style="display:flex;flex-direction:column;gap:0.15rem;margin-top:0.1rem;">
                            <div style="display:flex;justify-content:space-between;font-size:0.60rem;color:#94a3b8;font-family:var(--font-mono);">
                                <span style="color:#34d399;font-weight:700;">${advances} ▲</span>
                                <span style="color:#64748b;font-size:0.58rem;">Breadth</span>
                                <span style="color:#f87171;font-weight:700;">${declines} ▼</span>
                            </div>
                            <div style="height:4px;width:100%;border-radius:2px;background:rgba(255,255,255,0.06);display:flex;overflow:hidden;">
                                <div style="width:${advPct}%;background:#10b981;height:100%;"></div>
                                <div style="width:${decPct}%;background:#ef4444;height:100%;"></div>
                            </div>
                        </div>

                        <!-- Multi-Horizon Strip -->
                        <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.62rem;color:#94a3b8;font-family:var(--font-mono);border-top:1px solid rgba(255,255,255,0.06);padding-top:0.25rem;">
                            <span style="${currentTf === '1d' ? 'font-weight:800;color:#f8fafc;' : ''}">1D: <strong style="color:${s1d >= 0 ? '#34d399' : '#f87171'};">${s1d >= 0 ? '+' : ''}${s1d}%</strong></span>
                            <span style="${currentTf === '7d' ? 'font-weight:800;color:#f8fafc;' : ''}">7D: <strong style="color:${s7d >= 0 ? '#34d399' : '#f87171'};">${s7d >= 0 ? '+' : ''}${s7d}%</strong></span>
                            <span style="${currentTf === '30d' ? 'font-weight:800;color:#f8fafc;' : ''}">30D: <strong style="color:${s30d >= 0 ? '#34d399' : '#f87171'};">${s30d >= 0 ? '+' : ''}${s30d}%</strong></span>
                        </div>

                        <!-- Leader / Laggard Chips if present -->
                        ${(gainerHtml || loserHtml) ? `
                            <div style="display:flex;justify-content:space-between;gap:0.3rem;margin-top:0.05rem;">
                                ${gainerHtml || '<span></span>'}
                                ${loserHtml || '<span></span>'}
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join('');
        },

        setSectorTimeframe(tf) {
            this._currentSectorTimeframe = tf;
            const buttons = document.querySelectorAll('.pulse-sector-tf-btn');
            buttons.forEach(btn => {
                if (btn.getAttribute('data-tf') === tf) {
                    btn.classList.add('active');
                    btn.style.background = 'rgba(56,189,248,0.2)';
                    btn.style.color = '#38bdf8';
                    btn.style.border = '1px solid rgba(56,189,248,0.4)';
                } else {
                    btn.classList.remove('active');
                    btn.style.background = 'rgba(255,255,255,0.05)';
                    btn.style.color = '#94a3b8';
                    btn.style.border = '1px solid rgba(255,255,255,0.08)';
                }
            });
            if (this._lastSectorsData) {
                this.renderSectors(this._lastSectorsData);
            }
        },

        // =====================================================================
        // 📈 Macro Charts Rendering (5-Chart Grid) with High-DPI & Interactive Tooltips
        // =====================================================================
        renderMacroCharts(charts, participantOi = {}) {
            if (!charts) return;

            // 1. Fear & Greed 30D Trend Wave Chart
            const fgSeries = charts.fear_greed || [];
            if (fgSeries.length) {
                this.drawSparklineChart('chartFearGreed', fgSeries.map(x => x.score), {
                    color: '#34d399',
                    gradientFrom: 'rgba(52, 211, 153, 0.28)',
                    gradientTo: 'rgba(52, 211, 153, 0.01)',
                    minVal: 0,
                    maxVal: 100,
                    referenceLines: [25, 50, 75],
                    refLineColors: ['rgba(244,63,94,0.35)', 'rgba(251,191,36,0.3)', 'rgba(16,185,129,0.35)'],
                    dates: fgSeries.map(x => x.date || ''),
                    valueFormatter: (v) => `${Math.round(v)} / 100`,
                });
            }

            // 2. India VIX Volatility Corridor Chart
            const vixSeries = charts.vix || [];
            if (vixSeries.length) {
                this.drawSparklineChart('chartVix', vixSeries.map(x => x.value), {
                    color: '#38bdf8',
                    gradientFrom: 'rgba(56, 189, 248, 0.28)',
                    gradientTo: 'rgba(56, 189, 248, 0.01)',
                    referenceLines: [15, 20],
                    refLineColors: ['rgba(52,211,153,0.35)', 'rgba(248,113,113,0.35)'],
                    dates: vixSeries.map(x => x.date || ''),
                    valueFormatter: (v) => `${v.toFixed(2)}`,
                });
            }

            // 3. NIFTY 50 Benchmark Trajectory Chart
            const niftySeries = charts.nifty || [];
            if (niftySeries.length) {
                this.drawSparklineChart('chartNifty', niftySeries.map(x => x.value), {
                    color: '#818cf8',
                    gradientFrom: 'rgba(129, 140, 248, 0.28)',
                    gradientTo: 'rgba(129, 140, 248, 0.01)',
                    dates: niftySeries.map(x => x.date || ''),
                    valueFormatter: (v) => `${Math.round(v).toLocaleString()}`,
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
                const dates = chronological.map(x => x.date || x.session_date || '');

                this.drawMultiLineChart('chartParticipantOi', [
                    { name: 'FII', values: fiiSeries, color: '#34d399' },
                    { name: 'PRO', values: proSeries, color: '#818cf8' },
                    { name: 'CLIENT', values: clientSeries, color: '#fb923c' }
                ], {
                    showZeroLine: true,
                    dates: dates,
                    valueFormatter: (v) => (v >= 0 ? '+' : '') + Math.round(v).toLocaleString(),
                });

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
                const dates = chronological.map(x => x.date || x.session_date || '');

                this.drawSparklineChart('chartFiiLsRatio', fiiLsSeries, {
                    color: '#38bdf8',
                    gradientFrom: 'rgba(56, 189, 248, 0.28)',
                    gradientTo: 'rgba(56, 189, 248, 0.01)',
                    referenceLines: [0.85, 1.0, 1.25],
                    refLineColors: ['rgba(244,63,94,0.4)', 'rgba(251,191,36,0.3)', 'rgba(16,185,129,0.4)'],
                    dates: dates,
                    valueFormatter: (v) => `${v.toFixed(2)}x`,
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
            const dpr = Math.max(window.devicePixelRatio || 1, 2);
            const w = Math.round(rect.width || 300);
            const h = Math.round(rect.height || 100);

            canvas.width = Math.round(w * dpr);
            canvas.height = Math.round(h * dpr);
            canvas.style.width = w + 'px';
            canvas.style.height = h + 'px';

            const ctx = canvas.getContext('2d');

            const minVal = options.minVal !== undefined ? options.minVal : Math.min(...values) * 0.98;
            const maxVal = options.maxVal !== undefined ? options.maxVal : Math.max(...values) * 1.02;
            const valRange = (maxVal - minVal) || 1.0;

            const padding = 10;
            const drawW = w - padding * 2;
            const drawH = h - padding * 2;

            // Calculate points
            const points = values.map((v, i) => {
                const x = padding + (i / (values.length - 1)) * drawW;
                const y = padding + drawH - ((v - minVal) / valRange) * drawH;
                const date = options.dates && options.dates[i] ? options.dates[i] : '';
                return { x, y, v, date, index: i };
            });

            const renderFrame = (hoverPoint = null) => {
                ctx.save();
                ctx.scale(dpr, dpr);
                ctx.clearRect(0, 0, w, h);

                // Draw Reference Corridor Lines
                if (options.referenceLines) {
                    options.referenceLines.forEach((ref, idx) => {
                        if (ref >= minVal && ref <= maxVal) {
                            const y = padding + drawH - ((ref - minVal) / valRange) * drawH;
                            ctx.beginPath();
                            ctx.strokeStyle = (options.refLineColors && options.refLineColors[idx]) || 'rgba(255,255,255,0.12)';
                            ctx.lineWidth = 1;
                            ctx.setLineDash([3, 3]);
                            ctx.moveTo(padding, y);
                            ctx.lineTo(w - padding, y);
                            ctx.stroke();
                            ctx.setLineDash([]);
                        }
                    });
                }

                // Fill Area Gradient
                const gradient = ctx.createLinearGradient(0, padding, 0, h - padding);
                gradient.addColorStop(0, options.gradientFrom || 'rgba(56,189,248,0.28)');
                gradient.addColorStop(1, options.gradientTo || 'rgba(56,189,248,0.01)');

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

                if (hoverPoint) {
                    // Vertical Crosshair
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([2, 2]);
                    ctx.moveTo(hoverPoint.x, padding);
                    ctx.lineTo(hoverPoint.x, h - padding);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Glowing Hover Dot
                    ctx.beginPath();
                    ctx.arc(hoverPoint.x, hoverPoint.y, 4.5, 0, Math.PI * 2);
                    ctx.fillStyle = '#ffffff';
                    ctx.shadowColor = options.color || '#38bdf8';
                    ctx.shadowBlur = 10;
                    ctx.fill();
                    ctx.shadowBlur = 0;
                    ctx.lineWidth = 2;
                    ctx.strokeStyle = options.color || '#38bdf8';
                    ctx.stroke();

                    // Micro-HUD Tooltip Pill
                    const valText = options.valueFormatter ? options.valueFormatter(hoverPoint.v) : hoverPoint.v.toFixed(1);
                    const hudText = hoverPoint.date ? `${hoverPoint.date} · ${valText}` : `${valText}`;
                    ctx.font = '600 9px var(--font-mono, monospace)';
                    const textWidth = ctx.measureText(hudText).width;
                    const pillW = textWidth + 12;
                    const pillH = 16;
                    let pillX = Math.min(Math.max(hoverPoint.x - pillW / 2, padding), w - padding - pillW);
                    let pillY = hoverPoint.y - 20;
                    if (pillY < padding) pillY = hoverPoint.y + 8;

                    ctx.fillStyle = 'rgba(10, 15, 29, 0.88)';
                    ctx.strokeStyle = options.color || '#38bdf8';
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.roundRect(pillX, pillY, pillW, pillH, 3);
                    ctx.fill();
                    ctx.stroke();

                    ctx.fillStyle = '#f8fafc';
                    ctx.fillText(hudText, pillX + 6, pillY + 11);
                } else {
                    // Glowing Last Point
                    const last = points[points.length - 1];
                    ctx.beginPath();
                    ctx.arc(last.x, last.y, 3.5, 0, Math.PI * 2);
                    ctx.fillStyle = options.color || '#38bdf8';
                    ctx.shadowColor = options.color || '#38bdf8';
                    ctx.shadowBlur = 8;
                    ctx.fill();
                    ctx.shadowBlur = 0;
                }

                ctx.restore();
            };

            // Initial render
            renderFrame();

            // Interactive Crosshair Listeners
            canvas.onmousemove = (e) => {
                const cRect = canvas.getBoundingClientRect();
                const mouseX = e.clientX - cRect.left;
                // Find closest point by x
                let closest = points[0];
                let minDist = Math.abs(points[0].x - mouseX);
                for (let i = 1; i < points.length; i++) {
                    const dist = Math.abs(points[i].x - mouseX);
                    if (dist < minDist) {
                        minDist = dist;
                        closest = points[i];
                    }
                }
                renderFrame(closest);
            };

            canvas.onmouseleave = () => {
                renderFrame(null);
            };
        },

        drawMultiLineChart(canvasId, datasets, options = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas || !datasets || !datasets.length) return;

            const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: 300, height: 100 };
            const dpr = Math.max(window.devicePixelRatio || 1, 2);
            const w = Math.round(rect.width || 300);
            const h = Math.round(rect.height || 100);

            canvas.width = Math.round(w * dpr);
            canvas.height = Math.round(h * dpr);
            canvas.style.width = w + 'px';
            canvas.style.height = h + 'px';

            const ctx = canvas.getContext('2d');

            let allVals = [];
            datasets.forEach(ds => { allVals = allVals.concat(ds.values || []); });
            if (allVals.length === 0) return;

            const minVal = Math.min(...allVals);
            const maxVal = Math.max(...allVals);
            const valRange = (maxVal - minVal) || 1.0;

            const padding = 10;
            const drawW = w - padding * 2;
            const drawH = h - padding * 2;

            const preparedDatasets = datasets.map(ds => {
                const vals = ds.values || [];
                const points = vals.map((v, i) => {
                    const x = padding + (i / (vals.length - 1)) * drawW;
                    const y = padding + drawH - ((v - minVal) / valRange) * drawH;
                    const date = options.dates && options.dates[i] ? options.dates[i] : '';
                    return { x, y, v, date, index: i };
                });
                return { ...ds, points };
            });

            const renderFrame = (hoverIndex = null) => {
                ctx.save();
                ctx.scale(dpr, dpr);
                ctx.clearRect(0, 0, w, h);

                // Zero line
                if (options.showZeroLine && minVal <= 0 && maxVal >= 0) {
                    const zeroY = padding + drawH - ((0 - minVal) / valRange) * drawH;
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(255,255,255,0.18)';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([2, 2]);
                    ctx.moveTo(padding, zeroY);
                    ctx.lineTo(w - padding, zeroY);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }

                // Draw each dataset curve
                preparedDatasets.forEach(ds => {
                    const points = ds.points;
                    if (points.length < 2) return;

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

                    if (hoverIndex === null) {
                        // Terminal dot
                        const last = points[points.length - 1];
                        ctx.beginPath();
                        ctx.arc(last.x, last.y, 3, 0, Math.PI * 2);
                        ctx.fillStyle = ds.color || '#38bdf8';
                        ctx.fill();
                    }
                });

                if (hoverIndex !== null) {
                    const samplePt = preparedDatasets[0]?.points[hoverIndex];
                    if (samplePt) {
                        // Crosshair
                        ctx.beginPath();
                        ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([2, 2]);
                        ctx.moveTo(samplePt.x, padding);
                        ctx.lineTo(samplePt.x, h - padding);
                        ctx.stroke();
                        ctx.setLineDash([]);

                        // Highlight dots
                        preparedDatasets.forEach(ds => {
                            const pt = ds.points[hoverIndex];
                            if (pt) {
                                ctx.beginPath();
                                ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
                                ctx.fillStyle = '#ffffff';
                                ctx.shadowColor = ds.color || '#38bdf8';
                                ctx.shadowBlur = 8;
                                ctx.fill();
                                ctx.shadowBlur = 0;
                                ctx.lineWidth = 2;
                                ctx.strokeStyle = ds.color || '#38bdf8';
                                ctx.stroke();
                            }
                        });

                        // Multi-line HUD
                        const dateStr = samplePt.date || '';
                        let hudItems = preparedDatasets.map(ds => {
                            const pt = ds.points[hoverIndex];
                            const vStr = pt ? (options.valueFormatter ? options.valueFormatter(pt.v) : pt.v.toLocaleString()) : '—';
                            return `${ds.name}: ${vStr}`;
                        });
                        const hudText = (dateStr ? `[${dateStr}] ` : '') + hudItems.join(' · ');
                        ctx.font = '600 9px var(--font-mono, monospace)';
                        const textWidth = ctx.measureText(hudText).width;
                        const pillW = textWidth + 12;
                        const pillH = 16;
                        let pillX = Math.min(Math.max(samplePt.x - pillW / 2, padding), w - padding - pillW);
                        let pillY = padding + 2;

                        ctx.fillStyle = 'rgba(10, 15, 29, 0.90)';
                        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
                        ctx.lineWidth = 1;
                        ctx.beginPath();
                        ctx.roundRect(pillX, pillY, pillW, pillH, 3);
                        ctx.fill();
                        ctx.stroke();

                        ctx.fillStyle = '#f8fafc';
                        ctx.fillText(hudText, pillX + 6, pillY + 11);
                    }
                }

                ctx.restore();
            };

            // Initial render
            renderFrame();

            // Interactive Crosshair Listeners
            canvas.onmousemove = (e) => {
                const cRect = canvas.getBoundingClientRect();
                const mouseX = e.clientX - cRect.left;
                const samplePoints = preparedDatasets[0]?.points || [];
                if (!samplePoints.length) return;

                let closestIdx = 0;
                let minDist = Math.abs(samplePoints[0].x - mouseX);
                for (let i = 1; i < samplePoints.length; i++) {
                    const dist = Math.abs(samplePoints[i].x - mouseX);
                    if (dist < minDist) {
                        minDist = dist;
                        closestIdx = i;
                    }
                }
                renderFrame(closestIdx);
            };

            canvas.onmouseleave = () => {
                renderFrame(null);
            };
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
