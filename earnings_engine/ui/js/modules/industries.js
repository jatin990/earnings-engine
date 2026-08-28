// =========================================================================
// industries — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[industries] window.app not initialized'); return; }
    Object.assign(app, {
// ---------- Industries tab ----------

            industryColors: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#84cc16', '#f97316', '#ec4899', '#14b8a6', '#6366f1', '#d946ef', '#a3e635', '#0ea5e9', '#f43f5e', '#22c55e', '#eab308', '#38bdf8', '#fb7185', '#2dd4bf'],

            industryColor(name) {
                let h = 0;
                const s = String(name || '');
                for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
                return this.industryColors[h % this.industryColors.length];
            },

            async loadIndustryMoves() {
                const market = document.getElementById('indMarket').value;
                const lookback = document.getElementById('indLookback').value;
                const groupsEl = document.getElementById('indGroups');
                const statusEl = document.getElementById('indStatus');
                groupsEl.innerHTML = '<div class="card" style="margin:0">Loading industry moves...</div>';
                statusEl.textContent = '';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/industries?market=' + encodeURIComponent(market) + '&lookback_days=' + lookback);
                    const d = await res.json();
                    this.renderIndustryMoves(d);
                    statusEl.textContent = 'Loaded at ' + new Date().toLocaleTimeString() + ' · ' + d.total_results + ' results · ' + d.unclassified + ' unclassified';
                } catch (e) {
                    console.error('Error loading industry moves:', e);
                    groupsEl.innerHTML = '<div class="card" style="margin:0">Error loading industry moves</div>';
                }
            },

            renderIndustryMoves(d) {
                const summaryEl = document.getElementById('indSummary');
                const bestEl = document.getElementById('indBestBanner');
                const groupsEl = document.getElementById('indGroups');
                const industries = d.industries || [];
                const best = d.best_industry;
                const posInd = industries.filter(g => g.positive_count > 0).length;
                summaryEl.innerHTML = [
                    '<div class="metric"><span>Industries</span><strong>' + industries.length + '</strong></div>',
                    '<div class="metric"><span>Total Results</span><strong>' + (d.total_results || 0) + '</strong></div>',
                    '<div class="metric"><span>Industries w/ Gainers</span><strong>' + posInd + '</strong></div>',
                    '<div class="metric"><span>Unclassified</span><strong>' + (d.unclassified || 0) + '</strong></div>'
                ].join('');

                if (best) {
                    const bg = this.industryColor(best);
                    const bestGroup = industries.find(g => g.industry === best);
                    bestEl.innerHTML = '<div class="card" style="border:2px solid ' + bg + ';background:rgba(59,130,246,0.1);">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">🏆 BEST INDUSTRY BY POSITIVE RESULTS</span>' +
                        '<h3 style="margin:0.25rem 0;color:' + bg + ';">' + best + '</h3>' +
                        '<span class="timestamp">' + (bestGroup ? bestGroup.positive_count + ' positive / ' + bestGroup.count + ' results · avg high +' + bestGroup.avg_high_pct.toFixed(2) + '%' : '') + '</span>' +
                        '</div>';
                } else {
                    bestEl.innerHTML = '';
                }

                if (!industries.length) {
                    groupsEl.innerHTML = '<div class="card" style="margin:0">No past results in this window/universe.</div>';
                    return;
                }
                groupsEl.innerHTML = industries.map(g => {
                    const color = this.industryColor(g.industry);
                    const isBest = g.industry === best;
                    const rows = g.rows.map(r => {
                        const hp = r.high_pct !== null && r.high_pct !== undefined ? r.high_pct.toFixed(2) + '%' : '—';
                        const lp = r.low_pct !== null && r.low_pct !== undefined ? r.low_pct.toFixed(2) + '%' : '—';
                        const hcls = (r.high_pct !== null && r.high_pct > 0) ? 'price-positive' : ((r.high_pct !== null && r.high_pct < 0) ? 'price-negative' : '');
                        const lcls = (r.low_pct !== null && r.low_pct < 0) ? 'price-negative' : (r.low_pct !== null ? 'price-positive' : '');
                        return '<tr>' +
                            '<td><strong>' + r.ticker + '</strong></td>' +
                            '<td>' + r.earnings_date + '</td>' +
                            '<td class="' + hcls + '">' + hp + '</td>' +
                            '<td class="' + lcls + '">' + lp + '</td>' +
                            '</tr>';
                    }).join('');
                    return '<details class="card" style="border-left:4px solid ' + color + ';' + (isBest ? 'border:2px solid ' + color + ';background:rgba(59,130,246,0.06);' : '') + '" ' + (isBest ? 'open' : '') + '>' +
                        '<summary style="cursor:pointer;display:flex;align-items:center;gap:0.75rem;font-weight:600;font-size:1rem;">' +
                        '<span class="signal-badge" style="background:' + color + ';color:#fff;">&nbsp;</span>' +
                        '<span>' + g.industry + (isBest ? ' 🏆' : '') + '</span>' +
                        '<span class="timestamp" style="margin-left:auto;">' + g.positive_count + '/' + g.count + ' positive · avg +' + g.avg_high_pct.toFixed(2) + '%</span>' +
                        '</summary>' +
                        '<div class="table-wrapper" style="margin-top:0.75rem;">' +
                        '<table class="results-table"><thead><tr><th>Ticker</th><th>Result Date</th><th>7d High</th><th>7d Low</th></tr></thead>' +
                        '<tbody>' + rows + '</tbody></table></div>' +
                        '</details>';
                }).join('');
            },

            async classifyIndustries() {
                const btn = event.target;
                const original = btn.textContent;
                btn.disabled = true;
                btn.textContent = '⏳ Classifying...';
                const statusEl = document.getElementById('indStatus');
                statusEl.textContent = 'Fetching industry classifications from yfinance... this can take a while.';
                const market = document.getElementById('indMarket').value || 'ALL';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/industries/classify', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({market: market})
                    });
                    const data = await res.json();
                    if (data.success) {
                        statusEl.textContent = 'Classified ' + data.classified + '/' + data.total + ' tickers.';
                        await this.loadIndustryMoves();
                    } else {
                        statusEl.textContent = 'Failed: ' + (data.error || 'Unknown error');
                    }
                } catch (e) {
                    console.error('Error classifying industries:', e);
                    statusEl.textContent = 'Error: ' + e.message;
                } finally {
                    btn.disabled = false;
                    btn.textContent = original;
                }
            
    
        }
});
})(); // end industries IIFE
