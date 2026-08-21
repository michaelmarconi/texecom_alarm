# Add-on versioning

One SemVer string is the release id. Supervisor, Python packaging, the healthcheck
string, and the changelog all use the same value. Humans do not edit version
numbers by hand.

## Canonical source

`config.yaml` `version` (at the App folder root — today repo root; after catalogue
layout, `texecom_alarm/config.yaml`).

Copies (kept in lockstep by `scripts/sync-version.sh`):

- `texecom-alarm-app/pyproject.toml` `version`
- `texecom-alarm-app/src/texecom_alarm/__init__.py` `__version__`
- Latest `## [X.Y.Z]` heading in `CHANGELOG.md`

## When the version changes

- **On every merge to `main`** (human PRs, Dependabot, anything): GitHub Actions
  patch-bumps (`0.1.0` → `0.1.1` → …), updates the copies, prepends a changelog
  line, and creates git tag `vX.Y.Z`. If that tag already exists, the job fails —
  the same version is never reused.
- **Bootstrap:** if the current canonical version has no tag yet, the workflow
  tags it without bumping (so the first public release can be `0.1.0`).
- **Minor / major:** manual `workflow_dispatch` on `.github/workflows/bump-version.yml`
  with `bump=minor` or `bump=major`.
- **Local rebuild / Configuration refresh:** do **not** bump. Use Rebuild — see
  [run.md](run.md#refresh-local-add-on-without-a-version-bump).

## CI

Pull requests fail if any copy disagrees with `config.yaml`
(`./scripts/sync-version.sh check`).

## Do not

- Hand-edit version strings to reload the local App
- Move or retag an existing `vX.Y.Z`
- Invent a separate Python package version
