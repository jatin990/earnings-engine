"""Shared logging helpers and startup diagnostics for the earnings engine."""

from __future__ import annotations

import importlib
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from earnings_engine.config import PROJECT_ROOT

_ROOT_LOGGER_NAME = "earnings_engine"
_RUN_LOG_FILES: dict[str, Path] = {}
_STARTUP_LOGGED = False


def _get_run_log_file(base_dir: Path) -> Path | None:
    # Disable file logging on Vercel or when explicitly requested
    if os.getenv("VERCEL") == "1" or os.getenv("EARNINGS_ENGINE_DISABLE_FILE_LOGGING", "").lower() in ("true", "1"):
        return None

    base_key = str(base_dir.resolve())
    if base_key not in _RUN_LOG_FILES:
        try:
            log_dir = base_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            _RUN_LOG_FILES[base_key] = log_dir / f"earnings_engine-{stamp}.log"
        except (OSError, PermissionError):
            try:
                tmp_dir = Path("/tmp/logs")
                tmp_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
                _RUN_LOG_FILES[base_key] = tmp_dir / f"earnings_engine-{stamp}.log"
            except (OSError, PermissionError):
                return None
    return _RUN_LOG_FILES.get(base_key)


def setup_logger(name: str = "earnings_engine", base_dir: Path | None = None) -> logging.Logger:
    """Create and return a logger that writes to a shared per-run log file and stdout."""
    root = Path(base_dir) if base_dir is not None else PROJECT_ROOT
    log_file = _get_run_log_file(root)

    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    # Stream handler (stdout) is always enabled for console/serverless logs
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Optional file handler (if file system is writable)
    if log_file is not None:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except (OSError, PermissionError):
            pass

    root_logger.propagate = False

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = True
    return logger


def get_logger(name: str = "earnings_engine", base_dir: Path | None = None) -> logging.Logger:
    """Return a configured logger instance."""
    return setup_logger(name, base_dir=base_dir)


def check_module_status(module_name: str) -> tuple[bool, str]:
    """Check if a Python package is installed and return its version or error."""
    try:
        mod = importlib.import_module(module_name)
        ver = getattr(mod, "__version__", "installed")
        return True, str(ver)
    except ImportError:
        return False, "Not Installed"
    except Exception as e:
        return False, f"Load Error: {e}"


def log_startup_diagnostics(target_logger: logging.Logger | None = None) -> None:
    """Audit system environment, database config, and provider dependencies on startup."""
    global _STARTUP_LOGGED
    if _STARTUP_LOGGED:
        return
    _STARTUP_LOGGED = True

    log = target_logger or logging.getLogger(_ROOT_LOGGER_NAME)

    # 1. Database Configuration
    turso_url = os.getenv("TURSO_DATABASE_URL", "").strip()
    turso_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    is_cloud_db = bool(turso_url and turso_token)
    db_mode_desc = f"☁️ LibSQL Cloud ({turso_url})" if is_cloud_db else "📁 Local SQLite (fallback mode)"

    # 2. Key Environment Variables Audit
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    email_enabled = os.getenv("EARNINGS_ENGINE_EMAIL_ENABLED", "false").strip().lower() == "true"
    data_dir = os.getenv("EARNINGS_ENGINE_DATA_DIR", "./data")

    # 3. Dependencies Audit
    modules_to_check = [
        ("yfinance", "Yahoo Finance market data & quotes"),
        ("nselib", "Direct official NSE Bhavcopy / Delivery"),
        ("jugaad_data", "NSE Archives & Option Chain historical data"),
        ("lightgbm", "LightGBM Gradient Boosted ML Models"),
        ("torch", "PyTorch deep learning inference"),
        ("pyotp", "Automated TOTP 2FA for broker execution"),
        ("kiteconnect", "Zerodha Kite Connect broker execution"),
        ("smartapi", "Angel One SmartAPI broker execution"),
        ("dhanhq", "DhanHQ broker execution"),
        ("fyers_apiv3", "Fyers API v3 broker execution"),
    ]

    mod_statuses: list[dict[str, Any]] = []
    for mod_name, desc in modules_to_check:
        ok, detail = check_module_status(mod_name)
        mod_statuses.append({"module": mod_name, "ok": ok, "detail": detail, "description": desc})

    # PyTorch GPU acceleration check
    torch_device_desc = "CPU"
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "CUDA"
            torch_device_desc = f"GPU: {gpu_name} (CUDA {torch.version.cuda})"
    except Exception:
        pass

    # Log startup diagnostic summary
    lines = [
        "",
        "=" * 78,
        "🚀 EARNINGS ENGINE STARTUP & ENVIRONMENT DIAGNOSTICS",
        "=" * 78,
        "🗄️  DATABASE CONNECTION:",
        f"    • Mode:               {db_mode_desc}",
        f"    • Turso URL:          {turso_url if turso_url else '[UNSET] (Falling back to local SQLite)'}",
        f"    • Turso Auth Token:   {'[SET] (' + turso_token[:12] + '...)' if turso_token else '[UNSET]'}",
        f"    • Data Directory:     {data_dir}",
        "",
        "⚙️  AI & EXTERNAL INTEGRATIONS CONFIG:",
        f"    • OPENROUTER_API_KEY: {'[SET] (Multi-model consensus enabled)' if openrouter_key else '[MISSING] (Consensus will use rule-based fallback)'}",
        f"    • Email Alerts:       {'[ENABLED] ' + os.getenv('EARNINGS_ENGINE_EMAIL_TO', '') if email_enabled else '[DISABLED] (EARNINGS_ENGINE_EMAIL_ENABLED=false)'}",
        f"    • ML Inference Device:{torch_device_desc}",
        "",
        "📦  DATA PROVIDERS & MODULES AUDIT:",
    ]

    for m in mod_statuses:
        status_tag = f"✅ [{m['detail']}]" if m["ok"] else "⚠️  [NOT INSTALLED]"
        lines.append(f"    • {m['module']:<14} {status_tag:<22} -> {m['description']}")

    lines.extend([
        "=" * 78,
        "",
    ])

    log.info("\n".join(lines))
