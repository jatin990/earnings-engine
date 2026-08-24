
from earnings_engine.config import Settings
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.nse_api import fetch_event_calendar
from datetime import date, datetime, timedelta
import pandas as pd
from typing import Any

def get_previous_trading_session(settings=None):
    settings = settings or Settings()
    today = datetime.now().date()
    try:
        latest = prices_mod._last_cached_date('_session_probe', settings)
    except Exception:
        latest = None
    if latest is not None:
        latest_date = latest.date() if hasattr(latest, 'date') else latest
        if latest_date >= today:
            with prices_mod._connect(settings) as con:
                row = con.execute('SELECT MAX(date) FROM price_history WHERE date < ?', (str(today),)).fetchone()
            if row and row[0]:
                return date.fromisoformat(row[0])
            return today - timedelta(days=1)
        return latest_date
    return today - timedelta(days=1)

def _load_prices_for_tickers(tickers, settings):
    return prices_mod.load_prices_batch(tickers, settings)

def _latest_price_row(prices):
    if prices is None or prices.empty or 'close' not in prices.columns:
        return None
    closes = pd.to_numeric(prices['close'], errors='coerce').dropna()
    if closes.empty:
        return None
    latest_date = closes.index[-1]
    row = prices.loc[latest_date]
    return {
        'date': str(latest_date.date()) if hasattr(latest_date, 'date') else str(latest_date),
        'open': float(row['open']) if 'open' in row else None,
        'high': float(row['high']) if 'high' in row else None,
        'low': float(row['low']) if 'low' in row else None,
        'close': float(row['close']) if 'close' in row else None,
        'volume': int(row['volume']) if 'volume' in row else None,
    }

def _change_pct(current, previous):
    if current is None or previous is None or previous == 0:
        return None
    return ((current / previous) - 1.0) * 100.0

def _to_iso(d):
    if d is None:
        return None
    return d.isoformat() if hasattr(d, 'isoformat') else str(d)

def get_event_calendar_for_date(target_date):
    from_date = target_date - timedelta(days=2)
    to_date = target_date + timedelta(days=2)
    raw = fetch_event_calendar(from_date, to_date)
    if isinstance(raw, dict) and raw.get('error'):
        return [], str(raw['error'])
    entries = []
    data = raw if isinstance(raw, list) else raw.get('data', [])
    if not isinstance(data, list):
        return [], 'Unexpected event-calendar payload shape'
    target_str = target_date.isoformat()
    for item in data:
        if not isinstance(item, dict):
            continue
        item_date = item.get('date') or item.get('bm_date') or ''
        if str(item_date).startswith(target_str):
            entries.append({
                'symbol': (item.get('symbol') or '').upper(),
                'company': item.get('company') or item.get('bm_desc') or '',
                'purpose': item.get('purpose') or item.get('bm_desc') or '',
                'date': str(item_date),
            })
    return entries, None

def get_buydip_today(settings=None):
    settings = settings or Settings()
    today = datetime.now().date()
    entries, err = get_event_calendar_for_date(today)
    if err:
        return {'success': False, 'error': err, 'date': _to_iso(today), 'rows': []}
    return {'success': True, 'date': _to_iso(today), 'rows': entries}

def get_buydip_yesterday(settings=None):
    settings = settings or Settings()
    prev_session = get_previous_trading_session(settings)
    if prev_session is None:
        return {'success': False, 'error': 'No previous trading session available', 'date': None, 'rows': []}
    entries, err = get_event_calendar_for_date(prev_session)
    if err:
        return {'success': False, 'error': err, 'date': _to_iso(prev_session), 'rows': []}
    tickers = sorted({e['symbol'] for e in entries if e['symbol']})
    price_map = _load_prices_for_tickers(tickers, settings)
    rows = []
    for e in entries:
        sym = e['symbol']
        if not sym:
            continue
        prices = price_map.get(sym, pd.DataFrame())
        latest = _latest_price_row(prices)
        current_price = latest['close'] if latest else None
        today_open = latest['open'] if latest else None
        prev_close = None
        if latest and not prices.empty and 'close' in prices.columns:
            closes = pd.to_numeric(prices['close'], errors='coerce').dropna()
            if len(closes) >= 2:
                prev_close = float(closes.iloc[-2])
        change_pct = _change_pct(current_price, prev_close)
        rows.append({
            'symbol': sym,
            'company': e.get('company', ''),
            'result_date': _to_iso(prev_session),
            'current_price': current_price,
            'today_open': today_open,
            'prev_close': prev_close,
            'pe': None,
            'change_pct': change_pct,
            'revenue': 'N/A',
            'net_profit': 'N/A',
            'yoy_pct': 'N/A',
        })
    rows.sort(key=lambda r: (r['change_pct'] is None, r['change_pct'] or 0))
    return {'success': True, 'date': _to_iso(prev_session), 'rows': rows}
