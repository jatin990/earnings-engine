"""Backward-compatibility facade for Breakout Radar scanner.

All functionality has been decomposed into the domain package
`earnings_engine.data.breakout_scanner`.
"""

from __future__ import annotations

# Re-export entire namespace from the breakout_scanner package
from earnings_engine.data.breakout_scanner import *  # noqa: F401, F403
