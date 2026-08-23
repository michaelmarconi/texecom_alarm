#!/usr/bin/env bash
# Install the repo-relative pre-commit wrapper into this clone's .git/hooks.
# Worktrees share that hooks dir, so one install covers them all.
# Usage: ./scripts/install-git-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/git-hooks/pre-commit"
HOOK_DIR="$(git -C "$ROOT" rev-parse --git-path hooks)"
if [[ "$HOOK_DIR" != /* ]]; then
  HOOK_DIR="$ROOT/$HOOK_DIR"
fi
mkdir -p "$HOOK_DIR"

# Relative symlink so the clone can move and the installed hook cannot drift
# from scripts/git-hooks/pre-commit (a copy would go stale).
rel="$(python3 -c 'import os, sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$SRC" "$HOOK_DIR")"
ln -sfn "$rel" "$HOOK_DIR/pre-commit"
# Git requires the hook to be executable; some filesystems do not copy mode
# through a symlink, so chmod the source.
chmod +x "$SRC"
echo "Installed ${HOOK_DIR}/pre-commit -> ${rel}"
