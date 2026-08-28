// =========================================================================
// swing_range — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
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
                    const priceAsOf = data.price_as_of || data.asof_date || (new Date()).toLocaleDateString();
                    setEl('srModalPriceAsOf', 'textContent', priceAsOf ? ('🕒 As of: ' + priceAsOf) : '');

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
                        t + '<button type="button" onclick="app.removeFromWatchlist(\'' + t + '\')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:1rem;" title="Remove">&times;</button></span>'
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
                const ticker = (input ? input.value : '').trim().toUpperCase();
                if (!ticker) return;
                input.value = '';
                const dd = document.getElementById('watchlistAddDropdown');
                if (dd) dd.style.display = 'none';
                // Always prompt user to choose among all playlists/watchlists
                if (typeof app.openAddToWatchlistModal === 'function') {
                    app.openAddToWatchlistModal(ticker);
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
                                '<td><button type="button" onclick="app.generateForTicker(\'' + ticker + '\')" class="btn btn-primary btn-sm">Regenerate</button></td>' +
                                '</tr>';
                        } else {
                            return '<tr>' +
                                '<td><strong>' + ticker + '</strong></td>' +
                                '<td class="timestamp">No prediction</td>' +
                                '<td class="timestamp">—</td>' +
                                '<td class="timestamp">—</td>' +
                                '<td><button type="button" onclick="app.generateForTicker(\'' + ticker + '\')" class="btn btn-primary btn-sm">Generate</button></td>' +
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

        // [] → extracted to modules/coverage.js
        // [] → extracted to modules/industries.js
        // [] → extracted to modules/buy_dip.js
        // [] → extracted to modules/patterns.js
    });
})(); // end swing_range IIFE
