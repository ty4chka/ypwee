#!/usr/bin/env python3
"""WEB relay extra checks: carrier PING/PONG, WS PING, WINDOW no-op, CLOSE echo.

Builds on the ws_client.py e2e (upgrade + WELCOME + OPEN + DATA) and then
exercises the auxiliary carrier/WS control frames against the same session.
"""
import base64
import hashlib
import os
import socket
import struct
import sys
import time

PROXY = ("127.0.0.1", 1443)
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_send(sock, payload: bytes, opcode=2):
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    sock.sendall(bytes(header) + payload)


def ws_recv(sock):
    def rd(n):
        b = b""
        while len(b) < n:
            p = sock.recv(65536)
            if not p:
                raise EOFError
            b += p
        return b

    h = rd(2)
    opcode = h[0] & 0x0F
    ln = h[1] & 0x7F
    if ln == 126:
        ln = struct.unpack(">H", rd(2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", rd(8))[0]
    return opcode, rd(ln)


def carrier(ftype, sid, payload=b""):
    return struct.pack(">BI", ftype, (sid << 8) | len(payload))[:8] + payload


def carrier_parse(data):
    frames = []
    off = 0
    while off + 8 <= len(data):
        ftype = data[off]
        sid = int.from_bytes(data[off + 1 : off + 4], "big")
        ln = int.from_bytes(data[off + 4 : off + 8], "big")
        if off + 8 + ln > len(data):
            break
        frames.append((ftype, sid, data[off + 8 : off + 8 + ln]))
        off += 8 + ln
    return frames


def main():
    s = socket.create_connection(PROXY, timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += s.recv(4096)
    head = resp.split(b"\r\n\r\n")[0].decode()
    assert "101" in head.splitlines()[0], "no 101"
    want = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    assert f"Sec-WebSocket-Accept: {want}" in head, "bad accept"
    print("[x] upgrade ok")

    ws_send(s, carrier(0x10, 0, b"\x01"))
    opcode, msg = ws_recv(s)
    frames = carrier_parse(msg)
    assert frames and frames[0][0] == 0x11 and frames[0][1] == 0, f"no WELCOME: {frames}"
    print("[x] WELCOME received")

    ws_send(s, carrier(0x01, 1))
    time.sleep(0.3)
    print("[x] OPEN sid=1 sent")
    s.settimeout(5)

    # 1) carrier PING 0x05 -> PONG 0x06, same sid, payload echoed
    ws_send(s, carrier(0x05, 1, b"PINGPAYLOAD"))
    opcode, msg = ws_recv(s)
    frames = carrier_parse(msg)
    assert frames and frames[0][0] == 0x06, f"no carrier PONG: {frames}"
    assert frames[0][1] == 1, f"sid mismatch: {frames}"
    assert frames[0][2] == b"PINGPAYLOAD", f"payload mismatch: {frames}"
    print("[x] carrier PING -> PONG (sid=1, payload echoed)")

    # 2) WS-level PING opcode 0x9 -> PONG opcode 0xA
    ws_send(s, b"wspingdata", opcode=0x9)
    opcode, msg = ws_recv(s)
    assert opcode == 0xA, f"expected WS PONG 0xA, got op={opcode:#x}"
    print("[x] WS PING 0x9 -> PONG 0xA")

    # 3) WINDOW 0x04 -> must not disconnect; follow-up carrier PING still works
    ws_send(s, carrier(0x04, 1, struct.pack(">Q", 1000)))
    time.sleep(0.3)
    ws_send(s, carrier(0x05, 1, b"after-window"))
    opcode, msg = ws_recv(s)
    frames = carrier_parse(msg)
    assert frames and frames[0][0] == 0x06 and frames[0][1] == 1, f"WINDOW killed session: {frames}"
    assert frames[0][2] == b"after-window", f"payload mismatch: {frames}"
    print("[x] WINDOW 0x04 ignored, session alive")

    # 4) carrier CLOSE 0x03 -> echoed CLOSE frame + clean socket close
    ws_send(s, carrier(0x03, 1, b"\x00\x01"))
    opcode, msg = ws_recv(s)
    frames = carrier_parse(msg)
    assert frames and frames[0][0] == 0x03, f"no CLOSE echo: {frames}"
    assert frames[0][1] == 1, f"sid mismatch: {frames}"
    print("[x] CLOSE echoed")
    # expect FIN: server should close the TCP socket
    s.settimeout(5)
    try:
        tail = s.recv(4096)
    except socket.timeout:
        tail = b"<timeout>"
    assert tail == b"", f"expected clean close, got {tail!r}"
    print("[x] socket closed cleanly")

    print("[x] WS EXTRA OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
