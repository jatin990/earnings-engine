/**
 * Autocomplete functionality for ticker search
 */

class Autocomplete {
    constructor() {
        this.searchInput = document.getElementById('tickerSearch');
        this.dropdown = document.getElementById('autocompleteDropdown');
        this.allTickers = [];
        this.selectedIndex = -1;
        
        this.init();
    }
    
    init() {
        // Load all tickers on initialization
        this.loadTickers();
        
        // Event listeners
        this.searchInput.addEventListener('input', (e) => this.handleInput(e));
        this.searchInput.addEventListener('keydown', (e) => this.handleKeydown(e));
        this.searchInput.addEventListener('focus', () => this.handleFocus());
        
        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!this.searchInput.contains(e.target) && !this.dropdown.contains(e.target)) {
                this.hideDropdown();
            }
        });
    }
    
    async loadTickers() {
        try {
            // Load from multiple universe files
            const [nseAll, usTop, nseTop] = await Promise.all([
                this.fetchTickers('NSE_ALL'),
                this.fetchTickers('US'),
                this.fetchTickers('IN')
            ]);
            
            // Combine and deduplicate
            this.allTickers = [...new Set([...nseAll, ...usTop, ...nseTop])];
            console.log(`Loaded ${this.allTickers.length} tickers for autocomplete`);
        } catch (error) {
            console.error('Error loading tickers:', error);
            // Fallback to basic list
            this.allTickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS'];
        }
    }
    
    async fetchTickers(market) {
        market = (market || '').toUpperCase().trim();
        if (window.app && typeof window.app.getUniverse === 'function') {
            const u = await window.app.getUniverse(market);
            return (u && u.tickers) || [];
        }
        try {
            const cacheKey = 'ee_uni_' + market;
            const stored = sessionStorage.getItem(cacheKey);
            if (stored) {
                const parsed = JSON.parse(stored);
                if (parsed && Array.isArray(parsed.tickers) && parsed.ts && (Date.now() - parsed.ts < 3600000)) {
                    return parsed.tickers;
                }
            }
            const response = await fetch(`/api/v1/universe/${market}`);
            const data = await response.json();
            const tickers = data.tickers || [];
            try {
                sessionStorage.setItem(cacheKey, JSON.stringify({ market, count: tickers.length, tickers, ts: Date.now() }));
            } catch (e) {}
            return tickers;
        } catch (error) {
            console.error(`Error fetching ${market} tickers:`, error);
            return [];
        }
    }
    
    handleInput(e) {
        const query = e.target.value.trim().toUpperCase();
        
        if (query.length < 1) {
            this.hideDropdown();
            return;
        }
        
        // Filter tickers based on query
        const matches = this.allTickers.filter(ticker => 
            ticker.toUpperCase().includes(query)
        ).slice(0, 20); // Limit to 20 results
        
        if (matches.length > 0) {
            this.showDropdown(matches);
        } else {
            this.hideDropdown();
        }
    }
    
    handleKeydown(e) {
        const items = this.dropdown.querySelectorAll('.autocomplete-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.selectedIndex = Math.min(this.selectedIndex + 1, items.length - 1);
            this.updateSelection(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
            this.updateSelection(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (this.selectedIndex >= 0 && items[this.selectedIndex]) {
                items[this.selectedIndex].click();
            } else if (items.length > 0) {
                items[0].click();
            }
        } else if (e.key === 'Escape') {
            this.hideDropdown();
        }
    }
    
    handleFocus() {
        const query = this.searchInput.value.trim();
        if (query.length > 0) {
            this.handleInput({ target: { value: query } });
        }
    }
    
    updateSelection(items) {
        items.forEach((item, index) => {
            if (index === this.selectedIndex) {
                item.classList.add('bg-blue-50', 'dark:bg-blue-900');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('bg-blue-50', 'dark:bg-blue-900');
            }
        });
    }
    
    showDropdown(tickers) {
        this.dropdown.innerHTML = '';
        this.selectedIndex = -1;
        
        tickers.forEach(ticker => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            
            // Determine market type
            const market = ticker.endsWith('.NS') ? 'NSE' : 'US';
            const marketColor = market === 'NSE' ? 'text-green-600' : 'text-blue-600';
            
            item.innerHTML = `
                <div class="flex justify-between items-center">
                    <div>
                        <span class="ticker-symbol">${ticker}</span>
                        <span class="ml-2 text-xs ${marketColor}">${market}</span>
                    </div>
                </div>
            `;
            
            item.addEventListener('click', () => {
                this.selectTicker(ticker);
            });
            
            this.dropdown.appendChild(item);
        });
        
        this.dropdown.classList.remove('hidden');
    }
    
    hideDropdown() {
        this.dropdown.classList.add('hidden');
        this.dropdown.innerHTML = '';
        this.selectedIndex = -1;
    }
    
    selectTicker(ticker) {
        if (!ticker) return;
        const sym = ticker.trim().toUpperCase();
        if (this.searchInput) this.searchInput.value = '';
        this.hideDropdown();
        if (window.app && typeof window.app.openStockModal === 'function') {
            window.app.openStockModal(sym);
        } else if (typeof window.openStockModal === 'function') {
            window.openStockModal(sym);
        } else {
            window.open('/stock/' + encodeURIComponent(sym), '_blank');
        }
    }
}

// Initialize autocomplete when DOM is ready
let autocomplete;
document.addEventListener('DOMContentLoaded', () => {
    autocomplete = new Autocomplete();
});