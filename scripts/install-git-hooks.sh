#!/usr/bin/env bash
# Copy the repo-relative pre-commit wrapper into this clone's .git/hooks.
# Usage: ./scripts/install-git-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DIR="$(git -C "$ROOT" rev-parse --git-path hooks)"
mkdir -p "$HOOK_DIR"
cp "$ROOT/scripts/git-hooks/pre-commit" "$HOOK_DIR/pre-commit"
chmod +x "$HOOK_DIR/pre-commit"
echo "Installed ${HOOK_DIR}/pre-commit"
