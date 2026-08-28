// =========================================================================
// breakout_audit — Nexus Dashboard Module (Breakout Movement & Tier Transition Logs)
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[breakout_audit] window.app not initialized'); return; }

    Object.assign(app, {
            // =========================================================================
            // 🔄 Breakout Movement & Tier Transition Audit Log
            // =========================================================================
            _breakoutAuditOpen: false,

            toggleBreakoutAuditLog() {
                const container = document.getElementById('breakoutAuditContainer');
                const toggleIcon = document.getElementById('breakoutAuditToggleIcon');
                if (!container) return;

                this._breakoutAuditOpen = !this._breakoutAuditOpen;
                container.style.display = this._breakoutAuditOpen ? 'block' : 'none';
                if (toggleIcon) toggleIcon.textContent = this._breakoutAuditOpen ? '▲ Hide Log' : '▼ Show Log';

                if (this._breakoutAuditOpen) {
                    this.loadBreakoutAuditLog();
                }
            },

            async loadBreakoutAuditLog(ticker = null) {
                const listEl = document.getElementById('breakoutAuditList');
                const countBadge = document.getElementById('breakoutAuditBadgeCount');
                if (!listEl) return;

                try {
                    const url = API_BASE + '/api/v1/breakout-radar/audit-log' + (ticker ? `?ticker=${encodeURIComponent(ticker)}` : '?limit=40');
                    const res = await fetch(url);
                    if (res.ok) {
                        const data = await res.json();
                        const logs = data.logs || [];
                        if (countBadge) countBadge.textContent = `(${logs.length} events)`;

                        if (!logs.length) {
                            listEl.innerHTML = '<div style="text-align:center;color:#64748b;font-size:0.72rem;padding:0.75rem;">No recent tier movement events recorded yet. Transitions will appear automatically during scan cycles.</div>';
                            return;
                        }

                        listEl.innerHTML = logs.map(l => {
                            const isPromoted = l.event_type === 'PROMOTED_HOT' || l.to_tier === 'HOT';
                            const isAdded = l.event_type === 'ADDED_WARM';
                            const isDemoted = l.event_type === 'DEMOTED_WARM' || l.to_tier === 'WARM';
                            const isRemoved = l.event_type === 'REMOVED_COLD' || l.to_tier === 'COLD';
                            const isOverride = l.event_type === 'MANUAL_OVERRIDE';

                            const bg = isPromoted ? 'rgba(16,185,129,0.12)' : isAdded ? 'rgba(56,189,248,0.12)' : isDemoted ? 'rgba(245,158,11,0.12)' : isRemoved ? 'rgba(239,68,68,0.12)' : 'rgba(148,163,184,0.1)';
                            const border = isPromoted ? 'rgba(16,185,129,0.3)' : isAdded ? 'rgba(56,189,248,0.3)' : isDemoted ? 'rgba(245,158,11,0.3)' : isRemoved ? 'rgba(239,68,68,0.3)' : 'rgba(148,163,184,0.2)';
                            const color = isPromoted ? '#34d399' : isAdded ? '#38bdf8' : isDemoted ? '#fbbf24' : isRemoved ? '#f87171' : '#cbd5e1';
                            const icon = isPromoted ? '🔥 PROMOTED' : isAdded ? '⚡ ADDED' : isDemoted ? '📉 DEMOTED' : isRemoved ? '❌ REMOVED' : '⚙️ OVERRIDE';

                            const timeStr = l.created_at ? l.created_at.replace('T', ' ').substring(0, 16) : '';
                            const priceStr = l.price ? `₹${l.price.toFixed(2)}` : '';
                            const scoreStr = l.score_after !== null && l.score_after !== undefined ? `Score: ${l.score_after}` : '';

                            return `
                                <div style="background:${bg};border:1px solid ${border};border-radius:6px;padding:0.45rem 0.65rem;display:flex;flex-direction:column;gap:0.2rem;">
                                    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.3rem;">
                                        <div style="display:flex;align-items:center;gap:0.45rem;">
                                            <span style="font-size:0.65rem;font-weight:800;color:${color};background:#000000;padding:0.1rem 0.35rem;border-radius:4px;border:1px solid ${border};">${icon}</span>
                                            <strong style="font-size:0.78rem;color:#f8fafc;font-family:var(--font-mono);cursor:pointer;" onclick="app.inspectBreakoutStock('${l.ticker}')">${l.ticker}</strong>
                                            <span style="font-size:0.7rem;color:#94a3b8;">${l.company_name}</span>
                                            <span style="font-size:0.65rem;color:#64748b;">(${l.from_tier} ➔ ${l.to_tier})</span>
                                        </div>
                                        <div style="font-size:0.65rem;color:#64748b;font-family:var(--font-mono);">
                                            ${priceStr ? priceStr + ' | ' : ''} ${scoreStr ? scoreStr + ' | ' : ''} ${timeStr}
                                        </div>
                                    </div>
                                    <div style="font-size:0.72rem;color:#e2e8f0;line-height:1.35;margin-top:0.1rem;">
                                        <strong>Why:</strong> ${l.reason}
                                    </div>
                                    ${l.catalyst_impact ? `<div style="font-size:0.68rem;color:#38bdf8;margin-top:0.05rem;">📰 <em>Catalyst:</em> ${l.catalyst_impact}</div>` : ''}
                                </div>
                            `;
                        }).join('');
                    }
                } catch (e) {
                    console.error('Error loading breakout audit log:', e);
                    listEl.innerHTML = '<div style="color:#f87171;font-size:0.72rem;padding:0.5rem;">Failed loading movement logs.</div>';
                }
            },

    });
})(); // end breakout_audit IIFE