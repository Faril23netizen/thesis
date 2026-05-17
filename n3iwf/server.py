#!/usr/bin/env python3
"""
server.py - Aquaculture N3IWF Real Server
==========================================
TCP Server (menerima data REAL dari Pico 2W) +
Flask Dashboard (visualisasi real-time) +
Progressive Learning: Rule-Based → FQL → DQN +
Home Assistant IoT Comparison (optional)

Bedanya dengan testing_n3iwf:
  - testing_n3iwf: Mode --sim (data sintetis, tanpa Pico)
  - n3iwf/server.py: Mode REAL (data dari Pico fisik, progressive learning)

Format data dari Pico:
  - Simple test : "TEST_DATA: seq=N, status=OK"
  - Real mode   : "DATA:ph_x1000,temp_x100,action"

Jalankan: 
  python3 n3iwf/server.py                    # Tanpa Home Assistant
  python3 n3iwf/server.py --with-ha          # Dengan Home Assistant comparison
  
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
COMPARISON_CSV  = os.path.join(RESULTS_DIR, "edge_vs_cloud_comparison.csv")
QTABLE_FILE     = os.path.join(RESULTS_DIR, "qtable.json")

# ── Home Assistant Config ─────────────────────────────────────────────────────
# EDIT INI SESUAI SETUP HOME ASSISTANT ANDA
HA_ENABLED = False  # Will be set by --with-ha flag
HA_CONFIG = {
    "url": "http://192.168.1.100:8123",
    "token": "your_long_lived_access_token_here",
    "ph_entity": "sensor.aquaculture_ph",
    "temp_entity": "sensor.aquaculture_temperature"
}

ha_bridge = None

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
                    "phase", "action", "reward",
                    "rb_ms", "fql_ms", "dqn_ms",
                    "latency_ms", "buffer_size", "fql_eps"])
    _csv_initialized = True

def log_csv(packet_no, pH, T, phase, action_name, reward, inf, latency, buffer_size, fql_eps):
    with _csv_lock:
        _init_csv()
        with open(N3IWF_CSV, "a", newline="") as f:
            w = _csv.writer(f)
            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                packet_no, round(pH, 3), round(T, 2),
                phase, action_name, round(reward, 4),
                inf.get("rb",  {}).get("ms", 0),
                inf.get("fql", {}).get("ms", 0),
                inf.get("dqn", {}).get("ms", 0),
                latency,
                buffer_size,
                round(fql_eps, 4)
            ])

# ── Load AI agents ────────────────────────────────────────────────────────────
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
    fql_agent = FQLAgent()
    # Load Q-table dari simulation jika ada
    SIM_QTABLE = os.path.join(BASE_DIR, "results", "simulation", "qtable.json")
    if os.path.exists(SIM_QTABLE) and fql_agent.load_qtable(SIM_QTABLE):
        fql_agent.epsilon = 0.3  # Mulai dengan exploration
        FQL_AVAILABLE = True
        print("[FQL] Q-table loaded from simulation, epsilon=0.3")
    else:
        FQL_AVAILABLE = True
        print("[FQL] Starting with empty Q-table")
except ImportError as e:
    print(f"[FQL] Import failed: {e}")

try:
    from dqn.dqn_agent import DQNAgent
    dqn_agent = DQNAgent()
    # Load model dari simulation jika ada
    SIM_DQN = os.path.join(BASE_DIR, "results", "simulation", "dqn_model.pt")
    if os.path.exists(SIM_DQN) and dqn_agent.load(SIM_DQN):
        DQN_AVAILABLE = True
        print("[DQN] Model loaded from simulation")
    else:
        DQN_AVAILABLE = True
        print("[DQN] Starting with random weights")
except ImportError as e:
    print(f"[DQN] Import failed: {e}")

# ── Progressive Learning State ────────────────────────────────────────────────
PHASE_RB_STEPS  = 100   # 100 steps Rule-Based
PHASE_FQL_STEPS = 200   # 200 steps FQL
# Setelah itu: DQN forever

progressive_state = {
    "phase": "RB",           # RB → FQL → DQN
    "rb_steps": 0,
    "fql_steps": 0,
    "dqn_steps": 0,
    "total_steps": 0,
    "buffer": [],            # Replay buffer untuk DQN
    "last_state": None,
    "last_action": None,
}

def get_current_phase():
    """Tentukan phase berdasarkan jumlah steps."""
    if progressive_state["rb_steps"] < PHASE_RB_STEPS:
        return "RB"
    elif progressive_state["fql_steps"] < PHASE_FQL_STEPS:
        return "FQL"
    else:
        return "DQN"

def compute_reward(pH: float, T: float, action: int) -> float:
    """Reward function: stability + cost."""
    pH_penalty = 0
    if pH < 6.5 or pH > 8.5:
        pH_penalty = abs(7.0 - pH) * 0.5
    
    T_penalty = 0
    if T > 30.0:
        T_penalty = (T - 30.0) * 0.1
    
    cost = ACTION_COST[action]
    reward = 1.0 - pH_penalty - T_penalty - cost
    return max(-2.0, min(2.0, reward))

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

    # Progressive learning
    "phase": "RB",
    "action": "--",
    "reward": 0.0,
    "rb_steps": 0,
    "fql_steps": 0,
    "dqn_steps": 0,
    "total_steps": 0,
    "buffer_size": 0,
    "fql_eps": 1.0,

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

# ── AI Inference with Progressive Learning ────────────────────────────────────
def run_progressive_inference(pH: float, T: float) -> dict:
    """Run inference berdasarkan phase saat ini + update learning."""
    results = {}
    phase = get_current_phase()
    
    # Selalu hitung semua untuk comparison
    t0 = time.perf_counter()
    rb_act = rule_based_action(pH, T)
    rb_ms = (time.perf_counter() - t0) * 1000
    results["rb"] = {"action": rb_act, "name": ACTION_NAMES[rb_act], "ms": round(rb_ms, 3)}
    
    if FQL_AVAILABLE and fql_agent:
        t0 = time.perf_counter()
        fql_act = fql_agent.select_action(pH, T)
        fql_ms = (time.perf_counter() - t0) * 1000
        results["fql"] = {"action": fql_act, "name": ACTION_NAMES[fql_act], "ms": round(fql_ms, 3)}
    
    if DQN_AVAILABLE and dqn_agent:
        t0 = time.perf_counter()
        dqn_act = dqn_agent.select_action(pH, T)
        dqn_ms = (time.perf_counter() - t0) * 1000
        results["dqn"] = {"action": dqn_act, "name": ACTION_NAMES[dqn_act], "ms": round(dqn_ms, 3)}
    
    # Pilih action berdasarkan phase
    if phase == "RB":
        chosen_action = rb_act
        progressive_state["rb_steps"] += 1
    elif phase == "FQL" and FQL_AVAILABLE:
        chosen_action = fql_act
        progressive_state["fql_steps"] += 1
        
        # FQL Learning: update Q-table
        if progressive_state["last_state"] is not None:
            last_pH, last_T = progressive_state["last_state"]
            last_action = progressive_state["last_action"]
            reward = compute_reward(last_pH, last_T, last_action)
            fql_agent.update(last_pH, last_T, last_action, reward, pH, T)
        
        progressive_state["last_state"] = (pH, T)
        progressive_state["last_action"] = chosen_action
    elif phase == "DQN" and DQN_AVAILABLE:
        chosen_action = dqn_act
        progressive_state["dqn_steps"] += 1
        
        # DQN Learning: store in replay buffer
        if progressive_state["last_state"] is not None:
            last_pH, last_T = progressive_state["last_state"]
            last_action = progressive_state["last_action"]
            reward = compute_reward(last_pH, last_T, last_action)
            
            progressive_state["buffer"].append({
                "state": [last_pH, last_T],
                "action": last_action,
                "reward": reward,
                "next_state": [pH, T],
                "done": False
            })
            
            # Keep buffer size manageable
            if len(progressive_state["buffer"]) > 10000:
                progressive_state["buffer"].pop(0)
            
            # Train DQN every 10 steps
            if progressive_state["dqn_steps"] % 10 == 0 and len(progressive_state["buffer"]) >= 32:
                import random
                batch = random.sample(progressive_state["buffer"], 32)
                dqn_agent.train_batch(batch)
        
        progressive_state["last_state"] = (pH, T)
        progressive_state["last_action"] = chosen_action
    else:
        chosen_action = rb_act  # Fallback
    
    progressive_state["total_steps"] += 1
    progressive_state["phase"] = phase
    
    results["chosen"] = {
        "action": chosen_action,
        "name": ACTION_NAMES[chosen_action],
        "phase": phase
    }
    
    return results

# ── TCP Server Thread ─────────────────────────────────────────────────────────
DATA_RE = re.compile(r'^DATA:(-?\d+),(-?\d+),([0-3])$')

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
                            
                            # Run progressive inference
                            inf = run_progressive_inference(pH, T)
                            chosen = inf["chosen"]
                            reward = compute_reward(pH, T, chosen["action"])
                            
                            with state_lock:
                                state["mode"] = "REAL"
                                state["pH"] = pH
                                state["T"] = T
                                state["phase"] = chosen["phase"]
                                state["action"] = chosen["name"]
                                state["reward"] = reward
                                state["rb_steps"] = progressive_state["rb_steps"]
                                state["fql_steps"] = progressive_state["fql_steps"]
                                state["dqn_steps"] = progressive_state["dqn_steps"]
                                state["total_steps"] = progressive_state["total_steps"]
                                state["buffer_size"] = len(progressive_state["buffer"])
                                state["fql_eps"] = fql_agent.epsilon if fql_agent else 0
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
                                    "phase": chosen["phase"],
                                    "action": chosen["name"],
                                    "reward": reward,
                                    "latency": latency
                                })
                            
                            log_csv(state["total_packets"], pH, T, chosen["phase"], 
                                   chosen["name"], reward, inf, latency,
                                   len(progressive_state["buffer"]),
                                   fql_agent.epsilon if fql_agent else 0)
                            
                            print(f"[{chosen['phase']}] pH={pH:.2f} T={T:.1f}°C | "
                                  f"Action={chosen['name']} Reward={reward:.3f} | "
                                  f"Steps: RB={progressive_state['rb_steps']} "
                                  f"FQL={progressive_state['fql_steps']} "
                                  f"DQN={progressive_state['dqn_steps']}")
                            
                            # Save Q-table setiap 50 steps FQL
                            if chosen["phase"] == "FQL" and progressive_state["fql_steps"] % 50 == 0:
                                if fql_agent and fql_agent.save_qtable(QTABLE_FILE):
                                    print(f"  [FQL] Q-table saved ({progressive_state['fql_steps']} steps)")

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
    print(f"  Aquaculture N3IWF Real Server — Progressive Learning")
    print(f"{'='*60}")
    print(f"  Dashboard  : http://{local_ip}:5000")
    print(f"  TCP Port   : 5005 (Pico 2W)")
    print(f"  Mode       : REAL (data dari Pico)")
    print(f"  Learning   : RB({PHASE_RB_STEPS}) → FQL({PHASE_FQL_STEPS}) → DQN")
    print(f"  RB         : {'✅' if RB_AVAILABLE else '❌'}")
    print(f"  FQL        : {'✅' if FQL_AVAILABLE else '❌'}")
    print(f"  DQN        : {'✅' if DQN_AVAILABLE else '❌'}")
    print(f"  CSV Log    : {N3IWF_CSV}")
    print(f"{'='*60}\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
