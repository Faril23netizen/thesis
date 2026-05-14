# Edge-Intelligent Aquaculture Controller 🐟

This project implements a **Progressive Hybrid FQL-DQN** controller for aquaculture aeration, integrated with an **N3IWF Local Edge Service** dashboard.

## 📁 Directory Structure
- `fql/` : Fuzzy Q-Learning algorithm and pretraining scripts.
- `dqn/` : Deep Q-Network logic and offline training scripts.
- `n3iwf/` : N3IWF Web Dashboard (Flask + HTML/JS).
- `main/` : Core execution scripts.
  - `main/simulasi/` : Scripts for virtual evaluation.
  - `main/real/` : Scripts for real hardware deployment (Raspberry Pi + RP2040).
  - `main/env/` : Virtual pond simulator and environment models.
- `results/` : Auto-generated directory for logs, CSVs, and trained models.

---

## 💻 1. Running Simulations (Virtual Environment)
Use the simulation mode to test the algorithms (Rule-Based vs FQL vs DQN) safely on your computer without any physical hardware.

```bash
# Run the full simulation comparison
python3 -m main.simulasi.run_simulasi

# Run simulation with specific parameters
python3 -m main.simulasi.run_simulasi --episodes 50 --steps 500
```
*(All generated graphs and CSVs will be saved in `results/simulation/`)*

---

## 🍓 2. Running Real Hardware (Raspberry Pi)
When deployed to the physical pond, use the provided bash script. This script automatically starts **both** the AI Controller and the Web Dashboard.

```bash
# Make the script executable (only needed once)
chmod +x start_edge.sh

# Start the edge services
./start_edge.sh
```
- **Dashboard:** Open your browser and go to `http://<IP_RASPBERRY_PI>:5000`
- **Logs & Data:** Q-Tables, Models, and Telemetry CSVs are saved to `results/hasil_real/`

### Analyzing Real Hardware Data
After running the real hardware for some time, you can generate performance graphs:
```bash
python3 -m main.real.analyze_results
```
*(Graphs will be saved in `results/hasil_real/`)*

---

## ⚙️ 3. Running as a 24/7 Background Service (SystemD)
To ensure the system automatically starts when the Raspberry Pi turns on (and restarts if it crashes), install it as a Linux service.

**Important:** Before installing, open `aquaculture.service` and ensure the paths (like `/home/ubuntu/thesis/`) correctly match your Raspberry Pi's directory structure.

```bash
# Copy the service file to systemd
sudo cp aquaculture.service /etc/systemd/system/

# Reload systemd manager
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable aquaculture

# Start the service right now
sudo systemctl start aquaculture
```

**Useful Service Commands:**
- Check status: `sudo systemctl status aquaculture`
- Stop service: `sudo systemctl stop aquaculture`
- View live logs: `tail -f results/hasil_real/service.log`

---

## 🧠 Architectural Note: Why We Bypass INT8 Quantization (TinyML)
In typical TinyML deployments, Deep Neural Networks are compressed using **INT8 Quantization** (via TensorFlow Lite for Microcontrollers) to allow Matrix Multiplication operations to run within the strict RAM and CPU constraints of microcontrollers. 

However, this system purposefully **bypasses INT8 Quantization** in favor of a much more efficient **Edge-to-MCU Distillation** architecture:

1. **Heavy Lifting on the Edge**: The Deep Q-Network (DQN) is trained and executed on the Raspberry Pi 5 (Edge Server), which has abundant computational resources.
2. **Q-Table Distillation**: Instead of exporting the neural network weights to the MCU, the Edge Server evaluates the continuous DQN across the discrete state space (pH and Temperature bounds) to generate a flat policy matrix (Q-Table).
3. **O(1) Inference on MCU**: This distilled Q-Table is serialized and sent to the RP2040 Pico. To predict an action, the Pico simply performs a 2D array lookup (`action = qtable[ph_idx][temp_idx]`).

**Conclusion:** 
By avoiding Neural Network inference on the microcontroller altogether, the RP2040 Pico requires **zero mathematical operations (no MACs)** to determine the optimal action. An `O(1)` memory lookup is mathematically the absolute lowest latency and lowest power consumption possible—making it strictly superior to even the most highly optimized INT8 Quantized neural network.
