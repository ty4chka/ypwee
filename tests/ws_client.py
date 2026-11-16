#!/usr/bin/env python3
"""WEB relay e2e: WebSocket carrier over the ypwee MTProto port.

GET (HTTP) -> 101 upgrade -> WS binary frames with tdesktop carrier frames:
HELLO(0x10) -> WELCOME(0x11) -> OPEN(sid=1) -> DATA = obfuscated2 MTProto bytes.
The proxy relays DATA to its own MTProto backend (fake DC via dc-override) and
wraps the DC reply into DATA frames back over the same WS.
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
    # read 101 response
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += s.recv(4096)
    head = resp.split(b"\r\n\r\n")[0].decode()
    print("[ws] upgrade:", head.splitlines()[0])
    assert "101" in head.splitlines()[0], "no 101"
    want = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    assert f"Sec-WebSocket-Accept: {want}" in head, "bad accept"
    print("[ws] accept verified")

    # HELLO v1 (sid 0, payload 01)
    ws_send(s, carrier(0x10, 0, b"\x01"))
    opcode, msg = ws_recv(s)
    frames = carrier_parse(msg)
    assert frames and frames[0][0] == 0x11 and frames[0][1] == 0, f"no WELCOME: {frames}"
    print("[ws] WELCOME received")

    # OPEN sid=1 (one MTProto stream through the proxy's own MTProto backend)
    ws_send(s, carrier(0x01, 1))
    time.sleep(0.3)

    # MTProto stream: obfuscated2 nonce + intermediate req_pq_multi (fake DC answers via dc-override)
    import hashlib as hl

    secret_hex = "ee367a189aee18fa31c190054efd4a8e9573746f726167652e676f6f676c65617069732e636f6d"
    raw = bytes.fromhex(secret_hex)
    key16 = raw[1:17]

    # build obfuscated2 frame like mt_client.py (56 plain + 8 enc)
    while True:
        frame = bytearray(os.urandom(64))
        if frame[0] == 0xEF:
            continue
        f4 = struct.unpack("<I", frame[:4])[0]
        if f4 in (0x44414548, 0x54534F50, 0x20544547, 0x4954504F, 0x02010316, 0xDDDDDDDD, 0xEEEEEEEE):
            continue
        if frame[4] | frame[5] | frame[6] | frame[7] == 0:
            continue
        break
    frame[56:60] = b"\xdd\xdd\xdd\xdd"
    frame[60:62] = struct.pack("<h", 2)
    frame = bytes(frame)
    enc_key = hl.sha256(frame[8:40] + key16).digest()
    enc_iv = int.from_bytes(frame[40:56], "big")

    from Crypto.Cipher import AES as _AES

    ecb = _AES.new(enc_key, _AES.MODE_ECB)

    def stream_apply(iv, data):
        out = b""
        ctr = iv
        for i in range(0, len(data), 16):
            out += bytes(a ^ b for a, b in zip(data[i : i + 16], ecb.encrypt(ctr.to_bytes(16, "big"))))
            ctr = (ctr + 1) % (1 << 128)
        return out

    ks = stream_apply(enc_iv, frame)
    nonce_wire = frame[:56] + ks[56:64]
    # unencrypted MTProto req_pq_multi inside intermediate framing (what the client stream carries)
    body = struct.pack("<I", 0xBE7E8EF1) + os.urandom(16)
    msg_id = int(time.time() * (1 << 32)) & ~3
    mt = struct.pack("<qqI", 0, msg_id, len(body)) + body
    clear_payload = struct.pack("<I", len(mt)) + mt
    # client->proxy stream after nonce consumes 64 bytes
    tail = stream_apply(enc_iv, b"\x00" * 64 + clear_payload)[64:]
    ws_send(s, carrier(0x02, 1, nonce_wire + tail))
    print("[ws] MTProto stream bytes sent via DATA")

    s.settimeout(15)
    got_data = b""
    deadline = time.time() + 12
    while time.time() < deadline and len(got_data) < 5:
        try:
            opcode, msg = ws_recv(s)
        except (socket.timeout, EOFError):
            break
        for ftype, sid, payload in carrier_parse(msg):
            if ftype == 0x02 and sid == 1:
                got_data += payload
                print(f"[ws] DATA sid=1 +{len(payload)}B (total {len(got_data)})")
            elif ftype == 0x03:
                print("[ws] CLOSE from relay")
                return 1
    if not got_data:
        print("[ws] FAIL: no DATA frames from backend")
        return 1
    print("[ws] first bytes:", got_data[:8].hex())
    print("[ws] WEB E2E OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
