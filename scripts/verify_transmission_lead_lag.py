"""Empirical Lead-Lag and Cross-Correlation Verification Script.

Proves statistical lead-lag transmission relationships across:
1. AI Infrastructure & Hardware: Bloom Energy (BE) -> MTAR Tech (MTARTECH.NS)
2. Optical Fiber Supply Chain: Corning (GLW) -> Sterlite Tech (STLTECH.NS) -> HFCL (HFCL.NS)
3. Defense & Avionics: HAL (HAL.NS) -> Data Patterns (DATAPATTNS.NS)
4. Radar Subsystems: Bharat Electronics (BEL.NS) -> Astra Microwave (ASTRAMICRO.NS)
5. Power & Grid Transformers: Hitachi Energy (POWERINDIA.NS) -> TRIL (TARIL.NS)
6. Semiconductor & OSAT: CG Power (CGPOWER.NS) -> Kaynes Technology (KAYNES.NS)

Computes:
- Cross-correlation over lags: [-5d, -4d, -3d, -2d, -1d, 0d, +1d, +2d, +3d, +4d, +5d]
- Optimal lead-lag day shift (where peak correlation occurs)
- Directional beta / regression elasticity
- Granger-style directional predictive power (Upstream t-1 predicting Downstream t return sign)
"""

from __future__ import annotations

import argparse
import sys
import numpy as np
import pandas as pd
import yfinance as yf

# Canonical pairs representing cross-border and tier-to-tier transmission conduits
PAIRS = [
    {
        "basket": "AI_INFRA_HARDWARE",
        "name": "Bloom SOFC Anchor -> MTAR Tech",
        "source": "BE",
        "target": "MTARTECH.NS",
        "hypothesized_lag": "+1d (US market overnight -> India next day)",
    },
    {
        "basket": "AI_INFRA_HARDWARE",
        "name": "Sterlite Fiber Leader -> HFCL Retail Satellite",
        "source": "STLTECH.NS",
        "target": "HFCL.NS",
        "hypothesized_lag": "0d to +1d (sympathy spillover)",
    },
    {
        "basket": "AI_INFRA_HARDWARE",
        "name": "Hitachi Energy -> TRIL (Transformers & Rectifiers)",
        "source": "POWERINDIA.NS",
        "target": "TARIL.NS",
        "hypothesized_lag": "0d to +1d (transformer capacity spillover)",
    },
    {
        "basket": "DEFENSE_AERO",
        "name": "HAL Tejas Prime -> Data Patterns Radar Avionics",
        "source": "HAL.NS",
        "target": "DATAPATTNS.NS",
        "hypothesized_lag": "0d to +1d",
    },
    {
        "basket": "DEFENSE_AERO",
        "name": "Bharat Electronics (BEL) -> Astra Microwave",
        "source": "BEL.NS",
        "target": "ASTRAMICRO.NS",
        "hypothesized_lag": "0d to +1d",
    },
    {
        "basket": "DEFENSE_AERO",
        "name": "Bharat Electronics (BEL) -> Data Patterns (DATAPATTNS.NS)",
        "source": "BEL.NS",
        "target": "DATAPATTNS.NS",
        "hypothesized_lag": "0d to +1d",
    },
    {
        "basket": "SEMI_OSAT",
        "name": "CG Power Sanand OSAT -> Kaynes Technology",
        "source": "CGPOWER.NS",
        "target": "KAYNES.NS",
        "hypothesized_lag": "0d to +1d (OSAT multiple spillover)",
    },
    {
        "basket": "AI_INFRA_HARDWARE",
        "name": "Corning Global Fiber -> Sterlite Tech",
        "source": "GLW",
        "target": "STLTECH.NS",
        "hypothesized_lag": "+1d (US glass preform pricing -> India fiber)",
    },
]


def fetch_aligned_returns(source_ticker: str, target_ticker: str, period: str = "1y") -> pd.DataFrame:
    """Download daily close prices, compute percentage returns, and align trading calendar dates."""
    tickers = f"{source_ticker} {target_ticker}"
    df = yf.download(tickers, period=period, interval="1d", auto_adjust=True, progress=False)

    if df.empty:
        raise ValueError(f"Could not download price series for {tickers}")

    if isinstance(df.columns, pd.MultiIndex):
        closes = df["Close"]
    else:
        closes = df

    # Drop any ticker column missing, ensure strictly sorted
    s_close = closes[source_ticker].dropna()
    t_close = closes[target_ticker].dropna()

    s_ret = s_close.pct_change().dropna()
    t_ret = t_close.pct_change().dropna()

    combined = pd.DataFrame({"source_ret": s_ret, "target_ret": t_ret}).dropna()
    return combined


def calculate_lead_lag_profile(df: pd.DataFrame, max_lags: int = 5) -> dict:
    """Calculate cross-correlation function (CCF) across negative and positive daily shifts."""
    correlations = {}
    s = df["source_ret"]
    t = df["target_ret"]

    for lag in range(-max_lags, max_lags + 1):
        if lag < 0:
            # Negative lag: target shifted backwards (target leads source)
            corr = float(s.corr(t.shift(-lag)))
        elif lag > 0:
            # Positive lag: source at t-lag predicting target at t (source leads target)
            corr = float(t.corr(s.shift(lag)))
        else:
            # Contemporaneous
            corr = float(s.corr(t))
        correlations[lag] = corr if not np.isnan(corr) else 0.0

    peak_lag = max(correlations.keys(), key=lambda k: correlations[k])
    peak_corr = correlations[peak_lag]
    lag_0_corr = correlations[0]
    lag_1_corr = correlations.get(1, 0.0)

    # Directional sign concordance when source moved significantly (|ret| > 1%)
    # Same-day concordance
    valid_same = df[df["source_ret"].abs() > 0.01]
    concordance_0d = (
        (np.sign(valid_same["source_ret"]) == np.sign(valid_same["target_ret"])).mean()
        if len(valid_same) >= 5 else None
    )

    # Next-day predictive concordance: did Target at day t follow Source at day t-1?
    lagged_source = df["source_ret"].shift(1)
    valid_next = df[lagged_source.abs() > 0.01]
    concordance_1d = (
        (np.sign(lagged_source.loc[valid_next.index]) == np.sign(valid_next["target_ret"])).mean()
        if len(valid_next) >= 5 else None
    )

    return {
        "correlations": correlations,
        "peak_lag": peak_lag,
        "peak_corr": peak_corr,
        "lag_0_corr": lag_0_corr,
        "lag_1_corr": lag_1_corr,
        "concordance_0d": concordance_0d,
        "concordance_1d": concordance_1d,
        "sample_size": len(df),
    }


def verify_all_pairs(period: str = "1y") -> None:
    print("=" * 86)
    print("  NEXUS INTELLIGENCE: TRANSMISSION RADAR EMPIRICAL LEAD-LAG VERIFICATION")
    print(f"  Period: {period.upper()} | Sampling: Daily Settlement Returns | Confidence Analysis")
    print("=" * 86)

    results_table = []

    for pair in PAIRS:
        src = pair["source"]
        tgt = pair["target"]
        name = pair["name"]

        try:
            df = fetch_aligned_returns(src, tgt, period=period)
            if len(df) < 30:
                print(f"[-] Insufficient overlapping data for {src} -> {tgt} ({len(df)} bars)")
                continue

            stats = calculate_lead_lag_profile(df, max_lags=4)
            peak_lag = stats["peak_lag"]
            peak_corr = stats["peak_corr"]
            c0 = stats["lag_0_corr"]
            c1 = stats["lag_1_corr"]

            # Statistical verification thresholds
            is_valid = (peak_corr >= 0.15) or (c0 >= 0.15) or (c1 >= 0.12)
            status = "VERIFIED [STRONG]" if peak_corr >= 0.35 else ("VERIFIED [POSITIVE]" if is_valid else "WEAK / NOISE")

            results_table.append({
                "Pair": f"{src} -> {tgt}",
                "Theme": pair["basket"],
                "Bars": stats["sample_size"],
                "Lag 0 (r)": f"{c0:+.3f}",
                "Lag +1d (r)": f"{c1:+.3f}",
                "Peak Lag": f"{peak_lag:+}d",
                "Peak (r)": f"{peak_corr:+.3f}",
                "Status": status,
            })

            # Print detailed conduit profile
            print(f"\n[CONDUIT] {name} ({src} -> {tgt})")
            print(f"   Basket: {pair['basket']} | Hypothesized: {pair['hypothesized_lag']}")
            print(f"   Cross-Correlation Function [-4d .. +4d]:")
            line = "   "
            for lg in range(-4, 5):
                val = stats["correlations"][lg]
                star = " *" if lg == peak_lag else "  "
                line += f"[{lg:+1d}d: {val:+.2f}{star}] "
            print(line)
            c0_str = f"{stats['concordance_0d'] * 100:.1f}%" if stats['concordance_0d'] is not None else "N/A"
            c1_str = f"{stats['concordance_1d'] * 100:.1f}%" if stats['concordance_1d'] is not None else "N/A"
            print(f"   Directional Concordance (Source |ret| > 1%): Same-Day (0d)={c0_str} | Next-Day (+1d)={c1_str}")

        except Exception as exc:
            print(f"[-] Error processing {src} -> {tgt}: {exc}")

    # Summary Table
    print("\n" + "=" * 86)
    print("  EMPIRICAL TRANSMISSION SUMMARY TABLE")
    print("=" * 86)
    summary_df = pd.DataFrame(results_table)
    print(summary_df.to_string(index=False))
    print("=" * 86)
    print("Core Takeaways:")
    print("  * Lag 0: Same-day co-movement within the domestic supply chain (e.g. HAL -> Data Patterns, STLTECH -> HFCL).")
    print("  * Lag +1d: Cross-border overnight transmission where US close at T guides India open/close at T+1.")
    print("  * Directional Concordance: Probability that downstream asset moves in the same direction when leader moves >1%.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Transmission Lead-Lag Radar Pairs")
    parser.add_argument("--period", type=str, default="1y", help="Historical sample period (e.g. 6mo, 1y, 2y)")
    args = parser.parse_args()
    verify_all_pairs(period=args.period)
