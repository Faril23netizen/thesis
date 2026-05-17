# ⚡ Quick Start - Aquaculture N3IWF

## 🚀 CARA PRODUCTION (Recommended)

### **Dengan Dashboard (NEW!)**

```bash
# Terminal 1: Jalankan sistem
python3 main/real/run_real.py

# Terminal 2: Jalankan dashboard
python3 main/real/dashboard.py

# Akses dashboard
http://<IP_RPi5>:5000
```

### **Tanpa Dashboard**

```bash
# Jalankan
python3 main/real/run_real.py

# Monitor (terminal kedua)
tail -f results/hasil_real/pico_monitor.log
```

### **Analisis**

```bash
# Setelah 100+ steps
python3 main/real/analyze_results.py
```

**Output:** `results/hasil_real/analysis_plots.png`

---

## 🎯 CARA TESTING (n3iwf/server.py)

**⚠️ HANYA UNTUK TESTING MODE (bukan real Pico)**

```bash
# Jalankan
python3 n3iwf/server.py --sim

# Akses dashboard
http://<IP_RPi5>:5000
```

**Catatan:** `n3iwf/server.py` untuk testing dengan data sintetis, bukan untuk real Pico deployment!

---

## 📊 Perbedaan Singkat

| | run_real.py + dashboard.py | n3iwf/server.py |
|---|---|---|
| Data | Real Pico | Simulasi |
| Dashboard | ✅ (port 5000) | ✅ (port 5000) |
| Virtual Sim | ✅ | ❌ |
| Output | `hasil_real/` | `n3iwf_real/` |
| Tujuan | **Production** | Testing |

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
