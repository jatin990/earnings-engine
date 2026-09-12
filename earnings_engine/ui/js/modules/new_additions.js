// =========================================================================
// 🆕 Recent Market Additions & IPOs Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const newAdditionsModule = {
        _recentAdditionsData: [],
        _currentSeriesFilter: 'MAIN', // 'MAIN', 'SME', 'ALL'
        _selectedTicker: null,
        _ipoDetailCache: new Map(),
        _newAdditionsLoaded: false,

        /**
         * Change segment filter (MAIN, SME, ALL) and re-render table.
         * @param {string} series - 'MAIN', 'SME', or 'ALL'
         */
        setNewAdditionsSeriesFilter(series) {
            this._currentSeriesFilter = series || 'MAIN';

            // Update button styles
            const btnMain = document.getElementById('btnNewAdditionsSegment-main');
            const btnSme = document.getElementById('btnNewAdditionsSegment-sme');
            const btnAll = document.getElementById('btnNewAdditionsSegment-all');

            const activeStyle = 'background: #18181b; color: #ffffff; border: 1px solid rgba(255,255,255,0.3); font-weight: 700; padding: 0.35rem 0.85rem; font-size: 0.76rem;';
            const inactiveStyle = 'background: transparent; color: #94a3b8; border: 1px solid transparent; font-weight: 500; padding: 0.35rem 0.85rem; font-size: 0.76rem;';

            if (btnMain) btnMain.style.cssText = (this._currentSeriesFilter === 'MAIN') ? activeStyle : inactiveStyle;
            if (btnSme) btnSme.style.cssText = (this._currentSeriesFilter === 'SME') ? activeStyle : inactiveStyle;
            if (btnAll) btnAll.style.cssText = (this._currentSeriesFilter === 'ALL') ? activeStyle : inactiveStyle;

            // Filter data and re-render
            this.filterRecentAdditionsTable();
        },

        /**
         * Fetch recent listings from the backend API.
         */
        async loadRecentAdditions() {
            const daysSelect = document.getElementById('newAdditionsDaysSelect');
            const days = daysSelect ? daysSelect.value : '180';
            const tbody = document.getElementById('newAdditionsTableBody');

            // Restore split layout preference
            this.restoreNewAdditionsSplitLayout();

            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="padding:2.5rem;text-align:center;color:#60a5fa;">
                            <span class="spinner" style="display:inline-block;animation:spin 1s linear infinite;margin-right:0.4rem;">⏳</span> Fetching official NSE newly listed equities...
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
                    this.filterRecentAdditionsTable();

                    // Automatically inspect the top stock of the current filter if available
                    const filtered = this.getFilteredItems();
                    if (filtered && filtered.length > 0) {
                        const targetTicker = (this._selectedTicker && filtered.some(i => i.ticker === this._selectedTicker))
                            ? this._selectedTicker
                            : filtered[0].ticker;
                        this.inspectNewAdditionStock(targetTicker, false);
                    }
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

        /**
         * Get items based on current series filter.
         */
        getFilteredItems() {
            if (!this._recentAdditionsData || !this._recentAdditionsData.length) {
                return [];
            }
            if (this._currentSeriesFilter === 'MAIN') {
                return this._recentAdditionsData.filter(i => !i.is_sme);
            } else if (this._currentSeriesFilter === 'SME') {
                return this._recentAdditionsData.filter(i => i.is_sme);
            }
            return this._recentAdditionsData;
        },

        /**
         * Update top KPI summary cards with current data counts.
         */
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

        /**
         * Filter data according to active series and trigger table render.
         */
        filterRecentAdditionsTable() {
            const filtered = this.getFilteredItems();
            this.renderRecentAdditionsTable(filtered);

            // Update status text in footer
            const statusEl = document.getElementById('newAdditionsCountStatus');
            if (statusEl) {
                const total = this._recentAdditionsData ? this._recentAdditionsData.length : 0;
                const filterLabel = this._currentSeriesFilter === 'MAIN' ? 'Mainboard' : (this._currentSeriesFilter === 'SME' ? 'SME' : 'All');
                statusEl.textContent = `Showing ${filtered.length} of ${total} listings (${filterLabel})`;
            }
        },

        /**
         * Render listings in the left table view.
         * @param {Array} items
         */
        renderRecentAdditionsTable(items) {
            const tbody = document.getElementById('newAdditionsTableBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = `<tr><td colspan="8" style="padding:2.5rem;text-align:center;color:#64748b;">No recent listings found for selected filter & lookback window.</td></tr>`;
                return;
            }

            tbody.innerHTML = items.map(it => {
                const isSelected = this._selectedTicker && (this._selectedTicker === it.ticker || this._selectedTicker.split('.')[0] === it.raw_symbol);
                const rowBg = isSelected ? 'rgba(59,130,246,0.12)' : 'transparent';
                const rowBorder = isSelected ? 'rgba(59,130,246,0.35)' : 'rgba(255,255,255,0.06)';

                // Result badge styling
                const isDebut = it.result_sequence_number === 1;
                const isSecond = it.result_sequence_number === 2;
                const badgeBg = isDebut ? 'rgba(245,158,11,0.15)' : isSecond ? 'rgba(16,185,129,0.15)' : 'rgba(56,189,248,0.15)';
                const badgeCol = isDebut ? '#fbbf24' : isSecond ? '#34d399' : '#38bdf8';
                const badgeBorder = isDebut ? 'rgba(245,158,11,0.3)' : isSecond ? 'rgba(16,185,129,0.3)' : 'rgba(56,189,248,0.3)';

                // Series badge
                const seriesBadge = it.is_sme
                    ? `<span style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);border-radius:4px;padding:0.1rem 0.35rem;font-size:0.65rem;font-weight:700;">SME (${it.series || 'SM'})</span>`
                    : `<span style="background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);border-radius:4px;padding:0.1rem 0.35rem;font-size:0.65rem;font-weight:700;">EQ</span>`;

                // Price and debut return
                const cmpStr = (it.cmp !== null && it.cmp !== undefined) ? `₹${Number(it.cmp).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2})}` : '—';
                const debutRet = it.return_since_listing_pct !== null && it.return_since_listing_pct !== undefined ? it.return_since_listing_pct : null;
                let debutHtml = '';
                if (debutRet !== null) {
                    const retColor = debutRet >= 0 ? '#34d399' : '#f87171';
                    const retPrefix = debutRet > 0 ? '+' : '';
                    debutHtml = `<span style="color:${retColor};font-weight:700;font-size:0.68rem;margin-left:0.25rem;">(${retPrefix}${debutRet.toFixed(1)}%)</span>`;
                }

                // 7D and 30D returns
                const ret7d = it.return_7d_pct;
                const ret30d = it.return_30d_pct;
                const ret7dStr = (ret7d !== null && ret7d !== undefined)
                    ? `<span style="color:${ret7d >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${ret7d > 0 ? '+' : ''}${ret7d.toFixed(1)}%</span>`
                    : '<span style="color:#64748b;">—</span>';
                const ret30dStr = (ret30d !== null && ret30d !== undefined)
                    ? `<span style="color:${ret30d >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${ret30d > 0 ? '+' : ''}${ret30d.toFixed(1)}%</span>`
                    : '<span style="color:#64748b;">—</span>';

                // ATH Distance
                const athDist = it.ath_distance_pct;
                let athDistHtml = '<span style="color:#64748b;">—</span>';
                if (athDist !== null && athDist !== undefined) {
                    const athColor = athDist >= -3 ? '#34d399' : (athDist >= -15 ? '#fbbf24' : '#94a3b8');
                    const athPrefix = athDist > 0 ? '+' : '';
                    athDistHtml = `<span style="color:${athColor};font-weight:700;font-family:var(--font-mono);">${athPrefix}${athDist.toFixed(1)}%</span>`;
                }

                // Watchlist button
                const wlButton = it.in_watchlist
                    ? `<span style="color:#38bdf8;font-size:0.7rem;font-family:var(--font-mono);font-weight:700;">⭐ In WL</span>`
                    : `<button type="button" onclick="event.stopPropagation(); app.addRecentAdditionToWatchlist('${it.ticker}', this)" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.18rem 0.45rem;border-radius:4px;">+ Watchlist</button>`;

                return `
                    <tr id="row-new-addition-${it.ticker.replace(/[^a-zA-Z0-9]/g, '')}"
                        onclick="app.inspectNewAdditionStock('${it.ticker}')"
                        style="border-bottom:1px solid ${rowBorder};background:${rowBg};cursor:pointer;transition:background 0.15s;"
                        onmouseover="if(app._selectedTicker !== '${it.ticker}') this.style.background='rgba(255,255,255,0.03)'"
                        onmouseout="if(app._selectedTicker !== '${it.ticker}') this.style.background='${rowBg}'">
                        <td style="padding:0.55rem 0.6rem;font-family:var(--font-mono);font-weight:700;white-space:nowrap;">
                            <div style="display:flex;flex-direction:column;">
                                <span style="color:#38bdf8;font-size:0.76rem;">${it.ticker.split('.')[0]}</span>
                                <span style="color:#64748b;font-size:0.62rem;font-weight:450;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${it.company_name}">${it.company_name}</span>
                            </div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;white-space:nowrap;">${seriesBadge}</td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);white-space:nowrap;">
                            <div style="color:#cbd5e1;font-size:0.68rem;">${it.listing_date}</div>
                            <div style="color:#64748b;font-size:0.6rem;">${it.days_on_market}d ago</div>
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);white-space:nowrap;">
                            <span style="color:#ffffff;font-weight:700;">${cmpStr}</span>
                            ${debutHtml}
                        </td>
                        <td style="padding:0.55rem 0.5rem;font-family:var(--font-mono);font-size:0.68rem;white-space:nowrap;">
                            ${ret7dStr} <span style="color:#475569;">/</span> ${ret30dStr}
                        </td>
                        <td style="padding:0.55rem 0.5rem;white-space:nowrap;">
                            ${athDistHtml}
                        </td>
                        <td style="padding:0.55rem 0.5rem;white-space:nowrap;">
                            <span style="background:${badgeBg};color:${badgeCol};border:1px solid ${badgeBorder};border-radius:4px;padding:0.12rem 0.4rem;font-size:0.65rem;font-weight:700;display:inline-flex;align-items:center;gap:0.25rem;">
                                ${it.result_sequence_label}
                            </span>
                        </td>
                        <td style="padding:0.55rem 0.5rem;text-align:center;white-space:nowrap;" onclick="event.stopPropagation();">
                            <div style="display:flex;align-items:center;justify-content:center;gap:0.3rem;">
                                ${wlButton}
                                <button type="button" onclick="event.stopPropagation(); app.inspectNewAdditionStock('${it.ticker}', true)" class="btn btn-secondary btn-sm" style="font-size:0.65rem;padding:0.18rem 0.45rem;border-radius:4px;color:#cbd5e1;" title="Inspect stock in right panel">
                                    🔍
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        /**
         * Inspect a newly listed stock, pulling deep IPO technical, earnings lifecycle, and institutional backing.
         * @param {string} ticker
         * @param {boolean} autoScroll
         */
        async inspectNewAdditionStock(ticker, autoScroll = false) {
            if (!ticker) return;

            // Ensure .NS suffix for NSE equities if no exchange suffix present
            let cleanTicker = ticker.trim().toUpperCase();
            if (!cleanTicker.endsWith('.NS') && !cleanTicker.endsWith('.BO') && !cleanTicker.includes('.')) {
                cleanTicker = `${cleanTicker}.NS`;
            }

            this._selectedTicker = cleanTicker;

            // Highlight corresponding row in table
            const allRows = document.querySelectorAll('#newAdditionsTableBody tr');
            allRows.forEach(r => {
                r.style.background = 'transparent';
                r.style.borderColor = 'rgba(255,255,255,0.06)';
            });
            const safeId = cleanTicker.replace(/[^a-zA-Z0-9]/g, '');
            const targetRow = document.getElementById(`row-new-addition-${safeId}`);
            if (targetRow) {
                targetRow.style.background = 'rgba(59,130,246,0.12)';
                targetRow.style.borderColor = 'rgba(59,130,246,0.35)';
            }

            // If right pane was hidden (in single-column mode), ensure split grid is visible or scroll
            const grid = document.getElementById('newAdditionsSplitGrid');
            if (grid && grid.style.gridTemplateColumns === '1fr') {
                this.toggleNewAdditionsSplitLayout(true);
            }

            if (autoScroll) {
                const rightPane = document.getElementById('newAdditionsSplitRight');
                if (rightPane) {
                    rightPane.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }

            // Set loading skeleton state in header
            const selTickerEl = document.getElementById('newAdditionsSelectedTicker');
            const selNameEl = document.getElementById('newAdditionsSelectedCompanyName');
            const selVerdictEl = document.getElementById('newAdditionsSelectedVerdictBadge');
            const selLinkEl = document.getElementById('newAdditionsSelectedStockLink');

            if (selTickerEl) selTickerEl.textContent = cleanTicker;
            if (selNameEl) selNameEl.textContent = 'Fetching IPO intelligence...';
            if (selVerdictEl) {
                selVerdictEl.textContent = 'SYNCING';
                selVerdictEl.style.background = 'rgba(59,130,246,0.15)';
                selVerdictEl.style.color = '#60a5fa';
                selVerdictEl.style.borderColor = 'rgba(59,130,246,0.3)';
            }
            if (selLinkEl) {
                selLinkEl.href = `/stock/${encodeURIComponent(cleanTicker)}`;
            }

            // Check cache
            if (this._ipoDetailCache.has(cleanTicker)) {
                this.renderIpoDetail(this._ipoDetailCache.get(cleanTicker));
                return;
            }

            // Fetch live IPO detail from API
            try {
                const res = await fetch(API_BASE + `/api/v1/market/ipo-detail/${encodeURIComponent(cleanTicker)}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.success) {
                        this._ipoDetailCache.set(cleanTicker, data);
                        this.renderIpoDetail(data);
                    } else {
                        if (selNameEl) selNameEl.textContent = 'Listing details not found.';
                    }
                } else {
                    if (selNameEl) selNameEl.textContent = `Server error (${res.status})`;
                }
            } catch (e) {
                console.error('[NEW-ADDITIONS] Error fetching IPO detail for', cleanTicker, e);
                if (selNameEl) selNameEl.textContent = 'Network error fetching detail.';
            }
        },

        /**
         * Render detailed IPO inspection data into the right-hand panel.
         * @param {Object} data
         */
        renderIpoDetail(data) {
            if (!data) return;

            const ticker = data.ticker || this._selectedTicker || '--';
            const tech = data.technical || {};
            const earn = data.earnings_lifecycle || {};
            const inst = data.institutional || {};

            // 1. Header Card
            const selTickerEl = document.getElementById('newAdditionsSelectedTicker');
            const selNameEl = document.getElementById('newAdditionsSelectedCompanyName');
            const selVerdictEl = document.getElementById('newAdditionsSelectedVerdictBadge');
            const selLinkEl = document.getElementById('newAdditionsSelectedStockLink');
            const selTimeframeEl = document.getElementById('newAdditionsSelectedTimeframe');

            if (selTickerEl) selTickerEl.textContent = ticker;
            if (selNameEl) selNameEl.textContent = data.company_name || ticker.split('.')[0];
            if (selLinkEl) selLinkEl.href = `/stock/${encodeURIComponent(ticker)}`;

            // Verdict badge reflects technical stage or result sequence
            const stage = tech.stage || 'New Debut';
            if (selVerdictEl) {
                selVerdictEl.textContent = tech.stage_badge ? stage : (data.is_sme ? 'SME LISTING' : 'MAINBOARD');
                if (tech.stage_badge === 'emerald') {
                    selVerdictEl.style.cssText = 'background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else if (tech.stage_badge === 'amber') {
                    selVerdictEl.style.cssText = 'background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else if (tech.stage_badge === 'rose') {
                    selVerdictEl.style.cssText = 'background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else {
                    selVerdictEl.style.cssText = 'background:#18181b;color:#f4f4f5;border:1px solid rgba(255,255,255,0.25);font-size:0.65rem;padding:0.12rem 0.45rem;';
                }
            }

            if (selTimeframeEl) {
                selTimeframeEl.textContent = `Listed: ${data.listing_date} (${data.days_on_market}d on market) · Series: ${data.series || 'EQ'}`;
            }

            // Valuation Bar
            const priceEl = document.getElementById('ipoPriceVal');
            const debutRetEl = document.getElementById('ipoDebutRetVal');
            const ret7dEl = document.getElementById('ipoRet7dVal');
            const ret30dEl = document.getElementById('ipoRet30dVal');
            const athDistEl = document.getElementById('ipoAthDistVal');
            const mcapEl = document.getElementById('ipoMcapVal');

            if (priceEl) {
                priceEl.textContent = (tech.cmp !== null && tech.cmp !== undefined) ? `₹${Number(tech.cmp).toLocaleString('en-IN', {minimumFractionDigits: 1, maximumFractionDigits: 2})}` : '—';
            }

            if (debutRetEl) {
                if (tech.return_since_listing_pct !== null && tech.return_since_listing_pct !== undefined) {
                    const val = tech.return_since_listing_pct;
                    debutRetEl.textContent = `${val > 0 ? '+' : ''}${val.toFixed(1)}%`;
                    debutRetEl.style.color = val >= 0 ? '#34d399' : '#f87171';
                } else {
                    debutRetEl.textContent = '—';
                    debutRetEl.style.color = '#ffffff';
                }
            }

            if (ret7dEl) {
                if (tech.return_7d_pct !== null && tech.return_7d_pct !== undefined) {
                    const val = tech.return_7d_pct;
                    ret7dEl.textContent = `${val > 0 ? '+' : ''}${val.toFixed(1)}%`;
                    ret7dEl.style.color = val >= 0 ? '#34d399' : '#f87171';
                } else {
                    ret7dEl.textContent = '—';
                    ret7dEl.style.color = '#71717a';
                }
            }

            if (ret30dEl) {
                if (tech.return_30d_pct !== null && tech.return_30d_pct !== undefined) {
                    const val = tech.return_30d_pct;
                    ret30dEl.textContent = `${val > 0 ? '+' : ''}${val.toFixed(1)}%`;
                    ret30dEl.style.color = val >= 0 ? '#34d399' : '#f87171';
                } else {
                    ret30dEl.textContent = '—';
                    ret30dEl.style.color = '#71717a';
                }
            }

            if (athDistEl) {
                if (tech.ath_distance_pct !== null && tech.ath_distance_pct !== undefined) {
                    const val = tech.ath_distance_pct;
                    athDistEl.textContent = `${val > 0 ? '+' : ''}${val.toFixed(1)}%`;
                    athDistEl.style.color = val >= -3 ? '#34d399' : (val >= -15 ? '#fbbf24' : '#94a3b8');
                } else {
                    athDistEl.textContent = '—';
                    athDistEl.style.color = '#71717a';
                }
            }

            if (mcapEl) {
                mcapEl.textContent = data.is_sme ? 'SME Growth' : 'Mainboard EQ';
            }

            // 2. Technical Structure Card
            const baseStageBadge = document.getElementById('ipoBaseStageBadge');
            const listingLevelsEl = document.getElementById('ipoListingLevelsVal');
            const listingHighEl = document.getElementById('ipoListingHighVal');
            const athPriceEl = document.getElementById('ipoAthPriceVal');
            const atlPriceEl = document.getElementById('ipoAtlPriceVal');
            const volRatioEl = document.getElementById('ipoVolRatioVal');

            if (baseStageBadge) {
                baseStageBadge.textContent = tech.stage || 'Listed';
                if (tech.stage_badge === 'emerald') {
                    baseStageBadge.style.cssText = 'background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else if (tech.stage_badge === 'amber') {
                    baseStageBadge.style.cssText = 'background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else if (tech.stage_badge === 'rose') {
                    baseStageBadge.style.cssText = 'background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else {
                    baseStageBadge.style.cssText = 'background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                }
            }

            const lDay = tech.listing_day || {};
            if (listingLevelsEl) {
                const oStr = lDay.open !== null && lDay.open !== undefined ? `₹${lDay.open}` : '—';
                const cStr = lDay.close !== null && lDay.close !== undefined ? `₹${lDay.close}` : '—';
                listingLevelsEl.textContent = `${oStr} / ${cStr}`;
            }

            if (listingHighEl) {
                listingHighEl.textContent = (lDay.high !== null && lDay.high !== undefined) ? `₹${lDay.high}` : '—';
            }

            if (athPriceEl) {
                athPriceEl.textContent = (tech.ath_price !== null && tech.ath_price !== undefined) ? `₹${tech.ath_price}` : '—';
            }

            if (atlPriceEl) {
                atlPriceEl.textContent = (tech.atl_price !== null && tech.atl_price !== undefined) ? `₹${tech.atl_price}` : '—';
            }

            if (volRatioEl) {
                if (tech.volume_ratio_5_20 !== null && tech.volume_ratio_5_20 !== undefined) {
                    const vr = tech.volume_ratio_5_20;
                    volRatioEl.textContent = `${vr.toFixed(2)}x`;
                    volRatioEl.style.color = vr >= 1.5 ? '#34d399' : (vr < 0.7 ? '#94a3b8' : '#38bdf8');
                } else {
                    volRatioEl.textContent = '—';
                    volRatioEl.style.color = '#71717a';
                }
            }

            // 3. Debut Earnings Lifecycle Card
            const earnSeqBadge = document.getElementById('ipoEarningsSeqBadge');
            const nextEarnDateEl = document.getElementById('ipoNextEarningsDate');
            const quarterResultsBody = document.getElementById('ipoQuarterResultsBody');

            const seq = earn.result_sequence || {};
            if (earnSeqBadge) {
                earnSeqBadge.textContent = seq.result_sequence_label || (earn.past_earnings_count === 0 ? '🌟 1st Result Debut' : `Quarter #${earn.past_earnings_count + 1}`);
                if (seq.result_sequence_badge === 'amber' || earn.past_earnings_count === 0) {
                    earnSeqBadge.style.cssText = 'background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else if (seq.result_sequence_badge === 'emerald') {
                    earnSeqBadge.style.cssText = 'background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                } else {
                    earnSeqBadge.style.cssText = 'background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);font-size:0.65rem;padding:0.12rem 0.45rem;';
                }
            }

            if (nextEarnDateEl) {
                if (earn.upcoming_result && earn.upcoming_result.earnings_date) {
                    nextEarnDateEl.textContent = `${earn.upcoming_result.earnings_date} (${earn.upcoming_result.source || 'NSE'})`;
                } else {
                    nextEarnDateEl.textContent = earn.past_earnings_count === 0 ? 'Awaiting 1st Board Announcement' : 'Date Pending NSE Announcement';
                }
            }

            if (quarterResultsBody) {
                if (earn.last_reported) {
                    const lr = earn.last_reported;
                    const surp = lr.surprise_pct;
                    const surpHtml = (surp !== null && surp !== undefined)
                        ? `<span style="color:${surp >= 0 ? '#34d399' : '#f87171'};font-weight:700;">${surp > 0 ? '+' : ''}${surp.toFixed(1)}%</span>`
                        : '<span style="color:#64748b;">—</span>';

                    quarterResultsBody.innerHTML = `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                            <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#f8fafc;">${lr.earnings_date}</td>
                            <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#ffffff;font-weight:700;">${lr.eps_reported !== null ? `₹${lr.eps_reported}` : '—'}</td>
                            <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);color:#94a3b8;">${lr.eps_estimate !== null ? `₹${lr.eps_estimate}` : '—'}</td>
                            <td style="padding:0.4rem 0.5rem;font-family:var(--font-mono);">${surpHtml}</td>
                            <td style="padding:0.4rem 0.5rem;color:#60a5fa;font-size:0.62rem;text-transform:uppercase;">${lr.source || 'NSE'}</td>
                        </tr>
                    `;
                } else {
                    quarterResultsBody.innerHTML = `
                        <tr>
                            <td colspan="5" style="padding:0.8rem;text-align:center;color:#64748b;">
                                Awaiting 1st quarterly board meeting under SEBI disclosure window.
                            </td>
                        </tr>
                    `;
                }
            }

            // 4. Smart Money & Shareholding Card
            const shp = inst.shareholding_pattern || {};
            const promPct = shp.promoter_pct !== undefined && shp.promoter_pct !== null ? shp.promoter_pct : null;
            const fiiPct = shp.fii_pct !== undefined && shp.fii_pct !== null ? shp.fii_pct : null;
            const diiPct = shp.dii_pct !== undefined && shp.dii_pct !== null ? shp.dii_pct : null;
            const pubPct = shp.public_retail_pct !== undefined && shp.public_retail_pct !== null ? shp.public_retail_pct : null;

            const promEl = document.getElementById('ipoPromoterPct');
            const fiiEl = document.getElementById('ipoFiiPct');
            const diiEl = document.getElementById('ipoDiiPct');
            const pubEl = document.getElementById('ipoPublicPct');

            if (promEl) promEl.textContent = promPct !== null ? `${promPct.toFixed(1)}%` : '--%';
            if (fiiEl) fiiEl.textContent = fiiPct !== null ? `${fiiPct.toFixed(1)}%` : '--%';
            if (diiEl) diiEl.textContent = diiPct !== null ? `${diiPct.toFixed(1)}%` : '--%';
            if (pubEl) pubEl.textContent = pubPct !== null ? `${pubPct.toFixed(1)}%` : '--%';

            const barProm = document.getElementById('ipoBarPromoter');
            const barFii = document.getElementById('ipoBarFii');
            const barDii = document.getElementById('ipoBarDii');
            const barPub = document.getElementById('ipoBarPublic');

            if (barProm) barProm.style.width = `${Math.min(100, Math.max(0, promPct || 0))}%`;
            if (barFii) barFii.style.width = `${Math.min(100, Math.max(0, fiiPct || 0))}%`;
            if (barDii) barDii.style.width = `${Math.min(100, Math.max(0, diiPct || 0))}%`;
            if (barPub) barPub.style.width = `${Math.min(100, Math.max(0, pubPct || 0))}%`;

            // Mutual Funds Table
            const mfTbody = document.getElementById('ipoMutualFundsTableBody');
            if (mfTbody) {
                const funds = inst.mutual_funds || [];
                if (funds.length > 0) {
                    mfTbody.innerHTML = funds.map(f => `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:0.35rem 0.5rem;color:#f8fafc;font-weight:600;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${f.fund_name}">
                                ${f.fund_name}
                            </td>
                            <td style="padding:0.35rem 0.45rem;color:#94a3b8;font-size:0.62rem;">${f.fund_type || 'MF'}</td>
                            <td style="padding:0.35rem 0.45rem;font-family:var(--font-mono);color:#34d399;font-weight:700;">${f.holding_pct ? `${f.holding_pct.toFixed(2)}%` : '—'}</td>
                            <td style="padding:0.35rem 0.45rem;font-family:var(--font-mono);color:#ffffff;">${f.market_value_cr ? `₹${f.market_value_cr.toFixed(1)} Cr` : '—'}</td>
                        </tr>
                    `).join('');
                } else {
                    mfTbody.innerHTML = `
                        <tr>
                            <td colspan="4" style="padding:0.8rem;text-align:center;color:#64748b;">
                                No institutional mutual fund disclosures on record yet.
                            </td>
                        </tr>
                    `;
                }
            }

            // Block Deals Container
            const bdContainer = document.getElementById('ipoBlockDealsContainer');
            if (bdContainer) {
                const deals = inst.block_deals || [];
                if (deals.length > 0) {
                    bdContainer.innerHTML = deals.map(d => `
                        <div style="padding:0.4rem 0.5rem;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:4px;margin-bottom:0.3rem;display:flex;align-items:center;justify-content:space-between;gap:0.4rem;">
                            <div>
                                <div style="font-weight:600;color:#f8fafc;">${d.client_name}</div>
                                <div style="font-size:0.6rem;color:#71717a;font-family:var(--font-mono);">${d.deal_date} · ${d.exchange} · <span style="color:${d.deal_type === 'BUY' ? '#34d399' : '#f87171'};font-weight:700;">${d.deal_type}</span></div>
                            </div>
                            <div style="text-align:right;font-family:var(--font-mono);">
                                <div style="font-weight:700;color:#ffffff;">₹${d.price}</div>
                                <div style="font-size:0.6rem;color:#38bdf8;">${d.value_cr ? `₹${d.value_cr.toFixed(1)} Cr` : `${d.quantity} shares`}</div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    bdContainer.innerHTML = `
                        <div style="color:#64748b;text-align:center;padding:0.5rem;">
                            No bulk or block transactions recorded since listing debut.
                        </div>
                    `;
                }
            }
        },

        /**
         * Toggle between 50-50 split screen and full-width table.
         * @param {boolean|null} forceSplit
         */
        toggleNewAdditionsSplitLayout(forceSplit = null) {
            const grid = document.getElementById('newAdditionsSplitGrid');
            const rightPane = document.getElementById('newAdditionsSplitRight');
            const btn = document.getElementById('btnToggleNewAdditionsSplit');
            if (!grid) return;

            const isCurrentlySplit = grid.style.gridTemplateColumns !== '1fr';
            const willSplit = forceSplit !== null ? forceSplit : !isCurrentlySplit;

            if (willSplit) {
                grid.style.gridTemplateColumns = 'minmax(0, 1.05fr) minmax(0, 0.95fr)';
                if (rightPane) rightPane.style.display = 'block';
                if (btn) {
                    btn.textContent = '◫ 50-50 Split';
                    btn.style.background = '#18181b';
                    btn.style.color = '#cbd5e1';
                }
                localStorage.setItem('new_additions_split_layout', 'split');
            } else {
                grid.style.gridTemplateColumns = '1fr';
                if (rightPane) rightPane.style.display = 'none';
                if (btn) {
                    btn.textContent = '🗖 Full Table';
                    btn.style.background = 'rgba(59,130,246,0.15)';
                    btn.style.color = '#60a5fa';
                }
                localStorage.setItem('new_additions_split_layout', 'full');
            }
        },

        /**
         * Restore split layout preference from localStorage.
         */
        restoreNewAdditionsSplitLayout() {
            const saved = localStorage.getItem('new_additions_split_layout');
            if (saved === 'full') {
                this.toggleNewAdditionsSplitLayout(false);
            } else {
                this.toggleNewAdditionsSplitLayout(true);
            }
        },

        /**
         * Quick ticker lookup from search input.
         * @param {string} ticker
         */
        searchNewAdditionsStock(ticker) {
            if (!ticker) return;
            const sym = ticker.trim().toUpperCase();
            this.inspectNewAdditionStock(sym, true);
        },

        /**
         * Add stock to watchlist with feedback.
         */
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
                        btnElement.textContent = '+ Watchlist';
                    }
                }
            } catch (e) {
                console.error('Error adding to watchlist:', e);
                alert('Error: ' + e.message);
                if (btnElement) {
                    btnElement.disabled = false;
                    btnElement.textContent = '+ Watchlist';
                }
            }
        }
    };

    // Export module
    window.NewAdditionsModule = newAdditionsModule;
    window.app = window.app || {};
    Object.assign(window.app, newAdditionsModule);
})();
