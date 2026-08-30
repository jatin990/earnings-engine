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
                const res = await fetch(API_BASE + '/api/v1/automation/schedules');
                if (res.ok) {
                    const data = await res.json();
                    this._automationSchedules = data.schedules || [];
                    this.renderAutomationSchedules();
                    this.renderBreakoutSchedules();
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
                btn.innerHTML = '<span class="spinner" style="width:10px;height:10px;"></span> Running...';
            }
            try {
                const res = await fetch(API_BASE + `/api/v1/breakout-radar/schedules/${encodeURIComponent(jobId)}/trigger`, { method: 'POST' });
                if (res.ok) {
                    setTimeout(() => {
                        this.loadBreakoutSchedules();
                        this.loadBreakoutRadar();
                        this.loadBreakoutAuditLog();
                        if (btn) {
                            btn.disabled = false;
                            btn.innerHTML = '⚡ Run Now';
                        }
                    }, 2000);
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
                if (masterIcon) masterIcon.textContent = '⏳';
                masterBtn.style.opacity = '0.7';
            }
            if (modalBtn) {
                modalBtn.disabled = true;
                if (modalIcon) modalIcon.textContent = '⏳';
                modalBtn.innerHTML = '<span>⏳</span> Executing All 5 Strategies...';
            }

            try {
                const universe = this._breakoutUniverse || 'all';
                const minScore = parseFloat(document.getElementById('breakoutMinScore')?.value || '30');

                const res = await fetch(API_BASE + `/api/v1/breakout-radar/schedules/parallel-scan?universe=${encodeURIComponent(universe)}&min_score=${minScore}`, {
                    method: 'POST'
                });

                if (res.ok) {
                    const data = await res.json();
                    console.log('[BREAKOUT-PARALLEL] Result:', data);

                    // Refresh both radar candidates and schedule states
                    await this.loadBreakoutRadar();
                    await this.loadBreakoutAuditLog();
                    await this.loadBreakoutSchedules();
                    await this.loadAutomationSchedules();
                }
            } catch (e) {
                console.error('Error running parallel multi-strategy breakout scan:', e);
            } finally {
                this._isParallelScanRunning = false;
                if (masterBtn) {
                    masterBtn.disabled = false;
                    if (masterIcon) masterIcon.textContent = '🚀';
                    masterBtn.style.opacity = '1';
                }
                if (modalBtn) {
                    modalBtn.disabled = false;
                    modalBtn.innerHTML = '<span>⚡</span> Run All 5 Now';
                }
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
                        setTimeout(() => {
                            this.loadBreakoutRadar();
                            this.loadBreakoutAuditLog();
                        }, 2500);
                    }
                }
            } catch (e) {
                console.error('Trigger schedule error:', e);
            }
        }
    });
})(); // end schedules IIFE
