const API_BASE = window.location.origin;

        window.app = window.app || {};
        const app = window.app;

        Object.assign(app, {
            allTickers: [],
            resultsData: [],
            swingData: [],
            consensusMap: {},
            sortKey: 'earnings_date',
            sortDir: 'asc',

            _loadedScripts: new Set(),
            _scriptPromises: {},
            TAB_MODULES: {
                'home': [],
                'results': ['/static/js/modules/recalculate.js'],
                'monthfilter': ['/static/js/modules/consensus.js', '/static/js/modules/swing_range.js', '/static/js/modules/month_filter.js'],
                'scanner': ['/static/js/modules/consensus.js', '/static/js/modules/scanner.js'],
                'catalysts': ['/static/js/modules/schedules.js', '/static/js/modules/catalysts.js', '/static/js/modules/catalyst_consensus.js'],
                'premarket': ['/static/js/modules/premarket.js'],
                'gainers': ['/static/js/modules/consensus.js', '/static/js/modules/gainers.js'],
                'breakout': ['/static/js/modules/consensus.js', '/static/js/modules/schedules.js', '/static/js/modules/swing_range.js', '/static/js/modules/breakout_audit.js', '/static/js/modules/tracked_breakouts.js', '/static/js/modules/stock_rating.js', '/static/js/modules/stock_note.js', '/static/js/modules/breakout_radar.js'],
                'institutional': ['/static/js/modules/institutional.js'],
                'tri-confluence': ['/static/js/modules/tri_confluence.js'],
                'repeaters': ['/static/js/modules/repeaters.js'],
                'new-additions': ['/static/js/modules/new_additions.js'],
                'swing': ['/static/js/modules/swing_range.js', '/static/js/modules/swing.js'],
                'kronos': ['/static/js/modules/consensus.js'],
                'consensus': ['/static/js/modules/consensus.js'],
                'buydip': ['/static/js/modules/buy_dip.js'],
                'playground': ['/static/js/modules/schedules.js', '/static/js/modules/playground.js'],
                'watchlist': ['/static/js/modules/swing_range.js', '/static/js/modules/watchlist_modal.js', '/static/js/modules/watchlist.js'],
                'backtest': ['/static/js/modules/backtest.js'],
                'coverage': ['/static/js/modules/coverage.js'],
                'industries': ['/static/js/modules/industries.js'],
                'patterns': ['/static/js/modules/consensus.js', '/static/js/modules/patterns.js'],
                'options': ['/static/js/modules/options_hub.js']
            },

            loadScript(src) {
                if (!src) return Promise.resolve();
                const cleanSrc = src.split('?')[0];
                if (this._loadedScripts && this._loadedScripts.has(cleanSrc)) {
                    return Promise.resolve();
                }
                if (this._scriptPromises && this._scriptPromises[cleanSrc]) {
                    return this._scriptPromises[cleanSrc];
                }
                const version = '20260828_v23_modular';
                const versionedSrc = cleanSrc + (cleanSrc.includes('?') ? '&' : '?') + 'v=' + version;

                const p = new Promise((resolve, reject) => {
                    const existing = document.querySelector(`script[src*="${cleanSrc}"]`);
                    if (existing) {
                        this._loadedScripts.add(cleanSrc);
                        resolve();
                        return;
                    }
                    const s = document.createElement('script');
                    s.src = versionedSrc;
                    s.async = true;
                    s.onload = () => {
                        this._loadedScripts.add(cleanSrc);
                        delete this._scriptPromises[cleanSrc];
                        resolve();
                    };
                    s.onerror = (err) => {
                        delete this._scriptPromises[cleanSrc];
                        console.error(`[dynamic-loader] Failed to load script: ${versionedSrc}`, err);
                        reject(err);
                    };
                    document.head.appendChild(s);
                });

                if (!this._scriptPromises) this._scriptPromises = {};
                this._scriptPromises[cleanSrc] = p;
                return p;
            },

            async loadTabModules(tabName) {
                const modules = (this.TAB_MODULES && this.TAB_MODULES[tabName]) || [];
                for (const mod of modules) {
                    try {
                        await this.loadScript(mod);
                    } catch (e) {
                        console.warn(`[dynamic-loader] Error loading module ${mod} for tab ${tabName}:`, e);
                    }
                }
            },

            async openPageGuideModal(tabName) {
                await this.loadScript('/static/js/modules/page_guide.js');
                if (typeof app.openPageGuideModal === 'function') {
                    app.openPageGuideModal(tabName);
                }
            },
            closePageGuideModal() {
                const modal = document.getElementById('pageGuideModal');
                if (modal) modal.style.display = 'none';
            },
            async openSwingRangeModal(watchlist, ticker) {
                await this.loadScript('/static/js/modules/swing_range.js');
                if (typeof app.openSwingRangeModal === 'function') {
                    return app.openSwingRangeModal(watchlist, ticker);
                }
            },
            async openStockRatingModal(ticker) {
                await this.loadScript('/static/js/modules/stock_rating.js');
                if (typeof app.openStockRatingModal === 'function') {
                    return app.openStockRatingModal(ticker);
                }
            },
            async openStockNote(ticker, event) {
                await this.loadScript('/static/js/modules/stock_note.js');
                if (typeof app.openStockNote === 'function') {
                    return app.openStockNote(ticker, event);
                }
            },
            closeStockNote() {
                const modal = document.getElementById('stockIntelligenceNoteModal');
                if (modal) modal.style.display = 'none';
            },
            async openAddToWatchlistModal(ticker, price) {
                await this.loadScript('/static/js/modules/watchlist_modal.js');
                if (typeof app.openAddToWatchlistModal === 'function') {
                    return app.openAddToWatchlistModal(ticker, price);
                }
            },
            closeAddToWatchlistModal() {
                const modal = document.getElementById('addToWatchlistModal');
                if (modal) modal.style.display = 'none';
            },
            async openTradingAgentsWarRoom(ticker, event) {
                await this.loadScript('/static/js/modules/consensus.js');
                if (typeof app.openTradingAgentsWarRoom === 'function') {
                    return app.openTradingAgentsWarRoom(ticker, event);
                }
            },
            async openAiDetails(market, ticker, e) {
                await this.loadScript('/static/js/modules/consensus.js');
                await this.loadScript('/static/js/modules/swing_range.js');
                await this.loadScript('/static/js/modules/swing.js');
                await this.loadScript('/static/js/modules/month_filter.js');
                if (typeof app.openAiDetails === 'function') {
                    return app.openAiDetails(market, ticker, e);
                }
            },
            async loadSwing(e) {
                await this.loadScript('/static/js/modules/swing_range.js');
                await this.loadScript('/static/js/modules/swing.js');
                if (typeof app.loadSwing === 'function') {
                    return app.loadSwing(e);
                }
            },
            async filterSwingTable(query) {
                await this.loadScript('/static/js/modules/swing.js');
                if (typeof app.filterSwingTable === 'function') {
                    return app.filterSwingTable(query);
                }
            },

            async loadOverview() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/overview');
                    const data = await res.json();
                    if (typeof this.renderDatasetSummary === 'function') this.renderDatasetSummary(data.dataset);
                    if (typeof this.renderRefreshStatus === 'function') this.renderRefreshStatus(data.refresh_status);
                } catch (e) {
                    console.error('Error loading overview:', e);
                }
            },
            renderDatasetSummary(ds) {
                const el = document.getElementById('resultsDatasetSummary');
                if (!el) return;
                if (!ds || !ds.available) {
                    el.innerHTML = '<div class="card" style="margin:0">⚠️ Event dataset not available. Run <code>earnings-engine build-dataset</code> first.</div>';
                    return;
                }
                el.innerHTML = [
                    '<div class="metric"><span>Dataset Rows</span><strong>' + ds.rows + '</strong></div>',
                    '<div class="metric"><span>Tickers</span><strong>' + ds.tickers + '</strong></div>',
                    '<div class="metric"><span>Up-Label Rate</span><strong>' + (ds.up_label_rate !== null ? (ds.up_label_rate * 100).toFixed(1) + '%' : 'N/A') + '</strong></div>',
                    '<div class="metric"><span>Date Range</span><strong>' + (ds.date_range ? ds.date_range.min + ' → ' + ds.date_range.max : 'N/A') + '</strong></div>'
                ].join('');
            },
            renderRefreshStatus(status) {
                const el = document.getElementById('lastRefreshed');
                if (!el) return;
                if (!status || Object.keys(status).length === 0) {
                    el.textContent = 'Last refreshed: Never';
                    return;
                }
                let parts = Object.entries(status).map(([k, v]) => {
                    const time = v.last_refresh ? v.last_refresh.split(' ')[1] : '?';
                    return k + ': ' + time + ' (' + v.rows + ')';
                });
                el.textContent = 'Last refreshed — ' + parts.join(' · ');
            },
            maybeShowKronosPrompt() {
                const el = document.getElementById('kronosWidgets');
                if (!el) return;
                if (!el.innerHTML.trim()) {
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">' +
                        '<p style="margin:0 0 0.5rem 0;">Select a watchlist below, then click ▶ Run Predictions to load forecasts.</p>' +
                        '<p style="margin:0;color:var(--muted);font-size:0.8rem;">Kronos does not fetch anything by default — pick one of your managed watchlists to get started.</p>' +
                        '</div>';
                }
            },
            async loadConsensusCache() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/consensus/latest?limit=500');
                    const data = await res.json();
                    if (data && data.predictions) {
                        data.predictions.forEach(p => {
                            if (p.ticker) {
                                this.consensusMap[p.ticker.toUpperCase()] = p;
                            }
                        });
                    }
                } catch (e) {
                    console.warn('Failed to load consensus cache:', e);
                }
            },
            async loadTradingAgentsCache() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/trading-agents/all?limit=500');
                    const data = await res.json();
                    if (data && data.reports) {
                        data.reports.forEach(r => {
                            if (r.ticker) {
                                (this.tradingAgentsMap = this.tradingAgentsMap || {})[r.ticker.toUpperCase()] = r;
                            }
                        });
                    }
                } catch (e) {
                    console.warn('Failed to load TradingAgents cache:', e);
                }
            },
            renderConsensusBadge(ticker, market) {
                if (!ticker) return '—';
                const sym = String(ticker).trim().toUpperCase();
                const pred = (this.consensusMap || {})[sym];
                const safeMarket = (market || this.currentMarket || 'ALL').replace(/'/g, "\\'");
                const safeSym = sym.replace(/'/g, "\\'");
                const domId = 'consensus-cell-' + sym.replace(/[^A-Za-z0-9]/g, '_');

                if (pred && pred.consensus_direction) {
                    const dir = (pred.consensus_direction || 'NEUTRAL').toUpperCase();
                    const isBull = dir.includes('BULL');
                    const isBear = dir.includes('BEAR');
                    const color = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';
                    const bg = isBull ? 'rgba(16,185,129,0.18)' : isBear ? 'rgba(239,68,68,0.18)' : 'rgba(251,191,36,0.18)';
                    const border = isBull ? 'rgba(16,185,129,0.35)' : isBear ? 'rgba(239,68,68,0.35)' : 'rgba(251,191,36,0.35)';

                    const retPct = pred.consensus_return_pct != null ? pred.consensus_return_pct : (pred.expected_move_pct != null ? pred.expected_move_pct : null);
                    const retStr = retPct != null ? ((retPct > 0 ? '+' : '') + Number(retPct).toFixed(1) + '%') : '';
                    const strength = pred.consensus_strength != null ? Math.round(pred.consensus_strength) + '%' : '';
                    const agreeRatio = pred.agreement_ratio != null ? Math.round(pred.agreement_ratio * 100) : (pred.agreement_rate ? Math.round(pred.agreement_rate * 100) : null);
                    const action = pred.consensus_recommended_action || (isBull ? 'BUY' : isBear ? 'SELL' : 'HOLD');

                    const titleText = 'DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral: ' + dir + (retStr ? ' (' + retStr + ')' : '') +
                        (agreeRatio ? ' · ' + agreeRatio + '% Agreement' : '') +
                        (strength ? ' · ' + strength + ' Strength' : '') +
                        (action ? ' · Stance: ' + action : '') +
                        ' (Click to view full price action & 5-pillar targets)';

                    return '<div id="' + domId + '" style="display:inline-flex;align-items:center;gap:0.35rem;white-space:nowrap;">' +
                        '<span class="signal-badge" style="background:' + bg + ';color:' + color + ';border:1px solid ' + border + ';font-size:0.72rem;padding:0.18rem 0.5rem;font-weight:700;cursor:pointer;white-space:nowrap;" onclick="event.stopPropagation(); app.openAiDetails(\'' + safeMarket + '\', \'' + safeSym + '\', event)" title="' + titleText.replace(/"/g, '&quot;') + '">' +
                        '🤖 ' + dir + (retStr ? ' ' + retStr : '') +
                        '</span>' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(99,102,241,0.18);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);border-radius:0.3rem;" title="Re-run 4-Model AI Consensus for ' + safeSym + '">⚡</button>' +
                        '</div>';
                } else {
                    return '<div id="' + domId + '" style="white-space:nowrap;">' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.18rem 0.45rem;font-size:0.7rem;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);border-radius:0.3rem;font-weight:600;white-space:nowrap;" title="Run DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral 4-Model consensus for ' + safeSym + '">⚡ AI Consensus</button>' +
                        '</div>';
                }
            },
            renderTradingAgentsBadge(ticker, market) {
                if (!ticker) return '—';
                const sym = String(ticker).trim().toUpperCase();
                const rep = (this.tradingAgentsMap || {})[sym];
                const safeSym = sym.replace(/'/g, "\\'");
                const domId = 'trading-agents-cell-' + sym.replace(/[^A-Za-z0-9]/g, '_');

                if (rep && rep.action) {
                    const act = (rep.action || 'HOLD').toUpperCase();
                    const isBull = act.includes('BUY');
                    const isBear = act.includes('SELL');
                    const color = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';
                    const bg = isBull ? 'rgba(16,185,129,0.18)' : isBear ? 'rgba(239,68,68,0.18)' : 'rgba(251,191,36,0.18)';
                    const border = isBull ? 'rgba(16,185,129,0.35)' : isBear ? 'rgba(239,68,68,0.35)' : 'rgba(251,191,36,0.35)';
                    const score = rep.conviction_score || 50;
                    const rrr = rep.risk_reward_ratio ? ` · ${Number(rep.risk_reward_ratio).toFixed(1)}R` : '';

                    return '<div id="' + domId + '" style="display:inline-flex;align-items:center;gap:0.3rem;white-space:nowrap;">' +
                        '<span class="signal-badge" style="background:' + bg + ';color:' + color + ';border:1px solid ' + border + ';font-size:0.70rem;padding:0.15rem 0.45rem;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:0.25rem;" onclick="event.stopPropagation(); app.openTradingAgentsWarRoom(\'' + safeSym + '\', event)" title="TradingAgents 7-Agent Synthesis: ' + act + ' (' + score + '% Conviction' + rrr + ') · Click for 7-Agent War Room">' +
                        '🏛️ ' + act + ' (' + score + '%)' +
                        '</span>' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runTradingAgentsWorkflow(\'' + safeSym + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Re-run 7-Agent Trading Team for ' + safeSym + '">⚡</button>' +
                        '</div>';
                } else {
                    return '<div id="' + domId + '" style="white-space:nowrap;">' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runTradingAgentsWorkflow(\'' + safeSym + '\', this)" style="padding:0.16rem 0.42rem;font-size:0.68rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;font-weight:600;white-space:nowrap;" title="Run 7-Agent Trading Team (TauricResearch) for ' + safeSym + '">🏛️ TradingAgents</button>' +
                        '</div>';
                }
            },
            async runConsensusForTicker(ticker, btn) {
                await this.loadScript('/static/js/modules/consensus.js');
                if (typeof app.runConsensusForTicker === 'function') {
                    return app.runConsensusForTicker(ticker, btn);
                }
            },
            async runTradingAgentsWorkflow(ticker, btn) {
                await this.loadScript('/static/js/modules/consensus.js');
                if (typeof app.runTradingAgentsWorkflow === 'function') {
                    return app.runTradingAgentsWorkflow(ticker, btn);
                }
            },

            // ---------- Watchlist tab (multi-list manager) ----------
            // ---------- Watchlist tab (multi-list manager & OHLCV list view) ----------
        // [watchlist] -> extracted to modules/watchlist.js


            activeFetchControllers: {},
            tabDataCache: {},

            getTabCache(tabKey, maxAgeMs = 60000) {
                const entry = this.tabDataCache ? this.tabDataCache[tabKey] : null;
                if (!entry) return null;
                if (Date.now() - entry.ts < maxAgeMs) {
                    return entry.data;
                }
                delete this.tabDataCache[tabKey];
                return null;
            },

            setTabCache(tabKey, data) {
                if (!this.tabDataCache) this.tabDataCache = {};
                this.tabDataCache[tabKey] = { ts: Date.now(), data: data };
            },

            clearTabCache(tabKey = null) {
                if (!this.tabDataCache) return;
                if (tabKey) {
                    delete this.tabDataCache[tabKey];
                } else {
                    this.tabDataCache = {};
                }
            },

            apiFetch(url, options = {}, tabContext = null) {
                const tab = tabContext || this.currentTab || 'global';
                const controller = new AbortController();
                const reqId = 'req_' + tab + '_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
                const reqKey = reqId;

                const opts = { ...options, signal: controller.signal };
                opts.headers = { ...(opts.headers || {}), 'X-Request-ID': reqId, 'X-Tab-Context': tab };

                if (!this.activeFetchControllers) this.activeFetchControllers = {};
                this.activeFetchControllers[reqKey] = { controller, reqId, tabName: tab };

                return fetch(url, opts)
                    .catch(err => {
                        if (err.name === 'AbortError' || err.message === 'The user aborted a request.') {
                            console.debug(`[REQUEST-CANCELLED] ${tab} -> ${url}`);
                            return new Response(JSON.stringify({ success: false, aborted: true, message: 'Request cancelled' }), {
                                status: 499,
                                headers: { 'Content-Type': 'application/json' }
                            });
                        }
                        throw err;
                    })
                    .finally(() => {
                        if (this.activeFetchControllers && this.activeFetchControllers[reqKey]) {
                            delete this.activeFetchControllers[reqKey];
                        }
                    });
            },

            fetchWithAbort(taskName, url, options = {}) {
                return this.apiFetch(url, options, taskName);
            },

            cancelTabRequests(tabName, reason = 'Tab switched') {
                if (!this.activeFetchControllers) return;
                Object.keys(this.activeFetchControllers).forEach(key => {
                    const entry = this.activeFetchControllers[key];
                    if (entry && (entry.tabName === tabName || entry.tabName === ('tab-' + tabName))) {
                        try {
                            if (entry.controller) entry.controller.abort(reason);
                            if (entry.reqId) {
                                fetch('/api/v1/tasks/' + encodeURIComponent(entry.reqId) + '/cancel', { method: 'POST', keepalive: true }).catch(() => {});
                            }
                        } catch (e) {}
                        delete this.activeFetchControllers[key];
                    }
                });
            },

            cancelReportLoad(taskName) {
                this.cancelTabRequests(taskName, 'User cancelled');
                this.resetTaskLoadingUI(taskName, '⚠️ Request cancelled by user.');
            },

            cancelAllPendingRequests(reason = 'Tab switched') {
                if (!this.activeFetchControllers) return;
                Object.keys(this.activeFetchControllers).forEach(key => {
                    try {
                        const entry = this.activeFetchControllers[key];
                        if (entry) {
                            if (entry.controller) entry.controller.abort(reason);
                            if (entry.reqId) {
                                fetch('/api/v1/tasks/' + encodeURIComponent(entry.reqId) + '/cancel', { method: 'POST', keepalive: true }).catch(() => {});
                            }
                        }
                    } catch (e) {}
                    delete this.activeFetchControllers[key];
                });
                this.activeFetchControllers = {};
            },

            resetTaskLoadingUI(taskName, statusMessage) {
                if (taskName === 'results') {
                    const topBtn = document.getElementById('resultsLoadBtn');
                    if (topBtn) { topBtn.disabled = false; topBtn.innerHTML = '▶ Load Report'; }
                    const centerBtn = document.getElementById('resultsCenterLoadBtn');
                    if (centerBtn) { centerBtn.disabled = false; centerBtn.innerHTML = '▶ Load Results Report (±2 Months)'; }
                    const cancelBtn = document.getElementById('resultsCancelBtn');
                    if (cancelBtn) cancelBtn.style.display = 'none';
                    const statusEl = document.getElementById('resultsReportStatus');
                    if (statusEl && statusMessage) statusEl.textContent = statusMessage;
                } else if (taskName === 'monthfilter') {
                    const syncBtn = document.getElementById('mfSyncBtn');
                    if (syncBtn) { syncBtn.disabled = false; syncBtn.innerHTML = '🔄 Sync Delta'; }
                    const refreshBtn = document.getElementById('mfRefreshBtn');
                    if (refreshBtn) { refreshBtn.disabled = false; refreshBtn.innerHTML = '↻ Refresh'; }
                    const cancelBtn = document.getElementById('mfCancelBtn');
                    if (cancelBtn) cancelBtn.style.display = 'none';
                    const statusEl = document.getElementById('mfReportStatus');
                    if (statusEl && statusMessage) statusEl.textContent = statusMessage;
                }
            },

            getInitialTab() {
                // 1. Check URL Hash (e.g. #swing or #tab=swing or #institutional/investors)
                let hash = window.location.hash ? window.location.hash.replace(/^#/, '').trim() : '';
                if (hash.startsWith('tab=')) hash = hash.replace('tab=', '');
                
                // Check if hash points to institutional subpage
                if (hash.includes('institutional/investors') || hash === 'institutional-investors' || hash === 'smart-money') {
                    try { localStorage.setItem('ee_institutional_subpage', 'investors'); } catch (e) {}
                    hash = 'institutional';
                } else if (hash.includes('institutional/equities') || hash === 'institutional-equities') {
                    try { localStorage.setItem('ee_institutional_subpage', 'equities'); } catch (e) {}
                    hash = 'institutional';
                }

                // 2. Check URL Search Query (e.g. ?tab=swing)
                const params = new URLSearchParams(window.location.search);
                const queryTab = params.get('tab');
                if (params.get('sub')) {
                    try { localStorage.setItem('ee_institutional_subpage', params.get('sub')); } catch (e) {}
                }
                
                // 3. Check LocalStorage
                const storedTab = localStorage.getItem('dashboard_active_tab');

                const validTabs = ['home', 'results', 'monthfilter', 'scanner', 'catalysts', 'gainers', 'breakout', 'institutional', 'repeaters', 'new-additions', 'swing', 'watchlist', 'kronos', 'consensus', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
                
                if (hash && validTabs.includes(hash.toLowerCase())) return hash.toLowerCase();
                if (queryTab && validTabs.includes(queryTab.toLowerCase())) return queryTab.toLowerCase();
                if (storedTab && validTabs.includes(storedTab.toLowerCase())) return storedTab.toLowerCase();
                return 'home';
            },

            isMaster: null,

            async initAuthAndPermissions() {
                try {
                    const res = await fetch('/api/v1/auth/me');
                    if (res.ok) {
                        const data = await res.json();
                        if (data.authenticated && data.user) {
                            const user = data.user;
                            const isMaster = user.role === 'owner' || user.role === 'master' || (user.scopes && (user.scopes.includes('admin') || user.scopes.includes('*')));
                            this.isMaster = isMaster;
                            
                            const userBadge = document.getElementById('topUserBadge');
                            if (userBadge) {
                                userBadge.textContent = user.name || (isMaster ? 'Master Admin' : 'Verified Friend');
                            }
                            
                            this.applyRoleRestrictions();
                            return;
                        }
                    }
                } catch (e) {
                    console.debug('[AUTH] Session check error:', e);
                }
                
                // Fallback check from localStorage / default
                const friendName = localStorage.getItem('ee_friend_name');
                if (friendName && friendName !== 'Master Admin' && friendName !== 'Owner Account') {
                    this.isMaster = false;
                } else {
                    this.isMaster = true;
                }
                this.applyRoleRestrictions();
            },

            applyRoleRestrictions() {
                const isMaster = this.isMaster !== false;
                
                // 1. Topbar refresh earnings button
                const topRefreshBtn = document.getElementById('topRefreshEarningsBtn');
                if (topRefreshBtn) {
                    if (!isMaster) {
                        topRefreshBtn.style.display = 'none';
                        topRefreshBtn.disabled = true;
                        topRefreshBtn.title = 'Dataset refresh is restricted to Master Admin';
                    } else {
                        topRefreshBtn.style.display = 'inline-block';
                        topRefreshBtn.disabled = false;
                        topRefreshBtn.title = 'Refresh earnings dataset (Master only)';
                    }
                }
                
                // 2. Coverage tab "Fetch Missing" button
                const covMissingBtn = document.getElementById('coverageFetchMissingBtn');
                if (covMissingBtn) {
                    if (!isMaster) {
                        covMissingBtn.style.display = 'none';
                        covMissingBtn.disabled = true;
                        covMissingBtn.title = 'Incremental dataset ingest is restricted to Master Admin';
                    } else {
                        covMissingBtn.style.display = 'inline-block';
                        covMissingBtn.disabled = false;
                    }
                }
                
                // 3. Month filter "Sync Delta" button
                const mfSyncBtn = document.getElementById('mfSyncBtn');
                if (mfSyncBtn) {
                    if (!isMaster) {
                        mfSyncBtn.style.display = 'none';
                        mfSyncBtn.disabled = true;
                        mfSyncBtn.title = 'Dataset sync is restricted to Master Admin';
                    } else {
                        mfSyncBtn.style.display = 'inline-block';
                        mfSyncBtn.disabled = false;
                    }
                }

                // 4. All other elements marked with data-master-only
                document.querySelectorAll('[data-master-only="true"]').forEach(el => {
                    if (!isMaster) {
                        el.style.display = 'none';
                        el.setAttribute('disabled', 'true');
                    } else {
                        el.style.display = '';
                        el.removeAttribute('disabled');
                    }
                });
            },

            async init() {
                await this.initAuthAndPermissions();
                this.initCustomizer();
                this.bindKeyboardShortcuts();
                this._bindWatchlistSelectionPersistence();
                this._restoreBdControls?.();
                this._restorePatternsControls?.();

                // Defer non-critical background data fetches so initial Market Pulse load is instant and non-blocking
                setTimeout(() => {
                    this.populateWatchlistDropdowns();
                    this.loadOverview();
                    this.loadConsensusCache();
                    if (typeof this.loadTradingAgentsCache === 'function') {
                        this.loadTradingAgentsCache();
                    }
                    this.updateWatchlistFreshnessPill(localStorage.getItem('selectedGlobalWatchlist') || '');
                    this.initGlobalPriceRefresh?.();
                }, 1200);

                this.updateTopRateLimitPill();
                setInterval(() => {
                    this.updateTopRateLimitPill();
                }, 30000);

                const friendName = localStorage.getItem('ee_friend_name') || (this.isMaster ? 'Master Admin' : 'Verified Friend');
                const userBadge = document.getElementById('topUserBadge');
                if (userBadge) userBadge.textContent = friendName;
                
                const initialTab = this.getInitialTab();
                this.switchTab(initialTab, true, true);

                window.addEventListener('hashchange', () => {
                    const tab = this.getInitialTab();
                    this.switchTab(tab, false, false);
                });
                window.addEventListener('popstate', () => {
                    const tab = this.getInitialTab();
                    this.switchTab(tab, false, false);
                });
            },

            bindKeyboardShortcuts() {
                window.addEventListener('keydown', (e) => {
                    const tag = (e.target.tagName || '').toLowerCase();
                    const isInput = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;
                    
                    if (e.key === '/' && !isInput) {
                        e.preventDefault();
                        const searchEl = document.getElementById('tickerSearch');
                        if (searchEl) {
                            searchEl.focus();
                            searchEl.select();
                        }
                    } else if ((e.key === 'f' || e.key === 'F') && !isInput && !e.ctrlKey && !e.metaKey) {
                        e.preventDefault();
                        const findEl = document.getElementById('sidebarFind');
                        if (findEl) {
                            findEl.focus();
                            findEl.select();
                        }
                    } else if (e.key === 'Escape') {
                        const modal = document.getElementById('controlCenterModal');
                        if (modal && modal.style.display !== 'none') {
                            app.closeCustomizerModal();
                        }
                        const autoEl = document.getElementById('autocompleteDropdown');
                        if (autoEl) autoEl.style.display = 'none';
                        app.toggleMobileSidebar(false);
                        if (document.activeElement) document.activeElement.blur();
                    }
                });
            },

            toggleMobileSidebar(open = null) {
                const sidebar = document.getElementById('appSidebar') || document.querySelector('.app-sidebar');
                const backdrop = document.getElementById('sidebarBackdrop');
                if (!sidebar) return;
                
                const willOpen = (open !== null) ? !!open : !sidebar.classList.contains('mobile-open');
                sidebar.classList.toggle('mobile-open', willOpen);
                if (backdrop) {
                    backdrop.classList.toggle('active', willOpen);
                    backdrop.style.display = willOpen ? 'block' : 'none';
                }
                // Prevent body scrolling when sidebar drawer is open on mobile
                if (window.innerWidth <= 992) {
                    document.body.style.overflow = willOpen ? 'hidden' : '';
                }
            },

            filterSidebarTabs(query) {
                const q = (query || '').toLowerCase().trim();
                document.querySelectorAll('.sidebar-group').forEach(grp => {
                    let hasVisible = false;
                    grp.querySelectorAll('.sidebar-nav-item').forEach(item => {
                        const text = item.textContent.toLowerCase();
                        const isMatch = !q || text.includes(q);
                        item.style.display = isMatch ? 'flex' : 'none';
                        if (isMatch) hasVisible = true;
                    });
                    grp.style.display = hasVisible ? 'flex' : 'none';
                });
            },

            _bindWatchlistSelectionPersistence() {
                // Persist the selected watchlist/universe per tab so it survives
                // app restarts and is restored by default on the next load.
                const bindings = [
                    ['globalWatchlist', 'selectedGlobalWatchlist'],
                    ['resultsMarket', 'selectedWatchlist_results'],
                    ['swingMarket', 'selectedWatchlist_swing'],
                    ['coverageMarket', 'selectedWatchlist_coverage'],
                    ['kronosWatchlist', 'selectedWatchlist_kronos'],
                    ['bdMarket', 'selectedWatchlist_buydip'],
                    ['patternsMarket', 'selectedWatchlist_patterns'],
                    ['indMarket', 'selectedWatchlist_industries'],
                ];
                bindings.forEach(([id, key]) => {
                    const sel = document.getElementById(id);
                    if (!sel) return;
                    sel.addEventListener('change', () => {
                        try {
                            localStorage.setItem(key, sel.value);
                        } catch (e) {
                            console.error('Error saving watchlist selection:', e);
                        }
                    });
                });
            },

            _restoreWatchlistSelections() {
                const bindings = [
                    ['globalWatchlist', 'selectedGlobalWatchlist'],
                    ['resultsMarket', 'selectedWatchlist_results'],
                    ['swingMarket', 'selectedWatchlist_swing'],
                    ['coverageMarket', 'selectedWatchlist_coverage'],
                    ['kronosWatchlist', 'selectedWatchlist_kronos'],
                    ['bdMarket', 'selectedWatchlist_buydip'],
                    ['patternsMarket', 'selectedWatchlist_patterns'],
                    ['indMarket', 'selectedWatchlist_industries'],
                ];
                bindings.forEach(([id, key]) => {
                    const sel = document.getElementById(id);
                    if (!sel) return;
                    try {
                        const saved = localStorage.getItem(key);
                        if (saved !== null && Array.from(sel.options).some(o => o.value === saved)) {
                            sel.value = saved;
                        }
                    } catch (e) {}
                });
            },

            _watchlistNamesCache: null,
            _watchlistAllCache: null,

            async populateWatchlistDropdowns(forceRefresh = false) {
                try {
                    let data = this._watchlistNamesCache;
                    if (forceRefresh || !data) {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/names');
                        data = await res.json();
                        this._watchlistNamesCache = data;
                    }
                    const lists = data.watchlists || [];
                    const universes = data.universes || [];

                    // Standard Universes
                    let optionsHtml = '<optgroup label="⚡ Standard Universes">';
                    universes.forEach(u => {
                        optionsHtml += '<option value="' + u.name + '">' + u.title + '</option>';
                    });
                    optionsHtml += '</optgroup>';

                    if (lists.length) {
                        optionsHtml += '<optgroup label="⭐ Custom Watchlists">';
                        lists.forEach(w => {
                            const count = w.count || 0;
                            const name = w.name;
                            optionsHtml += '<option value="' + name + '">' + (w.title || name) + ' (' + count + ')</option>';
                        });
                        optionsHtml += '</optgroup>';
                    }

                    // Populate all watchlist dropdowns across tabs
                    const dropdownIds = [
                        'globalWatchlist',
                        'resultsMarket',
                        'swingMarket',
                        'coverageMarket',
                        'kronosWatchlist',
                        'bdMarket',
                        'patternsMarket',
                        'indMarket',
                        'btWatchlist',
                        'scannerWatchlistSelect',
                        'gainersMarketSelect'
                    ];

                    dropdownIds.forEach(id => {
                        const el = document.getElementById(id);
                        if (el) {
                            const currentVal = el.value;
                            el.innerHTML = optionsHtml;
                            if (currentVal) el.value = currentVal;
                        }
                    });

                    this._restoreWatchlistSelections();
                } catch (e) {
                    console.error('Error populating watchlist dropdowns:', e);
                }
            },

            onGlobalWatchlistChange(val) {
                localStorage.setItem('selectedGlobalWatchlist', val);
                localStorage.setItem('selectedWatchlist_kronos', val);
                
                // Update top navbar freshness pill for selected universe
                this.updateWatchlistFreshnessPill(val);

                // Sync Kronos, Backtest, Scanner, and Gainers selectors
                const targets = ['kronosWatchlist', 'btWatchlist', 'scannerWatchlistSelect', 'gainersMarketSelect'];
                targets.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.value = val;
                });

                // Trigger update based on active tab
                const activeTab = document.querySelector('.tab-btn.active')?.textContent || '';
                if (activeTab.includes('Kronos')) {
                    const isAudit = document.getElementById('kronosTabAudit')?.classList.contains('active');
                    const isList = document.getElementById('kronosTabList')?.classList.contains('active');
                    if (isAudit) {
                        this.loadKronosAudit();
                    } else if (isList) {
                        this.loadKronosList();
                    } else {
                        this.loadKronosLatest();
                    }
                } else if (activeTab.includes('Scanner')) {
                    this.scannerCategoriesData = [];
                    this.loadScanner();
                } else if (activeTab.includes('Catalysts')) {
                    this.loadCatalysts();
                } else if (activeTab.includes('Gainers')) {
                    this.refreshGainersTab();
                }
            },

            async updateWatchlistFreshnessPill(watchlistName) {
                const label = document.getElementById('topEarningsFreshnessLabel');
                const sub = document.getElementById('topEarningsFreshnessSub');
                if (!label) return;

                try {
                    const url = API_BASE + '/api/v1/earnings/freshness' + (watchlistName ? '?watchlist=' + encodeURIComponent(watchlistName) : '');
                    const res = await fetch(url);
                    const data = await res.json();

                    if (data.success) {
                        const rel = data.relative_time || 'Persistent Cache';
                        label.textContent = `Earnings: ${rel}`;
                        if (data.status === 'FRESH') {
                            label.style.color = '#34d399';
                        } else if (data.status === 'WARM') {
                            label.style.color = '#38bdf8';
                        } else {
                            label.style.color = '#f87171';
                        }

                        if (sub) {
                            if (data.last_updated) {
                                sub.textContent = `Updated: ${data.last_updated.substring(0, 16)}`;
                            } else {
                                sub.textContent = `${data.cached_tickers || 0}/${data.total_tickers || 0} cached`;
                            }
                        }
                    }
                } catch (e) {
                    console.debug('Error updating freshness pill:', e);
                }
            },

            async refreshCurrentWatchlistEarnings() {
                if (this.isMaster === false) {
                    alert('⚠️ Access Restricted: Refreshing large datasets is restricted to Master role.');
                    return;
                }
                const wl = document.getElementById('globalWatchlist')?.value || '';
                const btn = document.getElementById('topRefreshEarningsBtn');

                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="inline-block animate-spin mr-1">⟳</span> Refreshing...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/earnings/refresh-watchlist', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ watchlist: wl || null })
                    });
                    if (res.status === 403) {
                        alert('⚠️ Access Restricted: Refreshing large datasets is restricted to Master role.');
                        return;
                    }
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || 'Failed refreshing watchlist earnings');

                    alert(`✅ Refreshed earnings data for ${data.refreshed_count} tickers in ${data.watchlist}!`);
                    await this.updateWatchlistFreshnessPill(wl);

                    // If on results or swing tab, reload view
                    const activeTab = this.getInitialTab();
                    if (activeTab === 'results') {
                        this.loadResultsReport();
                    } else if (activeTab === 'swing') {
                        this.loadSwing();
                    }
                } catch (err) {
                    alert('Error refreshing watchlist earnings: ' + err.message);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '🔄 Refresh';
                    }
                }
            },

            onScannerWatchlistChange(val) {
                this.onGlobalWatchlistChange(val);
                const gEl = document.getElementById('globalWatchlist');
                if (gEl) gEl.value = val;
                this.scannerCategoriesData = [];
                this.loadScanner();
            },

            onGainersMarketChange(val) {
                this.onGlobalWatchlistChange(val);
                const gEl = document.getElementById('globalWatchlist');
                if (gEl) gEl.value = val;
                this.refreshGainersTab();
            },

            onResultsMarketChange(val) {
                this.onGlobalWatchlistChange(val);
                const gEl = document.getElementById('globalWatchlist');
                if (gEl) gEl.value = val;
                this.updateResultsMonthSummaryCards();
            },

            _tabLoadedAt: {},

            _shouldReloadTab(name, ttlSec = 60) {
                const now = Date.now();
                const last = this._tabLoadedAt[name] || 0;
                if (now - last > ttlSec * 1000) {
                    this._tabLoadedAt[name] = now;
                    return true;
                }
                return false;
            },

            async switchTab(name, updateUrl = true, isInitialLoad = false) {
                name = (name || 'home').toLowerCase().replace('#', '').replace('tab=', '');
                const validTabs = ['home', 'results', 'monthfilter', 'scanner', 'catalysts', 'premarket', 'options', 'gainers', 'breakout', 'institutional', 'tri-confluence', 'repeaters', 'new-additions', 'swing', 'watchlist', 'kronos', 'consensus', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
                if (!validTabs.includes(name)) name = 'home';

                this.currentTab = name;
                if (window.app) window.app.currentTab = name;

                // Abort any pending fetch requests when switching tabs
                this.cancelAllPendingRequests('Tab switched to ' + name);

                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                
                const targetContent = document.getElementById('tab-' + name);
                if (targetContent) targetContent.classList.add('active');

                // Sync legacy top buttons if any
                document.querySelectorAll('.tab-btn').forEach(el => {
                    const onclickAttr = el.getAttribute('onclick') || '';
                    if (onclickAttr.includes("'" + name + "'") || onclickAttr.includes('"' + name + '"') || el.textContent.toLowerCase().includes(name)) {
                        el.classList.add('active');
                    }
                });

                // Subtab state registry
                if (!app._subtabState) {
                    app._subtabState = {
                        catalysts: localStorage.getItem('subtab_catalysts') || 'feed',
                        breakout: localStorage.getItem('subtab_breakout') || 'scanner',
                        premarket: localStorage.getItem('subtab_premarket') || 'active',
                        gainers: localStorage.getItem('subtab_gainers') || 'gainers',
                        institutional: localStorage.getItem('subtab_institutional') || localStorage.getItem('ee_institutional_subpage') || 'equities',
                        kronos: localStorage.getItem('subtab_kronos') || 'latest'
                    };
                }

                // Sync Vercel Sidebar Active Item & Accordion Trees
                document.querySelectorAll('.sidebar-nav-item').forEach(el => {
                    const tabKey = el.getAttribute('data-tab');
                    const isActive = (tabKey === name);
                    el.classList.toggle('active', isActive);
                });

                document.querySelectorAll('.sidebar-nav-tree').forEach(tree => {
                    const parentTab = tree.getAttribute('data-parent-tab');
                    const isOpen = (parentTab === name);
                    tree.classList.toggle('open', isOpen);
                });

                // Update Breadcrumb Tab Title
                const bcEl = document.getElementById('topbarBreadcrumbTab');
                if (bcEl) {
                    const titles = {
                        'home': '🌐 Market Pulse',
                        'results': 'Results Ledger',
                        'monthfilter': 'Month Filter',
                        'scanner': 'Scanner',
                        'catalysts': 'Catalysts & News',
                        'premarket': '🌅 Pre-Market Setups',
                        'options': '⚡ Option Chain & Derivatives',
                        'gainers': 'Gainers & Breakouts',
                        'breakout': '⚡ Breakout Radar',
                        'institutional': '🏛️ Institutional Flows',
                        'tri-confluence': '🔗 Inst-Earnings Synergy',
                        'repeaters': '🔁 Quarter Repeaters',
                        'new-additions': '🆕 Recent Additions & IPOs',
                        'swing': 'Swing Ranges',
                        'kronos': 'Kronos 14D Forecast',
                        'consensus': '4-Model Consensus',
                        'buydip': 'Buy the Dip',
                        'playground': 'Quant Playground',
                        'watchlist': 'Watchlist Hub',
                        'backtest': 'Backtest Engine',
                        'coverage': 'Data Coverage',
                        'industries': 'Industries & Multiples',
                        'patterns': 'Technical Patterns'
                    };
                    bcEl.textContent = titles[name] || name;
                }

                // Update URL hash without page reload
                if (updateUrl && window.location.hash !== '#' + name) {
                    try {
                        history.replaceState(null, '', '#' + name);
                    } catch (e) {
                        window.location.hash = name;
                    }
                }
                try {
                    localStorage.setItem('dashboard_active_tab', name);
                } catch (e) {}

                // Sync tab-specific watchlist/universe dropdown with global selection
                const gWl = document.getElementById('globalWatchlist')?.value || localStorage.getItem('selectedGlobalWatchlist');
                if (gWl) {
                    const tabWlMap = {
                        'results': 'resultsMarket',
                        'monthfilter': 'mfMarket',
                        'scanner': 'scannerWatchlistSelect',
                        'gainers': 'gainersMarketSelect',
                        'swing': 'swingMarket',
                        'coverage': 'coverageMarket',
                        'industries': 'indMarket',
                        'patterns': 'patternsMarket',
                        'buydip': 'bdMarket',
                        'backtest': 'btWatchlist',
                        'kronos': 'kronosWatchlist'
                    };
                    const targetSel = document.getElementById(tabWlMap[name]);
                    if (targetSel && Array.from(targetSel.options).some(o => o.value === gWl)) {
                        targetSel.value = gWl;
                    }
                }

                // Dynamically load on-demand modules required for this tab
                await this.loadTabModules(name);

                // Lazy-initialize client UI components on first visit without firing heavy backend scans
                if (name === 'home') {
                    if (typeof this.loadMarketPulseData === 'function') this.loadMarketPulseData();
                }
                if (name === 'results') {
                    this.updateResultsMonthSummaryCards();
                }
                if (name === 'watchlist' && (!this.watchlistTab.customLists || !this.watchlistTab.customLists.length)) {
                    this.watchlistTab.load();
                }
                if (name === 'kronos') {
                    this.maybeShowKronosPrompt();
                }
                if (name === 'playground') {
                    if (typeof this.loadPlaygroundApiUsage === 'function') {
                        this.loadPlaygroundApiUsage();
                    }
                    if (typeof this.loadAutomationSchedules === 'function') {
                        this.loadAutomationSchedules();
                    }
                    if (this.pg && !this.pg._initialized) {
                        this.pg.init();
                        this.pg._initialized = true;
                    }
                    if (this.pgLocalAi && (!this.pgLocalAi._candidates || !this.pgLocalAi._candidates.length)) {
                        this.pgLocalAi.loadCandidates();
                    }
                }
                if (name === 'backtest') {
                    this.initBacktestTab();
                }
                if (name === 'breakout') {
                    const activeSub = (app._subtabState && app._subtabState['breakout']) || localStorage.getItem('subtab_breakout') || 'scanner';
                    if (typeof this.switchBreakoutSubtab === 'function') {
                        this.switchBreakoutSubtab(activeSub);
                    }
                    if (!this._breakoutLoaded) {
                        this._breakoutLoaded = true;
                    }
                    this.loadAutomationSchedules();
                    this.loadBreakoutAuditLog();
                }
                if (name === 'catalysts') {
                    this.loadAutomationSchedules();
                    const activeSub = (app._subtabState && app._subtabState['catalysts']) || localStorage.getItem('subtab_catalysts') || 'feed';
                    if (typeof this.switchCatalystsSubtab === 'function') {
                        this.switchCatalystsSubtab(activeSub);
                    } else if (typeof this.loadCatalysts === 'function') {
                        this.loadCatalysts();
                    }
                }
                if (name === 'premarket') {
                    // Redirect premarket tab to catalysts hub with premarket subtab
                    const activeSub = (app._subtabState && app._subtabState['premarket'] === 'outcomes') ? 'premarket-outcomes' : 'premarket';
                    if (typeof this.switchCatalystsSubtab === 'function') {
                        this.switchCatalystsSubtab(activeSub);
                    } else {
                        const pmSub = (app._subtabState && app._subtabState['premarket']) || localStorage.getItem('subtab_premarket') || 'active';
                        if (typeof this.switchPremarketView === 'function') {
                            this.switchPremarketView(pmSub);
                        }
                        if (typeof this.loadPremarketSetups === 'function') {
                            this.loadPremarketSetups();
                        }
                    }
                }
                if (name === 'options') {
                    if (typeof app.initOptionsHub === 'function') {
                        app.initOptionsHub();
                    }
                }
                if (name === 'gainers') {
                    const activeSub = (app._subtabState && app._subtabState['gainers']) || localStorage.getItem('subtab_gainers') || 'gainers';
                    if (typeof this.switchGainersSubTab === 'function') {
                        this.switchGainersSubTab(activeSub);
                    }
                }
                if (name === 'institutional') {
                    const activeSub = (app._subtabState && app._subtabState['institutional']) || localStorage.getItem('subtab_institutional') || localStorage.getItem('ee_institutional_subpage') || 'equities';
                    if (typeof this.switchInstitutionalPage === 'function') {
                        this.switchInstitutionalPage(activeSub);
                    }
                }
                if (name === 'kronos') {
                    const activeSub = (app._subtabState && app._subtabState['kronos']) || localStorage.getItem('subtab_kronos') || 'latest';
                    if (typeof this.switchKronosTab === 'function') {
                        this.switchKronosTab(activeSub);
                    }
                }
                if (name === 'tri-confluence') {
                    if (!this._triConfluenceLoaded) {
                        if (typeof app.loadTriConfluence === 'function') {
                            this._triConfluenceLoaded = true;
                            app.loadTriConfluence();
                        }
                    }
                }
                if (name === 'repeaters') {
                    if (!this._repeatersLoaded) {
                        this._repeatersLoaded = true;
                        this.loadQuarterRepeaters();
                    }
                }
                if (name === 'new-additions') {
                    if (!this._newAdditionsLoaded) {
                        this._newAdditionsLoaded = true;
                        if (typeof this.loadRecentAdditions === 'function') {
                            this.loadRecentAdditions();
                        }
                    }
                }
                if (name === 'buydip') {
                    if (typeof this._restoreBdControls === 'function') {
                        this._restoreBdControls();
                    }
                }
                if (name === 'patterns') {
                    if (typeof this._restorePatternsControls === 'function') {
                        this._restorePatternsControls();
                    }
                }
                if (name === 'swing') {
                    if (!this.swingData || !this.swingData.length) {
                        this.loadSwing();
                    }
                }
                this.applyRoleRestrictions();
            },

        // [scanner] -> extracted to modules/scanner.js
        // [catalysts] -> extracted to modules/catalysts.js


        // [gainers] -> extracted to modules/gainers.js
            // ---------- Universe Client-Side & Session Cache ----------
            _universeCache: {},

            async getUniverse(market, forceRefresh = false) {
                market = (market || 'NSE_ALL').toUpperCase().trim();
                
                // 1. In-memory fast cache
                if (!forceRefresh && this._universeCache[market] && this._universeCache[market].tickers) {
                    return this._universeCache[market];
                }

                // 2. Browser sessionStorage cache (valid for 1 hour)
                const cacheKey = 'ee_uni_' + market;
                if (!forceRefresh) {
                    try {
                        const stored = sessionStorage.getItem(cacheKey);
                        if (stored) {
                            const parsed = JSON.parse(stored);
                            if (parsed && Array.isArray(parsed.tickers) && parsed.ts && (Date.now() - parsed.ts < 3600000)) {
                                this._universeCache[market] = parsed;
                                return parsed;
                            }
                        }
                    } catch (e) {}
                }

                // 3. Network fetch ONLY when not cached
                try {
                    const res = await fetch(API_BASE + '/api/v1/universe/' + encodeURIComponent(market));
                    const data = await res.json();
                    const payload = {
                        market: market,
                        count: data.count != null ? data.count : (data.tickers && data.tickers.length) || 0,
                        tickers: data.tickers || [],
                        ts: Date.now()
                    };
                    this._universeCache[market] = payload;
                    try { sessionStorage.setItem(cacheKey, JSON.stringify(payload)); } catch (e) {}
                    return payload;
                } catch (e) {
                    console.error('Failed to fetch universe ' + market + ':', e);
                    return { market: market, count: 0, tickers: [] };
                }
            },

            invalidateUniverseCache(market) {
                if (market) {
                    const m = market.toUpperCase().trim();
                    delete this._universeCache[m];
                    try { sessionStorage.removeItem('ee_uni_' + m); } catch (e) {}
                } else {
                    this._universeCache = {};
                    try {
                        Object.keys(sessionStorage).forEach(k => {
                            if (k.startsWith('ee_uni_')) sessionStorage.removeItem(k);
                        });
                    } catch (e) {}
                }
                this._countsLoaded = false;
            },

            async loadSearchTickers() {
                try {
                    const [nse, us] = await Promise.all([
                        this.getUniverse('NSE_ALL'),
                        this.getUniverse('US')
                    ]);
                    this.allTickers = [...new Set([...(nse.tickers || []), ...(us.tickers || [])])];
                } catch (e) {
                    console.error('Failed to load tickers:', e);
                    this.allTickers = ['AAPL', 'MSFT', 'GOOGL', 'RELIANCE.NS', 'TCS.NS'];
                }
            },

            // Built-in universe options shared by all watchlist/market dropdowns.
            // "All watchlists" = the predefined universes (NSE_ALL, NSE Top, US Top,
            // NSE Large Cap, My Watchlist) AND user-created watchlists, each with counts.
            _BUILTINS: [
                { value: 'ALL', label: 'All Markets' },
                { value: 'WATCHLIST', label: 'My Watchlist' },
                { value: 'IN', label: 'NSE Top' },
                { value: 'US', label: 'US Top' },
                { value: 'NSE_LARGE_CAP', label: 'NSE Large Cap' },
                { value: 'NSE_ALL', label: 'NSE All' },
            ],
            _universeCounts: {},
            _countsLoaded: false,

            _builtinLabel(value) {
                const b = this._BUILTINS.find(x => x.value === value);
                if (!b) return value;
                const c = this._universeCounts[value];
                return c != null ? (b.label + ' (' + c + ')') : b.label;
            },

            getResultsPresetDetails(preset) {
                if (preset === 'recent') {
                    return { pastDays: 4, days: 7, label: 'Recent (-4D to +7D)' };
                } else if (preset === 'pm60') {
                    return { pastDays: 60, days: 60, label: '±2 Months' };
                } else if (preset === 'pm30') {
                    return { pastDays: 30, days: 30, label: '±1 Month' };
                } else if (preset === 'next14') {
                    return { pastDays: 0, days: 14, label: 'Upcoming 14 Days' };
                } else if (preset === 'next30') {
                    return { pastDays: 0, days: 30, label: 'Upcoming 30 Days' };
                } else if (preset === 'next60') {
                    return { pastDays: 0, days: 60, label: 'Upcoming 60 Days' };
                } else if (preset === 'past60') {
                    return { pastDays: 60, days: 0, label: 'Past 60 Days' };
                } else {
                    const past = parseInt(document.getElementById('resultsPastDays')?.value || '60', 10);
                    const ahead = parseInt(document.getElementById('resultsDays')?.value || '60', 10);
                    return { pastDays: past, days: ahead, label: `Custom (-${past}D to +${ahead}D)` };
                }
            },

            onResultsPresetChange(preset) {
                const customSpan = document.getElementById('resultsCustomInputs');
                const pastInput = document.getElementById('resultsPastDays');
                const nextInput = document.getElementById('resultsDays');
                const centerTitle = document.getElementById('resultsCenterTitle');
                const centerBtn = document.getElementById('resultsCenterLoadBtn');

                const details = this.getResultsPresetDetails(preset);
                if (pastInput) pastInput.value = details.pastDays;
                if (nextInput) nextInput.value = details.days;

                if (customSpan) {
                    customSpan.style.display = (preset === 'custom') ? 'inline-flex' : 'none';
                }
                if (centerTitle) {
                    centerTitle.textContent = `Ready to Load Results (${details.label})`;
                }
                if (centerBtn) {
                    centerBtn.innerHTML = `▶ Load Results Report (${details.label})`;
                }
            },

            async loadResultsReport() {
                const preset = document.getElementById('resultsRangePreset')?.value || 'recent';
                const details = this.getResultsPresetDetails(preset);
                const pastDays = details.pastDays;
                const days = details.days;
                const windowName = details.label;
                this.resultsActiveWindowName = windowName;

                const market = document.getElementById('resultsMarket')?.value || '';
                const query = '?days=' + days + '&past_days=' + pastDays + (market ? '&market=' + encodeURIComponent(market) : '');
                
                const loadBtns = [document.getElementById('resultsLoadBtn'), document.getElementById('resultsCenterLoadBtn')].filter(Boolean);
                loadBtns.forEach(b => { b.disabled = true; b.innerHTML = '<span class="loading-spinner"></span> Loading...'; });
                const cancelBtn = document.getElementById('resultsCancelBtn');
                if (cancelBtn) cancelBtn.style.display = 'inline-block';
                
                const statusEl = document.getElementById('resultsReportStatus');
                const countBadge = document.getElementById('resultsCount');
                if (statusEl) statusEl.textContent = 'Fetching corporate results across ' + windowName + ' window...';
                
                try {
                    const res = await this.fetchWithAbort('results', API_BASE + '/api/v1/dashboard/results/report' + query);
                    const data = await res.json();
                    if (!data.success) {
                        if (statusEl) statusEl.textContent = data.error || 'No report data';
                        document.getElementById('resultsReportSections').innerHTML = '<div class="card" style="margin:1rem 0;color:var(--muted);text-align:center;padding:1.5rem;">' + (data.error || 'No results data found for this selection.') + '<br><br><button type="button" onclick="app.loadResultsReport()" class="btn btn-sm btn-primary">↻ Try Again</button></div>';
                        return;
                    }
                    document.getElementById('resultsReportLegend').innerHTML = data.day_legend || '';
                    this.resultsDaySections = (data.day_sections_list && data.day_sections_list.length)
                        ? data.day_sections_list
                        : (data.day_sections ? [data.day_sections] : []);

                    this.resultsDaySectionsMeta = (data.day_sections_meta && data.day_sections_meta.length) ? data.day_sections_meta : [];
                    this.resultsMonths = (data.months && data.months.length) ? data.months : [];
                    this.resultsTotalStocks = data.total_stocks || 0;
                    this.resultsActiveMonth = 'ALL';
                    if (this.selectedResultsDates) this.selectedResultsDates.clear();

                    // Fallback: If months array was not provided by API, construct from day_sections
                    if (!this.resultsMonths.length && this.resultsDaySections.length) {
                        const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                        const monthsMap = {};
                        const meta = [];
                        const curMonthKey = new Date().toISOString().slice(0, 7);

                        this.resultsDaySections.forEach(secHtml => {
                            const match = secHtml.match(/<span class=["']day-dot["'][^>]*><\/span>\s*(\d{4}-\d{2}-\d{2})/i) || secHtml.match(/(\d{4}-\d{2}-\d{2})/);
                            const dateStr = match ? match[1] : '';
                            let mKey = 'other';
                            let mLabel = 'Other';
                            
                            const countMatch = secHtml.match(/class=["']day-count["']>\s*(\d+)/i);
                            let count = countMatch ? parseInt(countMatch[1], 10) : ((secHtml.match(/<tr/g) || []).length || 1);

                            if (dateStr) {
                                mKey = dateStr.slice(0, 7);
                                const parts = dateStr.split('-');
                                const y = parts[0];
                                const mIdx = parseInt(parts[1], 10) - 1;
                                mLabel = (monthNames[mIdx] || parts[1]) + ' ' + y;
                            }

                            meta.push({
                                date: dateStr,
                                month_key: mKey,
                                month_label: mLabel,
                                stocks_count: count,
                                html: secHtml
                            });

                            if (!monthsMap[mKey]) {
                                monthsMap[mKey] = {
                                    month_key: mKey,
                                    month_label: mLabel,
                                    stocks_count: 0,
                                    dates_count: 0,
                                    is_current: (mKey === curMonthKey),
                                    is_past: (mKey < curMonthKey)
                                };
                            }
                            monthsMap[mKey].stocks_count += count;
                            monthsMap[mKey].dates_count += 1;
                        });

                        this.resultsDaySectionsMeta = meta;
                        this.resultsMonths = Object.keys(monthsMap).sort().map(k => monthsMap[k]);
                        this.resultsTotalStocks = this.resultsMonths.reduce((acc, m) => acc + m.stocks_count, 0);
                    }
                    
                    // Render Month breakdown tabs and top 3 month cards
                    this.renderResultsMonthTabs();
                    this.updateResultsMonthSummaryCards();

                    // Render all dates in loaded window by default
                    this.resultsShowDays = (this.resultsDaySections || []).length || 1;
                    this.renderResultsDays();
                    
                    const totalDates = (this.resultsDaySections || []).length;
                    if (countBadge) {
                        countBadge.style.display = 'inline-block';
                        countBadge.textContent = this.resultsTotalStocks + ' results (' + totalDates + ' dates)';
                    }
                    if (statusEl) statusEl.textContent = 'Report loaded: ' + this.resultsTotalStocks + ' corporate results across ' + totalDates + ' dates in ' + windowName + ' window (' + new Date().toLocaleTimeString() + ')';
                    
                    if (data.popups) {
                        const existing = document.getElementById('resultsReportPopups');
                        if (existing) existing.remove();
                        const wrap = document.createElement('div');
                        wrap.id = 'resultsReportPopups';
                        wrap.innerHTML = data.popups;
                        document.body.appendChild(wrap);
                    }
                } catch (e) {
                    if (e.name === 'AbortError') {
                        console.log('Results report fetch aborted:', e.message);
                        if (statusEl) statusEl.textContent = '⚠️ Request cancelled (' + (e.message || 'aborted') + ').';
                        return;
                    }
                    console.error('Error loading results report:', e);
                    if (statusEl) statusEl.textContent = 'Error loading report: ' + (e.message || e);
                } finally {
                    this.resetTaskLoadingUI('results');
                }
            },

            async summarizeResults(event) {
                const btn = (event && event.target) || document.querySelector('button[onclick*="summarizeResults"]');
                const origHtml = btn ? btn.innerHTML : '✨ LLM Summary';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Summarizing...';
                }
                try {
                    const days = document.getElementById('resultsDays')?.value || 14;
                    const market = document.getElementById('resultsMarket')?.value || 'ALL';
                    const res = await fetch(API_BASE + '/api/v1/dashboard/results/summarize?days=' + encodeURIComponent(days) + '&market=' + encodeURIComponent(market));
                    const data = await res.json();
                    if (data && (data.summary || data.text)) {
                        alert('✨ Corporate Results AI Synthesis:\n\n' + (data.summary || data.text));
                    } else if (data && data.total_events !== undefined) {
                        const s = `📊 Results Dataset Summary (${market}):\n• Total Events in Window: ${data.total_events || 0}\n• Beat Rate: ${(data.overall_beat_rate ? (data.overall_beat_rate * 100).toFixed(1) + '%' : '—')}\n• Upward Reactions: ${(data.overall_up_rate ? (data.overall_up_rate * 100).toFixed(1) + '%' : '—')}\n• Top Volume Surge: ${(data.top_picks && data.top_picks[0] ? data.top_picks[0].ticker : '—')}`;
                        alert(s);
                    } else {
                        alert('Failed to generate summary: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error summarizing results:', e);
                    alert('Error generating results summary: ' + (e.message || e));
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async refreshResults() {
                try {
                    await this.loadResultsReport();
                } catch (e) {
                    console.error('Error refreshing results feed:', e);
                }
            },

            renderResultsMonthTabs() {
                let el = document.getElementById('resultsMonthTabs');
                if (!el) {
                    const sectionsEl = document.getElementById('resultsReportLegend') || document.getElementById('resultsReportSections');
                    if (sectionsEl && sectionsEl.parentNode) {
                        el = document.createElement('div');
                        el.id = 'resultsMonthTabs';
                        el.style.cssText = 'display:flex;gap:0.5rem;margin:0.75rem 0 1rem 0;flex-wrap:wrap;align-items:center;padding:0.5rem 0.75rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.6rem;';
                        sectionsEl.parentNode.insertBefore(el, sectionsEl);
                    }
                }
                if (!el) return;

                if (!this.resultsMonths || !this.resultsMonths.length) {
                    el.style.display = 'none';
                    return;
                }

                const totalStocks = this.resultsTotalStocks || this.resultsDaySectionsMeta.reduce((acc, m) => acc + (m.stocks_count || 1), 0);
                const totalDates = this.resultsDaySectionsMeta.length;

                let html = '<span style="font-size:0.75rem;font-weight:700;color:var(--muted);text-transform:uppercase;margin-right:0.25rem;">🗓️ Month Filter:</span>';
                
                // 1. "All Months" tab
                const allActive = (this.resultsActiveMonth === 'ALL');
                const allBtnStyle = allActive
                    ? 'background:var(--accent);color:#fff;font-weight:700;border:1px solid var(--accent);'
                    : 'background:rgba(255,255,255,0.06);color:var(--light);border:1px solid rgba(255,255,255,0.15);';
                const allLabel = this.resultsActiveWindowName ? `🌐 All (${this.resultsActiveWindowName})` : '🌐 All Dates';
                html += '<button type="button" onclick="app.filterResultsByMonth(\'ALL\')" class="btn btn-sm" style="' + allBtnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                    allLabel + ' <span style="background:rgba(0,0,0,0.25);padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;margin-left:0.2rem;">' + totalStocks + '</span>' +
                    '</button>';

                // 2. Individual month tabs (tabs for months in range)
                this.resultsMonths.forEach((m, idx) => {
                    const isActive = (this.resultsActiveMonth === m.month_key);
                    const tag = m.is_current ? '⭐ ' : (m.is_past ? '◀ ' : '▶ ');
                    const badgeBg = isActive ? 'rgba(0,0,0,0.3)' : (m.is_current ? 'rgba(16,185,129,0.25)' : 'rgba(255,255,255,0.12)');
                    const badgeColor = isActive ? '#fff' : (m.is_current ? '#34d399' : 'var(--light)');
                    
                    let btnStyle = '';
                    if (isActive) {
                        btnStyle = 'background:#2563eb;color:#fff;font-weight:700;border:1px solid #3b82f6;box-shadow:0 2px 8px rgba(37,99,235,0.4);';
                    } else if (m.is_current) {
                        btnStyle = 'background:rgba(16,185,129,0.15);color:#6ee7b7;border:1px solid rgba(16,185,129,0.35);';
                    } else if (m.is_past) {
                        btnStyle = 'background:rgba(148,163,184,0.1);color:#cbd5e1;border:1px solid rgba(255,255,255,0.1);';
                    } else {
                        btnStyle = 'background:rgba(59,130,246,0.12);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);';
                    }

                    html += '<button type="button" onclick="app.filterResultsByMonth(\'' + m.month_key + '\')" class="btn btn-sm" style="' + btnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                        tag + m.month_label + ' ' +
                        '<span style="background:' + badgeBg + ';color:' + badgeColor + ';padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;font-weight:700;margin-left:0.2rem;">' + (m.stocks_count || 0) + '</span>' +
                        '</button>';
                });

                el.innerHTML = html;
                el.style.display = 'flex';
            },

            selectedResultsDates: new Set(),

            toggleDateFilter(dateStr, event) {
                if (event) {
                    event.preventDefault();
                    event.stopPropagation();
                }

                if (!this.selectedResultsDates) {
                    this.selectedResultsDates = new Set();
                }

                if (dateStr === 'ALL') {
                    this.selectedResultsDates.clear();
                } else {
                    const isMulti = event && (event.ctrlKey || event.metaKey || event.shiftKey);
                    if (isMulti) {
                        // Multi-select toggle
                        if (this.selectedResultsDates.has(dateStr)) {
                            this.selectedResultsDates.delete(dateStr);
                        } else {
                            this.selectedResultsDates.add(dateStr);
                        }
                    } else {
                        // Single-select: if clicking the only selected date, toggle off back to ALL
                        if (this.selectedResultsDates.size === 1 && this.selectedResultsDates.has(dateStr)) {
                            this.selectedResultsDates.clear();
                        } else {
                            this.selectedResultsDates.clear();
                            this.selectedResultsDates.add(dateStr);
                        }
                    }
                }

                this.applyDateFilterUI();
            },

            applyDateFilterUI() {
                if (!this.selectedResultsDates) this.selectedResultsDates = new Set();
                const isAll = this.selectedResultsDates.size === 0;

                // Update chip active states in legend bar
                const legendEl = document.getElementById('resultsReportLegend') || document.getElementById('resultsDateLegendBar');
                if (legendEl) {
                    const allChip = legendEl.querySelector('.day-chip-all');
                    if (allChip) allChip.classList.toggle('active', isAll);

                    legendEl.querySelectorAll('.day-chip:not(.day-chip-all)').forEach(chip => {
                        const d = chip.getAttribute('data-date');
                        const isActive = !isAll && this.selectedResultsDates.has(d);
                        chip.classList.toggle('active', isActive);
                    });
                }

                // Filter sections in #resultsReportSections
                let filtered = [];
                let visibleCount = 0;
                let visibleDatesCount = 0;

                if (this.resultsDaySectionsMeta && this.resultsDaySectionsMeta.length) {
                    let baseMeta = this.resultsDaySectionsMeta;
                    if (this.resultsActiveMonth && this.resultsActiveMonth !== 'ALL') {
                        baseMeta = baseMeta.filter(m => m.month_key === this.resultsActiveMonth);
                    }

                    if (isAll) {
                        filtered = baseMeta.map(m => m.html);
                        visibleCount = baseMeta.reduce((acc, m) => acc + (m.stocks_count || 1), 0);
                        visibleDatesCount = baseMeta.length;
                    } else {
                        const matched = baseMeta.filter(m => this.selectedResultsDates.has(m.date));
                        filtered = matched.map(m => m.html);
                        visibleCount = matched.reduce((acc, m) => acc + (m.stocks_count || 1), 0);
                        visibleDatesCount = matched.length;
                    }
                }

                this.resultsDaySections = filtered;
                this.resultsShowDays = isAll ? Math.min(10, filtered.length || 1) : filtered.length;
                this.renderResultsDays();

                // If specific dates are selected, automatically expand them
                if (!isAll) {
                    document.querySelectorAll('#resultsReportSections .day-section').forEach(sec => {
                        sec.open = true;
                    });
                }

                // Update header count badge
                const countBadge = document.getElementById('resultsCount');
                if (countBadge) {
                    if (isAll) {
                        const mObj = (this.resultsMonths || []).find(m => m.month_key === this.resultsActiveMonth);
                        const label = (this.resultsActiveMonth === 'ALL') ? (this.resultsActiveWindowName || 'Selected Window') : (mObj ? mObj.month_label : this.resultsActiveMonth);
                        countBadge.textContent = visibleCount + ' results (' + visibleDatesCount + ' dates in ' + label + ')';
                    } else {
                        const datesArr = Array.from(this.selectedResultsDates);
                        const label = datesArr.length === 1 ? datesArr[0] : (datesArr.length + ' selected dates');
                        countBadge.textContent = visibleCount + ' results on ' + label;
                    }
                }
            },

            filterResultsByMonth(monthKey) {
                this.resultsActiveMonth = monthKey;
                if (this.selectedResultsDates) this.selectedResultsDates.clear();
                this.renderResultsMonthTabs();
                this.applyDateFilterUI();
            },

            async updateResultsMonthSummaryCards() {
                const now = new Date();
                const lastMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
                const thisMonthDate = new Date(now.getFullYear(), now.getMonth(), 1);
                const nextMonthDate = new Date(now.getFullYear(), now.getMonth() + 1, 1);

                const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                const lastMonthName = monthNames[lastMonthDate.getMonth()] + ' ' + lastMonthDate.getFullYear();
                const thisMonthName = monthNames[thisMonthDate.getMonth()] + ' ' + thisMonthDate.getFullYear();
                const nextMonthName = monthNames[nextMonthDate.getMonth()] + ' ' + nextMonthDate.getFullYear();

                const lastLabelEl = document.getElementById('resultsCardLastMonthLabel');
                const lastCountEl = document.getElementById('resultsCardLastMonthCount');
                const lastSubEl = document.getElementById('resultsCardLastMonthSubtitle');
                if (lastLabelEl) lastLabelEl.textContent = lastMonthName;

                const thisLabelEl = document.getElementById('resultsCardThisMonthLabel');
                const thisCountEl = document.getElementById('resultsCardThisMonthCount');
                const thisSubEl = document.getElementById('resultsCardThisMonthSubtitle');
                if (thisLabelEl) thisLabelEl.textContent = thisMonthName;

                const nextLabelEl = document.getElementById('resultsCardNextMonthLabel');
                const nextCountEl = document.getElementById('resultsCardNextMonthCount');
                const nextSubEl = document.getElementById('resultsCardNextMonthSubtitle');
                if (nextLabelEl) nextLabelEl.textContent = nextMonthName;

                const market = document.getElementById('resultsMarket')?.value || '';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/results/month-summary' + (market ? `?market=${encodeURIComponent(market)}` : ''));
                    if (res.ok) {
                        const data = await res.json();
                        if (data.success) {
                            if (lastLabelEl && data.last_month?.label) lastLabelEl.textContent = data.last_month.label;
                            if (lastCountEl) lastCountEl.textContent = (data.last_month?.count || 0).toLocaleString() + ' Results';
                            if (lastSubEl && data.last_month?.subtitle) lastSubEl.textContent = data.last_month.subtitle;

                            if (thisLabelEl && data.this_month?.label) thisLabelEl.textContent = data.this_month.label;
                            if (thisCountEl) thisCountEl.textContent = (data.this_month?.count || 0).toLocaleString() + ' Results';
                            if (thisSubEl && data.this_month?.subtitle) thisSubEl.textContent = data.this_month.subtitle;

                            if (nextLabelEl && data.next_month?.label) nextLabelEl.textContent = data.next_month.label;
                            if (nextCountEl) nextCountEl.textContent = (data.next_month?.count || 0).toLocaleString() + ' Results';
                            if (nextSubEl && data.next_month?.subtitle) nextSubEl.textContent = data.next_month.subtitle;
                            return;
                        }
                    }
                } catch (err) {
                    console.warn('Could not fetch month summary API, falling back to loaded results data:', err);
                }

                // Fallback if offline or API error
                let lastCount = 0;
                let thisCount = 0;
                let nextCount = 0;
                const lastMonthKey = lastMonthDate.toISOString().slice(0, 7);
                const thisMonthKey = thisMonthDate.toISOString().slice(0, 7);
                const nextMonthKey = nextMonthDate.toISOString().slice(0, 7);

                if (this.resultsMonths && this.resultsMonths.length) {
                    this.resultsMonths.forEach(m => {
                        if (m.month_key === lastMonthKey) lastCount = m.stocks_count;
                        else if (m.month_key === thisMonthKey) thisCount = m.stocks_count;
                        else if (m.month_key === nextMonthKey) nextCount = m.stocks_count;
                    });
                } else if (this.resultsDaySectionsMeta && this.resultsDaySectionsMeta.length) {
                    this.resultsDaySectionsMeta.forEach(d => {
                        const count = d.stocks_count || 1;
                        if (d.month_key === lastMonthKey || (d.date && d.date.startsWith(lastMonthKey))) lastCount += count;
                        else if (d.month_key === thisMonthKey || (d.date && d.date.startsWith(thisMonthKey))) thisCount += count;
                        else if (d.month_key === nextMonthKey || (d.date && d.date.startsWith(nextMonthKey))) nextCount += count;
                    });
                }

                if (lastCountEl) lastCountEl.textContent = lastCount.toLocaleString() + ' Results';
                if (lastSubEl) lastSubEl.textContent = lastCount > 0 ? 'Reported prints in ' + monthNames[lastMonthDate.getMonth()] : 'No prints in loaded range';
                if (thisCountEl) thisCountEl.textContent = thisCount.toLocaleString() + ' Results';
                if (thisSubEl) thisSubEl.textContent = thisCount > 0 ? 'Active prints in ' + monthNames[thisMonthDate.getMonth()] : 'No prints in loaded range';
                if (nextCountEl) nextCountEl.textContent = nextCount.toLocaleString() + ' Results';
                if (nextSubEl) nextSubEl.textContent = nextCount > 0 ? 'Scheduled prints in ' + monthNames[nextMonthDate.getMonth()] : 'Pipeline in ' + monthNames[nextMonthDate.getMonth()];
            },

            // =========================================================================
            // 🗓️ Month Cards Click & Drilldown Modal Handlers
            // =========================================================================
            onMonthCardClick(relativeType) {
                const now = new Date();
                let targetDate = now;
                if (relativeType === 'last') {
                    targetDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
                } else if (relativeType === 'next') {
                    targetDate = new Date(now.getFullYear(), now.getMonth() + 1, 1);
                }
                const targetKey = targetDate.toISOString().slice(0, 7);

                // If months are loaded and match, filter the ledger to that month
                if (this.resultsMonths && this.resultsMonths.some(m => m.month_key === targetKey)) {
                    this.filterResultsByMonth(targetKey);
                    // Also scroll smoothly down to the table
                    const tbl = document.getElementById('resultsReportSections');
                    if (tbl) tbl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                } else {
                    // Open drilldown modal for detailed breakdown
                    this.openResultsMonthModal(relativeType);
                }
            },

            openResultsMonthModal(monthTarget) {
                const modal = document.getElementById('resultsMonthModal');
                if (!modal) return;

                const now = new Date();
                let targetDate = now;
                let monthLabel = 'This Month';
                if (monthTarget === 'last') {
                    targetDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
                    monthLabel = 'Last Month';
                } else if (monthTarget === 'next') {
                    targetDate = new Date(now.getFullYear(), now.getMonth() + 1, 1);
                    monthLabel = 'Next Month';
                } else if (typeof monthTarget === 'string' && monthTarget.length === 7) {
                    const parts = monthTarget.split('-');
                    targetDate = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
                }

                const monthKey = targetDate.toISOString().slice(0, 7);
                const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
                const fullMonthName = monthNames[targetDate.getMonth()] + ' ' + targetDate.getFullYear();
                this._activeMonthModalKey = monthKey;

                // Set header info
                const titleEl = document.getElementById('resultsMonthModalTitle');
                const subEl = document.getElementById('resultsMonthModalSubtitle');
                if (titleEl) titleEl.textContent = `🗓️ ${fullMonthName} Earnings Catalysts`;
                if (subEl) subEl.textContent = `Detailed scheduled reports, company roster, and market-cap breakdown for ${monthKey}`;

                // Gather events for this month from resultsDaySectionsMeta
                let monthItems = (this.resultsDaySectionsMeta || []).filter(m => m.month_key === monthKey || (m.date && m.date.startsWith(monthKey)));

                // If not in current window, check if Month Filter data has it
                if (!monthItems.length && this.mfDaySectionsMeta && this.mfDaySectionsMeta.length) {
                    monthItems = this.mfDaySectionsMeta.filter(m => m.month_key === monthKey || (m.date && m.date.startsWith(monthKey)));
                }

                const totalStocks = monthItems.reduce((acc, m) => acc + (m.stocks_count || 1), 0);
                const totalDates = monthItems.length;

                // Update KPI Cards
                const sTotal = document.getElementById('resultsMonthModalTotalStocks');
                const sDates = document.getElementById('resultsMonthModalTotalDates');
                const sLarge = document.getElementById('resultsMonthModalLargeCap');
                const sStatus = document.getElementById('resultsMonthModalStatusBadge');
                if (sTotal) sTotal.textContent = totalStocks.toLocaleString();
                if (sDates) sDates.textContent = totalDates.toLocaleString();

                let largeCount = 0;
                monthItems.forEach(m => {
                    const matches = (m.html || '').match(/cap-badge-large/g);
                    if (matches) largeCount += matches.length;
                });
                if (sLarge) sLarge.textContent = largeCount > 0 ? largeCount.toLocaleString() : '—';

                const curMonthKey = now.toISOString().slice(0, 7);
                if (sStatus) {
                    if (monthKey === curMonthKey) {
                        sStatus.innerHTML = '<span style="color:#38bdf8;">🟢 Active Season</span>';
                    } else if (monthKey < curMonthKey) {
                        sStatus.innerHTML = '<span style="color:#94a3b8;">🕒 Past Results</span>';
                    } else {
                        sStatus.innerHTML = '<span style="color:#a7f3d0;">🔮 Future Pipeline</span>';
                    }
                }

                // Render Content inside Modal
                const contentEl = document.getElementById('resultsMonthModalContent');
                if (contentEl) {
                    if (monthItems.length) {
                        contentEl.innerHTML = monthItems.map(m => m.html).join('\n');
                        // Ensure all day sections are open inside modal
                        contentEl.querySelectorAll('.day-section').forEach(sec => sec.open = true);
                    } else {
                        contentEl.innerHTML = `
                            <div style="padding:2.5rem 1.5rem;text-align:center;color:var(--text-muted);background:rgba(255,255,255,0.02);border-radius:8px;">
                                <div style="font-size:1.6rem;margin-bottom:0.5rem;">📅</div>
                                <div style="font-weight:700;color:#ffffff;margin-bottom:0.35rem;">No Loaded Results for ${fullMonthName}</div>
                                <p style="font-size:0.75rem;max-width:420px;margin:0 auto 1rem auto;color:#94a3b8;">
                                    The currently loaded window does not encompass ${fullMonthName}. Choose "±2 Months" or "Custom Range" from the dropdown to ingest this period.
                                </p>
                                <button type="button" onclick="app.loadResultsPresetAndFilter('${monthKey}')" class="btn btn-primary btn-sm">⚡ Load ±2 Months Range</button>
                            </div>
                        `;
                    }
                }

                modal.style.display = 'flex';
                document.body.style.overflow = 'hidden';

                // Setup Esc key handler once
                if (!this._monthModalEscBound) {
                    this._monthModalEscBound = true;
                    window.addEventListener('keydown', (e) => {
                        if (e.key === 'Escape') {
                            app.closeResultsMonthModal();
                        }
                    });
                }
            },

            closeResultsMonthModal() {
                const modal = document.getElementById('resultsMonthModal');
                if (modal) modal.style.display = 'none';
                document.body.style.overflow = '';
            },

            filterTableFromMonthModal() {
                if (this._activeMonthModalKey) {
                    this.filterResultsByMonth(this._activeMonthModalKey);
                    this.closeResultsMonthModal();
                    const tbl = document.getElementById('resultsReportSections');
                    if (tbl) tbl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            },

            loadResultsPresetAndFilter(targetMonthKey) {
                this.closeResultsMonthModal();
                const presetEl = document.getElementById('resultsRangePreset');
                if (presetEl) {
                    presetEl.value = 'pm60';
                    this.onResultsPresetChange('pm60');
                }
                this.loadResultsReport().then(() => {
                    if (targetMonthKey) {
                        setTimeout(() => this.filterResultsByMonth(targetMonthKey), 400);
                    }
                });
            },

            filterMonthModalItems(query) {
                const q = (query || '').toLowerCase().trim();
                const container = document.getElementById('resultsMonthModalContent');
                if (!container) return;

                const rows = container.querySelectorAll('table.results-table tbody tr:not(.row-drawer-tr)');
                rows.forEach(row => {
                    if (!q) {
                        row.style.display = '';
                        return;
                    }
                    const isMatch = row.textContent.toLowerCase().includes(q);
                    row.style.display = isMatch ? '' : 'none';
                });

                // Auto hide/show day sections and cap categories based on visible rows
                container.querySelectorAll('.day-section').forEach(sec => {
                    const visibleRows = sec.querySelectorAll('table.results-table tbody tr:not([style*="display: none"])');
                    sec.style.display = (!q || visibleRows.length > 0) ? '' : 'none';
                    if (q && visibleRows.length > 0) sec.open = true;
                });
            },

            renderResultsDays() {
                const el = document.getElementById('resultsReportSections');
                const shown = (this.resultsDaySections || []).slice(0, this.resultsShowDays);
                el.innerHTML = shown.length ? shown.join('\n') : '<p class="timestamp">No upcoming or past earnings data in this window.</p>';
                const btn = document.getElementById('resultsMoreDaysBtn');
                if (btn) {
                    const total = (this.resultsDaySections || []).length;
                    if (this.resultsShowDays < total) {
                        btn.style.display = 'inline-block';
                        btn.disabled = false;
                        btn.textContent = '📅 Show ' + Math.min(this.resultsShowDays + 5, total) + ' of ' + total + ' dates';
                    } else if (total > 0) {
                        btn.style.display = 'inline-block';
                        btn.disabled = true;
                        btn.textContent = '📅 All ' + total + ' dates displayed';
                    } else {
                        btn.style.display = 'none';
                    }
                }
                this.updateResultsSummaryCards();
            },

            showMoreResultsDays() {
                if (this.resultsShowDays < (this.resultsDaySections || []).length) {
                    this.resultsShowDays = Math.min(this.resultsShowDays + 5, (this.resultsDaySections || []).length);
                    this.renderResultsDays();
                }
            },

            updateResultsSummaryCards() {
                const metricsBar = document.getElementById('resultsWindowMetricsBar');
                if (!metricsBar) return;

                const tableRows = document.querySelectorAll('#resultsReportSections table.results-table tbody tr:not(.row-drawer-tr)');
                if (!tableRows.length) {
                    metricsBar.style.display = 'none';
                    metricsBar.innerHTML = '';
                    return;
                }

                let totalStocks = 0;
                let sum30D = 0;
                let count30D = 0;
                let positiveMovesCount = 0;
                let totalBeatEvalCount = 0;
                let bullConsensusCount = 0;
                let bearConsensusCount = 0;
                let imminentCount = 0;

                const today = new Date();
                const next48h = new Date(today.getTime() + 48 * 3600 * 1000);
                const todayStr = today.toISOString().slice(0, 10);
                const next48hStr = next48h.toISOString().slice(0, 10);

                tableRows.forEach(row => {
                    totalStocks++;
                    const dateCell = row.querySelector('.cell-earnings-date');
                    if (dateCell) {
                        const dateText = dateCell.textContent.trim().slice(0, 10);
                        if (dateText >= todayStr && dateText <= next48hStr) {
                            imminentCount++;
                        }
                    }

                    const retCell = row.querySelector('.cell-thirty-day-return');
                    if (retCell) {
                        const retText = retCell.textContent.replace('%', '').replace('+', '').trim();
                        const val = parseFloat(retText);
                        if (!isNaN(val)) {
                            sum30D += val;
                            count30D++;
                        }
                    }

                    const qScoreCell = row.querySelector('.cell-prev-3q-score');
                    if (qScoreCell) {
                        const sText = qScoreCell.textContent.replace('/9', '').trim();
                        const sVal = parseFloat(sText);
                        if (!isNaN(sVal)) {
                            totalBeatEvalCount++;
                            if (sVal >= 5) positiveMovesCount++;
                        }
                    }

                    const aiCell = row.querySelector('.cell-ai-consensus');
                    if (aiCell) {
                        const text = aiCell.textContent.toUpperCase();
                        if (text.includes('BULL')) bullConsensusCount++;
                        else if (text.includes('BEAR')) bearConsensusCount++;
                    }
                });

                const avg30D = count30D ? (sum30D / count30D).toFixed(1) : '0.0';
                const avg30DCls = parseFloat(avg30D) >= 0 ? 'color:#34d399;' : 'color:#f87171;';
                const beatPct = totalBeatEvalCount ? Math.round((positiveMovesCount / totalBeatEvalCount) * 100) : 0;
                const winWindow = this.resultsActiveWindowName || 'Selected Window';

                metricsBar.innerHTML = `
                    <div class="metric" style="padding:0.25rem 0.45rem;">
                        <span style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;">Tracked Window</span>
                        <strong style="color:#ffffff;font-size:0.95rem;">${totalStocks} <span style="font-size:0.68rem;color:#60a5fa;font-weight:600;">(${winWindow})</span></strong>
                    </div>
                    <div class="metric" style="padding:0.25rem 0.45rem;">
                        <span style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;">Avg 30D Momentum</span>
                        <strong style="${avg30DCls}font-size:0.95rem;">${parseFloat(avg30D) > 0 ? '+' : ''}${avg30D}%</strong>
                    </div>
                    <div class="metric" style="padding:0.25rem 0.45rem;">
                        <span style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;">Quality Beat Rate</span>
                        <strong style="color:#38bdf8;font-size:0.95rem;">${beatPct}% <span style="font-size:0.68rem;color:#71717a;font-weight:400;">(${positiveMovesCount}/${totalBeatEvalCount})</span></strong>
                    </div>
                    <div class="metric" style="padding:0.25rem 0.45rem;">
                        <span style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;">AI Consensus</span>
                        <strong style="color:#60a5fa;font-size:0.95rem;"><span style="color:#34d399;">${bullConsensusCount} 🐂</span> / <span style="color:#f87171;">${bearConsensusCount} 🐻</span></strong>
                    </div>
                    <div class="metric" style="padding:0.25rem 0.45rem;">
                        <span style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;">Imminent (48h)</span>
                        <strong style="color:#fbbf24;font-size:0.95rem;">${imminentCount} <span style="font-size:0.68rem;color:#a1a1aa;font-weight:400;">catalysts</span></strong>
                    </div>
                `;
                metricsBar.style.display = 'grid';
            },

            filterResultsTable(query) {
                const q = (query || '').toLowerCase().trim();
                const rows = document.querySelectorAll('#resultsReportSections table.results-table tbody tr:not(.row-drawer-tr)');
                const matchEl = document.getElementById('resultsFilterMatchCount');
                let matchCount = 0;
                let totalCount = rows.length;

                rows.forEach(row => {
                    const rowId = row.id;
                    const drawerId = rowId ? rowId.replace('row_', 'drawer_') : null;
                    const drawerRow = drawerId ? document.getElementById(drawerId) : null;

                    if (!q) {
                        row.style.display = '';
                        matchCount++;
                        return;
                    }

                    const text = row.textContent.toLowerCase();
                    const isMatch = text.includes(q);
                    row.style.display = isMatch ? '' : 'none';
                    if (!isMatch && drawerRow) {
                        drawerRow.style.display = 'none';
                    }
                    if (isMatch) matchCount++;
                });

                // Also toggle empty cap/industry sections and auto-expand matching day sections
                document.querySelectorAll('#resultsReportSections .industry-subgroup, #resultsReportSections .cap-section').forEach(sec => {
                    const visibleTrs = sec.querySelectorAll('tbody tr:not(.row-drawer-tr):not([style*="display: none"])');
                    sec.style.display = (!q || visibleTrs.length) ? '' : 'none';
                });

                document.querySelectorAll('#resultsReportSections details.day-section').forEach(daySec => {
                    if (!q) {
                        daySec.style.display = '';
                    } else {
                        const visibleTrs = daySec.querySelectorAll('tbody tr:not(.row-drawer-tr):not([style*="display: none"])');
                        if (visibleTrs.length > 0) {
                            daySec.style.display = '';
                            daySec.open = true; // Auto-expand when search query matches tickers inside this day
                        } else {
                            daySec.style.display = 'none';
                        }
                    }
                });

                if (matchEl) {
                    matchEl.textContent = q ? `Showing ${matchCount}/${totalCount}` : '';
                }
            },

            sortResultsTable(th, colIndex, type) {
                const table = th.closest('table');
                if (!table) return;
                const tbody = table.querySelector('tbody');
                if (!tbody) return;

                const isAsc = th.classList.contains('sort-asc');
                const isDesc = th.classList.contains('sort-desc');
                const newDirection = isAsc ? 'desc' : 'asc';

                // Reset all th headers in this table
                table.querySelectorAll('th').forEach(h => {
                    h.classList.remove('sort-asc', 'sort-desc');
                });
                th.classList.add(newDirection === 'asc' ? 'sort-asc' : 'sort-desc');

                // Get row pairs (main row + drawer row)
                const rows = Array.from(tbody.querySelectorAll('tr:not(.row-drawer-tr)'));
                const rowPairs = rows.map(row => {
                    const drawerId = row.id ? row.id.replace('row_', 'drawer_') : null;
                    const drawerRow = drawerId ? document.getElementById(drawerId) : null;
                    return { row, drawerRow };
                });

                rowPairs.sort((a, b) => {
                    const cellA = a.row.children[colIndex];
                    const cellB = b.row.children[colIndex];
                    if (!cellA || !cellB) return 0;

                    let valA = cellA.textContent.trim();
                    let valB = cellB.textContent.trim();

                    if (type === 'num') {
                        const numA = parseFloat(valA.replace(/[^0-9.-]/g, '')) || 0;
                        const numB = parseFloat(valB.replace(/[^0-9.-]/g, '')) || 0;
                        return newDirection === 'asc' ? numA - numB : numB - numA;
                    } else if (type === 'date') {
                        const dateA = valA.slice(0, 10);
                        const dateB = valB.slice(0, 10);
                        return newDirection === 'asc' ? dateA.localeCompare(dateB) : dateB.localeCompare(dateA);
                    } else {
                        return newDirection === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
                    }
                });

                rowPairs.forEach(pair => {
                    tbody.appendChild(pair.row);
                    if (pair.drawerRow) tbody.appendChild(pair.drawerRow);
                });
            },

            toggleRowDrawer(rowTickerId, ticker, activeTab = 'intel') {
                const drawerTr = document.getElementById('drawer_' + rowTickerId);
                const arrow = document.getElementById('arrow_' + rowTickerId);
                const mainRow = document.getElementById('row_' + rowTickerId);
                if (!drawerTr) return;

                const isHidden = drawerTr.style.display === 'none' || !drawerTr.style.display;
                if (isHidden) {
                    drawerTr.style.display = 'table-row';
                    if (arrow) arrow.style.transform = 'rotate(90deg)';
                    if (mainRow) mainRow.classList.add('row-expanded');

                    const bodyTd = document.getElementById('drawer_body_' + rowTickerId);
                    if (bodyTd) {
                        // Extract content from corresponding popup modal if present
                        const popupEl = document.getElementById('popup_' + rowTickerId);
                        let sectionsHtml = '';
                        if (popupEl) {
                            sectionsHtml = popupEl.querySelector('.popup-sections')?.innerHTML || popupEl.querySelector('.popup-body')?.innerHTML || '';
                        }

                        if (!sectionsHtml) {
                            sectionsHtml = `
                                <div class="drawer-card">
                                    <h5>📊 Stock Intelligence for ${ticker}</h5>
                                    <div style="font-size:0.75rem;color:#a1a1aa;line-height:1.5;">
                                        Comprehensive earnings history, implied volatility breakdown, and 4-model AI consensus predictions.
                                    </div>
                                </div>
                            `;
                        }

                        bodyTd.innerHTML = `
                            <div class="ledger-drawer-wrapper" style="padding:0.75rem 1rem;background:#05070e;border-top:1px solid rgba(255,255,255,0.06);">
                                <!-- Drawer Header Sub-tabs -->
                                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.5rem;flex-wrap:wrap;gap:0.5rem;">
                                    <div style="display:flex;align-items:center;gap:0.4rem;">
                                        <button type="button" id="tabbtn_news_${rowTickerId}" onclick="app.switchDrawerTab('${rowTickerId}', '${ticker}', 'news')" class="btn-micro" style="background:${activeTab === 'news' ? 'var(--accent)' : 'rgba(255,255,255,0.08)'};color:#ffffff;font-weight:700;padding:0.25rem 0.6rem;">📰 Live News & Catalysts</button>
                                        <button type="button" id="tabbtn_intel_${rowTickerId}" onclick="app.switchDrawerTab('${rowTickerId}', '${ticker}', 'intel')" class="btn-micro" style="background:${activeTab === 'intel' ? 'var(--accent)' : 'rgba(255,255,255,0.08)'};color:#ffffff;font-weight:700;padding:0.25rem 0.6rem;">📊 Intelligence & Consensus</button>
                                    </div>
                                    <div style="display:flex;gap:0.35rem;align-items:center;">
                                        <button type="button" class="btn-micro btn-micro-violet" onclick="app.openAiDetails('ALL', '${ticker}', event)">🤖 4-Model AI Breakdown</button>
                                        <button type="button" class="btn-micro btn-micro-primary" onclick="app.showOhlcvBenchmarkModal('${ticker}')">📈 TradingView Chart</button>
                                        <button type="button" class="btn-micro btn-micro-neutral" onclick="app.showTickerAuditModal('${ticker}')">📜 Formula Audit</button>
                                    </div>
                                </div>

                                <!-- Tab Content: News -->
                                <div id="drawer_tab_news_${rowTickerId}" style="display:${activeTab === 'news' ? 'block' : 'none'};">
                                    <div id="drawer_news_content_${rowTickerId}">
                                        <div style="padding:1.5rem;text-align:center;color:var(--text-muted);"><span class="loading-spinner"></span> Fetching real-time news & catalysts for ${ticker}...</div>
                                    </div>
                                </div>

                                <!-- Tab Content: Intel -->
                                <div id="drawer_tab_intel_${rowTickerId}" style="display:${activeTab === 'intel' ? 'block' : 'none'};">
                                    <div class="drawer-content">${sectionsHtml}</div>
                                </div>
                            </div>
                        `;

                        if (activeTab === 'news') {
                            this.fetchStockNewsForDrawer(rowTickerId, ticker);
                        }
                    }
                } else {
                    drawerTr.style.display = 'none';
                    if (arrow) arrow.style.transform = 'rotate(0deg)';
                    if (mainRow) mainRow.classList.remove('row-expanded');
                }
            },

            switchDrawerTab(rowTickerId, ticker, tab) {
                const newsTab = document.getElementById('drawer_tab_news_' + rowTickerId);
                const intelTab = document.getElementById('drawer_tab_intel_' + rowTickerId);
                const newsBtn = document.getElementById('tabbtn_news_' + rowTickerId);
                const intelBtn = document.getElementById('tabbtn_intel_' + rowTickerId);

                if (tab === 'news') {
                    if (newsTab) newsTab.style.display = 'block';
                    if (intelTab) intelTab.style.display = 'none';
                    if (newsBtn) { newsBtn.style.background = 'var(--accent)'; newsBtn.style.color = '#ffffff'; }
                    if (intelBtn) { intelBtn.style.background = 'rgba(255,255,255,0.08)'; }
                    this.fetchStockNewsForDrawer(rowTickerId, ticker);
                } else {
                    if (newsTab) newsTab.style.display = 'none';
                    if (intelTab) intelTab.style.display = 'block';
                    if (intelBtn) { intelBtn.style.background = 'var(--accent)'; intelBtn.style.color = '#ffffff'; }
                    if (newsBtn) { newsBtn.style.background = 'rgba(255,255,255,0.08)'; }
                }
            },

            showStockNewsDrawer(rowTickerId, ticker, event) {
                if (event) event.stopPropagation();
                const drawerTr = document.getElementById('drawer_' + rowTickerId);
                if (!drawerTr || drawerTr.style.display === 'none' || !drawerTr.style.display) {
                    this.toggleRowDrawer(rowTickerId, ticker, 'news');
                } else {
                    this.switchDrawerTab(rowTickerId, ticker, 'news');
                }
            },

            async fetchStockNewsForDrawer(rowTickerId, ticker) {
                const cont = document.getElementById('drawer_news_content_' + rowTickerId);
                if (!cont) return;
                if (cont.getAttribute('data-loaded') === 'true') return;

                try {
                    const res = await fetch(API_BASE + '/api/v1/stock/' + encodeURIComponent(ticker) + '/catalysts');
                    const data = await res.json();
                    const catalysts = (data && data.catalysts) ? data.catalysts : [];

                    if (!catalysts.length) {
                        cont.innerHTML = `
                            <div style="padding:1.2rem;background:rgba(255,255,255,0.02);border:1px dashed rgba(255,255,255,0.1);border-radius:0.5rem;text-align:center;color:var(--text-muted);font-size:0.8rem;">
                                📰 No breaking news catalysts recorded for ${ticker} in the last 7 days.
                                <div style="margin-top:0.4rem;">
                                    <a href="https://www.google.com/search?q=${encodeURIComponent(ticker + ' stock news')}" target="_blank" style="color:#38bdf8;text-decoration:none;font-size:0.75rem;">Search Google News ↗</a>
                                </div>
                            </div>
                        `;
                        cont.setAttribute('data-loaded', 'true');
                        return;
                    }

                    let html = '<div style="display:flex;flex-direction:column;gap:0.45rem;">';
                    catalysts.slice(0, 6).forEach(c => {
                        const impactColor = (c.impact_score >= 70) ? '#f87171' : (c.impact_score >= 40 ? '#38bdf8' : '#34d399');
                        const sentimentBg = (c.sentiment === 'positive') ? 'rgba(16,185,129,0.15)' : (c.sentiment === 'negative' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.08)');
                        const sentimentColor = (c.sentiment === 'positive') ? '#34d399' : (c.sentiment === 'negative' ? '#fca5a5' : '#cbd5e1');

                        html += `
                            <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:0.55rem 0.75rem;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.4rem;gap:0.75rem;">
                                <div style="flex:1;">
                                    <div style="font-size:0.82rem;font-weight:600;color:#f1f5f9;line-height:1.4;">
                                        ${c.url ? `<a href="${c.url}" target="_blank" style="color:#f1f5f9;text-decoration:none;" onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#f1f5f9'">${c.headline} ↗</a>` : c.headline}
                                    </div>
                                    <div style="display:flex;gap:0.4rem;align-items:center;margin-top:0.25rem;font-size:0.7rem;color:#94a3b8;">
                                        <span>${c.source || 'News Wire'}</span>
                                        <span>•</span>
                                        <span>${c.date ? c.date.slice(0, 16) : 'Recent'}</span>
                                        ${c.category ? `<span class="signal-badge" style="background:rgba(59,130,246,0.12);color:#93c5fd;font-size:0.62rem;padding:0.05rem 0.35rem;">${c.category}</span>` : ''}
                                    </div>
                                </div>
                                <div style="display:flex;flex-direction:column;align-items:flex-end;gap:0.2rem;white-space:nowrap;">
                                    <span style="font-size:0.65rem;font-weight:700;color:${sentimentColor};background:${sentimentBg};padding:0.1rem 0.4rem;border-radius:4px;text-transform:uppercase;">
                                        ${c.sentiment || 'Neutral'}
                                    </span>
                                    ${c.impact_score ? `<span style="font-size:0.65rem;font-family:var(--font-mono);color:${impactColor};">Impact: ${c.impact_score}/100</span>` : ''}
                                </div>
                            </div>
                        `;
                    });
                    html += '</div>';

                    cont.innerHTML = html;
                    cont.setAttribute('data-loaded', 'true');
                } catch (e) {
                    cont.innerHTML = `<div style="color:#f87171;padding:0.75rem;font-size:0.78rem;">Error fetching news: ${e.message}</div>`;
                }
            },

            setResultsTableDensity(mode) {
                const tables = document.querySelectorAll('#resultsReportSections table.results-table');
                const btnCompact = document.getElementById('densityBtnCompact');
                const btnStd = document.getElementById('densityBtnStandard');

                if (mode === 'compact') {
                    tables.forEach(t => {
                        t.style.fontSize = '0.72rem';
                        t.querySelectorAll('th, td').forEach(c => c.style.padding = '0.32rem 0.48rem');
                    });
                    if (btnCompact) { btnCompact.style.background = 'rgba(255,255,255,0.12)'; btnCompact.style.color = '#ffffff'; }
                    if (btnStd) { btnStd.style.background = 'transparent'; btnStd.style.color = '#71717a'; }
                } else {
                    tables.forEach(t => {
                        t.style.fontSize = '0.78rem';
                        t.querySelectorAll('th, td').forEach(c => c.style.padding = '0.5rem 0.75rem');
                    });
                    if (btnCompact) { btnCompact.style.background = 'transparent'; btnCompact.style.color = '#71717a'; }
                    if (btnStd) { btnStd.style.background = 'rgba(255,255,255,0.12)'; btnStd.style.color = '#ffffff'; }
                }
            },

            exportResultsToCsv() {
                const rows = document.querySelectorAll('#resultsReportSections table.results-table tbody tr:not(.row-drawer-tr):not([style*="display: none"])');
                if (!rows.length) {
                    alert('No visible rows to export.');
                    return;
                }

                const headers = ['Ticker', 'Result Date', 'Market Cap', 'Price', '30D Return', 'Q1 Wk H/L', 'Q2 Wk H/L', 'Q3 Wk H/L', '52W H/L', 'Quality Scores', '3Q Avg', 'Resistance', 'Support', 'Consensus'];
                const csvData = [headers.join(',')];

                rows.forEach(r => {
                    const cols = Array.from(r.querySelectorAll('td')).map(td => {
                        let text = td.textContent.replace(/\s+/g, ' ').trim().replace(/"/g, '""');
                        return `"${text}"`;
                    });
                    if (cols.length >= 13) {
                        csvData.push(cols.slice(0, 14).join(','));
                    }
                });

                const blob = new Blob([csvData.join('\n')], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `corporate_results_${new Date().toISOString().slice(0, 10)}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            },

            exportResultsToJson() {
                const rows = document.querySelectorAll('#resultsReportSections table.results-table tbody tr:not(.row-drawer-tr):not([style*="display: none"])');
                if (!rows.length) {
                    alert('No visible rows to export.');
                    return;
                }

                const results = [];
                rows.forEach(r => {
                    const ticker = r.querySelector('.stock-ticker-main')?.textContent.replace(/[^A-Za-z0-9._-]/g, '') || '';
                    const company = r.querySelector('.stock-company-sub')?.textContent.trim() || '';
                    const date = r.querySelector('.cell-earnings-date')?.textContent.trim() || '';
                    const mcap = r.querySelector('.cell-market-cap')?.textContent.trim() || '';
                    const price = r.querySelector('.cell-current-price')?.textContent.trim() || '';
                    const ret30d = r.querySelector('.cell-thirty-day-return')?.textContent.trim() || '';
                    const consensus = r.querySelector('.cell-ai-consensus')?.textContent.trim() || '';

                    results.push({ ticker, company, date, mcap, price, ret30d, consensus });
                });

                const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `corporate_results_${new Date().toISOString().slice(0, 10)}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            },

        // [] → extracted to modules/recalculate.js
        // [month_filter] -> extracted to modules/month_filter.js
        // [consensus] -> extracted to modules/consensus.js
        // [customizer] -> extracted to modules/customizer.js
        // [stock_rating] -> extracted to modules/stock_rating.js
        // [watchlist_modal] -> extracted to modules/watchlist_modal.js
        // [catalyst_consensus] -> extracted to modules/catalyst_consensus.js
        // [breakout_radar] -> extracted to modules/breakout_radar.js
        // [tracked_breakouts] -> extracted to modules/tracked_breakouts.js
        // [schedules] -> extracted to modules/schedules.js
        // [breakout_audit] -> extracted to modules/breakout_audit.js
        // [institutional] -> extracted to modules/institutional.js
        });

        // Safe boot sequence: ensures all modular script tags have loaded & attached to window.app
        function bootApp() {
            if (typeof app.init === 'function' && !app._initialized) {
                app._initialized = true;
                try { app.init(); } catch (e) { console.warn('[dashboard] app.init error:', e); }
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootApp);
        } else {
            bootApp();
        }
