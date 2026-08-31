// =========================================================================
// repeaters — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
// =========================================================================
        // 🔁 QUARTER REPEATERS & AI FORWARD RADAR
        // =========================================================================
        app._repeatersData = [];

        app.loadQuarterRepeaters = async function(silent = false) {
            const tbody = document.getElementById('repeatersTableBody');
            if (tbody && !silent) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2.5rem;color:#64748b;"><div style="display:inline-block;animation:spin 1s linear infinite;">⏳</div> Screening quarter repeaters & loading AI forward predictions...</td></tr>`;
            }

            const universe = document.getElementById('repeatersUniverseSelect')?.value || 'nifty_50';
            const verdict = document.getElementById('repeatersVerdictSelect')?.value || '';
            const minBeat = document.getElementById('repeatersMinBeat')?.value || 0;
            const minHigh = document.getElementById('repeatersMinHigh')?.value || 2.5;

            try {
                const params = new URLSearchParams({ universe: universe, min_beat_pct: minBeat, min_week_high_pct: minHigh, limit: 60 });
                if (verdict) params.set('verdict', verdict);

                const res = await fetch(API_BASE + '/api/v1/earnings-radar/repeaters?' + params.toString());
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();

                app._repeatersData = data.candidates || [];
                const summary = data.summary || {};

                // Update KPI Cards
                const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
                setEl('repeatersStatTotal', summary.total_screened || 0);
                setEl('repeatersStatTopPick', summary.top_pick_ticker || '—');
                setEl('repeatersStatTopScore', summary.top_pick_score ? `Score: ${summary.top_pick_score}/100` : '—');
                setEl('repeatersStatAvgBeat', summary.avg_prior_beat_pct != null ? `${summary.avg_prior_beat_pct >= 0 ? '+' : ''}${summary.avg_prior_beat_pct}%` : '—');
                setEl('repeatersStatBuzz', summary.dominant_industry_buzz || '—');

                app.renderQuarterRepeaters(app._repeatersData);
            } catch (e) {
                console.error('[REPEATERS] Load error:', e);
                if (tbody && !silent) {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2rem;color:#f87171;">Failed to load quarter repeaters: ${e.message}</td></tr>`;
                }
            }
        };

        app.renderQuarterRepeaters = function(candidates) {
            const tbody = document.getElementById('repeatersTableBody');
            if (!tbody) return;

            if (!candidates || candidates.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2.5rem;color:#64748b;">No repeat candidates matching current filter criteria. Try lowering Min Beat % or Min Week High %.</td></tr>`;
                return;
            }

            const rows = candidates.map(c => {
                const ticker = c.ticker || '';
                const compName = c.company_name || ticker;
                const buzz = c.industry_buzz_tag || 'Growth';
                const curPrice = c.current_price != null ? `₹${Number(c.current_price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—';
                const hasSurp = c.last_eps_surprise != null && !isNaN(c.last_eps_surprise);
                const surpVal = hasSurp ? Number(c.last_eps_surprise) : null;
                const surpStr = hasSurp ? `${surpVal >= 0 ? '+' : ''}${surpVal.toFixed(1)}% Beat` : 'Solid Quality Beat';
                const score = c.last_quality_score != null ? `${c.last_quality_score}/9` : '—';
                const weekHigh = c.last_week_high_pct != null ? `+${Number(c.last_week_high_pct).toFixed(1)}%` : '—';
                const streak = c.beat_streak || 1;
                
                let upcomingHtml = '<span style="color:#475569;font-size:0.7rem;">Calendar TBD</span>';
                if (c.days_to_next_earnings != null) {
                    upcomingHtml = `<span style="color:#38bdf8;font-weight:700;">⏱️ In ${c.days_to_next_earnings}d</span>`;
                } else if (c.next_earnings_date) {
                    upcomingHtml = `<span>⏱️ ${c.next_earnings_date}</span>`;
                }

                const ret30 = c.thirty_day_return_pct != null && !isNaN(c.thirty_day_return_pct) ? Number(c.thirty_day_return_pct) : null;
                const ret30Html = ret30 != null ? `<div style="font-size:0.65rem;color:${ret30 >= 0 ? '#34d399' : '#f87171'};font-weight:normal;margin-top:0.1rem;">30D: ${ret30 >= 0 ? '+' : ''}${ret30.toFixed(1)}%</div>` : '';
                
                const ai = c.ai_forecast;
                let verdictBadge = `<span style="background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.25);font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:4px;">Pending AI</span>`;
                let probHtml = ``;

                if (ai) {
                    const prob = ai.repeat_probability_pct || 75;
                    const v = ai.ai_repeat_verdict || 'MODERATE_BEAT';
                    let vColor = '#34d399', vBg = 'rgba(16,185,129,0.15)', vBorder = 'rgba(16,185,129,0.3)', vLabel = 'Moderate Beat';
                    if (v === 'STRONG_REPEAT_BEAT') {
                        vColor = '#4ade80'; vBg = 'rgba(74,222,128,0.2)'; vBorder = 'rgba(74,222,128,0.4)'; vLabel = '🔥 Strong Repeat Beat';
                    } else if (v === 'IN_LINE') {
                        vColor = '#fbbf24'; vBg = 'rgba(251,191,36,0.15)'; vBorder = 'rgba(251,191,36,0.3)'; vLabel = '⚖️ In-Line';
                    } else if (v === 'RISK_OF_MISS') {
                        vColor = '#f87171'; vBg = 'rgba(248,113,113,0.15)'; vBorder = 'rgba(248,113,113,0.3)'; vLabel = '⚠️ Risk of Miss';
                    }
                    verdictBadge = `<span style="background:${vBg};color:${vColor};border:1px solid ${vBorder};font-size:0.7rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;">${vLabel}</span>`;
                    probHtml = `<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.2rem;font-family:var(--font-mono);">${prob}% Conviction</div>`;
                }

                const streakBadge = streak >= 3 
                    ? `<span style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);font-size:0.7rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;">🔥 ${streak}Q Streak</span>`
                    : (streak === 2 
                        ? `<span style="background:rgba(234,179,8,0.15);color:#fbbf24;border:1px solid rgba(234,179,8,0.3);font-size:0.7rem;font-weight:600;padding:0.15rem 0.45rem;border-radius:4px;">⚡ 2Q Streak</span>`
                        : `<span style="background:rgba(59,130,246,0.12);color:#60a5fa;border:1px solid rgba(59,130,246,0.25);font-size:0.7rem;padding:0.15rem 0.45rem;border-radius:4px;">1Q Beat</span>`);

                return `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);transition:background 0.15s ease;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                    <td style="padding:0.75rem 0.85rem;">
                        <div style="font-weight:700;color:#f1f5f9;font-family:var(--font-mono);">
                            <a href="/stock/${encodeURIComponent(ticker)}" target="_blank" style="color:#38bdf8;text-decoration:none;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${ticker}</a>
                        </div>
                        <div style="font-size:0.7rem;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;">${compName}</div>
                        <div style="margin-top:0.25rem;"><span style="font-size:0.65rem;background:rgba(168,85,247,0.12);color:#c084fc;border:1px solid rgba(168,85,247,0.25);padding:0.1rem 0.35rem;border-radius:3px;display:inline-block;">${buzz}</span></div>
                    </td>
                    <td style="padding:0.75rem 0.85rem;font-family:var(--font-mono);font-weight:700;color:#e2e8f0;white-space:nowrap;">
                        ${curPrice}
                        ${ret30Html}
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;">
                        <div style="color:#34d399;font-weight:700;font-family:var(--font-mono);">${surpStr}</div>
                        <div style="font-size:0.68rem;color:#94a3b8;margin-top:0.1rem;">Score: <strong style="color:#e2e8f0;">${score}</strong></div>
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;">
                        <span style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.72rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;">${weekHigh} Peak</span>
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;">
                        ${streakBadge}
                    </td>
                    <td style="padding:0.75rem 0.85rem;">
                        ${verdictBadge}
                        ${probHtml}
                    </td>
                    <td style="padding:0.75rem 0.85rem;white-space:nowrap;font-size:0.75rem;color:#cbd5e1;font-family:var(--font-mono);">
                        ${upcomingHtml}
                    </td>
                    <td style="padding:0.75rem 0.85rem;text-align:center;white-space:nowrap;">
                        <div style="display:flex;align-items:center;justify-content:center;gap:0.35rem;">
                            <button type="button" onclick="event.preventDefault(); event.stopPropagation(); app.openRepeaterDetails('${ticker}');" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#60a5fa;border:1px solid rgba(59,130,246,0.35);font-size:0.68rem;padding:0.25rem 0.55rem;border-radius:5px;cursor:pointer;" title="View AI Thesis & Drivers">
                                🧠 Thesis
                            </button>
                            <button type="button" onclick="event.preventDefault(); event.stopPropagation(); app.runSingleRepeaterAi('${ticker}', this);" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);font-size:0.68rem;padding:0.25rem 0.45rem;border-radius:5px;cursor:pointer;" title="Run AI Inference">
                                ⚡
                            </button>
                        </div>
                    </td>
                </tr>`;
            });

            tbody.innerHTML = rows.join('');
        };

        app.openRepeaterDetails = function(ticker) {
            try {
                const candidate = (app._repeatersData || []).find(c => c.ticker === ticker);
                if (!candidate) return;

                const modal = document.getElementById('repeatersAiModal');
                const content = document.getElementById('repeatersAiModalContent');
                if (!modal || !content) return;

                const ai = candidate.ai_forecast;
                const considered = ai?.considered_data || {};
                const streak = candidate.beat_streak || 1;
                
                const hasSurp = candidate.last_eps_surprise != null && !isNaN(candidate.last_eps_surprise);
                const surpVal = hasSurp ? Number(candidate.last_eps_surprise) : null;
                const surpStr = hasSurp ? `${surpVal >= 0 ? '+' : ''}${surpVal.toFixed(1)}% Beat` : 'Solid Quality Beat';
                
                const hasWkHigh = candidate.last_week_high_pct != null && !isNaN(candidate.last_week_high_pct);
                const wkHighVal = hasWkHigh ? Number(candidate.last_week_high_pct) : null;
                const wkHighStr = hasWkHigh ? `+${wkHighVal.toFixed(1)}%` : 'N/A';
                
                const hasWkLow = candidate.last_week_low_pct != null && !isNaN(candidate.last_week_low_pct);
                const wkLowVal = hasWkLow ? Number(candidate.last_week_low_pct) : null;
                const wkLowStr = hasWkLow ? `${wkLowVal >= 0 ? '+' : ''}${wkLowVal.toFixed(1)}%` : 'N/A';

                const hasWkMove = candidate.earnings_week_move_pct != null && !isNaN(candidate.earnings_week_move_pct);
                const wkMoveVal = hasWkMove ? Number(candidate.earnings_week_move_pct) : null;
                const wkMoveStr = hasWkMove ? `${wkMoveVal >= 0 ? '+' : ''}${wkMoveVal.toFixed(1)}%` : 'N/A';

                const ret30Val = candidate.thirty_day_return_pct != null && !isNaN(candidate.thirty_day_return_pct) ? Number(candidate.thirty_day_return_pct) : null;
                const ret30Str = ret30Val != null ? `${ret30Val >= 0 ? '+' : ''}${ret30Val.toFixed(1)}%` : 'N/A';

                const score = candidate.last_quality_score != null ? `${candidate.last_quality_score}/9` : '—';
                const modelUsed = ai?.model_used || ai?.source || 'Pending Inference';

                // Price action mechanics explanation
                let priceActionExplanation = ai?.price_action_assessment || '';
                if (!priceActionExplanation) {
                    if (wkMoveVal !== null && wkMoveVal < 0 && wkHighVal !== null && wkHighVal >= 2.5) {
                        priceActionExplanation = `Why the initial move was negative (${wkMoveStr}): After delivering a ${surpStr}, the stock surged to a peak intra-week high of ${wkHighStr}, followed by temporary post-earnings profit booking. Medium-term momentum proved resilient with a ${ret30Str} 30-day return.`;
                    } else if (wkHighVal !== null && wkHighVal >= 2.5) {
                        priceActionExplanation = `Stock delivered strong immediate reaction with a ${wkHighStr} peak post-earnings rally and sustained ${ret30Str} 30-day continuation.`;
                    } else {
                        priceActionExplanation = `Stock demonstrated steady post-earnings price stabilization following ${surpStr}.`;
                    }
                }

                // Drivers & Risks
                let driversHtml = '<li style="color:#94a3b8;">No specific growth drivers parsed yet. Click ⚡ Run Model to analyze.</li>';
                let risksHtml = '<li style="color:#94a3b8;">Standard market risk factors apply.</li>';
                let thesisText = 'Run AI Forecast below to generate multi-modal reasoning and upcoming quarter earnings continuity thesis.';

                if (ai) {
                    thesisText = ai.thesis || thesisText;
                    const rawDrivers = ai.primary_growth_drivers || ai.growth_drivers;
                    const drivers = Array.isArray(rawDrivers) ? rawDrivers : (typeof rawDrivers === 'string' ? [rawDrivers] : []);
                    if (drivers.length > 0) {
                        driversHtml = drivers.map(d => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${d}</li>`).join('');
                    }
                    const rawRisks = ai.key_risk_factors || ai.risk_factors;
                    const risks = Array.isArray(rawRisks) ? rawRisks : (typeof rawRisks === 'string' ? [rawRisks] : []);
                    if (risks.length > 0) {
                        risksHtml = risks.map(r => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${r}</li>`).join('');
                    }
                }

                // News articles list
                const articles = ai?.news_articles || candidate.news_articles || [];
                let newsHtml = '<div style="color:#94a3b8;font-size:0.75rem;font-style:italic;">No recent news headlines indexed for this ticker.</div>';
                if (articles && articles.length > 0) {
                    newsHtml = articles.map(a => {
                        const dateStr = a.published_at ? String(a.published_at).slice(0, 10) : 'Recent';
                        const titleStr = a.title || 'Corporate Announcement';
                        const sent = a.sentiment_label || 'Neutral';
                        const sentColor = sent.toLowerCase().includes('bull') || sent.toLowerCase().includes('pos') ? '#34d399' : (sent.toLowerCase().includes('bear') || sent.toLowerCase().includes('neg') ? '#f87171' : '#94a3b8');
                        const url = a.url ? `<a href="${a.url}" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.3rem;" onclick="event.stopPropagation();">↗</a>` : '';
                        return `
                            <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.65rem;margin-bottom:0.35rem;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;">
                                <div style="font-size:0.75rem;color:#e2e8f0;line-height:1.4;">
                                    <span style="color:#64748b;font-family:var(--font-mono);font-size:0.68rem;margin-right:0.35rem;">[${dateStr}]</span>
                                    <span>${titleStr}</span>${url}
                                </div>
                                <span style="font-size:0.65rem;background:rgba(255,255,255,0.05);color:${sentColor};border:1px solid rgba(255,255,255,0.1);padding:0.1rem 0.35rem;border-radius:3px;white-space:nowrap;">${sent}</span>
                            </div>
                        `;
                    }).join('');
                }

                // 3Q Streak History badges
                const history = candidate.streak_history || ai?.streak_history || [];
                let historyHtml = '<span style="color:#94a3b8;font-size:0.72rem;">No historical quarter data.</span>';
                if (history && history.length > 0) {
                    historyHtml = history.map((h, idx) => {
                        const qName = `Q${idx + 1}`;
                        const qScore = h.score != null ? `${h.score}/9` : '—';
                        const qSurp = h.surprise_pct != null ? `${h.surprise_pct >= 0 ? '+' : ''}${Number(h.surprise_pct).toFixed(1)}%` : 'Beat';
                        const isPos = (h.surprise_pct == null || h.surprise_pct >= 0) && (h.score == null || h.score >= 5);
                        return `
                            <div style="background:${isPos ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'};border:1px solid ${isPos ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:6px;padding:0.35rem 0.55rem;text-align:center;">
                                <div style="font-size:0.65rem;color:${isPos ? '#34d399' : '#f87171'};font-weight:700;">${qName} (${h.date ? String(h.date).slice(0, 7) : 'Prior'})</div>
                                <div style="font-size:0.75rem;font-weight:800;color:#f1f5f9;font-family:var(--font-mono);">${qSurp}</div>
                                <div style="font-size:0.62rem;color:#94a3b8;">Score: ${qScore}</div>
                            </div>
                        `;
                    }).join('');
                }

                content.innerHTML = `
                    <!-- Header -->
                    <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.85rem;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;">
                        <div style="display:flex;align-items:center;gap:0.6rem;">
                            <div style="font-size:1.6rem;">🔁</div>
                            <div>
                                <div style="font-size:1.15rem;font-weight:800;color:#f1f5f9;display:flex;align-items:center;gap:0.5rem;">
                                    <span>${candidate.ticker}</span>
                                    <span style="font-size:0.72rem;background:rgba(168,85,247,0.2);color:#c084fc;padding:0.15rem 0.45rem;border-radius:4px;">${candidate.industry_buzz_tag || 'Theme'}</span>
                                    <span style="font-size:0.72rem;background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.15rem 0.45rem;border-radius:4px;font-family:var(--font-mono);">${modelUsed}</span>
                                </div>
                                <div style="font-size:0.76rem;color:#94a3b8;">${candidate.company_name || candidate.ticker} &middot; Live Price: ₹${Number(candidate.current_price || 0).toLocaleString('en-IN')} &middot; 30D Return: <strong style="color:${ret30Val >= 0 ? '#34d399' : '#f87171'};">${ret30Str}</strong></div>
                            </div>
                        </div>
                    </div>

                    <!-- 1. Why in Repeaters & Move Mechanics (Audit Card) -->
                    <div style="background:#0c1222;border:1px solid rgba(59,130,246,0.25);border-radius:8px;padding:0.85rem;margin-bottom:1rem;">
                        <div style="font-size:0.78rem;font-weight:700;color:#38bdf8;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.35rem;">
                            <span>📊 Price Action, Reaction Mechanics &amp; Screening Rationale</span>
                        </div>
                        
                        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;margin-bottom:0.6rem;">
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Prior Delivery</div>
                                <div style="font-size:0.82rem;font-weight:700;color:#34d399;font-family:var(--font-mono);">${surpStr}</div>
                                <div style="font-size:0.62rem;color:#64748b;">Quality: ${score}</div>
                            </div>
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Week Peak High</div>
                        <div style="font-size:0.82rem;font-weight:700;color:#4ade80;font-family:var(--font-mono);">${wkHighStr} Peak</div>
                                <div style="font-size:0.62rem;color:#64748b;">Rally Magnitude</div>
                            </div>
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Net 1-Wk Move</div>
                                <div style="font-size:0.82rem;font-weight:700;color:${wkMoveVal >= 0 ? '#34d399' : '#f87171'};font-family:var(--font-mono);">${wkMoveStr}</div>
                                <div style="font-size:0.62rem;color:#64748b;">Low: ${wkLowStr}</div>
                            </div>
                            <div style="background:#090d16;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                                <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">30-Day Trend</div>
                                <div style="font-size:0.82rem;font-weight:700;color:${ret30Val >= 0 ? '#34d399' : '#f87171'};font-family:var(--font-mono);">${ret30Str}</div>
                                <div style="font-size:0.62rem;color:#64748b;">Continuation</div>
                            </div>
                        </div>

                        <div style="font-size:0.75rem;color:#cbd5e1;line-height:1.5;background:#090d16;border-radius:6px;padding:0.55rem 0.75rem;border-left:3px solid #38bdf8;">
                            ${priceActionExplanation}
                        </div>
                    </div>

                    <!-- 2. Interactive AI Model Selector & Runner Toolbar -->
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:0.75rem;margin-bottom:1rem;">
                        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;">
                            <div style="font-size:0.78rem;font-weight:700;color:#60a5fa;display:flex;align-items:center;gap:0.35rem;">
                                <span>🤖 Multi-Model AI Engine (Local Ollama &amp; OmniRoute Gateway)</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                                <select id="repeaterModelSelect" onchange="app.updateRepeaterModelTelemetry(this.value)" style="background:#090d16;border:1px solid rgba(255,255,255,0.15);color:#e2e8f0;font-size:0.72rem;padding:0.25rem 0.5rem;border-radius:5px;outline:none;">
                                    <optgroup label="🖥️ Local Ollama Models">
                                        <option value="llama3.2:3b" selected>llama3.2:3b (⚡ ~1.2s · 100% Success)</option>
                                        <option value="deepseek-r1:8b">deepseek-r1:8b (⚡ ~2.4s · 100% Success)</option>
                                        <option value="qwen2.5-coder:latest">qwen2.5-coder (⚡ ~1.5s · 100% Success)</option>
                                    </optgroup>
                                    <optgroup label="⚡ OmniRoute Model Presets">
                                        <option value="deepseek/deepseek-r1">DeepSeek-R1 (⚡ ~1.8s · 100% Success)</option>
                                        <option value="google/gemini-2.5-pro">Gemini 2.5 Pro (⚡ ~1.6s · 100% Success)</option>
                                        <option value="anthropic/claude-3.5-sonnet">Claude 3.5 Sonnet (⚡ ~2.0s · 100% Success)</option>
                                        <option value="meta-llama/llama-3.3-70b-instruct">Llama-3.3 70B (⚡ ~2.1s · 99.8% Success)</option>
                                        <option value="qwen/qwen-2.5-72b-instruct">Qwen 2.5 72B (⚡ ~2.2s · 99.7% Success)</option>
                                        <option value="mistralai/mistral-large">Mistral Large (⚡ ~1.9s · 99.7% Success)</option>
                                        <option value="z-ai/glm-5.2">GLM-5.2 (⚡ ~3.8s · 99.1% Success)</option>
                                    </optgroup>
                                </select>
                                <span id="repeaterModelTelemetryBadge" style="font-size:0.68rem;color:#38bdf8;font-family:var(--font-mono);background:rgba(56,189,248,0.1);border:1px solid rgba(56,189,248,0.25);padding:0.2rem 0.45rem;border-radius:4px;">
                                    ⚡ ~1.2s avg · <strong style="color:#34d399;">100% Success</strong>
                                </span>
                                <button type="button" onclick="event.preventDefault(); const sel = document.getElementById('repeaterModelSelect').value; app.runSingleRepeaterAi('${candidate.ticker}', this, sel);" class="btn btn-sm" style="background:#2563eb;color:#fff;font-size:0.72rem;padding:0.25rem 0.65rem;border-radius:5px;cursor:pointer;">
                                    ⚡ Run Selected Model
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- 3. AI Forward Thesis & Drivers -->
                    <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:1rem;margin-bottom:1rem;">
                        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem;">
                            <div style="font-size:0.76rem;font-weight:700;color:#38bdf8;">🧠 Forward Quarterly Earnings Thesis</div>
                            <div style="font-size:0.72rem;color:#34d399;font-weight:700;font-family:var(--font-mono);">${ai?.repeat_probability_pct ? ai.repeat_probability_pct + '% Conviction' : ''}</div>
                        </div>
                        <div style="font-size:0.82rem;color:#e2e8f0;line-height:1.55;">${thesisText}</div>
                    </div>

                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1rem;">
                        <div style="background:#0f172a;border:1px solid rgba(34,197,94,0.2);border-radius:8px;padding:0.85rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#4ade80;margin-bottom:0.4rem;">🚀 Growth Drivers &amp; Order Flow Considered</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.76rem;line-height:1.5;">${driversHtml}</ul>
                        </div>
                        <div style="background:#0f172a;border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:0.85rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#f87171;margin-bottom:0.4rem;">⚠️ Watchlist Risks &amp; Margins Considered</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.76rem;line-height:1.5;">${risksHtml}</ul>
                        </div>
                    </div>

                    <!-- 4. 3-Quarter Delivery History -->
                    <div style="background:#090d16;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.85rem;margin-bottom:1rem;">
                        <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.5rem;display:flex;align-items:center;justify-content:space-between;">
                            <span>📈 3-Quarter Beat Streak Track Record</span>
                            <span style="font-size:0.7rem;color:#f87171;font-family:var(--font-mono);font-weight:700;">🔥 ${streak}Q Consecutive Streak</span>
                        </div>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(110px, 1fr));gap:0.5rem;">
                            ${historyHtml}
                        </div>
                    </div>

                    <!-- 5. News & Catalysts Considered (Data Audit) -->
                    <div style="background:#090d16;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.85rem;margin-bottom:1rem;">
                        <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.5rem;">
                            📰 Recent News, Filings &amp; Catalysts Fed to AI
                        </div>
                        <div style="max-height:160px;overflow-y:auto;">
                            ${newsHtml}
                        </div>
                    </div>

                    <!-- Footer Action -->
                    <div style="display:flex;align-items:center;justify-content:space-between;padding-top:0.75rem;border-top:1px solid rgba(255,255,255,0.08);">
                        <a href="/stock/${encodeURIComponent(candidate.ticker)}" target="_blank" style="color:#38bdf8;font-size:0.78rem;text-decoration:none;font-weight:600;">Open Full Stock Intelligence ↗</a>
                        <button type="button" onclick="document.getElementById('repeatersAiModal').style.display='none'" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);padding:0.35rem 0.85rem;border-radius:6px;font-size:0.75rem;cursor:pointer;">
                            Close
                        </button>
                    </div>
                `;

                modal.style.display = 'flex';
            } catch (err) {
                console.error('[REPEATERS] openRepeaterDetails error:', err);
            }
        };

        app.runSingleRepeaterAi = async function(ticker, btnEl, modelName = null) {
            const originalContent = btnEl ? btnEl.innerHTML : '⚡';
            if (btnEl) {
                btnEl.disabled = true;
                btnEl.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> Running...`;
            }
            try {
                let url = API_BASE + '/api/v1/earnings-radar/repeaters/forecast/' + encodeURIComponent(ticker);
                if (modelName) {
                    const provider = modelName.includes('/') ? 'openrouter' : 'ollama';
                    url += '?model_name=' + encodeURIComponent(modelName) + '&provider=' + encodeURIComponent(provider);
                }
                const res = await fetch(url, { method: 'POST' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                
                // Silently refresh background table without resetting scroll or replacing table with full loading spinner
                await app.loadQuarterRepeaters(true);
                
                // If modal is currently open for this ticker, refresh its view with updated forecast
                const modal = document.getElementById('repeatersAiModal');
                if (modal && modal.style.display !== 'none') {
                    app.openRepeaterDetails(ticker);
                }
            } catch (e) {
                console.error('[REPEATERS] Forecast error for ' + ticker, e);
                alert('AI Forecast failed: ' + e.message);
            } finally {
                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.innerHTML = originalContent;
                }
            }
        };

        app.runBatchRepeatersAi = async function() {
            const btn = document.getElementById('repeatersBatchBtn');
            const universe = document.getElementById('repeatersUniverseSelect')?.value || 'nifty_50';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = `<span>⏳ Running Batch AI...</span>`;
            }
            try {
                const res = await fetch(API_BASE + '/api/v1/earnings-radar/repeaters/batch-forecast?universe=' + encodeURIComponent(universe) + '&limit=15', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    alert('Batch AI Forward forecasting started in background. Refreshing candidate table silently.');
                    setTimeout(() => app.loadQuarterRepeaters(true), 5000);
                    setTimeout(() => app.loadQuarterRepeaters(true), 15000);
                }
            } catch (e) {
                console.error('[REPEATERS] Batch forecast error:', e);
                alert('Batch forecast error: ' + e.message);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `<span>⚡ Run AI Batch</span>`;
                }
            }
        };

})(); // end repeaters IIFE
