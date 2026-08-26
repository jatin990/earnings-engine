/**
 * Watchlist management functionality
 */

class WatchlistManager {
    constructor() {
        this.watchlist = this.loadWatchlist();
        this.sidebar = document.getElementById('watchlistSidebar');
        this.watchlistItems = document.getElementById('watchlistItems');
        this.watchlistCount = document.getElementById('watchlistCount');
        this.watchlistCountDash = document.getElementById('watchlistCountDash');
        
        this.init();
    }
    
    init() {
        // Update UI on load
        this.updateWatchlistUI();
        
        // Toggle sidebar
        document.getElementById('watchlistToggle').addEventListener('click', () => {
            this.toggleSidebar();
        });
    }
    
    loadWatchlist() {
        try {
            const stored = localStorage.getItem('earningsEngineWatchlist');
            return stored ? JSON.parse(stored) : [];
        } catch (error) {
            console.error('Error loading watchlist:', error);
            return [];
        }
    }
    
    saveWatchlist() {
        try {
            localStorage.setItem('earningsEngineWatchlist', JSON.stringify(this.watchlist));
        } catch (error) {
            console.error('Error saving watchlist:', error);
        }
    }
    
    addTicker(ticker) {
        const tickerUpper = ticker.toUpperCase().trim();
        if (!this.watchlist.includes(tickerUpper)) {
            this.watchlist.push(tickerUpper);
            this.saveWatchlist();
            this.updateWatchlistUI();
            this.showNotification(`Added ${tickerUpper} to watchlist`, 'success');
            return true;
        } else {
            this.showNotification(`${tickerUpper} is already in watchlist`, 'info');
            return false;
        }
    }
    
    removeTicker(ticker) {
        const tickerUpper = ticker.toUpperCase().trim();
        const index = this.watchlist.indexOf(tickerUpper);
        if (index > -1) {
            this.watchlist.splice(index, 1);
            this.saveWatchlist();
            this.updateWatchlistUI();
            this.showNotification(`Removed ${tickerUpper} from watchlist`, 'info');
            return true;
        }
        return false;
    }
    
    isInWatchlist(ticker) {
        return this.watchlist.includes(ticker.toUpperCase().trim());
    }
    
    toggleTicker(ticker) {
        if (this.isInWatchlist(ticker)) {
            this.removeTicker(ticker);
        } else {
            this.addTicker(ticker);
        }
    }
    
    updateWatchlistUI() {
        // Update count badges
        const count = this.watchlist.length;
        this.watchlistCount.textContent = count;
        this.watchlistCountDash.textContent = count;
        
        if (count > 0) {
            this.watchlistCount.classList.remove('hidden');
        } else {
            this.watchlistCount.classList.add('hidden');
        }
        
        // Update sidebar items
        this.renderWatchlistItems();
    }
    
    renderWatchlistItems() {
        if (this.watchlist.length === 0) {
            this.watchlistItems.innerHTML = `
                <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                    <svg class="h-12 w-12 mx-auto mb-2 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>
                    </svg>
                    <p>No tickers in watchlist</p>
                    <p class="text-sm mt-1">Search for a ticker and add it here</p>
                </div>
            `;
            return;
        }
        
        this.watchlistItems.innerHTML = this.watchlist.map(ticker => `
            <div class="watchlist-item flex justify-between items-center p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer" onclick="app.loadTickerData('${ticker}')">
                <div class="flex items-center">
                    <svg class="h-5 w-5 text-yellow-500 mr-2" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>
                    </svg>
                    <span class="font-semibold text-gray-900 dark:text-white">${ticker}</span>
                </div>
                <button type="button" onclick="event.stopPropagation(); watchlist.removeTicker('${ticker}')" class="text-red-500 hover:text-red-700 p-1">
                    <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
        `).join('');
    }
    
    toggleSidebar() {
        this.sidebar.classList.toggle('translate-x-full');
        if (!this.sidebar.classList.contains('translate-x-full')) {
            this.sidebar.classList.add('sidebar-enter');
        }
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 fade-in ${
            type === 'success' ? 'bg-green-500 text-white' :
            type === 'error' ? 'bg-red-500 text-white' :
            'bg-blue-500 text-white'
        }`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.5s ease';
            setTimeout(() => notification.remove(), 500);
        }, 3000);
    }
    
    exportWatchlist() {
        const dataStr = JSON.stringify(this.watchlist, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'watchlist.json';
        link.click();
        URL.revokeObjectURL(url);
    }
    
    importWatchlist(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const imported = JSON.parse(e.target.result);
                if (Array.isArray(imported)) {
                    this.watchlist = [...new Set([...this.watchlist, ...imported])];
                    this.saveWatchlist();
                    this.updateWatchlistUI();
                    this.showNotification(`Imported ${imported.length} tickers`, 'success');
                }
            } catch (error) {
                this.showNotification('Invalid watchlist file', 'error');
            }
        };
        reader.readAsText(file);
    }
}

// Initialize watchlist manager
let watchlist;
document.addEventListener('DOMContentLoaded', () => {
    watchlist = new WatchlistManager();
});