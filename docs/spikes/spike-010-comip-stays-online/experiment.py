#!/usr/bin/env python3
"""
SPIKE-010: record Alarm Panel Connection and alarm state while you walk.

Does **not** talk to the panel. Leave the add-on running on the ComIP.

You do:
  Walk A — Arm Home, wait until settled, Disarm. Connection must stay ON.
  Walk B — Tell monitoring; bells off if you can. Arm, trigger, Disarm from HA.
            Connection must stay ON; Disarm must actually stop the alarm.

This script prints timestamped MQTT lines until you press Ctrl+C.

Usage (from this folder, HAOS host with Mosquitto in Docker):

    python3 experiment.py

Or subscribe yourself:

    mosquitto_sub -h <broker> -u texecom -P <password> -v \\
        -t 'texecom/panel_connection/state' -t 'texecom/alarm/state'
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

PREFIX = os.environ.get("TEXECOM_MQTT_PREFIX", "texecom")
TOPICS = [
    f"{PREFIX}/panel_connection/state",
    f"{PREFIX}/alarm/state",
    f"{PREFIX}/status",
]
MQTT_USER = os.environ.get("TEXECOM_MQTT_USER", "texecom")
MQTT_PASSWORD = os.environ.get("TEXECOM_MQTT_PASSWORD", "texecom-accept")
MQTT_HOST = os.environ.get("TEXECOM_MQTT_HOST", "")
DOCKER_MOSQUITTO = os.environ.get("TEXECOM_MQTT_DOCKER", "app_core_mosquitto")


def ts() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def mosquitto_sub_cmd() -> list[str]:
    args = [
        "mosquitto_sub",
        "-u",
        MQTT_USER,
        "-P",
        MQTT_PASSWORD,
        "-v",
    ]
    for t in TOPICS:
        args.extend(["-t", t])
    if MQTT_HOST:
        args.extend(["-h", MQTT_HOST])
    docker = shutil.which("docker")
    if docker and not MQTT_HOST:
        return [docker, "exec", "-i", DOCKER_MOSQUITTO, *args]
    return args


def main() -> int:
    print(f"[{ts()}] SPIKE-010 MQTT log — add-on stays up; you do Walk A then Walk B")
    print(f"[{ts()}] Topics: {', '.join(TOPICS)}")
    print(f"[{ts()}] Ctrl+C when both walks are done.")
    print()
    print("Walk A: Arm Home → settle → Disarm. Connection must stay ON.")
    print("Walk B: Arm → trigger → Disarm from HA. Connection ON; Disarm must work.")
    print()
    cmd = mosquitto_sub_cmd()
    display = [
        (c if i < 2 or cmd[i - 1] != "-P" else "****") for i, c in enumerate(cmd)
    ]
    print(f"[{ts()}] starting: {' '.join(display)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        print(f"[{ts()}] cannot start logger: {exc}", file=sys.stderr)
        print(
            "Install mosquitto_sub or set TEXECOM_MQTT_HOST / TEXECOM_MQTT_DOCKER.",
            file=sys.stderr,
        )
        return 1
    assert proc.stdout is not None
    off_seen = False
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            print(f"[{ts()}] {line}", flush=True)
            if line.endswith(" OFF") or line.endswith("\tOFF") or " OFF" in line:
                off_seen = True
    except KeyboardInterrupt:
        print(f"[{ts()}] stopped", flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print()
    print("=== summary ===")
    print(f"connection OFF seen in this log: {'yes' if off_seen else 'no'}")
    print("Walk A pass/fail and Walk B Disarm-from-HA pass/fail: you report those.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
