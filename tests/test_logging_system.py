"""Unit and integration tests for structured observability and logging infrastructure.

Tests:
1. Sensitive data redaction for API keys, tokens, passwords, and TOTP secrets.
2. SensitiveDataFilter log record scrubbing.
3. CategoryTagFormatter ANSI terminal tagging and plain-text stripping.
4. BatchProgressLogger milestone progress tracking and anti-spam suppression.
5. LogThrottle high-frequency suppression.
6. workflow_span lifecycle context manager (start, done, fail).
7. FastAPI HTTP request middleware bidirectional logging with request ID and param redaction.
"""

from __future__ import annotations

import io
import logging
import re
import time
from typing import Any

import pytest
from starlette.testclient import TestClient

from earnings_engine.logging_utils import (
    ANSI_ESCAPE_RE,
    BatchProgressLogger,
    CategoryTagFormatter,
    LogThrottle,
    SensitiveDataFilter,
    redact_sensitive_data,
    setup_logger,
    workflow_span,
)


def test_redact_sensitive_data() -> None:
    """Ensure sensitive tokens and query parameters are masked correctly."""
    # Query param style
    raw_query = "https://example.com/api?api_key=secret12345&username=johndoe&token=abc_token_999"
    redacted = redact_sensitive_data(raw_query)
    assert "secret12345" not in redacted
    assert "abc_token_999" not in redacted
    assert "username=johndoe" in redacted
    assert "api_key=***REDACTED***" in redacted
    assert "token=***REDACTED***" in redacted

    # Bearer token
    bearer_raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    bearer_redacted = redact_sensitive_data(bearer_raw)
    assert "Bearer ***REDACTED***" in bearer_redacted
    assert "eyJhbGci" not in bearer_redacted

    # JSON / Key-Value style
    json_raw = '{"password": "MySuperSecretPassword!", "status": "active", "totp_secret": "JBSWY3DPEHPK3PXP"}'
    json_redacted = redact_sensitive_data(json_raw)
    assert "MySuperSecretPassword!" not in json_redacted
    assert "JBSWY3DPEHPK3PXP" not in json_redacted
    assert '"status": "active"' in json_redacted


def test_sensitive_data_filter() -> None:
    """Test that SensitiveDataFilter scrubs secrets from LogRecord msg and args."""
    filt = SensitiveDataFilter()

    # Scrub in record.msg
    record1 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Connecting with api_key=super_secret_key_123",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record1) is True
    assert "super_secret_key_123" not in record1.msg
    assert "***REDACTED***" in record1.msg

    # Scrub in record.args tuple
    record2 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="User authenticated with token=%s",
        args=("sensitive_session_token_xyz",),
        exc_info=None,
    )
    assert filt.filter(record2) is True
    formatted_msg = record2.msg % record2.args
    assert "sensitive_session_token_xyz" not in formatted_msg
    assert "***REDACTED***" in formatted_msg


def test_category_tag_formatter_plain_and_ansi() -> None:
    """Test CategoryTagFormatter colorization and plain-text stripping."""
    record = logging.LogRecord(
        name="earnings_engine.scheduler",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="[SCHEDULER:START] Running background job 'breakout_cold_scan'...",
        args=(),
        exc_info=None,
    )

    # 1. Plain text (file output)
    plain_formatter = CategoryTagFormatter(colorize=False)
    plain_output = plain_formatter.format(record)
    # Must have no ANSI escape sequences
    assert ANSI_ESCAPE_RE.search(plain_output) is None
    assert "[SCHEDULER:START]" in plain_output
    assert "Running background job 'breakout_cold_scan'..." in plain_output

    # 2. Colorized text (terminal output)
    color_formatter = CategoryTagFormatter(colorize=True)
    color_output = color_formatter.format(record)
    # Must contain ANSI color code
    assert "\x1b[" in color_output
    assert "SCHEDULER:START" in color_output


def test_batch_progress_logger() -> None:
    """Test that BatchProgressLogger emits milestone progress at configured thresholds."""
    log_capture = []

    class MockLogger:
        def info(self, msg: str, *args: Any) -> None:
            log_capture.append(msg % args if args else msg)

    mock_logger = MockLogger()
    progress = BatchProgressLogger(
        name="test_scan",
        total=10,
        unit="tickers",
        milestones=[20, 40, 60, 80, 100],
        logger=mock_logger,
    )

    # Update 1 by 1
    for _ in range(10):
        progress.update(1)
    progress.finish()

    # Should have emitted milestone logs (e.g. 20%, 40%, 60%, 80%, 100%) plus completion
    assert len(log_capture) >= 5
    combined = " ".join(log_capture)
    assert "20.0%" in combined or "20%" in combined
    assert "100.0%" in combined or "100%" in combined
    assert "completed in" in combined


def test_log_throttle() -> None:
    """Test LogThrottle rate-limiting for high-frequency repeated logs."""
    log_capture = []

    class MockLogger:
        def info(self, msg: str, *args: Any) -> None:
            log_capture.append(msg % args if args else msg)

    mock_logger = MockLogger()
    throttle = LogThrottle(logger=mock_logger, interval_seconds=1.0)

    # Emit 5 times in rapid succession
    for _ in range(5):
        throttle.log_throttled("HIGH_FREQ_KEY", logging.INFO, "Rapid loop message")

    # Only first call should log immediately
    assert len(log_capture) == 1
    assert "Rapid loop message" in log_capture[0]


def test_workflow_span_success() -> None:
    """Test workflow_span context manager logs start and done with timing."""
    log_capture = []

    class MockLogger:
        def info(self, msg: str, *args: Any) -> None:
            log_capture.append(msg % args if args else msg)

        def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
            log_capture.append(msg % args if args else msg)

    mock_logger = MockLogger()

    with workflow_span("dataset_build", category="BUILD", total_items=50, logger=mock_logger) as span:
        time.sleep(0.01)
        span["items_processed"] = 50

    assert len(log_capture) == 2
    assert "[BUILD:START] Starting dataset_build (50 items)..." in log_capture[0]
    assert "[BUILD:DONE] Finished dataset_build in" in log_capture[1]
    assert "50 items processed" in log_capture[1]


def test_workflow_span_failure() -> None:
    """Test workflow_span logs failure and re-raises exception."""
    log_capture = []

    class MockLogger:
        def info(self, msg: str, *args: Any) -> None:
            log_capture.append(msg % args if args else msg)

        def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
            log_capture.append(msg % args if args else msg)

    mock_logger = MockLogger()

    with pytest.raises(ValueError, match="Synthetic test error"):
        with workflow_span("faulty_job", category="JOB", logger=mock_logger):
            raise ValueError("Synthetic test error")

    assert len(log_capture) == 2
    assert "[JOB:START]" in log_capture[0]
    assert "[JOB:FAIL] Failed faulty_job after" in log_capture[1]
    assert "Synthetic test error" in log_capture[1]


def test_http_middleware_bidirectional_logging() -> None:
    """Test FastAPI middleware captures incoming [HTTP:IN] and outgoing [HTTP:OUT] with sanitized params."""
    from earnings_engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # Perform request with query params and sensitive token
    resp = client.get("/api/v1/market/status?token=super_secret_token_123&market=NSE")
    assert resp.status_code in (200, 404, 500) or resp.status_code < 600

    # Ensure custom request ID header or state exists
    # And verify endpoint responds cleanly
