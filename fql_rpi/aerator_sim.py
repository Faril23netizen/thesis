"""
Aerator Effect Simulator
========================
Simulates the physical effect of an aerator on pond water chemistry.
Used when no physical aerator is connected — creates closed-loop feedback
for FQL training based on typical aquaculture aerator specifications.

Physics per 2-second step (dt = 2s):
  pH rise  : aeration strips dissolved CO2, shifting carbonate equilibrium
             toward higher pH. Effect scales with airflow rate.
  Cooling  : evaporative cooling from air bubbles passing through water.

Typical aerator specs (small aquaculture pond, 100–500 L):
  LOW  : ~5W  air pump, ~2 L/min  → +0.001 pH/step, −0.005°C/step
  MED  : ~15W air pump, ~5 L/min  → +0.003 pH/step, −0.015°C/step
  HIGH : ~30W air pump, ~10 L/min → +0.006 pH/step, −0.030°C/step

Drift tracking (TRACK_RATE = 0.02):
  Simulated state drifts 2% per step toward the real sensor reading.
  This prevents long-term divergence between sim and real pond conditions
  while still showing the aerator effect clearly over short horizons.

Disable: set USE_AERATOR_SIM = False in main_fql.py when a real aerator
is connected — otherwise the effect would be counted twice.
"""

# Action indices
_OFF, _LOW, _MED, _HIGH = 0, 1, 2, 3

# Per-step aerator effect on pH (CO2 stripping → pH rise)
_PH_RISE = (_OFF * 0, 0.001, 0.003, 0.006)   # OFF / LOW / MED / HIGH

# Per-step aerator effect on temperature (evaporative cooling)
_COOLING = (0.000, 0.005, 0.015, 0.030)        # OFF / LOW / MED / HIGH

# Rate at which simulated state tracks real sensor (per step)
_TRACK_RATE = 0.02

_PH_MIN,   _PH_MAX   = 5.5, 9.5
_TEMP_MIN, _TEMP_MAX = 17.5, 35.0


class AeratorSim:
    """
    Maintains a running simulated pond state that responds to control
    actions and slowly tracks real sensor readings to prevent drift.

    Usage:
        sim = AeratorSim()
        # Call once per real step with the action that WAS running
        ph_sim, t_sim = sim.update(real_ph, real_temp, action)
    """

    def __init__(self):
        self._ph:   float | None = None
        self._temp: float | None = None

    def update(self, real_ph: float, real_temp: float,
               action: int) -> tuple[float, float]:
        """
        Apply one step of aerator physics.
        action : the action that was running during this time step.
        Returns (sim_ph, sim_temp).
        """
        if self._ph is None:
            self._ph, self._temp = real_ph, real_temp
            return real_ph, real_temp

        # Aerator physics
        self._ph   += _PH_RISE[action]
        self._temp -= _COOLING[action]

        # Slow tracking toward real sensor to prevent simulation drift
        self._ph   += _TRACK_RATE * (real_ph   - self._ph)
        self._temp += _TRACK_RATE * (real_temp - self._temp)

        # Physical bounds
        self._ph   = max(_PH_MIN,   min(_PH_MAX,   self._ph))
        self._temp = max(_TEMP_MIN, min(_TEMP_MAX, self._temp))

        return self._ph, self._temp

    def reset(self) -> None:
        self._ph = self._temp = None

    @property
    def state(self) -> tuple[float, float] | None:
        if self._ph is None:
            return None
        return self._ph, self._temp
