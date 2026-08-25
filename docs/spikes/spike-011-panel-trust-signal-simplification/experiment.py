#!/usr/bin/env python3
"""SPIKE-011: compare the shipped Combination detector (SPIKE-008 / ADR-010)
against a simplified detector on the same event timelines, plus one new
timeline shaped like the 2026-08-25 live incident (a single background
house-state poll starved by a burst of panel event traffic, with keepalive
never failing and no arm/disarm in flight).

Hermetic — no ComIP, no MQTT, no production imports. This file intentionally
duplicates the small simulator core from
docs/spikes/spike-008-silent-panel-path-death-detection/experiment.py rather
than importing it, so this spike stays self-contained. Run:
  python3 docs/spikes/spike-011-panel-trust-signal-simplification/experiment.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EventKind = Literal[
    "keepalive_ok",
    "keepalive_fail",
    "zone",
    "area",
    "log",
    "arm_nak",
    "arm_ok",
    "disarm_nak",
    "disarm_ok",
    "corroboration_ok",
    "corroboration_fail",
    "disconnect",
]


@dataclass(frozen=True)
class Event:
    t: int
    kind: EventKind


@dataclass
class DetectorState:
    live: bool = True
    last_command_fail_t: int | None = None
    first_degraded_t: int | None = None
    live_again_t: int | None = None
    history: list[tuple[int, bool]] = field(default_factory=list)

    def set_live(self, t: int, live: bool) -> None:
        if self.live == live:
            return
        self.live = live
        self.history.append((t, live))
        if not live and self.first_degraded_t is None:
            self.first_degraded_t = t
        if live and self.first_degraded_t is not None and self.live_again_t is None:
            self.live_again_t = t


def combination(events: list[Event], *, recover_window: int = 30) -> DetectorState:
    """Shipped design (ADR-010): command NAK/timeout OR corroboration-poll
    fail/timeout degrades; recovers on a successful corroboration poll once
    recover_window has elapsed since the last command failure."""
    st = DetectorState()
    by_t: dict[int, list[Event]] = {}
    for e in events:
        by_t.setdefault(e.t, []).append(e)
    end = max((e.t for e in events), default=0) + recover_window + 5
    for t in range(0, end + 1):
        for e in by_t.get(t, []):
            if e.kind in ("arm_nak", "disarm_nak"):
                st.last_command_fail_t = t
                st.set_live(t, False)
            elif e.kind in ("corroboration_fail", "disconnect"):
                st.set_live(t, False)
            elif e.kind == "corroboration_ok":
                last_fail = st.last_command_fail_t
                if last_fail is None or (t - last_fail) >= recover_window:
                    st.set_live(t, True)
    return st


def simplified(events: list[Event], *, recover_window: int = 30) -> DetectorState:
    """Proposed design: degrade on a keepalive failure/disconnect, OR
    immediately on a command NAK/timeout. The periodic house-state poll no
    longer drives this signal at all (it may still run for its own resync
    purpose, but a poll failure/success is not fed to this detector).
    Recovers on the next successful keepalive once recover_window has
    elapsed since the last command failure (mirrors Combination's own
    recover guard, substituting keepalive for corroboration as the
    "still trustworthy" signal)."""
    st = DetectorState()
    by_t: dict[int, list[Event]] = {}
    for e in events:
        by_t.setdefault(e.t, []).append(e)
    end = max((e.t for e in events), default=0) + recover_window + 5
    for t in range(0, end + 1):
        for e in by_t.get(t, []):
            if e.kind in ("arm_nak", "disarm_nak"):
                st.last_command_fail_t = t
                st.set_live(t, False)
            elif e.kind in ("keepalive_fail", "disconnect"):
                st.set_live(t, False)
            elif e.kind == "keepalive_ok":
                last_fail = st.last_command_fail_t
                if last_fail is None or (t - last_fail) >= recover_window:
                    st.set_live(t, True)
    return st


def _keepalives(start: int, end: int, every: int = 15, *, ok: bool = True) -> list[Event]:
    kind: EventKind = "keepalive_ok" if ok else "keepalive_fail"
    return [Event(t, kind) for t in range(start, end + 1, every)]


def _corroborations(start: int, end: int, every: int = 30, *, ok: bool = True) -> list[Event]:
    kind: EventKind = "corroboration_ok" if ok else "corroboration_fail"
    return [Event(t, kind) for t in range(start + every, end + 1, every)]


def scenario_s1_quiet() -> list[Event]:
    events: list[Event] = []
    events += _keepalives(0, 600, ok=True)
    events += _corroborations(0, 600, ok=True)
    return sorted(events, key=lambda e: e.t)


def scenario_s2_silent_death() -> list[Event]:
    events: list[Event] = []
    events += _keepalives(0, 60, ok=True)
    events += _corroborations(0, 60, ok=True)
    events += _keepalives(75, 150, ok=False)
    events += _corroborations(60, 150, ok=False)
    return sorted(events, key=lambda e: e.t)


def scenario_s3_command_zombie() -> list[Event]:
    events: list[Event] = []
    events += _keepalives(0, 150, ok=True)
    events += _corroborations(0, 150, ok=True)
    events += [Event(t, "log") for t in range(0, 151, 10)]
    events += [Event(70, "arm_nak"), Event(90, "arm_nak"), Event(110, "arm_nak")]
    return sorted(events, key=lambda e: e.t)


def scenario_s4_clean_disconnect() -> list[Event]:
    events: list[Event] = []
    events += _keepalives(0, 60, ok=True)
    events += _corroborations(0, 60, ok=True)
    events.append(Event(70, "disconnect"))
    events += _keepalives(75, 120, ok=False)
    events += [Event(t, "corroboration_fail") for t in range(90, 121, 30)]
    return sorted(events, key=lambda e: e.t)


def scenario_s5_transient_nak() -> list[Event]:
    events: list[Event] = []
    events += _keepalives(0, 200, ok=True)
    events += _corroborations(0, 200, ok=True)
    events.append(Event(70, "arm_nak"))
    events.append(Event(100, "arm_ok"))
    return sorted(events, key=lambda e: e.t)


def scenario_s6_burst_starved_poll() -> list[Event]:
    """Shape of the 2026-08-25 live incident: keepalive succeeds on every
    scheduled tick, no arm/disarm is attempted, and exactly one scheduled
    house-state poll fails (starved by a burst of unrelated panel event
    traffic) before the next scheduled poll succeeds normally."""
    events: list[Event] = []
    events += _keepalives(0, 200, ok=True)
    events += [Event(t, "corroboration_ok") for t in (30, 60)]
    events.append(Event(90, "corroboration_fail"))
    events += [Event(t, "corroboration_ok") for t in (120, 150, 180)]
    # Non-command panel chatter around the same time (the burst itself) —
    # neither detector treats this as a trust signal either way.
    events += [Event(t, "log") for t in (85, 86, 87)]
    return sorted(events, key=lambda e: e.t)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def run() -> list[CheckResult]:
    results: list[CheckResult] = []

    # --- S1 quiet house: neither detector should ever degrade ---
    s1 = scenario_s1_quiet()
    for label, st in (("Combination", combination(s1)), ("Simplified", simplified(s1))):
        results.append(
            CheckResult(
                f"S1 {label} never degraded",
                st.first_degraded_t is None,
                f"first_degraded={st.first_degraded_t}",
            )
        )

    # --- S2 silent death: both must degrade within 30s of onset (t=75) ---
    s2 = scenario_s2_silent_death()
    onset = 75
    for label, st in (("Combination", combination(s2)), ("Simplified", simplified(s2))):
        ok = st.first_degraded_t is not None and st.first_degraded_t <= onset + 30
        results.append(
            CheckResult(
                f"S2 {label} degrade \u226430s after silence onset",
                ok,
                f"first_degraded={st.first_degraded_t} onset={onset}",
            )
        )

    # --- S3 command zombie: both must degrade by t=100 ---
    s3 = scenario_s3_command_zombie()
    for label, st in (("Combination", combination(s3)), ("Simplified", simplified(s3))):
        ok = st.first_degraded_t is not None and st.first_degraded_t <= 100
        results.append(
            CheckResult(
                f"S3 {label} degraded by t=100",
                ok,
                f"first_degraded={st.first_degraded_t}",
            )
        )

    # --- S4 clean disconnect: both must degrade by t=100 ---
    s4 = scenario_s4_clean_disconnect()
    drop = 70
    for label, st in (("Combination", combination(s4)), ("Simplified", simplified(s4))):
        ok = st.first_degraded_t is not None and st.first_degraded_t <= drop + 30
        results.append(
            CheckResult(
                f"S4 {label} degraded by t=100",
                ok,
                f"first_degraded={st.first_degraded_t}",
            )
        )

    # --- S5 transient nak: both must degrade then recover by t=160 ---
    s5 = scenario_s5_transient_nak()
    for label, detector in (("Combination", combination), ("Simplified", simplified)):
        st = detector(s5)
        degraded = st.first_degraded_t is not None and st.first_degraded_t >= 70
        recovered = st.live_again_t is not None and 100 <= st.live_again_t <= 160
        results.append(
            CheckResult(
                f"S5 {label} degrades then live again by t=160",
                degraded and recovered,
                f"first_degraded={st.first_degraded_t} live_again={st.live_again_t}",
            )
        )

    # --- S6 (NEW) burst-starved single poll: the live-incident shape ---
    s6 = scenario_s6_burst_starved_poll()
    s6_combo = combination(s6)
    s6_simplified = simplified(s6)
    results.append(
        CheckResult(
            "S6 Combination false-degrades on the one-off starved poll "
            "(expected fail of the shipped design — reproduces the live incident)",
            s6_combo.first_degraded_t is not None,
            f"first_degraded={s6_combo.first_degraded_t} live_again={s6_combo.live_again_t}",
        )
    )
    results.append(
        CheckResult(
            "S6 Simplified never degrades (no keepalive fail, no command in flight)",
            s6_simplified.first_degraded_t is None,
            f"first_degraded={s6_simplified.first_degraded_t}",
        )
    )

    # --- Hypothesis overall ---
    combo_s6_false_blip = s6_combo.first_degraded_t is not None
    simplified_s6_clean = s6_simplified.first_degraded_t is None
    simplified_matches_s1_s5 = all(
        r.passed for r in results if r.name.startswith(("S1 Simplified", "S2 Simplified", "S3 Simplified", "S4 Simplified", "S5 Simplified"))
    )
    results.append(
        CheckResult(
            "Hypothesis overall (Simplified matches Combination on S1-S5; "
            "avoids Combination's S6 false blip)",
            simplified_matches_s1_s5 and combo_s6_false_blip and simplified_s6_clean,
            (
                f"simplified_matches_s1_s5={simplified_matches_s1_s5} "
                f"combo_s6_false_blip={combo_s6_false_blip} "
                f"simplified_s6_clean={simplified_s6_clean}"
            ),
        )
    )

    return results


def main() -> int:
    results = run()
    print("SPIKE-011 detector comparison (hermetic simulator)")
    print("=" * 60)
    failed = 0
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        if not r.passed:
            failed += 1
        print(f"[{mark}] {r.name}: {r.detail}")
    print("=" * 60)
    print(f"{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
