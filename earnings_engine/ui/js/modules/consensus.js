// =========================================================================
// 🧠 Multi-Model AI Consensus Engine Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const consensusModule = {
        _consensusRunning: false,
        _selectedTimeframe: 14,
        _consensusCache: {},

        setTimeframe(days) {
            this._selectedTimeframe = parseInt(days, 10) || 14;
            document.querySelectorAll('.tf-pill-btn').forEach(btn => {
                const bDays = parseInt(btn.getAttribute('data-tf') || '14', 10);
                if (bDays === this._selectedTimeframe) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        },

        async runConsensusForStock(ticker) {
            if (!ticker) return;
            const sym = ticker.trim().toUpperCase();
            this.openConsensusModal(sym);
            this.executeConsensusEngine(sym, this._selectedTimeframe);
        },

        openConsensusModal(ticker) {
            const modal = document.getElementById('consensusModal');
            const symEl = document.getElementById('consensusModalTicker');
            if (symEl) symEl.textContent = ticker;
            if (modal) {
                modal.style.display = 'flex';
            }
        },

        closeConsensusModal() {
            const modal = document.getElementById('consensusModal');
            if (modal) modal.style.display = 'none';
        },

        async executeConsensusEngine(ticker, timeframe = 14) {
            const container = document.getElementById('consensusResultsContainer');
            if (!container) return;

            container.innerHTML = `
                <div style="text-align:center;padding:3rem 1rem;color:#94a3b8;">
                    <div class="spinner" style="width:24px;height:24px;margin:0 auto 1rem auto;"></div>
                    <div style="font-weight:700;color:#f8fafc;font-size:0.95rem;margin-bottom:0.35rem;">Synthesizing Multi-Model AI Consensus for ${ticker}...</div>
                    <div style="font-size:0.75rem;color:#64748b;">Evaluating DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, and Mistral-Large across 6 standardized pillars.</div>
                </div>
            `;

            try {
                const res = await fetch(API_BASE + `/api/v1/consensus/run/${encodeURIComponent(ticker)}?timeframe_days=${timeframe}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    const data = await res.json();
                    this.renderConsensusResult(data, container);
                } else {
                    const err = await res.json();
                    container.innerHTML = `<div style="color:#f87171;padding:2rem;text-align:center;">Consensus execution error: ${err.detail || 'Inference failed'}</div>`;
                }
            } catch (e) {
                console.error('[CONSENSUS] Execution failed:', e);
                container.innerHTML = `<div style="color:#f87171;padding:2rem;text-align:center;">Network error running consensus.</div>`;
            }
        },

        renderConsensusResult(data, container) {
            if (!data || !container) return;
            const pred = data.prediction || data;
            const dir = (pred.consensus_direction || 'NEUTRAL').toUpperCase();
            const isBull = dir.includes('BULL');
            const isBear = dir.includes('BEAR');
            const badgeBg = isBull ? 'rgba(16,185,129,0.15)' : (isBear ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)');
            const badgeCol = isBull ? '#34d399' : (isBear ? '#f87171' : '#fbbf24');
            const badgeBorder = isBull ? 'rgba(16,185,129,0.35)' : (isBear ? 'rgba(239,68,68,0.35)' : 'rgba(245,158,11,0.35)');

            const models = pred.models || {};

            container.innerHTML = `
                <div style="display:flex;flex-direction:column;gap:1.1rem;">
                    <!-- Verdict Header Card -->
                    <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:1.1rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;">
                        <div>
                            <div style="font-size:0.7rem;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:0.04em;">Unified Consensus Verdict</div>
                            <div style="display:flex;align-items:center;gap:0.55rem;margin-top:0.25rem;">
                                <span class="signal-badge" style="background:${badgeBg};color:${badgeCol};border:1px solid ${badgeBorder};font-size:1.05rem;font-weight:800;padding:0.25rem 0.75rem;">${dir}</span>
                                <span style="font-family:var(--font-mono);font-size:0.9rem;color:#f8fafc;font-weight:700;">Target: ₹${pred.consensus_target || '—'} | SL: ₹${pred.consensus_stop_loss || '—'}</span>
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:0.7rem;color:#94a3b8;">Consensus Strength</div>
                            <div style="font-family:var(--font-mono);font-size:1.35rem;font-weight:800;color:${badgeCol};">${pred.consensus_strength || 80}%</div>
                        </div>
                    </div>

                    <!-- Strategic Thesis -->
                    ${pred.consensus_thesis ? `
                        <div style="background:#090d16;border:1px solid rgba(59,130,246,0.3);border-radius:8px;padding:0.9rem 1.1rem;font-size:0.82rem;color:#e2e8f0;line-height:1.55;">
                            <strong style="color:#60a5fa;">AI Strategic Thesis:</strong> ${pred.consensus_thesis}
                        </div>
                    ` : ''}

                    <!-- 4-Model Breakdown Grid -->
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0.75rem;">
                        ${Object.entries(models).map(([mName, mData]) => {
                            const mDir = (mData.direction || 'NEUTRAL').toUpperCase();
                            const mBull = mDir.includes('BULL');
                            const mBear = mDir.includes('BEAR');
                            const mCol = mBull ? '#34d399' : (mBear ? '#f87171' : '#fbbf24');
                            return `
                                <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.75rem 0.85rem;display:flex;flex-direction:column;gap:0.35rem;">
                                    <div style="font-weight:700;font-size:0.75rem;color:#f8fafc;">${mName}</div>
                                    <div style="display:flex;justify-content:space-between;align-items:center;">
                                        <span style="color:${mCol};font-weight:800;font-size:0.8rem;font-family:var(--font-mono);">${mDir}</span>
                                        <span style="font-size:0.7rem;color:#94a3b8;font-family:var(--font-mono);">₹${mData.target_price || '—'}</span>
                                    </div>
                                    ${mData.rationale ? `<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.2rem;line-height:1.35;">${mData.rationale.substring(0, 90)}...</div>` : ''}
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        }
    };

    // Export module
    window.ConsensusModule = consensusModule;
    if (window.app) {
        Object.assign(window.app, consensusModule);
    }
})();
