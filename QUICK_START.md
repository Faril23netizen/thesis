# ⚡ Quick Start - Aquaculture N3IWF

## 🚀 CARA 1: N3IWF Server (Recommended - Ada Dashboard)

**Untuk deployment dengan N3IWF + Dashboard real-time**

```bash
# Jalankan server (TCP + Dashboard)
python3 n3iwf/server.py

# Akses dashboard
http://<IP_RPi5>:5000
```

**Output:** `results/n3iwf_real/n3iwf_real_log.csv`

**Analisis:**
```bash
python3 n3iwf/analyze_n3iwf_real.py
```

---

## 🎯 CARA 2: run_real.py (Production - No Dashboard)

**Untuk deployment production dengan virtual simulator**

### **Dengan Dashboard (Optional)**

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

**Output:** `results/hasil_real/comparison.csv`

**Analisis:**
```bash
python3 main/real/analyze_results.py
```

---

## 📊 Perbedaan Kedua Cara

| Aspek | n3iwf/server.py | run_real.py |
|---|---|---|
| **Dashboard** | ✅ Built-in | ❌ (perlu dashboard.py terpisah) |
| **TCP Server** | ✅ Port 5005 | ✅ WiFiBridge internal |
| **Virtual Sim** | ❌ | ✅ Interleaved |
| **Output** | `n3iwf_real/` | `hasil_real/` |
| **Analisis** | `analyze_n3iwf_real.py` | `analyze_results.py` |
| **Tujuan** | **N3IWF Testing** | Production |

**Rekomendasi:** Gunakan **`n3iwf/server.py`** untuk deployment dengan N3IWF + dashboard!

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
