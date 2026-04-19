"""
FQL Agent — Fuzzy Q-Learning for RPi 4
========================================
Thesis : Edge-Intelligent Aquaculture Aerator Control
         Using Progressive Hybrid FQL-DQN with N3IWF LES
Student: Faril Pirwanhadi (M14128104)

Update rule reference: Er & Deng, IEEE SMC 2004 — Dynamic FQL
"""

import json
import math
import random

# ── Action constants ─────────────────────────────────────────────────────── #
ACTION_OFF  = 0
ACTION_LOW  = 1
ACTION_MED  = 2
ACTION_HIGH = 3
N_ACTIONS   = 4
N_RULES     = 9

# Energy cost per action for reward (normalized 0–1)
ENERGY_COST = {
    ACTION_OFF:  0.0,
    ACTION_LOW:  0.3,
    ACTION_MED:  0.6,
    ACTION_HIGH: 1.0,
}


# ═══════════════════════════════════════════════════════════════════════════ #
#  Fuzzy Membership Functions
# ═══════════════════════════════════════════════════════════════════════════ #

class FuzzyMembership:
    """Trapezoidal fuzzy membership functions for pH and temperature."""

    @staticmethod
    def trapezoidal(x: float, a: float, b: float, c: float, d: float) -> float:
        """
        Trapezoidal membership function.
          0           if x <= a or x >= d
          (x-a)/(b-a) if a < x < b
          1.0         if b <= x <= c
          (d-x)/(d-c) if c < x < d
        """
        if x <= a or x >= d:
            return 0.0
        if b <= x <= c:
            return 1.0
        if x < b:
            return (x - a) / (b - a)
        return (d - x) / (d - c)

    @staticmethod
    def compute_pH_memberships(pH: float) -> dict:
        """
        Compute membership degrees for pH across 3 fuzzy sets.
        Returns: {"Acidic": float, "Normal": float, "Alkaline": float}
        """
        t = FuzzyMembership.trapezoidal
        return {
            "Acidic":   t(pH, 5.5, 5.5, 6.5, 7.0),
            "Normal":   t(pH, 6.5, 7.0, 7.5, 8.0),
            "Alkaline": t(pH, 7.5, 8.0, 9.5, 9.5),
        }

    @staticmethod
    def compute_T_memberships(T: float) -> dict:
        """
        Compute membership degrees for temperature across 3 fuzzy sets.
        Returns: {"Cold": float, "Optimal": float, "Hot": float}
        """
        t = FuzzyMembership.trapezoidal
        return {
            "Cold":    t(T, 17.5, 17.5, 20.0, 25.0),
            "Optimal": t(T, 22.0, 25.0, 30.0, 33.0),
            "Hot":     t(T, 30.0, 33.0, 35.0, 35.0),
        }


# ═══════════════════════════════════════════════════════════════════════════ #
#  FQL Agent
# ═══════════════════════════════════════════════════════════════════════════ #

class FQLAgent:
    """
    Fuzzy Q-Learning agent.

    9 rules × 4 actions = 36 Q-values.
    Learns online from Rule-Based data sent by the Pico.
    """

    # Rule order: (pH_set, T_set) — row-major 3×3
    _RULE_ORDER = [
        ("Acidic",   "Cold"),     # Rule 0
        ("Acidic",   "Optimal"),  # Rule 1
        ("Acidic",   "Hot"),      # Rule 2
        ("Normal",   "Cold"),     # Rule 3
        ("Normal",   "Optimal"),  # Rule 4
        ("Normal",   "Hot"),      # Rule 5
        ("Alkaline", "Cold"),     # Rule 6
        ("Alkaline", "Optimal"),  # Rule 7
        ("Alkaline", "Hot"),      # Rule 8
    ]

    def __init__(self,
                 alpha: float = 0.1,
                 gamma: float = 0.95,
                 eps_start: float = 1.0,
                 eps_min:   float = 0.05,
                 eps_decay: float = 0.9995):
        self.alpha     = alpha
        self.gamma     = gamma
        self.epsilon   = eps_start
        self.eps_min   = eps_min
        self.eps_decay = eps_decay

        # Q-table: 9×4, initialized to 0.0
        self.qtable = [[0.0] * N_ACTIONS for _ in range(N_RULES)]

        self.total_steps      = 0
        self.converged        = False
        self.converged_sent   = False   # flag — Q-table has been sent to Pico

        # Reward history for convergence detection
        self._reward_window:    list[float] = []   # buffer of last 100 steps
        self._avg_reward_history: list[float] = [] # average per 100-step window

        self._prev_action: int | None = None

    # ── Firing strength ─────────────────────────────────────────────────── #

    def compute_firing_strengths(self, pH: float, T: float) -> list:
        """
        Compute firing strength phi_r for all 9 rules.
        phi_r = mu_pH(pH) × mu_T(T)
        Returns: list of length 9.
        """
        mu_ph = FuzzyMembership.compute_pH_memberships(pH)
        mu_t  = FuzzyMembership.compute_T_memberships(T)
        return [
            mu_ph[ph_set] * mu_t[t_set]
            for ph_set, t_set in self._RULE_ORDER
        ]

    # ── Q-value FQL ─────────────────────────────────────────────────────── #

    def compute_Q_FQL(self, firing_strengths: list, action: int) -> float:
        """
        Q_FQL(s, a) = sum_r [phi_r(s) × Q_r(a)]
        """
        return sum(
            firing_strengths[r] * self.qtable[r][action]
            for r in range(N_RULES)
        )

    def compute_all_Q_FQL(self, firing_strengths: list) -> list:
        """
        Compute Q_FQL for all 4 actions.
        Returns: list of length 4.
        """
        return [
            self.compute_Q_FQL(firing_strengths, a)
            for a in range(N_ACTIONS)
        ]

    # ── Action selection ─────────────────────────────────────────────────── #

    def select_action(self, pH: float, T: float) -> int:
        """
        Epsilon-greedy action selection.
        During Rule-Based learning phase, output is not sent to Pico —
        used only for internal FQL update.
        """
        if random.random() < self.epsilon:
            return random.randint(0, N_ACTIONS - 1)
        firing = self.compute_firing_strengths(pH, T)
        q_vals = self.compute_all_Q_FQL(firing)
        return q_vals.index(max(q_vals))

    # ── Reward function ──────────────────────────────────────────────────── #

    def compute_reward(self, pH: float, T: float, action: int,
                       pH_next: float, T_next: float,
                       prev_action: int | None = None) -> float:
        """
        r = 1.0×R_safe + 0.3×R_energy + 0.5×R_NH3 + 0.1×R_stability

        R_safe    : +1.0 if pH in [6.5, 8.5], -5.0 otherwise
        R_energy  : action power cost (0 to -1.0)
        R_NH3     : -f(NH3) based on next pH and temperature
        R_stability: -1.0 if action changed, 0.0 if same
        """
        # R_safe
        r_safe = 1.0 if 6.5 <= pH <= 8.5 else -5.0

        # R_energy
        r_energy = -ENERGY_COST[action]

        # R_NH3 — computed from next state (s')
        pka   = 0.09018 + 2729.92 / (T_next + 273.15)
        f_nh3 = 1.0 / (1.0 + 10 ** (pka - pH_next))
        r_nh3 = -f_nh3

        # R_stability
        r_stab = -1.0 if (prev_action is not None and action != prev_action) else 0.0

        return 1.0 * r_safe + 0.3 * r_energy + 0.5 * r_nh3 + 0.1 * r_stab

    # ── Q-table update ───────────────────────────────────────────────────── #

    def update(self, pH: float, T: float, action: int,
               reward: float, pH_next: float, T_next: float) -> float:
        """
        Update Q-table using TD error (Er & Deng, 2004).

        Q_r(a) += alpha × phi_r(s) × TD_error
        TD_error = r + gamma × max_a Q_FQL(s') − Q_FQL(s, a)

        Returns: TD_error
        """
        firing      = self.compute_firing_strengths(pH, T)
        q_now       = self.compute_Q_FQL(firing, action)

        firing_next = self.compute_firing_strengths(pH_next, T_next)
        q_next_max  = max(self.compute_all_Q_FQL(firing_next))

        td_error = reward + self.gamma * q_next_max - q_now

        # Update all active rules (phi_r > 0)
        for r in range(N_RULES):
            if firing[r] > 0.0:
                self.qtable[r][action] += self.alpha * firing[r] * td_error

        # Epsilon decay
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)

        # Record reward for convergence monitoring
        self._reward_window.append(reward)
        if len(self._reward_window) >= 100:
            avg = sum(self._reward_window) / len(self._reward_window)
            self._avg_reward_history.append(avg)
            self._reward_window.clear()

        self.total_steps  += 1
        self._prev_action  = action
        return td_error

    # ── Convergence ──────────────────────────────────────────────────────── #

    def check_convergence(self) -> bool:
        """
        Converged if ALL conditions are met:
          1. total_steps >= 500
          2. at least 2 reward window averages (>= 200 steps)
          3. |avg[-1] - avg[-2]| < 0.01
        """
        if self.converged:
            return True
        if self.total_steps < 500:
            return False
        if len(self._avg_reward_history) < 2:
            return False
        delta = abs(self._avg_reward_history[-1] - self._avg_reward_history[-2])
        if delta < 0.01:
            self.converged = True
        return self.converged

    # ── Serialization ────────────────────────────────────────────────────── #

    def save_qtable(self, filename: str) -> None:
        """Save Q-table and agent state to JSON file."""
        data = {
            "qtable":      self.qtable,
            "epsilon":     self.epsilon,
            "total_steps": self.total_steps,
            "converged":   self.converged,
        }
        try:
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            print(f"[fql] Failed to save qtable: {e}")

    def load_qtable(self, filename: str) -> bool:
        """
        Load Q-table from JSON file.
        Returns True on success, False if file is missing or corrupted.
        """
        try:
            with open(filename) as f:
                data = json.load(f)
            self.qtable      = data["qtable"]
            self.epsilon     = data.get("epsilon",     self.eps_min)
            self.total_steps = data.get("total_steps", 0)
            self.converged   = data.get("converged",   False)
            return True
        except (OSError, KeyError, json.JSONDecodeError):
            return False

    def get_qtable_string(self) -> str:
        """
        Serialize Q-table to string format for transmission to Pico.
        Format: "QTABLE:[[q00,q01,q02,q03],...,[q80,q81,q82,q83]]\\n"
        """
        rows = []
        for r in range(N_RULES):
            vals = ",".join(f"{self.qtable[r][a]:.4f}" for a in range(N_ACTIONS))
            rows.append(f"[{vals}]")
        return "QTABLE:[" + ",".join(rows) + "]\n"

    # ── Statistics ───────────────────────────────────────────────────────── #

    def get_stats(self) -> dict:
        """Return agent statistics dictionary for logging."""
        avg_now  = (sum(self._reward_window) / len(self._reward_window)
                    if self._reward_window else 0.0)
        avg_prev = (self._avg_reward_history[-1]
                    if self._avg_reward_history else 0.0)
        avg_prev2 = (self._avg_reward_history[-2]
                     if len(self._avg_reward_history) >= 2 else 0.0)
        return {
            "total_steps":        self.total_steps,
            "epsilon":            round(self.epsilon, 4),
            "avg_reward_100":     round(avg_now,  4),
            "avg_reward_prev_100":round(avg_prev, 4),
            "avg_reward_prev2":   round(avg_prev2, 4),
            "converged":          self.converged,
            "converged_sent":     self.converged_sent,
            "n_windows":          len(self._avg_reward_history),
        }
