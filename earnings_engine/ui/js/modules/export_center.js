// =========================================================================
// 📑 Institutional Quantitative Research Pack Exporter Module
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    window.app = window.app || {};
    const app = window.app;

    app.exportCenter = {
        scope: 'radar', // 'radar' or 'ticker'
    };

    app.openExportPackModal = function(defaultTicker) {
        const modal = document.getElementById('exportPackModal');
        if (modal) modal.style.display = 'flex';

        if (defaultTicker) {
            app.exportCenter.scope = 'ticker';
            const radio = document.querySelector('input[name="exportScope"][value="ticker"]');
            if (radio) radio.checked = true;
            const tickerInput = document.getElementById('exportTickerInput');
            if (tickerInput) tickerInput.value = defaultTicker.toUpperCase().trim();
            app.onExportScopeChange('ticker');
        } else {
            app.onExportScopeChange(app.exportCenter.scope || 'radar');
        }
    };

    app.closeExportPackModal = function() {
        const modal = document.getElementById('exportPackModal');
        if (modal) modal.style.display = 'none';
    };

    app.onExportScopeChange = function(scope) {
        app.exportCenter.scope = scope;
        const radarBox = document.getElementById('exportRadarParams');
        const tickerBox = document.getElementById('exportTickerParams');

        if (radarBox) radarBox.style.display = scope === 'radar' ? 'flex' : 'none';
        if (tickerBox) tickerBox.style.display = scope === 'ticker' ? 'flex' : 'none';
    };

    app.triggerCsvExport = function() {
        if (app.exportCenter.scope === 'radar') {
            const radarType = document.getElementById('exportRadarType')?.value || 'breakout';
            const url = `${API_BASE}/api/v1/reports/export/radar?type=${encodeURIComponent(radarType)}`;
            window.location.href = url;
        } else {
            const ticker = document.getElementById('exportTickerInput')?.value.trim().toUpperCase();
            if (!ticker) {
                alert("Please enter a valid ticker symbol (e.g. TCS.NS)");
                return;
            }
            const url = `${API_BASE}/api/v1/reports/export/ticker/${encodeURIComponent(ticker)}`;
            window.open(url, '_blank');
        }
        app.closeExportPackModal();
    };

    app.triggerPrintPackExport = function() {
        let ticker = 'TCS.NS';
        if (app.exportCenter.scope === 'ticker') {
            ticker = document.getElementById('exportTickerInput')?.value.trim().toUpperCase() || 'TCS.NS';
        } else {
            const firstActive = document.querySelector('.stock-ticker-main');
            if (firstActive && firstActive.textContent) {
                ticker = firstActive.textContent.trim().toUpperCase();
            }
        }

        const url = `${API_BASE}/api/v1/reports/export/print-pack/${encodeURIComponent(ticker)}`;
        window.open(url, '_blank');
        app.closeExportPackModal();
    };

    // Hotkey listener for Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('exportPackModal');
            if (modal && modal.style.display === 'flex') {
                app.closeExportPackModal();
            }
        }
    });

})();
