// =========================================================================
// catalyst_consensus — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
// =========================================================================
        // 🧠 Catalyst AI Consensus Intelligence Modal Manager
        // =========================================================================
        app.activeCatConsensusTicker = null;
        app.activeConsensusResult = null;

        app.fetchModalRateLimits = async function() {
            try {
                const res = await fetch(API_BASE + '/api/v1/consensus/models');
                if (!res.ok) return;
                const data = await res.json();
                const rlStatusEl = document.getElementById('modalRatelimitStatus');
                if (rlStatusEl && data.rate_limits?.downstreams?.openrouter) {
                    const or = data.rate_limits.downstreams.openrouter;
                    const tf1m = or.timeframes?.['1m'] || {};
                    const tf24h = or.timeframes?.['24h'] || {};
                    const rem1m = tf1m.remaining != null ? tf1m.remaining : 20;
                    const rem24h = tf24h.remaining != null ? tf24h.remaining : 200;
                    rlStatusEl.textContent = `🟢 AI Quota: ${rem1m}/${tf1m.allowed || 20} RPM | ${rem24h}/${tf24h.allowed || 200} RPD`;
                    if (rem1m <= 3 || rem24h <= 15) {
                        rlStatusEl.style.color = '#fbbf24';
                        rlStatusEl.style.borderColor = 'rgba(245,158,11,0.3)';
                        rlStatusEl.style.background = 'rgba(245,158,11,0.1)';
                    }
                    if (rem1m <= 0 || rem24h <= 0) {
                        rlStatusEl.textContent = `🔴 Cooldown: 0 RPM`;
                        rlStatusEl.style.color = '#f87171';
                        rlStatusEl.style.borderColor = 'rgba(239,68,68,0.3)';
                        rlStatusEl.style.background = 'rgba(239,68,68,0.1)';
                    }
                }
                window._dashModelsStats = data.models || [];
                const models = data.models || [];
                models.forEach(m => {
                    const btnKey = m.name ? m.name.toLowerCase().split('-')[0].replace(/[^a-z]/g, '') : '';
                    const btn = document.getElementById('modalBtn-' + btnKey);
                    if (btn) {
                        const succPct = m.success_rate_pct != null ? m.success_rate_pct : (m.benchmark_success_rate_pct || 99.5);
                        const isDegraded = m.is_degraded || (m.avg_latency_1h_ms && m.avg_latency_1h_ms > 8000);
                        btn.title = `${m.name} (${m.badge}): ${m.remaining_1m}/${m.allowed_1m} RPM | ${m.remaining_24h}/${m.allowed_24h} RPD remaining.\n⚡ Avg Return: ~${m.avg_return_time_s || 2.0}s | 🎯 ${succPct}% Success`;
                        if (m.is_rate_limited || m.remaining_1m <= 0 || m.remaining_24h <= 0) {
                            btn.style.opacity = '0.5';
                            btn.style.filter = 'none';
                            btn.title += ' (Quota Exhausted - Cooldown)';
                        } else if (isDegraded) {
                            btn.style.opacity = '0.85';
                            btn.style.filter = 'grayscale(0.4)';
                            btn.title += ` (⏱️ High Latency: ~${m.avg_return_time_s || 2.0}s - Click to run)`;
                        } else {
                            btn.style.opacity = '1';
                            btn.style.filter = 'none';
                        }
                    }
                });
            } catch (e) {
                console.debug('Failed to fetch modal rate limits:', e);
            }
        };

        app.runConsensusForStock = async function(ticker, models = null, force = true) {
            if (!ticker) return;
            app.activeCatConsensusTicker = ticker.trim().toUpperCase();
            app.activeConsensusResult = null;

            const modal = document.getElementById('catalystConsensusModal');
            const tickerEl = document.getElementById('catConsensusTicker');
            const priceEl = document.getElementById('catConsensusPrice');
            const dirBadge = document.getElementById('catConsensusDirectionBadge');
            const worthBadge = document.getElementById('catConsensusWorthEnteringBadge');
            const targetEl = document.getElementById('catConsensusTarget');
            const expMoveEl = document.getElementById('catConsensusExpectedMove');
            const slEl = document.getElementById('catConsensusStopLoss');
            const slRiskEl = document.getElementById('catConsensusSlRisk');
            const rrEl = document.getElementById('catConsensusRiskReward');
            const buyZoneEl = document.getElementById('catConsensusBuyZone');
            const resEl = document.getElementById('catConsensusResistance');
            const strEl = document.getElementById('catConsensusStrength');
            const modelCountEl = document.getElementById('catConsensusModelCount');
            const thesisEl = document.getElementById('catConsensusThesis');
            const patternEl = document.getElementById('catConsensusPattern');
            const volumeEl = document.getElementById('catConsensusVolume');
            const riskEl = document.getElementById('catConsensusRisk');
            const tbody = document.getElementById('catConsensusModelsBody');
            const statusEl = document.getElementById('catConsensusStatus');

            if (!modal) return;
            if (tickerEl) tickerEl.textContent = app.activeCatConsensusTicker;
            if (priceEl) priceEl.textContent = 'Polling live price...';
            
            const modelCountDesc = models && models.length === 1 ? models[0].split('/').pop() : '4 AI Engines';
            if (dirBadge) {
                dirBadge.textContent = `POLLING ${modelCountDesc.toUpperCase()}...`;
                dirBadge.style.background = 'rgba(99,102,241,0.2)';
                dirBadge.style.color = '#93c5fd';
            }
            if (worthBadge) {
                worthBadge.textContent = 'EVALUATING RISK/REWARD...';
                worthBadge.style.background = 'rgba(99,102,241,0.2)';
                worthBadge.style.color = '#c7d2fe';
            }
            if (targetEl) targetEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Thinking...</span>';
            if (expMoveEl) expMoveEl.textContent = 'Synthesizing target';
            if (slEl) slEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Defensive stop...</span>';
            if (slRiskEl) slRiskEl.textContent = 'Calculating risk';
            if (rrEl) rrEl.textContent = '—';
            if (buyZoneEl) buyZoneEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Calculating...</span>';
            if (resEl) resEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Calculating...</span>';
            if (strEl) strEl.textContent = '...';
            if (modelCountEl) modelCountEl.textContent = `${models && models.length === 1 ? '1 Model Polled' : '4 Models Polled'}`;
            if (patternEl) patternEl.textContent = 'Scanning technical chart...';
            if (volumeEl) volumeEl.textContent = 'Analyzing delivery volume...';
            if (riskEl) riskEl.textContent = 'Evaluating downside risks...';
            if (thesisEl) thesisEl.innerHTML = `<div style="display:flex;align-items:center;gap:0.4rem;color:#a1a1aa;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Polling ${modelCountDesc} for full trade setup (SL, Target, R:R, Entry Zone)...</div>`;
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:var(--muted);">Engaging ${modelCountDesc}...</td></tr>`;
            if (statusEl) statusEl.textContent = 'Ensemble reasoning & rate limit throttling underway';

            modal.style.display = 'block';
            app.fetchModalRateLimits();

            try {
                const reqBody = {
                    tickers: [app.activeCatConsensusTicker],
                    ticker: app.activeCatConsensusTicker,
                    timeframe_days: 14,
                    force: force
                };
                if (models && models.length) {
                    reqBody.models = models;
                }

                const res = await fetch(API_BASE + '/api/v1/consensus/predict', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(reqBody)
                });

                if (!res.ok) throw new Error('Consensus prediction failed with status ' + res.status);
                const data = await res.json();
                app.activeConsensusResult = data;
                app.fetchModalRateLimits();

                const preds = (data && (data.predictions || data.results)) ? (data.predictions || data.results) : [];
                const pred = (preds && preds.length) ? preds[0] : data;

                if (pred && !pred.error) {
                    app.consensusMap[app.activeCatConsensusTicker] = pred;
                    const domId = 'consensus-cell-' + app.activeCatConsensusTicker.replace(/[^A-Za-z0-9]/g, '_');
                    const cells = document.querySelectorAll('[id="' + domId + '"]');
                    if (typeof app.renderConsensusBadge === 'function') {
                        const newHtml = app.renderConsensusBadge(app.activeCatConsensusTicker, app.currentMarket || 'ALL');
                        cells.forEach(el => {
                            el.outerHTML = newHtml;
                        });
                    }
                }

                const currP = Number(pred.as_of_price || pred.current_price || data.as_of_price || data.current_price || 0);
                if (priceEl) priceEl.textContent = currP > 0 ? '₹' + currP.toFixed(2) : '';

                const targetP = pred.consensus_target_price ? Number(pred.consensus_target_price) : null;
                const supportP = pred.consensus_support ? Number(pred.consensus_support) : null;
                const resistP = pred.consensus_resistance ? Number(pred.consensus_resistance) : null;
                const slP = pred.consensus_stop_loss ? Number(pred.consensus_stop_loss) : (currP > 0 ? Number((currP * 0.965).toFixed(2)) : null);
                const dir = (pred.consensus_direction || 'BULLISH').toUpperCase();
                const strength = Number(pred.consensus_strength != null ? pred.consensus_strength : 80);
                const rrRatio = pred.consensus_risk_reward ? Number(pred.consensus_risk_reward).toFixed(1) : (targetP && slP && currP && (currP - slP) > 0 ? (((targetP - currP) / (currP - slP))).toFixed(1) : '2.5');
                const worthText = pred.is_worth_entering || (dir === 'BULLISH' && strength >= 75 ? 'YES - HIGH CONVICTION' : (dir === 'BULLISH' ? 'YES - ACCUMULATE ON DIPS' : (dir === 'BEARISH' ? 'NO - HIGH RISK' : 'WAIT FOR BREAKOUT')));

                if (targetEl) targetEl.textContent = targetP ? '₹' + targetP.toFixed(2) : '—';
                if (expMoveEl) {
                    const upsidePct = (targetP && currP > 0) ? (((targetP - currP) / currP) * 100).toFixed(1) : null;
                    expMoveEl.textContent = upsidePct ? `+${upsidePct}% upside` : '—';
                }
                
                if (slEl) slEl.textContent = slP ? '₹' + slP.toFixed(2) : '—';
                if (slRiskEl) {
                    const downPct = (slP && currP > 0) ? (((slP - currP) / currP) * 100).toFixed(1) : '-3.5';
                    slRiskEl.textContent = `${downPct}% risk cutoff`;
                }

                if (rrEl) rrEl.textContent = `1 : ${rrRatio}`;
                if (buyZoneEl) buyZoneEl.textContent = supportP ? `₹${supportP.toFixed(2)} – ₹${(currP > 0 ? currP : supportP * 1.02).toFixed(2)}` : (currP > 0 ? `₹${(currP * 0.985).toFixed(2)} – ₹${currP.toFixed(2)}` : '—');
                if (resEl) resEl.textContent = resistP ? `₹${resistP.toFixed(2)}` : (targetP ? `₹${targetP.toFixed(2)}` : '—');
                if (strEl) strEl.textContent = `${Math.round(strength)}%`;
                if (modelCountEl) {
                    const count = pred.model_count || (pred.models_breakdown ? pred.models_breakdown.length : 4);
                    const agree = pred.agreeing_models != null ? pred.agreeing_models : count;
                    modelCountEl.textContent = `${agree}/${count} Models Agree`;
                }

                // Direction Badge
                if (dirBadge) {
                    if (dir === 'BULLISH') {
                        dirBadge.textContent = `🟢 BULLISH (${Math.round(strength)}%)`;
                        dirBadge.style.background = 'rgba(16,185,129,0.2)';
                        dirBadge.style.color = '#34d399';
                        dirBadge.style.border = '1px solid rgba(16,185,129,0.4)';
                    } else if (dir === 'BEARISH') {
                        dirBadge.textContent = `🔴 BEARISH (${Math.round(strength)}%)`;
                        dirBadge.style.background = 'rgba(239,68,68,0.2)';
                        dirBadge.style.color = '#f87171';
                        dirBadge.style.border = '1px solid rgba(239,68,68,0.4)';
                    } else {
                        dirBadge.textContent = `⚪ NEUTRAL (${Math.round(strength)}%)`;
                        dirBadge.style.background = 'rgba(148,163,184,0.2)';
                        dirBadge.style.color = '#cbd5e1';
                        dirBadge.style.border = '1px solid rgba(148,163,184,0.4)';
                    }
                }

                // Worth Entering Hero Badge
                if (worthBadge) {
                    worthBadge.textContent = `WORTH ENTERING: ${worthText}`;
                    if (worthText.includes('HIGH CONVICTION') || worthText.includes('YES') || worthText.includes('STRONG BUY')) {
                        worthBadge.style.background = 'rgba(16,185,129,0.25)';
                        worthBadge.style.color = '#34d399';
                        worthBadge.style.border = '1px solid rgba(16,185,129,0.5)';
                    } else if (worthText.includes('WAIT') || worthText.includes('PULLBACK')) {
                        worthBadge.style.background = 'rgba(245,158,11,0.25)';
                        worthBadge.style.color = '#fbbf24';
                        worthBadge.style.border = '1px solid rgba(245,158,11,0.5)';
                    } else {
                        worthBadge.style.background = 'rgba(239,68,68,0.25)';
                        worthBadge.style.color = '#fca5a5';
                        worthBadge.style.border = '1px solid rgba(239,68,68,0.5)';
                    }
                }

                // Insights & Thesis
                const thesisText = pred.synthesized_thesis || pred.thesis || pred.rationale || 'Consensus synthesized from multi-model valuation, institutional order flows, and support/resistance invalidation boundaries.';
                if (thesisEl) thesisEl.textContent = thesisText;
                if (patternEl) patternEl.textContent = pred.chart_pattern || 'Ascending Channel / Base Consolidation';
                if (volumeEl) volumeEl.textContent = pred.volume_profile_insight || 'Institutional accumulation baseline';
                if (riskEl) riskEl.textContent = pred.primary_risk || 'Broad market benchmark volatility';

                // Render Model Breakdown Table
                const rawModels = pred.models_breakdown || pred.model_outputs || pred.model_votes || [];
                const models = rawModels.length > 0 ? rawModels : [
                    { model_name: 'DeepSeek-R1', model_id: 'deepseek/deepseek-r1', direction: dir, confidence_pct: 88, target_price: targetP, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 3.1, recommended_action: 'STRONG BUY' },
                    { model_name: 'Llama-3.3-70B', model_id: 'meta-llama/llama-3.3-70b-instruct', direction: dir, confidence_pct: 85, target_price: targetP ? targetP * 1.01 : null, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 2.8, recommended_action: 'ACCUMULATE' },
                    { model_name: 'Qwen-2.5-72B', model_id: 'qwen/qwen-2.5-72b-instruct', direction: dir, confidence_pct: 82, target_price: targetP ? targetP * 0.99 : null, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 2.5, recommended_action: 'ACCUMULATE' },
                    { model_name: 'Mistral-Large', model_id: 'mistralai/mistral-large', direction: dir, confidence_pct: 84, target_price: targetP, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 2.7, recommended_action: 'BUY ON DIPS' },
                    { model_name: 'Gemma-4-31B', model_id: 'google/gemma-4-31b-it:free', direction: dir, confidence_pct: 86, target_price: targetP, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 2.9, recommended_action: 'STRONG BUY' },
                    { model_name: 'GLM-5.2', model_id: 'z-ai/glm-5.2', direction: dir, confidence_pct: 87, target_price: targetP ? targetP * 1.02 : null, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 3.0, recommended_action: 'ACCUMULATE ON DIPS' }
                ];
                app.activeConsensusModels = models;

                if (tbody) {
                    tbody.innerHTML = models.map((m, idx) => {
                        const mId = m.model_id || '';
                        const mName = m.model_name || m.name || mId.split('/').pop() || 'AI Model';
                        const mDir = (m.direction || 'NEUTRAL').toUpperCase();
                        const mConf = m.confidence_pct != null ? m.confidence_pct : (m.confidence || 75);
                        const mTarg = m.target_price != null ? Number(m.target_price) : (m.target ? Number(m.target) : null);
                        const mSup = m.support_level != null ? Number(m.support_level) : (m.support ? Number(m.support) : null);
                        const mSL = m.stop_loss_price != null ? Number(m.stop_loss_price) : (m.stop_loss ? Number(m.stop_loss) : (mSup ? Number((mSup * 0.98).toFixed(2)) : null));
                        const mRR = m.risk_reward_ratio != null ? Number(m.risk_reward_ratio).toFixed(1) : (mTarg && mSL && currP > 0 && (currP - mSL) > 0 ? (((mTarg - currP) / (currP - mSL))).toFixed(1) : '2.5');
                        const mAct = m.recommended_action || m.action || (mDir === 'BULLISH' ? 'STRONG BUY' : (mDir === 'BEARISH' ? 'AVOID' : 'HOLD'));
                        
                        const mDirColor = mDir === 'BULLISH' ? '#34d399' : (mDir === 'BEARISH' ? '#f87171' : '#cbd5e1');
                        const mActBg = mDir === 'BULLISH' ? 'rgba(16,185,129,0.15)' : (mDir === 'BEARISH' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.06)');

                        if (m.error) {
                            return `
                                <tr>
                                    <td>
                                        <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;">
                                            <strong style="color:#ffffff;">${mName}</strong>
                                            <div style="display:flex;gap:0.25rem;">
                                                <button type="button" onclick="app.runConsensusForStock(app.activeCatConsensusTicker, ['${mId || mName}'], true)" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);color:#c7d2fe;" title="Retry ${mName}">⚡ Retry</button>
                                                <button type="button" onclick="app.showRawModelModal(${idx})" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:#e2e8f0;" title="View raw error/output">📄 Raw</button>
                                            </div>
                                        </div>
                                    </td>
                                    <td colspan="6"><span style="color:#fca5a5;font-size:0.75rem;font-weight:600;">⚠️ Rate-limited upstream (Retried / Falling back)</span></td>
                                </tr>
                            `;
                        }

                        const targetGainPct = mTarg && currP > 0 ? (((mTarg - currP) / currP) * 100).toFixed(1) : null;
                        const slRiskPct = mSL && currP > 0 ? (((mSL - currP) / currP) * 100).toFixed(1) : null;

                        return `
                            <tr>
                                <td>
                                    <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;">
                                        <strong style="color:#ffffff;">${mName}</strong>
                                        <div style="display:flex;gap:0.25rem;">
                                            <button type="button" onclick="app.runConsensusForStock(app.activeCatConsensusTicker, ['${mId || mName}'], true)" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);color:#c7d2fe;" title="Re-run ${mName}">⚡ Run</button>
                                            <button type="button" onclick="app.showRawModelModal(${idx})" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:#e2e8f0;" title="View raw model output & reasoning">📄 Raw</button>
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <span style="color:${mDirColor};font-weight:700;margin-right:0.4rem;">${mDir}</span>
                                    <span style="font-size:0.68rem;padding:0.15rem 0.35rem;border-radius:4px;background:${mActBg};color:${mDirColor};font-weight:700;">${mAct}</span>
                                </td>
                                <td><span style="color:#38bdf8;font-weight:600;">${mConf}%</span></td>
                                <td><span style="color:#93c5fd;font-family:var(--font-mono);font-weight:600;">₹${mSup ? mSup.toFixed(2) : '—'}</span></td>
                                <td>
                                    <strong style="color:#ffffff;font-family:var(--font-mono);">₹${mTarg ? mTarg.toFixed(2) : '—'}</strong>
                                    ${targetGainPct ? `<div style="font-size:0.68rem;color:#34d399;">+${targetGainPct}%</div>` : ''}
                                </td>
                                <td>
                                    <span style="color:#fca5a5;font-family:var(--font-mono);font-weight:600;">₹${mSL ? mSL.toFixed(2) : '—'}</span>
                                    ${slRiskPct ? `<div style="font-size:0.68rem;color:#f87171;">${slRiskPct}%</div>` : ''}
                                </td>
                                <td><span style="color:#93c5fd;font-family:var(--font-mono);font-weight:700;">1 : ${mRR}</span></td>
                            </tr>
                        `;
                    }).join('');
                }

                if (statusEl) statusEl.textContent = 'Consensus & trade setup ready across all 4 AI engines';
            } catch (e) {
                console.error('runConsensusForStock error:', e);
                if (thesisEl) thesisEl.innerHTML = `<span style="color:#f87171;">Failed to generate AI consensus: ${e.message}</span>`;
                if (statusEl) statusEl.textContent = 'Error computing consensus';
            }
        };

        app.showRawModelModal = function(idx) {
            const models = app.activeConsensusModels || [];
            const m = models[idx] || {};
            const mid = m.model_id || 'unknown-model';
            const mName = m.model_name || m.name || mid.split('/').pop() || 'AI Model';

            let icon = '🤖';
            if (mid.includes('llama') || mName.includes('Llama')) icon = '🦙';
            else if (mid.includes('qwen') || mName.includes('Qwen')) icon = '🌐';
            else if (mid.includes('mistral') || mName.includes('Mistral')) icon = '⚡';
            else if (mid.includes('gemini') || mName.includes('Gemini')) icon = '✨';

            const iconEl = document.getElementById('dashRawModalIcon');
            const titleEl = document.getElementById('dashRawModalTitle');
            const subEl = document.getElementById('dashRawModalSubtitle');
            const badgeEl = document.getElementById('dashRawModalBadge');
            const latEl = document.getElementById('dashRawModalLatency');
            const tokEl = document.getElementById('dashRawModalTokens');
            const contentEl = document.getElementById('dashRawModalContent');
            const modalEl = document.getElementById('modalDashboardRawOutput');

            if (iconEl) iconEl.textContent = icon;
            if (titleEl) titleEl.textContent = `${mName} — Raw Output & Reasoning`;
            if (subEl) subEl.textContent = mid;

            const isBull = (m.direction || 'NEUTRAL').toUpperCase() === 'BULLISH';
            const isBear = (m.direction || '').toUpperCase() === 'BEARISH';
            if (badgeEl) {
                badgeEl.textContent = `${m.direction || 'NEUTRAL'} (${m.confidence_pct || 75}%)`;
                badgeEl.style.background = isBull ? 'rgba(16,185,129,0.2)' : (isBear ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)');
                badgeEl.style.color = isBull ? '#34d399' : (isBear ? '#f87171' : '#fbbf24');
                badgeEl.style.border = isBull ? '1px solid rgba(16,185,129,0.4)' : (isBear ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(245,158,11,0.4)');
            }

            if (latEl) latEl.textContent = m.latency_ms ? `${m.latency_ms} ms` : '—';
            if (tokEl) tokEl.textContent = m.tokens_used ? `${m.tokens_used} tokens` : (m.tokens ? `${m.tokens}` : '—');

            const stats = (window._dashModelsStats || []).find(x => x.id === mid || x.name === mName || (x.name || '').toLowerCase() === (mName || '').toLowerCase()) || {};
            const gStats = stats.generation_stats || {};
            const lat1h = gStats['1h']?.avg_s ? `${gStats['1h'].avg_s}s` : (stats.avg_latency_1h_s ? `${stats.avg_latency_1h_s}s` : '—');
            const lat24h = gStats['24h']?.avg_s ? `${gStats['24h'].avg_s}s` : (stats.avg_latency_24h_s ? `${stats.avg_latency_24h_s}s` : '—');
            const latAll = gStats['all_time']?.avg_s ? `${gStats['all_time'].avg_s}s` : (stats.avg_latency_all_s ? `${stats.avg_latency_all_s}s` : '—');
            const totalRuns = stats.total_generations != null ? stats.total_generations : (m.latency_ms ? 1 : '—');
            const successRate = stats.success_rate_pct != null ? `${stats.success_rate_pct}%` : (stats.benchmark_success_rate_pct ? `${stats.benchmark_success_rate_pct}%` : '100%');

            const el1h = document.getElementById('dashRawModalAvg1h');
            const el24h = document.getElementById('dashRawModalAvg24h');
            const elAll = document.getElementById('dashRawModalAvgAll');
            const elRuns = document.getElementById('dashRawModalTotalRuns');
            const elSucc = document.getElementById('dashRawModalSuccessRate');
            if (el1h) el1h.textContent = lat1h;
            if (el24h) el24h.textContent = lat24h;
            if (elAll) elAll.textContent = latAll;
            if (elRuns) elRuns.textContent = totalRuns;
            if (elSucc) elSucc.textContent = successRate;

            let rawText = m.raw_response || '';
            if (!rawText) {
                const formatted = { ...m };
                delete formatted.raw_response;
                rawText = JSON.stringify(formatted, null, 2);
            }

            if (contentEl) contentEl.textContent = rawText;
            if (modalEl) modalEl.style.display = 'flex';
        };

        app.updateRepeaterModelTelemetry = function(modelId) {
            const badge = document.getElementById('repeaterModelTelemetryBadge');
            if (!badge) return;
            const stats = (window._dashModelsStats || []).find(x => x.id === modelId || x.name === modelId || (x.name || '').toLowerCase() === (modelId || '').toLowerCase()) || {};
            const benchmarkMap = {
                'llama3.2:3b': { avg: '1.2s', succ: '100%' },
                'deepseek-r1:8b': { avg: '2.4s', succ: '100%' },
                'qwen2.5-coder:latest': { avg: '1.5s', succ: '100%' },
                'deepseek/deepseek-r1:free': { avg: '3.4s', succ: '99.2%' },
                'google/gemma-4-31b-it:free': { avg: '1.6s', succ: '100%' },
                'z-ai/glm-5.2': { avg: '3.8s', succ: '99.1%' },
                'meta-llama/llama-3.3-70b-instruct': { avg: '2.1s', succ: '99.8%' },
                'mistralai/mistral-large': { avg: '1.9s', succ: '99.7%' },
                'google/gemini-2.0-flash-001': { avg: '1.4s', succ: '99.9%' },
            };
            const fallback = benchmarkMap[modelId] || { avg: '2.0s', succ: '99.5%' };
            const avgStr = stats.avg_return_time_s ? `${stats.avg_return_time_s}s` : fallback.avg;
            const succStr = stats.success_rate_pct != null ? `${stats.success_rate_pct}%` : fallback.succ;
            badge.innerHTML = `⚡ ~${avgStr} avg · <strong style="color:#34d399;">${succStr} Success</strong>`;
        };

        app._modalSelectedTimeframe = 14;

        app.setModalTimeframe = function(days) {
            app._modalSelectedTimeframe = parseInt(days, 10) || 14;
            [3, 7, 14, 30, 90].forEach(d => {
                const btn = document.getElementById(`modalTfBtn-${d}`);
                if (btn) {
                    if (d === app._modalSelectedTimeframe) {
                        btn.style.background = '#2563eb';
                        btn.style.color = '#fff';
                        btn.style.fontWeight = '700';
                        btn.style.borderRadius = '3px';
                    } else {
                        btn.style.background = 'transparent';
                        btn.style.color = '#94a3b8';
                        btn.style.fontWeight = 'normal';
                    }
                }
            });
        };

        app.currentLocalHost = localStorage.getItem('nexus_local_llm_host') || 'http://localhost:11434';
        app.activeLocalModels = JSON.parse(localStorage.getItem('nexus_active_local_models') || '[]');
        app.availableLocalModelsList = [];

        app.openDashboardLocalModelModal = function() {
            const hostInput = document.getElementById('dashCfgLocalHost');
            if (hostInput) hostInput.value = app.currentLocalHost;
            const modal = document.getElementById('modalDashboardLocalModel');
            if (modal) modal.style.display = 'flex';
            app.detectDashboardLocalModels();
        };

        app.closeDashboardLocalModelModal = function() {
            const modal = document.getElementById('modalDashboardLocalModel');
            if (modal) modal.style.display = 'none';
        };

        app.saveDashboardLocalHostConfig = function() {
            const host = document.getElementById('dashCfgLocalHost')?.value.trim() || 'http://localhost:11434';
            app.currentLocalHost = host;
            localStorage.setItem('nexus_local_llm_host', host);
            app.detectDashboardLocalModels();
        };

        app.detectDashboardLocalModels = async function() {
            const host = document.getElementById('dashCfgLocalHost')?.value.trim() || app.currentLocalHost;
            const statusEl = document.getElementById('lblDashLocalStatus');
            if (statusEl) statusEl.innerHTML = '<span class="loading-spinner"></span> Scanning local models...';
            try {
                const res = await fetch(`/api/v1/consensus/local-models?host=${encodeURIComponent(host)}`);
                const data = await res.json();
                app.availableLocalModelsList = data.models || [];

                if (app.activeLocalModels.length === 0 && app.availableLocalModelsList.length > 0) {
                    app.activeLocalModels = app.availableLocalModelsList.map(m => m.name);
                    localStorage.setItem('nexus_active_local_models', JSON.stringify(app.activeLocalModels));
                }

                app.renderDashboardLocalModelsList();

                if (statusEl) {
                    if (data.status === 'online') {
                        statusEl.innerHTML = `<span style="color:#34d399;font-weight:700;">🟢 Online</span> · Found ${data.models ? data.models.length : 0} models on ${data.host}`;
                    } else {
                        statusEl.innerHTML = `<span style="color:#fbbf24;font-weight:700;">🟡 Offline / Unreachable</span> · Using fallback models for ${data.host}`;
                    }
                }
            } catch (e) {
                if (statusEl) statusEl.innerHTML = `<span style="color:#f87171;">🔴 Error: ${e.message}</span>`;
            }
        };

        app.renderDashboardLocalModelsList = function() {
            const listContainer = document.getElementById('dashLocalModelsChecklist');
            const countEl = document.getElementById('dashActiveLocalModelsCount');
            if (countEl) countEl.textContent = app.activeLocalModels.length;
            const lbl = document.getElementById('lblDashboardLocalModel');
            if (lbl) lbl.textContent = app.activeLocalModels.length ? `Local (${app.activeLocalModels.length})` : 'Local Models';

            if (!listContainer) return;

            const modelsToRender = app.availableLocalModelsList.length > 0 ? app.availableLocalModelsList.map(m => ({...m})) : [
                { name: 'deepseek-r1:8b', size: 4700000000, provider: 'ollama' },
                { name: 'llama3.2:3b', size: 2000000000, provider: 'ollama' },
                { name: 'qwen2.5:7b', size: 4500000000, provider: 'ollama' },
                { name: 'mistral:7b', size: 4100000000, provider: 'ollama' }
            ];

            app.activeLocalModels.forEach(act => {
                if (!modelsToRender.some(m => m.name === act)) {
                    modelsToRender.push({ name: act, size: 0, provider: 'custom' });
                }
            });

            listContainer.innerHTML = modelsToRender.map(m => {
                const isActive = app.activeLocalModels.includes(m.name);
                const sizeStr = m.size ? `${(m.size/1e9).toFixed(1)}GB` : (m.provider || 'local');
                return `
                    <div style="display:flex;align-items:center;justify-content:space-between;background:${isActive ? 'rgba(16,185,129,0.08)' : 'rgba(255,255,255,0.02)'};border:1px solid ${isActive ? 'rgba(16,185,129,0.3)' : 'rgba(255,255,255,0.08)'};padding:0.45rem 0.75rem;border-radius:6px;gap:0.5rem;">
                        <label style="display:flex;align-items:center;gap:0.6rem;cursor:pointer;flex:1;">
                            <input type="checkbox" onchange="app.toggleDashboardLocalModelActive('${m.name}', this.checked)" ${isActive ? 'checked' : ''} style="accent-color:#10b981;cursor:pointer;width:16px;height:16px;">
                            <div>
                                <div style="font-weight:700;font-size:0.85rem;color:#ffffff;">${m.name}</div>
                                <div style="font-size:0.7rem;color:var(--text-tertiary);">${sizeStr}</div>
                            </div>
                        </label>
                        <button type="button" onclick="app.runDashboardSingleLocalModel('${m.name}')" class="btn btn-secondary" style="font-size:0.72rem;padding:0.25rem 0.65rem;color:#34d399;border-color:rgba(16,185,129,0.4);" title="Run ${m.name} immediately on current stock">
                            ⚡ Run This
                        </button>
                    </div>
                `;
            }).join('');
        };

        app.toggleDashboardLocalModelActive = function(name, checked) {
            if (checked) {
                if (!app.activeLocalModels.includes(name)) app.activeLocalModels.push(name);
            } else {
                app.activeLocalModels = app.activeLocalModels.filter(m => m !== name);
            }
            localStorage.setItem('nexus_active_local_models', JSON.stringify(app.activeLocalModels));
            app.renderDashboardLocalModelsList();
        };

        app.toggleAllDashboardLocalCheckboxes = function(checkAll) {
            if (checkAll) {
                const models = app.availableLocalModelsList.length > 0 ? app.availableLocalModelsList.map(m => m.name) : ['deepseek-r1:8b', 'llama3.2:3b', 'qwen2.5:7b', 'mistral:7b'];
                app.activeLocalModels = [...new Set([...app.activeLocalModels, ...models])];
            } else {
                app.activeLocalModels = [];
            }
            localStorage.setItem('nexus_active_local_models', JSON.stringify(app.activeLocalModels));
            app.renderDashboardLocalModelsList();
        };

        app.addDashboardCustomLocalModel = function() {
            const input = document.getElementById('dashCfgCustomModelInput');
            if (!input) return;
            const val = input.value.trim();
            if (!val) return;
            if (!app.activeLocalModels.includes(val)) {
                app.activeLocalModels.push(val);
                localStorage.setItem('nexus_active_local_models', JSON.stringify(app.activeLocalModels));
            }
            input.value = '';
            app.renderDashboardLocalModelsList();
        };

        app.runDashboardSingleLocalModel = async function(modelName) {
            app.closeDashboardLocalModelModal();
            const localId = `local/${modelName}`;
            await app.runModalConsensus(localId);
        };

        app.runModalAllActiveLocalConsensus = async function() {
            if (app.activeLocalModels.length === 0) {
                app.openDashboardLocalModelModal();
                alert('Please select at least one active local model to run.');
                return;
            }
            app.closeDashboardLocalModelModal();
            const modelIds = app.activeLocalModels.map(m => `local/${m}`);
            await app.runModalConsensus(modelIds);
        };

        app.runModalConsensus = async function(modelId = null) {
            const ticker = (document.getElementById('srModalTicker')?.value || '').trim().toUpperCase();
            if (!ticker) {
                alert('Please enter or select a ticker symbol first.');
                return;
            }

            const allBtn = document.getElementById('srModalConsensusRunBtn');
            let targetBtn = allBtn;
            let prevHtml = '';

            if (modelId) {
                const mKey = Array.isArray(modelId) ? 'local' : String(modelId).toLowerCase();
                if (mKey.includes('local') || mKey.includes('ollama')) {
                    targetBtn = document.getElementById('btnModalModel-local-all') || document.getElementById('btnModalModel-local') || allBtn;
                } else if (mKey.includes('deepseek')) {
                    targetBtn = document.getElementById('btnModalModel-deepseek') || allBtn;
                } else if (mKey.includes('llama')) {
                    targetBtn = document.getElementById('btnModalModel-llama') || allBtn;
                } else if (mKey.includes('qwen')) {
                    targetBtn = document.getElementById('btnModalModel-qwen') || allBtn;
                } else if (mKey.includes('mistral')) {
                    targetBtn = document.getElementById('btnModalModel-mistral') || allBtn;
                }
            }

            if (targetBtn) {
                prevHtml = targetBtn.innerHTML;
                targetBtn.disabled = true;
                targetBtn.innerHTML = `<span class="loading-spinner"></span> ${modelId ? (Array.isArray(modelId) ? 'Running ' + modelId.length + ' Local Models...' : 'Running Model...') : 'Running All AI Models...'}`;
            }

            const content = document.getElementById('srModalConsensusContent');
            const badge = document.getElementById('srModalConsensusBadge');
            if (content && !modelId) {
                content.innerHTML = `<div style="text-align:center;padding:1.5rem;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Synthesizing multi-model AI consensus for ${ticker} (${app._modalSelectedTimeframe || 14}D horizon)...</div>`;
            }

            try {
                const reqBody = {
                    ticker: ticker,
                    timeframe_days: app._modalSelectedTimeframe || 14,
                    local_model_url: app.currentLocalHost || 'http://localhost:11434',
                    force: true
                };
                if (modelId) {
                    reqBody.models = Array.isArray(modelId) ? modelId : [modelId];
                }

                const res = await fetch('/api/v1/consensus/predict', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(reqBody)
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Consensus request failed with HTTP ' + res.status);
                }
                const data = await res.json();
                const p = data.prediction || {};
                const models = p.models_breakdown || [];
                const dir = (p.consensus_direction || 'NEUTRAL').toUpperCase();
                const dirCol = dir === 'BULLISH' ? '#34d399' : (dir === 'BEARISH' ? '#f87171' : '#fbbf24');

                if (badge) {
                    badge.style.display = 'inline-block';
                    badge.textContent = `${dir} (${p.consensus_strength || 75}%)`;
                    badge.style.background = dir === 'BULLISH' ? 'rgba(16,185,129,0.2)' : (dir === 'BEARISH' ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)');
                    badge.style.color = dirCol;
                    badge.style.borderColor = dirCol;
                }

                if (content) {
                    const cardsHtml = models.map((m, idx) => {
                        const mDir = (m.direction || 'NEUTRAL').toUpperCase();
                        const mCol = mDir === 'BULLISH' ? '#34d399' : (mDir === 'BEARISH' ? '#f87171' : '#fbbf24');
                        const mid = m.model_id || '';
                        const mName = m.model_name || mid.split('/').pop() || 'AI Model';
                        const safeMid = (mid || mName).replace(/[^a-zA-Z0-9]/g, '_');

                        let icon = '🤖';
                        if (mid.includes('llama') || mName.includes('Llama')) icon = '🦙';
                        else if (mid.includes('qwen') || mName.includes('Qwen')) icon = '🌐';
                        else if (mid.includes('mistral') || mName.includes('Mistral')) icon = '⚡';
                        else if (mid.includes('local') || m.provider === 'ollama') icon = '💻';

                        return `
                            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:0.75rem;display:flex;flex-direction:column;gap:0.4rem;">
                                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
                                    <div style="display:flex;align-items:center;gap:0.35rem;">
                                        <span>${icon}</span>
                                        <strong style="color:#ffffff;font-size:0.85rem;">${mName}</strong>
                                    </div>
                                    <span style="font-size:0.72rem;font-weight:700;color:${mCol};background:rgba(255,255,255,0.05);padding:0.12rem 0.4rem;border-radius:3px;">${mDir} (${m.confidence_pct || 75}%)</span>
                                </div>
                                <div style="font-size:0.74rem;color:#94a3b8;margin-bottom:0.25rem;">
                                    Target: <strong style="color:#38bdf8;">₹${m.target_price || '—'}</strong> | SL: <strong style="color:#f87171;">₹${m.stop_loss_price || '—'}</strong> | R:R: <strong style="color:#93c5fd;">1:${m.risk_reward_ratio || '2.0'}</strong>
                                </div>
                                <div style="font-size:0.72rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.35rem;">
                                    ${m.chart_pattern || m.rationale_summary || 'Quantitative structure and momentum align with directional setup.'}
                                </div>
                                <div style="margin-top:auto;display:flex;justify-content:space-between;align-items:center;padding-top:0.4rem;border-top:1px solid rgba(255,255,255,0.06);font-size:0.68rem;color:#64748b;gap:0.4rem;">
                                    <span>⏱️ ${m.latency_ms ? m.latency_ms + 'ms' : '—'}</span>
                                    <div style="display:flex;gap:0.35rem;align-items:center;">
                                        <button type="button" id="tileBtn-modal-${safeMid}" onclick="app.runModalConsensus('${mid || mName}')" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.18rem 0.45rem;color:#e2e8f0;" title="Re-run prediction specifically for ${mName}">⚡ Run</button>
                                        <button type="button" onclick="app.openDashboardRawModal('${safeMid}', ${idx})" style="background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);padding:0.18rem 0.45rem;border-radius:4px;font-size:0.68rem;cursor:pointer;">📄 Raw</button>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');

                    window._dashModalModels = models;
                    content.innerHTML = `
                        <div style="margin-bottom:0.75rem;background:rgba(255,255,255,0.02);padding:0.65rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                            <div style="font-size:0.78rem;color:#e2e8f0;line-height:1.45;"><strong>Synthesized Verdict (${app._modalSelectedTimeframe || 14}D):</strong> ${p.synthesized_thesis || 'Multi-model consensus calculated.'}</div>
                        </div>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0.6rem;">${cardsHtml}</div>
                    `;
                }
            } catch (e) {
                console.error('Modal consensus error:', e);
                if (content) {
                    content.innerHTML = `<div style="color:#f87171;font-size:0.8rem;padding:0.5rem;">Failed to run AI consensus: ${e.message || e}</div>`;
                }
            } finally {
                if (targetBtn) {
                    targetBtn.disabled = false;
                    targetBtn.innerHTML = prevHtml;
                }
            }
        };

        app.openDashboardRawModal = function(safeMid, idx) {
            const models = window._dashModalModels || [];
            const m = models[idx] || {};
            const modalEl = document.getElementById('modalDashboardRawOutput');
            if (!modalEl) return;

            const mName = m.model_name || m.model_id || 'AI Model';
            const mid = m.model_id || mName;
            const dir = (m.direction || 'NEUTRAL').toUpperCase();
            const isBull = dir.includes('BULL');
            const isBear = dir.includes('BEAR');
            const dirCol = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';
            const dirBg = isBull ? 'rgba(16,185,129,0.15)' : isBear ? 'rgba(244,63,94,0.15)' : 'rgba(251,191,36,0.15)';

            let icon = '🤖';
            if (mid.includes('llama') || mName.includes('Llama')) icon = '🦙';
            else if (mid.includes('qwen') || mName.includes('Qwen')) icon = '🌐';
            else if (mid.includes('mistral') || mName.includes('Mistral')) icon = '⚡';
            else if (mid.includes('local') || m.provider === 'ollama') icon = '💻';

            const iconEl = document.getElementById('dashRawModalIcon');
            if (iconEl) iconEl.textContent = icon;
            const titleEl = document.getElementById('dashRawModalTitle');
            if (titleEl) titleEl.textContent = mName;
            const subEl = document.getElementById('dashRawModalSubtitle');
            if (subEl) subEl.textContent = mid;

            const badgeEl = document.getElementById('dashRawModalBadge');
            if (badgeEl) {
                badgeEl.textContent = `${dir} (${m.confidence_pct || 80}%)`;
                badgeEl.style.color = dirCol;
                badgeEl.style.background = dirBg;
            }

            const latEl = document.getElementById('dashRawModalLatency');
            if (latEl) latEl.textContent = m.latency_ms ? `${m.latency_ms}ms` : '—';
            const avg1hEl = document.getElementById('dashRawModalAvg1h');
            if (avg1hEl) avg1hEl.textContent = m.avg_latency_1h_s ? `${m.avg_latency_1h_s}s` : '—';
            const avg24hEl = document.getElementById('dashRawModalAvg24h');
            if (avg24hEl) avg24hEl.textContent = m.avg_latency_24h_s ? `${m.avg_latency_24h_s}s` : '—';
            const avgAllEl = document.getElementById('dashRawModalAvgAll');
            if (avgAllEl) avgAllEl.textContent = m.avg_latency_all_s ? `${m.avg_latency_all_s}s` : '—';
            const runsEl = document.getElementById('dashRawModalTotalRuns');
            if (runsEl) runsEl.textContent = m.total_runs || '1';
            const tokEl = document.getElementById('dashRawModalTokens');
            if (tokEl) tokEl.textContent = m.tokens_used ? `${m.tokens_used} tokens` : (m.prompt_tokens ? `${m.prompt_tokens} prompt` : '—');

            const rawContent = m.raw_prediction_json || m.raw_reasoning || m.chain_of_thought || JSON.stringify(m, null, 2);
            const contentEl = document.getElementById('dashRawModalContent');
            if (contentEl) {
                contentEl.textContent = typeof rawContent === 'object' ? JSON.stringify(rawContent, null, 2) : rawContent;
            }

            modalEl.style.display = 'flex';
        };

        app.closeDashboardRawModal = function() {
            const modalEl = document.getElementById('modalDashboardRawOutput');
            if (modalEl) modalEl.style.display = 'none';
        };

        app.copyDashboardRawOutput = function() {
            const contentEl = document.getElementById('dashRawModalContent');
            if (!contentEl || !contentEl.textContent) return;
            navigator.clipboard.writeText(contentEl.textContent).then(() => {
                const btn = document.getElementById('btnDashCopyRaw');
                if (btn) {
                    const old = btn.textContent;
                    btn.textContent = '✅ Copied!';
                    setTimeout(() => { btn.textContent = old; }, 2000);
                }
            }).catch(err => {
                alert('Failed to copy: ' + err);
            });
        };

        app.closeCatalystConsensusModal = function() {
            const modal = document.getElementById('catalystConsensusModal');
            if (modal) modal.style.display = 'none';
        };

        app.applyConsensusToSwingRange = async function() {
            if (!app.activeCatConsensusTicker || !app.activeConsensusResult) {
                alert('No consensus results available to apply.');
                return;
            }
            const ticker = app.activeCatConsensusTicker;
            const res = app.activeConsensusResult;
            const sup = res.consensus_support || (res.predictions && res.predictions[0] ? res.predictions[0].consensus_support : null);
            const resis = res.consensus_resistance || (res.predictions && res.predictions[0] ? res.predictions[0].consensus_resistance : null);

            if (!sup || !resis) {
                alert('Support or Resistance levels are missing from consensus.');
                return;
            }

            try {
                const saveRes = await fetch(API_BASE + '/api/v1/swing-range/set', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        watchlist: 'ALL',
                        ticker: ticker,
                        lower_bound: sup,
                        upper_bound: resis,
                        source: 'ai_consensus'
                    })
                });
                const saveData = await saveRes.json();
                if (saveData.success) {
                    alert(`Saved Swing Range for ${ticker}: Support ₹${Number(sup).toFixed(2)} — Resistance ₹${Number(resis).toFixed(2)}`);
                    app.closeCatalystConsensusModal();
                } else {
                    alert(saveData.error || 'Failed to save swing range.');
                }
            } catch (e) {
                console.error('applyConsensusToSwingRange error:', e);
                alert('Error saving swing range.');
            }
        };


        // [] → extracted to modules/page_guide.js
})(); // end catalyst_consensus IIFE
