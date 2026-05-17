#!/usr/bin/env python3
"""
server.py - Aquaculture N3IWF Testing Server
=============================================
TCP Server (menerima data dari Pico 2W) +
Flask Dashboard (visualisasi real-time) +
DQN/FQL/RB Progressive Inference (dengan timer)

Format data dari Pico:
  - Simple test : "TEST_DATA: seq=N, status=OK"
  - Real mode   : "DATA:ph_x1000,temp_x100,action"

Jalankan: python3 testing_n3iwf/server.py
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

# Flask
from flask import Flask, jsonify, render_template

# ── Path setup ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

RESULTS_DIR = os.path.join(BASE_DIR, "results", "hasil_real")
NETWORK_DIR = os.path.join(BASE_DIR, "results", "network")
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(NETWORK_DIR, exist_ok=True)

NETWORK_SUMMARY = os.path.join(NETWORK_DIR, "network_summary.json")

# ── Load AI agents (optional) ────────────────────────────────────────────────
RB_AVAILABLE  = False
FQL_AVAILABLE = False
DQN_AVAILABLE = False
fql_agent = None
dqn_agent = None

ACTION_NAMES = ["OFF", "LOW", "MED", "HIGH"]
ACTION_COST  = {0: 0.0, 1: 0.3, 2: 0.6, 3: 1.0}

def rule_based_action(pH: float, T: float) -> int:
    if pH < 6.0 or pH > 9.5 or T > 35.0: return 3  # HIGH
    if pH < 6.5 or pH > 8.5 or T > 30.0: return 2  # MED
    return 1  # LOW

RB_AVAILABLE = True

try:
    from fql.fql_agent import FQLAgent
    QTABLE_FILE = os.path.join(RESULTS_DIR, "qtable.json")
    SIM_QTABLE  = os.path.join(BASE_DIR, "results", "simulation", "qtable.json")
    fql_agent = FQLAgent()
    if os.path.exists(QTABLE_FILE) and fql_agent.load_qtable(QTABLE_FILE):
        fql_agent.epsilon = 0.0
        FQL_AVAILABLE = True
        print("[FQL] Q-table loaded from real results")
    elif os.path.exists(SIM_QTABLE) and fql_agent.load_qtable(SIM_QTABLE):
        fql_agent.epsilon = 0.0
        FQL_AVAILABLE = True
        print("[FQL] Q-table loaded from simulation results")
    else:
        print("[FQL] No Q-table found, FQL unavailable")
except ImportError as e:
    print(f"[FQL] Import failed: {e}")

try:
    from dqn.dqn_agent import DQNAgent
    DQN_MODEL = os.path.join(RESULTS_DIR, "dqn_model.pt")
    SIM_DQN   = os.path.join(BASE_DIR, "results", "simulation", "dqn_model.pt")
    dqn_agent = DQNAgent()
    if os.path.exists(DQN_MODEL) and dqn_agent.load(DQN_MODEL):
        DQN_AVAILABLE = True
        print("[DQN] Model loaded from real results")
    elif os.path.exists(SIM_DQN) and dqn_agent.load(SIM_DQN):
        DQN_AVAILABLE = True
        print("[DQN] Model loaded from simulation results")
    else:
        print("[DQN] No model found, DQN unavailable")
except ImportError as e:
    print(f"[DQN] Import failed: {e}")

# ── Shared State ──────────────────────────────────────────────────────────────
state = {
    # Connection
    "connected": False,
    "pico_ip": "--",
    "mode": "TEST",          # TEST or REAL

    # Sensor data (REAL mode)
    "pH": None,
    "T": None,

    # Simple test (TEST mode)
    "seq": 0,
    "led": False,

    # AI decisions
    "rb_action": "--",
    "fql_action": "--",
    "dqn_action": "--",
    "active_phase": "RB",    # RB → FQL → DQN (progressive)

    # Timing
    "rb_infer_ms": 0,
    "fql_infer_ms": 0,
    "dqn_infer_ms": 0,
    "last_seen": None,
    "total_packets": 0,
    "latency_ms": [],

    # IPsec
    "ipsec": False,
    "ipsec_detail": "--",

    # Network stats (loaded from latency_test results)
    "net_avg_ms": "--",
    "net_min_ms": "--",
    "net_max_ms": "--",
    "net_jitter": "--",
    "net_pdr": "--",

    # AI availability
    "rb_available": RB_AVAILABLE,
    "fql_available": FQL_AVAILABLE,
    "dqn_available": DQN_AVAILABLE,
}

history = deque(maxlen=120)
state_lock = threading.Lock()

# ── AI Inference with timing ──────────────────────────────────────────────────
def run_inference(pH: float, T: float) -> dict:
    """Run all available AI agents and measure inference time."""
    results = {}

    # Rule-Based
    t0 = time.perf_counter()
    rb_act = rule_based_action(pH, T)
    rb_ms = (time.perf_counter() - t0) * 1000
    results["rb"] = {"action": rb_act, "name": ACTION_NAMES[rb_act], "ms": round(rb_ms, 3)}

    # FQL
    if FQL_AVAILABLE and fql_agent:
        t0 = time.perf_counter()
        fql_act = fql_agent.select_action(pH, T)
        fql_ms = (time.perf_counter() - t0) * 1000
        results["fql"] = {"action": fql_act, "name": ACTION_NAMES[fql_act], "ms": round(fql_ms, 3)}

    # DQN
    if DQN_AVAILABLE and dqn_agent:
        t0 = time.perf_counter()
        dqn_act = dqn_agent.select_action(pH, T)
        dqn_ms = (time.perf_counter() - t0) * 1000
        results["dqn"] = {"action": dqn_act, "name": ACTION_NAMES[dqn_act], "ms": round(dqn_ms, 3)}

    return results

# ── TCP Server Thread ─────────────────────────────────────────────────────────
def tcp_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 5005))
    srv.listen(1)
    print("[TCP] Waiting for Pico 2W on port 5005 ...")

    DATA_RE = re.compile(r'^DATA:(-?\d+),(-?\d+),([0-3])$')

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
                state["total_packets"] = 0

            buf = ""
            while True:
                try:
                    data = conn.recv(1024)
                    if not data:
                        break
                    now = time.time()
                    buf += data.decode(errors='ignore')

                    while '\n' in buf:
                        line, buf = buf.split('\n', 1)
                        line = line.strip()
                        if not line:
                            continue

                        latency = round((now - last_time) * 1000, 1)
                        last_time = now

                        # ── Real sensor data: DATA:ph_x1000,temp_x100,action
                        m = DATA_RE.match(line)
                        if m:
                            pH = int(m.group(1)) / 1000.0
                            T  = int(m.group(2)) / 100.0
                            # Run all AI agents with timing
                            inf = run_inference(pH, T)
                            with state_lock:
                                state["mode"] = "REAL"
                                state["pH"] = pH
                                state["T"] = T
                                state["rb_action"]   = inf.get("rb",  {}).get("name", "--")
                                state["fql_action"]  = inf.get("fql", {}).get("name", "--")
                                state["dqn_action"]  = inf.get("dqn", {}).get("name", "--")
                                state["rb_infer_ms"] = inf.get("rb",  {}).get("ms", 0)
                                state["fql_infer_ms"]= inf.get("fql", {}).get("ms", 0)
                                state["dqn_infer_ms"]= inf.get("dqn", {}).get("ms", 0)
                                state["last_seen"] = now
                                state["total_packets"] += 1
                                state["latency_ms"].append(latency)
                                if len(state["latency_ms"]) > 50:
                                    state["latency_ms"].pop(0)
                                history.append({
                                    "ts": now, "pH": pH, "T": T,
                                    "rb": state["rb_action"],
                                    "fql": state["fql_action"],
                                    "dqn": state["dqn_action"],
                                    "latency": latency
                                })
                            print(f"[REAL] pH={pH:.2f} T={T:.1f}°C | "
                                  f"RB={state['rb_action']}({state['rb_infer_ms']:.2f}ms) "
                                  f"FQL={state['fql_action']}({state['fql_infer_ms']:.2f}ms) "
                                  f"DQN={state['dqn_action']}({state['dqn_infer_ms']:.2f}ms)")

                        # ── Simple test: TEST_DATA: seq=N, status=OK
                        elif "TEST_DATA" in line or "seq=" in line:
                            m2 = re.search(r'seq=(\d+)', line)
                            seq = int(m2.group(1)) if m2 else 0
                            with state_lock:
                                state["mode"] = "TEST"
                                state["seq"] = seq
                                state["led"] = (seq % 2 == 0)
                                state["last_seen"] = now
                                state["total_packets"] += 1
                                state["latency_ms"].append(latency)
                                if len(state["latency_ms"]) > 50:
                                    state["latency_ms"].pop(0)
                                history.append({
                                    "ts": now, "seq": seq,
                                    "led": state["led"],
                                    "latency": latency
                                })
                            print(f"[TEST] seq={seq} | led={'ON' if state['led'] else 'OFF'} "
                                  f"| delay={latency}ms")

                except Exception as e:
                    print(f"[TCP] Error: {e}")
                    break

            conn.close()
            with state_lock:
                state["connected"] = False
                state["pico_ip"] = "--"
            print("[TCP] Pico disconnected. Waiting again ...")

        except Exception as e:
            print(f"[TCP] Server error: {e}")
            time.sleep(1)

# ── IPsec Monitor ─────────────────────────────────────────────────────────────
def ipsec_monitor():
    while True:
        try:
            result = subprocess.run(
                ["sudo", "ipsec", "statusall"],
                capture_output=True, text=True, timeout=5
            )
            established = "ESTABLISHED" in result.stdout
            detail = "--"
            if established:
                for line in result.stdout.splitlines():
                    if "ESTABLISHED" in line:
                        detail = line.strip()
                        break
            with state_lock:
                state["ipsec"] = established
                state["ipsec_detail"] = detail
        except Exception:
            with state_lock:
                state["ipsec"] = False
                state["ipsec_detail"] = "Error checking"
        time.sleep(5)

def ipsec_monitor_sim():
    """Simulasi IPsec tunnel ESTABLISHED ke N3IWF Callbox."""
    time.sleep(2)
    with state_lock:
        state["ipsec"] = True
        state["ipsec_detail"] = "N3IWF[1]: ESTABLISHED 192.168.137.251...192.168.100.101 (SIMULASI)"
    print("[SIM] IPsec tunnel: ESTABLISHED")
    while True:
        time.sleep(30)

# ── Network Summary Loader ────────────────────────────────────────────────────
def load_network_summary():
    """Load pre-measured network stats from latency_test.py results."""
    while True:
        try:
            if os.path.exists(NETWORK_SUMMARY):
                with open(NETWORK_SUMMARY) as f:
                    ns = json.load(f)
                with state_lock:
                    state["net_avg_ms"] = ns.get("avg_ms", "--")
                    state["net_min_ms"] = ns.get("min_ms", "--")
                    state["net_max_ms"] = ns.get("max_ms", "--")
                    state["net_jitter"] = ns.get("jitter_ms", "--")
                    state["net_pdr"]    = ns.get("pdr_pct", "--")
        except Exception:
            pass
        time.sleep(30)

def load_network_summary_sim():
    """Simulasi network stats N3IWF 5G realistis."""
    import random
    time.sleep(1)
    with state_lock:
        state["net_avg_ms"] = round(12.5 + random.uniform(-1, 1), 2)
        state["net_min_ms"] = round(8.3  + random.uniform(-0.5, 0.5), 2)
        state["net_max_ms"] = round(21.7 + random.uniform(-1, 2), 2)
        state["net_jitter"] = round(2.1  + random.uniform(-0.3, 0.3), 2)
        state["net_pdr"]    = round(99.2 + random.uniform(-0.5, 0.5), 1)
    print(f"[SIM] Network stats: avg={state['net_avg_ms']}ms jitter={state['net_jitter']}ms PDR={state['net_pdr']}%")
    while True:
        time.sleep(60)

# ── Flask App ─────────────────────────────────────────────────────────────────
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'n3iwf', 'templates')
app = Flask(__name__, template_folder=TEMPLATE_DIR)

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

# ── Simulation Mode (tanpa Pico) ─────────────────────────────────────────────
import math, random

def simulate_pico():
    """Generate sensor data simulasi pH & suhu tanpa Pico fisik."""
    t = 0
    pH  = 7.2
    temp = 28.0
    print("[SIM] Simulasi Pico aktif — generate data setiap 2 detik")
    while True:
        # Simulasi pH naik-turun sekitar 7.0-8.0
        pH   = 7.5 + 0.5 * math.sin(t / 30.0) + random.uniform(-0.05, 0.05)
        temp = 28.0 + 2.0 * math.sin(t / 60.0) + random.uniform(-0.1, 0.1)
        pH   = round(max(5.5, min(9.5, pH)), 3)
        temp = round(max(20.0, min(35.0, temp)), 2)

        inf = run_inference(pH, temp)
        now = time.time()
        with state_lock:
            state["connected"] = True
            state["pico_ip"]   = "SIMULASI"
            state["mode"]      = "REAL"
            state["pH"]        = pH
            state["T"]         = temp
            state["rb_action"]    = inf.get("rb",  {}).get("name", "--")
            state["fql_action"]   = inf.get("fql", {}).get("name", "--")
            state["dqn_action"]   = inf.get("dqn", {}).get("name", "--")
            state["rb_infer_ms"]  = inf.get("rb",  {}).get("ms", 0)
            state["fql_infer_ms"] = inf.get("fql", {}).get("ms", 0)
            state["dqn_infer_ms"] = inf.get("dqn", {}).get("ms", 0)
            state["last_seen"]    = now
            state["total_packets"] += 1
            history.append({"ts": now, "pH": pH, "T": temp,
                            "rb": state["rb_action"],
                            "fql": state["fql_action"],
                            "dqn": state["dqn_action"],
                            "latency": 0})
        print(f"[SIM] pH={pH:.3f} T={temp:.1f}C | "
              f"RB={state['rb_action']} FQL={state['fql_action']} DQN={state['dqn_action']}")
        t += 1
        time.sleep(2)

# ── Main ─────────────────────────────────────────────────────────────────────
import sys as _sys
SIM_MODE = "--sim" in _sys.argv

if __name__ == '__main__':
    if SIM_MODE:
        threading.Thread(target=simulate_pico,          daemon=True).start()
        threading.Thread(target=ipsec_monitor_sim,      daemon=True).start()
        threading.Thread(target=load_network_summary_sim, daemon=True).start()
        print("[INFO] Mode: SIMULASI (tanpa Pico & Callbox)")
    else:
        threading.Thread(target=tcp_server,             daemon=True).start()
        threading.Thread(target=ipsec_monitor,          daemon=True).start()
        threading.Thread(target=load_network_summary,   daemon=True).start()
        print("[INFO] Mode: REAL (menunggu Pico di port 5005)")

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "0.0.0.0"

    print(f"\n{'='*55}")
    print(f"  Aquaculture N3IWF Dashboard v2")
    print(f"{'='*55}")
    print(f"  Dashboard  : http://{local_ip}:5000")
    print(f"  TCP Port   : 5005 (Pico 2W)")
    print(f"  RB         : {'✅' if RB_AVAILABLE else '❌'}")
    print(f"  FQL        : {'✅' if FQL_AVAILABLE else '❌'}")
    print(f"  DQN        : {'✅' if DQN_AVAILABLE else '❌'}")
    print(f"{'='*55}\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
