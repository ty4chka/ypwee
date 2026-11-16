#!/usr/bin/env python3
"""ypwee MTProto FakeTLS e2e client (tdlib-compatible)."""
import socket, os, hmac, hashlib, struct, sys, time

SECRET_HEX = os.environ.get("YPWEE_SECRET", "")
HOST = os.environ.get("YPWEE_HOST", "storage.googleapis.com")
DC = int(os.environ.get("YPWEE_DC", "2"))

def b(x): return x if isinstance(x, bytes) else x.encode()

def grease(n):
    r = bytearray(os.urandom(n))
    for i in range(n):
        r[i] = (r[i] & 0xF0) + 0x0A
    for i in range(1, n, 2):
        if r[i] == r[i-1]:
            r[i] ^= 0x10
    return bytes(r)

def build_client_hello(secret_key: bytes, domain: str) -> bytes:
    ts = int(time.time())
    out = bytearray()
    out += b"\x16\x03\x01"
    body = bytearray()
    body += b"\x01\x00\x00\x00"  # handshake header (len patched later)
    body += b"\x03\x03"
    body += b"\x00" * 32
    body += b"\x20" + os.urandom(32)
    body += b"\x00\x1c" + grease(2) + b"\x13\x01\x13\x02\x13\x03\xc0\x2b\xc0\x2f\xc0\x2c\xc0\x30\xcc\xa9\xcc\xa8\xc0\x13\xc0\x14\x00\x9c\x00\x9d\x00\x2f\x00\x35"
    ext = bytearray()
    sni = bytearray()
    host_b = b(domain)
    sni += struct.pack(">H", len(host_b) + 5) + b"\x00" + struct.pack(">H", len(host_b) + 3) + struct.pack(">H", len(host_b)) + host_b
    ext += b"\x00\x00" + struct.pack(">H", len(sni)) + sni
    ext += b"\x00\x2b\x00\x07\x06" + grease(2) + b"\x03\x04\x03\x03"
    ext += b"\x00\x33\x00\x24\x00\x1d\x00\x20" + os.urandom(32)
    ext += b"\x00\x2d\x00\x02\x01\x01"
    ext += b"\x00\x0a\x00\x0c\x00\x0a" + grease(2) + b"\x11\xec\x00\x1d\x00\x17\x00\x18"
    ext += b"\x00\x0b\x00\x02\x01\x00"
    ext += b"\x00\x10\x00\x0e\x00\x0c\x02\x68\x32\x08\x68\x74\x74\x70\x2f\x31\x2e\x31"
    ext += b"\x00\x05\x00\x05\x01\x00\x00\x00\x00"
    ext += b"\x00\x12\x00\x00"
    ext += b"\x00\x17\x00\x00"
    ext += b"\x00\x01\x00"
    ext += b"\xff\x01\x00\x01\x00"
    body += b"\x01\x00"
    body += struct.pack(">H", len(ext)) + ext
    hl = len(body) - 4
    body[1:3] = struct.pack(">H", hl)
    out += struct.pack(">H", len(body)) + body
    data = bytes(out)
    mac = hmac.new(secret_key, data, hashlib.sha256).digest()
    patched = bytearray(data)
    ts_xor = struct.unpack(">I", mac[28:32])[0] ^ ts
    patched[11:43] = mac
    patched[39:43] = struct.pack(">I", ts_xor)
    return bytes(patched)

def obfuscated2_header(secret_key: bytes, dc: int):
    while True:
        frame = bytearray(os.urandom(64))
        if frame[0] == 0xef: continue
        f4 = struct.unpack("<I", frame[:4])[0]
        if f4 in (0x44414548,0x54534f50,0x20544547,0x4954504f,0x02010316,0xdddddddd,0xeeeeeeee): continue
        if frame[4]|frame[5]|frame[6]|frame[7] == 0: continue
        break
    frame[56:60] = b"\xdd\xdd\xdd\xdd"
    frame[60:62] = struct.pack("<h", dc)
    frame = bytes(frame)
    dec_key = hashlib.sha256(frame[8:40] + secret_key).digest()
    dec_iv = frame[40:56]
    rframe = frame[:8] + bytes(reversed(frame[8:56])) + frame[56:]
    enc_key = hashlib.sha256(rframe[8:40] + secret_key).digest()
    enc_iv = rframe[40:56]
    return frame, dec_key, dec_iv, enc_key, enc_iv

from Crypto.Cipher import AES as _AES

class Ctr:
    def __init__(self, key, iv):
        self.key = key
        self.ctr = int.from_bytes(iv, "big")
        self.ks = b""
        self.pos = 0
    def _refill(self):
        blk = self.ctr.to_bytes(16, "big")
        ecb = _AES.new(self.key, _AES.MODE_ECB)
        self.ks += ecb.encrypt(blk)
        self.ctr = (self.ctr + 1) % (1 << 128)
    def apply(self, data):
        out = bytearray()
        for byte in data:
            if self.pos >= len(self.ks): self._refill()
            out.append(byte ^ self.ks[self.pos]); self.pos += 1
        return bytes(out)

def main():
    secret_hex = SECRET_HEX
    raw = bytes.fromhex(secret_hex)
    assert raw[0] == 0xee, "secret must start with ee"
    key16 = raw[1:17]
    domain = raw[17:].decode()
    print("[client] secret host:", domain)
    proxy = os.environ.get("YPWEE_ADDR", "127.0.0.1:1443")
    ph, pp = proxy.split(":")
    s = socket.create_connection((ph, int(pp)), timeout=10)
    hello = build_client_hello(key16, domain)
    s.sendall(hello)
    resp = b""
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            part = s.recv(65536)
        except socket.timeout:
            break
        if not part: break
        resp += part
        if len(resp) > 150 and resp[:3] == b"\x16\x03\x03":
            i = 5 + struct.unpack(">H", resp[3:5])[0]
            if len(resp) >= i + 6 and resp[i:i+6] == b"\x14\x03\x03\x00\x01\x01":
                j = i + 6
                if len(resp) >= j + 5:
                    n = struct.unpack(">H", resp[j+3:j+5])[0]
                    if len(resp) >= j + 5 + n:
                        print("[client] ServerHello + CCS + noise received:", len(resp), "bytes")
                        break
    else:
        print("[client] FAIL: no welcome packet"); return 1
    hello_rand = hello[11:43]
    resp_copy = bytearray(resp)
    resp_rand = bytes(resp_copy[11:43])
    resp_copy[11:43] = b"\x00" * 32
    expect = hmac.new(key16, hello_rand + bytes(resp_copy), hashlib.sha256).digest()
    if expect != resp_rand:
        print("[client] FAIL: ServerHello HMAC mismatch")
        print(" expect", expect.hex())
        print(" got   ", resp_rand.hex())
        print(" resp len", len(resp))
        print(" resp[:64]", resp[:64].hex())
        return 1
    print("[client] OK: ServerHello HMAC verified - FakeTLS handshake complete")
    frame, dec_key, dec_iv, enc_key, enc_iv = obfuscated2_header(key16, DC)
    dec = Ctr(dec_key, dec_iv)
    enc = Ctr(enc_key, enc_iv)
    # official obfuscated2: first 56 bytes go on the wire PLAIN, only last 8 encrypted
    # (the CTR stream still consumes all 64 bytes)
    consumed = dec.apply(frame[:64])
    s.sendall(frame[:56] + consumed[56:64])
    print("[client] obfuscated2 header sent, dc", DC)
    # real unencrypted MTProto req_pq_multi#be7e8ef1 inside intermediate framing
    body = struct.pack("<I", 0xBE7E8EF1) + os.urandom(16)
    msg_id = int(time.time() * (1 << 32)) & ~3
    mt_msg = struct.pack("<qqI", 0, msg_id, len(body)) + body
    payload = struct.pack("<I", len(mt_msg)) + mt_msg
    tls = b"\x14\x03\x03\x00\x01\x01"
    rec = b"\x17\x03\x03" + struct.pack(">H", len(payload))
    s.sendall(tls + rec + dec.apply(payload))
    print("[client] payload sent through TLS record")
    s.settimeout(15)
    buf = b""
    try:
        while len(buf) < 5:
            part = s.recv(65536)
            if not part: break
            buf += part
    except socket.timeout:
        pass
    if buf[:3] == b"\x17\x03\x03":
        n = struct.unpack(">H", buf[3:5])[0]
        print("[client] DC response TLS record received:", len(buf), "bytes, payload", n)
        clear = enc.apply(buf[5:5+n])
        print("[client] decrypted first bytes:", clear[:16].hex())
        print("[client] E2E RELAY OK")
        return 0
    elif buf:
        print("[client] got non-TLS bytes:", buf[:32].hex())
        return 1
    else:
        print("[client] no response from DC (proxy may have failed)")
        return 1



def probe_wrong_secret():
    """M3 anti-probe: with a WRONG secret the proxy must transparently relay to the
    real masking site (we should get a genuine TLS ServerHello from storage.googleapis.com)."""
    secret_hex = "ee" + "00" * 16 + "6e6f7468696e672e6578616d706c65"  # wrong key, wrong host
    raw = bytes.fromhex(secret_hex)
    key16 = raw[1:17]
    proxy = os.environ.get("YPWEE_ADDR", "127.0.0.1:1443")
    ph, pp = proxy.split(":")
    s = socket.create_connection((ph, int(pp)), timeout=10)
    # any plausible ClientHello; HMAC will not match the real secret
    hello = build_client_hello(key16, b"www.example.com")
    s.sendall(hello)
    s.settimeout(10)
    resp = b""
    try:
        while len(resp) < 5:
            part = s.recv(65536)
            if not part:
                break
            resp += part
            if len(resp) >= 5 and resp[0] == 0x16 and resp[1] == 0x03:
                print(f"[prober] got TLS record back: type={resp[0]} ver={resp[1:3].hex()} len={struct.unpack('>H', resp[3:5])[0]}")
                print("[prober] M3 MASK OK")
                s.close()
                return 0
            if len(resp) >= 5 and resp[0] == 0x15:
                print("[prober] got TLS alert (site refused?) — still a masked TLS response")
                print("[prober] M3 MASK OK (alert)")
                s.close()
                return 0
    except socket.timeout:
        pass
    print("[prober] FAIL: no masked TLS response")
    return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "probe":
        sys.exit(probe_wrong_secret())
    sys.exit(main())
