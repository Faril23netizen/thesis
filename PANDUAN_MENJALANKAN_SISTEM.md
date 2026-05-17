# 🚀 Panduan Menjalankan Sistem Aquaculture N3IWF

## 📋 Overview Sistem

Ada **2 cara** menjalankan sistem:

### 1. **Cara Original** (Recommended untuk Production)
- File: `main/real/run_real.py`
- Fitur: Progressive Learning (RB → FQL → DQN)
- Output: `results/hasil_real/`
- Analisis: `main/real/analyze_results.py`

### 2. **Cara N3IWF Server** (Untuk Testing & Dashboard)
- File: `n3iwf/server.py`
- Fitur: TCP Server + Dashboard + Progressive Learning
- Output: `results/n3iwf_real/`
- Analisis: `n3iwf/analyze_n3iwf_real.py`
- Dashboard: `http://<IP_RPI>:5000`

---

## 🎯 CARA 1: Original System (run_real.py)

### Step 1: Jalankan Main System

```bash
# Di RPi5
cd /path/to/project
python3 main/real/run_real.py
```

**Output yang diharapkan:**
```
[2026-05-17 18:30:15] [INFO] =============================================
[2026-05-17 18:30:15] [INFO] Aquaculture FQL Controller — Raspberry Pi 4
[2026-05-17 18:30:15] [INFO]   Virtual sim   : 10 steps per real step
[2026-05-17 18:30:15] [INFO]   Episode length: 300 steps per scenario
[2026-05-17 18:30:15] [INFO] =============================================
[2026-05-17 18:30:15] [INFO] Pico monitor log: results/hasil_real/pico_monitor.log
[2026-05-17 18:30:15] [INFO]   Run in second terminal: tail -f results/hasil_real/pico_monitor.log
[2026-05-17 18:30:15] [INFO] PHASE A — Waiting for Pico WH connection (virtual sim running in background)...
```

### Step 2: Monitor Log (Terminal Kedua)

```bash
# Terminal 2
tail -f results/hasil_real/pico_monitor.log
```

### Step 3: Tunggu Pico Terkoneksi

Setelah Pico terhubung, sistem akan otomatis:
- ✅ Mulai learning dari data real
- ✅ Interleave dengan virtual simulator
- ✅ Save Q-table otomatis
- ✅ Log ke CSV

### Step 4: Analisis Hasil

Setelah data terkumpul (minimal 100 steps):

```bash
python3 main/real/analyze_results.py
```

**Output:**
- `results/hasil_real/analysis_plots.png` - Grafik analisis
- Terminal: Statistik lengkap

**Grafik yang dihasilkan:**
1. pH & Temperature over time
2. Action distribution
3. Reward over time
4. Energy consumption
5. FQL vs Rule-Based comparison

---

## 🎯 CARA 2: N3IWF Server (server.py + Dashboard)

### Step 1: Jalankan N3IWF Server

```bash
# Di RPi5
cd /path/to/project
python3 n3iwf/server.py
```

**Output yang diharapkan:**
```
[FQL] Q-table loaded from simulation, epsilon=0.3
[DQN] Model loaded from simulation
============================================================
  Aquaculture N3IWF Real Server — Progressive Learning
============================================================
  Dashboard  : http://192.168.99.103:5000
  TCP Port   : 5005 (Pico 2W)
  Mode       : REAL (data dari Pico)
  Learning   : RB(100) → FQL(200) → DQN
  RB         : ✅
  FQL        : ✅
  DQN        : ✅
  CSV Log    : results/n3iwf_real/n3iwf_real_log.csv
============================================================

[TCP] Waiting for Pico 2W on port 5005 ...
```

### Step 2: Akses Dashboard

Buka browser:
```
http://<IP_RPi5>:5000
```

**Dashboard menampilkan:**
- 📊 pH & Suhu real-time
- 🎯 Phase saat ini (RB/FQL/DQN)
- ⚡ Action & Reward
- 📈 Steps per phase
- ⏱️ Inference time
- 🌐 Network latency
- 🔒 IPsec status

### Step 3: Monitor Terminal

Terminal akan menampilkan log real-time:
```
[RB] pH=7.23 T=28.5°C | Action=LOW Reward=0.823 | Steps: RB=1 FQL=0 DQN=0
[RB] pH=7.19 T=28.7°C | Action=LOW Reward=0.789 | Steps: RB=2 FQL=0 DQN=0
...
[FQL] pH=7.46 T=29.1°C | Action=MED Reward=0.654 | Steps: RB=100 FQL=1 DQN=0
  [FQL] Q-table saved (50 steps)
...
[DQN] pH=7.32 T=28.9°C | Action=LOW Reward=0.891 | Steps: RB=100 FQL=200 DQN=1
```

### Step 4: Analisis Hasil N3IWF

Setelah data terkumpul (minimal 10 packets):

```bash
python3 n3iwf/analyze_n3iwf_real.py
```

**Output:**
- `results/n3iwf_real/n3iwf_real_analysis.png` - 7 grafik
- `results/n3iwf_real/n3iwf_real_summary.csv` - Tabel ringkasan
- Terminal: Statistik lengkap

**Grafik yang dihasilkan:**
1. Latency over time
2. Jitter over time
3. Reward over time (colored by phase)
4. CDF latency
5. Latency histogram
6. Inference time bar chart (RB vs FQL vs DQN)
7. FQL epsilon decay

---

## 📊 Perbandingan Kedua Cara

| Aspek | run_real.py | n3iwf/server.py |
|---|---|---|
| **Tujuan** | Production deployment | Testing + Monitoring |
| **Dashboard** | ❌ | ✅ (Port 5000) |
| **TCP Server** | WiFiBridge internal | Standalone TCP 5005 |
| **Output Folder** | `results/hasil_real/` | `results/n3iwf_real/` |
| **CSV Format** | `comparison.csv` | `n3iwf_real_log.csv` |
| **Analisis** | `analyze_results.py` | `analyze_n3iwf_real.py` |
| **Virtual Sim** | ✅ Interleaved | ❌ |
| **Progressive Learning** | ✅ | ✅ |
| **IPsec Monitor** | ❌ | ✅ |
| **Network Stats** | ❌ | ✅ |

---

## 🔧 Konfigurasi Pico 2W

Pastikan Pico dikonfigurasi dengan IP server yang benar:

### Untuk run_real.py (WiFiBridge)
Edit di `data_collection_test/main.c`:
```c
#define WIFI_SSID "your_wifi_ssid"
#define WIFI_PASSWORD "your_wifi_password"
#define SERVER_IP "192.168.99.103"  // IP RPi5
#define SERVER_PORT 5005
```

### Untuk n3iwf/server.py (TCP Server)
Edit di `data_collection_test/main.c`:
```c
#define N3IWF_SERVER_IP "192.168.99.103"  // IP RPi5
#define N3IWF_SERVER_PORT 5005
```

---

## 📁 Struktur Output

### Cara 1: run_real.py
```
results/hasil_real/
├── fql.log                    # Log utama
├── fql_error.log              # Error log
├── pico_monitor.log           # Raw data dari Pico
├── comparison.csv             # Data untuk analisis
├── qtable.json                # Q-table FQL
├── dqn_buffer.json            # Replay buffer DQN
├── state.json                 # State dashboard
└── analysis_plots.png         # Hasil analisis
```

### Cara 2: n3iwf/server.py
```
results/n3iwf_real/
├── n3iwf_real_log.csv         # Log lengkap
├── qtable.json                # Q-table FQL
├── n3iwf_real_analysis.png    # Hasil analisis
└── n3iwf_real_summary.csv     # Ringkasan statistik
```

---

## 🐛 Troubleshooting

### Pico tidak terkoneksi

```bash
# Cek IP Pico
ping <IP_PICO>

# Cek port listening
sudo netstat -tulpn | grep 5005

# Cek firewall
sudo ufw status
sudo ufw allow 5005/tcp
```

### Dashboard tidak bisa diakses (n3iwf/server.py)

```bash
# Cek Flask running
ps aux | grep server.py

# Cek port 5000
sudo netstat -tulpn | grep 5000

# Cek firewall
sudo ufw allow 5000/tcp
```

### FQL/DQN tidak tersedia

```bash
# Test import
python3 -c "from fql.fql_agent import FQLAgent; print('FQL OK')"
python3 -c "from dqn.dqn_agent import DQNAgent; print('DQN OK')"

# Cek file ada
ls fql/fql_agent.py
ls dqn/dqn_agent.py
```

### Analisis error: "File tidak ditemukan"

```bash
# Cek file CSV ada
ls -lh results/hasil_real/comparison.csv
ls -lh results/n3iwf_real/n3iwf_real_log.csv

# Tunggu minimal data terkumpul
# run_real.py: minimal 100 steps
# n3iwf/server.py: minimal 10 packets
```

---

## 📈 Expected Results

### Setelah 300+ steps (RB + FQL + DQN):

**Learning Performance:**
- ✅ Reward: RB (~0.7) → FQL (~0.75) → DQN (~0.85)
- ✅ FQL epsilon: 0.3 → 0.05 (exploration → exploitation)
- ✅ DQN buffer: 0 → ~10,000 samples
- ✅ Q-table: Converged & saved

**System Performance:**
- ✅ Inference time: <1ms (semua algoritma)
- ✅ Network latency: ~12ms avg (via N3IWF)
- ✅ Jitter: <5ms
- ✅ Packet delivery: >99%

**Water Quality:**
- ✅ pH: Stabil di 6.5-8.5
- ✅ Temperature: Stabil di 26-30°C
- ✅ NH3: <0.02 ppm (safe level)

---

## 🎯 Rekomendasi

### Untuk Production:
**Gunakan `run_real.py`**
- ✅ Lebih stabil
- ✅ Virtual simulator interleaved
- ✅ Auto-save state
- ✅ Systemd service ready

### Untuk Development/Testing:
**Gunakan `n3iwf/server.py`**
- ✅ Dashboard real-time
- ✅ Network monitoring
- ✅ IPsec status
- ✅ Lebih mudah debug

### Untuk Analisis:
**Gunakan kedua script analisis:**
- `main/real/analyze_results.py` - Fokus learning performance
- `n3iwf/analyze_n3iwf_real.py` - Fokus network + learning

---

## 📚 Dokumentasi Lengkap

- **Original System**: `main/real/run_real.py` (lihat docstring)
- **N3IWF Server**: `n3iwf/USAGE.md`
- **Changelog**: `n3iwf/CHANGELOG.md`
- **Setup N3IWF**: `n3iwf/README.md`

---

## ✅ Checklist Sebelum Menjalankan

- [ ] RPi5 sudah setup (Python 3, dependencies installed)
- [ ] Pico 2W sudah flashed dengan firmware terbaru
- [ ] Network configured (WiFi/5G)
- [ ] IP address sudah benar di Pico code
- [ ] Port 5005 tidak digunakan aplikasi lain
- [ ] (Optional) Port 5000 untuk dashboard
- [ ] Folder `results/` sudah ada (auto-created)
- [ ] FQL & DQN agents tersedia

---

**Author:** Faril  
**Date:** 2026-05-17  
**Version:** 1.0
