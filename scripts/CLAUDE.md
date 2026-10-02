# CLAUDE.md — Operational Scripts (`scripts/`)

> Subsystem guide for maintenance utilities, data auditing, and the Error Ledger self-healing protocol.

---

## 1. Scope & Architecture

The scripts directory contains operational and maintenance CLI scripts for error tracking, data integrity verification, and database diagnostics.

- **Error Ledger**: `scripts/error_ledger.py` (authoritative error tracking and resolution log)
- **Data Audit & Verification**: `scripts/verify_and_sync_all_data.py` (deep data validation and Turso sync)
- **Database Utilities**: `scripts/migrate_*.py`, `scripts/inspect_*.py`

---

## 2. Core Invariants & Rules

### 2.1 Error Ledger Self-Healing Protocol
To maintain zero-error hygiene across all development cycles:
1. **Pre-Task Check**:
   ```bash
   ./.venv/Scripts/python.exe scripts/error_ledger.py open
   ```
2. **Post-Task Verification**:
   ```bash
   ./.venv/Scripts/python.exe scripts/error_ledger.py scan
   ```
   Confirm no unhandled exceptions or new errors were introduced.
3. **Resolution Logging**:
   ```bash
   ./.venv/Scripts/python.exe scripts/error_ledger.py resolve <error_id> "<resolution details>"
   ```

### 2.2 Script Execution Environment
- Always invoke scripts using the virtual environment interpreter with forward slashes (`./.venv/Scripts/python.exe`) to prevent Git Bash path collapsing (`Exit code 127: ..venvScriptspython.exe`):
  ```bash
  ./.venv/Scripts/python.exe scripts/<script_name>.py [args]
  ```
- Scripts must operate non-interactively and exit with standard return codes (`0` for success, non-zero for failures).
