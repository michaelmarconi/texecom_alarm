#!/usr/bin/env python3
"""SPIKE-008: compare silent-death detectors on synthetic session timelines.

Hermetic — no ComIP, no MQTT, no production imports. Run:
  python3 docs/spikes/spike-008-silent-panel-path-death-detection/experiment.py
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
    last_trust_traffic_t: int = 0
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
            # record first recovery after first degrade (S5 cares about this)
            self.live_again_t = t


def traffic_absence(events: list[Event], *, n: int = 60) -> DetectorState:
    st = DetectorState()
    by_t: dict[int, list[Event]] = {}
    for e in events:
        by_t.setdefault(e.t, []).append(e)
    end = max((e.t for e in events), default=0) + n + 5
    for t in range(0, end + 1):
        for e in by_t.get(t, []):
            if e.kind in ("zone", "area", "log"):
                st.last_trust_traffic_t = t
        if t - st.last_trust_traffic_t >= n:
            st.set_live(t, False)
        else:
            st.set_live(t, True)
    return st


def idle_probe_fail(events: list[Event]) -> DetectorState:
    st = DetectorState()
    by_t: dict[int, list[Event]] = {}
    for e in events:
        by_t.setdefault(e.t, []).append(e)
    end = max((e.t for e in events), default=0) + 5
    for t in range(0, end + 1):
        for e in by_t.get(t, []):
            if e.kind == "keepalive_fail" or e.kind == "disconnect":
                st.set_live(t, False)
            elif e.kind == "keepalive_ok" and st.live:
                pass
            elif e.kind == "keepalive_ok" and not st.live:
                # idle-only detector does not auto-recover in this model
                pass
        # disconnect leaves degraded
    return st


def periodic_corroboration(events: list[Event]) -> DetectorState:
    st = DetectorState()
    by_t: dict[int, list[Event]] = {}
    for e in events:
        by_t.setdefault(e.t, []).append(e)
    end = max((e.t for e in events), default=0) + 5
    for t in range(0, end + 1):
        for e in by_t.get(t, []):
            if e.kind in ("corroboration_fail", "disconnect"):
                st.set_live(t, False)
            elif e.kind == "corroboration_ok":
                st.set_live(t, True)
    return st


def combination(events: list[Event], *, recover_window: int = 30) -> DetectorState:
    """Command NAK/timeout OR corroboration fail → degraded; recover on OK corroboration
    with no command failure in the last recover_window seconds."""
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
            elif e.kind in ("arm_ok", "disarm_ok"):
                # success alone does not clear degraded until corroboration + window
                pass
    return st


def _keepalives(start: int, end: int, every: int = 15, *, ok: bool = True) -> list[Event]:
    kind: EventKind = "keepalive_ok" if ok else "keepalive_fail"
    return [Event(t, kind) for t in range(start, end + 1, every)]


def _corroborations(start: int, end: int, every: int = 30, *, ok: bool = True) -> list[Event]:
    kind: EventKind = "corroboration_ok" if ok else "corroboration_fail"
    # first probe at start+every to match "every 30s" after session up at 0
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
    # silence onset: keepalives fail from t=75 (first scheduled after healthy window)
    events += _keepalives(75, 150, ok=False)
    events += _corroborations(60, 150, ok=False)
    return sorted(events, key=lambda e: e.t)


def scenario_s3_command_zombie() -> list[Event]:
    events: list[Event] = []
    events += _keepalives(0, 150, ok=True)
    events += _corroborations(0, 150, ok=True)
    # LOG every 10s so TrafficAbsence sees traffic
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


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def run() -> list[CheckResult]:
    results: list[CheckResult] = []

    # --- S1 ---
    s1 = scenario_s1_quiet()
    s1_combo = combination(s1)
    s1_idle = idle_probe_fail(s1)
    s1_ta = traffic_absence(s1)
    results.append(
        CheckResult(
            "S1 Combination never degraded",
            s1_combo.first_degraded_t is None,
            f"first_degraded={s1_combo.first_degraded_t}",
        )
    )
    results.append(
        CheckResult(
            "S1 IdleProbeFail never degraded",
            s1_idle.first_degraded_t is None,
            f"first_degraded={s1_idle.first_degraded_t}",
        )
    )
    results.append(
        CheckResult(
            "S1 TrafficAbsence false-degrades (expected fail of that detector)",
            s1_ta.first_degraded_t is not None and s1_ta.first_degraded_t <= 60,
            f"first_degraded={s1_ta.first_degraded_t}",
        )
    )

    # --- S2 ---
    s2 = scenario_s2_silent_death()
    silence_onset = 75
    for label, st in (
        ("Combination", combination(s2)),
        ("IdleProbeFail", idle_probe_fail(s2)),
        ("PeriodicCorroboration", periodic_corroboration(s2)),
    ):
        ok = (
            st.first_degraded_t is not None
            and st.first_degraded_t <= silence_onset + 30
        )
        results.append(
            CheckResult(
                f"S2 {label} degrade ≤30s after silence onset",
                ok,
                f"first_degraded={st.first_degraded_t} onset={silence_onset}",
            )
        )

    # --- S3 ---
    s3 = scenario_s3_command_zombie()
    s3_combo = combination(s3)
    s3_idle = idle_probe_fail(s3)
    s3_ta = traffic_absence(s3)
    results.append(
        CheckResult(
            "S3 Combination degraded by t=100",
            s3_combo.first_degraded_t is not None and s3_combo.first_degraded_t <= 100,
            f"first_degraded={s3_combo.first_degraded_t}",
        )
    )
    results.append(
        CheckResult(
            "S3 IdleProbeFail still live at t=120",
            s3_idle.first_degraded_t is None,
            f"first_degraded={s3_idle.first_degraded_t}",
        )
    )
    # TrafficAbsence must still be live at t=120: evaluate state by replaying to 120
    ta_live_120 = True
    if s3_ta.first_degraded_t is not None and s3_ta.first_degraded_t <= 120:
        # with LOG every 10s, should not degrade — if it did, fail
        ta_live_120 = False
    results.append(
        CheckResult(
            "S3 TrafficAbsence still live at t=120 (LOG feed)",
            ta_live_120,
            f"first_degraded={s3_ta.first_degraded_t}",
        )
    )

    # --- S4 ---
    s4 = scenario_s4_clean_disconnect()
    drop = 70
    for label, st in (
        ("IdleProbeFail", idle_probe_fail(s4)),
        ("PeriodicCorroboration", periodic_corroboration(s4)),
        ("Combination", combination(s4)),
    ):
        ok = st.first_degraded_t is not None and st.first_degraded_t <= drop + 30
        results.append(
            CheckResult(
                f"S4 {label} degraded by t=100",
                ok,
                f"first_degraded={st.first_degraded_t}",
            )
        )

    # --- S5 ---
    s5 = scenario_s5_transient_nak()
    s5_combo = combination(s5)
    # Need recovery: after arm_ok at 100, next corroboration at 120; recover_window=30
    # so live again when corroboration_ok at t>=130 (100+30) — first such is t=150
    degraded = s5_combo.first_degraded_t is not None and s5_combo.first_degraded_t >= 70
    # Re-run with tracking of live after degrade: live_again_t only set once
    recovered = (
        s5_combo.live_again_t is not None
        and s5_combo.live_again_t <= 160
        and s5_combo.live_again_t >= 100
    )
    results.append(
        CheckResult(
            "S5 Combination degrades then live again by t=160",
            degraded and recovered,
            f"first_degraded={s5_combo.first_degraded_t} live_again={s5_combo.live_again_t}",
        )
    )

    # --- Hypothesis overall ---
    s1_fail_ta = s1_ta.first_degraded_t is not None
    s3_fail_idle = s3_idle.first_degraded_t is None  # idle misses zombie = good for "idle alone fails S3"
    s3_fail_ta = ta_live_120  # traffic absence misses = fails as sole detector for S3
    combo_s1 = s1_combo.first_degraded_t is None
    combo_s3 = s3_combo.first_degraded_t is not None and s3_combo.first_degraded_t <= 100
    combo_s5 = degraded and recovered
    results.append(
        CheckResult(
            "Hypothesis overall (Combination wins; TA fails S1; Idle misses S3)",
            combo_s1 and combo_s3 and combo_s5 and s1_fail_ta and s3_fail_idle and s3_fail_ta,
            (
                f"combo_s1={combo_s1} combo_s3={combo_s3} combo_s5={combo_s5} "
                f"ta_false_s1={s1_fail_ta} idle_miss_s3={s3_fail_idle} ta_miss_s3={s3_fail_ta}"
            ),
        )
    )

    return results


def main() -> int:
    results = run()
    print("SPIKE-008 detector comparison (hermetic simulator)")
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
