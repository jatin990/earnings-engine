/**
 * Nexus Intelligence Platform — Stock Detail Master Entrypoint
 * Aggregates all Stock Detail modules into a clean namespace and handles fallback initialization.
 */

(function () {
    'use strict';

    window.StockDetail = {
        get state() {
            return window.StockDetailState;
        },
        initChart: window.initStockChart,
        loadChartData: window.loadStockChartData,
        setRange: window.setChartRange,
        toggleIndicator: window.toggleIndicator,
        loadLiquidity: window.loadStockLiquidityWalls,
        runConsensus: window.runStockConsensus,
        openTraceModal: window.openTraceModal,
        closeTraceModal: window.closeTraceModal,
        openEpsCalculator: window.openEpsCalculatorModal,
        closeEpsCalculator: window.closeEpsCalculatorModal,
        runEpsScenario: window.runEpsScenarioCalculation,
        hardRefreshPrices: window.hardRefreshStockPrices,
        openWatchlist: window.openWatchlistModal,
        closeWatchlist: window.closeWatchlistModal,
        toast: window.showStockToast,
    };
})();
