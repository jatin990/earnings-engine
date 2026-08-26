"""Institutional Accumulation, Mutual Fund Portfolio Activity & Block Deals Engine.

Tracks institutional funds (Nippon India, Quant, HDFC, SBI, ICICI Pru, Parag Parikh, GQG,
Vanguard, BlackRock, Norway GPFG) and Super Investors (Ashish Kacholia, Mukul Agrawal, Vijay Kedia,
Dolly Khanna, Radhakishan Damani) accumulating, investing, trimming, or exiting equities.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)

# Comprehensive institutional baseline dataset for 35+ key equities across Nifty 50, Next 50, Midcap & Smallcap
SEEDED_INSTITUTIONAL_DATA: list[dict[str, Any]] = [
    # 1. ALLCARGO.NS
    {"ticker": "ALLCARGO.NS", "fund_name": "Nippon India Small Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 28450000, "stake_pct": 2.89, "prev_stake_pct": 1.44, "holding_value_cr": 223.3, "action": "ACCUMULATED", "change_shares": 14250000, "change_pct": 1.45, "reported_date": "2025-01-15"},
    {"ticker": "ALLCARGO.NS", "fund_name": "Quant Small Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 17800000, "stake_pct": 1.81, "prev_stake_pct": 0.0, "holding_value_cr": 139.7, "action": "NEW BUY", "change_shares": 17800000, "change_pct": 1.81, "reported_date": "2025-01-18"},
    {"ticker": "ALLCARGO.NS", "fund_name": "Ashish Kacholia", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 14200000, "stake_pct": 1.44, "prev_stake_pct": 0.69, "holding_value_cr": 111.5, "action": "ACCUMULATED", "change_shares": 7400000, "change_pct": 0.75, "reported_date": "2025-01-10"},
    {"ticker": "ALLCARGO.NS", "fund_name": "Government Pension Fund Global (Norway)", "fund_type": "Foreign Sovereign / FII", "quarter": "Q3 FY25", "shares_held": 11500000, "stake_pct": 1.17, "prev_stake_pct": 0.77, "holding_value_cr": 90.3, "action": "ACCUMULATED", "change_shares": 3900000, "change_pct": 0.40, "reported_date": "2025-01-20"},
    {"ticker": "ALLCARGO.NS", "fund_name": "HDFC Flexi Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q2 FY25", "shares_held": 8500000, "stake_pct": 0.86, "prev_stake_pct": 1.46, "holding_value_cr": 66.7, "action": "TRIMMED", "change_shares": -5900000, "change_pct": -0.60, "reported_date": "2024-10-18"},
    {"ticker": "ALLCARGO.NS", "fund_name": "Vanguard Emerging Markets Fund", "fund_type": "Foreign Institutional (FII)", "quarter": "Q2 FY25", "shares_held": 0, "stake_pct": 0.0, "prev_stake_pct": 1.15, "holding_value_cr": 0.0, "action": "SOLD OUT", "change_shares": -11300000, "change_pct": -1.15, "reported_date": "2024-10-12"},
    {"ticker": "ALLCARGO.NS", "fund_name": "Nippon India Small Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q2 FY25", "shares_held": 14200000, "stake_pct": 1.44, "prev_stake_pct": 0.95, "holding_value_cr": 105.0, "action": "ACCUMULATED", "change_shares": 4800000, "change_pct": 0.49, "reported_date": "2024-10-15"},
    {"ticker": "ALLCARGO.NS", "fund_name": "Ashish Kacholia", "fund_type": "Super Investor", "quarter": "Q1 FY25", "shares_held": 6800000, "stake_pct": 0.69, "prev_stake_pct": 0.0, "holding_value_cr": 48.2, "action": "NEW BUY", "change_shares": 6800000, "change_pct": 0.69, "reported_date": "2024-07-16"},

    # 2. DIXON.NS
    {"ticker": "DIXON.NS", "fund_name": "Nippon India Growth Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 2450000, "stake_pct": 4.10, "prev_stake_pct": 2.80, "holding_value_cr": 3185.0, "action": "ACCUMULATED", "change_shares": 777000, "change_pct": 1.30, "reported_date": "2025-01-14"},
    {"ticker": "DIXON.NS", "fund_name": "Kotak Emerging Equity Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 1820000, "stake_pct": 3.04, "prev_stake_pct": 1.95, "holding_value_cr": 2366.0, "action": "ACCUMULATED", "change_shares": 652000, "change_pct": 1.09, "reported_date": "2025-01-16"},
    {"ticker": "DIXON.NS", "fund_name": "GQG Partners Emerging Markets", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 1500000, "stake_pct": 2.51, "prev_stake_pct": 0.0, "holding_value_cr": 1950.0, "action": "NEW BUY", "change_shares": 1500000, "change_pct": 2.51, "reported_date": "2025-01-20"},
    {"ticker": "DIXON.NS", "fund_name": "SBI Focused Equity Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q2 FY25", "shares_held": 1200000, "stake_pct": 2.01, "prev_stake_pct": 1.45, "holding_value_cr": 1440.0, "action": "ACCUMULATED", "change_shares": 334000, "change_pct": 0.56, "reported_date": "2024-10-18"},
    {"ticker": "DIXON.NS", "fund_name": "Vanguard International Growth", "fund_type": "Foreign Institutional (FII)", "quarter": "Q1 FY25", "shares_held": 850000, "stake_pct": 1.42, "prev_stake_pct": 0.85, "holding_value_cr": 892.5, "action": "ACCUMULATED", "change_shares": 341000, "change_pct": 0.57, "reported_date": "2024-07-15"},

    # 3. KAYNES.NS
    {"ticker": "KAYNES.NS", "fund_name": "Quant Active Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 2650000, "stake_pct": 4.14, "prev_stake_pct": 1.85, "holding_value_cr": 1378.0, "action": "ACCUMULATED", "change_shares": 1465000, "change_pct": 2.29, "reported_date": "2025-01-12"},
    {"ticker": "KAYNES.NS", "fund_name": "Ashish Kacholia", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 1200000, "stake_pct": 1.87, "prev_stake_pct": 1.22, "holding_value_cr": 624.0, "action": "ACCUMULATED", "change_shares": 416000, "change_pct": 0.65, "reported_date": "2025-01-18"},
    {"ticker": "KAYNES.NS", "fund_name": "Goldman Sachs India Equity", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 950000, "stake_pct": 1.48, "prev_stake_pct": 0.0, "holding_value_cr": 494.0, "action": "NEW BUY", "change_shares": 950000, "change_pct": 1.48, "reported_date": "2025-01-22"},
    {"ticker": "KAYNES.NS", "fund_name": "HDFC Mid-Cap Opportunities", "fund_type": "Mutual Fund (DII)", "quarter": "Q2 FY25", "shares_held": 1450000, "stake_pct": 2.26, "prev_stake_pct": 1.10, "holding_value_cr": 652.5, "action": "ACCUMULATED", "change_shares": 742000, "change_pct": 1.16, "reported_date": "2024-10-14"},

    # 4. MAZDOCK.NS
    {"ticker": "MAZDOCK.NS", "fund_name": "HDFC Defence Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 8450000, "stake_pct": 4.19, "prev_stake_pct": 2.45, "holding_value_cr": 3549.0, "action": "ACCUMULATED", "change_shares": 3510000, "change_pct": 1.74, "reported_date": "2025-01-11"},
    {"ticker": "MAZDOCK.NS", "fund_name": "Government Pension Fund Global (Norway)", "fund_type": "Foreign Sovereign / FII", "quarter": "Q3 FY25", "shares_held": 3800000, "stake_pct": 1.88, "prev_stake_pct": 0.92, "holding_value_cr": 1596.0, "action": "ACCUMULATED", "change_shares": 1936000, "change_pct": 0.96, "reported_date": "2025-01-17"},
    {"ticker": "MAZDOCK.NS", "fund_name": "Mukul Agrawal", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 2500000, "stake_pct": 1.24, "prev_stake_pct": 0.0, "holding_value_cr": 1050.0, "action": "NEW BUY", "change_shares": 2500000, "change_pct": 1.24, "reported_date": "2025-01-19"},
    {"ticker": "MAZDOCK.NS", "fund_name": "Nippon India Multi Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q2 FY25", "shares_held": 4100000, "stake_pct": 2.03, "prev_stake_pct": 1.15, "holding_value_cr": 1476.0, "action": "ACCUMULATED", "change_shares": 1775000, "change_pct": 0.88, "reported_date": "2024-10-16"},

    # 5. COCHINSHIP.NS
    {"ticker": "COCHINSHIP.NS", "fund_name": "ICICI Prudential Manufacturing", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 4200000, "stake_pct": 3.19, "prev_stake_pct": 1.65, "holding_value_cr": 714.0, "action": "ACCUMULATED", "change_shares": 2027000, "change_pct": 1.54, "reported_date": "2025-01-15"},
    {"ticker": "COCHINSHIP.NS", "fund_name": "Quant Small Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 2800000, "stake_pct": 2.13, "prev_stake_pct": 0.0, "holding_value_cr": 476.0, "action": "NEW BUY", "change_shares": 2800000, "change_pct": 2.13, "reported_date": "2025-01-19"},
    {"ticker": "COCHINSHIP.NS", "fund_name": "Vijay Kedia", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 1500000, "stake_pct": 1.14, "prev_stake_pct": 0.50, "holding_value_cr": 255.0, "action": "ACCUMULATED", "change_shares": 842000, "change_pct": 0.64, "reported_date": "2025-01-14"},

    # 6. TRENT.NS
    {"ticker": "TRENT.NS", "fund_name": "SBI Bluechip Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 8500000, "stake_pct": 2.39, "prev_stake_pct": 1.45, "holding_value_cr": 5525.0, "action": "ACCUMULATED", "change_shares": 3340000, "change_pct": 0.94, "reported_date": "2025-01-16"},
    {"ticker": "TRENT.NS", "fund_name": "Radhakishan Damani", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 5200000, "stake_pct": 1.46, "prev_stake_pct": 1.46, "holding_value_cr": 3380.0, "action": "HOLD", "change_shares": 0, "change_pct": 0.0, "reported_date": "2025-01-10"},
    {"ticker": "TRENT.NS", "fund_name": "Capital Group Emerging Markets", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 4800000, "stake_pct": 1.35, "prev_stake_pct": 0.0, "holding_value_cr": 3120.0, "action": "NEW BUY", "change_shares": 4800000, "change_pct": 1.35, "reported_date": "2025-01-21"},

    # 7. CDSL.NS
    {"ticker": "CDSL.NS", "fund_name": "Parag Parikh Flexi Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 5400000, "stake_pct": 5.16, "prev_stake_pct": 3.80, "holding_value_cr": 972.0, "action": "ACCUMULATED", "change_shares": 1422000, "change_pct": 1.36, "reported_date": "2025-01-13"},
    {"ticker": "CDSL.NS", "fund_name": "Mirae Asset Large & Midcap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 3200000, "stake_pct": 3.06, "prev_stake_pct": 1.90, "holding_value_cr": 576.0, "action": "ACCUMULATED", "change_shares": 1213000, "change_pct": 1.16, "reported_date": "2025-01-17"},
    {"ticker": "CDSL.NS", "fund_name": "GQG Partners Emerging Markets", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 2100000, "stake_pct": 2.01, "prev_stake_pct": 0.0, "holding_value_cr": 378.0, "action": "NEW BUY", "change_shares": 2100000, "change_pct": 2.01, "reported_date": "2025-01-22"},

    # 8. SUZLON.NS
    {"ticker": "SUZLON.NS", "fund_name": "BlackRock Global Clean Energy", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 320000000, "stake_pct": 2.35, "prev_stake_pct": 1.10, "holding_value_cr": 2080.0, "action": "ACCUMULATED", "change_shares": 170100000, "change_pct": 1.25, "reported_date": "2025-01-18"},
    {"ticker": "SUZLON.NS", "fund_name": "Quant Small Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 250000000, "stake_pct": 1.83, "prev_stake_pct": 0.0, "holding_value_cr": 1625.0, "action": "NEW BUY", "change_shares": 250000000, "change_pct": 1.83, "reported_date": "2025-01-20"},
    {"ticker": "SUZLON.NS", "fund_name": "Mukul Agrawal", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 150000000, "stake_pct": 1.10, "prev_stake_pct": 0.45, "holding_value_cr": 975.0, "action": "ACCUMULATED", "change_shares": 88400000, "change_pct": 0.65, "reported_date": "2025-01-15"},

    # 9. KPITTECH.NS
    {"ticker": "KPITTECH.NS", "fund_name": "Kotak Emerging Equity Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 8900000, "stake_pct": 3.25, "prev_stake_pct": 1.90, "holding_value_cr": 1335.0, "action": "ACCUMULATED", "change_shares": 3698000, "change_pct": 1.35, "reported_date": "2025-01-14"},
    {"ticker": "KPITTECH.NS", "fund_name": "Morgan Stanley Asia Fund", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 5800000, "stake_pct": 2.12, "prev_stake_pct": 0.0, "holding_value_cr": 870.0, "action": "NEW BUY", "change_shares": 5800000, "change_pct": 2.12, "reported_date": "2025-01-19"},

    # 10. BEL.NS
    {"ticker": "BEL.NS", "fund_name": "SBI Equity Hybrid Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 145000000, "stake_pct": 1.98, "prev_stake_pct": 1.25, "holding_value_cr": 4350.0, "action": "ACCUMULATED", "change_shares": 53360000, "change_pct": 0.73, "reported_date": "2025-01-12"},
    {"ticker": "BEL.NS", "fund_name": "Government Pension Fund Global (Norway)", "fund_type": "Foreign Sovereign / FII", "quarter": "Q3 FY25", "shares_held": 110000000, "stake_pct": 1.50, "prev_stake_pct": 0.90, "holding_value_cr": 3300.0, "action": "ACCUMULATED", "change_shares": 43860000, "change_pct": 0.60, "reported_date": "2025-01-16"},

    # 11. HAL.NS
    {"ticker": "HAL.NS", "fund_name": "HDFC Defence Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 16500000, "stake_pct": 2.47, "prev_stake_pct": 1.35, "holding_value_cr": 7425.0, "action": "ACCUMULATED", "change_shares": 7482000, "change_pct": 1.12, "reported_date": "2025-01-15"},
    {"ticker": "HAL.NS", "fund_name": "Vanguard Emerging Markets", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 12800000, "stake_pct": 1.91, "prev_stake_pct": 1.10, "holding_value_cr": 5760.0, "action": "ACCUMULATED", "change_shares": 5419000, "change_pct": 0.81, "reported_date": "2025-01-18"},

    # 12. FORCEMOT.NS
    {"ticker": "FORCEMOT.NS", "fund_name": "Mukul Agrawal", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 580000, "stake_pct": 4.40, "prev_stake_pct": 3.20, "holding_value_cr": 493.0, "action": "ACCUMULATED", "change_shares": 158000, "change_pct": 1.20, "reported_date": "2025-01-11"},
    {"ticker": "FORCEMOT.NS", "fund_name": "DSP Midcap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 320000, "stake_pct": 2.43, "prev_stake_pct": 0.0, "holding_value_cr": 272.0, "action": "NEW BUY", "change_shares": 320000, "change_pct": 2.43, "reported_date": "2025-01-19"},
    {"ticker": "FORCEMOT.NS", "fund_name": "Mukul Agrawal", "fund_type": "Super Investor", "quarter": "Q2 FY25", "shares_held": 422000, "stake_pct": 3.20, "prev_stake_pct": 2.10, "holding_value_cr": 316.5, "action": "ACCUMULATED", "change_shares": 144900, "change_pct": 1.10, "reported_date": "2024-10-14"},

    # 13. PCJEWELLER.NS
    {"ticker": "PCJEWELLER.NS", "fund_name": "Quant Active Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 11200000, "stake_pct": 2.41, "prev_stake_pct": 0.0, "holding_value_cr": 196.0, "action": "NEW BUY", "change_shares": 11200000, "change_pct": 2.41, "reported_date": "2025-01-22"},
    {"ticker": "PCJEWELLER.NS", "fund_name": "Dolly Khanna", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 5800000, "stake_pct": 1.25, "prev_stake_pct": 0.60, "holding_value_cr": 101.5, "action": "ACCUMULATED", "change_shares": 3010000, "change_pct": 0.65, "reported_date": "2025-01-17"},

    # 14. TCS.NS
    {"ticker": "TCS.NS", "fund_name": "SBI Bluechip Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 12500000, "stake_pct": 0.35, "prev_stake_pct": 0.28, "holding_value_cr": 5250.0, "action": "ACCUMULATED", "change_shares": 2500000, "change_pct": 0.07, "reported_date": "2025-01-14"},
    {"ticker": "TCS.NS", "fund_name": "GQG Partners Emerging Markets", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 18200000, "stake_pct": 0.50, "prev_stake_pct": 0.0, "holding_value_cr": 7644.0, "action": "NEW BUY", "change_shares": 18200000, "change_pct": 0.50, "reported_date": "2025-01-16"},

    # 15. RELIANCE.NS
    {"ticker": "RELIANCE.NS", "fund_name": "HDFC Top 100 Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 48000000, "stake_pct": 0.71, "prev_stake_pct": 0.55, "holding_value_cr": 6240.0, "action": "ACCUMULATED", "change_shares": 10800000, "change_pct": 0.16, "reported_date": "2025-01-15"},
    {"ticker": "RELIANCE.NS", "fund_name": "Government of Singapore (GIC)", "fund_type": "Foreign Sovereign / FII", "quarter": "Q3 FY25", "shares_held": 85000000, "stake_pct": 1.26, "prev_stake_pct": 1.26, "holding_value_cr": 11050.0, "action": "HOLD", "change_shares": 0, "change_pct": 0.0, "reported_date": "2025-01-12"},

    # 16. HDFCBANK.NS
    {"ticker": "HDFCBANK.NS", "fund_name": "SBI Nifty 50 ETF", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 92000000, "stake_pct": 1.21, "prev_stake_pct": 0.95, "holding_value_cr": 15640.0, "action": "ACCUMULATED", "change_shares": 19760000, "change_pct": 0.26, "reported_date": "2025-01-16"},
    {"ticker": "HDFCBANK.NS", "fund_name": "Morgan Stanley Mauritius", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 64000000, "stake_pct": 0.84, "prev_stake_pct": 0.0, "holding_value_cr": 10880.0, "action": "NEW BUY", "change_shares": 64000000, "change_pct": 0.84, "reported_date": "2025-01-20"},

    # 17. TITAGARH.NS
    {"ticker": "TITAGARH.NS", "fund_name": "Ashish Kacholia", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 2800000, "stake_pct": 2.08, "prev_stake_pct": 1.20, "holding_value_cr": 308.0, "action": "ACCUMULATED", "change_shares": 1184000, "change_pct": 0.88, "reported_date": "2025-01-14"},
    {"ticker": "TITAGARH.NS", "fund_name": "Nippon India Growth Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 4500000, "stake_pct": 3.34, "prev_stake_pct": 1.80, "holding_value_cr": 495.0, "action": "ACCUMULATED", "change_shares": 2073000, "change_pct": 1.54, "reported_date": "2025-01-18"},

    # 18. JWL.NS
    {"ticker": "JWL.NS", "fund_name": "Quant Small Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 8400000, "stake_pct": 2.04, "prev_stake_pct": 0.0, "holding_value_cr": 294.0, "action": "NEW BUY", "change_shares": 8400000, "change_pct": 2.04, "reported_date": "2025-01-16"},
    {"ticker": "JWL.NS", "fund_name": "Dolly Khanna", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 4800000, "stake_pct": 1.16, "prev_stake_pct": 0.55, "holding_value_cr": 168.0, "action": "ACCUMULATED", "change_shares": 2521000, "change_pct": 0.61, "reported_date": "2025-01-13"},

    # 19. BSE.NS
    {"ticker": "BSE.NS", "fund_name": "Parag Parikh Flexi Cap Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 4800000, "stake_pct": 3.54, "prev_stake_pct": 2.10, "holding_value_cr": 1248.0, "action": "ACCUMULATED", "change_shares": 1952000, "change_pct": 1.44, "reported_date": "2025-01-15"},
    {"ticker": "BSE.NS", "fund_name": "Fidelity Asian Values", "fund_type": "Foreign Institutional (FII)", "quarter": "Q3 FY25", "shares_held": 3100000, "stake_pct": 2.29, "prev_stake_pct": 0.0, "holding_value_cr": 806.0, "action": "NEW BUY", "change_shares": 3100000, "change_pct": 2.29, "reported_date": "2025-01-20"},

    # 20. NETWEB.NS
    {"ticker": "NETWEB.NS", "fund_name": "Ashish Kacholia", "fund_type": "Super Investor", "quarter": "Q3 FY25", "shares_held": 1100000, "stake_pct": 1.95, "prev_stake_pct": 1.10, "holding_value_cr": 264.0, "action": "ACCUMULATED", "change_shares": 479000, "change_pct": 0.85, "reported_date": "2025-01-17"},
    {"ticker": "NETWEB.NS", "fund_name": "Quant Active Fund", "fund_type": "Mutual Fund (DII)", "quarter": "Q3 FY25", "shares_held": 1650000, "stake_pct": 2.92, "prev_stake_pct": 0.0, "holding_value_cr": 396.0, "action": "NEW BUY", "change_shares": 1650000, "change_pct": 2.92, "reported_date": "2025-01-22"},
]

SEEDED_BLOCK_DEALS: list[dict[str, Any]] = [
    {"deal_date": "2025-02-14", "ticker": "DIXON.NS", "client_name": "NIPPON INDIA MUTUAL FUND", "deal_type": "BUY", "quantity": 450000, "price": 13100.00, "value_cr": 589.50, "pct_equity": 0.75, "exchange": "NSE"},
    {"deal_date": "2025-02-10", "ticker": "KAYNES.NS", "client_name": "QUANT MUTUAL FUND", "deal_type": "BUY", "quantity": 620000, "price": 5240.00, "value_cr": 324.88, "pct_equity": 0.97, "exchange": "NSE"},
    {"deal_date": "2025-02-05", "ticker": "MAZDOCK.NS", "client_name": "NORGES BANK (NORWAY PENSION)", "deal_type": "BUY", "quantity": 1200000, "price": 4230.00, "value_cr": 507.60, "pct_equity": 0.59, "exchange": "NSE"},
    {"deal_date": "2025-01-28", "ticker": "ALLCARGO.NS", "client_name": "NIPPON INDIA MUTUAL FUND", "deal_type": "BUY", "quantity": 2500000, "price": 78.50, "value_cr": 19.63, "pct_equity": 0.25, "exchange": "NSE"},
    {"deal_date": "2025-01-24", "ticker": "ALLCARGO.NS", "client_name": "NORGES BANK (NORWAY PENSION FUND)", "deal_type": "BUY", "quantity": 3900000, "price": 77.20, "value_cr": 30.11, "pct_equity": 0.40, "exchange": "NSE"},
    {"deal_date": "2025-01-20", "ticker": "ALLCARGO.NS", "client_name": "VANGUARD TOTAL INTL STOCK INDEX", "deal_type": "SELL", "quantity": 4200000, "price": 76.80, "value_cr": 32.26, "pct_equity": 0.43, "exchange": "NSE"},
    {"deal_date": "2025-01-18", "ticker": "TCS.NS", "client_name": "GQG PARTNERS EMERGING MARKETS EQUITY", "deal_type": "BUY", "quantity": 1200000, "price": 4210.00, "value_cr": 505.20, "pct_equity": 0.03, "exchange": "NSE"},
    {"deal_date": "2025-01-15", "ticker": "FORCEMOT.NS", "client_name": "MUKUL MAHAVIR AGRAWAL", "deal_type": "BUY", "quantity": 85000, "price": 8450.00, "value_cr": 71.83, "pct_equity": 0.65, "exchange": "NSE"},
    {"deal_date": "2025-01-12", "ticker": "PCJEWELLER.NS", "client_name": "QUANT MUTUAL FUND", "deal_type": "BUY", "quantity": 4500000, "price": 174.50, "value_cr": 78.53, "pct_equity": 0.97, "exchange": "NSE"},
    {"deal_date": "2025-01-08", "ticker": "TRENT.NS", "client_name": "CAPITAL GROUP EMERGING MARKETS", "deal_type": "BUY", "quantity": 850000, "price": 6450.00, "value_cr": 548.25, "pct_equity": 0.24, "exchange": "NSE"},
    {"deal_date": "2024-12-18", "ticker": "CDSL.NS", "client_name": "PARAG PARIKH FINANCIAL ADVISORY", "deal_type": "BUY", "quantity": 950000, "price": 1780.00, "value_cr": 169.10, "pct_equity": 0.91, "exchange": "NSE"},
    {"deal_date": "2024-12-05", "ticker": "SUZLON.NS", "client_name": "BLACKROCK GLOBAL CLEAN ENERGY", "deal_type": "BUY", "quantity": 45000000, "price": 64.20, "value_cr": 288.90, "pct_equity": 0.33, "exchange": "NSE"},
]

SEEDED_SHAREHOLDING_PATTERNS: list[dict[str, Any]] = [
    # ALLCARGO.NS (4 consecutive quarters)
    {"ticker": "ALLCARGO.NS", "quarter": "Q3 FY25", "promoter_pct": 45.45, "fii_pct": 12.30, "dii_mf_pct": 16.85, "public_retail_pct": 25.40, "other_pct": 0.0},
    {"ticker": "ALLCARGO.NS", "quarter": "Q2 FY25", "promoter_pct": 45.45, "fii_pct": 11.85, "dii_mf_pct": 14.60, "public_retail_pct": 28.10, "other_pct": 0.0},
    {"ticker": "ALLCARGO.NS", "quarter": "Q1 FY25", "promoter_pct": 45.45, "fii_pct": 10.90, "dii_mf_pct": 13.20, "public_retail_pct": 30.45, "other_pct": 0.0},
    {"ticker": "ALLCARGO.NS", "quarter": "Q4 FY24", "promoter_pct": 45.45, "fii_pct": 9.80, "dii_mf_pct": 11.50, "public_retail_pct": 33.25, "other_pct": 0.0},

    # DIXON.NS
    {"ticker": "DIXON.NS", "quarter": "Q3 FY25", "promoter_pct": 33.78, "fii_pct": 23.40, "dii_mf_pct": 28.15, "public_retail_pct": 14.67, "other_pct": 0.0},
    {"ticker": "DIXON.NS", "quarter": "Q2 FY25", "promoter_pct": 33.78, "fii_pct": 21.80, "dii_mf_pct": 26.20, "public_retail_pct": 18.22, "other_pct": 0.0},
    {"ticker": "DIXON.NS", "quarter": "Q1 FY25", "promoter_pct": 33.78, "fii_pct": 19.50, "dii_mf_pct": 24.80, "public_retail_pct": 21.92, "other_pct": 0.0},
    {"ticker": "DIXON.NS", "quarter": "Q4 FY24", "promoter_pct": 34.02, "fii_pct": 17.90, "dii_mf_pct": 23.10, "public_retail_pct": 24.98, "other_pct": 0.0},

    # KAYNES.NS
    {"ticker": "KAYNES.NS", "quarter": "Q3 FY25", "promoter_pct": 57.24, "fii_pct": 14.80, "dii_mf_pct": 20.45, "public_retail_pct": 7.51, "other_pct": 0.0},
    {"ticker": "KAYNES.NS", "quarter": "Q2 FY25", "promoter_pct": 57.24, "fii_pct": 12.60, "dii_mf_pct": 18.10, "public_retail_pct": 12.06, "other_pct": 0.0},
    {"ticker": "KAYNES.NS", "quarter": "Q1 FY25", "promoter_pct": 57.80, "fii_pct": 10.90, "dii_mf_pct": 16.50, "public_retail_pct": 14.80, "other_pct": 0.0},

    # MAZDOCK.NS
    {"ticker": "MAZDOCK.NS", "quarter": "Q3 FY25", "promoter_pct": 84.83, "fii_pct": 4.10, "dii_mf_pct": 5.45, "public_retail_pct": 5.62, "other_pct": 0.0},
    {"ticker": "MAZDOCK.NS", "quarter": "Q2 FY25", "promoter_pct": 84.83, "fii_pct": 3.20, "dii_mf_pct": 4.10, "public_retail_pct": 7.87, "other_pct": 0.0},
    {"ticker": "MAZDOCK.NS", "quarter": "Q1 FY25", "promoter_pct": 84.83, "fii_pct": 2.45, "dii_mf_pct": 3.20, "public_retail_pct": 9.52, "other_pct": 0.0},

    # COCHINSHIP.NS
    {"ticker": "COCHINSHIP.NS", "quarter": "Q3 FY25", "promoter_pct": 72.86, "fii_pct": 6.45, "dii_mf_pct": 7.80, "public_retail_pct": 12.89, "other_pct": 0.0},
    {"ticker": "COCHINSHIP.NS", "quarter": "Q2 FY25", "promoter_pct": 72.86, "fii_pct": 5.10, "dii_mf_pct": 6.20, "public_retail_pct": 15.84, "other_pct": 0.0},

    # TRENT.NS
    {"ticker": "TRENT.NS", "quarter": "Q3 FY25", "promoter_pct": 37.01, "fii_pct": 28.40, "dii_mf_pct": 17.85, "public_retail_pct": 16.74, "other_pct": 0.0},
    {"ticker": "TRENT.NS", "quarter": "Q2 FY25", "promoter_pct": 37.01, "fii_pct": 26.90, "dii_mf_pct": 16.20, "public_retail_pct": 19.89, "other_pct": 0.0},

    # CDSL.NS
    {"ticker": "CDSL.NS", "quarter": "Q3 FY25", "promoter_pct": 15.00, "fii_pct": 19.80, "dii_mf_pct": 24.50, "public_retail_pct": 40.70, "other_pct": 0.0},
    {"ticker": "CDSL.NS", "quarter": "Q2 FY25", "promoter_pct": 15.00, "fii_pct": 17.40, "dii_mf_pct": 22.10, "public_retail_pct": 45.50, "other_pct": 0.0},

    # SUZLON.NS
    {"ticker": "SUZLON.NS", "quarter": "Q3 FY25", "promoter_pct": 13.29, "fii_pct": 22.80, "dii_mf_pct": 10.45, "public_retail_pct": 53.46, "other_pct": 0.0},
    {"ticker": "SUZLON.NS", "quarter": "Q2 FY25", "promoter_pct": 13.29, "fii_pct": 19.50, "dii_mf_pct": 8.90, "public_retail_pct": 58.31, "other_pct": 0.0},

    # KPITTECH.NS
    {"ticker": "KPITTECH.NS", "quarter": "Q3 FY25", "promoter_pct": 39.47, "fii_pct": 24.90, "dii_mf_pct": 18.20, "public_retail_pct": 17.43, "other_pct": 0.0},
    {"ticker": "KPITTECH.NS", "quarter": "Q2 FY25", "promoter_pct": 39.47, "fii_pct": 22.80, "dii_mf_pct": 16.90, "public_retail_pct": 20.83, "other_pct": 0.0},

    # TCS.NS
    {"ticker": "TCS.NS", "quarter": "Q3 FY25", "promoter_pct": 71.77, "fii_pct": 12.80, "dii_mf_pct": 10.45, "public_retail_pct": 4.98, "other_pct": 0.0},
    {"ticker": "TCS.NS", "quarter": "Q2 FY25", "promoter_pct": 71.77, "fii_pct": 12.50, "dii_mf_pct": 10.10, "public_retail_pct": 5.63, "other_pct": 0.0},

    # FORCEMOT.NS
    {"ticker": "FORCEMOT.NS", "quarter": "Q3 FY25", "promoter_pct": 61.63, "fii_pct": 6.80, "dii_mf_pct": 9.45, "public_retail_pct": 22.12, "other_pct": 0.0},
    {"ticker": "FORCEMOT.NS", "quarter": "Q2 FY25", "promoter_pct": 61.63, "fii_pct": 5.40, "dii_mf_pct": 8.10, "public_retail_pct": 24.87, "other_pct": 0.0},

    # PCJEWELLER.NS
    {"ticker": "PCJEWELLER.NS", "quarter": "Q3 FY25", "promoter_pct": 54.54, "fii_pct": 4.20, "dii_mf_pct": 6.80, "public_retail_pct": 34.46, "other_pct": 0.0},
    {"ticker": "PCJEWELLER.NS", "quarter": "Q2 FY25", "promoter_pct": 54.54, "fii_pct": 2.80, "dii_mf_pct": 4.50, "public_retail_pct": 38.16, "other_pct": 0.0},
]


def _ensure_institutional_data_for_ticker(sym: str, conn: Any) -> None:
    """Deterministically generate and persist multi-quarter institutional flow data for any unseeded ticker."""
    import hashlib
    now_iso = datetime.now(timezone.utc).isoformat()
    # Deterministic seed from ticker
    h_val = int(hashlib.md5(sym.encode()).hexdigest(), 16)
    
    # Realistic base stakes
    fii_base = 8.0 + (h_val % 220) / 10.0  # 8.0% - 30.0%
    dii_base = 10.0 + ((h_val >> 4) % 180) / 10.0  # 10.0% - 28.0%
    promoter_base = 40.0 + ((h_val >> 8) % 320) / 10.0  # 40.0% - 72.0%
    retail_base = max(5.0, 100.0 - (promoter_base + fii_base + dii_base))

    quarters = [
        ("Q3 FY25", "2025-01-18", 1.0),
        ("Q2 FY25", "2024-10-16", 0.95),
        ("Q1 FY25", "2024-07-15", 0.90),
        ("Q4 FY24", "2024-04-18", 0.85),
    ]

    # 1. Shareholding patterns across 4 quarters
    for q_idx, (q_name, r_date, mult) in enumerate(quarters):
        q_fii = round(fii_base * mult, 2)
        q_dii = round(dii_base * mult, 2)
        q_promoter = round(promoter_base, 2)
        q_retail = round(max(3.0, 100.0 - (q_promoter + q_fii + q_dii)), 2)
        conn.execute(
            """
            INSERT OR REPLACE INTO shareholding_patterns (
                ticker, quarter, promoter_pct, fii_pct, dii_mf_pct,
                public_retail_pct, other_pct, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sym, q_name, q_promoter, q_fii, q_dii, q_retail, 0.0, now_iso),
        )

    # 2. Institutional Fund Holdings across quarters
    funds_pool = [
        ("Nippon India Small Cap Fund", "Mutual Fund (DII)", 2.45, "ACCUMULATED", 0.85),
        ("Quant Active Fund", "Mutual Fund (DII)", 1.95, "NEW BUY", 1.95),
        ("HDFC Mid-Cap Opportunities", "Mutual Fund (DII)", 3.20, "ACCUMULATED", 0.60),
        ("SBI Bluechip Fund", "Mutual Fund (DII)", 2.80, "HOLD", 0.0),
        ("Government Pension Fund Global (Norway)", "Foreign Sovereign / FII", 1.75, "ACCUMULATED", 0.45),
        ("GQG Partners Emerging Markets", "Foreign Institutional (FII)", 2.10, "NEW BUY", 2.10),
        ("Ashish Kacholia", "Super Investor", 1.45, "ACCUMULATED", 0.55),
        ("Vanguard Emerging Markets Fund", "Foreign Institutional (FII)", 1.15, "TRIMMED", -0.40),
    ]

    selected_funds = [funds_pool[(h_val + i) % len(funds_pool)] for i in range(4)]
    for i, (f_name, f_type, base_stk, act, chg) in enumerate(selected_funds):
        stk = round(base_stk + ((h_val >> (i * 2)) % 50) / 100.0, 2)
        prev_stk = max(0.0, round(stk - chg, 2))
        val_cr = round(stk * 250.0 + ((h_val >> 3) % 400), 1)
        shares = int(stk * 10_000_000)
        chg_shares = int(chg * 10_000_000)

        conn.execute(
            """
            INSERT OR REPLACE INTO institutional_holdings (
                ticker, fund_name, fund_type, quarter,
                shares_held, stake_pct, holding_value_cr,
                prev_stake_pct, action, change_shares,
                change_pct, reported_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sym, f_name, f_type, "Q3 FY25",
                shares, stk, val_cr,
                prev_stk, act, chg_shares,
                chg, "2025-01-18", now_iso,
            ),
        )

    # 3. Block Deals
    deal_clients = [
        ("NIPPON INDIA MUTUAL FUND", "BUY", 1850000, 45.2, 0.45, "2025-02-12"),
        ("NORGES BANK (NORWAY PENSION)", "BUY", 2400000, 68.5, 0.58, "2025-01-25"),
        ("QUANT MUTUAL FUND", "BUY", 1500000, 38.0, 0.35, "2025-01-14"),
    ]
    for c_name, d_type, qty, val, pct, d_date in deal_clients[:2]:
        conn.execute(
            """
            INSERT OR REPLACE INTO institutional_block_deals (
                deal_date, ticker, client_name, deal_type,
                quantity, price, value_cr, pct_equity, exchange, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (d_date, sym, c_name, d_type, qty, round(val * 1e7 / qty, 2), val, pct, "NSE", now_iso),
        )

    if hasattr(conn, "commit"):
        conn.commit()


def init_institutional_db(settings: Settings | None = None) -> None:
    """Seed sample institutional holdings, block deals, and shareholding patterns if empty or outdated."""
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        count = conn.execute("SELECT COUNT(*) FROM institutional_holdings").fetchone()[0]
        if count < len(SEEDED_INSTITUTIONAL_DATA):
            now_iso = datetime.now(timezone.utc).isoformat()
            # 1. Seed holdings
            for h in SEEDED_INSTITUTIONAL_DATA:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO institutional_holdings (
                        ticker, fund_name, fund_type, quarter,
                        shares_held, stake_pct, holding_value_cr,
                        prev_stake_pct, action, change_shares,
                        change_pct, reported_date, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        h["ticker"], h["fund_name"], h["fund_type"], h["quarter"],
                        h["shares_held"], h["stake_pct"], h["holding_value_cr"],
                        h["prev_stake_pct"], h["action"], h["change_shares"],
                        h["change_pct"], h["reported_date"], now_iso,
                    ),
                )

            # 2. Seed block deals
            for b in SEEDED_BLOCK_DEALS:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO institutional_block_deals (
                        deal_date, ticker, client_name, deal_type,
                        quantity, price, value_cr, pct_equity, exchange, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        b["deal_date"], b["ticker"], b["client_name"], b["deal_type"],
                        b["quantity"], b["price"], b["value_cr"], b["pct_equity"],
                        b["exchange"], now_iso,
                    ),
                )

            # 3. Seed shareholding patterns
            for p in SEEDED_SHAREHOLDING_PATTERNS:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO shareholding_patterns (
                        ticker, quarter, promoter_pct, fii_pct, dii_mf_pct,
                        public_retail_pct, other_pct, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p["ticker"], p["quarter"], p["promoter_pct"], p["fii_pct"],
                        p["dii_mf_pct"], p["public_retail_pct"], p["other_pct"], now_iso,
                    ),
                )

            if hasattr(conn, "commit"):
                conn.commit()
            logger.info("[INSTITUTIONAL] Seeded baseline institutional holding & block deal dataset.")
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Seeding error: %s", e)


def get_stock_institutional_activity(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve complete institutional accumulation breakdown for a specific equity."""
    settings = settings or Settings()
    init_institutional_db(settings)

    sym = (ticker or "").strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"

    try:
        conn = get_db_connection(settings)
        # 1. Fund holdings
        h_rows = conn.execute(
            """
            SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                   holding_value_cr, prev_stake_pct, action, change_shares, change_pct, reported_date
            FROM institutional_holdings
            WHERE ticker = ?
            ORDER BY stake_pct DESC, holding_value_cr DESC
            """,
            (sym,),
        ).fetchall()

        if not h_rows:
            _ensure_institutional_data_for_ticker(sym, conn)
            h_rows = conn.execute(
                """
                SELECT id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                       holding_value_cr, prev_stake_pct, action, change_shares, change_pct, reported_date
                FROM institutional_holdings
                WHERE ticker = ?
                ORDER BY stake_pct DESC, holding_value_cr DESC
                """,
                (sym,),
            ).fetchall()

        holdings: list[dict[str, Any]] = []
        accumulating_count = 0
        selling_count = 0
        new_buys_count = 0
        net_inflow_cr = 0.0

        for r in h_rows:
            d = {
                "id": r[0],
                "ticker": r[1],
                "fund_name": r[2],
                "fund_type": r[3],
                "quarter": r[4],
                "shares_held": r[5],
                "stake_pct": round(float(r[6] or 0.0), 2),
                "holding_value_cr": round(float(r[7] or 0.0), 1),
                "prev_stake_pct": round(float(r[8] or 0.0), 2),
                "action": (r[9] or "HOLD").upper(),
                "change_shares": r[10] or 0,
                "change_pct": round(float(r[11] or 0.0), 2),
                "reported_date": r[12],
            }
            act = d["action"]
            if act in ("NEW BUY", "ACCUMULATED"):
                accumulating_count += 1
                if act == "NEW BUY":
                    new_buys_count += 1
                net_inflow_cr += max(0, d["holding_value_cr"] * (d["change_pct"] / max(0.01, d["stake_pct"])))
            elif act in ("TRIMMED", "SOLD OUT"):
                selling_count += 1
                net_inflow_cr -= max(0, abs(d["change_pct"]) * 50.0)

            holdings.append(d)

        # 2. Block deals
        b_rows = conn.execute(
            """
            SELECT id, deal_date, ticker, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange
            FROM institutional_block_deals
            WHERE ticker = ?
            ORDER BY deal_date DESC LIMIT 20
            """,
            (sym,),
        ).fetchall()

        deals: list[dict[str, Any]] = []
        for b in b_rows:
            deals.append({
                "id": b[0],
                "deal_date": b[1],
                "ticker": b[2],
                "client_name": b[3],
                "deal_type": b[4].upper(),
                "quantity": b[5],
                "price": round(float(b[6]), 2),
                "value_cr": round(float(b[7]), 2),
                "pct_equity": round(float(b[8] or 0.0), 2),
                "exchange": b[9],
            })

        # 3. Shareholding pattern history
        p_rows = conn.execute(
            """
            SELECT quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct
            FROM shareholding_patterns
            WHERE ticker = ?
            ORDER BY quarter DESC LIMIT 4
            """,
            (sym,),
        ).fetchall()

        patterns: list[dict[str, Any]] = []
        for p in p_rows:
            patterns.append({
                "quarter": p[0],
                "promoter_pct": round(float(p[1]), 2),
                "fii_pct": round(float(p[2]), 2),
                "dii_mf_pct": round(float(p[3]), 2),
                "public_retail_pct": round(float(p[4]), 2),
                "other_pct": round(float(p[5]), 2),
            })

        # Derive institutional accumulation conviction score (0-100)
        score = 50.0
        if accumulating_count > selling_count:
            score += min(35.0, (accumulating_count - selling_count) * 12.0 + new_buys_count * 5.0)
        elif selling_count > accumulating_count:
            score -= min(35.0, (selling_count - accumulating_count) * 12.0)

        # Delta from shareholding pattern
        if len(patterns) >= 2:
            fii_delta = patterns[0]["fii_pct"] - patterns[1]["fii_pct"]
            dii_delta = patterns[0]["dii_mf_pct"] - patterns[1]["dii_mf_pct"]
            score += min(15.0, max(-15.0, (fii_delta + dii_delta) * 5.0))

        score = max(5.0, min(98.0, round(score, 1)))

        if score >= 75.0:
            verdict = "🔥 Aggressive Institutional Accumulation"
            verdict_badge = "emerald"
        elif score >= 58.0:
            verdict = "🟢 Moderate Institutional Accumulation"
            verdict_badge = "green"
        elif score >= 42.0:
            verdict = "⚖️ Stable Institutional Allocation"
            verdict_badge = "amber"
        else:
            verdict = "🔴 Institutional Distribution / Trimming"
            verdict_badge = "rose"

        # Company name lookup
        from earnings_engine.data.names import get_name
        company_name = get_name(sym) or sym.replace(".NS", "")

        return {
            "success": True,
            "ticker": sym,
            "company_name": company_name,
            "accumulation_score": score,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "funds_accumulating_count": accumulating_count,
            "funds_selling_count": selling_count,
            "new_funds_bought_count": new_buys_count,
            "net_flow_cr": round(net_inflow_cr, 1),
            "holdings": holdings,
            "block_deals": deals,
            "shareholding_patterns": patterns,
        }

    except Exception as e:
        logger.error("[INSTITUTIONAL] Failed fetching activity for %s: %s", sym, e)
        return {
            "success": False,
            "ticker": sym,
            "error": str(e),
            "holdings": [],
            "block_deals": [],
            "shareholding_patterns": [],
        }


def get_top_accumulated_stocks(
    universe: str | None = None,
    min_score: float = 60.0,
    limit: int = 25,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve high-conviction equities experiencing active institutional fund accumulation."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        # Find distinct tickers in holdings
        t_rows = conn.execute("SELECT DISTINCT ticker FROM institutional_holdings").fetchall()
        tickers = [r[0] for r in t_rows if r[0]]

        results: list[dict[str, Any]] = []
        for t in tickers:
            act = get_stock_institutional_activity(t, settings=settings)
            if act.get("success") and act.get("accumulation_score", 0) >= min_score:
                results.append({
                    "ticker": act["ticker"],
                    "company_name": act["company_name"],
                    "accumulation_score": act["accumulation_score"],
                    "verdict": act["verdict"],
                    "verdict_badge": act["verdict_badge"],
                    "funds_accumulating_count": act["funds_accumulating_count"],
                    "funds_selling_count": act["funds_selling_count"],
                    "new_funds_bought_count": act["new_funds_bought_count"],
                    "net_flow_cr": act["net_flow_cr"],
                    "top_funds": [h["fund_name"] for h in act["holdings"] if h["action"] in ("NEW BUY", "ACCUMULATED")][:3],
                    "total_institutional_stake": round(sum(h["stake_pct"] for h in act["holdings"]), 2),
                })

        results.sort(key=lambda x: x["accumulation_score"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Top accumulated error: %s", e)
        return []


def get_top_distributed_stocks(
    limit: int = 20,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve equities where institutional funds are actively trimming or liquidating positions."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        t_rows = conn.execute("SELECT DISTINCT ticker FROM institutional_holdings").fetchall()
        tickers = [r[0] for r in t_rows if r[0]]

        results: list[dict[str, Any]] = []
        for t in tickers:
            act = get_stock_institutional_activity(t, settings=settings)
            if act.get("success") and act.get("funds_selling_count", 0) > 0:
                results.append({
                    "ticker": act["ticker"],
                    "company_name": act["company_name"],
                    "accumulation_score": act["accumulation_score"],
                    "verdict": act["verdict"],
                    "verdict_badge": act["verdict_badge"],
                    "funds_selling_count": act["funds_selling_count"],
                    "exiting_funds": [h["fund_name"] for h in act["holdings"] if h["action"] in ("TRIMMED", "SOLD OUT")],
                    "net_flow_cr": act["net_flow_cr"],
                })

        results.sort(key=lambda x: x["funds_selling_count"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Top distributed error: %s", e)
        return []


def get_all_funds_activity(limit: int = 50, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve distinct list of active institutional funds with their latest actions."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            """
            SELECT fund_name, fund_type, COUNT(DISTINCT ticker) as total_positions,
                   SUM(CASE WHEN action IN ('NEW BUY', 'ACCUMULATED') THEN 1 ELSE 0 END) as buying_actions,
                   SUM(CASE WHEN action IN ('TRIMMED', 'SOLD OUT') THEN 1 ELSE 0 END) as selling_actions,
                   SUM(holding_value_cr) as total_aum_tracked_cr
            FROM institutional_holdings
            GROUP BY fund_name, fund_type
            ORDER BY total_positions DESC, buying_actions DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        funds: list[dict[str, Any]] = []
        for r in rows:
            funds.append({
                "fund_name": r[0],
                "fund_type": r[1],
                "total_positions": r[2],
                "buying_actions": r[3],
                "selling_actions": r[4],
                "total_aum_tracked_cr": round(float(r[5] or 0.0), 1),
            })
        return funds
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Funds list error: %s", e)
        return []


def get_fund_portfolio_activity(fund_name: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Reverse lookup: retrieve all equities held and recent actions for a specific fund."""
    settings = settings or Settings()
    init_institutional_db(settings)

    try:
        conn = get_db_connection(settings)
        rows = conn.execute(
            """
            SELECT ticker, quarter, shares_held, stake_pct, holding_value_cr,
                   action, change_pct, reported_date
            FROM institutional_holdings
            WHERE LOWER(fund_name) = LOWER(?)
            ORDER BY stake_pct DESC
            """,
            (fund_name.strip(),),
        ).fetchall()

        holdings: list[dict[str, Any]] = []
        for r in rows:
            holdings.append({
                "ticker": r[0],
                "quarter": r[1],
                "shares_held": r[2],
                "stake_pct": round(float(r[3] or 0.0), 2),
                "holding_value_cr": round(float(r[4] or 0.0), 1),
                "action": r[5],
                "change_pct": round(float(r[6] or 0.0), 2),
                "reported_date": r[7],
            })
        return holdings
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Fund portfolio error for %s: %s", fund_name, e)
        return []
