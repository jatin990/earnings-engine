/* ResultsLedger — Corporate Earnings Calendar. Institutional Monochrome (Ink/Pearl/Emerald/Rose). */
const PRESET_MAP = {
  next3:  { past: 0,   ahead: 3  },
  next7:  { past: 0,   ahead: 7  },
  recent: { past: 4,   ahead: 7  },
  pm30:   { past: 30,  ahead: 30 },
  pm60:   { past: 60,  ahead: 60 },
  next14: { past: 0,   ahead: 14 },
  next30: { past: 0,   ahead: 30 },
  past60: { past: 60,  ahead: 0  },
  custom: null,
};

/* ─── Module singleton ──────────────────────────────────────────────────── */
const ResultsLedger = (() => {
  /* State */
  let _app = null;
  let _abortCtrl = null;
  let _state = {
    daySectionsMeta: [], months: [], activeMonth: 'ALL',
    selectedDates: new Set(), capFilter: 'all', densityMode: 'compact',
    excludedIndustries: new Set(), allIndustries: [], industrySearchQuery: '',
    searchQuery: '', totalStocks: 0, activeWindowName: '', activePreset: 'next3',
  };

  const _esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const _el = id => document.getElementById(id);
  function _toast(msg, type = 'info') {
    if (window.showToast) { window.showToast(msg, type); return; }
    alert(msg);
  }

  function _setBtn(id, loading, label) {
    const btn = _el(id);
    if (!btn) return;
    btn.disabled = loading;
    btn.textContent = label;
  }

  /** Initialise module, bind slider events. Called once per tab activation. */
  function init(app) {
    _app = app;
    _syncSliderBadge();
    document.addEventListener('click', _onDocClick);
    _setupSliderInteraction();
  }
  function destroy() { document.removeEventListener('click', _onDocClick); }

  function _setupSliderInteraction() {
    const sliderBox = document.querySelector('.rl-range-slider');
    const pastInput = _el('rl-slider-past');
    const aheadInput = _el('rl-slider-ahead');
    if (!sliderBox || !pastInput || !aheadInput) return;

    function _arbitrateZIndex(e) {
      const rect = sliderBox.getBoundingClientRect();
      if (!rect.width) return;
      const xPct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const pastVal = parseFloat(pastInput.value) || 0;
      const pastMax = parseFloat(pastInput.max) || 180;
      const aheadVal = parseFloat(aheadInput.value) || 1;
      const aheadMax = parseFloat(aheadInput.max) || 90;
      const pastPct = pastVal / pastMax;
      const aheadPct = aheadVal / aheadMax;
      if (Math.abs(xPct - pastPct) < Math.abs(xPct - aheadPct)) {
        pastInput.style.zIndex = '10';
        aheadInput.style.zIndex = '2';
      } else {
        aheadInput.style.zIndex = '10';
        pastInput.style.zIndex = '2';
      }
    }

    sliderBox.addEventListener('pointermove', _arbitrateZIndex);
    sliderBox.addEventListener('pointerdown', _arbitrateZIndex);
    pastInput.addEventListener('focus', () => { pastInput.style.zIndex = '10'; aheadInput.style.zIndex = '2'; });
    aheadInput.addEventListener('focus', () => { aheadInput.style.zIndex = '10'; pastInput.style.zIndex = '2'; });
  }

  function _onDocClick(e) {
    const panel = _el('resultsIndustryDropdownPanel');
    const btn   = _el('resultsIndustryDropdownBtn');
    if (panel && panel.style.display !== 'none' && !panel.contains(e.target) && e.target !== btn) {
      panel.style.display = 'none';
    }
  }

  /* ── Slider / preset ────────────────────────────────────────────────────*/
  function getSliderValues() {
    const past  = parseInt(_el('rl-slider-past')?.value  ?? '0', 10);
    const ahead = parseInt(_el('rl-slider-ahead')?.value ?? '3', 10);
    return { pastDays: past, aheadDays: ahead };
  }

  function onSliderInput() {
    _state.activePreset = 'custom';
    _highlightPresetChip('custom');
    _syncSliderBadge();
  }

  function onMarketChange() { /* market dropdown handled natively */ }
  function setPreset(key) {
    const p = PRESET_MAP[key];
    if (!p) return;
    const ps = _el('rl-slider-past');
    const as = _el('rl-slider-ahead');
    if (ps) ps.value = p.past;
    if (as) as.value = p.ahead;
    _state.activePreset = key;
    _highlightPresetChip(key);
    _syncSliderBadge();
  }

  function _highlightPresetChip(key) {
    document.querySelectorAll('.rl-preset-chip').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.preset === key);
    });
  }

  function _syncSliderBadge() {
    const { pastDays, aheadDays } = getSliderValues();
    const badge = _el('rl-slider-badge');
    if (badge) badge.textContent = `Past ${pastDays}D · Ahead ${aheadDays}D`;
  }

  async function loadReport() {
    if (_abortCtrl) { _abortCtrl.abort(); }
    _abortCtrl = new AbortController();
    const { pastDays, aheadDays } = getSliderValues();
    const market = _el('resultsMarket')?.value ?? 'ALL';
    const params = new URLSearchParams({ days: aheadDays, past_days: pastDays, market });
    const url = `/api/v1/dashboard/results/report?${params}`;
    const loadBtn   = _el('resultsLoadBtn');
    const cancelBtn = _el('resultsCancelBtn');
    const sections  = _el('resultsReportSections');
    if (loadBtn)   loadBtn.style.display   = 'none';
    if (cancelBtn) cancelBtn.style.display = 'inline-flex';
    if (sections)  sections.innerHTML = '<div style="padding:1.5rem;text-align:center;color:#525a6b;font-size:0.75rem;">Loading results…</div>';
    _setStatus('');
    try {
      const res = await fetch(url, { signal: _abortCtrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      _processApiResponse(data);
    } catch (err) {
      if (err.name === 'AbortError') { _setStatus('Load cancelled.'); }
      else { _setStatus(`Error: ${err.message}`); _toast('Failed to load results report.', 'error'); }
      if (sections) sections.innerHTML = '<div style="padding:1.5rem;text-align:center;color:#525a6b;font-size:0.75rem;">Load failed or cancelled.</div>';
    } finally {
      if (loadBtn)   loadBtn.style.display   = 'inline-flex';
      if (cancelBtn) cancelBtn.style.display = 'none';
      _abortCtrl = null;
    }
  }

  function cancel() { if (_abortCtrl) _abortCtrl.abort(); }
  /* ── Response processing ────────────────────────────────────────────────*/
  function _processApiResponse(data) {
    let sections = Array.isArray(data.sections) ? data.sections : [];

    // Defensive fallback: Parse day_sections_list if sections array was omitted by a legacy response
    if (!sections.length && Array.isArray(data.day_sections_list) && data.day_sections_list.length > 0) {
      try {
        const parser = new DOMParser();
        sections = data.day_sections_list.map((htmlStr, idx) => {
          const doc = parser.parseFromString(htmlStr, 'text/html');
          const groupEl = doc.querySelector('.day-group');
          const date = groupEl?.getAttribute('data-date') || (data.day_sections_meta?.[idx]?.date) || '';
          const meta = (data.day_sections_meta || []).find(m => m.date === date) || {};
          const rowEls = doc.querySelectorAll('tr.results-row');
          const stocks = Array.from(rowEls).map(tr => ({
            ticker: tr.getAttribute('data-ticker') || '',
            industry: tr.getAttribute('data-industry') || '',
            cap_tier: tr.getAttribute('data-cap') || '',
            row_html: tr.outerHTML,
          }));
          return {
            date: date,
            day_label: meta.day_label || date,
            day_relative: meta.day_relative || '',
            stocks: stocks,
          };
        }).filter(s => s.stocks.length > 0);
      } catch (err) {
        console.warn('[RESULTS-LEDGER] Fallback day_sections parsing error:', err);
      }
    }

    _state.daySectionsMeta = [];
    _state.months = data.months || [];
    _state.totalStocks = 0;
    _state.activeMonth = 'ALL';
    _state.selectedDates = new Set();
    _state.allIndustries = [];
    const industrySet = new Set();
    sections.forEach(sec => {
      sec.stocks?.forEach(s => { if (s.industry) industrySet.add(s.industry); });
    });
    _state.allIndustries = [...industrySet].sort();
    _state.excludedIndustries = new Set();
    renderTable(sections);
    renderMonthStrip();
    renderDateChipRail();
    _buildIndustryCheckboxList();
    _updateCountBadge();
    filterTable();
    _setStatus(`Loaded ${_state.totalStocks} result${_state.totalStocks !== 1 ? 's' : ''} across ${sections.length} date${sections.length !== 1 ? 's' : ''}.`);
  }

  /* ── Table render ───────────────────────────────────────────────────────*/
  function renderTable(sections) {
    const container = _el('resultsReportSections');
    if (!container) return;
    if (!sections?.length) {
      container.innerHTML = '<div style="padding:2rem;text-align:center;color:#525a6b;font-size:0.75rem;">No results in this window.</div>';
      return;
    }
    let totalStocks = 0;
    let rowRangeCursor = 0;
    const rows = [];
    rows.push(`<table class="results-table" style="width:100%;border-collapse:collapse;table-layout:auto;">
      <thead>
        <tr style="background:#000;position:sticky;top:0;z-index:10;">
          <th style="${_thStyle()}text-align:left;min-width:140px;">TICKER</th><th style="${_thStyle()}">DATE</th><th style="${_thStyle()}text-align:center;">SIGNAL</th><th style="${_thStyle()}">PRICE / CAP</th><th style="${_thStyle()}">EPS EST</th><th style="${_thStyle()}">BEAT RATE</th><th style="${_thStyle()}text-align:center;">SURPRISE %</th><th style="${_thStyle()}">RETURNS</th><th style="${_thStyle()}text-align:center;">AI EDGE</th><th style="${_thStyle()}">SETUP</th><th style="${_thStyle()}">S/R RANGE</th><th style="${_thStyle()}">52W</th><th style="${_thStyle()}text-align:center;">REL VOL</th>
        </tr>
      </thead>
      <tbody id="rl-tbody">`);
    sections.forEach(sec => {
      const dateKey   = sec.date || '';
      const monthKey  = dateKey.substring(0, 7);
      const dayLabel  = sec.day_label || dateKey;
      const dayRel    = sec.day_relative || '';
      const stocks    = sec.stocks || [];
      const startRow  = rowRangeCursor;
      rows.push(`<tr class="rl-day-divider results-day-divider" data-date="${_esc(dateKey)}" data-month="${_esc(monthKey)}" data-row-start="${startRow}" data-count="${stocks.length}">
        <td colspan="13" class="rl-day-divider" style="padding:0.3rem 0.65rem;background:#000;border-top:1px solid rgba(255,255,255,0.07);">
          <div style="display:flex;align-items:center;gap:0.4rem;">
            <span style="font-size:0.66rem;font-weight:700;color:#94a3b8;font-family:var(--font-mono);">${_esc(dayLabel)}</span>
            ${dayRel ? `<span style="font-size:0.58rem;background:rgba(255,255,255,0.06);color:#f8fafc;padding:0.04rem 0.3rem;border-radius:3px;font-weight:600;">${_esc(dayRel)}</span>` : ''}
            <span style="font-size:0.6rem;color:#525a6b;">${stocks.length} result${stocks.length !== 1 ? 's' : ''}</span>
          </div>
        </td>
      </tr>`);
      stocks.forEach(stock => {
        rows.push(stock.row_html || '');
        rowRangeCursor++;
      });
      _state.daySectionsMeta.push({ date: dateKey, month_key: monthKey, stocks_count: stocks.length, startRow });
      totalStocks += stocks.length;
    });
    rows.push('</tbody></table>');
    container.innerHTML = rows.join('');
    _state.totalStocks = totalStocks;
  }

  function _thStyle() {
    return 'padding:0.35rem 0.5rem;font-size:0.6rem;font-weight:700;color:#6b7485;font-family:var(--font-mono);letter-spacing:0.06em;border-bottom:1px solid rgba(255,255,255,0.07);white-space:nowrap;';
  }

  /* ── Month strip ────────────────────────────────────────────────────────*/
  function renderMonthStrip() {
    const months = _state.months;
    const now = new Date();
    const thisMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const prevMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const nextMonthDate = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    const prevKey = `${prevMonthDate.getFullYear()}-${String(prevMonthDate.getMonth() + 1).padStart(2, '0')}`;
    const nextKey = `${nextMonthDate.getFullYear()}-${String(nextMonthDate.getMonth() + 1).padStart(2, '0')}`;
    const fmt = key => {
      if (!key) return '';
      const [y, m] = key.split('-');
      return new Date(+y, +m - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    };
    const countFor = key => {
      const m = months.find(x => x.month_key === key);
      return m ? m.stocks_count : null;
    };
    const setCell = (suffix, key, fmt_label) => {
      const countEl = _el(`rl-month-${suffix}-count`);
      const labelEl = _el(`rl-month-${suffix}-label`);
      const c = countFor(key);
      if (countEl) countEl.textContent = c !== null ? c : '—';
      if (labelEl) labelEl.textContent = fmt_label;
    };
    setCell('last', prevKey, fmt(prevKey));
    setCell('this', thisMonthKey, fmt(thisMonthKey));
    setCell('next', nextKey, fmt(nextKey));
  }

  /* ── Date chip rail ─────────────────────────────────────────────────────*/
  function renderDateChipRail() {
    const rail = _el('rl-date-chip-rail');
    if (!rail) return;
    const dates = _state.daySectionsMeta.map(d => d.date);
    if (!dates.length) { rail.style.display = 'none'; return; }
    let html = '<div style="display:flex;gap:0.25rem;align-items:center;">';
    html += `<button type="button" class="rl-preset-chip active" id="rl-date-chip-ALL"
      onclick="window.resultsLedger && window.resultsLedger.toggleDate('ALL', event)"
      style="font-size:0.6rem;padding:0.12rem 0.4rem;">All</button>`;
    dates.forEach(d => {
      const label = _fmtDateChip(d);
      html += `<button type="button" class="rl-preset-chip" id="rl-date-chip-${_esc(d)}"
        data-date="${_esc(d)}"
        onclick="window.resultsLedger && window.resultsLedger.toggleDate('${_esc(d)}', event)"
        style="font-size:0.6rem;padding:0.12rem 0.4rem;">${_esc(label)}</button>`;
    });
    html += '</div>';
    rail.innerHTML = html;
    rail.style.display = 'block';
  }

  function _fmtDateChip(iso) {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  /* ── Filter ─────────────────────────────────────────────────────────────*/
  function filterTable() {
    const q      = _state.searchQuery.toLowerCase();
    const cap    = _state.capFilter;
    const excl   = _state.excludedIndustries;
    const selDates = _state.selectedDates;
    const aMonth = _state.activeMonth;
    let visible = 0;
    const visibleDates = new Set();

    /* Hide/show stock rows */
    document.querySelectorAll('.results-row').forEach(row => {
      const date    = row.dataset.date || (row.closest('tr[data-date]') || _prevDivider(row))?.dataset?.date || '';
      const month   = date.substring(0, 7);
      const ticker  = (row.dataset.ticker || '').toLowerCase();
      const capTier = (row.dataset.cap    || '').toLowerCase();
      const industry= (row.dataset.industry || '').toLowerCase();
      const monthOk = aMonth === 'ALL' || month === aMonth;
      const dateOk  = !selDates.size || selDates.has(date);
      const capOk   = cap === 'all' || capTier === cap;
      const indOk   = !excl.size || !excl.has(row.dataset.industry || '');
      const searchOk= !q || ticker.includes(q) || industry.includes(q)
        || (row.querySelector('.stock-company-sub')?.textContent || '').toLowerCase().includes(q)
        || (row.dataset.setup || '').toLowerCase().includes(q)
        || (row.dataset.buySignal || '').toLowerCase().includes(q);
      const show = monthOk && dateOk && capOk && indOk && searchOk;
      row.style.display = show ? '' : 'none';
      if (show) {
        visible++;
        if (date) visibleDates.add(date);
      }
    });

    /* Hide/show day-divider rows: only show if date has visible rows and matches date/month filters */
    document.querySelectorAll('.results-day-divider').forEach(divRow => {
      const date  = divRow.dataset.date || '';
      const month = divRow.dataset.month || '';
      const monthOk = aMonth === 'ALL' || month === aMonth;
      const dateOk  = !selDates.size || selDates.has(date);
      divRow.style.display = (monthOk && dateOk && visibleDates.has(date)) ? '' : 'none';
    });

    _el('resultsFilterMatchCount') && (_el('resultsFilterMatchCount').textContent = visible || '');
    _updateCountBadge();
  }

  function _prevDivider(row) {
    let prev = row.previousElementSibling;
    while (prev) { if (prev.classList.contains('results-day-divider')) return prev; prev = prev.previousElementSibling; }
    return null;
  }

  /* ── Filter setters ─────────────────────────────────────────────────────*/
  function setMonth(key) {
    const now = new Date();
    const toKey = k => {
      const d = k === 'last' ? new Date(now.getFullYear(), now.getMonth() - 1, 1)
               : k === 'next' ? new Date(now.getFullYear(), now.getMonth() + 1, 1)
               : k === 'this' ? now : null;
      if (!d) return k;
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    };
    const resolved = (key === 'last' || key === 'this' || key === 'next') ? toKey(key) : key;
    _state.activeMonth = _state.activeMonth === resolved ? 'ALL' : resolved;
    document.querySelectorAll('.rl-month-cell').forEach(c => c.classList.remove('active'));
    if (_state.activeMonth !== 'ALL') {
      const map = { last: 'rl-month-last', this: 'rl-month-this', next: 'rl-month-next' };
      const cellId = map[key];
      if (cellId) _el(cellId)?.classList.add('active');
    }
    filterTable();
  }

  function toggleDate(date, _event) {
    if (date === 'ALL') {
      _state.selectedDates = new Set();
      document.querySelectorAll('[id^="rl-date-chip-"]').forEach(b => b.classList.remove('active'));
      _el('rl-date-chip-ALL')?.classList.add('active');
    } else {
      _el('rl-date-chip-ALL')?.classList.remove('active');
      if (_state.selectedDates.has(date)) {
        _state.selectedDates.delete(date);
        _el(`rl-date-chip-${date}`)?.classList.remove('active');
        if (!_state.selectedDates.size) _el('rl-date-chip-ALL')?.classList.add('active');
      } else {
        _state.selectedDates.add(date);
        _el(`rl-date-chip-${date}`)?.classList.add('active');
      }
    }
    filterTable();
  }

  function setCapFilter(tier) {
    _state.capFilter = tier;
    ['all', 'large', 'small'].forEach(t => {
      const btn = _el(`rl-cap-${t}`);
      if (!btn) return;
      btn.style.background = t === tier ? 'rgba(255,255,255,0.12)' : 'transparent';
      btn.style.color = t === tier ? '#f8fafc' : '#6b7485';
      btn.style.fontWeight = t === tier ? '700' : '400';
    });
    filterTable();
  }

  function setDensity(mode) {
    _state.densityMode = mode;
    ['compact', 'standard'].forEach(m => {
      const btn = _el(`rl-density-${m}`);
      if (!btn) return;
      btn.style.background = m === mode ? 'rgba(255,255,255,0.12)' : 'transparent';
      btn.style.color = m === mode ? '#f8fafc' : '#6b7485';
      btn.style.fontWeight = m === mode ? '700' : '400';
    });
    document.querySelectorAll('.results-row').forEach(r => {
      r.classList.toggle('density-standard', mode === 'standard');
    });
  }

  function onSearchInput(val) {
    _state.searchQuery = val;
    filterTable();
  }

  /* ── Industry filter ────────────────────────────────────────────────────*/
  function toggleIndustryDropdown(event) {
    event.stopPropagation();
    const panel = _el('resultsIndustryDropdownPanel');
    if (!panel) return;
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    if (panel.style.display === 'block') _el('resultsIndustrySearchInput')?.focus();
  }

  function _buildIndustryCheckboxList(filterQ) {
    const list = _el('resultsIndustryCheckboxList');
    if (!list) return;
    const q = (filterQ ?? _state.industrySearchQuery).toLowerCase();
    const industries = _state.allIndustries.filter(ind => !q || ind.toLowerCase().includes(q));
    list.innerHTML = industries.map(ind => {
      const checked = !_state.excludedIndustries.has(ind);
      return `<label style="display:flex;align-items:center;gap:0.3rem;cursor:pointer;padding:0.1rem 0.2rem;border-radius:2px;font-size:0.65rem;color:#94a3b8;font-family:var(--font-mono);" onmouseenter="this.style.background='rgba(255,255,255,0.04)'" onmouseleave="this.style.background='transparent'">
        <input type="checkbox" data-industry="${_esc(ind)}" ${checked ? 'checked' : ''}
          onchange="window.resultsLedger && window.resultsLedger.onIndustryCheckboxChange(this)" style="accent-color:#f8fafc;">
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(ind)}</span>
      </label>`;
    }).join('');
  }

  function filterIndustryList(q) {
    _state.industrySearchQuery = q;
    _buildIndustryCheckboxList(q);
  }

  function onIndustryCheckboxChange(cb) {
    const ind = cb.dataset.industry;
    if (cb.checked) { _state.excludedIndustries.delete(ind); }
    else            { _state.excludedIndustries.add(ind); }
    _updateIndustryBtn();
    filterTable();
  }

  function selectAllIndustries() {
    _state.excludedIndustries = new Set();
    _buildIndustryCheckboxList();
    _updateIndustryBtn();
    filterTable();
  }

  function clearAllIndustries() {
    _state.excludedIndustries = new Set(_state.allIndustries);
    _buildIndustryCheckboxList();
    _updateIndustryBtn();
    filterTable();
  }

  function _updateIndustryBtn() {
    const excl  = _state.excludedIndustries.size;
    const total = _state.allIndustries.length;
    const label = _el('resultsIndustryBtnLabel');
    const count = _el('resultsIndustrySelectedCount');
    const selected = total - excl;
    if (label) label.textContent = excl ? `Industries (${selected}/${total})` : 'Industries (All)';
    if (count) count.textContent = excl ? `${selected} selected` : 'All selected';
  }

  async function syncCalendar(btn) {
    const orig = btn?.textContent ?? '📅 Sync';
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Syncing…'; }
    try {
      const res = await fetch('/api/v1/dashboard/results/sync-calendar', { method: 'POST' });
      const d = await res.json();
      _toast(d.message || 'Calendar synced.', 'success');
      loadReport();
    } catch { _toast('Sync failed.', 'error'); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = orig; }
    }
  }

  async function recalcPrices(btn) {
    const orig = btn?.textContent ?? '⚡ Recalc';
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Recalculating…'; }
    try {
      const { pastDays, aheadDays } = getSliderValues();
      const res = await fetch(`/api/v1/dashboard/results/recalculate-prices?days=${aheadDays}&past_days=${pastDays}`, { method: 'POST' });
      const d = await res.json();
      _toast(d.message || 'Prices recalculated.', 'success');
      loadReport();
    } catch { _toast('Recalc failed.', 'error'); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = orig; }
    }
  }

  async function summarize(btn) {
    const orig = btn?.textContent ?? '✦ AI Summary';
    if (btn) { btn.disabled = true; btn.textContent = '✦ Summarizing…'; }
    try {
      const { pastDays, aheadDays } = getSliderValues();
      const res = await fetch(`/api/v1/dashboard/results/summarize?days=${aheadDays}&past_days=${pastDays}`);
      const d = await res.json();
      alert(d.summary || 'No summary available.');
    } catch { _toast('AI summary failed.', 'error'); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = orig; }
    }
  }

  function openDrawer(ticker) {
    if (_app?.openStockDrawer) _app.openStockDrawer(ticker);
  }

  function openMonthModal(slot) {
    if (_app?.openResultsMonthModal) _app.openResultsMonthModal(slot);
  }

  async function refreshSinglePrice(ticker, btn) {
    const orig = btn?.innerHTML ?? '↻';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span style="display:inline-block;animation:spin 0.8s linear infinite;">↻</span>';
    }
    try {
      const res = await fetch(`/api/v1/dashboard/results/refresh-price?ticker=${encodeURIComponent(ticker)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      if (d.metrics) {
        updateDomRowWithMetrics(ticker, d.metrics);
        if (btn) {
          btn.innerHTML = '✓';
          btn.style.color = '#34d399';
          setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = orig;
            btn.style.color = '';
          }, 1200);
        }
        _toast(`Refreshed quote for ${ticker}`, 'info');
      }
    } catch (err) {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
      _toast(`Refresh failed for ${ticker}: ${err.message}`, 'error');
    }
  }

  function updateDomRowWithMetrics(ticker, metrics) {
    const row = document.querySelector(`.results-row[data-ticker="${_esc(ticker)}"]`);
    if (!row) return;
    if (metrics.current_price != null) {
      const priceEl = row.querySelector('.price-val') ||
                      row.querySelector('.cell-current-price div > div > span:not(.live-pulse-dot)') ||
                      row.querySelector('.cell-current-price span:first-of-type');
      if (priceEl) priceEl.textContent = metrics.current_price;
      if (metrics.raw_price != null) row.dataset.price = String(metrics.raw_price);
    }
    if (metrics.market_cap != null) {
      const mcapEl = row.querySelector('.mcap-val') ||
                     row.querySelector('.cell-current-price > div > span:last-child');
      if (mcapEl) mcapEl.textContent = metrics.market_cap;
      if (metrics.raw_mcap != null) row.dataset.mcap = String(metrics.raw_mcap);
    }
  }

  function exportCsv() {
    const rows = _visibleRows();
    const cols = ['ticker', 'date', 'signal', 'buy_score', 'cap', 'industry', 'price', 'mcap', '3d', '7d', '30d', 'rel_vol', 'beat_rate'];
    const lines = [cols.join(',')];
    rows.forEach(r => {
      lines.push([
        r.dataset.ticker || '', r.dataset.date || '', r.dataset.buySignal || '', r.dataset.buyScore || '',
        r.dataset.cap || '', r.dataset.industry || '',
        r.dataset.price || '', r.dataset.mcap || '',
        r.dataset['3dRet'] || '', r.dataset['7dRet'] || '', r.dataset['30dRet'] || '',
        r.dataset.relVol || '', r.dataset.beatRate || '',
      ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
    });
    _downloadText(lines.join('\n'), 'results_export.csv', 'text/csv');
  }

  function exportJson() {
    const rows = _visibleRows().map(r => ({
      ticker: r.dataset.ticker, date: r.dataset.date,
      signal: r.dataset.buySignal || null,
      buy_score: r.dataset.buyScore ? Number(r.dataset.buyScore) : null,
      cap: r.dataset.cap, industry: r.dataset.industry,
      price: r.dataset.price, mcap: r.dataset.mcap,
      ret_3d: r.dataset['3dRet'], ret_7d: r.dataset['7dRet'], ret_30d: r.dataset['30dRet'],
      rel_vol: r.dataset.relVol, beat_rate: r.dataset.beatRate,
    }));
    _downloadText(JSON.stringify(rows, null, 2), 'results_export.json', 'application/json');
  }

  function _visibleRows() {
    return [...document.querySelectorAll('.results-row')].filter(r => r.style.display !== 'none');
  }

  function _downloadText(text, name, mime) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: mime }));
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function _setStatus(msg) {
    const el = _el('resultsReportStatus');
    if (el) el.textContent = msg;
  }

  function _updateCountBadge() {
    const badge = _el('resultsCount');
    if (!badge) return;
    const vis = _visibleRows().length;
    const total = _state.totalStocks;
    if (!total) { badge.style.display = 'none'; return; }
    badge.textContent = vis < total ? `${vis} / ${total} results` : `${total} result${total !== 1 ? 's' : ''}`;
    badge.style.display = '';
  }

  return {
    init, destroy, loadReport, cancel, getSliderValues, onSliderInput, onMarketChange, setPreset,
    renderTable, renderMonthStrip, renderDateChipRail, filterTable, setMonth, toggleDate,
    setCapFilter, setDensity, onSearchInput, toggleIndustryDropdown, filterIndustryList,
    onIndustryCheckboxChange, selectAllIndustries, clearAllIndustries, syncCalendar,
    recalcPrices, summarize, openDrawer, openMonthModal, refreshSinglePrice,
    onMonthCellClick: setMonth,
    updateDomRowWithMetrics, exportCsv, exportJson,
  };
})();

window.resultsLedger = ResultsLedger;