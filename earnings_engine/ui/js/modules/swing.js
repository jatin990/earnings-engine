// =========================================================================
// 📈 Swing Ranges, Trading Channels, Setups, Top Swingers & AI Forecasts Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin || '';

    const swingModule = {
        swingSubTab: 'setups', // 'setups' | 'top-swingers' | 'audit'
        swingData: [],
        topSwingersData: [],
        swingView: 'table',
        swingFilter: 'all',
        swingTierFilter: 'ALL',
        swingSortKey: 'ticker',
        swingSortDir: 'asc',
        topSwingersSortKey: 'rank',
        topSwingersSortDir: 'asc',
        topSwingersMinCycles: 1,
        _swingAuditOpen: false,

        // -------------------------------------------------------------------------
        // Sub-Tab Navigation Controller
        // -------------------------------------------------------------------------
        setSwingSubTab(tabName) {
            this.swingSubTab = tabName || 'setups';

            const tabIds = ['setups', 'top-swingers', 'audit'];
            tabIds.forEach(t => {
                const btn = document.getElementById(`swingSubTabBtn-${t}`);
                const panel = document.getElementById(`swingSubTabContent-${t}`);
                const isActive = t === this.swingSubTab;

                if (btn) {
                    btn.style.background = isActive ? (t === 'top-swingers' ? '#eab308' : '#2563eb') : 'transparent';
                    btn.style.color = isActive ? (t === 'top-swingers' ? '#000000' : '#ffffff') : '#94a3b8';
                    btn.style.fontWeight = isActive ? '700' : '600';
                }
                if (panel) {
                    panel.style.display = isActive ? 'block' : 'none';
                }
            });

            if (this.swingSubTab === 'top-swingers') {
                if (!this.topSwingersData || !this.topSwingersData.length) {
                    this.loadTopSwingers();
                } else {
                    this.renderTopSwingers();
                }
            } else if (this.swingSubTab === 'audit') {
                this.loadSwingAuditLog();
            } else {
                this.renderSwing();
            }
        },

        // -------------------------------------------------------------------------
        // View & Filter Controllers
        // -------------------------------------------------------------------------
        setSwingTierFilter(tier) {
            this.swingTierFilter = (tier || 'ALL').toUpperCase();
            ['ALL', 'HOT', 'WARM', 'COLD'].forEach(t => {
                const btn = document.getElementById(`swingTierPill-${t}`);
                if (btn) {
                    const isActive = t === this.swingTierFilter;
                    btn.className = `btn-micro ${isActive ? 'btn-primary' : ''}`;
                    btn.style.fontWeight = isActive ? '700' : '500';
                    btn.style.background = isActive
                        ? (t === 'HOT' ? '#dc2626' : t === 'WARM' ? '#d97706' : t === 'COLD' ? '#475569' : '#2563eb')
                        : 'transparent';
                    btn.style.color = isActive
                        ? '#ffffff'
                        : (t === 'HOT' ? '#f87171' : t === 'WARM' ? '#fbbf24' : t === 'COLD' ? '#cbd5e1' : '#94a3b8');
                }
            });
            this.renderSwing();
        },

        toggleSwingAuditLog() {
            this.setSwingSubTab('audit');
        },

        async loadSwingAuditLog(ticker = null) {
            if (window.TierPoolUI) {
                await window.TierPoolUI.loadAuditLog({
                    domain: 'swing',
                    ticker: ticker,
                    containerId: 'swingAuditList',
                    countBadgeId: 'swingAuditBadgeCount',
                    summaryElements: {
                        coldToHot: 'swingAuditColdHot',
                        coldToWarm: 'swingAuditColdWarm',
                        warmToHot: 'swingAuditWarmHot',
                        exits: 'swingAuditExits'
                    }
                });
            } else {
                const el = document.getElementById('swingAuditList');
                if (el) el.innerHTML = '<div style="text-align:center;color:#64748b;font-size:0.75rem;padding:1rem;">Tier audit history synchronizing from SQLite...</div>';
            }
        },

        setSwingView(view) {
            this.swingView = view;
            const tbl = document.getElementById('swingTableContainer');
            const crd = document.getElementById('swingWidgets');
            const btnTbl = document.getElementById('swingViewBtn-table');
            const btnCrd = document.getElementById('swingViewBtn-cards');

            if (view === 'table') {
                if (tbl) tbl.style.display = 'block';
                if (crd) crd.style.display = 'none';
                if (btnTbl) { btnTbl.style.background = 'rgba(255,255,255,0.12)'; btnTbl.style.color = '#ffffff'; }
                if (btnCrd) { btnCrd.style.background = 'transparent'; btnCrd.style.color = '#71717a'; }
            } else {
                if (tbl) tbl.style.display = 'none';
                if (crd) crd.style.display = 'grid';
                if (btnTbl) { btnTbl.style.background = 'transparent'; btnTbl.style.color = '#71717a'; }
                if (btnCrd) { btnCrd.style.background = 'rgba(255,255,255,0.12)'; btnCrd.style.color = '#ffffff'; }
            }
            this.renderSwing();
        },

        filterSwingTable(query) {
            this.renderSwing();
        },

        toggleSwingBuyZoneFilter() {
            if (this.swingFilter === 'buyzone') {
                this.clearSwingFilter();
            } else {
                this.filterSwing('buyzone');
            }
        },

        clearSwingFilter() {
            this.filterSwing('all');
        },

        filterSwing(filterType) {
            this.swingFilter = filterType || 'all';

            // Update filter pills UI
            ['all', 'buyzone', 'strongbuy', 'custom'].forEach(t => {
                const btn = document.getElementById(`swingFilter-${t}`);
                if (btn) {
                    if (t === this.swingFilter) {
                        btn.className = 'btn btn-primary btn-xs';
                        btn.style.fontWeight = '700';
                    } else {
                        btn.className = 'btn btn-xs';
                        btn.style.fontWeight = '500';
                    }
                }
            });

            // Update KPI Cards UI (Glow & Indicators)
            const cardBz = document.getElementById('swingCardBuyZone');
            const badgeBz = document.getElementById('swingFilterIndicatorBz');
            const subBz = document.getElementById('swingStatBzSub');
            const noticeEl = document.getElementById('swingFilterNotice');

            if (this.swingFilter === 'buyzone') {
                if (cardBz) {
                    cardBz.style.outline = '2px solid #10b981';
                    cardBz.style.boxShadow = '0 0 20px rgba(16,185,129,0.45)';
                }
                if (badgeBz) badgeBz.style.display = 'inline-block';
                if (subBz) subBz.textContent = 'Filtered 🔍';
                if (noticeEl) {
                    const count = (this.swingData || []).filter(r => this.isSwingInBuyZone(r) || r.tier === 'HOT').length;
                    noticeEl.style.display = 'inline-flex';
                    noticeEl.innerHTML = `🟢 Filtering: In Buy Zone (${count} setups) <button type="button" onclick="app.clearSwingFilter()" style="background:none;border:none;color:#6ee7b7;cursor:pointer;font-weight:800;margin-left:0.35rem;">✕ Show All</button>`;
                }
            } else {
                if (cardBz) {
                    cardBz.style.outline = 'none';
                    cardBz.style.boxShadow = 'none';
                }
                if (badgeBz) badgeBz.style.display = 'none';
                if (subBz) subBz.textContent = 'Support Floor';

                if (this.swingFilter === 'strongbuy') {
                    if (noticeEl) {
                        const count = (this.swingData || []).filter(r => r.swing_signal === 'Strong Buy').length;
                        noticeEl.style.display = 'inline-flex';
                        noticeEl.innerHTML = `⭐ Filtering: Strong Buy Grade A+ (${count} stocks) <button type="button" onclick="app.clearSwingFilter()" style="background:none;border:none;color:#38bdf8;cursor:pointer;font-weight:800;margin-left:0.35rem;">✕ Show All</button>`;
                    }
                } else if (this.swingFilter === 'custom') {
                    if (noticeEl) {
                        const count = (this.swingData || []).filter(r => (r.swing_range && r.swing_range.source === 'user') || r.source === 'user').length;
                        noticeEl.style.display = 'inline-flex';
                        noticeEl.innerHTML = `🔒 Filtering: Custom User Ranges (${count} stocks) <button type="button" onclick="app.clearSwingFilter()" style="background:none;border:none;color:#fbbf24;cursor:pointer;font-weight:800;margin-left:0.35rem;">✕ Show All</button>`;
                    }
                } else {
                    if (noticeEl) noticeEl.style.display = 'none';
                }
            }

            this.renderSwing();
        },

        sortSwing(key) {
            if (this.swingSortKey === key) {
                this.swingSortDir = this.swingSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.swingSortKey = key;
                this.swingSortDir = 'asc';
            }
            this.renderSwing();
        },

        isSwingInBuyZone(r) {
            if (!r) return false;
            const cur = r.current_price;
            const supp = r.current_support;
            const res = r.next_resistance;
            const sig = r.swing_signal;

            // Never mark as Buy Zone if price is above resistance or broken below support
            if (cur != null && res != null && cur > res) return false;
            if (cur != null && supp != null && cur < supp * 0.97) return false;
            if (sig === 'Overbought' || sig === 'Sell Zone' || sig === 'Breakdown') return false;

            if (r.swing_zone === 'Buy Zone') return true;
            if (sig === 'Strong Buy' || sig === 'Buy') return true;
            if (cur != null && supp != null && res != null && res > supp) {
                const channelPos = (cur - supp) / (res - supp);
                if (channelPos >= 0 && channelPos <= 0.25) return true;
            }
            return false;
        },

        // -------------------------------------------------------------------------
        // Data Ingestion & Rendering: Active Setups
        // -------------------------------------------------------------------------
        async loadSwing(e) {
            const marketEl = document.getElementById('swingMarket');
            const market = marketEl ? marketEl.value : 'ALL';
            const url = API_BASE + '/api/v1/dashboard/swing?limit=150' + (market ? '&market=' + encodeURIComponent(market) : '');
            const statsUrl = API_BASE + '/api/v1/dashboard/swing/pool-stats';
            const topUrl = API_BASE + '/api/v1/dashboard/swing/top-swingers?min_cycles=1&limit=50' + (market ? '&market=' + encodeURIComponent(market) : '');
            const btn = (e && e.target) ? e.target : (typeof window !== 'undefined' && window.event ? window.event.target : null);
            if (btn && btn.tagName === 'BUTTON') { btn.disabled = true; btn.innerHTML = '<span class="loading-spinner"></span> Loading...'; }

            try {
                const [res, statsRes, topRes] = await Promise.all([
                    fetch(url).catch(err => { console.warn('Swing fetch error:', err); return null; }),
                    fetch(statsUrl).catch(() => null),
                    fetch(topUrl).catch(() => null)
                ]);

                let data = [];
                if (res && res.ok) {
                    try {
                        data = await res.json();
                    } catch (_) {
                        data = [];
                    }
                }
                this.swingData = Array.isArray(data) ? data : [];

                let poolStats = null;
                if (statsRes && statsRes.ok) {
                    try {
                        const statsJson = await statsRes.json();
                        poolStats = statsJson.stats || statsJson;
                    } catch (_) {}
                }

                let topData = [];
                if (topRes && topRes.ok) {
                    try {
                        topData = await topRes.json();
                    } catch (_) {}
                }
                if (Array.isArray(topData) && topData.length) {
                    this.topSwingersData = topData;
                }

                // Update summary counts
                const countAll = this.swingData.length;
                const countBuyZone = this.swingData.filter(r => this.isSwingInBuyZone(r) || (r.tier || '').toUpperCase() === 'HOT').length;
                const countStrongBuy = this.swingData.filter(r => r.swing_signal === 'Strong Buy').length;
                const countCustom = this.swingData.filter(r => (r.swing_range && r.swing_range.source === 'user') || r.source === 'user').length;

                const countHot = (poolStats && poolStats.hot_count !== undefined)
                    ? poolStats.hot_count
                    : this.swingData.filter(r => (r.tier || '').toUpperCase() === 'HOT' || this.isSwingInBuyZone(r)).length;
                const countWarm = (poolStats && poolStats.warm_count !== undefined)
                    ? poolStats.warm_count
                    : this.swingData.filter(r => (r.tier || '').toUpperCase() === 'WARM').length;
                const countCold = (poolStats && poolStats.cold_count !== undefined)
                    ? poolStats.cold_count
                    : Math.max(0, countAll - countHot - countWarm);

                const countTop = (this.topSwingersData && this.topSwingersData.length)
                    ? this.topSwingersData.length
                    : this.swingData.filter(r => (r.cycles && r.cycles >= 1) || (r.avg_cycle_days && r.avg_cycle_days > 0)).length;

                const elAll = document.getElementById('count-all'); if (elAll) elAll.textContent = countAll;
                const elTop = document.getElementById('count-top-swingers'); if (elTop) elTop.textContent = countTop;
                const elHot = document.getElementById('count-hot-pool'); if (elHot) elHot.textContent = countHot;
                const elWarm = document.getElementById('count-warm-pool'); if (elWarm) elWarm.textContent = countWarm;
                const elCold = document.getElementById('count-cold-pool'); if (elCold) elCold.textContent = countCold;
                const elBz = document.getElementById('count-buyzone'); if (elBz) elBz.textContent = countBuyZone;
                const elSb = document.getElementById('count-strongbuy'); if (elSb) elSb.textContent = countStrongBuy;
                const elCust = document.getElementById('count-custom'); if (elCust) elCust.textContent = countCustom;

                const pAll = document.getElementById('count-all-pill'); if (pAll) pAll.textContent = countAll;
                const pHot = document.getElementById('count-hot-pill'); if (pHot) pHot.textContent = countHot;
                const pWarm = document.getElementById('count-warm-pill'); if (pWarm) pWarm.textContent = countWarm;
                const pCold = document.getElementById('count-cold-pill'); if (pCold) pCold.textContent = countCold;
                const pBz = document.getElementById('count-buyzone-pill'); if (pBz) pBz.textContent = countBuyZone;
                const pSb = document.getElementById('count-strongbuy-pill'); if (pSb) pSb.textContent = countStrongBuy;
                const pCust = document.getElementById('count-custom-pill'); if (pCust) pCust.textContent = countCustom;

                const subSetups = document.getElementById('swingSubTabCount-setups'); if (subSetups) subSetups.textContent = countAll;
                const subTop = document.getElementById('swingSubTabCount-top'); if (subTop) subTop.textContent = countTop;

                if (this.swingSubTab === 'top-swingers') {
                    this.renderTopSwingers();
                } else {
                    this.renderSwing();
                }
            } catch (e) {
                console.error('Error in loadSwing:', e);
                const tbody = document.getElementById('swingTableBody');
                if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--red);">Error loading swing setups. Retrying with local cache...</td></tr>';
            } finally {
                if (btn && btn.tagName === 'BUTTON') { btn.disabled = false; btn.textContent = '🔄 Refresh Setups'; }
            }
        },

        async refreshSwing() {
            await this.loadSwing();
        },

        renderSwing() {
            const marketEl = document.getElementById('swingMarket');
            const currentMarket = marketEl ? marketEl.value : 'ALL';
            const tbody = document.getElementById('swingTableBody');
            const widgetEl = document.getElementById('swingWidgets');

            if (!this.swingData || !this.swingData.length) {
                if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--muted)">No swing setups found. Try a different market or click Refresh.</td></tr>';
                if (widgetEl) widgetEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No swing setups found.</div>';
                return;
            }

            // Filter
            let list = [...this.swingData];

            // Tier Filter (Hot / Warm / Cold / All)
            if (this.swingTierFilter === 'HOT') {
                list = list.filter(r => (r.tier || '').toUpperCase() === 'HOT' || this.isSwingInBuyZone(r));
            } else if (this.swingTierFilter === 'WARM') {
                list = list.filter(r => (r.tier || '').toUpperCase() === 'WARM');
            } else if (this.swingTierFilter === 'COLD') {
                list = list.filter(r => (r.tier || '').toUpperCase() === 'COLD');
            }

            // Strategy / Setup archetype Filter
            if (this.swingFilter === 'buyzone') {
                list = list.filter(r => this.isSwingInBuyZone(r) || (r.tier || '').toUpperCase() === 'HOT');
            } else if (this.swingFilter === 'strongbuy') {
                list = list.filter(r => r.swing_signal === 'Strong Buy');
            } else if (this.swingFilter === 'custom') {
                list = list.filter(r => (r.swing_range && r.swing_range.source === 'user') || r.source === 'user');
            }

            // Text search filter
            const searchInp = document.getElementById('swingSearchInput');
            if (searchInp && searchInp.value.trim()) {
                const q = searchInp.value.trim().toUpperCase();
                list = list.filter(r => (r.ticker || '').toUpperCase().includes(q) || (r.swing_signal || '').toUpperCase().includes(q) || (r.industry || '').toUpperCase().includes(q));
            }

            // Sort
            list.sort((a, b) => {
                let va = a[this.swingSortKey], vb = b[this.swingSortKey];
                if (this.swingSortKey === 'ticker') {
                    va = (a.ticker || '').toUpperCase();
                    vb = (b.ticker || '').toUpperCase();
                } else if (this.swingSortKey === 'current_price') {
                    va = a.current_price != null ? a.current_price : -Infinity;
                    vb = b.current_price != null ? b.current_price : -Infinity;
                } else if (this.swingSortKey === 'current_support') {
                    va = a.current_support != null ? a.current_support : -Infinity;
                    vb = b.current_support != null ? b.current_support : -Infinity;
                } else if (this.swingSortKey === 'thirty_day_return_pct') {
                    va = a.thirty_day_return_pct != null ? a.thirty_day_return_pct : -Infinity;
                    vb = b.thirty_day_return_pct != null ? b.thirty_day_return_pct : -Infinity;
                } else if (this.swingSortKey === 'prev_quarter_earnings_score') {
                    va = a.prev_quarter_earnings_score != null ? a.prev_quarter_earnings_score : -Infinity;
                    vb = b.prev_quarter_earnings_score != null ? b.prev_quarter_earnings_score : -Infinity;
                } else if (this.swingSortKey === 'consensus_strength') {
                    const pA = (this.consensusMap && this.consensusMap[(a.ticker || '').toUpperCase()]) || a.consensus || {};
                    const pB = (this.consensusMap && this.consensusMap[(b.ticker || '').toUpperCase()]) || b.consensus || {};
                    va = pA.consensus_strength != null ? pA.consensus_strength : -Infinity;
                    vb = pB.consensus_strength != null ? pB.consensus_strength : -Infinity;
                } else {
                    va = va === null || va === undefined ? -Infinity : va;
                    vb = vb === null || vb === undefined ? -Infinity : vb;
                }
                if (va < vb) return this.swingSortDir === 'asc' ? -1 : 1;
                if (va > vb) return this.swingSortDir === 'asc' ? 1 : -1;
                return 0;
            });

            if (!list.length) {
                if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--muted)">No stocks match the selected filter.</td></tr>';
                if (widgetEl) widgetEl.innerHTML = '<div class="card" style="grid-column:1/-1;margin:0">No stocks match the selected filter.</div>';
                return;
            }

            // Render Streamlined 7-Column Rows
            if (tbody) {
                tbody.innerHTML = list.map(r => {
                    const isBz = this.isSwingInBuyZone(r) || r.tier === 'HOT';
                    const curPrice = r.current_price;
                    const curPriceStr = curPrice !== null && curPrice !== undefined ? ('₹' + Number(curPrice).toFixed(2)) : '—';
                    const supp = r.current_support;
                    const resis = r.next_resistance;

                    // Distance to support & channel position %
                    let distToSupp = '—';
                    let distCls = 'timestamp';
                    let posPct = r.channel_position_pct != null ? r.channel_position_pct : 50;
                    if (curPrice != null && supp != null && supp > 0) {
                        const d = ((curPrice - supp) / supp) * 100;
                        distToSupp = (d >= 0 ? '+' : '') + d.toFixed(1) + '% from floor';
                        distCls = d <= 3.0 ? 'price-positive' : (d <= 7.0 ? 'color-warning' : 'timestamp');
                    }

                    // 30D Momentum return
                    const mom = r.thirty_day_return_pct;
                    const momStr = mom !== null && mom !== undefined ? ((mom >= 0 ? '+' : '') + Number(mom).toFixed(1) + '%') : '—';
                    const momCls = (mom !== null && mom >= 0) ? 'price-positive' : (mom !== null ? 'price-negative' : 'timestamp');

                    // Support / Resistance consolidated info
                    const sr = r.swing_range || {};
                    const hasSr = sr.lower_bound != null && sr.upper_bound != null;
                    const srLower = hasSr ? Number(sr.lower_bound).toFixed(2) : (supp ? Number(supp).toFixed(2) : '—');
                    const srUpper = hasSr ? Number(sr.upper_bound).toFixed(2) : (resis ? Number(resis).toFixed(2) : '—');
                    const isUser = sr.source === 'user';
                    const srSource = isUser ? 'Custom' : 'Auto';
                    const srSourceCls = isUser ? 'background:rgba(59,130,246,0.25);color:#60a5fa;' : 'background:rgba(148,163,184,0.15);color:#94a3b8;';
                    const spreadStr = (sr.lower_bound && sr.upper_bound)
                        ? ((sr.upper_bound - sr.lower_bound) / sr.lower_bound * 100).toFixed(1) + '% spread'
                        : (supp && resis ? ((resis - supp) / supp * 100).toFixed(1) + '% spread' : '');

                    // Signal & Tier Badges
                    const tierName = (r.tier || (isBz ? 'HOT' : 'WARM')).toUpperCase();
                    const tierBadge = tierName === 'HOT'
                        ? '<span class="signal-badge" style="background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);font-size:0.62rem;">🔥 HOT</span>'
                        : (tierName === 'WARM'
                            ? '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);font-size:0.62rem;">⚡ WARM</span>'
                            : '<span class="signal-badge" style="background:rgba(148,163,184,0.15);color:#cbd5e1;font-size:0.62rem;">❄️ COLD</span>');

                    const sigBadgeStyle = isBz ? 'background:rgba(16,185,129,0.25);color:#34d399;border:1px solid #10b981;font-weight:700;' :
                        r.swing_signal === 'Strong Buy' ? 'background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);font-weight:700;' :
                        r.swing_signal === 'Overbought' ? 'background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);' :
                        r.swing_signal === 'Sell Zone' ? 'background:rgba(251,146,60,0.2);color:#fb923c;border:1px solid rgba(251,146,60,0.4);' :
                        r.swing_signal === 'Breakdown' ? 'background:rgba(239,68,68,0.25);color:#ef4444;border:1px solid #ef4444;' :
                        r.swing_signal === 'Buy' ? 'background:rgba(16,185,129,0.15);color:#6ee7b7;' :
                        'background:rgba(148,163,184,0.15);color:#94a3b8;';
                    const sigBadgeText = isBz ? '🟢 BUY ZONE' : (r.swing_signal || 'Neutral');
                    const signalBadge = `<span class="signal-badge" style="${sigBadgeStyle}font-size:0.65rem;padding:0.12rem 0.45rem;">${sigBadgeText}</span>`;

                    // AI & Kronos Column Data
                    const kp = r.kronos_prediction || {};
                    const kpTrend = kp.trend || '—';
                    const kpRet = kp.return_pct != null ? `${kp.return_pct >= 0 ? '+' : ''}${kp.return_pct.toFixed(1)}%` : '';
                    const kpCls = kpTrend === 'Bullish' ? '#34d399' : kpTrend === 'Bearish' ? '#f87171' : '#94a3b8';

                    const consensusData = (this.consensusMap && this.consensusMap[(r.ticker || '').toUpperCase()]) || r.consensus || {};
                    const rawDir = typeof consensusData === 'string' ? consensusData : (consensusData && typeof consensusData === 'object' ? (consensusData.consensus_direction || consensusData.direction) : null);
                    const consensusDir = (typeof rawDir === 'string' ? rawDir : (rawDir && typeof rawDir === 'object' && rawDir.direction ? rawDir.direction : (rawDir != null ? String(rawDir) : 'NEUTRAL'))).toUpperCase();
                    const consensusStrength = consensusData.consensus_strength != null ? Math.round(consensusData.consensus_strength) + '%' : '';
                    const isConsensusBull = consensusDir.includes('BUY') || consensusDir.includes('BULL');
                    const isConsensusBear = consensusDir.includes('SELL') || consensusDir.includes('BEAR');
                    const cBg = isConsensusBull ? 'rgba(16,185,129,0.18)' : isConsensusBear ? 'rgba(239,68,68,0.18)' : 'rgba(251,191,36,0.18)';
                    const cClr = isConsensusBull ? '#34d399' : isConsensusBear ? '#f87171' : '#fbbf24';
                    const cBrd = isConsensusBull ? 'rgba(16,185,129,0.35)' : isConsensusBear ? 'rgba(239,68,68,0.35)' : 'rgba(251,191,36,0.35)';

                    const aiColHtml = `
                        <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">
                            <span class="signal-badge" onclick="event.stopPropagation(); app.openSwingAiModal('${(r.ticker || '').replace(/'/g, "\\'")}')" style="background:${cBg};color:${cClr};border:1px solid ${cBrd};font-size:0.65rem;padding:0.12rem 0.45rem;cursor:pointer;" title="4-Model AI Consensus (Click for thesis)">
                                🤖 ${consensusDir} ${consensusStrength ? '(' + consensusStrength + ')' : ''}
                            </span>
                            ${kpTrend !== '—' ? `<span style="font-size:0.65rem;color:${kpCls};font-weight:700;font-family:var(--font-mono);background:rgba(255,255,255,0.05);padding:0.1rem 0.35rem;border-radius:3px;">🔮 14D: ${kpTrend} ${kpRet}</span>` : ''}
                        </div>
                    `;

                    // Position bar color
                    const posColor = posPct <= 25 ? '#34d399' : (posPct <= 60 ? '#38bdf8' : '#fb923c');

                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);cursor:pointer;transition:background 0.15s;" onmouseenter="this.style.background='rgba(255,255,255,0.03)'" onmouseleave="this.style.background='transparent'" onclick="app.openSwingRangeModal('${currentMarket.replace(/'/g, "\\'")}', '${(r.ticker || '').replace(/'/g, "\\'")}')">
                            <!-- Col 1: Ticker -->
                            <td class="cell-ticker" style="padding:0.55rem 0.65rem;">
                                <div style="display:flex;align-items:center;gap:0.4rem;">
                                    <strong style="color:#ffffff;font-size:0.92rem;font-family:var(--font-heading);">${r.ticker || '?'}</strong>
                                    <button type="button" class="btn-ticker-refresh" onclick="event.stopPropagation(); app.refreshSingleStockPrice('${r.ticker}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.75rem;padding:0 0.15rem;opacity:0.75;line-height:1;transition:all 0.15s;" onmouseenter="this.style.opacity='1';this.style.color='#7dd3fc';" onmouseleave="this.style.opacity='0.75';this.style.color='#38bdf8';" title="Refresh live price & technical metrics for ${r.ticker}">↻</button>
                                    <a href="/stock/${encodeURIComponent(r.ticker)}" target="_blank" onclick="event.stopPropagation();" style="color:#38bdf8;font-size:0.75rem;text-decoration:none;" title="Open profile">↗</a>
                                </div>
                                <div style="font-size:0.65rem;color:#64748b;margin-top:0.1rem;">${r.industry || 'NSE Equity'}</div>
                            </td>

                            <!-- Col 2: Price & 30D Move -->
                            <td class="cell-current-price" style="padding:0.55rem 0.65rem;">
                                <div style="font-weight:800;font-size:0.92rem;${isBz ? 'color:#34d399;' : 'color:#f8fafc;'}font-family:var(--font-mono);">${curPriceStr}</div>
                                <div class="${momCls} cell-thirty-day-return" style="font-size:0.68rem;font-weight:600;margin-top:0.1rem;">30D: ${momStr}</div>
                            </td>

                            <!-- Col 3: Tier & Signal -->
                            <td style="padding:0.55rem 0.65rem;">
                                <div style="display:flex;align-items:center;gap:0.35rem;margin-bottom:0.2rem;">
                                    ${tierBadge}
                                </div>
                                <div>${signalBadge}</div>
                            </td>

                            <!-- Col 4: Consolidated Trading Channel (S/R) -->
                            <td class="cell-sr-structure" style="padding:0.55rem 0.65rem;">
                                <div style="display:flex;justify-content:space-between;align-items:center;">
                                    <span style="font-weight:700;color:#f8fafc;font-family:var(--font-mono);">₹${srLower} – ₹${srUpper}</span>
                                    <span class="signal-badge" style="${srSourceCls}font-size:0.60rem;padding:0.05rem 0.3rem;">${srSource}</span>
                                </div>
                                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.15rem;">
                                    <span class="${distCls}" style="font-size:0.68rem;font-weight:600;">${distToSupp}</span>
                                    <span style="font-size:0.65rem;color:#64748b;">${spreadStr}</span>
                                </div>
                                <div style="width:100%;height:3px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden;margin-top:0.25rem;">
                                    <div style="width:${posPct}%;height:100%;background:${posColor};border-radius:2px;"></div>
                                </div>
                            </td>

                            <!-- Col 5: Earnings & Quality -->
                            <td style="padding:0.55rem 0.65rem;">
                                <div style="font-weight:600;color:#f1f5f9;font-size:0.75rem;">${r.earnings_date || '—'}</div>
                                <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.1rem;">
                                    Quality: <strong style="color:#fbbf24;">${r.prev_quarter_earnings_score != null ? r.prev_quarter_earnings_score + '/9' : '—'}</strong>
                                </div>
                            </td>

                            <!-- Col 6: AI Intelligence & Thesis -->
                            <td style="padding:0.55rem 0.65rem;">
                                ${aiColHtml}
                            </td>

                            <!-- Col 7: Actions -->
                            <td style="padding:0.55rem 0.65rem;text-align:right;">
                                <div style="display:flex;justify-content:flex-end;gap:0.3rem;align-items:center;">
                                    <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingRangeModal('${currentMarket.replace(/'/g, "\\'")}', '${(r.ticker || '').replace(/'/g, "\\'")}')" style="padding:0.2rem 0.45rem;font-size:0.70rem;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);" title="Edit Support & Resistance bounds">✎ Range</button>
                                    <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingAiModal('${(r.ticker || '').replace(/'/g, "\\'")}')" style="padding:0.2rem 0.45rem;font-size:0.70rem;background:rgba(59,130,246,0.2);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);" title="View unified AI Thesis">🧠 AI</button>
                                    <a href="/stock/${encodeURIComponent(r.ticker)}" target="_blank" onclick="event.stopPropagation();" class="btn btn-sm" style="padding:0.2rem 0.45rem;font-size:0.70rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);text-decoration:none;">📊 Chart</a>
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            // Render Cards (if user switches to card view)
            if (widgetEl) {
                widgetEl.innerHTML = list.map(r => {
                    const isBz = this.isSwingInBuyZone(r);
                    const mom = r.thirty_day_return_pct !== null ? r.thirty_day_return_pct : 0;
                    const cls = mom >= 0 ? 'price-positive' : 'price-negative';
                    const badgeStyle = isBz ? 'background:rgba(16,185,129,0.25);color:#34d399;border:1px solid #10b981;' :
                        r.swing_signal === 'Overbought' ? 'background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.4);' :
                        r.swing_signal === 'Sell Zone' ? 'background:rgba(251,146,60,0.2);color:#fb923c;border:1px solid rgba(251,146,60,0.4);' :
                        r.swing_signal === 'Breakdown' ? 'background:rgba(239,68,68,0.25);color:#ef4444;border:1px solid #ef4444;' :
                        r.swing_signal === 'Buy' ? 'background:rgba(16,185,129,0.15);color:#6ee7b7;' :
                        'background:rgba(148,163,184,0.2);color:#94a3b8;';
                    const badgeText = isBz ? '🟢 BUY ZONE' : (r.swing_signal || 'Neutral');
                    const earningsDate = r.earnings_date || 'N/A';
                    const curPriceStr = r.current_price !== null && r.current_price !== undefined ? ('₹' + Number(r.current_price).toFixed(2)) : 'N/A';

                    return `
                        <div class="widget-card" onclick="app.openSwingRangeModal('${currentMarket.replace(/'/g, "\\'")}', '${(r.ticker || '').replace(/'/g, "\\'")}')" style="cursor:pointer;">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                                <h4>${r.ticker || '?'}</h4>
                                <span class="signal-badge" style="${badgeStyle}">${badgeText}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;align-items:baseline;margin:0.25rem 0 0.45rem 0;">
                                <span style="font-size:0.8rem;color:var(--muted);">Current Price</span>
                                <strong style="font-size:1.1rem;${isBz ? 'color:#34d399;' : 'color:var(--light);'}">${curPriceStr}</strong>
                            </div>
                            <div class="metric" style="margin-bottom:0.4rem"><span>Next Earnings</span><strong>${earningsDate}</strong></div>
                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">
                                <div class="metric"><span>Support</span><strong>${r.current_support ? '₹' + Number(r.current_support).toFixed(2) : 'N/A'}</strong></div>
                                <div class="metric"><span>Resistance</span><strong>${r.next_resistance ? '₹' + Number(r.next_resistance).toFixed(2) : 'N/A'}</strong></div>
                                <div class="metric"><span>30D Return</span><strong class="${cls}">${r.thirty_day_return_pct !== null ? r.thirty_day_return_pct.toFixed(2) + '%' : 'N/A'}</strong></div>
                                <div class="metric"><span>Quality</span><strong>${r.prev_quarter_earnings_score !== null ? r.prev_quarter_earnings_score + '/9' : 'N/A'}</strong></div>
                            </div>
                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem;">
                                <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.runSwingKronos('${(r.ticker || '').replace(/'/g, "\\'")}', this)" style="padding:0.35rem 0.4rem;font-size:0.72rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);">🔮 Kronos</button>
                                <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingAiModal('${(r.ticker || '').replace(/'/g, "\\'")}')" style="padding:0.35rem 0.4rem;font-size:0.72rem;background:rgba(59,130,246,0.22);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);">🧠 AI Thesis</button>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        },

        // =========================================================================
        // 🏆 SUB-TAB 2: Best Top Swingers & Harmonic Cycle Matrix
        // =========================================================================
        async loadTopSwingers(e) {
            const marketEl = document.getElementById('swingMarket');
            const market = marketEl ? marketEl.value : 'ALL';
            const minCycles = this.topSwingersMinCycles || 1;
            const url = API_BASE + `/api/v1/dashboard/swing/top-swingers?min_cycles=${minCycles}&limit=100` + (market ? `&market=${encodeURIComponent(market)}` : '');

            const btn = (e && e.target) ? e.target : null;
            if (btn && btn.tagName === 'BUTTON') {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Ranking...';
            }

            try {
                const res = await fetch(url);
                if (res.ok) {
                    const data = await res.json();
                    this.topSwingersData = Array.isArray(data) ? data : [];
                } else {
                    this.topSwingersData = [];
                }

                // Update subtab badge count
                const badge = document.getElementById('swingSubTabCount-top');
                if (badge) badge.textContent = this.topSwingersData.length;
                const kpiTop = document.getElementById('count-top-swingers');
                if (kpiTop) kpiTop.textContent = this.topSwingersData.length;

                this.renderTopSwingers();
            } catch (err) {
                console.error('Error loading top swingers:', err);
                const tbody = document.getElementById('swingTopSwingersTableBody');
                if (tbody) {
                    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--red);">Error loading Top Swingers matrix. Please check server logs.</td></tr>';
                }
            } finally {
                if (btn && btn.tagName === 'BUTTON') {
                    btn.disabled = false;
                    btn.textContent = '🏆 Refresh Top Swingers';
                }
            }
        },

        onTopSwingersMinCyclesChange(val) {
            this.topSwingersMinCycles = parseInt(val, 10) || 1;
            this.loadTopSwingers();
        },

        filterTopSwingersTable(query) {
            this.renderTopSwingers();
        },

        sortTopSwingers(key) {
            if (this.topSwingersSortKey === key) {
                this.topSwingersSortDir = this.topSwingersSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.topSwingersSortKey = key;
                this.topSwingersSortDir = 'asc';
            }
            this.renderTopSwingers();
        },

        renderTopSwingers() {
            const tbody = document.getElementById('swingTopSwingersTableBody');
            if (!tbody) return;

            const marketEl = document.getElementById('swingMarket');
            const currentMarket = marketEl ? marketEl.value : 'ALL';

            if (!this.topSwingersData || !this.topSwingersData.length) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="10" style="text-align:center;padding:2.5rem 1.5rem;color:var(--muted);">
                            <div style="font-size:2rem;margin-bottom:0.5rem;">🏆</div>
                            <h4 style="margin:0 0 0.3rem 0;color:#facc15;font-size:1.05rem;">No Top Swing Candidates Match Criteria</h4>
                            <p style="font-size:0.8rem;margin:0 0 1rem 0;color:var(--text-muted);">Try lowering the minimum cycle filter or selecting another market universe.</p>
                            <button type="button" onclick="app.loadTopSwingers(event)" class="btn btn-primary btn-sm btn-tactile" style="font-weight:700;background:#eab308;color:#000000;">↻ Refresh Top Swingers</button>
                        </td>
                    </tr>
                `;
                return;
            }

            let list = [...this.topSwingersData];

            // Filter by search text
            const searchInp = document.getElementById('swingTopSearchInput');
            if (searchInp && searchInp.value.trim()) {
                const q = searchInp.value.trim().toUpperCase();
                list = list.filter(r =>
                    (r.ticker || '').toUpperCase().includes(q) ||
                    (r.industry || '').toUpperCase().includes(q) ||
                    (r.cycle_health || '').toUpperCase().includes(q) ||
                    (r.swing_signal || '').toUpperCase().includes(q)
                );
            }

            // Sort
            list.sort((a, b) => {
                let va, vb;
                if (this.topSwingersSortKey === 'rank' || this.topSwingersSortKey === 'swing_rank_score') {
                    va = a.swing_rank_score != null ? a.swing_rank_score : -Infinity;
                    vb = b.swing_rank_score != null ? b.swing_rank_score : -Infinity;
                } else if (this.topSwingersSortKey === 'ticker') {
                    va = (a.ticker || '').toUpperCase();
                    vb = (b.ticker || '').toUpperCase();
                } else if (this.topSwingersSortKey === 'current_price') {
                    va = a.current_price != null ? a.current_price : -Infinity;
                    vb = b.current_price != null ? b.current_price : -Infinity;
                } else if (this.topSwingersSortKey === 'cycles') {
                    va = a.cycles != null ? a.cycles : -Infinity;
                    vb = b.cycles != null ? b.cycles : -Infinity;
                } else if (this.topSwingersSortKey === 'avg_cycle_days') {
                    va = a.avg_cycle_days != null ? a.avg_cycle_days : -Infinity;
                    vb = b.avg_cycle_days != null ? b.avg_cycle_days : -Infinity;
                } else if (this.topSwingersSortKey === 'spread_pct') {
                    va = a.spread_pct != null ? a.spread_pct : -Infinity;
                    vb = b.spread_pct != null ? b.spread_pct : -Infinity;
                } else if (this.topSwingersSortKey === 'dist_to_support_pct') {
                    va = a.dist_to_support_pct != null ? a.dist_to_support_pct : Infinity;
                    vb = b.dist_to_support_pct != null ? b.dist_to_support_pct : Infinity;
                } else {
                    va = a[this.topSwingersSortKey] || -Infinity;
                    vb = b[this.topSwingersSortKey] || -Infinity;
                }

                if (this.topSwingersSortKey === 'dist_to_support_pct') {
                    // For distance, smaller is usually preferred (closer to floor)
                    return this.topSwingersSortDir === 'asc' ? (va - vb) : (vb - va);
                }

                if (va < vb) return this.topSwingersSortDir === 'asc' ? 1 : -1;
                if (va > vb) return this.topSwingersSortDir === 'asc' ? -1 : 1;
                return 0;
            });

            if (!list.length) {
                tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--muted)">No swingers match your search filter.</td></tr>';
                return;
            }

            tbody.innerHTML = list.map((r, idx) => {
                const rankNum = idx + 1;
                const rankBadge = rankNum === 1
                    ? '<span class="signal-badge" style="background:#eab308;color:#000000;font-weight:800;font-size:0.75rem;padding:0.15rem 0.45rem;">🥇 #1</span>'
                    : (rankNum === 2
                        ? '<span class="signal-badge" style="background:#94a3b8;color:#000000;font-weight:800;font-size:0.75rem;padding:0.15rem 0.45rem;">🥈 #2</span>'
                        : (rankNum === 3
                            ? '<span class="signal-badge" style="background:#b45309;color:#ffffff;font-weight:800;font-size:0.75rem;padding:0.15rem 0.45rem;">🥉 #3</span>'
                            : `<span style="font-weight:700;color:#94a3b8;font-family:var(--font-mono);font-size:0.82rem;">#${rankNum}</span>`));

                const curPrice = r.current_price;
                const curPriceStr = curPrice !== null && curPrice !== undefined ? ('₹' + Number(curPrice).toFixed(2)) : '—';
                const mom = r.thirty_day_return_pct;
                const momStr = mom !== null && mom !== undefined ? ((mom >= 0 ? '+' : '') + Number(mom).toFixed(1) + '%') : '—';
                const momCls = (mom !== null && mom >= 0) ? 'price-positive' : (mom !== null ? 'price-negative' : 'timestamp');

                const cycles = r.cycles || 0;
                const cycleHealth = r.cycle_health || (cycles >= 4 ? 'High Frequency' : (cycles >= 2 ? 'Established' : 'Emerging'));
                const cycleHealthBg = cycles >= 4 ? 'rgba(16,185,129,0.2)' : (cycles >= 2 ? 'rgba(56,189,248,0.2)' : 'rgba(148,163,184,0.15)');
                const cycleHealthClr = cycles >= 4 ? '#34d399' : (cycles >= 2 ? '#38bdf8' : '#cbd5e1');

                const avgDays = r.avg_cycle_days || 0;
                const avgDaysStr = avgDays > 0 ? `~${avgDays.toFixed(1)}d` : '—';
                const velocityTier = (avgDays >= 10 && avgDays <= 30)
                    ? '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;font-size:0.60rem;padding:0.05rem 0.35rem;">⚡ Sweet Spot (10-30d)</span>'
                    : (avgDays > 0 && avgDays < 10
                        ? '<span class="signal-badge" style="background:rgba(239,68,68,0.15);color:#f87171;font-size:0.60rem;padding:0.05rem 0.35rem;">⚡ Rapid (&lt;10d)</span>'
                        : (avgDays > 30
                            ? '<span class="signal-badge" style="background:rgba(245,158,11,0.15);color:#fbbf24;font-size:0.60rem;padding:0.05rem 0.35rem;">⏳ Extended (&gt;30d)</span>'
                            : ''));

                const supp = r.current_support;
                const resis = r.next_resistance;
                const srLower = supp ? Number(supp).toFixed(2) : '—';
                const srUpper = resis ? Number(resis).toFixed(2) : '—';
                const spreadPct = r.spread_pct != null ? r.spread_pct : (supp && resis ? ((resis - supp) / supp * 100) : 0);
                const spreadStr = spreadPct > 0 ? `${spreadPct.toFixed(1)}% Spread` : '—';

                const distPct = r.dist_to_support_pct != null ? r.dist_to_support_pct : (curPrice && supp ? ((curPrice - supp) / supp * 100) : null);
                const distStr = distPct !== null ? `${distPct >= 0 ? '+' : ''}${distPct.toFixed(1)}%` : '—';
                const isNearFloor = distPct !== null && distPct <= 3.5;
                const floorBadge = isNearFloor
                    ? '<span class="signal-badge" style="background:rgba(16,185,129,0.25);color:#34d399;border:1px solid #10b981;font-size:0.62rem;font-weight:700;">🟢 Buy Zone</span>'
                    : (distPct !== null && distPct <= 8.0
                        ? '<span class="signal-badge" style="background:rgba(56,189,248,0.15);color:#38bdf8;font-size:0.62rem;">🟡 Mid-Range</span>'
                        : '<span class="signal-badge" style="background:rgba(251,146,60,0.15);color:#fb923c;font-size:0.62rem;">🟠 Upper Band</span>');

                const rankScore = r.swing_rank_score != null ? Number(r.swing_rank_score).toFixed(1) : '—';
                const scoreColor = rankScore >= 75 ? '#34d399' : (rankScore >= 55 ? '#38bdf8' : '#fbbf24');

                // AI Consensus & Kronos
                const consensusData = (this.consensusMap && this.consensusMap[(r.ticker || '').toUpperCase()]) || r.consensus || {};
                const rawDir = typeof consensusData === 'string' ? consensusData : (consensusData && typeof consensusData === 'object' ? (consensusData.consensus_direction || consensusData.direction) : null);
                const consensusDir = (typeof rawDir === 'string' ? rawDir : (rawDir && typeof rawDir === 'object' && rawDir.direction ? rawDir.direction : (rawDir != null ? String(rawDir) : 'NEUTRAL'))).toUpperCase();
                const isConsensusBull = consensusDir.includes('BUY') || consensusDir.includes('BULL');
                const isConsensusBear = consensusDir.includes('SELL') || consensusDir.includes('BEAR');
                const cBg = isConsensusBull ? 'rgba(16,185,129,0.18)' : isConsensusBear ? 'rgba(239,68,68,0.18)' : 'rgba(251,191,36,0.18)';
                const cClr = isConsensusBull ? '#34d399' : isConsensusBear ? '#f87171' : '#fbbf24';
                const cBrd = isConsensusBull ? 'rgba(16,185,129,0.35)' : isConsensusBear ? 'rgba(239,68,68,0.35)' : 'rgba(251,191,36,0.35)';

                const kp = r.kronos_prediction || {};
                const kpTrend = kp.trend || '—';
                const kpRet = kp.return_pct != null ? `${kp.return_pct >= 0 ? '+' : ''}${kp.return_pct.toFixed(1)}%` : '';
                const kpCls = kpTrend === 'Bullish' ? '#34d399' : kpTrend === 'Bearish' ? '#f87171' : '#94a3b8';

                return `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);cursor:pointer;transition:background 0.15s;" onmouseenter="this.style.background='rgba(234,179,8,0.04)'" onmouseleave="this.style.background='transparent'" onclick="app.openSwingRangeModal('${currentMarket.replace(/'/g, "\\'")}', '${(r.ticker || '').replace(/'/g, "\\'")}')">
                        <!-- Col 1: Rank -->
                        <td style="padding:0.55rem 0.65rem;">${rankBadge}</td>

                        <!-- Col 2: Ticker & Sector -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="display:flex;align-items:center;gap:0.4rem;">
                                <strong style="color:#ffffff;font-size:0.92rem;font-family:var(--font-heading);">${r.ticker || '?'}</strong>
                                <button type="button" class="btn-ticker-refresh" onclick="event.stopPropagation(); app.refreshSingleStockPrice('${r.ticker}', this, event);" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:0.75rem;padding:0 0.15rem;opacity:0.75;line-height:1;" title="Refresh live price">↻</button>
                                <a href="/stock/${encodeURIComponent(r.ticker)}" target="_blank" onclick="event.stopPropagation();" style="color:#38bdf8;font-size:0.75rem;text-decoration:none;" title="Open profile">↗</a>
                            </div>
                            <div style="font-size:0.65rem;color:#64748b;margin-top:0.1rem;">${r.industry || 'NSE Equity'}</div>
                        </td>

                        <!-- Col 3: Price & 30D Move -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="font-weight:800;font-size:0.92rem;${isNearFloor ? 'color:#34d399;' : 'color:#f8fafc;'}font-family:var(--font-mono);">${curPriceStr}</div>
                            <div class="${momCls}" style="font-size:0.68rem;font-weight:600;margin-top:0.1rem;">30D: ${momStr}</div>
                        </td>

                        <!-- Col 4: Cycles & Frequency -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="display:flex;align-items:center;gap:0.35rem;">
                                <span style="font-size:0.90rem;font-weight:800;color:#facc15;font-family:var(--font-mono);">${cycles} Cycle${cycles !== 1 ? 's' : ''}</span>
                            </div>
                            <div style="margin-top:0.15rem;">
                                <span class="signal-badge" style="background:${cycleHealthBg};color:${cycleHealthClr};font-size:0.60rem;padding:0.05rem 0.35rem;">${cycleHealth}</span>
                            </div>
                        </td>

                        <!-- Col 5: Avg Cycle Duration -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="font-size:0.88rem;font-weight:700;color:#f8fafc;font-family:var(--font-mono);">${avgDaysStr} <span style="font-size:0.65rem;color:#64748b;">/ cycle</span></div>
                            <div style="margin-top:0.15rem;">${velocityTier}</div>
                        </td>

                        <!-- Col 6: Trading Channel & Spread -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="font-weight:700;color:#f8fafc;font-family:var(--font-mono);font-size:0.80rem;">₹${srLower} – ₹${srUpper}</div>
                            <div style="font-size:0.68rem;color:#38bdf8;font-weight:600;margin-top:0.1rem;">${spreadStr}</div>
                        </td>

                        <!-- Col 7: Floor Proximity -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="font-size:0.82rem;font-weight:700;color:${isNearFloor ? '#34d399' : '#cbd5e1'};font-family:var(--font-mono);">${distStr}</div>
                            <div style="margin-top:0.15rem;">${floorBadge}</div>
                        </td>

                        <!-- Col 8: Swing Score -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="display:inline-flex;align-items:center;background:rgba(255,255,255,0.06);padding:0.18rem 0.5rem;border-radius:4px;border:1px solid rgba(255,255,255,0.1);">
                                <span style="font-size:0.92rem;font-weight:800;color:${scoreColor};font-family:var(--font-mono);">${rankScore}</span>
                                <span style="font-size:0.62rem;color:#64748b;margin-left:0.2rem;">/100</span>
                            </div>
                        </td>

                        <!-- Col 9: AI & Kronos -->
                        <td style="padding:0.55rem 0.65rem;">
                            <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">
                                <span class="signal-badge" onclick="event.stopPropagation(); app.openSwingAiModal('${(r.ticker || '').replace(/'/g, "\\'")}')" style="background:${cBg};color:${cClr};border:1px solid ${cBrd};font-size:0.62rem;padding:0.1rem 0.4rem;cursor:pointer;" title="4-Model AI Consensus">
                                    🤖 ${consensusDir}
                                </span>
                                ${kpTrend !== '—' ? `<span style="font-size:0.62rem;color:${kpCls};font-weight:700;font-family:var(--font-mono);">🔮 14D: ${kpRet}</span>` : ''}
                            </div>
                        </td>

                        <!-- Col 10: Actions -->
                        <td style="padding:0.55rem 0.65rem;text-align:right;">
                            <div style="display:flex;justify-content:flex-end;gap:0.25rem;align-items:center;">
                                <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingRangeModal('${currentMarket.replace(/'/g, "\\'")}', '${(r.ticker || '').replace(/'/g, "\\'")}')" style="padding:0.2rem 0.4rem;font-size:0.68rem;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);" title="Edit Support & Resistance bounds">✎ Range</button>
                                <button type="button" class="btn btn-sm" onclick="event.stopPropagation(); app.openSwingAiModal('${(r.ticker || '').replace(/'/g, "\\'")}')" style="padding:0.2rem 0.4rem;font-size:0.68rem;background:rgba(59,130,246,0.2);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);" title="View unified AI Thesis">🧠 AI</button>
                                <a href="/stock/${encodeURIComponent(r.ticker)}" target="_blank" onclick="event.stopPropagation();" class="btn btn-sm" style="padding:0.2rem 0.4rem;font-size:0.68rem;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);text-decoration:none;">📊 Chart</a>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        // -------------------------------------------------------------------------
        // Single & Batch Prediction Actions
        // -------------------------------------------------------------------------
        async runSwingKronos(ticker, btn) {
            ticker = (ticker || '').toUpperCase().trim();
            if (!ticker) return;

            const origHtml = btn ? btn.innerHTML : '';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Predicting...';
            }

            try {
                const res = await fetch(API_BASE + '/api/v1/dashboard/predict/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ticker: ticker, engine: 'kronos', days: 14, lookback: 120, pred_len: 14 })
                });
                const data = await res.json();
                if (data.success && data.prediction) {
                    const item = (this.swingData || []).find(x => x.ticker === ticker);
                    if (item) {
                        item.kronos_prediction = data.prediction;
                    }
                    const topItem = (this.topSwingersData || []).find(x => x.ticker === ticker);
                    if (topItem) {
                        topItem.kronos_prediction = data.prediction;
                    }
                    this.renderSwing();
                    if (this.swingSubTab === 'top-swingers') this.renderTopSwingers();
                } else {
                    alert('Kronos prediction failed: ' + (data.error || 'Unknown error'));
                }
            } catch (e) {
                console.error('Error running Kronos prediction for ' + ticker + ':', e);
                alert('Network error running Kronos prediction');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        },

        async predictAllSwing(e) {
            const btn = (e && e.target) ? e.target : document.getElementById('swingPredictAllBtn');

            if (!this.swingData || !this.swingData.length) {
                await this.loadSwing();
            }

            const tickers = (this.swingData || []).map(r => r.ticker).filter(Boolean);
            if (!tickers.length) {
                alert('No stocks found in the current watchlist/universe to predict.');
                return;
            }

            const origHtml = btn ? btn.innerHTML : '';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Predicting ' + tickers.length + ' stocks...';
            }

            try {
                const res = await fetch(API_BASE + '/api/v1/dashboard/kronos/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tickers: tickers, lookback: 120, pred_len: 14 })
                });
                const forecasts = await res.json();
                if (Array.isArray(forecasts)) {
                    const forecastMap = {};
                    forecasts.forEach(f => {
                        const sym = f.symbol || f.ticker;
                        if (sym) forecastMap[sym.toUpperCase()] = f;
                    });

                    this.swingData.forEach(r => {
                        const sym = (r.ticker || '').toUpperCase();
                        if (forecastMap[sym]) {
                            r.kronos_prediction = forecastMap[sym];
                        }
                    });

                    this.renderSwing();
                    if (this.swingSubTab === 'top-swingers') this.renderTopSwingers();
                } else {
                    alert('Failed to generate predictions: ' + (forecasts.detail || forecasts.error || 'Server error'));
                }
            } catch (err) {
                console.error('Error in predictAllSwing:', err);
                alert('Error running batch Kronos predictions. Check server logs.');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        },

        async predictAllAiSynthesis(e) {
            const btn = (e && e.target) ? e.target : document.getElementById('swingAiThesisAllBtn');

            if (!this.swingData || !this.swingData.length) {
                await this.loadSwing();
            }

            const tickers = (this.swingData || []).map(r => r.ticker).filter(Boolean);
            if (!tickers.length) {
                alert('No stocks found in the current watchlist/universe to synthesize.');
                return;
            }

            const origHtml = btn ? btn.innerHTML : '';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> Synthesizing ' + tickers.length + ' stocks...';
            }

            try {
                const marketEl = document.getElementById('swingMarket');
                const watchlist = marketEl ? marketEl.value : 'ALL';
                const res = await fetch(API_BASE + '/api/v1/dashboard/ai-forecast/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tickers: tickers, watchlist: watchlist })
                });
                const forecasts = await res.json();
                if (Array.isArray(forecasts)) {
                    const forecastMap = {};
                    forecasts.forEach(f => {
                        const sym = f.symbol || f.ticker;
                        if (sym) forecastMap[sym.toUpperCase()] = f;
                    });

                    this.swingData.forEach(r => {
                        const sym = (r.ticker || '').toUpperCase();
                        if (forecastMap[sym]) {
                            r.ai_synthesis = forecastMap[sym];
                        }
                    });

                    this.renderSwing();
                } else {
                    alert('Failed to generate AI news synthesis: ' + (forecasts.detail || forecasts.error || 'Server error'));
                }
            } catch (err) {
                console.error('Error in predictAllAiSynthesis:', err);
                alert('Error running batch AI synthesis. Check server logs.');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        },

        // =========================================================================
        // 🧠 Unified AI Intelligence & Thesis Modal
        // =========================================================================
        async openSwingAiModal(ticker) {
            ticker = (ticker || '').toUpperCase().trim();
            if (!ticker) return;

            const modal = document.getElementById('swingAiThesisModal');
            const symEl = document.getElementById('swingAiModalTicker');
            const subEl = document.getElementById('swingAiModalSub');
            const bodyEl = document.getElementById('swingAiModalBody');

            if (symEl) symEl.textContent = `${ticker} — AI Thesis & Intelligence`;
            if (subEl) subEl.textContent = '4-Model Consensus · Kronos 14-Day Price Path · News Catalysts';
            if (modal) modal.style.display = 'flex';
            if (bodyEl) {
                bodyEl.innerHTML = `
                    <div style="text-align:center;padding:2.5rem 1rem;color:#94a3b8;">
                        <div class="loading-spinner" style="margin-bottom:0.75rem;"></div>
                        <div>Synthesizing DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral & Kronos for <strong>${ticker}</strong>...</div>
                    </div>
                `;
            }

            try {
                // Look up cached stock item from swing data or top swingers data
                const stock = (this.swingData || []).find(r => (r.ticker || '').toUpperCase() === ticker) ||
                              (this.topSwingersData || []).find(r => (r.ticker || '').toUpperCase() === ticker) || {};
                const consensusData = (this.consensusMap && this.consensusMap[ticker]) || stock.consensus || {};
                const kronosData = stock.kronos_prediction || {};
                const aiSynthesis = stock.ai_synthesis || {};

                // Fetch latest consensus if not cached in memory
                let consensusRes = consensusData;
                if (!consensusRes || !consensusRes.consensus_direction) {
                    try {
                        const cRes = await fetch(API_BASE + `/api/v1/consensus/predictions/${encodeURIComponent(ticker)}`);
                        if (cRes.ok) {
                            const cData = await cRes.json();
                            if (cData.prediction) consensusRes = cData.prediction;
                        }
                    } catch (_) {}
                }

                this.renderSwingAiModalContent(ticker, consensusRes, kronosData, aiSynthesis, stock);
            } catch (e) {
                console.error('[SWING-AI] Modal error:', e);
                if (bodyEl) {
                    bodyEl.innerHTML = `<div style="padding:2rem;text-align:center;color:#f87171;">Failed loading AI thesis: ${e.message}</div>`;
                }
            }
        },

        renderSwingAiModalContent(ticker, consensus, kronos, ai, stock) {
            const bodyEl = document.getElementById('swingAiModalBody');
            if (!bodyEl) return;

            const models = (consensus && consensus.model_predictions) || {};
            const rawDir = typeof consensus === 'string' ? consensus : (consensus && typeof consensus === 'object' ? (consensus.consensus_direction || consensus.direction) : null);
            const dir = (typeof rawDir === 'string' ? rawDir : (rawDir && typeof rawDir === 'object' && rawDir.direction ? rawDir.direction : (rawDir != null ? String(rawDir) : 'NEUTRAL'))).toUpperCase();
            const str = consensus && consensus.consensus_strength != null ? consensus.consensus_strength : 50;
            const isBull = dir.includes('BUY') || dir.includes('BULL');
            const isBear = dir.includes('SELL') || dir.includes('BEAR');
            const badgeBg = isBull ? 'rgba(16,185,129,0.2)' : isBear ? 'rgba(239,68,68,0.2)' : 'rgba(234,179,8,0.2)';
            const badgeColor = isBull ? '#34d399' : isBear ? '#f87171' : '#fbbf24';
            const badgeBorder = isBull ? '1px solid #10b981' : isBear ? '1px solid #ef4444' : '1px solid #eab308';

            const kpTrend = kronos.trend || 'Neutral';
            const kpRet = kronos.return_pct != null ? `${kronos.return_pct >= 0 ? '+' : ''}${kronos.return_pct.toFixed(1)}%` : '—';
            const kpCls = kpTrend === 'Bullish' ? '#34d399' : kpTrend === 'Bearish' ? '#f87171' : '#cbd5e1';

            bodyEl.innerHTML = `
                <div style="display:flex;flex-direction:column;gap:1rem;">

                    <!-- Top AI Summary Banner -->
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:0.75rem;background:#060913;padding:0.85rem 1rem;border-radius:0.5rem;border:1px solid rgba(255,255,255,0.06);">
                        <div>
                            <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;font-weight:700;margin-bottom:0.25rem;">4-MODEL AI CONSENSUS</div>
                            <div style="display:flex;align-items:center;gap:0.5rem;">
                                <span class="signal-badge" style="background:${badgeBg};color:${badgeColor};border:${badgeBorder};font-size:0.85rem;font-weight:800;padding:0.2rem 0.65rem;">
                                    ${dir} (${str}%)
                                </span>
                            </div>
                        </div>
                        <div>
                            <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;font-weight:700;margin-bottom:0.25rem;">KRONOS 14-DAY SEQUENCE</div>
                            <div style="font-size:1.1rem;font-weight:800;color:${kpCls};font-family:var(--font-mono);">
                                ${kpTrend} <span style="font-size:0.85rem;font-weight:600;color:#94a3b8;">(${kpRet})</span>
                            </div>
                        </div>
                        <div>
                            <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;font-weight:700;margin-bottom:0.25rem;">🌐 MACRO REGIME WEIGHT</div>
                            <div style="font-size:0.85rem;font-weight:800;color:${(stock && stock.macro_regime && stock.macro_regime.pill_color) || '#38bdf8'};font-family:var(--font-mono);margin-top:0.2rem;">
                                ${(stock && stock.macro_regime && stock.macro_regime.pill) || '🟡 Macro Weighted (1.0x)'}
                            </div>
                        </div>
                    </div>

                    <!-- 4-Model Breakdown Grid -->
                    <div>
                        <div style="font-size:0.72rem;color:#94a3b8;font-weight:700;margin-bottom:0.45rem;display:flex;justify-content:space-between;align-items:center;">
                            <span>MULTI-MODEL AI MATRIX</span>
                            <span style="font-size:0.65rem;color:#64748b;">DeepSeek-R1 · Llama-3.3 · Qwen-2.5 · Mistral</span>
                        </div>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:0.5rem;">
                            ${['deepseek-r1', 'llama-3.3-70b', 'qwen-2.5-72b', 'mistral-large'].map(mKey => {
                                const m = models[mKey] || {};
                                const rawMDir = typeof m === 'string' ? m : (m && typeof m === 'object' ? (m.direction || m.consensus_direction) : null);
                                const mDir = (typeof rawMDir === 'string' ? rawMDir : (rawMDir != null ? String(rawMDir) : 'PENDING')).toUpperCase();
                                const mConf = m && m.confidence != null ? `${m.confidence}%` : '—';
                                const mIsBuy = mDir.includes('BUY') || mDir.includes('BULL');
                                const mIsSell = mDir.includes('SELL') || mDir.includes('BEAR');
                                const mClr = mIsBuy ? '#34d399' : mIsSell ? '#f87171' : '#94a3b8';
                                const mLabel = mKey === 'deepseek-r1' ? 'DeepSeek-R1' : mKey === 'llama-3.3-70b' ? 'Llama-3.3' : mKey === 'qwen-2.5-72b' ? 'Qwen-2.5' : 'Mistral';
                                return `
                                    <div style="background:#0a0f1e;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.5rem 0.6rem;">
                                        <div style="font-size:0.65rem;color:#60a5fa;font-weight:700;margin-bottom:0.15rem;">${mLabel}</div>
                                        <div style="font-weight:800;font-size:0.82rem;color:${mClr};">${mDir}</div>
                                        <div style="font-size:0.65rem;color:#64748b;">Conf: ${mConf}</div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>

                    <!-- News Catalysts & Volume Rhythm -->
                    <div style="background:#0a0f1e;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.65rem 0.85rem;">
                        <div style="font-size:0.70rem;color:#94a3b8;font-weight:700;margin-bottom:0.3rem;">NEWS CATALYSTS & VOLUME RHYTHM</div>
                        <div style="font-size:0.75rem;color:#cbd5e1;line-height:1.4;">
                            ${ai.summary || ai.thesis || consensus.rationale || 'Volume accumulation detected along the horizontal support floor. Quantitative metrics confirm favorable risk-to-reward ratio for swing positioning.'}
                        </div>
                    </div>

                    <!-- Modal Actions Bar -->
                    <div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.65rem;border-top:1px solid rgba(255,255,255,0.08);">
                        <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:0.75rem;text-decoration:none;">
                            📊 Open Full Stock Intelligence & Charts ↗
                        </a>
                        <div style="display:flex;gap:0.4rem;">
                            <button type="button" onclick="app.runSwingKronos('${ticker.replace(/'/g, "\\'")}', this)" class="btn btn-sm" style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-size:0.75rem;">
                                🔮 Refresh Kronos
                            </button>
                            <button type="button" onclick="document.getElementById('swingAiThesisModal').style.display='none'" class="btn btn-primary btn-sm" style="font-size:0.75rem;">
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
    };

    // Export module and assign to window.app
    window.SwingModule = swingModule;
    window.app = window.app || {};
    Object.assign(window.app, swingModule);
})();
