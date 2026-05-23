#!/usr/bin/env python3
"""
server.py - Aquaculture N3IWF Real Server
==========================================
TCP Server (menerima data REAL dari Pico 2W) +
Flask Dashboard (visualisasi real-time) +
Progressive Learning: Rule-Based → FQL → DQN

Format data dari Pico:
  - Simple test : "TEST_DATA: seq=N, status=OK"
  - Real mode   : "DATA:ph_x1000,temp_x100,risk_level"

Jalankan: 
  python3 n3iwf/server.py
  
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
import csv as _csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

RESULTS_DIR  = os.path.join(BASE_DIR, "results", "n3iwf_real")
NETWORK_DIR  = os.path.join(BASE_DIR, "results", "network")
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(NETWORK_DIR, exist_ok=True)

NETWORK_SUMMARY = os.path.join(NETWORK_DIR, "network_summary.json")
N3IWF_CSV       = os.path.join(RESULTS_DIR, "n3iwf_real_log.csv")
QTABLE_FILE     = os.path.join(RESULTS_DIR, "qtable.json")

# ── CSV Logger ────────────────────────────────────────────────────────────────
_csv_lock = threading.Lock()
_csv_initialized = False

def _init_csv():
    global _csv_initialized
    if _csv_initialized:
        return
    with open(N3IWF_CSV, "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["timestamp", "packet_no", "pH", "T_C",
                    "actual_risk", "rb_risk", "fql_risk", "dqn_risk",
                    "rb_correct", "fql_correct", "dqn_correct",
                    "rb_ms", "fql_ms", "dqn_ms",
                    "latency_ms", "reward"])
    _csv_initialized = True

def log_csv(packet_no, pH, T, actual_risk, rb_risk, fql_risk, dqn_risk,
            rb_correct, fql_correct, dqn_correct, inf, latency, reward):
    with _csv_lock:
        _init_csv()
        with open(N3IWF_CSV, "a", newline="") as f:
            w = _csv.writer(f)
            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                packet_no, round(pH, 3), round(T, 2),
                actual_risk, rb_risk, fql_risk, dqn_risk,
                rb_correct, fql_correct, dqn_correct,
                inf.get("rb",  {}).get("ms", 0),
                inf.get("fql", {}).get("ms", 0),
                inf.get("dqn", {}).get("ms", 0),
                latency,
                round(reward, 4)
            ])

# ── Load AI agents ────────────────────────────────────────────────────────────
RB_AVAILABLE  = False
FQL_AVAILABLE = False
DQN_AVAILABLE = False
fql_agent = None
dqn_agent = None

RISK_LABELS = ["SAFE", "CAUTION", "WARNING", "CRITICAL"]

def calculate_actual_risk(pH: float, T: float) -> int:
    """Calculate actual NH3 risk level (ground truth)."""
    pka = 0.09018 + 2729.92 / (T + 273.15)
    nh3_frac = 1.0 / (1.0 + 10 ** (pka - pH))
    
    if nh3_frac < 0.01:
        return 0  # SAFE
    elif nh3_frac < 0.05:
        return 1  # CAUTION
    elif nh3_frac < 0.10:
        return 2  # WARNING
    else:
        return 3  # CRITICAL

def rule_based_risk(pH: float, T: float) -> int:
    """Simple rule-based risk prediction."""
    return calculate_actual_risk(pH, T)

RB_AVAILABLE = True

try:
    from fql.fql_agent import FQLAgent
    fql_agent = FQLAgent()
    # Load Q-table dari simulation jika ada
    SIM_QTABLE = os.path.join(BASE_DIR, "results", "simulation", "fql_qtable_sim.json")
    if os.path.exists(SIM_QTABLE) and fql_agent.load_qtable(SIM_QTABLE):
        fql_agent.epsilon = 0.01  # Exploitation mode
        FQL_AVAILABLE = True
        print("[FQL] Q-table loaded from simulation (exploitation mode)")
    else:
        FQL_AVAILABLE = True
        print("[FQL] Starting with empty Q-table")
except ImportError as e:
    print(f"[FQL] Import failed: {e}")

try:
    from dqn.dqn_agent import DQNAgent
    dqn_agent = DQNAgent()
    # Load model dari simulation jika ada
    SIM_DQN = os.path.join(BASE_DIR, "results", "simulation", "dqn_model_sim.pt")
    if os.path.exists(SIM_DQN) and dqn_agent.load(SIM_DQN):
        DQN_AVAILABLE = True
        print("[DQN] Model loaded from simulation")
    else:
        DQN_AVAILABLE = True
        print("[DQN] Starting with random weights")
except ImportError as e:
    print(f"[DQN] Import failed: {e}")

def compute_reward(predicted_risk: int, actual_risk: int) -> float:
    """
    Reward function (same as simulation).
    - Correct prediction: +1.0
    - Off by 1 level: -0.5
    - Off by 2+ levels: -1.0
    """
    error = abs(predicted_risk - actual_risk)
    if error == 0:
        return +1.0
    elif error == 1:
        return -0.5
    else:
        return -1.0

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

    # Risk predictions
    "actual_risk": "--",
    "rb_risk": "--",
    "fql_risk": "--",
    "dqn_risk": "--",
    "reward": 0.0,

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

    # Network stats
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

# ── AI Inference ──────────────────────────────────────────────────────────────
def run_inference(pH: float, T: float) -> dict:
    """Run inference on all agents and return results."""
    results = {}
    
    # Rule-Based
    t0 = time.perf_counter()
    rb_risk = rule_based_risk(pH, T)
    rb_ms = (time.perf_counter() - t0) * 1000
    results["rb"] = {"risk": rb_risk, "label": RISK_LABELS[rb_risk], "ms": round(rb_ms, 3)}
    
    # FQL
    if FQL_AVAILABLE and fql_agent:
        t0 = time.perf_counter()
        fql_risk = fql_agent.predict_risk(pH, T)
        fql_ms = (time.perf_counter() - t0) * 1000
        results["fql"] = {"risk": fql_risk, "label": RISK_LABELS[fql_risk], "ms": round(fql_ms, 3)}
    else:
        results["fql"] = {"risk": -1, "label": "N/A", "ms": 0}
    
    # DQN
    if DQN_AVAILABLE and dqn_agent and dqn_agent.ready:
        t0 = time.perf_counter()
        dqn_risk = dqn_agent.predict_risk(pH, T)
        dqn_ms = (time.perf_counter() - t0) * 1000
        results["dqn"] = {"risk": dqn_risk, "label": RISK_LABELS[dqn_risk], "ms": round(dqn_ms, 3)}
    else:
        results["dqn"] = {"risk": -1, "label": "N/A", "ms": 0}
    
    return results

# ── TCP Server Thread ─────────────────────────────────────────────────────────
DATA_RE = re.compile(r'^DATA:(-?\d+),(-?\d+),([0-3])$')

def tcp_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 5000))
    srv.listen(1)
    print("[TCP] Waiting for Pico WH on port 5000 ...")

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

                        # ── Real sensor data: DATA:ph_x1000,temp_x100,risk_level
                        m = DATA_RE.match(line)
                        if m:
                            pH = int(m.group(1)) / 1000.0
                            T  = int(m.group(2)) / 100.0
                            actual_risk = int(m.group(3))
                            
                            # Run inference on all agents
                            inf = run_inference(pH, T)
                            
                            rb_risk = inf["rb"]["risk"]
                            fql_risk = inf["fql"]["risk"]
                            dqn_risk = inf["dqn"]["risk"]
                            
                            # Calculate correctness
                            rb_correct = 1 if rb_risk == actual_risk else 0
                            fql_correct = 1 if fql_risk == actual_risk else 0
                            dqn_correct = 1 if dqn_risk == actual_risk else 0
                            
                            # Calculate reward (use best agent)
                            if dqn_risk >= 0:
                                reward = compute_reward(dqn_risk, actual_risk)
                            elif fql_risk >= 0:
                                reward = compute_reward(fql_risk, actual_risk)
                            else:
                                reward = compute_reward(rb_risk, actual_risk)
                            
                            with state_lock:
                                state["mode"] = "REAL"
                                state["pH"] = pH
                                state["T"] = T
                                state["actual_risk"] = RISK_LABELS[actual_risk]
                                state["rb_risk"] = inf["rb"]["label"]
                                state["fql_risk"] = inf["fql"]["label"]
                                state["dqn_risk"] = inf["dqn"]["label"]
                                state["reward"] = reward
                                state["rb_infer_ms"] = inf["rb"]["ms"]
                                state["fql_infer_ms"] = inf["fql"]["ms"]
                                state["dqn_infer_ms"] = inf["dqn"]["ms"]
                                state["last_seen"] = now
                                state["total_packets"] += 1
                                state["latency_ms"].append(latency)
                                if len(state["latency_ms"]) > 50:
                                    state["latency_ms"].pop(0)
                                history.append({
                                    "ts": now, "pH": pH, "T": T,
                                    "actual_risk": RISK_LABELS[actual_risk],
                                    "rb_risk": inf["rb"]["label"],
                                    "fql_risk": inf["fql"]["label"],
                                    "dqn_risk": inf["dqn"]["label"],
                                    "reward": reward,
                                    "latency": latency
                                })
                            
                            log_csv(state["total_packets"], pH, T, actual_risk,
                                   rb_risk, fql_risk, dqn_risk,
                                   rb_correct, fql_correct, dqn_correct,
                                   inf, latency, reward)
                            
                            print(f"[REAL] pH={pH:.2f} T={T:.1f}°C | "
                                  f"Actual={RISK_LABELS[actual_risk]} | "
                                  f"RB={inf['rb']['label']} "
                                  f"FQL={inf['fql']['label']} "
                                  f"DQN={inf['dqn']['label']} | "
                                  f"Reward={reward:.3f}")

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

# ── Flask App ─────────────────────────────────────────────────────────────────
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
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

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=tcp_server,             daemon=True).start()
    threading.Thread(target=ipsec_monitor,          daemon=True).start()
    threading.Thread(target=load_network_summary,   daemon=True).start()

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "0.0.0.0"

    print(f"\n{'='*60}")
    print(f"  Aquaculture N3IWF Real Server")
    print(f"{'='*60}")
    print(f"  Dashboard  : http://{local_ip}:8080")
    print(f"  TCP Port   : 5000 (Pico WH)")
    print(f"  Mode       : REAL (data dari Pico)")
    print(f"  RB         : {'✅' if RB_AVAILABLE else '❌'}")
    print(f"  FQL        : {'✅' if FQL_AVAILABLE else '❌'}")
    print(f"  DQN        : {'✅' if DQN_AVAILABLE else '❌'}")
    print(f"  CSV Log    : {N3IWF_CSV}")
    print(f"{'='*60}\n")

    app.run(host='0.0.0.0', port=8080, debug=False)
