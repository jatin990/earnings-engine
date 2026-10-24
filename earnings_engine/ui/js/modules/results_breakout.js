// =========================================================================
// results_breakout.js — Results Breakout Radar Frontend Module
// Nexus Intelligence Platform · Quantitative Equity Scanner
// Dedicated radar for declared/upcoming earnings (-3D to +7D default window)
// Strict Point-in-Time (PIT) · Zero Fabricated Data · High-Resolution 2K
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
    app._resultsSort = { field: 'score', asc: false };
    app._resultsTimingFilter = 'ALL'; // 'ALL' | 'DECLARED' | 'UPCOMING'

    // Helper: Escape HTML to prevent injection
    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
        );
    }

    // Helper: Format currency in INR with nullish and NaN safety
    function _fmtPrice(num) {
        if (num === null || num === undefined || isNaN(Number(num))) return '—';
        return '₹' + Number(num).toLocaleString('en-IN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    // Helper: Format percentage with nullish and NaN safety
    function _fmtPct(num, includeSign = true) {
        if (num === null || num === undefined || isNaN(Number(num))) return '—';
        const val = Number(num);
        const prefix = (val > 0 && includeSign) ? '+' : '';
        return prefix + val.toFixed(2) + '%';
    }

    // Helper: Format ratio / multiple (e.g. volume)
    function _fmtRatio(num, suffix = 'x') {
        if (num === null || num === undefined || isNaN(Number(num))) return '—';
        return Number(num).toFixed(2) + suffix;
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

            // Update KPI summary strip with dual fallback keys
            const summary = data.summary || {};
            const elTotal = document.getElementById('resultsStatTotal');
            const elDeclared = document.getElementById('resultsStatDeclared');
            const elUpcoming = document.getElementById('resultsStatUpcoming');
            const elHot = document.getElementById('resultsStatHot');
            const elTop = document.getElementById('resultsStatTopScore');

            const totalCount = summary.total_candidates ?? data.total_candidates ?? app._resultsRadarData.length;
            const declaredCount = summary.declared_results ?? summary.declared_count ?? '—';
            const upcomingCount = summary.upcoming_results ?? summary.upcoming_count ?? '—';
            const hotCount = summary.hot_setups ?? summary.breaking_out_count ?? '—';
            const topScore = summary.top_conviction_score ?? summary.top_score;

            if (elTotal) elTotal.textContent = totalCount;
            if (elDeclared) elDeclared.textContent = declaredCount;
            if (elUpcoming) elUpcoming.textContent = upcomingCount;
            if (elHot) elHot.textContent = hotCount;
            if (elTop) elTop.textContent = (topScore !== null && topScore !== undefined && !isNaN(topScore)) ? Math.round(Number(topScore)) : '—';

            // Filter, sort & render table
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
    // Timing Quick-Filter Pill Handlers ('ALL' | 'DECLARED' | 'UPCOMING')
    // -------------------------------------------------------------------------
    app.setResultsTimingFilter = function (filter, btnElement) {
        app._resultsTimingFilter = filter;
        document.querySelectorAll('.results-timing-pill, .bk-timing-pill').forEach(btn => {
            btn.classList.remove('active');
            btn.style.background = 'transparent';
        });
        if (btnElement) {
            btnElement.classList.add('active');
            btnElement.style.background = '#27272a';
        }
        app.filterResultsRadar();
    };

    // -------------------------------------------------------------------------
    // Client-side Multi-Column Sorting
    // -------------------------------------------------------------------------
    app.sortResultsRadar = function (field) {
        if (app._resultsSort.field === field) {
            app._resultsSort.asc = !app._resultsSort.asc;
        } else {
            app._resultsSort.field = field;
            // Ascending for string/ticker, descending for numeric/score/volume
            app._resultsSort.asc = (field === 'ticker' || field === 'timing');
        }
        app._updateSortIndicators();
        app.filterResultsRadar();
    };

    function _updateSortIndicators() {
        const headers = document.querySelectorAll('#resultsBreakoutTable th[data-sort]');
        headers.forEach(th => {
            const field = th.getAttribute('data-sort');
            const indicator = th.querySelector('.sort-indicator');
            if (!indicator) return;
            if (field === app._resultsSort.field) {
                indicator.textContent = app._resultsSort.asc ? '▲' : '▼';
                indicator.style.color = '#38bdf8';
            } else {
                indicator.textContent = '⇅';
                indicator.style.color = '#52525b';
            }
        });
    }

    // -------------------------------------------------------------------------
    // Client-side Filtering & Sorting Aggregator
    // -------------------------------------------------------------------------
    app.filterResultsRadar = function () {
        const searchInput = document.getElementById('resultsSearchInput');
        const archSelect = document.getElementById('resultsArchetypeSelect');
        const query = (searchInput?.value || '').trim().toUpperCase();
        const arch = archSelect?.value || 'ALL';
        const timing = app._resultsTimingFilter || 'ALL';

        let filtered = (app._resultsRadarData || []).slice();

        // Archetype filter
        if (arch !== 'ALL') {
            filtered = filtered.filter(item => item.archetype === arch);
        }

        // Timing filter
        if (timing === 'DECLARED') {
            filtered = filtered.filter(item => Boolean(item.is_declared || (item.days_since_result != null && item.days_since_result <= 0)));
        } else if (timing === 'UPCOMING') {
            filtered = filtered.filter(item => !item.is_declared && (item.days_since_result != null && item.days_since_result > 0));
        }

        // Search text filter
        if (query) {
            filtered = filtered.filter(item => {
                const sym = (item.symbol || (item.ticker ? item.ticker.split('.')[0] : '')).toUpperCase();
                const name = (item.company_name || '').toUpperCase();
                return sym.includes(query) || name.includes(query);
            });
        }

        // Client-side Sort
        const { field, asc } = app._resultsSort;
        filtered.sort((a, b) => {
            let valA, valB;
            switch (field) {
                case 'ticker':
                    valA = (a.symbol || a.ticker || '').toUpperCase();
                    valB = (b.symbol || b.ticker || '').toUpperCase();
                    return asc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                case 'timing':
                    valA = a.days_since_result ?? a.days_relative ?? 0;
                    valB = b.days_since_result ?? b.days_relative ?? 0;
                    break;
                case 'archetype':
                    valA = a.archetype || '';
                    valB = b.archetype || '';
                    return asc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                case 'price':
                    valA = a.current_price ?? 0;
                    valB = b.current_price ?? 0;
                    break;
                case 'trigger':
                    valA = a.breakout_trigger ?? a.trade_levels?.breakout_trigger ?? 0;
                    valB = b.breakout_trigger ?? b.trade_levels?.breakout_trigger ?? 0;
                    break;
                case 'dist':
                    valA = a.dist_to_trigger_pct ?? a.pct_from_trigger ?? a.trade_levels?.dist_to_trigger_pct ?? -999;
                    valB = b.dist_to_trigger_pct ?? b.pct_from_trigger ?? b.trade_levels?.dist_to_trigger_pct ?? -999;
                    break;
                case 'volume':
                    valA = a.technicals?.volume_ratio ?? a.technicals?.volume_ratio_20d ?? 0;
                    valB = b.technicals?.volume_ratio ?? b.technicals?.volume_ratio_20d ?? 0;
                    break;
                case 'score':
                default:
                    valA = a.composite_score ?? 0;
                    valB = b.composite_score ?? 0;
                    break;
            }
            if (valA < valB) return asc ? -1 : 1;
            if (valA > valB) return asc ? 1 : -1;
            return 0;
        });

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
            const ticker = item.ticker || '';
            const isSelected = ticker === app._selectedResultsTicker;
            const rowStyle = isSelected
                ? 'background: rgba(56, 189, 248, 0.10); border-left: 3px solid #38bdf8;'
                : 'border-left: 3px solid transparent;';

            const symbol = item.symbol || (ticker ? ticker.split('.')[0] : '—');
            const companyName = item.company_name || '';
            const arch = _archetypeMeta(item.archetype);

            // Safe days calculation
            const rawDays = item.days_since_result ?? item.days_relative;
            const daysDiff = (rawDays !== null && rawDays !== undefined && !isNaN(Number(rawDays))) ? Number(rawDays) : 0;
            const isDeclared = Boolean(item.is_declared || daysDiff <= 0);

            // Timing badge
            let timingBadge = '';
            if (isDeclared) {
                const absDays = Math.abs(daysDiff);
                timingBadge = `<span class="signal-badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-size: 0.64rem; padding: 0.1rem 0.35rem;" title="Declared ${item.earnings_date || 'recently'}">🟢 -${absDays}D</span>`;
            } else {
                timingBadge = `<span class="signal-badge" style="background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); font-size: 0.64rem; padding: 0.1rem 0.35rem;" title="Upcoming ${item.earnings_date || 'soon'}">⏳ +${daysDiff}D</span>`;
            }

            // Trigger level with fallbacks
            const trigger = item.breakout_trigger ?? item.trade_levels?.breakout_trigger;

            // Distance to trigger styling
            const dist = item.dist_to_trigger_pct ?? item.pct_from_trigger ?? item.trade_levels?.dist_to_trigger_pct;
            let distColor = '#94a3b8';
            if (dist !== null && dist !== undefined && !isNaN(Number(dist))) {
                const distNum = Number(dist);
                if (distNum >= 0) distColor = '#4ade80';
                else if (distNum >= -1.5) distColor = '#38bdf8';
                else distColor = '#fbbf24';
            }

            // Volume surge ratio
            const volSurge = item.technicals?.volume_ratio ?? item.technicals?.volume_ratio_20d;
            let volColor = '#94a3b8';
            if (volSurge !== null && volSurge !== undefined && !isNaN(Number(volSurge))) {
                const vNum = Number(volSurge);
                if (vNum >= 1.5) volColor = '#4ade80';
                else if (vNum >= 1.15) volColor = '#38bdf8';
            }

            // Score pill
            const score = (item.composite_score !== null && item.composite_score !== undefined && !isNaN(Number(item.composite_score)))
                ? Math.round(Number(item.composite_score))
                : 0;
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
                    onclick="app.inspectResultsCandidate('${_esc(ticker)}')"
                    style="${rowStyle} cursor: pointer; transition: background 0.15s; border-bottom: 1px solid rgba(255,255,255,0.05);"
                    onmouseover="if(this.style.borderLeftColor !== 'rgb(56, 189, 248)') this.style.background='rgba(255,255,255,0.03)';"
                    onmouseout="if(this.style.borderLeftColor !== 'rgb(56, 189, 248)') this.style.background='transparent';"
                >
                    <td style="padding: 0.45rem 0.6rem;">
                        <div style="font-family: var(--font-mono); font-weight: 700; color: #f8fafc; font-size: 0.76rem;">${_esc(symbol)}</div>
                        ${companyName ? `<div style="font-size: 0.62rem; color: #71717a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 110px;" title="${_esc(companyName)}">${_esc(companyName)}</div>` : ''}
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
                        ${_fmtPrice(trigger)}
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono); font-weight: 700; color: ${distColor};">
                        ${_fmtPct(dist)}
                    </td>
                    <td style="padding: 0.45rem 0.5rem; font-family: var(--font-mono);">
                        <div style="display: flex; flex-direction: column; gap: 0.15rem;">
                            <span style="font-weight: 600; color: ${volColor};">${_fmtRatio(volSurge)}</span>
                            ${item.technicals?.vol_badge_label ? `
                                <span class="signal-badge" style="background: ${item.technicals.vol_badge_bg || 'rgba(148, 163, 184, 0.12)'}; color: ${item.technicals.vol_badge_color || '#94a3b8'}; border: 1px solid ${item.technicals.vol_badge_border || 'rgba(148, 163, 184, 0.25)'}; font-size: 0.58rem; padding: 0.04rem 0.25rem; white-space: nowrap;" title="${_esc(item.technicals.vol_tooltip || '')}">
                                    ${_esc(item.technicals.vol_badge_label)}
                                </span>
                            ` : ''}
                        </div>
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
                            onclick="event.stopPropagation(); app.inspectResultsCandidate('${_esc(ticker)}')"
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
    // Inspect Candidate Setup Anatomy (Right Pane)
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
                    const symCell = tr.querySelector('td div');
                    const candidateSym = candidate.symbol || (candidate.ticker ? candidate.ticker.split('.')[0] : '');
                    if (symCell && symCell.textContent.trim() === candidateSym) {
                        tr.style.background = 'rgba(56, 189, 248, 0.10)';
                        tr.style.borderLeft = '3px solid #38bdf8';
                    } else {
                        tr.style.background = 'transparent';
                        tr.style.borderLeft = '3px solid transparent';
                    }
                });
            }
        }

        const symbol = candidate.symbol || (candidate.ticker ? candidate.ticker.split('.')[0] : '—');
        const companyName = candidate.company_name || '';
        const industry = candidate.industry || '';
        const arch = _archetypeMeta(candidate.archetype);

        const tl = candidate.trade_levels || {};
        const rs = candidate.result_structure || {};
        const tech = candidate.technicals || {};
        const fund = candidate.fundamentals || {};
        const score = (candidate.composite_score !== null && candidate.composite_score !== undefined && !isNaN(Number(candidate.composite_score)))
            ? Math.round(Number(candidate.composite_score))
            : 0;

        // Days timing
        const rawDays = candidate.days_since_result ?? candidate.days_relative;
        const daysDiff = (rawDays !== null && rawDays !== undefined && !isNaN(Number(rawDays))) ? Number(rawDays) : 0;
        const isDeclared = Boolean(candidate.is_declared || daysDiff <= 0);
        const timingLabel = isDeclared
            ? `🟢 Declared ${Math.abs(daysDiff)} Day${Math.abs(daysDiff) === 1 ? '' : 's'} Ago (${candidate.earnings_date || 'PIT'})`
            : `⏳ Upcoming in ${daysDiff} Day${daysDiff === 1 ? '' : 's'} (${candidate.earnings_date || 'PIT'})`;

        // Key Levels
        const cmp = candidate.current_price;
        const trigger = candidate.breakout_trigger ?? tl.breakout_trigger;
        const suggestedEntry = tl.suggested_entry ?? tl.ideal_entry ?? cmp;
        const target1 = tl.target_1 ?? tl.target_price;
        const target2 = tl.target_2;
        const stopLoss = tl.stop_loss;
        const rrr = tl.risk_reward_ratio;

        // Returns & Gaps
        const reactionRet = rs.reaction_day_ret_pct ?? rs.reaction_day_return_pct;
        const reactionGap = rs.reaction_day_gap_pct;
        const reactionColor = (reactionRet != null && reactionRet >= 0) ? '#4ade80' : (reactionRet != null ? '#f87171' : '#94a3b8');
        const gapColor = (reactionGap != null && reactionGap >= 0) ? '#4ade80' : (reactionGap != null ? '#f87171' : '#94a3b8');

        // Volume multiple
        const volSurge = tech.volume_ratio ?? tech.volume_ratio_20d;

        // Breakout Proximity Gauge Calculation
        // Gauge span: 20D Low / Stop Loss to Target 1
        const lowBound = Math.min(Number(stopLoss || cmp * 0.95), Number(cmp * 0.95));
        const highBound = Math.max(Number(target1 || cmp * 1.10), Number(cmp * 1.08));
        const span = Math.max(0.01, highBound - lowBound);
        const cmpPct = Math.min(100, Math.max(0, ((Number(cmp) - lowBound) / span) * 100));
        const trigPct = trigger ? Math.min(100, Math.max(0, ((Number(trigger) - lowBound) / span) * 100)) : 50;

        // Squeeze status
        const isSqueeze = Boolean(tech.squeeze_on);

        container.innerHTML = `
            <div class="card" style="padding: 1rem; background: #09090b; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;">
                <!-- Inspector Header -->
                <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 0.65rem; margin-bottom: 0.75rem;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                            <span style="font-size: 1.2rem; font-weight: 800; font-family: var(--font-mono); color: #f8fafc;">${_esc(symbol)}</span>
                            <span class="signal-badge" style="background: ${arch.bg}; color: ${arch.color}; border: 1px solid ${arch.border}; font-size: 0.68rem; padding: 0.12rem 0.45rem;">
                                ${arch.icon} ${_esc(arch.label)}
                            </span>
                            ${isSqueeze ? '<span class="signal-badge" style="background: rgba(234, 179, 8, 0.15); color: #eab308; border: 1px solid rgba(234, 179, 8, 0.3); font-size: 0.64rem; padding: 0.1rem 0.35rem;">⚡ SQUEEZE</span>' : ''}
                        </div>
                        <div style="font-size: 0.68rem; color: #94a3b8; font-family: var(--font-mono); margin-top: 0.2rem;">
                            ${companyName ? `${_esc(companyName)} · ` : ''}${industry ? `${_esc(industry)} · ` : ''}${timingLabel}
                        </div>
                    </div>

                    <div style="text-align: right;">
                        <div style="font-size: 0.62rem; color: #94a3b8; text-transform: uppercase; font-weight: 700;">Conviction Score</div>
                        <div style="font-size: 1.35rem; font-weight: 900; color: #38bdf8; font-family: var(--font-mono);">${score}<span style="font-size: 0.75rem; color: #64748b;">/100</span></div>
                    </div>
                </div>

                <!-- Visual Breakout Proximity Gauge -->
                <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.55rem 0.75rem; margin-bottom: 0.85rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.64rem; font-family: var(--font-mono); margin-bottom: 0.3rem;">
                        <span style="color: #f87171;">SL: ${_fmtPrice(stopLoss)}</span>
                        <span style="color: #38bdf8; font-weight: 700;">CMP: ${_fmtPrice(cmp)}</span>
                        <span style="color: #fbbf24;">Trigger: ${_fmtPrice(trigger)}</span>
                        <span style="color: #4ade80;">T1: ${_fmtPrice(target1)}</span>
                    </div>
                    <div style="position: relative; width: 100%; height: 8px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: visible;">
                        <!-- Trigger line marker -->
                        <div style="position: absolute; left: ${trigPct}%; top: -3px; width: 2px; height: 14px; background: #fbbf24; z-index: 2;" title="Trigger: ${_fmtPrice(trigger)}"></div>
                        <!-- Current Price progress bar -->
                        <div style="height: 100%; width: ${cmpPct}%; background: linear-gradient(90deg, #38bdf8, #4ade80); border-radius: 4px;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.60rem; color: #64748b; margin-top: 0.3rem; font-family: var(--font-mono);">
                        <span>Floor (${_fmtPrice(lowBound)})</span>
                        <span>Proximity: ${_fmtPct(candidate.dist_to_trigger_pct ?? candidate.pct_from_trigger)} to Trigger</span>
                        <span>Ceiling (${_fmtPrice(highBound)})</span>
                    </div>
                </div>

                <!-- 4-Box Key Metrics Strip -->
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.45rem; margin-bottom: 0.85rem;">
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Current Price</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: #f8fafc; font-family: var(--font-mono);">${_fmtPrice(cmp)}</div>
                    </div>
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Trigger (RDH)</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: #38bdf8; font-family: var(--font-mono);">${_fmtPrice(trigger)}</div>
                    </div>
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Reaction Return</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: ${reactionColor}; font-family: var(--font-mono);">${_fmtPct(reactionRet)}</div>
                    </div>
                    <div style="background: #06060a; border: 1px solid rgba(255,255,255,0.06); padding: 0.4rem; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.58rem; color: #94a3b8; text-transform: uppercase;">Volume Surge</div>
                        <div style="font-size: 0.90rem; font-weight: 700; color: #4ade80; font-family: var(--font-mono);">${_fmtRatio(volSurge)}</div>
                    </div>
                </div>

                <!-- Section 1: Result Technical Reference Levels -->
                <div style="margin-bottom: 0.85rem; background: #06060a; border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.6rem 0.75rem;">
                    <div style="font-size: 0.66rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 0.45rem;">
                        📊 Forensic Result Structure
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
                            <span style="color: #cbd5e1; font-weight: 600;">${_fmtPrice(rs.pre_close ?? rs.pre_result_close)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">Reaction Gap %:</span>
                            <span style="color: ${gapColor}; font-weight: 600;">${_fmtPct(reactionGap)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #64748b;">20D Resistance:</span>
                            <span style="color: #cbd5e1;">${_fmtPrice(tech.resistance_20d ?? tech.high_20d)}</span>
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
                            <span style="color: #38bdf8; font-weight: 700;">${_fmtPrice(suggestedEntry)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0; border-bottom: 1px dashed rgba(255,255,255,0.06);">
                            <span style="color: #64748b;">Stop Loss:</span>
                            <span style="color: #f87171; font-weight: 700;">${_fmtPrice(stopLoss)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">Target 1 (+1.5 ATR):</span>
                            <span style="color: #4ade80; font-weight: 700;">${_fmtPrice(target1)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">Target 2 (+3.0 ATR):</span>
                            <span style="color: #4ade80; font-weight: 700;">${_fmtPrice(target2)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">Risk/Reward:</span>
                            <span style="color: #facc15; font-weight: 700;">1 : ${_fmtRatio(rrr, '')}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">14D ATR:</span>
                            <span style="color: #cbd5e1;">${_fmtPrice(tech.atr_14d ?? tech.atr_val)}</span>
                        </div>
                    </div>
                </div>

                <!-- Section 3: Catalyst Thesis & Telemetry -->
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.6rem 0.75rem; margin-bottom: 0.85rem;">
                    <div style="font-size: 0.66rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 0.35rem;">
                        💡 Setup Rationale &amp; Catalyst Thesis
                    </div>
                    <div style="font-size: 0.70rem; color: #cbd5e1; line-height: 1.45;">
                        ${_esc(arch.desc)}.
                        ${fund.surprise_pct != null ? ` Reported earnings surprise of <strong>${_fmtPct(fund.surprise_pct)}</strong>.` : ''}
                        ${tech.momentum_3d_pct != null ? ` 3D Momentum: <strong>${_fmtPct(tech.momentum_3d_pct)}</strong>.` : ''}
                        ${isSqueeze ? ' Volatility Squeeze is currently active (Bollinger Band inside Keltner Channel).' : ''}
                    </div>
                </div>

                <!-- Section 4: Volume Polarity & F&O Positioning -->
                <div style="margin-bottom: 0.85rem; background: #06060a; border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.6rem 0.75rem;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.45rem;">
                        <div style="font-size: 0.66rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px;">
                            ⚡ Volume Polarity &amp; Institutional Positioning
                        </div>
                        ${candidate.is_fno ? '<span class="signal-badge" style="background: rgba(147, 51, 234, 0.15); color: #c084fc; border: 1px solid rgba(147, 51, 234, 0.3); font-size: 0.58rem; padding: 0.04rem 0.3rem;">NSE F&amp;O</span>' : '<span style="font-size: 0.58rem; color: #64748b;">Cash Equity</span>'}
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.45rem; font-size: 0.72rem; font-family: var(--font-mono);">
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0; border-bottom: 1px dashed rgba(255,255,255,0.06);">
                            <span style="color: #64748b;">Polarity:</span>
                            <span style="font-weight: 700; color: ${tech.vol_badge_color || '#94a3b8'};">${_esc(candidate.volume_polarity || 'NEUTRAL')}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0; border-bottom: 1px dashed rgba(255,255,255,0.06);">
                            <span style="color: #64748b;">Volume Character:</span>
                            <span style="font-weight: 600; color: #f8fafc;">${_esc(candidate.volume_character || '—')}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">F&amp;O Open Interest:</span>
                            <span style="font-weight: 600; color: ${candidate.oi_change_pct > 0 ? '#34d399' : (candidate.oi_change_pct < 0 ? '#f87171' : '#94a3b8')};">
                                ${candidate.oi_change_pct != null ? `${candidate.oi_change_pct > 0 ? '+' : ''}${candidate.oi_change_pct.toFixed(2)}%` : '—'}
                            </span>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.2rem 0;">
                            <span style="color: #64748b;">Derivatives Buildup:</span>
                            <span style="font-weight: 700; color: ${candidate.oi_buildup ? '#38bdf8' : '#64748b'};">${_esc(candidate.oi_buildup || 'N/A (Cash)')}</span>
                        </div>
                    </div>
                    ${tech.vol_tooltip ? `
                        <div style="font-size: 0.64rem; color: #94a3b8; font-family: var(--font-sans); margin-top: 0.4rem; padding-top: 0.35rem; border-top: 1px solid rgba(255,255,255,0.04); line-height: 1.35;">
                            ℹ️ ${_esc(tech.vol_tooltip)}
                        </div>
                    ` : ''}
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
                        onclick="if(window.app && app.toggleWatchlist) { app.toggleWatchlist('${_esc(candidate.ticker)}'); } else { alert('Watchlist updated for ${_esc(symbol)}'); }"
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
