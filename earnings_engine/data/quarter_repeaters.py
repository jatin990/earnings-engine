"""Quarter Repeaters & AI Forward Earnings Radar Engine.

Identifies companies that delivered stellar earnings beats and week-high rallies
in their prior quarterly results, enriches them with real-time news catalysts,
QoQ fundamental streaks, and industry buzz themes, and leverages Multi-Model AI
to forecast whether upcoming quarterly results will sustain their winning streak.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.news_sentiment import get_ticker_news_and_sentiment
from earnings_engine.data.prices import load_price_metrics, load_price_metrics_batch, load_prices
from earnings_engine.data.universe import load_universe
from earnings_engine.data.watchlists import all_watchlists, get_watchlist

logger = logging.getLogger("earnings_engine.data.quarter_repeaters")

# Industry Buzz Thematic Taxonomy
INDUSTRY_BUZZ_TAXONOMY: list[tuple[list[str], str]] = [
    (["dixon", "kaynes", "syrma", "amber", "electronics", "ems", "semiconductor", "hardware"], "⚡ EMS & High-Tech Electronics"),
    (["hal", "bel", "mazagon", "cochin", "paras", "astramicro", "defense", "aerospace", "shipbuilder"], "🛡️ Defense & Aerospace Upcycle"),
    (["tata power", "suzlon", "inox wind", "waaree", "ireda", "power", "solar", "renewable", "energy"], "⚡ Power & Renewable Infrastructure"),
    (["l&t", "bhel", "abb", "siemens", "cummins", "capital goods", "infrastructure", "engineering"], "🏗️ Capital Goods & Capex Cycle"),
    (["tata motors", "m&m", "maruti", "bajaj auto", "auto", "electric vehicle", "ev"], "🚗 Auto & EV Ancillaries"),
    (["tcs", "infosys", "persistent", "kpit", "tata elxsi", "software", "information technology", "ai"], "💻 AI & Cloud Enterprise Software"),
    (["hdfc", "icici", "sbi", "kotak", "bajaj finance", "bank", "financial services", "nbfc", "wealth"], "🏦 Private Banking & Wealth Expansion"),
    (["sun pharma", "dr reddy", "divis", "cipla", "torrent", "pharmaceutical", "healthcare", "cdmo", "biotech"], "💊 Pharma & API / CDMO"),
    (["tata consumer", "varun beverages", "nestle", "itc", "fmcg", "consumer goods", "retail"], "🛒 Premium Consumption & Retail"),
    (["tata steel", "jsw", "hindalco", "vedanta", "steel", "metals", "mining"], "⛏️ Commodities & Metal Super-Cycle"),
]


def classify_industry_buzz(company_name: str, industry: str, sector: str, ticker: str) -> str:
    """Classify a company into an institutional industry buzz theme."""
    combined = f"{ticker} {company_name} {industry} {sector}".lower()
    for keywords, buzz_tag in INDUSTRY_BUZZ_TAXONOMY:
        if any(kw in combined for kw in keywords):
            return buzz_tag
    if industry and industry not in ("—", "None", ""):
        return f"🏷️ {industry}"
    if sector and sector not in ("—", "None", ""):
        return f"🏷️ {sector}"
    return "📈 Growth & Industrial"


def compute_beat_streak(metrics: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Calculate QoQ beat streak from stored quarterly metrics (Q1, Q2, Q3).

    Returns (streak_count, list_of_quarter_summaries).
    """
    quarters = [
        ("Q1 (Latest)", metrics.get("q1_earnings_score"), metrics.get("q1_surprise_pct"), metrics.get("q1_week_high_pct"), metrics.get("q1_earnings_date")),
        ("Q2 (Prior)", metrics.get("q2_earnings_score"), metrics.get("q2_surprise_pct"), metrics.get("q2_week_high_pct"), metrics.get("q2_earnings_date")),
        ("Q3 (Prior-2)", metrics.get("q3_earnings_score"), metrics.get("q3_surprise_pct"), metrics.get("q3_week_high_pct"), metrics.get("q3_earnings_date")),
    ]

    history: list[dict[str, Any]] = []
    streak = 0
    streak_active = True

    for label, score, surp, high_pct, edate in quarters:
        score_val = float(score) if score is not None and not (isinstance(score, float) and np.isnan(score)) else None
        surp_val = float(surp) if surp is not None and not (isinstance(surp, float) and np.isnan(surp)) else None
        high_val = float(high_pct) if high_pct is not None and not (isinstance(high_pct, float) and np.isnan(high_pct)) else None

        is_beat = False
        if surp_val is not None and surp_val > 0:
            is_beat = True
        elif score_val is not None and score_val >= 6:
            is_beat = True

        if is_beat and streak_active:
            streak += 1
        elif not is_beat:
            streak_active = False

        if score_val is not None or surp_val is not None:
            history.append({
                "quarter": label,
                "score": score_val,
                "surprise_pct": surp_val,
                "week_high_pct": high_val,
                "earnings_date": str(edate)[:10] if edate else None,
                "is_beat": is_beat,
            })

    return streak, history


def get_cached_repeater_prediction(ticker: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Retrieve the latest cached AI forward prediction for a ticker."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        row = conn.execute(
            "SELECT ticker, run_at, as_of_quarter, last_eps_surprise, last_week_high_pct, "
            "last_quality_score, beat_streak, industry_buzz_tag, ai_repeat_verdict, "
            "repeat_probability_pct, confidence_pct, expected_price_bias, growth_drivers_json, "
            "risk_factors_json, thesis, news_summary, days_to_next_earnings, next_earnings_date, payload_json "
            "FROM quarter_repeater_predictions WHERE ticker = ? ORDER BY run_at DESC LIMIT 1",
            (ticker.strip().upper(),),
        ).fetchone()
        conn.close()

        if not row:
            return None

        return {
            "ticker": row[0],
            "run_at": row[1],
            "as_of_quarter": row[2],
            "last_eps_surprise": row[3],
            "last_week_high_pct": row[4],
            "last_quality_score": row[5],
            "beat_streak": row[6],
            "industry_buzz_tag": row[7],
            "ai_repeat_verdict": row[8],
            "repeat_probability_pct": row[9],
            "confidence_pct": row[10],
            "expected_price_bias": row[11],
            "growth_drivers": json.loads(row[12]) if row[12] else [],
            "risk_factors": json.loads(row[13]) if row[13] else [],
            "thesis": row[14],
            "news_summary": row[15],
            "days_to_next_earnings": row[16],
            "next_earnings_date": row[17],
            "payload": json.loads(row[18]) if row[18] else {},
        }
    except Exception as e:
        logger.debug("[REPEATERS] Could not load cached prediction for %s: %s", ticker, e)
        return None


def get_cached_repeater_predictions_batch(
    tickers: list[str],
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Retrieve the latest cached AI forward predictions for multiple tickers in batch."""
    if not tickers:
        return {}
    settings = settings or Settings()
    cleaned = [t.strip().upper() for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))
    result: dict[str, dict[str, Any]] = {}

    CHUNK_SIZE = 200
    try:
        conn = get_db_connection(settings)
        for i in range(0, len(unique_tickers), CHUNK_SIZE):
            chunk = unique_tickers[i : i + CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            query = (
                "SELECT ticker, run_at, as_of_quarter, last_eps_surprise, last_week_high_pct, "
                "last_quality_score, beat_streak, industry_buzz_tag, ai_repeat_verdict, "
                "repeat_probability_pct, confidence_pct, expected_price_bias, growth_drivers_json, "
                "risk_factors_json, thesis, news_summary, days_to_next_earnings, next_earnings_date, payload_json "
                f"FROM quarter_repeater_predictions WHERE ticker IN ({placeholders}) ORDER BY run_at DESC"
            )
            rows = conn.execute(query, chunk).fetchall()
            for row in rows:
                sym = str(row[0]).strip().upper()
                if sym in result:
                    continue  # Already have latest due to ORDER BY run_at DESC
                try:
                    result[sym] = {
                        "ticker": row[0],
                        "run_at": row[1],
                        "as_of_quarter": row[2],
                        "last_eps_surprise": row[3],
                        "last_week_high_pct": row[4],
                        "last_quality_score": row[5],
                        "beat_streak": row[6],
                        "industry_buzz_tag": row[7],
                        "ai_repeat_verdict": row[8],
                        "repeat_probability_pct": row[9],
                        "confidence_pct": row[10],
                        "expected_price_bias": row[11],
                        "growth_drivers": json.loads(row[12]) if row[12] else [],
                        "risk_factors": json.loads(row[13]) if row[13] else [],
                        "thesis": row[14],
                        "news_summary": row[15],
                        "days_to_next_earnings": row[16],
                        "next_earnings_date": row[17],
                        "payload": json.loads(row[18]) if row[18] else {},
                    }
                except Exception:
                    pass
        conn.close()
    except Exception as e:
        logger.debug("[REPEATERS] Could not batch load cached predictions: %s", e)

    return result


def store_repeater_prediction(ticker: str, data: dict[str, Any], settings: Settings | None = None) -> None:
    """Store an AI Forward prediction into the database."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    now_iso = datetime.now(timezone.utc).isoformat()

    growth_json = json.dumps(data.get("growth_drivers", []))
    risk_json = json.dumps(data.get("risk_factors", []))
    payload_json = json.dumps(data)

    try:
        conn = get_db_connection(settings)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO quarter_repeater_predictions (
                    ticker, run_at, as_of_quarter, last_eps_surprise, last_week_high_pct,
                    last_quality_score, beat_streak, industry_buzz_tag, ai_repeat_verdict,
                    repeat_probability_pct, confidence_pct, expected_price_bias, growth_drivers_json,
                    risk_factors_json, thesis, news_summary, days_to_next_earnings, next_earnings_date, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sym,
                now_iso,
                data.get("as_of_quarter", "Q1"),
                data.get("last_eps_surprise"),
                data.get("last_week_high_pct"),
                data.get("last_quality_score"),
                data.get("beat_streak", 1),
                data.get("industry_buzz_tag", "Growth"),
                data.get("ai_repeat_verdict", "MODERATE_BEAT"),
                data.get("repeat_probability_pct", 75.0),
                data.get("confidence_pct", 70.0),
                data.get("expected_price_bias", "BULLISH"),
                growth_json,
                risk_json,
                data.get("thesis", ""),
                data.get("news_summary", ""),
                data.get("days_to_next_earnings"),
                data.get("next_earnings_date"),
                payload_json,
            ))
            conn.commit()
    except Exception as e:
        logger.warning("[REPEATERS] Failed to store prediction for %s: %s", sym, e)


def scan_quarter_repeaters(
    settings: Settings,
    universe: str | None = None,
    min_beat_pct: float = 0.0,
    min_week_high_pct: float = 2.5,
    limit: int = 60,
) -> list[dict[str, Any]]:
    """Screen for companies that had strong past quarterly beats & week highs."""
    tickers: set[str] = set()
    u_clean = universe.lower().strip() if universe else "all"

    if u_clean in ("nifty_50", "nifty50", "nifty_top_50", "nse_top"):
        uni = load_universe("NSE_TOP", settings) or load_universe("NIFTY_50", settings)
        if uni:
            tickers.update(uni)
    elif u_clean in ("nse_large_cap", "large_cap"):
        large_caps = load_universe("NSE_LARGE_CAP", settings)
        if large_caps:
            tickers.update(large_caps)
    elif u_clean in ("us_top", "us"):
        us_uni = load_universe("US_TOP", settings)
        if us_uni:
            tickers.update(us_uni)
    elif u_clean == "all":
        # Load all tracked universes
        for u in ("NSE_ALL", "IN", "NSE_LARGE_CAP", "NSE_TOP", "US_TOP"):
            uni = load_universe(u, settings)
            if uni:
                tickers.update(uni)
        try:
            wls = all_watchlists(settings)
            for wl in wls:
                if isinstance(wl, dict):
                    tickers.update(wl.get("tickers", []))
                elif isinstance(wl, str):
                    wl_t = get_watchlist(wl, settings)
                    if wl_t:
                        tickers.update(wl_t)
        except Exception:
            pass
        try:
            conn = get_db_connection(settings)
            rows = conn.execute("SELECT ticker FROM tickers WHERE metrics IS NOT NULL").fetchall()
            conn.close()
            tickers.update([r[0] for r in rows if r[0]])
        except Exception:
            pass
    else:
        wl_tickers = get_watchlist(universe, settings)
        if wl_tickers:
            tickers.update(wl_tickers)
        else:
            custom_uni = load_universe(universe, settings)
            if custom_uni:
                tickers.update(custom_uni)

    if not tickers:
        try:
            wls = all_watchlists(settings)
            for wl in wls:
                if isinstance(wl, dict):
                    tickers.update(wl.get("tickers", []))
                elif isinstance(wl, str):
                    wl_t = get_watchlist(wl, settings)
                    if wl_t:
                        tickers.update(wl_t)
        except Exception:
            pass
        try:
            for u in ("NSE_ALL", "NSE_TOP", "IN", "NSE_LARGE_CAP"):
                uni = load_universe(u, settings)
                if uni:
                    tickers.update(uni)
        except Exception:
            pass

    if not tickers:
        try:
            conn = get_db_connection(settings)
            rows = conn.execute("SELECT ticker FROM tickers WHERE ticker IS NOT NULL LIMIT 200").fetchall()
            if not rows:
                rows = conn.execute("SELECT DISTINCT ticker FROM price_history LIMIT 200").fetchall()
            conn.close()
            tickers.update([r[0] for r in rows if r[0]])
        except Exception:
            pass

    sorted_tickers = sorted(tickers)
    metrics_by_ticker = load_price_metrics_batch(sorted_tickers, settings) if sorted_tickers else {}

    pre_candidates: list[dict[str, Any]] = []

    for ticker in sorted_tickers:
        try:
            sym_key = ticker.strip().upper()
            metrics = metrics_by_ticker.get(sym_key) or metrics_by_ticker.get(ticker) or {}
            if not metrics:
                continue

            q1_score = metrics.get("q1_earnings_score")
            q1_surprise = metrics.get("q1_surprise_pct")
            q1_week_high = metrics.get("q1_week_high_pct")
            q1_date = metrics.get("q1_earnings_date")
            q1_ai_note = metrics.get("q1_ai_note")

            score_val = float(q1_score) if q1_score is not None and not (isinstance(q1_score, float) and np.isnan(q1_score)) else None
            surp_val = float(q1_surprise) if q1_surprise is not None and not (isinstance(q1_surprise, float) and np.isnan(q1_surprise)) else None
            high_val = float(q1_week_high) if q1_week_high is not None and not (isinstance(q1_week_high, float) and np.isnan(q1_week_high)) else None

            # Condition 1: Last result delivered (Beat > min_beat_pct OR Score >= 6)
            is_beat = False
            if surp_val is not None and surp_val >= min_beat_pct:
                is_beat = True
            elif score_val is not None and score_val >= 6:
                is_beat = True

            if not is_beat:
                continue

            # Condition 2: Week High reaction (Peak move >= min_week_high_pct or score >= 8)
            if high_val is not None and high_val < min_week_high_pct and (score_val or 0) < 8:
                continue

            # Compute QoQ streak
            streak, streak_history = compute_beat_streak(metrics)

            # Industry buzz tag
            company_name = metrics.get("company_name") or ticker
            industry = metrics.get("industry") or metrics.get("sector") or ""
            sector = metrics.get("sector") or ""
            buzz_tag = classify_industry_buzz(company_name, industry, sector, ticker)

            # Days to next earnings
            days_to_next = None
            next_date_str = None
            today = datetime.now().date()
            if metrics.get("next_earnings_date"):
                try:
                    nd = datetime.strptime(str(metrics["next_earnings_date"])[:10], "%Y-%m-%d").date()
                    days_to_next = (nd - today).days
                    next_date_str = str(nd)
                except Exception:
                    pass

            # Build repeater composite conviction score
            base_score = 50.0
            if surp_val is not None:
                base_score += min(25.0, max(0.0, surp_val * 1.2))
            if high_val is not None:
                base_score += min(15.0, max(0.0, high_val * 0.8))
            if streak >= 2:
                base_score += streak * 5.0
            conviction_score = round(min(98.0, base_score), 1)

            pre_candidates.append({
                "ticker": ticker,
                "sym_key": sym_key,
                "company_name": company_name,
                "industry": industry or "—",
                "sector": sector or "—",
                "industry_buzz_tag": buzz_tag,
                "current_price": metrics.get("current_price"),
                "last_eps_surprise": surp_val,
                "last_quality_score": int(score_val) if score_val is not None else None,
                "last_week_high_pct": high_val,
                "last_week_low_pct": metrics.get("q1_week_low_pct"),
                "earnings_week_move_pct": metrics.get("earnings_week_move_pct"),
                "last_earnings_date": str(q1_date)[:10] if q1_date else None,
                "last_ai_note": q1_ai_note or metrics.get("q1_ai_summary"),
                "beat_streak": streak,
                "streak_history": streak_history,
                "conviction_score": conviction_score,
                "days_to_next_earnings": days_to_next,
                "next_earnings_date": next_date_str,
                "market_cap_cr": metrics.get("market_cap_cr"),
                "thirty_day_return_pct": metrics.get("thirty_day_return_pct"),
                "pct_from_52w_high": metrics.get("pct_from_52w_high"),
            })
        except Exception as e:
            logger.debug("[REPEATERS] Error processing ticker %s: %s", ticker, e)

    # Batch load cached AI predictions for pre-candidates
    candidate_tickers = [c["ticker"] for c in pre_candidates]
    predictions_map = get_cached_repeater_predictions_batch(candidate_tickers, settings) if candidate_tickers else {}

    candidates: list[dict[str, Any]] = []
    for c in pre_candidates:
        sym_key = c.pop("sym_key")
        ticker = c["ticker"]
        c["ai_forecast"] = predictions_map.get(sym_key) or predictions_map.get(ticker)
        candidates.append(c)

    # Sort candidates by composite conviction score descending
    candidates.sort(key=lambda x: x["conviction_score"], reverse=True)
    return candidates[:limit]


def generate_ai_repeater_forecast(
    ticker: str,
    settings: Settings | None = None,
    model_name: str | None = None,
    provider: str = "auto",
) -> dict[str, Any]:
    """Execute AI Forward reasoning for upcoming quarter earnings continuity with model selection."""
    settings = settings or Settings()
    sym = ticker.strip().upper()

    metrics = load_price_metrics(sym, settings) or {}
    company_name = metrics.get("company_name") or sym
    industry = metrics.get("industry") or "—"
    sector = metrics.get("sector") or "—"
    buzz_tag = classify_industry_buzz(company_name, industry, sector, sym)

    # Gather news & sentiment
    news_res = get_ticker_news_and_sentiment(sym, limit=6)
    articles = news_res.get("articles", [])
    news_headlines = [f"• [{a.get('published_at', '')[:10]}] {a.get('title', '')} ({a.get('sentiment_label', 'Neutral')})" for a in articles[:5]]
    news_summary_text = "\n".join(news_headlines) if news_headlines else "No recent material headlines found."

    streak, history = compute_beat_streak(metrics)
    last_surp = metrics.get("q1_surprise_pct")
    last_week_high = metrics.get("q1_week_high_pct")
    last_week_low = metrics.get("q1_week_low_pct")
    last_week_move = metrics.get("earnings_week_move_pct")
    last_score = metrics.get("q1_earnings_score")
    q1_summary = metrics.get("q1_ai_summary") or ""

    # Construct quantitative multi-factor prompt
    prompt = f"""You are an elite institutional equity analyst specializing in Indian and global corporate earnings cycles.
Analyze whether the following stock will SUSTAIN its earnings winning streak and deliver a REPEAT BEAT in the upcoming quarterly earnings release.

### Company Profile
- Ticker: {sym} ({company_name})
- Industry / Sector: {industry} | {sector}
- Market Theme / Buzz: {buzz_tag}
- Current Price: ₹{metrics.get('current_price', 'N/A')}
- 30-Day Momentum Return: {metrics.get('thirty_day_return_pct', 'N/A')}%
- Distance from 52W High: {metrics.get('pct_from_52w_high', 'N/A')}%

### Past Earnings Delivery & Reaction Mechanics
- Prior Quarter EPS Surprise: {f'{last_surp:+.1f}%' if last_surp is not None else 'N/A'}
- Prior Post-Earnings Week Peak High: {f'{last_week_high:+.1f}%' if last_week_high is not None else 'N/A'}
- Prior Post-Earnings Week Low (Drawdown): {f'{last_week_low:+.1f}%' if last_week_low is not None else 'N/A'}
- Prior Net 1-Week Post-Earnings Move: {f'{last_week_move:+.1f}%' if last_week_move is not None else 'N/A'}
- Prior Result Summary: {q1_summary}
- Quality Score: {last_score}/9
- Consecutive Beat Streak: {streak} quarters
- 3-Quarter Delivery History: {json.dumps(history)}

### Recent Corporate News, Filings, Catalysts & Order Wins
{news_summary_text}

### Instructions:
1. Assess why the prior quarterly result moved as it did (e.g. initial dip or pullback due to profit-taking despite stellar peak rally and EPS beat vs sustained continuation).
2. Evaluate recent news flow, new contracts, order wins, and industry macro tailwinds for upcoming quarter revenue visibility.
3. Predict if the upcoming quarterly result will be a Repeat Beat, In-Line, or Risk of Miss.
4. Output STRICT JSON adhering to this exact schema (no markdown outside JSON):

{{
  "ai_repeat_verdict": "STRONG_REPEAT_BEAT",
  "repeat_probability_pct": 85,
  "confidence_pct": 80,
  "predicted_next_quarter_quality": 8,
  "industry_buzz_tag": "{buzz_tag}",
  "industry_tailwind_score": 8,
  "price_action_assessment": "Explanation of the prior earnings reaction dynamics (e.g., peak rally vs net move) and current technical setup.",
  "primary_growth_drivers": [
    "Driver 1 (order flow, margin expansion)",
    "Driver 2 (sector tailwind)"
  ],
  "key_risk_factors": [
    "Risk 1 (valuation, input costs)"
  ],
  "thesis": "Concise 2-sentence institutional rationale explaining the forward expectation.",
  "expected_price_bias": "BULLISH",
  "suggested_action": "ACCUMULATE_PRE_EARNINGS"
}}
"""

    output_dict: dict[str, Any] | None = None
    model_used = model_name or "auto"
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    # 1. Targeted or Auto OpenRouter Inference
    if (provider == "openrouter" or (provider == "auto" and model_name and "/" in model_name)) and openrouter_key:
        target_model = model_name or "deepseek/deepseek-r1:free"
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://earnings-engine.local",
                    "X-Title": "Earnings Engine Repeater Radar",
                },
                data=json.dumps({
                    "model": target_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1000,
                }).encode("utf-8"),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    output_dict = json.loads(m.group(0))
                    model_used = f"OpenRouter ({target_model})"
        except Exception as e:
            logger.debug("[REPEATERS] OpenRouter inference failed for %s (%s): %s", sym, target_model, e)

    # 2. Targeted or Auto Local Ollama Inference
    if not output_dict and (provider in ("ollama", "auto") or not openrouter_key):
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = model_name if (model_name and "/" not in model_name) else os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        try:
            import urllib.request
            data_payload = json.dumps({
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "num_ctx": 4096,
                    "temperature": 0.3,
                },
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{ollama_host}/api/generate",
                data=data_payload,
                headers={"Content-Type": "application/json"},
            )
            timeout = 45 if "8b" in ollama_model or "deepseek" in ollama_model else 18
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_res = json.loads(resp.read().decode("utf-8"))
                resp_text = raw_res.get("response", "")
                m = re.search(r"\{[\s\S]*\}", resp_text)
                if m:
                    output_dict = json.loads(m.group(0))
                    model_used = f"Local Ollama ({ollama_model})"
        except Exception as e:
            logger.debug("[REPEATERS] Local Ollama call failed for %s (%s): %s", sym, ollama_model, e)

    # 3. Heuristic institutional fallback if LLMs unavailable
    if not output_dict:
        surp_score = float(last_surp or 5.0)
        high_score = float(last_week_high or 3.0)
        rep_prob = min(95.0, max(50.0, 60.0 + surp_score * 1.5 + streak * 4.0 + (high_score * 0.5)))
        
        verdict = "STRONG_REPEAT_BEAT" if rep_prob >= 80 else ("MODERATE_BEAT" if rep_prob >= 65 else "IN_LINE")
        model_used = "Institutional Quantitative Rules"
        
        # Price action explanation
        reaction_desc = "Strong positive earnings reaction."
        if last_week_move is not None and last_week_move < 0 and high_score > 3.0:
            reaction_desc = f"Stock rallied to a peak of +{high_score:.1f}% intra-week before experiencing short-term profit booking to close at {last_week_move:+.1f}%. Medium-term momentum remains positive ({metrics.get('thirty_day_return_pct', 0):+.1f}% 30D return)."
        elif high_score > 0:
            reaction_desc = f"Stock demonstrated healthy demand with a +{high_score:.1f}% peak post-earnings rally."

        output_dict = {
            "ai_repeat_verdict": verdict,
            "repeat_probability_pct": round(rep_prob, 1),
            "confidence_pct": 75,
            "predicted_next_quarter_quality": 8 if rep_prob >= 80 else 7,
            "industry_buzz_tag": buzz_tag,
            "industry_tailwind_score": 8,
            "price_action_assessment": reaction_desc,
            "primary_growth_drivers": [
                f"Sustained fundamental momentum following {f'{last_surp:+.1f}%' if last_surp is not None else 'strong'} EPS delivery",
                f"{buzz_tag} macro industry upcycle and healthy order book visibility",
            ],
            "key_risk_factors": [
                "Elevated consensus expectations leaving smaller margin for operational delay",
                "Broader market volatility and sector rotation",
            ],
            "thesis": f"{company_name} demonstrates strong QoQ consistency with a {streak}-quarter beat streak. Active tailwinds in {buzz_tag} provide constructive forward visibility for the upcoming print.",
            "expected_price_bias": "BULLISH" if rep_prob >= 70 else "NEUTRAL",
            "suggested_action": "ACCUMULATE_PRE_EARNINGS" if rep_prob >= 75 else "WATCH_CONFIRMATION",
        }

    output_dict["ticker"] = sym
    output_dict["model_used"] = model_used
    output_dict["as_of_quarter"] = "Q1"
    output_dict["last_eps_surprise"] = last_surp
    output_dict["last_week_high_pct"] = last_week_high
    output_dict["last_week_low_pct"] = last_week_low
    output_dict["earnings_week_move_pct"] = last_week_move
    output_dict["last_quality_score"] = last_score
    output_dict["beat_streak"] = streak
    output_dict["streak_history"] = history
    output_dict["news_summary"] = news_summary_text
    output_dict["news_articles"] = articles[:6]
    output_dict["next_earnings_date"] = str(metrics.get("next_earnings_date"))[:10] if metrics.get("next_earnings_date") else None
    
    # Store complete input audit trail for full transparency
    output_dict["considered_data"] = {
        "ticker": sym,
        "company_name": company_name,
        "industry": industry,
        "sector": sector,
        "industry_buzz_tag": buzz_tag,
        "current_price": metrics.get("current_price"),
        "thirty_day_return_pct": metrics.get("thirty_day_return_pct"),
        "pct_from_52w_high": metrics.get("pct_from_52w_high"),
        "earnings_week_move_pct": last_week_move,
        "last_week_high_pct": last_week_high,
        "last_week_low_pct": last_week_low,
        "last_eps_surprise": last_surp,
        "last_quality_score": last_score,
        "q1_ai_summary": q1_summary,
        "beat_streak": streak,
        "streak_history": history,
        "news_articles": articles[:6],
        "screening_rationale": f"Screened into Repeaters because company delivered prior {f'{last_surp:+.1f}%' if last_surp is not None else 'High Quality (Score ' + str(last_score or '6') + '/9)'} EPS beat and {f'+{last_week_high:.1f}%' if last_week_high is not None else 'positive'} peak post-earnings rally.",
    }

    # Store to database
    store_repeater_prediction(sym, output_dict, settings)
    return output_dict
