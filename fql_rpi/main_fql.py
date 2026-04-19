"""
Main FQL — Raspberry Pi 4
==========================
Auto-start via systemd. Phases:
  PHASE A -> Wait for Pico connection
  PHASE B -> FQL learns from Rule-Based data
  PHASE C -> FQL converges -> send Q-table to Pico
  PHASE D -> DQN buffer sufficient -> ready for DQN training
  PHASE E -> Continuous monitoring

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
from serial_bridge import SerialBridge

# ── Path configuration ───────────────────────────────────────────────────── #
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
QTABLE_FILE    = os.path.join(BASE_DIR, "qtable.json")
BUFFER_FILE    = os.path.join(BASE_DIR, "dqn_buffer.json")
LOG_DIR        = os.path.join(BASE_DIR, "logs")
LOG_FILE       = os.path.join(LOG_DIR, "fql.log")
LOG_ERROR_FILE = os.path.join(LOG_DIR, "fql_error.log")

# ── Constants ────────────────────────────────────────────────────────────── #
DQN_BUFFER_READY    = 10_000   # transitions before DQN is ready
DQN_BUFFER_MAX      = 50_000   # maximum buffer size (FIFO)
BUFFER_AUTOSAVE     = 500      # save buffer every N transitions
FQL_RETRY_INTERVAL  = 30       # seconds between Q-table send retries
LOG_INTERVAL        = 10       # detailed log every N steps
SUMMARY_INTERVAL    = 100      # summary log every N steps
RECONNECT_DELAY     = 2        # seconds between reconnect attempts


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

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler -> fql.log (INFO and above)
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # File handler -> fql_error.log (WARNING and above)
    eh = logging.FileHandler(LOG_ERROR_FILE)
    eh.setLevel(logging.WARNING)
    eh.setFormatter(fmt)
    logger.addHandler(eh)

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
    """
    Append one transition to the buffer.
    If buffer exceeds DQN_BUFFER_MAX, drop the oldest entry (FIFO).
    """
    buffer.append({
        "s":      s,
        "a":      a,
        "r":      round(r, 5),
        "s_next": s_next,
    })
    if len(buffer) > DQN_BUFFER_MAX:
        buffer.pop(0)


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

    logger.info("=" * 60)
    logger.info("Aquaculture FQL Controller — Raspberry Pi 4")
    logger.info("=" * 60)

    # ── Initialize main objects ──────────────────────────────────────────── #
    fql    = FQLAgent()
    bridge = SerialBridge()
    buffer_dqn: list = []

    # Log DQN buffer ready event only once
    dqn_ready_logged = False

    # Timestamp of last Q-table send retry
    last_qtable_retry = 0.0

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

    # ── PHASE A: Wait for Pico connection ───────────────────────────────── #
    logger.info("PHASE A — Waiting for Pico WH connection...")
    while not _shutdown:
        if bridge.connect():
            logger.info("Pico WH connected!")
            break
        logger.info(f"Pico not detected, retrying in {RECONNECT_DELAY}s...")
        time.sleep(2)

    if _shutdown:
        _cleanup(fql, buffer_dqn)
        return

    # ── Main loop ────────────────────────────────────────────────────────── #
    logger.info("PHASE B — FQL learning from Rule-Based data...")

    prev_data: dict | None = None

    while not _shutdown:
        # ── Receive data from Pico ───────────────────────────────────────── #
        data = bridge.read_data_line()
        if data is None:
            continue

        pH     = data["pH"]
        T      = data["T"]
        action = data["action"]

        # ── PHASE B: Update FQL from transition (s_prev -> s_now) ────────── #
        if prev_data is not None:
            pH_prev     = prev_data["pH"]
            T_prev      = prev_data["T"]
            action_prev = prev_data["action"]
            prev_action_before = prev_data.get("prev_action")

            # Compute reward based on previous state + action + current state
            reward = fql.compute_reward(
                pH_prev, T_prev, action_prev,
                pH, T,
                prev_action_before
            )

            # Update Q-table
            fql.update(pH_prev, T_prev, action_prev, reward, pH, T)

            # Store transition in DQN buffer
            append_transition(buffer_dqn,
                              s      = [pH_prev, T_prev],
                              a      = action_prev,
                              r      = reward,
                              s_next = [pH, T])

            # Auto-save buffer every BUFFER_AUTOSAVE transitions
            if len(buffer_dqn) % BUFFER_AUTOSAVE == 0 and len(buffer_dqn) > 0:
                save_buffer(buffer_dqn, BUFFER_FILE)
                logger.debug(f"DQN buffer auto-saved: {len(buffer_dqn)} transitions")

            # ── PHASE D: Check if DQN buffer is sufficient ───────────────── #
            if len(buffer_dqn) >= DQN_BUFFER_READY and not dqn_ready_logged:
                logger.info("=" * 60)
                logger.info(f"=== DQN BUFFER READY: {len(buffer_dqn)} transitions ===")
                logger.info("=== Ready for DQN training ===")
                logger.info("=" * 60)
                dqn_ready_logged = True

            # ── PHASE C: Check FQL convergence ───────────────────────────── #
            if fql.check_convergence() and not fql.converged_sent:
                stats = fql.get_stats()
                logger.info("=" * 60)
                logger.info(f"=== FQL CONVERGED === "
                            f"Step: {stats['total_steps']} | "
                            f"Avg Reward: {stats['avg_reward_prev_100']:.4f} ===")
                logger.info("=" * 60)

                fql.save_qtable(QTABLE_FILE)
                logger.info(f"Q-table saved to {QTABLE_FILE}")

                qtable_str = fql.get_qtable_string()
                if bridge.send_qtable(qtable_str):
                    logger.info("Q-table successfully sent to Pico WH")
                    fql.converged_sent = True
                else:
                    logger.warning(
                        f"FAILED to send Q-table — "
                        f"retry in {FQL_RETRY_INTERVAL}s"
                    )
                    last_qtable_retry = time.time()

            # Retry Q-table send if previous attempt failed
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

            # ── Periodic logging ──────────────────────────────────────────── #
            if fql.total_steps % LOG_INTERVAL == 0:
                stats = fql.get_stats()
                logger.info(
                    f"[{stats['total_steps']:5d}] "
                    f"pH:{pH:.3f} T:{T:.1f}C "
                    f"Action:{action} "
                    f"eps:{stats['epsilon']:.3f} "
                    f"AvgR:{stats['avg_reward_100']:+.3f} "
                    f"Buffer:{len(buffer_dqn)}"
                )

            if fql.total_steps % SUMMARY_INTERVAL == 0:
                stats = fql.get_stats()
                logger.info("-" * 60)
                logger.info(
                    f"Step {stats['total_steps']} | "
                    f"Avg Reward: {stats['avg_reward_prev_100']:+.4f} | "
                    f"Delta: {abs(stats['avg_reward_prev_100'] - stats['avg_reward_prev2']):.4f} | "
                    f"Converged: {stats['converged']} | "
                    f"DQN Buffer: {len(buffer_dqn)}"
                )
                logger.info("-" * 60)

        # Store current data as prev for the next iteration
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
