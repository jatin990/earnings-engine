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
                'results': ['/static/js/modules/recalculate.js', '/static/js/modules/results_ledger.js'],
                'monthfilter': ['/static/js/modules/consensus.js', '/static/js/modules/swing_range.js', '/static/js/modules/month_filter.js'],
                'scanner': ['/static/js/modules/consensus.js', '/static/js/modules/scanner.js'],
                'catalysts': ['/static/js/modules/schedules.js', '/static/js/modules/catalysts.js', '/static/js/modules/catalyst_consensus.js'],
                'premarket': ['/static/js/modules/premarket.js'],
                'morning-setups': ['/static/js/modules/morning_setups.js'],
                'gainers': ['/static/js/modules/consensus.js', '/static/js/modules/gainers.js'],
                'breakout': ['/static/js/modules/tier_pool.js', '/static/js/modules/consensus.js', '/static/js/modules/schedules.js', '/static/js/modules/swing_range.js', '/static/js/modules/breakout_audit.js', '/static/js/modules/tracked_breakouts.js', '/static/js/modules/results_breakout.js', '/static/js/modules/stock_rating.js', '/static/js/modules/stock_note.js', '/static/js/modules/breakout_radar.js'],
                'institutional': ['/static/js/modules/institutional.js'],
                'tri-confluence': ['/static/js/modules/tier_pool.js', '/static/js/modules/tri_confluence.js'],
                'repeaters': ['/static/js/modules/repeaters.js'],
                'new-additions': ['/static/js/modules/new_additions.js'],
                'swing': ['/static/js/modules/tier_pool.js', '/static/js/modules/swing_range.js', '/static/js/modules/swing.js'],
                'kronos': ['/static/js/modules/consensus.js'],
                'consensus': ['/static/js/modules/consensus.js'],
                'buydip': ['/static/js/modules/tier_pool.js', '/static/js/modules/buy_dip.js'],
                'playground': ['/static/js/modules/schedules.js', '/static/js/modules/playground.js'],
                'watchlist': ['/static/js/modules/swing_range.js', '/static/js/modules/watchlist_modal.js', '/static/js/modules/watchlist.js'],
                'backtest': ['/static/js/modules/backtest.js'],
                'coverage': ['/static/js/modules/coverage.js'],
                'industries': ['/static/js/modules/industries.js'],
                'patterns': ['/static/js/modules/consensus.js', '/static/js/modules/patterns.js'],
                'options': ['/static/js/modules/options_compass_renderer.js', '/static/js/modules/options_hub.js'],
                'commodities': ['/static/js/modules/commodities.js']
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
                const version = '20260915_v26_returns_strip';
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
            async setSwingSubTab(tabName) {
                await this.loadScript('/static/js/modules/swing_range.js');
                await this.loadScript('/static/js/modules/swing.js');
                if (typeof app.setSwingSubTab === 'function') {
                    return app.setSwingSubTab(tabName);
                }
            },
            async loadTopSwingers(e) {
                await this.loadScript('/static/js/modules/swing_range.js');
                await this.loadScript('/static/js/modules/swing.js');
                if (typeof app.loadTopSwingers === 'function') {
                    return app.loadTopSwingers(e);
                }
            },
            async setSwingTierFilter(tier) {
                await this.loadScript('/static/js/modules/swing.js');
                if (typeof app.setSwingTierFilter === 'function') {
                    return app.setSwingTierFilter(tier);
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
                await this.loadScript('/static/js/modules/consensus.js');
                if (app.loadConsensusCache && app.loadConsensusCache !== this.loadConsensusCache) {
                    return app.loadConsensusCache();
                }
            },
            async loadTradingAgentsCache() {
                await this.loadScript('/static/js/modules/consensus.js');
                if (app.loadTradingAgentsCache && app.loadTradingAgentsCache !== this.loadTradingAgentsCache) {
                    return app.loadTradingAgentsCache();
                }
            },
            renderConsensusBadge(ticker, market) {
                if (app.renderConsensusBadge && app.renderConsensusBadge !== this.renderConsensusBadge) {
                    return app.renderConsensusBadge(ticker, market);
                }
                return '—';
            },
            renderTradingAgentsBadge(ticker, market) {
                if (app.renderTradingAgentsBadge && app.renderTradingAgentsBadge !== this.renderTradingAgentsBadge) {
                    return app.renderTradingAgentsBadge(ticker, market);
                }
                return '—';
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
                this.setupResultsKeyboardNavigation?.();
                if (window.resultsLedger && !window.resultsLedger._initialized) {
                    window.resultsLedger.init(this);
                }
                this._bindWatchlistSelectionPersistence();
                this._restoreBdControls?.();
                this._restorePatternsControls?.();

                // Close industry dropdown popover when clicking outside
                document.addEventListener('click', (e) => {
                    const wrap = document.getElementById('resultsIndustryDropdownWrapper');
                    const panel = document.getElementById('resultsIndustryDropdownPanel');
                    if (panel && panel.style.display === 'block') {
                        if (!wrap || !wrap.contains(e.target)) {
                            panel.style.display = 'none';
                        }
                    }
                });

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

                // Check if deep link hash points to stock drawer (e.g. #stock/RELIANCE.NS)
                const curHash = window.location.hash ? window.location.hash.replace(/^#/, '').trim() : '';
                if (curHash.startsWith('stock/')) {
                    const stockSym = decodeURIComponent(curHash.substring(6)).trim();
                    if (stockSym && typeof app.openStockDrawer === 'function') {
                        setTimeout(() => app.openStockDrawer(stockSym), 100);
                    }
                }

                window.addEventListener('hashchange', () => {
                    const hash = window.location.hash ? window.location.hash.replace(/^#/, '').trim() : '';
                    if (hash.startsWith('stock/')) {
                        const stockSym = decodeURIComponent(hash.substring(6)).trim();
                        if (stockSym && typeof app.openStockDrawer === 'function') {
                            app.openStockDrawer(stockSym);
                            return;
                        }
                    }
                    const tab = this.getInitialTab();
                    this.switchTab(tab, false, false);
                });
                window.addEventListener('popstate', () => {
                    const hash = window.location.hash ? window.location.hash.replace(/^#/, '').trim() : '';
                    if (hash.startsWith('stock/')) {
                        const stockSym = decodeURIComponent(hash.substring(6)).trim();
                        if (stockSym && typeof app.openStockDrawer === 'function') {
                            app.openStockDrawer(stockSym);
                            return;
                        }
                    }
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
                const validTabs = ['home', 'results', 'monthfilter', 'scanner', 'catalysts', 'premarket', 'morning-setups', 'options', 'commodities', 'gainers', 'breakout', 'institutional', 'tri-confluence', 'transmission', 'repeaters', 'new-additions', 'swing', 'watchlist', 'kronos', 'consensus', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
                if (!validTabs.includes(name)) name = 'home';

                const previousTab = this.currentTab;
                if (previousTab === 'transmission' && name !== 'transmission') {
                    if (window.transmissionRadar && typeof window.transmissionRadar.onTabDeactivated === 'function') {
                        window.transmissionRadar.onTabDeactivated();
                    }
                }

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
                        kronos: localStorage.getItem('subtab_kronos') || 'latest',
                        swing: localStorage.getItem('subtab_swing') || 'setups'
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
                        'morning-setups': '🌅 Morning Setups (Deals & Meetings)',
                        'options': '⚡ Option Chain & Derivatives',
                        'commodities': '🥇 Commodities & Energy',
                        'gainers': 'Gainers & Breakouts',
                        'breakout': '⚡ Breakout Radar',
                        'institutional': '🏛️ Institutional Flows',
                        'tri-confluence': '🔗 Inst-Earnings Synergy',
                        'transmission': '🕸️ Transmission Lead-Lag Radar',
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
                    if (window.resultsLedger) {
                        if (!window.resultsLedger._initialized) {
                            window.resultsLedger.init(this);
                        }
                    }
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
                if (name === 'morning-setups') {
                    if (window.morningSetupsModule && typeof window.morningSetupsModule.init === 'function') {
                        window.morningSetupsModule.init();
                    }
                }
                if (name === 'options') {
                    if (typeof app.initOptionsHub === 'function') {
                        app.initOptionsHub();
                    }
                }
                if (name === 'commodities') {
                    if (window.commoditiesModule && typeof window.commoditiesModule.init === 'function') {
                        window.commoditiesModule.init();
                    }
                }
                if (name === 'gainers') {
                    const activeSub = (app._subtabState && app._subtabState['gainers']) || localStorage.getItem('subtab_gainers') || 'gainers';
                    if (typeof this.switchGainersSubTab === 'function') {
                        this.switchGainersSubTab(activeSub);
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
                if (name === 'transmission') {
                    if (!this._transmissionLoaded) {
                        this._transmissionLoaded = true;
                        if (typeof window.initTransmissionRadar === 'function') {
                            window.initTransmissionRadar();
                        }
                    } else if (window.transmissionRadar && typeof window.transmissionRadar.onTabActivated === 'function') {
                        window.transmissionRadar.onTabActivated();
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
                    const activeSub = (app._subtabState && app._subtabState['swing']) || localStorage.getItem('subtab_swing') || 'setups';
                    if (typeof this.switchSwingSubTab === 'function') {
                        this.switchSwingSubTab(activeSub);
                    }
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

            // ─── Results Ledger: delegated to results_ledger.js module ───────
            loadResultsReport()             { return window.resultsLedger?.loadReport(); },
            summarizeResults(event)         { const btn = (event && event.target) || document.getElementById('resultsSummarizeBtn'); return window.resultsLedger?.summarize(btn); },
            refreshResults()                { return window.resultsLedger?.loadReport(); },
            syncResultsCalendar(btn)        { return window.resultsLedger?.syncCalendar(btn); },
            recalculateResultsPrices(btn)   { return window.resultsLedger?.recalcPrices(btn); },
            cancelReportLoad(domain)        { if (domain === 'results') window.resultsLedger?.cancel(); },
            filterResultsTable(q)           { return window.resultsLedger?.onSearchInput(q); },
            filterResultsByMonth(key)       { return window.resultsLedger?.setMonth(key); },
            onMonthCardClick(rel)           { return window.resultsLedger?.onMonthCellClick(rel); },
            openResultsMonthModal(target)   { return window.resultsLedger?.setMonth(target); },
            closeResultsMonthModal()        { /* no-op in redesigned ledger */ },
            setResultsCapFilter(tier)       { return window.resultsLedger?.setCapFilter(tier); },
            setResultsTableDensity(mode)    { return window.resultsLedger?.setDensity(mode); },
            onResultsPresetChange(val)      { /* Range handled via dual slider and preset chips */ },
            toggleDateFilter(date, ev)      { return window.resultsLedger?.toggleDate(date, ev); },
            applyDateFilterUI()             { return window.resultsLedger?.filterTable(); },
            toggleResultsIndustryDropdown(ev){ return window.resultsLedger?.toggleIndustryDropdown(ev); },
            selectAllResultsIndustries()    { return window.resultsLedger?.selectAllIndustries(); },
            clearAllResultsIndustries()     { return window.resultsLedger?.clearAllIndustries(); },
            filterResultsIndustryList(q)    { return window.resultsLedger?.filterIndustryList(q); },
            exportResultsToCsv()            { return window.resultsLedger?.exportCsv(); },
            exportResultsToJson()           { return window.resultsLedger?.exportJson(); },
            showMoreResultsDays()           { /* flat table renders all dates */ },
            updateResultsSummaryCards()     { return window.resultsLedger?.renderMonthStrip(); },
            updateResultsMonthSummaryCards(){ return window.resultsLedger?.renderMonthStrip(); },
            renderResultsDays()             { /* table rendered by resultsLedger */ },
            sortResultsTable(th, col, type) {
                if (window.resultsLedger && window.resultsLedger.sortTable) {
                    return window.resultsLedger.sortTable(th, col, type);
                }
            },
            selectResultsStock(ticker)      { return window.resultsLedger?.openDrawer(ticker); },
            toggleRowDrawer(rowId, ticker)  { return window.resultsLedger?.openDrawer(ticker); },
            showStockNewsDrawer(rowId, ticker, ev) { if (ev) ev.stopPropagation(); return window.resultsLedger?.openDrawer(ticker); },
            recalculateRow(ticker, btn)     { return window.resultsLedger?.refreshSinglePrice(ticker, btn); },
            setupResultsKeyboardNavigation(){ /* keyboard navigation bound in resultsLedger */ },
            // ─────────────────────────────────────────────────────────────────

            async refreshSingleStockPrice(ticker, btn, event) {
                if (event) event.stopPropagation();
                if (!ticker) return;
                const origHtml = btn ? btn.innerHTML : '↻';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳';
                    btn.style.opacity = '0.7';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/ticker/recalculate?ticker=' + encodeURIComponent(ticker), {
                        method: 'POST'
                    });
                    const data = await res.json();
                    if (data.success) {
                        if (data.updated_metrics && typeof this.updateDomRowWithMetrics === 'function') {
                            this.updateDomRowWithMetrics(ticker, data.updated_metrics);
                        }
                        if (btn) {
                            btn.innerHTML = '✓';
                            btn.style.color = '#34d399';
                            setTimeout(() => {
                                btn.innerHTML = origHtml;
                                btn.style.color = '#64748b';
                                btn.disabled = false;
                                btn.style.opacity = '1';
                            }, 1500);
                        }
                    } else {
                        if (btn) {
                            btn.innerHTML = '✗';
                            btn.style.color = '#f87171';
                            setTimeout(() => {
                                btn.innerHTML = origHtml;
                                btn.style.color = '#64748b';
                                btn.disabled = false;
                                btn.style.opacity = '1';
                            }, 1500);
                        }
                    }
                } catch (e) {
                    console.error('Error refreshing price for ' + ticker, e);
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                        btn.style.opacity = '1';
                    }
                }
            },

        });

        // Universal Breakout Inspector Drawer Dispatcher
        if (!app.openBreakoutInspectorDrawer) {
            app.openBreakoutInspectorDrawer = async function(tickerOrCandidate) {
                if (typeof app.selectBreakoutCandidate !== 'function') {
                    if (app.loadTabModules) {
                        await app.loadTabModules('breakout');
                    }
                }
                if (typeof app.openBreakoutInspectorDrawer === 'function') {
                    return app.openBreakoutInspectorDrawer(tickerOrCandidate);
                }
            };
            window.openBreakoutInspectorDrawer = app.openBreakoutInspectorDrawer;
        }

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
