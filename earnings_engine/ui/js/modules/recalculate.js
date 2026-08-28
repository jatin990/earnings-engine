// =========================================================================
// recalculate — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[recalculate] window.app not initialized'); return; }
    Object.assign(app, {
// =========================================================================
            // 🔄 Ticker On-Demand Recalculate & Audit Trail
            // =========================================================================
            async recalculateRow(ticker, btn) {
                if (!ticker) return;
                const originalHtml = btn ? btn.innerHTML : '🔄 Recalc';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Recalc...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/ticker/recalculate?ticker=' + encodeURIComponent(ticker), {
                        method: 'POST',
                    });
                    const data = await res.json();
                    if (!res.ok || !data.success) {
                        alert('Recalculation error: ' + (data.detail || data.error || 'Failed'));
                        return;
                    }

                    // Update DOM row cells if present
                    const rowId = 'row_' + ticker.replace(/[^a-zA-Z0-9]/g, '_');
                    const rowEl = document.getElementById(rowId);
                    if (rowEl && data.updated_metrics) {
                        const m = data.updated_metrics;
                        const pCell = rowEl.querySelector('.cell-current-price');
                        if (pCell && m.current_price !== null && m.current_price !== undefined) {
                            pCell.textContent = Number(m.current_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                        }
                        const edCell = rowEl.querySelector('.cell-earnings-date');
                        if (edCell && m.earnings_date) {
                            edCell.textContent = m.earnings_date;
                        }
                        const retCell = rowEl.querySelector('.cell-thirty-day-return');
                        if (retCell && m.thirty_day_return_pct !== null && m.thirty_day_return_pct !== undefined) {
                            const val = Number(m.thirty_day_return_pct);
                            retCell.textContent = (val > 0 ? '+' : '') + val.toFixed(2) + '%';
                        }
                        const resCell = rowEl.querySelector('.cell-next-resistance');
                        if (resCell && m.next_resistance !== null && m.next_resistance !== undefined) {
                            resCell.textContent = Number(m.next_resistance).toFixed(2);
                        }
                        const supCell = rowEl.querySelector('.cell-current-support');
                        if (supCell && m.current_support !== null && m.current_support !== undefined) {
                            supCell.textContent = Number(m.current_support).toFixed(2);
                        }

                        // Update Recounted Quality Scores with AI Tooltips
                        const qualCell = rowEl.querySelector('.cell-quality-scores');
                        if (qualCell) {
                            const q1 = (m.q1_earnings_score !== null && m.q1_earnings_score !== undefined) ? `${m.q1_earnings_score}/9` : '—';
                            const q2 = (m.q2_earnings_score !== null && m.q2_earnings_score !== undefined) ? `${m.q2_earnings_score}/9` : '—';
                            const q3 = (m.q3_earnings_score !== null && m.q3_earnings_score !== undefined) ? `${m.q3_earnings_score}/9` : '—';
                            const q1t = (m.q1_ai_summary || `Q1 Quality: ${q1}`).replace(/"/g, '&quot;');
                            const q2t = (m.q2_ai_summary || `Q2 Quality: ${q2}`).replace(/"/g, '&quot;');
                            const q3t = (m.q3_ai_summary || `Q3 Quality: ${q3}`).replace(/"/g, '&quot;');
                            qualCell.innerHTML = `
                                <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q1t}">${q1}</span> | 
                                <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q2t}">${q2}</span> | 
                                <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q3t}">${q3}</span>
                            `;
                        }

                        const avgCell = rowEl.querySelector('.cell-prev-3q-score');
                        if (avgCell && m.prev_3q_earnings_score !== null && m.prev_3q_earnings_score !== undefined) {
                            avgCell.textContent = `${m.prev_3q_earnings_score}/9`;
                        }

                        ['q1', 'q2', 'q3'].forEach(q => {
                            const cell = rowEl.querySelector(`.cell-${q}-week-hl`);
                            if (cell && m[`${q}_ai_summary`]) {
                                const wrap = cell.querySelector('.q-week-hl-wrap') || cell;
                                wrap.setAttribute('title', m[`${q}_ai_summary`]);
                            }
                        });
                    }

                    // Render Custom Recalculation Alert / Modal
                    this.showRecalculateResultModal(data);

                } catch (err) {
                    console.error('Error recalculating row for ' + ticker, err);
                    alert('Network error while recalculating ' + ticker + ': ' + err.message);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalHtml;
                    }
                }
            },

            showRecalculateResultModal(data) {
                const existing = document.getElementById('recalculateResultModal');
                if (existing) existing.remove();

                const isUpdated = Boolean(data.has_changes);
                const titleBg = isUpdated ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                const titleBorder = isUpdated ? '#10b981' : '#3b82f6';
                const statusBadge = isUpdated 
                    ? '<span style="background:#10b981;color:#fff;padding:0.2rem 0.5rem;border-radius:9999px;font-size:0.75rem;font-weight:700;">🟢 METRICS UPDATED</span>' 
                    : '<span style="background:rgba(255,255,255,0.15);color:var(--light);padding:0.2rem 0.5rem;border-radius:9999px;font-size:0.75rem;font-weight:700;">⚪ NO CHANGES</span>';

                let changesHtml = '';
                if (data.changes_summary && data.changes_summary.length) {
                    changesHtml = '<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;padding:0.75rem;margin:0.75rem 0;font-size:0.85rem;line-height:1.6;">' +
                        '<div style="font-weight:700;color:var(--light);margin-bottom:0.4rem;">Summary of Diff:</div>' +
                        data.changes_summary.map(c => '<div style="display:flex;align-items:center;gap:0.4rem;"><span style="color:' + (isUpdated ? '#34d399' : 'var(--muted)') + ';">•</span> <span>' + c + '</span></div>').join('') +
                        '</div>';
                }

                const modalHtml = `
                <div id="recalculateResultModal" style="position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:99999;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);">
                    <div style="background:#0f172a;border:1px solid ${titleBorder};border-radius:0.75rem;max-width:520px;width:100%;box-shadow:0 20px 40px rgba(0,0,0,0.6);overflow:hidden;color:var(--light);animation:fadeIn 0.2s ease-out;">
                        <div style="padding:1rem 1.25rem;background:${titleBg};border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;">
                            <div style="display:flex;align-items:center;gap:0.6rem;">
                                <span style="font-size:1.3rem;">${isUpdated ? '⚡' : '🔍'}</span>
                                <h3 style="margin:0;font-size:1.05rem;font-weight:700;">${data.ticker} Recalculation</h3>
                            </div>
                            <div>${statusBadge}</div>
                        </div>
                        <div style="padding:1.25rem;">
                            <p style="margin:0 0 0.5rem 0;font-size:0.88rem;color:var(--muted);">
                                ${isUpdated ? 'Live market data and earnings calendars were refreshed. The following metrics changed:' : 'Live check completed. All earnings dates, price highs/lows, and quality scores are currently matching the latest market state.'}
                            </p>
                            ${changesHtml}
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:1rem;font-size:0.75rem;color:var(--muted);">
                                <span>Refreshed at: ${data.refreshed_at || new Date().toLocaleTimeString()}</span>
                                <span style="cursor:pointer;color:#93c5fd;text-decoration:underline;" onclick="app.showTickerAuditModal('${data.ticker}')">View Audit Trail 📜</span>
                            </div>
                        </div>
                        <div style="padding:0.75rem 1.25rem;background:rgba(0,0,0,0.2);border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:flex-end;">
                            <button type="button" class="btn btn-sm btn-primary" onclick="document.getElementById('recalculateResultModal').remove()">Done</button>
                        </div>
                    </div>
                </div>`;

                const wrap = document.createElement('div');
                wrap.innerHTML = modalHtml;
                document.body.appendChild(wrap.firstElementChild);
            },

            async showTickerAuditModal(ticker) {
                const existing = document.getElementById('tickerAuditModal');
                if (existing) existing.remove();

                const sym = (ticker || '').trim().toUpperCase();
                const title = sym ? `${sym} Audit History` : 'Global Recalculation Audit Trail';

                const modalEl = document.createElement('div');
                modalEl.id = 'tickerAuditModal';
                modalEl.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:99999;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);';
                modalEl.innerHTML = `
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.15);border-radius:0.75rem;max-width:750px;width:100%;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 25px 50px rgba(0,0,0,0.8);overflow:hidden;color:var(--light);">
                        <div style="padding:1rem 1.25rem;background:rgba(255,255,255,0.04);border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;">
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span style="font-size:1.2rem;">📜</span>
                                <h3 style="margin:0;font-size:1.05rem;font-weight:700;">${title}</h3>
                            </div>
                            <button type="button" class="btn btn-sm" onclick="document.getElementById('tickerAuditModal').remove()" style="background:rgba(255,255,255,0.1);color:var(--light);border:none;border-radius:0.3rem;cursor:pointer;">✕</button>
                        </div>
                        <div id="auditModalBody" style="padding:1.25rem;overflow-y:auto;flex:1;">
                            <div style="text-align:center;padding:2rem;color:var(--muted);"><span class="loading-spinner"></span> Loading audit logs...</div>
                        </div>
                        <div style="padding:0.75rem 1.25rem;background:rgba(0,0,0,0.3);border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;color:var(--muted);">
                            <span>Audit records are permanently preserved in the local/cloud database.</span>
                            <button type="button" class="btn btn-sm btn-primary" onclick="document.getElementById('tickerAuditModal').remove()">Close</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modalEl);

                try {
                    const url = API_BASE + '/api/v1/ticker/audit-log' + (sym ? '?ticker=' + encodeURIComponent(sym) : '') + '&limit=50';
                    const res = await fetch(url);
                    const list = await res.json();

                    const bodyEl = document.getElementById('auditModalBody');
                    if (!bodyEl) return;

                    if (!Array.isArray(list) || !list.length) {
                        bodyEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);">No audit entries found for this ticker yet. Click <strong>🔄 Recalc</strong> on a results row to trigger a live refresh.</div>';
                        return;
                    }

                    let tableHtml = `
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;font-size:0.82rem;text-align:left;">
                            <thead>
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.15);color:var(--muted);">
                                    <th style="padding:0.5rem 0.6rem;">Timestamp</th>
                                    <th style="padding:0.5rem 0.6rem;">Ticker</th>
                                    <th style="padding:0.5rem 0.6rem;">Status</th>
                                    <th style="padding:0.5rem 0.6rem;">Changes / Diff</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;

                    list.forEach(entry => {
                        const statusBadge = entry.has_changes
                            ? '<span style="background:rgba(16,185,129,0.2);color:#34d399;padding:0.15rem 0.45rem;border-radius:9999px;font-size:0.72rem;font-weight:700;">🟢 UPDATED</span>'
                            : '<span style="background:rgba(255,255,255,0.08);color:var(--muted);padding:0.15rem 0.45rem;border-radius:9999px;font-size:0.72rem;">⚪ NO CHANGE</span>';
                        
                        const summaryLines = (entry.changes_summary || '').split('\n').filter(Boolean);
                        const summaryDisplay = summaryLines.map(s => `<div style="font-size:0.78rem;margin:0.15rem 0;">• ${s}</div>`).join('') || '—';

                        tableHtml += `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                                <td style="padding:0.6rem;white-space:nowrap;color:var(--muted);">${entry.refreshed_at || '—'}</td>
                                <td style="padding:0.6rem;font-weight:700;color:var(--light);">${entry.ticker}</td>
                                <td style="padding:0.6rem;">${statusBadge}</td>
                                <td style="padding:0.6rem;color:var(--light);">${summaryDisplay}</td>
                            </tr>
                        `;
                    });

                    tableHtml += `</tbody></table></div>`;
                    bodyEl.innerHTML = tableHtml;

                } catch (e) {
                    console.error('Error fetching audit history:', e);
                    const bodyEl = document.getElementById('auditModalBody');
                    if (bodyEl) bodyEl.innerHTML = '<div style="color:#f87171;padding:1rem;">Failed to load audit history: ' + e.message + '</div>';
                }
            
    
        }
});
})(); // end recalculate IIFE
