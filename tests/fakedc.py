#!/usr/bin/env python3
"""Local fake Telegram DC for ypwee e2e: speaks obfuscated2 (secure dd tag) on 127.0.0.1:9443.

Receives the 64-byte nonce, derives both streams exactly like a real DC,
decrypts the incoming intermediate frame (req_pq_multi), and replies with a
valid resPQ-shaped intermediate frame over the reverse stream.
"""
import hashlib
import os
import socket
import struct
import sys
import threading
import time

from Crypto.Cipher import AES

LISTEN = ("127.0.0.1", 9443)


class Ctr:
    def __init__(self, key, iv):
        self.ecb = AES.new(key, AES.MODE_ECB)
        self.ctr = iv
        self.ks = b""
        self.pos = 0

    def apply(self, data):
        out = bytearray()
        for byte in data:
            if self.pos >= len(self.ks):
                blk = self.ctr.to_bytes(16, "big")
                self.ks += self.ecb.encrypt(blk)
                self.ctr = (self.ctr + 1) % (1 << 128)
            out.append(byte ^ self.ks[self.pos])
            self.pos += 1
        return bytes(out)


def handle(conn):
    try:
        conn.settimeout(10)
        nonce = b""
        while len(nonce) < 64:
            part = conn.recv(64 - len(nonce))
            if not part:
                return
            nonce += part
        # nonce wire form: first 56 plain, last 8 encrypted with enc stream(nonce[8..56])
        enc_key = nonce[8:40]  # DC side: raw nonce bytes ARE the AES key (no hashing)
        enc_iv = int.from_bytes(nonce[40:56], "big")
        enc = Ctr(enc_key, enc_iv)
        dec_blob = enc.apply(nonce)  # advance 4 blocks
        clear_nonce = nonce[:56] + dec_blob[56:64]
        tag = clear_nonce[56:60]
        if tag != b"\xdd\xdd\xdd\xdd":
            print(f"[fakedc] bad tag {tag.hex()}", flush=True)
            return
        dc_idx = struct.unpack("<h", clear_nonce[60:62])[0]
        print(f"[fakedc] handshake ok dc={dc_idx}", flush=True)
        # DC->proxy stream: reversed nonce[8..56]
        rev = nonce[8:56][::-1]
        s2c_key = rev[:32]
        s2c_iv = int.from_bytes(rev[32:48], "big")
        s2c = Ctr(s2c_key, s2c_iv)
        # proxy->DC stream: same as enc (continues after nonce)
        # read one intermediate frame (decrypted by proxy with enc stream)
        buf = b""
        while len(buf) < 4:
            part = conn.recv(4096)
            if not part:
                return
            buf += part
        # NOTE: proxy encrypts payload with the SAME stream as nonce tail (tg_enc), which has
        # already consumed 64 bytes; our enc object is at exactly that offset. Decrypt:
        clear = enc.apply(buf)
        plen = struct.unpack("<I", clear[:4])[0]
        while len(buf) < 4 + plen:
            part = conn.recv(4096)
            if not part:
                return
            buf += part
            clear = enc.apply(buf)
        frame = clear[4 : 4 + plen]
        ctor = struct.unpack("<I", frame[:4])[0] if len(frame) >= 4 else 0
        print(f"[fakedc] got frame len={plen} ctor=0x{ctor:08x}", flush=True)
        # reply: fake resPQ (unencrypted MTProto container, intermediate framed), sent through s2c
        body = struct.pack("<I", 0x05162463) + os.urandom(32)  # resPQ#5162463
        msg_id = int(time.time() * (1 << 32)) & ~7 | 1
        mt = struct.pack("<qqI", 0, msg_id, len(body)) + body
        reply = struct.pack("<I", len(mt)) + mt
        wire = s2c.apply(reply)
        conn.sendall(wire)
        print(f"[fakedc] replied {len(wire)}B", flush=True)
        time.sleep(1)
    except Exception as e:
        print(f"[fakedc] err: {type(e).__name__} {e}", flush=True)
    finally:
        conn.close()


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(8)
    print(f"[fakedc] listening on {LISTEN[0]}:{LISTEN[1]}", flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
