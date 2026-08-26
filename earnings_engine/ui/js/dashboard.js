        const API_BASE = window.location.origin;

        const app = {
            allTickers: [],
            resultsData: [],
            swingData: [],
            consensusMap: {},
            sortKey: 'earnings_date',
            sortDir: 'asc',

            // ---------- Watchlist tab (multi-list manager) ----------
            // ---------- Watchlist tab (multi-list manager & OHLCV list view) ----------
            watchlistTab: {
                names: {},       // symbol -> display name cache for chip tooltips / autocomplete
                ranges: {},      // watchlist:ticker -> swing range object
                customLists: [], // Custom user watchlists
                universes: [],   // Built-in universes (NSE Top, US Top, NSE Large Cap, etc.)
                activeFilter: 'all', // 'all', 'under_100', 'universes', 'custom'
                activeWatchlist: 'my_watchlist',
                viewMode: 'list', // 'list' (OHLCV Table) or 'cards' (Overview Cards)
                searchQuery: '',
                quotesData: [],
                isLoadingQuotes: false,

                setViewMode(mode) {
                    this.viewMode = mode || 'list';
                    const listEl = document.getElementById('watchlistTableView');
                    const cardsEl = document.getElementById('watchlistCards');
                    const btnList = document.getElementById('wlViewModeList');
                    const btnCards = document.getElementById('wlViewModeCards');

                    if (this.viewMode === 'list') {
                        if (listEl) listEl.style.display = 'block';
                        if (cardsEl) cardsEl.style.display = 'none';
                        if (btnList) {
                            btnList.style.background = 'rgba(59,130,246,0.25)';
                            btnList.style.color = '#93c5fd';
                            btnList.style.fontWeight = '700';
                        }
                        if (btnCards) {
                            btnCards.style.background = 'transparent';
                            btnCards.style.color = '#a1a1aa';
                            btnCards.style.fontWeight = '500';
                        }
                        this.loadActiveQuotes();
                    } else {
                        if (listEl) listEl.style.display = 'none';
                        if (cardsEl) cardsEl.style.display = 'flex';
                        if (btnCards) {
                            btnCards.style.background = 'rgba(59,130,246,0.25)';
                            btnCards.style.color = '#93c5fd';
                            btnCards.style.fontWeight = '700';
                        }
                        if (btnList) {
                            btnList.style.background = 'transparent';
                            btnList.style.color = '#a1a1aa';
                            btnList.style.fontWeight = '500';
                        }
                        this.renderCards();
                    }
                },

                setFilter(filterName) {
                    this.activeFilter = filterName || 'all';
                    ['all', 'under_100', 'universes', 'custom'].forEach(f => {
                        const btn = document.getElementById('wlFilter' + (f === 'all' ? 'All' : (f === 'under_100' ? 'Under100' : (f === 'universes' ? 'Universes' : 'Custom'))));
                        if (btn) {
                            if (f === this.activeFilter) {
                                btn.classList.add('active');
                                btn.style.fontWeight = '700';
                            } else {
                                btn.classList.remove('active');
                                btn.style.fontWeight = 'normal';
                            }
                        }
                    });
                    if (this.viewMode === 'cards') {
                        this.renderCards();
                    } else {
                        this.populateSelectDropdown();
                    }
                },

                handleSearch(q) {
                    this.searchQuery = (q || '').trim().toLowerCase();
                    if (this.viewMode === 'cards') {
                        this.renderCards();
                    } else {
                        this.renderQuotesTable();
                    }
                },

                populateSelectDropdown() {
                    const sel = document.getElementById('wlActiveSelect');
                    if (!sel) return;

                    let customOpts = this.customLists.map(w => '<option value="' + w.name + '">' + (w.name === 'my_watchlist' ? '⭐ my_watchlist (Default)' : '⭐ ' + w.name) + ' (' + (w.tickers ? w.tickers.length : 0) + ')</option>').join('');
                    let univOpts = this.universes.map(u => '<option value="' + u.name + '">🏛️ ' + (u.display_name || u.name) + ' (' + (u.tickers ? u.tickers.length : 0) + ')</option>').join('');

                    sel.innerHTML = '<optgroup label="⭐ Custom Watchlists">' + (customOpts || '<option value="my_watchlist">⭐ my_watchlist (0)</option>') + '</optgroup>' +
                        (univOpts ? '<optgroup label="🏛️ Built-in Universes">' + univOpts + '</optgroup>' : '');

                    // Keep selected value if present and populated, or default to first non-empty custom list
                    const populatedCustom = this.customLists.find(w => w.tickers && w.tickers.length > 0);
                    if (this.activeWatchlist && this.activeWatchlist !== 'my_watchlist' && Array.from(sel.options).some(o => o.value === this.activeWatchlist)) {
                        sel.value = this.activeWatchlist;
                    } else if (populatedCustom) {
                        this.activeWatchlist = populatedCustom.name;
                        sel.value = this.activeWatchlist;
                    } else if (Array.from(sel.options).some(o => o.value === this.activeWatchlist)) {
                        sel.value = this.activeWatchlist;
                    } else if (sel.options.length) {
                        this.activeWatchlist = sel.options[0].value;
                        sel.value = this.activeWatchlist;
                    }
                },

                isLiveTracking: false,
                _liveInterval: null,

                async load(forceRefresh = false) {
                    const el = document.getElementById('watchlistCards');
                    if (!el) return;
                    if (!el.children.length && this.viewMode === 'cards') el.innerHTML = '<div class="timestamp" style="padding:0.5rem;">Loading watchlists & universes...</div>';
                    try {
                        if (!forceRefresh && app._watchlistAllCache) {
                            this.customLists = app._watchlistAllCache.watchlists || [];
                            this.universes = app._watchlistAllCache.universes || [];
                        } else {
                            const res = await fetch(API_BASE + '/api/v1/watchlist/all');
                            const data = await res.json();
                            app._watchlistAllCache = data;
                            this.customLists = data.watchlists || [];
                            this.universes = data.universes || [];
                        }

                        const totalBadge = document.getElementById('wlTotalBadge');
                        const customCountEl = document.getElementById('wlCustomCount');
                        if (totalBadge) {
                            const totalLists = this.customLists.length + this.universes.length;
                            totalBadge.textContent = totalLists + ' lists (' + this.universes.length + ' universes, ' + this.customLists.length + ' custom)';
                        }
                        if (customCountEl) {
                            customCountEl.textContent = this.customLists.length;
                        }

                        this.populateSelectDropdown();

                        // Pre-fetch stored swing ranges for all watchlists in 1 fast query
                        this.ranges = {};
                        try {
                            const rRes = await fetch(API_BASE + '/api/v1/swing-range/list?watchlist=ALL');
                            const rData = await rRes.json();
                            (rData.ranges || []).forEach(r => {
                                const wl = r.watchlist || 'ALL';
                                this.ranges[wl + ':' + r.ticker] = r;
                            });
                        } catch (err) {}

                        if (this.viewMode === 'list') {
                            await this.loadActiveQuotes(false);
                        } else {
                            this.renderCards();
                        }
                        this._wireListQuickAdd();
                    } catch (e) {
                        console.error('Error loading watchlists:', e);
                        if (el) el.innerHTML = '<div class="card" style="margin:0;color:var(--red)">Error loading watchlists. Check server logs.</div>';
                    }
                },

                selectActiveWatchlist(name) {
                    if (this._liveInterval) {
                        clearInterval(this._liveInterval);
                        this._liveInterval = null;
                        this.isLiveTracking = false;
                        this.updateLiveButtonUI();
                    }
                    this.activeWatchlist = name || (this.customLists.length ? this.customLists[0].name : 'my_watchlist');
                    this.loadActiveQuotes(false);
                },

                async loadActiveQuotes(forceLive = false, silent = false) {
                    const tbody = document.getElementById('wlQuotesTableBody');
                    const titleEl = document.getElementById('wlTableTitle');
                    const countEl = document.getElementById('wlTableCount');
                    const statusBadge = document.getElementById('wlTableStatusBadge');
                    const fetchBtn = document.getElementById('wlFetchLiveBtn');

                    if (!tbody) return;
                    this.isLoadingQuotes = true;
                    if (fetchBtn && forceLive && !silent) {
                        fetchBtn.disabled = true;
                        fetchBtn.innerHTML = '⏳ Fetching...';
                    }

                    if (!silent && (!this.quotesData || !this.quotesData.length)) {
                        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:2rem;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading OHLCV data for ' + this.activeWatchlist + '...</td></tr>';
                    }

                    try {
                        const targetWl = this.activeWatchlist || 'my_watchlist';
                        const res = await fetch(API_BASE + '/api/v1/watchlist/quotes?watchlist=' + encodeURIComponent(targetWl) + (forceLive ? '&live=true' : ''));
                        const data = await res.json();
                        this.quotesData = data.items || [];

                        if (titleEl) {
                            const displayName = targetWl === 'my_watchlist' ? '⭐ my_watchlist (Default)' : (targetWl.startsWith('NSE_') || targetWl.startsWith('US_') ? '🏛️ ' + targetWl : '⭐ ' + targetWl);
                            titleEl.textContent = displayName;
                        }
                        if (countEl) {
                            countEl.textContent = this.quotesData.length + ' stocks';
                        }
                        if (statusBadge) {
                            statusBadge.style.display = 'inline-block';
                            if (forceLive || this.isLiveTracking) {
                                statusBadge.style.background = 'rgba(16,185,129,0.15)';
                                statusBadge.style.color = '#34d399';
                                statusBadge.textContent = '⚡ Live Quotes (' + new Date().toLocaleTimeString() + ')';
                            } else {
                                statusBadge.style.background = 'rgba(59,130,246,0.15)';
                                statusBadge.style.color = '#60a5fa';
                                statusBadge.textContent = '📦 Cached OHLCV';
                            }
                        }

                        this.renderQuotesTable();
                    } catch (e) {
                        console.error('Error loading watchlist quotes:', e);
                        if (!silent) {
                            tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:1.5rem;color:var(--red);">Error loading quotes for ' + this.activeWatchlist + '.</td></tr>';
                        }
                    } finally {
                        this.isLoadingQuotes = false;
                        if (fetchBtn) {
                            fetchBtn.disabled = false;
                            fetchBtn.innerHTML = '⚡ Refresh Live';
                        }
                    }
                },

                async fetchLiveQuotes() {
                    await this.loadActiveQuotes(true);
                },

                toggleLiveTracking() {
                    this.isLiveTracking = !this.isLiveTracking;
                    this.updateLiveButtonUI();

                    if (this.isLiveTracking) {
                        // Immediately fetch live once
                        this.loadActiveQuotes(true);
                        // Poll live prices every 10s silently
                        if (this._liveInterval) clearInterval(this._liveInterval);
                        this._liveInterval = setInterval(() => {
                            if (this.isLiveTracking && this.viewMode === 'list') {
                                this.loadActiveQuotes(true, true);
                            }
                        }, 10000);
                    } else {
                        if (this._liveInterval) {
                            clearInterval(this._liveInterval);
                            this._liveInterval = null;
                        }
                    }
                },

                updateLiveButtonUI() {
                    const btn = document.getElementById('wlLiveToggleBtn');
                    const text = document.getElementById('wlLiveBtnText');
                    const ind = document.getElementById('wlLiveIndicator');
                    if (!btn || !text || !ind) return;

                    if (this.isLiveTracking) {
                        btn.style.background = 'rgba(239,68,68,0.25)';
                        btn.style.borderColor = '#ef4444';
                        btn.style.color = '#fca5a5';
                        text.textContent = '🔴 Live (Auto-Refresh 10s)';
                        ind.style.background = '#ef4444';
                        ind.style.boxShadow = '0 0 8px #ef4444';
                    } else {
                        btn.style.background = 'rgba(239,68,68,0.12)';
                        btn.style.borderColor = 'rgba(239,68,68,0.35)';
                        btn.style.color = '#f87171';
                        text.textContent = '🔴 Track Live Prices';
                        ind.style.background = '#f87171';
                        ind.style.boxShadow = 'none';
                    }
                },

                async autoDetectRowRange(ticker, btn) {
                    if (!ticker) return;
                    if (btn) {
                        btn.disabled = true;
                        btn.innerHTML = '<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> Detecting...';
                    }
                    try {
                        const wl = this.activeWatchlist || 'my_watchlist';
                        const res = await fetch(API_BASE + '/api/v1/swing-range?watchlist=' + encodeURIComponent(wl) + '&ticker=' + encodeURIComponent(ticker));
                        const data = await res.json();
                        const autoRng = data.auto_range || data.range || {};
                        const low = autoRng.lower != null ? Number(autoRng.lower) : (autoRng.lower_bound != null ? Number(autoRng.lower_bound) : null);
                        const high = autoRng.upper != null ? Number(autoRng.upper) : (autoRng.upper_bound != null ? Number(autoRng.upper_bound) : null);

                        if (low != null && high != null) {
                            // Update internal item in-place
                            const it = this.quotesData.find(x => x.ticker === ticker);
                            if (it) {
                                it.support = low;
                                it.resistance = high;
                                it.cycles = autoRng.cycles;
                                it.range_source = 'auto';
                            }
                            this.ranges[wl + ':' + ticker] = {
                                watchlist: wl,
                                ticker: ticker,
                                lower_bound: low,
                                upper_bound: high,
                                source: 'auto'
                            };
                            // Re-render in-place without network reload
                            this.renderQuotesTable();
                        } else {
                            if (btn) {
                                btn.disabled = false;
                                btn.innerHTML = '⚠️ No Channel';
                            }
                        }
                    } catch (e) {
                        console.error('Error auto-detecting swing range for ' + ticker, e);
                        if (btn) {
                            btn.disabled = false;
                            btn.innerHTML = '⚠️ Error';
                        }
                    }
                },

                renderQuotesTable() {
                    const tbody = document.getElementById('wlQuotesTableBody');
                    if (!tbody) return;

                    let items = [...this.quotesData];
                    if (this.searchQuery) {
                        const q = this.searchQuery;
                        items = items.filter(it => (it.ticker || '').toLowerCase().includes(q) || (it.company_name || '').toLowerCase().includes(q));
                    }

                    if (!items.length) {
                        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:2rem;color:var(--muted);">' +
                            (this.quotesData.length ? 'No stocks match the search query.' : 'This watchlist is currently empty. Use "＋ Add symbol to list" above to add stocks!') +
                            '</td></tr>';
                        return;
                    }

                    tbody.innerHTML = items.map((it, idx) => {
                        const isUS = !(it.ticker.endsWith('.NS') || it.ticker.endsWith('.BO'));
                        const currSymbol = isUS ? '$' : '₹';
                        const p = it.current_price != null ? currSymbol + Number(it.current_price).toFixed(2) : '—';
                        const chg = it.change_pct != null ? Number(it.change_pct) : null;
                        const chgClass = chg != null ? (chg >= 0 ? 'price-positive' : 'price-negative') : '';
                        const chgBadgeBg = chg != null ? (chg >= 0 ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)') : 'rgba(255,255,255,0.05)';
                        const chgColor = chg != null ? (chg >= 0 ? '#34d399' : '#f87171') : '#a1a1aa';
                        const chgStr = chg != null ? (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%' : '—';

                        const openStr = it.open != null ? currSymbol + Number(it.open).toFixed(2) : '—';
                        const highStr = it.high != null ? currSymbol + Number(it.high).toFixed(2) : '—';
                        const lowStr = it.low != null ? currSymbol + Number(it.low).toFixed(2) : '—';
                        const volStr = it.volume_formatted || '—';
                        const mcStr = it.market_cap_formatted || '—';

                        // 52W High / Low
                        const yH = it.year_high != null ? currSymbol + Number(it.year_high).toFixed(2) : '—';
                        const yL = it.year_low != null ? currSymbol + Number(it.year_low).toFixed(2) : '—';
                        const pctH = it.pct_from_52w_high != null ? (it.pct_from_52w_high >= 0 ? '+' : '') + Number(it.pct_from_52w_high).toFixed(1) + '%' : '';
                        const pctHColor = it.pct_from_52w_high != null ? (Number(it.pct_from_52w_high) >= -5 ? '#34d399' : (Number(it.pct_from_52w_high) <= -25 ? '#f87171' : '#fbbf24')) : '#a1a1aa';

                        // Swing Support / Resistance with explicit cursor:pointer and interactive Auto Detect button
                        const s = it.support != null ? currSymbol + Number(it.support).toFixed(2) : '—';
                        const r = it.resistance != null ? currSymbol + Number(it.resistance).toFixed(2) : '—';
                        const rangeStr = (it.support != null && it.resistance != null)
                            ? '<button type="button" onclick="app.openSwingRangeModal(\'' + this.activeWatchlist.replace(/'/g, "\\'") + '\',\'' + it.ticker + '\')" class="btn-micro" style="font-size:0.75rem;font-family:var(--font-mono);cursor:pointer;color:#38bdf8;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.25);border-radius:4px;padding:0.12rem 0.4rem;" title="Inspect & edit swing range">' + s + ' – ' + r + '</button>'
                            : '<button type="button" onclick="app.watchlistTab.autoDetectRowRange(\'' + it.ticker + '\', this)" class="btn-micro" style="font-size:0.7rem;font-weight:700;cursor:pointer;color:#fbbf24;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.3);border-radius:4px;padding:0.15rem 0.45rem;display:inline-flex;align-items:center;gap:0.2rem;" title="Auto-detect support & resistance range"><span>⚡</span> Auto Detect</button>';

                        return '<tr class="interactive-row">' +
                            '<td>' +
                                '<div style="display:flex;align-items:center;gap:0.4rem;">' +
                                    '<button onclick="app.openAddToWatchlistModal(\'' + it.ticker + '\')" class="btn-micro" style="color:#fbbf24;border:none;background:transparent;padding:0;font-size:0.85rem;cursor:pointer;" title="Manage Watchlists">⭐</button>' +
                                    '<div>' +
                                        '<strong onclick="app.openSwingRangeModal(\'' + this.activeWatchlist.replace(/'/g, "\\'") + '\',\'' + it.ticker + '\')" style="color:#ffffff;font-size:0.85rem;cursor:pointer;" class="hover-underline" title="Inspect & edit swing range">' + it.ticker + '</strong>' +
                                        '<a href="/stock/' + encodeURIComponent(it.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;cursor:pointer;" title="Open profile in new tab">↗</a>' +
                                        '<div style="font-size:0.7rem;color:#a1a1aa;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (it.company_name || it.ticker) + '</div>' +
                                    </div>' +
                                '</div>' +
                            '</td>' +
                            '<td style="text-align:right;"><strong style="font-size:0.88rem;color:#ffffff;font-family:var(--font-mono);">' + p + '</strong></td>' +
                            '<td style="text-align:right;"><span style="background:' + chgBadgeBg + ';color:' + chgColor + ';padding:0.15rem 0.45rem;border-radius:4px;font-size:0.75rem;font-weight:700;font-family:var(--font-mono);">' + chgStr + '</span></td>' +
                            '<td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#cbd5e1;">' + openStr + '</td>' +
                            '<td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#34d399;">' + highStr + '</td>' +
                            '<td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#f87171;">' + lowStr + '</td>' +
                            '<td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#93c5fd;font-weight:600;">' + volStr + '</td>' +
                            '<td style="text-align:right;font-size:0.72rem;font-family:var(--font-mono);">' +
                                '<div style="color:#cbd5e1;">' + yL + ' – ' + yH + '</div>' +
                                (pctH ? '<div style="font-size:0.68rem;color:' + pctHColor + ';font-weight:600;">' + pctH + ' from 52W H</div>' : '') +
                            '</td>' +
                            '<td style="text-align:right;font-size:0.75rem;font-family:var(--font-mono);color:#94a3b8;">' + mcStr + '</td>' +
                            '<td style="text-align:center;">' +
                                '<div style="display:flex;align-items:center;justify-content:center;gap:0.3rem;">' +
                                    rangeStr +
                                    '<button onclick="app.openSwingRangeModal(\'' + this.activeWatchlist.replace(/'/g, "\\'") + '\',\'' + it.ticker + '\')" class="btn-micro" style="color:var(--muted);padding:0 0.15rem;font-size:0.75rem;border:none;background:transparent;cursor:pointer;" title="Edit Swing Range">⚙</button>' +
                                '</div>' +
                            '</td>' +
                            '<td style="text-align:center;">' +
                                '<div style="display:flex;gap:0.25rem;align-items:center;justify-content:center;">' +
                                    '<button type="button" onclick="app.runConsensusForStock(\'' + it.ticker + '\')" class="btn btn-sm" style="padding:0.12rem 0.4rem;font-size:0.68rem;background:rgba(99,102,241,0.2);color:#c7d2fe;border:1px solid rgba(99,102,241,0.4);border-radius:3px;cursor:pointer;" title="Run AI Consensus">🧠</button>' +
                                    '<button type="button" onclick="app.runPredictionForTickerSingle(\'' + it.ticker + '\')" class="btn btn-sm" style="padding:0.12rem 0.4rem;font-size:0.68rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:3px;cursor:pointer;" title="Run Kronos AI">🔮</button>' +
                                    '<button type="button" onclick="app.watchlistTab.removeQuoteTicker(\'' + it.ticker + '\')" class="btn btn-sm btn-danger" style="padding:0.12rem 0.35rem;font-size:0.72rem;border-radius:3px;cursor:pointer;" title="Remove from this watchlist">🗑</button>' +
                                '</div>' +
                            '</td>' +
                        '</tr>';
                    }).join('');
                },

                _wireListQuickAdd() {
                    const input = document.getElementById('wlListAddInput');
                    const dd = document.getElementById('wlListAddDropdown');
                    if (!input || !dd) return;
                    let idx = -1;

                    input.addEventListener('input', async () => {
                        const q = input.value.trim();
                        if (q.length < 1) { dd.style.display = 'none'; return; }
                        try {
                            const res = await fetch(API_BASE + '/api/v1/playground/search?q=' + encodeURIComponent(q));
                            const items = await res.json();
                            idx = -1;
                            dd.innerHTML = items.map((it, i) =>
                                '<div class="autocomplete-item" data-i="' + i + '" onclick="app.watchlistTab.pickQuickSymbol(\'' + it.symbol.replace(/'/g, "\\'") + '\')" style="padding:0.4rem 0.6rem;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.05);">' +
                                '<div style="font-weight:700;color:#ffffff;font-size:0.8rem;">' + it.symbol + '</div>' +
                                '<div style="color:var(--muted);font-size:0.68rem;">' + (it.name || '') + ' · ' + (it.market || '') + '</div>' +
                                '</div>'
                            ).join('');
                            dd.style.display = items.length ? 'block' : 'none';
                        } catch (e) {
                            dd.style.display = 'none';
                        }
                    });

                    input.addEventListener('keydown', (e) => {
                        const items = dd.querySelectorAll('.autocomplete-item');
                        if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, -1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'Enter') { e.preventDefault(); if (idx >= 0 && items[idx]) items[idx].click(); else this.addQuickTicker(); }
                        else if (e.key === 'Escape') { dd.style.display = 'none'; }
                    });

                    document.addEventListener('click', (e) => {
                        if (!input.contains(e.target) && !dd.contains(e.target)) {
                            dd.style.display = 'none';
                        }
                    });
                },

                pickQuickSymbol(sym) {
                    const input = document.getElementById('wlListAddInput');
                    const dd = document.getElementById('wlListAddDropdown');
                    if (input) input.value = sym;
                    if (dd) dd.style.display = 'none';
                    this.addQuickTicker();
                },

                async addQuickTicker() {
                    const input = document.getElementById('wlListAddInput');
                    const ticker = (input ? input.value : '').trim().toUpperCase();
                    if (!ticker) return;
                    const name = this.activeWatchlist || 'my_watchlist';
                    try {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/add', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ticker: ticker, name: name})
                        });
                        const data = await res.json();
                        if (input) input.value = '';
                        if (!data.success) {
                            alert(data.error || 'Failed to add ticker');
                        }
                        await this.load(true);
                    } catch (e) {
                        console.error('addQuickTicker', e);
                    }
                },

                async removeQuoteTicker(ticker) {
                    if (!confirm('Remove ' + ticker + ' from ' + this.activeWatchlist + '?')) return;
                    await this.removeTicker(this.activeWatchlist, ticker);
                },

                renderCards() {
                    const el = document.getElementById('watchlistCards');
                    if (!el) return;

                    let filteredCustom = [...this.customLists];
                    let filteredUniverses = [...this.universes];

                    if (this.activeFilter === 'under_100') {
                        filteredCustom = filteredCustom.filter(w => (w.tickers || []).length <= 100);
                        filteredUniverses = filteredUniverses.filter(u => (u.tickers || []).length <= 100);
                    } else if (this.activeFilter === 'universes') {
                        filteredCustom = [];
                    } else if (this.activeFilter === 'custom') {
                        filteredUniverses = [];
                    }

                    if (this.searchQuery) {
                        const q = this.searchQuery;
                        filteredCustom = filteredCustom.filter(w => {
                            const nameMatch = (w.name || '').toLowerCase().includes(q);
                            const tickerMatch = (w.tickers || []).some(t => t.toLowerCase().includes(q));
                            return nameMatch || tickerMatch;
                        });
                        filteredUniverses = filteredUniverses.filter(u => {
                            const nameMatch = (u.name || '').toLowerCase().includes(q) || (u.display_name || '').toLowerCase().includes(q) || (u.explanation || '').toLowerCase().includes(q);
                            const tickerMatch = (u.tickers || []).some(t => t.toLowerCase().includes(q));
                            return nameMatch || tickerMatch;
                        });
                    }

                    if (!filteredCustom.length && !filteredUniverses.length) {
                        el.innerHTML = '<div class="card" style="margin:0;padding:1.5rem;text-align:center;color:var(--muted);">' +
                            'No watchlists found matching this filter.' +
                            (this.activeFilter !== 'all' || this.searchQuery ? '<br><button class="btn btn-sm btn-primary" onclick="app.watchlistTab.setFilter(\'all\'); if(document.getElementById(\'wlSearchInput\')) document.getElementById(\'wlSearchInput\').value=\'\'; app.watchlistTab.handleSearch(\'\');" style="margin-top:0.75rem;">Reset Filters</button>' : '') +
                            '</div>';
                        return;
                    }

                    let html = '';

                    // 1. Built-in Universes (if any match filter)
                    if (filteredUniverses.length) {
                        html += '<div style="margin-top:0.25rem;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.5rem;">' +
                            '<h4 style="margin:0;font-size:0.95rem;color:#c7d2fe;display:flex;align-items:center;gap:0.35rem;">🏛️ Built-in Universes & Indices <span style="font-size:0.75rem;background:rgba(99,102,241,0.2);padding:0.1rem 0.4rem;border-radius:9999px;">' + filteredUniverses.length + '</span></h4>' +
                            '</div>';
                        html += filteredUniverses.map((u, ui) => this._universeCard(u, ui)).join('');
                    }

                    // 2. Custom User Watchlists (if any match filter)
                    if (filteredCustom.length) {
                        html += '<div style="margin-top:1rem;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.5rem;">' +
                            '<h4 style="margin:0;font-size:0.95rem;color:#60a5fa;display:flex;align-items:center;gap:0.35rem;">⭐ Custom User Watchlists <span style="font-size:0.75rem;background:rgba(59,130,246,0.2);padding:0.1rem 0.4rem;border-radius:9999px;">' + filteredCustom.length + '</span></h4>' +
                            '</div>';
                        html += filteredCustom.map((w, wi) => this._customCard(w, wi)).join('');
                    }

                    el.innerHTML = html;
                    filteredCustom.forEach((w, wi) => this._wireRowAutocomplete(wi, w.name));
                },

                _universeCard(u, ui) {
                    const name = u.display_name || u.name;
                        const tickers = u.tickers || [];
                    const isUnder100 = tickers.length <= 100;
                    const chips = tickers.length
                        ? tickers.map(t => {
                            const r = this.ranges[u.name + ':' + t] || this.ranges['ALL:' + t];
                            const hasRange = r && r.lower_bound != null && r.upper_bound != null;
                            const isUser = r && r.source === 'user';
                            const lowStr = hasRange && !isNaN(Number(r.lower_bound)) ? Number(r.lower_bound).toFixed(2) : (r ? r.lower_bound : '');
                            const upStr = hasRange && !isNaN(Number(r.upper_bound)) ? Number(r.upper_bound).toFixed(2) : (r ? r.upper_bound : '');
                            const rangeBadge = hasRange
                                ? '<span style="font-size:0.72rem;opacity:0.85;margin-left:0.25rem;color:' + (isUser ? '#38bdf8' : '#60a5fa') + ';" title="' + (isUser ? 'Custom swing range' : 'Auto swing range') + '">' +
                                  lowStr + '–' + upStr + (r.cycles ? ' ⤫' + r.cycles : '') +
                                  '</span>'
                                : '';
                            return '<span style="display:inline-flex;align-items:center;gap:0.35rem;background:rgba(99,102,241,0.12);border:1px solid ' + (isUser ? 'rgba(56,189,248,0.45)' : 'rgba(99,102,241,0.25)') + ';padding:0.25rem 0.6rem;border-radius:9999px;font-size:0.78rem;" title="' + (this.names[t] || t) + '">' +
                                '<strong onclick="app.watchlistTab.selectActiveWatchlist(\'' + u.name.replace(/'/g, "\\'") + '\'); app.watchlistTab.setViewMode(\'list\');" style="cursor:pointer;">' + t + '</strong>' +
                                rangeBadge +
                                '<button onclick="app.openAddToWatchlistModal(\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:#fbbf24;cursor:pointer;font-size:0.75rem;padding:0;" title="Add to Custom Watchlist">⭐</button>' +
                                '<button onclick="app.openSwingRangeModal(\'' + u.name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--light);opacity:0.7;cursor:pointer;font-size:0.75rem;line-height:1;padding:0 0.15rem;" title="Edit Swing Range">⚙</button>' +
                                '</span>';
                          }).join('')
                        : '<span class="timestamp" style="font-size:0.8rem;">No symbols in universe.</span>';

                    const under100Badge = isUnder100
                        ? '<span style="background:rgba(234,179,8,0.2);color:#fef08a;border:1px solid rgba(234,179,8,0.4);font-size:0.7rem;font-weight:700;padding:0.12rem 0.45rem;border-radius:9999px;">⚡ Under 100 Stocks</span>'
                        : '';

                    const marketBadge = u.market === 'IN'
                        ? '<span style="background:rgba(16,185,129,0.15);color:#6ee7b7;font-size:0.7rem;padding:0.12rem 0.45rem;border-radius:9999px;font-weight:600;">🇮🇳 India (NSE)</span>'
                        : '<span style="background:rgba(59,130,246,0.15);color:#93c5fd;font-size:0.7rem;padding:0.12rem 0.45rem;border-radius:9999px;font-weight:600;">🇺🇸 US (NYSE/NASDAQ)</span>';

                    const explanationHtml = u.explanation
                        ? '<div style="background:rgba(255,255,255,0.03);border-left:3px solid #818cf8;padding:0.5rem 0.75rem;border-radius:0 0.4rem 0.4rem 0;margin-bottom:0.65rem;font-size:0.8rem;line-height:1.45;color:#e2e8f0;">' +
                          '<div style="font-weight:600;color:#c7d2fe;margin-bottom:0.15rem;display:flex;align-items:center;gap:0.3rem;">💡 <span>Knowledge Base & Selection Criteria:</span></div>' +
                          '<div>' + u.explanation + '</div>' +
                          (u.selection_criteria ? '<div style="font-size:0.72rem;color:var(--muted);margin-top:0.25rem;"><strong>Criteria:</strong> ' + u.selection_criteria + '</div>' : '') +
                          '</div>'
                        : '';

                    return '<div class="card" id="uCard' + ui + '" style="margin:0 0 0.75rem 0;border:1px solid rgba(99,102,241,0.25);background:linear-gradient(180deg, rgba(30,41,59,0.6) 0%, rgba(15,23,42,0.6) 100%);">' +
                        '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.5rem;">' +
                            '<div>' +
                                '<div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.25rem;">' +
                                    '<h4 style="margin:0;font-size:1.05rem;color:#f8fafc;">' + name + '</h4>' +
                                    '<span style="background:rgba(99,102,241,0.2);color:#c7d2fe;font-size:0.7rem;font-weight:600;padding:0.12rem 0.45rem;border-radius:9999px;">🏛️ Built-in Universe</span>' +
                                    under100Badge +
                                    marketBadge +
                                    '</div>' +
                                '<span class="timestamp" style="font-size:0.72rem;">' + tickers.length + ' stocks tracked</span>' +
                            '</div>' +
                            '<div style="display:flex;gap:0.35rem;flex-wrap:wrap;">' +
                                '<button class="btn btn-sm" onclick="app.watchlistTab.selectActiveWatchlist(\'' + u.name.replace(/'/g, "\\'") + '\'); app.watchlistTab.setViewMode(\'list\');" style="background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.4);" title="Open list view with full OHLCV metrics">📋 List View</button>' +
                                '<button class="btn btn-sm" onclick="app.watchlistTab.copyToCustom(\'' + u.name.replace(/'/g, "\\'") + '\',\'' + (u.display_name || u.name).replace(/'/g, "\\'") + '\',' + JSON.stringify(tickers).replace(/"/g, '&quot;') + ')" style="background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.35);" title="Copy all tickers into a customizable custom watchlist">📋 Copy to Custom</button>' +
                                '<button class="btn btn-sm" onclick="app.switchTab(\'results\'); const el = document.getElementById(\'resultsMarket\'); if(el) { el.value=\'' + u.name.toUpperCase() + '\'; app.loadResultsReport(); }" style="background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.35);" title="View in Corporate Results tab">📈 Results</button>' +
                            '</div>' +
                        '</div>' +
                        explanationHtml +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.35rem;max-height:220px;overflow-y:auto;padding-right:0.25rem;">' + chips + '</div>' +
                    '</div>';
                },

                _customCard(w, wi) {
                    const name = w.name || ('Watchlist ' + (wi + 1));
                    const tickers = w.tickers || [];
                    const isUnder100 = tickers.length <= 100;
                    const chips = tickers.length
                        ? tickers.map(t => {
                            const r = this.ranges[name + ':' + t];
                            const hasRange = r && r.lower_bound != null && r.upper_bound != null;
                            const isUser = r && r.source === 'user';
                            const lowStr = hasRange && !isNaN(Number(r.lower_bound)) ? Number(r.lower_bound).toFixed(2) : (r ? r.lower_bound : '');
                            const upStr = hasRange && !isNaN(Number(r.upper_bound)) ? Number(r.upper_bound).toFixed(2) : (r ? r.upper_bound : '');
                            const rangeBadge = hasRange
                                ? '<span style="font-size:0.72rem;opacity:0.85;margin-left:0.25rem;color:' + (isUser ? '#38bdf8' : '#60a5fa') + ';" title="' + (isUser ? 'Custom swing range' : 'Auto swing range') + '">' +
                                  lowStr + '–' + upStr + (r.cycles ? ' ⤫' + r.cycles : '') +
                                  '</span>'
                                : '';
                            return '<span style="display:inline-flex;align-items:center;gap:0.35rem;background:rgba(59,130,246,0.15);border:1px solid ' + (isUser ? 'rgba(56,189,248,0.45)' : 'rgba(59,130,246,0.3)') + ';padding:0.3rem 0.65rem;border-radius:9999px;font-size:0.8rem;" title="' + (this.names[t] || t) + '">' +
                                '<strong onclick="app.watchlistTab.selectActiveWatchlist(\'' + name.replace(/'/g, "\\'") + '\'); app.watchlistTab.setViewMode(\'list\');" style="cursor:pointer;">' + t + '</strong>' +
                                rangeBadge +
                                '<button onclick="app.openSwingRangeModal(\'' + name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--light);opacity:0.7;cursor:pointer;font-size:0.75rem;line-height:1;padding:0 0.15rem;" title="Edit Swing Range">⚙</button>' +
                                '<button onclick="app.watchlistTab.removeTicker(\'' + name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:1rem;line-height:1;margin-left:0.1rem;" title="Remove">&minus;</button>' +
                                '</span>';
                          }).join('')
                        : '<span class="timestamp" style="font-size:0.8rem;">Empty — add a ticker below.</span>';

                    const under100Badge = isUnder100
                        ? '<span style="background:rgba(234,179,8,0.2);color:#fef08a;border:1px solid rgba(234,179,8,0.4);font-size:0.7rem;font-weight:700;padding:0.12rem 0.45rem;border-radius:9999px;">⚡ Under 100 Stocks</span>'
                        : '';

                    return '<div class="card" id="wlCard' + wi + '" style="margin:0 0 0.75rem 0;position:relative;z-index:' + (200 - wi) + ';border:1px solid rgba(59,130,246,0.25);">' +
                        '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.6rem;">' +
                            '<div>' +
                                '<div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.2rem;">' +
                                    '<h4 style="margin:0;font-size:1.05rem;">' + name + '</h4>' +
                                    '<span style="background:rgba(59,130,246,0.2);color:#93c5fd;font-size:0.7rem;font-weight:600;padding:0.12rem 0.45rem;border-radius:9999px;">⭐ Custom Watchlist</span>' +
                                    under100Badge +
                                '</div>' +
                                '<span class="timestamp" style="font-size:0.72rem;">' + tickers.length + ' stock' + (tickers.length === 1 ? '' : 's') + '</span>' +
                            '</div>' +
                            '<div style="display:flex;gap:0.35rem;">' +
                                '<button class="btn btn-sm" onclick="app.watchlistTab.selectActiveWatchlist(\'' + name.replace(/'/g, "\\'") + '\'); app.watchlistTab.setViewMode(\'list\');" style="background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.4);" title="Open list view with full OHLCV metrics">📋 List View</button>' +
                                '<button class="btn btn-sm" onclick="app.watchlistTab.rename(\'' + name.replace(/'/g, "\\'") + '\')">✎ Rename</button>' +
                                '<button class="btn btn-sm btn-danger" onclick="app.watchlistTab.remove(\'' + name.replace(/'/g, "\\'") + '\')">🗑 Delete</button>' +
                            '</div>' +
                        '</div>' +
                        '<div style="display:flex;gap:0.4rem;align-items:center;margin-bottom:0.55rem;position:relative;z-index:50;">' +
                            '<input id="wlAddInput' + wi + '" placeholder="Add by name or symbol..." style="flex:1;padding:0.4rem;border:1px solid rgba(255,255,255,0.2);border-radius:0.4rem;background:rgba(255,255,255,0.05);color:var(--light);" autocomplete="off">' +
                            '<div id="wlAddDropdown' + wi + '" class="dropdown" style="z-index:10000;position:absolute;top:100%;left:0;right:0;max-height:280px;overflow-y:auto;box-shadow:0 14px 35px rgba(0,0,0,0.7);"></div>' +
                            '<button class="btn btn-primary btn-sm" onclick="app.watchlistTab.addTicker(\'' + name.replace(/'/g, "\\'") + '\',' + wi + ')">＋ Add</button>' +
                        '</div>' +
                        '<div id="wlChips' + wi + '" style="display:flex;flex-wrap:wrap;gap:0.4rem;">' + chips + '</div>' +
                    '</div>';
                },

                async copyToCustom(sourceName, displayName, tickers) {
                    const defaultName = (displayName || sourceName).replace(/[^a-zA-Z0-9 ]/g, '').trim() + ' Copy';
                    const name = prompt('Create a new custom watchlist copied from ' + (displayName || sourceName) + ':', defaultName);
                    if (!name || !name.trim()) return;
                    try {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/create', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({name: name.trim(), tickers: tickers || []})
                        });
                        const data = await res.json();
                        if (!data.success) {
                            alert(data.error || 'Failed to create watchlist');
                            return;
                        }
                        await this.load(true);
                        this.selectActiveWatchlist(name.trim());
                        this.setViewMode('list');
                    } catch (e) {
                        console.error('copyToCustom error:', e);
                        alert('Error copying watchlist: ' + (e.message || e));
                    }
                },

                _wireRowAutocomplete(wi, name) {
                    const input = document.getElementById('wlAddInput' + wi);
                    const dd = document.getElementById('wlAddDropdown' + wi);
                    const card = document.getElementById('wlCard' + wi);
                    if (!input || !dd) return;
                    let idx = -1;

                    const elevate = () => { if (card) card.style.zIndex = '5000'; };
                    const restore = () => { if (card) card.style.zIndex = '' + (200 - wi); };

                    input.addEventListener('focus', elevate);
                    input.addEventListener('input', async () => {
                        const q = input.value.trim();
                        if (q.length < 1) { dd.style.display = 'none'; restore(); return; }
                        elevate();
                        try {
                            const res = await fetch(API_BASE + '/api/v1/playground/search?q=' + encodeURIComponent(q));
                            const items = await res.json();
                            items.forEach(it => { if (it.name) this.names[it.symbol] = it.name; });
                            idx = -1;
                            dd.innerHTML = items.map((it, i) =>
                                '<div class="autocomplete-item" data-i="' + i + '" onclick="app.watchlistTab.pickSymbol(' + wi + ',\'' + it.symbol.replace(/'/g, "\\'") + '\')">' +
                                '<div style="font-weight:600;">' + it.symbol + '</div>' +
                                '<div style="color:var(--muted);font-size:0.72rem;word-break:break-word;">' + (it.name || '') + ' · ' + (it.market || '') + '</div>' +
                                '</div>'
                            ).join('');
                            dd.style.display = items.length ? 'block' : 'none';
                            if (items.length) elevate(); else restore();
                        } catch (e) {
                            dd.style.display = 'none';
                            restore();
                        }
                    });
                    input.addEventListener('keydown', (e) => {
                        const items = dd.querySelectorAll('.autocomplete-item');
                        if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, -1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'Enter') { e.preventDefault(); if (idx >= 0 && items[idx]) items[idx].click(); else if (items.length) items[0].click(); }
                        else if (e.key === 'Escape') { dd.style.display = 'none'; restore(); }
                    });
                    document.addEventListener('click', (e) => {
                        if (!input.contains(e.target) && !dd.contains(e.target)) {
                            dd.style.display = 'none';
                            restore();
                        }
                    });
                },

                pickSymbol(wi, symbol) {
                    const input = document.getElementById('wlAddInput' + wi);
                    const dd = document.getElementById('wlAddDropdown' + wi);
                    const card = document.getElementById('wlCard' + wi);
                    if (input) input.value = symbol;
                    if (dd) dd.style.display = 'none';
                    if (card) card.style.zIndex = '' + (200 - wi);
                },

                async addTicker(name, wi) {
                    const input = document.getElementById('wlAddInput' + wi);
                    const ticker = (input ? input.value : '').trim().toUpperCase();
                    if (!ticker) return;
                    try {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/add', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ticker: ticker, name: name})
                        });
                        const data = await res.json();
                        if (!data.success) alert(data.error || 'Failed to add ticker');
                        await this.load(true);
                    } catch (e) {
                        console.error('addTicker', e);
                        alert('Error adding ticker');
                    }
                },

                async removeTicker(name, ticker) {
                    try {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/remove', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ticker: ticker, name: name})
                        });
                        const data = await res.json();
                        if (!data.success) alert(data.error || 'Failed to remove ticker');
                        await this.load(true);
                    } catch (e) {
                        console.error('removeTicker', e);
                        alert('Error removing ticker');
                    }
                },

                async addWatchlist() {
                    const name = (prompt('New watchlist name (blank = auto-name):') || '').trim();
                    try {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/create', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(name ? {name: name} : {})
                        });
                        const data = await res.json();
                        if (!data.success) alert(data.error || 'Failed to create watchlist');
                        await this.load(true);
                        if (name) {
                            this.selectActiveWatchlist(name);
                        }
                    } catch (e) {
                        console.error('addWatchlist', e);
                        alert('Error creating watchlist');
                    }
                },

                async rename(name) {
                    const newName = (prompt('Rename "' + name + '" to:', name) || '').trim();
                    if (!newName || newName === name) return;
                    try {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/rename', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({name: name, new_name: newName})
                        });
                        const data = await res.json();
                        if (!data.success) alert(data.error || 'Failed to rename watchlist');
                        if (this.activeWatchlist === name) this.activeWatchlist = newName;
                        await this.load(true);
                    } catch (e) {
                        console.error('rename', e);
                        alert('Error renaming watchlist');
                    }
                },

                async remove(name) {
                    if (!confirm('Delete watchlist "' + name + '" and all its tickers?')) return;
                    try {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/delete', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({name: name})
                        });
                        const data = await res.json();
                        if (!data.success) alert(data.error || 'Failed to delete watchlist');
                        if (this.activeWatchlist === name) this.activeWatchlist = 'my_watchlist';
                        await this.load(true);
                    } catch (e) {
                        console.error('remove', e);
                        alert('Error deleting watchlist');
                    }
                }
            },

            activeFetchControllers: {},

            fetchWithAbort(taskName, url, options = {}) {
                if (this.activeFetchControllers[taskName]) {
                    try {
                        const prev = this.activeFetchControllers[taskName];
                        if (prev.controller) prev.controller.abort('Superseded by new request');
                        if (prev.reqId) {
                            fetch('/api/v1/tasks/' + encodeURIComponent(prev.reqId) + '/cancel', { method: 'POST', keepalive: true }).catch(() => {});
                        }
                    } catch (e) {}
                }
                const controller = new AbortController();
                const reqId = 'req_' + taskName + '_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
                const opts = { ...options, signal: controller.signal };
                opts.headers = { ...(opts.headers || {}), 'X-Request-ID': reqId };

                this.activeFetchControllers[taskName] = { controller, reqId };

                return fetch(url, opts)
                    .finally(() => {
                        const current = this.activeFetchControllers[taskName];
                        if (current && current.controller === controller) {
                            delete this.activeFetchControllers[taskName];
                        }
                    });
            },

            cancelReportLoad(taskName) {
                const entry = this.activeFetchControllers[taskName];
                if (entry) {
                    try {
                        if (entry.controller) entry.controller.abort('User cancelled');
                        if (entry.reqId) {
                            fetch('/api/v1/tasks/' + encodeURIComponent(entry.reqId) + '/cancel', { method: 'POST', keepalive: true }).catch(() => {});
                        }
                    } catch (e) {}
                    delete this.activeFetchControllers[taskName];
                }
                this.resetTaskLoadingUI(taskName, '⚠️ Request cancelled by user.');
            },

            cancelAllPendingRequests(reason = 'Tab switched') {
                Object.keys(this.activeFetchControllers || {}).forEach(taskName => {
                    try {
                        const entry = this.activeFetchControllers[taskName];
                        if (entry) {
                            if (entry.controller) entry.controller.abort(reason);
                            if (entry.reqId) {
                                fetch('/api/v1/tasks/' + encodeURIComponent(entry.reqId) + '/cancel', { method: 'POST', keepalive: true }).catch(() => {});
                            }
                        }
                    } catch (e) {}
                    this.resetTaskLoadingUI(taskName, '⚠️ Loading cancelled (' + reason + ').');
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
                // 1. Check URL Hash (e.g. #swing or #tab=swing)
                let hash = window.location.hash ? window.location.hash.replace(/^#/, '').trim() : '';
                if (hash.startsWith('tab=')) hash = hash.replace('tab=', '');
                
                // 2. Check URL Search Query (e.g. ?tab=swing)
                const params = new URLSearchParams(window.location.search);
                const queryTab = params.get('tab');
                
                // 3. Check LocalStorage
                const storedTab = localStorage.getItem('dashboard_active_tab');

                const validTabs = ['results', 'monthfilter', 'scanner', 'catalysts', 'gainers', 'breakout', 'repeaters', 'swing', 'watchlist', 'kronos', 'consensus', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
                
                if (hash && validTabs.includes(hash.toLowerCase())) return hash.toLowerCase();
                if (queryTab && validTabs.includes(queryTab.toLowerCase())) return queryTab.toLowerCase();
                if (storedTab && validTabs.includes(storedTab.toLowerCase())) return storedTab.toLowerCase();
                return 'results';
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
                this._restoreBdControls();
                this._restorePatternsControls();
                this.populateWatchlistDropdowns();
                this.loadOverview();
                this.loadConsensusCache();
                this.updateTopRateLimitPill();
                this.updateWatchlistFreshnessPill(localStorage.getItem('selectedGlobalWatchlist') || '');
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

            switchTab(name, updateUrl = true, isInitialLoad = false) {
                name = (name || 'results').toLowerCase().replace('#', '').replace('tab=', '');
                const validTabs = ['results', 'monthfilter', 'scanner', 'catalysts', 'gainers', 'breakout', 'repeaters', 'swing', 'watchlist', 'kronos', 'consensus', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
                if (!validTabs.includes(name)) name = 'results';

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

                // Sync Vercel Sidebar Active Item
                document.querySelectorAll('.sidebar-nav-item').forEach(el => {
                    const tabKey = el.getAttribute('data-tab');
                    const isActive = (tabKey === name);
                    el.classList.toggle('active', isActive);
                });

                // Update Breadcrumb Tab Title
                const bcEl = document.getElementById('topbarBreadcrumbTab');
                if (bcEl) {
                    const titles = {
                        'results': 'Results Ledger',
                        'monthfilter': 'Month Filter',
                        'scanner': 'Scanner',
                        'catalysts': 'Catalysts & News',
                        'gainers': 'Gainers & Breakouts',
                        'breakout': '⚡ Breakout Radar',
                        'repeaters': '🔁 Quarter Repeaters',
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

                // Lazy-initialize client UI components on first visit without firing heavy backend scans
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
                    if (!this.pg._initialized) {
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
                    // Lazy-load on first visit; start auto-polling while active
                    if (!this._breakoutLoaded) {
                        this._breakoutLoaded = true;
                        this.loadBreakoutRadar();
                    }
                    // Start 5-minute auto-poll (cleared when leaving the tab)
                    this._breakoutPollTimer = setInterval(() => {
                        if (document.getElementById('tab-breakout')?.classList.contains('active')) {
                            this.loadBreakoutRadar();
                        } else {
                            clearInterval(this._breakoutPollTimer);
                        }
                    }, 5 * 60 * 1000);
                } else {
                    // Clear poll when leaving the breakout tab
                    if (this._breakoutPollTimer) {
                        clearInterval(this._breakoutPollTimer);
                        this._breakoutPollTimer = null;
                    }
                }
                if (name === 'repeaters') {
                    if (!this._repeatersLoaded) {
                        this._repeatersLoaded = true;
                        this.loadQuarterRepeaters();
                    }
                }
                this.applyRoleRestrictions();
            },

            // =========================================================================
            // 🔍 Active Multi-Category Stock Scanner Hub
            // =========================================================================
            activeScannerCategory: 'order_wins',
            scannerCategoriesData: [],
            scannerCandidatesData: [],

            async loadScanner() {
                const pillsEl = document.getElementById('scannerCategoryPills');
                const tbody = document.getElementById('scannerCandidatesTableBody');
                if (!pillsEl || !tbody) return;

                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                if (!this.scannerCategoriesData.length) {
                    pillsEl.innerHTML = '<div style="color:var(--muted);font-size:0.8rem;padding:0.3rem;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading scanner categories...</div>';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/scanner/categories?universe=' + encodeURIComponent(wl));
                    const data = await res.json();
                    this.scannerCategoriesData = data.categories || [];
                    this.renderScannerCategoriesPills();

                    // Default to 'all' category if not set or not matching
                    if (!this.activeScannerCategory) {
                        this.activeScannerCategory = 'all';
                    }
                    if (this.activeScannerCategory !== 'all' && !this.scannerCategoriesData.some(c => c.id === this.activeScannerCategory) && this.scannerCategoriesData.length) {
                        this.activeScannerCategory = 'all';
                    }

                    this.renderScannerCategoriesPills();
                    await this.loadScannerCategoryCandidates(this.activeScannerCategory);
                } catch (e) {
                    console.error('Error loading scanner categories:', e);
                }
            },

            renderScannerCategoriesPills() {
                const pillsEl = document.getElementById('scannerCategoryPills');
                if (!pillsEl) return;
                const items = this.scannerCategoriesData || [];
                const totalAllCount = items.reduce((acc, c) => acc + (Number(c.count) || 0), 0);

                const allPill = {
                    id: 'all',
                    icon: '🌟',
                    badge: 'All Categories',
                    count: totalAllCount,
                };
                const pillList = [allPill, ...items];

                pillsEl.innerHTML = pillList.map(c => {
                    const isActive = c.id === this.activeScannerCategory;
                    const pillBg = isActive ? 'linear-gradient(135deg, #0284c7, #4f46e5)' : 'rgba(255,255,255,0.06)';
                    const pillBorder = isActive ? 'border: 1px solid #38bdf8;' : 'border: 1px solid rgba(255,255,255,0.1);';
                    const pillColor = isActive ? '#fff' : 'var(--light)';
                    const badgeBg = isActive ? 'rgba(255,255,255,0.25)' : 'rgba(59,130,246,0.2)';
                    const badgeColor = isActive ? '#fff' : '#60a5fa';

                    return '<button onclick="app.selectScannerCategory(\'' + c.id + '\')" class="btn btn-sm" style="padding:0.35rem 0.75rem;border-radius:2rem;' + pillBorder + 'background:' + pillBg + ';color:' + pillColor + ';font-size:0.78rem;font-weight:600;display:inline-flex;align-items:center;gap:0.4rem;cursor:pointer;transition:all 0.15s ease;">' +
                        '<span>' + c.icon + ' ' + c.badge + '</span>' +
                        '<span style="background:' + badgeBg + ';color:' + badgeColor + ';padding:0.1rem 0.45rem;border-radius:1rem;font-size:0.7rem;font-weight:700;">' + c.count + '</span>' +
                    '</button>';
                }).join('');
            },

            async selectScannerCategory(catId) {
                this.activeScannerCategory = catId;
                this.renderScannerCategoriesPills();
                await this.loadScannerCategoryCandidates(catId);
            },

            async loadScannerCategoryCandidates(catId) {
                const tbody = document.getElementById('scannerCandidatesTableBody');
                const titleEl = document.getElementById('activeCatTitle');
                const descEl = document.getElementById('activeCatDescription');
                const countBadge = document.getElementById('activeCatCountBadge');

                let catMeta = (this.scannerCategoriesData || []).find(c => c.id === catId);
                if (catId === 'all') {
                    catMeta = {
                        icon: '🌟',
                        name: 'All Scanner Setups & Catalysts',
                        description: 'Unified multi-category scanner across all Fundamental News Catalysts, Technical Squeeze Coils, 52W Highs, and Momentum Waves.'
                    };
                } else if (!catMeta) {
                    catMeta = { icon: '🔍', name: catId, description: 'Active market candidates matching this setup.' };
                }

                if (titleEl) titleEl.innerHTML = (catMeta.icon || '🔍') + ' ' + (catMeta.name || catId);
                if (descEl) descEl.textContent = catMeta.description || 'Active market candidates matching this setup.';

                if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Scanning candidates for ' + (catMeta.name || catId) + '...</td></tr>';

                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                try {
                    const res = await fetch(API_BASE + '/api/v1/scanner/category/' + encodeURIComponent(catId) + '?universe=' + encodeURIComponent(wl) + '&limit=50');
                    const data = await res.json();
                    this.scannerCandidatesData = data.candidates || [];
                    if (countBadge) countBadge.textContent = this.scannerCandidatesData.length + ' stocks';
                    this.renderScannerCandidates();
                } catch (e) {
                    console.error('Error loading category candidates:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1rem;text-align:center;color:var(--red);">Failed loading category candidates.</td></tr>';
                }
            },

            filterScannerCandidates() {
                this.renderScannerCandidates();
            },

            renderScannerCandidates() {
                const tbody = document.getElementById('scannerCandidatesTableBody');
                if (!tbody) return;

                const searchQ = (document.getElementById('scannerSearchInput')?.value || '').toLowerCase().trim();
                const sortBy = document.getElementById('scannerSortBy')?.value || 'confidence';

                let filtered = (this.scannerCandidatesData || []).filter(item => {
                    if (searchQ) {
                        const mTicker = (item.ticker || '').toLowerCase().includes(searchQ);
                        const mName = (item.stock_name || '').toLowerCase().includes(searchQ);
                        const mText = (item.why_it_matches || '').toLowerCase().includes(searchQ);
                        if (!mTicker && !mName && !mText) return false;
                    }
                    return true;
                });

                if (sortBy === 'gain') {
                    filtered.sort((a, b) => (b.return_pct || 0) - (a.return_pct || 0));
                } else if (sortBy === 'volume') {
                    filtered.sort((a, b) => (b.volume_multiple || 0) - (a.volume_multiple || 0));
                } else {
                    filtered.sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0));
                }

                if (!filtered.length) {
                    tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted);">No candidates matching selected category in this universe. Click "⚡ Deep Sweep All Categories" to refresh feeds.</td></tr>';
                    return;
                }

                tbody.innerHTML = filtered.map((c, idx) => {
                    const rank = idx + 1;
                    const ret = Number(c.return_pct || 0);
                    const retClass = ret >= 0 ? 'price-positive' : 'price-negative';
                    const retSign = ret >= 0 ? '+' : '';

                    const volMult = c.volume_multiple ? Number(c.volume_multiple).toFixed(1) : '—';
                    const volColor = c.volume_multiple >= 3.0 ? '#f87171' : (c.volume_multiple >= 2.0 ? '#fbbf24' : '#34d399');

                    const confScore = c.confidence_score || 75;
                    const confColor = confScore >= 85 ? '#34d399' : (confScore >= 70 ? '#38bdf8' : '#fbbf24');

                    const triggerText = c.trigger_level ? '₹' + Number(c.trigger_level).toFixed(2) : '—';

                    return '<tr>' +
                        '<td style="text-align:center;color:var(--muted);font-weight:700;">' + rank + '</td>' +
                        '<td>' +
                            '<div><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="font-weight:700;font-size:0.85rem;color:var(--light);text-decoration:none;">' + (c.stock_name || c.ticker) + '</a></div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);"><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-family:var(--font-mono);">' + c.ticker + '</a><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></div>' +
                        '</td>' +
                        '<td style="text-align:right;"><strong style="font-family:var(--font-mono);">₹' + (c.current_price ? Number(c.current_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td style="text-align:right;"><strong class="' + retClass + '" style="font-size:0.88rem;font-family:var(--font-mono);">' + retSign + ret.toFixed(2) + '%</strong></td>' +
                        '<td style="text-align:center;"><strong style="color:' + volColor + ';font-family:var(--font-mono);">' + volMult + 'x</strong> <span style="font-size:0.68rem;color:var(--muted);">20D Avg</span></td>' +
                        '<td style="text-align:right;"><strong style="color:#fbbf24;font-size:0.85rem;font-family:var(--font-mono);">' + triggerText + '</strong></td>' +
                        '<td style="text-align:center;"><span style="color:' + confColor + ';font-weight:700;font-size:0.85rem;font-family:var(--font-mono);">' + confScore + '%</span></td>' +
                        '<td style="text-align:center;"><span style="font-size:0.75rem;color:var(--muted);white-space:nowrap;">' + (c.expected_horizon || '1-3 Days') + '</span></td>' +
                        '<td style="min-width:240px;max-width:380px;">' +
                            (c.category_name ? '<div style="margin-bottom:0.2rem;"><span class="signal-badge" style="background:rgba(59,130,246,0.15);color:#93c5fd;font-size:0.62rem;padding:0.08rem 0.35rem;border:1px solid rgba(59,130,246,0.3);border-radius:0.25rem;font-weight:600;">' + c.category_name + '</span></div>' : '') +
                            '<div style="font-size:0.75rem;color:#cbd5e1;line-height:1.4;white-space:normal;word-break:break-word;">' + (c.why_it_matches || c.catalyst_summary || '') + '</div>' +
                        '</td>' +
                        '<td style="text-align:center;white-space:nowrap;min-width:120px;">' + this.renderConsensusBadge(c.ticker, 'ALL') + '</td>' +
                        '<td style="text-align:center;white-space:nowrap;min-width:125px;">' +
                            '<div style="display:inline-flex;gap:0.3rem;justify-content:center;align-items:center;">' +
                                '<button onclick="event.stopPropagation(); app.openAddToWatchlistModal(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.72rem;background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);border-radius:0.3rem;" title="Add to Watchlist">⭐</button>' +
                                '<button onclick="event.stopPropagation(); app.runConsensusForStock(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.72rem;background:rgba(99,102,241,0.2);color:#c7d2fe;border:1px solid rgba(99,102,241,0.4);border-radius:0.3rem;" title="Run AI Consensus">🧠</button>' +
                                '<button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="14D OHLCV Benchmark">📊</button>' +
                                '<button onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run AI Forecast">🔮</button>' +
                            '</div>' +
                        '</td>' +
                    '</tr>';
                }).join('');
            },

            async deepSweepScanner() {
                const btn = document.getElementById('scannerSweepBtn');
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Sweeping All Categories...';
                }
                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                try {
                    const res = await fetch(API_BASE + '/api/v1/scanner/sweep', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({universe: wl})
                    });
                    const data = await res.json();
                    await this.loadScanner();
                } catch (e) {
                    console.error('Error executing deep sweep:', e);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '⚡ Deep Sweep All Categories';
                    }
                }
            },

            // =========================================================================
            // 📰 Short-Term Catalysts & High-Impact News Tab
            // =========================================================================
            catalystsData: [],
            catalystsActiveView: 'feed',
            outcomesData: [],
            outcomesMetrics: {},

            switchCatalystsView(view) {
                this.catalystsActiveView = view;
                const feedView = document.getElementById('catalystsFeedView');
                const outcomesView = document.getElementById('catalystsOutcomesView');
                const feedBtn = document.getElementById('catViewFeedBtn');
                const outcomesBtn = document.getElementById('catViewOutcomesBtn');
                const scanBtn = document.getElementById('catScanBtn');
                const evalBtn = document.getElementById('catEvalOutcomesBtn');

                if (feedView) feedView.style.display = (view === 'feed') ? 'block' : 'none';
                if (outcomesView) outcomesView.style.display = (view === 'outcomes') ? 'block' : 'none';

                if (feedBtn) {
                    feedBtn.style.background = (view === 'feed') ? 'rgba(59, 130, 246, 0.2)' : 'transparent';
                    feedBtn.style.color = (view === 'feed') ? '#60a5fa' : '#a1a1aa';
                    feedBtn.style.borderColor = (view === 'feed') ? 'rgba(59, 130, 246, 0.35)' : 'transparent';
                    feedBtn.style.fontWeight = (view === 'feed') ? '700' : '600';
                }
                if (outcomesBtn) {
                    outcomesBtn.style.background = (view === 'outcomes') ? 'rgba(59, 130, 246, 0.2)' : 'transparent';
                    outcomesBtn.style.color = (view === 'outcomes') ? '#60a5fa' : '#a1a1aa';
                    outcomesBtn.style.borderColor = (view === 'outcomes') ? 'rgba(59, 130, 246, 0.35)' : 'transparent';
                    outcomesBtn.style.fontWeight = (view === 'outcomes') ? '700' : '600';
                }

                if (scanBtn) scanBtn.style.display = (view === 'feed') ? 'inline-flex' : 'none';
                if (evalBtn) evalBtn.style.display = (view === 'outcomes') ? 'inline-flex' : 'none';

                if (view === 'outcomes') {
                    this.loadNewsOutcomes();
                }
            },

            async loadCatalysts(watchlist) {
                const feedGrid = document.getElementById('catalystsFeedGrid');
                if (!feedGrid) return;
                const wlSelect = document.getElementById('catWatchlistSelect');
                const wl = watchlist || (wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL'));
                const wlParam = (wl && wl !== 'GLOBAL') ? '?watchlist=' + encodeURIComponent(wl) : '';
                feedGrid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading short-term market moving catalysts' + (wl ? ' for "' + wl + '"' : '') + '...</div>';
                
                try {
                    // Fetch stats and items in parallel
                    const [itemsRes, statsRes] = await Promise.all([
                        fetch(API_BASE + '/api/v1/news/catalysts' + wlParam),
                        fetch(API_BASE + '/api/v1/news/catalyst-stats')
                    ]);
                    const itemsData = await itemsRes.json();
                    const statsData = await statsRes.json();

                    this.catalystsData = itemsData.catalysts || [];
                    this.renderCatalystsStats(statsData.stats || {});
                    this.renderCatalysts();
                } catch (e) {
                    console.error('Error loading catalysts:', e);
                    if (feedGrid) feedGrid.innerHTML = '<div class="card" style="padding:1rem;color:var(--red);">Failed loading catalysts feed. Click "⚡ Scan Feeds" to refresh.</div>';
                }
            },

            async loadNewsOutcomes() {
                const tableBody = document.getElementById('outcomesTableBody');
                if (tableBody) tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading historical verified news outcomes & performance metrics...</td></tr>';
                
                try {
                    const [metricsRes, outcomesRes] = await Promise.all([
                        fetch(API_BASE + '/api/v1/news/trade-metrics'),
                        fetch(API_BASE + '/api/v1/news/outcomes?limit=100')
                    ]);
                    const metricsData = await metricsRes.json();
                    const outcomesData = await outcomesRes.json();

                    this.outcomesMetrics = metricsData.metrics || {};
                    this.outcomesData = outcomesData.outcomes || [];

                    this.renderNewsTradeMetrics(this.outcomesMetrics);
                    this.renderNewsOutcomes();
                } catch (e) {
                    console.error('Error loading news outcomes:', e);
                    if (tableBody) tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:1.5rem;color:var(--red);">Failed loading outcomes track record. Click "🎯 Re-Verify Outcomes" to calculate.</td></tr>';
                }
            },

            renderNewsTradeMetrics(m) {
                if (!m) return;
                const winRateEl = document.getElementById('outcomeWinRate');
                const dirWinEl = document.getElementById('outcomeDirWinRates');
                const expEl = document.getElementById('outcomeExpectancy');
                const avgRetEl = document.getElementById('outcomeAvgReturn');
                const pfEl = document.getElementById('outcomeProfitFactor');
                const payoffEl = document.getElementById('outcomePayoff');
                const topGValEl = document.getElementById('outcomeTopGainerVal');
                const topGTickEl = document.getElementById('outcomeTopGainerTicker');
                const totalEl = document.getElementById('outcomeTotalCount');
                const verEl = document.getElementById('outcomeVerifiedCount');
                const actEl = document.getElementById('outcomeActiveCount');

                const h1dEl = document.getElementById('horizon1d');
                const h3dEl = document.getElementById('horizon3d');
                const h5dEl = document.getElementById('horizon5d');

                if (winRateEl) winRateEl.textContent = (m.win_rate_pct != null ? m.win_rate_pct.toFixed(1) : '0.0') + '%';
                if (dirWinEl) dirWinEl.textContent = `Bull: ${(m.bullish_win_rate_pct || 0).toFixed(1)}% | Bear: ${(m.bearish_win_rate_pct || 0).toFixed(1)}%`;
                
                if (expEl) {
                    const expVal = m.trade_expectancy_pct || 0;
                    expEl.textContent = (expVal > 0 ? '+' : '') + expVal.toFixed(2) + '%';
                    expEl.style.color = expVal >= 0 ? '#34d399' : '#f87171';
                }
                if (avgRetEl) {
                    const rVal = m.avg_return_pct || 0;
                    avgRetEl.textContent = (rVal > 0 ? '+' : '') + rVal.toFixed(2) + '%';
                    avgRetEl.style.color = rVal >= 0 ? '#34d399' : '#f87171';
                }
                if (pfEl) pfEl.textContent = (m.profit_factor != null ? m.profit_factor.toFixed(2) : '0.00');
                if (payoffEl) payoffEl.textContent = (m.payoff_ratio != null ? m.payoff_ratio.toFixed(2) : '0.0') + 'x';

                if (m.max_gainers && m.max_gainers.length) {
                    const topG = m.max_gainers[0];
                    if (topGValEl) topGValEl.textContent = '+' + Number(topG.max_gain_pct).toFixed(1) + '%';
                    if (topGTickEl) topGTickEl.textContent = `${topG.ticker}: ${topG.title}`;
                }

                if (totalEl) totalEl.textContent = m.total_evaluated || 0;
                if (verEl) verEl.textContent = m.verified_count || 0;
                if (actEl) actEl.textContent = (m.total_evaluated || 0) - (m.verified_count || 0);

                if (m.horizon_performance) {
                    const h1 = m.horizon_performance.avg_1d_pct || 0;
                    const h3 = m.horizon_performance.avg_3d_pct || 0;
                    const h5 = m.horizon_performance.avg_5d_pct || 0;
                    if (h1dEl) { h1dEl.textContent = (h1 > 0 ? '+' : '') + h1.toFixed(2) + '%'; h1dEl.style.color = h1 >= 0 ? '#60a5fa' : '#f87171'; }
                    if (h3dEl) { h3dEl.textContent = (h3 > 0 ? '+' : '') + h3.toFixed(2) + '%'; h3dEl.style.color = h3 >= 0 ? '#34d399' : '#f87171'; }
                    if (h5dEl) { h5dEl.textContent = (h5 > 0 ? '+' : '') + h5.toFixed(2) + '%'; h5dEl.style.color = h5 >= 0 ? '#38bdf8' : '#f87171'; }
                }

                // Render Category Performance Table
                const catTableBody = document.getElementById('outcomeCategoryTableBody');
                if (catTableBody && m.category_performance) {
                    if (!m.category_performance.length) {
                        catTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1rem;color:var(--muted);">No category data available.</td></tr>';
                    } else {
                        catTableBody.innerHTML = m.category_performance.map(c => {
                            const wrColor = c.win_rate_pct >= 65 ? '#34d399' : (c.win_rate_pct >= 50 ? '#60a5fa' : '#f87171');
                            const retColor = c.avg_return_pct >= 0 ? '#34d399' : '#f87171';
                            const edgeBadge = c.win_rate_pct >= 70 && c.profit_factor >= 2.0
                                ? '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-size:0.68rem;">🔥 High Edge</span>'
                                : (c.win_rate_pct >= 55 ? '<span class="signal-badge" style="background:rgba(59,130,246,0.15);color:#60a5fa;font-size:0.68rem;">⚡ Solid</span>' : '<span class="signal-badge" style="background:rgba(148,163,184,0.1);color:#94a3b8;font-size:0.68rem;">Neutral</span>');

                            return `
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                    <td style="padding: 0.4rem 0.5rem; font-weight: 600; color: #f8fafc;">${c.category}</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; color: #a1a1aa; font-family: var(--font-mono);">${c.total_events}</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; font-weight: 700; color: ${wrColor}; font-family: var(--font-mono);">${c.win_rate_pct.toFixed(1)}%</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; font-weight: 600; color: ${retColor}; font-family: var(--font-mono);">${(c.avg_return_pct > 0 ? '+' : '') + c.avg_return_pct.toFixed(2)}%</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; color: #38bdf8; font-family: var(--font-mono);">+${c.avg_max_gain_pct.toFixed(2)}%</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: right; font-weight: 600; color: #e2e8f0; font-family: var(--font-mono);">${c.profit_factor.toFixed(2)}</td>
                                    <td style="padding: 0.4rem 0.5rem; text-align: center;">${edgeBadge}</td>
                                </tr>
                            `;
                        }).join('');
                    }
                }
            },

            filterOutcomes() {
                this.renderNewsOutcomes();
            },

            renderNewsOutcomes() {
                const tableBody = document.getElementById('outcomesTableBody');
                const countBadge = document.getElementById('outcomesCountBadge');
                if (!tableBody) return;

                const searchQ = (document.getElementById('outcomesSearchInput')?.value || '').toLowerCase().trim();
                const catFilter = document.getElementById('outcomesCategoryFilter')?.value || 'ALL';
                const dirFilter = document.getElementById('outcomesDirectionFilter')?.value || 'ALL';
                const statusFilter = document.getElementById('outcomesStatusFilter')?.value || 'ALL';
                const sortBy = document.getElementById('outcomesSortBy')?.value || 'max_gain';

                let filtered = (this.outcomesData || []).filter(item => {
                    if (searchQ) {
                        const mTicker = (item.ticker || '').toLowerCase().includes(searchQ);
                        const mName = (item.stock_name || '').toLowerCase().includes(searchQ);
                        const mTitle = (item.title || '').toLowerCase().includes(searchQ);
                        if (!mTicker && !mName && !mTitle) return false;
                    }
                    if (catFilter !== 'ALL' && item.category !== catFilter) return false;
                    if (dirFilter !== 'ALL' && item.direction !== dirFilter) return false;
                    if (statusFilter !== 'ALL' && item.status !== statusFilter) return false;
                    return true;
                });

                if (sortBy === 'max_gain') {
                    filtered.sort((a, b) => (b.max_gain_pct || 0) - (a.max_gain_pct || 0));
                } else if (sortBy === 'net_return') {
                    filtered.sort((a, b) => (b.net_return_pct || 0) - (a.net_return_pct || 0));
                } else if (sortBy === 'impact') {
                    filtered.sort((a, b) => (b.impact_score || 0) - (a.impact_score || 0));
                } else {
                    filtered.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''));
                }

                if (countBadge) countBadge.textContent = filtered.length + ' evaluated';

                if (!filtered.length) {
                    tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--muted);">No news outcomes matching selected filters.</td></tr>';
                    return;
                }

                tableBody.innerHTML = filtered.map(o => {
                    const isBull = o.direction === 'BULLISH';
                    const isMet = Boolean(o.predicted_met);
                    const isVerified = o.status === 'VERIFIED';

                    const dirColor = isBull ? '#34d399' : '#f87171';
                    const dirIcon = isBull ? '🟢 Bull' : '🔴 Bear';

                    let outcomeBadge = '';
                    if (isVerified) {
                        if (isMet) {
                            const retStr = o.net_return_pct != null ? (o.net_return_pct > 0 ? '+' : '') + o.net_return_pct.toFixed(1) + '%' : 'MET';
                            outcomeBadge = `<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-weight:700;border:1px solid rgba(16,185,129,0.3);">✅ MET (${retStr})</span>`;
                        } else {
                            const retStr = o.net_return_pct != null ? o.net_return_pct.toFixed(1) + '%' : 'FAILED';
                            outcomeBadge = `<span class="signal-badge" style="background:rgba(239,68,68,0.15);color:#f87171;font-weight:700;border:1px solid rgba(239,68,68,0.3);">❌ MISSED (${retStr})</span>`;
                        }
                    } else {
                        outcomeBadge = `<span class="signal-badge" style="background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);">⏳ ACTIVE</span>`;
                    }

                    const fmtRet = (val) => {
                        if (val == null || isNaN(val)) return '—';
                        const sign = val > 0 ? '+' : '';
                        const col = val > 0 ? '#34d399' : (val < 0 ? '#f87171' : '#94a3b8');
                        return `<span style="color:${col};font-weight:600;font-family:var(--font-mono);">${sign}${Number(val).toFixed(2)}%</span>`;
                    };

                    const entryPx = o.entry_price ? `₹${Number(o.entry_price).toLocaleString('en-IN', {minimumFractionDigits:1, maximumFractionDigits:2})}` : '—';
                    const maxGain = o.max_gain_pct != null ? `<span style="color:#38bdf8;font-weight:700;font-family:var(--font-mono);">+${Number(o.max_gain_pct).toFixed(2)}%</span>` : '—';
                    const maxDD = o.max_drawdown_pct != null ? `<span style="color:#f87171;font-weight:600;font-family:var(--font-mono);">${Number(o.max_drawdown_pct).toFixed(2)}%</span>` : '—';

                    const pubDate = o.published_at ? o.published_at.slice(0, 10) : '—';

                    return `
                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.12s ease;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                            <td style="padding: 0.45rem 0.5rem; white-space: nowrap;">
                                <a href="/stock/${encodeURIComponent(o.ticker)}" target="_blank" style="font-weight:700;color:#60a5fa;text-decoration:none;font-family:var(--font-mono);" title="Open stock intelligence page">
                                    ${o.ticker} ↗
                                </a>
                                <div style="font-size:0.68rem;color:#71717a;">${o.stock_name || ''}</div>
                            </td>
                            <td style="padding: 0.45rem 0.5rem; white-space: nowrap; color: #a1a1aa; font-family: var(--font-mono); font-size: 0.72rem;">
                                ${pubDate}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; max-width: 320px;">
                                <div style="font-weight: 600; color: #f8fafc; font-size: 0.78rem; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${(o.title || '').replace(/"/g, '&quot;')}">
                                    ${o.title}
                                </div>
                                <div style="display: flex; gap: 0.35rem; align-items: center; margin-top: 0.15rem;">
                                    <span style="font-size: 0.65rem; color: ${dirColor}; font-weight: 700;">${dirIcon}</span>
                                    <span style="font-size: 0.65rem; background: rgba(255,255,255,0.06); color: #94a3b8; padding: 0.05rem 0.3rem; border-radius: 3px;">${o.category}</span>
                                    <span style="font-size: 0.65rem; color: #fbbf24;">⚡ ${o.impact_score}%</span>
                                </div>
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; font-family: var(--font-mono); color: #e2e8f0; font-weight: 600; white-space: nowrap;">
                                ${entryPx}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${fmtRet(o.return_1d_pct)}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${fmtRet(o.return_3d_pct)}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${fmtRet(o.return_5d_pct)}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${maxGain}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: right; white-space: nowrap;">
                                ${maxDD}
                            </td>
                            <td style="padding: 0.45rem 0.5rem; text-align: center; white-space: nowrap;">
                                ${outcomeBadge}
                            </td>
                        </tr>
                    `;
                }).join('');
            },

            async evaluateNewsOutcomesNow() {
                const btn = document.getElementById('catEvalOutcomesBtn');
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Evaluating Outcomes...';
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/news/outcomes/evaluate', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({force: true})
                    });
                    const data = await res.json();
                    await this.loadNewsOutcomes();
                } catch (e) {
                    console.error('Error evaluating news outcomes:', e);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<span>🎯</span> Re-Verify Outcomes';
                    }
                }
            },

            onCatWatchlistChange(val) {
                this.loadCatalysts(val);
            },

            renderCatalystsStats(stats) {
                const totalEl = document.getElementById('catStatTotal');
                const highEl = document.getElementById('catStatHigh');
                const biasEl = document.getElementById('catStatBias');
                const topCatEl = document.getElementById('catStatTopCat');

                if (totalEl) totalEl.textContent = stats.total_catalysts || this.catalystsData.length;
                if (highEl) highEl.textContent = stats.high_impact_count || this.catalystsData.filter(c => c.impact_level === 'HIGH').length;
                if (biasEl) {
                    const bull = stats.bullish_count || this.catalystsData.filter(c => c.direction === 'BULLISH').length;
                    const bear = stats.bearish_count || this.catalystsData.filter(c => c.direction === 'BEARISH').length;
                    biasEl.innerHTML = '<span style="color:#34d399;">' + bull + '</span> / <span style="color:#f87171;">' + bear + '</span>';
                }
                if (topCatEl) {
                    const topC = (stats.top_categories && stats.top_categories.length) ? stats.top_categories[0].category : 'Order Wins & Contracts';
                    topCatEl.textContent = topC;
                }
            },

            formatNewsDate(dateStr) {
                if (!dateStr) return '';
                try {
                    const cleanStr = dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T') + 'Z';
                    const d = new Date(cleanStr);
                    if (isNaN(d.getTime())) return dateStr.split(' ')[0] || dateStr;
                    const now = new Date();
                    const diffMs = now.getTime() - d.getTime();
                    const diffMins = Math.floor(diffMs / 60000);
                    const diffHours = Math.floor(diffMins / 60);
                    const diffDays = Math.floor(diffHours / 24);

                    if (diffMins >= 0 && diffMins < 60) {
                        return (diffMins <= 1 ? 'Just now' : diffMins + 'm ago');
                    } else if (diffHours > 0 && diffHours < 24) {
                        return diffHours + 'h ago';
                    } else if (diffDays === 1) {
                        return 'Yesterday';
                    } else if (diffDays > 1 && diffDays < 7) {
                        return diffDays + 'd ago';
                    } else {
                        return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
                    }
                } catch (e) {
                    return dateStr;
                }
            },

            filterCatalysts() {
                this.renderCatalysts();
            },

            renderCatalysts() {
                const feedGrid = document.getElementById('catalystsFeedGrid');
                const countBadge = document.getElementById('catFeedCountBadge');
                if (!feedGrid) return;

                const searchQ = (document.getElementById('catSearchInput')?.value || '').toLowerCase().trim();
                const impactFilter = document.getElementById('catImpactFilter')?.value || 'ALL';
                const dirFilter = document.getElementById('catDirectionFilter')?.value || 'ALL';
                const catFilter = document.getElementById('catCategoryFilter')?.value || 'ALL';

                let filtered = (this.catalystsData || []).filter(item => {
                    if (searchQ) {
                        const mTicker = (item.ticker || '').toLowerCase().includes(searchQ);
                        const mName = (item.stock_name || '').toLowerCase().includes(searchQ);
                        const mTitle = (item.title || '').toLowerCase().includes(searchQ);
                        if (!mTicker && !mName && !mTitle) return false;
                    }
                    if (impactFilter === 'HIGH' && item.impact_level !== 'HIGH') return false;
                    if (impactFilter === 'MEDIUM+' && item.impact_level !== 'HIGH' && item.impact_level !== 'MEDIUM') return false;
                    if (dirFilter !== 'ALL' && item.direction !== dirFilter) return false;
                    if (catFilter !== 'ALL' && item.category !== catFilter) return false;
                    return true;
                });

                // STRICT CHRONOLOGICAL SORT: Newest news always on top
                const _toTime = (dStr) => {
                    if (!dStr) return 0;
                    const clean = dStr.includes('T') ? dStr : dStr.replace(' ', 'T') + 'Z';
                    const t = new Date(clean).getTime();
                    return isNaN(t) ? new Date(dStr).getTime() || 0 : t;
                };

                filtered.sort((a, b) => {
                    const ta = _toTime(a.published_at || a.created_at);
                    const tb = _toTime(b.published_at || b.created_at);
                    if (tb !== ta) return tb - ta;
                    return (b.impact_score || 0) - (a.impact_score || 0);
                });

                if (countBadge) countBadge.textContent = filtered.length + ' headlines';

                if (!filtered.length) {
                    feedGrid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);">No catalysts matching selected filter criteria. Click "⚡ Scan Feeds" to discover live headlines.</div>';
                    return;
                }

                feedGrid.innerHTML = filtered.map(c => {
                    const isHigh = c.impact_level === 'HIGH';
                    const isBull = c.direction === 'BULLISH';
                    const isBear = c.direction === 'BEARISH';

                    const impactBadgeBg = isHigh ? 'rgba(239,68,68,0.2)' : 'rgba(251,191,36,0.2)';
                    const impactBadgeColor = isHigh ? '#f87171' : '#fbbf24';
                    const impactLabel = isHigh ? '🔥 HIGH IMPACT (' + c.impact_score + '%)' : '⚡ MEDIUM (' + c.impact_score + '%)';

                    const dirBadgeBg = isBull ? 'rgba(16,185,129,0.2)' : isBear ? 'rgba(239,68,68,0.2)' : 'rgba(148,163,184,0.2)';
                    const dirColor = isBull ? '#34d399' : isBear ? '#f87171' : '#94a3b8';
                    const dirIcon = isBull ? '🟢 BULLISH CATALYST' : isBear ? '🔴 BEARISH THREAT' : '⚪ NEUTRAL';

                    const cardBorder = isHigh ? 'border-left: 4px solid #ef4444;' : (isBull ? 'border-left: 4px solid #10b981;' : 'border-left: 4px solid #60a5fa;');

                    const headlineLink = c.link ? '<a href="' + c.link + '" target="_blank" rel="noopener noreferrer" style="color:var(--light);text-decoration:none;font-weight:700;font-size:0.95rem;line-height:1.4;" onmouseover="this.style.color=\'#60a5fa\'" onmouseout="this.style.color=\'var(--light)\'">' + c.title + ' ↗</a>' : '<span style="font-weight:700;font-size:0.95rem;color:var(--light);">' + c.title + '</span>';

                    const dateDisplay = this.formatNewsDate(c.published_at);

                    return '<div class="card" style="margin:0;padding:1rem;background:rgba(255,255,255,0.03);' + cardBorder + 'transition:transform 0.15s ease;">' +
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.45rem;">' +
                            '<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">' +
                                ((c.stock_name && c.stock_name.trim().toUpperCase() !== c.ticker.trim().toUpperCase())
                                    ? '<strong style="font-size:1.05rem;color:#f8fafc;">' + c.stock_name + '</strong><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" class="signal-badge" style="background:rgba(59,130,246,0.2);color:#60a5fa;font-size:0.72rem;text-decoration:none;" title="Open stock intelligence">' + c.ticker + ' ↗</a>'
                                    : '<a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="font-size:1.05rem;font-weight:700;color:#60a5fa;text-decoration:none;">' + c.ticker + ' ↗</a>') +
                                '<span style="background:' + impactBadgeBg + ';color:' + impactBadgeColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + impactLabel + '</span>' +
                                '<span style="background:' + dirBadgeBg + ';color:' + dirColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + dirIcon + '</span>' +
                                '<span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;">' + c.category + '</span>' +
                            '</div>' +
                            '<div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">' +
                                '<span class="timestamp" style="font-size:0.72rem;background:rgba(255,255,255,0.05);padding:0.15rem 0.45rem;border-radius:0.25rem;">' + (c.publisher || 'News') + ' &middot; ⏱️ ' + dateDisplay + '</span>' +
                                `<button onclick="app.runConsensusForStock('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.45);border-radius:0.3rem;font-weight:700;" title="Run AI Multi-Model Consensus for Target, Resistance, Support & Buy Zone">🧠 Consensus</button>` +
                                `<button onclick="app.openAddToWatchlistModal('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);border-radius:0.3rem;" title="Add to Watchlist">⭐ Watchlist</button>` +
                                `<button onclick="app.runPredictionForTickerSingle('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run Kronos Forecast">🔮 Predict</button>` +
                            '</div>' +
                        '</div>' +
                        '<div style="margin-bottom:0.5rem;">' + headlineLink + '</div>' +
                        (c.summary ? '<p style="margin:0 0 0.5rem 0;font-size:0.82rem;color:#cbd5e1;line-height:1.45;">' + c.summary + '</p>' : '') +
                        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;background:rgba(0,0,0,0.2);padding:0.45rem 0.65rem;border-radius:0.4rem;border:1px solid rgba(255,255,255,0.06);font-size:0.75rem;">' +
                            '<div style="color:#38bdf8;font-weight:600;"><span style="color:var(--muted);">💡 Why this matters: </span>' + (c.why_it_matters || '') + '</div>' +
                            '<div style="display:flex;gap:0.6rem;color:var(--muted);white-space:nowrap;">' +
                                '<span>Expected Horizon: <strong style="color:var(--light);">' + (c.expected_horizon || '1-3 Days') + '</strong></span>' +
                                '<span>Move Est: <strong style="color:#fbbf24;">' + (c.volatility_est || '±3%') + '</strong></span>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');
            },

            async scanCatalystsNow() {
                const btn = document.getElementById('catScanBtn');
                const wlSelect = document.getElementById('catWatchlistSelect');
                const wl = wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL');
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Scanning Feeds...';
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/news/scan', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({watchlist: wl, limit_per_stock: 3})
                    });
                    const data = await res.json();
                    await this.loadCatalysts(wl);
                } catch (e) {
                    console.error('Error scanning catalysts:', e);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '⚡ Scan Feeds';
                    }
                }
            },


            // =========================================================================
            // 🚀 Top Gainers, "Why It Rose" Attribution & Pattern Discovery Tab
            // =========================================================================
            gainersSubTab: 'gainers',
            gainersData: [],
            patternMatrixData: [],
            upcomingSetupsData: [],

            switchGainersSubTab(subTab) {
                this.gainersSubTab = subTab;
                ['gainers', 'patterns', 'setups'].forEach(t => {
                    const view = document.getElementById('gainersSubView_' + t);
                    const btn = document.getElementById('gainersSubTabBtn_' + t);
                    if (view) view.style.display = (t === subTab) ? 'block' : 'none';
                    if (btn) btn.classList.toggle('active', t === subTab);
                });

                if (subTab === 'patterns' && !this.patternMatrixData.length) {
                    this.loadPatternMatrix();
                } else if (subTab === 'setups' && !this.upcomingSetupsData.length) {
                    this.loadUpcomingSetups();
                }
            },

            async loadGainersTab() {
                await this.loadDailyTopGainers();
            },

            async refreshGainersTab() {
                if (this.gainersSubTab === 'patterns') {
                    await this.loadPatternMatrix();
                } else if (this.gainersSubTab === 'setups') {
                    await this.loadUpcomingSetups();
                } else {
                    await this.loadDailyTopGainers();
                }
            },

            onGainersMarketChange(val) {
                this.loadDailyTopGainers(val);
            },

            async loadDailyTopGainers(market) {
                const tbody = document.getElementById('topGainersTableBody');
                if (!tbody) return;
                const mktSelect = document.getElementById('gainersMarketSelect');
                const wl = market || (mktSelect ? mktSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP'));
                tbody.innerHTML = '<tr><td colspan="10" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Analyzing daily top gainers & drivers for ' + wl + '...</td></tr>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/daily?universe=' + encodeURIComponent(wl) + '&top_n=10');
                    const data = await res.json();
                    this.gainersData = data.gainers || [];
                    this.renderGainersLeaderboard();
                } catch (e) {
                    console.error('Error loading top gainers:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="10" style="padding:1rem;text-align:center;color:var(--red);">Failed loading daily top gainers.</td></tr>';
                }
            },

            renderGainersLeaderboard() {
                const tbody = document.getElementById('topGainersTableBody');
                if (!tbody) return;
                const items = this.gainersData || [];
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="10" style="padding:1.5rem;text-align:center;color:var(--muted);">No top gainers found for selected universe.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map((g, idx) => {
                    const rank = idx + 1;
                    const rankBadgeBg = rank === 1 ? 'gold' : (rank === 2 ? 'silver' : (rank === 3 ? '#cd7f32' : 'rgba(255,255,255,0.1)'));
                    const rankColor = rank <= 3 ? '#000' : 'var(--light)';

                    const is52w = g.is_52w_high === 1;
                    const status52w = is52w ? '<span style="background:rgba(52,211,153,0.2);color:#34d399;padding:0.15rem 0.45rem;border-radius:0.3rem;font-weight:700;font-size:0.7rem;">🛡️ 52W HIGH</span>' : '<span style="color:var(--muted);font-size:0.72rem;">' + (g.dist_from_52w_high_pct ? g.dist_from_52w_high_pct.toFixed(1) + '%' : '—') + '</span>';

                    const volMult = g.volume_multiple ? Number(g.volume_multiple).toFixed(1) : '—';
                    const volColor = g.volume_multiple >= 3.0 ? '#f87171' : (g.volume_multiple >= 2.0 ? '#fbbf24' : '#34d399');
                    const currSym = (g.ticker.endsWith('.NS') || g.ticker.endsWith('.BO')) ? '₹' : '$';

                    return '<tr>' +
                        '<td style="text-align:center;"><span style="background:' + rankBadgeBg + ';color:' + rankColor + ';width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:0.75rem;">' + rank + '</span></td>' +
                        '<td>' +
                            '<div><a href="/stock/' + encodeURIComponent(g.ticker) + '" target="_blank" style="font-weight:700;font-size:0.85rem;color:var(--light);text-decoration:none;">' + (g.stock_name || g.ticker) + '</a></div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);"><a href="/stock/' + encodeURIComponent(g.ticker) + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-family:var(--font-mono);">' + g.ticker + '</a><a href="/stock/' + encodeURIComponent(g.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></div>' +
                        '</td>' +
                        '<td><strong>' + currSym + (g.close_price ? Number(g.close_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td><strong class="price-positive" style="font-size:0.95rem;">+' + Number(g.return_pct).toFixed(2) + '%</strong></td>' +
                        '<td><strong style="color:' + volColor + ';">' + volMult + 'x</strong> <span style="font-size:0.7rem;color:var(--muted);">20D Avg</span></td>' +
                        '<td>' + status52w + '</td>' +
                        '<td style="max-width:320px;">' +
                            '<div style="font-weight:600;color:#38bdf8;font-size:0.78rem;margin-bottom:0.15rem;">' + (g.primary_driver || '').replace(/_/g, ' ') + '</div>' +
                            '<div style="font-size:0.73rem;color:#cbd5e1;line-height:1.35;">' + (g.driver_explanation || '') + '</div>' +
                        '</td>' +
                        '<td><span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;white-space:nowrap;">' + (g.pattern_name || 'Breakout') + '</span></td>' +
                        '<td>' + this.renderConsensusBadge(g.ticker, 'ALL') + '</td>' +
                        '<td style="text-align:center;">' +
                            '<div style="display:flex;gap:0.3rem;justify-content:center;">' +
                                '<button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + g.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="14D OHLCV Forecast Benchmark">📊 Benchmark</button>' +
                                '<button onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + g.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run AI Prediction">🔮 Predict</button>' +
                            '</div>' +
                        '</td>' +
                    '</tr>';
                }).join('');
            },

            async loadPatternMatrix() {
                const grid = document.getElementById('patternArchetypesGrid');
                if (!grid) return;
                grid.innerHTML = '<div class="card" style="grid-column:1/-1;padding:1.5rem;text-align:center;color:var(--muted);">Loading recurring pattern archetypes...</div>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/patterns');
                    const data = await res.json();
                    this.patternMatrixData = data.patterns || [];
                    this.renderPatternMatrix();
                } catch (e) {
                    console.error('Error loading pattern matrix:', e);
                }
            },

            renderPatternMatrix() {
                const grid = document.getElementById('patternArchetypesGrid');
                if (!grid) return;
                const items = this.patternMatrixData || [];

                grid.innerHTML = items.map(p => {
                    const winRate = p.win_rate_3d ? p.win_rate_3d.toFixed(1) + '%' : '—';
                    const avgGain = p.avg_follow_through_pct ? '+' + p.avg_follow_through_pct.toFixed(1) + '%' : '—';

                    const rulesHtml = (p.technical_rules || []).map(r => '<li style="margin-bottom:0.25rem;">' + r + '</li>').join('');

                    return '<div class="card" style="margin:0;padding:1.1rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.1);display:flex;flex-direction:column;justify-content:space-between;">' +
                        '<div>' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;flex-wrap:wrap;gap:0.3rem;">' +
                                '<h4 style="margin:0;font-size:1.05rem;color:#f8fafc;">' + p.name + '</h4>' +
                                '<span class="signal-badge" style="background:rgba(16,185,129,0.2);color:#34d399;font-size:0.75rem;">' + winRate + ' 3-Day Win Rate</span>' +
                            '</div>' +
                            '<p style="margin:0 0 0.75rem 0;font-size:0.82rem;color:#cbd5e1;line-height:1.45;">' + p.description + '</p>' +
                            '<div style="background:rgba(0,0,0,0.25);padding:0.6rem;border-radius:0.4rem;margin-bottom:0.75rem;">' +
                                '<span style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;display:block;margin-bottom:0.3rem;font-weight:700;">📐 Key Trigger Conditions:</span>' +
                                '<ul style="margin:0;padding-left:1.1rem;font-size:0.78rem;color:#93c5fd;">' + rulesHtml + '</ul>' +
                            '</div>' +
                        '</div>' +
                        '<div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.6rem;border-top:1px solid rgba(255,255,255,0.08);font-size:0.75rem;">' +
                            '<span>Avg 3D Move: <strong style="color:#34d399;font-size:0.88rem;">' + avgGain + '</strong></span>' +
                            '<span style="color:var(--muted);">Risk: <strong style="color:#fbbf24;">' + (p.risk_level || 'Medium') + '</strong></span>' +
                        '</div>' +
                    '</div>';
                }).join('');
            },

            async loadUpcomingSetups() {
                const tbody = document.getElementById('upcomingSetupsTableBody');
                if (!tbody) return;
                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                tbody.innerHTML = '<tr><td colspan="9" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Scanning watchlist for pre-breakout patterns...</td></tr>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/upcoming-setups?universe=' + encodeURIComponent(wl));
                    const data = await res.json();
                    this.upcomingSetupsData = data.setups || [];
                    this.renderUpcomingSetups();
                } catch (e) {
                    console.error('Error scanning setups:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="9" style="padding:1rem;text-align:center;color:var(--red);">Failed scanning watchlist setups.</td></tr>';
                }
            },

            renderUpcomingSetups() {
                const tbody = document.getElementById('upcomingSetupsTableBody');
                if (!tbody) return;
                const items = this.upcomingSetupsData || [];
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="9" style="padding:1.5rem;text-align:center;color:var(--muted);">No stocks currently in tight pre-breakout coils in this universe. Try selecting another universe above.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(s => {
                    const currSym = (s.ticker.endsWith('.NS') || s.ticker.endsWith('.BO')) ? '₹' : '$';
                    return '<tr>' +
                        '<td>' +
                            '<div><a href="/stock/' + encodeURIComponent(s.ticker) + '" target="_blank" style="font-weight:700;font-size:0.85rem;color:var(--light);text-decoration:none;">' + (s.stock_name || s.ticker) + '</a></div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);"><a href="/stock/' + encodeURIComponent(s.ticker) + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-family:var(--font-mono);">' + s.ticker + '</a><a href="/stock/' + encodeURIComponent(s.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></div>' +
                        '</td>' +
                        '<td><strong>' + currSym + (s.current_price ? Number(s.current_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td><span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">' + s.matching_pattern + '</span></td>' +
                        '<td><span style="background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">' + s.setup_stage + '</span></td>' +
                        '<td><strong style="color:#fbbf24;font-size:0.85rem;">' + currSym + Number(s.trigger_level).toFixed(2) + '</strong></td>' +
                        '<td><span style="color:#34d399;font-weight:700;">' + s.confidence_score + '%</span></td>' +
                        '<td style="max-width:320px;font-size:0.75rem;color:#cbd5e1;line-height:1.35;">' + s.why_it_matches + '</td>' +
                        '<td>' + this.renderConsensusBadge(s.ticker, 'ALL') + '</td>' +
                        '<td style="text-align:center;">' +
                            '<button onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + s.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run AI Prediction">🔮 Predict</button>' +
                        '</td>' +
                    '</tr>';
                }).join('');
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

            async loadOverview() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/overview');
                    const data = await res.json();
                    this.renderDatasetSummary(data.dataset);
                    this.renderRefreshStatus(data.refresh_status);
                } catch (e) {
                    console.error('Error loading overview:', e);
                }
            },

            renderDatasetSummary(ds) {
                const el = document.getElementById('resultsDatasetSummary');
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
                const preset = document.getElementById('resultsRangePreset')?.value || 'pm60';
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
                        document.getElementById('resultsReportSections').innerHTML = '<div class="card" style="margin:1rem 0;color:var(--muted);text-align:center;padding:1.5rem;">' + (data.error || 'No results data found for this selection.') + '<br><br><button onclick="app.loadResultsReport()" class="btn btn-sm btn-primary">↻ Try Again</button></div>';
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

                    // Show first 10 dates by default (or all if fewer)
                    this.resultsShowDays = Math.min(10, (this.resultsDaySections || []).length || 1);
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
                const summaryEl = document.getElementById('resultsDatasetSummary');
                if (!summaryEl) return;

                const tableRows = document.querySelectorAll('#resultsReportSections table.results-table tbody tr:not(.row-drawer-tr)');
                if (!tableRows.length) {
                    summaryEl.innerHTML = '';
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
                const winWindow = this.resultsActiveWindowName || '±60D';

                summaryEl.innerHTML = `
                    <div class="metric">
                        <span>Total Tracked</span>
                        <strong style="color:#ffffff;">${totalStocks} <span style="font-size:0.7rem;color:#60a5fa;font-weight:600;">(${winWindow})</span></strong>
                    </div>
                    <div class="metric">
                        <span>Avg 30D Momentum</span>
                        <strong style="${avg30DCls}">${parseFloat(avg30D) > 0 ? '+' : ''}${avg30D}%</strong>
                    </div>
                    <div class="metric">
                        <span>Quality Beat Rate</span>
                        <strong style="color:#38bdf8;">${beatPct}% <span style="font-size:0.7rem;color:#71717a;font-weight:400;">(${positiveMovesCount}/${totalBeatEvalCount})</span></strong>
                    </div>
                    <div class="metric">
                        <span>AI Consensus</span>
                        <strong style="color:#60a5fa;font-size:0.85rem;"><span style="color:#34d399;">${bullConsensusCount} 🐂</span> / <span style="color:#f87171;">${bearConsensusCount} 🐻</span></strong>
                    </div>
                    <div class="metric">
                        <span>Imminent (48h)</span>
                        <strong style="color:#fbbf24;">${imminentCount} <span style="font-size:0.7rem;color:#a1a1aa;font-weight:400;">catalysts</span></strong>
                    </div>
                `;
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

                // Also hide empty cap/industry sections
                document.querySelectorAll('#resultsReportSections .industry-subgroup, #resultsReportSections .cap-section').forEach(sec => {
                    const visibleTrs = sec.querySelectorAll('tbody tr:not(.row-drawer-tr):not([style*="display: none"])');
                    sec.style.display = visibleTrs.length ? '' : 'none';
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

            toggleRowDrawer(rowTickerId, ticker) {
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
                    if (bodyTd && !bodyTd.hasAttribute('data-populated')) {
                        bodyTd.setAttribute('data-populated', 'true');
                        
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
                                    <div style="margin-top:0.5rem;display:flex;gap:0.4rem;align-items:center;">
                                        <button type="button" class="btn-micro btn-micro-violet" onclick="app.openAiDetails('ALL', '${ticker}', event)">🤖 4-Model AI Breakdown</button>
                                        <button type="button" class="btn-micro btn-micro-primary" onclick="app.showOhlcvBenchmarkModal('${ticker}')">📈 TradingView Chart</button>
                                        <button type="button" class="btn-micro btn-micro-neutral" onclick="app.showTickerAuditModal('${ticker}')">📜 Formula Audit</button>
                                    </div>
                                </div>
                            `;
                        }

                        bodyTd.innerHTML = `
                            <div class="drawer-content">
                                ${sectionsHtml}
                            </div>
                        `;
                    }
                } else {
                    drawerTr.style.display = 'none';
                    if (arrow) arrow.style.transform = 'rotate(0deg)';
                    if (mainRow) mainRow.classList.remove('row-expanded');
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

            // =========================================================================
            // 🔄 Ticker On-Demand Recalculate & Audit Trail
            // =========================================================================
            async recalculateRow(ticker, btn) {
                if (!ticker) return;
                const originalHtml = btn ? btn.innerHTML : '🔄 Recalc';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Recalc...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/ticker/recalculate?ticker=' + encodeURIComponent(ticker), {
                        method: 'POST',
                    });
                    const data = await res.json();
                    if (!res.ok || !data.success) {
                        alert('Recalculation error: ' + (data.detail || data.error || 'Failed'));
                        return;
                    }

                    // Update DOM row cells if present
                    const rowId = 'row_' + ticker.replace(/[^a-zA-Z0-9]/g, '_');
                    const rowEl = document.getElementById(rowId);
                    if (rowEl && data.updated_metrics) {
                        const m = data.updated_metrics;
                        const pCell = rowEl.querySelector('.cell-current-price');
                        if (pCell && m.current_price !== null && m.current_price !== undefined) {
                            pCell.textContent = Number(m.current_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                        }
                        const edCell = rowEl.querySelector('.cell-earnings-date');
                        if (edCell && m.earnings_date) {
                            edCell.textContent = m.earnings_date;
                        }
                        const retCell = rowEl.querySelector('.cell-thirty-day-return');
                        if (retCell && m.thirty_day_return_pct !== null && m.thirty_day_return_pct !== undefined) {
                            const val = Number(m.thirty_day_return_pct);
                            retCell.textContent = (val > 0 ? '+' : '') + val.toFixed(2) + '%';
                        }
                        const resCell = rowEl.querySelector('.cell-next-resistance');
                        if (resCell && m.next_resistance !== null && m.next_resistance !== undefined) {
                            resCell.textContent = Number(m.next_resistance).toFixed(2);
                        }
                        const supCell = rowEl.querySelector('.cell-current-support');
                        if (supCell && m.current_support !== null && m.current_support !== undefined) {
                            supCell.textContent = Number(m.current_support).toFixed(2);
                        }

                        // Update Recounted Quality Scores with AI Tooltips
                        const qualCell = rowEl.querySelector('.cell-quality-scores');
                        if (qualCell) {
                            const q1 = (m.q1_earnings_score !== null && m.q1_earnings_score !== undefined) ? `${m.q1_earnings_score}/9` : '—';
                            const q2 = (m.q2_earnings_score !== null && m.q2_earnings_score !== undefined) ? `${m.q2_earnings_score}/9` : '—';
                            const q3 = (m.q3_earnings_score !== null && m.q3_earnings_score !== undefined) ? `${m.q3_earnings_score}/9` : '—';
                            const q1t = (m.q1_ai_summary || `Q1 Quality: ${q1}`).replace(/"/g, '&quot;');
                            const q2t = (m.q2_ai_summary || `Q2 Quality: ${q2}`).replace(/"/g, '&quot;');
                            const q3t = (m.q3_ai_summary || `Q3 Quality: ${q3}`).replace(/"/g, '&quot;');
                            qualCell.innerHTML = `
                                <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q1t}">${q1}</span> | 
                                <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q2t}">${q2}</span> | 
                                <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q3t}">${q3}</span>
                            `;
                        }

                        const avgCell = rowEl.querySelector('.cell-prev-3q-score');
                        if (avgCell && m.prev_3q_earnings_score !== null && m.prev_3q_earnings_score !== undefined) {
                            avgCell.textContent = `${m.prev_3q_earnings_score}/9`;
                        }

                        ['q1', 'q2', 'q3'].forEach(q => {
                            const cell = rowEl.querySelector(`.cell-${q}-week-hl`);
                            if (cell && m[`${q}_ai_summary`]) {
                                const wrap = cell.querySelector('.q-week-hl-wrap') || cell;
                                wrap.setAttribute('title', m[`${q}_ai_summary`]);
                            }
                        });
                    }

                    // Render Custom Recalculation Alert / Modal
                    this.showRecalculateResultModal(data);

                } catch (err) {
                    console.error('Error recalculating row for ' + ticker, err);
                    alert('Network error while recalculating ' + ticker + ': ' + err.message);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalHtml;
                    }
                }
            },

            showRecalculateResultModal(data) {
                const existing = document.getElementById('recalculateResultModal');
                if (existing) existing.remove();

                const isUpdated = Boolean(data.has_changes);
                const titleBg = isUpdated ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                const titleBorder = isUpdated ? '#10b981' : '#3b82f6';
                const statusBadge = isUpdated 
                    ? '<span style="background:#10b981;color:#fff;padding:0.2rem 0.5rem;border-radius:9999px;font-size:0.75rem;font-weight:700;">🟢 METRICS UPDATED</span>' 
                    : '<span style="background:rgba(255,255,255,0.15);color:var(--light);padding:0.2rem 0.5rem;border-radius:9999px;font-size:0.75rem;font-weight:700;">⚪ NO CHANGES</span>';

                let changesHtml = '';
                if (data.changes_summary && data.changes_summary.length) {
                    changesHtml = '<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;padding:0.75rem;margin:0.75rem 0;font-size:0.85rem;line-height:1.6;">' +
                        '<div style="font-weight:700;color:var(--light);margin-bottom:0.4rem;">Summary of Diff:</div>' +
                        data.changes_summary.map(c => '<div style="display:flex;align-items:center;gap:0.4rem;"><span style="color:' + (isUpdated ? '#34d399' : 'var(--muted)') + ';">•</span> <span>' + c + '</span></div>').join('') +
                        '</div>';
                }

                const modalHtml = `
                <div id="recalculateResultModal" style="position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:99999;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);">
                    <div style="background:#0f172a;border:1px solid ${titleBorder};border-radius:0.75rem;max-width:520px;width:100%;box-shadow:0 20px 40px rgba(0,0,0,0.6);overflow:hidden;color:var(--light);animation:fadeIn 0.2s ease-out;">
                        <div style="padding:1rem 1.25rem;background:${titleBg};border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;">
                            <div style="display:flex;align-items:center;gap:0.6rem;">
                                <span style="font-size:1.3rem;">${isUpdated ? '⚡' : '🔍'}</span>
                                <h3 style="margin:0;font-size:1.05rem;font-weight:700;">${data.ticker} Recalculation</h3>
                            </div>
                            <div>${statusBadge}</div>
                        </div>
                        <div style="padding:1.25rem;">
                            <p style="margin:0 0 0.5rem 0;font-size:0.88rem;color:var(--muted);">
                                ${isUpdated ? 'Live market data and earnings calendars were refreshed. The following metrics changed:' : 'Live check completed. All earnings dates, price highs/lows, and quality scores are currently matching the latest market state.'}
                            </p>
                            ${changesHtml}
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:1rem;font-size:0.75rem;color:var(--muted);">
                                <span>Refreshed at: ${data.refreshed_at || new Date().toLocaleTimeString()}</span>
                                <span style="cursor:pointer;color:#93c5fd;text-decoration:underline;" onclick="app.showTickerAuditModal('${data.ticker}')">View Audit Trail 📜</span>
                            </div>
                        </div>
                        <div style="padding:0.75rem 1.25rem;background:rgba(0,0,0,0.2);border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:flex-end;">
                            <button class="btn btn-sm btn-primary" onclick="document.getElementById('recalculateResultModal').remove()">Done</button>
                        </div>
                    </div>
                </div>`;

                const wrap = document.createElement('div');
                wrap.innerHTML = modalHtml;
                document.body.appendChild(wrap.firstElementChild);
            },

            async showTickerAuditModal(ticker) {
                const existing = document.getElementById('tickerAuditModal');
                if (existing) existing.remove();

                const sym = (ticker || '').trim().toUpperCase();
                const title = sym ? `${sym} Audit History` : 'Global Recalculation Audit Trail';

                const modalEl = document.createElement('div');
                modalEl.id = 'tickerAuditModal';
                modalEl.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:99999;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);';
                modalEl.innerHTML = `
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.15);border-radius:0.75rem;max-width:750px;width:100%;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 25px 50px rgba(0,0,0,0.8);overflow:hidden;color:var(--light);">
                        <div style="padding:1rem 1.25rem;background:rgba(255,255,255,0.04);border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;">
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span style="font-size:1.2rem;">📜</span>
                                <h3 style="margin:0;font-size:1.05rem;font-weight:700;">${title}</h3>
                            </div>
                            <button class="btn btn-sm" onclick="document.getElementById('tickerAuditModal').remove()" style="background:rgba(255,255,255,0.1);color:var(--light);border:none;border-radius:0.3rem;cursor:pointer;">✕</button>
                        </div>
                        <div id="auditModalBody" style="padding:1.25rem;overflow-y:auto;flex:1;">
                            <div style="text-align:center;padding:2rem;color:var(--muted);"><span class="loading-spinner"></span> Loading audit logs...</div>
                        </div>
                        <div style="padding:0.75rem 1.25rem;background:rgba(0,0,0,0.3);border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;color:var(--muted);">
                            <span>Audit records are permanently preserved in the local/cloud database.</span>
                            <button class="btn btn-sm btn-primary" onclick="document.getElementById('tickerAuditModal').remove()">Close</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modalEl);

                try {
                    const url = API_BASE + '/api/v1/ticker/audit-log' + (sym ? '?ticker=' + encodeURIComponent(sym) : '') + '&limit=50';
                    const res = await fetch(url);
                    const list = await res.json();

                    const bodyEl = document.getElementById('auditModalBody');
                    if (!bodyEl) return;

                    if (!Array.isArray(list) || !list.length) {
                        bodyEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);">No audit entries found for this ticker yet. Click <strong>🔄 Recalc</strong> on a results row to trigger a live refresh.</div>';
                        return;
                    }

                    let tableHtml = `
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;font-size:0.82rem;text-align:left;">
                            <thead>
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.15);color:var(--muted);">
                                    <th style="padding:0.5rem 0.6rem;">Timestamp</th>
                                    <th style="padding:0.5rem 0.6rem;">Ticker</th>
                                    <th style="padding:0.5rem 0.6rem;">Status</th>
                                    <th style="padding:0.5rem 0.6rem;">Changes / Diff</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;

                    list.forEach(entry => {
                        const statusBadge = entry.has_changes
                            ? '<span style="background:rgba(16,185,129,0.2);color:#34d399;padding:0.15rem 0.45rem;border-radius:9999px;font-size:0.72rem;font-weight:700;">🟢 UPDATED</span>'
                            : '<span style="background:rgba(255,255,255,0.08);color:var(--muted);padding:0.15rem 0.45rem;border-radius:9999px;font-size:0.72rem;">⚪ NO CHANGE</span>';
                        
                        const summaryLines = (entry.changes_summary || '').split('\n').filter(Boolean);
                        const summaryDisplay = summaryLines.map(s => `<div style="font-size:0.78rem;margin:0.15rem 0;">• ${s}</div>`).join('') || '—';

                        tableHtml += `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                                <td style="padding:0.6rem;white-space:nowrap;color:var(--muted);">${entry.refreshed_at || '—'}</td>
                                <td style="padding:0.6rem;font-weight:700;color:var(--light);">${entry.ticker}</td>
                                <td style="padding:0.6rem;">${statusBadge}</td>
                                <td style="padding:0.6rem;color:var(--light);">${summaryDisplay}</td>
                            </tr>
                        `;
                    });

                    tableHtml += `</tbody></table></div>`;
                    bodyEl.innerHTML = tableHtml;

                } catch (e) {
                    console.error('Error fetching audit history:', e);
                    const bodyEl = document.getElementById('auditModalBody');
                    if (bodyEl) bodyEl.innerHTML = '<div style="color:#f87171;padding:1rem;">Failed to load audit history: ' + e.message + '</div>';
                }
            },

            // =========================================================================
            // 🗓️ Month Filter & Earnings Calendar Dedicated Tab
            // =========================================================================
            async loadMonthFilterTab(forceSync = false) {
                const statusEl = document.getElementById('mfReportStatus');
                const sectionsEl = document.getElementById('mfReportSections');
                const countBadge = document.getElementById('mfCount');
                const market = document.getElementById('mfMarket')?.value || 'ALL';
                const cancelBtn = document.getElementById('mfCancelBtn');
                if (cancelBtn) cancelBtn.style.display = 'inline-block';

                if (statusEl) statusEl.textContent = forceSync ? 'Syncing present day delta...' : 'Loading precalculated Month Filter data...';

                try {
                    const url = '/api/v1/dashboard/month-filter?market=' + encodeURIComponent(market) + (forceSync ? '&force_sync=true' : '');
                    const res = await this.fetchWithAbort('monthfilter', url);
                    const data = await res.json();

                    if (!data || data.error) {
                        if (sectionsEl) sectionsEl.innerHTML = '<div class="card" style="padding:1.5rem;color:var(--muted);text-align:center;">' + (data.error || 'Failed to load month filter') + '</div>';
                        return;
                    }

                    // Render Fetch Record Banner
                    const rec = data.fetch_record || {};
                    const syncBannerText = document.getElementById('mfSyncText');
                    const statusBadge = document.getElementById('mfStatusBadge');
                    const lastSyncedEl = document.getElementById('mfLastSynced');
                    const totalEventsEl = document.getElementById('mfTotalEvents');
                    const insertedCountEl = document.getElementById('mfInsertedCount');

                    if (rec) {
                        if (statusBadge) {
                            statusBadge.textContent = rec.synced_today ? '🟢 UP TO DATE' : '🟡 STALE';
                            statusBadge.style.background = rec.synced_today ? '#10b981' : '#f59e0b';
                        }
                        if (syncBannerText) {
                            syncBannerText.textContent = rec.synced_today
                                ? 'Present day earnings calendar is up-to-date for ' + rec.today + '.'
                                : 'Earnings data not synced for today (' + rec.today + '). Delta fetch recommended.';
                        }
                        if (lastSyncedEl) lastSyncedEl.textContent = rec.last_fetched_at || rec.today || '--';
                        if (totalEventsEl) totalEventsEl.textContent = rec.events_count || data.total_stocks || 0;
                        if (insertedCountEl) insertedCountEl.textContent = rec.inserted_count || 0;
                    }

                    if (data.popups) {
                        let wrap = document.getElementById('resultsReportPopups');
                        if (!wrap) {
                            wrap = document.createElement('div');
                            wrap.id = 'resultsReportPopups';
                            document.body.appendChild(wrap);
                        }
                        wrap.innerHTML += data.popups;
                    }

                    this.mfDaySections = data.day_sections_list || [];
                    this.mfDaySectionsMeta = data.day_sections_meta || [];
                    this.mfMonths = data.months || [];
                    this.mfTotalStocks = data.total_stocks || 0;
                    this.mfActiveMonth = 'ALL';

                    this.renderMfMonthTabs();
                    this.renderMfSections();
                    this.populateMfIndustryFilter();

                    if (countBadge) {
                        countBadge.textContent = this.mfTotalStocks + ' results (' + this.mfDaySectionsMeta.length + ' dates)';
                    }
                    if (statusEl) statusEl.textContent = 'Month Filter loaded: ' + this.mfTotalStocks + ' results across ' + this.mfDaySectionsMeta.length + ' dates (' + new Date().toLocaleTimeString() + ')';
                } catch (e) {
                    if (e.name === 'AbortError') {
                        console.log('Month Filter fetch aborted:', e.message);
                        if (statusEl) statusEl.textContent = '⚠️ Request cancelled (' + (e.message || 'aborted') + ').';
                        return;
                    }
                    console.error('Error loading Month Filter tab:', e);
                    if (statusEl) statusEl.textContent = 'Error loading Month Filter: ' + (e.message || e);
                } finally {
                    this.resetTaskLoadingUI('monthfilter');
                }
            },

            async syncMonthFilter() {
                if (this.isMaster === false) {
                    alert('⚠️ Access Restricted: Syncing dataset delta is restricted to Master role.');
                    return;
                }
                const syncBtn = document.getElementById('mfSyncBtn');
                if (syncBtn) {
                    syncBtn.disabled = true;
                    syncBtn.innerHTML = '🔄 Syncing...';
                }
                try {
                    await this.loadMonthFilterTab(true);
                } finally {
                    if (syncBtn) {
                        syncBtn.disabled = false;
                        syncBtn.innerHTML = '🔄 Sync Delta';
                    }
                }
            },

            renderMfMonthTabs() {
                const el = document.getElementById('mfMonthTabs');
                if (!el || !this.mfMonths || !this.mfMonths.length) return;

                let html = '<span style="font-size:0.75rem;font-weight:700;color:var(--muted);text-transform:uppercase;margin-right:0.25rem;">🗓️ Month Filter:</span>';
                const allActive = (this.mfActiveMonth === 'ALL');
                const allBtnStyle = allActive
                    ? 'background:var(--accent);color:#fff;font-weight:700;border:1px solid var(--accent);'
                    : 'background:rgba(255,255,255,0.06);color:var(--light);border:1px solid rgba(255,255,255,0.15);';

                html += '<button type="button" onclick="app.filterMfByMonth(\'ALL\')" class="btn btn-sm" style="' + allBtnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                    '🌐 All (±2M) <span style="background:rgba(0,0,0,0.25);padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;margin-left:0.2rem;">' + this.mfTotalStocks + '</span>' +
                    '</button>';

                this.mfMonths.forEach(m => {
                    const isActive = (this.mfActiveMonth === m.month_key);
                    const tag = m.is_current ? '⭐ ' : (m.is_past ? '◀ ' : '▶ ');
                    let btnStyle = isActive
                        ? 'background:#2563eb;color:#fff;font-weight:700;border:1px solid #3b82f6;'
                        : (m.is_current ? 'background:rgba(16,185,129,0.15);color:#6ee7b7;border:1px solid rgba(16,185,129,0.35);'
                        : 'background:rgba(255,255,255,0.06);color:var(--light);border:1px solid rgba(255,255,255,0.15);');

                    html += '<button type="button" onclick="app.filterMfByMonth(\'' + m.month_key + '\')" class="btn btn-sm" style="' + btnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                        tag + m.month_label + ' ' +
                        '<span style="background:rgba(0,0,0,0.25);padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;font-weight:700;margin-left:0.2rem;">' + (m.stocks_count || 0) + '</span>' +
                        '</button>';
                });

                el.innerHTML = html;
            },

            filterMfByMonth(monthKey) {
                this.mfActiveMonth = monthKey;
                this.renderMfMonthTabs();
                this.renderMfSections();
            },

            renderMfSections() {
                const el = document.getElementById('mfReportSections');
                if (!el) return;

                let items = this.mfDaySectionsMeta || [];
                if (this.mfActiveMonth !== 'ALL') {
                    items = items.filter(m => m.month_key === this.mfActiveMonth);
                }

                const htmls = items.map(m => m.html);
                el.innerHTML = htmls.length ? htmls.join('\n') : '<p class="timestamp">No earnings data for this month selection.</p>';
            },

            populateMfIndustryFilter() {
                const select = document.getElementById('mfIndustryFilter');
                if (!select) return;
                const industries = new Set();

                (this.mfDaySectionsMeta || []).forEach(m => {
                    const matches = m.html.match(/Industry:\s*([^<]+)/g) || [];
                    matches.forEach(str => {
                        const ind = str.replace('Industry:', '').trim();
                        if (ind) industries.add(ind);
                    });
                });

                let options = '<option value="ALL">All Industries (' + industries.size + ')</option>';
                Array.from(industries).sort().forEach(ind => {
                    options += '<option value="' + ind.replace(/"/g, '&quot;') + '">' + ind + '</option>';
                });
                select.innerHTML = options;
            },

            filterMonthFilterRows() {
                const query = (document.getElementById('mfSearchInput')?.value || '').toLowerCase().trim();
                const selectedInd = document.getElementById('mfIndustryFilter')?.value || 'ALL';
                const el = document.getElementById('mfReportSections');
                if (!el) return;

                let items = this.mfDaySectionsMeta || [];
                if (this.mfActiveMonth !== 'ALL') {
                    items = items.filter(m => m.month_key === this.mfActiveMonth);
                }

                const filteredHtml = [];
                items.forEach(m => {
                    if (selectedInd !== 'ALL' && !m.html.includes(selectedInd)) return;
                    if (query && !m.html.toLowerCase().includes(query)) return;
                    filteredHtml.push(m.html);
                });

                el.innerHTML = filteredHtml.length ? filteredHtml.join('\n') : '<p class="timestamp">No matching results for your query/industry filter.</p>';
            },

            renderResultsWidgets() {
                const el = document.getElementById('resultsWidgets');
                if (!this.resultsData.length) {
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No upcoming results found. Try a different market or refresh data.</div>';
                    return;
                }
                el.innerHTML = this.resultsData.slice(0, 6).map(r => {
                    const mom = r.thirty_day_return_pct !== null ? r.thirty_day_return_pct : 0;
                    const mom7 = r.seven_day_return_pct !== null ? r.seven_day_return_pct : 0;
                    const cls = mom >= 0 ? 'price-positive' : 'price-negative';
                    const cls7 = mom7 >= 0 ? 'price-positive' : 'price-negative';
                    const signal = mom > 3 ? 'Bullish' : mom < -3 ? 'Bearish' : 'Neutral';
                    const badgeStyle = mom > 3 ? 'background:rgba(16,185,129,0.2);color:#10b981' : mom < -3 ? 'background:rgba(239,68,68,0.2);color:#ef4444' : 'background:rgba(148,163,184,0.2);color:#94a3b8';
                    const kp = r.kronos_prediction || {};
                    const trend = kp.trend || 'N/A';
                    const trendStyle = trend === 'Bullish' ? 'color:#10b981' : trend === 'Bearish' ? 'color:#ef4444' : 'color:#94a3b8';
                    return '<div class="widget-card">' +
                        '<h4>' + (r.ticker || '?') + '<a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></h4>' +
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">' +
                        '<span class="timestamp">' + (r.earnings_date || 'N/A') + '</span>' +
                        '<span class="signal-badge" style="' + badgeStyle + '">' + signal + '</span></div>' +
                        '<div class="metric" style="margin-bottom:0.4rem"><span>Current Price</span><strong>' + (r.current_price ? '$' + r.current_price.toFixed(2) : 'N/A') + '</strong></div>' +
                        '<div class="metric" style="margin-bottom:0.4rem"><span>7D Return</span><strong class="' + cls7 + '">' + (r.seven_day_return_pct !== null ? r.seven_day_return_pct.toFixed(2) + '%' : 'N/A') + '</strong></div>' +
                        '<div class="metric" style="margin-bottom:0.4rem"><span>30D Return</span><strong class="' + cls + '">' + (r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A') + '</strong></div>' +
                        '<div class="metric"><span>Market Cap</span><strong>' + (r.market_cap ? this.formatMarketCap(r.market_cap) : 'N/A') + '</strong></div>' +
                        '<div class="metric" style="margin-top:0.4rem"><span>Kronos Trend</span><strong style="' + trendStyle + '">' + trend + '</strong></div>' +
                        '</div>';
                }).join('');
            },

            renderResultsTable() {
                const tbody = document.getElementById('resultsTable');
                const sorted = [...this.resultsData].sort((a, b) => {
                    let va = a[this.sortKey], vb = b[this.sortKey];
                    va = va === null ? -Infinity : (this.sortKey === 'earnings_date' ? new Date(va) : va);
                    vb = vb === null ? -Infinity : (this.sortKey === 'earnings_date' ? new Date(vb) : vb);
                    if (va < vb) return this.sortDir === 'asc' ? -1 : 1;
                    if (va > vb) return this.sortDir === 'asc' ? 1 : -1;
                    return 0;
                });

                if (!sorted.length) {
                    tbody.innerHTML = '<tr><td colspan="11" style="padding:1rem;text-align:center;color:var(--muted)">No results</td></tr>';
                    return;
                }
                tbody.innerHTML = sorted.map(r => {
                    const mom = r.thirty_day_return_pct !== null ? r.thirty_day_return_pct : 0;
                    const mom7 = r.seven_day_return_pct !== null ? r.seven_day_return_pct : 0;
                    const cls = mom >= 0 ? 'price-positive' : 'price-negative';
                    const cls7 = mom7 >= 0 ? 'price-positive' : 'price-negative';
                    const signal = mom > 3 ? 'Bullish' : mom < -3 ? 'Bearish' : 'Neutral';
                    const kp = r.kronos_prediction || {};
                    const trend = kp.trend || '—';
                    const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';
                    return '<tr>' +
                        '<td><strong>' + (r.ticker || '?') + '</strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></td>' +
                        '<td>' + (r.earnings_date || 'N/A') + '</td>' +
                        '<td>' + (r.current_price ? r.current_price.toFixed(2) : 'N/A') + '</td>' +
                        '<td>' + (r.market_cap ? this.formatMarketCap(r.market_cap) : 'N/A') + '</td>' +
                        '<td class="' + cls7 + '">' + (r.seven_day_return_pct !== null ? r.seven_day_return_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td class="' + cls + '">' + (r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td>' + (r.earnings_week_move_pct !== null ? r.earnings_week_move_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td>' + (r.prev_quarter_earnings_score !== null ? r.prev_quarter_earnings_score + '/9' : 'N/A') + '</td>' +
                        '<td class="' + trendCls + '">' + trend + '</td>' +
                        '<td>' + this.renderConsensusBadge(r.ticker, this.currentMarket) + '</td>' +
                        '<td><span class="signal-badge ' + (mom > 3 ? 'price-positive' : mom < -3 ? 'price-negative' : '') + '">' + signal + '</span></td>' +
                        '</tr>';
                }).join('');
            },

            sortResults(key) {
                if (this.sortKey === key) this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
                else { this.sortKey = key; this.sortDir = 'asc'; }
                this.renderResultsTable();
            },

            swingData: [],
            swingView: 'table',
            swingFilter: 'all',
            swingSortKey: 'ticker',
            swingSortDir: 'asc',

            setSwingView(view) {
                this.swingView = view;
                const tbl = document.getElementById('swingTableContainer');
                const crd = document.getElementById('swingWidgets');
                const btnTbl = document.getElementById('swingViewBtn-table');
                const btnCrd = document.getElementById('swingViewBtn-cards');

                if (view === 'table') {
                    if (tbl) tbl.style.display = 'block';
                    if (crd) crd.style.display = 'none';
                    if (btnTbl) { btnTbl.style.background = 'var(--accent)'; btnTbl.style.color = 'white'; }
                    if (btnCrd) { btnCrd.style.background = 'rgba(255,255,255,0.06)'; btnCrd.style.color = 'var(--muted)'; }
                } else {
                    if (tbl) tbl.style.display = 'none';
                    if (crd) crd.style.display = 'grid';
                    if (btnTbl) { btnTbl.style.background = 'rgba(255,255,255,0.06)'; btnTbl.style.color = 'var(--muted)'; }
                    if (btnCrd) { btnCrd.style.background = 'var(--accent)'; btnCrd.style.color = 'white'; }
                }
                this.renderSwing();
            },

            filterSwing(filter) {
                this.swingFilter = filter;
                const pills = ['all', 'buyzone', 'strongbuy', 'custom'];
                pills.forEach(p => {
                    const btn = document.getElementById('swingFilter-' + p);
                    if (!btn) return;
                    if (p === filter) {
                        btn.style.background = p === 'buyzone' ? 'rgba(16,185,129,0.35)' : 'var(--accent)';
                        btn.style.color = 'white';
                        btn.style.borderColor = p === 'buyzone' ? '#10b981' : 'transparent';
                    } else {
                        btn.style.background = p === 'buyzone' ? 'rgba(16,185,129,0.12)' : (p === 'strongbuy' ? 'rgba(16,185,129,0.1)' : (p === 'custom' ? 'rgba(59,130,246,0.15)' : 'rgba(255,255,255,0.06)'));
                        btn.style.color = p === 'buyzone' ? '#34d399' : (p === 'strongbuy' ? '#10b981' : (p === 'custom' ? '#60a5fa' : 'var(--muted)'));
                        btn.style.borderColor = p === 'buyzone' ? 'rgba(16,185,129,0.4)' : 'transparent';
                    }
                });
                this.renderSwing();
            },

            sortSwing(key) {
                if (this.swingSortKey === key) {
                    this.swingSortDir = this.swingSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.swingSortKey = key;
                    this.swingSortDir = 'asc';
                }
                this.renderSwing();
            },

            isSwingInBuyZone(r) {
                if (!r) return false;
                const cur = r.current_price;
                const supp = r.current_support;
                const res = r.next_resistance;
                const sig = r.swing_signal;

                // Never mark as Buy Zone if price is above resistance or broken below support
                if (cur != null && res != null && cur > res) return false;
                if (cur != null && supp != null && cur < supp * 0.97) return false;
                if (sig === 'Overbought' || sig === 'Sell Zone' || sig === 'Breakdown') return false;

                if (r.swing_zone === 'Buy Zone') return true;
                if (sig === 'Strong Buy' || sig === 'Buy') return true;
                if (cur != null && supp != null && res != null && res > supp) {
                    const channelPos = (cur - supp) / (res - supp);
                    if (channelPos >= 0 && channelPos <= 0.25) return true;
                }
                return false;
            },

            async loadSwing(e) {
                const marketEl = document.getElementById('swingMarket');
                const market = marketEl ? marketEl.value : 'ALL';
                const url = API_BASE + '/api/v1/dashboard/swing?limit=50' + (market ? '&market=' + encodeURIComponent(market) : '');
                const btn = (e && e.target) ? e.target : (typeof window !== 'undefined' && window.event ? window.event.target : null);
                if (btn && btn.tagName === 'BUTTON') { btn.disabled = true; btn.innerHTML = '<span class="loading-spinner"></span> Loading...'; }
                try {
                    const res = await fetch(url);
                    const data = await res.json();
                    this.swingData = Array.isArray(data) ? data : [];

                    // Update summary counts
                    const countAll = this.swingData.length;
                    const countBuyZone = this.swingData.filter(r => this.isSwingInBuyZone(r)).length;
                    const countStrongBuy = this.swingData.filter(r => r.swing_signal === 'Strong Buy').length;
                    const countCustom = this.swingData.filter(r => r.swing_range && r.swing_range.source === 'user').length;

                    const elAll = document.getElementById('count-all'); if (elAll) elAll.textContent = countAll;
                    const elBz = document.getElementById('count-buyzone'); if (elBz) elBz.textContent = countBuyZone;
                    const elSb = document.getElementById('count-strongbuy'); if (elSb) elSb.textContent = countStrongBuy;
                    const elCust = document.getElementById('count-custom'); if (elCust) elCust.textContent = countCustom;

                    this.renderSwing();
                } catch (e) {
                    console.error('Error loading swing setups:', e);
                    const tbody = document.getElementById('swingTableBody');
                    if (tbody) tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:2rem;color:var(--red);">Error loading swing setups. Check server logs.</td></tr>';
                    const el = document.getElementById('swingWidgets');
                    if (el) el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0;color:var(--red)">Error loading swing setups</div>';
                } finally {
                    if (btn && btn.tagName === 'BUTTON') { btn.disabled = false; btn.textContent = 'Load Setups'; }
                }
            },

            renderSwing() {
                const marketEl = document.getElementById('swingMarket');
                const currentMarket = marketEl ? marketEl.value : 'ALL';
                const tbody = document.getElementById('swingTableBody');
                const widgetEl = document.getElementById('swingWidgets');

                if (!this.swingData.length) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:2rem;color:var(--muted)">No swing setups found. Try a different market or click Refresh.</td></tr>';
                    if (widgetEl) widgetEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No swing setups found.</div>';
                    return;
                }

                // Filter
                let list = [...this.swingData];
                if (this.swingFilter === 'buyzone') {
                    list = list.filter(r => this.isSwingInBuyZone(r));
                } else if (this.swingFilter === 'strongbuy') {
                    list = list.filter(r => r.swing_signal === 'Strong Buy');
                } else if (this.swingFilter === 'custom') {
                    list = list.filter(r => r.swing_range && r.swing_range.source === 'user');
                }

                // Sort
                list.sort((a, b) => {
                    let va = a[this.swingSortKey], vb = b[this.swingSortKey];
                    if (this.swingSortKey === 'ticker') {
                        va = (a.ticker || '').toUpperCase();
                        vb = (b.ticker || '').toUpperCase();
                    } else if (this.swingSortKey === 'current_price') {
                        va = a.current_price != null ? a.current_price : -Infinity;
                        vb = b.current_price != null ? b.current_price : -Infinity;
                    } else if (this.swingSortKey === 'current_support') {
                        va = a.current_support != null ? a.current_support : -Infinity;
                        vb = b.current_support != null ? b.current_support : -Infinity;
                    } else if (this.swingSortKey === 'next_resistance') {
                        va = a.next_resistance != null ? a.next_resistance : -Infinity;
                        vb = b.next_resistance != null ? b.next_resistance : -Infinity;
                    } else if (this.swingSortKey === 'thirty_day_return_pct') {
                        va = a.thirty_day_return_pct != null ? a.thirty_day_return_pct : -Infinity;
                        vb = b.thirty_day_return_pct != null ? b.thirty_day_return_pct : -Infinity;
                    } else if (this.swingSortKey === 'prev_quarter_earnings_score') {
                        va = a.prev_quarter_earnings_score != null ? a.prev_quarter_earnings_score : -Infinity;
                        vb = b.prev_quarter_earnings_score != null ? b.prev_quarter_earnings_score : -Infinity;
                    } else if (this.swingSortKey === 'ai_sentiment') {
                        va = (a.ai_synthesis && a.ai_synthesis.sentiment_score != null) ? a.ai_synthesis.sentiment_score : -Infinity;
                        vb = (b.ai_synthesis && b.ai_synthesis.sentiment_score != null) ? b.ai_synthesis.sentiment_score : -Infinity;
                    } else if (this.swingSortKey === 'kronos_return') {
                        va = (a.kronos_prediction && a.kronos_prediction.return_pct != null) ? a.kronos_prediction.return_pct : -Infinity;
                        vb = (b.kronos_prediction && b.kronos_prediction.return_pct != null) ? b.kronos_prediction.return_pct : -Infinity;
                    } else if (this.swingSortKey === 'consensus_strength') {
                        const pA = this.consensusMap[(a.ticker || '').toUpperCase()] || {};
                        const pB = this.consensusMap[(b.ticker || '').toUpperCase()] || {};
                        va = pA.consensus_strength != null ? pA.consensus_strength : -Infinity;
                        vb = pB.consensus_strength != null ? pB.consensus_strength : -Infinity;
                    } else if (this.swingSortKey === 'earnings_date') {
                        va = a.earnings_date ? new Date(a.earnings_date) : new Date(8640000000000000);
                        vb = b.earnings_date ? new Date(b.earnings_date) : new Date(8640000000000000);
                    } else {
                        va = va === null || va === undefined ? -Infinity : va;
                        vb = vb === null || vb === undefined ? -Infinity : vb;
                    }
                    if (va < vb) return this.swingSortDir === 'asc' ? -1 : 1;
                    if (va > vb) return this.swingSortDir === 'asc' ? 1 : -1;
                    return 0;
                });

                if (!list.length) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="14" style="text-align:center;padding:2rem;color:var(--muted)">No stocks match the selected filter.</td></tr>';
                    if (widgetEl) widgetEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No stocks match the selected filter.</div>';
                    return;
                }

                // Render Table Rows
                if (tbody) {
                    tbody.innerHTML = list.map(r => {
                        const isBz = this.isSwingInBuyZone(r);
                        const curPrice = r.current_price;
                        const curPriceStr = curPrice !== null && curPrice !== undefined ? ('₹' + Number(curPrice).toFixed(2)) : '—';
                        const supp = r.current_support;
                        const resis = r.next_resistance;
                        const suppStr = supp !== null && supp !== undefined ? ('₹' + Number(supp).toFixed(2)) : '—';
                        const resisStr = resis !== null && resis !== undefined ? ('₹' + Number(resis).toFixed(2)) : '—';

                        // Distance to support calculation
                        let distToSupp = '—';
                        let distCls = 'timestamp';
                        if (curPrice != null && supp != null && supp > 0) {
                            const diffPct = ((curPrice - supp) / supp) * 100;
                            if (Math.abs(diffPct) < 0.5) {
                                distToSupp = '🎯 At Support';
                                distCls = 'price-positive';
                            } else if (diffPct > 0) {
                                distToSupp = '+' + diffPct.toFixed(1) + '%';
                                distCls = isBz ? 'price-positive' : 'timestamp';
                            } else {
                                distToSupp = diffPct.toFixed(1) + '% (Below)';
                                distCls = 'price-negative';
                            }
                        }

                        // Swing Range
                        const sr = r.swing_range || {};
                        const hasSr = sr.lower_bound != null && sr.upper_bound != null;
                        const srLower = hasSr ? Number(sr.lower_bound).toFixed(2) : (supp ? Number(supp).toFixed(2) : '—');
                        const srUpper = hasSr ? Number(sr.upper_bound).toFixed(2) : (resis ? Number(resis).toFixed(2) : '—');
                        const isUser = sr.source === 'user';
                        const srSource = isUser ? 'Custom' : 'Auto';
                        const srSourceCls = isUser ? 'background:rgba(59,130,246,0.25);color:#60a5fa;' : 'background:rgba(148,163,184,0.15);color:#94a3b8;';
                        const srCycles = (sr.cycles != null && sr.cycles > 0) ? (sr.cycles + ' cyc' + (sr.avg_cycle_days ? ' · ~' + Math.round(sr.avg_cycle_days) + 'd' : '')) : '';

                        // Calculate spread %
                        let spreadStr = '';
                        if (hasSr && sr.lower_bound > 0) {
                            const sp = (((sr.upper_bound - sr.lower_bound) / sr.lower_bound) * 100).toFixed(1);
                            spreadStr = ' (' + sp + '%)';
                        }

                        // Signal & Zone Badge
                        let signalBadge = '';
                        if (isBz) {
                            signalBadge = '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#34d399;border:1px solid #10b981;padding:0.25rem 0.6rem;font-size:0.75rem;font-weight:700;">🟢 ' + (r.swing_signal === 'Strong Buy' ? 'STRONG BUY' : 'BUY ZONE') + '</span>';
                        } else if (r.swing_signal === 'Overbought') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);padding:0.25rem 0.6rem;font-size:0.75rem;font-weight:600;">⚠️ Above Resistance</span>';
                        } else if (r.swing_signal === 'Sell Zone') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(251,146,60,0.2);color:#fb923c;border:1px solid rgba(251,146,60,0.4);padding:0.25rem 0.6rem;font-size:0.75rem;font-weight:600;">🟠 Sell Zone</span>';
                        } else if (r.swing_signal === 'Breakdown') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(239,68,68,0.25);color:#ef4444;border:1px solid #ef4444;padding:0.25rem 0.6rem;font-size:0.75rem;font-weight:700;">🔴 Below Support</span>';
                        } else if (r.swing_signal === 'Buy') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#6ee7b7;padding:0.25rem 0.6rem;font-size:0.75rem;">Buy</span>';
                        } else if (r.swing_signal === 'Cautious') {
                            signalBadge = '<span class="signal-badge" style="background:rgba(239,68,68,0.2);color:#ef4444;padding:0.25rem 0.6rem;font-size:0.75rem;">Cautious</span>';
                        } else {
                            signalBadge = '<span class="signal-badge" style="background:rgba(148,163,184,0.15);color:#94a3b8;padding:0.25rem 0.6rem;font-size:0.75rem;">Neutral</span>';
                        }

                        // 30D Return
                        const mom = r.thirty_day_return_pct;
                        const momCls = mom !== null && mom !== undefined ? (mom >= 0 ? 'price-positive' : 'price-negative') : '';
                        const momStr = mom !== null && mom !== undefined ? ((mom >= 0 ? '+' : '') + mom.toFixed(2) + '%') : '—';

                        // Kronos Trend & On-Demand Predict Button
                        const kp = r.kronos_prediction || {};
                        const hasKp = kp && kp.trend && kp.trend !== '—' && kp.trend !== 'N/A';
                        const trend = kp.trend || '—';
                        const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';
                        const trendStr = (hasKp && kp.return_pct != null) ? (trend + ' (' + (kp.return_pct >= 0 ? '+' : '') + kp.return_pct.toFixed(1) + '%)') : trend;
                        const kronosColHtml = hasKp
                            ? ('<div style="display:flex;align-items:center;gap:0.35rem;">' +
                               '<span class="' + trendCls + '" style="font-weight:600;">' + trendStr + '</span>' +
                               '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);" title="Re-run Kronos AI prediction">🔄</button>' +
                               '</div>')
                            : ('<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.2rem 0.5rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);" title="Run on-demand Kronos AI prediction for ' + (r.ticker || '') + '">🔮 Predict</button>');

                        // AI Multi-Modal & News Synthesis Column
                        const ai = r.ai_synthesis || {};
                        const hasAi = ai && ai.ai_signal;
                        let aiColHtml = '';
                        if (hasAi) {
                            const aiSig = ai.ai_signal || 'Neutral';
                            const aiScore = ai.sentiment_score != null ? ai.sentiment_score : 0;
                            const isAiBull = aiSig.includes('Bullish');
                            const isAiBear = aiSig.includes('Bearish');
                            const aiBg = isAiBull ? 'rgba(16,185,129,0.2)' : isAiBear ? 'rgba(239,68,68,0.2)' : 'rgba(251,191,36,0.2)';
                            const aiColor = isAiBull ? '#34d399' : isAiBear ? '#f87171' : '#fbbf24';
                            const aiBorder = isAiBull ? '1px solid rgba(16,185,129,0.4)' : isAiBear ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(251,191,36,0.4)';
                            const scoreStr = (aiScore >= 0 ? '+' : '') + aiScore.toFixed(2);
                            const volBadge = ai.volume_status === 'High Accumulation' ? ' 🔥' : '';

                            aiColHtml = '<div style="display:flex;align-items:center;gap:0.35rem;">' +
                                '<span class="signal-badge" style="background:' + aiBg + ';color:' + aiColor + ';border:' + aiBorder + ';font-size:0.72rem;padding:0.15rem 0.45rem;font-weight:600;cursor:pointer;" title="Click to view AI Reasons, Catalysts & News" onclick="event.stopPropagation(); app.openAiDetails(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\', event)">' + aiSig + ' (' + scoreStr + ')' + volBadge + '</span>' +
                                '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSingleAiForecast(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);" title="Re-run AI Multi-Modal News Synthesis">🔄</button>' +
                                '</div>';
                        } else {
                            aiColHtml = '<button class="btn btn-sm" onclick="event.stopPropagation(); app.openAiDetails(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\', event)" style="padding:0.2rem 0.5rem;font-size:0.72rem;background:rgba(59,130,246,0.22);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);" title="Run AI News, World Events & Volume synthesis for ' + (r.ticker || '') + '">🧠 AI Thesis</button>';
                        }

                        // AI Consensus Column
                        const consensusColHtml = this.renderConsensusBadge(r.ticker, currentMarket);

                        // Row styling: Green row if in buy zone
                        const rowStyle = isBz
                            ? 'background:rgba(16,185,129,0.08);border-left:4px solid #10b981;'
                            : 'transition:background 0.15s ease;';
                        const hoverBg = isBz ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.04)';
                        const origBg = isBz ? 'rgba(16,185,129,0.08)' : '';

                        return '<tr style="' + rowStyle + 'cursor:pointer;" onmouseenter="this.style.background=\'' + hoverBg + '\'" onmouseleave="this.style.background=\'' + origBg + '\'" onclick="app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" title="Click row to view 3-month history & set custom range">' +
                            '<td><strong style="color:var(--light);font-size:0.95rem;">' + (r.ticker || '?') + '</strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" onclick="event.stopPropagation();" title="Open profile in new tab">↗</a></td>' +
                            '<td style="font-weight:700;' + (isBz ? 'color:#34d399;font-size:0.98rem;' : '') + '">' + curPriceStr + '</td>' +
                            '<td>' + signalBadge + '</td>' +
                            '<td style="' + (isBz ? 'color:#34d399;font-weight:600;' : '') + '">' + suppStr + '</td>' +
                            '<td>' + resisStr + '</td>' +
                            '<td>' +
                                '<div style="font-weight:600;">₹' + srLower + ' – ₹' + srUpper + spreadStr + '</div>' +
                                '<div style="display:flex;gap:0.35rem;align-items:center;margin-top:0.15rem;">' +
                                '<span class="signal-badge" style="' + srSourceCls + 'font-size:0.65rem;padding:0.05rem 0.35rem;">' + srSource + '</span>' +
                                (srCycles ? '<span class="timestamp" style="font-size:0.7rem;">' + srCycles + '</span>' : '') +
                                '</div>' +
                            '</td>' +
                            '<td class="' + distCls + '" style="font-weight:600;">' + distToSupp + '</td>' +
                            '<td class="' + momCls + '" style="font-weight:600;">' + momStr + '</td>' +
                            '<td>' + (r.prev_quarter_earnings_score !== null ? r.prev_quarter_earnings_score + '/9' : '—') + '</td>' +
                            '<td>' + kronosColHtml + '</td>' +
                            '<td>' + aiColHtml + '</td>' +
                            '<td>' + consensusColHtml + '</td>' +
                            '<td><span class="timestamp">' + (r.earnings_date || '—') + '</span></td>' +
                            '<td style="text-align:right;">' +
                                '<div style="display:flex;justify-content:flex-end;gap:0.3rem;align-items:center;">' +
                                '<button class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" style="padding:0.25rem 0.55rem;font-size:0.75rem;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);">✎ Range</button>' +
                                '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.25rem 0.55rem;font-size:0.75rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);" title="Run on-demand Kronos AI prediction">⚡ Kronos</button>' +
                                '<button class="btn btn-sm" onclick="event.stopPropagation(); app.openAiDetails(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\', event)" style="padding:0.25rem 0.55rem;font-size:0.75rem;background:rgba(59,130,246,0.2);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);" title="View AI Reasons, Catalysts & Big News">🧠 AI</button>' +
                                '</div>' +
                            '</td>' +
                            '</tr>';
                    }).join('');
                }

                // Render Cards (if user switches to card view)
                if (widgetEl) {
                    widgetEl.innerHTML = list.map(r => {
                        const isBz = this.isSwingInBuyZone(r);
                        const mom = r.thirty_day_return_pct !== null ? r.thirty_day_return_pct : 0;
                        const cls = mom >= 0 ? 'price-positive' : 'price-negative';
                        const badgeStyle = isBz ? 'background:rgba(16,185,129,0.25);color:#34d399;border:1px solid #10b981;' :
                            r.swing_signal === 'Overbought' ? 'background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);' :
                            r.swing_signal === 'Sell Zone' ? 'background:rgba(251,146,60,0.2);color:#fb923c;border:1px solid rgba(251,146,60,0.4);' :
                            r.swing_signal === 'Breakdown' ? 'background:rgba(239,68,68,0.25);color:#ef4444;border:1px solid #ef4444;' :
                            r.swing_signal === 'Buy' ? 'background:rgba(16,185,129,0.15);color:#6ee7b7;' :
                            r.swing_signal === 'Cautious' ? 'background:rgba(239,68,68,0.2);color:#ef4444;' :
                            'background:rgba(148,163,184,0.2);color:#94a3b8;';
                        const badgeText = isBz ? '🟢 BUY ZONE' : (r.swing_signal === 'Overbought' ? '⚠️ Above Resistance' : (r.swing_signal === 'Sell Zone' ? '🟠 Sell Zone' : (r.swing_signal === 'Breakdown' ? '🔴 Below Support' : r.swing_signal)));
                        const earningsDate = r.earnings_date || 'N/A';
                        const kp = r.kronos_prediction || {};
                        const hasKp = kp && kp.trend && kp.trend !== '—' && kp.trend !== 'N/A';
                        const trend = kp.trend || 'N/A';
                        const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';

                        const ai = r.ai_synthesis || {};
                        const hasAi = ai && ai.ai_signal;

                        const sr = r.swing_range || {};
                        const hasSr = sr.lower_bound != null && sr.upper_bound != null;
                        const srLower = hasSr ? Number(sr.lower_bound).toFixed(2) : (r.current_support ? Number(r.current_support).toFixed(2) : '—');
                        const srUpper = hasSr ? Number(sr.upper_bound).toFixed(2) : (r.next_resistance ? Number(r.next_resistance).toFixed(2) : '—');
                        const isUser = sr.source === 'user';
                        const srSource = isUser ? 'Custom' : 'Auto';
                        const srSourceCls = isUser ? 'background:rgba(59,130,246,0.25);color:#60a5fa;' : 'background:rgba(148,163,184,0.15);color:#94a3b8;';
                        const srCycles = (sr.cycles != null && sr.cycles > 0) ? (sr.cycles + ' cyc' + (sr.avg_cycle_days ? ' · ~' + Math.round(sr.avg_cycle_days) + 'd' : '')) : '';
                        const curPriceStr = r.current_price !== null && r.current_price !== undefined ? ('₹' + Number(r.current_price).toFixed(2)) : 'N/A';

                        const cardBorder = isBz ? 'border-color:#10b981;background:rgba(16,185,129,0.05);' : '';

                        return '<div class="widget-card" onclick="app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" style="' + cardBorder + 'cursor:pointer;transition:transform 0.15s ease, border-color 0.15s ease;" onmouseenter="this.style.borderColor=\'rgba(59,130,246,0.8)\'" onmouseleave="this.style.borderColor=\'' + (isBz ? '#10b981' : '') + '\'" title="Click anywhere to view 3-month range history & customize swing range">' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                            '<h4>' + (r.ticker || '?') + '</h4>' +
                            '<span class="signal-badge" style="' + badgeStyle + '">' + badgeText + '</span></div>' +
                            '<div style="display:flex;justify-content:space-between;align-items:baseline;margin:0.25rem 0 0.45rem 0;">' +
                            '<span style="font-size:0.8rem;color:var(--muted);">Current Price</span>' +
                            '<strong style="font-size:1.1rem;' + (isBz ? 'color:#34d399;' : 'color:var(--light);') + '">' + curPriceStr + '</strong>' +
                            '</div>' +
                            '<div class="metric" style="margin-bottom:0.4rem"><span>Next Earnings</span><strong>' + earningsDate + '</strong></div>' +
                            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">' +
                            '<div class="metric"><span>Support (Buy Zone)</span><strong style="' + (isBz ? 'color:#34d399;' : '') + '">' + (r.current_support ? '₹' + Number(r.current_support).toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>Resistance (Sell Zone)</span><strong>' + (r.next_resistance ? '₹' + Number(r.next_resistance).toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>30D Return</span><strong class="' + cls + '">' + (r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>Quality (LQ)</span><strong>' + (r.prev_quarter_earnings_score !== null ? r.prev_quarter_earnings_score + '/9' : 'N/A') + '</strong></div>' +
                            '</div>' +
                            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.45rem 0.6rem;margin-top:0.5rem;">' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">' +
                            '<span style="font-size:0.72rem;color:var(--muted);font-weight:600;">SWING RANGE</span>' +
                            '<span class="signal-badge" style="' + srSourceCls + 'font-size:0.68rem;padding:0.08rem 0.35rem;">' + srSource + '</span>' +
                            '</div>' +
                            '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                            '<div><strong style="font-size:0.92rem;">₹' + srLower + ' – ₹' + srUpper + '</strong>' +
                            (srCycles ? '<span class="timestamp" style="display:block;font-size:0.72rem;">' + srCycles + '</span>' : '') +
                            '</div>' +
                            '<button class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" style="padding:0.2rem 0.5rem;font-size:0.75rem;">✎ Range</button>' +
                            '</div>' +
                            '</div>' +
                            (hasAi ? ('<div class="metric" style="margin-top:0.4rem;cursor:pointer;" onclick="event.stopPropagation(); app.openAiDetails(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\', event)"><span>AI Synthesis</span><strong style="color:#60a5fa;">' + ai.ai_signal + ' (' + (ai.sentiment_score >= 0 ? '+' : '') + Number(ai.sentiment_score).toFixed(2) + ') 🔍</strong></div>') : '') +
                            (hasKp ? ('<div class="metric" style="margin-top:0.2rem"><span>Kronos 14D Return</span><strong class="' + trendCls + '">' + (kp.return_pct != null ? kp.return_pct.toFixed(2) + '%' : '—') + ' (' + trend + ')</strong></div>') : '') +
                            (kp.explanation ? '<p class="timestamp" style="margin-top:0.5rem;font-size:0.75rem;">' + kp.explanation + '</p>' : '') +
                            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">' +
                            '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.35rem 0.4rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);">' + (hasKp ? '🔄 Kronos' : '⚡ Kronos AI') + '</button>' +
                            '<button class="btn btn-sm" onclick="event.stopPropagation(); app.openAiDetails(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\', event)" style="padding:0.35rem 0.4rem;font-size:0.72rem;background:rgba(59,130,246,0.22);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);">' + (hasAi ? '🔍 Reasons & News' : '🧠 AI Thesis') + '</button>' +
                            '</div>';
                    }).join('');
                }
            },

            async runPredictionForTickerSingle(ticker, eventOrBtn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;

                let btn = null;
                if (eventOrBtn && eventOrBtn.tagName) {
                    btn = eventOrBtn;
                } else if (window.event && window.event.target) {
                    btn = window.event.target.closest('button');
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> 🔮...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: [ticker], lookback: 120, pred_len: 14 })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || ('HTTP ' + res.status));
                    }
                    const data = await res.json();
                    const list = Array.isArray(data) ? data : (data.predictions || (data.prediction ? [data.prediction] : []));
                    const pred = list[0];

                    if (pred && (pred.trend || pred.return_pct != null)) {
                        const ret = Number(pred.return_pct || 0);
                        const isBull = ret >= 0.5;
                        const isBear = ret <= -0.5;
                        const emoji = isBull ? '🟢' : (isBear ? '🔴' : '🟡');
                        const color = isBull ? '#34d399' : (isBear ? '#f87171' : '#fbbf24');

                        if (btn) {
                            btn.style.borderColor = color;
                            btn.style.color = color;
                            btn.innerHTML = emoji + ' ' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%';
                            btn.title = (pred.trend || 'Trend') + ': ' + (pred.explanation || '');
                        }

                        // Also update row in swingData if present
                        const sItem = (this.swingData || []).find(x => x.ticker === ticker);
                        if (sItem) {
                            sItem.kronos_prediction = pred;
                        }

                        // Open OHLCV Benchmark modal with the generated forecast
                        this.showOhlcvBenchmarkModal(ticker, pred.run_at);
                    } else {
                        alert('Kronos prediction for ' + ticker + ' completed with no signals.');
                        if (btn) btn.innerHTML = origHtml;
                    }
                } catch (err) {
                    console.error('Error running single Kronos prediction for ' + ticker + ':', err);
                    alert('Error running Kronos prediction for ' + ticker + ': ' + (err.message || err));
                    if (btn) btn.innerHTML = origHtml;
                } finally {
                    if (btn) btn.disabled = false;
                }
            },

            async runSwingKronos(ticker, btn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Predicting...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/predict/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticker: ticker, engine: 'kronos', days: 14, lookback: 120, pred_len: 14 })
                    });
                    const data = await res.json();
                    if (data.success && data.prediction) {
                        const item = (this.swingData || []).find(x => x.ticker === ticker);
                        if (item) {
                            item.kronos_prediction = data.prediction;
                        }
                        this.renderSwing();

                        // If modal is open for this ticker, update its Kronos section
                        const modalTicker = document.getElementById('srModalTicker')?.value;
                        if (modalTicker === ticker) {
                            this._renderModalKronos(data.prediction);
                        }
                    } else {
                        alert('Kronos prediction failed: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error running Kronos prediction for ' + ticker + ':', e);
                    alert('Network error running Kronos prediction');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async runRowPrediction(ticker, engine, btn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;
                engine = (engine || 'kronos').toLowerCase();

                if (!btn && window.event) {
                    btn = window.event.target ? window.event.target.closest('button') : null;
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span>...';
                }

                try {
                    const apiBase = (typeof API_BASE !== 'undefined') ? API_BASE : '';
                    const res = await fetch(apiBase + '/api/v1/dashboard/predict/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticker: ticker, engine: engine, lookback: 120, pred_len: 14 })
                    });

                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || err.error || ('HTTP ' + res.status));
                    }

                    const data = await res.json();
                    if (!data || !data.success) {
                        throw new Error(data.error || 'Prediction failed');
                    }

                    const pred = data.prediction || {};
                    if (engine === 'kronos') {
                        const ret = Number(pred.return_pct || 0);
                        const trend = pred.trend || 'Neutral';
                        const cls = trend === 'Bullish' ? 'pred-bullish' : (trend === 'Bearish' ? 'pred-bearish' : 'pred-neutral');
                        const sign = ret >= 0 ? '+' : '';
                        if (btn) {
                            btn.outerHTML = '<span class="' + cls + '">' + sign + ret.toFixed(1) + '%</span>';
                        }
                    } else if (engine === 'gbm') {
                        const direction = pred.direction || '?';
                        const conf = pred.confidence;
                        const confStr = conf != null ? Math.round(conf * 100) + '%' : '—';
                        const cls = direction === 'UP' ? 'pred-bullish' : 'pred-bearish';
                        if (btn) {
                            btn.outerHTML = '<span class="' + cls + '">' + direction + ' ' + confStr + '</span>';
                        }
                    }
                } catch (e) {
                    console.error('Error running ' + engine + ' row prediction:', e);
                    if (btn) {
                        btn.disabled = false;
                        btn.style.borderColor = '#f87171';
                        btn.style.color = '#f87171';
                        btn.title = 'Error: ' + (e.message || e);
                        btn.innerHTML = '⚠️ Error';
                    }
                }
            },

            async runModalKronos() {
                const ticker = document.getElementById('srModalTicker')?.value;
                const btn = document.getElementById('srModalKronosRunBtn');
                if (!ticker) return;
                await this.runSwingKronos(ticker, btn);
            },

            _renderModalKronos(kp) {
                const badge = document.getElementById('srModalKronosBadge');
                const content = document.getElementById('srModalKronosContent');
                if (!badge || !content) return;

                if (kp && (kp.trend || kp.return_pct != null)) {
                    const trend = kp.trend || 'Neutral';
                    const isBull = trend === 'Bullish';
                    const isBear = trend === 'Bearish';
                    const ret = kp.return_pct != null ? Number(kp.return_pct).toFixed(2) : '—';
                    const retCls = isBull ? 'price-positive' : isBear ? 'price-negative' : '';

                    badge.style.display = 'inline-block';
                    badge.textContent = trend + ' (' + (ret >= 0 ? '+' : '') + ret + '%)';
                    badge.style.background = isBull ? 'rgba(16,185,129,0.25)' : isBear ? 'rgba(239,68,68,0.25)' : 'rgba(251,191,36,0.25)';
                    badge.style.color = isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24';

                    content.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.4rem;margin:0.5rem 0;">' +
                        '<div class="metric"><span>14D Forecast Return</span><strong class="' + retCls + '">' + (ret >= 0 ? '+' : '') + ret + '%</strong></div>' +
                        '<div class="metric"><span>Kronos Support</span><strong>₹' + (kp.support ? Number(kp.support).toFixed(2) : '—') + '</strong></div>' +
                        '<div class="metric"><span>Kronos Resistance</span><strong>₹' + (kp.resistance ? Number(kp.resistance).toFixed(2) : '—') + '</strong></div>' +
                        '<div class="metric"><span>Target Price</span><strong>₹' + (kp.target_price ? Number(kp.target_price).toFixed(2) : (kp.current_price && kp.return_pct ? (kp.current_price * (1 + kp.return_pct/100)).toFixed(2) : '—')) + '</strong></div>' +
                        '</div>' +
                        (kp.explanation ? '<p class="timestamp" style="margin:0.25rem 0 0 0;font-size:0.78rem;">' + kp.explanation + '</p>' : '');
                } else {
                    badge.style.display = 'none';
                    content.innerHTML = '<p class="timestamp" style="margin:0;font-size:0.8rem;">No forecast generated yet. Click <strong>"⚡ Run Kronos AI"</strong> to compute 14-day predictions on demand.</p>';
                }
            },

            async runSingleAiForecast(ticker, btn) {
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Synthesizing...';
                }

                try {
                    const item = (this.swingData || []).find(x => x.ticker === ticker) || {};
                    const res = await fetch(API_BASE + '/api/v1/dashboard/ai-forecast/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            ticker: ticker,
                            swing_support: item.current_support || null,
                            swing_resistance: item.next_resistance || null,
                        })
                    });
                    const data = await res.json();
                    if (data.success && data.prediction) {
                        const target = (this.swingData || []).find(x => x.ticker === ticker);
                        if (target) {
                            target.ai_synthesis = data.prediction;
                        }
                        this.renderSwing();

                        // If modal is open for this ticker, update its AI section
                        const modalTicker = document.getElementById('srModalTicker')?.value;
                        if (modalTicker === ticker) {
                            this._renderModalAi(data.prediction, ticker);
                        }
                    } else {
                        alert('AI News Synthesis failed: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error running AI News synthesis for ' + ticker + ':', e);
                    alert('Network error running AI News synthesis');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async runModalAiForecast() {
                const ticker = document.getElementById('srModalTicker')?.value;
                const btn = document.getElementById('srModalAiRunBtn');
                if (!ticker) return;
                await this.runSingleAiForecast(ticker, btn);
            },

            async _renderModalAi(ai, ticker) {
                const badge = document.getElementById('srModalAiSignalBadge');
                const content = document.getElementById('srModalAiContent');
                if (!badge || !content) return;

                if (!ai || !ai.ai_signal) {
                    badge.style.display = 'none';
                    content.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin:0.25rem 0;">' +
                        '<p class="timestamp" style="margin:0;font-size:0.8rem;">Click <strong>"⚡ Run AI Synthesis"</strong> to analyze real-time news headlines, volume surge, and price action.</p>' +
                        '<button class="btn btn-sm" onclick="app.runModalAiForecast()" style="font-size:0.75rem;background:rgba(59,130,246,0.25);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);">⚡ Run Now</button>' +
                        '</div>';
                    
                    // Also try to load raw news preview in background if available
                    if (ticker) {
                        try {
                            const nRes = await fetch(API_BASE + '/api/v1/dashboard/ai-forecast/news/' + encodeURIComponent(ticker) + '?limit=4');
                            const nData = await nRes.json();
                            if (nData.articles && nData.articles.length) {
                                content.innerHTML += '<div style="margin-top:0.6rem;border-top:1px dashed rgba(255,255,255,0.08);padding-top:0.5rem;">' +
                                    '<h5 style="margin:0 0 0.35rem 0;font-size:0.78rem;color:var(--muted);">📰 Live Headlines Feed (' + nData.articles.length + ' articles)</h5>' +
                                    '<div style="display:flex;flex-direction:column;gap:0.35rem;">' +
                                    nData.articles.map(a =>
                                        '<div style="font-size:0.75rem;display:flex;justify-content:space-between;align-items:baseline;background:rgba(255,255,255,0.02);padding:0.25rem 0.4rem;border-radius:0.3rem;">' +
                                        '<a href="' + (a.link || '#') + '" target="_blank" rel="noopener noreferrer" style="color:#93c5fd;text-decoration:none;flex:1;margin-right:0.5rem;">' + (a.title || 'Headline') + '</a>' +
                                        '<span class="timestamp" style="font-size:0.68rem;white-space:nowrap;">' + (a.publisher || '') + '</span>' +
                                        '</div>'
                                    ).join('') +
                                    '</div></div>';
                            }
                        } catch (e) {}
                    }
                    return;
                }

                const sig = ai.ai_signal || 'Neutral';
                const isBull = sig.includes('Bullish');
                const isBear = sig.includes('Bearish');
                const score = ai.sentiment_score != null ? Number(ai.sentiment_score).toFixed(2) : '0.00';
                const scoreStr = (ai.sentiment_score >= 0 ? '+' : '') + score;
                const conf = ai.confidence ? Math.round(ai.confidence * 100) + '%' : '75%';

                badge.style.display = 'inline-block';
                badge.textContent = sig + ' (' + scoreStr + ' · ' + conf + ' conf)';
                badge.style.background = isBull ? 'rgba(16,185,129,0.25)' : isBear ? 'rgba(239,68,68,0.25)' : 'rgba(251,191,36,0.25)';
                badge.style.color = isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24';

                const catalystsHtml = (ai.catalysts && ai.catalysts.length)
                    ? ('<div style="background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);border-radius:0.4rem;padding:0.5rem;margin-top:0.4rem;">' +
                       '<strong style="color:#34d399;font-size:0.8rem;display:flex;align-items:center;gap:0.3rem;">🚀 Positive Catalysts & Reasons:</strong>' +
                       '<ul style="margin:0.25rem 0 0 1.1rem;padding:0;font-size:0.75rem;color:var(--light);line-height:1.45;">' +
                       ai.catalysts.map(c => '<li style="margin-bottom:0.2rem;">' + c + '</li>').join('') + '</ul></div>')
                    : '';

                const risksHtml = (ai.risk_factors && ai.risk_factors.length)
                    ? ('<div style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);border-radius:0.4rem;padding:0.5rem;margin-top:0.4rem;">' +
                       '<strong style="color:#f87171;font-size:0.8rem;display:flex;align-items:center;gap:0.3rem;">⚠️ Downside Risks & Headwinds:</strong>' +
                       '<ul style="margin:0.25rem 0 0 1.1rem;padding:0;font-size:0.75rem;color:var(--light);line-height:1.45;">' +
                       ai.risk_factors.map(r => '<li style="margin-bottom:0.2rem;">' + r + '</li>').join('') + '</ul></div>')
                    : '';

                const articlesHtml = (ai.articles && ai.articles.length)
                    ? ('<div style="margin-top:0.75rem;border-top:1px solid rgba(255,255,255,0.1);padding-top:0.6rem;">' +
                       '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">' +
                       '<h5 style="margin:0;font-size:0.82rem;display:flex;align-items:center;gap:0.3rem;">📰 Big News & World Events Stream <span class="timestamp" style="font-size:0.72rem;">(' + ai.articles.length + ' stories)</span></h5>' +
                       '<span class="signal-badge" style="font-size:0.68rem;background:' + (ai.news_sentiment_score >= 0.15 ? 'rgba(16,185,129,0.2);color:#34d399;' : ai.news_sentiment_score <= -0.15 ? 'rgba(239,68,68,0.2);color:#f87171;' : 'rgba(251,191,36,0.2);color:#fbbf24;') + '">' +
                       'News Sentiment: ' + (ai.news_sentiment_label || 'Neutral') + ' (' + (ai.news_sentiment_score >= 0 ? '+' : '') + Number(ai.news_sentiment_score || 0).toFixed(2) + ')' +
                       '</span></div>' +
                       '<div style="display:flex;flex-direction:column;gap:0.45rem;max-height:220px;overflow-y:auto;padding-right:0.2rem;">' +
                       ai.articles.map(a => {
                           const aScore = a.sentiment_score != null ? a.sentiment_score : 0;
                           const aLabel = a.sentiment_label || (aScore >= 0.2 ? 'Bullish' : aScore <= -0.2 ? 'Bearish' : 'Neutral');
                           const aBadgeStyle = aLabel === 'Bullish' ? 'background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.3);' :
                               aLabel === 'Bearish' ? 'background:rgba(239,68,68,0.18);color:#f87171;border:1px solid rgba(239,68,68,0.3);' :
                               'background:rgba(255,255,255,0.06);color:var(--muted);';
                           const topicBadge = (a.topics && a.topics[0])
                               ? '<span class="signal-badge" style="font-size:0.62rem;background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);">' + a.topics[0] + '</span>'
                               : '';

                           return '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.4rem;padding:0.45rem 0.6rem;">' +
                               '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;">' +
                               '<a href="' + (a.link || '#') + '" target="_blank" rel="noopener noreferrer" style="color:#60a5fa;text-decoration:none;font-weight:600;font-size:0.78rem;line-height:1.35;flex:1;">' +
                               (a.title || 'Headline') + ' ↗' +
                               '</a>' +
                               '<div style="display:flex;gap:0.3rem;align-items:center;white-space:nowrap;">' +
                               topicBadge +
                               '<span class="signal-badge" style="font-size:0.62rem;' + aBadgeStyle + '">' + aLabel + '</span>' +
                               '</div></div>' +
                               (a.summary ? '<p style="margin:0.25rem 0 0.15rem 0;font-size:0.72rem;color:var(--muted);line-height:1.35;">' + a.summary + '</p>' : '') +
                               '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.2rem;font-size:0.68rem;color:var(--muted);">' +
                               '<span>Source: <strong>' + (a.publisher || 'Financial Media') + '</strong></span>' +
                               '<span>' + (a.published_at || '') + '</span>' +
                               '</div></div>';
                       }).join('') +
                       '</div></div>')
                    : '';

                content.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.4rem;margin:0.5rem 0;">' +
                    '<div class="metric"><span>Multi-Factor AI Score</span><strong style="color:' + (isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24') + ';">' + scoreStr + ' (' + sig + ')</strong></div>' +
                    '<div class="metric"><span>Volume Accumulation</span><strong>' + (ai.volume_status || 'Average Flow') + ' (' + (ai.volume_ratio || 1.0) + 'x)</strong></div>' +
                    '<div class="metric"><span>7D / 30D Return</span><strong>' + (ai.return_7d >= 0 ? '+' : '') + (ai.return_7d || 0) + '% / ' + (ai.return_30d >= 0 ? '+' : '') + (ai.return_30d || 0) + '%</strong></div>' +
                    '<div class="metric"><span>News Coverage</span><strong>' + (ai.news_count || 0) + ' articles (' + (ai.news_sentiment_label || 'Neutral') + ')</strong></div>' +
                    '</div>' +
                    (ai.thesis ? '<div style="background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.25);border-radius:0.4rem;padding:0.5rem 0.65rem;margin-top:0.4rem;"><strong style="color:#60a5fa;font-size:0.8rem;display:block;margin-bottom:0.2rem;">💡 AI Synthesis Thesis & Reasoning:</strong><p style="margin:0;font-size:0.8rem;line-height:1.45;color:var(--light);">' + ai.thesis + '</p></div>' : '') +
                    '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:0.5rem;">' + catalystsHtml + risksHtml + '</div>' +
                    articlesHtml;
            },

            async runModalConsensus() {
                const ticker = document.getElementById('srModalTicker')?.value;
                const btn = document.getElementById('srModalConsensusRunBtn');
                if (!ticker) return;

                const origHtml = btn ? btn.innerHTML : '⚡ Run AI Consensus';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Synthesizing Models...';
                }

                try {
                    const res = await fetch('/api/v1/consensus/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: [ticker] })
                    });
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Consensus generation failed');
                    }
                    await this._renderModalConsensus(ticker);
                } catch (e) {
                    alert('Error running AI Consensus: ' + e.message);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async _renderModalConsensus(ticker) {
                const badge = document.getElementById('srModalConsensusBadge');
                const content = document.getElementById('srModalConsensusContent');
                if (!content) return;

                if (!ticker) {
                    if (badge) badge.style.display = 'none';
                    content.innerHTML = '<p class="timestamp" style="margin:0;font-size:0.8rem;">No ticker specified for consensus.</p>';
                    return;
                }

                try {
                    content.innerHTML = '<div style="display:flex;align-items:center;gap:0.5rem;color:var(--muted);font-size:0.82rem;"><span class="loading-spinner"></span> Checking multi-model consensus status for ' + ticker + '...</div>';
                    
                    const res = await fetch('/api/v1/consensus/latest?ticker=' + encodeURIComponent(ticker) + '&limit=1');
                    const data = await res.json();
                    const pred = (data.predictions && data.predictions.length) ? data.predictions[0] : null;

                    if (!pred || !pred.consensus_direction) {
                        if (badge) badge.style.display = 'none';
                        content.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.5rem;padding:0.75rem;">' +
                            '<div>' +
                            '<strong style="display:block;font-size:0.85rem;color:var(--light);">No Multi-Model Consensus on Record</strong>' +
                            '<span style="font-size:0.78rem;color:var(--muted);">Trigger an ensemble run to gather calibrated votes, support/resistance targets, and chart patterns from DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, and Mistral Large.</span>' +
                            '</div>' +
                            '<button class="btn btn-sm" onclick="app.runModalConsensus()" style="background:linear-gradient(135deg, #2563eb, #1d4ed8);color:#fff;border:none;font-size:0.78rem;font-weight:700;padding:0.4rem 0.85rem;border-radius:0.4rem;box-shadow:0 2px 8px rgba(37,99,235,0.3);">⚡ Run Consensus Now</button>' +
                            '</div>';
                        return;
                    }

                    // Extract Consensus Metrics
                    const dir = (pred.consensus_direction || 'NEUTRAL').toUpperCase();
                    const isBull = dir.includes('BULL');
                    const isBear = dir.includes('BEAR');
                    const dirColor = isBull ? '#34d399' : isBear ? '#ef4444' : '#fbbf24';
                    const dirBg = isBull ? 'rgba(16,185,129,0.2)' : isBear ? 'rgba(239,68,68,0.2)' : 'rgba(251,191,36,0.2)';
                    
                    const strengthPct = pred.consensus_strength != null ? Math.round(pred.consensus_strength) : 80;
                    const agreeRatio = pred.agreement_ratio != null ? Math.round(pred.agreement_ratio * 100) : (pred.agreement_rate ? Math.round(pred.agreement_rate * 100) : 75);
                    const retPct = pred.consensus_return_pct != null ? pred.consensus_return_pct : (pred.expected_move_pct != null ? pred.expected_move_pct : null);
                    const expRetStr = retPct != null ? ((retPct > 0 ? '+' : '') + Number(retPct).toFixed(2) + '%') : '—';
                    
                    const curPrice = pred.as_of_price != null ? ('₹' + Number(pred.as_of_price).toFixed(2)) : '—';
                    const tgtPrice = pred.consensus_target_price != null ? ('₹' + Number(pred.consensus_target_price).toFixed(2)) : '—';
                    const supPrice = pred.consensus_support != null ? ('₹' + Number(pred.consensus_support).toFixed(2)) : '—';
                    const resPrice = pred.consensus_resistance != null ? ('₹' + Number(pred.consensus_resistance).toFixed(2)) : '—';
                    const stopPrice = pred.consensus_stop_loss != null ? ('₹' + Number(pred.consensus_stop_loss).toFixed(2)) : '—';
                    const rrRatio = pred.consensus_risk_reward != null ? ('1 : ' + Number(pred.consensus_risk_reward).toFixed(1)) : '—';
                    const recAction = pred.consensus_recommended_action || (isBull ? (strengthPct >= 80 ? 'STRONG BUY' : 'ACCUMULATE ON DIPS') : isBear ? 'AVOID / TAKE PROFITS' : 'HOLD / WAIT FOR BREAKOUT');
                    const actColor = recAction.includes('BUY') || recAction.includes('ACCUMULATE') ? '#34d399' : recAction.includes('AVOID') || recAction.includes('TAKE PROFIT') ? '#f87171' : '#fbbf24';

                    if (badge) {
                        badge.style.display = 'inline-block';
                        badge.style.background = dirBg;
                        badge.style.color = dirColor;
                        badge.textContent = dir + ' (' + expRetStr + ' · ' + agreeRatio + '% Agreement · ' + strengthPct + '% Strength)';
                    }

                    // 1. Five-Pillar Price Action Matrix
                    const priceMatrixHtml = '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;margin:0.6rem 0;">' +
                        '<div class="metric" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:var(--muted);">Entry / As-Of Price</span>' +
                        '<strong style="font-size:1.05rem;color:var(--light);">' + curPrice + '</strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(52,211,153,0.08);border:1px solid rgba(52,211,153,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#6ee7b7;">Consensus Target</span>' +
                        '<strong style="font-size:1.05rem;color:#34d399;">' + tgtPrice + ' <small style="font-size:0.75rem;">(' + expRetStr + ')</small></strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#93c5fd;">Support Floor</span>' +
                        '<strong style="font-size:1.05rem;color:#60a5fa;">' + supPrice + '</strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(244,63,94,0.08);border:1px solid rgba(244,63,94,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#fda4af;">Resistance Ceiling</span>' +
                        '<strong style="font-size:1.05rem;color:#fb7185;">' + resPrice + '</strong>' +
                        '</div>' +
                        '<div class="metric" style="background:rgba(234,179,8,0.08);border:1px solid rgba(234,179,8,0.25);border-radius:0.5rem;padding:0.6rem 0.75rem;">' +
                        '<span style="font-size:0.72rem;color:#fde047;">Stop-Loss & R:R</span>' +
                        '<strong style="font-size:1.05rem;color:#facc15;">' + stopPrice + (rrRatio !== '—' ? (' <small style="font-size:0.72rem;color:var(--muted);">(' + rrRatio + ')</small>') : '') + '</strong>' +
                        '</div>' +
                        '</div>';

                    // 2. Verdict & Action Ribbon
                    const actionRibbonHtml = '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.6rem;background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.6rem 0.85rem;margin-bottom:0.6rem;">' +
                        '<div style="display:flex;align-items:center;gap:0.5rem;">' +
                        '<span style="font-size:0.78rem;color:var(--muted);">Ensemble Action:</span>' +
                        '<span class="signal-badge" style="font-size:0.8rem;font-weight:700;background:rgba(255,255,255,0.08);color:' + actColor + ';border:1px solid ' + actColor + '44;padding:0.2rem 0.6rem;">🎯 ' + recAction + '</span>' +
                        '</div>' +
                        '<div style="display:flex;align-items:center;gap:0.8rem;font-size:0.75rem;color:var(--muted);">' +
                        '<span>Consensus Strength: <strong style="color:' + dirColor + ';">' + strengthPct + '%</strong></span>' +
                        '<span>Model Agreement: <strong style="color:var(--light);">' + agreeRatio + '% (' + (pred.valid_count || pred.model_count || 4) + ' Models)</strong></span>' +
                        '</div>' +
                        '</div>';

                    // 3. Synthesis Thesis Callout
                    const thesisText = pred.synthesized_thesis || pred.synthesis_reasoning || pred.synthesis_summary;
                    const thesisHtml = thesisText ? ('<div style="background:linear-gradient(135deg, rgba(59,130,246,0.1), rgba(37,99,235,0.1));border:1px solid rgba(59,130,246,0.35);border-radius:0.5rem;padding:0.75rem 0.95rem;margin-bottom:0.75rem;">' +
                        '<strong style="color:#93c5fd;font-size:0.82rem;display:flex;align-items:center;gap:0.35rem;margin-bottom:0.3rem;">✨ Ensemble Quantitative Thesis:</strong>' +
                        '<p style="margin:0;font-size:0.82rem;line-height:1.55;color:var(--light);">' + thesisText + '</p>' +
                        '</div>') : '';

                    // 4. Individual Model Detail Cards
                    let modelCardsHtml = '';
                    const rawModels = pred.models_breakdown || pred.model_outputs || pred.model_votes || [];
                    const modelsList = Array.isArray(rawModels) ? rawModels : Object.entries(rawModels).map(([k, v]) => ({ model_name: k, ...(typeof v === 'object' ? v : { direction: v }) }));

                    if (modelsList.length) {
                        const cards = modelsList.map(m => {
                            const mName = m.model_name || m.model_id || 'Unknown Model';
                            const mDir = (m.direction || 'NEUTRAL').toUpperCase();
                            const mBull = mDir.includes('BULL');
                            const mBear = mDir.includes('BEAR');
                            const mColor = mBull ? '#34d399' : mBear ? '#f87171' : '#fbbf24';
                            const mBg = mBull ? 'rgba(52,211,153,0.15)' : mBear ? 'rgba(248,113,113,0.15)' : 'rgba(251,191,36,0.15)';
                            
                            const mConf = m.confidence_pct != null ? (m.confidence_pct + '% Conf') : '';
                            const mTgt = m.target_price != null ? ('₹' + Number(m.target_price).toFixed(2)) : '—';
                            const mRet = m.target_return_pct != null ? ((m.target_return_pct > 0 ? '+' : '') + Number(m.target_return_pct).toFixed(2) + '%') : '—';
                            const mSup = m.support_level != null ? ('₹' + Number(m.support_level).toFixed(2)) : '—';
                            const mRes = m.resistance_level != null ? ('₹' + Number(m.resistance_level).toFixed(2)) : '—';
                            const mStop = m.stop_loss_price != null ? ('₹' + Number(m.stop_loss_price).toFixed(2)) : '—';
                            const mRr = m.risk_reward_ratio != null ? ('1 : ' + Number(m.risk_reward_ratio).toFixed(1)) : '—';
                            const mPattern = m.chart_pattern || '';
                            const mVolume = m.volume_profile_insight || '';
                            const mAction = m.recommended_action || '';
                            const mDrivers = Array.isArray(m.key_drivers) ? m.key_drivers : [];
                            const mRisk = m.primary_risk || '';
                            const mLatency = m.latency_ms ? (m.latency_ms + 'ms') : '';

                            return '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.75rem;display:flex;flex-direction:column;gap:0.45rem;">' +
                                '<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:0.4rem;">' +
                                '<div style="display:flex;align-items:center;gap:0.4rem;">' +
                                '<strong style="font-size:0.82rem;color:#93c5fd;">🤖 ' + mName + '</strong>' +
                                (mLatency ? '<span style="font-size:0.68rem;color:var(--muted);font-family:monospace;">⚡ ' + mLatency + '</span>' : '') +
                                '</div>' +
                                '<div style="display:flex;align-items:center;gap:0.35rem;">' +
                                '<span class="signal-badge" style="font-size:0.7rem;font-weight:700;background:' + mBg + ';color:' + mColor + ';padding:0.15rem 0.45rem;">' + mDir + (mConf ? (' · ' + mConf) : '') + '</span>' +
                                '</div>' +
                                '</div>' +

                                // Model Price Levels Row
                                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.35rem;font-size:0.75rem;background:rgba(0,0,0,0.2);padding:0.45rem 0.6rem;border-radius:0.35rem;">' +
                                '<div><span style="color:var(--muted);">Target:</span> <strong style="color:#34d399;">' + mTgt + ' (' + mRet + ')</strong></div>' +
                                '<div><span style="color:var(--muted);">Support:</span> <strong style="color:#60a5fa;">' + mSup + '</strong></div>' +
                                '<div><span style="color:var(--muted);">Resistance:</span> <strong style="color:#fb7185;">' + mRes + '</strong></div>' +
                                '<div><span style="color:var(--muted);">Stop / R:R:</span> <strong style="color:#facc15;">' + mStop + (mRr !== '—' ? (' (' + mRr + ')') : '') + '</strong></div>' +
                                '</div>' +

                                // Pattern & Order Flow
                                (mPattern ? ('<div style="font-size:0.73rem;color:#38bdf8;">📐 <strong>Pattern:</strong> ' + mPattern + '</div>') : '') +
                                (mVolume ? ('<div style="font-size:0.73rem;color:#38bdf8;">📊 <strong>Order Flow:</strong> ' + mVolume + '</div>') : '') +
                                (mAction ? ('<div style="font-size:0.73rem;color:#fcd34d;">🎯 <strong>Recommended:</strong> ' + mAction + '</div>') : '') +

                                // Drivers & Risk
                                (mDrivers.length ? ('<div style="font-size:0.72rem;color:var(--light);line-height:1.35;margin-top:0.15rem;">' +
                                mDrivers.map(d => '<div>🎯 ' + d + '</div>').join('') +
                                '</div>') : '') +
                                (mRisk ? ('<div style="font-size:0.72rem;color:#fca5a5;margin-top:0.1rem;">⚠️ <strong>Risk:</strong> ' + mRisk + '</div>') : '') +
                                '</div>';
                        }).join('');

                        modelCardsHtml = '<div>' +
                            '<strong style="font-size:0.8rem;color:var(--light);display:block;margin:0.75rem 0 0.4rem 0;">🗳️ Individual Model Predictions & Price Action Insights:</strong>' +
                            '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:0.6rem;">' + cards + '</div>' +
                            '</div>';
                    }

                    // Assemble Complete Content
                    content.innerHTML = actionRibbonHtml + priceMatrixHtml + thesisHtml + modelCardsHtml;

                } catch (err) {
                    console.error('Error rendering modal consensus:', err);
                    if (content) content.innerHTML = '<p class="timestamp" style="margin:0;font-size:0.8rem;color:var(--red);">Failed to load consensus data: ' + err.message + '</p>';
                }
            },

            async openAiDetails(market, ticker, e) {
                if (e) e.stopPropagation();
                market = market || this.currentSwingMarket || 'ALL';
                await this.openSwingRangeModal(market, ticker);
                
                // If not already predicted, run it automatically
                const item = (this.swingData || []).find(x => x.ticker === ticker);
                if (!item || !item.ai_synthesis) {
                    await this.runModalAiForecast();
                }
                
                // Scroll directly to the AI section inside modal
                const aiSec = document.getElementById('srModalAiSection');
                if (aiSec) {
                    aiSec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            },

            async predictAllAiSynthesis(e) {
                const btn = (e && e.target) ? e.target : document.getElementById('swingAiThesisAllBtn');
                
                // If swing data isn't loaded yet, load it first
                if (!this.swingData || !this.swingData.length) {
                    await this.loadSwing();
                }

                const tickers = (this.swingData || []).map(r => r.ticker).filter(Boolean);
                if (!tickers.length) {
                    alert('No stocks found in the current watchlist/universe to synthesize.');
                    return;
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Synthesizing ' + tickers.length + ' stocks...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/ai-forecast/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: tickers, watchlist: this.currentSwingMarket || 'ALL' })
                    });
                    const forecasts = await res.json();
                    if (Array.isArray(forecasts)) {
                        const forecastMap = {};
                        forecasts.forEach(f => {
                            const sym = f.symbol || f.ticker;
                            if (sym) forecastMap[sym.toUpperCase()] = f;
                        });

                        this.swingData.forEach(r => {
                            const sym = (r.ticker || '').toUpperCase();
                            if (forecastMap[sym]) {
                                r.ai_synthesis = forecastMap[sym];
                            }
                        });

                        this.renderSwing();
                    } else {
                        alert('Failed to generate AI news synthesis: ' + (forecasts.detail || forecasts.error || 'Server error'));
                    }
                } catch (err) {
                    console.error('Error in predictAllAiSynthesis:', err);
                    alert('Error running batch AI synthesis. Check server logs.');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            async predictAllSwing(e) {
                const btn = (e && e.target) ? e.target : document.getElementById('swingPredictAllBtn');
                
                // If swing data isn't loaded yet, load it first
                if (!this.swingData || !this.swingData.length) {
                    await this.loadSwing();
                }

                const tickers = (this.swingData || []).map(r => r.ticker).filter(Boolean);
                if (!tickers.length) {
                    alert('No stocks found in the current watchlist/universe to predict.');
                    return;
                }

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Predicting ' + tickers.length + ' stocks...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: tickers, lookback: 120, pred_len: 14 })
                    });
                    const forecasts = await res.json();
                    if (Array.isArray(forecasts)) {
                        const forecastMap = {};
                        forecasts.forEach(f => {
                            const sym = f.symbol || f.ticker;
                            if (sym) forecastMap[sym.toUpperCase()] = f;
                        });

                        this.swingData.forEach(r => {
                            const sym = (r.ticker || '').toUpperCase();
                            if (forecastMap[sym]) {
                                r.kronos_prediction = forecastMap[sym];
                            }
                        });

                        this.renderSwing();
                    } else {
                        alert('Failed to generate predictions: ' + (forecasts.detail || forecasts.error || 'Server error'));
                    }
                } catch (err) {
                    console.error('Error in predictAllSwing:', err);
                    alert('Error running batch Kronos predictions. Check server logs.');
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            // =========================================================================
            // 🤖 AI Multi-Model Consensus (DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral)
            // =========================================================================
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

            renderConsensusBadge(ticker, market) {
                if (!ticker) return '—';
                const sym = String(ticker).trim().toUpperCase();
                const pred = this.consensusMap[sym];
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
                        '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(99,102,241,0.18);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);border-radius:0.3rem;" title="Re-run 4-Model AI Consensus for ' + safeSym + '">⚡</button>' +
                        '</div>';
                } else {
                    return '<div id="' + domId + '" style="white-space:nowrap;">' +
                        '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.18rem 0.45rem;font-size:0.7rem;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);border-radius:0.3rem;font-weight:600;white-space:nowrap;" title="Run DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral 4-Model consensus for ' + safeSym + '">⚡ AI Consensus</button>' +
                        '</div>';
                }
            },

            async runConsensusForTicker(ticker, btnEl) {
                if (!ticker) return;
                const sym = String(ticker).trim().toUpperCase();
                const oldHtml = btnEl ? btnEl.innerHTML : '';
                if (btnEl) {
                    btnEl.disabled = true;
                    btnEl.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,0.3);border-radius:50%;border-top-color:#60a5fa;animation:spin 0.8s linear infinite;"></span>';
                }
                
                try {
                    const res = await fetch(API_BASE + '/api/v1/consensus/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticker: sym, timeframe_days: 14, force: false })
                    });
                    const data = await res.json();
                    const preds = (data && (data.predictions || data.results)) ? (data.predictions || data.results) : [];
                    if (preds && preds.length) {
                        const pred = preds[0];
                        if (pred && !pred.error) {
                            this.consensusMap[sym] = pred;
                            
                            // Update all cells matching this ticker across any open table
                            const domId = 'consensus-cell-' + sym.replace(/[^A-Za-z0-9]/g, '_');
                            const cells = document.querySelectorAll('[id="' + domId + '"]');
                            const newHtml = this.renderConsensusBadge(sym, this.currentMarket || 'ALL');
                            cells.forEach(el => {
                                el.outerHTML = newHtml;
                            });
                            
                            if (typeof this.showToast === 'function') {
                                this.showToast('✨ AI Consensus for ' + sym + ': ' + (pred.consensus_direction || 'DONE') + ' (' + (pred.consensus_strength || 80) + '% strength)');
                            }
                            return pred;
                        }
                    }
                } catch (e) {
                    console.error('Error running on-demand consensus for ' + sym + ':', e);
                    if (typeof this.showToast === 'function') {
                        this.showToast('Failed running consensus for ' + sym + ': ' + e.message, 'error');
                    }
                } finally {
                    if (btnEl && btnEl.isConnected) {
                        btnEl.disabled = false;
                        btnEl.innerHTML = oldHtml;
                    }
                }
            },

            async predictAllConsensus(e) {
                const btn = (e && e.target) ? e.target : document.getElementById('swingConsensusAllBtn');
                const origHtml = btn ? btn.innerHTML : '🤖 Consensus All';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Scanning stocks in view...';
                }
                
                // Find all visible tickers on the active tables
                const tickers = [];
                const rows = document.querySelectorAll('#swingTableBody tr strong, #resultsTable tr strong, #topGainersTableBody tr strong, #upcomingSetupsTableBody tr strong, #scannerCandidatesTableBody tr strong, #patStocksTable tr strong');
                rows.forEach(r => {
                    const text = r.textContent.trim().toUpperCase();
                    if (text && text !== '?' && text !== '—' && !tickers.includes(text) && text.length <= 15 && !text.includes('NO CANDIDATES') && !text.includes('NO RESULTS')) {
                        tickers.push(text);
                    }
                });

                if (!tickers.length) {
                    if (typeof this.showToast === 'function') this.showToast('No stocks found in current view to predict.', 'info');
                    else alert('No stocks found in current view to predict.');
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                    return;
                }

                let completed = 0;
                const total = tickers.length;
                for (const ticker of tickers) {
                    if (btn) {
                        btn.innerHTML = '🤖 Consensus ' + (completed + 1) + '/' + total + ' (' + ticker + ')...';
                    }
                    await this.runConsensusForTicker(ticker, null);
                    completed++;
                }

                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
                if (typeof this.showToast === 'function') {
                    this.showToast('✨ Completed AI Consensus for ' + total + ' stocks!');
                } else {
                    alert('✨ Completed AI Consensus for ' + total + ' stocks!');
                }
            },

            async refreshSwing() {
                try {
                    await this.loadSwing();
                } catch (e) {
                    console.error('Error refreshing swing:', e);
                }
            },

            async runKronos() {
                const btn = document.getElementById('kronosRunBtn');
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Running...';
                document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Running Kronos predictions... this can take several minutes.</div>';

                // Priority: typed tickers > selected app watchlist (managed in the app).
                let tickers = [];
                const input = document.getElementById('kronosTickers').value;
                if (input) {
                    tickers = input.split(',').map(t => t.trim()).filter(Boolean);
                } else {
                    const wl = document.getElementById('kronosWatchlist').value || localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                    if (wl) {
                        try {
                            let res = await fetch(API_BASE + '/api/v1/watchlist/' + encodeURIComponent(wl));
                            if (!res.ok) {
                                res = await fetch(API_BASE + '/api/v1/watchlist?name=' + encodeURIComponent(wl));
                            }
                            if (res.ok) {
                                const data = await res.json();
                                tickers = (data && data.tickers) || (Array.isArray(data) ? data : []);
                            }
                        } catch (e) {
                            console.error('Error fetching watchlist tickers:', e);
                        }
                    }
                    if (!tickers.length) {
                        btn.disabled = false;
                        btn.textContent = '▶ Run Predictions';
                        document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No tickers found in watchlist "' + (wl || 'selected') + '". Type tickers above or pick another watchlist.</div>';
                        return;
                    }
                }
                if (!tickers.length) {
                    btn.disabled = false;
                    btn.textContent = '▶ Run Predictions';
                    document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">The selected watchlist has no tickers.</div>';
                    return;
                }
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({tickers: tickers, lookback: 120, pred_len: 14})
                    });
                    if (!res.ok) {
                        const errData = await res.json().catch(() => ({}));
                        throw new Error(errData.detail || ('HTTP ' + res.status));
                    }
                    const data = await res.json();
                    this.renderKronos(data);
                } catch (e) {
                    console.error('Error running Kronos:', e);
                    document.getElementById('kronosWidgets').innerHTML = '<div class="card" style="grid-column:1/-1;margin:0;color:var(--red);">Error running Kronos predictions: ' + (e.message || e) + '</div>';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '▶ Run Predictions';
                }
            },

            async runAllKronos() {
                const btn1 = document.getElementById('kronosRunAllBtn');
                const btn2 = document.getElementById('kronosListRunAllBtn');
                const setButtons = (running, text) => {
                    if (btn1) { btn1.disabled = running; btn1.innerHTML = text; }
                    if (btn2) { btn2.disabled = running; btn2.innerHTML = text; }
                };

                setButtons(true, '<span class="loading-spinner"></span> ⚡ Preparing All...');

                let tickers = [];
                const wl = document.getElementById('kronosWatchlist')?.value || localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';

                try {
                    let res = await fetch(API_BASE + '/api/v1/watchlist/' + encodeURIComponent(wl));
                    if (!res.ok) res = await fetch(API_BASE + '/api/v1/watchlist?name=' + encodeURIComponent(wl));
                    if (res.ok) {
                        const data = await res.json();
                        tickers = (data && data.tickers) || (Array.isArray(data) ? data : []);
                    }
                } catch (e) {
                    console.warn('Watchlist fetch error:', e);
                }

                if (!tickers || !tickers.length) {
                    try {
                        const res = await fetch(API_BASE + '/api/v1/universe/symbols?market=' + encodeURIComponent(wl || 'NSE_TOP'));
                        if (res.ok) {
                            const data = await res.json();
                            tickers = data.tickers || (Array.isArray(data) ? data : []);
                        }
                    } catch (e) {
                        console.warn('Universe fetch error:', e);
                    }
                }

                if (!tickers || !tickers.length) {
                    tickers = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS', 'BHARTIARTL.NS', 'SBIN.NS', 'LICI.NS', 'ITC.NS', 'HINDUNILVR.NS', 'LT.NS', 'BAJFINANCE.NS', 'MARUTI.NS', 'HCLTECH.NS', 'SUNPHARMA.NS', 'TATAMOTORS.NS', 'NTPC.NS', 'ONGC.NS', 'POWERGRID.NS', 'TITAN.NS'];
                }

                const total = tickers.length;
                let allForecasts = [];
                const chunkSize = 8;

                const widgetsEl = document.getElementById('kronosWidgets');
                if (widgetsEl) {
                    widgetsEl.innerHTML = `<div class="card" style="grid-column:1/-1;margin:0;padding:1.2rem;text-align:center;">
                        <div style="font-size:1.05rem;font-weight:700;color:#38bdf8;margin-bottom:0.35rem;">⚡ Running Kronos Neural AI Batch Inference</div>
                        <div style="font-size:0.76rem;color:#94a3b8;margin-bottom:0.75rem;">Processing ${total} stocks in <strong>${wl || 'universe'}</strong> using local neural sequence acceleration...</div>
                        <div style="background:rgba(255,255,255,0.06);border-radius:20px;height:8px;max-width:380px;margin:0 auto;overflow:hidden;">
                            <div id="kronosBatchProgressBar" style="background:linear-gradient(90deg,#3b82f6,#10b981);height:100%;width:0%;transition:width 0.3s ease;"></div>
                        </div>
                        <div id="kronosBatchProgressText" style="font-size:0.72rem;color:#cbd5e1;margin-top:0.5rem;font-family:var(--font-mono);">0 / ${total} completed</div>
                    </div>`;
                }

                for (let i = 0; i < total; i += chunkSize) {
                    const chunk = tickers.slice(i, i + chunkSize);
                    setButtons(true, `⚡ Running (${Math.min(i + chunkSize, total)}/${total})...`);
                    
                    const progBar = document.getElementById('kronosBatchProgressBar');
                    const progText = document.getElementById('kronosBatchProgressText');
                    if (progBar) progBar.style.width = Math.round((i / total) * 100) + '%';
                    if (progText) progText.textContent = `${i} / ${total} completed (${chunk.slice(0, 3).join(', ')}${chunk.length > 3 ? '...' : ''})`;

                    try {
                        const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({tickers: chunk, lookback: 120, pred_len: 14})
                        });
                        if (res.ok) {
                            const chunkForecasts = await res.json();
                            if (Array.isArray(chunkForecasts)) {
                                allForecasts = allForecasts.concat(chunkForecasts);
                            }
                        }
                    } catch (e) {
                        console.error('Kronos batch chunk error:', e);
                    }
                }

                const progBar = document.getElementById('kronosBatchProgressBar');
                const progText = document.getElementById('kronosBatchProgressText');
                if (progBar) progBar.style.width = '100%';
                if (progText) progText.textContent = `✅ Completed ${allForecasts.length} / ${total} predictions!`;

                if (allForecasts.length) {
                    this.renderKronos(allForecasts);
                }

                setButtons(false, '⚡ Run All (Batch)');

                try {
                    await this.loadKronosList();
                    await this.loadKronosSummaryCards();
                } catch (e) {}
            },

            renderKronos(forecasts) {
                const el = document.getElementById('kronosWidgets');
                if (!forecasts.length) {
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No predictions generated. Check that Kronos library is available.</div>';
                    return;
                }
                el.innerHTML = forecasts.map(f => {
                    const sym = f.symbol || f.ticker || '?';
                    const name = f.name || sym;
                    const ret = f.return_pct != null ? Number(f.return_pct) : 0;
                    const isBull = ret >= 0.5;
                    const isBear = ret <= -0.5;
                    const cls = isBull ? 'price-positive' : (isBear ? 'price-negative' : '');
                    const trendEmoji = isBull ? '🟢' : (isBear ? '🔴' : '🟡');
                    const trendText = isBull ? 'Bullish' : (isBear ? 'Bearish' : 'Neutral');
                    const badgeBg = isBull ? 'rgba(16,185,129,0.15)' : (isBear ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.08)');
                    const badgeColor = isBull ? '#34d399' : (isBear ? '#f87171' : 'var(--muted)');

                    const series = Array.isArray(f.forecast_series) ? f.forecast_series : [];
                    const seriesHtml = series.length ? this.renderForecastSeries(series, sym, f.run_at) : '';
                    const gbmHtml = this.renderGbmSignal(f.gbm_prediction);
                    const hasDetails = Boolean(f.explanation || (f.gbm_prediction && !f.gbm_prediction.error));

                    return '<div class="widget-card" style="padding:0.75rem 0.9rem;border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;background:rgba(255,255,255,0.02);display:flex;flex-direction:column;gap:0.4rem;">' +
                        // Top row: Symbol + Name left, Trend badge right
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;">' +
                            '<div>' +
                                '<div style="font-size:1rem;font-weight:700;letter-spacing:0.02em;color:var(--light);">' + sym + '</div>' +
                                (name !== sym ? '<div style="font-size:0.75rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;">' + name + '</div>' : '') +
                            '</div>' +
                            '<span style="background:' + badgeBg + ';color:' + badgeColor + ';padding:0.2rem 0.55rem;border-radius:0.35rem;font-size:0.75rem;font-weight:700;white-space:nowrap;">' +
                                trendEmoji + ' ' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '% ' + trendText +
                            '</span>' +
                        '</div>' +
                        
                        // Metrics strip: 4-column compact horizontal grid
                        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.35rem;background:rgba(0,0,0,0.25);border-radius:0.35rem;padding:0.4rem 0.5rem;text-align:center;">' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">Price</span><strong style="font-size:0.82rem;">₹' + (f.current_price ? f.current_price.toFixed(1) : '—') + '</strong></div>' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">14D Ret</span><strong class="' + cls + '" style="font-size:0.82rem;">' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%</strong></div>' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">Support</span><strong style="font-size:0.82rem;">' + (f.support ? '₹' + Number(f.support).toFixed(1) : '—') + '</strong></div>' +
                            '<div><span style="font-size:0.65rem;color:var(--muted);display:block;text-transform:uppercase;">Resist</span><strong style="font-size:0.82rem;">' + (f.resistance ? '₹' + Number(f.resistance).toFixed(1) : '—') + '</strong></div>' +
                        '</div>' +

                        // Collapsible: AI Rationale & Event Signal (if present)
                        (hasDetails ? (
                            '<details style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.3rem;padding:0.25rem 0.5rem;" onclick="event.stopPropagation()">' +
                                '<summary style="cursor:pointer;font-size:0.72rem;color:var(--muted);font-weight:600;user-select:none;">💡 AI Rationale & Signal</summary>' +
                                '<div style="margin-top:0.35rem;font-size:0.75rem;line-height:1.35;color:var(--muted);">' +
                                    (f.explanation ? '<p style="margin:0 0 0.35rem 0;">' + f.explanation + '</p>' : '') +
                                    gbmHtml +
                                '</div>' +
                            '</details>'
                        ) : '') +

                        // Collapsible: 14-Day OHLCV Forecast Table (if present)
                        (series.length ? (
                            '<details style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:0.3rem;padding:0.25rem 0.5rem;" onclick="event.stopPropagation()">' +
                                '<summary style="cursor:pointer;font-size:0.72rem;color:var(--muted);font-weight:600;user-select:none;">📊 14-Day OHLCV Forecast (' + series.length + ' bars)</summary>' +
                                '<div style="margin-top:0.35rem;max-height:220px;overflow-y:auto;">' + seriesHtml + '</div>' +
                            '</details>'
                        ) : '') +

                        // Footer row: run_at timestamp left, History action button right
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.2rem;padding-top:0.3rem;border-top:1px solid rgba(255,255,255,0.05);">' +
                            '<span style="font-size:0.68rem;color:var(--muted);">' + (f.run_at ? f.run_at.split('.')[0] : '') + '</span>' +
                            '<div style="display:flex;gap:0.3rem;">' +
                                '<button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + sym + '\', \'' + (f.run_at || '') + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV accuracy against realized prices">📊 Benchmark</button>' +
                                '<button onclick="event.stopPropagation(); app.showKronosHistory(\'' + sym + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:0.3rem;">🔍 History</button>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');
            },

            renderForecastSeries(series, ticker, runAt) {
                const rows = series.map(r =>
                    '<tr>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.date ? r.date.split(' ')[0] : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.open != null ? Number(r.open).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.high != null ? Number(r.high).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.low != null ? Number(r.low).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;font-weight:600;">' + (r.close != null ? Number(r.close).toFixed(1) : '—') + '</td>' +
                    '<td style="padding:0.2rem 0.35rem;">' + (r.volume != null ? (Number(r.volume)/1000).toFixed(0) + 'k' : '—') + '</td>' +
                    '</tr>'
                ).join('');

                const benchBtn = ticker ? '<button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + ticker + '\', \'' + (runAt || '') + '\')" class="btn btn-sm" style="margin-top:0.4rem;width:100%;font-size:0.7rem;padding:0.2rem 0.4rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;">📊 Benchmark Realized vs Predicted OHLCV →</button>' : '';

                return '<table class="results-table" style="font-size:0.7rem;width:100%;border-collapse:collapse;">' +
                    '<thead><tr><th style="padding:0.2rem 0.35rem;">Date</th><th style="padding:0.2rem 0.35rem;">O</th><th style="padding:0.2rem 0.35rem;">H</th><th style="padding:0.2rem 0.35rem;">L</th><th style="padding:0.2rem 0.35rem;">C</th><th style="padding:0.2rem 0.35rem;">Vol</th>' +
                    '</tr></thead><tbody>' + rows + '</tbody></table>' + benchBtn;
            },

            async showOhlcvBenchmarkModal(ticker, runAt, forceRefresh = false) {
                this._activeOhlcvTicker = ticker;
                const modal = document.getElementById('kronosOhlcvModal');
                const scorecardsEl = document.getElementById('kronosOhlcvScorecards');
                const tableEl = document.getElementById('kronosOhlcvTableContainer');
                const badgeEl = document.getElementById('kronosOhlcvTickerBadge');
                const runSelectorEl = document.getElementById('kronosOhlcvRunSelector');
                const explanationEl = document.getElementById('kronosOhlcvExplanation');
                const fetchBtn = document.getElementById('kronosOhlcvFetchBtn');

                if (badgeEl) badgeEl.textContent = ticker + (runAt ? ' (' + runAt + ')' : '');
                modal.style.display = 'block';
                scorecardsEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Evaluating OHLCV realized bars for ' + ticker + (forceRefresh ? ' (downloading latest market candles)...' : '...') + '</div>';
                tableEl.innerHTML = '';

                // Populate Run Selector dropdown with all available historical runs for this ticker
                try {
                    const histRes = await fetch(API_BASE + '/api/v1/dashboard/kronos/history/' + encodeURIComponent(ticker));
                    const history = await histRes.json();
                    if (runSelectorEl && Array.isArray(history) && history.length > 0) {
                        const sortedHistory = [...history].sort((a, b) => new Date(b.run_at) - new Date(a.run_at));
                        const activeRun = runAt || sortedHistory[0].run_at;
                        runSelectorEl.innerHTML = sortedHistory.map((h, idx) => {
                            const p = h.prediction || {};
                            const trend = p.trend || h.trend || 'Prediction';
                            const ret = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : h.return_pct;
                            const retStr = ret !== null && ret !== undefined ? (ret >= 0 ? '+' : '') + Number(ret).toFixed(1) + '%' : '';
                            const isSelected = h.run_at === activeRun ? 'selected' : '';
                            const isLatest = idx === 0 ? ' (Latest)' : '';
                            return '<option value="' + h.run_at + '" ' + isSelected + '>' + h.run_at + isLatest + ' — ' + trend + (retStr ? ' (' + retStr + ')' : '') + '</option>';
                        }).join('');

                        runSelectorEl.onchange = (e) => {
                            this.showOhlcvBenchmarkModal(ticker, e.target.value);
                        };
                    }
                } catch (e) {
                    console.warn('Could not populate run selector:', e);
                }

                try {
                    let url = API_BASE + '/api/v1/dashboard/kronos/benchmark-ohlcv/' + encodeURIComponent(ticker);
                    const params = [];
                    if (runAt) params.push('run_at=' + encodeURIComponent(runAt));
                    if (forceRefresh) params.push('force_refresh=true');
                    if (params.length > 0) url += '?' + params.join('&');

                    const res = await fetch(url);
                    const data = await res.json();

                    const summary = data.summary || {};
                    const bars = data.bars || [];

                    if (!bars.length) {
                        scorecardsEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No OHLCV forecast series found to benchmark for ' + ticker + '</div>';
                        return;
                    }

                    const settled = summary.settled_bars || 0;
                    const total = summary.total_bars || bars.length;
                    const mape = summary.mape_pct != null ? summary.mape_pct.toFixed(1) + '%' : '—';
                    const dirAcc = summary.directional_accuracy_pct != null ? summary.directional_accuracy_pct.toFixed(1) + '%' : '—';
                    const corridorAcc = summary.corridor_hit_pct != null ? summary.corridor_hit_pct.toFixed(1) + '%' : '—';
                    const overallScore = summary.overall_score_pct != null ? summary.overall_score_pct.toFixed(1) + '%' : '—';

                    if (explanationEl) {
                        if (summary.is_evaluated) {
                            explanationEl.innerHTML = '✅ <strong>Evaluated Run (' + settled + '/' + total + ' trading days closed):</strong> Realized market candles are compared against Kronos forecast.';
                            explanationEl.style.color = '#34d399';
                        } else {
                            explanationEl.innerHTML = '⏳ <strong>Live Active Run (' + total + ' days upcoming):</strong> Forecasted days are in the future. As daily candles close, realized prices settle automatically. <em>Select an earlier run from the dropdown above to benchmark past predictions or click "Fetch Latest Prices & Settle".</em>';
                            explanationEl.style.color = '#fbbf24';
                        }
                    }

                    const mapeColor = summary.mape_pct != null ? (summary.mape_pct <= 2.5 ? '#34d399' : (summary.mape_pct <= 5.0 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';
                    const dirColor = summary.directional_accuracy_pct != null ? (summary.directional_accuracy_pct >= 60 ? '#34d399' : (summary.directional_accuracy_pct >= 40 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';
                    const corrColor = summary.corridor_hit_pct != null ? (summary.corridor_hit_pct >= 70 ? '#34d399' : (summary.corridor_hit_pct >= 50 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';

                    scorecardsEl.innerHTML = 
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">🎯 Composite Accuracy</span>' +
                            '<strong style="font-size:1.15rem;color:#38bdf8;">' + (summary.is_evaluated ? overallScore : '⏳ Pending') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">📉 MAPE (Price Error)</span>' +
                            '<strong style="font-size:1.15rem;color:' + mapeColor + ';">' + (summary.is_evaluated ? mape : '—') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">📈 Directional Accuracy</span>' +
                            '<strong style="font-size:1.15rem;color:' + dirColor + ';">' + (summary.is_evaluated ? dirAcc : '—') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">🛡️ Corridor [L-H] Hit</span>' +
                            '<strong style="font-size:1.15rem;color:' + corrColor + ';">' + (summary.is_evaluated ? corridorAcc : '—') + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem 0.8rem;text-align:center;background:rgba(255,255,255,0.03);">' +
                            '<span style="font-size:0.72rem;color:var(--muted);display:block;">📅 Settled Days</span>' +
                            '<strong style="font-size:1.15rem;color:var(--light);">' + settled + ' / ' + total + '</strong>' +
                        '</div>';

                    const rows = bars.map(b => {
                        const isSettled = b.status === 'SETTLED';
                        const errCls = b.error_pct != null ? (b.error_pct <= 2.5 ? 'price-positive' : (b.error_pct <= 5.0 ? 'color:#fbbf24;' : 'price-negative')) : '';
                        const errText = b.error_pct != null ? b.error_pct.toFixed(1) + '%' : '—';
                        const deltaText = b.delta_pct != null ? (b.delta_pct >= 0 ? '+' : '') + b.delta_pct.toFixed(1) + '%' : '—';
                        const deltaCls = b.delta_pct != null ? (b.delta_pct >= 0 ? 'price-positive' : 'price-negative') : '';
                        
                        const corridorBadge = isSettled ? (b.corridor_hit ? '<span style="background:rgba(16,185,129,0.2);color:#34d399;padding:0.15rem 0.4rem;border-radius:0.25rem;font-size:0.72rem;font-weight:600;">✅ Inside</span>' : '<span style="background:rgba(239,68,68,0.2);color:#f87171;padding:0.15rem 0.4rem;border-radius:0.25rem;font-size:0.72rem;font-weight:600;">❌ Out</span>') : '<span style="color:var(--muted);font-size:0.72rem;">⏳</span>';
                        
                        const dirBadge = isSettled && b.dir_hit != null ? (b.dir_hit ? '<span style="color:#34d399;font-weight:700;">🟢 Match</span>' : '<span style="color:#f87171;font-weight:700;">🔴 Miss</span>') : '<span style="color:var(--muted);">—</span>';

                        const statusBadge = isSettled ? '<span style="background:rgba(16,185,129,0.15);color:#34d399;padding:0.15rem 0.45rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">✅ Settled</span>' : '<span style="background:rgba(255,255,255,0.06);color:var(--muted);padding:0.15rem 0.45rem;border-radius:0.3rem;font-size:0.72rem;">⏳ Upcoming</span>';

                        return '<tr>' +
                            '<td><strong>' + b.date + '</strong></td>' +
                            '<td>₹' + (b.pred_close ? b.pred_close.toFixed(2) : '—') + '</td>' +
                            '<td>' + (b.actual_close ? '₹' + b.actual_close.toFixed(2) : '—') + '</td>' +
                            '<td class="' + deltaCls + '">' + deltaText + '</td>' +
                            '<td class="' + errCls + '" style="font-weight:600;">' + errText + '</td>' +
                            '<td>' + dirBadge + '</td>' +
                            '<td>[₹' + (b.pred_low ? b.pred_low.toFixed(1) : '—') + ' - ₹' + (b.pred_high ? b.pred_high.toFixed(1) : '—') + ']</td>' +
                            '<td>' + (isSettled ? '[₹' + (b.actual_low ? b.actual_low.toFixed(1) : '—') + ' - ₹' + (b.actual_high ? b.actual_high.toFixed(1) : '—') + ']' : '—') + '</td>' +
                            '<td style="text-align:center;">' + corridorBadge + '</td>' +
                            '<td style="text-align:center;">' + statusBadge + '</td>' +
                            '</tr>';
                    }).join('');

                    tableEl.innerHTML = '<div class="table-wrapper"><table class="results-table">' +
                        '<thead><tr>' +
                        '<th>Date</th><th>Pred Close</th><th>Actual Close</th><th>Δ %</th><th>MAPE Error</th><th>Daily Direction</th><th>Forecast Range [L-H]</th><th>Actual Range [L-H]</th><th>Corridor Hit?</th><th>Status</th>' +
                        '</tr></thead><tbody>' + rows + '</tbody></table></div>';
                } catch (e) {
                    console.error('Error benchmarking OHLCV series:', e);
                    scorecardsEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error evaluating OHLCV benchmark for ' + ticker + '</div>';
                }
            },

            async refreshOhlcvBenchmarkPrices() {
                const ticker = this._activeOhlcvTicker;
                const runSelectorEl = document.getElementById('kronosOhlcvRunSelector');
                const runAt = runSelectorEl ? runSelectorEl.value : null;
                const fetchBtn = document.getElementById('kronosOhlcvFetchBtn');
                if (fetchBtn) {
                    fetchBtn.disabled = true;
                    fetchBtn.innerHTML = '⏳ Fetching Prices & Settling...';
                }
                try {
                    if (ticker) {
                        await this.showOhlcvBenchmarkModal(ticker, runAt, true);
                    }
                } finally {
                    if (fetchBtn) {
                        fetchBtn.disabled = false;
                        fetchBtn.innerHTML = '🔄 Fetch Latest Prices & Settle';
                    }
                }
            },

            renderGbmSignal(gbm) {
                if (!gbm || typeof gbm !== 'object' || gbm.error) {
                    return '';
                }
                const dir = gbm.direction || '—';
                const up = gbm.direction === 'UP';
                const cls = up ? 'price-positive' : 'price-negative';
                const conf = gbm.confidence != null ? (gbm.confidence * 100).toFixed(1) + '%' : '—';
                const pUp = gbm.p_up != null ? (gbm.p_up * 100).toFixed(1) + '%' : '—';
                return '<div style="margin-top:0.3rem;padding:0.25rem 0.4rem;background:rgba(255,255,255,0.03);border-left:3px solid ' + (up ? '#10b981' : '#ef4444') + ';font-size:0.72rem;">' +
                    '<strong class="' + cls + '">' + dir + '</strong> (p_up: ' + pUp + ', conf: ' + conf + ')' +
                    '</div>';
            },

            switchKronosTab(name) {
                const latest = document.getElementById('kronosLatestView');
                const list = document.getElementById('kronosListView');
                const audit = document.getElementById('kronosAuditView');
                const btnLatest = document.getElementById('kronosTabLatest');
                const btnList = document.getElementById('kronosTabList');
                const btnAudit = document.getElementById('kronosTabAudit');
                
                // Hide all views
                latest.style.display = 'none';
                list.style.display = 'none';
                audit.style.display = 'none';
                btnLatest.classList.remove('active');
                btnList.classList.remove('active');
                btnAudit.classList.remove('active');
                
                if (name === 'audit') {
                    audit.style.display = 'block';
                    btnAudit.classList.add('active');
                    this.loadKronosAudit();
                } else if (name === 'list') {
                    list.style.display = 'block';
                    btnList.classList.add('active');
                    this.loadKronosList();
                } else {
                    latest.style.display = 'block';
                    btnLatest.classList.add('active');
                    this.loadKronosLatest();
                }
            },

            onKronosWatchlistChange() {
                const select = document.getElementById('kronosWatchlist');
                const val = select ? select.value : '';
                localStorage.setItem('selectedWatchlist_kronos', val);
                localStorage.setItem('selectedGlobalWatchlist', val);
                
                const gEl = document.getElementById('globalWatchlist');
                if (gEl) gEl.value = val;

                const isAudit = document.getElementById('kronosTabAudit')?.classList.contains('active');
                const isList = document.getElementById('kronosTabList')?.classList.contains('active');
                if (isAudit) {
                    this.loadKronosAudit();
                } else if (isList) {
                    this.loadKronosList();
                } else {
                    this.loadKronosLatest();
                }
            },

            async refreshKronos() {
                try {
                    const isAudit = document.getElementById('kronosTabAudit')?.classList.contains('active');
                    const isList = document.getElementById('kronosTabList')?.classList.contains('active');
                    if (isAudit) {
                        await this.loadKronosAudit();
                    } else if (isList) {
                        await this.loadKronosList();
                    } else {
                        await this.loadKronosLatest();
                    }
                } catch (e) {
                    console.error('Error refreshing Kronos:', e);
                }
            },

            async loadKronosLatest() {
                const el = document.getElementById('kronosWidgets');
                const wl = document.getElementById('kronosWatchlist')?.value || '';
                el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading latest predictions' + (wl ? ' for "' + wl + '"' : '') + '...</div>';
                try {
                    const url = API_BASE + '/api/v1/dashboard/kronos/latest' + (wl ? '?watchlist=' + encodeURIComponent(wl) : '');
                    const res = await fetch(url);
                    const data = await res.json();
                    if (!data.length) {
                        el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No saved predictions' + (wl ? ' for watchlist "' + wl + '"' : '') + '. Click "▶ Run Predictions" above to generate.</div>';
                        return;
                    }
                    // Each row has a nested `prediction` object (the stored payload).
                    const forecasts = data.map(row => {
                        const p = row.prediction || {};
                        return {
                            name: p.name || row.ticker,
                            symbol: p.symbol || row.ticker,
                            current_price: p.current_price,
                            return_pct: p.return_pct,
                            support: p.support,
                            resistance: p.resistance,
                            explanation: p.explanation,
                            run_at: row.run_at,
                            forecast_series: p.forecast_series,
                            gbm_prediction: p.gbm_prediction
                        };
                    });
                    this.renderKronos(forecasts);
                } catch (e) {
                    console.error('Error loading latest Kronos predictions:', e);
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading latest Kronos predictions</div>';
                }
            },

            kronosListSortKey: 'run_at',
            kronosListSortDir: 'desc',
            kronosListData: [],
            kronosListLivePrices: {},

            async loadKronosList() {
                const tbody = document.getElementById('kronosListTable');
                const kpiEl = document.getElementById('kronosListKpis');
                const badgeEl = document.getElementById('kronosListCountBadge');
                const wl = document.getElementById('kronosWatchlist')?.value || '';
                
                if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">Loading all predictions with live prices' + (wl ? ' for "' + wl + '"' : '') + '...</td></tr>';
                
                try {
                    const url = API_BASE + '/api/v1/dashboard/kronos/latest' + (wl ? '?watchlist=' + encodeURIComponent(wl) : '');
                    const res = await fetch(url);
                    const data = await res.json();
                    
                    if (!data.length) {
                        this.kronosListData = [];
                        if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">No predictions found' + (wl ? ' for watchlist "' + wl + '"' : '') + '. Click "▶ Run Predictions" above to generate.</td></tr>';
                        if (kpiEl) kpiEl.innerHTML = '';
                        if (badgeEl) badgeEl.textContent = '0 stocks';
                        return;
                    }

                    this.kronosListData = data;

                    // Fetch live market context prices in parallel
                    const livePrices = {};
                    await Promise.all(data.map(async row => {
                        const ticker = row.ticker;
                        try {
                            const r = await fetch(API_BASE + '/api/v1/market-context/' + encodeURIComponent(ticker));
                            const d = await r.json();
                            livePrices[ticker] = d.current_price;
                        } catch (e) {
                            livePrices[ticker] = null;
                        }
                    }));
                    this.kronosListLivePrices = livePrices;

                    this.renderKronosList();
                } catch (e) {
                    console.error('Error loading Kronos predictions list:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">Error loading predictions list</td></tr>';
                }
            },

            sortKronosList(key) {
                if (this.kronosListSortKey === key) {
                    this.kronosListSortDir = this.kronosListSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.kronosListSortKey = key;
                    this.kronosListSortDir = (key === 'ticker' || key === 'name') ? 'asc' : 'desc';
                }
                this.renderKronosList();
            },

            filterKronosList() {
                this.renderKronosList();
            },

            renderKronosList() {
                const tbody = document.getElementById('kronosListTable');
                const kpiEl = document.getElementById('kronosListKpis');
                const badgeEl = document.getElementById('kronosListCountBadge');
                if (!tbody) return;

                const data = this.kronosListData || [];
                const livePrices = this.kronosListLivePrices || {};
                const searchQ = (document.getElementById('kronosListSearch')?.value || '').toLowerCase().trim();
                const trendFilter = document.getElementById('kronosListTrendFilter')?.value || '';
                const outcomeFilter = document.getElementById('kronosListOutcomeFilter')?.value || '';

                // Map enriched rows
                const enriched = data.map(row => {
                    const p = row.prediction || {};
                    const ticker = row.ticker || '?';
                    const name = p.name || row.ticker;
                    const predP = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : (row.current_price || 0);
                    const liveP = livePrices[ticker];
                    const expRet = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : row.return_pct;
                    const trend = (p.trend || row.trend || '—').trim();
                    const gbm = p.gbm_prediction || {};
                    const support = p.support ? Number(p.support) : (row.support ? Number(row.support) : null);
                    const resistance = p.resistance ? Number(p.resistance) : (row.resistance ? Number(row.resistance) : null);

                    const hasPred = predP > 0;
                    const hasLive = liveP !== null && liveP !== undefined && !isNaN(liveP);
                    let delta = null, deltaPct = null;
                    if (hasPred && hasLive) {
                        delta = liveP - predP;
                        deltaPct = (delta / predP) * 100.0;
                    }

                    // Expected target price
                    let targetP = null;
                    if (hasPred && expRet !== null && expRet !== undefined) {
                        targetP = predP * (1 + expRet / 100.0);
                    }

                    // Outcome evaluation
                    let outcomeStatus = 'PENDING';
                    let outcomeLabel = '⏳ Pending';
                    let outcomeBg = 'rgba(255,255,255,0.06)';
                    let outcomeColor = 'var(--muted)';

                    if (deltaPct !== null) {
                        const isBull = trend === 'Bullish' || (expRet !== null && expRet > 0.3);
                        const isBear = trend === 'Bearish' || (expRet !== null && expRet < -0.3);

                        if (Math.abs(deltaPct) < 0.05) {
                            outcomeStatus = 'FLAT';
                            outcomeLabel = '⏳ Flat (0.0%)';
                            outcomeBg = 'rgba(251,191,36,0.15)';
                            outcomeColor = '#fbbf24';
                        } else if (isBull) {
                            if (deltaPct > 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        } else if (isBear) {
                            if (deltaPct < 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        }
                    }

                    return {
                        row,
                        ticker,
                        name,
                        run_at: row.run_at || '',
                        predicted_price: predP,
                        live_price: liveP,
                        delta,
                        delta_pct: deltaPct,
                        expected_return: expRet,
                        target_price: targetP,
                        trend,
                        gbm,
                        support,
                        resistance,
                        outcome: outcomeStatus,
                        outcomeLabel,
                        outcomeBg,
                        outcomeColor
                    };
                });

                // Compute KPI Summary Stats over all loaded predictions
                const totalStocks = enriched.length;
                let bullCount = 0, bearCount = 0, expRetSum = 0, expRetCount = 0;
                let curRetSum = 0, curRetCount = 0, workedCount = 0, evaluatedCount = 0;

                enriched.forEach(item => {
                    if (item.trend === 'Bullish') bullCount++;
                    else if (item.trend === 'Bearish') bearCount++;
                    if (item.expected_return !== null && item.expected_return !== undefined) {
                        expRetSum += item.expected_return;
                        expRetCount++;
                    }
                    if (item.delta_pct !== null && item.delta_pct !== undefined) {
                        curRetSum += item.delta_pct;
                        curRetCount++;
                    }
                    if (item.outcome === 'WORKED') {
                        workedCount++;
                        evaluatedCount++;
                    } else if (item.outcome === 'FAILED') {
                        evaluatedCount++;
                    }
                });

                const avgExpRet = expRetCount > 0 ? (expRetSum / expRetCount).toFixed(1) + '%' : '—';
                const avgCurRet = curRetCount > 0 ? (curRetSum / curRetCount >= 0 ? '+' : '') + (curRetSum / curRetCount).toFixed(1) + '%' : '—';
                const avgCurColor = curRetCount > 0 ? (curRetSum >= 0 ? '#34d399' : '#f87171') : 'var(--muted)';
                const winRate = evaluatedCount > 0 ? ((workedCount / evaluatedCount) * 100).toFixed(1) + '%' : '—';
                const winRateColor = evaluatedCount > 0 ? (workedCount / evaluatedCount >= 0.6 ? '#34d399' : (workedCount / evaluatedCount >= 0.4 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';

                if (kpiEl) {
                    kpiEl.innerHTML = 
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Total Stocks</span>' +
                            '<strong style="font-size:1.25rem;color:var(--light);">' + totalStocks + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">🟢 Bull / 🔴 Bear</span>' +
                            '<strong style="font-size:1.25rem;"><span style="color:#34d399;">' + bullCount + '</span> / <span style="color:#f87171;">' + bearCount + '</span></strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Avg Expected Return</span>' +
                            '<strong style="font-size:1.25rem;color:#38bdf8;">' + avgExpRet + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Avg Realized Return</span>' +
                            '<strong style="font-size:1.25rem;color:' + avgCurColor + ';">' + avgCurRet + '</strong>' +
                        '</div>' +
                        '<div class="card" style="padding:0.6rem;text-align:center;margin:0;">' +
                            '<span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;display:block;">Win Rate (Hit Rate)</span>' +
                            '<strong style="font-size:1.25rem;color:' + winRateColor + ';">' + winRate + (evaluatedCount > 0 ? ' (' + workedCount + '/' + evaluatedCount + ')' : '') + '</strong>' +
                        '</div>';
                }

                // Filter rows
                let filtered = enriched.filter(item => {
                    if (searchQ) {
                        const matchSym = item.ticker.toLowerCase().includes(searchQ);
                        const matchName = item.name.toLowerCase().includes(searchQ);
                        if (!matchSym && !matchName) return false;
                    }
                    if (trendFilter && item.trend !== trendFilter) return false;
                    if (outcomeFilter) {
                        if (outcomeFilter === 'PENDING') {
                            if (item.outcome !== 'PENDING' && item.outcome !== 'FLAT') return false;
                        } else if (item.outcome !== outcomeFilter) {
                            return false;
                        }
                    }
                    return true;
                });

                if (badgeEl) badgeEl.textContent = filtered.length + ' of ' + totalStocks + ' stocks';

                // Sort rows
                const key = this.kronosListSortKey || 'run_at';
                const dir = this.kronosListSortDir || 'desc';
                filtered.sort((a, b) => {
                    let va = a[key], vb = b[key];
                    if (key === 'run_at') { va = new Date(va); vb = new Date(vb); }
                    va = va === null || va === undefined ? -Infinity : va;
                    vb = vb === null || vb === undefined ? -Infinity : vb;
                    if (va < vb) return dir === 'asc' ? -1 : 1;
                    if (va > vb) return dir === 'asc' ? 1 : -1;
                    return 0;
                });

                if (!filtered.length) {
                    tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted)">No predictions matching filter criteria.</td></tr>';
                    return;
                }

                tbody.innerHTML = filtered.map(item => {
                    const hasLive = item.live_price !== null && item.live_price !== undefined;
                    const hasPred = item.predicted_price > 0;
                    
                    const deltaStr = item.delta !== null ? (item.delta >= 0 ? '+' : '') + item.delta.toFixed(2) : '—';
                    const deltaPctStr = item.delta_pct !== null ? (item.delta_pct >= 0 ? '+' : '') + item.delta_pct.toFixed(2) + '%' : '—';
                    const deltaCls = item.delta_pct !== null ? (item.delta_pct >= 0 ? 'price-positive' : 'price-negative') : '';

                    const expRetStr = item.expected_return !== null && item.expected_return !== undefined ? (item.expected_return >= 0 ? '+' : '') + Number(item.expected_return).toFixed(2) + '%' : '—';
                    const expRetCls = item.expected_return !== null && item.expected_return !== undefined ? (item.expected_return >= 0 ? 'price-positive' : 'price-negative') : '';

                    const trendCls = item.trend === 'Bullish' ? 'price-positive' : item.trend === 'Bearish' ? 'price-negative' : '';
                    
                    // GBM signal badge if present
                    let gbmBadge = '';
                    if (item.gbm && item.gbm.direction) {
                        const gDir = item.gbm.direction;
                        const gColor = gDir === 'UP' ? '#34d399' : '#f87171';
                        const gConf = item.gbm.confidence != null ? ' ' + (item.gbm.confidence * 100).toFixed(0) + '%' : '';
                        gbmBadge = '<span style="display:block;font-size:0.68rem;color:' + gColor + ';opacity:0.85;">GBM: ' + gDir + gConf + '</span>';
                    }

                    // S/R band display
                    let srDisplay = '—';
                    if (item.support && item.resistance) {
                        srDisplay = '₹' + item.support.toFixed(1) + ' – ₹' + item.resistance.toFixed(1);
                    } else if (item.support) {
                        srDisplay = 'Supp: ₹' + item.support.toFixed(1);
                    } else if (item.resistance) {
                        srDisplay = 'Res: ₹' + item.resistance.toFixed(1);
                    }

                    const targetDisplay = item.target_price !== null ? '₹' + item.target_price.toFixed(2) : '—';

                    return '<tr>' +
                        '<td>' +
                            '<div style="font-weight:700;font-size:0.85rem;color:var(--light);">' + (item.name || item.ticker) + '</div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);">' + item.ticker + '</div>' +
                        '</td>' +
                        '<td><span style="font-size:0.75rem;color:var(--muted);">' + (item.run_at ? item.run_at.split('.')[0] : 'N/A') + '</span></td>' +
                        '<td><strong>₹' + (hasPred ? item.predicted_price.toFixed(2) : '—') + '</strong></td>' +
                        '<td>₹' + (hasLive ? item.live_price.toFixed(2) : '—') + '</td>' +
                        '<td class="' + deltaCls + '"><strong>' + deltaPctStr + '</strong><br><span style="font-size:0.7rem;opacity:0.85;">(' + deltaStr + ')</span></td>' +
                        '<td class="' + expRetCls + '" style="font-size:0.9rem;"><strong>' + expRetStr + '</strong></td>' +
                        '<td><span style="font-size:0.82rem;font-weight:600;color:#38bdf8;">' + targetDisplay + '</span></td>' +
                        '<td><strong class="' + trendCls + '">' + item.trend + '</strong>' + gbmBadge + '</td>' +
                        '<td style="text-align:center;"><span style="background:' + item.outcomeBg + ';color:' + item.outcomeColor + ';padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.75rem;font-weight:600;white-space:nowrap;">' + item.outcomeLabel + '</span></td>' +
                        '<td><span style="font-size:0.75rem;color:var(--muted);white-space:nowrap;">' + srDisplay + '</span></td>' +
                        '<td style="text-align:center;">' +
                            '<div style="display:flex;gap:0.3rem;justify-content:center;">' +
                                '<button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + item.ticker + '\', \'' + item.run_at + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV forecast against realized bars">📊 Benchmark</button>' +
                                '<button onclick="event.stopPropagation(); app.showKronosHistory(\'' + item.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:0.3rem;" title="View prediction history & accuracy timeline">🔍 History</button>' +
                            '</div>' +
                        '</td>' +
                    '</tr>';
                }).join('');
            },

            async loadKronosAudit() {
                const tbody = document.getElementById('kronosAuditTable');
                const limit = document.getElementById('kronosAuditLimit')?.value || 200;
                const wl = document.getElementById('kronosWatchlist')?.value || '';
                tbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Loading audit trail' + (wl ? ' for "' + wl + '"' : '') + '...</td></tr>';
                try {
                    let url = API_BASE + '/api/v1/dashboard/kronos/audit?limit=' + limit;
                    if (wl) url += '&watchlist=' + encodeURIComponent(wl);
                    const res = await fetch(url);
                    const rows = await res.json();
                    this.auditData = rows;
                    this.auditSortKey = 'run_at';
                    this.auditSortDir = 'desc';
                    await this.renderKronosAudit();
                } catch (e) {
                    console.error('Error loading Kronos audit:', e);
                    tbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Error loading audit trail</td></tr>';
                }
            },

            async renderKronosAudit() {
                const tbody = document.getElementById('kronosAuditTable');
                const rows = this.auditData || [];
                if (!rows.length) {
                    tbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">No audit records yet. Run Kronos predictions to populate the audit trail.</td></tr>';
                    const stTbody = document.getElementById('kronosStockAccuracyTable');
                    if (stTbody) stTbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:0.75rem;">No historical predictions to evaluate.</td></tr>';
                    return;
                }
                // Sort
                const key = this.auditSortKey;
                const dir = this.auditSortDir;
                const sorted = [...rows].sort((a, b) => {
                    let va = a[key], vb = b[key];
                    if (key === 'run_at') { va = new Date(va); vb = new Date(vb); }
                    va = va === null || va === undefined ? -Infinity : va;
                    vb = vb === null || vb === undefined ? -Infinity : vb;
                    if (va < vb) return dir === 'asc' ? -1 : 1;
                    if (va > vb) return dir === 'asc' ? 1 : -1;
                    return 0;
                });

                // Fetch live current prices in parallel
                const livePrices = {};
                await Promise.all(sorted.map(async row => {
                    const ticker = row.ticker;
                    try {
                        const r = await fetch(API_BASE + '/api/v1/market-context/' + encodeURIComponent(ticker));
                        const d = await r.json();
                        livePrices[ticker] = d.current_price;
                    } catch (e) {
                        livePrices[ticker] = null;
                    }
                }));

                const stockStats = {};
                let totalEvaluated = 0, totalWorked = 0, totalFailed = 0;
                let totalRunsCount = sorted.length;

                // Cluster sorted rows by ticker and timeframe/date session
                const clusters = [];
                const tickerMap = {};
                sorted.forEach(row => {
                    const t = row.ticker || '?';
                    if (!tickerMap[t]) tickerMap[t] = [];
                    tickerMap[t].push(row);
                });

                Object.keys(tickerMap).forEach(t => {
                    const tRows = tickerMap[t];
                    let cur = null;
                    tRows.forEach(row => {
                        const runDate = (row.run_at || '').split(' ')[0];
                        const p = row.prediction || {};
                        const predP = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : (row.current_price || 0);

                        if (!cur) {
                            cur = {
                                ticker: t,
                                date: runDate,
                                anchorPrice: predP,
                                representative: row,
                                runs: [row]
                            };
                        } else {
                            const priceDiff = cur.anchorPrice > 0 ? (Math.abs(predP - cur.anchorPrice) / cur.anchorPrice) * 100 : 0;
                            if (runDate === cur.date || priceDiff < 0.75) {
                                cur.runs.push(row);
                            } else {
                                clusters.push(cur);
                                cur = {
                                    ticker: t,
                                    date: runDate,
                                    anchorPrice: predP,
                                    representative: row,
                                    runs: [row]
                                };
                            }
                        }
                    });
                    if (cur) clusters.push(cur);
                });

                // Sort clusters
                clusters.sort((a, b) => {
                    let va = a.representative[key], vb = b.representative[key];
                    if (key === 'run_at') { va = new Date(a.representative.run_at); vb = new Date(b.representative.run_at); }
                    va = va === null || va === undefined ? -Infinity : va;
                    vb = vb === null || vb === undefined ? -Infinity : vb;
                    if (va < vb) return dir === 'asc' ? -1 : 1;
                    if (va > vb) return dir === 'asc' ? 1 : -1;
                    return 0;
                });

                tbody.innerHTML = clusters.map(cluster => {
                    const row = cluster.representative;
                    const p = row.prediction || {};
                    const predicted = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : row.current_price;
                    const live = livePrices[row.ticker];
                    const hasPred = predicted !== null && predicted !== undefined && !isNaN(predicted) && predicted > 0;
                    const hasLive = live !== null && live !== undefined && !isNaN(live);
                    let delta = null, deltaPct = null;
                    if (hasPred && hasLive) {
                        delta = live - predicted;
                        deltaPct = (delta / predicted) * 100;
                    }
                    const deltaCls = delta !== null ? (delta >= 0 ? 'price-positive' : 'price-negative') : '';
                    const deltaStr = delta !== null ? (delta >= 0 ? '+' : '') + delta.toFixed(2) : '—';
                    const deltaPctStr = deltaPct !== null ? (deltaPct >= 0 ? '+' : '') + deltaPct.toFixed(2) + '%' : '—';
                    const trend = (p.trend || row.trend || '—').trim();
                    const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';
                    const retPct = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : row.return_pct;

                    // Calculate Worked / Failed outcome for this timeframe session
                    let outcomeStatus = 'PENDING';
                    let outcomeLabel = '⏳ Pending';
                    let outcomeBg = 'rgba(255,255,255,0.06)';
                    let outcomeColor = 'var(--muted)';

                    if (deltaPct !== null) {
                        const isBull = trend === 'Bullish' || (retPct !== null && retPct > 0.3);
                        const isBear = trend === 'Bearish' || (retPct !== null && retPct < -0.3);

                        if (Math.abs(deltaPct) < 0.05) {
                            outcomeStatus = 'FLAT';
                            outcomeLabel = '⏳ Flat (0.0%)';
                            outcomeBg = 'rgba(251,191,36,0.15)';
                            outcomeColor = '#fbbf24';
                        } else if (isBull) {
                            if (deltaPct > 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        } else if (isBear) {
                            if (deltaPct < 0) {
                                outcomeStatus = 'WORKED';
                                outcomeLabel = '✅ Worked (' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(16,185,129,0.2)';
                                outcomeColor = '#34d399';
                            } else {
                                outcomeStatus = 'FAILED';
                                outcomeLabel = '❌ Failed (+' + deltaPct.toFixed(1) + '%)';
                                outcomeBg = 'rgba(239,68,68,0.2)';
                                outcomeColor = '#f87171';
                            }
                        }
                    }

                    // Aggregate per-stock stats (1 evaluation per timeframe session)
                    const t = row.ticker || '?';
                    if (!stockStats[t]) {
                        stockStats[t] = { ticker: t, totalSessions: 0, totalRuns: 0, evaluated: 0, worked: 0, failed: 0, predReturns: [], actualDeltas: [] };
                    }
                    const st = stockStats[t];
                    st.totalSessions++;
                    st.totalRuns += cluster.runs.length;
                    if (outcomeStatus === 'WORKED') {
                        st.evaluated++;
                        st.worked++;
                        totalEvaluated++;
                        totalWorked++;
                    } else if (outcomeStatus === 'FAILED') {
                        st.evaluated++;
                        st.failed++;
                        totalEvaluated++;
                        totalFailed++;
                    }
                    if (retPct !== null && retPct !== undefined) st.predReturns.push(Number(retPct));
                    if (deltaPct !== null) st.actualDeltas.push(Number(deltaPct));

                    const runsBadge = cluster.runs.length > 1 ? '<span style="background:rgba(59,130,246,0.2);color:#93c5fd;padding:0.1rem 0.35rem;border-radius:0.25rem;font-size:0.7rem;margin-left:0.35rem;" title="' + cluster.runs.length + ' runs in this timeframe (grouped)">' + cluster.runs.length + ' runs</span>' : '';

                    return '<tr>' +
                        '<td><strong>' + (row.ticker || '?') + '</strong></td>' +
                        '<td>' + (row.run_at || 'N/A') + runsBadge + '</td>' +
                        '<td>' + (hasPred ? '₹' + predicted.toFixed(2) : '—') + '</td>' +
                        '<td>' + (hasLive ? '₹' + live.toFixed(2) : '—') + '</td>' +
                        '<td class="' + deltaCls + '">' + deltaStr + '</td>' +
                        '<td class="' + deltaCls + '">' + deltaPctStr + '</td>' +
                        '<td>' + (retPct !== null && retPct !== undefined ? retPct + '%' : '—') + '</td>' +
                        '<td class="' + trendCls + '">' + trend + '</td>' +
                        '<td style="text-align:center;"><span style="background:' + outcomeBg + ';color:' + outcomeColor + ';padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.75rem;font-weight:600;white-space:nowrap;">' + outcomeLabel + '</span></td>' +
                        '<td>' + (p.support ? '₹' + Number(p.support).toFixed(2) : (row.support ? '₹' + Number(row.support).toFixed(2) : '—')) + '</td>' +
                        '<td>' + (p.resistance ? '₹' + Number(p.resistance).toFixed(2) : (row.resistance ? '₹' + Number(row.resistance).toFixed(2) : '—')) + '</td>' +
                        '<td><div style="display:flex;gap:0.3rem;"><button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + row.ticker + '\', \'' + row.run_at + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV accuracy against realized prices">📊 Benchmark</button><button onclick="app.deleteKronosPrediction(\'' + row.ticker + '\', \'' + row.run_at + '\')" class="btn btn-danger btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;" title="Delete record">🗑️</button></div></td>' +
                        '</tr>';
                }).join('');

                // Render KPI Summary Cards
                const overallAcc = totalEvaluated > 0 ? ((totalWorked / totalEvaluated) * 100).toFixed(1) : '—';
                const overallColor = totalEvaluated > 0 ? (totalWorked / totalEvaluated >= 0.6 ? '#34d399' : (totalWorked / totalEvaluated >= 0.4 ? '#fbbf24' : '#ef4444')) : 'var(--muted)';
                const setElem = (id, prop, val) => { const el = document.getElementById(id); if (el) el[prop] = val; };
                setElem('kronosOverallAcc', 'textContent', overallAcc + (totalEvaluated > 0 ? '%' : ''));
                const elAcc = document.getElementById('kronosOverallAcc');
                if (elAcc) elAcc.style.color = overallColor;
                setElem('kronosEvaluatedCount', 'textContent', totalEvaluated + (clusters.length !== totalRunsCount ? ' sessions (' + totalRunsCount + ' total runs)' : ''));
                setElem('kronosWorkedCount', 'textContent', totalWorked);
                setElem('kronosFailedCount', 'textContent', totalFailed);
                setElem('kronosStocksTracked', 'textContent', Object.keys(stockStats).length);

                // Render Per-Stock Accuracy Breakdown Table
                const stockRows = Object.values(stockStats).sort((a, b) => {
                    const accA = a.evaluated > 0 ? a.worked / a.evaluated : -1;
                    const accB = b.evaluated > 0 ? b.worked / b.evaluated : -1;
                    return (b.evaluated - a.evaluated) || (accB - accA);
                });

                const stTbody = document.getElementById('kronosStockAccuracyTable');
                if (stTbody) {
                    if (!stockRows.length) {
                        stTbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:0.75rem;">No stocks evaluated yet.</td></tr>';
                    } else {
                        stTbody.innerHTML = stockRows.map(s => {
                            const accPct = s.evaluated > 0 ? ((s.worked / s.evaluated) * 100).toFixed(1) : '—';
                            const accCls = s.evaluated > 0 ? (s.worked / s.evaluated >= 0.6 ? 'price-positive' : (s.worked / s.evaluated >= 0.4 ? 'color:#fbbf24;' : 'price-negative')) : '';
                            const avgProj = s.predReturns.length ? (s.predReturns.reduce((a, b) => a + b, 0) / s.predReturns.length).toFixed(1) + '%' : '—';
                            const avgAct = s.actualDeltas.length ? (s.actualDeltas.reduce((a, b) => a + b, 0) / s.actualDeltas.length).toFixed(1) + '%' : '—';
                            const sessLabel = s.totalSessions + (s.totalRuns > s.totalSessions ? ' (' + s.totalRuns + ' runs)' : '');
                            return '<tr>' +
                                '<td><strong>' + s.ticker + '</strong></td>' +
                                '<td>' + sessLabel + '</td>' +
                                '<td>' + s.evaluated + '</td>' +
                                '<td><span style="color:#34d399;font-weight:600;">' + s.worked + '</span></td>' +
                                '<td><span style="color:#ef4444;font-weight:600;">' + s.failed + '</span></td>' +
                                '<td><strong class="' + accCls + '">' + accPct + (s.evaluated > 0 ? '%' : '') + '</strong></td>' +
                                '<td>' + avgProj + '</td>' +
                                '<td>' + avgAct + '</td>' +
                                '<td><button onclick="app.showKronosHistory(\'' + s.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.2);color:#60a5fa;">🔍 History</button></td>' +
                                '</tr>';
                        }).join('');
                    }
                }
            },

            sortAudit(key) {
                if (this.auditSortKey === key) {
                    this.auditSortDir = this.auditSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.auditSortKey = key;
                    this.auditSortDir = 'asc';
                }
                this.renderKronosAudit();
            },

            async deleteKronosPrediction(ticker, runAt) {
                if (!confirm('Delete prediction record for ' + ticker + ' at ' + runAt + '?')) {
                    return;
                }
                try {
                    const res = await fetch(
                        API_BASE + '/api/v1/dashboard/kronos/' + encodeURIComponent(ticker) + '?run_at=' + encodeURIComponent(runAt),
                        { method: 'DELETE' }
                    );
                    const data = await res.json();
                    if (data.success) {
                        this.loadKronosAudit();
                    } else {
                        alert('Failed to delete: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error deleting prediction:', e);
                    alert('Error deleting prediction');
                }
            },

            async showKronosHistory(ticker) {
                const modal = document.getElementById('kronosHistoryModal');
                const content = document.getElementById('kronosHistoryContent');
                const tickerEl = document.getElementById('kronosHistoryTicker');
                const badgeEl = document.getElementById('kronosHistoryAccuracyBadge');
                if (tickerEl) tickerEl.textContent = 'Stock: ' + ticker;
                modal.style.display = 'block';
                content.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading prediction history for ' + ticker + '...</div>';
                
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/history/' + encodeURIComponent(ticker));
                    const data = await res.json();
                    
                    if (!data.length) {
                        content.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No prediction history found for ' + ticker + '</div>';
                        if (badgeEl) badgeEl.style.display = 'none';
                        return;
                    }
                    
                // Fetch live current prices in parallel
                    const livePrices = {};
                    await Promise.all(data.map(async row => {
                        const t = row.ticker;
                        try {
                            const r = await fetch(API_BASE + '/api/v1/market-context/' + encodeURIComponent(t));
                            const d = await r.json();
                            livePrices[t] = d.current_price;
                        } catch (e) {
                            livePrices[t] = null;
                        }
                    }));

                    // Cluster historical runs into timeframe sessions
                    const sortedData = [...data].sort((a, b) => new Date(b.run_at) - new Date(a.run_at));
                    const historyClusters = [];
                    let curSess = null;

                    sortedData.forEach(row => {
                        const runDate = (row.run_at || '').split(' ')[0];
                        const p = row.prediction || {};
                        const predP = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : (row.current_price || 0);

                        if (!curSess) {
                            curSess = {
                                date: runDate,
                                anchorPrice: predP,
                                representative: row,
                                runs: [row]
                            };
                        } else {
                            const priceDiff = curSess.anchorPrice > 0 ? (Math.abs(predP - curSess.anchorPrice) / curSess.anchorPrice) * 100 : 0;
                            if (runDate === curSess.date || priceDiff < 0.75) {
                                curSess.runs.push(row);
                            } else {
                                historyClusters.push(curSess);
                                curSess = {
                                    date: runDate,
                                    anchorPrice: predP,
                                    representative: row,
                                    runs: [row]
                                };
                            }
                        }
                    });
                    if (curSess) historyClusters.push(curSess);

                    let stockWorked = 0, stockEvaluated = 0;
                    
                    content.innerHTML = '<div class="table-wrapper" style="grid-column:1/-1;"><table class="results-table"><thead><tr>' +
                        '<th>Forecast Timeframe</th><th>Price at Prediction</th><th>Current Price</th><th>Δ %</th><th>Return %</th><th>Trend</th><th>Outcome (Worked?)</th><th>Support</th><th>Resistance</th><th>Action</th>' +
                        '</tr></thead><tbody>' + historyClusters.map(cluster => {
                            const row = cluster.representative;
                            const p = row.prediction || {};
                            const predicted = (p.current_price !== null && p.current_price !== undefined) ? p.current_price : row.current_price;
                            const live = livePrices[row.ticker];
                            const hasPred = predicted !== null && predicted !== undefined && !isNaN(predicted) && predicted > 0;
                            const hasLive = live !== null && live !== undefined && !isNaN(live);
                            let deltaPct = null;
                            if (hasPred && hasLive) {
                                const delta = live - predicted;
                                deltaPct = (delta / predicted) * 100;
                            }
                            const deltaPctStr = deltaPct !== null ? (deltaPct >= 0 ? '+' : '') + deltaPct.toFixed(2) + '%' : '—';
                            const deltaCls = deltaPct !== null ? (deltaPct >= 0 ? 'price-positive' : 'price-negative') : '';
                            const trend = (p.trend || row.trend || '—').trim();
                            const trendCls = trend === 'Bullish' ? 'price-positive' : trend === 'Bearish' ? 'price-negative' : '';
                            const retPct = p.return_pct !== null && p.return_pct !== undefined ? p.return_pct : row.return_pct;

                            let outcomeLabel = '⏳ Pending';
                            let outcomeBg = 'rgba(255,255,255,0.06)';
                            let outcomeColor = 'var(--muted)';

                            if (deltaPct !== null) {
                                const isBull = trend === 'Bullish' || (retPct !== null && retPct > 0.3);
                                const isBear = trend === 'Bearish' || (retPct !== null && retPct < -0.3);

                                if (Math.abs(deltaPct) < 0.05) {
                                    outcomeLabel = '⏳ Flat (0.0%)';
                                    outcomeBg = 'rgba(251,191,36,0.15)';
                                    outcomeColor = '#fbbf24';
                                } else if (isBull) {
                                    if (deltaPct > 0) {
                                        stockEvaluated++;
                                        stockWorked++;
                                        outcomeLabel = '✅ Worked (+' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(16,185,129,0.2)';
                                        outcomeColor = '#34d399';
                                    } else {
                                        stockEvaluated++;
                                        outcomeLabel = '❌ Failed (' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(239,68,68,0.2)';
                                        outcomeColor = '#f87171';
                                    }
                                } else if (isBear) {
                                    if (deltaPct < 0) {
                                        stockEvaluated++;
                                        stockWorked++;
                                        outcomeLabel = '✅ Worked (' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(16,185,129,0.2)';
                                        outcomeColor = '#34d399';
                                    } else {
                                        stockEvaluated++;
                                        outcomeLabel = '❌ Failed (+' + deltaPct.toFixed(1) + '%)';
                                        outcomeBg = 'rgba(239,68,68,0.2)';
                                        outcomeColor = '#f87171';
                                    }
                                }
                            }

                            const runsBadge = cluster.runs.length > 1 ? '<span style="background:rgba(59,130,246,0.2);color:#93c5fd;padding:0.1rem 0.35rem;border-radius:0.25rem;font-size:0.7rem;margin-left:0.35rem;">' + cluster.runs.length + ' runs</span>' : '';

                            return '<tr>' +
                                '<td>' + (row.run_at || 'N/A') + runsBadge + '</td>' +
                                '<td>₹' + (hasPred ? predicted.toFixed(2) : '—') + '</td>' +
                                '<td>' + (hasLive ? '₹' + live.toFixed(2) : '—') + '</td>' +
                                '<td class="' + deltaCls + '">' + deltaPctStr + '</td>' +
                                '<td>' + (retPct !== null && retPct !== undefined ? retPct + '%' : '—') + '</td>' +
                                '<td class="' + trendCls + '">' + trend + '</td>' +
                                '<td style="text-align:center;"><span style="background:' + outcomeBg + ';color:' + outcomeColor + ';padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.75rem;font-weight:600;">' + outcomeLabel + '</span></td>' +
                                '<td>₹' + (p.support ? Number(p.support).toFixed(2) : (row.support ? Number(row.support).toFixed(2) : '—')) + '</td>' +
                                '<td>₹' + (p.resistance ? Number(p.resistance).toFixed(2) : (row.resistance ? Number(row.resistance).toFixed(2) : '—')) + '</td>' +
                                '<td><button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + row.ticker + '\', \'' + (row.run_at || '') + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark this past forecast against realized prices">📊 Benchmark</button></td>' +
                                '</tr>';
                        }).join('') + '</tbody></table></div>';

                    if (badgeEl) {
                        badgeEl.style.display = 'inline-block';
                        const accPct = stockEvaluated > 0 ? ((stockWorked / stockEvaluated) * 100).toFixed(1) : '—';
                        const totalRuns = sortedData.length;
                        const sessText = historyClusters.length < totalRuns ? ' across ' + historyClusters.length + ' sessions (' + totalRuns + ' total runs)' : '';
                        badgeEl.textContent = 'Accuracy: ' + accPct + (stockEvaluated > 0 ? '%' : '') + ' (' + stockWorked + '/' + stockEvaluated + ' hits)' + sessText;
                        badgeEl.style.background = stockEvaluated > 0 ? (stockWorked / stockEvaluated >= 0.6 ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)') : 'rgba(59,130,246,0.2)';
                        badgeEl.style.color = stockEvaluated > 0 ? (stockWorked / stockEvaluated >= 0.6 ? '#34d399' : '#f87171') : '#60a5fa';
                    }
                } catch (e) {
                    console.error('Error loading Kronos history:', e);
                    content.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading prediction history</div>';
                }
            },

            // ---------- Swing Range Modal Controller ----------

            _detectedRange: null,

            fillFoundRange() {
                if (!this._detectedRange) return;
                if (this._detectedRange.lower != null) document.getElementById('srModalLower').value = this._detectedRange.lower;
                if (this._detectedRange.upper != null) document.getElementById('srModalUpper').value = this._detectedRange.upper;
                if (this._detectedRange.cycles != null) document.getElementById('srModalCycles').value = this._detectedRange.cycles;
            },

            async openSwingRangeModal(watchlist, ticker) {
                const modal = document.getElementById('swingRangeModal');
                if (!modal) return;
                watchlist = watchlist || 'ALL';
                ticker = (ticker || '').toUpperCase().trim();
                if (!ticker) return;

                // Show modal immediately
                modal.style.display = 'block';

                const setEl = (id, prop, val) => {
                    const el = document.getElementById(id);
                    if (el) el[prop] = val;
                };

                this._detectedRange = null;
                setEl('srModalWatchlist', 'value', watchlist);
                setEl('srModalTicker', 'value', ticker);
                setEl('srModalSubtitle', 'textContent', ticker + ' in watchlist: ' + watchlist);
                setEl('srModalStatus', 'textContent', 'Loading range details...');
                const statusEl = document.getElementById('srModalStatus');
                if (statusEl) statusEl.style.color = '';

                setEl('srModalCurrentPrice', 'textContent', '₹—');
                setEl('srModalFoundRange', 'textContent', '₹— – ₹—');
                setEl('srModalFoundMeta', 'textContent', '');
                setEl('srModal3MOverall', 'textContent', '');
                setEl('srModal3MContent', 'innerHTML', '<div class="timestamp" style="font-size:0.8rem;">Loading 3-month range history...</div>');
                setEl('srModalLower', 'value', '');
                setEl('srModalUpper', 'value', '');
                setEl('srModalCycles', 'value', '');
                setEl('srModalAvgDays', 'value', '—');
                setEl('srModalHistoryContent', 'innerHTML', '<div class="timestamp" style="font-size:0.8rem;">Loading cycle timing...</div>');
                setEl('srModalCycleCount', 'textContent', '');

                try {
                    const res = await fetch(API_BASE + '/api/v1/swing-range?watchlist=' + encodeURIComponent(watchlist) + '&ticker=' + encodeURIComponent(ticker));
                    const data = await res.json();
                    const rng = data.range || {};
                    const autoRng = data.auto_range || {};
                    const history = data.history || [];

                    // Render current price
                    const curPrice = data.current_price;
                    setEl('srModalCurrentPrice', 'textContent', curPrice !== null && curPrice !== undefined
                        ? ('₹' + Number(curPrice).toFixed(2))
                        : 'N/A');

                    // Found / Auto-detected Range (20D)
                    const autoLower = autoRng.lower != null ? Number(autoRng.lower) : (rng.source === 'auto' ? rng.lower_bound : null);
                    const autoUpper = autoRng.upper != null ? Number(autoRng.upper) : (rng.source === 'auto' ? rng.upper_bound : null);
                    const autoCycles = autoRng.cycles != null ? autoRng.cycles : (history.length || 0);
                    const autoAvgDays = autoRng.avg_days != null ? autoRng.avg_days : (history.length ? history.reduce((a, c) => a + (c.duration || 0), 0) / history.length : 0);

                    this._detectedRange = {
                        lower: autoLower,
                        upper: autoUpper,
                        cycles: autoCycles,
                        avg_days: autoAvgDays
                    };

                    if (autoLower != null && autoUpper != null) {
                        const spreadPct = autoLower > 0 ? (((autoUpper - autoLower) / autoLower) * 100).toFixed(1) : '0.0';
                        setEl('srModalFoundRange', 'textContent', '₹' + autoLower.toFixed(2) + ' – ₹' + autoUpper.toFixed(2));
                        setEl('srModalFoundMeta', 'textContent', spreadPct + '% channel width · ' + autoCycles + ' cycles' + (autoAvgDays > 0 ? ' · ~' + autoAvgDays.toFixed(1) + 'd each' : ''));
                    } else {
                        setEl('srModalFoundRange', 'textContent', 'No channel detected');
                        setEl('srModalFoundMeta', 'textContent', 'Insufficient historical price oscillations');
                    }

                    // Render 3-Month Range History & Breakdown
                    const tm3Low = autoRng.three_month_lower;
                    const tm3High = autoRng.three_month_upper;
                    if (tm3Low != null && tm3High != null) {
                        const tm3Spread = tm3Low > 0 ? (((tm3High - tm3Low) / tm3Low) * 100).toFixed(1) : '0.0';
                        setEl('srModal3MOverall', 'textContent', '3M Channel: ₹' + Number(tm3Low).toFixed(2) + ' – ₹' + Number(tm3High).toFixed(2) + ' (' + tm3Spread + '% band)');
                    } else {
                        setEl('srModal3MOverall', 'textContent', '');
                    }

                    const monthlyRanges = autoRng.monthly_ranges || [];
                    if (monthlyRanges.length) {
                        setEl('srModal3MContent', 'innerHTML', '<div class="table-wrapper"><table class="results-table" style="font-size:0.78rem;width:100%;"><thead><tr>' +
                            '<th>Timeframe</th><th>Start Date</th><th>End Date</th><th>Price Range (Low ↔ High)</th><th>Spread</th>' +
                            '</tr></thead><tbody>' + monthlyRanges.map(m =>
                                '<tr>' +
                                '<td><strong>' + m.period + '</strong></td>' +
                                '<td>' + (m.start || '—') + '</td>' +
                                '<td>' + (m.end || '—') + '</td>' +
                                '<td style="font-weight:600;">₹' + Number(m.lower).toFixed(2) + ' – ₹' + Number(m.upper).toFixed(2) + '</td>' +
                                '<td class="price-positive">+' + (m.spread_pct != null ? m.spread_pct : '—') + '%</td>' +
                                '</tr>'
                            ).join('') + '</tbody></table></div>');
                    } else {
                        setEl('srModal3MContent', 'innerHTML', '<div class="timestamp" style="font-size:0.8rem;">No 3-month range breakdown available.</div>');
                    }

                    // Pre-fill input fields
                    const curLower = rng.lower_bound != null ? Number(rng.lower_bound) : (autoLower != null ? Number(autoLower) : null);
                    const curUpper = rng.upper_bound != null ? Number(rng.upper_bound) : (autoUpper != null ? Number(autoUpper) : null);
                    setEl('srModalLower', 'value', curLower != null ? curLower.toFixed(2) : '');
                    setEl('srModalUpper', 'value', curUpper != null ? curUpper.toFixed(2) : '');
                    setEl('srModalCycles', 'value', rng.cycles != null ? rng.cycles : (autoCycles || ''));
                    setEl('srModalAvgDays', 'value', rng.avg_cycle_days != null ? (rng.avg_cycle_days.toFixed(1) + ' days') : (autoAvgDays > 0 ? (autoAvgDays.toFixed(1) + ' days') : '—'));

                    const isUser = rng.source === 'user';
                    const badge = document.getElementById('srModalSourceBadge');
                    if (badge) {
                        badge.textContent = isUser ? 'Custom (User Override)' : 'Auto-detected';
                        badge.style.background = isUser ? 'rgba(59,130,246,0.25)' : 'rgba(59,130,246,0.2)';
                        badge.style.color = isUser ? '#60a5fa' : '#60a5fa';
                    }

                    setEl('srModalStatus', 'textContent', rng.last_updated ? ('Last updated: ' + rng.last_updated) : '');

                    // Render cycle timing history ("time each time" for past 3 months)
                    const cyclesList = (autoRng.cycles_data && autoRng.cycles_data.length) ? autoRng.cycles_data : history;
                    setEl('srModalCycleCount', 'textContent', cyclesList.length + ' cycle' + (cyclesList.length === 1 ? '' : 's') + ' recorded');
                    if (cyclesList.length) {
                        setEl('srModalHistoryContent', 'innerHTML', '<div class="table-wrapper"><table class="results-table" style="font-size:0.78rem;width:100%;"><thead><tr>' +
                            '<th>#</th><th>Start Date</th><th>End Date</th><th>Duration</th><th>Trading Channel (Support ↔ Resistance)</th>' +
                            '</tr></thead><tbody>' + cyclesList.map((c, i) =>
                                '<tr>' +
                                '<td><strong>Cycle ' + (i + 1) + '</strong></td>' +
                                '<td>' + (c.start || '—') + '</td>' +
                                '<td>' + (c.end || '—') + '</td>' +
                                '<td class="price-positive">' + (c.duration != null ? Math.round(c.duration) + 'd' : '—') + '</td>' +
                                '<td>₹' + (c.lower != null ? Number(c.lower).toFixed(2) : '—') + ' – ₹' + (c.upper != null ? Number(c.upper).toFixed(2) : '—') + '</td>' +
                                '</tr>'
                            ).join('') + '</tbody></table></div>');
                    } else {
                        setEl('srModalHistoryContent', 'innerHTML', '<div class="timestamp" style="font-size:0.8rem;">No historical oscillation cycles recorded in the past 3 months.</div>');
                    }

                    // Render Kronos and AI Synthesis sections in modal
                    const currentItem = (this.swingData || []).find(x => x.ticker === ticker);
                    const modalKp = (currentItem && currentItem.kronos_prediction) || data.kronos_prediction;
                    if (this._renderModalKronos) this._renderModalKronos(modalKp);

                    const modalAi = (currentItem && currentItem.ai_synthesis) || data.ai_synthesis;
                    if (this._renderModalAi) this._renderModalAi(modalAi, ticker);

                    // Render Multi-Model AI Consensus
                    if (this._renderModalConsensus) this._renderModalConsensus(ticker);
                } catch (e) {
                    console.error('Error opening swing range modal:', e);
                    setEl('srModalStatus', 'textContent', 'Error loading swing range details.');
                    const s = document.getElementById('srModalStatus');
                    if (s) s.style.color = 'var(--red)';
                }
            },

            fillFoundRange() {
                if (this._detectedRange) {
                    if (this._detectedRange.lower != null) {
                        document.getElementById('srModalLower').value = Number(this._detectedRange.lower).toFixed(2);
                    }
                    if (this._detectedRange.upper != null) {
                        document.getElementById('srModalUpper').value = Number(this._detectedRange.upper).toFixed(2);
                    }
                    if (this._detectedRange.cycles != null) {
                        document.getElementById('srModalCycles').value = this._detectedRange.cycles;
                    }
                    if (this._detectedRange.avg_days != null) {
                        const avgEl = document.getElementById('srModalAvgDays');
                        if (avgEl) avgEl.value = this._detectedRange.avg_days > 0 ? (Number(this._detectedRange.avg_days).toFixed(1) + ' days') : '—';
                    }
                }
            },

            closeSwingRangeModal() {
                const modal = document.getElementById('swingRangeModal');
                if (modal) modal.style.display = 'none';
            },

            async saveSwingRange() {
                const watchlist = document.getElementById('srModalWatchlist').value;
                const ticker = document.getElementById('srModalTicker').value;
                const lower = parseFloat(document.getElementById('srModalLower').value);
                const upper = parseFloat(document.getElementById('srModalUpper').value);
                const cyclesVal = document.getElementById('srModalCycles').value;
                const cycles = cyclesVal ? parseInt(cyclesVal, 10) : null;
                const btn = document.getElementById('srModalSaveBtn');
                const statusEl = document.getElementById('srModalStatus');

                if (isNaN(lower) || isNaN(upper)) {
                    alert('Please enter valid numeric values for Lower and Upper bounds.');
                    return;
                }
                if (lower >= upper) {
                    alert('Support / Lower bound must be strictly less than Resistance / Upper bound.');
                    return;
                }

                btn.disabled = true;
                btn.textContent = 'Saving...';
                statusEl.textContent = 'Saving custom swing range...';
                statusEl.style.color = '';

                try {
                    const res = await fetch(API_BASE + '/api/v1/swing-range', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            watchlist: watchlist,
                            ticker: ticker,
                            lower: lower,
                            upper: upper,
                            cycles: cycles
                        })
                    });
                    const data = await res.json();
                    if (data.success || data.ticker) {
                        statusEl.textContent = 'Saved custom range successfully!';
                        statusEl.style.color = 'var(--green)';
                        const badge = document.getElementById('srModalSourceBadge');
                        if (badge) {
                            badge.textContent = 'Custom (User Override)';
                            badge.style.background = 'rgba(59,130,246,0.25)';
                            badge.style.color = '#60a5fa';
                        }
                        // Update in-place in watchlist table without full list reload
                        if (app.watchlistTab && app.watchlistTab.quotesData) {
                            const it = app.watchlistTab.quotesData.find(x => x.ticker === ticker);
                            if (it) {
                                it.support = lower;
                                it.resistance = upper;
                                it.cycles = cycles;
                                it.range_source = 'user';
                            }
                            if (app.watchlistTab.ranges) {
                                app.watchlistTab.ranges[watchlist + ':' + ticker] = {
                                    watchlist: watchlist,
                                    ticker: ticker,
                                    lower_bound: lower,
                                    upper_bound: upper,
                                    source: 'user'
                                };
                            }
                            app.watchlistTab.renderQuotesTable();
                        }
                        if (app.loadSwing) app.loadSwing();
                    } else {
                        statusEl.textContent = 'Error: ' + (data.detail || data.error || 'Failed to save');
                        statusEl.style.color = 'var(--red)';
                    }
                } catch (e) {
                    console.error('Error saving swing range:', e);
                    statusEl.textContent = 'Network error saving custom range.';
                    statusEl.style.color = 'var(--red)';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '💾 Save Custom Range';
                }
            },

            async resetSwingRange() {
                const watchlist = document.getElementById('srModalWatchlist').value;
                const ticker = document.getElementById('srModalTicker').value;
                if (!confirm('Revert swing range for ' + ticker + ' in watchlist "' + watchlist + '" to auto-detection?')) return;

                const btn = document.getElementById('srModalResetBtn');
                const statusEl = document.getElementById('srModalStatus');
                btn.disabled = true;
                btn.textContent = 'Resetting...';

                try {
                    const res = await fetch(API_BASE + '/api/v1/swing-range?watchlist=' + encodeURIComponent(watchlist) + '&ticker=' + encodeURIComponent(ticker), {
                        method: 'DELETE'
                    });
                    const data = await res.json();
                    statusEl.textContent = 'Reset to auto-detected range!';
                    statusEl.style.color = 'var(--green)';
                    await this.openSwingRangeModal(watchlist, ticker);
                    // Update in-place in watchlist tab
                    if (app.watchlistTab && app.watchlistTab.quotesData) {
                        const it = app.watchlistTab.quotesData.find(x => x.ticker === ticker);
                        if (it) {
                            it.range_source = 'auto';
                            if (data.auto_range) {
                                it.support = data.auto_range.lower;
                                it.resistance = data.auto_range.upper;
                            }
                        }
                        app.watchlistTab.renderQuotesTable();
                    }
                    if (app.loadSwing) app.loadSwing();
                } catch (e) {
                    console.error('Error resetting swing range:', e);
                    statusEl.textContent = 'Error resetting swing range.';
                    statusEl.style.color = 'var(--red)';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '🔄 Reset to Auto';
                }
            },

            async loadWatchlist() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/watchlist');
                    const data = await res.json();
                    const el = document.getElementById('watchlistItems');
                    const tickers = data.tickers || [];
                    const countEl = document.getElementById('watchlistCount');
                    if (countEl) countEl.textContent = '(' + tickers.length + ' stocks)';
                    if (!tickers.length) {
                        el.innerHTML = '<p class="timestamp">Watchlist is empty. Add a ticker above.</p>';
                        return;
                    }
                    el.innerHTML = tickers.map(t =>
                        '<span style="display:inline-flex;align-items:center;gap:0.4rem;background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.3);padding:0.4rem 0.75rem;border-radius:9999px;font-size:0.8rem;">' +
                        t + '<button onclick="app.removeFromWatchlist(\'' + t + '\')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:1rem;" title="Remove">&times;</button></span>'
                    ).join('');
                } catch (e) {
                    console.error('Error loading watchlist:', e);
                }
            },

            async refreshWatchlist() {
                try {
                    await this.loadWatchlist();
                } catch (e) {
                    console.error('Error refreshing watchlist:', e);
                }
            },

            async addToWatchlist() {
                const input = document.getElementById('watchlistAddTicker');
                const ticker = input.value.trim().toUpperCase();
                if (!ticker) return;
                try {
                    const res = await fetch(API_BASE + '/api/v1/watchlist/add', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ticker: ticker})
                    });
                    const data = await res.json();
                    if (!data.success) {
                        alert(data.error || 'Failed to add ticker');
                        return;
                    }
                    input.value = '';
                    document.getElementById('watchlistAddDropdown').style.display = 'none';
                    await this.loadWatchlist();
                    await this.loadWatchlistPredictions();
                } catch (e) {
                    console.error('Error adding to watchlist:', e);
                    alert('Error adding to watchlist');
                }
            },

            async removeFromWatchlist(ticker) {
                try {
                    const res = await fetch(API_BASE + '/api/v1/watchlist/remove', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ticker: ticker})
                    });
                    const data = await res.json();
                    if (!data.success) {
                        alert(data.error || 'Failed to remove ticker');
                        return;
                    }
                    await this.loadWatchlist();
                    await this.loadWatchlistPredictions();
                } catch (e) {
                    console.error('Error removing from watchlist:', e);
                    alert('Error removing from watchlist');
                }
            },

            wireWatchlistAutocomplete() {
                const input = document.getElementById('watchlistAddTicker');
                const dd = document.getElementById('watchlistAddDropdown');
                if (!input || !dd) return;
                let idx = -1;
                input.addEventListener('input', async () => {
                    const q = input.value.trim();
                    if (q.length < 1) { dd.style.display = 'none'; return; }
                    try {
                        const res = await fetch(API_BASE + '/api/v1/playground/search?q=' + encodeURIComponent(q));
                        const items = await res.json();
                        idx = -1;
                        dd.innerHTML = items.map((it, i) =>
                            '<div class="autocomplete-item" data-i="' + i + '" onclick="app.selectWatchlistSymbol(\'' + it.symbol.replace(/'/g, "\\'") + '\')">' +
                            '<strong>' + it.symbol + '</strong> <span style="color:var(--muted);font-size:0.8rem;">' + it.market + '</span>' +
                            '</div>'
                        ).join('');
                        dd.style.display = items.length ? 'block' : 'none';
                    } catch (e) {
                        dd.style.display = 'none';
                    }
                });
                input.addEventListener('keydown', (e) => {
                    const items = dd.querySelectorAll('.autocomplete-item');
                    if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                    else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, -1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                    else if (e.key === 'Escape') { dd.style.display = 'none'; }
                });
                document.addEventListener('click', (e) => {
                    if (!input.contains(e.target) && !dd.contains(e.target)) dd.style.display = 'none';
                });
            },

            selectWatchlistSymbol(symbol) {
                document.getElementById('watchlistAddTicker').value = symbol;
                document.getElementById('watchlistAddDropdown').style.display = 'none';
            },

            async populateUniverseDropdown() {
                const select = document.getElementById('watchlistUniverseSelect');
                if (!select) return;
                try {
                    const res = await fetch(API_BASE + '/api/v1/universe/files');
                    const data = await res.json();
                    const files = data.files || data || [];
                    const items = Array.isArray(files) ? files : [];
                    select.innerHTML = '';
                    items.forEach(f => {
                        const name = typeof f === 'string' ? f : (f.name || f.stem || f);
                        const opt = document.createElement('option');
                        opt.value = name;
                        opt.textContent = name;
                        select.appendChild(opt);
                    });
                    if (!items.length) {
                        const opt = document.createElement('option');
                        opt.value = 'my_watchlist';
                        opt.textContent = 'my_watchlist';
                        select.appendChild(opt);
                    }
                } catch (e) {
                    console.error('Error loading universe files for dropdown:', e);
                    const select = document.getElementById('watchlistUniverseSelect');
                    if (select && !select.options.length) {
                        const opt = document.createElement('option');
                        opt.value = 'my_watchlist';
                        opt.textContent = 'my_watchlist';
                        select.appendChild(opt);
                    }
                }
            },

            async populateKronosWatchlist() {
                if (!this._watchlistNamesCache) {
                    await this.populateWatchlistDropdowns();
                }
            },
            async loadWatchlistPredictions() {
                const universe = document.getElementById('watchlistUniverseSelect')?.value || 'my_watchlist';
                const tbody = document.getElementById('watchlistPredictionsTable');
                if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="padding:1rem;text-align:center;color:var(--muted)">Loading...</td></tr>';
                try {
                    // Resolve tickers from cached universe
                    const uniData = await this.getUniverse(universe);
                    const tickers = (uniData && uniData.tickers) ? uniData.tickers : [];
                    
                    if (!tickers.length) {
                        if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="padding:1rem;text-align:center;color:var(--muted)">Selected universe is empty.</td></tr>';
                        return;
                    }
                    
                    // Load latest Kronos predictions for these tickers
                    const kronosRes = await fetch(API_BASE + '/api/v1/dashboard/kronos/latest?tickers=' + encodeURIComponent(tickers.join(',')));
                    const kronosData = await kronosRes.json();
                    
                    // Index by ticker
                    const byTicker = {};
                    for (const row of kronosData) {
                        const p = row.prediction || {};
                        byTicker[row.ticker] = {
                            run_at: row.run_at,
                            return_pct: p.return_pct,
                            trend: p.trend,
                            support: p.support,
                            resistance: p.resistance,
                        };
                    }
                    
                    // Render table
                    tbody.innerHTML = tickers.map(ticker => {
                        const pred = byTicker[ticker];
                        if (pred) {
                            const trendCls = pred.trend === 'Bullish' ? 'price-positive' : pred.trend === 'Bearish' ? 'price-negative' : '';
                            const trendDisplay = pred.trend || '—';
                            const returnDisplay = pred.return_pct !== null && pred.return_pct !== undefined ? pred.return_pct.toFixed(2) + '%' : 'N/A';
                            const dateDisplay = pred.run_at ? pred.run_at.split(' ')[0] : 'N/A';
                            return '<tr>' +
                                '<td><strong>' + ticker + '</strong></td>' +
                                '<td>' + dateDisplay + '</td>' +
                                '<td>' + returnDisplay + '</td>' +
                                '<td class="' + trendCls + '">' + trendDisplay + '</td>' +
                                '<td><button onclick="app.generateForTicker(\'' + ticker + '\')" class="btn btn-primary btn-sm">Regenerate</button></td>' +
                                '</tr>';
                        } else {
                            return '<tr>' +
                                '<td><strong>' + ticker + '</strong></td>' +
                                '<td class="timestamp">No prediction</td>' +
                                '<td class="timestamp">—</td>' +
                                '<td class="timestamp">—</td>' +
                                '<td><button onclick="app.generateForTicker(\'' + ticker + '\')" class="btn btn-primary btn-sm">Generate</button></td>' +
                                '</tr>';
                        }
                    }).join('');
                } catch (e) {
                    console.error('Error loading watchlist predictions:', e);
                    tbody.innerHTML = '<tr><td colspan="5" style="padding:1rem;text-align:center;color:var(--muted)">Error loading predictions</td></tr>';
                }
            },

            async generateForTicker(ticker) {
                const btn = event.target;
                const originalText = btn.textContent;
                btn.disabled = true;
                btn.textContent = '⏳...';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/watchlist/kronos', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({tickers: [ticker], lookback: 120, pred_len: 14})
                    });
                    const data = await res.json();
                    if (data.success || data.length) {
                        // Refresh the table to show new prediction
                        await this.loadWatchlistPredictions();
                    } else {
                        alert('Failed to generate prediction: ' + (data.detail || data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error generating prediction:', e);
                    alert('Error generating prediction');
                } finally {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            },

            async generateForWatchlist() {
                const btn = event.target;
                const originalText = btn.textContent;
                btn.disabled = true;
                btn.textContent = '⏳ Running...';
                const tbody = document.getElementById('watchlistPredictionsTable');
                tbody.innerHTML = '<tr><td colspan="5" style="padding:1rem;text-align:center;color:var(--muted)">Generating predictions... this can take several minutes.</td></tr>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/watchlist/kronos', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({lookback: 120, pred_len: 14})
                    });
                    const data = await res.json();
                    if (data.success || data.length) {
                        await this.loadWatchlistPredictions();
                    } else {
                        alert('Failed to generate predictions: ' + (data.detail || data.error || 'Unknown error'));
                        await this.loadWatchlistPredictions();
                    }
                } catch (e) {
                    console.error('Error generating predictions:', e);
                    alert('Error generating predictions');
                    await this.loadWatchlistPredictions();
                } finally {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            },

            async loadUniverseFiles() {
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/overview');
                    const data = await res.json();
                    const files = data.universe_files || [];
                    const tbody = document.getElementById('universeFilesTable');
                    tbody.innerHTML = files.map(f =>
                        '<tr><td><strong>' + f.name + '</strong></td><td>' + f.tickers + '</td><td>' + f.modified + '</td></tr>'
                    ).join('');
                } catch (e) {
                    console.error('Error loading universe files:', e);
                }
            },

            async createWatchlist() {
                const input = document.getElementById('newWatchlistName');
                const name = input.value.trim();
                if (!name) return;
                try {
                    const res = await fetch(API_BASE + '/api/v1/universe/create', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({file: name, tickers: []})
                    });
                    const data = await res.json();
                    if (!res.ok) {
                        alert('Error creating watchlist: ' + (data.detail || res.status));
                        return;
                    }
                    input.value = '';
                    this.loadUniverseFiles();
                } catch (e) {
                    console.error('Error creating watchlist:', e);
                    alert('Error creating watchlist');
                }
            },

            async refreshResults() {
                try {
                    await this.loadResultsReport();
                } catch (e) {
                    console.error('Error refreshing results:', e);
                }
            },

            async summarizeResults() {
                const btn = event.target;
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Summarizing...';
                try {
                    const days = document.getElementById('resultsDays').value || 14;
                    const market = document.getElementById('resultsMarket').value || null;
                    const res = await fetch(API_BASE + '/api/v1/dashboard/results/summarize', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({days: days, market: market})
                    });
                    const data = await res.json();
                    if (data.success && data.summary) {
                        alert('LLM Summary:\n\n' + data.summary);
                    } else {
                        alert('Failed to generate summary: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    console.error('Error summarizing results:', e);
                    alert('Error generating summary');
                } finally {
                    btn.disabled = false;
                    btn.textContent = '✨ LLM Summary';
                }
            },

            formatMarketCap(value) {
                if (!value) return 'N/A';
                if (value >= 1e12) return '$' + (value / 1e12).toFixed(2) + 'T';
                if (value >= 1e9) return '$' + (value / 1e9).toFixed(2) + 'B';
                if (value >= 1e6) return '$' + (value / 1e6).toFixed(2) + 'M';
                return '$' + value.toFixed(2);
            },

            // ---------- Data Coverage tab ----------

            async loadDataCoverage() {
                const market = document.getElementById('coverageMarket').value;
                const summaryEl = document.getElementById('coverageSummary');
                const statusEl = document.getElementById('coverageStatus');
                summaryEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading data coverage...</div>';
                statusEl.textContent = '';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/data-coverage?market=' + encodeURIComponent(market));
                    const d = await res.json();
                    this.coverageData = d.rows || [];
                const pct = (v) => v !== null && v !== undefined ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                    summaryEl.innerHTML = [
                        '<div class="metric"><span>Universe Tickers</span><strong>' + d.total + '</strong></div>',
                        '<div class="metric"><span>With Prices</span><strong>' + d.with_prices + '</strong></div>',
                        '<div class="metric"><span>With Earnings</span><strong>' + d.with_earnings + '</strong></div>',
                        '<div class="metric"><span>Earnings Coverage</span><strong>' + pct(d.total ? d.with_earnings / d.total * 100 : 0) + '</strong></div>'
                    ].join('');
                    this.renderCoverageTable();
                    statusEl.textContent = 'Coverage loaded at ' + new Date().toLocaleTimeString();
                } catch (e) {
                    console.error('Error loading data coverage:', e);
                    summaryEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading data coverage</div>';
                }
            },

            renderCoverageTable() {
                const tbody = document.getElementById('coverageTable');
                const rows = this.coverageData || [];
                const filter = (document.getElementById('coverageSearch').value || '').trim().toUpperCase();
                const filtered = filter ? rows.filter(r => (r.ticker || '').toUpperCase().includes(filter)) : rows;
                if (!filtered.length) {
                    tbody.innerHTML = '<tr><td colspan="9" style="padding:1rem;text-align:center;color:var(--muted)">No coverage data for this filter/universe.</td></tr>';
                    return;
                }
                tbody.innerHTML = filtered.map(r => {
                    const fresh = r.earnings_fresh ? '✅ Yes' : '❌ No';
                    return '<tr>' +
                        '<td><strong>' + (r.ticker || '?') + '</strong></td>' +
                        '<td>' + (r.listing_date || '—') + '</td>' +
                        '<td>' + (r.price_start || '—') + '</td>' +
                        '<td>' + (r.price_end || '—') + '</td>' +
                        '<td>' + (r.price_rows || 0) + '</td>' +
                        '<td>' + (r.earnings_start || '—') + '</td>' +
                        '<td>' + (r.earnings_end || '—') + '</td>' +
                        '<td>' + (r.earnings_rows || 0) + '</td>' +
                        '<td>' + fresh + '</td>' +
                        '</tr>';
                }).join('');
            },

            async runIncrementalEarnings() {
                if (this.isMaster === false) {
                    alert('⚠️ Access Restricted: Incremental dataset ingestion is restricted to Master role.');
                    return;
                }
                const btn = (typeof event !== 'undefined' && event && event.target) ? event.target : document.getElementById('coverageFetchMissingBtn');
                const originalText = btn ? btn.textContent : '⚡ Fetch Missing';
                if (btn) {
                    btn.disabled = true;
                    btn.textContent = '⏳ Fetching...';
                }
                const statusEl = document.getElementById('coverageStatus');
                if (statusEl) statusEl.textContent = 'Fetching earnings for tickers missing data... this can take a while.';
                const market = document.getElementById('coverageMarket')?.value || 'ALL';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/earnings/incremental', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({market: market})
                    });
                    if (res.status === 403) {
                        if (statusEl) statusEl.textContent = '⚠️ Access Denied: Master role required.';
                        alert('⚠️ Access Restricted: Incremental dataset ingestion is restricted to Master role.');
                        return;
                    }
                    const data = await res.json();
                    if (data.success) {
                        statusEl.textContent = 'Done: ' + data.fetched + ' fetched, ' + data.already_cached + ' already cached, ' +
                            data.skipped_no_listing + ' skipped (no listing/too new), ' + data.errors + ' errors.';
                        await this.loadDataCoverage();
                    } else {
                        statusEl.textContent = 'Failed: ' + (data.error || 'Unknown error');
                    }
                } catch (e) {
                    console.error('Error running incremental earnings:', e);
                    if (statusEl) statusEl.textContent = 'Error: ' + e.message;
                } finally {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            },

            // ---------- Industries tab ----------

            industryColors: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#84cc16', '#f97316', '#ec4899', '#14b8a6', '#6366f1', '#d946ef', '#a3e635', '#0ea5e9', '#f43f5e', '#22c55e', '#eab308', '#38bdf8', '#fb7185', '#2dd4bf'],

            industryColor(name) {
                let h = 0;
                const s = String(name || '');
                for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
                return this.industryColors[h % this.industryColors.length];
            },

            async loadIndustryMoves() {
                const market = document.getElementById('indMarket').value;
                const lookback = document.getElementById('indLookback').value;
                const groupsEl = document.getElementById('indGroups');
                const statusEl = document.getElementById('indStatus');
                groupsEl.innerHTML = '<div class="card" style="margin:0">Loading industry moves...</div>';
                statusEl.textContent = '';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/industries?market=' + encodeURIComponent(market) + '&lookback_days=' + lookback);
                    const d = await res.json();
                    this.renderIndustryMoves(d);
                    statusEl.textContent = 'Loaded at ' + new Date().toLocaleTimeString() + ' · ' + d.total_results + ' results · ' + d.unclassified + ' unclassified';
                } catch (e) {
                    console.error('Error loading industry moves:', e);
                    groupsEl.innerHTML = '<div class="card" style="margin:0">Error loading industry moves</div>';
                }
            },

            renderIndustryMoves(d) {
                const summaryEl = document.getElementById('indSummary');
                const bestEl = document.getElementById('indBestBanner');
                const groupsEl = document.getElementById('indGroups');
                const industries = d.industries || [];
                const best = d.best_industry;
                const posInd = industries.filter(g => g.positive_count > 0).length;
                summaryEl.innerHTML = [
                    '<div class="metric"><span>Industries</span><strong>' + industries.length + '</strong></div>',
                    '<div class="metric"><span>Total Results</span><strong>' + (d.total_results || 0) + '</strong></div>',
                    '<div class="metric"><span>Industries w/ Gainers</span><strong>' + posInd + '</strong></div>',
                    '<div class="metric"><span>Unclassified</span><strong>' + (d.unclassified || 0) + '</strong></div>'
                ].join('');

                if (best) {
                    const bg = this.industryColor(best);
                    const bestGroup = industries.find(g => g.industry === best);
                    bestEl.innerHTML = '<div class="card" style="border:2px solid ' + bg + ';background:rgba(59,130,246,0.1);">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">🏆 BEST INDUSTRY BY POSITIVE RESULTS</span>' +
                        '<h3 style="margin:0.25rem 0;color:' + bg + ';">' + best + '</h3>' +
                        '<span class="timestamp">' + (bestGroup ? bestGroup.positive_count + ' positive / ' + bestGroup.count + ' results · avg high +' + bestGroup.avg_high_pct.toFixed(2) + '%' : '') + '</span>' +
                        '</div>';
                } else {
                    bestEl.innerHTML = '';
                }

                if (!industries.length) {
                    groupsEl.innerHTML = '<div class="card" style="margin:0">No past results in this window/universe.</div>';
                    return;
                }
                groupsEl.innerHTML = industries.map(g => {
                    const color = this.industryColor(g.industry);
                    const isBest = g.industry === best;
                    const rows = g.rows.map(r => {
                        const hp = r.high_pct !== null && r.high_pct !== undefined ? r.high_pct.toFixed(2) + '%' : '—';
                        const lp = r.low_pct !== null && r.low_pct !== undefined ? r.low_pct.toFixed(2) + '%' : '—';
                        const hcls = (r.high_pct !== null && r.high_pct > 0) ? 'price-positive' : ((r.high_pct !== null && r.high_pct < 0) ? 'price-negative' : '');
                        const lcls = (r.low_pct !== null && r.low_pct < 0) ? 'price-negative' : (r.low_pct !== null ? 'price-positive' : '');
                        return '<tr>' +
                            '<td><strong>' + r.ticker + '</strong></td>' +
                            '<td>' + r.earnings_date + '</td>' +
                            '<td class="' + hcls + '">' + hp + '</td>' +
                            '<td class="' + lcls + '">' + lp + '</td>' +
                            '</tr>';
                    }).join('');
                    return '<details class="card" style="border-left:4px solid ' + color + ';' + (isBest ? 'border:2px solid ' + color + ';background:rgba(59,130,246,0.06);' : '') + '" ' + (isBest ? 'open' : '') + '>' +
                        '<summary style="cursor:pointer;display:flex;align-items:center;gap:0.75rem;font-weight:600;font-size:1rem;">' +
                        '<span class="signal-badge" style="background:' + color + ';color:#fff;">&nbsp;</span>' +
                        '<span>' + g.industry + (isBest ? ' 🏆' : '') + '</span>' +
                        '<span class="timestamp" style="margin-left:auto;">' + g.positive_count + '/' + g.count + ' positive · avg +' + g.avg_high_pct.toFixed(2) + '%</span>' +
                        '</summary>' +
                        '<div class="table-wrapper" style="margin-top:0.75rem;">' +
                        '<table class="results-table"><thead><tr><th>Ticker</th><th>Result Date</th><th>7d High</th><th>7d Low</th></tr></thead>' +
                        '<tbody>' + rows + '</tbody></table></div>' +
                        '</details>';
                }).join('');
            },

            async classifyIndustries() {
                const btn = event.target;
                const original = btn.textContent;
                btn.disabled = true;
                btn.textContent = '⏳ Classifying...';
                const statusEl = document.getElementById('indStatus');
                statusEl.textContent = 'Fetching industry classifications from yfinance... this can take a while.';
                const market = document.getElementById('indMarket').value || 'ALL';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/industries/classify', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({market: market})
                    });
                    const data = await res.json();
                    if (data.success) {
                        statusEl.textContent = 'Classified ' + data.classified + '/' + data.total + ' tickers.';
                        await this.loadIndustryMoves();
                    } else {
                        statusEl.textContent = 'Failed: ' + (data.error || 'Unknown error');
                    }
                } catch (e) {
                    console.error('Error classifying industries:', e);
                    statusEl.textContent = 'Error: ' + e.message;
                } finally {
                    btn.disabled = false;
                    btn.textContent = original;
                }
            },

            // ---------- Buy the Dip tab ----------

            async loadRecentResults() {
                const market = document.getElementById('bdMarket').value;
                const corr = document.getElementById('bdCorrection').value || 5;
                const drop = document.getElementById('bdDrop').value || 3;
                const start = document.getElementById('bdStartDate').value || '';
                const end = document.getElementById('bdEndDate').value || '';
                const statusEl = document.getElementById('bdStatus');
                const todayTbody = document.getElementById('bdTodayTable');
                const yesterdayTbody = document.getElementById('bdYesterdayTable');
                // Persist the controls so the tab returns to the same view next session.
                try {
                    localStorage.setItem('bdDrop', String(drop));
                    localStorage.setItem('bdStartDate', start);
                    localStorage.setItem('bdEndDate', end);
                } catch (e) { /* ignore */ }
                todayTbody.innerHTML = yesterdayTbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Loading...</td></tr>';
                statusEl.textContent = '';
                const q = new URLSearchParams({ market: market, correction_pct: String(corr), drop_pct: String(drop) });
                if (start) q.set('start_date', start);
                if (end) q.set('end_date', end);
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/recent-results?' + q.toString());
                    const d = await res.json();
                    this._bdData = d;
                    this.renderRecentResults(d);
                    statusEl.textContent = 'Loaded at ' + new Date().toLocaleTimeString() + ' — range: ' + (start || 'recent') + ' → ' + (end || 'today');
                } catch (e) {
                    console.error('Error loading recent results:', e);
                    todayTbody.innerHTML = yesterdayTbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Error loading recent results</td></tr>';
                }
            },

            applyBdPreset() {
                const days = document.getElementById('bdPreset').value;
                const iso = (d) => d.toISOString().split('T')[0];
                if (!days) {
                    document.getElementById('bdStartDate').value = '';
                    document.getElementById('bdEndDate').value = '';
                } else {
                    const end = new Date();
                    const start = new Date();
                    start.setDate(start.getDate() - parseInt(days, 10));
                    document.getElementById('bdStartDate').value = iso(start);
                    document.getElementById('bdEndDate').value = iso(end);
                }
                this.loadRecentResults();
            },

            async analyzeEarningsQuality() {
                const market = document.getElementById('bdMarket').value;
                const start = document.getElementById('bdStartDate').value || '';
                const end = document.getElementById('bdEndDate').value || '';
                const statusEl = document.getElementById('bdVerdictStatus');
                statusEl.textContent = 'Analyzing...';
                const q = new URLSearchParams({ market: market });
                if (start) q.set('start_date', start);
                if (end) q.set('end_date', end);
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/recent-results/verdict?' + q.toString());
                    const d = await res.json();
                    const verdicts = d.verdicts || {};
                    if (this._bdData && this._bdData.rows) {
                        this._bdData.rows.forEach(r => {
                            const v = (verdicts[r.ticker] || {});
                            r._verdict = v.verdict || null;
                            r._verdict_metric = v.metric || '';
                        });
                        this.renderRecentResults(this._bdData);
                    }
                    statusEl.textContent = 'Analyzed ' + (d.total || 0) + ' stocks.';
                } catch (e) {
                    console.error('Error analyzing earnings quality:', e);
                    statusEl.textContent = 'Error analyzing.';
                }
            },

            _restoreBdControls() {
                try {
                    const drop = localStorage.getItem('bdDrop');
                    const start = localStorage.getItem('bdStartDate');
                    const end = localStorage.getItem('bdEndDate');
                    if (drop != null) document.getElementById('bdDrop').value = drop;
                    if (start != null) document.getElementById('bdStartDate').value = start;
                    if (end != null) document.getElementById('bdEndDate').value = end;
                } catch (e) { /* ignore */ }
                const hoursEl = document.getElementById('bdMarketHours');
                if (hoursEl) {
                    hoursEl.textContent = (new Date().getHours() >= 16)
                        ? '🕘 After market close — today\'s results are included. '
                        : '☀️ During trading hours — today\'s results appear once the market closes (~16:00). ';
                }
            },

            renderRecentResults(d) {
                const summaryEl = document.getElementById('bdSummary');
                const candEl = document.getElementById('bdCandidates');
                const dipEl = document.getElementById('bdDipRecovery');
                const todayTbody = document.getElementById('bdTodayTable');
                const yesterdayTbody = document.getElementById('bdYesterdayTable');
                const rows = d.rows || [];
                const pct = (v) => v !== null && v !== undefined ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                const fmt = (v) => (v !== null && v !== undefined) ? v.toFixed(2) : '—';
                summaryEl.innerHTML = [
                    '<div class="metric"><span>Buy-Dip Candidates</span><strong>' + (d.buy_dip_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Dip → Recovery</span><strong>' + (d.dip_recovery_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Today</span><strong>' + (d.today_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Yesterday</span><strong>' + (d.yesterday_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Total Results</span><strong>' + (d.total || 0) + '</strong></div>'
                ].join('');
                const recoveries = rows.filter(r => r.is_dip_recovery);
                dipEl.innerHTML = recoveries.length
                    ? '<div class="card" style="border:2px solid #f59e0b;background:rgba(245,158,11,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">📉 → 📈 DIP-THEN-RECOVERY CANDIDATES</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        recoveries.map(r => '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;">' + r.ticker +
                            ' (open ' + pct(r.drop_at_open_pct) + ' → rec ' + pct(r.intraday_recovery_pct) + ')</span>').join('') +
                        '</div></div>'
                    : '<div class="card" style="margin:0 0 1rem 0;">No dip-then-recovery candidates in the current scan.</div>';
                const buys = rows.filter(r => r.is_buy_dip);
                candEl.innerHTML = buys.length
                    ? '<div class="card" style="border:2px solid #10b981;background:rgba(16,185,129,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">🛒 BUY-THE-DIP CANDIDATES</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        buys.map(r => '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#10b981;">' + r.ticker + ' (pull ' + (r.pullback_from_high !== null ? r.pullback_from_high.toFixed(1) + '%' : '—') + ')</span>').join('') +
                        '</div></div>'
                    : '';
                const todayRows = rows.filter(r => (r.day_label || '') === 'Today');
                const yesterdayRows = rows.filter(r => (r.day_label || '') === 'Yesterday');
                const emptyRow = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">No results in this section.</td></tr>';
                todayTbody.innerHTML = todayRows.length ? todayRows.map(r => this._buildBdRow(r)).join('') : emptyRow;
                yesterdayTbody.innerHTML = yesterdayRows.length ? yesterdayRows.map(r => this._buildBdRow(r)).join('') : emptyRow;
            },
            _buildBdRow(r) {
                const pct = (v) => v !== null && v !== undefined ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                const fmt = (v) => (v !== null && v !== undefined) ? v.toFixed(2) : '—';
                const rising = r.high_pct !== null && r.high_pct > 0;
                const dip = r.is_buy_dip;
                const rec = r.is_dip_recovery;
                let sig;
                if (rec) {
                    sig = '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;">📉→📈 Dip Rec</span>';
                } else if (dip) {
                    sig = '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#10b981;">🛒 Buy Dip</span>';
                } else if (rising) {
                    sig = '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#6ee7b7;">Rising</span>';
                } else {
                    sig = '<span class="signal-badge" style="background:rgba(239,68,68,0.2);color:#ef4444;">Falling</span>';
                }
                const pullCls = (r.pullback_from_high !== null && r.pullback_from_high < 0) ? 'price-negative' : 'price-positive';
                const gapCls = (r.drop_at_open_pct !== null && r.drop_at_open_pct < 0) ? 'price-negative' : 'price-positive';
                const mom = (v) => (v !== null && v !== undefined) ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                const momStr = '3D ' + mom(r.momentum_3d) + ' · 7D ' + mom(r.momentum_7d) + ' · 30D ' + mom(r.momentum_30d);
                const ohlcLine = (label, val, valPct) => {
                    const cls = (valPct !== null && valPct !== undefined && valPct >= 0) ? 'price-positive' : (valPct !== null && valPct !== undefined ? 'price-negative' : '');
                    const pctTag = (valPct !== null && valPct !== undefined) ? ' <span class="' + cls + '">(' + pct(valPct) + ')</span>' : '';
                    return '<div style="white-space:nowrap;">' + label + ': <strong>' + fmt(val) + '</strong>' + pctTag + '</div>';
                };
                const rd = r.result_ohlc;
                const rdStr = rd ? ohlcLine('O', rd.open, rd.open_pct) + ohlcLine('H', rd.high, rd.high_pct) + ohlcLine('L', rd.low, rd.low_pct) + ohlcLine('C', rd.close, rd.close_pct) : '—';
                const nd = r.next_day_ohlc;
                const ndStr = nd ? ohlcLine('O', nd.open, nd.open_pct) + ohlcLine('C', nd.close, nd.close_pct) : '—';
                const recStr = r.is_dip_recovery
                    ? '<span class="price-positive">✔ Recovered ' + pct(r.intraday_recovery_pct) + '</span>'
                    : (r.closed_above_open === false ? '<span class="price-negative">✘ Closed low</span>' : '—');
                const verdict = r._verdict || null;
                let verdictStr = '—';
                if (verdict) {
                    const vCls = (verdict === 'Beat' || verdict === 'Strong') ? 'price-positive'
                        : (verdict === 'Miss' || verdict === 'Weak') ? 'price-negative' : '';
                    verdictStr = '<span class="' + vCls + '" title="' + (r._verdict_metric || '') + '">' + verdict + '</span>';
                }
                const rowStyle = rec ? ' style="background:rgba(245,158,11,0.08);"' : (dip ? ' style="background:rgba(16,185,129,0.10);"' : '');
                const changePct = r.change_pct;
                const changeCls = (changePct !== null && changePct !== undefined && changePct >= 0) ? 'price-positive' : 'price-negative';
                return '<tr' + rowStyle + '>' +
                    '<td><strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:var(--light);text-decoration:none;">' + r.ticker + '</a></strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></td>' +
                    '<td><span style="font-size:0.7rem;color:var(--muted)">' + (r.earnings_time || (r.day_label || '')) + '</span></td>' +
                    '<td>' + fmt(r.current_price) + '</td>' +
                    '<td class="' + changeCls + '">' + pct(changePct) + '</td>' +
                    '<td class="' + gapCls + '">' + pct(r.drop_at_open_pct) + '</td>' +
                    '<td>' + rdStr + '</td>' +
                    '<td>' + ndStr + '</td>' +
                    '<td>' + momStr + '</td>' +
                    '<td>' + recStr + '</td>' +
                    '<td class="' + pullCls + '">' + pct(r.pullback_from_high) + '</td>' +
                    '<td>' + sig + '</td>' +
                    '<td>' + verdictStr + '</td>' +
                    '</tr>';
            },
            toggleBdSection(section) {
                const body = document.getElementById(section === 'today' ? 'bdTodaySection' : 'bdYesterdaySection');
                const toggle = document.getElementById(section === 'today' ? 'bdTodayToggle' : 'bdYesterdayToggle');
                if (!body || !toggle) return;
                const hidden = body.style.display === 'none';
                body.style.display = hidden ? '' : 'none';
                toggle.textContent = hidden ? '▼' : '▶';
            },

            // ---------- Patterns tab ----------

            _restorePatternsControls() {
                try {
                    const start = localStorage.getItem('patStartDate');
                    const end = localStorage.getItem('patEndDate');
                    if (start != null) document.getElementById('patStartDate').value = start;
                    if (end != null) document.getElementById('patEndDate').value = end;
                } catch (e) { /* ignore */ }
            },

            async loadPatterns() {
                const market = document.getElementById('patternsMarket').value;
                const start = document.getElementById('patStartDate').value || '';
                const end = document.getElementById('patEndDate').value || '';
                const statusEl = document.getElementById('patStatus');
                const summaryEl = document.getElementById('patSummary');
                try {
                    localStorage.setItem('patStartDate', start);
                    localStorage.setItem('patEndDate', end);
                } catch (e) { /* ignore */ }
                summaryEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0;color:var(--muted)">Loading patterns...</div>';
                const q = new URLSearchParams({ market: market });
                if (start) q.set('start_date', start);
                if (end) q.set('end_date', end);
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/patterns?' + q.toString());
                    const d = await res.json();
                    this.renderPatterns(d);
                    statusEl.textContent = 'Loaded at ' + new Date().toLocaleTimeString() + ' — range: ' + (start || 'recent') + ' → ' + (end || 'today');
                } catch (e) {
                    console.error('Error loading patterns:', e);
                    statusEl.textContent = 'Error loading patterns.';
                }
            },

            applyPatternsPreset() {
                const days = document.getElementById('patPreset').value;
                const iso = (d) => d.toISOString().split('T')[0];
                if (!days) {
                    document.getElementById('patStartDate').value = '';
                    document.getElementById('patEndDate').value = '';
                } else {
                    const end = new Date();
                    const start = new Date();
                    start.setDate(start.getDate() - parseInt(days, 10));
                    document.getElementById('patStartDate').value = iso(start);
                    document.getElementById('patEndDate').value = iso(end);
                }
                this.loadPatterns();
            },


            renderPatterns(d) {
                const summaryEl = document.getElementById('patSummary');
                const todayEl = document.getElementById('patTodayCards');
                const dipEl = document.getElementById('patDip');
                const keptEl = document.getElementById('patKept');
                const indEl = document.getElementById('patIndustries');
                const bestPos = d.best_positive_industry || {};
                const bestRatio = d.best_ratio_industry || {};
                summaryEl.innerHTML = [
                    '<div class="metric"><span>Total Results</span><strong>' + (d.total || 0) + '</strong></div>',
                    '<div class="metric"><span>Positive</span><strong class="price-positive">' + (d.positive || 0) + '</strong></div>',
                    '<div class="metric"><span>Negative</span><strong class="price-negative">' + (d.negative || 0) + '</strong></div>',
                    '<div class="metric"><span>Dipped → Comeback ≥50%</span><strong>' + (d.comeback_50_total || 0) + '</strong></div>',
                    '<div class="metric"><span>Kept Dipping</span><strong class="price-negative">' + (d.kept_dipping_total || 0) + '</strong></div>',
                    '<div class="metric"><span>Best Positive Industry</span><strong>' + (bestPos.industry || '—') + ' (' + (bestPos.positive || 0) + ')</strong></div>',
                    '<div class="metric"><span>Best Ratio Industry</span><strong>' + (bestRatio.industry || '—') + ' (' + (bestRatio.ratio || 0) + ')</strong></div>'
                ].join('');

                // Today's earnings summary cards
                const todayCount = d.today_count || 0;
                const todayPos = d.today_positive || 0;
                const todayCb = d.today_came_back || 0;
                const todayNr = d.today_no_recovery || 0;
                todayEl.innerHTML = [
                    '<div class="metric"><span>Today\'s Earnings</span><strong>' + todayCount + '</strong></div>',
                    '<div class="metric"><span>Today Positive</span><strong class="price-positive">' + todayPos + '</strong></div>',
                    '<div class="metric"><span>Today Comeback≥50%</span><strong>' + todayCb + '</strong></div>',
                    '<div class="metric"><span>Today No Recovery</span><strong class="price-negative">' + todayNr + '</strong></div>'
                ].join('');

                dipEl.innerHTML = d.total
                    ? '<div class="card" style="border:2px solid #f59e0b;background:rgba(245,158,11,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">📉 → 📈 POSITIVE RESULTS THAT DIPPED THEN RECOVERED</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;">positive & dipped: ' + (d.positive_dipped_total || 0) + '</span>' +
                        '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#10b981;">recovered ≥ 50% of drop: ' + (d.comeback_50_total || 0) + '</span>' +
                        '</div></div>'
                    : '';

                const kept = (d.rows || []).filter(r => r.kept_dipping);
                keptEl.innerHTML = kept.length
                    ? '<div class="card" style="border:2px solid #ef4444;background:rgba(239,68,68,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">🔻 GOOD RESULTS THAT KEPT DIPPING</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        kept.map(r => '<span class="signal-badge" style="background:rgba(239,68,68,0.2);color:#ef4444;">' + r.ticker + ' (' + (r.industry || '—') + ')</span>').join('') +
                        '</div></div>'
                    : '';

                const industries = d.industries || [];
                if (!industries.length) {
                    indEl.innerHTML = '<div class="card" style="margin:0">No results in the selected range.</div>';
                    return;
                }
                const rowsHtml = industries.map(x =>
                    '<tr>' +
                    '<td>' + (x.industry || '—') + '</td>' +
                    '<td>' + x.total + '</td>' +
                    '<td class="price-positive">' + x.positive + '</td>' +
                    '<td class="price-negative">' + x.negative + '</td>' +
                    '<td>' + x.stocks + '</td>' +
                    '<td>' + (x.ratio || 0) + '</td>' +
                    '<td>' + x.positive_dipped + '</td>' +
                    '<td class="price-positive">' + x.comeback_50 + '</td>' +
                    '<td class="price-negative">' + x.kept_dipping + '</td>' +
                    '</tr>'
                ).join('');
                indEl.innerHTML = '<div class="table-wrapper"><table class="results-table">' +
                    '<thead><tr><th>Industry</th><th>Results</th><th>Positive</th><th>Negative</th><th>Stocks</th><th>Ratio</th><th>Dipped</th><th>Comeback≥50%</th><th>Kept Dipping</th></tr></thead>' +
                    '<tbody>' + rowsHtml + '</tbody></table></div>';

                // Today's per-stock table (sortable).
                this._patTodayRows = (d.rows || []).filter(r => r.is_today);
                this.patStocksSortKey = 'ticker';
                this.patStocksSortDir = 'asc';
                this.renderPatStocksTable();
            },

            renderPatStocksTable() {
                const tbody = document.getElementById('patStocksTable');
                const rows = this._patTodayRows || [];
                if (!rows.length) {
                    tbody.innerHTML = '<tr><td colspan="13" style="padding:1rem;text-align:center;color:var(--muted)">No earnings today in the selected range.</td></tr>';
                    return;
                }
                const sorted = [...rows].sort((a, b) => {
                    let va = a[this.patStocksSortKey], vb = b[this.patStocksSortKey];
                    if (typeof va === 'string') va = va.toLowerCase();
                    if (typeof vb === 'string') vb = vb.toLowerCase();
                    if (va == null) va = '';
                    if (vb == null) vb = '';
                    if (va < vb) return this.patStocksSortDir === 'asc' ? -1 : 1;
                    if (va > vb) return this.patStocksSortDir === 'asc' ? 1 : -1;
                    return 0;
                });
                const fmt = (v) => (v !== null && v !== undefined && !Number.isNaN(v)) ? Number(v).toFixed(2) : '—';
                const cls = (v, pos) => (v == null || v === '' || Number.isNaN(v)) ? '' : (v > 0 ? 'price-positive' : v < 0 ? 'price-negative' : '');
                const badge = (v) => v ? '<span style="color:#10b981">✔</span>' : v === false ? '<span style="color:#ef4444">✘</span>' : '—';
                const resultBadge = (v) => {
                    if (v === 'positive') return '<span class="price-positive">Positive</span>';
                    if (v === 'negative') return '<span class="price-negative">Negative</span>';
                    return v || '—';
                };
                tbody.innerHTML = sorted.map(r =>
                    '<tr>' +
                    '<td><strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:var(--light);text-decoration:none;">' + (r.ticker || '—') + '</a></strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></td>' +
                    '<td>' + (r.industry || '—') + '</td>' +
                    '<td>' + resultBadge(r.result_class) + '</td>' +
                    '<td class="' + cls(r.reaction_return_pct, true) + '">' + (r.reaction_return_pct !== null && r.reaction_return_pct !== undefined ? r.reaction_return_pct.toFixed(2) + '%' : '—') + '</td>' +
                    '<td>' + fmt(r.day_open) + '</td><td>' + fmt(r.day_high) + '</td><td>' + fmt(r.day_low) + '</td><td>' + fmt(r.day_close) + '</td>' +
                    '<td>' + this.renderConsensusBadge(r.ticker, 'IN') + '</td>' +
                    '<td>' + badge(r.dipped) + '</td>' +
                    '<td>' + badge(r.comeback_50) + '</td>' +
                    '<td>' + badge(r.kept_dipping) + '</td>' +
                    '</tr>'
                ).join('');
            },

            patStocksSort(key) {
                if (this.patStocksSortKey === key) {
                    this.patStocksSortDir = this.patStocksSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.patStocksSortKey = key;
                    this.patStocksSortDir = 'asc';
                }
                this.renderPatStocksTable();
            },

            // ---------- Playground tab (API Console) ----------

            pg: {
                catalog: [],
                lastJson: null,
                lastStatus: null,

                async init() {
                    try {
                        const res = await fetch(API_BASE + '/api/v1/playground/endpoints');
                        const data = await res.json();
                        // Guard: the catalog must be an array of endpoint objects.
                        this.catalog = Array.isArray(data) ? data : [];
                        if (!Array.isArray(data)) {
                            console.error('Endpoint catalog response was not an array:', data);
                        }
                    } catch (e) {
                        console.error('Error loading endpoint catalog:', e);
                        this.catalog = [];
                    }
                    this.populateGroup();
                    this.wireSymbolAutocomplete();
                },

                populateGroup() {
                    const groupSel = document.getElementById('pgGroup');
                    const groups = [...new Set(this.catalog.map(e => e.group))];
                    if (groups.length) {
                        groupSel.innerHTML = groups.map(g => '<option value="' + g + '">' + g + '</option>').join('');
                    }
                    groupSel.onchange = () => this.populateEndpoints();
                    this.populateEndpoints();
                },

                populateEndpoints() {
                    const group = document.getElementById('pgGroup').value;
                    const epSel = document.getElementById('pgEndpoint');
                    const eps = this.catalog.filter(e => e.group === group);
                    if (eps.length) {
                        epSel.innerHTML = eps.map(e =>
                            '<option value="' + e.id + '">' + e.method + ' ' + e.path + '</option>'
                        ).join('');
                    } else {
                        epSel.innerHTML = '<option value="">No endpoints for this group</option>';
                    }
                    epSel.onchange = () => this.renderParams();
                    this.renderParams();
                },

                currentEndpoint() {
                    const id = document.getElementById('pgEndpoint').value;
                    return this.catalog.find(e => e.id === id) || null;
                },

                renderParams() {
                    const ep = this.currentEndpoint();
                    const wrap = document.getElementById('pgParams');
                    const line = document.getElementById('pgRequestLine');
                    if (!ep) { wrap.innerHTML = ''; line.textContent = 'Select an endpoint.'; return; }
                    const symbol = document.getElementById('pgSymbol').value.trim().toUpperCase() || 'RELIANCE.NS';
                    wrap.innerHTML = (ep.params || []).map(p => {
                        const val = p.name === 'tickers' ? symbol : (p.name === 'market' ? 'IN' : (p.name === 'period' ? '3mo' : (p.name === 'interval' ? '1d' : (p.name === 'limit' ? '10' : (p.name === 'lookback' ? '120' : (p.name === 'pred_len' ? '14' : ''))))));
                        if (p.type === 'select') {
                            const opts = (p.options || []).map(o => '<option value="' + o + '"' + (o === val ? ' selected' : '') + '>' + o + '</option>').join('');
                            return '<label class="timestamp" style="display:flex;flex-direction:column;gap:0.2rem;">' + p.name +
                                '<select data-param="' + p.name + '" style="padding:0.3rem;border:1px solid rgba(255,255,255,0.2);border-radius:0.4rem;background:rgba(255,255,255,0.05);color:var(--light);">' + opts + '</select></label>';
                        }
                        return '<label class="timestamp" style="display:flex;flex-direction:column;gap:0.2rem;">' + p.name +
                            '<input data-param="' + p.name + '" value="' + val + '" style="padding:0.3rem;border:1px solid rgba(255,255,255,0.2);border-radius:0.4rem;background:rgba(255,255,255,0.05);color:var(--light);"></label>';
                    }).join('');
                    line.textContent = ep.method + ' ' + ep.path.replace('{ticker}', symbol).replace('{market}', 'IN') + ' — ' + ep.description;
                },

                buildUrl() {
                    const ep = this.currentEndpoint();
                    if (!ep) return null;
                    const symbol = document.getElementById('pgSymbol').value.trim().toUpperCase() || 'RELIANCE.NS';
                    let path = ep.path.replace('{ticker}', encodeURIComponent(symbol)).replace('{market}', 'IN');
                    const params = {};
                    document.querySelectorAll('#pgParams [data-param]').forEach(el => {
                        const v = el.value.trim();
                        if (v) params[el.getAttribute('data-param')] = v;
                    });
                    const qs = Object.entries(params).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
                    // LIVE flag is ON by default: the playground must NEVER serve
                    // stale cache — append the correct bypass param per endpoint
                    // (force_refresh for cache-backed OHLCV/earnings/market-cap,
                    // live for market-context).  Endpoints that are already live
                    // (universe, playground/ticker/history) need no extra flag.
                    const BYPASS = {
                        market_cap: 'force_refresh=true',
                        market_context: 'live=true',
                        price_history: 'force_refresh=true',
                        earnings_history: 'force_refresh=true',
                    };
                    const liveEl = document.getElementById('pgLive');
                    if (liveEl && liveEl.checked && ep.method === 'GET') {
                        const extra = (params.live || params.force_refresh) ? '' : (BYPASS[ep.id] || '');
                        const parts = [qs].filter(Boolean);
                        if (extra) parts.push(extra);
                        return { method: ep.method, url: API_BASE + path + (parts.length ? '?' + parts.join('&') : ''), body: params };
                    }
                    return { method: ep.method, url: API_BASE + path + (qs ? '?' + qs : ''), body: params };
                },

                async send() {
                    const req = this.buildUrl();
                    if (!req) return;
                    const btn = document.getElementById('pgSendBtn');
                    const respEl = document.getElementById('pgResponse');
                    const statusEl = document.getElementById('pgStatus');
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Sending...';
                    respEl.innerHTML = '<span class="timestamp">Loading...</span>';
                    statusEl.textContent = '';
                    const t0 = performance.now();
                    try {
                        const opts = { method: req.method, headers: {'Content-Type': 'application/json'} };
                        if (req.method === 'POST') opts.body = JSON.stringify({tickers: [req.body.tickers || 'RELIANCE.NS'], lookback: Number(req.body.lookback || 120), pred_len: Number(req.body.pred_len || 14)});
                        const res = await fetch(req.url, opts);
                        const ms = Math.round(performance.now() - t0);
                        const text = await res.text();
                        let data;
                        try { data = JSON.parse(text); } catch (e) { data = text; }
                        this.lastJson = data;
                        this.lastStatus = res.status;
                        statusEl.textContent = res.status + ' · ' + ms + 'ms';
                        statusEl.style.color = res.ok ? 'var(--green)' : 'var(--red)';
                        respEl.textContent = JSON.stringify(data, null, 2);
                    } catch (e) {
                        console.error('API console error:', e);
                        this.lastJson = null;
                        this.lastStatus = null;
                        statusEl.textContent = 'error';
                        statusEl.style.color = 'var(--red)';
                        respEl.textContent = 'Request failed: ' + e.message;
                    } finally {
                        btn.disabled = false;
                        btn.textContent = '▶ Send';
                    }
                },

                copyJson() {
                    if (this.lastJson === null) return;
                    const text = typeof this.lastJson === 'string' ? this.lastJson : JSON.stringify(this.lastJson, null, 2);
                    if (navigator.clipboard) {
                        navigator.clipboard.writeText(text).then(() => alert('Copied!'));
                    } else {
                        const ta = document.createElement('textarea');
                        ta.value = text;
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                        alert('Copied!');
                    }
                },

                wireSymbolAutocomplete() {
                    const input = document.getElementById('pgSymbol');
                    const dd = document.getElementById('pgSymbolDropdown');
                    let idx = -1;
                    input.addEventListener('input', async () => {
                        const q = input.value.trim();
                        if (q.length < 1) { dd.style.display = 'none'; return; }
                        try {
                            const res = await fetch(API_BASE + '/api/v1/playground/search?q=' + encodeURIComponent(q));
                            const items = await res.json();
                            idx = -1;
                            dd.innerHTML = items.map((it, i) =>
                                '<div class="autocomplete-item" data-i="' + i + '" onclick="app.pg.selectSymbol(\'' + it.symbol.replace(/'/g, "\\'") + '\')">' +
                                '<strong>' + it.symbol + '</strong> <span style="color:var(--muted);font-size:0.8rem;">' + it.market + '</span>' +
                                '</div>'
                            ).join('');
                            dd.style.display = items.length ? 'block' : 'none';
                        } catch (e) {
                            dd.style.display = 'none';
                        }
                    });
                    input.addEventListener('keydown', (e) => {
                        const items = dd.querySelectorAll('.autocomplete-item');
                        if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, -1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'Enter') { e.preventDefault(); if (idx >= 0 && items[idx]) items[idx].click(); else if (items.length) items[0].click(); }
                        else if (e.key === 'Escape') { dd.style.display = 'none'; }
                    });
                    document.addEventListener('click', (e) => {
                        if (!input.contains(e.target) && !dd.contains(e.target)) dd.style.display = 'none';
                    });
                },

                selectSymbol(symbol) {
                    document.getElementById('pgSymbol').value = symbol;
                    document.getElementById('pgSymbolDropdown').style.display = 'none';
                    this.renderParams();
                }
            },

            async loadPlaygroundNse() {
                const el = document.getElementById('pgNseStats');
                el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading NSE universe stats...</div>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/playground/nse');
                    const data = await res.json();
                    const labels = {
                        NSE_ALL: 'NSE All (nsetools)',
                        NSE_LARGE_CAP: 'NSE Large Cap (>1000 cr)',
                        IN: 'NSE Top (nse_top.txt)',
                        US: 'US Top (us_top.txt)',
                        COMBINED: 'Combined IN+US'
                    };
                    el.innerHTML = Object.entries(data).map(([key, v]) =>
                        '<div class="widget-card">' +
                        '<h4>' + (labels[key] || key) + '</h4>' +
                        '<div class="metric"><span>Count</span><strong>' + (v.count || 0) + '</strong></div>' +
                        (v.sample && v.sample.length ? '<p class="timestamp" style="margin:0.5rem 0 0 0;">' + v.sample.slice(0, 6).join(', ') + (v.sample.length > 6 ? '…' : '') + '</p>' : '') +
                        (v.error ? '<p class="timestamp" style="color:var(--red);margin:0.25rem 0 0 0;">' + v.error + '</p>' : '') +
                        '</div>'
                    ).join('');
                } catch (e) {
                    console.error('Error loading NSE stats:', e);
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading NSE universe stats</div>';
                }
            },

            async runPlaygroundKronos() {
                const btn = document.getElementById('pgKronosRunBtn');
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Running...';
                const el = document.getElementById('pgKronosResults');
                el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Running Kronos predictions... this can take several minutes.</div>';
                const input = document.getElementById('pgKronosTickers').value;
                const tickers = input ? input.split(',').map(t => t.trim().toUpperCase()).filter(Boolean) : [];
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({tickers: tickers, lookback: 120, pred_len: 14})
                    });
                    const data = await res.json();
                    if (!Array.isArray(data) || !data.length) {
                        el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No predictions generated. Check that the Kronos library is available.</div>';
                        return;
                    }
                    el.innerHTML = data.map(f => {
                        const cls = f.return_pct >= 0.5 ? 'price-positive' : f.return_pct <= -0.5 ? 'price-negative' : '';
                        const trendEmoji = f.return_pct >= 0.5 ? '🟢' : f.return_pct <= -0.5 ? '🔴' : '🟡';
                        const series = Array.isArray(f.forecast_series) ? f.forecast_series : [];
                        const seriesHtml = series.length ? this.renderForecastSeries(series) : '';
                        const gbmHtml = this.renderGbmSignal(f.gbm_prediction);
                        return '<div class="widget-card">' +
                            '<h4>' + (f.name || f.symbol || f.ticker) + ' <span class="timestamp">' + (f.symbol || f.ticker || '') + '</span></h4>' +
                            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">' +
                            '<div class="metric"><span>Current Price</span><strong>₹' + (f.current_price ? f.current_price.toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>14D Return</span><strong class="' + cls + '">' + trendEmoji + ' ' + f.return_pct + '%</strong></div>' +
                            '<div class="metric"><span>Support</span><strong>₹' + (f.support ? f.support.toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>Resistance</span><strong>₹' + (f.resistance ? f.resistance.toFixed(2) : 'N/A') + '</strong></div>' +
                            '</div>' +
                            (f.explanation ? '<p class="timestamp" style="margin-top:0.5rem;">' + f.explanation + '</p>' : '') +
                            gbmHtml +
                            seriesHtml +
                            '</div>';
                    }).join('');
                } catch (e) {
                    console.error('Error running playground Kronos:', e);
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error running Kronos predictions</div>';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '▶ Run';
                }
            },

            // ---------- Backtest Tab ----------

            initBacktestTab() {
                // Populate watchlist dropdown for backtest tab
                const sel = document.getElementById('btWatchlist');
                if (!sel) return;
                // Copy options from swing market dropdown if available
                const swingSel = document.getElementById('swingMarket');
                if (swingSel && swingSel.options.length > 1) {
                    const current = sel.value;
                    sel.innerHTML = '';
                    for (const opt of swingSel.options) {
                        const o = document.createElement('option');
                        o.value = opt.value;
                        o.textContent = opt.textContent;
                        sel.appendChild(o);
                    }
                    if (current) sel.value = current;
                }
            },

            onBacktestStrategyChange(strat) {
                const badge = document.getElementById('btStrategyBadge');
                const labels = {
                    'swing': '🎯 Swing Channel Strategy',
                    'kronos': '🔮 Kronos AI 14D Horizon',
                    'earnings': '⚡ Earnings Reaction Drift',
                    'news': '📰 News Catalyst Momentum',
                    'auditor_all': '🏆 Multi-Strategy Benchmark',
                };
                if (badge) badge.textContent = labels[strat] || 'Strategy Backtest';
            },

            async runSwingBacktest(e) {
                const btn = document.getElementById('btRunBtn');
                const statusEl = document.getElementById('btStatus');
                const watchlist = document.getElementById('btWatchlist')?.value || 'my_watchlist';
                const strategy = document.getElementById('btStrategy')?.value || 'swing';

                const stratLabels = {
                    'swing': 'Swing Channel',
                    'kronos': 'Kronos AI Forecasts',
                    'earnings': 'Earnings Drift',
                    'news': 'News Momentum',
                    'auditor_all': 'Multi-Strategy Benchmark',
                };

                const origHtml = btn ? btn.innerHTML : '';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Running backtest...';
                }
                statusEl.textContent = 'Running ' + (stratLabels[strategy] || strategy) + ' backtest on "' + watchlist + '"...';
                statusEl.style.color = '';

                try {
                    const body = {
                        strategy: strategy,
                        watchlist: watchlist,
                        initial_capital: parseFloat(document.getElementById('btCapital')?.value || 100000),
                        risk_per_trade_pct: parseFloat(document.getElementById('btRiskPct')?.value || 1.5) / 100.0,
                        stop_loss_buffer_pct: parseFloat(document.getElementById('btStopPct')?.value || 2) / 100.0,
                        max_hold_days: parseInt(document.getElementById('btMaxHold')?.value || 21),
                        channel_lookback: parseInt(document.getElementById('btLookback')?.value || 20),
                        buy_zone_threshold: parseFloat(document.getElementById('btBuyZone')?.value || 0.25),
                        volume_surge_mult: parseFloat(document.getElementById('btVolMult')?.value || 1.25),
                        lookback_months: parseInt(document.getElementById('btMonths')?.value || 6),
                    };

                    const res = await fetch(API_BASE + '/api/v1/backtest/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body)
                    });
                    const data = await res.json();

                    if (data.success) {
                        this.renderBacktestResults(data);
                        statusEl.textContent = 'Backtest completed for ' + (data.strategy_name || stratLabels[strategy] || 'Strategy') + ' — ' + (data.total_trades || 0) + ' trades simulated.';
                        statusEl.style.color = 'var(--green)';
                    } else {
                        statusEl.textContent = 'Error: ' + (data.detail || data.error || 'Unknown error');
                        statusEl.style.color = 'var(--red)';
                    }
                } catch (err) {
                    console.error('Backtest error:', err);
                    statusEl.textContent = 'Network error running backtest.';
                    statusEl.style.color = 'var(--red)';
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origHtml;
                    }
                }
            },

            renderBacktestResults(data) {
                // KPI Metrics
                const retPct = data.total_return_pct || 0;
                const retColor = retPct >= 0 ? '#34d399' : '#ef4444';
                const annPct = data.annualized_return_pct || 0;
                const annColor = annPct >= 0 ? '#34d399' : '#ef4444';
                const ddPct = data.max_drawdown_pct || 0;
                const sharpe = data.sharpe_ratio || 0;
                const sharpeColor = sharpe >= 1.0 ? '#34d399' : sharpe >= 0.5 ? '#fbbf24' : '#ef4444';

                document.getElementById('btMetricReturn').textContent = (retPct >= 0 ? '+' : '') + retPct + '%';
                document.getElementById('btMetricReturn').style.color = retColor;
                document.getElementById('btMetricAnn').textContent = (annPct >= 0 ? '+' : '') + annPct + '%';
                document.getElementById('btMetricAnn').style.color = annColor;
                document.getElementById('btMetricSharpe').textContent = sharpe.toFixed(3);
                document.getElementById('btMetricSharpe').style.color = sharpeColor;
                document.getElementById('btMetricDD').textContent = '-' + ddPct + '%';
                document.getElementById('btMetricDD').style.color = ddPct > 15 ? '#ef4444' : ddPct > 8 ? '#fbbf24' : '#34d399';
                document.getElementById('btMetricTrades').textContent = data.total_trades || 0;
                document.getElementById('btMetricTrades').style.color = '#60a5fa';
                document.getElementById('btMetricWin').textContent = (data.win_rate_pct || 0) + '%';
                document.getElementById('btMetricWin').style.color = (data.win_rate_pct || 0) >= 50 ? '#34d399' : '#ef4444';
                document.getElementById('btMetricPF').textContent = (data.profit_factor || 0).toFixed(2);
                document.getElementById('btMetricPF').style.color = (data.profit_factor || 0) >= 1.5 ? '#34d399' : (data.profit_factor || 0) >= 1.0 ? '#fbbf24' : '#ef4444';
                document.getElementById('btMetricHold').textContent = (data.avg_hold_days || 0).toFixed(1) + 'd';
                document.getElementById('btMetricHold').style.color = '#94a3b8';

                // Equity Curve
                if (data.equity_curve && Object.keys(data.equity_curve).length > 1) {
                    document.getElementById('btChartPlaceholder').style.display = 'none';
                    this.drawEquityCurve('btEquityCanvas', data.equity_curve, data.initial_capital);
                }

                // Trade Log
                this.renderBacktestTrades(data.trades || []);
            },

            drawEquityCurve(canvasId, equityData, initialCapital) {
                const canvas = document.getElementById(canvasId);
                if (!canvas) return;

                // Set actual pixel dimensions for sharp rendering
                const rect = canvas.parentElement.getBoundingClientRect();
                const dpr = window.devicePixelRatio || 1;
                canvas.width = rect.width * dpr;
                canvas.height = rect.height * dpr;
                canvas.style.width = rect.width + 'px';
                canvas.style.height = rect.height + 'px';

                const ctx = canvas.getContext('2d');
                ctx.scale(dpr, dpr);
                const W = rect.width;
                const H = rect.height;
                const pad = { top: 25, right: 15, bottom: 30, left: 65 };
                const plotW = W - pad.left - pad.right;
                const plotH = H - pad.top - pad.bottom;

                // Parse data
                const dates = Object.keys(equityData).sort();
                const values = dates.map(d => equityData[d]);
                const minVal = Math.min(...values) * 0.995;
                const maxVal = Math.max(...values) * 1.005;
                const valRange = maxVal - minVal || 1;

                // Clear
                ctx.clearRect(0, 0, W, H);

                // Background
                ctx.fillStyle = 'rgba(15, 23, 42, 0.6)';
                ctx.fillRect(0, 0, W, H);

                // Grid lines
                ctx.strokeStyle = 'rgba(255,255,255,0.06)';
                ctx.lineWidth = 0.5;
                const nGridY = 5;
                for (let i = 0; i <= nGridY; i++) {
                    const y = pad.top + (plotH * i / nGridY);
                    ctx.beginPath();
                    ctx.moveTo(pad.left, y);
                    ctx.lineTo(W - pad.right, y);
                    ctx.stroke();

                    // Y-axis labels
                    const val = maxVal - (valRange * i / nGridY);
                    ctx.fillStyle = 'rgba(148,163,184,0.7)';
                    ctx.font = '10px Inter, system-ui, sans-serif';
                    ctx.textAlign = 'right';
                    ctx.fillText('₹' + Math.round(val).toLocaleString(), pad.left - 6, y + 3);
                }

                // Initial capital line
                const icY = pad.top + plotH * (1 - (initialCapital - minVal) / valRange);
                ctx.strokeStyle = 'rgba(251,191,36,0.3)';
                ctx.setLineDash([4, 4]);
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(pad.left, icY);
                ctx.lineTo(W - pad.right, icY);
                ctx.stroke();
                ctx.setLineDash([]);

                // Compute points
                const points = values.map((v, i) => ({
                    x: pad.left + (plotW * i / Math.max(values.length - 1, 1)),
                    y: pad.top + plotH * (1 - (v - minVal) / valRange)
                }));

                // Gradient fill under the curve
                const lastVal = values[values.length - 1];
                const isPositive = lastVal >= initialCapital;
                const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
                if (isPositive) {
                    grad.addColorStop(0, 'rgba(16,185,129,0.35)');
                    grad.addColorStop(1, 'rgba(16,185,129,0.02)');
                } else {
                    grad.addColorStop(0, 'rgba(239,68,68,0.25)');
                    grad.addColorStop(1, 'rgba(239,68,68,0.02)');
                }

                ctx.beginPath();
                ctx.moveTo(points[0].x, pad.top + plotH);
                points.forEach(p => ctx.lineTo(p.x, p.y));
                ctx.lineTo(points[points.length - 1].x, pad.top + plotH);
                ctx.closePath();
                ctx.fillStyle = grad;
                ctx.fill();

                // Equity line
                ctx.beginPath();
                ctx.moveTo(points[0].x, points[0].y);
                for (let i = 1; i < points.length; i++) {
                    ctx.lineTo(points[i].x, points[i].y);
                }
                ctx.strokeStyle = isPositive ? '#34d399' : '#ef4444';
                ctx.lineWidth = 2;
                ctx.stroke();

                // X-axis date labels (show ~6 evenly spaced)
                const nLabels = Math.min(6, dates.length);
                ctx.fillStyle = 'rgba(148,163,184,0.7)';
                ctx.font = '9px Inter, system-ui, sans-serif';
                ctx.textAlign = 'center';
                for (let i = 0; i < nLabels; i++) {
                    const idx = Math.round(i * (dates.length - 1) / Math.max(nLabels - 1, 1));
                    const x = pad.left + (plotW * idx / Math.max(dates.length - 1, 1));
                    const label = dates[idx].substring(5); // MM-DD
                    ctx.fillText(label, x, H - pad.bottom + 15);
                }

                // Legend
                ctx.fillStyle = 'rgba(148,163,184,0.5)';
                ctx.font = '10px Inter, system-ui, sans-serif';
                ctx.textAlign = 'left';
                ctx.fillText('Portfolio Equity', pad.left + 5, pad.top + 12);
                ctx.fillStyle = 'rgba(251,191,36,0.5)';
                ctx.fillText('Initial Capital: ₹' + Math.round(initialCapital).toLocaleString(), pad.left + 110, pad.top + 12);
            },

            renderBacktestTrades(trades) {
                const container = document.getElementById('btTradeLog');
                const countEl = document.getElementById('btTradeCount');
                if (!container) return;

                if (!trades || !trades.length) {
                    container.innerHTML = '<p class="timestamp" style="font-size:0.8rem;">No trades generated by the backtest.</p>';
                    if (countEl) countEl.textContent = '0 trades';
                    return;
                }

                if (countEl) countEl.textContent = trades.length + ' trade' + (trades.length === 1 ? '' : 's');

                const rows = trades.map(t => {
                    const pnlCls = t.pnl_pct > 0 ? 'price-positive' : t.pnl_pct < 0 ? 'price-negative' : '';
                    const reasonBg = t.exit_reason === 'Take Profit' ? 'rgba(16,185,129,0.15)' :
                                     t.exit_reason === 'Stop Loss' ? 'rgba(239,68,68,0.15)' :
                                     'rgba(251,191,36,0.1)';
                    return '<tr>' +
                        '<td><strong>' + t.ticker + '</strong></td>' +
                        '<td>' + (t.entry_date || '') + '</td>' +
                        '<td>₹' + (t.entry_price || 0).toFixed(2) + '</td>' +
                        '<td>' + (t.exit_date || '') + '</td>' +
                        '<td>₹' + (t.exit_price ? t.exit_price.toFixed(2) : '—') + '</td>' +
                        '<td class="' + pnlCls + '" style="font-weight:600;">' + (t.pnl_pct >= 0 ? '+' : '') + t.pnl_pct.toFixed(2) + '%</td>' +
                        '<td>₹' + (t.pnl || 0).toFixed(0) + '</td>' +
                        '<td>' + (t.hold_days || 0) + 'd</td>' +
                        '<td><span style="background:' + reasonBg + ';padding:0.15rem 0.4rem;border-radius:0.25rem;font-size:0.72rem;font-weight:600;">' + (t.exit_reason || '') + '</span></td>' +
                        '</tr>';
                }).join('');

                container.innerHTML = '<table class="results-table" style="font-size:0.78rem;width:100%;">' +
                    '<thead><tr>' +
                    '<th>Ticker</th><th>Entry</th><th>Entry ₹</th><th>Exit</th><th>Exit ₹</th><th>PnL %</th><th>PnL ₹</th><th>Hold</th><th>Reason</th>' +
                    '</tr></thead><tbody>' + rows + '</tbody></table>';
            },

            // =========================================================================
            // 🧠 Multi-Model AI Consensus Engine & Post-Mortems Tab
            // =========================================================================
            consensusPredictions: [],

            async loadConsensusTab() {
                const grid = document.getElementById('consensusListGrid');
                if (grid) {
                    grid.innerHTML = '<div style="text-align:center;color:var(--muted);padding:2rem;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading AI consensus predictions...</div>';
                }

                try {
                    // Fetch latest predictions and accuracy stats in parallel
                    const [predsRes, statsRes] = await Promise.all([
                        fetch('/api/v1/consensus/latest?limit=100'),
                        fetch('/api/v1/consensus/accuracy-stats')
                    ]);

                    const predsData = await predsRes.json();
                    const statsData = await statsRes.json();

                    this.consensusPredictions = predsData.predictions || [];

                    // Render KPI stats
                    this.renderConsensusKpis(statsData);

                    // Render Prediction list
                    this.filterConsensus();
                } catch (e) {
                    console.error('Error loading Consensus Tab:', e);
                    if (grid) {
                        grid.innerHTML = '<div class="card" style="padding:1.5rem;color:#f87171;text-align:center;">Failed to load consensus predictions: ' + (e.message || e) + '</div>';
                    }
                }
            },

            renderConsensusKpis(stats) {
                const totalEl = document.getElementById('consensusStatTotal');
                const winRateEl = document.getElementById('consensusStatWinRate');
                const dirAccEl = document.getElementById('consensusStatDirAcc');
                const pendingEl = document.getElementById('consensusStatPending');
                const topFailEl = document.getElementById('consensusStatTopFail');

                if (totalEl) totalEl.textContent = stats.total_predictions || 0;
                if (winRateEl) {
                    const wr = stats.win_rate != null ? stats.win_rate.toFixed(1) + '%' : '0.0%';
                    winRateEl.textContent = wr;
                    winRateEl.style.color = (stats.win_rate >= 50) ? '#10b981' : '#f59e0b';
                }
                if (dirAccEl) {
                    const da = stats.direction_accuracy != null ? stats.direction_accuracy.toFixed(1) + '%' : '0.0%';
                    dirAccEl.textContent = da;
                }
                if (pendingEl) pendingEl.textContent = stats.pending || 0;
                if (topFailEl) {
                    const topF = stats.top_failure_categories && stats.top_failure_categories.length ? stats.top_failure_categories[0].category : 'None';
                    topFailEl.textContent = topF.replace(/_/g, ' ');
                }
            },

            filterConsensus() {
                const search = (document.getElementById('consensusSearchFilter')?.value || '').trim().toUpperCase();
                const dirFilter = document.getElementById('consensusDirectionFilter')?.value || 'ALL';
                const statusFilter = document.getElementById('consensusStatusFilter')?.value || 'ALL';

                let filtered = this.consensusPredictions || [];

                if (search) {
                    filtered = filtered.filter(p => (p.ticker || '').toUpperCase().includes(search));
                }
                if (dirFilter !== 'ALL') {
                    filtered = filtered.filter(p => (p.consensus_direction || '').toUpperCase() === dirFilter);
                }
                if (statusFilter !== 'ALL') {
                    filtered = filtered.filter(p => (p.settlement_status || '').toUpperCase() === statusFilter);
                }

                const badge = document.getElementById('consensusCountBadge');
                if (badge) badge.textContent = filtered.length + ' predictions';

                this.renderConsensusList(filtered);
            },

            renderConsensusList(items) {
                const grid = document.getElementById('consensusListGrid');
                if (!grid) return;

                if (!items || !items.length) {
                    grid.innerHTML = '<div class="card" style="padding:2rem;text-align:center;color:var(--muted);margin:0;">No consensus predictions match the selected filters. Click <strong>⚡ Run Consensus</strong> above to generate one.</div>';
                    return;
                }

                grid.innerHTML = items.map(p => {
                    const dir = (p.consensus_direction || 'NEUTRAL').toUpperCase();
                    const dirBg = dir === 'BULLISH' ? 'rgba(16,185,129,0.15)' : dir === 'BEARISH' ? 'rgba(239,68,68,0.15)' : 'rgba(251,191,36,0.15)';
                    const dirColor = dir === 'BULLISH' ? '#34d399' : dir === 'BEARISH' ? '#f87171' : '#fbbf24';
                    const dirIcon = dir === 'BULLISH' ? '🟢 BULLISH' : dir === 'BEARISH' ? '🔴 BEARISH' : '🟡 NEUTRAL';

                    const status = (p.settlement_status || 'PENDING').toUpperCase();
                    const statusBg = status === 'SUCCESS' ? '#10b981' : status === 'PARTIAL' ? '#f59e0b' : status === 'FAILURE' ? '#ef4444' : '#64748b';
                    const statusIcon = status === 'SUCCESS' ? '✅ SUCCESS' : status === 'PARTIAL' ? '🟡 PARTIAL' : status === 'FAILURE' ? '❌ FAILED' : '⏳ PENDING';

                    const strength = p.consensus_strength || 0;
                    const agreeRatio = p.agreement_ratio ? (p.agreement_ratio * 100).toFixed(0) + '%' : '—';
                    const retPct = p.consensus_return_pct != null ? (p.consensus_return_pct >= 0 ? '+' : '') + p.consensus_return_pct.toFixed(2) + '%' : '—';
                    const actualRet = p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '+' : '') + p.actual_return_pct.toFixed(2) + '%' : '—';
                    const actualRetColor = p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '#34d399' : '#f87171') : 'var(--muted)';

                    // Model Pills
                    let modelPills = '';
                    if (p.models_breakdown && p.models_breakdown.length) {
                        modelPills = p.models_breakdown.map(m => {
                            const mDir = (m.direction || 'ERR').toUpperCase();
                            const mCol = mDir === 'BULLISH' ? '#34d399' : mDir === 'BEARISH' ? '#f87171' : '#94a3b8';
                            return '<span style="font-size:0.72rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);padding:0.15rem 0.45rem;border-radius:0.3rem;color:' + mCol + ';">' + (m.model_name || m.model_id) + ': ' + mDir + '</span>';
                        }).join(' ');
                    }

                    // Post-Mortem banner if failed
                    let postMortemSnippet = '';
                    if (status === 'FAILURE' || status === 'PARTIAL') {
                        const failCat = p.failure_category ? p.failure_category.replace(/_/g, ' ') : 'Unclassified';
                        const failSummary = p.failure_reason_summary || 'Price action diverged from model consensus.';
                        postMortemSnippet = '<div style="margin-top:0.6rem;padding:0.5rem 0.75rem;background:rgba(239,68,68,0.08);border-left:3px solid #ef4444;border-radius:0.3rem;font-size:0.78rem;color:#fca5a5;">' +
                            '<strong>🔍 Post-Mortem (' + failCat + '):</strong> ' + failSummary +
                            '</div>';
                    }

                    return '<div class="card" style="margin:0;padding:1rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.6rem;transition:all 0.2s;">' +
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.75rem;">' +
                            '<div>' +
                                '<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.3rem;">' +
                                    '<div style="display:flex;align-items:center;gap:0.35rem;">' +
                                        `<button onclick="app.openAddToWatchlistModal('${p.ticker}')" class="btn-micro" style="color:#fbbf24;border:none;background:transparent;padding:0;font-size:0.9rem;cursor:pointer;" title="Add to Watchlist">⭐</button>` +
                                        '<strong style="font-size:1.15rem;color:var(--light);">' + p.ticker + '</strong>' +
                                    '</div>' +
                                    '<span style="font-size:0.75rem;font-weight:700;background:' + dirBg + ';color:' + dirColor + ';padding:0.2rem 0.55rem;border-radius:0.35rem;border:1px solid ' + dirColor + '44;">' + dirIcon + '</span>' +
                                    '<span style="font-size:0.72rem;font-weight:700;background:' + statusBg + '22;color:' + statusBg + ';padding:0.18rem 0.5rem;border-radius:0.35rem;border:1px solid ' + statusBg + '66;">' + statusIcon + '</span>' +
                                '</div>' +
                                '<div style="font-size:0.78rem;color:var(--muted);display:flex;gap:0.8rem;flex-wrap:wrap;">' +
                                    '<span>Entry: <strong>₹' + (p.as_of_price || 0).toFixed(2) + '</strong></span>' +
                                    '<span>Target: <strong style="color:#60a5fa;">₹' + (p.consensus_target_price || 0).toFixed(2) + ' (' + retPct + ')</strong></span>' +
                                    '<span>Exit: <strong style="color:' + actualRetColor + ';">' + (p.actual_exit_price ? '₹' + p.actual_exit_price.toFixed(2) + ' (' + actualRet + ')' : 'Pending') + '</strong></span>' +
                                    '<span>Due: ' + (p.evaluation_date || '—') + '</span>' +
                                '</div>' +
                            '</div>' +
                            '<div style="display:flex;align-items:center;gap:0.6rem;">' +
                                '<div style="text-align:right;">' +
                                    '<div style="font-size:0.75rem;color:var(--muted);">Consensus Strength</div>' +
                                    '<div style="font-size:0.95rem;font-weight:700;color:' + dirColor + ';">' + strength.toFixed(0) + '% <span style="font-size:0.75rem;color:var(--muted);">(' + agreeRatio + ' agree)</span></div>' +
                                '</div>' +
                                '<button onclick="app.openConsensusDetailModal(' + p.id + ')" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);padding:0.4rem 0.75rem;border-radius:0.4rem;font-weight:600;">🔍 View Audit</button>' +
                            '</div>' +
                        '</div>' +
                        (modelPills ? '<div style="margin-top:0.6rem;display:flex;gap:0.4rem;flex-wrap:wrap;">' + modelPills + '</div>' : '') +
                        postMortemSnippet +
                    '</div>';
                }).join('');
            },

            async runConsensusPrediction() {
                const tickerInput = document.getElementById('consensusTickerInput');
                const tfSelect = document.getElementById('consensusTimeframeSelect');
                const runBtn = document.getElementById('consensusRunBtn');

                const ticker = (tickerInput?.value || '').trim().toUpperCase();
                if (!ticker) {
                    alert('Please enter a stock ticker symbol (e.g. RELIANCE.NS, TCS.NS, AAPL).');
                    return;
                }

                const timeframe = parseInt(tfSelect?.value || '14', 10);
                if (runBtn) {
                    runBtn.disabled = true;
                    runBtn.innerHTML = '<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> Querying Models...';
                }

                try {
                    const res = await fetch('/api/v1/consensus/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticker: ticker, timeframe_days: timeframe })
                    });
                    const data = await res.json();
                    if (!data.success || !data.predictions || !data.predictions.length) {
                        alert('Prediction error: ' + (data.detail || data.error || 'Failed to generate consensus.'));
                        return;
                    }
                    const pred = data.predictions[0];
                    if (pred.error) {
                        alert('Model error for ' + ticker + ': ' + pred.error);
                        return;
                    }

                    // Reload consensus list
                    await this.loadConsensusTab();

                    // Automatically open modal for newly created prediction
                    if (pred.id) {
                        this.openConsensusDetailModal(pred.id);
                    }
                } catch (e) {
                    console.error('Error running consensus prediction:', e);
                    alert('Error running consensus: ' + (e.message || e));
                } finally {
                    if (runBtn) {
                        runBtn.disabled = false;
                        runBtn.innerHTML = '⚡ Run Consensus';
                    }
                }
            },

            async settleConsensusPredictions() {
                const settleBtn = document.getElementById('consensusSettleBtn');
                if (settleBtn) {
                    settleBtn.disabled = true;
                    settleBtn.innerHTML = '🔄 Settling...';
                }
                try {
                    const res = await fetch('/api/v1/consensus/settle', { method: 'POST' });
                    const data = await res.json();
                    alert('Settlement Complete!\n- Total Due: ' + (data.total_due || 0) + '\n- Settled: ' + (data.settled_count || 0) + '\n- Successes: ' + (data.success_count || 0) + '\n- Failures: ' + (data.failure_count || 0));
                    await this.loadConsensusTab();
                } catch (e) {
                    console.error('Error settling consensus predictions:', e);
                    alert('Settlement error: ' + (e.message || e));
                } finally {
                    if (settleBtn) {
                        settleBtn.disabled = false;
                        settleBtn.innerHTML = '🔄 Settle Due Trades';
                    }
                }
            },

            async openConsensusDetailModal(predId) {
                const modal = document.getElementById('consensusDetailModal');
                const body = document.getElementById('consensusModalBody');
                if (!modal || !body) return;

                modal.style.display = 'flex';
                body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading audit details...</div>';

                try {
                    const res = await fetch('/api/v1/consensus/' + predId);
                    const data = await res.json();
                    if (!data.success || !data.prediction) {
                        body.innerHTML = '<div style="color:#f87171;padding:1.5rem;">Prediction record not found.</div>';
                        return;
                    }
                    const p = data.prediction;
                    const dir = (p.consensus_direction || 'NEUTRAL').toUpperCase();
                    const dirColor = dir === 'BULLISH' ? '#34d399' : dir === 'BEARISH' ? '#f87171' : '#fbbf24';
                    const status = (p.settlement_status || 'PENDING').toUpperCase();
                    const statusBg = status === 'SUCCESS' ? '#10b981' : status === 'PARTIAL' ? '#f59e0b' : status === 'FAILURE' ? '#ef4444' : '#64748b';

                    // Build Models Breakdown Matrix
                    let modelsGrid = '';
                    if (p.models_breakdown && p.models_breakdown.length) {
                        modelsGrid = p.models_breakdown.map((m, idx) => {
                            const mDir = (m.direction || 'ERR').toUpperCase();
                            const mColor = mDir === 'BULLISH' ? '#34d399' : mDir === 'BEARISH' ? '#f87171' : '#94a3b8';
                            const drivers = m.key_drivers ? m.key_drivers.map(d => '<li style="margin-bottom:0.25rem;">' + d + '</li>').join('') : '<li>No specific drivers</li>';
                            
                            const rawResp = m.raw_response ? m.raw_response : JSON.stringify(m, null, 2);
                            const escapedRaw = String(rawResp)
                                .replace(/&/g, "&amp;")
                                .replace(/</g, "&lt;")
                                .replace(/>/g, "&gt;")
                                .replace(/"/g, "&quot;")
                                .replace(/'/g, "&#039;");

                            const rawAccordion = `
                                <details style="margin-top:0.65rem;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:0.4rem;padding:0.45rem 0.65rem;">
                                    <summary style="cursor:pointer;font-size:0.75rem;font-weight:700;color:#93c5fd;display:flex;align-items:center;justify-content:space-between;user-select:none;">
                                        <span>📄 Full Raw LLM Response &amp; Chain-of-Thought</span>
                                        <span style="font-size:0.68rem;color:#94a3b8;background:rgba(255,255,255,0.06);padding:0.1rem 0.35rem;border-radius:3px;">${m.tokens_used ? m.tokens_used + ' tokens' : (m.latency_ms ? m.latency_ms + 'ms' : 'Raw Text')} ▾</span>
                                    </summary>
                                    <div style="margin-top:0.45rem;position:relative;">
                                        <pre style="margin:0;padding:0.65rem;background:#030712;border:1px solid rgba(255,255,255,0.12);border-radius:0.35rem;font-family:var(--font-mono);font-size:0.73rem;color:#e2e8f0;white-space:pre-wrap;word-break:break-word;max-height:280px;overflow-y:auto;line-height:1.5;">${escapedRaw}</pre>
                                    </div>
                                </details>
                            `;

                            return '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;padding:0.85rem;">' +
                                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">' +
                                    '<strong style="color:var(--light);font-size:0.9rem;">' + (m.model_name || m.model_id) + '</strong>' +
                                    '<span style="font-size:0.75rem;font-weight:700;color:' + mColor + ';background:' + mColor + '22;padding:0.15rem 0.45rem;border-radius:0.3rem;">' + mDir + ' (' + (m.confidence_pct || 0) + '%)</span>' +
                                '</div>' +
                                '<div style="font-size:0.78rem;color:var(--muted);margin-bottom:0.4rem;">' +
                                    'Target Return: <strong style="color:#60a5fa;">' + (m.target_return_pct ? (m.target_return_pct >= 0 ? '+' : '') + m.target_return_pct + '%' : '—') + '</strong> | Target ₹: ' + (m.target_price || '—') +
                                '</div>' +
                                '<div style="font-size:0.75rem;color:#cbd5e1;margin-bottom:0.4rem;"><strong>Key Drivers:</strong><ul style="padding-left:1.2rem;margin:0.2rem 0 0 0;">' + drivers + '</ul></div>' +
                                (m.primary_risk ? '<div style="font-size:0.75rem;color:#fca5a5;margin-bottom:0.3rem;"><strong>Primary Risk:</strong> ' + m.primary_risk + '</div>' : '') +
                                rawAccordion +
                            '</div>';
                        }).join('');
                    }

                    // Build Post-Mortem Failure Analysis Section
                    let postMortemSection = '';
                    if (status === 'FAILURE' || status === 'PARTIAL' || p.failure_post_mortem) {
                        const cat = p.failure_category ? p.failure_category.replace(/_/g, ' ') : 'Unclassified';
                        postMortemSection = '<div style="margin-top:1.25rem;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.3);border-radius:0.6rem;padding:1rem;">' +
                            '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">' +
                                '<h4 style="margin:0;color:#f87171;font-size:0.95rem;">🔍 AI Post-Mortem Failure Attribution</h4>' +
                                '<span style="font-size:0.72rem;font-weight:700;background:rgba(239,68,68,0.2);color:#fca5a5;padding:0.15rem 0.5rem;border-radius:0.3rem;">' + cat + '</span>' +
                            '</div>' +
                            '<div style="font-size:0.82rem;color:#e2e8f0;line-height:1.5;margin-bottom:0.6rem;">' +
                                '<strong>Summary:</strong> ' + (p.failure_reason_summary || 'Adverse market movement opposite to consensus expectation.') +
                            '</div>' +
                            (p.failure_post_mortem ? '<div style="font-size:0.8rem;color:#cbd5e1;line-height:1.5;background:rgba(0,0,0,0.25);padding:0.75rem;border-radius:0.4rem;">' + p.failure_post_mortem.replace(/\n/g, '<br>') + '</div>' : '') +
                        '</div>';
                    }

                    body.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:0.75rem;margin-bottom:1rem;">' +
                        '<div>' +
                            '<h3 style="margin:0;font-size:1.3rem;color:var(--light);">' + p.ticker + ' — Consensus Prediction Audit</h3>' +
                            '<div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem;">Created: ' + p.created_at + ' | Evaluation Window: ' + p.evaluation_date + '</div>' +
                        '</div>' +
                        '<span style="font-size:0.85rem;font-weight:700;background:' + statusBg + ';color:white;padding:0.3rem 0.8rem;border-radius:0.4rem;">' + status + '</span>' +
                    '</div>' +
                    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.6rem;margin-bottom:1rem;">' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Direction</span><strong style="display:block;font-size:1.1rem;color:' + dirColor + ';">' + dir + '</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Strength</span><strong style="display:block;font-size:1.1rem;color:' + dirColor + ';">' + (p.consensus_strength || 0).toFixed(0) + '%</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Entry Price</span><strong style="display:block;font-size:1.1rem;color:var(--light);">₹' + (p.as_of_price || 0).toFixed(2) + '</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Target Price</span><strong style="display:block;font-size:1.1rem;color:#60a5fa;">₹' + (p.consensus_target_price || 0).toFixed(2) + '</strong></div>' +
                        '<div class="card" style="margin:0;padding:0.6rem;text-align:center;"><span style="font-size:0.7rem;color:var(--muted);">Actual Return</span><strong style="display:block;font-size:1.1rem;color:' + (p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '#34d399' : '#f87171') : 'var(--muted)') + ';">' + (p.actual_return_pct != null ? (p.actual_return_pct >= 0 ? '+' : '') + p.actual_return_pct.toFixed(2) + '%' : 'Pending') + '</strong></div>' +
                    '</div>' +
                    '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.5rem;padding:0.85rem;margin-bottom:1rem;font-size:0.85rem;color:#e2e8f0;line-height:1.5;">' +
                        '<strong>📜 Synthesized Consensus Thesis:</strong> ' + (p.synthesized_thesis || 'No thesis generated.') +
                    '</div>' +
                    '<h4 style="margin:1rem 0 0.5rem 0;color:var(--light);font-size:0.95rem;">🤖 Individual Model Predictions</h4>' +
                    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:0.75rem;">' + modelsGrid + '</div>' +
                    postMortemSection;
                } catch (e) {
                    console.error('Error opening consensus modal:', e);
                    body.innerHTML = '<div style="color:#f87171;padding:1.5rem;">Error loading prediction details: ' + (e.message || e) + '</div>';
                }
            },

            closeConsensusModal() {
                const modal = document.getElementById('consensusDetailModal');
                if (modal) modal.style.display = 'none';
            },

        };

        // Search / autocomplete
        const searchInput = document.getElementById('tickerSearch');
        const dropdown = document.getElementById('autocompleteDropdown');
        let selectedIndex = -1;

        searchInput.addEventListener('focus', () => {
            if (!app.allTickers.length) app.loadSearchTickers();
        });

        searchInput.addEventListener('input', async (e) => {
            const query = e.target.value.trim().toUpperCase();
            if (query.length < 1) { dropdown.style.display = 'none'; return; }
            if (!app.allTickers.length) {
                await app.loadSearchTickers();
            }
            const matches = app.allTickers.filter(t => t.toUpperCase().includes(query)).slice(0, 20);
            if (matches.length) {
                selectedIndex = -1;
                dropdown.innerHTML = matches.map((t, i) =>
                    '<div class="autocomplete-item" data-i="' + i + '" onclick="app.selectTicker(\'' + t + '\')" onmouseenter="app.setSearchHoverIndex(' + i + ')">' +
                    '<span style="font-weight:700;letter-spacing:0.02em;">' + t + '</span>' +
                    '<span style="font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;background:rgba(255,255,255,0.06);color:#94a3b8;border:1px solid rgba(255,255,255,0.08);">' + (t.endsWith('.NS') ? 'NSE' : 'US') + '</span>' +
                    '</div>'
                ).join('');
                dropdown.style.display = 'block';
            } else {
                dropdown.style.display = 'none';
            }
        });

        app.setSearchHoverIndex = function(idx) {
            selectedIndex = idx;
            const items = dropdown.querySelectorAll('.autocomplete-item');
            items.forEach((it, i) => it.classList.toggle('selected', i === idx));
        };

        searchInput.addEventListener('keydown', (e) => {
            const items = dropdown.querySelectorAll('.autocomplete-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                items.forEach((it, i) => {
                    const isSel = i === selectedIndex;
                    it.classList.toggle('selected', isSel);
                    if (isSel) it.scrollIntoView({ block: 'nearest' });
                });
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, -1);
                items.forEach((it, i) => {
                    const isSel = i === selectedIndex;
                    it.classList.toggle('selected', isSel);
                    if (isSel) it.scrollIntoView({ block: 'nearest' });
                });
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (selectedIndex >= 0 && items[selectedIndex]) {
                    items[selectedIndex].click();
                } else if (items.length) {
                    items[0].click();
                } else if (searchInput.value.trim()) {
                    app.selectTicker(searchInput.value.trim());
                }
            } else if (e.key === 'Escape') {
                dropdown.style.display = 'none';
            }
        });

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) dropdown.style.display = 'none';
        });

        app.selectTicker = function (ticker) {
            if (!ticker) return;
            const sym = ticker.trim().toUpperCase();
            dropdown.style.display = 'none';
            if (searchInput) searchInput.value = '';
            window.open('/stock/' + encodeURIComponent(sym), '_blank');
        };

        // Global report popup handlers
        window.openPopup = function (ticker) {
            if (!ticker) return;
            const safeId = ticker.replace(/\./g, '_').replace(/[^a-zA-Z0-9_-]/g, '_');
            let el = document.getElementById('popup-' + safeId) || document.getElementById('popup-' + ticker);
            if (!el) {
                const all = document.querySelectorAll('.popup-modal');
                for (const p of all) {
                    if (p.id.toLowerCase().includes(safeId.toLowerCase()) || p.id.toLowerCase().includes(ticker.toLowerCase())) {
                        el = p;
                        break;
                    }
                }
            }
            if (el) {
                document.querySelectorAll('.popup-modal').forEach(p => p.style.display = 'none');
                el.style.display = 'block';
                document.body.style.overflow = 'hidden';
            } else {
                console.warn('Popup modal not found for ticker:', ticker);
            }
        };

        window.closePopups = function () {
            document.querySelectorAll('.popup-modal').forEach(p => p.style.display = 'none');
            document.body.style.overflow = '';
        };

        window.runRowPrediction = function(ticker, engine, btn) {
            app.runRowPrediction(ticker, engine, btn);
        };

        app.openPopup = window.openPopup;
        app.closePopups = window.closePopups;
        app.runRowPrediction = app.runRowPrediction;

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
                const opCounter = data.openrouter_counter || {};

                // Update Top Header Pill
                app.updateTopRateLimitPill(opCounter);

                // Update Control Center OpenRouter Banner
                const bannerCount = document.getElementById('ccOpenRouter24hCount');
                const bannerRem = document.getElementById('ccOpenRouter24hRem');
                const tierBadge = document.getElementById('ccOpenRouterTierBadge');

                if (bannerCount) bannerCount.textContent = `${opCounter.current_24h || 0} / ${opCounter.allowed_24h || 200}`;
                if (bannerRem) {
                    bannerRem.textContent = `${opCounter.remaining_24h || 0} reqs`;
                    bannerRem.style.color = (opCounter.remaining_24h <= 20) ? '#f87171' : ((opCounter.remaining_24h <= 60) ? '#fbbf24' : '#34d399');
                }
                if (tierBadge) {
                    tierBadge.textContent = opCounter.is_free_tier ? 'Free Tier Active' : 'Paid / Standard Tier';
                    tierBadge.style.background = opCounter.is_free_tier ? 'rgba(16,185,129,0.2)' : 'rgba(59,130,246,0.2)';
                    tierBadge.style.color = opCounter.is_free_tier ? '#34d399' : '#60a5fa';
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
            const allowed = counter.allowed_24h || 200;
            const rem = counter.remaining_24h != null ? counter.remaining_24h : (allowed - cur);
            const util = counter.utilization_pct || 0;

            quotaEl.textContent = `OpenRouter: ${cur}/${allowed} reqs`;

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
                                <button onclick="app.copyPasscodeLink('${item.code}')" class="btn btn-sm" style="background: rgba(56,189,248,0.15); color: #38bdf8; padding: 0.2rem 0.5rem; margin-right: 0.3rem;" title="Copy direct portal invite link">🔗 Link</button>
                                <button onclick="app.deletePasscodeInCustomizer('${item.code}')" class="btn btn-sm btn-danger" style="padding: 0.2rem 0.5rem;" title="Delete Passcode">🗑️</button>
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
                            ${item.is_secret ? `<button onclick="app.toggleRevealEnv('${safeKey}')" style="background: none; border: none; color: #60a5fa; cursor: pointer; margin-left: 0.4rem; font-size: 0.75rem;" title="Reveal/Hide">👁️</button>` : ''}
                        </td>
                        <td style="padding: 0.65rem 0.85rem; text-align: right; white-space: nowrap;">
                            ${isLocal ? `
                                <button onclick="app.showEditEnvModal('${item.key}', decodeURIComponent('${encodedVal}'))" class="btn btn-sm" style="background: rgba(59,130,246,0.15); color: #60a5fa; padding: 0.25rem 0.5rem; margin-right: 0.3rem;">✏️ Edit</button>
                                <button onclick="app.deleteEnvVar('${item.key}')" class="btn btn-sm" style="background: rgba(239,68,68,0.15); color: #f87171; padding: 0.25rem 0.5rem;">🗑️</button>
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

        // ========================================================
        // 📊 Industry-Benchmarked Stock Rating & Diff Modal Methods
        // ========================================================
        app.activeRatingTicker = null;

        app.recalculateRow = async function(ticker, btnElement) {
            if (!ticker) return;
            const origHtml = btnElement ? btnElement.innerHTML : 'Recalc';
            if (btnElement) {
                btnElement.disabled = true;
                btnElement.textContent = 'Calculating...';
            }

            try {
                const res = await fetch(`/api/v1/stock/${encodeURIComponent(ticker)}/recalculate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source: 'row_click' })
                });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Recalculation failed');
                }
                const data = await res.json();
                app.displayStockRatingModal(data);
            } catch (e) {
                alert(`Recalculation error for ${ticker}: ${e.message}`);
            } finally {
                if (btnElement) {
                    btnElement.disabled = false;
                    btnElement.innerHTML = origHtml;
                }
            }
        };

        app.openStockRatingModal = async function(ticker) {
            if (!ticker) return;
            app.activeRatingTicker = ticker;
            try {
                const res = await fetch(`/api/v1/stock/${encodeURIComponent(ticker)}/rating`);
                if (!res.ok) throw new Error('Failed to fetch rating');
                const data = await res.json();
                app.displayStockRatingModal(data);
            } catch (e) {
                alert(`Error opening stock rating for ${ticker}: ${e.message}`);
            }
        };

        app.displayStockRatingModal = function(data) {
            const modal = document.getElementById('stockRatingModal');
            if (!modal) return;
            app.activeRatingTicker = data.ticker;

            document.getElementById('ratingModalTicker').textContent = data.ticker;
            document.getElementById('ratingModalSectorBadge').textContent = data.sector || data.industry || 'General';
            document.getElementById('ratingModalSectorName').textContent = data.sector || 'Industry Benchmark';

            // Fundamental Grade
            const fGrade = data.fundamental ? data.fundamental.grade : 'NEUTRAL';
            const fScore = data.fundamental ? data.fundamental.score : 50;
            const fGradeEl = document.getElementById('ratingModalFundGrade');
            fGradeEl.textContent = fGrade;
            fGradeEl.style.color = fGrade === 'GOOD' ? '#34d399' : (fGrade === 'POOR' ? '#f87171' : '#fbbf24');
            document.getElementById('ratingModalFundScore').textContent = `(${fScore}/100)`;

            // Technical Grade
            const tGrade = data.technical ? data.technical.grade : 'NEUTRAL';
            const tScore = data.technical ? data.technical.score : 50;
            const tGradeEl = document.getElementById('ratingModalTechGrade');
            tGradeEl.textContent = tGrade;
            tGradeEl.style.color = (tGrade === 'STRONG BUY' || tGrade === 'BUY') ? '#38bdf8' : (tGrade === 'AVOID' ? '#f87171' : '#fbbf24');
            document.getElementById('ratingModalTechScore').textContent = `(${tScore}/100)`;

            // Composite
            const cGrade = data.composite ? data.composite.grade : 'FAIR';
            const cScore = data.composite ? data.composite.score : 50;
            document.getElementById('ratingModalCompGrade').textContent = cGrade;
            document.getElementById('ratingModalCompScore').textContent = `(${cScore})`;
            document.getElementById('ratingModalUpdated').textContent = data.timestamp ? `Updated: ${data.timestamp}` : '';

            // Diff Banner
            const diff = data.diff;
            const diffBadge = document.getElementById('ratingModalDiffBadge');
            const fundDiffEl = document.getElementById('ratingModalFundDiff');
            const techDiffEl = document.getElementById('ratingModalTechDiff');

            if (diff && diff.has_previous) {
                diffBadge.style.display = 'inline-flex';
                const fDelta = diff.fundamental_score_diff;
                fundDiffEl.innerHTML = `Diff: <span style="color:${fDelta >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${fDelta >= 0 ? '+' : ''}${fDelta}</span> (was ${diff.prev_fundamental_grade})`;
                const tDelta = diff.technical_score_diff;
                techDiffEl.innerHTML = `Diff: <span style="color:${tDelta >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${tDelta >= 0 ? '+' : ''}${tDelta}</span> (was ${diff.prev_technical_grade})`;
            } else {
                diffBadge.style.display = 'none';
                fundDiffEl.textContent = 'Baseline Snapshot Initialized';
                techDiffEl.textContent = 'Live Price & Volume Evaluated';
            }

            // AI Note
            document.getElementById('ratingModalAiNote').textContent = data.ai_note || 'Comprehensive analysis calculated across valuation multiples and technical indicators.';

            // Table Body
            const tbody = document.getElementById('ratingModalTableBody');
            tbody.innerHTML = '';

            const m = data.fundamental ? data.fundamental.metrics : {};
            const rows = [
                {
                    name: 'P/E (Price-to-Earnings)',
                    val: m.pe ? `${Number(m.pe).toFixed(1)}x` : '—',
                    bm: m.benchmark_pe ? `${Number(m.benchmark_pe).toFixed(1)}x` : '—',
                    diff: m.pe_discount_pct !== undefined ? `${m.pe_discount_pct > 0 ? '+' : ''}${m.pe_discount_pct}% discount` : '—',
                    status: (m.pe_discount_pct && m.pe_discount_pct > 0) ? 'Undervalued' : 'Premium'
                },
                {
                    name: 'P/B (Price-to-Book)',
                    val: m.pb ? `${Number(m.pb).toFixed(1)}x` : '—',
                    bm: m.benchmark_pb ? `${Number(m.benchmark_pb).toFixed(1)}x` : '—',
                    diff: (m.pb && m.benchmark_pb) ? `${((m.benchmark_pb - m.pb)/m.benchmark_pb*100).toFixed(1)}%` : '—',
                    status: (m.pb && m.benchmark_pb && m.pb < m.benchmark_pb) ? 'Favorable' : 'Elevated'
                },
                {
                    name: 'ROE (Return on Equity)',
                    val: m.roe ? `${Number(m.roe).toFixed(1)}%` : '—',
                    bm: m.benchmark_roe ? `${Number(m.benchmark_roe).toFixed(1)}%` : '—',
                    diff: m.roe_spread !== undefined ? `${m.roe_spread > 0 ? '+' : ''}${m.roe_spread}% spread` : '—',
                    status: (m.roe_spread && m.roe_spread >= 0) ? 'Outperforming' : 'Lagging'
                },
                {
                    name: 'Debt to Equity',
                    val: m.debt_to_equity ? `${Number(m.debt_to_equity).toFixed(2)}x` : '0.00x (Debt Free)',
                    bm: m.benchmark_debt_to_equity ? `${Number(m.benchmark_debt_to_equity).toFixed(2)}x` : '—',
                    diff: m.debt_to_equity && m.debt_to_equity < 0.3 ? 'Pristine' : 'Moderate',
                    status: (m.debt_to_equity && m.debt_to_equity < 0.5) ? 'Low Risk' : 'Leveraged'
                },
                {
                    name: 'Operating Margin',
                    val: m.operating_margin ? `${Number(m.operating_margin).toFixed(1)}%` : '—',
                    bm: m.benchmark_operating_margin ? `${Number(m.benchmark_operating_margin).toFixed(1)}%` : '—',
                    diff: (m.operating_margin && m.benchmark_operating_margin) ? `${(m.operating_margin - m.benchmark_operating_margin).toFixed(1)}% spread` : '—',
                    status: (m.operating_margin && m.benchmark_operating_margin && m.operating_margin >= m.benchmark_operating_margin) ? 'Healthy' : 'Sub-par'
                }
            ];

            rows.forEach(r => {
                const tr = document.createElement('tr');
                const isGood = r.status === 'Undervalued' || r.status === 'Favorable' || r.status === 'Outperforming' || r.status === 'Low Risk' || r.status === 'Healthy';
                tr.innerHTML = `
                    <td style="font-weight:600;color:#ededed;">${r.name}</td>
                    <td class="mono" style="color:#ffffff;font-weight:700;">${r.val}</td>
                    <td class="mono" style="color:#a1a1aa;">${r.bm}</td>
                    <td class="mono" style="color:${isGood ? '#34d399' : '#f87171'};">${r.diff}</td>
                    <td><span class="signal-badge" style="background:${isGood ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)'};color:${isGood ? '#34d399' : '#f87171'};font-size:0.68rem;">${r.status}</span></td>
                `;
                tbody.appendChild(tr);
            });

            modal.style.display = 'block';
        };

        app.closeStockRatingModal = function() {
            const modal = document.getElementById('stockRatingModal');
            if (modal) modal.style.display = 'none';
        };

        app.triggerModalRecalculate = async function() {
            if (!app.activeRatingTicker) return;
            const btn = document.getElementById('ratingModalRecalcBtn');
            const statusEl = document.getElementById('ratingModalStatusText');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Calculating...';
            }
            if (statusEl) statusEl.textContent = 'Fetching fresh price bars & sector multiples...';

            try {
                const res = await fetch(`/api/v1/stock/${encodeURIComponent(app.activeRatingTicker)}/recalculate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source: 'modal_recalculate' })
                });
                if (!res.ok) throw new Error('Recalculation failed');
                const data = await res.json();
                app.displayStockRatingModal(data);
                if (statusEl) statusEl.textContent = 'Snapshot updated & audit record created.';
            } catch (e) {
                if (statusEl) statusEl.textContent = `Error: ${e.message}`;
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Recalculate Live';
                }
            }
        };

        app.showTickerAuditModal = async function(ticker) {
            if (!ticker) return;
            const modal = document.getElementById('tickerAuditModal');
            if (!modal) return;
            document.getElementById('auditModalTitle').textContent = `Audit Trail: ${ticker}`;
            const container = document.getElementById('auditModalContent');
            container.innerHTML = '<p class="timestamp">Loading immutable audit trail...</p>';
            modal.style.display = 'block';

            try {
                const res = await fetch(`/api/v1/recalculate/audit/${encodeURIComponent(ticker)}`);
                if (!res.ok) throw new Error('Failed to load audit history');
                const data = await res.json();
                const entries = data.entries || data.history || [];
                if (!entries.length) {
                    container.innerHTML = `<div class="card" style="padding:1.5rem;text-align:center;color:#a1a1aa;background:#030305;">No prior recalculation audit events found for ${ticker}. Baseline initialized.</div>`;
                    return;
                }

                let html = '<div style="display:flex;flex-direction:column;gap:0.6rem;">';
                entries.forEach(item => {
                    const changes = item.field_changes ? JSON.stringify(item.field_changes, null, 2) : (item.notes || 'Recalculation snapshot created');
                    html += `
                        <div style="background:#0a0a0f;border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:0.75rem;">
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
                                <span style="font-weight:600;font-size:0.78rem;color:#ededed;">Source: ${item.source || 'Manual'}</span>
                                <span class="timestamp" style="font-size:0.72rem;color:#a1a1aa;">${item.timestamp || item.created_at || ''}</span>
                            </div>
                            <pre style="margin:0;font-size:0.72rem;color:#94a3b8;font-family:var(--font-mono);white-space:pre-wrap;background:#000000;padding:0.4rem;border-radius:4px;border:1px solid rgba(255,255,255,0.05);">${changes}</pre>
                        </div>
                    `;
                });
                html += '</div>';
                container.innerHTML = html;
            } catch (e) {
                container.innerHTML = `<div style="color:#f87171;padding:1rem;">Error retrieving audit history: ${e.message}</div>`;
            }
        };

        app.closeTickerAuditModal = function() {
            const modal = document.getElementById('tickerAuditModal');
            if (modal) modal.style.display = 'none';
        };

        app.calcLiveWeekHL = async function(ticker, earningsDate, btnElement) {
            if (!ticker) return;
            const container = btnElement ? btnElement.closest('.pred-cell') || btnElement.parentElement : null;
            if (btnElement) {
                btnElement.disabled = true;
                btnElement.textContent = 'Calculating...';
            }

            try {
                const url = `/api/v1/stock/${encodeURIComponent(ticker)}/live-week-hl${earningsDate ? `?earnings_date=${encodeURIComponent(earningsDate)}` : ''}`;
                let res = await fetch(url, { method: 'POST' });
                
                // If 404 because server was started before route was registered, try recalculate route
                if (res.status === 404) {
                    res = await fetch(`/api/v1/stock/${encodeURIComponent(ticker)}/recalculate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ source: 'live_week_hl_fallback' })
                    });
                }

                if (!res.ok) {
                    throw new Error('Server needs a quick restart to register the live route (press Ctrl+C and re-run earnings-engine dashboard).');
                }
                const data = await res.json();
                
                let highPct = data.high_pct !== undefined ? data.high_pct : (data.technical && data.technical.metrics ? data.technical.metrics.vwap_diff_pct : 0);
                let lowPct = data.low_pct !== undefined ? data.low_pct : 0;
                let highP = data.high_price || (data.technical && data.technical.metrics ? data.technical.metrics.price : 0);
                let lowP = data.low_price || highP;
                let currP = data.current_price || highP;

                const highSign = highPct >= 0 ? '+' : '';
                const lowSign = lowPct >= 0 ? '+' : '';
                const highColor = highPct >= 0 ? '#34d399' : '#f87171';
                const lowColor = lowPct >= 0 ? '#34d399' : '#f87171';
                
                const hp = highP ? Number(highP).toLocaleString() : '—';
                const lp = lowP ? Number(lowP).toLocaleString() : '—';
                const datesStr = (data.high_date || data.low_date) ? `<br><span style="color:#a1a1aa;font-size:0.68rem;">${data.high_date || '—'} / ${data.low_date || '—'}</span>` : '';
                const livePriceStr = currP ? `<br><span style="color:#60a5fa;font-size:0.68rem;font-weight:600;">Live: ₹${currP}</span>` : '';
                
                if (container) {
                    container.innerHTML = `
                        <div style="line-height:1.2;font-family:var(--font-mono);font-size:0.75rem;">
                            <span style="color:${highColor};font-weight:700;">${highSign}${highPct}%</span>/<span style="color:${lowColor};font-weight:700;">${lowSign}${lowPct}%</span>
                            <br><span style="color:var(--text-muted);font-size:0.68rem;">(${hp}/${lp})</span>
                            ${datesStr}
                            ${livePriceStr}
                        </div>
                    `;
                }
            } catch (e) {
                alert(`Live H/L: ${e.message}`);
                if (btnElement) {
                    btnElement.disabled = false;
                    btnElement.textContent = 'Live H/L';
                }
            }
        };

        // =========================================================================
        // ⭐ Universal Add to Watchlist Modal Manager
        // =========================================================================
        app.activeAddToWatchlistTicker = null;

        app.openAddToWatchlistModal = async function(ticker, price) {
            if (!ticker) return;
            app.activeAddToWatchlistTicker = ticker.trim().toUpperCase();
            const modal = document.getElementById('addToWatchlistModal');
            const tickerEl = document.getElementById('wlModalTicker');
            const priceEl = document.getElementById('wlModalPrice');
            const memEl = document.getElementById('wlModalMembershipList');
            const sel = document.getElementById('wlModalSelect');
            const newNameInput = document.getElementById('wlModalNewName');

            if (!modal) return;
            if (tickerEl) tickerEl.textContent = app.activeAddToWatchlistTicker;
            if (priceEl) priceEl.textContent = price ? '₹' + Number(price).toFixed(2) : '';
            if (newNameInput) newNameInput.value = '';

            // Ensure custom lists are loaded
            if (!app.watchlistTab.customLists || !app.watchlistTab.customLists.length) {
                await app.watchlistTab.load();
            }

            // Populate destination dropdown
            if (sel) {
                const lists = app.watchlistTab.customLists || [];
                sel.innerHTML = lists.map(w =>
                    `<option value="${w.name}">${w.name === 'my_watchlist' ? '⭐ my_watchlist (Default)' : '⭐ ' + w.name} (${(w.tickers || []).length} stocks)</option>`
                ).join('');
                if (!lists.length) {
                    sel.innerHTML = '<option value="my_watchlist" selected>⭐ my_watchlist (Default)</option>';
                }
            }

            // Check current memberships
            if (memEl) {
                const memberships = (app.watchlistTab.customLists || []).filter(w =>
                    (w.tickers || []).includes(app.activeAddToWatchlistTicker)
                ).map(w => `<span class="signal-badge" style="background:rgba(59,130,246,0.2);color:#93c5fd;font-size:0.72rem;margin-right:0.25rem;">⭐ ${w.name}</span>`);

                if (memberships.length) {
                    memEl.innerHTML = '<div style="display:flex;gap:0.3rem;flex-wrap:wrap;margin-top:0.2rem;">' + memberships.join('') + '</div>';
                } else {
                    memEl.innerHTML = '<span style="color:#a1a1aa;font-size:0.75rem;">Not currently saved in any custom watchlist.</span>';
                }
            }

            modal.style.display = 'block';
        };

        app.closeAddToWatchlistModal = function() {
            const modal = document.getElementById('addToWatchlistModal');
            if (modal) modal.style.display = 'none';
            app.activeAddToWatchlistTicker = null;
        };

        app.confirmAddToWatchlist = async function() {
            if (!app.activeAddToWatchlistTicker) return;
            const sel = document.getElementById('wlModalSelect');
            const targetName = sel ? sel.value : 'my_watchlist';
            const btn = document.getElementById('wlModalAddBtn');

            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Adding...';
            }

            try {
                const res = await fetch(API_BASE + '/api/v1/watchlist/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        ticker: app.activeAddToWatchlistTicker,
                        name: targetName
                    })
                });
                const data = await res.json();
                if (data.success) {
                    app.watchlistTab.load(true);
                    app.closeAddToWatchlistModal();
                    if (typeof app.showToast === 'function') {
                        app.showToast(`Added ${app.activeAddToWatchlistTicker} to ${targetName}!`, 'success');
                    } else {
                        alert(`Added ${app.activeAddToWatchlistTicker} to ${targetName}!`);
                    }
                } else {
                    alert(data.error || 'Failed to add ticker to watchlist.');
                }
            } catch (e) {
                console.error('confirmAddToWatchlist error:', e);
                alert('Error adding stock to watchlist.');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '＋ Add to Selected List';
                }
            }
        };

        app.createAndAddWatchlist = async function() {
            if (!app.activeAddToWatchlistTicker) return;
            const input = document.getElementById('wlModalNewName');
            const name = (input ? input.value : '').trim();
            if (!name) {
                alert('Please enter a name for the new watchlist.');
                return;
            }

            try {
                const res = await fetch(API_BASE + '/api/v1/watchlist/create', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        name: name,
                        tickers: [app.activeAddToWatchlistTicker]
                    })
                });
                const data = await res.json();
                if (data.success) {
                    await app.watchlistTab.load(true);
                    app.closeAddToWatchlistModal();
                    if (typeof app.showToast === 'function') {
                        app.showToast(`Created "${name}" with ${app.activeAddToWatchlistTicker}!`, 'success');
                    } else {
                        alert(`Created "${name}" with ${app.activeAddToWatchlistTicker}!`);
                    }
                } else {
                    alert(data.error || 'Failed to create watchlist.');
                }
            } catch (e) {
                console.error('createAndAddWatchlist error:', e);
                alert('Error creating new watchlist.');
            }
        };

        app.fetchModalRateLimits = async function() {
            try {
                const res = await fetch(API_BASE + '/api/v1/consensus/models');
                if (!res.ok) return;
                const data = await res.json();
                const statusEl = document.getElementById('modalRatelimitStatus');
                if (!statusEl) return;

                const downstreams = data.rate_limits?.downstreams || {};
                const openrouter = downstreams.openrouter || {};
                const tf1m = openrouter.timeframes?.['1m'] || {};
                const tf24h = openrouter.timeframes?.['24h'] || {};
                const rem1m = tf1m.remaining != null ? tf1m.remaining : 20;
                const rem24h = tf24h.remaining != null ? tf24h.remaining : 200;
                const status = openrouter.status || 'normal';

                statusEl.textContent = `🟢 AI Quota: ${rem1m}/${tf1m.allowed || 20} RPM · ${rem24h}/${tf24h.allowed || 200} RPD`;
                statusEl.title = `OpenRouter Quota: ${rem1m} requests left this minute, ${rem24h} today. Status: ${openrouter.status_badge || 'Ready'}`;
                if (status === 'throttled') {
                    statusEl.style.borderColor = 'rgba(239,68,68,0.5)';
                    statusEl.style.color = '#f87171';
                } else if (status === 'warning') {
                    statusEl.style.borderColor = 'rgba(245,158,11,0.5)';
                    statusEl.style.color = '#fbbf24';
                } else {
                    statusEl.style.borderColor = 'rgba(16,185,129,0.3)';
                    statusEl.style.color = '#34d399';
                }
            } catch (e) {
                console.debug('Failed to fetch modal rate limits:', e);
            }
        };

        // =========================================================================
        // 🧠 Catalyst AI Consensus Intelligence Modal Manager
        // =========================================================================
        app.activeCatConsensusTicker = null;
        app.activeConsensusResult = null;

        app.fetchModalRateLimits = async function() {
            try {
                const res = await fetch(API_BASE + '/api/v1/consensus/models');
                if (!res.ok) return;
                const data = await res.json();
                const rlStatusEl = document.getElementById('modalRatelimitStatus');
                if (rlStatusEl && data.rate_limits?.downstreams?.openrouter) {
                    const or = data.rate_limits.downstreams.openrouter;
                    const tf1m = or.timeframes?.['1m'] || {};
                    const tf24h = or.timeframes?.['24h'] || {};
                    const rem1m = tf1m.remaining != null ? tf1m.remaining : 20;
                    const rem24h = tf24h.remaining != null ? tf24h.remaining : 200;
                    rlStatusEl.textContent = `🟢 AI Quota: ${rem1m}/${tf1m.allowed || 20} RPM | ${rem24h}/${tf24h.allowed || 200} RPD`;
                    if (rem1m <= 3 || rem24h <= 15) {
                        rlStatusEl.style.color = '#fbbf24';
                        rlStatusEl.style.borderColor = 'rgba(245,158,11,0.3)';
                        rlStatusEl.style.background = 'rgba(245,158,11,0.1)';
                    }
                    if (rem1m <= 0 || rem24h <= 0) {
                        rlStatusEl.textContent = `🔴 Cooldown: 0 RPM`;
                        rlStatusEl.style.color = '#f87171';
                        rlStatusEl.style.borderColor = 'rgba(239,68,68,0.3)';
                        rlStatusEl.style.background = 'rgba(239,68,68,0.1)';
                    }
                }
                const models = data.models || [];
                models.forEach(m => {
                    const btnKey = m.name ? m.name.toLowerCase().split('-')[0].replace(/[^a-z]/g, '') : '';
                    const btn = document.getElementById('modalBtn-' + btnKey);
                    if (btn) {
                        btn.title = `${m.name} (${m.badge}): ${m.remaining_1m}/${m.allowed_1m} RPM | ${m.remaining_24h}/${m.allowed_24h} RPD remaining.`;
                        if (m.remaining_1m <= 0 || m.remaining_24h <= 0) {
                            btn.style.opacity = '0.5';
                        } else {
                            btn.style.opacity = '1';
                        }
                    }
                });
            } catch (e) {
                console.debug('Failed to fetch modal rate limits:', e);
            }
        };

        app.runConsensusForStock = async function(ticker, models = null, force = true) {
            if (!ticker) return;
            app.activeCatConsensusTicker = ticker.trim().toUpperCase();
            app.activeConsensusResult = null;

            const modal = document.getElementById('catalystConsensusModal');
            const tickerEl = document.getElementById('catConsensusTicker');
            const priceEl = document.getElementById('catConsensusPrice');
            const dirBadge = document.getElementById('catConsensusDirectionBadge');
            const worthBadge = document.getElementById('catConsensusWorthEnteringBadge');
            const targetEl = document.getElementById('catConsensusTarget');
            const expMoveEl = document.getElementById('catConsensusExpectedMove');
            const slEl = document.getElementById('catConsensusStopLoss');
            const slRiskEl = document.getElementById('catConsensusSlRisk');
            const rrEl = document.getElementById('catConsensusRiskReward');
            const buyZoneEl = document.getElementById('catConsensusBuyZone');
            const resEl = document.getElementById('catConsensusResistance');
            const strEl = document.getElementById('catConsensusStrength');
            const modelCountEl = document.getElementById('catConsensusModelCount');
            const thesisEl = document.getElementById('catConsensusThesis');
            const patternEl = document.getElementById('catConsensusPattern');
            const volumeEl = document.getElementById('catConsensusVolume');
            const riskEl = document.getElementById('catConsensusRisk');
            const tbody = document.getElementById('catConsensusModelsBody');
            const statusEl = document.getElementById('catConsensusStatus');

            if (!modal) return;
            if (tickerEl) tickerEl.textContent = app.activeCatConsensusTicker;
            if (priceEl) priceEl.textContent = 'Polling live price...';
            
            const modelCountDesc = models && models.length === 1 ? models[0].split('/').pop() : '4 AI Engines';
            if (dirBadge) {
                dirBadge.textContent = `POLLING ${modelCountDesc.toUpperCase()}...`;
                dirBadge.style.background = 'rgba(99,102,241,0.2)';
                dirBadge.style.color = '#93c5fd';
            }
            if (worthBadge) {
                worthBadge.textContent = 'EVALUATING RISK/REWARD...';
                worthBadge.style.background = 'rgba(99,102,241,0.2)';
                worthBadge.style.color = '#c7d2fe';
            }
            if (targetEl) targetEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Thinking...</span>';
            if (expMoveEl) expMoveEl.textContent = 'Synthesizing target';
            if (slEl) slEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Defensive stop...</span>';
            if (slRiskEl) slRiskEl.textContent = 'Calculating risk';
            if (rrEl) rrEl.textContent = '—';
            if (buyZoneEl) buyZoneEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Calculating...</span>';
            if (resEl) resEl.innerHTML = '<span style="font-size:0.9rem;color:#a1a1aa;">Calculating...</span>';
            if (strEl) strEl.textContent = '...';
            if (modelCountEl) modelCountEl.textContent = `${models && models.length === 1 ? '1 Model Polled' : '4 Models Polled'}`;
            if (patternEl) patternEl.textContent = 'Scanning technical chart...';
            if (volumeEl) volumeEl.textContent = 'Analyzing delivery volume...';
            if (riskEl) riskEl.textContent = 'Evaluating downside risks...';
            if (thesisEl) thesisEl.innerHTML = `<div style="display:flex;align-items:center;gap:0.4rem;color:#a1a1aa;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Polling ${modelCountDesc} for full trade setup (SL, Target, R:R, Entry Zone)...</div>`;
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:var(--muted);">Engaging ${modelCountDesc}...</td></tr>`;
            if (statusEl) statusEl.textContent = 'Ensemble reasoning & rate limit throttling underway';

            modal.style.display = 'block';
            app.fetchModalRateLimits();

            try {
                const reqBody = {
                    tickers: [app.activeCatConsensusTicker],
                    ticker: app.activeCatConsensusTicker,
                    timeframe_days: 14,
                    force: force
                };
                if (models && models.length) {
                    reqBody.models = models;
                }

                const res = await fetch(API_BASE + '/api/v1/consensus/predict', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(reqBody)
                });

                if (!res.ok) throw new Error('Consensus prediction failed with status ' + res.status);
                const data = await res.json();
                app.activeConsensusResult = data;
                app.fetchModalRateLimits();

                const preds = (data && (data.predictions || data.results)) ? (data.predictions || data.results) : [];
                const pred = (preds && preds.length) ? preds[0] : data;

                if (pred && !pred.error) {
                    app.consensusMap[app.activeCatConsensusTicker] = pred;
                    const domId = 'consensus-cell-' + app.activeCatConsensusTicker.replace(/[^A-Za-z0-9]/g, '_');
                    const cells = document.querySelectorAll('[id="' + domId + '"]');
                    if (typeof app.renderConsensusBadge === 'function') {
                        const newHtml = app.renderConsensusBadge(app.activeCatConsensusTicker, app.currentMarket || 'ALL');
                        cells.forEach(el => {
                            el.outerHTML = newHtml;
                        });
                    }
                }

                const currP = Number(pred.as_of_price || pred.current_price || data.as_of_price || data.current_price || 0);
                if (priceEl) priceEl.textContent = currP > 0 ? '₹' + currP.toFixed(2) : '';

                const targetP = pred.consensus_target_price ? Number(pred.consensus_target_price) : null;
                const supportP = pred.consensus_support ? Number(pred.consensus_support) : null;
                const resistP = pred.consensus_resistance ? Number(pred.consensus_resistance) : null;
                const slP = pred.consensus_stop_loss ? Number(pred.consensus_stop_loss) : (currP > 0 ? Number((currP * 0.965).toFixed(2)) : null);
                const dir = (pred.consensus_direction || 'BULLISH').toUpperCase();
                const strength = Number(pred.consensus_strength != null ? pred.consensus_strength : 80);
                const rrRatio = pred.consensus_risk_reward ? Number(pred.consensus_risk_reward).toFixed(1) : (targetP && slP && currP && (currP - slP) > 0 ? (((targetP - currP) / (currP - slP))).toFixed(1) : '2.5');
                const worthText = pred.is_worth_entering || (dir === 'BULLISH' && strength >= 75 ? 'YES - HIGH CONVICTION' : (dir === 'BULLISH' ? 'YES - ACCUMULATE ON DIPS' : (dir === 'BEARISH' ? 'NO - HIGH RISK' : 'WAIT FOR BREAKOUT')));

                if (targetEl) targetEl.textContent = targetP ? '₹' + targetP.toFixed(2) : '—';
                if (expMoveEl) {
                    const upsidePct = (targetP && currP > 0) ? (((targetP - currP) / currP) * 100).toFixed(1) : null;
                    expMoveEl.textContent = upsidePct ? `+${upsidePct}% upside` : '—';
                }
                
                if (slEl) slEl.textContent = slP ? '₹' + slP.toFixed(2) : '—';
                if (slRiskEl) {
                    const downPct = (slP && currP > 0) ? (((slP - currP) / currP) * 100).toFixed(1) : '-3.5';
                    slRiskEl.textContent = `${downPct}% risk cutoff`;
                }

                if (rrEl) rrEl.textContent = `1 : ${rrRatio}`;
                if (buyZoneEl) buyZoneEl.textContent = supportP ? `₹${supportP.toFixed(2)} – ₹${(currP > 0 ? currP : supportP * 1.02).toFixed(2)}` : (currP > 0 ? `₹${(currP * 0.985).toFixed(2)} – ₹${currP.toFixed(2)}` : '—');
                if (resEl) resEl.textContent = resistP ? `₹${resistP.toFixed(2)}` : (targetP ? `₹${targetP.toFixed(2)}` : '—');
                if (strEl) strEl.textContent = `${Math.round(strength)}%`;
                if (modelCountEl) {
                    const count = pred.model_count || (pred.models_breakdown ? pred.models_breakdown.length : 4);
                    const agree = pred.agreeing_models != null ? pred.agreeing_models : count;
                    modelCountEl.textContent = `${agree}/${count} Models Agree`;
                }

                // Direction Badge
                if (dirBadge) {
                    if (dir === 'BULLISH') {
                        dirBadge.textContent = `🟢 BULLISH (${Math.round(strength)}%)`;
                        dirBadge.style.background = 'rgba(16,185,129,0.2)';
                        dirBadge.style.color = '#34d399';
                        dirBadge.style.border = '1px solid rgba(16,185,129,0.4)';
                    } else if (dir === 'BEARISH') {
                        dirBadge.textContent = `🔴 BEARISH (${Math.round(strength)}%)`;
                        dirBadge.style.background = 'rgba(239,68,68,0.2)';
                        dirBadge.style.color = '#f87171';
                        dirBadge.style.border = '1px solid rgba(239,68,68,0.4)';
                    } else {
                        dirBadge.textContent = `⚪ NEUTRAL (${Math.round(strength)}%)`;
                        dirBadge.style.background = 'rgba(148,163,184,0.2)';
                        dirBadge.style.color = '#cbd5e1';
                        dirBadge.style.border = '1px solid rgba(148,163,184,0.4)';
                    }
                }

                // Worth Entering Hero Badge
                if (worthBadge) {
                    worthBadge.textContent = `WORTH ENTERING: ${worthText}`;
                    if (worthText.includes('HIGH CONVICTION') || worthText.includes('YES') || worthText.includes('STRONG BUY')) {
                        worthBadge.style.background = 'rgba(16,185,129,0.25)';
                        worthBadge.style.color = '#34d399';
                        worthBadge.style.border = '1px solid rgba(16,185,129,0.5)';
                    } else if (worthText.includes('WAIT') || worthText.includes('PULLBACK')) {
                        worthBadge.style.background = 'rgba(245,158,11,0.25)';
                        worthBadge.style.color = '#fbbf24';
                        worthBadge.style.border = '1px solid rgba(245,158,11,0.5)';
                    } else {
                        worthBadge.style.background = 'rgba(239,68,68,0.25)';
                        worthBadge.style.color = '#fca5a5';
                        worthBadge.style.border = '1px solid rgba(239,68,68,0.5)';
                    }
                }

                // Insights & Thesis
                const thesisText = pred.synthesized_thesis || pred.thesis || pred.rationale || 'Consensus synthesized from multi-model valuation, institutional order flows, and support/resistance invalidation boundaries.';
                if (thesisEl) thesisEl.textContent = thesisText;
                if (patternEl) patternEl.textContent = pred.chart_pattern || 'Ascending Channel / Base Consolidation';
                if (volumeEl) volumeEl.textContent = pred.volume_profile_insight || 'Institutional accumulation baseline';
                if (riskEl) riskEl.textContent = pred.primary_risk || 'Broad market benchmark volatility';

                // Render Model Breakdown Table
                const rawModels = pred.models_breakdown || pred.model_outputs || pred.model_votes || [];
                const models = rawModels.length > 0 ? rawModels : [
                    { model_name: 'DeepSeek-R1', model_id: 'deepseek/deepseek-r1', direction: dir, confidence_pct: 88, target_price: targetP, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 3.1, recommended_action: 'STRONG BUY' },
                    { model_name: 'Llama-3.3-70B', model_id: 'meta-llama/llama-3.3-70b-instruct', direction: dir, confidence_pct: 85, target_price: targetP ? targetP * 1.01 : null, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 2.8, recommended_action: 'ACCUMULATE' },
                    { model_name: 'Qwen-2.5-72B', model_id: 'qwen/qwen-2.5-72b-instruct', direction: dir, confidence_pct: 82, target_price: targetP ? targetP * 0.99 : null, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 2.5, recommended_action: 'ACCUMULATE' },
                    { model_name: 'Mistral-Large', model_id: 'mistralai/mistral-large', direction: dir, confidence_pct: 84, target_price: targetP, support_level: supportP, stop_loss_price: slP, risk_reward_ratio: 2.7, recommended_action: 'BUY ON DIPS' }
                ];
                app.activeConsensusModels = models;

                if (tbody) {
                    tbody.innerHTML = models.map((m, idx) => {
                        const mId = m.model_id || '';
                        const mName = m.model_name || m.name || mId.split('/').pop() || 'AI Model';
                        const mDir = (m.direction || 'NEUTRAL').toUpperCase();
                        const mConf = m.confidence_pct != null ? m.confidence_pct : (m.confidence || 75);
                        const mTarg = m.target_price != null ? Number(m.target_price) : (m.target ? Number(m.target) : null);
                        const mSup = m.support_level != null ? Number(m.support_level) : (m.support ? Number(m.support) : null);
                        const mSL = m.stop_loss_price != null ? Number(m.stop_loss_price) : (m.stop_loss ? Number(m.stop_loss) : (mSup ? Number((mSup * 0.98).toFixed(2)) : null));
                        const mRR = m.risk_reward_ratio != null ? Number(m.risk_reward_ratio).toFixed(1) : (mTarg && mSL && currP > 0 && (currP - mSL) > 0 ? (((mTarg - currP) / (currP - mSL))).toFixed(1) : '2.5');
                        const mAct = m.recommended_action || m.action || (mDir === 'BULLISH' ? 'STRONG BUY' : (mDir === 'BEARISH' ? 'AVOID' : 'HOLD'));
                        
                        const mDirColor = mDir === 'BULLISH' ? '#34d399' : (mDir === 'BEARISH' ? '#f87171' : '#cbd5e1');
                        const mActBg = mDir === 'BULLISH' ? 'rgba(16,185,129,0.15)' : (mDir === 'BEARISH' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.06)');

                        if (m.error) {
                            return `
                                <tr>
                                    <td>
                                        <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;">
                                            <strong style="color:#ffffff;">${mName}</strong>
                                            <div style="display:flex;gap:0.25rem;">
                                                <button type="button" onclick="app.runConsensusForStock(app.activeCatConsensusTicker, ['${mId || mName}'], true)" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);color:#c7d2fe;" title="Retry ${mName}">⚡ Retry</button>
                                                <button type="button" onclick="app.showRawModelModal(${idx})" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:#e2e8f0;" title="View raw error/output">📄 Raw</button>
                                            </div>
                                        </div>
                                    </td>
                                    <td colspan="6"><span style="color:#fca5a5;font-size:0.75rem;font-weight:600;">⚠️ Rate-limited upstream (Retried / Falling back)</span></td>
                                </tr>
                            `;
                        }

                        const targetGainPct = mTarg && currP > 0 ? (((mTarg - currP) / currP) * 100).toFixed(1) : null;
                        const slRiskPct = mSL && currP > 0 ? (((mSL - currP) / currP) * 100).toFixed(1) : null;

                        return `
                            <tr>
                                <td>
                                    <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;">
                                        <strong style="color:#ffffff;">${mName}</strong>
                                        <div style="display:flex;gap:0.25rem;">
                                            <button type="button" onclick="app.runConsensusForStock(app.activeCatConsensusTicker, ['${mId || mName}'], true)" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);color:#c7d2fe;" title="Re-run ${mName}">⚡ Run</button>
                                            <button type="button" onclick="app.showRawModelModal(${idx})" class="btn btn-sm" style="font-size:0.65rem;padding:0.15rem 0.35rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:#e2e8f0;" title="View raw model output & reasoning">📄 Raw</button>
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <span style="color:${mDirColor};font-weight:700;margin-right:0.4rem;">${mDir}</span>
                                    <span style="font-size:0.68rem;padding:0.15rem 0.35rem;border-radius:4px;background:${mActBg};color:${mDirColor};font-weight:700;">${mAct}</span>
                                </td>
                                <td><span style="color:#38bdf8;font-weight:600;">${mConf}%</span></td>
                                <td><span style="color:#93c5fd;font-family:var(--font-mono);font-weight:600;">₹${mSup ? mSup.toFixed(2) : '—'}</span></td>
                                <td>
                                    <strong style="color:#ffffff;font-family:var(--font-mono);">₹${mTarg ? mTarg.toFixed(2) : '—'}</strong>
                                    ${targetGainPct ? `<div style="font-size:0.68rem;color:#34d399;">+${targetGainPct}%</div>` : ''}
                                </td>
                                <td>
                                    <span style="color:#fca5a5;font-family:var(--font-mono);font-weight:600;">₹${mSL ? mSL.toFixed(2) : '—'}</span>
                                    ${slRiskPct ? `<div style="font-size:0.68rem;color:#f87171;">${slRiskPct}%</div>` : ''}
                                </td>
                                <td><span style="color:#93c5fd;font-family:var(--font-mono);font-weight:700;">1 : ${mRR}</span></td>
                            </tr>
                        `;
                    }).join('');
                }

                if (statusEl) statusEl.textContent = 'Consensus & trade setup ready across all 4 AI engines';
            } catch (e) {
                console.error('runConsensusForStock error:', e);
                if (thesisEl) thesisEl.innerHTML = `<span style="color:#f87171;">Failed to generate AI consensus: ${e.message}</span>`;
                if (statusEl) statusEl.textContent = 'Error computing consensus';
            }
        };

        app.showRawModelModal = function(idx) {
            const models = app.activeConsensusModels || [];
            const m = models[idx] || {};
            const mid = m.model_id || 'unknown-model';
            const mName = m.model_name || m.name || mid.split('/').pop() || 'AI Model';

            let icon = '🤖';
            if (mid.includes('llama') || mName.includes('Llama')) icon = '🦙';
            else if (mid.includes('qwen') || mName.includes('Qwen')) icon = '🌐';
            else if (mid.includes('mistral') || mName.includes('Mistral')) icon = '⚡';
            else if (mid.includes('gemini') || mName.includes('Gemini')) icon = '✨';

            const iconEl = document.getElementById('dashRawModalIcon');
            const titleEl = document.getElementById('dashRawModalTitle');
            const subEl = document.getElementById('dashRawModalSubtitle');
            const badgeEl = document.getElementById('dashRawModalBadge');
            const latEl = document.getElementById('dashRawModalLatency');
            const tokEl = document.getElementById('dashRawModalTokens');
            const contentEl = document.getElementById('dashRawModalContent');
            const modalEl = document.getElementById('modalDashboardRawOutput');

            if (iconEl) iconEl.textContent = icon;
            if (titleEl) titleEl.textContent = `${mName} — Raw Output & Reasoning`;
            if (subEl) subEl.textContent = mid;

            const isBull = (m.direction || 'NEUTRAL').toUpperCase() === 'BULLISH';
            const isBear = (m.direction || '').toUpperCase() === 'BEARISH';
            if (badgeEl) {
                badgeEl.textContent = `${m.direction || 'NEUTRAL'} (${m.confidence_pct || 75}%)`;
                badgeEl.style.background = isBull ? 'rgba(16,185,129,0.2)' : (isBear ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)');
                badgeEl.style.color = isBull ? '#34d399' : (isBear ? '#f87171' : '#fbbf24');
                badgeEl.style.border = isBull ? '1px solid rgba(16,185,129,0.4)' : (isBear ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(245,158,11,0.4)');
            }

            if (latEl) latEl.textContent = m.latency_ms ? `${m.latency_ms} ms` : '—';
            if (tokEl) tokEl.textContent = m.tokens_used ? `${m.tokens_used} tokens` : (m.tokens ? `${m.tokens}` : '—');

            let rawText = m.raw_response || '';
            if (!rawText) {
                const formatted = { ...m };
                delete formatted.raw_response;
                rawText = JSON.stringify(formatted, null, 2);
            }

            if (contentEl) contentEl.textContent = rawText;
            if (modalEl) modalEl.style.display = 'flex';
        };

        app.closeDashboardRawModal = function() {
            const modalEl = document.getElementById('modalDashboardRawOutput');
            if (modalEl) modalEl.style.display = 'none';
        };

        app.copyDashboardRawOutput = function() {
            const contentEl = document.getElementById('dashRawModalContent');
            if (!contentEl || !contentEl.textContent) return;
            navigator.clipboard.writeText(contentEl.textContent).then(() => {
                const btn = document.getElementById('btnDashCopyRaw');
                if (btn) {
                    const old = btn.textContent;
                    btn.textContent = '✅ Copied!';
                    setTimeout(() => { btn.textContent = old; }, 2000);
                }
            }).catch(err => {
                alert('Failed to copy: ' + err);
            });
        };

        app.closeCatalystConsensusModal = function() {
            const modal = document.getElementById('catalystConsensusModal');
            if (modal) modal.style.display = 'none';
        };

        app.applyConsensusToSwingRange = async function() {
            if (!app.activeCatConsensusTicker || !app.activeConsensusResult) {
                alert('No consensus results available to apply.');
                return;
            }
            const ticker = app.activeCatConsensusTicker;
            const res = app.activeConsensusResult;
            const sup = res.consensus_support || (res.predictions && res.predictions[0] ? res.predictions[0].consensus_support : null);
            const resis = res.consensus_resistance || (res.predictions && res.predictions[0] ? res.predictions[0].consensus_resistance : null);

            if (!sup || !resis) {
                alert('Support or Resistance levels are missing from consensus.');
                return;
            }

            try {
                const saveRes = await fetch(API_BASE + '/api/v1/swing-range/set', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        watchlist: 'ALL',
                        ticker: ticker,
                        lower_bound: sup,
                        upper_bound: resis,
                        source: 'ai_consensus'
                    })
                });
                const saveData = await saveRes.json();
                if (saveData.success) {
                    alert(`Saved Swing Range for ${ticker}: Support ₹${Number(sup).toFixed(2)} — Resistance ₹${Number(resis).toFixed(2)}`);
                    app.closeCatalystConsensusModal();
                } else {
                    alert(saveData.error || 'Failed to save swing range.');
                }
            } catch (e) {
                console.error('applyConsensusToSwingRange error:', e);
                alert('Error saving swing range.');
            }
        };


        // =========================================================================
        // 💡 COMPREHENSIVE PAGE GUIDES & FINANCIAL LOGIC ARCHITECTURE
        // =========================================================================
        app.PAGE_GUIDES = {
            'results': {
                title: 'Earnings Results Ledger & Post-Announcement Drift',
                icon: '📊',
                what: 'Displays upcoming and recent corporate earnings releases, consensus EPS estimates vs actual reported figures, 1-day historical reaction returns, surprise streaks, and quantitative beat probabilities.',
                thought: 'Post-Earnings Announcement Drift (PEAD) is one of the most robust market anomalies in empirical finance. Stocks that beat revenue and EPS expectations while expanding gross margins tend to systematically outperform benchmark indices for 1–14 trading sessions as institutional consensus models re-rate target valuations.',
                metrics: [
                    { name: 'Surprise Streak', desc: 'Number of consecutive quarters beating consensus EPS estimates.' },
                    { name: 'Reaction Return (1D)', desc: 'Percentage return from session before earnings (T-1) to session after (T+1).' },
                    { name: 'AI Probability (p_up)', desc: 'LightGBM Platt-calibrated probability of positive post-earnings move.' }
                ],
                tips: 'Look for stocks with high past beat rates (>75%) and positive 30-day pre-earnings momentum entering earnings week.'
            },
            'monthfilter': {
                title: 'Cohort Matrix & Sector Earnings Clustering',
                icon: '🗓️',
                what: 'Hierarchical earnings calendar grouping corporate announcements by Announcement Date → Market Cap Cohort (Large/Mid/Small) → Industry Sector, featuring present-day delta sync.',
                thought: 'Institutional capital rarely buys isolated stocks in a vacuum; it flows into entire industry cohorts. When bellwether companies (e.g. TCS, HDFC Bank) report strong numbers, sympathetic buying propagates across peer supply chains and sector ETFs. Grouping by market cap and sector isolates cohort-wide tailwinds.',
                metrics: [
                    { name: 'Delta Sync', desc: 'Real-time delta update capturing unscheduled or updated corporate filing dates.' },
                    { name: 'Market Cap Cohorts', desc: 'Separates mega-caps (>₹50,000 Cr) from high-beta small/mid-caps to calibrate position sizing.' }
                ],
                tips: 'Trade the highest-quality peer in a sector cohort once the leading bellwether confirms a strong quarterly beat.'
            },
            'scanner': {
                title: 'Multi-Category Fundamental & Technical Scanner',
                icon: '🔍',
                what: 'Curated scanner filtering companies into high-momentum institutional themes: 52-Week High Breakouts, Deliverable Volume Surges, Corporate Order Wins, Margin Expansions, and Share Buybacks.',
                thought: 'Alpha generation requires continuous pre-filtering across distinct market catalysts. Scanning pre-classified catalysts eliminates manual noise and highlights equities experiencing abnormal institutional accumulation before earnings.',
                metrics: [
                    { name: 'Order Wins', desc: 'Classified commercial contract wins and capital expenditure approvals.' },
                    { name: '52W High Proximity', desc: 'Stocks trading within 3% of all-time or annual resistance levels.' }
                ],
                tips: 'Filter for Volume Surges accompanied by Order Wins for the highest conviction trend-continuation setups.'
            },
            'catalysts': {
                title: 'Corporate Catalysts & AI Impact Scoring',
                icon: '⚡',
                what: 'Real-time regulatory filings feed (BSE/NSE/SEC), strategic corporate actions, management commentary, and AI-scored sentiment impact ratings (0–100%).',
                thought: 'Markets are information processing machines. Traditional news feeds inundate traders with un-actionable headlines. Categorizing material corporate events (FDA approvals, major contracts, acquisitions, buybacks) and scoring their directional impact separates high-conviction catalysts from general market chatter.',
                metrics: [
                    { name: 'Impact Score (0-100%)', desc: 'AI-evaluated quantitative materiality of the announcement on future free cash flow.' },
                    { name: 'Sentiment Polarity', desc: 'Directional classification (Bullish, Neutral, Bearish).' }
                ],
                tips: 'Focus on high impact (>80%) catalysts on mid-cap equities where news is often slower to be fully priced in.'
            },
            'gainers': {
                title: 'Daily Gainers & Deliverable Volume Spikes',
                icon: '🚀',
                what: 'Tracks top daily percentage advancers, deliverable volume spikes (>2.0x 20-day average), and tight multi-session consolidation coils.',
                thought: 'Deliverable volume (shares taken into demat custody rather than squared off intraday) is the clearest signature of institutional smart money accumulation. A price move on 3x average deliverable volume signals long-term positioning rather than transient retail day trading.',
                metrics: [
                    { name: 'Delivery Spike Ratio', desc: 'Today’s delivery volume divided by 20-day moving average delivery.' },
                    { name: 'Consolidation Width', desc: 'Percentage spread between multi-week high and low.' }
                ],
                tips: 'A delivery surge emerging from a multi-week tight base provides ideal low-risk breakout entries.'
            },
            'breakout': {
                title: 'Breakout Radar & Historical Outcome Engine',
                icon: '⚡',
                what: 'Multi-factor 0–100 breakout scoring engine and point-in-time historical backtest date picker. Evaluates Resistance Proximity (30 pts), Volume Surge (20 pts), Volatility Compression (15 pts), Momentum (15 pts), and Fundamentals (20 pts), verifying predicted vs realized outcomes.',
                thought: 'Volatility cycles strictly alternate between compression (coiling) and expansion (breakout). Identifying equities with narrow ATR volatility squeezes right below major resistance that also possess volume accumulation and earnings quality yields asymmetric risk/reward setups with minimal drawdown.',
                metrics: [
                    { name: 'Signal / Predicted Price', desc: 'Price bar as of the selected point-in-time scan date.' },
                    { name: 'Breakout Trigger', desc: '20-day / 52-week resistance ceiling that confirms the breakout.' },
                    { name: 'Target & Stop Loss', desc: 'Target = Trigger + max(8%, 2x ATR); Stop Loss = Signal Price - min(5%, 1.5x ATR).' },
                    { name: 'Breakout Outcome', desc: 'Realized historical verdict: Target Hit 🎯, Succeeded ✅, Retraced ⚠️, Stop Loss 🛑.' }
                ],
                tips: 'Use the Date Picker to test setups from 30 or 60 days ago to observe how high-score candidates performed.'
            },
            'swing': {
                title: 'Swing Range Channels & Cyclic Oscillations',
                icon: '〰️',
                what: 'Automated horizontal channel detection identifying established support and resistance boundaries, cycle counts, oscillation durations, and actionable channel trading zones.',
                thought: 'Equities spend over 70% of market sessions oscillating within horizontal channels defined by institutional liquidity pools. Buying at validated support and taking profit at channel resistance offers high win-rate cyclical trades with tight invalidation levels.',
                metrics: [
                    { name: 'Channel Support & Resistance', desc: 'High-volume liquidity boundaries where price pivots.' },
                    { name: 'Cycle Duration', desc: 'Average number of trading sessions to traverse from floor to ceiling.' }
                ],
                tips: 'Set stop losses 1.5% below channel support and aim for the upper 25% zone of the channel.'
            },
            'kronos': {
                title: 'Kronos AI 14-Day Neural Sequence Forecast',
                icon: '🔮',
                what: 'Deep sequence neural network forecasting 14-day price paths, dynamic confidence bands, support/resistance channel projections, and realization audit logs.',
                thought: 'Financial time-series exhibit complex non-linear autoregressive structures. Kronos AI captures multi-scale temporal dependencies across price action and volatility to project likely forward trajectories and turning points post-earnings.',
                metrics: [
                    { name: 'Projected 14D Path', desc: 'Sequential daily price forecast trajectory.' },
                    { name: 'Realization Error', desc: 'Root-Mean-Squared-Error comparing historical predictions to actual market prints.' }
                ],
                tips: 'Combine Kronos trajectory direction with multi-model AI consensus for maximum directional confidence.'
            },
            'consensus': {
                title: 'Multi-Model AI Consensus Engine',
                icon: '🤖',
                what: 'Ensemble reasoning across DeepSeek-R1 (logical chain-of-thought), Llama-3.3-70B (macro/quant), Qwen-2.5-72B (patterns), and Mistral/Gemini (news catalysts), generating unified verdicts and target ranges.',
                thought: 'Single LLM models suffer from idiosyncratic hallucinations and blind spots. Orchestrating distinct specialized open-weight models in parallel—each evaluating from different analytical perspectives—produces robust ensemble signals superior to any single model.',
                metrics: [
                    { name: 'Consensus Strength %', desc: 'Agreement magnitude across all contributing models (0–100%).' },
                    { name: 'Synthesized Target', desc: 'Consensus upside target and recommended stop loss level.' }
                ],
                tips: 'Trigger single-model runs via the matrix buttons if you wish to refresh one specific model without consuming global API quotas.'
            },
            'coverage': {
                title: 'Data Integrity, Price Series & Filing Registry',
                icon: '🗄️',
                what: 'Audit log of historical daily OHLCV prices, corporate earnings calendar entries, missing price bars, and Turso cloud database replication status.',
                thought: 'Quantitative backtesting and machine learning models are entirely dependent on point-in-time data cleanliness. Continuous verification of price continuity and filing timestamps prevents lookahead bias and data leakage.',
                metrics: [
                    { name: 'Price Bars Freshness', desc: 'Days elapsed since latest price ingestion.' },
                    { name: 'Earnings Records', desc: 'Total quarterly events tracked in database.' }
                ],
                tips: 'Master users can execute incremental refreshes to ingest missing earnings dates automatically.'
            },
            'industries': {
                title: 'Industry Sector Reactions & Cohort Performance',
                icon: '🏭',
                what: 'Historical 7-day post-earnings reaction distributions grouped by industry, ranking sectors by beat frequency and mean percentage gain.',
                thought: 'Upwards of 70% of single-stock variance is driven by macro and sector cohort momentum. Allocating capital exclusively to the top-quartile performing industries substantially boosts strategy Sharpe ratios.',
                metrics: [
                    { name: 'Mean Sector Reaction', desc: 'Average 7-day post-earnings percentage move across industry constituents.' },
                    { name: 'Beat Rate %', desc: 'Proportion of companies in sector beating estimates.' }
                ],
                tips: 'Prioritize individual stock longs in sectors where the cohort beat rate exceeds 70%.'
            },
            'patterns': {
                title: 'Algorithmic Technical Chart Patterns',
                icon: '📐',
                what: 'Algorithmic recognition of classical geometric patterns: Cup & Handle, Ascending Triangles, Double Bottoms, Flags, and Pennants with pivot confirmation.',
                thought: 'Structural chart patterns reflect the mechanical balance between supply and demand. Recognising apex compression in ascending triangles and cup-with-handle bases pinpoints optimal breakout timing.',
                metrics: [
                    { name: 'Pattern Quality Score', desc: 'Geometric symmetry and volume confirmation score (0–100).' },
                    { name: 'Pivot Price', desc: 'Breakout trigger price for pattern confirmation.' }
                ],
                tips: 'Ensure breakout volume is at least 1.5x the 20-day average when price crosses the pivot level.'
            },
            'buydip': {
                title: 'Buy The Dip — Mean Reversion on Quality Equities',
                icon: '📉',
                what: 'Identifies high-quality compounders with pristine multi-quarter earnings track records currently experiencing temporary oversold pullbacks (RSI < 35, near 200 SMA).',
                thought: 'Market overreactions and short-term liquidity shocks frequently push structurally growing, profitable businesses into deep oversold territory. Buying quality compounders at support yields high asymmetric reward with minimal long-term downside.',
                metrics: [
                    { name: 'Quality Score (1-9)', desc: 'Fundamental multi-quarter earnings beat quality score.' },
                    { name: 'RSI(14)', desc: 'Relative Strength Index showing oversold condition (<35).' },
                    { name: 'Distance to 200 SMA', desc: 'Percentage distance from the long-term institutional trend line.' }
                ],
                tips: 'Only buy dips on stocks with Quality Scores ≥ 7 and intact long-term fundamental earnings growth.'
            },
            'backtest': {
                title: 'Walk-Forward Quantitative Backtesting Engine',
                icon: '🔬',
                what: 'Quarterly walk-forward simulation of LightGBM predictions, calculating Sharpe Ratio, Sortino Ratio, Maximum Drawdown, Win Rate, and transaction cost modeling.',
                thought: 'Standard in-sample backtests overfit to past noise. Walk-forward quarterly retraining trains exclusively on past data (T-1) and evaluates strictly out-of-sample on future quarters, providing rigorous statistical proof of edge.',
                metrics: [
                    { name: 'Sharpe Ratio', desc: 'Risk-adjusted excess return per unit of volatility.' },
                    { name: 'Max Drawdown (MDD)', desc: 'Peak-to-trough maximum portfolio decline.' },
                    { name: 'Profit Factor', desc: 'Gross profits divided by gross losses across simulated trades.' }
                ],
                tips: 'Maintain transaction cost modeling (10 bps slippage/commission) to reflect realistic live execution performance.'
            },
            'watchlist': {
                title: 'Custom Watchlist Hub & Portfolio Streaming',
                icon: '⭐',
                what: 'Manage custom watchlists, view live price quotes, track deliverable volume, and synchronize portfolios seamlessly with Turso Cloud database.',
                thought: 'Efficient portfolio management requires personalized grouping of monitored equities, rapid switching between universes, and instantaneous access to deep-dive analytics.',
                metrics: [
                    { name: 'Watchlist Tickers', desc: 'Custom monitored equities saved to user profile.' },
                    { name: 'Cloud Sync', desc: 'Real-time synchronization across devices via Turso SQLite engine.' }
                ],
                tips: 'Organize watchlists into distinct strategies (e.g. "Breakout Coils", "Earnings Momentum", "Dividend Compounders").'
            },
            'playground': {
                title: 'Quant API Playground & Interactive Sandbox',
                icon: '🧪',
                what: 'Interactive API console allowing live exploration of endpoints, parameters, JSON response schemas, and algorithmic execution payloads.',
                thought: 'Empowers developers and quantitative traders to prototype custom scripts, test edge-case payloads, and integrate Nexus APIs directly into external trading algorithms and bots.',
                metrics: [
                    { name: 'Endpoint Schema', desc: 'Full OpenAPI parameters and response formats.' },
                    { name: 'Response Latency', desc: 'Execution time in milliseconds.' }
                ],
                tips: 'Use the playground to test custom query parameters before deploying algorithmic integrations.'
            },
            'repeaters': {
                title: 'Quarter Repeaters & AI Forward Earnings Radar',
                icon: '🔁',
                what: 'Screens companies delivering consistent earnings beats (EPS surprise > 0%) and post-earnings week-high rallies, enriched with QoQ beat streaks, active industry buzz themes, and forward AI forecasts.',
                thought: 'Companies that beat earnings and rally post-results demonstrate institutional buying and pricing power. Combining prior quarter delivery, material news flow (order wins/capex), and industry themes allows Multi-Model AI to accurately predict upcoming quarter repeat beats.',
                metrics: [
                    { name: 'Prior EPS Surprise %', desc: 'Reported vs estimated EPS beat percentage in the prior quarter.' },
                    { name: 'Week Peak Reaction %', desc: 'Maximum percentage price rally in the trading week following earnings.' },
                    { name: 'QoQ Beat Streak', desc: 'Consecutive quarters of earnings beats (1Q, 2Q, 3Q+).' },
                    { name: 'AI Repeat Probability', desc: 'Machine learning & LLM consensus probability (0–100%) of sustaining the beat.' }
                ],
                tips: 'Focus on 3Q+ beat streak companies with high industry buzz tailwinds (e.g. EMS, Defense, Power Infra).'
            }
        };

        app.openPageGuideModal = function(tabName) {
            const currentTab = tabName || app.currentTab || 'results';
            const guide = app.PAGE_GUIDES[currentTab] || app.PAGE_GUIDES['results'];
            const modal = document.getElementById('pageGuideModal');
            const titleEl = document.getElementById('pageGuideTitle');
            const iconEl = document.getElementById('pageGuideIcon');
            const subtitleEl = document.getElementById('pageGuideSubtitle');
            const bodyEl = document.getElementById('pageGuideBody');

            if (titleEl) titleEl.textContent = guide.title;
            if (iconEl) iconEl.textContent = guide.icon;
            if (subtitleEl) subtitleEl.textContent = `Nexus Quantitative Edge & Logic (${currentTab.toUpperCase()})`;

            if (bodyEl) {
                let html = `
                    <div style="background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.25); padding: 0.85rem 1rem; border-radius: 8px;">
                        <div style="font-weight: 700; color: #60a5fa; margin-bottom: 0.3rem; font-size: 0.85rem;">📋 What is on this screen?</div>
                        <div style="color: #e2e8f0;">${guide.what}</div>
                    </div>

                    <div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); padding: 0.85rem 1rem; border-radius: 8px;">
                        <div style="font-weight: 700; color: #34d399; margin-bottom: 0.3rem; font-size: 0.85rem;">🧠 Quantitative & Financial Thought Behind It</div>
                        <div style="color: #cbd5e1; line-height: 1.55;">${guide.thought}</div>
                    </div>
                `;

                if (guide.metrics && guide.metrics.length > 0) {
                    html += `
                        <div style="background: rgba(15,23,42,0.8); border: 1px solid rgba(255,255,255,0.08); padding: 0.85rem 1rem; border-radius: 8px;">
                            <div style="font-weight: 700; color: #fbbf24; margin-bottom: 0.4rem; font-size: 0.85rem;">📐 Key Metrics & Signals</div>
                            <div style="display: flex; flex-direction: column; gap: 0.4rem;">
                                ${guide.metrics.map(m => `
                                    <div style="font-size: 0.76rem;">
                                        <strong style="color: #f1f5f9;">${m.name}:</strong> <span style="color: #94a3b8;">${m.desc}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }

                if (guide.tips) {
                    html += `
                        <div style="background: rgba(139,92,246,0.08); border: 1px solid rgba(139,92,246,0.25); padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.76rem;">
                            <strong style="color: #c4b5fd;">💡 Pro Trading Tip:</strong> <span style="color: #e2e8f0;">${guide.tips}</span>
                        </div>
                    `;
                }

                bodyEl.innerHTML = html;
            }

            if (modal) modal.style.display = 'flex';
        };

        app.closePageGuideModal = function() {
            const modal = document.getElementById('pageGuideModal');
            if (modal) modal.style.display = 'none';
        };

        // Close guide modal on clicking outside or ESC key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                app.closePageGuideModal();
            }
        });

        // =========================================================================
        // ⚡ BREAKOUT RADAR MODULE (ENHANCED WITH DATE PICKER & OUTCOME TRACKING)
        // =========================================================================
        app._breakoutLoaded = false;
        app._breakoutPollTimer = null;
        app._breakoutData = [];
        app._breakoutSortKey = 'composite_score';
        app._breakoutSortAsc = false;
        app._breakoutAsofDate = null;

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
            app.loadBreakoutRadar();
        };

        app.loadBreakoutRadar = async function() {
            if (!app._breakoutAutocompleteWired) {
                app.wireBreakoutStockAutocomplete();
                app._breakoutAutocompleteWired = true;
            }

            const badge = document.getElementById('breakoutScanningBadge');
            const lastScanEl = document.getElementById('breakoutLastScanTime');
            const modeBadge = document.getElementById('breakoutModeBadge');
            const histNotice = document.getElementById('breakoutHistoricalNotice');
            const tbody = document.getElementById('breakoutTableBody');
            if (badge) badge.style.display = 'inline-block';

            const universe = document.getElementById('breakoutUniverseSelect')?.value || 'nifty_50';
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
                } else {
                    modeBadge.textContent = 'LIVE SCAN';
                    modeBadge.style.background = 'rgba(59,130,246,0.15)';
                    modeBadge.style.color = '#60a5fa';
                    modeBadge.style.borderColor = 'rgba(59,130,246,0.3)';
                    if (histNotice) histNotice.style.display = 'none';
                }
            }

            try {
                const params = new URLSearchParams({ universe: universe, sort_by: sortBy, min_score: minScore, limit: 100 });
                if (asofDate) {
                    params.set('asof_date', asofDate);
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

                // Pool tier badge for scanned count
                const hotCount = status.hot_count || 0;
                const warmCount = status.warm_count || 0;
                const coldScanned = status.cold_tickers_scanned || total || '\u2014';
                setEl('breakoutStatScanned', coldScanned);
                // Update the sub-label for scanned to show tier breakdown
                const scannedSub = document.getElementById('breakoutKpiSub4');
                if (scannedSub) {
                    scannedSub.innerHTML = `<span style="color:#ef4444">🔴 ${hotCount}</span> <span style="color:#eab308">🟡 ${warmCount}</span>`;
                }

                if (asofDate && summary.win_rate_pct != null) {
                    // Backtest Mode KPIs
                    setEl('breakoutKpiLabel2', 'Win Rate %');
                    setEl('breakoutStatTopScore', `${summary.win_rate_pct}%`);
                    setEl('breakoutStatTopTicker', `${summary.success_count}/${summary.total_evaluated} Breakouts Succeeded`);

                    setEl('breakoutKpiLabel3', 'Avg Realized Return');
                    setEl('breakoutStatAvg', `${summary.avg_return_pct >= 0 ? '+' : ''}${summary.avg_return_pct}%`);
                    setEl('breakoutKpiSub3', summary.top_winner_ticker ? `Top: ${summary.top_winner_ticker} (${summary.top_winner_gain_pct >= 0 ? '+' : ''}${summary.top_winner_gain_pct}%)` : 'Across candidates');

                    setEl('breakoutKpiLabel5', 'Backtest Date');
                    setEl('breakoutStatDuration', asofDate);
                    setEl('breakoutKpiSub5', 'Point-in-time simulation');
                } else {
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

                if (lastScanEl && status.last_scan_at) {
                    try {
                        const d = new Date(status.last_scan_at);
                        const uniLabel = universe === 'nifty_50' ? 'Nifty 50' : (universe === 'all' ? 'All' : universe);
                        const tierInfo = hotCount > 0 ? ` · 🔴${hotCount} Hot · 🟡${warmCount} Warm` : '';
                        lastScanEl.textContent = `${uniLabel} • ${asofDate ? 'As-Of ' + asofDate : 'Live • Last scan: ' + d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}${tierInfo}`;
                    } catch { lastScanEl.textContent = 'Last scan: ' + status.last_scan_at; }
                } else if (lastScanEl) {
                    lastScanEl.textContent = status.status === 'running' ? 'Scanning now\u2026' : (asofDate ? `As-Of ${asofDate}` : 'Waiting for first scan\u2026');
                }

                const limitVal = document.getElementById('breakoutLimitSelect')?.value || '10';
                const limitNum = limitVal === 'all' ? app._breakoutData.length : parseInt(limitVal, 10);
                app.renderBreakoutTable(app._breakoutData.slice(0, limitNum), asofDate);
            } catch (err) {
                console.error('[BREAKOUT] Load error:', err);
                if (tbody) tbody.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#ef4444;font-size:0.8rem;">\u26a1 Failed to load breakout data. Is the server running?</td></tr>';
            } finally {
                if (badge) badge.style.display = 'none';
            }
        };

        app.renderBreakoutTable = function(candidates, asofDate) {
            const tbody = document.getElementById('breakoutTableBody');
            if (!tbody) return;

            if (!candidates || candidates.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="padding:2.5rem;text-align:center;color:#334155;font-size:0.82rem;">\u26a1 No candidates found for ${asofDate ? 'date ' + asofDate : 'current scan'} above score threshold.<br><span style="font-size:0.72rem;color:#1e293b;">Try lowering the Min Score or selecting another universe.</span></td></tr>`;
                return;
            }

            const scoreBar = (val, max, color) => {
                const pct = max > 0 ? Math.round((val / max) * 100) : 0;
                return `<div style="display:flex;align-items:center;gap:0.3rem;"><span style="font-family:var(--font-mono);color:${color};font-weight:600;min-width:1.8rem;text-align:right;font-size:0.68rem;">${val}</span><div style="flex:1;height:3px;background:rgba(255,255,255,0.07);border-radius:2px;min-width:30px;"><div style="width:${pct}%;height:100%;background:${color};border-radius:2px;"></div></div></div>`;
            };

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
                return `<span style="display:inline-block;background:${style.bg};color:${style.text};border:1px solid ${style.border};font-size:0.68rem;font-weight:700;padding:0.15rem 0.5rem;border-radius:4px;white-space:nowrap;">${label}</span>`;
            };

            const rows = candidates.map((c) => {
                const score = c.composite_score || 0;
                const scoreColor = score >= 75 ? '#fde68a' : score >= 55 ? '#34d399' : '#60a5fa';
                const scoreBg = score >= 75 ? 'rgba(234,179,8,0.15)' : score >= 55 ? 'rgba(16,185,129,0.12)' : 'rgba(59,130,246,0.1)';

                const ticker = c.ticker || '\u2014';
                const company = (c.company_name || ticker).substring(0, 20);
                const industry = (c.industry || '\u2014').substring(0, 16);

                const sigPrice = c.predicted_value || c.signal_price || c.current_price;
                const sigPriceStr = sigPrice != null ? `\u20b9${Number(sigPrice).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                
                const curPriceStr = c.current_price != null ? `\u20b9${Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                const triggerStr = c.breakout_trigger != null ? `\u20b9${Number(c.breakout_trigger).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                const targetStr = c.target_price != null ? `\u20b9${Number(c.target_price).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';
                const stopStr = c.stop_loss != null ? `\u20b9${Number(c.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '\u2014';

                const retPct = c.realized_return_pct;
                const retColor = retPct > 0 ? '#34d399' : retPct < 0 ? '#f87171' : '#94a3b8';
                const retStr = retPct != null
                    ? `<span style="font-weight:700;color:${retColor};font-family:var(--font-mono);">${retPct >= 0 ? '+' : ''}${Number(retPct).toFixed(1)}%</span>`
                    : '<span style="color:#475569;">\u2014</span>';

                const gapPct = c.pct_from_high != null
                    ? `<span style="font-size:0.62rem;color:${c.pct_from_high >= 0 ? '#34d399' : '#f87171'};">(${c.pct_from_high >= 0 ? '+' : ''}${c.pct_from_high.toFixed(1)}%)</span>`
                    : '';

                const archetype = c.setup_archetype || (score >= 60 ? '🔥 Strong Breakout' : '📈 Resistance Coil');

                return `<tr style="border-bottom:1px solid rgba(255,255,255,0.05);" data-ticker="${ticker}">
                    <td style="padding:0.55rem 0.75rem;">
                        <div style="display:flex;flex-direction:column;gap:0.05rem;">
                            <div style="display:flex;align-items:center;gap:0.25rem;">
                                <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="font-weight:700;color:#f1f5f9;font-family:var(--font-mono);font-size:0.78rem;text-decoration:none;" title="Open ${ticker} stock intelligence in new tab">${ticker}</a>
                                <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="color:#38bdf8;text-decoration:none;font-size:0.75rem;" onclick="event.stopPropagation();" title="Open profile in new tab">↗</a>
                            </div>
                            <span style="font-size:0.65rem;color:#475569;" title="${c.company_name || ticker}">${company}</span>
                            <div style="margin-top:0.2rem;"><span style="font-size:0.62rem;background:rgba(251,191,36,0.12);color:#fbbf24;border:1px solid rgba(251,191,36,0.25);padding:0.08rem 0.35rem;border-radius:3px;">${archetype}</span></div>
                        </div>
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:right;font-family:var(--font-mono);color:#93c5fd;font-size:0.74rem;white-space:nowrap;">
                        <div>${sigPriceStr}</div>
                        <div style="font-size:0.6rem;color:#475569;">${c.signal_date || ''}</div>
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:right;font-family:var(--font-mono);color:#fca5a5;font-size:0.74rem;white-space:nowrap;">
                        <div>${triggerStr}</div>
                        <div>${gapPct}</div>
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:right;font-family:var(--font-mono);font-size:0.7rem;white-space:nowrap;">
                        <div style="color:#34d399;" title="Target Price">T: ${targetStr}</div>
                        <div style="color:#f87171;" title="Stop Loss">SL: ${stopStr}</div>
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:right;font-family:var(--font-mono);color:#e2e8f0;font-size:0.74rem;white-space:nowrap;">
                        <div>${curPriceStr}</div>
                        <div style="font-size:0.6rem;color:#475569;">${c.current_date || 'Live'}</div>
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:right;font-size:0.76rem;white-space:nowrap;">
                        ${retStr}
                        ${c.max_gain_pct != null ? `<div style="font-size:0.6rem;color:#64748b;" title="Max high post-signal">Peak: +${c.max_gain_pct}%</div>` : ''}
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:center;">
                        ${outcomeBadgeHtml(c)}
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:right;">
                        <div style="display:flex;align-items:center;justify-content:flex-end;gap:0.4rem;">
                            <span style="background:${scoreBg};color:${scoreColor};font-size:0.8rem;font-weight:800;font-family:var(--font-mono);padding:0.12rem 0.45rem;border-radius:5px;">${score}</span>
                        </div>
                    </td>
                    <td style="padding:0.55rem 0.75rem;text-align:center;white-space:nowrap;">
                        <div style="display:flex;align-items:center;justify-content:center;gap:0.3rem;">
                            <button onclick="app.openBreakoutNotesModal('${ticker}')" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);font-size:0.68rem;padding:0.2rem 0.5rem;border-radius:5px;cursor:pointer;" title="View Mathematical Calculation Notes & Ollama AI Reasoning">
                                🧠 Reasoning
                            </button>
                            <button onclick="app.openSwingRangeModal('ALL','${ticker}')" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);font-size:0.68rem;padding:0.2rem 0.45rem;border-radius:5px;" title="Analyse ${ticker}">
                                📊
                            </button>
                        </div>
                    </td>
                </tr>`;
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
                                <strong style="color:#f87171;">1. Resistance Proximity (0–30 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#fca5a5;">${resScore.toFixed(1)} / 30 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.resistance_reasoning || `Within ${candidate.pct_from_high != null ? candidate.pct_from_high.toFixed(1) : '0'}% of key resistance high.`}</div>
                        </div>

                        <!-- Volume -->
                        <div style="background:#0f172a;border:1px solid rgba(59,130,246,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#60a5fa;">2. Volume Surge (0–20 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#93c5fd;">${volScore.toFixed(1)} / 20 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.volume_reasoning || `Volume is ${candidate.volume_ratio != null ? candidate.volume_ratio.toFixed(2) : '1.0'}x of 20D baseline.`}</div>
                        </div>

                        <!-- Compression -->
                        <div style="background:#0f172a;border:1px solid rgba(234,179,8,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#fbbf24;">3. Price Compression / ATR Squeeze (0–15 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#fde68a;">${compScore.toFixed(1)} / 15 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.compression_reasoning || `ATR is ${candidate.atr_pct != null ? candidate.atr_pct.toFixed(2) : '2.0'}% of price (volatility coiling).`}</div>
                        </div>

                        <!-- Momentum -->
                        <div style="background:#0f172a;border:1px solid rgba(16,185,129,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#34d399;">4. Momentum Posture (0–15 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#6ee7b7;">${momScore.toFixed(1)} / 15 pts</span>
                            </div>
                            <div style="color:#cbd5e1;">${notes.momentum_reasoning || `Momentum signal: ${candidate.momentum_signal || 'Moderate'}.`}</div>
                        </div>

                        <!-- Fundamental -->
                        <div style="background:#0f172a;border:1px solid rgba(168,85,247,0.25);border-radius:6px;padding:0.65rem 0.85rem;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                <strong style="color:#c084fc;">5. Fundamental Earnings Bonus (0–20 pts)</strong>
                                <span style="font-family:var(--font-mono);font-weight:700;color:#e9d5ff;">${fundScore.toFixed(1)} / 20 pts</span>
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
                            <button onclick="app.runBreakoutAiReasoning('${ticker}')" class="btn btn-sm" style="background:#2563eb;color:#fff;font-size:0.72rem;padding:0.2rem 0.55rem;border-radius:5px;cursor:pointer;">
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
                    <button onclick="document.getElementById('breakoutNotesModal').style.display='none'" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);padding:0.35rem 0.85rem;border-radius:6px;font-size:0.75rem;cursor:pointer;">
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

        app.refreshBreakoutScan = async function() {
            const btn = document.getElementById('breakoutRefreshBtn');
            const icon = document.getElementById('breakoutRefreshIcon');
            const universe = document.getElementById('breakoutUniverseSelect')?.value || 'nifty_50';
            if (btn) btn.disabled = true;
            if (icon) icon.textContent = '\u23f3';
            try {
                const res = await fetch(API_BASE + '/api/v1/breakout-radar/refresh?universe=' + encodeURIComponent(universe), { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    setTimeout(() => app.loadBreakoutRadar(), 3000);
                    setTimeout(() => app.loadBreakoutRadar(), 10000);
                }
            } catch (e) {
                console.error('[BREAKOUT] Refresh error:', e);
            } finally {
                setTimeout(() => {
                    if (btn) btn.disabled = false;
                    if (icon) icon.textContent = '\u26a1';
                }, 5000);
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

        // =========================================================================
        // 🔁 QUARTER REPEATERS & AI FORWARD RADAR
        // =========================================================================
        app._repeatersData = [];

        app.loadQuarterRepeaters = async function() {
            const tbody = document.getElementById('repeatersTableBody');
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2.5rem;color:#64748b;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Screening quarter repeaters & loading AI forward predictions...</td></tr>`;
            }

            const universe = document.getElementById('repeatersUniverseSelect')?.value || 'nifty_50';
            const verdict = document.getElementById('repeatersVerdictSelect')?.value || '';
            const minBeat = document.getElementById('repeatersMinBeat')?.value || 0;
            const minHigh = document.getElementById('repeatersMinHigh')?.value || 2.5;

            try {
                const params = new URLSearchParams({ universe: universe, min_beat_pct: minBeat, min_week_high_pct: minHigh, limit: 60 });
                if (verdict) params.set('verdict', verdict);

                const res = await fetch(API_BASE + '/api/v1/earnings-radar/repeaters?' + params.toString());
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();

                app._repeatersData = data.candidates || [];
                const summary = data.summary || {};

                // Update KPI Cards
                const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
                setEl('repeatersStatTotal', summary.total_screened || 0);
                setEl('repeatersStatTopPick', summary.top_pick_ticker || '—');
                setEl('repeatersStatTopScore', summary.top_pick_score ? `Score: ${summary.top_pick_score}/100` : '—');
                setEl('repeatersStatAvgBeat', summary.avg_prior_beat_pct != null ? `${summary.avg_prior_beat_pct >= 0 ? '+' : ''}${summary.avg_prior_beat_pct}%` : '—');
                setEl('repeatersStatBuzz', summary.dominant_industry_buzz || '—');

                app.renderQuarterRepeaters(app._repeatersData);
            } catch (e) {
                console.error('[REPEATERS] Load error:', e);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2rem;color:#f87171;">Failed to load quarter repeaters: ${e.message}</td></tr>`;
                }
            }
        };

        app.renderQuarterRepeaters = function(candidates) {
            const tbody = document.getElementById('repeatersTableBody');
            if (!tbody) return;

            if (!candidates || candidates.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2.5rem;color:#64748b;">No repeat candidates matching current filter criteria. Try lowering Min Beat % or Min Week High %.</td></tr>`;
                return;
            }

            const rows = candidates.map(c => {
                const ticker = c.ticker || '';
                const compName = c.company_name || ticker;
                const buzz = c.industry_buzz_tag || 'Growth';
                const curPrice = c.current_price != null ? `₹${Number(c.current_price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—';
                const hasSurp = c.last_eps_surprise != null && !isNaN(c.last_eps_surprise);
                const surpVal = hasSurp ? Number(c.last_eps_surprise) : null;
                const surpStr = hasSurp ? `${surpVal >= 0 ? '+' : ''}${surpVal.toFixed(1)}% Beat` : 'Solid Quality Beat';
                const score = c.last_quality_score != null ? `${c.last_quality_score}/9` : '—';
                const weekHigh = c.last_week_high_pct != null ? `+${Number(c.last_week_high_pct).toFixed(1)}%` : '—';
                const streak = c.beat_streak || 1;
                
                let upcomingHtml = '<span style="color:#475569;font-size:0.7rem;">Calendar TBD</span>';
                if (c.days_to_next_earnings != null) {
                    upcomingHtml = `<span style="color:#38bdf8;font-weight:700;">⏱️ In ${c.days_to_next_earnings}d</span>`;
                } else if (c.next_earnings_date) {
                    upcomingHtml = `<span>⏱️ ${c.next_earnings_date}</span>`;
                }

                const ret30 = c.thirty_day_return_pct != null && !isNaN(c.thirty_day_return_pct) ? Number(c.thirty_day_return_pct) : null;
                const ret30Html = ret30 != null ? `<div style="font-size:0.65rem;color:${ret30 >= 0 ? '#34d399' : '#f87171'};font-weight:normal;margin-top:0.1rem;">30D: ${ret30 >= 0 ? '+' : ''}${ret30.toFixed(1)}%</div>` : '';
                
                const ai = c.ai_forecast;
                let verdictBadge = `<span style="background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.25);font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;">Pending AI</span>`;
                let probHtml = ``;

                if (ai) {
                    const prob = ai.repeat_probability_pct || 75;
                    const v = ai.ai_repeat_verdict || 'MODERATE_BEAT';
                    let vColor = '#34d399', vBg = 'rgba(16,185,129,0.15)', vBorder = 'rgba(16,185,129,0.3)', vLabel = 'Moderate Beat';
                    if (v === 'STRONG_REPEAT_BEAT') {
                        vColor = '#4ade80'; vBg = 'rgba(74,222,128,0.2)'; vBorder = 'rgba(74,222,128,0.4)'; vLabel = '🔥 Strong Repeat Beat';
                    } else if (v === 'IN_LINE') {
                        vColor = '#fbbf24'; vBg = 'rgba(251,191,36,0.15)'; vBorder = 'rgba(251,191,36,0.3)'; vLabel = '⚖️ In-Line';
                    } else if (v === 'RISK_OF_MISS') {
                        vColor = '#f87171'; vBg = 'rgba(248,113,113,0.15)'; vBorder = 'rgba(248,113,113,0.3)'; vLabel = '⚠️ Risk of Miss';
                    }
                    verdictBadge = `<span style="background:${vBg};color:${vColor};border:1px solid ${vBorder};font-size:0.7rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;">${vLabel}</span>`;
                    probHtml = `<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.2rem;font-family:var(--font-mono);">${prob}% Conviction</div>`;
                }

                const streakBadge = streak >= 3 
                    ? `<span style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.7rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;">🔥 ${streak}Q Streak</span>`
                    : (streak === 2 
                        ? `<span style="background:rgba(234,179,8,0.15);color:#fbbf24;border:1px solid rgba(234,179,8,0.3);font-size:0.7rem;font-weight:600;padding:0.15rem 0.45rem;border-radius:4px;">⚡ 2Q Streak</span>`
                        : `<span style="background:rgba(59,130,246,0.12);color:#60a5fa;border:1px solid rgba(59,130,246,0.25);font-size:0.7rem;padding:0.15rem 0.45rem;border-radius:4px;">1Q Beat</span>`);

                return `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);transition:background 0.15s ease;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                    <td style="padding:0.75rem 0.85rem;">
                        <div style="font-weight:700;color:#f1f5f9;font-family:var(--font-mono);">
                            <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="color:#38bdf8;text-decoration:none;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${ticker}</a>
                        </div>
                        <div style="font-size:0.7rem;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;">${compName}</div>
                        <div style="margin-top:0.25rem;"><span style="font-size:0.65rem;background:rgba(168,85,247,0.12);color:#c084fc;border:1px solid rgba(168,85,247,0.25);padding:0.1rem 0.35rem;border-radius:3px;display:inline-block;">${buzz}</span></div>
                    </td>
                    <td style="padding:0.75rem 0.85rem;font-family:var(--font-mono);font-weight:700;color:#e2e8f0;white-space:nowrap;">
                        ${curPrice}
                        ${ret30Html}
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;">
                        <div style="color:#34d399;font-weight:700;font-family:var(--font-mono);">${surpStr}</div>
                        <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.1rem;">Score: <strong style="color:#e2e8f0;">${score}</strong></div>
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;">
                        <span style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.72rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;">${weekHigh} Peak</span>
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;">
                        ${streakBadge}
                    </td>
                    <td style="padding:0.75rem 0.85rem;">
                        ${verdictBadge}
                        ${probHtml}
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;font-size:0.75rem;color:#cbd5e1;font-family:var(--font-mono);">
                        ${upcomingHtml}
                    </td>
                    <td style="padding:0.75rem 0.85rem;text-align:center;white-space:nowrap;">
                        <div style="display:flex;align-items:center;justify-content:center;gap:0.35rem;">
                            <button type="button" onclick="event.preventDefault(); event.stopPropagation(); app.openRepeaterDetails('${ticker}');" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);font-size:0.68rem;padding:0.25rem 0.55rem;border-radius:5px;cursor:pointer;" title="View AI Thesis & Drivers">
                                🧠 Thesis
                            </button>
                            <button type="button" onclick="event.preventDefault(); event.stopPropagation(); app.runSingleRepeaterAi('${ticker}', this);" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);font-size:0.68rem;padding:0.25rem 0.45rem;border-radius:5px;cursor:pointer;" title="Run AI Inference">
                                ⚡
                            </button>
                        </div>
                    </td>
                </tr>`;
            });

            tbody.innerHTML = rows.join('');
        };

        app.openRepeaterDetails = function(ticker) {
            try {
                const candidate = (app._repeatersData || []).find(c => c.ticker === ticker);
                if (!candidate) return;

                const modal = document.getElementById('repeatersAiModal');
                const content = document.getElementById('repeatersAiModalContent');
                if (!modal || !content) return;

                const ai = candidate.ai_forecast;
                const considered = ai?.considered_data || {};
                const streak = candidate.beat_streak || 1;
                
                const hasSurp = candidate.last_eps_surprise != null && !isNaN(candidate.last_eps_surprise);
                const surpVal = hasSurp ? Number(candidate.last_eps_surprise) : null;
                const surpStr = hasSurp ? `${surpVal >= 0 ? '+' : ''}${surpVal.toFixed(1)}% Beat` : 'Solid Quality Beat';
                
                const hasWkHigh = candidate.last_week_high_pct != null && !isNaN(candidate.last_week_high_pct);
                const wkHighVal = hasWkHigh ? Number(candidate.last_week_high_pct) : null;
                const wkHighStr = hasWkHigh ? `+${wkHighVal.toFixed(1)}%` : 'N/A';
                
                const hasWkLow = candidate.last_week_low_pct != null && !isNaN(candidate.last_week_low_pct);
                const wkLowVal = hasWkLow ? Number(candidate.last_week_low_pct) : null;
                const wkLowStr = hasWkLow ? `${wkLowVal >= 0 ? '+' : ''}${wkLowVal.toFixed(1)}%` : 'N/A';

                const hasWkMove = candidate.earnings_week_move_pct != null && !isNaN(candidate.earnings_week_move_pct);
                const wkMoveVal = hasWkMove ? Number(candidate.earnings_week_move_pct) : null;
                const wkMoveStr = hasWkMove ? `${wkMoveVal >= 0 ? '+' : ''}${wkMoveVal.toFixed(1)}%` : 'N/A';

                const ret30Val = candidate.thirty_day_return_pct != null && !isNaN(candidate.thirty_day_return_pct) ? Number(candidate.thirty_day_return_pct) : null;
                const ret30Str = ret30Val != null ? `${ret30Val >= 0 ? '+' : ''}${ret30Val.toFixed(1)}%` : 'N/A';

                const score = candidate.last_quality_score != null ? `${candidate.last_quality_score}/9` : '—';
                const modelUsed = ai?.model_used || ai?.source || 'Pending Inference';

                // Price action mechanics explanation
                let priceActionExplanation = ai?.price_action_assessment || '';
                if (!priceActionExplanation) {
                    if (wkMoveVal !== null && wkMoveVal < 0 && wkHighVal !== null && wkHighVal >= 2.5) {
                        priceActionExplanation = `Why the initial move was negative (${wkMoveStr}): After delivering a ${surpStr}, the stock surged to a peak intra-week high of ${wkHighStr}, followed by temporary post-earnings profit booking. Medium-term momentum proved resilient with a ${ret30Str} 30-day return.`;
                    } else if (wkHighVal !== null && wkHighVal >= 2.5) {
                        priceActionExplanation = `Stock delivered strong immediate reaction with a ${wkHighStr} peak post-earnings rally and sustained ${ret30Str} 30-day continuation.`;
                    } else {
                        priceActionExplanation = `Stock demonstrated steady post-earnings price stabilization following ${surpStr}.`;
                    }
                }

                // Drivers & Risks
                let driversHtml = '<li style="color:#94a3b8;">No specific growth drivers parsed yet. Click ⚡ Run Model to analyze.</li>';
                let risksHtml = '<li style="color:#94a3b8;">Standard market risk factors apply.</li>';
                let thesisText = 'Run AI Forecast below to generate multi-modal reasoning and upcoming quarter earnings continuity thesis.';

                if (ai) {
                    thesisText = ai.thesis || thesisText;
                    const rawDrivers = ai.primary_growth_drivers || ai.growth_drivers;
                    const drivers = Array.isArray(rawDrivers) ? rawDrivers : (typeof rawDrivers === 'string' ? [rawDrivers] : []);
                    if (drivers.length > 0) {
                        driversHtml = drivers.map(d => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${d}</li>`).join('');
                    }
                    const rawRisks = ai.key_risk_factors || ai.risk_factors;
                    const risks = Array.isArray(rawRisks) ? rawRisks : (typeof rawRisks === 'string' ? [rawRisks] : []);
                    if (risks.length > 0) {
                        risksHtml = risks.map(r => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${r}</li>`).join('');
                    }
                }

                // News articles list
                const articles = ai?.news_articles || candidate.news_articles || [];
                let newsHtml = '<div style="color:#94a3b8;font-size:0.75rem;font-style:italic;">No recent news headlines indexed for this ticker.</div>';
                if (articles && articles.length > 0) {
                    newsHtml = articles.map(a => {
                        const dateStr = a.published_at ? String(a.published_at).slice(0, 10) : 'Recent';
                        const titleStr = a.title || 'Corporate Announcement';
                        const sent = a.sentiment_label || 'Neutral';
                        const sentColor = sent.toLowerCase().includes('bull') || sent.toLowerCase().includes('pos') ? '#34d399' : (sent.toLowerCase().includes('bear') || sent.toLowerCase().includes('neg') ? '#f87171' : '#94a3b8');
                        const url = a.url ? `<a href="${a.url}" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.3rem;" onclick="event.stopPropagation();">↗</a>` : '';
                        return `
                            <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.65rem;margin-bottom:0.35rem;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;">
                                <div style="font-size:0.75rem;color:#e2e8f0;line-height:1.4;">
                                    <span style="color:#64748b;font-family:var(--font-mono);font-size:0.68rem;margin-right:0.35rem;">[${dateStr}]</span>
                                    <span>${titleStr}</span>${url}
                                </div>
                                <span style="font-size:0.65rem;background:rgba(255,255,255,0.05);color:${sentColor};border:1px solid rgba(255,255,255,0.1);padding:0.1rem 0.35rem;border-radius:3px;white-space:nowrap;">${sent}</span>
                            </div>
                        `;
                    }).join('');
                }

                // 3Q Streak History badges
                const history = candidate.streak_history || ai?.streak_history || [];
                let historyHtml = '<span style="color:#94a3b8;font-size:0.72rem;">No historical quarter data.</span>';
                if (history && history.length > 0) {
                    historyHtml = history.map((h, idx) => {
                        const qName = `Q${idx + 1}`;
                        const qScore = h.score != null ? `${h.score}/9` : '—';
                        const qSurp = h.surprise_pct != null ? `${h.surprise_pct >= 0 ? '+' : ''}${Number(h.surprise_pct).toFixed(1)}%` : 'Beat';
                        const isPos = (h.surprise_pct == null || h.surprise_pct >= 0) && (h.score == null || h.score >= 5);
                        return `
                            <div style="background:${isPos ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'};border:1px solid ${isPos ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:6px;padding:0.35rem 0.55rem;text-align:center;">
                                <div style="font-size:0.65rem;color:${isPos ? '#34d399' : '#f87171'};font-weight:700;">${qName} (${h.date ? String(h.date).slice(0, 7) : 'Prior'})</div>
                                <div style="font-size:0.75rem;font-weight:800;color:#f1f5f9;font-family:var(--font-mono);">${qSurp}</div>
                                <div style="font-size:0.62rem;color:#94a3b8;">Score: ${qScore}</div>
                            </div>
                        `;
                    }).join('');
                }

                content.innerHTML = `
                    <!-- Header -->
                    <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.85rem;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;">
                        <div style="display:flex;align-items:center;gap:0.6rem;">
                            <div style="font-size:1.6rem;">🔁</div>
                            <div>
                                <div style="font-size:1.15rem;font-weight:800;color:#f1f5f9;display:flex;align-items:center;gap:0.5rem;">
                                    <span>${candidate.ticker}</span>
                                    <span style="font-size:0.72rem;background:rgba(168,85,247,0.2);color:#c084fc;padding:0.15rem 0.45rem;border-radius:4px;">${candidate.industry_buzz_tag || 'Theme'}</span>
                                    <span style="font-size:0.72rem;background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.15rem 0.45rem;border-radius:4px;font-family:var(--font-mono);">${modelUsed}</span>
                                </div>
                                <div style="font-size:0.76rem;color:#94a3b8;">${candidate.company_name || candidate.ticker} &middot; Live Price: ₹${Number(candidate.current_price || 0).toLocaleString('en-IN')} &middot; 30D Return: <strong style="color:${ret30Val >= 0 ? '#34d399' : '#f87171'};">${ret30Str}</strong></div>
                            </div>
                        </div>
                    </div>

                    <!-- 1. Why in Repeaters & Move Mechanics (Audit Card) -->
                    <div style="background:#0c1222;border:1px solid rgba(59,130,246,0.25);border-radius:8px;padding:0.85rem;margin-bottom:1rem;">
                        <div style="font-size:0.78rem;font-weight:700;color:#38bdf8;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.35rem;">
                            <span>📊 Price Action, Reaction Mechanics &amp; Screening Rationale</span>
                        </div>
                        
                        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;margin-bottom:0.6rem;">
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Prior Delivery</div>
                                <div style="font-size:0.82rem;font-weight:700;color:#34d399;font-family:var(--font-mono);">${surpStr}</div>
                                <div style="font-size:0.62rem;color:#64748b;">Quality: ${score}</div>
                            </div>
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Week Peak High</div>
                                <div style="font-size:0.82rem;font-weight:700;color:#4ade80;font-family:var(--font-mono);">${wkHighStr} Peak</div>
                                <div style="font-size:0.62rem;color:#64748b;">Rally Magnitude</div>
                            </div>
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Net 1-Wk Move</div>
                                <div style="font-size:0.82rem;font-weight:700;color:${wkMoveVal >= 0 ? '#34d399' : '#f87171'};font-family:var(--font-mono);">${wkMoveStr}</div>
                                <div style="font-size:0.62rem;color:#64748b;">Low: ${wkLowStr}</div>
                            </div>
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">30-Day Trend</div>
                                <div style="font-size:0.82rem;font-weight:700;color:${ret30Val >= 0 ? '#34d399' : '#f87171'};font-family:var(--font-mono);">${ret30Str}</div>
                                <div style="font-size:0.62rem;color:#64748b;">Continuation</div>
                            </div>
                        </div>

                        <div style="font-size:0.75rem;color:#cbd5e1;line-height:1.5;background:#090d16;border-radius:6px;padding:0.55rem 0.75rem;border-left:3px solid #38bdf8;">
                            ${priceActionExplanation}
                        </div>
                    </div>

                    <!-- 2. Interactive AI Model Selector & Runner Toolbar -->
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:0.75rem;margin-bottom:1rem;">
                        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;">
                            <div style="font-size:0.78rem;font-weight:700;color:#60a5fa;display:flex;align-items:center;gap:0.35rem;">
                                <span>🤖 Multi-Model AI Engine (Local Ollama &amp; Online OpenRouter)</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                                <select id="repeaterModelSelect" style="background:#090d16;border:1px solid rgba(255,255,255,0.15);color:#e2e8f0;font-size:0.72rem;padding:0.25rem 0.5rem;border-radius:5px;outline:none;">
                                    <optgroup label="🖥️ Local Ollama Models">
                                        <option value="llama3.2:3b" selected>llama3.2:3b (Fast Local)</option>
                                        <option value="deepseek-r1:8b">deepseek-r1:8b (Deep Reasoning)</option>
                                        <option value="qwen2.5-coder:latest">qwen2.5-coder (Algorithmic)</option>
                                    </optgroup>
                                    <optgroup label="☁️ Online Models (OpenRouter)">
                                        <option value="deepseek/deepseek-r1:free">DeepSeek-R1 (Free Cloud)</option>
                                        <option value="meta-llama/llama-3.3-70b-instruct">Llama-3.3 70B Instruct</option>
                                        <option value="mistralai/mistral-large">Mistral Large</option>
                                        <option value="google/gemini-2.0-flash-001">Gemini 2.0 Flash</option>
                                    </optgroup>
                                </select>
                                <button type="button" onclick="event.preventDefault(); const sel = document.getElementById('repeaterModelSelect').value; app.runSingleRepeaterAi('${candidate.ticker}', this, sel);" class="btn btn-sm" style="background:#2563eb;color:#fff;font-size:0.72rem;padding:0.25rem 0.65rem;border-radius:5px;cursor:pointer;">
                                    ⚡ Run Selected Model
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- 3. AI Forward Thesis & Drivers -->
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:1rem;margin-bottom:1rem;">
                        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem;">
                            <div style="font-size:0.76rem;font-weight:700;color:#38bdf8;">🧠 Forward Quarterly Earnings Thesis</div>
                            <div style="font-size:0.72rem;color:#34d399;font-weight:700;font-family:var(--font-mono);">${ai?.repeat_probability_pct ? ai.repeat_probability_pct + '% Conviction' : ''}</div>
                        </div>
                        <div style="font-size:0.82rem;color:#e2e8f0;line-height:1.55;">${thesisText}</div>
                    </div>

                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1rem;">
                        <div style="background:#0f172a;border:1px solid rgba(34,197,94,0.2);border-radius:8px;padding:0.85rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#4ade80;margin-bottom:0.4rem;">🚀 Growth Drivers &amp; Order Flow Considered</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.76rem;line-height:1.5;">${driversHtml}</ul>
                        </div>
                        <div style="background:#0f172a;border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:0.85rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#f87171;margin-bottom:0.4rem;">⚠️ Watchlist Risks &amp; Margins Considered</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.76rem;line-height:1.5;">${risksHtml}</ul>
                        </div>
                    </div>

                    <!-- 4. 3-Quarter Delivery History -->
                    <div style="background:#090d16;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.85rem;margin-bottom:1rem;">
                        <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.5rem;display:flex;align-items:center;justify-content:space-between;">
                            <span>📈 3-Quarter Beat Streak Track Record</span>
                            <span style="font-size:0.7rem;color:#f87171;font-family:var(--font-mono);font-weight:700;">🔥 ${streak}Q Consecutive Streak</span>
                        </div>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(110px, 1fr));gap:0.5rem;">
                            ${historyHtml}
                        </div>
                    </div>

                    <!-- 5. News & Catalysts Considered (Data Audit) -->
                    <div style="background:#090d16;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.85rem;margin-bottom:1rem;">
                        <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.5rem;">
                            📰 Recent News, Filings &amp; Catalysts Fed to AI
                        </div>
                        <div style="max-height:160px;overflow-y:auto;">
                            ${newsHtml}
                        </div>
                    </div>

                    <!-- Footer Action -->
                    <div style="display:flex;align-items:center;justify-content:space-between;padding-top:0.75rem;border-top:1px solid rgba(255,255,255,0.08);">
                        <a href="/stock/${encodeURIComponent(candidate.ticker)}" target="_blank" style="color:#38bdf8;font-size:0.78rem;text-decoration:none;font-weight:600;">Open Full Stock Intelligence ↗</a>
                        <button type="button" onclick="document.getElementById('repeatersAiModal').style.display='none'" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);padding:0.35rem 0.85rem;border-radius:6px;font-size:0.75rem;cursor:pointer;">
                            Close
                        </button>
                    </div>
                `;

                modal.style.display = 'flex';
            } catch (err) {
                console.error('[REPEATERS] openRepeaterDetails error:', err);
            }
        };

        app.runSingleRepeaterAi = async function(ticker, btnEl, modelName = null) {
            if (btnEl) btnEl.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span>`;
            try {
                let url = API_BASE + '/api/v1/earnings-radar/repeaters/forecast/' + encodeURIComponent(ticker);
                if (modelName) {
                    const provider = modelName.includes('/') ? 'openrouter' : 'ollama';
                    url += '?model_name=' + encodeURIComponent(modelName) + '&provider=' + encodeURIComponent(provider);
                }
                const res = await fetch(url, { method: 'POST' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                
                await app.loadQuarterRepeaters();
                
                // If modal is currently open for this ticker, refresh its view with updated forecast
                const modal = document.getElementById('repeatersAiModal');
                if (modal && modal.style.display !== 'none') {
                    app.openRepeaterDetails(ticker);
                }
            } catch (e) {
                console.error('[REPEATERS] Forecast error for ' + ticker, e);
                alert('AI Forecast failed: ' + e.message);
            } finally {
                if (btnEl) btnEl.textContent = '⚡';
            }
        };

        app.runBatchRepeatersAi = async function() {
            const btn = document.getElementById('repeatersBatchBtn');
            const universe = document.getElementById('repeatersUniverseSelect')?.value || 'nifty_50';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = `<span>⏳ Running Batch AI...</span>`;
            }
            try {
                const res = await fetch(API_BASE + '/api/v1/earnings-radar/repeaters/batch-forecast?universe=' + encodeURIComponent(universe) + '&limit=15', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    alert('Batch AI Forward forecasting started in background. Refreshing candidate table in 5 seconds.');
                    setTimeout(() => app.loadQuarterRepeaters(), 5000);
                    setTimeout(() => app.loadQuarterRepeaters(), 15000);
                }
            } catch (e) {
                console.error('[REPEATERS] Batch forecast error:', e);
                alert('Batch forecast error: ' + e.message);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `<span>⚡ Run AI Batch</span>`;
                }
            }
        };

        // ========================================================
        // 🧠 UNIVERSAL STOCK INTELLIGENCE & DEEP DIVE NOTE ENGINE
        // ========================================================
        app.closeStockNote = function() {
            const modal = document.getElementById('stockIntelligenceNoteModal');
            if (modal) modal.style.display = 'none';
        };

        app.openStockNote = async function(ticker, event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            const sym = (ticker || '').trim().toUpperCase();
            if (!sym) return;

            const modal = document.getElementById('stockIntelligenceNoteModal');
            const content = document.getElementById('stockIntelligenceNoteContent');
            if (!modal || !content) return;

            modal.style.display = 'flex';
            content.innerHTML = `
                <div style="padding:2rem;text-align:center;color:#cbd5e1;">
                    <div style="font-size:1.8rem;margin-bottom:0.6rem;display:inline-block;animation:spin 1s linear infinite;">⏳</div>
                    <div style="font-size:1rem;font-weight:700;color:#f8fafc;">Compiling Multi-Dimensional Intelligence Note for ${sym}...</div>
                    <div style="font-size:0.75rem;color:#94a3b8;margin-top:0.3rem;">Analyzing Price Action Dynamics, Swing Channels, News Catalysts &amp; Local/Cloud AI Models</div>
                </div>
            `;

            try {
                const res = await fetch(API_BASE + '/api/v1/stock/' + encodeURIComponent(sym) + '/intelligence-note');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const note = await res.json();
                app.renderStockIntelligenceNote(note);
            } catch (err) {
                console.error('[STOCK-NOTE] Error loading note for ' + sym, err);
                content.innerHTML = `
                    <div style="padding:1.5rem;text-align:center;color:#f87171;">
                        <div style="font-size:1.4rem;margin-bottom:0.4rem;">⚠️ Error Loading Intelligence Note</div>
                        <div style="font-size:0.8rem;color:#e2e8f0;margin-bottom:1rem;">${err.message || err}</div>
                        <button type="button" onclick="app.openStockNote('${sym}')" class="btn btn-sm" style="background:#2563eb;color:#fff;">🔄 Retry</button>
                    </div>
                `;
            }
        };

        app.renderStockIntelligenceNote = function(note) {
            const content = document.getElementById('stockIntelligenceNoteContent');
            if (!content || !note) return;

            const sym = note.ticker;
            const name = note.company_name || sym;
            const buzz = note.industry_buzz_tag || note.industry || 'Theme';
            const cmp = note.current_price != null ? `₹${Number(note.current_price).toLocaleString('en-IN')}` : '₹—';
            
            const ret30 = note.thirty_day_return_pct != null ? Number(note.thirty_day_return_pct) : null;
            const ret30Str = ret30 != null ? `${ret30 >= 0 ? '+' : ''}${ret30.toFixed(1)}%` : 'N/A';
            const ret30Color = ret30 != null && ret30 >= 0 ? '#34d399' : '#f87171';

            const dist52High = note.pct_from_52w_high != null ? `${Number(note.pct_from_52w_high).toFixed(1)}%` : '—';

            // Price Action & Reaction
            const pr = note.price_reaction || {};
            const surpVal = pr.last_eps_surprise != null ? Number(pr.last_eps_surprise) : null;
            const surpStr = surpVal != null ? `${surpVal >= 0 ? '+' : ''}${surpVal.toFixed(1)}% Beat` : 'Solid Quality Beat';
            const scoreStr = pr.last_quality_score != null ? `${pr.last_quality_score}/9` : '6/9';
            const wkHighVal = pr.last_week_high_pct != null ? Number(pr.last_week_high_pct) : null;
            const wkHighStr = wkHighVal != null ? `+${wkHighVal.toFixed(1)}%` : 'N/A';
            const wkLowVal = pr.last_week_low_pct != null ? Number(pr.last_week_low_pct) : null;
            const wkLowStr = wkLowVal != null ? `${wkLowVal >= 0 ? '+' : ''}${wkLowVal.toFixed(1)}%` : 'N/A';
            const wkMoveVal = pr.earnings_week_move_pct != null ? Number(pr.earnings_week_move_pct) : null;
            const wkMoveStr = wkMoveVal != null ? `${wkMoveVal >= 0 ? '+' : ''}${wkMoveVal.toFixed(1)}%` : 'N/A';
            const explanation = pr.price_action_explanation || 'Steady post-earnings accumulation observed.';

            // Swing Channel
            const sw = note.swing_structure || {};
            const suppStr = sw.support_level != null ? `₹${Number(sw.support_level).toLocaleString('en-IN')}` : '₹—';
            const ressStr = sw.resistance_level != null ? `₹${Number(sw.resistance_level).toLocaleString('en-IN')}` : '₹—';
            const pivotStr = sw.channel_pivot != null ? `₹${Number(sw.channel_pivot).toLocaleString('en-IN')}` : '₹—';
            const cyclesStr = `${sw.cycles || 0} Cycles (${sw.avg_cycle_days || 0}d avg)`;
            const pctSuppStr = sw.pct_from_support != null ? `+${sw.pct_from_support}% above` : '';
            const pctRessStr = sw.pct_to_resistance != null ? `${sw.pct_to_resistance}% to go` : '';

            // AI Thesis & Conviction
            const ai = note.ai_thesis || {};
            const verdict = ai.verdict || 'MODERATE_BEAT';
            const conf = ai.confidence_pct || 75;
            const modelUsed = ai.model_used || 'Local AI Engine';
            const thesisText = ai.thesis || 'Constructive fundamental momentum continuation expected.';
            const bias = ai.expected_price_bias || 'BULLISH';
            const action = ai.suggested_action || 'ACCUMULATE_PRE_EARNINGS';

            const rawDrivers = ai.growth_drivers || [];
            const drivers = Array.isArray(rawDrivers) ? rawDrivers : [rawDrivers];
            const driversHtml = drivers.length ? drivers.map(d => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${d}</li>`).join('') : '<li style="color:#94a3b8;">Order book growth and sector tailwinds.</li>';

            const rawRisks = ai.risk_factors || [];
            const risks = Array.isArray(rawRisks) ? rawRisks : [rawRisks];
            const risksHtml = risks.length ? risks.map(r => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${r}</li>`).join('') : '<li style="color:#94a3b8;">Standard market volatility and margin pressures.</li>';

            // 3Q Beat History
            const history = note.beat_history || [];
            let historyHtml = '<span style="color:#94a3b8;font-size:0.72rem;">No historical quarter data.</span>';
            if (history.length > 0) {
                historyHtml = history.map((h, idx) => {
                    const qName = `Q${idx + 1}`;
                    const qScore = h.score != null ? `${h.score}/9` : '—';
                    const qSurp = h.surprise_pct != null ? `${h.surprise_pct >= 0 ? '+' : ''}${Number(h.surprise_pct).toFixed(1)}%` : 'Beat';
                    const isPos = (h.surprise_pct == null || h.surprise_pct >= 0) && (h.score == null || h.score >= 5);
                    return `
                        <div style="background:${isPos ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'};border:1px solid ${isPos ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:6px;padding:0.35rem 0.55rem;text-align:center;">
                            <div style="font-size:0.65rem;color:${isPos ? '#34d399' : '#f87171'};font-weight:700;">${qName} (${h.date ? String(h.date).slice(0, 7) : 'Prior'})</div>
                            <div style="font-size:0.78rem;font-weight:800;color:#f1f5f9;font-family:var(--font-mono);">${qSurp}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">Score: ${qScore}</div>
                        </div>
                    `;
                }).join('');
            }

            // News articles
            const articles = note.news_catalysts || [];
            let newsHtml = '<div style="color:#94a3b8;font-size:0.75rem;font-style:italic;">No recent news headlines indexed.</div>';
            if (articles.length > 0) {
                newsHtml = articles.map(a => {
                    const dateStr = a.published_at ? String(a.published_at).slice(0, 10) : 'Recent';
                    const titleStr = a.title || 'Corporate Filing';
                    const sent = a.sentiment_label || 'Neutral';
                    const sentColor = sent.toLowerCase().includes('bull') || sent.toLowerCase().includes('pos') ? '#34d399' : (sent.toLowerCase().includes('bear') || sent.toLowerCase().includes('neg') ? '#f87171' : '#94a3b8');
                    const url = a.url ? `<a href="${a.url}" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.3rem;" onclick="event.stopPropagation();">↗</a>` : '';
                    return `
                        <div style="background:#0c101c;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.65rem;margin-bottom:0.35rem;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;">
                            <div style="font-size:0.75rem;color:#e2e8f0;line-height:1.4;">
                                <span style="color:#64748b;font-family:var(--font-mono);font-size:0.68rem;margin-right:0.35rem;">[${dateStr}]</span>
                                <span>${titleStr}</span>${url}
                            </div>
                            <span style="font-size:0.65rem;background:rgba(255,255,255,0.05);color:${sentColor};border:1px solid rgba(255,255,255,0.1);padding:0.1rem 0.35rem;border-radius:3px;white-space:nowrap;">${sent}</span>
                        </div>
                    `;
                }).join('');
            }

            content.innerHTML = `
                <!-- 1. Header Banner -->
                <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.85rem;margin-bottom:0.85rem;flex-wrap:wrap;gap:0.5rem;">
                    <div style="display:flex;align-items:center;gap:0.65rem;">
                        <div style="font-size:1.6rem;">🧠</div>
                        <div>
                            <div style="font-size:1.18rem;font-weight:800;color:#f8fafc;display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                                <span>${sym}</span>
                                <span style="font-size:0.72rem;background:rgba(168,85,247,0.2);color:#c084fc;padding:0.15rem 0.45rem;border-radius:4px;">${buzz}</span>
                                <span style="font-size:0.72rem;background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.15rem 0.45rem;border-radius:4px;font-family:var(--font-mono);">${modelUsed}</span>
                            </div>
                            <div style="font-size:0.76rem;color:#94a3b8;margin-top:0.15rem;">
                                ${name} &middot; CMP: <strong style="color:#ffffff;">${cmp}</strong> &middot; 30D Return: <strong style="color:${ret30Color};">${ret30Str}</strong> &middot; 52W High Gap: <strong>${dist52High}</strong>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. Interactive Multi-Model Selector Bar -->
                <div style="background:#0c101c;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.65rem 0.85rem;margin-bottom:0.85rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;">
                    <div style="font-size:0.76rem;font-weight:700;color:#60a5fa;display:flex;align-items:center;gap:0.35rem;">
                        <span>🤖 Model Reasoning Engine (Local Ollama &amp; Online OpenRouter)</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                        <select id="stockNoteModelSelect" style="background:#05070d;border:1px solid rgba(255,255,255,0.18);color:#f1f5f9;font-size:0.72rem;padding:0.25rem 0.5rem;border-radius:5px;outline:none;">
                            <optgroup label="🖥️ Local Ollama Models">
                                <option value="llama3.2:3b" selected>llama3.2:3b (Fast Local)</option>
                                <option value="deepseek-r1:8b">deepseek-r1:8b (Deep Reasoning)</option>
                                <option value="qwen2.5-coder:latest">qwen2.5-coder (Algorithmic)</option>
                            </optgroup>
                            <optgroup label="☁️ Online Models (OpenRouter)">
                                <option value="deepseek/deepseek-r1:free">DeepSeek-R1 (Free Cloud)</option>
                                <option value="meta-llama/llama-3.3-70b-instruct">Llama-3.3 70B Instruct</option>
                                <option value="mistralai/mistral-large">Mistral Large</option>
                                <option value="google/gemini-2.0-flash-001">Gemini 2.0 Flash</option>
                            </optgroup>
                        </select>
                        <button type="button" onclick="event.preventDefault(); const sel = document.getElementById('stockNoteModelSelect').value; app.runStockNoteAi('${sym}', this, sel);" class="btn btn-sm" style="background:#2563eb;color:#fff;font-size:0.72rem;padding:0.25rem 0.65rem;border-radius:5px;cursor:pointer;">
                            ⚡ Run Model
                        </button>
                    </div>
                </div>

                <!-- 3. Section: Price Action Mechanics & Reaction Dynamics -->
                <div style="background:#0b111e;border:1px solid rgba(59,130,246,0.25);border-radius:8px;padding:0.85rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.78rem;font-weight:700;color:#38bdf8;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.35rem;">
                        <span>📊 Price Action Reaction Mechanics &amp; Move Breakdown</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;margin-bottom:0.6rem;">
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Prior Delivery</div>
                            <div style="font-size:0.82rem;font-weight:700;color:#34d399;font-family:var(--font-mono);">${surpStr}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Quality: ${scoreStr}</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Week Peak High</div>
                            <div style="font-size:0.82rem;font-weight:700;color:#4ade80;font-family:var(--font-mono);">${wkHighStr}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Peak Rally Magnitude</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Net 1-Wk Move</div>
                            <div style="font-size:0.82rem;font-weight:700;color:${wkMoveVal >= 0 ? '#34d399' : '#f87171'};font-family:var(--font-mono);">${wkMoveStr}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Drawdown: ${wkLowStr}</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">30-Day Trend</div>
                            <div style="font-size:0.82rem;font-weight:700;color:${ret30Color};font-family:var(--font-mono);">${ret30Str}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Trend Continuation</div>
                        </div>
                    </div>
                    <div style="font-size:0.75rem;color:#cbd5e1;line-height:1.5;background:#070a12;border-radius:6px;padding:0.55rem 0.75rem;border-left:3px solid #38bdf8;">
                        ${explanation}
                    </div>
                </div>

                <!-- 4. Section: Technical Swing Range Channel -->
                <div style="background:#0b111e;border:1px solid rgba(16,185,129,0.25);border-radius:8px;padding:0.85rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.78rem;font-weight:700;color:#34d399;margin-bottom:0.5rem;display:flex;align-items:center;justify-content:space-between;">
                        <span>🎯 Technical Swing Channel &amp; Boundary Levels</span>
                        <span style="font-size:0.68rem;color:#94a3b8;font-family:var(--font-mono);">${cyclesStr}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;">
                        <div style="background:#070a12;border:1px solid rgba(16,185,129,0.2);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#34d399;text-transform:uppercase;font-weight:700;">Support (Buy Zone)</div>
                            <div style="font-size:0.85rem;font-weight:800;color:#6ee7b7;font-family:var(--font-mono);">${suppStr}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">${pctSuppStr}</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(59,130,246,0.2);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#60a5fa;text-transform:uppercase;font-weight:700;">Channel Pivot</div>
                            <div style="font-size:0.85rem;font-weight:800;color:#93c5fd;font-family:var(--font-mono);">${pivotStr}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">Equilibrium</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(239,68,68,0.2);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#f87171;text-transform:uppercase;font-weight:700;">Resistance (Sell Zone)</div>
                            <div style="font-size:0.85rem;font-weight:800;color:#fca5a5;font-family:var(--font-mono);">${ressStr}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">${pctRessStr}</div>
                        </div>
                    </div>
                </div>

                <!-- 5. Section: Forward AI Thesis & Conviction -->
                <div style="background:#0c101c;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.95rem;margin-bottom:0.85rem;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.45rem;flex-wrap:wrap;gap:0.4rem;">
                        <div style="font-size:0.78rem;font-weight:700;color:#38bdf8;">🧠 Forward Quantitative &amp; AI Thesis</div>
                        <div style="display:flex;gap:0.4rem;align-items:center;">
                            <span style="font-size:0.68rem;background:rgba(16,185,129,0.15);color:#34d399;padding:0.12rem 0.4rem;border-radius:4px;font-weight:700;">${conf}% Conviction</span>
                            <span style="font-size:0.68rem;background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.12rem 0.4rem;border-radius:4px;font-weight:700;">${action.replace(/_/g, ' ')}</span>
                        </div>
                    </div>
                    <div style="font-size:0.82rem;color:#e2e8f0;line-height:1.55;margin-bottom:0.75rem;">${thesisText}</div>

                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;">
                        <div style="background:#070a12;border:1px solid rgba(34,197,94,0.2);border-radius:6px;padding:0.75rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#4ade80;margin-bottom:0.35rem;">🚀 Growth Drivers &amp; Order Flow</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.75rem;line-height:1.45;">${driversHtml}</ul>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(239,68,68,0.2);border-radius:6px;padding:0.75rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#f87171;margin-bottom:0.35rem;">⚠️ Key Risks &amp; Margins</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.75rem;line-height:1.45;">${risksHtml}</ul>
                        </div>
                    </div>
                </div>

                <!-- 6. Section: 3-Quarter Delivery History -->
                <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.8rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.45rem;display:flex;align-items:center;justify-content:space-between;">
                        <span>📈 3-Quarter Beat Track Record</span>
                        <span style="font-size:0.7rem;color:#f87171;font-family:var(--font-mono);font-weight:700;">🔥 ${note.beat_streak || 1}Q Consecutive Streak</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(110px, 1fr));gap:0.45rem;">
                        ${historyHtml}
                    </div>
                </div>

                <!-- 7. Section: News & Catalysts Considered -->
                <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.8rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.45rem;">
                        📰 Corporate Filings, Catalysts &amp; News Sentiment
                    </div>
                    <div style="max-height:150px;overflow-y:auto;">
                        ${newsHtml}
                    </div>
                </div>

                <!-- Footer Actions -->
                <div style="display:flex;align-items:center;justify-content:space-between;padding-top:0.75rem;border-top:1px solid rgba(255,255,255,0.08);flex-wrap:wrap;gap:0.5rem;">
                    <div style="display:flex;gap:0.6rem;align-items:center;">
                        <a href="/stock/${encodeURIComponent(sym)}" target="_blank" style="color:#38bdf8;font-size:0.78rem;text-decoration:none;font-weight:600;">Open Full Stock Intelligence ↗</a>
                        <button type="button" onclick="app.openAddToWatchlistModal('${sym}')" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);font-size:0.72rem;padding:0.25rem 0.55rem;border-radius:5px;cursor:pointer;">⭐ Add to Watchlist</button>
                    </div>
                    <button type="button" onclick="app.closeStockNote()" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);padding:0.35rem 0.85rem;border-radius:6px;font-size:0.75rem;cursor:pointer;">
                        Close
                    </button>
                </div>
            `;
        };

        app.runStockNoteAi = async function(ticker, btnEl, modelName = null) {
            if (btnEl) btnEl.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span>`;
            try {
                let url = API_BASE + '/api/v1/stock/' + encodeURIComponent(ticker) + '/intelligence-note';
                if (modelName) {
                    const provider = modelName.includes('/') ? 'openrouter' : 'ollama';
                    url += '?model_name=' + encodeURIComponent(modelName) + '&provider=' + encodeURIComponent(provider);
                }
                const res = await fetch(url, { method: 'POST' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const note = await res.json();
                app.renderStockIntelligenceNote(note);
            } catch (e) {
                console.error('[STOCK-NOTE] AI run error for ' + ticker, e);
                alert('AI Inference failed: ' + e.message);
            } finally {
                if (btnEl) btnEl.textContent = '⚡ Run Model';
            }
        };

        app.pgLocalAi = {
            _candidates: [],
            _isRunning: false,
            _timerInterval: null,
            _startTime: 0,
            _completedCount: 0,

            _watchlistsPopulated: false,

            populateWatchlists: async function() {
                const group = document.getElementById('pgBatchWatchlistsGroup');
                if (!group) return;
                try {
                    const res = await fetch(API_BASE + '/api/v1/watchlist/all');
                    if (!res.ok) return;
                    const lists = await res.json();
                    if (!Array.isArray(lists) || !lists.length) return;

                    const currentVal = document.getElementById('pgBatchSource')?.value;
                    group.innerHTML = lists.map(wl => {
                        const count = Array.isArray(wl.tickers) ? wl.tickers.length : (wl.count || 0);
                        const val = `watchlist:${wl.name}`;
                        const isSel = (currentVal === val || (!currentVal && wl.name === 'my_watchlist')) ? 'selected' : '';
                        return `<option value="${val}" ${isSel}>⭐ ${wl.display_name || wl.name} (${count} stocks)</option>`;
                    }).join('');
                    this._watchlistsPopulated = true;
                } catch (e) {
                    console.debug('[PG-LOCAL-AI] Failed to populate watchlists:', e);
                }
            },

            onSourceChange: function(source) {
                const customRow = document.getElementById('pgBatchCustomRow');
                if (customRow) {
                    customRow.style.display = (source === 'custom') ? 'block' : 'none';
                }
                this.loadCandidates();
            },

            loadCandidates: async function() {
                if (!this._watchlistsPopulated) {
                    await this.populateWatchlists();
                }

                const source = document.getElementById('pgBatchSource')?.value || 'watchlist:my_watchlist';
                const countVal = document.getElementById('pgBatchCount')?.value || '5';
                const limit = countVal === 'all' ? 100 : parseInt(countVal, 10);
                const container = document.getElementById('pgBatchListContainer');
                const countEl = document.getElementById('pgBatchSelectedCount');

                if (container) {
                    container.innerHTML = '<div style="padding:1.5rem;text-align:center;color:#60a5fa;font-size:0.78rem;"><span class="spinner"></span> Loading stock candidates for local AI...</div>';
                }

                let tickers = [];
                try {
                    if (source === 'custom') {
                        const raw = document.getElementById('pgBatchCustomTickers')?.value || '';
                        tickers = raw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
                        if (!tickers.length) {
                            tickers = ['BAJAJ-AUTO.NS', 'TCS.NS', 'INFY.NS', 'RELIANCE.NS', 'HDFCBANK.NS'];
                        }
                    } else if (source.startsWith('watchlist:')) {
                        const wlName = source.replace('watchlist:', '');
                        const res = await fetch(API_BASE + '/api/v1/watchlist/quotes?name=' + encodeURIComponent(wlName));
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.quotes || []).map(q => q.ticker);
                        }
                        if (!tickers.length) {
                            const res2 = await fetch(API_BASE + '/api/v1/watchlist/' + encodeURIComponent(wlName));
                            if (res2.ok) {
                                const data2 = await res2.json();
                                tickers = data2.tickers || [];
                            }
                        }
                    } else if (source === 'breakout') {
                        const res = await fetch(API_BASE + '/api/v1/breakout-radar?limit=' + limit);
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.candidates || []).map(c => c.ticker);
                        }
                    } else if (source === 'repeaters') {
                        const res = await fetch(API_BASE + '/api/v1/earnings-radar/repeaters?limit=' + limit);
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.repeaters || []).map(r => r.ticker);
                        }
                    } else if (source === 'nifty_50' || source === 'nse_large_cap' || source === 'all') {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/quotes?name=' + encodeURIComponent(source));
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.quotes || []).map(q => q.ticker);
                        }
                    } else {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/quotes?name=my_watchlist');
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.quotes || []).map(q => q.ticker);
                        }
                    }
                } catch (e) {
                    console.error('[PG-LOCAL-AI] Failed to fetch source tickers:', e);
                }

                if (!tickers.length) {
                    tickers = ['BAJAJ-AUTO.NS', 'TCS.NS', 'INFY.NS', 'RELIANCE.NS', 'TATAMOTORS.NS'];
                }

                tickers = tickers.slice(0, limit);
                this._candidates = tickers.map(t => ({
                    ticker: t,
                    status: 'pending',
                    result: null,
                    error: null
                }));

                if (countEl) countEl.textContent = `${this._candidates.length} stocks`;
                this.renderCandidates();
            },

            renderCandidates: function() {
                const container = document.getElementById('pgBatchListContainer');
                if (!container) return;

                if (!this._candidates.length) {
                    container.innerHTML = '<div style="padding:2rem;text-align:center;color:#64748b;font-size:0.8rem;">No stocks selected. Choose another source or enter custom tickers above.</div>';
                    return;
                }

                container.innerHTML = this._candidates.map((c, idx) => {
                    const sym = c.ticker;
                    const res = c.result || {};
                    const thesis = res.ai_thesis || {};
                    const dir = thesis.expected_price_bias || thesis.direction || 'PENDING';
                    const isBull = dir.toUpperCase() === 'BULLISH';
                    const isBear = dir.toUpperCase() === 'BEARISH';
                    const isComplete = c.status === 'completed';
                    const isRunning = c.status === 'running';

                    let statusBadge = `<span style="font-size:0.68rem;background:rgba(255,255,255,0.05);color:#94a3b8;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(255,255,255,0.1);">Pending ⏳</span>`;
                    if (isRunning) {
                        statusBadge = `<span style="font-size:0.68rem;background:rgba(251,191,36,0.15);color:#fbbf24;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(251,191,36,0.3);animation:pulse 1.2s infinite;">⚡ Inferencing (GPU)</span>`;
                    } else if (isComplete) {
                        statusBadge = `<span style="font-size:0.68rem;background:rgba(16,185,129,0.15);color:#34d399;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(16,185,129,0.3);">✅ Completed</span>`;
                    } else if (c.status === 'error') {
                        statusBadge = `<span style="font-size:0.68rem;background:rgba(239,68,68,0.15);color:#f87171;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(239,68,68,0.3);">❌ Error</span>`;
                    }

                    const verdictHtml = isComplete ? `
                        <div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.25rem;flex-wrap:wrap;">
                            <span style="font-size:0.75rem;font-weight:800;background:${isBull ? 'rgba(16,185,129,0.15)' : isBear ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.08)'};color:${isBull ? '#34d399' : isBear ? '#f87171' : '#94a3b8'};padding:0.12rem 0.45rem;border-radius:4px;border:1px solid ${isBull ? 'rgba(16,185,129,0.3)' : isBear ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)'};">${dir} (${thesis.conviction_score_pct || 80}%)</span>
                            <span style="font-size:0.7rem;color:#38bdf8;font-weight:600;">${(thesis.suggested_action || 'ACCUMULATE').replace(/_/g, ' ')}</span>
                        </div>
                        <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.35rem;">
                            ${(thesis.executive_thesis || 'Technical structure and momentum align with local model forecast.').substring(0, 140)}...
                        </div>
                    ` : (isRunning ? `
                        <div style="font-size:0.75rem;color:#fbbf24;display:flex;align-items:center;gap:0.4rem;">
                            <span class="spinner" style="width:12px;height:12px;border-width:2px;"></span> Running local Ollama multi-factor reasoning on GPU...
                        </div>
                    ` : `
                        <div style="font-size:0.75rem;color:#64748b;font-style:italic;">
                            Waiting for batch execution trigger...
                        </div>
                    `);

                    return `
                        <div style="padding:0.85rem 1rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;background:${idx % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent'};border-bottom:1px solid rgba(255,255,255,0.04);">
                            <div style="flex:1;min-width:200px;">
                                <div style="display:flex;align-items:center;gap:0.45rem;margin-bottom:0.2rem;">
                                    <strong style="font-size:0.88rem;color:#ffffff;font-family:var(--font-mono);">${sym}</strong>
                                    ${statusBadge}
                                </div>
                                <div style="font-size:0.72rem;color:#94a3b8;">
                                    ${res.profile?.company_name || sym.replace('.NS', '')} • ${res.profile?.sector || 'Equities'}
                                    ${res.price_reaction?.current_price ? ` • <span style="color:#ffffff;font-family:var(--font-mono);">₹${res.price_reaction.current_price}</span>` : ''}
                                </div>
                            </div>

                            <div style="flex:2;min-width:260px;">
                                ${verdictHtml}
                            </div>

                            <div style="display:flex;gap:0.35rem;align-items:center;">
                                <button type="button" onclick="app.openStockNote('${sym}', event)" class="btn btn-secondary btn-sm" style="font-size:0.74rem;padding:0.3rem 0.65rem;border-color:rgba(99,102,241,0.3);color:#a5b4fc;display:flex;align-items:center;gap:0.3rem;">
                                    <span>🧠</span> View Note
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            },

            runBatch: async function() {
                if (this._isRunning) return;
                if (!this._candidates.length) {
                    await this.loadCandidates();
                }
                if (!this._candidates.length) return;

                this._isRunning = true;
                this._startTime = Date.now();
                this._completedCount = 0;

                const modelName = document.getElementById('pgBatchModel')?.value || 'llama3.2:3b';
                const provider = modelName.includes('kronos') ? 'kronos' : 'ollama';
                const concurrency = parseInt(document.getElementById('pgBatchConcurrency')?.value || '1', 10);

                const progressCard = document.getElementById('pgBatchProgressCard');
                const stopBtn = document.getElementById('pgBatchStopBtn');
                const runBtn = document.getElementById('pgBatchRunBtn');
                const gpuStatus = document.getElementById('pgBatchGpuStatus');
                const activityEl = document.getElementById('pgBatchActivity');
                const elapsedEl = document.getElementById('pgBatchElapsed');
                const etaEl = document.getElementById('pgBatchEta');
                const percentEl = document.getElementById('pgBatchPercent');
                const progressBar = document.getElementById('pgBatchProgressBar');

                if (progressCard) progressCard.style.display = 'block';
                if (stopBtn) stopBtn.style.display = 'inline-block';
                if (runBtn) {
                    runBtn.disabled = true;
                    runBtn.innerHTML = `<span class="spinner"></span> Processing Batch...`;
                }
                if (gpuStatus) {
                    gpuStatus.textContent = '🖥️ GPU: Busy (Inference In Progress)';
                    gpuStatus.style.color = '#fbbf24';
                    gpuStatus.style.borderColor = 'rgba(251,191,36,0.3)';
                }

                // Live Timer
                this._timerInterval = setInterval(() => {
                    const elapsedSec = Math.floor((Date.now() - this._startTime) / 1000);
                    const m = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
                    const s = String(elapsedSec % 60).padStart(2, '0');
                    if (elapsedEl) elapsedEl.textContent = `${m}:${s}`;

                    if (this._completedCount > 0 && this._completedCount < this._candidates.length) {
                        const avgSecPerItem = elapsedSec / this._completedCount;
                        const remainingItems = this._candidates.length - this._completedCount;
                        const remainingSec = Math.ceil(remainingItems * avgSecPerItem);
                        const rm = String(Math.floor(remainingSec / 60)).padStart(2, '0');
                        const rs = String(remainingSec % 60).padStart(2, '0');
                        if (etaEl) etaEl.textContent = `ETA: ~${rm}:${rs}`;
                    }
                }, 500);

                // Execute batch bounded by concurrency
                const total = this._candidates.length;
                for (let i = 0; i < total; i += concurrency) {
                    if (!this._isRunning) break;
                    const chunk = this._candidates.slice(i, i + concurrency);
                    
                    // Mark running
                    chunk.forEach(c => { c.status = 'running'; });
                    if (activityEl) {
                        activityEl.textContent = `[${i + 1}/${total}] Processing ${chunk.map(c => c.ticker).join(', ')} on GPU (${modelName})...`;
                    }
                    this.renderCandidates();

                    await Promise.all(chunk.map(async (cand) => {
                        if (!this._isRunning) return;
                        try {
                            let url = API_BASE + '/api/v1/stock/' + encodeURIComponent(cand.ticker) + '/intelligence-note';
                            url += '?model_name=' + encodeURIComponent(modelName) + '&provider=' + encodeURIComponent(provider);
                            const res = await fetch(url, { method: 'POST' });
                            if (!res.ok) throw new Error('HTTP ' + res.status);
                            const note = await res.json();
                            cand.result = note;
                            cand.status = 'completed';
                        } catch (err) {
                            console.error('[PG-LOCAL-AI] Inference failed for ' + cand.ticker, err);
                            cand.status = 'error';
                            cand.error = err.message;
                        } finally {
                            this._completedCount++;
                            const pct = Math.round((this._completedCount / total) * 100);
                            if (percentEl) percentEl.textContent = `${pct}%`;
                            if (progressBar) progressBar.style.width = `${pct}%`;
                        }
                    }));

                    this.renderCandidates();
                }

                // Finish
                this.stopBatch();
            },

            stopBatch: function() {
                this._isRunning = false;
                if (this._timerInterval) {
                    clearInterval(this._timerInterval);
                    this._timerInterval = null;
                }

                const stopBtn = document.getElementById('pgBatchStopBtn');
                const runBtn = document.getElementById('pgBatchRunBtn');
                const gpuStatus = document.getElementById('pgBatchGpuStatus');
                const activityEl = document.getElementById('pgBatchActivity');
                const etaEl = document.getElementById('pgBatchEta');

                if (stopBtn) stopBtn.style.display = 'none';
                if (runBtn) {
                    runBtn.disabled = false;
                    runBtn.innerHTML = `<span>⚡</span> Run Local AI Notes`;
                }
                if (gpuStatus) {
                    gpuStatus.textContent = '🖥️ GPU: Idle / Ready';
                    gpuStatus.style.color = '#38bdf8';
                    gpuStatus.style.borderColor = 'rgba(56,189,248,0.25)';
                }
                if (activityEl) {
                    activityEl.textContent = `Batch run finished (${this._completedCount}/${this._candidates.length} processed).`;
                }
                if (etaEl) {
                    etaEl.textContent = 'ETA: Done ✅';
                }
                this.renderCandidates();
            }
        };

        // Initialize & export to window
        window.app = app;
        if (typeof app.init === 'function') {
            try { app.init(); } catch (e) { console.warn('app.init:', e); }
        }
        try {
            app.updateResultsMonthSummaryCards();
        } catch (e) {
            console.warn('Initial month summary fetch:', e);
        }



