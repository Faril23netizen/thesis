#!/usr/bin/env python3
"""
dashboard.py - Aquaculture N3IWF Dashboard
===========================================
Membaca state dari run_real.py via state.json + comparison.csv.
TIDAK membuka TCP server sendiri (port 5005 milik run_real.py / WiFiBridge).

Jalankan BERSAMAAN dengan run_real.py:
  Terminal 1: python3 -m main.real.run_real
  Terminal 2: python3 n3iwf/dashboard.py

Dashboard: http://<IP_RPI5>:5000
"""

import os
import sys
import csv
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

RESULTS_REAL    = os.path.join(BASE_DIR, "results", "hasil_real")
NETWORK_DIR     = os.path.join(BASE_DIR, "results", "network")
STATE_JSON      = os.path.join(RESULTS_REAL, "state.json")
COMPARISON_CSV  = os.path.join(RESULTS_REAL, "comparison.csv")
NETWORK_SUMMARY = os.path.join(NETWORK_DIR,  "network_summary.json")

# ── Shared state ──────────────────────────────────────────────────────────────
state = {
    # Dari state.json (ditulis oleh run_real.py setiap real step)
    "pH": None, "T": None,
    "action": "--",
    "phase": "--",        # Rule-Based / FQL / DQN
    "real_steps": 0,
    "buffer_size": 0,
    "reward": 0,
    "fql_eps": 1.0,
    "run_real_active": False,

    # 5G Network stats (dari latency_test.py)
    "net_avg_ms": "--", "net_min_ms": "--",
    "net_max_ms": "--", "net_jitter": "--", "net_pdr": "--",
    "live_rtt_ms": None,

    # IPsec
    "ipsec": False, "ipsec_detail": "--",

    # Comparison CSV summary
    "rb_avg_reward": None,
    "fql_avg_reward": None,
    "dqn_avg_reward": None,
    "rb_steps": 0, "fql_steps": 0, "dqn_steps": 0,
}

latency_history = deque(maxlen=60)
comparison_history = deque(maxlen=300)   # last 300 rows dari comparison.csv
lock = threading.Lock()

# ── State JSON Reader ─────────────────────────────────────────────────────────
def state_reader():
    """Baca state.json yang ditulis run_real.py setiap 0.5 detik."""
    last_mtime = 0
    while True:
        try:
            if os.path.exists(STATE_JSON):
                mtime = os.path.getmtime(STATE_JSON)
                if mtime != last_mtime:
                    last_mtime = mtime
                    with open(STATE_JSON) as f:
                        s = json.load(f)
                    with lock:
                        state["pH"]             = s.get("pH")
                        state["T"]              = s.get("T")
                        state["action"]         = s.get("action", "--")
                        state["phase"]          = s.get("phase", "--")
                        state["real_steps"]     = s.get("real_steps", 0)
                        state["buffer_size"]    = s.get("buffer_size", 0)
                        state["reward"]         = s.get("reward", 0)
                        state["fql_eps"]        = s.get("fql_eps", 1.0)
                        state["run_real_active"] = True
        except Exception:
            with lock:
                state["run_real_active"] = False
        time.sleep(0.5)

# ── Comparison CSV Reader ─────────────────────────────────────────────────────
def csv_reader():
    """Baca comparison.csv, hitung avg reward per phase."""
    last_size = 0
    while True:
        try:
            if os.path.exists(COMPARISON_CSV):
                sz = os.path.getsize(COMPARISON_CSV)
                if sz != last_size and sz > 0:
                    last_size = sz
                    rb_r, fql_r, dqn_r = [], [], []
                    rows = []
                    with open(COMPARISON_CSV, newline="") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            try:
                                mode   = row.get("mode","")
                                reward = float(row.get("reward", 0))
                                if mode == "RB":  rb_r.append(reward)
                                elif mode == "FQL": fql_r.append(reward)
                                elif mode == "DQN": dqn_r.append(reward)
                                rows.append(row)
                            except (ValueError, KeyError):
                                pass
                    with lock:
                        state["rb_avg_reward"]  = round(sum(rb_r)/len(rb_r), 4) if rb_r else None
                        state["fql_avg_reward"] = round(sum(fql_r)/len(fql_r), 4) if fql_r else None
                        state["dqn_avg_reward"] = round(sum(dqn_r)/len(dqn_r), 4) if dqn_r else None
                        state["rb_steps"]  = len(rb_r)
                        state["fql_steps"] = len(fql_r)
                        state["dqn_steps"] = len(dqn_r)
                        comparison_history.clear()
                        comparison_history.extend(rows[-300:])
        except Exception:
            pass
        time.sleep(5)

# ── IPsec Monitor ─────────────────────────────────────────────────────────────
def ipsec_monitor():
    while True:
        try:
            r = subprocess.run(["sudo","ipsec","statusall"],
                               capture_output=True, text=True, timeout=5)
            ok = "ESTABLISHED" in r.stdout
            detail = "--"
            if ok:
                for line in r.stdout.splitlines():
                    if "ESTABLISHED" in line:
                        detail = line.strip(); break
            with lock:
                state["ipsec"] = ok
                state["ipsec_detail"] = detail
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

# ── Live Ping ─────────────────────────────────────────────────────────────────
def live_ping(target: str = "192.168.100.101", interval: int = 3):
    """Ping Callbox setiap interval detik untuk latency live chart."""
    print(f"[PING] Live ping to {target} every {interval}s")
    while True:
        rtt = None
        try:
            r = subprocess.run(["ping","-c","1","-W","2",target],
                               capture_output=True, text=True, timeout=4)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if "time=" in line:
                        rtt = round(float(line.split("time=")[1].split(" ")[0]), 2)
                        break
        except Exception: pass
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
        return jsonify(dict(state))

@app.route('/api/latency_history')
def get_latency_history():
    with lock: return jsonify(list(latency_history))

@app.route('/api/comparison')
def get_comparison():
    with lock: return jsonify(list(comparison_history)[-100:])

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(RESULTS_REAL, exist_ok=True)
    os.makedirs(NETWORK_DIR,  exist_ok=True)

    threading.Thread(target=state_reader,    daemon=True).start()
    threading.Thread(target=csv_reader,      daemon=True).start()
    threading.Thread(target=ipsec_monitor,   daemon=True).start()
    threading.Thread(target=net_stats_loader, daemon=True).start()
    threading.Thread(target=live_ping,       daemon=True).start()

    try: ip = socket.gethostbyname(socket.gethostname())
    except: ip = "0.0.0.0"

    print(f"\n{'='*55}")
    print(f"  Aquaculture N3IWF Dashboard")
    print(f"  Dashboard : http://{ip}:5000")
    print(f"  Membaca   : {STATE_JSON}")
    print(f"  CSV       : {COMPARISON_CSV}")
    print(f"")
    print(f"  ⚠️  Jalankan run_real.py di terminal lain:")
    print(f"      python3 -m main.real.run_real")
    print(f"{'='*55}\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
