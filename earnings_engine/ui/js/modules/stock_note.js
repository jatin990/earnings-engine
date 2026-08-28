// =========================================================================
// stock_note — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;
// ========================================================
        // 🧠 UNIVERSAL STOCK INTELLIGENCE & DEEP DIVE NOTE ENGINE
        // ========================================================
        app.closeStockNote = function() {
            const modal = document.getElementById('stockIntelligenceNoteModal');
            if (modal) modal.style.display = 'none';
        };

        app.openStockNote = async function(ticker, event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            const sym = (ticker || '').trim().toUpperCase();
            if (!sym) return;

            const modal = document.getElementById('stockIntelligenceNoteModal');
            const content = document.getElementById('stockIntelligenceNoteContent');
            if (!modal || !content) return;

            modal.style.display = 'flex';
            content.innerHTML = `
                <div style="padding:2rem;text-align:center;color:#cbd5e1;">
                    <div style="font-size:1.8rem;margin-bottom:0.6rem;display:inline-block;animation:spin 1s linear infinite;">⏳</div>
                    <div style="font-size:1rem;font-weight:700;color:#f8fafc;">Compiling Multi-Dimensional Intelligence Note for ${sym}...</div>
                    <div style="font-size:0.75rem;color:#94a3b8;margin-top:0.3rem;">Analyzing Price Action Dynamics, Swing Channels, News Catalysts &amp; Local/Cloud AI Models</div>
                </div>
            `;

            try {
                const res = await fetch(API_BASE + '/api/v1/stock/' + encodeURIComponent(sym) + '/intelligence-note');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const note = await res.json();
                app.renderStockIntelligenceNote(note);
            } catch (err) {
                console.error('[STOCK-NOTE] Error loading note for ' + sym, err);
                content.innerHTML = `
                    <div style="padding:1.5rem;text-align:center;color:#f87171;">
                        <div style="font-size:1.4rem;margin-bottom:0.4rem;">⚠️ Error Loading Intelligence Note</div>
                        <div style="font-size:0.8rem;color:#e2e8f0;margin-bottom:1rem;">${err.message || err}</div>
                        <button type="button" onclick="app.openStockNote('${sym}')" class="btn btn-sm" style="background:#2563eb;color:#fff;">🔄 Retry</button>
                    </div>
                `;
            }
        };

        app.renderStockIntelligenceNote = function(note) {
            const content = document.getElementById('stockIntelligenceNoteContent');
            if (!content || !note) return;

            const sym = note.ticker;
            const name = note.company_name || sym;
            const buzz = note.industry_buzz_tag || note.industry || 'Theme';
            const cmp = note.current_price != null ? `₹${Number(note.current_price).toLocaleString('en-IN')}` : '₹—';
            
            const ret30 = note.thirty_day_return_pct != null ? Number(note.thirty_day_return_pct) : null;
            const ret30Str = ret30 != null ? `${ret30 >= 0 ? '+' : ''}${ret30.toFixed(1)}%` : 'N/A';
            const ret30Color = ret30 != null && ret30 >= 0 ? '#34d399' : '#f87171';

            const dist52High = note.pct_from_52w_high != null ? `${Number(note.pct_from_52w_high).toFixed(1)}%` : '—';

            // Price Action & Reaction
            const pr = note.price_reaction || {};
            const surpVal = pr.last_eps_surprise != null ? Number(pr.last_eps_surprise) : null;
            const surpStr = surpVal != null ? `${surpVal >= 0 ? '+' : ''}${surpVal.toFixed(1)}% Beat` : 'Solid Quality Beat';
            const scoreStr = pr.last_quality_score != null ? `${pr.last_quality_score}/9` : '6/9';
            const wkHighVal = pr.last_week_high_pct != null ? Number(pr.last_week_high_pct) : null;
            const wkHighStr = wkHighVal != null ? `+${wkHighVal.toFixed(1)}%` : 'N/A';
            const wkLowVal = pr.last_week_low_pct != null ? Number(pr.last_week_low_pct) : null;
            const wkLowStr = wkLowVal != null ? `${wkLowVal >= 0 ? '+' : ''}${wkLowVal.toFixed(1)}%` : 'N/A';
            const wkMoveVal = pr.earnings_week_move_pct != null ? Number(pr.earnings_week_move_pct) : null;
            const wkMoveStr = wkMoveVal != null ? `${wkMoveVal >= 0 ? '+' : ''}${wkMoveVal.toFixed(1)}%` : 'N/A';
            const explanation = pr.price_action_explanation || 'Steady post-earnings accumulation observed.';

            // Swing Channel
            const sw = note.swing_structure || {};
            const suppStr = sw.support_level != null ? `₹${Number(sw.support_level).toLocaleString('en-IN')}` : '₹—';
            const ressStr = sw.resistance_level != null ? `₹${Number(sw.resistance_level).toLocaleString('en-IN')}` : '₹—';
            const pivotStr = sw.channel_pivot != null ? `₹${Number(sw.channel_pivot).toLocaleString('en-IN')}` : '₹—';
            const cyclesStr = `${sw.cycles || 0} Cycles (${sw.avg_cycle_days || 0}d avg)`;
            const pctSuppStr = sw.pct_from_support != null ? `+${sw.pct_from_support}% above` : '';
            const pctRessStr = sw.pct_to_resistance != null ? `${sw.pct_to_resistance}% to go` : '';

            // AI Thesis & Conviction
            const ai = note.ai_thesis || {};
            const verdict = ai.verdict || 'MODERATE_BEAT';
            const conf = ai.confidence_pct || 75;
            const modelUsed = ai.model_used || 'Local AI Engine';
            const thesisText = ai.thesis || 'Constructive fundamental momentum continuation expected.';
            const bias = ai.expected_price_bias || 'BULLISH';
            const action = ai.suggested_action || 'ACCUMULATE_PRE_EARNINGS';

            const rawDrivers = ai.growth_drivers || [];
            const drivers = Array.isArray(rawDrivers) ? rawDrivers : [rawDrivers];
            const driversHtml = drivers.length ? drivers.map(d => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${d}</li>`).join('') : '<li style="color:#94a3b8;">Order book growth and sector tailwinds.</li>';

            const rawRisks = ai.risk_factors || [];
            const risks = Array.isArray(rawRisks) ? rawRisks : [rawRisks];
            const risksHtml = risks.length ? risks.map(r => `<li style="color:#cbd5e1;margin-bottom:0.35rem;">${r}</li>`).join('') : '<li style="color:#94a3b8;">Standard market volatility and margin pressures.</li>';

            // 3Q Beat History
            const history = note.beat_history || [];
            let historyHtml = '<span style="color:#94a3b8;font-size:0.72rem;">No historical quarter data.</span>';
            if (history.length > 0) {
                historyHtml = history.map((h, idx) => {
                    const qName = `Q${idx + 1}`;
                    const qScore = h.score != null ? `${h.score}/9` : '—';
                    const qSurp = h.surprise_pct != null ? `${h.surprise_pct >= 0 ? '+' : ''}${Number(h.surprise_pct).toFixed(1)}%` : 'Beat';
                    const isPos = (h.surprise_pct == null || h.surprise_pct >= 0) && (h.score == null || h.score >= 5);
                    return `
                        <div style="background:${isPos ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'};border:1px solid ${isPos ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'};border-radius:6px;padding:0.35rem 0.55rem;text-align:center;">
                            <div style="font-size:0.65rem;color:${isPos ? '#34d399' : '#f87171'};font-weight:700;">${qName} (${h.date ? String(h.date).slice(0, 7) : 'Prior'})</div>
                            <div style="font-size:0.78rem;font-weight:800;color:#f1f5f9;font-family:var(--font-mono);">${qSurp}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">Score: ${qScore}</div>
                        </div>
                    `;
                }).join('');
            }

            // News articles
            const articles = note.news_catalysts || [];
            let newsHtml = '<div style="color:#94a3b8;font-size:0.75rem;font-style:italic;">No recent news headlines indexed.</div>';
            if (articles.length > 0) {
                newsHtml = articles.map(a => {
                    const dateStr = a.published_at ? String(a.published_at).slice(0, 10) : 'Recent';
                    const titleStr = a.title || 'Corporate Filing';
                    const sent = a.sentiment_label || 'Neutral';
                    const sentColor = sent.toLowerCase().includes('bull') || sent.toLowerCase().includes('pos') ? '#34d399' : (sent.toLowerCase().includes('bear') || sent.toLowerCase().includes('neg') ? '#f87171' : '#94a3b8');
                    const url = a.url ? `<a href="${a.url}" target="_blank" style="color:#38bdf8;text-decoration:none;margin-left:0.3rem;" onclick="event.stopPropagation();">↗</a>` : '';
                    return `
                        <div style="background:#0c101c;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.65rem;margin-bottom:0.35rem;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;">
                            <div style="font-size:0.75rem;color:#e2e8f0;line-height:1.4;">
                                <span style="color:#64748b;font-family:var(--font-mono);font-size:0.68rem;margin-right:0.35rem;">[${dateStr}]</span>
                                <span>${titleStr}</span>${url}
                            </div>
                            <span style="font-size:0.65rem;background:rgba(255,255,255,0.05);color:${sentColor};border:1px solid rgba(255,255,255,0.1);padding:0.1rem 0.35rem;border-radius:3px;white-space:nowrap;">${sent}</span>
                        </div>
                    `;
                }).join('');
            }

            content.innerHTML = `
                <!-- 1. Header Banner -->
                <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.85rem;margin-bottom:0.85rem;flex-wrap:wrap;gap:0.5rem;">
                    <div style="display:flex;align-items:center;gap:0.65rem;">
                        <div style="font-size:1.6rem;">🧠</div>
                        <div>
                            <div style="font-size:1.18rem;font-weight:800;color:#f8fafc;display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                                <span>${sym}</span>
                                <span style="font-size:0.72rem;background:rgba(168,85,247,0.2);color:#c084fc;padding:0.15rem 0.45rem;border-radius:4px;">${buzz}</span>
                                <span style="font-size:0.72rem;background:rgba(59,130,246,0.2);color:#60a5fa;padding:0.15rem 0.45rem;border-radius:4px;font-family:var(--font-mono);">${modelUsed}</span>
                            </div>
                            <div style="font-size:0.76rem;color:#94a3b8;margin-top:0.15rem;">
                                ${name} &middot; CMP: <strong style="color:#ffffff;">${cmp}</strong> &middot; 30D Return: <strong style="color:${ret30Color};">${ret30Str}</strong> &middot; 52W High Gap: <strong>${dist52High}</strong>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. Interactive Multi-Model Selector Bar -->
                <div style="background:#0c101c;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.65rem 0.85rem;margin-bottom:0.85rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;">
                    <div style="font-size:0.76rem;font-weight:700;color:#60a5fa;display:flex;align-items:center;gap:0.35rem;">
                        <span>🤖 Model Reasoning Engine (Local Ollama &amp; Online OpenRouter)</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                        <select id="stockNoteModelSelect" style="background:#05070d;border:1px solid rgba(255,255,255,0.18);color:#f1f5f9;font-size:0.72rem;padding:0.25rem 0.5rem;border-radius:5px;outline:none;">
                            <optgroup label="🖥️ Local Ollama Models">
                                <option value="llama3.2:3b" selected>llama3.2:3b (Fast Local)</option>
                                <option value="deepseek-r1:8b">deepseek-r1:8b (Deep Reasoning)</option>
                                <option value="qwen2.5-coder:latest">qwen2.5-coder (Algorithmic)</option>
                            </optgroup>
                            <optgroup label="☁️ Online Models (OpenRouter)">
                                <option value="deepseek/deepseek-r1:free">DeepSeek-R1 (Free Cloud)</option>
                                <option value="google/gemma-4-31b-it:free">Gemma-4-31B (Free Multimodal)</option>
                                <option value="z-ai/glm-5.2">GLM-5.2 (Z.ai Flagship 753B)</option>
                                <option value="meta-llama/llama-3.3-70b-instruct">Llama-3.3 70B Instruct</option>
                                <option value="mistralai/mistral-large">Mistral Large</option>
                                <option value="google/gemini-2.0-flash-001">Gemini 2.0 Flash</option>
                            </optgroup>
                        </select>
                        <button type="button" onclick="event.preventDefault(); const sel = document.getElementById('stockNoteModelSelect').value; app.runStockNoteAi('${sym}', this, sel);" class="btn btn-sm" style="background:#2563eb;color:#fff;font-size:0.72rem;padding:0.25rem 0.65rem;border-radius:5px;cursor:pointer;">
                            ⚡ Run Model
                        </button>
                    </div>
                </div>

                <!-- 3. Section: Price Action Mechanics & Reaction Dynamics -->
                <div style="background:#0b111e;border:1px solid rgba(59,130,246,0.25);border-radius:8px;padding:0.85rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.78rem;font-weight:700;color:#38bdf8;margin-bottom:0.5rem;display:flex;align-items:center;gap:0.35rem;">
                        <span>📊 Price Action Reaction Mechanics &amp; Move Breakdown</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;margin-bottom:0.6rem;">
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Prior Delivery</div>
                            <div style="font-size:0.82rem;font-weight:700;color:#34d399;font-family:var(--font-mono);">${surpStr}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Quality: ${scoreStr}</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Week Peak High</div>
                            <div style="font-size:0.82rem;font-weight:700;color:#4ade80;font-family:var(--font-mono);">${wkHighStr}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Peak Rally Magnitude</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Net 1-Wk Move</div>
                            <div style="font-size:0.82rem;font-weight:700;color:${wkMoveVal >= 0 ? '#34d399' : '#f87171'};font-family:var(--font-mono);">${wkMoveStr}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Drawdown: ${wkLowStr}</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">30-Day Trend</div>
                            <div style="font-size:0.82rem;font-weight:700;color:${ret30Color};font-family:var(--font-mono);">${ret30Str}</div>
                            <div style="font-size:0.62rem;color:#64748b;">Trend Continuation</div>
                        </div>
                    </div>
                    <div style="font-size:0.75rem;color:#cbd5e1;line-height:1.5;background:#070a12;border-radius:6px;padding:0.55rem 0.75rem;border-left:3px solid #38bdf8;">
                        ${explanation}
                    </div>
                </div>

                <!-- 4. Section: Technical Swing Range Channel -->
                <div style="background:#0b111e;border:1px solid rgba(16,185,129,0.25);border-radius:8px;padding:0.85rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.78rem;font-weight:700;color:#34d399;margin-bottom:0.5rem;display:flex;align-items:center;justify-content:space-between;">
                        <span>🎯 Technical Swing Channel &amp; Boundary Levels</span>
                        <span style="font-size:0.68rem;color:#94a3b8;font-family:var(--font-mono);">${cyclesStr}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:0.5rem;">
                        <div style="background:#070a12;border:1px solid rgba(16,185,129,0.2);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#34d399;text-transform:uppercase;font-weight:700;">Support (Buy Zone)</div>
                            <div style="font-size:0.85rem;font-weight:800;color:#6ee7b7;font-family:var(--font-mono);">${suppStr}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">${pctSuppStr}</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(59,130,246,0.2);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#60a5fa;text-transform:uppercase;font-weight:700;">Channel Pivot</div>
                            <div style="font-size:0.85rem;font-weight:800;color:#93c5fd;font-family:var(--font-mono);">${pivotStr}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">Equilibrium</div>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(239,68,68,0.2);border-radius:6px;padding:0.45rem 0.6rem;">
                            <div style="font-size:0.62rem;color:#f87171;text-transform:uppercase;font-weight:700;">Resistance (Sell Zone)</div>
                            <div style="font-size:0.85rem;font-weight:800;color:#fca5a5;font-family:var(--font-mono);">${ressStr}</div>
                            <div style="font-size:0.62rem;color:#94a3b8;">${pctRessStr}</div>
                        </div>
                    </div>
                </div>

                <!-- 5. Section: Forward AI Thesis & Conviction -->
                <div style="background:#0c101c;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.95rem;margin-bottom:0.85rem;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.45rem;flex-wrap:wrap;gap:0.4rem;">
                        <div style="font-size:0.78rem;font-weight:700;color:#38bdf8;">🧠 Forward Quantitative &amp; AI Thesis</div>
                        <div style="display:flex;gap:0.4rem;align-items:center;">
                            <span style="font-size:0.68rem;background:rgba(16,185,129,0.15);color:#34d399;padding:0.12rem 0.4rem;border-radius:4px;font-weight:700;">${conf}% Conviction</span>
                            <span style="font-size:0.68rem;background:rgba(59,130,246,0.15);color:#60a5fa;padding:0.12rem 0.4rem;border-radius:4px;font-weight:700;">${action.replace(/_/g, ' ')}</span>
                        </div>
                    </div>
                    <div style="font-size:0.82rem;color:#e2e8f0;line-height:1.55;margin-bottom:0.75rem;">${thesisText}</div>

                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;">
                        <div style="background:#070a12;border:1px solid rgba(34,197,94,0.2);border-radius:6px;padding:0.75rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#4ade80;margin-bottom:0.35rem;">🚀 Growth Drivers &amp; Order Flow</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.75rem;line-height:1.45;">${driversHtml}</ul>
                        </div>
                        <div style="background:#070a12;border:1px solid rgba(239,68,68,0.2);border-radius:6px;padding:0.75rem;">
                            <div style="font-size:0.72rem;font-weight:700;color:#f87171;margin-bottom:0.35rem;">⚠️ Key Risks &amp; Margins</div>
                            <ul style="margin:0;padding-left:1.1rem;font-size:0.75rem;line-height:1.45;">${risksHtml}</ul>
                        </div>
                    </div>
                </div>

                <!-- 6. Section: 3-Quarter Delivery History -->
                <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.8rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.45rem;display:flex;align-items:center;justify-content:space-between;">
                        <span>📈 3-Quarter Beat Track Record</span>
                        <span style="font-size:0.7rem;color:#f87171;font-family:var(--font-mono);font-weight:700;">🔥 ${note.beat_streak || 1}Q Consecutive Streak</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(110px, 1fr));gap:0.45rem;">
                        ${historyHtml}
                    </div>
                </div>

                <!-- 7. Section: News & Catalysts Considered -->
                <div style="background:#070a12;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.8rem;margin-bottom:0.85rem;">
                    <div style="font-size:0.75rem;font-weight:700;color:#e2e8f0;margin-bottom:0.45rem;">
                        📰 Corporate Filings, Catalysts &amp; News Sentiment
                    </div>
                    <div style="max-height:150px;overflow-y:auto;">
                        ${newsHtml}
                    </div>
                </div>

                <!-- Footer Actions -->
                <div style="display:flex;align-items:center;justify-content:space-between;padding-top:0.75rem;border-top:1px solid rgba(255,255,255,0.08);flex-wrap:wrap;gap:0.5rem;">
                    <div style="display:flex;gap:0.6rem;align-items:center;">
                        <a href="/stock/${encodeURIComponent(sym)}" target="_blank" style="color:#38bdf8;font-size:0.78rem;text-decoration:none;font-weight:600;">Open Full Stock Intelligence ↗</a>
                        <button type="button" onclick="app.openAddToWatchlistModal('${sym}')" class="btn btn-sm" style="background:rgba(59,130,246,0.18);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);font-size:0.72rem;padding:0.25rem 0.55rem;border-radius:5px;cursor:pointer;">⭐ Add to Watchlist</button>
                    </div>
                    <button type="button" onclick="app.closeStockNote()" class="btn btn-sm" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1);padding:0.35rem 0.85rem;border-radius:6px;font-size:0.75rem;cursor:pointer;">
                        Close
                    </button>
                </div>
            `;
        };

        app.runStockNoteAi = async function(ticker, btnEl, modelName = null) {
            if (btnEl) btnEl.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span>`;
            try {
                let url = API_BASE + '/api/v1/stock/' + encodeURIComponent(ticker) + '/intelligence-note';
                if (modelName) {
                    const provider = modelName.includes('/') ? 'openrouter' : 'ollama';
                    url += '?model_name=' + encodeURIComponent(modelName) + '&provider=' + encodeURIComponent(provider);
                }
                const res = await fetch(url, { method: 'POST' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const note = await res.json();
                app.renderStockIntelligenceNote(note);
            } catch (e) {
                console.error('[STOCK-NOTE] AI run error for ' + ticker, e);
                alert('AI Inference failed: ' + e.message);
            } finally {
                if (btnEl) btnEl.textContent = '⚡ Run Model';
            }
        };

        app.pgLocalAi = {
            _candidates: [],
            _isRunning: false,
            _timerInterval: null,
            _startTime: 0,
            _completedCount: 0,

            _watchlistsPopulated: false,

            populateWatchlists: async function() {
                const group = document.getElementById('pgBatchWatchlistsGroup');
                if (!group) return;
                try {
                    const res = await fetch(API_BASE + '/api/v1/watchlist/all');
                    if (!res.ok) return;
                    const lists = await res.json();
                    if (!Array.isArray(lists) || !lists.length) return;

                    const currentVal = document.getElementById('pgBatchSource')?.value;
                    group.innerHTML = lists.map(wl => {
                        const count = Array.isArray(wl.tickers) ? wl.tickers.length : (wl.count || 0);
                        const val = `watchlist:${wl.name}`;
                        const isSel = (currentVal === val || (!currentVal && wl.name === 'my_watchlist')) ? 'selected' : '';
                        return `<option value="${val}" ${isSel}>⭐ ${wl.display_name || wl.name} (${count} stocks)</option>`;
                    }).join('');
                    this._watchlistsPopulated = true;
                } catch (e) {
                    console.debug('[PG-LOCAL-AI] Failed to populate watchlists:', e);
                }
            },

            onSourceChange: function(source) {
                const customRow = document.getElementById('pgBatchCustomRow');
                if (customRow) {
                    customRow.style.display = (source === 'custom') ? 'block' : 'none';
                }
                this.loadCandidates();
            },

            loadCandidates: async function() {
                if (!this._watchlistsPopulated) {
                    await this.populateWatchlists();
                }

                const source = document.getElementById('pgBatchSource')?.value || 'watchlist:my_watchlist';
                const countVal = document.getElementById('pgBatchCount')?.value || '5';
                const limit = countVal === 'all' ? 100 : parseInt(countVal, 10);
                const container = document.getElementById('pgBatchListContainer');
                const countEl = document.getElementById('pgBatchSelectedCount');

                if (container) {
                    container.innerHTML = '<div style="padding:1.5rem;text-align:center;color:#60a5fa;font-size:0.78rem;"><span class="spinner"></span> Loading stock candidates for local AI...</div>';
                }

                let tickers = [];
                try {
                    if (source === 'custom') {
                        const raw = document.getElementById('pgBatchCustomTickers')?.value || '';
                        tickers = raw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
                        if (!tickers.length) {
                            tickers = ['BAJAJ-AUTO.NS', 'TCS.NS', 'INFY.NS', 'RELIANCE.NS', 'HDFCBANK.NS'];
                        }
                    } else if (source.startsWith('watchlist:')) {
                        const wlName = source.replace('watchlist:', '');
                        const res = await fetch(API_BASE + '/api/v1/watchlist/quotes?name=' + encodeURIComponent(wlName));
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.quotes || []).map(q => q.ticker);
                        }
                        if (!tickers.length) {
                            const res2 = await fetch(API_BASE + '/api/v1/watchlist/' + encodeURIComponent(wlName));
                            if (res2.ok) {
                                const data2 = await res2.json();
                                tickers = data2.tickers || [];
                            }
                        }
                    } else if (source === 'breakout') {
                        const res = await fetch(API_BASE + '/api/v1/breakout-radar?limit=' + limit);
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.candidates || []).map(c => c.ticker);
                        }
                    } else if (source === 'repeaters') {
                        const res = await fetch(API_BASE + '/api/v1/earnings-radar/repeaters?limit=' + limit);
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.repeaters || []).map(r => r.ticker);
                        }
                    } else if (source === 'nifty_50' || source === 'nse_large_cap' || source === 'all') {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/quotes?name=' + encodeURIComponent(source));
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.quotes || []).map(q => q.ticker);
                        }
                    } else {
                        const res = await fetch(API_BASE + '/api/v1/watchlist/quotes?name=my_watchlist');
                        if (res.ok) {
                            const data = await res.json();
                            tickers = (data.quotes || []).map(q => q.ticker);
                        }
                    }
                } catch (e) {
                    console.error('[PG-LOCAL-AI] Failed to fetch source tickers:', e);
                }

                if (!tickers.length) {
                    tickers = ['BAJAJ-AUTO.NS', 'TCS.NS', 'INFY.NS', 'RELIANCE.NS', 'TATAMOTORS.NS'];
                }

                tickers = tickers.slice(0, limit);
                this._candidates = tickers.map(t => ({
                    ticker: t,
                    status: 'pending',
                    result: null,
                    error: null
                }));

                if (countEl) countEl.textContent = `${this._candidates.length} stocks`;
                this.renderCandidates();
            },

            renderCandidates: function() {
                const container = document.getElementById('pgBatchListContainer');
                if (!container) return;

                if (!this._candidates.length) {
                    container.innerHTML = '<div style="padding:2rem;text-align:center;color:#64748b;font-size:0.8rem;">No stocks selected. Choose another source or enter custom tickers above.</div>';
                    return;
                }

                container.innerHTML = this._candidates.map((c, idx) => {
                    const sym = c.ticker;
                    const res = c.result || {};
                    const thesis = res.ai_thesis || {};
                    const dir = thesis.expected_price_bias || thesis.direction || 'PENDING';
                    const isBull = dir.toUpperCase() === 'BULLISH';
                    const isBear = dir.toUpperCase() === 'BEARISH';
                    const isComplete = c.status === 'completed';
                    const isRunning = c.status === 'running';

                    let statusBadge = `<span style="font-size:0.68rem;background:rgba(255,255,255,0.05);color:#94a3b8;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(255,255,255,0.1);">Pending ⏳</span>`;
                    if (isRunning) {
                        statusBadge = `<span style="font-size:0.68rem;background:rgba(251,191,36,0.15);color:#fbbf24;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(251,191,36,0.3);animation:pulse 1.2s infinite;">⚡ Inferencing (GPU)</span>`;
                    } else if (isComplete) {
                        statusBadge = `<span style="font-size:0.68rem;background:rgba(16,185,129,0.15);color:#34d399;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(16,185,129,0.3);">✅ Completed</span>`;
                    } else if (c.status === 'error') {
                        statusBadge = `<span style="font-size:0.68rem;background:rgba(239,68,68,0.15);color:#f87171;padding:0.15rem 0.45rem;border-radius:4px;border:1px solid rgba(239,68,68,0.3);">❌ Error</span>`;
                    }

                    const verdictHtml = isComplete ? `
                        <div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.25rem;flex-wrap:wrap;">
                            <span style="font-size:0.75rem;font-weight:800;background:${isBull ? 'rgba(16,185,129,0.15)' : isBear ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.08)'};color:${isBull ? '#34d399' : isBear ? '#f87171' : '#94a3b8'};padding:0.12rem 0.45rem;border-radius:4px;border:1px solid ${isBull ? 'rgba(16,185,129,0.3)' : isBear ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.1)'};">${dir} (${thesis.conviction_score_pct || 80}%)</span>
                            <span style="font-size:0.7rem;color:#38bdf8;font-weight:600;">${(thesis.suggested_action || 'ACCUMULATE').replace(/_/g, ' ')}</span>
                        </div>
                        <div style="font-size:0.74rem;color:#cbd5e1;line-height:1.4;margin-bottom:0.35rem;">
                            ${(thesis.executive_thesis || 'Technical structure and momentum align with local model forecast.').substring(0, 140)}...
                        </div>
                    ` : (isRunning ? `
                        <div style="font-size:0.75rem;color:#fbbf24;display:flex;align-items:center;gap:0.4rem;">
                            <span class="spinner" style="width:12px;height:12px;border-width:2px;"></span> Running local Ollama multi-factor reasoning on GPU...
                        </div>
                    ` : `
                        <div style="font-size:0.75rem;color:#64748b;font-style:italic;">
                            Waiting for batch execution trigger...
                        </div>
                    `);

                    return `
                        <div style="padding:0.85rem 1rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;background:${idx % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent'};border-bottom:1px solid rgba(255,255,255,0.04);">
                            <div style="flex:1;min-width:200px;">
                                <div style="display:flex;align-items:center;gap:0.45rem;margin-bottom:0.2rem;">
                                    <strong style="font-size:0.88rem;color:#ffffff;font-family:var(--font-mono);">${sym}</strong>
                                    ${statusBadge}
                                </div>
                                <div style="font-size:0.72rem;color:#94a3b8;">
                                    ${res.profile?.company_name || sym.replace('.NS', '')} • ${res.profile?.sector || 'Equities'}
                                    ${res.price_reaction?.current_price ? ` • <span style="color:#ffffff;font-family:var(--font-mono);">₹${res.price_reaction.current_price}</span>` : ''}
                                </div>
                            </div>

                            <div style="flex:2;min-width:260px;">
                                ${verdictHtml}
                            </div>

                            <div style="display:flex;gap:0.35rem;align-items:center;">
                                <button type="button" onclick="app.openStockNote('${sym}', event)" class="btn btn-secondary btn-sm" style="font-size:0.74rem;padding:0.3rem 0.65rem;border-color:rgba(99,102,241,0.3);color:#a5b4fc;display:flex;align-items:center;gap:0.3rem;">
                                    <span>🧠</span> View Note
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            },

            runBatch: async function() {
                if (this._isRunning) return;
                if (!this._candidates.length) {
                    await this.loadCandidates();
                }
                if (!this._candidates.length) return;

                this._isRunning = true;
                this._startTime = Date.now();
                this._completedCount = 0;

                const modelName = document.getElementById('pgBatchModel')?.value || 'llama3.2:3b';
                const provider = modelName.includes('kronos') ? 'kronos' : 'ollama';
                const concurrency = parseInt(document.getElementById('pgBatchConcurrency')?.value || '1', 10);

                const progressCard = document.getElementById('pgBatchProgressCard');
                const stopBtn = document.getElementById('pgBatchStopBtn');
                const runBtn = document.getElementById('pgBatchRunBtn');
                const gpuStatus = document.getElementById('pgBatchGpuStatus');
                const activityEl = document.getElementById('pgBatchActivity');
                const elapsedEl = document.getElementById('pgBatchElapsed');
                const etaEl = document.getElementById('pgBatchEta');
                const percentEl = document.getElementById('pgBatchPercent');
                const progressBar = document.getElementById('pgBatchProgressBar');

                if (progressCard) progressCard.style.display = 'block';
                if (stopBtn) stopBtn.style.display = 'inline-block';
                if (runBtn) {
                    runBtn.disabled = true;
                    runBtn.innerHTML = `<span class="spinner"></span> Processing Batch...`;
                }
                if (gpuStatus) {
                    gpuStatus.textContent = '🖥️ GPU: Busy (Inference In Progress)';
                    gpuStatus.style.color = '#fbbf24';
                    gpuStatus.style.borderColor = 'rgba(251,191,36,0.3)';
                }

                // Live Timer
                this._timerInterval = setInterval(() => {
                    const elapsedSec = Math.floor((Date.now() - this._startTime) / 1000);
                    const m = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
                    const s = String(elapsedSec % 60).padStart(2, '0');
                    if (elapsedEl) elapsedEl.textContent = `${m}:${s}`;

                    if (this._completedCount > 0 && this._completedCount < this._candidates.length) {
                        const avgSecPerItem = elapsedSec / this._completedCount;
                        const remainingItems = this._candidates.length - this._completedCount;
                        const remainingSec = Math.ceil(remainingItems * avgSecPerItem);
                        const rm = String(Math.floor(remainingSec / 60)).padStart(2, '0');
                        const rs = String(remainingSec % 60).padStart(2, '0');
                        if (etaEl) etaEl.textContent = `ETA: ~${rm}:${rs}`;
                    }
                }, 500);

                // Execute batch bounded by concurrency
                const total = this._candidates.length;
                for (let i = 0; i < total; i += concurrency) {
                    if (!this._isRunning) break;
                    const chunk = this._candidates.slice(i, i + concurrency);
                    
                    // Mark running
                    chunk.forEach(c => { c.status = 'running'; });
                    if (activityEl) {
                        activityEl.textContent = `[${i + 1}/${total}] Processing ${chunk.map(c => c.ticker).join(', ')} on GPU (${modelName})...`;
                    }
                    this.renderCandidates();

                    await Promise.all(chunk.map(async (cand) => {
                        if (!this._isRunning) return;
                        try {
                            let url = API_BASE + '/api/v1/stock/' + encodeURIComponent(cand.ticker) + '/intelligence-note';
                            url += '?model_name=' + encodeURIComponent(modelName) + '&provider=' + encodeURIComponent(provider);
                            const res = await fetch(url, { method: 'POST' });
                            if (!res.ok) throw new Error('HTTP ' + res.status);
                            const note = await res.json();
                            cand.result = note;
                            cand.status = 'completed';
                        } catch (err) {
                            console.error('[PG-LOCAL-AI] Inference failed for ' + cand.ticker, err);
                            cand.status = 'error';
                            cand.error = err.message;
                        } finally {
                            this._completedCount++;
                            const pct = Math.round((this._completedCount / total) * 100);
                            if (percentEl) percentEl.textContent = `${pct}%`;
                            if (progressBar) progressBar.style.width = `${pct}%`;
                        }
                    }));

                    this.renderCandidates();
                }

                // Finish
                this.stopBatch();
            },

            stopBatch: function() {
                this._isRunning = false;
                if (this._timerInterval) {
                    clearInterval(this._timerInterval);
                    this._timerInterval = null;
                }

                const stopBtn = document.getElementById('pgBatchStopBtn');
                const runBtn = document.getElementById('pgBatchRunBtn');
                const gpuStatus = document.getElementById('pgBatchGpuStatus');
                const activityEl = document.getElementById('pgBatchActivity');
                const etaEl = document.getElementById('pgBatchEta');

                if (stopBtn) stopBtn.style.display = 'none';
                if (runBtn) {
                    runBtn.disabled = false;
                    runBtn.innerHTML = `<span>⚡</span> Run Local AI Notes`;
                }
                if (gpuStatus) {
                    gpuStatus.textContent = '🖥️ GPU: Idle / Ready';
                    gpuStatus.style.color = '#38bdf8';
                    gpuStatus.style.borderColor = 'rgba(56,189,248,0.25)';
                }
                if (activityEl) {
                    activityEl.textContent = `Batch run finished (${this._completedCount}/${this._candidates.length} processed).`;
                }
                if (etaEl) {
                    etaEl.textContent = 'ETA: Done ✅';
                }
                this.renderCandidates();
            },
        };

})(); // end stock_note IIFE
