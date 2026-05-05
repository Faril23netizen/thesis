# Daily Scrum Report
**Name:** Faril Pirwanhadi
**Date:** 2026-04-26

---

## 1. [Last Week] What have you done since the last daily scrum?

Since the last meeting, I have completed the following:

- **Aquaculture Thesis — Progressive Hybrid FQL-DQN Pipeline:**
  Successfully implemented and validated the full three-phase autonomous control pipeline on Raspberry Pi 5:
  - **Phase RB (Rule-Based):** Baseline controller mirrors the Pico WH firmware logic, providing the initial data collection phase.
  - **Phase FQL (Fuzzy Q-Learning):** Agent trains online from both real pond data (Pico WH serial stream) and a virtual pond simulator running interleaved — 10 virtual steps per real step. FQL convergence detection is active; upon convergence, the Q-table is transmitted to the Pico WH via serial.
  - **Phase DQN (Deep Q-Network):** Trains offline on the accumulated replay buffer (real + virtual transitions). DQN only activates on the Pico after FQL has demonstrated superior reward over RB for at least 1,000 real steps, ensuring the progressive improvement is validated before handoff.
  - The full pipeline (RB → FQL → DQN) has been demonstrated end-to-end with logged results showing FQL reward Δ=+0.36 over RB and DQN achieving the lowest NH3 exposure (10.47%) among all three controllers.
  - A simulation-based evaluation script (`simulate_compare.py`) was developed to fairly compare all three controllers under identical virtual scenarios and random seeds, independent of real pond timing.

- **PQC RP2040 Project:** Successfully completed the Post-Quantum Cryptography (PQC) implementation on the RP2040 microcontroller. The project is finalized and documented.

- **Micro ROS — ROS ↔ RP2040 Integration:** Successfully established communication between ROS and the RP2040 via Micro ROS. The connection is stable and verified.

---

## 2. [This Week] What will you do between now and the next daily scrum?

This week I will complete the following targeted tasks:

- **Aquaculture Thesis:**
  - Continue running the live RB → FQL → DQN pipeline on RPi5 to accumulate sufficient real-world data for the final thesis comparison figures.
  - Run `simulate_compare.py` with 30 episodes × 7 scenarios to produce fair simulation-based evaluation plots (pH trace, NH3, cumulative reward, action distribution) for the thesis.
  - Analyze and finalize the three-way comparison (RB vs FQL vs DQN) for the results chapter.

- **PQC RP2040:**
  - Assist Ryan tomorrow in understanding the completed PQC RP2040 project — walk through the implementation, key design decisions, and codebase structure.

- **Micro ROS:**
  - Develop a sample OS-level project on RP2040 using Micro ROS as a working example — demonstrating the ROS–microcontroller communication in a structured, reproducible setup.

---

## 3. [Issues] What impedes you from performing your work as effectively as possible?

- **DQN Policy Impediment:** The DQN agent exhibits over-aggressive use of the HIGH aeration action (~15%) in conditions where LOW would suffice. This is caused by the virtual replay buffer being skewed toward extreme scenarios (ACID_CRASH, HIGH_NH3), which trains the DQN to generalize HIGH too broadly. This inflates energy consumption in the DQN phase.

- **Fair Comparison Timing Impediment:** The three-phase pipeline runs sequentially in real time — RB, FQL, and DQN phases occur at different times of day with potentially different pond conditions (pH, temperature, DO). This makes the raw CSV comparison inherently unfair, which is why the simulation-based evaluation (`simulate_compare.py`) is needed as the primary benchmark.

- **FQL Convergence on Virtual Data Impediment:** FQL converges primarily on virtual simulator data (virtual steps >> real steps), meaning its Q-table is optimized for simulated conditions before sufficient real-world exposure. On restart with a saved Q-table, the system skips the RB phase entirely, which can prevent the reward baseline comparison from being computed.
