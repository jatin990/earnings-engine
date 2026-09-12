// =========================================================================
// ⚡ Custom Alert Rules Engine UI Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app.alerts = {
        rules: [],
        logs: [],
        currentTab: 'rules',
    };

    app.openAlertRulesModal = function() {
        const modal = document.getElementById('alertRulesModal');
        if (modal) modal.style.display = 'flex';
        app.switchAlertModalTab('rules');
        app.loadAlertRules();
    };

    app.closeAlertRulesModal = function() {
        const modal = document.getElementById('alertRulesModal');
        if (modal) modal.style.display = 'none';
    };

    app.switchAlertModalTab = function(tab) {
        app.alerts.currentTab = tab;
        ['rules', 'builder', 'logs'].forEach(t => {
            const btn = document.getElementById(`alertTabBtn-${t}`);
            const view = document.getElementById(`alertView${t.charAt(0).toUpperCase() + t.slice(1)}`);
            if (btn) {
                if (t === tab) {
                    btn.classList.add('active');
                    btn.style.background = 'rgba(244,63,94,0.15)';
                    btn.style.color = '#fb7185';
                } else {
                    btn.classList.remove('active');
                    btn.style.background = 'transparent';
                    btn.style.color = '#94a3b8';
                }
            }
            if (view) {
                view.style.display = t === tab ? 'flex' : 'none';
            }
        });

        if (tab === 'rules') app.loadAlertRules();
        if (tab === 'logs') app.refreshAlertLogs();
    };

    app.loadAlertRules = async function() {
        const container = document.getElementById('alertRulesListContainer');
        const countEl = document.getElementById('alertActiveRulesCount');
        if (!container) return;

        container.innerHTML = `<div style="padding:2rem;text-align:center;color:#64748b;font-size:0.78rem;">Loading configured alert rules...</div>`;

        try {
            const resp = await fetch(`${API_BASE}/api/v1/alerts/rules`);
            if (!resp.ok) throw new Error("Failed to fetch rules: " + resp.status);
            const data = await resp.json();
            const rules = data.rules || [];
            app.alerts.rules = rules;

            if (countEl) countEl.textContent = rules.filter(r => r.is_active).length;

            if (rules.length === 0) {
                container.innerHTML = `
                    <div style="text-align:center;padding:3rem 1rem;color:#64748b;">
                        <div style="font-size:2rem;margin-bottom:0.5rem;">⚡</div>
                        <strong style="color:#e2e8f0;display:block;margin-bottom:0.25rem;">No Alert Rules Configured</strong>
                        <p style="font-size:0.78rem;margin-bottom:1rem;">Set up rules to receive real-time notifications when stocks break out.</p>
                        <button type="button" onclick="app.switchAlertModalTab('builder')" class="btn btn-primary btn-sm" style="background:#e11d48;border-color:#f43f5e;">➕ Create First Rule</button>
                    </div>
                `;
                return;
            }

            container.innerHTML = rules.map(r => {
                const channels = typeof r.actions_json === 'string' ? JSON.parse(r.actions_json || '[]') : (r.actions_json || []);
                const chanBadges = channels.map(c => {
                    if (c === 'browser') return '<span class="signal-badge" style="background:rgba(56,189,248,0.15);color:#38bdf8;">🖥️ Browser</span>';
                    if (c === 'webhook') return '<span class="signal-badge" style="background:rgba(168,85,247,0.15);color:#c084fc;">🔗 Webhook</span>';
                    if (c === 'email') return '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;">📧 Email</span>';
                    return `<span class="signal-badge">${c}</span>`;
                }).join(' ');

                return `
                    <div style="background:#0d0d12;border:1px solid ${r.is_active ? 'rgba(244,63,94,0.2)' : 'rgba(255,255,255,0.06)'};border-radius:8px;padding:0.75rem 1rem;display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;">
                        <div style="display:flex;flex-direction:column;gap:0.3rem;">
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <strong style="color:#ffffff;font-size:0.9rem;">${r.name}</strong>
                                <span class="signal-badge" style="background:rgba(255,255,255,0.05);color:#cbd5e1;font-size:0.68rem;">${r.strategy}</span>
                                ${r.is_active ? '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-size:0.65rem;">ACTIVE</span>' : '<span class="signal-badge" style="background:rgba(148,163,184,0.15);color:#94a3b8;font-size:0.65rem;">PAUSED</span>'}
                            </div>
                            <div style="display:flex;gap:1rem;font-size:0.74rem;color:#94a3b8;flex-wrap:wrap;">
                                <span>Min Score: <strong style="color:#38bdf8;">${r.min_score}</strong></span>
                                <span>Volume Surge: <strong style="color:#34d399;">${r.min_volume_surge}x</strong></span>
                                <span>Triggers: <strong style="color:#ffffff;">${r.trigger_count || 0}</strong></span>
                            </div>
                            <div style="display:flex;gap:0.35rem;align-items:center;margin-top:0.15rem;">
                                ${chanBadges}
                            </div>
                        </div>
                        <div style="display:flex;align-items:center;gap:0.5rem;">
                            <button type="button" onclick="app.toggleAlertRuleActive('${r.id}', ${r.is_active ? 0 : 1})" class="btn btn-secondary btn-sm" style="font-size:0.72rem;padding:0.25rem 0.6rem;">
                                ${r.is_active ? '⏸️ Pause' : '▶️ Activate'}
                            </button>
                            <button type="button" onclick="app.deleteAlertRule('${r.id}')" class="btn-micro" style="color:#f87171;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.25);border-radius:4px;padding:0.25rem 0.5rem;cursor:pointer;" title="Delete Rule">
                                🗑️
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (err) {
            console.error("Error loading alert rules:", err);
            container.innerHTML = `<div style="text-align:center;padding:2rem;color:#f87171;">Failed to load alert rules.</div>`;
        }
    };

    app.saveAlertRuleFromBuilder = async function() {
        const nameInput = document.getElementById('alertRuleName');
        const stratInput = document.getElementById('alertRuleStrategy');
        const minScore = parseFloat(document.getElementById('alertMinScore').value || 75);
        const minSurge = parseFloat(document.getElementById('alertMinSurge').value || 2.0);
        const chanBrowser = document.getElementById('alertChanBrowser').checked;
        const chanWebhook = document.getElementById('alertChanWebhook').checked;
        const webhookUrl = document.getElementById('alertWebhookUrl').value.trim();

        if (!nameInput || !nameInput.value.trim()) {
            alert("Please provide a name for the alert rule.");
            return;
        }

        const actions = [];
        if (chanBrowser) actions.push('browser');
        if (chanWebhook) actions.push('webhook');

        const payload = {
            name: nameInput.value.trim(),
            strategy: stratInput ? stratInput.value : 'ALL',
            min_score: minScore,
            min_volume_surge: minSurge,
            tier: 'ALL',
            target_universe: 'ALL',
            max_entry_delay_pct: 3.0,
            actions_json: actions,
            webhook_url: webhookUrl || null,
            is_active: true,
        };

        try {
            const resp = await fetch(`${API_BASE}/api/v1/alerts/rules`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (resp.ok) {
                nameInput.value = '';
                app.switchAlertModalTab('rules');
            } else {
                alert("Failed to save rule: " + resp.statusText);
            }
        } catch (e) {
            console.error("Error creating alert rule:", e);
        }
    };

    app.toggleAlertRuleActive = async function(ruleId, targetState) {
        try {
            const resp = await fetch(`${API_BASE}/api/v1/alerts/rules/${ruleId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: !!targetState }),
            });
            if (resp.ok) {
                app.loadAlertRules();
            }
        } catch (e) {
            console.error("Error toggling rule:", e);
        }
    };

    app.deleteAlertRule = async function(ruleId) {
        if (!confirm("Are you sure you want to delete this alert rule?")) return;
        try {
            const resp = await fetch(`${API_BASE}/api/v1/alerts/rules/${ruleId}`, {
                method: 'DELETE',
            });
            if (resp.ok) {
                app.loadAlertRules();
            }
        } catch (e) {
            console.error("Error deleting rule:", e);
        }
    };

    app.testDispatchSampleAlert = async function() {
        const payload = {
            channel: 'browser',
            sample_ticker: 'TCS.NS',
            sample_strategy: 'Momentum Breakout',
            sample_score: 86.5,
            sample_surge: 2.8,
        };

        try {
            const resp = await fetch(`${API_BASE}/api/v1/alerts/test-dispatch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (resp.ok) {
                if ('Notification' in window && Notification.permission === 'granted') {
                    new Notification("⚡ Breakout Alert: TCS.NS", {
                        body: "Score: 86.5 | Volume Surge: 2.8x | Strategy: Momentum Breakout",
                        icon: "/favicon.ico",
                    });
                } else if ('Notification' in window && Notification.permission !== 'denied') {
                    Notification.requestPermission();
                }
                alert("⚡ Test dispatch ping sent successfully!");
            }
        } catch (e) {
            console.error("Error in test dispatch:", e);
        }
    };

    app.refreshAlertLogs = async function() {
        const container = document.getElementById('alertLogsListContainer');
        if (!container) return;

        container.innerHTML = `<div style="padding:2rem;text-align:center;color:#64748b;font-size:0.78rem;">Loading recent execution logs...</div>`;

        try {
            const resp = await fetch(`${API_BASE}/api/v1/alerts/logs?limit=30`);
            if (!resp.ok) throw new Error("Failed to fetch logs: " + resp.status);
            const data = await resp.json();
            const logs = data.logs || [];

            if (logs.length === 0) {
                container.innerHTML = `<div style="text-align:center;padding:2rem;color:#64748b;font-size:0.78rem;">No trigger execution events recorded yet.</div>`;
                return;
            }

            container.innerHTML = logs.map(l => `
                <div style="background:#0d0d12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.5rem 0.75rem;display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;">
                    <div style="display:flex;align-items:center;gap:0.5rem;">
                        <strong style="color:#ffffff;font-family:var(--font-mono);">${l.ticker}</strong>
                        <span style="color:#94a3b8;">${l.strategy}</span>
                        <span style="color:#38bdf8;font-weight:700;">Score: ${l.score}</span>
                        <span style="color:#34d399;">Surge: ${l.volume_surge}x</span>
                    </div>
                    <div style="color:#64748b;font-family:var(--font-mono);font-size:0.68rem;">
                        ${l.triggered_at}
                    </div>
                </div>
            `).join('');
        } catch (e) {
            console.error("Error loading alert logs:", e);
            container.innerHTML = `<div style="text-align:center;padding:2rem;color:#f87171;">Failed to load logs.</div>`;
        }
    };

    // Hotkey listener for Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('alertRulesModal');
            if (modal && modal.style.display === 'flex') {
                app.closeAlertRulesModal();
            }
        }
    });

})();
