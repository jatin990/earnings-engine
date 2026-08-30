// =========================================================================
// sidebar_badges — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// Handles: sidebar badge counts (catalysts, breakouts, gainers)
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
app.updateSidebarBadges = async function() {
            try {
                const res = await fetch(API_BASE + '/api/v1/sidebar/badges');
                if (res.ok) {
                    const data = await res.json();

                    // 1. High-Impact Catalysts (>70% impact)
                    const catBadge = document.getElementById('sidebarCatalystCountBadge');
                    const catCount = data.high_impact_news_70 || data.catalysts_count || 0;
                    if (catBadge) {
                        if (catCount > 0) {
                            catBadge.textContent = catCount > 99 ? '99+' : String(catCount);
                            catBadge.style.display = 'inline-block';
                        } else {
                            catBadge.style.display = 'none';
                        }
                    }

                    // 2. Pre-Market Setups (>70% impact news & filings)
                    const pmBadge = document.getElementById('sidebarPremarketCountBadge');
                    const pmCount = data.premarket_high_impact_70 || data.premarket_count || 0;
                    if (pmBadge) {
                        if (pmCount > 0) {
                            pmBadge.textContent = pmCount > 99 ? '99+' : String(pmCount);
                            pmBadge.style.display = 'inline-block';
                        } else {
                            pmBadge.style.display = 'none';
                        }
                    }

                    // 3. Active Breakout Setups & Candidates
                    const boBadge = document.getElementById('sidebarBreakoutCountBadge');
                    const boCount = data.active_breakouts ?? data.breakouts_count ?? 0;
                    if (boBadge) {
                        if (boCount > 0) {
                            boBadge.textContent = boCount > 99 ? '99+' : String(boCount);
                            boBadge.style.display = 'inline-block';
                        } else {
                            boBadge.style.display = 'none';
                        }
                    }

                    // 4. Gainers & Momentum Breakouts badge
                    const gainerBadge = document.getElementById('sidebarGainersCountBadge');
                    const gainerCount = data.active_gainers ?? data.gainers_count ?? boCount;
                    if (gainerBadge) {
                        if (gainerCount > 0) {
                            gainerBadge.textContent = gainerCount > 99 ? '99+' : String(gainerCount);
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

    // Auto-refresh sidebar badges every 45 seconds
    try {
        app.updateSidebarBadges();
        setInterval(() => {
            if (typeof app.updateSidebarBadges === 'function') {
                app.updateSidebarBadges();
            }
        }, 45000);
    } catch (e) {
        console.warn('[sidebar_badges] Initial badge fetch error:', e);
    }

})(); // end sidebar_badges IIFE
