#!/usr/bin/env bash
# Single SemVer: config.yaml is canonical; copies stay in lockstep.
# Usage:
#   ./scripts/sync-version.sh check              # exit 1 if copies drift (CI)
#   ./scripts/sync-version.sh require-bump [ref] # exit 1 if canonical equals ref (default origin/main)
#   ./scripts/sync-version.sh sync               # write copies from canonical
#   ./scripts/sync-version.sh bump patch|minor|major [changelog-body]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Canonical path: app folder after catalogue layout, else repo root.
if [[ -f texecom_alarm/config.yaml ]]; then
  CONFIG=texecom_alarm/config.yaml
else
  CONFIG=config.yaml
fi

PYPROJECT=texecom-alarm-app/pyproject.toml
if [[ -f texecom_alarm/texecom-alarm-app/pyproject.toml ]]; then
  PYPROJECT=texecom_alarm/texecom-alarm-app/pyproject.toml
fi

INIT=texecom-alarm-app/src/texecom_alarm/__init__.py
if [[ -f texecom_alarm/texecom-alarm-app/src/texecom_alarm/__init__.py ]]; then
  INIT=texecom_alarm/texecom-alarm-app/src/texecom_alarm/__init__.py
fi

CHANGELOG=CHANGELOG.md
if [[ -f texecom_alarm/CHANGELOG.md ]]; then
  CHANGELOG=texecom_alarm/CHANGELOG.md
fi

read_canonical() {
  # version: "0.1.0" or version: 0.1.0
  sed -nE 's/^version:[[:space:]]*"?([0-9]+\.[0-9]+\.[0-9]+)"?.*/\1/p' "$CONFIG" | head -1
}

read_pyproject() {
  sed -nE 's/^version[[:space:]]*=[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' "$PYPROJECT" | head -1
}

read_init() {
  sed -nE 's/^__version__[[:space:]]*=[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' "$INIT" | head -1
}

read_changelog_latest() {
  sed -nE 's/^## \[([0-9]+\.[0-9]+\.[0-9]+)\].*/\1/p' "$CHANGELOG" | head -1
}

write_all() {
  local v="$1"
  # config.yaml
  if grep -qE '^version:[[:space:]]*"' "$CONFIG"; then
    sed -i -E "s/^version:[[:space:]]*\"[0-9]+\.[0-9]+\.[0-9]+\"/version: \"$v\"/" "$CONFIG"
  else
    sed -i -E "s/^version:[[:space:]]*[0-9]+\.[0-9]+\.[0-9]+/version: \"$v\"/" "$CONFIG"
  fi
  # pyproject.toml
  sed -i -E "s/^version[[:space:]]*=[[:space:]]*\"[0-9]+\.[0-9]+\.[0-9]+\"/version = \"$v\"/" "$PYPROJECT"
  # __init__.py
  sed -i -E "s/^__version__[[:space:]]*=[[:space:]]*\"[0-9]+\.[0-9]+\.[0-9]+\"/__version__ = \"$v\"/" "$INIT"
}

bump_semver() {
  local v="$1" kind="$2"
  local major minor patch
  IFS=. read -r major minor patch <<<"$v"
  case "$kind" in
    patch) patch=$((patch + 1)) ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    major) major=$((major + 1)); minor=0; patch=0 ;;
    *) echo "Unknown bump kind: $kind (use patch|minor|major)" >&2; exit 2 ;;
  esac
  echo "${major}.${minor}.${patch}"
}

prepend_changelog() {
  local v="$1" body="$2" date
  date="$(date -u +%Y-%m-%d)"
  local tmp
  tmp="$(mktemp)"
  {
    # Keep header through the SemVer blurb, then insert new section.
    awk -v ver="$v" -v d="$date" -v body="$body" '
      BEGIN { inserted=0 }
      /^## \[/ && !inserted {
        print "## [" ver "] - " d
        print ""
        print "### Changed"
        print ""
        print "- " body
        print ""
        inserted=1
      }
      { print }
    ' "$CHANGELOG" >"$tmp"
    mv "$tmp" "$CHANGELOG"
  }
}

cmd="${1:-}"
case "$cmd" in
  check)
    canon="$(read_canonical)"
    [[ -n "$canon" ]] || { echo "No version in $CONFIG" >&2; exit 1; }
    py="$(read_pyproject)"
    init="$(read_init)"
    cl="$(read_changelog_latest)"
    ok=1
    if [[ "$py" != "$canon" ]]; then
      echo "pyproject.toml version $py != canonical $canon" >&2
      ok=0
    fi
    if [[ "$init" != "$canon" ]]; then
      echo "__init__.py version $init != canonical $canon" >&2
      ok=0
    fi
    if [[ "$cl" != "$canon" ]]; then
      echo "CHANGELOG latest $cl != canonical $canon" >&2
      ok=0
    fi
    if [[ "$ok" -ne 1 ]]; then
      exit 1
    fi
    echo "version sync ok: $canon"
    ;;
  require-bump)
    canon="$(read_canonical)"
    [[ -n "$canon" ]] || { echo "No version in $CONFIG" >&2; exit 1; }
    base_ref="${2:-origin/main}"
    if ! git rev-parse --verify "$base_ref" >/dev/null 2>&1; then
      echo "Cannot resolve $base_ref — fetch main before require-bump" >&2
      exit 1
    fi
    base="$(git show "${base_ref}:${CONFIG}" 2>/dev/null | sed -nE 's/^version:[[:space:]]*"?([0-9]+\.[0-9]+\.[0-9]+)"?.*/\1/p' | head -1)"
    if [[ -z "$base" ]]; then
      echo "No version at ${base_ref}:${CONFIG}" >&2
      exit 1
    fi
    if [[ "$canon" == "$base" ]]; then
      echo "Version ${canon} is unchanged from ${base_ref}." >&2
      echo "Bump in this PR before merge: ./scripts/sync-version.sh bump patch|minor|major \"why\"" >&2
      exit 1
    fi
    echo "version bump ok: ${base} -> ${canon}"
    ;;
  sync)
    canon="$(read_canonical)"
    [[ -n "$canon" ]] || { echo "No version in $CONFIG" >&2; exit 1; }
    write_all "$canon"
    # Ensure changelog heading matches (do not invent body on sync alone).
    cl="$(read_changelog_latest)"
    if [[ "$cl" != "$canon" ]]; then
      echo "CHANGELOG latest is $cl; expected $canon — fix CHANGELOG or run bump" >&2
      exit 1
    fi
    echo "synced copies to $canon"
    ;;
  bump)
    kind="${2:-patch}"
    body="${3:-Automated version bump}"
    canon="$(read_canonical)"
    [[ -n "$canon" ]] || { echo "No version in $CONFIG" >&2; exit 1; }
    next="$(bump_semver "$canon" "$kind")"
    write_all "$next"
    prepend_changelog "$next" "$body"
    echo "$next"
    ;;
  *)
    echo "Usage: $0 check|require-bump [ref]|sync|bump patch|minor|major [changelog-body]" >&2
    exit 2
    ;;
esac
