// =========================================================================
// Breakout Radar - Filters, Controls & Live Polling Sub-module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app._breakoutPollTimer = null;
    app._breakoutAsofDate = null;
    app._breakoutFilterBreakingOut = false;
    app._breakoutPoolFilter = 'ALL';
    app._breakoutFilterLate = false;
    app._breakoutRealTrackedOnly = false;
    app._breakoutStrategy = 'ALL';
    app.breakoutLiveTracking = false;
    app.breakoutLiveIntervalTimer = null;
    app.breakoutLiveIntervalMs = parseInt(localStorage.getItem('nexus_breakout_refresh_interval') || '300000', 10);

    app.isItemBreaking = function(item) {
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

    app.updateBreakoutTierBadge = function() {
        const badge = document.getElementById('breakoutPoolTierBadge');
        const card = document.getElementById('breakoutCardPool');
        const tier = (app._breakoutPoolFilter || 'ALL').toUpperCase();
        if (badge) {
            if (tier === 'HOT') {
                badge.textContent = 'HOT ONLY';
                badge.style.color = '#f87171';
                badge.style.background = 'rgba(239,68,68,0.18)';
                badge.style.borderColor = 'rgba(239,68,68,0.4)';
            } else if (tier === 'WARM') {
                badge.textContent = 'WARM ONLY';
                badge.style.color = '#facc15';
                badge.style.background = 'rgba(234,179,8,0.18)';
                badge.style.borderColor = 'rgba(234,179,8,0.4)';
            } else {
                badge.textContent = 'ALL';
                badge.style.color = '#38bdf8';
                badge.style.background = '#18181b';
                badge.style.borderColor = 'rgba(56,189,248,0.3)';
            }
        }
        if (card) {
            if (tier === 'HOT') {
                card.style.border = '1px solid rgba(239,68,68,0.35)';
            } else if (tier === 'WARM') {
                card.style.border = '1px solid rgba(234,179,8,0.35)';
            } else {
                card.style.border = '1px solid rgba(255,255,255,0.08)';
            }
        }
    };

    app.cycleBreakoutPoolFilter = function() {
        const current = (app._breakoutPoolFilter || 'ALL').toUpperCase();
        if (current === 'ALL') {
            app._breakoutPoolFilter = 'HOT';
        } else if (current === 'HOT') {
            app._breakoutPoolFilter = 'WARM';
        } else {
            app._breakoutPoolFilter = 'ALL';
        }
        const tierSel = document.getElementById('breakoutTierSelect');
        if (tierSel) tierSel.value = app._breakoutPoolFilter;
        app.updateBreakoutTierBadge();
        app.applyBreakoutFilterAndRender();
    };

    app.onBreakoutTierChange = function(val) {
        app._breakoutPoolFilter = (val || 'ALL').toUpperCase();
        const tierSel = document.getElementById('breakoutTierSelect');
        if (tierSel && tierSel.value !== app._breakoutPoolFilter) {
            tierSel.value = app._breakoutPoolFilter;
        }
        app.updateBreakoutTierBadge();
        app.applyBreakoutFilterAndRender();
    };

    app.toggleBreakingOutFilter = function() {
        app._breakoutFilterBreakingOut = !app._breakoutFilterBreakingOut;
        if (app._breakoutFilterBreakingOut) app._breakoutFilterLate = false;
        app.applyBreakoutFilterAndRender();
    };

    app.toggleBreakoutLateFilter = function() {
        app._breakoutFilterLate = !app._breakoutFilterLate;
        if (app._breakoutFilterLate) app._breakoutFilterBreakingOut = false;
        app.applyBreakoutFilterAndRender();
    };

    app.clearBreakoutFilter = function() {
        app._breakoutFilterBreakingOut = false;
        app._breakoutFilterLate = false;
        app._breakoutPoolFilter = 'ALL';
        const tierSel = document.getElementById('breakoutTierSelect');
        if (tierSel) tierSel.value = 'ALL';
        app.updateBreakoutTierBadge();
        app.applyBreakoutFilterAndRender();
    };

    app.toggleBreakoutRealTrackedOnly = function() {
        const sw = document.getElementById('breakoutRealTrackedSwitch');
        app._breakoutRealTrackedOnly = sw ? sw.checked : !app._breakoutRealTrackedOnly;
        app.applyBreakoutFilterAndRender();
    };

    app.clearBreakoutRealTrackedFilter = function() {
        app._breakoutRealTrackedOnly = false;
        const sw = document.getElementById('breakoutRealTrackedSwitch');
        if (sw) sw.checked = false;
        app.applyBreakoutFilterAndRender();
    };

    app.applyBreakoutFilterAndRender = function() {
        const fireCard = document.getElementById('breakoutCardOnFire');
        const totalCard = document.getElementById('breakoutCardTotal');
        const lateCard = document.getElementById('breakoutCardLate');
        const lateIndicator = document.getElementById('breakoutLateFilterIndicator');
        const activeNotice = document.getElementById('breakoutFilterNotice');
        const filterIndicator = document.getElementById('breakoutFilterIndicator');
        const breakingSub = document.getElementById('breakoutStatBreakingSub');

        const tierFilter = (app._breakoutPoolFilter || 'ALL').toUpperCase();
        let list = (app._breakoutData || []);
        if (tierFilter === 'HOT') {
            list = list.filter(c => (c.tier || 'HOT').toUpperCase() === 'HOT');
        } else if (tierFilter === 'WARM') {
            list = list.filter(c => (c.tier || '').toUpperCase() === 'WARM');
        }
        const breakingCount = list.filter(app.isItemBreaking).length;

        if (app._breakoutRealTrackedOnly) {
            list = list.filter(item => Boolean(item.is_real_tracked));
        }

        if (lateCard) {
            if (app._breakoutFilterLate) {
                lateCard.style.border = '1px solid rgba(245, 158, 11, 0.5)';
                lateCard.style.background = '#18181b';
            } else {
                lateCard.style.border = '1px solid rgba(255, 255, 255, 0.08)';
                lateCard.style.background = '#09090b';
            }
        }
        if (lateIndicator) {
            lateIndicator.style.display = app._breakoutFilterLate ? 'inline-block' : 'none';
        }

        if (app._breakoutFilterBreakingOut) {
            list = list.filter(app.isItemBreaking);
            if (fireCard) {
                fireCard.style.border = '1px solid rgba(255, 255, 255, 0.3)';
                fireCard.style.boxShadow = 'none';
                fireCard.style.background = '#18181b';
            }
            if (totalCard) totalCard.style.opacity = '0.75';
            if (filterIndicator) filterIndicator.style.display = 'inline-block';
            if (breakingSub) breakingSub.textContent = 'Filtered 🔍';
            if (activeNotice) {
                activeNotice.style.display = 'inline-flex';
                activeNotice.innerHTML = `<span>⚡</span> Filtering: <strong>Breaking Out Only (${list.length} setup${list.length === 1 ? '' : 's'})</strong> <button type="button" onclick="app.clearBreakoutFilter(); event.stopPropagation();" style="margin-left:0.45rem;background:#18181b;border:1px solid rgba(255,255,255,0.25);color:#f4f4f5;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">✕ Show All (${app._breakoutData.length})</button>`;
            }
        } else if (app._breakoutFilterLate) {
            list = list.filter(item => Boolean(item.is_late || (item.entry_delay_pct != null && item.entry_delay_pct > 0.2)));
            if (totalCard) totalCard.style.opacity = '0.75';
            if (filterIndicator) filterIndicator.style.display = 'none';
            if (activeNotice) {
                activeNotice.style.display = 'inline-flex';
                activeNotice.innerHTML = `<span>⚡</span> Filtering: <strong>Late Entries Only (${list.length} setup${list.length === 1 ? '' : 's'})</strong> <button type="button" onclick="app.clearBreakoutFilter(); event.stopPropagation();" style="margin-left:0.45rem;background:#18181b;border:1px solid rgba(255,255,255,0.25);color:#f4f4f5;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">✕ Show All (${app._breakoutData.length})</button>`;
            }
        } else if (app._breakoutRealTrackedOnly) {
            if (activeNotice) {
                activeNotice.style.display = 'inline-flex';
                activeNotice.innerHTML = `<span>🟢</span> Filtering: <strong>Real Tracked Entries Only (${list.length} setup${list.length === 1 ? '' : 's'})</strong> <button type="button" onclick="app.clearBreakoutRealTrackedFilter(); event.stopPropagation();" style="margin-left:0.45rem;background:#18181b;border:1px solid rgba(255,255,255,0.25);color:#f4f4f5;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">✕ Show All (${app._breakoutData.length})</button>`;
            }
        } else if (tierFilter !== 'ALL') {
            if (fireCard) {
                fireCard.style.border = '1px solid rgba(255, 255, 255, 0.08)';
                fireCard.style.boxShadow = 'none';
                fireCard.style.background = '#09090b';
            }
            if (totalCard) totalCard.style.opacity = '1';
            if (filterIndicator) filterIndicator.style.display = 'none';
            if (breakingSub) breakingSub.textContent = (app._breakoutAsofDate ? 'Fired' : (breakingCount > 0 ? 'Breached' : 'Active'));
            if (activeNotice) {
                activeNotice.style.display = 'inline-flex';
                const icon = tierFilter === 'HOT' ? '🔥' : '🟡';
                const label = tierFilter === 'HOT' ? 'Hot Pool Only' : 'Warm Pool Only';
                activeNotice.innerHTML = `<span>${icon}</span> Filtering: <strong>${label} (${list.length} setup${list.length === 1 ? '' : 's'})</strong> <button type="button" onclick="app.onBreakoutTierChange('ALL'); event.stopPropagation();" style="margin-left:0.45rem;background:#18181b;border:1px solid rgba(255,255,255,0.25);color:#f4f4f5;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">✕ Show All (${app._breakoutData.length})</button>`;
            }
        } else {
            if (fireCard) {
                fireCard.style.border = '1px solid rgba(255, 255, 255, 0.08)';
                fireCard.style.boxShadow = 'none';
                fireCard.style.background = '#09090b';
            }
            if (totalCard) totalCard.style.opacity = '1';
            if (filterIndicator) filterIndicator.style.display = 'none';
            if (breakingSub) breakingSub.textContent = (app._breakoutAsofDate ? 'Fired' : (breakingCount > 0 ? 'Breached' : 'Active'));
            if (activeNotice) activeNotice.style.display = 'none';
        }

        const limitVal = document.getElementById('breakoutLimitSelect')?.value || '10';
        const limitNum = limitVal === 'all' ? list.length : parseInt(limitVal, 10);
        if (typeof app.renderBreakoutTable === 'function') {
            app.renderBreakoutTable(list.slice(0, limitNum), app._breakoutAsofDate);
        }

        app.updateBreakoutStrategyDropdown();
    };

    app.updateBreakoutStrategyDropdown = function(poolStats) {
        const stratSelect = document.getElementById('breakoutStrategySelect');
        if (!stratSelect) return;

        const stats = poolStats || app._lastBreakoutPoolStats || {};
        const stratStats = stats.strategies || {};
        const tier = (app._breakoutPoolFilter || document.getElementById('breakoutTierSelect')?.value || 'ALL').toUpperCase();
        const asofDate = app._breakoutAsofDate || document.getElementById('breakoutDateInput')?.value || null;

        let counts = {};
        let allCount = 0;

        if (asofDate && app._breakoutData && app._breakoutData.length > 0) {
            app._breakoutData.forEach(c => {
                const s = (c.strategy || 'CLASSIC_TECHNICAL').toUpperCase();
                const cTier = (c.tier || 'HOT').toUpperCase();
                if (tier === 'ALL' || cTier === tier) {
                    counts[s] = (counts[s] || 0) + 1;
                    allCount++;
                }
            });
        } else if (stratStats && Object.keys(stratStats).length > 0) {
            for (const [sKey, sObj] of Object.entries(stratStats)) {
                const key = sKey.toUpperCase();
                let c = 0;
                if (tier === 'HOT') c = sObj.hot || 0;
                else if (tier === 'WARM') c = sObj.warm || 0;
                else c = sObj.total != null ? sObj.total : ((sObj.hot || 0) + (sObj.warm || 0));
                counts[key] = c;
                allCount += c;
            }
        } else if (app._breakoutData && app._breakoutData.length > 0) {
            app._breakoutData.forEach(c => {
                const s = (c.strategy || 'CLASSIC_TECHNICAL').toUpperCase();
                const cTier = (c.tier || 'HOT').toUpperCase();
                if (tier === 'ALL' || cTier === tier) {
                    counts[s] = (counts[s] || 0) + 1;
                    allCount++;
                }
            });
        }

        const STRATEGY_BASE_LABELS = {
            'ALL': 'All Strategies (Aggregated)',
            'CLASSIC_TECHNICAL': 'Classic Coiling (52W+ATR)',
            'NSE_DELIVERY_ABSORPTION': 'NSE Delivery Absorption',
            'NSE_FO_CALL_WALL': 'NSE F&O Call OI Wall',
            'VOLUME_PROFILE_VAH': 'Volume Profile VAH',
            'DONCHIAN_TTM_SQUEEZE': 'Donchian TTM Squeeze',
        };

        Array.from(stratSelect.options).forEach(opt => {
            const val = opt.value.toUpperCase();
            const baseName = STRATEGY_BASE_LABELS[val] || opt.getAttribute('data-base-label') || opt.textContent.replace(/\s*\(\d[\d,]*\)$/, '').trim();
            opt.setAttribute('data-base-label', baseName);
            const count = val === 'ALL' ? allCount : (counts[val] || 0);
            opt.textContent = `${baseName} (${count.toLocaleString()})`;
        });
    };

    app.toggleBreakoutExplainer = function() {
        const card = document.getElementById('breakoutExplainerCard');
        if (!card) return;
        card.style.display = (card.style.display === 'none' || !card.style.display) ? 'block' : 'none';
    };

    app.onBreakoutStrategyChange = function(strategy) {
        app._breakoutStrategy = strategy || 'ALL';
        if (typeof app.loadBreakoutRadar === 'function') {
            app.loadBreakoutRadar();
        }
    };

    app.onBreakoutUniverseChange = function(uni) {
        app._breakoutUniverse = uni || 'nse_large_cap';
        if (typeof app.loadBreakoutRadar === 'function') {
            app.loadBreakoutRadar();
        }
    };

    app.onBreakoutDateChange = function(dateStr) {
        app._breakoutAsofDate = dateStr && dateStr.trim() !== '' ? dateStr.trim() : null;

        document.querySelectorAll('.bk-preset-btn').forEach(btn => {
            const btnDays = parseInt(btn.getAttribute('data-days'), 10);
            if (btnDays === 0 && !app._breakoutAsofDate) {
                btn.classList.add('bk-preset-active');
            } else if (btnDays > 0 && app._breakoutAsofDate) {
                const d = new Date();
                d.setDate(d.getDate() - btnDays);
                const iso = d.toISOString().split('T')[0];
                if (iso === app._breakoutAsofDate) {
                    btn.classList.add('bk-preset-active');
                } else {
                    btn.classList.remove('bk-preset-active');
                }
            } else {
                btn.classList.remove('bk-preset-active');
            }
        });

        if (typeof app.loadBreakoutRadar === 'function') {
            app.loadBreakoutRadar();
        }
    };

    app.setBreakoutDatePreset = function(daysAgo) {
        const dateInput = document.getElementById('breakoutDateInput');
        if (daysAgo === 0) {
            if (dateInput) dateInput.value = '';
            app._breakoutAsofDate = null;
        } else {
            const d = new Date();
            d.setDate(d.getDate() - daysAgo);
            const iso = d.toISOString().split('T')[0];
            if (dateInput) dateInput.value = iso;
            app._breakoutAsofDate = iso;
        }

        document.querySelectorAll('.bk-preset-btn').forEach(btn => {
            const btnDays = parseInt(btn.getAttribute('data-days'), 10);
            if (btnDays === daysAgo) {
                btn.classList.add('bk-preset-active');
            } else {
                btn.classList.remove('bk-preset-active');
            }
        });

        if (typeof app.loadBreakoutRadar === 'function') {
            app.loadBreakoutRadar();
        }
    };

    app.setBreakoutLiveInterval = function(ms) {
        app.breakoutLiveIntervalMs = parseInt(ms, 10) || 300000;
        localStorage.setItem('nexus_breakout_refresh_interval', app.breakoutLiveIntervalMs);
        app.updateBreakoutLiveButtonUI();
        if (app.breakoutLiveTracking) {
            if (app.breakoutLiveIntervalTimer) clearInterval(app.breakoutLiveIntervalTimer);
            app.breakoutLiveIntervalTimer = setInterval(() => {
                if (app.breakoutLiveTracking && typeof app.loadBreakoutRadar === 'function') {
                    app.loadBreakoutRadar(true, true);
                }
            }, app.breakoutLiveIntervalMs);
        }
    };

    app.toggleBreakoutLiveTracking = function() {
        app.breakoutLiveTracking = !app.breakoutLiveTracking;
        app.breakoutLiveIntervalMs = parseInt(localStorage.getItem('nexus_breakout_refresh_interval') || '300000', 10);

        const sel = document.getElementById('breakoutLiveIntervalSelect');
        if (sel) sel.value = String(app.breakoutLiveIntervalMs);

        app.updateBreakoutLiveButtonUI();

        if (app.breakoutLiveTracking) {
            if (typeof app.loadBreakoutRadar === 'function') app.loadBreakoutRadar(true);
            if (app.breakoutLiveIntervalTimer) clearInterval(app.breakoutLiveIntervalTimer);
            app.breakoutLiveIntervalTimer = setInterval(() => {
                if (app.breakoutLiveTracking && typeof app.loadBreakoutRadar === 'function') {
                    app.loadBreakoutRadar(true, true);
                }
            }, app.breakoutLiveIntervalMs);
        } else {
            if (app.breakoutLiveIntervalTimer) {
                clearInterval(app.breakoutLiveIntervalTimer);
                app.breakoutLiveIntervalTimer = null;
            }
        }
    };

    app.fetchLiveBreakoutQuotes = async function() {
        const fetchBtn = document.getElementById('breakoutFetchLiveBtn');
        if (fetchBtn) {
            fetchBtn.disabled = true;
            fetchBtn.innerHTML = '⏳ Fetching...';
        }
        try {
            if (typeof app.loadBreakoutRadar === 'function') {
                await app.loadBreakoutRadar(true);
            }
        } finally {
            if (fetchBtn) {
                fetchBtn.disabled = false;
                fetchBtn.innerHTML = '⚡ Refresh Live';
            }
        }
    };

    app.updateBreakoutLiveButtonUI = function() {
        const btn = document.getElementById('breakoutLiveToggleBtn');
        const text = document.getElementById('breakoutLiveBtnText');
        const ind = document.getElementById('breakoutLiveIndicator');
        if (!btn || !text || !ind) return;

        const intLabel = app.breakoutLiveIntervalMs >= 60000
            ? `${Math.round(app.breakoutLiveIntervalMs / 60000)}m`
            : `${Math.round(app.breakoutLiveIntervalMs / 1000)}s`;

        if (app.breakoutLiveTracking) {
            btn.style.background = '#18181b';
            btn.style.color = '#34d399';
            btn.style.borderColor = 'rgba(52, 211, 153, 0.4)';
            text.textContent = `🟢 Live (${intLabel})`;
            ind.style.background = '#34d399';
            ind.style.boxShadow = 'none';
        } else {
            btn.style.background = '#18181b';
            btn.style.color = '#a1a1aa';
            btn.style.borderColor = 'rgba(255, 255, 255, 0.15)';
            text.textContent = '⏱️ Track Live Prices';
            ind.style.background = '#71717a';
            ind.style.boxShadow = 'none';
        }
    };

    app.startBreakoutPolling = function(maxAttempts = 30, intervalMs = 3000) {
        if (app._breakoutPollTimer) clearInterval(app._breakoutPollTimer);
        let attempts = 0;
        const notice = document.getElementById('breakoutFilterNotice');
        if (notice) {
            notice.style.display = 'inline-flex';
            notice.innerHTML = `<span>⏳</span> Background scan in progress... polling for fresh setups <button type="button" onclick="app.stopBreakoutPolling(); event.stopPropagation();" style="margin-left:0.45rem;background:#18181b;border:1px solid rgba(255,255,255,0.25);color:#f4f4f5;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">Cancel</button>`;
        }

        app._breakoutPollTimer = setInterval(async () => {
            attempts++;
            try {
                const res = await fetch(API_BASE + '/api/v1/breakout-radar/refresh/status');
                if (res.ok) {
                    const status = await res.json();
                    if (!status.is_running) {
                        clearInterval(app._breakoutPollTimer);
                        app._breakoutPollTimer = null;
                        if (typeof app.loadBreakoutRadar === 'function') await app.loadBreakoutRadar(false);
                        if (typeof app.loadBreakoutAuditLog === 'function') await app.loadBreakoutAuditLog();
                        if (typeof app.loadBreakoutSchedules === 'function') await app.loadBreakoutSchedules();
                        if (notice) {
                            notice.style.display = 'inline-flex';
                            notice.innerHTML = `✅ <strong>Background scan finished</strong> · Database refreshed with latest setups! <button type="button" onclick="this.parentElement.style.display='none'; event.stopPropagation();" style="margin-left:0.45rem;background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.25);color:#cbd5e1;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">✕</button>`;
                            setTimeout(() => { if (notice && !app._breakoutFilterBreakingOut && !app._breakoutRealTrackedOnly) notice.style.display = 'none'; }, 6000);
                        }
                        return;
                    }
                }
                if (attempts % 2 === 0 && typeof app.loadBreakoutRadar === 'function') {
                    await app.loadBreakoutRadar(true);
                }
            } catch (e) {
                console.debug('[BREAKOUT-POLL] Status error:', e);
            }

            if (attempts >= maxAttempts) {
                clearInterval(app._breakoutPollTimer);
                app._breakoutPollTimer = null;
                if (typeof app.loadBreakoutRadar === 'function') await app.loadBreakoutRadar(false);
                if (notice && !app._breakoutFilterBreakingOut && !app._breakoutRealTrackedOnly) {
                    notice.style.display = 'none';
                }
            }
        }, intervalMs);
    };

    app.stopBreakoutPolling = function() {
        if (app._breakoutPollTimer) {
            clearInterval(app._breakoutPollTimer);
            app._breakoutPollTimer = null;
        }
        const notice = document.getElementById('breakoutFilterNotice');
        if (notice && !app._breakoutFilterBreakingOut && !app._breakoutRealTrackedOnly) {
            notice.style.display = 'none';
        }
    };

    app.refreshBreakoutScan = async function() {
        const btn = document.getElementById('breakoutRefreshBtn');
        const icon = document.getElementById('breakoutRefreshIcon');
        const universe = document.getElementById('breakoutUniverseSelect')?.value || 'nse_large_cap';
        const strategy = document.getElementById('breakoutStrategySelect')?.value || app._breakoutStrategy || 'ALL';
        if (btn) btn.disabled = true;
        if (icon) icon.textContent = '⏱️';
        try {
            const res = await fetch(API_BASE + '/api/v1/breakout-radar/refresh?universe=' + encodeURIComponent(universe) + '&strategy=' + encodeURIComponent(strategy), { method: 'POST' });
            const data = await res.json();
            console.log('[BREAKOUT] Schedule response:', data);
            app.startBreakoutPolling();
        } catch (e) {
            console.error('[BREAKOUT] Refresh error:', e);
        } finally {
            setTimeout(() => {
                if (btn) btn.disabled = false;
                if (icon) icon.textContent = '⏱️';
            }, 3000);
        }
    };

    app.runAdhocBreakoutBacktest = async function() {
        const btn = document.getElementById('btnRunBreakoutBacktest');
        const modal = document.getElementById('breakoutBacktestModal');
        const content = document.getElementById('breakoutBacktestModalContent');
        if (!btn || !modal || !content) return;

        const universe = document.getElementById('breakoutUniverseSelect')?.value || 'nifty_50';
        const universeLabel = universe === 'nifty_50' ? 'Nifty 50' : (universe === 'all' ? 'All Monitored' : universe);

        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span> Auditing...';

        content.innerHTML = `
            <div style="text-align:center;padding:3rem 2rem;">
                <div style="font-size:2rem;margin-bottom:1rem;animation:spin 2s linear infinite;display:inline-block;">🔬</div>
                <div style="font-size:1.1rem;font-weight:700;color:#f8fafc;margin-bottom:0.4rem;">Running Historical Breakout Backtest Audit</div>
                <div style="font-size:0.75rem;color:#94a3b8;font-family:var(--font-mono);margin-bottom:1.5rem;">Scanning ${universeLabel} over the last 90, 75, 60, 45, and 30 days...</div>
                <div style="max-width:320px;margin:0 auto;background:rgba(255,255,255,0.06);height:6px;border-radius:10px;overflow:hidden;position:relative;">
                    <div style="background:linear-gradient(90deg, #0284c7, #38bdf8);height:100%;width:65%;position:absolute;left:0;top:0;border-radius:10px;"></div>
                </div>
                <p style="font-size:0.7rem;color:#64748b;margin-top:1rem;line-height:1.45;">Stand by while we crunch technical proximity, price compression, volume surges, and earnings quality factors against subsequent realized outcomes.</p>
            </div>
        `;
        modal.style.display = 'flex';

        try {
            const res = await fetch(API_BASE + '/api/v1/breakout-radar/backtest?universe=' + encodeURIComponent(universe));
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();

            if (!data.success) {
                throw new Error(data.error || 'Backtest failed');
            }

            const wr = data.win_rate_pct || 0;
            const duration = data.duration_s || 0;
            const es = data.effect_sizes || {};
            const th = data.score_thresholds || {};
            const vth = data.volume_thresholds || {};

            const sortedEs = Object.entries(es).sort((a, b) => b[1].effect_size - a[1].effect_size);

            const esRows = sortedEs.map(([col, info]) => {
                const val = info.effect_size;
                const importance = val >= 0.8 ? '🔴 HIGH' : (val >= 0.5 ? '🟡 MEDIUM' : (val >= 0.3 ? '🟢 MODERATE' : '⚪ LOW'));
                const impBg = val >= 0.8 ? 'rgba(239,68,68,0.15)' : (val >= 0.5 ? 'rgba(245,158,11,0.15)' : (val >= 0.3 ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.1)'));
                const impText = val >= 0.8 ? '#f87171' : (val >= 0.5 ? '#fbbf24' : (val >= 0.3 ? '#34d399' : '#94a3b8'));

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:0.45rem 0.6rem;font-weight:600;color:#f1f5f9;">${info.label}</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);">${info.mean_breakout}</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);">${info.mean_failed}</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);color:${info.delta >= 0 ? '#34d399' : '#f87171'};">${info.delta >= 0 ? '+' : ''}${info.delta}</td>
                        <td style="padding:0.45rem 0.6rem;text-align:right;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${val.toFixed(3)}</td>
                        <td style="padding:0.45rem 0.6rem;text-align:center;">
                            <span style="background:${impBg};color:${impText};padding:0.1rem 0.4rem;border-radius:4px;font-size:0.62rem;font-weight:700;">${importance}</span>
                        </td>
                    </tr>
                `;
            }).join('');

            const thRows = Object.entries(th).map(([score, info]) => `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                    <td style="padding:0.4rem 0.6rem;font-weight:600;color:#cbd5e1;">Score &ge; ${score}</td>
                    <td style="padding:0.4rem 0.6rem;text-align:center;font-family:var(--font-mono);">${info.count}</td>
                    <td style="padding:0.4rem 0.6rem;text-align:center;font-family:var(--font-mono);color:#34d399;font-weight:700;">${info.broke_count}</td>
                    <td style="padding:0.4rem 0.6rem;text-align:right;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">${info.win_rate_pct}%</td>
                </tr>
            `).join('');

            const vthRows = Object.entries(vth).map(([vol, info]) => `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                    <td style="padding:0.4rem 0.6rem;font-weight:600;color:#cbd5e1;">Volume &ge; ${vol}</td>
                    <td style="padding:0.4rem 0.6rem;text-align:center;font-family:var(--font-mono);">${info.count}</td>
                    <td style="padding:0.4rem 0.6rem;text-align:center;font-family:var(--font-mono);color:#34d399;font-weight:700;">${info.broke_count}</td>
                    <td style="padding:0.4rem 0.6rem;text-align:right;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">${info.win_rate_pct}%</td>
                </tr>
            `).join('');

            content.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.85rem;margin-bottom:1rem;">
                    <div style="display:flex;align-items:center;gap:0.6rem;">
                        <span style="font-size:1.5rem;">🔬</span>
                        <div>
                            <div style="font-size:1.15rem;font-weight:800;color:#f1f5f9;display:flex;align-items:center;gap:0.45rem;">
                                <span>Historical Backtest Audit Report</span>
                                <span style="font-size:0.68rem;background:rgba(56,189,248,0.15);color:#38bdf8;padding:0.15rem 0.45rem;border-radius:4px;font-weight:700;">ADHOC RUN</span>
                            </div>
                            <div style="font-size:0.74rem;color:#94a3b8;font-family:var(--font-mono);">Universe: ${universeLabel} &bull; 5 Periods (30d to 90d ago) &bull; Calc in ${duration}s</div>
                        </div>
                    </div>
                </div>

                <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:0.65rem;margin-bottom:1.25rem;">
                    <div class="card" style="padding:0.75rem 0.95rem;background:#061a14;border:1px solid rgba(52,211,153,0.25);border-top:2px solid #34d399;">
                        <div style="font-size:0.65rem;color:#34d399;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Win Rate %</div>
                        <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">${wr}%</div>
                        <div style="font-size:0.68rem;color:#86efac;margin-top:0.15rem;">${data.success_count} succeeded / ${data.total_evaluated} evaluated</div>
                    </div>
                    <div class="card" style="padding:0.75rem 0.95rem;background:#09090b;border:1px solid rgba(255,255,255,0.08);border-top:2px solid #38bdf8;">
                        <div style="font-size:0.65rem;color:#38bdf8;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Avg Return (All)</div>
                        <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">${data.avg_return_pct >= 0 ? '+' : ''}${data.avg_return_pct}%</div>
                        <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.15rem;">Across all evaluated setups</div>
                    </div>
                    <div class="card" style="padding:0.75rem 0.95rem;background:#061a14;border:1px solid rgba(52,211,153,0.25);border-top:2px solid #34d399;">
                        <div style="font-size:0.65rem;color:#34d399;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Avg Breakout Return</div>
                        <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">+${data.avg_broke_return_pct}%</div>
                        <div style="font-size:0.68rem;color:#a7f3d0;margin-top:0.15rem;">For successful breakouts</div>
                    </div>
                    <div class="card" style="padding:0.75rem 0.95rem;background:#1a0808;border:1px solid rgba(248,113,113,0.25);border-top:2px solid #f87171;">
                        <div style="font-size:0.65rem;color:#f87171;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Avg Failed Return</div>
                        <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">${data.avg_failed_return_pct}%</div>
                        <div style="font-size:0.68rem;color:#fca5a5;margin-top:0.15rem;">For setups that failed to breakout</div>
                    </div>
                </div>

                <div style="display:grid;grid-template-columns:1.3fr 1fr;gap:1rem;margin-bottom:1rem;align-items:start;">
                    <div class="card" style="padding:0.85rem 1rem;background:#080d16;border:1px solid rgba(255,255,255,0.08);">
                        <div style="font-size:0.82rem;font-weight:700;color:#38bdf8;margin-bottom:0.6rem;">🔬 Factor Predictive Power (Cohen's d)</div>
                        <table style="width:100%;border-collapse:collapse;font-size:0.72rem;text-align:left;">
                            <thead>
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.12);color:#94a3b8;font-weight:600;">
                                    <th style="padding:0.4rem 0.6rem;">Scoring Factor</th>
                                    <th style="padding:0.4rem 0.6rem;text-align:right;">B-Out Avg</th>
                                    <th style="padding:0.4rem 0.6rem;text-align:right;">Fail Avg</th>
                                    <th style="padding:0.4rem 0.6rem;text-align:right;">Delta</th>
                                    <th style="padding:0.4rem 0.6rem;text-align:right;">Effect Size</th>
                                    <th style="padding:0.4rem 0.6rem;text-align:center;">Power</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${esRows}
                            </tbody>
                        </table>
                    </div>

                    <div style="display:flex;flex-direction:column;gap:0.75rem;">
                        <div class="card" style="padding:0.85rem 1rem;background:#080d16;border:1px solid rgba(255,255,255,0.08);">
                            <div style="font-size:0.82rem;font-weight:700;color:#fbbf24;margin-bottom:0.6rem;">🎯 Win Rate by Score Threshold</div>
                            <table style="width:100%;border-collapse:collapse;font-size:0.72rem;text-align:left;">
                                <thead>
                                    <tr style="border-bottom:1px solid rgba(255,255,255,0.12);color:#94a3b8;font-weight:600;">
                                        <th style="padding:0.4rem 0.6rem;">Min Score Threshold</th>
                                        <th style="padding:0.4rem 0.6rem;text-align:center;">Candidates</th>
                                        <th style="padding:0.4rem 0.6rem;text-align:center;">B-Outs</th>
                                        <th style="padding:0.4rem 0.6rem;text-align:right;">Win Rate %</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${thRows}
                                </tbody>
                            </table>
                        </div>

                        <div class="card" style="padding:0.85rem 1rem;background:#080d16;border:1px solid rgba(255,255,255,0.08);">
                            <div style="font-size:0.82rem;font-weight:700;color:#fb923c;margin-bottom:0.6rem;">📊 Win Rate by Volume Surge Ratio</div>
                            <table style="width:100%;border-collapse:collapse;font-size:0.72rem;text-align:left;">
                                <thead>
                                    <tr style="border-bottom:1px solid rgba(255,255,255,0.12);color:#94a3b8;font-weight:600;">
                                        <th style="padding:0.4rem 0.6rem;">Volume Ratio</th>
                                        <th style="padding:0.4rem 0.6rem;text-align:center;">Candidates</th>
                                        <th style="padding:0.4rem 0.6rem;text-align:center;">B-Outs</th>
                                        <th style="padding:0.4rem 0.6rem;text-align:right;">Win Rate %</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${vthRows}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <div style="display:flex;align-items:center;justify-content:space-between;padding-top:0.75rem;border-top:1px solid rgba(255,255,255,0.08);">
                    <div style="font-size:0.68rem;color:#64748b;">
                        * Outcome definitions: Target Hit = high &ge; target_price; Stop Loss Hit = low &le; stop_loss.
                    </div>
                    <button type="button" onclick="document.getElementById('breakoutBacktestModal').style.display='none'" class="btn btn-sm btn-secondary" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);padding:0.35rem 1rem;border-radius:6px;font-size:0.75rem;cursor:pointer;">
                        Close Audit Report
                    </button>
                </div>
            `;
        } catch (err) {
            console.error('[BREAKOUT-BACKTEST] Backtest run failed:', err);
            content.innerHTML = `
                <div style="text-align:center;padding:3rem 1.5rem;color:#f87171;">
                    <div style="font-size:2.5rem;margin-bottom:1rem;">⚠️</div>
                    <div style="font-size:1.05rem;font-weight:700;margin-bottom:0.5rem;">Historical Backtest Audit Failed</div>
                    <p style="font-size:0.78rem;color:#cbd5e1;max-width:420px;margin:0 auto 1.5rem;">${err.message || 'An error occurred while communicating with the backtest server.'}</p>
                    <button type="button" onclick="document.getElementById('breakoutBacktestModal').style.display='none'" class="btn btn-sm" style="background:#1e293b;color:#fff;border:1px solid rgba(255,255,255,0.1);padding:0.4rem 1rem;border-radius:6px;">Close</button>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '🔬 Run Backtest Audit';
        }
    };
})();
