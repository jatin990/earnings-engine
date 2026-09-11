// =========================================================================
// buy_dip — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
// ---------- Buy the Dip tab ----------

            async loadRecentResults() {
                const market = document.getElementById('bdMarket').value;
                const corr = document.getElementById('bdCorrection').value || 5;
                const drop = document.getElementById('bdDrop').value || 3;
                const start = document.getElementById('bdStartDate').value || '';
                const end = document.getElementById('bdEndDate').value || '';
                const statusEl = document.getElementById('bdStatus');
                const todayTbody = document.getElementById('bdTodayTable');
                const yesterdayTbody = document.getElementById('bdYesterdayTable');
                // Persist the controls so the tab returns to the same view next session.
                try {
                    localStorage.setItem('bdDrop', String(drop));
                    localStorage.setItem('bdStartDate', start);
                    localStorage.setItem('bdEndDate', end);
                } catch (e) { /* ignore */ }
                todayTbody.innerHTML = yesterdayTbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Loading...</td></tr>';
                statusEl.textContent = '';
                const q = new URLSearchParams({ market: market, correction_pct: String(corr), drop_pct: String(drop) });
                if (start) q.set('start_date', start);
                if (end) q.set('end_date', end);
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/recent-results?' + q.toString());
                    const d = await res.json();
                    this._bdData = d;
                    this.renderRecentResults(d);
                    statusEl.textContent = 'Loaded at ' + new Date().toLocaleTimeString() + ' — range: ' + (start || 'recent') + ' → ' + (end || 'today');
                } catch (e) {
                    console.error('Error loading recent results:', e);
                    todayTbody.innerHTML = yesterdayTbody.innerHTML = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">Error loading recent results</td></tr>';
                }
            },

            applyBdPreset() {
                const days = document.getElementById('bdPreset').value;
                const iso = (d) => d.toISOString().split('T')[0];
                if (!days) {
                    document.getElementById('bdStartDate').value = '';
                    document.getElementById('bdEndDate').value = '';
                } else {
                    const end = new Date();
                    const start = new Date();
                    start.setDate(start.getDate() - parseInt(days, 10));
                    document.getElementById('bdStartDate').value = iso(start);
                    document.getElementById('bdEndDate').value = iso(end);
                }
                this.loadRecentResults();
            },

            async analyzeEarningsQuality() {
                const market = document.getElementById('bdMarket').value;
                const start = document.getElementById('bdStartDate').value || '';
                const end = document.getElementById('bdEndDate').value || '';
                const statusEl = document.getElementById('bdVerdictStatus');
                statusEl.textContent = 'Analyzing...';
                const q = new URLSearchParams({ market: market });
                if (start) q.set('start_date', start);
                if (end) q.set('end_date', end);
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/recent-results/verdict?' + q.toString());
                    const d = await res.json();
                    const verdicts = d.verdicts || {};
                    if (this._bdData && this._bdData.rows) {
                        this._bdData.rows.forEach(r => {
                            const v = (verdicts[r.ticker] || {});
                            r._verdict = v.verdict || null;
                            r._verdict_metric = v.metric || '';
                        });
                        this.renderRecentResults(this._bdData);
                    }
                    statusEl.textContent = 'Analyzed ' + (d.total || 0) + ' stocks.';
                } catch (e) {
                    console.error('Error analyzing earnings quality:', e);
                    statusEl.textContent = 'Error analyzing.';
                }
            },

            _restoreBdControls() {
                try {
                    const drop = localStorage.getItem('bdDrop');
                    const start = localStorage.getItem('bdStartDate');
                    const end = localStorage.getItem('bdEndDate');
                    if (drop != null) document.getElementById('bdDrop').value = drop;
                    if (start != null) document.getElementById('bdStartDate').value = start;
                    if (end != null) document.getElementById('bdEndDate').value = end;
                } catch (e) { /* ignore */ }
                const hoursEl = document.getElementById('bdMarketHours');
                if (hoursEl) {
                    hoursEl.textContent = (new Date().getHours() >= 16)
                        ? '🕘 After market close — today\'s results are included. '
                        : '☀️ During trading hours — today\'s results appear once the market closes (~16:00). ';
                }
            },

            renderRecentResults(d) {
                const summaryEl = document.getElementById('bdSummary');
                const candEl = document.getElementById('bdCandidates');
                const dipEl = document.getElementById('bdDipRecovery');
                const todayTbody = document.getElementById('bdTodayTable');
                const yesterdayTbody = document.getElementById('bdYesterdayTable');
                const rows = d.rows || [];
                const pct = (v) => v !== null && v !== undefined ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                const fmt = (v) => (v !== null && v !== undefined) ? v.toFixed(2) : '—';
                summaryEl.innerHTML = [
                    '<div class="metric"><span>Buy-Dip Candidates</span><strong>' + (d.buy_dip_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Dip → Recovery</span><strong>' + (d.dip_recovery_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Today</span><strong>' + (d.today_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Yesterday</span><strong>' + (d.yesterday_count || 0) + '</strong></div>',
                    '<div class="metric"><span>Total Results</span><strong>' + (d.total || 0) + '</strong></div>'
                ].join('');
                const recoveries = rows.filter(r => r.is_dip_recovery);
                dipEl.innerHTML = recoveries.length
                    ? '<div class="card" style="border:2px solid #f59e0b;background:rgba(245,158,11,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">📉 → 📈 DIP-THEN-RECOVERY CANDIDATES</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        recoveries.map(r => '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;">' + r.ticker +
                            ' (open ' + pct(r.drop_at_open_pct) + ' → rec ' + pct(r.intraday_recovery_pct) + ')</span>').join('') +
                        '</div></div>'
                    : '<div class="card" style="margin:0 0 1rem 0;">No dip-then-recovery candidates in the current scan.</div>';
                const buys = rows.filter(r => r.is_buy_dip);
                candEl.innerHTML = buys.length
                    ? '<div class="card" style="border:2px solid #10b981;background:rgba(16,185,129,0.08);margin-bottom:1rem;">' +
                        '<span style="font-size:0.8rem;color:var(--muted);font-weight:600;">🛒 BUY-THE-DIP CANDIDATES</span>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem;">' +
                        buys.map(r => '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#10b981;">' + r.ticker + ' (pull ' + (r.pullback_from_high !== null ? r.pullback_from_high.toFixed(1) + '%' : '—') + ')</span>').join('') +
                        '</div></div>'
                    : '';
                const todayRows = rows.filter(r => (r.day_label || '') === 'Today');
                const yesterdayRows = rows.filter(r => (r.day_label || '') === 'Yesterday');
                const emptyRow = '<tr><td colspan="12" style="padding:1rem;text-align:center;color:var(--muted)">No results in this section.</td></tr>';
                todayTbody.innerHTML = todayRows.length ? todayRows.map(r => this._buildBdRow(r)).join('') : emptyRow;
                yesterdayTbody.innerHTML = yesterdayRows.length ? yesterdayRows.map(r => this._buildBdRow(r)).join('') : emptyRow;
            },
            _buildBdRow(r) {
                const pct = (v) => v !== null && v !== undefined ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                const fmt = (v) => (v !== null && v !== undefined) ? v.toFixed(2) : '—';
                const rising = r.high_pct !== null && r.high_pct > 0;
                const dip = r.is_buy_dip;
                const rec = r.is_dip_recovery;
                let sig;
                if (rec) {
                    sig = '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;">📉→📈 Dip Rec</span>';
                } else if (dip) {
                    sig = '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#10b981;">🛒 Buy Dip</span>';
                } else if (rising) {
                    sig = '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#6ee7b7;">Rising</span>';
                } else {
                    sig = '<span class="signal-badge" style="background:rgba(239,68,68,0.2);color:#ef4444;">Falling</span>';
                }
                const pullCls = (r.pullback_from_high !== null && r.pullback_from_high < 0) ? 'price-negative' : 'price-positive';
                const gapCls = (r.drop_at_open_pct !== null && r.drop_at_open_pct < 0) ? 'price-negative' : 'price-positive';
                const mom = (v) => (v !== null && v !== undefined) ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—';
                const momStr = '3D ' + mom(r.momentum_3d) + ' · 7D ' + mom(r.momentum_7d) + ' · 30D ' + mom(r.momentum_30d);
                const ohlcLine = (label, val, valPct) => {
                    const cls = (valPct !== null && valPct !== undefined && valPct >= 0) ? 'price-positive' : (valPct !== null && valPct !== undefined ? 'price-negative' : '');
                    const pctTag = (valPct !== null && valPct !== undefined) ? ' <span class="' + cls + '">(' + pct(valPct) + ')</span>' : '';
                    return '<div style="white-space:nowrap;">' + label + ': <strong>' + fmt(val) + '</strong>' + pctTag + '</div>';
                };
                const rd = r.result_ohlc;
                const rdStr = rd ? ohlcLine('O', rd.open, rd.open_pct) + ohlcLine('H', rd.high, rd.high_pct) + ohlcLine('L', rd.low, rd.low_pct) + ohlcLine('C', rd.close, rd.close_pct) : '—';
                const nd = r.next_day_ohlc;
                const ndStr = nd ? ohlcLine('O', nd.open, nd.open_pct) + ohlcLine('C', nd.close, nd.close_pct) : '—';
                const recStr = r.is_dip_recovery
                    ? '<span class="price-positive">✔ Recovered ' + pct(r.intraday_recovery_pct) + '</span>'
                    : (r.closed_above_open === false ? '<span class="price-negative">✘ Closed low</span>' : '—');
                const verdict = r._verdict || null;
                let verdictStr = '—';
                if (verdict) {
                    const vCls = (verdict === 'Beat' || verdict === 'Strong') ? 'price-positive'
                        : (verdict === 'Miss' || verdict === 'Weak') ? 'price-negative' : '';
                    verdictStr = '<span class="' + vCls + '" title="' + (r._verdict_metric || '') + '">' + verdict + '</span>';
                }
                const rowStyle = rec ? ' style="background:rgba(245,158,11,0.08);"' : (dip ? ' style="background:rgba(16,185,129,0.10);"' : '');
                const changePct = r.change_pct;
                const changeCls = (changePct !== null && changePct !== undefined && changePct >= 0) ? 'price-positive' : 'price-negative';
                return '<tr' + rowStyle + '>' +
                    '<td><strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:var(--light);text-decoration:none;">' + r.ticker + '</a></strong><a href="/stock/' + encodeURIComponent(r.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></td>' +
                    '<td><span style="font-size:0.7rem;color:var(--muted)">' + (r.earnings_time || (r.day_label || '')) + '</span></td>' +
                    '<td>' + fmt(r.current_price) + '</td>' +
                    '<td class="' + changeCls + '">' + pct(changePct) + '</td>' +
                    '<td class="' + gapCls + '">' + pct(r.drop_at_open_pct) + '</td>' +
                    '<td>' + rdStr + '</td>' +
                    '<td>' + ndStr + '</td>' +
                    '<td>' + momStr + '</td>' +
                    '<td>' + recStr + '</td>' +
                    '<td class="' + pullCls + '">' + pct(r.pullback_from_high) + '</td>' +
                    '<td>' + sig + '</td>' +
                    '<td>' + verdictStr + '</td>' +
                    '</tr>';
            },
            toggleBdSection(section) {
                const body = document.getElementById(section === 'today' ? 'bdTodaySection' : 'bdYesterdaySection');
                const toggle = document.getElementById(section === 'today' ? 'bdTodayToggle' : 'bdYesterdayToggle');
                if (!body || !toggle) return;
                const hidden = body.style.display === 'none';
                body.style.display = hidden ? '' : 'none';
                toggle.textContent = hidden ? '▼' : '▶';
            }
    });

    try {
        app._restoreBdControls?.();
    } catch (e) {}
})(); // end buy_dip IIFE
