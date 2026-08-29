// =========================================================================
// stock_rating — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    // ========================================================
    // 📊 Industry-Benchmarked Stock Rating & Diff Modal Methods
    // ========================================================
    app.activeRatingTicker = null;

    app.recalculateRow = async function(ticker, btnElement) {
        if (!ticker) return;
        const origHtml = btnElement ? btnElement.innerHTML : 'Recalc';
        if (btnElement) {
            btnElement.disabled = true;
            btnElement.textContent = 'Calculating...';
        }

        try {
            const res = await fetch(`/api/v1/stock/${encodeURIComponent(ticker)}/recalculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: 'row_click' })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Recalculation failed');
            }
            const data = await res.json();
            app.displayStockRatingModal(data);
        } catch (e) {
            alert(`Recalculation error for ${ticker}: ${e.message}`);
        } finally {
            if (btnElement) {
                btnElement.disabled = false;
                btnElement.innerHTML = origHtml;
            }
        }
    };

    app.openStockRatingModal = async function(ticker) {
        if (!ticker) return;
        app.activeRatingTicker = ticker;
        try {
            const res = await fetch(`/api/v1/stock/${encodeURIComponent(ticker)}/rating`);
            if (!res.ok) throw new Error('Failed to fetch rating');
            const data = await res.json();
            app.displayStockRatingModal(data);
        } catch (e) {
            alert(`Error opening stock rating for ${ticker}: ${e.message}`);
        }
    };

    app.displayStockRatingModal = function(data) {
        const modal = document.getElementById('stockRatingModal');
        if (!modal) return;
        app.activeRatingTicker = data.ticker;

        const tickerEl = document.getElementById('ratingModalTicker');
        if (tickerEl) tickerEl.textContent = data.ticker;

        const badgeEl = document.getElementById('ratingModalSectorBadge');
        if (badgeEl) badgeEl.textContent = data.sector || data.industry || 'General';

        const sectorNameEl = document.getElementById('ratingModalSectorName');
        if (sectorNameEl) sectorNameEl.textContent = data.sector || 'Industry Benchmark';

        // Fundamental Grade
        const fGrade = data.fundamental ? data.fundamental.grade : 'NEUTRAL';
        const fScore = data.fundamental ? data.fundamental.score : 50;
        const fGradeEl = document.getElementById('ratingModalFundGrade');
        if (fGradeEl) {
            fGradeEl.textContent = fGrade;
            fGradeEl.style.color = fGrade === 'GOOD' ? '#34d399' : (fGrade === 'POOR' ? '#f87171' : '#fbbf24');
        }
        const fScoreEl = document.getElementById('ratingModalFundScore');
        if (fScoreEl) fScoreEl.textContent = `(${fScore}/100)`;

        // Technical Grade
        const tGrade = data.technical ? data.technical.grade : 'NEUTRAL';
        const tScore = data.technical ? data.technical.score : 50;
        const tGradeEl = document.getElementById('ratingModalTechGrade');
        if (tGradeEl) {
            tGradeEl.textContent = tGrade;
            tGradeEl.style.color = (tGrade === 'STRONG BUY' || tGrade === 'BUY') ? '#38bdf8' : (tGrade === 'AVOID' ? '#f87171' : '#fbbf24');
        }
        const tScoreEl = document.getElementById('ratingModalTechScore');
        if (tScoreEl) tScoreEl.textContent = `(${tScore}/100)`;

        // Composite
        const cGrade = data.composite ? data.composite.grade : 'FAIR';
        const cScore = data.composite ? data.composite.score : 50;
        const cGradeEl = document.getElementById('ratingModalCompGrade');
        if (cGradeEl) cGradeEl.textContent = cGrade;
        const cScoreEl = document.getElementById('ratingModalCompScore');
        if (cScoreEl) cScoreEl.textContent = `(${cScore})`;

        const updatedEl = document.getElementById('ratingModalUpdated');
        if (updatedEl) updatedEl.textContent = data.timestamp ? `Updated: ${data.timestamp}` : '';

        // Diff Banner
        const diff = data.diff;
        const diffBadge = document.getElementById('ratingModalDiffBadge');
        const fundDiffEl = document.getElementById('ratingModalFundDiff');
        const techDiffEl = document.getElementById('ratingModalTechDiff');

        if (diff && diff.has_previous) {
            if (diffBadge) diffBadge.style.display = 'inline-flex';
            const fDelta = diff.fundamental_score_diff;
            if (fundDiffEl) fundDiffEl.innerHTML = `Diff: <span style="color:${fDelta >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${fDelta >= 0 ? '+' : ''}${fDelta}</span> (was ${diff.prev_fundamental_grade})`;
            const tDelta = diff.technical_score_diff;
            if (techDiffEl) techDiffEl.innerHTML = `Diff: <span style="color:${tDelta >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${tDelta >= 0 ? '+' : ''}${tDelta}</span> (was ${diff.prev_technical_grade})`;
        } else {
            if (diffBadge) diffBadge.style.display = 'none';
            if (fundDiffEl) fundDiffEl.textContent = 'Baseline Snapshot Initialized';
            if (techDiffEl) techDiffEl.textContent = 'Live Price & Volume Evaluated';
        }

        // AI Note
        const aiNoteEl = document.getElementById('ratingModalAiNote');
        if (aiNoteEl) aiNoteEl.textContent = data.ai_note || 'Comprehensive analysis calculated across valuation multiples and technical indicators.';

        // Table Body
        const tbody = document.getElementById('ratingModalTableBody');
        if (tbody) {
            tbody.innerHTML = '';

            const m = data.fundamental ? data.fundamental.metrics : {};
            const rows = [
                {
                    name: 'P/E (Price-to-Earnings)',
                    val: (m.pe != null && !isNaN(m.pe)) ? `${Number(m.pe).toFixed(1)}x` : '—',
                    bm: (m.benchmark_pe != null) ? `${Number(m.benchmark_pe).toFixed(1)}x` : '—',
                    diff: (m.pe != null && m.pe_discount_pct !== undefined) ? `${m.pe_discount_pct > 0 ? '+' : ''}${m.pe_discount_pct}% discount` : '—',
                    status: (m.pe == null) ? 'Pending Data' : ((m.pe_discount_pct && m.pe_discount_pct > 0) ? 'Undervalued' : 'Premium'),
                    isPending: m.pe == null
                },
                {
                    name: 'P/B (Price-to-Book)',
                    val: (m.pb != null && !isNaN(m.pb)) ? `${Number(m.pb).toFixed(1)}x` : '—',
                    bm: (m.benchmark_pb != null) ? `${Number(m.benchmark_pb).toFixed(1)}x` : '—',
                    diff: (m.pb != null && m.benchmark_pb) ? `${((m.benchmark_pb - m.pb)/m.benchmark_pb*100).toFixed(1)}%` : '—',
                    status: (m.pb == null) ? 'Pending Data' : ((m.benchmark_pb && m.pb < m.benchmark_pb) ? 'Favorable' : 'Elevated'),
                    isPending: m.pb == null
                },
                {
                    name: 'ROE (Return on Equity)',
                    val: (m.roe != null && !isNaN(m.roe)) ? `${Number(m.roe).toFixed(1)}%` : '—',
                    bm: (m.benchmark_roe != null) ? `${Number(m.benchmark_roe).toFixed(1)}%` : '—',
                    diff: (m.roe != null && m.roe_spread !== undefined) ? `${m.roe_spread > 0 ? '+' : ''}${m.roe_spread}% spread` : '—',
                    status: (m.roe == null) ? 'Pending Data' : ((m.roe_spread && m.roe_spread >= 0) ? 'Outperforming' : 'Lagging'),
                    isPending: m.roe == null
                },
                {
                    name: 'Debt to Equity',
                    val: (m.debt_to_equity != null && !isNaN(m.debt_to_equity)) ? `${Number(m.debt_to_equity).toFixed(2)}x` : '—',
                    bm: (m.benchmark_debt_to_equity != null) ? `${Number(m.benchmark_debt_to_equity).toFixed(2)}x` : '—',
                    diff: (m.debt_to_equity != null) ? (m.debt_to_equity < 0.3 ? 'Pristine' : (m.debt_to_equity < 0.8 ? 'Moderate' : 'Elevated')) : '—',
                    status: (m.debt_to_equity == null) ? 'Pending Data' : (m.debt_to_equity < 0.5 ? 'Low Risk' : 'Leveraged'),
                    isPending: m.debt_to_equity == null
                },
                {
                    name: 'Operating Margin',
                    val: (m.operating_margin != null && !isNaN(m.operating_margin)) ? `${Number(m.operating_margin).toFixed(1)}%` : '—',
                    bm: (m.benchmark_operating_margin != null) ? `${Number(m.benchmark_operating_margin).toFixed(1)}%` : '—',
                    diff: (m.operating_margin != null && m.benchmark_operating_margin) ? `${(m.operating_margin - m.benchmark_operating_margin).toFixed(1)}% spread` : '—',
                    status: (m.operating_margin == null) ? 'Pending Data' : ((m.benchmark_operating_margin && m.operating_margin >= m.benchmark_operating_margin) ? 'Healthy' : 'Sub-par'),
                    isPending: m.operating_margin == null
                }
            ];

            rows.forEach(r => {
                const tr = document.createElement('tr');
                const isGood = r.status === 'Undervalued' || r.status === 'Favorable' || r.status === 'Outperforming' || r.status === 'Low Risk' || r.status === 'Healthy';
                const isPending = r.isPending;
                
                let badgeBg = 'rgba(239,68,68,0.12)';
                let badgeColor = '#f87171';
                let diffColor = '#f87171';

                if (isPending) {
                    badgeBg = 'rgba(148,163,184,0.12)';
                    badgeColor = '#94a3b8';
                    diffColor = '#64748b';
                } else if (isGood) {
                    badgeBg = 'rgba(16,185,129,0.12)';
                    badgeColor = '#34d399';
                    diffColor = '#34d399';
                }

                tr.innerHTML = `
                    <td style="font-weight:600;color:#ededed;">${r.name}</td>
                    <td class="mono" style="color:#ffffff;font-weight:700;">${r.val}</td>
                    <td class="mono" style="color:#a1a1aa;">${r.bm}</td>
                    <td class="mono" style="color:${diffColor};">${r.diff}</td>
                    <td><span class="signal-badge" style="background:${badgeBg};color:${badgeColor};font-size:0.68rem;">${r.status}</span></td>
                `;
                tbody.appendChild(tr);
            });
        }

        modal.style.display = 'block';
    };

    app.closeStockRatingModal = function() {
        const modal = document.getElementById('stockRatingModal');
        if (modal) modal.style.display = 'none';
    };

    app.triggerModalRecalculate = async function() {
        if (!app.activeRatingTicker) return;
        const btn = document.getElementById('ratingModalRecalcBtn');
        const statusEl = document.getElementById('ratingModalStatusText');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Calculating...';
        }
        if (statusEl) statusEl.textContent = 'Fetching fresh price bars & sector multiples...';

        try {
            const res = await fetch(`/api/v1/stock/${encodeURIComponent(app.activeRatingTicker)}/recalculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: 'modal_recalculate' })
            });
            if (!res.ok) throw new Error('Recalculation failed');
            const data = await res.json();
            app.displayStockRatingModal(data);
            if (statusEl) statusEl.textContent = 'Snapshot updated & audit record created.';
        } catch (e) {
            if (statusEl) statusEl.textContent = `Error: ${e.message}`;
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Recalculate Live';
            }
        }
    };

    app.showTickerAuditModal = async function(ticker) {
        if (!ticker) return;
        const modal = document.getElementById('tickerAuditModal');
        if (!modal) return;
        document.getElementById('auditModalTitle').textContent = `Audit Trail: ${ticker}`;
        const container = document.getElementById('auditModalContent');
        container.innerHTML = '<p class="timestamp">Loading immutable audit trail...</p>';
        modal.style.display = 'block';

        try {
            const res = await fetch(`/api/v1/recalculate/audit/${encodeURIComponent(ticker)}`);
            if (!res.ok) throw new Error('Failed to load audit history');
            const data = await res.json();
            const entries = data.entries || data.history || [];
            if (!entries.length) {
                container.innerHTML = `<div class="card" style="padding:1.5rem;text-align:center;color:#a1a1aa;background:#030305;">No prior recalculation audit events found for ${ticker}. Baseline initialized.</div>`;
                return;
            }

            let html = '<div style="display:flex;flex-direction:column;gap:0.6rem;">';
            entries.forEach(item => {
                const changes = item.field_changes ? JSON.stringify(item.field_changes, null, 2) : (item.notes || 'Recalculation snapshot created');
                html += `
                    <div style="background:#0a0a0f;border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:0.75rem;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
                            <span style="font-weight:600;font-size:0.78rem;color:#ededed;">Source: ${item.source || 'Manual'}</span>
                            <span class="timestamp" style="font-size:0.72rem;color:#a1a1aa;">${item.timestamp || item.created_at || ''}</span>
                        </div>
                        <pre style="margin:0;font-size:0.72rem;color:#94a3b8;font-family:var(--font-mono);white-space:pre-wrap;background:#000000;padding:0.4rem;border-radius:4px;border:1px solid rgba(255,255,255,0.05);">${changes}</pre>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<div style="color:#f87171;padding:1rem;">Error retrieving audit history: ${e.message}</div>`;
        }
    };

    app.closeTickerAuditModal = function() {
        const modal = document.getElementById('tickerAuditModal');
        if (modal) modal.style.display = 'none';
    };

    app.calcLiveWeekHL = async function(ticker, earningsDate, btnElement) {
        if (!ticker) return;
        const container = btnElement ? btnElement.closest('.pred-cell') || btnElement.parentElement : null;
        if (btnElement) {
            btnElement.disabled = true;
            btnElement.textContent = 'Calculating...';
        }

        try {
            const url = `/api/v1/stock/${encodeURIComponent(ticker)}/live-week-hl${earningsDate ? `?earnings_date=${encodeURIComponent(earningsDate)}` : ''}`;
            let res = await fetch(url, { method: 'POST' });
            
            // If 404 because server was started before route was registered, try recalculate route
            if (res.status === 404) {
                res = await fetch(`/api/v1/stock/${encodeURIComponent(ticker)}/recalculate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source: 'live_week_hl_fallback' })
                });
            }

            if (!res.ok) {
                throw new Error('Server needs a quick restart to register the live route (press Ctrl+C and re-run earnings-engine dashboard).');
            }
            const data = await res.json();
            
            let highPct = data.high_pct !== undefined ? data.high_pct : (data.technical && data.technical.metrics ? data.technical.metrics.vwap_diff_pct : 0);
            let lowPct = data.low_pct !== undefined ? data.low_pct : 0;
            let highP = data.high_price || (data.technical && data.technical.metrics ? data.technical.metrics.price : 0);
            let lowP = data.low_price || highP;
            let currP = data.current_price || highP;

            const highSign = highPct >= 0 ? '+' : '';
            const lowSign = lowPct >= 0 ? '+' : '';
            const highColor = highPct >= 0 ? '#34d399' : '#f87171';
            const lowColor = lowPct >= 0 ? '#34d399' : '#f87171';
            
            const hp = highP ? Number(highP).toLocaleString() : '—';
            const lp = lowP ? Number(lowP).toLocaleString() : '—';
            const datesStr = (data.high_date || data.low_date) ? `<br><span style="color:#a1a1aa;font-size:0.68rem;">${data.high_date || '—'} / ${data.low_date || '—'}</span>` : '';
            const livePriceStr = currP ? `<br><span style="color:#60a5fa;font-size:0.68rem;font-weight:600;">Live: ₹${currP}</span>` : '';
            
            if (container) {
                container.innerHTML = `
                    <div style="line-height:1.2;font-family:var(--font-mono);font-size:0.75rem;">
                        <span style="color:${highColor};font-weight:700;">${highSign}${highPct}%</span>/<span style="color:${lowColor};font-weight:700;">${lowSign}${lowPct}%</span>
                        <br><span style="color:var(--text-muted);font-size:0.68rem;">(${hp}/${lp})</span>
                        ${datesStr}
                        ${livePriceStr}
                    </div>
                `;
            }
        } catch (e) {
            alert(`Live H/L: ${e.message}`);
            if (btnElement) {
                btnElement.disabled = false;
                btnElement.textContent = 'Live H/L';
            }
        }
    };

})(); // end stock_rating IIFE
