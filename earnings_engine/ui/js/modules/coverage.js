// =========================================================================
// coverage — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[coverage] window.app not initialized'); return; }
            // ---------- Data Coverage tab ----------

            async loadDataCoverage() {
                const market = document.getElementById('coverageMarket').value;
                const summaryEl = document.getElementById('coverageSummary');
                const statusEl = document.getElementById('coverageStatus');
                summaryEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading data coverage...</div>';
                statusEl.textContent = '';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/data-coverage?market=' + encodeURIComponent(market));
                    const d = await res.json();
                    this.coverageData = d.rows || [];
                const pct = (v) => v !== null && v !== undefined ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                    summaryEl.innerHTML = [
                        '<div class="metric"><span>Universe Tickers</span><strong>' + d.total + '</strong></div>',
                        '<div class="metric"><span>With Prices</span><strong>' + d.with_prices + '</strong></div>',
                        '<div class="metric"><span>With Earnings</span><strong>' + d.with_earnings + '</strong></div>',
                        '<div class="metric"><span>Earnings Coverage</span><strong>' + pct(d.total ? d.with_earnings / d.total * 100 : 0) + '</strong></div>'
                    ].join('');
                    this.renderCoverageTable();
                    statusEl.textContent = 'Coverage loaded at ' + new Date().toLocaleTimeString();
                } catch (e) {
                    console.error('Error loading data coverage:', e);
                    summaryEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading data coverage</div>';
                }
            },

            renderCoverageTable() {
                const tbody = document.getElementById('coverageTable');
                const rows = this.coverageData || [];
                const filter = (document.getElementById('coverageSearch').value || '').trim().toUpperCase();
                const filtered = filter ? rows.filter(r => (r.ticker || '').toUpperCase().includes(filter)) : rows;
                if (!filtered.length) {
                    tbody.innerHTML = '<tr><td colspan="9" style="padding:1rem;text-align:center;color:var(--muted)">No coverage data for this filter/universe.</td></tr>';
                    return;
                }
                tbody.innerHTML = filtered.map(r => {
                    const fresh = r.earnings_fresh ? '✅ Yes' : '❌ No';
                    return '<tr>' +
                        '<td><strong>' + (r.ticker || '?') + '</strong></td>' +
                        '<td>' + (r.listing_date || '—') + '</td>' +
                        '<td>' + (r.price_start || '—') + '</td>' +
                        '<td>' + (r.price_end || '—') + '</td>' +
                        '<td>' + (r.price_rows || 0) + '</td>' +
                        '<td>' + (r.earnings_start || '—') + '</td>' +
                        '<td>' + (r.earnings_end || '—') + '</td>' +
                        '<td>' + (r.earnings_rows || 0) + '</td>' +
                        '<td>' + fresh + '</td>' +
                        '</tr>';
                }).join('');
            },

            async runIncrementalEarnings() {
                if (this.isMaster === false) {
                    alert('⚠️ Access Restricted: Incremental dataset ingestion is restricted to Master role.');
                    return;
                }
                const btn = (typeof event !== 'undefined' && event && event.target) ? event.target : document.getElementById('coverageFetchMissingBtn');
                const originalText = btn ? btn.textContent : '⚡ Fetch Missing';
                if (btn) {
                    btn.disabled = true;
                    btn.textContent = '⏳ Fetching...';
                }
                const statusEl = document.getElementById('coverageStatus');
                if (statusEl) statusEl.textContent = 'Fetching earnings for tickers missing data... this can take a while.';
                const market = document.getElementById('coverageMarket')?.value || 'ALL';
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/earnings/incremental', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({market: market})
                    });
                    if (res.status === 403) {
                        if (statusEl) statusEl.textContent = '⚠️ Access Denied: Master role required.';
                        alert('⚠️ Access Restricted: Incremental dataset ingestion is restricted to Master role.');
                        return;
                    }
                    const data = await res.json();
                    if (data.success) {
                        statusEl.textContent = 'Done: ' + data.fetched + ' fetched, ' + data.already_cached + ' already cached, ' +
                            data.skipped_no_listing + ' skipped (no listing/too new), ' + data.errors + ' errors.';
                        await this.loadDataCoverage();
                    } else {
                        statusEl.textContent = 'Failed: ' + (data.error || 'Unknown error');
                    }
                } catch (e) {
                    console.error('Error running incremental earnings:', e);
                    if (statusEl) statusEl.textContent = 'Error: ' + e.message;
                } finally {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            },

})(); // end coverage IIFE
