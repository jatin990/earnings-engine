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
    app._trackedBreakoutPresetDays = 3;
    app._trackedBreakoutCapital = 1000000; // 10 Lakhs default
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
        const resultsView = document.getElementById('breakoutResultsContainer');
        const backtestView = document.getElementById('breakoutBacktestContainer');
        const trackedView = document.getElementById('breakoutTrackedContainer');

        const btnScanner = document.getElementById('btnBreakoutSubtabScanner');
        const btnResults = document.getElementById('btnBreakoutSubtabResults');
        const btnBacktest = document.getElementById('btnBreakoutSubtabBacktest');
        const btnTracked = document.getElementById('btnBreakoutSubtabTracked');
        const contextLabel = document.getElementById('bkSubtabContextLabel');

        const sideSubScanner = document.getElementById('sidebarSubBreakoutScanner');
        const sideSubResults = document.getElementById('sidebarSubBreakoutResults');
        const sideSubBacktest = document.getElementById('sidebarSubBreakoutBacktest');
        const sideSubTracked = document.getElementById('sidebarSubBreakoutTracked');

        if (scannerView) scannerView.style.display = 'none';
        if (resultsView) resultsView.style.display = 'none';
        if (backtestView) backtestView.style.display = 'none';
        if (trackedView) trackedView.style.display = 'none';

        if (btnScanner) btnScanner.classList.remove('bk-subtab-active');
        if (btnResults) btnResults.classList.remove('bk-subtab-active');
        if (btnBacktest) btnBacktest.classList.remove('bk-subtab-active');
        if (btnTracked) btnTracked.classList.remove('bk-subtab-active');

        if (sideSubScanner) sideSubScanner.classList.remove('active');
        if (sideSubResults) sideSubResults.classList.remove('active');
        if (sideSubBacktest) sideSubBacktest.classList.remove('active');
        if (sideSubTracked) sideSubTracked.classList.remove('active');

        if (subtab === 'results') {
            if (resultsView) resultsView.style.display = 'block';
            if (btnResults) btnResults.classList.add('bk-subtab-active');
            if (sideSubResults) sideSubResults.classList.add('active');
            if (contextLabel) contextLabel.textContent = '📊 Results Breakout Radar (Recent & Upcoming Earnings Technical Setups)';
            if (typeof app.loadResultsRadar === 'function') {
                app.loadResultsRadar();
            }
        } else if (subtab === 'backtest') {
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
        app.setTrackedBreakoutPreset(3);
    };

    // =========================================================================
    // 💰 PORTFOLIO CAPITAL SIMULATOR (10L Default, 70/30 Target Booking Rule)
    // =========================================================================
    app.formatInr = function(val, showSign = false) {
        if (val == null || isNaN(val)) return '—';
        const num = Number(val);
        const absVal = Math.abs(num);
        const sign = num > 0 ? (showSign ? '+' : '') : (num < 0 ? '-' : '');
        return `${sign}₹${absVal.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
    };

    app.setTrackedBreakoutCapital = function(cap) {
        app._trackedBreakoutCapital = Number(cap) || 1000000;
        const input = document.getElementById('breakoutTrackedCapitalInput');
        if (input) input.value = app._trackedBreakoutCapital;

        document.querySelectorAll('.bk-cap-preset').forEach(btn => {
            const btnCap = Number(btn.getAttribute('data-capital'));
            if (btnCap === app._trackedBreakoutCapital) {
                btn.classList.add('bk-cap-active');
            } else {
                btn.classList.remove('bk-cap-active');
            }
        });

        app.recalculatePortfolioSimulation();
    };

    app.onTrackedCapitalInputChange = function(val) {
        const num = parseFloat(val);
        if (isNaN(num) || num <= 0) return;
        app._trackedBreakoutCapital = num;
        document.querySelectorAll('.bk-cap-preset').forEach(btn => {
            const btnCap = Number(btn.getAttribute('data-capital'));
            if (btnCap === app._trackedBreakoutCapital) {
                btn.classList.add('bk-cap-active');
            } else {
                btn.classList.remove('bk-cap-active');
            }
        });
        app.recalculatePortfolioSimulation();
    };

    app.recalculatePortfolioSimulation = function() {
        const items = app._trackedBreakoutsData || [];
        const total = items.length;
        const cap = Number(app._trackedBreakoutCapital) || 1000000;
        const alloc = total > 0 ? (cap / total) : 0;

        let totalProfit = 0;
        let totalLoss = 0;
        let netPnl = 0;
        let winCount = 0;
        let lossCount = 0;

        items.forEach(it => {
            const outStr = (it.outcome || '').toUpperCase();
            const sigP = Number(it.signal_price || it.breakout_trigger || 0);
            const targetP = Number(it.target_price || 0);
            const stopP = Number(it.stop_loss || 0);
            const curP = Number(it.current_price || 0);
            const maxG = Number(it.max_gain_pct || 0);

            let simRet = 0;
            let bookNote = '';

            if (outStr === 'TARGET_HIT') {
                const targetRet = (sigP > 0 && targetP > 0) ? ((targetP - sigP) / sigP * 100) : Number(it.realized_return_pct || 0);
                const peakRet = Math.max(targetRet, maxG);
                simRet = (0.70 * targetRet) + (0.30 * peakRet);
                bookNote = `70% @ Target (+${targetRet.toFixed(1)}%), 30% @ Peak (+${peakRet.toFixed(1)}%)`;
            } else if (outStr === 'STOP_HIT' || outStr === 'STOP_LOSS_HIT') {
                let stopRet = (sigP > 0 && stopP > 0) ? ((stopP - sigP) / sigP * 100) : Number(it.realized_return_pct || -5);
                if (stopRet > 0) stopRet = -Math.abs(stopRet);
                simRet = stopRet;
                bookNote = `100% Stop Loss Hit (${stopRet.toFixed(1)}%)`;
            } else if (outStr === 'ACTIVE' || outStr === 'PENDING' || outStr.includes('COILING')) {
                simRet = Number(it.realized_return_pct || 0);
                bookNote = `MTM Live (${simRet >= 0 ? '+' : ''}${simRet.toFixed(1)}%)`;
            } else {
                simRet = Number(it.realized_return_pct || 0);
                bookNote = `14D Settled (${simRet >= 0 ? '+' : ''}${simRet.toFixed(1)}%)`;
            }

            const pnl = alloc * (simRet / 100);
            it.simulated_return_pct = simRet;
            it.simulated_allocation = alloc;
            it.simulated_pnl = pnl;
            it.simulated_booking_note = bookNote;

            netPnl += pnl;
            if (pnl > 0) {
                totalProfit += pnl;
                winCount++;
            } else if (pnl < 0) {
                totalLoss += Math.abs(pnl);
                lossCount++;
            }
        });

        const finalCap = cap + netPnl;
        const retPct = cap > 0 ? ((netPnl / cap) * 100) : 0;
        const pf = totalLoss > 0 ? (totalProfit / totalLoss) : (totalProfit > 0 ? 99.0 : 0.0);

        // Update UI tiles
        const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setEl('bkPortStatStart', app.formatInr(cap));
        setEl('bkPortStatValue', app.formatInr(finalCap));
        setEl('bkPortStatNetPnl', app.formatInr(netPnl, true));
        setEl('bkPortStatWins', app.formatInr(totalProfit, true));
        setEl('bkPortStatLosses', totalLoss > 0 ? `-${app.formatInr(totalLoss)}` : '₹0');
        setEl('bkPortStatWinCount', String(winCount));
        setEl('bkPortStatLossCount', String(lossCount));
        setEl('bkPortStatPF', pf >= 99 ? '∞ Max' : `${pf.toFixed(2)}x`);
        setEl('bkPortStatAlloc', app.formatInr(alloc));

        const netRetEl = document.getElementById('bkPortStatNetRet');
        if (netRetEl) {
            netRetEl.textContent = `(${retPct >= 0 ? '+' : ''}${retPct.toFixed(2)}%)`;
            netRetEl.style.color = retPct >= 0 ? '#34d399' : '#f87171';
        }

        const netPnlEl = document.getElementById('bkPortStatNetPnl');
        if (netPnlEl) {
            netPnlEl.style.color = netPnl >= 0 ? '#34d399' : '#f87171';
        }

        // Re-render table rows to display updated rupee amounts
        app.renderTrackedBreakoutsTable(items);
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
        params.set('capital', String(app._trackedBreakoutCapital || 1000000));
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
            setEl('bkTrackedKpiActiveCount', `${summary.active_count || 0} active · ${(summary.total_tracked || 0) - (summary.active_count || 0)} settled`);
            setEl('bkTrackedKpiWinRate', summary.win_rate_pct != null ? `${summary.win_rate_pct}%` : '—');
            setEl('bkTrackedKpiWinLoss', `${summary.win_count || 0}W · ${summary.loss_count || 0}L`);
            setEl('bkTrackedKpiTargetCount', summary.target_hit_count != null ? `${summary.target_hit_count} Hits` : '—');
            setEl('bkTrackedKpiTargetRate', summary.target_hit_rate_pct != null ? `(${summary.target_hit_rate_pct}%)` : '(—)');
            setEl('bkTrackedKpiAvgDays', summary.avg_days_to_target != null ? `${summary.avg_days_to_target} Days` : '—');
            setEl('bkTrackedKpiAvgReturn', summary.avg_return_pct != null ? `${summary.avg_return_pct >= 0 ? '+' : ''}${summary.avg_return_pct}%` : '—');
            setEl('bkTrackedKpiTopTicker', summary.max_return_ticker || '—');
            setEl('bkTrackedKpiMaxReturn', summary.max_return_pct != null ? `(${summary.max_return_pct >= 0 ? '+' : ''}${summary.max_return_pct}%)` : '');

            // Render Per-Strategy Matrix Breakdown
            renderPerStrategyBreakdown(summary.per_strategy_stats || {});

            app.recalculatePortfolioSimulation();
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

    // Render Per-Strategy Quantitative Breakdown Matrix
    function renderPerStrategyBreakdown(stats) {
        const tbody = document.getElementById('breakoutTrackedStrategyTableBody');
        if (!tbody) return;

        const stratKeys = Object.keys(stats || {});
        if (stratKeys.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" style="padding:1.5rem; text-align:center; color:#64748b; font-size:0.75rem;">No strategy performance records available for current timeframe filter.</td></tr>`;
            return;
        }

        const rowsHtml = stratKeys.map(k => {
            const s = stats[k] || {};
            const total = s.total_tracked || 0;
            const icon = s.icon || '⚡';
            const name = s.strategy_name || k;
            const badge = s.badge || k;

            const winRate = s.win_rate_pct != null ? s.win_rate_pct : 0.0;
            const winCount = s.win_count || 0;
            const lossCount = s.loss_count || 0;
            const winColor = winRate >= 65 ? '#34d399' : (winRate >= 50 ? '#fbbf24' : (total > 0 ? '#f87171' : '#94a3b8'));
            const winBg = winRate >= 65 ? 'rgba(16,185,129,0.15)' : (winRate >= 50 ? 'rgba(245,158,11,0.12)' : (total > 0 ? 'rgba(239,68,68,0.12)' : 'rgba(255,255,255,0.03)'));

            const targetHits = s.target_hit_count || 0;
            const targetRate = s.target_hit_rate_pct != null ? s.target_hit_rate_pct : 0.0;

            const avgDays = s.avg_days_to_target != null ? `${s.avg_days_to_target}d` : '—';
            const avgDaysBadge = s.avg_days_to_target != null
                ? `<span style="font-size:0.68rem; font-weight:700; color:#fbbf24; background:rgba(234,179,8,0.15); border:1px solid rgba(234,179,8,0.3); padding:0.08rem 0.4rem; border-radius:3px;">⏱️ ${avgDays}</span>`
                : `<span style="color:#64748b;">—</span>`;

            const stopHits = s.stop_hit_count || 0;
            const stopRate = s.stop_hit_rate_pct != null ? s.stop_hit_rate_pct : 0.0;

            const avgRet = s.avg_return_pct != null ? s.avg_return_pct : 0.0;
            const avgRetColor = avgRet > 0 ? '#34d399' : (avgRet < 0 ? '#f87171' : '#94a3b8');

            const avgPeak = s.avg_peak_gain_pct != null ? s.avg_peak_gain_pct : 0.0;

            const bestSym = s.best_ticker && s.best_ticker !== '—' ? s.best_ticker : '—';
            const bestRet = s.best_return_pct != null ? s.best_return_pct : 0.0;
            const bestWinnerHtml = bestSym !== '—'
                ? `<div style="display:flex; align-items:baseline; gap:0.3rem;"><strong style="color:#f8fafc; cursor:pointer;" onclick="app.inspectBreakoutStock('${bestSym}')">${bestSym}</strong> <span style="color:#34d399; font-size:0.65rem; font-weight:700;">+${bestRet.toFixed(1)}%</span></div>`
                : `<span style="color:#64748b;">—</span>`;

            return `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.04); background:rgba(2,6,23,0.4); transition:background 0.15s;" onmouseenter="this.style.background='rgba(30,41,59,0.4)'" onmouseleave="this.style.background='rgba(2,6,23,0.4)'">
                    <td style="padding:0.5rem 0.6rem; text-align:left;">
                        <div style="display:flex; align-items:center; gap:0.4rem;">
                            <span style="font-size:0.9rem;">${icon}</span>
                            <div>
                                <div style="font-weight:700; color:#f8fafc; font-size:0.74rem;">${name}</div>
                                <div style="font-size:0.58rem; color:#94a3b8;">${badge}</div>
                            </div>
                        </div>
                    </td>
                    <td style="padding:0.5rem 0.55rem; text-align:center; font-weight:700; color:#cbd5e1;">
                        <div>${total}</div>
                        <div style="font-size:0.56rem; color:#64748b;">${s.active_count || 0} act / ${s.triggered_count || 0} fired</div>
                    </td>
                    <td style="padding:0.5rem 0.55rem; text-align:center;">
                        <span style="font-weight:800; color:${winColor}; background:${winBg}; padding:0.1rem 0.4rem; border-radius:3px; font-size:0.72rem;">${total > 0 ? `${winRate}%` : '—'}</span>
                        <div style="font-size:0.56rem; color:#64748b; margin-top:2px;">${winCount}W / ${lossCount}L</div>
                    </td>
                    <td style="padding:0.5rem 0.55rem; text-align:center;">
                        <div style="font-weight:700; color:#38bdf8;">${targetHits} <span style="font-size:0.62rem; color:#94a3b8;">(${total > 0 ? targetRate : 0}%)</span></div>
                    </td>
                    <td style="padding:0.5rem 0.55rem; text-align:center;">
                        ${avgDaysBadge}
                    </td>
                    <td style="padding:0.5rem 0.55rem; text-align:center;">
                        <span style="color:${stopHits > 0 ? '#f87171' : '#94a3b8'}; font-weight:600;">${stopHits} <span style="font-size:0.62rem; color:#64748b;">(${total > 0 ? stopRate : 0}%)</span></span>
                    </td>
                    <td style="padding:0.5rem 0.55rem; text-align:right; font-weight:700; color:${avgRetColor};">
                        ${total > 0 ? `${avgRet >= 0 ? '+' : ''}${avgRet.toFixed(2)}%` : '—'}
                    </td>
                    <td style="padding:0.5rem 0.55rem; text-align:right; font-weight:700; color:#34d399;">
                        ${total > 0 ? `+${avgPeak.toFixed(2)}%` : '—'}
                    </td>
                    <td style="padding:0.5rem 0.6rem; text-align:left;">
                        ${bestWinnerHtml}
                    </td>
                </tr>
            `;
        }).join('');

        tbody.innerHTML = rowsHtml;
    }

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
                    quote_timestamp: item.quote_timestamp || item.current_price_time,
                    price_delay_status: item.price_delay_status,
                    is_price_stale: item.is_price_stale,
                    setups: [],
                    latest_signal_date: item.signal_date,
                    latest_signal_time: item.signal_time,
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
                    simulated_pnl: 0,
                    simulated_allocation: 0,
                });
            }

            const g = groupedMap.get(sym);
            g.setups.push(item);
            g.simulated_pnl += (item.simulated_pnl != null ? Number(item.simulated_pnl) : 0);
            g.simulated_allocation += (item.simulated_allocation != null ? Number(item.simulated_allocation) : 0);

            if (item.company_name && (!g.company_name || g.company_name === g.ticker)) g.company_name = item.company_name;
            if (item.industry && item.industry !== '—') g.industry = item.industry;
            if (item.current_price != null) g.current_price = item.current_price;
            if (item.quote_timestamp) g.quote_timestamp = item.quote_timestamp;
            if (item.price_delay_status) g.price_delay_status = item.price_delay_status;
            if (item.is_price_stale != null) g.is_price_stale = item.is_price_stale;

            // Date tracking
            if (item.signal_date && (!g.latest_signal_date || item.signal_date > g.latest_signal_date)) {
                g.latest_signal_date = item.signal_date;
                g.latest_signal_time = item.signal_time;
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
            const sigTime = g.latest_signal_time ? (g.latest_signal_time.length > 10 ? g.latest_signal_time.substring(11, 16) : g.latest_signal_time) : '';
            const sigDateLabel = sigDate !== '—' && sigTime ? `${sigDate} ${sigTime}` : sigDate;
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

            // Check if any setup in the group is late
            const anyLateSetup = g.setups.find(s => {
                const ideal = s.ideal_entry_price != null ? Number(s.ideal_entry_price) : (s.data?.calculation_notes?.ideal_entry_price != null ? Number(s.data.calculation_notes.ideal_entry_price) : null);
                return Boolean(s.is_late || (ideal != null && s.signal_price > ideal * 1.002));
            });
            const parentLateBadge = anyLateSetup
                ? `<div style="font-size:0.58rem;color:#fca5a5;margin-top:2px;line-height:1.2;" title="Late Detection: Signal was detected near or above breakout trigger.">
                     <span style="background:rgba(239,68,68,0.18);border:1px solid rgba(239,68,68,0.35);color:#fca5a5;padding:0.04rem 0.25rem;border-radius:3px;font-weight:700;">⚠️ Late Entry</span>
                   </div>`
                : '';

            // Quote Timestamp & Staleness Formatting for parent row
            const rawQuoteTs = g.quote_timestamp || g.current_date || '';
            let quoteTsLabel = rawQuoteTs;
            if (rawQuoteTs) {
                if (rawQuoteTs.includes('T') || (rawQuoteTs.includes(' ') && rawQuoteTs.length > 10)) {
                    try {
                        const qd = new Date(rawQuoteTs);
                        if (!isNaN(qd.getTime())) {
                            quoteTsLabel = `${qd.toISOString().slice(0, 10)} ${qd.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
                        }
                    } catch (e) {}
                }
            } else {
                quoteTsLabel = isLiveRecent ? 'Live Quote' : '14D Close';
            }

            const pDelayStatus = (g.price_delay_status || (isLiveRecent ? 'LIVE' : 'DELAYED')).toUpperCase();
            let pDelayBg = 'rgba(59,130,246,0.15)';
            let pDelayColor = '#60a5fa';
            let pDelayBorder = 'rgba(59,130,246,0.3)';
            if (pDelayStatus === 'LIVE') {
                pDelayBg = 'rgba(16,185,129,0.18)';
                pDelayColor = '#34d399';
                pDelayBorder = 'rgba(16,185,129,0.4)';
            } else if (pDelayStatus === 'MARKET CLOSED') {
                pDelayBg = 'rgba(148,163,184,0.15)';
                pDelayColor = '#94a3b8';
                pDelayBorder = 'rgba(148,163,184,0.3)';
            } else if (pDelayStatus === 'STALE') {
                pDelayBg = 'rgba(239,68,68,0.18)';
                pDelayColor = '#f87171';
                pDelayBorder = 'rgba(239,68,68,0.4)';
            } else if (pDelayStatus === 'DELAYED') {
                pDelayBg = 'rgba(245,158,11,0.15)';
                pDelayColor = '#fbbf24';
                pDelayBorder = 'rgba(245,158,11,0.35)';
            }

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

            const gTargetHitDays = g.setups.filter(s => s.days_to_target != null && s.outcome === 'TARGET_HIT').map(s => s.days_to_target);
            const gMinDays = gTargetHitDays.length > 0 ? Math.min(...gTargetHitDays) : null;

            if (g.has_target_hit) {
                outcomeColor = '#34d399';
                outcomeBg = 'rgba(16,185,129,0.18)';
                outcomeBorder = 'rgba(16,185,129,0.45)';
                outcomeLabel = `Target Hit 🎯${gMinDays != null ? ` (${gMinDays}d)` : ''}`;
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
                const sTime = s.signal_time ? (s.signal_time.length > 10 ? s.signal_time.substring(11, 16) : s.signal_time) : '';
                const sDateLabel = sDate !== '—' && sTime ? `${sDate} ${sTime}` : sDate;
                const sSigP = s.signal_price != null ? `₹${Number(s.signal_price).toFixed(2)}` : '—';
                const sIdeal = s.ideal_entry_price != null ? Number(s.ideal_entry_price) : (s.data?.calculation_notes?.ideal_entry_price != null ? Number(s.data.calculation_notes.ideal_entry_price) : null);
                const sIsLate = Boolean(s.is_late || (sIdeal != null && s.signal_price > sIdeal * 1.002));
                const sDelay = s.entry_delay_pct != null ? Number(s.entry_delay_pct) : (sIdeal ? ((s.signal_price - sIdeal) / sIdeal * 100) : 0);
                const sLateSub = (sIsLate && sIdeal != null)
                    ? `<div style="font-size:0.58rem;color:#f59e0b;margin-top:1px;"><sub>Ideal: ₹${sIdeal.toFixed(2)}</sub></div>`
                    : '';
                const sTrigP = s.breakout_trigger != null ? `₹${Number(s.breakout_trigger).toFixed(2)}` : '—';
                const sTargetP = s.target_price != null ? `₹${Number(s.target_price).toFixed(2)}` : '—';
                const sStopP = s.stop_loss != null ? `₹${Number(s.stop_loss).toFixed(2)}` : '—';
                const sCurP = s.current_price != null ? `₹${Number(s.current_price).toFixed(2)}` : '—';

                const sRawTs = s.quote_timestamp || s.current_price_time || s.current_date || '';
                let sQuoteTs = sRawTs;
                if (sRawTs && (sRawTs.includes('T') || (sRawTs.includes(' ') && sRawTs.length > 10))) {
                    try {
                        const sqd = new Date(sRawTs);
                        if (!isNaN(sqd.getTime())) {
                            sQuoteTs = `${sqd.toISOString().slice(0, 10)} ${sqd.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
                        }
                    } catch (e) {}
                }
                const sStatus = (s.price_delay_status || (isLiveRecent ? 'LIVE' : 'DELAYED')).toUpperCase();
                let sStatusBg = 'rgba(59,130,246,0.15)';
                let sStatusColor = '#60a5fa';
                let sStatusBorder = 'rgba(59,130,246,0.3)';
                if (sStatus === 'LIVE') {
                    sStatusBg = 'rgba(16,185,129,0.18)';
                    sStatusColor = '#34d399';
                    sStatusBorder = 'rgba(16,185,129,0.4)';
                } else if (sStatus === 'MARKET CLOSED') {
                    sStatusBg = 'rgba(148,163,184,0.15)';
                    sStatusColor = '#94a3b8';
                    sStatusBorder = 'rgba(148,163,184,0.3)';
                } else if (sStatus === 'STALE') {
                    sStatusBg = 'rgba(239,68,68,0.18)';
                    sStatusColor = '#f87171';
                    sStatusBorder = 'rgba(239,68,68,0.4)';
                } else if (sStatus === 'DELAYED') {
                    sStatusBg = 'rgba(245,158,11,0.15)';
                    sStatusColor = '#fbbf24';
                    sStatusBorder = 'rgba(245,158,11,0.35)';
                }

                const sRet = s.realized_return_pct;
                const sRetColor = sRet > 0 ? '#34d399' : (sRet < 0 ? '#f87171' : '#94a3b8');
                const sRetBg = sRet > 0 ? 'rgba(16,185,129,0.15)' : (sRet < 0 ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)');
                const sRetBorder = sRet > 0 ? 'rgba(16,185,129,0.3)' : (sRet < 0 ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)');
                const sRetFormatted = sRet != null ? `${sRet >= 0 ? '+' : ''}${sRet.toFixed(2)}%` : '—';
                const sSimPnl = s.simulated_pnl != null ? s.simulated_pnl : (s.simulated_allocation ? (s.simulated_allocation * (sRet / 100)) : null);
                const sPnlFormatted = sSimPnl != null ? app.formatInr(sSimPnl, true) : '';
                const sBookNote = s.simulated_booking_note || '';

                const sGain = s.max_gain_pct != null ? s.max_gain_pct : s.peak_gain_pct;
                const sGainStr = sGain != null ? `+${Number(sGain).toFixed(2)}%` : '—';

                const sScore = s.composite_score || 0;
                let sOutLabel = s.outcome_label || s.outcome || 'ACTIVE';
                if (s.outcome === 'TARGET_HIT' && s.days_to_target != null) {
                    sOutLabel = `Target Hit 🎯 (${s.days_to_target}d)`;
                }

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);background:rgba(2,6,23,0.6);transition:background 0.15s;cursor:pointer;" onmouseenter="this.style.background='rgba(30,41,59,0.5)'" onmouseleave="this.style.background='rgba(2,6,23,0.6)'" onclick="app.inspectBreakoutStock('${sym}')" title="Click to inspect setup forensics in Slide-Over Drawer">
                        <td style="padding:0.4rem 0.5rem;font-size:0.68rem;color:#64748b;font-weight:700;font-variant-numeric:tabular-nums;">#${sId}</td>
                        <td style="padding:0.4rem 0.5rem;font-size:0.72rem;white-space:nowrap;">${sStratBadge}</td>
                        <td style="padding:0.4rem 0.5rem;font-size:0.72rem;color:#cbd5e1;font-variant-numeric:tabular-nums;">${sDateLabel}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#94a3b8;font-variant-numeric:tabular-nums;">${sSigP}${sLateSub}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#fbbf24;font-weight:600;font-variant-numeric:tabular-nums;">${sTrigP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#34d399;font-weight:600;font-variant-numeric:tabular-nums;">${sTargetP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#f87171;font-variant-numeric:tabular-nums;">${sStopP}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.72rem;color:#f8fafc;font-weight:700;font-variant-numeric:tabular-nums;">
                            <div>${sCurP}</div>
                            <div style="font-size:0.55rem;color:#94a3b8;font-weight:400;margin-top:1px;">${sQuoteTs ? `🕒 ${sQuoteTs}` : ''}</div>
                            <div style="margin-top:0.1rem;"><span style="background:${sStatusBg};border:1px solid ${sStatusBorder};color:${sStatusColor};font-size:0.52rem;font-weight:800;padding:0.02rem 0.25rem;border-radius:2px;">${sStatus}</span></div>
                        </td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;">
                            <span style="font-size:0.70rem;font-weight:700;color:${sRetColor};background:${sRetBg};border:1px solid ${sRetBorder};padding:0.08rem 0.35rem;border-radius:3px;font-variant-numeric:tabular-nums;" title="${sBookNote || sOutLabel}">
                                ${sPnlFormatted ? `${sPnlFormatted} ` : ''}(${sRetFormatted})
                            </span>
                            ${sBookNote ? `<div style="font-size:0.55rem;color:#94a3b8;font-family:var(--font-mono);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px;" title="${sBookNote}">${sBookNote}</div>` : ''}
                        </td>
                        <td style="padding:0.4rem 0.5rem;text-align:right;font-size:0.70rem;color:#34d399;font-weight:700;font-variant-numeric:tabular-nums;">${sGainStr}</td>
                        <td style="padding:0.4rem 0.5rem;font-size:0.68rem;color:#cbd5e1;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${sOutLabel}">${sOutLabel}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:center;font-size:0.72rem;font-weight:700;color:#38bdf8;">${sScore.toFixed(0)}</td>
                        <td style="padding:0.4rem 0.5rem;text-align:center;" onclick="event.stopPropagation();">
                            <button type="button" onclick="app.untrackSingleSetup(${sId}, '${sym}')" style="background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.64rem;padding:0.15rem 0.4rem;border-radius:3px;cursor:pointer;font-weight:600;" title="Untrack this specific setup (#${sId})">
                                🗑️ Untrack
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            const groupPnl = g.simulated_pnl || 0;
            const groupAlloc = g.simulated_allocation || 0;
            const groupRet = groupAlloc > 0 ? ((groupPnl / groupAlloc) * 100) : (ret || 0);
            const groupPnlColor = groupPnl > 0 ? '#34d399' : (groupPnl < 0 ? '#f87171' : '#94a3b8');
            const groupPnlBg = groupPnl > 0 ? 'rgba(16,185,129,0.15)' : (groupPnl < 0 ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)');
            const groupPnlBorder = groupPnl > 0 ? 'rgba(16,185,129,0.3)' : (groupPnl < 0 ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)');
            const groupPnlFormatted = app.formatInr(groupPnl, true);
            const groupRetFormatted = `${groupRet >= 0 ? '+' : ''}${groupRet.toFixed(2)}%`;

            return `
                <tr class="bk-table-row" data-ticker="${sym}" onclick="app.inspectBreakoutStock('${sym}')" style="cursor:pointer;" title="Click to inspect setup forensics in Slide-Over Drawer">
                    <!-- Stock & Setup Confluence Cluster -->
                    <td style="padding:0.55rem 0.65rem;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">
                            <button type="button" onclick="app.toggleTrackedSetupRow('${cleanSym}')" id="breakoutToggleBtn_${cleanSym}" style="background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.3);color:#38bdf8;font-size:0.65rem;width:20px;height:20px;border-radius:3px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;padding:0;line-height:1;" title="Expand / Collapse ${setupCount} Setups Breakdown">
                                <span id="breakoutChevron_${cleanSym}">&#9654;</span>
                            </button>
                            <a href="/stock/${encodeURIComponent(sym)}" target="_blank" style="font-weight:700;color:#f8fafc;font-size:0.85rem;text-decoration:none;letter-spacing:-0.01em;" onmouseenter="this.style.color='#38bdf8'" onmouseleave="this.style.color='#f8fafc'">
                                ${sym}
                            </a>
                            <button type="button" class="btn-ticker-refresh" onclick="event.stopPropagation(); app.refreshSingleStockPrice('${sym}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.75rem;padding:0 0.15rem;opacity:0.75;line-height:1;transition:all 0.15s;" onmouseenter="this.style.opacity='1';this.style.color='#7dd3fc';" onmouseleave="this.style.opacity='0.75';this.style.color='#38bdf8';" title="Refresh live price & technical metrics for ${sym}">↻</button>
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
                        <div style="font-weight:600;color:#e2e8f0;font-size:0.75rem;font-variant-numeric:tabular-nums;">${sigDateLabel}</div>
                        <div style="font-size:0.62rem;color:#64748b;margin-top:1px;">${isLiveRecent ? '🟢 Live Active' : '14D Settled'}</div>
                    </td>

                    <!-- Tier -->
                    <td style="padding:0.55rem 0.5rem;text-align:center;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="font-size:0.65rem;font-weight:800;background:${tierBg};color:${tierColor};border:1px solid ${tierColor}44;padding:0.12rem 0.45rem;border-radius:4px;">${tier}</span>
                    </td>

                    <!-- Signal Price -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;font-weight:600;color:#94a3b8;font-size:0.75rem;font-variant-numeric:tabular-nums;border-right:1px solid rgba(255,255,255,0.03);">
                        <div>${sigP}</div>
                        ${parentLateBadge}
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
                        <div style="font-size:0.58rem;color:#94a3b8;margin-top:1px;font-weight:500;" title="Quote Timestamp">🕒 ${quoteTsLabel}</div>
                        <div style="margin-top:0.12rem;">
                            <span style="background:${pDelayBg};border:1px solid ${pDelayBorder};color:${pDelayColor};font-size:0.55rem;font-weight:800;padding:0.04rem 0.28rem;border-radius:3px;letter-spacing:0.02em;">${pDelayStatus}</span>
                        </div>
                    </td>

                    <!-- Return % & Booked P&L -->
                    <td style="padding:0.55rem 0.65rem;text-align:right;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="display:inline-block;font-weight:800;font-size:0.76rem;color:${groupPnlColor};background:${groupPnlBg};border:1px solid ${groupPnlBorder};padding:0.12rem 0.45rem;border-radius:4px;font-variant-numeric:tabular-nums;" title="Simulated Booked P&L across ${setupCount} setup(s)">
                            ${groupPnlFormatted} (${groupRetFormatted})
                        </span>
                        <div style="font-size:0.58rem;color:#64748b;font-family:var(--font-mono);margin-top:2px;">
                            Alloc: ${app.formatInr(groupAlloc)}
                        </div>
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
                    <td style="padding:0.55rem 0.65rem;text-align:center;white-space:nowrap;" onclick="event.stopPropagation();">
                        <div style="display:flex;align-items:center;justify-content:center;gap:0.3rem;">
                            <button type="button" onclick="app.inspectBreakoutStock('${sym}');" class="btn btn-sm" style="background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);font-size:0.68rem;padding:0.22rem 0.45rem;border-radius:4px;cursor:pointer;font-weight:700;" title="Inspect in Slide-Over Forensics Drawer">
                                ⚡ Forensics
                            </button>
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

})(); // end tracked_breakouts IIFE
