// =========================================================================
// ⏱️ Automation Schedules & Background Job Monitor Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const schedulesModule = {
        _automationSchedules: [],
        _scheduleTimerStarted: false,

        async loadAutomationSchedules() {
            try {
                const res = await fetch(API_BASE + '/api/v1/automation/schedules');
                if (res.ok) {
                    const data = await res.json();
                    this._automationSchedules = data.schedules || [];
                    this.renderAutomationSchedules();
                    if (!this._scheduleTimerStarted) {
                        this._scheduleTimerStarted = true;
                        this.startScheduleTimer();
                    }
                }
            } catch (e) {
                console.debug('[SCHEDULES] Failed loading schedules:', e);
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
            }, 1000);
        },

        renderAutomationSchedules() {
            const containers = [
                document.getElementById('breakoutAutomationBar'),
                document.getElementById('catalystsAutomationBar')
            ];

            const formatCountdown = (sec) => {
                if (sec <= 0) return '<span style="color:#fbbf24;font-weight:700;">Running now...</span>';
                const m = Math.floor(sec / 60);
                const s = sec % 60;
                return `<span style="font-family:var(--font-mono);color:#38bdf8;font-weight:700;">in ${m}m ${s < 10 ? '0' : ''}${s}s</span>`;
            };

            const html = this._automationSchedules.map(s => {
                return `
                    <div style="display:flex;align-items:center;gap:0.45rem;background:#0d1117;border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:0.25rem 0.55rem;font-size:0.72rem;">
                        <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#34d399;box-shadow:0 0 6px #34d399;"></span>
                        <strong style="color:#f8fafc;">${s.name}:</strong>
                        <span>${formatCountdown(s.seconds_until_next)}</span>
                        <button type="button" onclick="app.triggerAutomationSchedule('${s.id}', this)" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.1rem 0.4rem;margin-left:0.25rem;" title="Run job immediately">⚡ Run</button>
                    </div>
                `;
            }).join('');

            containers.forEach(c => {
                if (c) c.innerHTML = html;
            });
        },

        async triggerAutomationSchedule(scheduleId, btnElement) {
            if (!scheduleId) return;
            if (btnElement) {
                btnElement.disabled = true;
                btnElement.textContent = 'Running...';
            }
            try {
                const res = await fetch(API_BASE + `/api/v1/automation/trigger/${encodeURIComponent(scheduleId)}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    await this.loadAutomationSchedules();
                    if (scheduleId.includes('breakout') && typeof this.loadBreakoutRadar === 'function') {
                        this.loadBreakoutRadar();
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
        }
    };

    // Export module
    window.SchedulesModule = schedulesModule;
    if (window.app) {
        Object.assign(window.app, schedulesModule);
    }
})();
