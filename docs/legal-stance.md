# Legal stance — protocol interoperability

**Status:** Project position statement (not legal advice)  
**Related:** [Protocol overview](protocol-overview.md) · [Protocol reference](protocol-reference.md) · RISK-008 in [analysis](analysis.md)

This document states how this project treats Texecom Connect / ComIP protocol knowledge and why the public materials look the way they do.

## Short version

This Home Assistant add-on exists so an operator can **interoperate** with a Premier Elite panel they already own, over the local network module the panel exposes.

Protocol behaviour documented and implemented here was obtained by **independent observation** of wire traffic and panel responses on that equipment — not by receiving, copying, or republishing Texecom’s confidential protocol documentation.

This project is **not** affiliated with, endorsed by, or approved by Texecom. Texecom, Premier Elite, ComIP, and Texecom Connect are trademarks of their respective owners.

## What we publish

| Published | Intent |
|-----------|--------|
| Add-on code (MIT) | A bridge from panel TCP session → MQTT discovery for Home Assistant |
| Consumer docs (`README.md`, `DOCS.md`) | How to install and configure the add-on |
| [Protocol overview](protocol-overview.md) + [protocol reference](protocol-reference.md) and spike reports | Living **observational** notes of what this panel did on the wire (explanation + lookup) |
| Architecture / ADRs / specs | Product and engineering decisions for *this* add-on |

We do **not** publish Texecom’s internal protocol manuals, NDA packs, SDK dumps, or verbatim extracts from materials Texecom distributes only under confidentiality.

## How protocol knowledge was obtained

1. **Live capture and probe** against a Premier Elite panel (model/firmware recorded in the protocol overview/reference), using the network path the panel already offers for Connect/ComIP-style clients.
2. **Independent implementation** of a client and tests from those observations (and from this project’s own spikes), rather than importing proprietary Texecom documentation into the tree.
3. **Public prior art** (open-source clients, forum reports) may be **cited for corroboration or contrast**, and is labelled when a fact is not yet independently confirmed on this panel. Citation ≠ copying confidential Texecom documents.

Where a finding has not been confirmed live here, the protocol reference says so.

## What we ask of readers

- Treat the protocol overview and reference as **incomplete, panel-specific, and empirical** — not as an official Texecom specification.
- Do not assume behaviour on other models, firmware, or installations without your own verification.
- If you hold Texecom materials under NDA, **do not** contribute those materials (or close paraphrases of them) into this repository. Contribute only what you can defend as independent observation or your own clean-room work.

## Position toward Texecom

We respect that Texecom may protect confidential documentation and commercial products.

Our aim is lawful **interoperability** with hardware end users already purchased: documenting and implementing the network dialogue that hardware performs when ordinary Connect-class clients talk to it on the LAN.

If Texecom believes something in this repository crosses a line:

1. Prefer a clear, specific notice (what file/passage, and why) over a blanket demand.
2. Contact via [GitHub private vulnerability reporting](https://github.com/michaelmarconi/texecom_alarm/security/advisories/new) (preferred for confidentiality claims) or the maintainer [@michaelmarconi](https://github.com/michaelmarconi).
3. We will review in good faith. Where a concern is about **copied confidential documentation**, that is taken seriously. Where a concern is solely that **independently observed wire behaviour** was written down for interoperability, we will say so and discuss.

Nothing in this document waives any rights, admits liability, or claims that reverse engineering is risk-free in every jurisdiction. **This is not legal advice.** Maintainers and users should take their own counsel if they need certainty.

## Licence boundary

- **Code and project-authored documentation** (other than third-party marks and the Flaticon icon credit): see root [`LICENSE`](../LICENSE) (MIT).
- **Add-on icon:** Flaticon terms; see Credits in `README.md` / `DOCS.md`.
- **Trademarks:** remain with their owners; use here is referential only.

## Change control

If this stance is updated, bump the date below and keep prior substance visible in git history.

| Date | Note |
|------|------|
| 2026-08-08 | Initial public stance |
