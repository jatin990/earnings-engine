/**
 * Zepto Store Management Hub — Frontend Controller Module
 * Handles Staffing Matrix, MoM Salary & Bonus Tracking, Expenses & Insights,
 * Candidate Pipeline Conversions, and ₹75L 50-50 Partner Capital Ledger.
 */

const zeptoApp = {
    overview: null,
    employees: [],
    expenses: [],
    candidates: [],
    security: null,
    activeTab: 'employees',
    currentEmpId: null,

    async init() {
        // Tab routing via hash
        const hash = (window.location.hash || '#employees').replace('#', '');
        if (['employees', 'expenses', 'candidates', 'security'].includes(hash)) {
            this.activeTab = hash;
        }
        this.switchTab(this.activeTab, false);

        // Status change listener on employee modal
        const empStatusEl = document.getElementById('empFormStatus');
        if (empStatusEl) {
            empStatusEl.addEventListener('change', (e) => {
                const grp = document.getElementById('resignationReasonGroup');
                if (grp) grp.style.display = e.target.value === 'RESIGNED' ? 'block' : 'none';
            });
        }

        await this.loadAll();
    },

    async loadAll() {
        await Promise.all([
            this.loadOverview(),
            this.loadEmployees(),
            this.loadExpenses(),
            this.loadCandidates(),
            this.loadSecurity(),
        ]);
    },

    // -----------------------------------------------------------------------
    // Navigation & Tabs
    // -----------------------------------------------------------------------

    switchTab(tabId, updateHash = true) {
        this.activeTab = tabId;
        if (updateHash) {
            window.location.hash = tabId;
        }

        ['employees', 'expenses', 'candidates', 'security'].forEach(t => {
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
            this.renderOverviewWidgets(data);
        } catch (err) {
            console.error('[ZEPTO] Error loading overview:', err);
        }
    },

    renderOverviewWidgets(data) {
        const hc = data.headcount || {};
        const exp = data.expenses || {};
        const cands = data.candidates || {};
        const sec = data.security_capital || {};

        // 1. Staff Headcount & Attrition
        const activeEl = document.getElementById('kpiActiveStaff');
        if (activeEl) activeEl.textContent = `${hc.active || 0} Active`;

        const attritionBadge = document.getElementById('kpiAttritionBadge');
        if (attritionBadge) {
            const rate = hc.attrition_rate_pct || 0;
            attritionBadge.textContent = `${rate}% Attrition`;
            attritionBadge.className = `text-[10px] font-extrabold px-2 py-0.5 rounded-full border ${
                rate > 20 ? 'bg-rose-500/15 text-rose-300 border-rose-500/30' : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
            }`;
        }

        const breakdownEl = document.getElementById('kpiStaffBreakdown');
        if (breakdownEl && hc.role_breakdown) {
            const parts = Object.entries(hc.role_breakdown).map(([r, count]) => `${count} ${r.replace('_', ' ').toLowerCase()}`);
            breakdownEl.textContent = parts.join(' · ') || 'No active staff';
        }

        const payrollEl = document.getElementById('kpiPayroll');
        if (payrollEl) payrollEl.textContent = this.formatCurrency(hc.monthly_payroll || 0);

        // 2. Total Store Expenses & Spend per Employee
        const totalExpEl = document.getElementById('kpiTotalExpenses');
        if (totalExpEl) totalExpEl.textContent = this.formatCurrency(exp.total_expenses || 0);

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
        if (!config || !config.partners) return;
        const p1 = config.partners.partner_1;
        const p2 = config.partners.partner_2;
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

            const res = await fetch(`/api/v1/zepto/employees?${params.toString()}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load employees');

            this.employees = data.items || [];
            this.renderEmployees(this.employees);
        } catch (err) {
            console.error('[ZEPTO] Error loading employees:', err);
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

        tbody.innerHTML = items.map(emp => {
            const roleBadge = this.getRoleBadge(emp.role);
            const statusBadge = this.getStatusBadge(emp.status);
            const ratingStars = this.getRatingStars(emp.rating);
            const docsHtml = this.getDocsPill(emp.aadhar_doc_url, emp.resume_doc_url);

            return `
                <tr class="hover:bg-white/[0.02] transition">
                    <td class="p-3.5 pl-4">
                        <div class="font-bold text-white text-sm">${emp.name}</div>
                        <div class="text-[11px] text-slate-400 font-mono">${emp.phone || 'No phone'} ${emp.email ? '· ' + emp.email : ''}</div>
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
                    <td class="p-3.5 text-center">${docsHtml}</td>
                    <td class="p-3.5 pr-4 text-center">
                        <div class="flex items-center justify-center gap-1.5">
                            <button type="button" onclick="zeptoApp.openSalaryDrilldown('${emp.id}')" class="px-2.5 py-1 rounded bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 font-bold text-[11px] border border-purple-500/30 transition" title="MoM Salary History">
                                💵 Salary MoM
                            </button>
                            <button type="button" onclick="zeptoApp.openEditEmployeeModal('${emp.id}')" class="p-1 rounded bg-white/5 hover:bg-white/10 text-slate-300 text-xs" title="Edit Staff Details">
                                ✏️
                            </button>
                            <button type="button" onclick="zeptoApp.deleteEmployee('${emp.id}')" class="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs" title="Delete Staff">
                                🗑️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
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
            tbody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-slate-500">No monthly payout slips recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = salaries.map(sal => `
            <tr>
                <td class="p-2.5 font-bold text-white">${sal.year_month}</td>
                <td class="p-2.5 text-right">${this.formatCurrency(sal.base_amount)}</td>
                <td class="p-2.5 text-right text-purple-400">${sal.bonus_amount > 0 ? '+' + this.formatCurrency(sal.bonus_amount) : '₹0'}</td>
                <td class="p-2.5 text-right font-bold text-emerald-400">${this.formatCurrency(sal.net_paid)}</td>
                <td class="p-2.5 text-slate-400 text-[11px]">${sal.payment_date || '—'}</td>
                <td class="p-2.5 text-center">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                        ${sal.payment_status || 'PAID'}
                    </span>
                </td>
            </tr>
        `).join('');
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
        const search = document.getElementById('expSearchInput')?.value || '';

        try {
            const params = new URLSearchParams();
            if (category !== 'ALL') params.append('category', category);
            if (incurred !== 'ALL') params.append('incurred_by', incurred);
            if (search) params.append('search', search);

            const res = await fetch(`/api/v1/zepto/expenses?${params.toString()}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load expenses');

            this.expenses = data.items || [];
            this.renderExpenses(this.expenses, data.total_amount || 0);
        } catch (err) {
            console.error('[ZEPTO] Error loading expenses:', err);
        }
    },

    filterExpenses() {
        this.loadExpenses();
    },

    renderExpenses(items, totalAmount) {
        const tbody = document.getElementById('expensesTableBody');
        const badge = document.getElementById('expTotalAmountBadge');
        if (badge) badge.textContent = `Total: ${this.formatCurrency(totalAmount)}`;
        if (!tbody) return;

        // Update category summary cards
        const catSums = {};
        items.forEach(exp => {
            catSums[exp.category] = (catSums[exp.category] || 0) + exp.amount;
        });
        ['TRAINING', 'UNIFORMS_GEAR', 'EQUIPMENT', 'SNACKS_WELFARE', 'STORE_MAINTENANCE', 'OPERATIONAL'].forEach(cat => {
            const el = document.getElementById(`catSpend-${cat}`);
            if (el) el.textContent = this.formatCurrency(catSums[cat] || 0);
        });

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="p-8 text-center text-slate-500">
                        No expenses recorded yet. Click "Record Expense" to track out-of-pocket store costs.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = items.map(exp => {
            const catBadge = this.getCategoryBadge(exp.category);
            const proofLink = exp.document_url
                ? `<a href="${exp.document_url}" target="_blank" class="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold hover:underline">📄 View Bill</a>`
                : `<span class="text-slate-600">—</span>`;

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

    openAddExpenseModal() {
        document.getElementById('formExpense')?.reset();
        document.getElementById('expFormDate').value = new Date().toISOString().split('T')[0];
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

            const payload = {
                title: document.getElementById('expFormTitle').value,
                category: document.getElementById('expFormCategory').value,
                amount: parseFloat(document.getElementById('expFormAmount').value || 0),
                expense_date: document.getElementById('expFormDate').value,
                incurred_by: document.getElementById('expFormIncurred').value,
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
                        <button type="button" onclick="zeptoApp.deleteTranche('${t.id}')" class="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs" title="Delete Tranche">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    openAddTrancheModal() {
        document.getElementById('formTranche')?.reset();
        document.getElementById('trancheFormDate').value = new Date().toISOString().split('T')[0];
        this.openModal('modalTranche');
    },

    async saveTranche(e) {
        e.preventDefault();
        const btn = document.getElementById('btnSaveTranche');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Recording...';
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
                proof_doc_url: proofUrl,
                notes: document.getElementById('trancheFormNotes').value,
            };

            const res = await fetch('/api/v1/zepto/security', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to record tranche');

            this.closeModal('modalTranche');
            await this.loadOverview();
            await this.loadSecurity();
        } catch (err) {
            alert(err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Record Tranche';
            }
        }
    },

    async deleteTranche(trancheId) {
        if (!confirm('Are you sure you want to delete this capital payment tranche?')) return;
        try {
            const res = await fetch(`/api/v1/zepto/security/${trancheId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed to delete tranche');
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
            'SHIFT_INCHARGE': { label: '👔 Shift Incharge', class: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40' },
            'RIDER': { label: '🛵 Rider', class: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
            'PACKER': { label: '📦 Packer', class: 'bg-pink-500/20 text-pink-300 border-pink-500/40' },
            'STORE_MANAGER': { label: '🏛️ Manager', class: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
            'INVENTORY': { label: '📊 Inventory', class: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
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
    }
};

document.addEventListener('DOMContentLoaded', () => {
    zeptoApp.init();
});
