// =========================================================================
// 🌐 Universal Hot / Warm / Cold Tier & Pool Management Frontend Plugin
// Standardized UI components for graduated multi-speed scanning & audits
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin || '';

    window.TierPoolUI = {
        /**
         * Render standardized Hot / Warm / All toggle pills into a container.
         * @param {Object} options
         * @param {string} options.containerId Container element ID
         * @param {string} options.activeTier Currently active tier ('ALL', 'HOT', 'WARM', 'COLD')
         * @param {Object} options.counts Object with counts { hot: 0, warm: 0, total: 0 }
         * @param {Function} options.onSelect Callback function (tier) => void
         * @param {string} [options.prefix] Optional prefix for element IDs (default: 'tierPill')
         */
        renderTierPills({ containerId, activeTier = 'ALL', counts = {}, onSelect, prefix = 'tierPill' }) {
            const container = document.getElementById(containerId);
            if (!container) return;

            const hotCount = Number(counts.hot || 0).toLocaleString();
            const warmCount = Number(counts.warm || 0).toLocaleString();
            const totalCount = Number(counts.total || 0).toLocaleString();

            const isAll = activeTier === 'ALL';
            const isHot = activeTier === 'HOT';
            const isWarm = activeTier === 'WARM';

            container.innerHTML = `
                <div class="tier-pill-group" style="display:inline-flex;align-items:center;background:#030305;border:1px solid rgba(255,255,255,0.1);border-radius:0.4rem;padding:2px;gap:2px;">
                    <button type="button" id="${prefix}-ALL" class="btn-micro ${isAll ? 'btn-primary' : ''}" style="padding:0.2rem 0.55rem;font-size:0.70rem;font-weight:${isAll ? '700' : '500'};border-radius:0.3rem;background:${isAll ? '#2563eb' : 'transparent'};color:${isAll ? '#ffffff' : '#94a3b8'};border:none;cursor:pointer;" title="View all tracked candidates">
                        🌐 All (${totalCount})
                    </button>
                    <button type="button" id="${prefix}-HOT" class="btn-micro ${isHot ? 'btn-primary' : ''}" style="padding:0.2rem 0.55rem;font-size:0.70rem;font-weight:${isHot ? '700' : '500'};border-radius:0.3rem;background:${isHot ? '#dc2626' : 'transparent'};color:${isHot ? '#ffffff' : '#f87171'};border:none;cursor:pointer;" title="Hot Tier: High velocity immediate action candidates">
                        🔥 Hot (${hotCount})
                    </button>
                    <button type="button" id="${prefix}-WARM" class="btn-micro ${isWarm ? 'btn-primary' : ''}" style="padding:0.2rem 0.55rem;font-size:0.70rem;font-weight:${isWarm ? '700' : '500'};border-radius:0.3rem;background:${isWarm ? '#d97706' : 'transparent'};color:${isWarm ? '#ffffff' : '#fbbf24'};border:none;cursor:pointer;" title="Warm Tier: Coiling setup / compression candidates">
                        ⚡ Warm (${warmCount})
                    </button>
                </div>
            `;

            // Attach event listeners
            ['ALL', 'HOT', 'WARM'].forEach(tier => {
                const btn = document.getElementById(`${prefix}-${tier}`);
                if (btn && onSelect) {
                    btn.addEventListener('click', () => onSelect(tier));
                }
            });
        },

        /**
         * Render standardized Tier Badge HTML.
         * @param {string} tier 'HOT' | 'WARM' | 'COLD'
         * @returns {string} HTML markup for tier badge
         */
        renderTierBadge(tier) {
            const t = (tier || '').toUpperCase();
            if (t === 'HOT') {
                return '<span class="signal-badge" style="background:rgba(239,68,68,0.18);color:#f87171;border:1px solid rgba(239,68,68,0.4);font-weight:700;font-size:0.62rem;padding:0.1rem 0.35rem;border-radius:3px;">🔥 HOT</span>';
            }
            if (t === 'WARM') {
                return '<span class="signal-badge" style="background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);font-weight:700;font-size:0.62rem;padding:0.1rem 0.35rem;border-radius:3px;">⚡ WARM</span>';
            }
            return '<span class="signal-badge" style="background:rgba(100,116,139,0.15);color:#94a3b8;border:1px solid rgba(100,116,139,0.3);font-size:0.62rem;padding:0.1rem 0.35rem;border-radius:3px;">❄️ COLD</span>';
        },

        /**
         * Fetch and render strategy tier audit transitions log into a specified list element.
         * @param {Object} options
         * @param {string} options.domain Strategy domain ('breakout', 'swing', etc.)
         * @param {string} [options.ticker] Optional ticker filter
         * @param {string} options.containerId ID of element to inject log rows into
         * @param {string} [options.countBadgeId] ID of element to display total count
         * @param {Object} [options.summaryElements] IDs of elements to update with macro summary counts
         */
        async loadAuditLog({ domain, ticker = null, containerId, countBadgeId = null, summaryElements = {} }) {
            const listEl = document.getElementById(containerId);
            const countBadge = countBadgeId ? document.getElementById(countBadgeId) : null;
            if (!listEl) return;

            try {
                const endpoint = domain === 'breakout'
                    ? '/api/v1/breakout-radar/audit-log'
                    : `/api/v1/${domain}/audit-log`;

                const url = API_BASE + endpoint + (ticker ? `?ticker=${encodeURIComponent(ticker)}` : '?limit=40');
                const res = await fetch(url);
                if (res.ok) {
                    const data = await res.json();
                    const logs = data.logs || [];
                    const totalCount = (data.total_count !== undefined && data.total_count !== null) ? data.total_count : logs.length;
                    if (countBadge) countBadge.textContent = `(${totalCount.toLocaleString()} events)`;

                    // Hydrate Macro Summary Chips if provided
                    const summary = data.summary_stats || {};
                    if (summaryElements.coldToHot) {
                        const el = document.getElementById(summaryElements.coldToHot);
                        if (el) el.textContent = Number(summary.cold_to_hot || 0).toLocaleString();
                    }
                    if (summaryElements.coldToWarm) {
                        const el = document.getElementById(summaryElements.coldToWarm);
                        if (el) el.textContent = Number(summary.cold_to_warm || 0).toLocaleString();
                    }
                    if (summaryElements.warmToHot) {
                        const el = document.getElementById(summaryElements.warmToHot);
                        if (el) el.textContent = Number(summary.warm_to_hot || 0).toLocaleString();
                    }
                    if (summaryElements.exits) {
                        const el = document.getElementById(summaryElements.exits);
                        if (el) el.textContent = Number(summary.exits || 0).toLocaleString();
                    }

                    if (!logs.length) {
                        listEl.innerHTML = '<div style="text-align:center;color:#64748b;font-size:0.72rem;padding:0.75rem;">No recent tier movement events recorded yet. Transitions appear automatically during scan cycles.</div>';
                        return;
                    }

                    listEl.innerHTML = logs.map(l => {
                        const isTargetHit = l.event_type === 'TARGET_HIT';
                        const isPromotedHot = l.event_type === 'PROMOTED_HOT';
                        const isAddedWarm = l.event_type === 'ADDED_WARM';
                        const isDemoted = l.event_type === 'DEMOTED_WARM' || l.event_type === 'REMOVED_COLD';

                        let badgeColor = '#94a3b8';
                        let badgeBg = 'rgba(148,163,184,0.12)';
                        let badgeBorder = 'rgba(148,163,184,0.25)';
                        let icon = '🔄';

                        if (isTargetHit) {
                            badgeColor = '#34d399';
                            badgeBg = 'rgba(16,185,129,0.18)';
                            badgeBorder = 'rgba(16,185,129,0.4)';
                            icon = '🎯';
                        } else if (isPromotedHot) {
                            badgeColor = '#f87171';
                            badgeBg = 'rgba(239,68,68,0.18)';
                            badgeBorder = 'rgba(239,68,68,0.4)';
                            icon = '🔥';
                        } else if (isAddedWarm) {
                            badgeColor = '#fbbf24';
                            badgeBg = 'rgba(245,158,11,0.18)';
                            badgeBorder = 'rgba(245,158,11,0.4)';
                            icon = '⚡';
                        } else if (isDemoted) {
                            badgeColor = '#94a3b8';
                            badgeBg = 'rgba(100,116,139,0.18)';
                            badgeBorder = 'rgba(100,116,139,0.35)';
                            icon = '❄️';
                        }

                        const dt = (l.created_at || '').replace('T', ' ').substring(0, 19);
                        const strat = l.strategy ? `<span style="color:#38bdf8;font-size:0.65rem;margin-left:0.35rem;">[${l.strategy}]</span>` : '';
                        const counterBadge = (l.counter && l.counter > 1)
                            ? `<span style="background:rgba(59,130,246,0.2);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);border-radius:8px;padding:0.05rem 0.35rem;font-size:0.60rem;font-weight:700;margin-left:0.35rem;">×${l.counter} confirmations</span>`
                            : '';

                        return `
                            <div style="display:flex;justify-content:space-between;align-items:center;padding:0.35rem 0.55rem;background:#030305;border:1px solid rgba(255,255,255,0.05);border-radius:0.35rem;margin-bottom:0.25rem;font-size:0.72rem;">
                                <div style="display:flex;align-items:center;gap:0.45rem;">
                                    <span style="font-size:0.85rem;">${icon}</span>
                                    <div>
                                        <strong style="color:#ffffff;font-family:var(--font-mono);">${l.ticker}</strong>${strat}${counterBadge}
                                        <div style="font-size:0.65rem;color:#94a3b8;margin-top:0.1rem;">
                                            ${l.reason || l.event_type} • Price: ₹${Number(l.price || 0).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 2})} • Score: ${l.score_after || 0}
                                        </div>
                                    </div>
                                </div>
                                <div style="text-align:right;">
                                    <span class="signal-badge" style="background:${badgeBg};color:${badgeColor};border:1px solid ${badgeBorder};font-size:0.62rem;font-weight:700;padding:0.08rem 0.35rem;">
                                        ${l.from_tier || 'INIT'} ➔ ${l.to_tier || 'COLD'}
                                    </span>
                                    <div style="font-size:0.60rem;color:#64748b;margin-top:0.15rem;font-family:var(--font-mono);">${dt}</div>
                                </div>
                            </div>
                        `;
                    }).join('');
                }
            } catch (err) {
                console.error(`[TierPoolUI] Failed to load audit log for ${domain}:`, err);
                if (listEl) listEl.innerHTML = '<div style="color:var(--red);font-size:0.72rem;padding:0.5rem;text-align:center;">Failed to fetch audit log from server.</div>';
            }
        }
    };
})();
