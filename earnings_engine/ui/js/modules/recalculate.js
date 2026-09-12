// =========================================================================
// recalculate — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
Object.assign(app, {
            // =========================================================================
            // ⚡ Live Stock Price & Metric Refresh (Batched & Single)
            // =========================================================================
            _pendingRefreshQueue: new Set(),
            _pendingRefreshButtons: new Map(),
            _refreshDebounceTimer: null,

            refreshSingleStockPrice(ticker, btn, event) {
                if (event) {
                    event.stopPropagation();
                    event.preventDefault();
                }
                if (!ticker) return;
                const cleanTicker = ticker.trim().toUpperCase();

                if (btn) {
                    btn.disabled = true;
                    if (!btn.dataset.origHtml) btn.dataset.origHtml = btn.innerHTML;
                    btn.innerHTML = '<span style="display:inline-block;animation:spin 0.8s linear infinite;">↻</span>';
                    this._pendingRefreshButtons.set(cleanTicker, btn);
                }
                this._pendingRefreshQueue.add(cleanTicker);

                if (this._refreshDebounceTimer) clearTimeout(this._refreshDebounceTimer);
                this._refreshDebounceTimer = setTimeout(() => {
                    this._flushPendingRefreshQueue();
                }, 60);
            },

            async _flushPendingRefreshQueue() {
                const tickers = Array.from(this._pendingRefreshQueue);
                this._pendingRefreshQueue.clear();
                const buttonMap = new Map(this._pendingRefreshButtons);
                this._pendingRefreshButtons.clear();
                if (!tickers.length) return;

                await this.refreshStocksBatch(tickers, null, buttonMap);
            },

            async refreshStocksBatch(tickers, triggerBtn, buttonMap = null) {
                const cleanTickers = Array.from(new Set((tickers || []).map(t => (t || '').trim().toUpperCase()).filter(Boolean)));
                if (!cleanTickers.length) return { success: true, count: 0 };

                const origTriggerHtml = triggerBtn ? triggerBtn.innerHTML : '';
                if (triggerBtn) {
                    triggerBtn.disabled = true;
                    const iconEl = triggerBtn.querySelector('#topRefreshPricesIcon') || triggerBtn.querySelector('.refresh-icon');
                    if (iconEl) iconEl.style.animation = 'spin 0.8s linear infinite';
                }

                let totalUpdated = 0;
                let processed = 0;
                const chunkSize = 10;

                try {
                    for (let i = 0; i < cleanTickers.length; i += chunkSize) {
                        const chunk = cleanTickers.slice(i, i + chunkSize);
                        if (triggerBtn) {
                            const textEl = triggerBtn.querySelector('#topRefreshPricesText');
                            if (textEl) {
                                textEl.textContent = `Refreshing (${processed}/${cleanTickers.length})...`;
                            }
                        }

                        const res = await fetch(API_BASE + '/api/v1/ticker/recalculate-batch', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ tickers: chunk })
                        });
                        const data = await res.json();
                        if (data && data.success && Array.isArray(data.results)) {
                            data.results.forEach(item => {
                                if (item.ticker && item.updated_metrics) {
                                    if (item.has_changes) totalUpdated++;
                                    this.updateDomRowWithMetrics(item.ticker, item.updated_metrics);
                                }

                                if (buttonMap && buttonMap.has(item.ticker)) {
                                    const b = buttonMap.get(item.ticker);
                                    if (b) {
                                        b.innerHTML = '✓';
                                        b.style.color = '#34d399';
                                        setTimeout(() => {
                                            b.disabled = false;
                                            b.innerHTML = b.dataset.origHtml || '↻';
                                            b.style.color = '';
                                        }, 1200);
                                    }
                                }
                            });
                        }
                        processed += chunk.length;
                    }

                    if (typeof this.showToast === 'function') {
                        this.showToast(`🟢 Refreshed live prices & metrics for ${processed} stock${processed > 1 ? 's' : ''}`, 'success');
                    }
                } catch (err) {
                    console.error('[BATCH-PRICE-REFRESH] Error:', err);
                    if (typeof this.showToast === 'function') {
                        this.showToast(`⚠️ Price refresh error: ${err.message}`, 'error');
                    }
                } finally {
                    if (triggerBtn) {
                        triggerBtn.disabled = false;
                        triggerBtn.style.animation = '';
                        const iconEl = triggerBtn.querySelector('#topRefreshPricesIcon') || triggerBtn.querySelector('.refresh-icon');
                        if (iconEl) iconEl.style.animation = '';
                        const textEl = triggerBtn.querySelector('#topRefreshPricesText');
                        if (textEl) {
                            textEl.textContent = 'Refresh Prices';
                        } else if (origTriggerHtml) {
                            triggerBtn.innerHTML = origTriggerHtml;
                        }
                    }
                    if (buttonMap) {
                        buttonMap.forEach(b => {
                            if (b && b.disabled) {
                                b.disabled = false;
                                b.innerHTML = b.dataset.origHtml || '↻';
                            }
                        });
                    }
                }

                return { success: true, total: cleanTickers.length, updated: totalUpdated };
            },

            updateDomRowWithMetrics(ticker, m) {
                if (!ticker || !m) return;
                const cleanTicker = ticker.trim().toUpperCase();
                const slug = cleanTicker.replace(/[^a-zA-Z0-9]/g, '_');
                const baseTicker = cleanTicker.replace(/\.NS$/i, '').replace(/\.BO$/i, '');

                const flashBg = (el) => {
                    if (!el) return;
                    const prev = el.style.backgroundColor;
                    el.style.transition = 'background-color 0.3s ease';
                    el.style.backgroundColor = 'rgba(16, 185, 129, 0.25)';
                    setTimeout(() => {
                        el.style.backgroundColor = prev || '';
                    }, 1200);
                };

                const rows = document.querySelectorAll(`
                    tr[data-ticker="${cleanTicker}"],
                    tr[data-ticker="${baseTicker}"],
                    #row_${slug},
                    #trackedParentRow_${slug},
                    #smRow-${baseTicker}
                `);

                const isUS = !(cleanTicker.endsWith('.NS') || cleanTicker.endsWith('.BO'));
                const currSymbol = isUS ? '$' : '₹';
                const curP = m.current_price !== null && m.current_price !== undefined ? Number(m.current_price) : null;
                const priceFormatted = curP !== null ? `${currSymbol}${curP.toLocaleString(isUS ? 'en-US' : 'en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : null;

                rows.forEach(rowEl => {
                    // 1. Current Price
                    const pCell = rowEl.querySelector('.cell-current-price') || rowEl.querySelector('.row-price');
                    if (pCell && priceFormatted) {
                        const liveDot = rowEl.querySelector('.live-pulse-dot') ? '<span class="live-pulse-dot" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;margin-right:0.35rem;" title="Live Active Session"></span>' : '';
                        pCell.innerHTML = `<div style="display:flex;align-items:center;">${liveDot}<span>${priceFormatted}</span></div>`;
                        flashBg(pCell);
                    }

                    // 2. Earnings Date
                    const edCell = rowEl.querySelector('.cell-earnings-date');
                    if (edCell && m.earnings_date) {
                        edCell.textContent = m.earnings_date;
                    }

                    // 3. Three-Day Return
                    const ret3Cell = rowEl.querySelector('.cell-three-day-return');
                    if (ret3Cell && m.three_day_return_pct !== null && m.three_day_return_pct !== undefined) {
                        const val = Number(m.three_day_return_pct);
                        ret3Cell.textContent = (val >= 0 ? '+' : '') + val.toFixed(2) + '%';
                        ret3Cell.style.color = val >= 0 ? '#93c5fd' : '#fca5a5';
                        flashBg(ret3Cell);
                    }

                    // 4. Seven-Day Return (7D)
                    const ret7Cell = rowEl.querySelector('.cell-seven-day-return') || rowEl.querySelector('.return-7d-cell');
                    if (ret7Cell && m.seven_day_return_pct !== null && m.seven_day_return_pct !== undefined) {
                        const val = Number(m.seven_day_return_pct);
                        ret7Cell.textContent = (val >= 0 ? '+' : '') + val.toFixed(2) + '%';
                        ret7Cell.style.color = val >= 0 ? '#38bdf8' : '#f87171';
                        flashBg(ret7Cell);
                    }

                    // 5. Thirty-Day Return (30D)
                    const retCell = rowEl.querySelector('.cell-thirty-day-return') || rowEl.querySelector('.return-30d-cell');
                    if (retCell && m.thirty_day_return_pct !== null && m.thirty_day_return_pct !== undefined) {
                        const val = Number(m.thirty_day_return_pct);
                        retCell.textContent = (val >= 0 ? '+' : '') + val.toFixed(2) + '%';
                        retCell.style.color = val >= 0 ? '#34d399' : '#f87171';
                        flashBg(retCell);
                    }

                    // 6. Support / Resistance Bar (Technical Structure)
                    const srCell = rowEl.querySelector('.cell-sr-structure');
                    const supVal = m.current_support !== null && m.current_support !== undefined ? Number(m.current_support) : null;
                    const resVal = m.next_resistance !== null && m.next_resistance !== undefined ? Number(m.next_resistance) : null;
                    let chanPos = m.channel_position_pct !== null && m.channel_position_pct !== undefined ? Number(m.channel_position_pct) : 50;
                    if (srCell && supVal && resVal && resVal > supVal && curP) {
                        const distSup = ((curP - supVal) / curP) * 100;
                        const distRes = ((resVal - curP) / curP) * 100;
                        srCell.innerHTML = `
                            <div class="sr-structure-cell" style="display:flex;flex-direction:column;gap:0.18rem;min-width:130px;" title="Support: ${currSymbol}${supVal.toFixed(1)} (-${distSup.toFixed(1)}%) | Resistance: ${currSymbol}${resVal.toFixed(1)} (+${distRes.toFixed(1)}%)">
                                <div style="display:flex;justify-content:space-between;font-size:0.65rem;font-family:var(--font-mono);line-height:1;">
                                    <span style="color:#34d399;font-weight:600;">${currSymbol}${supVal.toLocaleString(isUS ? 'en-US' : 'en-IN', {maximumFractionDigits:0})}</span>
                                    <span style="color:#f87171;font-weight:600;">${currSymbol}${resVal.toLocaleString(isUS ? 'en-US' : 'en-IN', {maximumFractionDigits:0})}</span>
                                </div>
                                <div style="position:relative;height:5px;background:rgba(255,255,255,0.08);border-radius:9999px;overflow:hidden;">
                                    <div style="position:absolute;left:0;top:0;height:100%;width:${Math.max(0, Math.min(100, chanPos))}%;background:linear-gradient(90deg, #10b981, #38bdf8, #f87171);border-radius:9999px;"></div>
                                </div>
                                <div style="display:flex;justify-content:space-between;font-size:0.62rem;color:#94a3b8;">
                                    <span>-${distSup.toFixed(1)}%</span>
                                    <span style="color:#e2e8f0;font-weight:700;">${chanPos.toFixed(0)}%</span>
                                    <span>+${distRes.toFixed(1)}%</span>
                                </div>
                            </div>
                        `;
                        flashBg(srCell);
                    }

                    // 7. Channel Position
                    const chanPosCell = rowEl.querySelector('.cell-channel-position');
                    if (chanPosCell && m.channel_position_pct !== null && m.channel_position_pct !== undefined) {
                        chanPosCell.textContent = Number(m.channel_position_pct).toFixed(0) + '%';
                    }

                    // 8. 52W High / Low
                    const hlCell = rowEl.querySelector('.cell-pct-52w-hl');
                    if (hlCell && m.pct_from_52w_high !== null && m.pct_from_52w_high !== undefined) {
                        const hVal = Number(m.pct_from_52w_high);
                        const lVal = m.pct_from_52w_low !== null && m.pct_from_52w_low !== undefined ? Number(m.pct_from_52w_low) : null;
                        hlCell.innerHTML = `<div>${hVal >= 0 ? '+' : ''}${hVal.toFixed(1)}% H</div>${lVal !== null ? `<div style="font-size:0.65rem;color:#94a3b8;">${lVal >= 0 ? '+' : ''}${lVal.toFixed(1)}% L</div>` : ''}`;
                    }

                    // 9. Quality Scores
                    const qualCell = rowEl.querySelector('.cell-quality-scores');
                    if (qualCell) {
                        const q1 = (m.q1_earnings_score !== null && m.q1_earnings_score !== undefined) ? `${m.q1_earnings_score}/9` : '—';
                        const q2 = (m.q2_earnings_score !== null && m.q2_earnings_score !== undefined) ? `${m.q2_earnings_score}/9` : '—';
                        const q3 = (m.q3_earnings_score !== null && m.q3_earnings_score !== undefined) ? `${m.q3_earnings_score}/9` : '—';
                        const q1t = (m.q1_ai_summary || `Q1 Quality: ${q1}`).replace(/"/g, '&quot;');
                        const q2t = (m.q2_ai_summary || `Q2 Quality: ${q2}`).replace(/"/g, '&quot;');
                        const q3t = (m.q3_ai_summary || `Q3 Quality: ${q3}`).replace(/"/g, '&quot;');
                        qualCell.innerHTML = `
                            <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q1t}">${q1}</span> |
                            <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q2t}">${q2}</span> |
                            <span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="${q3t}">${q3}</span>
                        `;
                    }
                    const avgCell = rowEl.querySelector('.cell-prev-3q-score');
                    if (avgCell && m.prev_3q_earnings_score !== null && m.prev_3q_earnings_score !== undefined) {
                        avgCell.textContent = `${m.prev_3q_earnings_score}/9`;
                    }
                });

                // Also update stock modal if open for this ticker
                const modal = document.getElementById('stockDetailModal');
                if (modal && modal.style.display !== 'none' && this.currentModalTicker === cleanTicker) {
                    if (typeof this.refreshStockModalLivePrice === 'function') {
                        this.refreshStockModalLivePrice(cleanTicker);
                    }
                }
            },

// =========================================================================
// 🔄 Ticker On-Demand Recalculate & Audit Trail
// =========================================================================
            async recalculateRow(ticker, btn) {
                if (!ticker) return;
                const originalHtml = btn ? btn.innerHTML : '🔄 Recalc';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="loading-spinner"></span> Recalc...';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/ticker/recalculate?ticker=' + encodeURIComponent(ticker), {
                        method: 'POST',
                    });
                    const data = await res.json();
                    if (!res.ok || !data.success) {
                        alert('Recalculation error: ' + (data.detail || data.error || 'Failed'));
                        return;
                    }

                    // Update DOM row cells across all active lists
                    if (data.updated_metrics) {
                        this.updateDomRowWithMetrics(ticker, data.updated_metrics);
                    }

                    // Render Custom Recalculation Alert / Modal
                    this.showRecalculateResultModal(data);

                } catch (err) {
                    console.error('Error recalculating row for ' + ticker, err);
                    alert('Network error while recalculating ' + ticker + ': ' + err.message);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalHtml;
                    }
                }
            },

            showRecalculateResultModal(data) {
                const existing = document.getElementById('recalculateResultModal');
                if (existing) existing.remove();

                const isUpdated = Boolean(data.has_changes);
                const titleBg = isUpdated ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)';
                const titleBorder = isUpdated ? '#10b981' : '#3b82f6';
                const statusBadge = isUpdated 
                    ? '<span style="background:#10b981;color:#fff;padding:0.2rem 0.5rem;border-radius:9999px;font-size:0.75rem;font-weight:700;">🟢 METRICS UPDATED</span>' 
                    : '<span style="background:rgba(255,255,255,0.15);color:var(--light);padding:0.2rem 0.5rem;border-radius:9999px;font-size:0.75rem;font-weight:700;">⚪ NO CHANGES</span>';

                let changesHtml = '';
                if (data.changes_summary && data.changes_summary.length) {
                    changesHtml = '<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;padding:0.75rem;margin:0.75rem 0;font-size:0.85rem;line-height:1.6;">' +
                        '<div style="font-weight:700;color:var(--light);margin-bottom:0.4rem;">Summary of Diff:</div>' +
                        data.changes_summary.map(c => '<div style="display:flex;align-items:center;gap:0.4rem;"><span style="color:' + (isUpdated ? '#34d399' : 'var(--muted)') + ';">•</span> <span>' + c + '</span></div>').join('') +
                        '</div>';
                }

                const modalHtml = `
                <div id="recalculateResultModal" style="position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:99999;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);">
                    <div style="background:#0f172a;border:1px solid ${titleBorder};border-radius:0.75rem;max-width:520px;width:100%;box-shadow:0 20px 40px rgba(0,0,0,0.6);overflow:hidden;color:var(--light);animation:fadeIn 0.2s ease-out;">
                        <div style="padding:1rem 1.25rem;background:${titleBg};border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;">
                            <div style="display:flex;align-items:center;gap:0.6rem;">
                                <span style="font-size:1.3rem;">${isUpdated ? '⚡' : '🔍'}</span>
                                <h3 style="margin:0;font-size:1.05rem;font-weight:700;">${data.ticker} Recalculation</h3>
                            </div>
                            <div>${statusBadge}</div>
                        </div>
                        <div style="padding:1.25rem;">
                            <p style="margin:0 0 0.5rem 0;font-size:0.88rem;color:var(--muted);">
                                ${isUpdated ? 'Live market data and earnings calendars were refreshed. The following metrics changed:' : 'Live check completed. All earnings dates, price highs/lows, and quality scores are currently matching the latest market state.'}
                            </p>
                            ${changesHtml}
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:1rem;font-size:0.75rem;color:var(--muted);">
                                <span>Refreshed at: ${data.refreshed_at || new Date().toLocaleTimeString()}</span>
                                <span style="cursor:pointer;color:#93c5fd;text-decoration:underline;" onclick="app.showTickerAuditModal('${data.ticker}')">View Audit Trail 📜</span>
                            </div>
                        </div>
                        <div style="padding:0.75rem 1.25rem;background:rgba(0,0,0,0.2);border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:flex-end;">
                            <button type="button" class="btn btn-sm btn-primary" onclick="document.getElementById('recalculateResultModal').remove()">Done</button>
                        </div>
                    </div>
                </div>`;

                const wrap = document.createElement('div');
                wrap.innerHTML = modalHtml;
                document.body.appendChild(wrap.firstElementChild);
            },

            async showTickerAuditModal(ticker) {
                const existing = document.getElementById('tickerAuditModal');
                if (existing) existing.remove();

                const sym = (ticker || '').trim().toUpperCase();
                const title = sym ? `${sym} Audit History` : 'Global Recalculation Audit Trail';

                const modalEl = document.createElement('div');
                modalEl.id = 'tickerAuditModal';
                modalEl.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:99999;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);';
                modalEl.innerHTML = `
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.15);border-radius:0.75rem;max-width:750px;width:100%;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 25px 50px rgba(0,0,0,0.8);overflow:hidden;color:var(--light);">
                        <div style="padding:1rem 1.25rem;background:rgba(255,255,255,0.04);border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;">
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span style="font-size:1.2rem;">📜</span>
                                <h3 style="margin:0;font-size:1.05rem;font-weight:700;">${title}</h3>
                            </div>
                            <button type="button" class="btn btn-sm" onclick="document.getElementById('tickerAuditModal').remove()" style="background:rgba(255,255,255,0.1);color:var(--light);border:none;border-radius:0.3rem;cursor:pointer;">✕</button>
                        </div>
                        <div id="auditModalBody" style="padding:1.25rem;overflow-y:auto;flex:1;">
                            <div style="text-align:center;padding:2rem;color:var(--muted);"><span class="loading-spinner"></span> Loading audit logs...</div>
                        </div>
                        <div style="padding:0.75rem 1.25rem;background:rgba(0,0,0,0.3);border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;color:var(--muted);">
                            <span>Audit records are permanently preserved in the local/cloud database.</span>
                            <button type="button" class="btn btn-sm btn-primary" onclick="document.getElementById('tickerAuditModal').remove()">Close</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modalEl);

                try {
                    const url = API_BASE + '/api/v1/ticker/audit-log' + (sym ? '?ticker=' + encodeURIComponent(sym) : '') + '&limit=50';
                    const res = await fetch(url);
                    const list = await res.json();

                    const bodyEl = document.getElementById('auditModalBody');
                    if (!bodyEl) return;

                    if (!Array.isArray(list) || !list.length) {
                        bodyEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);">No audit entries found for this ticker yet. Click <strong>🔄 Recalc</strong> on a results row to trigger a live refresh.</div>';
                        return;
                    }

                    let tableHtml = `
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;font-size:0.82rem;text-align:left;">
                            <thead>
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.15);color:var(--muted);">
                                    <th style="padding:0.5rem 0.6rem;">Timestamp</th>
                                    <th style="padding:0.5rem 0.6rem;">Ticker</th>
                                    <th style="padding:0.5rem 0.6rem;">Status</th>
                                    <th style="padding:0.5rem 0.6rem;">Changes / Diff</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;

                    list.forEach(entry => {
                        const statusBadge = entry.has_changes
                            ? '<span style="background:rgba(16,185,129,0.2);color:#34d399;padding:0.15rem 0.45rem;border-radius:9999px;font-size:0.72rem;font-weight:700;">🟢 UPDATED</span>'
                            : '<span style="background:rgba(255,255,255,0.08);color:var(--muted);padding:0.15rem 0.45rem;border-radius:9999px;font-size:0.72rem;">⚪ NO CHANGE</span>';
                        
                        const summaryLines = (entry.changes_summary || '').split('\n').filter(Boolean);
                        const summaryDisplay = summaryLines.map(s => `<div style="font-size:0.78rem;margin:0.15rem 0;">• ${s}</div>`).join('') || '—';

                        tableHtml += `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                                <td style="padding:0.6rem;white-space:nowrap;color:var(--muted);">${entry.refreshed_at || '—'}</td>
                                <td style="padding:0.6rem;font-weight:700;color:var(--light);">${entry.ticker}</td>
                                <td style="padding:0.6rem;">${statusBadge}</td>
                                <td style="padding:0.6rem;color:var(--light);">${summaryDisplay}</td>
                            </tr>
                        `;
                    });

                    tableHtml += `</tbody></table></div>`;
                    bodyEl.innerHTML = tableHtml;

                } catch (e) {
                    console.error('Error fetching audit history:', e);
                    const bodyEl = document.getElementById('auditModalBody');
                    if (bodyEl) bodyEl.innerHTML = '<div style="color:#f87171;padding:1rem;">Failed to load audit history: ' + e.message + '</div>';
                }
            },

            async recalculateAllVisibleResults(btn) {
                const rows = Array.from(document.querySelectorAll('#resultsReportSections table.results-table tbody tr:not(.row-drawer-tr):not([style*="display: none"])'));
                if (!rows.length) {
                    alert('No visible stocks in current report to recalculate.');
                    return;
                }

                const tickers = Array.from(new Set(rows.map(r => r.getAttribute('data-ticker')).filter(Boolean)));
                if (!tickers.length) {
                    alert('No tickers found to recalculate.');
                    return;
                }

                const originalText = btn ? btn.innerHTML : '🔄 Recalc Window';
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = `<span class="loading-spinner"></span> Recalculating (0/${tickers.length})...`;
                }

                let updatedCount = 0;
                let processed = 0;

                try {
                    // Process in chunks of 5 to allow live UI updates
                    const chunkSize = 5;
                    for (let i = 0; i < tickers.length; i += chunkSize) {
                        const chunk = tickers.slice(i, i + chunkSize);
                        const res = await fetch(API_BASE + '/api/v1/ticker/recalculate-batch', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ tickers: chunk })
                        });
                        const data = await res.json();
                        if (data && data.success && Array.isArray(data.results)) {
                            data.results.forEach(item => {
                                if (item.has_changes) updatedCount++;
                                if (item.ticker && item.updated_metrics) {
                                    const rowId = 'row_' + item.ticker.replace(/[^a-zA-Z0-9]/g, '_');
                                    const rowEl = document.getElementById(rowId);
                                    if (rowEl) {
                                        const m = item.updated_metrics;
                                        const pCell = rowEl.querySelector('.cell-current-price');
                                        if (pCell && m.current_price !== null && m.current_price !== undefined) {
                                            const liveDot = rowEl.querySelector('.live-pulse-dot') ? '<span class="live-pulse-dot" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;margin-right:0.35rem;" title="Live Active Session (±3D Results Window)"></span>' : '';
                                            pCell.innerHTML = `<div style="display:flex;align-items:center;">${liveDot}<span>${Number(m.current_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></div>`;
                                        }
                                        const ret3Cell = rowEl.querySelector('.cell-three-day-return');
                                        if (ret3Cell && m.three_day_return_pct !== null && m.three_day_return_pct !== undefined) {
                                            const val = Number(m.three_day_return_pct);
                                            ret3Cell.textContent = (val > 0 ? '+' : '') + val.toFixed(2) + '%';
                                            ret3Cell.style.color = val >= 0 ? '#93c5fd' : '#fca5a5';
                                        }
                                        const ret7Cell = rowEl.querySelector('.cell-seven-day-return');
                                        if (ret7Cell && m.seven_day_return_pct !== null && m.seven_day_return_pct !== undefined) {
                                            const val = Number(m.seven_day_return_pct);
                                            ret7Cell.textContent = (val > 0 ? '+' : '') + val.toFixed(2) + '%';
                                            ret7Cell.style.color = val >= 0 ? '#38bdf8' : '#f87171';
                                        }
                                        const retCell = rowEl.querySelector('.cell-thirty-day-return');
                                        if (retCell && m.thirty_day_return_pct !== null && m.thirty_day_return_pct !== undefined) {
                                            const val = Number(m.thirty_day_return_pct);
                                            retCell.textContent = (val > 0 ? '+' : '') + val.toFixed(2) + '%';
                                            retCell.style.color = val >= 0 ? '#34d399' : '#f87171';
                                        }
                                    }
                                }
                            });
                        }
                        processed += chunk.length;
                        if (btn) {
                            btn.innerHTML = `<span class="loading-spinner"></span> Recalculating (${processed}/${tickers.length})...`;
                        }
                    }

                    alert(`Batch Recalculation Complete: ${processed} stocks refreshed. ${updatedCount} stocks updated with new market metrics.`);
                } catch (err) {
                    console.error('Batch recalculation failed:', err);
                    alert('Batch recalculation error: ' + err.message);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalText;
                    }
                }
            }
});
})(); // end recalculate IIFE
