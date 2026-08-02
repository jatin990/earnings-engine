# Earnings Engine API Server

A FastAPI-based REST API that exposes earnings-engine data (price history, earnings history, market cap, market context, upcoming earnings, and universe data) for programmatic access and integration with tools like Postman.

## Features

- **CORS enabled** - Accessible from any frontend or API client
- **Interactive documentation** - Auto-generated Swagger UI and ReDoc
- **Cached data** - Leverages existing parquet cache for fast responses
- **Real-time refresh** - Optional force refresh from Yahoo Finance
- **Comprehensive endpoints** - All earnings-engine data exposed via REST

## Quick Start

### 1. Install Dependencies

```bash
# Ensure you're in the earnings-engine directory
cd earnings-engine

# Install the package with API dependencies
pip install -e ".[dev]"
```

### 2. Start the API Server

```bash
# Start the server on default port 8000
python -m earnings_engine.api.server

# Or specify a custom port
python -m earnings_engine.api.server --port 8080

# Or use uvicorn directly
uvicorn earnings_engine.api.server:app --host 0.0.0.0 --port 8000 --reload
```

The server will start at `http://localhost:8000`

### 3. Access the API

- **API Base URL:** `http://localhost:8000`
- **Interactive Docs (Swagger UI):** `http://localhost:8000/docs`
- **Alternative Docs (ReDoc):** `http://localhost:8000/redoc`
- **OpenAPI Schema:** `http://localhost:8000/openapi.json`

## API Endpoints

### Health Check

**GET** `/health`

Check if the API is running.

**Response:**
```json
{
  "status": "ok",
  "service": "earnings-engine-api"
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

---

### Price History

**GET** `/api/v1/price-history/{ticker}`

Get OHLCV price history for a ticker.

**Parameters:**
- `ticker` (path): Stock ticker symbol (e.g., `AAPL`, `TCS.NS`)
- `start_date` (query, optional): Start date in `YYYY-MM-DD` format
- `end_date` (query, optional): End date in `YYYY-MM-DD` format
- `force_refresh` (query, optional): Set to `true` to fetch fresh data from yfinance

**Example:**
```bash
# Get all cached price history
curl http://localhost:8000/api/v1/price-history/AAPL

# Get price history for a specific date range
curl "http://localhost:8000/api/v1/price-history/AAPL?start_date=2024-01-01&end_date=2024-06-30"

# Force refresh from yfinance
curl "http://localhost:8000/api/v1/price-history/AAPL?force_refresh=true"
```

**Response:**
```json
[
  {
    "date": "2024-01-02",
    "open": 185.06,
    "high": 186.33,
    "low": 181.83,
    "close": 183.56,
    "volume": 82488700
  }
]
```

---

### Earnings History

**GET** `/api/v1/earnings-history/{ticker}`

Get historical earnings data for a ticker.

**Parameters:**
- `ticker` (path): Stock ticker symbol
- `force_refresh` (query, optional): Set to `true` to fetch fresh data

**Example:**
```bash
curl http://localhost:8000/api/v1/earnings-history/MSFT
```

**Response:**
```json
[
  {
    "earnings_date": "2024-01-25",
    "eps_estimate": 2.10,
    "eps_reported": 2.18,
    "surprise_pct": 3.81
  }
]
```

---

### Market Cap

**GET** `/api/v1/market-cap/{ticker}`

Get current market capitalization for a ticker.

**Parameters:**
- `ticker` (path): Stock ticker symbol

**Example:**
```bash
curl http://localhost:8000/api/v1/market-cap/GOOGL
```

**Response:**
```json
{
  "ticker": "GOOGL",
  "market_cap": 2100000000000.0
}
```

---

### Market Context (Comprehensive Data)

**GET** `/api/v1/market-context/{ticker}`

Get comprehensive market context for a ticker including price, market cap, earnings scores, support/resistance levels, and more.

**Parameters:**
- `ticker` (path): Stock ticker symbol

**Example:**
```bash
curl http://localhost:8000/api/v1/market-context/AAPL
```

**Response:**
```json
{
  "ticker": "AAPL",
  "market_cap": 4537070911488.0,
  "current_price": 308.91,
  "week_change": -7.35,
  "pct_from_52w_high": 10.35,
  "pct_from_52w_low": 53.17,
  "thirty_day_return_pct": 3.66,
  "earnings_week_move_pct": -8.31,
  "earnings_week_high_pct": 0.94,
  "earnings_week_low_pct": -8.31,
  "week_high": 344.57,
  "week_low": 201.68,
  "prev_quarter_earnings_score": 6,
  "prev_3q_earnings_score": 6,
  "q1_earnings_score": 6,
  "q2_earnings_score": 7,
  "q3_earnings_score": 6,
  "next_resistance": 340.08,
  "current_support": 308.91,
  "eps_estimate": 1.89,
  "eps_reported": 2.02,
  "surprise_pct": 6.74
}
```

---

### Upcoming Earnings

**GET** `/api/v1/upcoming-earnings`

Get upcoming earnings events.

**Parameters:**
- `tickers` (query, optional): Comma-separated list of tickers (e.g., `AAPL,MSFT,GOOGL`)
- `days` (query, optional): Number of days to look ahead (default: 14, max: 90)
- `market` (query, optional): Market universe to use (e.g., `IN`, `US`, `NSE_LARGE_CAP`)

**Example:**
```bash
# Get upcoming earnings for specific tickers
curl "http://localhost:8000/api/v1/upcoming-earnings?tickers=AAPL,MSFT,GOOGL&days=14"

# Get upcoming earnings for NSE large cap universe
curl "http://localhost:8000/api/v1/upcoming-earnings?market=NSE_LARGE_CAP&days=30"
```

**Response:**
```json
[
  {
    "ticker": "AAPL",
    "earnings_date": "2024-10-31"
  }
]
```

---

### Universe

**GET** `/api/v1/universe/{market}`

Get the ticker universe for a specific market.

**Parameters:**
- `market` (path): Market identifier
  - `IN` - Indian stocks (top 44)
  - `US` - US stocks
  - `NSE_ALL` - All NSE stocks (~2000+)
  - `NSE_LARGE_CAP` - NSE large cap stocks (>1000cr market cap)

**Example:**
```bash
# Get Indian stock universe
curl http://localhost:8000/api/v1/universe/IN

# Get NSE large cap universe
curl http://localhost:8000/api/v1/universe/NSE_LARGE_CAP
```

**Response:**
```json
{
  "market": "IN",
  "tickers": [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    ...
  ],
  "count": 44
}
```

---

### All Market Caps

**GET** `/api/v1/market-caps`

Get all cached market caps.

**Example:**
```bash
curl http://localhost:8000/api/v1/market-caps
```

**Response:**
```json
{
  "AAPL": 4537070911488.0,
  "MSFT": 3100000000000.0,
  "GOOGL": 2100000000000.0
}
```

---

### Interactive Dashboard

**GET** `/dashboard`

Serves the fully interactive web dashboard with tab-based navigation. Because it's served from the same origin as the API server, all embedded JavaScript can call the REST endpoints directly without CORS issues.

**Tabs:**
- **📊 Results** - Upcoming earnings with market context, sortable table, dataset summary widgets
- **🔄 Swing** - Swing trading setups with support/resistance, momentum signals, quality scores
- **🤖 Kronos** - Run Kronos AI 14-day predictions on-demand
- **⭐ Watchlist** - Server-side watchlist management (persisted to `my_watchlist.txt`) + universe file browser

**Features:**
- 🔍 Ticker search with autocomplete (from NSE/US universe files)
- 📊 Widget cards for quick stats
- 🔄 Refresh Now button with last-refreshed timestamp per data source
- 📁 Universe file browser (NSE files with ticker counts and modified times)
- 📱 Fully mobile-responsive

**Usage:**
```bash
# Start the API server
python -m earnings_engine.api.server

# Open the dashboard in your browser
start http://localhost:8000/dashboard
```

**CLI Quick Start:**
```bash
# Starts the API server and opens the dashboard automatically
earnings-engine dashboard

# With custom port
earnings-engine dashboard --port 8080
```

---

### Dashboard Data Endpoints

These endpoints power the interactive dashboard tabs. All data is sourced from the SQLite database (`prices.sqlite3`) and NSE universe files.

#### Dashboard Overview

**GET** `/api/v1/dashboard/overview`

Returns dataset summary, refresh status, watchlist, and universe file metadata.

**Response:**
```json
{
  "dataset": {
    "available": true,
    "rows": 4182,
    "tickers": 95,
    "up_label_rate": 0.495,
    "date_range": {"min": "2015-01-01", "max": "2026-07-01"}
  },
  "refresh_status": {
    "prices": {"last_refresh": "2026-08-02 21:00:00", "rows": 95, "status": "ok"},
    "earnings": {"last_refresh": "2026-08-02 21:00:00", "rows": 95, "status": "ok"}
  },
  "watchlist": ["RELIANCE.NS", "TCS.NS"],
  "universe_files": [
    {"name": "nse_all", "tickers": 2000, "modified": "2026-08-01 10:00:00"}
  ]
}
```

#### Dashboard Results

**GET** `/api/v1/dashboard/results?days=14&market=IN`

Returns upcoming earnings results enriched with market context (price, market cap, momentum, quality scores, support/resistance).

**Parameters:**
- `days` (optional): Look-ahead window (default: 14, max: 90)
- `market` (optional): Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)

#### Dashboard Swing

**GET** `/api/v1/dashboard/swing?limit=50&market=IN`

Returns swing trading setups with support/resistance levels, momentum, and computed swing signals (Strong Buy / Buy / Cautious / Neutral).

**Parameters:**
- `limit` (optional): Max tickers to analyze (default: 50, max: 200)
- `market` (optional): Market universe

#### Dashboard Kronos

**POST** `/api/v1/dashboard/kronos/run`

Runs Kronos AI 14-day predictions on-demand.

**Request Body:**
```json
{
  "tickers": ["RELIANCE.NS", "TCS.NS"],
  "lookback": 120,
  "pred_len": 14
}
```

**Response:** List of prediction objects with current price, support, resistance, return %, trend, and AI explanation.

#### Dashboard Refresh

**POST** `/api/v1/dashboard/refresh`

Refreshes prices, earnings, and market caps on-demand.

**Request Body:**
```json
{
  "market": "IN",
  "force": true
}
```

#### Dashboard Refresh Status

**GET** `/api/v1/dashboard/refresh-status`

Returns the last-refresh timestamp for each data source (prices, earnings, market_caps, results, swing, kronos, watchlist).

#### Watchlist Endpoints

**GET** `/api/v1/watchlist` - Get current watchlist from `my_watchlist.txt`

**POST** `/api/v1/watchlist/add` - Add ticker to watchlist
```json
{"ticker": "RELIANCE.NS"}
```

**POST** `/api/v1/watchlist/remove` - Remove ticker from watchlist
```json
{"ticker": "RELIANCE.NS"}
```

---

## Usage Examples

### Python Requests

```python
import requests

BASE_URL = "http://localhost:8000"

# Health check
response = requests.get(f"{BASE_URL}/health")
print(response.json())

# Get market context for Apple
response = requests.get(f"{BASE_URL}/api/v1/market-context/AAPL")
apple_data = response.json()
print(f"AAPL Market Cap: ${apple_data['market_cap'] / 1e12:.2f}T")

# Get price history
response = requests.get(
    f"{BASE_URL}/api/v1/price-history/TCS.NS",
    params={
        "start_date": "2024-01-01",
        "end_date": "2024-06-30"
    }
)
prices = response.json()

# Get upcoming earnings for NSE large caps
response = requests.get(
    f"{BASE_URL}/api/v1/upcoming-earnings",
    params={"market": "NSE_LARGE_CAP", "days": 14}
)
upcoming = response.json()
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

const BASE_URL = "http://localhost:8000";

async function getMarketContext(ticker) {
  const response = await axios.get(`${BASE_URL}/api/v1/market-context/${ticker}`);
  return response.data;
}

// Example usage
getMarketContext('AAPL')
  .then(data => console.log(`Market Cap: $${(data.market_cap / 1e12).toFixed(2)}T`))
  .catch(err => console.error(err));
```

### PowerShell

```powershell
$baseUrl = "http://localhost:8000"

# Health check
Invoke-RestMethod -Uri "$baseUrl/health" -Method Get

# Get market context
$response = Invoke-RestMethod -Uri "$baseUrl/api/v1/market-context/AAPL" -Method Get
Write-Host "AAPL Market Cap: $($response.market_cap / 1e12)T"

# Get upcoming earnings
$upcoming = Invoke-RestMethod -Uri "$baseUrl/api/v1/upcoming-earnings?market=IN&days=14" -Method Get
```

---

## Integration with Postman

### Quick Import

1. Open Postman
2. Click **Import**
3. Select **Link** tab
4. Enter: `http://localhost:8000/openapi.json`
5. Click **Continue** → **Import**

This imports all endpoints automatically!

### Manual Setup

See [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md) for detailed Postman setup instructions.

---

## Configuration

### Environment Variables

The API server respects the following environment variables:

```bash
# Optional: Change the default port
export EARNINGS_ENGINE_API_PORT=8080

# Optional: Change host (default: 0.0.0.0)
export EARNINGS_ENGINE_API_HOST=127.0.0.1
```

### Port Configuration

```bash
# Start on custom port
python -m earnings_engine.api.server --port 8080

# Or with uvicorn
uvicorn earnings_engine.api.server:app --host 0.0.0.0 --port 8080
```

---

## Development

### Running with Auto-Reload

For development, use the `--reload` flag to automatically restart the server when code changes:

```bash
uvicorn earnings_engine.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Running Tests

```bash
# Run all tests
pytest

# Run API-specific tests
pytest test_api.py -v
```

### Project Structure

```
earnings_engine/
├── api/
│   └── server.py          # FastAPI server and endpoints
├── data/
│   ├── prices.py          # Price data loading and caching
│   ├── earnings.py        # Earnings data loading and caching
│   ├── universe.py        # Universe management
│   └── market_context.py  # Market context enrichment
├── reports/
│   └── render.py          # Report generation
└── ...

tests/
├── test_api.py            # API endpoint tests
└── ...
```

---

## Troubleshooting

### Port Already in Use

If port 8000 is already in use:

```bash
# Use a different port
python -m earnings_engine.api.server --port 8080
```

### Module Not Found Error

Ensure the package is installed in development mode:

```bash
pip install -e ".[dev]"
```

### CORS Errors

The API server has CORS enabled by default. If you encounter CORS issues, check that:
1. The server is running
2. You're using the correct origin in your requests
3. CORS middleware is properly configured in `server.py`

### Slow First Requests

The first request for a ticker downloads data from Yahoo Finance (slower). Subsequent requests use the parquet cache (much faster). This is expected behavior.

### Empty Responses

If you get empty responses:
1. The ticker might not have cached data yet
2. Try adding `force_refresh=true` to fetch fresh data
3. Check the server logs for errors

---

## Performance Tips

1. **Use caching:** The API leverages the parquet cache. After the first request, subsequent requests are much faster.

2. **Batch requests:** For multiple tickers, make parallel requests instead of sequential ones.

3. **Use appropriate date ranges:** Request only the data you need to reduce response size.

4. **Force refresh sparingly:** Only use `force_refresh=true` when you need fresh data. It's slower as it downloads from Yahoo Finance.

---

## API Response Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 404 | Ticker not found or no data available |
| 422 | Validation error (invalid parameters) |
| 500 | Internal server error |

---

## Rate Limiting

Currently, there is no rate limiting. However, please be respectful:
- Cache responses when possible
- Avoid rapid-fire requests in loops
- Use the `force_refresh` parameter judiciously

---

## Next Steps

1. ✅ Start the API server
2. ✅ Visit `http://localhost:8000/docs` to explore the interactive API documentation
3. ✅ Import the API into Postman using the OpenAPI schema
4. ✅ Test endpoints with your favorite API client
5. ✅ Integrate with your applications

For CLI usage and data ingestion, see the main [README.md](README.md).

## Support

For issues, questions, or contributions, visit the [GitHub repository](https://github.com/chandewardnyanesh/earnings-engine).