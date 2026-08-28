// =========================================================================
// patterns — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[patterns] window.app not initialized'); return; }
    Object.assign(app, {
// ---------- Patterns tab ----------

            _restorePatternsControls() {
                try {
                    const start = localStorage.getItem('patStartDate');
                    const end = localStorage.getItem('patEndDate');
                    if (start != null) document.getElementById('patStartDate').value = start;
                    if (end != null) document.getElementById('patEndDate').value = end;
                } catch (e) { /* ignore */ }
            },

            async loadPatterns() {
                const market = document.getElementById('patternsMarket').value;
                const start = document.getElementById('patStartDate').value || '';
                const end = document.getElementById('patEndDate').value || '';
                const statusEl = document.getElementById('patStatus');
                const summaryEl = document.getElementById('patSummary');
                try {
                    localStorage.setItem('patStartDate', start);
                    localStorage.setItem('patEndDate', end);
                } catch (e) { /* ignore */ }
                summaryEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0;color:var(--muted)">Loading patterns...</div>';
                const q = new URLSearchParams({ market: market });
                if (start) q.set('start_date', start);
                if (end) q.set('end_date', end);
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/patterns?' + q.toString());
                    const d = await res.json();
                    this.renderPatterns(d);
                    statusEl.textContent = 'Loaded at ' + new Date().toLocaleTimeString() + ' — range: ' + (start || 'recent') + ' → ' + (end || 'today');
                } catch (e) {
                    console.error('Error loading patterns:', e);
                    statusEl.textContent = 'Error loading patterns.';
                }
            },

            applyPatternsPreset() {
                const days = document.getElementById('patPreset').value;
                const iso = (d) => d.toISOString().split('T')[0];
                if (!days) {
                    document.getElementById('patStartDate').value = '';
                    document.getElementById('patEndDate').value = '';
                } else {
                    const end = new Date();
                    const start = new Date();
                    start.setDate(start.getDate() - parseInt(days, 10));
                    document.getElementById('patStartDate').value = iso(start);
                    document.getElementById('patEndDate').value = iso(end);
                }
                this.loadPatterns();
            },


            renderPatterns(d) {
                const summaryEl = document.getElementById('patSummary');
                const todayEl = document.getElementById('patTodayCards');
                const dipEl = document.getElementById('patDip');
                const keptEl = document.getElementById('patKept');
                const indEl = document.getElementById('patIndustries');
                const bestPos = d.best_positive_industry || {};
                const bestRatio = d.best_ratio_industry || {};
                summaryEl.innerHTML = [
                    '<div class="metric"><span>Total Results</span><strong>' + (d.total || 0) + '</strong></div>',
                    '<div class="metric"><span>Positive</span><strong class="price-positive">' + (d.positive || 0) + '</strong></div>',
                    '<div class="metric"><span>Negative</span><strong class="price-negative">' + (d.negative || 0) + '</strong></div>',
                    '<div class="metric"><span>Dipped → Comeback ≥50%</span><strong>' + (d.comeback_50_total || 0) + '</strong></div>',
                    '<div class="metric"><span>Kept Dipping</span><strong class="price-negative">' + (d.kept_dipping_total || 0) + '</strong></div>',
                    '<div class="metric"><span>Best Positive Industry</span><strong>' + (bestPos.industry || '—') + ' (' + (bestPos.positive || 0) + ')</strong></div>',
                    '<div class="metric"><span>Best Ratio Industry</span><strong>' + (bestRatio.industry || '—') + ' (' + (bestRatio.ratio || 0) + ')</strong></div>'
                ].join('');

                // Today's earnings summary cards
                const todayCount = d.today_count || 0;
                const todayPos = d.today_positive || 0;
                const todayCb = d.today_came_back || 0;
                const todayNr = d.today_no_recovery || 0;
                todayEl.innerHTML = [
                    '<div class="metric"><span>Today\'s Earnings</span><strong>' + todayCount + '</strong></div>',
                    '<div class="metric"><span>Today Positive</span><strong class="price-positive">' + todayPos + '</strong></div>',
                    '<div class="metric"><span>Today Comeback≥50%</span><strong>' + todayCb + '</strong></div>',
                    '<div class="metric"><span>Today No Recovery</span><strong class="price-negative">' + todayNr + '</strong></div>'
                ].join('');

                dipEl.innerHTML = d.total
                    ? '<div class="card" style="border:2px solid #f59e0b;background:rgba(245,158,11,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">📉 → 📈 POSITIVE RESULTS THAT DIPPED THEN RECOVERED</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;">positive & dipped: ' + (d.positive_dipped_total || 0) + '</span>' +
                        '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#10b981;">recovered ≥ 50% of drop: ' + (d.comeback_50_total || 0) + '</span>' +
                        '</div></div>'
                    : '';

                const kept = (d.rows || []).filter(r => r.kept_dipping);
                keptEl.innerHTML = kept.length
                    ? '<div class="card" style="border:2px solid #ef4444;background:rgba(239,68,68,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">🔻 GOOD RESULTS THAT KEPT DIPPING</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        kept.map(r => '<span class="signal-badge" style="background:rgba(239,68,68,0.2);color:#ef4444;">' + r.ticker + ' (' + (r.industry || '—') + ')</span>').join('') +
                        '</div></div>'
                    : '';

                const industries = d.industries || [];
                if (!industries.length) {
                    indEl.innerHTML = '<div class="card" style="margin:0">No results in the selected range.</div>';
                    return;
                }
                const rowsHtml = industries.map(x =>
                    '<tr>' +
                    '<td>' + (x.industry || '—') + '</td>' +
                    '<td>' + x.total + '</td>' +
                    '<td class="price-positive">' + x.positive + '</td>' +
                    '<td class="price-negative">' + x.negative + '</td>' +
                    '<td>' + x.stocks + '</td>' +
                    '<td>' + (x.ratio || 0) + '</td>' +
                    '<td>' + x.positive_dipped + '</td>' +
                    '<td class="price-positive">' + x.comeback_50 + '</td>' +
                    '<td class="price-negative">' + x.kept_dipping + '</td>' +
                    '</tr>'
                ).join('');
                indEl.innerHTML = '<div class="table-wrapper"><table class="results-table">' +
                    '<thead><tr><th>Industry</th><th>Results</th><th>Positive</th><th>Negative</th><th>Stocks</th><th>Ratio</th><th>Dipped</th><th>Comeback≥50%</th><th>Kept Dipping</th></tr></thead>' +
                    '<tbody>' + rowsHtml + '</tbody></table></div>';

                // Today's per-stock table (sortable).
                this._patTodayRows = (d.rows || []).filter(r => r.is_today);
                this.patStocksSortKey = 'ticker';
                this.patStocksSortDir = 'asc';
                this.renderPatStocksTable();
            },

            renderPatStocksTable() {
                const tbody = document.getElementById('patStocksTable');
                const rows = this._patTodayRows || [];
                if (!rows.length) {
                    tbody.innerHTML = '<tr><td colspan="13" style="padding:1rem;text-align:center;color:var(--muted)">No earnings today in the selected range.</td></tr>';
                    return;
                }
                const sorted = [...rows].sort((a, b) => {
                    let va = a[this.patStocksSortKey], vb = b[this.patStocksSortKey];
                    if (typeof va === 'string') va = va.toLowerCase();
                    if (typeof vb === 'string') vb = vb.toLowerCase();
                    if (va == null) va = '';
                    if (vb == null) vb = '';
                    if (va < vb) return this.patStocksSortDir === 'asc' ? -1 : 1;
                    if (va > vb) return this.patStocksSortDir === 'asc' ? 1 : -1;
                    return 0;
                });
                const fmt = (v) => (v !== null && v !== undefined && !Number.isNaN(v)) ? Number(v).toFixed(2) : '—';
                const cls = (v, pos) => (v == null || v === '' || Number.isNaN(v)) ? '' : (v > 0 ? 'price-positive' : v < 0 ? 'price-negative' : '');
                const badge = (v) => v ? '<span style="color:#10b981">✔</span>' : v === false ? '<span style="color:#ef4444">✘</span>' : '—';
                const resultBadge = (v) => {
                    if (v === 'positive') return '<span class="price-positive">Positive</span>';
                    if (v === 'negative') return '<span class="price-negative">Negative</span>';
                    return v || '—';
                };
                tbody.innerHTML = sorted.map(r =>
                    '<tr>' +
                    '<td><strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:var(--light);text-decoration:none;">' + (r.ticker || '—') + '</a></strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></td>' +
                    '<td>' + (r.industry || '—') + '</td>' +
                    '<td>' + resultBadge(r.result_class) + '</td>' +
                    '<td class="' + cls(r.reaction_return_pct, true) + '">' + (r.reaction_return_pct !== null && r.reaction_return_pct !== undefined ? r.reaction_return_pct.toFixed(2) + '%' : '—') + '</td>' +
                    '<td>' + fmt(r.day_open) + '</td><td>' + fmt(r.day_high) + '</td><td>' + fmt(r.day_low) + '</td><td>' + fmt(r.day_close) + '</td>' +
                    '<td>' + this.renderConsensusBadge(r.ticker, 'IN') + '</td>' +
                    '<td>' + badge(r.dipped) + '</td>' +
                    '<td>' + badge(r.comeback_50) + '</td>' +
                    '<td>' + badge(r.kept_dipping) + '</td>' +
                    '</tr>'
                ).join('');
            },

            patStocksSort(key) {
                if (this.patStocksSortKey === key) {
                    this.patStocksSortDir = this.patStocksSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.patStocksSortKey = key;
                    this.patStocksSortDir = 'asc';
                }
                this.renderPatStocksTable();
            
    
        }
});
})(); // end patterns IIFE
