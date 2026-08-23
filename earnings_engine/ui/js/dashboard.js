        const API_BASE = window.location.origin;

        const app = {
            allTickers: [],
            resultsData: [],
            swingData: [],
            sortKey: 'earnings_date',
            sortDir: 'asc',

            // ---------- Watchlist tab (multi-list manager) ----------
            watchlistTab: {
                names: {},       // symbol -> display name cache for chip tooltips / autocomplete
                ranges: {},      // watchlist:ticker -> swing range object
                customLists: [], // Custom user watchlists
                universes: [],   // Built-in universes (NSE Top, US Top, NSE Large Cap, etc.)
                activeFilter: 'all', // 'all', 'under_100', 'universes', 'custom'
                searchQuery: '',

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
                    this.renderCards();
                },

                handleSearch(q) {
                    this.searchQuery = (q || '').trim().toLowerCase();
                    this.renderCards();
                },

                async load(forceRefresh = false) {
                    const el = document.getElementById('watchlistCards');
                    if (!el) return;
                    if (!el.children.length) el.innerHTML = '<div class="timestamp" style="padding:0.5rem;">Loading watchlists & universes...</div>';
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
                        if (totalBadge) {
                            const totalLists = this.customLists.length + this.universes.length;
                            totalBadge.textContent = totalLists + ' lists (' + this.universes.length + ' universes, ' + this.customLists.length + ' custom)';
                        }

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

                        this.renderCards();
                    } catch (e) {
                        console.error('Error loading watchlists:', e);
                        el.innerHTML = '<div class="card" style="margin:0;color:var(--red)">Error loading watchlists. Check server logs.</div>';
                    }
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
                            '<h4 style="margin:0;font-size:0.95rem;color:#e9d5ff;display:flex;align-items:center;gap:0.35rem;">⭐ Custom User Watchlists <span style="font-size:0.75rem;background:rgba(168,85,247,0.2);padding:0.1rem 0.4rem;border-radius:9999px;">' + filteredCustom.length + '</span></h4>' +
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
                                ? '<span style="font-size:0.72rem;opacity:0.85;margin-left:0.25rem;color:' + (isUser ? '#c084fc' : '#60a5fa') + ';" title="' + (isUser ? 'Custom swing range' : 'Auto swing range') + '">' +
                                  lowStr + '–' + upStr + (r.cycles ? ' ⤫' + r.cycles : '') +
                                  '</span>'
                                : '';
                            return '<span style="display:inline-flex;align-items:center;gap:0.35rem;background:rgba(99,102,241,0.12);border:1px solid ' + (isUser ? 'rgba(139,92,246,0.45)' : 'rgba(99,102,241,0.25)') + ';padding:0.25rem 0.6rem;border-radius:9999px;font-size:0.78rem;" title="' + (this.names[t] || t) + '">' +
                                '<strong>' + t + '</strong>' +
                                rangeBadge +
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
                                '<button class="btn btn-sm" onclick="app.watchlistTab.copyToCustom(\'' + u.name.replace(/'/g, "\\'") + '\',\'' + (u.display_name || u.name).replace(/'/g, "\\'") + '\',' + JSON.stringify(tickers).replace(/"/g, '&quot;') + ')" style="background:rgba(168,85,247,0.15);color:#e9d5ff;border:1px solid rgba(168,85,247,0.35);" title="Copy all tickers into a customizable custom watchlist">📋 Copy to Custom</button>' +
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
                                ? '<span style="font-size:0.72rem;opacity:0.85;margin-left:0.25rem;color:' + (isUser ? '#c084fc' : '#60a5fa') + ';" title="' + (isUser ? 'Custom swing range' : 'Auto swing range') + '">' +
                                  lowStr + '–' + upStr + (r.cycles ? ' ⤫' + r.cycles : '') +
                                  '</span>'
                                : '';
                            return '<span style="display:inline-flex;align-items:center;gap:0.35rem;background:rgba(59,130,246,0.15);border:1px solid ' + (isUser ? 'rgba(139,92,246,0.45)' : 'rgba(59,130,246,0.3)') + ';padding:0.3rem 0.65rem;border-radius:9999px;font-size:0.8rem;" title="' + (this.names[t] || t) + '">' +
                                '<strong>' + t + '</strong>' +
                                rangeBadge +
                                '<button onclick="app.openSwingRangeModal(\'' + name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--light);opacity:0.7;cursor:pointer;font-size:0.75rem;line-height:1;padding:0 0.15rem;" title="Edit Swing Range">⚙</button>' +
                                '<button onclick="app.watchlistTab.removeTicker(\'' + name.replace(/'/g, "\\'") + '\',\'' + t.replace(/'/g, "\\'") + '\')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:1rem;line-height:1;margin-left:0.1rem;" title="Remove">&minus;</button>' +
                                '</span>';
                          }).join('')
                        : '<span class="timestamp" style="font-size:0.8rem;">Empty — add a ticker below.</span>';

                    const under100Badge = isUnder100
                        ? '<span style="background:rgba(234,179,8,0.2);color:#fef08a;border:1px solid rgba(234,179,8,0.4);font-size:0.7rem;font-weight:700;padding:0.12rem 0.45rem;border-radius:9999px;">⚡ Under 100 Stocks</span>'
                        : '';

                    return '<div class="card" id="wlCard' + wi + '" style="margin:0 0 0.75rem 0;position:relative;z-index:' + (200 - wi) + ';border:1px solid rgba(168,85,247,0.25);">' +
                        '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.6rem;">' +
                            '<div>' +
                                '<div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.2rem;">' +
                                    '<h4 style="margin:0;font-size:1.05rem;">' + name + '</h4>' +
                                    '<span style="background:rgba(168,85,247,0.2);color:#e9d5ff;font-size:0.7rem;font-weight:600;padding:0.12rem 0.45rem;border-radius:9999px;">⭐ Custom Watchlist</span>' +
                                    under100Badge +
                                '</div>' +
                                '<span class="timestamp" style="font-size:0.72rem;">' + tickers.length + ' stock' + (tickers.length === 1 ? '' : 's') + '</span>' +
                            '</div>' +
                            '<div style="display:flex;gap:0.35rem;">' +
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
                        await this.load();
                        this.setFilter('custom');
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
                        await this.load();
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
                        await this.load();
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
                        await this.load();
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
                        await this.load();
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
                        await this.load();
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
                        this.activeFetchControllers[taskName].abort('Superseded by new request');
                    } catch (e) {}
                }
                const controller = new AbortController();
                this.activeFetchControllers[taskName] = controller;
                return fetch(url, { ...options, signal: controller.signal })
                    .finally(() => {
                        if (this.activeFetchControllers[taskName] === controller) {
                            delete this.activeFetchControllers[taskName];
                        }
                    });
            },

            cancelReportLoad(taskName) {
                if (this.activeFetchControllers[taskName]) {
                    try {
                        this.activeFetchControllers[taskName].abort('User cancelled');
                    } catch (e) {}
                    delete this.activeFetchControllers[taskName];
                }
                this.resetTaskLoadingUI(taskName, '⚠️ Request cancelled by user.');
            },

            cancelAllPendingRequests(reason = 'Tab switched') {
                Object.keys(this.activeFetchControllers || {}).forEach(taskName => {
                    try {
                        if (this.activeFetchControllers[taskName]) {
                            this.activeFetchControllers[taskName].abort(reason);
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

                const validTabs = ['results', 'monthfilter', 'scanner', 'catalysts', 'gainers', 'swing', 'watchlist', 'kronos', 'consensus', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
                
                if (hash && validTabs.includes(hash.toLowerCase())) return hash.toLowerCase();
                if (queryTab && validTabs.includes(queryTab.toLowerCase())) return queryTab.toLowerCase();
                if (storedTab && validTabs.includes(storedTab.toLowerCase())) return storedTab.toLowerCase();
                return 'results';
            },

            async init() {
                this.initCustomizer();
                this._bindWatchlistSelectionPersistence();
                this._restoreBdControls();
                this._restorePatternsControls();
                this.populateWatchlistDropdowns();
                this.loadOverview();
                
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
                const validTabs = ['results', 'monthfilter', 'scanner', 'catalysts', 'gainers', 'swing', 'watchlist', 'kronos', 'coverage', 'industries', 'patterns', 'buydip', 'backtest', 'playground'];
                if (!validTabs.includes(name)) name = 'results';

                // Abort any pending fetch requests when switching tabs
                this.cancelAllPendingRequests('Tab switched to ' + name);

                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                
                const targetContent = document.getElementById('tab-' + name);
                if (targetContent) targetContent.classList.add('active');

                document.querySelectorAll('.tab-btn').forEach(el => {
                    const onclickAttr = el.getAttribute('onclick') || '';
                    if (onclickAttr.includes("'" + name + "'") || onclickAttr.includes('"' + name + '"') || el.textContent.toLowerCase().includes(name)) {
                        el.classList.add('active');
                    }
                });

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
                if (name === 'watchlist' && (!this.watchlistTab.customLists || !this.watchlistTab.customLists.length)) {
                    this.watchlistTab.load();
                }
                if (name === 'kronos') {
                    this.maybeShowKronosPrompt();
                }
                if (name === 'playground' && !this.pg._initialized) {
                    this.pg.init();
                    this.pg._initialized = true;
                }
                if (name === 'backtest') {
                    this.initBacktestTab();
                }
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

                    // If active category not in data, pick first
                    if (!this.scannerCategoriesData.some(c => c.id === this.activeScannerCategory) && this.scannerCategoriesData.length) {
                        this.activeScannerCategory = this.scannerCategoriesData[0].id;
                    }

                    await this.loadScannerCategoryCandidates(this.activeScannerCategory);
                } catch (e) {
                    console.error('Error loading scanner categories:', e);
                }
            },

            renderScannerCategoriesPills() {
                const pillsEl = document.getElementById('scannerCategoryPills');
                if (!pillsEl) return;
                const items = this.scannerCategoriesData || [];

                pillsEl.innerHTML = items.map(c => {
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

                const catMeta = (this.scannerCategoriesData || []).find(c => c.id === catId) || {};
                if (titleEl) titleEl.innerHTML = (catMeta.icon || '🔍') + ' ' + (catMeta.name || catId);
                if (descEl) descEl.textContent = catMeta.description || 'Active market candidates matching this setup.';

                if (tbody) tbody.innerHTML = '<tr><td colspan="10" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Scanning candidates for ' + (catMeta.name || catId) + '...</td></tr>';

                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                try {
                    const res = await fetch(API_BASE + '/api/v1/scanner/category/' + encodeURIComponent(catId) + '?universe=' + encodeURIComponent(wl) + '&limit=25');
                    const data = await res.json();
                    this.scannerCandidatesData = data.candidates || [];
                    if (countBadge) countBadge.textContent = this.scannerCandidatesData.length + ' stocks';
                    this.renderScannerCandidates();
                } catch (e) {
                    console.error('Error loading category candidates:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="10" style="padding:1rem;text-align:center;color:var(--red);">Failed loading category candidates.</td></tr>';
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
                    tbody.innerHTML = '<tr><td colspan="10" style="padding:1.5rem;text-align:center;color:var(--muted);">No candidates matching selected category in this universe. Click "⚡ Deep Sweep All Categories" to refresh feeds.</td></tr>';
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
                            '<div style="font-weight:700;font-size:0.85rem;color:var(--light);">' + (c.stock_name || c.ticker) + '</div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);">' + c.ticker + '</div>' +
                        '</td>' +
                        '<td><strong>₹' + (c.current_price ? Number(c.current_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td><strong class="' + retClass + '" style="font-size:0.9rem;">' + retSign + ret.toFixed(2) + '%</strong></td>' +
                        '<td><strong style="color:' + volColor + ';">' + volMult + 'x</strong> <span style="font-size:0.7rem;color:var(--muted);">20D Avg</span></td>' +
                        '<td><strong style="color:#fbbf24;font-size:0.85rem;">' + triggerText + '</strong></td>' +
                        '<td><span style="color:' + confColor + ';font-weight:700;font-size:0.85rem;">' + confScore + '%</span></td>' +
                        '<td><span style="font-size:0.75rem;color:var(--muted);white-space:nowrap;">' + (c.expected_horizon || '1-3 Days') + '</span></td>' +
                        '<td style="max-width:320px;">' +
                            '<div style="font-size:0.75rem;color:#cbd5e1;line-height:1.35;">' + (c.why_it_matches || c.catalyst_summary || '') + '</div>' +
                        '</td>' +
                        '<td style="text-align:center;">' +
                            '<div style="display:flex;gap:0.3rem;justify-content:center;">' +
                                '<button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="14D OHLCV Benchmark">📊 Benchmark</button>' +
                                '<button onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(139,92,246,0.2);color:#c084fc;border:1px solid rgba(139,92,246,0.4);border-radius:0.3rem;" title="Run AI Forecast">🔮 Predict</button>' +
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

            async loadCatalysts() {
                const feedGrid = document.getElementById('catalystsFeedGrid');
                if (!feedGrid) return;
                const wl = localStorage.getItem('selectedGlobalWatchlist') || '';
                feedGrid.innerHTML = '<div class="card" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading short-term market moving catalysts' + (wl ? ' for "' + wl + '"' : '') + '...</div>';
                
                try {
                    // Fetch stats and items in parallel
                    const [itemsRes, statsRes] = await Promise.all([
                        fetch(API_BASE + '/api/v1/news/catalysts' + (wl ? '?watchlist=' + encodeURIComponent(wl) : '')),
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
                filtered.sort((a, b) => {
                    const da = a.published_at || a.created_at || '';
                    const db = b.published_at || b.created_at || '';
                    if (da && db && da !== db) return db.localeCompare(da);
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
                                '<strong style="font-size:1.05rem;color:#f8fafc;">' + (c.stock_name || c.ticker) + '</strong>' +
                                '<span class="signal-badge" style="background:rgba(59,130,246,0.2);color:#60a5fa;font-size:0.72rem;">' + c.ticker + '</span>' +
                                '<span style="background:' + impactBadgeBg + ';color:' + impactBadgeColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + impactLabel + '</span>' +
                                '<span style="background:' + dirBadgeBg + ';color:' + dirColor + ';padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;font-weight:700;">' + dirIcon + '</span>' +
                                '<span style="background:rgba(139,92,246,0.15);color:#c084fc;padding:0.15rem 0.5rem;border-radius:0.3rem;font-size:0.7rem;">' + c.category + '</span>' +
                            '</div>' +
                            '<div style="display:flex;align-items:center;gap:0.4rem;">' +
                                '<span class="timestamp" style="font-size:0.72rem;background:rgba(255,255,255,0.05);padding:0.15rem 0.45rem;border-radius:0.25rem;">' + (c.publisher || 'News') + ' &middot; ⏱️ ' + dateDisplay + '</span>' +
                                '<button onclick="app.runPredictionForTickerSingle(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(139,92,246,0.2);color:#c084fc;border:1px solid rgba(139,92,246,0.4);border-radius:0.3rem;" title="Run Kronos Forecast">🔮 Predict</button>' +
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
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Scanning Feeds...';
                }
                try {
                    const wl = localStorage.getItem('selectedGlobalWatchlist') || '';
                    const res = await fetch(API_BASE + '/api/v1/news/scan', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({watchlist: wl})
                    });
                    const data = await res.json();
                    await this.loadCatalysts();
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

            async loadDailyTopGainers() {
                const tbody = document.getElementById('topGainersTableBody');
                if (!tbody) return;
                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_ALL';
                tbody.innerHTML = '<tr><td colspan="9" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Analyzing daily top gainers & drivers...</td></tr>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/daily?universe=' + encodeURIComponent(wl) + '&top_n=10');
                    const data = await res.json();
                    this.gainersData = data.gainers || [];
                    this.renderGainersLeaderboard();
                } catch (e) {
                    console.error('Error loading top gainers:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="9" style="padding:1rem;text-align:center;color:var(--red);">Failed loading daily top gainers.</td></tr>';
                }
            },

            renderGainersLeaderboard() {
                const tbody = document.getElementById('topGainersTableBody');
                if (!tbody) return;
                const items = this.gainersData || [];
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="9" style="padding:1.5rem;text-align:center;color:var(--muted);">No top gainers found for selected universe.</td></tr>';
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
                            '<div style="font-weight:700;font-size:0.85rem;color:var(--light);">' + (g.stock_name || g.ticker) + '</div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);">' + g.ticker + '</div>' +
                        '</td>' +
                        '<td><strong>' + currSym + (g.close_price ? Number(g.close_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td><strong class="price-positive" style="font-size:0.95rem;">+' + Number(g.return_pct).toFixed(2) + '%</strong></td>' +
                        '<td><strong style="color:' + volColor + ';">' + volMult + 'x</strong> <span style="font-size:0.7rem;color:var(--muted);">20D Avg</span></td>' +
                        '<td>' + status52w + '</td>' +
                        '<td style="max-width:320px;">' +
                            '<div style="font-weight:600;color:#38bdf8;font-size:0.78rem;margin-bottom:0.15rem;">' + (g.primary_driver || '').replace(/_/g, ' ') + '</div>' +
                            '<div style="font-size:0.73rem;color:#cbd5e1;line-height:1.35;">' + (g.driver_explanation || '') + '</div>' +
                        '</td>' +
                        '<td><span style="background:rgba(139,92,246,0.15);color:#c084fc;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;white-space:nowrap;">' + (g.pattern_name || 'Breakout') + '</span></td>' +
                        '<td style="text-align:center;">' +
                            '<div style="display:flex;gap:0.3rem;justify-content:center;">' +
                                '<button onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + g.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="14D OHLCV Forecast Benchmark">📊 Benchmark</button>' +
                                '<button onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + g.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(139,92,246,0.2);color:#c084fc;border:1px solid rgba(139,92,246,0.4);border-radius:0.3rem;" title="Run AI Prediction">🔮 Predict</button>' +
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
                tbody.innerHTML = '<tr><td colspan="8" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Scanning watchlist for pre-breakout patterns...</td></tr>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/gainers/upcoming-setups?universe=' + encodeURIComponent(wl));
                    const data = await res.json();
                    this.upcomingSetupsData = data.setups || [];
                    this.renderUpcomingSetups();
                } catch (e) {
                    console.error('Error scanning setups:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="padding:1rem;text-align:center;color:var(--red);">Failed scanning watchlist setups.</td></tr>';
                }
            },

            renderUpcomingSetups() {
                const tbody = document.getElementById('upcomingSetupsTableBody');
                if (!tbody) return;
                const items = this.upcomingSetupsData || [];
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="8" style="padding:1.5rem;text-align:center;color:var(--muted);">No stocks currently in tight pre-breakout coils in this universe. Try selecting another universe above.</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(s => {
                    const currSym = (s.ticker.endsWith('.NS') || s.ticker.endsWith('.BO')) ? '₹' : '$';
                    return '<tr>' +
                        '<td>' +
                            '<div style="font-weight:700;font-size:0.85rem;color:var(--light);">' + (s.stock_name || s.ticker) + '</div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);">' + s.ticker + '</div>' +
                        '</td>' +
                        '<td><strong>' + currSym + (s.current_price ? Number(s.current_price).toFixed(2) : '—') + '</strong></td>' +
                        '<td><span style="background:rgba(139,92,246,0.15);color:#c084fc;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">' + s.matching_pattern + '</span></td>' +
                        '<td><span style="background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.2rem 0.5rem;border-radius:0.3rem;font-size:0.72rem;font-weight:600;">' + s.setup_stage + '</span></td>' +
                        '<td><strong style="color:#fbbf24;font-size:0.85rem;">' + currSym + Number(s.trigger_level).toFixed(2) + '</strong></td>' +
                        '<td><span style="color:#34d399;font-weight:700;">' + s.confidence_score + '%</span></td>' +
                        '<td style="max-width:320px;font-size:0.75rem;color:#cbd5e1;line-height:1.35;">' + s.why_it_matches + '</td>' +
                        '<td style="text-align:center;">' +
                            '<button onclick="event.stopPropagation(); app.runPredictionForTickerSingle(\'' + s.ticker + '\')" class="btn btn-sm" style="padding:0.15rem 0.45rem;font-size:0.72rem;background:rgba(139,92,246,0.2);color:#c084fc;border:1px solid rgba(139,92,246,0.4);border-radius:0.3rem;" title="Run AI Prediction">🔮 Predict</button>' +
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

            onResultsPresetChange(preset) {
                const customSpan = document.getElementById('resultsCustomInputs');
                const pastInput = document.getElementById('resultsPastDays');
                const nextInput = document.getElementById('resultsDays');
                if (!customSpan || !pastInput || !nextInput) return;

                if (preset === 'pm60') {
                    customSpan.style.display = 'none';
                    pastInput.value = 60;
                    nextInput.value = 60;
                } else if (preset === 'pm30') {
                    customSpan.style.display = 'none';
                    pastInput.value = 30;
                    nextInput.value = 30;
                } else if (preset === 'next14') {
                    customSpan.style.display = 'none';
                    pastInput.value = 0;
                    nextInput.value = 14;
                } else if (preset === 'next30') {
                    customSpan.style.display = 'none';
                    pastInput.value = 0;
                    nextInput.value = 30;
                } else if (preset === 'next60') {
                    customSpan.style.display = 'none';
                    pastInput.value = 0;
                    nextInput.value = 60;
                } else if (preset === 'past60') {
                    customSpan.style.display = 'none';
                    pastInput.value = 60;
                    nextInput.value = 0;
                } else if (preset === 'custom') {
                    customSpan.style.display = 'inline-flex';
                }
            },

            async loadResultsReport() {
                const preset = document.getElementById('resultsRangePreset')?.value || 'pm60';
                let pastDays = 60;
                let days = 60;

                if (preset === 'pm60') {
                    pastDays = 60; days = 60;
                } else if (preset === 'pm30') {
                    pastDays = 30; days = 30;
                } else if (preset === 'next14') {
                    pastDays = 0; days = 14;
                } else if (preset === 'next30') {
                    pastDays = 0; days = 30;
                } else if (preset === 'next60') {
                    pastDays = 0; days = 60;
                } else if (preset === 'past60') {
                    pastDays = 60; days = 0;
                } else {
                    pastDays = parseInt(document.getElementById('resultsPastDays')?.value || '60', 10);
                    days = parseInt(document.getElementById('resultsDays')?.value || '60', 10);
                }

                const market = document.getElementById('resultsMarket')?.value || '';
                const query = '?days=' + days + '&past_days=' + pastDays + (market ? '&market=' + encodeURIComponent(market) : '');
                
                const loadBtns = [document.getElementById('resultsLoadBtn'), document.getElementById('resultsCenterLoadBtn')].filter(Boolean);
                loadBtns.forEach(b => { b.disabled = true; b.innerHTML = '<span class="loading-spinner"></span> Loading...'; });
                const cancelBtn = document.getElementById('resultsCancelBtn');
                if (cancelBtn) cancelBtn.style.display = 'inline-block';
                
                const statusEl = document.getElementById('resultsReportStatus');
                const countBadge = document.getElementById('resultsCount');
                if (statusEl) statusEl.textContent = 'Fetching corporate results across ±2 months...';
                
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
                    
                    // Render Month breakdown tabs (e.g. 4 tabs for 4 months)
                    this.renderResultsMonthTabs();

                    // Show first 10 dates by default (or all if fewer)
                    this.resultsShowDays = Math.min(10, (this.resultsDaySections || []).length || 1);
                    this.renderResultsDays();
                    
                    const totalDates = (this.resultsDaySections || []).length;
                    if (countBadge) {
                        countBadge.style.display = 'inline-block';
                        countBadge.textContent = this.resultsTotalStocks + ' results (' + totalDates + ' dates)';
                    }
                    if (statusEl) statusEl.textContent = 'Report loaded: ' + this.resultsTotalStocks + ' corporate results across ' + totalDates + ' dates in ±2 months window (' + new Date().toLocaleTimeString() + ')';
                    
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
                html += '<button type="button" onclick="app.filterResultsByMonth(\'ALL\')" class="btn btn-sm" style="' + allBtnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                    '🌐 All (±2M) <span style="background:rgba(0,0,0,0.25);padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;margin-left:0.2rem;">' + totalStocks + '</span>' +
                    '</button>';

                // 2. Individual month tabs (4 tabs for 4 months)
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
                        btnStyle = 'background:rgba(192,132,252,0.12);color:#d8b4fe;border:1px solid rgba(192,132,252,0.3);';
                    }

                    html += '<button type="button" onclick="app.filterResultsByMonth(\'' + m.month_key + '\')" class="btn btn-sm" style="' + btnStyle + 'padding:0.25rem 0.65rem;border-radius:0.4rem;font-size:0.75rem;cursor:pointer;">' +
                        tag + m.month_label + ' ' +
                        '<span style="background:' + badgeBg + ';color:' + badgeColor + ';padding:0.1rem 0.35rem;border-radius:9999px;font-size:0.7rem;font-weight:700;margin-left:0.2rem;">' + (m.stocks_count || 0) + '</span>' +
                        '</button>';
                });

                el.innerHTML = html;
                el.style.display = 'flex';
            },

            filterResultsByMonth(monthKey) {
                this.resultsActiveMonth = monthKey;
                this.renderResultsMonthTabs();

                let filtered = [];
                let filteredStocks = 0;

                if (monthKey === 'ALL') {
                    filtered = this.resultsDaySectionsMeta.map(m => m.html);
                    filteredStocks = this.resultsTotalStocks || this.resultsDaySectionsMeta.reduce((acc, m) => acc + (m.stocks_count || 1), 0);
                } else {
                    const matchingMeta = this.resultsDaySectionsMeta.filter(m => m.month_key === monthKey);
                    filtered = matchingMeta.map(m => m.html);
                    filteredStocks = matchingMeta.reduce((acc, m) => acc + (m.stocks_count || 0), 0);
                }

                this.resultsDaySections = filtered;
                this.resultsShowDays = Math.min(10, filtered.length || 1);
                this.renderResultsDays();

                const countBadge = document.getElementById('resultsCount');
                if (countBadge) {
                    const mObj = (this.resultsMonths || []).find(m => m.month_key === monthKey);
                    const label = (monthKey === 'ALL') ? '±2 Months' : (mObj ? mObj.month_label : monthKey);
                    countBadge.textContent = filteredStocks + ' results (' + filtered.length + ' dates in ' + label + ')';
                }
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
            },

            showMoreResultsDays() {
                if (this.resultsShowDays < (this.resultsDaySections || []).length) {
                    this.resultsShowDays = Math.min(this.resultsShowDays + 5, (this.resultsDaySections || []).length);
                    this.renderResultsDays();
                }
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
                        '<h4>' + (r.ticker || '?') + '</h4>' +
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
                    tbody.innerHTML = '<tr><td colspan="10" style="padding:1rem;text-align:center;color:var(--muted)">No results</td></tr>';
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
                        '<td><strong>' + (r.ticker || '?') + '</strong></td>' +
                        '<td>' + (r.earnings_date || 'N/A') + '</td>' +
                        '<td>' + (r.current_price ? r.current_price.toFixed(2) : 'N/A') + '</td>' +
                        '<td>' + (r.market_cap ? this.formatMarketCap(r.market_cap) : 'N/A') + '</td>' +
                        '<td class="' + cls7 + '">' + (r.seven_day_return_pct !== null ? r.seven_day_return_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td class="' + cls + '">' + (r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td>' + (r.earnings_week_move_pct !== null ? r.earnings_week_move_pct.toFixed(2) + '%' : 'N/A') + '</td>' +
                        '<td>' + (r.prev_quarter_earnings_score !== null ? r.prev_quarter_earnings_score + '/9' : 'N/A') + '</td>' +
                        '<td class="' + trendCls + '">' + trend + '</td>' +
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
                        btn.style.background = p === 'buyzone' ? 'rgba(16,185,129,0.12)' : (p === 'strongbuy' ? 'rgba(16,185,129,0.1)' : (p === 'custom' ? 'rgba(139,92,246,0.12)' : 'rgba(255,255,255,0.06)'));
                        btn.style.color = p === 'buyzone' ? '#34d399' : (p === 'strongbuy' ? '#10b981' : (p === 'custom' ? '#c084fc' : 'var(--muted)'));
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
                    if (tbody) tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:2rem;color:var(--muted)">No stocks match the selected filter.</td></tr>';
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
                        const srSourceCls = isUser ? 'background:rgba(139,92,246,0.25);color:#c084fc;' : 'background:rgba(148,163,184,0.15);color:#94a3b8;';
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
                               '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.12rem 0.35rem;font-size:0.68rem;background:rgba(139,92,246,0.18);color:#c084fc;border:1px solid rgba(139,92,246,0.3);" title="Re-run Kronos AI prediction">🔄</button>' +
                               '</div>')
                            : ('<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.2rem 0.5rem;font-size:0.72rem;background:rgba(139,92,246,0.22);color:#c084fc;border:1px solid rgba(139,92,246,0.4);" title="Run on-demand Kronos AI prediction for ' + (r.ticker || '') + '">🔮 Predict</button>');

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

                        // Row styling: Green row if in buy zone
                        const rowStyle = isBz
                            ? 'background:rgba(16,185,129,0.08);border-left:4px solid #10b981;'
                            : 'transition:background 0.15s ease;';
                        const hoverBg = isBz ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.04)';
                        const origBg = isBz ? 'rgba(16,185,129,0.08)' : '';

                        return '<tr style="' + rowStyle + 'cursor:pointer;" onmouseenter="this.style.background=\'' + hoverBg + '\'" onmouseleave="this.style.background=\'' + origBg + '\'" onclick="app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" title="Click row to view 3-month history & set custom range">' +
                            '<td><strong style="color:var(--light);font-size:0.95rem;">' + (r.ticker || '?') + '</strong></td>' +
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
                            '<td><span class="timestamp">' + (r.earnings_date || '—') + '</span></td>' +
                            '<td style="text-align:right;">' +
                                '<div style="display:flex;justify-content:flex-end;gap:0.3rem;align-items:center;">' +
                                '<button class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingRangeModal(\'' + currentMarket.replace(/'/g, "\\'") + '\', \'' + (r.ticker || '').replace(/'/g, "\\'") + '\')" style="padding:0.25rem 0.55rem;font-size:0.75rem;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);">✎ Range</button>' +
                                '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.25rem 0.55rem;font-size:0.75rem;background:rgba(139,92,246,0.2);color:#c084fc;border:1px solid rgba(139,92,246,0.4);" title="Run on-demand Kronos AI prediction">⚡ Kronos</button>' +
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
                        const srSourceCls = isUser ? 'background:rgba(139,92,246,0.25);color:#c084fc;' : 'background:rgba(148,163,184,0.15);color:#94a3b8;';
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
                            '<button class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos(\'' + (r.ticker || '').replace(/'/g, "\\'") + '\', this)" style="padding:0.35rem 0.4rem;font-size:0.72rem;background:rgba(139,92,246,0.22);color:#c084fc;border:1px solid rgba(139,92,246,0.4);">' + (hasKp ? '🔄 Kronos' : '⚡ Kronos AI') + '</button>' +
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
                    setEl('srModalLower', 'value', rng.lower_bound != null ? rng.lower_bound : (autoLower != null ? autoLower : ''));
                    setEl('srModalUpper', 'value', rng.upper_bound != null ? rng.upper_bound : (autoUpper != null ? autoUpper : ''));
                    setEl('srModalCycles', 'value', rng.cycles != null ? rng.cycles : (autoCycles || ''));
                    setEl('srModalAvgDays', 'value', rng.avg_cycle_days != null ? (rng.avg_cycle_days.toFixed(1) + ' days') : (autoAvgDays > 0 ? (autoAvgDays.toFixed(1) + ' days') : '—'));

                    const isUser = rng.source === 'user';
                    const badge = document.getElementById('srModalSourceBadge');
                    if (badge) {
                        badge.textContent = isUser ? 'Custom (User Override)' : 'Auto-detected';
                        badge.style.background = isUser ? 'rgba(139,92,246,0.25)' : 'rgba(59,130,246,0.2)';
                        badge.style.color = isUser ? '#c084fc' : '#60a5fa';
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
                        document.getElementById('srModalLower').value = this._detectedRange.lower;
                    }
                    if (this._detectedRange.upper != null) {
                        document.getElementById('srModalUpper').value = this._detectedRange.upper;
                    }
                    if (this._detectedRange.cycles != null) {
                        document.getElementById('srModalCycles').value = this._detectedRange.cycles;
                    }
                    if (this._detectedRange.avg_days != null) {
                        document.getElementById('srModalAvgDays').value = this._detectedRange.avg_days > 0 ? (this._detectedRange.avg_days.toFixed(1) + ' days') : '—';
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
                        badge.textContent = 'Custom (User Override)';
                        badge.style.background = 'rgba(139,92,246,0.25)';
                        badge.style.color = '#c084fc';
                        // Refresh active tabs
                        if (app.watchlistTab && app.watchlistTab.load) app.watchlistTab.load();
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
                    // Refresh tabs
                    if (app.watchlistTab && app.watchlistTab.load) app.watchlistTab.load();
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
                const btn = event.target;
                const originalText = btn.textContent;
                btn.disabled = true;
                btn.textContent = '⏳ Fetching...';
                const statusEl = document.getElementById('coverageStatus');
                statusEl.textContent = 'Fetching earnings for tickers missing data... this can take a while.';
                const market = document.getElementById('coverageMarket').value || 'ALL';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/earnings/incremental', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({market: market})
                    });
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
                    statusEl.textContent = 'Error: ' + e.message;
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
                    bestEl.innerHTML = '<div class="card" style="border:2px solid ' + bg + ';background:rgba(139,92,246,0.1);">' +
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
                    return '<details class="card" style="border-left:4px solid ' + color + ';' + (isBest ? 'border:2px solid ' + color + ';background:rgba(139,92,246,0.06);' : '') + '" ' + (isBest ? 'open' : '') + '>' +
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
                    '<td><strong>' + r.ticker + '</strong></td>' +
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
                    tbody.innerHTML = '<tr><td colspan="11" style="padding:1rem;text-align:center;color:var(--muted)">No earnings today in the selected range.</td></tr>';
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
                    '<td><strong>' + (r.ticker || '—') + '</strong></td>' +
                    '<td>' + (r.industry || '—') + '</td>' +
                    '<td>' + resultBadge(r.result_class) + '</td>' +
                    '<td class="' + cls(r.reaction_return_pct, true) + '">' + (r.reaction_return_pct !== null && r.reaction_return_pct !== undefined ? r.reaction_return_pct.toFixed(2) + '%' : '—') + '</td>' +
                    '<td>' + fmt(r.day_open) + '</td><td>' + fmt(r.day_high) + '</td><td>' + fmt(r.day_low) + '</td><td>' + fmt(r.day_close) + '</td>' +
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
                                    '<strong style="font-size:1.15rem;color:var(--light);">' + p.ticker + '</strong>' +
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
                        modelsGrid = p.models_breakdown.map(m => {
                            const mDir = (m.direction || 'ERR').toUpperCase();
                            const mColor = mDir === 'BULLISH' ? '#34d399' : mDir === 'BEARISH' ? '#f87171' : '#94a3b8';
                            const drivers = m.key_drivers ? m.key_drivers.map(d => '<li style="margin-bottom:0.25rem;">' + d + '</li>').join('') : '<li>No specific drivers</li>';
                            return '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;padding:0.85rem;">' +
                                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">' +
                                    '<strong style="color:var(--light);font-size:0.9rem;">' + (m.model_name || m.model_id) + '</strong>' +
                                    '<span style="font-size:0.75rem;font-weight:700;color:' + mColor + ';background:' + mColor + '22;padding:0.15rem 0.45rem;border-radius:0.3rem;">' + mDir + ' (' + (m.confidence_pct || 0) + '%)</span>' +
                                '</div>' +
                                '<div style="font-size:0.78rem;color:var(--muted);margin-bottom:0.4rem;">' +
                                    'Target Return: <strong style="color:#60a5fa;">' + (m.target_return_pct ? (m.target_return_pct >= 0 ? '+' : '') + m.target_return_pct + '%' : '—') + '</strong> | Target ₹: ' + (m.target_price || '—') +
                                '</div>' +
                                '<div style="font-size:0.75rem;color:#cbd5e1;margin-bottom:0.4rem;"><strong>Key Drivers:</strong><ul style="padding-left:1.2rem;margin:0.2rem 0 0 0;">' + drivers + '</ul></div>' +
                                (m.primary_risk ? '<div style="font-size:0.75rem;color:#fca5a5;"><strong>Primary Risk:</strong> ' + m.primary_risk + '</div>' : '') +
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
                    '<div class="autocomplete-item" data-i="' + i + '" onclick="app.selectTicker(\'' + t + '\')">' +
                    '<strong>' + t + '</strong> <span style="color:var(--muted);font-size:0.8rem;">' + (t.endsWith('.NS') ? 'NSE' : 'US') + '</span>' +
                    '</div>'
                ).join('');
                dropdown.style.display = 'block';
            } else {
                dropdown.style.display = 'none';
            }
        });

        searchInput.addEventListener('keydown', (e) => {
            const items = dropdown.querySelectorAll('.autocomplete-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                items.forEach((it, i) => it.classList.toggle('selected', i === selectedIndex));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, -1);
                items.forEach((it, i) => it.classList.toggle('selected', i === selectedIndex));
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (selectedIndex >= 0 && items[selectedIndex]) items[selectedIndex].click();
                else if (items.length) items[0].click();
            } else if (e.key === 'Escape') {
                dropdown.style.display = 'none';
            }
        });

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) dropdown.style.display = 'none';
        });

        app.selectTicker = function (ticker) {
            searchInput.value = ticker;
            dropdown.style.display = 'none';
            document.getElementById('tab-results').classList.add('active');
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.querySelector('.tab-btn').classList.add('active');
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

        const THEME_PRESETS = {
            obsidian: {
                '--bg': '#0f172a',
                '--card': 'rgba(30,41,59,0.7)',
                '--accent': '#3b82f6',
                '--green': '#10b981',
                '--red': '#ef4444',
                '--light': '#f8fafc',
                '--muted': '#94a3b8'
            },
            sapphire: {
                '--bg': '#030712',
                '--card': 'rgba(17,24,39,0.85)',
                '--accent': '#06b6d4',
                '--green': '#10b981',
                '--red': '#f43f5e',
                '--light': '#f9fafb',
                '--muted': '#9ca3af'
            },
            cyberpunk: {
                '--bg': '#18181b',
                '--card': 'rgba(39,39,42,0.85)',
                '--accent': '#10b981',
                '--green': '#22c55e',
                '--red': '#f43f5e',
                '--light': '#fafafa',
                '--muted': '#a1a1aa'
            },
            amethyst: {
                '--bg': '#1e102d',
                '--card': 'rgba(46,16,68,0.75)',
                '--accent': '#a855f7',
                '--green': '#34d399',
                '--red': '#fb7185',
                '--light': '#fdf4ff',
                '--muted': '#d8b4fe'
            }
        };

        app._customizer = {
            activeSubTab: 'tabs',
            tabVisibility: {},
            activeTheme: 'obsidian',
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

        app.openCustomizerModal = function() {
            const modal = document.getElementById('controlCenterModal');
            if (!modal) return;
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
            app.switchCustomizerTab(app._customizer.activeSubTab || 'tabs');
        };

        app.closeCustomizerModal = function() {
            const modal = document.getElementById('controlCenterModal');
            if (modal) modal.style.display = 'none';
            document.body.style.overflow = '';
        };

        app.switchCustomizerTab = function(subTab) {
            app._customizer.activeSubTab = subTab;
            
            // Toggle nav buttons
            ['tabs', 'themes', 'env'].forEach(t => {
                const navBtn = document.getElementById('ccNav' + t.charAt(0).toUpperCase() + t.slice(1));
                const sec = document.getElementById('ccSection' + t.charAt(0).toUpperCase() + t.slice(1));
                if (navBtn) navBtn.classList.toggle('active', t === subTab);
                if (sec) sec.style.display = (t === subTab) ? 'block' : 'none';
            });

            if (subTab === 'tabs') {
                app.renderCustomizerTabsGrid();
            } else if (subTab === 'themes') {
                app.syncThemePickers();
            } else if (subTab === 'env') {
                app.loadEnvVars();
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
                document.querySelectorAll('.tab-btn').forEach(btn => {
                    const onclick = btn.getAttribute('onclick') || '';
                    if (onclick.includes("'" + tab.key + "'") || onclick.includes('"' + tab.key + '"')) {
                        btn.style.display = isVisible ? 'inline-block' : 'none';
                    }
                });

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

        app.resetDefaultColors = function() {
            app.applyPresetTheme('obsidian', true);
        };

        app.syncThemePickers = function() {
            const computed = getComputedStyle(document.documentElement);
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

        // Initialize & export to window
        window.app = app;
        app.init();

