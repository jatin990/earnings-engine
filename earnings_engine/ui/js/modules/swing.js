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
                    if (typeof this.loadActiveQuotes === 'function') {
                        this.loadActiveQuotes(false);
                    }
                }
            } catch (e) {
                console.error('[SWING] Save range error:', e);
            }
        }
    };

    // Export module
    window.SwingModule = swingModule;
    if (window.app) {
        Object.assign(window.app, swingModule);
    }
})();
