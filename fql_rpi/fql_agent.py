"""
FQL Agent — Fuzzy Q-Learning untuk RPi 4
==========================================
Thesis : Edge-Intelligent Aquaculture Aerator Control
         Using Progressive Hybrid FQL-DQN with N3IWF LES
Student: Faril Pirwanhadi (M14128104)

Referensi update rule: Er & Deng, IEEE SMC 2004 — Dynamic FQL
"""

import json
import math
import random

# ── Konstanta aksi ───────────────────────────────────────────────────────── #
ACTION_OFF  = 0
ACTION_LOW  = 1
ACTION_MED  = 2
ACTION_HIGH = 3
N_ACTIONS   = 4
N_RULES     = 9

# Biaya energi per aksi untuk reward (dinormalisasi 0–1)
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
    """Kumpulan fungsi keanggotaan fuzzy trapezoidal untuk pH dan suhu."""

    @staticmethod
    def trapezoidal(x: float, a: float, b: float, c: float, d: float) -> float:
        """
        Fungsi keanggotaan trapezoidal.
          0           jika x <= a atau x >= d
          (x-a)/(b-a) jika a < x < b
          1.0         jika b <= x <= c
          (d-x)/(d-c) jika c < x < d
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
        Hitung derajat keanggotaan pH untuk 3 set fuzzy.
        Return: {"Acidic": float, "Normal": float, "Alkaline": float}
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
        Hitung derajat keanggotaan suhu untuk 3 set fuzzy.
        Return: {"Cold": float, "Optimal": float, "Hot": float}
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

    9 rules × 4 aksi = 36 nilai Q-table.
    Belajar online dari data Rule-Based yang dikirim Pico.
    """

    # Urutan rule: (pH_set, T_set) — row-major 3×3
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

        # Q-table: list 9×4, semua 0.0
        self.qtable = [[0.0] * N_ACTIONS for _ in range(N_RULES)]

        self.total_steps      = 0
        self.converged        = False
        self.converged_sent   = False   # flag — Q-table sudah dikirim ke Pico

        # History reward untuk deteksi konvergensi
        self._reward_window:    list[float] = []   # buffer 100 step terakhir
        self._avg_reward_history: list[float] = [] # rata-rata tiap 100 step

        self._prev_action: int | None = None

    # ── Firing strength ─────────────────────────────────────────────────── #

    def compute_firing_strengths(self, pH: float, T: float) -> list:
        """
        Hitung firing strength φ_r untuk semua 9 rules.
        phi_r = mu_pH(pH) × mu_T(T)
        Return: list panjang 9.
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
        Q_FQL(s, a) = Σ_r [phi_r(s) × Q_r(a)]
        """
        return sum(
            firing_strengths[r] * self.qtable[r][action]
            for r in range(N_RULES)
        )

    def compute_all_Q_FQL(self, firing_strengths: list) -> list:
        """
        Hitung Q_FQL untuk semua 4 aksi.
        Return: list panjang 4.
        """
        return [
            self.compute_Q_FQL(firing_strengths, a)
            for a in range(N_ACTIONS)
        ]

    # ── Action selection ─────────────────────────────────────────────────── #

    def select_action(self, pH: float, T: float) -> int:
        """
        ε-greedy action selection.
        Selama fase belajar dari Rule-Based, hasilnya tidak dikirim ke Pico —
        hanya dipakai untuk internal FQL update.
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

        R_safe    : +1.0 jika pH ∈ [6.5, 8.5], -5.0 di luar
        R_energy  : biaya daya aksi (0 s.d. -1.0)
        R_NH3     : -f(NH3) berdasarkan pH dan suhu berikutnya
        R_stability: -1.0 jika aksi berubah, 0.0 jika sama
        """
        # R_safe
        r_safe = 1.0 if 6.5 <= pH <= 8.5 else -5.0

        # R_energy
        r_energy = -ENERGY_COST[action]

        # R_NH3 — hitung dari state berikutnya (s')
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
        Update Q-table dengan TD error (Er & Deng, 2004).

        Q_r(a) += α × φ_r(s) × TD_error
        TD_error = r + γ × max_a Q_FQL(s') − Q_FQL(s, a)

        Return: TD_error
        """
        firing      = self.compute_firing_strengths(pH, T)
        q_now       = self.compute_Q_FQL(firing, action)

        firing_next = self.compute_firing_strengths(pH_next, T_next)
        q_next_max  = max(self.compute_all_Q_FQL(firing_next))

        td_error = reward + self.gamma * q_next_max - q_now

        # Update semua rule yang aktif (phi_r > 0)
        for r in range(N_RULES):
            if firing[r] > 0.0:
                self.qtable[r][action] += self.alpha * firing[r] * td_error

        # Update ε decay
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)

        # Catat reward untuk monitoring konvergensi
        self._reward_window.append(reward)
        if len(self._reward_window) >= 100:
            avg = sum(self._reward_window) / len(self._reward_window)
            self._avg_reward_history.append(avg)
            self._reward_window.clear()

        self.total_steps  += 1
        self._prev_action  = action
        return td_error

    # ── Konvergensi ──────────────────────────────────────────────────────── #

    def check_convergence(self) -> bool:
        """
        Konvergen jika SEMUA terpenuhi:
          1. total_steps >= 500
          2. sudah ada >= 2 window rata-rata (>=200 step)
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

    # ── Serialisasi ──────────────────────────────────────────────────────── #

    def save_qtable(self, filename: str) -> None:
        """Simpan Q-table dan state agent ke file JSON."""
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
            print(f"[fql] Gagal simpan qtable: {e}")

    def load_qtable(self, filename: str) -> bool:
        """
        Load Q-table dari file JSON.
        Return True jika berhasil, False jika file tidak ada atau rusak.
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
        Serialisasi Q-table ke format string untuk dikirim ke Pico.
        Format: "QTABLE:[[q00,q01,q02,q03],...,[q80,q81,q82,q83]]\\n"
        """
        rows = []
        for r in range(N_RULES):
            vals = ",".join(f"{self.qtable[r][a]:.4f}" for a in range(N_ACTIONS))
            rows.append(f"[{vals}]")
        return "QTABLE:[" + ",".join(rows) + "]\n"

    # ── Statistik ────────────────────────────────────────────────────────── #

    def get_stats(self) -> dict:
        """Return dict statistik agent untuk logging."""
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
