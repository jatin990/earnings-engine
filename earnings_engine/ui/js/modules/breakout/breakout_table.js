// =========================================================================
// Breakout Radar - Table Grid, Sorting, Columns & Data Loader Sub-module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app.loadBreakoutRadar = async function(forceLive = false, silent = false) {
        if (!app._breakoutAutocompleteWired && typeof app.wireBreakoutStockAutocomplete === 'function') {
            app.wireBreakoutStockAutocomplete();
            app._breakoutAutocompleteWired = true;
        }

        const badge = document.getElementById('breakoutScanningBadge');
        const lastScanEl = document.getElementById('breakoutLastScanTime');
        const modeBadge = document.getElementById('breakoutModeBadge');
        const histNotice = document.getElementById('breakoutHistoricalNotice');
        const tbody = document.getElementById('breakoutTableBody');
        if (badge && !silent) badge.style.display = 'inline-block';

        const universe = document.getElementById('breakoutUniverseSelect')?.value || 'nse_large_cap';
        const strategy = document.getElementById('breakoutStrategySelect')?.value || app._breakoutStrategy || 'ALL';
        const sortBy = document.getElementById('breakoutSortBy')?.value || 'composite_score';
        const minScore = document.getElementById('breakoutMinScore')?.value || 35;
        const asofDate = app._breakoutAsofDate || document.getElementById('breakoutDateInput')?.value || null;

        if (modeBadge) {
            if (asofDate) {
                modeBadge.textContent = `BACKTEST: ${asofDate}`;
                modeBadge.style.background = 'rgba(234,179,8,0.15)';
                modeBadge.style.color = '#fbbf24';
                modeBadge.style.borderColor = 'rgba(234,179,8,0.3)';
                if (histNotice) histNotice.style.display = 'inline';
            } else if (forceLive || app.breakoutLiveTracking) {
                modeBadge.textContent = `LIVE TRACKING (${new Date().toLocaleTimeString()})`;
                modeBadge.style.background = 'rgba(16,185,129,0.15)';
                modeBadge.style.color = '#34d399';
                modeBadge.style.borderColor = 'rgba(16,185,129,0.35)';
                if (histNotice) histNotice.style.display = 'none';
            } else {
                modeBadge.textContent = 'LIVE SCAN';
                modeBadge.style.background = 'rgba(59,130,246,0.15)';
                modeBadge.style.color = '#60a5fa';
                modeBadge.style.borderColor = 'rgba(59,130,246,0.3)';
                if (histNotice) histNotice.style.display = 'none';
            }
        }

        try {
            const tierSelect = document.getElementById('breakoutTierSelect');
            const tier = tierSelect?.value || app._breakoutPoolFilter || 'ALL';
            const params = new URLSearchParams({ universe: universe, strategy: strategy, sort_by: sortBy, min_score: minScore, limit: 100, tier: tier });
            if (asofDate) {
                params.set('asof_date', asofDate);
            }
            if (forceLive || app.breakoutLiveTracking) {
                params.set('live', 'true');
            }
            const mcapVal = document.getElementById('breakoutMcapSelect')?.value || 'all';
            if (mcapVal === 'gt1000') {
                params.set('mcap_min', '1000');
            } else if (mcapVal && mcapVal !== 'all') {
                params.set('mcap_class', mcapVal);
            }
            const volVal = document.getElementById('breakoutVolumeSelect')?.value || 'all';
            if (volVal && volVal !== 'all') {
                params.set('min_volume_ratio', volVal);
            }
            const convVal = document.getElementById('breakoutConvictionSelect')?.value || 'all';
            if (convVal && convVal !== 'all') {
                params.set('min_conviction', convVal);
            }
            const res = await fetch(API_BASE + '/api/v1/breakout-radar?' + params.toString());
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();

            app._breakoutData = data.candidates || [];
            const status = data.scan_status || {};
            const summary = data.backtest_summary || {};
            const poolStats = data.pool_stats || {};
            app._lastBreakoutPoolStats = poolStats;
            if (typeof app.updateBreakoutStrategyDropdown === 'function') {
                app.updateBreakoutStrategyDropdown(poolStats);
            }
            const total = app._breakoutData.length;
            const topCandidate = total > 0 ? app._breakoutData[0] : null;
            const avgScore = total > 0
                ? (app._breakoutData.reduce((s, c) => s + (c.composite_score || 0), 0) / total).toFixed(1)
                : '—';

            const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

            setEl('breakoutStatTotal', total);

            const hotCount = poolStats.hot_count != null ? poolStats.hot_count : (app._breakoutData.filter(c => (c.tier || 'HOT').toUpperCase() === 'HOT').length);
            const warmCount = poolStats.warm_count != null ? poolStats.warm_count : (app._breakoutData.filter(c => (c.tier || '').toUpperCase() === 'WARM').length);
            setEl('breakoutStatHotCount', hotCount.toLocaleString());
            setEl('breakoutStatWarmCount', warmCount.toLocaleString());
            setEl('breakoutStatScanned', poolStats.total_pool ? poolStats.total_pool.toLocaleString() : (status.total_monitored || total));

            const lateCount = poolStats.late_entries_count != null ? poolStats.late_entries_count : (app._breakoutData.filter(c => c.is_late || (c.entry_delay_pct != null && c.entry_delay_pct > 0.2)).length);
            const lateDelay = poolStats.avg_entry_delay_pct != null ? poolStats.avg_entry_delay_pct : 0.0;
            setEl('breakoutStatLateCount', lateCount.toLocaleString());
            setEl('breakoutStatLateDelay', `(+${Number(lateDelay).toFixed(1)}% avg)`);

            const isBreaking = typeof app.isItemBreaking === 'function' ? app.isItemBreaking : (item) => {
                if (!item) return false;
                const cp = item.current_price != null ? Number(item.current_price) : null;
                const tp = item.breakout_trigger != null ? Number(item.breakout_trigger) : null;
                const ph = item.post_high != null ? Number(item.post_high) : null;
                return Boolean(
                    item.is_breaking_out ||
                    item.outcome === 'TARGET_HIT' ||
                    item.outcome === 'BREAKOUT_SUCCEEDED' ||
                    (cp != null && tp != null && cp >= tp) ||
                    (ph != null && tp != null && ph >= tp)
                );
            };
            const breakingCount = (app._breakoutData || []).filter(isBreaking).length;
            const fireCard = document.getElementById('breakoutCardOnFire');

            if (asofDate && summary && summary.total_evaluated != null) {
                const firedCount = summary.breakout_fired_count != null ? summary.breakout_fired_count : (summary.success_count || breakingCount);
                const firedSuccess = summary.breakout_fired_success_count != null ? summary.breakout_fired_success_count : (summary.success_count || 0);
                const firedWinRate = summary.breakout_fired_win_rate_pct != null ? summary.breakout_fired_win_rate_pct : (summary.win_rate_pct || 0);
                const targetsHit = summary.targets_hit_count || 0;
                const breakoutsSucceeded = summary.breakouts_succeeded_count || 0;
                const breakoutsRetraced = summary.breakouts_retraced_count || 0;
                const stopCount = summary.stop_losses_hit_count || 0;
                const coilingCount = summary.coiling_count != null ? summary.coiling_count : Math.max(0, summary.total_evaluated - firedCount);

                setEl('breakoutStatBreakingCount', firedCount);
                if (fireCard) fireCard.classList.add('card-on-fire');
                setEl('breakoutStatBreakingSub', 'Fired');
                setEl('breakoutKpiSubFire', `🎯 ${targetsHit} Targets · 🟢 ${breakoutsSucceeded} Green · ⚠️ ${breakoutsRetraced} Retraced · 🛑 ${stopCount} Stops`);

                setEl('breakoutKpiLabel2', 'Breakout Win Rate %');
                setEl('breakoutStatTopScore', `${firedWinRate}%`);
                setEl('breakoutStatTopTicker', `${firedSuccess}/${firedCount} Fired Succeeded · ${coilingCount} Coiling`);

                setEl('breakoutKpiLabel3', 'Avg Realized Return');
                setEl('breakoutStatAvg', `${summary.avg_return_pct >= 0 ? '+' : ''}${summary.avg_return_pct}%`);
                const topPriceStr = summary.top_winner_price != null ? ` @ ₹${Number(summary.top_winner_price).toLocaleString('en-IN', {maximumFractionDigits:2})}` : '';
                setEl('breakoutKpiSub3', summary.top_winner_ticker ? `Top: ${summary.top_winner_ticker} (${summary.top_winner_gain_pct >= 0 ? '+' : ''}${summary.top_winner_gain_pct}%${topPriceStr})` : 'Across candidates');

                setEl('breakoutKpiLabel5', 'Backtest Date');
                setEl('breakoutStatDuration', asofDate);
                setEl('breakoutKpiSub5', `${firedCount} Fired · ${coilingCount} Coiling`);
            } else {
                setEl('breakoutStatBreakingCount', breakingCount);
                if (breakingCount > 0) {
                    if (fireCard) fireCard.classList.add('card-on-fire');
                    setEl('breakoutStatBreakingSub', 'Breached');
                    setEl('breakoutKpiSubFire', `⚡ ${breakingCount} setup(s) crossed trigger`);
                } else {
                    if (fireCard) fireCard.classList.remove('card-on-fire');
                    setEl('breakoutStatBreakingSub', 'Active');
                    setEl('breakoutKpiSubFire', 'All setups coiling below trigger');
                }

                setEl('breakoutKpiLabel2', 'Top Score');
                setEl('breakoutStatTopScore', topCandidate ? topCandidate.composite_score : '—');
                setEl('breakoutStatTopTicker', topCandidate ? (topCandidate.ticker || '—') : '—');

                setEl('breakoutKpiLabel3', 'Avg Score');
                setEl('breakoutStatAvg', avgScore);
                setEl('breakoutKpiSub3', 'Composite Average');

                setEl('breakoutKpiLabel5', 'Scan Duration');
                setEl('breakoutStatDuration', status.last_scan_duration_s != null ? `${status.last_scan_duration_s}s` : '—');
                const intervals = status.scan_intervals || {};
                setEl('breakoutKpiSub5', intervals.hot_min ? `Hot: ${intervals.hot_min}m · Warm: ${intervals.warm_min}m · Cold: ${intervals.cold_min}m` : 'Last Full Scan');
            }

            if (lastScanEl) {
                const uniLabel = universe === 'nifty_50' ? 'Nifty 50' : (universe === 'all' ? 'All Monitored' : universe);
                if (asofDate) {
                    lastScanEl.textContent = `${uniLabel} • Point-in-Time Backtest (${asofDate})`;
                } else if (status.last_scan_at) {
                    try {
                        const d = new Date(status.last_scan_at);
                        lastScanEl.textContent = `${uniLabel} • Live Pool (${d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })})`;
                    } catch {
                        lastScanEl.textContent = `${uniLabel} • Hot Breakout Pool`;
                    }
                } else if (total > 0) {
                    lastScanEl.textContent = `${uniLabel} • Hot Breakout Pool (${total} setups)`;
                } else if (status.status === 'running') {
                    lastScanEl.textContent = `${uniLabel} • Scanning now…`;
                } else {
                    lastScanEl.textContent = `${uniLabel} • Hot Breakout Pool`;
                }
            }

            if (typeof app.applyBreakoutFilterAndRender === 'function') {
                app.applyBreakoutFilterAndRender();
            }

            if (typeof app.loadBreakoutAuditLog === 'function') {
                app.loadBreakoutAuditLog();
            }
        } catch (err) {
            console.error('[BREAKOUT] Load error:', err);
            if (tbody && !silent) tbody.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#ef4444;font-size:0.8rem;">⚡ Failed to load breakout data. Is the server running?</td></tr>';
        } finally {
            if (badge) badge.style.display = 'none';
        }
    };

    const DEFAULT_BREAKOUT_COLS = ['stock', 'score', 'current_price', 'trigger', 'target_stop', 'return', 'outcome', 'signal_price', 'actions'];

    const BREAKOUT_COLUMNS = {
        stock: {
            id: 'stock',
            label: 'Stock & Quality',
            sortKey: 'ticker',
            align: 'left',
            headerStyle: 'color:#94a3b8;min-width:145px;',
            render: (c, ctx) => `
                <td style="padding:0.28rem 0.45rem;border-right:1px solid rgba(255,255,255,0.03);">
                    <div style="display:flex;flex-direction:column;gap:0.08rem;">
                        <div style="display:flex;align-items:center;gap:0.3rem;flex-wrap:nowrap;">
                            <a href="/stock/${encodeURIComponent(ctx.ticker)}" target="_blank" style="font-weight:800;color:#ffffff;font-family:var(--font-mono);font-size:0.78rem;text-decoration:none;letter-spacing:-0.01em;" title="Open ${ctx.ticker} stock intelligence in new tab" onmouseenter="this.style.color='#38bdf8'" onmouseleave="this.style.color='#ffffff'">${ctx.ticker}</a>
                            <button type="button" class="btn-ticker-refresh btn-tactile" onclick="event.stopPropagation(); if (app.refreshSingleStockPrice) app.refreshSingleStockPrice('${ctx.ticker}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.70rem;padding:0 0.1rem;opacity:0.8;line-height:1;" title="Refresh live price & technical metrics for ${ctx.ticker}">↻</button>
                            <a href="/stock/${encodeURIComponent(ctx.ticker)}" target="_blank" style="color:#71717a;text-decoration:none;font-size:0.65rem;" onclick="event.stopPropagation();" title="Open profile in new tab">↗</a>
                            ${c.confirmation_badge ? `
                                <span style="font-size:0.54rem;background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.25);padding:0.02rem 0.25rem;border-radius:3px;font-weight:800;white-space:nowrap;display:inline-flex;align-items:center;gap:0.15rem;" title="Volume expansion and fakeout protection indicator">
                                    ${c.confirmation_badge}
                                </span>
                            ` : (ctx.isBreakingOut ? `
                                <span style="font-size:0.54rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);padding:0.02rem 0.25rem;border-radius:3px;font-weight:800;white-space:nowrap;display:inline-flex;align-items:center;gap:0.15rem;" title="Price crossed above resistance trigger">
                                    ⚡ Breached
                                </span>
                            ` : '')}
                        </div>
                        <div style="font-size:0.64rem;color:#94a3b8;max-width:145px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${c.company_name || ctx.ticker}">${ctx.company}</div>
                        <div style="margin-top:0.05rem;display:flex;gap:0.2rem;flex-wrap:wrap;align-items:center;">
                            <span style="font-size:0.55rem;background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);padding:0.02rem 0.25rem;border-radius:3px;font-weight:800;" title="Tier: Elite Hot Breakout Pool">HOT</span>
                            <span style="font-size:0.55rem;background:#18181b;color:#cbd5e1;border:1px solid rgba(255,255,255,0.12);padding:0.02rem 0.25rem;border-radius:3px;font-weight:600;">${ctx.archetype}</span>
                            ${c.strategy ? `<span style="font-size:0.55rem;background:#18181b;color:#38bdf8;border:1px solid rgba(56,189,248,0.2);padding:0.02rem 0.25rem;border-radius:3px;font-weight:700;" title="Strategy Model: ${c.strategy}">${String(c.strategy).replace(/_/g, ' ')}</span>` : ''}
                            ${(c.institutional_flow && c.institutional_flow.funds_in > 0) ? `<span style="font-size:0.55rem;background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.25);padding:0.02rem 0.25rem;border-radius:3px;font-weight:700;" title="Institutional Accumulation: +${c.institutional_flow.funds_in} Funds Buying">🏛️ +${c.institutional_flow.funds_in}</span>` : ''}
                            ${c.is_real_tracked ? `
                                <span style="font-size:0.55rem;background:#18181b;color:#f4f4f5;border:1px solid rgba(255,255,255,0.2);padding:0.02rem 0.25rem;border-radius:3px;font-weight:800;display:inline-flex;align-items:center;gap:0.15rem;" title="Real-Time Tracked Entry recorded in SQLite database archive">
                                    <span style="display:inline-block;width:4px;height:4px;border-radius:50%;background:#34d399;"></span> REAL
                                </span>
                            ` : `
                                <span style="font-size:0.55rem;background:#18181b;color:#71717a;border:1px solid rgba(255,255,255,0.08);padding:0.02rem 0.25rem;border-radius:3px;font-weight:600;" title="Dynamic live scan setup">
                                    SCAN
                                </span>
                            `}
                        </div>
                    </div>
                </td>
            `
        },
        score: {
            id: 'score',
            label: 'Score',
            sortKey: 'composite_score',
            align: 'center',
            headerStyle: 'color:#94a3b8;width:55px;text-align:center;',
            render: (c, ctx) => `
                <td style="padding:0.28rem 0.35rem;text-align:center;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                    <span style="display:inline-block;background:${ctx.scoreBg};color:${ctx.scoreColor};border:1px solid ${ctx.scoreBorder};font-size:0.75rem;font-weight:800;font-family:var(--font-mono);padding:0.10rem 0.40rem;border-radius:4px;" title="Quantitative Conviction Score: ${ctx.score}/100">
                        ${ctx.score}
                    </span>
                </td>
            `
        },
        signal_price: {
            id: 'signal_price',
            label: 'Signal Price',
            sortKey: 'predicted_value',
            align: 'right',
            headerStyle: 'color:#94a3b8;',
            render: (c, ctx) => {
                const idealEntry = c.ideal_entry_price != null ? Number(c.ideal_entry_price) : (c.calculation_notes?.ideal_entry_price != null ? Number(c.calculation_notes.ideal_entry_price) : null);
                const sigVal = c.signal_price != null ? Number(c.signal_price) : (c.predicted_value != null ? Number(c.predicted_value) : (c.current_price != null ? Number(c.current_price) : null));
                const isLate = Boolean(c.is_late || (idealEntry != null && sigVal != null && sigVal > idealEntry * 1.002));
                const delayPct = c.entry_delay_pct != null ? Number(c.entry_delay_pct) : (idealEntry != null && sigVal != null ? ((sigVal - idealEntry) / idealEntry * 100) : 0);

                const subLateHtml = (isLate && idealEntry != null)
                    ? `<div style="font-size:0.58rem;color:#fca5a5;margin-top:1px;line-height:1.2;" title="Late Detection: Signal was detected after breakout occurred. Ideal entry was ₹${idealEntry.toFixed(2)} (+${delayPct.toFixed(1)}% earlier)">
                         <sub>Ideal: ₹${idealEntry.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}</sub>
                         <sub style="color:#f87171;font-weight:700;">(+${delayPct.toFixed(1)}% late)</sub>
                       </div>`
                    : '';

                const sigDate = c.signal_date || c.entry_date || '';
                const sigTime = c.signal_time ? (c.signal_time.length > 10 ? c.signal_time.substring(11, 16) : c.signal_time) : '';
                const sigDateTimeLabel = sigDate ? (sigTime ? `${sigDate} ${sigTime}` : sigDate) : 'Signal';

                return `
                <td style="padding:0.28rem 0.45rem;text-align:right;font-family:var(--font-mono);font-size:0.72rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                    <div style="font-weight:700;color:#f8fafc;">${ctx.sigPriceStr}</div>
                    ${subLateHtml}
                    <div style="font-size:0.58rem;color:#64748b;margin-top:1px;" title="Signal detection exact date & time">📅 ${sigDateTimeLabel}</div>
                </td>
                `;
            }
        },
        current_price: {
            id: 'current_price',
            label: 'Current Price',
            sortKey: 'current_price',
            align: 'right',
            headerStyle: 'color:#94a3b8;',
            render: (c, ctx) => {
                const rawTs = c.quote_timestamp || c.current_price_time || c.current_date || c.asof_date || ctx.asofDate || '';
                let asOfLabel = rawTs;
                if (rawTs) {
                    if (rawTs.includes('T') || (rawTs.includes(' ') && rawTs.length > 10)) {
                        try {
                            const d = new Date(rawTs);
                            if (!isNaN(d.getTime())) {
                                asOfLabel = `${d.toISOString().slice(0, 10)} ${d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
                            }
                        } catch (e) {}
                    }
                } else if (c.scanned_at) {
                    try {
                        asOfLabel = new Date(c.scanned_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
                    } catch (e) {}
                }
                if (!asOfLabel) asOfLabel = 'Today';

                const delayStatus = (c.price_delay_status || (c.is_live ? 'LIVE' : 'DELAYED')).toUpperCase();
                let delayBg = '#18181b';
                let delayColor = '#94a3b8';
                let delayBorder = 'rgba(255,255,255,0.12)';
                if (delayStatus === 'LIVE') {
                    delayBg = 'rgba(16,185,129,0.12)';
                    delayColor = '#34d399';
                    delayBorder = 'rgba(16,185,129,0.3)';
                } else if (delayStatus === 'MARKET CLOSED') {
                    delayBg = '#18181b';
                    delayColor = '#94a3b8';
                    delayBorder = 'rgba(255,255,255,0.1)';
                } else if (delayStatus === 'STALE') {
                    delayBg = '#18181b';
                    delayColor = '#71717a';
                    delayBorder = 'rgba(255,255,255,0.1)';
                } else if (delayStatus === 'DELAYED') {
                    delayBg = 'rgba(245,158,11,0.12)';
                    delayColor = '#fbbf24';
                    delayBorder = 'rgba(245,158,11,0.3)';
                }

                return `
                <td style="padding:0.28rem 0.45rem;text-align:right;font-family:var(--font-mono);font-size:0.72rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                    <div style="font-weight:800;color:${ctx.curPriceColor};font-size:0.78rem;">${ctx.curPriceStr}</div>
                    <div style="font-size:0.56rem;color:#94a3b8;font-weight:500;margin-top:1px;" title="Quote Timestamp">🕒 ${asOfLabel}</div>
                    <div style="margin-top:0.12rem;display:flex;gap:0.2rem;justify-content:flex-end;align-items:center;">
                        <span style="background:${delayBg};border:1px solid ${delayBorder};color:${delayColor};font-size:0.52rem;font-weight:800;padding:0.02rem 0.22rem;border-radius:3px;letter-spacing:0.02em;" title="Quote Freshness Status">${delayStatus}</span>
                        <span class="signal-badge" style="background:${ctx.curPriceBadgeBg};border:1px solid ${ctx.curPriceBadgeBorder};color:${ctx.curPriceBadgeText};font-size:0.56rem;font-weight:700;padding:0.04rem 0.26rem;border-radius:3px;display:inline-block;">${ctx.curPriceBadgeLabel}</span>
                    </div>
                </td>
                `;
            }
        },
        trigger: {
            id: 'trigger',
            label: 'Trigger (Res)',
            sortKey: 'breakout_trigger',
            align: 'right',
            headerStyle: 'color:#94a3b8;',
            render: (c, ctx) => {
                const idealEntry = c.ideal_entry_price != null ? Number(c.ideal_entry_price) : (c.calculation_notes?.ideal_entry_price != null ? Number(c.calculation_notes.ideal_entry_price) : null);
                const trigVal = c.breakout_trigger != null ? Number(c.breakout_trigger) : null;
                const isLate = Boolean(c.is_late || (idealEntry != null && trigVal != null && idealEntry < trigVal * 0.998));
                const baseSub = (isLate && idealEntry != null && Number(idealEntry).toFixed(2) !== Number(c.breakout_trigger).toFixed(2))
                    ? `<div style="font-size:0.56rem;color:#94a3b8;margin-top:1px;"><sub>Base Res: ₹${idealEntry.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}</sub></div>`
                    : '';

                return `
                <td style="padding:0.28rem 0.45rem;text-align:right;font-family:var(--font-mono);font-size:0.72rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                    <div style="font-weight:700;color:#38bdf8;">${ctx.triggerStr}</div>
                    ${baseSub}
                    <div style="font-size:0.58rem;margin-top:1px;">${ctx.gapPct}</div>
                </td>
                `;
            }
        },
        target_stop: {
            id: 'target_stop',
            label: 'Target / Stop',
            sortKey: null,
            align: 'right',
            headerStyle: 'color:#94a3b8;',
            render: (c, ctx) => `
                <td style="padding:0.28rem 0.45rem;text-align:right;font-family:var(--font-mono);font-size:0.68rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                    <div style="background:#09090b;border:1px solid rgba(255,255,255,0.08);padding:0.15rem 0.35rem;border-radius:4px;display:inline-flex;flex-direction:column;gap:1px;text-align:right;">
                        <div style="color:#34d399;font-weight:700;" title="Target Price">T: ${ctx.targetStr}</div>
                        <div style="color:#f87171;font-weight:600;" title="Stop Loss">SL: ${ctx.stopStr}</div>
                    </div>
                </td>
            `
        },
        return: {
            id: 'return',
            label: 'Return & Peak',
            sortKey: 'realized_return_pct',
            align: 'right',
            headerStyle: 'color:#94a3b8;',
            render: (c, ctx) => {
                const peakP = c.post_high != null ? c.post_high : (c.peak_price != null ? c.peak_price : null);
                const peakGain = c.max_gain_pct != null ? c.max_gain_pct : (c.peak_gain_pct != null ? c.peak_gain_pct : null);
                const peakStr = peakP != null
                    ? `₹${Number(peakP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`
                    : '—';
                return `
                <td style="padding:0.28rem 0.45rem;text-align:right;font-size:0.72rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                    ${ctx.retStr}
                    ${peakGain != null ? `
                        <div style="font-size:0.58rem;color:#94a3b8;font-family:var(--font-mono);margin-top:2px;" title="Peak price reached after breakout signal">
                            Peak: <span style="color:#34d399;font-weight:800;">+${peakGain}%</span> <span style="color:#cbd5e1;">(${peakStr})</span>
                        </div>
                    ` : ''}
                </td>
                `;
            }
        },
        outcome: {
            id: 'outcome',
            label: 'Outcome & Summary',
            sortKey: null,
            align: 'left',
            headerStyle: 'color:#94a3b8;',
            render: (c, ctx) => {
                const expl = c.what_happened_summary || c.explanation_one_liner;
                return `
                <td style="padding:0.28rem 0.45rem;border-right:1px solid rgba(255,255,255,0.03);max-width:175px;">
                    <div style="display:flex;align-items:center;gap:0.3rem;">
                        ${ctx.outcomeBadgeHtml(c)}
                    </div>
                    ${expl ? `
                        <div style="font-size:0.60rem;color:#cbd5e1;line-height:1.2;margin-top:0.18rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${expl}">
                            ${expl}
                        </div>
                    ` : ''}
                </td>
                `;
            }
        },
        actions: {
            id: 'actions',
            label: 'Actions',
            sortKey: null,
            align: 'center',
            headerStyle: 'color:#94a3b8;',
            render: (c, ctx) => `
                <td style="padding:0.28rem 0.45rem;text-align:center;white-space:nowrap;">
                    <div style="display:flex;align-items:center;justify-content:center;gap:0.2rem;">
                        <button type="button" onclick="event.stopPropagation(); if (app.openMultiChartModal) app.openMultiChartModal(['${ctx.ticker}'])" class="btn btn-sm btn-tactile" style="background:#18181b;color:#38bdf8;border:1px solid rgba(56,189,248,0.3);font-size:0.62rem;padding:0.14rem 0.35rem;border-radius:3px;cursor:pointer;" title="Launch interactive multi-chart split">
                            📈 Chart
                        </button>
                        <button type="button" onclick="event.stopPropagation(); if (app.openAddToWatchlistModal) app.openAddToWatchlistModal('${ctx.ticker}', ${c.current_price || c.signal_price || 0})" class="btn btn-sm btn-tactile" style="background:#18181b;color:#fbbf24;border:1px solid rgba(251,191,36,0.3);font-size:0.62rem;padding:0.14rem 0.35rem;border-radius:3px;cursor:pointer;" title="Add to watchlist">
                            ⭐
                        </button>
                        <button type="button" onclick="event.stopPropagation(); if (app.openBreakoutHistoryModal) app.openBreakoutHistoryModal('${ctx.ticker}')" class="btn btn-sm btn-tactile" style="background:#18181b;color:#cbd5e1;border:1px solid rgba(255,255,255,0.15);font-size:0.62rem;padding:0.14rem 0.35rem;border-radius:3px;cursor:pointer;" title="View Transition Lifecycle & Notes Timeline">
                            📜
                        </button>
                        <button type="button" id="btnReeval-${ctx.ticker.replace(/[^a-zA-Z0-9]/g, '_')}" onclick="event.stopPropagation(); if (app.reevaluateBreakoutStock) app.reevaluateBreakoutStock('${ctx.ticker}')" class="btn btn-sm btn-tactile" style="background:#18181b;color:#f4f4f5;border:1px solid rgba(255,255,255,0.18);font-size:0.62rem;padding:0.14rem 0.35rem;border-radius:3px;cursor:pointer;" title="Re-evaluate with fresh market prices">
                            ⚡
                        </button>
                    </div>
                </td>
            `
        }
    };

    app.getBreakoutColumnOrder = function() {
        try {
            const stored = JSON.parse(localStorage.getItem('nexus_breakout_col_order') || 'null');
            if (Array.isArray(stored) && stored.length) {
                const valid = stored.filter(k => BREAKOUT_COLUMNS[k]);
                DEFAULT_BREAKOUT_COLS.forEach(k => {
                    if (!valid.includes(k)) valid.push(k);
                });
                return valid;
            }
        } catch (e) {}
        return [...DEFAULT_BREAKOUT_COLS];
    };

    app.setBreakoutColumnOrder = function(cols) {
        localStorage.setItem('nexus_breakout_col_order', JSON.stringify(cols));
        const notice = document.getElementById('breakoutColOrderNotice');
        if (notice) {
            notice.style.display = 'inline-block';
            setTimeout(() => { notice.style.display = 'none'; }, 2500);
        }
        app.renderBreakoutTableHeader();
        if (app._breakoutData) {
            const limitVal = document.getElementById('breakoutLimitSelect')?.value || '10';
            const limitNum = limitVal === 'all' ? app._breakoutData.length : parseInt(limitVal, 10);
            app.renderBreakoutTable(app._breakoutData.slice(0, limitNum));
        }
    };

    app.resetBreakoutColumnOrder = function() {
        localStorage.removeItem('nexus_breakout_col_order');
        app.setBreakoutColumnOrder([...DEFAULT_BREAKOUT_COLS]);
    };

    app._draggedColKey = null;

    app.handleBreakoutColDragStart = function(e, colKey) {
        app._draggedColKey = colKey;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', colKey);
        e.currentTarget.style.opacity = '0.4';
    };

    app.handleBreakoutColDragOver = function(e, targetColKey) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const th = e.currentTarget;
        if (app._draggedColKey && app._draggedColKey !== targetColKey) {
            th.style.borderLeft = '2px solid #38bdf8';
            th.style.background = 'rgba(56,189,248,0.12)';
        }
    };

    app.handleBreakoutColLeave = function(e, targetColKey) {
        const th = e.currentTarget;
        th.style.borderLeft = '';
        th.style.background = '';
    };

    app.handleBreakoutColDrop = function(e, targetColKey) {
        e.preventDefault();
        const th = e.currentTarget;
        th.style.borderLeft = '';
        th.style.background = '';
        const sourceColKey = app._draggedColKey || e.dataTransfer.getData('text/plain');
        if (!sourceColKey || sourceColKey === targetColKey) return;

        const cols = [...app.getBreakoutColumnOrder()];
        const srcIdx = cols.indexOf(sourceColKey);
        const tgtIdx = cols.indexOf(targetColKey);
        if (srcIdx > -1 && tgtIdx > -1) {
            cols.splice(srcIdx, 1);
            cols.splice(tgtIdx, 0, sourceColKey);
            app.setBreakoutColumnOrder(cols);
        }
    };

    app.handleBreakoutColDragEnd = function(e) {
        app._draggedColKey = null;
        e.currentTarget.style.opacity = '1';
        document.querySelectorAll('#breakoutTableHeaderRow th').forEach(th => {
            th.style.borderLeft = '';
            th.style.background = '';
        });
    };

    app._breakoutSortField = null;
    app._breakoutSortAsc = false;

    app.sortBreakoutTable = function(field) {
        if (!field) return;
        if (app._breakoutSortField === field) {
            app._breakoutSortAsc = !app._breakoutSortAsc;
        } else {
            app._breakoutSortField = field;
            app._breakoutSortAsc = false;
        }
        if (app._breakoutData && app._breakoutData.length) {
            app._breakoutData.sort((a, b) => {
                let valA = a[field];
                let valB = b[field];
                if (valA == null) valA = -999999;
                if (valB == null) valB = -999999;
                if (typeof valA === 'string') {
                    return app._breakoutSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                }
                return app._breakoutSortAsc ? (valA - valB) : (valB - valA);
            });
            if (typeof app.applyBreakoutFilterAndRender === 'function') {
                app.applyBreakoutFilterAndRender();
            }
        }
    };

    app.renderBreakoutTableHeader = function() {
        const headerRow = document.getElementById('breakoutTableHeaderRow');
        if (!headerRow) return;

        const cols = app.getBreakoutColumnOrder();
        headerRow.innerHTML = cols.map(colKey => {
            const def = BREAKOUT_COLUMNS[colKey];
            if (!def) return '';

            const sortIcon = def.sortKey ? (app._breakoutSortField === def.sortKey ? (app._breakoutSortAsc ? ' ▲' : ' ▼') : ' ↕') : '';
            const isSortActive = def.sortKey && app._breakoutSortField === def.sortKey;
            const sortColor = isSortActive ? '#38bdf8' : '';

            return `
                <th
                    draggable="true"
                    data-col-key="${colKey}"
                    ondragstart="app.handleBreakoutColDragStart(event, '${colKey}')"
                    ondragover="app.handleBreakoutColDragOver(event, '${colKey}')"
                    ondragleave="app.handleBreakoutColLeave(event, '${colKey}')"
                    ondrop="app.handleBreakoutColDrop(event, '${colKey}')"
                    ondragend="app.handleBreakoutColDragEnd(event)"
                    onclick="${def.sortKey ? `app.sortBreakoutTable('${def.sortKey}')` : ''}"
                    style="position:sticky;top:0;z-index:30;background:#000000;padding:0.55rem 0.65rem;text-align:${def.align};${def.headerStyle || ''}${sortColor ? `color:${sortColor};` : ''}font-weight:700;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.04em;cursor:${def.sortKey ? 'pointer' : 'grab'};white-space:nowrap;user-select:none;border-bottom:1px solid rgba(255,255,255,0.08);box-shadow:0 2px 6px rgba(0,0,0,0.7);transition:background 0.15s, border-color 0.15s;"
                    title="Drag to move column${def.sortKey ? ' • Click to sort' : ''}"
                >
                    <span style="opacity:0.4;font-size:0.65rem;margin-right:0.25rem;cursor:grab;" title="Drag to move column">⋮⋮</span>
                    ${def.label}${sortIcon}
                </th>
            `;
        }).join('');
    };

    app.renderBreakoutTable = function(candidates, asofDate) {
        app.renderBreakoutTableHeader();
        const tbody = document.getElementById('breakoutTableBody');
        if (!tbody) return;

        const cols = app.getBreakoutColumnOrder();
        app._currentRenderedBreakoutList = candidates || [];

        const footerCountEl = document.getElementById('breakoutFooterCount');
        if (footerCountEl) {
            footerCountEl.textContent = (candidates || []).length;
        }

        if (!candidates || candidates.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${cols.length}" style="padding:2.5rem;text-align:center;color:#52525b;font-size:0.82rem;">⚡ No candidates found for ${asofDate ? 'date ' + asofDate : 'current scan'} above score threshold.<br><span style="font-size:0.72rem;color:#71717a;">Try lowering the Min Score or selecting another universe.</span></td></tr>`;
            if (typeof app.renderBreakoutSetupInspector === 'function') {
                app.renderBreakoutSetupInspector(null);
            }
            return;
        }

        const outcomeBadgeHtml = (c) => {
            const badge = c.outcome_badge || 'blue';
            const label = c.outcome_label || (c.breakout_happened ? 'Breakout Succeeded' : 'Pending');
            const colors = {
                emerald: { bg: 'rgba(16,185,129,0.15)', text: '#34d399', border: 'rgba(16,185,129,0.35)' },
                amber: { bg: 'rgba(245,158,11,0.15)', text: '#fbbf24', border: 'rgba(245,158,11,0.35)' },
                rose: { bg: 'rgba(239,68,68,0.15)', text: '#f87171', border: 'rgba(239,68,68,0.35)' },
                slate: { bg: '#18181b', text: '#94a3b8', border: 'rgba(255,255,255,0.1)' },
                blue: { bg: 'rgba(56,189,248,0.15)', text: '#38bdf8', border: 'rgba(56,189,248,0.35)' }
            };
            const style = colors[badge] || colors.blue;
            return `<span style="display:inline-block;background:${style.bg};color:${style.text};border:1px solid ${style.border};font-size:0.62rem;font-weight:700;padding:0.10rem 0.38rem;border-radius:4px;white-space:nowrap;">${label}</span>`;
        };

        const rows = candidates.map((c) => {
            const score = c.composite_score || 0;
            let scoreColor = '#cbd5e1';
            let scoreBg = '#18181b';
            let scoreBorder = 'rgba(255,255,255,0.12)';
            if (score >= 75) {
                scoreColor = '#34d399';
                scoreBg = 'rgba(16,185,129,0.12)';
                scoreBorder = 'rgba(16,185,129,0.3)';
            } else if (score >= 55) {
                scoreColor = '#38bdf8';
                scoreBg = 'rgba(56,189,248,0.12)';
                scoreBorder = 'rgba(56,189,248,0.3)';
            }

            const ticker = c.ticker || '—';
            const company = (c.company_name || ticker).substring(0, 20);
            const industry = (c.industry || '—').substring(0, 16);

            const sigPrice = c.predicted_value || c.signal_price || c.current_price;
            const sigPriceStr = sigPrice != null ? `₹${Number(sigPrice).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';

            const curPriceStr = c.current_price != null ? `₹${Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
            const triggerStr = c.breakout_trigger != null ? `₹${Number(c.breakout_trigger).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
            const targetStr = c.target_price != null ? `₹${Number(c.target_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
            const stopStr = c.stop_loss != null ? `₹${Number(c.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';

            let curPriceColor = '#f8fafc';
            let curPriceBadgeBg = '#18181b';
            let curPriceBadgeBorder = 'rgba(255,255,255,0.12)';
            let curPriceBadgeText = '#94a3b8';
            let curPriceBadgeLabel = 'Pending';

            const curVal = c.current_price != null ? Number(c.current_price) : null;
            const trigVal = c.breakout_trigger != null ? Number(c.breakout_trigger) : null;
            const targetVal = c.target_price != null ? Number(c.target_price) : null;
            const stopVal = c.stop_loss != null ? Number(c.stop_loss) : null;

            if (curVal != null) {
                if (targetVal != null && curVal >= targetVal) {
                    curPriceColor = '#34d399';
                    curPriceBadgeBg = 'rgba(16,185,129,0.15)';
                    curPriceBadgeBorder = 'rgba(16,185,129,0.35)';
                    curPriceBadgeText = '#34d399';
                    curPriceBadgeLabel = '🎯 Target Hit';
                } else if (trigVal != null && curVal >= trigVal * 1.002) {
                    curPriceColor = '#38bdf8';
                    curPriceBadgeBg = 'rgba(56,189,248,0.15)';
                    curPriceBadgeBorder = 'rgba(56,189,248,0.35)';
                    curPriceBadgeText = '#38bdf8';
                    curPriceBadgeLabel = '⚡ Breakout Fired';
                } else if (stopVal != null && curVal <= stopVal) {
                    curPriceColor = '#f87171';
                    curPriceBadgeBg = 'rgba(239,68,68,0.15)';
                    curPriceBadgeBorder = 'rgba(239,68,68,0.35)';
                    curPriceBadgeText = '#f87171';
                    curPriceBadgeLabel = 'SL Hit';
                } else if (trigVal != null && curVal >= trigVal * 0.985) {
                    curPriceColor = '#fbbf24';
                    curPriceBadgeBg = 'rgba(245,158,11,0.15)';
                    curPriceBadgeBorder = 'rgba(245,158,11,0.35)';
                    curPriceBadgeText = '#fbbf24';
                    curPriceBadgeLabel = 'Coiling';
                } else {
                    curPriceColor = '#cbd5e1';
                    curPriceBadgeBg = '#18181b';
                    curPriceBadgeBorder = 'rgba(255,255,255,0.12)';
                    curPriceBadgeText = '#cbd5e1';
                    curPriceBadgeLabel = 'Active Setup';
                }
            }

            const retPct = c.realized_return_pct;
            let retColor = '#94a3b8';
            let retBg = '#18181b';
            let retBorder = 'rgba(255,255,255,0.12)';
            if (retPct > 0) {
                retColor = '#34d399';
                retBg = 'rgba(16,185,129,0.12)';
                retBorder = 'rgba(16,185,129,0.3)';
            } else if (retPct < 0) {
                retColor = '#f87171';
                retBg = 'rgba(239,68,68,0.12)';
                retBorder = 'rgba(239,68,68,0.3)';
            }

            const retStr = retPct != null
                ? `<span style="display:inline-block;font-weight:800;color:${retColor};background:${retBg};border:1px solid ${retBorder};font-family:var(--font-mono);font-size:0.72rem;padding:0.08rem 0.36rem;border-radius:4px;">${retPct >= 0 ? '+' : ''}${Number(retPct).toFixed(2)}%</span>`
                : '<span style="color:#64748b;">—</span>';

            let gapPct = '';
            if (curVal != null && trigVal != null && trigVal > 0) {
                const diffPct = ((curVal - trigVal) / trigVal) * 100;
                if (diffPct >= 0.2) {
                    gapPct = `<span style="font-size:0.58rem;color:#38bdf8;font-weight:700;">(+${diffPct.toFixed(1)}% breached)</span>`;
                } else {
                    gapPct = `<span style="font-size:0.58rem;color:#fbbf24;font-weight:600;">(${diffPct.toFixed(1)}% to trigger)</span>`;
                }
            } else if (c.pct_from_high != null) {
                gapPct = `<span style="font-size:0.58rem;color:${c.pct_from_high >= 0 ? '#34d399' : '#a1a1aa'};font-weight:600;">(${c.pct_from_high >= 0 ? '+' : ''}${c.pct_from_high.toFixed(1)}%)</span>`;
            }

            const archetype = c.setup_archetype || (score >= 60 ? '⚡ Strong Breakout' : '📈 Resistance Coil');

            const postHighVal = c.post_high != null ? Number(c.post_high) : null;
            const isBreakingOut = Boolean(
                c.is_breaking_out ||
                c.outcome === 'TARGET_HIT' ||
                c.outcome === 'BREAKOUT_SUCCEEDED' ||
                (curVal != null && trigVal != null && curVal >= trigVal * 1.002) ||
                (postHighVal != null && trigVal != null && postHighVal >= trigVal * 1.002)
            );

            const cellCtx = {
                ticker,
                company,
                industry,
                archetype,
                sigPriceStr,
                curPriceStr,
                triggerStr,
                targetStr,
                stopStr,
                curPriceColor,
                curPriceBadgeBg,
                curPriceBadgeBorder,
                curPriceBadgeText,
                curPriceBadgeLabel,
                retStr,
                gapPct,
                score,
                scoreColor,
                scoreBg,
                scoreBorder,
                outcomeBadgeHtml,
                isBreakingOut
            };

            const cellsHtml = cols.map(colKey => {
                const def = BREAKOUT_COLUMNS[colKey];
                if (!def || typeof def.render !== 'function') return '';
                return def.render(c, cellCtx);
            }).join('');

            let rowClass = 'bk-table-row';
            if (c.outcome === 'TARGET_HIT' || c.outcome === 'BREAKOUT_SUCCEEDED') {
                rowClass += ' bk-row-success';
            } else if (c.outcome === 'STOP_HIT') {
                rowClass += ' bk-row-stop';
            } else if (isBreakingOut || c.tier === 'HOT') {
                rowClass += ' bk-row-hot';
            } else {
                rowClass += ' bk-row-warm';
            }

            const isSelected = app._selectedBreakoutTicker === ticker;
            if (isSelected) {
                rowClass += ' bk-row-selected';
            }

            return `<tr class="${rowClass}${isBreakingOut ? ' breakout-row-on-fire' : ''}" data-ticker="${ticker}" onclick="if (app.selectBreakoutCandidate) app.selectBreakoutCandidate('${ticker}', false, true)" style="cursor:pointer;">${cellsHtml}</tr>`;
        });

        tbody.innerHTML = rows.join('');

        if (candidates.length > 0 && typeof app.selectBreakoutCandidate === 'function') {
            const targetTicker = (app._selectedBreakoutTicker && candidates.some(c => c.ticker === app._selectedBreakoutTicker))
                ? app._selectedBreakoutTicker
                : candidates[0].ticker;
            app.selectBreakoutCandidate(targetTicker, false, false);
        }
    };
})();
