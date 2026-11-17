#!/bin/bash
set -eux
cd "$(dirname "$0")/../.."

YUKINO_REF="753ee4e9374bb33b3dbbaf85028f7f66254207ff"

# 1. LLVM 22 via official installer (handles runner codename itself)
wget -qO- https://apt.llvm.org/llvm.sh | sudo -E bash -s -- 22
sudo apt-get install -y -qq libpolly-22-dev lld-22 libzstd-dev zlib1g-dev
echo "LLVM_SYS_221_PREFIX=/usr/lib/llvm-22" >> "$GITHUB_ENV"
sudo ln -sf /usr/lib/llvm-22/bin/llvm-ar /usr/local/bin/llvm-ar
sudo ln -sf /usr/bin/ld.lld-22 /usr/local/bin/ld.lld

# 2. Yukino toolchain (PINNED + sret patch for aarch64 ABI)
cat > /tmp/patch_sret.py <<'PYEOF'
import re
targets = {
    "crates/yukic-codegen/src/intrinsic.rs": [
        r"(?m)^[ \t]*f\.add_attribute\(AttributeLoc::Param\(0\), sret_attr\);\r?\n",
        r"(?m)^[ \t]*call\.add_attribute\(AttributeLoc::Param\(0\), sret_attr\);\r?\n",
    ],
    "crates/yukic-codegen/src/body/mod.rs": [
        r"(?m)^[ \t]*f\.add_attribute\(AttributeLoc::Param\(0\), sret_attr\);\r?\n",
    ],
}
for path, pats in targets.items():
    s = open(path, encoding="utf-8").read()
    for pat in pats:
        s, n = re.subn(pat, "", s)
        print("patched", path, pat[:40], n)
        open(path, "w", encoding="utf-8").write(s)
PYEOF

if [ ! -x /tmp/yukino/target/release/yukic ]; then
  git clone https://github.com/yukitsuri/yukino /tmp/yukino
  (
    cd /tmp/yukino
    git fetch --depth 1 origin "$YUKINO_REF"
    git checkout -q "$YUKINO_REF"
    python3 /tmp/patch_sret.py
    cargo build --release 2>&1 | tail -5
  )
fi
sudo cp /tmp/yukino/target/release/yukic /tmp/yukino/target/release/yukino /usr/local/bin/
yukic --version

# 3. Unit tests
yukic --test --entry src/main.ykn -o test_ci.bin -- --error-limit=0 2>&1 | tail -20
chmod +x test_ci.bin
./test_ci.bin 2>&1 | tail -6

# 4. Build server
yukic --release --entry src/main.ykn -o ypwee-ci.bin -- --error-limit=0 2>&1 | tail -20
ls -la ypwee-ci.bin

# 5. e2e: server + python FakeTLS client
pip install pycryptodome --quiet 2>&1 | tail -1
python3 tests/fakedc.py > fakedc.log 2>&1 &
FDC=$!
cat > ypwee.conf <<'CONF'
user = alice:changeMe1
allow = *
mtproto-secret = ee367a189aee18fa31c190054efd4a8e9573746f726167652e676f6f676c65617069732e636f6d
mtproto-port = 127.0.0.1:1443
dc-override = 127.0.0.1:9443
CONF
chmod +x ypwee-ci.bin
pkill -f ypwee-ci.bin 2>/dev/null || true
pkill -f fakedc.py 2>/dev/null || true
sleep 2
./ypwee-ci.bin ypwee.conf > server.log 2>&1 &
SRV=$!
sleep 2
YPWEE_SECRET=ee367a189aee18fa31c190054efd4a8e9573746f726167652e676f6f676c65617069732e636f6d YPWEE_ADDR=127.0.0.1:1443 python3 tests/mt_client.py 2>&1 | tee client.log
kill $SRV 2>/dev/null || true
kill $FDC 2>/dev/null || true
echo "--- fakedc.log:"; cat fakedc.log
echo "--- server.log:"; cat server.log
RESULT=$(grep -c "E2E RELAY OK" client.log || true)
echo "E2E_RESULT=$RESULT"
[ "$RESULT" = "1" ]

# 6. M4 WEB relay: WS carrier -> MTProto through the proxy itself (restart server)
kill $SRV 2>/dev/null || true
pkill -f ypwee-ci.bin 2>/dev/null || true
sleep 3
python3 tests/fakedc.py > fakedc.log 2>&1 &
FDC=$!
sleep 1
./ypwee-ci.bin ypwee.conf > server.log 2>&1 &
SRV=$!
sleep 2
YPWEE_ADDR=127.0.0.1:1443 python3 tests/ws_client.py 2>&1 | tee ws.log
WS=$(grep -c "WEB E2E OK" ws.log || true)
echo "WS_RESULT=$WS"

# 7. M3 anti-probe: wrong secret must yield a masked TLS response (restart server)
kill $SRV 2>/dev/null || true
pkill -f ypwee-ci.bin 2>/dev/null || true
sleep 3
./ypwee-ci.bin ypwee.conf > server2.log 2>&1 &
SRV=$!
sleep 2
YPWEE_ADDR=127.0.0.1:1443 python3 tests/mt_client.py probe 2>&1 | tee probe.log
PROBE=$(grep -c "M3 MASK OK" probe.log || true)
echo "PROBE_RESULT=$PROBE"
kill $SRV 2>/dev/null || true
kill $FDC 2>/dev/null || true
[ "$PROBE" = "1" ]
[ "$WS" = "1" ]
