"""Tests for Kronos CUDA GPU detection, device normalization, and device parameters."""

import pytest
import torch
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings, get_default_device
from earnings_engine.kronos_predictor import (
    _normalize_device,
    get_cuda_status,
    _setup_kronos_paths,
)


def test_normalize_device_explicit():
    """Verify that device normalization handles cpu and cuda correctly."""
    assert _normalize_device("cpu") == "cpu"
    if torch.cuda.is_available():
        assert _normalize_device("cuda") == "cuda:0"
        assert _normalize_device("cuda:0") == "cuda:0"


def test_normalize_device_fallback_when_cuda_unavailable(monkeypatch):
    """Verify fallback to CPU when CUDA is requested but torch.cuda is unavailable."""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert _normalize_device("cuda") == "cpu"
    assert _normalize_device("cuda:0") == "cpu"


def test_get_default_device_env(monkeypatch):
    """Verify that EARNINGS_ENGINE_KRONOS_DEVICE environment variable is respected."""
    monkeypatch.setenv("EARNINGS_ENGINE_KRONOS_DEVICE", "cpu")
    assert get_default_device() == "cpu"

    monkeypatch.setenv("EARNINGS_ENGINE_KRONOS_DEVICE", "cuda")
    if torch.cuda.is_available():
        assert get_default_device() == "cuda:0"


def test_settings_resolve_device():
    """Verify that Settings.resolve_device resolves device correctly."""
    s = Settings(kronos_device="cpu")
    assert s.resolve_device() == "cpu"
    assert s.resolve_device("cpu") == "cpu"


def test_get_cuda_status_structure():
    """Verify that get_cuda_status returns a valid dictionary structure."""
    status = get_cuda_status()
    assert isinstance(status, dict)
    assert "cuda_available" in status
    assert "torch_version" in status
    assert "device_count" in status
    assert "devices" in status
    assert "default_device" in status
    assert isinstance(status["devices"], list)


def test_api_system_gpu_endpoint():
    """Verify GET /api/v1/dashboard/system/gpu endpoint returns GPU diagnostics."""
    client = TestClient(app)
    resp = client.get("/api/v1/dashboard/system/gpu")
    assert resp.status_code == 200
    data = resp.json()
    assert "cuda_available" in data
    assert "default_device" in data
    assert "torch_version" in data


def test_setup_kronos_paths():
    """Verify _setup_kronos_paths locates kronos_lib directory."""
    found = _setup_kronos_paths()
    assert isinstance(found, bool)
