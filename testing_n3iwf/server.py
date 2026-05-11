#!/usr/bin/env python3
"""
server.py - Aquaculture N3IWF Testing Server
Menggabungkan TCP Server (menerima data dari Pico 2W) +
Flask Dashboard (visualisasi real-time) dalam satu proses.

Jalankan: python3 server.py
Buka browser: http://<IP_RPI5>:5000
"""

import os
import re
import time
import socket
import threading
import subprocess
from collections import deque
from flask import Flask, jsonify, render_template

# ─── Shared State ───────────────────────────────────────────────────────────
state = {
    "connected": False,
    "pico_ip": "--",
    "seq": 0,
    "led": False,          # True = ON, False = OFF (toggle tiap paket)
    "last_seen": None,
    "ipsec": False,
    "ipsec_detail": "--",
    "latency_ms": [],      # riwayat latency antar paket
    "total_packets": 0,
}
history = deque(maxlen=100)   # riwayat untuk grafik

state_lock = threading.Lock()

# ─── TCP Server Thread ───────────────────────────────────────────────────────
def tcp_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 5005))
    srv.listen(1)
    print("[TCP] Waiting for Pico 2W on port 5005 ...")

    while True:
        try:
            conn, addr = srv.accept()
            print(f"[TCP] Pico connected from {addr[0]}")
            last_time = time.time()

            with state_lock:
                state["connected"] = True
                state["pico_ip"] = addr[0]
                state["seq"] = 0
                state["led"] = False
                state["latency_ms"] = []

            while True:
                try:
                    data = conn.recv(1024)
                    if not data:
                        break
                    now = time.time()
                    text = data.decode(errors='ignore').strip()
                    m = re.search(r'seq=(\d+)', text)
                    if m:
                        seq = int(m.group(1))
                        latency = round((now - last_time) * 1000, 1)
                        last_time = now
                        with state_lock:
                            state["seq"] = seq
                            state["led"] = (seq % 2 == 0)
                            state["last_seen"] = now
                            state["total_packets"] += 1
                            state["latency_ms"].append(latency)
                            if len(state["latency_ms"]) > 50:
                                state["latency_ms"].pop(0)
                            history.append({
                                "seq": seq,
                                "led": state["led"],
                                "ts": now,
                                "latency": latency
                            })
                        print(f"[TCP] {text} | latency={latency}ms")
                except Exception as e:
                    print(f"[TCP] Recv error: {e}")
                    break

            conn.close()
            with state_lock:
                state["connected"] = False
                state["pico_ip"] = "--"
            print("[TCP] Pico disconnected. Waiting again ...")

        except Exception as e:
            print(f"[TCP] Server error: {e}")
            time.sleep(1)


# ─── IPsec Monitor Thread ────────────────────────────────────────────────────
def ipsec_monitor():
    while True:
        try:
            result = subprocess.run(
                ["sudo", "ipsec", "statusall"],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout
            established = "ESTABLISHED" in output
            detail = "--"
            if established:
                for line in output.splitlines():
                    if "ESTABLISHED" in line:
                        detail = line.strip()
                        break
            with state_lock:
                state["ipsec"] = established
                state["ipsec_detail"] = detail
        except Exception:
            with state_lock:
                state["ipsec"] = False
                state["ipsec_detail"] = "Error checking IPsec"
        time.sleep(5)


# ─── Flask App ───────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='n3iwf/templates')


@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/api/state')
def get_state():
    with state_lock:
        s = dict(state)
        s["latency_avg"] = round(sum(s["latency_ms"]) / len(s["latency_ms"]), 1) \
                           if s["latency_ms"] else 0
        s["last_seen_ago"] = round(time.time() - s["last_seen"], 1) \
                             if s["last_seen"] else None
    return jsonify(s)


@app.route('/api/history')
def get_history():
    with state_lock:
        return jsonify(list(history))


# ─── Main ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=ipsec_monitor, daemon=True).start()

    import socket as _s
    hostname = _s.gethostname()
    local_ip = _s.gethostbyname(hostname)
    print(f"\n{'='*55}")
    print(f"  Aquaculture N3IWF Testing Dashboard")
    print(f"{'='*55}")
    print(f"  Dashboard : http://{local_ip}:5000")
    print(f"  TCP Port  : 5005 (waiting for Pico)")
    print(f"  IPsec     : auto-check every 5s")
    print(f"{'='*55}\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
