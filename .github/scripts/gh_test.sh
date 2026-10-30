#!/bin/bash
set -x
cd "$(dirname "$0")/../.."

# 1. LLVM 22 (обязательно для llvm-sys Yukino)
sudo wget -qO- https://apt.llvm.org/llvm-snapshot.gpg.key | sudo apt-key add -
echo "deb http://apt.llvm.org/jammy/ llvm-toolchain-jammy-22 main" | sudo tee /etc/apt/sources.list.d/llvm22.list
sudo apt-get update -qq
sudo apt-get install -y -qq llvm-22-dev libpolly-22-dev libzstd-dev zlib1g-dev lld-22
echo "LLVM_SYS_221_PREFIX=/usr/lib/llvm-22" >> "$GITHUB_ENV"
sudo ln -sf /usr/lib/llvm-22/bin/llvm-ar /usr/local/bin/llvm-ar
sudo ln -sf /usr/bin/ld.lld-22 /usr/local/bin/ld.lld
sudo ln -sf /usr/lib/llvm-22/bin/ld.lld /usr/bin/ld.lld 2>/dev/null || true
ld.lld --version || ls /usr/lib/llvm-22/bin/ | head

# 2. Yukino toolchain
if [ ! -x /tmp/yukino/target/release/yukic ]; then
  git clone --depth 1 https://github.com/yukitsuri/yukino /tmp/yukino
  (cd /tmp/yukino && cargo build --release 2>&1 | tail -5)
fi
sudo cp /tmp/yukino/target/release/yukic /tmp/yukino/target/release/yukino /usr/local/bin/
yukic --version

# 3. Unit tests
yukic --test --entry src/main.ykn -o test_ci.bin --error-limit=0 2>&1 | tail -20
chmod +x test_ci.bin
./test_ci.bin 2>&1 | tail -6

# 4. Build server
yukic --release --entry src/main.ykn -o ypwee-ci.bin --error-limit=0 2>&1 | tail -20
ls -la ypwee-ci.bin

# 5. e2e: server + python FakeTLS client
pip install pycryptodome --quiet 2>&1 | tail -1
cat > ypwee.conf <<'CONF'
user = alice:changeMe1
allow = *
mtproto-secret = ee367a189aee18fa31c190054efd4a8e9573746f726167652e676f6f676c65617069732e636f6d
mtproto-port = 127.0.0.1:1443
CONF
chmod +x ypwee-ci.bin
./ypwee-ci.bin ypwee.conf > server.log 2>&1 &
SRV=$!
sleep 2
YPWEE_SECRET=ee367a189aee18fa31c190054efd4a8e9573746f726167652e676f6f676c65617069732e636f6d YPWEE_ADDR=127.0.0.1:1443 python3 tests/mt_client.py 2>&1 | tee client.log
kill $SRV 2>/dev/null
echo "--- server.log:"; cat server.log
RESULT=$(grep -c "E2E RELAY OK" client.log || true)
echo "E2E_RESULT=$RESULT"
