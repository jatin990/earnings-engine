/**
 * Nexus Breakout Radar - Order Book Depth Spread Overlay
 * Handles draggable order book spread ladder, Poc/VAH/VAL/Walls display, and compact/expand toggles.
 */
(function() {
    'use strict';

    window.app = window.app || {};
    const app = window.app;

    app.toggleBreakoutDepthSpread = function() {
        const overlay = document.getElementById('bkInspOrderBookDepthOverlay');
        const btn = document.getElementById('bkToggleDepthSpreadBtn');
        if (!overlay) return;
        const isHidden = overlay.style.display === 'none';
        overlay.style.display = isHidden ? 'flex' : 'none';
        if (btn) {
            btn.style.background = isHidden ? 'rgba(16,185,129,0.18)' : 'transparent';
            btn.style.color = isHidden ? '#34d399' : '#94a3b8';
        }
    };

    app._bkDepthSpreadExpanded = localStorage.getItem('breakout_depth_expanded') === 'true';

    app.toggleDepthSpreadExpansion = function() {
        app._bkDepthSpreadExpanded = !app._bkDepthSpreadExpanded;
        localStorage.setItem('breakout_depth_expanded', String(app._bkDepthSpreadExpanded));
        if (app._bkLastOrderFlowData) {
            app.renderBreakoutOrderBookSpread(app._bkLastOrderFlowData, app._bkLastCurPrice, app._bkLastWallsData);
        }
    };

    // Make the Depth Spread overlay draggable so it never permanently hides the chart behind it.
    app.initDepthSpreadDrag = function() {
        const overlay = document.getElementById('bkInspOrderBookDepthOverlay');
        const wrap = document.getElementById('bkInspLightweightChartWrap');
        if (!overlay || overlay.dataset.dragBound === '1') return;
        overlay.dataset.dragBound = '1';

        const restore = () => {
            try {
                const saved = JSON.parse(localStorage.getItem('breakout_depth_pos') || 'null');
                if (saved && saved.left != null && wrap) {
                    overlay.style.left = saved.left + 'px';
                    overlay.style.top = saved.top + 'px';
                    overlay.style.right = 'auto';
                }
            } catch (e) { /* ignore malformed saved state */ }
        };

        // Delegate: overlay persists across re-renders, its innerHTML is replaced each render.
        overlay.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            const handle = e.target.closest('#bkDepthSpreadDragHandle');
            if (!handle) return;
            e.preventDefault();
            const wrapRect = wrap ? wrap.getBoundingClientRect() : { left: 0, top: 0 };
            const rect = overlay.getBoundingClientRect();
            app._bkDepthDrag = {
                startX: e.clientX,
                startY: e.clientY,
                origLeft: rect.left - wrapRect.left,
                origTop: rect.top - wrapRect.top,
            };
            document.body.style.cursor = 'grabbing';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            const d = app._bkDepthDrag;
            if (!d || !wrap) return;
            let left = d.origLeft + (e.clientX - d.startX);
            let top = d.origTop + (e.clientY - d.startY);
            left = Math.max(0, Math.min(left, wrap.clientWidth - overlay.offsetWidth));
            top = Math.max(0, Math.min(top, wrap.clientHeight - 24));
            overlay.style.left = left + 'px';
            overlay.style.top = top + 'px';
            overlay.style.right = 'auto';
        });

        document.addEventListener('mouseup', () => {
            if (!app._bkDepthDrag) return;
            app._bkDepthDrag = null;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            try {
                if (wrap) {
                    const r = overlay.getBoundingClientRect();
                    const wrapRect = wrap.getBoundingClientRect();
                    localStorage.setItem('breakout_depth_pos', JSON.stringify({
                        left: Math.round(r.left - wrapRect.left),
                        top: Math.round(r.top - wrapRect.top),
                    }));
                }
            } catch (e) { /* ignore persist failure */ }
        });

        window.addEventListener('resize', restore);
        restore();
    };

    app.renderBreakoutOrderBookSpread = function(orderFlowData, currentPrice, wallsData) {
        const overlay = document.getElementById('bkInspOrderBookDepthOverlay');
        if (!overlay) return;
        app.initDepthSpreadDrag();

        const spreadBins = orderFlowData?.order_book_spread || [];
        const vp = orderFlowData?.volume_profile || {};
        const of = orderFlowData?.order_flow || {};
        const curP = currentPrice || orderFlowData?.current_price || 0;
        app._bkLastOrderFlowData = orderFlowData;
        app._bkLastCurPrice = curP;
        app._bkLastWallsData = wallsData;

        const isExpanded = app._bkDepthSpreadExpanded;
        const overlayWidth = isExpanded ? '360px' : '240px';
        const maxH = isExpanded ? '460px' : 'calc(100% - 35px)';
        overlay.style.width = overlayWidth;
        overlay.style.maxHeight = maxH;
        overlay.style.overflowY = isExpanded ? 'auto' : 'hidden';
        overlay.style.scrollBehavior = 'smooth';
        overlay.style.scrollbarWidth = 'thin';
        overlay.style.scrollbarColor = 'rgba(148,163,184,0.35) transparent';

        if (!spreadBins || spreadBins.length === 0) {
            const buyW = wallsData?.support_strike || curP * 0.96;
            const sellW = wallsData?.resistance_strike || curP * 1.04;
            const maxP = wallsData?.max_pain_strike || curP;
            overlay.innerHTML = `
                <div style="background: rgba(5,5,8,0.88); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; padding: 0.35rem 0.45rem; font-family: var(--font-mono); font-size: 0.58rem; box-shadow: 0 4px 12px rgba(0,0,0,0.6); pointer-events: auto;">
                    <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 0.2rem; margin-bottom: 0.3rem;">
                        <span style="color: #38bdf8; font-weight: 700;">🧱 Order Book Depth</span>
                        <span style="color: #94a3b8;">Spot ₹${curP.toFixed(1)}</span>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 3px;">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <span style="color: #f87171;">Sell Wall:</span>
                            <span style="color: #fca5a5; font-weight: 700;">₹${Number(sellW).toFixed(1)}</span>
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <span style="color: #fde047;">Max Pain:</span>
                            <span style="color: #fef08a; font-weight: 700;">₹${Number(maxP).toFixed(1)}</span>
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <span style="color: #34d399;">Buy Wall:</span>
                            <span style="color: #6ee7b7; font-weight: 700;">₹${Number(buyW).toFixed(1)}</span>
                        </div>
                    </div>
                </div>
            `;
            return;
        }

        const sorted = [...spreadBins].sort((a, b) => b.price - a.price);
        const maxVol = Math.max(1, ...sorted.map(b => b.volume || 1));
        const buyPct = of.buy_volume_pct || 50;
        const sellPct = of.sell_volume_pct || 50;
        const minVol = isExpanded ? 0 : maxVol * 0.04;

        const sellBins = sorted.filter(b => b.price > curP);
        const buyBins = sorted.filter(b => b.price <= curP);

        function fmtVol(v) {
            return v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1000 ? (v / 1000).toFixed(0) + 'k' : String(v);
        }

        function makeRow(b) {
            const isAbove = b.price > curP;
            const barColor = isAbove ? 'rgba(239,68,68,0.45)' : 'rgba(16,185,129,0.45)';
            const borderColor = isAbove ? '#ef4444' : '#10b981';
            const widthPct = Math.min(100, Math.max(8, (b.volume / maxVol) * 100));
            const isSpot = Math.abs(b.price - curP) < (curP * 0.008);

            let badge = '';
            if (b.is_call_wall) badge = '<span style="background:#ef4444;color:#fff;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">CALL WALL</span>';
            else if (b.is_put_wall) badge = '<span style="background:#10b981;color:#fff;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">PUT WALL</span>';
            else if (b.is_sell_wall) badge = '<span style="background:#ef4444;color:#fff;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">SELL</span>';
            else if (b.is_buy_wall) badge = '<span style="background:#10b981;color:#fff;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">BUY</span>';
            else if (b.is_poc) badge = '<span style="background:#f59e0b;color:#000;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">POC</span>';
            else if (b.is_vah) badge = '<span style="background:#38bdf8;color:#000;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">VAH</span>';
            else if (b.is_val) badge = '<span style="background:#34d399;color:#000;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">VAL</span>';
            else if (b.is_max_pain) badge = '<span style="background:#fde047;color:#000;font-size:0.46rem;padding:0 2px;border-radius:2px;font-weight:800;margin-left:2px;">MAX PAIN</span>';

            return `
                <div class="bk-depth-row" data-price="${b.price.toFixed(2)}" style="display:flex;align-items:center;justify-content:space-between;height:${isExpanded ? '16px' : '13px'};font-size:${isExpanded ? '0.56rem' : '0.54rem'};position:relative;background:${isSpot ? 'rgba(56,189,248,0.12)' : 'transparent'};border-radius:2px;padding:0 2px;${isSpot ? 'border-left:2px solid #38bdf8;' : ''}" title="${isAbove ? 'ASK' : 'BID'} ₹${b.price.toFixed(1)} | Vol: ${b.volume.toLocaleString()} | Buy: ${b.buy_volume.toLocaleString()} | Sell: ${b.sell_volume.toLocaleString()}">
                    <div style="position:absolute;top:1px;bottom:1px;right:0;width:${widthPct}%;background:${barColor};border-right:2px solid ${borderColor};border-radius:2px;z-index:1;"></div>
                    <span style="position:relative;z-index:2;color:${isSpot ? '#38bdf8' : isAbove ? '#fca5a5' : '#6ee7b7'};font-weight:${isSpot || b.is_poc || b.is_call_wall ? '700' : '400'};white-space:nowrap;">
                        ₹${b.price.toFixed(1)}${badge}
                    </span>
                    <span style="position:relative;z-index:2;color:#94a3b8;font-size:${isExpanded ? '0.52rem' : '0.50rem'};white-space:nowrap;">
                        ${fmtVol(b.volume)}
                    </span>
                </div>`;
        }

        const sellRows = sellBins.filter(b => b.volume >= minVol).map(makeRow).join('');
        const spotRow = `<div id="bkDepthSpotDivider" style="display:flex;align-items:center;justify-content:center;height:${isExpanded ? '22px' : '17px'};font-size:0.58rem;font-weight:800;color:#38bdf8;background:rgba(56,189,248,0.08);border-top:1px solid rgba(56,189,248,0.35);border-bottom:1px solid rgba(56,189,248,0.35);margin:2px 0;letter-spacing:0.04em;">
            <span style="display:inline-block;width:6px;height:6px;background:#38bdf8;border-radius:50%;margin-right:4px;animation:bkPulse 1.8s ease-in-out infinite;"></span>
            SPOT ₹${curP.toFixed(1)}
        </div>`;
        const buyRows = buyBins.filter(b => b.volume >= minVol).map(makeRow).join('');

        const expandIcon = isExpanded ? '↙' : '⤢';
        const expandLabel = isExpanded ? 'Compact' : 'Expand';

        const rowsContainer = `
            <div style="display:flex;flex-direction:column;gap:1px;">
                ${sellRows}
                ${spotRow}
                ${buyRows}
            </div>`;

        overlay.innerHTML = `
            <div style="background:rgba(5,5,8,0.92);border:1px solid rgba(255,255,255,0.12);border-radius:4px;padding:${isExpanded ? '0.45rem 0.55rem' : '0.35rem 0.45rem'};font-family:var(--font-mono);box-shadow:0 4px 16px rgba(0,0,0,0.7);pointer-events:auto;backdrop-filter:blur(8px);">
                <div id="bkDepthSpreadDragHandle" style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.2rem;margin-bottom:0.25rem;cursor:grab;user-select:none;pointer-events:all;" title="Drag to reposition Depth Spread · × to collapse">
                    <span style="color:#38bdf8;font-weight:700;font-size:0.60rem;">🧱 Depth Spread</span>
                    <div style="display:flex;align-items:center;gap:6px;pointer-events:all;">
                        <span style="color:#fbbf24;font-size:0.52rem;">POC: ₹${vp.poc ? Number(vp.poc).toFixed(1) : '—'}</span>
                        <button onclick="app.toggleDepthSpreadExpansion()" style="background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.3);color:#38bdf8;font-size:0.52rem;padding:1px 5px;border-radius:3px;cursor:pointer;font-family:var(--font-mono);font-weight:700;white-space:nowrap;" title="${expandLabel} depth spread ladder">${expandIcon} ${expandLabel}</button>
                        <button onclick="app.toggleBreakoutDepthSpread()" style="background:transparent;border:none;color:#64748b;font-size:0.62rem;cursor:pointer;padding:0 2px;line-height:1;vertical-align:middle;" title="Close Depth Spread">×</button>
                    </div>
                </div>
                <div style="display:flex;height:5px;border-radius:2px;overflow:hidden;margin-bottom:0.3rem;" title="Order Flow: ${buyPct}% Bids vs ${sellPct}% Asks">
                    <div style="width:${buyPct}%;background:#10b981;"></div>
                    <div style="width:${sellPct}%;background:#ef4444;"></div>
                </div>
                ${isExpanded ? '<div style="display:flex;justify-content:space-between;font-size:0.48rem;color:#94a3b8;margin-bottom:4px;padding:0 2px;"><span>▲ ASKS (Sell)</span><span>BIDS (Buy) ▼</span></div>' : ''}
                ${rowsContainer}
            </div>
            <style>@keyframes bkPulse{0%,100%{opacity:1}50%{opacity:0.35}}</style>`;

        if (isExpanded) {
            setTimeout(() => {
                const spotEl = document.getElementById('bkDepthSpotDivider');
                if (spotEl) spotEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
            }, 120);
        }
    };

})();
