"""API endpoints for dashboard customization, theme preferences, and local .env management."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from earnings_engine.config import PROJECT_ROOT, Settings
from earnings_engine.data.db import get_db_connection, is_server_environment
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.config_api")

ENV_PATH = PROJECT_ROOT / ".env"

# Known secret key patterns for masking
SECRET_KEY_PATTERNS = {"KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL"}


class EnvVarPayload(BaseModel):
    key: str = Field(..., description="Environment variable name")
    value: str = Field(..., description="Environment variable value")


class UIPreferencesPayload(BaseModel):
    tab_visibility: dict[str, bool] = Field(default_factory=dict)
    theme: str = Field(default="obsidian")
    custom_colors: dict[str, str] = Field(default_factory=dict)


def _is_secret_key(key: str) -> bool:
    """Return True if the key name implies sensitive/credential data."""
    k = key.upper()
    return any(pat in k for pat in SECRET_KEY_PATTERNS)


def _mask_value(val: str) -> str:
    """Mask a secret string (e.g. sk-or-*** -> sk-or...xyz)."""
    if not val:
        return ""
    if len(val) <= 6:
        return "******"
    return val[:4] + "*" * (min(len(val) - 8, 12)) + val[-4:]


def get_env_config() -> dict[str, Any]:
    """Retrieve environment variables categorized for the control center."""
    is_local = not is_server_environment()
    env_vars: list[dict[str, Any]] = []
    known_keys: set[str] = set()

    # Read .env file directly if it exists
    if ENV_PATH.exists():
        try:
            content = ENV_PATH.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    known_keys.add(k)
                    is_sec = _is_secret_key(k)
                    env_vars.append({
                        "key": k,
                        "value": v,
                        "masked_value": _mask_value(v) if is_sec else v,
                        "is_secret": is_sec,
                        "category": _categorize_key(k),
                        "source": ".env file",
                    })
        except Exception as e:
            logger.warning("Failed to read .env file: %s", e)

    # Also capture custom test or standard keys from os.environ
    for k, v in os.environ.items():
        if k not in known_keys and (k.startswith("TEST_") or k.startswith("EARNINGS_") or k.startswith("TURSO_") or k.startswith("OPENROUTER_") or k in ("PORT", "HOST", "ENV")):
            is_sec = _is_secret_key(k)
            env_vars.append({
                "key": k,
                "value": v,
                "masked_value": _mask_value(v) if is_sec else v,
                "is_secret": is_sec,
                "category": _categorize_key(k),
                "source": "process environment",
            })

    return {
        "is_local": is_local,
        "env_path": str(ENV_PATH),
        "env_vars": env_vars,
    }


def _categorize_key(key: str) -> str:
    """Categorize environment variable for organized UI display."""
    k = key.upper()
    if "TURSO" in k or "DATABASE" in k or "DB" in k:
        return "Database & Cloud"
    if "OPENROUTER" in k or "DEEPSEEK" in k or "AI" in k or "ANTHROPIC" in k or "GEMINI" in k:
        return "AI & Model APIs"
    if "SMTP" in k or "EMAIL" in k or "ALERT" in k:
        return "Notifications & Alerts"
    if "MARKET" in k or "NSE" in k or "HISTORY" in k or "CACHE" in k:
        return "Market Engine & Cache"
    return "System & Config"


def save_env_var(payload: EnvVarPayload) -> dict[str, Any]:
    """Create or update an environment variable in local .env."""
    if is_server_environment():
        raise HTTPException(
            status_code=403,
            detail="Environment variable editing is only permitted in local environments for security.",
        )

    key = payload.key.strip()
    # Validate key name format (alphanumeric + underscore)
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        raise HTTPException(status_code=400, detail="Invalid environment variable name format.")

    val = payload.value.strip()
    updated = False
    lines = []

    if ENV_PATH.exists():
        try:
            content = ENV_PATH.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
                    lines.append(f"{key}={val}")
                    updated = True
                else:
                    lines.append(line)
        except Exception as e:
            logger.warning("Error reading .env during write: %s", e)

    if not updated:
        lines.append(f"{key}={val}")

    try:
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.environ[key] = val
        logger.info("Updated environment variable %s in .env", key)
    except Exception as e:
        logger.error("Failed writing to .env: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed writing to .env: {e}")

    return {"success": True, "key": key, "value": val}


def delete_env_var(key: str) -> dict[str, Any]:
    """Delete an environment variable from local .env."""
    if is_server_environment():
        raise HTTPException(
            status_code=403,
            detail="Environment variable editing is only permitted in local environments.",
        )

    key = key.strip()
    if not ENV_PATH.exists():
        return {"success": True, "key": key}

    lines = []
    try:
        content = ENV_PATH.read_text(encoding="utf-8")
        for line in content.splitlines():
            if not (line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} =")):
                lines.append(line)
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if key in os.environ:
            del os.environ[key]
    except Exception as e:
        logger.error("Failed removing key from .env: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed removing key from .env: {e}")

    return {"success": True, "key": key}


def get_ui_preferences(settings: Settings | None = None) -> dict[str, Any]:
    """Load persisted UI preferences from SQLite/Turso."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ui_preferences (
                id TEXT PRIMARY KEY,
                preferences_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        row = conn.execute("SELECT preferences_json FROM ui_preferences WHERE id = 'default'").fetchone()

    if not row or not row[0]:
        return {
            "tab_visibility": {},
            "theme": "obsidian",
            "custom_colors": {},
        }

    try:
        return json.loads(row[0])
    except Exception:
        return {
            "tab_visibility": {},
            "theme": "obsidian",
            "custom_colors": {},
        }


def save_ui_preferences(payload: UIPreferencesPayload, settings: Settings | None = None) -> dict[str, Any]:
    """Persist UI preferences (tab visibility, theme, custom colors)."""
    settings = settings or Settings()
    data_json = json.dumps(payload.model_dump(), default=str)
    now_str = datetime.now().isoformat(timespec="seconds")
    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ui_preferences (
                id TEXT PRIMARY KEY,
                preferences_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO ui_preferences (id, preferences_json, updated_at) VALUES ('default', ?, ?)",
            (data_json, now_str),
        )
        conn.commit()

    return {"success": True, "preferences": payload.model_dump()}
