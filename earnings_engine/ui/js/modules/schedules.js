// =========================================================================
// schedules — Nexus Dashboard Module (Automation Schedules & Job Monitor)
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
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
                console.debug('Failed loading schedules:', e);
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
            if (!this._automationSchedules) return;

            const hotSched = this._automationSchedules.find(s => s.job_id === 'breakout_hot_rescore');
            const warmSched = this._automationSchedules.find(s => s.job_id === 'breakout_warm_rescore');
            const coldSched = this._automationSchedules.find(s => s.job_id === 'breakout_cold_scan');
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
