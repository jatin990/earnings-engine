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
                this.renderSectors(data.sectors || []);

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
            if (biasEl && flows.bias) {
                biasEl.textContent = flows.bias;
                biasEl.style.color = flows.bias.includes('BULLISH') ? '#34d399' : '#f87171';
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
        }
    };

    window.marketPulseModule = marketPulseModule;
    Object.assign(window.app, marketPulseModule);
})();
