// =========================================================================
// watchlist_modal — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
// =========================================================================
        // ⭐ Universal Add to Watchlist & Playlist Selector Modal Manager
        // =========================================================================
        app.activeAddToWatchlistTicker = null;
        app._allCustomPlaylists = [];

        app.openAddToWatchlistModal = async function(ticker, price) {
            if (!ticker) return;
            app.activeAddToWatchlistTicker = ticker.trim().toUpperCase();
            const modal = document.getElementById('addToWatchlistModal');
            const tickerEl = document.getElementById('wlModalTicker');
            const priceEl = document.getElementById('wlModalPrice');
            const listContainer = document.getElementById('wlModalPlaylistsList');
            const newNameInput = document.getElementById('wlModalNewName');
            const statusMsg = document.getElementById('wlModalStatusMsg');

            if (!modal) return;
            if (tickerEl) tickerEl.textContent = app.activeAddToWatchlistTicker;
            if (priceEl) priceEl.textContent = price ? '₹' + Number(price).toFixed(2) : '';
            if (newNameInput) newNameInput.value = '';
            if (statusMsg) statusMsg.textContent = '';

            modal.style.display = 'block';

            if (listContainer) {
                listContainer.innerHTML = '<div style="padding:1rem;text-align:center;color:#64748b;font-size:0.75rem;"><div class="spinner" style="display:inline-block;margin-right:0.35rem;"></div> Fetching your playlists...</div>';
            }

            try {
                // Fetch fresh lists from API
                const res = await fetch(API_BASE + '/api/v1/watchlist/all');
                if (res.ok) {
                    const data = await res.json();
                    app._allCustomPlaylists = data.custom_lists || [];
                } else {
                    const resNames = await fetch(API_BASE + '/api/v1/watchlist/names');
                    if (resNames.ok) {
                        const dataN = await resNames.json();
                        app._allCustomPlaylists = (dataN.watchlists || []).map(w => ({ name: w.name, tickers: [] }));
                    }
                }
            } catch (e) {
                console.warn('[WATCHLIST-MODAL] Failed loading fresh playlists:', e);
            }

            if (!app._allCustomPlaylists.length) {
                app._allCustomPlaylists = [
                    { name: 'my_watchlist', tickers: [] },
                    { name: 'swing', tickers: [] }
                ];
            }

            app.renderPlaylistModalItems();
        };

        app.renderPlaylistModalItems = function() {
            const listContainer = document.getElementById('wlModalPlaylistsList');
            if (!listContainer) return;

            const ticker = app.activeAddToWatchlistTicker;
            const lists = app._allCustomPlaylists || [];

            if (!lists.length) {
                listContainer.innerHTML = '<div style="padding:0.75rem;text-align:center;color:#94a3b8;font-size:0.75rem;">No playlists created yet. Create one below!</div>';
                return;
            }

            listContainer.innerHTML = lists.map(w => {
                const isMember = (w.tickers || []).includes(ticker);
                const count = (w.tickers || []).length;
                const displayName = w.name === 'my_watchlist' ? '⭐ my_watchlist (Default)' : (w.name === 'swing' ? '📈 swing (Setups)' : `📁 ${w.name}`);
                const bg = isMember ? 'rgba(59,130,246,0.12)' : 'rgba(255,255,255,0.02)';
                const border = isMember ? 'rgba(59,130,246,0.4)' : 'rgba(255,255,255,0.06)';
                const badgeColor = isMember ? '#34d399' : '#94a3b8';
                const badgeText = isMember ? '✓ In Playlist' : 'Click to Add';

                return `
                    <div style="display:flex;align-items:center;justify-content:space-between;padding:0.5rem 0.75rem;background:${bg};border:1px solid ${border};border-radius:8px;cursor:pointer;transition:all 0.15s ease;" onclick="app.togglePlaylistMembership('${w.name.replace(/'/g, "\\'")}', this)" onmouseover="this.style.borderColor='rgba(59,130,246,0.6)'" onmouseout="this.style.borderColor='${border}'">
                        <div style="display:flex;align-items:center;gap:0.6rem;">
                            <input type="checkbox" ${isMember ? 'checked' : ''} style="accent-color:#38bdf8;cursor:pointer;width:15px;height:15px;" onclick="event.stopPropagation(); app.togglePlaylistMembership('${w.name.replace(/'/g, "\\'")}', this.parentElement.parentElement);">
                            <div>
                                <div style="font-size:0.82rem;font-weight:700;color:#f8fafc;">${displayName}</div>
                                <div style="font-size:0.68rem;color:#94a3b8;font-family:var(--font-mono);">${count} stock${count === 1 ? '' : 's'}</div>
                            </div>
                        </div>
                        <span class="signal-badge" style="background:${isMember ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.05)'};color:${badgeColor};font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;">
                            ${badgeText}
                        </span>
                    </div>
                `;
            }).join('');
        };

        app.togglePlaylistMembership = async function(playlistName, itemRowEl) {
            if (!app.activeAddToWatchlistTicker || !playlistName) return;
            const ticker = app.activeAddToWatchlistTicker;
            const statusMsg = document.getElementById('wlModalStatusMsg');

            // Find current status
            const listObj = (app._allCustomPlaylists || []).find(w => w.name === playlistName);
            const isCurrentlyMember = listObj ? (listObj.tickers || []).includes(ticker) : false;
            const endpoint = isCurrentlyMember ? '/api/v1/watchlist/remove' : '/api/v1/watchlist/add';

            if (statusMsg) {
                statusMsg.style.color = '#38bdf8';
                statusMsg.textContent = isCurrentlyMember ? `Removing from ${playlistName}...` : `Adding to ${playlistName}...`;
            }

            try {
                const res = await fetch(API_BASE + endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        ticker: ticker,
                        name: playlistName
                    })
                });
                const data = await res.json();
                if (data.success) {
                    // Update local state array
                    if (listObj) {
                        if (isCurrentlyMember) {
                            listObj.tickers = (listObj.tickers || []).filter(t => t !== ticker);
                        } else {
                            if (!listObj.tickers) listObj.tickers = [];
                            listObj.tickers.push(ticker);
                        }
                    }
                    app.renderPlaylistModalItems();

                    if (statusMsg) {
                        statusMsg.style.color = '#34d399';
                        statusMsg.textContent = isCurrentlyMember ? `✓ Removed from ${playlistName}` : `✓ Added to ${playlistName}!`;
                        setTimeout(() => { if (statusMsg) statusMsg.textContent = ''; }, 2500);
                    }

                    if (typeof app.showToast === 'function') {
                        app.showToast(isCurrentlyMember ? `Removed ${ticker} from ${playlistName}` : `Added ${ticker} to ${playlistName}!`, 'success');
                    }

                    if (app.watchlistTab && typeof app.watchlistTab.load === 'function') {
                        app.watchlistTab.load(true);
                    }
                } else {
                    if (statusMsg) {
                        statusMsg.style.color = '#f87171';
                        statusMsg.textContent = data.error || 'Operation failed';
                    }
                    alert(data.error || 'Failed to update playlist');
                }
            } catch (e) {
                console.error('[WATCHLIST-TOGGLE] error:', e);
                if (statusMsg) {
                    statusMsg.style.color = '#f87171';
                    statusMsg.textContent = 'Network error updating playlist';
                }
            }
        };

        app.closeAddToWatchlistModal = function() {
            const modal = document.getElementById('addToWatchlistModal');
            if (modal) modal.style.display = 'none';
            app.activeAddToWatchlistTicker = null;
        };

        app.applyWatchlistSelections = function() {
            app.closeAddToWatchlistModal();
        };

        app.createAndAddWatchlist = async function() {
            if (!app.activeAddToWatchlistTicker) return;
            const input = document.getElementById('wlModalNewName');
            const name = (input ? input.value : '').trim();
            const statusMsg = document.getElementById('wlModalStatusMsg');

            if (!name) {
                if (statusMsg) {
                    statusMsg.style.color = '#fbbf24';
                    statusMsg.textContent = 'Please enter a playlist name';
                }
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
                    if (input) input.value = '';
                    // Add to local playlist list
                    app._allCustomPlaylists.push({
                        name: name,
                        tickers: [app.activeAddToWatchlistTicker]
                    });
                    app.renderPlaylistModalItems();

                    if (statusMsg) {
                        statusMsg.style.color = '#34d399';
                        statusMsg.textContent = `✓ Created "${name}" with ${app.activeAddToWatchlistTicker}!`;
                        setTimeout(() => { if (statusMsg) statusMsg.textContent = ''; }, 2500);
                    }

                    if (typeof app.showToast === 'function') {
                        app.showToast(`Created playlist "${name}"!`, 'success');
                    }
                    if (app.watchlistTab && typeof app.watchlistTab.load === 'function') {
                        app.watchlistTab.load(true);
                    }
                } else {
                    if (statusMsg) {
                        statusMsg.style.color = '#f87171';
                        statusMsg.textContent = data.error || 'Failed to create playlist';
                    }
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

})(); // end watchlist_modal IIFE
