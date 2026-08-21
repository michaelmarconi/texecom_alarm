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

Python 3.12. App package lives in `texecom_alarm/texecom-alarm-app/`
(Supervisor App folder is `texecom_alarm/`).

```bash
cd texecom_alarm/texecom-alarm-app
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest --cov=texecom_alarm --cov-fail-under=90
bandit -r src -ll
pip-audit
```

CI runs the same checks on pull requests to `main`. Tests must use the
in-repo FakePanel stand-in — do not point CI or unit tests at a live panel.

Local Home Assistant boot (optional): see [docs/run.md](docs/run.md).

Every PR to `main` must raise SemVer in the same diff:

```bash
./scripts/sync-version.sh bump patch "why this is a new add-on version"
```

See [docs/addon-versioning.md](docs/addon-versioning.md).

## Pull requests

`main` only moves via pull request, including for the maintainer. Direct
pushes are blocked.

Use the PR template. Keep the diff small, match existing style, and say how you
tested (CI-only vs a live panel).

## Conduct

Participation is covered by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
