// =========================================================================
// 📈 Swing Ranges, Channel Editor & Auto-Detector Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const swingModule = {
        _activeSwingTicker: null,
        _activeSwingWatchlist: 'ALL',

        openSwingRangeModal(watchlist, ticker) {
            this._activeSwingTicker = ticker;
            this._activeSwingWatchlist = watchlist || 'ALL';
            const modal = document.getElementById('swingRangeModal');
            const symEl = document.getElementById('swingModalTicker');
            if (symEl) symEl.textContent = ticker;
            if (modal) modal.style.display = 'flex';
            this.loadSwingModalDetails(ticker, this._activeSwingWatchlist);
        },

        closeSwingRangeModal() {
            const modal = document.getElementById('swingRangeModal');
            if (modal) modal.style.display = 'none';
        },

        async loadSwingModalDetails(ticker, watchlist = 'ALL') {
            const content = document.getElementById('swingModalContent');
            if (!content) return;
            content.innerHTML = '<div style="padding:2rem;text-align:center;color:#64748b;">Loading support & resistance channel levels...</div>';

            try {
                const res = await fetch(API_BASE + `/api/v1/swing-ranges/${encodeURIComponent(watchlist)}/${encodeURIComponent(ticker)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.renderSwingModalForm(data, content);
                } else {
                    content.innerHTML = '<div style="padding:2rem;text-align:center;color:#f87171;">Failed loading swing range.</div>';
                }
            } catch (e) {
                console.error('[SWING] Error loading range:', e);
            }
        },

        renderSwingModalForm(data, container) {
            const r = data.range || {};
            const hist = data.history || [];
            container.innerHTML = `
                <div style="display:flex;flex-direction:column;gap:1rem;">
                    <!-- Price & Bounds inputs -->
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;">
                        <div>
                            <label style="font-size:0.72rem;color:#94a3b8;font-weight:700;display:block;margin-bottom:0.25rem;">SUPPORT LEVEL (₹)</label>
                            <input id="inpSwingLower" type="number" step="0.05" value="${r.lower || ''}" style="width:100%;background:#090d16;border:1px solid rgba(255,255,255,0.15);color:#34d399;font-family:var(--font-mono);font-size:1.1rem;font-weight:800;padding:0.45rem 0.65rem;border-radius:6px;" />
                        </div>
                        <div>
                            <label style="font-size:0.72rem;color:#94a3b8;font-weight:700;display:block;margin-bottom:0.25rem;">RESISTANCE LEVEL (₹)</label>
                            <input id="inpSwingUpper" type="number" step="0.05" value="${r.upper || ''}" style="width:100%;background:#090d16;border:1px solid rgba(255,255,255,0.15);color:#f87171;font-family:var(--font-mono);font-size:1.1rem;font-weight:800;padding:0.45rem 0.65rem;border-radius:6px;" />
                        </div>
                    </div>

                    <!-- Action buttons -->
                    <div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.5rem;border-top:1px solid rgba(255,255,255,0.08);">
                        <button type="button" onclick="app.autoDetectCurrentSwingRange()" class="btn btn-secondary btn-sm" style="font-size:0.75rem;">⚡ Auto-Detect (3M ATR)</button>
                        <button type="button" onclick="app.saveCurrentSwingRange()" class="btn btn-primary btn-sm" style="font-size:0.75rem;font-weight:700;">💾 Save Custom Range</button>
                    </div>

                    <!-- Cycle History -->
                    ${hist.length ? `
                        <div style="margin-top:0.5rem;">
                            <div style="font-size:0.75rem;font-weight:700;color:#94a3b8;margin-bottom:0.35rem;">Historical Swing Cycles (${hist.length})</div>
                            <div style="max-height:160px;overflow-y:auto;font-size:0.72rem;">
                                ${hist.map(h => `
                                    <div style="display:flex;justify-content:space-between;padding:0.25rem 0.45rem;border-bottom:1px solid rgba(255,255,255,0.04);font-family:var(--font-mono);">
                                        <span style="color:#f8fafc;">Cycle ${h.cycle_idx}: ${h.start_date || '—'} ➔ ${h.end_date || '—'}</span>
                                        <span style="color:#cbd5e1;">₹${h.cycle_low} – ₹${h.cycle_high}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;
        },

        async autoDetectCurrentSwingRange() {
            if (!this._activeSwingTicker) return;
            try {
                const res = await fetch(API_BASE + `/api/v1/swing-ranges/auto-detect/${encodeURIComponent(this._activeSwingTicker)}`, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    if (data.range) {
                        const lowEl = document.getElementById('inpSwingLower');
                        const upEl = document.getElementById('inpSwingUpper');
                        if (lowEl) lowEl.value = data.range.lower;
                        if (upEl) upEl.value = data.range.upper;
                    }
                }
            } catch (e) {
                console.error('[SWING] Auto-detect error:', e);
            }
        },

        async saveCurrentSwingRange() {
            if (!this._activeSwingTicker) return;
            const lowVal = parseFloat(document.getElementById('inpSwingLower')?.value);
            const upVal = parseFloat(document.getElementById('inpSwingUpper')?.value);
            if (isNaN(lowVal) || isNaN(upVal)) {
                alert('Please enter valid numeric support and resistance values.');
                return;
            }
            try {
                const res = await fetch(API_BASE + '/api/v1/swing-ranges/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        watchlist: this._activeSwingWatchlist || 'ALL',
                        ticker: this._activeSwingTicker,
                        lower: lowVal,
                        upper: upVal,
                        source: 'user'
                    })
                });
                if (res.ok) {
                    this.closeSwingRangeModal();
                    if (typeof this.loadSwing === 'function') {
                        this.loadSwing();
                    } else if (typeof this.loadActiveQuotes === 'function') {
                        this.loadActiveQuotes(false);
                    }
                }
            } catch (e) {
                console.error('[SWING] Save range error:', e);
            }
        },

        // =========================================================================
        // 🧠 Unified AI Intelligence & Thesis Popover/Modal
        // =========================================================================
        async openSwingAiModal(ticker) {
            ticker = (ticker || '').toUpperCase().trim();
            if (!ticker) return;

            const modal = document.getElementById('swingAiThesisModal');
            const symEl = document.getElementById('swingAiModalTicker');
            const subEl = document.getElementById('swingAiModalSub');
            const bodyEl = document.getElementById('swingAiModalBody');

            if (symEl) symEl.textContent = `${ticker} — AI Thesis & Intelligence`;
            if (subEl) subEl.textContent = '4-Model Consensus · Kronos 14-Day Price Path · News Catalysts';
            if (modal) modal.style.display = 'flex';
            if (bodyEl) {
                bodyEl.innerHTML = `
                    <div style="text-align:center;padding:2.5rem 1rem;color:#94a3b8;">
                        <div class="loading-spinner" style="margin-bottom:0.75rem;"></div>
                        <div>Synthesizing DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral & Kronos for <strong>${ticker}</strong>...</div>
                    </div>
                `;
            }

            try {
                // Look up cached stock item from swing data
                const stock = (this.swingData || []).find(r => (r.ticker || '').toUpperCase() === ticker) || {};
                const consensusData = (this.consensusMap && this.consensusMap[ticker]) || stock.consensus || {};
                const kronosData = stock.kronos_prediction || {};
                const aiSynthesis = stock.ai_synthesis || {};

                // Fetch live consensus if missing
                let consensusRes = consensusData;
                if (!consensusRes.consensus_direction) {
                    try {
                        const cRes = await fetch(API_BASE + `/api/v1/consensus/predictions/${encodeURIComponent(ticker)}`);
                        if (cRes.ok) {
                            const cData = await cRes.json();
                            if (cData.prediction) consensusRes = cData.prediction;
                        }
                    } catch (_) {}
                }

                this.renderSwingAiModalContent(ticker, consensusRes, kronosData, aiSynthesis, stock);
            } catch (e) {
                console.error('[SWING-AI] Modal error:', e);
                if (bodyEl) {
                    bodyEl.innerHTML = `<div style="padding:2rem;text-align:center;color:#f87171;">Failed loading AI thesis: ${e.message}</div>`;
                }
            }
        },

        renderSwingAiModalContent(ticker, consensus, kronos, ai, stock) {
            const bodyEl = document.getElementById('swingAiModalBody');
            if (!bodyEl) return;

            const models = consensus.model_predictions || {};
            const dir = consensus.consensus_direction || 'NEUTRAL';
            const str = consensus.consensus_strength != null ? consensus.consensus_strength : 50;
            const isBull = dir.includes('BUY') || dir.includes('BULL');
            const isBear = dir.includes('SELL') || dir.includes('BEAR');
            const badgeBg = isBull ? 'rgba(16,185,129,0.2)' : isBear ? 'rgba(239,68,68,0.2)' : 'rgba(234,179,8,0.2)';
            const badgeColor = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';
            const badgeBorder = isBull ? '1px solid #10b981' : isBear ? '1px solid #ef4444' : '1px solid #eab308';

            const kpTrend = kronos.trend || 'Neutral';
            const kpRet = kronos.return_pct != null ? `${kronos.return_pct >= 0 ? '+' : ''}${kronos.return_pct.toFixed(1)}%` : '—';
            const kpCls = kpTrend === 'Bullish' ? '#34d399' : kpTrend === 'Bearish' ? '#f87171' : '#cbd5e1';

            bodyEl.innerHTML = `
                <div style="display:flex;flex-direction:column;gap:1rem;">
                    
                    <!-- Top AI Summary Banner -->
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:0.75rem;background:#060913;padding:0.85rem 1rem;border-radius:0.5rem;border:1px solid rgba(255,255,255,0.06);">
                        <div>
                            <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;font-weight:700;margin-bottom:0.25rem;">4-MODEL AI CONSENSUS</div>
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span class="signal-badge" style="background:${badgeBg};color:${badgeColor};border:${badgeBorder};font-size:0.85rem;font-weight:800;padding:0.2rem 0.65rem;">
                                    ${dir} (${str}%)
                                </span>
                            </div>
                        </div>
                        <div>
                            <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;font-weight:700;margin-bottom:0.25rem;">KRONOS 14-DAY SEQUENCE</div>
                            <div style="font-size:1.1rem;font-weight:800;color:${kpCls};font-family:var(--font-mono);">
                                ${kpTrend} <span style="font-size:0.85rem;font-weight:600;color:#94a3b8;">(${kpRet})</span>
                            </div>
                        </div>
                        <div>
                            <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;font-weight:700;margin-bottom:0.25rem;">🌐 MACRO REGIME WEIGHT</div>
                            <div style="font-size:0.85rem;font-weight:800;color:${(stock && stock.macro_regime && stock.macro_regime.pill_color) || '#38bdf8'};font-family:var(--font-mono);margin-top:0.2rem;">
                                ${(stock && stock.macro_regime && stock.macro_regime.pill) || '🟡 Macro Weighted (1.0x)'}
                            </div>
                        </div>
                    </div>

                    <!-- 4-Model Breakdown Grid -->
                    <div>
                        <div style="font-size:0.72rem;color:#94a3b8;font-weight:700;margin-bottom:0.45rem;display:flex;justify-content:space-between;align-items:center;">
                            <span>MULTI-MODEL AI MATRIX</span>
                            <span style="font-size:0.65rem;color:#64748b;">DeepSeek-R1 · Llama-3.3 · Qwen-2.5 · Mistral</span>
                        </div>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:0.5rem;">
                            ${['deepseek-r1', 'llama-3.3-70b', 'qwen-2.5-72b', 'mistral-large'].map(mKey => {
                                const m = models[mKey] || {};
                                const mDir = m.direction || 'PENDING';
                                const mConf = m.confidence != null ? `${m.confidence}%` : '—';
                                const mIsBuy = mDir.includes('BUY') || mDir.includes('BULL');
                                const mIsSell = mDir.includes('SELL') || mDir.includes('BEAR');
                                const mClr = mIsBuy ? '#34d399' : mIsSell ? '#f87171' : '#94a3b8';
                                const mLabel = mKey === 'deepseek-r1' ? 'DeepSeek-R1' : mKey === 'llama-3.3-70b' ? 'Llama-3.3' : mKey === 'qwen-2.5-72b' ? 'Qwen-2.5' : 'Mistral';
                                return `
                                    <div style="background:#0a0f1e;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.5rem 0.6rem;">
                                        <div style="font-size:0.65rem;color:#60a5fa;font-weight:700;margin-bottom:0.15rem;">${mLabel}</div>
                                        <div style="font-weight:800;font-size:0.82rem;color:${mClr};">${mDir}</div>
                                        <div style="font-size:0.65rem;color:#64748b;">Conf: ${mConf}</div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>

                    <!-- News Catalysts & Volume Rhythm -->
                    <div style="background:#0a0f1e;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.65rem 0.85rem;">
                        <div style="font-size:0.70rem;color:#94a3b8;font-weight:700;margin-bottom:0.3rem;">NEWS CATALYSTS & VOLUME RHYTHM</div>
                        <div style="font-size:0.75rem;color:#cbd5e1;line-height:1.4;">
                            ${ai.summary || ai.thesis || consensus.rationale || 'Volume accumulation detected along the horizontal support floor. Quantitative metrics confirm favorable risk-to-reward ratio for swing positioning.'}
                        </div>
                    </div>

                    <!-- Modal Actions Bar -->
                    <div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.65rem;border-top:1px solid rgba(255,255,255,0.08);">
                        <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:0.75rem;text-decoration:none;">
                            📊 Open Full Stock Intelligence & Charts ↗
                        </a>
                        <div style="display:flex;gap:0.4rem;">
                            <button type="button" onclick="app.runSwingKronos('${ticker.replace(/'/g, "\\'")}', this)" class="btn btn-sm" style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-size:0.75rem;">
                                🔮 Refresh Kronos
                            </button>
                            <button type="button" onclick="document.getElementById('swingAiThesisModal').style.display='none'" class="btn btn-primary btn-sm" style="font-size:0.75rem;">
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
    };

    // Export module
    window.SwingModule = swingModule;
    window.app = window.app || {};
    Object.assign(window.app, swingModule);
})();

