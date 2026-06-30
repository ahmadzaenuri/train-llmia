"""
Pearl Fortune Miner — standalone runner for platform deployments
(e.g. Lightning AI Studios / generic job runners that execute `python server.py`)

This script:
  1. Downloads and extracts the official Pearl Fortune miner tarball
  2. Launches it pointed at the Pearl Fortune global proxy with your wallet
  3. Streams miner output to stdout (visible in platform logs)
  4. Opens a small HTTP server on the required port, exposing /health and /
     so the platform's port check / health probe is satisfied

Edit WALLET / PROXY / WORKER below if needed.
"""

import os
import stat
import subprocess
import sys
import tarfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WALLET = "prl1p3uspnlkj7cq7nnl7adevj4rhw7c67symca02rt6ckltnrcf4udhq983d6e"
PROXY = "global.pearlfortune.org:443"
WORKER = "container-h100"

MINER_VERSION = "1.1.8"
MINER_URL = f"https://github.com/pearlfortune/pearl-miner/releases/download/v{MINER_VERSION}/pearlfortune-v{MINER_VERSION}.tar.gz"
MINER_DIR = "/tmp/pearlfortune"
MINER_TARBALL = "/tmp/pearlfortune.tar.gz"
PORT = int(os.environ.get("PORT", "11134"))  # match the Port(s) field in the deploy UI

miner_status = {"running": False, "pid": None}

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def ensure_miner_binary():
    miner_bin_path = os.path.join(MINER_DIR, "miner-cuda12")
    if not os.path.exists(miner_bin_path):
        print(f"[server] Downloading miner from {MINER_URL}", flush=True)
        req = urllib.request.Request(MINER_URL, headers=UA)
        with urllib.request.urlopen(req) as resp, open(MINER_TARBALL, "wb") as out:
            out.write(resp.read())

        print("[server] Extracting tarball", flush=True)
        os.makedirs(MINER_DIR, exist_ok=True)
        with tarfile.open(MINER_TARBALL) as tar:
            tar.extractall(MINER_DIR)

        # tarball may extract into a nested "pearlfortune" folder; flatten if so
        nested = os.path.join(MINER_DIR, "pearlfortune")
        if os.path.isdir(nested):
            for item in os.listdir(nested):
                dest = os.path.join(MINER_DIR, item)
                if not os.path.exists(dest):
                    os.rename(os.path.join(nested, item), dest)

        print(f"[server] Extracted contents: {os.listdir(MINER_DIR)}", flush=True)

        if not os.path.exists(miner_bin_path):
            # fallback: try cuda13 binary, or any executable-looking file named miner*
            candidates = [f for f in os.listdir(MINER_DIR) if f.startswith("miner")]
            print(f"[server] miner-cuda12 not found, candidates: {candidates}", flush=True)
            if candidates:
                miner_bin_path = os.path.join(MINER_DIR, candidates[0])
            else:
                raise FileNotFoundError(f"No miner binary found in {MINER_DIR}")

        st = os.stat(miner_bin_path)
        os.chmod(miner_bin_path, st.st_mode | stat.S_IEXEC)
    else:
        print("[server] Miner already present", flush=True)
    return miner_bin_path


def run_miner():
    miner_bin_path = ensure_miner_binary()
    print("[server] --- nvidia-smi check ---", flush=True)
    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=15)
        print(out.stdout or out.stderr, flush=True)
    except Exception as e:
        print(f"[server] nvidia-smi failed: {e}", flush=True)
    print("[server] --- end nvidia-smi check ---", flush=True)

    print(f"[server] Pearl Fortune Miner — target GPU: 2x H100", flush=True)
    print(f"[server] Proxy: {PROXY}", flush=True)
    print(f"[server] Wallet: {WALLET}", flush=True)
    print(f"[server] Worker: {WORKER}", flush=True)
    print(f"[server] Binary: {miner_bin_path}", flush=True)

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = os.path.join(MINER_DIR, "lib") + ":" + env.get("LD_LIBRARY_PATH", "")

    cmd = [
        miner_bin_path,
        "--proxy", PROXY,
        "--address", WALLET,
        "--worker", WORKER,
        "-gpu",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=MINER_DIR, env=env
    )
    miner_status["running"] = True
    miner_status["pid"] = proc.pid
    print(f"[server] Miner PID: {proc.pid}", flush=True)

    for line in iter(proc.stdout.readline, b""):
        print(line.decode(errors="replace").strip(), flush=True)

    miner_status["running"] = False
    code = proc.wait()
    print(f"[server] Miner exited with code {code}", flush=True)


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence default HTTP logging, miner logs are what matter

    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = (
                '{"status": "ok", "miner_running": %s, "pid": %s}'
                % (
                    str(miner_status["running"]).lower(),
                    miner_status["pid"] if miner_status["pid"] else "null",
                )
            )
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    miner_thread = threading.Thread(target=run_miner, daemon=True)
    miner_thread.start()

    print(f"[server] Health server listening on 0.0.0.0:{PORT}", flush=True)
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[server] Shutting down", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
