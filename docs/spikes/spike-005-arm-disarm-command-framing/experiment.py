#!/usr/bin/env python3
"""
SPIKE-005 experiment: decode the exact arm/disarm command framing the official
Texecom Connect mobile app sends to the panel, from a passive network capture
of its own real traffic - WITHOUT ever sending a guessed/experimental command
to the panel ourselves.

This is an offline analysis script (Part B of the experiment - see SPIKE.md
## Experiment Design). Part A, performed by the practitioner on the household
LAN, produces a classic libpcap (.pcap) capture of the official Texecom
Connect app's traffic to the panel while it is used (in "Local Connection"
mode, per the manufacturer's own INS273-7 installation manual, section 6.1)
to arm to each of Home/Away/Night and disarm, each cycle repeated twice.

This script never talks to the panel itself. It only reads a capture file
already produced by Part A and reconstructs/decodes what the app already
sent, reusing the frame-parsing/resync logic already proven working in
SPIKE-002's experiment.py (start byte 't', type/length/seq/body/CRC-8 header,
scan-forward-and-skip on any non-conforming byte) - reimplemented here from
first principles against those documented byte values, not copied from any
GPL/Apache-licensed source, per RISK-008.

Input format: classic libpcap (.pcap), stdlib-only (no scapy/dpkt dependency).
If your capture is pcapng (Wireshark's default), convert it first, e.g.:
    tcpdump -r capture.pcapng -w capture.pcap
    # or: editcap -F pcap capture.pcapng capture.pcap

Usage:
    TEXECOM_HOST=192.168.1.183 TEXECOM_PORT=10001 \
        python3 experiment.py capture.pcap
"""

import os
import struct
import sys
import time

HOST = os.environ.get("TEXECOM_HOST", "192.168.1.183")
PORT = int(os.environ.get("TEXECOM_PORT", "10001"))

HEADER_START = ord("t")
HEADER_TYPE_COMMAND = ord("C")
HEADER_TYPE_RESPONSE = ord("R")
HEADER_TYPE_MESSAGE = ord("M")
LENGTH_HEADER = 4

CMD_LOGIN = 1
CMD_GETDATETIME = 23
CMD_GETPANELIDENTIFICATION = 22
CMD_SETEVENTMESSAGES = 37

RESP_ACK = 0x06
RESP_NAK = 0x15

MSG_DEBUG = 0
MSG_ZONEEVENT = 1
MSG_AREAEVENT = 2
MSG_OUTPUTEVENT = 3
MSG_USEREVENT = 4
MSG_LOGEVENT = 5

AREA_STATES = ["disarmed", "in exit", "in entry", "armed", "part armed", "in alarm"]

KNOWN_COMMANDS = {
    CMD_LOGIN: "LOGIN",
    3: "GETZONEDETAILS",
    13: "GETLCDDISPLAY",
    15: "GETLOGPOINTER",
    CMD_GETPANELIDENTIFICATION: "GETPANELIDENTIFICATION",
    CMD_GETDATETIME: "GETDATETIME",
    25: "GETSYSTEMPOWER",
    27: "GETUSER",
    35: "GETAREADETAILS",
    CMD_SETEVENTMESSAGES: "SETEVENTMESSAGES",
}

# Reproduced from Texecom Connect protocol documentation cross-referenced
# publicly (see SPIKE-002's SPIKE.md ## Research) - independently retyped,
# not copied from any single source file.
LOG_EVENT_TYPES = {
    27: "Alarm Active",
    28: "Bell Active",
    29: "Re-arm",
    32: "Exit Started",
    33: "Exit Error (Arming Failed)",
    34: "Entry Started",
    35: "Part Arm Suite",
    37: "Open/Close (Away Armed)",
    38: "Part Armed",
    43: "Quick Arm",
    45: "Reset After Alarm",
    53: "Download Start",
    54: "Download End",
    78: "Part Arm 1",
    79: "Part Arm 2",
    80: "Part Arm 3",
    81: "Auto Arming Started",
    82: "Confirmed Alarm",
    85: "Arm Failed",
    100: "Site Data Changed",
    113: "Remote Command",
}


def crc8(data: bytes) -> int:
    """CRC-8, poly=0x185 (crcmod convention: leading bit implicit, so the
    working 8-bit polynomial is 0x85), non-reflected, init=0xFF - as
    documented for the Connect protocol and confirmed working in SPIKE-001."""
    poly = 0x85
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def decode_message(payload: bytes) -> str:
    if not payload:
        return "empty message payload"
    msg_type, body = payload[0], payload[1:]

    if msg_type == MSG_AREAEVENT and len(body) >= 2:
        area_number, area_state = body[0], body[1]
        state_str = AREA_STATES[area_state] if area_state < len(AREA_STATES) else f"unknown({area_state})"
        return f"AREA event: area={area_number} state={state_str}"

    if msg_type == MSG_LOGEVENT and len(body) >= 4:
        event_type, group_type_msg = body[0], body[1]
        group_type = group_type_msg & 0b00111111
        event_str = LOG_EVENT_TYPES.get(event_type, f"unknown log event type {event_type}")
        return f"LOG event: type={event_type} ({event_str}) group={group_type}"

    if msg_type == MSG_ZONEEVENT and len(body) >= 2:
        zone_number, zone_bitmap = body[0], body[1]
        zone_str = ["secure", "active", "tamper", "short"][zone_bitmap & 0x3]
        return f"ZONE event: zone={zone_number} state={zone_str} bitmap={zone_bitmap:#04x}"

    if msg_type == MSG_OUTPUTEVENT:
        return f"OUTPUT event: raw={body.hex()}"
    if msg_type == MSG_USEREVENT:
        return f"USER event: raw={body.hex()}"
    if msg_type == MSG_DEBUG:
        return f"DEBUG message: raw={body.hex()}"
    return f"unknown message type {msg_type}: raw={body.hex()}"


# --------------------------------------------------------------------------
# Part A output reader: minimal classic-libpcap parser (stdlib only).
# --------------------------------------------------------------------------

PCAP_MAGIC_LE = 0xA1B2C3D4
PCAP_MAGIC_LE_NS = 0xA1B23C4D
PCAP_MAGIC_BE = 0xD4C3B2A1
PCAP_MAGIC_BE_NS = 0x4D3CB2A1


LINKTYPE_ETHERNET = 1
LINKTYPE_LINUX_SLL = 113   # "Linux cooked capture" v1
LINKTYPE_LINUX_SLL2 = 276  # "Linux cooked capture" v2
SUPPORTED_LINKTYPES = {LINKTYPE_ETHERNET, LINKTYPE_LINUX_SLL, LINKTYPE_LINUX_SLL2}


def read_pcap_packets(path):
    """Yield (timestamp, raw_packet_bytes, linktype) for every packet in a
    classic libpcap file. Does not support pcapng - see module docstring for
    the conversion command if your capture tool produced pcapng instead."""
    with open(path, "rb") as f:
        magic_raw = f.read(4)
        if len(magic_raw) < 4:
            raise ValueError(f"{path}: file too short to be a pcap capture")
        magic = struct.unpack("<I", magic_raw)[0]
        if magic in (PCAP_MAGIC_LE, PCAP_MAGIC_LE_NS):
            endian = "<"
        elif magic in (PCAP_MAGIC_BE, PCAP_MAGIC_BE_NS):
            endian = ">"
        else:
            raise ValueError(
                f"{path}: unrecognised magic number {magic:#010x} - this looks like "
                "pcapng, not classic pcap. Convert first: "
                "tcpdump -r <file> -w <file>.pcap"
            )
        header = f.read(20)
        if len(header) < 20:
            raise ValueError(f"{path}: truncated pcap global header")
        _ver_major, _ver_minor, _thiszone, _sigfigs, _snaplen, linktype = struct.unpack(
            endian + "HHiIII", header
        )
        if linktype not in SUPPORTED_LINKTYPES:
            raise ValueError(
                f"{path}: link type {linktype} is not one of the supported types "
                f"{sorted(SUPPORTED_LINKTYPES)} (Ethernet / Linux cooked v1 / Linux cooked "
                "v2) - e.g. `tcpdump -i any` produces Linux cooked framing, which is now "
                "supported; other link types are not."
            )
        while True:
            rec_header = f.read(16)
            if len(rec_header) < 16:
                return
            ts_sec, ts_usec, incl_len, _orig_len = struct.unpack(endian + "IIII", rec_header)
            packet = f.read(incl_len)
            if len(packet) < incl_len:
                return
            yield ts_sec + ts_usec / 1_000_000.0, packet, linktype


def parse_ipv4_tcp(packet: bytes, linktype: int = LINKTYPE_ETHERNET):
    """Return (src_ip, src_port, dst_ip, dst_port, seq, payload) for an
    IPv4/TCP packet framed per `linktype`, or None if it isn't one.

    Supports Ethernet (linktype 1) and both "Linux cooked capture" variants
    (linktype 113/276) produced by `tcpdump -i any`, since the pseudo-`any`
    device has no single, consistent L2 header to use real Ethernet framing."""
    if linktype == LINKTYPE_LINUX_SLL2:
        # 20-byte SLL2 header: protocol_type(2) reserved(2) if_index(4)
        # link_layer_type(2) packet_type(1) addr_len(1) addr(8).
        if len(packet) < 20:
            return None
        eth_type = struct.unpack(">H", packet[0:2])[0]
        offset = 20
    elif linktype == LINKTYPE_LINUX_SLL:
        # 16-byte SLL header: packet_type(2) addr_type(2) addr_len(2) addr(8)
        # protocol_type(2).
        if len(packet) < 16:
            return None
        eth_type = struct.unpack(">H", packet[14:16])[0]
        offset = 16
    else:
        if len(packet) < 14:
            return None
        eth_type = struct.unpack(">H", packet[12:14])[0]
        offset = 14
        if eth_type == 0x8100:  # 802.1Q VLAN tag
            if len(packet) < 18:
                return None
            eth_type = struct.unpack(">H", packet[16:18])[0]
            offset = 18

    if eth_type != 0x0800:  # IPv4
        return None

    ip = packet[offset:]
    if len(ip) < 20:
        return None
    ver_ihl = ip[0]
    ihl = (ver_ihl & 0x0F) * 4
    proto = ip[9]
    if proto != 6:  # TCP
        return None
    src_ip = ".".join(str(b) for b in ip[12:16])
    dst_ip = ".".join(str(b) for b in ip[16:20])
    tcp = ip[ihl:]
    if len(tcp) < 20:
        return None
    src_port, dst_port, seq = struct.unpack(">HHI", tcp[0:8])
    data_offset = (tcp[12] >> 4) * 4
    payload = tcp[data_offset:]
    return src_ip, src_port, dst_ip, dst_port, seq, bytes(payload)


def reassemble_streams(pcap_path, host, port):
    """Reconstruct the two directional byte streams (app->panel, panel->app)
    for the single TCP session in this capture that talks to host:port.
    Best-effort ordering by TCP sequence number with duplicate-segment
    dedup - adequate for a short, local/on-path capture, not a general
    TCP reassembly implementation."""
    to_panel = {}    # seq -> payload
    from_panel = {}  # seq -> payload
    client_ip = None
    packet_count = 0
    matched_count = 0

    for _ts, packet, linktype in read_pcap_packets(pcap_path):
        packet_count += 1
        parsed = parse_ipv4_tcp(packet, linktype)
        if parsed is None:
            continue
        src_ip, src_port, dst_ip, dst_port, seq, payload = parsed
        if not payload:
            continue
        if dst_ip == host and dst_port == port:
            matched_count += 1
            client_ip = client_ip or src_ip
            to_panel.setdefault(seq, payload)
        elif src_ip == host and src_port == port:
            matched_count += 1
            from_panel.setdefault(seq, payload)

    def flatten(segments: dict) -> bytes:
        buf = bytearray()
        for _seq, payload in sorted(segments.items()):
            buf += payload
        return bytes(buf)

    return {
        "packet_count": packet_count,
        "matched_count": matched_count,
        "client_ip": client_ip,
        "to_panel": flatten(to_panel),
        "from_panel": flatten(from_panel),
    }


# --------------------------------------------------------------------------
# Connect-protocol frame decoder, adapted from SPIKE-002's live-socket
# _recv_frame to instead walk a static byte buffer already captured on disk.
# --------------------------------------------------------------------------


def decode_frames(buf: bytes, direction: str):
    """Yield (offset, msg_type, seq, cmd_or_none, body) for every valid
    Connect-protocol frame found in buf, resyncing past any non-conforming
    byte instead of stopping - same policy as SPIKE-002's live client."""
    i = 0
    n = len(buf)
    skipped_total = 0
    skipped_run_start = None
    while i < n:
        if buf[i] != HEADER_START:
            if skipped_run_start is None:
                skipped_run_start = i
            i += 1
            skipped_total += 1
            continue
        if i + LENGTH_HEADER > n:
            break
        msg_type, msg_length, msg_seq = buf[i + 1], buf[i + 2], buf[i + 3]
        if not (LENGTH_HEADER + 1 <= msg_length <= 255) or i + msg_length > n:
            if skipped_run_start is None:
                skipped_run_start = i
            i += 1
            skipped_total += 1
            continue
        frame = buf[i : i + msg_length]
        payload, msg_crc = frame[LENGTH_HEADER:-1], frame[-1]
        expected_crc = crc8(frame[:-1])
        if msg_crc != expected_crc:
            if skipped_run_start is None:
                skipped_run_start = i
            i += 1
            skipped_total += 1
            continue

        if skipped_run_start is not None:
            run_len = i - skipped_run_start
            print(
                f"  [{direction}] [resync] skipped {run_len} non-frame byte(s) at offset "
                f"{skipped_run_start}: {buf[skipped_run_start:i].hex()}"
            )
            skipped_run_start = None

        if msg_type == HEADER_TYPE_COMMAND and payload:
            yield i, msg_type, msg_seq, payload[0], payload[1:]
        elif msg_type == HEADER_TYPE_RESPONSE and payload:
            yield i, msg_type, msg_seq, payload[0], payload[1:]
        else:
            yield i, msg_type, msg_seq, None, payload
        i += msg_length

    if skipped_run_start is not None:
        run_len = n - skipped_run_start
        print(
            f"  [{direction}] [resync] skipped {run_len} trailing non-frame byte(s) at offset "
            f"{skipped_run_start}: {buf[skipped_run_start:n].hex()}"
        )

    if skipped_total:
        print(f"  [{direction}] total non-frame bytes skipped: {skipped_total} / {n}")


def run_analysis(pcap_path):
    print("=== SPIKE-005 experiment: decode app arm/disarm commands from a real capture ===")
    print(f"Capture file: {pcap_path}")
    print(f"Panel target: {HOST}:{PORT}")
    print()

    streams = reassemble_streams(pcap_path, HOST, PORT)
    print(f"Packets in capture: {streams['packet_count']}")
    print(f"Packets matching {HOST}:{PORT}: {streams['matched_count']}")
    print(f"Inferred app IP: {streams['client_ip']}")
    print(f"Reassembled app->panel bytes: {len(streams['to_panel'])}")
    print(f"Reassembled panel->app bytes: {len(streams['from_panel'])}")
    print()

    if streams["matched_count"] == 0:
        print(
            "FATAL: no packets in this capture matched the configured panel host:port. "
            "Check TEXECOM_HOST/TEXECOM_PORT and that the capture actually includes the "
            "app<->panel conversation (see SPIKE.md Part A)."
        )
        return

    commands_seen = []
    responses_seen = []
    events_seen = []

    print("--- app -> panel (commands) ---")
    for offset, msg_type, seq, cmd, body in decode_frames(streams["to_panel"], "app->panel"):
        if msg_type == HEADER_TYPE_COMMAND:
            name = KNOWN_COMMANDS.get(cmd, "UNKNOWN/undocumented command")
            print(f"  offset={offset} seq={seq} cmd={cmd} ({name}) body={body.hex()}")
            commands_seen.append((offset, seq, cmd, body))
        else:
            print(f"  offset={offset} seq={seq} unexpected type={msg_type:#x} raw={body.hex()}")

    print()
    print("--- panel -> app (responses / unsolicited events) ---")
    for offset, msg_type, seq, cmd, body in decode_frames(streams["from_panel"], "panel->app"):
        if msg_type == HEADER_TYPE_RESPONSE:
            print(f"  offset={offset} seq={seq} RESPONSE to cmd={cmd} body={body.hex()}")
            responses_seen.append((offset, seq, cmd, body))
        elif msg_type == HEADER_TYPE_MESSAGE:
            decoded = decode_message(bytes([cmd]) + body if cmd is not None else body)
            print(f"  offset={offset} seq={seq} {decoded} raw={body.hex()}")
            events_seen.append((offset, seq, decoded))
        else:
            print(f"  offset={offset} seq={seq} unexpected type={msg_type:#x} raw={body.hex()}")

    print()
    print("=== Summary ===")
    print(f"Commands decoded from app->panel stream: {len(commands_seen)}")
    unknown_commands = {cmd for _o, _s, cmd, _b in commands_seen if cmd not in KNOWN_COMMANDS}
    print(f"Distinct command bytes not in the already-known command set: {sorted(unknown_commands)}")
    print(f"Responses decoded from panel->app stream: {len(responses_seen)}")
    print(f"Unsolicited AREA/LOG/ZONE/etc. events decoded from panel->app stream: {len(events_seen)}")
    if not unknown_commands and commands_seen:
        print(
            "NOTE: every decoded command byte matches this project's already-known, "
            "read-only command set - no new arm/disarm command was found. Either the "
            "app didn't send one during this capture window, or it is using a command "
            "byte already reserved for something else (would need the response/event "
            "correlation above to disambiguate), or the traffic is encrypted (see "
            "SPIKE.md's AES risk) and what's being decoded here is coincidental noise."
        )
    if len(commands_seen) == 0 and len(streams["to_panel"]) > 0:
        print(
            "NOTE: app->panel bytes were captured but zero valid Connect-protocol frames "
            "decoded from them - this is the concrete signal called out in SPIKE.md that "
            "the traffic may be AES-encrypted rather than plaintext Connect-protocol."
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <capture.pcap>", file=sys.stderr)
        sys.exit(2)
    run_analysis(sys.argv[1])
