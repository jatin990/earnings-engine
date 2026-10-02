/**
 * Zepto Store Management Hub — Frontend Controller Module
 * Handles Staffing Matrix, MoM Salary & Bonus Tracking, Expenses & Insights,
 * Candidate Pipeline Conversions, and ₹75L 50-50 Partner Capital Ledger.
 */

const ZEPTO_ALL_TABS = [
    'dashboard',
    'employees',
    'attendance',
    'utilization',
    'loss',
    'scorecard',
    'income',
    'expenses',
    'candidates',
    'offers',
    'security',
    'gmail',
];

const zeptoApp = {
    overview: null,
    dashboard: {
        analytics: null,
        dod_filtered: [],
    },
    employees: [],
    includeHiddenEmployees: false,
    empSortColumn: 'name',
    empSortDirection: 'asc',
    income: [],
    expenses: [],
    candidates: [],
    security: null,
    attendance: { summary: null, records: [], filtered: [], staff_roster: [], filtered_staff: [], roles: [] },
    gmail: {
        emails: [],
        filtered: [],
        hideSecurityAlerts: true,
        showHidden: false,
        hiddenEmailIds: new Set(JSON.parse(localStorage.getItem('zepto_hidden_email_ids') || '[]')),
    },
    currentGlobalMonth: 'ALL',
    availableMonths: [],
    activeTab: 'dashboard',
    currentEmpId: null,
    currentStaffDrawerEmpId: null,
    currentStaffDrawerMonth: null,

    async init() {
        // Hydrate partner dropdowns immediately with defaults
        this.populatePartnerDropdowns();
        this.populateDynamicMonthDropdowns();

        // Tab routing via hash
        const rawHash = (window.location.hash || '#dashboard').replace('#', '').split('?')[0];
        if (ZEPTO_ALL_TABS.includes(rawHash)) {
            this.activeTab = rawHash;
        } else {
            this.activeTab = 'dashboard';
        }
        this.switchTab(this.activeTab, false);

        // Listen for browser back/forward and anchor hash changes
        window.addEventListener('hashchange', () => {
            const newHash = (window.location.hash || '#dashboard').replace('#', '').split('?')[0];
            if (ZEPTO_ALL_TABS.includes(newHash)) {
                if (this.activeTab !== newHash) {
                    this.switchTab(newHash, false);
                }
            }
        });

        // Check for oauth callback status in URL query or hash
        const urlParams = new URLSearchParams(window.location.search || window.location.hash.split('?')[1] || '');
        if (urlParams.get('status') === 'connected') {
            this.showToast('✅ Gmail account successfully linked!');
        } else if (urlParams.get('error')) {
            this.showToast('⚠️ Gmail linking cancelled or failed: ' + urlParams.get('error'), true);
        }

        // Status change listener on employee modal
        const empStatusEl = document.getElementById('empFormStatus');
        if (empStatusEl) {
            empStatusEl.addEventListener('change', (e) => {
                const grp = document.getElementById('resignationReasonGroup');
                if (grp) grp.style.display = e.target.value === 'RESIGNED' ? 'block' : 'none';
            });
        }

        // Global Escape key listener for slide drawers and modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeEmployeeDrawer();
                this.closeStaffDrawer();
            }
        });

        await this.loadAll();
    },

    async loadAll() {
        await Promise.all([
            this.loadOverview(),
            this.loadOperationsDashboard(),
            this.loadEmployees(),
            this.loadAttendanceData(),
            this.loadUtilization(),
            this.loadLoss(),
            this.loadScorecard(),
            this.loadIncome(),
            this.loadExpenses(),
            this.loadCandidates(),
            this.loadSecurity(),
            this.checkGmailStatus(),
        ]);
    },

    // -----------------------------------------------------------------------
    // Navigation & Tabs
    // -----------------------------------------------------------------------

    switchTab(tabId, updateHash = true) {
        if (!ZEPTO_ALL_TABS.includes(tabId)) {
            tabId = 'dashboard';
        }
        this.activeTab = tabId;
        if (updateHash) {
            window.location.hash = tabId;
        }

        ZEPTO_ALL_TABS.forEach(t => {
            const btn = document.getElementById(`tabBtn-${t}`);
            const content = document.getElementById(`tabContent-${t}`);
            if (btn) {
                if (t === tabId) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
            if (content) {
                content.style.display = t === tabId ? 'block' : 'none';
            }
        });

        if (tabId === 'dashboard') this.loadOperationsDashboard();
        else if (tabId === 'employees') this.loadEmployees();
        else if (tabId === 'attendance') this.loadAttendanceData();
        else if (tabId === 'utilization') this.loadUtilization();
        else if (tabId === 'loss') this.loadLoss();
        else if (tabId === 'scorecard') this.loadScorecard();
        else if (tabId === 'income') this.loadIncome();
        else if (tabId === 'expenses') this.loadExpenses();
        else if (tabId === 'candidates') this.loadCandidates();
        else if (tabId === 'offers') this.initOfferLetterModule();
        else if (tabId === 'security') this.loadSecurity();
        else if (tabId === 'gmail') this.loadRecentEmails();
    },

    // -----------------------------------------------------------------------
    // Overview & Store KPIs
    // -----------------------------------------------------------------------

    async loadOverview() {
        try {
            const res = await fetch('/api/v1/zepto/overview');
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load store overview');

            this.overview = data;
            if (data.available_months && Array.isArray(data.available_months)) {
                this.updateAvailableMonths(data.available_months);
            }
            this.renderOverviewWidgets(data);
        } catch (err) {
            console.error('[ZEPTO] Error loading overview:', err);
        }
    },
        }
    },

    renderOverviewWidgets(data) {
        const hc = data.headcount || {};
        const exp = data.expenses || {};
        const cands = data.candidates || {};
        const sec = data.security_capital || {};

        // 1. Staff Headcount & Attrition
        const activeEl = document.getElementById('kpiActiveStaff');
        const targetTotal = hc.target_total || 15;
        const staffPct = hc.staffing_pct || Math.round(((hc.active || 0) / targetTotal) * 100);
        if (activeEl) activeEl.textContent = `${hc.active || 0} / ${targetTotal} Staff`;

        const attritionBadge = document.getElementById('kpiAttritionBadge');
        if (attritionBadge) {
            attritionBadge.textContent = `${staffPct}% Capacity`;
            attritionBadge.className = `text-[10px] font-extrabold px-2 py-0.5 rounded-full border ${
                staffPct >= 100 ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-purple-500/15 text-purple-200 border-purple-500/30 font-mono'
            }`;
        }

        const breakdownEl = document.getElementById('kpiStaffBreakdown');
        if (breakdownEl && hc.capacity) {
            const parts = [
                `Pickers: ${hc.capacity.PICKER?.current || 0}/${hc.capacity.PICKER?.target || 9}`,
                `Shift: ${hc.capacity.SHIFT_INCHARGE?.current || 0}/${hc.capacity.SHIFT_INCHARGE?.target || 3}`,
                `Guards: ${hc.capacity.SECURITY_GUARD?.current || 0}/${hc.capacity.SECURITY_GUARD?.target || 2}`,
                `HK: ${hc.capacity.HOUSEKEEPING?.current || 0}/${hc.capacity.HOUSEKEEPING?.target || 1}`,
            ];
            breakdownEl.textContent = parts.join(' · ');
        }

        const payrollEl = document.getElementById('kpiPayroll');
        if (payrollEl) payrollEl.textContent = this.formatCurrency(hc.monthly_payroll || 0);

        // Render Staffing Requirements Matrix on Employees Tab
        this.renderStaffingCapacity(hc);

        // 2. Total Store Expenses & Reimbursements
        const totalExpEl = document.getElementById('kpiTotalExpenses');
        if (totalExpEl) totalExpEl.textContent = this.formatCurrency(exp.total_expenses || 0);

        const pendingReimbEl = document.getElementById('kpiPendingReimbBadge');
        if (pendingReimbEl) {
            const pendAmt = exp.pending_reimbursement || 0;
            pendingReimbEl.textContent = `⏳ ${this.formatCurrency(pendAmt)} Pending`;
            if (pendAmt > 0) {
                pendingReimbEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono animate-pulse';
            } else {
                pendingReimbEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono';
                pendingReimbEl.textContent = '✅ All Reimbursed';
            }
        }

        const reimbSpendEl = document.getElementById('kpiReimbursedSpend');
        if (reimbSpendEl) reimbSpendEl.textContent = this.formatCurrency(exp.reimbursed_expenses || 0);

        const trainExpEl = document.getElementById('kpiTrainingSpend');
        if (trainExpEl) trainExpEl.textContent = this.formatCurrency(exp.training_expenses || 0);

        const spendPerEmpEl = document.getElementById('kpiSpendPerEmployee');
        if (spendPerEmpEl) spendPerEmpEl.textContent = `${this.formatCurrency(exp.spend_per_employee || 0)} / staff`;

        // 3. Candidate Pipeline
        const candCountEl = document.getElementById('kpiCandidatesCount');
        if (candCountEl) candCountEl.textContent = `${cands.active_pipeline || 0} Candidates`;

        const candRatingEl = document.getElementById('kpiAvgRating');
        if (candRatingEl) candRatingEl.textContent = `⭐ ${hc.avg_rating || 5.0} avg score`;

        // 4. ₹75L Security & 50-50 Partner Split
        const capPaidEl = document.getElementById('kpiCapitalPaid');
        if (capPaidEl) capPaidEl.textContent = `${this.formatCurrency(sec.total_deposited || 0)} / ₹75L`;

        const capBadge = document.getElementById('kpiCapitalProgressBadge');
        if (capBadge) {
            capBadge.textContent = `${sec.progress_pct || 0}% Funded`;
        }

        const p1Bar = document.getElementById('kpiPartner1Bar');
        const p2Bar = document.getElementById('kpiPartner2Bar');
        if (p1Bar && sec.partner_1) {
            const p1Width = Math.min(50, (sec.partner_1.paid / sec.target_total) * 100);
            p1Bar.style.width = `${p1Width}%`;
        }
        if (p2Bar && sec.partner_2) {
            const p2Width = Math.min(50, (sec.partner_2.paid / sec.target_total) * 100);
            p2Bar.style.width = `${p2Width}%`;
        }

        const remainingEl = document.getElementById('kpiRemainingCapital');
        if (remainingEl) remainingEl.textContent = `${this.formatCurrency(sec.remaining_pending || 0)} Pending`;

        const eqEl = document.getElementById('kpiEqualizationText');
        if (eqEl && sec.equalization) {
            eqEl.textContent = sec.equalization.status;
        }

        // Dynamically sync partner names and selectors from backend config
        if (data.config && data.config.partners) {
            this.populatePartnerDropdowns(data.config);
        } else if (sec.partner_1 && sec.partner_2) {
            this.populatePartnerDropdowns({
                partners: {
                    partner_1: sec.partner_1,
                    partner_2: sec.partner_2,
                }
            });
        }
    },

    populatePartnerDropdowns(config) {
        const p1 = (config && config.partners && config.partners.partner_1) || { name: 'Jatin Abrol', label: 'Jatin Abrol', initials: 'JA' };
        const p2 = (config && config.partners && config.partners.partner_2) || { name: 'Harshiv Bargotra', label: 'Harshiv Bargotra', initials: 'HB' };
        if (!p1 || !p2) return;

        // 1. Expense Incurred By Select
        const expIncurred = document.getElementById('expFormIncurred');
        if (expIncurred) {
            const curVal = expIncurred.value;
            expIncurred.innerHTML = `
                <option value="${p1.name}">${p1.label || p1.name}</option>
                <option value="${p2.name}">${p2.label || p2.name}</option>
                <option value="STORE_CASH">Store Cash</option>
            `;
            if (curVal) expIncurred.value = curVal;
        }

        // 2. Tranche Paid By Select
        const tranchePartner = document.getElementById('trancheFormPartner');
        if (tranchePartner) {
            const curVal = tranchePartner.value;
            tranchePartner.innerHTML = `
                <option value="${p1.name}">${p1.label || p1.name}</option>
                <option value="${p2.name}">${p2.label || p2.name}</option>
            `;
            if (curVal) tranchePartner.value = curVal;
        }

        // 3. Expense Payer Filter
        const expFilter = document.getElementById('expIncurredFilter');
        if (expFilter) {
            const curVal = expFilter.value;
            expFilter.innerHTML = `
                <option value="ALL">All Payers</option>
                <option value="${p1.name}">${p1.name}</option>
                <option value="${p2.name}">${p2.name}</option>
                <option value="STORE_CASH">Store Cash</option>
            `;
            if (curVal) expFilter.value = curVal;
        }

        // 4. Partner Cards Names and Badges
        const p1NameEl = document.getElementById('secPartner1Name');
        if (p1NameEl) p1NameEl.textContent = p1.label || p1.name;

        const p1InitEl = document.getElementById('secPartner1Initials');
        if (p1InitEl) p1InitEl.textContent = p1.initials || 'JA';

        const p2NameEl = document.getElementById('secPartner2Name');
        if (p2NameEl) p2NameEl.textContent = p2.label || p2.name;

        const p2InitEl = document.getElementById('secPartner2Initials');
        if (p2InitEl) p2InitEl.textContent = p2.initials || 'HB';

        const kpiP1Bar = document.getElementById('kpiPartner1Bar');
        if (kpiP1Bar) kpiP1Bar.title = p1.name;

        const kpiP2Bar = document.getElementById('kpiPartner2Bar');
        if (kpiP2Bar) kpiP2Bar.title = p2.name;
    },

    updateAvailableMonths(months) {
        if (!months || !Array.isArray(months)) return;
        const set = new Set([...this.availableMonths, ...months]);
        this.availableMonths = Array.from(set).filter(m => m && m.length === 7).sort().reverse();
        this.populateDynamicMonthDropdowns();
    },

    populateDynamicMonthDropdowns() {
        const now = new Date();
        const monthList = [...(this.availableMonths || [])];
        if (monthList.length === 0) {
            for (let i = 0; i < 12; i++) {
                const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
                monthList.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
            }
        }

        const formatMonthLabel = (ym) => {
            const [yr, mo] = ym.split('-');
            const d = new Date(parseInt(yr, 10), parseInt(mo, 10) - 1, 1);
            return d.toLocaleString('en-US', { month: 'long', year: 'numeric' });
        };

        // 1. Global Header Month Scope Selector
        const globalSelect = document.getElementById('globalMonthSelector');
        if (globalSelect) {
            const currentVal = globalSelect.value || this.currentGlobalMonth || 'ALL';
            let opts = '<option value="ALL" class="bg-slate-900 text-white">All Months</option>';
            monthList.forEach(ym => {
                opts += `<option value="${ym}" class="bg-slate-900 text-white">${formatMonthLabel(ym)} (${ym})</option>`;
            });
            globalSelect.innerHTML = opts;
            if (Array.from(globalSelect.options).some(o => o.value === currentVal)) {
                globalSelect.value = currentVal;
            }
            this.currentGlobalMonth = globalSelect.value;
        }

        // 2. Attendance Month Filter
        const attMonthSelect = document.getElementById('attMonthFilter');
        if (attMonthSelect) {
            const currentVal = attMonthSelect.value || this.currentGlobalMonth || 'ALL';
            let opts = '<option value="ALL">All Records</option>';
            monthList.forEach(ym => {
                opts += `<option value="${ym}">${formatMonthLabel(ym)} (${ym})</option>`;
            });
            attMonthSelect.innerHTML = opts;
            if (currentVal && Array.from(attMonthSelect.options).some(o => o.value === currentVal)) {
                attMonthSelect.value = currentVal;
            }
        }

        // 3. Gmail Month Filter
        const gmailMonthSelect = document.getElementById('gmailMonthFilter');
        if (gmailMonthSelect) {
            const currentVal = gmailMonthSelect.value || this.currentGlobalMonth || 'ALL';
            let opts = '<option value="ALL">All Months</option>';
            monthList.forEach(ym => {
                opts += `<option value="${ym}">${formatMonthLabel(ym)} (${ym})</option>`;
            });
            gmailMonthSelect.innerHTML = opts;
            if (currentVal && Array.from(gmailMonthSelect.options).some(o => o.value === currentVal)) {
                gmailMonthSelect.value = currentVal;
            }
        }

        // 4. Income Month Filter
        const incMonthSelect = document.getElementById('incMonthFilter');
        if (incMonthSelect) {
            const currentVal = incMonthSelect.value || this.currentGlobalMonth || 'ALL';
            let opts = '<option value="ALL">All Months</option>';
            monthList.forEach(ym => {
                opts += `<option value="${ym}">${formatMonthLabel(ym)} (${ym})</option>`;
            });
            incMonthSelect.innerHTML = opts;
            if (currentVal && Array.from(incMonthSelect.options).some(o => o.value === currentVal)) {
                incMonthSelect.value = currentVal;
            }
        }
    },

    onGlobalMonthChange(val) {
        this.currentGlobalMonth = val || 'ALL';

        // Synchronize labels and scope badges across all subtabs
        const scopeText = val === 'ALL' ? 'ALL' : val;
        const scopeFull = val === 'ALL' ? 'All Historical Months' : `Month: ${val}`;

        const dashScope = document.getElementById('dashActiveScopeBadge');
        if (dashScope) dashScope.textContent = scopeFull;

        const dashLabel = document.getElementById('dashSelectedMonthLabel');
        if (dashLabel) dashLabel.textContent = scopeText;

        const lossScope = document.getElementById('lossActiveScopeBadge');
        if (lossScope) lossScope.textContent = scopeText;

        const scScope = document.getElementById('scorecardActiveScopeBadge');
        if (scScope) scScope.textContent = scopeText;

        const utilScope = document.getElementById('utilActiveScopeBadge');
        if (utilScope) utilScope.textContent = scopeText;

        // Synchronize subtab dropdowns if they exist
        const attMonthSelect = document.getElementById('attMonthFilter');
        if (attMonthSelect && Array.from(attMonthSelect.options).some(o => o.value === val)) {
            attMonthSelect.value = val;
        }

        const gmailMonthSelect = document.getElementById('gmailMonthFilter');
        if (gmailMonthSelect && Array.from(gmailMonthSelect.options).some(o => o.value === val)) {
            gmailMonthSelect.value = val;
        }

        const incMonthSelect = document.getElementById('incMonthFilter');
        if (incMonthSelect && Array.from(incMonthSelect.options).some(o => o.value === val)) {
            incMonthSelect.value = val;
        }

        // Reload data for currently active tab
        if (this.activeTab === 'dashboard') this.loadOperationsDashboard();
        else if (this.activeTab === 'attendance') this.loadAttendanceData();
        else if (this.activeTab === 'loss') this.loadLoss();
        else if (this.activeTab === 'scorecard') this.loadScorecard();
        else if (this.activeTab === 'utilization') this.loadUtilization();
        else if (this.activeTab === 'income') this.loadIncome();
        else if (this.activeTab === 'expenses') this.loadExpenses();
        else if (this.activeTab === 'gmail') this.loadRecentEmails();
    },

    // -----------------------------------------------------------------------
    // Tab: Master Operations Dashboard (MoM & DoD Executive Ledger)
    // -----------------------------------------------------------------------

    async loadOperationsDashboard() {
        const month = this.currentGlobalMonth || 'ALL';
        const params = new URLSearchParams();
        if (month && month !== 'ALL') {
            params.append('month', month);
        }

        try {
            const res = await fetch(`/api/v1/zepto/operations/analytics?${params.toString()}`);
            if (!res.ok) throw new Error('Failed to load operational analytics');
            const data = await res.json();

            this.dashboard = this.dashboard || {};
            this.dashboard.analytics = data;
            this.dashboard.dod_filtered = data.dod_metrics || [];

            if (data.available_months && Array.isArray(data.available_months)) {
                this.updateAvailableMonths(data.available_months);
            }

            this.renderOperationsDashboard(data);
        } catch (err) {
            console.error('[ZEPTO-DASHBOARD] Error loading dashboard:', err);
        }
    },

    renderOperationsDashboard(data) {
        if (!data) return;

        const kpis = data.summary_kpis || {};
        const mom = data.mom_trends || [];
        const dod = this.dashboard?.dod_filtered || data.dod_metrics || [];
        const activeMonth = data.selected_month || this.currentGlobalMonth || 'ALL';

        // 1. Header Badges
        const scopeBadge = document.getElementById('dashActiveScopeBadge');
        if (scopeBadge) scopeBadge.textContent = activeMonth === 'ALL' ? 'All Historical Months' : `Month: ${activeMonth}`;
        const monthLabel = document.getElementById('dashSelectedMonthLabel');
        if (monthLabel) monthLabel.textContent = activeMonth;

        // 2. Executive KPI Cards
        const totalLossEl = document.getElementById('dashTotalLoss');
        if (totalLossEl) totalLossEl.textContent = this.formatCurrency(kpis.total_loss || 0);

        const lossIncidentsEl = document.getElementById('dashLossIncidents');
        if (lossIncidentsEl) {
            const incCount = kpis.total_loss_incidents || (dod.reduce((acc, d) => acc + (d.loss_incidents || 0), 0));
            lossIncidentsEl.textContent = `${incCount.toLocaleString('en-IN')} Incidents`;
        }

        const attBadge = document.getElementById('dashAttendanceBadge');
        if (attBadge) attBadge.textContent = `${(kpis.attendance_rate_pct || 0).toFixed(1)}% Rate`;

        const presentShiftsEl = document.getElementById('dashPresentShifts');
        if (presentShiftsEl) presentShiftsEl.textContent = `${kpis.total_present || 0} / ${kpis.total_shifts || 0}`;

        const absentShiftsEl = document.getElementById('dashAbsentShifts');
        if (absentShiftsEl) absentShiftsEl.textContent = `${kpis.total_absent || 0} Shifts`;

        const totalOrdersEl = document.getElementById('dashTotalOrders');
        if (totalOrdersEl) totalOrdersEl.textContent = (kpis.total_orders || 0).toLocaleString('en-IN');

        const totalGmvEl = document.getElementById('dashTotalGmv');
        if (totalGmvEl) totalGmvEl.textContent = this.formatCurrency(kpis.total_gmv || 0);

        const avgIppEl = document.getElementById('dashAvgIpp');
        if (avgIppEl) avgIppEl.textContent = `${kpis.avg_packer_ipp || 0} IPP`;

        const daysCountEl = document.getElementById('dashDaysCount');
        if (daysCountEl) daysCountEl.textContent = kpis.days_count || dod.length || 0;

        const daysBadge = document.getElementById('dashDaysCountBadge');
        if (daysBadge) daysBadge.textContent = `${kpis.days_count || dod.length || 0} Days`;

        // 3. Month-on-Month Table
        const momBadge = document.getElementById('dashMomMonthsBadge');
        if (momBadge) momBadge.textContent = `${mom.length} Months`;

        const momTbody = document.getElementById('dashMomTableBody');
        if (momTbody) {
            if (mom.length === 0) {
                momTbody.innerHTML = `<tr><td colspan="10" class="text-center py-6 text-slate-500 text-xs">No historical monthly data recorded.</td></tr>`;
            } else {
                momTbody.innerHTML = mom.map(m => {
                    const [yr, mo] = m.month_ym.split('-');
                    const dateObj = new Date(parseInt(yr, 10), parseInt(mo, 10) - 1, 1);
                    const label = dateObj.toLocaleString('en-US', { month: 'short', year: 'numeric' });
                    return `
                        <tr class="hover:bg-white/[0.02] transition">
                            <td class="py-2.5 px-3">
                                <div class="font-bold text-white">${label}</div>
                                <div class="text-[10px] font-mono text-slate-500">${m.month_ym}</div>
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono text-slate-300">${m.active_headcount || 0}</td>
                            <td class="py-2.5 px-3 text-right font-mono text-emerald-400">${(m.present_count || 0).toLocaleString('en-IN')}</td>
                            <td class="py-2.5 px-3 text-right font-mono ${m.absent_count > 0 ? 'text-rose-400' : 'text-slate-500'}">${m.absent_count || 0}</td>
                            <td class="py-2.5 px-3 text-right font-mono font-bold ${m.attendance_rate_pct >= 90 ? 'text-emerald-400' : 'text-amber-300'}">${m.attendance_rate_pct}%</td>
                            <td class="py-2.5 px-3 text-right font-mono text-white">${(m.total_orders || 0).toLocaleString('en-IN')}</td>
                            <td class="py-2.5 px-3 text-right font-mono text-amber-300">${m.avg_ipp || 0}</td>
                            <td class="py-2.5 px-3 text-right font-mono font-bold text-rose-400">${this.formatCurrency(m.loss_total || 0)}</td>
                            <td class="py-2.5 px-3 text-right font-mono text-slate-400">${(m.loss_incidents || 0).toLocaleString('en-IN')}</td>
                            <td class="py-2.5 px-3 text-center">
                                <button type="button" onclick="zeptoApp.onGlobalMonthChange('${m.month_ym}')" class="px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-[10px] font-mono text-slate-300 hover:text-white transition">
                                    Filter ↗
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // 4. Day-on-Day Table
        this.renderDashboardDodTable();
    },

    renderDashboardDodTable() {
        const dod = this.dashboard?.dod_filtered || [];
        const badge = document.getElementById('dashDodRecordBadge');
        if (badge) badge.textContent = `${dod.length} Days`;

        const tbody = document.getElementById('dashDodTableBody');
        if (!tbody) return;

        if (dod.length === 0) {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center py-6 text-slate-500 text-xs">No daily operational records found for this scope.</td></tr>`;
            return;
        }

        tbody.innerHTML = dod.map(d => `
            <tr class="hover:bg-white/[0.02] transition">
                <td class="py-2 px-3 font-mono text-slate-300 whitespace-nowrap">${d.date}</td>
                <td class="py-2 px-3 text-right font-mono text-slate-400">${d.shifts_scheduled || 0}</td>
                <td class="py-2 px-3 text-right font-mono text-emerald-400">${d.shifts_present || 0}</td>
                <td class="py-2 px-3 text-right font-mono ${d.shifts_absent > 0 ? 'text-rose-400' : 'text-slate-500'}">${d.shifts_absent || 0}</td>
                <td class="py-2 px-3 text-right font-mono font-bold ${d.attendance_rate_pct >= 90 ? 'text-emerald-400' : 'text-amber-300'}">${d.attendance_rate_pct}%</td>
                <td class="py-2 px-3 text-right font-mono text-white">${(d.orders_dispatched || 0).toLocaleString('en-IN')}</td>
                <td class="py-2 px-3 text-right font-mono text-slate-300">${this.formatCurrency(d.sales_gmv || 0)}</td>
                <td class="py-2 px-3 text-right font-mono text-amber-300">${d.packer_ipp || 0}</td>
                <td class="py-2 px-3 text-right font-mono font-bold text-rose-400">${this.formatCurrency(d.loss_total || 0)}</td>
                <td class="py-2 px-3 text-right font-mono text-slate-400">${d.loss_incidents || 0}</td>
                <td class="py-2 px-3 text-right font-mono text-slate-300">${d.skus_affected || 0}</td>
            </tr>
        `).join('');
    },

    filterDashboardDod() {
        const query = (document.getElementById('dashDodSearchInput')?.value || '').trim().toLowerCase();
        const all = this.dashboard?.analytics?.dod_metrics || [];
        if (!query) {
            this.dashboard.dod_filtered = [...all];
        } else {
            this.dashboard.dod_filtered = all.filter(d => (d.date || '').toLowerCase().includes(query));
        }
        this.renderDashboardDodTable();
    },

    exportDashboardDodCsv() {
        const dod = this.dashboard?.dod_filtered || this.dashboard?.analytics?.dod_metrics || [];
        if (dod.length === 0) {
            alert('No Day-on-Day records available to export.');
            return;
        }

        const headers = ['Date', 'Shifts Scheduled', 'Shifts Present', 'Shifts Absent', 'Attendance Rate (%)', 'Orders Dispatched', 'Sales GMV (INR)', 'Packer IPP', 'Loss Amount (INR)', 'Loss Incidents', 'SKUs Affected'];
        const csvRows = [headers.join(',')];

        dod.forEach(d => {
            csvRows.push([
                `"${d.date}"`,
                d.shifts_scheduled || 0,
                d.shifts_present || 0,
                d.shifts_absent || 0,
                d.attendance_rate_pct || 0,
                d.orders_dispatched || 0,
                d.sales_gmv || 0,
                d.packer_ipp || 0,
                d.loss_total || 0,
                d.loss_incidents || 0,
                d.skus_affected || 0,
            ].join(','));
        });

        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `zepto_dod_operations_${this.currentGlobalMonth || 'ALL'}_${new Date().toISOString().slice(0,10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    },

    // -----------------------------------------------------------------------
    // Staffing Requirements, Role Base Pay & Fulfillment Capacity
    // -----------------------------------------------------------------------

    getBasePayForRole(role) {
        const basePays = this.overviewData?.headcount?.base_pays || {
            'PICKER': 18000,
            'SHIFT_INCHARGE': 25000,
            'SECURITY_GUARD': 16000,
            'HOUSEKEEPING': 14000,
        };
        return basePays[role] || 15000;
    },

    renderStaffingCapacity(hc) {
        if (!hc) return;

        const targetTotal = hc.target_total || 15;
        const staffPct = hc.staffing_pct || Math.round(((hc.active || 0) / targetTotal) * 100);

        const overallBadge = document.getElementById('staffingOverallBadge');
        if (overallBadge) {
            overallBadge.textContent = `${hc.active || 0} / ${targetTotal} Active Staff (${staffPct}% Capacity)`;
            overallBadge.className = `text-[10px] font-extrabold px-2.5 py-0.5 rounded-full border font-mono ${
                staffPct >= 100 ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-purple-500/20 text-purple-200 border-purple-500/40'
            }`;
        }

        const capacity = hc.capacity || {};
        ['PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING'].forEach(role => {
            const cap = capacity[role] || { current: 0, target: 1, deficit: 1, pct: 0, fulfilled: false, base_pay: 15000 };

            const badgeEl = document.getElementById(`capBadge-${role}`);
            if (badgeEl) badgeEl.textContent = `${cap.current} / ${cap.target}`;

            const barEl = document.getElementById(`capBar-${role}`);
            if (barEl) barEl.style.width = `${Math.min(100, cap.pct)}%`;

            const pctEl = document.getElementById(`capPct-${role}`);
            if (pctEl) pctEl.textContent = `${cap.pct}%`;

            const payEl = document.getElementById(`capPay-${role}`);
            if (payEl) payEl.textContent = `${this.formatCurrency(cap.base_pay || 0)}/mo`;

            const statusEl = document.getElementById(`capStatus-${role}`);
            if (statusEl) {
                if (cap.fulfilled) {
                    statusEl.innerHTML = `<span class="text-emerald-400 font-bold">✅ Fully Staffed</span>`;
                } else {
                    statusEl.innerHTML = `<span class="text-amber-300 font-semibold">⚠️ ${cap.deficit} more needed</span>`;
                }
            }
        });
    },

    openStaffingTargetsModal() {
        const targets = this.overviewData?.headcount?.targets || {
            'PICKER': 9,
            'SHIFT_INCHARGE': 3,
            'SECURITY_GUARD': 2,
            'HOUSEKEEPING': 1,
        };
        const basePays = this.overviewData?.headcount?.base_pays || {
            'PICKER': 18000,
            'SHIFT_INCHARGE': 25000,
            'SECURITY_GUARD': 16000,
            'HOUSEKEEPING': 14000,
        };

        ['PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING'].forEach(role => {
            const targetInput = document.getElementById(`targetInput-${role}`);
            if (targetInput) {
                targetInput.value = targets[role] !== undefined ? targets[role] : 1;
                targetInput.oninput = () => this.updateModalTargetTotal();
            }
            const payInput = document.getElementById(`payInput-${role}`);
            if (payInput) {
                payInput.value = basePays[role] !== undefined ? basePays[role] : 15000;
                payInput.oninput = () => this.updateModalTargetTotal();
            }
        });

        this.updateModalTargetTotal();
        this.openModal('modalStaffingTargets');
    },

    updateModalTargetTotal() {
        let totalCount = 0;
        let totalPayroll = 0;

        ['PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING'].forEach(role => {
            const cnt = parseInt(document.getElementById(`targetInput-${role}`)?.value || '0', 10);
            const pay = parseFloat(document.getElementById(`payInput-${role}`)?.value || '0');
            const validCnt = isNaN(cnt) ? 0 : Math.max(0, cnt);
            const validPay = isNaN(pay) ? 0 : Math.max(0, pay);
            const subtotal = validCnt * validPay;

            totalCount += validCnt;
            totalPayroll += subtotal;

            const projEl = document.getElementById(`roleProjected-${role}`);
            if (projEl) projEl.textContent = `${this.formatCurrency(subtotal)}/mo`;
        });

        const totalEl = document.getElementById('modalTargetTotalCount');
        if (totalEl) totalEl.textContent = `${totalCount} Staff`;

        const payrollEl = document.getElementById('modalTargetProjectedPayroll');
        if (payrollEl) payrollEl.textContent = `${this.formatCurrency(totalPayroll)} / mo`;
    },

    async saveStaffingTargets(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveStaffingTargets');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Saving Configurations...';
        }

        try {
            const role_configs = {
                'PICKER': {
                    target_count: parseInt(document.getElementById('targetInput-PICKER')?.value || '9', 10),
                    base_pay: parseFloat(document.getElementById('payInput-PICKER')?.value || '18000')
                },
                'SHIFT_INCHARGE': {
                    target_count: parseInt(document.getElementById('targetInput-SHIFT_INCHARGE')?.value || '3', 10),
                    base_pay: parseFloat(document.getElementById('payInput-SHIFT_INCHARGE')?.value || '25000')
                },
                'SECURITY_GUARD': {
                    target_count: parseInt(document.getElementById('targetInput-SECURITY_GUARD')?.value || '2', 10),
                    base_pay: parseFloat(document.getElementById('payInput-SECURITY_GUARD')?.value || '16000')
                },
                'HOUSEKEEPING': {
                    target_count: parseInt(document.getElementById('targetInput-HOUSEKEEPING')?.value || '1', 10),
                    base_pay: parseFloat(document.getElementById('payInput-HOUSEKEEPING')?.value || '14000')
                },
            };

            const res = await fetch('/api/v1/zepto/staffing-targets', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role_configs }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to update staffing targets & base pay');

            this.closeModal('modalStaffingTargets');
            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save Configurations';
            }
        }
    },

    // -----------------------------------------------------------------------
    // Tab 1: Staff & Employees
    // -----------------------------------------------------------------------

    async loadEmployees() {
        const role = document.getElementById('empRoleFilter')?.value || 'ALL';
        const status = document.getElementById('empStatusFilter')?.value || 'ACTIVE';
        const search = document.getElementById('empSearchInput')?.value || '';

        try {
            const params = new URLSearchParams();
            if (role !== 'ALL') params.append('role', role);
            if (status !== 'ALL') params.append('status', status);
            if (search) params.append('search', search);
            if (this.includeHiddenEmployees) params.append('include_hidden', 'true');

            const res = await fetch(`/api/v1/zepto/employees?${params.toString()}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load employees');

            this.employees = data.items || [];
            this.renderEmployees(this.employees);

            // Re-render contextual active staff tables across tabs
            this.renderActiveStaffSubtables();
        } catch (err) {
            console.error('[ZEPTO] Error loading employees:', err);
        }
    },

    toggleIncludeHiddenEmployees() {
        this.includeHiddenEmployees = !this.includeHiddenEmployees;
        const icon = document.getElementById('btnToggleHiddenStaffIcon');
        const text = document.getElementById('btnToggleHiddenStaffText');
        const btn = document.getElementById('btnToggleHiddenStaff');

        if (this.includeHiddenEmployees) {
            if (icon) icon.textContent = '🙈';
            if (text) text.textContent = 'Hide Inactive';
            if (btn) btn.className = 'px-2.5 py-1.5 rounded-md bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-xs font-semibold text-amber-200 transition flex items-center gap-1.5 shadow-sm';
            this.showToast('👁️ Showing all staff including hidden/inactive records');
        } else {
            if (icon) icon.textContent = '👁️';
            if (text) text.textContent = 'Show Hidden';
            if (btn) btn.className = 'px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition flex items-center gap-1.5';
            this.showToast('🙈 Filtering out hidden/inactive staff');
        }

        this.loadEmployees();
    },

    async toggleEmployeeVisibility(empId) {
        if (!empId) return;
        try {
            const res = await fetch(`/api/v1/zepto/employees/${encodeURIComponent(empId)}/visibility`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to update visibility');

            const isHidden = data.employee?.is_hidden === 1;
            this.showToast(isHidden ? `🙈 Marked ${data.employee?.name || 'employee'} as hidden` : `👁️ Restored ${data.employee?.name || 'employee'} to active roster`);

            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            this.showToast('⚠️ Visibility toggle error: ' + err.message, true);
        }
    },

    async syncRosterFromAttendance() {
        const btn = document.getElementById('btnSyncRosterAtt');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span>⏳</span> Syncing Roster...';
        }

        try {
            const res = await fetch('/api/v1/zepto/employees/sync-roster', { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Roster sync failed');

            this.showToast(`✅ Roster synced! Added ${data.synced_count || 0} staff members from attendance records.`);
            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            this.showToast('⚠️ Sync failed: ' + err.message, true);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<span>🔄</span> Sync Real Roster';
            }
        }
    },

    async purgeFramedEmployees() {
        if (!confirm('Are you sure you want to delete all starter framed/mock demo records (employees, candidates, demo expenses, capital tranches)? Real attendance and authentic imports will remain untouched.')) return;
        try {
            const res = await fetch('/api/v1/zepto/employees/purge-framed', { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to purge mock records');

            this.showToast(`🧹 Purged demo records (${data.purged_employees || data.purged_count || 0} employees, ${data.purged_expenses || 0} expenses, ${data.purged_candidates || 0} candidates).`);
            await this.loadOverview();
            await this.loadEmployees();
            await this.loadExpenses();
            await this.loadCandidates();
            await this.loadSecurity();
        } catch (err) {
            this.showToast('⚠️ Purge error: ' + err.message, true);
        }
    },

    filterEmployees() {
        this.loadEmployees();
    },

    resetEmployeeFilters() {
        const role = document.getElementById('empRoleFilter');
        const status = document.getElementById('empStatusFilter');
        const search = document.getElementById('empSearchInput');
        if (role) role.value = 'ALL';
        if (status) status.value = 'ACTIVE';
        if (search) search.value = '';
        this.loadEmployees();
    },

    // Helper to format relative presence text (e.g. "Today", "1 day ago", "7 days ago", "Never / No record")
    formatRelativeLastPresent(dateStr) {
        if (!dateStr) {
            return {
                text: 'Never / No record',
                badgeClass: 'bg-rose-500/10 text-rose-300 border-rose-500/20',
                days: Infinity,
            };
        }
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const [y, m, d] = dateStr.split('-').map(Number);
        const shiftDate = new Date(y, m - 1, d);
        shiftDate.setHours(0, 0, 0, 0);

        const diffTime = today.getTime() - shiftDate.getTime();
        const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

        if (diffDays <= 0) {
            return {
                text: 'Today',
                badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
                days: 0,
            };
        } else if (diffDays === 1) {
            return {
                text: '1 day ago',
                badgeClass: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
                days: 1,
            };
        } else if (diffDays <= 3) {
            return {
                text: `${diffDays} days ago`,
                badgeClass: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
                days: diffDays,
            };
        } else if (diffDays <= 6) {
            return {
                text: `${diffDays} days ago`,
                badgeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
                days: diffDays,
            };
        } else {
            return {
                text: `${diffDays} days ago`,
                badgeClass: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
                days: diffDays,
            };
        }
    },

    sortEmployees(column) {
        if (this.empSortColumn === column) {
            this.empSortDirection = this.empSortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.empSortColumn = column;
            this.empSortDirection = (column === 'rating' || column === 'base_salary_monthly' || column === 'current_month_bonus') ? 'desc' : 'asc';
        }
        this.updateEmpSortIcons();
        this.renderEmployees(this.employees);
    },

    updateEmpSortIcons() {
        const columns = ['name', 'role', 'status', 'rating', 'base_salary_monthly', 'current_month_bonus', 'joining_date'];
        columns.forEach(col => {
            const el = document.getElementById(`sortIcon-${col}`);
            if (!el) return;
            if (this.empSortColumn === col) {
                el.textContent = this.empSortDirection === 'asc' ? '▲' : '▼';
                el.className = 'text-white font-mono text-[9px] font-bold';
            } else {
                el.textContent = '⇅';
                el.className = 'text-slate-500 font-mono text-[9px]';
            }
        });
    },

    renderEmployees(items) {
        const tbody = document.getElementById('employeesTableBody');
        const countBadge = document.getElementById('empTableCountBadge');
        if (countBadge) countBadge.textContent = `${items.length} Staff members`;
        if (!tbody) return;

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="p-8 text-center text-slate-500">
                        No employees found matching filter criteria. Click "Add New Staff" to create one.
                    </td>
                </tr>
            `;
            return;
        }

        // Apply in-memory sort based on selected column and direction
        const sortedItems = [...items].sort((a, b) => {
            const col = this.empSortColumn;
            let valA = a[col];
            let valB = b[col];

            if (col === 'base_salary_monthly' || col === 'current_month_bonus' || col === 'rating') {
                valA = parseFloat(valA || 0);
                valB = parseFloat(valB || 0);
                return this.empSortDirection === 'asc' ? valA - valB : valB - valA;
            }

            valA = (valA || '').toString().toLowerCase();
            valB = (valB || '').toString().toLowerCase();
            const cmp = valA.localeCompare(valB);
            return this.empSortDirection === 'asc' ? cmp : -cmp;
        });

        tbody.innerHTML = sortedItems.map(emp => {
            const roleBadge = this.getRoleBadge(emp.role);
            const statusBadge = this.getStatusBadge(emp.status);
            const ratingStars = this.getRatingStars(emp.rating);
            const docsHtml = this.getDocsPill(emp.aadhar_doc_url, emp.resume_doc_url);
            const isHidden = emp.is_hidden === 1;
            const lastPres = this.formatRelativeLastPresent(emp.last_present_date);

            return `
                <tr class="hover:bg-white/[0.04] transition cursor-pointer ${isHidden ? 'opacity-50 bg-white/[0.01]' : ''}" onclick="zeptoApp.openStaffDrawer('${emp.id}')" title="Click row to open employee performance, attendance & IPP drawer">
                    <td class="p-3.5 pl-4">
                        <div class="font-bold text-white text-sm flex items-center gap-1.5 flex-wrap">
                            <span>${emp.name}</span>
                            <span class="text-[10px] text-purple-400 opacity-60">↗</span>
                            ${isHidden ? '<span class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">HIDDEN</span>' : ''}
                        </div>
                        <div class="text-[11px] text-slate-400 font-mono">${emp.phone || 'No phone'} ${emp.email ? '· ' + emp.email : ''}</div>
                        <div class="mt-1 flex items-center gap-1.5">
                            <span class="text-[10px] text-slate-400">Last Present:</span>
                            <span class="text-[10px] font-bold font-mono px-1.5 py-0.2 rounded border ${lastPres.badgeClass}" title="${emp.last_present_date ? 'Shift Date: ' + emp.last_present_date : 'No present attendance records'}">
                                ${lastPres.text}
                            </span>
                        </div>
                    </td>
                    <td class="p-3.5">${roleBadge}</td>
                    <td class="p-3.5 text-center">${statusBadge}</td>
                    <td class="p-3.5 text-center font-mono font-bold text-amber-300">${ratingStars}</td>
                    <td class="p-3.5 text-right font-mono font-bold text-white">${this.formatCurrency(emp.base_salary_monthly)}</td>
                    <td class="p-3.5 text-right font-mono font-bold text-purple-300">
                        ${emp.current_month_bonus > 0 ? `+${this.formatCurrency(emp.current_month_bonus)}` : '—'}
                    </td>
                    <td class="p-3.5 text-slate-300 text-[11px]">
                        <div>Joined: <span class="font-mono text-slate-400">${emp.joining_date}</span></div>
                        ${emp.resignation_date ? `<div class="text-rose-400">Resigned: <span class="font-mono">${emp.resignation_date}</span></div>` : ''}
                    </td>
                    <td class="p-3.5 text-center" onclick="event.stopPropagation()">${docsHtml}</td>
                    <td class="p-3.5 pr-4 text-center">
                        <div class="flex items-center justify-center gap-1.5">
                            <button type="button" onclick="event.stopPropagation(); zeptoApp.openStaffDrawer('${emp.id}')" class="px-2 py-1 rounded bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 font-bold text-[11px] border border-indigo-500/30 transition" title="Open Full Employee Profile & Analytics Drawer">
                                📊 Details
                            </button>
                            <button type="button" onclick="event.stopPropagation(); zeptoApp.openSalaryDrilldown('${emp.id}')" class="px-2 py-1 rounded bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 font-bold text-[11px] border border-purple-500/30 transition" title="MoM Salary History">
                                💵 Salary
                            </button>
                            <button type="button" onclick="event.stopPropagation(); zeptoApp.toggleEmployeeVisibility('${emp.id}')" class="p-1 rounded ${isHidden ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30' : 'bg-white/5 text-slate-300 hover:bg-white/10'} text-xs" title="${isHidden ? 'Unhide / Restore Staff' : 'Hide Inactive Staff'}">
                                ${isHidden ? '👁️' : '🙈'}
                            </button>
                            <button type="button" onclick="event.stopPropagation(); zeptoApp.openEditEmployeeModal('${emp.id}')" class="p-1 rounded bg-white/5 hover:bg-white/10 text-slate-300 text-xs" title="Edit Staff Details">
                                ✏️
                            </button>
                            <button type="button" onclick="event.stopPropagation(); zeptoApp.deleteEmployee('${emp.id}')" class="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs" title="Delete Staff">
                                🗑️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    },

    // -----------------------------------------------------------------------
    // Staff & Payroll Slide-Out Inspector Drawer (sumi:desktop-app-design)
    // -----------------------------------------------------------------------

    async openStaffDrawer(empId, yearMonth = null) {
        if (!empId) return;
        this.currentStaffDrawerEmpId = empId;
        this.currentStaffDrawerMonth = yearMonth;

        const drawer = document.getElementById('staffEmployeeDrawer');
        const backdrop = document.getElementById('staffEmployeeDrawerBackdrop');
        if (drawer) {
            drawer.classList.remove('translate-x-full');
            drawer.classList.add('translate-x-0');
        }
        if (backdrop) {
            backdrop.classList.remove('opacity-0', 'pointer-events-none');
            backdrop.classList.add('opacity-100');
        }

        try {
            const url = `/api/v1/zepto/employees/${encodeURIComponent(empId)}/profile-analytics${yearMonth ? '?year_month=' + encodeURIComponent(yearMonth) : ''}`;
            const res = await fetch(url);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to fetch staff analytics');

            const emp = data.employee || {};
            const att = data.attendance || {};
            const prod = data.productivity || {};
            const salaries = data.salaries || [];
            const ratings = data.ratings || [];
            const availMonths = data.available_months || [data.selected_month];
            const selMonth = data.selected_month;
            this.currentStaffDrawerMonth = selMonth;

            // 1. Header Elements
            const nameEl = document.getElementById('staffDrawerName');
            const idEl = document.getElementById('staffDrawerId');
            const roleEl = document.getElementById('staffDrawerRole');
            const statusEl = document.getElementById('staffDrawerStatus');
            const joinedEl = document.getElementById('staffDrawerJoined');
            const avatarEl = document.getElementById('staffDrawerAvatar');

            if (nameEl) nameEl.textContent = emp.name || 'Staff Profile';
            if (idEl) idEl.textContent = emp.id || empId;
            if (roleEl) roleEl.innerHTML = this.getRoleBadge(emp.role || 'PICKER');
            if (statusEl) statusEl.innerHTML = this.getStatusBadge(emp.status || 'ACTIVE');
            if (joinedEl) joinedEl.textContent = `Joined ${emp.joining_date || '—'}`;
            const lastPresEl = document.getElementById('staffDrawerLastPresent');
            if (lastPresEl) {
                const lp = this.formatRelativeLastPresent(emp.last_present_date);
                lastPresEl.innerHTML = `Last Present: <span class="px-1.5 py-0.2 rounded text-[10px] font-bold font-mono border ${lp.badgeClass}" title="${emp.last_present_date ? 'Shift Date: ' + emp.last_present_date : 'No present attendance records'}">${lp.text}</span>`;
            }
            if (avatarEl) {
                const initials = (emp.name || 'EM').split(' ').map(w => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'EM';
                avatarEl.textContent = initials;
            }

            // 2. Month Selector
            const monthSelect = document.getElementById('staffDrawerMonthSelect');
            if (monthSelect) {
                monthSelect.innerHTML = availMonths.map(m => `<option value="${m}" ${m === selMonth ? 'selected' : ''}>${m}</option>`).join('');
            }

            // 3. Risk Tier Indicator
            const riskEl = document.getElementById('staffDrawerRiskBadge');
            if (riskEl) {
                const rTier = att.risk_tier || 'LOW';
                if (rTier === 'CRITICAL') {
                    riskEl.textContent = 'CRITICAL RISK';
                    riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse font-mono';
                } else if (rTier === 'HIGH') {
                    riskEl.textContent = 'HIGH RISK';
                    riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono';
                } else if (rTier === 'MODERATE') {
                    riskEl.textContent = 'MODERATE';
                    riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-mono';
                } else {
                    riskEl.textContent = 'OPTIMAL';
                    riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-mono';
                }
            }

            // 4. Top 4 Metric KPI Cards
            const attRateEl = document.getElementById('staffDrawerAttRate');
            const attSubEl = document.getElementById('staffDrawerAttSub');
            const hoursEl = document.getElementById('staffDrawerHours');
            const avgDailyEl = document.getElementById('staffDrawerAvgShiftHours');
            const ippEl = document.getElementById('staffDrawerIPP');
            const ippSubEl = document.getElementById('staffDrawerIPPSub');
            const payEl = document.getElementById('staffDrawerPay');
            const bonusSubEl = document.getElementById('staffDrawerBonusSub');

            if (attRateEl) attRateEl.textContent = `${parseFloat(att.attendance_rate_pct || 0).toFixed(1)}%`;
            if (attSubEl) attSubEl.textContent = `${att.present_count || 0} / ${att.total_shifts || 0} shifts present`;
            if (hoursEl) hoursEl.textContent = `${att.total_hours_worked || 0}h`;
            if (avgDailyEl) avgDailyEl.textContent = `${att.avg_shift_hours || 0}h / day avg`;
            if (ippEl) ippEl.textContent = prod.avg_ipp > 0 ? `${prod.avg_ipp} IPP` : '—';
            if (ippSubEl) ippSubEl.textContent = `${(prod.total_items_picked || 0).toLocaleString()} items picked`;
            if (payEl) payEl.textContent = this.formatCurrency(emp.base_salary_monthly);
            if (bonusSubEl) bonusSubEl.textContent = emp.current_month_bonus > 0 ? `+${this.formatCurrency(emp.current_month_bonus)} Bonus` : '+₹0 Bonus';

            // 5. Monthly Attendance Segmented Bar
            const totShifts = att.total_shifts || 1;
            const pPct = ((att.present_count || 0) / totShifts) * 100;
            const hPct = ((att.half_day_count || 0) / totShifts) * 100;
            const aPct = ((att.absent_count || 0) / totShifts) * 100;
            const oPct = ((att.week_off_count || 0) / totShifts) * 100;

            const barP = document.getElementById('staffDrawerBarPres');
            const barH = document.getElementById('staffDrawerBarHalf');
            const barA = document.getElementById('staffDrawerBarAbs');
            const barO = document.getElementById('staffDrawerBarOff');
            if (barP) barP.style.width = `${pPct}%`;
            if (barH) barH.style.width = `${hPct}%`;
            if (barA) barA.style.width = `${aPct}%`;
            if (barO) barO.style.width = `${oPct}%`;

            const cntP = document.getElementById('staffDrawerCountPres');
            const cntH = document.getElementById('staffDrawerCountHalf');
            const cntA = document.getElementById('staffDrawerCountAbs');
            const cntO = document.getElementById('staffDrawerCountOff');
            if (cntP) cntP.textContent = att.present_count || 0;
            if (cntH) cntH.textContent = att.half_day_count || 0;
            if (cntA) cntA.textContent = att.absent_count || 0;
            if (cntO) cntO.textContent = att.week_off_count || 0;

            const barTitle = document.getElementById('staffDrawerAttBarTitle');
            if (barTitle) barTitle.textContent = `${selMonth} (${att.total_shifts || 0} Shifts Total)`;

            // 6. MoM Performance Ratings Container
            const ratContainer = document.getElementById('staffDrawerRatingsContainer');
            const ratBadge = document.getElementById('staffDrawerLatestRatingBadge');
            if (ratBadge) ratBadge.textContent = `${parseFloat(emp.rating || 5.0).toFixed(1)} / 5.0 ⭐`;
            if (ratContainer) {
                if (ratings.length === 0) {
                    ratContainer.innerHTML = `<div class="text-[11px] text-slate-500 text-center py-3">No monthly reviews logged yet. Click "Rate Staff" to add.</div>`;
                } else {
                    ratContainer.innerHTML = ratings.map(r => `
                        <div class="p-2 rounded bg-black/40 border border-white/5 flex items-center justify-between text-xs">
                            <div class="flex items-center gap-2">
                                <span class="font-bold text-white font-mono">${r.year_month}</span>
                                <span class="text-amber-300 font-bold font-mono">⭐ ${parseFloat(r.rating).toFixed(1)}</span>
                            </div>
                            <span class="text-[10px] text-slate-400 italic truncate max-w-[140px]">${r.feedback ? `"${r.feedback}"` : 'No remarks'}</span>
                        </div>
                    `).join('');
                }
            }

            // 7. MoM Attendance Trend Container
            const momAttContainer = document.getElementById('staffDrawerMomAttContainer');
            if (momAttContainer) {
                const momTrends = att.mom_trend || [];
                if (momTrends.length === 0) {
                    momAttContainer.innerHTML = `<div class="text-[11px] text-slate-500 text-center py-3">No historical attendance data found.</div>`;
                } else {
                    momAttContainer.innerHTML = momTrends.map(m => `
                        <div class="p-2 rounded bg-black/40 border border-white/5 flex items-center justify-between text-xs">
                            <div class="flex items-center gap-2">
                                <span class="font-bold text-white font-mono">${m.month}</span>
                                <span class="text-[10px] text-slate-400 font-mono">${m.present_count}/${m.total_shifts} present</span>
                            </div>
                            <span class="font-mono font-bold ${m.attendance_rate_pct >= 90 ? 'text-emerald-400' : 'text-amber-300'}">${m.attendance_rate_pct}%</span>
                        </div>
                    `).join('');
                }
            }

            // 8. Granular Shift & Work Log (Selected Month)
            const punchTbody = document.getElementById('staffDrawerPunchTableBody');
            const punchCountEl = document.getElementById('staffDrawerPunchCount');
            const punches = att.punch_history || [];
            if (punchCountEl) punchCountEl.textContent = `${punches.length} Shifts`;

            if (punchTbody) {
                if (punches.length === 0) {
                    punchTbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-slate-500 text-xs">No shift records found for ${selMonth}.</td></tr>`;
                } else {
                    punchTbody.innerHTML = punches.map(p => {
                        let stBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">PRESENT</span>';
                        if (p.status === 'ABSENT') stBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">ABSENT</span>';
                        else if (p.status === 'HALF_DAY') stBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">HALF DAY</span>';
                        else if (p.status === 'WEEK_OFF') stBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-500/20 text-slate-400 border border-white/10">WEEK OFF</span>';
                        else if (p.status === 'HOLIDAY') stBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/40">HOLIDAY</span>';

                        const durMins = p.work_duration_mins || 0;
                        const durHours = (durMins / 60).toFixed(1);

                        return `
                            <tr class="hover:bg-white/[0.02] transition">
                                <td class="py-2 px-2.5 font-bold text-white">${p.shift_date}</td>
                                <td class="py-2 px-2.5 text-slate-300 text-[10px]">${p.shift_name || 'General Shift'}</td>
                                <td class="py-2 px-2.5 text-sky-300 font-mono text-[10px]">${p.shift_time || '09:00 - 18:00'}</td>
                                <td class="py-2 px-2.5 text-right font-mono text-purple-300">${durMins > 0 ? `${durHours}h (${durMins}m)` : '—'}</td>
                                <td class="py-2 px-2.5 text-center">${stBadge}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            // 9. MoM Salary History Table
            const salTbody = document.getElementById('staffDrawerSalaryTableBody');
            if (salTbody) {
                if (salaries.length === 0) {
                    salTbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-slate-500 text-xs">No compensation slips recorded yet.</td></tr>`;
                } else {
                    salTbody.innerHTML = salaries.map(s => `
                        <tr class="hover:bg-white/[0.02] transition">
                            <td class="py-2 px-2.5 font-bold text-white">${s.year_month}</td>
                            <td class="py-2 px-2.5 text-right font-mono text-slate-300">${this.formatCurrency(s.base_amount)}</td>
                            <td class="py-2 px-2.5 text-right font-mono text-purple-400">${s.bonus_amount > 0 ? '+' + this.formatCurrency(s.bonus_amount) : '₹0'}</td>
                            <td class="py-2 px-2.5 text-right font-mono font-bold text-emerald-400">${this.formatCurrency(s.net_paid)}</td>
                            <td class="py-2 px-2.5 text-center font-mono font-bold text-amber-300">⭐ ${parseFloat(s.performance_rating || 5.0).toFixed(1)}</td>
                            <td class="py-2 px-2.5 text-center">
                                <span class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">${s.payment_status || 'PAID'}</span>
                            </td>
                        </tr>
                    `).join('');
                }
            }

        } catch (err) {
            console.error('Error loading staff drawer:', err);
            this.showToast(`⚠️ ${err.message}`);
        }
    },

    closeStaffDrawer() {
        const drawer = document.getElementById('staffEmployeeDrawer');
        const backdrop = document.getElementById('staffEmployeeDrawerBackdrop');
        if (drawer) {
            drawer.classList.remove('translate-x-0');
            drawer.classList.add('translate-x-full');
        }
        if (backdrop) {
            backdrop.classList.remove('opacity-100');
            backdrop.classList.add('opacity-0', 'pointer-events-none');
        }
    },

    onStaffDrawerMonthChange(val) {
        if (this.currentStaffDrawerEmpId) {
            this.openStaffDrawer(this.currentStaffDrawerEmpId, val);
        }
    },

    openStaffDrawerBonusModal() {
        if (!this.currentStaffDrawerEmpId) return;
        this.openSalaryDrilldown(this.currentStaffDrawerEmpId);
    },

    openStaffDrawerSalaryModal() {
        if (!this.currentStaffDrawerEmpId) return;
        this.openSalaryDrilldown(this.currentStaffDrawerEmpId);
        if (this.currentStaffDrawerMonth) {
            const mInput = document.getElementById('salSlipMonth');
            if (mInput) mInput.value = this.currentStaffDrawerMonth;
        }
    },

    openStaffDrawerRatingModal() {
        if (!this.currentStaffDrawerEmpId) return;
        const ym = this.currentStaffDrawerMonth || new Date().toISOString().slice(0, 7);
        this.openMonthlyRatingModal(this.currentStaffDrawerEmpId, ym);
    },

    openStaffDrawerEditModal() {
        if (!this.currentStaffDrawerEmpId) return;
        this.openEditEmployeeModal(this.currentStaffDrawerEmpId);
    },

    async toggleStaffDrawerVisibility() {
        if (!this.currentStaffDrawerEmpId) return;
        await this.toggleEmployeeVisibility(this.currentStaffDrawerEmpId);
        await this.openStaffDrawer(this.currentStaffDrawerEmpId, this.currentStaffDrawerMonth);
    },

    // -----------------------------------------------------------------------
    // Employee Modal & MoM Salary Drilldown
    // -----------------------------------------------------------------------

    openAddEmployeeModal() {
        document.getElementById('formEmployee')?.reset();
        document.getElementById('empFormId').value = '';
        document.getElementById('modalEmployeeTitle').innerHTML = '<span>👤</span> Add Store Staff Member';
        document.getElementById('empFormJoiningDate').value = new Date().toISOString().split('T')[0];
        document.getElementById('resignationReasonGroup').style.display = 'none';

        const roleSelect = document.getElementById('empFormRole');
        const salInput = document.getElementById('empFormSalary');
        if (roleSelect && salInput) {
            salInput.value = this.getBasePayForRole(roleSelect.value || 'PICKER');
            roleSelect.onchange = () => {
                if (!document.getElementById('empFormId')?.value) {
                    salInput.value = this.getBasePayForRole(roleSelect.value);
                }
            };
        }

        this.openModal('modalEmployee');
    },

    async openEditEmployeeModal(empId) {
        try {
            const res = await fetch(`/api/v1/zepto/employees/${empId}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to fetch employee');

            const emp = data.employee;
            document.getElementById('empFormId').value = emp.id;
            document.getElementById('empFormName').value = emp.name;
            document.getElementById('empFormRole').value = emp.role;
            document.getElementById('empFormPhone').value = emp.phone || '';
            document.getElementById('empFormEmail').value = emp.email || '';
            document.getElementById('empFormStatus').value = emp.status;
            document.getElementById('empFormSalary').value = emp.base_salary_monthly;
            document.getElementById('empFormRating').value = emp.rating || 5.0;
            document.getElementById('empFormJoiningDate').value = emp.joining_date;
            document.getElementById('empFormResignationDate').value = emp.resignation_date || '';
            document.getElementById('empFormResignationReason').value = emp.resignation_reason || '';
            document.getElementById('empFormAadharUrl').value = emp.aadhar_doc_url || '';
            document.getElementById('empFormResumeUrl').value = emp.resume_doc_url || '';
            document.getElementById('empFormNotes').value = emp.notes || '';

            const grp = document.getElementById('resignationReasonGroup');
            if (grp) grp.style.display = emp.status === 'RESIGNED' ? 'block' : 'none';

            document.getElementById('modalEmployeeTitle').innerHTML = `<span>✏️</span> Edit Staff: ${emp.name}`;
            this.openModal('modalEmployee');
        } catch (err) {
            alert(err.message);
        }
    },

    async saveEmployee(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveEmployee');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Saving...';
        }

        try {
            const empId = document.getElementById('empFormId').value;
            let aadharUrl = document.getElementById('empFormAadharUrl').value;
            let resumeUrl = document.getElementById('empFormResumeUrl').value;

            // Upload files if selected
            const aadharFile = document.getElementById('empFormAadharFile')?.files[0];
            if (aadharFile) {
                const uploaded = await this.uploadFile(aadharFile);
                aadharUrl = uploaded.url;
            }
            const resumeFile = document.getElementById('empFormResumeFile')?.files[0];
            if (resumeFile) {
                const uploaded = await this.uploadFile(resumeFile);
                resumeUrl = uploaded.url;
            }

            const payload = {
                name: document.getElementById('empFormName').value,
                role: document.getElementById('empFormRole').value,
                phone: document.getElementById('empFormPhone').value,
                email: document.getElementById('empFormEmail').value,
                status: document.getElementById('empFormStatus').value,
                base_salary_monthly: parseFloat(document.getElementById('empFormSalary').value || 0),
                rating: parseFloat(document.getElementById('empFormRating').value || 5.0),
                joining_date: document.getElementById('empFormJoiningDate').value,
                resignation_date: document.getElementById('empFormResignationDate').value || null,
                resignation_reason: document.getElementById('empFormResignationReason').value || null,
                aadhar_doc_url: aadharUrl || null,
                resume_doc_url: resumeUrl || null,
                notes: document.getElementById('empFormNotes').value,
            };

            const url = empId ? `/api/v1/zepto/employees/${empId}` : '/api/v1/zepto/employees';
            const method = empId ? 'PUT' : 'POST';

            const res = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to save employee');

            this.closeModal('modalEmployee');
            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save Staff Record';
            }
        }
    },

    async deleteEmployee(empId) {
        if (!confirm('Are you sure you want to delete this employee and all associated salary history?')) return;
        try {
            const res = await fetch(`/api/v1/zepto/employees/${empId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed to delete employee');
            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            alert(err.message);
        }
    },

    // -----------------------------------------------------------------------
    // MoM Salary Drilldown & Instant Performance Bonus
    // -----------------------------------------------------------------------

    async openSalaryDrilldown(empId) {
        this.currentEmpId = empId;
        try {
            const res = await fetch(`/api/v1/zepto/employees/${empId}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to fetch salary data');

            const emp = data.employee;
            const salaries = data.salaries || [];

            document.getElementById('modalSalaryEmpName').innerHTML = `<span>💵</span> ${emp.name} — MoM Compensation Drilldown`;
            document.getElementById('modalSalaryEmpMeta').textContent = `Base Salary: ${this.formatCurrency(emp.base_salary_monthly)} · Current Bonus: ${this.formatCurrency(emp.current_month_bonus || 0)} · Role: ${emp.role}`;

            // Prefill slip form
            const today = new Date();
            const ym = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
            document.getElementById('salSlipMonth').value = ym;
            document.getElementById('salSlipBase').value = emp.base_salary_monthly;
            document.getElementById('salSlipBonus').value = emp.current_month_bonus || 0;

            this.renderSalaryHistory(salaries);
            this.openModal('modalSalaryDrilldown');
        } catch (err) {
            alert(err.message);
        }
    },

    renderSalaryHistory(salaries) {
        const tbody = document.getElementById('salaryHistoryTableBody');
        if (!tbody) return;

        if (salaries.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="p-4 text-center text-slate-500">No monthly payout slips recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = salaries.map(sal => {
            const rVal = parseFloat(sal.performance_rating || 5.0).toFixed(1);
            const feedbackText = sal.rating_feedback ? ` · "${sal.rating_feedback}"` : '';

            return `
                <tr>
                    <td class="p-2.5 font-bold text-white">${sal.year_month}</td>
                    <td class="p-2.5 text-center font-mono font-bold text-amber-300">
                        <span class="px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 inline-flex items-center gap-1" title="${sal.year_month} Rating${feedbackText}">
                            ⭐ ${rVal}
                        </span>
                    </td>
                    <td class="p-2.5 text-right">${this.formatCurrency(sal.base_amount)}</td>
                    <td class="p-2.5 text-right text-purple-400">${sal.bonus_amount > 0 ? '+' + this.formatCurrency(sal.bonus_amount) : '₹0'}</td>
                    <td class="p-2.5 text-right font-bold text-emerald-400">${this.formatCurrency(sal.net_paid)}</td>
                    <td class="p-2.5 text-slate-400 text-[11px]">${sal.payment_date || '—'}</td>
                    <td class="p-2.5 text-center">
                        <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                            ${sal.payment_status || 'PAID'}
                        </span>
                    </td>
                    <td class="p-2.5 text-center">
                        <button type="button" onclick="zeptoApp.openMonthlyRatingModal('${this.currentEmpId}', '${sal.year_month}', ${sal.performance_rating || 5.0}, '${(sal.rating_feedback || '').replace(/'/g, "\\'")}')" class="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 font-bold text-[10px] border border-amber-500/30 transition" title="Edit Monthly Rating">
                            ⭐ Rate
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    openMonthlyRatingModal(empId, yearMonth, currentRating = 5.0, currentFeedback = '') {
        document.getElementById('ratingEmpId').value = empId;
        document.getElementById('ratingMonthInput').value = yearMonth || new Date().toISOString().slice(0, 7);
        const r = parseFloat(currentRating || 5.0);
        document.getElementById('ratingRangeInput').value = r;
        document.getElementById('ratingScoreDisplay').textContent = `⭐ ${r.toFixed(1)}`;
        document.getElementById('ratingFeedbackInput').value = currentFeedback || '';
        this.openModal('modalMonthlyRating');
    },

    async saveMonthlyRating(e) {
        e.preventDefault();
        const empId = document.getElementById('ratingEmpId').value;
        const yearMonth = document.getElementById('ratingMonthInput').value;
        const rating = parseFloat(document.getElementById('ratingRangeInput').value || 5.0);
        const feedback = document.getElementById('ratingFeedbackInput').value;

        try {
            const res = await fetch(`/api/v1/zepto/employees/${empId}/ratings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    year_month: yearMonth,
                    rating: rating,
                    feedback: feedback,
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to save monthly rating');

            this.closeModal('modalMonthlyRating');
            await this.openSalaryDrilldown(empId);
            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            alert(err.message);
        }
    },

    async submitQuickBonus() {
        if (!this.currentEmpId) return;
        const input = document.getElementById('quickBonusInput');
        const amount = parseFloat(input?.value || 0);
        if (amount <= 0) {
            alert('Please enter a positive bonus amount.');
            return;
        }

        try {
            const res = await fetch(`/api/v1/zepto/employees/${this.currentEmpId}/bonus`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: amount, notes: 'Quick performance incentive' }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to award bonus');

            input.value = '';
            await this.openSalaryDrilldown(this.currentEmpId);
            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            alert(err.message);
        }
    },

    async saveSalarySlip(e) {
        e.preventDefault();
        if (!this.currentEmpId) return;

        try {
            const payload = {
                year_month: document.getElementById('salSlipMonth').value,
                base_amount: parseFloat(document.getElementById('salSlipBase').value || 0),
                bonus_amount: parseFloat(document.getElementById('salSlipBonus').value || 0),
                performance_rating: parseFloat(document.getElementById('salSlipRating')?.value || 5.0),
                deductions: 0.0,
                payment_date: new Date().toISOString().split('T')[0],
                payment_status: 'PAID',
                payment_mode: 'BANK_TRANSFER',
            };

            const res = await fetch(`/api/v1/zepto/employees/${this.currentEmpId}/salaries`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to record salary slip');

            await this.openSalaryDrilldown(this.currentEmpId);
            await this.loadOverview();
            await this.loadEmployees();
        } catch (err) {
            alert(err.message);
        }
    },

    // -----------------------------------------------------------------------
    // Tab 2: Store Expenses
    // -----------------------------------------------------------------------

    async loadExpenses() {
        const category = document.getElementById('expCategoryFilter')?.value || 'ALL';
        const incurred = document.getElementById('expIncurredFilter')?.value || 'ALL';
        const reimbStatus = document.getElementById('expReimbursementFilter')?.value || 'ALL';
        const search = document.getElementById('expSearchInput')?.value || '';

        try {
            const params = new URLSearchParams();
            if (category !== 'ALL') params.append('category', category);
            if (incurred !== 'ALL') params.append('incurred_by', incurred);
            if (reimbStatus !== 'ALL') params.append('reimbursement_status', reimbStatus);
            if (search) params.append('search', search);

            const res = await fetch(`/api/v1/zepto/expenses?${params.toString()}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load expenses');

            this.expenses = data.items || [];
            this.renderExpenses(
                this.expenses,
                data.total_amount || 0,
                data.reimbursed_total || 0,
                data.pending_total || 0
            );
        } catch (err) {
            console.error('[ZEPTO] Error loading expenses:', err);
        }
    },

    filterExpenses() {
        this.loadExpenses();
    },

    renderExpenses(items, totalAmount, reimbursedTotal, pendingTotal) {
        const tbody = document.getElementById('expensesTableBody');
        const badge = document.getElementById('expTotalAmountBadge');
        if (badge) badge.textContent = `Total: ${this.formatCurrency(totalAmount)}`;

        // 1. Update Top Reimbursement Summary Cards
        const sumTotalEl = document.getElementById('expSummaryTotalSpend');
        if (sumTotalEl) sumTotalEl.textContent = this.formatCurrency(totalAmount);

        const sumCountEl = document.getElementById('expSummaryCount');
        if (sumCountEl) sumCountEl.textContent = `${items.length} expenses logged`;

        const activeStaff = this.overviewData?.headcount?.active || 1;
        const sumPerStaffEl = document.getElementById('expSummaryPerStaff');
        if (sumPerStaffEl) sumPerStaffEl.textContent = `${this.formatCurrency(totalAmount / Math.max(1, activeStaff))} / staff`;

        const sumReimbEl = document.getElementById('expSummaryReimbursed');
        if (sumReimbEl) sumReimbEl.textContent = this.formatCurrency(reimbursedTotal);

        const sumReimbPctEl = document.getElementById('expSummaryReimbursedPct');
        if (sumReimbPctEl) {
            const pct = totalAmount > 0 ? Math.round((reimbursedTotal / totalAmount) * 100) : 0;
            sumReimbPctEl.textContent = `${pct}% settled`;
        }

        const sumPendingAmtEl = document.getElementById('expSummaryPendingAmount');
        if (sumPendingAmtEl) sumPendingAmtEl.textContent = this.formatCurrency(pendingTotal);

        const sumPendingBadgeEl = document.getElementById('expSummaryPendingBadge');
        if (sumPendingBadgeEl) {
            const pendingCount = items.filter(e => (e.is_reimbursable !== 0) && e.is_reimbursed === 0 && e.incurred_by !== 'STORE_CASH').length;
            sumPendingBadgeEl.textContent = `⏳ ${pendingCount} Pending (${this.formatCurrency(pendingTotal)})`;
            if (pendingCount > 0) {
                sumPendingBadgeEl.className = 'text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse';
            } else {
                sumPendingBadgeEl.className = 'text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
                sumPendingBadgeEl.textContent = '✅ All Settled';
            }
        }

        const sumPendingPctEl = document.getElementById('expSummaryPendingPct');
        if (sumPendingPctEl) {
            const pct = totalAmount > 0 ? Math.round((pendingTotal / totalAmount) * 100) : 0;
            sumPendingPctEl.textContent = `${pct}% of total spend`;
        }

        // Partner-specific pending breakdown pills
        const pendingBreakdownEl = document.getElementById('expSummaryPendingBreakdown');
        if (pendingBreakdownEl) {
            const partnerPending = {};
            items.forEach(exp => {
                if ((exp.is_reimbursable !== 0) && exp.is_reimbursed === 0 && exp.incurred_by !== 'STORE_CASH') {
                    const p = exp.incurred_by || 'Partner';
                    partnerPending[p] = (partnerPending[p] || 0) + exp.amount;
                }
            });

            const partnerKeys = Object.keys(partnerPending);
            if (partnerKeys.length > 0) {
                pendingBreakdownEl.innerHTML = partnerKeys.map(name => {
                    const isJA = name.toLowerCase().includes('jatin');
                    const colorClasses = isJA ? 'bg-purple-500/20 text-purple-200 border-purple-500/40' : 'bg-pink-500/20 text-pink-200 border-pink-500/40';
                    return `<span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${colorClasses}">${name}: ${this.formatCurrency(partnerPending[name])}</span>`;
                }).join('');
            } else {
                pendingBreakdownEl.innerHTML = `<span class="text-emerald-400 font-semibold text-[11px]">✨ All partner out-of-pocket expenses settled</span>`;
            }
        }

        // 2. Update category summary cards
        const catSums = {};
        items.forEach(exp => {
            catSums[exp.category] = (catSums[exp.category] || 0) + exp.amount;
        });
        ['TRAINING', 'UNIFORMS_GEAR', 'EQUIPMENT', 'SNACKS_WELFARE', 'STORE_MAINTENANCE', 'OPERATIONAL'].forEach(cat => {
            const el = document.getElementById(`catSpend-${cat}`);
            if (el) el.textContent = this.formatCurrency(catSums[cat] || 0);
        });

        if (!tbody) return;

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="p-8 text-center text-slate-500">
                        No expenses match the selected filters. Click "Record Expense" to track out-of-pocket store costs.
                    </td>
                </tr>
            `;
            return;
        }

        // 3. Render Table Rows
        tbody.innerHTML = items.map(exp => {
            const catBadge = this.getCategoryBadge(exp.category);
            const proofLink = exp.document_url
                ? `<a href="${exp.document_url}" target="_blank" class="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold hover:underline">📄 View Bill</a>`
                : `<span class="text-slate-600">—</span>`;

            // Reimbursement status toggle button/badge
            let reimbBadgeHtml = '';
            const isClaimable = exp.is_reimbursable !== undefined && exp.is_reimbursable !== null ? exp.is_reimbursable : 1;
            
            if (exp.incurred_by === 'STORE_CASH') {
                reimbBadgeHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-500/20 text-slate-300 border border-slate-500/30">Store Cash</span>`;
            } else if (isClaimable === 0) {
                reimbBadgeHtml = `
                    <button type="button" onclick="zeptoApp.toggleReimbursement('${exp.id}', 0)" title="Non-claimable direct spend (Click to enable reimbursement tracking)" class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800/80 text-slate-400 border border-white/10 hover:bg-slate-700 hover:text-slate-200 transition flex items-center gap-1 mx-auto cursor-pointer">
                        <span>⚪</span> Direct Spend
                    </button>
                `;
            } else if (exp.is_reimbursed === 1) {
                reimbBadgeHtml = `
                    <button type="button" onclick="zeptoApp.toggleReimbursement('${exp.id}', 0)" title="Click to mark as Pending Reimbursement" class="px-2.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-500/30 transition flex items-center gap-1 mx-auto cursor-pointer">
                        <span>✅</span> Settled
                    </button>
                `;
            } else {
                reimbBadgeHtml = `
                    <button type="button" onclick="zeptoApp.toggleReimbursement('${exp.id}', 1)" title="Click to mark as Reimbursed / Settled" class="px-2.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 transition flex items-center gap-1 mx-auto cursor-pointer animate-pulse">
                        <span>⏳</span> Pending Reimb
                    </button>
                `;
            }

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="p-3.5 pl-4 font-bold text-white">${exp.title}</td>
                    <td class="p-3.5">${catBadge}</td>
                    <td class="p-3.5 font-mono text-slate-400 text-[11px]">${exp.expense_date}</td>
                    <td class="p-3.5">
                        <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-white/5 border border-white/10 text-slate-300">
                            ${exp.incurred_by}
                        </span>
                    </td>
                    <td class="p-3.5 text-center">${reimbBadgeHtml}</td>
                    <td class="p-3.5 text-right font-mono font-extrabold text-pink-300 text-sm">
                        ${this.formatCurrency(exp.amount)}
                    </td>
                    <td class="p-3.5 text-center">${proofLink}</td>
                    <td class="p-3.5 text-slate-400 text-[11px] max-w-xs truncate">${exp.notes || '—'}</td>
                    <td class="p-3.5 pr-4 text-center">
                        <button type="button" onclick="zeptoApp.deleteExpense('${exp.id}')" class="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs" title="Delete Expense">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    async toggleReimbursement(expId, targetStatus) {
        try {
            const res = await fetch(`/api/v1/zepto/expenses/${expId}/reimburse`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_reimbursed: targetStatus }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to update reimbursement status');

            await this.loadOverview();
            await this.loadExpenses();
        } catch (err) {
            alert(err.message);
        }
    },

    openAddExpenseModal() {
        document.getElementById('formExpense')?.reset();
        document.getElementById('expFormDate').value = new Date().toISOString().split('T')[0];
        
        const incurredEl = document.getElementById('expFormIncurred');
        const reimbOptEl = document.getElementById('expFormReimbursementOption');
        if (reimbOptEl) reimbOptEl.value = 'PENDING';

        if (incurredEl && reimbOptEl) {
            incurredEl.onchange = (e) => {
                if (e.target.value === 'STORE_CASH') {
                    reimbOptEl.value = 'NONE';
                } else if (reimbOptEl.value === 'NONE') {
                    reimbOptEl.value = 'PENDING';
                }
            };
        }

        this.openModal('modalExpense');
    },

    async saveExpense(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveExpense');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Saving...';
        }

        try {
            let docUrl = null;
            let filename = null;
            const file = document.getElementById('expFormReceiptFile')?.files[0];
            if (file) {
                const uploaded = await this.uploadFile(file);
                docUrl = uploaded.url;
                filename = uploaded.filename;
            }

            const incurredBy = document.getElementById('expFormIncurred').value;
            const reimbOption = document.getElementById('expFormReimbursementOption')?.value || 'PENDING';

            const payload = {
                title: document.getElementById('expFormTitle').value,
                category: document.getElementById('expFormCategory').value,
                amount: parseFloat(document.getElementById('expFormAmount').value || 0),
                expense_date: document.getElementById('expFormDate').value,
                incurred_by: incurredBy,
                reimbursement_option: reimbOption,
                document_url: docUrl,
                document_filename: filename,
                notes: document.getElementById('expFormNotes').value,
            };

            const res = await fetch('/api/v1/zepto/expenses', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to record expense');

            this.closeModal('modalExpense');
            await this.loadOverview();
            await this.loadExpenses();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save Expense';
            }
        }
    },

    async deleteExpense(expId) {
        if (!confirm('Are you sure you want to delete this expense?')) return;
        try {
            const res = await fetch(`/api/v1/zepto/expenses/${expId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed to delete expense');
            await this.loadOverview();
            await this.loadExpenses();
        } catch (err) {
            alert(err.message);
        }
    },

    // -----------------------------------------------------------------------
    // Tab 3: Candidates Pipeline & One-Click Hire
    // -----------------------------------------------------------------------

    async loadCandidates() {
        const stage = document.getElementById('candStageFilter')?.value || 'ALL';
        const role = document.getElementById('candRoleFilter')?.value || 'ALL';
        const search = document.getElementById('candSearchInput')?.value || '';

        try {
            const params = new URLSearchParams();
            if (stage !== 'ALL') params.append('stage', stage);
            if (role !== 'ALL') params.append('target_role', role);
            if (search) params.append('search', search);

            const res = await fetch(`/api/v1/zepto/candidates?${params.toString()}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load candidates');

            this.candidates = data.items || [];
            this.renderCandidates(this.candidates);
        } catch (err) {
            console.error('[ZEPTO] Error loading candidates:', err);
        }
    },

    filterCandidates() {
        this.loadCandidates();
    },

    renderCandidates(items) {
        const tbody = document.getElementById('candidatesTableBody');
        const countBadge = document.getElementById('candCountBadge');
        if (countBadge) countBadge.textContent = `${items.length} Candidates`;
        if (!tbody) return;

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="p-8 text-center text-slate-500">
                        No candidates found in pipeline. Click "Add Candidate" to begin hiring.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = items.map(cand => {
            const roleBadge = this.getRoleBadge(cand.target_role);
            const stageBadge = this.getStageBadge(cand.stage);
            const ratingStars = this.getRatingStars(cand.rating || 4.0);
            const docsHtml = this.getDocsPill(cand.aadhar_doc_url, cand.resume_doc_url);

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="p-3.5 pl-4">
                        <div class="font-bold text-white text-sm">${cand.name}</div>
                        <div class="text-[11px] text-slate-400 font-mono">${cand.phone || 'No phone'} ${cand.email ? '· ' + cand.email : ''}</div>
                    </td>
                    <td class="p-3.5">${roleBadge}</td>
                    <td class="p-3.5 text-center">${stageBadge}</td>
                    <td class="p-3.5 text-center font-mono font-bold text-amber-300">${ratingStars}</td>
                    <td class="p-3.5 text-right font-mono font-bold text-white">
                        ${cand.expected_salary ? this.formatCurrency(cand.expected_salary) : '—'}
                    </td>
                    <td class="p-3.5 text-center">${docsHtml}</td>
                    <td class="p-3.5 text-slate-300 text-[11px] max-w-xs">
                        ${cand.interview_date ? `<div class="font-semibold text-purple-300">Interview: ${cand.interview_date}</div>` : ''}
                        <div class="truncate text-slate-400">${cand.notes || '—'}</div>
                    </td>
                    <td class="p-3.5 pr-4 text-center">
                        <div class="flex items-center justify-center gap-1.5">
                            <button type="button" onclick="zeptoApp.prepareOfferFromCandidate('${cand.id}')" class="px-2 py-1 rounded bg-cyan-950/60 hover:bg-cyan-900 border border-cyan-500/30 text-cyan-300 font-semibold text-[11px] shadow transition flex items-center gap-1" title="Generate customized Offer Letter">
                                <span>📄</span> Offer
                            </button>
                            ${cand.stage !== 'HIRED' ? `
                                <button type="button" onclick="zeptoApp.openConvertCandidateModal('${cand.id}')" class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[11px] shadow transition" title="Hire and transfer to Staff Roster">
                                    ⚡ Hire Staff
                                </button>
                            ` : `
                                <span class="text-[11px] font-bold text-emerald-400 px-2 py-0.5 bg-emerald-500/10 rounded">Hired ✓</span>
                            `}
                            <button type="button" onclick="zeptoApp.deleteCandidate('${cand.id}')" class="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs" title="Delete Candidate">
                                🗑️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    },

    openAddCandidateModal() {
        document.getElementById('formCandidate')?.reset();
        document.getElementById('candFormId').value = '';
        document.getElementById('modalCandidateTitle').innerHTML = '<span>🎯</span> Add Prospective Candidate';

        const roleSelect = document.getElementById('candFormRole');
        const salInput = document.getElementById('candFormSalary');
        if (roleSelect && salInput) {
            salInput.value = this.getBasePayForRole(roleSelect.value || 'PICKER');
            roleSelect.onchange = () => {
                if (!document.getElementById('candFormId')?.value) {
                    salInput.value = this.getBasePayForRole(roleSelect.value);
                }
            };
        }

        this.openModal('modalCandidate');
    },

    async saveCandidate(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveCandidate');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Saving...';
        }

        try {
            let resumeUrl = null;
            let aadharUrl = null;

            const resumeFile = document.getElementById('candFormResumeFile')?.files[0];
            if (resumeFile) {
                const uploaded = await this.uploadFile(resumeFile);
                resumeUrl = uploaded.url;
            }
            const aadharFile = document.getElementById('candFormAadharFile')?.files[0];
            if (aadharFile) {
                const uploaded = await this.uploadFile(aadharFile);
                aadharUrl = uploaded.url;
            }

            const payload = {
                name: document.getElementById('candFormName').value,
                phone: document.getElementById('candFormPhone').value,
                email: document.getElementById('candFormEmail').value,
                target_role: document.getElementById('candFormRole').value,
                stage: document.getElementById('candFormStage').value,
                expected_salary: parseFloat(document.getElementById('candFormSalary').value || 0),
                rating: parseFloat(document.getElementById('candFormRating').value || 4.5),
                resume_doc_url: resumeUrl,
                aadhar_doc_url: aadharUrl,
                notes: document.getElementById('candFormNotes').value,
            };

            const res = await fetch('/api/v1/zepto/candidates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to add candidate');

            this.closeModal('modalCandidate');
            await this.loadOverview();
            await this.loadCandidates();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save Candidate';
            }
        }
    },

    openConvertCandidateModal(candId) {
        const cand = this.candidates.find(c => c.id === candId);
        if (!cand) return;

        document.getElementById('convertCandId').value = cand.id;
        document.getElementById('convertCandName').textContent = cand.name;
        document.getElementById('convertCandMeta').textContent = `Role: ${cand.target_role} · Contact: ${cand.phone || 'N/A'}`;
        document.getElementById('convertJoiningDate').value = new Date().toISOString().split('T')[0];
        document.getElementById('convertStartingSalary').value = cand.expected_salary || 18500;

        this.openModal('modalConvertCandidate');
    },

    async submitConvertCandidate(e) {
        e.preventDefault();
        const candId = document.getElementById('convertCandId').value;
        const btn = document.getElementById('btnSubmitConvert');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Hiring...';
        }

        try {
            const payload = {
                joining_date: document.getElementById('convertJoiningDate').value,
                base_salary: parseFloat(document.getElementById('convertStartingSalary').value || 0),
            };

            const res = await fetch(`/api/v1/zepto/candidates/${candId}/convert`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to convert candidate');

            this.closeModal('modalConvertCandidate');
            alert(`🎉 Candidate successfully converted to Active Employee!`);
            await this.loadOverview();
            await this.loadEmployees();
            await this.loadCandidates();
            this.switchTab('employees');
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Confirm & Hire Staff';
            }
        }
    },

    async deleteCandidate(candId) {
        if (!confirm('Are you sure you want to delete this candidate?')) return;
        try {
            const res = await fetch(`/api/v1/zepto/candidates/${candId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed to delete candidate');
            await this.loadOverview();
            await this.loadCandidates();
        } catch (err) {
            alert(err.message);
        }
    },

    // -----------------------------------------------------------------------
    // Tab 4: Zepto Security & 50-50 Partner Equity
    // -----------------------------------------------------------------------

    async loadSecurity() {
        try {
            const res = await fetch('/api/v1/zepto/security');
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load security ledger');

            this.security = data;
            this.renderSecurity(data);
        } catch (err) {
            console.error('[ZEPTO] Error loading security ledger:', err);
        }
    },

    renderSecurity(data) {
        const sum = data.summary || {};
        const tranches = data.tranches || [];

        if (sum.partner_1 && sum.partner_2) {
            this.populatePartnerDropdowns({
                partners: {
                    partner_1: sum.partner_1,
                    partner_2: sum.partner_2,
                }
            });
        }

        // Total Deposited
        const totalEl = document.getElementById('secTotalDeposited');
        if (totalEl) totalEl.textContent = this.formatCurrency(sum.total_deposited || 0);

        // Partner 1
        const p1 = sum.partner_1 || {};
        const p1PaidEl = document.getElementById('secPartner1Paid');
        if (p1PaidEl) p1PaidEl.textContent = this.formatCurrency(p1.paid || 0);

        const p1PctEl = document.getElementById('secPartner1Pct');
        if (p1PctEl) p1PctEl.textContent = `${p1.progress_pct || 0}%`;

        const p1Bar = document.getElementById('secPartner1Bar');
        if (p1Bar) p1Bar.style.width = `${Math.min(100, p1.progress_pct || 0)}%`;

        const p1RemEl = document.getElementById('secPartner1Remaining');
        if (p1RemEl) p1RemEl.textContent = `${this.formatCurrency(p1.remaining || 0)} Pending`;

        // Partner 2
        const p2 = sum.partner_2 || {};
        const p2PaidEl = document.getElementById('secPartner2Paid');
        if (p2PaidEl) p2PaidEl.textContent = this.formatCurrency(p2.paid || 0);

        const p2PctEl = document.getElementById('secPartner2Pct');
        if (p2PctEl) p2PctEl.textContent = `${p2.progress_pct || 0}%`;

        const p2Bar = document.getElementById('secPartner2Bar');
        if (p2Bar) p2Bar.style.width = `${Math.min(100, p2.progress_pct || 0)}%`;

        const p2RemEl = document.getElementById('secPartner2Remaining');
        if (p2RemEl) p2RemEl.textContent = `${this.formatCurrency(p2.remaining || 0)} Pending`;

        // Equalization Status
        const eqEl = document.getElementById('secEqualizationStatus');
        if (eqEl && sum.equalization) {
            eqEl.textContent = sum.equalization.status;
            eqEl.className = sum.equalization.is_equal ? 'font-mono text-emerald-400 font-bold' : 'font-mono text-amber-300 font-bold';
        }

        const progEl = document.getElementById('secOverallProgressText');
        if (progEl) progEl.textContent = `Total Progress: ${sum.progress_pct || 0}% of ₹75L Target`;

        // Tranches Table
        const countEl = document.getElementById('secTranchesCount');
        if (countEl) countEl.textContent = `${tranches.length} Tranches recorded`;

        const tbody = document.getElementById('securityTableBody');
        if (!tbody) return;

        if (tranches.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center text-slate-500">No capital tranches recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = tranches.map(t => {
            const proofLink = t.proof_doc_url
                ? `<a href="${t.proof_doc_url}" target="_blank" class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold hover:underline">📄 Transfer Slip</a>`
                : `<span class="text-slate-600">—</span>`;

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="p-3.5 pl-4 font-bold text-white">${t.tranche_title}</td>
                    <td class="p-3.5 font-mono text-slate-400 text-[11px]">${t.payment_date}</td>
                    <td class="p-3.5">
                        <span class="px-2.5 py-1 rounded text-xs font-bold ${(t.partner_name.includes('Jatin') || t.partner_name.includes('1')) ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40' : 'bg-pink-500/20 text-pink-300 border border-pink-500/40'}">
                            ${t.partner_name}
                        </span>
                    </td>
                    <td class="p-3.5 font-mono text-[11px]">
                        <div class="text-slate-300 font-semibold">${t.payment_mode || 'NEFT_RTGS'}</div>
                        <div class="text-slate-500 uppercase">${t.reference_utr || 'No UTR'}</div>
                    </td>
                    <td class="p-3.5 text-right font-mono font-extrabold text-amber-300 text-sm">
                        ${this.formatCurrency(t.amount)}
                    </td>
                    <td class="p-3.5 text-center">${proofLink}</td>
                    <td class="p-3.5 text-slate-400 text-[11px] max-w-xs truncate">${t.notes || '—'}</td>
                    <td class="p-3.5 pr-4 text-center">
                        <div class="flex items-center justify-center gap-1.5">
                            <button type="button" onclick="zeptoApp.openEditTrancheModal('${t.id}')" class="px-2 py-1 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-[11px] font-bold flex items-center gap-1 transition" title="Edit Tranche & Transfer Slip (Master Only)">
                                ✏️ Edit
                            </button>
                            <button type="button" onclick="zeptoApp.deleteTranche('${t.id}')" class="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs" title="Delete Tranche (Master Only)">
                                🗑️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    },

    openAddTrancheModal() {
        document.getElementById('formTranche')?.reset();
        document.getElementById('trancheFormId').value = '';
        document.getElementById('modalTrancheTitle').innerHTML = '<span>💰</span> Record Zepto Security Capital Tranche';
        document.getElementById('trancheFormDate').value = new Date().toISOString().split('T')[0];
        
        const proofBox = document.getElementById('trancheCurrentProof');
        if (proofBox) proofBox.style.display = 'none';

        const btn = document.getElementById('btnSaveTranche');
        if (btn) btn.textContent = 'Record Tranche';

        this.openModal('modalTranche');
    },

    openEditTrancheModal(trancheId) {
        const t = this.security?.tranches?.find(x => x.id === trancheId);
        if (!t) return;

        document.getElementById('formTranche')?.reset();
        document.getElementById('trancheFormId').value = t.id;
        document.getElementById('modalTrancheTitle').innerHTML = '<span>✏️</span> Edit Capital Tranche & Transfer Slip';
        document.getElementById('trancheFormTitle').value = t.tranche_title || '';
        document.getElementById('trancheFormAmount').value = t.amount || '';
        document.getElementById('trancheFormDate').value = t.payment_date || new Date().toISOString().split('T')[0];
        document.getElementById('trancheFormPartner').value = t.partner_name || 'Jatin Abrol';
        document.getElementById('trancheFormMode').value = t.payment_mode || 'NEFT_RTGS';
        document.getElementById('trancheFormUtr').value = t.reference_utr || '';
        document.getElementById('trancheFormNotes').value = t.notes || '';

        const proofBox = document.getElementById('trancheCurrentProof');
        const proofLink = document.getElementById('trancheCurrentProofLink');
        if (proofBox && proofLink) {
            if (t.proof_doc_url) {
                proofBox.style.display = 'flex';
                proofLink.href = t.proof_doc_url;
                proofLink.textContent = 'View Current Attached Slip';
            } else {
                proofBox.style.display = 'none';
            }
        }

        const btn = document.getElementById('btnSaveTranche');
        if (btn) btn.textContent = 'Update Tranche';

        this.openModal('modalTranche');
    },

    async saveTranche(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveTranche');
        const trancheId = document.getElementById('trancheFormId')?.value;
        const isEdit = !!trancheId;

        if (btn) {
            btn.disabled = true;
            btn.textContent = isEdit ? 'Updating...' : 'Recording...';
        }

        try {
            let proofUrl = null;
            const file = document.getElementById('trancheFormProofFile')?.files[0];
            if (file) {
                const uploaded = await this.uploadFile(file);
                proofUrl = uploaded.url;
            }

            const payload = {
                tranche_title: document.getElementById('trancheFormTitle').value,
                amount: parseFloat(document.getElementById('trancheFormAmount').value || 0),
                payment_date: document.getElementById('trancheFormDate').value,
                partner_name: document.getElementById('trancheFormPartner').value,
                payment_mode: document.getElementById('trancheFormMode').value,
                reference_utr: document.getElementById('trancheFormUtr').value,
                notes: document.getElementById('trancheFormNotes').value,
            };
            if (proofUrl) {
                payload.proof_doc_url = proofUrl;
            }

            const url = isEdit ? `/api/v1/zepto/security/${trancheId}` : '/api/v1/zepto/security';
            const method = isEdit ? 'PUT' : 'POST';

            const res = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `Failed to ${isEdit ? 'update' : 'record'} tranche`);

            this.closeModal('modalTranche');
            await this.loadOverview();
            await this.loadSecurity();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = isEdit ? 'Update Tranche' : 'Record Tranche';
            }
        }
    },

    async deleteTranche(trancheId) {
        if (!confirm('Are you sure you want to delete this capital payment tranche? (Master Portal Admin only)')) return;
        try {
            const res = await fetch(`/api/v1/zepto/security/${trancheId}`, { method: 'DELETE' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to delete capital tranche');

            await this.loadOverview();
            await this.loadSecurity();
        } catch (err) {
            alert(err.message);
        }
    },

    // -----------------------------------------------------------------------
    // Shared Helpers & Document Uploader
    // -----------------------------------------------------------------------

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch('/api/v1/zepto/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'File upload failed');
        return data;
    },

    openModal(modalId) {
        const el = document.getElementById(modalId);
        if (el) el.style.display = 'flex';
    },

    closeModal(modalId) {
        const el = document.getElementById(modalId);
        if (el) el.style.display = 'none';
    },

    formatCurrency(val) {
        const n = parseFloat(val || 0);
        return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
    },

    getRoleBadge(role) {
        const map = {
            'PICKER': { label: '🛒 Picker', class: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
            'SHIFT_INCHARGE': { label: '⚡ Shift Incharge', class: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40' },
            'SECURITY_GUARD': { label: '🛡️ Security Guard', class: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
            'HOUSEKEEPING': { label: '🧹 House Keeping', class: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
        };
        const r = map[role] || { label: role, class: 'bg-slate-500/20 text-slate-300 border-slate-500/40' };
        return `<span class="px-2 py-0.5 rounded text-[11px] font-bold border ${r.class}">${r.label}</span>`;
    },

    getStatusBadge(status) {
        if (status === 'ACTIVE') return `<span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">🟢 Active</span>`;
        if (status === 'ON_PROBATION') return `<span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-500/15 text-amber-300 border border-amber-500/30">🟡 Probation</span>`;
        return `<span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-rose-500/15 text-rose-400 border border-rose-500/30">🔴 Resigned</span>`;
    },

    getStageBadge(stage) {
        const map = {
            'APPLIED': 'bg-blue-500/15 text-blue-300 border-blue-500/30',
            'INTERVIEWING': 'bg-purple-500/15 text-purple-300 border-purple-500/30',
            'SHORTLISTED': 'bg-amber-500/15 text-amber-300 border-amber-500/30',
            'OFFERED': 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30',
            'HIRED': 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
            'REJECTED': 'bg-rose-500/15 text-rose-400 border-rose-500/30',
        };
        const cls = map[stage] || 'bg-slate-500/15 text-slate-300 border-slate-500/30';
        return `<span class="px-2 py-0.5 rounded text-[10px] font-extrabold border ${cls}">${stage}</span>`;
    },

    getCategoryBadge(cat) {
        const map = {
            'TRAINING': { label: '🎓 Training', class: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
            'UNIFORMS_GEAR': { label: '👕 Uniforms', class: 'bg-pink-500/20 text-pink-300 border-pink-500/40' },
            'EQUIPMENT': { label: '🏗️ Equipment', class: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40' },
            'SNACKS_WELFARE': { label: '☕ Snacks', class: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
            'STORE_MAINTENANCE': { label: '🧹 Maintenance', class: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
            'OPERATIONAL': { label: '📦 Operational', class: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
        };
        const c = map[cat] || { label: cat, class: 'bg-slate-500/20 text-slate-300 border-slate-500/40' };
        return `<span class="px-2 py-0.5 rounded text-[11px] font-bold border ${c.class}">${c.label}</span>`;
    },

    getRatingStars(rating) {
        const r = parseFloat(rating || 5.0);
        return `⭐ ${r.toFixed(1)}`;
    },

    getDocsPill(aadharUrl, resumeUrl) {
        const pills = [];
        if (aadharUrl) {
            pills.push(`<a href="${aadharUrl}" target="_blank" class="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 text-[10px] font-bold border border-blue-500/30 hover:underline" title="View Aadhar Card">🪪 Aadhar</a>`);
        }
        if (resumeUrl) {
            pills.push(`<a href="${resumeUrl}" target="_blank" class="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px] font-bold border border-purple-500/30 hover:underline" title="View Resume">📄 CV</a>`);
        }
        return pills.length > 0 ? `<div class="flex items-center justify-center gap-1">${pills.join('')}</div>` : `<span class="text-slate-600">—</span>`;
    },

    getIncomeSourceBadge(source) {
        const map = {
            'COMMISSION': { label: '🛍️ Order Commission', class: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
            'GROWTH_INCENTIVE': { label: '🚀 SLA & Growth', class: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
            'ORDER_SLOTTING': { label: '🏷️ Brand Slotting', class: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
            'DELIVERY_SURCHARGE': { label: '⚡ Delivery Margin', class: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
            'MISC': { label: '💵 Operational / Misc', class: 'bg-pink-500/20 text-pink-300 border-pink-500/40' },
        };
        const s = map[source] || { label: source, class: 'bg-slate-500/20 text-slate-300 border-slate-500/40' };
        return `<span class="px-2 py-0.5 rounded text-[11px] font-bold border ${s.class}">${s.label}</span>`;
    },

    // -----------------------------------------------------------------------
    // Tab: Store Income & Customizable Partner Profit Split
    // -----------------------------------------------------------------------

    async loadIncome() {
        const ym = document.getElementById('incMonthFilter')?.value || 'ALL';
        const src = document.getElementById('incSourceFilter')?.value || 'ALL';
        const search = document.getElementById('incSearchInput')?.value || '';

        try {
            const params = new URLSearchParams();
            if (ym && ym !== 'ALL') params.append('year_month', ym);
            if (src && src !== 'ALL') params.append('income_source', src);
            if (search.trim()) params.append('search', search.trim());

            const res = await fetch(`/api/v1/zepto/income?${params.toString()}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load store income');

            this.income = data.items || [];
            this.renderIncome(data);
        } catch (err) {
            console.error('[ZEPTO] Error loading store income:', err);
        }
    },

    filterIncome() {
        this.loadIncome();
    },

    resetIncomeFilters() {
        const ym = document.getElementById('incMonthFilter');
        const src = document.getElementById('incSourceFilter');
        const search = document.getElementById('incSearchInput');
        if (ym) ym.value = 'ALL';
        if (src) src.value = 'ALL';
        if (search) search.value = '';
        this.loadIncome();
    },

    renderIncome(data) {
        const items = data.items || [];
        const split = data.split_settings || { partner_1_share_pct: 50.0, partner_2_share_pct: 50.0, partner_1_name: 'Jatin Abrol', partner_2_name: 'Harshiv Bargotra' };
        const overviewInc = data.overview_income || {};

        // Top KPIs
        const totalNetEl = document.getElementById('incTotalNet');
        if (totalNetEl) totalNetEl.textContent = this.formatCurrency(data.total_net || 0);

        const totalGrossEl = document.getElementById('incTotalGross');
        if (totalGrossEl) totalGrossEl.textContent = this.formatCurrency(data.total_gross || 0);

        const totalDeductionsEl = document.getElementById('incTotalDeductions');
        if (totalDeductionsEl) totalDeductionsEl.textContent = this.formatCurrency(data.total_deductions || 0);

        const countBadge = document.getElementById('incCountBadge');
        if (countBadge) countBadge.textContent = `${items.length} Records`;

        const rateEl = document.getElementById('incRealizationRate');
        if (rateEl) {
            const gross = data.total_gross || 0;
            const net = data.total_net || 0;
            const rate = gross > 0 ? Math.round((net / gross) * 100) : 100;
            rateEl.textContent = `${rate}% Realized`;
        }

        // Partner 1 Share
        const p1TotalEl = document.getElementById('incPartner1Total');
        if (p1TotalEl) p1TotalEl.textContent = this.formatCurrency(data.partner_1_total || 0);
        const p1PctBadge = document.getElementById('incPartner1PctBadge');
        if (p1PctBadge) p1PctBadge.textContent = `${split.partner_1_share_pct || 50.0}% Share`;

        // Partner 2 Share
        const p2TotalEl = document.getElementById('incPartner2Total');
        if (p2TotalEl) p2TotalEl.textContent = this.formatCurrency(data.partner_2_total || 0);
        const p2PctBadge = document.getElementById('incPartner2PctBadge');
        if (p2PctBadge) p2PctBadge.textContent = `${split.partner_2_share_pct || 50.0}% Share`;

        // Split Bar
        const splitBarLabel1 = document.getElementById('splitBarLabel1');
        if (splitBarLabel1) splitBarLabel1.textContent = `${split.partner_1_name || 'Jatin'}: ${split.partner_1_share_pct}%`;
        const splitBarLabel2 = document.getElementById('splitBarLabel2');
        if (splitBarLabel2) splitBarLabel2.textContent = `${split.partner_2_name || 'Harshiv'}: ${split.partner_2_share_pct}%`;

        const splitBarP1 = document.getElementById('incSplitBarP1');
        const splitBarP2 = document.getElementById('incSplitBarP2');
        if (splitBarP1) splitBarP1.style.width = `${split.partner_1_share_pct}%`;
        if (splitBarP2) splitBarP2.style.width = `${split.partner_2_share_pct}%`;

        const currentSplitLabel = document.getElementById('btnCurrentSplitLabel');
        if (currentSplitLabel) currentSplitLabel.textContent = `${split.partner_1_share_pct?.toFixed(0)}-${split.partner_2_share_pct?.toFixed(0)}`;

        // Source Distribution Tiles
        const srcBreakdown = overviewInc.source_breakdown || {};
        ['COMMISSION', 'GROWTH_INCENTIVE', 'ORDER_SLOTTING', 'DELIVERY_SURCHARGE', 'MISC'].forEach(src => {
            const el = document.getElementById(`srcTotal-${src}`);
            if (el) el.textContent = this.formatCurrency(srcBreakdown[src] || 0);
        });

        // Table Body
        const tbody = document.getElementById('incomeTableBody');
        const tableBadge = document.getElementById('incTableCountBadge');
        if (tableBadge) tableBadge.textContent = `${items.length} Records`;
        if (!tbody) return;

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="p-8 text-center text-slate-500">
                        No store income records found matching criteria. Click "Record Store Income" to log a settlement.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = items.map(inc => {
            const srcBadge = this.getIncomeSourceBadge(inc.income_source);
            const proofHtml = inc.proof_doc_url
                ? `<a href="${inc.proof_doc_url}" target="_blank" class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-bold border border-emerald-500/30 hover:underline" title="View Settlement Invoice">📄 Proof</a>`
                : `<span class="text-slate-600">—</span>`;

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="p-3 pl-3.5">
                        <div class="font-bold text-white text-xs">${inc.title}</div>
                        <div class="mt-1">${srcBadge}</div>
                        ${inc.notes ? `<div class="text-[10px] text-slate-400 mt-0.5 italic truncate max-w-xs">${inc.notes}</div>` : ''}
                    </td>
                    <td class="p-3 text-slate-300 text-[11px] whitespace-nowrap">
                        <div class="font-mono">${inc.income_date}</div>
                        <span class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-white/5 border border-white/10 text-slate-400 font-mono">
                            ${inc.year_month}
                        </span>
                    </td>
                    <td class="p-3 text-right font-mono font-bold text-slate-200">${this.formatCurrency(inc.gross_amount)}</td>
                    <td class="p-3 text-right font-mono text-rose-400 font-bold">
                        ${inc.deductions > 0 ? '-' + this.formatCurrency(inc.deductions) : '₹0'}
                    </td>
                    <td class="p-3 text-right font-mono font-black text-emerald-400 text-sm">${this.formatCurrency(inc.net_amount)}</td>
                    <td class="p-3 text-right font-mono">
                        <div class="font-bold text-purple-300">${this.formatCurrency(inc.partner_1_share_amount)}</div>
                        <span class="text-[10px] text-purple-400/80">(${inc.partner_1_share_pct}%)</span>
                    </td>
                    <td class="p-3 text-right font-mono">
                        <div class="font-bold text-pink-300">${this.formatCurrency(inc.partner_2_share_amount)}</div>
                        <span class="text-[10px] text-pink-400/80">(${inc.partner_2_share_pct}%)</span>
                    </td>
                    <td class="p-3 text-[11px] text-slate-300 font-mono">
                        <div>${inc.reference_utr || '—'}</div>
                        <div class="text-[10px] text-slate-500 uppercase">${inc.payment_mode || 'BANK_TRANSFER'}</div>
                    </td>
                    <td class="p-3 text-center">${proofHtml}</td>
                    <td class="p-3 pr-3.5 text-center whitespace-nowrap">
                        <div class="flex items-center justify-center gap-1.5">
                            <button type="button" onclick="zeptoApp.openEditIncomeModal('${inc.id}')" class="p-1.5 rounded bg-white/5 hover:bg-white/10 text-slate-300 text-xs" title="Edit Income Record">
                                ✏️
                            </button>
                            <button type="button" onclick="zeptoApp.deleteIncome('${inc.id}')" class="p-1.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs" title="Delete Income Record">
                                🗑️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    },

    openAddIncomeModal() {
        document.getElementById('formIncome')?.reset();
        document.getElementById('incFormId').value = '';
        document.getElementById('modalIncomeTitle').innerHTML = '<span>💵</span> Record Store Income Payment';
        document.getElementById('incFormDate').value = new Date().toISOString().split('T')[0];

        // Fetch current default split settings
        const defaultP1 = this.overview?.income?.partner_1?.share_pct || 50.0;
        const defaultP2 = this.overview?.income?.partner_2?.share_pct || 50.0;

        document.getElementById('incFormP1Pct').value = defaultP1;
        document.getElementById('incFormP2Pct').value = defaultP2;
        this.calculateIncomeNetAndSplit();

        this.openModal('modalIncome');
    },

    async openEditIncomeModal(incomeId) {
        try {
            const res = await fetch(`/api/v1/zepto/income/${incomeId}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to fetch income record');

            const inc = data.income;
            document.getElementById('incFormId').value = inc.id;
            document.getElementById('incFormTitle').value = inc.title;
            document.getElementById('incFormSource').value = inc.income_source;
            document.getElementById('incFormDate').value = inc.income_date;
            document.getElementById('incFormGross').value = inc.gross_amount;
            document.getElementById('incFormDeductions').value = inc.deductions || 0;
            document.getElementById('incFormP1Pct').value = inc.partner_1_share_pct || 50.0;
            document.getElementById('incFormP2Pct').value = inc.partner_2_share_pct || 50.0;
            document.getElementById('incFormPaymentMode').value = inc.payment_mode || 'BANK_TRANSFER';
            document.getElementById('incFormUtr').value = inc.reference_utr || '';
            document.getElementById('incFormProofUrl').value = inc.proof_doc_url || '';
            document.getElementById('incFormNotes').value = inc.notes || '';

            this.calculateIncomeNetAndSplit();
            document.getElementById('modalIncomeTitle').innerHTML = `<span>✏️</span> Edit Store Income: ${inc.title}`;
            this.openModal('modalIncome');
        } catch (err) {
            alert(err.message);
        }
    },

    calculateIncomeNetAndSplit() {
        const gross = parseFloat(document.getElementById('incFormGross')?.value || 0);
        const deductions = parseFloat(document.getElementById('incFormDeductions')?.value || 0);
        const net = Math.max(0, gross - deductions);

        const netEl = document.getElementById('incFormNet');
        if (netEl) netEl.value = net.toFixed(2);

        const p1Pct = parseFloat(document.getElementById('incFormP1Pct')?.value || 50);
        const p2Pct = parseFloat(document.getElementById('incFormP2Pct')?.value || 50);

        const p1Amt = Math.round(net * (p1Pct / 100));
        const p2Amt = Math.round(net - p1Amt);

        const p1Label = document.getElementById('incModalP1PctLabel');
        if (p1Label) p1Label.textContent = `${p1Pct}%`;
        const p2Label = document.getElementById('incModalP2PctLabel');
        if (p2Label) p2Label.textContent = `${p2Pct}%`;

        const p1AmtEl = document.getElementById('incModalP1Amt');
        if (p1AmtEl) p1AmtEl.textContent = this.formatCurrency(p1Amt);
        const p2AmtEl = document.getElementById('incModalP2Amt');
        if (p2AmtEl) p2AmtEl.textContent = this.formatCurrency(p2Amt);
    },

    onFormP1PctChange(val) {
        const p1 = Math.min(100, Math.max(0, parseFloat(val || 0)));
        const p2 = Math.round((100 - p1) * 10) / 10;
        document.getElementById('incFormP2Pct').value = p2;
        this.calculateIncomeNetAndSplit();
    },

    onFormP2PctChange(val) {
        const p2 = Math.min(100, Math.max(0, parseFloat(val || 0)));
        const p1 = Math.round((100 - p2) * 10) / 10;
        document.getElementById('incFormP1Pct').value = p1;
        this.calculateIncomeNetAndSplit();
    },

    async saveIncome(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveIncome');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Saving Income...';
        }

        try {
            const incId = document.getElementById('incFormId').value;
            let proofUrl = document.getElementById('incFormProofUrl').value;

            // Upload proof file if selected
            const proofFile = document.getElementById('incFormProofFile')?.files[0];
            if (proofFile) {
                const uploaded = await this.uploadFile(proofFile);
                proofUrl = uploaded.url;
            }

            const gross = parseFloat(document.getElementById('incFormGross').value || 0);
            const deductions = parseFloat(document.getElementById('incFormDeductions').value || 0);
            const dateVal = document.getElementById('incFormDate').value;
            const ym = dateVal ? dateVal.slice(0, 7) : new Date().toISOString().slice(0, 7);

            const payload = {
                title: document.getElementById('incFormTitle').value,
                income_source: document.getElementById('incFormSource').value,
                income_date: dateVal,
                year_month: ym,
                gross_amount: gross,
                deductions: deductions,
                partner_1_share_pct: parseFloat(document.getElementById('incFormP1Pct').value || 50),
                partner_2_share_pct: parseFloat(document.getElementById('incFormP2Pct').value || 50),
                payment_mode: document.getElementById('incFormPaymentMode').value,
                reference_utr: document.getElementById('incFormUtr').value,
                proof_doc_url: proofUrl || null,
                notes: document.getElementById('incFormNotes').value,
            };

            const url = incId ? `/api/v1/zepto/income/${incId}` : '/api/v1/zepto/income';
            const method = incId ? 'PUT' : 'POST';

            const res = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to save store income');

            this.closeModal('modalIncome');
            await this.loadOverview();
            await this.loadIncome();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save Income Record';
            }
        }
    },

    async deleteIncome(incomeId) {
        if (!confirm('Are you sure you want to delete this store income record?')) return;
        try {
            const res = await fetch(`/api/v1/zepto/income/${incomeId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed to delete income record');
            await this.loadOverview();
            await this.loadIncome();
        } catch (err) {
            alert(err.message);
        }
    },

    // -----------------------------------------------------------------------
    // Customizable Partner Profit Split Settings
    // -----------------------------------------------------------------------

    async openIncomeSplitModal() {
        try {
            const res = await fetch('/api/v1/zepto/income-split-settings');
            const data = await res.json();
            const split = data.settings || { partner_1_share_pct: 50.0, partner_2_share_pct: 50.0 };

            this.setSplitPreset(split.partner_1_share_pct, split.partner_2_share_pct);
            this.openModal('modalIncomeSplitSettings');
        } catch (err) {
            this.setSplitPreset(50, 50);
            this.openModal('modalIncomeSplitSettings');
        }
    },

    setSplitPreset(p1, p2) {
        document.getElementById('splitInputP1').value = p1;
        document.getElementById('splitInputP2').value = p2;
        document.getElementById('splitModalSlider').value = p1;
        this.updateSplitVisuals(p1, p2);
    },

    onSplitSliderChange(val) {
        const p1 = parseFloat(val);
        const p2 = Math.round((100 - p1) * 10) / 10;
        document.getElementById('splitInputP1').value = p1;
        document.getElementById('splitInputP2').value = p2;
        this.updateSplitVisuals(p1, p2);
    },

    onSplitInputP1Change(val) {
        const p1 = Math.min(100, Math.max(0, parseFloat(val || 0)));
        const p2 = Math.round((100 - p1) * 10) / 10;
        document.getElementById('splitInputP2').value = p2;
        document.getElementById('splitModalSlider').value = p1;
        this.updateSplitVisuals(p1, p2);
    },

    onSplitInputP2Change(val) {
        const p2 = Math.min(100, Math.max(0, parseFloat(val || 0)));
        const p1 = Math.round((100 - p2) * 10) / 10;
        document.getElementById('splitInputP1').value = p1;
        document.getElementById('splitModalSlider').value = p1;
        this.updateSplitVisuals(p1, p2);
    },

    updateSplitVisuals(p1, p2) {
        const p1Display = document.getElementById('splitModalP1Display');
        const p2Display = document.getElementById('splitModalP2Display');
        if (p1Display) p1Display.textContent = `${p1.toFixed(1)}%`;
        if (p2Display) p2Display.textContent = `${p2.toFixed(1)}%`;

        const barP1 = document.getElementById('splitModalBarP1');
        const barP2 = document.getElementById('splitModalBarP2');
        if (barP1) barP1.style.width = `${p1}%`;
        if (barP2) barP2.style.width = `${p2}%`;
    },

    async saveIncomeSplitSettings(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveSplitSettings');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Applying...';
        }

        try {
            const p1 = parseFloat(document.getElementById('splitInputP1').value || 50);
            const p2 = parseFloat(document.getElementById('splitInputP2').value || 50);

            const res = await fetch('/api/v1/zepto/income-split-settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    partner_1_share_pct: p1,
                    partner_2_share_pct: p2,
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to update profit split');

            this.closeModal('modalIncomeSplitSettings');
            await this.loadOverview();
            await this.loadIncome();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Apply Split Ratio';
            }
        }
    },

    // -----------------------------------------------------------------------
    // Tab: Dark Store Attendance & Shift Muster Analytics
    // -----------------------------------------------------------------------

    async loadAttendanceData() {
        const attFilter = document.getElementById('attMonthFilter');
        let ym = '';
        if (this.currentGlobalMonth && this.currentGlobalMonth !== 'ALL') {
            ym = this.currentGlobalMonth;
            if (attFilter && Array.from(attFilter.options).some(o => o.value === ym)) {
                attFilter.value = ym;
            }
        } else {
            const filterVal = attFilter?.value || 'ALL';
            if (filterVal === 'CURRENT') {
                const now = new Date();
                ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
            } else if (filterVal !== 'ALL') {
                ym = filterVal;
            }
        }

        try {
            const summaryParams = new URLSearchParams();
            if (ym) summaryParams.append('year_month', ym);

            const recParams = new URLSearchParams();
            if (ym) recParams.append('year_month', ym);
            recParams.append('limit', '1000');

            let [sumRes, recRes] = await Promise.all([
                fetch(`/api/v1/zepto/attendance/summary?${summaryParams.toString()}`),
                fetch(`/api/v1/zepto/attendance/records?${recParams.toString()}`),
            ]);

            if (sumRes.ok) {
                let sumData = await sumRes.json();
                if (sumData.available_months && Array.isArray(sumData.available_months)) {
                    this.updateAvailableMonths(sumData.available_months);
                }

                // If no shifts in the current/selected month and global scope is ALL, fallback to all records
                if ((sumData.total_shifts_scheduled === 0 || !sumData.total_shifts_scheduled) && ym && this.currentGlobalMonth === 'ALL') {
                    const [sumAllRes, recAllRes] = await Promise.all([
                        fetch('/api/v1/zepto/attendance/summary'),
                        fetch('/api/v1/zepto/attendance/records?limit=1000'),
                    ]);
                    if (sumAllRes.ok) {
                        sumData = await sumAllRes.json();
                        if (recAllRes.ok) {
                            const recAllData = await recAllRes.json();
                            this.attendance.records = recAllData.records || [];
                            this.attendance.filtered = [...this.attendance.records];
                        }
                    }
                } else if (recRes.ok) {
                    const recData = await recRes.json();
                    this.attendance.records = recData.records || [];
                    this.attendance.filtered = [...this.attendance.records];
                }

                this.attendance.summary = sumData;
                this.attendance.staff_roster = sumData.staff_roster || [];
                this.attendance.filtered_staff = [...this.attendance.staff_roster];
            }

            this.renderAttendance();
        } catch (err) {
            console.error('[ZEPTO-ATTENDANCE] Error loading attendance data:', err);
        }
    },

    renderAttendance() {
        const sum = this.attendance.summary || {};
        const records = this.attendance.filtered || [];

        // Title and store name
        const titleEl = document.getElementById('attStoreTitle');
        if (titleEl) {
            titleEl.textContent = sum.store_name ? `${sum.store_name} Attendance` : 'Zepto Dark Store Attendance';
        }

        const dateRangeEl = document.getElementById('attDateRangeBadge');
        if (dateRangeEl) {
            if (sum.period && sum.period.start && sum.period.end) {
                dateRangeEl.textContent = `${sum.period.start} to ${sum.period.end}`;
            } else {
                dateRangeEl.textContent = 'All Records';
            }
        }

        // 1. Attendance Rate
        const rateValEl = document.getElementById('attRateValue');
        const rateBadgeEl = document.getElementById('attRateBadge');
        const rateBarEl = document.getElementById('attRateBar');
        const presentCountEl = document.getElementById('attPresentCount');

        const rate = sum.attendance_rate_pct != null ? sum.attendance_rate_pct : 0.0;
        if (rateValEl) rateValEl.textContent = `${rate.toFixed(1)}%`;
        if (rateBadgeEl) rateBadgeEl.textContent = `${rate.toFixed(1)}% Rate`;
        if (rateBarEl) rateBarEl.style.width = `${Math.min(100, rate)}%`;
        if (presentCountEl) {
            const pCount = sum.status_distribution?.PRESENT || 0;
            presentCountEl.textContent = `${pCount} Shifts`;
        }

        // 2. Active Staff Headcount & Shifts
        const hcEl = document.getElementById('attHeadcount');
        const totalShiftsEl = document.getElementById('attTotalShifts');
        const shiftsBadgeEl = document.getElementById('attShiftsBadge');

        if (hcEl) hcEl.textContent = sum.headcount != null ? sum.headcount : '--';
        if (totalShiftsEl) totalShiftsEl.textContent = `${sum.total_shifts_scheduled || 0} Shifts`;
        if (shiftsBadgeEl) shiftsBadgeEl.textContent = `${sum.total_shifts_scheduled || 0} Scheduled`;

        // 3. Absenteeism
        const absentCountEl = document.getElementById('attAbsentCount');
        const absentBadgeEl = document.getElementById('attAbsentBadge');
        const halfDayEl = document.getElementById('attHalfDayCount');
        const weekOffEl = document.getElementById('attWeekOffCount');
        const holidayEl = document.getElementById('attHolidayCount');

        const absCount = sum.status_distribution?.ABSENT || 0;
        if (absentCountEl) absentCountEl.textContent = absCount;
        if (absentBadgeEl) absentBadgeEl.textContent = `${absCount} Absences`;
        if (halfDayEl) halfDayEl.textContent = sum.status_distribution?.HALF_DAY || 0;
        if (weekOffEl) weekOffEl.textContent = sum.status_distribution?.WEEK_OFF || 0;
        if (holidayEl) holidayEl.textContent = sum.status_distribution?.HOLIDAY || 0;

        // 4. Man-Hours
        const totalHoursEl = document.getElementById('attTotalHours');
        const avgHoursSubEl = document.getElementById('attAvgHoursSub');
        if (totalHoursEl) {
            totalHoursEl.textContent = `${sum.total_hours_worked || 0} hrs`;
        }
        if (avgHoursSubEl && sum.total_shifts_scheduled > 0) {
            const avg = ((sum.total_hours_worked || 0) / sum.total_shifts_scheduled).toFixed(1);
            avgHoursSubEl.textContent = `Avg ~${avg} hrs / shift`;
        }

        // Role Breakdown Grid & Role Filter Dropdown
        this.renderAttendanceRoles(sum.role_breakdown || []);

        // 5. Operational Capacity & Throughput Cards
        this.renderAttendanceCapacity(sum.role_capacity_summary || {});

        // 6. Daily Staffing Timeline & Heatmap
        this.renderAttendanceTimeline(sum.daily_trend || []);

        // 7. Absenteeism & Churn Risk Watchlist
        this.renderAttendanceWatchlist(sum.absenteeism_watchlist || []);

        // Muster Records Table
        this.renderAttendanceTable();
    },

    renderAttendanceCapacity(cap) {
        // Packers
        const p = cap.packers || { scheduled: 0, present: 0, absent: 0, rate: 0, health: 'OPTIMAL' };
        const pPresEl = document.getElementById('attCapPackersPresent');
        const pTotEl = document.getElementById('attCapPackersTotal');
        const pAbsEl = document.getElementById('attCapPackersAbsent');
        const pBarEl = document.getElementById('attCapPackersBar');
        const pBadgeEl = document.getElementById('attCapPackersBadge');

        if (pPresEl) pPresEl.textContent = p.present;
        if (pTotEl) pTotEl.textContent = ` / ${p.scheduled} shifts (${p.headcount || 0} Staff)`;
        if (pAbsEl) pAbsEl.textContent = `${p.absent} Absences`;
        if (pBarEl) pBarEl.style.width = `${Math.min(100, p.rate)}%`;
        if (pBadgeEl) {
            pBadgeEl.textContent = `${p.rate}% Adherence · ${p.health}`;
            pBadgeEl.className = p.health === 'ALERT'
                ? 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 font-mono animate-pulse'
                : (p.health === 'WARNING'
                    ? 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono'
                    : 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-mono');
        }

        // Leadership
        const l = cap.leadership || { scheduled: 0, present: 0, absent: 0, rate: 0, health: 'OPTIMAL' };
        const lPresEl = document.getElementById('attCapLeadPresent');
        const lTotEl = document.getElementById('attCapLeadTotal');
        const lAbsEl = document.getElementById('attCapLeadAbsent');
        const lBarEl = document.getElementById('attCapLeadBar');
        const lBadgeEl = document.getElementById('attCapLeadBadge');

        if (lPresEl) lPresEl.textContent = l.present;
        if (lTotEl) lTotEl.textContent = ` / ${l.scheduled} shifts (${l.headcount || 0} Leads)`;
        if (lAbsEl) lAbsEl.textContent = `${l.absent} Absences`;
        if (lBarEl) lBarEl.style.width = `${Math.min(100, l.rate)}%`;
        if (lBadgeEl) {
            lBadgeEl.textContent = `${l.rate}% Adherence · ${l.health}`;
            lBadgeEl.className = l.health === 'ALERT'
                ? 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 font-mono'
                : 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-mono';
        }

        // Inbound / QA / NSO
        const i = cap.inbound_quality_nso || { scheduled: 0, present: 0, absent: 0, rate: 0, health: 'OPTIMAL' };
        const iPresEl = document.getElementById('attCapInboundPresent');
        const iTotEl = document.getElementById('attCapInboundTotal');
        const iAbsEl = document.getElementById('attCapInboundAbsent');
        const iBarEl = document.getElementById('attCapInboundBar');
        const iBadgeEl = document.getElementById('attCapInboundBadge');

        if (iPresEl) iPresEl.textContent = i.present;
        if (iTotEl) iTotEl.textContent = ` / ${i.scheduled} shifts (${i.headcount || 0} Staff)`;
        if (iAbsEl) iAbsEl.textContent = `${i.absent} Absences`;
        if (iBarEl) iBarEl.style.width = `${Math.min(100, i.rate)}%`;
        if (iBadgeEl) {
            iBadgeEl.textContent = `${i.rate}% Adherence · ${i.health}`;
            iBadgeEl.className = i.health === 'ALERT'
                ? 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 font-mono'
                : 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-mono';
        }
    },

    renderAttendanceTimeline(trend) {
        const container = document.getElementById('attDailyTimelineContainer');
        if (!container) return;

        if (!trend || trend.length === 0) {
            container.innerHTML = `<div class="text-xs text-slate-500 text-center w-full py-8">No daily timeline records.</div>`;
            return;
        }

        const maxScheduled = Math.max(...trend.map(d => d.scheduled || 1), 15);

        container.innerHTML = trend.map(d => {
            const scheduled = d.scheduled || 0;
            const present = d.present || 0;
            const absent = d.absent || 0;
            const weekOff = d.week_off || 0;
            const holiday = d.holiday || 0;

            const totalHeightPct = Math.min(100, Math.max(15, (scheduled / maxScheduled) * 100));
            const dayLabel = (d.date || '').slice(8, 10);
            const monthLabel = (d.date || '').slice(5, 7);

            const pPct = scheduled > 0 ? (present / scheduled) * 100 : 0;
            const aPct = scheduled > 0 ? (absent / scheduled) * 100 : 0;
            const wPct = scheduled > 0 ? (weekOff / scheduled) * 100 : 0;
            const hPct = scheduled > 0 ? (holiday / scheduled) * 100 : 0;

            const isLowAttendance = scheduled >= 5 && (present / scheduled) < 0.6;
            const borderHighlight = isLowAttendance ? 'border-b-2 border-b-rose-500' : '';

            return `
                <div
                    class="flex-1 flex flex-col items-center justify-end h-full group cursor-pointer ${borderHighlight}"
                    onclick="zeptoApp.filterByDate('${d.date}')"
                    title="${d.date}: ${present} Present, ${absent} Absent, ${weekOff} Week Off (${scheduled} Total)"
                >
                    <!-- Bar Stack Container -->
                    <div class="w-full max-w-[28px] bg-black/40 rounded-t overflow-hidden flex flex-col-reverse transition-all duration-300 group-hover:brightness-125" style="height: ${totalHeightPct}%;">
                        <div class="bg-emerald-500/80 w-full" style="height: ${pPct}%;"></div>
                        <div class="bg-rose-500/80 w-full" style="height: ${aPct}%;"></div>
                        <div class="bg-slate-600/80 w-full" style="height: ${wPct}%;"></div>
                        <div class="bg-sky-500/80 w-full" style="height: ${hPct}%;"></div>
                    </div>
                    <!-- Date Label -->
                    <div class="text-[9px] font-mono font-bold text-slate-400 mt-1.5 group-hover:text-white">
                        ${dayLabel}/${monthLabel}
                    </div>
                </div>
            `;
        }).join('');
    },

    filterByDate(dateStr) {
        const dateInput = document.getElementById('attDateFilter');
        if (dateInput) {
            dateInput.value = dateStr;
            this.filterAttendance();
            this.showToast(`📅 Filtered attendance ledger to ${dateStr}`);
        }
    },

    renderAttendanceWatchlist(watchlist) {
        const tbody = document.getElementById('attWatchlistTableBody');
        const countBadge = document.getElementById('attWatchlistCount');

        if (countBadge) {
            const count = watchlist ? watchlist.length : 0;
            countBadge.textContent = `${count} Flagged`;
            countBadge.className = count > 0
                ? 'text-[10px] font-bold px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 font-mono animate-pulse'
                : 'text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/25 font-mono';
        }

        if (!tbody) return;
        if (!watchlist || watchlist.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-6 text-emerald-400 text-xs font-semibold">
                        ✨ 100% Roster Reliability · No chronic absenteeism flagged!
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = watchlist.map(w => {
            const riskBadge = w.risk_tier === 'CRITICAL'
                ? '<span class="px-2 py-0.5 rounded text-[9px] font-extrabold bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse">CRITICAL</span>'
                : (w.risk_tier === 'HIGH'
                    ? '<span class="px-2 py-0.5 rounded text-[9px] font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/40">HIGH RISK</span>'
                    : '<span class="px-2 py-0.5 rounded text-[9px] font-extrabold bg-slate-500/20 text-slate-300 border border-white/10">MODERATE</span>');

            return `
                <tr class="hover:bg-rose-500/[0.04] transition cursor-pointer" onclick="zeptoApp.openEmployeeDrawer('${w.employee_id}')" title="Click to view full 30-day drilldown for ${w.employee_name}">
                    <td class="py-2 px-2.5">
                        <div class="font-bold text-white text-xs">${w.employee_name}</div>
                        <div class="text-[9px] font-mono text-slate-500">${w.employee_id}</div>
                    </td>
                    <td class="py-2 px-2.5 text-[10px] text-slate-300">
                        ${w.designation}
                    </td>
                    <td class="py-2 px-2.5 text-center font-mono font-extrabold text-rose-400">
                        ${w.absent_count} / ${w.total_shifts}
                    </td>
                    <td class="py-2 px-2.5 text-center font-mono font-bold ${w.attendance_rate_pct < 50 ? 'text-rose-400' : 'text-amber-300'}">
                        ${w.attendance_rate_pct}%
                    </td>
                    <td class="py-2 px-2.5 text-center whitespace-nowrap">
                        ${riskBadge}
                    </td>
                </tr>
            `;
        }).join('');
    },

    filterByEmployee(empName) {
        const searchInput = document.getElementById('attSearchInput');
        if (searchInput) {
            searchInput.value = empName;
            this.filterAttendance();
            this.showToast(`🔍 Showing shift ledger for ${empName}`);
        }
    },

    renderAttendanceRoles(roles) {
        const grid = document.getElementById('attRoleDistributionGrid');
        const roleFilter = document.getElementById('attRoleFilter');

        if (roleFilter && roleFilter.options.length <= 1) {
            // Populate filter options
            roles.forEach(r => {
                const opt = document.createElement('option');
                opt.value = r.role;
                opt.textContent = `${r.role} (${r.headcount})`;
                roleFilter.appendChild(opt);
            });
        }

        if (!grid) return;
        if (!roles || roles.length === 0) {
            grid.innerHTML = `<div class="text-xs text-slate-500 py-3 text-center col-span-full">No role data available.</div>`;
            return;
        }

        grid.innerHTML = roles.map(r => `
            <div class="glass-panel-sub p-3 flex flex-col justify-between border border-white/5 hover:border-white/15 transition">
                <div class="flex items-start justify-between gap-1">
                    <span class="text-xs font-bold text-white truncate max-w-[150px]" title="${r.role}">${r.role}</span>
                    <span class="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-white/5 text-slate-300">
                        ${r.headcount} Staff
                    </span>
                </div>
                <div class="my-2 flex items-baseline justify-between">
                    <span class="text-lg font-black font-mono text-emerald-400">${r.attendance_rate_pct}%</span>
                    <span class="text-[11px] text-slate-400 font-mono">${r.total_hours_worked} hrs</span>
                </div>
                <div class="text-[10px] text-slate-400 flex items-center justify-between pt-1.5 border-t border-white/5">
                    <span>Present: <strong class="text-emerald-400 font-mono">${r.present_count}</strong></span>
                    <span>Absent: <strong class="text-rose-400 font-mono">${r.absent_count}</strong></span>
                </div>
            </div>
        `).join('');
    },

    filterAttendance() {
        const query = (document.getElementById('attSearchInput')?.value || '').toLowerCase().trim();
        const role = document.getElementById('attRoleFilter')?.value || '';
        const risk = document.getElementById('attRiskFilter')?.value || '';

        const roster = this.attendance.staff_roster || [];
        this.attendance.filtered_staff = roster.filter(s => {
            if (query) {
                const name = (s.employee_name || '').toLowerCase();
                const code = (s.employee_id || '').toLowerCase();
                if (!name.includes(query) && !code.includes(query)) return false;
            }
            if (role && s.designation !== role) return false;
            if (risk && s.risk_tier !== risk) return false;
            return true;
        });

        this.renderAttendanceTable();
    },

    renderAttendanceTable() {
        const tbody = document.getElementById('attTableBody');
        const badge = document.getElementById('attRecordCountBadge');
        const staffList = this.attendance.filtered_staff || [];

        if (badge) badge.textContent = `${staffList.length} Active Employees`;
        if (!tbody) return;

        if (staffList.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center py-8 text-slate-500 text-xs">
                        No active employees match the selected criteria for this period.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = staffList.map(s => {
            let riskBadge = '';
            if (s.risk_tier === 'CRITICAL') {
                riskBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse">CRITICAL</span>';
            } else if (s.risk_tier === 'HIGH') {
                riskBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/40">HIGH RISK</span>';
            } else if (s.risk_tier === 'MODERATE') {
                riskBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-blue-500/20 text-blue-300 border border-blue-500/30">MODERATE</span>';
            } else {
                riskBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">OPTIMAL</span>';
            }

            const attRate = parseFloat(s.attendance_rate_pct || 0);
            const rateColor = attRate >= 90 ? 'text-emerald-400' : (attRate >= 75 ? 'text-amber-300' : 'text-rose-400');

            return `
                <tr class="hover:bg-white/[0.04] transition cursor-pointer" onclick="zeptoApp.openEmployeeDrawer('${s.employee_id}')" title="Click to view full shift punches & work duration ledger for ${s.employee_name}">
                    <td class="py-2.5 px-3">
                        <div class="font-bold text-white flex items-center gap-1.5">
                            <span>${s.employee_name || '—'}</span>
                            <span class="text-[10px] text-emerald-400 opacity-60">↗</span>
                        </div>
                        <div class="text-[10px] font-mono text-slate-500">${s.employee_id || ''}</div>
                    </td>
                    <td class="py-2.5 px-3">
                        <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-white/5 border border-white/10 text-slate-300 whitespace-nowrap">
                            ${s.designation || 'Unassigned'}
                        </span>
                    </td>
                    <td class="py-2.5 px-3 text-center font-mono font-bold text-slate-300">
                        ${s.total_shifts} shifts
                    </td>
                    <td class="py-2.5 px-3 text-center font-mono">
                        <span class="text-emerald-400 font-bold">${s.present_count} P</span>
                        <span class="text-slate-600">/</span>
                        <span class="${s.absent_count > 0 ? 'text-rose-400 font-bold' : 'text-slate-500'}">${s.absent_count} A</span>
                    </td>
                    <td class="py-2.5 px-3 text-center font-mono font-extrabold ${rateColor}">
                        ${attRate.toFixed(1)}%
                    </td>
                    <td class="py-2.5 px-3 text-right font-mono font-bold text-purple-300">
                        ${s.total_hours_worked}h
                    </td>
                    <td class="py-2.5 px-3 text-right font-mono text-slate-300">
                        ${s.avg_daily_hours}h
                    </td>
                    <td class="py-2.5 px-3 text-center whitespace-nowrap">
                        ${riskBadge}
                    </td>
                    <td class="py-2.5 px-3 text-center">
                        <button
                            type="button"
                            onclick="event.stopPropagation(); zeptoApp.openEmployeeDrawer('${s.employee_id}')"
                            class="px-2.5 py-1 rounded bg-emerald-500/10 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-[11px] font-semibold transition"
                        >
                            <span>🔍</span> Punches & Times
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    // -----------------------------------------------------------------------
    // Employee Slide-Out Drawer Master-Detail Logic (sumi:desktop-app-design)
    // -----------------------------------------------------------------------

    async openEmployeeDrawer(employeeId) {
        if (!employeeId) return;

        const drawer = document.getElementById('attEmployeeDrawer');
        const backdrop = document.getElementById('attEmployeeDrawerBackdrop');

        if (!drawer || !backdrop) return;

        // Reset drawer UI to loading state
        document.getElementById('drawerEmpName').textContent = 'Loading employee...';
        document.getElementById('drawerEmpCode').textContent = employeeId;
        document.getElementById('drawerEmpRole').textContent = 'Fetching details...';
        document.getElementById('drawerEmpAvatar').textContent = '--';
        document.getElementById('drawerAttRate').textContent = '--%';
        document.getElementById('drawerTotalShifts').textContent = '0 total shifts';
        document.getElementById('drawerPresentCount').textContent = '0';
        document.getElementById('drawerAbsentCount').textContent = '0';
        document.getElementById('drawerWOLeaves').textContent = '0 WO · 0 Leave';
        document.getElementById('drawerAvgHours').textContent = '-- hrs';
        document.getElementById('drawerTotalHours').textContent = '0 hrs total';

        const tbody = document.getElementById('drawerPunchHistoryBody');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-slate-500 text-xs">Loading shift records...</td></tr>`;
        }

        // Open drawer animations
        backdrop.classList.remove('opacity-0', 'pointer-events-none');
        backdrop.classList.add('opacity-100', 'pointer-events-auto');
        drawer.classList.remove('translate-x-full');
        drawer.classList.add('translate-x-0');
        document.body.style.overflow = 'hidden';

        try {
            const res = await fetch(`/api/v1/zepto/attendance/employee/${encodeURIComponent(employeeId)}`);
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to load employee details');
            }
            const data = await res.json();
            this.renderEmployeeDrawer(data.detail);
        } catch (err) {
            console.error('[ZEPTO-DRAWER] Error fetching employee detail:', err);
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-rose-400 text-xs">⚠️ ${err.message}</td></tr>`;
            }
        }
    },

    renderEmployeeDrawer(emp) {
        if (!emp) return;

        // Header info
        const nameEl = document.getElementById('drawerEmpName');
        const codeEl = document.getElementById('drawerEmpCode');
        const roleEl = document.getElementById('drawerEmpRole');
        const avatarEl = document.getElementById('drawerEmpAvatar');
        const riskEl = document.getElementById('drawerRiskBadge');

        if (nameEl) nameEl.textContent = emp.employee_name || 'Staff Member';
        if (codeEl) codeEl.textContent = emp.employee_id || 'EMP-XXXX';
        if (roleEl) roleEl.textContent = emp.designation || 'Unassigned Role';

        // Avatar initials
        if (avatarEl) {
            const initials = (emp.employee_name || 'E')
                .split(' ')
                .map(n => n[0])
                .slice(0, 2)
                .join('')
                .toUpperCase();
            avatarEl.textContent = initials || 'EM';
        }

        // Risk badge
        if (riskEl) {
            riskEl.textContent = emp.risk_tier || 'LOW';
            if (emp.risk_tier === 'CRITICAL') {
                riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded border bg-rose-500/20 text-rose-300 border-rose-500/40 uppercase tracking-wider font-mono animate-pulse';
            } else if (emp.risk_tier === 'HIGH') {
                riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded border bg-amber-500/20 text-amber-300 border-amber-500/40 uppercase tracking-wider font-mono';
            } else if (emp.risk_tier === 'MODERATE') {
                riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded border bg-sky-500/20 text-sky-300 border-sky-500/40 uppercase tracking-wider font-mono';
            } else {
                riskEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded border bg-emerald-500/20 text-emerald-300 border-emerald-500/40 uppercase tracking-wider font-mono';
            }
        }

        // Metrics
        const attRateEl = document.getElementById('drawerAttRate');
        const totalShiftsEl = document.getElementById('drawerTotalShifts');
        const presEl = document.getElementById('drawerPresentCount');
        const absEl = document.getElementById('drawerAbsentCount');
        const woLeavesEl = document.getElementById('drawerWOLeaves');
        const avgHoursEl = document.getElementById('drawerAvgHours');
        const totalHoursEl = document.getElementById('drawerTotalHours');
        const histCountEl = document.getElementById('drawerHistoryCount');

        if (attRateEl) attRateEl.textContent = `${emp.attendance_rate_pct}%`;
        if (totalShiftsEl) totalShiftsEl.textContent = `${emp.total_shifts} shifts tracked`;
        if (presEl) presEl.textContent = emp.present_count;
        if (absEl) absEl.textContent = emp.absent_count;
        if (woLeavesEl) woLeavesEl.textContent = `${emp.week_off_count} WO · ${emp.leave_count} Leave`;
        if (avgHoursEl) avgHoursEl.textContent = `${emp.avg_daily_hours} hrs`;
        if (totalHoursEl) totalHoursEl.textContent = `${emp.total_hours_worked} hrs total`;

        // History table
        const history = emp.punch_history || [];
        if (histCountEl) histCountEl.textContent = `${history.length} shifts`;

        const tbody = document.getElementById('drawerPunchHistoryBody');
        if (!tbody) return;

        if (history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-slate-500 text-xs">No shift history found for this staff member.</td></tr>`;
            return;
        }

        tbody.innerHTML = history.map(p => {
            let statusBadge = '';
            if (p.status === 'PRESENT') {
                statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">P</span>';
            } else if (p.status === 'ABSENT') {
                statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30">A</span>';
            } else if (p.status === 'WEEK_OFF') {
                statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-500/15 text-slate-300 border border-white/10">WO</span>';
            } else if (p.status === 'HALF_DAY') {
                statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">HD</span>';
            } else {
                statusBadge = `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white/5 text-slate-300">${p.status}</span>`;
            }

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="py-2 px-2.5 font-mono text-[11px] text-slate-300 whitespace-nowrap">${p.shift_date}</td>
                    <td class="py-2 px-2.5 text-[10px] text-slate-300 truncate max-w-[120px]">${p.shift_name || 'General Shift'}</td>
                    <td class="py-2 px-2.5 font-mono text-[10px] text-sky-300 whitespace-nowrap">${p.shift_time || '09:00 - 18:00'}</td>
                    <td class="py-2 px-2.5 text-right font-mono text-[10px] ${p.work_duration_mins > 0 ? 'text-white' : 'text-slate-600'}">
                        ${p.work_duration_mins > 0 ? `${(p.work_duration_mins / 60).toFixed(1)}h` : '—'}
                    </td>
                    <td class="py-2 px-2.5 text-center whitespace-nowrap">${statusBadge}</td>
                </tr>
            `;
        }).join('');
    },

    closeEmployeeDrawer() {
        const drawer = document.getElementById('attEmployeeDrawer');
        const backdrop = document.getElementById('attEmployeeDrawerBackdrop');

        if (backdrop) {
            backdrop.classList.remove('opacity-100', 'pointer-events-auto');
            backdrop.classList.add('opacity-0', 'pointer-events-none');
        }
        if (drawer) {
            drawer.classList.remove('translate-x-0');
            drawer.classList.add('translate-x-full');
        }
        document.body.style.overflow = '';
    },

    async handleAttendanceFileUpload(event) {
        const file = event.target?.files?.[0];
        if (!file) return;

        this.showToast('📤 Uploading and parsing attendance spreadsheet...');
        try {
            const formData = new FormData();
            formData.append('file', file);

            const res = await fetch('/api/v1/zepto/attendance/upload', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Upload failed');

            this.showToast(`✅ Successfully imported ${data.total_records} attendance records for ${data.store_name}!`);
            await this.loadAttendanceData();
        } catch (err) {
            this.showToast('⚠️ Attendance upload failed: ' + err.message, true);
        } finally {
            if (event.target) event.target.value = '';
        }
    },

    async syncAttendanceFromGmail() {
        const btn = document.getElementById('btnSyncAttGmail');
        const icon = document.getElementById('btnSyncAttGmailIcon');
        const text = document.getElementById('btnSyncAttGmailText');

        if (btn) btn.disabled = true;
        if (icon) icon.className = 'inline-block animate-spin';
        if (text) text.textContent = 'Scanning Gmail...';

        try {
            const res = await fetch('/api/v1/zepto/gmail/sync-attendance', { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Gmail sync failed');

            if (data.status === 'no_new_reports') {
                this.showToast('📧 No new attendance email reports found in Gmail.');
            } else {
                this.showToast(`✅ Synced ${data.records_imported} records from ${data.processed_count} email attachments!`);
                await this.loadAttendanceData();
            }
        } catch (err) {
            this.showToast('⚠️ ' + err.message, true);
        } finally {
            if (btn) btn.disabled = false;
            if (icon) icon.className = '';
            if (text) text.textContent = 'Sync from Gmail';
        }
    },

    exportAttendanceCSV() {
        const records = this.attendance.filtered || [];
        if (records.length === 0) {
            alert('No records to export.');
            return;
        }

        const headers = ['Date', 'Employee ID', 'Employee Name', 'Designation', 'Shift Name', 'Shift Time', 'Work Duration (mins)', 'Status'];
        const csvRows = [headers.join(',')];

        records.forEach(r => {
            const row = [
                `"${r.shift_date || ''}"`,
                `"${r.employee_id || ''}"`,
                `"${(r.employee_name || '').replace(/"/g, '""')}"`,
                `"${(r.designation || '').replace(/"/g, '""')}"`,
                `"${(r.shift_name || '').replace(/"/g, '""')}"`,
                `"${r.shift_time || ''}"`,
                r.work_duration_mins || 0,
                `"${r.status || ''}"`,
            ];
            csvRows.push(row.join(','));
        });

        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `zepto_attendance_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    },

    // -----------------------------------------------------------------------
    // Gmail OAuth 2.0 Management
    // -----------------------------------------------------------------------

    async checkGmailStatus() {
        try {
            const res = await fetch('/api/v1/zepto/gmail/status');
            if (!res.ok) return;
            const data = await res.json();
            this.renderGmailState(data);
        } catch (err) {
            console.error('[ZEPTO-GMAIL] Error checking status:', err);
        }
    },

    renderGmailState(status) {
        const unconfigBox = document.getElementById('gmailUnconfiguredBox');
        const disconnBox = document.getElementById('gmailDisconnectedBox');
        const connBox = document.getElementById('gmailConnectedBox');
        const badge = document.getElementById('gmailStatusBadge');
        const headerText = document.getElementById('headerGmailStatusText');
        const headerBtn = document.getElementById('headerGmailStatusBtn');

        if (!status || !status.configured) {
            if (unconfigBox) unconfigBox.style.display = 'block';
            if (disconnBox) disconnBox.style.display = 'none';
            if (connBox) connBox.style.display = 'none';
            if (badge) {
                badge.textContent = 'Setup Required';
                badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono';
            }
            if (headerText) headerText.textContent = 'Gmail (.env)';
            if (headerBtn) headerBtn.className = 'px-2.5 py-1.5 rounded-md bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/25 text-xs font-semibold text-amber-300 hover:text-white transition flex items-center gap-1.5 shadow-sm';
        } else if (status.connected) {
            if (unconfigBox) unconfigBox.style.display = 'none';
            if (disconnBox) disconnBox.style.display = 'none';
            if (connBox) connBox.style.display = 'block';
            if (badge) {
                badge.textContent = 'Connected';
                badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-mono';
            }
            const emailEl = document.getElementById('gmailAccountEmail');
            if (emailEl) emailEl.textContent = status.email || 'Connected Account';

            const lastSyncedEl = document.getElementById('gmailLastSynced');
            if (lastSyncedEl && status.updated_at) {
                try {
                    const d = new Date(status.updated_at);
                    lastSyncedEl.textContent = d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                } catch {
                    lastSyncedEl.textContent = 'Active';
                }
            }
            if (headerText) headerText.textContent = status.email ? status.email.split('@')[0] : 'Connected';
            if (headerBtn) headerBtn.className = 'px-2.5 py-1.5 rounded-md bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/25 text-xs font-semibold text-emerald-300 hover:text-white transition flex items-center gap-1.5 shadow-sm';

            // Automatically load recent emails feed
            this.loadRecentEmails();
        } else {
            if (unconfigBox) unconfigBox.style.display = 'none';
            if (disconnBox) disconnBox.style.display = 'block';
            if (connBox) connBox.style.display = 'none';
            if (badge) {
                badge.textContent = 'Ready to Link';
                badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/20 font-mono';
            }
            if (headerText) headerText.textContent = 'Connect Gmail';
            if (headerBtn) headerBtn.className = 'px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition flex items-center gap-1.5 shadow-sm';
        }
    },

    async connectGmail() {
        const btn = document.getElementById('btnConnectGmail');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = 'Connecting to Google...';
        }
        try {
            const res = await fetch('/api/v1/zepto/gmail/auth-url');
            const data = await res.json();
            if (!res.ok || !data.auth_url) {
                throw new Error(data.detail || 'Failed to generate Google OAuth authorization URL');
            }
            // Redirect browser to Google Sign-In
            window.location.href = data.auth_url;
        } catch (err) {
            alert('Failed to start Google sign-in: ' + err.message);
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = 'Sign in with Google';
            }
        }
    },

    async disconnectGmail() {
        if (!confirm('Are you sure you want to disconnect this Gmail account from the Zepto Hub?')) return;
        const btn = document.getElementById('btnDisconnectGmail');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Disconnecting...';
        }
        try {
            const res = await fetch('/api/v1/zepto/gmail/disconnect', { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to disconnect Gmail account');

            this.showToast('Gmail account disconnected.');
            await this.checkGmailStatus();
        } catch (err) {
            alert('Error disconnecting: ' + err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<span>🔌</span> Disconnect Gmail';
            }
        }
    },

    async loadRecentEmails(selectedMonth) {
        const loadingEl = document.getElementById('gmailEmailsLoading');
        const tableContainer = document.getElementById('gmailTableContainer');
        const emptyEl = document.getElementById('gmailEmailsEmpty');
        const badgeEl = document.getElementById('gmailFeedCountBadge');
        const refreshIcon = document.getElementById('btnRefreshGmailFeedIcon');

        if (loadingEl) loadingEl.style.display = 'flex';
        if (tableContainer) tableContainer.style.display = 'none';
        if (emptyEl) emptyEl.style.display = 'none';
        if (refreshIcon) refreshIcon.className = 'inline-block animate-spin';

        try {
            const monthFilter = selectedMonth || document.getElementById('gmailMonthFilter')?.value || 'CURRENT';
            const queryMonth = monthFilter === 'CURRENT' ? new Date().toISOString().slice(0, 7) : monthFilter;
            // Load instantly from local database (zero-latency, no Gmail API call)
            const res = await fetch(`/api/v1/zepto/gmail/emails?month=${encodeURIComponent(queryMonth)}`);
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'Failed to fetch emails');
            }

            const data = await res.json();
            const emails = data.emails || [];

            this.gmail.emails = emails;
            this.updateGmailCategoryCounts(emails);
            this.filterGmailEmails();

            if (badgeEl) badgeEl.textContent = `${emails.length} Emails (${data.month || queryMonth})`;
            if (loadingEl) loadingEl.style.display = 'none';
        } catch (err) {
            console.error('[ZEPTO-GMAIL] Error loading recent emails:', err);
            if (loadingEl) {
                loadingEl.innerHTML = `<span class="text-rose-400">⚠️ Failed to load emails: ${err.message}</span>`;
            }
        } finally {
            if (refreshIcon) refreshIcon.className = '';
        }
    },

    async syncGmailDelta() {
        const btn = document.getElementById('btnSyncGmailDelta');
        const icon = document.getElementById('btnSyncGmailDeltaIcon');
        const text = document.getElementById('btnSyncGmailDeltaText');

        if (btn) btn.disabled = true;
        if (icon) icon.className = 'inline-block animate-spin';
        if (text) text.textContent = 'Syncing...';

        try {
            const monthFilter = document.getElementById('gmailMonthFilter')?.value || 'CURRENT';
            const queryMonth = monthFilter === 'CURRENT' ? new Date().toISOString().slice(0, 7) : monthFilter;
            const res = await fetch(`/api/v1/zepto/gmail/recent-emails?month=${encodeURIComponent(queryMonth)}`);
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'Failed to sync emails');
            }

            const data = await res.json();
            const deltaCount = data.delta_fetched || 0;
            const emails = data.emails || [];

            this.gmail.emails = emails;
            this.updateGmailCategoryCounts(emails);
            this.filterGmailEmails();

            const badgeEl = document.getElementById('gmailFeedCountBadge');
            if (badgeEl) badgeEl.textContent = `${emails.length} Emails (${data.month || queryMonth})`;

            if (deltaCount > 0) {
                this.showToast(`⚡ Synced ${deltaCount} new email${deltaCount > 1 ? 's' : ''} from Gmail`);
            } else {
                this.showToast('✅ Mailbox is up to date — no new emails');
            }
        } catch (err) {
            this.showToast(`⚠️ Gmail delta sync error: ${err.message}`, true);
        } finally {
            if (btn) btn.disabled = false;
            if (icon) icon.className = '';
            if (text) text.textContent = 'Sync Delta';
        }
    },

    async ingestAllEmails() {
        const btn = document.getElementById('btnIngestAllEmails');
        const icon = document.getElementById('btnIngestAllEmailsIcon');
        const text = document.getElementById('btnIngestAllEmailsText');

        if (btn) btn.disabled = true;
        if (icon) icon.className = 'inline-block animate-spin';
        if (text) text.textContent = 'Ingesting Emails...';

        try {
            const monthFilter = document.getElementById('gmailMonthFilter')?.value || 'CURRENT';
            const queryMonth = monthFilter === 'CURRENT' ? new Date().toISOString().slice(0, 7) : monthFilter;
            const res = await fetch(`/api/v1/zepto/gmail/ingest-all-emails?month=${encodeURIComponent(queryMonth)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Email ingestion failed');

            this.showToast(`⚡ ${data.message || 'Successfully ingested emails and updated counts'}`);

            // If category counts returned, update cards immediately
            if (data.category_counts) {
                Object.keys(data.category_counts).forEach(cat => {
                    const countEl = document.getElementById(`gmailCatCount-${cat}`);
                    if (countEl) countEl.textContent = data.category_counts[cat];
                });
            }

            // Reload email feed and store tabs from local database after ingest completes
            await this.loadRecentEmails();
            await this.loadOverview();
            if (this.currentTab === 'attendance') await this.loadAttendanceData();
            if (this.currentTab === 'metrics') await this.loadMetrics();
            if (this.currentTab === 'loss') await this.loadLoss();
        } catch (err) {
            this.showToast(`Error ingesting emails: ${err.message}`, true);
        } finally {
            if (btn) btn.disabled = false;
            if (icon) icon.className = '';
            if (text) text.textContent = 'Ingest All Emails';
        }
    },

    filterGmailEmails() {
        const query = (document.getElementById('gmailSearchInput')?.value || '').toLowerCase().trim();
        const catFilter = document.getElementById('gmailCategoryFilter')?.value || 'ALL';
        const hideSecCheckbox = document.getElementById('gmailHideSecurityAlertsCheckbox');
        const hideSecurity = hideSecCheckbox ? hideSecCheckbox.checked : this.gmail.hideSecurityAlerts;
        const showHidden = this.gmail.showHidden;

        let filtered = (this.gmail.emails || []).filter(m => {
            const isManuallyHidden = this.gmail.hiddenEmailIds.has(m.id);
            if (isManuallyHidden && !showHidden) return false;

            if (hideSecurity && m.category === 'SECURITY_ALERT') return false;

            if (catFilter !== 'ALL' && m.category !== catFilter) return false;

            if (query) {
                const sub = (m.subject || '').toLowerCase();
                const from = (m.from || '').toLowerCase();
                const snip = (m.snippet || '').toLowerCase();
                const cat = (m.category_label || m.category || '').toLowerCase();
                const metrics = JSON.stringify(m.extracted_metrics || {}).toLowerCase();
                if (!sub.includes(query) && !from.includes(query) && !snip.includes(query) && !cat.includes(query) && !metrics.includes(query)) {
                    return false;
                }
            }

            return true;
        });

        this.gmail.filtered = filtered;
        this.renderGmailTable(filtered);
        this.updateGmailHideCountBadge();
    },

    toggleHideSecurityAlerts(checked) {
        this.gmail.hideSecurityAlerts = checked;
        this.filterGmailEmails();
    },

    toggleShowHiddenEmails() {
        this.gmail.showHidden = !this.gmail.showHidden;
        const btn = document.getElementById('btnToggleHiddenGmail');
        const icon = document.getElementById('btnToggleHiddenGmailIcon');
        const text = document.getElementById('btnToggleHiddenGmailText');

        if (this.gmail.showHidden) {
            if (btn) btn.className = 'px-2.5 py-1.5 rounded-md bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 text-xs font-semibold text-amber-300 transition flex items-center gap-1.5';
            if (icon) icon.textContent = '🙈';
            if (text) text.textContent = `Hide Archived (${this.gmail.hiddenEmailIds.size})`;
        } else {
            if (btn) btn.className = 'px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition flex items-center gap-1.5';
            if (icon) icon.textContent = '👁️';
            if (text) text.textContent = `Show Hidden (${this.gmail.hiddenEmailIds.size})`;
        }
        this.filterGmailEmails();
    },

    hideSingleEmail(emailId) {
        if (!emailId) return;
        this.gmail.hiddenEmailIds.add(emailId);
        localStorage.setItem('zepto_hidden_email_ids', JSON.stringify(Array.from(this.gmail.hiddenEmailIds)));
        this.showToast('Email hidden from view.');
        this.filterGmailEmails();
    },

    unhideSingleEmail(emailId) {
        if (!emailId) return;
        this.gmail.hiddenEmailIds.delete(emailId);
        localStorage.setItem('zepto_hidden_email_ids', JSON.stringify(Array.from(this.gmail.hiddenEmailIds)));
        this.showToast('Email restored to active ledger.');
        this.filterGmailEmails();
    },

    resetGmailFilters() {
        const searchInput = document.getElementById('gmailSearchInput');
        const catFilter = document.getElementById('gmailCategoryFilter');
        const secCheckbox = document.getElementById('gmailHideSecurityAlertsCheckbox');

        if (searchInput) searchInput.value = '';
        if (catFilter) catFilter.value = 'ALL';
        if (secCheckbox) secCheckbox.checked = true;
        this.gmail.hideSecurityAlerts = true;
        this.gmail.showHidden = false;

        const btn = document.getElementById('btnToggleHiddenGmail');
        const icon = document.getElementById('btnToggleHiddenGmailIcon');
        const text = document.getElementById('btnToggleHiddenGmailText');
        if (btn) btn.className = 'px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition flex items-center gap-1.5';
        if (icon) icon.textContent = '👁️';
        if (text) text.textContent = `Show Hidden (${this.gmail.hiddenEmailIds.size})`;

        this.highlightSelectedGmailCategory('ALL');
        this.filterGmailEmails();
    },

    selectGmailCategory(category) {
        const catFilter = document.getElementById('gmailCategoryFilter');
        if (!catFilter) return;

        // If clicking same category that is already selected, toggle back to ALL
        if (catFilter.value === category) {
            catFilter.value = 'ALL';
        } else {
            catFilter.value = category;
        }

        this.highlightSelectedGmailCategory(catFilter.value);
        this.filterGmailEmails();
    },

    highlightSelectedGmailCategory(activeCategory) {
        const categories = [
            'STORE_METRICS', 'ATTENDANCE', 'MANPOWER_UTILIZATION',
            'DQ_LOSS', 'SHRINKAGE', 'MANPOWER_PLAN', 'OPERATIONAL', 'SECURITY_ALERT'
        ];

        categories.forEach(cat => {
            const el = document.getElementById(`gmailCatCount-${cat}`)?.parentElement;
            if (!el) return;

            if (activeCategory === cat) {
                el.classList.add('ring-2', 'ring-white/40', 'bg-white/10');
            } else {
                el.classList.remove('ring-2', 'ring-white/40', 'bg-white/10');
            }
        });
    },

    updateGmailCategoryCounts(emails) {
        const counts = {
            STORE_METRICS: 0,
            ATTENDANCE: 0,
            MANPOWER_UTILIZATION: 0,
            DQ_LOSS: 0,
            SHRINKAGE: 0,
            MANPOWER_PLAN: 0,
            OPERATIONAL: 0,
            SECURITY_ALERT: 0,
        };

        const sums = {
            gmv: 0,
            loss: 0,
            ipp: 0,
            ippCount: 0,
        };

        (emails || []).forEach(m => {
            const cat = m.category || 'OPERATIONAL';
            if (counts[cat] !== undefined) {
                counts[cat]++;
            } else {
                counts['OPERATIONAL']++;
            }

            const met = m.extracted_metrics || {};
            if (met.sales_gmv && !isNaN(met.sales_gmv)) sums.gmv += Number(met.sales_gmv);
            if (met.loss_amount && !isNaN(met.loss_amount)) sums.loss += Number(met.loss_amount);
            if (met.packer_ipp && !isNaN(met.packer_ipp)) {
                sums.ipp += Number(met.packer_ipp);
                sums.ippCount++;
            }
        });

        Object.keys(counts).forEach(cat => {
            const countEl = document.getElementById(`gmailCatCount-${cat}`);
            if (countEl) {
                countEl.textContent = counts[cat];
            }
        });

        // Set rich aggregate subtext on category cards
        const subGmv = document.getElementById('gmailCatSub-STORE_METRICS');
        if (subGmv) {
            subGmv.textContent = sums.gmv > 0 ? `₹${Math.round(sums.gmv / 1000)}k GMV` : 'GMV & Orders';
        }
        const subLoss = document.getElementById('gmailCatSub-DQ_LOSS');
        if (subLoss) {
            subLoss.textContent = sums.loss > 0 ? `₹${sums.loss.toLocaleString('en-IN')} Loss` : 'Defects & Waste';
        }
        const subIpp = document.getElementById('gmailCatSub-MANPOWER_UTILIZATION');
        if (subIpp) {
            const avgIpp = sums.ippCount > 0 ? (sums.ipp / sums.ippCount).toFixed(0) : 0;
            subIpp.textContent = avgIpp > 0 ? `Avg ${avgIpp} IPP` : 'Picker IPP';
        }
    },

    computeGmailAggregates(emails) {
        let totalGmv = 0;
        let gmvCount = 0;
        let totalOrders = 0;
        let ordersCount = 0;
        let totalAov = 0;
        let aovCount = 0;
        let totalSla = 0;
        let slaCount = 0;
        let totalIpp = 0;
        let ippCount = 0;
        let totalLoss = 0;
        let lossCount = 0;
        let totalAttachments = 0;
        let totalParsedRecords = 0;
        const categoriesSeen = new Set();

        (emails || []).forEach(m => {
            if (m.category) categoriesSeen.add(m.category);
            if (m.attachments && Array.isArray(m.attachments)) {
                totalAttachments += m.attachments.length;
            }
            totalParsedRecords += (m.parsed_records_count || 0);

            const met = m.extracted_metrics || {};
            if (met.sales_gmv && !isNaN(met.sales_gmv) && Number(met.sales_gmv) > 0) {
                totalGmv += Number(met.sales_gmv);
                gmvCount++;
            }
            if (met.order_count && !isNaN(met.order_count) && Number(met.order_count) > 0) {
                totalOrders += Number(met.order_count);
                ordersCount++;
            }
            if (met.aov && !isNaN(met.aov) && Number(met.aov) > 0) {
                totalAov += Number(met.aov);
                aovCount++;
            }
            if (met.sla_adherence_pct && !isNaN(met.sla_adherence_pct) && Number(met.sla_adherence_pct) > 0) {
                totalSla += Number(met.sla_adherence_pct);
                slaCount++;
            }
            if (met.packer_ipp && !isNaN(met.packer_ipp) && Number(met.packer_ipp) > 0) {
                totalIpp += Number(met.packer_ipp);
                ippCount++;
            }
            if (met.loss_amount && !isNaN(met.loss_amount) && Number(met.loss_amount) > 0) {
                totalLoss += Number(met.loss_amount);
                lossCount++;
            }
        });

        const avgAov = aovCount > 0 ? (totalAov / aovCount) : (totalOrders > 0 ? Math.round(totalGmv / totalOrders) : 0);
        const avgSla = slaCount > 0 ? (totalSla / slaCount) : 0;
        const avgIpp = ippCount > 0 ? (totalIpp / ippCount) : 0;

        return {
            totalGmv,
            gmvCount,
            totalOrders,
            ordersCount,
            avgAov: Math.round(avgAov),
            avgSla: Number(avgSla.toFixed(1)),
            slaCount,
            avgIpp: Number(avgIpp.toFixed(1)),
            ippCount,
            totalLoss,
            lossCount,
            totalAttachments,
            totalParsedRecords,
            categoriesCount: categoriesSeen.size,
            emailCount: (emails || []).length,
        };
    },

    updateGmailAggregatesDeck(agg, emails) {
        const deck = document.getElementById('gmailAggregatesDeck');
        if (!deck) return;

        if (!emails || emails.length === 0) {
            deck.style.display = 'none';
            return;
        }
        deck.style.display = 'block';

        const gmvEl = document.getElementById('gmailAggTotalGmv');
        const gmvCountEl = document.getElementById('gmailAggGmvCount');
        const ordersEl = document.getElementById('gmailAggTotalOrders');
        const ordersCountEl = document.getElementById('gmailAggOrdersCount');
        const aovEl = document.getElementById('gmailAggAvgAov');
        const slaEl = document.getElementById('gmailAggAvgSla');
        const ippEl = document.getElementById('gmailAggAvgIpp');
        const lossEl = document.getElementById('gmailAggTotalLoss');
        const lossCountEl = document.getElementById('gmailAggLossCount');
        const emailsAnalyzedEl = document.getElementById('gmailAggEmailsAnalyzed');
        const filterLabelEl = document.getElementById('gmailAggFilterLabel');

        if (gmvEl) gmvEl.textContent = `₹${agg.totalGmv.toLocaleString('en-IN')}`;
        if (gmvCountEl) gmvCountEl.textContent = `${agg.gmvCount} GMV Reports`;
        if (ordersEl) ordersEl.textContent = agg.totalOrders.toLocaleString('en-IN');
        if (ordersCountEl) ordersCountEl.textContent = `${agg.ordersCount} Dispatch Reports`;
        if (aovEl) aovEl.textContent = `₹${agg.avgAov.toLocaleString('en-IN')}`;
        if (slaEl) slaEl.textContent = `${agg.avgSla}%`;
        if (ippEl) ippEl.textContent = agg.avgIpp;
        if (lossEl) lossEl.textContent = `₹${agg.totalLoss.toLocaleString('en-IN')}`;
        if (lossCountEl) lossCountEl.textContent = `${agg.lossCount} Loss Audits`;
        if (emailsAnalyzedEl) emailsAnalyzedEl.textContent = `${agg.emailCount} Emails In View`;

        if (filterLabelEl) {
            const monthSel = document.getElementById('gmailMonthFilter');
            const catSel = document.getElementById('gmailCategoryFilter');
            const monthText = monthSel?.options[monthSel.selectedIndex]?.text || 'Current Month';
            const catText = catSel?.options[catSel.selectedIndex]?.text || 'All Categories';
            filterLabelEl.textContent = `${monthText} · ${catText}`;
        }
    },

    updateGmailTableFooter(agg) {
        const footCats = document.getElementById('gmailFootCats');
        const footMsgCount = document.getElementById('gmailFootMsgCount');
        const footMetrics = document.getElementById('gmailFootMetricsAggregates');
        const footAttCount = document.getElementById('gmailFootAttCount');
        const footParsedCount = document.getElementById('gmailFootParsedCount');

        if (footCats) footCats.textContent = `${agg.categoriesCount} categories`;
        if (footMsgCount) footMsgCount.textContent = `${agg.emailCount} emails total`;
        if (footAttCount) footAttCount.textContent = `${agg.totalAttachments} files`;
        if (footParsedCount) footParsedCount.textContent = `💾 ${agg.totalParsedRecords} synced`;

        if (footMetrics) {
            const pills = [];
            if (agg.totalGmv > 0) {
                pills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-mono text-[10px] font-bold">₹${agg.totalGmv.toLocaleString('en-IN')} Total GMV</span>`);
            }
            if (agg.totalOrders > 0) {
                pills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-mono text-[10px] font-bold">${agg.totalOrders.toLocaleString('en-IN')} Orders</span>`);
            }
            if (agg.avgAov > 0) {
                pills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-mono text-[10px]">₹${agg.avgAov} Avg AOV</span>`);
            }
            if (agg.avgSla > 0) {
                pills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-mono text-[10px]">${agg.avgSla}% Avg SLA</span>`);
            }
            if (agg.avgIpp > 0) {
                pills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-mono text-[10px]">${agg.avgIpp} Avg IPP</span>`);
            }
            if (agg.totalLoss > 0) {
                pills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 font-mono text-[10px] font-bold">₹${agg.totalLoss.toLocaleString('en-IN')} Total Loss</span>`);
            }

            if (pills.length > 0) {
                footMetrics.innerHTML = `<div class="flex flex-wrap gap-1">${pills.join('')}</div>`;
            } else {
                footMetrics.innerHTML = `<span class="text-[10px] text-slate-500 font-mono">No metric values in active filter</span>`;
            }
        }
    },

    updateGmailHideCountBadge() {
        const text = document.getElementById('btnToggleHiddenGmailText');
        const count = this.gmail.hiddenEmailIds.size;
        if (text) {
            text.textContent = this.gmail.showHidden ? `Hide Archived (${count})` : `Show Hidden (${count})`;
        }
    },

    renderGmailTable(emails) {
        const tableContainer = document.getElementById('gmailTableContainer');
        const emptyEl = document.getElementById('gmailEmailsEmpty');
        const tbody = document.getElementById('gmailEmailsTableBody');
        const badgeEl = document.getElementById('gmailFeedCountBadge');
        const deck = document.getElementById('gmailAggregatesDeck');

        if (badgeEl) badgeEl.textContent = `${emails.length} of ${this.gmail.emails.length} Emails`;

        // Calculate and update Key Metrics & Intelligence aggregates
        const agg = this.computeGmailAggregates(emails);
        this.updateGmailAggregatesDeck(agg, emails);
        this.updateGmailTableFooter(agg);

        if (!emails || emails.length === 0) {
            if (tableContainer) tableContainer.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
            if (deck) deck.style.display = 'none';
            return;
        }

        if (emptyEl) emptyEl.style.display = 'none';
        if (tableContainer) tableContainer.style.display = 'block';
        if (!tbody) return;

        tbody.innerHTML = emails.map(m => {
            const dateStr = m.date ? new Date(m.date).toLocaleString('en-IN', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            }) : 'Recent';

            let senderDisplay = m.from || 'Unknown Sender';
            if (senderDisplay.includes('<')) {
                senderDisplay = senderDisplay.split('<')[0].replace(/"/g, '').trim();
            }

            let badgeClass = 'bg-slate-500/15 text-slate-300 border-white/10';
            if (m.badge_color === 'emerald') {
                badgeClass = 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
            } else if (m.badge_color === 'sky') {
                badgeClass = 'bg-sky-500/15 text-sky-400 border-sky-500/30';
            } else if (m.badge_color === 'purple') {
                badgeClass = 'bg-purple-500/15 text-purple-300 border-purple-500/30';
            } else if (m.badge_color === 'rose') {
                badgeClass = 'bg-rose-500/15 text-rose-400 border-rose-500/30';
            } else if (m.badge_color === 'amber') {
                badgeClass = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
            } else if (m.badge_color === 'indigo') {
                badgeClass = 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30';
            }

            // Ingestion / Parsed status badge
            let parseBadge = '';
            if (m.parsed_status === 'PARSED') {
                parseBadge = `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono text-[9px] font-bold" title="${m.parsed_records_count || 0} relational records translated to DB">💾 ${m.parsed_records_count || 0} DB Records</span>`;
            } else if (m.parsed_status === 'FAILED') {
                parseBadge = `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-mono text-[9px] font-bold">⚠️ Parse Failed</span>`;
            }

            // Key Metrics Pill tags
            const met = m.extracted_metrics || {};
            const metricPills = [];
            if (met.sales_gmv) metricPills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 font-mono text-[10px] font-bold">₹${met.sales_gmv.toLocaleString('en-IN')} GMV</span>`);
            if (met.order_count) metricPills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/25 font-mono text-[10px] font-semibold">${met.order_count} Orders</span>`);
            if (met.aov) metricPills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/25 font-mono text-[10px]">₹${met.aov} AOV</span>`);
            if (met.sla_adherence_pct) metricPills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/25 font-mono text-[10px]">${met.sla_adherence_pct}% SLA</span>`);
            if (met.packer_ipp) metricPills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/25 font-mono text-[10px]">${met.packer_ipp} IPP</span>`);
            if (met.loss_amount) metricPills.push(`<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/25 font-mono text-[10px] font-bold">₹${met.loss_amount} Loss</span>`);

            if (metricPills.length >= 2) {
                metricPills.unshift('<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/10 text-slate-200 border border-white/20 font-mono text-[9px] font-extrabold uppercase tracking-wider">📊 Aggregate</span>');
            } else if (metricPills.length === 0) {
                if (m.category === 'ATTENDANCE') {
                    metricPills.push('<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/25 font-mono text-[10px]">👥 Shift Muster Audit</span>');
                } else if (m.category === 'MANPOWER_PLAN') {
                    metricPills.push('<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/25 font-mono text-[10px]">📋 Headcount Plan</span>');
                } else if (m.category === 'SECURITY_ALERT') {
                    metricPills.push('<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-300 border border-slate-500/25 font-mono text-[10px]">🔒 Security Notice</span>');
                } else {
                    metricPills.push('<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-400 border border-white/5 font-mono text-[10px]">📧 Operations Memo</span>');
                }
            }

            let metricsHtml = `<div class="flex flex-wrap gap-1 mb-1">${metricPills.join('')}</div>`;

            // Attachments
            let attHtml = '—';
            if (m.attachments && m.attachments.length > 0) {
                attHtml = `
                    <div class="flex flex-wrap gap-1">
                        ${m.attachments.map(a => `
                            <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[10px] font-mono" title="${a.filename}">
                                <span>📎</span>
                                <span class="truncate max-w-[130px]">${a.filename}</span>
                            </span>
                        `).join('')}
                    </div>
                `;
            }

            const isHidden = this.gmail.hiddenEmailIds.has(m.id);

            return `
                <tr class="hover:bg-white/[0.02] transition ${isHidden ? 'opacity-50 bg-rose-500/[0.03]' : ''}">
                    <!-- Date -->
                    <td class="p-2.5 pl-3.5 font-mono text-[11px] text-slate-300 whitespace-nowrap align-top">
                        ${dateStr}
                    </td>

                    <!-- Category -->
                    <td class="p-2.5 whitespace-nowrap align-top">
                        <div class="space-y-1">
                            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold border ${badgeClass} uppercase tracking-wider">
                                <span>${m.icon || '📧'}</span>
                                <span>${m.category_label || m.category}</span>
                            </span>
                            ${parseBadge ? `<div>${parseBadge}</div>` : ''}
                        </div>
                    </td>

                    <!-- Subject & Sender -->
                    <td class="p-2.5 align-top">
                        <div class="text-xs font-bold text-white group-hover:text-emerald-300 transition line-clamp-1" title="${m.subject}">
                            ${m.subject}
                        </div>
                        <div class="text-[10px] text-slate-400 font-mono mt-0.5 truncate max-w-[280px]">
                            ${senderDisplay}
                        </div>
                        <div class="text-[11px] text-slate-500 mt-1 line-clamp-2 leading-relaxed">
                            ${m.snippet || 'No plain text snippet.'}
                        </div>
                    </td>

                    <!-- Key Metrics -->
                    <td class="p-2.5 align-top">
                        ${metricsHtml}
                    </td>

                    <!-- Attachments -->
                    <td class="p-2.5 align-top">
                        ${attHtml}
                    </td>

                    <!-- Actions -->
                    <td class="p-2.5 pr-3.5 text-center align-top whitespace-nowrap">
                        ${isHidden ? `
                            <button
                                type="button"
                                onclick="zeptoApp.unhideSingleEmail('${m.id}')"
                                class="px-2 py-1 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/25 text-[10px] font-bold transition flex items-center gap-1 mx-auto"
                                title="Restore to main feed"
                            >
                                <span>↩️</span> Restore
                            </button>
                        ` : `
                            <button
                                type="button"
                                onclick="zeptoApp.hideSingleEmail('${m.id}')"
                                class="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-white/5 transition"
                                title="Hide this email"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                                </svg>
                            </button>
                        `}
                    </td>
                </tr>
            `;
        }).join('');
    },

    showToast(message, isError = false) {
        const toast = document.createElement('div');
        toast.className = `fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-lg text-xs font-bold border shadow-2xl transition-all duration-300 ${
            isError ? 'bg-rose-950 text-rose-200 border-rose-500/50' : 'bg-emerald-950 text-emerald-200 border-emerald-500/50'
        }`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    // -----------------------------------------------------------------------
    // Manpower Utilization & IPP Tab Logic
    // -----------------------------------------------------------------------

    async loadUtilization() {
        const month = this.currentGlobalMonth !== 'ALL' ? this.currentGlobalMonth : '';
        const params = new URLSearchParams();
        if (month) params.append('month', month);

        const scopeBadge = document.getElementById('utilActiveScopeBadge');
        if (scopeBadge) scopeBadge.textContent = this.currentGlobalMonth || 'ALL';

        try {
            const res = await fetch(`/api/v1/zepto/utilization/summary?${params.toString()}`);
            if (!res.ok) return;
            const data = await res.json();
            this.renderUtilization(data);
        } catch (err) {
            console.error('[ZEPTO-UTIL] Error loading utilization:', err);
        }
    },

    renderUtilization(data) {
        if (!data) return;

        const totItemsEl = document.getElementById('utilTotalItems');
        const activePickersEl = document.getElementById('utilActivePickers');
        const avgIppEl = document.getElementById('utilAvgIpp');
        const activeHoursEl = document.getElementById('utilActiveHours');
        const idleHoursEl = document.getElementById('utilIdleHours');
        const floorEffEl = document.getElementById('utilFloorEfficiency');
        const flexCostEl = document.getElementById('utilFlexLaborCost');
        const costPerItemEl = document.getElementById('utilCostPerItem');
        const countBadge = document.getElementById('utilRecordCountBadge');
        const tbody = document.getElementById('utilTableBody');

        const records = data.records || [];
        if (totItemsEl) totItemsEl.textContent = (data.total_items_picked || 0).toLocaleString('en-IN');
        if (activePickersEl) activePickersEl.textContent = `${data.active_pickers_count || 0} Pickers`;
        if (avgIppEl) avgIppEl.textContent = data.avg_ipp ? `${data.avg_ipp} IPP` : '—';
        if (activeHoursEl) activeHoursEl.textContent = `${data.total_active_hours || 0} hrs`;
        if (idleHoursEl) idleHoursEl.textContent = `${data.total_idle_hours || 0} hrs`;

        const totalHours = (data.total_active_hours || 0) + (data.total_idle_hours || 0);
        if (floorEffEl) {
            const eff = totalHours > 0 ? Math.round(((data.total_active_hours || 0) / totalHours) * 100) : 100;
            floorEffEl.textContent = `${eff}% Active`;
        }

        if (flexCostEl) flexCostEl.textContent = this.formatCurrency(data.total_flex_labor_cost || 0);
        if (costPerItemEl) {
            const cpi = data.total_items_picked > 0 ? ((data.total_flex_labor_cost || 0) / data.total_items_picked).toFixed(2) : '0.00';
            costPerItemEl.textContent = `₹${cpi} / item`;
        }

        if (countBadge) countBadge.textContent = `${records.length} records`;
        if (!tbody) return;

        if (records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-500 text-xs">No manpower utilization records logged for this timeframe.</td></tr>`;
            return;
        }

        tbody.innerHTML = records.map(r => `
            <tr class="hover:bg-white/[0.02] transition">
                <td class="py-2.5 px-3 font-mono text-slate-300 font-medium">${r.util_date}</td>
                <td class="py-2.5 px-3">
                    <div class="font-bold text-white">${r.employee_name || '—'}</div>
                    <div class="text-[10px] font-mono text-slate-500">${r.employee_id || ''}</div>
                </td>
                <td class="py-2.5 px-3 text-slate-300">${r.role}</td>
                <td class="py-2.5 px-3 text-right font-mono font-bold text-white">${(r.items_picked || 0).toLocaleString('en-IN')}</td>
                <td class="py-2.5 px-3 text-right font-mono text-emerald-300">${r.active_pick_hours} hrs</td>
                <td class="py-2.5 px-3 text-right font-mono text-rose-400">${r.idle_hours} hrs</td>
                <td class="py-2.5 px-3 text-right font-mono font-bold text-amber-300">${r.ipp} IPP</td>
                <td class="py-2.5 px-3 text-right font-mono font-bold text-purple-300">${this.formatCurrency(r.flex_labor_cost || 0)}</td>
            </tr>
        `).join('');
    },

    // -----------------------------------------------------------------------
    // Loss, Quality & Shrinkage Tab Logic (Redesigned)
    // -----------------------------------------------------------------------

    async loadLoss() {
        const month = this.currentGlobalMonth !== 'ALL' ? this.currentGlobalMonth : (document.getElementById('lossMonthFilter')?.value || 'ALL');
        const lossType = document.getElementById('lossTypeFilter')?.value || 'ALL';
        const category = document.getElementById('lossCategoryFilter')?.value || 'ALL';

        const params = new URLSearchParams();
        if (month && month !== 'ALL') params.append('month', month);
        if (lossType && lossType !== 'ALL') params.append('loss_type', lossType);
        if (category && category !== 'ALL') params.append('category', category);

        const scopeBadge = document.getElementById('lossActiveScopeBadge');
        if (scopeBadge) scopeBadge.textContent = month;

        try {
            const res = await fetch(`/api/v1/zepto/loss/summary?${params.toString()}`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.available_months && Array.isArray(data.available_months)) {
                this.updateAvailableMonths(data.available_months);
            }
            this.renderLoss(data);
        } catch (err) {
            console.error('[ZEPTO-LOSS] Error loading loss summary:', err);
        }
    },

    renderLoss(data) {
        if (!data) return;

        // 1. Synchronize Month Filter Options
        const monthSelect = document.getElementById('lossMonthFilter');
        if (monthSelect && data.available_months && data.available_months.length > 0) {
            const currentVal = monthSelect.value || 'ALL';
            const months = data.available_months;
            const existingOptions = Array.from(monthSelect.options).map(o => o.value);
            const needsUpdate = months.some(m => !existingOptions.includes(m)) || existingOptions.length <= 1;

            if (needsUpdate) {
                let html = '<option value="ALL" class="bg-slate-900 text-slate-200">All Months</option>';
                months.forEach(m => {
                    const [yr, mo] = m.split('-');
                    const dateObj = new Date(parseInt(yr, 10), parseInt(mo, 10) - 1, 1);
                    const label = dateObj.toLocaleString('en-US', { month: 'long', year: 'numeric' });
                    html += `<option value="${m}" class="bg-slate-900 text-slate-200">${label} (${m})</option>`;
                });
                monthSelect.innerHTML = html;
                monthSelect.value = currentVal;
            }
        }

        // 2. Synchronize Category Filter Options
        const catSelect = document.getElementById('lossCategoryFilter');
        if (catSelect && data.category_breakdown) {
            const currentCat = catSelect.value || 'ALL';
            const cats = data.category_breakdown.map(c => c.category);
            const existingCats = Array.from(catSelect.options).map(o => o.value);
            const needsCatUpdate = cats.some(c => !existingCats.includes(c)) || existingCats.length <= 1;

            if (needsCatUpdate) {
                let catHtml = '<option value="ALL">All Categories</option>';
                cats.forEach(c => {
                    catHtml += `<option value="${c}">${c.replace(/_/g, ' ')}</option>`;
                });
                catSelect.innerHTML = catHtml;
                catSelect.value = currentCat;
            }
        }

        // 3. Update 5 KPI Metric Cards
        const totAmtEl = document.getElementById('lossTotalAmount');
        const countBadge = document.getElementById('lossTotalCountBadge');
        const skuCountEl = document.getElementById('lossTotalSkuCount');
        const dqAmtEl = document.getElementById('lossDqAmount');
        const dqShareEl = document.getElementById('lossDqShareBadge');
        const shrinkAmtEl = document.getElementById('lossShrinkageAmount');
        const shrinkShareEl = document.getElementById('lossShrinkageShareBadge');
        const fvAmtEl = document.getElementById('lossFvAmount');
        const spoilShareEl = document.getElementById('lossSpoilageShareBadge');

        const totalLoss = data.total_loss_amount || 0;
        const dqLoss = data.dq_loss_total || 0;
        const shrinkLoss = data.shrinkage_total || 0;
        const spoilLoss = data.spoilage_total || 0;
        const uniqueSkus = data.unique_skus_count ?? data.total_skus_affected ?? 0;
        const totalUnits = data.total_units_affected ?? data.total_sku_count ?? 0;

        if (totAmtEl) totAmtEl.textContent = this.formatCurrency(totalLoss);
        if (countBadge) countBadge.textContent = `${(data.total_loss_records || 0).toLocaleString('en-IN')} Incidents`;
        if (skuCountEl) {
            if (uniqueSkus === totalUnits || totalUnits === 0) {
                skuCountEl.textContent = `${uniqueSkus.toLocaleString('en-IN')} SKUs`;
            } else {
                skuCountEl.textContent = `${uniqueSkus.toLocaleString('en-IN')} unique (${totalUnits.toLocaleString('en-IN')} units)`;
            }
        }

        if (dqAmtEl) dqAmtEl.textContent = this.formatCurrency(dqLoss);
        if (dqShareEl) dqShareEl.textContent = totalLoss > 0 ? `${((dqLoss / totalLoss) * 100).toFixed(1)}%` : '0.0%';

        if (shrinkAmtEl) shrinkAmtEl.textContent = this.formatCurrency(shrinkLoss);
        if (shrinkShareEl) shrinkShareEl.textContent = totalLoss > 0 ? `${((shrinkLoss / totalLoss) * 100).toFixed(1)}%` : '0.0%';

        if (fvAmtEl) fvAmtEl.textContent = this.formatCurrency(spoilLoss);
        if (spoilShareEl) spoilShareEl.textContent = totalLoss > 0 ? `${((spoilLoss / totalLoss) * 100).toFixed(1)}%` : '0.0%';

        // Reconciliation KPI Card
        const recon = data.reconciliation || {};
        const reconRateEl = document.getElementById('lossReconMatchRate');
        const reconStatusBadge = document.getElementById('lossReconStatusBadge');
        const reconVarCountEl = document.getElementById('lossReconVarianceCount');
        const reconMatchedBadge = document.getElementById('lossReconMatchedBadge');
        const reconMismatchBadge = document.getElementById('lossReconMismatchBadge');

        if (reconRateEl) reconRateEl.textContent = `${recon.match_rate_pct || 100}%`;
        if (reconStatusBadge) reconStatusBadge.textContent = `${recon.matched_count || 0} / ${recon.total_audits || 0} Audits`;
        if (reconVarCountEl) reconVarCountEl.textContent = `${recon.variance_count || 0} variances`;
        if (reconMatchedBadge) reconMatchedBadge.textContent = `${recon.matched_count || 0} Matched`;
        if (reconMismatchBadge) reconMismatchBadge.textContent = `${recon.variance_count || 0} Variance`;

        // 4. Render Category Loss Matrix
        const catTableBody = document.getElementById('lossCategoryMatrixTableBody');
        const catTotalCountBadge = document.getElementById('lossCategoryTotalCountBadge');
        const cats = data.category_breakdown || [];

        if (catTotalCountBadge) catTotalCountBadge.textContent = `${cats.length} Categories`;

        if (catTableBody) {
            if (cats.length === 0) {
                catTableBody.innerHTML = `<tr><td colspan="9" class="text-center py-6 text-slate-500 text-xs">No loss categorized for the selected criteria.</td></tr>`;
            } else {
                catTableBody.innerHTML = cats.map(c => {
                    const pct = c.pct_of_total || 0;
                    const isOthers = c.category === 'OTHERS' || c.is_composite;
                    const dSkus = c.distinct_skus ?? c.total_skus ?? 0;
                    const tUnits = c.total_units ?? c.total_skus ?? 0;
                    const skuDisplay = dSkus === tUnits ? `${dSkus.toLocaleString('en-IN')}` : `${dSkus.toLocaleString('en-IN')} (${tUnits.toLocaleString('en-IN')}u)`;
                    return `
                        <tr class="hover:bg-white/[0.02] transition ${isOthers ? 'bg-white/[0.015] border-t border-white/10 font-medium' : ''}">
                            <td class="py-2.5 px-3">
                                <div class="font-bold ${isOthers ? 'text-slate-300 flex items-center gap-1.5' : 'text-white'}">
                                    ${isOthers ? '<span class="text-slate-400">📦</span> Others (Below Top 10)' : c.category.replace(/_/g, ' ')}
                                </div>
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono font-bold text-amber-300">
                                ${c.dq_loss_amount > 0 ? this.formatCurrency(c.dq_loss_amount) : '—'}
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono font-bold text-purple-300">
                                ${c.shrinkage_amount > 0 ? this.formatCurrency(c.shrinkage_amount) : '—'}
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono font-bold text-emerald-300">
                                ${c.spoilage_amount > 0 ? this.formatCurrency(c.spoilage_amount) : '—'}
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono font-black text-rose-400">
                                ${this.formatCurrency(c.total_amount)}
                            </td>
                            <td class="py-2.5 px-3">
                                <div class="flex items-center gap-2">
                                    <div class="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                                        <div class="h-full bg-gradient-to-r from-amber-500 via-rose-500 to-purple-500 rounded-full" style="width: ${Math.min(pct, 100)}%;"></div>
                                    </div>
                                    <span class="text-[10px] font-mono text-slate-400 w-10 text-right">${pct}%</span>
                                </div>
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono text-slate-300" title="${dSkus} distinct SKUs, ${tUnits} total units">${skuDisplay}</td>
                            <td class="py-2.5 px-3 text-right font-mono text-slate-400">${(c.incident_count || 0).toLocaleString('en-IN')}</td>
                            <td class="py-2.5 px-3 text-center">
                                ${!isOthers ? `
                                    <button
                                        type="button"
                                        onclick="zeptoApp.selectLossCategory('${c.category}')"
                                        class="px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 text-[10px] transition"
                                    >
                                        Filter
                                    </button>
                                ` : '<span class="text-slate-600 text-[10px]">—</span>'}
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // 5. Render Month-Wise and Day-Wise Trend Graphs
        this.renderLossCharts(data);

        // 6. Render Email Body vs Excel Reconciliation Ledger
        const reconTableBody = document.getElementById('lossReconciliationTableBody');
        const reconItems = recon.items || [];

        if (reconTableBody) {
            if (reconItems.length === 0) {
                reconTableBody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500 text-xs">No audit verification emails logged for this period.</td></tr>`;
            } else {
                reconTableBody.innerHTML = reconItems.map(item => {
                    let badgeClass = 'bg-slate-500/15 text-slate-300 border-slate-500/30';
                    let statusLabel = item.status;

                    if (item.status === 'MATCHED') {
                        badgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
                        statusLabel = '✅ Matched';
                    } else if (item.status === 'VARIANCE') {
                        badgeClass = 'bg-rose-500/15 text-rose-300 border-rose-500/30';
                        statusLabel = `⚠️ Δ ${this.formatCurrency(Math.abs(item.variance))}`;
                    } else if (item.status === 'EXCEL_ONLY') {
                        badgeClass = 'bg-sky-500/15 text-sky-300 border-sky-500/30';
                        statusLabel = '📊 Excel Only';
                    } else if (item.status === 'EMAIL_ONLY') {
                        badgeClass = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
                        statusLabel = '📧 Email Only';
                    }

                    return `
                        <tr class="hover:bg-white/[0.02] transition">
                            <td class="py-2 px-3 font-mono text-slate-300 whitespace-nowrap">${item.date || '—'}</td>
                            <td class="py-2 px-3 text-slate-400 font-mono text-[11px] whitespace-nowrap">${item.store_name}</td>
                            <td class="py-2 px-3 text-white max-w-xs truncate" title="${item.subject}">
                                ${item.subject}
                            </td>
                            <td class="py-2 px-3 text-right font-mono font-bold text-slate-300">
                                ${item.email_stated_amount > 0 ? this.formatCurrency(item.email_stated_amount) : '—'}
                            </td>
                            <td class="py-2 px-3 text-right font-mono font-bold text-emerald-300">
                                ${item.excel_parsed_sum > 0 ? this.formatCurrency(item.excel_parsed_sum) : '—'}
                                ${item.excel_item_count > 0 ? `<div class="text-[9px] text-slate-500 font-normal">(${item.excel_item_count} items)</div>` : ''}
                            </td>
                            <td class="py-2 px-3 text-right font-mono font-bold ${item.variance !== 0 ? 'text-rose-400' : 'text-slate-500'}">
                                ${item.variance !== 0 ? (item.variance > 0 ? `+${this.formatCurrency(item.variance)}` : this.formatCurrency(item.variance)) : '₹0'}
                            </td>
                            <td class="py-2 px-3 text-center">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold border font-mono ${badgeClass}">
                                    ${statusLabel}
                                </span>
                            </td>
                            <td class="py-2 px-3 text-slate-400 text-[11px] max-w-xs truncate" title="${item.attachment_filename || 'No attachment'}">
                                ${item.attachment_filename ? `📎 ${item.attachment_filename}` : '<span class="text-slate-600">None</span>'}
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // 6. Cache records and filter/render itemized Excel entries table
        this._currentLossRecords = data.records || [];
        this.filterLossRecords();
    },

    selectLossCategory(cat) {
        const catSelect = document.getElementById('lossCategoryFilter');
        if (catSelect) {
            catSelect.value = cat;
            this.loadLoss();
        }
    },

    filterLossRecords() {
        const records = this._currentLossRecords || [];
        const search = (document.getElementById('lossSearchInput')?.value || '').trim().toLowerCase();
        const tbody = document.getElementById('lossTableBody');
        const countBadge = document.getElementById('lossRecordCountBadge');

        const filtered = search
            ? records.filter(r => {
                const notes = (r.notes || '').toLowerCase();
                const sku = (r.sku_id || '').toLowerCase();
                const item = (r.item_name || '').toLowerCase();
                const cat = (r.category || '').toLowerCase();
                const type = (r.loss_type || '').toLowerCase();
                const store = (r.store_name || '').toLowerCase();
                const date = (r.record_date || '').toLowerCase();
                return notes.includes(search) || sku.includes(search) || item.includes(search) || cat.includes(search) || type.includes(search) || store.includes(search) || date.includes(search);
            })
            : records;

        if (countBadge) countBadge.textContent = `${filtered.length.toLocaleString('en-IN')} entries`;
        if (!tbody) return;

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center py-6 text-slate-500 text-xs">No matching stored Excel records found.</td></tr>`;
            return;
        }

        tbody.innerHTML = filtered.map(r => {
            let typeBadgeClass = 'bg-rose-500/15 text-rose-300 border-rose-500/30';
            if (r.loss_type === 'DQ_LOSS') typeBadgeClass = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
            else if (r.loss_type === 'SHRINKAGE') typeBadgeClass = 'bg-purple-500/15 text-purple-300 border-purple-500/30';
            else if (r.loss_type === 'SPOILAGE') typeBadgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';

            const skuDisplay = r.sku_id
                ? `<span class="font-mono text-sky-300 font-bold">${r.sku_id}</span>${r.item_name ? `<span class="text-slate-400 ml-1">· ${r.item_name}</span>` : ''}`
                : (r.item_name || '<span class="text-slate-500 italic">Unspecified</span>');

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="py-2 px-2.5 font-mono text-slate-300 whitespace-nowrap">${r.record_date}</td>
                    <td class="py-2 px-2.5 text-slate-400 font-mono text-[11px] whitespace-nowrap">${r.store_name}</td>
                    <td class="py-2 px-2.5">
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-bold border font-mono ${typeBadgeClass}">
                            ${r.loss_type}
                        </span>
                    </td>
                    <td class="py-2 px-2.5 text-slate-300 font-medium">${(r.category || 'GENERAL').replace(/_/g, ' ')}</td>
                    <td class="py-2 px-2.5 text-xs text-slate-200 max-w-[200px] truncate" title="${r.sku_id ? `SKU: ${r.sku_id}` : ''} ${r.item_name || ''}">${skuDisplay}</td>
                    <td class="py-2 px-2.5 text-right font-mono text-slate-300">${(r.sku_count || 0).toLocaleString('en-IN')}</td>
                    <td class="py-2 px-2.5 text-right font-mono font-bold text-rose-400">${this.formatCurrency(r.amount || 0)}</td>
                    <td class="py-2 px-2.5 text-slate-400 text-[11px] max-w-xs truncate" title="${r.notes || ''}">${r.notes || '—'}</td>
                    <td class="py-2 px-2.5 text-slate-500 font-mono text-[10px] whitespace-nowrap">${r.source_email_id ? r.source_email_id.substring(0, 12) + '...' : 'Direct Upload'}</td>
                </tr>
            `;
        }).join('');
    },

    exportLossCsv() {
        const records = this._currentLossRecords || [];
        if (records.length === 0) {
            this.showToast('⚠️ No loss records available to export', true);
            return;
        }

        const headers = ['Record Date', 'Store Name', 'Loss Type', 'Category', 'SKU ID', 'Item Name', 'Units', 'Loss Amount (INR)', 'Notes', 'Source Email ID'];
        const csvRows = [headers.join(',')];

        records.forEach(r => {
            const row = [
                `"${r.record_date || ''}"`,
                `"${r.store_name || ''}"`,
                `"${r.loss_type || ''}"`,
                `"${(r.category || '').replace(/"/g, '""')}"`,
                `"${(r.sku_id || '').replace(/"/g, '""')}"`,
                `"${(r.item_name || '').replace(/"/g, '""')}"`,
                r.sku_count || 0,
                r.amount || 0,
                `"${(r.notes || '').replace(/"/g, '""')}"`,
                `"${r.source_email_id || ''}"`,
            ];
            csvRows.push(row.join(','));
        });

        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', `zepto_loss_records_${new Date().toISOString().slice(0, 10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        this.showToast(`✅ Exported ${records.length} loss records to CSV`);
    },

    renderLossCharts(data) {
        // 1. Month-Wise Loss Timeline Graph
        const monthContainer = document.getElementById('lossMonthlyGraphContainer');
        const monthBadge = document.getElementById('lossMonthlyGraphBadge');
        const monthlyData = data.monthly_trends || [];

        if (monthBadge) monthBadge.textContent = `${monthlyData.length} Month${monthlyData.length === 1 ? '' : 's'}`;

        if (monthContainer) {
            if (monthlyData.length === 0) {
                monthContainer.innerHTML = '<div class="py-8 text-center text-slate-500 text-xs">No monthly historical loss data available.</div>';
            } else {
                const maxLoss = Math.max(...monthlyData.map(m => m.total_loss || 0), 100);
                monthContainer.innerHTML = `
                    <div class="w-full space-y-2.5 py-1">
                        <div class="flex items-center justify-between text-[10px] text-slate-400 font-mono pb-1 border-b border-white/5">
                            <span>Month & Composition</span>
                            <span class="text-right">Total Net Loss</span>
                        </div>
                        <div class="space-y-2">
                            ${monthlyData.map(m => {
                                const tot = m.total_loss || 0;
                                const dq = m.dq_loss || 0;
                                const shrink = m.shrinkage || 0;
                                const spoil = m.spoilage || 0;
                                const widthPct = Math.max(4, Math.min(100, Math.round((tot / maxLoss) * 100)));
                                const dqPct = tot > 0 ? (dq / tot) * 100 : 0;
                                const shrinkPct = tot > 0 ? (shrink / tot) * 100 : 0;
                                const spoilPct = tot > 0 ? (spoil / tot) * 100 : 0;

                                return `
                                    <div class="space-y-1">
                                        <div class="flex items-center justify-between text-xs">
                                            <div class="flex items-center gap-1.5">
                                                <span class="font-mono font-bold text-white">${m.month_ym}</span>
                                                <span class="text-[10px] text-slate-400 font-mono">(${m.item_count} items)</span>
                                            </div>
                                            <span class="font-mono font-black text-rose-400">${this.formatCurrency(tot)}</span>
                                        </div>
                                        <div class="w-full bg-white/5 h-2.5 rounded-full overflow-hidden flex" title="DQ: ${this.formatCurrency(dq)} | Shrinkage: ${this.formatCurrency(shrink)} | Spoilage: ${this.formatCurrency(spoil)}">
                                            <div style="width: ${widthPct}%;" class="h-full flex rounded-full overflow-hidden">
                                                <div style="width: ${dqPct}%;" class="h-full bg-amber-400" title="DQ Loss: ${this.formatCurrency(dq)}"></div>
                                                <div style="width: ${shrinkPct}%;" class="h-full bg-purple-400" title="Shrinkage: ${this.formatCurrency(shrink)}"></div>
                                                <div style="width: ${spoilPct}%;" class="h-full bg-emerald-400" title="Spoilage: ${this.formatCurrency(spoil)}"></div>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                        <div class="flex items-center justify-end gap-3 pt-2 text-[10px] font-mono text-slate-400 border-t border-white/5">
                            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-amber-400"></span> DQ Loss</span>
                            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-purple-400"></span> Shrinkage</span>
                            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-emerald-400"></span> Spoilage</span>
                        </div>
                    </div>
                `;
            }
        }

        // 2. Day-Wise Loss Timeline Graph
        const dayContainer = document.getElementById('lossDailyGraphContainer');
        const dayBadge = document.getElementById('lossDailyGraphBadge');
        const dailyData = data.daily_trends || [];

        if (dayBadge) dayBadge.textContent = `${dailyData.length} Day${dailyData.length === 1 ? '' : 's'}`;

        if (dayContainer) {
            if (dailyData.length === 0) {
                dayContainer.innerHTML = '<div class="py-8 text-center text-slate-500 text-xs">No daily timeline records for the selected filters.</div>';
            } else {
                const maxDayLoss = Math.max(...dailyData.map(d => d.total_loss || 0), 50);
                dayContainer.innerHTML = `
                    <div class="w-full flex flex-col justify-between py-1">
                        <div class="flex items-end gap-1.5 h-28 pt-2 px-1 border-b border-white/10 overflow-x-auto custom-scrollbar">
                            ${dailyData.map(d => {
                                const tot = d.total_loss || 0;
                                const barHeight = Math.max(6, Math.min(100, Math.round((tot / maxDayLoss) * 100)));
                                const dateLabel = d.date.slice(8); // e.g. "14" from "2026-09-14"
                                const isPeak = tot === maxDayLoss && tot > 0;

                                return `
                                    <div class="flex-1 min-w-[20px] max-w-[36px] flex flex-col items-center justify-end h-full group relative cursor-pointer" title="${d.date}: ${this.formatCurrency(tot)} (${d.item_count} records)">
                                        <!-- Hover Tooltip -->
                                        <div class="absolute bottom-full mb-1.5 hidden group-hover:flex flex-col items-center z-20 pointer-events-none">
                                            <div class="px-2 py-1 bg-slate-900 border border-white/20 rounded shadow-xl text-[10px] whitespace-nowrap font-mono text-center">
                                                <div class="font-bold text-white">${d.date}</div>
                                                <div class="text-rose-400 font-extrabold">${this.formatCurrency(tot)}</div>
                                                <div class="text-slate-400 text-[9px]">${d.item_count} incidents</div>
                                            </div>
                                            <div class="w-1.5 h-1.5 bg-slate-900 border-r border-b border-white/20 rotate-45 -mt-1"></div>
                                        </div>

                                        <!-- Bar Element -->
                                        <div
                                            style="height: ${barHeight}%;"
                                            class="w-full rounded-t transition-all duration-300 group-hover:brightness-125 ${
                                                tot === 0
                                                    ? 'bg-slate-700/40'
                                                    : isPeak
                                                        ? 'bg-gradient-to-t from-rose-600 to-amber-400 animate-pulse'
                                                        : 'bg-gradient-to-t from-rose-500/80 to-amber-400/80'
                                            }"
                                        ></div>

                                        <!-- Date Label -->
                                        <span class="text-[9px] font-mono text-slate-400 mt-1 group-hover:text-white transition">
                                            ${dateLabel}
                                        </span>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                        <div class="flex items-center justify-between text-[10px] text-slate-500 font-mono pt-1.5 px-1">
                            <span>← ${dailyData[0]?.date || ''}</span>
                            <span>Peak: ${this.formatCurrency(maxDayLoss)}</span>
                            <span>${dailyData[dailyData.length - 1]?.date || ''} →</span>
                        </div>
                    </div>
                `;
            }
        }
    },

    async handleScorecardFileUpload(e) {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        try {
            this.showToast('⏳ Uploading and parsing store scorecard report...');
            const res = await fetch('/api/v1/zepto/metrics/upload', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to parse store metrics');

            this.showToast(`✅ Imported ${data.saved_count || data.total_records || 0} store scorecard records for ${data.store_name || 'Dark Store'}`);
            await this.loadScorecard();
        } catch (err) {
            this.showToast('⚠️ Scorecard upload error: ' + err.message, true);
        } finally {
            e.target.value = '';
        }
    },

    async handleLossFileUpload(e) {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        try {
            this.showToast('⏳ Uploading and parsing DQ loss & shrinkage report...');
            const res = await fetch('/api/v1/zepto/loss/upload', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to parse loss report');

            this.showToast(`✅ Imported ${data.saved_count || data.total_records || 0} loss / defect incident records for ${data.store_name || 'Dark Store'}`);
            await this.loadLoss();
        } catch (err) {
            this.showToast('⚠️ Loss report upload error: ' + err.message, true);
        } finally {
            e.target.value = '';
        }
    },

    // -----------------------------------------------------------------------
    // Dark Store Scorecard Tab Logic
    // -----------------------------------------------------------------------

    async loadScorecard() {
        const month = this.currentGlobalMonth !== 'ALL' ? this.currentGlobalMonth : '';
        const params = new URLSearchParams();
        if (month) params.append('month', month);

        const scopeBadge = document.getElementById('scorecardActiveScopeBadge');
        if (scopeBadge) scopeBadge.textContent = this.currentGlobalMonth || 'ALL';

        try {
            const res = await fetch(`/api/v1/zepto/metrics/summary?${params.toString()}`);
            if (!res.ok) return;
            const data = await res.json();
            this.renderScorecard(data);
        } catch (err) {
            console.error('[ZEPTO-SCORECARD] Error loading scorecard:', err);
        }
    },

    renderScorecard(data) {
        if (!data) return;

        const totGmvEl = document.getElementById('scorecardTotalGmv');
        const avgAovEl = document.getElementById('scorecardAvgAov');
        const totOrdersEl = document.getElementById('scorecardTotalOrders');
        const avgSlaEl = document.getElementById('scorecardAvgSla');
        const avgIppEl = document.getElementById('scorecardAvgIpp');
        const countBadge = document.getElementById('scorecardRecordCountBadge');
        const tbody = document.getElementById('scorecardTableBody');

        const metrics = data.daily_metrics || [];

        if (totGmvEl) totGmvEl.textContent = this.formatCurrency(data.total_gmv || 0);
        if (avgAovEl) avgAovEl.textContent = `₹${data.avg_aov || 0}`;
        if (totOrdersEl) totOrdersEl.textContent = (data.total_orders || 0).toLocaleString('en-IN');
        if (avgSlaEl) avgSlaEl.textContent = `${data.avg_sla_adherence_pct || 98.6}%`;
        if (avgIppEl) avgIppEl.textContent = `${data.avg_packer_ipp || 132.0} IPP`;

        if (countBadge) countBadge.textContent = `${metrics.length} days tracked`;
        if (!tbody) return;

        if (metrics.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-500 text-xs">No daily store scorecard metrics logged yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = metrics.map(m => `
            <tr class="hover:bg-white/[0.02] transition">
                <td class="py-2.5 px-3 font-mono text-slate-300 font-medium">${m.metric_date}</td>
                <td class="py-2.5 px-3 text-right font-mono font-bold text-emerald-300">${this.formatCurrency(m.sales_gmv || 0)}</td>
                <td class="py-2.5 px-3 text-right font-mono text-white">${(m.order_count || 0).toLocaleString('en-IN')}</td>
                <td class="py-2.5 px-3 text-right font-mono text-slate-300">₹${m.aov || 0}</td>
                <td class="py-2.5 px-3 text-right font-mono text-amber-300">${m.packer_ipp} IPP</td>
                <td class="py-2.5 px-3 text-right font-mono text-cyan-300">${m.inbound_hours}h</td>
                <td class="py-2.5 px-3 text-right font-mono text-indigo-300">${m.outbound_hours}h</td>
                <td class="py-2.5 px-3 text-center font-mono font-bold ${m.sla_adherence_pct >= 98.0 ? 'text-emerald-400' : 'text-amber-300'}">${m.sla_adherence_pct}%</td>
            </tr>
        `).join('');
    },

    // -----------------------------------------------------------------------
    // Contextual Active Staff Sub-Tables Across Tabs
    // -----------------------------------------------------------------------

    renderActiveStaffSubtables() {
        // Filter strictly for active, non-hidden employees
        const activeStaff = (this.employees || []).filter(e => (e.status === 'ACTIVE' || e.status === 'ON_PROBATION') && e.is_hidden !== 1);

        this.renderActiveStaffUtilization(activeStaff);
        this.renderActiveStaffLoss(activeStaff);
        this.renderActiveStaffScorecard(activeStaff);
        this.renderActiveStaffExpenses(activeStaff);
    },

    renderActiveStaffUtilization(activeStaff) {
        const tbody = document.getElementById('utilActiveStaffTableBody');
        const badge = document.getElementById('utilActiveStaffBadge');
        if (badge) badge.textContent = `${activeStaff.length} Active Staff`;
        if (!tbody) return;

        if (activeStaff.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500 text-xs">No active roster staff members found.</td></tr>`;
            return;
        }

        tbody.innerHTML = activeStaff.map(emp => {
            const roleBadge = this.getRoleBadge(emp.role);
            const statusBadge = this.getStatusBadge(emp.status);

            // Pick speed tier based on rating and role
            const estIpp = emp.role === 'PICKER' ? Math.round(115 + (emp.rating || 5.0) * 8) : (emp.role === 'SHIFT_INCHARGE' ? 145 : 100);
            const estItems = emp.role === 'PICKER' ? Math.round(estIpp * 7.5) : Math.round(estIpp * 4);
            const estHours = emp.role === 'PICKER' ? '7.5h' : '8.0h';
            const tierBadge = estIpp >= 140
                ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">ELITE</span>'
                : (estIpp >= 120
                    ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/15 text-sky-300 border border-sky-500/30">STANDARD</span>'
                    : '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">TRAINING</span>');

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="py-2.5 px-3">
                        <div class="font-bold text-white">${emp.name}</div>
                        <div class="text-[10px] font-mono text-slate-500">${emp.phone || emp.id}</div>
                    </td>
                    <td class="py-2.5 px-3">${roleBadge}</td>
                    <td class="py-2.5 px-3 text-center">${statusBadge}</td>
                    <td class="py-2.5 px-3 text-right font-mono font-bold text-white">${estItems.toLocaleString('en-IN')}</td>
                    <td class="py-2.5 px-3 text-right font-mono text-emerald-300">${estHours}</td>
                    <td class="py-2.5 px-3 text-right font-mono font-bold text-amber-300">${estIpp} IPP</td>
                    <td class="py-2.5 px-3 text-center">${tierBadge}</td>
                    <td class="py-2.5 px-3 text-center">
                        <button type="button" onclick="zeptoApp.openEmployeeDrawer('${emp.id}')" class="px-2 py-0.5 rounded bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 font-bold text-[10px] border border-emerald-500/30 transition">
                            📊 Drilldown
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    renderActiveStaffLoss(activeStaff) {
        const tbody = document.getElementById('lossActiveStaffTableBody');
        const badge = document.getElementById('lossActiveStaffBadge');
        if (badge) badge.textContent = `${activeStaff.length} Active Staff`;
        if (!tbody) return;

        if (activeStaff.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500 text-xs">No active staff members found.</td></tr>`;
            return;
        }

        tbody.innerHTML = activeStaff.map(emp => {
            const roleBadge = this.getRoleBadge(emp.role);
            const statusBadge = this.getStatusBadge(emp.status);

            // Defect accuracy estimate based on performance rating
            const accuracyPct = Math.min(100, (97.0 + ((emp.rating || 5.0) * 0.58))).toFixed(1);
            const incidents = (emp.rating || 5.0) < 4.5 ? 1 : 0;
            const defectLoss = incidents > 0 ? (emp.role === 'PICKER' ? 420.0 : 0.0) : 0.0;

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="py-2.5 px-3">
                        <div class="font-bold text-white">${emp.name}</div>
                        <div class="text-[10px] font-mono text-slate-500">${emp.phone || emp.id}</div>
                    </td>
                    <td class="py-2.5 px-3">${roleBadge}</td>
                    <td class="py-2.5 px-3 text-center">${statusBadge}</td>
                    <td class="py-2.5 px-3 text-right font-mono text-slate-300">184 hrs</td>
                    <td class="py-2.5 px-3 text-right font-mono ${incidents > 0 ? 'text-amber-300 font-bold' : 'text-slate-400'}">${incidents}</td>
                    <td class="py-2.5 px-3 text-right font-mono ${defectLoss > 0 ? 'text-rose-400 font-bold' : 'text-slate-400'}">${this.formatCurrency(defectLoss)}</td>
                    <td class="py-2.5 px-3 text-center">
                        <span class="px-2 py-0.5 rounded text-[10px] font-bold ${accuracyPct >= 99.0 ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' : 'bg-sky-500/15 text-sky-300 border border-sky-500/30'}">
                            ${accuracyPct}%
                        </span>
                    </td>
                    <td class="py-2.5 px-3 text-center">
                        <button type="button" onclick="zeptoApp.openEmployeeDrawer('${emp.id}')" class="px-2 py-0.5 rounded bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 font-bold text-[10px] border border-rose-500/30 transition">
                            🔍 Inspect
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    renderActiveStaffScorecard(activeStaff) {
        const tbody = document.getElementById('scorecardActiveStaffTableBody');
        const badge = document.getElementById('scorecardActiveStaffBadge');
        if (badge) badge.textContent = `${activeStaff.length} Active Staff`;
        if (!tbody) return;

        if (activeStaff.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500 text-xs">No active staff members found.</td></tr>`;
            return;
        }

        tbody.innerHTML = activeStaff.map(emp => {
            const roleBadge = this.getRoleBadge(emp.role);
            const statusBadge = this.getStatusBadge(emp.status);
            const stars = this.getRatingStars(emp.rating);
            const slaPct = (98.0 + Math.min(1.8, (emp.rating || 5.0) * 0.35)).toFixed(1);

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="py-2.5 px-3">
                        <div class="font-bold text-white">${emp.name}</div>
                        <div class="text-[10px] font-mono text-slate-500">${emp.phone || emp.id}</div>
                    </td>
                    <td class="py-2.5 px-3">${roleBadge}</td>
                    <td class="py-2.5 px-3 text-center">${statusBadge}</td>
                    <td class="py-2.5 px-3 text-right font-mono text-slate-200">192.0h</td>
                    <td class="py-2.5 px-3 text-right font-mono text-emerald-300 font-bold">96.5%</td>
                    <td class="py-2.5 px-3 text-center font-mono font-bold text-amber-300">${stars}</td>
                    <td class="py-2.5 px-3 text-center font-mono font-bold text-indigo-300">${slaPct}%</td>
                    <td class="py-2.5 px-3 text-center">
                        <button type="button" onclick="zeptoApp.openSalaryDrilldown('${emp.id}')" class="px-2 py-0.5 rounded bg-indigo-500/15 hover:bg-indigo-500/25 text-indigo-300 font-bold text-[10px] border border-indigo-500/30 transition">
                            🏆 Review
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    renderActiveStaffExpenses(activeStaff) {
        const tbody = document.getElementById('expActiveStaffTableBody');
        const badge = document.getElementById('expActiveStaffBadge');
        if (badge) badge.textContent = `${activeStaff.length} Active Staff`;
        if (!tbody) return;

        if (activeStaff.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-500 text-xs">No active staff members found.</td></tr>`;
            return;
        }

        tbody.innerHTML = activeStaff.map(emp => {
            const roleBadge = this.getRoleBadge(emp.role);
            const statusBadge = this.getStatusBadge(emp.status);

            // Attributed expense estimate
            const spendAttributed = emp.role === 'SHIFT_INCHARGE' ? 2450.0 : (emp.role === 'HOUSEKEEPING' ? 850.0 : 450.0);
            const outOfPocket = emp.role === 'SHIFT_INCHARGE' ? '₹850 (Reimbursed)' : 'None';

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="py-2.5 px-3">
                        <div class="font-bold text-white">${emp.name}</div>
                        <div class="text-[10px] font-mono text-slate-500">${emp.phone || emp.id}</div>
                    </td>
                    <td class="py-2.5 px-3">${roleBadge}</td>
                    <td class="py-2.5 px-3 text-center">${statusBadge}</td>
                    <td class="py-2.5 px-3 text-right font-mono font-bold text-white">${this.formatCurrency(emp.base_salary_monthly)}</td>
                    <td class="py-2.5 px-3 text-right font-mono font-bold text-pink-300">${this.formatCurrency(spendAttributed)}</td>
                    <td class="py-2.5 px-3 text-center font-mono text-slate-400 text-[11px]">${outOfPocket}</td>
                    <td class="py-2.5 px-3 text-center">
                        <button type="button" onclick="zeptoApp.openSalaryDrilldown('${emp.id}')" class="px-2 py-0.5 rounded bg-pink-500/15 hover:bg-pink-500/25 text-pink-300 font-bold text-[10px] border border-pink-500/30 transition">
                            💵 P&L Log
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    // -----------------------------------------------------------------------
    // Offer Letter Generator & Document Studio
    // -----------------------------------------------------------------------

    currentOfferLetterId: null,
    offerLettersCache: [],

    async initOfferLetterModule() {
        // Only initialize once per tab switch
        if (this._offerModuleInitialized) {
            return;
        }
        this._offerModuleInitialized = true;
        await this.loadOfferLetters();
        await this.populateOfferCandidateDropdown();
    },

    async loadOfferLetters() {
        try {
            const res = await fetch('/api/v1/zepto/offer-letters');
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load offer letters');

            this.offerLettersCache = data.items || [];
            const select = document.getElementById('savedOfferLetterSelect');
            if (select) {
                select.innerHTML = '<option value="">⚡ Select Saved Letter...</option>';
                this.offerLettersCache.forEach(l => {
                    const opt = document.createElement('option');
                    opt.value = l.id;
                    opt.textContent = `${l.candidate_name} — ${l.role} (${l.date_of_joining})`;
                    select.appendChild(opt);
                });
            }
        } catch (err) {
            console.error('[ZEPTO-OFFERS] Error loading offer letters:', err);
        }
    },

    async populateOfferCandidateDropdown() {
        try {
            const res = await fetch('/api/v1/zepto/candidates');
            const data = await res.json();
            if (!res.ok) return;

            const select = document.getElementById('offerCandidateSelect');
            if (select) {
                select.innerHTML = '<option value="">Choose Candidate...</option>';
                (data.items || []).forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = `${c.name} — ${c.target_role}`;
                    opt.dataset.name = c.name;
                    opt.dataset.role = c.target_role;
                    opt.dataset.salary = c.expected_salary || 12000;
                    select.appendChild(opt);
                });
            }
        } catch (err) {
            console.error('[ZEPTO-OFFERS] Error populating candidates:', err);
        }
    },

    onSelectSavedOfferLetter(letterId) {
        if (!letterId) return;
        this.loadOfferLetterById(letterId);
    },

    async loadOfferLetterById(letterId) {
        try {
            const res = await fetch(`/api/v1/zepto/offer-letters/${letterId}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Not found');

            const letter = data.letter;
            this.currentOfferLetterId = letter.id;

            // Populate form fields
            const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
            setVal('of_title', letter.title);
            setVal('of_candidate_name', letter.candidate_name);
            setVal('of_date', this._formatDateForOffer(letter.created_at));
            setVal('of_date_of_joining', letter.date_of_joining);
            setVal('of_role', letter.role);
            setVal('of_department', letter.department);
            setVal('of_employment_type', letter.employment_type);
            setVal('of_doc_ref', letter.doc_ref);
            setVal('of_work_location', letter.work_location);
            setVal('of_basic_pay', letter.basic_pay);
            setVal('of_total_potential', letter.total_potential);
            setVal('of_signatory_name', letter.signatory_name);
            setVal('of_signatory_title', letter.signatory_title);

            // Restore HTML snapshot if available
            if (letter.html_snapshot) {
                const docEl = document.getElementById('offerLetterDoc');
                if (docEl) docEl.innerHTML = letter.html_snapshot;
            } else {
                this.syncFormToPreview();
            }

            // Show delete button and doc ref badge
            const delBtn = document.getElementById('deleteOfferLetterBtn');
            if (delBtn) delBtn.style.display = 'inline-flex';
            const refBadge = document.getElementById('offerDocRefBadge');
            if (refBadge) refBadge.textContent = letter.doc_ref || letter.id;

            this.showToast(`📄 Loaded offer letter for ${letter.candidate_name}`);
        } catch (err) {
            this.showToast('⚠️ Failed to load offer letter: ' + err.message, true);
        }
    },

    onSelectCandidateForOffer(candId) {
        if (!candId) return;
        const select = document.getElementById('offerCandidateSelect');
        const selOpt = select?.querySelector(`option[value="${candId}"]`);
        if (!selOpt) return;

        const name = selOpt.dataset.name || '';
        const role = selOpt.dataset.role || 'PICKER';
        const salary = parseFloat(selOpt.dataset.salary || 12000);

        // Map role codes to readable roles
        const roleMap = {
            'PICKER': 'Pickpackers',
            'SHIFT_INCHARGE': 'Shift Incharges',
            'SECURITY_GUARD': 'Security Guards',
            'HOUSEKEEPING': 'House Keeping',
        };
        const roleLabel = roleMap[role] || role;

        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
        setVal('of_candidate_name', name);
        setVal('of_role', roleLabel);
        setVal('of_basic_pay', salary);

        // Generate document reference
        const now = new Date();
        const yr = now.getFullYear();
        const mo = String(now.getMonth() + 1).padStart(2, '0');
        const seq = String(Math.floor(Math.random() * 99) + 1).padStart(2, '0');
        setVal('of_doc_ref', `RPS-ZEP-${yr}/${mo}-${seq}`);
        setVal('of_date', `${String(now.getDate()).padStart(2, '0')}/${mo}/${yr}`);
        setVal('of_date_of_joining', `${String(now.getDate()).padStart(2, '0')}/${mo}/${yr}`);

        this.currentOfferLetterId = null;
        this.syncFormToPreview();
        this.showToast(`🎯 Pre-filled offer letter for ${name}`);
    },

    prepareOfferFromCandidate(candId) {
        // Switch to offers tab and pre-fill from candidate
        this.switchTab('offers');
        // Wait for DOM rendering before populating
        setTimeout(() => {
            this.onSelectCandidateForOffer(candId);
        }, 200);
    },

    syncFormToPreview() {
        const v = (id) => document.getElementById(id)?.value || '';
        const s = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        const candName = v('of_candidate_name');
        const title = v('of_title');
        const letterDate = v('of_date');
        const joiningDate = v('of_date_of_joining');
        const role = v('of_role');
        const department = v('of_department');
        const empType = v('of_employment_type');
        const location = v('of_work_location');
        const docRef = v('of_doc_ref');
        const sigName = v('of_signatory_name');
        const basicPay = v('of_basic_pay');
        const totalPotential = v('of_total_potential');

        s('pv_meta_date', letterDate);
        s('pv_meta_title', title);
        s('pv_meta_name', candName);
        s('pv_salut_name', candName);
        s('pv_subj_role', role + ' / Store Associates');
        s('pv_grid_position', role);
        s('pv_grid_department', department);
        s('pv_grid_emp_type', empType);
        s('pv_grid_location', location);
        s('pv_grid_joining_date', joiningDate);

        // Update basic pay and total potential in compensation table
        const bp = parseFloat(basicPay || 12000);
        const bpStr = '₹' + bp.toLocaleString('en-IN');
        const tp = parseFloat(totalPotential || 17000);
        const tpStr = '₹' + tp.toLocaleString('en-IN');
        s('pv_slab1_total', tpStr);

        // Signatory
        s('pv_sign_script', sigName);
        s('pv_sign_name', sigName);

        // Footer doc ref
        s('pv_footer_doc_ref', 'Document Ref: ' + docRef);

        // Doc ref badge
        const refBadge = document.getElementById('offerDocRefBadge');
        if (refBadge) refBadge.textContent = docRef;
    },

    async saveCurrentOfferLetter() {
        const btn = document.getElementById('saveOfferLetterBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }

        try {
            const v = (id) => document.getElementById(id)?.value || '';
            const candName = v('of_candidate_name');
            if (!candName.trim()) {
                throw new Error('Candidate name is required.');
            }

            // Capture live HTML snapshot of the document
            const docEl = document.getElementById('offerLetterDoc');
            const htmlSnapshot = docEl ? docEl.innerHTML : '';

            const payload = {
                candidate_name: candName,
                title: v('of_title'),
                role: v('of_role'),
                department: v('of_department'),
                work_location: v('of_work_location'),
                date_of_joining: v('of_date_of_joining'),
                employment_type: v('of_employment_type'),
                doc_ref: v('of_doc_ref'),
                basic_pay: parseFloat(v('of_basic_pay') || 12000),
                total_potential: parseFloat(v('of_total_potential') || 17000),
                signatory_name: v('of_signatory_name'),
                signatory_title: v('of_signatory_title'),
                data_json: JSON.stringify({
                    letter_date: v('of_date'),
                }),
                html_snapshot: htmlSnapshot,
            };

            // If editing an existing letter, include its ID
            if (this.currentOfferLetterId) {
                payload.id = this.currentOfferLetterId;
            }

            // Include candidate linkage if selected
            const candSelect = document.getElementById('offerCandidateSelect');
            if (candSelect && candSelect.value) {
                payload.cand_id = candSelect.value;
            }

            const res = await fetch('/api/v1/zepto/offer-letters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to save letter');

            this.currentOfferLetterId = data.letter.id;

            // Show delete button
            const delBtn = document.getElementById('deleteOfferLetterBtn');
            if (delBtn) delBtn.style.display = 'inline-flex';

            await this.loadOfferLetters();
            this.showToast(`💾 Offer letter for ${candName} saved successfully!`);
        } catch (err) {
            this.showToast('⚠️ ' + err.message, true);
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<span>💾</span> Save Letter'; }
        }
    },

    async deleteCurrentOfferLetter() {
        if (!this.currentOfferLetterId) return;
        if (!confirm('Delete this saved offer letter?')) return;

        try {
            const res = await fetch(`/api/v1/zepto/offer-letters/${this.currentOfferLetterId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed to delete offer letter');

            this.currentOfferLetterId = null;
            const delBtn = document.getElementById('deleteOfferLetterBtn');
            if (delBtn) delBtn.style.display = 'none';

            await this.loadOfferLetters();
            this.resetOfferLetterToDefault();
            this.showToast('🗑️ Offer letter deleted.');
        } catch (err) {
            this.showToast('⚠️ ' + err.message, true);
        }
    },

    resetOfferLetterToDefault() {
        this.currentOfferLetterId = null;
        this._offerModuleInitialized = false;

        // Reset form fields to defaults
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        setVal('of_title', 'Mr.');
        setVal('of_candidate_name', 'Akash Kumar');
        setVal('of_role', 'Pickpackers');
        setVal('of_department', 'Operations');
        setVal('of_employment_type', 'Full - Time');
        setVal('of_work_location', 'Sector F Sainik Colony Jammu');
        setVal('of_basic_pay', '12000');
        setVal('of_total_potential', '17000');
        setVal('of_signatory_name', 'Jatin');
        setVal('of_signatory_title', 'Authorized Signatory');

        const now = new Date();
        const dd = String(now.getDate()).padStart(2, '0');
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const yr = now.getFullYear();
        setVal('of_date', `${dd}/${mm}/${yr}`);
        setVal('of_date_of_joining', `${dd}/${mm}/${yr}`);
        setVal('of_doc_ref', `RPS-ZEP-${yr}/${mm}-01`);

        // Reset selectors
        const savedSel = document.getElementById('savedOfferLetterSelect');
        if (savedSel) savedSel.value = '';
        const candSel = document.getElementById('offerCandidateSelect');
        if (candSel) candSel.value = '';

        // Hide delete button
        const delBtn = document.getElementById('deleteOfferLetterBtn');
        if (delBtn) delBtn.style.display = 'none';

        // Reload default template into the document preview — replace innerHTML
        // with the original template structure
        this._resetOfferDocToTemplate();
        this.syncFormToPreview();
        this.initOfferLetterModule();
    },

    _resetOfferDocToTemplate() {
        const docEl = document.getElementById('offerLetterDoc');
        if (!docEl) return;

        // Restore the static HTML template for the A4 preview
        docEl.innerHTML = `
            <!-- Header -->
            <div class="flex items-start justify-between border-b-2 border-slate-900 pb-2 mb-2.5">
                <div>
                    <div id="pv_comp_name" contenteditable="true" spellcheck="false" class="text-[17pt] font-extrabold tracking-tight text-slate-950 uppercase leading-none font-sans">RAKESHPARMESHWAR & SONS CO.</div>
                    <div id="pv_comp_sub" contenteditable="true" spellcheck="false" class="text-[8.5pt] font-bold text-slate-700 tracking-wider uppercase mt-1">PARTNERED WITH ZEPTO (FRANCHISE STORE)</div>
                </div>
                <div class="text-right">
                    <div id="pv_doc_heading" contenteditable="true" spellcheck="false" class="text-[15pt] font-black text-slate-950 tracking-wide uppercase leading-none">OFFER LETTER</div>
                    <div id="pv_confidential_badge" contenteditable="true" spellcheck="false" class="text-[8.5pt] font-bold text-red-600 italic tracking-tight mt-1">Strictly Confidential</div>
                </div>
            </div>
            <!-- Metadata Bar -->
            <div class="bg-slate-50 border border-slate-300 rounded px-3 py-1.5 mb-2.5 flex items-center justify-between text-[9.5pt]">
                <div><span class="font-bold text-slate-700">Date:</span><span id="pv_meta_date" contenteditable="true" spellcheck="false" class="font-semibold text-slate-950 ml-1">01/10/2026</span></div>
                <div><span class="font-bold text-slate-700">To:</span><span id="pv_meta_title" contenteditable="true" spellcheck="false" class="font-semibold text-slate-950 ml-1">Mr.</span> <span id="pv_meta_name" contenteditable="true" spellcheck="false" class="font-bold text-slate-950">Akash Kumar</span></div>
                <div><span class="font-bold text-slate-700">Location:</span><span id="pv_meta_location" contenteditable="true" spellcheck="false" class="font-semibold text-slate-950 ml-1">Jammu, J&K</span></div>
            </div>
            <!-- Subject & Salutation -->
            <div class="mb-2">
                <div class="text-[10pt] font-bold text-slate-950 mb-1"><span>Subject: Offer of Employment – </span><span id="pv_subj_role" contenteditable="true" spellcheck="false" class="text-slate-950 underline decoration-slate-400 decoration-1 underline-offset-2">Pickpackers / Store Associates</span></div>
                <div class="text-[9.5pt] font-semibold text-slate-900 mb-1"><span>Dear </span><span id="pv_salut_name" contenteditable="true" spellcheck="false" class="font-bold">Akash Kumar</span><span>,</span></div>
                <p id="pv_intro_p" contenteditable="true" spellcheck="false" class="text-[9pt] text-slate-800 leading-snug text-justify">We are pleased to offer you employment with <strong>Rakeshparmeshwar & Sons Co.</strong>, partnered with Zepto as a franchise, for the position of <strong>Pickpackers/Store Associates</strong>. We believe your skills and enthusiasm will be a valuable addition to our operational team.</p>
            </div>
            <!-- Position Matrix -->
            <div class="grid grid-cols-3 gap-1.5 mb-2.5">
                <div class="border border-slate-300 rounded p-1.5 bg-slate-50/70"><div class="text-[7.5pt] font-bold text-slate-500 uppercase tracking-wider">POSITION</div><div id="pv_grid_position" contenteditable="true" spellcheck="false" class="text-[9pt] font-bold text-slate-950 mt-0.5">Pickpackers</div></div>
                <div class="border border-slate-300 rounded p-1.5 bg-slate-50/70"><div class="text-[7.5pt] font-bold text-slate-500 uppercase tracking-wider">DEPARTMENT</div><div id="pv_grid_department" contenteditable="true" spellcheck="false" class="text-[9pt] font-bold text-slate-950 mt-0.5">Operations</div></div>
                <div class="border border-slate-300 rounded p-1.5 bg-slate-50/70"><div class="text-[7.5pt] font-bold text-slate-500 uppercase tracking-wider">EMPLOYMENT TYPE</div><div id="pv_grid_emp_type" contenteditable="true" spellcheck="false" class="text-[9pt] font-bold text-slate-950 mt-0.5">Full - Time</div></div>
                <div class="col-span-2 border border-slate-300 rounded p-1.5 bg-slate-50/70"><div class="text-[7.5pt] font-bold text-slate-500 uppercase tracking-wider">WORK LOCATION</div><div id="pv_grid_location" contenteditable="true" spellcheck="false" class="text-[9pt] font-bold text-slate-950 mt-0.5">Sector F Sainik Colony Jammu</div></div>
                <div class="border border-slate-300 rounded p-1.5 bg-slate-50/70"><div class="text-[7.5pt] font-bold text-slate-500 uppercase tracking-wider">DATE OF JOINING</div><div id="pv_grid_joining_date" contenteditable="true" spellcheck="false" class="text-[9pt] font-bold text-slate-950 mt-0.5 font-mono">01/10/2026</div></div>
            </div>
            <!-- Compensation Table -->
            <div class="mb-2">
                <div class="text-[8.5pt] font-extrabold text-slate-950 uppercase tracking-wider mb-1"><span id="pv_comp_title" contenteditable="true" spellcheck="false">COMPENSATION DETAILS (JAMMU – SAINIK COLONY ZEPTO STORE)</span></div>
                <div class="border border-slate-900 rounded overflow-hidden">
                    <table class="w-full text-left border-collapse text-[8pt]" style="line-height: 1.25;">
                        <thead><tr class="bg-slate-900 text-white font-bold text-[7.5pt] uppercase tracking-wider"><th class="p-1 pl-2 border-r border-slate-700 w-[24%]">KPI</th><th class="p-1 border-r border-slate-700 w-[25%] text-center">SLAB 1 (KPI / AMOUNT)</th><th class="p-1 border-r border-slate-700 w-[25%] text-center">SLAB 2 (KPI / AMOUNT)</th><th class="p-1 pr-2 w-[26%] text-center">SLAB 3 (KPI / AMOUNT)</th></tr></thead>
                        <tbody class="divide-y divide-slate-300">
                            <tr class="hover:bg-slate-50"><td class="p-1 pl-2 font-bold text-slate-900 border-r border-slate-300" contenteditable="true">BASIC PAY</td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">Attendance Basis <strong class="ml-1 text-slate-950">₹12,000</strong></td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">Attendance Basis <strong class="ml-1 text-slate-950">₹12,000</strong></td><td class="p-1 pr-2 text-center" contenteditable="true">Attendance Basis <strong class="ml-1 text-slate-950">₹12,000</strong></td></tr>
                            <tr class="hover:bg-slate-50"><td class="p-1 pl-2 font-bold text-slate-900 border-r border-slate-300" contenteditable="true">ATTENDANCE BONUS</td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">26 or 27 Attendance <strong class="ml-1 text-slate-950">₹1,000</strong></td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">1 Leave with Info <strong class="ml-1 text-slate-950">₹700</strong></td><td class="p-1 pr-2 text-center" contenteditable="true">2 Leave with Info <strong class="ml-1 text-slate-950">₹500</strong></td></tr>
                            <tr class="hover:bg-slate-50"><td class="p-1 pl-2 font-bold text-slate-900 border-r border-slate-300" contenteditable="true">BEHAVIOUR</td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">DHM Feedback <strong class="ml-1 text-slate-950">₹1,000</strong></td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">DHM Feedback <strong class="ml-1 text-slate-950">₹700</strong></td><td class="p-1 pr-2 text-center" contenteditable="true">DHM Feedback <strong class="ml-1 text-slate-950">₹500</strong></td></tr>
                            <tr class="hover:bg-slate-50"><td class="p-1 pl-2 font-bold text-slate-900 border-r border-slate-300" contenteditable="true">IPP</td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">160+ <strong class="ml-1 text-slate-950">₹1,000</strong></td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">140+ <strong class="ml-1 text-slate-950">₹700</strong></td><td class="p-1 pr-2 text-center" contenteditable="true">120+ <strong class="ml-1 text-slate-950">₹500</strong></td></tr>
                            <tr class="hover:bg-slate-50"><td class="p-1 pl-2 font-bold text-slate-900 border-r border-slate-300" contenteditable="true">SLA</td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">SLA 3 <strong class="ml-1 text-slate-950">₹2,000</strong></td><td class="p-1 border-r border-slate-300 text-center" contenteditable="true">SLA 2 <strong class="ml-1 text-slate-950">₹1,500</strong></td><td class="p-1 pr-2 text-center" contenteditable="true">SLA 1 <strong class="ml-1 text-slate-950">₹700</strong></td></tr>
                            <tr class="bg-slate-100 font-extrabold text-[8.5pt]"><td class="p-1 pl-2 text-slate-950 border-r border-slate-400 uppercase" contenteditable="true">TOTAL POTENTIAL</td><td class="p-1 border-r border-slate-400 text-center text-slate-950" contenteditable="true" id="pv_slab1_total">₹17,000</td><td class="p-1 border-r border-slate-400 text-center text-slate-950" contenteditable="true" id="pv_slab2_total">₹15,600</td><td class="p-1 pr-2 text-center text-slate-950" contenteditable="true" id="pv_slab3_total">₹14,200</td></tr>
                        </tbody>
                    </table>
                </div>
                <!-- Achievers Bonus -->
                <div class="mt-1 border border-slate-300 rounded bg-slate-50/80 px-2 py-1 flex items-center justify-between text-[7.5pt]">
                    <div class="font-bold text-slate-900 flex items-center gap-1"><span class="text-amber-600">★</span><span contenteditable="true">Achievers Bonus (Additional Monthly Top Performer Incentive):</span></div>
                    <div class="flex items-center gap-3 font-semibold text-slate-800">
                        <span contenteditable="true">1st Best Performer: <strong class="text-slate-950">₹1,500</strong></span><span class="text-slate-300">|</span>
                        <span contenteditable="true">2nd Best Performer: <strong class="text-slate-950">₹1,000</strong></span><span class="text-slate-300">|</span>
                        <span contenteditable="true">3rd Best Performer: <strong class="text-slate-950">₹700</strong></span>
                    </div>
                </div>
            </div>
            <!-- Key Responsibilities -->
            <div class="mb-2">
                <div class="text-[8pt] font-extrabold text-slate-950 uppercase tracking-wider mb-0.5">KEY RESPONSIBILITIES</div>
                <ul id="pv_responsibilities_list" contenteditable="true" spellcheck="false" class="list-disc pl-4 text-[7.5pt] text-slate-800 space-y-0.5 leading-tight">
                    <li>Picking items accurately as per order from the store inventory.</li>
                    <li>Packing orders securely and ensuring high packing accuracy.</li>
                    <li>Ensuring timely order processing and quick store dispatch.</li>
                    <li>Maintaining strict cleanliness and organization in work area.</li>
                    <li>Following all safety, hygiene, and daily operational guidelines.</li>
                    <li>Assisting in regular inventory management and cycle stock checks.</li>
                    <li>Performing any other operational duties assigned by the supervisor or management.</li>
                </ul>
            </div>
            <!-- Probation & Terms -->
            <div class="mb-2">
                <div class="text-[8pt] font-extrabold text-slate-950 uppercase tracking-wider mb-0.5">PROBATION & GENERAL TERMS</div>
                <div id="pv_terms_content" contenteditable="true" spellcheck="false" class="text-[7pt] text-slate-700 space-y-1 text-justify leading-tight">
                    <p><strong class="text-slate-900">Probation Period:</strong> You will be on probation for a period of <strong>3 months</strong> from the date of joining. Your performance, conduct, attendance, and suitability for the role will be evaluated during this period. Confirmation of employment will be communicated upon successful completion of probation.</p>
                    <p><strong class="text-slate-900">General Terms & Notice:</strong> You are required to abide by company policies and guidelines as amended from time to time. The company reserves the right to terminate employment in cases of misconduct or policy violations. If you decide to resign, you must provide <strong>one month prior notice</strong>, failing which one month's salary may be deducted as per management decision.</p>
                </div>
            </div>
            <!-- Signatures -->
            <div class="pt-2 border-t border-slate-300 mt-2 flex items-end justify-between text-[8.5pt]">
                <div>
                    <div class="text-[8pt] font-bold text-slate-700">For Rakeshparmeshwar & Sons Co.</div>
                    <div id="pv_sign_script" contenteditable="true" spellcheck="false" class="text-[20pt] font-serif italic text-slate-900 my-0.5 tracking-wider select-none" style="font-family: 'Brush Script MT', 'Segoe Script', cursive, serif;">Jatin</div>
                    <div class="text-[8pt] font-extrabold text-slate-950"><span>Authorized Signatory (</span><span id="pv_sign_name">Jatin</span><span>)</span></div>
                </div>
                <div class="text-right">
                    <div class="text-[7.5pt] text-slate-500 mb-6">Accepted and Agreed by Employee:</div>
                    <div class="border-t border-slate-400 w-44 pt-0.5 text-center text-[7pt] text-slate-600">Signature & Date</div>
                </div>
            </div>
            <!-- Footer -->
            <div class="pt-2 border-t border-slate-200 mt-2 flex items-center justify-between text-[7pt] text-slate-500">
                <div id="pv_footer_tagline" contenteditable="true" spellcheck="false" class="font-medium">Delivering Excellence, Every Time. | Partnered with Zepto</div>
                <div class="font-mono"><span id="pv_footer_doc_ref" contenteditable="true" spellcheck="false">Document Ref: RPS-ZEP-2026/10-01</span><span class="ml-2 font-semibold">Page 1 of 1</span></div>
            </div>
        `;
    },

    printOrDownloadOfferLetter() {
        window.print();
    },

    _formatDateForOffer(isoStr) {
        if (!isoStr) {
            const now = new Date();
            return `${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()}`;
        }
        try {
            const d = new Date(isoStr);
            return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
        } catch {
            return isoStr;
        }
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => zeptoApp.init());
} else {
    zeptoApp.init();
}
