# Local Error Ledger & Auto-Healing Rule

## Mandatory Workflow for Agent Tasks

To maintain system integrity and eliminate lingering application bugs, every coding turn MUST follow this pre-task and post-task protocol:

### 1. Pre-Task Error Inspection
Before starting work on a user request:
- Run `python scripts/error_ledger.py open` or check the ledger for any open runtime exceptions.
- If there are unresolved high-priority bugs directly impacting the requested area, diagnose and fix them as part of your execution plan.

### 2. Post-Task Error Scan & Verification Gate
After making code changes or running tests:
- Execute `python scripts/error_ledger.py scan` to ingest any newly generated logs.
- Verify that your changes did not produce any new runtime errors.
- If you resolved a previous error, mark it resolved in the ledger:
  ```bash
  python scripts/error_ledger.py resolve <error_id> "<description of what was fixed>"
  ```
- Run `python scripts/error_ledger.py check` to ensure the health gate passes with 0 open blocking errors.

### 3. Log Cleanliness
- Unhandled 500 errors, SQL syntax/column mismatches, and null pointer exceptions must never be ignored or left unresolved in production logs.
