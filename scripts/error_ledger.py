#!/usr/bin/env python3
"""CLI utility for scanning, inspecting, and managing the local Error Ledger.

Usage:
    python scripts/error_ledger.py scan       # Scan log files and update ledger
    python scripts/error_ledger.py open       # List open unresolved errors
    python scripts/error_ledger.py summary    # Display error health KPIs
    python scripts/error_ledger.py resolve <id_or_sig> [notes]  # Mark error as resolved
    python scripts/error_ledger.py check      # Pre/post-task health gate (returns non-zero if open errors)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure UTF-8 stdout for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from earnings_engine.config import Settings
from earnings_engine.data.error_ledger import (
    get_error_summary,
    get_open_errors,
    mark_error_resolved,
    scan_log_files,
)


def cmd_scan(settings: Settings) -> None:
    print("🔍 Scanning logs/ directory for errors and exceptions...")
    res = scan_log_files(base_dir=PROJECT_ROOT, settings=settings)
    print(f"✅ Scanned {res['scanned_files']} log file(s).")
    print(f"📊 Found {res['errors_found']} total error instances ({res['newly_recorded']} new unique signatures).")
    print()
    cmd_summary(settings)


def cmd_summary(settings: Settings) -> None:
    s = get_error_summary(settings)
    print("=" * 60)
    print("🐞 ERROR LEDGER HEALTH SUMMARY")
    print("=" * 60)
    print(f"• Unique Error Signatures : {s['total_unique_errors']}")
    print(f"• Open / Unresolved Errors: \033[91m{s['open_errors']}\033[0m" if s['open_errors'] > 0 else f"• Open / Unresolved Errors: \033[92m0 (Clean)\033[0m")
    print(f"• Resolved Errors         : \033[92m{s['resolved_errors']}\033[0m")
    print(f"• Total Log Occurrences   : {s['total_occurrences']}")
    print("=" * 60)

    if s["top_open_errors"]:
        print("\n⚠️ TOP OPEN ERRORS:")
        for idx, err in enumerate(s["top_open_errors"], 1):
            print(f"  [{idx}] ID: {err['id']} ({err['occurrences']}x) - {err['error_type']}")
            print(f"      Msg : {err['message'][:90]}")
            print(f"      Seen: {err['last_seen_at']}")
            print()


def cmd_open(settings: Settings) -> None:
    open_errs = get_open_errors(settings, limit=50)
    if not open_errs:
        print("✅ No open unresolved errors in ledger. Everything is healthy!")
        return

    print(f"\n📋 Found {len(open_errs)} Open Unresolved Error(s):")
    print("-" * 75)
    for err in open_errs:
        print(f"ID        : {err['id']} | Sig: {err['signature']}")
        print(f"Type      : {err['error_type']}")
        print(f"Message   : {err['message']}")
        if err.get("source_file"):
            print(f"Location  : {err['source_file']}:{err.get('line_no', '?')}")
        print(f"Count     : {err['occurrences']} times (Last seen: {err['last_seen_at']})")
        if err.get("stack_trace"):
            trace_preview = "\n".join(err["stack_trace"].strip().splitlines()[-4:])
            print(f"Traceback :\n{trace_preview}")
        print("-" * 75)


def cmd_resolve(identifier: str, notes: str, settings: Settings) -> None:
    if not identifier:
        print("❌ Error: Missing error ID or signature to resolve.")
        sys.exit(1)

    success = mark_error_resolved(identifier, resolution_notes=notes, settings=settings)
    if success:
        print(f"✅ Error '{identifier}' marked as RESOLVED.")
        print(f"📝 Resolution note: {notes}")
    else:
        print(f"❌ Error '{identifier}' not found in ledger.")
        sys.exit(1)


def cmd_check(settings: Settings) -> int:
    """Pre/post-task check gate."""
    # First sync latest log files
    scan_log_files(base_dir=PROJECT_ROOT, settings=settings)
    open_errs = get_open_errors(settings, limit=10)
    
    if not open_errs:
        print("✅ [ERROR-GATE] 0 open errors in ledger. Workspace healthy.")
        return 0
    else:
        print(f"⚠️ [ERROR-GATE] {len(open_errs)} open error(s) detected in logs:")
        for err in open_errs[:5]:
            print(f"  • [{err['id']}] {err['error_type']}: {err['message'][:80]}")
        print("\n👉 Please diagnose and fix these errors or resolve them via:")
        print("   python scripts/error_ledger.py resolve <error_id> '<fix description>'")
        return 1


def main() -> None:
    args = sys.argv[1:]
    settings = Settings()

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    cmd = args[0].lower()
    if cmd == "scan":
        cmd_scan(settings)
    elif cmd == "summary":
        cmd_summary(settings)
    elif cmd == "open":
        cmd_open(settings)
    elif cmd == "resolve":
        err_id = args[1] if len(args) > 1 else ""
        notes = " ".join(args[2:]) if len(args) > 2 else "Resolved by agent task fix"
        cmd_resolve(err_id, notes, settings)
    elif cmd == "check":
        code = cmd_check(settings)
        sys.exit(code)
    else:
        print(f"❌ Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
