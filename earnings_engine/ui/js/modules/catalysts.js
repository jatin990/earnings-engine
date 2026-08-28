// =========================================================================
// 📰 Short-Term News Catalysts & Corporate Filings Frontend Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || '';

    const catalystsModule = {
        catalystsData: [],
        catalystsOutcomes: [],
        activeCatView: 'feed',
        activeCatUniverse: 'GLOBAL',

        switchCatalystsView(view) {
            this.activeCatView = view || 'feed';
            const feedView = document.getElementById('catalystsFeedView');
            const outcomesView = document.getElementById('catalystsOutcomesView');
            const feedBtn = document.getElementById('catViewFeedBtn');
            const outcomesBtn = document.getElementById('catViewOutcomesBtn');
            const scanBtn = document.getElementById('catScanBtn');
            const evalBtn = document.getElementById('catEvalOutcomesBtn');

            if (this.activeCatView === 'feed') {
                if (feedView) feedView.style.display = 'block';
                if (outcomesView) outcomesView.style.display = 'none';
                if (scanBtn) scanBtn.style.display = 'inline-flex';
                if (evalBtn) evalBtn.style.display = 'none';

                if (feedBtn) {
                    feedBtn.style.background = 'rgba(59, 130, 246, 0.2)';
                    feedBtn.style.color = '#60a5fa';
                    feedBtn.style.border = '1px solid rgba(59, 130, 246, 0.35)';
                    feedBtn.style.fontWeight = '700';
                }
                if (outcomesBtn) {
                    outcomesBtn.style.background = 'transparent';
                    outcomesBtn.style.color = '#a1a1aa';
                    outcomesBtn.style.border = '1px solid transparent';
                    outcomesBtn.style.fontWeight = '600';
                }
            } else {
                if (feedView) feedView.style.display = 'none';
                if (outcomesView) outcomesView.style.display = 'block';
                if (scanBtn) scanBtn.style.display = 'none';
                if (evalBtn) evalBtn.style.display = 'inline-flex';

                if (outcomesBtn) {
                    outcomesBtn.style.background = 'rgba(59, 130, 246, 0.2)';
                    outcomesBtn.style.color = '#60a5fa';
                    outcomesBtn.style.border = '1px solid rgba(59, 130, 246, 0.35)';
                    outcomesBtn.style.fontWeight = '700';
                }
                if (feedBtn) {
                    feedBtn.style.background = 'transparent';
                    feedBtn.style.color = '#a1a1aa';
                    feedBtn.style.border = '1px solid transparent';
                    feedBtn.style.fontWeight = '600';
                }
                this.loadCatalystsOutcomes();
            }
        },

        async loadCatalysts(universe = 'GLOBAL', days = 14) {
            this.activeCatUniverse = universe || 'GLOBAL';
            const tbody = document.getElementById('catalystsTableBody');
            const totalEl = document.getElementById('catStatTotal');
            try {
                const res = await fetch(API_BASE + `/api/v1/catalysts?watchlist_or_universe=${encodeURIComponent(this.activeCatUniverse)}&limit=200&days=${encodeURIComponent(days || 14)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.catalystsData = data.catalysts || [];
                    if (totalEl) totalEl.textContent = this.catalystsData.length;
                    this.renderCatalystsFeed(this.catalystsData);
                    if (typeof window.app?.updateSidebarBadges === 'function') {
                        window.app.updateSidebarBadges();
                    }
                }
            } catch (e) {
                console.error('[CATALYSTS] Failed loading news catalysts:', e);
                if (tbody) {
                    tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#f87171;">Failed loading news catalysts.</td></tr>';
                }
            }
        },

        renderCatalystsFeed(items) {
            const tbody = document.getElementById('catalystsTableBody');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No recent high-impact corporate catalysts found. Click "⚡ Scan Feeds" to fetch fresh announcements.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(c => {
                const isBull = c.direction === 'BULLISH';
                const isBear = c.direction === 'BEARISH';
                const dirBg = isBull ? 'rgba(16,185,129,0.15)' : (isBear ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.06)');
                const dirColor = isBull ? '#34d399' : (isBear ? '#f87171' : '#94a3b8');
                const dirBorder = isBull ? 'rgba(16,185,129,0.3)' : (isBear ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)');

                const sigPrice = (c.signal_price != null && c.signal_price > 0) ? '₹' + Number(c.signal_price).toFixed(1) : null;
                const curPrice = (c.current_price != null && c.current_price > 0) ? '₹' + Number(c.current_price).toFixed(1) : null;
                const chgPct = c.price_change_pct || 0;
                const chgColor = chgPct > 0 ? '#34d399' : (chgPct < 0 ? '#f87171' : '#94a3b8');
                const chgSign = chgPct > 0 ? '+' : '';
                const priceCell = (sigPrice && curPrice) 
                    ? `<div style="font-size:0.72rem;font-family:var(--font-mono);">${sigPrice} → <strong style="color:#38bdf8;">${curPrice}</strong> <span style="color:${chgColor};font-weight:700;">(${chgSign}${chgPct.toFixed(1)}%)</span></div>`
                    : (curPrice ? `<div style="font-size:0.72rem;font-family:var(--font-mono);color:#38bdf8;">${curPrice}</div>` : '<div style="color:#64748b;">—</div>');

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);transition:background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;">
                            <a href="/stock/${encodeURIComponent(c.ticker)}" target="_blank" style="color:#38bdf8;text-decoration:none;">${c.ticker} ↗</a>
                        </td>
                        <td style="padding:0.65rem 0.8rem;color:#f8fafc;font-weight:600;max-width:320px;">
                            <div>${c.title}</div>
                            ${c.summary ? `<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.2rem;">${c.summary.substring(0, 140)}...</div>` : ''}
                        </td>
                        <td style="padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.72rem;">${c.category || 'Corporate'}</td>
                        <td style="padding:0.65rem 0.8rem;">
                            ${priceCell}
                        </td>
                        <td style="padding:0.65rem 0.8rem;">
                            <span class="signal-badge" style="background:${dirBg};color:${dirColor};border:1px solid ${dirBorder};font-size:0.68rem;padding:0.12rem 0.45rem;">${c.direction || 'NEUTRAL'}</span>
                        </td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#38bdf8;">${c.impact_score || 50}/100</td>
                        <td style="padding:0.65rem 0.8rem;font-family:var(--font-mono);color:#64748b;font-size:0.7rem;">${c.published_at || c.published_date || c.detected_at || '—'}</td>
                        <td style="padding:0.65rem 0.8rem;text-align:center;">
                            <button type="button" onclick="app.openStockNote('${c.ticker}')" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:0.2rem 0.55rem;">Analysis</button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async scanCatalystsNow() {
            const btn = document.getElementById('catScanBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner" style="width:10px;height:10px;"></span> Scanning Feeds...';
            }
            try {
                await this.loadCatalysts(this.activeCatUniverse);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>⚡</span> Scan Feeds';
                }
            }
        },

        onCatWatchlistChange(val) {
            this.loadCatalysts(val);
        },

        async loadCatalystsOutcomes() {
            const tbody = document.getElementById('catalystsOutcomesTableBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">Loading post-catalyst trade outcomes...</td></tr>';
            try {
                const res = await fetch(API_BASE + '/api/v1/catalysts/outcomes');
                if (res.ok) {
                    const data = await res.json();
                    this.catalystsOutcomes = data.outcomes || [];
                    this.renderCatalystsOutcomes(this.catalystsOutcomes);
                }
            } catch (e) {
                console.error('[CATALYSTS] Failed loading outcomes:', e);
            }
        },

        renderCatalystsOutcomes(outcomes) {
            const tbody = document.getElementById('catalystsOutcomesTableBody');
            if (!tbody) return;
            if (!outcomes || !outcomes.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:#64748b;">No post-catalyst price outcomes verified yet. Outcomes verify automatically as trading days elapse.</td></tr>';
                return;
            }
            tbody.innerHTML = outcomes.map(o => {
                const ret = o.realized_return_pct;
                const retCol = ret > 0 ? '#34d399' : (ret < 0 ? '#f87171' : '#94a3b8');
                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:#f8fafc;">${o.ticker}</td>
                        <td style="padding:0.6rem 0.8rem;color:#cbd5e1;font-size:0.75rem;">${o.title}</td>
                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#94a3b8;font-size:0.72rem;">${o.signal_date}</td>
                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);">₹${o.signal_price}</td>
                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);">₹${o.current_price}</td>
                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);font-weight:700;color:${retCol};">${ret > 0 ? '+' : ''}${ret}%</td>
                        <td style="padding:0.6rem 0.8rem;font-family:var(--font-mono);color:#64748b;font-size:0.7rem;">${o.days_elapsed}d</td>
                    </tr>
                `;
            }).join('');
        },

        async evaluateNewsOutcomesNow() {
            const btn = document.getElementById('catEvalOutcomesBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = 'Verifying...';
            }
            try {
                await this.loadCatalystsOutcomes();
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>🎯</span> Re-Verify Outcomes';
                }
            }
        }
    };

    // Export module
    window.CatalystsModule = catalystsModule;
    if (window.app) {
        Object.assign(window.app, catalystsModule);
    }
})();
