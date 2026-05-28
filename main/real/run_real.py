
"""
Main FQL — Raspberry Pi 4 (Multi-Node Monitoring System)
=================================================
NH3 Risk Monitoring System - NO AERATOR CONTROL

Progressive Learning: Rule-Based -> FQL -> DQN
Multi-Node Support: Dynamically creates separate Agent & Session for each Pico
"""

import csv
import json
import logging
import os
import signal
import sys
import time
import numpy as np

from fql.fql_agent import FQLAgent, calculate_actual_risk, RISK_SAFE, RISK_CAUTION, RISK_WARNING, RISK_CRITICAL
from main.real.wifi_bridge import WiFiBridge, _setup_pico_monitor_log
from dqn.dqn_agent import DQNAgent

try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "n3iwf"))
    from homeassistant_bridge import HomeAssistantBridge
    HA_AVAILABLE = True
except ImportError as e:
    HA_AVAILABLE = False

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_REAL    = os.path.join(BASE_DIR, "results", "hasil_real")
NETWORK_STATS   = os.path.join(BASE_DIR, "results", "network", "callbox_stats.json")
STATE_JSON_FILE = os.path.join(RESULTS_REAL, "state.json")

# Hyperparameters
LOG_INTERVAL           = 10
SUMMARY_INTERVAL       = 100
RECONNECT_DELAY        = 2
DISCONNECT_TIMEOUT     = 30.0

BUFFER_AUTOSAVE        = 100
DQN_BUFFER_READY       = 1000
DQN_BUFFER_MAX         = 20000
DQN_TRAIN_EPOCHS       = 2000
DQN_RETRAIN_INTERVAL   = 500
FQL_MIN_REAL_STEPS     = 1000

QTABLE_UPDATE_INTERVAL = 200
FQL_RETRY_INTERVAL     = 10.0

_shutdown = False

def signal_handler(sig, frame):
    global _shutdown
    _shutdown = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def setup_logging():
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("socketio").setLevel(logging.WARNING)
    logging.getLogger("engineio").setLevel(logging.WARNING)
    
    logger = logging.getLogger("run_real")
    logger.setLevel(logging.DEBUG)
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger

def attach_file_loggers(logger, session_dir):
    for h in logger.handlers[:]:
        if isinstance(h, logging.FileHandler):
            logger.removeHandler(h)
            h.close()
    fh = logging.FileHandler(os.path.join(session_dir, "run_real.log"))
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

RISK_LABELS = ["SAFE", "CAUTION", "WARNING", "CRITICAL"]

def nh3_fraction(pH, T):
    pka = 0.09018 + 2729.92 / (T + 273.15)
    return 1.0 / (1.0 + 10 ** (pka - pH))

def rule_based_risk(pH, T):
    nh3_pct = nh3_fraction(pH, T) * 100.0
    if nh3_pct < 1.0: return RISK_SAFE
    elif nh3_pct < 5.0: return RISK_CAUTION
    elif nh3_pct < 10.0: return RISK_WARNING
    else: return RISK_CRITICAL

def get_network_qos(node_id, bridge=None):
    if bridge is not None:
        return bridge.get_node_qos(node_id)
    return {"latency_ms": 0.0, "jitter_ms": 0.0, "bandwidth_mbps": 0.0}

class NodeState:
    def __init__(self, node_id, base_dir, logger):
        self.node_id = node_id
        self.logger = logger
        
        session_ts = time.strftime("%Y%m%d_%H%M%S")
        self.dir = os.path.join(base_dir, node_id, f"session_{session_ts}")
        os.makedirs(self.dir, exist_ok=True)
        
        # Attach file log specific to this node's session folder
        fh = logging.FileHandler(os.path.join(self.dir, "run_real.log"))
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        _setup_pico_monitor_log(self.dir)
        
        self.fql = FQLAgent()
        self.dqn = DQNAgent()
        self.buffer_dqn = []
        
        self.real_steps = 0
        self.dqn_ready_logged = False
        self.dqn_model_ready = False
        self.dqn_active = False
        self.last_qtable_retry = 0.0
        self.last_qtable_update = 0
        self.last_dqn_retrain = 0
        self.fql_mode_start = None
        self.last_data_time = time.time()
        
        self.qtable_file = os.path.join(self.dir, "qtable.json")
        self.buffer_file = os.path.join(self.dir, "dqn_buffer.json")
        self.dqn_model_file = os.path.join(self.dir, "dqn_model.pt")
        
        self.csv_path = os.path.join(self.dir, "comparison.csv")
        write_header = not os.path.exists(self.csv_path)
        self.csv_file = open(self.csv_path, "a", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        
        if write_header:
            self.csv_writer.writerow([
                "timestamp", "real_step", "pH", "T_C", "NH3_pct",
                "mode", "actual_risk", "rb_risk", "fql_risk", "dqn_risk",
                "rb_correct", "fql_correct", "dqn_correct",
                "fql_steps", "epsilon",
                "bandwidth_mbps", "latency_ms", "jitter_ms"
            ])
            self.csv_file.flush()
            
    def append_transition(self, s, a, r, s_next):
        self.buffer_dqn.append({
            "s": s, "a": a, "r": round(r, 5), "s_next": s_next,
        })
        if len(self.buffer_dqn) > DQN_BUFFER_MAX:
            self.buffer_dqn.pop(0)
            
    def log_comparison(self, pH, T, mode, dqn_risk, fql_risk, actual_risk, rb_risk, qos):
        rb_correct = 1 if rb_risk == actual_risk else 0
        fql_correct = 1 if fql_risk == actual_risk else 0
        dqn_correct = 1 if dqn_risk == actual_risk else 0 if self.dqn_active else -1
        
        nh3_pct = nh3_fraction(pH, T) * 100.0
        stats = self.fql.get_stats()
        
        self.csv_writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"), self.real_steps,
            round(pH, 4), round(T, 2), round(nh3_pct, 4),
            mode, actual_risk, rb_risk, fql_risk, dqn_risk,
            rb_correct, fql_correct, dqn_correct,
            stats["total_steps"], round(self.fql.epsilon, 4),
            qos.get("bandwidth_mbps", 0.0), qos.get("latency_ms", 0.0), qos.get("jitter_ms", 0.0)
        ])
        self.csv_file.flush()

    def save_buffer(self):
        with open(self.buffer_file, "w") as f:
            json.dump(self.buffer_dqn, f, indent=2)

    def close(self):
        self.fql.save_qtable(self.qtable_file)
        self.save_buffer()
        if self.csv_file:
            self.csv_file.close()


def main():
    global _shutdown
    logger = setup_logging()
    logger.info("=" * 65)
    logger.info("Aquaculture NH3 Risk Monitoring System - MULTI-NODE")
    logger.info("=" * 65)

    bridge = WiFiBridge(port=5000)
    session = 0

    while not _shutdown:
        session += 1
        logger.info(f"PHASE A - Waiting for Pico connection... (session #{session})")
        while not _shutdown:
            if bridge.connect():
                logger.info("First Pico connected!")
                break
            time.sleep(RECONNECT_DELAY)

        if _shutdown:
            break

        nodes = {} # node_id -> NodeState
        last_qos_write = 0.0
        QOS_WRITE_INTERVAL = 3.0  # write callbox_stats.json every 3 seconds

        logger.info("PHASE B — FQL learning risk prediction from real Pico data...")

        while not _shutdown:
            parsed_results = bridge.read_data_line()
            
            if len(bridge.clients) == 0:
                logger.warning("[DISCONNECT] All Picos disconnected. Returning to Phase A...")
                bridge.disconnect()
                break

            for node_id, data in parsed_results.items():
                if node_id not in nodes:
                    logger.info(f"Initialize AI Agent & Folder for new node: {node_id}")
                    # Each node gets its own subfolder: results/hasil_real/Pico_1_Main/session_XXX/
                    nodes[node_id] = NodeState(node_id, RESULTS_REAL, logger)
                
                node = nodes[node_id]
                node.last_data_time = time.time()
                
                pH = data["pH"]
                T  = data["T"]
                node.real_steps += 1
            
                qos = get_network_qos(node_id, bridge)
                actual_risk = calculate_actual_risk(pH, T)
                rb_risk = rule_based_risk(pH, T)
                fql_risk = node.fql.predict_risk(pH, T)
                dqn_risk = node.dqn.predict_risk(pH, T) if node.dqn_active and node.dqn.ready else -1
            
                node.fql.update(pH, T, fql_risk, actual_risk)
            
                mode = "DQN" if node.dqn_active else ("FQL" if node.fql.converged_sent else "RB")
                node.log_comparison(pH, T, mode, dqn_risk, fql_risk, actual_risk, rb_risk, qos)
            
                node.append_transition(s=[pH, T], a=actual_risk, r=1.0 if fql_risk==actual_risk else -1.0, s_next=[pH, T])

                if len(node.buffer_dqn) % BUFFER_AUTOSAVE == 0 and len(node.buffer_dqn) > 0:
                    node.save_buffer()

                fql_real_elapsed = (node.real_steps - node.fql_mode_start) if node.fql_mode_start else 0

                # PHASE D: Train DQN
                if (len(node.buffer_dqn) >= DQN_BUFFER_READY and node.fql.converged_sent 
                    and not node.dqn_model_ready and not node.dqn_ready_logged):
                    node.dqn_ready_logged = True
                    logger.info(f"[{node_id}] PHASE D — DQN training: {len(node.buffer_dqn)} transitions")
                    node.save_buffer()
                    try:
                        from dqn.train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
                        if TORCH_AVAILABLE:
                            train_pytorch(node.buffer_dqn, DQN_TRAIN_EPOCHS, node.dqn_model_file)
                        else:
                            train_numpy(node.buffer_dqn, DQN_TRAIN_EPOCHS, node.dqn_model_file)
                        if node.dqn.load(node.dqn_model_file):
                            node.dqn_model_ready = True
                            node.last_dqn_retrain = node.real_steps
                            logger.info(f"[{node_id}] DQN ready.")
                    except Exception as e:
                        logger.error(f"[{node_id}] DQN training failed: {e}")

                # PHASE E: Activate DQN
                elif (node.dqn_model_ready and not node.dqn_active and fql_real_elapsed >= FQL_MIN_REAL_STEPS):
                    node.dqn_active = True
                    bridge.send_qtable(node.dqn.to_qtable_string()) # broadcasts to all, but node specific in future
                    logger.info(f"[{node_id}] PHASE E — DQN activated.")

                elif node.dqn_active and node.real_steps - node.last_dqn_retrain >= DQN_RETRAIN_INTERVAL:
                    node.save_buffer()
                    try:
                        from dqn.train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
                        if TORCH_AVAILABLE:
                            train_pytorch(node.buffer_dqn, DQN_TRAIN_EPOCHS, node.dqn_model_file)
                        else:
                            train_numpy(node.buffer_dqn, DQN_TRAIN_EPOCHS, node.dqn_model_file)
                        if node.dqn.load(node.dqn_model_file):
                            node.last_dqn_retrain = node.real_steps
                            bridge.send_qtable(node.dqn.to_qtable_string())
                    except Exception:
                        pass

                if node.fql.check_convergence() and not node.fql.converged_sent:
                    node.fql.save_qtable(node.qtable_file)
                    bridge.send_qtable(node.fql.get_qtable_string())
                    node.fql.converged_sent = True
                    node.fql_mode_start = node.real_steps
                    logger.info(f"[{node_id}] FQL CONVERGED.")
                elif node.fql.converged and not node.fql.converged_sent and time.time() - node.last_qtable_retry > FQL_RETRY_INTERVAL:
                    bridge.send_qtable(node.fql.get_qtable_string())
                    node.fql.converged_sent = True
                    node.fql_mode_start = node.real_steps
                elif node.fql.converged_sent and node.real_steps - node.last_qtable_update >= QTABLE_UPDATE_INTERVAL:
                    bridge.send_qtable(node.fql.get_qtable_string())
                    node.fql.save_qtable(node.qtable_file)
                    node.last_qtable_update = node.real_steps

                if node.real_steps % LOG_INTERVAL == 0:
                    nh3_pct = nh3_fraction(pH, T) * 100.0
                    stats = node.fql.get_stats()
                    logger.info(
                        f"[{node_id}][{mode}][Step:{node.real_steps:5d}] "
                        f"pH:{pH:.3f} T:{T:.1f}°C NH3:{nh3_pct:.2f}% | "
                        f"Risk: {RISK_LABELS[actual_risk]} | Acc: {stats['avg_accuracy_100']:.2%} | "
                        f"QoS: {qos.get('bandwidth_mbps',0.0):.3f}Mbps {qos.get('latency_ms',0.0):.1f}ms"
                    )
            
            # Dashboard state dump (Using Pico_1_Main as reference for dashboard)
            main_node = nodes.get("Pico_1_Main")
            if main_node:
                stats = main_node.fql.get_stats()
                state_dump = {
                    "pH": round(pH, 3), "T": round(T, 2),
                    "nh3_pct": round(nh3_fraction(pH, T) * 100.0, 2),
                    "actual_risk": RISK_LABELS[actual_risk],
                    "rb_risk": RISK_LABELS[rule_based_risk(pH,T)],
                    "fql_risk": RISK_LABELS[main_node.fql.predict_risk(pH,T)],
                    "dqn_risk": RISK_LABELS[main_node.dqn.predict_risk(pH,T)] if main_node.dqn_active else "N/A",
                    "phase": "DQN" if main_node.dqn_active else ("FQL" if main_node.fql.converged_sent else "Rule-Based"),
                    "reward": round(stats.get('avg_reward_100', 0.0), 4),
                    "buffer_size": len(main_node.buffer_dqn),
                    "accuracy": round(stats['avg_accuracy_100'], 4),
                    "real_steps": main_node.real_steps,
                    "fql_eps": round(main_node.fql.epsilon, 3),
                    "dqn_ready": main_node.dqn_model_ready,
                    "dqn_active": main_node.dqn_active,
                    "connected_picos": len(bridge.clients)
                }
                with open(STATE_JSON_FILE, "w") as f:
                    json.dump(state_dump, f)

            # Periodic QoS write so dashboard can read node data
            now_t = time.time()
            if now_t - last_qos_write >= QOS_WRITE_INTERVAL:
                bridge.write_qos_stats(NETWORK_STATS)
                last_qos_write = now_t

            time.sleep(0.01)

        # Cleanup inner loop
        for node in nodes.values():
            node.close()

    bridge.disconnect()
    logger.info("System stopped.")

if __name__ == "__main__":
    main()
