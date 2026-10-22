/**
 * Nexus Intelligence Platform — Shared UI Utilities
 * Canonical date formatting (IST), Indian Rupee currency formatters, percentage badges, and table sorters.
 */

window.app = window.app || {};
window.app.utils = window.app.utils || {};

(function() {
    'use strict';

    /**
     * Formats an ISO string or Date into Indian Standard Time (IST).
     * @param {string|Date|number} dateStr
     * @param {boolean} includeSeconds
     * @returns {string}
     */
    function formatIST(dateStr, includeSeconds = false) {
        if (!dateStr) return '—';
        try {
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return String(dateStr);
            const options = {
                timeZone: 'Asia/Kolkata',
                day: '2-digit',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: true
            };
            if (includeSeconds) options.second = '2-digit';
            return new Intl.DateTimeFormat('en-IN', options).format(d);
        } catch (e) {
            return String(dateStr);
        }
    }

    /**
     * Formats numeric amounts in Crores (Cr) with specified decimals.
     * @param {number|string} val
     * @param {number} decimals
     * @returns {string}
     */
    function formatCrores(val, decimals = 2) {
        if (val === null || val === undefined || isNaN(val)) return '—';
        const num = parseFloat(val);
        return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} Cr`;
    }

    /**
     * Formats raw rupees with Indian numbering grouping.
     * @param {number|string} val
     * @returns {string}
     */
    function formatCurrency(val) {
        if (val === null || val === undefined || isNaN(val)) return '—';
        const num = parseFloat(val);
        return `₹${num.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    }

    /**
     * Formats percentage with sign and optional color class.
     * @param {number|string} val
     * @param {boolean} withSign
     * @returns {string}
     */
    function formatPct(val, withSign = true) {
        if (val === null || val === undefined || isNaN(val)) return '—';
        const num = parseFloat(val);
        const sign = withSign && num > 0 ? '+' : '';
        return `${sign}${num.toFixed(2)}%`;
    }

    /**
     * Reusable Tab Switcher Activator
     * @param {string} containerSelector
     * @param {string} activeClass
     * @param {Function} onSwitch
     */
    function initTabSwitcher(containerSelector, activeClass, onSwitch) {
        const container = document.querySelector(containerSelector);
        if (!container) return;
        const buttons = container.querySelectorAll('button[data-tab]');
        buttons.forEach(btn => {
            btn.addEventListener('click', () => {
                buttons.forEach(b => b.classList.remove(activeClass));
                btn.classList.add(activeClass);
                if (typeof onSwitch === 'function') {
                    onSwitch(btn.getAttribute('data-tab'));
                }
            });
        });
    }

    // Attach to namespace
    window.app.utils.formatIST = formatIST;
    window.app.utils.formatCrores = formatCrores;
    window.app.utils.formatCurrency = formatCurrency;
    window.app.utils.formatPct = formatPct;
    window.app.utils.initTabSwitcher = initTabSwitcher;

    // Direct app-level shortcuts for backward compatibility
    window.app.formatIST = window.app.formatIST || formatIST;
    window.app.formatCrores = window.app.formatCrores || formatCrores;
})();
