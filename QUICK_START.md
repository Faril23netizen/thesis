# ⚡ Quick Start - Aquaculture N3IWF

## 🚀 Pilih Salah Satu Cara

### CARA 1: Production (Recommended)
```bash
# Jalankan
python3 main/real/run_real.py

# Monitor (terminal kedua)
tail -f results/hasil_real/pico_monitor.log

# Analisis (setelah 100+ steps)
python3 main/real/analyze_results.py
```

**Output:** `results/hasil_real/analysis_plots.png`

---

### CARA 2: Testing + Dashboard
```bash
# Jalankan
python3 n3iwf/server.py

# Akses dashboard
http://<IP_RPi5>:5000

# Analisis (setelah 10+ packets)
python3 n3iwf/analyze_n3iwf_real.py
```

**Output:** `results/n3iwf_real/n3iwf_real_analysis.png`

---

## 📊 Perbedaan Singkat

| | run_real.py | n3iwf/server.py |
|---|---|---|
| Dashboard | ❌ | ✅ |
| Virtual Sim | ✅ | ❌ |
| Output | `hasil_real/` | `n3iwf_real/` |
| Tujuan | Production | Testing |

---

## 🔧 Troubleshooting Cepat

```bash
# Pico tidak connect
ping <IP_PICO>
sudo netstat -tulpn | grep 5005

# Dashboard tidak bisa diakses
sudo ufw allow 5000/tcp

# Test agents
python3 -c "from fql.fql_agent import FQLAgent; print('OK')"
```

---

**Dokumentasi Lengkap:** `PANDUAN_MENJALANKAN_SISTEM.md`
