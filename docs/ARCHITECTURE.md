# ypwee — architecture (draft)

Status: design. Nothing below is implemented yet.

## One port, many protocols

A single `SocketPoller` (epoll/kqueue) loop accepts connections and looks at the first bytes:

| First bytes | Handler |
|---|---|
| `0x05` | SOCKS5 (auth required by default) |
| `CONNECT ` | HTTP CONNECT proxy |
| TLS ClientHello with a valid secret-derived digest | FakeTLS, then MTProto obfuscated2 |
| TLS ClientHello for the relay host (SNI) | WEB relay (Telegram Desktop 7.1+) |
| anything else / invalid secret | forward to the real masking site (anti-probing) |

## Gaps in Yukino `std` that we must fill (found in the docs)

| Need | In `std`? | Plan |
|---|---|---|
| TCP, epoll poller, TLS client/server, HTTP codec | yes (`std.net`) | use as is |
| SHA-256, HMAC, ChaCha20, HKDF | yes (`std.hash`, `std.crypto`) | use as is |
| AES-256-CTR (MTProto obfuscated2) | not listed | implement in ypwee with NIST test vectors, or bind via `cfun` |
| WebSocket (RFC 6455) | not listed | implement in ypwee (`src/web/ws.ykn`) |
| Raw TLS record control for FakeTLS | not needed | FakeTLS is built on raw `TcpStream` bytes |

## WEB relay (from public notes of mtproto.zig v1.11.0 — verify against tdesktop source before coding)

- Telegram Desktop 7.1 added a fourth proxy type, WEB; MTProto runs over WebSocket inside a hidden WebView at `https://<domain>/?bridge=<capability>`.
- Capability: `base64url(HMAC-SHA256(secret, "tdesktop-web-proxy-bridge-v1\n" + host))`.
- Frames v1: `type:u8 | stream_id:u24 | length:u32`.

## Testing

- Unit tests via `yukino test` (`#[test]`, `#[timeout_ms]`).
- Protocol vectors: AES-CTR (NIST), HMAC, RFC 6455 frames, SOCKS5 (RFC 1928/1929).
- Soak test in CI: thousands of idle connections, assert flat RSS.
