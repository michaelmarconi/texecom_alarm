# Add-on versioning

One SemVer string is the release id. Supervisor, Python packaging, the
healthcheck string, and the changelog all use the same value.

The version that lands on `main` is already the release number. Nothing on
GitHub edits version files after merge. `main` itself only moves via pull
request — including for the maintainer.

## Canonical source

`texecom_alarm/config.yaml` `version` (App folder root under catalogue layout).

Copies (kept in lockstep by `scripts/sync-version.sh`):

- `texecom_alarm/texecom-alarm-app/pyproject.toml` `version`
- `texecom_alarm/texecom-alarm-app/src/texecom_alarm/__init__.py` `__version__`
- Latest `## [X.Y.Z]` heading in `texecom_alarm/CHANGELOG.md`

## When the version changes

Bump **in the pull request**, before merge:

```bash
./scripts/sync-version.sh bump patch "why this is a new add-on version"
# or: minor | major
```

CI on PRs to `main` fails if the canonical version still equals `main`
(`./scripts/sync-version.sh require-bump`). Copies must also match
(`./scripts/sync-version.sh check`).

After merge, **Tag version** creates `vX.Y.Z` if that tag does not exist. It
does not bump. Builder publishes GHCR for the tag.

| Event | Bump in the PR? |
|--------|-----------------|
| User-facing fix or feature | Yes (`patch` or `minor`) |
| Breaking change | Yes (`major`) |
| Dependabot | Yes — a workflow patch-bumps **on that PR** so CI can pass |
| Local rebuild / Configuration refresh | No — use Rebuild; see [run.md](run.md#refresh-local-add-on-without-a-version-bump) |

## Do not

- Hand-edit only one of the four version locations (use the script)
- Open a follow-up “bump after merge” PR
- Move or retag an existing `vX.Y.Z`
- Invent a separate Python package version
