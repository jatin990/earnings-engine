"""Order Flow, Volume Profile (TPO), Cumulative Volume Delta (CVD), and Liquidity Walls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner.indicators import _calculate_volume_profile_detailed


def get_order_flow_analytics(
    ticker: str,
    settings: Settings | None = None,
    lookback_days: int = 63,
) -> dict[str, Any]:
    """Calculate GoCharting-grade Order Flow, Volume Profile (TPO), Cumulative Volume Delta (CVD),
    and Liquidity Walls for BSE and NSE equities.
    """
    settings = settings or Settings()
    from earnings_engine.data.prices import canonical_symbol, load_prices, fetch_live_quote

    sym = ticker.strip().upper()
    if sym.startswith("BSE:"):
        raw_sym = sym.split(":", 1)[1]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = canonical_symbol(f"{raw_sym}.BO" if not raw_sym.endswith((".BO", ".NS")) else raw_sym)
    elif sym.startswith("NSE:"):
        raw_sym = sym.split(":", 1)[1]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = canonical_symbol(f"{raw_sym}.NS" if not raw_sym.endswith((".BO", ".NS")) else raw_sym)
    elif sym.endswith(".BO"):
        raw_sym = sym[:-3]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = sym
    elif sym.endswith(".NS"):
        raw_sym = sym[:-3]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = sym
    else:
        raw_sym = sym
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = canonical_symbol(sym)

    # 1. Load price data with fallback cascade
    df = load_prices(canon_sym, settings)
    if (df is None or df.empty):
        if not canon_sym.endswith(".NS"):
            ns_sym = canonical_symbol(f"{raw_sym}.NS")
            df = load_prices(ns_sym, settings)
            if df is not None and not df.empty:
                canon_sym = ns_sym
        if (df is None or df.empty) and not canon_sym.endswith(".BO"):
            bo_sym = canonical_symbol(f"{raw_sym}.BO")
            df = load_prices(bo_sym, settings)
            if df is not None and not df.empty:
                canon_sym = bo_sym

    live_q = fetch_live_quote(canon_sym, settings) or {}
    cur_p = float(live_q.get("current_price") or 0.0)

    if df is not None and not df.empty and "close" in df.columns:
        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
        if not closes.empty and cur_p <= 0:
            cur_p = float(closes.iloc[-1])
        recent_df = df.tail(lookback_days)
    else:
        recent_df = pd.DataFrame()

    # 2. Compute Volume Profile (TPO)
    if not recent_df.empty:
        poc, vah, val, lvn_ratio, profile_bins = _calculate_volume_profile_detailed(recent_df, num_bins=30)
    else:
        poc, vah, val, lvn_ratio, profile_bins = cur_p, cur_p, cur_p, 1.0, []

    # 3. Compute Cumulative Volume Delta (CVD) & Delta Imbalance
    buy_vol = 0.0
    sell_vol = 0.0
    cvd_bars: list[dict[str, Any]] = []
    cum_delta = 0.0

    if not recent_df.empty and "close" in recent_df.columns and "volume" in recent_df.columns:
        for idx, row in recent_df.iterrows():
            c = float(row.get("close") or 0.0)
            o = float(row.get("open") or c)
            h = float(row.get("high") or max(c, o))
            l = float(row.get("low") or min(c, o))
            v = float(row.get("volume") or 0.0)

            rng = max(0.01, h - l)
            # Intra-bar buy/sell partition approximation (Lee-Ready / Candle Body Ratio)
            buy_ratio = max(0.05, min(0.95, (c - l) / rng))
            bar_buy = v * buy_ratio
            bar_sell = v * (1.0 - buy_ratio)
            bar_delta = bar_buy - bar_sell
            cum_delta += bar_delta
            buy_vol += bar_buy
            sell_vol += bar_sell

            cvd_bars.append({
                "date": str(idx)[:10],
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": int(v),
                "buy_volume": int(bar_buy),
                "sell_volume": int(bar_sell),
                "delta": int(bar_delta),
                "cumulative_delta": int(cum_delta),
                "cvd": int(cum_delta),
            })

    total_vol = buy_vol + sell_vol
    buy_pct = round((buy_vol / max(1.0, total_vol)) * 100, 1)
    sell_pct = round((sell_vol / max(1.0, total_vol)) * 100, 1)
    delta_bias = "ACCUMULATION" if buy_pct >= 55.0 else ("DISTRIBUTION" if sell_pct >= 55.0 else "NEUTRAL")

    # 4. Compute Footprint Matrix for Recent 20 Bars (Synchronized 1:1 with CVD lookback window)
    footprint_matrix: list[dict[str, Any]] = []
    lookback_footprint = cvd_bars[-20:] if len(cvd_bars) >= 20 else cvd_bars
    for b in lookback_footprint:
        b_h = b.get("high", b.get("close", 0.0))
        b_l = b.get("low", b.get("close", 0.0))
        b_v = b.get("volume", 0)
        b_bv = b.get("buy_volume", 0)
        b_sv = b.get("sell_volume", 0)

        levels_count = 5
        step = max(0.05, (b_h - b_l) / max(1, levels_count - 1)) if b_h > b_l else 1.0
        clusters = []
        for i in range(levels_count):
            lvl_p = round(b_l + i * step, 2)
            ratio = max(0.1, min(0.9, (i + 1) / levels_count))
            lvl_bv = int(b_bv * (ratio / levels_count * 2.0))
            lvl_sv = int(b_sv * ((1.0 - ratio) / levels_count * 2.0))
            clusters.append({
                "price": lvl_p,
                "buy_vol": lvl_bv,
                "sell_vol": lvl_sv,
                "buy": lvl_bv,
                "sell": lvl_sv,
                "delta": lvl_bv - lvl_sv,
                "imbalance": "BUY_IMBALANCE" if lvl_bv > lvl_sv * 2.5 else ("SELL_IMBALANCE" if lvl_sv > lvl_bv * 2.5 else "BALANCED"),
            })
        footprint_matrix.append({
            "date": b["date"],
            "open": b.get("open", b["close"]),
            "high": b_h,
            "low": b_l,
            "close": b["close"],
            "volume": b_v,
            "buy_volume": b_bv,
            "sell_volume": b_sv,
            "delta": b["delta"],
            "cvd": b.get("cvd", 0),
            "clusters": clusters,
        })

    # 5. Derivative / Technical Walls & Order Book Spread
    buy_wall = val
    sell_wall = vah
    max_pain = poc
    option_strikes: list[dict[str, Any]] = []
    call_wall_oi = 0.0
    put_wall_oi = 0.0

    # Integrate real Option Chain data using analyze_option_chain
    try:
        from earnings_engine.data.universe import is_fno_eligible
        from earnings_engine.data.option_chain import analyze_option_chain
        if is_fno_eligible(canon_sym):
            opt = analyze_option_chain(canon_sym, spot_price=cur_p, settings=settings)
            if opt and isinstance(opt, dict):
                sell_wall = float(opt.get("resistance_strike") or vah)
                buy_wall = float(opt.get("support_strike") or val)
                max_pain = float(opt.get("max_pain_strike") or poc)
                if opt.get("strikes"):
                    option_strikes = opt.get("strikes")[:20]
                for strike in option_strikes:
                    if abs(strike.get("strike", 0) - sell_wall) < 1.0:
                        call_wall_oi = float(strike.get("ce_oi", 0))
                    if abs(strike.get("strike", 0) - buy_wall) < 1.0:
                        put_wall_oi = float(strike.get("pe_oi", 0))
    except Exception:
        pass

    # Build Two-Sided Unified Price Ladder (Expanded for Sell-Side Depth)
    order_book_spread: list[dict[str, Any]] = []
    if cur_p > 0:
        p_min = float(recent_df["low"].min()) if not recent_df.empty and "low" in recent_df.columns else (cur_p * 0.92)
        p_max = float(recent_df["high"].max()) if not recent_df.empty and "high" in recent_df.columns else (cur_p * 1.08)

        # Extend bounds symmetrically for sell-side depth (asks above spot)
        upper_price = max(p_max, cur_p * 1.08, (sell_wall * 1.02) if sell_wall > cur_p else cur_p * 1.08)
        lower_price = min(p_min, cur_p * 0.92, (buy_wall * 0.98) if buy_wall > 0 and buy_wall < cur_p else cur_p * 0.92)

        num_bins = 30
        upper_bins = int(round(num_bins * ((upper_price - cur_p) / max(1.0, upper_price - lower_price))))
        lower_bins = num_bins - upper_bins
        upper_bins = max(12, min(18, upper_bins))
        lower_bins = num_bins - upper_bins

        upper_grid = np.linspace(cur_p, upper_price, upper_bins + 1) if upper_bins > 0 else []
        lower_grid = np.linspace(lower_price, cur_p, lower_bins + 1) if lower_bins > 0 else []

        # Helper to map historical bin volume near a target price
        hist_bins_map = {b["price"]: b for b in profile_bins} if profile_bins else {}
        def find_nearest_hist_bin(target_price):
            if not hist_bins_map:
                return None
            return min(hist_bins_map.values(), key=lambda b: abs(b["price"] - target_price))

        max_vol = max(1, max(b["volume"] for b in profile_bins)) if profile_bins else 1

        def make_spread_level(price, side_type, hist_bin=None):
            vol = hist_bin["volume"] if hist_bin else int(1000 + 2000 * max(0, 1 - abs(price - cur_p) / (cur_p * 0.05)))
            bv = hist_bin["buy_volume"] if hist_bin else int(vol * max(0.05, min(0.95, (price - (price - 0.1)) / max(0.01, 0.2)))) if side_type == "SUPPORT_BID" else int(vol * 0.35)
            sv = hist_bin["sell_volume"] if hist_bin else int(vol - bv)
            return {
                "price": round(price, 2),
                "type": side_type,
                "volume": vol,
                "buy_volume": bv,
                "sell_volume": sv,
                "spread_depth_pct": round((vol / max_vol) * 100, 1),
                "is_poc": bool(hist_bin["is_poc"]) if hist_bin else bool(abs(price - poc) < (upper_grid[1] - upper_grid[0] if len(upper_grid) > 1 else 1.0)),
                "is_vah": bool(hist_bin["is_vah"]) if hist_bin else bool(abs(price - vah) < (upper_grid[1] - upper_grid[0] if len(upper_grid) > 1 else 1.0)),
                "is_val": bool(hist_bin["is_val"]) if hist_bin else bool(abs(price - val) < (lower_grid[1] - lower_grid[0] if len(lower_grid) > 1 else 1.0)),
                "is_buy_wall": bool(abs(price - buy_wall) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0)),
                "is_sell_wall": bool(abs(price - sell_wall) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0)),
                "is_call_wall": bool(abs(price - sell_wall) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0) and call_wall_oi > 0),
                "is_put_wall": bool(abs(price - buy_wall) < ((lower_grid[1] - lower_grid[0]) if len(lower_grid) > 1 else 5.0) and put_wall_oi > 0),
                "is_max_pain": bool(abs(price - max_pain) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0)),
            }

        # Build Ask / Sell Side Ladder (Above Spot)
        for price in reversed(upper_grid[1:]):
            order_book_spread.append(make_spread_level(price, "RESISTANCE_ASK", find_nearest_hist_bin(price)))

        # Build Bid / Buy Side Ladder (Below Spot)
        for price in lower_grid[:-1]:
            order_book_spread.append(make_spread_level(price, "SUPPORT_BID", find_nearest_hist_bin(price)))

    # Fallback if no levels generated (e.g. zero-cur_p guard path)
    if not order_book_spread and cur_p > 0:
        order_book_spread.append({
            "price": round(cur_p, 2),
            "type": "SPOT",
            "volume": 1,
            "buy_volume": 1,
            "sell_volume": 0,
            "spread_depth_pct": 100.0,
            "is_poc": True,
            "is_vah": False,
            "is_val": False,
            "is_buy_wall": False,
            "is_sell_wall": False,
            "is_call_wall": False,
            "is_put_wall": False,
            "is_max_pain": False,
        })

    gocharting_url = f"https://gocharting.com/terminal?ticker={bse_sym}"
    tv_url = f"https://www.tradingview.com/chart/?symbol={bse_sym}"

    return {
        "ticker": ticker,
        "bse_symbol": bse_sym,
        "nse_symbol": nse_sym,
        "current_price": round(cur_p, 2),
        "asof_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "gocharting_url": gocharting_url,
        "tradingview_url": tv_url,
        "volume_profile": {
            "poc": round(poc, 2),
            "vah": round(vah, 2),
            "val": round(val, 2),
            "lvn_resistance_ratio": round(lvn_ratio, 2),
            "value_area_range_pct": round(((vah - val) / max(0.01, cur_p)) * 100, 2) if cur_p > 0 else 0.0,
            "price_vs_value_area": "ABOVE_VAH" if cur_p > vah else ("BELOW_VAL" if cur_p < val else "INSIDE_VALUE_AREA"),
            "profile_bins": profile_bins,
        },
        "order_flow": {
            "buy_volume_pct": buy_pct,
            "sell_volume_pct": sell_pct,
            "net_cumulative_delta": int(cum_delta),
            "delta_regime": delta_bias,
            "cvd_history_bars": cvd_bars[-20:],
        },
        "cvd_history_bars": cvd_bars[-20:],
        "order_book_walls": {
            "buy_wall_floor": round(buy_wall, 2),
            "sell_wall_ceiling": round(sell_wall, 2),
            "max_pain": round(max_pain, 2),
        },
        "order_book_spread": order_book_spread,
        "footprint_matrix": footprint_matrix,
        "option_strikes_sample": option_strikes,
        "verdict_summary": f"GoCharting Order Flow: {delta_bias} flow regime. POC at ₹{poc:,.2f} with VAH ceiling at ₹{vah:,.2f} and VAL floor at ₹{val:,.2f}."
    }
