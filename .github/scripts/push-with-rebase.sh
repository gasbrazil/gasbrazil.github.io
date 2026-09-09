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
  git pull --rebase origin main
done
if [ "$pushed" != "1" ]; then
  echo "ERROR: git push did not succeed after 5 attempts" >&2
  exit 1
fi
