/**
 * Option Chain & Derivatives Hub Module
 *
 * Provides interactive strike trees, ATM call/put walls, Max Pain, PCR metrics,
 * and multi-day positioning snapshots from NSE Option Chains.
 */
(function (window) {
    'use strict';

    window.app = window.app || {};
    const app = window.app;

    app._optionsSymbol = 'NIFTY';
    app._optionsExpiry = '';
    app._optionsStrikeRange = 20;
    app._optionsChart = null;

    /**
     * Switch active symbol and refresh data
     */
    app.switchOptionSymbol = function (symbol) {
        if (!symbol) return;
        const clean = symbol.trim().toUpperCase().replace('.NS', '');
        app._optionsSymbol = clean;
        app._optionsExpiry = ''; // Reset expiry to default to nearest active for new symbol

        // Update active class on quick pills
        document.querySelectorAll('.option-sym-pill').forEach(pill => {
            pill.classList.toggle('active', pill.getAttribute('data-sym') === clean);
        });

        const input = document.getElementById('optionsSymbolInput');
        if (input) input.value = clean;

        app.loadOptionChain(false);
    };

    /**
     * Handler for expiry date selector
     */
    app.onOptionExpiryChange = function (expiry) {
        app._optionsExpiry = expiry || '';
        app.loadOptionChain(false);
    };

    /**
     * Handler for strike range selector
     */
    app.onOptionStrikeRangeChange = function (range) {
        app._optionsStrikeRange = parseInt(range, 10) || 20;
        app.loadOptionChain(false);
    };

    /**
     * Load Option Chain and calculate key metrics
     */
    app.loadOptionChain = async function (forceRefresh = false) {
        const symbol = app._optionsSymbol || 'NIFTY';
        const expiry = app._optionsExpiry || '';
        const strikeRange = app._optionsStrikeRange || 20;

        const refreshBtn = document.getElementById('optionsRefreshBtn');
        const chartLoading = document.getElementById('optionsChartLoading');
        const statusBanner = document.getElementById('optionsStatusBanner');

        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<span>⏳</span> Loading...';
        }
        if (chartLoading) chartLoading.style.display = 'flex';

        try {
            let url = `/api/v1/options/chain?symbol=${encodeURIComponent(symbol)}&strike_range=${strikeRange}`;
            if (expiry) url += `&expiry=${encodeURIComponent(expiry)}`;
            if (forceRefresh) url += `&force_refresh=true`;

            const res = await fetch(url);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || `Server error: ${res.status}`);
            }

            const payload = await res.json();
            const data = payload.data || {};

            // Handle status banner for offline / archived / not_fno states
            if (statusBanner) {
                if (data.status === 'NOT_FNO') {
                    statusBanner.style.display = 'block';
                    statusBanner.style.background = 'rgba(239, 68, 68, 0.15)';
                    statusBanner.style.border = '1px solid rgba(239, 68, 68, 0.35)';
                    statusBanner.style.color = '#f87171';
                    statusBanner.innerHTML = `⚠️ <strong>${symbol} is not eligible for NSE Derivatives (F&amp;O)</strong>. Only official NSE index &amp; stock derivatives are supported.`;
                } else if (data.status === 'ARCHIVED') {
                    statusBanner.style.display = 'block';
                    statusBanner.style.background = 'rgba(245, 158, 11, 0.15)';
                    statusBanner.style.border = '1px solid rgba(245, 158, 11, 0.35)';
                    statusBanner.style.color = '#fbbf24';
                    statusBanner.innerHTML = `ℹ️ <strong>NSE Live Option Chain is closed / unreachable</strong>. Displaying latest recorded positioning snapshot${data.as_of_date ? ' from ' + data.as_of_date : ''}.`;
                } else if (data.status === 'OFFLINE') {
                    statusBanner.style.display = 'block';
                    statusBanner.style.background = 'rgba(239, 68, 68, 0.15)';
                    statusBanner.style.border = '1px solid rgba(239, 68, 68, 0.35)';
                    statusBanner.style.color = '#f87171';
                    statusBanner.innerHTML = `📡 <strong>Option Chain Unreachable</strong>. NSE data provider did not respond and no local archival snapshot was found.`;
                } else {
                    statusBanner.style.display = 'none';
                }
            }

            // Populate Expiries Dropdown if available
            app.populateOptionExpiries(data.expiries || [], data.selected_expiry || expiry);

            // Render KPI cards
            app.renderOptionKpiCards(data);

            // Render Open Interest Distribution Chart
            app.renderOiDistributionChart(data);

            // Render Strike Tree Table
            app.renderStrikeTreeTable(data);

            // Also load multi-day positioning history asynchronously
            app.fetchOptionHistory(symbol);

        } catch (err) {
            console.error('Failed to load option chain:', err);
            if (statusBanner) {
                statusBanner.style.display = 'block';
                statusBanner.style.background = 'rgba(239, 68, 68, 0.15)';
                statusBanner.style.border = '1px solid rgba(239, 68, 68, 0.35)';
                statusBanner.style.color = '#f87171';
                statusBanner.innerHTML = `❌ <strong>Error loading option chain:</strong> ${err.message}`;
            }
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<span>🔄</span> Refresh';
            }
            if (chartLoading) chartLoading.style.display = 'none';
        }
    };

    /**
     * Populate the expiry dates dropdown
     */
    app.populateOptionExpiries = function (expiries, selectedExpiry) {
        const select = document.getElementById('optionsExpirySelect');
        if (!select) return;

        const currentVal = selectedExpiry || app._optionsExpiry || '';
        let html = '<option value="">Nearest Active</option>';

        if (expiries && expiries.length > 0) {
            expiries.forEach(exp => {
                const isSelected = (exp === currentVal) ? 'selected' : '';
                html += `<option value="${exp}" ${isSelected}>${exp}</option>`;
            });
        }
        select.innerHTML = html;
        if (currentVal && expiries.includes(currentVal)) {
            select.value = currentVal;
        }
    };

    /**
     * Render the 7 KPI Summary Cards
     */
    app.renderOptionKpiCards = function (data) {
        const formatNum = (num, decimals = 2) => {
            if (num === null || num === undefined || isNaN(num)) return '--';
            return Number(num).toLocaleString('en-IN', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            });
        };

        const formatQty = (qty) => {
            if (qty === null || qty === undefined || isNaN(qty)) return '--';
            const val = Number(qty);
            if (val >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
            if (val >= 100000) return (val / 100000).toFixed(2) + ' L';
            if (val >= 1000) return (val / 1000).toFixed(1) + 'k';
            return val.toLocaleString('en-IN');
        };

        // Spot Price
        const spotEl = document.getElementById('optKpiSpotPrice');
        if (spotEl) spotEl.textContent = formatNum(data.spot_price, 2);

        // Max Pain Strike
        const mpEl = document.getElementById('optKpiMaxPain');
        if (mpEl) mpEl.textContent = formatNum(data.max_pain_strike, 0);

        // PCR (OI)
        const pcrOiEl = document.getElementById('optKpiPcrOi');
        const pcrOiLabel = document.getElementById('optKpiPcrOiLabel');
        if (pcrOiEl) {
            const pcr = data.pcr_oi;
            pcrOiEl.textContent = formatNum(pcr, 2);
            if (pcr !== null && pcr !== undefined) {
                if (pcr > 1.2) {
                    pcrOiEl.style.color = '#34d399'; // Bullish
                    if (pcrOiLabel) pcrOiLabel.textContent = 'Bullish (Put Heavy)';
                } else if (pcr < 0.8) {
                    pcrOiEl.style.color = '#f87171'; // Bearish
                    if (pcrOiLabel) pcrOiLabel.textContent = 'Bearish (Call Heavy)';
                } else {
                    pcrOiEl.style.color = '#38bdf8'; // Neutral
                    if (pcrOiLabel) pcrOiLabel.textContent = 'Neutral (Balanced)';
                }
            }
        }

        // PCR (Volume)
        const pcrVolEl = document.getElementById('optKpiPcrVol');
        if (pcrVolEl) pcrVolEl.textContent = formatNum(data.pcr_volume, 2);

        // Call Wall (Resistance)
        const callWallEl = document.getElementById('optKpiCallWall');
        const callWallOiEl = document.getElementById('optKpiCallWallOi');
        if (callWallEl) callWallEl.textContent = formatNum(data.resistance_strike, 0);
        if (callWallOiEl) callWallOiEl.textContent = `Total Call OI: ${formatQty(data.call_oi_total)}`;

        // Put Wall (Support)
        const putWallEl = document.getElementById('optKpiPutWall');
        const putWallOiEl = document.getElementById('optKpiPutWallOi');
        if (putWallEl) putWallEl.textContent = formatNum(data.support_strike, 0);
        if (putWallOiEl) putWallOiEl.textContent = `Total Put OI: ${formatQty(data.put_oi_total)}`;

        // ATM IV & Sentiment
        const atmIvEl = document.getElementById('optKpiAtmIv');
        const atmStraddleEl = document.getElementById('optKpiAtmStraddle');
        if (atmIvEl) {
            const atmStrike = (data.strikes || []).find(s => s.is_atm);
            if (atmStrike) {
                const avgIv = ((atmStrike.ce_iv || 0) + (atmStrike.pe_iv || 0)) / ((atmStrike.ce_iv && atmStrike.pe_iv) ? 2 : 1);
                atmIvEl.textContent = avgIv > 0 ? `${avgIv.toFixed(1)}%` : '--';
                if (atmStraddleEl) {
                    const straddleCost = (atmStrike.ce_ltp || 0) + (atmStrike.pe_ltp || 0);
                    atmStraddleEl.textContent = `Straddle: ₹${straddleCost.toFixed(1)} (@${atmStrike.strike})`;
                }
            } else {
                atmIvEl.textContent = '--';
                if (atmStraddleEl) atmStraddleEl.textContent = 'CE + PE Premium';
            }
        }

        // Header Sentiment Badge
        const sentimentBadge = document.getElementById('optionsSentimentBadge');
        if (sentimentBadge) {
            if (data.sentiment) {
                sentimentBadge.style.display = 'inline-block';
                sentimentBadge.textContent = data.sentiment;
                if (data.sentiment.includes('BULLISH')) {
                    sentimentBadge.style.background = 'rgba(16,185,129,0.15)';
                    sentimentBadge.style.color = '#34d399';
                    sentimentBadge.style.border = '1px solid rgba(16,185,129,0.3)';
                } else if (data.sentiment.includes('BEARISH')) {
                    sentimentBadge.style.background = 'rgba(239,68,68,0.15)';
                    sentimentBadge.style.color = '#f87171';
                    sentimentBadge.style.border = '1px solid rgba(239,68,68,0.3)';
                } else {
                    sentimentBadge.style.background = 'rgba(245,158,11,0.15)';
                    sentimentBadge.style.color = '#fbbf24';
                    sentimentBadge.style.border = '1px solid rgba(245,158,11,0.3)';
                }
            } else {
                sentimentBadge.style.display = 'none';
            }
        }
    };

    /**
     * Render Open Interest Distribution Bar Chart using Chart.js
     */
    app.renderOiDistributionChart = function (data) {
        const ctx = document.getElementById('optionsOiChart');
        if (!ctx) return;

        const strikes = data.strikes || [];
        if (strikes.length === 0) {
            if (app._optionsChart) {
                app._optionsChart.destroy();
                app._optionsChart = null;
            }
            return;
        }

        const labels = strikes.map(s => s.strike);
        const callOiData = strikes.map(s => s.ce_oi || 0);
        const putOiData = strikes.map(s => s.pe_oi || 0);

        if (app._optionsChart) {
            app._optionsChart.destroy();
        }

        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded on page.');
            return;
        }

        app._optionsChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Call OI (Resistance)',
                        data: callOiData,
                        backgroundColor: 'rgba(239, 68, 68, 0.75)',
                        borderColor: '#ef4444',
                        borderWidth: 1,
                        borderRadius: 3,
                    },
                    {
                        label: 'Put OI (Support)',
                        data: putOiData,
                        backgroundColor: 'rgba(16, 185, 129, 0.75)',
                        borderColor: '#10b981',
                        borderWidth: 1,
                        borderRadius: 3,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(10, 10, 10, 0.9)',
                        titleColor: '#fbbf24',
                        titleFont: { weight: 'bold' },
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        callbacks: {
                            label: function (context) {
                                const val = context.parsed.y || 0;
                                const formatted = val >= 100000 ? (val / 100000).toFixed(2) + ' L' : val.toLocaleString();
                                return `${context.dataset.label}: ${formatted} (${val.toLocaleString()} contracts)`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)'
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: { size: 10, family: 'var(--font-mono)' }
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)'
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: { size: 10, family: 'var(--font-mono)' },
                            callback: function (val) {
                                if (val >= 10000000) return (val / 10000000) + ' Cr';
                                if (val >= 100000) return (val / 100000) + ' L';
                                if (val >= 1000) return (val / 1000) + 'k';
                                return val;
                            }
                        }
                    }
                }
            }
        });
    };

    /**
     * Render the comprehensive Strike Tree Table
     */
    app.renderStrikeTreeTable = function (data) {
        const tbody = document.getElementById('optionsStrikeTreeBody');
        if (!tbody) return;

        const strikes = data.strikes || [];
        if (strikes.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="11" style="text-align:center;padding:2.5rem;color:var(--text-secondary);">
                        No option strikes available for the selected parameters.
                    </td>
                </tr>
            `;
            return;
        }

        const formatQty = (val) => {
            if (!val) return '-';
            const num = Number(val);
            if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
            if (num >= 1000) return (num / 1000).toFixed(1) + 'k';
            return num.toLocaleString('en-IN');
        };

        const formatDelta = (delta) => {
            if (!delta || delta === 0) return '<span style="color:#71717a;">0</span>';
            const num = Number(delta);
            const formatted = formatQty(Math.abs(num));
            if (num > 0) {
                return `<span style="color:#34d399;">+${formatted}</span>`;
            }
            return `<span style="color:#f87171;">-${formatted}</span>`;
        };

        const formatPrice = (val) => {
            if (val === null || val === undefined) return '-';
            return Number(val).toFixed(2);
        };

        const formatIv = (val) => {
            if (!val || val === 0) return '-';
            return Number(val).toFixed(1) + '%';
        };

        let html = '';
        strikes.forEach(s => {
            const isAtm = !!s.is_atm;
            const ceItm = !!s.ce_itm;
            const peItm = !!s.pe_itm;

            // Row styling
            let rowBg = 'transparent';
            let strikeStyle = 'color: #ededed;';

            if (isAtm) {
                rowBg = 'rgba(245, 158, 11, 0.12)';
                strikeStyle = 'color: #fbbf24; font-weight: 800; border-left: 2px solid #fbbf24; border-right: 2px solid #fbbf24;';
            }

            const ceBg = ceItm ? 'background:rgba(239, 68, 68, 0.06);' : '';
            const peBg = peItm ? 'background:rgba(16, 185, 129, 0.06);' : '';

            html += `
                <tr style="background:${rowBg}; border-bottom: 1px solid rgba(255,255,255,0.04);" ${isAtm ? 'id="optionsAtmRow"' : ''}>
                    <!-- CE: OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${ceBg}">${formatQty(s.ce_oi)}</td>
                    <!-- CE: Chg OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${ceBg}">${formatDelta(s.ce_change_oi)}</td>
                    <!-- CE: Volume -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${ceBg}">${formatQty(s.ce_vol)}</td>
                    <!-- CE: IV -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${ceBg}">${formatIv(s.ce_iv)}</td>
                    <!-- CE: LTP -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#f87171;border-right:1px solid rgba(255,255,255,0.08);${ceBg}">${formatPrice(s.ce_ltp)}</td>

                    <!-- STRIKE -->
                    <td style="padding:0.35rem 0.5rem;text-align:center;font-family:var(--font-mono);background:#121316;${strikeStyle}">
                        ${s.strike} ${isAtm ? '<span style="font-size:0.65rem;background:#fbbf24;color:#000;padding:0.1rem 0.3rem;border-radius:4px;margin-left:0.2rem;font-weight:bold;">ATM</span>' : ''}
                    </td>

                    <!-- PE: LTP -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);font-weight:700;color:#34d399;border-left:1px solid rgba(255,255,255,0.08);${peBg}">${formatPrice(s.pe_ltp)}</td>
                    <!-- PE: IV -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${peBg}">${formatIv(s.pe_iv)}</td>
                    <!-- PE: Volume -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);color:var(--text-secondary);${peBg}">${formatQty(s.pe_vol)}</td>
                    <!-- PE: Chg OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${peBg}">${formatDelta(s.pe_change_oi)}</td>
                    <!-- PE: OI -->
                    <td style="padding:0.35rem 0.5rem;font-family:var(--font-mono);${peBg}">${formatQty(s.pe_oi)}</td>
                </tr>
            `;
        });

        tbody.innerHTML = html;

        // Auto-scroll to ATM row smoothly inside container
        setTimeout(() => {
            const atmRow = document.getElementById('optionsAtmRow');
            if (atmRow) {
                atmRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 150);
    };

    /**
     * Fetch and render multi-day historical snapshots
     */
    app.fetchOptionHistory = async function (symbol = null) {
        const sym = (symbol || app._optionsSymbol || 'NIFTY').trim().toUpperCase().replace('.NS', '');
        const tbody = document.getElementById('optionsHistoryBody');
        if (!tbody) return;

        try {
            const res = await fetch(`/api/v1/options/history?symbol=${encodeURIComponent(sym)}&limit=25`);
            if (!res.ok) throw new Error('Failed to fetch history');

            const payload = await res.json();
            const history = payload.history || [];

            if (history.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="10" style="text-align:center;padding:1.5rem;color:var(--text-secondary);">
                            No historical snapshots recorded yet for ${sym}. Snapshots are saved automatically during market updates.
                        </td>
                    </tr>
                `;
                return;
            }

            const formatQty = (qty) => {
                if (!qty) return '--';
                const val = Number(qty);
                if (val >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
                if (val >= 100000) return (val / 100000).toFixed(2) + ' L';
                return val.toLocaleString('en-IN');
            };

            let html = '';
            history.forEach(h => {
                const sentimentColor = (h.sentiment || '').includes('BULLISH') ? '#34d399' :
                                       (h.sentiment || '').includes('BEARISH') ? '#f87171' : '#fbbf24';
                html += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
                        <td style="font-family:var(--font-mono);font-weight:600;color:var(--text-primary);">${h.as_of_date || '--'}</td>
                        <td style="font-family:var(--font-mono);">${h.spot_price != null ? Number(h.spot_price).toFixed(2) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#fbbf24;font-weight:700;">${h.max_pain_strike != null ? Number(h.max_pain_strike).toFixed(0) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#38bdf8;">${h.pcr_oi != null ? Number(h.pcr_oi).toFixed(2) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#a855f7;">${h.pcr_volume != null ? Number(h.pcr_volume).toFixed(2) : '--'}</td>
                        <td><span style="color:${sentimentColor};font-weight:700;font-size:0.75rem;">${h.sentiment || '--'}</span></td>
                        <td style="font-family:var(--font-mono);color:#f87171;">${h.resistance_strike != null ? Number(h.resistance_strike).toFixed(0) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:#34d399;">${h.support_strike != null ? Number(h.support_strike).toFixed(0) : '--'}</td>
                        <td style="font-family:var(--font-mono);color:var(--text-secondary);">${formatQty(h.call_oi_total)}</td>
                        <td style="font-family:var(--font-mono);color:var(--text-secondary);">${formatQty(h.put_oi_total)}</td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;

        } catch (e) {
            console.error('Error fetching options history:', e);
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" style="text-align:center;padding:1.5rem;color:#f87171;">
                        Could not load historical snapshots: ${e.message}
                    </td>
                </tr>
            `;
        }
    };

    // Auto-initialize when loaded
    if (document.getElementById('tab-options')) {
        app.loadOptionChain(false);
    }

})(window);
