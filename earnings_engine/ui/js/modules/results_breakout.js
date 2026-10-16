// =========================================================================
// results_breakout.js — Results Breakout Radar Frontend Module
// Nexus Intelligence Platform · Quantitative Equity Scanner
// Dedicated radar for declared/upcoming earnings (-3D to +7D default window)
// =========================================================================

(function () {
    'use strict';

    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    // Module internal state
    app._resultsRadarData = [];
    app._resultsRadarWindow = { past_days: 3, future_days: 7 };
    app._selectedResultsTicker = null;
    app._resultsRadarLoading = false;

    // Helper: Escape HTML to prevent injection
    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
        );
    }

    // Helper: Format currency in INR
    function _fmtPrice(num) {
        if (num == null || isNaN(num)) return '—';
        return '₹' + Number(num).toLocaleString('en-IN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    // Helper: Format percentage
    function _fmtPct(num, includeSign = true) {
        if (num == null || isNaN(num)) return '—';
        const val = Number(num);
        const prefix = (val > 0 && includeSign) ? '+' : '';
        return prefix + val.toFixed(2) + '%';
    }

    // Helper: Archetype display metadata
    function _archetypeMeta(arch) {
        switch (arch) {
            case 'RDH_EXPANSION':
                return {
                    label: 'RDH Expansion',
                    icon: '🔥',
                    color: '#ef4444',
                    bg: 'rgba(239, 68, 68, 0.15)',
                    border: 'rgba(239, 68, 68, 0.35)',
                    desc: 'Price testing or breaking above Result-Day High on volume expansion'
                };
            case 'PEAD_MOMENTUM':
                return {
                    label: 'PEAD Drift',
                    icon: '🚀',
                    color: '#38bdf8',
                    bg: 'rgba(56, 189, 248, 0.15)',
                    border: 'rgba(56, 189, 248, 0.35)',
                    desc: 'Post-Earnings Announcement Drift holding above pre-result close'
                };
            case 'PRE_EARNINGS_COIL':
                return {
                    label: 'Pre-Result Coil',
                    icon: '⚡',
                    color: '#fbbf24',
                    bg: 'rgba(251, 191, 36, 0.15)',
                    border: 'rgba(251, 191, 36, 0.35)',
                    desc: 'Pre-earnings volatility compression within striking distance of resistance'
                };
            case 'POST_RESULT_RECOVERY':
                return {
                    label: 'Post-Dip Recovery',
                    icon: '🛡️',
                    color: '#a78bfa',
                    bg: 'rgba(167, 139, 250, 0.15)',
                    border: 'rgba(167, 139, 250, 0.35)',
                    desc: 'Knee-jerk dip absorbed with price recovering back above pre-result close'
                };
            default:
                return {
                    label: arch || 'Setup',
                    icon: '📊',
                    color: '#94a3b8',
                    bg: 'rgba(148, 163, 184, 0.15)',
                    border: 'rgba(148, 163, 184, 0.35)',
                    desc: 'Results breakout setup candidate'
                };
        }
    }

    // -------------------------------------------------------------------------
    // Main Fetch: Load Results Breakout Radar Candidates
    // -------------------------------------------------------------------------
    app.loadResultsRadar = async function () {
        if (app._resultsRadarLoading) return;

        const pastInput = document.getElementById('resultsPastDaysInput');
        const futureInput = document.getElementById('resultsFutureDaysInput');
        const minScoreSelect = document.getElementById('resultsMinScoreSelect');
        const archetypeSelect = document.getElementById('resultsArchetypeSelect');
        const universeSelect = document.getElementById('resultsUniverseSelect');
        const refreshIcon = document.getElementById('resultsRefreshIcon');
        const tbody = document.getElementById('resultsBreakoutTableBody');

        const pastDays = Math.max(0, Math.min(30, parseInt(pastInput?.value || '3', 10)));
        const futureDays = Math.max(0, Math.min(30, parseInt(futureInput?.value || '7', 10)));
        const minScore = Math.max(0, Math.min(100, parseInt(minScoreSelect?.value || '30', 10)));
        const archetype = archetypeSelect?.value || 'ALL';
        const universe = universeSelect?.value || 'all';

        app._resultsRadarLoading = true;
        if (refreshIcon) refreshIcon.style.animation = 'spin 1s linear infinite';
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" style="padding: 2.5rem; text-align: center; color: #94a3b8; font-size: 0.75rem;">
                        <div style="display: inline-block; animation: spin 1s linear infinite; margin-right: 0.4rem;">⏳</div>
                        Scanning declared (-${pastDays}D) and upcoming (+${futureDays}D) results candidates...
                    </td>
                </tr>
            `;
        }

        try {
            const url = `${API_BASE}/api/breakout/results-radar?past_days=${pastDays}&future_days=${futureDays}&archetype=${encodeURIComponent(archetype)}&min_score=${minScore}&universe=${encodeURIComponent(universe)}`;
            const resp = await fetch(url);
            if (!resp.ok) {
                throw new Error(`Server returned HTTP ${resp.status}`);
            }
            const data = await resp.json();

            app._resultsRadarData = Array.isArray(data.items) ? data.items : [];
            app._resultsRadarWindow = data.window || { past_days: pastDays, future_days: futureDays };

            // Update KPI summary strip
            const summary = data.summary || {};
            const elTotal = document.getElementById('resultsStatTotal');
            const elDeclared = document.getElementById('resultsStatDeclared');
            const elUpcoming = document.getElementById('resultsStatUpcoming');
            const elHot = document.getElementById('resultsStatHot');
            const elTop = document.getElementById('resultsStatTopScore');

            if (elTotal) elTotal.textContent = summary.total_candidates ?? app._resultsRadarData.length;
            if (elDeclared) elDeclared.textContent = summary.declared_results ?? '—';
            if (elUpcoming) elUpcoming.textContent = summary.upcoming_results ?? '—';
            if (elHot) elHot.textContent = summary.hot_setups ?? '—';
            if (elTop) elTop.textContent = summary.top_conviction_score ? Math.round(summary.top_conviction_score) : '—';

            // Render table
            app.filterResultsRadar();

        } catch (err) {
            console.error('Failed to load results radar:', err);
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="9" style="padding: 2rem; text-align: center; color: #f87171; font-size: 0.75rem;">
                            ⚠️ Error loading results breakout radar: ${_esc(err.message)}
                        </td>
                    </tr>
                `;
            }
        } finally {
            app._resultsRadarLoading = false;
            if (refreshIcon) refreshIcon.style.animation = '';
        }
    };

    // -------------------------------------------------------------------------
    // Preset & Window Stepper Handlers
    // -------------------------------------------------------------------------
    app.setResultsRadarPreset = function (pastDays, futureDays, btnElement) {
        const pastInput = document.getElementById('resultsPastDaysInput');
        const futureInput = document.getElementById('resultsFutureDaysInput');
        if (pastInput) pastInput.value = pastDays;
        if (futureInput) futureInput.value = futureDays;

        // Toggle active preset button state
        document.querySelectorAll('.bk-preset-btn').forEach(btn => btn.classList.remove('active'));
        if (btnElement) btnElement.classList.add('active');

        app.loadResultsRadar();
    };

    app.onResultsRadarWindowChange = function () {
        // Clear active class from presets when manual inputs change
        document.querySelectorAll('.bk-preset-btn').forEach(btn => btn.classList.remove('active'));
        app.loadResultsRadar();
    };

    // -------------------------------------------------------------------------
    // Client-side Filtering (Search Query & Archetype Filter)
    // -------------------------------------------------------------------------
    app.filterResultsRadar = function () {
        const searchInput = document.getElementById('resultsSearchInput');
        const archSelect = document.getElementById('resultsArchetypeSelect');
        const query = (searchInput?.value || '').trim().toUpperCase();
        const arch = archSelect?.value || 'ALL';

        let filtered = app._resultsRadarData || [];

        if (arch !== 'ALL') {
            filtered = filtered.filter(item => item.archetype === arch);
        }

        if (query) {
            filtered = filtered.filter(item => {
                const sym = (item.symbol || item.ticker || '').toUpperCase();
                return sym.includes(query);
            });
        }

        app.renderResultsRadarTable(filtered);
    };

    // -------------------------------------------------------------------------
    // Render Results Breakout Table
    // -------------------------------------------------------------------------
    app.renderResultsRadarTable = function (items) {
        const tbody = document.getElementById('resultsBreakoutTableBody');
        const footerCount = document.getElementById('resultsFooterCount');
        if (!tbody) return;

        if (footerCount) {
            footerCount.textContent = `${items.length} candidate${items.length === 1 ? '' : 's'} (${app._resultsRadarWindow.past_days}D past / +${app._resultsRadarWindow.future_days}D upcoming)`;
        }

        if (!items || items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" style="padding: 2.5rem; text-align: center; color: #71717a; font-size: 0.75rem;">
                        <div style="font-size: 1.3rem; margin-bottom: 0.4rem;">🔍</div>
                        <div style="font-weight: 700; color: #a1a1aa;">No Earnings Candidates Found</div>
                        <div style="font-size: 0.68rem; margin-top: 0.2rem; color: #52525b;">Try expanding the past/future day window or lowering the conviction score threshold.</div>
                    </td>
                </tr>
            `;
            const inspector = document.getElementById('resultsInspectorContent');
            if (inspector) {
                inspector.innerHTML = `
                    <div class="card" style="padding: 2rem; text-align: center; background: #09090b; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; color: #71717a;">
                        <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📊</div>
                        <div style="font-size: 0.82rem; font-weight: 700; color: #f8fafc;">No Candidate Selected</div>
                        <div style="font-size: 0.68rem; margin-top: 0.25rem; color: #a1a1aa;">No matching stocks in the current results window.</div>
                    </div>
                `;
            }
            return;
        }

        // If currently selected ticker is not in items, select first item
        const selectedExists = items.some(it => it.ticker === app._selectedResultsTicker);
        if (!selectedExists) {
            app._selectedResultsTicker = items[0].ticker;
        }

        let html = '';
        items.forEach((item) => {
            const isSelected = item.ticker === app._selectedResultsTicker;
            const rowStyle = isSelected
                ? 'background: rgba(56, 189, 248, 0.10); border-left: 3px solid #38bdf8;'
                : 'border-left: 3px solid transparent;';

            const arch = _archetypeMeta(item.archetype);
            const isDeclared = item.is_declared;
            const daysDiff = item.days_since_result;

            // Timing badge
            let timingBadge = '';
            if (isDeclared) {
                timingBadge = `<span class="signal-badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-size: 0.64rem; padding: 0.1rem 0.35rem;" title="Declared ${item.earnings_date}">🟢 -${Math.abs(daysDiff)}D</span>`;
            } else {
                timingBadge = `<span class="signal-badge" style="background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); font-size: 0.64rem; padding: 0.1rem 0.35rem;" title="Upcoming ${item.earnings_date}">⏳ +${daysDiff}D</span>`;
            }

            // Distance to trigger styling
            const dist = item.trade_levels?.dist_to_trigger_pct;
            let distColor = '#94a3b8';
            if (dist != null) {
                if (dist >= 0) distColor = '#4ade80';
                else if (dist >= -1.5) distColor = '#38bdf8';
                else distColor = '#fbbf24';
            }

            // Volume surge ratio
            const volSurge = item.technicals?.volume_ratio_20d;
            let volColor = '#94a3b8';
            if (volSurge != null) {
                if (volSurge >= 1.5) volColor = '#4ade80';
                else if (volSurge >= 1.15) volColor = '#38bdf8';
            }

            // Score pill
            const score = Math.round(item.composite_score || 0);
            let scoreBg = 'rgba(148, 163, 184, 0.15)';
            let scoreColor = '#94a3b8';
            if (score >= 70) {
                scoreBg = 'rgba(74, 222, 128, 0.2)';
                scoreColor = '#4ade80';
            } else if (score >= 50) {
                scoreBg = 'rgba(56, 189, 248, 0.2)';
                scoreColor = '#38bdf8';
            } else if (score >= 30) {
                scoreBg = 'rgba(251, 191, 36, 0.2)';
                scoreColor = '#fbbf24';
            }

            html += `
                <tr
                    onclick="app.inspectResultsCandidate('${_esc(item.ticker)}')"
                    style="${rowStyle} cursor: pointer; transition: background 0.15s; border-bottom: 1px solid rgba(255,255,255,0.05);"
                    onmouseover="if(this.style.borderLeftColor !== 'rgb(56, 189, 248)') this.style.background='rgba(255,255,255,0.03)';"
                    onmouseout="if(this.style.borderLeftColor !== 'rgb(56, 189, 248)') this.style.background='transparent';"
                >
                    <td style="padding: 0.45rem 0.6rem; font-family: var(--font-mono); font-weight: 700; color: #f8fafc;">
                        ${_esc(item.symbol)}
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono);">
                        ${timingBadge}
                    </td>
                    <td style="padding: 0.45rem 0.5rem;">
                        <span class="signal-badge" style="background: ${arch.bg}; color: ${arch.color}; border: 1px solid ${arch.border}; font-size: 0.64rem; padding: 0.1rem 0.35rem;" title="${_esc(arch.desc)}">
                            ${arch.icon} ${_esc(arch.label)}
                        </span>
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono); font-weight: 600; color: #f8fafc;">
                        ${_fmtPrice(item.current_price)}
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono); color: #cbd5e1;">
                        ${_fmtPrice(item.trade_levels?.breakout_trigger)}
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono); font-weight: 700; color: ${distColor};">
                        ${_fmtPct(dist)}
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono); font-weight: 600; color: ${volColor};">
                        ${volSurge != null ? volSurge.toFixed(2) + 'x' : '—'}
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono);">
                        <span style="display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 800; font-size: 0.72rem; background: ${scoreBg}; color: ${scoreColor};">
                            ${score}
                        </span>
                    </td>
                    <td style="padding: 0.45rem 0.4rem; text-align: center;">
                        <button
                            type="button"
                            class="btn btn-sm"
                            onclick="event.stopPropagation(); app.inspectResultsCandidate('${_esc(item.ticker)}')"
                            style="padding: 0.15rem 0.45rem; font-size: 0.65rem; background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); border-radius: 3px;"
                            title="Inspect setup details"
                        >
                            Inspect
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;

        // Render inspector for the selected ticker
        if (app._selectedResultsTicker) {
            app.inspectResultsCandidate(app._selectedResultsTicker, false);
        }
    };

    // -------------------------------------------------------------------------
    // Inspect Candidate Setup Anatomy
    // -------------------------------------------------------------------------
    app.inspectResultsCandidate = function (ticker, reRenderTable = true) {
        app._selectedResultsTicker = ticker;
        const candidate = (app._resultsRadarData || []).find(it => it.ticker === ticker);
        const container = document.getElementById('resultsInspectorContent');
        if (!container || !candidate) return;

        if (reRenderTable) {
            // Update table row active styles quickly without full re-render
            const tbody = document.getElementById('resultsBreakoutTableBody');
            if (tbody) {
                Array.from(tbody.querySelectorAll('tr')).forEach(tr => {
                    const symCell = tr.querySelector('td');
                    if (symCell && symCell.textContent.trim() === candidate.symbol) {
                        tr.style.background = 'rgba(56, 189, 248, 0.10)';
                        tr.style.borderLeft = '3px solid #38bdf8';
                    } else {
                        tr.style.background = 'transparent';
                        tr.style.borderLeft = '3px solid transparent';
                    }
                });
            }
        }

        const arch = _archetypeMeta(candidate.archetype);
        const tl = candidate.trade_levels || {};
        const rs = candidate.result_structure || {};
        const tech = candidate.technicals || {};
        const score = Math.round(candidate.composite_score || 0);

        const isDeclared = candidate.is_declared;
        const daysDiff = candidate.days_since_result;
        const timingLabel = isDeclared
            ? `🟢 Declared ${Math.abs(daysDiff)} Day${Math.abs(daysDiff) === 1 ? '' : 's'} Ago (${candidate.earnings_date})`
            : `⏳ Upcoming in ${daysDiff} Day${daysDiff === 1 ? '' : 's'} (${candidate.earnings_date})`;

        const reactionColor = rs.reaction_day_ret_pct >= 0 ? '#4ade80' : '#f87171';
        const gapColor = rs.reaction_day_gap_pct >= 0 ? '#4ade80' : '#f87171';

        container.innerHTML = `
            <div class="card" style="padding: 1rem; background: #09090b; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;">
                <!-- Inspector Header -->
                <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 0.65rem; margin-bottom: 0.75rem;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <span style="font-size: 1.15rem; font-weight: 800; font-family: var(--font-mono); color: #f8fafc;">${_esc(candidate.symbol)}</span>
                            <span class="signal-badge" style="background: ${arch.bg}; color: ${arch.color}; border: 1px solid ${arch.border}; font-size: 0.70rem; padding: 0.15rem 0.45rem;">
                                ${arch.icon} ${_esc(arch.label)}
                            </span>
                        </div>
                        <div style="font-size: 0.68rem; color: #94a3b8; font-family: var(--font-mono); margin-top: 0.2rem;">
                            ${timingLabel}
                        </div>
                    </div>

                    <div style="text-align: right;">
                        <div style="font-size: 0.62rem; color: #94a3b8; text-transform: uppercase; font-weight: 700;">Conviction Score</div>
                        <div style="font-size: 1.35rem; font-weight: 900; color: #38bdf8; font-family: var(--font-mono);">${score}<span style="font-size: 0.75rem; color: #64748b;">/100</span></div>
                    </div>
                </div>

                <!-- 4-Box Key Metrics Strip -->
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.45rem; margin-bottom: 0.85rem;">
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Current Price</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: #f8fafc; font-family: var(--font-mono);">${_fmtPrice(candidate.current_price)}</div>
                    </div>
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Trigger (RDH)</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: #38bdf8; font-family: var(--font-mono);">${_fmtPrice(tl.breakout_trigger)}</div>
                    </div>
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Reaction Return</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: ${reactionColor}; font-family: var(--font-mono);">${_fmtPct(rs.reaction_day_ret_pct)}</div>
                    </div>
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Volume Ratio</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: #4ade80; font-family: var(--font-mono);">${tech.volume_ratio_20d != null ? tech.volume_ratio_20d.toFixed(2) + 'x' : '—'}</div>
                    </div>
                </div>

                <!-- Section 1: Result Technical Reference Levels -->
                <div style="margin-bottom: 0.85rem; background: #06060a; border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.6rem 0.75rem;">
                    <div style="font-size: 0.66rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 0.45rem;">
                        📊 Result Technical Reference Levels
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; font-size: 0.72rem; font-family: var(--font-mono);">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">Result-Day High (RDH):</span>
                            <span style="color: #f8fafc; font-weight: 600;">${_fmtPrice(rs.result_day_high)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">Result-Day Low (RDL):</span>
                            <span style="color: #f8fafc; font-weight: 600;">${_fmtPrice(rs.result_day_low)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">Pre-Result Close:</span>
                            <span style="color: #cbd5e1; font-weight: 600;">${_fmtPrice(rs.pre_close)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">Reaction Gap %:</span>
                            <span style="color: ${gapColor}; font-weight: 600;">${_fmtPct(rs.reaction_day_gap_pct)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">20D Resistance:</span>
                            <span style="color: #cbd5e1;">${_fmtPrice(tech.resistance_20d)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">52-Week High:</span>
                            <span style="color: #cbd5e1;">${_fmtPrice(tech.high_52w)}</span>
                        </div>
                    </div>
                </div>

                <!-- Section 2: Trade Execution Blueprint -->
                <div style="margin-bottom: 0.85rem; background: #06060a; border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.6rem 0.75rem;">
                    <div style="font-size: 0.66rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 0.45rem;">
                        🎯 Trade Execution Blueprint
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.4rem; font-size: 0.72rem; font-family: var(--font-mono);">
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0; border-bottom: 1px dashed rgba(255,255,255,0.06);">
                            <span style="color: #64748b;">Suggested Entry:</span>
                            <span style="color: #38bdf8; font-weight: 700;">${_fmtPrice(tl.suggested_entry)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0; border-bottom: 1px dashed rgba(255,255,255,0.06);">
                            <span style="color: #64748b;">Stop Loss:</span>
                            <span style="color: #f87171; font-weight: 700;">${_fmtPrice(tl.stop_loss)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">Target 1 (+1.5 ATR):</span>
                            <span style="color: #4ade80; font-weight: 700;">${_fmtPrice(tl.target_1)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">Target 2 (+3.0 ATR):</span>
                            <span style="color: #4ade80; font-weight: 700;">${_fmtPrice(tl.target_2)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">Risk/Reward:</span>
                            <span style="color: #facc15; font-weight: 700;">1 : ${tl.risk_reward_ratio != null ? tl.risk_reward_ratio.toFixed(2) : '—'}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">14D ATR:</span>
                            <span style="color: #cbd5e1;">${_fmtPrice(tech.atr_14d)}</span>
                        </div>
                    </div>
                </div>

                <!-- Section 3: Setup Rationale & Catalyst Thesis -->
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.6rem 0.75rem; margin-bottom: 0.85rem;">
                    <div style="font-size: 0.66rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 0.35rem;">
                        💡 Setup Rationale & Execution Notes
                    </div>
                    <div style="font-size: 0.70rem; color: #cbd5e1; line-height: 1.45;">
                        ${_esc(arch.desc)}.
                        ${candidate.surprise_pct != null ? ` Reported earnings surprise of <strong>${_fmtPct(candidate.surprise_pct)}</strong>.` : ''}
                        ${tech.squeeze_on ? ' Volatility Squeeze is currently active (Bollinger inside Keltner Channels).' : ''}
                    </div>
                </div>

                <!-- Action Footer Buttons -->
                <div style="display: flex; gap: 0.45rem;">
                    <button
                        type="button"
                        class="btn btn-primary btn-sm"
                        onclick="if(window.app && app.openStockDetail) { app.openStockDetail('NSE', '${_esc(candidate.ticker)}'); } else { window.open('/stock/' + encodeURIComponent('${_esc(candidate.ticker)}'), '_blank'); }"
                        style="flex: 1; padding: 0.35rem; font-size: 0.72rem; font-weight: 700;"
                    >
                        📈 Open Stock Terminal
                    </button>
                    <button
                        type="button"
                        class="btn btn-secondary btn-sm"
                        onclick="if(window.app && app.toggleWatchlist) { app.toggleWatchlist('${_esc(candidate.ticker)}'); } else { alert('Watchlist updated for ${_esc(candidate.symbol)}'); }"
                        style="padding: 0.35rem 0.75rem; font-size: 0.72rem;"
                        title="Toggle Watchlist"
                    >
                        ⭐ Watch
                    </button>
                </div>
            </div>
        `;
    };

})();
