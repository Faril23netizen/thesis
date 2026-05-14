"""
FQL Pre-Training — Virtual Pond Simulator
==========================================
Pre-trains FQLAgent on simulated pond environment covering all 7 scenario
types (normal + 6 extreme conditions) until strict convergence is achieved.

Training loop:
  1. Run every scenario type sequentially (one full "loop")
  2. After each loop, check strict convergence criteria
  3. If not converged -> repeat from scenario 1
  4. If converged    -> save Q-table and exit

The saved Q-table is loaded by main_fql.py at startup, giving FQL a
strong initialization before fine-tuning on real Pico data.

Usage:
  python3 pretrain_fql.py
  python3 pretrain_fql.py --output qtable_pretrained.json
  python3 pretrain_fql.py --max-loops 200 --target-reward 0.3
"""

import argparse
import logging
import os
import sys
import time

from fql.fql_agent import FQLAgent
from main.env.pond_simulator import PondSimulator, ScenarioType, SimConfig

# ── Pre-training constants ───────────────────────────────────────────────── #

# Episode length (steps) per scenario per episode
STEPS_PER_EPISODE = 300

# How many episodes to run per scenario per loop pass
# Normal gets more episodes (most common real-world condition)
EPISODES_PER_SCENARIO = {
    ScenarioType.NORMAL:       80,
    ScenarioType.ACID_CRASH:   50,
    ScenarioType.ALKALINE:     50,
    ScenarioType.COLD_STRESS:  40,
    ScenarioType.HEAT_STRESS:  50,
    ScenarioType.HIGH_NH3:     60,   # extra emphasis — most dangerous
    ScenarioType.MULTI_STRESS: 70,   # systematic grid sweep
}

# Convergence criteria (stricter than online FQL)
CONV_MIN_STEPS   = 5_000   # must have at least this many training steps
CONV_MIN_WINDOWS = 10      # need >= N consecutive 100-step reward windows
CONV_MAX_DELTA   = 0.005   # |avg[-1] - avg[-2]| must be below this
CONV_MIN_REWARD  = 0.20    # final window average reward must exceed this

MAX_LOOPS = 150            # hard safety cap on loop count

# Epsilon at start of fine-tuning on real data (after pre-training)
FINETUNE_EPSILON = 0.15

# Log progress every N total steps
LOG_STEP_INTERVAL = 2_000

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT  = os.path.join(BASE_DIR, "results", "hasil_real", "qtable.json")

# Scenario order — normal first to build baseline policy,
# then extremes to stress-test, multi-stress last for coverage sweep
SCENARIO_ORDER = [
    ScenarioType.NORMAL,
    ScenarioType.ACID_CRASH,
    ScenarioType.ALKALINE,
    ScenarioType.COLD_STRESS,
    ScenarioType.HEAT_STRESS,
    ScenarioType.HIGH_NH3,
    ScenarioType.MULTI_STRESS,
]


# ── Logging ──────────────────────────────────────────────────────────────── #

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("pretrain")


# ── Helpers ──────────────────────────────────────────────────────────────── #

def check_strict_convergence(fql: FQLAgent,
                              min_reward: float = CONV_MIN_REWARD) -> bool:
    """
    Returns True only when ALL four conditions hold:
      1. total_steps >= CONV_MIN_STEPS
      2. len(avg_reward_history) >= CONV_MIN_WINDOWS
      3. |avg[-1] - avg[-2]| < CONV_MAX_DELTA
      4. avg_reward in last window >= min_reward
    """
    if fql.total_steps < CONV_MIN_STEPS:
        return False
    hist = fql._avg_reward_history
    if len(hist) < CONV_MIN_WINDOWS:
        return False
    if abs(hist[-1] - hist[-2]) >= CONV_MAX_DELTA:
        return False
    if hist[-1] < min_reward:
        return False
    return True


def run_episode(fql: FQLAgent, sim: PondSimulator,
                scenario: ScenarioType) -> tuple[int, float]:
    """
    Run one episode of STEPS_PER_EPISODE steps.
    Returns (steps_taken, sum_of_rewards).
    """
    ph, temp     = sim.reset(scenario)
    prev_action  = None
    total_reward = 0.0

    for _ in range(STEPS_PER_EPISODE):
        action             = fql.select_action(ph, temp)
        ph_next, temp_next = sim.step(action)
        reward             = fql.compute_reward(ph, temp, action,
                                                ph_next, temp_next,
                                                prev_action)
        fql.update(ph, temp, action, reward, ph_next, temp_next)

        total_reward += reward
        prev_action   = action
        ph, temp      = ph_next, temp_next

    return STEPS_PER_EPISODE, total_reward


def convergence_status(fql: FQLAgent) -> str:
    hist = fql._avg_reward_history
    avg   = hist[-1]            if hist           else float("nan")
    delta = abs(hist[-1] - hist[-2]) if len(hist) >= 2 else float("inf")
    return (f"steps={fql.total_steps:6d} | "
            f"eps={fql.epsilon:.4f} | "
            f"avg_reward={avg:+.4f} | "
            f"delta={delta:.5f} | "
            f"windows={len(hist)}")


def print_qtable(fql: FQLAgent):
    log.info(fql.format_policy_map())


# ══════════════════════════════════════════════════════════════════════════ #
#  Main pre-training loop
# ══════════════════════════════════════════════════════════════════════════ #

def pretrain(output_file: str = DEFAULT_OUT,
             max_loops:   int = MAX_LOOPS,
             target_reward: float = CONV_MIN_REWARD):

    log.info("=" * 65)
    log.info("FQL Pre-Training — Virtual Pond Simulator")
    log.info("=" * 65)
    log.info(f"Scenarios     : {[s.name for s in SCENARIO_ORDER]}")
    log.info(f"Episodes/loop : {sum(EPISODES_PER_SCENARIO.values())} total "
             f"({STEPS_PER_EPISODE} steps each)")
    log.info(f"Max loops     : {max_loops}")
    log.info(f"Convergence   : steps>={CONV_MIN_STEPS}, "
             f"windows>={CONV_MIN_WINDOWS}, "
             f"delta<{CONV_MAX_DELTA}, "
             f"avg_reward>={target_reward}")
    log.info("=" * 65)

    fql = FQLAgent(
        alpha     = 0.1,
        gamma     = 0.95,
        eps_start = 1.0,
        eps_min   = 0.05,
        eps_decay = 0.9995,
    )
    sim      = PondSimulator(SimConfig())
    t_start  = time.time()
    last_log = 0

    for loop_idx in range(1, max_loops + 1):
        log.info(f"\n{'─'*65}")
        log.info(f"Loop {loop_idx}/{max_loops}  |  {convergence_status(fql)}")
        log.info(f"{'─'*65}")

        for scenario in SCENARIO_ORDER:
            n_episodes   = EPISODES_PER_SCENARIO[scenario]
            scen_label   = PondSimulator.label(scenario)
            scen_reward  = 0.0
            scen_steps   = 0

            for _ in range(n_episodes):
                steps, ep_reward = run_episode(fql, sim, scenario)
                scen_reward     += ep_reward
                scen_steps      += steps

                # Periodic progress log
                if fql.total_steps - last_log >= LOG_STEP_INTERVAL:
                    log.info(f"  [{scen_label:<18}] {convergence_status(fql)}")
                    last_log = fql.total_steps

            avg_step_reward = scen_reward / scen_steps
            log.info(
                f"  [{scen_label:<18}] done — "
                f"{scen_steps:5d} steps | "
                f"avg_reward/step={avg_step_reward:+.4f}"
            )

        # ── Convergence check after full loop ────────────────────────────── #
        converged = check_strict_convergence(fql, min_reward=target_reward)
        if converged:
            hist  = fql._avg_reward_history
            delta = abs(hist[-1] - hist[-2]) if len(hist) >= 2 else float("inf")
            elapsed = time.time() - t_start
            log.info("\n" + "=" * 65)
            log.info(f"CONVERGED after loop {loop_idx}")
            log.info(f"  Total steps  : {fql.total_steps:,}")
            log.info(f"  Avg reward   : {hist[-1]:+.4f}")
            log.info(f"  Delta        : {delta:.6f}")
            log.info(f"  Epsilon      : {fql.epsilon:.4f}")
            log.info(f"  Reward windows: {len(hist)}")
            log.info(f"  Elapsed      : {elapsed:.1f}s")
            log.info("=" * 65)
            break
        else:
            hist  = fql._avg_reward_history
            avg_r = hist[-1] if hist else float("nan")
            delta = abs(hist[-1] - hist[-2]) if len(hist) >= 2 else float("inf")
            # Explain which condition(s) are not yet met
            reasons = []
            if fql.total_steps < CONV_MIN_STEPS:
                reasons.append(f"steps {fql.total_steps}<{CONV_MIN_STEPS}")
            if len(hist) < CONV_MIN_WINDOWS:
                reasons.append(f"windows {len(hist)}<{CONV_MIN_WINDOWS}")
            if delta >= CONV_MAX_DELTA:
                reasons.append(f"delta {delta:.5f}>={CONV_MAX_DELTA}")
            if hist and hist[-1] < target_reward:
                reasons.append(f"avg_reward {avg_r:.4f}<{target_reward}")
            log.info(f"  Not converged: {', '.join(reasons)} — looping again...")
    else:
        log.warning(f"Reached MAX_LOOPS={max_loops} without strict convergence.")
        log.warning("Saving best Q-table achieved.")

    # ── Prepare Q-table for fine-tuning ─────────────────────────────────── #
    # Reset converged=False so main_fql.py continues fine-tuning on real data.
    # Set epsilon to FINETUNE_EPSILON for mild exploration in real environment.
    fql.converged    = False
    fql.epsilon      = max(fql.eps_min, FINETUNE_EPSILON)
    fql.total_steps  = 0   # reset step counter for online phase

    fql.save_qtable(output_file)

    elapsed = time.time() - t_start
    log.info(f"\nQ-table saved to : {output_file}")
    log.info(f"Fine-tune epsilon: {fql.epsilon:.4f}")
    log.info(f"Total time       : {elapsed:.1f}s")
    log.info("\nFinal Q-table:")
    print_qtable(fql)
    log.info("\nRun main_fql.py to fine-tune on real Pico data.")


# ══════════════════════════════════════════════════════════════════════════ #
#  Entry point
# ══════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pre-train FQL agent on virtual pond simulator"
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUT,
        help=f"Output Q-table JSON path (default: {DEFAULT_OUT})"
    )
    parser.add_argument(
        "--max-loops", type=int, default=MAX_LOOPS,
        help=f"Maximum scenario loop count (default: {MAX_LOOPS})"
    )
    parser.add_argument(
        "--target-reward", type=float, default=CONV_MIN_REWARD,
        help=f"Minimum avg reward for convergence (default: {CONV_MIN_REWARD})"
    )
    args = parser.parse_args()
    pretrain(
        output_file   = args.output,
        max_loops     = args.max_loops,
        target_reward = args.target_reward,
    )
