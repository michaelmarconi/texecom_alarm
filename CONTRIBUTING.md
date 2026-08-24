# Contributing

Thanks for taking an interest. This add-on talks to a Texecom Premier Elite
panel over the local network and publishes MQTT discovery to Home Assistant.

## First stop

- Bugs, install trouble, and ideas: [open an issue](https://github.com/michaelmarconi/texecom_alarm/issues/new/choose) (templates are required).
- Configuration reference: [DOCS.md](DOCS.md).
- How we treat panel protocol knowledge: [docs/legal-stance.md](docs/legal-stance.md).

Please **never** paste UDL passwords, MQTT passwords, or full household LAN
addresses into issues or pull requests.

## What belongs here

In scope: the panel session, MQTT entities this add-on publishes, and docs for
operators.

Out of scope: household automations, notifications, and HomeKit rules. Those
stay in the operator’s Home Assistant configuration.

## Protocol contributions

Protocol behaviour in this repo is **independently observed** wire traffic, not
Texecom’s confidential documentation.

If you hold Texecom materials under NDA, **do not** contribute those files or
close paraphrases of them. Contribute only what you can defend as independent
observation or your own clean-room work.

## Development

Python 3.12. Package and Supervisor App folder are both under `texecom_alarm/`
(`pyproject.toml`, `src/`, `tests/` next to `config.yaml`).

```bash
python3 -m venv texecom_alarm/.venv
texecom_alarm/.venv/bin/pip install -e "texecom_alarm/[dev]"
./scripts/install-git-hooks.sh

cd texecom_alarm
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest --cov=texecom_alarm --cov-fail-under=90
.venv/bin/bandit -r src -ll
.venv/bin/pip-audit
```

The git hook runs Ruff on `texecom_alarm/` before each commit. Use
`./scripts/install-git-hooks.sh` (a repo-relative wrapper). Do **not** run
`pre-commit install` — that hard-codes the venv’s absolute path and breaks when
the directory is moved or renamed. Linked git worktrees share that hook and
the primary `texecom_alarm/.venv`; they do not need a second venv.

CI runs the same checks on pull requests to `main`. Tests must use the
in-repo FakePanel stand-in — do not point CI or unit tests at a live panel.

Local Home Assistant boot (optional): see [docs/run.md](docs/run.md).

`config.yaml` `version` is the Supervisor release. Bump it only when households
should see an **Update** (notable product change). Docs, CI, and Dependabot
PRs leave it alone. Product notes go under `## [Unreleased]` in
`texecom_alarm/CHANGELOG.md` until you cut a release:

```bash
./scripts/sync-version.sh bump patch
```

See [docs/addon-versioning.md](docs/addon-versioning.md).

## Pull requests

Outside contributors change `main` via pull request. Direct pushes are
blocked except for the maintainer.

Use the PR template. Keep the diff small, match existing style, and say how you
tested (CI-only vs a live panel).

## Conduct

Participation is covered by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
