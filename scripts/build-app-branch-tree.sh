#!/usr/bin/env bash
# Assemble the thin Supervisor store tree (allowlisted catalogue paths only).
# Usage:
#   ./scripts/build-app-branch-tree.sh <dest-dir>
# Exits non-zero if the assembled tree fails allowlist / safety assertions.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-}"

if [[ -z "$DEST" ]]; then
  echo "usage: $0 <dest-dir>" >&2
  exit 2
fi

if [[ -e "$DEST" ]]; then
  rm -rf "$DEST"
fi
mkdir -p "$DEST"

for path in LICENSE README.md repository.yaml texecom_alarm; do
  if [[ ! -e "$REPO_ROOT/$path" ]]; then
    echo "missing required path: $path" >&2
    exit 1
  fi
  cp -a "$REPO_ROOT/$path" "$DEST/"
done

# Top-level must be exactly the allowlist (sorted compare).
mapfile -t top < <(find "$DEST" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
expected=(LICENSE README.md repository.yaml texecom_alarm)
if [[ "${top[*]}" != "${expected[*]}" ]]; then
  echo "top-level mismatch:" >&2
  echo "  got:      ${top[*]}" >&2
  echo "  expected: ${expected[*]}" >&2
  exit 1
fi

if [[ -e "$DEST/backlog" || -e "$DEST/docs" ]]; then
  echo "forbidden path present under DEST (backlog or docs)" >&2
  exit 1
fi

# Supervisor scans **/config.yml — none outside the App folder.
while IFS= read -r -d '' cfg; do
  rel="${cfg#"$DEST"/}"
  case "$rel" in
    texecom_alarm/*) ;;
    *)
      echo "stray config.yml outside texecom_alarm/: $rel" >&2
      exit 1
      ;;
  esac
done < <(find "$DEST" -name 'config.yml' -print0 2>/dev/null || true)

for required in texecom_alarm/config.yaml texecom_alarm/DOCS.md; do
  if [[ ! -f "$DEST/$required" ]]; then
    echo "missing required file: $required" >&2
    exit 1
  fi
done

echo "app branch tree OK at $DEST"
