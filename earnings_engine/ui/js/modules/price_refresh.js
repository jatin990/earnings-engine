// =========================================================================
// price_refresh — Nexus Dashboard Module
// Unified Global Live Ticks & Metric Auto-Refresh Architecture
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app._lastGlobalPriceRefresh = null;

    /**
     * Inspect active tab/container and return unique visible stock tickers.
     */
    app.getVisibleTickersOnActiveTab = function() {
        const activeTab = this.currentTab || window.app?.currentTab || 'home';
        const container = document.getElementById('tab-' + activeTab) || document.querySelector('.tab-content.active') || document.body;
        const tickerSet = new Set();

        // 1. Elements with explicit data-ticker attribute
        container.querySelectorAll('[data-ticker]').forEach(el => {
            if (el.offsetParent !== null || el.style.display !== 'none') {
                const t = el.getAttribute('data-ticker');
                if (t && t.length > 1 && !t.includes('{')) tickerSet.add(t.trim().toUpperCase());
            }
        });

        // 2. Links to stock profile /stock/XYZ
        container.querySelectorAll('a[href*="/stock/"]').forEach(a => {
            if (a.offsetParent !== null) {
                const match = a.getAttribute('href').match(/\/stock\/([^\/\?#]+)/);
                if (match && match[1]) {
                    const sym = decodeURIComponent(match[1]).trim().toUpperCase();
                    if (sym && sym.length > 1 && !sym.includes('{')) tickerSet.add(sym);
                }
            }
        });

        // 3. Ticker elements with common class names
        container.querySelectorAll('.stock-ticker-main, .ticker-symbol').forEach(el => {
            if (el.offsetParent !== null) {
                const txt = el.textContent.trim().replace(/^▶\s*/, '').trim().toUpperCase();
                if (txt && txt.length > 1 && !txt.includes(' ') && !txt.includes('{')) {
                    tickerSet.add(txt);
                }
            }
        });

        return Array.from(tickerSet).slice(0, 100);
    };

    /**
     * Trigger global price & metric refresh across the active screen.
     */
    app.triggerGlobalPriceRefresh = async function(manual = false) {
        const btn = document.getElementById('topRefreshPricesBtn');
        const iconEl = btn ? (btn.querySelector('#topRefreshPricesIcon') || btn.querySelector('.refresh-icon')) : null;
        const textEl = btn ? btn.querySelector('#topRefreshPricesText') : null;
        const originalText = textEl ? textEl.textContent : '';

        if (btn) {
            btn.disabled = true;
            btn.style.animation = '';
        }
        if (iconEl) iconEl.style.animation = 'spin 0.8s linear infinite';
        if (textEl) textEl.textContent = 'Refreshing...';

        try {
            const activeTab = this.currentTab || window.app?.currentTab || 'home';

            // 1. Gather all visible tickers on the active tab and batch update prices/metrics
            const visibleTickers = typeof this.getVisibleTickersOnActiveTab === 'function'
                ? this.getVisibleTickersOnActiveTab()
                : [];

            if (visibleTickers.length > 0 && typeof this.refreshStocksBatch === 'function') {
                await this.refreshStocksBatch(visibleTickers, btn);
            }

            // 2. Dispatch page-specific data refresh based on temporal freshness rules
            if (activeTab === 'home' || activeTab === 'pulse') {
                if (typeof this.loadMarketPulseData === 'function') await this.loadMarketPulseData();
                else if (typeof this.loadPulseData === 'function') await this.loadPulseData();
            } else if (activeTab === 'results' || activeTab === 'upcoming') {
                if (typeof this.updateResultsMonthSummaryCards === 'function') this.updateResultsMonthSummaryCards();
                if (typeof this.loadResultsReport === 'function') await this.loadResultsReport();
            } else if (activeTab === 'monthfilter') {
                if (typeof this.loadMonthFilterTab === 'function') await this.loadMonthFilterTab(true);
                else if (typeof this.loadMonthFilter === 'function') await this.loadMonthFilter();
            } else if (activeTab === 'scanner' || activeTab === 'category') {
                if (typeof this.loadScanner === 'function') await this.loadScanner();
            } else if (activeTab === 'catalysts') {
                if (typeof this.loadCatalysts === 'function') await this.loadCatalysts();
            } else if (activeTab === 'premarket') {
                if (typeof this.refreshPremarketQuotes === 'function') await this.refreshPremarketQuotes();
                else if (typeof this.loadPremarketSetups === 'function') await this.loadPremarketSetups();
            } else if (activeTab === 'gainers') {
                if (typeof this.refreshGainersTab === 'function') await this.refreshGainersTab();
                else if (typeof this.loadGainers === 'function') await this.loadGainers();
            } else if (activeTab === 'breakout') {
                if (this._activeBreakoutSubtab === 'tracked' && typeof this.loadTrackedBreakouts === 'function') {
                    await this.loadTrackedBreakouts(true);
                } else if (typeof this.loadBreakoutRadar === 'function') {
                    await this.loadBreakoutRadar(true, true);
                }
            } else if (activeTab === 'institutional' || activeTab === 'super-investor') {
                if (this._institutionalSubpage === 'smart-money' && typeof this.loadSmartMoneyRadar === 'function') {
                    await this.loadSmartMoneyRadar(true);
                } else if (typeof this.loadInstitutionalData === 'function') {
                    await this.loadInstitutionalData();
                }
            } else if (activeTab === 'tri-confluence' || activeTab === 'confluence') {
                if (typeof this.loadTriConfluence === 'function') await this.loadTriConfluence(true);
            } else if (activeTab === 'repeaters') {
                if (typeof this.loadQuarterRepeaters === 'function') await this.loadQuarterRepeaters(true);
            } else if (activeTab === 'new-additions') {
                if (typeof this.loadRecentAdditions === 'function') await this.loadRecentAdditions(true);
            } else if (activeTab === 'swing') {
                if (typeof this.loadSwing === 'function') await this.loadSwing();
            } else if (activeTab === 'watchlist') {
                if (typeof this.watchlistTab?.loadActiveQuotes === 'function') {
                    await this.watchlistTab.loadActiveQuotes(true, true);
                } else if (typeof this.loadWatchlist === 'function') {
                    await this.loadWatchlist();
                }
            } else if (activeTab === 'options') {
                if (typeof this.loadOptionChain === 'function') await this.loadOptionChain(true);
            } else if (activeTab === 'kronos') {
                if (typeof this.loadKronosLatest === 'function') await this.loadKronosLatest();
            } else if (activeTab === 'consensus') {
                if (typeof this.loadConsensusTab === 'function') await this.loadConsensusTab();
            } else if (activeTab === 'buydip' || activeTab === 'recent-results') {
                if (typeof this.loadRecentResults === 'function') await this.loadRecentResults();
                else if (typeof this.loadBuyDip === 'function') await this.loadBuyDip();
            } else if (activeTab === 'coverage') {
                if (typeof this.loadDataCoverage === 'function') await this.loadDataCoverage();
            } else if (activeTab === 'industries') {
                if (typeof this.loadIndustryMoves === 'function') await this.loadIndustryMoves();
            } else if (activeTab === 'patterns') {
                if (typeof this.loadPatterns === 'function') await this.loadPatterns();
            }

            // 3. Refresh active open stock detail modal if currently displayed
            const modal = document.getElementById('stockDetailModal');
            if (modal && modal.style.display !== 'none' && this.currentModalTicker) {
                if (typeof this.refreshStockModalLivePrice === 'function') {
                    this.refreshStockModalLivePrice(this.currentModalTicker);
                }
            }

            this._lastGlobalPriceRefresh = new Date();
            if (manual && typeof this.showToast === 'function') {
                this.showToast('🟢 Live prices & technical metrics refreshed', 'success');
            }
        } catch (e) {
            console.error('[PRICE-REFRESH] Refresh error:', e);
            if (typeof this.showToast === 'function') {
                this.showToast('⚠️ Error refreshing prices: ' + e.message, 'error');
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.style.animation = '';
            }
            const liveIcon = btn ? (btn.querySelector('#topRefreshPricesIcon') || btn.querySelector('.refresh-icon')) : document.getElementById('topRefreshPricesIcon');
            if (liveIcon) liveIcon.style.animation = '';
            const liveText = btn ? btn.querySelector('#topRefreshPricesText') : document.getElementById('topRefreshPricesText');
            if (liveText) liveText.textContent = originalText || 'Refresh Prices';
        }
    };

})(); // end price_refresh IIFE
