# Postman Guide for Earnings Engine API

This guide will help you test the Earnings Engine API using Postman.

## Prerequisites

1. **Start the API Server** (if not already running):
   ```bash
   python run_api.py
   ```
   The server will start at `http://localhost:8000`

2. **Install Postman** (if not already installed):
   - Download from: https://www.postman.com/downloads/

## Importing the API into Postman

### Option 1: Import from OpenAPI Schema

1. Open Postman
2. Click **Import** button
3. Select **Link** tab
4. Enter: `http://localhost:8000/openapi.json`
5. Click **Continue** → **Import**

This will import all API endpoints automatically!

### Option 2: Manual Setup

Follow the instructions below to manually create requests.

---

## API Endpoints for Postman

### 1. Health Check

**Method:** GET  
**URL:** `http://localhost:8000/health`

**Purpose:** Check if the API is running

**Response Example:**
```json
{
  "status": "ok",
  "service": "earnings-engine-api"
}
```

---

### 2. Price History

**Method:** GET  
**URL:** `http://localhost:8000/api/v1/price-history/{ticker}`

**Query Parameters:**
- `start_date` (optional): Start date in YYYY-MM-DD format
- `end_date` (optional): End date in YYYY-MM-DD format
- `force_refresh` (optional): Set to `true` to fetch fresh data from yfinance

**Example Request:**
```
GET http://localhost:8000/api/v1/price-history/AAPL?start_date=2024-01-01&end_date=2024-06-30
```

**Postman Setup:**
1. Create new GET request
2. URL: `http://localhost:8000/api/v1/price-history/AAPL`
3. Go to **Params** tab
4. Add key-value pairs:
   - `start_date` = `2024-01-01`
   - `end_date` = `2024-06-30`
5. Click **Send**

**Response Example:**
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

### 3. Earnings History

**Method:** GET  
**URL:** `http://localhost:8000/api/v1/earnings-history/{ticker}`

**Query Parameters:**
- `force_refresh` (optional): Set to `true` to fetch fresh data

**Example Request:**
```
GET http://localhost:8000/api/v1/earnings-history/MSFT
```

**Postman Setup:**
1. Create new GET request
2. URL: `http://localhost:8000/api/v1/earnings-history/MSFT`
3. Click **Send**

**Response Example:**
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

### 4. Market Cap

**Method:** GET  
**URL:** `http://localhost:8000/api/v1/market-cap/{ticker}`

**Example Request:**
```
GET http://localhost:8000/api/v1/market-cap/GOOGL
```

**Response Example:**
```json
{
  "ticker": "GOOGL",
  "market_cap": 2100000000000.0
}
```

---

### 5. Market Context (Comprehensive Data)

**Method:** GET  
**URL:** `http://localhost:8000/api/v1/market-context/{ticker}`

**Example Request:**
```
GET http://localhost:8000/api/v1/market-context/AAPL
```

**Response Example:**
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

### 6. Upcoming Earnings

**Method:** GET  
**URL:** `http://localhost:8000/api/v1/upcoming-earnings`

**Query Parameters:**
- `tickers` (optional): Comma-separated list of tickers
- `days` (optional): Number of days to look ahead (default: 14, max: 90)
- `market` (optional): Market universe to use

**Example Requests:**
```
# Specific tickers
GET http://localhost:8000/api/v1/upcoming-earnings?tickers=AAPL,MSFT,GOOGL&days=14

# Using market universe
GET http://localhost:8000/api/v1/upcoming-earnings?market=NSE_LARGE_CAP&days=30
```

**Postman Setup:**
1. Create new GET request
2. URL: `http://localhost:8000/api/v1/upcoming-earnings`
3. Go to **Params** tab
4. Add key-value pairs:
   - `tickers` = `AAPL,MSFT,GOOGL`
   - `days` = `14`
5. Click **Send**

**Response Example:**
```json
[
  {
    "ticker": "AAPL",
    "earnings_date": "2024-10-31"
  }
]
```

---

### 7. Universe

**Method:** GET  
**URL:** `http://localhost:8000/api/v1/universe/{market}`

**Supported Markets:**
- `IN` - Indian stocks (top 44)
- `US` - US stocks
- `NSE_ALL` - All NSE stocks (~2000+)
- `NSE_LARGE_CAP` - NSE large cap stocks (>1000cr market cap)

**Example Requests:**
```
GET http://localhost:8000/api/v1/universe/IN
GET http://localhost:8000/api/v1/universe/NSE_LARGE_CAP
```

**Response Example:**
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

### 8. All Market Caps

**Method:** GET  
**URL:** `http://localhost:8000/api/v1/market-caps`

**Purpose:** Get all cached market caps

**Response Example:**
```json
{
  "AAPL": 4537070911488.0,
  "MSFT": 3100000000000.0,
  "GOOGL": 2100000000000.0
}
```

---

## Creating a Postman Collection

### Step 1: Create a New Collection

1. Click **Collections** in the left sidebar
2. Click **New Collection**
3. Name it: `Earnings Engine API`
4. Click **Create**

### Step 2: Add Requests to Collection

For each endpoint above:
1. Create a new request
2. Configure the method, URL, and parameters
3. Click **Save** and select your `Earnings Engine API` collection

### Step 3: Organize with Folders (Optional)

Create folders in your collection:
- **Market Data** - Price history, market cap, market context
- **Earnings** - Earnings history, upcoming earnings
- **Universe** - Universe endpoints

---

## Using Environment Variables (Recommended)

To make your requests more flexible:

### Step 1: Create an Environment

1. Click **Environments** in the left sidebar
2. Click **New**
3. Name it: `Earnings Engine Local`
4. Add variable:
   - **Variable:** `base_url`
   - **Initial Value:** `http://localhost:8000`
   - **Current Value:** `http://localhost:8000`
5. Click **Save**

### Step 2: Use Environment Variables

Now use `{{base_url}}` in your requests:

```
GET {{base_url}}/api/v1/price-history/AAPL?start_date=2024-01-01&end_date=2024-06-30
```

### Step 3: Select Environment

1. Click the environment dropdown in the top-right (usually shows "No Environment")
2. Select `Earnings Engine Local`

---

## Example Postman Test Scenarios

### Scenario 1: Analyze Apple Stock

1. **Get Market Context:**
   ```
   GET {{base_url}}/api/v1/market-context/AAPL
   ```
   Review: current price, market cap, earnings scores, support/resistance

2. **Get Price History:**
   ```
   GET {{base_url}}/api/v1/price-history/AAPL?start_date=2024-01-01&end_date=2024-06-30
   ```
   Review: Price trends over 6 months

3. **Get Earnings History:**
   ```
   GET {{base_url}}/api/v1/earnings-history/AAPL
   ```
   Review: Past earnings performance and surprises

### Scenario 2: Find Upcoming Earnings

1. **Get NSE Large Cap Universe:**
   ```
   GET {{base_url}}/api/v1/universe/NSE_LARGE_CAP
   ```

2. **Get Upcoming Earnings:**
   ```
   GET {{base_url}}/api/v1/upcoming-earnings?market=NSE_LARGE_CAP&days=14
   ```

3. **For each upcoming ticker, get market context:**
   ```
   GET {{base_url}}/api/v1/market-context/RELIANCE.NS
   ```

### Scenario 3: Compare Multiple Stocks

1. **Get market context for multiple tickers:**
   ```
   GET {{base_url}}/api/v1/market-context/AAPL
   GET {{base_url}}/api/v1/market-context/MSFT
   GET {{base_url}}/api/v1/market-context/GOOGL
   ```

2. **Compare:**
   - Market caps
   - Current prices
   - Earnings quality scores
   - 30-day returns

---

## Tips for Postman

### 1. Save Responses
- Click **Save Response** in the response body to save examples
- Useful for documentation and testing

### 2. Use Tests Tab
Add automated tests in the **Tests** tab:

```javascript
// Test: Check status code
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

// Test: Check response has data
pm.test("Response has data", function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData.length).to.be.greaterThan(0);
});

// Test: Check specific field exists
pm.test("Market cap exists", function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('market_cap');
});
```

### 3. Use Collection Runner
To run multiple requests in sequence:
1. Click **Runner** in the left sidebar
2. Select your `Earnings Engine API` collection
3. Click **Run**

### 4. Generate Code Snippets
For each request:
1. Click **Code** button (</> icon)
2. Select language (Python, JavaScript, etc.)
3. Copy generated code

---

## Troubleshooting

### Connection Refused
- Make sure the API server is running: `python run_api.py`
- Check if port 8000 is available
- Try changing the port in `run_api.py`

### Empty Responses
- The ticker might not have cached data
- Try adding `force_refresh=true` to fetch fresh data
- First requests take longer (downloading from yfinance)

### Slow Responses
- First request for a ticker downloads from yfinance (slower)
- Subsequent requests use cache (much faster)
- This is normal behavior

---

## Quick Reference Card

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/api/v1/price-history/{ticker}` | GET | OHLCV price data |
| `/api/v1/earnings-history/{ticker}` | GET | Earnings history |
| `/api/v1/market-cap/{ticker}` | GET | Current market cap |
| `/api/v1/market-context/{ticker}` | GET | Comprehensive market data |
| `/api/v1/upcoming-earnings` | GET | Upcoming earnings events |
| `/api/v1/universe/{market}` | GET | Ticker universe |
| `/api/v1/market-caps` | GET | All cached market caps |

---

## Next Steps

1. ✅ Import the API into Postman
2. ✅ Test each endpoint
3. ✅ Create a collection with your most-used requests
4. ✅ Set up environment variables
5. ✅ Add automated tests
6. ✅ Share the collection with your team

For more information, see [API_README.md](API_README.md)