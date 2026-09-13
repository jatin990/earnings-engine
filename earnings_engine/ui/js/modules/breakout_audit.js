// =========================================================================
// breakout_audit — Nexus Dashboard Module (Breakout Movement & Tier Transition Logs)
// Extracted from dashboard.js — modularization 2026-08-28 & updated 2026-09-13
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    // Local helper to group raw transition logs into discrete scan cycles
    function groupLogsIntoScanBatches(logs) {
        if (!Array.isArray(logs) || !logs.length) return [];
        const batches = {};

        logs.forEach(l => {
            const rawTime = String(l.created_at || '');
            const timeKey = rawTime.length >= 16 ? rawTime.substring(0, 16).replace('T', ' ') : (rawTime || 'Recent Scan');

            if (!batches[timeKey]) {
                batches[timeKey] = {
                    batch_id: timeKey,
                    timestamp: rawTime,
                    total_moved: 0,
                    promoted_hot: 0,
                    added_warm: 0,
                    demoted_warm: 0,
                    removed_cold: 0,
                    target_hit: 0,
                    stopped_out: 0,
                    entries: []
                };
            }

            const b = batches[timeKey];
            b.total_moved += 1;
            const ev = String(l.event_type || '').toUpperCase();
            const toT = String(l.to_tier || '').toUpperCase();
            const fromT = String(l.from_tier || '').toUpperCase();

            if (ev === 'TARGET_HIT') {
                b.target_hit += 1;
            } else if (ev === 'STOPPED_OUT' || ev === 'STOP_LOSS_HIT' || ev === 'STOP_HIT') {
                b.stopped_out += 1;
            } else if (ev === 'PROMOTED_HOT' || toT === 'HOT') {
                b.promoted_hot += 1;
            } else if (ev === 'ADDED_WARM' || (toT === 'WARM' && fromT === 'COLD')) {
                b.added_warm += 1;
            } else if (ev === 'DEMOTED_WARM' || (toT === 'WARM' && fromT === 'HOT')) {
                b.demoted_warm += 1;
            } else if (ev === 'REMOVED_COLD' || ev === 'INVALIDATED' || ev === 'EXPIRED' || toT === 'COLD') {
                b.removed_cold += 1;
            }

            b.entries.push(l);
        });

        return Object.values(batches);
    }

    Object.assign(app, {
        _breakoutAuditOpen: false,
        _breakoutScanBatches: [],
        _breakoutRawLogs: [],
        _currentDrawerBatch: null,
        _currentDrawerFilter: 'ALL',

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
            const btnBadge = document.getElementById('breakoutAuditBtnBadge');

            try {
                const url = API_BASE + '/api/v1/breakout-radar/audit-log' + (ticker ? `?ticker=${encodeURIComponent(ticker)}` : '?limit=100');
                const res = await fetch(url);
                if (res.ok) {
                    const data = await res.json();
                    const logs = data.logs || [];
                    app._breakoutRawLogs = logs;

                    // Compute or consume scan batches
                    const batches = (data.scan_batches && data.scan_batches.length)
                        ? data.scan_batches
                        : groupLogsIntoScanBatches(logs);
                    app._breakoutScanBatches = batches;

                    const totalCount = (data.total_count !== undefined && data.total_count !== null) ? data.total_count : logs.length;

                    if (countBadge) {
                        countBadge.textContent = `(${totalCount.toLocaleString()} events · ${batches.length} scan cycles)`;
                    }
                    if (btnBadge) {
                        btnBadge.textContent = `(${totalCount.toLocaleString()})`;
                    }

                    // Hydrate Transition Macro Summary Chips
                    const summary = data.summary_stats || {};
                    const setSummaryEl = (id, val) => {
                        const el = document.getElementById(id);
                        if (el) el.textContent = Number(val || 0).toLocaleString();
                    };
                    setSummaryEl('breakoutAuditColdHot', summary.cold_to_hot);
                    setSummaryEl('breakoutAuditColdWarm', summary.cold_to_warm);
                    setSummaryEl('breakoutAuditWarmHot', summary.warm_to_hot);
                    setSummaryEl('breakoutAuditExits', summary.exits);

                    if (!listEl) return;

                    if (!batches.length) {
                        listEl.innerHTML = '<div style="text-align:center;color:#64748b;font-size:0.72rem;padding:0.75rem;">No recent tier movement events recorded yet. Transitions will appear automatically during scan cycles.</div>';
                        return;
                    }

                    // Render scan cycle rows
                    listEl.innerHTML = batches.map(b => {
                        const timeDisplay = b.batch_id.replace('T', ' ');
                        const chips = [];
                        if (b.promoted_hot > 0) chips.push(`<span style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);padding:0.1rem 0.35rem;border-radius:3px;font-size:0.65rem;font-weight:700;">🔥 ${b.promoted_hot} Hot</span>`);
                        if (b.added_warm > 0) chips.push(`<span style="background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.3);padding:0.1rem 0.35rem;border-radius:3px;font-size:0.65rem;font-weight:700;">⚡ ${b.added_warm} Warm</span>`);
                        if (b.target_hit > 0) chips.push(`<span style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);padding:0.1rem 0.35rem;border-radius:3px;font-size:0.65rem;font-weight:700;">🎯 ${b.target_hit} Targets</span>`);
                        if (b.demoted_warm > 0) chips.push(`<span style="background:rgba(245,158,11,0.10);color:#fde68a;border:1px solid rgba(245,158,11,0.2);padding:0.1rem 0.35rem;border-radius:3px;font-size:0.65rem;">📉 ${b.demoted_warm} Demoted</span>`);
                        if (b.removed_cold > 0) chips.push(`<span style="background:rgba(239,68,68,0.10);color:#fca5a5;border:1px solid rgba(239,68,68,0.2);padding:0.1rem 0.35rem;border-radius:3px;font-size:0.65rem;">❄️ ${b.removed_cold} Cold Exits</span>`);

                        return `
                            <div class="card cursor-pointer" onclick="app.openBreakoutScanDetailDrawer('${b.batch_id}')" style="background:#0c0c11;border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:0.45rem 0.75rem;display:flex;align-items:center;justify-content:space-between;transition:all 0.2s ease;gap:0.5rem;" onmouseover="this.style.borderColor='rgba(56,189,248,0.4)';this.style.background='#13131c';" onmouseout="this.style.borderColor='rgba(255,255,255,0.08)';this.style.background='#0c0c11';">
                                <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">
                                    <span style="font-size:0.75rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);display:flex;align-items:center;gap:0.3rem;">
                                        <span>⏱️</span> <span>Scan Cycle · ${timeDisplay}</span>
                                    </span>
                                    <span style="font-size:0.65rem;background:#18181b;color:#94a3b8;padding:0.08rem 0.35rem;border-radius:3px;border:1px solid rgba(255,255,255,0.1);font-family:var(--font-mono);">${b.total_moved} ${b.total_moved === 1 ? 'setup' : 'setups'} moved</span>
                                    <div style="display:flex;gap:0.3rem;align-items:center;flex-wrap:wrap;">
                                        ${chips.join('')}
                                    </div>
                                </div>
                                <button type="button" class="btn btn-xs" style="background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);font-size:0.65rem;font-weight:700;padding:0.15rem 0.5rem;border-radius:4px;cursor:pointer;white-space:nowrap;">
                                    🔍 Inspect Scan ➔
                                </button>
                            </div>
                        `;
                    }).join('');
                }
            } catch (e) {
                console.error('Error loading breakout audit log:', e);
                if (listEl) listEl.innerHTML = '<div style="color:#f87171;font-size:0.72rem;padding:0.5rem;">Failed loading movement logs.</div>';
            }
        },

        openBreakoutScanDetailDrawer(batchId) {
            const batch = (app._breakoutScanBatches || []).find(b => b.batch_id === batchId);
            if (!batch) return;

            app._currentDrawerBatch = batch;
            app._currentDrawerFilter = 'ALL';

            const drawer = document.getElementById('breakoutScanDetailDrawer');
            const titleEl = document.getElementById('breakoutScanDrawerTitle');
            const subEl = document.getElementById('breakoutScanDrawerSubtitle');
            if (!drawer) return;

            if (titleEl) titleEl.textContent = `Scan Cycle Inspector · ${batch.batch_id}`;
            if (subEl) subEl.textContent = `${batch.total_moved} Setups Evaluated & Moved in this Scan Run`;

            app.renderBreakoutScanDrawerContent();
            drawer.style.display = 'flex';
        },

        closeBreakoutScanDetailDrawer() {
            const drawer = document.getElementById('breakoutScanDetailDrawer');
            if (drawer) drawer.style.display = 'none';
        },

        setBreakoutDrawerFilter(filter) {
            app._currentDrawerFilter = filter;
            app.renderBreakoutScanDrawerContent();
        },

        renderBreakoutScanDrawerContent() {
            const batch = app._currentDrawerBatch;
            if (!batch) return;

            const pillsContainer = document.getElementById('breakoutScanDrawerPills');
            const listContainer = document.getElementById('breakoutScanDrawerList');
            if (!pillsContainer || !listContainer) return;

            // Render filter pills
            const filter = app._currentDrawerFilter;
            pillsContainer.innerHTML = `
                <button type="button" onclick="app.setBreakoutDrawerFilter('ALL')" class="btn-micro" style="padding:0.35rem 0.75rem;font-size:0.75rem;font-weight:700;border-radius:5px;background:${filter === 'ALL' ? '#2563eb' : '#18181b'};color:${filter === 'ALL' ? '#fff' : '#94a3b8'};border:1px solid rgba(255,255,255,0.15);cursor:pointer;">All (${batch.total_moved})</button>
                <button type="button" onclick="app.setBreakoutDrawerFilter('HOT')" class="btn-micro" style="padding:0.35rem 0.75rem;font-size:0.75rem;font-weight:700;border-radius:5px;background:${filter === 'HOT' ? 'rgba(239,68,68,0.25)' : '#18181b'};color:#f87171;border:1px solid rgba(239,68,68,0.3);cursor:pointer;">🔥 Hot (${batch.promoted_hot})</button>
                <button type="button" onclick="app.setBreakoutDrawerFilter('WARM')" class="btn-micro" style="padding:0.35rem 0.75rem;font-size:0.75rem;font-weight:700;border-radius:5px;background:${filter === 'WARM' ? 'rgba(245,158,11,0.25)' : '#18181b'};color:#fbbf24;border:1px solid rgba(245,158,11,0.3);cursor:pointer;">⚡ Warm (${batch.added_warm})</button>
                ${batch.target_hit > 0 ? `<button type="button" onclick="app.setBreakoutDrawerFilter('TARGET')" class="btn-micro" style="padding:0.35rem 0.75rem;font-size:0.75rem;font-weight:700;border-radius:5px;background:${filter === 'TARGET' ? 'rgba(16,185,129,0.25)' : '#18181b'};color:#34d399;border:1px solid rgba(16,185,129,0.3);cursor:pointer;">🎯 Targets (${batch.target_hit})</button>` : ''}
                ${(batch.demoted_warm + batch.removed_cold) > 0 ? `<button type="button" onclick="app.setBreakoutDrawerFilter('EXITS')" class="btn-micro" style="padding:0.35rem 0.75rem;font-size:0.75rem;font-weight:700;border-radius:5px;background:${filter === 'EXITS' ? 'rgba(239,68,68,0.2)' : '#18181b'};color:#fca5a5;border:1px solid rgba(239,68,68,0.2);cursor:pointer;">Exits (${batch.demoted_warm + batch.removed_cold})</button>` : ''}
            `;

            // Filter entries
            let entries = batch.entries;
            if (filter === 'HOT') {
                entries = entries.filter(l => l.event_type === 'PROMOTED_HOT' || l.to_tier === 'HOT');
            } else if (filter === 'WARM') {
                entries = entries.filter(l => l.event_type === 'ADDED_WARM' || (l.to_tier === 'WARM' && l.from_tier === 'COLD'));
            } else if (filter === 'TARGET') {
                entries = entries.filter(l => l.event_type === 'TARGET_HIT');
            } else if (filter === 'EXITS') {
                entries = entries.filter(l => l.event_type === 'DEMOTED_WARM' || l.event_type === 'REMOVED_COLD' || l.to_tier === 'COLD');
            }

            if (!entries.length) {
                listContainer.innerHTML = '<div style="text-align:center;color:#64748b;font-size:0.82rem;padding:2rem;">No setups matching selected tier filter in this scan.</div>';
                return;
            }

            listContainer.innerHTML = entries.map(l => {
                const isTargetHit = l.event_type === 'TARGET_HIT';
                const isPromoted = l.event_type === 'PROMOTED_HOT' || l.to_tier === 'HOT';
                const isAdded = l.event_type === 'ADDED_WARM';
                const isDemoted = l.event_type === 'DEMOTED_WARM' || l.to_tier === 'WARM';
                const isRemoved = l.event_type === 'REMOVED_COLD' || l.to_tier === 'COLD';

                const bg = isTargetHit ? 'rgba(16,185,129,0.12)' : isPromoted ? 'rgba(239,68,68,0.10)' : isAdded ? 'rgba(245,158,11,0.10)' : isDemoted ? 'rgba(245,158,11,0.08)' : 'rgba(239,68,68,0.08)';
                const border = isTargetHit ? 'rgba(16,185,129,0.45)' : isPromoted ? 'rgba(239,68,68,0.35)' : isAdded ? 'rgba(245,158,11,0.35)' : isDemoted ? 'rgba(245,158,11,0.25)' : 'rgba(239,68,68,0.25)';
                const color = isTargetHit ? '#10b981' : isPromoted ? '#f87171' : isAdded ? '#fbbf24' : isDemoted ? '#fde68a' : '#f87171';
                const badgeLabel = isTargetHit ? '🎯 TARGET HIT' : isPromoted ? '🔥 PROMOTED HOT' : isAdded ? '⚡ ADDED WARM' : isDemoted ? '📉 DEMOTED WARM' : '❌ REMOVED COLD';

                const priceStr = l.price ? `₹${Number(l.price).toFixed(2)}` : '—';
                const triggerStr = l.trigger_price ? `₹${Number(l.trigger_price).toFixed(2)}` : null;
                const targetStr = l.target_price ? `₹${Number(l.target_price).toFixed(2)}` : null;
                const stopStr = l.stop_loss ? `₹${Number(l.stop_loss).toFixed(2)}` : null;
                const scoreBefore = l.score_before != null ? l.score_before : '—';
                const scoreAfter = l.score_after != null ? l.score_after : '—';
                const counterBadge = (l.counter && l.counter > 1) ? `<span style="font-size:0.68rem;font-weight:700;color:#38bdf8;background:rgba(56,189,248,0.15);padding:0.1rem 0.4rem;border-radius:4px;border:1px solid rgba(56,189,248,0.3);">🔁 ${l.counter}x</span>` : '';

                return `
                    <div style="background:${bg};border:1px solid ${border};border-radius:8px;padding:0.75rem 0.9rem;display:flex;flex-direction:column;gap:0.45rem;">
                        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.4rem;">
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span style="font-size:0.70rem;font-weight:800;color:${color};background:#000;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid ${border};">${badgeLabel}</span>
                                <strong style="font-size:1.02rem;color:#f8fafc;font-family:var(--font-mono);font-weight:800;cursor:pointer;" onclick="app.inspectBreakoutStock('${l.ticker}')" title="Click to view setup details in HUD">${l.ticker}</strong>
                                <span style="font-size:0.76rem;color:#94a3b8;">${l.company_name || ''}</span>
                                ${counterBadge}
                            </div>
                            <div style="display:flex;align-items:center;gap:0.4rem;">
                                <button type="button" onclick="app.inspectBreakoutStock('${l.ticker}'); event.stopPropagation();" class="btn btn-xs" style="background:#18181b;color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-size:0.72rem;font-weight:700;padding:0.2rem 0.5rem;border-radius:4px;cursor:pointer;">⚡ HUD</button>
                                <button type="button" onclick="app.openStockModal('${l.ticker}'); event.stopPropagation();" class="btn btn-xs" style="background:#18181b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.2);font-size:0.72rem;font-weight:600;padding:0.2rem 0.5rem;border-radius:4px;cursor:pointer;">📈 Chart</button>
                            </div>
                        </div>

                        <!-- Transition Metric Strip -->
                        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(95px, 1fr));gap:0.4rem;background:#030305;border:1px solid rgba(255,255,255,0.08);border-radius:5px;padding:0.45rem 0.65rem;font-size:0.74rem;font-family:var(--font-mono);">
                            <div><span style="color:#94a3b8;">Price:</span> <strong style="color:#f8fafc;font-size:0.80rem;">${priceStr}</strong></div>
                            <div><span style="color:#94a3b8;">Score:</span> <strong style="color:#60a5fa;font-size:0.80rem;">${scoreBefore} ➔ ${scoreAfter}</strong></div>
                            ${triggerStr ? `<div><span style="color:#94a3b8;">Trigger:</span> <strong style="color:#fbbf24;font-size:0.80rem;">${triggerStr}</strong></div>` : ''}
                            ${targetStr ? `<div><span style="color:#94a3b8;">Target:</span> <strong style="color:#34d399;font-size:0.80rem;">${targetStr}</strong></div>` : ''}
                            ${stopStr ? `<div><span style="color:#94a3b8;">Stop:</span> <strong style="color:#f87171;font-size:0.80rem;">${stopStr}</strong></div>` : ''}
                        </div>

                        <!-- Reason / Explanation -->
                        <div style="font-size:0.78rem;color:#e2e8f0;line-height:1.45;margin-top:0.05rem;">
                            <strong style="color:#ffffff;">Why:</strong> ${l.reason || 'Multi-speed tier evaluation'}
                        </div>
                        ${l.catalyst_impact ? `<div style="font-size:0.74rem;color:#38bdf8;line-height:1.4;">📰 <strong style="color:#93c5fd;">Catalyst:</strong> ${l.catalyst_impact}</div>` : ''}
                    </div>
                `;
            }).join('');
        }
    });
})(); // end breakout_audit IIFE
