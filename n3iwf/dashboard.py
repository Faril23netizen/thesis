#!/usr/bin/env python3
"""
dashboard.py - Aquaculture N3IWF Dashboard Server
==================================================
TCP Server (menerima data dari Pico 2W) +
Flask Dashboard (visualisasi real-time) +
Progressive AI Inference (RB → FQL → DQN) dengan timer

Format data dari Pico:
  - Simple test : "TEST_DATA: seq=N, status=OK"
  - Real mode   : "DATA:ph_x1000,temp_x100,action"

Jalankan: python3 n3iwf/dashboard.py  (dari root thesis/)
Dashboard: http://<IP_RPI5>:5000
"""

import os
import re
import sys
import time
import json
import socket
import threading
import subprocess
from collections import deque
from datetime import datetime

from flask import Flask, jsonify, render_template

# ── Path setup ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

RESULTS_REAL = os.path.join(BASE_DIR, "results", "hasil_real")
NETWORK_DIR  = os.path.join(BASE_DIR, "results", "network")
os.makedirs(RESULTS_REAL, exist_ok=True)
os.makedirs(NETWORK_DIR, exist_ok=True)

NETWORK_SUMMARY = os.path.join(NETWORK_DIR, "network_summary.json")

# ── Load AI agents ────────────────────────────────────────────────────────────
RB_AVAILABLE = False
FQL_AVAILABLE = False
DQN_AVAILABLE = False
fql_agent = None
dqn_agent = None
ACTION_NAMES = ["OFF", "LOW", "MED", "HIGH"]

def rule_based_action(pH: float, T: float) -> int:
    if pH < 6.0 or pH > 9.5 or T > 35.0: return 3
    if pH < 6.5 or pH > 8.5 or T > 30.0: return 2
    return 1

RB_AVAILABLE = True

try:
    from fql.fql_agent import FQLAgent
    _qt_real = os.path.join(RESULTS_REAL, "qtable.json")
    _qt_sim  = os.path.join(BASE_DIR, "results", "simulation", "qtable.json")
    fql_agent = FQLAgent()
    for _qt in [_qt_real, _qt_sim]:
        if os.path.exists(_qt) and fql_agent.load_qtable(_qt):
            fql_agent.epsilon = 0.0
            FQL_AVAILABLE = True
            print(f"[FQL] Loaded: {_qt}")
            break
    if not FQL_AVAILABLE:
        print("[FQL] No Q-table found")
except ImportError as e:
    print(f"[FQL] Import error: {e}")

try:
    from dqn.dqn_agent import DQNAgent
    _dqn_real = os.path.join(RESULTS_REAL, "dqn_model.pt")
    _dqn_sim  = os.path.join(BASE_DIR, "results", "simulation", "dqn_model.pt")
    dqn_agent = DQNAgent()
    for _dm in [_dqn_real, _dqn_sim]:
        if os.path.exists(_dm) and dqn_agent.load(_dm):
            DQN_AVAILABLE = True
            print(f"[DQN] Loaded: {_dm}")
            break
    if not DQN_AVAILABLE:
        print("[DQN] No model found")
except ImportError as e:
    print(f"[DQN] Import error: {e}")

# ── Shared state ──────────────────────────────────────────────────────────────
state = {
    "connected": False, "pico_ip": "--", "mode": "TEST",
    "pH": None, "T": None,
    "seq": 0, "led": False,
    "rb_action": "--", "fql_action": "--", "dqn_action": "--",
    "rb_infer_ms": 0, "fql_infer_ms": 0, "dqn_infer_ms": 0,
    "last_seen": None, "total_packets": 0, "latency_ms": [],
    "ipsec": False, "ipsec_detail": "--",
    "net_avg_ms": "--", "net_min_ms": "--",
    "net_max_ms": "--", "net_jitter": "--", "net_pdr": "--",
    "live_rtt_ms": None,   # latest ping RTT to Callbox
    "rb_available": RB_AVAILABLE,
    "fql_available": FQL_AVAILABLE,
    "dqn_available": DQN_AVAILABLE,
}
history = deque(maxlen=120)
latency_history = deque(maxlen=60)   # live ping RTT to Callbox (last 60 samples)
lock = threading.Lock()

# ── AI Inference ──────────────────────────────────────────────────────────────
def run_inference(pH: float, T: float) -> dict:
    res = {}
    t0 = time.perf_counter()
    res["rb"] = {"name": ACTION_NAMES[rule_based_action(pH, T)],
                 "ms": round((time.perf_counter()-t0)*1000, 3)}
    if FQL_AVAILABLE and fql_agent:
        t0 = time.perf_counter()
        a = fql_agent.select_action(pH, T)
        res["fql"] = {"name": ACTION_NAMES[a], "ms": round((time.perf_counter()-t0)*1000, 3)}
    if DQN_AVAILABLE and dqn_agent:
        t0 = time.perf_counter()
        a = dqn_agent.select_action(pH, T)
        res["dqn"] = {"name": ACTION_NAMES[a], "ms": round((time.perf_counter()-t0)*1000, 3)}
    return res

# ── TCP Server ────────────────────────────────────────────────────────────────
def tcp_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 5005))
    srv.listen(1)
    DATA_RE = re.compile(r'^DATA:(-?\d+),(-?\d+),([0-3])$')
    print("[TCP] Listening on port 5005...")

    while True:
        try:
            conn, addr = srv.accept()
            print(f"[TCP] Pico connected: {addr[0]}")
            last_time = time.time()
            with lock:
                state["connected"] = True
                state["pico_ip"] = addr[0]
                state["total_packets"] = 0
                state["latency_ms"] = []

            buf = ""
            while True:
                try:
                    data = conn.recv(1024)
                    if not data: break
                    now = time.time()
                    buf += data.decode(errors='ignore')
                    while '\n' in buf:
                        line, buf = buf.split('\n', 1)
                        line = line.strip()
                        if not line: continue
                        latency = round((now - last_time) * 1000, 1)
                        last_time = now

                        m = DATA_RE.match(line)
                        if m:
                            pH = int(m.group(1)) / 1000.0
                            T  = int(m.group(2)) / 100.0
                            inf = run_inference(pH, T)
                            with lock:
                                state.update({
                                    "mode": "REAL", "pH": pH, "T": T,
                                    "rb_action":   inf.get("rb",{}).get("name","--"),
                                    "fql_action":  inf.get("fql",{}).get("name","--"),
                                    "dqn_action":  inf.get("dqn",{}).get("name","--"),
                                    "rb_infer_ms": inf.get("rb",{}).get("ms",0),
                                    "fql_infer_ms":inf.get("fql",{}).get("ms",0),
                                    "dqn_infer_ms":inf.get("dqn",{}).get("ms",0),
                                    "last_seen": now, "total_packets": state["total_packets"]+1,
                                })
                                state["latency_ms"].append(latency)
                                if len(state["latency_ms"]) > 50: state["latency_ms"].pop(0)
                                history.append({"ts": now, "pH": pH, "T": T, "latency": latency,
                                                "rb": state["rb_action"], "fql": state["fql_action"],
                                                "dqn": state["dqn_action"]})
                            print(f"[REAL] pH={pH:.2f} T={T:.1f} | "
                                  f"RB={state['rb_action']} FQL={state['fql_action']} DQN={state['dqn_action']}")
                        elif "seq=" in line or "TEST_DATA" in line:
                            m2 = re.search(r'seq=(\d+)', line)
                            seq = int(m2.group(1)) if m2 else state["seq"]+1
                            with lock:
                                state.update({"mode": "TEST", "seq": seq, "led": (seq%2==0),
                                              "last_seen": now, "total_packets": state["total_packets"]+1})
                                state["latency_ms"].append(latency)
                                if len(state["latency_ms"]) > 50: state["latency_ms"].pop(0)
                                history.append({"ts": now, "seq": seq, "led": state["led"], "latency": latency})
                            print(f"[TEST] seq={seq} led={'ON' if state['led'] else 'OFF'}")
                except Exception as e:
                    print(f"[TCP] err: {e}"); break
            conn.close()
            with lock:
                state["connected"] = False; state["pico_ip"] = "--"
            print("[TCP] Disconnected. Waiting...")
        except Exception as e:
            print(f"[TCP] server err: {e}"); time.sleep(1)

# ── IPsec Monitor ─────────────────────────────────────────────────────────────
def ipsec_monitor():
    while True:
        try:
            r = subprocess.run(["sudo","ipsec","statusall"], capture_output=True, text=True, timeout=5)
            ok = "ESTABLISHED" in r.stdout
            detail = "--"
            if ok:
                for l in r.stdout.splitlines():
                    if "ESTABLISHED" in l: detail = l.strip(); break
            with lock:
                state["ipsec"] = ok; state["ipsec_detail"] = detail
        except Exception:
            with lock: state["ipsec"] = False
        time.sleep(5)

# ── Network Stats Loader ──────────────────────────────────────────────────────
def net_stats_loader():
    while True:
        try:
            if os.path.exists(NETWORK_SUMMARY):
                with open(NETWORK_SUMMARY) as f:
                    ns = json.load(f)
                with lock:
                    state["net_avg_ms"] = ns.get("avg_ms","--")
                    state["net_min_ms"] = ns.get("min_ms","--")
                    state["net_max_ms"] = ns.get("max_ms","--")
                    state["net_jitter"] = ns.get("jitter_ms","--")
                    state["net_pdr"]    = ns.get("pdr_pct","--")
        except Exception: pass
        time.sleep(30)

# ── Live Ping Thread (N3IWF Real-time Latency) ────────────────────────────────
def live_ping(target: str = "192.168.100.101", interval: int = 3):
    """Ping Callbox every `interval` seconds, store RTT in latency_history."""
    print(f"[PING] Live ping to {target} every {interval}s")
    while True:
        rtt = None
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", target],
                capture_output=True, text=True, timeout=4
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if "time=" in line:
                        rtt = round(float(line.split("time=")[1].split(" ")[0]), 2)
                        break
        except Exception:
            pass
        ts = datetime.now().strftime("%H:%M:%S")
        with lock:
            state["live_rtt_ms"] = rtt
            latency_history.append({"ts": ts, "rtt": rtt})
        time.sleep(interval)

# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='templates')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state')
def get_state():
    with lock:
        s = dict(state)
        s["latency_avg"] = round(sum(s["latency_ms"])/len(s["latency_ms"]),1) if s["latency_ms"] else 0
        s["last_seen_ago"] = round(time.time()-s["last_seen"],1) if s["last_seen"] else None
    return jsonify(s)

@app.route('/api/history')
def get_history():
    with lock: return jsonify(list(history))

@app.route('/api/latency_history')
def get_latency_history():
    with lock: return jsonify(list(latency_history))

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=ipsec_monitor, daemon=True).start()
    threading.Thread(target=net_stats_loader, daemon=True).start()
    threading.Thread(target=live_ping, daemon=True).start()

    try: ip = socket.gethostbyname(socket.gethostname())
    except: ip = "0.0.0.0"

    print(f"\n{'='*50}")
    print(f"  Aquaculture N3IWF Dashboard")
    print(f"  Dashboard : http://{ip}:5000")
    print(f"  TCP Port  : 5005 (Pico 2W)")
    print(f"  RB={RB_AVAILABLE} | FQL={FQL_AVAILABLE} | DQN={DQN_AVAILABLE}")
    print(f"{'='*50}\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
