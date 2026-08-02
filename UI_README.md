# Earnings Engine UI - User Guide

A modern, intuitive web interface for the Earnings Engine API with autocomplete, watchlist management, and universe file management.

## Quick Start

### 1. Start the Server

```bash
python run_api.py
```

The server will start at `http://localhost:8000`

### 2. Access the UI

Open your browser and navigate to:
- **Main UI**: http://localhost:8000/ui
- **API Docs**: http://localhost:8000/docs

## Features

### 🎨 Modern Interface
- **Dark/Light Mode**: Toggle between themes with the sun/moon icon
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Smooth Animations**: Polished user experience with transitions
- **Clean Layout**: Intuitive dashboard with clear information hierarchy

### 🔍 Smart Search with Autocomplete
- **Real-time Suggestions**: As you type, matching tickers appear instantly
- **Multi-Source Search**: Searches across NSE_ALL, US, and NSE Top universes
- **Keyboard Navigation**: Use arrow keys to navigate, Enter to select, Escape to close
- **Market Indicator**: Shows NSE (green) or US (blue) next to each ticker
- **Smart Filtering**: Shows up to 20 best matches

**Example Searches:**
- Type "AAPL" → Shows Apple Inc.
- Type "RELIANCE" → Shows RELIANCE.NS
- Type "TCS" → Shows TCS.NS

### ⭐ Watchlist Management
- **Personal Watchlist**: Save your favorite tickers (stored in browser)
- **Quick Access**: Click the star icon to view all watchlist items
- **One-Click Add/Remove**: Add tickers directly from search or detail view
- **Persistent Storage**: Watchlist saved in browser localStorage
- **Visual Feedback**: Badge shows watchlist count, notifications confirm actions

**How to Use:**
1. Search for a ticker (e.g., "AAPL")
2. Click "Add to Watchlist" button
3. Click the star icon in header to view watchlist
4. Click any watchlist item to view details
5. Click X to remove from watchlist

### 📊 Comprehensive Market Data

**Dashboard Stats:**
- Total tickers in database
- Cached market caps count
- Upcoming earnings events
- Your watchlist size

**Ticker Detail View:**
- **Current Price & Market Cap**: Real-time data
- **52-Week Range**: High/low with percentage from extremes
- **30-Day Returns**: Performance tracking
- **Earnings Quality Score**: 1-9 rating based on historical surprises
- **Interactive Price Chart**: Visualize price history with volume
- **Earnings History Table**: Last 10 earnings with EPS data

### 📈 Interactive Price Charts
- **Date Range Selection**: Choose custom start/end dates
- **Dual Axis**: Price (left) and Volume (right)
- **Interactive Tooltips**: Hover to see exact values
- **Smooth Rendering**: Optimized Chart.js implementation
- **Volume Bars**: Green bars show trading volume

### 🎯 Universe File Management
- **Add Tickers**: Add new symbols to any universe file
- **Remove Tickers**: Remove unwanted symbols
- **Multiple Files**: Manage NSE Top, US Top, NSE All, NSE Large Cap, My Watchlist
- **Live Updates**: Changes reflect immediately in UI
- **Persistent Changes**: Modifications saved to CSV files

**How to Use:**
1. Search for a ticker and view details
2. Click "Add to Universe" button
3. Select target file (e.g., "my_watchlist")
4. Enter ticker symbol and click "Add"
5. View current tickers in the list
6. Click "Remove" to delete tickers

### 🌓 Dark/Light Mode
- **Automatic Detection**: Respects system preference
- **Manual Toggle**: Click sun/moon icon to switch
- **Persistent Choice**: Remembers your preference
- **Smooth Transition**: Animated theme switching

## UI Components

### Navigation Bar
- **Logo**: Click to return to dashboard
- **Search Bar**: With autocomplete dropdown
- **Theme Toggle**: Switch between dark/light mode
- **Watchlist Button**: Opens watchlist sidebar with count badge

### Dashboard Cards
1. **Total Tickers**: Shows total stocks in database
2. **Cached Market Caps**: Number of tickers with market cap data
3. **Upcoming Earnings**: Count of earnings events in next 14 days
4. **Watchlist**: Your personal watchlist size

### Ticker Detail Section
**Header:**
- Ticker symbol and market (NSE/US)
- "Add to Watchlist" button
- "Add to Universe" button

**Market Context Cards:**
- Current Price & Market Cap
- 52-Week Range (Low - High)
- % from 52W High
- 30-Day Return (color-coded: green/red)
- Earnings Quality Score

**Price Chart:**
- Interactive line chart with volume bars
- Date range picker
- Update button to refresh chart

**Earnings History Table:**
- Date, EPS Estimate, EPS Reported, Surprise %
- Last 10 earnings events
- Color-coded surprise percentages

### Watchlist Sidebar
- Slides in from right
- Lists all watchlist tickers
- Click to view details
- X button to remove
- Empty state with helpful message

### Universe Manager Modal
- File selector dropdown
- Add ticker input
- Current tickers list with remove buttons
- Scrollable list (max height 96)

## Keyboard Shortcuts

- **Arrow Down**: Navigate down in autocomplete
- **Arrow Up**: Navigate up in autocomplete
- **Enter**: Select highlighted ticker
- **Escape**: Close autocomplete dropdown

## Browser Compatibility

- ✅ Chrome/Edge (v90+)
- ✅ Firefox (v88+)
- ✅ Safari (v14+)
- ✅ Opera (v76+)

## Tips & Tricks

1. **Quick Search**: Start typing immediately after clicking search bar
2. **Batch Operations**: Use universe manager to add multiple tickers
3. **Export Watchlist**: Use browser console to export: `JSON.stringify(watchlist.watchlist)`
4. **Import Watchlist**: Use browser console to import: `watchlist.importWatchlist(yourFile)`
5. **Keyboard Friendly**: Navigate entire UI without mouse
6. **Mobile Friendly**: Touch-optimized for phones and tablets

## Troubleshooting

### UI Not Loading
- Ensure server is running: `python run_api.py`
- Check console for errors (F12)
- Verify static files are mounted: `/static`

### Autocomplete Not Working
- Check browser console for errors
- Ensure API is running: `curl http://localhost:8000/api/v1/universe/NSE_ALL`
- Wait for tickers to load (check console for "Loaded X tickers")

### Watchlist Not Persisting
- Check browser localStorage is enabled
- Not in incognito/private mode
- Clear browser cache if corrupted

### Charts Not Rendering
- Check if price data exists for ticker
- Verify Chart.js is loaded (check Network tab)
- Try different date range

## Data Flow

```
User Action (Search/Click)
    ↓
JavaScript (app.js, autocomplete.js, watchlist.js)
    ↓
API Call (fetch)
    ↓
FastAPI Backend (server.py)
    ↓
Data Layer (prices.py, earnings.py, universe.py)
    ↓
SQLite Cache / yfinance
    ↓
JSON Response
    ↓
UI Update
```

## File Structure

```
earnings_engine/
├── api/
│   └── server.py          # FastAPI backend with UI serving
├── ui/
│   ├── index.html         # Main HTML structure
│   ├── css/
│   │   └── styles.css     # Custom styles and animations
│   └── js/
│       ├── app.js         # Main application logic
│       ├── autocomplete.js # Ticker search functionality
│       ├── watchlist.js   # Watchlist management
│       └── charts.js      # Chart.js configurations
└── data/
    └── universes/         # Ticker universe files
        ├── nse_top.txt
        ├── us_top.txt
        ├── nse_all.txt
        ├── nse_large_cap.txt
        └── my_watchlist.txt
```

## Next Steps

1. ✅ Access the UI at http://localhost:8000/ui
2. ✅ Try searching for a ticker (e.g., "AAPL")
3. ✅ Add tickers to your watchlist
4. ✅ Explore price charts and earnings data
5. ✅ Manage universe files
6. ✅ Toggle dark/light mode
7. ✅ Test on mobile device

## Support

For issues or questions:
- Check API docs: http://localhost:8000/docs
- Review console logs (F12)
- Verify server is running
- Check network connectivity

---

**Enjoy using the Earnings Engine UI!** 🚀