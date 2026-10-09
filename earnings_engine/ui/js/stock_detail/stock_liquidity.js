/**
 * Nexus Intelligence Platform — Stock Liquidity, Volume Profile & Option Walls
 * Renders Multi-Tier Liquidity Walls, Order Book Spread, and Interactive Chart Price Lines.
 */

(function () {
    'use strict';

    const State = window.StockDetailState;
    let _liquidityData = null;

    /**
     * Load Option Chain Walls & Order Flow Liquidity Data
     */
    window.loadStockLiquidityWalls = async function () {
        const cleanSym = State.cleanTicker;
        try {
            const [chainRes, flowRes, techRes] = await Promise.allSettled([
                fetch(`/api/v1/options/chain?symbol=${encodeURIComponent(cleanSym)}`),
                fetch(`/api/v1/orderflow/${encodeURIComponent(State.ticker)}`),
                fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/technicals`),
            ]);

            let chainData = null;
            let flowData = null;
            let techData = null;

            if (chainRes.status === 'fulfilled' && chainRes.value.ok) {
                chainData = await chainRes.value.json();
            }
            if (flowRes.status === 'fulfilled' && flowRes.value.ok) {
                flowData = await flowRes.value.json();
            }
            if (techRes.status === 'fulfilled' && techRes.value.ok) {
                techData = await techRes.value.json();
            }

            _liquidityData = {
                chain: chainData,
                flow: flowData,
                technical: techData?.technical || null,
            };

            renderLiquidityUI(_liquidityData);
            window.applyLiquidityLinesToChart();
        } catch (err) {
            console.debug('Error loading liquidity walls:', err);
        }
    };

    /**
     * Render Liquidity & Volume Profile Panels
     */
    function renderLiquidityUI(data) {
        const chain = data.chain;
        const flow = data.flow;
        const tech = data.technical;

        // 1. Support & Resistance from Technicals / Swings
        if (tech) {
            if (tech.support_level) {
                window.setElText('kpiSupport', window.formatPrice(tech.support_level));
            }
            if (tech.resistance_level) {
                window.setElText('kpiResistance', window.formatPrice(tech.resistance_level));
            }
        }

        // 2. Options Hub Metrics (if available)
        if (chain && chain.success && chain.data) {
            const d = chain.data;
            if (d.max_pain) window.setElText('kpiMaxPain', window.formatPrice(d.max_pain));
            if (d.pcr) window.setElText('kpiPcr', Number(d.pcr).toFixed(2));
            if (d.call_wall) window.setElText('kpiCallWall', window.formatPrice(d.call_wall));
            if (d.put_wall) window.setElText('kpiPutWall', window.formatPrice(d.put_wall));

            // Render mini strikes bar visualizer
            renderStrikesBarVisualizer(d.strikes, d.spot_price);
        } else {
            window.setElText('kpiMaxPain', 'Non-F&O');
            window.setElText('kpiPcr', '—');
            window.setElText('kpiCallWall', '—');
            window.setElText('kpiPutWall', '—');
        }

        // 3. Cash POC & Volume Profile (if available)
        if (flow && flow.poc_price) {
            window.setElText('kpiPoc', window.formatPrice(flow.poc_price));
        }
    }

    /**
     * Mini Strikes Visualizer for Top 5 Strikes
     */
    function renderStrikesBarVisualizer(strikes, spotPrice) {
        const container = document.getElementById('stockStrikesBarContainer');
        if (!container || !strikes || strikes.length === 0) return;

        // Filter strikes within 10% of spot
        const nearStrikes = strikes
            .filter((s) => spotPrice ? Math.abs(s.strike - spotPrice) / spotPrice <= 0.10 : true)
            .slice(0, 7);

        if (nearStrikes.length === 0) return;

        const maxOi = Math.max(...nearStrikes.map((s) => Math.max(s.call_oi || 0, s.put_oi || 0)), 1);

        let html = '<div style="display:flex; flex-direction:column; gap:0.4rem;">';
        nearStrikes.forEach((s) => {
            const callPct = ((s.call_oi || 0) / maxOi) * 100;
            const putPct = ((s.put_oi || 0) / maxOi) * 100;
            const isAtm = spotPrice && Math.abs(s.strike - spotPrice) <= (spotPrice * 0.01);

            html += `
                <div style="display:grid; grid-template-columns: 1fr 65px 1fr; align-items:center; gap:0.5rem; font-size:0.72rem; font-family:var(--font-mono);">
                    <div style="display:flex; justify-content:flex-end; align-items:center;">
                        <div style="height:6px; background:rgba(239,68,68,0.7); width:${callPct}%; border-radius:2px 0 0 2px;"></div>
                    </div>
                    <div style="text-align:center; font-weight:700; color:${isAtm ? '#38bdf8' : '#ffffff'};">${s.strike}</div>
                    <div style="display:flex; justify-content:flex-start; align-items:center;">
                        <div style="height:6px; background:rgba(16,185,129,0.7); width:${putPct}%; border-radius:0 2px 2px 0;"></div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;
    }

    /**
     * Apply Liquidity Price Lines to Lightweight Chart
     */
    window.applyLiquidityLinesToChart = function () {
        if (!State.candleSeries || !_liquidityData) return;

        // Clean up previous lines
        if (State.liquidityLines && State.liquidityLines.length > 0) {
            State.liquidityLines.forEach((line) => {
                try {
                    State.candleSeries.removePriceLine(line);
                } catch (e) {}
            });
            State.liquidityLines = [];
        }

        const tech = _liquidityData.technical;
        const chain = _liquidityData.chain?.data;

        // Support Line
        if (tech && tech.support_level) {
            const line = State.candleSeries.createPriceLine({
                price: tech.support_level,
                color: '#10b981',
                lineWidth: 1.5,
                lineStyle: 2, // Dotted
                axisLabelVisible: true,
                title: 'SUPPORT',
            });
            State.liquidityLines.push(line);
        }

        // Resistance Line
        if (tech && tech.resistance_level) {
            const line = State.candleSeries.createPriceLine({
                price: tech.resistance_level,
                color: '#ef4444',
                lineWidth: 1.5,
                lineStyle: 2, // Dotted
                axisLabelVisible: true,
                title: 'RESISTANCE',
            });
            State.liquidityLines.push(line);
        }

        // Max Pain Line
        if (chain && chain.max_pain) {
            const line = State.candleSeries.createPriceLine({
                price: chain.max_pain,
                color: '#f59e0b',
                lineWidth: 1.5,
                lineStyle: 3, // Dashed
                axisLabelVisible: true,
                title: 'MAX PAIN',
            });
            State.liquidityLines.push(line);
        }

        // Call Wall (Major Resistance)
        if (chain && chain.call_wall && chain.call_wall !== tech?.resistance_level) {
            const line = State.candleSeries.createPriceLine({
                price: chain.call_wall,
                color: 'rgba(239, 68, 68, 0.7)',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'CALL WALL',
            });
            State.liquidityLines.push(line);
        }

        // Put Wall (Major Support)
        if (chain && chain.put_wall && chain.put_wall !== tech?.support_level) {
            const line = State.candleSeries.createPriceLine({
                price: chain.put_wall,
                color: 'rgba(16, 185, 129, 0.7)',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'PUT WALL',
            });
            State.liquidityLines.push(line);
        }
    };
})();
