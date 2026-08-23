"""Cooperative cancellation tokens and ASGI client disconnect monitoring for backend tasks.

Allows front-end client aborts (AbortController, window close, tab switch, or explicit cancel API calls)
to immediately terminate long-running data aggregations, multi-model predictions, and database queries.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable, Optional
from fastapi import Request
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.cancellation")


class CancellationToken:
    """Thread-safe and asyncio-aware cooperative cancellation token."""

    def __init__(self, token_id: str):
        self.token_id = token_id
        self._cancelled = False
        self._reason: str = ""
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[str], Any]] = []
        self._event = threading.Event()
        self.created_at = time.time()

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @property
    def cancel_reason(self) -> str:
        with self._lock:
            return self._reason

    def cancel(self, reason: str = "Client aborted request") -> None:
        """Mark token as cancelled and invoke all registered callbacks."""
        callbacks_to_run = []
        with self._lock:
            if self._cancelled:
                return
            self._cancelled = True
            self._reason = reason
            self._event.set()
            callbacks_to_run = list(self._callbacks)

        logger.info(
            "CancellationToken [%s] CANCELLED: %s",
            self.token_id,
            reason,
        )

        for cb in callbacks_to_run:
            try:
                cb(reason)
            except Exception as e:
                logger.debug("Error in cancellation callback for token %s: %s", self.token_id, e)

    def register_callback(self, callback: Callable[[str], Any]) -> None:
        """Register a callback to be invoked immediately upon cancellation."""
        with self._lock:
            if self._cancelled:
                reason = self._reason
            else:
                self._callbacks.append(callback)
                return
        try:
            callback(reason)
        except Exception as e:
            logger.debug("Error running immediate cancellation callback: %s", e)

    def check_cancelled(self) -> None:
        """Raise asyncio.CancelledError if the token has been cancelled."""
        with self._lock:
            if self._cancelled:
                raise asyncio.CancelledError(f"Task {self.token_id} cancelled: {self._reason}")

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for cancellation event with optional timeout."""
        return self._event.wait(timeout=timeout)


class CancellationManager:
    """Global registry of active request and task cancellation tokens with automatic TTL cleanup."""

    def __init__(self, ttl_seconds: float = 3600.0):
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds

    def register(self, token_id: str) -> CancellationToken:
        """Create or retrieve a cancellation token for the given request/task ID."""
        self._cleanup_stale()
        with self._lock:
            if token_id in self._tokens:
                return self._tokens[token_id]
            token = CancellationToken(token_id)
            self._tokens[token_id] = token
            return token

    def cancel(self, token_id: str, reason: str = "Explicit client cancel API call") -> bool:
        """Cancel a registered token by ID."""
        with self._lock:
            token = self._tokens.get(token_id)
        if token:
            token.cancel(reason)
            return True
        logger.debug("CancellationManager: token [%s] not found (already finished or invalid)", token_id)
        return False

    def get_token(self, token_id: str) -> Optional[CancellationToken]:
        """Retrieve active token by ID if registered."""
        with self._lock:
            return self._tokens.get(token_id)

    def unregister(self, token_id: str) -> None:
        """Remove a token after request completion."""
        with self._lock:
            self._tokens.pop(token_id, None)

    def _cleanup_stale(self) -> None:
        """Evict expired tokens to prevent memory growth."""
        now = time.time()
        with self._lock:
            stale_keys = [
                k for k, tok in self._tokens.items()
                if now - tok.created_at > self._ttl_seconds
            ]
            for k in stale_keys:
                self._tokens.pop(k, None)


# Global singleton instance
cancellation_manager = CancellationManager()


async def monitor_disconnect(request: Request, token: CancellationToken) -> None:
    """Asynchronous coroutine that polls for HTTP client disconnects."""
    try:
        while not token.is_cancelled:
            if await request.is_disconnected():
                token.cancel("Client disconnected from HTTP connection")
                break
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug("Error in monitor_disconnect: %s", e)
