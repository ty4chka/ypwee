<div align="center">

<img src="assets/banner.svg" alt="ypwee" width="100%">

<p>Один маленький нативный прокси для Telegram — MTProto, SOCKS5 и WEB в одном бинарнике.<br>Написан на <a href="https://github.com/yukitsuri/yukino">Yukino</a>.</p>

<p><b>Русский</b> · <a href="README.md">English</a></p>

<p>
<img alt="tests" src="https://img.shields.io/badge/tests-44%2F44-brightgreen">
<img alt="platforms" src="https://img.shields.io/badge/platforms-amd64%20%7C%20arm64-blue">
<img alt="size" src="https://img.shields.io/badge/binary-2.6%20MB-lightgrey">
</p>

</div>

---

## Что это

`ypwee` — прокси-сервер для Telegram. Один бинарник, один порт, один конфиг. Три протокола поднимаются одновременно и различаются по первым байтам соединения.

| Протокол | Для чего |
|---|---|
| **MTProto** | прокси внутри Telegram (`dd`/`ee`-секреты, FakeTLS, несколько пользователей) |
| **SOCKS5** | звонки Telegram, обычный SOCKS5 с паролем и ACL |
| **WEB** | тип прокси «WEB» в Telegram Desktop 7.1+, поверх обычного HTTPS |

Плюс маскировка: если секрет неверный или пришёл сканер — соединение прозрачно уходит на настоящий сайт. Проверяющий видит обычный TLS-хендшейк.

## Установка

Готовые бинарники — в [релизах](https://github.com/ty4chka/ypwee/releases). Никакого `curl | sudo bash`: скачал, распаковал, запустил.

```bash
# amd64
curl -LO https://github.com/ty4chka/ypwee/releases/latest/download/ypwee-linux-amd64
chmod +x ypwee-linux-amd64

# arm64 (Raspberry Pi, VPS, телефоны)
curl -LO https://github.com/ty4chka/ypwee/releases/latest/download/ypwee-linux-arm64
chmod +x ypwee-linux-arm64
```

Проверить целостность:

```bash
curl -LO https://github.com/ty4chka/ypwee/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS
```

## Запуск

Минимальный конфиг — файл `ypwee.conf` рядом с бинарником:

```ini
user = alice:мойПароль
allow = *

# секрет MTProto из @MTProxybot: dd + 32 hex-символа, либо ee + хост
mtproto-secret = ee367a189aee18fa31c190054efd4a8e9573746f726167652e676f6f676c65617069732e636f6d
mtproto-port = 0.0.0.0:443
```

```bash
./ypwee-linux-amd64 ypwee.conf
```

В консоли появится:

```
[ypwee] socks5 on 127.0.0.1:1080
[ypwee] http on 127.0.0.1:8081
[ypwee] mtproto on 0.0.0.0:443
```

Дальше в Telegram: **Настройки → Продвинутые → Прокси → MTProto** и вводишь адрес сервера с портом и секретом.

## Один порт — три протокола

```
клиент
  │
  ├─ 0x05 ────────────────► SOCKS5
  ├─ CONNECT ─────────────► HTTP-прокси
  ├─ TLS + верный секрет ─► FakeTLS → MTProto
  ├─ TLS + relay-хост ────► WEB-релей
  └─ что-то ещё ──────────► маска: настоящий сайт
```

## Конфиг

| Ключ | Что задаёт | По умолчанию |
|---|---|---|
| `user` | логин:пароль SOCKS5, можно несколько строк | — |
| `allow` | список разрешённых хостов, `*` — все | `*` |
| `allow-private` | разрешить приватные адреса как цель | `false` |
| `mtproto-secret` | секрет MTProto (`dd…` или `ee…`) | — |
| `mtproto-port` | адрес и порт MTProto | — |
| `socks5` | адрес и порт SOCKS5 | `127.0.0.1:1080` |
| `http` | адрес и порт HTTP-прокси | `127.0.0.1:8081` |
| `max-conns` | лимит соединений | `1024` |

Полный список — в [`ypwee.example.toml`](ypwee.example.toml).

## Сборка из исходников

Нужен компилятор [Yukino](https://github.com/yukitsuri/yukino) (`yukic`) и `lld`.

```bash
git clone https://github.com/ty4chka/ypwee.git
cd ypwee

# тесты: 44/44
yukic --test --entry src/main.ykn -o test.bin -- --error-limit=0
chmod +x test.bin && ./test.bin

# релизная сборка
yukic --release --entry src/main.ykn -o ypwee -- --error-limit=0
```

Готовые сборки для amd64 и arm64 собираются автоматически при каждом пуше — см. [`.github/workflows/build.yml`](.github/workflows/build.yml).

## Что проверено

- **44/44 теста** — SHA-1, SHA-256, HMAC, base64/base64url (векторы RFC), AES-CTR (NIST), SOCKS5, HTTP CONNECT, MTProto, WS-фреймы
- **e2e FakeTLS** — MTProto-хендшейк и релей против локального фейкового DC
- **e2e WebSocket** — WEB-релей через прокси, полный цикл HELLO→WELCOME→OPEN→DATA
- **анти-пробинг** — неверный секрет даёт настоящий TLS-ответ сайта

Тесты гоняются на amd64 и arm64 в CI.

## Чего пока нет

- Проверки против **настоящего** DC Telegram с резидентного IP: датацентры игнорируют obfs2 с серверных адресов.
- Подписанных релизов (cosign/provenance) — в планах.
- Бенчмарков против mtg / Telemt / mtproto.zig — в планах.

## Лицензия

См. [LICENSE](LICENSE).
