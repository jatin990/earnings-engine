// =========================================================================
// customizer — Nexus Dashboard Module (Control Center, Themes & .env)
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
// =========================================================================
        // ⚙️ DASHBOARD CONTROL CENTER, THEMES & LOCAL .ENV MANAGER
        // =========================================================================

        const DASHBOARD_TABS_SCHEMA = [
            { key: 'results', label: 'Results', icon: '📊', desc: 'Corporate earnings report & financial results' },
            { key: 'monthfilter', label: 'Month Filter', icon: '🗓️', desc: 'Calendar timeline & upcoming announcements' },
            { key: 'scanner', label: 'Scanner', icon: '🔍', desc: 'Categorical breakout & earnings filter scanner' },
            { key: 'catalysts', label: 'Catalysts', icon: '📰', desc: 'Corporate filings, order wins, and news catalyst feed' },
            { key: 'gainers', label: 'Gainers & Patterns', icon: '🚀', desc: 'Top post-earnings movers and candle patterns' },
            { key: 'swing', label: 'Swing Setups', icon: '🔄', desc: 'High/low swing ranges and cycle timing oscillations' },
            { key: 'kronos', label: 'Kronos AI', icon: '🤖', desc: 'Multimodal AI deep learning 14-day price trajectory' },
            { key: 'consensus', label: 'AI Consensus', icon: '🧠', desc: 'Multi-model LLM ensemble forecasting & reasoning' },
            { key: 'playground', label: 'Playground', icon: '🧪', desc: 'Interactive prompt engineering & live backtesting sandbox' },
            { key: 'coverage', label: 'Data Coverage', icon: '📊', desc: 'Dataset health, cache freshness, and ticker coverage' },
            { key: 'industries', label: 'Industries', icon: '🏭', desc: 'Sector breakdown and industry performance moves' },
            { key: 'patterns', label: 'Patterns', icon: '📊', desc: 'Automated technical chart pattern recognition' },
            { key: 'buydip', label: 'Buy the Dip', icon: '🛒', desc: 'Oversold mean-reversion quality dip finder' },
            { key: 'backtest', label: 'Backtest', icon: '📈', desc: 'Strategy backtest evaluation and historical performance' },
            { key: 'watchlist', label: 'Watchlists', icon: '⭐', desc: 'Custom watchlists and universe portfolio management' },
        ];

        const FONT_PRESETS = {
            geist: {
                label: 'Geist & Geist Mono (Modern Minimalist)',
                sans: "'Geist', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                mono: "'Geist Mono', 'JetBrains Mono', monospace",
                heading: "'Geist', 'Space Grotesk', sans-serif"
            },
            inter: {
                label: 'Inter & JetBrains Mono (Precision Fintech)',
                sans: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                mono: "'JetBrains Mono', monospace",
                heading: "'Inter', sans-serif"
            },
            outfit: {
                label: 'Outfit & Geist Mono (Futuristic Luxury)',
                sans: "'Outfit', 'Inter', sans-serif",
                mono: "'Geist Mono', 'JetBrains Mono', monospace",
                heading: "'Outfit', sans-serif"
            },
            space: {
                label: 'Space Grotesk & JetBrains Mono (Cyber Tech)',
                sans: "'Space Grotesk', 'Inter', sans-serif",
                mono: "'JetBrains Mono', monospace",
                heading: "'Space Grotesk', sans-serif"
            },
            jakarta: {
                label: 'Plus Jakarta Sans & JetBrains Mono (Executive Glass)',
                sans: "'Plus Jakarta Sans', sans-serif",
                mono: "'JetBrains Mono', monospace",
                heading: "'Space Grotesk', 'Plus Jakarta Sans', sans-serif"
            }
        };

        const THEME_PRESETS = {
            obsidian: {
                '--bg': '#030712',
                '--card': 'rgba(15,23,42,0.85)',
                '--accent': '#3b82f6',
                '--green': '#10b981',
                '--red': '#f43f5e',
                '--light': '#f8fafc',
                '--muted': '#94a3b8'
            },
            sapphire: {
                '--bg': '#010510',
                '--card': 'rgba(8,16,36,0.85)',
                '--accent': '#06b6d4',
                '--green': '#10b981',
                '--red': '#f43f5e',
                '--light': '#f9fafb',
                '--muted': '#38bdf8'
            },
            cyberpunk: {
                '--bg': '#030a08',
                '--card': 'rgba(8,24,18,0.85)',
                '--accent': '#10b981',
                '--green': '#22c55e',
                '--red': '#f43f5e',
                '--light': '#fafafa',
                '--muted': '#34d399'
            },
            slate: {
                '--bg': '#090d16',
                '--card': 'rgba(15,23,42,0.85)',
                '--accent': '#60a5fa',
                '--green': '#34d399',
                '--red': '#fb7185',
                '--light': '#f8fafc',
                '--muted': '#94a3b8'
            }
        };

        app._customizer = {
            activeSubTab: 'tabs',
            tabVisibility: {},
            activeTheme: 'obsidian',
            activeFont: 'geist',
            customColors: {},
            envData: null,
            envSearchQuery: '',
            envCategory: 'ALL'
        };

        app.initCustomizer = function() {
            // Restore tab visibility from localStorage
            try {
                const savedTabs = localStorage.getItem('ee_tab_visibility');
                if (savedTabs) {
                    app._customizer.tabVisibility = JSON.parse(savedTabs);
                }
            } catch (e) {}

            // Restore font preset
            try {
                const savedFont = localStorage.getItem('ee_active_font') || 'geist';
                app.applyFontPreset(savedFont, false);
            } catch (e) {}

            // Restore theme & custom colors
            try {
                const savedTheme = localStorage.getItem('ee_active_theme') || 'obsidian';
                const savedColors = localStorage.getItem('ee_custom_colors');
                if (savedColors) {
                    app._customizer.customColors = JSON.parse(savedColors);
                }
                app.applyPresetTheme(savedTheme, false);
                if (app._customizer.customColors) {
                    Object.entries(app._customizer.customColors).forEach(([varName, val]) => {
                        document.documentElement.style.setProperty(varName, val);
                    });
                }
            } catch (e) {}

            // Apply tab visibility to DOM
            app.applyAllTabVisibilities();

            // Background sync with backend UI preferences
            fetch('/api/v1/config/ui-preferences')
                .then(r => r.ok ? r.json() : null)
                .then(prefs => {
                    if (prefs && prefs.tab_visibility && Object.keys(prefs.tab_visibility).length) {
                        app._customizer.tabVisibility = Object.assign({}, prefs.tab_visibility, app._customizer.tabVisibility);
                        app.applyAllTabVisibilities();
                    }
                })
                .catch(() => {});
        };

        app.openCustomizerModal = function(defaultSubTab = 'tabs') {
            const modal = document.getElementById('controlCenterModal');
            if (!modal) return;
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
            app.switchCustomizerTab(defaultSubTab || app._customizer.activeSubTab || 'tabs');
        };

        app.closeCustomizerModal = function() {
            const modal = document.getElementById('controlCenterModal');
            if (modal) modal.style.display = 'none';
            document.body.style.overflow = '';
        };

        app.switchCustomizerTab = function(subTab) {
            const tabKey = (subTab || 'tabs').toLowerCase();
            app._customizer.activeSubTab = tabKey;
            
            const tabMap = {
                'tabs': 'Tabs',
                'themes': 'Themes',
                'env': 'Env',
                'ratelimits': 'RateLimits',
                'keys': 'Keys',
                'audit': 'Audit',
            };
            
            // Toggle nav buttons and sections
            Object.keys(tabMap).forEach(t => {
                const suffix = tabMap[t];
                const navBtn = document.getElementById('ccNav' + suffix);
                const sec = document.getElementById('ccSection' + suffix);
                const isCurrent = (t === tabKey);
                if (navBtn) navBtn.classList.toggle('active', isCurrent);
                if (sec) sec.style.display = isCurrent ? 'block' : 'none';
            });

            if (tabKey === 'tabs') {
                app.renderCustomizerTabsGrid();
            } else if (tabKey === 'themes') {
                app.syncThemePickers();
            } else if (tabKey === 'env') {
                app.loadEnvVars();
            } else if (tabKey === 'ratelimits') {
                app.loadRateLimits();
            } else if (tabKey === 'keys') {
                app.loadPasscodesInCustomizer();
            } else if (tabKey === 'audit') {
                app.loadAccessAudit();
            }
        };

        app.loadRateLimits = async function() {
            const grid = document.getElementById('ccRateLimitsGrid');
            if (grid) {
                grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--muted); padding: 2rem;"><span class="loading-spinner"></span> Loading downstream rate limits and quotas...</div>';
            }

            try {
                const res = await fetch('/api/v1/config/ratelimits');
                const data = await res.json();
                const downstreams = data.downstreams || {};
                const opCounter = data.omniroute_counter || data.openrouter_counter || {};

                // Update Top Header Pill
                app.updateTopRateLimitPill(opCounter);

                // Update Control Center OmniRoute / AI Gateway Banner
                const bannerCount = document.getElementById('ccOpenRouter24hCount');
                const bannerRem = document.getElementById('ccOpenRouter24hRem');
                const tierBadge = document.getElementById('ccOpenRouterTierBadge');

                if (bannerCount) bannerCount.textContent = `${opCounter.current_24h || 0} / ${opCounter.allowed_24h || 2000}`;
                if (bannerRem) {
                    bannerRem.textContent = `${opCounter.remaining_24h || 0} reqs`;
                    bannerRem.style.color = (opCounter.remaining_24h <= 20) ? '#f87171' : ((opCounter.remaining_24h <= 60) ? '#fbbf24' : '#34d399');
                }
                if (tierBadge) {
                    tierBadge.textContent = 'OmniRoute Gateway Active';
                    tierBadge.style.background = 'rgba(16,185,129,0.2)';
                    tierBadge.style.color = '#34d399';
                }

                if (!grid) return;

                let html = '';
                Object.values(downstreams).forEach(ds => {
                    const statusBg = ds.status === 'throttled' ? 'rgba(239,68,68,0.2)' : (ds.status === 'warning' ? 'rgba(251,191,36,0.2)' : 'rgba(16,185,129,0.2)');
                    const statusColor = ds.status === 'throttled' ? '#f87171' : (ds.status === 'warning' ? '#fbbf24' : '#34d399');
                    const statusBorder = ds.status === 'throttled' ? 'rgba(239,68,68,0.4)' : (ds.status === 'warning' ? 'rgba(251,191,36,0.4)' : 'rgba(16,185,129,0.4)');

                    const tfHtml = Object.entries(ds.timeframes || {}).map(([tfKey, tf]) => {
                        const barColor = tf.utilization_pct >= 90 ? '#ef4444' : (tf.utilization_pct >= 70 ? '#fbbf24' : '#3b82f6');
                        return `
                            <div style="background: rgba(0,0,0,0.25); padding: 0.65rem 0.8rem; border-radius: 0.45rem; border: 1px solid rgba(255,255,255,0.06);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; font-size: 0.78rem;">
                                    <span style="color: #cbd5e1; font-weight: 600;">⏱️ ${tf.label}</span>
                                    <span style="font-family: monospace; font-weight: 700; color: ${barColor};">
                                        ${tf.current} / ${tf.allowed} ${ds.unit} (${tf.utilization_pct}%)
                                    </span>
                                </div>
                                <div style="width: 100%; height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; margin-bottom: 0.3rem;">
                                    <div style="width: ${Math.min(100, tf.utilization_pct)}%; height: 100%; background: ${barColor}; border-radius: 3px; transition: width 0.3s ease;"></div>
                                </div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--muted);">
                                    <span>Remaining: <strong style="color: #f8fafc;">${tf.remaining}</strong></span>
                                    <span>Cap: ${tf.allowed} ${ds.unit}</span>
                                </div>
                            </div>
                        `;
                    }).join('');

                    // Extra metadata rows for OpenRouter
                    let extraMetaHtml = '';
                    if (ds.key === 'openrouter' && ds.openrouter_key_info) {
                        const ki = ds.openrouter_key_info;
                        extraMetaHtml = `
                            <div style="background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.2); border-radius: 0.45rem; padding: 0.5rem 0.75rem; margin-top: 0.75rem; font-size: 0.75rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.4rem;">
                                <span>🔑 Key Label: <strong style="color: #60a5fa;">${ki.label || 'Default'}</strong></span>
                                <span>Usage: <strong style="color: #38bdf8;">$${Number(ki.usage || 0).toFixed(4)}</strong></span>
                                ${ki.limit ? `<span>Credit Cap: <strong>$${ki.limit}</strong></span>` : ''}
                            </div>
                        `;
                    }

                    html += `
                        <div class="card" style="margin: 0; padding: 1.15rem; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); display: flex; flex-direction: column; justify-content: space-between;">
                            <div>
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; gap: 0.5rem;">
                                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                                        <span style="font-size: 1.4rem;">${ds.icon}</span>
                                        <div>
                                            <h4 style="margin: 0; font-size: 0.95rem; color: #f8fafc;">${ds.service_name}</h4>
                                            <span style="font-size: 0.72rem; color: var(--muted);">${ds.description}</span>
                                        </div>
                                    </div>
                                    <span class="signal-badge" style="background: ${statusBg}; color: ${statusColor}; border: 1px solid ${statusBorder}; font-size: 0.72rem; padding: 0.2rem 0.55rem; white-space: nowrap;">
                                        ${ds.status_badge}
                                    </span>
                                </div>

                                <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.85rem;">
                                    ${tfHtml}
                                </div>

                                ${extraMetaHtml}
                            </div>

                            <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 0.75rem; margin-top: 0.85rem; border-top: 1px solid rgba(255,255,255,0.08); font-size: 0.72rem; color: var(--muted);">
                                <span>Max Utilization: <strong style="color: ${statusColor}; font-size: 0.82rem;">${ds.max_utilization_pct}%</strong></span>
                                <a href="${ds.docs_url}" target="_blank" rel="noopener noreferrer" style="color: #60a5fa; text-decoration: none;">Docs & Criteria ↗</a>
                            </div>
                        </div>
                    `;
                });

                grid.innerHTML = html;
            } catch (e) {
                console.error('Error loading rate limits:', e);
                if (grid) {
                    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--red); padding: 2rem;">Failed loading rate limits: ${e.message}</div>`;
                }
            }
        };

        app.updateTopRateLimitPill = async function(cachedCounter) {
            const quotaEl = document.getElementById('topOpenRouterQuota');
            const statusEl = document.getElementById('topRateLimitStatus');
            const pillEl = document.getElementById('topRateLimitPill');
            if (!quotaEl || !statusEl || !pillEl) return;

            let counter = cachedCounter;
            if (!counter) {
                try {
                    const res = await fetch('/api/v1/config/ratelimits');
                    const data = await res.json();
                    counter = data.openrouter_counter || {};
                } catch (e) {
                    return;
                }
            }

            const cur = counter.current_24h || 0;
            const allowed = counter.allowed_24h || 2000;
            const rem = counter.remaining_24h != null ? counter.remaining_24h : (allowed - cur);
            const util = counter.utilization_pct || 0;

            quotaEl.textContent = `OmniRoute: ${cur}/${allowed} reqs`;

            if (util >= 90 || rem <= 20) {
                statusEl.textContent = `🔴 ${rem} left · High`;
                statusEl.style.color = '#f87171';
                pillEl.style.borderColor = 'rgba(239, 68, 68, 0.5)';
                pillEl.style.background = 'rgba(239, 68, 68, 0.15)';
            } else if (util >= 70 || rem <= 60) {
                statusEl.textContent = `🟡 ${rem} left · Warning`;
                statusEl.style.color = '#fbbf24';
                pillEl.style.borderColor = 'rgba(251, 191, 36, 0.5)';
                pillEl.style.background = 'rgba(251, 191, 36, 0.15)';
            } else {
                statusEl.textContent = `🟢 ${rem} left · Healthy`;
                statusEl.style.color = '#34d399';
                pillEl.style.borderColor = 'rgba(59, 130, 246, 0.35)';
                pillEl.style.background = 'rgba(59, 130, 246, 0.12)';
            }
        };

        app.loadPasscodesInCustomizer = async function() {
            const tbody = document.getElementById('ccPasscodesTableBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:1.5rem;"><span class="loading-spinner"></span> Loading friend passcodes...</td></tr>';

            try {
                const res = await fetch('/api/v1/auth/codes');
                const data = await res.json();
                const list = data.passcodes || [];

                if (!list.length) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:1.5rem;">No passcodes found. Click Generate to create one.</td></tr>';
                    return;
                }

                tbody.innerHTML = list.map(item => {
                    const maxStr = item.max_uses ? `${item.use_count} / ${item.max_uses}` : `${item.use_count} / ♾️`;
                    let expDisplay = '<span style="color: #34d399; font-family: monospace; font-size: 0.75rem;">♾️ Permanent</span>';
                    if (item.expires_at) {
                        const expDate = new Date(item.expires_at);
                        const now = new Date();
                        const diffMs = expDate - now;
                        if (diffMs <= 0) {
                            expDisplay = '<span style="color: #f87171; font-weight: 700; font-family: monospace; font-size: 0.75rem;">⚠️ Expired</span>';
                        } else {
                            const diffHours = Math.round(diffMs / (1000 * 60 * 60));
                            if (diffHours < 24) {
                                expDisplay = `<span style="color: #fde047; font-family: monospace; font-size: 0.75rem;">⏳ ${diffHours}h left</span>`;
                            } else {
                                const diffDays = Math.round(diffHours / 24);
                                expDisplay = `<span style="color: #60a5fa; font-family: monospace; font-size: 0.75rem;">⏳ ${diffDays}d left</span>`;
                            }
                        }
                    }

                    return `
                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);">
                            <td style="padding: 0.65rem 0.8rem; font-family: monospace; font-weight: 700; color: #60a5fa;">${item.code}</td>
                            <td style="padding: 0.65rem 0.8rem; font-weight: 600; color: var(--light);">${item.label}</td>
                            <td style="padding: 0.65rem 0.8rem;">
                                <div style="display: flex; flex-wrap: wrap; gap: 0.3rem;">
                                    ${item.allowed_routes.map(r => `<span style="background: rgba(255,255,255,0.06); padding: 0.15rem 0.45rem; border-radius: 0.3rem; font-size: 0.72rem; color: #93c5fd;">${r}</span>`).join('')}
                                </div>
                            </td>
                            <td style="padding: 0.65rem 0.8rem; text-align: center; font-family: monospace; color: var(--muted);">${maxStr}</td>
                            <td style="padding: 0.65rem 0.8rem; text-align: center;">${expDisplay}</td>
                            <td style="padding: 0.65rem 0.8rem; text-align: right; white-space: nowrap;">
                                <button type="button" onclick="app.copyPasscodeLink('${item.code}')" class="btn btn-sm" style="background: rgba(56,189,248,0.15); color: #38bdf8; padding: 0.2rem 0.5rem; margin-right: 0.3rem;" title="Copy direct portal invite link">🔗 Link</button>
                                <button type="button" onclick="app.deletePasscodeInCustomizer('${item.code}')" class="btn btn-sm btn-danger" style="padding: 0.2rem 0.5rem;" title="Delete Passcode">🗑️</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (e) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--red);padding:1.5rem;">Failed loading passcodes: ${e.message}</td></tr>`;
            }
        };

        app.showAddPasscodeModal = function() {
            document.getElementById('ccNewPassLabel').value = '';
            document.getElementById('ccNewPassCode').value = '';
            if (document.getElementById('ccNewPassMaxUses')) document.getElementById('ccNewPassMaxUses').value = '0';
            if (document.getElementById('ccNewPassExpiry')) document.getElementById('ccNewPassExpiry').value = '30';
            document.getElementById('ccRouteDash').checked = true;
            document.getElementById('ccRouteCards').checked = true;
            document.getElementById('ccRoutePlay').checked = true;
            document.getElementById('ccRouteAdmin').checked = false;
            document.getElementById('addPasscodeModal').style.display = 'flex';
        };

        app.submitCreatePasscodeInCustomizer = async function() {
            const label = (document.getElementById('ccNewPassLabel')?.value || '').trim();
            const code = (document.getElementById('ccNewPassCode')?.value || '').trim();
            const maxUsesVal = parseInt(document.getElementById('ccNewPassMaxUses')?.value || '0', 10);
            const expiryVal = parseFloat(document.getElementById('ccNewPassExpiry')?.value || '30');

            if (!label) {
                alert('Please enter a friend name or label.');
                return;
            }

            const routes = [];
            if (document.getElementById('ccRouteDash')?.checked) routes.push('dashboard');
            if (document.getElementById('ccRouteCards')?.checked) routes.push('credit_card');
            if (document.getElementById('ccRoutePlay')?.checked) routes.push('playground');
            if (document.getElementById('ccRouteAdmin')?.checked) routes.push('admin');

            if (!routes.length) {
                alert('Please select at least one route.');
                return;
            }

            try {
                const res = await fetch('/api/v1/auth/codes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        label,
                        code: code || null,
                        allowed_routes: routes,
                        max_uses: maxUsesVal > 0 ? maxUsesVal : null,
                        expires_in_days: expiryVal > 0 ? expiryVal : null,
                    })
                });
                if (!res.ok) throw new Error('Failed to generate passcode');

                document.getElementById('addPasscodeModal').style.display = 'none';
                app.loadPasscodesInCustomizer();
            } catch (e) {
                alert(`Error creating passcode: ${e.message}`);
            }
        };

        app.deletePasscodeInCustomizer = async function(code) {
            if (!confirm(`Are you sure you want to revoke and delete passcode ${code}?`)) return;
            try {
                const res = await fetch(`/api/v1/auth/codes/${encodeURIComponent(code)}`, { method: 'DELETE' });
                if (!res.ok) throw new Error('Failed to delete passcode');
                app.loadPasscodesInCustomizer();
            } catch (e) {
                alert(e.message);
            }
        };

        app.copyPasscodeLink = function(code) {
            const link = `${window.location.origin}/portal?code=${code}`;
            navigator.clipboard.writeText(link);
            alert(`Copied direct portal invite link for ${code}:\n${link}`);
        };

        app.toggleGroupedTelemetryView = function() {
            app._customizer.showRawJson = false;
            app._customizer.telemetryGrouped = !(app._customizer.telemetryGrouped !== false);
            const btnGrouped = document.getElementById('ccToggleGroupedBtn');
            const btnRaw = document.getElementById('ccToggleEncryptedBtn');
            if (btnGrouped) {
                btnGrouped.style.background = app._customizer.telemetryGrouped ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.08)';
                btnGrouped.style.color = app._customizer.telemetryGrouped ? '#93c5fd' : 'var(--light)';
            }
            if (btnRaw) {
                btnRaw.style.background = 'rgba(255,255,255,0.08)';
                btnRaw.style.color = 'var(--light)';
                btnRaw.innerHTML = '📄 View Raw Decrypted JSON';
            }
            app.loadAccessAudit();
        };

        app.toggleEncryptedAuditView = function() {
            app._customizer.showRawJson = !app._customizer.showRawJson;
            const btnRaw = document.getElementById('ccToggleEncryptedBtn');
            const btnGrouped = document.getElementById('ccToggleGroupedBtn');
            if (btnRaw) {
                btnRaw.innerHTML = app._customizer.showRawJson ? '📊 View Table View' : '📄 View Raw Decrypted JSON';
                btnRaw.style.background = app._customizer.showRawJson ? 'rgba(59, 130, 246, 0.25)' : 'rgba(255,255,255,0.08)';
                btnRaw.style.color = app._customizer.showRawJson ? '#60a5fa' : 'var(--light)';
            }
            if (btnGrouped) {
                btnGrouped.style.background = 'rgba(255,255,255,0.08)';
                btnGrouped.style.color = 'var(--light)';
            }
            app.loadAccessAudit();
        };

        app.loadAccessAudit = async function() {
            const tableWrapper = document.getElementById('ccAuditTableWrapper');
            const tbody = document.getElementById('ccAuditTableBody');
            if (!tbody || !tableWrapper) return;

            const isRaw = app._customizer.showRawJson === true;
            const isGrouped = !isRaw && (app._customizer.telemetryGrouped !== false);
            
            // Adjust table header according to view mode
            const thead = tableWrapper.querySelector('thead');
            if (thead) {
                if (isRaw) {
                    thead.innerHTML = '<tr><th style="width: 60px;">ID</th><th style="width: 170px;">Timestamp</th><th>Decrypted JSON Payload</th></tr>';
                } else if (isGrouped) {
                    thead.innerHTML = '<tr><th>Machine & Hostname</th><th>IP Address</th><th style="text-align:center;">Hits / Access Count</th><th>Last Active / First Seen</th><th>Location & Coordinates</th><th>ISP / Network</th><th>Device & OS</th><th>Endpoints</th></tr>';
                } else {
                    thead.innerHTML = '<tr><th>Timestamp</th><th>IP Address</th><th>Machine / Hostname</th><th>Location & Coordinates</th><th>ISP / Org</th><th>Device & OS</th><th>Route</th></tr>';
                }
            }

            const colCount = isRaw ? 3 : (isGrouped ? 8 : 7);
            tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;color:var(--muted);padding:1.5rem;"><span class="loading-spinner"></span> Loading telemetry...</td></tr>`;

            try {
                const url = '/api/v1/system/telemetry?limit=300' + (isGrouped ? '&grouped=true' : '&grouped=false');
                const res = await fetch(url);
                const data = await res.json();

                if (!res.ok) {
                    tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;color:#ef4444;padding:1.5rem;">⚠️ Access Denied: ${data.detail || 'Insufficient permissions to view system telemetry.'}</td></tr>`;
                    return;
                }

                const records = data.records || [];

                if (!records.length) {
                    tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;color:var(--muted);padding:1.5rem;">No telemetry records captured yet.</td></tr>`;
                    return;
                }

                if (isRaw) {
                    tbody.innerHTML = records.map(r => {
                        const jsonStr = JSON.stringify(r.raw_decrypted || {}, null, 2);
                        return `
                            <tr>
                                <td style="font-family:monospace;color:var(--muted);font-weight:700;">#${r.id}</td>
                                <td style="font-family:monospace;white-space:nowrap;color:var(--muted);font-size:0.75rem;">${r.timestamp || '—'}</td>
                                <td>
                                    <div style="display:flex;flex-direction:column;gap:0.4rem;">
                                        <pre style="margin:0;max-height:180px;overflow-y:auto;background:rgba(0,0,0,0.6);padding:0.6rem 0.8rem;border-radius:0.4rem;font-family:monospace;font-size:0.75rem;color:#38bdf8;word-break:break-all;white-space:pre-wrap;border:1px solid rgba(56,189,248,0.25);">${jsonStr}</pre>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join('');
                } else if (isGrouped) {
                    tbody.innerHTML = records.map(r => {
                        const loc = [r.city, r.region, r.country].filter(x => x && x !== 'Unknown' && x !== '—').join(', ') || 'Unknown Location';
                        const coordsHtml = (r.lat && r.lon)
                            ? `<div style="margin-top:0.2rem;"><a href="https://maps.google.com/?q=${r.lat},${r.lon}" target="_blank" rel="noopener noreferrer" style="color:#38bdf8;font-size:0.72rem;text-decoration:none;display:inline-flex;align-items:center;gap:0.25rem;">🌐 ${r.coordinates} ↗</a></div>`
                            : '';

                        const epEntries = Object.entries(r.endpoints || {});
                        const epPills = epEntries.length
                            ? epEntries.map(([ep, count]) => `<span class="signal-badge" style="font-size:0.68rem;background:rgba(59,130,246,0.15);color:#93c5fd;margin-right:0.25rem;margin-bottom:0.2rem;display:inline-block;">${ep} (${count})</span>`).join('')
                            : `<span style="color:var(--muted);font-size:0.75rem;">/</span>`;

                        return `
                            <tr>
                                <td>
                                    <div><strong style="color:#38bdf8;font-family:monospace;font-size:0.85rem;">${r.machine_name || '—'}</strong></div>
                                    <div style="color:var(--muted);font-size:0.72rem;margin-top:0.15rem;">👤 ${r.system_user || '—'}</div>
                                </td>
                                <td><strong style="color:#60a5fa;font-family:monospace;font-size:0.85rem;">${r.ip_address || '—'}</strong></td>
                                <td style="text-align:center;">
                                    <span class="signal-badge" style="font-size:0.75rem;background:rgba(59,130,246,0.22);color:#93c5fd;border:1px solid rgba(59,130,246,0.45);padding:0.25rem 0.65rem;border-radius:9999px;font-weight:700;box-shadow:0 0 12px rgba(59,130,246,0.25);">
                                        ⚡ ${r.count}x Hits
                                    </span>
                                </td>
                                <td>
                                    <div style="font-family:monospace;white-space:nowrap;color:var(--light);font-weight:600;">${r.last_seen || '—'}</div>
                                    <div style="color:var(--muted);font-size:0.7rem;margin-top:0.15rem;">First: ${r.first_seen || '—'}</div>
                                </td>
                                <td><div><span>📍 ${loc}</span>${coordsHtml}</div></td>
                                <td><span style="color:var(--muted);">${r.isp || '—'}</span></td>
                                <td><span style="font-size:0.75rem;color:var(--text-muted);">${r.device_info || r.user_agent || '—'}</span></td>
                                <td><div style="max-width:260px;display:flex;flex-wrap:wrap;">${epPills}</div></td>
                            </tr>
                        `;
                    }).join('');
                } else {
                    tbody.innerHTML = records.map(r => {
                        const loc = [r.city, r.region, r.country].filter(x => x && x !== 'Unknown' && x !== '—').join(', ') || 'Unknown Location';
                        const coordsHtml = (r.lat && r.lon)
                            ? `<div style="margin-top:0.2rem;"><a href="https://maps.google.com/?q=${r.lat},${r.lon}" target="_blank" rel="noopener noreferrer" style="color:#38bdf8;font-size:0.72rem;text-decoration:none;display:inline-flex;align-items:center;gap:0.25rem;">🌐 ${r.coordinates} ↗</a></div>`
                            : '';
                        return `
                            <tr>
                                <td style="font-family:monospace;white-space:nowrap;color:var(--muted);">${r.timestamp || '—'}</td>
                                <td><strong style="color:#60a5fa;font-family:monospace;">${r.ip_address || '—'}</strong></td>
                                <td><div><span style="color:#60a5fa;font-weight:600;">${r.machine_name || '—'}</span></div><div style="color:var(--muted);font-size:0.72rem;margin-top:0.15rem;">👤 ${r.system_user || '—'}</div></td>
                                <td><div><span>📍 ${loc}</span>${coordsHtml}</div></td>
                                <td><span style="color:var(--muted);">${r.isp || '—'}</span></td>
                                <td><span style="font-size:0.75rem;">${r.device_info || r.user_agent || '—'}</span></td>
                                <td><span class="signal-badge" style="font-size:0.68rem;background:rgba(59,130,246,0.15);color:#93c5fd;">${r.endpoint || '/'}</span></td>
                            </tr>
                        `;
                    }).join('');
                }
            } catch (e) {
                tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;color:var(--red);padding:1.5rem;">Error loading telemetry: ${(e.message || e)}</td></tr>`;
            }
        };

        app.clearAccessAudit = async function() {
            if (!confirm('Are you sure you want to clear system telemetry records?')) return;
            try {
                await fetch('/api/v1/system/telemetry', { method: 'DELETE' });
                app.loadAccessAudit();
            } catch (e) {
                alert('Error clearing telemetry records: ' + e.message);
            }
        };

        app.renderCustomizerTabsGrid = function() {
            const container = document.getElementById('ccTabsGrid');
            if (!container) return;

            let html = '';
            DASHBOARD_TABS_SCHEMA.forEach(tab => {
                const isVisible = app._customizer.tabVisibility[tab.key] !== false; // Default true
                html += `
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid ${isVisible ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.08)'}; border-radius: 0.65rem; padding: 0.85rem; display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; transition: all 0.2s;">
                        <div style="display: flex; align-items: center; gap: 0.6rem; min-width: 0;">
                            <span style="font-size: 1.25rem;">${tab.icon}</span>
                            <div style="min-width: 0;">
                                <strong style="display: block; font-size: 0.88rem; color: ${isVisible ? 'var(--light)' : 'var(--muted)'};">${tab.label}</strong>
                                <span style="display: block; font-size: 0.72rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${tab.desc}</span>
                            </div>
                        </div>
                        <label style="position: relative; display: inline-block; width: 44px; height: 24px; flex-shrink: 0; cursor: pointer;">
                            <input type="checkbox" onchange="app.toggleTabVisibility('${tab.key}', this.checked)" ${isVisible ? 'checked' : ''} style="opacity: 0; width: 0; height: 0;">
                            <span style="position: absolute; cursor: pointer; inset: 0; background-color: ${isVisible ? '#3b82f6' : '#475569'}; border-radius: 24px; transition: .3s; display: block;">
                                <span style="position: absolute; content: ''; height: 18px; width: 18px; left: ${isVisible ? '23px' : '3px'}; bottom: 3px; background-color: white; border-radius: 50%; transition: .3s; display: block;"></span>
                            </span>
                        </label>
                    </div>
                `;
            });
            container.innerHTML = html;
        };

        app.toggleTabVisibility = function(tabKey, isVisible) {
            app._customizer.tabVisibility[tabKey] = isVisible;
            try {
                localStorage.setItem('ee_tab_visibility', JSON.stringify(app._customizer.tabVisibility));
            } catch (e) {}

            app.applyAllTabVisibilities();
            app.renderCustomizerTabsGrid();
            app.saveUIPreferencesToBackend();
        };

        app.setAllTabsVisibility = function(showAll) {
            DASHBOARD_TABS_SCHEMA.forEach(tab => {
                app._customizer.tabVisibility[tab.key] = showAll;
            });
            try {
                localStorage.setItem('ee_tab_visibility', JSON.stringify(app._customizer.tabVisibility));
            } catch (e) {}

            app.applyAllTabVisibilities();
            app.renderCustomizerTabsGrid();
            app.saveUIPreferencesToBackend();
        };

        app.applyAllTabVisibilities = function() {
            DASHBOARD_TABS_SCHEMA.forEach(tab => {
                const isVisible = app._customizer.tabVisibility[tab.key] !== false;
                
                // Toggle tab button in navbar
                const btn = document.querySelector(`button.tab-btn[data-tab="${tab.key}"]`) || document.getElementById(`tabBtn-${tab.key}`);
                if (btn) {
                    btn.style.display = isVisible ? 'inline-block' : 'none';
                } else {
                    document.querySelectorAll('.tab-btn').forEach(b => {
                        const onclick = b.getAttribute('onclick') || '';
                        if (onclick.includes("'" + tab.key + "'") || onclick.includes('"' + tab.key + '"')) {
                            b.style.display = isVisible ? 'inline-block' : 'none';
                        }
                    });
                }

                // Toggle tab content section
                const content = document.getElementById('tab-' + tab.key);
                if (content && !isVisible) {
                    content.classList.remove('active');
                }
            });

            // If active tab is now hidden, switch to the first visible tab
            const activeTab = localStorage.getItem('dashboard_active_tab') || 'results';
            if (app._customizer.tabVisibility[activeTab] === false) {
                const firstVisible = DASHBOARD_TABS_SCHEMA.find(t => app._customizer.tabVisibility[t.key] !== false);
                if (firstVisible) {
                    app.switchTab(firstVisible.key);
                }
            }
        };

        app.applyPresetTheme = function(themeName, persist = true) {
            const palette = THEME_PRESETS[themeName] || THEME_PRESETS.obsidian;
            app._customizer.activeTheme = themeName;
            app._customizer.customColors = Object.assign({}, palette);

            Object.entries(palette).forEach(([varName, val]) => {
                document.documentElement.style.setProperty(varName, val);
            });

            if (persist) {
                try {
                    localStorage.setItem('ee_active_theme', themeName);
                    localStorage.setItem('ee_custom_colors', JSON.stringify(app._customizer.customColors));
                } catch (e) {}
                app.saveUIPreferencesToBackend();
            }
            app.syncThemePickers();
        };

        app.onCustomColorInput = function(cssVar, hexValue) {
            document.documentElement.style.setProperty(cssVar, hexValue);
            app._customizer.customColors[cssVar] = hexValue;

            const valSpanId = 'val' + cssVar.replace('--', '').charAt(0).toUpperCase() + cssVar.replace('--', '').slice(1);
            const valSpan = document.getElementById(valSpanId);
            if (valSpan) valSpan.textContent = hexValue;

            try {
                localStorage.setItem('ee_custom_colors', JSON.stringify(app._customizer.customColors));
            } catch (e) {}
            app.saveUIPreferencesToBackend();
        };

        app.applyFontPreset = function(fontKey, persist = true) {
            const preset = FONT_PRESETS[fontKey] || FONT_PRESETS.geist;
            app._customizer.activeFont = fontKey;
            document.documentElement.style.setProperty('--font-sans', preset.sans);
            document.documentElement.style.setProperty('--font-mono', preset.mono);
            document.documentElement.style.setProperty('--font-heading', preset.heading);
            
            const fontSelect = document.getElementById('pickerFontPreset');
            if (fontSelect) fontSelect.value = fontKey;

            const sample = document.getElementById('fontSamplePreview');
            if (sample) {
                sample.style.fontFamily = preset.sans;
            }

            if (persist) {
                try {
                    localStorage.setItem('ee_active_font', fontKey);
                } catch (e) {}
                app.saveUIPreferencesToBackend();
            }
        };

        app.resetDefaultColors = function() {
            app.applyPresetTheme('obsidian', true);
            app.applyFontPreset('geist', true);
        };

        app.syncThemePickers = function() {
            const computed = getComputedStyle(document.documentElement);
            const fontSelect = document.getElementById('pickerFontPreset');
            if (fontSelect && app._customizer.activeFont) {
                fontSelect.value = app._customizer.activeFont;
            }
            const vars = ['--bg', '--card', '--accent', '--green', '--red', '--light'];
            vars.forEach(v => {
                const rawVal = computed.getPropertyValue(v).trim();
                const key = v.replace('--', '').charAt(0).toUpperCase() + v.replace('--', '').slice(1);
                const picker = document.getElementById('picker' + key);
                const valSpan = document.getElementById('val' + key);
                if (valSpan) valSpan.textContent = rawVal;
                if (picker && rawVal.startsWith('#') && rawVal.length === 7) {
                    picker.value = rawVal;
                }
            });
        };

        app.saveUIPreferencesToBackend = function() {
            fetch('/api/v1/config/ui-preferences', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tab_visibility: app._customizer.tabVisibility,
                    theme: app._customizer.activeTheme || 'obsidian',
                    custom_colors: app._customizer.customColors || {}
                })
            }).catch(() => {});
        };

        // ================= ENVIRONMENT VARIABLES CONTROLLER =================

        app.loadEnvVars = function() {
            const tbody = document.getElementById('ccEnvTableBody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 2rem; color: var(--muted);"><span class="loading-spinner"></span> Loading environment variables...</td></tr>';
            }

            fetch('/api/v1/config/env')
                .then(r => r.json())
                .then(data => {
                    app._customizer.envData = data;
                    
                    // Update environment status badge
                    const badge = document.getElementById('ccEnvBadge');
                    const warning = document.getElementById('ccEnvWarning');
                    const addBtn = document.getElementById('btnAddNewEnv');
                    
                    if (data.is_local) {
                        if (badge) {
                            badge.textContent = '🟢 Local Mode';
                            badge.style.background = 'rgba(16, 185, 129, 0.15)';
                            badge.style.color = '#34d399';
                            badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                        }
                        if (warning) warning.style.display = 'none';
                        if (addBtn) addBtn.style.display = 'flex';
                    } else {
                        if (badge) {
                            badge.textContent = '🔒 Cloud Mode (Read-Only)';
                            badge.style.background = 'rgba(239, 68, 68, 0.15)';
                            badge.style.color = '#f87171';
                            badge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                        }
                        if (warning) warning.style.display = 'block';
                        if (addBtn) addBtn.style.display = 'none';
                    }

                    app.renderEnvTable();
                })
                .catch(err => {
                    if (tbody) {
                        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 2rem; color: var(--red);">Failed to load environment variables: ${err.message}</td></tr>`;
                    }
                });
        };

        app.filterEnvVars = function() {
            app._customizer.envSearchQuery = (document.getElementById('ccEnvSearch')?.value || '').toLowerCase().trim();
            app._customizer.envCategory = document.getElementById('ccEnvCategoryFilter')?.value || 'ALL';
            app.renderEnvTable();
        };

        app.renderEnvTable = function() {
            const tbody = document.getElementById('ccEnvTableBody');
            if (!tbody || !app._customizer.envData) return;

            const isLocal = app._customizer.envData.is_local;
            let list = app._customizer.envData.env_vars || [];

            if (app._customizer.envCategory !== 'ALL') {
                list = list.filter(item => item.category === app._customizer.envCategory);
            }

            if (app._customizer.envSearchQuery) {
                list = list.filter(item => item.key.toLowerCase().includes(app._customizer.envSearchQuery));
            }

            if (!list.length) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 2rem; color: var(--muted);">No matching environment variables found.</td></tr>';
                return;
            }

            let html = '';
            list.forEach(item => {
                const masked = item.masked_value || item.value || '';
                const rawVal = item.value || '';
                const encodedVal = encodeURIComponent(rawVal);
                const safeKey = item.key.replace(/[^a-zA-Z0-9_]/g, '_');

                html += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.06); transition: background 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                        <td style="padding: 0.65rem 0.85rem; font-family: monospace; font-weight: 600; color: #93c5fd;">${item.key}</td>
                        <td style="padding: 0.65rem 0.85rem;">
                            <span style="background: rgba(255,255,255,0.06); padding: 0.15rem 0.5rem; border-radius: 0.3rem; font-size: 0.72rem; color: var(--muted);">${item.category}</span>
                        </td>
                        <td style="padding: 0.65rem 0.85rem; font-family: monospace; font-size: 0.8rem;">
                            <span id="envVal_${safeKey}" data-masked="${masked}" data-raw="${encodedVal}" data-revealed="false">${masked}</span>
                            ${item.is_secret ? `<button type="button" onclick="app.toggleRevealEnv('${safeKey}')" style="background: none; border: none; color: #60a5fa; cursor: pointer; margin-left: 0.4rem; font-size: 0.75rem;" title="Reveal/Hide">👁️</button>` : ''}
                        </td>
                        <td style="padding: 0.65rem 0.85rem; text-align: right; white-space: nowrap;">
                            ${isLocal ? `
                                <button type="button" onclick="app.showEditEnvModal('${item.key}', decodeURIComponent('${encodedVal}'))" class="btn btn-sm" style="background: rgba(59,130,246,0.15); color: #60a5fa; padding: 0.25rem 0.5rem; margin-right: 0.3rem;">✏️ Edit</button>
                                <button type="button" onclick="app.deleteEnvVar('${item.key}')" class="btn btn-sm" style="background: rgba(239,68,68,0.15); color: #f87171; padding: 0.25rem 0.5rem;">🗑️</button>
                            ` : `
                                <span style="font-size: 0.72rem; color: var(--muted);">Read-Only</span>
                            `}
                        </td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        };

        app.toggleRevealEnv = function(safeKey) {
            const span = document.getElementById('envVal_' + safeKey);
            if (!span) return;
            const isRevealed = span.getAttribute('data-revealed') === 'true';
            if (isRevealed) {
                span.textContent = span.getAttribute('data-masked');
                span.setAttribute('data-revealed', 'false');
            } else {
                span.textContent = decodeURIComponent(span.getAttribute('data-raw'));
                span.setAttribute('data-revealed', 'true');
            }
        };

        app.showAddEnvModal = function() {
            document.getElementById('editEnvTitle').textContent = '➕ Add Environment Variable';
            document.getElementById('editEnvKey').value = '';
            document.getElementById('editEnvKey').disabled = false;
            document.getElementById('editEnvVal').value = '';
            document.getElementById('editEnvModal').style.display = 'flex';
        };

        app.showEditEnvModal = function(key, value) {
            document.getElementById('editEnvTitle').textContent = `✏️ Edit ${key}`;
            document.getElementById('editEnvKey').value = key;
            document.getElementById('editEnvKey').disabled = true; // Key name locked when editing
            document.getElementById('editEnvVal').value = value;
            document.getElementById('editEnvModal').style.display = 'flex';
        };

        app.submitSaveEnvVar = function() {
            const key = document.getElementById('editEnvKey').value.trim();
            const value = document.getElementById('editEnvVal').value.trim();
            if (!key) {
                alert('Please enter a valid environment variable name.');
                return;
            }

            const btn = document.getElementById('btnSaveEnv');
            btn.disabled = true;
            btn.textContent = 'Saving...';

            fetch('/api/v1/config/env', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value })
            })
            .then(r => {
                if (!r.ok) return r.json().then(d => { throw new Error(d.detail || 'Save failed'); });
                return r.json();
            })
            .then(() => {
                document.getElementById('editEnvModal').style.display = 'none';
                app.loadEnvVars();
            })
            .catch(err => {
                alert(`Error saving environment variable: ${err.message}`);
            })
            .finally(() => {
                btn.disabled = false;
                btn.textContent = 'Save to .env';
            });
        };

        app.deleteEnvVar = function(key) {
            if (!confirm(`Are you sure you want to remove ${key} from your .env configuration?`)) return;

            fetch(`/api/v1/config/env/${encodeURIComponent(key)}`, {
                method: 'DELETE'
            })
            .then(r => {
                if (!r.ok) return r.json().then(d => { throw new Error(d.detail || 'Delete failed'); });
                return r.json();
            })
            .then(() => {
                app.loadEnvVars();
            })
            .catch(err => {
                alert(`Error deleting environment variable: ${err.message}`);
            });
        };

})(); // end customizer IIFE
