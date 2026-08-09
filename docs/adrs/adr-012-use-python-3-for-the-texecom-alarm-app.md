# ADR-012: Use Python 3 for the Texecom Alarm App

**Status:** Accepted ✅  
**Date:** 2026-08-10  

## Overview

**Background:** The project ships a long-running Home Assistant add-on that speaks a
binary panel protocol and publishes MQTT discovery and state. The implementation
language has to fit that ecosystem and the libraries the work already depends on.
**Decision:** Use Python 3 for the Texecom Alarm App.
**Why this way:** Python is the usual language for Home Assistant add-on and
integration work, and the dependencies this app needs are mature there. Other
languages would force a less natural stack for the same job without a compensating
gain for this project.
**What this constrains:**
- New app code for this peer stays in Python 3 — do not reimplement the add-on in
  another language without a superseding ADR.
- Packaging and runtime stay compatible with a Python 3 process inside the Home
  Assistant App image (not a second language runtime as the primary app).
**Open follow-ons:** None.

## Context

The Texecom Alarm App is a single long-running process that bridges a Premier Elite
panel (ComIP / Connect protocol) to Home Assistant over MQTT discovery. Language
choice was made when the architecture and scaffold were first locked and the app has
already shipped on Python 3. That choice was never recorded as an ADR, which left
architecture reviews flagging “technology without ADR.” This ADR records the decision
as already in force.

## Decision drivers

- Fit the Home Assistant add-on ecosystem (images, process model, operator expectations).
- Prefer languages where MQTT clients, async I/O, and binary-protocol work are
  ordinary, well-supported dependencies.
- Avoid a language rewrite with no product payoff while the panel/MQTT behaviour is
  still the hard problem.

## Options considered

- **Python 3** — run the add-on as a Python 3 process in the Home Assistant App image.
- **Node.js / TypeScript** — also common around Home Assistant tooling. Rejected
  because: this project’s chosen dependencies and existing codebase are Python; a
  Node rewrite would not improve panel/MQTT outcomes for the cost.
- **Go (or another compiled single-binary language)** — appealing for a small
  long-running binary. Rejected because: poorer fit for the usual HA add-on Python
  stack and for the libraries already in use; no driver here requires that trade.

## Decision

Chosen option: **Python 3**

Python 3 is the standard language choice for this class of Home Assistant add-on, and
it already carries the dependencies the app uses. Recording it closes the gap between
the shipping stack and the ADR register without changing runtime behaviour.

## Consequences

**Positive:** Agents and reviews can cite a settled language; Technology fields can
point at ADR-012; no ambiguity about rewriting the peer in another language.

**Negative:** The project stays on Python’s packaging and runtime model; moving to
another language later requires a superseding ADR and a real migration.

**Follow-on:** None — Docker base image and s6 process supervision remain
platform-mandated Home Assistant App packaging, not a separate language decision.

## Confirmation

This decision is correctly implemented when the Texecom Alarm App peer’s primary
source and runtime remain Python 3, and architecture / agent context cite ADR-012 for
that technology choice rather than leaving Python unnamed in the ADR register.
