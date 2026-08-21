#!/usr/bin/env python3
"""
Spike experiment: SPIKE-001 zone enumeration feasibility.

Read-only probe against a live Texecom Premier Elite panel (Connect protocol,
ComIP transport) to test whether zone count, type, and name can be retrieved
programmatically via GETPANELIDENTIFICATION + GETZONEDETAILS, without a
hand-maintained zone list in configuration.

Reimplemented from first principles based on this project's own reading of the
public davidMbrooke/texecom-connect source (see SPIKE.md ## Research), rather
than importing that library directly, per RISK-008 (keep this project's own
protocol notes self-produced from packet-level reasoning).

Sends no arm/disarm or other state-changing command -- only LOGIN (required by
the protocol before any other command is accepted) and two read/query commands
(GETPANELIDENTIFICATION, GETZONEDETAILS), each queried once per zone.
"""

import os
import socket
import time

HOST = os.environ.get("TEXECOM_HOST", "").strip()
PORT = int(os.environ.get("TEXECOM_PORT", "10001"))
UDL_PASSWORD = os.environ.get("TEXECOM_UDL_PASSWORD", "")

HEADER_START = ord("t")
TYPE_COMMAND = ord("C")
TYPE_RESPONSE = ord("R")
TYPE_MESSAGE = ord("M")

CMD_LOGIN = 1
CMD_GETZONEDETAILS = 3
CMD_GETPANELIDENTIFICATION = 22

ACK = 0x06
NAK = 0x15

CMD_TIMEOUT = 3.0
CMD_RETRIES = 3
INTER_ZONE_DELAY = 0.05

ZONE_TYPES = {
    0: "Unused", 1: "Entry/Exit 1", 2: "Entry/Exit 2", 3: "Interior", 4: "Perimeter",
    5: "24hr Audible", 6: "24hr Silent", 7: "Audible PA", 8: "Silent PA", 9: "Fire Alarm",
    10: "Medical", 11: "24Hr Gas Alarm", 12: "Auxiliary Alarm", 13: "24hr Tamper Alarm",
    14: "Exit Terminator", 15: "Keyswitch - Momentary", 16: "Keyswitch - Latching",
    17: "Security Key", 18: "Omit Key", 19: "Custom Alarm", 20: "Confirmed PA Audible",
    21: "Confirmed PA Audible",
}


def crc8(data: bytes) -> int:
    """Non-reflected CRC-8, polynomial x^8+x^7+x^2+1, init 0xff.

    Matches crcmod.mkCrcFun(poly=0x185, rev=False, initCrc=0xff), which
    texecomConnect.py uses for Texecom Connect framing (see SPIKE.md Research).
    """
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x85) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class ProtocolError(Exception):
    pass


class TexecomProbe:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.seq = 0

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(CMD_TIMEOUT)
        self.sock.connect((self.host, self.port))
        # Texecom guidance: wait >=500ms after connect before sending LOGIN,
        # or the panel ignores it.
        time.sleep(0.5)

    def close(self):
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
            self.sock = None

    def _next_seq(self):
        seq = self.seq
        self.seq = (self.seq + 1) % 256
        return seq

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ProtocolError(
                    "connection closed by panel while reading {} bytes (got {})".format(n, len(buf))
                )
            buf += chunk
        return buf

    def send_command(self, cmd_byte, body=b""):
        payload_body = bytes([cmd_byte]) + body
        seq = self._next_seq()
        header = bytes([HEADER_START, TYPE_COMMAND, len(payload_body) + 5, seq])
        frame = header + payload_body
        frame += bytes([crc8(frame)])

        for attempt in range(CMD_RETRIES):
            self.sock.send(frame)
            try:
                return self._recv_response(cmd_byte, seq)
            except socket.timeout:
                print(
                    "  [retry {}/{}] timeout waiting for response to cmd {}".format(
                        attempt + 1, CMD_RETRIES, cmd_byte
                    )
                )
                continue
        raise ProtocolError("no response to cmd {} after {} attempts".format(cmd_byte, CMD_RETRIES))

    def _recv_response(self, expected_cmd, expected_seq):
        deadline = time.time() + CMD_TIMEOUT
        while True:
            if time.time() > deadline:
                raise socket.timeout()
            header = self._recv_exact(4)
            if header[:3] == b"+++":
                raise ProtocolError("panel forcibly dropped the connection (+++ signal)")
            if header[0] != HEADER_START:
                raise ProtocolError("unexpected frame start byte: 0x{:02x}".format(header[0]))
            msg_type, msg_len, msg_seq = header[1], header[2], header[3]
            body_and_crc = self._recv_exact(msg_len - 4)
            body, crc_byte = body_and_crc[:-1], body_and_crc[-1]
            expected_crc = crc8(header + body)
            if crc_byte != expected_crc:
                raise ProtocolError(
                    "CRC mismatch: got 0x{:02x}, expected 0x{:02x}".format(crc_byte, expected_crc)
                )
            if msg_type == TYPE_MESSAGE:
                print("  [info] ignoring unsolicited message while awaiting response (seq {})".format(msg_seq))
                continue
            if msg_type != TYPE_RESPONSE:
                raise ProtocolError("unexpected frame type: 0x{:02x}".format(msg_type))
            if msg_seq != expected_seq:
                continue
            resp_cmd, resp_payload = body[0], body[1:]
            if resp_cmd != expected_cmd:
                raise ProtocolError("response cmd id {} != expected {}".format(resp_cmd, expected_cmd))
            return resp_payload

    def login(self, password: str):
        body = password.encode("ascii")
        resp = self.send_command(CMD_LOGIN, body)
        if len(resp) == 1 and resp[0] == ACK:
            return True
        if len(resp) == 1 and resp[0] == NAK:
            return False
        raise ProtocolError("unexpected LOGIN response: {!r}".format(resp))

    def get_panel_identification(self):
        resp = self.send_command(CMD_GETPANELIDENTIFICATION)
        if len(resp) != 32:
            raise ProtocolError("GETPANELIDENTIFICATION: expected 32 bytes, got {}".format(len(resp)))
        text = resp.decode("ascii", errors="replace")
        return {"raw": text, "parts": text.split()}

    def get_zone_details(self, zone_number: int):
        resp = self.send_command(CMD_GETZONEDETAILS, bytes([zone_number]))
        n = len(resp)
        if n == 34:
            zone_type, text = resp[0], resp[2:]
        elif n == 35:
            zone_type, text = resp[0], resp[3:]
        elif n == 41:
            zone_type, text = resp[0], resp[9:]
        else:
            raise ProtocolError("GETZONEDETAILS: unexpected response length {}".format(n))
        name = text.replace(b"\x00", b" ").decode("ascii", errors="replace").strip()
        return {"zone_type": zone_type, "name": name}


def main():
    if not HOST:
        raise SystemExit(
            "Set TEXECOM_HOST to the panel address (no default). "
            "Optional: TEXECOM_PORT (default 10001), TEXECOM_UDL_PASSWORD."
        )
    print("=== SPIKE-001 experiment: zone enumeration feasibility ===")
    print("Target: {}:{}".format(HOST, PORT))
    probe = TexecomProbe(HOST, PORT)
    criteria = {
        "zone_count_reported": None,
        "zone_type_reported": None,
        "zone_name_reported": None,
        "no_crash_or_collision": True,
    }
    try:
        probe.connect()
        print("[ok] TCP connected")

        logged_in = probe.login(UDL_PASSWORD)
        print("[{}] LOGIN (password={!r})".format("ok" if logged_in else "NAK", UDL_PASSWORD))
        if not logged_in:
            print("Cannot proceed without a successful login; aborting.")
            criteria["no_crash_or_collision"] = "inconclusive: login NAK, no further commands sent"
            return criteria

        ident = probe.get_panel_identification()
        print("[ok] GETPANELIDENTIFICATION raw: {!r}".format(ident["raw"]))
        print("     parsed parts: {}".format(ident["parts"]))
        zone_count = None
        if len(ident["parts"]) >= 2:
            try:
                zone_count = int(ident["parts"][1])
            except ValueError:
                pass
        criteria["zone_count_reported"] = zone_count
        if not zone_count or zone_count <= 0:
            print("[fail] could not parse a usable zone count from panel identification response")
            return criteria
        print("[ok] panel reports {} zones".format(zone_count))

        zone_results = []
        types_seen = set()
        names_seen = 0
        for zone_number in range(1, zone_count + 1):
            try:
                details = probe.get_zone_details(zone_number)
            except (ProtocolError, socket.timeout) as e:
                print("  [error] zone {}: {}".format(zone_number, e))
                zone_results.append((zone_number, None, None, str(e)))
                time.sleep(INTER_ZONE_DELAY)
                continue
            types_seen.add(details["zone_type"])
            if details["name"]:
                names_seen += 1
            zone_results.append((zone_number, details["zone_type"], details["name"], None))
            type_label = ZONE_TYPES.get(details["zone_type"], "Unknown({})".format(details["zone_type"]))
            print("  zone {:>2}: type={:<22} name={!r}".format(zone_number, type_label, details["name"]))
            time.sleep(INTER_ZONE_DELAY)

        queried_ok = sum(1 for r in zone_results if r[3] is None)
        criteria["zone_type_reported"] = "{} distinct type codes seen across {}/{} zones queried ok".format(
            len(types_seen), queried_ok, zone_count
        )
        criteria["zone_name_reported"] = "{}/{} zones returned non-empty name text".format(
            names_seen, queried_ok
        )

        print()
        print("=== Summary ===")
        print("Zone count from panel: {}".format(zone_count))
        print("Zones successfully queried: {}/{}".format(queried_ok, zone_count))
        print("Distinct zone type codes seen: {}".format(sorted(types_seen)))
        print("Zones with non-empty name text: {}/{}".format(names_seen, queried_ok))

    except (ProtocolError, socket.timeout, OSError) as e:
        print("[fail] experiment aborted: {}".format(e))
        criteria["no_crash_or_collision"] = "no: {}".format(e)
    finally:
        probe.close()
        print("[ok] socket closed cleanly")

    return criteria


if __name__ == "__main__":
    result = main()
    print()
    print("=== Decision criteria (raw) ===")
    for k, v in result.items():
        print("{}: {}".format(k, v))
