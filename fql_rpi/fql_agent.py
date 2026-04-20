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
N_PH_SETS   = 5
N_T_SETS    = 5
N_RULES     = N_PH_SETS * N_T_SETS   # 25

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
        Compute membership degrees for pH across 5 fuzzy sets.
        Returns: {"VeryAcidic", "Acidic", "Normal", "Alkaline", "VeryAlkaline"}
        """
        t = FuzzyMembership.trapezoidal
        return {
            "VeryAcidic":   t(pH, 5.5, 5.5, 6.0, 6.5),
            "Acidic":       t(pH, 5.5, 6.0, 6.5, 7.0),
            "Normal":       t(pH, 6.5, 7.0, 7.5, 8.0),
            "Alkaline":     t(pH, 7.5, 8.0, 8.5, 9.0),
            "VeryAlkaline": t(pH, 8.5, 9.0, 9.5, 9.5),
        }

    @staticmethod
    def compute_T_memberships(T: float) -> dict:
        """
        Compute membership degrees for temperature across 5 fuzzy sets.
        Returns: {"VeryCold", "Cold", "Optimal", "Hot", "VeryHot"}
        """
        t = FuzzyMembership.trapezoidal
        return {
            "VeryCold": t(T, 17.5, 17.5, 18.0, 20.0),
            "Cold":     t(T, 18.0, 20.0, 22.0, 25.0),
            "Optimal":  t(T, 22.0, 25.0, 29.0, 32.0),
            "Hot":      t(T, 29.0, 32.0, 33.0, 34.5),
            "VeryHot":  t(T, 33.0, 34.0, 35.0, 35.0),
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

    # Rule order: (pH_set, T_set) — row-major 5×5
    # Must match C code: phi[i*5 + j] = mu_ph[i] * mu_t[j]
    _PH_SETS = ["VeryAcidic", "Acidic", "Normal", "Alkaline", "VeryAlkaline"]
    _T_SETS  = ["VeryCold", "Cold", "Optimal", "Hot", "VeryHot"]
    _RULE_ORDER = [
        (ph, t)
        for ph in _PH_SETS
        for t  in _T_SETS
    ]  # 25 rules total

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

    # Convergence thresholds — deliberately strict so FQL learns long enough
    CONV_MIN_STEPS   = 5_000   # minimum training steps
    CONV_MIN_WINDOWS = 8       # consecutive 100-step reward windows needed
    CONV_MAX_DELTA   = 0.005   # max |avg[-1] - avg[-2]| to declare stable
    CONV_MIN_REWARD  = 0.15    # final window avg reward must exceed this

    def check_convergence(self) -> bool:
        """
        Converged only when ALL four conditions hold (strict):
          1. total_steps >= CONV_MIN_STEPS      (enough experience)
          2. reward windows >= CONV_MIN_WINDOWS  (sustained stability)
          3. |avg[-1] - avg[-2]| < CONV_MAX_DELTA (reward stable)
          4. avg_reward[-1] >= CONV_MIN_REWARD   (actually performing well)
        """
        if self.converged:
            return True
        if self.total_steps < self.CONV_MIN_STEPS:
            return False
        hist = self._avg_reward_history
        if len(hist) < self.CONV_MIN_WINDOWS:
            return False
        if abs(hist[-1] - hist[-2]) >= self.CONV_MAX_DELTA:
            return False
        if hist[-1] < self.CONV_MIN_REWARD:
            return False
        self.converged = True
        return True

    def convergence_progress(self) -> dict:
        """Return how close each convergence condition is (0.0–1.0 = done)."""
        hist = self._avg_reward_history
        avg  = hist[-1] if hist else 0.0
        delta = abs(hist[-1] - hist[-2]) if len(hist) >= 2 else float("inf")
        return {
            "steps":      min(self.total_steps / self.CONV_MIN_STEPS,   1.0),
            "windows":    min(len(hist)         / self.CONV_MIN_WINDOWS, 1.0),
            "delta":      min(self.CONV_MAX_DELTA / max(delta, 1e-9),    1.0),
            "reward":     min(max(avg, 0) / self.CONV_MIN_REWARD,        1.0),
            "converged":  self.converged,
        }

    # ── Policy evaluation ────────────────────────────────────────────────── #

    # Representative center-point for each fuzzy set
    _PH_CENTERS = [5.75, 6.25, 7.25, 8.25, 9.25]  # VeryAcidic..VeryAlkaline
    _T_CENTERS  = [17.75, 21.0, 27.0, 32.5, 34.5]  # VeryCold..VeryHot

    def evaluate_policy(self) -> list[list[int]]:
        """
        Greedy policy for all 25 fuzzy regions (no epsilon).
        Returns 5x5 list: [row=pH][col=T] -> action index.
        Rows 0-4: VeryAcidic / Acidic / Normal / Alkaline / VeryAlkaline
        Cols 0-4: VeryCold / Cold / Optimal / Hot / VeryHot
        """
        policy = []
        for ph in self._PH_CENTERS:
            row = []
            for t in self._T_CENTERS:
                firing = self.compute_firing_strengths(ph, t)
                q_vals = self.compute_all_Q_FQL(firing)
                row.append(q_vals.index(max(q_vals)))
            policy.append(row)
        return policy

    def format_policy_map(self) -> str:
        """
        Render policy as a readable 5x5 table with domain-knowledge reference.

        Expected good policy for aquaculture:
          VeryAcidic  : HIGH everywhere (urgent pH correction)
          Acidic      : HIGH (raise pH via CO2 stripping)
          Normal+VCold: LOW  (good conditions, save energy, don't cool more)
          Normal+Cold : LOW
          Normal+Opt  : LOW  (ideal, minimal intervention)
          Normal+Hot  : MED  (some cooling needed)
          Normal+VHot : HIGH (cool urgently)
          Alkaline+VCold: LOW (cold keeps NH3 low despite high pH)
          Alkaline+Cold : LOW
          Alkaline+Opt  : MED (moderate NH3 risk)
          Alkaline+Hot  : HIGH (NH3 danger rising)
          Alkaline+VHot : HIGH
          VeryAlkaline  : HIGH everywhere (urgent, worst NH3 risk)
        """
        policy = self.evaluate_policy()
        names  = ["OFF ", "LOW ", "MED ", "HIGH"]
        ph_lbl = ["VeryAcid", "Acidic  ", "Normal  ", "Alkaline", "VeryAlk "]
        t_lbl  = ["VCold", "Cold ", "Opt  ", "Hot  ", "VHot "]

        header = "  " + "  ".join(t_lbl)
        sep    = "  " + "-" * 42
        lines  = [
            "=" * 56,
            "  FQL Policy Map — greedy action per fuzzy region (5x5)",
            f"              {header}",
            sep,
        ]
        for i, ph in enumerate(ph_lbl):
            acts = "  ".join(names[policy[i][j]] for j in range(5))
            lines.append(f"  {ph}:  {acts}")

        lines += [
            sep,
            "  Expected (domain knowledge):",
            "  VeryAcid:  HIGH  HIGH  HIGH  HIGH  HIGH",
            "  Acidic  :  HIGH  HIGH  HIGH  HIGH  HIGH",
            "  Normal  :  LOW   LOW   LOW   MED   HIGH",
            "  Alkaline:  LOW   LOW   MED   HIGH  HIGH",
            "  VeryAlk :  HIGH  HIGH  HIGH  HIGH  HIGH",
            "=" * 56,
        ]
        return "\n".join(lines)

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
