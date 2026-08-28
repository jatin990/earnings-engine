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

                    const benchmarkKeys = ['nifty_50', 'nifty_next_50', 'nifty_100', 'nifty_200', 'nifty_500'];
                    const capKeys = ['nse_large_cap', 'nse_mid_cap', 'nse_small_cap', 'nse_all'];
                    const usKeys = ['us_top', 'us'];

                    const benchUnis = this.universes.filter(u => benchmarkKeys.includes(u.name.toLowerCase()));
                    const capUnis = this.universes.filter(u => capKeys.includes(u.name.toLowerCase()));
                    const usUnis = this.universes.filter(u => usKeys.includes(u.name.toLowerCase()));
                    const otherUnis = this.universes.filter(u => !benchmarkKeys.includes(u.name.toLowerCase()) && !capKeys.includes(u.name.toLowerCase()) && !usKeys.includes(u.name.toLowerCase()));

                    let benchHtml = benchUnis.map(u => '<option value="' + u.name + '">' + (u.display_name || u.name) + ' (' + (u.tickers ? u.tickers.length : 0) + ')</option>').join('');
                    let capHtml = capUnis.map(u => '<option value="' + u.name + '">' + (u.name.toLowerCase() === 'nse_large_cap' ? '🏛️ Large Cap (>₹1,000 Cr Market Cap)' : (u.display_name || u.name)) + ' (' + (u.tickers ? u.tickers.length : 0) + ')</option>').join('');
                    let usHtml = usUnis.map(u => '<option value="' + u.name + '">' + (u.display_name || u.name) + ' (' + (u.tickers ? u.tickers.length : 0) + ')</option>').join('');
                    let otherHtml = otherUnis.map(u => '<option value="' + u.name + '">🏛️ ' + (u.display_name || u.name) + ' (' + (u.tickers ? u.tickers.length : 0) + ')</option>').join('');

                    let html = '';
                    // 1. Custom User Watchlists FIRST & Primary
                    html += '<optgroup label="⭐ Custom Watchlists">' + (customOpts || '<option value="my_watchlist">⭐ my_watchlist (0)</option>') + '</optgroup>';
                    // 2. Large Cap (>1000 Cr) & Market Cap Segments
                    if (capHtml) html += '<optgroup label="🏛️ Stocks > ₹1,000 Cr & Market Caps">' + capHtml + '</optgroup>';
                    // 3. Groww Benchmark Indices
                    if (benchHtml) html += '<optgroup label="🇮🇳 Groww Benchmark Indices">' + benchHtml + '</optgroup>';
                    // 4. US Mega-Caps
                    if (usHtml) html += '<optgroup label="🇺🇸 US Mega-Caps">' + usHtml + '</optgroup>';
                    if (otherHtml) html += '<optgroup label="🏛️ Other Universes">' + otherHtml + '</optgroup>';

                    sel.innerHTML = html;

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

                setLiveInterval(ms) {
                    this.liveIntervalMs = parseInt(ms, 10) || 300000;
                    localStorage.setItem('nexus_wl_refresh_interval', this.liveIntervalMs);
                    this.updateLiveButtonUI();
                    if (this.isLiveTracking) {
                        if (this._liveInterval) clearInterval(this._liveInterval);
                        this._liveInterval = setInterval(() => {
                            if (this.isLiveTracking && this.viewMode === 'list') {
                                this.loadActiveQuotes(true, true);
                            }
                        }, this.liveIntervalMs);
                    }
                },

                toggleLiveTracking() {
                    this.isLiveTracking = !this.isLiveTracking;
                    this.liveIntervalMs = parseInt(localStorage.getItem('nexus_wl_refresh_interval') || '300000', 10);
                    
                    const sel = document.getElementById('wlLiveIntervalSelect');
                    if (sel) sel.value = String(this.liveIntervalMs);

                    this.updateLiveButtonUI();

                    if (this.isLiveTracking) {
                        // Immediately fetch live once
                        this.loadActiveQuotes(true);
                        // Poll live prices every interval (default 5m = 300000ms) silently
                        if (this._liveInterval) clearInterval(this._liveInterval);
                        this._liveInterval = setInterval(() => {
                            if (this.isLiveTracking && this.viewMode === 'list') {
                                this.loadActiveQuotes(true, true);
                            }
                        }, this.liveIntervalMs);
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

                    const intervalMs = this.liveIntervalMs || parseInt(localStorage.getItem('nexus_wl_refresh_interval') || '300000', 10);
                    const intervalSec = Math.round(intervalMs / 1000);
                    const intervalLabel = intervalSec >= 60 ? `${Math.round(intervalSec / 60)}m` : `${intervalSec}s`;

                    if (this.isLiveTracking) {
                        btn.style.background = 'rgba(239,68,68,0.25)';
                        btn.style.borderColor = '#ef4444';
                        btn.style.color = '#fca5a5';
                        text.textContent = `🔴 Live (${intervalLabel})`;
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

                        // Swing Support / Resistance with color-coded BUY (Green) / SELL (Red) / HOLD (Brown) signals
                        const s = it.support != null ? currSymbol + Number(it.support).toFixed(2) : '—';
                        const r = it.resistance != null ? currSymbol + Number(it.resistance).toFixed(2) : '—';
                        const activeWl = (this.activeWatchlist || '').replace(/'/g, "\\'");
                        
                        let rangeCellHtml = '';
                        if (it.support != null && it.resistance != null && it.current_price != null && Number(it.resistance) > Number(it.support)) {
                            const pVal = Number(it.current_price);
                            const sVal = Number(it.support);
                            const rVal = Number(it.resistance);
                            const posPct = ((pVal - sVal) / (rVal - sVal)) * 100;

                            let sig = it.swing_signal;
                            if (!sig) {
                                if (posPct <= 35 || pVal <= sVal) sig = 'BUY';
                                else if (posPct >= 70 || pVal >= rVal) sig = 'SELL';
                                else sig = 'HOLD';
                            }

                            let badgeBg = 'rgba(146, 64, 14, 0.28)';
                            let badgeBorder = 'rgba(217, 119, 6, 0.45)';
                            let badgeColor = '#fcd34d';
                            let badgeIcon = '🟤';
                            let badgeTitle = `Swing Hold: ${posPct.toFixed(0)}% mid-channel`;

                            if (sig === 'BUY') {
                                badgeBg = 'rgba(16, 185, 129, 0.2)';
                                badgeBorder = 'rgba(16, 185, 129, 0.5)';
                                badgeColor = '#34d399';
                                badgeIcon = '🟢';
                                badgeTitle = `Swing Buy: ${posPct.toFixed(0)}% near support (${s})`;
                            } else if (sig === 'SELL') {
                                badgeBg = 'rgba(239, 68, 68, 0.2)';
                                badgeBorder = 'rgba(239, 68, 68, 0.5)';
                                badgeColor = '#f87171';
                                badgeIcon = '🔴';
                                badgeTitle = `Swing Sell: ${posPct.toFixed(0)}% near resistance (${r})`;
                            }

                            rangeCellHtml = `
                                <div style="display:flex;align-items:center;justify-content:center;gap:0.35rem;flex-wrap:wrap;">
                                    <span class="signal-badge" style="background:${badgeBg};border:1px solid ${badgeBorder};color:${badgeColor};font-size:0.68rem;font-weight:800;padding:0.12rem 0.45rem;border-radius:4px;display:inline-flex;align-items:center;gap:0.2rem;letter-spacing:0.02em;" title="${badgeTitle}">${badgeIcon} ${sig}</span>
                                    <button type="button" onclick="app.openSwingRangeModal('${activeWl}','${it.ticker}')" class="btn-micro" style="font-size:0.72rem;font-family:var(--font-mono);cursor:pointer;color:#94a3b8;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.12);border-radius:4px;padding:0.1rem 0.35rem;" title="Inspect & edit swing range (${s} – ${r})">${s} – ${r}</button>
                                    <button type="button" onclick="app.openSwingRangeModal('${activeWl}','${it.ticker}')" class="btn-micro" style="color:var(--muted);padding:0;font-size:0.72rem;border:none;background:transparent;cursor:pointer;" title="Edit Swing Range">⚙</button>
                                </div>`;
                        } else if (it.support != null && it.resistance != null) {
                            rangeCellHtml = `
                                <div style="display:flex;align-items:center;justify-content:center;gap:0.3rem;">
                                    <button type="button" onclick="app.openSwingRangeModal('${activeWl}','${it.ticker}')" class="btn-micro" style="font-size:0.75rem;font-family:var(--font-mono);cursor:pointer;color:#38bdf8;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.25);border-radius:4px;padding:0.12rem 0.4rem;" title="Inspect & edit swing range">${s} – ${r}</button>
                                    <button type="button" onclick="app.openSwingRangeModal('${activeWl}','${it.ticker}')" class="btn-micro" style="color:var(--muted);padding:0 0.15rem;font-size:0.75rem;border:none;background:transparent;cursor:pointer;" title="Edit Swing Range">⚙</button>
                                </div>`;
                        } else {
                            rangeCellHtml = `<button type="button" onclick="app.watchlistTab.autoDetectRowRange('${it.ticker}', this)" class="btn-micro" style="font-size:0.7rem;font-weight:700;cursor:pointer;color:#fbbf24;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.3);border-radius:4px;padding:0.15rem 0.45rem;display:inline-flex;align-items:center;gap:0.2rem;" title="Auto-detect support & resistance range"><span>⚡</span> Auto Detect</button>`;
                        }

                        return `<tr class="interactive-row">
                            <td>
                                <div style="display:flex;align-items:center;gap:0.4rem;">
                                    <button type="button" onclick="app.openAddToWatchlistModal('${it.ticker}')" class="btn-micro" style="color:#fbbf24;border:none;background:transparent;padding:0;font-size:0.85rem;cursor:pointer;" title="Manage Watchlists">⭐</button>
                                    <div>
                                        <strong onclick="app.openSwingRangeModal('${activeWl}','${it.ticker}')" style="color:#ffffff;font-size:0.85rem;cursor:pointer;" class="hover-underline" title="Inspect & edit swing range">${it.ticker}</strong>
                                        <a href="/stock/${encodeURIComponent(it.ticker)}" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;cursor:pointer;" title="Open profile in new tab">↗</a>
                                        <div style="font-size:0.7rem;color:#a1a1aa;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${it.company_name || it.ticker}</div>
                                        ${it.funds_buying > 0 ? `<div style="font-size:0.64rem;color:#34d399;font-weight:700;margin-top:2px;" title="Institutional Accumulation (+${it.funds_buying} Funds Buying)">🏛️ +${it.funds_buying} Funds Buying</div>` : (it.funds_selling > 0 ? `<div style="font-size:0.64rem;color:#f87171;font-weight:700;margin-top:2px;" title="Institutional Distribution (-${it.funds_selling} Funds Selling)">🏛️ -${it.funds_selling} Funds Selling</div>` : '')}
                                    </div>
                                </div>
                            </td>
                            <td style="text-align:right;"><strong style="font-size:0.88rem;color:#ffffff;font-family:var(--font-mono);">${p}</strong></td>
                            <td style="text-align:right;"><span style="background:${chgBadgeBg};color:${chgColor};padding:0.15rem 0.45rem;border-radius:4px;font-size:0.75rem;font-weight:700;font-family:var(--font-mono);">${chgStr}</span></td>
                            <td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#cbd5e1;">${openStr}</td>
                            <td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#34d399;">${highStr}</td>
                            <td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#f87171;">${lowStr}</td>
                            <td style="text-align:right;font-family:var(--font-mono);font-size:0.75rem;color:#93c5fd;font-weight:600;">${volStr}</td>
                            <td style="text-align:right;font-size:0.72rem;font-family:var(--font-mono);">
                                <div style="color:#cbd5e1;">${yL} – ${yH}</div>
                                ${pctH ? `<div style="font-size:0.68rem;color:${pctHColor};font-weight:600;">${pctH} from 52W H</div>` : ''}
                            </td>
                            <td style="text-align:right;font-size:0.75rem;font-family:var(--font-mono);color:#94a3b8;">${mcStr}</td>
                            <td style="text-align:center;">
                                ${rangeCellHtml}
                            </td>
                            <td style="text-align:center;">
                                <div style="display:flex;gap:0.25rem;align-items:center;justify-content:center;">
                                    <button type="button" onclick="app.runConsensusForStock('${it.ticker}')" class="btn btn-sm" style="padding:0.12rem 0.4rem;font-size:0.68rem;background:rgba(99,102,241,0.2);color:#c7d2fe;border:1px solid rgba(99,102,241,0.4);border-radius:3px;cursor:pointer;" title="Run AI Consensus">🧠</button>
                                    <button type="button" onclick="app.runPredictionForTickerSingle('${it.ticker}')" class="btn btn-sm" style="padding:0.12rem 0.4rem;font-size:0.68rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:3px;cursor:pointer;" title="Run Kronos AI">🔮</button>
                                    <button type="button" onclick="app.watchlistTab.removeQuoteTicker('${it.ticker}')" class="btn btn-sm btn-danger" style="padding:0.12rem 0.35rem;font-size:0.72rem;border-radius:3px;cursor:pointer;" title="Remove from this watchlist">🗑</button>
                                </div>
                            </td>
                        </tr>`;
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
                            (this.activeFilter !== 'all' || this.searchQuery ? '<br><button type="button" class="btn btn-sm btn-primary" onclick="app.watchlistTab.setFilter(\'all\'); if(document.getElementById(\'wlSearchInput\')) document.getElementById(\'wlSearchInput\').value=\'\'; app.watchlistTab.handleSearch(\'\');" style="margin-top:0.75rem;">Reset Filters</button>' : '') +
                            '</div>';
                        return;
                    }

                    let html = '';

                    // 1. Custom User Watchlists (Rendered FIRST & Primary)
                    if (filteredCustom.length) {
                        html += '<div style="margin-top:0.25rem;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.5rem;">' +
                            '<h4 style="margin:0;font-size:0.95rem;color:#60a5fa;display:flex;align-items:center;gap:0.35rem;">⭐ Custom User Watchlists <span style="font-size:0.75rem;background:rgba(59,130,246,0.2);padding:0.1rem 0.4rem;border-radius:9999px;">' + filteredCustom.length + '</span></h4>' +
                            '</div>';
                        html += filteredCustom.map((w, wi) => this._customCard(w, wi)).join('');
                    }

                    // 2. Built-in Universes & Indices
                    if (filteredUniverses.length) {
                        html += '<div style="margin-top:' + (filteredCustom.length ? '1rem' : '0.25rem') + ';margin-bottom:0.5rem;display:flex;align-items:center;gap:0.5rem;">' +
                            '<h4 style="margin:0;font-size:0.95rem;color:#c7d2fe;display:flex;align-items:center;gap:0.35rem;">🏛️ Built-in Universes & Indices <span style="font-size:0.75rem;background:rgba(99,102,241,0.2);padding:0.1rem 0.4rem;border-radius:9999px;">' + filteredUniverses.length + '</span></h4>' +
                            '</div>';
                        html += filteredUniverses.map((u, ui) => this._universeCard(u, ui)).join('');
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
                                '<button type="button" onclick="app.openAddToWatchlistModal(\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:#fbbf24;cursor:pointer;font-size:0.75rem;padding:0;" title="Add to Custom Watchlist">⭐</button>' +
                                '<button type="button" onclick="app.openSwingRangeModal(\'' + u.name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--light);opacity:0.7;cursor:pointer;font-size:0.75rem;line-height:1;padding:0 0.15rem;" title="Edit Swing Range">⚙</button>' +
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
                                '<button type="button" class="btn btn-sm" onclick="app.watchlistTab.selectActiveWatchlist(\'' + u.name.replace(/'/g, "\\'") + '\'); app.watchlistTab.setViewMode(\'list\');" style="background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.4);" title="Open list view with full OHLCV metrics">📋 List View</button>' +
                                '<button type="button" class="btn btn-sm" onclick="app.watchlistTab.copyToCustom(\'' + u.name.replace(/'/g, "\\'") + '\',\'' + (u.display_name || u.name).replace(/'/g, "\\'") + '\',' + JSON.stringify(tickers).replace(/"/g, '&quot;') + ')" style="background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.35);" title="Copy all tickers into a customizable custom watchlist">📋 Copy to Custom</button>' +
                                '<button type="button" class="btn btn-sm" onclick="app.switchTab(\'results\'); const el = document.getElementById(\'resultsMarket\'); if(el) { el.value=\'' + u.name.toUpperCase() + '\'; app.loadResultsReport(); }" style="background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.35);" title="View in Corporate Results tab">📈 Results</button>' +
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
                                '<button type="button" onclick="app.openSwingRangeModal(\'' + name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--light);opacity:0.7;cursor:pointer;font-size:0.75rem;line-height:1;padding:0 0.15rem;" title="Edit Swing Range">⚙</button>' +
                                '<button type="button" onclick="app.watchlistTab.removeTicker(\'' + name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:1rem;line-height:1;margin-left:0.1rem;" title="Remove">&minus;</button>' +
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
                                '<button type="button" class="btn btn-sm" onclick="app.watchlistTab.selectActiveWatchlist(\'' + name.replace(/'/g, "\\'") + '\'); app.watchlistTab.setViewMode(\'list\');" style="background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.4);" title="Open list view with full OHLCV metrics">📋 List View</button>' +
                                '<button type="button" class="btn btn-sm" onclick="app.watchlistTab.rename(\'' + name.replace(/'/g, "\\'") + '\')">✎ Rename</button>' +
                                '<button type="button" class="btn btn-sm btn-danger" onclick="app.watchlistTab.remove(\'' + name.replace(/'/g, "\\'") + '\')">🗑 Delete</button>' +
                            '</div>' +
                        '</div>' +
                        '<div style="display:flex;gap:0.4rem;align-items:center;margin-bottom:0.55rem;position:relative;z-index:50;">' +
                            '<input id="wlAddInput' + wi + '" placeholder="Add by name or symbol..." style="flex:1;padding:0.4rem;border:1px solid rgba(255,255,255,0.2);border-radius:0.4rem;background:rgba(255,255,255,0.05);color:var(--light);" autocomplete="off">' +
                            '<div id="wlAddDropdown' + wi + '" class="dropdown" style="z-index:10000;position:absolute;top:100%;left:0;right:0;max-height:280px;overflow-y:auto;box-shadow:0 14px 35px rgba(0,0,0,0.7);"></div>' +
                            '<button type="button" class="btn btn-primary btn-sm" onclick="app.watchlistTab.addTicker(\'' + name.replace(/'/g, "\\'") + '\',' + wi + ')">＋ Add</button>' +
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
                name = (name || 'home').toLowerCase().replace('#', '').replace('tab=', '');
                const validTabs = ['home', 'results', 'monthfilter', 'scanner', 'catalysts', 'premarket', 'gainers', 'breakout', 'institutional', 'repeaters', 'new-additions', 'swing', 'watchlist', 'kronos', 'consensus', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
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
                        'home': '🌐 Market Pulse',
                        'results': 'Results Ledger',
                        'monthfilter': 'Month Filter',
                        'scanner': 'Scanner',
                        'catalysts': 'Catalysts & News',
                        'premarket': '🌅 Pre-Market Setups',
                        'gainers': 'Gainers & Breakouts',
                        'breakout': '⚡ Breakout Radar',
                        'institutional': '🏛️ Institutional Flows',
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

                // Lazy-initialize client UI components on first visit without firing heavy backend scans
                if (name === 'home') {
                    if (typeof this.loadMarketPulseData === 'function') this.loadMarketPulseData();
                }
                if (name === 'institutional') {
                    if (typeof this.loadInstitutionalData === 'function') this.loadInstitutionalData();
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
                    // Lazy-load on first visit; start auto-polling while active
                    if (!this._breakoutLoaded) {
                        this._breakoutLoaded = true;
                        if (this._activeBreakoutSubtab === 'tracked') {
                            this.loadTrackedBreakouts();
                        } else {
                            this.loadBreakoutRadar();
                        }
                    }
                    this.loadAutomationSchedules();
                    this.loadBreakoutAuditLog();
                    // Start 5-minute auto-poll (cleared when leaving the tab)
                    this._breakoutPollTimer = setInterval(() => {
                        if (document.getElementById('tab-breakout')?.classList.contains('active')) {
                            if (this._activeBreakoutSubtab === 'tracked') {
                                this.loadTrackedBreakouts();
                            } else {
                                this.loadBreakoutRadar();
                            }
                            this.loadAutomationSchedules();
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
                if (name === 'catalysts') {
                    this.loadAutomationSchedules();
                }
                if (name === 'premarket') {
                    if (typeof this.loadPremarketSetups === 'function') {
                        this.loadPremarketSetups();
                    }
                }
                if (name === 'institutional') {
                    if (!this._institutionalLoaded) {
                        this._institutionalLoaded = true;
                        if (typeof this.loadInstitutionalData === 'function') this.loadInstitutionalData();
                    } else {
                        const savedSub = localStorage.getItem('ee_institutional_subpage') || 'equities';
                        if (typeof this.switchInstitutionalPage === 'function') {
                            this.switchInstitutionalPage(savedSub);
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
                this.applyRoleRestrictions();
            },

        // [scanner] -> extracted to modules/scanner.js
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

            async loadCatalysts(watchlist, days) {
                const feedGrid = document.getElementById('catalystsFeedGrid');
                if (!feedGrid) return;
                const wlSelect = document.getElementById('catWatchlistSelect');
                const daysSelect = document.getElementById('catDaysFilter');
                const wl = watchlist || (wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL'));
                const d = (days !== undefined && days !== null) ? days : (daysSelect ? daysSelect.value : '14');
                const wlParam = (wl && wl !== 'GLOBAL') ? '?watchlist=' + encodeURIComponent(wl) + '&limit=200&days=' + encodeURIComponent(d) : '?limit=200&days=' + encodeURIComponent(d);
                const statsParam = (wl && wl !== 'GLOBAL') ? '?watchlist=' + encodeURIComponent(wl) + '&days=' + encodeURIComponent(d) : '?days=' + encodeURIComponent(d);
                feedGrid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading short-term market moving catalysts' + (wl ? ' for "' + wl + '"' : '') + '...</div>';
                
                try {
                    // Fetch stats and items in parallel
                    const [itemsRes, statsRes] = await Promise.all([
                        fetch(API_BASE + '/api/v1/news/catalysts' + wlParam),
                        fetch(API_BASE + '/api/v1/news/catalyst-stats' + statsParam)
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
                const daysSelect = document.getElementById('catDaysFilter');
                const d = daysSelect ? daysSelect.value : '14';
                this.loadCatalysts(val, d);
            },

            onCatDaysFilterChange(val) {
                const wlSelect = document.getElementById('catWatchlistSelect');
                const wl = wlSelect ? wlSelect.value : (localStorage.getItem('selectedGlobalWatchlist') || 'GLOBAL');
                this.loadCatalysts(wl, val);
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
                const daysFilter = parseInt(document.getElementById('catDaysFilter')?.value || '14', 10);
                const impactFilter = document.getElementById('catImpactFilter')?.value || 'ALL';
                const dirFilter = document.getElementById('catDirectionFilter')?.value || 'ALL';
                const catFilter = document.getElementById('catCategoryFilter')?.value || 'ALL';

                // STRICT CHRONOLOGICAL SORT: Newest news always on top
                const _toTime = (dStr) => {
                    if (!dStr) return 0;
                    const clean = dStr.includes('T') ? dStr : dStr.replace(' ', 'T') + 'Z';
                    const t = new Date(clean).getTime();
                    return isNaN(t) ? new Date(dStr).getTime() || 0 : t;
                };

                const nowMs = Date.now();
                const cutoffMs = (daysFilter > 0) ? (nowMs - (daysFilter * 24 * 60 * 60 * 1000)) : 0;

                let filtered = (this.catalystsData || []).filter(item => {
                    if (daysFilter > 0) {
                        const itemTime = _toTime(item.published_at || item.created_at);
                        if (itemTime > 0 && itemTime < cutoffMs) return false;
                    }
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

                filtered.sort((a, b) => {
                    const ta = _toTime(a.published_at || a.created_at);
                    const tb = _toTime(b.published_at || b.created_at);
                    if (tb !== ta) return tb - ta;
                    return (b.impact_score || 0) - (a.impact_score || 0);
                });

                if (countBadge) countBadge.textContent = filtered.length + ' headlines';

                // Synchronously update top KPI summary cards based on the filtered dataset
                const totalCount = filtered.length;
                const highCount = filtered.filter(c => c.impact_level === 'HIGH').length;
                const bullCount = filtered.filter(c => c.direction === 'BULLISH').length;
                const bearCount = filtered.filter(c => c.direction === 'BEARISH').length;

                const catCounts = {};
                filtered.forEach(c => {
                    const cat = c.category || 'Order Wins & Contracts';
                    catCounts[cat] = (catCounts[cat] || 0) + 1;
                });
                let topCat = '—';
                let maxCnt = 0;
                for (const [cat, cnt] of Object.entries(catCounts)) {
                    if (cnt > maxCnt) {
                        maxCnt = cnt;
                        topCat = cat;
                    }
                }

                const totalEl = document.getElementById('catStatTotal');
                const highEl = document.getElementById('catStatHigh');
                const biasEl = document.getElementById('catStatBias');
                const topCatEl = document.getElementById('catStatTopCat');

                if (totalEl) totalEl.textContent = totalCount;
                if (highEl) highEl.textContent = highCount;
                if (biasEl) biasEl.innerHTML = '<span style="color:#34d399;">' + bullCount + '</span> / <span style="color:#f87171;">' + bearCount + '</span>';
                if (topCatEl) topCatEl.textContent = topCat;

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

                    const sigPrice = (c.signal_price != null && c.signal_price > 0) ? '₹' + Number(c.signal_price).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : null;
                    const curPrice = (c.current_price != null && c.current_price > 0) ? '₹' + Number(c.current_price).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2}) : null;
                    const chgPct = c.price_change_pct || 0;
                    const chgColor = chgPct > 0 ? '#34d399' : (chgPct < 0 ? '#f87171' : '#94a3b8');
                    const chgSign = chgPct > 0 ? '+' : '';
                    const priceBadge = (sigPrice && curPrice) ? `
                        <div style="display:inline-flex;align-items:center;gap:0.4rem;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.12);border-radius:5px;padding:0.12rem 0.5rem;font-size:0.72rem;" title="Price at time of news disclosure vs latest quote">
                            <span style="color:#94a3b8;">Signal Price: <strong style="color:#f8fafc;font-family:var(--font-mono);">${sigPrice}</strong></span>
                            <span style="color:#64748b;">→</span>
                            <span style="color:#94a3b8;">Now: <strong style="color:#38bdf8;font-family:var(--font-mono);">${curPrice}</strong></span>
                            <span style="color:${chgColor};font-weight:700;font-family:var(--font-mono);margin-left:0.2rem;">(${chgSign}${chgPct.toFixed(2)}%)</span>
                        </div>
                    ` : (curPrice ? `
                        <div style="display:inline-flex;align-items:center;gap:0.35rem;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.08);border-radius:5px;padding:0.12rem 0.45rem;font-size:0.72rem;">
                            <span style="color:#94a3b8;">Live Price: <strong style="color:#38bdf8;font-family:var(--font-mono);">${curPrice}</strong></span>
                        </div>
                    ` : '');

                    return '<div class="card" style="margin:0;padding:1rem;background:rgba(255,255,255,0.03);' + cardBorder + 'transition:transform 0.15s ease;">' +
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.45rem;">' +
                            '<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">' +
                                ((c.stock_name && c.stock_name.trim().toUpperCase() !== c.ticker.trim().toUpperCase())
                                    ? '<strong style="font-size:1.05rem;color:#f8fafc;">' + c.stock_name + '</strong><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" class="signal-badge" style="background:rgba(59,130,246,0.2);color:#60a5fa;font-size:0.72rem;text-decoration:none;" title="Open stock intelligence">' + c.ticker + ' ↗</a>'
                                    : '<a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="font-size:1.05rem;font-weight:700;color:#60a5fa;text-decoration:none;">' + c.ticker + ' ↗</a>') +
                                priceBadge +
                                '<span style="background:' + impactBadgeBg + ';color:' + impactBadgeColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + impactLabel + '</span>' +
                                '<span style="background:' + dirBadgeBg + ';color:' + dirColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + dirIcon + '</span>' +
                                '<span style="background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;">' + c.category + '</span>' +
                            '</div>' +
                            '<div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">' +
                                '<span class="timestamp" style="font-size:0.72rem;background:rgba(255,255,255,0.05);padding:0.15rem 0.45rem;border-radius:0.25rem;">' + (c.publisher || 'News') + ' &middot; ⏱️ ' + dateDisplay + '</span>' +
                                `<button type="button" onclick="app.runConsensusForStock('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.45);border-radius:0.3rem;font-weight:700;" title="Run AI Multi-Model Consensus for Target, Resistance, Support & Buy Zone">🧠 Consensus</button>` +
                                `<button type="button" onclick="app.openAddToWatchlistModal('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);border-radius:0.3rem;" title="Add to Watchlist">⭐ Watchlist</button>` +
                                `<button type="button" onclick="app.runPredictionForTickerSingle('${c.ticker}')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);border-radius:0.3rem;" title="Run Kronos Forecast">🔮 Predict</button>` +
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

        // [] → extracted to modules/recalculate.js
        // [month_filter] -> extracted to modules/month_filter.js
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
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(99,102,241,0.18);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);border-radius:0.3rem;" title="Re-run 4-Model AI Consensus for ' + safeSym + '">⚡</button>' +
                        '</div>';
                } else {
                    return '<div id="' + domId + '" style="white-space:nowrap;">' +
                        '<button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runConsensusForTicker(\'' + safeSym + '\', this)" style="padding:0.18rem 0.45rem;font-size:0.7rem;background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);border-radius:0.3rem;font-weight:600;white-space:nowrap;" title="Run DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral 4-Model consensus for ' + safeSym + '">⚡ AI Consensus</button>' +
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
                                '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + sym + '\', \'' + (f.run_at || '') + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV accuracy against realized prices">📊 Benchmark</button>' +
                                '<button type="button" onclick="event.stopPropagation(); app.showKronosHistory(\'' + sym + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:0.3rem;">🔍 History</button>' +
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

                const benchBtn = ticker ? '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + ticker + '\', \'' + (runAt || '') + '\')" class="btn btn-sm" style="margin-top:0.4rem;width:100%;font-size:0.7rem;padding:0.2rem 0.4rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;">📊 Benchmark Realized vs Predicted OHLCV →</button>' : '';

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
                                '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + item.ticker + '\', \'' + item.run_at + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV forecast against realized bars">📊 Benchmark</button>' +
                                '<button type="button" onclick="event.stopPropagation(); app.showKronosHistory(\'' + item.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:0.3rem;" title="View prediction history & accuracy timeline">🔍 History</button>' +
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
                        '<td><div style="display:flex;gap:0.3rem;"><button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + row.ticker + '\', \'' + row.run_at + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark OHLCV accuracy against realized prices">📊 Benchmark</button><button type="button" onclick="app.deleteKronosPrediction(\'' + row.ticker + '\', \'' + row.run_at + '\')" class="btn btn-danger btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;" title="Delete record">🗑️</button></div></td>' +
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
                                '<td><button type="button" onclick="app.showKronosHistory(\'' + s.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(59,130,246,0.2);color:#60a5fa;">🔍 History</button></td>' +
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
                                '<td><button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + row.ticker + '\', \'' + (row.run_at || '') + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="Benchmark this past forecast against realized prices">📊 Benchmark</button></td>' +
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

        // [swing_range] -> extracted to modules/swing_range.js
        // [playground] -> extracted to modules/playground.js
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
                                        `<button type="button" onclick="app.openAddToWatchlistModal('${p.ticker}')" class="btn-micro" style="color:#fbbf24;border:none;background:transparent;padding:0;font-size:0.9rem;cursor:pointer;" title="Add to Watchlist">⭐</button>` +
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
                                '<button type="button" onclick="app.openConsensusDetailModal(' + p.id + ')" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);padding:0.4rem 0.75rem;border-radius:0.4rem;font-weight:600;">🔍 View Audit</button>' +
                            '</div>' +
                        '</div>' +
                        (modelPills ? '<div style="margin-top:0.6rem;display:flex;gap:0.4rem;flex-wrap:wrap;">' + modelPills + '</div>' : '') +
                        postMortemSnippet +
                    '</div>';
                }).join('');
            },

            updateConsensusModelTelemetry() {
                const sel = document.getElementById('consensusModelSelect');
                const badge = document.getElementById('consensusModelTelemetryBadge');
                if (!sel || !badge) return;
                const mKey = sel.value;
                const bench = {
                    'ALL': { time: '~2.4s', succ: '99.6%', label: 'Ensemble' },
                    'deepseek/deepseek-r1': { time: '~3.4s', succ: '99.2%', label: 'DeepSeek-R1' },
                    'meta-llama/llama-3.3-70b-instruct': { time: '~2.1s', succ: '99.8%', label: 'Llama-3.3-70B' },
                    'qwen/qwen-2.5-72b-instruct': { time: '~2.3s', succ: '99.6%', label: 'Qwen-2.5-72B' },
                    'mistralai/mistral-large': { time: '~1.9s', succ: '99.7%', label: 'Mistral-Large' },
                    'google/gemma-4-31b-it:free': { time: '~1.6s', succ: '100%', label: 'Gemma-4-31B' },
                    'z-ai/glm-5.2': { time: '~2.6s', succ: '99.4%', label: 'GLM-5.2' },
                    'local': { time: '~1.2s', succ: '100%', label: 'Local Model' }
                };
                const info = bench[mKey] || { time: '~2.2s', succ: '99.5%', label: mKey.split('/').pop() };
                badge.innerHTML = `⚡ ${info.label} Avg: ${info.time} · ${info.succ} Success`;
            },

            async runConsensusPrediction(explicitModelId = null) {
                const tickerInput = document.getElementById('consensusTickerInput');
                const tfSelect = document.getElementById('consensusTimeframeSelect');
                const modelSelect = document.getElementById('consensusModelSelect');
                const runBtn = document.getElementById('consensusRunBtn');

                const ticker = (tickerInput?.value || '').trim().toUpperCase();
                if (!ticker) {
                    alert('Please enter a stock ticker symbol (e.g. RELIANCE.NS, TCS.NS, AAPL).');
                    return;
                }

                const timeframe = parseInt(tfSelect?.value || '14', 10);
                const selectedModel = explicitModelId || (modelSelect?.value || 'ALL');

                if (explicitModelId && modelSelect) {
                    modelSelect.value = explicitModelId;
                    this.updateConsensusModelTelemetry();
                }

                const reqBody = {
                    ticker: ticker,
                    timeframe_days: timeframe,
                    force: true
                };
                if (selectedModel && selectedModel !== 'ALL') {
                    reqBody.models = [selectedModel];
                }

                const modelNameDisplay = selectedModel === 'ALL' ? 'All Engines' : (selectedModel.split('/').pop());
                if (runBtn) {
                    runBtn.disabled = true;
                    runBtn.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> Running ${modelNameDisplay}...`;
                }

                try {
                    const res = await fetch('/api/v1/consensus/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(reqBody)
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
                        runBtn.innerHTML = '<span>⚡</span> Run Model / Consensus';
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
                    '<div class="autocomplete-item" data-i="' + i + '" onclick="app.selectTicker(\'' + t + '\')" onmouseenter="app.setSearchHoverIndex(' + i + ')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:0.45rem 0.75rem;border-bottom:1px solid rgba(255,255,255,0.04);">' +
                    '<a href="/stock/' + encodeURIComponent(t) + '" onclick="event.preventDefault(); app.selectTicker(\'' + t + '\');" style="color:#ffffff;font-weight:700;letter-spacing:0.02em;text-decoration:none;display:flex;justify-content:space-between;align-items:center;width:100%;">' +
                    '<span>' + t + '</span>' +
                    '<span style="font-size:0.68rem;padding:0.12rem 0.45rem;border-radius:4px;background:rgba(255,255,255,0.06);color:#94a3b8;border:1px solid rgba(255,255,255,0.08);">' + (t.endsWith('.NS') ? 'NSE' : 'US') + '</span>' +
                    '</a>' +
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
            app.openStockModal(sym);
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

        // [stock_rating] -> extracted to modules/stock_rating.js
        // [watchlist_modal] -> extracted to modules/watchlist_modal.js
        // [catalyst_consensus] -> extracted to modules/catalyst_consensus.js
        // [breakout_radar] -> extracted to modules/breakout_radar.js
        // [tracked_breakouts] -> extracted to modules/tracked_breakouts.js
        // [repeaters] -> extracted to modules/repeaters.js
        // [stock_note] -> extracted to modules/stock_note.js
        // =========================================================================
        // ⏱️ Automation Schedules & Background Job Monitor
        // =========================================================================
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
            },

            // =========================================================================
            // 🔄 Breakout Movement & Tier Transition Audit Log
            // =========================================================================
            _breakoutAuditOpen: false,

            toggleBreakoutAuditLog() {
                const container = document.getElementById('breakoutAuditContainer');
                const toggleIcon = document.getElementById('breakoutAuditToggleIcon');
                if (!container) return;

                this._breakoutAuditOpen = !this._breakoutAuditOpen;
                container.style.display = this._breakoutAuditOpen ? 'block' : 'none';
                if (toggleIcon) toggleIcon.textContent = this._breakoutAuditOpen ? '▲ Hide Log' : '▼ Show Log';

                if (this._breakoutAuditOpen) {
                    this.loadBreakoutAuditLog();
                }
            },

            async loadBreakoutAuditLog(ticker = null) {
                const listEl = document.getElementById('breakoutAuditList');
                const countBadge = document.getElementById('breakoutAuditBadgeCount');
                if (!listEl) return;

                try {
                    const url = API_BASE + '/api/v1/breakout-radar/audit-log' + (ticker ? `?ticker=${encodeURIComponent(ticker)}` : '?limit=40');
                    const res = await fetch(url);
                    if (res.ok) {
                        const data = await res.json();
                        const logs = data.logs || [];
                        if (countBadge) countBadge.textContent = `(${logs.length} events)`;

                        if (!logs.length) {
                            listEl.innerHTML = '<div style="text-align:center;color:#64748b;font-size:0.72rem;padding:0.75rem;">No recent tier movement events recorded yet. Transitions will appear automatically during scan cycles.</div>';
                            return;
                        }

                        listEl.innerHTML = logs.map(l => {
                            const isPromoted = l.event_type === 'PROMOTED_HOT' || l.to_tier === 'HOT';
                            const isAdded = l.event_type === 'ADDED_WARM';
                            const isDemoted = l.event_type === 'DEMOTED_WARM' || l.to_tier === 'WARM';
                            const isRemoved = l.event_type === 'REMOVED_COLD' || l.to_tier === 'COLD';
                            const isOverride = l.event_type === 'MANUAL_OVERRIDE';

                            const bg = isPromoted ? 'rgba(16,185,129,0.12)' : isAdded ? 'rgba(56,189,248,0.12)' : isDemoted ? 'rgba(245,158,11,0.12)' : isRemoved ? 'rgba(239,68,68,0.12)' : 'rgba(148,163,184,0.1)';
                            const border = isPromoted ? 'rgba(16,185,129,0.3)' : isAdded ? 'rgba(56,189,248,0.3)' : isDemoted ? 'rgba(245,158,11,0.3)' : isRemoved ? 'rgba(239,68,68,0.3)' : 'rgba(148,163,184,0.2)';
                            const color = isPromoted ? '#34d399' : isAdded ? '#38bdf8' : isDemoted ? '#fbbf24' : isRemoved ? '#f87171' : '#cbd5e1';
                            const icon = isPromoted ? '🔥 PROMOTED' : isAdded ? '⚡ ADDED' : isDemoted ? '📉 DEMOTED' : isRemoved ? '❌ REMOVED' : '⚙️ OVERRIDE';

                            const timeStr = l.created_at ? l.created_at.replace('T', ' ').substring(0, 16) : '';
                            const priceStr = l.price ? `₹${l.price.toFixed(2)}` : '';
                            const scoreStr = l.score_after !== null && l.score_after !== undefined ? `Score: ${l.score_after}` : '';

                            return `
                                <div style="background:${bg};border:1px solid ${border};border-radius:6px;padding:0.45rem 0.65rem;display:flex;flex-direction:column;gap:0.2rem;">
                                    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.3rem;">
                                        <div style="display:flex;align-items:center;gap:0.45rem;">
                                            <span style="font-size:0.65rem;font-weight:800;color:${color};background:#000000;padding:0.1rem 0.35rem;border-radius:4px;border:1px solid ${border};">${icon}</span>
                                            <strong style="font-size:0.78rem;color:#f8fafc;font-family:var(--font-mono);cursor:pointer;" onclick="app.inspectBreakoutStock('${l.ticker}')">${l.ticker}</strong>
                                            <span style="font-size:0.7rem;color:#94a3b8;">${l.company_name}</span>
                                            <span style="font-size:0.65rem;color:#64748b;">(${l.from_tier} ➔ ${l.to_tier})</span>
                                        </div>
                                        <div style="font-size:0.65rem;color:#64748b;font-family:var(--font-mono);">
                                            ${priceStr ? priceStr + ' | ' : ''} ${scoreStr ? scoreStr + ' | ' : ''} ${timeStr}
                                        </div>
                                    </div>
                                    <div style="font-size:0.72rem;color:#e2e8f0;line-height:1.35;margin-top:0.1rem;">
                                        <strong>Why:</strong> ${l.reason}
                                    </div>
                                    ${l.catalyst_impact ? `<div style="font-size:0.68rem;color:#38bdf8;margin-top:0.05rem;">📰 <em>Catalyst:</em> ${l.catalyst_impact}</div>` : ''}
                                </div>
                            `;
                        }).join('');
                    }
                } catch (e) {
                    console.error('Error loading breakout audit log:', e);
                    listEl.innerHTML = '<div style="color:#f87171;font-size:0.72rem;padding:0.5rem;">Failed loading movement logs.</div>';
                }
            },

            // =========================================================================
            // 🏛️ Institutional Accumulation & Mutual Fund Activity Hub
            // =========================================================================
            institutionalActiveView: 'accumulating',
            institutionalData: {
                accumulating: [],
                distributing: [],
                funds: [],
                currentStock: null,
            },

            switchInstitutionalView(view) {
                this.institutionalActiveView = view || 'accumulating';
                ['accumulating', 'stock', 'distributing', 'funds'].forEach(v => {
                    const el = document.getElementById('instView-' + v);
                    const btn = document.getElementById('btnInstTab-' + v);
                    if (el) el.style.display = (v === this.institutionalActiveView) ? 'block' : 'none';
                    if (btn) {
                        if (v === this.institutionalActiveView) {
                            btn.style.background = '#1e293b';
                            btn.style.color = '#38bdf8';
                            btn.style.borderColor = 'rgba(56,189,248,0.4)';
                            btn.style.fontWeight = '700';
                        } else {
                            btn.style.background = 'transparent';
                            btn.style.color = '#94a3b8';
                            btn.style.borderColor = 'rgba(255,255,255,0.1)';
                            btn.style.fontWeight = '500';
                        }
                    }
                });
            },

            _accLimit: 25,
            _distLimit: 20,
            _fundsLimit: 50,
            _loadingMoreAcc: false,
            _loadingMoreDist: false,
            _loadingMoreFunds: false,

            async loadInstitutionalData() {
                try {
                    this._accLimit = 25;
                    this._distLimit = 20;
                    this._fundsLimit = 50;

                    const [resAcc, resDist, resFunds] = await Promise.all([
                        fetch(API_BASE + `/api/v1/institutional/accumulating?limit=${this._accLimit}`),
                        fetch(API_BASE + `/api/v1/institutional/distributing?limit=${this._distLimit}`),
                        fetch(API_BASE + `/api/v1/institutional/funds?limit=${this._fundsLimit}`)
                    ]);

                    if (resAcc.ok) {
                        const accData = await resAcc.json();
                        this.institutionalData.accumulating = accData.items || [];
                        this.renderInstitutionalAccumulatingTable(this.institutionalData.accumulating);
                    }

                    if (resDist.ok) {
                        const distData = await resDist.json();
                        this.institutionalData.distributing = distData.items || [];
                        this.renderInstitutionalDistributingTable(this.institutionalData.distributing);
                    }

                    if (resFunds.ok) {
                        const fundsData = await resFunds.json();
                        this.institutionalData.funds = fundsData.funds || [];
                        this.renderInstitutionalFundsTable(this.institutionalData.funds);
                    }

                    // Default search ALLCARGO.NS
                    this.searchInstitutionalStock('ALLCARGO.NS', false);

                } catch (e) {
                    console.error('Failed loading institutional data:', e);
                }
            },

            async loadMoreInstitutionalEquities(type) {
                const isAcc = type === 'accumulating';
                if (isAcc && this._loadingMoreAcc) return;
                if (!isAcc && this._loadingMoreDist) return;

                const btnId = isAcc ? 'btnInstLoadMoreAcc' : 'btnInstLoadMoreDist';
                const btn = document.getElementById(btnId);
                const originalBtnHtml = isAcc 
                    ? '<span>📥</span> Load More Accumulating (+25)'
                    : '<span>📥</span> Load More Distributing (+25)';

                if (isAcc) {
                    this._loadingMoreAcc = true;
                    this._accLimit = (this._accLimit || 25) + 25;
                } else {
                    this._loadingMoreDist = true;
                    this._distLimit = (this._distLimit || 20) + 25;
                }

                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<div style="display:inline-block;animation:spin 1s linear infinite;margin-right:0.3rem;">⏳</div> Loading...';
                }

                try {
                    const targetLimit = isAcc ? this._accLimit : this._distLimit;
                    const endpoint = isAcc 
                        ? `/api/v1/institutional/accumulating?limit=${targetLimit}`
                        : `/api/v1/institutional/distributing?limit=${targetLimit}`;
                    
                    const prevCount = isAcc ? (this.institutionalData.accumulating || []).length : (this.institutionalData.distributing || []).length;
                    const res = await fetch(API_BASE + endpoint);
                    if (res.ok) {
                        const data = await res.json();
                        const items = data.items || [];
                        if (isAcc) {
                            this.institutionalData.accumulating = items;
                            this.renderInstitutionalAccumulatingTable(items);
                        } else {
                            this.institutionalData.distributing = items;
                            this.renderInstitutionalDistributingTable(items);
                        }

                        if (btn) {
                            if (items.length <= prevCount || items.length < targetLimit) {
                                btn.disabled = true;
                                btn.style.opacity = '0.6';
                                btn.innerHTML = `✓ All Setups Loaded (${items.length})`;
                            } else {
                                btn.disabled = false;
                                btn.innerHTML = originalBtnHtml;
                            }
                        }
                    } else {
                        if (btn) {
                            btn.disabled = false;
                            btn.innerHTML = originalBtnHtml;
                        }
                    }
                } catch (e) {
                    console.error('[INSTITUTIONAL] Failed loading more equities:', e);
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalBtnHtml;
                    }
                } finally {
                    if (isAcc) this._loadingMoreAcc = false;
                    else this._loadingMoreDist = false;
                }
            },

            async loadMoreInstitutionalFunds() {
                if (this._loadingMoreFunds) return;
                const btn = document.getElementById('btnInstLoadMoreFunds');
                const originalBtnHtml = '<span>📥</span> Load More Funds & Whales (+25)';

                this._loadingMoreFunds = true;
                this._fundsLimit = (this._fundsLimit || 50) + 25;

                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<div style="display:inline-block;animation:spin 1s linear infinite;margin-right:0.3rem;">⏳</div> Loading...';
                }

                try {
                    const prevCount = (this.institutionalData.funds || []).length;
                    const res = await fetch(API_BASE + `/api/v1/institutional/funds?limit=${this._fundsLimit}`);
                    if (res.ok) {
                        const data = await res.json();
                        const allFunds = data.funds || [];
                        this.institutionalData.funds = allFunds;

                        if (this._currentInvestorFilter === 'ALL') {
                            this.renderInstitutionalFundsTable(allFunds);
                        } else {
                            const filtered = allFunds.filter(f => (f.fund_type || '').toLowerCase().includes(this._currentInvestorFilter.toLowerCase()));
                            this.renderInstitutionalFundsTable(filtered);
                        }

                        if (btn) {
                            if (allFunds.length <= prevCount || allFunds.length < this._fundsLimit) {
                                btn.disabled = true;
                                btn.style.opacity = '0.6';
                                btn.innerHTML = `✓ All Funds Loaded (${allFunds.length})`;
                            } else {
                                btn.disabled = false;
                                btn.innerHTML = originalBtnHtml;
                            }
                        }
                    } else {
                        if (btn) {
                            btn.disabled = false;
                            btn.innerHTML = originalBtnHtml;
                        }
                    }
                } catch (e) {
                    console.error('[INSTITUTIONAL] Failed loading more funds:', e);
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalBtnHtml;
                    }
                } finally {
                    this._loadingMoreFunds = false;
                }
            },

            renderInstitutionalAccumulatingTable(items) {
                const tbody = document.getElementById('instAccumulatingTableBody');
                const countBadge = document.getElementById('instAccCountBadge');
                if (countBadge) {
                    countBadge.innerText = `Showing ${items ? items.length : 0} setups`;
                }
                if (!tbody) return;

                if (!items || !items.length) {
                    tbody.innerHTML = '<tr><td colspan="8" style="padding:2rem;text-align:center;color:#64748b;">No high-conviction accumulating stocks found.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(it => {
                    const badgeBg = it.verdict_badge === 'emerald' ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                    const badgeCol = it.verdict_badge === 'emerald' ? '#34d399' : '#60a5fa';
                    const fundsInStr = `<span style="color:#34d399;font-weight:700;">+${it.funds_accumulating_count} in</span> / <span style="color:#f87171;">-${it.funds_selling_count} out</span>`;
                    const topFundsStr = it.top_funds && it.top_funds.length ? it.top_funds.join(', ') : '—';

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">
                                <span style="color:#38bdf8;">${it.ticker}</span>
                            </td>
                            <td style="padding:0.65rem 0.8rem;color:#cbd5e1;">${it.company_name}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:800;color:#38bdf8;">${it.accumulation_score} / 100</td>
                            <td style="padding:0.65rem 0.8rem;">
                                <span class="signal-badge" style="background:${badgeBg};color:${badgeCol};font-size:0.68rem;padding:0.15rem 0.45rem;">${it.verdict}</span>
                            </td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-size:0.74rem;">${fundsInStr}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f8fafc;">${it.total_institutional_stake}%</td>
                            <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${topFundsStr}">
                                ${topFundsStr}
                            </td>
                            <td style="padding:0.65rem 0.8rem;text-align:center;">
                                <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">Inspect</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            },

            renderInstitutionalDistributingTable(items) {
                const tbody = document.getElementById('instDistributingTableBody');
                const countBadge = document.getElementById('instDistCountBadge');
                if (countBadge) {
                    countBadge.innerText = `Showing ${items ? items.length : 0} setups`;
                }
                if (!tbody) return;

                if (!items || !items.length) {
                    tbody.innerHTML = '<tr><td colspan="6" style="padding:2rem;text-align:center;color:#64748b;">No high-distribution equities detected.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(it => {
                    const exitingStr = it.exiting_funds && it.exiting_funds.length ? it.exiting_funds.join(', ') : '—';
                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f87171;cursor:pointer;" onclick="app.searchInstitutionalStock('${it.ticker}')">${it.ticker}</td>
                            <td style="padding:0.65rem 0.8rem;color:#cbd5e1;">${it.company_name}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f87171;">${it.accumulation_score} / 100</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${it.funds_selling_count} Funds</td>
                            <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${exitingStr}</td>
                            <td style="padding:0.65rem 0.8rem;text-align:center;">
                                <button type="button" onclick="app.searchInstitutionalStock('${it.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">Inspect</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            },

            renderInstitutionalFundsTable(funds) {
                const tbody = document.getElementById('instFundsTableBody') || document.getElementById('instInvestorsDirectoryTableBody');
                const countBadge = document.getElementById('instFundsCountBadge');
                if (countBadge) {
                    countBadge.innerText = `Showing ${funds ? funds.length : 0} funds & whales`;
                }
                const countEl = document.getElementById('instFundsTrackedCount');
                if (countEl) countEl.textContent = funds ? funds.length + '+' : '50+';
                if (!tbody) return;

                if (!funds || !funds.length) {
                    tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No fund profiles loaded.</td></tr>';
                    return;
                }

                tbody.innerHTML = funds.map(f => {
                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:0.65rem 0.8rem;font-weight:700;color:#f8fafc;">${f.fund_name}</td>
                            <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${f.fund_type}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;">${f.total_positions} Stocks</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">+${f.buying_actions}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#f87171;font-weight:700;">-${f.selling_actions}</td>
                            <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">₹${f.total_aum_tracked_cr.toLocaleString()} Cr</td>
                            <td style="padding:0.65rem 0.8rem;text-align:center;">
                                <button type="button" onclick="app.inspectFundPortfolio('${f.fund_name.replace(/'/g, "\\'")}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">View Holdings</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            },

            async searchInstitutionalStock(ticker, autoSwitch = true) {
                if (!ticker) return;
                const cleanTicker = ticker.trim().toUpperCase();
                try {
                    const res = await fetch(API_BASE + `/api/v1/institutional/stock/${encodeURIComponent(cleanTicker)}`);
                    if (res.ok) {
                        const data = await res.json();
                        this.renderStockInstitutionalDetails(data);
                        if (autoSwitch) {
                            this.switchInstitutionalView('stock');
                        }
                    } else {
                        console.warn('Failed finding institutional data for ' + cleanTicker);
                    }
                } catch (e) {
                    console.error('Error fetching institutional stock:', e);
                }
            },

            renderStockInstitutionalDetails(data) {
                if (!data) return;

                const tickerEl = document.getElementById('instSelectedTicker');
                const nameEl = document.getElementById('instSelectedCompanyName');
                const badgeEl = document.getElementById('instSelectedVerdictBadge');
                const scoreTextEl = document.getElementById('instSelectedScoreText');

                if (tickerEl) tickerEl.textContent = data.ticker;
                if (nameEl) nameEl.textContent = data.company_name || '';
                if (badgeEl) {
                    badgeEl.textContent = data.verdict;
                    badgeEl.style.background = data.verdict_badge === 'emerald' ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                    badgeEl.style.color = data.verdict_badge === 'emerald' ? '#34d399' : '#60a5fa';
                }
                if (scoreTextEl) {
                    scoreTextEl.innerHTML = `Accumulation Score: <strong style="color:#38bdf8;">${data.accumulation_score} / 100</strong> | Net Tracked Flow: <strong style="color:#34d399;">+₹${data.net_flow_cr} Cr</strong> | Funds In/Out (QoQ): <strong style="color:#34d399;">+${data.funds_accumulating_count}</strong> / <strong style="color:#f87171;">-${data.funds_selling_count}</strong>`;
                }

                // 1. Shareholding pattern history
                const patContainer = document.getElementById('instShareholdingPatternContainer');
                if (patContainer) {
                    const pats = data.shareholding_patterns || [];
                    if (!pats.length) {
                        patContainer.innerHTML = '<div style="color:#64748b;font-size:0.72rem;">No historical shareholding filings found.</div>';
                    } else {
                        patContainer.innerHTML = `
                            <table style="width:100%;font-size:0.72rem;text-align:left;border-collapse:collapse;">
                                <thead>
                                    <tr style="color:#94a3b8;border-bottom:1px solid rgba(255,255,255,0.06);font-family:var(--font-mono);">
                                        <th style="padding:0.35rem 0.5rem;">QUARTER</th>
                                        <th style="padding:0.35rem 0.5rem;text-align:right;">STOCK PRICE</th>
                                        <th style="padding:0.35rem 0.5rem;text-align:right;">PROMOTER</th>
                                        <th style="padding:0.35rem 0.5rem;text-align:right;">FII / FPI</th>
                                        <th style="padding:0.35rem 0.5rem;text-align:right;">DII / MUTUAL FUNDS</th>
                                        <th style="padding:0.35rem 0.5rem;text-align:right;">RETAIL / PUBLIC</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${pats.map((p, idx) => {
                                        const prevP = pats[idx + 1];
                                        const fiiDelta = prevP ? (p.fii_pct - prevP.fii_pct) : 0;
                                        const diiDelta = prevP ? (p.dii_mf_pct - prevP.dii_mf_pct) : 0;
                                        const fiiDeltaStr = prevP ? (fiiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${fiiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${fiiDelta.toFixed(2)}%)</span>`) : '';
                                        const diiDeltaStr = prevP ? (diiDelta >= 0 ? `<span style="color:#34d399;font-size:0.62rem;">(+${diiDelta.toFixed(2)}%)</span>` : `<span style="color:#f87171;font-size:0.62rem;">(${diiDelta.toFixed(2)}%)</span>`) : '';

                                        const isCurrentQ = p.is_current_quarter || idx === 0;
                                        let priceHtml = '—';
                                        if (isCurrentQ) {
                                            const curP = p.current_price != null ? p.current_price : p.stock_price;
                                            const startP = p.quarter_start_price;
                                            const retQ = (curP && startP) ? (((curP - startP) / startP) * 100) : null;
                                            const retStr = retQ != null ? `<span style="color:${retQ >= 0 ? '#34d399' : '#f87171'};font-size:0.60rem;font-weight:700;">(${retQ >= 0 ? '+' : ''}${retQ.toFixed(1)}%)</span>` : '';
                                            priceHtml = `
                                                <div style="font-weight:800;color:#f8fafc;">₹${curP != null ? Number(curP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}) : '—'} <span style="font-size:0.58rem;color:#38bdf8;background:rgba(56,189,248,0.15);padding:0.02rem 0.25rem;border-radius:3px;font-weight:700;">Live</span></div>
                                                ${startP ? `<div style="font-size:0.60rem;color:#64748b;">Start: ₹${Number(startP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})} ${retStr}</div>` : ''}
                                            `;
                                        } else {
                                            const startP = p.quarter_start_price != null ? p.quarter_start_price : p.stock_price;
                                            priceHtml = `
                                                <div style="font-weight:700;color:#93c5fd;">₹${startP != null ? Number(startP).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}) : '—'}</div>
                                                <div style="font-size:0.60rem;color:#64748b;">Quarter Start</div>
                                            `;
                                        }

                                        return `
                                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                                <td style="padding:0.4rem 0.5rem;font-weight:700;color:#f8fafc;font-family:var(--font-mono);">${p.quarter}</td>
                                                <td style="padding:0.4rem 0.5rem;text-align:right;font-family:var(--font-mono);">${priceHtml}</td>
                                                <td style="padding:0.4rem 0.5rem;text-align:right;color:#cbd5e1;font-family:var(--font-mono);">${p.promoter_pct}%</td>
                                                <td style="padding:0.4rem 0.5rem;text-align:right;color:#38bdf8;font-weight:700;font-family:var(--font-mono);">${p.fii_pct}% ${fiiDeltaStr}</td>
                                                <td style="padding:0.4rem 0.5rem;text-align:right;color:#34d399;font-weight:700;font-family:var(--font-mono);">${p.dii_mf_pct}% ${diiDeltaStr}</td>
                                                <td style="padding:0.4rem 0.5rem;text-align:right;color:#94a3b8;font-family:var(--font-mono);">${p.public_retail_pct}%</td>
                                            </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        `;
                    }
                }

                // 2. Block deals
                const dealsContainer = document.getElementById('instBlockDealsContainer');
                if (dealsContainer) {
                    const deals = data.block_deals || [];
                    if (!deals.length) {
                        dealsContainer.innerHTML = '<div style="color:#64748b;font-size:0.72rem;padding:0.5rem;">No recent bulk or block deals recorded for this ticker.</div>';
                    } else {
                        dealsContainer.innerHTML = deals.map(d => {
                            const isBuy = d.deal_type === 'BUY';
                            const bg = isBuy ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
                            const col = isBuy ? '#34d399' : '#f87171';
                            return `
                                <div style="background:${bg};border:1px solid ${isBuy ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:4px;padding:0.35rem 0.55rem;margin-bottom:0.35rem;display:flex;justify-content:space-between;align-items:center;font-size:0.72rem;">
                                    <div>
                                        <span style="font-weight:700;color:${col};font-family:var(--font-mono);margin-right:0.35rem;">[${d.deal_type}]</span>
                                        <strong style="color:#f8fafc;">${d.client_name}</strong>
                                    </div>
                                    <div style="font-family:var(--font-mono);color:#cbd5e1;text-align:right;">
                                        ${d.quantity.toLocaleString()} shares @ ₹${d.price} (₹${d.value_cr} Cr) | <span style="color:#94a3b8;">${d.deal_date}</span>
                                    </div>
                                </div>
                            `;
                        }).join('');
                    }
                }

                // 3. Fund-by-Fund Table
                const tbody = document.getElementById('instStockHoldingsTableBody');
                if (tbody) {
                    const holdings = data.holdings || [];
                    if (!holdings.length) {
                        tbody.innerHTML = '<tr><td colspan="9" style="padding:2rem;text-align:center;color:#64748b;">No fund positions recorded for this ticker yet.</td></tr>';
                        return;
                    }

                    tbody.innerHTML = holdings.map(h => {
                        const act = h.action;
                        const isBuy = act === 'NEW BUY';
                        const isAcc = act === 'ACCUMULATED';
                        const isTrim = act === 'TRIMMED';
                        const isSold = act === 'SOLD OUT';

                        const actBg = isBuy ? 'rgba(56,189,248,0.15)' : isAcc ? 'rgba(16,185,129,0.15)' : isTrim ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)';
                        const actCol = isBuy ? '#38bdf8' : isAcc ? '#34d399' : isTrim ? '#fbbf24' : '#f87171';
                        const changeStr = h.change_pct > 0 ? `+${h.change_pct}%` : `${h.change_pct}%`;

                        return `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                                <td style="padding:0.6rem 0.8rem;font-weight:700;color:#f8fafc;">${h.fund_name}</td>
                                <td style="padding:0.6rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${h.fund_type}</td>
                                <td style="padding:0.6rem 0.8rem;">
                                    <span class="signal-badge" style="background:${actBg};color:${actCol};font-size:0.68rem;padding:0.12rem 0.4rem;">${h.action}</span>
                                </td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${h.stake_pct}%</td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;font-weight:600;">₹${h.avg_price != null ? Number(h.avg_price).toFixed(2) : '—'}</td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#a7f3d0;font-weight:600;">₹${h.recent_buy_price != null ? Number(h.recent_buy_price).toFixed(2) : '—'}</td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${actCol};">${changeStr}</td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#38bdf8;">₹${h.holding_value_cr} Cr</td>
                                <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#64748b;font-size:0.7rem;">${h.reported_date || '—'}</td>
                            </tr>
                        `;
                    }).join('');
                }
            },

            async inspectFundPortfolio(fundName) {
                if (!fundName) return;
                try {
                    const res = await fetch(API_BASE + `/api/v1/institutional/fund/${encodeURIComponent(fundName)}`);
                    if (res.ok) {
                        const data = await res.json();
                        const holdings = data.holdings || [];
                        const summary = holdings.map(h => `${h.ticker} (${h.stake_pct}% stake, Action: ${h.action})`).join('\n• ');
                        alert(`💼 Holdings for ${fundName}:\n\n• ${summary || 'No positions recorded.'}`);
                    }
                } catch (e) {
                    console.error('Error fetching fund portfolio:', e);
                }
            }
        });

        // [] → extracted to modules/stock_modal.js
                // Downstreams Header Group
                html += `<tr style="background: rgba(30, 41, 59, 0.6); font-weight: 700; color: #94a3b8; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.04em;">
                    <td colspan="7" style="padding: 0.4rem 0.7rem; border-top: 1px solid rgba(255,255,255,0.06); border-bottom: 1px solid rgba(255,255,255,0.06);">
                        🏛️ Market Data &amp; Corporate Filings Downstreams
                    </td>
                </tr>`;

                const downstreams = data.downstreams || [];
                downstreams.forEach(d => {
                    const statusColor = d.status === 'throttled' ? '#ef4444' : (d.status === 'warning' ? '#f59e0b' : '#34d399');
                    const statusBg = d.status === 'throttled' ? 'rgba(239,68,68,0.15)' : (d.status === 'warning' ? 'rgba(245,158,11,0.15)' : 'rgba(16,185,129,0.15)');
                    const statusBorder = d.status === 'throttled' ? 'rgba(239,68,68,0.3)' : (d.status === 'warning' ? 'rgba(245,158,11,0.3)' : 'rgba(16,185,129,0.3)');

                    html += `<tr style="border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s ease;" onmouseenter="this.style.background='rgba(255,255,255,0.03)'" onmouseleave="this.style.background='transparent'">
                        <td style="padding: 0.55rem 0.7rem;">
                            <div style="display: flex; align-items: center; gap: 0.45rem;">
                                <span style="font-size: 1.05rem;">${d.icon || '📦'}</span>
                                <div>
                                    <div style="font-weight: 700; color: #ffffff; font-size: 0.78rem;">${d.name}</div>
                                    <div style="font-size: 0.65rem; color: #64748b; margin-top: 0.05rem;">${d.description}</div>
                                </div>
                            </div>
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); font-weight: 700; color: #ffffff;">
                            ${(d.total_calls || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); font-weight: 700; color: #38bdf8;">
                            ${(d.calls_today || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); color: #cbd5e1;">
                            ${(d.calls_1h || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); color: #94a3b8;">
                            ${(d.calls_1m || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.65rem; text-align: right; font-family: var(--font-mono); font-size: 0.68rem; color: #94a3b8;">
                            ${d.limit_1m}/min &bull; ${d.limit_24h}/day
                        </td>
                        <td style="padding: 0.55rem 0.65rem; text-align: center;">
                            <span class="signal-badge" style="background: ${statusBg}; color: ${statusColor}; border: 1px solid ${statusBorder}; font-size: 0.62rem; padding: 0.12rem 0.45rem; border-radius: 4px;">
                                ${d.status_badge || '🟢 Ready'}
                            </span>
                        </td>
                    </tr>`;
                });

                // AI Models Header Group
                html += `<tr style="background: rgba(30, 41, 59, 0.6); font-weight: 700; color: #94a3b8; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.04em;">
                    <td colspan="7" style="padding: 0.4rem 0.7rem; border-top: 1px solid rgba(255,255,255,0.06); border-bottom: 1px solid rgba(255,255,255,0.06);">
                        🤖 AI Reasoning &amp; Sequence Forecasting Models
                    </td>
                </tr>`;

                const aiModels = data.ai_models || [];
                aiModels.forEach(m => {
                    const statusColor = m.status === 'throttled' ? '#ef4444' : (m.status === 'warning' ? '#f59e0b' : '#34d399');
                    const statusBg = m.status === 'throttled' ? 'rgba(239,68,68,0.15)' : (m.status === 'warning' ? 'rgba(245,158,11,0.15)' : 'rgba(16,185,129,0.15)');
                    const statusBorder = m.status === 'throttled' ? 'rgba(239,68,68,0.3)' : (m.status === 'warning' ? 'rgba(245,158,11,0.3)' : 'rgba(16,185,129,0.3)');

                    html += `<tr style="border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s ease;" onmouseenter="this.style.background='rgba(255,255,255,0.03)'" onmouseleave="this.style.background='transparent'">
                        <td style="padding: 0.55rem 0.7rem;">
                            <div style="display: flex; align-items: center; gap: 0.45rem;">
                                <span style="font-size: 1.05rem;">${m.icon || '🤖'}</span>
                                <div>
                                    <div style="display: flex; align-items: center; gap: 0.35rem;">
                                        <span style="font-weight: 700; color: #ffffff; font-size: 0.78rem;">${m.name}</span>
                                        <span style="font-size: 0.60rem; padding: 0.05rem 0.3rem; border-radius: 3px; background: rgba(255,255,255,0.08); color: ${m.color || '#38bdf8'}; font-weight: 600;">${m.badge || m.id}</span>
                                    </div>
                                    <div style="font-size: 0.65rem; color: #64748b; margin-top: 0.05rem;">${m.description || m.id}</div>
                                </div>
                            </div>
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); font-weight: 700; color: #34d399;">
                            ${(m.total_calls || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); font-weight: 700; color: #38bdf8;">
                            ${(m.calls_today || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); color: #cbd5e1;">
                            ${(m.calls_1h || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.55rem; text-align: right; font-family: var(--font-mono); color: #94a3b8;">
                            ${(m.calls_1m || 0).toLocaleString()}
                        </td>
                        <td style="padding: 0.55rem 0.65rem; text-align: right; font-family: var(--font-mono); font-size: 0.68rem; color: #94a3b8;">
                            ${m.remaining_1m !== undefined ? m.remaining_1m + ' rem/min' : '20/min'} &bull; ${m.remaining_24h !== undefined ? m.remaining_24h + ' rem/day' : '200/day'}
                        </td>
                        <td style="padding: 0.55rem 0.65rem; text-align: center;">
                            <span class="signal-badge" style="background: ${statusBg}; color: ${statusColor}; border: 1px solid ${statusBorder}; font-size: 0.62rem; padding: 0.12rem 0.45rem; border-radius: 4px;">
                                ${m.status_badge || '🟢 Ready'}
                            </span>
                        </td>
                    </tr>`;
                });

                tableBody.innerHTML = html;
            } catch (e) {
                console.error('[API-USAGE] Error loading playground API usage:', e);
                if (tableBody) tableBody.innerHTML = '<tr><td colspan="7" style="padding:1.5rem;text-align:center;color:#ef4444;">Error fetching API usage metrics</td></tr>';
            }
        };

        // Initialize & export to window
        window.app = app;
        if (typeof app.init === 'function') {
            try { app.init(); } catch (e) { console.warn('app.init:', e); }
        }
        // initGlobalPriceRefresh -> handled by modules/price_refresh.js
        try {
            app.updateResultsMonthSummaryCards();
        } catch (e) {
            console.warn('Initial month summary fetch:', e);
        }
        // updateSidebarBadges + 45s interval -> handled by modules/sidebar_badges.js



