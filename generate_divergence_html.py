import json
from pathlib import Path

data_file = Path("institutional_divergence_data.json")
with open(data_file, "r", encoding="utf-8") as f:
    data = json.load(f)

html_template = """<title>Institutional Flow Divergence Radar</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  :root {
    --bg-primary: #0b0f19;
    --bg-secondary: #131b2e;
    --bg-card: #182238;
    --text-main: #f1f5f9;
    --text-muted: #94a3b8;
    --border-subtle: #23314d;
    --dii-teal: #0d9488;
    --dii-emerald: #10b981;
    --fii-rose: #f43f5e;
    --fii-crimson: #e11d48;
    --net-indigo: #6366f1;
  }
  body {
    background-color: var(--bg-primary);
    color: var(--text-main);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    margin: 0;
  }
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: var(--bg-secondary);
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: var(--border-subtle);
    border-radius: 3px;
  }
  .chart-tooltip {
    position: absolute;
    pointer-events: none;
    transition: opacity 0.15s ease, transform 0.15s ease;
    z-index: 50;
  }
</style>

<div class="min-h-screen p-4 md:p-8 custom-scrollbar">

  <!-- Header Section -->
  <div class="max-w-7xl mx-auto mb-8">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-6">
      <div>
        <div class="flex items-center gap-3">
          <span class="px-2.5 py-1 text-xs font-semibold rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">QUANTITATIVE MACRO</span>
          <span class="text-xs text-slate-400">NSE India · Cash & F&O Markets · 09 Sep 2026</span>
        </div>
        <h1 class="text-2xl md:text-3xl font-bold mt-2 tracking-tight text-white flex items-center gap-2">
          🏛️ Institutional Flow Divergence Radar
        </h1>
        <p class="text-sm text-slate-400 mt-1 max-w-2xl">
          Point-in-Time quantitative divergence analytics: Domestic Institutions (DII/Mutual Funds) vs. Foreign Portfolio Investors (FII/FPI) across Cash & Derivatives.
        </p>
      </div>

      <div class="flex items-center gap-3">
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center gap-3">
          <div class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
          <div>
            <div class="text-xs text-slate-400 font-medium">Macro Regime</div>
            <div class="text-sm font-bold text-emerald-400">DII Absorption · Net Bullish</div>
          </div>
        </div>
      </div>
    </div>

    <!-- KPI Summary Hero Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
      <!-- Card 1: DII Cumulative Inflow -->
      <div class="bg-slate-900/80 border border-slate-800/80 rounded-xl p-5 relative overflow-hidden">
        <div class="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-xl -mr-6 -mt-6"></div>
        <div class="text-xs font-semibold text-emerald-400 uppercase tracking-wider">38D DII Cash Inflow</div>
        <div class="text-2xl font-bold text-white mt-1.5">+₹38,981 <span class="text-sm font-normal text-emerald-400">Cr</span></div>
        <div class="flex items-center gap-1 text-xs text-slate-400 mt-2">
          <span class="text-emerald-400 font-semibold">+₹48.1 Cr</span> today · Systematic SIP Inflow
        </div>
      </div>

      <!-- Card 2: FII Cumulative Outflow -->
      <div class="bg-slate-900/80 border border-slate-800/80 rounded-xl p-5 relative overflow-hidden">
        <div class="absolute top-0 right-0 w-24 h-24 bg-rose-500/5 rounded-full blur-xl -mr-6 -mt-6"></div>
        <div class="text-xs font-semibold text-rose-400 uppercase tracking-wider">38D FII Cash Outflow</div>
        <div class="text-2xl font-bold text-white mt-1.5">-₹31,185 <span class="text-sm font-normal text-rose-400">Cr</span></div>
        <div class="flex items-center gap-1 text-xs text-slate-400 mt-2">
          <span class="text-rose-400 font-semibold">-₹38.5 Cr</span> today · Foreign Selling Streak
        </div>
      </div>

      <!-- Card 3: Net Cash Absorption -->
      <div class="bg-slate-900/80 border border-slate-800/80 rounded-xl p-5 relative overflow-hidden">
        <div class="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-xl -mr-6 -mt-6"></div>
        <div class="text-xs font-semibold text-indigo-400 uppercase tracking-wider">Net Market Absorption</div>
        <div class="text-2xl font-bold text-white mt-1.5">+₹7,796 <span class="text-sm font-normal text-indigo-400">Cr</span></div>
        <div class="flex items-center gap-1 text-xs text-slate-400 mt-2">
          <span class="text-indigo-400 font-semibold">+₹9.6 Cr</span> net domestic liquidity surplus
        </div>
      </div>

      <!-- Card 4: FII Index Futures Bias -->
      <div class="bg-slate-900/80 border border-slate-800/80 rounded-xl p-5 relative overflow-hidden">
        <div class="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-full blur-xl -mr-6 -mt-6"></div>
        <div class="text-xs font-semibold text-amber-400 uppercase tracking-wider">FII Index Futures Long %</div>
        <div class="text-2xl font-bold text-rose-400 mt-1.5">11.0% <span class="text-xs font-normal text-amber-400">(Extreme Short)</span></div>
        <div class="flex items-center gap-1 text-xs text-slate-400 mt-2">
          <span class="text-amber-400 font-semibold">-276,250</span> net contracts · Short Squeeze Zone
        </div>
      </div>
    </div>
  </div>

  <!-- Main Visualizations Grid -->
  <div class="max-w-7xl mx-auto space-y-8">

    <!-- Chart 1: Daily Cash Market Divergence (Diverging Bar Chart) -->
    <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>📊 Daily Institutional Cash Flow Spread (₹ Crores)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            Diverging view: DII Inflows (Emerald) vs. FII Outflows (Rose) with Net Market Absorption (Indigo Dots).
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex items-center gap-3 text-xs text-slate-300">
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-emerald-500"></span> DII Net</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-rose-500"></span> FII Net</span>
            <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-indigo-400"></span> Net Market</span>
          </div>
          <select id="timeframeSelect" class="bg-slate-800 border border-slate-700 text-xs text-white rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500">
            <option value="14">Last 14 Sessions</option>
            <option value="20">Last 20 Sessions</option>
            <option value="38" selected>All 38 Sessions</option>
          </select>
        </div>
      </div>

      <!-- SVG Chart Container -->
      <div class="w-full overflow-x-auto custom-scrollbar relative">
        <div id="divergenceChartWrapper" class="min-w-[700px] h-[320px] relative">
          <svg id="divergenceSvg" class="w-full h-full"></svg>
          <div id="chartTooltip" class="chart-tooltip bg-slate-950/95 border border-slate-700 rounded-lg p-3 text-xs shadow-2xl backdrop-blur-md opacity-0"></div>
        </div>
      </div>
    </div>

    <!-- Chart 2: Cumulative Divergence Trajectory (Dual Line / Area) -->
    <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>📈 Cumulative Flow Divergence Trajectory</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            Diverging curves: Domestic SIP inflows (+₹38.9k Cr) steadily absorbing Foreign Institutional Outflows (-₹31.1k Cr).
          </p>
        </div>
        <div class="flex items-center gap-4 text-xs text-slate-300">
          <span class="flex items-center gap-1.5"><span class="w-3 h-1 bg-emerald-400 rounded"></span> Cum. DII (+₹38.9k Cr)</span>
          <span class="flex items-center gap-1.5"><span class="w-3 h-1 bg-rose-400 rounded"></span> Cum. FII (-₹31.1k Cr)</span>
          <span class="flex items-center gap-1.5"><span class="w-3 h-1 bg-indigo-400 rounded"></span> Cum. Net (+₹7.7k Cr)</span>
        </div>
      </div>

      <div class="w-full overflow-x-auto custom-scrollbar relative">
        <div id="cumulativeChartWrapper" class="min-w-[700px] h-[280px] relative">
          <svg id="cumulativeSvg" class="w-full h-full"></svg>
        </div>
      </div>
    </div>

    <!-- Two Column Breakdown: Participant Derivatives Matrix & Stock Accumulation -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">

      <!-- Participant Derivatives Breakdown Matrix -->
      <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between">
        <div>
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-bold text-white flex items-center gap-2">
              <span>🎯 Participant Derivatives Stance (OI)</span>
            </h2>
            <span class="text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-400">F&O SEGMENT</span>
          </div>
          <p class="text-xs text-slate-400 mb-6">
            Index Futures positioning, Long-to-Short ratios, and directional sentiment across all 4 major market participant groups.
          </p>

          <div class="space-y-4" id="participantCards"></div>
        </div>

        <div class="mt-6 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300/90">
          <span class="font-bold">💡 Quantitative Contrarian Signal:</span> FII Index Futures Long % is currently at <strong>11.0%</strong> (Net -276,250 contracts), while Retail is at <strong>84.3% Long</strong>. In quantitative history, FII Long % under 15% represents extreme short crowding and typically precedes aggressive mean-reversion short-covering rallies.
        </div>
      </div>

      <!-- Top Stock-Level Institutional Accumulation vs Distribution -->
      <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between">
        <div>
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-bold text-white flex items-center gap-2">
              <span>🏢 Equity Accumulation vs Distribution Leaders</span>
            </h2>
            <div class="flex gap-1 bg-slate-800 p-1 rounded-lg text-xs">
              <button id="tabInflows" class="px-3 py-1 font-semibold rounded-md bg-emerald-500 text-white transition-all">Top Inflows</button>
              <button id="tabOutflows" class="px-3 py-1 font-semibold rounded-md text-slate-400 hover:text-white transition-all">Top Outflows</button>
            </div>
          </div>
          <p class="text-xs text-slate-400 mb-4" id="stockTabSubtitle">
            Large-cap & mid-cap equities experiencing maximum institutional accumulation score & fund additions.
          </p>

          <div class="overflow-x-auto custom-scrollbar">
            <table class="w-full text-left text-xs border-collapse">
              <thead>
                <tr class="border-b border-slate-800 text-slate-400 font-semibold">
                  <th class="pb-2">Ticker / Company</th>
                  <th class="pb-2 text-right">Net Flow</th>
                  <th class="pb-2 text-right">Inst. Addition</th>
                  <th class="pb-2 text-right">Score</th>
                  <th class="pb-2 text-right">FII / DII Stake</th>
                </tr>
              </thead>
              <tbody id="stockTableBody" class="divide-y divide-slate-800/60"></tbody>
            </table>
          </div>
        </div>

        <div class="mt-4 text-right">
          <span class="text-[11px] text-slate-500">Point-in-Time Institutional Database Filings</span>
        </div>
      </div>

    </div>

  </div>
</div>

<script>
  const rawData = __DATA_JSON__;
  let currentStockTab = 'inflows';

  function init() {
    renderDivergenceChart();
    renderCumulativeChart();
    renderParticipants();
    renderStockTable();

    document.getElementById('timeframeSelect').addEventListener('change', () => {
      renderDivergenceChart();
      renderCumulativeChart();
    });

    document.getElementById('tabInflows').addEventListener('click', () => switchStockTab('inflows'));
    document.getElementById('tabOutflows').addEventListener('click', () => switchStockTab('outflows'));
  }

  function renderDivergenceChart() {
    const limit = parseInt(document.getElementById('timeframeSelect').value, 10);
    const flows = rawData.flows.slice(-limit);
    const svg = document.getElementById('divergenceSvg');
    const wrapper = document.getElementById('divergenceChartWrapper');
    const width = wrapper.clientWidth || 800;
    const height = 320;
    const padding = { top: 25, right: 30, bottom: 40, left: 65 };

    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    let maxVal = 0;
    flows.forEach(d => {
      maxVal = Math.max(maxVal, Math.abs(d.fii), Math.abs(d.dii), Math.abs(d.net));
    });
    maxVal = Math.ceil(maxVal * 1.15);

    const zeroY = padding.top + (chartH / 2);
    const scaleY = (val) => zeroY - (val / maxVal) * (chartH / 2);
    const barSlot = chartW / flows.length;
    const barWidth = Math.min(barSlot * 0.38, 14);

    let svgHtml = `
      <line x1="${padding.left}" y1="${zeroY}" x2="${width - padding.right}" y2="${zeroY}" stroke="#475569" stroke-width="1.5" />
      <line x1="${padding.left}" y1="${scaleY(maxVal * 0.5)}" x2="${width - padding.right}" y2="${scaleY(maxVal * 0.5)}" stroke="#1e293b" stroke-dasharray="3,3" />
      <line x1="${padding.left}" y1="${scaleY(-maxVal * 0.5)}" x2="${width - padding.right}" y2="${scaleY(-maxVal * 0.5)}" stroke="#1e293b" stroke-dasharray="3,3" />

      <text x="${padding.left - 10}" y="${scaleY(maxVal * 0.75)}" fill="#64748b" font-size="10" text-anchor="end">+₹${Math.round(maxVal * 0.75)}</text>
      <text x="${padding.left - 10}" y="${zeroY + 4}" fill="#94a3b8" font-size="10" text-anchor="end">0</text>
      <text x="${padding.left - 10}" y="${scaleY(-maxVal * 0.75)}" fill="#64748b" font-size="10" text-anchor="end">-₹${Math.round(maxVal * 0.75)}</text>
    `;

    flows.forEach((d, i) => {
      const cx = padding.left + i * barSlot + barSlot / 2;
      const diiH = Math.abs(scaleY(d.dii) - zeroY);
      const diiY = d.dii >= 0 ? scaleY(d.dii) : zeroY;

      const fiiH = Math.abs(scaleY(d.fii) - zeroY);
      const fiiY = d.fii >= 0 ? scaleY(d.fii) : zeroY;

      const netY = scaleY(d.net);
      const diiBarX = cx - barWidth - 1;
      const fiiBarX = cx + 1;

      svgHtml += `
        <g class="bar-group cursor-pointer"
           data-date="${d.date}" data-label="${d.label}" data-fii="${d.fii}" data-dii="${d.dii}" data-net="${d.net}" data-stance="${d.stance}">
          <rect x="${cx - barSlot/2 + 1}" y="${padding.top}" width="${barSlot - 2}" height="${chartH}" fill="white" opacity="0" class="hover:opacity-5 transition-opacity" />
          <rect x="${diiBarX}" y="${diiY}" width="${barWidth}" height="${Math.max(diiH, 2)}" rx="3" fill="#10b981" fill-opacity="0.9" />
          <rect x="${fiiBarX}" y="${fiiY}" width="${barWidth}" height="${Math.max(fiiH, 2)}" rx="3" fill="#f43f5e" fill-opacity="0.9" />
          <circle cx="${cx}" cy="${netY}" r="3.5" fill="#818cf8" stroke="#1e1b4b" stroke-width="1.5" />
          ${i % Math.ceil(flows.length / 10) === 0 ? `
            <text x="${cx}" y="${height - padding.bottom + 16}" fill="#64748b" font-size="9" text-anchor="middle">${d.label.split(' ')[0]} ${d.label.split(' ')[1] || ''}</text>
          ` : ''}
        </g>
      `;
    });

    svg.innerHTML = svgHtml;

    svg.querySelectorAll('.bar-group').forEach(el => {
      el.addEventListener('mouseenter', (e) => {
        showTooltip(
          e,
          el.getAttribute('data-date'),
          el.getAttribute('data-label'),
          parseFloat(el.getAttribute('data-fii')),
          parseFloat(el.getAttribute('data-dii')),
          parseFloat(el.getAttribute('data-net')),
          el.getAttribute('data-stance')
        );
      });
      el.addEventListener('mouseleave', hideTooltip);
    });
  }

  function renderCumulativeChart() {
    const limit = parseInt(document.getElementById('timeframeSelect').value, 10);
    const flows = rawData.flows.slice(-limit);
    const svg = document.getElementById('cumulativeSvg');
    const wrapper = document.getElementById('cumulativeChartWrapper');
    const width = wrapper.clientWidth || 800;
    const height = 280;
    const padding = { top: 25, right: 30, bottom: 40, left: 65 };

    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    let minVal = 0, maxVal = 0;
    flows.forEach(d => {
      minVal = Math.min(minVal, d.cum_fii, d.cum_dii, d.cum_net);
      maxVal = Math.max(maxVal, d.cum_fii, d.cum_dii, d.cum_net);
    });
    maxVal = Math.ceil(maxVal * 1.15);
    minVal = Math.floor(minVal * 1.15);

    const scaleY = (val) => padding.top + chartH - ((val - minVal) / (maxVal - minVal)) * chartH;
    const scaleX = (idx) => padding.left + (idx / (flows.length - 1)) * chartW;
    const zeroY = scaleY(0);

    let diiPath = '', fiiPath = '', netPath = '';
    flows.forEach((d, i) => {
      const x = scaleX(i);
      const yDii = scaleY(d.cum_dii);
      const yFii = scaleY(d.cum_fii);
      const yNet = scaleY(d.cum_net);

      if (i === 0) {
        diiPath = `M ${x} ${yDii}`;
        fiiPath = `M ${x} ${yFii}`;
        netPath = `M ${x} ${yNet}`;
      } else {
        diiPath += ` L ${x} ${yDii}`;
        fiiPath += ` L ${x} ${yFii}`;
        netPath += ` L ${x} ${yNet}`;
      }
    });

    let svgHtml = `
      <line x1="${padding.left}" y1="${zeroY}" x2="${width - padding.right}" y2="${zeroY}" stroke="#475569" stroke-width="1.2" stroke-dasharray="4,4" />
      <text x="${padding.left - 10}" y="${scaleY(maxVal * 0.8)}" fill="#10b981" font-size="10" text-anchor="end">+₹${Math.round(maxVal * 0.8)}</text>
      <text x="${padding.left - 10}" y="${zeroY + 4}" fill="#94a3b8" font-size="10" text-anchor="end">0</text>
      <text x="${padding.left - 10}" y="${scaleY(minVal * 0.8)}" fill="#f43f5e" font-size="10" text-anchor="end">-₹${Math.abs(Math.round(minVal * 0.8))}</text>

      <path d="${diiPath}" fill="none" stroke="#10b981" stroke-width="2.5" />
      <path d="${fiiPath}" fill="none" stroke="#f43f5e" stroke-width="2.5" />
      <path d="${netPath}" fill="none" stroke="#818cf8" stroke-width="2" stroke-dasharray="3,3" />
    `;

    flows.forEach((d, i) => {
      const x = scaleX(i);
      svgHtml += `
        <circle cx="${x}" cy="${scaleY(d.cum_dii)}" r="3" fill="#10b981" />
        <circle cx="${x}" cy="${scaleY(d.cum_fii)}" r="3" fill="#f43f5e" />
        <circle cx="${x}" cy="${scaleY(d.cum_net)}" r="2.5" fill="#818cf8" />
        ${i % Math.ceil(flows.length / 8) === 0 ? `
          <text x="${x}" y="${height - padding.bottom + 16}" fill="#64748b" font-size="9" text-anchor="middle">${d.label.split(' ')[0]} ${d.label.split(' ')[1] || ''}</text>
        ` : ''}
      `;
    });

    svg.innerHTML = svgHtml;
  }

  function renderParticipants() {
    const container = document.getElementById('participantCards');
    container.innerHTML = rawData.participants.map(p => {
      const isFII = p.id === 'FII';
      const isBullish = p.idx_long_pct >= 50;
      const color = isFII ? 'text-rose-400' : (p.id === 'DII' ? 'text-emerald-400' : (p.id === 'PRO' ? 'text-cyan-400' : 'text-indigo-400'));
      const bgBadge = isBullish ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20';

      return `
        <div class="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-slate-700 transition-all">
          <div class="flex items-center justify-between">
            <span class="font-bold ${color}">${p.label}</span>
            <span class="px-2 py-0.5 rounded text-[11px] font-semibold border ${bgBadge}">${p.idx_long_pct}% Long</span>
          </div>

          <div class="grid grid-cols-3 gap-2 mt-3 text-[11px]">
            <div>
              <span class="text-slate-500 block">Index Fut Net</span>
              <span class="font-mono font-bold ${p.idx_fut_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
                ${p.idx_fut_net > 0 ? '+' : ''}${p.idx_fut_net.toLocaleString()}
              </span>
            </div>
            <div>
              <span class="text-slate-500 block">Stock Fut Net</span>
              <span class="font-mono font-bold ${p.stk_fut_net >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
                ${p.stk_fut_net > 0 ? '+' : ''}${p.stk_fut_net.toLocaleString()}
              </span>
            </div>
            <div>
              <span class="text-slate-500 block">Call vs Put Net</span>
              <span class="font-mono font-bold ${p.idx_calls_net >= p.idx_puts_net ? 'text-emerald-400' : 'text-rose-400'}">
                ${p.idx_calls_net >= p.idx_puts_net ? 'Long Calls' : 'Put Hedge'}
              </span>
            </div>
          </div>

          <div class="mt-2.5 flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-800/60 pt-2">
            <span>Stance:</span>
            <span class="font-medium text-slate-300">${p.stance}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function switchStockTab(tab) {
    currentStockTab = tab;
    const tabInflows = document.getElementById('tabInflows');
    const tabOutflows = document.getElementById('tabOutflows');
    const subtitle = document.getElementById('stockTabSubtitle');

    if (tab === 'inflows') {
      tabInflows.className = 'px-3 py-1 font-semibold rounded-md bg-emerald-500 text-white transition-all';
      tabOutflows.className = 'px-3 py-1 font-semibold rounded-md text-slate-400 hover:text-white transition-all';
      subtitle.innerText = 'Large-cap & mid-cap equities experiencing maximum institutional accumulation score & fund additions.';
    } else {
      tabOutflows.className = 'px-3 py-1 font-semibold rounded-md bg-rose-500 text-white transition-all';
      tabInflows.className = 'px-3 py-1 font-semibold rounded-md text-slate-400 hover:text-white transition-all';
      subtitle.innerText = 'Equities facing institutional trimming or profit-taking across recent quarters.';
    }
    renderStockTable();
  }

  function renderStockTable() {
    const items = currentStockTab === 'inflows' ? rawData.top_inflows : rawData.top_outflows;
    const tbody = document.getElementById('stockTableBody');

    tbody.innerHTML = items.map(s => {
      const isPos = s.net_flow >= 0;
      return `
        <tr class="hover:bg-slate-800/40 transition-colors">
          <td class="py-2.5 font-medium text-white">
            <div class="flex items-center gap-1.5">
              <span class="font-bold font-mono text-indigo-400">${s.ticker}</span>
            </div>
            <div class="text-[11px] text-slate-400 truncate max-w-[140px]">${s.name}</div>
          </td>
          <td class="py-2.5 text-right font-mono font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}">
            ${isPos ? '+₹' : '-₹'}${Math.abs(s.net_flow).toLocaleString()} Cr
          </td>
          <td class="py-2.5 text-right font-mono text-slate-300">
            +${s.addition_pct}%
          </td>
          <td class="py-2.5 text-right">
            <span class="px-2 py-0.5 rounded font-mono font-bold ${s.score >= 70 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-800 text-slate-300'}">
              ${s.score}
            </span>
          </td>
          <td class="py-2.5 text-right text-[11px] text-slate-400">
            <span class="text-rose-400 font-mono">${s.fii}%</span> / <span class="text-emerald-400 font-mono">${s.dii}%</span>
          </td>
        </tr>
      `;
    }).join('');
  }

  function showTooltip(e, date, label, fii, dii, net, stance) {
    const tt = document.getElementById('chartTooltip');
    const isNetPos = net >= 0;
    tt.innerHTML = `
      <div class="font-bold text-white border-b border-slate-700 pb-1.5 mb-1.5 flex justify-between gap-3">
        <span>${label}</span>
        <span class="text-slate-400 font-normal">${date}</span>
      </div>
      <div class="space-y-1">
        <div class="flex justify-between gap-4">
          <span class="text-emerald-400">DII Net Buy:</span>
          <span class="font-mono font-bold text-white">+₹${dii.toFixed(1)} Cr</span>
        </div>
        <div class="flex justify-between gap-4">
          <span class="text-rose-400">FII Net Sell:</span>
          <span class="font-mono font-bold text-white">${fii.toFixed(1)} Cr</span>
        </div>
        <div class="flex justify-between gap-4 border-t border-slate-800 pt-1">
          <span class="text-indigo-400 font-bold">Net Absorption:</span>
          <span class="font-mono font-bold ${isNetPos ? 'text-emerald-400' : 'text-rose-400'}">
            ${isNetPos ? '+' : ''}₹${net.toFixed(1)} Cr
          </span>
        </div>
        <div class="text-[10px] text-slate-400 pt-1 italic">${stance}</div>
      </div>
    `;
    tt.style.opacity = '1';
    const rect = e.currentTarget.getBoundingClientRect();
    const parentRect = document.getElementById('divergenceChartWrapper').getBoundingClientRect();
    tt.style.left = Math.max(10, Math.min(parentRect.width - 220, rect.left - parentRect.left + 20)) + 'px';
    tt.style.top = '40px';
  }

  function hideTooltip() {
    const tt = document.getElementById('chartTooltip');
    tt.style.opacity = '0';
  }

  window.addEventListener('DOMContentLoaded', init);
  window.addEventListener('resize', () => {
    renderDivergenceChart();
    renderCumulativeChart();
  });
</script>
"""

final_html = html_template.replace("__DATA_JSON__", json.dumps(data))

with open("institutional_flow_divergence.html", "w", encoding="utf-8") as out:
    out.write(final_html)

print("Generated institutional_flow_divergence.html successfully.")
