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
        app._activeBreakoutSubtab = subtab;
        const scannerView = document.getElementById('breakoutLiveScannerContainer');
        const backtestView = document.getElementById('breakoutBacktestContainer');
        const trackedView = document.getElementById('breakoutTrackedContainer');

        const btnScanner = document.getElementById('btnBreakoutSubtabScanner');
        const btnBacktest = document.getElementById('btnBreakoutSubtabBacktest');
        const btnTracked = document.getElementById('btnBreakoutSubtabTracked');
        const contextLabel = document.getElementById('bkSubtabContextLabel');

        if (scannerView) scannerView.style.display = 'none';
        if (backtestView) backtestView.style.display = 'none';
        if (trackedView) trackedView.style.display = 'none';

        if (btnScanner) btnScanner.classList.remove('bk-subtab-active');
        if (btnBacktest) btnBacktest.classList.remove('bk-subtab-active');
        if (btnTracked) btnTracked.classList.remove('bk-subtab-active');

        if (subtab === 'backtest') {
            if (backtestView) backtestView.style.display = 'block';
            if (btnBacktest) btnBacktest.classList.add('bk-subtab-active');
            if (contextLabel) contextLabel.textContent = '📅 Historical Point-in-Time Date Backtest Simulator';
            if (typeof app.loadBreakoutBacktest === 'function') {
                app.loadBreakoutBacktest();
            }
        } else if (subtab === 'tracked') {
            if (trackedView) trackedView.style.display = 'block';
            if (btnTracked) btnTracked.classList.add('bk-subtab-active');
            if (contextLabel) contextLabel.textContent = '📜 Permanent Tracked Breakout History (14D Horizon & Live Active Setups)';
            app.loadTrackedBreakouts();
        } else {
            // Default: 'scanner' (Active Setup Pool)
            if (scannerView) scannerView.style.display = 'block';
            if (btnScanner) btnScanner.classList.add('bk-subtab-active');
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

        tbody.innerHTML = items.map(c => {
            const sym = c.ticker || '—';
            const name = (c.company_name || sym).substring(0, 22);
            const ind = (c.industry || 'Equities').substring(0, 16);
            const tier = (c.tier || 'WARM').toUpperCase();
            const tierColor = tier === 'HOT' ? '#f87171' : '#fbbf24';
            const tierBg = tier === 'HOT' ? 'rgba(239,68,68,0.18)' : 'rgba(245,158,11,0.18)';

            const sigDate = c.signal_date || '—';
            const daysElapsed = c.days_elapsed != null ? c.days_elapsed : 0;
            const isLiveRecent = c.is_live_recent || daysElapsed < 14;
            const isSettled14D = c.settled_14d || daysElapsed >= 14;

            const ageLabel = isLiveRecent
                ? `<span style="color:#34d399;font-weight:700;">🟢 Day ${daysElapsed}/14 (Live)</span>`
                : `<span style="color:#94a3b8;">${daysElapsed}d ago (14D Settled)</span>`;

            const sigP = c.signal_price != null ? `₹${Number(c.signal_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
            const trigP = c.breakout_trigger != null ? `₹${Number(c.breakout_trigger).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
            const targetP = c.target_price != null ? `₹${Number(c.target_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
            const stopP = c.stop_loss != null ? `₹${Number(c.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
            const curP = c.current_price != null ? `₹${Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';

            // Return styling
            const ret = c.realized_return_pct;
            const retColor = ret > 0 ? '#34d399' : (ret < 0 ? '#f87171' : '#94a3b8');
            const retBg = ret > 0 ? 'rgba(16,185,129,0.15)' : (ret < 0 ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)');
            const retBorder = ret > 0 ? 'rgba(16,185,129,0.3)' : (ret < 0 ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)');
            const retFormatted = ret != null ? `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%` : '—';

            // Peak Max Gain & Peak Price
            const peakP = c.post_high != null ? c.post_high : (c.peak_price != null ? c.peak_price : null);
            const peakStr = peakP != null ? `₹${Number(peakP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '';
            const maxGain = c.max_gain_pct != null ? c.max_gain_pct : (c.peak_gain_pct != null ? c.peak_gain_pct : null);
            const maxGainStr = maxGain != null
                ? `<div style="text-align:right;"><span style="color:#34d399;font-weight:700;font-family:var(--font-mono);font-size:0.75rem;">+${Number(maxGain).toFixed(2)}%</span>${peakStr ? `<div style="font-size:0.60rem;color:#94a3b8;font-family:var(--font-mono);">${peakStr}</div>` : ''}</div>`
                : '<span style="color:#64748b;">—</span>';

            // Explanatory one-liner
            const oneLiner = c.what_happened_summary || c.explanation_one_liner;

            // Outcome badge
            const outcome = c.outcome || 'ACTIVE';
            let outcomeLabel = c.outcome_label || (isLiveRecent ? `🟢 Live Active (D${daysElapsed}/14)` : '14D Settled');
            let outcomeColor = '#94a3b8';
            let outcomeBg = 'rgba(148,163,184,0.12)';
            let outcomeBorder = 'rgba(148,163,184,0.25)';

            if (outcome === 'TARGET_HIT') {
                outcomeColor = '#34d399';
                outcomeBg = 'rgba(16,185,129,0.18)';
                outcomeBorder = 'rgba(16,185,129,0.45)';
            } else if (outcome === 'TRIGGERED' || outcome === 'BREAKOUT_SUCCEEDED') {
                outcomeColor = isLiveRecent ? '#34d399' : '#38bdf8';
                outcomeBg = isLiveRecent ? 'rgba(16,185,129,0.18)' : 'rgba(56,189,248,0.18)';
                outcomeBorder = isLiveRecent ? 'rgba(16,185,129,0.45)' : 'rgba(56,189,248,0.45)';
            } else if (outcome === 'STOP_HIT' || outcome === 'STOP_LOSS_HIT') {
                outcomeColor = '#f87171';
                outcomeBg = 'rgba(239,68,68,0.18)';
                outcomeBorder = 'rgba(239,68,68,0.45)';
            } else if (outcome === 'SETUP_FAILED' || outcome === 'BREAKOUT_FAILED') {
                outcomeColor = '#f87171';
                outcomeBg = 'rgba(239,68,68,0.14)';
                outcomeBorder = 'rgba(239,68,68,0.38)';
            } else if (outcome === 'BREAKOUT_RETRACED') {
                outcomeColor = '#fbbf24';
                outcomeBg = 'rgba(245,158,11,0.15)';
                outcomeBorder = 'rgba(245,158,11,0.35)';
            }

            // Row Tier Accent Class
            let rowClass = 'bk-table-row';
            if (outcome === 'TARGET_HIT' || outcome === 'BREAKOUT_SUCCEEDED') {
                rowClass += ' bk-row-success';
            } else if (outcome === 'STOP_HIT' || outcome === 'STOP_LOSS_HIT' || outcome === 'SETUP_FAILED') {
                rowClass += ' bk-row-stop';
            } else if (isLiveRecent) {
                rowClass += ' bk-row-hot';
            } else {
                rowClass += ' bk-row-warm';
            }

            // Score
            const score = c.composite_score || 0;
            const scoreColor = score >= 75 ? '#fde68a' : (score >= 55 ? '#34d399' : '#60a5fa');
            const scoreBg = score >= 75 ? 'rgba(234,179,8,0.18)' : (score >= 55 ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.12)');

            const archetype = c.setup_archetype || (score >= 60 ? '🔥 Breakout Setup' : '📈 Resistance Coil');

            const horizonBadge = isLiveRecent
                ? `<span style="font-size:0.58rem;background:rgba(16,185,129,0.2);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:0.04rem 0.32rem;border-radius:3px;font-weight:800;display:inline-flex;align-items:center;gap:0.2rem;" title="Live Active Breakout (within 14-day window)"><span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:#34d399;box-shadow:0 0 6px #34d399;"></span> LIVE D${daysElapsed}/14</span>`
                : `<span style="font-size:0.58rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:0.04rem 0.32rem;border-radius:3px;font-weight:700;" title="14-Day Horizon Settled Outcome">14D SETTLED</span>`;

            return `
                <tr class="${rowClass}" data-ticker="${sym}">
                    <!-- Stock & Archetype -->
                    <td style="padding:0.46rem 0.65rem;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">
                            <a href="/stock/${encodeURIComponent(sym)}" target="_blank" style="font-weight:800;color:#ffffff;font-family:var(--font-mono);font-size:0.82rem;text-decoration:none;letter-spacing:-0.01em;" onmouseenter="this.style.color='#38bdf8'" onmouseleave="this.style.color='#ffffff'">
                                ${sym}
                            </a>
                            <span style="font-size:0.60rem;color:#38bdf8;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.25);padding:0.04rem 0.32rem;border-radius:3px;font-weight:600;">${archetype}</span>
                            ${horizonBadge}
                            ${c.confirmation_badge ? `<span style="font-size:0.58rem;color:${c.confirmation_color || '#34d399'};background:rgba(255,255,255,0.05);border:1px solid ${c.confirmation_color || '#34d399'}44;padding:0.02rem 0.3rem;border-radius:3px;font-weight:700;">${c.confirmation_badge}</span>` : ''}
                        </div>
                        <div style="font-size:0.67rem;color:#94a3b8;margin-top:2px;max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${c.company_name || sym}">${name} &middot; <span style="color:#64748b;">${ind}</span></div>
                    </td>

                    <!-- Signal Date & Age -->
                    <td style="padding:0.46rem 0.65rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="font-family:var(--font-mono);font-weight:700;color:#f1f5f9;font-size:0.75rem;">${sigDate}</div>
                        <div style="font-size:0.62rem;font-family:var(--font-mono);margin-top:1px;">${ageLabel}</div>
                    </td>

                    <!-- Tier -->
                    <td style="padding:0.46rem 0.5rem;text-align:center;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="font-size:0.65rem;font-weight:800;background:${tierBg};color:${tierColor};border:1px solid ${tierColor}44;padding:0.1rem 0.42rem;border-radius:4px;">${tier}</span>
                    </td>

                    <!-- Signal Price -->
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:#93c5fd;font-size:0.75rem;border-right:1px solid rgba(255,255,255,0.03);">
                        ${sigP}
                    </td>

                    <!-- Trigger Level -->
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:#fde047;font-size:0.75rem;border-right:1px solid rgba(255,255,255,0.03);">
                        ${trigP}
                    </td>

                    <!-- Target Price -->
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:#34d399;font-size:0.75rem;border-right:1px solid rgba(255,255,255,0.03);">
                        ${targetP}
                    </td>

                    <!-- Stop Loss -->
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-weight:600;color:#f87171;font-size:0.75rem;border-right:1px solid rgba(255,255,255,0.03);">
                        ${stopP}
                    </td>

                    <!-- Current Price -->
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-weight:800;color:#f8fafc;font-size:0.80rem;border-right:1px solid rgba(255,255,255,0.03);">
                        ${curP}
                        ${isLiveRecent ? `<span style="font-size:0.58rem;color:#34d399;font-weight:700;display:block;">Live Quote</span>` : `<span style="font-size:0.58rem;color:#64748b;display:block;">Day 14 Price</span>`}
                    </td>

                    <!-- Return % -->
                    <td style="padding:0.46rem 0.65rem;text-align:right;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="display:inline-block;font-family:var(--font-mono);font-weight:800;font-size:0.76rem;color:${retColor};background:${retBg};border:1px solid ${retBorder};padding:0.12rem 0.42rem;border-radius:4px;">
                            ${retFormatted}
                        </span>
                        <div style="font-size:0.58rem;color:#64748b;font-family:var(--font-mono);margin-top:1px;">${isLiveRecent ? 'Live Return' : '14D Return'}</div>
                    </td>

                    <!-- Max Gain & Peak -->
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-size:0.75rem;border-right:1px solid rgba(255,255,255,0.03);">
                        ${maxGainStr}
                    </td>

                    <!-- Outcome Status & Explanation -->
                    <td style="padding:0.46rem 0.65rem;text-align:left;border-right:1px solid rgba(255,255,255,0.03);min-width:180px;">
                        <div style="display:flex;align-items:center;gap:0.35rem;">
                            <span style="display:inline-block;font-size:0.65rem;font-weight:700;background:${outcomeBg};color:${outcomeColor};border:1px solid ${outcomeBorder};padding:0.12rem 0.45rem;border-radius:4px;">
                                ${outcomeLabel}
                            </span>
                        </div>
                        ${oneLiner ? `<div style="font-size:0.62rem;color:#cbd5e1;line-height:1.25;margin-top:0.22rem;max-width:250px;">${oneLiner}</div>` : ''}
                    </td>

                    <!-- Score -->
                    <td style="padding:0.46rem 0.5rem;text-align:center;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="display:inline-block;font-family:var(--font-mono);font-weight:800;font-size:0.78rem;color:${scoreColor};background:${scoreBg};border:1px solid ${scoreColor}44;padding:0.12rem 0.45rem;border-radius:5px;" title="Volume: ${c.volume_score || 0} • Resistance: ${c.resistance_score || 0} • Compression: ${c.compression_score || 0}">
                            ${score.toFixed(0)}
                        </span>
                    </td>

                    <!-- Actions -->
                    <td style="padding:0.46rem 0.65rem;text-align:center;white-space:nowrap;">
                        <div style="display:flex;align-items:center;justify-content:center;gap:0.25rem;">
                            <a href="/stock/${encodeURIComponent(sym)}" target="_blank" class="btn btn-sm" style="background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);font-size:0.65rem;padding:0.18rem 0.45rem;border-radius:4px;text-decoration:none;" title="Open Stock Intelligence">
                                📊 Intel
                            </a>
                            <button type="button" onclick="app.openBreakoutNotesModal('${sym}')" class="btn btn-sm" style="background:#1e293b;color:#cbd5e1;border:1px solid rgba(255,255,255,0.1);font-size:0.65rem;padding:0.18rem 0.42rem;border-radius:4px;" title="View AI Notes">
                                🧠
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    };

})(); // end tracked_breakouts IIFE
