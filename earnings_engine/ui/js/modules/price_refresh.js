// =========================================================================
// price_refresh — Nexus Dashboard Module
// Unified Global Live Ticks & Metric Auto-Refresh Architecture
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    // =========================================================================
    // ⏱️ Global Ticker Price Refresh Engine (Configurable Interval, Default 5m)
    // =========================================================================
    app._globalPriceRefreshTimer = null;
    app._lastGlobalPriceRefresh = null;
    app._visibilityBound = false;

    app.getGlobalPriceRefreshInterval = function() {
        const stored = localStorage.getItem('nexus_price_refresh_interval');
        if (stored !== null) {
            const parsed = parseInt(stored, 10);
            if (!isNaN(parsed)) return parsed;
        }
        if (window.APP_CONFIG && typeof window.APP_CONFIG.live_refresh_interval_sec === 'number') {
            return window.APP_CONFIG.live_refresh_interval_sec;
        }
        return 300; // 5 minutes default
    };

    app.initGlobalPriceRefresh = function() {
        const sec = this.getGlobalPriceRefreshInterval();
        const selectEl = document.getElementById('globalPriceRefreshSelect');
        if (selectEl) selectEl.value = String(sec);

        this.startGlobalPriceRefreshLoop(sec);
        this.syncSubmoduleIntervals(sec);

        // Resume refresh when tab becomes visible if stale
        if (!this._visibilityBound && typeof document !== 'undefined') {
            this._visibilityBound = true;
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible') {
                    const currentSec = this.getGlobalPriceRefreshInterval();
                    if (currentSec > 0 && this._lastGlobalPriceRefresh) {
                        const elapsedSec = (Date.now() - this._lastGlobalPriceRefresh.getTime()) / 1000;
                        if (elapsedSec >= currentSec) {
                            this.triggerGlobalPriceRefresh(false);
                        }
                    }
                }
            });

            window.addEventListener('online', () => {
                this.triggerGlobalPriceRefresh(false);
            });
        }
    };

    app.syncSubmoduleIntervals = function(sec) {
        const ms = sec > 0 ? sec * 1000 : 300000;
        if (this.watchlistTab && typeof this.watchlistTab.setLiveInterval === 'function') {
            const wlSel = document.getElementById('wlLiveIntervalSelect');
            if (wlSel) wlSel.value = String(ms);
            this.watchlistTab.liveIntervalMs = ms;
        }
        if (typeof this.setBreakoutLiveInterval === 'function') {
            const boSel = document.getElementById('breakoutLiveIntervalSelect');
            if (boSel) boSel.value = String(ms);
            this.breakoutLiveIntervalMs = ms;
        }
    };

    app.setGlobalPriceRefreshInterval = function(secondsStr) {
        const seconds = parseInt(secondsStr, 10) || 0;
        localStorage.setItem('nexus_price_refresh_interval', String(seconds));
        const selectEl = document.getElementById('globalPriceRefreshSelect');
        if (selectEl && selectEl.value !== String(seconds)) selectEl.value = String(seconds);

        this.startGlobalPriceRefreshLoop(seconds);
        this.syncSubmoduleIntervals(seconds);

        const label = seconds === 0 ? 'Manual (Auto-refresh Off)' : `${Math.round(seconds / 60)} min${seconds > 60 ? 's' : ''}`;
        if (typeof this.showToast === 'function') {
            this.showToast(`⏱️ Price refresh interval set to ${label}`, 'success');
        }
    };

    app.startGlobalPriceRefreshLoop = function(intervalSeconds) {
        if (this._globalPriceRefreshTimer) {
            clearInterval(this._globalPriceRefreshTimer);
            this._globalPriceRefreshTimer = null;
        }
        const sec = (intervalSeconds !== undefined) ? intervalSeconds : this.getGlobalPriceRefreshInterval();
        if (sec > 0) {
            this._globalPriceRefreshTimer = setInterval(() => {
                if (typeof document === 'undefined' || document.visibilityState === 'visible') {
                    this.triggerGlobalPriceRefresh(false);
                }
            }, sec * 1000);
        }
    };

    app.triggerGlobalPriceRefresh = async function(manual = false) {
        const btn = document.getElementById('topRefreshPricesBtn');
        if (btn) {
            btn.style.animation = 'spin 1s linear infinite';
            btn.disabled = true;
        }
        try {
            const activeTab = this.currentTab || window.app?.currentTab || 'home';

            // Dispatch live refresh based on active screen
            if (activeTab === 'home' || activeTab === 'pulse') {
                if (typeof this.loadMarketPulseData === 'function') await this.loadMarketPulseData();
                else if (typeof this.loadPulseData === 'function') await this.loadPulseData();
            } else if (activeTab === 'results' || activeTab === 'upcoming') {
                if (typeof this.updateResultsMonthSummaryCards === 'function') this.updateResultsMonthSummaryCards();
                if (typeof this.loadUpcoming === 'function') await this.loadUpcoming();
            } else if (activeTab === 'monthfilter') {
                if (typeof this.loadMonthFilter === 'function') await this.loadMonthFilter();
                else if (typeof this.loadResultsMonthView === 'function') await this.loadResultsMonthView();
            } else if (activeTab === 'scanner' || activeTab === 'category') {
                if (typeof this.loadScanner === 'function') await this.loadScanner();
                else if (typeof this.loadCategoryScanner === 'function') await this.loadCategoryScanner();
            } else if (activeTab === 'catalysts') {
                if (typeof this.loadCatalysts === 'function') await this.loadCatalysts();
                if (typeof this.loadAutomationSchedules === 'function') this.loadAutomationSchedules();
            } else if (activeTab === 'premarket') {
                if (typeof this.loadPremarketSetups === 'function') await this.loadPremarketSetups();
            } else if (activeTab === 'gainers') {
                if (typeof this.refreshGainersTab === 'function') await this.refreshGainersTab();
                else if (typeof this.loadGainers === 'function') await this.loadGainers();
            } else if (activeTab === 'breakout') {
                if (this._activeBreakoutSubtab === 'tracked' && typeof this.loadTrackedBreakouts === 'function') {
                    await this.loadTrackedBreakouts();
                } else if (typeof this.loadBreakoutRadar === 'function') {
                    await this.loadBreakoutRadar(true, true);
                }
                if (typeof this.loadAutomationSchedules === 'function') this.loadAutomationSchedules();
            } else if (activeTab === 'institutional' || activeTab === 'super-investor') {
                if (typeof this.loadInstitutionalFlows === 'function') await this.loadInstitutionalFlows();
            } else if (activeTab === 'tri-confluence' || activeTab === 'confluence') {
                if (typeof this.loadTriConfluence === 'function') await this.loadTriConfluence();
                else if (typeof this.loadConfluence === 'function') await this.loadConfluence();
            } else if (activeTab === 'repeaters') {
                if (typeof this.loadQuarterRepeaters === 'function') await this.loadQuarterRepeaters();
            } else if (activeTab === 'new-additions') {
                if (typeof this.loadRecentAdditions === 'function') await this.loadRecentAdditions();
            } else if (activeTab === 'swing') {
                if (typeof this.loadSwingRanges === 'function') await this.loadSwingRanges();
            } else if (activeTab === 'watchlist') {
                if (typeof this.loadWatchlist === 'function') await this.loadWatchlist();
                if (typeof this.watchlistTab?.loadActiveQuotes === 'function') await this.watchlistTab.loadActiveQuotes(true, true);
            } else if (activeTab === 'kronos') {
                if (typeof this.loadKronosLatest === 'function') await this.loadKronosLatest();
            } else if (activeTab === 'consensus') {
                if (typeof this.loadConsensus === 'function') await this.loadConsensus();
            } else if (activeTab === 'buydip' || activeTab === 'recent-results') {
                if (typeof this.loadRecentResults === 'function') await this.loadRecentResults();
                else if (typeof this.loadBuyDip === 'function') await this.loadBuyDip();
            } else if (activeTab === 'coverage') {
                if (typeof this.loadCoverage === 'function') await this.loadCoverage();
            } else if (activeTab === 'industries') {
                if (typeof this.loadIndustries === 'function') await this.loadIndustries();
            } else if (activeTab === 'patterns') {
                if (typeof this.loadPatterns === 'function') await this.loadPatterns();
            } else if (activeTab === 'allstocks') {
                if (typeof this.loadAllStocks === 'function') await this.loadAllStocks();
            } else if (activeTab === 'playground') {
                if (typeof this.loadPlaygroundApiUsage === 'function') this.loadPlaygroundApiUsage();
                if (typeof this.loadAutomationSchedules === 'function') this.loadAutomationSchedules();
            }

            // Also refresh active open stock modal quote if visible
            const modal = document.getElementById('stockDetailModal');
            if (modal && modal.style.display !== 'none' && this.currentModalTicker) {
                if (typeof this.refreshStockModalLivePrice === 'function') {
                    this.refreshStockModalLivePrice(this.currentModalTicker);
                }
            }

            this._lastGlobalPriceRefresh = new Date();
            if (manual && typeof this.showToast === 'function') {
                this.showToast('🟢 Ticker prices refreshed across active page', 'success');
            }
        } catch (e) {
            console.debug('[PRICE-REFRESH] Auto-refresh error:', e);
        } finally {
            if (btn) {
                btn.style.animation = '';
                btn.disabled = false;
            }
        }
    };

})(); // end price_refresh IIFE
