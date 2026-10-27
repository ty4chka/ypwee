# Existing projects — what we read

| Project | Lang | Does | Notes |
|---|---|---|---|
| sleep3r/mtproto.zig | Zig | MTProto (FakeTLS), WEB relay, DPI-bypass modules, `mtbuddy` CLI | Self-reported: 177 KB binary, ~0.75 MB RSS, 0 deps. README says Telegram calls are not supported (they need SOCKS-style paths). MIT. |
| valnesfjord/tg-ws-proxy-rs | Rust | Local MTProto → WebSocket bridge for Desktop, optional inbound FakeTLS | Port of Flowseal/tg-ws-proxy; v2.2.5-beta.1 notes address memory growth (#97, #113). Can fetch a Cloudflare domain list from GitHub. |
| Telemt | Rust | MTProxy server, FakeTLS, masking | Per mtproto.zig's table: ~15 MB, 423 crates, ~5–6 s startup. |
| mtg | Go | MTProxy, FakeTLS | Per mtproto.zig's table: ~13 MB, 78 modules. |
| Official MTProxy | C | Reference MTProxy | Per mtproto.zig's table: 524 KB, 8 MB RSS, needs openssl + zlib. |

Caveat: size/RSS/startup numbers above come from the mtproto.zig README (a competitor). ypwee will measure all of them itself on the same machine before claiming anything.

Not yet reviewed: SOCKS5 servers (microsocks, 3proxy, shadowsocks-rust, sing-box) — next pass.
