"""Shared helpers for the API playground scripts."""

from __future__ import annotations

import math
import sys
from typing import Any


# ANSI colors (Windows 10+ supports them natively)
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def heading(title: str) -> None:
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {title}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")


def subheading(title: str) -> None:
    print(f"\n{C.BOLD}{C.YELLOW}--- {title} ---{C.RESET}")


def info(msg: str) -> None:
    print(f"{C.DIM}{msg}{C.RESET}")


def ok(msg: str) -> None:
    print(f"{C.GREEN}✓ {msg}{C.RESET}")


def warn(msg: str) -> None:
    print(f"{C.YELLOW}⚠ {msg}{C.RESET}")


def err(msg: str) -> None:
    print(f"{C.RED}✗ {msg}{C.RESET}")


def fmt_num(value: Any, precision: int = 2) -> str:
    """Safely format a numeric value, returning '—' for None/NaN."""
    try:
        if value is None:
            return "—"
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return "—"
        return f"{f:,.{precision}f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_pct(value: Any) -> str:
    """Safely format a percentage, returning '—' for None/NaN."""
    s = fmt_num(value)
    return "—" if s == "—" else f"{s}%"


def prompt_ticker(default: str = "RELIANCE.NS") -> str:
    """Prompt the user for a ticker symbol, defaulting to a sensible NSE stock."""
    if not sys.stdin.isatty():
        return default
    try:
        value = input(f"{C.BOLD}Ticker (default: {default}): {C.RESET}").strip()
        return value or default
    except (EOFError, KeyboardInterrupt):
        return default


def prompt_yes_no(question: str, default: bool = False) -> bool:
    """Prompt the user for a yes/no answer."""
    if not sys.stdin.isatty():
        return default
    suffix = " [y/N] " if not default else " [Y/n] "
    try:
        value = input(f"{C.BOLD}{question}{suffix}{C.RESET}").strip().lower()
        if not value:
            return default
        return value in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return default


def summarize_predictions(forecasts: list[dict[str, Any]]) -> None:
    """Pretty-print a list of Kronos forecast dicts."""
    if not forecasts:
        warn("No forecasts returned.")
        return
    for item in forecasts:
        trend = item.get("trend", "?")
        color = C.GREEN if trend.lower() == "bullish" else C.RED if trend.lower() == "bearish" else C.YELLOW
        print(
            f"  {C.BOLD}{item.get('symbol', '?')}{C.RESET} "
            f"₹{fmt_num(item.get('current_price'))} "
            f"→ ₹{fmt_num(item.get('resistance'))} (res) / ₹{fmt_num(item.get('support'))} (sup) "
            f"| {color}{item.get('return_pct', 0):+.2f}%{C.RESET} "
            f"| {color}{trend}{C.RESET}"
        )
        if item.get("results_date"):
            info(f"      results: {item['results_date']}")