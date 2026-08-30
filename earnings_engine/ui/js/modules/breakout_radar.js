// =========================================================================
// breakout_radar — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
// =========================================================================
        // ⚡ BREAKOUT RADAR MODULE (ENHANCED WITH DATE PICKER & OUTCOME TRACKING)
        // =========================================================================
        app._breakoutLoaded = false;
        app._breakoutPollTimer = null;
        app._breakoutData = [];
        app._breakoutSortKey = 'composite_score';
        app._breakoutSortAsc = false;
        app._breakoutAsofDate = null;
        app._breakoutFilterBreakingOut = false;

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

        app.toggleBreakingOutFilter = function() {
            app._breakoutFilterBreakingOut = !app._breakoutFilterBreakingOut;
            app.applyBreakoutFilterAndRender();
        };

        app.clearBreakoutFilter = function() {
            app._breakoutFilterBreakingOut = false;
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
            const activeNotice = document.getElementById('breakoutFilterNotice');
            const filterIndicator = document.getElementById('breakoutFilterIndicator');
            const breakingSub = document.getElementById('breakoutStatBreakingSub');

            let list = app._breakoutData || [];
            const breakingCount = list.filter(app.isItemBreaking).length;

            if (app._breakoutRealTrackedOnly) {
                list = list.filter(item => Boolean(item.is_real_tracked));
            }

            if (app._breakoutFilterBreakingOut) {
                list = list.filter(app.isItemBreaking);
                if (fireCard) {
                    fireCard.style.outline = '2px solid #f97316';
                    fireCard.style.boxShadow = '0 0 20px rgba(249,115,22,0.5)';
                    fireCard.style.background = '#1e1610';
                }
                if (totalCard) {
                    totalCard.style.opacity = '0.75';
                }
                if (filterIndicator) {
                    filterIndicator.style.display = 'inline-block';
                }
                if (breakingSub) {
                    breakingSub.textContent = 'Filtered 🔍';
                }
                if (activeNotice) {
                    activeNotice.style.display = 'inline-flex';
                    activeNotice.innerHTML = `🔥 Filtering: <strong>Breaking Out Only (${list.length} setup${list.length === 1 ? '' : 's'})</strong> <button type="button" onclick="app.clearBreakoutFilter(); event.stopPropagation();" style="margin-left:0.45rem;background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.25);color:#fdba74;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">✕ Show All (${app._breakoutData.length})</button>`;
                }
            } else if (app._breakoutRealTrackedOnly) {
                if (activeNotice) {
                    activeNotice.style.display = 'inline-flex';
                    activeNotice.innerHTML = `🟢 Filtering: <strong>Real Tracked Entries Only (${list.length} setup${list.length === 1 ? '' : 's'})</strong> <button type="button" onclick="app.clearBreakoutRealTrackedFilter(); event.stopPropagation();" style="margin-left:0.45rem;background:rgba(16,185,129,0.2);border:1px solid rgba(16,185,129,0.4);color:#34d399;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">✕ Show All (${app._breakoutData.length})</button>`;
                }
            } else {
                if (fireCard) {
                    fireCard.style.outline = '';
                    fireCard.style.boxShadow = '';
                    fireCard.style.background = '#0f172a';
                }
                if (totalCard) {
                    totalCard.style.opacity = '1';
                }
                if (filterIndicator) {
                    filterIndicator.style.display = 'none';
                }
                if (breakingSub) {
                    breakingSub.textContent = (app._breakoutAsofDate ? 'Fired' : (breakingCount > 0 ? 'Breached' : 'Active'));
                }
                if (activeNotice) {
                    activeNotice.style.display = 'none';
                }
            }

            const limitVal = document.getElementById('breakoutLimitSelect')?.value || '10';
            const limitNum = limitVal === 'all' ? list.length : parseInt(limitVal, 10);
            app.renderBreakoutTable(list.slice(0, limitNum), app._breakoutAsofDate);
        };

        app.toggleBreakoutExplainer = function() {
            const card = document.getElementById('breakoutExplainerCard');
            if (!card) return;
            card.style.display = card.style.display === 'none' ? 'block' : 'none';
        };

        app.onBreakoutUniverseChange = function(uni) {
            app.loadBreakoutRadar();
        };

        app.onBreakoutDateChange = function(dateStr) {
            app._breakoutAsofDate = dateStr && dateStr.trim() !== '' ? dateStr.trim() : null;
            
            // Highlight the matching preset button (if any) or clear highlight
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

            app.loadBreakoutRadar();
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
            
            // Update button visual active state
            document.querySelectorAll('.bk-preset-btn').forEach(btn => {
                const btnDays = parseInt(btn.getAttribute('data-days'), 10);
                if (btnDays === daysAgo) {
                    btn.classList.add('bk-preset-active');
                } else {
                    btn.classList.remove('bk-preset-active');
                }
            });

            app.loadBreakoutRadar();
        };

        app.breakoutLiveTracking = false;
        app.breakoutLiveIntervalTimer = null;
        app.breakoutLiveIntervalMs = parseInt(localStorage.getItem('nexus_breakout_refresh_interval') || '300000', 10);

        app.setBreakoutLiveInterval = function(ms) {
            app.breakoutLiveIntervalMs = parseInt(ms, 10) || 300000;
            localStorage.setItem('nexus_breakout_refresh_interval', app.breakoutLiveIntervalMs);
            app.updateBreakoutLiveButtonUI();
            if (app.breakoutLiveTracking) {
                if (app.breakoutLiveIntervalTimer) clearInterval(app.breakoutLiveIntervalTimer);
                app.breakoutLiveIntervalTimer = setInterval(() => {
                    if (app.breakoutLiveTracking) {
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
                app.loadBreakoutRadar(true);
                if (app.breakoutLiveIntervalTimer) clearInterval(app.breakoutLiveIntervalTimer);
                app.breakoutLiveIntervalTimer = setInterval(() => {
                    if (app.breakoutLiveTracking) {
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
                await app.loadBreakoutRadar(true);
            } finally {
                if (fetchBtn) {
                    fetchBtn.disabled = false;
                    fetchBtn.innerHTML = '⚡ Refresh Live';
                }
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

            // Show loading modal immediately
            content.innerHTML = `
                <div style="text-align:center;padding:3rem 2rem;">
                    <div style="font-size:2rem;margin-bottom:1rem;animation:spin 2s linear infinite;display:inline-block;">🔬</div>
                    <div style="font-size:1.1rem;font-weight:700;color:#f8fafc;margin-bottom:0.4rem;">Running Historical Breakout Backtest Audit</div>
                    <div style="font-size:0.75rem;color:#94a3b8;font-family:var(--font-mono);margin-bottom:1.5rem;">Scanning ${universeLabel} over the last 90, 75, 60, 45, and 30 days...</div>
                    <div style="max-width:320px;margin:0 auto;background:rgba(255,255,255,0.06);height:6px;border-radius:10px;overflow:hidden;position:relative;">
                        <div style="background:#38bdf8;height:100%;width:50%;position:absolute;left:0;top:0;animation:breakoutPulse 1.2s ease-in-out infinite;"></div>
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

                // Render metrics report
                const wr = data.win_rate_pct || 0;
                const total = data.total_candidates || 0;
                const evaluated = data.total_evaluated || 0;
                const duration = data.duration_s || 0;
                const outcomes = data.outcomes || {};
                const es = data.effect_sizes || {};
                const th = data.score_thresholds || {};
                const vth = data.volume_thresholds || {};

                // Sort effect sizes by value
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
                    <!-- Header -->
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

                    <!-- KPI Summary Cards -->
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:0.65rem;margin-bottom:1.25rem;">
                        <div class="card" style="padding:0.75rem 0.95rem;background:#052e16;border:1px solid rgba(34,197,94,0.3);border-top:2px solid #22c55e;">
                            <div style="font-size:0.65rem;color:#4ade80;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Win Rate %</div>
                            <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">${wr}%</div>
                            <div style="font-size:0.68rem;color:#86efac;margin-top:0.15rem;">${data.success_count} succeeded / ${data.total_evaluated} evaluated</div>
                        </div>
                        <div class="card" style="padding:0.75rem 0.95rem;background:#090d16;border:1px solid rgba(255,255,255,0.1);border-top:2px solid #38bdf8;">
                            <div style="font-size:0.65rem;color:#38bdf8;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Avg Return (All)</div>
                            <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">${data.avg_return_pct >= 0 ? '+' : ''}${data.avg_return_pct}%</div>
                            <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.15rem;">Across all evaluated setups</div>
                        </div>
                        <div class="card" style="padding:0.75rem 0.95rem;background:#064e3b;border:1px solid rgba(16,185,129,0.3);border-top:2px solid #10b981;">
                            <div style="font-size:0.65rem;color:#34d399;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Avg Breakout Return</div>
                            <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">+${data.avg_broke_return_pct}%</div>
                            <div style="font-size:0.68rem;color:#a7f3d0;margin-top:0.15rem;">For successful breakouts</div>
                        </div>
                        <div class="card" style="padding:0.75rem 0.95rem;background:#450a0a;border:1px solid rgba(239,68,68,0.3);border-top:2px solid #ef4444;">
                            <div style="font-size:0.65rem;color:#f87171;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.25rem;">Avg Failed Return</div>
                            <div style="font-size:1.8rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">${data.avg_failed_return_pct}%</div>
                            <div style="font-size:0.68rem;color:#fca5a5;margin-top:0.15rem;">For setups that failed to breakout</div>
                        </div>
                    </div>

                    <!-- Two-column Tables: Effect Sizes & Thresholds -->
                    <div style="display:grid;grid-template-columns:1.3fr 1fr;gap:1rem;margin-bottom:1rem;align-items:start;">
                        <!-- Factor Discriminative Power (Cohen's d) -->
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
                            <div style="font-size:0.62rem;color:#64748b;margin-top:0.6rem;line-height:1.45;">
                                * Cohen's d measures the standard deviation distance between breakout success vs failed means. Value &ge; 0.8 implies high predictive discrimination.
                            </div>
                        </div>

                        <!-- Threshold Analysis -->
                        <div style="display:flex;flex-direction:column;gap:0.75rem;">
                            <!-- Score Threshold Win Rates -->
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

                            <!-- Volume Ratio Threshold Win Rates -->
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

                    <!-- Footer Action -->
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

        app.updateBreakoutLiveButtonUI = function() {
            const btn = document.getElementById('breakoutLiveToggleBtn');
            const text = document.getElementById('breakoutLiveBtnText');
            const ind = document.getElementById('breakoutLiveIndicator');
            if (!btn || !text || !ind) return;

            const intLabel = app.breakoutLiveIntervalMs >= 60000
                ? `${Math.round(app.breakoutLiveIntervalMs / 60000)}m`
                : `${Math.round(app.breakoutLiveIntervalMs / 1000)}s`;

            if (app.breakoutLiveTracking) {
                btn.style.background = 'rgba(16, 185, 129, 0.2)';
                btn.style.color = '#34d399';
                btn.style.borderColor = 'rgba(16, 185, 129, 0.5)';
                text.textContent = `🟢 Live (${intLabel})`;
                ind.style.background = '#34d399';
                ind.style.boxShadow = '0 0 6px #34d399';
            } else {
                btn.style.background = 'rgba(239, 68, 68, 0.12)';
                btn.style.color = '#f87171';
                btn.style.borderColor = 'rgba(239, 68, 68, 0.35)';
                text.textContent = '🔴 Track Live Prices';
                ind.style.background = '#f87171';
                ind.style.boxShadow = 'none';
            }
        };

        app._breakoutStrategy = 'CLASSIC_TECHNICAL';
        app.onBreakoutStrategyChange = function(strategy) {
            app._breakoutStrategy = strategy || 'CLASSIC_TECHNICAL';
            app.loadBreakoutRadar();
        };

        app.loadBreakoutRadar = async function(forceLive = false, silent = false) {
            if (!app._breakoutAutocompleteWired) {
                app.wireBreakoutStockAutocomplete();
                app._breakoutAutocompleteWired = true;
            }

            const badge = document.getElementById('breakoutScanningBadge');
            const lastScanEl = document.getElementById('breakoutLastScanTime');
            const modeBadge = document.getElementById('breakoutModeBadge');
            const histNotice = document.getElementById('breakoutHistoricalNotice');
            const tbody = document.getElementById('breakoutTableBody');
            if (badge && !silent) badge.style.display = 'inline-block';

            const universe = document.getElementById('breakoutUniverseSelect')?.value || 'all';
            const strategy = document.getElementById('breakoutStrategySelect')?.value || app._breakoutStrategy || 'CLASSIC_TECHNICAL';
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
                const params = new URLSearchParams({ universe: universe, strategy: strategy, sort_by: sortBy, min_score: minScore, limit: 100 });
                if (asofDate) {
                    params.set('asof_date', asofDate);
                }
                if (forceLive || app.breakoutLiveTracking) {
                    params.set('live', 'true');
                }
                const res = await fetch(API_BASE + '/api/v1/breakout-radar?' + params.toString());
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();

                app._breakoutData = data.candidates || [];
                const status = data.scan_status || {};
                const summary = data.backtest_summary || {};
                const total = app._breakoutData.length;
                const topCandidate = total > 0 ? app._breakoutData[0] : null;
                const avgScore = total > 0
                    ? (app._breakoutData.reduce((s, c) => s + (c.composite_score || 0), 0) / total).toFixed(1)
                    : '\u2014';

                const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
                
                // Update KPI Cards
                setEl('breakoutStatTotal', total);

                // Calculate breaking out count across all candidates
                const isItemBreaking = (item) => {
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
                const breakingCount = (app._breakoutData || []).filter(isItemBreaking).length;
                const fireCard = document.getElementById('breakoutCardOnFire');

                if (asofDate && summary && summary.total_evaluated != null) {
                    // Backtest Mode KPIs (Breakouts Fired vs Coiling)
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
                        setEl('breakoutKpiSubFire', `🔥 ${breakingCount} setup(s) crossed trigger!`);
                    } else {
                        if (fireCard) fireCard.classList.remove('card-on-fire');
                        setEl('breakoutStatBreakingSub', 'Active');
                        setEl('breakoutKpiSubFire', 'All setups coiling below trigger');
                    }

                    // Live Mode KPIs
                    setEl('breakoutKpiLabel2', 'Top Score');
                    setEl('breakoutStatTopScore', topCandidate ? topCandidate.composite_score : '\u2014');
                    setEl('breakoutStatTopTicker', topCandidate ? (topCandidate.ticker || '\u2014') : '\u2014');

                    setEl('breakoutKpiLabel3', 'Avg Score');
                    setEl('breakoutStatAvg', avgScore);
                    setEl('breakoutKpiSub3', 'Composite Average');

                    setEl('breakoutKpiLabel5', 'Scan Duration');
                    setEl('breakoutStatDuration', status.last_scan_duration_s != null ? `${status.last_scan_duration_s}s` : '\u2014');
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
                            lastScanEl.textContent = `${uniLabel} • Active Setup Pool`;
                        }
                    } else if (total > 0) {
                        lastScanEl.textContent = `${uniLabel} • Active Setup Pool (${total} setups)`;
                    } else if (status.status === 'running') {
                        lastScanEl.textContent = `${uniLabel} • Scanning now…`;
                    } else {
                        lastScanEl.textContent = `${uniLabel} • Active Setup Pool`;
                    }
                }

                app.applyBreakoutFilterAndRender();
            } catch (err) {
                console.error('[BREAKOUT] Load error:', err);
                if (tbody && !silent) tbody.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#ef4444;font-size:0.8rem;">\u26a1 Failed to load breakout data. Is the server running?</td></tr>';
            } finally {
                if (badge) badge.style.display = 'none';
            }
        };

        const DEFAULT_BREAKOUT_COLS = ['stock', 'signal_price', 'current_price', 'trigger', 'target_stop', 'return', 'outcome', 'score', 'actions'];

        const BREAKOUT_COLUMNS = {
            stock: {
                id: 'stock',
                label: 'Stock & Quality',
                sortKey: 'ticker',
                align: 'left',
                headerStyle: 'color:#94a3b8;',
                render: (c, ctx) => `
                    <td style="padding:0.46rem 0.65rem;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="display:flex;flex-direction:column;gap:0.12rem;">
                            <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:nowrap;">
                                <a href="/stock/${encodeURIComponent(ctx.ticker)}" target="_blank" style="font-weight:800;color:#ffffff;font-family:var(--font-mono);font-size:0.82rem;text-decoration:none;letter-spacing:-0.01em;" title="Open ${ctx.ticker} stock intelligence in new tab" onmouseenter="this.style.color='#38bdf8'" onmouseleave="this.style.color='#ffffff'">${ctx.ticker}</a>
                                <a href="/stock/${encodeURIComponent(ctx.ticker)}" target="_blank" style="color:#38bdf8;text-decoration:none;font-size:0.7rem;opacity:0.8;" onclick="event.stopPropagation();" title="Open profile in new tab">↗</a>
                                ${c.confirmation_badge ? `
                                    <span style="font-size:0.58rem;background:rgba(255,255,255,0.05);color:${c.confirmation_color || '#38bdf8'};border:1px solid ${c.confirmation_color || '#38bdf8'}40;padding:0.04rem 0.35rem;border-radius:3px;font-weight:800;display:inline-flex;align-items:center;gap:0.2rem;" title="Volume expansion and fakeout protection indicator">
                                        ${c.confirmation_badge}
                                    </span>
                                ` : (ctx.isBreakingOut ? `
                                    <span style="font-size:0.58rem;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:0.04rem 0.35rem;border-radius:3px;font-weight:800;display:inline-flex;align-items:center;gap:0.2rem;" title="Price crossed above resistance trigger">
                                        🚀 Resistance Breached
                                    </span>
                                ` : '')}
                            </div>
                            <div style="font-size:0.67rem;color:#94a3b8;max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${c.company_name || ctx.ticker}">${ctx.company}</div>
                            <div style="margin-top:0.1rem;display:flex;gap:0.25rem;flex-wrap:wrap;align-items:center;">
                                <span style="font-size:0.60rem;background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.25);padding:0.04rem 0.32rem;border-radius:3px;font-weight:600;">${ctx.archetype}</span>
                                ${c.strategy ? `<span style="font-size:0.60rem;background:rgba(168,85,247,0.15);color:#c084fc;border:1px solid rgba(168,85,247,0.3);padding:0.04rem 0.32rem;border-radius:3px;font-weight:700;" title="Strategy Model: ${c.strategy}">🎯 ${String(c.strategy).replace(/_/g, ' ')}</span>` : ''}
                                <button type="button" onclick="app.openBreakoutHistoryModal('${ctx.ticker}', event)" style="background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:0.04rem 0.32rem;border-radius:3px;font-size:0.60rem;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:0.2rem;" title="View Transition Lifecycle & Notes Timeline (Warm ➔ Hot ➔ Breakout)">
                                    📜 History
                                </button>
                                ${(c.institutional_flow && c.institutional_flow.funds_in > 0) ? `<span style="font-size:0.60rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);padding:0.04rem 0.3rem;border-radius:3px;font-weight:700;" title="Institutional Accumulation: +${c.institutional_flow.funds_in} Funds Buying">🏛️ +${c.institutional_flow.funds_in}</span>` : ''}
                                ${c.is_real_tracked ? `
                                    <span style="font-size:0.60rem;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);padding:0.04rem 0.32rem;border-radius:3px;font-weight:800;display:inline-flex;align-items:center;gap:0.2rem;" title="Real-Time Tracked Entry recorded in SQLite database archive">
                                        <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:#34d399;box-shadow:0 0 6px #34d399;"></span> REAL TRACKED
                                    </span>
                                ` : `
                                    <span style="font-size:0.60rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);padding:0.04rem 0.32rem;border-radius:3px;font-weight:600;display:inline-flex;align-items:center;gap:0.2rem;" title="Dynamic live scan setup">
                                        📊 DYNAMIC SCAN
                                    </span>
                                `}
                            </div>
                        </div>
                    </td>
                `
            },
            signal_price: {
                id: 'signal_price',
                label: 'Signal Price',
                sortKey: 'predicted_value',
                align: 'right',
                headerStyle: 'color:#60a5fa;',
                render: (c, ctx) => `
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-size:0.75rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="font-weight:700;color:#93c5fd;">${ctx.sigPriceStr}</div>
                        <div style="font-size:0.62rem;color:#64748b;margin-top:1px;" title="Signal detection date">📅 ${c.signal_date || c.entry_date || 'Signal'}</div>
                    </td>
                `
            },
            current_price: {
                id: 'current_price',
                label: 'Current Price',
                sortKey: 'current_price',
                align: 'right',
                headerStyle: 'color:#e2e8f0;',
                render: (c, ctx) => {
                    const asOfDate = c.current_date || c.asof_date || ctx.asofDate || '';
                    const timeStr = c.scanned_at ? new Date(c.scanned_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '';
                    const asOfLabel = asOfDate ? `as of ${asOfDate}` : (timeStr ? `as of ${timeStr}` : 'Today');
                    return `
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-size:0.75rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="font-weight:800;color:${ctx.curPriceColor};font-size:0.80rem;">${ctx.curPriceStr}</div>
                        <div style="font-size:0.60rem;color:#94a3b8;font-weight:500;margin-top:1px;" title="Price as of date/time">🕒 ${asOfLabel}</div>
                        <div style="margin-top:0.12rem;">
                            <span class="signal-badge" style="background:${ctx.curPriceBadgeBg};border:1px solid ${ctx.curPriceBadgeBorder};color:${ctx.curPriceBadgeText};font-size:0.60rem;font-weight:700;padding:0.06rem 0.32rem;border-radius:3px;display:inline-block;">${ctx.curPriceBadgeLabel}</span>
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
                headerStyle: 'color:#fbbf24;',
                render: (c, ctx) => `
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-size:0.75rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="font-weight:700;color:#fde047;">${ctx.triggerStr}</div>
                        <div style="font-size:0.62rem;margin-top:1px;">${ctx.gapPct}</div>
                    </td>
                `
            },
            target_stop: {
                id: 'target_stop',
                label: 'Target / Stop',
                sortKey: null,
                align: 'right',
                headerStyle: 'color:#38bdf8;',
                render: (c, ctx) => `
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-family:var(--font-mono);font-size:0.70rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);padding:0.2rem 0.4rem;border-radius:4px;display:inline-flex;flex-direction:column;gap:1px;text-align:right;">
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
                headerStyle: 'color:#34d399;',
                render: (c, ctx) => {
                    const peakP = c.post_high != null ? c.post_high : (c.peak_price != null ? c.peak_price : null);
                    const peakGain = c.max_gain_pct != null ? c.max_gain_pct : (c.peak_gain_pct != null ? c.peak_gain_pct : null);
                    const peakStr = peakP != null
                        ? `₹${Number(peakP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`
                        : '—';
                    return `
                    <td style="padding:0.46rem 0.65rem;text-align:right;font-size:0.75rem;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        ${ctx.retStr}
                        ${peakGain != null ? `
                            <div style="font-size:0.62rem;color:#94a3b8;font-family:var(--font-mono);margin-top:2px;" title="Peak price reached after breakout signal">
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
                headerStyle: 'color:#fbbf24;',
                render: (c, ctx) => {
                    const expl = c.what_happened_summary || c.explanation_one_liner;
                    return `
                    <td style="padding:0.46rem 0.65rem;border-right:1px solid rgba(255,255,255,0.03);min-width:190px;">
                        <div style="display:flex;align-items:center;gap:0.35rem;">
                            ${ctx.outcomeBadgeHtml(c)}
                        </div>
                        ${expl ? `
                            <div style="font-size:0.63rem;color:#cbd5e1;line-height:1.25;margin-top:0.25rem;max-width:270px;" title="${expl}">
                                ${expl}
                            </div>
                        ` : ''}
                    </td>
                    `;
                }
            },
            score: {
                id: 'score',
                label: '⚡ Score',
                sortKey: 'composite_score',
                align: 'center',
                headerStyle: 'color:#f1f5f9;',
                render: (c, ctx) => `
                    <td style="padding:0.46rem 0.65rem;text-align:center;white-space:nowrap;border-right:1px solid rgba(255,255,255,0.03);">
                        <span style="display:inline-block;background:${ctx.scoreBg};color:${ctx.scoreColor};border:1px solid ${ctx.scoreColor}44;font-size:0.78rem;font-weight:800;font-family:var(--font-mono);padding:0.12rem 0.45rem;border-radius:5px;" title="Resistance: ${c.resistance_score || 0} • Volume: ${c.volume_score || 0} • Compression: ${c.compression_score || 0} • Momentum: ${c.momentum_score || 0} • Fundamental: ${c.fundamental_score || 0}">
                            ${ctx.score}
                        </span>
                    </td>
                `
            },
            actions: {
                id: 'actions',
                label: 'Actions',
                sortKey: null,
                align: 'center',
                headerStyle: 'color:#64748b;',
                render: (c, ctx) => `
                    <td style="padding:0.46rem 0.65rem;text-align:center;white-space:nowrap;">
                        <div style="display:flex;align-items:center;justify-content:center;gap:0.25rem;">
                            <button type="button" onclick="app.openBreakoutHistoryModal('${ctx.ticker}')" class="btn btn-sm" style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-size:0.65rem;padding:0.18rem 0.45rem;border-radius:4px;cursor:pointer;" title="View Transition Lifecycle & Notes Timeline (Warm ➔ Hot ➔ Breakout)">
                                📜 History
                            </button>
                            <button type="button" id="btnReeval-${ctx.ticker.replace(/[^a-zA-Z0-9]/g, '_')}" onclick="app.reevaluateBreakoutStock('${ctx.ticker}')" class="btn btn-sm" style="background:rgba(234,179,8,0.15);color:#fbbf24;border:1px solid rgba(234,179,8,0.3);font-size:0.65rem;padding:0.18rem 0.42rem;border-radius:4px;cursor:pointer;" title="Re-evaluate with fresh market prices and recalculate conviction">
                                ⚡ Re-eval
                            </button>
                            <button type="button" onclick="app.openBreakoutNotesModal('${ctx.ticker}')" class="btn btn-sm" style="background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);font-size:0.65rem;padding:0.18rem 0.45rem;border-radius:4px;cursor:pointer;" title="View Mathematical Calculation Notes & Ollama AI Reasoning">
                                🧠 Reasoning
                            </button>
                            <button type="button" onclick="app.openSwingRangeModal('ALL','${ctx.ticker}')" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);font-size:0.65rem;padding:0.18rem 0.42rem;border-radius:4px;" title="Analyse ${ctx.ticker}">
                                📊
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
                app.applyBreakoutFilterAndRender();
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
                        style="position:sticky;top:0;z-index:30;background:#090e1a;padding:0.55rem 0.65rem;text-align:${def.align};${def.headerStyle || ''}${sortColor ? `color:${sortColor};` : ''}font-weight:700;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.04em;cursor:${def.sortKey ? 'pointer' : 'grab'};white-space:nowrap;user-select:none;border-bottom:1px solid rgba(56,189,248,0.3);box-shadow:0 2px 6px rgba(0,0,0,0.7);transition:background 0.15s, border-color 0.15s;"
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

            if (!candidates || candidates.length === 0) {
                tbody.innerHTML = `<tr><td colspan="${cols.length}" style="padding:2.5rem;text-align:center;color:#334155;font-size:0.82rem;">\u26a1 No candidates found for ${asofDate ? 'date ' + asofDate : 'current scan'} above score threshold.<br><span style="font-size:0.72rem;color:#1e293b;">Try lowering the Min Score or selecting another universe.</span></td></tr>`;
                return;
            }

            const outcomeBadgeHtml = (c) => {
                const badge = c.outcome_badge || 'blue';
                const label = c.outcome_label || (c.breakout_happened ? 'Breakout Succeeded ✅' : 'Pending ⏳');
                const colors = {
                    emerald: { bg: 'rgba(16,185,129,0.15)', text: '#34d399', border: 'rgba(16,185,129,0.3)' },
                    amber: { bg: 'rgba(234,179,8,0.15)', text: '#fbbf24', border: 'rgba(234,179,8,0.3)' },
                    rose: { bg: 'rgba(239,68,68,0.15)', text: '#f87171', border: 'rgba(239,68,68,0.3)' },
                    slate: { bg: 'rgba(71,85,105,0.15)', text: '#94a3b8', border: 'rgba(71,85,105,0.3)' },
                    blue: { bg: 'rgba(59,130,246,0.15)', text: '#60a5fa', border: 'rgba(59,130,246,0.3)' }
                };
                const style = colors[badge] || colors.blue;
                return `<span style="display:inline-block;background:${style.bg};color:${style.text};border:1px solid ${style.border};font-size:0.65rem;font-weight:700;padding:0.12rem 0.45rem;border-radius:4px;white-space:nowrap;">${label}</span>`;
            };

            const rows = candidates.map((c) => {
                const score = c.composite_score || 0;
                const scoreColor = score >= 75 ? '#fde68a' : score >= 55 ? '#34d399' : '#60a5fa';
                const scoreBg = score >= 75 ? 'rgba(234,179,8,0.18)' : score >= 55 ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.12)';

                const ticker = c.ticker || '\u2014';
                const company = (c.company_name || ticker).substring(0, 20);
                const industry = (c.industry || '\u2014').substring(0, 16);

                const sigPrice = c.predicted_value || c.signal_price || c.current_price;
                const sigPriceStr = sigPrice != null ? `\u20b9${Number(sigPrice).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                
                const curPriceStr = c.current_price != null ? `\u20b9${Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                const triggerStr = c.breakout_trigger != null ? `\u20b9${Number(c.breakout_trigger).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                const targetStr = c.target_price != null ? `\u20b9${Number(c.target_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                const stopStr = c.stop_loss != null ? `\u20b9${Number(c.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';

                // Compute Color-Coded Prediction Status & Current Price Styling
                let curPriceColor = '#e2e8f0';
                let curPriceBadgeBg = 'rgba(255,255,255,0.05)';
                let curPriceBadgeBorder = 'rgba(255,255,255,0.12)';
                let curPriceBadgeText = '#94a3b8';
                let curPriceBadgeLabel = 'Pending ⏳';

                const curVal = c.current_price != null ? Number(c.current_price) : null;
                const trigVal = c.breakout_trigger != null ? Number(c.breakout_trigger) : null;
                const targetVal = c.target_price != null ? Number(c.target_price) : null;
                const stopVal = c.stop_loss != null ? Number(c.stop_loss) : null;

                if (curVal != null) {
                    if (targetVal != null && curVal >= targetVal) {
                        curPriceColor = '#34d399';
                        curPriceBadgeBg = 'rgba(16,185,129,0.2)';
                        curPriceBadgeBorder = 'rgba(16,185,129,0.5)';
                        curPriceBadgeText = '#34d399';
                        curPriceBadgeLabel = '🎯 Target Hit';
                    } else if (trigVal != null && curVal >= trigVal * 1.002) {
                        curPriceColor = '#34d399';
                        curPriceBadgeBg = 'rgba(16,185,129,0.18)';
                        curPriceBadgeBorder = 'rgba(16,185,129,0.45)';
                        curPriceBadgeText = '#34d399';
                        curPriceBadgeLabel = '🟢 Breakout Fired';
                    } else if (stopVal != null && curVal <= stopVal) {
                        curPriceColor = '#f87171';
                        curPriceBadgeBg = 'rgba(239,68,68,0.2)';
                        curPriceBadgeBorder = 'rgba(239,68,68,0.5)';
                        curPriceBadgeText = '#f87171';
                        curPriceBadgeLabel = '🔴 SL Hit';
                    } else if (trigVal != null && curVal >= trigVal * 0.985) {
                        curPriceColor = '#fcd34d';
                        curPriceBadgeBg = 'rgba(146,64,14,0.28)';
                        curPriceBadgeBorder = 'rgba(217,119,6,0.45)';
                        curPriceBadgeText = '#fcd34d';
                        curPriceBadgeLabel = '🟤 Coiling';
                    } else {
                        curPriceColor = '#93c5fd';
                        curPriceBadgeBg = 'rgba(59,130,246,0.15)';
                        curPriceBadgeBorder = 'rgba(59,130,246,0.35)';
                        curPriceBadgeText = '#93c5fd';
                        curPriceBadgeLabel = '⏳ Active Setup';
                    }
                }

                const retPct = c.realized_return_pct;
                const retColor = retPct > 0 ? '#34d399' : (retPct < 0 ? '#f87171' : '#94a3b8');
                const retBg = retPct > 0 ? 'rgba(16,185,129,0.15)' : (retPct < 0 ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)');
                const retBorder = retPct > 0 ? 'rgba(16,185,129,0.3)' : (retPct < 0 ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)');
                const retStr = retPct != null
                    ? `<span style="display:inline-block;font-weight:800;color:${retColor};background:${retBg};border:1px solid ${retBorder};font-family:var(--font-mono);font-size:0.76rem;padding:0.12rem 0.42rem;border-radius:4px;">${retPct >= 0 ? '+' : ''}${Number(retPct).toFixed(2)}%</span>`
                    : '<span style="color:#64748b;">—</span>';

                let gapPct = '';
                if (curVal != null && trigVal != null && trigVal > 0) {
                    const diffPct = ((curVal - trigVal) / trigVal) * 100;
                    if (diffPct >= 0.2) {
                        gapPct = `<span style="font-size:0.62rem;color:#34d399;font-weight:700;">(+${diffPct.toFixed(1)}% breached)</span>`;
                    } else {
                        gapPct = `<span style="font-size:0.62rem;color:#fbbf24;font-weight:600;">(${diffPct.toFixed(1)}% to trigger)</span>`;
                    }
                } else if (c.pct_from_high != null) {
                    gapPct = `<span style="font-size:0.62rem;color:${c.pct_from_high >= 0 ? '#34d399' : '#f87171'};font-weight:600;">(${c.pct_from_high >= 0 ? '+' : ''}${c.pct_from_high.toFixed(1)}%)</span>`;
                }

                const archetype = c.setup_archetype || (score >= 60 ? '🔥 Strong Breakout' : '📈 Resistance Coil');

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

                return `<tr class="${rowClass}${isBreakingOut ? ' breakout-row-on-fire' : ''}" data-ticker="${ticker}">${cellsHtml}</tr>`;
            });

            tbody.innerHTML = rows.join('');
        };

        app.openBreakoutNotesModal = async function(ticker) {
            const candidate = (app._breakoutData || []).find(c => c.ticker === ticker) || { ticker: ticker };
            const modal = document.getElementById('breakoutNotesModal');
            const content = document.getElementById('breakoutNotesModalContent');
            if (!modal || !content) return;

            const notes = candidate.calculation_notes || {};
            const score = candidate.composite_score || 0;
            const resScore = candidate.resistance_score || 0;
            const volScore = candidate.volume_score || 0;
            const compScore = candidate.compression_score || 0;
            const momScore = candidate.momentum_score || 0;
            const fundScore = candidate.fundamental_score || 0;
            const archetype = candidate.setup_archetype || notes.setup_archetype || 'Breakout Setup';

            content.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.85rem;margin-bottom:1rem;">
                    <div style="display:flex;align-items:center;gap:0.6rem;">
                        <div style="font-size:1.6rem;">⚡</div>
                        <div>
                            <div style="font-size:1.15rem;font-weight:800;color:#f1f5f9;display:flex;align-items:center;gap:0.5rem;">
                                <span>${ticker}</span>
                                <span style="font-size:0.72rem;background:rgba(234,179,8,0.2);color:#fbbf24;padding:0.15rem 0.45rem;border-radius:4px;">${archetype}</span>
                                <span style="font-size:0.75rem;background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.15rem 0.45rem;border-radius:4px;font-family:var(--font-mono);">Score ${score}/100</span>
                            </div>
                            <div style="font-size:0.76rem;color:#94a3b8;">${candidate.company_name || ticker} &middot; Signal Price: ₹${candidate.signal_price || candidate.current_price || '—'}</div>
                        </div>
                    </div>
                </div>

                <!-- 1. Mathematical 5-Factor Calculation Breakdown -->
                <div style="margin-bottom:1.25rem;">
                    <div style="font-size:0.8rem;font-weight:700;color:#38bdf8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.6rem;display:flex;align-items:center;gap:0.35rem;">
                        <span>📐 Mathematical Formula &amp; Factor Reasoning</span>
                    </div>

                    <div style="display:flex;flex-direction:column;gap:0.5rem;font-size:0.78rem;">
                        <!-- Resistance -->
                        <div style="background:#0f172a;border:1px solid rgba(239,68,68,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#f87171;">1. Resistance Proximity (0–40 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#fca5a5;">${resScore.toFixed(1)} / 40 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.resistance_reasoning || `Within ${candidate.pct_from_high != null ? candidate.pct_from_high.toFixed(1) : '0'}% of key resistance high.`}</div>
                        </div>

                        <!-- Volume -->
                        <div style="background:#0f172a;border:1px solid rgba(59,130,246,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#60a5fa;">2. Volume Surge (0–10 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#93c5fd;">${volScore.toFixed(1)} / 10 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.volume_reasoning || `Volume is ${candidate.volume_ratio != null ? candidate.volume_ratio.toFixed(2) : '1.0'}x of 20D baseline.`}</div>
                        </div>

                        <!-- Compression -->
                        <div style="background:#0f172a;border:1px solid rgba(234,179,8,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#fbbf24;">3. Price Compression / ATR Squeeze (0–10 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#fde68a;">${compScore.toFixed(1)} / 10 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.compression_reasoning || `ATR is ${candidate.atr_pct != null ? candidate.atr_pct.toFixed(2) : '2.0'}% of price (volatility coiling).`}</div>
                        </div>

                        <!-- Momentum -->
                        <div style="background:#0f172a;border:1px solid rgba(16,185,129,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#34d399;">4. Momentum Posture (0–25 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#6ee7b7;">${momScore.toFixed(1)} / 25 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.momentum_reasoning || `Momentum signal: ${candidate.momentum_signal || 'Moderate'}.`}</div>
                        </div>

                        <!-- Fundamental -->
                        <div style="background:#0f172a;border:1px solid rgba(168,85,247,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#c084fc;">5. Fundamental Earnings Bonus (0–15 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#e9d5ff;">${fundScore.toFixed(1)} / 15 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.fundamental_reasoning || `Historical earnings quality score.`}</div>
                        </div>
                    </div>
                </div>

                <!-- 2. Local Ollama Multi-Model AI Opinion -->
                <div style="background:#0c1222;border:1px solid rgba(59,130,246,0.3);border-radius:8px;padding:1rem;margin-bottom:1rem;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.6rem;flex-wrap:wrap;gap:0.4rem;">
                        <div style="font-size:0.8rem;font-weight:700;color:#60a5fa;display:flex;align-items:center;gap:0.35rem;">
                            <span>🤖 Local AI Consensus (Ollama Models)</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:0.35rem;">
                            <select id="breakoutOllamaModelSelect" style="background:#0f172a;border:1px solid rgba(255,255,255,0.15);color:#e2e8f0;font-size:0.72rem;padding:0.2rem 0.45rem;border-radius:5px;outline:none;">
                                <option value="llama3.2:3b">llama3.2:3b (Fast Local)</option>
                                <option value="deepseek-r1:8b">deepseek-r1:8b (Deep Reasoning)</option>
                                <option value="qwen2.5-coder:latest">qwen2.5-coder (Algorithmic)</option>
                            </select>
                            <button type="button" onclick="app.runBreakoutAiReasoning('${ticker}')" class="btn btn-sm" style="background:#2563eb;color:#fff;font-size:0.72rem;padding:0.2rem 0.55rem;border-radius:5px;cursor:pointer;">
                                ⚡ Generate Opinion
                            </button>
                        </div>
                    </div>

                    <div id="breakoutAiOpinionBody" style="font-size:0.8rem;color:#cbd5e1;line-height:1.55;">
                        <div style="color:#94a3b8;font-style:italic;">Click "⚡ Generate Opinion" to run local Ollama multi-model analysis on volume accumulation, key levels, and fakeout risks.</div>
                    </div>
                </div>

                <!-- Footer Action -->
                <div style="display:flex;align-items:center;justify-content:space-between;padding-top:0.75rem;border-top:1px solid rgba(255,255,255,0.08);">
                    <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="color:#38bdf8;font-size:0.78rem;text-decoration:none;font-weight:600;">Open Full Stock Intelligence ↗</a>
                    <button type="button" onclick="document.getElementById('breakoutNotesModal').style.display='none'" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);padding:0.35rem 0.85rem;border-radius:6px;font-size:0.75rem;cursor:pointer;">
                        Close
                    </button>
                </div>
            `;

            modal.style.display = 'flex';
            // Auto-trigger fast local opinion
            app.runBreakoutAiReasoning(ticker);
        };

        app.runBreakoutAiReasoning = async function(ticker) {
            const bodyEl = document.getElementById('breakoutAiOpinionBody');
            const model = document.getElementById('breakoutOllamaModelSelect')?.value || 'llama3.2:3b';
            if (bodyEl) {
                bodyEl.innerHTML = `<div style="color:#60a5fa;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Generating institutional reasoning with <strong>${model}</strong> on local Ollama...</div>`;
            }

            try {
                const res = await fetch(API_BASE + '/api/v1/breakout-radar/ai-reasoning/' + encodeURIComponent(ticker) + '?model_name=' + encodeURIComponent(model), { method: 'POST' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const r = data.reasoning || {};

                if (bodyEl) {
                    const verdictColor = r.verdict === 'HIGH_CONVICTION_BREAKOUT' ? '#34d399' : (r.verdict === 'POTENTIAL_BREAKOUT_COIL' ? '#60a5fa' : '#fbbf24');
                    bodyEl.innerHTML = `
                        <div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.5rem;">
                            <span style="background:rgba(59,130,246,0.15);color:${verdictColor};font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;font-size:0.74rem;">${r.verdict || 'ANALYSIS COMPLETE'}</span>
                            <span style="color:#94a3b8;font-size:0.72rem;font-family:var(--font-mono);">Confidence: ${r.confidence_pct || 80}% &middot; Model: ${r.model_used || model}</span>
                        </div>
                        <div style="margin-bottom:0.5rem;"><strong style="color:#38bdf8;">📊 Accumulation vs Fakeout:</strong> ${r.accumulation_analysis || 'Solid volume posture.'}</div>
                        <div style="margin-bottom:0.5rem;"><strong style="color:#f87171;">⚠️ Fakeout Risk Warning:</strong> ${r.fakeout_risk_assessment || 'Monitor volume on breakout bar.'}</div>
                        <div><strong style="color:#34d399;">🎯 Execution Plan:</strong> ${r.execution_plan || 'Confirm with hourly close.'}</div>
                    `;
                }
            } catch (e) {
                console.error('[BREAKOUT-AI] Error:', e);
                if (bodyEl) {
                    bodyEl.innerHTML = `<div style="color:#f87171;">AI reasoning call failed: ${e.message}. Using rule-based calculation notes above.</div>`;
                }
            }
        };

        // =========================================================================
        // 📜 BREAKOUT LIFECYCLE & TIER TRANSITION HISTORY NOTE MODAL
        // =========================================================================
        app.closeBreakoutHistoryModal = function() {
            const modal = document.getElementById('breakoutHistoryModal');
            if (modal) modal.style.display = 'none';
        };

        app.openBreakoutHistoryModal = async function(ticker, event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            const sym = (ticker || '').trim().toUpperCase();
            if (!sym) return;

            const modal = document.getElementById('breakoutHistoryModal');
            const content = document.getElementById('bkHistContent');
            const tickerEl = document.getElementById('bkHistTicker');
            const compEl = document.getElementById('bkHistCompany');
            const badgeEl = document.getElementById('bkHistTierBadge');
            const btnStock = document.getElementById('bkHistBtnStockDetail');
            const btnIntel = document.getElementById('bkHistBtnIntelNote');

            if (!modal || !content) return;

            modal.style.display = 'flex';
            if (tickerEl) tickerEl.textContent = sym;
            if (compEl) compEl.textContent = 'Loading lifecycle history...';
            if (badgeEl) {
                badgeEl.textContent = '…';
                badgeEl.className = 'signal-badge';
                badgeEl.style.background = 'rgba(255,255,255,0.08)';
                badgeEl.style.color = '#94a3b8';
            }

            if (btnStock) btnStock.onclick = () => window.open('/stock/' + encodeURIComponent(sym), '_blank');
            if (btnIntel) btnIntel.onclick = () => { app.closeBreakoutHistoryModal(); app.openStockNote(sym); };

            content.innerHTML = `
                <div style="text-align:center;padding:3rem;color:#94a3b8;">
                    <div style="font-size:1.8rem;margin-bottom:0.6rem;display:inline-block;animation:spin 1s linear infinite;">⏳</div>
                    <div style="font-size:0.95rem;color:#f8fafc;font-weight:700;">Retrieving Transition Lifecycle for ${sym}...</div>
                    <div style="font-size:0.75rem;color:#64748b;margin-top:0.25rem;">Fetching tier movements (Warm ➔ Hot ➔ Breakout), score deltas &amp; live prices</div>
                </div>
            `;

            try {
                const res = await fetch(API_BASE + '/api/v1/breakout-radar/history/' + encodeURIComponent(sym));
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                app.renderBreakoutHistoryTimeline(data);
            } catch (err) {
                console.error('[BREAKOUT-HISTORY] Error loading timeline:', err);
                content.innerHTML = `
                    <div style="padding:2rem;text-align:center;color:#f87171;">
                        <div style="font-size:1.4rem;margin-bottom:0.4rem;">⚠️ Error Loading Transition History</div>
                        <div style="font-size:0.8rem;color:#e2e8f0;margin-bottom:1rem;">${err.message || err}</div>
                        <button type="button" onclick="app.openBreakoutHistoryModal('${sym}')" class="btn btn-sm" style="background:#2563eb;color:#fff;">🔄 Retry</button>
                    </div>
                `;
            }
        };

        app.renderBreakoutHistoryTimeline = function(data) {
            const content = document.getElementById('bkHistContent');
            const tickerEl = document.getElementById('bkHistTicker');
            const compEl = document.getElementById('bkHistCompany');
            const badgeEl = document.getElementById('bkHistTierBadge');

            if (!content || !data) return;

            const sym = data.ticker || '';
            const comp = data.company_name || sym.replace('.NS', '');
            const tier = (data.tier || 'WARM').toUpperCase();
            const curP = data.current_price != null ? '₹' + Number(data.current_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
            const trigP = data.breakout_trigger != null ? '₹' + Number(data.breakout_trigger).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
            const targetP = data.target_price != null ? '₹' + Number(data.target_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
            const stopP = data.stop_loss != null ? '₹' + Number(data.stop_loss).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
            const score = data.composite_score != null ? Number(data.composite_score).toFixed(0) : '—';
            const retPct = data.realized_return_pct != null ? Number(data.realized_return_pct) : null;
            const retStr = retPct != null ? (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%' : '—';
            const retColor = retPct != null ? (retPct >= 0 ? '#34d399' : '#f87171') : '#94a3b8';
            const activeStep = data.active_step != null ? Number(data.active_step) : 1;

            if (tickerEl) tickerEl.textContent = sym;
            if (compEl) compEl.textContent = comp + (data.industry ? ` · ${data.industry}` : '');
            if (badgeEl) {
                badgeEl.textContent = tier === 'HOT' ? '🔥 HOT POOL' : '⚡ WARM POOL';
                badgeEl.style.background = tier === 'HOT' ? 'rgba(248,113,113,0.15)' : 'rgba(251,191,36,0.15)';
                badgeEl.style.color = tier === 'HOT' ? '#f87171' : '#fbbf24';
                badgeEl.style.border = '1px solid ' + (tier === 'HOT' ? 'rgba(248,113,113,0.35)' : 'rgba(251,191,36,0.35)');
            }

            // Stepper stages
            const steps = [
                { idx: 0, label: 'Discovery', icon: '❄️', desc: 'Cold scan discovery' },
                { idx: 1, label: 'Warm Pool', icon: '⚡', desc: 'Pre-breakout coiling' },
                { idx: 2, label: 'Hot Priority', icon: '🔥', desc: 'Imminent setup' },
                { idx: 3, label: 'Breakout Fired', icon: '🚀', desc: 'Trigger breached' },
                { idx: 4, label: 'Target / Settle', icon: '🎯', desc: 'Live target tracking' },
            ];

            const stepperHtml = `
                <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:0.9rem 1rem;">
                    <div style="display:flex;align-items:center;justify-content:space-between;position:relative;margin:0 0.5rem;">
                        <div style="position:absolute;top:15px;left:0;right:0;height:2px;background:rgba(255,255,255,0.1);z-index:1;"></div>
                        <div style="position:absolute;top:15px;left:0;width:${Math.min(100, Math.max(0, activeStep * 25))}%;height:2px;background:linear-gradient(90deg, #38bdf8, #34d399);z-index:2;transition:width 0.4s ease;"></div>
                        ${steps.map((s) => {
                            const isPast = s.idx < activeStep;
                            const isCurrent = s.idx === activeStep;
                            const bg = isCurrent ? '#38bdf8' : (isPast ? '#10b981' : '#1e293b');
                            const border = isCurrent ? '#38bdf8' : (isPast ? '#10b981' : 'rgba(255,255,255,0.15)');
                            const color = isCurrent || isPast ? '#ffffff' : '#64748b';
                            const shadow = isCurrent ? '0 0 12px rgba(56,189,248,0.6)' : 'none';
                            return `
                                <div style="display:flex;flex-direction:column;align-items:center;z-index:3;cursor:default;">
                                    <div style="width:30px;height:30px;border-radius:50%;background:${bg};border:2px solid ${border};display:flex;align-items:center;justify-content:center;font-size:0.8rem;box-shadow:${shadow};color:${color};font-weight:700;">
                                        ${s.icon}
                                    </div>
                                    <div style="font-size:0.68rem;font-weight:${isCurrent ? '800' : '600'};color:${isCurrent ? '#38bdf8' : (isPast ? '#f8fafc' : '#64748b')};margin-top:0.4rem;text-align:center;">
                                        ${s.label}
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;

            // Key levels & score metrics strip
            const metricsHtml = `
                <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(110px, 1fr));gap:0.6rem;">
                    <div style="background:#0b1120;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.6rem 0.75rem;text-align:center;">
                        <div style="font-size:0.65rem;color:#64748b;font-weight:600;text-transform:uppercase;">Current Price</div>
                        <div style="font-size:0.95rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);margin-top:0.15rem;">${curP}</div>
                    </div>
                    <div style="background:#0b1120;border:1px solid rgba(56,189,248,0.25);border-radius:8px;padding:0.6rem 0.75rem;text-align:center;">
                        <div style="font-size:0.65rem;color:#38bdf8;font-weight:600;text-transform:uppercase;">Trigger Price</div>
                        <div style="font-size:0.95rem;font-weight:800;color:#38bdf8;font-family:var(--font-mono);margin-top:0.15rem;">${trigP}</div>
                    </div>
                    <div style="background:#0b1120;border:1px solid rgba(16,185,129,0.25);border-radius:8px;padding:0.6rem 0.75rem;text-align:center;">
                        <div style="font-size:0.65rem;color:#34d399;font-weight:600;text-transform:uppercase;">Target (1:2 R:R)</div>
                        <div style="font-size:0.95rem;font-weight:800;color:#34d399;font-family:var(--font-mono);margin-top:0.15rem;">${targetP}</div>
                    </div>
                    <div style="background:#0b1120;border:1px solid rgba(239,68,68,0.25);border-radius:8px;padding:0.6rem 0.75rem;text-align:center;">
                        <div style="font-size:0.65rem;color:#f87171;font-weight:600;text-transform:uppercase;">Stop Loss</div>
                        <div style="font-size:0.95rem;font-weight:800;color:#f87171;font-family:var(--font-mono);margin-top:0.15rem;">${stopP}</div>
                    </div>
                    <div style="background:#0b1120;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.6rem 0.75rem;text-align:center;">
                        <div style="font-size:0.65rem;color:#94a3b8;font-weight:600;text-transform:uppercase;">Score</div>
                        <div style="font-size:0.95rem;font-weight:800;color:#fbbf24;font-family:var(--font-mono);margin-top:0.15rem;">${score}<span style="font-size:0.68rem;color:#64748b;">/100</span></div>
                    </div>
                    <div style="background:#0b1120;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.6rem 0.75rem;text-align:center;">
                        <div style="font-size:0.65rem;color:#94a3b8;font-weight:600;text-transform:uppercase;">Outcome Return</div>
                        <div style="font-size:0.95rem;font-weight:800;color:${retColor};font-family:var(--font-mono);margin-top:0.15rem;">${retStr}</div>
                    </div>
                </div>
            `;

            // Timeline cards
            const events = data.events || [];
            const eventsHtml = events.length ? `
                <div style="display:flex;flex-direction:column;gap:0.75rem;position:relative;padding-left:1.5rem;">
                    <!-- Vertical connecting line -->
                    <div style="position:absolute;top:10px;bottom:10px;left:7px;width:2px;background:rgba(255,255,255,0.1);"></div>

                    ${events.map((ev) => {
                        const pxStr = ev.price != null ? '₹' + Number(ev.price).toFixed(2) : null;
                        const scoreStr = ev.score != null ? 'Score: ' + Number(ev.score).toFixed(1) : null;
                        return `
                            <div style="position:relative;background:#0c1322;border:1px solid rgba(255,255,255,0.08);border-left:3px solid ${ev.badge_color || '#38bdf8'};border-radius:8px;padding:0.75rem 0.9rem;box-shadow:0 4px 12px rgba(0,0,0,0.3);">
                                <!-- Node bullet on line -->
                                <div style="position:absolute;left:-1.9rem;top:1.1rem;width:12px;height:12px;border-radius:50%;background:${ev.badge_color || '#38bdf8'};border:2px solid #090d16;box-shadow:0 0 6px ${ev.badge_color || '#38bdf8'}aa;"></div>

                                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.35rem;">
                                    <div style="display:flex;align-items:center;gap:0.4rem;">
                                        <span style="font-size:0.86rem;font-weight:800;color:#f8fafc;">${ev.title}</span>
                                        <span style="font-size:0.64rem;font-weight:700;background:${ev.badge_color || '#38bdf8'}22;color:${ev.badge_color || '#38bdf8'};border:1px solid ${ev.badge_color || '#38bdf8'}44;padding:0.08rem 0.4rem;border-radius:4px;">
                                            ${ev.badge || 'EVENT'}
                                        </span>
                                    </div>
                                    <div style="font-size:0.70rem;color:#94a3b8;font-family:var(--font-mono);">
                                        ⏱️ ${ev.timestamp}
                                    </div>
                                </div>

                                <div style="font-size:0.78rem;color:#cbd5e1;line-height:1.45;margin-bottom:0.4rem;">
                                    ${ev.reason || 'Transition evaluated by multi-factor scanner.'}
                                </div>

                                ${(pxStr || scoreStr || ev.catalyst_impact) ? `
                                    <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;border-top:1px solid rgba(255,255,255,0.05);padding-top:0.35rem;font-size:0.70rem;">
                                        ${pxStr ? `<span style="color:#94a3b8;"><strong style="color:#e2e8f0;">Price:</strong> ${pxStr}</span>` : ''}
                                        ${scoreStr ? `<span style="color:#94a3b8;"><strong style="color:#fbbf24;">${scoreStr}</strong></span>` : ''}
                                        ${ev.catalyst_impact ? `<span style="color:#c084fc;">📰 ${ev.catalyst_impact}</span>` : ''}
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            ` : `
                <div style="text-align:center;padding:2rem;color:#64748b;font-size:0.8rem;">
                    No transition history events recorded for this ticker yet.
                </div>
            `;

            content.innerHTML = `
                ${stepperHtml}
                ${metricsHtml}
                <div style="margin-top:0.5rem;">
                    <div style="font-size:0.8rem;font-weight:700;color:#38bdf8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.75rem;display:flex;align-items:center;gap:0.35rem;">
                        <span>📋 Chronological Movement &amp; Lifecycle Notes</span>
                    </div>
                    ${eventsHtml}
                </div>
            `;
        };

        app.reevaluateBreakoutStock = async function(ticker, forceTier = null) {
            const safeId = ticker.replace(/[^a-zA-Z0-9]/g, '_');
            const btn = document.getElementById(`btnReeval-${safeId}`);
            let oldText = '';
            if (btn) {
                oldText = btn.innerHTML;
                btn.disabled = true;
                btn.innerHTML = '<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span>';
            }
            try {
                let url = `/api/v1/breakout-radar/evaluate/${encodeURIComponent(ticker)}`;
                if (forceTier) url += `?force_tier=${encodeURIComponent(forceTier)}`;
                const res = await fetch(url);
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Evaluation failed');
                }
                const data = await res.json();
                
                // Update in-memory data
                if (app._breakoutData) {
                    const idx = app._breakoutData.findIndex(x => x.ticker === ticker || x.ticker === data.ticker);
                    if (idx > -1) {
                        app._breakoutData[idx] = data;
                    } else {
                        app._breakoutData.unshift(data);
                    }
                    const limitVal = document.getElementById('breakoutLimitSelect')?.value || '10';
                    const limitNum = limitVal === 'all' ? app._breakoutData.length : parseInt(limitVal, 10);
                    app.renderBreakoutTable(app._breakoutData.slice(0, limitNum));
                }

                // Show notification / evaluated card
                app.renderBreakoutEvaluatedCard(data);
            } catch (e) {
                console.error('Re-evaluate error:', e);
                alert(`Failed to re-evaluate ${ticker}: ${e.message || e}`);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = oldText;
                }
            }
        };

        app.setBreakoutStockTier = async function(ticker, tier) {
            try {
                const res = await fetch(`/api/v1/breakout-radar/set-tier/${encodeURIComponent(ticker)}?tier=${encodeURIComponent(tier)}`, { method: 'POST' });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Failed to update tier');
                }
                const data = await res.json();
                alert(`✅ ${ticker} moved to ${tier.toUpperCase()} tier!`);
                await app.loadBreakoutRadar(false);
            } catch (e) {
                console.error('Set tier error:', e);
                alert(`Failed to set tier: ${e.message || e}`);
            }
        };

        app.evaluateCurrentBreakoutInput = async function() {
            const input = document.getElementById('breakoutTickerInput');
            const ticker = (input?.value || '').trim().toUpperCase();
            if (!ticker) {
                alert('Please enter a stock ticker or company name.');
                return;
            }
            const btn = document.getElementById('breakoutEvaluateBtn');
            let prevText = '';
            if (btn) {
                prevText = btn.innerHTML;
                btn.disabled = true;
                btn.innerHTML = '<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> Evaluating...';
            }

            try {
                const res = await fetch(`/api/v1/breakout-radar/evaluate/${encodeURIComponent(ticker)}`);
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Evaluation failed');
                }
                const data = await res.json();
                app.renderBreakoutEvaluatedCard(data);

                // Add to table if not present
                if (app._breakoutData) {
                    const idx = app._breakoutData.findIndex(x => x.ticker === data.ticker || x.ticker === ticker);
                    if (idx > -1) {
                        app._breakoutData[idx] = data;
                    } else {
                        app._breakoutData.unshift(data);
                    }
                    const limitVal = document.getElementById('breakoutLimitSelect')?.value || '10';
                    const limitNum = limitVal === 'all' ? app._breakoutData.length : parseInt(limitVal, 10);
                    app.renderBreakoutTable(app._breakoutData.slice(0, limitNum));
                }
            } catch (e) {
                console.error('Evaluator error:', e);
                alert(`Failed to evaluate ${ticker}: ${e.message || e}`);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = prevText;
                }
            }
        };

        app.clearBreakoutEvaluator = function() {
            const input = document.getElementById('breakoutTickerInput');
            const card = document.getElementById('breakoutEvaluatedStockCard');
            const clearBtn = document.getElementById('breakoutClearInputBtn');
            if (input) input.value = '';
            if (card) card.style.display = 'none';
            if (clearBtn) clearBtn.style.display = 'none';
        };

        app.renderBreakoutEvaluatedCard = function(c) {
            const card = document.getElementById('breakoutEvaluatedStockCard');
            if (!card) return;

            const score = c.composite_score || 0;
            const scoreColor = score >= 75 ? '#fde68a' : score >= 55 ? '#34d399' : '#60a5fa';
            const tier = c.tier || 'WARM';
            const tierBadgeColor = tier === 'HOT' ? '#f87171' : (tier === 'WARM' ? '#fbbf24' : '#94a3b8');
            const tierBg = tier === 'HOT' ? 'rgba(239,68,68,0.2)' : (tier === 'WARM' ? 'rgba(234,179,8,0.2)' : 'rgba(148,163,184,0.15)');

            const curPriceStr = c.current_price != null ? `₹${Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits:2})}` : '—';
            const trigStr = c.breakout_trigger != null ? `₹${Number(c.breakout_trigger).toLocaleString('en-IN', {minimumFractionDigits:2})}` : '—';
            const targetStr = c.target_price != null ? `₹${Number(c.target_price).toLocaleString('en-IN', {minimumFractionDigits:2})}` : '—';
            const stopStr = c.stop_loss != null ? `₹${Number(c.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2})}` : '—';

            card.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.75rem;margin-bottom:0.75rem;">
                    <div style="display:flex;align-items:center;gap:0.6rem;">
                        <span style="font-size:1.4rem;">🎯</span>
                        <div>
                            <div style="font-size:1.1rem;font-weight:800;color:#f8fafc;display:flex;align-items:center;gap:0.4rem;">
                                <span>${c.ticker}</span>
                                <span style="font-size:0.72rem;background:${tierBg};color:${tierBadgeColor};border:1px solid ${tierBadgeColor}44;padding:0.12rem 0.45rem;border-radius:4px;font-weight:700;">${c.tier_label || tier}</span>
                                <span style="font-size:0.75rem;background:rgba(59,130,246,0.2);color:${scoreColor};padding:0.12rem 0.45rem;border-radius:4px;font-family:var(--font-mono);font-weight:800;">Score ${score}/100</span>
                            </div>
                            <div style="font-size:0.75rem;color:#94a3b8;">${c.company_name || c.ticker} &middot; Sector: ${c.industry || 'Equities'}</div>
                        </div>
                    </div>

                    <!-- User Tier Decision & Re-evaluate Buttons -->
                    <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                        <button type="button" onclick="app.setBreakoutStockTier('${c.ticker}', 'hot')" class="btn btn-sm" style="background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);font-size:0.72rem;font-weight:700;" title="Pin or promote to Hot Tier (scanned every 30s)">
                            🔥 Move to Hot
                        </button>
                        <button type="button" onclick="app.setBreakoutStockTier('${c.ticker}', 'warm')" class="btn btn-sm" style="background:rgba(234,179,8,0.2);color:#fbbf24;border:1px solid rgba(234,179,8,0.4);font-size:0.72rem;font-weight:700;" title="Keep in Warm Tier (scanned every 5 min)">
                            🟡 Move to Warm
                        </button>
                        <button type="button" onclick="app.reevaluateBreakoutStock('${c.ticker}')" class="btn btn-sm" style="background:linear-gradient(135deg, #2563eb, #3b82f6);color:#fff;border:none;font-size:0.72rem;font-weight:700;" title="Re-evaluate with fresh market prices">
                            ⚡ Re-evaluate Now
                        </button>
                        <button type="button" onclick="document.getElementById('breakoutEvaluatedStockCard').style.display='none'" style="background:transparent;border:none;color:#64748b;font-size:1.1rem;cursor:pointer;padding:0.2rem 0.4rem;">✕</button>
                    </div>
                </div>

                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.6rem;font-size:0.78rem;">
                    <div style="background:#030712;padding:0.5rem 0.7rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                        <div style="color:#94a3b8;font-size:0.68rem;display:flex;justify-content:space-between;align-items:center;">
                            <span>Current Price</span>
                            <span style="color:#64748b;font-family:var(--font-mono);font-size:0.62rem;">🕒 ${c.current_date || c.asof_date || 'Today'}</span>
                        </div>
                        <div style="color:#e2e8f0;font-weight:700;font-size:0.95rem;font-family:var(--font-mono);">${curPriceStr}</div>
                    </div>
                    <div style="background:#030712;padding:0.5rem 0.7rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                        <div style="color:#94a3b8;font-size:0.68rem;">Breakout Trigger</div>
                        <div style="color:#f87171;font-weight:700;font-size:0.95rem;font-family:var(--font-mono);">${trigStr}</div>
                    </div>
                    <div style="background:#030712;padding:0.5rem 0.7rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                        <div style="color:#94a3b8;font-size:0.68rem;">Upside Target</div>
                        <div style="color:#34d399;font-weight:700;font-size:0.95rem;font-family:var(--font-mono);">${targetStr}</div>
                    </div>
                    <div style="background:#030712;padding:0.5rem 0.7rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                        <div style="color:#94a3b8;font-size:0.68rem;">Stop Loss</div>
                        <div style="color:#fca5a5;font-weight:700;font-size:0.95rem;font-family:var(--font-mono);">${stopStr}</div>
                    </div>
                </div>
            `;
            card.style.display = 'block';
            const clearBtn = document.getElementById('breakoutClearInputBtn');
            if (clearBtn) clearBtn.style.display = 'block';
        };

        app.startBreakoutPolling = function(maxAttempts = 30, intervalMs = 3000) {
            if (app._breakoutPollTimer) {
                clearInterval(app._breakoutPollTimer);
                app._breakoutPollTimer = null;
            }
            let attempts = 0;
            const notice = document.getElementById('breakoutFilterNotice');
            if (notice) {
                notice.style.display = 'inline-flex';
                notice.innerHTML = `⏱️ <strong>Scan is scheduled in background</strong> · Watching for database updates (${attempts}/${maxAttempts})... <button type="button" onclick="app.stopBreakoutPolling(); event.stopPropagation();" style="margin-left:0.45rem;background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.25);color:#cbd5e1;cursor:pointer;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;">Dismiss</button>`;
            }

            app._breakoutPollTimer = setInterval(async () => {
                attempts++;
                try {
                    const res = await fetch(API_BASE + '/api/v1/breakout-radar/status');
                    if (res.ok) {
                        const status = await res.json();
                        if (status.status === 'done' || (!status.is_scanning && attempts >= 2)) {
                            clearInterval(app._breakoutPollTimer);
                            app._breakoutPollTimer = null;
                            await app.loadBreakoutRadar(false);
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
                    if (attempts % 2 === 0) {
                        await app.loadBreakoutRadar(true);
                    }
                } catch (e) {
                    console.debug('[BREAKOUT-POLL] Status error:', e);
                }

                if (attempts >= maxAttempts) {
                    clearInterval(app._breakoutPollTimer);
                    app._breakoutPollTimer = null;
                    await app.loadBreakoutRadar(false);
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
            const universe = document.getElementById('breakoutUniverseSelect')?.value || 'nifty_50';
            const strategy = document.getElementById('breakoutStrategySelect')?.value || app._breakoutStrategy || 'CLASSIC_TECHNICAL';
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

        app.toggleBreakoutExplainer = function() {
            const card = document.getElementById('breakoutExplainerCard');
            if (!card) return;
            if (card.style.display === 'none' || !card.style.display) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        };

        app.sortBreakoutTable = function(key) {
            if (app._breakoutSortKey === key) {
                app._breakoutSortAsc = !app._breakoutSortAsc;
            } else {
                app._breakoutSortKey = key;
                app._breakoutSortAsc = false;
            }
            const sorted = [...(app._breakoutData || [])].sort((a, b) => {
                const av = a[key], bv = b[key];
                if (av == null && bv == null) return 0;
                if (av == null) return 1;
                if (bv == null) return -1;
                return app._breakoutSortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
            });
            app.renderBreakoutTable(sorted, app._breakoutAsofDate);
        };

        // -------------------------------------------------------------------------
        // 🎯 On-Demand Stock Breakout Evaluator & Live Autocomplete
        // -------------------------------------------------------------------------
        app._breakoutAutocompleteWired = false;

        app.wireBreakoutStockAutocomplete = function() {
            const input = document.getElementById('breakoutTickerInput');
            const dropdown = document.getElementById('breakoutAutocompleteDropdown');
            const clearBtn = document.getElementById('breakoutClearInputBtn');
            if (!input || !dropdown) return;

            let debounceTimer = null;
            let selectedIdx = -1;

            input.addEventListener('input', (e) => {
                const query = e.target.value.trim();
                if (clearBtn) clearBtn.style.display = query ? 'block' : 'none';

                if (debounceTimer) clearTimeout(debounceTimer);
                if (query.length < 1) {
                    dropdown.style.display = 'none';
                    return;
                }

                debounceTimer = setTimeout(async () => {
                    try {
                        const res = await fetch(API_BASE + '/api/v1/breakout-radar/search?q=' + encodeURIComponent(query));
                        if (!res.ok) throw new Error('Search failed');
                        const data = await res.json();
                        const matches = data.matches || [];

                        if (matches.length > 0) {
                            selectedIdx = -1;
                            dropdown.innerHTML = matches.map((m, i) => `
                                <div class="autocomplete-item breakout-auto-item" data-idx="${i}" onclick="app.selectBreakoutStock('${m.symbol.replace(/'/g, "\\'")}')" style="display:flex;align-items:center;justify-content:space-between;padding:0.5rem 0.8rem;border-bottom:1px solid rgba(255,255,255,0.06);cursor:pointer;transition:background 0.15s;">
                                    <div>
                                        <div style="display:flex;align-items:center;gap:0.4rem;">
                                            <strong style="color:#f8fafc;font-size:0.82rem;font-family:var(--font-mono);">${m.symbol}</strong>
                                            <span style="font-size:0.65rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:4px;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.25);">${m.market || 'NSE'}</span>
                                        </div>
                                        <div style="font-size:0.72rem;color:#94a3b8;margin-top:0.1rem;">${m.name || ''}</div>
                                    </div>
                                    <span style="font-size:0.7rem;color:#38bdf8;font-weight:600;">⚡ Audit Breakout</span>
                                </div>
                            `).join('');
                            dropdown.style.display = 'block';
                        } else {
                            dropdown.style.display = 'none';
                        }
                    } catch (err) {
                        console.debug('[BREAKOUT-AUTOCOMPLETE] Error:', err);
                        dropdown.style.display = 'none';
                    }
                }, 180);
            });

            input.addEventListener('keydown', (e) => {
                const items = dropdown.querySelectorAll('.breakout-auto-item');
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    selectedIdx = Math.min(selectedIdx + 1, items.length - 1);
                    items.forEach((it, i) => {
                        const isSel = i === selectedIdx;
                        it.style.background = isSel ? 'rgba(59,130,246,0.25)' : 'transparent';
                        if (isSel) it.scrollIntoView({ block: 'nearest' });
                    });
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    selectedIdx = Math.max(selectedIdx - 1, -1);
                    items.forEach((it, i) => {
                        const isSel = i === selectedIdx;
                        it.style.background = isSel ? 'rgba(59,130,246,0.25)' : 'transparent';
                        if (isSel) it.scrollIntoView({ block: 'nearest' });
                    });
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    if (selectedIdx >= 0 && items[selectedIdx]) {
                        items[selectedIdx].click();
                    } else if (items.length > 0) {
                        items[0].click();
                    } else if (input.value.trim()) {
                        app.evaluateCurrentBreakoutInput();
                    }
                } else if (e.key === 'Escape') {
                    dropdown.style.display = 'none';
                }
            });

            document.addEventListener('click', (e) => {
                if (!input.contains(e.target) && !dropdown.contains(e.target)) {
                    dropdown.style.display = 'none';
                }
            });
        };

        app.selectBreakoutStock = function(ticker) {
            const input = document.getElementById('breakoutTickerInput');
            const dropdown = document.getElementById('breakoutAutocompleteDropdown');
            if (input) input.value = ticker;
            if (dropdown) dropdown.style.display = 'none';
            app.evaluateBreakoutStock(ticker);
        };

        app.evaluateCurrentBreakoutInput = function() {
            const input = document.getElementById('breakoutTickerInput');
            const ticker = input ? input.value.trim() : '';
            if (!ticker) {
                alert('Please enter a stock ticker symbol (e.g. RELIANCE, TCS, INFY).');
                return;
            }
            const dropdown = document.getElementById('breakoutAutocompleteDropdown');
            if (dropdown) dropdown.style.display = 'none';
            app.evaluateBreakoutStock(ticker);
        };

        app.clearBreakoutEvaluator = function() {
            const input = document.getElementById('breakoutTickerInput');
            const dropdown = document.getElementById('breakoutAutocompleteDropdown');
            const clearBtn = document.getElementById('breakoutClearInputBtn');
            const card = document.getElementById('breakoutEvaluatedStockCard');
            if (input) input.value = '';
            if (clearBtn) clearBtn.style.display = 'none';
            if (dropdown) dropdown.style.display = 'none';
            if (card) {
                card.style.display = 'none';
                card.innerHTML = '';
            }
        };

        app.evaluateBreakoutStock = async function(ticker) {
            if (!ticker) return;
            const btn = document.getElementById('breakoutEvaluateBtn');
            const icon = document.getElementById('breakoutEvaluateIcon');
            const card = document.getElementById('breakoutEvaluatedStockCard');
            const clearBtn = document.getElementById('breakoutClearInputBtn');

            if (clearBtn) clearBtn.style.display = 'block';
            if (btn) btn.disabled = true;
            if (icon) icon.innerHTML = '<span style="display:inline-block;animation:spin 0.8s linear infinite;">⏳</span>';

            if (card) {
                card.style.display = 'block';
                card.innerHTML = `
                    <div style="text-align:center;padding:1.8rem 1rem;color:#94a3b8;">
                        <div style="font-size:1.6rem;margin-bottom:0.5rem;animation:spin 1s linear infinite;display:inline-block;">⚡</div>
                        <div style="font-weight:700;color:#f8fafc;font-size:0.92rem;">Evaluating Breakout Setup for ${ticker.toUpperCase()}...</div>
                        <div style="font-size:0.75rem;color:#64748b;margin-top:0.25rem;">Computing volatility compression, volume surge multiples, 52W resistance ceiling, and risk-reward levels...</div>
                    </div>
                `;
            }

            try {
                const asofDate = app._breakoutAsofDate || document.getElementById('breakoutDateInput')?.value || null;
                let url = API_BASE + '/api/v1/breakout-radar/evaluate/' + encodeURIComponent(ticker.trim().toUpperCase());
                if (asofDate) {
                    url += '?asof_date=' + encodeURIComponent(asofDate);
                }

                const res = await fetch(url);
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || `HTTP ${res.status}: Failed to evaluate ticker.`);
                }
                const data = await res.json();
                app.renderEvaluatedStockBreakout(data);
            } catch (e) {
                console.error('[BREAKOUT-EVAL] Error:', e);
                if (card) {
                    card.innerHTML = `
                        <div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:1rem;color:#fca5a5;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.4rem;">
                                <strong style="font-size:0.88rem;color:#f87171;">⚠️ Stock Evaluation Error</strong>
                                <button type="button" onclick="app.clearBreakoutEvaluator()" style="background:transparent;border:none;color:#94a3b8;cursor:pointer;">✕</button>
                            </div>
                            <div style="font-size:0.78rem;">${e.message || 'Could not evaluate stock for breakout. Please verify symbol.'}</div>
                        </div>
                    `;
                }
            } finally {
                if (btn) btn.disabled = false;
                if (icon) icon.textContent = '⚡';
            }
        };

        app.renderEvaluatedStockBreakout = function(d) {
            const card = document.getElementById('breakoutEvaluatedStockCard');
            if (!card || !d) return;

            const sym = d.ticker || '—';
            const comp = d.composite_score != null ? d.composite_score : 0;
            const resScore = d.resistance_score || 0;
            const volScore = d.volume_score || 0;
            const compScore = d.compression_score || 0;
            const momScore = d.momentum_score || 0;
            const fundScore = d.fundamental_score || 0;

            const tier = d.tier || (comp >= 50 ? 'HOT' : (comp >= 25 ? 'WARM' : 'COLD'));
            const tierBadge = d.tier_badge || (tier === 'HOT' ? 'emerald' : (tier === 'WARM' ? 'amber' : 'slate'));
            const tierLabel = d.tier_label || (tier === 'HOT' ? '🔥 High Conviction Setup' : (tier === 'WARM' ? '⚡ Coiling / Approaching Trigger' : '💤 Low Momentum / Dormant'));

            const scoreColor = comp >= 70 ? '#34d399' : (comp >= 45 ? '#38bdf8' : (comp >= 25 ? '#fbbf24' : '#94a3b8'));
            const calcNotes = d.calculation_notes || {};

            const curPrice = d.current_price != null ? `₹${d.current_price.toFixed(2)}` : '—';
            const triggerPrice = d.breakout_trigger != null ? `₹${d.breakout_trigger.toFixed(2)}` : '—';
            const targetPrice = d.target_price != null ? `₹${d.target_price.toFixed(2)}` : '—';
            const stopLoss = d.stop_loss != null ? `₹${d.stop_loss.toFixed(2)}` : '—';
            const rrRatio = d.risk_reward_ratio != null ? `${d.risk_reward_ratio.toFixed(2)}x` : '—';

            const pctFromHigh = d.pct_from_high != null ? `${d.pct_from_high >= 0 ? '+' : ''}${d.pct_from_high.toFixed(1)}%` : '—';
            const volRatio = d.volume_ratio != null ? `${d.volume_ratio.toFixed(2)}x` : '—';
            const atrPct = d.atr_pct != null ? `${d.atr_pct.toFixed(2)}%` : '—';

            card.innerHTML = `
                <!-- Header Banner -->
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;padding-bottom:0.75rem;border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:0.9rem;">
                    <div>
                        <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                            <h3 style="margin:0;font-size:1.15rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);letter-spacing:-0.01em;">${sym}</h3>
                            <span style="font-size:0.75rem;color:#cbd5e1;font-weight:600;">${d.company_name || ''}</span>
                            <span style="font-size:0.65rem;font-weight:700;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);padding:0.1rem 0.45rem;border-radius:4px;">${d.industry || 'Equities'}</span>
                            <span class="badge badge-${tierBadge}" style="font-size:0.7rem;font-weight:700;padding:0.15rem 0.55rem;border-radius:20px;">${tierLabel}</span>
                        </div>
                        <div style="font-size:0.72rem;color:#64748b;margin-top:0.2rem;font-family:var(--font-mono);">
                            Signal Date: ${d.signal_date || 'Live'} &middot; Data Bars: ${d.data_points || '—'} sessions &middot; Evaluated at: ${new Date().toLocaleTimeString()}
                        </div>
                    </div>

                    <!-- Composite Score Gauge Box -->
                    <div style="display:flex;align-items:center;gap:0.75rem;">
                        <div style="text-align:right;">
                            <div style="font-size:0.68rem;text-transform:uppercase;color:#94a3b8;font-weight:700;letter-spacing:0.04em;">Breakout Score</div>
                            <div style="font-size:1.75rem;font-weight:900;color:${scoreColor};font-family:var(--font-mono);line-height:1;">
                                ${comp}<span style="font-size:0.95rem;color:#64748b;font-weight:600;">/100</span>
                            </div>
                        </div>
                        <button type="button" onclick="app.clearBreakoutEvaluator()" title="Close evaluation" style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;width:28px;height:28px;border-radius:6px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:0.8rem;transition:all 0.15s;" onmouseenter="this.style.background='rgba(239,68,68,0.2)';this.style.color='#f87171'" onmouseleave="this.style.background='rgba(255,255,255,0.06)';this.style.color='#94a3b8'">✕</button>
                    </div>
                </div>

                <!-- 5-Metric Sub-Score Progress Bars Grid -->
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:0.6rem;margin-bottom:0.9rem;">
                    <!-- 1. Resistance -->
                    <div style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);padding:0.6rem 0.75rem;border-radius:6px;">
                        <div style="display:flex;justify-content:space-between;font-size:0.7rem;font-weight:700;color:#f87171;margin-bottom:0.25rem;">
                            <span>🎯 Resistance Ceiling</span>
                            <span>${resScore.toFixed(0)} / 30 pts</span>
                        </div>
                        <div style="height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;margin-bottom:0.35rem;">
                            <div style="height:100%;width:${(resScore / 30 * 100).toFixed(0)}%;background:#ef4444;border-radius:3px;"></div>
                        </div>
                        <div style="font-size:0.67rem;color:#cbd5e1;">52W Dist: <strong>${pctFromHigh}</strong></div>
                    </div>

                    <!-- 2. Volume -->
                    <div style="background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.2);padding:0.6rem 0.75rem;border-radius:6px;">
                        <div style="display:flex;justify-content:space-between;font-size:0.7rem;font-weight:700;color:#60a5fa;margin-bottom:0.25rem;">
                            <span>📊 Volume Surge</span>
                            <span>${volScore.toFixed(0)} / 20 pts</span>
                        </div>
                        <div style="height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;margin-bottom:0.35rem;">
                            <div style="height:100%;width:${(volScore / 20 * 100).toFixed(0)}%;background:#3b82f6;border-radius:3px;"></div>
                        </div>
                        <div style="font-size:0.67rem;color:#cbd5e1;">Volume: <strong>${volRatio}</strong> vs 20D SMA</div>
                    </div>

                    <!-- 3. Compression -->
                    <div style="background:rgba(234,179,8,0.06);border:1px solid rgba(234,179,8,0.2);padding:0.6rem 0.75rem;border-radius:6px;">
                        <div style="display:flex;justify-content:space-between;font-size:0.7rem;font-weight:700;color:#fbbf24;margin-bottom:0.25rem;">
                            <span>🗜️ Squeeze Compression</span>
                            <span>${compScore.toFixed(0)} / 15 pts</span>
                        </div>
                        <div style="height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;margin-bottom:0.35rem;">
                            <div style="height:100%;width:${(compScore / 15 * 100).toFixed(0)}%;background:#eab308;border-radius:3px;"></div>
                        </div>
                        <div style="font-size:0.67rem;color:#cbd5e1;">ATR Volatility: <strong>${atrPct}</strong></div>
                    </div>

                    <!-- 4. Momentum -->
                    <div style="background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);padding:0.6rem 0.75rem;border-radius:6px;">
                        <div style="display:flex;justify-content:space-between;font-size:0.7rem;font-weight:700;color:#34d399;margin-bottom:0.25rem;">
                            <span>🚀 Trend Momentum</span>
                            <span>${momScore.toFixed(0)} / 15 pts</span>
                        </div>
                        <div style="height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;margin-bottom:0.35rem;">
                            <div style="height:100%;width:${(momScore / 15 * 100).toFixed(0)}%;background:#10b981;border-radius:3px;"></div>
                        </div>
                        <div style="font-size:0.67rem;color:#cbd5e1;">Signal: <strong>${d.momentum_signal || 'Neutral'}</strong></div>
                    </div>

                    <!-- 5. Fundamental -->
                    <div style="background:rgba(139,92,246,0.06);border:1px solid rgba(139,92,246,0.2);padding:0.6rem 0.75rem;border-radius:6px;">
                        <div style="display:flex;justify-content:space-between;font-size:0.7rem;font-weight:700;color:#a78bfa;margin-bottom:0.25rem;">
                            <span>💎 Earnings Quality</span>
                            <span>${fundScore.toFixed(0)} / 20 pts</span>
                        </div>
                        <div style="height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;margin-bottom:0.35rem;">
                            <div style="height:100%;width:${(fundScore / 20 * 100).toFixed(0)}%;background:#8b5cf6;border-radius:3px;"></div>
                        </div>
                        <div style="font-size:0.67rem;color:#cbd5e1;">Avg Quality: <strong>${d.avg_quality_score != null ? d.avg_quality_score + '/9' : '—'}</strong></div>
                    </div>
                </div>

                <!-- Key Levels & Execution Plan Grid -->
                <div style="background:rgba(15,23,42,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.8rem 1rem;margin-bottom:0.9rem;">
                    <div style="font-size:0.72rem;font-weight:700;color:#38bdf8;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:0.6rem;">
                        🎯 Key Trading & Breakout Execution Levels
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:0.6rem;text-align:center;">
                        <div style="background:rgba(255,255,255,0.03);padding:0.5rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                            <div style="font-size:0.65rem;color:#94a3b8;margin-bottom:0.15rem;">Current Price</div>
                            <div style="font-size:1.05rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);">${curPrice}</div>
                        </div>
                        <div style="background:rgba(234,179,8,0.08);padding:0.5rem;border-radius:6px;border:1px solid rgba(234,179,8,0.25);">
                            <div style="font-size:0.65rem;color:#fbbf24;font-weight:700;margin-bottom:0.15rem;">⚡ Trigger Level</div>
                            <div style="font-size:1.05rem;font-weight:800;color:#fef08a;font-family:var(--font-mono);">${triggerPrice}</div>
                        </div>
                        <div style="background:rgba(16,185,129,0.08);padding:0.5rem;border-radius:6px;border:1px solid rgba(16,185,129,0.25);">
                            <div style="font-size:0.65rem;color:#34d399;font-weight:700;margin-bottom:0.15rem;">🎯 Upside Target</div>
                            <div style="font-size:1.05rem;font-weight:800;color:#6ee7b7;font-family:var(--font-mono);">${targetPrice}</div>
                        </div>
                        <div style="background:rgba(239,68,68,0.08);padding:0.5rem;border-radius:6px;border:1px solid rgba(239,68,68,0.25);">
                            <div style="font-size:0.65rem;color:#f87171;font-weight:700;margin-bottom:0.15rem;">🛑 Stop Loss</div>
                            <div style="font-size:1.05rem;font-weight:800;color:#fca5a5;font-family:var(--font-mono);">${stopLoss}</div>
                        </div>
                        <div style="background:rgba(59,130,246,0.08);padding:0.5rem;border-radius:6px;border:1px solid rgba(59,130,246,0.25);">
                            <div style="font-size:0.65rem;color:#60a5fa;font-weight:700;margin-bottom:0.15rem;">⚖️ Risk / Reward</div>
                            <div style="font-size:1.05rem;font-weight:800;color:#93c5fd;font-family:var(--font-mono);">${rrRatio}</div>
                        </div>
                    </div>
                </div>

                <!-- Narrative Rationale Box -->
                <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.7rem 0.9rem;margin-bottom:0.9rem;font-size:0.75rem;color:#cbd5e1;line-height:1.45;">
                    <div style="display:flex;align-items:center;gap:0.35rem;font-weight:700;color:#38bdf8;margin-bottom:0.3rem;">
                        <span>📜</span> Setup Archetype: <span style="color:#f8fafc;">${d.setup_archetype || 'Technical Breakout Candidate'}</span>
                    </div>
                    <div>${calcNotes.formula_summary || 'Formula calculation verified against price history sequence.'}</div>
                </div>

                <!-- Action Bar -->
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;padding-top:0.6rem;border-top:1px solid rgba(255,255,255,0.08);">
                    <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                        <button type="button" onclick="app.openAiConsensusForStock('${sym}')" class="btn-micro" style="background:rgba(139,92,246,0.18);color:#c084fc;border:1px solid rgba(139,92,246,0.3);padding:0.3rem 0.65rem;">
                            <span>🧠</span> AI Consensus
                        </button>
                        <button type="button" onclick="app.openKronosForStock('${sym}')" class="btn-micro" style="background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:0.3rem 0.65rem;">
                            <span>🔮</span> Kronos 14D Forecast
                        </button>
                        <button type="button" onclick="window.open('/stock/' + encodeURIComponent('${sym}'), '_blank')" class="btn-micro" style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);padding:0.3rem 0.65rem;">
                            <span>📊</span> Full Stock Intelligence ↗
                        </button>
                    </div>

                    <button type="button" onclick="app.clearBreakoutEvaluator()" class="btn-micro" style="background:rgba(255,255,255,0.06);color:#94a3b8;padding:0.3rem 0.65rem;">
                        Dismiss Audit ✕
                    </button>
                </div>
            `;

            // Scroll card into view gently
            card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        };

        app.openAiConsensusForStock = function(ticker) {
            if (typeof app.switchTab === 'function') {
                app.switchTab('consensus');
                setTimeout(() => {
                    const input = document.getElementById('consensusTickerInput');
                    if (input) {
                        input.value = ticker;
                        if (typeof app.loadConsensusPrediction === 'function') {
                            app.loadConsensusPrediction(ticker);
                        }
                    }
                }, 150);
            } else {
                window.open('/stock/' + encodeURIComponent(ticker) + '#consensus', '_blank');
            }
        };

        app.openKronosForStock = function(ticker) {
            if (typeof app.switchTab === 'function') {
                app.switchTab('kronos');
                setTimeout(() => {
                    const input = document.getElementById('kronosSymbolInput');
                    if (input) {
                        input.value = ticker;
                        if (typeof app.loadKronosPrediction === 'function') {
                            app.loadKronosPrediction(ticker);
                        }
                    }
                }, 150);
            } else {
                window.open('/stock/' + encodeURIComponent(ticker) + '#kronos', '_blank');
            }
        };

        // 📅 QUICK DATE BACKTEST MODULE
        app.loadBreakoutBacktest = async function() {
            const dateInput = document.getElementById('breakoutBacktestDateInput');
            let dateVal = dateInput?.value;
            if (!dateVal) {
                const d = new Date();
                dateVal = d.toISOString().split('T')[0];
                if (dateInput) dateInput.value = dateVal;
            }

            const universe = document.getElementById('breakoutBacktestUniverseSelect')?.value || 'all';
            const minScore = document.getElementById('breakoutBacktestMinScore')?.value || 35;
            const sortBy = document.getElementById('breakoutBacktestSortBy')?.value || 'composite_score';

            try {
                const params = new URLSearchParams({
                    universe: universe,
                    sort_by: sortBy,
                    min_score: minScore,
                    asof_date: dateVal,
                    limit: 100
                });
                const res = await fetch(API_BASE + '/api/v1/breakout-radar?' + params.toString());
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();

                const candidates = data.candidates || [];
                const summary = data.backtest_summary || {};
                const total = candidates.length;
                const avgScore = total > 0
                    ? (candidates.reduce((s, c) => s + (c.composite_score || 0), 0) / total).toFixed(1)
                    : '—';

                const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
                setEl('bkBacktestStatDate', dateVal);
                setEl('bkBacktestStatEvaluated', summary.total_evaluated != null ? summary.total_evaluated : total);
                setEl('bkBacktestStatFired', summary.breakout_fired_count != null ? summary.breakout_fired_count : candidates.filter(app.isItemBreaking).length);
                setEl('bkBacktestStatWinRate', (summary.win_rate_pct != null ? Number(summary.win_rate_pct).toFixed(1) : '0.0') + '%');
                setEl('bkBacktestStatAvgScore', avgScore);

                app.renderBreakoutBacktestTable(candidates, dateVal);
            } catch (err) {
                console.error('[BREAKOUT BACKTEST] Load error:', err);
            }
        };

        app.setBreakoutBacktestPresetDays = function(daysAgo) {
            const d = new Date();
            d.setDate(d.getDate() - daysAgo);
            const iso = d.toISOString().split('T')[0];
            const dateInput = document.getElementById('breakoutBacktestDateInput');
            if (dateInput) dateInput.value = iso;

            document.querySelectorAll('.bk-backtest-preset-btn').forEach(btn => {
                const btnDays = btn.getAttribute('data-days');
                if (String(btnDays) === String(daysAgo)) {
                    btn.classList.add('bk-preset-active');
                    btn.style.background = 'rgba(56,189,248,0.2)';
                    btn.style.borderColor = '#38bdf8';
                    btn.style.color = '#38bdf8';
                } else {
                    btn.classList.remove('bk-preset-active');
                    btn.style.background = '#0f172a';
                    btn.style.borderColor = 'rgba(255,255,255,0.12)';
                    btn.style.color = '#94a3b8';
                }
            });

            app.loadBreakoutBacktest();
        };

        app.renderBreakoutBacktestTable = function(candidates, dateVal) {
            const tbody = document.getElementById('breakoutBacktestTableBody');
            if (!tbody) return;

            if (!candidates || candidates.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="padding:2.5rem;text-align:center;color:#64748b;font-size:0.8rem;">⚡ No historical breakout candidates found for date <strong>${dateVal}</strong> above threshold.</td></tr>`;
                return;
            }

            tbody.innerHTML = candidates.map(c => {
                const ticker = c.ticker || '—';
                const company = (c.company_name || ticker).substring(0, 22);
                const score = c.composite_score || 0;
                const scoreColor = score >= 75 ? '#fde68a' : (score >= 55 ? '#34d399' : '#60a5fa');
                const scoreBg = score >= 75 ? 'rgba(234,179,8,0.18)' : (score >= 55 ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.12)');

                const sigPriceStr = c.signal_price != null ? `₹${Number(c.signal_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const triggerStr = c.breakout_trigger != null ? `₹${Number(c.breakout_trigger).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const targetStr = c.target_price != null ? `₹${Number(c.target_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const stopStr = c.stop_loss != null ? `₹${Number(c.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '—';
                const retPct = c.realized_return_pct != null ? c.realized_return_pct : c.post_return_pct;
                const retStr = retPct != null ? `<span style="color:${retPct >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${retPct >= 0 ? '+' : ''}${Number(retPct).toFixed(2)}%</span>` : '—';

                const outcomeLabel = c.outcome_label || (c.breakout_happened ? 'Breakout Succeeded ✅' : 'Coiling ⏳');

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                        <td style="padding:0.5rem 0.75rem;">
                            <div style="font-weight:800;color:#ffffff;font-family:var(--font-mono);font-size:0.82rem;"><a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="color:#ffffff;text-decoration:none;">${ticker}</a></div>
                            <div style="font-size:0.67rem;color:#94a3b8;">${company}</div>
                        </td>
                        <td style="padding:0.5rem 0.75rem;text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#94a3b8;">${sigPriceStr}</td>
                        <td style="padding:0.5rem 0.75rem;text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#38bdf8;font-weight:700;">${triggerStr}</td>
                        <td style="padding:0.5rem 0.75rem;text-align:right;font-family:var(--font-mono);font-size:0.70rem;">
                            <div style="color:#34d399;">T: ${targetStr}</div>
                            <div style="color:#f87171;">SL: ${stopStr}</div>
                        </td>
                        <td style="padding:0.5rem 0.75rem;text-align:right;font-family:var(--font-mono);font-size:0.75rem;">${retStr}</td>
                        <td style="padding:0.5rem 0.75rem;font-size:0.72rem;color:#e2e8f0;">${outcomeLabel}</td>
                        <td style="padding:0.5rem 0.75rem;text-align:center;">
                            <span style="background:${scoreBg};color:${scoreColor};border:1px solid ${scoreColor}44;font-size:0.75rem;font-weight:800;font-family:var(--font-mono);padding:0.1rem 0.4rem;border-radius:4px;">${score}</span>
                        </td>
                    </tr>
                `;
            }).join('');
        };

})(); // end breakout_radar IIFE
