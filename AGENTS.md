# Earnings Engine Agent Guidelines

## Error Ledger & Self-Healing Protocol
Whenever you work on this repository:
1. **Pre-Task Check**: Check active errors with `python scripts/error_ledger.py open`.
2. **Post-Task Verification**: Run `python scripts/error_ledger.py scan` and `scripts/smart_test.py` to confirm that changes are clean and free of unhandled exceptions.
3. **Resolution Logging**: When you fix a bug, mark it resolved:
   `python scripts/error_ledger.py resolve <error_id> "<explanation of the fix>"`
