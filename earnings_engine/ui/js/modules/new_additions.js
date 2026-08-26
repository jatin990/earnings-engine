// =========================================================================
// 🆕 Recent Market Additions & IPOs Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const newAdditionsModule = {
        _recentAdditionsData: [],
        _newAdditionsLoaded: false,

        async loadRecentAdditions() {
            const daysSelect = document.getElementById('newAdditionsDaysSelect');
            const days = daysSelect ? daysSelect.value : '180';
            const tbody = document.getElementById('newAdditionsTableBody');

            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="padding:2.5rem;text-align:center;color:#60a5fa;">
                            <span class="spinner"></span> Fetching official NSE newly listed equities...
                        </td>
                    </tr>
                `;
            }

            try {
                const res = await fetch(API_BASE + `/api/v1/market/recent-additions?days=${encodeURIComponent(days)}&limit=200`);
                if (res.ok) {
                    const data = await res.json();
                    this._recentAdditionsData = data.items || [];
                    this.updateNewAdditionsMetrics(this._recentAdditionsData);
                    this.renderRecentAdditionsTable(this._recentAdditionsData);
                } else {
                    if (tbody) {
                        tbody.innerHTML = `<tr><td colspan="8" style="padding:2rem;text-align:center;color:#f87171;">Failed fetching recent listings from server.</td></tr>`;
                    }
                }
            } catch (e) {
                console.error('[NEW-ADDITIONS] Error loading listings:', e);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="8" style="padding:2rem;text-align:center;color:#f87171;">Error loading data: ${e.message}</td></tr>`;
                }
            }
        },

        updateNewAdditionsMetrics(items) {
            const totalEl = document.getElementById('metricTotalNewListings');
            const firstEl = document.getElementById('metricFirstResultCount');
            const secondEl = document.getElementById('metricSecondResultCount');
            const wlEl = document.getElementById('metricInWatchlistCount');
            const badgeEl = document.getElementById('newAdditionsCountBadge');

            if (!items) items = [];
            const firstCount = items.filter(i => i.result_sequence_number === 1).length;
            const secondCount = items.filter(i => i.result_sequence_number === 2).length;
            const inWlCount = items.filter(i => i.in_watchlist).length;

            if (totalEl) totalEl.textContent = items.length;
            if (firstEl) firstEl.textContent = firstCount;
            if (secondEl) secondEl.textContent = secondCount;
            if (wlEl) wlEl.textContent = inWlCount;
            if (badgeEl) badgeEl.textContent = `${items.length} NSE LISTINGS`;
        },

        filterRecentAdditionsTable() {
            const seriesSelect = document.getElementById('newAdditionsSeriesSelect');
            const mode = seriesSelect ? seriesSelect.value : 'ALL';

            if (!this._recentAdditionsData || !this._recentAdditionsData.length) {
                return;
            }

            let filtered = this._recentAdditionsData;
            if (mode === 'MAIN') {
                filtered = filtered.filter(i => !i.is_sme);
            } else if (mode === 'SME') {
                filtered = filtered.filter(i => i.is_sme);
            }

            this.renderRecentAdditionsTable(filtered);
        },

        renderRecentAdditionsTable(items) {
            const tbody = document.getElementById('newAdditionsTableBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = `<tr><td colspan="8" style="padding:2rem;text-align:center;color:#64748b;">No recent listings found for selected lookback window.</td></tr>`;
                return;
            }

            tbody.innerHTML = items.map(it => {
                const isDebut = it.result_sequence_number === 1;
                const isSecond = it.result_sequence_number === 2;
                const badgeBg = isDebut ? 'rgba(245,158,11,0.15)' : isSecond ? 'rgba(16,185,129,0.15)' : 'rgba(56,189,248,0.15)';
                const badgeCol = isDebut ? '#fbbf24' : isSecond ? '#34d399' : '#38bdf8';
                const badgeBorder = isDebut ? 'rgba(245,158,11,0.3)' : isSecond ? 'rgba(16,185,129,0.3)' : 'rgba(56,189,248,0.3)';

                const wlButton = it.in_watchlist
                    ? `<span style="color:#38bdf8;font-size:0.7rem;font-family:var(--font-mono);font-weight:700;">⭐ In Watchlist</span>`
                    : `<button type="button" onclick="app.addRecentAdditionToWatchlist('${it.ticker}', this)" class="btn btn-secondary btn-sm" style="font-size:0.68rem;padding:0.2rem 0.5rem;">+ Add Watchlist</button>`;

                const seriesBadge = it.is_sme
                    ? `<span style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);border-radius:4px;padding:0.1rem 0.35rem;font-size:0.65rem;font-weight:700;">SME (${it.series})</span>`
                    : `<span style="background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:4px;padding:0.1rem 0.35rem;font-size:0.65rem;font-weight:700;">EQ</span>`;

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;">
                            <a href="/stock/${encodeURIComponent(it.ticker)}" target="_blank" style="color:#38bdf8;text-decoration:none;">${it.ticker}</a>
                        </td>
                        <td style="padding:0.65rem 0.8rem;color:#f8fafc;font-weight:600;">${it.company_name}</td>
                        <td style="padding:0.65rem 0.8rem;">${seriesBadge}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#cbd5e1;">${it.listing_date}</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#94a3b8;">
                            <strong style="color:#f8fafc;">${it.days_on_market}</strong> days ago
                        </td>
                        <td style="padding:0.65rem 0.8rem;">
                            <span style="background:${badgeBg};color:${badgeCol};border:1px solid ${badgeBorder};border-radius:4px;padding:0.15rem 0.45rem;font-size:0.68rem;font-weight:700;display:inline-flex;align-items:center;gap:0.25rem;">
                                ${it.result_sequence_label}
                            </span>
                        </td>
                        <td style="padding:0.65rem 0.8rem;">${wlButton}</td>
                        <td style="padding:0.65rem 0.8rem;text-align:center;">
                            <a href="/stock/${encodeURIComponent(it.ticker)}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;text-decoration:none;display:inline-block;">
                                ⚡ Intel Note
                            </a>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async addRecentAdditionToWatchlist(ticker, btnElement) {
            if (!ticker) return;
            if (btnElement) {
                btnElement.disabled = true;
                btnElement.textContent = 'Adding...';
            }

            try {
                const res = await fetch(API_BASE + `/api/v1/market/recent-additions/sync-watchlist?ticker=${encodeURIComponent(ticker)}&watchlist=my_watchlist`, {
                    method: 'POST'
                });
                if (res.ok) {
                    if (btnElement) {
                        btnElement.outerHTML = `<span style="color:#38bdf8;font-size:0.7rem;font-family:var(--font-mono);font-weight:700;">⭐ Added!</span>`;
                    }
                    // Update internal state
                    const found = this._recentAdditionsData.find(i => i.ticker === ticker);
                    if (found) found.in_watchlist = true;
                    this.updateNewAdditionsMetrics(this._recentAdditionsData);
                } else {
                    alert('Failed adding ' + ticker + ' to watchlist.');
                    if (btnElement) {
                        btnElement.disabled = false;
                        btnElement.textContent = '+ Add Watchlist';
                    }
                }
            } catch (e) {
                console.error('Error adding to watchlist:', e);
                alert('Error: ' + e.message);
                if (btnElement) {
                    btnElement.disabled = false;
                    btnElement.textContent = '+ Add Watchlist';
                }
            }
        }
    };

    // Export module
    window.NewAdditionsModule = newAdditionsModule;
    if (window.app) {
        Object.assign(window.app, newAdditionsModule);
    }
})();
