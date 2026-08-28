// =========================================================================
// scanner — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[scanner] window.app not initialized'); return; }
            // =========================================================================
            // 🔍 Active Multi-Category Stock Scanner Hub
            // =========================================================================
            activeScannerCategory: 'order_wins',
            scannerCategoriesData: [],
            scannerCandidatesData: [],

            async loadScanner() {
                const pillsEl = document.getElementById('scannerCategoryPills');
                const tbody = document.getElementById('scannerCandidatesTableBody');
                if (!pillsEl || !tbody) return;

                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                if (!this.scannerCategoriesData.length) {
                    pillsEl.innerHTML = '<div style="color:var(--muted);font-size:0.8rem;padding:0.3rem;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Loading scanner categories...</div>';
                }

                try {
                    const res = await fetch(API_BASE + '/api/v1/scanner/categories?universe=' + encodeURIComponent(wl));
                    const data = await res.json();
                    this.scannerCategoriesData = data.categories || [];
                    this.renderScannerCategoriesPills();

                    // Default to 'all' category if not set or not matching
                    if (!this.activeScannerCategory) {
                        this.activeScannerCategory = 'all';
                    }
                    if (this.activeScannerCategory !== 'all' && !this.scannerCategoriesData.some(c => c.id === this.activeScannerCategory) && this.scannerCategoriesData.length) {
                        this.activeScannerCategory = 'all';
                    }

                    this.renderScannerCategoriesPills();
                    await this.loadScannerCategoryCandidates(this.activeScannerCategory);
                } catch (e) {
                    console.error('Error loading scanner categories:', e);
                }
            },

            renderScannerCategoriesPills() {
                const pillsEl = document.getElementById('scannerCategoryPills');
                if (!pillsEl) return;
                const items = this.scannerCategoriesData || [];
                const totalAllCount = items.reduce((acc, c) => acc + (Number(c.count) || 0), 0);

                const allPill = {
                    id: 'all',
                    icon: '🌟',
                    badge: 'All Categories',
                    count: totalAllCount,
                };
                const pillList = [allPill, ...items];

                pillsEl.innerHTML = pillList.map(c => {
                    const isActive = c.id === this.activeScannerCategory;
                    const pillBg = isActive ? 'linear-gradient(135deg, #0284c7, #4f46e5)' : 'rgba(255,255,255,0.06)';
                    const pillBorder = isActive ? 'border: 1px solid #38bdf8;' : 'border: 1px solid rgba(255,255,255,0.1);';
                    const pillColor = isActive ? '#fff' : 'var(--light)';
                    const badgeBg = isActive ? 'rgba(255,255,255,0.25)' : 'rgba(59,130,246,0.2)';
                    const badgeColor = isActive ? '#fff' : '#60a5fa';

                    return '<button type="button" onclick="app.selectScannerCategory(\'' + c.id + '\')" class="btn btn-sm" style="padding:0.35rem 0.75rem;border-radius:2rem;' + pillBorder + 'background:' + pillBg + ';color:' + pillColor + ';font-size:0.78rem;font-weight:600;display:inline-flex;align-items:center;gap:0.4rem;cursor:pointer;transition:all 0.15s ease;">' +
                        '<span>' + c.icon + ' ' + c.badge + '</span>' +
                        '<span style="background:' + badgeBg + ';color:' + badgeColor + ';padding:0.1rem 0.45rem;border-radius:1rem;font-size:0.7rem;font-weight:700;">' + c.count + '</span>' +
                    '</button>';
                }).join('');
            },

            async selectScannerCategory(catId) {
                this.activeScannerCategory = catId;
                this.renderScannerCategoriesPills();
                await this.loadScannerCategoryCandidates(catId);
            },

            async loadScannerCategoryCandidates(catId) {
                const tbody = document.getElementById('scannerCandidatesTableBody');
                const titleEl = document.getElementById('activeCatTitle');
                const descEl = document.getElementById('activeCatDescription');
                const countBadge = document.getElementById('activeCatCountBadge');

                let catMeta = (this.scannerCategoriesData || []).find(c => c.id === catId);
                if (catId === 'all') {
                    catMeta = {
                        icon: '🌟',
                        name: 'All Scanner Setups & Catalysts',
                        description: 'Unified multi-category scanner across all Fundamental News Catalysts, Technical Squeeze Coils, 52W Highs, and Momentum Waves.'
                    };
                } else if (!catMeta) {
                    catMeta = { icon: '🔍', name: catId, description: 'Active market candidates matching this setup.' };
                }

                if (titleEl) titleEl.innerHTML = (catMeta.icon || '🔍') + ' ' + (catMeta.name || catId);
                if (descEl) descEl.textContent = catMeta.description || 'Active market candidates matching this setup.';

                if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted);"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Scanning candidates for ' + (catMeta.name || catId) + '...</td></tr>';

                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                try {
                    const res = await fetch(API_BASE + '/api/v1/scanner/category/' + encodeURIComponent(catId) + '?universe=' + encodeURIComponent(wl) + '&limit=50');
                    const data = await res.json();
                    this.scannerCandidatesData = data.candidates || [];
                    if (countBadge) countBadge.textContent = this.scannerCandidatesData.length + ' stocks';
                    this.renderScannerCandidates();
                } catch (e) {
                    console.error('Error loading category candidates:', e);
                    if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="padding:1rem;text-align:center;color:var(--red);">Failed loading category candidates.</td></tr>';
                }
            },

            filterScannerCandidates() {
                this.renderScannerCandidates();
            },

            renderScannerCandidates() {
                const tbody = document.getElementById('scannerCandidatesTableBody');
                if (!tbody) return;

                const searchQ = (document.getElementById('scannerSearchInput')?.value || '').toLowerCase().trim();
                const sortBy = document.getElementById('scannerSortBy')?.value || 'confidence';

                let filtered = (this.scannerCandidatesData || []).filter(item => {
                    if (searchQ) {
                        const mTicker = (item.ticker || '').toLowerCase().includes(searchQ);
                        const mName = (item.stock_name || '').toLowerCase().includes(searchQ);
                        const mText = (item.why_it_matches || '').toLowerCase().includes(searchQ);
                        if (!mTicker && !mName && !mText) return false;
                    }
                    return true;
                });

                if (sortBy === 'gain') {
                    filtered.sort((a, b) => (b.return_pct || 0) - (a.return_pct || 0));
                } else if (sortBy === 'volume') {
                    filtered.sort((a, b) => (b.volume_multiple || 0) - (a.volume_multiple || 0));
                } else {
                    filtered.sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0));
                }

                if (!filtered.length) {
                    tbody.innerHTML = '<tr><td colspan="11" style="padding:1.5rem;text-align:center;color:var(--muted);">No candidates matching selected category in this universe. Click "⚡ Deep Sweep All Categories" to refresh feeds.</td></tr>';
                    return;
                }

                tbody.innerHTML = filtered.map((c, idx) => {
                    const rank = idx + 1;
                    const ret = Number(c.return_pct || 0);
                    const retClass = ret >= 0 ? 'price-positive' : 'price-negative';
                    const retSign = ret >= 0 ? '+' : '';

                    // Price formatters
                    const sigPrice = c.signal_price || c.current_price;
                    const sigPriceStr = sigPrice ? '₹' + Number(sigPrice).toFixed(2) : '—';
                    const curPriceStr = c.current_price ? '₹' + Number(c.current_price).toFixed(2) : '—';
                    const triggerStr = c.trigger_level ? '₹' + Number(c.trigger_level).toFixed(2) : '—';
                    const targetStr = c.target_price ? '₹' + Number(c.target_price).toFixed(2) : '—';
                    const stopStr = c.stop_loss ? '₹' + Number(c.stop_loss).toFixed(2) : '—';

                    // News Date and Published Time
                    const newsDate = c.signal_date || (c.published_at ? c.published_at.substring(0, 10) : 'Today');
                    const newsHeadline = c.headline || c.catalyst_summary || c.why_it_matches || 'Market Catalyst';

                    // Severity Styling
                    const sev = (c.severity || 'MEDIUM').toUpperCase();
                    let sevBg = 'rgba(59,130,246,0.15)';
                    let sevText = '#60a5fa';
                    let sevBorder = 'rgba(59,130,246,0.3)';
                    let sevLabel = '📈 MEDIUM';

                    if (sev === 'HIGH') {
                        sevBg = 'rgba(234,179,8,0.18)';
                        sevText = '#fde68a';
                        sevBorder = 'rgba(234,179,8,0.4)';
                        sevLabel = '⚡ HIGH';
                    } else if (sev === 'RISK' || c.category_id === 'risk_alerts') {
                        sevBg = 'rgba(239,68,68,0.2)';
                        sevText = '#f87171';
                        sevBorder = 'rgba(239,68,68,0.5)';
                        sevLabel = '⚠️ RISK';
                    } else if (sev === 'LOW') {
                        sevBg = 'rgba(148,163,184,0.12)';
                        sevText = '#cbd5e1';
                        sevBorder = 'rgba(148,163,184,0.25)';
                        sevLabel = '⚖️ LOW';
                    }

                    // Outcome Badge Styling
                    const outcomeBadge = c.outcome_badge || 'blue';
                    const outcomeLabel = c.outcome_label || 'In Play ⏳';
                    const badgeStyles = {
                        emerald: 'background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.35);',
                        amber: 'background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);',
                        rose: 'background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.35);',
                        blue: 'background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);',
                    };
                    const outcomeStyle = badgeStyles[outcomeBadge] || badgeStyles.blue;

                    const confScore = c.confidence_score || 75;
                    const confColor = confScore >= 85 ? '#34d399' : (confScore >= 70 ? '#38bdf8' : '#fbbf24');

                    return '<tr>' +
                        '<td style="text-align:center;color:var(--muted);font-weight:700;">' + rank + '</td>' +
                        '<td style="padding:0.5rem 0.65rem;">' +
                            '<div><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="font-weight:700;font-size:0.85rem;color:var(--light);text-decoration:none;">' + (c.stock_name || c.ticker) + '</a></div>' +
                            '<div style="font-size:0.72rem;color:var(--muted);margin-top:1px;"><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-family:var(--font-mono);">' + c.ticker + '</a><a href="/stock/' + encodeURIComponent(c.ticker) + '" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.25rem;font-size:0.75rem;" title="Open profile in new tab">↗</a></div>' +
                        '</td>' +
                        '<td style="padding:0.5rem 0.65rem;max-width:340px;">' +
                            '<div style="display:flex;align-items:center;gap:0.35rem;margin-bottom:0.2rem;">' +
                                '<span style="font-size:0.62rem;color:#94a3b8;font-family:var(--font-mono);font-weight:600;">📅 ' + newsDate + '</span>' +
                                (c.category_badge ? '<span class="signal-badge" style="background:rgba(59,130,246,0.12);color:#93c5fd;font-size:0.6rem;padding:0.04rem 0.3rem;border:1px solid rgba(59,130,246,0.25);border-radius:0.25rem;">' + c.category_badge + '</span>' : '') +
                            '</div>' +
                            '<div style="font-size:0.75rem;color:#f1f5f9;line-height:1.35;font-weight:500;white-space:normal;word-break:break-word;">' + newsHeadline + '</div>' +
                            (c.why_it_matches && c.why_it_matches !== newsHeadline ? '<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.2rem;line-height:1.3;">' + c.why_it_matches + '</div>' : '') +
                        '</td>' +
                        '<td style="text-align:right;padding:0.5rem 0.65rem;font-family:var(--font-mono);color:#93c5fd;font-size:0.76rem;white-space:nowrap;">' +
                            '<div style="font-weight:700;">' + sigPriceStr + '</div>' +
                            '<div style="font-size:0.62rem;color:#64748b;">Signal Base</div>' +
                        '</td>' +
                        '<td style="text-align:right;padding:0.5rem 0.65rem;font-family:var(--font-mono);font-size:0.76rem;white-space:nowrap;">' +
                            '<div style="font-weight:800;color:#f8fafc;font-size:0.84rem;">' + curPriceStr + '</div>' +
                            '<div style="font-size:0.62rem;color:#94a3b8;">Live Price</div>' +
                        '</td>' +
                        '<td style="text-align:right;padding:0.5rem 0.65rem;font-family:var(--font-mono);color:#fca5a5;font-size:0.76rem;white-space:nowrap;">' +
                            '<div style="font-weight:600;">' + triggerStr + '</div>' +
                            '<div style="font-size:0.62rem;color:#64748b;">Breakout Res</div>' +
                        '</td>' +
                        '<td style="text-align:right;padding:0.5rem 0.65rem;font-family:var(--font-mono);font-size:0.72rem;white-space:nowrap;">' +
                            '<div style="color:#34d399;font-weight:700;" title="Target Price">T: ' + targetStr + '</div>' +
                            '<div style="color:#f87171;font-weight:600;" title="Stop Loss">SL: ' + stopStr + '</div>' +
                        '</td>' +
                        '<td style="text-align:right;padding:0.5rem 0.65rem;font-family:var(--font-mono);white-space:nowrap;">' +
                            '<strong class="' + retClass + '" style="font-size:0.84rem;">' + retSign + ret.toFixed(2) + '%</strong>' +
                            (c.volume_multiple ? '<div style="font-size:0.62rem;color:#94a3b8;">Vol: ' + Number(c.volume_multiple).toFixed(1) + 'x</div>' : '') +
                        '</td>' +
                        '<td style="text-align:center;padding:0.5rem 0.65rem;white-space:nowrap;">' +
                            '<span style="display:inline-block;font-size:0.68rem;font-weight:700;padding:0.12rem 0.45rem;border-radius:4px;' + outcomeStyle + '">' + outcomeLabel + '</span>' +
                        '</td>' +
                        '<td style="text-align:center;padding:0.5rem 0.65rem;white-space:nowrap;">' +
                            '<div style="margin-bottom:0.15rem;"><span style="display:inline-block;background:' + sevBg + ';color:' + sevText + ';border:1px solid ' + sevBorder + ';font-size:0.62rem;font-weight:800;padding:0.08rem 0.35rem;border-radius:3px;font-family:var(--font-mono);">' + sevLabel + '</span></div>' +
                            '<div style="font-size:0.72rem;color:' + confColor + ';font-weight:700;font-family:var(--font-mono);">' + confScore + '% Conviction</div>' +
                        '</td>' +
                        '<td style="text-align:center;padding:0.5rem 0.65rem;white-space:nowrap;">' +
                            '<div style="display:inline-flex;gap:0.3rem;justify-content:center;align-items:center;">' +
                                '<button type="button" onclick="event.stopPropagation(); app.openAddToWatchlistModal(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.72rem;background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.35);border-radius:0.3rem;" title="Add to Watchlist">⭐</button>' +
                                '<button type="button" onclick="event.stopPropagation(); app.runConsensusForStock(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.72rem;background:rgba(99,102,241,0.2);color:#c7d2fe;border:1px solid rgba(99,102,241,0.4);border-radius:0.3rem;" title="Run AI Consensus">🧠</button>' +
                                '<button type="button" onclick="event.stopPropagation(); app.showOhlcvBenchmarkModal(\'' + c.ticker + '\')" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.72rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);border-radius:0.3rem;" title="14D OHLCV Benchmark">📊</button>' +
                            '</div>' +
                        '</td>' +
                    '</tr>';
                }).join('');
            },

            async deepSweepScanner() {
                const btn = document.getElementById('scannerSweepBtn');
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Sweeping All Categories...';
                }
                const wl = localStorage.getItem('selectedGlobalWatchlist') || 'NSE_TOP';
                try {
                    const res = await fetch(API_BASE + '/api/v1/scanner/sweep', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({universe: wl})
                    });
                    const data = await res.json();
                    await this.loadScanner();
                } catch (e) {
                    console.error('Error executing deep sweep:', e);
                } finally {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '⚡ Deep Sweep All Categories';
                    }
                }
            },

})(); // end scanner IIFE
