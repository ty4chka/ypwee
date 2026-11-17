<div align="center">

<img src="assets/banner.svg" alt="ypwee" width="100%">

<p>One small native proxy for Telegram — MTProto, SOCKS5 and WEB in a single binary.<br>Written in <a href="https://github.com/yukitsuri/yukino">Yukino</a>.</p>

<p><b>English</b> · <a href="README.ru.md">Русский</a></p>

<p>
<img alt="tests" src="https://img.shields.io/badge/tests-44%2F44-brightgreen">
<img alt="platforms" src="https://img.shields.io/badge/platforms-amd64%20%7C%20arm64-blue">
<img alt="size" src="https://img.shields.io/badge/binary-2.6%20MB-lightgrey">
</p>

</div>

---

## What it is

`ypwee` is a proxy server for Telegram. One binary, one port, one config. Three protocols run at once and are told apart by the first bytes of a connection.

| Protocol | What it is for |
|---|---|
| **MTProto** | proxy inside Telegram (`dd`/`ee` secrets, FakeTLS, several users) |
| **SOCKS5** | Telegram calls, plain SOCKS5 with password and ACL |
| **WEB** | the "WEB" proxy type of Telegram Desktop 7.1+, over ordinary HTTPS |

Plus masking: a wrong secret or a port scanner gets the real website instead. The prober sees an ordinary TLS handshake.

## Install

Prebuilt binaries are in [releases](https://github.com/ty4chka/ypwee/releases). No `curl | sudo bash`: download, unpack, run.

```bash
# amd64
curl -LO https://github.com/ty4chka/ypwee/releases/latest/download/ypwee-linux-amd64
chmod +x ypwee-linux-amd64

# arm64 (Raspberry Pi, VPS, phones)
curl -LO https://github.com/ty4chka/ypwee/releases/latest/download/ypwee-linux-arm64
chmod +x ypwee-linux-arm64
```

Verify integrity:

```bash
curl -LO https://github.com/ty4chka/ypwee/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS
```

## Run

Minimal config — a file `ypwee.conf` next to the binary:

```ini
user = alice:myPassword
allow = *

# MTProto secret from @MTProxybot: dd + 32 hex chars, or ee + host
mtproto-secret = ee367a189aee18fa31c190054efd4a8e9573746f726167652e676f6f676c65617069732e636f6d
mtproto-port = 0.0.0.0:443
```

```bash
./ypwee-linux-amd64 ypwee.conf
```

You will see:

```
[ypwee] socks5 on 127.0.0.1:1080
[ypwee] http on 127.0.0.1:8081
[ypwee] mtproto on 0.0.0.0:443
```

Then in Telegram: **Settings → Advanced → Proxy → MTProto**, enter the server address, port and secret.

## One port, three protocols

```
client
  │
  ├─ 0x05 ────────────────► SOCKS5
  ├─ CONNECT ─────────────► HTTP proxy
  ├─ TLS + valid secret ──► FakeTLS → MTProto
  ├─ TLS + relay host ────► WEB relay
  └─ anything else ───────► mask: the real website
```

## Config

| Key | Meaning | Default |
|---|---|---|
| `user` | SOCKS5 login:password, may repeat | — |
| `allow` | allow-list of target hosts, `*` for all | `*` |
| `allow-private` | allow private addresses as targets | `false` |
| `mtproto-secret` | MTProto secret (`dd…` or `ee…`) | — |
| `mtproto-port` | MTProto address and port | — |
| `socks5` | SOCKS5 address and port | `127.0.0.1:1080` |
| `http` | HTTP proxy address and port | `127.0.0.1:8081` |
| `max-conns` | connection limit | `1024` |

Full list — in [`ypwee.example.toml`](ypwee.example.toml).

## Build from source

You need the [Yukino](https://github.com/yukitsuri/yukino) compiler (`yukic`) and `lld`.

```bash
git clone https://github.com/ty4chka/ypwee.git
cd ypwee

# tests: 44/44
yukic --test --entry src/main.ykn -o test.bin -- --error-limit=0
chmod +x test.bin && ./test.bin

# release build
yukic --release --entry src/main.ykn -o ypwee -- --error-limit=0
```

Prebuilt amd64 and arm64 binaries are produced on every push — see [`.github/workflows/build.yml`](.github/workflows/build.yml).

## What is verified

- **44/44 tests** — SHA-1, SHA-256, HMAC, base64/base64url (RFC vectors), AES-CTR (NIST), SOCKS5, HTTP CONNECT, MTProto, WS frames
- **FakeTLS e2e** — MTProto handshake and relay against a local fake DC
- **WebSocket e2e** — WEB relay through the proxy, full HELLO→WELCOME→OPEN→DATA cycle
- **anti-probing** — a wrong secret yields the real website's TLS response

Tests run on amd64 and arm64 in CI.

## Not done yet

- A test against a **real** Telegram DC from a residential IP: datacenters ignore obfs2 from server addresses.
- Signed releases (cosign/provenance) — planned.
- Benchmarks against mtg / Telemt / mtproto.zig — planned.

## License

See [LICENSE](LICENSE).
