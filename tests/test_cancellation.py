"""Unit and integration tests for backend request and task cancellation."""
import asyncio
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.cancellation import (
    CancellationToken,
    CancellationManager,
    cancellation_manager,
)
from earnings_engine.api.server import app


def test_cancellation_token_basic():
    token = CancellationToken("test_task_1")
    assert not token.is_cancelled
    assert token.cancel_reason == ""

    callback_called = []
    token.register_callback(lambda reason: callback_called.append(reason))

    # Trigger cancellation
    token.cancel("User aborted computation")
    assert token.is_cancelled
    assert token.cancel_reason == "User aborted computation"
    assert len(callback_called) == 1
    assert callback_called[0] == "User aborted computation"

    # check_cancelled raises CancelledError
    with pytest.raises(asyncio.CancelledError) as exc_info:
        token.check_cancelled()
    assert "User aborted computation" in str(exc_info.value)


def test_cancellation_manager_lifecycle():
    manager = CancellationManager(ttl_seconds=10)
    tok = manager.register("req_abc_123")
    assert tok is not None
    assert tok.token_id == "req_abc_123"

    # Fetch token
    fetched = manager.get_token("req_abc_123")
    assert fetched is tok

    # Cancel token via manager
    success = manager.cancel("req_abc_123", reason="Frontend button clicked")
    assert success is True
    assert tok.is_cancelled
    assert tok.cancel_reason == "Frontend button clicked"

    # Cancelling unknown returns False
    assert manager.cancel("non_existent") is False

    # Unregister
    manager.unregister("req_abc_123")
    assert manager.get_token("req_abc_123") is None


def test_cancel_task_api_endpoints():
    client = TestClient(app)

    # 1. Register a task token
    req_id = "test_fe_req_9988"
    token = cancellation_manager.register(req_id)
    assert not token.is_cancelled

    # 2. Call cancel endpoint
    resp = client.post(f"/api/v1/tasks/{req_id}/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["cancelled"] is True
    assert data["task_id"] == req_id
    assert token.is_cancelled

    # 3. Call generic cancel endpoint
    req_id_2 = "test_fe_req_7766"
    token_2 = cancellation_manager.register(req_id_2)
    assert not token_2.is_cancelled

    resp_2 = client.post("/api/v1/tasks/cancel", json={"request_id": req_id_2, "reason": "Tab switched"})
    assert resp_2.status_code == 200
    data_2 = resp_2.json()
    assert data_2["success"] is True
    assert data_2["cancelled"] is True
    assert token_2.is_cancelled
    assert token_2.cancel_reason == "Tab switched"
