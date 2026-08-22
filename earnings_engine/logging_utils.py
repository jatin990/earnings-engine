"""Shared logging helpers for the earnings engine."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from earnings_engine.config import PROJECT_ROOT

_ROOT_LOGGER_NAME = "earnings_engine"
_RUN_LOG_FILES: dict[str, Path] = {}


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
            # Fallback to /tmp/logs if base_dir is read-only
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

