// =========================================================================
// playground — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[playground] window.app not initialized'); return; }
            // ---------- Playground tab (API Console) ----------

            pg: {
                catalog: [],
                lastJson: null,
                lastStatus: null,

                async init() {
                    try {
                        const res = await fetch(API_BASE + '/api/v1/playground/endpoints');
                        const data = await res.json();
                        // Guard: the catalog must be an array of endpoint objects.
                        this.catalog = Array.isArray(data) ? data : [];
                        if (!Array.isArray(data)) {
                            console.error('Endpoint catalog response was not an array:', data);
                        }
                    } catch (e) {
                        console.error('Error loading endpoint catalog:', e);
                        this.catalog = [];
                    }
                    this.populateGroup();
                    this.wireSymbolAutocomplete();
                },

                populateGroup() {
                    const groupSel = document.getElementById('pgGroup');
                    const groups = [...new Set(this.catalog.map(e => e.group))];
                    if (groups.length) {
                        groupSel.innerHTML = groups.map(g => '<option value="' + g + '">' + g + '</option>').join('');
                    }
                    groupSel.onchange = () => this.populateEndpoints();
                    this.populateEndpoints();
                },

                populateEndpoints() {
                    const group = document.getElementById('pgGroup').value;
                    const epSel = document.getElementById('pgEndpoint');
                    const eps = this.catalog.filter(e => e.group === group);
                    if (eps.length) {
                        epSel.innerHTML = eps.map(e =>
                            '<option value="' + e.id + '">' + e.method + ' ' + e.path + '</option>'
                        ).join('');
                    } else {
                        epSel.innerHTML = '<option value="">No endpoints for this group</option>';
                    }
                    epSel.onchange = () => this.renderParams();
                    this.renderParams();
                },

                currentEndpoint() {
                    const id = document.getElementById('pgEndpoint').value;
                    return this.catalog.find(e => e.id === id) || null;
                },

                renderParams() {
                    const ep = this.currentEndpoint();
                    const wrap = document.getElementById('pgParams');
                    const line = document.getElementById('pgRequestLine');
                    if (!ep) { wrap.innerHTML = ''; line.textContent = 'Select an endpoint.'; return; }
                    const symbol = document.getElementById('pgSymbol').value.trim().toUpperCase() || 'RELIANCE.NS';
                    wrap.innerHTML = (ep.params || []).map(p => {
                        const val = p.name === 'tickers' ? symbol : (p.name === 'market' ? 'IN' : (p.name === 'period' ? '3mo' : (p.name === 'interval' ? '1d' : (p.name === 'limit' ? '10' : (p.name === 'lookback' ? '120' : (p.name === 'pred_len' ? '14' : ''))))));
                        if (p.type === 'select') {
                            const opts = (p.options || []).map(o => '<option value="' + o + '"' + (o === val ? ' selected' : '') + '>' + o + '</option>').join('');
                            return '<label class="timestamp" style="display:flex;flex-direction:column;gap:0.2rem;">' + p.name +
                                '<select data-param="' + p.name + '" style="padding:0.3rem;border:1px solid rgba(255,255,255,0.2);border-radius:0.4rem;background:rgba(255,255,255,0.05);color:var(--light);">' + opts + '</select></label>';
                        }
                        return '<label class="timestamp" style="display:flex;flex-direction:column;gap:0.2rem;">' + p.name +
                            '<input data-param="' + p.name + '" value="' + val + '" style="padding:0.3rem;border:1px solid rgba(255,255,255,0.2);border-radius:0.4rem;background:rgba(255,255,255,0.05);color:var(--light);"></label>';
                    }).join('');
                    line.textContent = ep.method + ' ' + ep.path.replace('{ticker}', symbol).replace('{market}', 'IN') + ' — ' + ep.description;
                },

                buildUrl() {
                    const ep = this.currentEndpoint();
                    if (!ep) return null;
                    const symbol = document.getElementById('pgSymbol').value.trim().toUpperCase() || 'RELIANCE.NS';
                    let path = ep.path.replace('{ticker}', encodeURIComponent(symbol)).replace('{market}', 'IN');
                    const params = {};
                    document.querySelectorAll('#pgParams [data-param]').forEach(el => {
                        const v = el.value.trim();
                        if (v) params[el.getAttribute('data-param')] = v;
                    });
                    const qs = Object.entries(params).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
                    // LIVE flag is ON by default: the playground must NEVER serve
                    // stale cache — append the correct bypass param per endpoint
                    // (force_refresh for cache-backed OHLCV/earnings/market-cap,
                    // live for market-context).  Endpoints that are already live
                    // (universe, playground/ticker/history) need no extra flag.
                    const BYPASS = {
                        market_cap: 'force_refresh=true',
                        market_context: 'live=true',
                        price_history: 'force_refresh=true',
                        earnings_history: 'force_refresh=true',
                    };
                    const liveEl = document.getElementById('pgLive');
                    if (liveEl && liveEl.checked && ep.method === 'GET') {
                        const extra = (params.live || params.force_refresh) ? '' : (BYPASS[ep.id] || '');
                        const parts = [qs].filter(Boolean);
                        if (extra) parts.push(extra);
                        return { method: ep.method, url: API_BASE + path + (parts.length ? '?' + parts.join('&') : ''), body: params };
                    }
                    return { method: ep.method, url: API_BASE + path + (qs ? '?' + qs : ''), body: params };
                },

                async send() {
                    const req = this.buildUrl();
                    if (!req) return;
                    const btn = document.getElementById('pgSendBtn');
                    const respEl = document.getElementById('pgResponse');
                    const statusEl = document.getElementById('pgStatus');
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Sending...';
                    respEl.innerHTML = '<span class="timestamp">Loading...</span>';
                    statusEl.textContent = '';
                    const t0 = performance.now();
                    try {
                        const opts = { method: req.method, headers: {'Content-Type': 'application/json'} };
                        if (req.method === 'POST') opts.body = JSON.stringify({tickers: [req.body.tickers || 'RELIANCE.NS'], lookback: Number(req.body.lookback || 120), pred_len: Number(req.body.pred_len || 14)});
                        const res = await fetch(req.url, opts);
                        const ms = Math.round(performance.now() - t0);
                        const text = await res.text();
                        let data;
                        try { data = JSON.parse(text); } catch (e) { data = text; }
                        this.lastJson = data;
                        this.lastStatus = res.status;
                        statusEl.textContent = res.status + ' · ' + ms + 'ms';
                        statusEl.style.color = res.ok ? 'var(--green)' : 'var(--red)';
                        respEl.textContent = JSON.stringify(data, null, 2);
                    } catch (e) {
                        console.error('API console error:', e);
                        this.lastJson = null;
                        this.lastStatus = null;
                        statusEl.textContent = 'error';
                        statusEl.style.color = 'var(--red)';
                        respEl.textContent = 'Request failed: ' + e.message;
                    } finally {
                        btn.disabled = false;
                        btn.textContent = '▶ Send';
                    }
                },

                copyJson() {
                    if (this.lastJson === null) return;
                    const text = typeof this.lastJson === 'string' ? this.lastJson : JSON.stringify(this.lastJson, null, 2);
                    if (navigator.clipboard) {
                        navigator.clipboard.writeText(text).then(() => alert('Copied!'));
                    } else {
                        const ta = document.createElement('textarea');
                        ta.value = text;
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                        alert('Copied!');
                    }
                },

                wireSymbolAutocomplete() {
                    const input = document.getElementById('pgSymbol');
                    const dd = document.getElementById('pgSymbolDropdown');
                    let idx = -1;
                    input.addEventListener('input', async () => {
                        const q = input.value.trim();
                        if (q.length < 1) { dd.style.display = 'none'; return; }
                        try {
                            const res = await fetch(API_BASE + '/api/v1/playground/search?q=' + encodeURIComponent(q));
                            const items = await res.json();
                            idx = -1;
                            dd.innerHTML = items.map((it, i) =>
                                '<div class="autocomplete-item" data-i="' + i + '" onclick="app.pg.selectSymbol(\'' + it.symbol.replace(/'/g, "\\'") + '\')">' +
                                '<strong>' + it.symbol + '</strong> <span style="color:var(--muted);font-size:0.8rem;">' + it.market + '</span>' +
                                '</div>'
                            ).join('');
                            dd.style.display = items.length ? 'block' : 'none';
                        } catch (e) {
                            dd.style.display = 'none';
                        }
                    });
                    input.addEventListener('keydown', (e) => {
                        const items = dd.querySelectorAll('.autocomplete-item');
                        if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, -1); items.forEach((it, i) => it.classList.toggle('selected', i === idx)); }
                        else if (e.key === 'Enter') { e.preventDefault(); if (idx >= 0 && items[idx]) items[idx].click(); else if (items.length) items[0].click(); }
                        else if (e.key === 'Escape') { dd.style.display = 'none'; }
                    });
                    document.addEventListener('click', (e) => {
                        if (!input.contains(e.target) && !dd.contains(e.target)) dd.style.display = 'none';
                    });
                },

                selectSymbol(symbol) {
                    document.getElementById('pgSymbol').value = symbol;
                    document.getElementById('pgSymbolDropdown').style.display = 'none';
                    this.renderParams();
                }
            },

            async loadPlaygroundNse() {
                const el = document.getElementById('pgNseStats');
                el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Loading NSE universe stats...</div>';
                try {
                    const res = await fetch(API_BASE + '/api/v1/playground/nse');
                    const data = await res.json();
                    const labels = {
                        NSE_ALL: 'NSE All (nsetools)',
                        NSE_LARGE_CAP: 'NSE Large Cap (>1000 cr)',
                        IN: 'NSE Top (nse_top.txt)',
                        US: 'US Top (us_top.txt)',
                        COMBINED: 'Combined IN+US'
                    };
                    el.innerHTML = Object.entries(data).map(([key, v]) =>
                        '<div class="widget-card">' +
                        '<h4>' + (labels[key] || key) + '</h4>' +
                        '<div class="metric"><span>Count</span><strong>' + (v.count || 0) + '</strong></div>' +
                        (v.sample && v.sample.length ? '<p class="timestamp" style="margin:0.5rem 0 0 0;">' + v.sample.slice(0, 6).join(', ') + (v.sample.length > 6 ? '…' : '') + '</p>' : '') +
                        (v.error ? '<p class="timestamp" style="color:var(--red);margin:0.25rem 0 0 0;">' + v.error + '</p>' : '') +
                        '</div>'
                    ).join('');
                } catch (e) {
                    console.error('Error loading NSE stats:', e);
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error loading NSE universe stats</div>';
                }
            },

            async runPlaygroundKronos() {
                const btn = document.getElementById('pgKronosRunBtn');
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Running...';
                const el = document.getElementById('pgKronosResults');
                el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Running Kronos predictions... this can take several minutes.</div>';
                const input = document.getElementById('pgKronosTickers').value;
                const tickers = input ? input.split(',').map(t => t.trim().toUpperCase()).filter(Boolean) : [];
                try {
                    const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({tickers: tickers, lookback: 120, pred_len: 14})
                    });
                    const data = await res.json();
                    if (!Array.isArray(data) || !data.length) {
                        el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No predictions generated. Check that the Kronos library is available.</div>';
                        return;
                    }
                    el.innerHTML = data.map(f => {
                        const cls = f.return_pct >= 0.5 ? 'price-positive' : f.return_pct <= -0.5 ? 'price-negative' : '';
                        const trendEmoji = f.return_pct >= 0.5 ? '🟢' : f.return_pct <= -0.5 ? '🔴' : '🟡';
                        const series = Array.isArray(f.forecast_series) ? f.forecast_series : [];
                        const seriesHtml = series.length ? this.renderForecastSeries(series) : '';
                        const gbmHtml = this.renderGbmSignal(f.gbm_prediction);
                        return '<div class="widget-card">' +
                            '<h4>' + (f.name || f.symbol || f.ticker) + ' <span class="timestamp">' + (f.symbol || f.ticker || '') + '</span></h4>' +
                            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">' +
                            '<div class="metric"><span>Current Price</span><strong>₹' + (f.current_price ? f.current_price.toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>14D Return</span><strong class="' + cls + '">' + trendEmoji + ' ' + f.return_pct + '%</strong></div>' +
                            '<div class="metric"><span>Support</span><strong>₹' + (f.support ? f.support.toFixed(2) : 'N/A') + '</strong></div>' +
                            '<div class="metric"><span>Resistance</span><strong>₹' + (f.resistance ? f.resistance.toFixed(2) : 'N/A') + '</strong></div>' +
                            '</div>' +
                            (f.explanation ? '<p class="timestamp" style="margin-top:0.5rem;">' + f.explanation + '</p>' : '') +
                            gbmHtml +
                            seriesHtml +
                            '</div>';
                    }).join('');
                } catch (e) {
                    console.error('Error running playground Kronos:', e);
                    el.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">Error running Kronos predictions</div>';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '▶ Run';
                }
            },

        // [] → extracted to modules/backtest.js
})(); // end playground IIFE
