// =========================================================================
// schedules — Nexus Dashboard Module (Automation Schedules & Job Monitor)
// Extracted from dashboard.js — modularization 2026-08-28 & Multi-Strategy 2026-08-30
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    Object.assign(app, {
        _automationSchedules: [],
        _breakoutSchedules: [],
        _scheduleTimerStarted: false,
        _isParallelScanRunning: false,

        async loadAutomationSchedules() {
            try {
                this.checkMasterSchedulerEngineStatus();
                const res = await fetch(API_BASE + '/api/v1/automation/schedules');
                if (res.ok) {
                    const data = await res.json();
                    this._automationSchedules = data.schedules || [];
                    this.renderAutomationSchedules();
                    this.renderBreakoutSchedules();
                    this.renderPlaygroundSchedules();
                    if (!this._scheduleTimerStarted) {
                        this._scheduleTimerStarted = true;
                        this.startScheduleTimer();
                    }
                }
            } catch (e) {
                console.debug('Failed loading schedules:', e);
            }
        },

        async loadBreakoutSchedules() {
            try {
                const res = await fetch(API_BASE + '/api/v1/breakout-radar/schedules');
                if (res.ok) {
                    const data = await res.json();
                    this._breakoutSchedules = data.schedules || [];
                    this.renderBreakoutSchedules();
                }
            } catch (e) {
                console.debug('Failed loading breakout schedules:', e);
            }
        },

        startScheduleTimer() {
            setInterval(() => {
                if (this._automationSchedules && this._automationSchedules.length) {
                    this._automationSchedules.forEach(s => {
                        if (s.seconds_until_next > 0) {
                            s.seconds_until_next -= 1;
                        }
                    });
                    this.renderAutomationSchedules();
                    this.renderPlaygroundSchedules();
                }
                if (this._breakoutSchedules && this._breakoutSchedules.length) {
                    this._breakoutSchedules.forEach(s => {
                        if (s.seconds_until_next > 0) {
                            s.seconds_until_next -= 1;
                        }
                    });
                    this.renderBreakoutSchedules();
                }
            }, 1000);
        },

        renderAutomationSchedules() {
            if (!this._automationSchedules) return;

            const hotSched = this._automationSchedules.find(s => s.job_id === 'breakout_hot_rescore');
            const warmSched = this._automationSchedules.find(s => s.job_id === 'breakout_warm_rescore');
            const coldSched = this._automationSchedules.find(s => s.job_id === 'breakout_cold_scan' || s.job_id === 'breakout_all_strategies_parallel');
            const newsSched = this._automationSchedules.find(s => s.job_id === 'news_catalyst_harvest');

            const formatTimer = (s) => {
                if (!s) return 'Next run: <strong style="color:#38bdf8;">--</strong>';
                const now = new Date();
                const day = now.getDay(); // 0 is Sunday, 6 is Saturday
                const isMarketHoursOnly = !s.market_session || s.market_session === 'market_hours_only' || s.run_after_hours === 0;
                if ((day === 0 || day === 6) && isMarketHoursOnly) {
                    const lastRun = s.last_run_formatted || 'Weekend Snapshot';
                    return `Market: <strong style="color:#fbbf24;">Closed (Weekend)</strong> | Last: ${lastRun}`;
                }
                const sec = s.seconds_until_next;
                const timeIn = sec <= 0 ? 'Due now' : (sec < 60 ? `${sec}s` : `${Math.floor(sec/60)}m ${sec%60}s`);
                const lastRun = s.last_run_formatted || 'Never';
                return `Next run: <strong style="color:#38bdf8;">${timeIn}</strong> | Last: ${lastRun}`;
            };

            const elHot = document.getElementById('schedBreakoutHotTimer');
            if (elHot && hotSched) elHot.innerHTML = formatTimer(hotSched);

            const elWarm = document.getElementById('schedBreakoutWarmTimer');
            if (elWarm && warmSched) elWarm.innerHTML = formatTimer(warmSched);

            const elCold = document.getElementById('schedBreakoutColdTimer');
            if (elCold && coldSched) elCold.innerHTML = formatTimer(coldSched);

            const elNews = document.getElementById('schedNewsHarvesterTimer');
            if (elNews && newsSched) elNews.innerHTML = formatTimer(newsSched);
        },

        updateHarvesterScheduleDisplay() {
            this.renderAutomationSchedules();
        },

        // =========================================================================
        // Master Scheduler Engine Controls & Status
        // =========================================================================

        async toggleMasterSchedulerEngine() {
            try {
                const statusRes = await fetch(API_BASE + '/api/v1/automation/engine');
                let isRunning = true;
                if (statusRes.ok) {
                    const statusData = await statusRes.json();
                    isRunning = !!statusData.is_running;
                }
                const endpoint = isRunning ? '/api/v1/automation/engine/stop' : '/api/v1/automation/engine/start';
                const res = await fetch(API_BASE + endpoint, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    this.updateMasterSchedulerEngineDisplay(data.is_running);
                    await this.loadAutomationSchedules();
                }
            } catch (e) {
                console.error('Failed toggling scheduler engine:', e);
            }
        },

        updateMasterSchedulerEngineDisplay(isRunning) {
            const badge = document.getElementById('pgEngineStatusBadge');
            const btn = document.getElementById('pgToggleEngineBtn');
            if (badge) {
                badge.textContent = isRunning ? '🟢 ENGINE ACTIVE' : '⏸️ ENGINE PAUSED';
                badge.style.background = isRunning ? 'rgba(16, 185, 129, 0.15)' : 'rgba(251, 191, 36, 0.15)';
                badge.style.color = isRunning ? '#34d399' : '#fbbf24';
                badge.style.borderColor = isRunning ? 'rgba(16, 185, 129, 0.3)' : 'rgba(251, 191, 36, 0.3)';
            }
            if (btn) {
                btn.innerHTML = isRunning ? '⏸️ Pause Engine' : '▶️ Resume Engine';
            }
        },

        async checkMasterSchedulerEngineStatus() {
            try {
                const res = await fetch(API_BASE + '/api/v1/automation/engine');
                if (res.ok) {
                    const data = await res.json();
                    this.updateMasterSchedulerEngineDisplay(data.is_running);
                }
            } catch (e) {
                console.debug('Failed checking scheduler engine status:', e);
            }
        },

        // =========================================================================
        // Multi-Strategy Breakout Scheduler Modal & Controls
        // =========================================================================

        openBreakoutScheduleModal() {
            const modal = document.getElementById('breakoutScheduleModal');
            if (modal) {
                modal.style.display = 'flex';
                this.loadBreakoutSchedules();
            }
        },

        closeBreakoutScheduleModal() {
            const modal = document.getElementById('breakoutScheduleModal');
            if (modal) modal.style.display = 'none';
        },

        renderBreakoutSchedules() {
            const schedules = this._breakoutSchedules.length ? this._breakoutSchedules : this._automationSchedules.filter(s => s.category === 'Breakout Radar' || s.job_id.startsWith('breakout'));
            if (!schedules || !schedules.length) return;

            // 1. Master Parallel Schedule Card elements
            const masterSched = schedules.find(s => s.job_id === 'breakout_all_strategies_parallel');
            if (masterSched) {
                const badge = document.getElementById('bkMasterSchedStatusBadge');
                if (badge) {
                    const isAct = masterSched.status === 'active' || masterSched.status === 'running';
                    const intervalMin = Math.round(masterSched.interval_seconds / 60);
                    badge.textContent = isAct ? `🟢 Active (${intervalMin}m)` : `⏸️ Paused (${intervalMin}m)`;
                    badge.style.background = isAct ? 'rgba(16,185,129,0.15)' : 'rgba(251,191,36,0.15)';
                    badge.style.color = isAct ? '#34d399' : '#fbbf24';
                }
                const countdown = document.getElementById('bkMasterSchedCountdown');
                if (countdown) {
                    const sec = masterSched.seconds_until_next;
                    const timeIn = sec <= 0 ? 'Due now' : (sec < 60 ? `${sec}s` : `${Math.floor(sec/60)}m ${sec%60}s`);
                    countdown.innerHTML = `Next automated sweep in: <strong style="color:#38bdf8;">${timeIn}</strong> · Last run: <strong>${masterSched.last_run_formatted || 'Never'}</strong> (${masterSched.last_duration_s || 0}s)`;
                }
            }

            // 2. Individual Strategy Schedule Cards
            const container = document.getElementById('bkStrategySchedulesContainer');
            if (!container) return;

            const stratJobs = [
                { id: 'breakout_cold_scan', name: '⚡ Classic Technical Coiling', badge: 'Classic 20D/52W Coil', icon: '⚡', desc: '52W High & 20D High proximity with ATR compression coiling and volume confirmation.' },
                { id: 'breakout_delivery_absorption_scan', name: '🏛️ NSE Institutional Delivery Absorption', badge: 'Bhavcopy Delivery Surge', icon: '🏛️', desc: 'Deliverable volume spikes exceeding 60% with FII/DII block deal accumulation support.' },
                { id: 'breakout_fo_call_wall_scan', name: '🎯 NSE F&O Call OI Wall Gamma Squeeze', badge: 'Call OI Gamma Squeeze', icon: '🎯', desc: 'Call open interest resistance strike proximity, short-covering velocity, and PCR momentum.' },
                { id: 'breakout_volume_profile_scan', name: '📊 Volume Profile Value Area High (VAH)', badge: 'Value Area High VAH', icon: '📊', desc: '63-day Volume Profile VAH breakouts and low-volume node (LVN) liquidity vacuum acceleration.' },
                { id: 'breakout_donchian_squeeze_scan', name: '🌪️ Donchian 55D + TTM Volatility Squeeze', badge: 'TTM Squeeze + 55D Donchian', icon: '🌪️', desc: 'John Carter TTM Squeeze (Bollinger inside Keltner) alongside 55-Day Donchian channel expansion.' },
            ];

            let html = '';
            stratJobs.forEach(jobMeta => {
                const s = schedules.find(item => item.job_id === jobMeta.id) || {
                    job_id: jobMeta.id,
                    job_name: jobMeta.name,
                    interval_seconds: 3600,
                    status: 'active',
                    is_enabled: 1,
                    seconds_until_next: 3600,
                    last_duration_s: 0,
                    last_summary: 'Ready for scheduled run.',
                };

                const isAct = (s.status === 'active' || s.status === 'running') && s.is_enabled;
                const sec = s.seconds_until_next || 0;
                const timeIn = sec <= 0 ? 'Due now' : (sec < 60 ? `${sec}s` : `${Math.floor(sec/60)}m ${sec%60}s`);

                html += `
                <div class="card" style="padding:0.75rem 1rem;background:#080d1a;border:1px solid ${isAct ? 'rgba(56,189,248,0.22)' : 'rgba(255,255,255,0.08)'};border-radius:8px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;">
                    <div style="max-width:480px;">
                        <div style="display:flex;align-items:center;gap:0.45rem;margin-bottom:0.2rem;">
                            <span style="font-size:1.1rem;">${jobMeta.icon}</span>
                            <strong style="color:#f8fafc;font-size:0.85rem;">${jobMeta.name}</strong>
                            <span class="signal-badge" style="font-size:0.62rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);padding:0.08rem 0.35rem;border-radius:4px;">${jobMeta.badge}</span>
                        </div>
                        <div style="font-size:0.70rem;color:#94a3b8;line-height:1.35;">
                            ${jobMeta.desc}
                        </div>
                        <div style="font-size:0.68rem;color:#64748b;font-family:var(--font-mono);margin-top:0.3rem;">
                            Next run: <span style="color:#38bdf8;font-weight:700;">${timeIn}</span> · Last: <span style="color:#cbd5e1;">${s.last_run_formatted || 'Never'}</span> (${s.last_duration_s || 0}s)
                        </div>
                    </div>

                    <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                        <!-- Cadence Selector -->
                        <div style="display:flex;align-items:center;gap:0.3rem;">
                            <span style="font-size:0.68rem;color:#64748b;">Cadence:</span>
                            <select onchange="app.updateBreakoutStrategySchedule('${s.job_id}', this.value, ${isAct ? 'true' : 'false'})" style="background:#0f172a;border:1px solid rgba(255,255,255,0.15);color:#38bdf8;font-size:0.72rem;font-weight:600;font-family:var(--font-mono);padding:0.2rem 0.4rem;border-radius:4px;outline:none;cursor:pointer;">
                                <option value="300" ${s.interval_seconds === 300 ? 'selected' : ''}>5m</option>
                                <option value="900" ${s.interval_seconds === 900 ? 'selected' : ''}>15m</option>
                                <option value="1800" ${s.interval_seconds === 1800 ? 'selected' : ''}>30m</option>
                                <option value="3600" ${s.interval_seconds === 3600 ? 'selected' : ''}>1 Hour</option>
                                <option value="7200" ${s.interval_seconds === 7200 ? 'selected' : ''}>2 Hours</option>
                                <option value="14400" ${s.interval_seconds === 14400 ? 'selected' : ''}>4 Hours</option>
                                <option value="86400" ${s.interval_seconds === 86400 ? 'selected' : ''}>Daily</option>
                            </select>
                        </div>

                        <!-- Toggle Active/Pause Button -->
                        <button type="button" onclick="app.updateBreakoutStrategySchedule('${s.job_id}', ${s.interval_seconds}, ${isAct ? 'false' : 'true'})" class="btn btn-sm ${isAct ? 'btn-secondary' : 'btn-primary'}" style="font-size:0.70rem;padding:0.22rem 0.55rem;">
                            ${isAct ? '⏸️ Pause' : '▶️ Enable'}
                        </button>

                        <!-- Single Strategy Trigger Button -->
                        <button type="button" id="btnRun_${s.job_id}" onclick="app.triggerBreakoutSingleSchedule('${s.job_id}')" class="btn btn-secondary btn-sm" style="font-size:0.70rem;padding:0.22rem 0.6rem;color:#38bdf8;border-color:rgba(56,189,248,0.35);">
                            ⚡ Run Now
                        </button>
                    </div>
                </div>
                `;
            });

            container.innerHTML = html;
        },

        async updateBreakoutStrategySchedule(jobId, intervalSeconds, isEnabled) {
            try {
                const payload = {
                    interval_seconds: parseInt(intervalSeconds, 10),
                    is_enabled: isEnabled,
                    status: isEnabled ? 'active' : 'paused'
                };
                const res = await fetch(API_BASE + `/api/v1/breakout-radar/schedules/configure?job_id=${encodeURIComponent(jobId)}&interval_seconds=${payload.interval_seconds}&is_enabled=${payload.is_enabled}&status=${payload.status}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    await this.loadBreakoutSchedules();
                    await this.loadAutomationSchedules();
                }
            } catch (e) {
                console.error('Failed to configure breakout schedule:', e);
            }
        },

        async triggerBreakoutSingleSchedule(jobId) {
            const btn = document.getElementById(`btnRun_${jobId}`);
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner" style="width:10px;height:10px;"></span> Scheduled...';
            }
            try {
                const res = await fetch(API_BASE + `/api/v1/breakout-radar/schedules/${encodeURIComponent(jobId)}/trigger`, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    console.log('[BREAKOUT-SCHEDULE] Triggered:', data);
                    if (typeof app.startBreakoutPolling === 'function') {
                        app.startBreakoutPolling();
                    }
                    setTimeout(() => {
                        this.loadBreakoutSchedules();
                        if (btn) {
                            btn.disabled = false;
                            btn.innerHTML = '⚡ Run Now';
                        }
                    }, 1200);
                }
            } catch (e) {
                console.error('Error triggering breakout schedule:', e);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '⚡ Run Now';
                }
            }
        },

        async triggerAllBreakoutStrategiesParallel(fromModal = false) {
            if (this._isParallelScanRunning) return;
            this._isParallelScanRunning = true;

            const masterBtn = document.getElementById('breakoutParallelScanBtn');
            const masterIcon = document.getElementById('breakoutParallelIcon');
            const modalBtn = document.getElementById('bkModalParallelTriggerBtn');
            const modalIcon = document.getElementById('bkModalParallelTriggerIcon');

            if (masterBtn) {
                masterBtn.disabled = true;
                if (masterIcon) masterIcon.textContent = '⏱️';
                masterBtn.style.opacity = '0.7';
            }
            if (modalBtn) {
                modalBtn.disabled = true;
                if (modalIcon) modalIcon.textContent = '⏱️';
                modalBtn.innerHTML = '<span>⏱️</span> Scan Scheduled in Background...';
            }

            try {
                const universe = this._breakoutUniverse || 'all';
                const minScore = parseFloat(document.getElementById('breakoutMinScore')?.value || '30');

                const res = await fetch(API_BASE + `/api/v1/breakout-radar/schedules/parallel-scan?universe=${encodeURIComponent(universe)}&min_score=${minScore}`, {
                    method: 'POST'
                });

                if (res.ok) {
                    const data = await res.json();
                    console.log('[BREAKOUT-PARALLEL] Scheduled:', data);

                    // Initiate background polling loop to track database population
                    if (typeof app.startBreakoutPolling === 'function') {
                        app.startBreakoutPolling();
                    }
                    this.loadBreakoutSchedules();
                }
            } catch (e) {
                console.error('Error scheduling parallel multi-strategy breakout scan:', e);
            } finally {
                setTimeout(() => {
                    this._isParallelScanRunning = false;
                    if (masterBtn) {
                        masterBtn.disabled = false;
                        if (masterIcon) masterIcon.textContent = '⏱️';
                        masterBtn.style.opacity = '1';
                    }
                    if (modalBtn) {
                        modalBtn.disabled = false;
                        modalBtn.innerHTML = '<span>⚡</span> Schedule Parallel Sweep';
                    }
                }, 1500);
            }
        },

        async triggerScheduleJob(jobId) {
            try {
                const res = await fetch(API_BASE + `/api/v1/automation/trigger?job_id=${encodeURIComponent(jobId)}`, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    console.log(data.message);
                    setTimeout(() => this.loadAutomationSchedules(), 1500);
                    if (jobId.startsWith('breakout')) {
                        // Poll scan status and refresh only after scan actually completes
                        const pollForScanDone = (attempts = 0) => {
                            const maxAttempts = 40;
                            const interval = 3000;
                            const timer = setInterval(async () => {
                                attempts++;
                                try {
                                    const statusRes = await fetch(API_BASE + '/api/v1/breakout-radar/status');
                                    if (statusRes.ok) {
                                        const st = await statusRes.json();
                                        if (st.status === 'done' || (!st.is_scanning && attempts >= 3)) {
                                            clearInterval(timer);
                                            await window.app.loadBreakoutRadar(false);
                                            if (typeof window.app.loadBreakoutAuditLog === 'function') {
                                                await window.app.loadBreakoutAuditLog();
                                            }
                                            if (typeof window.app.updateSidebarBadges === 'function') {
                                                await window.app.updateSidebarBadges();
                                            }
                                            return;
                                        }
                                    }
                                } catch (e) {
                                    console.debug('[SCHEDULE-POLL] Status error:', e);
                                }
                                if (attempts >= maxAttempts) {
                                    clearInterval(timer);
                                    await window.app.loadBreakoutRadar(false);
                                }
                            }, interval);
                        };
                        pollForScanDone();
                    }
                }
            } catch (e) {
                console.error('Trigger schedule error:', e);
            }
        },

        // =========================================================================
        // Centralized Automation Studio Table & Playground Handlers
        // =========================================================================

        renderPlaygroundSchedules() {
            if (!this._automationSchedules) return;
            const schedules = this._automationSchedules;

            // Update KPIs
            const total = schedules.length;
            const active = schedules.filter(s => s.is_enabled && s.status !== 'paused').length;
            const running = schedules.filter(s => s.status === 'running').length;
            const runs = schedules.reduce((acc, s) => acc + (s.total_runs || 0), 0);

            const elTotal = document.getElementById('pgSchedKpiTotal');
            if (elTotal) elTotal.textContent = total;
            const elActive = document.getElementById('pgSchedKpiActive');
            if (elActive) elActive.textContent = active;
            const elRunning = document.getElementById('pgSchedKpiRunning');
            if (elRunning) elRunning.textContent = running;
            const elRuns = document.getElementById('pgSchedKpiRuns');
            if (elRuns) elRuns.textContent = runs;

            // Render Table Body
            const tbody = document.getElementById('pgSchedulesTableBody');
            if (!tbody) return;

            if (!schedules.length) {
                tbody.innerHTML = `<tr><td colspan="8" style="padding:2rem; text-align:center; color:#64748b;">No scheduled flows registered.</td></tr>`;
                return;
            }

            let html = '';
            schedules.forEach(s => {
                const isAct = s.is_enabled && s.status !== 'paused';
                const isRunning = s.status === 'running';
                const isError = s.status === 'error';
                
                const sec = s.seconds_until_next || 0;
                const timeIn = !isAct ? 'Paused' : (sec <= 0 ? 'Due now' : (sec < 60 ? `${sec}s` : `${Math.floor(sec/60)}m ${sec%60}s`));
                
                let statusBadge = '';
                if (isRunning) {
                    statusBadge = `<span class="signal-badge" style="background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid rgba(56,189,248,0.3); font-size:0.65rem; padding:0.1rem 0.4rem; border-radius:4px;">⚡ Running</span>`;
                } else if (isError) {
                    statusBadge = `<span class="signal-badge" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); font-size:0.65rem; padding:0.1rem 0.4rem; border-radius:4px;">🔴 Error</span>`;
                } else if (isAct) {
                    statusBadge = `<span class="signal-badge" style="background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.3); font-size:0.65rem; padding:0.1rem 0.4rem; border-radius:4px;">🟢 Active</span>`;
                } else {
                    statusBadge = `<span class="signal-badge" style="background:rgba(251,191,36,0.15); color:#fbbf24; border:1px solid rgba(251,191,36,0.3); font-size:0.65rem; padding:0.1rem 0.4rem; border-radius:4px;">⏸️ Paused</span>`;
                }

                const paramsDisplay = s.params_json ? (typeof s.params_json === 'string' ? s.params_json : JSON.stringify(s.params_json)) : 'Default';

                html += `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                    <td style="padding:0.6rem 0.75rem;">
                        <div style="font-weight:700; color:#f8fafc; font-size:0.8rem;">${s.job_name || s.job_id}</div>
                        <div style="display:flex; align-items:center; gap:0.35rem; margin-top:0.15rem;">
                            <span style="font-size:0.65rem; color:#38bdf8; font-family:var(--font-mono);">${s.job_id}</span>
                            <span class="signal-badge" style="font-size:0.6rem; background:rgba(255,255,255,0.05); color:#94a3b8; padding:0.05rem 0.3rem; border-radius:3px;">${s.category || 'Automation'}</span>
                        </div>
                    </td>
                    <td style="padding:0.6rem 0.65rem;">
                        <span style="font-size:0.68rem; color:#cbd5e1; font-family:var(--font-mono); display:inline-block; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${paramsDisplay}">${paramsDisplay}</span>
                    </td>
                    <td style="padding:0.6rem 0.55rem; font-family:var(--font-mono); color:#38bdf8; font-weight:600;">
                        ${s.interval_formatted || s.interval_seconds + 's'}
                    </td>
                    <td style="padding:0.6rem 0.55rem; font-family:var(--font-mono); font-weight:700; color:${isAct ? '#38bdf8' : '#64748b'};">
                        ${timeIn}
                    </td>
                    <td style="padding:0.6rem 0.55rem;">
                        ${statusBadge}
                    </td>
                    <td style="padding:0.6rem 0.55rem; font-family:var(--font-mono); font-size:0.68rem; color:#94a3b8;">
                        <div>${s.last_run_formatted || 'Never'}</div>
                        <div style="color:#64748b;">${s.last_duration_s ? s.last_duration_s + 's' : ''}</div>
                    </td>
                    <td style="padding:0.6rem 0.65rem; font-size:0.7rem; color:#94a3b8; max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${s.last_summary || s.description || ''}">
                        ${s.last_summary || s.description || '-'}
                    </td>
                    <td style="padding:0.6rem 0.65rem; text-align:center;">
                        <div style="display:flex; align-items:center; justify-content:center; gap:0.3rem;">
                            <button type="button" onclick="app.triggerScheduleJob('${s.job_id}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.35rem; color:#38bdf8;" title="Trigger Execution Now">⚡</button>
                            <button type="button" onclick="app.toggleScheduleStatus('${s.job_id}', '${isAct ? 'paused' : 'active'}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.35rem;" title="${isAct ? 'Pause Flow' : 'Resume Flow'}">${isAct ? '⏸️' : '▶️'}</button>
                            <button type="button" onclick="app.openEditScheduleModal('${s.job_id}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.35rem;" title="Edit Flow Parameters">✏️</button>
                            <button type="button" onclick="app.deleteSchedule('${s.job_id}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.35rem; color:#f87171;" title="Delete Schedule">🗑️</button>
                        </div>
                    </td>
                </tr>
                `;
            });

            tbody.innerHTML = html;
        },

        openCreateScheduleModal() {
            const modal = document.getElementById('pgScheduleModal');
            if (!modal) return;
            const title = document.getElementById('pgSchedModalTitle');
            if (title) title.textContent = 'Configure Scheduled Flow';
            
            const inpId = document.getElementById('pgSchedInputJobId');
            if (inpId) { inpId.value = ''; inpId.disabled = false; }
            const inpName = document.getElementById('pgSchedInputJobName');
            if (inpName) inpName.value = '';
            const inpCat = document.getElementById('pgSchedInputCategory');
            if (inpCat) inpCat.value = 'Scanner';
            const inpList = document.getElementById('pgSchedInputTargetList');
            if (inpList) inpList.value = 'universe:NSE_ALL';
            const inpCustomT = document.getElementById('pgSchedInputCustomTickers');
            if (inpCustomT) inpCustomT.value = '';
            const customTRow = document.getElementById('pgSchedCustomTickersRow');
            if (customTRow) customTRow.style.display = 'none';
            const inpPreset = document.getElementById('pgSchedInputIntervalPreset');
            if (inpPreset) inpPreset.value = '300';
            const inpSec = document.getElementById('pgSchedInputIntervalSeconds');
            if (inpSec) inpSec.value = '300';
            const customIRow = document.getElementById('pgSchedCustomIntervalRow');
            if (customIRow) customIRow.style.display = 'none';
            const inpSession = document.getElementById('pgSchedInputMarketSession');
            if (inpSession) inpSession.value = 'all';
            const inpEn = document.getElementById('pgSchedInputEnabled');
            if (inpEn) inpEn.checked = true;
            
            this.syncSchedParamsJson();
            modal.style.display = 'flex';
        },

        openEditScheduleModal(jobId) {
            const modal = document.getElementById('pgScheduleModal');
            if (!modal) return;
            const s = this._automationSchedules.find(item => item.job_id === jobId);
            if (!s) return;

            const title = document.getElementById('pgSchedModalTitle');
            if (title) title.textContent = `Edit Flow: ${s.job_name || jobId}`;

            const inpId = document.getElementById('pgSchedInputJobId');
            if (inpId) { inpId.value = s.job_id; inpId.disabled = true; }
            const inpName = document.getElementById('pgSchedInputJobName');
            if (inpName) inpName.value = s.job_name || '';
            const inpCat = document.getElementById('pgSchedInputCategory');
            if (inpCat) inpCat.value = s.category || 'Scanner';
            const inpSec = document.getElementById('pgSchedInputIntervalSeconds');
            if (inpSec) inpSec.value = s.interval_seconds || 300;
            const inpPreset = document.getElementById('pgSchedInputIntervalPreset');
            if (inpPreset) {
                const standard = [30, 60, 300, 600, 1800, 3600, 7200, 86400];
                if (standard.includes(Number(s.interval_seconds))) {
                    inpPreset.value = String(s.interval_seconds);
                    const customIRow = document.getElementById('pgSchedCustomIntervalRow');
                    if (customIRow) customIRow.style.display = 'none';
                } else {
                    inpPreset.value = 'custom';
                    const customIRow = document.getElementById('pgSchedCustomIntervalRow');
                    if (customIRow) customIRow.style.display = 'block';
                }
            }
            const inpSession = document.getElementById('pgSchedInputMarketSession');
            if (inpSession) inpSession.value = s.market_session || (s.run_after_hours ? 'all' : 'market_hours_only');
            const inpParams = document.getElementById('pgSchedInputParams');
            if (inpParams) inpParams.value = s.params_json ? (typeof s.params_json === 'string' ? s.params_json : JSON.stringify(s.params_json)) : '';
            const inpEn = document.getElementById('pgSchedInputEnabled');
            if (inpEn) inpEn.checked = !!s.is_enabled;

            modal.style.display = 'flex';
        },

        closeScheduleModal() {
            const modal = document.getElementById('pgScheduleModal');
            if (!modal) return;
            modal.style.display = 'none';
        },

        onSchedTargetListChange(val) {
            const row = document.getElementById('pgSchedCustomTickersRow');
            if (row) row.style.display = val === 'custom_tickers' ? 'block' : 'none';
            this.syncSchedParamsJson();
        },

        onSchedIntervalPresetChange(val) {
            const row = document.getElementById('pgSchedCustomIntervalRow');
            if (row) row.style.display = val === 'custom' ? 'block' : 'none';
            if (val !== 'custom') {
                const inpSec = document.getElementById('pgSchedInputIntervalSeconds');
                if (inpSec) inpSec.value = val;
            }
        },

        syncSchedParamsJson() {
            const listVal = document.getElementById('pgSchedInputTargetList')?.value || 'universe:NSE_ALL';
            const limit = parseInt(document.getElementById('pgSchedInputLimit')?.value || '100', 10);
            const minScoreVal = document.getElementById('pgSchedInputMinScore')?.value;
            const minScore = minScoreVal ? parseFloat(minScoreVal) : null;
            const pool = document.getElementById('pgSchedInputPool')?.value || 'all';
            const device = document.getElementById('pgSchedInputDevice')?.value || 'auto';

            const params = {};
            if (listVal.startsWith('watchlist:')) {
                params.watchlist = listVal.replace('watchlist:', '');
            } else if (listVal.startsWith('universe:')) {
                params.universe = listVal.replace('universe:', '');
            } else if (listVal === 'custom_tickers') {
                const customStr = document.getElementById('pgSchedInputCustomTickers')?.value || '';
                params.tickers = customStr.split(',').map(t => t.trim()).filter(Boolean);
            }
            if (limit > 0) params.limit = limit;
            if (minScore !== null) params.min_score = minScore;
            if (pool && pool !== 'all') params.pool = pool;
            if (device && device !== 'auto') params.device = device;

            const inp = document.getElementById('pgSchedInputParams');
            if (inp) inp.value = JSON.stringify(params);
        },

        async submitScheduleModal() {
            const inpId = document.getElementById('pgSchedInputJobId');
            const jobId = inpId ? inpId.value.trim().toLowerCase().replace(/[^a-z0-9_]/g, '_') : '';
            if (!jobId) return;

            const name = document.getElementById('pgSchedInputJobName')?.value || jobId;
            const category = document.getElementById('pgSchedInputCategory')?.value || 'Scanner';
            const preset = document.getElementById('pgSchedInputIntervalPreset')?.value;
            const intervalSec = preset === 'custom' 
                ? parseInt(document.getElementById('pgSchedInputIntervalSeconds')?.value || '300', 10)
                : parseInt(preset || '300', 10);
            const marketSession = document.getElementById('pgSchedInputMarketSession')?.value || 'all';
            const runAfterHours = marketSession !== 'market_hours_only' ? 1 : 0;
            const paramsJson = document.getElementById('pgSchedInputParams')?.value || '{}';
            const isEnabled = document.getElementById('pgSchedInputEnabled')?.checked ? 1 : 0;

            const payload = {
                job_id: jobId,
                job_name: name,
                category: category,
                interval_seconds: intervalSec,
                market_session: marketSession,
                run_after_hours: runAfterHours,
                params_json: paramsJson,
                is_enabled: isEnabled,
            };

            const existing = this._automationSchedules.find(s => s.job_id === jobId);
            const method = existing ? 'PUT' : 'POST';
            const url = existing ? `${API_BASE}/api/v1/automation/schedules/${encodeURIComponent(jobId)}` : `${API_BASE}/api/v1/automation/schedules`;

            try {
                const res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    this.closeScheduleModal();
                    await this.loadAutomationSchedules();
                } else {
                    const err = await res.json();
                    alert(`Error saving schedule: ${err.detail || err.message || 'Unknown error'}`);
                }
            } catch (e) {
                console.error('Failed submitting schedule:', e);
                alert(`Request failed: ${e.message}`);
            }
        },

        async deleteSchedule(jobId) {
            if (!confirm(`Are you sure you want to delete schedule '${jobId}'?`)) return;
            try {
                const res = await fetch(`${API_BASE}/api/v1/automation/schedules/${encodeURIComponent(jobId)}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    await this.loadAutomationSchedules();
                } else {
                    const err = await res.json();
                    alert(`Error deleting schedule: ${err.detail || err.message}`);
                }
            } catch (e) {
                console.error('Delete schedule error:', e);
            }
        },

        async toggleScheduleStatus(jobId, targetStatus) {
            const endpoint = targetStatus === 'active' 
                ? `${API_BASE}/api/v1/automation/schedules/${encodeURIComponent(jobId)}/start`
                : `${API_BASE}/api/v1/automation/schedules/${encodeURIComponent(jobId)}/stop`;
            try {
                const res = await fetch(endpoint, { method: 'POST' });
                if (res.ok) {
                    await this.loadAutomationSchedules();
                }
            } catch (e) {
                console.error('Toggle schedule status error:', e);
            }
        },

        openScheduleLogsModal(jobId = '') {
            const modal = document.getElementById('pgScheduleLogsModal');
            if (!modal) return;
            modal.style.display = 'flex';
            this.loadScheduleLogs(jobId);
        },

        closeScheduleLogsModal() {
            const modal = document.getElementById('pgScheduleLogsModal');
            if (!modal) return;
            modal.style.display = 'none';
        },

        async loadScheduleLogs(jobId = '') {
            const tbody = document.getElementById('pgLogsTableBody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="padding:2rem; text-align:center; color:#64748b;"><div class="spinner" style="display:inline-block; margin-right:0.35rem;"></div> Loading execution logs...</td></tr>`;

            const filterSelect = document.getElementById('pgLogsJobFilter');
            if (filterSelect && this._automationSchedules) {
                let opts = '<option value="">All Background Jobs</option>';
                this._automationSchedules.forEach(s => {
                    opts += `<option value="${s.job_id}" ${jobId === s.job_id ? 'selected' : ''}>${s.job_name || s.job_id}</option>`;
                });
                filterSelect.innerHTML = opts;
            }

            try {
                const url = jobId 
                    ? `${API_BASE}/api/v1/automation/logs?job_id=${encodeURIComponent(jobId)}&limit=50`
                    : `${API_BASE}/api/v1/automation/logs?limit=50`;
                const res = await fetch(url);
                if (res.ok) {
                    const data = await res.json();
                    const logs = data.logs || [];
                    if (!tbody) return;

                    if (!logs.length) {
                        tbody.innerHTML = `<tr><td colspan="5" style="padding:2rem; text-align:center; color:#64748b;">No logs recorded yet.</td></tr>`;
                        return;
                    }

                    let html = '';
                    logs.forEach(l => {
                        const isSuccess = l.status === 'success';
                        const statusColor = isSuccess ? '#34d399' : '#f87171';
                        const statusBg = isSuccess ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
                        const statusBorder = isSuccess ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)';

                        html += `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                            <td style="padding:0.45rem 0.65rem; font-family:var(--font-mono); color:#94a3b8; font-size:0.68rem;">${l.started_ago || l.started_at || '-'}</td>
                            <td style="padding:0.45rem 0.55rem; font-weight:600; color:#f8fafc;">${l.job_name || l.job_id}</td>
                            <td style="padding:0.45rem 0.45rem;">
                                <span class="signal-badge" style="background:${statusBg}; color:${statusColor}; border:1px solid ${statusBorder}; font-size:0.62rem; padding:0.05rem 0.35rem; border-radius:3px;">${l.status}</span>
                            </td>
                            <td style="padding:0.45rem 0.45rem; font-family:var(--font-mono); color:#38bdf8;">${l.duration_s ? l.duration_s + 's' : '-'}</td>
                            <td style="padding:0.45rem 0.65rem; color:#cbd5e1; font-size:0.7rem;">${l.summary || l.error_details || '-'}</td>
                        </tr>
                        `;
                    });
                    tbody.innerHTML = html;
                }
            } catch (e) {
                console.error('Failed loading schedule logs:', e);
                if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="padding:2rem; text-align:center; color:#f87171;">Failed to load logs.</td></tr>`;
            }
        }
    });
})(); // end schedules IIFE
