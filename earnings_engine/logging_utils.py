"""Shared logging helpers, structured formatting, and startup diagnostics for the earnings engine."""

from __future__ import annotations

import importlib
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generator

from earnings_engine.config import PROJECT_ROOT

_ROOT_LOGGER_NAME = "earnings_engine"
_RUN_LOG_FILES: dict[str, Path] = {}
_STARTUP_LOGGED = False

# ANSI Color Codes
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"
ANSI_WHITE = "\033[37m"

ANSI_BRIGHT_RED = "\033[91m"
ANSI_BRIGHT_GREEN = "\033[92m"
ANSI_BRIGHT_YELLOW = "\033[93m"
ANSI_BRIGHT_BLUE = "\033[94m"
ANSI_BRIGHT_MAGENTA = "\033[95m"
ANSI_BRIGHT_CYAN = "\033[96m"
ANSI_BRIGHT_WHITE = "\033[97m"

# Regex to strip ANSI escape codes
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

# Sensitive Data Redaction Patterns
SENSITIVE_PATTERNS = [
    # Bearer tokens in headers or text
    (
        re.compile(r"(?i)\bBearer\s+(?!\*\*\*REDACTED\*\*)([A-Za-z0-9_\-\.]{8,})"),
        r"Bearer ***REDACTED***",
    ),
    # URL query parameters with keys/tokens
    (
        re.compile(
            r"(?i)([?&](?:api[_-]?key|token|auth|secret|password|totp(?:[_-]?secret)?|passcode)=)(?!\*\*\*REDACTED\*\*)([^&\s]+)",
        ),
        r"\1***REDACTED***",
    ),
    # Key=value or key: value (JSON, query, headers, config)
    (
        re.compile(
            r"(?i)\b(api[_-]?key|auth(?:orization)?|token|secret|password|passwd|totp(?:[_-]?secret)?|pin|session[_-]?token|client[_-]?secret|private[_-]?key)\b(['\"]?\s*[:=]\s*['\"]?)(?!(?:Bearer\s+)?\*\*\*REDACTED\*\*\*|%[sdrfba]|%\([^\)]+\)[sdrfba])([^'\"&\s,]+)(['\"]?)",
        ),
        r"\1\2***REDACTED***\4",
    ),
]


def redact_sensitive_data(text: str) -> str:
    """Scrub sensitive keys, passwords, bearer tokens, and credentials from log text."""
    if not text:
        return text
    redacted = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes from string."""
    return ANSI_ESCAPE_RE.sub("", text)


def _supports_color() -> bool:
    """Determine if current console environment supports ANSI colors."""
    if os.getenv("NO_COLOR") or os.getenv("EARNINGS_ENGINE_NO_COLOR", "").lower() in ("true", "1"):
        return False
    if os.getenv("FORCE_COLOR") or os.getenv("CLICOLOR_FORCE", "").lower() in ("true", "1"):
        return True
    if sys.platform == "win32":
        # Windows Terminal, VSCode, ConEmu, Mintty support colors
        if any(os.getenv(k) for k in ("WT_SESSION", "VSCODE_PID", "TERM_PROGRAM", "ANSICON")):
            return True
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts sensitive credentials from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            formatted = record.getMessage()
            redacted = redact_sensitive_data(formatted)
            record.msg = redacted
            record.args = ()
        except Exception:
            if isinstance(record.msg, str):
                record.msg = redact_sensitive_data(record.msg)
        return True


class CategoryTagFormatter(logging.Formatter):
    """Format log lines with timestamp, level, domain category tags, and optional ANSI colors."""

    LEVEL_COLORS = {
        logging.DEBUG: ANSI_DIM + ANSI_WHITE,
        logging.INFO: ANSI_BRIGHT_BLUE,
        logging.WARNING: ANSI_BRIGHT_YELLOW,
        logging.ERROR: ANSI_BRIGHT_RED + ANSI_BOLD,
        logging.CRITICAL: ANSI_BRIGHT_RED + ANSI_BOLD,
    }

    TAG_COLORS = {
        # HTTP
        "[HTTP:IN]": ANSI_BRIGHT_CYAN + ANSI_BOLD,
        "[HTTP:OUT]": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "[HTTP:ERR]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[HTTP:CANCEL]": ANSI_BRIGHT_YELLOW,
        # Schedulers
        "[SCHEDULER:START]": ANSI_BRIGHT_MAGENTA + ANSI_BOLD,
        "[SCHEDULER:DONE]": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "[SCHEDULER:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[SCHEDULER:TICK]": ANSI_MAGENTA,
        "[SCHEDULER]": ANSI_MAGENTA,
        # AI Consensus
        "[CONSENSUS:OUT]": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
        "[CONSENSUS:IN]": ANSI_YELLOW,
        "[CONSENSUS:DONE]": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "[CONSENSUS:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[CONSENSUS]": ANSI_YELLOW,
        # Ingestion & Exchanges
        "[NSE:REQ]": ANSI_BLUE,
        "[NSE:RESP]": ANSI_BRIGHT_BLUE + ANSI_BOLD,
        "[NSE:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[NSE]": ANSI_BLUE,
        "[NSELIB:REQ]": ANSI_BLUE,
        "[NSELIB:RESP]": ANSI_BRIGHT_BLUE + ANSI_BOLD,
        "[NSELIB:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[NSELIB]": ANSI_BLUE,
        "[JUGAAD:REQ]": ANSI_CYAN,
        "[JUGAAD:RESP]": ANSI_BRIGHT_CYAN + ANSI_BOLD,
        "[JUGAAD:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[JUGAAD]": ANSI_CYAN,
        "[YF:REQ]": ANSI_YELLOW,
        "[YF:RESP]": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
        "[YF:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[YF]": ANSI_YELLOW,
        "[INGEST]": ANSI_BLUE,
        # Cloud Sync
        "[TURSO:START]": ANSI_BRIGHT_CYAN + ANSI_BOLD,
        "[TURSO:DONE]": ANSI_CYAN,
        "[TURSO:FAIL]": ANSI_BRIGHT_RED,
        "[TURSO]": ANSI_CYAN,
        # Brokers
        "[BROKER:AUTH]": ANSI_BRIGHT_GREEN,
        "[BROKER:ORDER]": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "[BROKER]": ANSI_GREEN,
        # Models & Radar
        "[KRONOS]": ANSI_BRIGHT_MAGENTA,
        "[BREAKOUT]": ANSI_CYAN,
        "[WORKFLOW:START]": ANSI_BRIGHT_WHITE + ANSI_BOLD,
        "[WORKFLOW:DONE]": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "[WORKFLOW:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[WORKFLOW]": ANSI_WHITE,
        "[BUILD:START]": ANSI_BRIGHT_WHITE + ANSI_BOLD,
        "[BUILD:DONE]": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "[BUILD:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[JOB:START]": ANSI_BRIGHT_MAGENTA + ANSI_BOLD,
        "[JOB:DONE]": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "[JOB:FAIL]": ANSI_BRIGHT_RED + ANSI_BOLD,
        "[BATCH]": ANSI_DIM + ANSI_CYAN,
    }

    def __init__(self, use_color: bool = True, colorize: bool | None = None) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")
        if colorize is not None:
            self.use_color = bool(colorize)
        else:
            self.use_color = bool(use_color) and _supports_color()

    def format(self, record: logging.LogRecord) -> str:
        asctime = self.formatTime(record, self.datefmt)
        levelname = record.levelname
        msg = record.getMessage()

        # Handle formatting with or without color
        if self.use_color:
            level_color = self.LEVEL_COLORS.get(record.levelno, ANSI_WHITE)
            level_str = f"{level_color}{levelname:<5}{ANSI_RESET}"

            # Apply tag coloring if message begins with a known tag
            colored_msg = msg
            for tag, tag_color in self.TAG_COLORS.items():
                if tag in colored_msg:
                    colored_msg = colored_msg.replace(tag, f"{tag_color}{tag}{ANSI_RESET}")
                    break

            name_str = f"{ANSI_DIM}{record.name}{ANSI_RESET}"
            formatted = f"{ANSI_DIM}{asctime}{ANSI_RESET} {level_str} {name_str}: {colored_msg}"
        else:
            clean_msg = strip_ansi(msg)
            formatted = f"{asctime} {levelname:<5} {record.name}: {clean_msg}"

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                formatted += "\n" + (record.exc_text if not self.use_color else f"{ANSI_RED}{record.exc_text}{ANSI_RESET}")

        return formatted


class BatchProgressLogger:
    """Emits clean milestone updates during bulk iterations to prevent N-log console spam."""

    def __init__(
        self,
        total: int = 1,
        operation: str = "Processing",
        task_name: str | None = None,
        name: str | None = None,
        category: str = "BATCH",
        unit: str = "items",
        logger: logging.Logger | Any = None,
        milestones: list[int] | None = None,
        min_interval_seconds: float = 3.0,
    ) -> None:
        self.total = max(1, total)
        self.task_name = name or task_name or operation
        self.category = category
        self.unit = unit
        self.logger = logger or logging.getLogger(_ROOT_LOGGER_NAME)
        self.milestones = milestones or [20, 40, 60, 80, 100]
        self.min_interval = min_interval_seconds

        self.current = 0
        self.success_count = 0
        self.fail_count = 0
        self.start_time = time.perf_counter()
        self.last_log_time = self.start_time
        self.last_milestone_logged = 0

    def update(
        self,
        step: int = 1,
        success: bool = True,
        item_label: str = "",
        force: bool = False,
    ) -> None:
        """Advance progress and emit milestone log if threshold crossed or interval elapsed."""
        self.current += step
        if success:
            self.success_count += step
        else:
            self.fail_count += step

        now = time.perf_counter()
        pct = min(100, int((self.current / self.total) * 100))
        elapsed = max(0.001, now - self.start_time)
        rate = self.current / elapsed
        remaining = max(0, self.total - self.current)
        eta_s = remaining / rate if rate > 0 else 0.0

        crossed_milestone = None
        for m in sorted(self.milestones):
            if pct >= m > self.last_milestone_logged:
                crossed_milestone = m
                break

        time_elapsed = (now - self.last_log_time) >= self.min_interval
        is_final = self.current >= self.total

        if crossed_milestone or (time_elapsed and pct != self.last_milestone_logged) or force or is_final:
            if crossed_milestone:
                self.last_milestone_logged = crossed_milestone
            self.last_log_time = now

            extra_info = f" -> {item_label}" if item_label else ""
            fail_info = f" (failures: {self.fail_count})" if self.fail_count > 0 else ""
            self.logger.info(
                "[%s] %s: %d%% (%d/%d %s) [%.1f/s, elapsed: %.1fs, ETA: %.1fs]%s%s",
                self.category,
                self.task_name,
                pct,
                self.current,
                self.total,
                self.unit,
                rate,
                elapsed,
                eta_s,
                fail_info,
                extra_info,
            )

    def finish(self, summary: str = "") -> None:
        """Log the final summary upon completion."""
        total_time = time.perf_counter() - self.start_time
        summary_str = f" - {summary}" if summary else ""
        fail_str = f", {self.fail_count} failed" if self.fail_count > 0 else ""
        self.logger.info(
            "[%s] Completed %s: %d %s completed in %.2fs (%.1f/s, %d ok%s)%s",
            self.category,
            self.task_name,
            self.current,
            self.unit,
            total_time,
            (self.current / max(0.001, total_time)),
            self.success_count,
            fail_str,
            summary_str,
        )


class LogThrottle:
    """Rate-limits repeated log messages to prevent console spam."""

    def __init__(
        self,
        cooldown_seconds: float = 60.0,
        interval_seconds: float | None = None,
        logger: logging.Logger | Any = None,
    ) -> None:
        self._cooldown = interval_seconds if interval_seconds is not None else cooldown_seconds
        self.logger = logger
        self._last_logged: dict[str, float] = {}
        self._suppressed_counts: dict[str, int] = {}

    def should_log(self, key: str) -> tuple[bool, int]:
        """Return (should_log, suppressed_count_since_last_log)."""
        now = time.monotonic()
        last_time = self._last_logged.get(key, 0.0)
        if (now - last_time) >= self._cooldown:
            suppressed = self._suppressed_counts.get(key, 0)
            self._last_logged[key] = now
            self._suppressed_counts[key] = 0
            return True, suppressed

        self._suppressed_counts[key] = self._suppressed_counts.get(key, 0) + 1
        return False, self._suppressed_counts[key]

    def log_throttled(self, key: str, level: int, msg: str, *args: Any, **kwargs: Any) -> bool:
        """Log message if throttle period has passed; otherwise track suppressed count."""
        should, suppressed = self.should_log(key)
        if should:
            log = self.logger or logging.getLogger(_ROOT_LOGGER_NAME)
            supp_msg = f" (suppressed {suppressed} repeated messages)" if suppressed > 0 else ""
            if args:
                formatted_msg = (msg % args) + supp_msg
                log.info(formatted_msg) if level == logging.INFO else log.error(formatted_msg)
            else:
                log.info(f"{msg}{supp_msg}") if level == logging.INFO else log.error(f"{msg}{supp_msg}")
            return True
        return False


@contextmanager
def workflow_span(
    name: str,
    category: str = "WORKFLOW",
    logger: logging.Logger | Any = None,
    metadata: dict[str, Any] | None = None,
    log_start: bool = True,
    **kwargs: Any,
) -> Generator[dict[str, Any], None, None]:
    """Context manager that times and logs execution spans with clean start/done/fail tags."""
    log = logger or logging.getLogger(_ROOT_LOGGER_NAME)
    meta_ctx = metadata.copy() if metadata else {}
    meta_ctx.update(kwargs)
    start_time = time.perf_counter()

    start_details = []
    if "total_items" in meta_ctx:
        start_details.append(f"{meta_ctx['total_items']} items")
    for k, v in meta_ctx.items():
        if k not in ("total_items", "summary", "items_processed"):
            start_details.append(f"{k}={v}")

    detail_str = f" ({', '.join(start_details)})" if start_details else ""
    if log_start:
        log.info("[%s:START] Starting %s%s...", category, name, detail_str)

    try:
        yield meta_ctx
        elapsed = time.perf_counter() - start_time
        done_details = []
        if "items_processed" in meta_ctx:
            done_details.append(f"{meta_ctx['items_processed']} items processed")
        if "summary" in meta_ctx and meta_ctx["summary"]:
            done_details.append(str(meta_ctx["summary"]))
        for k, v in meta_ctx.items():
            if k not in ("total_items", "summary", "items_processed") and k not in kwargs:
                done_details.append(f"{k}={v}")

        done_str = f" ({', '.join(done_details)})" if done_details else ""
        log.info("[%s:DONE] Finished %s in %.2fs%s", category, name, elapsed, done_str)
    except Exception as exc:
        elapsed = time.perf_counter() - start_time
        log.error("[%s:FAIL] Failed %s after %.2fs: %s", category, name, elapsed, exc, exc_info=True)
        raise


def _get_run_log_file(base_dir: Path) -> Path | None:
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


class ErrorLedgerLoggingHandler(logging.Handler):
    """Logging handler that captures ERROR and CRITICAL logs to the active error stream & ledger."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("earnings_engine.data.error_ledger"):
            return
        try:
            from earnings_engine.data.error_ledger import append_to_error_stream, record_error

            stack_trace = None
            if record.exc_info:
                import traceback
                stack_trace = "".join(traceback.format_exception(*record.exc_info))

            now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
            msg = record.getMessage()
            err_type = f"{record.name}.{record.levelname}"

            if "No earnings dates found, symbol may be delisted" in msg:
                return

            append_to_error_stream({
                "timestamp": now_iso,
                "level": record.levelname,
                "logger": record.name,
                "error_type": err_type,
                "message": msg,
                "stack_trace": stack_trace,
                "source_file": record.pathname,
                "line_no": record.lineno,
            })

            record_error(
                error_type=err_type,
                message=msg,
                stack_trace=stack_trace,
                source_file=record.pathname,
                line_no=record.lineno,
            )
        except Exception:
            pass


class SafeStreamHandler(logging.StreamHandler):
    """Safe stream handler that suppresses stream closed or broken pipe errors."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.stream is None or getattr(self.stream, "closed", False):
                return
            super().emit(record)
        except (ValueError, OSError):
            pass


def setup_logger(name: str = "earnings_engine", base_dir: Path | None = None) -> logging.Logger:
    """Create and return a logger configured with category formatters, sensitive data filtering, and file outputs."""
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

    # Attach sensitive data filter
    sensitive_filter = SensitiveDataFilter()
    root_logger.addFilter(sensitive_filter)

    # Ensure stdout encoding safe on Windows
    try:
        if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # Stream handler (stdout) with colorized category formatter
    stream_handler = SafeStreamHandler(sys.stdout)
    stream_formatter = CategoryTagFormatter(use_color=True)
    stream_handler.setFormatter(stream_formatter)
    stream_handler.addFilter(sensitive_filter)
    root_logger.addHandler(stream_handler)

    # Error ledger handler captures ERROR/CRITICAL logs
    error_handler = ErrorLedgerLoggingHandler()
    error_handler.addFilter(sensitive_filter)
    root_logger.addHandler(error_handler)

    # Optional file handler (plain text, ANSI codes stripped)
    if log_file is not None:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_formatter = CategoryTagFormatter(use_color=False)
            file_handler.setFormatter(file_formatter)
            file_handler.addFilter(sensitive_filter)
            root_logger.addHandler(file_handler)
        except (OSError, PermissionError):
            pass

    # Ensure error stream handler is also attached to root logger
    top_root = logging.getLogger()
    if not any(isinstance(h, ErrorLedgerLoggingHandler) for h in top_root.handlers):
        top_root.addHandler(ErrorLedgerLoggingHandler())

    canonical_name = name if name.startswith("earnings_engine") or name == "" else f"earnings_engine.{name}"
    logger = logging.getLogger(canonical_name)
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

    turso_url = os.getenv("TURSO_DATABASE_URL", "").strip()
    turso_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    is_cloud_db = bool(turso_url and turso_token)
    from earnings_engine.data.db import is_server_environment, measure_db_latencies
    if is_server_environment() and is_cloud_db:
        db_mode_desc = f"LibSQL Cloud ({turso_url})"
    elif is_cloud_db:
        db_mode_desc = "Local SQLite (Fast Local Execution + Upstream Turso Sync)"
    else:
        db_mode_desc = "Local SQLite (Pure offline mode)"

    db_latencies = measure_db_latencies()
    sqlite_lat_ms = db_latencies.get("sqlite_ms")
    sqlite_lat_str = f"{sqlite_lat_ms:.2f} ms ({db_latencies.get('sqlite_status', 'Healthy')})" if sqlite_lat_ms is not None else f"Error ({db_latencies.get('sqlite_status')})"

    turso_lat_ms = db_latencies.get("turso_ms")
    if turso_lat_ms is not None:
        turso_lat_str = f"{turso_lat_ms:.2f} ms ({db_latencies.get('turso_status', 'Connected')})"
    elif is_cloud_db:
        turso_lat_str = f"Error ({db_latencies.get('turso_status')})"
    else:
        turso_lat_str = "[UNSET] (Local offline mode)"

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    email_enabled = os.getenv("EARNINGS_ENGINE_EMAIL_ENABLED", "false").strip().lower() == "true"
    data_dir = os.getenv("EARNINGS_ENGINE_DATA_DIR", "./data")

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

    torch_device_desc = "CPU"
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "CUDA"
            torch_device_desc = f"GPU: {gpu_name} (CUDA {torch.version.cuda})"
    except Exception:
        pass

    lines = [
        "",
        "=" * 78,
        "🚀 EARNINGS ENGINE STARTUP & ENVIRONMENT DIAGNOSTICS",
        "=" * 78,
        "🗄️  DATABASE CONNECTION & LATENCY:",
        f"    • Mode:                  {db_mode_desc}",
        f"    • Local SQLite Latency:  {sqlite_lat_str}",
        f"    • Turso Cloud Latency:   {turso_lat_str}",
        f"    • Turso URL:             {turso_url if turso_url else '[UNSET] (Falling back to local SQLite)'}",
        f"    • Turso Auth Token:      {'[SET] (' + turso_token[:12] + '...)' if turso_token else '[UNSET]'}",
        f"    • Data Directory:        {data_dir}",
        "",
        "⚙️  AI & EXTERNAL INTEGRATIONS CONFIG:",
        f"    • OPENROUTER_API_KEY:    {'[SET] (Multi-model consensus enabled)' if openrouter_key else '[MISSING] (Consensus will use rule-based fallback)'}",
        f"    • Email Alerts:          {'[ENABLED] ' + os.getenv('EARNINGS_ENGINE_EMAIL_TO', '') if email_enabled else '[DISABLED] (EARNINGS_ENGINE_EMAIL_ENABLED=false)'}",
        f"    • ML Inference Device:   {torch_device_desc}",
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
