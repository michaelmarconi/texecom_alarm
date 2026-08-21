# Home Assistant loses your Texecom panel the moment the alarm goes off

## The symptom

Everything works fine day to day. You can arm, disarm, see zone states. Then a
real alarm triggers — sirens going, HA correctly shows "triggered" — and disarm
from Home Assistant does nothing at all. You end up walking to the keypad.

Afterwards, the connection comes back on its own, usually within a minute or two.

The Texecom app and the keypad both still work throughout. Only Home Assistant
is locked out, and only during the alarm.

## What's probably happening

Texecom panels talk to the outside world through communication modules — small
add-on boards plugged into "COM ports" on the main PCB. A ComIP or SmartCom is
one of these.

**The important bit: each COM port is a single serial connection. It can only do
one job at a time.**

So when the panel needs to report an alarm — to a monitoring station, or to
Texecom's cloud for the app — it grabs the COM port it uses for that and kicks
off whatever was already using it. If Home Assistant happens to be connected
through that same module, HA is what gets kicked off. The panel isn't
malfunctioning; it's prioritising, exactly as designed. Alarm signalling wins.

Once signalling finishes, the port frees up and HA reconnects. Which is why the
outage is temporary and why it *only* ever happens during real alarms.

## The most likely cause, and it's an easy one to miss

**Home Assistant is talking to the wrong module.**

Lots of these systems have two IP modules — the installer's one for the app and
the monitoring station, plus a ComIP the homeowner added later for local
control. If HA got pointed at the installer's module rather than the one you
added, you're sharing the signalling path, and you'll get exactly this
behaviour.

It's a very easy mistake, because both modules sit on the same network, both
answer on similar ports, and routers frequently label them wrongly or not at
all. In the case that prompted this write-up, HA had been on the wrong module
for two years.

## How to check

**1. Work out how many IP modules you actually have.**

Open the panel (see the safety note below) and look at what's plugged in. Note
each module's make and which COM header its cable goes to. Photograph
everything.

**2. Find them on your network.**

Scan your LAN for anything answering on ports 9999 and 10001. A ComIP is built
around a Lantronix serial-to-Ethernet chip, so its MAC address will start
`00:80:A3` — that identifies it beyond doubt. Anything else answering is likely
the installer's module.

**Watch out:** a module with a manually-set IP address won't appear in your
router's device list at all, because it never asks the router for an address.
It's still there and still working — just invisible. Don't conclude it doesn't
exist because your router doesn't list it.

**3. Compare against what Home Assistant is configured to use.**

Look at the IP address in your Texecom integration or add-on config. If it
matches the installer's module rather than your own, that's your problem, and
repointing HA is a five-minute config change with no risk to the alarm.

**4. If they're already separate, check the panel programming.**

Get into engineer mode and look at **Program Digi**. Each alarm receiving centre
entry specifies which COM port it signals through. If any of them names the port
your ComIP is on, the panel will seize it during an alarm no matter how many
modules you have.

Also check **Digi Options** for "Dial All Numbers". Where multiple communicators
are fitted, Texecom's own documentation says this should be enabled — and it
means the panel signals through *every* fitted module. That would include your
ComIP, and would reproduce this fault even with the modules otherwise properly
separated.

## Things worth knowing before you start

- **You need the engineer code.** Without it you can't see any of the relevant
  settings. Some installs also require "Enable Engineer" to be switched on from
  the master user menu first.
- **Opening the cabinet is fine while in engineer mode** — tampers are inhibited,
  which is precisely why engineers can work on live systems. Your monitoring
  station will likely log "engineer on site". Tell them first if you can.
- **Read everything before you change anything.** Back out of screens with
  NO/RESET rather than pressing YES to "confirm" a value that was already
  correct.
- **Don't touch the installer's module.** If you break the monitoring path it
  may fail silently, and you won't find out until you need it.
- **These modules accept one connection at a time.** If a port scan says
  "connection refused" on port 10001, that's usually just Home Assistant already
  holding the socket. It's a sign of health, not a fault.
- **Prove the fix.** Arrange a walk test with the monitoring station notified and
  the bells disabled, then watch whether HA's connection survives a genuine
  alarm condition. Nothing else actually confirms it.

## If none of that helps

If you genuinely only have one IP module, HA and the panel's signalling *must*
share it, and no amount of reprogramming separates them. Your options are to add
a second module so signalling and local control each get their own COM port, or
to accept that HA can't disarm mid-alarm and scope it to status and routine
arming instead.

That second option is more reasonable than it sounds — the keypad always works,
and disarm-during-alarm is the one moment the panel is designed to prioritise
everything else.
