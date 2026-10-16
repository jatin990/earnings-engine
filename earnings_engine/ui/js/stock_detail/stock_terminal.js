/**
 * Nexus Intelligence Platform — Stock Drilldown Terminal Coordinator
 * Quote polling, hard-refresh pipelines, multi-playlist modal, tab coordination, and bootstrap.
 */

(function () {
    'use strict';

    const State = window.StockDetailState;

    /**
     * DOM Bootstrap & Lifecycle Initialization
     */
    document.addEventListener('DOMContentLoaded', () => {
        if (!State.ticker) return;

        initSearchInput();
        initTabNavigation();
        loadStockOverview();

        if (window.initStockChart) window.initStockChart();
        if (window.initStockConsensus) window.initStockConsensus();
        if (window.initStockFundamentals) window.initStockFundamentals();

        // Start 15s quote polling
        startQuotePolling();
    });

    /**
     * Search Input Enter Listener
     */
    function initSearchInput() {
        const input = document.getElementById('stockSearchInput');
        if (!input) return;
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const val = input.value.trim().toUpperCase();
                if (val) {
                    const formatted = (val.endsWith('.NS') || val.endsWith('.BO') || val.includes('.')) ? val : `${val}.NS`;
                    window.location.href = `/stock/${encodeURIComponent(formatted)}`;
                }
            }
        });
    }

    /**
     * Tab Navigation Switcher
     */
    function initTabNavigation() {
        document.querySelectorAll('.stock-tab-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const targetTab = btn.getAttribute('data-tab');
                document.querySelectorAll('.stock-tab-btn').forEach((b) => b.classList.remove('active'));
                document.querySelectorAll('.stock-tab-content').forEach((c) => c.classList.remove('active'));

                btn.classList.add('active');
                const contentEl = document.getElementById(`tabContent_${targetTab}`);
                if (contentEl) contentEl.classList.add('active');

                // If switching to chart tab, trigger chart resize/fit
                if (targetTab === 'chart' && State.chartInstance) {
                    setTimeout(() => {
                        const container = document.getElementById('optionsSmartChartCanvas') || document.getElementById('stockChartCanvas');
                        if (container) {
                            State.chartInstance.applyOptions({
                                width: container.clientWidth,
                                height: 520,
                            });
                        }
                    }, 50);
                }
            });
        });
    }

    /**
     * Fetch Full Stock Overview & Populate Hero + KPIs
     */
    async function loadStockOverview() {
        try {
            const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/overview`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (data && data.success) {
                State.quote = data.quote;
                State.technicals = data.technicals || data.technical;
                renderHeroHeader(data);
                renderKpiStrip(data);
            }
        } catch (e) {
            console.debug('Error loading stock overview:', e);
        }
    }

    /**
     * Render Hero Header Metrics
     */
    function renderHeroHeader(data) {
        const q = data.quote || {};
        const p = data.profile || {};
        const isINR = State.ticker.endsWith('.NS') || State.ticker.endsWith('.BO');

        const companyName = p.name || p.company_name || q.company_name || q.shortName || State.cleanTicker;
        const sectorText = p.sector ? `${p.sector} · ${p.industry || 'Equities'}` : (q.sector ? `${q.sector} · ${q.industry || 'Equities'}` : 'NSE Equities');

        window.setElText('heroTicker', State.ticker);
        window.setElText('heroCompanyName', companyName);
        window.setElText('heroSector', sectorText);

        // Price & Change
        const ltp = q.current_price !== undefined && q.current_price !== null ? q.current_price : q.ltp;
        if (ltp !== undefined && ltp !== null) {
            window.setElText('heroLtp', window.formatPrice(ltp, isINR));

            const change = q.day_change !== undefined && q.day_change !== null ? q.day_change : (q.change !== undefined && q.change !== null ? q.change : 0);
            const changePct = q.day_change_pct !== undefined && q.day_change_pct !== null ? q.day_change_pct : (q.change_pct !== undefined && q.change_pct !== null ? q.change_pct : (q.percent_change !== undefined && q.percent_change !== null ? q.percent_change : 0));
            const isBull = changePct >= 0;

            const changePill = document.getElementById('heroChangePill');
            if (changePill) {
                changePill.textContent = `${isBull ? '+' : ''}${change.toFixed(2)} (${isBull ? '+' : ''}${changePct.toFixed(2)}%)`;
                changePill.className = `stock-change-pill ${isBull ? 'bullish' : 'bearish'}`;
            }
        }

        // Day Range & 52W Range Bars
        const dayLow = q.day_low !== undefined && q.day_low !== null ? q.day_low : q.low;
        const dayHigh = q.day_high !== undefined && q.day_high !== null ? q.day_high : q.high;
        if (dayLow && dayHigh && ltp) {
            window.setElText('dayLowVal', window.formatPrice(dayLow, isINR));
            window.setElText('dayHighVal', window.formatPrice(dayHigh, isINR));
            const dayRangePct = dayHigh > dayLow ? Math.min(Math.max(((ltp - dayLow) / (dayHigh - dayLow)) * 100, 0), 100) : 50;
            const dayFill = document.getElementById('dayRangeFill');
            if (dayFill) dayFill.style.width = `${dayRangePct}%`;
        }

        const week52Low = q.week_52_low !== undefined && q.week_52_low !== null ? q.week_52_low : q.week52_low;
        const week52High = q.week_52_high !== undefined && q.week_52_high !== null ? q.week_52_high : q.week52_high;
        if (week52Low && week52High && ltp) {
            window.setElText('w52LowVal', window.formatPrice(week52Low, isINR));
            window.setElText('w52HighVal', window.formatPrice(week52High, isINR));
            const w52RangePct = week52High > week52Low ? Math.min(Math.max(((ltp - week52Low) / (week52High - week52Low)) * 100, 0), 100) : 50;
            const w52Fill = document.getElementById('w52RangeFill');
            if (w52Fill) w52Fill.style.width = `${w52RangePct}%`;
        }

        // External URLs
        const tvLink = document.getElementById('linkTradingView');
        if (tvLink) tvLink.href = `https://in.tradingview.com/chart/?symbol=NSE:${State.cleanTicker}`;

        const scrLink = document.getElementById('linkScreener');
        if (scrLink) scrLink.href = `https://www.screener.in/company/${State.cleanTicker}/`;
    }

    /**
     * Render Technical & Fundamental KPI Strip
     */
    function renderKpiStrip(data) {
        const t = data.technical || data.technicals || {};
        const q = data.quote || {};

        const rsiVal = t.rsi_14 !== undefined && t.rsi_14 !== null ? t.rsi_14 : (t.rsi !== undefined && t.rsi !== null ? t.rsi : null);
        if (rsiVal !== null) {
            const numRsi = Number(rsiVal);
            window.setElText('kpiRsi', numRsi.toFixed(1));
            const rsiBadge = document.getElementById('kpiRsiBadge');
            if (rsiBadge) {
                rsiBadge.textContent = numRsi >= 70 ? 'Overbought' : numRsi <= 30 ? 'Oversold' : 'Neutral';
                rsiBadge.style.color = numRsi >= 70 ? '#fb7185' : numRsi <= 30 ? '#34d399' : '#8e97a8';
            }
        } else {
            window.setElText('kpiRsi', '—');
        }

        if (t.dma_20) window.setElText('kpiDma20', window.formatPrice(t.dma_20));
        else window.setElText('kpiDma20', '—');

        if (t.dma_50) window.setElText('kpiDma50', window.formatPrice(t.dma_50));
        else window.setElText('kpiDma50', '—');

        if (t.dma_200) window.setElText('kpiDma200', window.formatPrice(t.dma_200));
        else window.setElText('kpiDma200', '—');

        if (q.pe_ratio) window.setElText('kpiPe', `${Number(q.pe_ratio).toFixed(1)}x`);
        else window.setElText('kpiPe', '—');

        if (q.market_cap) window.setElText('kpiMarketCap', window.formatCrores(q.market_cap));
        else window.setElText('kpiMarketCap', '—');

        if (q.volume) window.setElText('kpiVolume', window.formatVolume(q.volume));
        else window.setElText('kpiVolume', '—');
    }

    /**
     * Start Background Quote Polling (15s Interval)
     */
    function startQuotePolling() {
        if (State.isPollingQuote) return;
        State.isPollingQuote = true;

        setInterval(async () => {
            if (document.hidden) return; // Save resources when tab is backgrounded
            try {
                const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/quote`);
                if (!resp.ok) return;
                const data = await resp.json();
                if (data && data.success && data.quote) {
                    renderHeroHeader({ quote: data.quote });
                }
            } catch (e) {
                // Silently handle polling glitch
            }
        }, 15000);
    }

    /**
     * Hard Refresh Prices Trigger
     */
    window.hardRefreshStockPrices = async function () {
        const btn = document.getElementById('btnHardRefresh');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="stock-spinner" style="width:12px;height:12px;border-width:2px;"></span> Refreshing...';
        }
        window.showStockToast('Triggering clean hard-refresh from NSE/Yahoo APIs...', 'info');

        try {
            const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/hard-refresh-prices?hard=true`, {
                method: 'POST',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            window.showStockToast('Prices refreshed successfully', 'success');

            loadStockOverview();
            if (window.loadStockChartData) window.loadStockChartData();
        } catch (err) {
            window.showStockToast(`Refresh failed: ${err.message}`, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '⟳ Refresh Prices';
            }
        }
    };

    /**
     * Watchlist Playlist Modal Management
     */
    window.openWatchlistModal = async function () {
        const modal = document.getElementById('stockWatchlistModal');
        const listContainer = document.getElementById('stockWatchlistItems');
        if (!modal || !listContainer) return;

        listContainer.innerHTML = '<div style="color:#8e97a8;"><span class="stock-spinner" style="width:14px;height:14px;border-width:2px;"></span> Loading playlists...</div>';
        modal.classList.add('active');

        try {
            const resp = await fetch('/api/v1/watchlist/all');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            if (data && data.watchlists) {
                renderWatchlistModalItems(data.watchlists);
            }
        } catch (err) {
            listContainer.innerHTML = `<div style="color:#fb7185;">Failed to load playlists: ${err.message}</div>`;
        }
    };

    window.closeWatchlistModal = function () {
        const modal = document.getElementById('stockWatchlistModal');
        if (modal) modal.classList.remove('active');
    };

    function renderWatchlistModalItems(watchlists) {
        const listContainer = document.getElementById('stockWatchlistItems');
        if (!listContainer) return;

        let html = '';
        Object.entries(watchlists).forEach(([name, items]) => {
            const isMember = Array.isArray(items) && items.some((i) => (typeof i === 'string' ? i : i.ticker) === State.ticker);
            html += `
                <div style="display:flex; align-items:center; justify-content:space-between; padding:0.6rem 0.75rem; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:6px;">
                    <div>
                        <div style="font-weight:600; color:#ffffff; font-size:0.85rem;">${name}</div>
                        <div style="font-size:0.72rem; color:#8e97a8;">${Array.isArray(items) ? items.length : 0} items</div>
                    </div>
                    <button type="button"
                            class="stock-btn ${isMember ? 'stock-btn-secondary' : 'stock-btn-primary'}"
                            style="font-size:0.75rem; padding:0.3rem 0.6rem;"
                            onclick="window.toggleWatchlistMembership('${name}', ${isMember})">
                        ${isMember ? '✓ Added' : '＋ Add'}
                    </button>
                </div>
            `;
        });
        listContainer.innerHTML = html;
    }

    window.toggleWatchlistMembership = async function (playlistName, isCurrentlyMember) {
        const endpoint = isCurrentlyMember ? '/api/v1/watchlist/remove' : '/api/v1/watchlist/add';
        try {
            const resp = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    watchlist_name: playlistName,
                    ticker: State.ticker,
                }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            window.showStockToast(`${isCurrentlyMember ? 'Removed from' : 'Added to'} ${playlistName}`, 'success');
            window.openWatchlistModal();
        } catch (err) {
            window.showStockToast(`Failed to update watchlist: ${err.message}`, 'error');
        }
    };
})();
