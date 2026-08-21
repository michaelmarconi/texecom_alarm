# Definition of Done

<!-- Universal completion bars. Every task inherits this baseline.
     Task-specific acceptance criteria sit on top of these bars. -->

## Build passes
Build succeeds (`pip install -e ".[dev]"` in `texecom_alarm/texecom-alarm-app/` exits 0).

## Tests pass
All automated tests pass (`pytest` in `texecom_alarm/texecom-alarm-app/` exits 0), including
E2E suites that mock the alarm panel — never targeting the live household panel
in CI.

## Coverage ≥ 90%
Line coverage for `texecom_alarm` is at least 90%
(`pytest --cov=texecom_alarm --cov-fail-under=90` exits 0).

## Lint and format clean
`ruff check` and `ruff format --check` pass in `texecom_alarm/texecom-alarm-app/`; the same
checks are enforced on every commit via pre-commit.

## Security scan clean
Dependency and static security scans pass (`pip-audit` and `bandit` in CI exit 0).

## PR approved
Solo workflow: no PR approval required. Merge to `main` only after explicit
in-session practitioner permission — never silent auto-merge.

## Documentation updated
Public Add-on docs stay current with Home Assistant community conventions:
root `README.md` (install/run), `DOCS.md` (Supervisor docs tab — configuration
options fully described), `CHANGELOG.md` for user-visible releases, and
`config.yaml` schema/options kept in sync with documented behaviour.

## Add-on version discipline
Do not bump `config.yaml` `version` mid-task or to reload local Configuration —
follow [addon-versioning.md](addon-versioning.md). Local schema/translation
refresh uses Rebuild (see [run.md](run.md#reload-local-add-on-without-a-version-bump)).
CI sync-check keeps the four version locations in lockstep; SemVer rises
only for a Supervisor release — see [addon-versioning.md](addon-versioning.md).

## Ops tracing
Every panel session lifecycle step (connect, login, enumerate, subscribe,
arm/disarm, resync, reconnect) and MQTT publish/command path is covered by
structured debug logging sufficient to diagnose stability issues from app logs
alone.

## Secrets hygiene
No panel credentials, UDL passwords, or raw packet captures are committed;
`docs/captures/` and secrets stay out of git (see `.gitignore`).
