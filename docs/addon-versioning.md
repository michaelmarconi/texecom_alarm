# Add-on versioning

`texecom_alarm/config.yaml` `version` is the Supervisor release id. When it
changes, households see an **Update** and read `CHANGELOG.md`. Bump it only
for notable product changes — not for CI, docs, or Dependabot.

`main` only moves via pull request, including for the maintainer. GitHub does
not edit version files after merge.

## Canonical source

`texecom_alarm/config.yaml` `version` (App folder root under catalogue layout).

Copies (kept in lockstep by `scripts/sync-version.sh`):

- `texecom_alarm/texecom-alarm-app/pyproject.toml` `version`
- `texecom_alarm/texecom-alarm-app/src/texecom_alarm/__init__.py` `__version__`
- Latest dated `## [X.Y.Z]` heading in `texecom_alarm/CHANGELOG.md`
  (`## [Unreleased]` does not count)

## Day to day

Product PRs add bullets under `## [Unreleased]` (Added / Changed / Fixed /
Removed). Docs, CI, and Dependabot skip the changelog unless a household
would care.

CI only checks that the four version locations match
(`./scripts/sync-version.sh check`). It does **not** require a bump.

## Cutting a Supervisor release

When Unreleased has something a household should read:

```bash
./scripts/sync-version.sh bump patch
# or: minor | major
```

That raises SemVer, moves Unreleased notes into `## [X.Y.Z] - date`, and
leaves an empty Unreleased. Do it in the same PR as the product change, or in
a small follow-up release PR — before merge, not after.

After merge, **Tag version** creates `vX.Y.Z` if that tag does not exist.
Builder publishes GHCR for the tag. Same version on `main` again is a no-op.

| Event | Bump `config.yaml`? |
|--------|---------------------|
| User-facing fix or feature | Yes, when you mean to ship it |
| Breaking change | Yes (`major`) |
| Dependabot / CI / docs | No |
| Local rebuild / Configuration refresh | No — use Rebuild; see [run.md](run.md#refresh-local-add-on-without-a-version-bump) |

Optional local check that this PR actually raised SemVer vs `main`:

```bash
./scripts/sync-version.sh require-bump origin/main
```

## Do not

- Hand-edit only one of the four version locations (use the script)
- Put Dependabot or commit subjects in the household changelog
- Open a follow-up “bump after merge” robot PR
- Move or retag an existing `vX.Y.Z`
- Invent a separate Python package version
