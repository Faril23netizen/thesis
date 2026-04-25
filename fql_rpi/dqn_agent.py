"""
DQN Agent — inference only
===========================
Loads a trained DQN model and provides select_action(pH, T).
Supports both PyTorch (.pt) and numpy fallback (_meta.json + _W*.npy).
"""

import json
import os
import numpy as np

PH_MIN, PH_MAX = 5.5,  9.5
T_MIN,  T_MAX  = 17.5, 35.0
N_ACTIONS      = 4


def _normalize(ph: float, t: float) -> np.ndarray:
    return np.array([
        (ph - PH_MIN) / (PH_MAX - PH_MIN),
        (t  - T_MIN)  / (T_MAX  - T_MIN),
    ], dtype=np.float32)


def _relu(x):
    return np.maximum(0.0, x)


class DQNAgent:
    """
    Loaded DQN for real-time inference.

    Usage:
        agent = DQNAgent()
        if agent.load(model_path):
            action = agent.select_action(pH, T)
    """

    def __init__(self):
        self._ready   = False
        self._backend = None   # "torch" or "numpy"
        self._net     = None   # torch Module or dict of numpy arrays

    # ── Loading ──────────────────────────────────────────────────────────── #

    def load(self, path: str) -> bool:
        """
        Load model from path.
        Tries PyTorch first; falls back to numpy weights.
        Returns True on success.
        """
        if path.endswith(".pt") and os.path.exists(path):
            if self._load_torch(path):
                return True
        # numpy fallback
        meta_path = path.replace(".pt", "_meta.json")
        if os.path.exists(meta_path):
            return self._load_numpy(path)
        return False

    def _load_torch(self, path: str) -> bool:
        try:
            import torch
            import torch.nn as nn

            ckpt = torch.load(path, map_location="cpu")

            class _Net(nn.Module):
                def __init__(self, hidden=64):
                    super().__init__()
                    self.net = nn.Sequential(
                        nn.Linear(2, hidden), nn.ReLU(),
                        nn.Linear(hidden, hidden), nn.ReLU(),
                        nn.Linear(hidden, N_ACTIONS),
                    )
                def forward(self, x):
                    return self.net(x)

            hidden = ckpt.get("hidden", 64)
            net = _Net(hidden)
            net.load_state_dict(ckpt["model_state"])
            net.eval()

            self._net     = net
            self._backend = "torch"
            self._ready   = True
            return True
        except Exception:
            return False

    def _load_numpy(self, path: str) -> bool:
        try:
            base = path.replace(".pt", "")
            W1 = np.load(base + "_W1.npy")
            b1 = np.load(base + "_b1.npy")
            W2 = np.load(base + "_W2.npy")
            b2 = np.load(base + "_b2.npy")
            W3 = np.load(base + "_W3.npy")
            b3 = np.load(base + "_b3.npy")
            self._net     = {"W1":W1,"b1":b1,"W2":W2,"b2":b2,"W3":W3,"b3":b3}
            self._backend = "numpy"
            self._ready   = True
            return True
        except Exception:
            return False

    # ── Inference ─────────────────────────────────────────────────────────── #

    @property
    def ready(self) -> bool:
        return self._ready

    def q_values(self, ph: float, t: float) -> list:
        """Return Q-values for all 4 actions."""
        if not self._ready:
            return [0.0] * N_ACTIONS
        x = _normalize(ph, t)
        if self._backend == "torch":
            import torch
            with torch.no_grad():
                q = self._net(torch.tensor(x).unsqueeze(0)).squeeze(0).numpy()
            return q.tolist()
        else:
            w = self._net
            h1 = _relu(x @ w["W1"] + w["b1"][0])
            h2 = _relu(h1 @ w["W2"] + w["b2"][0])
            q  = h2 @ w["W3"] + w["b3"][0]
            return q.tolist()

    def select_action(self, ph: float, t: float) -> int:
        """Greedy action selection."""
        q = self.q_values(ph, t)
        return int(np.argmax(q))

    def to_qtable_string(self) -> str:
        """
        Evaluate DQN at the 25 FQL rule centers and return a Q-table string
        in the same format as FQL — so it can be sent directly to the Pico.

        Rule order matches FQL: row-major pH×T (5×5).
        pH centers : 5.75, 6.25, 7.25, 8.25, 9.25
        T  centers : 17.75, 21.0, 27.0, 32.5, 34.5
        """
        ph_centers = [5.75, 6.25, 7.25, 8.25, 9.25]
        t_centers  = [17.75, 21.0, 27.0, 32.5, 34.5]
        rows = []
        for ph in ph_centers:
            for t in t_centers:
                q = self.q_values(ph, t)
                vals = ",".join(f"{v:.4f}" for v in q)
                rows.append(f"[{vals}]")
        return "QTABLE:[" + ",".join(rows) + "]\n"
