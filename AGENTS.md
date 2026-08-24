# Earnings Engine Agent Guidelines

## Error Ledger & Self-Healing Protocol
Whenever you work on this repository:
1. **Pre-Task Check**: Check active errors with `python scripts/error_ledger.py open`.
2. **Post-Task Verification**: Run `python scripts/error_ledger.py scan` and `scripts/smart_test.py` to confirm that changes are clean and free of unhandled exceptions.
3. **Resolution Logging**: When you fix a bug, mark it resolved:
   `python scripts/error_ledger.py resolve <error_id> "<explanation of the fix>"`

## Git Commit & Push Protocol
- **Local Commits**: Keep committing changes locally as each feature, fix, or refactor is completed and verified.
- **Push Policy**: Do **not** push to the remote repository after every individual change. Only push once per day after **10:00 PM IST** (or when explicitly commanded by the user).

