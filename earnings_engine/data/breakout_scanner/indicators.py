"""Technical indicators, VCP detection, squeeze calculators, and decision metrics."""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from earnings_engine.config import Settings


def _score_resistance_proximity(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-40, pct_from_high).

    Points awarded based on how close current price is to the recent high.
    Closer = higher score. Being above high = breakout already = also high.
    """
    if len(closes) < 2:
        return 0.0, float("nan")
    vals = closes.values
    current = float(vals[-1])
    window = min(len(vals), 252)   # up to 1 year
    high = float(vals[-window:].max())
    if high <= 0:
        return 0.0, float("nan")
    pct_from_high = (current - high) / high * 100  # negative = below high
    if pct_from_high >= 0:           # above or at high (breakout)
        score = 40.0
    elif pct_from_high >= -1:
        score = 37.0
    elif pct_from_high >= -2:
        score = 32.0
    elif pct_from_high >= -3:
        score = 25.0
    elif pct_from_high >= -5:
        score = 15.0
    elif pct_from_high >= -8:
        score = 5.0
    else:
        score = 0.0
    return score, pct_from_high


def _score_volume_surge(volumes: pd.Series) -> tuple[float, float]:
    """Return (score 0-10, vol_ratio).

    Vol today vs 20D avg. Reward strong institutional accumulation and breakout volume expansion.
    """
    if len(volumes) < 5:
        return 0.0, float("nan")
    vals = volumes.values
    avg_20 = float(vals[-21:-1].mean()) if len(vals) >= 21 else float(vals.mean())
    today = float(vals[-1])
    if avg_20 <= 0:
        return 0.0, float("nan")
    ratio = today / avg_20
    if ratio >= 2.0:
        score = 10.0
    elif 1.5 <= ratio < 2.0:
        score = 8.0
    elif 1.25 <= ratio < 1.5:
        score = 6.0
    elif 1.0 <= ratio < 1.25:
        score = 3.0
    else:
        score = 0.0
    return score, round(ratio, 2)


def _calc_atr_pct(closes: pd.Series, default: float = 2.0) -> float:
    """Calculate 14-day average true range as percentage of price using vectorized numpy.

    Guards against division by zero on non-positive prices and handles NaN values gracefully.
    """
    if closes is None or len(closes) < 15:
        return default
    vals = closes.values[-15:]
    denom = np.where(vals[:-1] == 0, 1.0, vals[:-1])
    daily_range = abs(vals[1:] - vals[:-1]) / denom
    atr = float(daily_range.mean()) * 100.0
    return atr if (atr > 0 and not np.isnan(atr)) else default


def _score_price_compression(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-10, atr_pct).

    ATR(14) / price. Low ratio = price coiling = potential energy.
    """
    if len(closes) < 15:
        return 0.0, float("nan")
    atr_pct = _calc_atr_pct(closes, default=0.0)
    if np.isnan(atr_pct) or atr_pct <= 0:
        return 0.0, float("nan")
    if atr_pct < 0.5:
        score = 10.0
    elif atr_pct < 1.0:
        score = 8.0
    elif atr_pct < 1.5:
        score = 5.0
    elif atr_pct < 2.5:
        score = 2.0
    else:
        score = 0.0
    return score, round(atr_pct, 3)


def _score_momentum(closes: pd.Series) -> tuple[float, str]:
    """Return (score 0-25, signal).

    30D return > 0 AND price > 20D SMA → strong momentum.
    """
    if len(closes) < 20:
        return 0.0, "insufficient"
    vals = closes.values
    current = float(vals[-1])
    sma_20 = float(vals[-20:].mean())
    ref_val = float(vals[max(0, len(vals) - 31)])
    ret_30 = float((current / ref_val) - 1) * 100 if ref_val > 0 else 0.0

    above_sma = current > sma_20
    positive_momentum = ret_30 > 0

    if above_sma and positive_momentum and ret_30 > 5:
        score, signal = 25.0, "Strong"
    elif above_sma and positive_momentum:
        score, signal = 18.0, "Moderate"
    elif above_sma or positive_momentum:
        score, signal = 8.0, "Weak"
    else:
        score, signal = 0.0, "None"
    return score, signal


def _score_fundamental(quality_scores: list[float | None]) -> tuple[float, float]:
    """Return (score 0-15, avg_quality).

    Takes a list of quality scores (each 1-9) from q1/q2/q3 earnings history.
    Normalised: avg=9 → 15 pts, avg=1 → 0 pts.
    """
    valid = [q for q in quality_scores if q is not None and not (isinstance(q, float) and np.isnan(q))]
    if not valid:
        return 0.0, float("nan")
    avg_q = float(np.mean(valid))
    score = round((avg_q - 1) / 8 * 15, 1)   # map [1,9] → [0,15]
    return max(0.0, min(15.0, score)), round(avg_q, 2)


def _calculate_volume_profile_detailed(
    df: pd.DataFrame, num_bins: int = 30
) -> tuple[float, float, float, float, list[dict[str, Any]]]:
    """Calculate Point of Control (POC), Value Area High (VAH), Value Area Low (VAL),
    LVN ratio, and detailed price-level volume bins across historical dataframe.

    Returns (poc, vah, val, lvn_ratio_above_vah, profile_bins).
    """
    if df.empty or "close" not in df.columns:
        return 0.0, 0.0, 0.0, 1.0, []

    closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(closes) < 5:
        p = float(closes.iloc[-1]) if not closes.empty else 0.0
        return p, p, p, 1.0, []

    highs = pd.to_numeric(df["high"], errors="coerce").dropna() if "high" in df.columns else closes
    lows = pd.to_numeric(df["low"], errors="coerce").dropna() if "low" in df.columns else closes
    volumes = pd.to_numeric(df["volume"], errors="coerce") if "volume" in df.columns else pd.Series(1.0, index=closes.index)
    volumes.fillna(0, inplace=True)

    p_min = float(lows.min()) if not lows.empty else float(closes.min())
    p_max = float(highs.max()) if not highs.empty else float(closes.max())
    if p_min == p_max:
        p = float(closes.iloc[-1])
        return p, p, p, 1.0, [{
            "price": round(p, 2),
            "volume": int(volumes.sum()),
            "buy_volume": int(volumes.sum() / 2),
            "sell_volume": int(volumes.sum() / 2),
            "is_poc": True,
            "is_va": True,
        }]

    bins = np.linspace(p_min, p_max, num_bins + 1)
    bin_volumes = np.zeros(num_bins)
    bin_buy_vols = np.zeros(num_bins)
    bin_sell_vols = np.zeros(num_bins)

    for idx_row, row in df.iterrows():
        c = float(row.get("close") or 0.0)
        h = float(row.get("high") or c)
        l = float(row.get("low") or c)
        v = float(row.get("volume") or 0.0)
        rng = max(0.01, h - l)
        buy_ratio = max(0.05, min(0.95, (c - l) / rng))
        bar_buy = v * buy_ratio
        bar_sell = v * (1.0 - buy_ratio)

        b_idx = int(np.digitize(c, bins) - 1)
        b_idx = max(0, min(num_bins - 1, b_idx))
        bin_volumes[b_idx] += v
        bin_buy_vols[b_idx] += bar_buy
        bin_sell_vols[b_idx] += bar_sell

    total_vol = float(np.sum(bin_volumes))
    if total_vol <= 0:
        p = float(closes.iloc[-1])
        return p, p, p, 1.0, []

    poc_idx = int(np.argmax(bin_volumes))
    poc_price = float((bins[poc_idx] + bins[poc_idx + 1]) / 2.0)

    target_va_vol = total_vol * 0.70
    cum_vol = bin_volumes[poc_idx]
    lower_idx = poc_idx
    upper_idx = poc_idx

    while cum_vol < target_va_vol and (lower_idx > 0 or upper_idx < num_bins - 1):
        next_upper = bin_volumes[upper_idx + 1] if upper_idx < num_bins - 1 else 0
        next_lower = bin_volumes[lower_idx - 1] if lower_idx > 0 else 0
        if next_upper >= next_lower and upper_idx < num_bins - 1:
            upper_idx += 1
            cum_vol += bin_volumes[upper_idx]
        elif lower_idx > 0:
            lower_idx -= 1
            cum_vol += bin_volumes[lower_idx]
        else:
            break

    vah_price = float((bins[upper_idx] + bins[upper_idx + 1]) / 2.0)
    val_price = float((bins[lower_idx] + bins[lower_idx + 1]) / 2.0)

    avg_bin_vol = total_vol / num_bins
    vol_above_vah = float(np.mean(bin_volumes[upper_idx + 1:])) if upper_idx < num_bins - 1 else 0.0
    lvn_ratio = vol_above_vah / max(1.0, avg_bin_vol)

    profile_bins = []
    max_bin_vol = max(1.0, float(np.max(bin_volumes)))
    for i in range(num_bins):
        mid_p = float((bins[i] + bins[i + 1]) / 2.0)
        v = float(bin_volumes[i])
        bv = float(bin_buy_vols[i])
        sv = float(bin_sell_vols[i])
        profile_bins.append({
            "price": round(mid_p, 2),
            "volume": int(v),
            "buy_volume": int(bv),
            "sell_volume": int(sv),
            "volume_pct": round((v / max_bin_vol) * 100, 1),
            "delta": int(bv - sv),
            "is_poc": bool(i == poc_idx),
            "is_vah": bool(i == upper_idx),
            "is_val": bool(i == lower_idx),
            "in_value_area": bool(lower_idx <= i <= upper_idx),
        })

    return poc_price, vah_price, val_price, lvn_ratio, profile_bins


def _calculate_volume_profile(df: pd.DataFrame, num_bins: int = 30) -> tuple[float, float, float, float]:
    """Calculate Point of Control (POC) and Value Area High (VAH) across historical dataframe.

    Returns (poc, vah, val, lvn_ratio_above_vah).
    """
    poc_price, vah_price, val_price, lvn_ratio, _ = _calculate_volume_profile_detailed(df, num_bins=num_bins)
    return poc_price, vah_price, val_price, lvn_ratio


def _calculate_donchian_ttm_squeeze(
    closes: pd.Series, highs: pd.Series, lows: pd.Series
) -> tuple[bool, float, float, float, float]:
    """Calculate John Carter TTM Volatility Squeeze (Bollinger Bands vs Keltner Channels) and 55D Donchian High.

    Returns (squeeze_on, donchian_55_high, momentum_osc, bb_width_pct, kc_width_pct).
    """
    if len(closes) < 20:
        c = float(closes.iloc[-1]) if not closes.empty else 0.0
        return False, c, 0.0, 0.0, 0.0

    c = pd.to_numeric(closes, errors="coerce").dropna()
    h = pd.to_numeric(highs, errors="coerce").dropna() if not highs.empty else c
    l = pd.to_numeric(lows, errors="coerce").dropna() if not lows.empty else c

    sma_20 = float(c.tail(20).mean())
    std_20 = float(c.tail(20).std(ddof=0))
    bb_upper = sma_20 + 2.0 * std_20
    bb_lower = sma_20 - 2.0 * std_20
    bb_width = bb_upper - bb_lower

    tr1 = h - l
    tr2 = (h - c.shift(1)).abs()
    tr3 = (l - c.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_20 = float(tr.tail(20).mean()) if len(tr) >= 20 else float(c.tail(20).std(ddof=0))
    kc_upper = sma_20 + 1.5 * atr_20
    kc_lower = sma_20 - 1.5 * atr_20
    kc_width = kc_upper - kc_lower

    squeeze_on = bool(bb_upper <= kc_upper and bb_lower >= kc_lower)
    donchian_window = min(len(h), 55)
    donchian_55_high = float(h.tail(donchian_window).max())

    cur_p = float(c.iloc[-1])
    mom_osc = ((cur_p - sma_20) / max(0.01, sma_20)) * 100.0
    bb_width_pct = (bb_width / max(0.01, cur_p)) * 100.0
    kc_width_pct = (kc_width / max(0.01, cur_p)) * 100.0

    return squeeze_on, donchian_55_high, mom_osc, bb_width_pct, kc_width_pct


def _detect_vcp_pattern(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    volumes: pd.Series,
    lookback: int = 60,
) -> dict[str, Any]:
    """Detect Mark Minervini's Volatility Contraction Pattern (VCP).

    Analyzes wave contractions across trailing swing pivots:
    - Measures contraction depth: (Swing High - Swing Low) / Swing High * 100
    - Enforces progressive contraction: C1 > C2 > C3...
    - Detects volume dry-up on the final contraction wave before breakout pivot.
    """
    if len(closes) < 30:
        return {
            "is_vcp": False,
            "stage": "None",
            "num_contractions": 0,
            "contractions_pct": [],
            "volume_dry_up": False,
            "pivot_level": None,
        }

    w_highs = highs.tail(lookback).values
    w_lows = lows.tail(lookback).values
    w_closes = closes.tail(lookback).values
    w_vols = volumes.tail(lookback).values
    n = len(w_closes)

    # Identify swing highs (local peaks) and swing lows (local troughs)
    peaks = []
    troughs = []
    order = 3
    for i in range(order, n - order):
        if w_highs[i] == max(w_highs[i - order : i + order + 1]):
            peaks.append((i, float(w_highs[i])))
        if w_lows[i] == min(w_lows[i - order : i + order + 1]):
            troughs.append((i, float(w_lows[i])))

    if len(peaks) < 2 or len(troughs) < 2:
        return {
            "is_vcp": False,
            "stage": "None",
            "num_contractions": 0,
            "contractions_pct": [],
            "volume_dry_up": False,
            "pivot_level": None,
        }

    contractions = []
    for i in range(min(len(peaks), len(troughs))):
        p_price = peaks[i][1]
        sub_troughs = [t[1] for t in troughs if t[0] >= peaks[i][0]]
        if sub_troughs:
            t_price = min(sub_troughs)
            if p_price > 0:
                depth = round(((p_price - t_price) / p_price) * 100.0, 1)
                if depth > 0.5:
                    contractions.append(depth)

    is_contracting = False
    valid_contractions = []
    if len(contractions) >= 2:
        tail_c = contractions[-4:]
        if all(tail_c[j] >= tail_c[j + 1] * 0.9 for j in range(len(tail_c) - 1)) and tail_c[-1] <= 10.0:
            is_contracting = True
            valid_contractions = tail_c

    avg_vol_20 = float(np.mean(w_vols[-20:])) if len(w_vols) >= 20 else float(np.mean(w_vols))
    recent_vol = float(np.mean(w_vols[-5:])) if len(w_vols) >= 5 else avg_vol_20
    volume_dry_up = bool(avg_vol_20 > 0 and recent_vol <= avg_vol_20 * 0.85)

    is_vcp = bool(is_contracting and len(valid_contractions) >= 2)
    num_c = len(valid_contractions)
    pivot_level = round(float(peaks[-1][1]), 2) if peaks else None

    if is_vcp:
        c_str = " -> ".join(f"{c:.1f}%" for c in valid_contractions)
        stage = f"VCP {num_c}T Coiled ({c_str})"
    elif is_contracting:
        stage = f"VCP Developing ({len(contractions)} Waves)"
    else:
        stage = "No VCP"

    return {
        "is_vcp": is_vcp,
        "stage": stage,
        "num_contractions": num_c,
        "contractions_pct": valid_contractions,
        "volume_dry_up": volume_dry_up,
        "pivot_level": pivot_level,
    }


def compute_technical_decision_metrics(
    ticker: str,
    prices_df: pd.DataFrame | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compute comprehensive technical decision metrics for email alerts and trading context.

    Extracts:
    - Moving averages: SMA 20, 50, 200, EMA 8, EMA 21 and percentage distances
    - Trend Alignment: Bullish Golden Stack, Bullish Alignment, Above 200 SMA, Below 200 SMA
    - Supertrend: 10-period 3.0-multiplier direction and stop level
    - 52-Week Range: High, Low, % from 52W High, % from 52W Low, 20D Range %
    - Volatility & Squeeze: ATR(14) %, John Carter TTM Volatility Squeeze, Minervini VCP status
    - Momentum & Flow: RSI(14), 20D Volume Surge Ratio, 30D Return %
    """
    settings = settings or Settings()
    if prices_df is None or prices_df.empty or len(prices_df) < 5:
        from earnings_engine.data.prices import load_prices
        sym = ticker.strip().upper()
        if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
            sym = f"{sym}.NS"
        prices_df = load_prices(sym, settings)
        if prices_df is None or len(prices_df) < 5:
            prices_df = load_prices(ticker.strip().upper(), settings)

    if prices_df is None or prices_df.empty or len(prices_df) < 5:
        return {
            "sma_20": None, "sma_50": None, "sma_200": None,
            "ema_8": None, "ema_21": None,
            "dist_sma_20_pct": None, "dist_sma_50_pct": None, "dist_sma_200_pct": None,
            "dist_ema_8_pct": None, "dist_ema_21_pct": None,
            "ema_ribbon_bullish": False,
            "trend_alignment": "Unknown",
            "supertrend_direction": "UNKNOWN",
            "supertrend_value": None,
            "high_52w": None, "low_52w": None,
            "dist_52w_high_pct": None, "dist_52w_low_pct": None,
            "range_20d_pct": None,
            "atr_14": None, "atr_14_pct": None,
            "squeeze_on": False,
            "vcp_pattern": {
                "is_vcp": False, "stage": "None", "num_contractions": 0,
                "contractions_pct": [], "volume_dry_up": False, "pivot_level": None,
            },
            "rsi_14": None,
            "volume_surge_ratio": None,
            "ret_30d_pct": None,
        }

    closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
    if closes.empty:
        return {
            "sma_20": None, "sma_50": None, "sma_200": None,
            "ema_8": None, "ema_21": None,
            "dist_sma_20_pct": None, "dist_sma_50_pct": None, "dist_sma_200_pct": None,
            "dist_ema_8_pct": None, "dist_ema_21_pct": None,
            "ema_ribbon_bullish": False,
            "trend_alignment": "Unknown",
            "supertrend_direction": "UNKNOWN",
            "supertrend_value": None,
            "high_52w": None, "low_52w": None,
            "dist_52w_high_pct": None, "dist_52w_low_pct": None,
            "range_20d_pct": None,
            "atr_14": None, "atr_14_pct": None,
            "squeeze_on": False,
            "vcp_pattern": {
                "is_vcp": False, "stage": "None", "num_contractions": 0,
                "contractions_pct": [], "volume_dry_up": False, "pivot_level": None,
            },
            "rsi_14": None,
            "volume_surge_ratio": None,
            "ret_30d_pct": None,
        }

    highs = pd.to_numeric(prices_df["high"], errors="coerce").dropna() if "high" in prices_df.columns else closes
    lows = pd.to_numeric(prices_df["low"], errors="coerce").dropna() if "low" in prices_df.columns else closes
    volumes = pd.to_numeric(prices_df["volume"], errors="coerce") if "volume" in prices_df.columns else pd.Series(0.0, index=closes.index)
    volumes.fillna(0, inplace=True)

    current_price = float(closes.iloc[-1])

    # Moving Averages (Simple & Exponential)
    sma_20 = float(closes.values[-20:].mean()) if len(closes) >= 20 else float(closes.mean())
    sma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else (float(closes.mean()) if len(closes) >= 20 else None)
    sma_200 = float(closes.tail(200).mean()) if len(closes) >= 200 else (float(closes.mean()) if len(closes) >= 100 else None)

    ema_8 = float(closes.ewm(span=8, adjust=False).mean().iloc[-1]) if len(closes) >= 8 else None
    ema_21 = float(closes.ewm(span=21, adjust=False).mean().iloc[-1]) if len(closes) >= 21 else None

    dist_sma_20_pct = round(((current_price - sma_20) / sma_20) * 100.0, 2) if sma_20 and sma_20 > 0 else None
    dist_sma_50_pct = round(((current_price - sma_50) / sma_50) * 100.0, 2) if sma_50 and sma_50 > 0 else None
    dist_sma_200_pct = round(((current_price - sma_200) / sma_200) * 100.0, 2) if sma_200 and sma_200 > 0 else None
    dist_ema_8_pct = round(((current_price - ema_8) / ema_8) * 100.0, 2) if ema_8 and ema_8 > 0 else None
    dist_ema_21_pct = round(((current_price - ema_21) / ema_21) * 100.0, 2) if ema_21 and ema_21 > 0 else None
    ema_ribbon_bullish = bool(ema_8 and ema_21 and ema_8 > ema_21 and current_price >= ema_8)

    # Trend Alignment
    if sma_20 is not None and sma_50 is not None and sma_200 is not None:
        if current_price >= sma_20 >= sma_50 >= sma_200:
            trend_alignment = "Bullish Golden Stack (P > 20 > 50 > 200)"
        elif current_price >= sma_50 >= sma_200:
            trend_alignment = "Bullish Alignment (P > 50 > 200)"
        elif current_price >= sma_200:
            trend_alignment = "Above 200 SMA (Long-Term Bullish)"
        else:
            trend_alignment = "Below 200 SMA (Counter-Trend Setup)"
    elif sma_20 is not None and sma_50 is not None:
        if current_price >= sma_20 >= sma_50:
            trend_alignment = "Bullish Alignment (P > 20 > 50)"
        elif current_price >= sma_50:
            trend_alignment = "Above 50 SMA"
        else:
            trend_alignment = "Below 50 SMA"
    else:
        trend_alignment = "Short-Term Up" if current_price >= sma_20 else "Consolidating"

    # 52W & 20D Ranges
    w52_len = min(len(closes), 252)
    high_52w = float(highs.tail(w52_len).max())
    low_52w = float(lows.tail(w52_len).min())
    dist_52w_high_pct = round(((current_price - high_52w) / high_52w) * 100.0, 2) if high_52w > 0 else 0.0
    dist_52w_low_pct = round(((current_price - low_52w) / low_52w) * 100.0, 2) if low_52w > 0 else 0.0

    w20_len = min(len(closes), 20)
    high_20d = float(highs.tail(w20_len).max())
    low_20d = float(lows.tail(w20_len).min())
    range_20d_pct = round(((high_20d - low_20d) / max(0.01, current_price)) * 100.0, 2)

    # ATR(14) & True Range
    tr1 = (highs - lows).abs()
    tr2 = (highs - closes.shift(1)).abs()
    tr3 = (lows - closes.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_14 = float(tr.tail(14).mean()) if len(tr) >= 14 else float(tr.mean())
    atr_14_pct = round((atr_14 / max(0.01, current_price)) * 100.0, 2) if current_price > 0 else 0.0

    # TTM Squeeze
    squeeze_on = False
    if len(closes) >= 20:
        std_20 = float(closes.tail(20).std(ddof=0))
        bb_upper = sma_20 + 2.0 * std_20
        bb_lower = sma_20 - 2.0 * std_20
        atr_20 = float(tr.tail(20).mean()) if len(tr) >= 20 else atr_14
        kc_upper = sma_20 + 1.5 * atr_20
        kc_lower = sma_20 - 1.5 * atr_20
        squeeze_on = bool(bb_upper <= kc_upper and bb_lower >= kc_lower)

    # Supertrend (10, 3.0)
    supertrend_direction = "UNKNOWN"
    supertrend_value = None
    if len(closes) >= 15:
        hl2 = (highs + lows) / 2.0
        matr = tr.rolling(10).mean()
        upper_basic = hl2 + (3.0 * matr)
        lower_basic = hl2 - (3.0 * matr)

        final_upper = upper_basic.copy()
        final_lower = lower_basic.copy()
        supertrend = pd.Series(index=closes.index, dtype=float)
        direction = pd.Series(index=closes.index, dtype=int)

        for i in range(10, len(closes)):
            if upper_basic.iloc[i] < final_upper.iloc[i - 1] or closes.iloc[i - 1] > final_upper.iloc[i - 1]:
                final_upper.iloc[i] = upper_basic.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i - 1]

            if lower_basic.iloc[i] > final_lower.iloc[i - 1] or closes.iloc[i - 1] < final_lower.iloc[i - 1]:
                final_lower.iloc[i] = lower_basic.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i - 1]

            if closes.iloc[i] > final_upper.iloc[i - 1]:
                direction.iloc[i] = 1
            elif closes.iloc[i] < final_lower.iloc[i - 1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i - 1] if i > 10 else 1

            supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

        if not supertrend.dropna().empty:
            supertrend_value = round(float(supertrend.iloc[-1]), 2)
            supertrend_direction = "BULLISH" if direction.iloc[-1] == 1 else "BEARISH"

    # VCP Pattern Detection
    vcp_result = _detect_vcp_pattern(highs, lows, closes, volumes, lookback=60)

    # RSI(14)
    rsi_14 = None
    if len(closes) >= 15:
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.tail(14).mean()
        avg_loss = loss.tail(14).mean()
        if avg_loss == 0:
            rsi_14 = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_14 = round(100.0 - (100.0 / (1.0 + rs)), 1)

    # Volume Surge Ratio
    volume_surge_ratio = None
    if len(volumes) >= 5:
        avg_vol_20 = float(volumes.tail(21).iloc[:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
        today_vol = float(volumes.iloc[-1])
        if avg_vol_20 > 0:
            volume_surge_ratio = round(today_vol / avg_vol_20, 2)

    # 7D Return %
    ret_7d_pct = None
    if len(closes) >= 6:
        idx_7 = max(0, len(closes) - 8)
        ret_7d_pct = round(((current_price / float(closes.iloc[idx_7])) - 1.0) * 100.0, 2)

    # 30D Return %
    ret_30d_pct = None
    if len(closes) >= 20:
        idx_30 = max(0, len(closes) - 31)
        ret_30d_pct = round(((current_price / float(closes.iloc[idx_30])) - 1.0) * 100.0, 2)

    return {
        "current_price": round(current_price, 2),
        "sma_20": round(sma_20, 2) if sma_20 is not None else None,
        "sma_50": round(sma_50, 2) if sma_50 is not None else None,
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "ema_8": round(ema_8, 2) if ema_8 is not None else None,
        "ema_21": round(ema_21, 2) if ema_21 is not None else None,
        "dist_sma_20_pct": dist_sma_20_pct,
        "dist_sma_50_pct": dist_sma_50_pct,
        "dist_sma_200_pct": dist_sma_200_pct,
        "dist_ema_8_pct": dist_ema_8_pct,
        "dist_ema_21_pct": dist_ema_21_pct,
        "ema_ribbon_bullish": ema_ribbon_bullish,
        "trend_alignment": trend_alignment,
        "supertrend_direction": supertrend_direction,
        "supertrend_value": supertrend_value,
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "dist_52w_high_pct": dist_52w_high_pct,
        "dist_52w_low_pct": dist_52w_low_pct,
        "range_20d_pct": range_20d_pct,
        "atr_14": round(atr_14, 2),
        "atr_14_pct": atr_14_pct,
        "squeeze_on": squeeze_on,
        "vcp_pattern": vcp_result,
        "rsi_14": rsi_14,
        "volume_surge_ratio": volume_surge_ratio,
        "ret_30d_pct": ret_30d_pct,
        "ret_7d_pct": ret_7d_pct,
    }
