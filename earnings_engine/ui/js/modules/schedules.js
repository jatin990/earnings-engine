// =========================================================================
// ⏱️ Automation Schedules & Background Job Monitor Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const schedulesModule = {
        _automationSchedules: [],
        _engineStatus: { is_running: true },
        _scheduleTimerStarted: false,
        _editingJobId: null,

        async loadAutomationSchedules() {
            try {
                // Fetch schedules and engine status in parallel
                const [schedRes, engineRes] = await Promise.all([
                    fetch(API_BASE + '/api/v1/automation/schedules'),
                    fetch(API_BASE + '/api/v1/automation/engine').catch(() => null)
                ]);

                if (schedRes.ok) {
                    const data = await schedRes.json();
                    this._automationSchedules = data.schedules || [];
                }

                if (engineRes && engineRes.ok) {
                    const engData = await engineRes.json();
                    this._engineStatus = engData;
                }

                this.renderAutomationSchedules();

                if (!this._scheduleTimerStarted) {
                    this._scheduleTimerStarted = true;
                    this.startScheduleTimer();
                }
            } catch (e) {
                console.debug('[SCHEDULES] Failed loading schedules:', e);
            }
        },

        startScheduleTimer() {
            setInterval(() => {
                if (this._automationSchedules && this._automationSchedules.length) {
                    this._automationSchedules.forEach(s => {
                        const isActive = s.status === 'active' || s.status === 'running';
                        if (isActive && s.seconds_until_next > 0) {
                            s.seconds_until_next -= 1;
                        }
                    });
                    this.renderAutomationSchedules();
                }
            }, 1000);
        },

        renderAutomationSchedules() {
            if (!this._automationSchedules) return;

            // 1. Update mini timers on Breakout and News headers
            const hotSched = this._automationSchedules.find(s => s.job_id === 'breakout_hot_rescore');
            const warmSched = this._automationSchedules.find(s => s.job_id === 'breakout_warm_rescore');
            const coldSched = this._automationSchedules.find(s => s.job_id === 'breakout_cold_scan');
            const newsSched = this._automationSchedules.find(s => s.job_id === 'news_catalyst_harvest');

            const formatTimer = (s) => {
                if (!s) return 'Next run: <strong style="color:#38bdf8;">--</strong>';
                if (!s.is_enabled || s.status === 'paused') return '<span style="color:#94a3b8;font-weight:700;">⏸️ Paused</span>';
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

            // 2. Update Quant Playground Studio KPIs
            const totalCount = this._automationSchedules.length;
            const activeCount = this._automationSchedules.filter(s => (s.status === 'active' || s.status === 'running') && s.is_enabled).length;
            const runningCount = this._automationSchedules.filter(s => s.status === 'running').length;
            const totalRuns = this._automationSchedules.reduce((sum, s) => sum + (parseInt(s.total_runs) || 0), 0);

            const kpiTotalEl = document.getElementById('pgSchedKpiTotal');
            if (kpiTotalEl) kpiTotalEl.textContent = totalCount;
            const kpiActiveEl = document.getElementById('pgSchedKpiActive');
            if (kpiActiveEl) kpiActiveEl.textContent = activeCount;
            const kpiRunningEl = document.getElementById('pgSchedKpiRunning');
            if (kpiRunningEl) kpiRunningEl.textContent = runningCount;
            const kpiRunsEl = document.getElementById('pgSchedKpiRuns');
            if (kpiRunsEl) kpiRunsEl.textContent = totalRuns;

            // 3. Engine Status Badge & Toggle Button
            const engineRunning = this._engineStatus.is_running !== false;
            const badgeEl = document.getElementById('pgEngineStatusBadge');
            if (badgeEl) {
                badgeEl.textContent = engineRunning ? '🟢 ENGINE ACTIVE' : '⏸️ ENGINE PAUSED';
                badgeEl.style.background = engineRunning ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';
                badgeEl.style.color = engineRunning ? '#34d399' : '#f87171';
                badgeEl.style.borderColor = engineRunning ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)';
            }
            const toggleBtn = document.getElementById('pgToggleEngineBtn');
            if (toggleBtn) {
                toggleBtn.textContent = engineRunning ? '⏸️ Pause Engine' : '▶️ Resume Engine';
            }

            // 4. Render Playground Schedules Grid
            const tbody = document.getElementById('pgSchedulesTableBody');
            if (!tbody) return;

            if (this._automationSchedules.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">
                            No background schedules registered. Click <strong>＋ Add Scheduled Flow</strong> to create one.
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = this._automationSchedules.map(s => {
                const isRunning = s.status === 'running';
                const isPaused = !s.is_enabled || s.status === 'paused';
                const isError = s.status === 'error';

                let statusBadge = '';
                if (isRunning) {
                    statusBadge = '<span class="signal-badge" style="background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);font-size:0.65rem;">⚡ RUNNING</span>';
                } else if (isPaused) {
                    statusBadge = '<span class="signal-badge" style="background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.3);font-size:0.65rem;">⏸️ PAUSED</span>';
                } else if (isError) {
                    statusBadge = '<span class="signal-badge" style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.65rem;">🔴 ERROR</span>';
                } else {
                    statusBadge = '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.65rem;">🟢 ACTIVE</span>';
                }

                // Countdown formatting
                let countdownHtml = '';
                if (isRunning) {
                    countdownHtml = '<strong style="color:#38bdf8;">Executing now...</strong>';
                } else if (isPaused) {
                    countdownHtml = '<span style="color:#64748b;">Paused</span>';
                } else if (s.seconds_until_next <= 0) {
                    countdownHtml = '<span style="color:#fbbf24;font-weight:700;">Due now</span>';
                } else {
                    const sec = s.seconds_until_next;
                    const m = Math.floor(sec / 60);
                    const remSec = sec % 60;
                    const timeStr = m > 0 ? `${m}m ${remSec < 10 ? '0' : ''}${remSec}s` : `${remSec}s`;
                    countdownHtml = `<span style="font-family:var(--font-mono);color:#38bdf8;font-weight:700;">in ${timeStr}</span>`;
                }

                // Category badge
                const cat = s.category || 'Automation';
                const catBadge = `<span style="font-size:0.65rem;padding:0.1rem 0.4rem;border-radius:4px;background:rgba(255,255,255,0.05);color:#cbd5e1;border:1px solid rgba(255,255,255,0.1);">${cat}</span>`;

                const durationStr = s.last_duration_s ? `${s.last_duration_s}s` : '—';
                const lastRunStr = s.last_run_formatted ? `${s.last_run_formatted} (${durationStr})` : 'Never';

                return `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                        <td style="padding: 0.6rem 0.75rem;">
                            <div style="font-weight: 700; color: #f8fafc; font-size: 0.78rem;">${s.job_name || s.job_id}</div>
                            <div style="display:flex; align-items:center; gap:0.35rem; margin-top:0.15rem;">
                                <span style="font-family:var(--font-mono); font-size:0.66rem; color:#64748b;">${s.job_id}</span>
                                ${catBadge}
                            </div>
                        </td>
                        <td style="padding: 0.6rem 0.55rem; font-family: var(--font-mono); color: #93c5fd; font-weight: 700;">
                            ${s.interval_formatted || (s.interval_seconds + 's')}
                        </td>
                        <td style="padding: 0.6rem 0.55rem;">
                            ${countdownHtml}
                        </td>
                        <td style="padding: 0.6rem 0.55rem;">
                            ${statusBadge}
                        </td>
                        <td style="padding: 0.6rem 0.55rem; font-size: 0.7rem; color: #94a3b8;">
                            ${lastRunStr}
                        </td>
                        <td style="padding: 0.6rem 0.65rem; font-size: 0.7rem; color: #cbd5e1; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${s.last_summary || ''}">
                            ${s.last_summary || '<span style="color:#64748b;">No run recorded</span>'}
                        </td>
                        <td style="padding: 0.6rem 0.65rem; text-align: center;">
                            <div style="display: inline-flex; align-items: center; gap: 0.3rem;">
                                <button type="button" onclick="app.triggerScheduleJob('${s.job_id}', this)" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.45rem; background:rgba(56,189,248,0.1); color:#38bdf8; border-color:rgba(56,189,248,0.3);" title="Run immediately" ${isRunning ? 'disabled' : ''}>
                                    ⚡ Run
                                </button>
                                <button type="button" onclick="app.toggleScheduleActive('${s.job_id}', ${!isPaused})" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.4rem;" title="${isPaused ? 'Resume schedule' : 'Pause schedule'}">
                                    ${isPaused ? '▶️' : '⏸️'}
                                </button>
                                <button type="button" onclick="app.openEditScheduleModal('${s.job_id}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.4rem;" title="Edit schedule">
                                    ✏️
                                </button>
                                <button type="button" onclick="app.openScheduleLogsModal('${s.job_id}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.4rem;" title="View run logs">
                                    📜
                                </button>
                                <button type="button" onclick="app.deleteSchedule('${s.job_id}')" class="btn btn-secondary btn-sm" style="font-size:0.65rem; padding:0.15rem 0.35rem; color:#f87171; border-color:rgba(239,68,68,0.25);" title="Delete schedule">
                                    🗑️
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async toggleMasterSchedulerEngine() {
            const currentlyRunning = this._engineStatus.is_running !== false;
            const endpoint = currentlyRunning ? '/api/v1/automation/engine/stop' : '/api/v1/automation/engine/start';
            try {
                const res = await fetch(API_BASE + endpoint, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    this._engineStatus = data;
                    await this.loadAutomationSchedules();
                }
            } catch (e) {
                console.error('[SCHEDULES] Toggle engine error:', e);
            }
        },

        async triggerScheduleJob(jobId, btnElement) {
            if (!jobId) return;
            if (btnElement) {
                btnElement.disabled = true;
                btnElement.textContent = '...';
            }
            try {
                const res = await fetch(API_BASE + `/api/v1/automation/trigger?job_id=${encodeURIComponent(jobId)}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    await this.loadAutomationSchedules();
                    if (jobId.startsWith('breakout') && typeof this.loadBreakoutRadar === 'function') {
                        setTimeout(() => this.loadBreakoutRadar(), 1500);
                    }
                }
            } catch (e) {
                console.error('[SCHEDULES] Trigger error:', e);
            } finally {
                if (btnElement) {
                    btnElement.disabled = false;
                    btnElement.textContent = '⚡ Run';
                }
            }
        },

        async toggleScheduleActive(jobId, currentlyActive) {
            const endpoint = currentlyActive ? `/api/v1/automation/schedules/${encodeURIComponent(jobId)}/stop` : `/api/v1/automation/schedules/${encodeURIComponent(jobId)}/start`;
            try {
                const res = await fetch(API_BASE + endpoint, { method: 'POST' });
                if (res.ok) {
                    await this.loadAutomationSchedules();
                }
            } catch (e) {
                console.error('[SCHEDULES] Toggle status error:', e);
            }
        },

        async deleteSchedule(jobId) {
            if (!confirm(`Are you sure you want to delete scheduled flow '${jobId}'?`)) return;
            try {
                const res = await fetch(API_BASE + `/api/v1/automation/schedules/${encodeURIComponent(jobId)}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    await this.loadAutomationSchedules();
                }
            } catch (e) {
                console.error('[SCHEDULES] Delete error:', e);
            }
        },

        openCreateScheduleModal() {
            this._editingJobId = null;
            const titleEl = document.getElementById('pgSchedModalTitle');
            if (titleEl) titleEl.textContent = '➕ Create Scheduled Flow';

            const idInput = document.getElementById('pgSchedInputJobId');
            if (idInput) {
                idInput.value = '';
                idInput.disabled = false;
            }
            const nameInput = document.getElementById('pgSchedInputJobName');
            if (nameInput) nameInput.value = '';
            const catSelect = document.getElementById('pgSchedInputCategory');
            if (catSelect) catSelect.value = 'Breakout Radar';
            const presetSelect = document.getElementById('pgSchedInputIntervalPreset');
            if (presetSelect) presetSelect.value = '300';
            const customRow = document.getElementById('pgSchedCustomIntervalRow');
            if (customRow) customRow.style.display = 'none';
            const paramsInput = document.getElementById('pgSchedInputParams');
            if (paramsInput) paramsInput.value = '';
            const enabledInput = document.getElementById('pgSchedInputEnabled');
            if (enabledInput) enabledInput.checked = true;

            const modal = document.getElementById('pgScheduleModal');
            if (modal) modal.style.display = 'block';
        },

        openEditScheduleModal(jobId) {
            const sched = this._automationSchedules.find(s => s.job_id === jobId);
            if (!sched) return;

            this._editingJobId = jobId;
            const titleEl = document.getElementById('pgSchedModalTitle');
            if (titleEl) titleEl.textContent = `✏️ Edit Scheduled Flow: ${sched.job_name || jobId}`;

            const idInput = document.getElementById('pgSchedInputJobId');
            if (idInput) {
                idInput.value = sched.job_id;
                idInput.disabled = true; // Job ID cannot be changed
            }
            const nameInput = document.getElementById('pgSchedInputJobName');
            if (nameInput) nameInput.value = sched.job_name || sched.job_id;
            const catSelect = document.getElementById('pgSchedInputCategory');
            if (catSelect) catSelect.value = sched.category || 'Breakout Radar';

            const presetSelect = document.getElementById('pgSchedInputIntervalPreset');
            const customRow = document.getElementById('pgSchedCustomIntervalRow');
            const customInput = document.getElementById('pgSchedInputIntervalSeconds');

            const interval = sched.interval_seconds || 300;
            const commonIntervals = ['30', '60', '300', '600', '1800', '3600', '7200', '86400'];
            if (commonIntervals.includes(String(interval))) {
                if (presetSelect) presetSelect.value = String(interval);
                if (customRow) customRow.style.display = 'none';
            } else {
                if (presetSelect) presetSelect.value = 'custom';
                if (customRow) customRow.style.display = 'block';
                if (customInput) customInput.value = interval;
            }

            const paramsInput = document.getElementById('pgSchedInputParams');
            if (paramsInput) paramsInput.value = sched.params_json || '';
            const enabledInput = document.getElementById('pgSchedInputEnabled');
            if (enabledInput) enabledInput.checked = Boolean(sched.is_enabled);

            const modal = document.getElementById('pgScheduleModal');
            if (modal) modal.style.display = 'block';
        },

        closeScheduleModal() {
            const modal = document.getElementById('pgScheduleModal');
            if (modal) modal.style.display = 'none';
        },

        onSchedIntervalPresetChange(val) {
            const customRow = document.getElementById('pgSchedCustomIntervalRow');
            if (customRow) {
                customRow.style.display = val === 'custom' ? 'block' : 'none';
            }
        },

        async submitScheduleModal() {
            const idInput = document.getElementById('pgSchedInputJobId');
            const nameInput = document.getElementById('pgSchedInputJobName');
            const catSelect = document.getElementById('pgSchedInputCategory');
            const presetSelect = document.getElementById('pgSchedInputIntervalPreset');
            const customInput = document.getElementById('pgSchedInputIntervalSeconds');
            const paramsInput = document.getElementById('pgSchedInputParams');
            const enabledInput = document.getElementById('pgSchedInputEnabled');

            const jobId = (idInput ? idInput.value : '').trim();
            if (!jobId) return;

            let interval = 300;
            if (presetSelect && presetSelect.value === 'custom') {
                interval = parseInt(customInput?.value || '300', 10);
            } else if (presetSelect) {
                interval = parseInt(presetSelect.value, 10);
            }

            const payload = {
                job_id: jobId,
                job_name: nameInput ? nameInput.value.trim() : jobId,
                category: catSelect ? catSelect.value : 'Custom',
                interval_seconds: interval,
                params_json: paramsInput ? paramsInput.value.trim() : '',
                is_enabled: enabledInput ? enabledInput.checked : true
            };

            const submitBtn = document.getElementById('pgSchedSubmitBtn');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Saving...';
            }

            try {
                let res;
                if (this._editingJobId) {
                    res = await fetch(API_BASE + `/api/v1/automation/schedules/${encodeURIComponent(this._editingJobId)}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                } else {
                    res = await fetch(API_BASE + '/api/v1/automation/schedules', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                }

                if (res.ok) {
                    this.closeScheduleModal();
                    await this.loadAutomationSchedules();
                } else {
                    const err = await res.json();
                    alert(`Error saving schedule: ${err.detail || 'Unknown error'}`);
                }
            } catch (e) {
                console.error('[SCHEDULES] Save error:', e);
                alert(`Error saving schedule: ${e.message}`);
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = '💾 Save Schedule';
                }
            }
        },

        async openScheduleLogsModal(jobId = null) {
            const modal = document.getElementById('pgScheduleLogsModal');
            if (modal) modal.style.display = 'block';

            // Populate filter options with existing schedules
            const filterSelect = document.getElementById('pgLogsJobFilter');
            if (filterSelect) {
                filterSelect.innerHTML = `<option value="">All Background Jobs (${this._automationSchedules.length})</option>` +
                    this._automationSchedules.map(s => `<option value="${s.job_id}" ${jobId === s.job_id ? 'selected' : ''}>${s.job_name || s.job_id}</option>`).join('');
                if (jobId) filterSelect.value = jobId;
            }

            await this.loadScheduleLogs(jobId);
        },

        closeScheduleLogsModal() {
            const modal = document.getElementById('pgScheduleLogsModal');
            if (modal) modal.style.display = 'none';
        },

        async loadScheduleLogs(jobId = '') {
            const tbody = document.getElementById('pgLogsTableBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="5" style="padding:2rem;text-align:center;color:#64748b;"><div class="spinner" style="display:inline-block;margin-right:0.3rem;"></div> Loading execution logs...</td></tr>';

            try {
                const url = jobId ? `${API_BASE}/api/v1/automation/logs?job_id=${encodeURIComponent(jobId)}&limit=50` : `${API_BASE}/api/v1/automation/logs?limit=50`;
                const res = await fetch(url);
                if (res.ok) {
                    const data = await res.json();
                    const logs = data.logs || [];

                    if (logs.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="5" style="padding:2rem;text-align:center;color:#64748b;">No run logs recorded yet for this selection.</td></tr>';
                        return;
                    }

                    tbody.innerHTML = logs.map(l => {
                        const isSuccess = l.status === 'success';
                        const badge = isSuccess
                            ? '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-size:0.65rem;">✓ SUCCESS</span>'
                            : '<span class="signal-badge" style="background:rgba(239,68,68,0.15);color:#f87171;font-size:0.65rem;">✕ FAILED</span>';

                        const timeFormatted = (l.started_at || '').substring(11, 19);
                        const dateFormatted = (l.started_at || '').substring(0, 10);
                        const durStr = `${l.duration_s || 0}s`;

                        return `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <td style="padding: 0.5rem 0.65rem; font-family:var(--font-mono); font-size:0.68rem; color:#94a3b8;">
                                    ${dateFormatted} <strong>${timeFormatted}</strong>
                                    <div style="font-size:0.62rem; color:#64748b;">${l.started_ago || ''}</div>
                                </td>
                                <td style="padding: 0.5rem 0.55rem; font-weight:700; color:#f8fafc;">
                                    ${l.job_name || l.job_id}
                                    <div style="font-size:0.62rem; color:#64748b; font-family:var(--font-mono);">${l.job_id}</div>
                                </td>
                                <td style="padding: 0.5rem 0.45rem;">
                                    ${badge}
                                </td>
                                <td style="padding: 0.5rem 0.45rem; font-family:var(--font-mono); color:#93c5fd;">
                                    ${durStr}
                                </td>
                                <td style="padding: 0.5rem 0.65rem; color:#cbd5e1; font-size:0.7rem;">
                                    ${l.summary || '<span style="color:#64748b;">—</span>'}
                                    ${l.error_details ? `<div style="color:#f87171; font-size:0.65rem; margin-top:0.2rem;">${l.error_details}</div>` : ''}
                                </td>
                            </tr>
                        `;
                    }).join('');
                }
            } catch (e) {
                console.error('[SCHEDULES] Logs fetch error:', e);
                tbody.innerHTML = `<tr><td colspan="5" style="padding:2rem;text-align:center;color:#f87171;">Failed loading logs: ${e.message}</td></tr>`;
            }
        }
    };

    // Export module and attach to global app
    window.schedulesModule = schedulesModule;
    window.SchedulesModule = schedulesModule;

    if (window.app) {
        Object.assign(window.app, schedulesModule);
    } else {
        window.addEventListener('DOMContentLoaded', () => {
            if (window.app) {
                Object.assign(window.app, schedulesModule);
            }
        });
    }
})();
