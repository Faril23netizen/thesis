# N3IWF Real Server - Usage Guide

## 📋 Overview

`n3iwf/server.py` adalah server untuk **real deployment** dengan progressive learning:
- **Data source**: Pico 2W via TCP (real sensor pH & suhu)
- **Learning**: Rule-Based (100 steps) → FQL (200 steps) → DQN (forever)
- **Output**: CSV log + real-time dashboard

## 🚀 Quick Start

### 1. Jalankan Server
```bash
# Di RPi5
python3 n3iwf/server.py
```

**Output:**
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

### 2. Koneksikan Pico
Pastikan Pico sudah dikonfigurasi dengan IP server yang benar di `main.c`:
```c
#define N3IWF_SERVER_IP "192.168.99.103"  // IP RPi5
#define N3IWF_SERVER_PORT 5005
```

### 3. Monitor Dashboard
Buka browser: `http://<IP_RPi5>:5000`

Dashboard menampilkan:
- pH & Suhu real-time
- Phase saat ini (RB/FQL/DQN)
- Action & Reward
- Steps per phase
- Inference time
- Network latency
- IPsec status

### 4. Analisis Hasil
Setelah data terkumpul (minimal 10 packets):
```bash
python3 n3iwf/analyze_n3iwf_real.py
```

**Output:**
- `results/n3iwf_real/n3iwf_real_analysis.png` - 7 grafik analisis
- `results/n3iwf_real/n3iwf_real_summary.csv` - Tabel ringkasan

## 📊 Progressive Learning Flow

```
┌─────────────────────────────────────────────────────────┐
│  PHASE 1: Rule-Based (100 steps)                        │
│  - Baseline performance                                 │
│  - No learning, pure heuristic                          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  PHASE 2: FQL (200 steps)                               │
│  - Q-table learning                                     │
│  - Epsilon decay: 0.3 → 0.05                            │
│  - Save Q-table setiap 50 steps                         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  PHASE 3: DQN (forever)                                 │
│  - Deep Q-Network                                       │
│  - Replay buffer (max 10000)                            │
│  - Train every 10 steps (batch=32)                      │
└─────────────────────────────────────────────────────────┘
```

## 📁 File Output

### CSV Log: `results/n3iwf_real/n3iwf_real_log.csv`
Kolom:
- `timestamp` - Waktu packet diterima
- `packet_no` - Nomor urut packet
- `pH`, `T_C` - Sensor data
- `phase` - RB/FQL/DQN
- `action` - OFF/LOW/MED/HIGH
- `reward` - Reward value
- `rb_ms`, `fql_ms`, `dqn_ms` - Inference time per algoritma
- `latency_ms` - Network latency
- `buffer_size` - DQN replay buffer size
- `fql_eps` - FQL epsilon value

### Q-table: `results/n3iwf_real/qtable.json`
Disimpan otomatis setiap 50 steps FQL.

## 🔧 Konfigurasi

Edit di `n3iwf/server.py`:

```python
# Progressive learning steps
PHASE_RB_STEPS  = 100   # Rule-Based steps
PHASE_FQL_STEPS = 200   # FQL steps
# Setelah itu: DQN forever

# Reward function
def compute_reward(pH: float, T: float, action: int) -> float:
    # Customize reward logic here
    ...
```

## 🆚 Perbedaan dengan `testing_n3iwf`

| Fitur | `testing_n3iwf` | `n3iwf` |
|---|---|---|
| Data | Simulasi sintetis | Real dari Pico |
| Learning | ❌ (hanya inference) | ✅ Progressive RB→FQL→DQN |
| Mode | `--sim` flag | Selalu real |
| Q-table | Read-only | Update & save |
| DQN | Read-only | Train online |
| Tujuan | Network testing | Real deployment |

## 🐛 Troubleshooting

### Server tidak menerima data dari Pico
```bash
# Cek koneksi
ping <IP_PICO>

# Cek port
sudo netstat -tulpn | grep 5005
```

### FQL/DQN tidak tersedia
```bash
# Pastikan module ada
ls fql/fql_agent.py
ls dqn/dqn_agent.py

# Test import
python3 -c "from fql.fql_agent import FQLAgent; print('OK')"
python3 -c "from dqn.dqn_agent import DQNAgent; print('OK')"
```

### Dashboard tidak bisa diakses
```bash
# Cek Flask running
ps aux | grep server.py

# Cek firewall
sudo ufw status
sudo ufw allow 5000/tcp
```

## 📈 Monitoring Real-time

```bash
# Terminal 1: Server
python3 n3iwf/server.py

# Terminal 2: Log monitoring
tail -f results/n3iwf_real/n3iwf_real_log.csv

# Terminal 3: IPsec status
watch -n 5 'sudo ipsec statusall | grep ESTABLISHED'
```

## 🎯 Expected Output

Setelah 300+ steps (RB+FQL+DQN), Anda akan melihat:
- ✅ Reward meningkat dari RB → FQL → DQN
- ✅ FQL epsilon decay dari 0.3 → 0.05
- ✅ DQN buffer terisi hingga ~10000 samples
- ✅ Inference time stabil (<1ms untuk semua algoritma)
- ✅ Network latency konsisten

## 📚 Referensi

- Progressive Learning: `main/real/run_real.py` (original implementation)
- Testing Mode: `testing_n3iwf/server.py` (simulation reference)
- Analysis: `n3iwf/analyze_n3iwf_real.py`
