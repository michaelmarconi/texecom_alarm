# Security policy

## Supported versions

Report against current `main`. Pre-1.0 (`0.0.x`) has no older release line to
backport to.

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/michaelmarconi/texecom_alarm/security/advisories/new).

Do **not** open a public issue for:

- Credential leaks (UDL, MQTT, or other secrets)
- A remotely exploitable bug
- A claim that this repository copies Texecom confidential documentation —
  see [docs/legal-stance.md](docs/legal-stance.md)

You should hear back within a few days. If the report is accepted, a fix will
be prepared privately before any public disclosure.

## What to include

- Add-on version (or git commit)
- What an attacker would need (LAN access, MQTT access, …)
- Steps to reproduce, without real passwords or household IPs
