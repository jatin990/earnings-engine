"""Unit tests for the dashboard Control Center and local env manager API."""
import os
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.api.config_api import (
    get_env_config,
    save_env_var,
    delete_env_var,
    get_ui_preferences,
    save_ui_preferences,
    EnvVarPayload,
    UIPreferencesPayload,
)


@pytest.fixture
def test_client():
    return TestClient(app)


def test_get_env_config_returns_categorized_variables():
    """Verify get_env_config returns categorized environment variables."""
    os.environ["TEST_CUSTOM_KEY"] = "custom_test_value"
    os.environ["TEST_SECRET_TOKEN"] = "secret123456789"

    config = get_env_config()
    assert "is_local" in config
    assert isinstance(config["env_vars"], list)

    keys = {v["key"] for v in config["env_vars"]}
    assert "TEST_CUSTOM_KEY" in keys or "TEST_SECRET_TOKEN" in keys


def test_save_and_delete_env_var_local(tmp_path, monkeypatch):
    """Test creating and deleting an environment variable in local mode."""
    test_env_file = tmp_path / ".env"
    monkeypatch.setattr("earnings_engine.api.config_api.ENV_PATH", test_env_file)
    monkeypatch.setattr("earnings_engine.api.config_api.is_server_environment", lambda: False)

    # Save new variable
    payload = EnvVarPayload(key="MY_TEST_API_KEY", value="super-secret-token-12345")
    res = save_env_var(payload)
    assert res["success"] is True
    assert res["key"] == "MY_TEST_API_KEY"
    assert "MY_TEST_API_KEY=super-secret-token-12345" in test_env_file.read_text(encoding="utf-8")
    assert os.getenv("MY_TEST_API_KEY") == "super-secret-token-12345"

    # Delete variable
    del_res = delete_env_var("MY_TEST_API_KEY")
    assert del_res["success"] is True
    assert "MY_TEST_API_KEY" not in test_env_file.read_text(encoding="utf-8")
    assert os.getenv("MY_TEST_API_KEY") is None


def test_ui_preferences_persistence(temp_settings):
    """Test saving and retrieving UI tab visibility and theme customizer preferences."""
    payload = UIPreferencesPayload(
        tab_visibility={"results": True, "scanner": False, "swing": True},
        theme="amethyst",
        custom_colors={"--bg": "#1e102d", "--accent": "#a855f7"}
    )
    save_res = save_ui_preferences(payload, settings=temp_settings)
    assert save_res["success"] is True

    loaded = get_ui_preferences(settings=temp_settings)
    assert loaded["theme"] == "amethyst"
    assert loaded["tab_visibility"]["scanner"] is False
    assert loaded["tab_visibility"]["results"] is True
    assert loaded["custom_colors"]["--accent"] == "#a855f7"


def test_config_api_endpoints(test_client, tmp_path, monkeypatch):
    """Test HTTP API endpoints for control center."""
    test_env_file = tmp_path / ".env"
    monkeypatch.setattr("earnings_engine.api.config_api.ENV_PATH", test_env_file)
    monkeypatch.setattr("earnings_engine.api.config_api.is_server_environment", lambda: False)

    # 1. GET /api/v1/config/env
    r1 = test_client.get("/api/v1/config/env")
    assert r1.status_code == 200
    assert "env_vars" in r1.json()

    # 2. POST /api/v1/config/env
    r2 = test_client.post("/api/v1/config/env", json={"key": "TEST_VAR_HTTP", "value": "http_val_123"})
    assert r2.status_code == 200
    assert r2.json()["success"] is True

    # 3. GET /api/v1/config/ui-preferences
    r3 = test_client.get("/api/v1/config/ui-preferences")
    assert r3.status_code == 200

    # 4. POST /api/v1/config/ui-preferences
    r4 = test_client.post("/api/v1/config/ui-preferences", json={
        "tab_visibility": {"results": True, "buydip": False},
        "theme": "sapphire",
        "custom_colors": {"--accent": "#06b6d4"}
    })
    assert r4.status_code == 200
    assert r4.json()["success"] is True
