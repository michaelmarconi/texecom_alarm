# Availability vs panel connection

Home Assistant has two different “is this working?” questions. This app answers
them on **separate** signals on purpose.

## App up vs panel reachable

| Question | What to look at | When it goes “off” |
|----------|-----------------|-------------------|
| Is the **app** running? | Alarm and zone entities’ availability (MQTT last will) | The add-on process has stopped |
| Is the **panel link** live and trustworthy? | **Alarm Panel Connection** | Hang-up / end-of-session, health-check patience exceeded, or an arm/disarm refused or silently timed out (not a garbled follow-up after a successful arm/disarm whose first re-login works) |

If the panel connection drops, **alarm and zone entities stay available** with
their last known state. Dashboards and automations can still *see* a value;
that value may be stale. Use **Alarm Panel Connection** (and your own
automations on it) to tell live data from a stale link.

Marking the alarm or zones unavailable because the panel hiccupped would hide
the last known state — including during a real alarm, when you most want to
see what happened.

## What “Connection off” means

The sensor is off while the app is still running but should not be trusted for
fresh panel state, for example:

- The socket closed (hang-up) or the panel ended the session, and the app is
  reconnecting
- Health-check refusals or silence past the patience window
- An arm or disarm was rejected, or timed out with a silent wait (or busy
  retries exhausted), even if keepalives still succeed

Unreadable bytes after an arm or disarm that already succeeded are a session
resync, not a failed tap: Connection stays on if the first re-login works.

A successful keepalive can turn it back on. If it stays off longer than the
**force-reconnect window** (default 90 seconds), the app tears down the
session and logs in again. It does **not** silently re-send the failed arm or
disarm.

Separately, the add-on also periodically double-checks the alarm state
against the panel and corrects it if they disagree — that reconciliation
check is a belt-and-braces correction, not a connectivity signal. It does
**not** affect **Alarm Panel Connection**, even if it times out in isolation.

## Last-trigger snapshot

When the alarm entity first enters **triggered**, the app publishes a short
retained summary of recent zone activity (initiating zone number and time) as
attributes on the alarm entity. That snapshot is meant to survive a later
outage so you can still see what happened just before the alarm.

A restart while already in alarm does not invent a new snapshot.

## Related

- MQTT topics: [MQTT reference](../reference/mqtt.md)
- Option reference: [Documentation](../../texecom_alarm/DOCS.md#soft-trust-recovery)
- Protocol shape: [protocol overview](../protocol-overview.md)
