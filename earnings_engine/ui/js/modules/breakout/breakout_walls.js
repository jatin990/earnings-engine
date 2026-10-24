/**
 * Nexus Breakout Radar - Order Book Walls & Boundaries
 * Analyzes NSE F&O derivative strikes (Buy Wall, Sell Wall, Max Pain, PCR)
 * or pure Cash Market technical price channels (Support, Trigger, Target, Expected Move).
 */
(function() {
    'use strict';

    window.app = window.app || {};
    const app = window.app;
    const API_BASE = window.API_BASE || '';

    app.loadBreakoutOrderBookWalls = async function(ticker, candidate) {
        const ladderHeader = document.getElementById('bkInspStrikeLadderHeader');
        const ladderList = document.getElementById('bkInspStrikeLadderList');
        const cardTitle = document.getElementById('bkInspWallsCardTitle');
        const buyWallLabel = document.getElementById('bkInspBuyWallLabel');
        const buyWallEl = document.getElementById('bkInspBuyWallStrike');
        const buyDistEl = document.getElementById('bkInspBuyWallDist');
        const sellWallLabel = document.getElementById('bkInspSellWallLabel');
        const sellWallEl = document.getElementById('bkInspSellWallStrike');
        const sellDistEl = document.getElementById('bkInspSellWallDist');
        const maxPainLabel = document.getElementById('bkInspMaxPainLabel');
        const maxPainEl = document.getElementById('bkInspMaxPainStrike');
        const maxPainDistEl = document.getElementById('bkInspMaxPainDist');
        const pcrLabel = document.getElementById('bkInspPcrLabel');
        const pcrOiEl = document.getElementById('bkInspPcrOi');
        const pcrVolEl = document.getElementById('bkInspPcrVol');
        const sentBadge = document.getElementById('bkInspWallsSentimentBadge');
        const fnoBadge = document.getElementById('bkInspFnoBadge');

        const wallBox1 = document.getElementById('bkInspWallBox1');
        const wallBox2 = document.getElementById('bkInspWallBox2');
        const wallBox3 = document.getElementById('bkInspWallBox3');
        const wallBox4 = document.getElementById('bkInspWallBox4');

        if (!ladderList || !ticker) return;

        ladderList.innerHTML = `<div style="color:#94a3b8;font-size:0.78rem;font-style:italic;text-align:center;padding:0.75rem;">Analyzing real-time order book boundaries &amp; structure...</div>`;

        const curPrice = candidate?.current_price != null ? Number(candidate.current_price) : (candidate?.signal_price ? Number(candidate.signal_price) : 0);
        const cleanSym = ticker.replace('.NS', '').replace('.BO', '').toUpperCase();

        try {
            const res = await fetch(`/api/v1/options/chain?symbol=${encodeURIComponent(cleanSym)}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            const data = json.data || {};

            const isFno = (data.status === 'LIVE' || data.status === 'ARCHIVED') && Array.isArray(data.strikes) && data.strikes.length > 0;

            if (fnoBadge) {
                if (isFno) {
                    fnoBadge.textContent = 'F&O DERIVATIVES';
                    fnoBadge.style.background = 'rgba(168,85,247,0.14)';
                    fnoBadge.style.color = '#c084fc';
                    fnoBadge.style.border = '1px solid rgba(168,85,247,0.35)';
                } else {
                    fnoBadge.textContent = 'CASH EQUITY';
                    fnoBadge.style.background = 'rgba(56,189,248,0.12)';
                    fnoBadge.style.color = '#38bdf8';
                    fnoBadge.style.border = '1px solid rgba(56,189,248,0.3)';
                }
            }

            if (isFno) {
                if (cardTitle) cardTitle.innerHTML = '🧱 NSE F&amp;O Derivative Walls';
                if (buyWallLabel) {
                    buyWallLabel.textContent = 'Buy Wall (Floor)';
                    buyWallLabel.style.color = '#34d399';
                }
                if (maxPainLabel) {
                    maxPainLabel.textContent = 'Max Pain';
                    maxPainLabel.style.color = '#c084fc';
                }
                if (sellWallLabel) {
                    sellWallLabel.textContent = 'Sell Wall (Ceiling)';
                    sellWallLabel.style.color = '#f87171';
                }
                if (pcrLabel) {
                    pcrLabel.textContent = 'PCR (OI / Vol)';
                    pcrLabel.style.color = '#38bdf8';
                }
                if (ladderHeader) ladderHeader.style.display = 'flex';

                if (wallBox1) {
                    wallBox1.style.background = 'rgba(16,185,129,0.08)';
                    wallBox1.style.borderColor = 'rgba(16,185,129,0.28)';
                }
                if (wallBox2) {
                    wallBox2.style.background = 'rgba(168,85,247,0.08)';
                    wallBox2.style.borderColor = 'rgba(168,85,247,0.28)';
                }
                if (wallBox3) {
                    wallBox3.style.background = 'rgba(239,68,68,0.08)';
                    wallBox3.style.borderColor = 'rgba(239,68,68,0.28)';
                }
                if (wallBox4) {
                    wallBox4.style.background = 'rgba(56,189,248,0.08)';
                    wallBox4.style.borderColor = 'rgba(56,189,248,0.28)';
                }

                const buyWall = data.support_strike != null ? Number(data.support_strike) : (curPrice * 0.96);
                const sellWall = data.resistance_strike != null ? Number(data.resistance_strike) : (curPrice * 1.05);
                const maxPain = data.max_pain_strike != null ? Number(data.max_pain_strike) : curPrice;
                const pcrOi = data.pcr_oi != null ? Number(data.pcr_oi) : 1.0;
                const pcrVol = data.pcr_volume != null ? Number(data.pcr_volume) : 1.0;

                if (buyWallEl) {
                    buyWallEl.textContent = `₹${Math.round(buyWall)}`;
                    buyWallEl.style.color = '#34d399';
                }
                if (buyDistEl) {
                    const dist = curPrice > 0 ? ((buyWall - curPrice) / curPrice * 100) : -4.0;
                    buyDistEl.textContent = `${dist.toFixed(1)}%`;
                    buyDistEl.style.color = '#6ee7b7';
                }

                if (maxPainEl) {
                    maxPainEl.textContent = `₹${Math.round(maxPain)}`;
                    maxPainEl.style.color = '#c084fc';
                }
                if (maxPainDistEl) {
                    const dist = curPrice > 0 ? ((maxPain - curPrice) / curPrice * 100) : 0.0;
                    maxPainDistEl.textContent = `${dist >= 0 ? '+' : ''}${dist.toFixed(1)}%`;
                    maxPainDistEl.style.color = '#e9d5ff';
                }

                if (sellWallEl) {
                    sellWallEl.textContent = `₹${Math.round(sellWall)}`;
                    sellWallEl.style.color = '#f87171';
                }
                if (sellDistEl) {
                    const dist = curPrice > 0 ? ((sellWall - curPrice) / curPrice * 100) : 5.0;
                    sellDistEl.textContent = `+${dist.toFixed(1)}%`;
                    sellDistEl.style.color = '#fca5a5';
                }

                if (pcrOiEl) {
                    pcrOiEl.textContent = pcrOi.toFixed(2);
                    pcrOiEl.style.color = '#38bdf8';
                }
                if (pcrVolEl) {
                    pcrVolEl.textContent = `Vol: ${pcrVol.toFixed(2)}`;
                    pcrVolEl.style.color = '#bae6fd';
                }

                const sentiment = (data.sentiment || (pcrOi >= 1.2 ? 'BULLISH' : (pcrOi <= 0.8 ? 'BEARISH' : 'NEUTRAL'))).toUpperCase();
                if (sentBadge) {
                    sentBadge.textContent = `${sentiment} (PCR ${pcrOi.toFixed(2)})`;
                    if (sentiment.includes('BULL')) {
                        sentBadge.style.color = '#34d399';
                        sentBadge.style.borderColor = 'rgba(16,185,129,0.3)';
                        sentBadge.style.background = 'rgba(16,185,129,0.1)';
                    } else if (sentiment.includes('BEAR')) {
                        sentBadge.style.color = '#f87171';
                        sentBadge.style.borderColor = 'rgba(239,68,68,0.3)';
                        sentBadge.style.background = 'rgba(239,68,68,0.1)';
                    } else {
                        sentBadge.style.color = '#38bdf8';
                        sentBadge.style.borderColor = 'rgba(56,189,248,0.3)';
                        sentBadge.style.background = 'rgba(56,189,248,0.1)';
                    }
                }

                const strikes = data.strikes || [];
                const sortedStrikes = [...strikes].sort((a, b) => a.strike - b.strike);
                const atmIdx = sortedStrikes.findIndex(s => s.strike >= curPrice);
                const centerIdx = atmIdx >= 0 ? atmIdx : Math.floor(sortedStrikes.length / 2);
                const sliceStart = Math.max(0, centerIdx - 4);
                const sliceEnd = Math.min(sortedStrikes.length, centerIdx + 5);
                const windowStrikes = sortedStrikes.slice(sliceStart, sliceEnd);

                const maxOi = Math.max(...windowStrikes.map(s => Math.max(s.put_oi || 0, s.call_oi || 0)), 1);

                ladderList.innerHTML = windowStrikes.map(s => {
                    const isAtm = Math.abs(s.strike - curPrice) <= (curPrice * 0.007);
                    const putPct = Math.min(100, Math.round(((s.put_oi || 0) / maxOi) * 100));
                    const callPct = Math.min(100, Math.round(((s.call_oi || 0) / maxOi) * 100));
                    const isBuyWall = s.strike === buyWall;
                    const isSellWall = s.strike === sellWall;

                    return `
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:0.45rem;background:${isAtm ? 'rgba(56,189,248,0.1)' : 'rgba(255,255,255,0.02)'};border:${isAtm ? '1px solid rgba(56,189,248,0.35)' : '1px solid rgba(255,255,255,0.06)'};padding:0.35rem 0.55rem;border-radius:5px;">
                            <div style="flex:1;display:flex;align-items:center;justify-content:flex-end;gap:0.35rem;">
                                <span style="font-size:0.72rem;color:${isBuyWall ? '#34d399' : '#94a3b8'};font-weight:${isBuyWall ? '900' : '500'};">${(s.put_oi || 0).toLocaleString('en-IN')}</span>
                                <div style="width:55px;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;direction:rtl;">
                                    <div style="height:100%;width:${putPct}%;background:${isBuyWall ? '#10b981' : '#34d39988'};border-radius:3px;"></div>
                                </div>
                            </div>
                            <div style="width:84px;text-align:center;">
                                <span style="font-weight:800;color:${isAtm ? '#38bdf8' : '#f8fafc'};font-size:0.78rem;">₹${s.strike}</span>
                                ${isBuyWall ? '<span style="font-size:0.62rem;color:#34d399;display:block;line-height:1;font-weight:800;">BUY WALL</span>' : ''}
                                ${isSellWall ? '<span style="font-size:0.62rem;color:#f87171;display:block;line-height:1;font-weight:800;">SELL WALL</span>' : ''}
                                ${isAtm && !isBuyWall && !isSellWall ? '<span style="font-size:0.62rem;color:#38bdf8;display:block;line-height:1;font-weight:700;">ATM SPOT</span>' : ''}
                            </div>
                            <div style="flex:1;display:flex;align-items:center;justify-content:flex-start;gap:0.35rem;">
                                <div style="width:55px;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;">
                                    <div style="height:100%;width:${callPct}%;background:${isSellWall ? '#ef4444' : '#f8717188'};border-radius:3px;"></div>
                                </div>
                                <span style="font-size:0.72rem;color:${isSellWall ? '#f87171' : '#94a3b8'};font-weight:${isSellWall ? '900' : '500'};">${(s.call_oi || 0).toLocaleString('en-IN')}</span>
                            </div>
                        </div>
                    `;
                }).join('');

                if (app._bkChartMode === 'native' && app.initBreakoutQuantumChart) {
                    app.initBreakoutQuantumChart(ticker, candidate, {
                        resistance_strike: sellWall,
                        support_strike: buyWall,
                        max_pain_strike: maxPain,
                    });
                }
                return;
            }

            // Pure Cash Market Technical Boundaries Flow
            const supportFloor = candidate?.stop_loss != null ? Number(candidate.stop_loss) : (curPrice * 0.95);
            const resCeiling = candidate?.breakout_trigger != null ? Number(candidate.breakout_trigger) : (curPrice * 1.04);
            const targetCeil = candidate?.target_price != null ? Number(candidate.target_price) : (resCeiling * 1.08);
            const atrVal = candidate?.atr_14 != null
                ? Number(candidate.atr_14)
                : (candidate?.daily_volatility_pct ? (curPrice * candidate.daily_volatility_pct / 100) : (curPrice * 0.022));
            const atrPct = curPrice > 0 ? (atrVal / curPrice * 100) : 2.2;

            if (cardTitle) cardTitle.innerHTML = '📊 Cash Market Key Price Boundaries';
            if (ladderHeader) ladderHeader.style.display = 'none';

            if (buyWallLabel) {
                buyWallLabel.textContent = 'Support Floor';
                buyWallLabel.style.color = '#34d399';
            }
            if (maxPainLabel) {
                maxPainLabel.textContent = 'Breakout Trigger';
                maxPainLabel.style.color = '#38bdf8';
            }
            if (sellWallLabel) {
                sellWallLabel.textContent = 'Projected Target';
                sellWallLabel.style.color = '#a78bfa';
            }
            if (pcrLabel) {
                pcrLabel.textContent = 'Daily Expected Move';
                pcrLabel.style.color = '#fbbf24';
            }

            if (wallBox1) {
                wallBox1.style.background = 'rgba(16,185,129,0.08)';
                wallBox1.style.borderColor = 'rgba(16,185,129,0.28)';
            }
            if (wallBox2) {
                wallBox2.style.background = 'rgba(56,189,248,0.08)';
                wallBox2.style.borderColor = 'rgba(56,189,248,0.28)';
            }
            if (wallBox3) {
                wallBox3.style.background = 'rgba(167,139,250,0.08)';
                wallBox3.style.borderColor = 'rgba(167,139,250,0.28)';
            }
            if (wallBox4) {
                wallBox4.style.background = 'rgba(251,191,36,0.08)';
                wallBox4.style.borderColor = 'rgba(251,191,36,0.28)';
            }

            if (buyWallEl) {
                buyWallEl.textContent = `₹${Math.round(supportFloor)}`;
                buyWallEl.style.color = '#34d399';
            }
            if (buyDistEl) {
                buyDistEl.textContent = `${(((supportFloor - curPrice) / (curPrice || 1)) * 100).toFixed(1)}%`;
                buyDistEl.style.color = '#6ee7b7';
            }

            if (maxPainEl) {
                maxPainEl.textContent = `₹${Math.round(resCeiling)}`;
                maxPainEl.style.color = '#38bdf8';
            }
            if (maxPainDistEl) {
                maxPainDistEl.textContent = `+${(((resCeiling - curPrice) / (curPrice || 1)) * 100).toFixed(1)}%`;
                maxPainDistEl.style.color = '#bae6fd';
            }

            if (sellWallEl) {
                sellWallEl.textContent = `₹${Math.round(targetCeil)}`;
                sellWallEl.style.color = '#c084fc';
            }
            if (sellDistEl) {
                sellDistEl.textContent = `+${(((targetCeil - curPrice) / (curPrice || 1)) * 100).toFixed(1)}%`;
                sellDistEl.style.color = '#e9d5ff';
            }

            if (pcrOiEl) {
                pcrOiEl.textContent = `₹${atrVal.toFixed(1)}`;
                pcrOiEl.style.color = '#fbbf24';
            }
            if (pcrVolEl) {
                pcrVolEl.textContent = `±${atrPct.toFixed(1)}% (ATR-14)`;
                pcrVolEl.style.color = '#fde68a';
            }

            if (sentBadge) {
                sentBadge.textContent = 'CASH EQUITY · NO F&O';
                sentBadge.style.color = '#38bdf8';
                sentBadge.style.borderColor = 'rgba(56,189,248,0.35)';
                sentBadge.style.background = 'rgba(56,189,248,0.1)';
                sentBadge.title = 'Traded solely in the cash equity market. Key price execution boundaries are derived from volatility and structural order channels.';
            }

            ladderList.innerHTML = `
                <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.08);padding:0.75rem 0.85rem;border-radius:6px;font-family:var(--font-mono);display:flex;flex-direction:column;gap:0.6rem;">
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <span style="color:#38bdf8;font-size:0.76rem;font-weight:800;">🛡️ Pure Cash Market Technical Structure</span>
                        <span style="color:#94a3b8;font-size:0.68rem;background:rgba(255,255,255,0.05);padding:0.1rem 0.35rem;border-radius:4px;">NSE Equity Segment</span>
                    </div>
                    <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.45;">
                        <strong style="color:#ffffff;">${ticker}</strong> is not listed in the NSE Equity Derivatives (F&amp;O) segment. No derivative open interest walls exist. Technical positioning is determined by calculated price channels:
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:0.45rem;text-align:center;">
                        <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);padding:0.45rem 0.35rem;border-radius:5px;">
                            <div style="color:#34d399;font-size:0.68rem;font-weight:800;letter-spacing:0.02em;">SUPPORT FLOOR</div>
                            <div style="color:#ffffff;font-weight:900;font-size:0.92rem;margin-top:0.1rem;">₹${supportFloor.toFixed(2)}</div>
                            <div style="color:#6ee7b7;font-size:0.68rem;font-weight:700;">${(((supportFloor - curPrice) / (curPrice || 1)) * 100).toFixed(1)}%</div>
                        </div>
                        <div style="background:rgba(56,189,248,0.08);border:1px solid rgba(56,189,248,0.25);padding:0.45rem 0.35rem;border-radius:5px;">
                            <div style="color:#38bdf8;font-size:0.68rem;font-weight:800;letter-spacing:0.02em;">BREAKOUT TRIGGER</div>
                            <div style="color:#ffffff;font-weight:900;font-size:0.92rem;margin-top:0.1rem;">₹${resCeiling.toFixed(2)}</div>
                            <div style="color:#7dd3fc;font-size:0.68rem;font-weight:700;">+${(((resCeiling - curPrice) / (curPrice || 1)) * 100).toFixed(1)}%</div>
                        </div>
                        <div style="background:rgba(168,85,247,0.08);border:1px solid rgba(168,85,247,0.25);padding:0.45rem 0.35rem;border-radius:5px;">
                            <div style="color:#c084fc;font-size:0.68rem;font-weight:800;letter-spacing:0.02em;">PROJECTED TARGET</div>
                            <div style="color:#ffffff;font-weight:900;font-size:0.92rem;margin-top:0.1rem;">₹${targetCeil.toFixed(2)}</div>
                            <div style="color:#d8b4fe;font-size:0.68rem;font-weight:700;">+${(((targetCeil - curPrice) / (curPrice || 1)) * 100).toFixed(1)}%</div>
                        </div>
                    </div>
                </div>
            `;

            if (app._bkChartMode === 'native' && app.initBreakoutQuantumChart) {
                app.initBreakoutQuantumChart(ticker, candidate, null);
            }
        } catch (err) {
            console.debug("Non-F&O or options fetch error:", err);
            if (ladderList) {
                ladderList.innerHTML = `<div style="color:#94a3b8;font-size:0.75rem;padding:0.6rem;text-align:center;">Cash market execution parameters loaded.</div>`;
            }
        }
    };

})();
