---
name: nse-data-toolkit
description: Indian National Stock Exchange (NSE) and BSE data processing, Bhavcopy parsers, corporate earnings calendars, deliverable volume spikes, circuit filters, and institutional flows (FII/DII).
---

# NSE Data Toolkit Skill

## Overview
Domain knowledge, data structures, and scraping/API patterns for Indian equity markets (National Stock Exchange of India - NSE & Bombay Stock Exchange - BSE).

## Key Indian Market Concepts

### 1. Ticker Symbol Standard & Suffixes
- NSE symbols in Yahoo Finance / Jugaad Data require `.NS` (e.g. `RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `INFY.NS`).
- BSE symbols use `.BO` (e.g. `500325.BO` or `RELIANCE.BO`).

### 2. Bhavcopy & Delivery Position Analysis
- **Total Traded Volume vs. Deliverable Volume**: A sudden spike in *Delivery %* (> 60–70% of total volume) preceding earnings often indicates institutional accumulation by Domestic Institutional Investors (DII) or Foreign Institutional Investors (FII).
- **Circuit Filters**: Stocks have daily price bands (2%, 5%, 10%, 20%), while F&O (Futures & Options) constituent stocks have no fixed daily circuits (only dynamic cooling pauses).

### 3. Corporate Actions & Earnings Calendar
- **Board Meetings & Financial Results**: Companies file prior intimation with NSE (usually 7–14 days in advance) declaring the date of the Board Meeting to consider financial results.
- **NSE Corporate Filing URLs**:
  - API endpoint: `https://www.nseindia.com/api/corporate-announcements?index=equities`
  - Required headers: `User-Agent`, `Accept-Language`, `Referer: https://www.nseindia.com/` (with initial session cookie handshake on home page).

### 4. Market Hours (IST - Indian Standard Time, UTC+5:30)
- **Pre-Open**: 09:00 AM – 09:08 AM IST
- **Normal Trading**: 09:15 AM – 03:30 PM IST
- **Post-Market / Closing**: 03:40 PM – 04:00 PM IST
- Results announced after 03:30 PM reflect in price action on the next trading day's session.
