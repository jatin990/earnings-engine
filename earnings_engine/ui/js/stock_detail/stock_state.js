/**
 * Nexus Intelligence Platform — Stock Detail State & Shared Helpers
 * Provides centralized state, IST date localization, financial formatters, and toast telemetry.
 */

(function () {
    'use strict';

    window.StockDetailState = {
        ticker: (window.__STOCK_TICKER__ || '').trim().toUpperCase(),
        cleanTicker: (window.__STOCK_TICKER__ || '').trim().toUpperCase().replace('.NS', '').replace('.BO', ''),
        quote: null,
        technicals: null,
        earnings: null,
        consensus: null,
        kronos: null,
        institutional: null,
        catalysts: null,
        rating: null,
        chartRecords: [],
        chartInstance: null,
        candleSeries: null,
        volumeSeries: null,
        sma20Series: null,
        sma50Series: null,
        sma200Series: null,
        vwapSeries: null,
        vwapUpperSeries: null,
        vwapLowerSeries: null,
        liquidityLines: [],
        activeRange: '1Y',
        selectedModel: 'qwen2.5:72b-instruct',
        selectedTimeframe: 14,
        isPollingQuote: false,
    };

    const State = window.StockDetailState;

    /**
     * Display a floating toast notification.
     */
    window.showStockToast = function (msg, type = 'info', duration = 3500) {
        let container = document.getElementById('stockToastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'stockToastContainer';
            container.className = 'stock-toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `stock-toast ${type}`;

        const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
        toast.innerHTML = `<span style="font-weight: bold; color: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#38bdf8'};">${icon}</span> <span>${msg}</span>`;

        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            toast.style.transition = 'all 0.25s ease';
            setTimeout(() => toast.remove(), 250);
        }, duration);
    };

    /**
     * Format timestamp or date string to Indian Standard Time (IST)
     */
    window.formatIST = function (val, opts = {}) {
        if (!val) return '—';
        try {
            let d;
            if (typeof val === 'number') {
                // Check if seconds or milliseconds
                d = new Date(val > 1e11 ? val : val * 1000);
            } else if (typeof val === 'object' && val.year) {
                d = new Date(Date.UTC(val.year, (val.month || 1) - 1, val.day || 1));
            } else {
                d = new Date(val);
            }
            if (isNaN(d.getTime())) return String(val);

            const istOptions = {
                timeZone: 'Asia/Kolkata',
                day: '2-digit',
                month: 'short',
            };

            if (opts.includeYear !== false) {
                istOptions.year = 'numeric';
            }

            if (opts.includeTime) {
                istOptions.hour = '2-digit';
                istOptions.minute = '2-digit';
                istOptions.hour12 = false;
            }

            const formatted = new Intl.DateTimeFormat('en-IN', istOptions).format(d);
            return opts.suffix ? `${formatted} IST` : formatted;
        } catch (e) {
            return String(val);
        }
    };

    /**
     * Adaptive Financial Number Formatters
     */
    window.formatPrice = function (val, isINR = true) {
        if (val === null || val === undefined || isNaN(val)) return '—';
        const num = Number(val);
        const prefix = isINR ? '₹' : '$';
        return `${prefix}${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    window.formatPercent = function (val, includePlus = true) {
        if (val === null || val === undefined || isNaN(val)) return '—';
        const num = Number(val);
        const sign = includePlus && num > 0 ? '+' : '';
        return `${sign}${num.toFixed(2)}%`;
    };

    window.formatVolume = function (vol) {
        if (vol === null || vol === undefined || isNaN(vol)) return '—';
        const num = Number(vol);
        if (num >= 10000000) return `${(num / 10000000).toFixed(2)} Cr`;
        if (num >= 100000) return `${(num / 100000).toFixed(2)} L`;
        if (num >= 1000) return `${(num / 1000).toFixed(1)} K`;
        return num.toLocaleString('en-IN');
    };

    window.formatCrores = function (val) {
        if (val === null || val === undefined || isNaN(val)) return '—';
        const num = Number(val);
        if (num >= 100000) return `₹${(num / 100000).toFixed(2)} L Cr`;
        return `₹${num.toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr`;
    };

    /**
     * Safe DOM Text Setter
     */
    window.setElText = function (id, text, fallback = '—') {
        const el = typeof id === 'string' ? document.getElementById(id) : id;
        if (el) {
            el.textContent = (text !== null && text !== undefined && text !== '') ? text : fallback;
        }
    };

    window.setElHtml = function (id, htmlStr) {
        const el = typeof id === 'string' ? document.getElementById(id) : id;
        if (el) {
            el.innerHTML = htmlStr || '';
        }
    };
})();
