// =========================================================================
// stock_modal — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
// ========================================================
        // 🚀 FULL SCREEN STOCK INTELLIGENCE MODAL CONTROLLER
        // ========================================================
        app.activeStockModalTicker = null;

        app.openStockModal = function (ticker, hash = '') {
            if (!ticker) return;
            const sym = String(ticker).trim().toUpperCase();
            app.activeStockModalTicker = sym;

            const modal = document.getElementById('stockFullScreenModal');
            const tickerEl = document.getElementById('stockModalTicker');
            const nameEl = document.getElementById('stockModalName');
            const spinner = document.getElementById('stockModalSpinner');
            const iframe = document.getElementById('stockModalIframe');

            if (!modal || !iframe) {
                // Fallback if modal container is not rendered
                window.open('/stock/' + encodeURIComponent(sym) + (hash ? (hash.startsWith('#') ? hash : '#' + hash) : ''), '_blank');
                return;
            }

            if (tickerEl) tickerEl.textContent = sym;
            if (nameEl) nameEl.textContent = 'Loading live financials & AI consensus...';
            if (spinner) spinner.style.display = 'flex';

            const cleanHash = hash ? (hash.startsWith('#') ? hash : '#' + hash) : '';
            const targetUrl = '/stock/' + encodeURIComponent(sym) + cleanHash;

            iframe.src = targetUrl;
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';

            // Attempt to fetch company name & live price for top bar
            try {
                fetch(`/api/v1/stock/${encodeURIComponent(sym)}/overview`)
                    .then(r => r.ok ? r.json() : null)
                    .then(data => {
                        if (data && nameEl && app.activeStockModalTicker === sym) {
                            const name = data.company_name || data.short_name || 'Stock Intelligence';
                            const pStr = data.current_price ? ` · ₹${Number(data.current_price).toFixed(2)}` : '';
                            nameEl.textContent = `${name}${pStr}`;
                        }
                    })
                    .catch(() => {});
            } catch (_) {}
        };

        app.closeStockModal = function () {
            const modal = document.getElementById('stockFullScreenModal');
            const iframe = document.getElementById('stockModalIframe');
            if (modal) modal.style.display = 'none';
            if (iframe) iframe.src = 'about:blank';
            document.body.style.overflow = '';
            app.activeStockModalTicker = null;
        };

        app.navStockModal = function (hash) {
            const iframe = document.getElementById('stockModalIframe');
            if (!iframe || !app.activeStockModalTicker) return;
            const cleanHash = hash.startsWith('#') ? hash : '#' + hash;
            if (iframe.contentWindow) {
                try {
                    iframe.contentWindow.location.hash = cleanHash;
                    return;
                } catch (_) {}
            }
            iframe.src = '/stock/' + encodeURIComponent(app.activeStockModalTicker) + cleanHash;
        };

        app.refreshStockModal = function () {
            const iframe = document.getElementById('stockModalIframe');
            const spinner = document.getElementById('stockModalSpinner');
            if (iframe && app.activeStockModalTicker) {
                if (spinner) spinner.style.display = 'flex';
                iframe.src = iframe.src;
            }
        };

        app.openStockInNewTab = function () {
            if (app.activeStockModalTicker) {
                window.open('/stock/' + encodeURIComponent(app.activeStockModalTicker), '_blank');
            }
        };

        window.openStockModal = app.openStockModal;
        window.closeStockModal = app.closeStockModal;
        window.openStockPage = app.openStockModal;

        // Global Esc Key Listener for Full Screen Stock Modal
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                const modal = document.getElementById('stockFullScreenModal');
                if (modal && modal.style.display !== 'none') {
                    app.closeStockModal();
                }
            }
        });

        // Global Stock Link Interceptor across the Entire Dashboard
        document.addEventListener('click', function (e) {
            const link = e.target.closest('a[href^="/stock/"]');
            if (link) {
                const href = link.getAttribute('href') || '';
                const match = href.match(/\/stock\/([^/?#]+)(#.*)?/);
                if (match && match[1]) {
                    e.preventDefault();
                    e.stopPropagation();
                    const rawTicker = decodeURIComponent(match[1]);
                    const hash = match[2] || '';
                    app.openStockModal(rawTicker, hash);
                }
            }
        }, true);

        // Merge all modular hub modules
        if (window.institutionalModule) Object.assign(app, window.institutionalModule);
        if (window.marketPulseModule) Object.assign(app, window.marketPulseModule);
        if (window.schedulesModule || window.SchedulesModule) Object.assign(app, window.schedulesModule || window.SchedulesModule);
        if (window.newAdditionsModule) Object.assign(app, window.newAdditionsModule);
        if (window.catalystsModule) Object.assign(app, window.catalystsModule);
        if (window.premarketModule || window.PremarketModule) Object.assign(app, window.premarketModule || window.PremarketModule);
        if (window.consensusModule) Object.assign(app, window.consensusModule);
        if (window.swingModule) Object.assign(app, window.swingModule);

        // Update Sidebar Navigation Count Badges (Catalysts >50% impact & Breakout candidates)
        app.updateSidebarBadges = async function() {
            try {
                const res = await fetch(API_BASE + '/api/v1/sidebar/badges');
                if (res.ok) {
                    const data = await res.json();

                    // 1. High-Impact Catalysts (>50% impact)
                    const catBadge = document.getElementById('sidebarCatalystCountBadge');
                    const catCount = data.catalysts_count || data.high_impact_catalysts || 0;
                    if (catBadge) {
                        if (catCount > 0) {
                            catBadge.textContent = catCount > 99 ? '99+' : String(catCount);
                            catBadge.style.display = 'inline-block';
                        } else {
                            catBadge.style.display = 'none';
                        }
                    }

                    // 2. Active Breakout Setups & Candidates
                    const boBadge = document.getElementById('sidebarBreakoutCountBadge');
                    const boCount = data.breakouts_count || data.active_breakouts || 0;
                    if (boBadge) {
                        if (boCount > 0) {
                            boBadge.textContent = boCount > 99 ? '99+' : String(boCount);
                            boBadge.style.display = 'inline-block';
                        } else {
                            boBadge.style.display = 'none';
                        }
                    }

                    // 3. Gainers / Breakouts badge
                    const gainerBadge = document.getElementById('sidebarGainersCountBadge');
                    if (gainerBadge) {
                        if (boCount > 0) {
                            gainerBadge.textContent = boCount > 99 ? '99+' : String(boCount);
                            gainerBadge.style.display = 'inline-block';
                        } else {
                            gainerBadge.style.display = 'none';
                        }
                    }
                }
            } catch (e) {
                console.debug('[SIDEBAR-BADGES] Error updating sidebar count badges:', e);
            }
        };

})(); // end stock_modal IIFE
