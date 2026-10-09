/**
 * Nexus Intelligence Platform — Multi-Model AI Consensus & Kronos Engine
 * Handles Zero-Token On-Demand AI Consensus Execution, Model Selection, and Trace Inspection.
 */

(function () {
    'use strict';

    const State = window.StockDetailState;
    let _activeTraceData = null;

    /**
     * Initialize Model Selection Pills & Timeframe
     */
    window.initStockConsensus = function () {
        loadAvailableModels();
        loadExistingConsensus();
        loadKronosForecast();
    };

    /**
     * Load Available AI Models for Selection
     */
    async function loadAvailableModels() {
        const container = document.getElementById('stockModelSelectionPills');
        if (!container) return;

        try {
            const resp = await fetch('/api/v1/consensus/omniroute-models');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            if (data && data.models && data.models.length > 0) {
                let html = '';
                data.models.forEach((m, idx) => {
                    const isSelected = idx === 0 || m.id === State.selectedModel;
                    if (isSelected) State.selectedModel = m.id;
                    html += `
                        <button type="button"
                                class="stock-model-pill ${isSelected ? 'active' : ''}"
                                onclick="window.selectConsensusModel('${m.id}', this)">
                            ${m.name || m.id}
                        </button>
                    `;
                });
                container.innerHTML = html;
            }
        } catch (e) {
            console.debug('Error loading consensus models:', e);
        }
    }

    /**
     * Model Pill Click Handler
     */
    window.selectConsensusModel = function (modelId, btnEl) {
        State.selectedModel = modelId;
        const parent = btnEl.parentElement;
        if (parent) {
            parent.querySelectorAll('.stock-model-pill').forEach((p) => p.classList.remove('active'));
        }
        btnEl.classList.add('active');
    };

    /**
     * Timeframe Selection Handler (7D, 14D, 30D, 90D)
     */
    window.selectConsensusTimeframe = function (days, btnEl) {
        State.selectedTimeframe = days;
        const parent = btnEl.parentElement;
        if (parent) {
            parent.querySelectorAll('.stock-range-btn').forEach((b) => b.classList.remove('active'));
        }
        btnEl.classList.add('active');
        loadExistingConsensus();
    };

    /**
     * Load Existing Cached Consensus (Zero-Token Default)
     */
    async function loadExistingConsensus() {
        const thesisBox = document.getElementById('stockConsensusThesis');
        const verdictBox = document.getElementById('stockConsensusVerdict');
        if (!thesisBox) return;

        try {
            const resp = await fetch(
                `/api/v1/consensus/prediction?ticker=${encodeURIComponent(State.ticker)}&timeframe_days=${State.selectedTimeframe || 14}`
            );
            if (!resp.ok) return;
            const data = await resp.json();

            if (data && data.success && data.prediction) {
                renderConsensusResult(data.prediction);
            }
        } catch (e) {
            console.debug('Error loading cached consensus:', e);
        }
    }

    /**
     * Run Multi-Model Consensus (User-Initiated POST)
     */
    window.runStockConsensus = async function (force = false) {
        const btn = document.getElementById('btnRunConsensus');
        const thesisBox = document.getElementById('stockConsensusThesis');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="stock-spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;"></span> Synthesizing...';
        }
        if (thesisBox) {
            thesisBox.innerHTML = '<div style="color:#38bdf8; font-family:var(--font-mono); display:flex; align-items:center; gap:0.5rem;"><span class="stock-spinner" style="width:16px;height:16px;border-width:2px;"></span> Generating multi-model quantitative consensus synthesis...</div>';
        }

        try {
            const resp = await fetch('/api/v1/consensus/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker: State.ticker,
                    timeframe_days: State.selectedTimeframe || 14,
                    model_override: State.selectedModel,
                    force: force,
                    include_raw_trace: true,
                }),
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${resp.status}`);
            }

            const data = await resp.json();
            if (data && data.success && data.prediction) {
                renderConsensusResult(data.prediction);
                window.showStockToast('Consensus inference completed successfully', 'success');
            } else {
                throw new Error(data.error || 'Failed to generate consensus');
            }
        } catch (err) {
            console.error('Consensus error:', err);
            window.showStockToast(`Consensus error: ${err.message}`, 'error');
            if (thesisBox) {
                thesisBox.innerHTML = `<div style="color:#fb7185; font-family:var(--font-mono);">Failed to run consensus: ${err.message}</div>`;
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '⚡ Run Multi-Model Consensus';
            }
        }
    };

    /**
     * Render Consolidated Consensus Verdict & Thesis
     */
    function renderConsensusResult(pred) {
        _activeTraceData = pred;

        const verdictEl = document.getElementById('stockConsensusVerdict');
        const scoreEl = document.getElementById('stockConsensusScore');
        const targetEl = document.getElementById('stockConsensusTarget');
        const thesisBox = document.getElementById('stockConsensusThesis');
        const traceBtn = document.getElementById('btnInspectTrace');

        if (verdictEl) {
            const stance = (pred.direction || pred.stance || 'NEUTRAL').toUpperCase();
            verdictEl.textContent = stance;
            verdictEl.className = `stock-change-pill ${stance.includes('BULL') ? 'bullish' : stance.includes('BEAR') ? 'bearish' : ''}`;
        }

        if (scoreEl) {
            const score = pred.confidence_score !== undefined ? `${(pred.confidence_score * 100).toFixed(0)}%` : '—';
            scoreEl.textContent = score;
        }

        if (targetEl) {
            targetEl.textContent = pred.target_price ? window.formatPrice(pred.target_price) : '—';
        }

        if (thesisBox) {
            const rawText = pred.synthesis || pred.rationale || pred.analysis || 'No synthesis narrative provided.';
            thesisBox.innerHTML = formatMarkdownToHTML(rawText);
        }

        if (traceBtn) {
            traceBtn.style.display = 'inline-flex';
        }
    }

    /**
     * Inspect Raw LLM Trace Modal
     */
    window.openTraceModal = function () {
        const modal = document.getElementById('stockTraceModal');
        const body = document.getElementById('stockTraceModalBody');
        if (!modal || !body) return;

        if (!_activeTraceData) {
            body.innerHTML = '<div style="color:#8e97a8;">No execution trace available. Run consensus first.</div>';
        } else {
            body.innerHTML = `
                <div style="display:flex; flex-direction:column; gap:0.75rem; font-family:var(--font-mono); font-size:0.8rem;">
                    <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:0.5rem; background:rgba(0,0,0,0.3); padding:0.75rem; border-radius:6px;">
                        <div><span style="color:#8e97a8;">Model:</span> <span style="color:#ffffff;">${_activeTraceData.model || State.selectedModel}</span></div>
                        <div><span style="color:#8e97a8;">Tokens:</span> <span style="color:#38bdf8;">${_activeTraceData.total_tokens || '—'}</span></div>
                        <div><span style="color:#8e97a8;">Latency:</span> <span style="color:#34d399;">${_activeTraceData.latency_ms ? `${_activeTraceData.latency_ms}ms` : '—'}</span></div>
                    </div>
                    <div style="background:rgba(0,0,0,0.4); padding:1rem; border-radius:6px; max-height:400px; overflow-y:auto; color:#c5cbd6; white-space:pre-wrap;">
                        ${_activeTraceData.raw_trace || _activeTraceData.prompt_context || JSON.stringify(_activeTraceData, null, 2)}
                    </div>
                </div>
            `;
        }
        modal.classList.add('active');
    };

    window.closeTraceModal = function () {
        const modal = document.getElementById('stockTraceModal');
        if (modal) modal.classList.remove('active');
    };

    /**
     * Load Kronos 14-Day Trajectory Forecast
     */
    async function loadKronosForecast() {
        const container = document.getElementById('stockKronosContainer');
        if (!container) return;

        try {
            const resp = await fetch(`/api/v1/stock/${encodeURIComponent(State.ticker)}/kronos`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (data && data.success && data.prediction) {
                const k = data.prediction;
                window.setElText('kronosExpectedMove', window.formatPercent(k.predicted_pct_move));
                window.setElText('kronosConfidence', `${(k.confidence || 0.85 * 100).toFixed(0)}%`);
                window.setElText('kronosRegime', k.market_regime || 'Trending');
            }
        } catch (e) {
            console.debug('Error loading Kronos forecast:', e);
        }
    }

    /**
     * Simple Markdown Parser for AI Theses
     */
    function formatMarkdownToHTML(text) {
        if (!text) return '';
        let escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Bold
        escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Headers
        escaped = escaped.replace(/^### (.*$)/gim, '<h4 style="color:#38bdf8; margin:0.75rem 0 0.35rem 0; font-size:0.95rem;">$1</h4>');
        escaped = escaped.replace(/^## (.*$)/gim, '<h3 style="color:#ffffff; margin:1rem 0 0.5rem 0; font-size:1.05rem;">$1</h3>');
        // Bullet points
        escaped = escaped.replace(/^\* (.*$)/gim, '<li style="margin-left:1.25rem; margin-bottom:0.25rem;">$1</li>');
        escaped = escaped.replace(/^- (.*$)/gim, '<li style="margin-left:1.25rem; margin-bottom:0.25rem;">$1</li>');
        // Line breaks
        escaped = escaped.replace(/\n\n/g, '<br/><br/>');

        return escaped;
    }
})();
