// =========================================================================
// price_refresh — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
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

        app.initGlobalPriceRefresh = function() {
            const stored = localStorage.getItem('nexus_price_refresh_interval') || '300';
            const selectEl = document.getElementById('globalPriceRefreshSelect');
            if (selectEl) selectEl.value = stored;
            this.startGlobalPriceRefreshLoop(parseInt(stored, 10));
        };

        app.setGlobalPriceRefreshInterval = function(secondsStr) {
            const seconds = parseInt(secondsStr, 10) || 0;
            localStorage.setItem('nexus_price_refresh_interval', String(seconds));
            const selectEl = document.getElementById('globalPriceRefreshSelect');
            if (selectEl && selectEl.value !== String(seconds)) selectEl.value = String(seconds);
            this.startGlobalPriceRefreshLoop(seconds);
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
            const sec = (intervalSeconds !== undefined) ? intervalSeconds : (parseInt(localStorage.getItem('nexus_price_refresh_interval') || '300', 10) || 300);
            if (sec > 0) {
                this._globalPriceRefreshTimer = setInterval(() => {
                    this.triggerGlobalPriceRefresh(false);
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
                if (activeTab === 'catalysts') {
                    await this.loadCatalysts();
                } else if (activeTab === 'breakout') {
                    if (typeof this.loadBreakoutRadar === 'function') await this.loadBreakoutRadar();
                } else if (activeTab === 'gainers') {
                    if (typeof this.loadGainers === 'function') await this.loadGainers();
                } else if (activeTab === 'watchlist') {
                    if (typeof this.loadWatchlist === 'function') await this.loadWatchlist();
                    if (typeof this.watchlistTab?.loadActiveQuotes === 'function') await this.watchlistTab.loadActiveQuotes();
                } else if (activeTab === 'swing') {
                    if (typeof this.loadSwingRanges === 'function') await this.loadSwingRanges();
                } else if (activeTab === 'home') {
                    if (typeof this.loadPulseData === 'function') await this.loadPulseData();
                } else if (activeTab === 'results' || activeTab === 'monthfilter') {
                    if (typeof this.loadUpcoming === 'function') await this.loadUpcoming();
                } else if (activeTab === 'institutional') {
                    if (typeof this.loadInstitutionalFlows === 'function') await this.loadInstitutionalFlows();
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
