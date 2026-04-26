# Thesis Results Tables
## Progressive Hybrid FQL-DQN — Aquaculture Aerator Control

---

## Table 1. Simulation-Based Controller Comparison
*(30 episodes × 7 scenarios = 210 episodes, 300 steps/episode, identical virtual environment)*

| Controller | Avg Reward | Avg Energy/step | Avg NH3 (%) | pH Safe (%) |
|---|---|---|---|---|
| Rule-Based (RB) | -0.529 | 0.452 | 16.955 | 59.38 |
| FQL | -0.809 | 0.314 | 13.976 | 59.49 |
| **DQN** | **-0.395** | **0.300** | **13.622** | **60.49** |

**Improvement DQN vs RB:**
| Metric | RB | DQN | Δ | Improvement |
|---|---|---|---|---|
| Avg Reward | -0.529 | -0.395 | +0.134 | +25.3% |
| Avg Energy/step | 0.452 | 0.300 | -0.152 | -33.6% |
| Avg NH3 (%) | 16.955 | 13.622 | -3.333 | -19.7% |
| pH Safe (%) | 59.38 | 60.49 | +1.11 | +1.9% |

**Improvement DQN vs FQL:**
| Metric | FQL | DQN | Δ | Improvement |
|---|---|---|---|---|
| Avg Reward | -0.809 | -0.395 | +0.414 | +51.2% |
| Avg Energy/step | 0.314 | 0.300 | -0.014 | -4.5% |
| Avg NH3 (%) | 13.976 | 13.622 | -0.354 | -2.5% |
| pH Safe (%) | 59.49 | 60.49 | +1.00 | +1.7% |

---

## Table 2. Action Distribution Comparison (Simulation)

| Controller | OFF (%) | LOW (%) | MED (%) | HIGH (%) |
|---|---|---|---|---|
| Rule-Based (RB) | 0.0 | 50.5 | 48.5 | 1.0 |
| FQL | 1.5 | 93.5 | 3.5 | 1.5 |
| DQN | 0.0 | 100.0 | 0.0 | 0.0 |

---

## Table 3. Real-World Deployment Results
*(Actual pond data — Raspberry Pi 5 + Pico WH)*

| Phase | Steps | Avg Reward | Avg Energy/step | NH3 Exposure (%-steps) | pH Safe (%) | Dominant Action |
|---|---|---|---|---|---|---|
| Rule-Based (RB) | 1,805 | +0.197 | 0.405 | 22,325 | 65.1 | LOW=65%, MED=35% |
| FQL | 7,408 | +0.560 | 0.451 | 94,291 | 85.6 | LOW=50%, MED=51% |
| DQN | 39,023 | +0.265 | 0.489 | 408,589 | 72.0 | LOW=58%, MED=27%, HIGH=15% |

**Improvement FQL vs RB (Real Data):**
| Metric | RB | FQL | Δ |
|---|---|---|---|
| Avg Reward | +0.197 | +0.560 | +0.363 |
| Avg Energy/step | 0.405 | 0.451 | +0.046 |
| pH Safe (%) | 65.1 | 85.6 | +20.5% |

---

## Table 4. Per-Scenario Simulation Results

| Scenario | RB Reward | FQL Reward | DQN Reward | Best Controller |
|---|---|---|---|---|
| Normal | positive | positive | positive | DQN ≈ RB |
| Acid Crash | best | negative | negative | **RB** |
| Alkaline Spike | worst (-800) | moderate | moderate | **DQN / FQL** |
| Cold Stress | moderate | best | moderate | **FQL** |
| Heat Stress | best | negative | negative | **RB** |
| High NH3 Danger | negative | negative | best NH3 | **DQN** (NH3) |
| Multi-Stress Grid | similar | similar | similar | DQN ≈ all |

---

## Table 5. System Configuration Summary

| Parameter | Value |
|---|---|
| FQL Rules | 25 (5 pH sets × 5 Temperature sets) |
| FQL Actions | 4 (OFF, LOW, MED, HIGH) |
| FQL Learning Rate (α) | 0.1 |
| FQL Discount Factor (γ) | 0.95 |
| FQL ε decay | 0.9995 (1.0 → 0.05) |
| DQN Architecture | 2 → 64 → 64 → 4 (ReLU) |
| DQN Optimizer | Adam (lr=0.001) |
| DQN Loss Function | Huber Loss |
| DQN Batch Size | 64 |
| DQN Training Epochs | 300 |
| DQN Discount Factor (γ) | 0.95 |
| Replay Buffer Size | 50,000 transitions |
| Virtual Steps per Real Step | 10 |
| Sample Interval (Pico WH) | 2 seconds |
| Hardware | Raspberry Pi 5 + Pico WH |
