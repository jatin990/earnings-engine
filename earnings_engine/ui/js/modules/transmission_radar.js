// ===========================================================================
// transmission_radar.js — Transmission Lead-Lag Radar Frontend Module
// Nexus Intelligence Platform · Cross-Border Supply Chain DAG Radar
// Canvas Bezier curve transmission links with fluid particle pulse animation
// ===========================================================================

(function () {
    'use strict';

    const API_BASE = window.API_BASE || window.location.origin;

    // ---------------------------------------------------------------------------
    // Module State
    // ---------------------------------------------------------------------------
    const _state = {
        currentBasketId: 'AI_INFRA_HARDWARE',
        graphData: null,          // last fetched graph payload from /api/transmission/graph
        nodes: [],
        edges: [],
        nodePositions: {},        // { node_id: { x, y, w, h } } populated after DOM render
        activeParticles: [],      // max 40 particles
        animationFrameId: null,
        selectedNodeId: null,
        isLoading: false,
        tradeMatrixFilter: 'ALL',
    };

    // Animation constants
    const MAX_PARTICLES = 40;
    const PARTICLE_SPEED = 0.014;  // speed along Bezier t [0,1] per frame at 60fps
    const PARTICLE_RADIUS = 3.5;

    // ---------------------------------------------------------------------------
    // Helpers
    // ---------------------------------------------------------------------------
    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
        );
    }

    function _fmt(num, decimals = 2, fallback = '—') {
        if (num == null || isNaN(num)) return fallback;
        const v = Number(num);
        const prefix = v > 0 ? '+' : '';
        return prefix + v.toFixed(decimals);
    }

    function _fmtPrice(num, decimals = 2) {
        if (num == null || isNaN(num)) return '—';
        return Number(num).toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }

    function _statusColors(status) {
        switch ((status || '').toUpperCase()) {
            case 'BULLISH_EXPANSION': return { color: '#34d399', bg: 'rgba(16,185,129,0.15)', border: 'rgba(16,185,129,0.35)' };
            case 'BEARISH_PULLBACK':  return { color: '#f87171', bg: 'rgba(239,68,68,0.15)',  border: 'rgba(239,68,68,0.35)' };
            default:                  return { color: '#a1a1aa', bg: 'rgba(113,113,122,0.15)', border: 'rgba(113,113,122,0.3)' };
        }
    }

    function _circuitColors(cs) {
        switch ((cs || '').toUpperCase()) {
            case 'CIRCUIT_LOCKED':   return '#ef4444';
            case 'HIGH_FREEZE_RISK': return '#f97316';
            default:                 return '#34d399';
        }
    }

    function _anomalyMeta(flag) {
        switch ((flag || '').toUpperCase()) {
            case 'CIRCUIT_FREEZE':
                return { label: '🔴 Circuit Freeze', color: '#ef4444', bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.35)' };
            case 'LEADER_DUMP_FOLLOWER_PUMP':
                return { label: '⚠️ Leader Dump / Follower Pump', color: '#f97316', bg: 'rgba(249,115,22,0.15)', border: 'rgba(249,115,22,0.35)' };
            case 'VALUATION_ELASTICITY_TRAP':
                return { label: '💣 Valuation Elasticity Trap', color: '#fbbf24', bg: 'rgba(251,191,36,0.15)', border: 'rgba(251,191,36,0.35)' };
            case 'INTRADAY_MOMENTUM_ROLLOVER':
                return { label: '📉 Intraday Momentum Rollover', color: '#60a5fa', bg: 'rgba(96,165,250,0.15)', border: 'rgba(96,165,250,0.35)' };
            default:
                return null;
        }
    }

    function _gateMeta(status) {
        if (!status || status === 'PENDING') return { cls: 'tm-gate-pending', icon: '⏳' };
        if (status === 'PASS')              return { cls: 'tm-gate-pass', icon: '✅' };
        return                               { cls: 'tm-gate-fail', icon: '❌' };
    }

    // ---------------------------------------------------------------------------
    // Canvas Utilities – Bezier cubic helper
    // ---------------------------------------------------------------------------
    function _bezierPoint(p0, p1, p2, p3, t) {
        const mt = 1 - t;
        return {
            x: mt*mt*mt*p0.x + 3*mt*mt*t*p1.x + 3*mt*t*t*p2.x + t*t*t*p3.x,
            y: mt*mt*mt*p0.y + 3*mt*mt*t*p1.y + 3*mt*t*t*p2.y + t*t*t*p3.y,
        };
    }

    // ---------------------------------------------------------------------------
    // DOM Rendering
    // ---------------------------------------------------------------------------

    function _buildNodeCard(node) {
        const sc = _statusColors(node.status);
        const anom = _anomalyMeta(node.anomaly_flag);
        const c1d = Number(node.change_1d_pct ?? 0);
        const pctColor = c1d > 0 ? '#34d399' : c1d < 0 ? '#f87171' : '#a1a1aa';
        const freshBadge = node.is_stale
            ? `<span style="background:rgba(234,179,8,0.15);color:#fde047;border:1px solid rgba(234,179,8,0.3);font-size:0.62rem;padding:0.1rem 0.4rem;border-radius:3px;font-family:var(--font-mono);">STALE·${node.snapshot_age_minutes}m</span>`
            : `<span style="background:rgba(16,185,129,0.12);color:#34d399;border:1px solid rgba(16,185,129,0.25);font-size:0.62rem;padding:0.1rem 0.4rem;border-radius:3px;font-family:var(--font-mono);">LIVE·${node.snapshot_age_minutes}m</span>`;
        const circuitColor = _circuitColors(node.circuit_status);
        const circuitBadge = (node.circuit_status && node.circuit_status !== 'STABLE')
            ? `<span style="background:rgba(239,68,68,0.12);color:${circuitColor};border:1px solid ${circuitColor}33;font-size:0.6rem;padding:0.08rem 0.38rem;border-radius:3px;font-family:var(--font-mono);" title="Circuit Status">${node.circuit_status}</span>`
            : '';
        const anomBadge = anom
            ? `<span style="background:${anom.bg};color:${anom.color};border:1px solid ${anom.border};font-size:0.62rem;padding:0.1rem 0.4rem;border-radius:3px;" title="${_esc(node.anomaly_flag)}">${anom.label}</span>`
            : '';

        const elastLabel = (node.elasticity_label && node.elasticity_label !== 'N/A (Anchor)' && node.elasticity_label !== 'N/A')
            ? `<span style="color:#a1a1aa;font-size:0.68rem;">${_esc(node.elasticity_label)}</span>`
            : '';

        const actionBadge = (node.trade_action && node.trade_action.action)
            ? `<span style="font-size:0.62rem;font-weight:800;color:${node.trade_action.action_color};background:${node.trade_action.action_color}18;border:1px solid ${node.trade_action.action_color}35;padding:0.1rem 0.35rem;border-radius:3px;">${_esc(node.trade_action.action.replace(/_/g, ' '))}</span>`
            : '';

        return `<div class="tm-node-card" id="tm-card-${_esc(node.node_id)}"
                     data-node-id="${_esc(node.node_id)}"
                     onclick="window.transmissionRadar.openDrawer('${_esc(node.node_id)}')"
                     style="border-left: 3px solid ${sc.border};">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.4rem;">
                <div style="display:flex;align-items:center;gap:0.4rem;">
                    <span style="font-size:0.95rem;font-weight:800;color:#f8fafc;">${_esc(node.symbol)}</span>
                    <span style="font-size:0.68rem;color:#71717a;">${_esc(node.market || '')}</span>
                </div>
                <div style="display:flex;align-items:center;gap:0.3rem;">
                    ${freshBadge}
                    ${circuitBadge}
                </div>
            </div>
            <div style="font-size:0.72rem;color:#a1a1aa;margin-bottom:0.45rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(node.name)}</div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.35rem;">
                <span style="font-size:1.0rem;font-weight:700;color:#f8fafc;font-family:var(--font-mono);">${node.price != null ? (node.market === 'NSE' ? '₹' : '$') + _fmtPrice(node.price) : '—'}</span>
                <span style="font-size:0.8rem;font-weight:700;color:${pctColor};font-family:var(--font-mono);">${c1d != null ? _fmt(c1d) + '%' : '—'}<span style="font-size:0.62rem;color:#71717a;font-weight:400;"> 1D</span></span>
            </div>
            <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                ${actionBadge}
                ${elastLabel}
                ${anomBadge}
            </div>
        </div>`;
    }

    function _renderNodeGrid(nodes) {
        const tier1 = document.getElementById('tmNodeListTier1');
        const tier2 = document.getElementById('tmNodeListTier2');
        const tier3 = document.getElementById('tmNodeListTier3');
        if (!tier1 || !tier2 || !tier3) return;
        tier1.innerHTML = '';
        tier2.innerHTML = '';
        tier3.innerHTML = '';

        for (const node of nodes) {
            const html = _buildNodeCard(node);
            const tier = node.tier_column || node.tier || 1;
            if (tier === 1)      tier1.innerHTML += html;
            else if (tier === 2) tier2.innerHTML += html;
            else                 tier3.innerHTML += html;
        }
    }

    function _renderAnomalyStrip(anomalies) {
        const strip = document.getElementById('transmissionAnomalyStrip');
        if (!strip) return;
        if (!anomalies || anomalies.length === 0) {
            strip.innerHTML = `<span style="font-size:0.72rem;color:#52525b;">No active anomalies detected.</span>`;
            return;
        }
        const sevColor = { 'CRITICAL': '#ef4444', 'SEVERE': '#f97316', 'HIGH': '#fbbf24' };
        strip.innerHTML = anomalies.map(a => {
            const c = sevColor[a.severity] || '#a1a1aa';
            return `<div style="flex-shrink:0;background:rgba(0,0,0,0.6);border:1px solid ${c}55;border-left:3px solid ${c};border-radius:5px;padding:0.35rem 0.6rem;display:flex;flex-direction:column;gap:0.15rem;min-width:200px;max-width:260px;" title="${_esc(a.description)}">
                <div style="font-size:0.68rem;font-weight:700;color:${c};">${_esc(a.type)} · ${_esc(a.severity)}</div>
                <div style="font-size:0.7rem;color:#d4d4d8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(a.title)}</div>
            </div>`;
        }).join('');
    }

    function _renderGates(gates) {
        const _set = (id, status, detail) => {
            const badge = document.getElementById(id + 'Badge');
            const det   = document.getElementById(id + 'Detail');
            if (!badge) return;
            const m = _gateMeta(status);
            badge.className = `tm-gate-pill ${m.cls}`;
            badge.textContent = `${m.icon} ${status || 'PENDING'}`;
            if (det) det.textContent = detail ? '— ' + detail : '';
        };
        if (!gates) return;
        _set('gate1', gates.us_anchor_stabilization?.status, gates.us_anchor_stabilization?.detail);
        _set('gate2', gates.circuit_liquidity_unlocked?.status, gates.circuit_liquidity_unlocked?.detail);
        _set('gate3', gates.q2_cash_conversion?.status, gates.q2_cash_conversion?.detail);
    }

    function _renderStaleBanner(freshness) {
        const banner = document.getElementById('transmissionStaleBanner');
        if (!banner) return;
        if (freshness && freshness.has_stale_nodes) {
            banner.style.display = 'flex';
            const txt = document.getElementById('transmissionStaleText');
            if (txt) {
                txt.textContent = `Some node snapshots exceed freshness threshold (oldest: ${freshness.oldest_snapshot_minutes}m, limit: ${freshness.stale_threshold_minutes}m). Displaying latest recorded settlement bars.`;
            }
        } else {
            banner.style.display = 'none';
        }
    }

    function _updateShockwaveOriginOptions(nodes) {
        const sel = document.getElementById('shockwaveOriginNode');
        if (!sel) return;
        sel.innerHTML = '';
        for (const n of nodes) {
            const opt = document.createElement('option');
            opt.value = n.node_id;
            opt.textContent = `${n.symbol} (${n.node_id}) — ${n.role}`;
            sel.appendChild(opt);
        }
    }

    function _renderTradeActionMatrix(nodes) {
        const tbody = document.getElementById('transmissionTradeActionBody');
        if (!tbody) return;

        let filtered = nodes || [];
        const f = _state.tradeMatrixFilter || 'ALL';
        if (f === 'BUYS') {
            filtered = filtered.filter(n => ['STRONG_BUY_DIP', 'ACCUMULATE_BREAKOUT', 'HOLD_MOMENTUM'].includes(n.trade_action?.action));
        } else if (f === 'RISK') {
            filtered = filtered.filter(n => ['TRIM_CIRCUIT_RISK', 'FADE_VALUATION_TRAP'].includes(n.trade_action?.action));
        }

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:#71717a;">No assets match filter: ${_esc(f)}</td></tr>`;
            return;
        }

        tbody.innerHTML = filtered.map(node => {
            const act = node.trade_action || { action: 'NEUTRAL_WATCH', action_color: '#a1a1aa', rationale: 'Consolidation', key_risk: 'None' };
            const c1d = Number(node.change_1d_pct ?? 0);
            const pctColor = c1d > 0 ? '#34d399' : c1d < 0 ? '#f87171' : '#a1a1aa';
            const priceStr = node.price != null ? (node.market === 'NSE' ? '₹' : '$') + _fmtPrice(node.price) : '—';

            // Elasticity badge
            const elastLabel = node.elasticity_label || '—';
            const elastRatio = node.elasticity_ratio != null ? `${Number(node.elasticity_ratio).toFixed(2)}×` : '—';
            const elastColor = (elastLabel === 'EXTREME') ? '#ef4444' : (elastLabel === 'ELEVATED') ? '#f59e0b' : (elastLabel === 'DISCOUNTED') ? '#10b981' : '#a1a1aa';

            // Circuit & Inst
            const circuitText = (node.circuit_status && node.circuit_status !== 'STABLE')
                ? `<span style="color:${_circuitColors(node.circuit_status)};font-weight:700;">${_esc(node.circuit_status)}</span>`
                : `<span style="color:#34d399;">STABLE</span>`;
            const distText = node.distance_to_lower_circuit_pct != null ? `${Number(node.distance_to_lower_circuit_pct).toFixed(1)}% to band` : '';
            const instHolding = node.institutional_holding_pct != null
                ? `<span style="${node.institutional_holding_pct < 10 ? 'color:#f59e0b;font-weight:700;' : 'color:#d4d4d8;'}">${Number(node.institutional_holding_pct).toFixed(1)}% Inst</span>`
                : '—';

            // Top catalyst
            const topCat = (node.catalysts && node.catalysts.length > 0) ? node.catalysts[0] : null;
            let catHtml = `<span style="color:#52525b;font-style:italic;">No filings on record</span>`;
            if (topCat) {
                const catBadgeBg = topCat.category === 'ORDER_WIN' ? 'rgba(16,185,129,0.15)' : topCat.category === 'EARNINGS_BEAT' ? 'rgba(59,130,246,0.15)' : 'rgba(234,179,8,0.15)';
                const catBadgeColor = topCat.category === 'ORDER_WIN' ? '#34d399' : topCat.category === 'EARNINGS_BEAT' ? '#60a5fa' : '#facc15';
                const extraVal = topCat.order_value_cr ? ` · ₹${topCat.order_value_cr} Cr` : (topCat.details ? ` · ${topCat.details}` : '');
                catHtml = `
                    <div style="display:flex;flex-direction:column;gap:0.15rem;">
                        <div style="display:flex;align-items:center;gap:0.35rem;">
                            <span style="background:${catBadgeBg};color:${catBadgeColor};border:1px solid ${catBadgeColor}33;padding:0.05rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:700;">${_esc(topCat.category)}</span>
                            <span style="color:#71717a;font-size:0.65rem;">${_esc(topCat.published_at || '')}${extraVal}</span>
                        </div>
                        <div style="color:#e4e4e7;font-size:0.72rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${_esc(topCat.title)}">${_esc(topCat.title)}</div>
                    </div>
                `;
            }

            return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); cursor: pointer;" onclick="window.transmissionRadar.openDrawer('${_esc(node.node_id)}')">
                    <td style="padding: 0.65rem 0.8rem;">
                        <div style="display:flex;align-items:center;gap:0.4rem;">
                            <span style="font-weight:800;color:#f8fafc;font-size:0.85rem;">${_esc(node.symbol)}</span>
                            <span style="color:#71717a;font-size:0.65rem;">${_esc(node.market || '')}</span>
                        </div>
                        <div style="font-size:0.68rem;color:#71717a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px;" title="${_esc(node.product_lineage || node.name)}">${_esc(node.product_lineage || node.name)}</div>
                    </td>
                    <td style="padding: 0.65rem 0.8rem;">
                        <span style="background:${act.action_color}18;color:${act.action_color};border:1px solid ${act.action_color}44;padding:0.18rem 0.5rem;border-radius:4px;font-size:0.68rem;font-weight:800;font-family:var(--font-mono);letter-spacing:0.02em;">
                            ${_esc(act.action.replace(/_/g, ' '))}
                        </span>
                    </td>
                    <td style="padding: 0.65rem 0.8rem; font-family:var(--font-mono);">
                        <div style="font-weight:700;color:#f8fafc;">${priceStr}</div>
                        <div style="color:${pctColor};font-size:0.7rem;font-weight:700;">${c1d != null ? _fmt(c1d) + '%' : '—'}</div>
                    </td>
                    <td style="padding: 0.65rem 0.8rem; font-family:var(--font-mono);">
                        <div style="color:${elastColor};font-weight:700;">${elastRatio}</div>
                        <div style="color:#71717a;font-size:0.65rem;">${_esc(elastLabel)}</div>
                    </td>
                    <td style="padding: 0.65rem 0.8rem; font-size:0.7rem;">
                        <div>${circuitText} ${distText ? `<span style="color:#71717a;font-size:0.65rem;">(${distText})</span>` : ''}</div>
                        <div style="margin-top:0.1rem;">${instHolding}</div>
                    </td>
                    <td style="padding: 0.65rem 0.8rem;">
                        ${catHtml}
                    </td>
                    <td style="padding: 0.65rem 0.8rem;">
                        <div style="color:#d4d4d8;font-size:0.72rem;line-height:1.25;">${_esc(act.rationale)}</div>
                        ${act.key_risk ? `<div style="color:#f87171;font-size:0.65rem;margin-top:0.2rem;display:flex;align-items:center;gap:0.25rem;"><span>⚠️</span><span>${_esc(act.key_risk)}</span></div>` : ''}
                    </td>
                </tr>
            `;
        }).join('');
    }

    // ---------------------------------------------------------------------------
    // Canvas Animation Engine
    // ---------------------------------------------------------------------------

    function _captureNodePositions() {
        _state.nodePositions = {};
        const container = document.getElementById('transmissionGraphContainer');
        if (!container) return;
        const cRect = container.getBoundingClientRect();

        for (const node of _state.nodes) {
            const card = document.getElementById(`tm-card-${node.node_id}`);
            if (!card) continue;
            const r = card.getBoundingClientRect();
            _state.nodePositions[node.node_id] = {
                x: r.left - cRect.left + r.width / 2,
                y: r.top - cRect.top + r.height / 2,
                w: r.width,
                h: r.height,
            };
        }
    }

    function _spawnParticlesForEdges() {
        _state.activeParticles = [];
        const edges = _state.edges;
        if (!edges.length) return;

        // color palette by impact level
        const impactColors = {
            CRITICAL: '#ef4444',
            HIGH:     '#f97316',
            MODERATE: '#38bdf8',
            LOW:      '#6b7280',
        };

        // Distribute particles evenly across edges (up to MAX_PARTICLES total)
        const perEdge = Math.max(1, Math.floor(MAX_PARTICLES / edges.length));
        for (const edge of edges) {
            const src = _state.nodePositions[edge.source_node_id || edge.source];
            const tgt = _state.nodePositions[edge.target_node_id || edge.target];
            if (!src || !tgt) continue;
            const color = impactColors[edge.impact_level] || '#38bdf8';
            for (let i = 0; i < perEdge && _state.activeParticles.length < MAX_PARTICLES; i++) {
                _state.activeParticles.push({
                    src, tgt,
                    t: i / perEdge,      // stagger start positions
                    color,
                    speed: PARTICLE_SPEED * (0.8 + Math.random() * 0.4),
                    alpha: 0.6 + Math.random() * 0.4,
                });
            }
        }
    }

    function _drawFrame() {
        const canvas = document.getElementById('transmissionCanvas');
        if (!canvas) return;
        const container = document.getElementById('transmissionGraphContainer');
        if (!container) return;

        // Resize canvas if needed
        const dpr = window.devicePixelRatio || 1;
        const cw = container.offsetWidth;
        const ch = container.offsetHeight;
        if (canvas.width !== cw * dpr || canvas.height !== ch * dpr) {
            canvas.width  = cw * dpr;
            canvas.height = ch * dpr;
            canvas.style.width  = cw + 'px';
            canvas.style.height = ch + 'px';
        }

        const ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cw, ch);

        // Draw static Bezier curve links
        for (const edge of _state.edges) {
            const src = _state.nodePositions[edge.source_node_id || edge.source];
            const tgt = _state.nodePositions[edge.target_node_id || edge.target];
            if (!src || !tgt) continue;

            const impactAlpha = { CRITICAL: 0.65, HIGH: 0.5, MODERATE: 0.35, LOW: 0.2 };
            const alpha = impactAlpha[edge.impact_level] || 0.35;

            ctx.beginPath();
            ctx.moveTo(src.x, src.y);
            // Cubic Bezier with horizontal control points creating natural S-curve
            const cpx = src.x + (tgt.x - src.x) * 0.45;
            ctx.bezierCurveTo(cpx, src.y, cpx, tgt.y, tgt.x, tgt.y);
            ctx.strokeStyle = edge.pulse_color || '#38bdf8';
            ctx.globalAlpha = alpha;
            ctx.lineWidth = 1.2;
            ctx.setLineDash([4, 8]);
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // Draw & advance particles
        ctx.globalAlpha = 1;
        for (const p of _state.activeParticles) {
            const src = p.src;
            const tgt = p.tgt;
            const cpx = src.x + (tgt.x - src.x) * 0.45;

            // Control points matching the curve above
            const cp1 = { x: cpx, y: src.y };
            const cp2 = { x: cpx, y: tgt.y };
            const pos = _bezierPoint(src, cp1, cp2, tgt, p.t);

            ctx.beginPath();
            ctx.arc(pos.x, pos.y, PARTICLE_RADIUS, 0, Math.PI * 2);
            ctx.fillStyle = p.color;
            ctx.globalAlpha = p.alpha;
            ctx.fill();

            // Outer glow
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, PARTICLE_RADIUS * 2.2, 0, Math.PI * 2);
            ctx.fillStyle = p.color;
            ctx.globalAlpha = p.alpha * 0.25;
            ctx.fill();

            p.t += p.speed;
            if (p.t > 1) p.t = 0;  // loop around
        }

        ctx.globalAlpha = 1;
        _state.animationFrameId = requestAnimationFrame(_drawFrame);
    }

    function _startAnimation() {
        if (_state.animationFrameId) {
            cancelAnimationFrame(_state.animationFrameId);
            _state.animationFrameId = null;
        }
        // Capture positions after DOM has settled
        setTimeout(() => {
            _captureNodePositions();
            _spawnParticlesForEdges();
            _drawFrame();
        }, 120);
    }

    function _stopAnimation() {
        if (_state.animationFrameId) {
            cancelAnimationFrame(_state.animationFrameId);
            _state.animationFrameId = null;
        }
    }

    // ---------------------------------------------------------------------------
    // Data Fetch & Render
    // ---------------------------------------------------------------------------

    async function _fetchAndRender(basketId, forceRefresh = false) {
        if (_state.isLoading) return;
        _state.isLoading = true;
        _state.currentBasketId = basketId;

        const btn = document.getElementById('btnRefreshTransmission');
        if (btn) btn.textContent = '⟳ Refreshing…';

        try {
            const refreshParam = forceRefresh ? '&refresh=true' : '';
            const res = await fetch(`${API_BASE}/api/transmission/graph?basket_id=${encodeURIComponent(basketId)}${refreshParam}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            _state.graphData = data;
            _state.nodes     = data.nodes || [];
            _state.edges     = data.edges || [];

            // Theme label
            const themeEl = document.getElementById('transmissionThemeLabel');
            if (themeEl && data.basket) themeEl.textContent = data.basket.macro_theme || '';

            // Render
            _renderNodeGrid(_state.nodes);
            _renderTradeActionMatrix(_state.nodes);
            _renderAnomalyStrip(data.anomalies || []);
            _renderGates(data.reentry_gates);
            _renderStaleBanner(data.data_freshness);
            _updateShockwaveOriginOptions(_state.nodes);

            // Restart animation
            _stopAnimation();
            _startAnimation();
        } catch (err) {
            console.error('[TransmissionRadar] fetch error:', err);
            const t1 = document.getElementById('tmNodeListTier1');
            if (t1) t1.innerHTML = `<span style="color:#f87171;font-size:0.75rem;">Failed to load graph: ${_esc(String(err))}</span>`;
        } finally {
            _state.isLoading = false;
            if (btn) btn.textContent = '⟳ Refresh';
        }
    }

    // ---------------------------------------------------------------------------
    // Node Drawer Inspector
    // ---------------------------------------------------------------------------

    function _buildDrawerContent(node) {
        const anom = _anomalyMeta(node.anomaly_flag);
        const sc = _statusColors(node.status);
        const c1d = Number(node.change_1d_pct ?? 0);
        const pctColor = c1d > 0 ? '#34d399' : c1d < 0 ? '#f87171' : '#a1a1aa';

        const _row = (label, value, mono = false) => {
            if (value == null || value === '—') return '';
            return `<div style="display:flex;justify-content:space-between;align-items:center;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.05);">
                <span style="font-size:0.72rem;color:#71717a;">${_esc(label)}</span>
                <span style="font-size:0.75rem;color:#e4e4e7;${mono ? 'font-family:var(--font-mono);' : ''}">${value}</span>
            </div>`;
        };

        const anomSection = anom ? `<div style="background:${anom.bg};border:1px solid ${anom.border};border-radius:6px;padding:0.5rem 0.65rem;margin-top:0.5rem;">
            <div style="font-size:0.72rem;font-weight:700;color:${anom.color};">${anom.label}</div>
            <div style="font-size:0.68rem;color:#a1a1aa;margin-top:0.2rem;">${_esc(node.anomaly_flag)}</div>
        </div>` : '';

        const elast = (node.elasticity_ratio != null)
            ? `${Number(node.elasticity_ratio).toFixed(2)}× (${_esc(node.elasticity_label)})`
            : _esc(node.elasticity_label || '—');

        const circuit = node.circuit_status
            ? `<span style="color:${_circuitColors(node.circuit_status)};">${_esc(node.circuit_status)}</span>${node.distance_to_lower_circuit_pct != null ? ` · ${Number(node.distance_to_lower_circuit_pct).toFixed(2)}% to limit` : ''}`
            : '—';

        const dataModeBadge = node.data_mode === 'INTRADAY'
            ? `<span style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:0.08rem 0.35rem;border-radius:3px;font-size:0.65rem;">INTRADAY</span>`
            : `<span style="background:rgba(113,113,122,0.15);color:#a1a1aa;border:1px solid rgba(113,113,122,0.3);padding:0.08rem 0.35rem;border-radius:3px;font-size:0.65rem;">EOD</span>`;

        // Connected edges
        const outEdges = _state.edges.filter(e => (e.source_node_id || e.source) === node.node_id);
        const inEdges  = _state.edges.filter(e => (e.target_node_id || e.target) === node.node_id);

        const edgesSect = (outEdges.length + inEdges.length > 0) ? `
            <div style="margin-top:0.75rem;">
                <div style="font-size:0.68rem;font-weight:700;color:#a1a1aa;text-transform:uppercase;margin-bottom:0.4rem;">Transmission Links</div>
                ${outEdges.map(e => `<div style="font-size:0.7rem;color:#6b7280;padding:0.2rem 0;">→ <b style="color:#d4d4d8;">${_esc(e.target_node_id || e.target)}</b> via ${_esc(e.catalyst || e.catalyst_event || '—')} · ${_esc(e.impact_level || '—')} impact · ${e.lag_hours ?? 0}h lag</div>`).join('')}
                ${inEdges.map(e => `<div style="font-size:0.7rem;color:#6b7280;padding:0.2rem 0;">← <b style="color:#d4d4d8;">${_esc(e.source_node_id || e.source)}</b> via ${_esc(e.catalyst || e.catalyst_event || '—')} · ${_esc(e.impact_level || '—')} impact · ${e.lag_hours ?? 0}h lag</div>`).join('')}
            </div>
        ` : '';

        const prodLineage = node.product_lineage ? `<div style="font-size:0.7rem;color:#71717a;margin-bottom:0.6rem;font-style:italic;">${_esc(node.product_lineage)}</div>` : '';

        // Tactical Trade Action Box
        const act = node.trade_action || { action: 'NEUTRAL_WATCH', action_color: '#a1a1aa', rationale: 'Consolidation', key_risk: 'None' };
        const tradeActionCard = `
            <div style="background:rgba(0,0,0,0.6);border:1px solid ${act.action_color}44;border-left:4px solid ${act.action_color};border-radius:6px;padding:0.75rem 0.85rem;margin:0.6rem 0;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.35rem;">
                    <span style="font-size:0.68rem;text-transform:uppercase;color:#71717a;font-weight:700;letter-spacing:0.04em;">TACTICAL TRADE ACTION</span>
                    <span style="background:${act.action_color}22;color:${act.action_color};border:1px solid ${act.action_color}55;padding:0.15rem 0.45rem;border-radius:4px;font-size:0.7rem;font-weight:800;font-family:var(--font-mono);">
                        ${_esc(act.action.replace(/_/g, ' '))}
                    </span>
                </div>
                <div style="font-size:0.75rem;color:#f8fafc;font-weight:600;line-height:1.3;margin-bottom:0.35rem;">${_esc(act.rationale)}</div>
                ${act.key_risk ? `<div style="font-size:0.68rem;color:#fca5a5;background:rgba(239,68,68,0.1);padding:0.25rem 0.45rem;border-radius:4px;display:flex;align-items:center;gap:0.3rem;"><span>⚠️ Risk:</span><span>${_esc(act.key_risk)}</span></div>` : ''}
            </div>
        `;

        // Catalysts Section
        const catalysts = node.catalysts || [];
        let catalystsSect = '';
        if (catalysts.length > 0) {
            catalystsSect = `
                <div style="margin-top:0.75rem;">
                    <div style="font-size:0.68rem;font-weight:700;color:#a1a1aa;text-transform:uppercase;margin-bottom:0.4rem;letter-spacing:0.04em;">
                        Recent Corporate Catalysts (${catalysts.length})
                    </div>
                    <div style="display:flex;flex-direction:column;gap:0.4rem;">
                        ${catalysts.map(c => {
                            const badgeBg = c.category === 'ORDER_WIN' ? 'rgba(16,185,129,0.15)' : c.category === 'EARNINGS_BEAT' ? 'rgba(59,130,246,0.15)' : 'rgba(234,179,8,0.15)';
                            const badgeColor = c.category === 'ORDER_WIN' ? '#34d399' : c.category === 'EARNINGS_BEAT' ? '#60a5fa' : '#facc15';
                            const extraVal = c.order_value_cr ? ` · ₹${c.order_value_cr} Cr Order` : (c.details ? ` · ${c.details}` : '');
                            return `
                                <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:5px;padding:0.45rem 0.6rem;">
                                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">
                                        <span style="background:${badgeBg};color:${badgeColor};border:1px solid ${badgeColor}33;padding:0.05rem 0.35rem;border-radius:3px;font-size:0.6rem;font-weight:700;">${_esc(c.category)}</span>
                                        <span style="color:#71717a;font-size:0.65rem;">${_esc(c.published_at || '')}${extraVal}</span>
                                    </div>
                                    <div style="font-size:0.72rem;color:#e4e4e7;line-height:1.25;">${_esc(c.title)}</div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        }

        return `
            <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.35rem;">
                <span style="font-size:0.7rem;background:${sc.bg};color:${sc.color};border:1px solid ${sc.border};padding:0.1rem 0.45rem;border-radius:4px;">${_esc(node.status || '—')}</span>
                <span style="font-size:0.7rem;color:#71717a;">${_esc(node.role || '')} · ${_esc(node.market || '')}</span>
            </div>
            ${prodLineage}
            ${tradeActionCard}
            ${_row('Price', node.price != null ? (node.market === 'NSE' ? '₹' : '$') + _fmtPrice(node.price) : '—', true)}
            ${_row('1D Change', c1d != null ? `<span style="color:${pctColor};">${_fmt(c1d)}%</span>` : '—', true)}
            ${_row('5D Change', node.change_5d_pct != null ? `${_fmt(node.change_5d_pct)}%` : '—', true)}
            ${_row('20D Change', node.change_20d_pct != null ? `${_fmt(node.change_20d_pct)}%` : '—', true)}
            ${_row('Trailing P/E', node.trailing_pe != null ? Number(node.trailing_pe).toFixed(1) + '×' : '—', true)}
            ${_row('Forward P/E', node.forward_pe != null ? Number(node.forward_pe).toFixed(1) + '×' : '—', true)}
            ${_row('Price/Sales', node.price_to_sales != null ? Number(node.price_to_sales).toFixed(1) + '×' : '—', true)}
            ${_row('Institutional Holding', node.institutional_holding_pct != null ? Number(node.institutional_holding_pct).toFixed(1) + '%' : '—', true)}
            ${_row('Elasticity Ratio', elast, true)}
            ${_row('Circuit Status', circuit)}
            ${_row('Delivery %', node.delivery_pct != null ? Number(node.delivery_pct).toFixed(1) + '%' : '—', true)}
            ${_row('Volume Multiple (20D)', node.volume_multiple_20d != null ? Number(node.volume_multiple_20d).toFixed(2) + '×' : '—', true)}
            ${_row('Volume Velocity', node.volume_velocity_ratio != null ? Number(node.volume_velocity_ratio).toFixed(2) + '×' : '—', true)}
            ${_row('Data Mode', dataModeBadge)}
            ${_row('Snapshot As Of', node.snapshot_as_of_utc ? node.snapshot_as_of_utc.replace('T', ' ').slice(0, 16) + ' UTC' : '—')}
            ${anomSection}
            ${catalystsSect}
            ${edgesSect}
        `;
    }

    // ---------------------------------------------------------------------------
    // Shockwave Flash Animation
    // ---------------------------------------------------------------------------

    function _applyShockwaveFlash(propagation) {
        for (const item of propagation) {
            const card = document.getElementById(`tm-card-${item.node_id}`);
            if (!card) continue;
            // stagger by propagation_order
            setTimeout(() => {
                card.classList.add('shockwave-flash');
                setTimeout(() => card.classList.remove('shockwave-flash'), 1400);
            }, (item.propagation_order || 0) * 350);
        }
    }

    // ---------------------------------------------------------------------------
    // Public API exposed as window.transmissionRadar
    // ---------------------------------------------------------------------------

    window.transmissionRadar = {

        init() {
            _fetchAndRender(_state.currentBasketId);

            // Re-capture positions on window resize (debounced)
            let _resizeTimer;
            window.addEventListener('resize', () => {
                clearTimeout(_resizeTimer);
                _resizeTimer = setTimeout(() => {
                    _captureNodePositions();
                    _spawnParticlesForEdges();
                }, 250);
            });
        },

        onBasketChange(basketId) {
            if (!basketId || basketId === _state.currentBasketId) return;
            _state.currentBasketId = basketId;
            _fetchAndRender(basketId);
        },

        refreshGraph() {
            _fetchAndRender(_state.currentBasketId, true);
        },

        openDrawer(nodeId) {
            const node = _state.nodes.find(n => n.node_id === nodeId);
            if (!node) return;
            _state.selectedNodeId = nodeId;

            const sym  = document.getElementById('drawerNodeSymbol');
            const name = document.getElementById('drawerNodeName');
            const cont = document.getElementById('drawerNodeContent');
            const drw  = document.getElementById('transmissionNodeDrawer');
            if (!drw) return;

            if (sym)  sym.textContent  = node.symbol;
            if (name) name.textContent = `${node.name} · ${node.role}`;
            if (cont) cont.innerHTML   = _buildDrawerContent(node);
            drw.style.display = 'block';
        },

        closeDrawer() {
            const drw = document.getElementById('transmissionNodeDrawer');
            if (drw) drw.style.display = 'none';
            _state.selectedNodeId = null;
        },

        openShockwaveModal() {
            const modal = document.getElementById('transmissionShockwaveModal');
            if (modal) modal.style.display = 'flex';
        },

        async runShockwaveSimulation() {
            const modal = document.getElementById('transmissionShockwaveModal');
            const originSel = document.getElementById('shockwaveOriginNode');
            const slider    = document.getElementById('shockwaveSlider');
            if (!originSel || !slider) return;

            const payload = {
                basket_id:        _state.currentBasketId,
                origin_node_id:   originSel.value,
                anchor_shock_pct: parseFloat(slider.value),
            };

            const runBtn = modal ? modal.querySelector('button[onclick*="runShockwaveSimulation"]') : null;
            if (runBtn) runBtn.textContent = 'Propagating…';

            try {
                const res = await fetch(`${API_BASE}/api/transmission/simulate-shockwave`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                if (modal) modal.style.display = 'none';
                _applyShockwaveFlash(data.propagation || []);

                // Optional: toast feedback
                if (typeof window.showToast === 'function') {
                    window.showToast(`⚡ Shockwave launched from ${payload.origin_node_id}: ${data.propagation.length} nodes affected`, 'info');
                }
            } catch (err) {
                console.error('[TransmissionRadar] shockwave error:', err);
            } finally {
                if (runBtn) runBtn.textContent = 'Execute Wave';
            }
        },

        openGate3Modal() {
            const modal = document.getElementById('transmissionGate3Modal');
            if (modal) modal.style.display = 'flex';

            // Pre-fill with current gate3 status
            const currentStatus = _state.graphData?.reentry_gates?.q2_cash_conversion?.status || 'PENDING';
            const sel = document.getElementById('gate3StatusSelect');
            if (sel) sel.value = currentStatus;
        },

        async submitGate3Update() {
            const modal       = document.getElementById('transmissionGate3Modal');
            const statusSel   = document.getElementById('gate3StatusSelect');
            const updatedBy   = document.getElementById('gate3UpdatedByInput');
            if (!statusSel) return;

            const payload = {
                status:     statusSel.value,
                updated_by: (updatedBy?.value || 'quant_desk').trim() || 'quant_desk',
            };

            const saveBtn = modal ? modal.querySelector('button[onclick*="submitGate3Update"]') : null;
            if (saveBtn) saveBtn.textContent = 'Saving…';

            try {
                const res = await fetch(`${API_BASE}/api/transmission/baskets/${encodeURIComponent(_state.currentBasketId)}/gate3`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                if (modal) modal.style.display = 'none';

                // Refresh graph to pull updated gate status
                await _fetchAndRender(_state.currentBasketId);

                if (typeof window.showToast === 'function') {
                    window.showToast(`Gate 3 updated → ${payload.status}`, 'success');
                }
            } catch (err) {
                console.error('[TransmissionRadar] gate3 update error:', err);
            } finally {
                if (saveBtn) saveBtn.textContent = 'Save Status';
            }
        },

        filterTradeMatrix(type) {
            _state.tradeMatrixFilter = type;
            const btnAll = document.getElementById('tmFilterAll');
            const btnBuys = document.getElementById('tmFilterBuys');
            const btnRisk = document.getElementById('tmFilterRisk');

            const activeStyle = 'background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);padding:0.25rem 0.65rem;border-radius:4px;font-size:0.7rem;font-weight:700;cursor:pointer;';
            const inactiveStyle = 'background:rgba(255,255,255,0.05);color:#a1a1aa;border:1px solid rgba(255,255,255,0.1);padding:0.25rem 0.65rem;border-radius:4px;font-size:0.7rem;font-weight:700;cursor:pointer;';

            if (btnAll) btnAll.style.cssText = type === 'ALL' ? activeStyle : inactiveStyle;
            if (btnBuys) btnBuys.style.cssText = type === 'BUYS' ? activeStyle : inactiveStyle;
            if (btnRisk) btnRisk.style.cssText = type === 'RISK' ? activeStyle : inactiveStyle;

            _renderTradeActionMatrix(_state.nodes);
        },

        destroy() {
            _stopAnimation();
        },
    };

    // ---------------------------------------------------------------------------
    // App Integration Hook: called from dashboard.js switchTab('transmission')
    // ---------------------------------------------------------------------------

    window.initTransmissionRadar = function () {
        window.transmissionRadar.init();
    };

})();
