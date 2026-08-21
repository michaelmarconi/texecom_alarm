## What

<!-- 1–3 sentences. Link the issue if there is one. -->

## How you tested

- [ ] CI / local tests in `texecom-alarm-app/` (`ruff`, `pytest`)
- [ ] Live panel (say model/firmware if so)

## Checks

- [ ] No UDL passwords, MQTT passwords, or household LAN addresses in the diff
- [ ] No Texecom confidential / NDA protocol documents (or close paraphrases) — see [legal stance](../docs/legal-stance.md)
- [ ] Household automations / notifications stay in Home Assistant, not this add-on
- [ ] Supervisor release: version bumped (`./scripts/sync-version.sh bump …`) — or notable notes under `## [Unreleased]`. Skip both for docs / CI / Dependabot
