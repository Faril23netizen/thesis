# N3IWF Implementation Changelog

## 🎯 Tujuan Perubahan

Membuat implementasi **N3IWF Real Server** yang mirip dengan `testing_n3iwf` tapi untuk **real deployment** dengan progressive learning.

## 📦 File Baru

### 1. `n3iwf/server.py`
**Fungsi:** TCP Server + Flask Dashboard + Progressive Learning

**Fitur Utama:**
- ✅ Menerima data REAL dari Pico 2W via TCP port 5005
- ✅ Progressive Learning: Rule-Based (100 steps) → FQL (200 steps) → DQN (forever)
- ✅ Real-time inference dengan timing measurement
- ✅ CSV logging lengkap ke `results/n3iwf_real/n3iwf_real_log.csv`
- ✅ Auto-save Q-table setiap 50 steps FQL
- ✅ DQN online training dengan replay buffer
- ✅ IPsec tunnel monitoring
- ✅ Network stats integration
- ✅ Flask dashboard di port 5000

**Perbedaan dengan `testing_n3iwf/server.py`:**
| Aspek | testing_n3iwf | n3iwf |
|---|---|---|
| Mode | `--sim` (simulasi) | Real only |
| Data | Sintetis | Pico TCP |
| Learning | ❌ | ✅ RB→FQL→DQN |
| Q-table | Read-only | Update & save |
| DQN | Read-only | Train online |

### 2. `n3iwf/analyze_n3iwf_real.py`
**Fungsi:** Analisis data real dengan fokus progressive learning

**Output:**
- 7 grafik analisis:
  1. Latency over time
  2. Jitter over time
  3. Reward over time (colored by phase)
  4. CDF latency
  5. Latency histogram
  6. Inference time bar chart
  7. FQL epsilon decay
- Summary table (network + learning metrics)
- CSV export: `n3iwf_real_summary.csv`

**Perbedaan dengan `testing_n3iwf/analyze_n3iwf.py`:**
- ✅ Tambahan: Reward analysis per phase
- ✅ Tambahan: FQL epsilon decay chart
- ✅ Tambahan: Phase-colored scatter plot
- ✅ Tambahan: Learning performance metrics

### 3. `n3iwf/USAGE.md`
Dokumentasi lengkap cara penggunaan server real.

### 4. `n3iwf/CHANGELOG.md`
Dokumen ini.

## 📊 Struktur Folder Baru

```
results/
├── n3iwf/                    # Testing (simulasi)
│   ├── n3iwf_log.csv
│   ├── n3iwf_summary.csv
│   └── n3iwf_analysis.png
└── n3iwf_real/               # Real deployment (NEW!)
    ├── n3iwf_real_log.csv
    ├── n3iwf_real_summary.csv
    ├── n3iwf_real_analysis.png
    └── qtable.json
```

## 🔄 Progressive Learning Flow

```
Step 0-99:    Rule-Based Phase
              - Pure heuristic
              - Baseline performance
              
Step 100-299: FQL Phase
              - Q-table learning
              - Epsilon: 0.3 → 0.05
              - Save Q-table every 50 steps
              
Step 300+:    DQN Phase
              - Deep Q-Network
              - Replay buffer (max 10000)
              - Train every 10 steps (batch=32)
```

## 📝 CSV Log Format

### `n3iwf_real_log.csv`
```csv
timestamp,packet_no,pH,T_C,phase,action,reward,rb_ms,fql_ms,dqn_ms,latency_ms,buffer_size,fql_eps
2026-05-17 18:30:15,1,7.234,28.5,RB,LOW,0.8234,0.023,0.045,0.067,12.3,0,0.3
2026-05-17 18:30:17,2,7.189,28.7,RB,LOW,0.7891,0.021,0.043,0.065,11.8,0,0.3
...
2026-05-17 18:35:20,101,7.456,29.1,FQL,MED,0.6543,0.022,0.048,0.066,13.1,0,0.295
...
2026-05-17 18:45:30,301,7.321,28.9,DQN,LOW,0.8912,0.023,0.047,0.071,12.7,1024,0.05
```

**Kolom Baru (vs testing_n3iwf):**
- `phase` - RB/FQL/DQN
- `reward` - Reward value
- `buffer_size` - DQN replay buffer size
- `fql_eps` - FQL epsilon value

## 🔧 Konfigurasi

### Phase Duration
Edit di `n3iwf/server.py`:
```python
PHASE_RB_STEPS  = 100   # Rule-Based steps
PHASE_FQL_STEPS = 200   # FQL steps
```

### Reward Function
```python
def compute_reward(pH: float, T: float, action: int) -> float:
    pH_penalty = abs(7.0 - pH) * 0.5 if pH < 6.5 or pH > 8.5 else 0
    T_penalty = (T - 30.0) * 0.1 if T > 30.0 else 0
    cost = ACTION_COST[action]
    return 1.0 - pH_penalty - T_penalty - cost
```

## 🚀 Cara Penggunaan

### 1. Jalankan Server
```bash
python3 n3iwf/server.py
```

### 2. Koneksikan Pico
Pastikan Pico dikonfigurasi dengan IP server yang benar.

### 3. Monitor Dashboard
```
http://<IP_RPi5>:5000
```

### 4. Analisis Hasil
```bash
python3 n3iwf/analyze_n3iwf_real.py
```

## 📈 Expected Results

Setelah 300+ steps:
- ✅ Reward: RB (~0.7) → FQL (~0.75) → DQN (~0.85)
- ✅ FQL epsilon: 0.3 → 0.05
- ✅ DQN buffer: 0 → ~10000 samples
- ✅ Inference time: <1ms (semua algoritma)
- ✅ Network latency: ~12ms avg

## 🆚 Comparison Matrix

| Feature | testing_n3iwf | n3iwf (NEW) |
|---|---|---|
| **Data Source** | Simulasi sintetis | Pico 2W TCP |
| **Mode Flag** | `--sim` | Always real |
| **Learning** | ❌ | ✅ Progressive |
| **Q-table** | Read-only | Update + save |
| **DQN** | Read-only | Train online |
| **Reward** | N/A | Computed |
| **Phase** | N/A | RB→FQL→DQN |
| **Buffer** | N/A | Replay buffer |
| **Epsilon** | N/A | Decay tracking |
| **CSV Columns** | 11 | 13 (+phase, +reward, +buffer_size, +fql_eps) |
| **Grafik** | 6 | 7 (+reward, +epsilon) |
| **Tujuan** | Network testing | Real deployment |

## 🔗 Integration dengan Sistem Lain

### 1. Dengan `main/real/run_real.py`
`n3iwf/server.py` adalah **standalone version** yang tidak perlu `run_real.py`.

**Perbedaan:**
- `run_real.py`: Menggunakan `wifi_bridge.py` + `state.json`
- `n3iwf/server.py`: All-in-one TCP server + dashboard

### 2. Dengan `testing_n3iwf/`
Keduanya bisa jalan bersamaan di port berbeda:
```bash
# Terminal 1: Testing (simulasi)
python3 testing_n3iwf/server.py --sim  # Port 5000

# Terminal 2: Real (Pico)
python3 n3iwf/server.py                # Port 5001 (ubah di code)
```

## 📚 Referensi

- Original implementation: `main/real/run_real.py`
- Testing reference: `testing_n3iwf/server.py`
- FQL Agent: `fql/fql_agent.py`
- DQN Agent: `dqn/dqn_agent.py`

## ✅ Testing Checklist

- [x] Syntax check: `python -m py_compile n3iwf/server.py`
- [x] Syntax check: `python -m py_compile n3iwf/analyze_n3iwf_real.py`
- [ ] Run server tanpa Pico (should wait on port 5005)
- [ ] Connect Pico dan verify data logging
- [ ] Verify progressive learning (RB→FQL→DQN)
- [ ] Verify Q-table auto-save
- [ ] Verify DQN training
- [ ] Run analysis script
- [ ] Verify dashboard accessible

## 🐛 Known Issues

None yet. Ini adalah implementasi baru yang belum ditest dengan hardware.

## 📅 Timeline

- **2026-05-17**: Initial implementation
  - Created `n3iwf/server.py`
  - Created `n3iwf/analyze_n3iwf_real.py`
  - Created documentation

## 👤 Author

Faril - Thesis Implementation
