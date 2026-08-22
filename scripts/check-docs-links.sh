#!/usr/bin/env bash
# Fail if stale post-flatten DOCS.md links remain (repo-root DOCS.md is gone).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

hits="$(
  {
    git grep -nF 'blob/main/DOCS.md' -- . ':!scripts/check-docs-links.sh' 2>/dev/null || true
    git grep -nF '](../../DOCS.md)' -- . ':!scripts/check-docs-links.sh' 2>/dev/null || true
  } | grep -v '^$' || true
)"

if [[ -n "$hits" ]]; then
  echo "stale DOCS.md links (use texecom_alarm/DOCS.md):" >&2
  echo "$hits" >&2
  exit 1
fi

echo "DOCS.md link check OK"
