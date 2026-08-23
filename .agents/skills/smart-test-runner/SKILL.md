---
name: smart-test-runner
description: Change-aware intelligent test execution, selective test mapping, fail-fast iteration, and milestone full-regression gates. Use when testing code changes efficiently without running redundant tests.
---

# Smart Test Runner Skill

## Overview
Optimizes testing feedback loops by dynamically mapping modified source files to their corresponding test suites, executing targeted unit tests during development, and running full regression suites only at key milestone checkpoints.

---

## 1. Change-to-Test Mapping Rules

When editing files in `earnings_engine/`, execute ONLY the matching test file:

| Changed Source File | Targeted Test Command |
|---|---|
| `earnings_engine/data/migrations.py` | `pytest tests/test_migrations.py -v` |
| `earnings_engine/data/ticker_audit.py` or `recalculate_api.py` | `pytest tests/test_recalculate_audit.py -v` |
| `earnings_engine/data/universe.py` or `names.py` | `pytest tests/test_universe.py tests/test_migrations.py -v` |
| `earnings_engine/data/swing_ranges.py` | `pytest tests/test_swing_ranges.py -v` |
| `earnings_engine/data/market_context.py` | `pytest tests/test_recalculate_audit.py tests/test_swing_ranges.py -v` |
| `earnings_engine/api/server.py` | `pytest tests/test_recalculate_audit.py tests/test_swing_ranges.py -v` |

---

## 2. Iteration Workflow

### A. Rapid Development Loop (During active coding)
Run only the test file related to the active change:
```bash
pytest tests/test_<target>.py -v
```

### B. Debugging Failures (Fail-Fast)
If a test fails, re-run only the failed test and stop immediately on error:
```bash
pytest --lf -x
```

### C. Milestone Checkpoint (Before git commit & push)
Execute the complete test suite once a major feature or bug fix is finished:
```bash
pytest -v
```

---

## 3. Automation Script (`scripts/smart_test.py`)
Run the intelligent test selector:
```bash
python scripts/smart_test.py
```
This script inspects `git status` / `git diff`, extracts modified files, maps them to their respective test suites, and runs only the relevant tests. If no files changed or `--all` is passed, it executes the full test suite.
