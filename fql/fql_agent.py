"""
FQL Agent — Fuzzy Q-Learning for Risk Classification
=====================================================
Thesis : Edge-Intelligent Aquaculture Monitoring System
         Using Progressive Hybrid FQL-DQN with N3IWF LES
Student: Faril Pirwanhadi (M14128104)

MONITORING SYSTEM v2:
- Predicts NH₃ risk level (Safe/Caution/Warning/Critical)
- No aerator control, pure monitoring
- Reward based on prediction accuracy
"""

import json
import math
import random

# ── Risk Level constants ─────────────────────────────────────────────────── #
RISK_SAFE     = 0
RISK_CAUTION  = 1
RISK_WARNING  = 2
RISK_CRITICAL = 3
N_RISK_LEVELS = 4
N_PH_SETS     = 5
N_T_SETS      = 5
N_RULES       = N_PH_SETS * N_T_SETS   # 25


def _nh3_fraction(pH: float, T: float) -> float:
    """Fraction of total ammonia in unionized (toxic) NH3 form (0.0–1.0)."""
    pka = 0.09018 + 2729.92 / (T + 273.15)
    return 1.0 / (1.0 + 10 ** (pka - pH))


def calculate_actual_risk(pH: float, T: float) -> int:
    """
    Calculate actual NH₃ risk level (ground truth).
    
    Risk thresholds based on NH₃ fraction:
    - Safe:     NH₃ < 1%   (0.01)
    - Caution:  NH₃ 1-5%   (0.01-0.05)
    - Warning:  NH₃ 5-10%  (0.05-0.10)
    - Critical: NH₃ > 10%  (0.10+)
    
    Returns: 0=Safe, 1=Caution, 2=Warning, 3=Critical
    """
    nh3_frac = _nh3_fraction(pH, T)
    if nh3_frac < 0.01:
        return RISK_SAFE
    elif nh3_frac < 0.05:
        return RISK_CAUTION
    elif nh3_frac < 0.10:
        return RISK_WARNING
    else:
        return RISK_CRITICAL


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
#  FQL Agent - Risk Classification
# ═══════════════════════════════════════════════════════════════════════════ #

class FQLAgent:
    """
    Fuzzy Q-Learning agent for NH₃ risk classification.

    25 rules → each predicts risk level (0-3).
    Learns online from actual NH₃ risk (ground truth).
    """

    # Rule order: (pH_set, T_set) — row-major 5×5
    _PH_SETS = ["VeryAcidic", "Acidic", "Normal", "Alkaline", "VeryAlkaline"]
    _T_SETS  = ["VeryCold", "Cold", "Optimal", "Hot", "VeryHot"]
    _RULE_ORDER = [
        ("VeryAcidic", "VeryCold"), ("VeryAcidic", "Cold"), ("VeryAcidic", "Optimal"), ("VeryAcidic", "Hot"), ("VeryAcidic", "VeryHot"),
        ("Acidic",     "VeryCold"), ("Acidic",     "Cold"), ("Acidic",     "Optimal"), ("Acidic",     "Hot"), ("Acidic",     "VeryHot"),
        ("Normal",     "VeryCold"), ("Normal",     "Cold"), ("Normal",     "Optimal"), ("Normal",     "Hot"), ("Normal",     "VeryHot"),
        ("Alkaline",   "VeryCold"), ("Alkaline",   "Cold"), ("Alkaline",   "Optimal"), ("Alkaline",   "Hot"), ("Alkaline",   "VeryHot"),
        ("VeryAlkaline","VeryCold"),("VeryAlkaline","Cold"), ("VeryAlkaline","Optimal"),("VeryAlkaline","Hot"),("VeryAlkaline","VeryHot"),
    ]  # 25 rules total

    def __init__(self,
                 alpha: float = 0.1,
                 gamma: float = 0.95,
                 eps_start: float = 0.3,
                 eps_min:   float = 0.05,
                 eps_decay: float = 0.9995):
        self.alpha     = alpha
        self.gamma     = gamma
        self.epsilon   = eps_start
        self.eps_min   = eps_min
        self.eps_decay = eps_decay

        # Q-table: 25 rules × 4 risk levels
        # Initialize with domain knowledge based on NH₃ risk
        # pH centers: 5.75, 6.25, 7.25, 8.25, 9.25
        # T  centers: 17.75, 21.0, 27.0, 32.5, 34.5
        _PH_C = [5.75, 6.25, 7.25, 8.25, 9.25]
        _T_C  = [17.75, 21.0, 27.0, 32.5, 34.5]

        def _init_risk_q(ph, t):
            """Initialize Q-values based on expected risk level"""
            actual_risk = calculate_actual_risk(ph, t)
            # Give higher Q-value to correct risk level
            q = [0.0, 0.0, 0.0, 0.0]
            q[actual_risk] = 1.0
            return q

        self.qtable = [
            _init_risk_q(_PH_C[r // N_T_SETS], _T_C[r % N_T_SETS])
            for r in range(N_RULES)
        ]

        self.total_steps      = 0
        self.converged        = False
        self.converged_sent   = False

        # Accuracy tracking for convergence
        self._accuracy_window:    list[float] = []   # buffer of last 100 steps
        self._avg_accuracy_history: list[float] = [] # average per 100-step window
        
        # Reward tracking for dashboard
        self._reward_window:      list[float] = []   # buffer of last 100 steps
        self._avg_reward_history:   list[float] = [] # average per 100-step window

    # ── Firing strength ─────────────────────────────────────────────────── #

    def compute_firing_strengths(self, pH: float, T: float) -> list:
        """
        Compute firing strength phi_r for all 25 rules.
        phi_r = mu_pH(pH) × mu_T(T)
        Returns: list of length 25.
        """
        mu_ph = FuzzyMembership.compute_pH_memberships(pH)
        mu_t  = FuzzyMembership.compute_T_memberships(T)
        return [
            mu_ph[ph_set] * mu_t[t_set]
            for ph_set, t_set in self._RULE_ORDER
        ]

    # ── Q-value FQL ─────────────────────────────────────────────────────── #

    def compute_Q_FQL(self, firing_strengths: list, risk_level: int) -> float:
        """
        Q_FQL(s, risk) = sum_r [phi_r(s) × Q_r(risk)]
        """
        return sum(
            firing_strengths[r] * self.qtable[r][risk_level]
            for r in range(N_RULES)
        )

    def compute_all_Q_FQL(self, firing_strengths: list) -> list:
        """
        Compute Q_FQL for all 4 risk levels.
        Returns: list of length 4.
        """
        return [
            self.compute_Q_FQL(firing_strengths, risk)
            for risk in range(N_RISK_LEVELS)
        ]

    # ── Risk prediction ──────────────────────────────────────────────────── #

    def predict_risk(self, pH: float, T: float) -> int:
        """
        Predict NH₃ risk level (0=Safe, 1=Caution, 2=Warning, 3=Critical).
        
        Uses epsilon-greedy for exploration during training:
        - With probability epsilon: random prediction
        - Otherwise: argmax Q_FQL(s, risk)
        
        Returns: risk level (0-3)
        """
        if random.random() < self.epsilon:
            return random.randint(0, N_RISK_LEVELS - 1)
        
        firing = self.compute_firing_strengths(pH, T)
        q_vals = self.compute_all_Q_FQL(firing)
        return int(q_vals.index(max(q_vals)))

    # ── Reward function ──────────────────────────────────────────────────── #

    def compute_reward(self, predicted_risk: int, actual_risk: int) -> float:
        """
        Reward based on prediction accuracy.
        
        - Correct prediction: +1.0
        - Off by 1 level:     -0.5
        - Off by 2+ levels:   -1.0
        
        Args:
            predicted_risk: Predicted risk level (0-3)
            actual_risk: Actual risk level from calculate_actual_risk()
        
        Returns: reward value
        """
        error = abs(predicted_risk - actual_risk)
        if error == 0:
            return +1.0  # Perfect prediction
        elif error == 1:
            return -0.5  # Close
        else:
            return -1.0  # Far off

    # ── Q-table update ───────────────────────────────────────────────────── #

    def update(self, pH: float, T: float, predicted_risk: int,
               actual_risk: int) -> float:
        """
        Update Q-table using supervised learning approach.
        
        For correct prediction: increase Q-value
        For wrong prediction: decrease Q-value
        
        Q_r(predicted) += alpha × phi_r(s) × reward
        
        Args:
            pH: Current pH
            T: Current temperature
            predicted_risk: Risk level predicted by agent
            actual_risk: Actual risk level (ground truth)
        
        Returns: reward value
        """
        firing = self.compute_firing_strengths(pH, T)
        reward = self.compute_reward(predicted_risk, actual_risk)

        # Update Q-values for all active rules
        for r in range(N_RULES):
            if firing[r] > 0.0:
                # Increase Q for correct prediction, decrease for wrong
                if predicted_risk == actual_risk:
                    self.qtable[r][predicted_risk] += self.alpha * firing[r] * reward
                else:
                    # Decrease Q for wrong prediction
                    self.qtable[r][predicted_risk] += self.alpha * firing[r] * reward
                    # Increase Q for correct answer
                    self.qtable[r][actual_risk] += self.alpha * firing[r] * abs(reward)

        # Epsilon decay
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)

        # Track accuracy and reward for dashboard and convergence
        accuracy = 1.0 if predicted_risk == actual_risk else 0.0
        self._accuracy_window.append(accuracy)
        self._reward_window.append(reward)
        if len(self._accuracy_window) >= 100:
            avg = sum(self._accuracy_window) / len(self._accuracy_window)
            self._avg_accuracy_history.append(avg)
            self._accuracy_window.clear()
            
            avg_rew = sum(self._reward_window) / len(self._reward_window)
            self._avg_reward_history.append(avg_rew)
            self._reward_window.clear()
            
        self.total_steps += 1
        return reward

    # ── Convergence ──────────────────────────────────────────────────────── #

    CONV_MIN_STEPS   = 2_000   # minimum training steps
    CONV_MIN_WINDOWS = 5       # consecutive 100-step windows needed
    CONV_MIN_ACCURACY = 0.75   # minimum accuracy to declare converged

    def check_convergence(self) -> bool:
        """
        Converged when:
          1. total_steps >= CONV_MIN_STEPS
          2. accuracy windows >= CONV_MIN_WINDOWS
          3. avg_accuracy[-1] >= CONV_MIN_ACCURACY
        """
        if self.converged:
            return True
        if self.total_steps < self.CONV_MIN_STEPS:
            return False
        hist = self._avg_accuracy_history
        if len(hist) < self.CONV_MIN_WINDOWS:
            return False
        if hist[-1] < self.CONV_MIN_ACCURACY:
            return False
        self.converged = True
        return True

    def convergence_progress(self) -> dict:
        """Return convergence progress (0.0–1.0 = done)."""
        hist = self._avg_accuracy_history
        acc  = hist[-1] if hist else 0.0
        return {
            "steps":      min(self.total_steps / self.CONV_MIN_STEPS,   1.0),
            "windows":    min(len(hist)         / self.CONV_MIN_WINDOWS, 1.0),
            "accuracy":   min(acc / self.CONV_MIN_ACCURACY, 1.0),
            "converged":  self.converged,
        }

    # ── Policy evaluation ────────────────────────────────────────────────── #

    _PH_CENTERS = [5.75, 6.25, 7.25, 8.25, 9.25]
    _T_CENTERS  = [17.75, 21.0, 27.0, 32.5, 34.5]

    def evaluate_policy(self) -> list[list[int]]:
        """
        Greedy risk prediction for all 25 fuzzy regions.
        Returns 5x5 list: [row=pH][col=T] -> risk level.
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
        Render risk prediction policy as 5x5 table.
        """
        policy = self.evaluate_policy()
        names  = ["SAFE", "CAUT", "WARN", "CRIT"]
        ph_lbl = ["VeryAcid", "Acidic  ", "Normal  ", "Alkaline", "VeryAlk "]
        t_lbl  = ["VCold", "Cold ", "Opt  ", "Hot  ", "VHot "]

        header = "  " + "  ".join(t_lbl)
        sep    = "  " + "-" * 42
        lines  = [
            "=" * 56,
            "  FQL Risk Prediction Map (5x5)",
            f"              {header}",
            sep,
        ]
        for i, ph in enumerate(ph_lbl):
            risks = "  ".join(names[policy[i][j]] for j in range(5))
            lines.append(f"  {ph}:  {risks}")
        lines.append("=" * 56)
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
        """Load Q-table from JSON file."""
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
        Format: "QTABLE:[[q00,q01,q02,q03],...,[q24_0,q24_1,q24_2,q24_3]]\\n"
        """
        rows = []
        for r in range(N_RULES):
            vals = ",".join(f"{self.qtable[r][risk]:.4f}" for risk in range(N_RISK_LEVELS))
            rows.append(f"[{vals}]")
        return "QTABLE:[" + ",".join(rows) + "]\n"

    # ── Statistics ───────────────────────────────────────────────────────── #

    def get_stats(self) -> dict:
        """Return agent statistics dictionary for logging."""
        acc_now = (self._avg_accuracy_history[-1]
                   if self._avg_accuracy_history else 0.0)
        acc_prev = (self._avg_accuracy_history[-2]
                    if len(self._avg_accuracy_history) >= 2 else 0.0)
        
        # Compute sliding average for current incomplete window
        rew_now = (self._avg_reward_history[-1] if self._avg_reward_history else 0.0)
        if self._reward_window:
            rew_now = sum(self._reward_window) / len(self._reward_window)
            
        return {
            "total_steps":        self.total_steps,
            "epsilon":            round(self.epsilon, 4),
            "avg_accuracy_100":   round(acc_now,  4),
            "avg_accuracy_prev":  round(acc_prev, 4),
            "avg_reward_100":     rew_now,
            "converged":          self.converged,
            "converged_sent":     self.converged_sent,
            "n_windows":          len(self._avg_accuracy_history),
        }
