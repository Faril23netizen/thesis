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

import json
import logging
import os
import signal
import sys
import time

from fql_agent import FQLAgent
from serial_bridge import SerialBridge, _setup_pico_monitor_log
from pond_simulator import PondSimulator, ScenarioType, SimConfig

# ── Path configuration ───────────────────────────────────────────────────── #
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
QTABLE_FILE    = os.path.join(BASE_DIR, "qtable.json")
BUFFER_FILE    = os.path.join(BASE_DIR, "dqn_buffer.json")
LOG_DIR        = os.path.join(BASE_DIR, "logs")
LOG_FILE       = os.path.join(LOG_DIR, "fql.log")
LOG_ERROR_FILE = os.path.join(LOG_DIR, "fql_error.log")

# ── Constants ────────────────────────────────────────────────────────────── #
DQN_BUFFER_READY       = 10_000   # transitions before DQN is ready
DQN_BUFFER_MAX         = 50_000   # maximum buffer size (FIFO)
BUFFER_AUTOSAVE        = 500      # save buffer every N transitions
FQL_RETRY_INTERVAL     = 30       # seconds between Q-table send retries
LOG_INTERVAL           = 10       # detailed log every N real steps
SUMMARY_INTERVAL       = 100      # summary log every N real steps
RECONNECT_DELAY        = 2        # seconds between reconnect attempts

# Virtual simulator settings
VIRTUAL_STEPS_PER_REAL = 10       # virtual steps per real Pico step
VIRTUAL_EPISODE_LEN    = 300      # steps before switching to next scenario
VIRTUAL_PHASE_A_BATCH  = 50       # virtual steps per iteration while waiting

# Scenario rotation order
_SCENARIO_ORDER = [
    ScenarioType.NORMAL,
    ScenarioType.ACID_CRASH,
    ScenarioType.ALKALINE,
    ScenarioType.COLD_STRESS,
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

    dqn_ready_logged  = False
    last_qtable_retry = 0.0
    real_steps        = 0

    # ── Load previous state if available ────────────────────────────────── #
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

        pH     = data["pH"]
        T      = data["T"]
        action = data["action"]
        real_steps += 1

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

        # ── PHASE D: DQN buffer ready ─────────────────────────────────────── #
        if len(buffer_dqn) >= DQN_BUFFER_READY and not dqn_ready_logged:
            logger.info("=" * 65)
            logger.info(f"=== DQN BUFFER READY: {len(buffer_dqn)} transitions ===")
            logger.info("=== Ready for DQN training ===")
            logger.info("=" * 65)
            dqn_ready_logged = True

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

        # ── Periodic logging ──────────────────────────────────────────────── #
        if real_steps % LOG_INTERVAL == 0:
            stats = fql.get_stats()
            logger.info(
                f"[R:{real_steps:5d} V:{fql.total_steps:6d}] "
                f"pH:{pH:.3f} T:{T:.1f}C "
                f"Action:{action} "
                f"eps:{stats['epsilon']:.3f} "
                f"AvgR:{stats['avg_reward_100']:+.3f} "
                f"Scenario:{venv.current_scenario()} "
                f"Buffer:{len(buffer_dqn)}"
            )

        if real_steps % SUMMARY_INTERVAL == 0:
            stats = fql.get_stats()
            logger.info("-" * 65)
            logger.info(
                f"Real steps: {real_steps} | "
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
