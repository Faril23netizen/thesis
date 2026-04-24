"""
Virtual Pond Simulator — for FQL pre-training
==============================================
Models simplified pond water chemistry (pH + temperature) with
realistic disturbances and systematic extreme scenario generation.

Physics:
  pH   : CO2 stripping by aeration raises pH; biological drift; buffering;
         scenario-specific acid/alkaline load; Gaussian noise.
  Temp : Evaporative cooling by aeration; ambient heat exchange;
         scenario-specific ambient; Gaussian noise.

Scenario types cover the full 9-rule fuzzy state space:
  NORMAL       — stable pond, mild random disturbances
  ACID_CRASH   — pH below safe range, acid load
  ALKALINE     — pH above safe range, alkaline load
  COLD_STRESS  — low temperature
  HEAT_STRESS  — high temperature
  HIGH_NH3     — high pH + high temperature (worst NH3 case)
  MULTI_STRESS — full state-space grid sweep, all 9 fuzzy regions
"""

import random
import math
from dataclasses import dataclass
from enum import IntEnum


# ── Scenario types ───────────────────────────────────────────────────────── #

class ScenarioType(IntEnum):
    NORMAL       = 0
    ACID_CRASH   = 1
    ALKALINE     = 2
    COLD_STRESS  = 3
    HEAT_STRESS  = 4
    HIGH_NH3     = 5
    MULTI_STRESS = 6


# ── Physics config ───────────────────────────────────────────────────────── #

@dataclass
class SimConfig:
    dt: float = 2.0  # seconds per step (matches real Pico sample interval)

    # pH dynamics — per step
    aeration_ph_rise: tuple = (0.000, 0.002, 0.005, 0.010)  # OFF/LOW/MED/HIGH
    buffering_rate:   float = 0.005   # pull toward ph_equilibrium each step
    ph_equilibrium:   float = 7.5     # natural buffering target
    ph_noise_std:     float = 0.02    # Gaussian noise on pH

    # Temperature dynamics — per step
    aeration_cooling:    tuple = (0.00, 0.01, 0.03, 0.06)  # OFF/LOW/MED/HIGH
    heat_exchange_rate:  float = 0.002   # pull toward ambient each step
    temp_noise_std:      float = 0.05    # Gaussian noise on temperature

    # Hard state boundaries
    ph_min:   float = 5.5
    ph_max:   float = 9.5
    temp_min: float = 17.5
    temp_max: float = 35.0


# ── Scenario parameter table ─────────────────────────────────────────────── #
#
# ph_range   — (lo, hi) for random initial pH
# temp_range — (lo, hi) for random initial temperature
# ph_drift   — constant acid(-) or alkaline(+) load added every step
# amb_range  — (lo, hi) ambient temperature this episode
#
_SCENARIO_TABLE = {
    ScenarioType.NORMAL: {
        "ph_range":   (7.0, 8.0),   # true optimal zone — LOW is sufficient here
        "temp_range": (24.0, 29.0), # comfortable temperature range
        "ph_drift":   -0.002,       # mild acid drift (CO2 buildup) — realistic
        "amb_range":  (24.0, 28.0),
        "label":      "Normal",
    },
    ScenarioType.ACID_CRASH: {
        "ph_range":   (5.5, 6.5),   # capped at 6.5 — no overlap with Normal fuzzy set
        "temp_range": (22.0, 30.0),
        "ph_drift":   -0.008,
        "amb_range":  (24.0, 28.0),
        "label":      "Acid Crash",
    },
    ScenarioType.ALKALINE: {
        "ph_range":   (8.5, 9.5),   # raised to 8.5 — no overlap with Normal fuzzy set
        "temp_range": (25.0, 32.0),
        "ph_drift":   +0.006,
        "amb_range":  (26.0, 30.0),
        "label":      "Alkaline Spike",
    },
    ScenarioType.COLD_STRESS: {
        "ph_range":   (6.5, 8.0),
        "temp_range": (17.5, 22.0),
        "ph_drift":    0.000,
        "amb_range":  (17.0, 20.0),
        "label":      "Cold Stress",
    },
    ScenarioType.HEAT_STRESS: {
        "ph_range":   (7.0, 8.5),
        "temp_range": (32.0, 35.0),
        "ph_drift":    0.000,
        "amb_range":  (33.0, 35.0),
        "label":      "Heat Stress",
    },
    ScenarioType.HIGH_NH3: {
        "ph_range":   (8.0, 9.5),
        "temp_range": (30.0, 35.0),
        "ph_drift":   +0.004,
        "amb_range":  (32.0, 35.0),
        "label":      "High NH3 Danger",
    },
    # MULTI_STRESS uses the grid sweep — table entry is a placeholder
    ScenarioType.MULTI_STRESS: {
        "ph_range":   (5.5, 9.5),
        "temp_range": (17.5, 35.0),
        "ph_drift":    0.000,
        "amb_range":  (20.0, 32.0),
        "label":      "Multi-Stress Grid",
    },
}

# 9 grid points — one per fuzzy region (pH center × T center)
# pH:  Acidic≈5.8, Normal≈7.25, Alkaline≈8.75
# T:   Cold≈19.5,  Optimal≈27.5, Hot≈34.0
_GRID_STARTS = [
    (ph, temp)
    for ph   in [5.8, 7.25, 8.75]
    for temp in [19.5, 27.5, 34.0]
]


class PondSimulator:
    """
    Simulates pond water chemistry for one episode at a time.

    Usage:
        sim = PondSimulator()
        ph, temp = sim.reset(ScenarioType.ACID_CRASH)
        for _ in range(steps):
            action = agent.select_action(ph, temp)
            ph, temp = sim.step(action)
    """

    def __init__(self, config: SimConfig | None = None):
        self.cfg = config or SimConfig()
        self.ph:   float = 7.5
        self.temp: float = 28.0
        self._ph_drift:     float = 0.0
        self._temp_ambient: float = 28.0
        self.step_count:    int   = 0
        self._grid_index:   int   = 0   # used for MULTI_STRESS round-robin

    def reset(self, scenario: ScenarioType,
              ph_override:   float | None = None,
              temp_override: float | None = None) -> tuple[float, float]:
        """
        Reset to a new episode.
        MULTI_STRESS cycles through all 9 fuzzy-region starting points.
        Returns initial (pH, temperature).
        """
        cfg = _SCENARIO_TABLE[scenario]
        self._ph_drift = cfg["ph_drift"]

        amb_lo, amb_hi = cfg["amb_range"]
        self._temp_ambient = random.uniform(amb_lo, min(amb_hi, self.cfg.temp_max))

        if scenario == ScenarioType.MULTI_STRESS:
            # Round-robin over the 9 grid centers, then fall back to random
            if self._grid_index < len(_GRID_STARTS):
                ph_start, temp_start = _GRID_STARTS[self._grid_index]
                self._grid_index += 1
            else:
                ph_lo, ph_hi = cfg["ph_range"]
                t_lo,  t_hi  = cfg["temp_range"]
                ph_start   = random.uniform(ph_lo, ph_hi)
                temp_start = random.uniform(t_lo,  t_hi)
                if self._grid_index >= len(_GRID_STARTS) * 3:
                    self._grid_index = 0  # reset grid after 3 full sweeps
                self._grid_index += 1
        else:
            ph_lo, ph_hi = cfg["ph_range"]
            t_lo,  t_hi  = cfg["temp_range"]
            ph_start   = ph_override   if ph_override   is not None else random.uniform(ph_lo, ph_hi)
            temp_start = temp_override if temp_override is not None else random.uniform(t_lo,  t_hi)

        self.ph         = ph_start
        self.temp       = temp_start
        self.step_count = 0
        return self.ph, self.temp

    def step(self, action: int) -> tuple[float, float]:
        """
        Advance simulation by one step (dt seconds) with the given action.
        Returns next (pH, temperature).
        """
        # ── pH update ────────────────────────────────────────────────────── #
        ph_rise  = self.cfg.aeration_ph_rise[action]
        buffering = self.cfg.buffering_rate * (self.cfg.ph_equilibrium - self.ph)
        ph_noise  = random.gauss(0.0, self.cfg.ph_noise_std)
        self.ph  += ph_rise + buffering + self._ph_drift + ph_noise
        self.ph   = max(self.cfg.ph_min, min(self.cfg.ph_max, self.ph))

        # ── Temperature update ───────────────────────────────────────────── #
        cooling   = self.cfg.aeration_cooling[action]
        exchange  = self.cfg.heat_exchange_rate * (self._temp_ambient - self.temp)
        t_noise   = random.gauss(0.0, self.cfg.temp_noise_std)
        self.temp += -cooling + exchange + t_noise
        self.temp  = max(self.cfg.temp_min, min(self.cfg.temp_max, self.temp))

        self.step_count += 1
        return self.ph, self.temp

    def get_state(self) -> tuple[float, float]:
        return self.ph, self.temp

    @staticmethod
    def label(scenario: ScenarioType) -> str:
        return _SCENARIO_TABLE[scenario]["label"]

    @staticmethod
    def all_scenarios() -> list[ScenarioType]:
        return list(ScenarioType)
