#!/usr/bin/env bash
# Retry git push after rebase when another dashboard workflow landed first.
# Fails the job if the push never succeeds (a failed push + successful rebase
# must not report green).
set -euo pipefail
pushed=0
for i in 1 2 3 4 5; do
  if git push; then
    pushed=1
    break
  fi
  echo "Push rejected (another workflow likely pushed first) -- rebasing and retrying ($i)..."
  if ! git pull --rebase origin main; then
    echo "ERROR: Rebase conflict occurred. Conflicting files:" >&2
    git diff --name-only --diff-filter=U >&2 || true
    git status --short >&2 || true
    git rebase --abort 2>/dev/null || true
    exit 1
  fi
done
if [ "$pushed" != "1" ]; then
  echo "ERROR: git push did not succeed after 5 attempts" >&2
  exit 1
fi
