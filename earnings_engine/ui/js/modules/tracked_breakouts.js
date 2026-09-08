// =========================================================================
// tracked_breakouts — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    // =========================================================================
    // 📜 TRACKED BREAKOUTS HISTORY CONTROLLER
    // =========================================================================
    app._trackedBreakoutsData = [];
    app._trackedBreakoutPresetDays = 7;
    app._activeBreakoutSubtab = 'scanner';

    app.switchBreakoutSubtab = function(subtab) {
        subtab = subtab || 'scanner';
        app._activeBreakoutSubtab = subtab;
        try {
            localStorage.setItem('subtab_breakout', subtab);
            if (!app._subtabState) app._subtabState = {};
            app._subtabState['breakout'] = subtab;
        } catch (e) {}

        const scannerView = document.getElementById('breakoutLiveScannerContainer');
        const backtestView = document.getElementById('breakoutBacktestContainer');
        const trackedView = document.getElementById('breakoutTrackedContainer');

        const btnScanner = document.getElementById('btnBreakoutSubtabScanner');
        const btnBacktest = document.getElementById('btnBreakoutSubtabBacktest');
        const btnTracked = document.getElementById('btnBreakoutSubtabTracked');
        const contextLabel = document.getElementById('bkSubtabContextLabel');

        const sideSubScanner = document.getElementById('sidebarSubBreakoutScanner');
        const sideSubBacktest = document.getElementById('sidebarSubBreakoutBacktest');
        const sideSubTracked = document.getElementById('sidebarSubBreakoutTracked');

        if (scannerView) scannerView.style.display = 'none';
        if (backtestView) backtestView.style.display = 'none';
        if (trackedView) trackedView.style.display = 'none';

        if (btnScanner) btnScanner.classList.remove('bk-subtab-active');
        if (btnBacktest) btnBacktest.classList.remove('bk-subtab-active');
        if (btnTracked) btnTracked.classList.remove('bk-subtab-active');

        if (sideSubScanner) sideSubScanner.classList.remove('active');
        if (sideSubBacktest) sideSubBacktest.classList.remove('active');
        if (sideSubTracked) sideSubTracked.classList.remove('active');

        if (subtab === 'backtest') {
            if (backtestView) backtestView.style.display = 'block';
            if (btnBacktest) btnBacktest.classList.add('bk-subtab-active');
            if (sideSubBacktest) sideSubBacktest.classList.add('active');
            if (contextLabel) contextLabel.textContent = '📅 Historical Point-in-Time Date Backtest Simulator';
            if (typeof app.loadBreakoutBacktest === 'function') {
                app.loadBreakoutBacktest();
            }
        } else if (subtab === 'tracked') {
            if (trackedView) trackedView.style.display = 'block';
            if (btnTracked) btnTracked.classList.add('bk-subtab-active');
            if (sideSubTracked) sideSubTracked.classList.add('active');
            if (contextLabel) contextLabel.textContent = '📜 Permanent Tracked Breakout History (14D Horizon & Live Active Setups)';
            app.loadTrackedBreakouts();
        } else {
            // Default: 'scanner' (Active Setup Pool)
            if (scannerView) scannerView.style.display = 'block';
            if (btnScanner) btnScanner.classList.add('bk-subtab-active');
            if (sideSubScanner) sideSubScanner.classList.add('active');
            if (contextLabel) contextLabel.textContent = '⚡ Active Breakout Radar & Coiling Pool Engine';
            app._breakoutAsofDate = null;
            app.loadBreakoutRadar();
        }
    };

    app.setTrackedBreakoutPreset = function(days) {
        app._trackedBreakoutPresetDays = days;
        const startInput = document.getElementById('breakoutTrackedStartDate');
        const endInput = document.getElementById('breakoutTrackedEndDate');
        if (startInput) startInput.value = '';
        if (endInput) endInput.value = '';

        document.querySelectorAll('.bk-tracked-preset').forEach(btn => {
            const btnDays = btn.getAttribute('data-days');
            if (String(btnDays) === String(days)) {
                btn.classList.add('bk-preset-active');
            } else {
                btn.classList.remove('bk-preset-active');
            }
        });

        app.loadTrackedBreakouts();
    };

    app.applyTrackedBreakoutDateRange = function() {
        const startInput = document.getElementById('breakoutTrackedStartDate');
        const endInput = document.getElementById('breakoutTrackedEndDate');
        if (!startInput?.value && !endInput?.value) {
            alert('Please pick a start or end date.');
            return;
        }
        // Deselect preset buttons
        document.querySelectorAll('.bk-tracked-preset').forEach(btn => btn.classList.remove('bk-preset-active'));
        app._trackedBreakoutPresetDays = null;
        app.loadTrackedBreakouts();
    };

    app.clearTrackedBreakoutDateRange = function() {
        const startInput = document.getElementById('breakoutTrackedStartDate');
        const endInput = document.getElementById('breakoutTrackedEndDate');
        if (startInput) startInput.value = '';
        if (endInput) endInput.value = '';
        app.setTrackedBreakoutPreset(7);
    };

    app.loadTrackedBreakouts = async function(isLive = false) {
        const tbody = document.getElementById('breakoutTrackedTableBody');
        const liveBtn = document.getElementById('btnTrackedLiveRefresh');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="13" style="text-align:center;padding:2.5rem;color:#64748b;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading tracked breakout history...</td></tr>`;
        }
        if (isLive && liveBtn) {
            liveBtn.disabled = true;
            liveBtn.innerHTML = '<span>⏳</span> Refreshing Quotes...';
        }

        const tier = document.getElementById('breakoutTrackedTierFilter')?.value || 'ALL';
        const outcome = document.getElementById('breakoutTrackedOutcomeFilter')?.value || 'ALL';
        const strategy = document.getElementById('breakoutTrackedStrategyFilter')?.value || 'ALL';
        const sortBy = document.getElementById('breakoutTrackedSortBy')?.value || 'signal_date';
        const startVal = document.getElementById('breakoutTrackedStartDate')?.value || '';
        const endVal = document.getElementById('breakoutTrackedEndDate')?.value || '';

        const params = new URLSearchParams();
        if (startVal) params.set('start_date', startVal);
        if (endVal) params.set('end_date', endVal);
        if (!startVal && !endVal && app._trackedBreakoutPresetDays && app._trackedBreakoutPresetDays !== 'all') {
            params.set('days', String(app._trackedBreakoutPresetDays));
        }
        if (tier && tier !== 'ALL') params.set('tier', tier);
        if (outcome && outcome !== 'ALL') params.set('outcome', outcome);
        if (strategy && strategy !== 'ALL') params.set('strategy', strategy);
        if (sortBy) params.set('sort_by', sortBy);
        if (isLive) params.set('live', 'true');
        params.set('limit', '200');

        try {
            const res = await fetch(API_BASE + '/api/v1/breakout/tracked?' + params.toString());
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();

            app._trackedBreakoutsData = data.items || [];
            const summary = data.summary || {};
            const timeframe = data.timeframe || {};

            // Update badge count
            const badgeCount = document.getElementById('bkTrackedCountBadge');
            if (badgeCount) badgeCount.textContent = String(data.total_count || 0);

            // Update Timeframe label
            const tfLabel = document.getElementById('breakoutTrackedTimeframeLabel');
            if (tfLabel) {
                if (timeframe.start_date && timeframe.end_date) {
                    tfLabel.textContent = `Filtered range: ${timeframe.start_date} to ${timeframe.end_date} (${data.total_count || 0} setups)`;
                } else if (timeframe.preset_days) {
                    tfLabel.textContent = `Last ${timeframe.preset_days} Day(s) window (${data.total_count || 0} setups) • As of ${new Date().toLocaleTimeString()}`;
                } else {
                    tfLabel.textContent = `All-Time Tracked Breakout History (${data.total_count || 0} setups) • As of ${new Date().toLocaleTimeString()}`;
                }
            }

            // Update KPI Cards
            const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
            setEl('bkTrackedKpiTotal', summary.total_tracked != null ? summary.total_tracked : '—');
            setEl('bkTrackedKpiWinRate', summary.win_rate_pct != null ? `${summary.win_rate_pct}%` : '—');
            setEl('bkTrackedKpiAvgReturn', summary.avg_return_pct != null ? `${summary.avg_return_pct >= 0 ? '+' : ''}${summary.avg_return_pct}%` : '—');
            setEl('bkTrackedKpiMaxReturn', summary.max_return_pct != null ? `${summary.max_return_pct >= 0 ? '+' : ''}${summary.max_return_pct}%` : '—');
            setEl('bkTrackedKpiTopTicker', summary.max_return_ticker || '—');
            setEl('bkTrackedKpiActiveCount', `${summary.active_count || 0} active / ${summary.triggered_count || 0} fired`);

            app.renderTrackedBreakoutsTable(app._trackedBreakoutsData);
        } catch (e) {
            console.error('[BREAKOUT-TRACKED] Load error:', e);
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="13" style="text-align:center;padding:2rem;color:#f87171;">Failed to load tracked breakouts: ${e.message}</td></tr>`;
            }
        } finally {
            if (isLive && liveBtn) {
                liveBtn.disabled = false;
                liveBtn.innerHTML = '<span>⚡</span> Refresh Live Quotes';
            }
        }
    };

    // Strategy badge formatter
    function formatStrategyBadge(strat, archetype) {
        const s = (strat || archetype || '').toUpperCase().trim();
        if (s.includes('DELIVERY') || s.includes('ABSORPTION')) {
            return `<span style="font-size:0.60rem;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);padding:0.06rem 0.35rem;border-radius:3px;font-weight:700;">📦 Delivery Surge</span>`;
        }
        if (s.includes('FO_CALL') || s.includes('CALL_WALL') || s.includes('WALL')) {
            return `<span style="font-size:0.60rem;background:rgba(234,179,8,0.18);color:#fde047;border:1px solid rgba(234,179,8,0.35);padding:0.06rem 0.35rem;border-radius:3px;font-weight:700;">🧱 F&O Call Wall</span>`;
        }
        if (s.includes('VOLUME_PROFILE') || s.includes('VAH')) {
            return `<span style="font-size:0.60rem;background:rgba(168,85,247,0.18);color:#c084fc;border:1px solid rgba(168,85,247,0.35);padding:0.06rem 0.35rem;border-radius:3px;font-weight:700;">📊 Volume Profile</span>`;
        }
        if (s.includes('DONCHIAN') || s.includes('SQUEEZE') || s.includes('TTM')) {
            return `<span style="font-size:0.60rem;background:rgba(236,72,153,0.18);color:#f472b6;border:1px solid rgba(236,72,153,0.35);padding:0.06rem 0.35rem;border-radius:3px;font-weight:700;">🔄 Donchian Squeeze</span>`;
        }
        return `<span style="font-size:0.60rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:0.06rem 0.35rem;border-radius:3px;font-weight:700;">⚡ Classic Technical</span>`;
    }

    // Helper to group raw setups by ticker for multi-strategy confluence
    app.groupTrackedBreakoutsByTicker = function(items) {
        if (!items || items.length === 0) return [];
        const groupedMap = new Map();

        items.forEach(item => {
            const sym = (item.ticker || '').toUpperCase().trim();
            if (!sym) return;

            if (!groupedMap.has(sym)) {
                groupedMap.set(sym, {
                    ticker: item.ticker,
                    company_name: item.company_name,
                    industry: item.industry,
                    current_price: item.current_price,
                    current_date: item.current_date,
                    setups: [],
                    latest_signal_date: item.signal_date,
                    min_signal_price: item.signal_price,
                    max_signal_price: item.signal_price,
                    min_trigger: item.breakout_trigger,
                    max_trigger: item.breakout_trigger,
                    min_target: item.target_price,
                    max_target: item.target_price,
                    min_stop: item.stop_loss,
                    max_stop: item.stop_loss,
                    max_score: item.composite_score || 0,
                    max_gain_pct: item.max_gain_pct != null ? item.max_gain_pct : (item.peak_gain_pct != null ? item.peak_gain_pct : null),
                    latest_return_pct: item.realized_return_pct != null ? item.realized_return_pct : null,
                    highest_tier: (item.tier || 'WARM').toUpperCase(),
                    strategies: new Set(),
                    has_live_recent: false,
                    days_elapsed: item.days_elapsed != null ? item.days_elapsed : 0,
                    has_target_hit: false,
                    has_triggered: false,
                    has_stop_hit: false,
                    has_active: false,
                    best_outcome: item.outcome || 'ACTIVE',
                    best_outcome_label: item.outcome_label || null,
                    best_one_liner: item.what_happened_summary || item.explanation_one_liner || '',
                });
            }

            const g = groupedMap.get(sym);
            g.setups.push(item);

            if (item.company_name && (!g.company_name || g.company_name === g.ticker)) g.company_name = item.company_name;
            if (item.industry && item.industry !== '—') g.industry = item.industry;
            if (item.current_price != null) g.current_price = item.current_price;

            // Date tracking
            if (item.signal_date && (!g.latest_signal_date || item.signal_date > g.latest_signal_date)) {
                g.latest_signal_date = item.signal_date;
                g.latest_return_pct = item.realized_return_pct;
                g.days_elapsed = item.days_elapsed != null ? item.days_elapsed : 0;
            }

            // Price range aggregations
            if (item.signal_price != null) {
                if (g.min_signal_price == null || item.signal_price < g.min_signal_price) g.min_signal_price = item.signal_price;
                if (g.max_signal_price == null || item.signal_price > g.max_signal_price) g.max_signal_price = item.signal_price;
            }
            if (item.breakout_trigger != null) {
                if (g.min_trigger == null || item.breakout_trigger < g.min_trigger) g.min_trigger = item.breakout_trigger;
                if (g.max_trigger == null || item.breakout_trigger > g.max_trigger) g.max_trigger = item.breakout_trigger;
            }
            if (item.target_price != null) {
                if (g.min_target == null || item.target_price < g.min_target) g.min_target = item.target_price;
                if (g.max_target == null || item.target_price > g.max_target) g.max_target = item.target_price;
            }
            if (item.stop_loss != null) {
                if (g.min_stop == null || item.stop_loss < g.min_stop) g.min_stop = item.stop_loss;
                if (g.max_stop == null || item.stop_loss > g.max_stop) g.max_stop = item.stop_loss;
            }

            // Score & gain
            if ((item.composite_score || 0) > g.max_score) g.max_score = item.composite_score || 0;
            const itemGain = item.max_gain_pct != null ? item.max_gain_pct : item.peak_gain_pct;
            if (itemGain != null && (g.max_gain_pct == null || itemGain > g.max_gain_pct)) g.max_gain_pct = itemGain;

            // Tier
            if ((item.tier || '').toUpperCase() === 'HOT') g.highest_tier = 'HOT';

            // Active/Recent
            const dElapsed = item.days_elapsed != null ? item.days_elapsed : 0;
            if (item.is_live_recent || dElapsed < 14) g.has_live_recent = true;

            // Strategy collection
            const strat = item.strategy || (item.data && item.data.strategy) || item.setup_archetype || 'CLASSIC_TECHNICAL';
            g.strategies.add(strat);

            // Outcomes
            const out = (item.outcome || '').toUpperCase();
            if (out === 'TARGET_HIT') {
                g.has_target_hit = true;
                g.best_outcome = 'TARGET_HIT';
                g.best_outcome_label = item.outcome_label || 'Target Hit';
            } else if (out === 'TRIGGERED' || out === 'BREAKOUT_SUCCEEDED') {
                g.has_triggered = true;
                if (g.best_outcome !== 'TARGET_HIT') {
                    g.best_outcome = 'TRIGGERED';
                    g.best_outcome_label = item.outcome_label || 'Triggered';
                }
            } else if (out === 'STOP_HIT' || out === 'STOP_LOSS_HIT') {
                g.has_stop_hit = true;
            } else if (out === 'ACTIVE' || dElapsed < 14) {
                g.has_active = true;
            }
        });

        return Array.from(groupedMap.values());
    };

    app.renderTrackedBreakoutsTable = function(items) {
        const tbody = document.getElementById('breakoutTrackedTableBody');
        if (!tbody) return;

        if (!items || items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="13" style="padding:3rem;text-align:center;color:#64748b;font-size:0.85rem;">
                        📜 No breakout signals found in the selected timeframe or filter.<br>
                        <span style="font-size:0.75rem;color:#475569;margin-top:0.3rem;display:inline-block;">Try selecting "⚡ 7 Days" or "🌐 All Time" presets to view historical setups.</span>
                    </td>
                </tr>
            `;
            return;
        }

        // Group by ticker for unified multi-setup parent rows
        const grouped = app.groupTrackedBreakoutsByTicker(items);

        tbody.innerHTML = grouped.map(g => {
            const sym = g.ticker || '—';
            const cleanSym = sym.replace(/[^a-zA-Z0-9]/g, '_');
            const rawName = (g.company_name || sym).replace(/\.NS$/i, '');
            const name = rawName.length > 22 ? rawName.substring(0, 22) + '…' : rawName;
            const ind = (g.industry && g.industry !== '—') ? g.industry : 'Equities';
            const tier = g.highest_tier || 'WARM';
            const tierColor = tier === 'HOT' ? '#f87171' : '#fbbf24';
            const tierBg = tier === 'HOT' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)';

            const sigDate = g.latest_signal_date || '—';
            const daysElapsed = g.days_elapsed != null ? g.days_elapsed : 0;
            const isLiveRecent = g.has_live_recent || daysElapsed < 14;

            // Multi-setup count badge
            const setupCount = g.setups.length;
            const setupCountBadge = setupCount > 1
                ? `<span style="font-size:0.62rem;background:rgba(249,115,22,0.2);color:#fb923c;border:1px solid rgba(249,115,22,0.45);padding:0.08rem 0.4rem;border-radius:4px;font-weight:800;display:inline-flex;align-items:center;gap:0.2rem;">🔥 ${setupCount} Setups</span>`
                : `<span style="font-size:0.60rem;background:rgba(148,163,184,0.12);color:#94a3b8;border:1px solid rgba(148,163,184,0.25);padding:0.06rem 0.35rem;border-radius:3px;font-weight:600;">1 Setup</span>`;

            // Strategy badges cluster
            const stratBadges = Array.from(g.strategies).map(s => formatStrategyBadge(s)).join(' ');

            // Price calculations for parent row
            const sigP = (g.min_signal_price != null && g.max_signal_price != null)
                ? (g.min_signal_price === g.max_signal_price ? `₹${Number(g.min_signal_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : `₹${Number(g.min_signal_price).toFixed(0)} - ₹${Number(g.max_signal_price).toFixed(0)}`)
                : '—';
            const trigP = (g.min_trigger != null && g.max_trigger != null)
                ? (g.min_trigger === g.max_trigger ? `₹${Number(g.min_trigger).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : `₹${Number(g.min_trigger).toFixed(0)} - ₹${Number(g.max_trigger).toFixed(0)}`)
                : '—';
            const targetP = (g.min_target != null && g.max_target != null)
                ? (g.min_target === g.max_target ? `₹${Number(g.min_target).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : `₹${Number(g.min_target).toFixed(0)} - ₹${Number(g.max_target).toFixed(0)}`)
                : '—';
            const stopP = (g.min_stop != null && g.max_stop != null)
                ? (g.min_stop === g.max_stop ? `₹${Number(g.min_stop).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : `₹${Number(g.min_stop).toFixed(0)} - ₹${Number(g.max_stop).toFixed(0)}`)
                : '—';
            const curP = g.current_price != null ? `₹${Number(g.current_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';

            // Return styling
            const ret = g.latest_return_pct;
            const retColor = ret > 0 ? '#34d399' : (ret < 0 ? '#f87171' : '#94a3b8');
            const retBg = ret > 0 ? 'rgba(16,185,129,0.15)' : (ret < 0 ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)');
            const retBorder = ret > 0 ? 'rgba(16,185,129,0.3)' : (ret < 0 ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)');
            const retFormatted = ret != null ? `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%` : '—';

            // Max Gain
            const maxGain = g.max_gain_pct;
            const maxGainStr = maxGain != null
                ? `<div style="text-align:right;"><span style="color:#34d399;font-weight:700;font-size:0.75rem;font-variant-numeric:tabular-nums;">+${Number(maxGain).toFixed(2)}%</span></div>`
                : '<span style="color:#64748b;">—</span>';

            // Outcome badge
            let outcome = g.best_outcome;
            let outcomeLabel = g.best_outcome_label || (isLiveRecent ? `Live Active 🟢 (+0.0% D${daysElapsed})` : '14D Settled');
            let outcomeColor = '#94a3b8';
            let outcomeBg = 'rgba(148,163,184,0.12)';
            let outcomeBorder = 'rgba(148,163,184,0.25)';

            if (g.has_target_hit) {
                outcomeColor = '#34d399';
                outcomeBg = 'rgba(16,185,129,0.18)';
                outcomeBorder = 'rgba(16,185,129,0.45)';
                outcomeLabel = 'Target Hit 🎯';
            } else if (g.has_triggered) {
                outcomeColor = isLiveRecent ? '#34d399' : '#38bdf8';
                outcomeBg = isLiveRecent ? 'rgba(16,185,129,0.18)' : 'rgba(56,189,248,0.18)';
                outcomeBorder = isLiveRecent ? 'rgba(16,185,129,0.45)' : 'rgba(56,189,248,0.45)';
                outcomeLabel = 'Triggered 🟢';
            } else if (g.has_stop_hit && !g.has_active) {
                outcomeColor = '#f87171';
                outcomeBg = 'rgba(239,68,68,0.18)';
                outcomeBorder = 'rgba(239,68,68,0.45)';
                outcomeLabel = 'Stop Hit 🛑';
            }

            // Score
            const score = g.max_score || 0;
            const scoreColor = score >= 75 ? '#fde68a' : (score >= 55 ? '#34d399' : '#60a5fa');
            const scoreBg = score >= 75 ? 'rgba(234,179,8,0.18)' : (score >= 55 ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.12)');

            const horizonBadge = isLiveRecent
                ? `<span style="font-size:0.60rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.35);padding:0.06rem 0.35rem;border-radius:3px;font-weight:700;display:inline-flex;align-items:center;gap:0.25rem;"><span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:#34d399;box-shadow:0 0 6px #34d399;"></span> LIVE D${daysElapsed}/14</span>`
                : `<span style="font-size:0.60rem;background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.3);padding:0.06rem 0.35rem;border-radius:3px;font-weight:600;">14D SETTLED</span>`;

            // Render Child Setups Sub-table
            const childSetupsRows = g.setups.map(s => {
                const sId = s.id;
                const sStratBadge = formatStrategyBadge(s.strategy, s.setup_archetype);
                const sDate = s.signal_date || '—';
                const sSigP = s.signal_price != null ? `₹${Number(s.signal_price).toFixed(2)}` : '—';
                const sTrigP = s.breakout_trigger != null ? `₹${Number(s.breakout_trigger).toFixed(2)}` : '—';
                const sTargetP = s.target_price != null ? `₹${Number(s.target_price).toFixed(2)}` : '—';
                const sStopP = s.stop_loss != null ? `₹${Number(s.stop_loss).toFixed(2)}` : '—';
                const sCurP = s.current_price != null ? `₹${Number(s.current_price).toFixed(2)}` : '—';

                const sRet = s.realized_return_pct;
                const sRetColor = sRet > 0 ? '#34d399' : (sRet < 0 ? '#f87171' : '#94a3b8');
                const sRetBg = sRet > 0 ? 'rgba(16,185,129,0.15)' : (sRet < 0 ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)');
                const sRetFormatted = sRet != null ? `${sRet >= 0 ? '+' : ''}${sRet.toFixed(2)}%` : '—';

                const sGain = s.max_gain_pct != null ? s.max_gain_pct : s.peak_gain_pct;
                const sGainStr = sGain != null ? `+${Number(sGain).toFixed(2)}%` : '—';

                const sScore = s.composite_score || 0;
                const sOutLabel = s.outcome_label || s.outcome || 'ACTIVE';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);background:rgba(2,6,23,0.6);transition:background 0.15s;" onmouseenter="this.style.background='rgba(30,41,59,0.5)'" onmouseleave="this.style.background='rgba(2,6,23,0.6)'">
                        <td style="padding:0.4rem 0.5rem;font-size:0.68rem;color:#64748b;font-weight:700;font-variant-numeric:tabular-nums;">#${sId}</td>
                        <td style="padding:0.4rem 0.5rem;font-size:0.72rem;white-space:nowrap;">${sStratBadge}</td>
                        <td style="padding:0.4rem 0.5rem;font-size:0.72rem;color:#cbd5e1;font-variant-numeric:tabular-nums;">${sDate}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#94a3b8;font-variant-numeric:tabular-nums;">${sSigP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#fbbf24;font-weight:600;font-variant-numeric:tabular-nums;">${sTrigP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#34d399;font-weight:600;font-variant-numeric:tabular-nums;">${sTargetP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#f87171;font-variant-numeric:tabular-nums;">${sStopP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#f8fafc;font-weight:700;font-variant-numeric:tabular-nums;">${sCurP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;">
                            <span style="font-size:0.70rem;font-weight:700;color:${sRetColor};background:${sRetBg};padding:0.08rem 0.35rem;border-radius:3px;font-variant-numeric:tabular-nums;">${sRetFormatted}</span>
                        </td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.70rem;color:#34d399;font-weight:700;font-variant-numeric:tabular-nums;">${sGainStr}</td>
                        <td style="padding:0.4rem 0.5rem;font-size:0.68rem;color:#cbd5e1;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${sOutLabel}">${sOutLabel}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:center;font-size:0.72rem;font-weight:700;color:#38bdf8;">${sScore.toFixed(0)}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:center;">
                            <button type="button" onclick="app.untrackSingleSetup(${sId}, '${sym}')" style="background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.64rem;padding:0.15rem 0.4rem;border-radius:3px;cursor:pointer;font-weight:600;" title="Untrack this specific setup (#${sId})">
                                🗑️ Untrack
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            return `
                <tr class="bk-table-row" data-ticker="${sym}">
                    <!-- Stock & Setup Confluence Cluster -->
                    <td style="padding:0.55rem 0.65rem;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">
                            <button type="button" onclick="app.toggleTrackedSetupRow('${cleanSym}')" id="breakoutToggleBtn_${cleanSym}" style="background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.3);color:#38bdf8;font-size:0.65rem;width:20px;height:20px;border-radius:3px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;padding:0;line-height:1;" title="Expand / Collapse ${setupCount} Setups Breakdown">
                                <span id="breakoutChevron_${cleanSym}">&#9654;</span>
                            </button>
                            <a href="/stock/${encodeURIComponent(sym)}" target="_blank" style="font-weight:700;color:#f8fafc;font-size:0.85rem;text-decoration:none;letter-spacing:-0.01em;" onmouseenter="this.style.color='#38bdf8'" onmouseleave="this.style.color='#f8fafc'">
                                ${sym}
                            </a>
                            ${setupCountBadge}
                            ${horizonBadge}
                        </div>
                        <div style="display:flex;align-items:center;gap:0.3rem;margin-top:4px;flex-wrap:wrap;">
                            ${stratBadges}
                        </div>
                        <div style="font-size:0.68rem;color:#94a3b8;margin-top:3px;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${g.company_name || sym}">${name} &middot; <span style="color:#64748b;">${ind}</span></div>
                    </td>

                    <!-- Latest Signal Date & Age -->
                    <td style="padding:0.55rem 0.65rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="font-weight:600;color:#e2e8f0;font-size:0.75rem;font-variant-numeric:tabular-nums;">${sigDate}</div>
                        <div style="font-size:0.62rem;color:#64748b;margin-top:1px;">${isLiveRecent ? '🟢 Live Active' : '14D Settled'}</div>
                    </td>

                    <!-- Tier -->
                    <td style="padding:0.55rem 0.5rem;text-align:center;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="font-size:0.65rem;font-weight:800;background:${tierBg};color:${tierColor};border:1px solid ${tierColor}44;padding:0.12rem 0.45rem;border-radius:4px;">${tier}</span>
                    </td>

                    <!-- Signal Price -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;font-weight:600;color:#94a3b8;font-size:0.75rem;font-variant-numeric:tabular-nums;border-right:1px solid rgba(255,255,255,0.03);">
                        ${sigP}
                    </td>

                    <!-- Trigger Level -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;font-weight:700;color:#fbbf24;font-size:0.75rem;font-variant-numeric:tabular-nums;border-right:1px solid rgba(255,255,255,0.03);">
                        ${trigP}
                    </td>

                    <!-- Target Price -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;font-weight:700;color:#34d399;font-size:0.75rem;font-variant-numeric:tabular-nums;border-right:1px solid rgba(255,255,255,0.03);">
                        ${targetP}
                    </td>

                    <!-- Stop Loss -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;font-weight:600;color:#f87171;font-size:0.75rem;font-variant-numeric:tabular-nums;border-right:1px solid rgba(255,255,255,0.03);">
                        ${stopP}
                    </td>

                    <!-- Current Price -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="font-weight:800;color:#f8fafc;font-size:0.82rem;font-variant-numeric:tabular-nums;">${curP}</div>
                        <div style="font-size:0.58rem;color:${isLiveRecent ? '#34d399' : '#64748b'};margin-top:1px;font-weight:600;">${isLiveRecent ? 'Live Quote' : '14D Close'}</div>
                    </td>

                    <!-- Return % -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="display:inline-block;font-weight:800;font-size:0.76rem;color:${retColor};background:${retBg};border:1px solid ${retBorder};padding:0.12rem 0.45rem;border-radius:4px;font-variant-numeric:tabular-nums;">
                            ${retFormatted}
                        </span>
                    </td>

                    <!-- Max Gain & Peak -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;font-size:0.75rem;border-right:1px solid rgba(255,255,255,0.03);">
                        ${maxGainStr}
                    </td>

                    <!-- Outcome Status & Explanation -->
                    <td style="padding:0.55rem 0.65rem;text-align:left;border-right:1px solid rgba(255,255,255,0.03);min-width:160px;">
                        <div style="display:flex;align-items:center;gap:0.35rem;">
                            <span style="display:inline-block;font-size:0.65rem;font-weight:700;background:${outcomeBg};color:${outcomeColor};border:1px solid ${outcomeBorder};padding:0.12rem 0.45rem;border-radius:4px;">
                                ${outcomeLabel}
                            </span>
                        </div>
                    </td>

                    <!-- Score -->
                    <td style="padding:0.55rem 0.5rem;text-align:center;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="display:inline-block;font-weight:800;font-size:0.78rem;color:${scoreColor};background:${scoreBg};border:1px solid ${scoreColor}44;padding:0.12rem 0.45rem;border-radius:5px;font-variant-numeric:tabular-nums;">
                            ${score.toFixed(0)}
                        </span>
                    </td>

                    <!-- Actions -->
                    <td style="padding:0.55rem 0.65rem;text-align:center;white-space:nowrap;">
                        <div style="display:flex;align-items:center;justify-content:center;gap:0.3rem;">
                            <button type="button" onclick="app.toggleTrackedSetupRow('${cleanSym}')" class="btn btn-sm" style="background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);font-size:0.68rem;padding:0.22rem 0.45rem;border-radius:4px;cursor:pointer;font-weight:600;" title="View Setup Breakdown">
                                🔍 Setups (${setupCount})
                            </button>
                            <button type="button" onclick="app.openBreakoutHistoryModal('${sym}')" class="btn btn-sm" style="background:rgba(168,85,247,0.12);color:#c084fc;border:1px solid rgba(168,85,247,0.3);font-size:0.68rem;padding:0.22rem 0.45rem;border-radius:4px;cursor:pointer;font-weight:600;" title="View Transition Lifecycle & Notes Timeline">
                                📜 History
                            </button>
                            <a href="/stock/${encodeURIComponent(sym)}" target="_blank" class="btn btn-sm" style="background:rgba(59,130,246,0.12);color:#60a5fa;border:1px solid rgba(59,130,246,0.25);font-size:0.68rem;padding:0.22rem 0.45rem;border-radius:4px;text-decoration:none;font-weight:600;" title="Open Stock Intelligence">
                                📊 Intel
                            </a>
                            <button type="button" onclick="app.untrackAllForTicker('${sym}')" class="btn btn-sm" style="background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.68rem;padding:0.22rem 0.45rem;border-radius:4px;cursor:pointer;font-weight:600;" title="Untrack ALL setups for ${sym}">
                                🗑️
                            </button>
                        </div>
                    </td>
                </tr>

                <!-- Child Drawer Row: Individual Setups Breakdown -->
                <tr id="breakoutChildRow_${cleanSym}" style="display:none;background:#030712;">
                    <td colspan="13" style="padding:0.6rem 0.85rem;border-bottom:2px solid rgba(56,189,248,0.2);">
                        <div style="background:#020617;border:1px solid rgba(56,189,248,0.2);border-radius:6px;padding:0.6rem 0.8rem;box-shadow:inset 0 2px 4px rgba(0,0,0,0.5);">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem;padding-bottom:0.35rem;border-bottom:1px solid rgba(255,255,255,0.06);">
                                <div style="font-size:0.75rem;font-weight:700;color:#38bdf8;display:flex;align-items:center;gap:0.4rem;">
                                    <span>🔍 Individual Setups Breakdown for <strong style="color:#f8fafc;">${sym}</strong></span>
                                    <span style="font-size:0.65rem;color:#94a3b8;font-weight:500;">(${setupCount} active/historical setup triggers)</span>
                                </div>
                                <button type="button" onclick="app.untrackAllForTicker('${sym}')" style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.35);font-size:0.65rem;padding:0.18rem 0.5rem;border-radius:4px;cursor:pointer;font-weight:600;">
                                    🗑️ Untrack All Setups for ${sym}
                                </button>
                            </div>

                            <div style="overflow-x:auto;">
                                <table style="width:100%;border-collapse:collapse;font-size:0.72rem;">
                                    <thead>
                                        <tr style="border-bottom:1px solid rgba(255,255,255,0.08);color:#64748b;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.04em;">
                                            <th style="padding:0.35rem 0.5rem;text-align:left;">Setup ID</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:left;">Strategy</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:left;">Signal Date</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:right;">Entry Signal</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:right;">Trigger</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:right;">Target</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:right;">Stop Loss</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:right;">Current</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:right;">Return %</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:right;">Peak Gain</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:left;">Outcome</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:center;">Score</th>
                                            <th style="padding:0.35rem 0.5rem;text-align:center;">Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${childSetupsRows}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    };

    // Toggle child drawer for setups
    app.toggleTrackedSetupRow = function(cleanSym) {
        const childRow = document.getElementById(`breakoutChildRow_${cleanSym}`);
        const chevron = document.getElementById(`breakoutChevron_${cleanSym}`);
        if (!childRow) return;

        const isHidden = childRow.style.display === 'none' || !childRow.style.display;
        if (isHidden) {
            childRow.style.display = 'table-row';
            if (chevron) {
                chevron.innerHTML = '&#9660;'; // ▼
                chevron.style.color = '#38bdf8';
            }
        } else {
            childRow.style.display = 'none';
            if (chevron) {
                chevron.innerHTML = '&#9654;'; // ▶
                chevron.style.color = '#94a3b8';
            }
        }
    };

    // Untrack a single setup by ID
    app.untrackSingleSetup = async function(setupId, ticker) {
        if (!confirm(`Are you sure you want to untrack setup #${setupId} for ${ticker}?`)) return;
        try {
            const res = await fetch(`/api/v1/breakout/tracked/${setupId}`, {
                method: 'DELETE',
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to untrack setup');

            // Optimistically remove from cached items
            app._trackedBreakoutsData = (app._trackedBreakoutsData || []).filter(item => item.id !== setupId);

            // Re-render table and update KPI cards
            app.renderTrackedBreakoutsTable(app._trackedBreakoutsData);
            if (typeof app.updateBreakoutKPICards === 'function') {
                app.updateBreakoutKPICards(app._trackedBreakoutsData);
            }

            if (typeof showToast === 'function') {
                showToast(`Untracked setup #${setupId} for ${ticker}`, 'success');
            }
        } catch (err) {
            console.error('[BREAKOUT-TRACKED] Error untracking setup:', err);
            alert(`Error untracking setup: ${err.message}`);
        }
    };

    // Untrack all setups for a ticker
    app.untrackAllForTicker = async function(ticker) {
        if (!confirm(`⚠️ Are you sure you want to untrack ALL setups for ${ticker}? This will remove it completely from the tracked breakout archive.`)) return;
        try {
            const res = await fetch(`/api/v1/breakout/tracked/ticker/${encodeURIComponent(ticker)}`, {
                method: 'DELETE',
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to untrack setups');

            // Optimistically remove from cached items
            const symClean = ticker.toUpperCase().replace(/\.NS$/i, '');
            app._trackedBreakoutsData = (app._trackedBreakoutsData || []).filter(item => {
                const t = (item.ticker || '').toUpperCase().replace(/\.NS$/i, '');
                return t !== symClean;
            });

            // Re-render table and update KPI cards
            app.renderTrackedBreakoutsTable(app._trackedBreakoutsData);
            if (typeof app.updateBreakoutKPICards === 'function') {
                app.updateBreakoutKPICards(app._trackedBreakoutsData);
            }

            if (typeof showToast === 'function') {
                showToast(`Untracked ${data.deleted_count || 'all'} setups for ${ticker}`, 'success');
            }
        } catch (err) {
            console.error('[BREAKOUT-TRACKED] Error untracking ticker:', err);
            alert(`Error untracking ticker: ${err.message}`);
        }
    };
    };

})(); // end tracked_breakouts IIFE
