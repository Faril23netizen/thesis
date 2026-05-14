"""
DQN Training — Progressive Hybrid FQL-DQN
==========================================
Thesis : Edge-Intelligent Aquaculture Aerator Control
         Using Progressive Hybrid FQL-DQN with N3IWF LES
Student: Faril Pirwanhadi (M14128104)

Trains a Deep Q-Network on the replay buffer collected during FQL operation.
The DQN refines the policy learned by FQL using a neural network approximator.

Architecture:
  Input  : [pH, T]  (normalized to [0, 1])
  Hidden : 64 → 64  (ReLU)
  Output : Q(s, a) for 4 actions (OFF, LOW, MED, HIGH)

Training:
  - Experience replay from dqn_buffer.json
  - Target network (updated every TARGET_UPDATE_FREQ steps)
  - Huber loss (robust to outliers)
  - Adam optimizer

Usage:
  uv run python3 train_dqn.py
  uv run python3 train_dqn.py --buffer dqn_buffer.json --epochs 200
"""

import argparse
import json
import os
import random
import sys
import time

import numpy as np

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "hasil_real")

BUFFER_FILE = os.path.join(RESULTS_DIR, "dqn_buffer.json")
MODEL_FILE  = os.path.join(RESULTS_DIR, "dqn_model.pt")
LOG_DIR     = os.path.join(RESULTS_DIR, "logs")

# ── Hyperparameters ──────────────────────────────────────────────────────── #
# GAMMA=0.70 (not 0.95): keeps Q magnitudes bounded ≈ r/(1-γ) ≈ 3.3×reward.
# With GAMMA=0.95, Q[LOW]_SAFE≈20 dominates gradient across all states (all-LOW).
GAMMA              = 0.80   # Balanced: propagates stress rewards without all-LOW collapse
LR                 = 1e-3
BATCH_SIZE         = 256
EPOCHS             = 20000
TARGET_UPDATE_FREQ = 200     # update target network every N epochs
MIN_BUFFER         = 500    # minimum transitions needed to start training

# State normalization bounds
PH_MIN, PH_MAX     = 5.5,  9.5
T_MIN,  T_MAX      = 17.5, 35.0
N_ACTIONS          = 4
ACTION_NAMES       = ["OFF", "LOW", "MED", "HIGH"]


# ── State normalization ───────────────────────────────────────────────────── #

def normalize(ph: float, t: float) -> list:
    return [
        (ph - PH_MIN) / (PH_MAX - PH_MIN),
        (t  - T_MIN)  / (T_MAX  - T_MIN),
    ]


# ── Load buffer ───────────────────────────────────────────────────────────── #

def load_buffer(path: str) -> list:
    print(f"Loading buffer: {path}")
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, list) or len(data) == 0:
            print("[ERROR] Buffer is empty or invalid.")
            sys.exit(1)
        print(f"Loaded {len(data):,} transitions.")
        return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] Cannot load buffer: {e}")
        sys.exit(1)


def buffer_to_arrays(buffer: list):
    """Convert buffer list to numpy arrays."""
    states      = np.array([normalize(t["s"][0],      t["s"][1])      for t in buffer], dtype=np.float32)
    actions     = np.array([t["a"]                                     for t in buffer], dtype=np.int64)
    rewards     = np.array([t["r"]                                     for t in buffer], dtype=np.float32)
    next_states = np.array([normalize(t["s_next"][0], t["s_next"][1]) for t in buffer], dtype=np.float32)
    return states, actions, rewards, next_states


# ══════════════════════════════════════════════════════════════════════════ #
#  DQN Network (PyTorch)
# ══════════════════════════════════════════════════════════════════════════ #

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class DQNNet(nn.Module if TORCH_AVAILABLE else object):
    """Small DQN for embedded deployment on RPi5."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(2,  64), nn.ReLU(),
            nn.Linear(64, 64), nn.ReLU(),
            nn.Linear(64, N_ACTIONS),
        )

    def forward(self, x):
        return self.net(x)


def train_pytorch(buffer: list, epochs: int, model_path: str):
    import torch
    import torch.nn as nn
    import torch.optim as optim

    print(f"\nTraining DQN with PyTorch  ({len(buffer):,} transitions, {epochs} epochs)")

    states, actions, rewards, next_states = buffer_to_arrays(buffer)
    N = len(states)

    # Online + target networks
    online_net = DQNNet()
    target_net = DQNNet()
    target_net.load_state_dict(online_net.state_dict())
    target_net.eval()

    optimizer = optim.Adam(online_net.parameters(), lr=LR)
    loss_fn   = nn.HuberLoss()

    t_start = time.time()
    losses  = []

    for epoch in range(1, epochs + 1):
        # Sample mini-batch
        idx    = np.random.randint(0, N, BATCH_SIZE)
        s      = torch.tensor(states[idx])
        a      = torch.tensor(actions[idx])
        r      = torch.tensor(rewards[idx])
        s_next = torch.tensor(next_states[idx])

        # Bellman target: y = r + γ × max_a Q_target(s')
        # Exclude action 0 (OFF) — never in buffer, untrained Q values add noise
        with torch.no_grad():
            q_next = target_net(s_next)[:, 1:].max(dim=1).values
            y      = r + GAMMA * q_next

        # Current Q(s, a)
        q_pred = online_net(s).gather(1, a.unsqueeze(1)).squeeze(1)

        loss = loss_fn(q_pred, y)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        losses.append(loss.item())

        # Sync target network
        if epoch % TARGET_UPDATE_FREQ == 0:
            target_net.load_state_dict(online_net.state_dict())

        if epoch % 50 == 0:
            avg_loss = np.mean(losses[-50:])
            print(f"  Epoch {epoch:4d}/{epochs} | loss={avg_loss:.5f} | "
                  f"elapsed={time.time()-t_start:.1f}s")

    # Save model
    torch.save({
        "model_state": online_net.state_dict(),
        "ph_min": PH_MIN, "ph_max": PH_MAX,
        "t_min":  T_MIN,  "t_max":  T_MAX,
        "n_actions": N_ACTIONS,
        "hidden": 64,
        "epochs_trained": epochs,
        "buffer_size": N,
    }, model_path)
    print(f"\nModel saved: {model_path}")

    # Policy evaluation
    print("\nDQN Policy Map (greedy):")
    _print_policy_pytorch(online_net)
    return online_net


def _print_policy_pytorch(net):
    import torch
    ph_centers = [5.75, 6.25, 7.25, 8.25, 9.25]
    t_centers  = [17.75, 21.0, 27.0, 32.5, 34.5]
    ph_lbl     = ["VeryAcid", "Acidic  ", "Normal  ", "Alkaline", "VeryAlk "]
    t_lbl      = ["VCold", "Cold ", "Opt  ", "Hot  ", "VHot "]
    names      = ["OFF ", "LOW ", "MED ", "HIGH"]

    print("  " + "  ".join(t_lbl))
    print("  " + "-" * 38)
    for i, ph in enumerate(ph_centers):
        row = []
        for t in t_centers:
            s = torch.tensor([normalize(ph, t)], dtype=torch.float32)
            with torch.no_grad():
                a = net(s).argmax(dim=1).item()
            row.append(names[a])
        print(f"  {ph_lbl[i]}:  {'  '.join(row)}")


# ══════════════════════════════════════════════════════════════════════════ #
#  Numpy fallback (no PyTorch)
# ══════════════════════════════════════════════════════════════════════════ #

def relu(x):
    return np.maximum(0, x)


class DQNNumpy:
    """Minimal 2-layer DQN using numpy (fallback when PyTorch unavailable)."""

    def __init__(self, lr=LR):
        self.lr = lr
        np.random.seed(42)  # deterministic weight init
        self.W1 = np.random.randn(2,  64).astype(np.float32) * 0.1
        self.b1 = np.zeros((1, 64),        dtype=np.float32)
        self.W2 = np.random.randn(64, 64).astype(np.float32) * 0.1
        self.b2 = np.zeros((1, 64),        dtype=np.float32)
        self.W3 = np.random.randn(64, N_ACTIONS).astype(np.float32) * 0.1
        self.b3 = np.zeros((1, N_ACTIONS), dtype=np.float32)
        # Target network weights
        self._sync_target()

    def _sync_target(self):
        self.tW1, self.tb1 = self.W1.copy(), self.b1.copy()
        self.tW2, self.tb2 = self.W2.copy(), self.b2.copy()
        self.tW3, self.tb3 = self.W3.copy(), self.b3.copy()

    def _forward(self, x, target=False):
        W1,b1,W2,b2,W3,b3 = (self.tW1,self.tb1,self.tW2,self.tb2,self.tW3,self.tb3) \
                             if target else \
                             (self.W1, self.b1, self.W2, self.b2, self.W3, self.b3)
        h1 = relu(x @ W1 + b1)
        h2 = relu(h1 @ W2 + b2)
        return h2 @ W3 + b3

    def predict(self, x):
        return self._forward(x, target=False)

    def predict_target(self, x):
        return self._forward(x, target=True)

    def train_step(self, s, a, r, s_next):
        # Bellman target — exclude OFF (col 0), never in buffer, noisy Q
        q_next = self.predict_target(s_next)[:, 1:].max(axis=1, keepdims=True)
        y      = r.reshape(-1, 1) + GAMMA * q_next  # (B,1)

        # Forward pass (online)
        h1 = relu(s @ self.W1 + self.b1)
        h2 = relu(h1 @ self.W2 + self.b2)
        q  = h2 @ self.W3 + self.b3  # (B, 4)

        # One-hot target
        q_target = q.copy()
        for i, ai in enumerate(a):
            q_target[i, ai] = y[i, 0]

        # Huber loss gradient (simplified MSE)
        delta = q - q_target  # (B, 4)
        loss  = np.mean(delta ** 2)

        # Backprop W3
        dW3 = h2.T @ (2 * delta) / len(s)
        db3 = (2 * delta).mean(axis=0, keepdims=True)

        # Backprop W2
        d2  = (2 * delta) @ self.W3.T * (h2 > 0)
        dW2 = h1.T @ d2 / len(s)
        db2 = d2.mean(axis=0, keepdims=True)

        # Backprop W1
        d1  = d2 @ self.W2.T * (h1 > 0)
        dW1 = s.T @ d1 / len(s)
        db1 = d1.mean(axis=0, keepdims=True)

        # Gradient descent
        self.W3 -= self.lr * dW3;  self.b3 -= self.lr * db3
        self.W2 -= self.lr * dW2;  self.b2 -= self.lr * db2
        self.W1 -= self.lr * dW1;  self.b1 -= self.lr * db1

        return loss

    def save(self, path: str, buffer_size: int, epochs: int):
        np.save(path.replace(".pt", "_W1.npy"), self.W1)
        np.save(path.replace(".pt", "_b1.npy"), self.b1)
        np.save(path.replace(".pt", "_W2.npy"), self.W2)
        np.save(path.replace(".pt", "_b2.npy"), self.b2)
        np.save(path.replace(".pt", "_W3.npy"), self.W3)
        np.save(path.replace(".pt", "_b3.npy"), self.b3)
        meta = {"ph_min":PH_MIN,"ph_max":PH_MAX,"t_min":T_MIN,"t_max":T_MAX,
                "n_actions":N_ACTIONS,"hidden":64,"epochs_trained":epochs,
                "buffer_size":buffer_size,"backend":"numpy"}
        with open(path.replace(".pt", "_meta.json"), "w") as f:
            json.dump(meta, f, indent=2)
        print(f"Model saved (numpy): {path.replace('.pt','_W*.npy')}")

    def policy(self, ph: float, t: float) -> int:
        x = np.array([normalize(ph, t)], dtype=np.float32)
        q = self.predict(x)[0]
        return int(np.argmax(q[1:])) + 1


def train_numpy(buffer: list, epochs: int, model_path: str):
    print(f"\nTraining DQN with numpy  ({len(buffer):,} transitions, {epochs} epochs)")

    states, actions, rewards, next_states = buffer_to_arrays(buffer)
    N   = len(states)
    net = DQNNumpy(lr=LR)

    t_start = time.time()
    losses  = []

    for epoch in range(1, epochs + 1):
        idx    = np.random.randint(0, N, BATCH_SIZE)
        loss   = net.train_step(states[idx], actions[idx],
                                rewards[idx], next_states[idx])
        losses.append(loss)

        if epoch % TARGET_UPDATE_FREQ == 0:
            net._sync_target()

        if epoch % 50 == 0:
            avg_loss = np.mean(losses[-50:])
            print(f"  Epoch {epoch:4d}/{epochs} | loss={avg_loss:.5f} | "
                  f"elapsed={time.time()-t_start:.1f}s")

    net.save(model_path, N, epochs)

    print("\nDQN Policy Map (greedy):")
    ph_centers = [5.75, 6.25, 7.25, 8.25, 9.25]
    t_centers  = [17.75, 21.0, 27.0, 32.5, 34.5]
    ph_lbl     = ["VeryAcid", "Acidic  ", "Normal  ", "Alkaline", "VeryAlk "]
    t_lbl      = ["VCold", "Cold ", "Opt  ", "Hot  ", "VHot "]
    names      = ["OFF ", "LOW ", "MED ", "HIGH"]
    print("  " + "  ".join(t_lbl))
    print("  " + "-" * 38)
    for i, ph in enumerate(ph_centers):
        row = [names[net.policy(ph, t)] for t in t_centers]
        print(f"  {ph_lbl[i]}:  {'  '.join(row)}")

    return net


# ══════════════════════════════════════════════════════════════════════════ #
#  Entry point
# ══════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train DQN from FQL replay buffer")
    parser.add_argument("--buffer", default=BUFFER_FILE,  help="Path to dqn_buffer.json")
    parser.add_argument("--model",  default=MODEL_FILE,   help="Output model path (.pt)")
    parser.add_argument("--epochs", type=int, default=EPOCHS, help=f"Training epochs (default {EPOCHS})")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)

    buffer = load_buffer(args.buffer)

    if len(buffer) < MIN_BUFFER:
        print(f"[ERROR] Need at least {MIN_BUFFER} transitions, got {len(buffer)}.")
        print("Run main_fql.py longer to collect more data first.")
        sys.exit(1)

    print(f"Buffer size   : {len(buffer):,}")
    print(f"Epochs        : {args.epochs}")
    print(f"Batch size    : {BATCH_SIZE}")
    print(f"Learning rate : {LR}")
    print(f"Gamma         : {GAMMA}")

    if TORCH_AVAILABLE:
        print("Backend       : PyTorch")
        train_pytorch(buffer, args.epochs, args.model)
    else:
        print("Backend       : numpy (PyTorch not found)")
        train_numpy(buffer, args.epochs, args.model)

    print("\nDone. Next step: run evaluate_dqn.py to compare FQL vs DQN vs RB.")
