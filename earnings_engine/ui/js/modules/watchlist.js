// =========================================================================
// watchlist — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
app.watchlistTab = {
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
    };
})(); // end watchlist IIFE