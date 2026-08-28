"""Kronos AI price prediction module for Indian equities.

This module provides 14-day price predictions using the Kronos foundation model,
extracted and modularized from RayCodes_Kronos/market_advisor.py for integration
with the earnings-engine ecosystem.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import yfinance as yf

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

logger = logging.getLogger("earnings_engine.kronos_predictor")

# Fixed models as mandated by specification
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_API = "http://localhost:11434/api/generate"
KRONOS_MODEL_NAME = "NeoQuasar/Kronos-base"
TOKENIZER_NAME = "NeoQuasar/Kronos-Tokenizer-base"

# Module-level cache for Kronos model instances (reused across predictions)
_KRONOS_CACHE: dict[str, Any] = {
    "tokenizer": None,
    "model": None,
    "device": None,
    "predictor": None,
    "predictor_device": None,
}


def _setup_kronos_paths() -> bool:
    """Add Kronos library to system path if not already present."""
    candidates = [
        os.getenv("KRONOS_LIB_PATH"),
        Path(__file__).resolve().parent.parent.parent / "RayCodes_Kronos" / "kronos_lib",
        Path(__file__).resolve().parent.parent / "RayCodes_Kronos" / "kronos_lib",
        Path.cwd() / "RayCodes_Kronos" / "kronos_lib",
        Path("D:/RayCodes_Kronos/kronos_lib"),
        Path("C:/RayCodes_Kronos/kronos_lib"),
    ]
    for cand in candidates:
        if not cand:
            continue
        p = Path(cand).resolve()
        if p.exists() and (p / "model").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            return True
        elif p.exists():
            if str(p) not in sys.path:
                sys.path.append(str(p))
            return True
    return False


def _import_kronos():
    """Import Kronos classes, setting up paths if needed."""
    _setup_kronos_paths()
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor
        return Kronos, KronosTokenizer, KronosPredictor
    except ImportError:
        logger.warning("Kronos library not found. Price predictions will be unavailable.")
        return None, None, None


def _normalize_device(device: str | None = None) -> str:
    """Normalize and validate a PyTorch device string for Kronos inference.

    Handles 'cuda' -> 'cuda:0', validates CUDA availability, and falls back to CPU
    gracefully if CUDA was requested but is not available.
    """
    if device is None or not str(device).strip():
        from earnings_engine.config import get_default_device
        device = get_default_device()

    dev = str(device).strip().lower()
    if dev == "cuda":
        dev = "cuda:0"

    if not TORCH_AVAILABLE or torch is None:
        return "cpu"

    if dev.startswith("cuda"):
        if not torch.cuda.is_available():
            logger.warning("[DEVICE] CUDA requested (%s) but torch.cuda is not available; falling back to CPU", dev)
            return "cpu"
        try:
            torch.cuda.get_device_properties(dev)
        except Exception as e:
            logger.warning("[DEVICE] CUDA device %s invalid (%s); falling back to cuda:0 or CPU", dev, e)
            if torch.cuda.is_available():
                return "cuda:0"
            return "cpu"
        return dev

    if dev == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        logger.warning("[DEVICE] MPS requested but not available; falling back to CPU")
        return "cpu"

    return "cpu" if dev not in ("cpu",) else dev


def get_cuda_status() -> dict[str, Any]:
    """Return diagnostic status of CUDA and GPU hardware for Kronos inference."""
    if not TORCH_AVAILABLE or torch is None:
        return {
            "cuda_available": False,
            "torch_version": None,
            "device_count": 0,
            "devices": [],
            "default_device": "cpu",
        }
    available = torch.cuda.is_available()
    status: dict[str, Any] = {
        "cuda_available": available,
        "torch_version": getattr(torch, "__version__", "unknown"),
        "device_count": torch.cuda.device_count() if available else 0,
        "devices": [],
        "default_device": _normalize_device(None),
    }
    if available:
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            total_mb = round(props.total_memory / (1024 * 1024), 2)
            allocated_mb = round(torch.cuda.memory_allocated(i) / (1024 * 1024), 2)
            reserved_mb = round(torch.cuda.memory_reserved(i) / (1024 * 1024), 2)
            status["devices"].append({
                "index": i,
                "name": props.name,
                "compute_capability": f"{props.major}.{props.minor}",
                "total_memory_mb": total_mb,
                "allocated_memory_mb": allocated_mb,
                "reserved_memory_mb": reserved_mb,
            })
    return status


def get_asset_name(symbol: str) -> str:
    """Resolve the display name for a ticker symbol."""
    try:
        info = yf.Ticker(symbol).info
        name = info.get("shortName") or info.get("longName") or symbol
        logger.info("[ASSET] Resolved name for %s: %s", symbol, name)
        return name
    except Exception as exc:
        logger.warning("[ASSET] Could not resolve name for %s: %s", symbol, exc)
        return symbol


def has_results_coming_up(symbol: str, days: int = 7) -> bool:
    """Check if the stock has earnings results in the next N days."""
    try:
        ticker = yf.Ticker(symbol)
        earnings_dates = getattr(ticker, "earnings_dates", None)
        if earnings_dates is None:
            return False

        if isinstance(earnings_dates, pd.DataFrame):
            if earnings_dates.empty:
                return False
            if "Earnings Date" in earnings_dates.columns:
                raw_dates = pd.to_datetime(earnings_dates["Earnings Date"], errors="coerce")
            else:
                raw_dates = pd.to_datetime(earnings_dates.index, errors="coerce")
            raw_dates = raw_dates.dropna()
            if raw_dates.empty:
                return False

            now = pd.Timestamp.now().tz_localize(None)
            future_window = now + pd.Timedelta(days=days)
            for dt in raw_dates:
                if pd.isna(dt):
                    continue
                if dt.tzinfo is not None:
                    dt = dt.tz_convert(None)
                if now <= dt <= future_window:
                    return True
        return False
    except Exception:
        return False


def get_upcoming_earnings_date(symbol: str, days: int = 7) -> str | None:
    """Get the next earnings date within the next N days."""
    try:
        ticker = yf.Ticker(symbol)
        earnings_dates = getattr(ticker, "earnings_dates", None)
        if earnings_dates is None:
            return None

        if isinstance(earnings_dates, pd.DataFrame):
            if earnings_dates.empty:
                return None
            if "Earnings Date" in earnings_dates.columns:
                raw_dates = pd.to_datetime(earnings_dates["Earnings Date"], errors="coerce")
            else:
                raw_dates = pd.to_datetime(earnings_dates.index, errors="coerce")
        elif isinstance(earnings_dates, pd.Series):
            raw_dates = pd.to_datetime(earnings_dates.index, errors="coerce")
        else:
            return None

        raw_dates = raw_dates.dropna()
        if raw_dates.empty:
            return None

        now = pd.Timestamp.now().tz_localize(None)
        future_window = now + pd.Timedelta(days=days)
        upcoming = []
        for dt in raw_dates:
            if pd.isna(dt):
                continue
            if dt.tzinfo is not None:
                dt = dt.tz_convert(None)
            if now <= dt <= future_window:
                upcoming.append(dt)

        if not upcoming:
            return None
        return min(upcoming).strftime("%d %b %Y")
    except Exception:
        return None


def get_last_week_change(symbol: str) -> float | None:
    """Calculate the percentage change over the last week."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="15d", interval="1d")
        if hist.empty or len(hist) < 5:
            return None
        close = hist["Close"].dropna()
        if len(close) < 5:
            return None
        current = float(close.iloc[-1])
        week_ago = float(close.iloc[-5])
        if week_ago == 0:
            return None
        return round(((current - week_ago) / week_ago) * 100, 2)
    except Exception:
        return None


def get_results_metadata(symbol: str) -> dict[str, Any]:
    """Get earnings-related metadata for a stock."""
    results_date = get_upcoming_earnings_date(symbol)
    weekly_change = get_last_week_change(symbol)
    logger.info("[EVENT] %s -> results_date=%s, 1W_change=%s", symbol, results_date, weekly_change)
    return {
        "results_date": results_date,
        "last_week_change_pct": weekly_change
    }


def _history_to_clean_df(df: pd.DataFrame) -> pd.DataFrame | None:
    """Convert a yfinance history DataFrame into the cleaned OHLCV schema.

    Returns None if the frame is empty or lacks the expected columns.
    """
    if df is None or df.empty:
        return None
    try:
        df = df.reset_index()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        df["timestamps"] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume"
        })
        cleaned = df[["timestamps", "open", "high", "low", "close", "volume"]].dropna()
        return cleaned if not cleaned.empty else None
    except Exception:
        return None


def fetch_historical_data(symbol: str) -> pd.DataFrame:
    """Fetch 1 year of historical price data for a stock.

    Handles the transient yfinance ``possibly delisted; no timezone found``
    warning that commonly affects NSE (``.NS``) tickers like ZOMATO.NS:
    retries with explicit start/end dates + ``auto_adjust=False``, then falls
    back to ``yf.download``.  Only if every live path fails do we fall back to
    synthetic data (and we log that clearly).
    """
    logger.info("[DATA] Fetching 1Y history for %s...", symbol)

    # --- Attempt 1: Ticker.history(period=...) ---
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")
        cleaned = _history_to_clean_df(df)
        if cleaned is not None and len(cleaned) >= 60:
            logger.info("[DATA] Loaded %d rows for %s from Yahoo Finance", len(cleaned), symbol)
            return cleaned
    except Exception as exc:
        logger.warning("[DATA] Yahoo Finance history failed for %s: %s", symbol, exc)

    # --- Attempt 2: explicit start/end + auto_adjust=False (avoids timezone lookup) ---
    try:
        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=400)
        df = yf.Ticker(symbol).history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
        )
        cleaned = _history_to_clean_df(df)
        if cleaned is not None and len(cleaned) >= 60:
            logger.info("[DATA] Loaded %d rows for %s via explicit-range retry", len(cleaned), symbol)
            return cleaned
    except Exception as exc:
        logger.warning("[DATA] Yahoo Finance explicit-range retry failed for %s: %s", symbol, exc)

    # --- Attempt 3: yf.download fallback ---
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False, auto_adjust=False)
        cleaned = _history_to_clean_df(df)
        if cleaned is not None and len(cleaned) >= 60:
            logger.info("[DATA] Loaded %d rows for %s via yf.download fallback", len(cleaned), symbol)
            return cleaned
    except Exception as exc:
        logger.warning("[DATA] yf.download fallback failed for %s: %s", symbol, exc)

    # --- Final fallback: synthetic data (logged clearly, never silent) ---
    base_price = 24000.0 if symbol == "^NSEI" else (1500.0 if "NS" in symbol else 84.0)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=180, freq='D')
    noise = np.random.normal(0, base_price * 0.01, size=len(dates))
    prices = base_price + np.cumsum(noise)
    df = pd.DataFrame({
        'timestamps': dates,
        'open': prices * 0.998,
        'high': prices * 1.006,
        'low': prices * 0.994,
        'close': prices,
        'volume': np.random.randint(100000, 5000000, size=len(dates))
    })
    logger.warning("[DATA] All live data paths failed for %s; using synthetic fallback with %d rows", symbol, len(df))
    return df


def generate_local_explanation(
    symbol_name: str,
    current: float,
    support: float,
    resistance: float,
    ret_pct: float,
    trend_text: str
) -> str:
    """Generate AI-powered trading explanation using Ollama."""
    logger.info("[EXPLAIN] Generating trader note for %s", symbol_name)
    prompt = (
        f"You are a seasoned Indian swing trader managing short-term equity positions. Analyze this 14-day AI forecast for {symbol_name} like a desk trader evaluating setup quality, risk, and reward. "
        f"Inputs: - Symbol: {symbol_name} - Current price: Rs. {current} - Projected resistance: Rs. {resistance} - Projected support: Rs. {support} - Expected return: {ret_pct}% - Trend direction: {trend_text}. "
        f"Provide a clear swing-trade read covering: - Trend quality and market structure. - Distance to support and resistance. - Whether upside justifies the downside risk. - Entry style: breakout, pullback, or wait. - Positioning bias over the next 14 days. "
        f"Style rules: - Professional, concise, and trader-focused. - Use standard market language. - Keep it specific to Indian equities. - Avoid hype, vague statements, and beginner explanations. - Mention key invalidation or caution levels. - Keep it to 4 to 6 sentences, with a direct conclusion."
    )
    try:
        response = requests.post(
            OLLAMA_API,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"think": False, "temperature": 0.3}
            },
            timeout=15
        )
        if response.status_code == 200:
            explanation = response.json().get("response", "").strip()
            logger.info("[EXPLAIN] Ollama returned explanation for %s", symbol_name)
            return explanation
    except Exception as e:
        logger.warning("[EXPLAIN] Ollama call failed for %s: %s", symbol_name, e)
    
    # Fallback explanation if Ollama is unavailable
    if ret_pct > 0:
        return (
            f"{symbol_name} shows positive momentum with an expected return of +{ret_pct}%. "
            f"Key levels: support at Rs. {support}, resistance at Rs. {resistance}. "
            f"Consider pullback entries near support for favorable risk-reward."
        )
    else:
        return (
            f"{symbol_name} is showing mild weakness with an expected return of {ret_pct}%. "
            f"Key levels: support at Rs. {support}, resistance at Rs. {resistance}. "
            f"Wait for confirmation near support before considering positions."
        )


def _get_kronos_predictor(device: str | None = None) -> Any | None:
    """Get or create a cached Kronos predictor instance.

    The returned ``KronosPredictor`` is a singleton: the same instance is
    reused across all predictions so the model + tokenizer are loaded exactly
    once per process and batched GPU inference via ``predict_batch`` operates
    on a single shared model.
    """
    Kronos, KronosTokenizer, KronosPredictor = _import_kronos()
    if KronosPredictor is None:
        return None

    norm_device = _normalize_device(device)

    # Return cached predictor instance if the device matches.
    if _KRONOS_CACHE["predictor"] is not None and _KRONOS_CACHE["predictor_device"] == norm_device:
        logger.debug("[CACHE] Reusing cached Kronos predictor on %s", norm_device)
        return _KRONOS_CACHE["predictor"]

    # Load and cache model components.
    if norm_device.startswith("cuda"):
        dev_idx = 0
        if ":" in norm_device:
            try:
                dev_idx = int(norm_device.split(":")[1])
            except ValueError:
                pass
        try:
            gpu_name = torch.cuda.get_device_name(dev_idx)
            total_vram = round(torch.cuda.get_device_properties(dev_idx).total_memory / (1024**3), 1)
            logger.info("[INIT] Initializing Kronos on CUDA GPU: %s (%s, %.1fGB VRAM)", norm_device, gpu_name, total_vram)
        except Exception as e:
            logger.info("[INIT] Initializing Kronos on CUDA GPU: %s (%s)", norm_device, e)
    else:
        logger.info("[INIT] Initializing Kronos on CPU / device: %s", norm_device)

    logger.info("[LOAD] Loading tokenizer: %s", TOKENIZER_NAME)
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_NAME)
    logger.info("[LOAD] Loading model: %s", KRONOS_MODEL_NAME)
    model = Kronos.from_pretrained(KRONOS_MODEL_NAME)

    predictor = KronosPredictor(model, tokenizer, device=norm_device, max_context=512)
    _KRONOS_CACHE["tokenizer"] = tokenizer
    _KRONOS_CACHE["model"] = model
    _KRONOS_CACHE["device"] = norm_device
    _KRONOS_CACHE["predictor"] = predictor
    _KRONOS_CACHE["predictor_device"] = norm_device

    logger.info("[CACHE] Cached Kronos predictor on %s", norm_device)
    return predictor


def predict_single_stock(
    symbol: str,
    lookback: int = 120,
    pred_len: int = 14,
    device: str | None = None
) -> dict[str, Any] | None:
    """Generate 14-day price prediction for a single stock.
    
    Returns a dictionary with prediction results or None if prediction fails.
    """
    norm_device = _normalize_device(device)
    predictor = _get_kronos_predictor(norm_device)
    if predictor is None:
        logger.error("Kronos library not available for prediction")
        return None
    
    try:
        # Fetch data
        df = fetch_historical_data(symbol)
        if len(df) < lookback:
            logger.warning("[EXEC] Skipping %s: insufficient data (%d rows)", symbol, len(df))
            return None
        
        # Prepare input
        x_df = df.iloc[-lookback:][['open', 'high', 'low', 'close']].reset_index(drop=True)
        x_timestamp = df.iloc[-lookback:]['timestamps'].reset_index(drop=True)
        
        last_date = x_timestamp.iloc[-1]
        y_timestamp = pd.Series([last_date + pd.Timedelta(days=i) for i in range(1, pred_len + 1)])
        logger.info("[PRED] Running %d-day forecast for %s using %d lookback rows", 
                   pred_len, symbol, len(x_df))
        
        # Generate prediction
        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=0.8,
            top_p=0.9,
            sample_count=1,
            verbose=False
        )
        
        # Extract results
        curr_close = round(float(x_df["close"].iloc[-1]), 2)
        proj_close = float(pred_df["close"].iloc[-1])
        support = round(float(pred_df["low"].min()), 2)
        resistance = round(float(pred_df["high"].max()), 2)
        
        logger.info(
            "[PRED] %s | current=%s | projected=%s | support=%s | resistance=%s",
            symbol, curr_close, proj_close, support, resistance
        )
        
        ret_pct = round(((proj_close - curr_close) / curr_close) * 100, 2)
        trend = "Bullish" if ret_pct >= 0.5 else ("Bearish" if ret_pct <= -0.5 else "Neutral")
        
        # Get metadata
        asset_name = get_asset_name(symbol)
        results_meta = get_results_metadata(symbol)
        
        # Build the full 14-day forecast series (everything Kronos returns:
        # open/high/low/close/volume/amount per forecast day).
        forecast_series = []
        for idx, row in pred_df.iterrows():
            forecast_series.append({
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                "open": round(float(row.get("open", 0)), 2),
                "high": round(float(row.get("high", 0)), 2),
                "low": round(float(row.get("low", 0)), 2),
                "close": round(float(row.get("close", 0)), 2),
                "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else None,
                "amount": round(float(row.get("amount", 0)), 2) if pd.notna(row.get("amount")) else None,
            })
        
        logger.info("[RESULT] %s -> trend=%s, return=%s%%", asset_name, trend, ret_pct)
        
        return {
            "symbol": symbol,
            "name": asset_name,
            "current_price": curr_close,
            "projected_close": round(proj_close, 2),
            "support": support,
            "resistance": resistance,
            "return_pct": ret_pct,
            "trend": trend,
            "results_date": results_meta["results_date"],
            "last_week_change_pct": results_meta["last_week_change_pct"],
            "pred_len": pred_len,
            "forecast_series": forecast_series,
        }
        
    except Exception as e:
        logger.error("[ERROR] Prediction failed for %s: %s", symbol, e, exc_info=True)
        return None
    finally:
        if norm_device.startswith("cuda") and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass


def _prepare_batch_inputs(
    symbol: str,
    df: pd.DataFrame,
    lookback: int,
    pred_len: int,
) -> tuple[pd.DataFrame, pd.Series, pd.Series] | None:
    """Slice a fetched history frame into the (x_df, x_timestamp, y_timestamp)
    inputs that ``KronosPredictor.predict_batch`` expects.

    Returns None if the frame has fewer than ``lookback`` rows.
    """
    if len(df) < lookback:
        logger.warning("[EXEC] Skipping %s: insufficient data (%d rows)", symbol, len(df))
        return None
    x_df = df.iloc[-lookback:][["open", "high", "low", "close"]].reset_index(drop=True)
    x_timestamp = df.iloc[-lookback:]["timestamps"].reset_index(drop=True)
    last_date = x_timestamp.iloc[-1]
    y_timestamp = pd.Series([last_date + pd.Timedelta(days=i) for i in range(1, pred_len + 1)])
    return x_df, x_timestamp, y_timestamp


def _build_forecast(
    symbol: str,
    x_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    pred_len: int,
) -> dict[str, Any]:
    """Assemble the forecast dict from a single prediction DataFrame."""
    curr_close = round(float(x_df["close"].iloc[-1]), 2)
    proj_close = float(pred_df["close"].iloc[-1])
    support = round(float(pred_df["low"].min()), 2)
    resistance = round(float(pred_df["high"].max()), 2)

    ret_pct = round(((proj_close - curr_close) / curr_close) * 100, 2)
    trend = "Bullish" if ret_pct >= 0.5 else ("Bearish" if ret_pct <= -0.5 else "Neutral")

    asset_name = get_asset_name(symbol)
    results_meta = get_results_metadata(symbol)

    forecast_series = []
    for idx, row in pred_df.iterrows():
        forecast_series.append({
            "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
            "open": round(float(row.get("open", 0)), 2),
            "high": round(float(row.get("high", 0)), 2),
            "low": round(float(row.get("low", 0)), 2),
            "close": round(float(row.get("close", 0)), 2),
            "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else None,
            "amount": round(float(row.get("amount", 0)), 2) if pd.notna(row.get("amount")) else None,
        })

    logger.info("[RESULT] %s -> trend=%s, return=%s%%", asset_name, trend, ret_pct)
    return {
        "symbol": symbol,
        "name": asset_name,
        "current_price": curr_close,
        "projected_close": round(proj_close, 2),
        "support": support,
        "resistance": resistance,
        "return_pct": ret_pct,
        "trend": trend,
        "results_date": results_meta["results_date"],
        "last_week_change_pct": results_meta["last_week_change_pct"],
        "pred_len": pred_len,
        "forecast_series": forecast_series,
    }


def predict_portfolio(
    symbols: list[str],
    lookback: int = 120,
    pred_len: int = 14,
    device: str | None = None,
    progress_callback: callable | None = None,
    on_forecast: callable | None = None,
) -> list[dict[str, Any]]:
    """Generate predictions for a portfolio of stocks.

    Concurrency model (tuned for a 32GB / i7 / RTX 3060 box):
      1. **Parallel fetch** — historical data + metadata are I/O-bound (yfinance),
         so they're fetched on a thread pool sized by ``kronos_fetch_workers``.
      2. **Batched GPU inference** — the fetched sequences are grouped into
         batches of ``kronos_gpu_batch_size`` (default 2) and fed to
         ``KronosPredictor.predict_batch``, which runs all sequences in a single
         forward pass.  This is far more efficient — and safer on a 6GB 3060 —
         than spawning concurrent threads that hammer the same model.
      3. **Parallel explanations** — Ollama calls are local-network I/O, so they
         run on a thread pool sized by ``kronos_explain_workers``.

    Args:
        symbols: List of ticker symbols to predict
        lookback: Number of historical days to use for prediction
        pred_len: Number of days to predict forward
        device: Device for model inference ('cuda', 'cuda:0', 'cpu', or None for auto)
        progress_callback: Optional callback function(current, total, symbol) for progress
        on_forecast: Optional callback function(forecast_dict) called as each forecast
            completes — used by ``run_kronos_with_cache`` for incremental cache
            saving so interrupted runs preserve progress.

    Returns:
        List of prediction dictionaries
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from earnings_engine.config import Settings as _Settings

    settings = _Settings()
    norm_device = _normalize_device(device or getattr(settings, "kronos_device", None))
    logger.info("[INFO] Initializing Kronos predictor on %s for %d stocks", norm_device, len(symbols))

    total = len(symbols)
    completed = 0

    # --- Phase 1: parallel historical-data fetch (I/O-bound) ---
    fetch_workers = max(1, getattr(settings, "kronos_fetch_workers", 8))
    fetched: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=min(fetch_workers, total)) as executor:
        futures = {executor.submit(fetch_historical_data, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1
            try:
                df = future.result()
                if df is not None and len(df) >= lookback:
                    fetched[symbol] = df
                else:
                    logger.warning("  [SKIP] Failed to fetch enough data for %s", symbol)
            except Exception as e:
                logger.warning("  [SKIP] Fetch failed for %s: %s", symbol, e)
            if progress_callback:
                progress_callback(completed, total, symbol)

    if not fetched:
        logger.warning("[DONE] No symbols had sufficient data to predict")
        return []

    # --- Phase 2: batched GPU inference ---
    predictor = _get_kronos_predictor(norm_device)
    if predictor is None:
        logger.error("Kronos library not available for prediction")
        return []

    gpu_batch = max(1, getattr(settings, "kronos_gpu_batch_size", 2))
    ordered_symbols = [s for s in symbols if s in fetched]
    forecasts: list[dict[str, Any]] = []

    for i in range(0, len(ordered_symbols), gpu_batch):
        batch_symbols = ordered_symbols[i:i + gpu_batch]
        batch_inputs = []
        for sym in batch_symbols:
            prepared = _prepare_batch_inputs(sym, fetched[sym], lookback, pred_len)
            if prepared is not None:
                batch_inputs.append((sym, prepared))

        if not batch_inputs:
            continue

        batch_syms = [b[0] for b in batch_inputs]
        x_dfs = [b[1][0] for b in batch_inputs]
        x_ts = [b[1][1] for b in batch_inputs]
        y_ts = [b[1][2] for b in batch_inputs]

        logger.info(
            "[PRED] Running %d-day forecast for %d stocks in one GPU batch (batch=%d)",
            pred_len, len(batch_syms), gpu_batch,
        )
        try:
            pred_dfs = predictor.predict_batch(
                df_list=x_dfs,
                x_timestamp_list=x_ts,
                y_timestamp_list=y_ts,
                pred_len=pred_len,
                T=0.8,
                top_p=0.9,
                sample_count=1,
                verbose=False,
            )
        except Exception as e:
            logger.error("[ERROR] Batch prediction failed for %s: %s", batch_syms, e, exc_info=True)
            # Fall back to per-symbol single prediction for this batch.
            for sym, (x_df, x_ts_i, y_ts_i) in zip(batch_syms, x_dfs, x_ts):
                try:
                    pred_df = predictor.predict(
                        df=x_df, x_timestamp=x_ts_i, y_timestamp=y_ts_i,
                        pred_len=pred_len, T=0.8, top_p=0.9, sample_count=1, verbose=False,
                    )
                    forecasts.append(_build_forecast(sym, x_df, pred_df, pred_len))
                except Exception as e2:
                    logger.error("[ERROR] Single prediction failed for %s: %s", sym, e2)
            continue

        for sym, x_df, pred_df in zip(batch_syms, x_dfs, pred_dfs):
            try:
                forecasts.append(_build_forecast(sym, x_df, pred_df, pred_len))
            except Exception as e:
                logger.error("[ERROR] Building forecast failed for %s: %s", sym, e)

    # Free transient GPU allocations after inference loop
    if norm_device.startswith("cuda") and torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    # --- Phase 3: parallel Ollama explanations (local-network I/O) ---
    explain_workers = max(1, getattr(settings, "kronos_explain_workers", 4))
    with ThreadPoolExecutor(max_workers=min(explain_workers, len(forecasts))) as executor:
        def _explain(fc: dict[str, Any]) -> dict[str, Any]:
            try:
                explanation = generate_local_explanation(
                    fc["name"], fc["current_price"], fc["support"],
                    fc["resistance"], fc["return_pct"], fc["trend"],
                )
                fc["explanation"] = " ".join(explanation.split())
            except Exception as e:
                logger.warning("[EXPLAIN] Failed for %s: %s", fc.get("symbol"), e)
                fc["explanation"] = ""
            return fc

        explained = list(executor.map(_explain, forecasts))

    # Preserve input order and surface progress per completed forecast.
    by_symbol = {fc["symbol"]: fc for fc in explained}
    ordered_forecasts = [by_symbol[s] for s in ordered_symbols if s in by_symbol]
    for idx, fc in enumerate(ordered_forecasts, start=1):
        if on_forecast:
            try:
                on_forecast(fc)
            except Exception as e:
                logger.warning("[ON-FORECAST] callback failed: %s", e)
        logger.info(
            "  [OK] Completed: %s (%s) | Proj Return: %s%%",
            fc["name"], fc["trend"], fc["return_pct"],
        )

    # --- Phase 4: attach the GBM (event-dataset) signal to every forecast ---
    try:
        from earnings_engine.predict import get_gbm_predictions_by_ticker

        gbm = get_gbm_predictions_by_ticker(symbols, settings)
        if not isinstance(gbm, dict) or "error" in gbm:
            logger.warning("[GBM] GBM prediction unavailable: %s", gbm.get("error", "unknown"))
        for fc in ordered_forecasts:
            ticker = fc.get("symbol", fc.get("ticker", ""))
            if isinstance(gbm, dict) and ticker in gbm:
                fc["gbm_prediction"] = gbm[ticker]
            else:
                fc["gbm_prediction"] = None
    except Exception as e:
        logger.warning("[GBM] Failed to attach GBM prediction: %s", e)
        for fc in ordered_forecasts:
            fc["gbm_prediction"] = None

    logger.info("[DONE] Generated %d predictions from %d symbols", len(ordered_forecasts), total)
    return ordered_forecasts


def run_kronos_with_cache(
    tickers: list[str],
    lookback: int = 120,
    pred_len: int = 14,
    device: str | None = None,
    progress_callback: callable | None = None,
    force: bool = False,
    audit: bool = True,
) -> list[dict[str, Any]]:
    """Run Kronos predictions standalone, persisted to the daily prediction cache.

    Uses the same ``prediction_cache`` JSON file that ``upcoming-results`` reads.
    On a cache hit (and not ``force``) the cached Kronos map is returned without
    re-running the model.  On a miss (or ``force``) ``predict_portfolio`` runs
    with the given progress callback, the forecasts are saved to today's cache,
    and — when ``audit=True`` — each forecast is written to the SQLite
    ``kronos_predictions`` audit table so it appears in the dashboard's Kronos
    Audit/Latest tabs.

    When ``audit=True`` and ``force=False``, the SQLite audit trail is also
    consulted per-ticker: predictions that already exist for today are reused,
    and only the genuinely missing tickers are computed via
    ``predict_portfolio`` (so a repeated ``cache-predictions`` on the same day
    is a near no-op, and a partial cache/audit only fills the gaps instead of
    re-running all tickers).
    """
    from earnings_engine.prediction_cache import load_prediction_cache_partial, save_prediction_cache

    reused: dict[str, dict[str, Any]] = {}

    if not force:
        # 1) Reuse whatever per-ticker coverage exists in the daily JSON cache.
        try:
            cached = load_prediction_cache_partial(tickers)
            reused.update(cached.get("kronos") or {})
        except Exception as e:
            logger.warning("[KRONOS-CACHE] Partial cache read failed; continuing: %s", e)

        # 2) Fill remaining gaps from today's SQLite audit trail.
        if audit:
            try:
                from earnings_engine.config import Settings as _Settings
                from earnings_engine.data.predictions import load_predictions_by_date

                settings = _Settings()
                today = datetime.now().strftime("%Y-%m-%d")
                existing = load_predictions_by_date(tickers, today, settings)
                for t in tickers:
                    if t in reused:
                        continue
                    row = existing.get(t)
                    if not row:
                        continue
                    fc = dict(row.get("prediction") or {})
                    # Ensure required keys even if the stored JSON is older.
                    fc.setdefault("symbol", t)
                    fc.setdefault("name", t)
                    fc.setdefault("lookback", lookback)
                    fc.setdefault("pred_len", pred_len)
                    reused[t] = fc
            except Exception as e:
                logger.warning("[KRONOS-AUDIT] Audit-trail lookup failed; continuing: %s", e)

    missing = [t for t in tickers if t not in reused]
    if not missing:
        logger.info(
            "[KRONOS-CACHE] Reusing %d Kronos predictions from cache/audit (no model run)",
            len(reused),
        )
        return [reused[t] for t in tickers if not reused[t].get("failed")]

    logger.info(
        "[KRONOS-CACHE] Reusing %d Kronos predictions from cache/audit; computing %d new",
        len(reused), len(missing),
    )

    # Build the full per-ticker map incrementally as forecasts complete, so an
    # interrupted run preserves all progress in the cache + audit trail.
    full_map = dict(reused)
    new_symbols: set[str] = set()
    audit_store = None
    audit_settings = None
    if audit:
        try:
            from earnings_engine.config import Settings as _Settings
            from earnings_engine.data.predictions import store_prediction
            audit_settings = _Settings()
            audit_store = store_prediction
        except Exception as e:
            logger.warning("[KRONOS-AUDIT] Audit setup failed; audit disabled: %s", e)
            audit = False

    save_counter = {"n": 0}

    def _on_forecast(fc: dict[str, Any]) -> None:
        """Incremental save: cache + audit each forecast as it completes."""
        sym = fc.get("symbol", fc.get("ticker", ""))
        full_map[sym] = fc
        new_symbols.add(sym)
        save_counter["n"] += 1
        # Save to cache every 20 forecasts (batch to avoid excessive file I/O).
        if save_counter["n"] % 20 == 0:
            try:
                save_prediction_cache({t: full_map[t] for t in tickers if t in full_map}, {})
            except Exception as e:
                logger.warning("[KRONOS-CACHE] Incremental save failed: %s", e)
        # Audit each forecast immediately (cheap INSERT).
        if audit and audit_store:
            try:
                payload = dict(fc)
                payload["lookback"] = lookback
                payload["pred_len"] = pred_len
                audit_store(sym, audit_settings, payload)
            except Exception as e:
                logger.warning("[KRONOS-AUDIT] Failed to store audit row for %s: %s", sym, e)

    forecasts = predict_portfolio(
        missing,
        lookback=lookback,
        pred_len=pred_len,
        device=device,
        progress_callback=progress_callback,
        on_forecast=_on_forecast,
    )

    # Cache failed tickers (those that didn't produce a forecast) so they're
    # NOT retried on the next run — avoids an infinite retry loop for stocks
    # with insufficient data, delisted tickers, etc.
    failed_count = 0
    for t in missing:
        if t not in new_symbols:
            full_map[t] = {"symbol": t, "failed": True}
            failed_count += 1

    # Return only successful forecasts (exclude failed markers).
    ordered = [full_map[t] for t in tickers if t in full_map and not full_map[t].get("failed")]

    # Final cache save (includes any remaining forecasts + failed markers).
    try:
        save_prediction_cache({t: full_map[t] for t in tickers if t in full_map}, {})
        logger.info(
            "[KRONOS-CACHE] Saved %d Kronos predictions (%d failed) to daily cache",
            len(ordered), failed_count,
        )
    except Exception as e:
        logger.warning("[KRONOS-CACHE] Failed to save Kronos cache: %s", e)

    return ordered


def run_batch_kronos(
    market: str = "ALL",
    days: int = 14,
    device: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Run batch Kronos predictions for a market universe, watchlist, or upcoming earnings.

    Persists forecasts into SQLite `kronos_predictions` table and returns the list of predictions.
    """
    settings = settings or Settings()
    from earnings_engine.data.universe import load_universe
    from earnings_engine.data.watchlists import get_watchlist

    tickers: list[str] = []
    m_clean = str(market or "ALL").strip().upper()
    if m_clean in ("IN", "NSE_ALL", "ALL"):
        uni = load_universe("NSE_TOP", settings) or load_universe("IN", settings)
        if uni:
            tickers = list(uni[:50])
    elif m_clean in ("NIFTY_50", "NIFTY50", "NSE_TOP"):
        tickers = list(load_universe("NSE_TOP", settings) or load_universe("NIFTY_50", settings) or [])
    elif m_clean in ("NSE_LARGE_CAP", "LARGE_CAP"):
        large_caps = load_universe("NSE_LARGE_CAP", settings) or []
        tickers = list(large_caps[:50])
    else:
        # Check if it is a watchlist name
        wl = get_watchlist(market, settings)
        if wl:
            tickers = list(wl)
        else:
            custom_uni = load_universe(market, settings)
            if custom_uni:
                tickers = list(custom_uni)

    if not tickers:
        # Fallback to default watchlists or price history tickers
        wl = get_watchlist("my_watchlist", settings) or get_watchlist("swing", settings)
        if wl:
            tickers = list(wl)
        else:
            from earnings_engine.data.prices import _connect
            try:
                with _connect(settings) as conn:
                    rows = conn.execute("SELECT DISTINCT ticker FROM price_history LIMIT 30").fetchall()
                    tickers = [r[0] for r in rows if r[0]]
            except Exception:
                tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]

    return run_kronos_with_cache(
        tickers=tickers,
        lookback=120,
        pred_len=days,
        device=device,
        force=False,
        audit=True,
    )


def generate_markdown_report(forecasts: list[dict[str, Any]], output_path: Path) -> None:
    """Generate a Markdown report from predictions."""
    results_watch = []
    for item in forecasts:
        if item.get("results_date"):
            weekly_change = item.get("last_week_change_pct")
            weekly_change_display = f"{weekly_change:+.2f}%" if weekly_change is not None else "—"
            results_watch.append((item["name"], item["symbol"], item["results_date"], weekly_change_display))
    
    md_lines = [
        "# 🇮🇳 Kronos Indian Market Advisory Report\n",
        "**Powered by NeoQuasar/Kronos-base Foundation Model**\n",
        "\n## Results Watch (Next 7 Days)",
        ""
    ]
    
    if results_watch:
        md_lines.extend([
            "| Stock | Symbol | Results Date | 1W Change |",
            "| :--- | :--- | :--- | :---: |"
        ])
        for name, symbol, results_date, weekly_change_display in results_watch:
            md_lines.append(f"| {name} | {symbol} | {results_date} | {weekly_change_display} |")
    else:
        md_lines.append("No major results events flagged in the next 7 days.")
    
    md_lines.extend([
        "",
        "## 14-Day Price Forecasts",
        "",
        "| Asset | Current Price (₹) | Support (₹) | Resistance (₹) | 14-Day Return | Outlook | Results Date | 1W Change |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :---: |"
    ])
    
    for item in forecasts:
        results_date = item.get("results_date") or "—"
        weekly_change = item.get("last_week_change_pct")
        weekly_change_display = f"{weekly_change:+.2f}%" if weekly_change is not None else "—"
        md_lines.append(
            f"| **{item['name']}** ({item['symbol']}) | ₹{item['current_price']:,.2f} | "
            f"₹{item['support']:,.2f} | ₹{item['resistance']:,.2f} | "
            f"**{item['return_pct']}%** | {item['trend']} | {results_date} | {weekly_change_display} |"
        )
    
    md_lines.extend([
        "\n---",
        "*Disclaimer: AI quantitative predictions are generated for educational and analytical purposes. Always consult a certified SEBI registered advisor before real-capital investments.*"
    ])
    
    output_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info("[SAVE] Saved forecast report to %s", output_path)


def generate_html_report(forecasts: list[dict[str, Any]], output_path: Path) -> None:
    """Generate an HTML report from predictions."""
    # Simple HTML report generation
    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Kronos Market Advisory Report</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }",
        ".header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }",
        ".header h1 { margin: 0; font-size: 2em; }",
        ".header p { margin: 10px 0 0 0; opacity: 0.9; }",
        ".forecast-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }",
        ".forecast-card { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }",
        ".forecast-card h2 { margin: 0 0 10px 0; color: #333; }",
        ".symbol { color: #666; font-size: 0.9em; margin-bottom: 15px; }",
        ".metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }",
        ".metric { background: #f8f9fa; padding: 10px; border-radius: 5px; }",
        ".metric-label { font-size: 0.8em; color: #666; }",
        ".metric-value { font-size: 1.2em; font-weight: bold; color: #333; }",
        ".trend-bullish { color: #28a745; }",
        ".trend-bearish { color: #dc3545; }",
        ".trend-neutral { color: #ffc107; }",
        ".explanation { margin-top: 15px; padding: 15px; background: #f8f9fa; border-left: 4px solid #667eea; border-radius: 5px; }",
        ".footer { margin-top: 30px; padding: 20px; text-align: center; color: #666; font-size: 0.9em; }",
        "</style>",
        "</head>",
        "<body>",
        "<div class='header'>",
        "<h1>🇮🇳 Kronos Market Advisory Report</h1>",
        "<p>14-Day Price Predictions Powered by NeoQuasar/Kronos-base</p>",
        f"<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>",
        "</div>",
    ]
    
    if forecasts:
        html_parts.append("<div class='forecast-grid'>")
        for item in forecasts:
            trend_class = f"trend-{item['trend'].lower()}"
            html_parts.append(f"""
            <div class='forecast-card'>
                <h2>{item['name']}</h2>
                <div class='symbol'>{item['symbol']}</div>
                <div class='metrics'>
                    <div class='metric'>
                        <div class='metric-label'>Current Price</div>
                        <div class='metric-value'>₹{item['current_price']:,.2f}</div>
                    </div>
                    <div class='metric'>
                        <div class='metric-label'>Projected Return</div>
                        <div class='metric-value {trend_class}'>{item['return_pct']:+.2f}%</div>
                    </div>
                    <div class='metric'>
                        <div class='metric-label'>Support</div>
                        <div class='metric-value'>₹{item['support']:,.2f}</div>
                    </div>
                    <div class='metric'>
                        <div class='metric-label'>Resistance</div>
                        <div class='metric-value'>₹{item['resistance']:,.2f}</div>
                    </div>
                </div>
                <div class='explanation'>
                    <strong>Analysis:</strong> {item.get('explanation', 'No analysis available.')}
                </div>
            </div>
            """)
        html_parts.append("</div>")
    else:
        html_parts.append("<p>No forecasts generated.</p>")
    
    html_parts.extend([
        "<div class='footer'>",
        "<p><em>Disclaimer: AI quantitative predictions are generated for educational and analytical purposes. "
        "Always consult a certified SEBI registered advisor before real-capital investments.</em></p>",
        "</div>",
        "</body>",
        "</html>"
    ])
    
    output_path.write_text("\n".join(html_parts), encoding="utf-8")
    logger.info("[SAVE] Generated HTML report at %s", output_path)