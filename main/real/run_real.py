"""
Main FQL — Raspberry Pi 4 (Monitoring System v2)
=================================================
NH₃ Risk Monitoring System - NO AERATOR CONTROL

Phases:
  PHASE A -> Wait for Pico connection
  PHASE B -> FQL learns risk prediction from real data
  PHASE C -> FQL converges -> send risk model to Pico
  PHASE D -> DQN buffer sufficient -> ready for DQN training
  PHASE E -> Continuous risk monitoring

Progressive Learning:
  - Rule-Based: Simple NH₃ risk thresholds
  - FQL: Learns risk patterns from field data
  - DQN: Deep learning for accurate risk prediction

Manual run:
  python3 main/real/run_real.py

Install as service:
  sudo cp aquaculture.service /etc/systemd/system/
  sudo systemctl enable aquaculture
  sudo systemctl start aquaculture
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
# Fallback import if USB Serial is needed instead of Wi-Fi:
# from main.real.serial_bridge import SerialBridge, _setup_pico_monitor_log
from dqn.dqn_agent import DQNAgent

# Import Home Assistant Bridge
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "n3iwf"))
    from homeassistant_bridge import HomeAssistantBridge
    HA_AVAILABLE = True
except ImportError as e:
    print(f"[HA] Import failed: {e}")
    HA_AVAILABLE = False

# ── Path configuration ───────────────────────────────────────────────────── #
# Go up two levels from 'main/real' to the root directory
BASE_DIR        = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_REAL    = os.path.join(BASE_DIR, "results", "hasil_real")

QTABLE_FILE     = ""
BUFFER_FILE     = ""
DQN_MODEL_FILE  = ""

LOG_FILE        = os.path.join(RESULTS_REAL, "fql.log")
LOG_ERROR_FILE  = os.path.join(RESULTS_REAL, "fql_error.log")
STATE_JSON_FILE = os.path.join(RESULTS_REAL, "state.json")

# ── Constants ────────────────────────────────────────────────────────────── #
DQN_BUFFER_READY       = 10_000   # transitions before DQN training starts
DQN_BUFFER_MAX         = 50_000   # maximum buffer size (FIFO)
DQN_TRAIN_EPOCHS       = 300      # epochs for DQN training
DQN_RETRAIN_INTERVAL   = 2_000    # retrain DQN every N real steps after first training
FQL_MIN_REAL_STEPS     = 1_000    # minimum real steps in FQL phase before DQN can start
BUFFER_AUTOSAVE        = 500      # save buffer every N transitions
FQL_RETRY_INTERVAL     = 30       # seconds between Q-table send retries
QTABLE_UPDATE_INTERVAL = 500      # re-send improved Q-table every N real steps
LOG_INTERVAL           = 10       # detailed log every N real steps
SUMMARY_INTERVAL       = 100      # summary log every N real steps
RECONNECT_DELAY        = 2        # seconds between reconnect attempts
DISCONNECT_TIMEOUT     = 30       # detik tanpa data → anggap Pico putus

# MONITORING SYSTEM v2 - No aerator simulation needed
# System only monitors and predicts risk, does not control aerator


# ══════════════════════════════════════════════════════════════════════════ #
#  Logging setup
# ══════════════════════════════════════════════════════════════════════════ #

def setup_logging() -> logging.Logger:
    os.makedirs(RESULTS_REAL, exist_ok=True)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    logger = logging.getLogger("aquaculture")
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    eh = logging.FileHandler(LOG_ERROR_FILE)
    eh.setLevel(logging.WARNING)
    eh.setFormatter(fmt)
    logger.addHandler(eh)

    _setup_pico_monitor_log(RESULTS_REAL)
    logger.info(f"Pico monitor log: {os.path.join(RESULTS_REAL, 'pico_monitor.log')}")
    logger.info("  Run in second terminal: tail -f results/hasil_real/pico_monitor.log")

    return logger


# ══════════════════════════════════════════════════════════════════════════ #
#  DQN buffer helpers
# ══════════════════════════════════════════════════════════════════════════ #

def load_buffer(path: str) -> list:
    """Load DQN buffer from JSON file. Returns empty list on failure."""
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


def save_buffer(buffer: list, path: str) -> None:
    """Save DQN buffer to JSON file."""
    try:
        with open(path, "w") as f:
            json.dump(buffer, f)
    except OSError as e:
        logger.warning(f"Failed to save DQN buffer: {e}")


def append_transition(buffer: list, s, a, r, s_next) -> None:
    """Append one transition; drop oldest if buffer exceeds DQN_BUFFER_MAX."""
    buffer.append({
        "s":      s,
        "a":      a,
        "r":      round(r, 5),
        "s_next": s_next,
    })
    if len(buffer) > DQN_BUFFER_MAX:
        buffer.pop(0)


# ══════════════════════════════════════════════════════════════════════════ #
#  Risk Level Labels
# ══════════════════════════════════════════════════════════════════════════ #

RISK_LABELS = ["SAFE", "CAUTION", "WARNING", "CRITICAL"]

def nh3_fraction(pH: float, T: float) -> float:
    """Fraction of total ammonia in unionized (toxic) NH3 form."""
    pka = 0.09018 + 2729.92 / (T + 273.15)
    return 1.0 / (1.0 + 10 ** (pka - pH))

def rule_based_risk(pH: float, T: float) -> int:
    """
    Rule-Based risk prediction based on NH3%.
    Returns: 0=SAFE, 1=CAUTION, 2=WARNING, 3=CRITICAL
    """
    nh3_pct = nh3_fraction(pH, T) * 100.0
    
    if nh3_pct < 1.0:
        return RISK_SAFE
    elif nh3_pct < 5.0:
        return RISK_CAUTION
    elif nh3_pct < 10.0:
        return RISK_WARNING
    else:
        return RISK_CRITICAL

# ── Comparison CSV writer ────────────────────────────────────────────────── #

_csv_file   = None
_csv_writer = None

def _init_comparison_csv(session_dir: str) -> None:
    global _csv_file, _csv_writer
    
    # Tutup file lama jika ada
    if _csv_file is not None and not _csv_file.closed:
        _csv_file.close()

    os.makedirs(session_dir, exist_ok=True)
    csv_path = os.path.join(session_dir, "comparison.csv")
    
    write_header = not os.path.exists(csv_path)
    _csv_file   = open(csv_path, "a", newline="")
    _csv_writer = csv.writer(_csv_file)
    if write_header:
        _csv_writer.writerow([
            "timestamp", "real_step",
            "pH", "T_C", "NH3_pct",
            "mode",              # RB, FQL, or DQN
            "actual_risk",       # ground truth risk level
            "rb_risk",           # Rule-Based prediction
            "fql_risk",          # FQL prediction
            "dqn_risk",          # DQN prediction (if active)
            "rb_correct",        # 1 if RB correct, 0 if wrong
            "fql_correct",       # 1 if FQL correct, 0 if wrong
            "dqn_correct",       # 1 if DQN correct, 0 if wrong
            "fql_steps", "epsilon",
        ])
        _csv_file.flush()

# ── Home Assistant Comparison CSV writer ──────────────────────────────────── #

_ha_csv_file   = None
_ha_csv_writer = None

def _init_ha_comparison_csv(session_dir: str) -> None:
    global _ha_csv_file, _ha_csv_writer
    
    # Tutup file lama jika ada
    if _ha_csv_file is not None and not _ha_csv_file.closed:
        _ha_csv_file.close()

    os.makedirs(session_dir, exist_ok=True)
    csv_path = os.path.join(session_dir, "ha_comparison.csv")

    write_header = not os.path.exists(csv_path)
    _ha_csv_file   = open(csv_path, "a", newline="")
    _ha_csv_writer = csv.writer(_ha_csv_file)
    if write_header:
        _ha_csv_writer.writerow([
            "timestamp", "real_step",
            # Real sensor data (from Pico via N3IWF)
            "real_pH", "real_T_C",
            # IoT sensor data (from Home Assistant)
            "iot_pH", "iot_T_C",
            # Differences
            "pH_diff", "T_diff",
            # Latency comparison
            "real_latency_ms", "iot_latency_ms",
            # Data quality
            "iot_available",
        ])
        _ha_csv_file.flush()

def _log_ha_comparison(real_step: int, 
                       real_pH: float, real_T: float,
                       iot_pH: float | None, iot_T: float | None,
                       real_latency: float, iot_latency: float) -> None:
    if _ha_csv_writer is None:
        return
    
    iot_available = (iot_pH is not None and iot_T is not None)
    pH_diff = abs(real_pH - iot_pH) if iot_available else None
    T_diff = abs(real_T - iot_T) if iot_available else None
    
    _ha_csv_writer.writerow([
        time.strftime("%Y-%m-%d %H:%M:%S"), real_step,
        round(real_pH, 4), round(real_T, 2),
        round(iot_pH, 4) if iot_pH is not None else "N/A",
        round(iot_T, 2) if iot_T is not None else "N/A",
        round(pH_diff, 4) if pH_diff is not None else "N/A",
        round(T_diff, 2) if T_diff is not None else "N/A",
        round(real_latency, 2),
        round(iot_latency, 2),
        "YES" if iot_available else "NO",
    ])
    _ha_csv_file.flush()

def _log_comparison(real_step: int, pH: float, T: float,
                    mode: str, fql: FQLAgent, dqn: DQNAgent,
                    dqn_active: bool) -> None:
    if _csv_writer is None:
        return
    
    # Calculate actual risk (ground truth)
    actual_risk = calculate_actual_risk(pH, T)
    
    # Get predictions from each agent
    rb_risk = rule_based_risk(pH, T)
    fql_risk = fql.predict_risk(pH, T)
    dqn_risk = dqn.predict_risk(pH, T) if dqn_active and dqn.ready else -1
    
    # Check correctness
    rb_correct = 1 if rb_risk == actual_risk else 0
    fql_correct = 1 if fql_risk == actual_risk else 0
    dqn_correct = 1 if dqn_risk == actual_risk else 0 if dqn_active else -1
    
    nh3 = nh3_fraction(pH, T) * 100.0

    _csv_writer.writerow([
        time.strftime("%Y-%m-%d %H:%M:%S"), real_step,
        round(pH, 4), round(T, 2), round(nh3, 4),
        mode, actual_risk, rb_risk, fql_risk, dqn_risk,
        rb_correct, fql_correct, dqn_correct,
        fql.total_steps, round(fql.epsilon, 4),
    ])
    _csv_file.flush()


# ══════════════════════════════════════════════════════════════════════════ #
#  Graceful shutdown
# ══════════════════════════════════════════════════════════════════════════ #

_shutdown = False

def _handle_signal(sig, frame):
    global _shutdown
    _shutdown = True

signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ══════════════════════════════════════════════════════════════════════════ #
#  Main
# ══════════════════════════════════════════════════════════════════════════ #

logger = setup_logging()


def main():
    global _shutdown

    # Parse command line arguments for Home Assistant
    use_ha = "--with-ha" in sys.argv
    
    logger.info("=" * 65)
    logger.info("Aquaculture NH₃ Risk Monitoring System — Raspberry Pi 4")
    logger.info("  Mode: MONITORING ONLY (no aerator control)")
    logger.info("  Progressive Learning: Rule-Based → FQL → DQN")
    if use_ha and HA_AVAILABLE:
        logger.info(f"  Home Assistant: ENABLED (comparison mode)")
    logger.info("=" * 65)

    # ── Initialize main objects ──────────────────────────────────────────── #
    fql        = FQLAgent()
    
    # N3IWF Wi-Fi Bridge (TCP Server on Port 5000)
    bridge     = WiFiBridge(port=5000)
    
    # To fallback to USB Serial, comment the WiFiBridge above and uncomment below:
    # _setup_pico_monitor_log(RESULTS_REAL)
    # bridge = SerialBridge(baudrate=115200)

    buffer_dqn: list = []
    
    # ── Initialize Home Assistant Bridge (if enabled) ────────────────────── #
    ha_bridge = None
    if use_ha and HA_AVAILABLE:
        # EDIT INI SESUAI SETUP HOME ASSISTANT ANDA
        HA_URL = os.getenv("HA_URL", "http://192.168.1.100:8123")
        HA_TOKEN = os.getenv("HA_TOKEN", "your_long_lived_access_token_here")
        HA_PH_ENTITY = os.getenv("HA_PH_ENTITY", "sensor.aquaculture_ph")
        HA_TEMP_ENTITY = os.getenv("HA_TEMP_ENTITY", "sensor.aquaculture_temperature")
        
        ha_bridge = HomeAssistantBridge(
            url=HA_URL,
            token=HA_TOKEN,
            ph_entity=HA_PH_ENTITY,
            temp_entity=HA_TEMP_ENTITY
        )
        
        if ha_bridge.test_connection():
            logger.info(f"[HA] Connected to Home Assistant at {HA_URL}")
        else:
            logger.warning("[HA] Failed to connect to Home Assistant — comparison disabled")
            ha_bridge = None
    elif use_ha and not HA_AVAILABLE:
        logger.warning("[HA] Home Assistant requested but module not available")

    dqn_ready_logged      = False
    dqn_model_ready       = False
    dqn_active            = False
    dqn                   = DQNAgent()
    last_qtable_retry     = 0.0
    last_qtable_update    = 0
    last_dqn_retrain      = 0
    fql_mode_start        = None
    real_steps            = 0

    session = 0  # sesi koneksi ke-N

    # ══════════════════════════════════════════════════════════════════════ #
    #  OUTER LOOP — satu iterasi per sesi koneksi Pico WH
    # ══════════════════════════════════════════════════════════════════════ #
    while not _shutdown:
        session += 1

        # ── Reset semua state AI pada sesi ke-2 dan seterusnya ──────────── #
        if session > 1:
            logger.info("═" * 65)
            logger.info(f"PICO PUTUS — Reset seluruh state belajar (sesi #{session})")
            logger.info("Alasan: Pico WH mungkin dipindah ke lokasi/kolam berbeda.")
            logger.info("═" * 65)

            # Reset semua agent
            fql              = FQLAgent()
            dqn              = DQNAgent()
            buffer_dqn       = []
            real_steps       = 0
            dqn_ready_logged = False
            dqn_model_ready  = False
            dqn_active       = False
            last_qtable_retry  = 0.0
            last_qtable_update = 0
            last_dqn_retrain   = 0
            fql_mode_start     = None

        # ── PHASE A: Tunggu Pico WH konek ───────────────────────────────── #
        logger.info(f"PHASE A — Waiting for Pico WH connection... (sesi #{session})")
        while not _shutdown:
            if bridge.connect():
                logger.info("Pico connected!")
                break
            time.sleep(RECONNECT_DELAY)

        if _shutdown:
            break

        # Sesi terhubung, buat folder sesi baru
        global QTABLE_FILE, BUFFER_FILE, DQN_MODEL_FILE
        session_ts = time.strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(RESULTS_REAL, f"session_{session_ts}")
        os.makedirs(session_dir, exist_ok=True)
        
        # Set path file AI ke dalam folder sesi
        QTABLE_FILE    = os.path.join(session_dir, "qtable.json")
        BUFFER_FILE    = os.path.join(session_dir, "dqn_buffer.json")
        DQN_MODEL_FILE = os.path.join(session_dir, "dqn_model.pt")

        _init_comparison_csv(session_dir)
        logger.info(f"Folder sesi baru dibuat: {session_dir}")
        
        if ha_bridge is not None:
            _init_ha_comparison_csv(session_dir)

        # Waktu terakhir data diterima — untuk deteksi disconnect
        last_data_time = time.time()

        # ── Main loop — real data monitoring ────────────────────────────── #
        logger.info("PHASE B — FQL learning risk prediction from real Pico data...")

        while not _shutdown:
            # ── Real: receive data from Pico ─────────────────────────────── #
            data = bridge.read_data_line()
            if data is None:
                # Deteksi disconnect: jika > DISCONNECT_TIMEOUT detik tanpa data
                if time.time() - last_data_time > DISCONNECT_TIMEOUT:
                    logger.warning(
                        f"[DISCONNECT] Tidak ada data selama {DISCONNECT_TIMEOUT}s "
                        f"— Pico WH dianggap terputus. Kembali ke Phase A..."
                    )
                    bridge.disconnect()
                    break  # Keluar inner loop → outer loop → reset + Phase A
                time.sleep(0.1)
                continue

            last_data_time = time.time()  # Update waktu data terakhir

            pH = data["pH"]
            T  = data["T"]
            real_steps += 1
        
            # Get latency from bridge (time since last packet)
            real_latency = data.get("latency_ms", 0)

            # ── Get IoT data from Home Assistant (if enabled) ────────────────── #
            iot_pH, iot_T, iot_latency = None, None, 0
            if ha_bridge is not None:
                iot_pH, iot_T, iot_latency = ha_bridge.get_sensor_data()
                _log_ha_comparison(real_steps, pH, T, 
                                 iot_pH, iot_T, real_latency, iot_latency)
            
                if iot_pH is not None and iot_T is not None:
                    pH_diff = abs(pH - iot_pH)
                    T_diff = abs(T - iot_T)
                    if real_steps % LOG_INTERVAL == 0:
                        logger.info(
                            f"[HA] IoT: pH={iot_pH:.3f} T={iot_T:.1f}°C | "
                            f"Diff: ΔpH={pH_diff:.3f} ΔT={T_diff:.1f}°C | "
                            f"Latency: Real={real_latency:.1f}ms IoT={iot_latency:.1f}ms"
                        )

            # ── Calculate actual risk (ground truth) ─────────────────────────── #
            actual_risk = calculate_actual_risk(pH, T)
        
            # ── Get risk predictions from agents ─────────────────────────────── #
            rb_risk = rule_based_risk(pH, T)
            fql_risk = fql.predict_risk(pH, T)
            dqn_risk = dqn.predict_risk(pH, T) if dqn_active and dqn.ready else -1
        
            # ── Update FQL with actual risk ──────────────────────────────────── #
            fql.update(pH, T, fql_risk, actual_risk)
        
            # ── Track accuracy per phase ─────────────────────────────────────── #
            if dqn_active:
                mode = "DQN"
            elif fql.converged_sent:
                mode = "FQL"
            else:
                mode = "RB"
        
            _log_comparison(real_steps, pH, T, mode, fql, dqn, dqn_active)
        
            # ── Store transition for DQN training ────────────────────────────── #
            append_transition(buffer_dqn,
                              s      = [pH, T],
                              a      = actual_risk,  # Use actual risk as "action"
                              r      = 1.0 if fql_risk == actual_risk else -1.0,
                              s_next = [pH, T])  # Same state (no dynamics)

            # ── Auto-save buffer ─────────────────────────────────────────────── #
            if len(buffer_dqn) % BUFFER_AUTOSAVE == 0 and len(buffer_dqn) > 0:
                save_buffer(buffer_dqn, BUFFER_FILE)
                logger.debug(f"DQN buffer auto-saved: {len(buffer_dqn)} transitions")

            fql_real_elapsed = (real_steps - fql_mode_start) if fql_mode_start else 0

            # ── PHASE D: Train DQN as soon as buffer ready + FQL converged ──────── #
            if (len(buffer_dqn) >= DQN_BUFFER_READY
                    and fql.converged_sent
                    and not dqn_model_ready
                    and not dqn_ready_logged):
                dqn_ready_logged = True
                logger.info("=" * 65)
                logger.info(f"PHASE D — DQN training: {len(buffer_dqn)} transitions "
                            f"— Pico stays on FQL during training")
                logger.info("=" * 65)
                save_buffer(buffer_dqn, BUFFER_FILE)
                try:
                    from dqn.train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
                    if TORCH_AVAILABLE:
                        train_pytorch(buffer_dqn, DQN_TRAIN_EPOCHS, DQN_MODEL_FILE)
                    else:
                        train_numpy(buffer_dqn, DQN_TRAIN_EPOCHS, DQN_MODEL_FILE)
                    if dqn.load(DQN_MODEL_FILE):
                        dqn_model_ready = True
                        last_dqn_retrain = real_steps
                        logger.info("[DQN] Model trained and ready. "
                                    f"Waiting for {FQL_MIN_REAL_STEPS} FQL steps "
                                    f"({fql_real_elapsed}/{FQL_MIN_REAL_STEPS}).")
                    else:
                        logger.warning("DQN model failed to load — will retry later.")
                except Exception as e:
                    logger.error(f"DQN training failed: {e}")

            # ── PHASE E: Activate DQN only after FQL proves better than RB ──────── #
            elif (dqn_model_ready
                  and not dqn_active
                  and fql_real_elapsed >= FQL_MIN_REAL_STEPS):
                logger.info("=" * 65)
                logger.info(f"PHASE E — [DQN] activating after {fql_real_elapsed} FQL steps")
                logger.info("=" * 65)
                dqn_active = True
                if bridge.send_qtable(dqn.to_qtable_string()):
                    logger.info("[DQN] Q-table sent to Pico — DQN now predicts risk.")
                else:
                    logger.warning("[DQN] Failed to send Q-table — retrying next cycle.")
                    dqn_active = False

            # ── Periodic DQN retraining with growing buffer ───────────────────── #
            elif (dqn_active
                  and real_steps - last_dqn_retrain >= DQN_RETRAIN_INTERVAL):
                logger.info(f"[DQN] Retraining with updated buffer "
                            f"({len(buffer_dqn)} transitions, real_step={real_steps})...")
                save_buffer(buffer_dqn, BUFFER_FILE)
                try:
                    from dqn.train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
                    if TORCH_AVAILABLE:
                        train_pytorch(buffer_dqn, DQN_TRAIN_EPOCHS, DQN_MODEL_FILE)
                    else:
                        train_numpy(buffer_dqn, DQN_TRAIN_EPOCHS, DQN_MODEL_FILE)
                    if dqn.load(DQN_MODEL_FILE):
                        last_dqn_retrain = real_steps
                        logger.info("[DQN] Retrained. Sending updated policy to Pico...")
                        if bridge.send_qtable(dqn.to_qtable_string()):
                            logger.info("[DQN] Updated Q-table sent to Pico.")
                        else:
                            logger.warning("[DQN] Failed to send updated Q-table.")
                except Exception as e:
                    logger.error(f"[DQN] Retraining failed: {e}")

            # ── Convergence progress log (every SUMMARY_INTERVAL real steps) ─── #
            if real_steps % SUMMARY_INTERVAL == 0:
                prog = fql.convergence_progress()
                logger.info(
                    f"  Convergence progress: "
                    f"steps {prog['steps']*100:.0f}% | "
                    f"windows {prog['windows']*100:.0f}% | "
                    f"accuracy {prog['accuracy']*100:.0f}%"
                )
                logger.info(fql.format_policy_map())

            # ── PHASE C: FQL convergence check ───────────────────────────────── #
            if fql.check_convergence() and not fql.converged_sent:
                stats = fql.get_stats()
                logger.info("=" * 65)
                logger.info(f"=== FQL CONVERGED === "
                            f"Step: {stats['total_steps']} | "
                            f"Real: {real_steps} | "
                            f"Avg Accuracy: {stats['avg_accuracy_100']:.2%} ===")
                logger.info("=" * 65)
                logger.info(fql.format_policy_map())

                fql.save_qtable(QTABLE_FILE)
                logger.info(f"Q-table saved to {QTABLE_FILE}")

                qtable_str = fql.get_qtable_string()
                if bridge.send_qtable(qtable_str):
                    logger.info("Q-table successfully sent to Pico WH")
                    fql.converged_sent = True
                    fql_mode_start = real_steps
                    logger.info(f"[FQL] Phase started at real_step={real_steps}. "
                                f"DQN unlocks after {FQL_MIN_REAL_STEPS} more real steps.")
                else:
                    logger.warning(f"FAILED to send Q-table — retry in {FQL_RETRY_INTERVAL}s")
                    last_qtable_retry = time.time()

            elif (fql.converged and
                  not fql.converged_sent and
                  time.time() - last_qtable_retry > FQL_RETRY_INTERVAL):
                logger.info("Retrying Q-table send to Pico...")
                qtable_str = fql.get_qtable_string()
                if bridge.send_qtable(qtable_str):
                    logger.info("Q-table successfully sent to Pico WH (retry)")
                    fql.converged_sent = True
                    fql_mode_start = real_steps
                    logger.info(f"[FQL] Phase started at real_step={real_steps}. "
                                f"DQN unlocks after {FQL_MIN_REAL_STEPS} more real steps.")
                else:
                    last_qtable_retry = time.time()

            # ── Periodic Q-table re-send as FQL keeps improving ──────────────── #
            elif (fql.converged_sent and
                  real_steps - last_qtable_update >= QTABLE_UPDATE_INTERVAL):
                stats = fql.get_stats()
                logger.info(f"Sending updated Q-table to Pico "
                            f"(step={real_steps}, AvgR={stats['avg_reward_prev_100']:+.4f})...")
                logger.info(fql.format_policy_map())
                if bridge.send_qtable(fql.get_qtable_string()):
                    fql.save_qtable(QTABLE_FILE)
                    logger.info("Updated Q-table sent and saved.")
                last_qtable_update = real_steps

            # ── Periodic logging ──────────────────────────────────────────────── #
            if real_steps % LOG_INTERVAL == 0:
                stats = fql.get_stats()
                _mode_label = "DQN" if dqn_active else ("FQL" if fql.converged_sent else "RB")
                nh3_pct = nh3_fraction(pH, T) * 100.0
                logger.info(
                    f"[{_mode_label}][Step:{real_steps:5d}] "
                    f"pH:{pH:.3f} T:{T:.1f}°C NH₃:{nh3_pct:.2f}% | "
                    f"Risk: Actual={RISK_LABELS[actual_risk]} "
                    f"RB={RISK_LABELS[rb_risk]} "
                    f"FQL={RISK_LABELS[fql_risk]} "
                    f"{'DQN=' + RISK_LABELS[dqn_risk] if dqn_active else ''} | "
                    f"Acc:{stats['avg_accuracy_100']:.2%} "
                    f"Buffer:{len(buffer_dqn)}"
                )

            if real_steps % SUMMARY_INTERVAL == 0:
                stats = fql.get_stats()
                _mode_label = "DQN" if dqn_active else ("FQL" if fql.converged_sent else "RB")
                logger.info("-" * 65)
                logger.info(
                    f"[{_mode_label}] Real steps: {real_steps} | "
                    f"FQL steps: {stats['total_steps']} | "
                    f"Avg Accuracy: {stats['avg_accuracy_100']:.2%} | "
                    f"Converged: {stats['converged']} | "
                    f"DQN Buffer: {len(buffer_dqn)}"
                )
                if fql.converged_sent and not dqn_active:
                    remaining = max(0, FQL_MIN_REAL_STEPS - fql_real_elapsed)
                    logger.info(
                        f"[FQL] Steps in FQL phase: {fql_real_elapsed} / {FQL_MIN_REAL_STEPS} "
                        f"| DQN unlocks in {remaining} more real steps"
                    )
                logger.info("-" * 65)

            # ── Dashboard state dump ──────────────────────────────────────────── #
            stats = fql.get_stats()  # Always fetch latest for dashboard
            state_dump = {
                "pH": round(pH, 3),
                "T": round(T, 2),
                "nh3_pct": round(nh3_fraction(pH, T) * 100.0, 2),
                "actual_risk": RISK_LABELS[actual_risk],
                "rb_risk": RISK_LABELS[rb_risk],
                "fql_risk": RISK_LABELS[fql_risk],
                "dqn_risk": RISK_LABELS[dqn_risk] if dqn_active and dqn_risk >= 0 else "N/A",
                "phase": "DQN" if dqn_active else ("FQL" if fql.converged_sent else "Rule-Based"),
                "buffer_size": len(buffer_dqn),
                "accuracy": round(stats['avg_accuracy_100'], 4),
                "real_steps": real_steps,
                "fql_eps": round(fql.epsilon, 3)
            }
            with open(STATE_JSON_FILE, "w") as f:
                json.dump(state_dump, f)

    # ── Cleanup on shutdown ───────────────────────────────────────────────── #
    _cleanup(fql, buffer_dqn)
    bridge.disconnect()
    logger.info("Sistem berhenti total.")


def _cleanup(fql: FQLAgent, buffer_dqn: list) -> None:
    """Save all state before exiting."""
    logger.info("System stopping — saving data...")
    fql.save_qtable(QTABLE_FILE)
    save_buffer(buffer_dqn, BUFFER_FILE)
    logger.info(f"Q-table saved: {QTABLE_FILE}")
    logger.info(f"DQN buffer saved: {BUFFER_FILE} ({len(buffer_dqn)} transitions)")
    logger.info("System stopped — data saved.")


if __name__ == "__main__":
    main()
