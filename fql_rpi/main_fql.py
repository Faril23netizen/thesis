"""
Main FQL — Raspberry Pi 4
==========================
Auto-start via systemd. Phases:
  PHASE A -> Wait for Pico connection (virtual simulator runs during wait)
  PHASE B -> FQL learns from BOTH real Pico data AND virtual simulator
  PHASE C -> FQL converges -> send Q-table to Pico
  PHASE D -> DQN buffer sufficient -> ready for DQN training
  PHASE E -> Continuous monitoring (virtual sim keeps running)

Real + virtual learning run interleaved in the same loop:
  - Every real Pico transition  -> 1 FQL update
  - Every real step             -> VIRTUAL_STEPS_PER_REAL virtual updates
  - Virtual simulator cycles through all 7 scenario types automatically

Manual run:
  python3 main_fql.py

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

from fql_agent import FQLAgent, ACTION_OFF, ACTION_LOW, ACTION_MED, ACTION_HIGH
from serial_bridge import SerialBridge, _setup_pico_monitor_log
from pond_simulator import PondSimulator, ScenarioType, SimConfig
from aerator_sim import AeratorSim
from dqn_agent import DQNAgent

# ── Path configuration ───────────────────────────────────────────────────── #
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
QTABLE_FILE     = os.path.join(BASE_DIR, "qtable.json")
BUFFER_FILE     = os.path.join(BASE_DIR, "dqn_buffer.json")
DQN_MODEL_FILE  = os.path.join(BASE_DIR, "dqn_model.pt")
LOG_DIR         = os.path.join(BASE_DIR, "logs")
LOG_FILE        = os.path.join(LOG_DIR, "fql.log")
LOG_ERROR_FILE  = os.path.join(LOG_DIR, "fql_error.log")
COMPARISON_CSV  = os.path.join(LOG_DIR, "comparison.csv")

# ── Constants ────────────────────────────────────────────────────────────── #
DQN_BUFFER_READY       = 10_000   # transitions before DQN training starts
DQN_BUFFER_MAX         = 50_000   # maximum buffer size (FIFO)
DQN_TRAIN_EPOCHS       = 300      # epochs for DQN training
DQN_RETRAIN_INTERVAL   = 2_000    # retrain DQN every N real steps after first training
BUFFER_AUTOSAVE        = 500      # save buffer every N transitions
FQL_RETRY_INTERVAL     = 30       # seconds between Q-table send retries
QTABLE_UPDATE_INTERVAL = 500      # re-send improved Q-table every N real steps
LOG_INTERVAL           = 10       # detailed log every N real steps
SUMMARY_INTERVAL       = 100      # summary log every N real steps
RECONNECT_DELAY        = 2        # seconds between reconnect attempts

# Aerator simulation — set False when real aerator is connected (prevents double-counting)
USE_AERATOR_SIM        = False  # True only when physical aerator is connected

# Virtual simulator settings
VIRTUAL_STEPS_PER_REAL = 10       # virtual steps per real Pico step
VIRTUAL_EPISODE_LEN    = 300      # steps before switching to next scenario
VIRTUAL_PHASE_A_BATCH  = 50       # virtual steps per iteration while waiting

# Scenario rotation order — NORMAL gets 4/10 = 40% to teach LOW in safe conditions
_SCENARIO_ORDER = [
    ScenarioType.NORMAL,
    ScenarioType.NORMAL,
    ScenarioType.ACID_CRASH,
    ScenarioType.NORMAL,
    ScenarioType.ALKALINE,
    ScenarioType.COLD_STRESS,
    ScenarioType.NORMAL,
    ScenarioType.HEAT_STRESS,
    ScenarioType.HIGH_NH3,
    ScenarioType.MULTI_STRESS,
]


# ══════════════════════════════════════════════════════════════════════════ #
#  Logging setup
# ══════════════════════════════════════════════════════════════════════════ #

def setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

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

    _setup_pico_monitor_log(LOG_DIR)
    logger.info(f"Pico monitor log: {os.path.join(LOG_DIR, 'pico_monitor.log')}")
    logger.info("  Run in second terminal: tail -f logs/pico_monitor.log")

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
#  Virtual simulator state machine
# ══════════════════════════════════════════════════════════════════════════ #

class VirtualEnv:
    """
    Wraps PondSimulator with automatic scenario rotation.
    Keeps its own prev_action so FQL gets proper stability reward.
    """

    def __init__(self):
        self.sim          = PondSimulator(SimConfig())
        self._scen_idx    = 0
        self._steps_left  = 0
        self._prev_action = None
        self._ph:   float = 7.5
        self._temp: float = 28.0
        self._new_episode()

    def _new_episode(self):
        scenario       = _SCENARIO_ORDER[self._scen_idx % len(_SCENARIO_ORDER)]
        self._ph, self._temp = self.sim.reset(scenario)
        self._steps_left  = VIRTUAL_EPISODE_LEN
        self._prev_action = None
        self._scen_idx   += 1

    def step(self, fql: FQLAgent, buffer_dqn: list) -> None:
        """Run one virtual step: select action, step sim, update FQL + buffer."""
        if self._steps_left <= 0:
            self._new_episode()

        action                   = fql.select_action(self._ph, self._temp)
        ph_next, temp_next       = self.sim.step(action)
        reward                   = fql.compute_reward(
            self._ph, self._temp, action,
            ph_next, temp_next,
            self._prev_action
        )
        fql.update(self._ph, self._temp, action, reward, ph_next, temp_next)
        append_transition(buffer_dqn,
                          s      = [self._ph, self._temp],
                          a      = action,
                          r      = reward,
                          s_next = [ph_next, temp_next])

        self._prev_action = action
        self._ph, self._temp = ph_next, temp_next
        self._steps_left -= 1

    def current_scenario(self) -> str:
        idx = (self._scen_idx - 1) % len(_SCENARIO_ORDER)
        return PondSimulator.label(_SCENARIO_ORDER[idx])


# ══════════════════════════════════════════════════════════════════════════ #
#  Rule-Based shadow (mirrors safety_action() in Pico C code)
# ══════════════════════════════════════════════════════════════════════════ #

def rule_based_action(pH: float, T: float) -> int:
    """Exact mirror of safety_action() in main.c — for shadow comparison."""
    if pH < 6.0 or pH > 9.5 or T > 35.0: return ACTION_HIGH
    if pH < 6.5 or pH > 8.5 or T > 30.0: return ACTION_MED
    return ACTION_LOW

def nh3_fraction(pH: float, T: float) -> float:
    """Fraction of total ammonia in unionized (toxic) NH3 form."""
    pka = 0.09018 + 2729.92 / (T + 273.15)
    return 1.0 / (1.0 + 10 ** (pka - pH))

_ACTION_COST = {ACTION_OFF: 0.0, ACTION_LOW: 0.3, ACTION_MED: 0.6, ACTION_HIGH: 1.0}

# ── Comparison CSV writer ────────────────────────────────────────────────── #

_csv_file   = None
_csv_writer = None

def _init_comparison_csv() -> None:
    global _csv_file, _csv_writer
    os.makedirs(LOG_DIR, exist_ok=True)
    write_header = not os.path.exists(COMPARISON_CSV)
    _csv_file   = open(COMPARISON_CSV, "a", newline="")
    _csv_writer = csv.writer(_csv_file)
    if write_header:
        _csv_writer.writerow([
            "timestamp", "real_step",
            "pH", "T_C", "NH3_pct",
            "mode",        # RB or FQL
            "real_action", # action actually sent to relay (from Pico)
            "rb_action",   # what Rule-Based would have done
            "fql_action",  # what FQL would have done (greedy)
            "reward",
            "rb_reward",   # reward if RB had been used
            "energy_real", "energy_rb", "energy_fql",
            "fql_steps", "epsilon",
        ])
        _csv_file.flush()

def _log_comparison(real_step: int, pH: float, T: float,
                    mode: str, real_action: int,
                    fql: FQLAgent, reward: float,
                    pH_prev: float, T_prev: float) -> None:
    if _csv_writer is None:
        return
    rb_act  = rule_based_action(pH_prev, T_prev)
    fql_act = fql.select_action(pH_prev, T_prev) if fql.converged else real_action

    # Compute what reward would have been if RB acted instead
    rb_reward = fql.compute_reward(pH_prev, T_prev, rb_act, pH, T)

    nh3 = nh3_fraction(pH_prev, T_prev) * 100.0

    _csv_writer.writerow([
        time.strftime("%Y-%m-%d %H:%M:%S"), real_step,
        round(pH_prev, 4), round(T_prev, 2), round(nh3, 4),
        mode, real_action, rb_act, fql_act,
        round(reward, 5), round(rb_reward, 5),
        round(_ACTION_COST[real_action], 2),
        round(_ACTION_COST[rb_act], 2),
        round(_ACTION_COST[fql_act], 2),
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
_init_comparison_csv()


def main():
    global _shutdown

    logger.info("=" * 65)
    logger.info("Aquaculture FQL Controller — Raspberry Pi 4")
    logger.info(f"  Virtual sim   : {VIRTUAL_STEPS_PER_REAL} steps per real step")
    logger.info(f"  Episode length: {VIRTUAL_EPISODE_LEN} steps per scenario")
    logger.info("=" * 65)

    # ── Initialize main objects ──────────────────────────────────────────── #
    fql        = FQLAgent()
    bridge     = SerialBridge()
    venv       = VirtualEnv()
    buffer_dqn: list = []
    aerator_sim = AeratorSim() if USE_AERATOR_SIM else None
    if USE_AERATOR_SIM:
        logger.info("Aerator sim : ENABLED (typical 5-30W aquaculture pump)")
        logger.info("             Set USE_AERATOR_SIM=False when real aerator connected")

    dqn_ready_logged      = False
    dqn_trained           = False
    dqn                   = DQNAgent()
    last_qtable_retry     = 0.0
    last_qtable_update    = 0      # real_steps count of last Q-table update
    last_dqn_retrain      = 0      # real_steps count of last DQN retraining
    real_steps            = 0

    # ── Load Q-table (if previous session exists) ───────────────────────── #
    if os.path.exists(QTABLE_FILE):
        if fql.load_qtable(QTABLE_FILE):
            logger.info(f"Q-table loaded from {QTABLE_FILE} "
                        f"(step={fql.total_steps}, eps={fql.epsilon:.3f})")
        else:
            logger.warning("Q-table file corrupted, starting fresh.")

    if os.path.exists(BUFFER_FILE):
        buffer_dqn = load_buffer(BUFFER_FILE)
        if buffer_dqn:
            logger.info(f"DQN buffer loaded: {len(buffer_dqn)} transitions")

    # ── PHASE A: Wait for Pico (virtual sim runs here too) ──────────────── #
    logger.info("PHASE A — Waiting for Pico WH connection "
                "(virtual sim running in background)...")
    while not _shutdown:
        if bridge.connect():
            logger.info("Pico WH connected!")
            break

        # Keep learning from virtual environment while waiting for Pico
        for _ in range(VIRTUAL_PHASE_A_BATCH):
            venv.step(fql, buffer_dqn)

        if fql.total_steps % 1000 == 0 and fql.total_steps > 0:
            stats = fql.get_stats()
            logger.info(
                f"[Phase A] virtual steps={fql.total_steps} | "
                f"scenario={venv.current_scenario()} | "
                f"eps={stats['epsilon']:.3f} | "
                f"AvgR={stats['avg_reward_100']:+.3f} | "
                f"Buffer={len(buffer_dqn)}"
            )

        logger.info(f"Pico not detected, retrying in {RECONNECT_DELAY}s...")
        time.sleep(RECONNECT_DELAY)

    if _shutdown:
        _cleanup(fql, buffer_dqn)
        return

    # ── Main loop — real + virtual interleaved ───────────────────────────── #
    logger.info("PHASE B — FQL learning from real Pico data + virtual sim...")

    prev_data: dict | None = None

    while not _shutdown:
        # ── Real: receive data from Pico ─────────────────────────────────── #
        data = bridge.read_data_line()
        if data is None:
            # Even when no real data, run a virtual step to keep learning
            venv.step(fql, buffer_dqn)
            continue

        pH_real = data["pH"]
        T_real  = data["T"]
        action  = data["action"]
        real_steps += 1

        # Apply aerator sim using the action that was running last step
        action_for_sim = prev_data["action"] if prev_data else ACTION_LOW
        if aerator_sim is not None:
            pH, T = aerator_sim.update(pH_real, T_real, action_for_sim)
        else:
            pH, T = pH_real, T_real

        # ── Real: update FQL from real transition ─────────────────────────── #
        if prev_data is not None:
            pH_prev     = prev_data["pH"]
            T_prev      = prev_data["T"]
            action_prev = prev_data["action"]
            prev_action_before = prev_data.get("prev_action")

            reward = fql.compute_reward(
                pH_prev, T_prev, action_prev,
                pH, T,
                prev_action_before
            )
            fql.update(pH_prev, T_prev, action_prev, reward, pH, T)

            # Log comparison: real action vs RB shadow vs FQL greedy
            if dqn_trained:
                mode = "DQN"
            elif fql.converged_sent:
                mode = "FQL"
            else:
                mode = "RB"
            _log_comparison(real_steps, pH, T, mode, action_prev,
                            fql, reward, pH_prev, T_prev)

            append_transition(buffer_dqn,
                              s      = [pH_prev, T_prev],
                              a      = action_prev,
                              r      = reward,
                              s_next = [pH, T])

        # ── Virtual: run interleaved simulation steps ─────────────────────── #
        for _ in range(VIRTUAL_STEPS_PER_REAL):
            venv.step(fql, buffer_dqn)

        # ── Auto-save buffer ─────────────────────────────────────────────── #
        if len(buffer_dqn) % BUFFER_AUTOSAVE == 0 and len(buffer_dqn) > 0:
            save_buffer(buffer_dqn, BUFFER_FILE)
            logger.debug(f"DQN buffer auto-saved: {len(buffer_dqn)} transitions")

        # ── PHASE D: DQN training (once buffer is ready + FQL converged) ───── #
        if (len(buffer_dqn) >= DQN_BUFFER_READY
                and fql.converged_sent
                and not dqn_trained
                and not dqn_ready_logged):
            dqn_ready_logged = True
            logger.info("=" * 65)
            logger.info(f"PHASE D — DQN training: {len(buffer_dqn)} transitions "
                        f"(real + virtual)")
            logger.info("=" * 65)
            save_buffer(buffer_dqn, BUFFER_FILE)
            try:
                from train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
                if TORCH_AVAILABLE:
                    train_pytorch(buffer_dqn, DQN_TRAIN_EPOCHS, DQN_MODEL_FILE)
                else:
                    train_numpy(buffer_dqn, DQN_TRAIN_EPOCHS, DQN_MODEL_FILE)
                if dqn.load(DQN_MODEL_FILE):
                    dqn_trained = True
                    last_dqn_retrain = real_steps
                    logger.info("=" * 65)
                    logger.info("PHASE E — [DQN] active. Sending policy to Pico...")
                    logger.info("=" * 65)
                    if bridge.send_qtable(dqn.to_qtable_string()):
                        logger.info("[DQN] Q-table sent to Pico — DQN now controls.")
                    else:
                        logger.warning("[DQN] Failed to send Q-table — Pico stays on FQL.")
                else:
                    logger.warning("DQN model failed to load — staying on FQL.")
            except Exception as e:
                logger.error(f"DQN training failed: {e} — staying on FQL.")

        # ── PHASE E: Periodic DQN retraining with growing buffer ─────────── #
        elif (dqn_trained
              and real_steps - last_dqn_retrain >= DQN_RETRAIN_INTERVAL):
            logger.info(f"[DQN] Retraining with updated buffer "
                        f"({len(buffer_dqn)} transitions, "
                        f"real_step={real_steps})...")
            save_buffer(buffer_dqn, BUFFER_FILE)
            try:
                from train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
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
                f"stability {prog['delta']*100:.0f}% | "
                f"reward {prog['reward']*100:.0f}%"
            )
            logger.info(fql.format_policy_map())

        # ── PHASE C: FQL convergence check ───────────────────────────────── #
        if fql.check_convergence() and not fql.converged_sent:
            stats = fql.get_stats()
            logger.info("=" * 65)
            logger.info(f"=== FQL CONVERGED === "
                        f"Step: {stats['total_steps']} | "
                        f"Real: {real_steps} | "
                        f"Avg Reward: {stats['avg_reward_prev_100']:.4f} ===")
            logger.info("=" * 65)
            logger.info(fql.format_policy_map())

            fql.save_qtable(QTABLE_FILE)
            logger.info(f"Q-table saved to {QTABLE_FILE}")

            qtable_str = fql.get_qtable_string()
            if bridge.send_qtable(qtable_str):
                logger.info("Q-table successfully sent to Pico WH")
                fql.converged_sent = True
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
            _mode_label = "DQN" if dqn_trained else ("FQL" if fql.converged_sent else "RB")
            logger.info(
                f"[{_mode_label}][R:{real_steps:5d} V:{fql.total_steps:6d}] "
                f"pH:{pH:.3f} T:{T:.1f}C "
                f"Action:{action} "
                f"eps:{stats['epsilon']:.3f} "
                f"AvgR:{stats['avg_reward_100']:+.3f} "
                f"Scenario:{venv.current_scenario()} "
                f"Buffer:{len(buffer_dqn)}"
            )

        if real_steps % SUMMARY_INTERVAL == 0:
            stats = fql.get_stats()
            _mode_label = "DQN" if dqn_trained else ("FQL" if fql.converged_sent else "RB")
            logger.info("-" * 65)
            logger.info(
                f"[{_mode_label}] Real steps: {real_steps} | "
                f"Total (real+virtual): {stats['total_steps']} | "
                f"Avg Reward: {stats['avg_reward_prev_100']:+.4f} | "
                f"Delta: {abs(stats['avg_reward_prev_100'] - stats['avg_reward_prev2']):.4f} | "
                f"Converged: {stats['converged']} | "
                f"DQN Buffer: {len(buffer_dqn)}"
            )
            logger.info("-" * 65)

        # Store current data for next iteration
        prev_data = {
            "pH":          pH,
            "T":           T,
            "action":      action,
            "prev_action": prev_data["action"] if prev_data else None,
        }

    # ── Cleanup on shutdown ───────────────────────────────────────────────── #
    _cleanup(fql, buffer_dqn)
    bridge.disconnect()


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
