# Add-on versioning (local vs release)

Supervisor treats `config.yaml` `version` as the add-on **release id**. This note is the project rule for when that field may change. It is intentionally short — the project is pre-ship.

## When `version` may be bumped

Bump `config.yaml` `version` **only** for an intentional releasable build that should appear as a new add-on release (and, when we publish, as a matching `CHANGELOG.md` entry).

Do **not** bump it:

- mid-task as a Supervisor cache-buster
- so the Configuration tab / schema / translations refresh locally
- for any other local-dev convenience

Inventing release numbers for local reload is forbidden. Use rebuild/reload instead — see [run.md](run.md#refresh-local-add-on-without-a-version-bump).

## Local development

Leave `version` alone while iterating. Rebuild or reload the local add-on so schema, options, and translations pick up; do not invent semver.

## Relationship to `/ship` and CHANGELOG

`/ship` is go-live readiness after docs-ready — it is **not** a licence to invent release trains during ordinary tasks.

**Not decided yet** (stop and ask a human; do not guess):

- when a published release is authorized and who bumps `version` for it
- CHANGELOG cadence and how deeply we follow Keep a Changelog / SemVer for 1.0+
- whether store/update UX requires a bump beyond what this local policy covers

Until those are decided, agents must not silently bump `version` or invent release handbook detail. Point practitioners at this file and ask.
