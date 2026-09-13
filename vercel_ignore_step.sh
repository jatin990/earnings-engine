#!/bin/bash

# Vercel Ignored Build Step Script
# Exit code 0 = SKIP build
# Exit code 1 = PROCEED with build

echo "==> Evaluating Vercel Ignored Build Step..."

# 1. Check commit message for skip keywords
COMMIT_MESSAGE=$(git log -1 --pretty=%B)
if echo "$COMMIT_MESSAGE" | grep -qiE '\[skip ci\]|\[skip vercel\]|\[ci skip\]|\[skip-build\]'; then
  echo "[-] Skip keyword found in commit message. Skipping build."
  exit 0
fi

# 2. Check if this is the initial commit or has no parent
if ! git rev-parse --verify HEAD^ >/dev/null 2>&1; then
  echo "[+] Initial commit detected. Proceeding with build."
  exit 1
fi

# 3. Check for changes in production application files
# Only build if api/, earnings_engine/, or dependency/config files changed
PRODUCTION_FILES="api/ earnings_engine/ requirements.txt vercel.json setup.py pyproject.toml"

if git diff HEAD^ HEAD --quiet -- $PRODUCTION_FILES; then
  echo "[-] No production files changed (only docs/tests/scripts/config modified). Skipping build."
  exit 0
else
  echo "[+] Changes detected in production files ($PRODUCTION_FILES). Proceeding with build."
  exit 1
fi
