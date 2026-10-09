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
                        const container = document.getElementById('stockChartCanvas');
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
                State.technicals = data.technicals;
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
        const isINR = State.ticker.endsWith('.NS') || State.ticker.endsWith('.BO');

        window.setElText('heroTicker', State.ticker);
        window.setElText('heroCompanyName', q.company_name || q.shortName || State.cleanTicker);
        window.setElText('heroSector', q.sector ? `${q.sector} · ${q.industry || 'Equities'}` : 'NSE Equities');

        // Price & Change
        if (q.current_price || q.ltp) {
            const ltp = q.current_price || q.ltp;
            window.setElText('heroLtp', window.formatPrice(ltp, isINR));

            const change = q.change !== undefined ? q.change : 0;
            const changePct = q.change_pct !== undefined ? q.change_pct : (q.percent_change !== undefined ? q.percent_change : 0);
            const isBull = changePct >= 0;

            const changePill = document.getElementById('heroChangePill');
            if (changePill) {
                changePill.textContent = `${isBull ? '+' : ''}${change.toFixed(2)} (${isBull ? '+' : ''}${changePct.toFixed(2)}%)`;
                changePill.className = `stock-change-pill ${isBull ? 'bullish' : 'bearish'}`;
            }
        }

        // Day Range & 52W Range Bars
        if (q.day_low && q.day_high && q.current_price) {
            window.setElText('dayLowVal', window.formatPrice(q.day_low, isINR));
            window.setElText('dayHighVal', window.formatPrice(q.day_high, isINR));
            const dayRangePct = Math.min(Math.max(((q.current_price - q.day_low) / (q.day_high - q.day_low)) * 100, 0), 100);
            const dayFill = document.getElementById('dayRangeFill');
            if (dayFill) dayFill.style.width = `${dayRangePct}%`;
        }

        if (q.week52_low && q.week52_high && q.current_price) {
            window.setElText('w52LowVal', window.formatPrice(q.week52_low, isINR));
            window.setElText('w52HighVal', window.formatPrice(q.week52_high, isINR));
            const w52RangePct = Math.min(Math.max(((q.current_price - q.week52_low) / (q.week52_high - q.week52_low)) * 100, 0), 100);
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
        const t = data.technicals || {};
        const q = data.quote || {};

        if (t.rsi_14 !== undefined) {
            window.setElText('kpiRsi', Number(t.rsi_14).toFixed(1));
            const rsiBadge = document.getElementById('kpiRsiBadge');
            if (rsiBadge) {
                rsiBadge.textContent = t.rsi_14 >= 70 ? 'Overbought' : t.rsi_14 <= 30 ? 'Oversold' : 'Neutral';
                rsiBadge.style.color = t.rsi_14 >= 70 ? '#fb7185' : t.rsi_14 <= 30 ? '#34d399' : '#8e97a8';
            }
        }

        if (t.dma_20) window.setElText('kpiDma20', window.formatPrice(t.dma_20));
        if (t.dma_50) window.setElText('kpiDma50', window.formatPrice(t.dma_50));
        if (t.dma_200) window.setElText('kpiDma200', window.formatPrice(t.dma_200));

        if (q.pe_ratio) window.setElText('kpiPe', `${Number(q.pe_ratio).toFixed(1)}x`);
        if (q.market_cap) window.setElText('kpiMarketCap', window.formatCrores(q.market_cap));
        if (q.volume) window.setElText('kpiVolume', window.formatVolume(q.volume));
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
