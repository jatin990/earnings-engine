/**
 * Strategy Auditor — Front-end controller for the Strategy Auditor tab.
 *
 * Communicates with /api/v1/audit/* endpoints to log predictions, run audits,
 * display per-strategy performance metrics, and render the audit ledger table.
 */

(function () {
    'use strict';

    const API_BASE = '/api/v1/audit';
    let currentPage = 0;
    const PAGE_SIZE = 50;

    // -----------------------------------------------------------------------
    // View toggle
    // -----------------------------------------------------------------------

    function show() {
        document.getElementById('dashboardView').classList.add('hidden');
        document.getElementById('tickerDetail')?.classList.add('hidden');
        document.getElementById('strategyAuditorView').classList.remove('hidden');
        loadMetrics();
        loadHistory();
        loadStrategyFilter();
    }

    function hide() {
        document.getElementById('strategyAuditorView').classList.add('hidden');
        document.getElementById('dashboardView').classList.remove('hidden');
    }

    // -----------------------------------------------------------------------
    // Load metrics
    // -----------------------------------------------------------------------

    async function loadMetrics() {
        try {
            const res = await fetch(`${API_BASE}/metrics`);
            const data = await res.json();
            if (!data.success) return;

            const ov = data.overall || {};
            _setText('sa-total', ov.total_predictions || 0);
            _setText('sa-winrate', (ov.win_rate_pct || 0) + '%');
            _setText('sa-pf', ov.profit_factor || 0);

            const avgRet = ov.avg_return_pct || 0;
            const avgEl = document.getElementById('sa-avgret');
            if (avgEl) {
                avgEl.textContent = avgRet.toFixed(2) + '%';
                avgEl.className = 'text-2xl font-bold mt-1 ' + (avgRet >= 0 ? 'text-green-500' : 'text-red-500');
            }
            _setText('sa-sharpe', ov.sharpe_ratio || 0);

            // Strategy breakdown table
            const tbody = document.getElementById('sa-strategy-table');
            if (tbody && data.by_strategy) {
                tbody.innerHTML = '';
                for (const [name, m] of Object.entries(data.by_strategy)) {
                    const wrClass = m.win_rate_pct >= 50 ? 'text-green-500' : 'text-red-500';
                    const retClass = m.avg_return_pct >= 0 ? 'text-green-500' : 'text-red-500';
                    const brierStr = m.brier_score !== null && m.brier_score !== undefined
                        ? m.brier_score.toFixed(3)
                        : '—';
                    tbody.innerHTML += `
                        <tr class="hover:bg-gray-50 dark:hover:bg-gray-700">
                            <td class="px-4 py-3 font-medium text-gray-900 dark:text-white">${_esc(name)}</td>
                            <td class="px-4 py-3 text-right text-gray-600 dark:text-gray-300">${m.total_predictions}</td>
                            <td class="px-4 py-3 text-right font-semibold ${wrClass}">${m.win_rate_pct}%</td>
                            <td class="px-4 py-3 text-right text-gray-600 dark:text-gray-300">${m.profit_factor}</td>
                            <td class="px-4 py-3 text-right font-medium ${retClass}">${m.avg_return_pct.toFixed(2)}%</td>
                            <td class="px-4 py-3 text-right text-gray-600 dark:text-gray-300">${m.cumulative_return_pct.toFixed(2)}%</td>
                            <td class="px-4 py-3 text-right text-gray-600 dark:text-gray-300">${m.sharpe_ratio}</td>
                            <td class="px-4 py-3 text-right text-gray-600 dark:text-gray-300">${brierStr}</td>
                        </tr>`;
                }
                if (Object.keys(data.by_strategy).length === 0) {
                    tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-6 text-center text-gray-400">No audited strategies yet. Log predictions and run audit.</td></tr>`;
                }
            }
        } catch (e) {
            console.error('Failed to load strategy metrics:', e);
        }
    }

    // -----------------------------------------------------------------------
    // Load audit history ledger
    // -----------------------------------------------------------------------

    async function loadHistory() {
        const strategy = document.getElementById('sa-filter-strategy')?.value || '';
        const status = document.getElementById('sa-filter-status')?.value || '';
        const params = new URLSearchParams({
            limit: PAGE_SIZE,
            offset: currentPage * PAGE_SIZE,
        });
        if (strategy) params.set('strategy', strategy);
        if (status) params.set('status', status);

        try {
            const res = await fetch(`${API_BASE}/history?${params}`);
            const data = await res.json();
            if (!data.success) return;

            const tbody = document.getElementById('sa-ledger-table');
            if (!tbody) return;
            tbody.innerHTML = '';

            const items = data.items || [];
            for (const item of items) {
                const dateStr = (item.created_at || '').substring(0, 10);
                const signal = item.signal || '';
                const signalBadge = _signalBadge(signal);
                const statusBadge = _statusBadge(item.audit_status);
                const entry = item.entry_price ? item.entry_price.toFixed(2) : '—';
                const exit = item.actual_exit_price ? item.actual_exit_price.toFixed(2) : '—';
                const retPct = item.actual_return_pct !== null && item.actual_return_pct !== undefined
                    ? `<span class="${item.actual_return_pct >= 0 ? 'text-green-500' : 'text-red-500'}">${item.actual_return_pct.toFixed(2)}%</span>`
                    : '—';
                const headline = item.news_headline || '';

                tbody.innerHTML += `
                    <tr class="hover:bg-gray-50 dark:hover:bg-gray-700 text-sm">
                        <td class="px-3 py-2 text-gray-600 dark:text-gray-300">${dateStr}</td>
                        <td class="px-3 py-2 font-medium text-gray-900 dark:text-white">${_esc(item.ticker)}</td>
                        <td class="px-3 py-2 text-gray-600 dark:text-gray-300">${_esc(item.strategy_name)}</td>
                        <td class="px-3 py-2 text-center">${signalBadge}</td>
                        <td class="px-3 py-2 text-right text-gray-600 dark:text-gray-300">${entry}</td>
                        <td class="px-3 py-2 text-right text-gray-600 dark:text-gray-300">${exit}</td>
                        <td class="px-3 py-2 text-right">${retPct}</td>
                        <td class="px-3 py-2 text-center">${statusBadge}</td>
                        <td class="px-3 py-2 text-gray-500 dark:text-gray-400 max-w-xs truncate" title="${_esc(headline)}">${_esc(headline)}</td>
                        <td class="px-3 py-2 text-center">
                            <button type="button" onclick="window.strategyAuditor.deletePrediction(${item.id})" class="text-red-400 hover:text-red-600 text-xs" title="Delete">🗑️</button>
                        </td>
                    </tr>`;
            }

            if (items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10" class="px-4 py-6 text-center text-gray-400">No predictions logged yet.</td></tr>`;
            }

            const total = data.total || 0;
            _setText('sa-ledger-info', `Showing ${currentPage * PAGE_SIZE + 1}–${Math.min((currentPage + 1) * PAGE_SIZE, total)} of ${total} predictions`);
        } catch (e) {
            console.error('Failed to load audit history:', e);
        }
    }

    // -----------------------------------------------------------------------
    // Load strategy filter dropdown
    // -----------------------------------------------------------------------

    async function loadStrategyFilter() {
        try {
            const res = await fetch(`${API_BASE}/strategies`);
            const data = await res.json();
            if (!data.success) return;

            const select = document.getElementById('sa-filter-strategy');
            if (!select) return;

            // Preserve current selection
            const current = select.value;
            select.innerHTML = '<option value="">All Strategies</option>';
            for (const s of (data.strategies || [])) {
                const selected = s.strategy_name === current ? ' selected' : '';
                select.innerHTML += `<option value="${_esc(s.strategy_name)}"${selected}>${_esc(s.strategy_name)} (${s.total_predictions})</option>`;
            }
        } catch (e) {
            console.error('Failed to load strategies list:', e);
        }
    }

    // -----------------------------------------------------------------------
    // Log prediction
    // -----------------------------------------------------------------------

    async function logPrediction() {
        const ticker = document.getElementById('sa-ticker')?.value?.trim();
        const strategy = document.getElementById('sa-strategy')?.value?.trim();
        const signal = document.getElementById('sa-signal')?.value;

        if (!ticker || !strategy) {
            alert('Ticker and Strategy Name are required.');
            return;
        }

        const payload = {
            ticker: ticker.toUpperCase(),
            strategy_name: strategy,
            signal: signal,
            holding_horizon: document.getElementById('sa-horizon')?.value || '1D',
            news_headline: document.getElementById('sa-headline')?.value?.trim() || null,
            news_source: document.getElementById('sa-news-source')?.value?.trim() || null,
        };

        const confidence = parseFloat(document.getElementById('sa-confidence')?.value);
        if (!isNaN(confidence)) payload.confidence_pct = confidence;

        const entryPrice = parseFloat(document.getElementById('sa-entry-price')?.value);
        if (!isNaN(entryPrice)) payload.entry_price = entryPrice;

        const expectedReturn = parseFloat(document.getElementById('sa-expected-return')?.value);
        if (!isNaN(expectedReturn)) payload.expected_return_pct = expectedReturn;

        try {
            const res = await fetch(`${API_BASE}/log`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (data.success) {
                // Clear form
                document.getElementById('sa-ticker').value = '';
                document.getElementById('sa-headline').value = '';
                document.getElementById('sa-confidence').value = '';
                document.getElementById('sa-entry-price').value = '';
                document.getElementById('sa-expected-return').value = '';
                document.getElementById('sa-news-source').value = '';

                loadHistory();
                loadMetrics();
                loadStrategyFilter();
            } else {
                alert('Error: ' + (data.detail || 'Unknown error'));
            }
        } catch (e) {
            console.error('Failed to log prediction:', e);
            alert('Failed to log prediction.');
        }
    }

    // -----------------------------------------------------------------------
    // Run audit
    // -----------------------------------------------------------------------

    async function runAudit() {
        try {
            const res = await fetch(`${API_BASE}/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force: false }),
            });
            const data = await res.json();
            if (data.success) {
                alert(`Audit complete: ${data.evaluated} evaluated, ${data.pending} pending`);
                loadMetrics();
                loadHistory();
            } else {
                alert('Audit failed: ' + (data.detail || 'Unknown error'));
            }
        } catch (e) {
            console.error('Audit failed:', e);
            alert('Failed to run audit.');
        }
    }

    // -----------------------------------------------------------------------
    // Delete prediction
    // -----------------------------------------------------------------------

    async function deletePrediction(id) {
        if (!confirm(`Delete prediction #${id}?`)) return;
        try {
            const res = await fetch(`${API_BASE}/prediction/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                loadHistory();
                loadMetrics();
            }
        } catch (e) {
            console.error('Delete failed:', e);
        }
    }

    // -----------------------------------------------------------------------
    // Pagination
    // -----------------------------------------------------------------------

    function nextPage() {
        currentPage++;
        loadHistory();
    }

    function prevPage() {
        if (currentPage > 0) {
            currentPage--;
            loadHistory();
        }
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    function _setText(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function _esc(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function _signalBadge(signal) {
        const s = (signal || '').toUpperCase();
        if (s === 'BULLISH') return '<span class="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300">🟢 Bullish</span>';
        if (s === 'BEARISH') return '<span class="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300">🔴 Bearish</span>';
        return '<span class="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">⚪ Neutral</span>';
    }

    function _statusBadge(status) {
        const s = (status || '').toUpperCase();
        if (s === 'WORKED') return '<span class="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300">✅ Worked</span>';
        if (s === 'FAILED') return '<span class="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300">❌ Failed</span>';
        return '<span class="px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300">⏳ Pending</span>';
    }

    // -----------------------------------------------------------------------
    // Import Kronos & Run Backtest
    // -----------------------------------------------------------------------

    async function importKronos() {
        if (!confirm('Import all historical Kronos AI predictions and audit outcomes against actual price data?')) return;
        try {
            const res = await fetch(`${API_BASE}/import-kronos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force: false }),
            });
            const data = await res.json();
            if (data.success) {
                alert(`✅ Imported ${data.imported} Kronos predictions (${data.skipped} skipped). Audited ${data.audited} outcomes!`);
                loadMetrics();
                loadHistory();
                loadStrategyFilter();
            } else {
                alert('Error: ' + (data.detail || 'Import failed'));
            }
        } catch (e) {
            console.error('Import Kronos failed:', e);
            alert('Failed to import Kronos predictions.');
        }
    }

    async function runBacktest() {
        if (!confirm('Run 1-Year historical backtest across all strategies (Kronos, Momentum Breakout, Earnings Drift, Mean Reversion)?')) return;
        try {
            const res = await fetch(`${API_BASE}/backtest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategy: 'ALL', days: 365 }),
            });
            const data = await res.json();
            if (data.success) {
                alert(`✅ 1-Year Backtest complete!\nGenerated: ${data.predictions_generated} decisions\nAudited: ${data.audited_count} outcomes`);
                loadMetrics();
                loadHistory();
                loadStrategyFilter();
            } else {
                alert('Error: ' + (data.detail || 'Backtest failed'));
            }
        } catch (e) {
            console.error('Backtest failed:', e);
            alert('Failed to run backtest.');
        }
    }

    // -----------------------------------------------------------------------
    // Public API
    // -----------------------------------------------------------------------

    window.strategyAuditor = {
        show,
        hide,
        loadMetrics,
        loadHistory,
        logPrediction,
        runAudit,
        importKronos,
        runBacktest,
        deletePrediction,
        nextPage,
        prevPage,
    };
})();

