# Edge-Intelligent Aquaculture Controller 🐟

Progressive Hybrid FQL-DQN controller untuk aquaculture dengan N3IWF integration.

---

## 🚀 Quick Start (3 Commands!)

```bash
# 1. Start semua
sudo ./start_all.sh

# 2. Monitor dashboard
http://10.42.0.1:5000

# 3. Stop dan analisis
sudo ./stop_all.sh
python3 analyze_all.py
```

**Restart setelah shutdown tidak normal:**
```bash
chmod +x quick_restart.sh
sudo ./quick_restart.sh
```

**Baca:** `START_HERE.md` atau `SINGLE_COMMAND_USAGE.md` untuk panduan lengkap.

---

## 📁 Struktur Project

```
start_all.sh          # ⭐ Start semua service
stop_all.sh           # ⭐ Stop semua service
analyze_all.py        # ⭐ Generate grafik + PDF

fql/                  # Fuzzy Q-Learning
dqn/                  # Deep Q-Network
n3iwf/                # N3IWF + Callbox Simulator
  ├── callbox_simulator.py
  ├── n3iwf_client.py
  └── server.py
main/
  ├── env/            # Pond simulator
  ├── simulasi/       # Virtual testing
  └── real/           # Hardware deployment
results/              # Output (logs, CSV, plots)
```

---

## 💻 Simulasi (Virtual)

Test algoritma tanpa hardware:

```bash
python3 -m main.simulasi.run_simulasi
```

Output: `results/simulation/`

---

## 🍓 Hardware (Raspberry Pi)

### Option A: Complete System (Recommended)

```bash
sudo ./start_all.sh       # Start semua
http://10.42.0.1:5000     # Dashboard
sudo ./stop_all.sh        # Stop semua
python3 analyze_all.py    # Analisis
```

Output: `results/thesis/complete_analysis.pdf`

### Option B: Manual (Legacy)

```bash
chmod +x start_edge.sh
./start_edge.sh
```

Output: `results/hasil_real/`

---

## ⚙️ Systemd Service (Auto-start)

Agar sistem auto-start saat RPi boot:

```bash
# Edit path di aquaculture.service
sudo cp aquaculture.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aquaculture
sudo systemctl start aquaculture

# Check status
sudo systemctl status aquaculture
```

---

## 🧠 Arsitektur

**Edge-to-MCU Distillation:**
- DQN training di RPi5 (Edge)
- Q-Table distillation ke RP2040 Pico
- O(1) inference di MCU (array lookup)
- Lebih efisien dari INT8 quantization

**Kenapa bypass INT8?**
- Tidak perlu matrix multiplication di MCU
- Latency minimal (O(1) lookup)
- Power consumption terendah
- Lebih simple dan reliable

---

**Author:** Faril  
**Version:** 2.0 - Simplified
