#!/bin/bash
# ypwee MTProto CI: build toolchain, run tests, build server, run e2e FakeTLS client.
set -x
cd "$(dirname "$0")/../.."

if [ ! -x /tmp/yukino/target/release/yukic ]; then
  git clone --depth 1 https://github.com/yukitsuri/yukino /tmp/yukino
  (cd /tmp/yukino && cargo build --release 2>&1 | tail -3)
fi
sudo cp /tmp/yukino/target/release/yukic /tmp/yukino/target/release/yukino /usr/local/bin/
yukic --version

yukino test 2>&1 | tail -20

yukic --release --entry src/main.ykn -o ypwee-ci.bin 2>&1 | tail -2
ls -la ypwee-ci.bin

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
