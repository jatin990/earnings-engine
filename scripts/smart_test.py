"""Smart Test Runner: Discovers modified source files from git and runs only relevant tests."""
import subprocess
import sys
from pathlib import Path

# Mapping of source modules to related test files
MODULE_TEST_MAP = {
    "migrations": ["tests/test_migrations.py"],
    "ticker_audit": ["tests/test_recalculate_audit.py"],
    "recalculate_api": ["tests/test_recalculate_audit.py"],
    "universe": ["tests/test_universe.py", "tests/test_migrations.py"],
    "names": ["tests/test_migrations.py"],
    "swing_ranges": ["tests/test_swing_ranges.py"],
    "market_context": ["tests/test_recalculate_audit.py", "tests/test_swing_ranges.py"],
    "dashboard_api": ["tests/test_swing_ranges.py", "tests/test_recalculate_audit.py"],
    "server": ["tests/test_recalculate_audit.py", "tests/test_swing_ranges.py"],
    "prices": ["tests/test_recalculate_audit.py", "tests/test_swing_ranges.py"],
    "earnings": ["tests/test_recalculate_audit.py"],
    "config": ["tests/test_config_api.py"],
}


def get_modified_files() -> list[str]:
    """Get list of changed files from git status and diff against HEAD."""
    files = set()
    try:
        # Check untracked and modified working directory files
        status_out = subprocess.check_output(["git", "status", "--porcelain"], text=True)
        for line in status_out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                files.add(parts[1].replace("\\", "/"))
    except Exception:
        pass

    try:
        # Check diff against HEAD
        diff_out = subprocess.check_output(["git", "diff", "--name-only", "HEAD~1"], text=True)
        for line in diff_out.splitlines():
            if line.strip():
                files.add(line.strip().replace("\\", "/"))
    except Exception:
        pass

    return list(files)


def select_test_files(modified_files: list[str]) -> list[str]:
    """Resolve modified files into a deduplicated list of test files."""
    selected_tests = set()

    for path in modified_files:
        p = path.lower().replace("\\", "/")
        if p.startswith("tests/") and p.endswith(".py"):
            filename = Path(p).name
            if filename.startswith("test_"):
                selected_tests.add(p)
            elif filename == "conftest.py":
                # Conftest changes affect all tests -> trigger all existing tests
                all_tests = [str(f.as_posix()) for f in Path("tests").glob("test_*.py")]
                return sorted(all_tests)
            continue

        for module_name, test_paths in MODULE_TEST_MAP.items():
            if module_name in p:
                for t in test_paths:
                    if Path(t).exists():
                        selected_tests.add(t)

    return sorted(t for t in selected_tests if Path(t).exists())


def main():
    args = sys.argv[1:]
    if "--all" in args or "-a" in args:
        print("[SMART-TEST] Running full regression test suite...")
        cmd = [sys.executable, "-m", "pytest", "-v"]
        return subprocess.run(cmd).returncode

    modified = get_modified_files()
    matched_tests = select_test_files(modified)

    if not matched_tests:
        print("[SMART-TEST] No module-specific test mapping found for current diffs. Running full test suite...")
        cmd = [sys.executable, "-m", "pytest", "-v"]
        return subprocess.run(cmd).returncode

    print(f"[SMART-TEST] Selected {len(matched_tests)} test file(s) based on your changes:")
    for t in matched_tests:
        print(f"   * {t}")

    cmd = [sys.executable, "-m", "pytest"] + matched_tests + ["-v"] + [a for a in args if a not in ("--all", "-a")]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
