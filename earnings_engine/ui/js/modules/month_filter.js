// =========================================================================
// month_filter — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
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
                if (!el) return;
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
                        '<td><div style="display:flex;flex-direction:column;gap:0.3rem;">' + this.renderConsensusBadge(r.ticker, this.currentMarket) + (typeof this.renderTradingAgentsBadge === 'function' ? this.renderTradingAgentsBadge(r.ticker, this.currentMarket) : '') + '</div></td>' +
                        '<td><span class="signal-badge ' + (mom > 3 ? 'price-positive' : mom < -3 ? 'price-negative' : '') + '">' + signal + '</span></td>' +
                        '</tr>';
                }).join('');
            },

            sortResults(key) {
                if (this.sortKey === key) this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
                else { this.sortKey = key; this.sortDir = 'asc'; }
                this.renderResultsTable();
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

    });
})(); // end month_filter IIFE
