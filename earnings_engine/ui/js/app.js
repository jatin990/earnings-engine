/**
 * Main application logic
 */

class App {
    constructor() {
        this.currentTicker = null;
        this.apiBaseUrl = '';
        this.chartManager = null;
        this.watchlistManager = null;
        this.autocomplete = null;
        
        this.init();
    }
    
    init() {
        // Set API base URL
        this.apiBaseUrl = window.location.origin;
        
        // Initialize managers
        this.chartManager = window.chartManager;
        this.watchlistManager = window.watchlist;
        this.autocomplete = window.autocomplete;
        
        // Load dashboard stats
        this.loadDashboardStats();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Set default dates for chart
        this.setDefaultDates();
        
        // Load theme preference
        this.loadTheme();
    }
    
    setupEventListeners() {
        // Theme toggle
        document.getElementById('themeToggle').addEventListener('click', () => {
            this.toggleTheme();
        });
        
        // Search on Enter key
        document.getElementById('tickerSearch').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const ticker = e.target.value.trim();
                if (ticker) {
                    this.loadTickerData(ticker);
                }
            }
        });
    }
    
    setDefaultDates() {
        const endDate = new Date();
        const startDate = new Date();
        startDate.setFullYear(startDate.getFullYear() - 1);
        
        document.getElementById('endDate').value = endDate.toISOString().split('T')[0];
        document.getElementById('startDate').value = startDate.toISOString().split('T')[0];
    }
    
    // Dashboard
    async loadDashboardStats() {
        try {
            // Load total tickers
            const nseAll = await fetch('/api/v1/universe/NSE_ALL').then(r => r.json());
            document.getElementById('totalTickers').textContent = nseAll.count.toLocaleString();
            
            // Load cached market caps
            const marketCaps = await fetch('/api/v1/market-caps').then(r => r.json());
            document.getElementById('cachedCaps').textContent = Object.keys(marketCaps).length.toLocaleString();
            
            // Load upcoming earnings
            const upcoming = await fetch('/api/v1/upcoming-earnings?days=14&market=IN').then(r => r.json());
            document.getElementById('upcomingEarnings').textContent = upcoming.length;
            
        } catch (error) {
            console.error('Error loading dashboard stats:', error);
        }
    }
    
    // Ticker Data
    async loadTickerData(ticker) {
        this.currentTicker = ticker.toUpperCase();
        
        // Show loading
        document.getElementById('loadingSpinner').classList.remove('hidden');
        document.getElementById('tickerDetail').classList.remove('hidden');
        
        try {
            // Load market context
            const contextResponse = await fetch(`/api/v1/market-context/${this.currentTicker}`);
            const context = await contextResponse.json();
            
            if (!context || context.ticker === undefined) {
                this.showNotification('Ticker not found', 'error');
                return;
            }
            
            // Update UI with market context
            this.updateMarketContext(context);
            
            // Load price history
            await this.loadPriceHistory(this.currentTicker);
            
            // Load earnings history
            await this.loadEarningsHistory(this.currentTicker);
            
            // Update watchlist button
            this.updateWatchlistButton();
            
        } catch (error) {
            console.error('Error loading ticker data:', error);
            this.showNotification('Error loading ticker data', 'error');
        } finally {
            // Hide loading
            document.getElementById('loadingSpinner').classList.add('hidden');
        }
    }
    
    updateMarketContext(context) {
        // Basic info
        document.getElementById('detailTicker').textContent = context.ticker;
        document.getElementById('detailMarket').textContent = context.ticker.endsWith('.NS') ? 'NSE India' : 'US Market';
        
        // Price and market cap
        const price = context.current_price ? `$${context.current_price.toFixed(2)}` : 'N/A';
        document.getElementById('detailPrice').textContent = price;
        
        const marketCap = context.market_cap ? this.formatMarketCap(context.market_cap) : 'N/A';
        document.getElementById('detailMarketCap').textContent = marketCap;
        
        // 52-week range
        const low = context.week_low ? `$${context.week_low.toFixed(2)}` : 'N/A';
        const high = context.week_high ? `$${context.week_high.toFixed(2)}` : 'N/A';
        document.getElementById('detail52wLow').textContent = low;
        document.getElementById('detail52wHigh').textContent = high;
        
        // Percentage from high/low
        const pctFromHigh = context.pct_from_52w_high ? `${context.pct_from_52w_high.toFixed(2)}%` : 'N/A';
        document.getElementById('detailPctFromHigh').textContent = pctFromHigh;
        
        // 30-day return
        const return30d = context.thirty_day_return_pct ? `${context.thirty_day_return_pct.toFixed(2)}%` : 'N/A';
        const returnEl = document.getElementById('detail30DayReturn');
        returnEl.textContent = return30d;
        returnEl.className = `text-2xl font-bold ${context.thirty_day_return_pct >= 0 ? 'price-positive' : 'price-negative'}`;
        
        // Earnings score
        const score = context.prev_quarter_earnings_score || 'N/A';
        document.getElementById('detailEarningsScore').textContent = score;
    }
    
    async loadPriceHistory(ticker) {
        const startDate = document.getElementById('startDate').value;
        const endDate = document.getElementById('endDate').value;
        
        if (this.chartManager) {
            await this.chartManager.renderPriceChart(ticker, startDate, endDate);
        }
    }
    
    async loadEarningsHistory(ticker) {
        try {
            const response = await fetch(`/api/v1/earnings-history/${ticker}`);
            const earnings = await response.json();
            
            const tbody = document.getElementById('earningsTable');
            
            if (!earnings || earnings.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-gray-500">No earnings data available</td></tr>';
                return;
            }
            
            // Show last 10 earnings
            const recentEarnings = earnings.slice(-10).reverse();
            
            tbody.innerHTML = recentEarnings.map(earn => {
                const date = new Date(earn.earnings_date).toLocaleDateString();
                const surprise = earn.surprise_pct;
                const surpriseClass = surprise > 0 ? 'price-positive' : surprise < 0 ? 'price-negative' : '';
                const surpriseText = surprise ? `${surprise.toFixed(2)}%` : 'N/A';
                
                return `
                    <tr class="table-row-hover">
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">${date}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">${earn.eps_estimate || 'N/A'}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">${earn.eps_reported || 'N/A'}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm font-semibold ${surpriseClass}">${surpriseText}</td>
                    </tr>
                `;
            }).join('');
            
        } catch (error) {
            console.error('Error loading earnings history:', error);
        }
    }
    
    updatePriceChart() {
        if (this.currentTicker) {
            this.loadPriceHistory(this.currentTicker);
        }
    }
    
    // Watchlist
    addToWatchlist() {
        if (this.currentTicker && this.watchlistManager) {
            this.watchlistManager.addTicker(this.currentTicker);
            this.updateWatchlistButton();
        }
    }
    
    updateWatchlistButton() {
        const btn = event.target.closest('button');
        if (btn && this.watchlistManager) {
            const isInWatchlist = this.watchlistManager.isInWatchlist(this.currentTicker);
            if (isInWatchlist) {
                btn.innerHTML = `
                    <svg class="h-5 w-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>
                    </svg>
                    In Watchlist
                `;
                btn.classList.remove('bg-yellow-500', 'hover:bg-yellow-600');
                btn.classList.add('bg-gray-500', 'hover:bg-gray-600');
            }
        }
    }
    
    toggleWatchlist() {
        if (this.watchlistManager) {
            this.watchlistManager.toggleSidebar();
        }
    }
    
    // Universe Manager
    async showUniverseManager() {
        document.getElementById('universeModal').classList.remove('hidden');
        await this.loadUniverseTickers();
    }
    
    hideUniverseManager() {
        document.getElementById('universeModal').classList.add('hidden');
    }
    
    async loadUniverseTickers() {
        const file = document.getElementById('universeFileSelect').value;
        try {
            const response = await fetch(`/api/v1/universe/${file}`);
            const data = await response.json();
            this.renderUniverseTickers(data.tickers);
        } catch (error) {
            console.error('Error loading universe tickers:', error);
        }
    }
    
    renderUniverseTickers(tickers) {
        const container = document.getElementById('universeTickersList');
        
        if (!tickers || tickers.length === 0) {
            container.innerHTML = '<p class="text-gray-500 text-center py-4">No tickers in this universe</p>';
            return;
        }
        
        container.innerHTML = tickers.map(ticker => `
            <div class="flex justify-between items-center p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
                <span class="text-sm text-gray-900 dark:text-white">${ticker}</span>
                <button onclick="app.removeTickerFromUniverse('${ticker}')" class="text-red-500 hover:text-red-700 text-sm">
                    Remove
                </button>
            </div>
        `).join('');
    }
    
    async addTickerToUniverse() {
        const input = document.getElementById('newTickerInput');
        const ticker = input.value.trim().toUpperCase();
        const file = document.getElementById('universeFileSelect').value;
        
        if (!ticker) {
            this.showNotification('Please enter a ticker', 'error');
            return;
        }
        
        try {
            const response = await fetch('/api/v1/universe/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file: file,
                    tickers: [ticker]
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`Added ${ticker} to ${file}`, 'success');
                input.value = '';
                this.loadUniverseTickers();
            } else {
                this.showNotification('Failed to add ticker', 'error');
            }
        } catch (error) {
            console.error('Error adding ticker:', error);
            this.showNotification('Error adding ticker', 'error');
        }
    }
    
    async removeTickerFromUniverse(ticker) {
        const file = document.getElementById('universeFileSelect').value;
        
        if (!confirm(`Remove ${ticker} from ${file}?`)) {
            return;
        }
        
        try {
            const response = await fetch('/api/v1/universe/remove', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file: file,
                    tickers: [ticker]
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`Removed ${ticker} from ${file}`, 'success');
                this.loadUniverseTickers();
            } else {
                this.showNotification('Failed to remove ticker', 'error');
            }
        } catch (error) {
            console.error('Error removing ticker:', error);
            this.showNotification('Error removing ticker', 'error');
        }
    }
    
    // Theme
    toggleTheme() {
        document.documentElement.classList.toggle('dark');
        const isDark = document.documentElement.classList.contains('dark');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        this.updateThemeIcon(isDark);
    }
    
    loadTheme() {
        const theme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        
        if (theme === 'dark' || (!theme && prefersDark)) {
            document.documentElement.classList.add('dark');
            this.updateThemeIcon(true);
        } else {
            this.updateThemeIcon(false);
        }
    }
    
    updateThemeIcon(isDark) {
        const sunIcon = document.getElementById('sunIcon');
        const moonIcon = document.getElementById('moonIcon');
        
        if (isDark) {
            sunIcon.classList.remove('hidden');
            moonIcon.classList.add('hidden');
        } else {
            sunIcon.classList.add('hidden');
            moonIcon.classList.remove('hidden');
        }
    }
    
    // Utilities
    formatMarketCap(value) {
        if (!value) return 'N/A';
        
        if (value >= 1e12) {
            return `$${(value / 1e12).toFixed(2)}T`;
        } else if (value >= 1e9) {
            return `$${(value / 1e9).toFixed(2)}B`;
        } else if (value >= 1e6) {
            return `$${(value / 1e6).toFixed(2)}M`;
        } else {
            return `$${value.toFixed(2)}`;
        }
    }
    
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 fade-in ${
            type === 'success' ? 'bg-green-500 text-white' :
            type === 'error' ? 'bg-red-500 text-white' :
            'bg-blue-500 text-white'
        }`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.5s ease';
            setTimeout(() => notification.remove(), 500);
        }, 3000);
    }
    
    goHome() {
        document.getElementById('tickerDetail').classList.add('hidden');
        document.getElementById('tickerSearch').value = '';
        this.currentTicker = null;
    }
}

// Initialize app
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new App();
});