// =========================================================================
// ⭐ Global Watchlist Slide-Over Drawer ([Shift + W] Hotkey)
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app.watchlistDrawer = {
        isOpen: false,
        activeWatchlist: '',
        quotes: [],
        names: [],
    };

    app.toggleWatchlistDrawer = function() {
        if (app.watchlistDrawer.isOpen) {
            app.closeWatchlistDrawer();
        } else {
            app.openWatchlistDrawer();
        }
    };

    app.openWatchlistDrawer = function() {
        const drawer = document.getElementById('globalWatchlistDrawer');
        const backdrop = document.getElementById('globalWatchlistBackdrop');
        if (!drawer) return;

        app.watchlistDrawer.isOpen = true;
        drawer.style.right = '0';
        if (backdrop) backdrop.style.display = 'block';

        app.loadDrawerWatchlists();
    };

    app.closeWatchlistDrawer = function() {
        const drawer = document.getElementById('globalWatchlistDrawer');
        const backdrop = document.getElementById('globalWatchlistBackdrop');
        if (!drawer) return;

        app.watchlistDrawer.isOpen = false;
        drawer.style.right = '-460px';
        if (backdrop) backdrop.style.display = 'none';
    };

    app.loadDrawerWatchlists = async function() {
        try {
            const resp = await fetch(`${API_BASE}/api/v1/watchlist/names`);
            if (resp.ok) {
                const data = await resp.json();
                const names = Array.isArray(data) ? data : (data.watchlists || data.names || []);
                app.watchlistDrawer.names = names;

                const select = document.getElementById('drawerWatchlistSelect');
                if (select) {
                    select.innerHTML = names.map(n => `<option value="${n}" ${n === app.watchlistDrawer.activeWatchlist ? 'selected' : ''}>${n}</option>`).join('');
                    if (!app.watchlistDrawer.activeWatchlist && names.length > 0) {
                        app.watchlistDrawer.activeWatchlist = names[0];
                    }
                }
            }
        } catch (e) {
            console.debug("Could not fetch watchlist names for drawer", e);
        }

        app.refreshDrawerQuotes();
    };

    app.onDrawerWatchlistSelect = function(name) {
        app.watchlistDrawer.activeWatchlist = name;
        app.refreshDrawerQuotes();
    };

    app.refreshDrawerQuotes = async function() {
        const container = document.getElementById('drawerWatchlistItems');
        const totalCountEl = document.getElementById('drawerTotalCount');
        const topCountEl = document.getElementById('topbarWlCount');
        if (!container) return;

        const wl = app.watchlistDrawer.activeWatchlist || 'my_watchlist';
        container.innerHTML = `<div style="text-align:center;padding:2rem;color:#64748b;font-size:0.78rem;">Loading live quotes for ${wl}...</div>`;

        try {
            const resp = await fetch(`${API_BASE}/api/v1/watchlist/quotes?watchlist=${encodeURIComponent(wl)}&live=true`);
            if (!resp.ok) throw new Error("Quotes API returned " + resp.status);
            const quotes = await resp.json();
            const list = Array.isArray(quotes) ? quotes : (quotes.quotes || []);
            app.watchlistDrawer.quotes = list;

            if (totalCountEl) totalCountEl.textContent = list.length;
            if (topCountEl) topCountEl.textContent = list.length;

            if (list.length === 0) {
                container.innerHTML = `
                    <div style="text-align:center;padding:3rem 1rem;color:#64748b;font-size:0.8rem;">
                        <div style="font-size:1.8rem;margin-bottom:0.5rem;">⭐</div>
                        <strong style="color:#e2e8f0;display:block;margin-bottom:0.25rem;">Watchlist is Empty</strong>
                        Add your first symbol using the search bar above.
                    </div>
                `;
                return;
            }

            container.innerHTML = list.map(item => {
                const ticker = item.ticker || item.symbol || '';
                const name = item.stock_name || item.name || ticker;
                const price = typeof item.price === 'number' ? item.price : (item.close || 0);
                const chg = typeof item.change_pct === 'number' ? item.change_pct : (item.return_pct || 0);
                const ret7d = item.return_7d || 0;
                const volumeSurge = item.volume_ratio || item.volume_surge || 1.0;
                const low52 = item.low_52w || item.year_low || price * 0.7;
                const high52 = item.high_52w || item.year_high || price * 1.3;

                // 52W range calculation
                const rangeSpan = high52 - low52;
                const rangePct = rangeSpan > 0 ? Math.min(100, Math.max(0, ((price - low52) / rangeSpan) * 100)) : 50;

                const sym = ticker.endsWith('.NS') || ticker.endsWith('.BO') ? '₹' : '$';
                const isPos = chg >= 0;

                return `
                    <div class="drawer-quote-row" style="background:#0d0d12;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.6rem 0.75rem;display:flex;flex-direction:column;gap:0.4rem;transition:border-color 0.15s ease;">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                            <div>
                                <div style="display:flex;align-items:center;gap:0.45rem;">
                                    <strong style="color:#ffffff;font-size:0.88rem;font-family:var(--font-mono);">${ticker}</strong>
                                    ${volumeSurge >= 1.8 ? `<span class="signal-badge" style="font-size:0.62rem;background:rgba(234,179,8,0.15);color:#facc15;">🔥 ${volumeSurge.toFixed(1)}x Vol</span>` : ''}
                                </div>
                                <div style="font-size:0.7rem;color:#94a3b8;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-size:0.9rem;font-weight:700;color:#ffffff;font-family:var(--font-mono);">${sym}${price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                                <div style="font-size:0.72rem;font-weight:700;color:${isPos ? '#34d399' : '#f87171'};font-family:var(--font-mono);">${isPos ? '+' : ''}${chg.toFixed(2)}%</div>
                            </div>
                        </div>

                        <!-- 52W Range Mini Bar -->
                        <div style="display:flex;align-items:center;gap:0.4rem;font-size:0.65rem;color:#64748b;">
                            <span>52L: ${sym}${low52.toFixed(0)}</span>
                            <div style="flex:1;height:4px;background:rgba(255,255,255,0.08);border-radius:2px;position:relative;overflow:hidden;">
                                <div style="position:absolute;left:0;top:0;bottom:0;width:${rangePct}%;background:${isPos ? '#34d399' : '#38bdf8'};border-radius:2px;"></div>
                            </div>
                            <span>52H: ${sym}${high52.toFixed(0)}</span>
                        </div>

                        <!-- Action Buttons -->
                        <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(255,255,255,0.04);padding-top:0.35rem;margin-top:0.15rem;">
                            <div style="display:flex;gap:0.35rem;">
                                <button type="button" onclick="app.openMultiChartModal('${ticker}')" class="btn-micro" style="font-size:0.68rem;padding:0.15rem 0.45rem;background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.25);border-radius:4px;cursor:pointer;">📈 Chart</button>
                                <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" class="btn-micro" style="font-size:0.68rem;padding:0.15rem 0.45rem;background:rgba(255,255,255,0.05);color:#cbd5e1;border:1px solid rgba(255,255,255,0.1);border-radius:4px;text-decoration:none;">🔍 Detail</a>
                            </div>
                            <button type="button" onclick="app.removeTickerFromDrawer('${ticker}')" class="btn-micro" style="font-size:0.68rem;padding:0.15rem 0.35rem;background:transparent;color:#94a3b8;border:none;cursor:pointer;" title="Remove from watchlist">✕ Remove</button>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (err) {
            console.error("Error refreshing drawer quotes:", err);
            container.innerHTML = `<div style="text-align:center;padding:2rem;color:#f87171;font-size:0.78rem;">Failed to load watchlist quotes.</div>`;
        }
    };

    app.addTickerFromDrawer = async function() {
        const input = document.getElementById('drawerAddTickerInput');
        if (!input || !input.value.trim()) return;

        const ticker = input.value.trim().toUpperCase();
        const wl = app.watchlistDrawer.activeWatchlist || 'my_watchlist';

        try {
            const resp = await fetch(`${API_BASE}/api/v1/watchlist/add`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ watchlist: wl, ticker: ticker }),
            });
            if (resp.ok) {
                input.value = '';
                app.refreshDrawerQuotes();
            }
        } catch (e) {
            console.error("Error adding ticker from drawer:", e);
        }
    };

    app.removeTickerFromDrawer = async function(ticker) {
        if (!ticker) return;
        const wl = app.watchlistDrawer.activeWatchlist || 'my_watchlist';

        try {
            const resp = await fetch(`${API_BASE}/api/v1/watchlist/remove`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ watchlist: wl, ticker: ticker }),
            });
            if (resp.ok) {
                app.refreshDrawerQuotes();
            }
        } catch (e) {
            console.error("Error removing ticker from drawer:", e);
        }
    };

    // Global Keydown Shortcut [Shift + W]
    document.addEventListener('keydown', function(e) {
        // Ignore if user is currently typing in an input or textarea
        const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
        if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
            return;
        }

        if (e.shiftKey && (e.key === 'W' || e.key === 'w')) {
            e.preventDefault();
            app.toggleWatchlistDrawer();
        } else if (e.key === 'Escape' && app.watchlistDrawer.isOpen) {
            app.closeWatchlistDrawer();
        }
    });

    // Initial drawer count hydration on page load
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(app.loadDrawerWatchlists, 1000);
    });

})();
